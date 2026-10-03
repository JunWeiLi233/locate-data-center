"""Loading and validation for `configs/*.yaml` (AGENTS.md section 5).

Every config file has a strict (`extra="forbid"`) pydantic model: an
unexpected key in a YAML file is a bug (typo, stale key after a rename), not
silently-ignored configuration. Grid and facility configurations are active.
Phase 3's model.cooling/model.screening additionally validate individual
design/scenario/constraint entries; scoring and broader future scenarios
remain later-phase contracts.
"""

from __future__ import annotations

import hashlib
import math
import warnings
from numbers import Integral, Real
from pathlib import Path
from typing import Optional

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from dc_locator.paths import configs_dir
from dc_locator.provenance import DataMode, ScreeningMode, SourceStatus


def _finite_real_input(value, label: str):
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, Real) or not math.isfinite(float(value)):
        raise ValueError(f"{label} must be finite numeric input, not a boolean")
    return float(value)


def _integer_input(value, label: str):
    if isinstance(value, bool) or not isinstance(value, Integral):
        raise ValueError(f"{label} must be explicit integer input, not a boolean")
    return int(value)


def grid_number_token(value: float) -> str:
    """Round-trip a finite coordinate without rounding away sub-metre detail.

    Whole-metre values keep the published v1 spelling (no trailing ``.0``).
    """
    number = float(value)
    if not math.isfinite(number):
        raise ValueError("Grid definition values must be finite.")
    return str(int(number)) if number.is_integer() else repr(number)


class ConfigValidationError(RuntimeError):
    """A configs/*.yaml file failed to parse or validate against its schema."""


def _load_yaml_mapping(path: Path) -> dict:
    if not path.is_file():
        raise FileNotFoundError(f"Config file not found: {path}")
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    if data is None:
        data = {}
    if not isinstance(data, dict):
        raise ConfigValidationError(f"{path}: expected a YAML mapping at the top level, got {type(data).__name__}.")
    return data


# --------------------------------------------------------------------------
# grid.yaml -- the only config Phase 1 fully exercises for grid generation.
# --------------------------------------------------------------------------


class StudyAreaBBox(BaseModel):
    """An EPSG:4326 bounding box used only to *select* cells of the already
    stable national grid (GRID CONTRACT); it never changes grid IDs or
    attributes of a retained cell.
    """

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    lon_min: float = Field(ge=-180.0, le=180.0)
    lat_min: float = Field(ge=-90.0, le=90.0)
    lon_max: float = Field(ge=-180.0, le=180.0)
    lat_max: float = Field(ge=-90.0, le=90.0)

    @field_validator("lon_min", "lat_min", "lon_max", "lat_max", mode="before")
    @classmethod
    def _typed_coordinates(cls, value):
        return _finite_real_input(value, "Study-area coordinate")

    @model_validator(mode="after")
    def _validate_order(self) -> "StudyAreaBBox":
        if self.lon_min >= self.lon_max:
            raise ValueError(f"lon_min ({self.lon_min}) must be < lon_max ({self.lon_max}).")
        if self.lat_min >= self.lat_max:
            raise ValueError(f"lat_min ({self.lat_min}) must be < lat_max ({self.lat_max}).")
        return self


class GridConfig(BaseModel):
    """`configs/grid.yaml`: the grid definition (GRID CONTRACT). All of
    `crs`/`origin_x_m`/`origin_y_m`/`cell_size_m`/`grid_scheme_version` are
    constants of the grid definition itself -- never derived from the
    study-area boundary. Changing any of them changes `grid_definition_id`
    and therefore every `grid_id`.
    """

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    crs: str
    origin_x_m: float
    origin_y_m: float
    cell_size_m: float = Field(gt=0.0)
    grid_scheme_version: int = Field(ge=1)
    id_row_col_digits: int = Field(ge=1, description="Zero-padded width of row/col in grid_id. Generation fails loudly if the actual CONUS extent needs more digits than this at the configured cell_size_m.")
    tile_size_cells: int = Field(gt=0)
    min_intersection_km2: float = Field(ge=0.0, description="Inclusion threshold: a cell is retained only if (cell square ∩ CONUS) area exceeds this. 0.0 = any positive intersection; edge/point touches are excluded regardless.")
    study_areas: dict[str, StudyAreaBBox]

    @field_validator("origin_x_m", "origin_y_m", "cell_size_m", "min_intersection_km2", mode="before")
    @classmethod
    def _typed_real_fields(cls, value):
        return _finite_real_input(value, "Grid numeric field")

    @field_validator("grid_scheme_version", "id_row_col_digits", "tile_size_cells", mode="before")
    @classmethod
    def _typed_integer_fields(cls, value):
        return _integer_input(value, "Grid integer field")

    @model_validator(mode="after")
    def _validate_crs_and_nesting(self) -> "GridConfig":
        if self.crs.upper() != "EPSG:5070":
            raise ValueError(f"grid.yaml crs must be 'EPSG:5070' (NAD83 / Conus Albers Equal Area); got {self.crs!r}.")
        ratio = 100_000.0 / self.cell_size_m
        if abs(ratio - round(ratio)) > 1e-6:
            warnings.warn(
                f"grid.yaml cell_size_m={self.cell_size_m} does not evenly divide 100000m: "
                "grids at different resolutions will not nest exactly (GRID CONTRACT).",
                stacklevel=2,
            )
        return self

    def grid_definition_id(self) -> str:
        """Deterministic, human-readable id encoding CRS, origin, cell size
        and grid-scheme version (GRID CONTRACT), e.g.
        'conus-epsg5070-ox-2500000-oy3400000-s10000m-v1'.
        """
        ox = grid_number_token(self.origin_x_m)
        oy = grid_number_token(self.origin_y_m)
        size = grid_number_token(self.cell_size_m)
        return f"conus-epsg5070-ox{ox}-oy{oy}-s{size}m-v{self.grid_scheme_version}"


