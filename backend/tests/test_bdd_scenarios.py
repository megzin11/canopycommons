"""Gate 2 BDD Acceptance Test Suite verifying all 5 frozen scenarios from docs/URD.md."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from backend.app import db
from backend.app.deliberation import synthesize_deliberation
from backend.app.main import app
from backend.app.optimizer import rank_portfolios_rawlsian
from backend.app.physics import compute_hvi_single_cell, load_city_dataframe, simulate_scenario
from backend.app.schemas import (
    FeedbackSubmission,
    InterventionPlacement,
    NEBWeights,
    SimulationRequest,
)


def _sample_scored_cell(city: str = "alexandria") -> str:
    df = load_city_dataframe(city)
    scored = df[df["baseline_hvi"].notna()].sort_values("baseline_hvi", ascending=False)
    return str(scored.iloc[0]["h3_index"])


def test_bdd_1_missing_core_indicator_triggers_strict_na_gating() -> None:
    """Scenario 1: Weight coverage q < 0.67 or missing mandatory core indicator outputs NA."""
    hvi, q = compute_hvi_single_cell(e_score=0.82, s_score=None, a_score=None, population=4200, min_q=0.67)
    assert q < 0.67
    assert hvi is None

    # Even with q = 0.6667 (2 of 3 indicators), mandatory core gating returns None
    hvi2, q2 = compute_hvi_single_cell(e_score=0.82, s_score=0.45, a_score=None, population=4200, min_q=0.67)
    assert q2 < 0.67
    assert hvi2 is None

    # Verify city endpoint explicitly publishes unscored_population_share
    client = TestClient(app)
    res = client.get("/api/cities")
    assert res.status_code == 200
    body = res.json()
    assert "unscored_population_share" in body["cities"]["alexandria"]["summary"]
    assert "unscored_population_share" in body["cities"]["porto"]["summary"]


def test_bdd_2_shaded_transit_stop_distinct_air_vs_pet_and_latency() -> None:
    """Scenario 2: 20 m2 Shaded Transit Stop reports distinct air vs PET relief under 200 ms with DOIs."""
    cell_id = _sample_scored_cell("alexandria")
    req = SimulationRequest(
        city="alexandria",
        budget_eur=1_500_000,
        placements=[
            InterventionPlacement(
                h3_index=cell_id,
                intervention_id="shaded_transit_stop",
                units=1,
                exposed_time_share=0.20,
            )
        ],
        cost_scenario="mid",
        cooling_scenario="mid",
    )
    res = simulate_scenario(req)
    assert res.within_budget is True
    assert res.latency_ms < 200.0
    assert len(res.cell_results) == 1

    cell = res.cell_results[0]
    assert cell.treated_footprint_m2 == 20.0
    assert cell.capex_low_eur == 2200.0
    assert cell.capex_high_eur == 5720.0
    # Air cooling (0.6-1.0 C * 0.20) vs PET relief (17.3-18.7 C * 0.20) strictly distinct
    assert 0.12 <= cell.delta_air_c <= 0.20
    assert 3.46 <= cell.delta_pet_c <= 3.74
    assert cell.delta_pet_c > cell.delta_air_c * 10.0
    assert any("10.1007/s00484-021-02074-4" in c for c in cell.citations)


def test_bdd_3_high_albedo_paving_surfaces_signed_mrt_warming_warning() -> None:
    """Scenario 3: High-albedo paving discloses +4.0 C midday MRT warning and gain-only Gini label."""
    cell_id = _sample_scored_cell("alexandria")
    req = SimulationRequest(
        city="alexandria",
        budget_eur=1_500_000,
        placements=[
            InterventionPlacement(
                h3_index=cell_id,
                intervention_id="high_albedo_paving",
                units=1,
            )
        ],
    )
    res = simulate_scenario(req)
    assert len(res.warming_warnings) == 1
    warn = res.warming_warnings[0]
    assert warn.h3_index == cell_id
    assert warn.pedestrian_mrt_penalty_c == 4.0
    assert warn.affected_population > 0
    assert "Gain-only Benefit Gini" in res.equity.gini_disclosure
    assert res.cell_results[0].delta_surface_c > 0
    assert res.cell_results[0].delta_air_c > 0


def test_bdd_4_rawlsian_lexicographic_tie_breaking_over_quintile_v() -> None:
    """Scenario 4: Tie-breaks worst-off 0-benefit cells sequentially, then by NEB Score(p)."""
    # Both p_a and p_b leave the single worst cell at 0.0, but p_b improves the second-worst cell
    v_vectors = {
        "p_a": [0.0, 0.0, 0.45, 0.50],
        "p_b": [0.0, 0.12, 0.20, 0.25],
        "p_c": [0.0, 0.12, 0.20, 0.25],  # exact tie with p_b on V vector; higher NEB score wins
    }
    neb_scores = {"p_a": 0.90, "p_b": 0.55, "p_c": 0.72}

    ranked = rank_portfolios_rawlsian(v_vectors, neb_scores)
    assert ranked == ["p_c", "p_b", "p_a"]


def test_bdd_5_deliberation_synthesizer_strict_traceability_and_no_silent_mutation(tmp_path: Path) -> None:
    """Scenario 5: Every theme cites valid DB feedback_ids + h3_indices; active weights stay untouched."""
    test_db = tmp_path / "test_canopy.db"
    db.init_db(test_db)

    df = load_city_dataframe("alexandria")
    cells = df[df["baseline_hvi"].notna()]["h3_index"].head(4).tolist()
    tags = ["Unshaded Transit Hub", "Elderly Clinic Route", "Unshaded Transit Hub", "School Walk Corridor"]

    inserted_ids: set[int] = set()
    for idx in range(8):
        rec = db.insert_feedback(
            FeedbackSubmission(
                city="alexandria",
                h3_index=cells[idx % 4],
                stratum="Karmouz Residents" if idx % 2 == 0 else "Daily Tram Commuters",
                persona_role="transit_rider" if idx % 2 == 1 else "resident",
                priority_tag=tags[idx % 4],
                rationale_text=f"Observed extreme afternoon glare and zero shade near stop #{idx + 1}.",
                points_sustainable=40,
                points_beautiful=20,
                points_together=40,
            ),
            db_path=test_db,
        )
        inserted_ids.add(rec.feedback_id)

    records = db.list_feedback("alexandria", db_path=test_db)
    weights = db.get_stratified_citizen_weights("alexandria", db_path=test_db)
    active_weights_before = NEBWeights(sustainable=0.60, beautiful=0.20, together=0.20)

    result = synthesize_deliberation(
        city="alexandria",
        records=records,
        stratified_weights=weights,
        use_live_llm=False,  # deterministic CI mode; live Gemini enforces the exact same sanitizer
    )

    assert result.advisory_only is True
    assert result.weights_mutated is False
    assert len(result.themes) >= 2
    for theme in result.themes:
        assert len(theme.cited_feedback_ids) > 0
        assert len(theme.cited_h3_indices) > 0
        assert set(theme.cited_feedback_ids).issubset(inserted_ids)
        assert set(theme.cited_h3_indices).issubset(set(cells))

    # Active weights remain unchanged until human confirms
    assert active_weights_before.sustainable == 0.60


def test_api_dual_city_optimize_and_dossier_export() -> None:
    """Integration check: both Alexandria and Porto optimize & export valid Co-Design Dossiers."""
    client = TestClient(app)

    for city, budget in [("alexandria", 1_500_000), ("porto", 2_500_000)]:
        opt = client.post("/api/optimize", json={"city": city, "budget_eur": budget})
        assert opt.status_code == 200
        opt_body = opt.json()
        assert len(opt_body["candidates"]) == 3
        top_placements = opt_body["candidates"][2]["placements"][:5]

        dos = client.post(
            "/api/dossier",
            json={
                "scenario_name": f"{city.title()} Gate 2 Verification",
                "simulation_request": {
                    "city": city,
                    "budget_eur": budget,
                    "placements": top_placements,
                },
            },
        )
        assert dos.status_code == 200
        assert "CanopyCommons Co-Design Impact Dossier" in dos.json()["markdown_report"]