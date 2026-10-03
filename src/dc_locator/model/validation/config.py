"""Strict Phase 6 validation policy and preregistered case definitions."""

from __future__ import annotations

import math
from numbers import Integral, Real
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


GROUP_IDS = {"energy_carbon", "water_stewardship", "grid_infrastructure", "land"}
SUPPORTED_WATER_YEARS = {2030, 2050, 2080}


def _positive_real(value, label):
    if isinstance(value, bool) or not isinstance(value, Real) or not math.isfinite(float(value)) or value <= 0:
        raise ValueError(f"{label} must be finite positive numeric input, not a boolean")
    return float(value)


def _strict_int(value, label):
    if isinstance(value, bool) or not isinstance(value, Integral):
        raise ValueError(f"{label} must be an explicit integer")
    return int(value)


class DescribedCase(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    case_id: str = Field(min_length=1)
    basis: str = Field(min_length=1)
    rationale: str = Field(min_length=1)


class BaselineCase(DescribedCase):
    pathway: Literal["bau", "opt", "pes"]
    milestone_year: int
    screening_mode: Literal["STRICT", "EXPLORATORY"]

    @field_validator("milestone_year", mode="before")
    @classmethod
    def typed_year(cls, value):
        return _strict_int(value, "Baseline milestone_year")

    @model_validator(mode="after")
    def supported_year(self):
        if self.milestone_year not in SUPPORTED_WATER_YEARS:
            raise ValueError("Baseline requires a supported native Aqueduct milestone")
        return self


class TopKPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")
    k: int = Field(gt=0)
    key: list[str]
    cross_context_comparison_key: list[str]
    scenario_policy: Literal["separate_each_external_context"]
    tie_policy: Literal["mcda_score_desc_then_grid_id_design_id_scenario_id_asc_exact_k"]

    @field_validator("k", mode="before")
    @classmethod
    def typed_k(cls, value):
        return _strict_int(value, "top_k.k")

    @model_validator(mode="after")
    def exact_key(self):
        if self.key != ["grid_id", "design_id", "scenario_id"]:
            raise ValueError("Top-k key and stable tie policy are part of the frozen contract")
        if self.cross_context_comparison_key != ["grid_id", "design_id"]:
            raise ValueError("Cross-context top-k correspondence must align grid/design without pooling scenarios")
        return self


class FixedRegionPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")
    membership_path: str
    join_key: list[str]
    policy: str = Field(min_length=1)

    @model_validator(mode="after")
    def exact_join(self):
        if self.join_key != ["grid_id", "design_id"]:
            raise ValueError("Fixed baseline membership must align grid/design across case scenarios")
        return self


class WeightCase(DescribedCase):
    group_weights: dict[str, float]

    @field_validator("group_weights", mode="before")
    @classmethod
    def typed_weights(cls, value):
        if not isinstance(value, dict) or set(value) != GROUP_IDS:
            raise ValueError("Weight cases must cover exactly the four accepted parent groups")
        cleaned = {str(k): _positive_real(v, "Group weight") for k, v in value.items()}
        if not math.isclose(sum(cleaned.values()), 1.0, abs_tol=1e-12):
            raise ValueError("Group weights must sum to one")
        return cleaned


class ScalarCase(DescribedCase):
    category: Literal["pue", "wue", "load", "carbon", "land"]
    multiplier: float

    @field_validator("multiplier", mode="before")
    @classmethod
    def typed_multiplier(cls, value):
        return _positive_real(value, "Sensitivity multiplier")


class WaterCase(BaseModel):
    model_config = ConfigDict(extra="forbid")
    case_id: str = Field(min_length=1)
    pathway: Literal["bau", "opt", "pes"]
    milestone_year: int
    profile: str

    @field_validator("milestone_year", mode="before")
    @classmethod
    def typed_year(cls, value):
        return _strict_int(value, "Water milestone_year")

    @model_validator(mode="after")
    def supported_profile(self):
        if self.milestone_year not in SUPPORTED_WATER_YEARS:
            raise ValueError("Only supported native Aqueduct milestones are sensitivity cases")
        if Path(self.profile).stem != f"{self.pathway}_{self.milestone_year}":
            raise ValueError("Water case/profile identity mismatch")
        return self


class ScreeningCase(DescribedCase):
    mode: Literal["STRICT", "EXPLORATORY"]


class AblationCase(BaseModel):
    model_config = ConfigDict(extra="forbid")
    case_id: str = Field(min_length=1)
    removed_group: Literal["energy_carbon", "water_stewardship", "grid_infrastructure", "land"]


class AblationPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")
    method: Literal["remove_group_then_equalize_remaining_parent_groups"]
    rationale: str = Field(min_length=1)


class HoldoutInputs(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    holdout_geography: str
    holdout_provenance: str
    fine_geography: str
    fine_provenance: str
    coarse_geography: str
    coarse_provenance: str
    common_footprint_epsg5070: list[float]
    expected_holdout_cells: int = Field(gt=0)
    expected_fine_cells: int = Field(gt=0)
    expected_coarse_cells: int = Field(gt=0)
    expected_common_square_union_km2: float
    minimum_baseline_separation_km: float

    @field_validator("expected_holdout_cells", "expected_fine_cells", "expected_coarse_cells", mode="before")
    @classmethod
    def typed_counts(cls, value):
        return _strict_int(value, "Expected cell count")

    @field_validator("expected_common_square_union_km2", "minimum_baseline_separation_km", mode="before")
    @classmethod
    def typed_positive_values(cls, value):
        return _positive_real(value, "Holdout policy value")

    @field_validator("common_footprint_epsg5070", mode="before")
    @classmethod
    def typed_bounds(cls, value):
        if not isinstance(value, list) or len(value) != 4:
            raise ValueError("Common footprint requires [minx,miny,maxx,maxy]")
        cleaned = []
        for item in value:
            if isinstance(item, bool) or not isinstance(item, Real) or not math.isfinite(float(item)):
                raise ValueError("Common footprint coordinates must be finite numeric values")
            cleaned.append(float(item))
        if cleaned[0] >= cleaned[2] or cleaned[1] >= cleaned[3]:
            raise ValueError("Common footprint bounds are inverted")
        return cleaned


class InactiveAnalysis(BaseModel):
    model_config = ConfigDict(extra="forbid")
    module_id: str = Field(min_length=1)
    status: Literal["INAPPLICABLE"]
    reason: str = Field(min_length=1)


class ExternalValidationPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal["UNAVAILABLE"]
    rationale: str = Field(min_length=1)


class Phase6Config(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal["1.0.0"]
    evaluation_version: str = Field(min_length=1)
    accepted_phase5_record: str
    preselection_manifest: str
    software_evidence: str
    inputs: dict[str, str]
    baseline: BaselineCase
    top_k: TopKPolicy
    fixed_region_policy: FixedRegionPolicy
    weight_cases: list[WeightCase]
    scalar_cases: list[ScalarCase]
    water_cases: list[WaterCase]
    screening_cases: list[ScreeningCase]
    ablation_cases: list[AblationCase]
    ablation_policy: AblationPolicy
    holdout: HoldoutInputs
    inactive_analyses: list[InactiveAnalysis]
    external_validation: ExternalValidationPolicy

    @model_validator(mode="after")
    def complete_preregistration(self):
        required_inputs = {
            "geography", "provenance", "facility", "cooling_designs", "physical_scenarios",
            "constraints", "phase5_profile_declaration", "baseline_profile",
            "baseline_ranked_cells", "baseline_region_membership",
        }
        if set(self.inputs) != required_inputs:
            raise ValueError("Phase6 inputs must exactly match the preregistered contract")
        cases = [self.baseline.case_id]
        cases += [c.case_id for c in self.weight_cases + self.scalar_cases + self.water_cases + self.screening_cases + self.ablation_cases]
        if len(cases) != len(set(cases)):
            raise ValueError("Phase6 case IDs must be globally unique")
        if {c.category for c in self.scalar_cases} != {"pue", "wue", "load", "carbon", "land"}:
            raise ValueError("PUE, WUE, load, carbon and land sensitivity categories are all required")
        removed_groups = [c.removed_group for c in self.ablation_cases]
        if len(removed_groups) != len(GROUP_IDS) or set(removed_groups) != GROUP_IDS:
            raise ValueError("Ablation must cover each accepted parent group exactly once")
        inactive = {c.module_id for c in self.inactive_analyses}
        if inactive != {"climate_to_cooling_response", "construction_lifecycle_sensitivity"}:
            raise ValueError("Unsupported climate/construction sensitivities must be explicitly inactive")
        if self.holdout.minimum_baseline_separation_km < 50:
            raise ValueError("Prospective holdout must be at least 50 km from the inspected baseline")
        return self


def load_phase6_config(path="configs/phase6.yaml") -> Phase6Config:
    target = Path(path)
    value = yaml.safe_load(target.read_text(encoding="utf-8"))
    return Phase6Config.model_validate(value)


__all__ = ["GROUP_IDS", "Phase6Config", "load_phase6_config"]
