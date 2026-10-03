"""Versioned shared data contracts (AGENTS.md section 6; phase1.md.txt step 3).

The initial eight contracts are extended by Phase 2 provenance and Phase 3
screening/performance/eligibility contracts. Field names, types, explicit
units, keys and semver `schema_version` values are described in
`docs/data_contracts.md`; Phase4 extends the decision/region contracts additively.

Design notes:

- Every model is `extra="forbid"`: an unexpected field is a bug (a typo'd
  column name, a stale writer), not silently accepted data.
- Units are explicit in field names (`_km2`, `_m`, `_mwh`, `_frac`, `_kg`, ...)
  per AGENTS.md section 6, never bare numbers with an implied unit.
- `schema_version` follows semver; a breaking field change bumps the major
  version and must be recorded as a migration note in
  `docs/data_contracts.md` (AGENTS.md section 9).
- This module imports from `dc_locator.provenance`, never the reverse
  (see `provenance.py`'s own module docstring).
"""

from __future__ import annotations

from datetime import datetime
from numbers import Integral, Real
from typing import Optional
from typing import Literal
import json
import math

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from dc_locator.provenance import (
    AHPStatus,
    DataMode,
    ProvenanceRecord,
    ScreeningMode,
    ScreeningOutcome,
    ValueStatus,
    Confidence,
    ensure_utc_datetime,
)


def _frac_field(description: str, default: "float | None" = None, required: bool = True) -> Field:  # type: ignore[valid-type]
    kwargs = dict(ge=0.0, le=1.0, description=description)
    if not required:
        kwargs["default"] = default
    return Field(**kwargs)  # type: ignore[arg-type]


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


# --------------------------------------------------------------------------
# 1. GridCell -- geography/grid.py output; see docs/data_contracts.md and the
#    GRID CONTRACT for the authoritative definition of every field.
# --------------------------------------------------------------------------


