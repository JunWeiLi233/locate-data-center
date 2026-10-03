"""Phase 6 output rows kept separate from accepted model schemas."""

from __future__ import annotations

import json
import math
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


CaseCategory = Literal["baseline", "weights", "pue", "wue", "load", "carbon", "land", "water", "screening", "ablation"]


class SensitivityResultRow(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    schema_version: Literal["1.0.0"] = "1.0.0"
    evaluation_version: str = Field(min_length=1)
    freeze_id: str = Field(min_length=1)
    case_id: str = Field(min_length=1)
    case_category: CaseCategory
    grid_definition_id: str = Field(min_length=1)
    data_mode: Literal["real", "synthetic"]
    grid_id: str = Field(min_length=1)
    design_id: str = Field(min_length=1)
    baseline_scenario_id: str = Field(min_length=1)
    case_scenario_id: str = Field(min_length=1)
    baseline_profile_id: str = Field(min_length=1)
    case_profile_id: str = Field(min_length=1)
    base_eligible: bool
    case_eligible: bool
    eligibility_changed: bool
    base_rankable: bool
    case_rankable: bool
    base_hard_fail: bool
    case_hard_fail: bool
    base_critical_unknown: bool
    case_critical_unknown: bool
    base_conditional: bool
    case_conditional: bool
    base_rank: int | None = Field(default=None, ge=1)
    case_rank: int | None = Field(default=None, ge=1)
    rank_change: int | None = None
    base_score: float | None = Field(default=None, ge=0, le=100)
    case_score: float | None = Field(default=None, ge=0, le=100)
    score_change: float | None = None
    base_pareto: bool | None = None
    case_pareto: bool | None = None
    base_top_k: bool
    case_top_k: bool
    main_driver: str | None = None
    driver_abs_contribution_change: float | None = Field(default=None, ge=0)
    base_raw_metrics_json: str
    case_raw_metrics_json: str
    raw_metric_delta_json: str
    base_contributions_json: str
    case_contributions_json: str
    contribution_delta_json: str
    case_assumptions_json: str
    status: Literal["MATCHED_RANKED", "MATCHED_UNRANKED", "MATCHED_INELIGIBLE"]

    @field_validator(
        "base_raw_metrics_json", "case_raw_metrics_json", "raw_metric_delta_json",
        "base_contributions_json", "case_contributions_json", "contribution_delta_json",
        "case_assumptions_json",
    )
    @classmethod
    def finite_json(cls, value):
        def bad(_):
            raise ValueError("Nonfinite JSON constant")
        parsed = json.loads(value, parse_constant=bad)
        if not isinstance(parsed, dict):
            raise ValueError("Sensitivity JSON fields must be objects")
        return value

    @model_validator(mode="after")
    def invariants(self):
        if self.eligibility_changed != (self.base_eligible != self.case_eligible):
            raise ValueError("eligibility_changed disagrees with flags")
        if self.base_rankable != (self.base_rank is not None and self.base_score is not None):
            raise ValueError("Baseline rank/score must match rankable status")
        if self.case_rankable != (self.case_rank is not None and self.case_score is not None):
            raise ValueError("Case rank/score must match rankable status")
        if self.base_hard_fail and self.base_rankable or self.case_hard_fail and self.case_rankable:
            raise ValueError("Hard failures can never be rankable")
        for label, eligible, rankable, hard_fail, critical_unknown, conditional in (
            ("Baseline", self.base_eligible, self.base_rankable, self.base_hard_fail, self.base_critical_unknown, self.base_conditional),
            ("Case", self.case_eligible, self.case_rankable, self.case_hard_fail, self.case_critical_unknown, self.case_conditional),
        ):
            if rankable and (not eligible or hard_fail):
                raise ValueError(f"{label} rankable status contradicts eligibility")
            if hard_fail and eligible:
                raise ValueError(f"{label} hard failure cannot be eligible")
            if conditional and (not eligible or hard_fail or not critical_unknown):
                raise ValueError(f"{label} conditional status is inconsistent")
        if self.base_rank is None or self.case_rank is None:
            if self.rank_change is not None or self.score_change is not None:
                raise ValueError("Unranked comparisons cannot report rank/score changes")
        elif self.rank_change != self.case_rank - self.base_rank or not math.isclose(
            self.score_change, self.case_score - self.base_score, rel_tol=1e-10, abs_tol=1e-9
        ):
            raise ValueError("Rank/score changes disagree with endpoints")
        expected = "MATCHED_RANKED" if self.case_rankable else "MATCHED_INELIGIBLE" if not self.case_eligible else "MATCHED_UNRANKED"
        if self.status != expected:
            raise ValueError("Sensitivity status disagrees with eligibility/rankability")
        return self


class RobustnessSummaryRow(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    schema_version: Literal["1.0.0"] = "1.0.0"
    evaluation_version: str
    freeze_id: str
    case_id: str
    case_category: CaseCategory
    alternatives: int = Field(ge=0)
    eligible: int = Field(ge=0)
    rankable: int = Field(ge=0)
    conditional_ranked: int = Field(ge=0)
    hard_failures: int = Field(ge=0)
    eligibility_changes: int = Field(ge=0)
    top_k_requested: int = Field(gt=0)
    baseline_top_k_count: int = Field(ge=0)
    case_top_k_count: int = Field(ge=0)
    top_k_overlap_count: int = Field(ge=0)
    top_k_jaccard: float | None = Field(default=None, ge=0, le=1)
    rank_correlation: float | None = Field(default=None, ge=-1, le=1)
    mean_absolute_rank_change: float | None = Field(default=None, ge=0)
    maximum_absolute_rank_change: int | None = Field(default=None, ge=0)
    main_driver: str | None = None
    main_driver_mean_abs_contribution_change: float | None = Field(default=None, ge=0)
    weighting_method: str
    baseline_scenario_id: str
    case_scenario_id: str
    comparison_key_json: str

    @model_validator(mode="after")
    def counts(self):
        if any(v > self.alternatives for v in (self.eligible, self.rankable, self.conditional_ranked, self.hard_failures, self.eligibility_changes)):
            raise ValueError("Robustness counts exceed alternatives")
        return self


class FixedRegionSummaryRow(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    schema_version: Literal["1.0.0"] = "1.0.0"
    evaluation_version: str
    freeze_id: str
    case_id: str
    region_id: str
    design_id: str
    baseline_scenario_id: str
    case_scenario_id: str
    total_baseline_members: int = Field(gt=0)
    matched_members: int = Field(ge=0)
    eligible_members: int = Field(ge=0)
    rankable_members: int = Field(ge=0)
    unranked_members: int = Field(ge=0)
    case_rank_min: int | None = Field(default=None, ge=1)
    case_rank_max: int | None = Field(default=None, ge=1)
    case_rank_mean: float | None = Field(default=None, ge=1)
    case_rank_range_basis: Literal["ranked_members_only"] = "ranked_members_only"
    case_rank_mean_basis: Literal["all_members_only_or_null"] = "all_members_only_or_null"

    @model_validator(mode="after")
    def complete_membership(self):
        if self.matched_members != self.total_baseline_members:
            raise ValueError("Fixed-region comparison must retain every original member")
        if self.eligible_members > self.matched_members or self.rankable_members > self.eligible_members:
            raise ValueError("Fixed-region eligibility/rankability counts are inconsistent")
        if self.unranked_members != self.matched_members - self.rankable_members:
            raise ValueError("Fixed-region unranked count is inconsistent")
        if self.rankable_members == 0 and any(v is not None for v in (self.case_rank_min, self.case_rank_max, self.case_rank_mean)):
            raise ValueError("A region without ranked members cannot report rank statistics")
        if self.rankable_members > 0 and (self.case_rank_min is None or self.case_rank_max is None):
            raise ValueError("Ranked-member range is required when ranked members exist")
        if self.rankable_members != self.total_baseline_members and self.case_rank_mean is not None:
            raise ValueError("Full-region mean must be null when any baseline member is unranked")
        if self.rankable_members == self.total_baseline_members and self.case_rank_mean is None:
            raise ValueError("Full-region mean is required when every baseline member is ranked")
        return self


class AlternativeRankRangeRow(BaseModel):
    """Per-alternative stability summary across separately evaluated cases."""

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    schema_version: Literal["1.0.0"] = "1.0.0"
    evaluation_version: str = Field(min_length=1)
    freeze_id: str = Field(min_length=1)
    grid_id: str = Field(min_length=1)
    design_id: str = Field(min_length=1)
    baseline_scenario_id: str = Field(min_length=1)
    base_rank: int | None = Field(default=None, ge=1)
    evaluated_cases: int = Field(gt=0)
    ranked_cases: int = Field(ge=0)
    unranked_cases: int = Field(ge=0)
    minimum_rank: int | None = Field(default=None, ge=1)
    maximum_rank: int | None = Field(default=None, ge=1)
    rank_range: int | None = Field(default=None, ge=0)
    scope: str = Field(min_length=1)

    @model_validator(mode="after")
    def counts_and_range(self):
        if self.ranked_cases + self.unranked_cases != self.evaluated_cases:
            raise ValueError("Ranked and unranked case counts must cover every evaluated case")
        endpoints = (self.minimum_rank, self.maximum_rank, self.rank_range)
        if self.ranked_cases == 0:
            if any(value is not None for value in endpoints):
                raise ValueError("An alternative with no ranked cases cannot report a rank range")
        elif any(value is None for value in endpoints):
            raise ValueError("A ranked alternative requires minimum, maximum, and range")
        elif self.minimum_rank > self.maximum_rank or self.rank_range != self.maximum_rank - self.minimum_rank:
            raise ValueError("Alternative rank range disagrees with its endpoints")
        return self


__all__ = [
    "SensitivityResultRow", "RobustnessSummaryRow", "FixedRegionSummaryRow",
    "AlternativeRankRangeRow",
]
