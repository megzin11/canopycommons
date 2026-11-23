"""CanopyCommons FastAPI Backend (Phase 2)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from backend.app.db import (
    DEFAULT_DB_PATH,
    get_feedback_cell_boosts,
    get_stratified_citizen_weights,
    init_db,
    insert_feedback,
    list_feedback,
)
from backend.app.deliberation import synthesize_deliberation
from backend.app.optimizer import generate_pareto_portfolios
from backend.app.physics import (
    DATA_DIR,
    load_cities_config,
    load_interventions_catalog,
    load_provenance,
    simulate_scenario,
)
from backend.app.schemas import (
    CityKey,
    DeliberationResponse,
    FeedbackRecord,
    FeedbackSubmission,
    NEBWeights,
    OptimizeRequest,
    OptimizeResponse,
    SimulationRequest,
    SimulationResponse,
)

@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db(DEFAULT_DB_PATH)
    yield
    
app = FastAPI(
    title="CanopyCommons API",
    version="1.0.0",
    description="Participatory Urban Heat & Green-Corridor Co-Design Simulator (Alexandria + Porto)",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173", "*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class DossierRequest(BaseModel):
    scenario_name: str = Field(default="Co-Design Proposal")
    simulation_request: SimulationRequest


class DossierResponse(BaseModel):
    generated_utc: str
    scenario_name: str
    markdown_report: str
    json_payload: dict[str, Any]





@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "canopycommons-backend"}


@app.get("/api/cities")
def get_cities() -> dict[str, Any]:
    cfg = load_cities_config()
    prov = load_provenance()
    return {
        "h3_resolution": cfg["h3_resolution"],
        "normalization": cfg["normalization"],
        "pooled_bounds": prov["pooled_bounds"],
        "cities": {
            key: {**meta, "summary": prov["cities"][key]["summary"]}
            for key, meta in cfg["cities"].items()
        },
    }


@app.get("/api/cities/{city}/grid")
def get_city_grid(city: CityKey) -> dict[str, Any]:
    gj_path = Path(DATA_DIR) / f"{city}_h3.geojson"
    if not gj_path.exists():
        raise HTTPException(status_code=404, detail=f"GeoJSON grid not found for {city}")
    with gj_path.open("r", encoding="utf-8") as f:
        return json.load(f)


@app.get("/api/interventions")
def get_interventions() -> dict[str, Any]:
    return {"interventions": load_interventions_catalog()}


@app.post("/api/simulate", response_model=SimulationResponse)
def post_simulate(req: SimulationRequest) -> SimulationResponse:
    try:
        return simulate_scenario(req)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/optimize", response_model=OptimizeResponse)
def post_optimize(req: OptimizeRequest) -> OptimizeResponse:
    boosts = get_feedback_cell_boosts(req.city, db_path=DEFAULT_DB_PATH)
    return generate_pareto_portfolios(req, feedback_cell_boosts=boosts)


@app.get("/api/feedback/{city}")
def get_city_feedback(city: CityKey) -> dict[str, Any]:
    records = list_feedback(city, db_path=DEFAULT_DB_PATH)
    weights = get_stratified_citizen_weights(city, db_path=DEFAULT_DB_PATH)
    return {
        "city": city,
        "count": len(records),
        "stratified_citizen_weights": weights.model_dump() if weights else None,
        "records": [r.model_dump() for r in records],
    }


@app.post("/api/feedback", response_model=FeedbackRecord)
def post_feedback(sub: FeedbackSubmission) -> FeedbackRecord:
    return insert_feedback(sub, db_path=DEFAULT_DB_PATH)


@app.post("/api/deliberation/{city}", response_model=DeliberationResponse)
def post_deliberation(city: CityKey, use_live_llm: bool = True) -> DeliberationResponse:
    records = list_feedback(city, db_path=DEFAULT_DB_PATH)
    weights = get_stratified_citizen_weights(city, db_path=DEFAULT_DB_PATH)
    return synthesize_deliberation(
        city=city,
        records=records,
        stratified_weights=weights,
        use_live_llm=use_live_llm,
    )


@app.post("/api/dossier", response_model=DossierResponse)
def post_dossier(req: DossierRequest) -> DossierResponse:
    sim = simulate_scenario(req.simulation_request)
    feedback = list_feedback(req.simulation_request.city, db_path=DEFAULT_DB_PATH)
    now_utc = datetime.now(timezone.utc).isoformat()

    warnings_md = (
        "\n".join(
            f"- **{w.h3_index}** (`{w.intervention_id}`): +{w.pedestrian_mrt_penalty_c:.1f} C midday MRT "
            f"(~{w.affected_population:,} residents) — {w.note}"
            for w in sim.warming_warnings
        )
        if sim.warming_warnings
        else "- None (zero reflective-paving radiant warming penalties triggered)."
    )

    citations_md = "\n".join(f"- {c}" for c in sim.citations) if sim.citations else "- Baseline only."
    objections_md = (
        "\n".join(
            f"- `[#{f.feedback_id} | {f.h3_index} | {f.stratum}]` **{f.priority_tag}**: {f.rationale_text}"
            for f in feedback[:15]
        )
        if feedback
        else "- No stakeholder tags recorded yet."
    )

    md = f"""# CanopyCommons Co-Design Impact Dossier
- **Scenario:** {req.scenario_name}
- **City:** {sim.city.title()}
- **Generated (UTC):** {now_utc}
- **Budget Status:** EUR {sim.total_capex_eur:,.2f} spent (range EUR {sim.capex_range_eur[0]:,.0f}–{sim.capex_range_eur[1]:,.0f}) | Remaining: EUR {sim.budget_remaining_eur:,.2f}

## Key Equity & NEB Outcomes
| Metric | Value |
| :--- | :--- |
| NEB Composite Score | {sim.neb_score:.4f} (S={sim.neb_pillars['sustainable']:.2f}, B={sim.neb_pillars['beautiful']:.2f}, T={sim.neb_pillars['together']:.2f}) |
| Mean Experienced Air Cooling | {sim.equity.mean_air_benefit_c:.4f} C |
| Mean Experienced Pedestrian PET Relief | {sim.equity.mean_pet_benefit_c:.4f} C |
| Population-Weighted Benefit Gini (Air) | {sim.equity.benefit_gini_air if sim.equity.benefit_gini_air is not None else 'Undefined'} |
| Top HVI Quintile (V) Residents Reached | {sim.equity.v_residents_reached_share:.1%} |
| Unscored Population Share (q < 0.67 / Missing) | {sim.unscored_population_share:.2%} |

> **Equity Disclosure:** {sim.equity.gini_disclosure}

## Signed Pedestrian Warming Warnings
{warnings_md}

## Recorded Stakeholder Objections & Lived-Experience Tags
{objections_md}

## Literature Citations Used
{citations_md}
"""

    payload = {
        "generated_utc": now_utc,
        "scenario_name": req.scenario_name,
        "request": req.simulation_request.model_dump(),
        "simulation": sim.model_dump(),
        "stakeholder_feedback": [f.model_dump() for f in feedback],
    }
    return DossierResponse(
        generated_utc=now_utc,
        scenario_name=req.scenario_name,
        markdown_report=md,
        json_payload=payload,
    )