class GridCell(BaseModel):
    """One cell of the national (or a development-area subset of the)
    regular grid defined by `configs/grid.yaml`.

    Primary key: `grid_id`. `geometry` is always the *full* cell square
    (never clipped to the study area) in EPSG:5070; `study_area_intersection_km2`
    / `study_area_frac` separately capture how much of that square actually
    falls inside the CONUS administrative boundary, including mapped water.
    These are not land-only or developable-land areas. A development-area grid
    selects a subset of national rows and must not alter any attribute of a
    retained cell (see `geography/grid.py::select_development_area`).

    `geometry` is validated here as a shapely `Polygon` for single-row use
    (construction, unit tests); bulk reads/writes of `us_grid*.parquet` go
    through GeoPandas/pyogrio directly (`dc_locator.io`), not row-by-row
    through this model.
    """

    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)

    schema_version: str = Field(default="1.1.0", description="Semver of the GridCell schema.")

    # Identity
    grid_id: str = Field(min_length=1, description="Primary key within one grid definition. Published fixed-origin v1 IDs retain their spelling; other origins/schemes include grid_definition_id.")
    grid_definition_id: str = Field(min_length=1, description="Deterministic id of the grid definition (CRS + origin + cell size + scheme version) this cell belongs to.")
    row: int = Field(ge=0, description="Row index from the fixed national origin (top-left). Stored as int32 in Parquet.")
    col: int = Field(ge=0, description="Column index from the fixed national origin (top-left). Stored as int32 in Parquet.")
    tile_id: str = Field(min_length=1, description="Coarser (row // tile_size_cells, col // tile_size_cells) grouping for resumable tile-based processing in later phases.")

    # Geometry (EPSG:5070 unless noted)
    geometry: object = Field(description="Full cell square, shapely Polygon, EPSG:5070.")

    # Areas (km2, EPSG:5070 equal-area -- never computed from degrees)
    cell_area_km2: float = Field(gt=0.0, description="Full square's area in km2; constant for a given grid_definition_id (cell_size_m/1000)**2.")
    study_area_intersection_km2: float = Field(ge=0.0, description="Area of (cell square ∩ CONUS study-area boundary) in km2.")
    study_area_frac: float = Field(ge=0.0, le=1.0 + 1e-9, description="study_area_intersection_km2 / cell_area_km2; 1e-9 numerical tolerance, without altering measured areas.")
    is_boundary_cell: bool = Field(description="True when study_area_frac < 1 - 1e-9, i.e. the study-area boundary cuts through this cell.")

    # Centroids / representative point
    centroid_x_m: float = Field(description="X of the full cell's centroid, EPSG:5070 metres.")
    centroid_y_m: float = Field(description="Y of the full cell's centroid, EPSG:5070 metres.")
    centroid_lat: float = Field(ge=-90.0, le=90.0, description="Latitude of the full cell's centroid, EPSG:4326.")
    centroid_lon: float = Field(ge=-180.0, le=180.0, description="Longitude of the full cell's centroid, EPSG:4326.")
    rep_point_lat: float = Field(ge=-90.0, le=90.0, description="Latitude of a point guaranteed inside (cell ∩ CONUS), EPSG:4326.")
    rep_point_lon: float = Field(ge=-180.0, le=180.0, description="Longitude of a point guaranteed inside (cell ∩ CONUS), EPSG:4326.")

    # State attribution (by largest intersection area with the cell's CONUS-intersection area; ties -> lowest FIPS)
    state_fips_primary: str = Field(min_length=2, max_length=2, description="2-digit FIPS of the state with the largest share of this cell's CONUS intersection.")
    state_abbr_primary: str = Field(min_length=2, max_length=2, description="USPS abbreviation of state_fips_primary.")
    state_share_primary_frac: float = Field(ge=0.0, le=1.0 + 1e-9, description="Fraction of this cell's CONUS-intersection area inside state_fips_primary (1e-9 numerical tolerance).")
    state_fips_all: str = Field(min_length=2, description="';'-joined, sorted, all state FIPS codes intersecting this cell.")
    n_states: int = Field(ge=1, description="Number of distinct states intersecting this cell.")

    # County attribution (same rule as state; nullable because a small number of
    # coastal/boundary cells can fall inside a state's CONUS intersection but
    # outside every county polygon, due to coastline generalization differences
    # between the state and county cartographic boundary files -- see
    # docs/limitations.md rather than silently fabricating a county).
    county_geoid_primary: Optional[str] = Field(default=None, min_length=5, max_length=5, description="5-char state+county FIPS (GEOID) with the largest share, or null for a state/county coastline-generalization mismatch (n_counties=0).")
    county_name_primary: Optional[str] = Field(default=None, description="Name of county_geoid_primary, or null.")
    county_share_primary_frac: Optional[float] = Field(default=None, ge=0.0, le=1.0 + 1e-9, description="Fraction of this cell's CONUS-intersection area inside county_geoid_primary, or null (1e-9 numerical tolerance).")
    county_geoid_all: Optional[str] = Field(default=None, description="';'-joined, sorted, all county GEOIDs intersecting this cell, or null.")
    n_counties: int = Field(ge=0, description="Number of distinct counties intersecting this cell (0 only for the rare coastline-mismatch case above).")

    data_mode: DataMode = Field(description="Always DataMode.REAL for data/processed/ outputs; DataMode.SYNTHETIC only in tests/fixtures/.")

    @field_validator("geometry")
    @classmethod
    def _validate_geometry_is_polygon(cls, value: object) -> object:
        from shapely.geometry.base import BaseGeometry

        if not isinstance(value, BaseGeometry) or value.geom_type != "Polygon":
            raise ValueError(f"GridCell.geometry must be a shapely Polygon, got {type(value).__name__}/{getattr(value, 'geom_type', None)!r}.")
        if not value.is_valid:
            raise ValueError("GridCell.geometry must be a valid Polygon (shapely .is_valid is False).")
        return value

    @model_validator(mode="after")
    def _validate_areas_and_counties(self) -> "GridCell":
        if self.study_area_intersection_km2 > self.cell_area_km2 * (1 + 1e-6):
            raise ValueError(
                f"GridCell {self.grid_id!r}: study_area_intersection_km2 ({self.study_area_intersection_km2}) "
                f"exceeds cell_area_km2 ({self.cell_area_km2})."
            )
        has_county = self.county_geoid_primary is not None
        if has_county != (self.n_counties >= 1):
            raise ValueError(
                f"GridCell {self.grid_id!r}: county_geoid_primary presence ({has_county}) is inconsistent "
                f"with n_counties ({self.n_counties})."
            )
        return self


