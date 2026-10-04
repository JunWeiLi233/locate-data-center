"""Declared configuration for one rediscovery analysis (``configs/rediscovery.yaml``).

Every threshold is a declared project assumption with a rationale, fixed before the facility inventory is
compared. None of them is an engineering or regulatory fact. Changing the configuration creates a new
analysis identity, and that analysis must be written to a new output folder.
"""
from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class DeclaredValue(_Strict):
    basis: Literal["project_assumption", "published_source", "user_input"]
    rationale: str = Field(min_length=10)


class CandidateGeneration(_Strict):
    source: Literal["national_fine_surface"]
    model_run: str
    top_n_values: list[int]
    min_candidate_distance_km: float = Field(ge=0, le=500)
    separation: DeclaredValue
    design_selection: Literal["best_design_per_cell"]
    write_evaluated_cells: bool = True

    @field_validator("top_n_values")
    @classmethod
    def _sorted_unique(cls, values: list[int]) -> list[int]:
        if not values or any(value < 1 for value in values) or sorted(set(values)) != values:
            raise ValueError("top_n_values must be strictly increasing positive integers")
        if values[-1] > 2000:
            raise ValueError("At most 2000 candidates are supported by the presentation contract")
        return values


class FacilitySource(_Strict):
    source_id: Literal["im3_datacenter_atlas"]
    url: str
    path: str
    expected_bytes: int = Field(gt=0)
    expected_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    version: str
    doi: str
    license: str
    layers: list[Literal["point", "building", "campus"]]
    scope: Literal["conus"]


class Classification(_Strict):
    validated_max_km: float = Field(gt=0)
    emerging_min_km: float = Field(gt=0)
    declared: DeclaredValue

    @model_validator(mode="after")
    def _ordered(self):
        if self.emerging_min_km < self.validated_max_km:
            raise ValueError("emerging_min_km must be at least validated_max_km")
        return self


class Hubs(_Strict):
    linkage_km: float = Field(gt=0, le=100)
    min_facilities: int = Field(ge=2)
    declared: DeclaredValue


class Validation(_Strict):
    hit_radii_km: list[float]
    classification: Classification
    hubs: Hubs

    @field_validator("hit_radii_km")
    @classmethod
    def _radii(cls, values: list[float]) -> list[float]:
        if not values or any(value <= 0 for value in values) or sorted(set(values)) != values:
            raise ValueError("hit_radii_km must be strictly increasing positive distances")
        return values


class Control(_Strict):
    control_id: Literal["uniform_conus", "infrastructure_plausible"]
    label: str
    max_transmission_distance_km: float | None = Field(default=None, gt=0)
    min_suitable_land_frac: float | None = Field(default=None, ge=0, le=1)
    declared: DeclaredValue

    @model_validator(mode="after")
    def _filters(self):
        has_filters = self.max_transmission_distance_km is not None and self.min_suitable_land_frac is not None
        if self.control_id == "infrastructure_plausible" and not has_filters:
            raise ValueError("infrastructure_plausible needs both transmission and land thresholds")
        if self.control_id == "uniform_conus" and (self.max_transmission_distance_km is not None or self.min_suitable_land_frac is not None):
            raise ValueError("uniform_conus samples every valued cell and takes no filters")
        return self


class Baselines(_Strict):
    draws: int = Field(ge=20, le=10_000)
    seed: int = Field(ge=0)
    area_weighted: bool = True
    controls: list[Control]

    @field_validator("controls")
    @classmethod
    def _unique(cls, values: list[Control]) -> list[Control]:
        ids = [value.control_id for value in values]
        if not ids or len(ids) != len(set(ids)):
            raise ValueError("Baseline controls must be nonempty and unique")
        return values


class RobustnessProviderConfig(_Strict):
    kind: Literal["county_monte_carlo", "table"]
    path: str | None = None
    label: str


class Robustness(_Strict):
    providers: list[RobustnessProviderConfig]
    declared_weight_cases: Literal["from_model_run", "none"]


class Places(_Strict):
    county_boundaries: str
    county_boundaries_manifest: str
    nearest_county_max_km: float = Field(ge=0, le=25)


class Explanation(_Strict):
    strong_normalized_min: float = Field(ge=0, le=100)
    weak_normalized_max: float = Field(ge=0, le=100)
    declared: DeclaredValue

    @model_validator(mode="after")
    def _ordered(self):
        if self.weak_normalized_max >= self.strong_normalized_min:
            raise ValueError("weak_normalized_max must be below strong_normalized_min")
        return self


class SurfaceImage(_Strict):
    enabled: bool = True
    width_px: int = Field(ge=200, le=4000)


class TieSensitivity(_Strict):
    permutations: int = Field(ge=0, le=2000)
    seed: int = Field(ge=0)


class RediscoveryConfig(_Strict):
    schema_version: Literal["1.0.0"]
    analysis_name: str = Field(pattern=r"^[a-z0-9_]{3,64}$")
    data_mode: Literal["real", "synthetic"]
    candidate_generation: CandidateGeneration
    facilities: FacilitySource
    validation: Validation
    baselines: Baselines
    robustness: Robustness
    places: Places
    explanation: Explanation
    surface_image: SurfaceImage
    tie_sensitivity: TieSensitivity


def load_config(path: str | Path) -> RediscoveryConfig:
    return RediscoveryConfig.model_validate(yaml.safe_load(Path(path).read_text(encoding="utf-8")))
