"""Deterministic HVI gating, 3-field thermal physics, and footprint CAPEX engine."""

from __future__ import annotations

import json
import math
import time
from functools import lru_cache
from pathlib import Path
from typing import Any

import geopandas as gpd
import numpy as np
import pandas as pd
import yaml

from backend.app.schemas import (
    CellBenefitResult,
    CityKey,
    SimulationRequest,
    SimulationResponse,
    WarmingWarning,
)
from backend.app.optimizer import compute_equity_and_neb

ROOT = Path(__file__).resolve().parents[2]
CONFIGS_DIR = ROOT / "configs"
DATA_DIR = ROOT / "data"


@lru_cache(maxsize=1)
def load_interventions_catalog() -> dict[str, Any]:
    with (CONFIGS_DIR / "interventions.yaml").open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)["interventions"]


@lru_cache(maxsize=1)
def load_cities_config() -> dict[str, Any]:
    with (CONFIGS_DIR / "cities.yaml").open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


@lru_cache(maxsize=1)
def load_provenance() -> dict[str, Any]:
    with (DATA_DIR / "provenance.json").open("r", encoding="utf-8") as f:
        return json.load(f)


@lru_cache(maxsize=2)
def load_city_dataframe(city: CityKey) -> pd.DataFrame:
    gdf = gpd.read_parquet(DATA_DIR / f"{city}_h3.parquet")
    return pd.DataFrame(gdf.drop(columns=["geometry"]))


def compute_hvi_single_cell(
    e_score: float | None,
    s_score: float | None,
    a_score: float | None,
    population: int,
    min_q: float = 0.67,
) -> tuple[float | None, float]:
    """
    AR4-style heat-priority index: HVI = 100 * [E + S + (1 - A)] / 3.
    Requires all mandatory core indicators and weight coverage q >= 0.67; else returns None (NA).
    """
    vals = [e_score, s_score, a_score]
    valid_count = sum(v is not None and not (isinstance(v, float) and math.isnan(v)) for v in vals)
    q = round(valid_count / 3.0, 4)
    if q < min_q or valid_count < 3 or population <= 0:
        return None, q
    hvi = round(100.0 * (float(e_score) + float(s_score) + (1.0 - float(a_score))) / 3.0, 2)
    return hvi, q


def _pick_range(bounds: dict[str, Any] | None, scenario: str, low_key: str, high_key: str) -> float:
    if not bounds:
        return 0.0
    lo = float(bounds[low_key])
    hi = float(bounds[high_key])
    if scenario == "min" or scenario == "low":
        return lo
    if scenario == "max" or scenario == "high":
        return hi
    return round((lo + hi) / 2.0, 4)


def _default_exposed_time_share(
    intervention_id: str,
    treated_m2: float,
    land_area_m2: float,
    transit_stops: int,
) -> float:
    """
    Estimate fraction of exposed person-minutes inside the treated footprint,
    explicitly retaining zero-benefit time outside the site.
    """
    if intervention_id == "shaded_transit_stop":
        # 20 m2 shelter covers 1 boarding queue (~20% of a rider's exposed daily walk+wait window)
        sheltered_queues = treated_m2 / 20.0
        denominator = max(float(transit_stops), 1.0)
        return float(np.clip((sheltered_queues / denominator) * 0.25, 0.02, 0.60))

    if intervention_id == "pocket_park":
        # Neighborhood refuge visits represent a bounded share of daily outdoor exposure
        return float(np.clip((treated_m2 / max(land_area_m2, 1.0)) * 8.0, 0.01, 0.35))

    # Area-proportional outdoor exposure for street corridors, paving, and district roofs
    return float(np.clip((treated_m2 / max(land_area_m2, 1.0)) * 2.5, 0.005, 0.75))