# --------------------------------------------------------------------------
# 2. FeatureMetadata -- the versioned schema for feature_provenance.parquet
#    (Phase 2+). `provenance.py::ProvenanceRecord` is the per-row validation
#    model; FeatureMetadata is that same row shape plus the schema_version
#    this module adds to every contract, so provenance.py can stay free of
#    a dependency on this module (see provenance.py's own docstring).
# --------------------------------------------------------------------------


class FeatureMetadata(ProvenanceRecord):
    """Versioned wrapper around `ProvenanceRecord`: the authoritative schema
    for one row of `feature_provenance.parquet` (one row per `grid_id x
    metric`). Introduced in Phase 1 as a structural contract; populated
    starting Phase 2 once source adapters exist.
    """

    schema_version: str = Field(default="1.1.0", description="Semver of the FeatureMetadata schema.")


# --------------------------------------------------------------------------
# 3. FacilityConfig -- Phase 3 input, loaded from configs/facility.yaml.
# --------------------------------------------------------------------------


class FacilityConfig(BaseModel):
    """A data-center facility specification used to drive Phase 3 screening
    and physical calculations (master_prompt.md Phase 3), with explicit
    annual evaluation period and regional/parcel land requirements.
    """

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    schema_version: str = Field(default="1.1.0", description="Semver of the FacilityConfig schema.")

    facility_id: str = Field(min_length=1, description="Primary key / identifier for this facility specification, e.g. 'default'.")
    peak_it_power_mw: float = Field(gt=0.0, description="Peak IT (compute) power draw, megawatts.")
    average_it_load_factor: float = Field(ge=0.0, le=1.0, description="Average IT load as a fraction of peak_it_power_mw (0-1), including zero-load tests.")
    target_opening_year: int = Field(ge=2000, le=2100, description="Planned year of operational start.")
    operating_lifetime_years: int = Field(gt=0, description="Assumed operating lifetime, years.")
    cooling_design_id: Optional[str] = Field(default=None, description="Foreign key into configs/cooling_designs.yaml (Phase 3); null until a design is selected.")
    notes: Optional[str] = Field(default=None, description="Free-text rationale or caveats for this specification.")
    hours_in_modeled_year: Optional[float] = Field(default=None, gt=0, le=8784)
    minimum_land_area_km2: Optional[float] = Field(default=None, ge=0)
    cooling_designs: list[str] = Field(default_factory=list)
    screening_mode: ScreeningMode = ScreeningMode.STRICT
    basis: Optional[str] = None
    rationale: Optional[str] = None

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


# --------------------------------------------------------------------------
# 4. ScreeningResult -- Phase 3 output.
# --------------------------------------------------------------------------


class ScreeningResult(BaseModel):
    """One PASS/FAIL/UNKNOWN evaluation of one requirement for one
    (grid_id, design_id, scenario_id) alternative (Phase 3; AGENTS.md
    section 6 "Status enums"). UNKNOWN is a distinct outcome and is never
    silently folded into PASS or FAIL (AGENTS.md section 3.3).
    """

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    schema_version: str = Field(default="1.1.0", description="Semver of the ScreeningResult schema.")

    grid_id: str = Field(min_length=1, description="Foreign key to GridCell.grid_id.")
    design_id: str = Field(min_length=1, description="Foreign key to a cooling design in configs/cooling_designs.yaml.")
    scenario_id: str = Field(min_length=1, description="Foreign key to an external scenario in configs/scenarios.yaml.")
    requirement: str = Field(min_length=1, description="Name of the screened requirement/constraint, e.g. 'min_transmission_proximity_km'.")
    outcome: ScreeningOutcome = Field(description="PASS | FAIL | UNKNOWN for this requirement.")
    mode: ScreeningMode = Field(description="STRICT | EXPLORATORY -- how an UNKNOWN critical requirement was handled.")
    value: Optional[float] = Field(default=None, description="Observed/calculated value driving this outcome, in `unit`; null if UNKNOWN.")
    unit: Optional[str] = Field(default=None, description="Explicit unit of `value`, e.g. 'km', 'frac'; null if value is null.")
    threshold: Optional[float] = Field(default=None, description="Threshold the value was compared against, same unit as `value`.")
    is_critical: bool = Field(default=True, description="Whether failing/unknown on this requirement alone can reject the alternative (AGENTS.md section 3.7, hard failures are never compensated by other scores).")
    missing_reason: Optional[str] = Field(default=None, description="Required when outcome is UNKNOWN; mirrors dc_locator.provenance.MissingReason values.")
    grid_definition_id: Optional[str] = None
    facility_id: Optional[str] = None
    metric: Optional[str] = None
    reason: Optional[str] = None
    evidence_json: Optional[str] = None
    source_status: Optional[str] = None
    confidence: Optional[str] = None
    coverage_frac: Optional[float] = Field(default=None, ge=0, le=1)
    basis: Optional[str] = None
    rationale: Optional[str] = None
    data_mode: Optional[DataMode] = None

    @model_validator(mode="after")
    def validate_outcome_evidence(self):
        if self.outcome == ScreeningOutcome.UNKNOWN:
            if not self.missing_reason or self.value is not None:
                raise ValueError("UNKNOWN requires null value and a missing_reason")
        elif self.value is None or self.missing_reason is not None:
            raise ValueError("PASS/FAIL require evidence value and no missing_reason")
        return self