def load_grid_config(path: Optional[Path] = None) -> GridConfig:
    target = path if path is not None else configs_dir() / "grid.yaml"
    data = _load_yaml_mapping(target)  # FileNotFoundError propagates as-is, not wrapped
    try:
        return GridConfig.model_validate(data)
    except Exception as exc:  # re-raise validation/parse failures with file context; never swallow
        raise ConfigValidationError(f"Failed to load/validate {target}: {exc}") from exc


# --------------------------------------------------------------------------
# sources.yaml -- Phase 2+ source registry. Phase 1 only registers the
# sources master_prompt.md already names, status NOT_IMPLEMENTED, with no
# fabricated URLs (AGENTS.md section 3.2: never fabricate a URL).
# --------------------------------------------------------------------------


class SourceRegistryEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    phase: int = Field(ge=1, le=7)
    status: SourceStatus
    url: Optional[str] = None
    notes: Optional[str] = None


class SourcesConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sources: list[SourceRegistryEntry] = Field(default_factory=list)


def load_sources_config(path: Optional[Path] = None) -> SourcesConfig:
    target = path if path is not None else configs_dir() / "sources.yaml"
    data = _load_yaml_mapping(target)
    try:
        return SourcesConfig.model_validate(data)
    except Exception as exc:
        raise ConfigValidationError(f"Failed to load/validate {target}: {exc}") from exc


# --------------------------------------------------------------------------
# facility.yaml -- explicit Phase 3 facility specification(s).
# --------------------------------------------------------------------------


class FacilityFileEntry(BaseModel):
    """One facility entry in `configs/facility.yaml`. `basis` /`rationale`
    label explicit assumption provenance (AGENTS.md section 3.2). Phase 3
    maps validated entries onto `dc_locator.schemas.FacilityConfig`1.1,
    preserving their basis/rationale in every model run.
    """

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    facility_id: str = Field(min_length=1)
    basis: str = Field(description="'project_assumption' or a citation key; see rationale.")
    rationale: Optional[str] = None
    peak_it_power_mw: float = Field(gt=0.0)
    average_it_load_factor: float = Field(ge=0.0, le=1.0)
    target_opening_year: int = Field(ge=2000, le=2100)
    operating_lifetime_years: int = Field(gt=0)
    cooling_design_id: Optional[str] = None
    notes: Optional[str] = None
    hours_in_modeled_year: Optional[float] = Field(default=None, gt=0, le=8784)
    minimum_land_area_km2: Optional[float] = Field(default=None, ge=0)
    cooling_designs: list[str] = Field(default_factory=list)
    screening_mode: ScreeningMode = ScreeningMode.STRICT

    @field_validator(
        "peak_it_power_mw", "average_it_load_factor", "hours_in_modeled_year",
        "minimum_land_area_km2", mode="before",
    )
    @classmethod
    def _typed_real_fields(cls, value):
        return _finite_real_input(value, "Facility numeric field")

    @field_validator("target_opening_year", "operating_lifetime_years", mode="before")
    @classmethod
    def _typed_integer_fields(cls, value):
        return _integer_input(value, "Facility integer field")


class FacilityFileConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    facilities: list[FacilityFileEntry] = Field(default_factory=list)