def simulate_scenario(req: SimulationRequest) -> SimulationResponse:
    """Run deterministic footprint-level thermal, CAPEX, NEB, and equity simulation."""
    t0 = time.perf_counter()
    catalog = load_interventions_catalog()
    df = load_city_dataframe(req.city)
    prov = load_provenance()
    cell_lookup = df.set_index("h3_index").to_dict(orient="index")

    cell_accum: dict[str, dict[str, Any]] = {}
    warnings: list[WarmingWarning] = []
    all_citations: set[str] = set()
    total_low = 0.0
    total_high = 0.0
    total_selected = 0.0
    weighted_water_num = 0.0
    weighted_beauty_num = 0.0
    step_free_capex = 0.0

    for p in req.placements:
        if p.intervention_id not in catalog:
            raise ValueError(f"Unknown intervention_id: {p.intervention_id}")
        if p.h3_index not in cell_lookup:
            raise ValueError(f"H3 cell {p.h3_index} not found in {req.city} grid.")

        spec = catalog[p.intervention_id]
        cell = cell_lookup[p.h3_index]
        unit_m2 = float(spec["default_unit_footprint_m2"])
        treated_m2 = float(p.footprint_m2) if p.footprint_m2 else unit_m2 * p.units

        capex_low = round(treated_m2 * float(spec["capex_eur_per_m2"]["low"]), 2)
        capex_high = round(treated_m2 * float(spec["capex_eur_per_m2"]["high"]), 2)
        capex_sel = round(
            treated_m2 * _pick_range(spec["capex_eur_per_m2"], req.cost_scenario, "low", "high"), 2
        )

        share = (
            float(p.exposed_time_share)
            if p.exposed_time_share is not None
            else _default_exposed_time_share(
                p.intervention_id,
                treated_m2,
                float(cell["land_area_m2"]),
                int(cell.get("transit_stops", 0)),
            )
        )

        # Keep LST/surface, 2m air, and pedestrian PET strictly separate
        raw_air = _pick_range(spec["metrics"]["delta_air_c"], req.cooling_scenario, "min", "max")
        raw_surf = _pick_range(spec["metrics"]["delta_surface_c"], req.cooling_scenario, "min", "max")
        raw_pet = _pick_range(spec["metrics"]["delta_pet_c"], req.cooling_scenario, "min", "max")
        mrt_pen = float(spec["metrics"].get("pedestrian_mrt_penalty_c", 0.0))

        exp_air = round(share * raw_air, 4)
        exp_surf = round(min(1.0, treated_m2 / max(float(cell["land_area_m2"]), 1.0)) * raw_surf, 4)
        exp_pet = round(share * raw_pet, 4)

        citations = list(spec.get("citations", []))
        all_citations.update(citations)

        if mrt_pen > 0:
            warnings.append(
                WarmingWarning(
                    h3_index=p.h3_index,
                    intervention_id=p.intervention_id,
                    pedestrian_mrt_penalty_c=mrt_pen,
                    affected_population=int(cell["population_count"]),
                    note=(
                        f"Reflective paving adds +{mrt_pen:.1f} C midday Mean Radiant Temperature "
                        "for pedestrians despite surface/air cooling (Middel et al. 2020)."
                    ),
                )
            )

        bucket = cell_accum.setdefault(
            p.h3_index,
            {
                "treated_footprint_m2": 0.0,
                "exposed_time_share": 0.0,
                "delta_air_c": 0.0,
                "delta_surface_c": 0.0,
                "delta_pet_c": 0.0,
                "capex_low_eur": 0.0,
                "capex_high_eur": 0.0,
                "capex_selected_eur": 0.0,
                "mrt_penalty_c": 0.0,
                "citations": set(),
            },
        )
        bucket["treated_footprint_m2"] += treated_m2
        # Combine non-overlapping exposure shares conservatively: 1 - (1 - s1)(1 - s2)
        bucket["exposed_time_share"] = round(
            1.0 - (1.0 - bucket["exposed_time_share"]) * (1.0 - share), 4
        )
        bucket["delta_air_c"] = round(min(bucket["delta_air_c"] + exp_air, 3.5), 4)
        bucket["delta_surface_c"] = round(min(bucket["delta_surface_c"] + exp_surf, 20.0), 4)
        bucket["delta_pet_c"] = round(min(bucket["delta_pet_c"] + exp_pet, 18.7), 4)
        bucket["capex_low_eur"] = round(bucket["capex_low_eur"] + capex_low, 2)
        bucket["capex_high_eur"] = round(bucket["capex_high_eur"] + capex_high, 2)
        bucket["capex_selected_eur"] = round(bucket["capex_selected_eur"] + capex_sel, 2)
        bucket["mrt_penalty_c"] = max(bucket["mrt_penalty_c"], mrt_pen)
        bucket["citations"].update(citations)

        total_low += capex_low
        total_high += capex_high
        total_selected += capex_sel

        neb_d = spec["neb_defaults"]
        weighted_water_num += capex_sel * float(neb_d["water_demand_score"])
        weighted_beauty_num += capex_sel * float(neb_d["beauty_prior"])
        if neb_d.get("step_free_access", False):
            step_free_capex += capex_sel

    cell_results = [
        CellBenefitResult(
            h3_index=cid,
            treated_footprint_m2=round(b["treated_footprint_m2"], 2),
            exposed_time_share=b["exposed_time_share"],
            delta_air_c=b["delta_air_c"],
            delta_surface_c=b["delta_surface_c"],
            delta_pet_c=b["delta_pet_c"],
            capex_low_eur=b["capex_low_eur"],
            capex_high_eur=b["capex_high_eur"],
            capex_selected_eur=b["capex_selected_eur"],
            mrt_penalty_c=b["mrt_penalty_c"],
            citations=sorted(b["citations"]),
        )
        for cid, b in cell_accum.items()
    ]

    air_map = {r.h3_index: r.delta_air_c for r in cell_results}
    pet_map = {r.h3_index: r.delta_pet_c for r in cell_results}
    avg_water = weighted_water_num / total_selected if total_selected > 0 else 0.0
    avg_beauty = weighted_beauty_num / total_selected if total_selected > 0 else 0.0
    step_free_ratio = step_free_capex / total_selected if total_selected > 0 else 0.0

    equity, neb_score, neb_pillars = compute_equity_and_neb(
        df=df,
        air_benefits=air_map,
        pet_benefits=pet_map,
        neb_weights=req.neb_weights,
        avg_water_demand=avg_water,
        avg_beauty_prior=avg_beauty,
        step_free_ratio=step_free_ratio,
        has_warming_warning=len(warnings) > 0,
    )

    unscored_share = float(prov["cities"][req.city]["summary"]["unscored_population_share"])
    elapsed_ms = round((time.perf_counter() - t0) * 1000.0, 2)

    return SimulationResponse(
        city=req.city,
        total_capex_eur=round(total_selected, 2),
        capex_range_eur=(round(total_low, 2), round(total_high, 2)),
        budget_remaining_eur=round(req.budget_eur - total_selected, 2),
        within_budget=total_selected <= req.budget_eur + 1e-6,
        neb_score=neb_score,
        neb_pillars=neb_pillars,
        equity=equity,
        warming_warnings=warnings,
        unscored_population_share=unscored_share,
        cell_results=cell_results,
        citations=sorted(all_citations),
        latency_ms=elapsed_ms,
    )