class ScreeningEligibility(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: str = "1.0.0"
    grid_id: str
    grid_definition_id: str
    facility_id: str
    design_id: str
    scenario_id: str
    mode: ScreeningMode
    hard_fail: bool
    critical_unknown: bool
    eligible: bool
    conditional: bool
    data_mode: DataMode

    @model_validator(mode="after")
    def validate_eligibility(self):
        expected = not self.hard_fail and (self.mode == ScreeningMode.EXPLORATORY or not self.critical_unknown)
        conditional = expected and self.critical_unknown and self.mode == ScreeningMode.EXPLORATORY
        if self.eligible != expected or self.conditional != conditional:
            raise ValueError("Eligibility cannot compensate a hard FAIL or hide a critical UNKNOWN")
        return self


# --------------------------------------------------------------------------
# 5. SitePerformance -- Phase 3 output (physical calculations).
# --------------------------------------------------------------------------


class SitePerformance(BaseModel):
    """One physical-performance record for one (grid_id, design_id,
    scenario_id) alternative (master_prompt.md Phase 3): E_IT, E_facility,
    electricity-related carbon, and site water use. Site water and
    electricity-related water are kept separate per AGENTS.md section 6.
    Formulas are evaluated in model.physics; scenario/source/calculation
    metadata accompanies every important metric.
    """

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    schema_version: str = Field(default="1.1.0", description="Semver of the SitePerformance schema.")

    grid_id: str = Field(min_length=1, description="Foreign key to GridCell.grid_id.")
    design_id: str = Field(min_length=1, description="Foreign key to a cooling design in configs/cooling_designs.yaml.")
    scenario_id: str = Field(min_length=1, description="Foreign key to an external scenario in configs/scenarios.yaml.")

    pue: Optional[float] = Field(default=None, ge=1.0, description="Annual power usage effectiveness (dimensionless, scenario/design value); not verified peak PUE.")
    wue_l_per_kwh: Optional[float] = Field(default=None, ge=0.0, description="Water usage effectiveness, litres per kWh of IT energy (scenario/design value).")

    e_it_mwh: Optional[float] = Field(default=None, ge=0.0, description="IT energy over the evaluation period, MWh. E_IT = P_peak_mw * load_factor * hours.")
    e_facility_mwh: Optional[float] = Field(default=None, ge=0.0, description="Total facility energy, MWh. E_facility = E_IT * PUE.")
    grid_carbon_intensity_kg_per_mwh: Optional[float] = Field(default=None, ge=0.0, description="Observed/scenario grid carbon intensity at this cell, kg CO2e per MWh.")
    c_electricity_kg: Optional[float] = Field(default=None, ge=0.0, description="Electricity-related carbon emissions, kg CO2e. C_electricity = E_facility * grid_carbon_intensity.")
    w_site_m3: Optional[float] = Field(default=None, ge=0.0, description="Direct site water consumption, cubic metres. W_site = E_IT * WUE, unit-converted.")
    w_electricity_m3: Optional[float] = Field(default=None, ge=0.0, description="Electricity-related (off-site, power-generation) water consumption, cubic metres -- kept separate from w_site_m3.")
    grid_definition_id: Optional[str] = None
    facility_id: Optional[str] = None
    c_electricity_tonnes: Optional[float] = Field(default=None, ge=0)
    w_site_liters: Optional[float] = Field(default=None, ge=0)
    w_electricity_liters: Optional[float] = Field(default=None, ge=0)
    w_site_withdrawal_m3: Optional[float] = Field(default=None, ge=0)
    w_site_withdrawal_liters: Optional[float] = Field(default=None, ge=0)
    w_electricity_withdrawal_m3: Optional[float] = Field(default=None, ge=0)
    w_electricity_withdrawal_liters: Optional[float] = Field(default=None, ge=0)
    peak_facility_demand_mw: Optional[float] = Field(default=None, ge=0)
    target_opening_year: Optional[int] = None
    operating_lifetime_years: Optional[int] = None
    hours_in_modeled_year: Optional[float] = None
    metric_metadata_json: Optional[str] = None
    assumptions_json: Optional[str] = None
    warnings_json: Optional[str] = None
    data_mode: Optional[DataMode] = None


# --------------------------------------------------------------------------
# 6. DecisionResult -- Phase 4 output (Pareto / AHP / MCDA).
# --------------------------------------------------------------------------


class DecisionResult(BaseModel):
    """One decision-analysis record for one (grid_id, design_id,
    scenario_id) alternative (master_prompt.md Phase 4). Structural
    contract extended in Phase4 with profile identity and rankability invariants.
    """

    model_config = ConfigDict(extra="forbid")

    schema_version: str = Field(default="1.1.0", description="Semver of the DecisionResult schema.")

    grid_id: str = Field(min_length=1, description="Foreign key to GridCell.grid_id.")
    design_id: str = Field(min_length=1, description="Foreign key to a cooling design in configs/cooling_designs.yaml.")
    scenario_id: str = Field(min_length=1, description="Foreign key to an external scenario in configs/scenarios.yaml.")

    hard_fail: bool = Field(description="True if any critical ScreeningResult failed; a hard failure cannot be compensated by other scores (AGENTS.md section 3.7).")
    is_pareto_optimal: Optional[bool] = Field(default=None, description="Whether this alternative is non-dominated; null until Pareto analysis runs. Dominated alternatives are kept, never deleted.")
    pareto_rank: Optional[int] = Field(default=None, ge=0, description="Pareto front index (0 = non-dominated front), or null.")
    ahp_status: Optional[AHPStatus] = Field(default=None, description="Consistency status of the AHP weights used, if any.")
    mcda_score: Optional[float] = Field(default=None, description="Score(s) = sum_j w_j * N_j(s); null until computed.")
    contribution_by_metric: Optional[dict[str, float]] = Field(default=None, description="Per-metric contribution to mcda_score, keyed by metric name (exported so no contribution is hidden).")
    weights_used: Optional[dict[str, float]] = Field(default=None, description="Per-metric weight actually applied, keyed by metric name.")
    grid_definition_id: Optional[str] = None
    profile_id: Optional[str] = None
    profile_fingerprint: Optional[str] = None
    data_mode: Optional[DataMode] = None
    eligible: Optional[bool] = None
    conditional: Optional[bool] = None
    critical_unknown: Optional[bool] = None
    mode: Optional[ScreeningMode] = None
    rankable: Optional[bool] = None
    rank_status: Optional[str] = None
    unranked_reason: Optional[str] = None
    mcda_rank: Optional[int] = Field(default=None,ge=1)

    @model_validator(mode="after")
    def _validate_decision_eligibility(self):
        if self.mcda_score is not None and (self.hard_fail or self.eligible is False or self.rankable is False):
            raise ValueError("Ineligible/hard-failed/unrankable alternatives cannot have scores")
        if self.mode == ScreeningMode.STRICT and self.critical_unknown and self.mcda_score is not None:
            raise ValueError("STRICT critical UNKNOWN cannot rank")
        return self


# --------------------------------------------------------------------------
# 7. CandidateRegion -- Phase 4 output (spatial clustering).
# --------------------------------------------------------------------------


class CandidateRegion(BaseModel):
    """A cluster of adjacent, high-performing grid cells (master_prompt.md
    Phase 4). A region's geometry is a search area, never an approved
    construction site (AGENTS.md section 1 / section 8 interpretation
    language). Phase4 stores an actual evaluated representative and member distributions.
    """

    model_config = ConfigDict(extra="forbid")

    schema_version: str = Field(default="1.1.0", description="Semver of the CandidateRegion schema.")

    region_id: str = Field(min_length=1, description="Primary key, deterministic from design_id/scenario_id + member cells.")
    design_id: str = Field(min_length=1, description="Foreign key to a cooling design in configs/cooling_designs.yaml.")
    scenario_id: str = Field(min_length=1, description="Foreign key to an external scenario in configs/scenarios.yaml.")
    member_grid_ids: list[str] = Field(min_length=1, description="GridCell.grid_id members of this region; adjacent cells only, never merged across distant cells.")
    n_cells: int = Field(gt=0, description="len(member_grid_ids), stored for convenient filtering without exploding the list column.")
    total_area_km2: float = Field(gt=0.0, description="Sum of member cells' study_area_intersection_km2.")
    centroid_lat: float = Field(ge=-90.0, le=90.0, description="Latitude of the region's member-cell centroid, EPSG:4326. A search-area centroid, not an approved site.")
    centroid_lon: float = Field(ge=-180.0, le=180.0, description="Longitude of the region's member-cell centroid, EPSG:4326.")
    mean_mcda_score: Optional[float] = Field(default=None, description="Mean DecisionResult.mcda_score across member cells, or null until computed.")
    grid_definition_id: Optional[str] = None
    profile_id: Optional[str] = None
    profile_fingerprint: Optional[str] = None
    suitable_land_area_km2: Optional[float] = Field(default=None,ge=0)
    representative_grid_id: Optional[str] = None
    representative_json: Optional[str] = None
    metric_distributions_json: Optional[str] = None
    conditional: Optional[bool] = None
    critical_unknown: Optional[bool] = None
    interpretation: Optional[str] = None

    @field_validator("member_grid_ids")
    @classmethod
    def _validate_unique_members(cls, value: list[str]) -> list[str]:
        if len(set(value)) != len(value):
            raise ValueError("CandidateRegion.member_grid_ids must not contain duplicates.")
        return value

    @model_validator(mode="after")
    def _validate_n_cells(self) -> "CandidateRegion":
        if self.n_cells != len(self.member_grid_ids):
            raise ValueError(f"CandidateRegion {self.region_id!r}: n_cells ({self.n_cells}) != len(member_grid_ids) ({len(self.member_grid_ids)}).")
        if self.representative_grid_id is not None and self.representative_grid_id not in self.member_grid_ids:
            raise ValueError("Region representative must be a member evaluated cell")
        return self


# --------------------------------------------------------------------------
# 8. RunManifest -- Phase 7 output, but defined now so every phase can record
#    a run from the start (AGENTS.md section 3.9 "Record everything").
# --------------------------------------------------------------------------


class RunManifest(BaseModel):
    """Metadata for one end-to-end (or partial) pipeline run: identity,
    code/environment/config provenance, and anything that went wrong.
    Written to `runs/<run_name>/run_metadata.json`.
    """

    model_config = ConfigDict(extra="forbid")

    schema_version: str = Field(default="1.0.0", description="Semver of the RunManifest schema.")

    run_id: str = Field(min_length=1, description="Primary key, e.g. '<run_name>-<created_at>'.")
    created_at: datetime = Field(description="UTC timestamp the run started.")
    code_revision: Optional[str] = Field(default=None, description="Git commit SHA the run executed against, or null if unavailable (e.g. uncommitted working tree).")
    config_snapshot_hash: str = Field(min_length=1, description="sha256 of the concatenated, canonicalized configs/*.yaml used for this run (deterministic config fingerprint).")
    grid_definition_id: str = Field(min_length=1, description="Foreign key to the grid definition used.")
    grid_resolution_m: float = Field(gt=0.0, description="cell_size_m of grid_definition_id, metres.")
    dataset_versions: dict[str, str] = Field(default_factory=dict, description="source_id -> version/vintage string for every dataset the run touched.")
    source_coverage: Optional[dict[str, str]] = Field(default=None, description="source_id -> SourceStatus string (READY/PARTIAL/BLOCKED/NOT_IMPLEMENTED).")
    random_seed: Optional[int] = Field(default=None, description="Fixed seed for any stochastic step (e.g. Monte Carlo, Phase 6); null if the run used none.")
    data_mode: DataMode = Field(description="REAL for an actual run; SYNTHETIC for a fixture-driven test run.")
    warnings: list[str] = Field(default_factory=list, description="Non-fatal issues encountered during the run.")
    blockers: list[str] = Field(default_factory=list, description="Fatal or scope-limiting issues encountered during the run.")

    @field_validator("created_at")
    @classmethod
    def _validate_created_at(cls, value: datetime) -> datetime:
        return ensure_utc_datetime(value)


class FutureScenarioValue(BaseModel):
    """One explicit operating year or native source window; never interpolated."""
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
    schema_version: str = '1.0.0'
    grid_id: str = Field(min_length=1)
    grid_definition_id: str = Field(min_length=1)
    facility_id: str = Field(min_length=1)
    design_id: str = Field(min_length=1)
    scenario_id: str = Field(min_length=1)
    model: str = Field(min_length=1)
    period_kind: Literal['annual_operating', 'source_projection_window', 'unsupported_requested_period']
    period_start_year: int | None = None
    period_end_year: int | None = None
    milestone_year: int | None = None
    ssp_rcp: str | None = None
    variable: str = Field(min_length=1)
    value: float | None = None
    value_text: str | None = None
    unit: str | None = None
    source_id: str | None = None
    source_year: str | None = None
    source_json: str
    assumptions_json: str
    status: ValueStatus
    confidence: Confidence
    coverage_frac: float | None = Field(default=None, ge=0, le=1)
    missing_reason: str | None = None
    hours_in_modeled_year: float | None = Field(default=None, gt=0, le=8784)
    data_mode: DataMode

    @field_validator('source_json', 'assumptions_json')
    @classmethod
    def _json_object(cls, value):
        def invalid_constant(_): raise ValueError('Nonfinite JSON constant')
        if not isinstance(json.loads(value, parse_constant=invalid_constant), dict):
            raise ValueError('Scenario provenance/assumptions must be JSON objects')
        return value

    @model_validator(mode='after')
    def _period_value(self):
        present = self.value is not None or self.value_text is not None
        if self.status == ValueStatus.UNKNOWN:
            if present or not self.missing_reason or self.confidence != Confidence.UNKNOWN:
                raise ValueError('Unknown temporal value requires null, unknown confidence and reason')
        elif not present or self.missing_reason is not None or self.confidence == Confidence.UNKNOWN:
            raise ValueError('Known temporal value requires evidence and no missing reason')
        if not json.loads(self.assumptions_json):
            raise ValueError('Temporal rows require explicit nonempty scenario assumptions')
        if present and (not self.source_id or not json.loads(self.source_json) or self.coverage_frac is None
                        or (self.value is not None and not self.unit)):
            raise ValueError('Known temporal rows require source identity/evidence, coverage and numeric units')
        if self.period_kind == 'unsupported_requested_period':
            if self.period_start_year is not None or self.period_end_year is not None or self.status != ValueStatus.UNKNOWN:
                raise ValueError('Unsupported source period has no invented window or value')
        elif self.period_start_year is None or self.period_end_year is None or self.period_end_year < self.period_start_year:
            raise ValueError('Valid explicit period bounds required')
        if self.period_kind == 'annual_operating' and self.period_start_year != self.period_end_year:
            raise ValueError('Annual row represents exactly one modeled year')
        return self


class LifecycleResult(BaseModel):
    """Gross lifecycle accounting with explicit unknown components and subtotal."""
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
    schema_version: str = '1.0.0'
    grid_id: str = Field(min_length=1)
    grid_definition_id: str = Field(min_length=1)
    facility_id: str = Field(min_length=1)
    design_id: str = Field(min_length=1)
    scenario_id: str = Field(min_length=1)
    opening_year: int
    lifetime_years: int = Field(gt=0)
    construction_kg: float | None = Field(default=None, ge=0)
    equipment_kg: float | None = Field(default=None, ge=0)
    operations_electricity_kg: float | None = Field(default=None, ge=0)
    operations_electricity_known_subtotal_kg: float | None = Field(default=None, ge=0)
    operations_other_kg: float | None = Field(default=None, ge=0)
    operations_kg: float | None = Field(default=None, ge=0)
    replacements_kg: float | None = Field(default=None, ge=0)
    end_of_life_kg: float | None = Field(default=None, ge=0)
    total_lifecycle_kg: float | None = Field(default=None, ge=0)
    known_subtotal_partial_kg: float | None = Field(default=None, ge=0)
    known_leaf_count: int = Field(ge=0)
    required_components_json: str
    unknown_components_json: str
    component_metadata_json: str
    accounting_boundary_json: str
    status: ValueStatus
    confidence: Confidence
    missing_reason: str | None = None
    data_mode: DataMode

    @field_validator('required_components_json','unknown_components_json','component_metadata_json','accounting_boundary_json')
    @classmethod
    def _finite_json(cls,value):
        def invalid_constant(_): raise ValueError('Nonfinite lifecycle JSON constant')
        json.loads(value,parse_constant=invalid_constant)
        return value

    @model_validator(mode='after')
    def _total_status(self):
        unknown = json.loads(self.unknown_components_json)
        required = json.loads(self.required_components_json)
        metadata = json.loads(self.component_metadata_json)
        boundary = json.loads(self.accounting_boundary_json)
        components = ['construction','equipment','operations','replacements','end_of_life']
        leaves = ['operations_electricity','operations_other','construction','equipment','replacements','end_of_life']
        if not isinstance(unknown, list) or not isinstance(required, list) or not isinstance(metadata, dict) or not isinstance(boundary, dict):
            raise ValueError('Lifecycle accounting metadata has invalid JSON structure')
        if len(required)!=len(components) or set(required)!=set(components) or len(set(unknown))!=len(unknown) or set(unknown)!={c for c in components if getattr(self,c+'_kg') is None}:
            raise ValueError('Required and unknown lifecycle components must match exact component fields')
        if not set(components+['operations_electricity','operations_other'])<=set(metadata) or not isinstance(boundary.get('component_modules'),dict) or set(boundary['component_modules'])!=set(leaves):
            raise ValueError('Lifecycle metadata must declare all component evidence and accounting boundaries')
        valid_modules = {f'A{i}' for i in range(1,6)} | {f'B{i}' for i in range(1,8)} | {f'C{i}' for i in range(1,5)}
        for component,modules in boundary['component_modules'].items():
            if not isinstance(modules,list) or not modules or len(set(modules))!=len(modules) or not set(modules)<=valid_modules or ('B6' in modules and component!='operations_electricity'):
                raise ValueError('Lifecycle component boundary has invalid/overlapping accounting modules')
        if not all(isinstance(metadata[c],dict) for c in components+['operations_electricity','operations_other']):
            raise ValueError('Lifecycle component evidence must be JSON objects')
        def equal(a,b): return math.isclose(a,b,rel_tol=1e-10,abs_tol=1e-6)
        expected_operations = None if self.operations_electricity_kg is None or self.operations_other_kg is None else self.operations_electricity_kg+self.operations_other_kg
        if (expected_operations is None)!=(self.operations_kg is None) or (expected_operations is not None and not equal(self.operations_kg,expected_operations)):
            raise ValueError('Operations must equal electricity plus other operating components when complete')
        if self.total_lifecycle_kg is None:
            if self.status != ValueStatus.UNKNOWN or not self.missing_reason or not unknown:
                raise ValueError('Incomplete lifecycle requires UNKNOWN and named unknown components')
        elif self.status != ValueStatus.CALCULATED or unknown or self.missing_reason:
            raise ValueError('Known lifecycle total requires complete calculated accounting')
        elif not equal(self.total_lifecycle_kg,sum(getattr(self,c+'_kg') for c in components)):
            raise ValueError('Lifecycle total must equal its five complete components')
        if (self.known_leaf_count == 0) != (self.known_subtotal_partial_kg is None):
            raise ValueError('No known leaves cannot yield a zero subtotal')
        partials = [self.operations_electricity_known_subtotal_kg]+[metadata[c].get('known_subtotal_kg') for c in leaves if c!='operations_electricity']
        known_partials = [v for v in partials if v is not None]
        if any(type(v) not in {int,float} or not math.isfinite(v) or v<0 for v in known_partials):
            raise ValueError('Lifecycle leaf subtotals must be finite nonnegative numbers')
        if (not known_partials)!=(self.known_subtotal_partial_kg is None) or (known_partials and not equal(self.known_subtotal_partial_kg,sum(known_partials))):
            raise ValueError('Partial subtotal must equal named known accounting leaves')
        if self.total_lifecycle_kg is not None and not equal(self.known_subtotal_partial_kg,self.total_lifecycle_kg):
            raise ValueError('Complete lifecycle partial subtotal must match full total')
        return self


__all__ = [
    "GridCell",
    "FeatureMetadata",
    "FacilityConfig",
    "ScreeningResult",
    "ScreeningEligibility",
    "SitePerformance",
    "DecisionResult",
    "CandidateRegion",
    "RunManifest",
    "FutureScenarioValue",
    "LifecycleResult",
]
