"""Complete cooling alternatives and explicitly labeled external scenarios.

Constant annual assumptions do not model local climate or prove peak demand.
"""

import math
from numbers import Real
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
import yaml


def _numeric_input(value, label):
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, Real) or not math.isfinite(float(value)):
        raise ValueError(f"{label} must be finite numeric input, not a boolean")
    return float(value)


class CoolingDesign(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    design_id: str = Field(min_length=1)
    heat_transport: str = Field(min_length=1)
    heat_rejection: str = Field(min_length=1)
    annual_pue: float | None = Field(default=None, ge=1)
    wue_l_per_it_kwh: float | None = Field(default=None, ge=0)
    water_basis: Literal["consumption", "withdrawal"]
    peak_pue: float | None = Field(default=None, ge=1)
    peak_pue_verified: bool = False
    peak_pue_evidence: str | None = None
    basis: str = Field(min_length=1)
    rationale: str = Field(min_length=1)
    reference: str | None = None

    @field_validator("annual_pue", "wue_l_per_it_kwh", "peak_pue", mode="before")
    @classmethod
    def typed_numeric_fields(cls, value):
        return _numeric_input(value, "Cooling design coefficient")

    @model_validator(mode="after")
    def validate_peak_evidence(self):
        if self.peak_pue_verified and (self.peak_pue is None or not self.peak_pue_evidence):
            raise ValueError("Verified peak PUE needs a value and design-day evidence")
        return self


class PhysicalScenario(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    scenario_id: str = Field(min_length=1)
    carbon_data_year: str = Field(min_length=1)
    historical_static: bool
    grid_water_l_per_kwh: float | None = Field(default=None, ge=0)
    grid_water_basis: Literal["consumption", "withdrawal"] = "consumption"
    grid_water_geography: str | None = None
    basis: str = Field(min_length=1)
    rationale: str = Field(min_length=1)

    @field_validator("grid_water_l_per_kwh", mode="before")
    @classmethod
    def typed_grid_water(cls, value):
        return _numeric_input(value, "Grid-water coefficient")

    @model_validator(mode="after")
    def validate_water_geography(self):
        if self.grid_water_l_per_kwh is not None and not self.grid_water_geography:
            raise ValueError("Generation water factor requires generation geography/system boundary")
        return self


def load_cooling_designs(path: str | Path) -> list[CoolingDesign]:
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    designs = [CoolingDesign.model_validate(row) for row in data["cooling_designs"]]
    if not designs or len({d.design_id for d in designs}) != len(designs):
        raise ValueError("Cooling designs must be nonempty with unique design_id")
    return designs


def load_physical_scenarios(path: str | Path) -> list[PhysicalScenario]:
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    scenarios = [PhysicalScenario.model_validate(row) for row in data["scenarios"]]
    if not scenarios or len({s.scenario_id for s in scenarios}) != len(scenarios):
        raise ValueError("External scenarios must be nonempty with unique scenario_id")
    return scenarios


def validate_alternative_ids(designs, scenarios):
    if not designs or not scenarios:
        raise ValueError("Nonempty design and external scenario sets are required")
    if len({d.design_id for d in designs}) != len(designs) or len({s.scenario_id for s in scenarios}) != len(scenarios):
        raise ValueError("Duplicate design/scenario IDs")
