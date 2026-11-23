"""Pydantic v2 contracts for CanopyCommons Phase 2 backend."""

from __future__ import annotations

from typing import Literal
from pydantic import BaseModel, Field, model_validator


CityKey = Literal["alexandria", "porto"]


class InterventionPlacement(BaseModel):
    h3_index: str
    intervention_id: str
    units: int = Field(default=1, ge=1, le=50)
    footprint_m2: float | None = Field(default=None, gt=0)
    exposed_time_share: float | None = Field(default=None, gt=0, le=1.0)


class NEBWeights(BaseModel):
    sustainable: float = Field(default=0.40, ge=0.0, le=1.0)
    beautiful: float = Field(default=0.30, ge=0.0, le=1.0)
    together: float = Field(default=0.30, ge=0.0, le=1.0)

    @model_validator(mode="after")
    def normalize_weights(self) -> "NEBWeights":
        total = self.sustainable + self.beautiful + self.together
        if total <= 0:
            raise ValueError("NEB weights must sum to a positive value.")
        self.sustainable = round(self.sustainable / total, 4)
        self.beautiful = round(self.beautiful / total, 4)
        self.together = round(1.0 - self.sustainable - self.beautiful, 4)
        return self


class SimulationRequest(BaseModel):
    city: CityKey
    budget_eur: float = Field(gt=0)
    placements: list[InterventionPlacement] = Field(default_factory=list)
    neb_weights: NEBWeights = Field(default_factory=NEBWeights)
    cost_scenario: Literal["low", "mid", "high"] = "mid"
    cooling_scenario: Literal["min", "mid", "max"] = "mid"


class WarmingWarning(BaseModel):
    h3_index: str
    intervention_id: str
    pedestrian_mrt_penalty_c: float
    affected_population: int
    note: str


class CellBenefitResult(BaseModel):
    h3_index: str
    treated_footprint_m2: float
    exposed_time_share: float
    delta_air_c: float
    delta_surface_c: float
    delta_pet_c: float
    capex_low_eur: float
    capex_high_eur: float
    capex_selected_eur: float
    mrt_penalty_c: float
    citations: list[str]


class EquityMetrics(BaseModel):
    mean_air_benefit_c: float
    mean_pet_benefit_c: float
    benefit_gini_air: float | None
    gini_disclosure: str
    rawlsian_min_v_air_c: float
    v_population_weighted_mean_c: float
    v_residents_reached_share: float


class SimulationResponse(BaseModel):
    city: CityKey
    total_capex_eur: float
    capex_range_eur: tuple[float, float]
    budget_remaining_eur: float
    within_budget: bool
    neb_score: float
    neb_pillars: dict[str, float]
    equity: EquityMetrics
    warming_warnings: list[WarmingWarning]
    unscored_population_share: float
    cell_results: list[CellBenefitResult]
    citations: list[str]
    latency_ms: float


class OptimizeRequest(BaseModel):
    city: CityKey
    budget_eur: float = Field(gt=0)
    neb_weights: NEBWeights = Field(default_factory=NEBWeights)
    cost_scenario: Literal["low", "mid", "high"] = "mid"
    cooling_scenario: Literal["min", "mid", "max"] = "mid"
    max_water_demand: float = Field(default=0.75, ge=0.0, le=1.0)


class PortfolioCandidate(BaseModel):
    strategy_id: str
    label: str
    description: str
    placements: list[InterventionPlacement]
    simulation: SimulationResponse


class OptimizeResponse(BaseModel):
    city: CityKey
    candidates: list[PortfolioCandidate]
    rawlsian_ranked_order: list[str]


class FeedbackSubmission(BaseModel):
    city: CityKey
    h3_index: str
    stratum: str = Field(min_length=2, max_length=60)
    persona_role: Literal["resident", "transit_rider", "ngo", "planner"] = "resident"
    priority_tag: str = Field(min_length=2, max_length=60)
    rationale_text: str = Field(min_length=5, max_length=600)
    points_sustainable: int = Field(ge=0, le=100)
    points_beautiful: int = Field(ge=0, le=100)
    points_together: int = Field(ge=0, le=100)

    @model_validator(mode="after")
    def validate_100_points(self) -> "FeedbackSubmission":
        if self.points_sustainable + self.points_beautiful + self.points_together != 100:
            raise ValueError("NEB participatory points must sum to exactly 100.")
        return self


class FeedbackRecord(FeedbackSubmission):
    feedback_id: int
    created_at: str


class DeliberationTheme(BaseModel):
    theme_title: str
    summary: str
    cited_feedback_ids: list[int]
    cited_h3_indices: list[str]
    suggested_neb_weights: NEBWeights | None = None


class DeliberationResponse(BaseModel):
    city: CityKey
    provider: str
    advisory_only: bool = True
    weights_mutated: bool = False
    themes: list[DeliberationTheme]
    stratified_citizen_weights: NEBWeights | None = None