def load_facility_config(path: Optional[Path] = None) -> FacilityFileConfig:
    target = path if path is not None else configs_dir() / "facility.yaml"
    data = _load_yaml_mapping(target)
    try:
        return FacilityFileConfig.model_validate(data)
    except Exception as exc:
        raise ConfigValidationError(f"Failed to load/validate {target}: {exc}") from exc


# --------------------------------------------------------------------------
# cooling_designs.yaml / constraints.yaml / scoring.yaml / scenarios.yaml --
# Phase 3 model modules validate cooling/constraint entries. Scoring and
# broader future-scenario entries remain Phase 4/5 contracts.
# --------------------------------------------------------------------------


class CoolingDesignsConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cooling_designs: list[dict] = Field(default_factory=list, description="Envelope; model.cooling.CoolingDesign validates each complete design.")


class ConstraintsConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    screening_mode: ScreeningMode = ScreeningMode.STRICT
    requirements: list[dict] = Field(default_factory=list, description="Envelope; model.screening.Requirement validates each evidence-based constraint.")


class ScoringConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    metrics: list[dict] = Field(default_factory=list, description="Phase 4 metric registry: units, direction, normalization, thresholds, role, source requirements.")
    weighting_method: Optional[str] = Field(default=None, description="'equal' | 'user' | 'ahp' (Phase 4); null until chosen.")
    ahp_judgments: Optional[dict] = Field(default=None, description="Phase 4 pairwise comparison matrix input, if weighting_method == 'ahp'.")


class ScenariosConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scenarios: list[dict] = Field(default_factory=list, description="Phase 5 external scenarios (climate/grid/water futures), kept separate from cooling_designs.yaml decision alternatives.")


def _make_loader(model: type[BaseModel], filename: str):
    def _load(path: Optional[Path] = None):
        target = path if path is not None else configs_dir() / filename
        data = _load_yaml_mapping(target)
        try:
            return model.model_validate(data)
        except Exception as exc:
            raise ConfigValidationError(f"Failed to load/validate {target}: {exc}") from exc

    return _load


load_cooling_designs_config = _make_loader(CoolingDesignsConfig, "cooling_designs.yaml")
load_constraints_config = _make_loader(ConstraintsConfig, "constraints.yaml")
load_scoring_config = _make_loader(ScoringConfig, "scoring.yaml")
load_scenarios_config = _make_loader(ScenariosConfig, "scenarios.yaml")


# --------------------------------------------------------------------------
# run.yaml -- top-level run configuration (Phase 7 wires every phase
# together; Phase 1's `build-grid` CLI command already uses it).
# --------------------------------------------------------------------------


class RunConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_name: str = Field(min_length=1)
    data_mode: DataMode
    grid_config: str = Field(min_length=1, description="Path (relative to the project root) to the grid.yaml to use.")
    study_area: str = Field(min_length=1, description="'conus' for the national grid, or a key under grid.yaml:study_areas.")
    random_seed: Optional[int] = Field(default=None)


def load_run_config(path: Optional[Path] = None) -> RunConfig:
    target = path if path is not None else configs_dir() / "run.yaml"
    data = _load_yaml_mapping(target)
    try:
        if data.get('delivery_version'):
            from dc_locator.run_config import DeliveryConfig
            return DeliveryConfig.model_validate(data)
        return RunConfig.model_validate(data)
    except Exception as exc:
        raise ConfigValidationError(f"Failed to load/validate {target}: {exc}") from exc


# --------------------------------------------------------------------------
# Deterministic config-snapshot hash (GRID CONTRACT note; RunManifest).
# --------------------------------------------------------------------------


def config_snapshot_hash(paths: list[Path]) -> str:
    """sha256 over the concatenation of `b"<relative-name>\\0" + <file bytes>`
    for each path, in the given order -- a deterministic fingerprint of the
    exact config files a run used (AGENTS.md section 3.9 "record everything").
    Order matters and is the caller's responsibility (pass a fixed, documented
    order) so the hash is reproducible across runs and operating systems.
    """
    digest = hashlib.sha256()
    for path in paths:
        digest.update(path.name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(Path(path).read_bytes())
    return digest.hexdigest()


__all__ = [
    "ConfigValidationError",
    "StudyAreaBBox",
    "GridConfig",
    "load_grid_config",
    "SourceRegistryEntry",
    "SourcesConfig",
    "load_sources_config",
    "FacilityFileEntry",
    "FacilityFileConfig",
    "load_facility_config",
    "CoolingDesignsConfig",
    "ConstraintsConfig",
    "ScoringConfig",
    "ScenariosConfig",
    "load_cooling_designs_config",
    "load_constraints_config",
    "load_scoring_config",
    "load_scenarios_config",
    "RunConfig",
    "load_run_config",
    "config_snapshot_hash",
]
