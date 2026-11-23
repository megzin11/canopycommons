"""Equity metrics (Benefit Gini, Rawlsian lexicographic priority) and NEB MCDA optimizer."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from backend.app.schemas import (
    EquityMetrics,
    InterventionPlacement,
    NEBWeights,
    OptimizeRequest,
    OptimizeResponse,
    PortfolioCandidate,
    SimulationRequest,
)


def compute_benefit_gini(populations: np.ndarray, benefits: np.ndarray) -> float | None:
    """
    Population-weighted Benefit Gini over nonnegative per-resident benefits b_i,
    explicitly including residents receiving zero benefit:
      p_i = N_i / sum(N), mu = sum(p_i * b_i),
      G = sum_i sum_j p_i * p_j * |b_i - b_j| / (2 * mu).
    Returns None (undefined) if total population is 0 or all benefits are zero (mu <= 0).
    """
    pop = np.asarray(populations, dtype=np.float64)
    ben = np.maximum(np.asarray(benefits, dtype=np.float64), 0.0)
    total_pop = float(pop.sum())
    if total_pop <= 0:
        return None

    p = pop / total_pop
    mu = float(np.dot(p, ben))
    if mu <= 1e-12:
        return None

    # Exact O(n log n) equivalent of double sum sum_i sum_j p_i p_j |b_i - b_j| / (2 * mu)
    order = np.argsort(ben)
    p_s = p[order]
    b_s = ben[order]
    cum_p = np.cumsum(p_s)
    cum_pb = np.cumsum(p_s * b_s)
    # Using trapezoidal Lorenz area: G = 1 - sum_k p_k * (L_{k-1} + L_k)
    lorenz = cum_pb / mu
    lorenz_prev = np.concatenate(([0.0], lorenz[:-1]))
    gini = 1.0 - float(np.sum(p_s * (lorenz_prev + lorenz)))
    return round(float(np.clip(gini, 0.0, 1.0)), 4)


def aggregate_stratified_neb_weights(
    votes_by_stratum: dict[str, list[tuple[int, int, int]]],
    stratum_shares: dict[str, float] | None = None,
) -> NEBWeights:
    """
    Compute W_j = sum_g pi_g * mean_{r in g}(points_{r,j} / 100) across participant strata.
    Defaults to equal stratum weights pi_g when custom shares are not supplied.
    """
    active = {g: v for g, v in votes_by_stratum.items() if v}
    if not active:
        return NEBWeights()

    if stratum_shares:
        raw_pi = {g: float(stratum_shares.get(g, 0.0)) for g in active}
        pi_sum = sum(raw_pi.values())
        pi = {g: (val / pi_sum if pi_sum > 0 else 1.0 / len(active)) for g, val in raw_pi.items()}
    else:
        pi = {g: 1.0 / len(active) for g in active}

    w_s = w_b = w_t = 0.0
    for g, votes in active.items():
        arr = np.asarray(votes, dtype=np.float64) / 100.0
        means = arr.mean(axis=0)
        w_s += pi[g] * float(means[0])
        w_b += pi[g] * float(means[1])
        w_t += pi[g] * float(means[2])

    return NEBWeights(sustainable=w_s, beautiful=w_b, together=w_t)


def compute_equity_and_neb(
    df: pd.DataFrame,
    air_benefits: dict[str, float],
    pet_benefits: dict[str, float],
    neb_weights: NEBWeights,
    avg_water_demand: float,
    avg_beauty_prior: float,
    step_free_ratio: float,
    has_warming_warning: bool,
) -> tuple[EquityMetrics, float, dict[str, float]]:
    """Compute citywide Benefit Gini, Rawlsian metrics on fixed quintile V, and NEB Score(p)."""
    inhabited = df[df["population_count"] > 0]
    pops = inhabited["population_count"].to_numpy(dtype=np.float64)
    air_vec = inhabited["h3_index"].map(lambda c: air_benefits.get(c, 0.0)).to_numpy(dtype=np.float64)
    pet_vec = inhabited["h3_index"].map(lambda c: pet_benefits.get(c, 0.0)).to_numpy(dtype=np.float64)

    total_pop = float(pops.sum())
    mean_air = round(float(np.dot(pops, air_vec) / max(total_pop, 1.0)), 4)
    mean_pet = round(float(np.dot(pops, pet_vec) / max(total_pop, 1.0)), 4)
    gini_air = compute_benefit_gini(pops, air_vec)

    if gini_air is None:
        disclosure = "Benefit Gini is undefined because mean experienced cooling benefit is zero."
    elif has_warming_warning:
        disclosure = (
            "Gain-only Benefit Gini on air cooling; signed pedestrian MRT warming (+4.0 C) "
            "and harmed population are disclosed separately."
        )
    else:
        disclosure = "Population-weighted Benefit Gini on nonnegative air cooling including zero-benefit residents."

    # Fixed top baseline HVI quintile V
    v_df = inhabited[inhabited["in_top_hvi_quintile_v"] == True]  # noqa: E712
    v_pops = v_df["population_count"].to_numpy(dtype=np.float64)
    v_air = v_df["h3_index"].map(lambda c: air_benefits.get(c, 0.0)).to_numpy(dtype=np.float64)

    rawlsian_min = round(float(v_air.min()), 4) if len(v_air) > 0 else 0.0
    v_pop_total = float(v_pops.sum())
    v_mean = round(float(np.dot(v_pops, v_air) / max(v_pop_total, 1.0)), 4)
    v_reached = round(float(v_pops[v_air > 0].sum() / max(v_pop_total, 1.0)), 4)

    # Fixed 0-1 New European Bauhaus pillar scales
    thermal_norm = float(np.clip((mean_air / 0.15) + (mean_pet / 1.5), 0.0, 1.0))
    v_sustainable = round(float(np.clip(0.75 * thermal_norm + 0.25 * (1.0 - avg_water_demand), 0.0, 1.0)), 4)
    v_beautiful = round(float(np.clip(avg_beauty_prior if len(air_benefits) > 0 else 0.0, 0.0, 1.0)), 4)
    v_together = round(float(np.clip(0.65 * v_reached + 0.35 * step_free_ratio, 0.0, 1.0)), 4)

    neb_score = round(
        neb_weights.sustainable * v_sustainable
        + neb_weights.beautiful * v_beautiful
        + neb_weights.together * v_together,
        4,
    )
    neb_pillars = {
        "sustainable": v_sustainable,
        "beautiful": v_beautiful,
        "together": v_together,
    }

    equity = EquityMetrics(
        mean_air_benefit_c=mean_air,
        mean_pet_benefit_c=mean_pet,
        benefit_gini_air=gini_air,
        gini_disclosure=disclosure,
        rawlsian_min_v_air_c=rawlsian_min,
        v_population_weighted_mean_c=v_mean,
        v_residents_reached_share=v_reached,
    )
    return equity, neb_score, neb_pillars


def rank_portfolios_rawlsian(
    portfolio_v_vectors: dict[str, list[float]],
    portfolio_neb_scores: dict[str, float],
) -> list[str]:
    """
    Rawlsian lexicographic maximin over fixed top baseline HVI quintile V:
    maximize min_{i in V} b_i(p); if tied (e.g., both 0), compare the next-worst cell in V
    sequentially; break remaining ties by stratified NEB Score(p).
    """
    def sort_key(pid: str) -> tuple[tuple[float, ...], float]:
        sorted_v = tuple(round(float(x), 6) for x in sorted(portfolio_v_vectors[pid]))
        return (sorted_v, round(float(portfolio_neb_scores[pid]), 6))

    return sorted(portfolio_v_vectors.keys(), key=sort_key, reverse=True)


def generate_pareto_portfolios(
    req: OptimizeRequest,
    feedback_cell_boosts: dict[str, int] | None = None,
) -> OptimizeResponse:
    """Generate 3 distinct budget-feasible co-design portfolios for Pareto comparison."""
    from backend.app.physics import load_city_dataframe, load_interventions_catalog, simulate_scenario

    df = load_city_dataframe(req.city)
    catalog = load_interventions_catalog()
    boosts = feedback_cell_boosts or {}
    scored = df[df["baseline_hvi"].notna()].copy()

    def unit_cost(iid: str) -> float:
        spec = catalog[iid]
        rates = spec["capex_eur_per_m2"]
        rate = rates["low"] if req.cost_scenario == "low" else rates["high"] if req.cost_scenario == "high" else (rates["low"] + rates["high"]) / 2.0
        return float(spec["default_unit_footprint_m2"]) * float(rate)

    def build_greedy(order_df: pd.DataFrame, prefer_transit: bool) -> list[InterventionPlacement]:
        rem = req.budget_eur
        placements: list[InterventionPlacement] = []
        transit_cost = unit_cost("shaded_transit_stop")
        canopy_cost = unit_cost("street_canopy")
        park_cost = unit_cost("pocket_park")

        for row in order_df.itertuples():
            if prefer_transit and int(row.transit_stops) > 0 and rem >= transit_cost:
                placements.append(InterventionPlacement(h3_index=row.h3_index, intervention_id="shaded_transit_stop"))
                rem -= transit_cost
            elif rem >= canopy_cost and float(catalog["street_canopy"]["neb_defaults"]["water_demand_score"]) <= req.max_water_demand:
                placements.append(InterventionPlacement(h3_index=row.h3_index, intervention_id="street_canopy"))
                rem -= canopy_cost
            elif rem >= park_cost and float(catalog["pocket_park"]["neb_defaults"]["water_demand_score"]) <= req.max_water_demand:
                placements.append(InterventionPlacement(h3_index=row.h3_index, intervention_id="pocket_park"))
                rem -= park_cost
            elif rem >= transit_cost:
                placements.append(InterventionPlacement(h3_index=row.h3_index, intervention_id="shaded_transit_stop"))
                rem -= transit_cost
            if rem < min(transit_cost, park_cost, canopy_cost):
                break
        return placements

    # 1. Pure Efficiency Baseline: highest population * baseline LST first
    scored["eff_score"] = scored["population_count"] * scored["lst_summer_c"]
    eff_placements = build_greedy(scored.sort_values("eff_score", ascending=False), prefer_transit=False)

    # 2. Community NEB Co-Design: blends HVI + citizen lived-experience feedback boosts + transit demand
    scored["citizen_boost"] = scored["h3_index"].map(lambda c: boosts.get(c, 0))
    scored["comm_score"] = scored["baseline_hvi"] * (1.0 + 0.35 * scored["citizen_boost"]) + 4.0 * scored["transit_stops"]
    comm_placements = build_greedy(scored.sort_values("comm_score", ascending=False), prefer_transit=True)

    # 3. Rawlsian Maximin Equity: spread low-cost, high-PET transit + park/canopy across every cell in V first
    v_first = scored.sort_values(["in_top_hvi_quintile_v", "baseline_hvi"], ascending=[False, False])
    rawls_placements = build_greedy(v_first, prefer_transit=True)

    specs: list[tuple[str, str, str, list[InterventionPlacement]]] = [
        (
            "pure_efficiency",
            "Pure Efficiency Baseline",
            "Maximizes aggregate population-weighted cooling per euro without equity or citizen-feedback constraints.",
            eff_placements,
        ),
        (
            "community_neb",
            "Community NEB Co-Design",
            "Incorporates resident lived-experience H3 tags, transit-stop shade priorities, and New European Bauhaus weights.",
            comm_placements,
        ),
        (
            "rawlsian_equity",
            "Rawlsian Maximin Priority (Top HVI Quintile V)",
            "Prioritizes reaching the maximum share of residents in the fixed top 20% baseline HVI quintile V under budget.",
            rawls_placements,
        ),
    ]

    v_cells = scored.loc[scored["in_top_hvi_quintile_v"] == True, "h3_index"].tolist()  # noqa: E712
    candidates: list[PortfolioCandidate] = []
    v_vectors: dict[str, list[float]] = {}
    neb_scores: dict[str, float] = {}

    for sid, label, desc, pl in specs:
        sim = simulate_scenario(
            SimulationRequest(
                city=req.city,
                budget_eur=req.budget_eur,
                placements=pl,
                neb_weights=req.neb_weights,
                cost_scenario=req.cost_scenario,
                cooling_scenario=req.cooling_scenario,
            )
        )
        air_map = {r.h3_index: r.delta_air_c for r in sim.cell_results}
        v_vectors[sid] = [air_map.get(c, 0.0) for c in v_cells]
        neb_scores[sid] = sim.neb_score
        candidates.append(
            PortfolioCandidate(strategy_id=sid, label=label, description=desc, placements=pl, simulation=sim)
        )

    ranked = rank_portfolios_rawlsian(v_vectors, neb_scores)
    return OptimizeResponse(city=req.city, candidates=candidates, rawlsian_ranked_order=ranked)