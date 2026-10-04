# Data contracts

Authoritative, column-by-column description of every table `dc_locator` produces, and the file-level
metadata every Parquet/GeoParquet file carries (AGENTS.md section 6). The pydantic source of truth for
all nine schemas is `src/dc_locator/schemas.py`; this document explains *why* each field exists and how
it was computed, which the code's docstrings summarize more tersely.

Schema versions follow semver. A breaking field change bumps the major version and must be recorded here
as a changelog entry (AGENTS.md section 9) before any later phase relies on the new shape.

## Changelog

- **Phase7 delivery, 2026-10-03** — active `RunConfig` **2.0.0** is a reference-based
  `DeliveryConfig` rather than the legacy embedded Phase1 run shape. The legacy loader still reads1.0.0;
  `load_run_config` dispatches explicit `delivery_version` documents to the new contract. Native geographic,
  physical and decision row semantics/versions are unchanged. Final enhanced geography uses1.2.0 and
  FeatureMetadata1.1.0, including reproducible run-package copies. New current sensitivity/rank-range
  tables are1.0.0 with `validation_revision`/`validation_id`; they never claim a Phase6 freeze ID.
  JSON execution metadata is2.0.0; stage/profile/source/current-validation JSON is separately versioned.
  Exact current baseline table comparison tolerates lossless nullable numeric/list serialization while
  still rejecting different values, bool-as-number, geometry, membership, identity or contributions.

- **Phase 3, 2026-10-03** -- FacilityConfig, ScreeningResult and SitePerformance are **1.1.0**.
  Additive configuration/evidence/unit-conversion fields preserve existing names and historical rows.
  Facility load factor now permits zero; PUE is constrained to >=1; nonfinite physical values are rejected.
  Screening UNKNOWN requires a null decision value and missing reason; PASS/FAIL requires a value.
  Informational regional evidence is stored in `evidence_json`, with UNKNOWN decision outcome and no
  invented threshold. New ScreeningEligibility **1.0.0** records the explicit acceptance/conditional gate.
  Existing Phase 1/2 geographic contracts, files, values and metadata are unchanged.
- **2026-10-03 UTC** -- Phase 2 introduces `GeographicFeatureDataset` **1.1.0**
  without changing the Phase 1 GridCell fields or IDs. `FeatureMetadata` **1.1.0**
  corrects textual-value presence: either `value` or `value_text` supplies an
  observed/calculated/proxy value; UNKNOWN forbids both. Missing reasons apply
  only when both are absent. Existing numeric 1.0.0 records remain valid. The
  long table remains one row per grid_id/metric, with per-source native units,
  coverage and masks documented in `docs/data_dictionary.md`.

- **2026-10-03 UTC (2026-10-02 America/New_York)** -- GridCell contract **1.1.0**:
  definition numbers now preserve fractional metres; grids with an origin other than the published
  `(-2500000, 3400000)` or a scheme other than v1 prefix `grid_definition_id` to `grid_id`.
  Existing fixed-origin v1 identifiers and all three saved 1.0.0 files remain unchanged.
  Fraction validation accepts at most `1e-9` numerical excess above one without changing measured areas;
  larger state/county area mismatches fail generation. No columns are added or removed. Consumers must
  treat IDs as opaque strings and check `grid_definition_id` before joining different datasets; no
  migration is needed for current saved files. New grid writes use 1.1.0 metadata; other schemas remain 1.0.0.
- **2026-10-02** -- Phase 1: all eight schemas introduced at `schema_version = "1.0.0"`. Only `GridCell`
  is populated with real data this phase; the other seven are structural placeholders (see
  `docs/phase_handoff.md`).

---

## 1. GridCell (`schema_version 1.1.0`, reads existing 1.0.0) -- `data/processed/us_grid*.parquet`

One row per grid cell. Primary key: `grid_id`. Produced by `dc_locator.geography.grid.generate_national_grid`
/ `select_study_area`; see "The grid definition" below for the full algorithm.

| Column | Type | Unit | Description |
|---|---|---|---|
| `grid_id` | string | -- | Primary key within one grid definition. Published fixed-origin v1 uses e.g. `g10000m-r0022-c0051`; other origins/schemes prefix `<grid_definition_id>--`. Never depends on processing order or the study area. |
| `grid_definition_id` | string | -- | Identifies the grid definition (CRS + origin + cell size + scheme version) this cell belongs to, e.g. `conus-epsg5070-ox-2500000-oy3400000-s10000m-v1`. |
| `row` | int32 | -- | Row index from the fixed national origin (top-left), increasing southward. |
| `col` | int32 | -- | Column index from the fixed national origin, increasing eastward. |
| `tile_id` | string | -- | `(row // tile_size_cells, col // tile_size_cells)`, zero-padded 4 digits each, e.g. `t25-tr0000-tc0002`. A coarser grouping for future resumable, tile-based processing (Phase 2+). |
| `geometry` | Polygon, EPSG:5070 | metres | The **full** cell square -- never clipped to the study-area boundary. |
| `cell_area_km2` | float64 | km² | `(cell_size_m / 1000)^2`. Constant for every cell sharing a `grid_definition_id`. |
| `study_area_intersection_km2` | float64 | km² | Area of `(cell square ∩ CONUS boundary)`. |
| `study_area_frac` | float64 | fraction (0-1) | `study_area_intersection_km2 / cell_area_km2`. |
| `is_boundary_cell` | bool | -- | `study_area_frac < 1 - 1e-9`, i.e. the CONUS boundary cuts through this cell. |
| `centroid_x_m`, `centroid_y_m` | float64 | metres, EPSG:5070 | Centroid of the **full** cell square. |
| `centroid_lat`, `centroid_lon` | float64 | degrees, EPSG:4326 | The above centroid, reprojected. |
| `rep_point_lat`, `rep_point_lon` | float64 | degrees, EPSG:4326 | A point guaranteed to fall inside `(cell ∩ CONUS)` (`shapely representative_point()` of the clipped intersection, then reprojected). Use this, not the centroid, whenever a point *inside the study area* is required -- a boundary cell's centroid can fall outside CONUS entirely. |
| `state_fips_primary` | string(2) | -- | 2-digit state FIPS code with the largest intersection area. Ties broken by the lowest FIPS code. |
| `state_abbr_primary` | string(2) | -- | USPS abbreviation of `state_fips_primary`. |
| `state_share_primary_frac` | float64 | fraction (0-1) | `area(cell ∩ state_fips_primary) / study_area_intersection_km2`. |
| `state_fips_all` | string | -- | `;`-joined, sorted, every state FIPS code intersecting this cell. |
| `n_states` | int64 | count | `len(state_fips_all.split(';'))`. Observed values in the Phase 1 national run: 1 (75,758 cells), 2 (4,046), 3 (83), 4 (1 -- a four-state corner). |
| `county_geoid_primary` | string(5) or null | -- | 5-digit state+county FIPS (`GEOID`) with the largest intersection area, or **null** -- see "County-attribution edge case" below. |
| `county_name_primary` | string or null | -- | Name of `county_geoid_primary`. |
| `county_share_primary_frac` | float64 or null | fraction (0-1) | Same definition as the state share, for the primary county. |
| `county_geoid_all` | string or null | -- | `;`-joined, sorted, every county GEOID intersecting this cell. |
| `n_counties` | int64 | count | `0` only in the null-county edge case; otherwise `len(county_geoid_all.split(';'))`. |
| `data_mode` | string (`real`\|`synthetic`) | -- | Always `real` under `data/processed/` (enforced by `dc_locator.io`). |

All `*_km2` figures come from areas measured directly in EPSG:5070 (an equal-area projection), never
from degrees (AGENTS.md section 6).

`study_area_intersection_km2` is an **administrative-boundary intersection**, including mapped inland
and coastal water in the Census polygons. It is not land area or developable area. A water/land mask
from Phase 2 land-cover features is required before reporting land-only suitability. Census `ALAND`
is state-level metadata and is not distributed among cells or used to fabricate a land-only geometry.

### County-attribution edge case

`county_geoid_primary`/`n_counties=0` is reserved for a cell that intersects CONUS (via the state
cartographic boundary file) but matches no polygon in the *separate* county cartographic boundary file --
possible because the two files are independently generalized at the coastline and can disagree by a sliver
narrower than a cell. **This did not occur in the Phase 1 national run** (`n_counties` was never 0 for any
of the 79,888 retained cells at 10 km resolution; see `docs/phase_handoff.md`), but the schema and the
code (`GridCell`'s consistency validator, `generate_national_grid`'s null-handling) support it rather than
assuming it can never happen, since it becomes more likely at finer resolutions or after a boundary-vintage
change.

---

## 2. FeatureMetadata (`schema_version 1.1.0`) -- `data/processed/feature_provenance.parquet`

A thin, versioned wrapper around `dc_locator.provenance.ProvenanceRecord` (adds only `schema_version`).
One row per `(grid_id, metric)` for every declared Phase 2 geographic metric, including missing ones.
`value_text` stores region/category-share JSON or region labels without fabricated numeric codes.
`coverage_frac` uses the Phase 1 study-intersection geometry, not the full square's offshore area.
Infrastructure proximity has null areal coverage because an infrastructure inventory is not an areal
measurement. Native resolution is preserved even though outputs are joined to 10 km cells.

### GeographicFeatureDataset (1.1.0)

All original Phase 1 grid rows and square geometries, plus the metrics in `docs/data_dictionary.md`.
For each geographic metric, `<metric>_status`, `<metric>_confidence`, and (except coverage metrics
themselves) `<metric>_coverage_frac` appear in the wide table. A coverage value of 0 does not make a
missing hazard value 0. Analysis geometry is cell square intersect CONUS boundary; its recomputed
area must match `study_area_intersection_km2`. A development bounding box selects IDs only and is
never used as the analysis clipping boundary. The saved 42-cell table is development coverage;
no national analysis is claimed. The builder accepts the 79,888-cell national grid and processes
bounded resumable tiles, subject to source availability and the documented compute budget.

## 3. FacilityConfig (`schema_version 1.1.0`) -- Phase 3 input, `configs/facility.yaml`

`facility_id` (PK), `peak_it_power_mw`, `average_it_load_factor` (0-1), `target_opening_year`,
`operating_lifetime_years`, `cooling_design_id` (FK, nullable), `notes`; Phase 3 adds
`hours_in_modeled_year`, `minimum_land_area_km2`, `cooling_designs` (design IDs), `screening_mode`,
`basis` and `rationale`. Older rows may omit new optional fields; missing hours/land requirements remain
UNKNOWN rather than using implicit defaults. The current 100 MW/0.80/2030/25-year/8760-hour specification
is an explicit project assumption. Land minimum 100 acres is a planning assumption, not parcel evidence.

## 4. ScreeningResult (`schema_version 1.1.0`) -- Phase 3 output

One row per `(grid_id, design_id, scenario_id, requirement)`: `outcome` (`PASS`\|`FAIL`\|`UNKNOWN`),
`mode` (`STRICT`\|`EXPLORATORY`), `value`/`unit`/`threshold`, `is_critical`, `missing_reason`.
Additional fields: `grid_definition_id`, `facility_id`, `metric`, `reason`, `evidence_json`,
`source_status`, `confidence`, `coverage_frac`, `basis`, `rationale`, `data_mode`.
`evidence_json` preserves source ID/field/year/resolution/status/coverage and observed value, including
informational regional indicators that cannot establish parcel feasibility. Confirmed requirements
accept observed/calculated evidence by default, rejecting proxy/scenario evidence as UNKNOWN. Explicit
`accepted_statuses` permits the NLCD proxy only for regional total-area plausibility; optional
`accepted_source_ids` restricts source identity. Critical constraints need full coverage within a disclosed
1e-6 numerical tolerance; partial evidence never silently PASSes. This tolerance is a computational policy.

## 5. SitePerformance (`schema_version 1.1.0`) -- Phase 3 output

One row per `(grid_id, design_id, scenario_id)`: `pue`, `wue_l_per_kwh`, `e_it_mwh`, `e_facility_mwh`,
`grid_carbon_intensity_kg_per_mwh`, `c_electricity_kg`, `w_site_m3`, `w_electricity_m3` (kept separate
from site water per AGENTS.md section 6). Adds `grid_definition_id`, `facility_id`,
`c_electricity_tonnes`, `w_site_liters`, `w_electricity_liters`, `w_site_withdrawal_m3`,
`w_site_withdrawal_liters`, `w_electricity_withdrawal_m3`, `w_electricity_withdrawal_liters`, `peak_facility_demand_mw`,
`target_opening_year`, `operating_lifetime_years`, `hours_in_modeled_year`, `metric_metadata_json`,
`assumptions_json`, `warnings_json`, `data_mode`.

All physical values are annual, not lifetime totals. Canonical `w_site_m3` and `w_electricity_m3` mean
consumption; withdrawal-based factors populate only distinct withdrawal fields. Missing factors or
incompatible water basis yield nulls with UNKNOWN metadata, even at zero load. `metric_metadata_json`
maps each physical metric to status/confidence/unit/formula/missing reason and relevant source evidence.
PUE/WUE are scenario assumptions. Historical 2023 carbon reused for opening 2030 is status `scenario`,
while its original proxy/observed metadata is retained under `source_evidence`; emissions are calculated.
Peak facility demand remains UNKNOWN without separately verified design-day peak PUE/evidence.

### ScreeningEligibility (`schema_version 1.0.0`) -- Phase 3/4 gate

One row per `(grid_id, design_id, scenario_id)` with `grid_definition_id`, `facility_id`, `mode`,
`hard_fail`, `critical_unknown`, `eligible`, `conditional`, `data_mode`. Any critical FAIL sets hard_fail
and prevents eligibility in both modes. STRICT additionally excludes critical UNKNOWN. EXPLORATORY
retains those alternatives with conditional=true, without changing their requirement outcomes to PASS.
SitePerformance contains all alternatives for diagnostics; Phase 4 must join this table before ranking.

## 6. DecisionResult (`schema_version 1.1.0`) -- Phase 4 output

One row per `(grid_id, design_id, scenario_id)`: `hard_fail`, `is_pareto_optimal`, `pareto_rank`,
`ahp_status`, `mcda_score`, `contribution_by_metric`, `weights_used`, plus profile/grid/data identity,
eligibility/conditional/criticalUNKNOWN flags and rankability/status/reason. Phase4 populates its
validated core projection in the wideRankedCellDataset; see additive migration below.

## 7. CandidateRegion (`schema_version 1.1.0`) -- Phase 4 output

One row per clustered region: `region_id` (PK), `member_grid_ids` (unique, non-empty), `n_cells`,
`total_area_km2`, `centroid_lat`/`lon` (a search-area centroid, never an approved site -- AGENTS.md
section 1/8), `mean_mcda_score`, plus actual evaluated representative, metric distributions,
suitable-area proxy, profile/grid identity and screening flags. Phase4 populates regions for the
conditional development example and a valid empty collection for strict screening.

## 8. RunManifest (`schema_version 1.0.0`) -- `runs/<run_name>/run_metadata.json` (Phase 7, usable earlier)

`run_id` (PK), `created_at` (UTC, tz-aware required), `code_revision`, `config_snapshot_hash`
(`dc_locator.config.config_snapshot_hash`), `grid_definition_id`, `grid_resolution_m`, `dataset_versions`,
`source_coverage`, `random_seed`, `data_mode`, `warnings`, `blockers`.

---

## File-level Parquet metadata contract

Every file `dc_locator.io.write_geoparquet`/`write_parquet` writes carries these schema-metadata keys
(AGENTS.md section 6), merged in without disturbing any pre-existing key such as GeoParquet's own `geo`
key:

| Key | Example value |
|---|---|
| `dc_locator.schema` | `GridCell` |
| `dc_locator.schema_version` | `1.0.0` |
| `dc_locator.data_mode` | `real` |
| `dc_locator.grid_definition_id` | `conus-epsg5070-ox-2500000-oy3400000-s10000m-v1` (geography tables only) |
| `dc_locator.created_by` | `dc_locator/0.1.0 (<hostname>/<user>)` |

Read them back with `dc_locator.io.read_parquet_metadata(path)`. Writing `data_mode=synthetic` anywhere
under `data/processed/` raises `SyntheticDataInProcessedDirError` rather than silently writing the file
(AGENTS.md section 3.6).

---

## The grid definition (GRID CONTRACT)

Encoded in `configs/grid.yaml`; loaded/validated by `dc_locator.config.GridConfig`.

- **CRS**: `EPSG:5070` (NAD83 / Conus Albers Equal Area, metres) for cell geometry, areas, and adjacency.
  Lat/lon outputs use `EPSG:4326`. Confirmed empirically (not assumed) that this CRS's point `areal_scale`
  factor is exactly `1.0` everywhere (true equal-area), while its linear scale factor deviates from `1.0`
  away from the two standard parallels -- see `src/dc_locator/geography/distance.py`'s module docstring for
  the measured bound and exactly how it was computed.
- **Fixed national origin** (top-left corner): `origin_x_m = -2,500,000`, `origin_y_m = 3,400,000`. These
  are constants of the grid definition, **not** derived from the boundary. Verified against the actual
  loaded CONUS boundary (`tests/test_boundary.py`, and manually during Phase 1 development): the real
  boundary's EPSG:5070 bounds are approximately `minx=-2,356,114`, `maxy=3,172,568` -- comfortably inside
  the fixed origin on both axes, so `generate_national_grid` does not hit its `GridOriginViolationError`
  fail-loud path for the current boundary vintage, but will if a future, differently-sourced or
  differently-clipped boundary ever extends further north or west.
- **Cell size**: `cell_size_m`, default `10,000` (10 km). Must be `> 0`; a `UserWarning` (not a failure) is
  raised if `100,000` is not an integer multiple of it, since that loses exact nesting across resolutions.
- **Row/col formula**: `col = floor((x - origin_x) / size)`; `row = floor((origin_y - y) / size)`. Cell
  `(row, col)` is the square `[ox + col*s, ox + (col+1)*s] x [oy - (row+1)*s, oy - row*s]`.
- **`grid_definition_id`**: `f"conus-epsg5070-ox{origin_x_m}-oy{origin_y_m}-s{cell_size_m}m-v{grid_scheme_version}"`,
  e.g. `conus-epsg5070-ox-2500000-oy3400000-s10000m-v1`. Whole-metre numbers retain their original spelling;
  fractional values use Python's shortest float round-trip representation, never integer rounding. Inputs
  must be finite. Across definitions use `(grid_definition_id, grid_id)` as the identity/join key.
- **`grid_id`**: `f"g{cell_size_m}m-r{row:0{digits}d}-c{col:0{digits}d}"`, e.g. `g10000m-r0022-c0051`.
  This spelling is preserved for the published origin `(-2500000, 3400000)` and scheme v1. Other origins
  or schemes use `<grid_definition_id>--<above ID>`, preventing row/column collisions across changed
  definitions. Cell size uses the same exact numeric formatting as `grid_definition_id`.
  `digits` is `configs/grid.yaml:id_row_col_digits` (default 4); generation fails loudly
  (`GridIdOverflowError`) if the real extent needs more digits than configured, rather than silently
  truncating or colliding IDs.
- **`tile_id`**: `(row // tile_size_cells, col // tile_size_cells)`, zero-padded 4 digits regardless of
  `id_row_col_digits` (an independent formatting choice), e.g. `t25-tr0000-tc0002`.
- **Inclusion rule**: a cell is retained when its square intersects the CONUS boundary with intersection
  area strictly greater than `min_intersection_km2` (default `0.0`, i.e. any positive area; a pure
  edge/point touch has area exactly `0` and is always excluded regardless of the threshold). If a positive
  threshold is configured, excluded-by-threshold cells are counted (`n_excluded_by_min_intersection_threshold`,
  `excluded_by_threshold_total_km2`) in `us_grid_summary.json`, never silently dropped.
- **CONUS** = 48 states + DC. Excludes Alaska (`02`), Hawaii (`15`), and the island territories American
  Samoa (`60`), Guam (`66`), Northern Mariana Islands (`69`), Puerto Rico (`72`), U.S. Virgin Islands (`78`).
- **Study areas**: `conus` (the full national grid) plus named EPSG:4326 bounding boxes under
  `grid.yaml:study_areas` (`dev_tiny`, `dev_default`). `select_study_area` selects national-grid cells
  whose full square intersects **both** CONUS (already guaranteed) and the bounding box -- the box is
  densified (`shapely.segmentize`, 0.01 degree steps) before reprojection to EPSG:5070 so its edges are not
  coarsened into 4 straight segments under the Albers projection. Selection never recomputes an ID or
  attribute: a cell retained in both a development output and the national output is identical in every
  non-geometry-subsetting column (verified in `tests/test_cli_build_grid_real.py`).
- **State/county attribution**: computed by overlaying each retained cell's **full square** (not the
  CONUS-clipped shape) against the state/county cartographic boundary layers. State geometry lies in the
  state union by construction; independently generalized county geometry may disagree at a coastline.
  Generation raises `GridIntegrityError` for a primary fraction above `1 + 1e-9`, rather than silently
  clipping an observed area. Fractions above one by at most `1e-9` are preserved and counted in
  `generation_stats.fraction_roundoff_above_one_counts`. The saved national file has 25 state and 20
  county fractions above one by floating roundoff only (maximum county excess `4.44e-16`). Primary
  = largest intersection area; ties broken by the lowest FIPS/GEOID code (`dc_locator.geography.grid._aggregate_primary_and_all`).

See `src/dc_locator/geography/grid.py` for the full, vectorized implementation and
`tests/test_grid.py` for a completely hand-calculated worked example (areas, fracs, state/county
attribution, tie-breaking) independent of the production code.
# Phase 4 additive migration (2026-10-03)

DecisionResult and CandidateRegion defaults move1.0.0→1.1.0. Earlier structural fields remain;
new optional identity/profile/eligibility fields preserve earlier numeric callers. New decisions
validate that hardFAIL, ineligible, unrankable and STRICT criticalUNKNOWN records cannot carry
MCDA scores. CandidateRegion representative_grid_id must be a member. FeatureMetadata, geography
and Phase3 physical meanings do not change.

`ranked_cells.parquet` is the wide`RankedCellDataset`1.1.0 (core projection validated as
DecisionResult1.1.0): retained SitePerformance values/metadata/assumptions/warnings, canonical
facility_id, eligibility, raw_<metric_id>, normalized leaf columns, full weights/contributions JSON,
each contribution_<metric_id>, profile identity/hash, weighting/AHP status, rankability/reason,
MCDA score/rank and scenario-separated Pareto status. JSON encodings avoid ambiguous nested column
schemas. `rank_status`=RANKED/CONDITIONAL/UNRANKED/INELIGIBLE/WEIGHTS_REVIEW_REQUIRED. Unknown
scores/contributions/ranks stay null; missing metrics never induce per-alternative reweighting.

`normalized_metrics.parquet`:NormalizedMetricDataset1.0.0, one alternative×active metric. Includes
raw value, physical column/unit, original status/confidence/evidence_json, coverage, source_valid,
missing_reason, normalized_value, normalization_status(within_reference/clipped_low/clipped_high/
missing), reference bounds/direction/method, constant_observed_column and profile/grid/data identity.
`pareto_results.parquet`:ParetoDataset1.0.0, all alternatives including dominated/notassessed,
selected raw objectives and eligibility. `pareto_comparable` is independent of MCDA rankable/AHP
review; is_pareto_optimal null for NOT_ASSESSED, true for FRONTIER, false for DOMINATED.
`pareto_rank`0 identifies only the frontier; no deeper layers are claimed.

CandidateRegion1.1.0 GeoJSON adds dc_locator metadata (schema/version/grid/data/profile/hash),
member IDs, actual representative_grid_id/representative_json, suitable_land_area_km2 proxy,
metric_distributions_json and conditional/criticalUNKNOWN interpretation. Geometry is EPSG4326
for interchange; clustering/union/centroid computation uses EPSG5070. `region_membership.parquet`
RegionMembership1.0.0 retains evaluated tuple keys, member score/Pareto/screening flags and
suitable-area proxy. Empty strict feature collections/tables are valid.

Public`decide(...)`/`assemble_metrics(...)` validate SitePerformance, ScreeningEligibility and
FeatureMetadata rows, grid/data/facility identity and provenance. Accepted FeatureMetadata rows
store grid definition only in file metadata; direct table callers must bind
`provenance.attrs['grid_definition_id']` or provide`provenance_grid_definition_id=`. The file runner
checks and binds all file metadata before calling the table API. Baseline byte fingerprint is
protected by its predeclaration; custom/versioned profiles are frozen in run snapshots before
ranking and record their own hashes. They are not labeled independently accepted baseline profiles.

## Phase 5 additive contracts

Enhanced GeographicFeatureDataset1.2.0 appends native context and future Aqueduct features while
preserving baseline columns/geometry/values. FeatureMetadata remains1.1.0; its extensible
missing-reason vocabulary adds `unsupported_source_period`. Additive and temporal APIs validate
every provenance row, unique(grid_id,metric), exact grid domain, mode and verified grid definition
bound through attrs or an explicit argument. Existing stored contracts and Phase3/4 outputs remain.

FutureScenarioValue1.0.0 (`future_scenarios.parquet`) keys include grid/design/scenario/model,
period_kind, explicit start/end and variable, plus grid_definition_id/facility_id/data_mode.
Columns also include milestone_year, ssp_rcp, value/value_text/unit, source_id/source_year/source_json,
assumptions_json, status/confidence/coverage_frac/missing_reason and hours_in_modeled_year.
Known numeric values require units, source evidence, coverage and assumptions. UNKNOWN has null
values, unknown confidence and a reason. Annual rows represent one modeled year; native-window rows
keep their source bounds; unsupported requested periods have null bounds. Physical calculated
energy/site-water source convention `dc_locator_physics_v1` refers to recorded project assumptions,
with coverage1 of the configured alternative, not external engineering verification.

LifecycleResult1.0.0 (`lifecycle_results.parquet`) has construction_kg, equipment_kg, operations_kg,
operations_electricity_kg, operations_electricity_known_subtotal_kg, operations_other_kg,
replacements_kg, end_of_life_kg, total_lifecycle_kg, known_subtotal_partial_kg and known_leaf_count.
Opening/lifetime, required/unknown components JSON, component_metadata_json, accounting_boundary_json
and status/confidence/reason accompany each alternative. Units are gross kgCO2e. Unknown required
components keep total null; all-unknown partial is null, while explicit known zeros are retained.
Schemas validate JSON, exact unknown fields and sum identities. Model methods enforce compatible
units/products/modules, full annual carbon support and no duplicate included freight.

BaselineEnhancedComparison1.0.0 records one mode/grid/design/external-context comparison: raw physical
values and water stress, score/rank deltas, both rankability/status/conditional/criticalUNKNOWN/hardFAIL
flags, pathway/SSP/native window and matched-preference assertion. The only active binding change is
predeclared future water. Context-only NASA has an independent model/member/SSP/year ID and reserved
source_context design. Full accounting/period and input rules are documented in
`docs/research/phase5/temporal_lifecycle.md`; no new source receives an automatic weight.

## Phase 6 additive validation contracts

Phase 6 does not alter accepted geographic, physical, screening, decision or Phase 5 schemas. It adds
`SensitivityResult` 1.0.0 and `AlternativeRankRange` 1.0.0 under
`dc_locator.model.validation.schemas`. Sensitivity rows require matching base/case grid definition,
facility, data mode and complete grid/design domains. Boolean flags are strict; rankable requires eligible,
non-hard-fail, finite rank and score; strict critical UNKNOWN cannot rank; conditional requires an eligible
exploratory critical UNKNOWN. Rank and score deltas must equal their endpoints. JSON fields must be finite
objects. Alternative rank-range rows require ranked+unranked=evaluated and exact min/max/range identities.

CSV summaries are deterministic projections of validated long rows. Robustness counts cannot exceed the
alternative domain. Fixed-region rows require every accepted baseline member, consistent eligibility and
rankability counts, ranked-member min/max, and a null mean whenever any original member is unranked.
Resolution rows compare topology and area over the preregistered common footprint and never equate unlike
fine/coarse IDs. Data-quality known counts are rowwise numeric-or-text evidence; UNKNOWN is separate, and
partial coverage means known coverage below one rather than an invented value status.

`freeze_manifest.json` 1.0.0 records the evaluation version, freeze ID, complete software/input inventories,
restorable snapshot files/archive, and a pre-holdout status. Verification recomputes every hash and exact
inventory; any added, deleted or modified protected file requires a new version. Each prospective build's
`evaluation_manifest.json` binds the freeze, ordered grid IDs/definition, primary/repeat hashes, the frozen
build script, and all protected builder/source/config/grid inputs. The validator then rechecks preregistered
IDs, row/column, bounds, WKB hashes, disjointness, distance, equal footprint and file metadata before use.

## Phase7 delivery contracts

`DeliveryConfig`2.0.0 contains explicit file references (grid, source registry/native documents,
facility/design/scenario/requirements/profile), real/synthetic mode, strict/exploratory mode,
weighting/AHP, separate future contexts, current-validation settings and a declared bounded execution
budget. Unknown options and wrong setting types reject. Output folders remain workspace-owned and
historical input/freezes/results are protected. `ingest` verifies native bytes and acquisition log
URL/source/version/request identities; it does not acquire unavailable data.

All persisted tables retain `dc_locator.schema`, `schema_version`, `data_mode`, `grid_definition_id`.
`candidate_regions.parquet` retains original EPSG:5070 geometry for exact semantic recomputation;
`candidate_regions.geojson` is its validated EPSG:4326 presentation. RegionMembership1.0.0 includes
profile ID/fingerprint, grid definition and data mode. `weight_result.json` records actual global
weights/method; requested AHP with no judgments remains equal/template, without expert claims.

CurrentRunIdentity binds stable run ID, working model revision/hash mapping, configuration hash mapping
and source hash mapping. CurrentValidationSettings declares baseline mode, exact-k policy and bounded
explicit scalar/weight/screening cases. A FutureValidationContext binds one native pathway/milestone/
window/SSP profile and source geometry independently. CurrentSensitivityResult1.0.0 stores all alternatives
per case, including exclusions; CurrentAlternativeRankRange1.0.0 stores evaluated/ranked/unranked counts
and null rank ranges when no ranked denominator exists. Fixed-region CSV retains original baseline
members. Future newly selected regions are not relabeled as fixed baseline stability experiments.

`stage_manifests` bind current content identity and substantive output hashes; same-folder identity
changes reject instead of mixing stale optional outputs. RunMetadata2.0.0 separates content-derived
analysis ID from execution UUID/timestamp, current working-code hashes from Git base, and accepted
historical phase records from fresh current validation. Canonical Phase7 acceptance is recognized only
for the matching delivery version and complete current code hash mapping. Independent test evidence
is a separate phase record, not an invented validation accuracy claim.

## Phase7 V2 resource accounting

The first delivery repeat exposed a cumulative interim-cache byte counter inside the source manifest.
All science/source/geometry/decision/report tables matched; the counter and its dependent stage checksum
changed when another run added a cached tile. V1 outputs and executable_freeze.json were retained.
The narrowly revised executable_freeze_v2.json moves cumulative raw/interim byte totals into freshly
measured `run_metadata.resource_diagnostics`, including cached executions. Native source-file bytes and
hashes remain authoritative substantive evidence; the native adapters themselves were not changed.
Only intermediate `geography_core/coverage_report.json` processed/resumed counters and execution metadata
are intentionally varying. Final source manifest and all substantive stage hashes repeat exactly.
# National discovery revision (2026-10-03)

Delivery configuration schema **2.1.0** / `phase8_national_v1` enables bounded CONUS execution;
schema 2.0.0 preserves the historical development resource bounds. National real grids must cover
all 49 CONUS states/DC jurisdictions, so naming a development grid `conus` is rejected. Geographic,
performance, screening and ranking table column contracts and UNKNOWN semantics are unchanged.
The new 50 km grid has its own `grid_definition_id`; no 10 km IDs are reassigned or mixed.

The transport API adds per-run external-context availability in **1.1.0**, while the frontend still
reads archived 1.0.0 responses. Coverage reports include actual projected extent and study area.
Categorical NLCD reprojection records native/output CRS, resampling, checksums and bounded memory
in its preparation manifest. Native classifications are aggregated using the existing land proxy
formula; no source value, weight or screening threshold is invented.
# Phase 9 regional refinement migration (2026-10-03)

The additive wrapper configuration schema3.0.0 composes a real schema2.1.0
national discovery with bounded child analysis. Child snapshot schema2.2.0
requires `phase9_regional_v1` and `study_area: regional_refinement`.
Existing2.0/2.1 serialized configurations retain their contracts.

`GridCell` remains1.1.0: the fixed national EPSG:5070 origin defines 1km rows,
columns and IDs; a window selects full cells and never changes their geometry
or CONUS intersection area. `RegionalRefinementWindows`1.0.0 records the
selected 50km parent geometry and retains the parent grid identity.

`CandidateRegion`1.2.0 adds a semantic constraint for bounded policies:
connected components are formed inside deterministic global lattice partitions,
with projected bounding-box spans at most the declared 20 km per axis. Columns
remain compatible; this limit is a project search-area assumption. Legacy
unbounded policies still emit1.1.0. Neither version identifies approved parcels.

`RegionalPreparedDecisionDataset`1.0.0 persists validated fixed-reference batch
values/statuses with unset global ranks/frontiers. `RegionalRankedCellDataset`
1.0.0 stores the complete compact fine universe and globally recomputed ranks
and Pareto flags, retaining all failed/unranked alternatives. Native wide
`RankedCellDataset`1.1.0 batch outputs are reconciled to those global decisions.
`RegionalGridIndex`1.0.0 holds geometry and clustering fields, while all native
geographic metrics/provenance remain in the checksum-bound batch files.

`regional_catalog.json`1.0.0 binds selected parents, parent run/output identity,
child definition, per-part output hashes, representative-to-part lookup, actual
fine coverage and omitted shortlist coverage. Global ranking applies only to
the explicitly evaluated refined alternatives, separately per external scenario.
Source native resolution is retained; finer cells do not increase source detail.

Regional validation streams complete per-case compact decisions and numeric
comparisons (`RegionalSensitivityDataset`1.0.0). `sensitivity_results.parquet`
contains the existing full sensitivity schema for evaluated representatives;
`RegionalRankRangeDataset`1.0.0 covers every fine alternative. This extract scope
is explicit in the validation report. Fresh batch physics/screening/baseline and
fresh global ranking are checked before completion. API 1.2.0 introduces analysis
resolution, regional coverage and parent lineage; indicator requests select one
bounded parent window, with a10000feature response limit.
# Additive submission contracts — 2026-10-03

`SubmissionBrief` JSON schema 1.0.0 is a presentation of verified saved model outputs,
separate from scientific table schema versions. It retains one selected external
scenario, stored representative ordering, paired design/physical quantities, actual
leaf weights/contributions and archived source/config/code hashes. Representative
cell coordinates and connected region coordinates are separate fields. An empty
STRICT finding contains no manufactured recommendation. The frontend API adds
optional `decision_brief` and unavailable reason under additive version 1.3.0;
older 1.x saved responses remain loadable.

National root tables and regional catalog/native-part tables are supported. Regional
briefs verify full global ranks against selected native representative parts; source
rows and physical metadata come from those same cells. Read only completed artifacts,
verify every consumed checksum/data mode/grid identity, and include native part
ranked tables in the presentation cache identity. No cross-scope evidence is borrowed.

`HeatReuseInputs` and heat-result JSON schema 1.0.0 are optional alternative-bound
contracts. No numerical defaults are supplied. Factors require a project-assumption
basis/rationale or document reference plus table/page/section. Output quantities carry
unit, status, confidence, method and missing reason. Delivered heat is demand capped;
distribution losses and auxiliary-energy emissions are explicit. The signed heating
system carbon comparison does not modify facility emissions or rankings. This adds
new schemas without changing previously accepted scientific table meanings.

## Cleanview diagnostic revision contracts — 2026-10-03

Regional `ScreeningResult` 1.2.0 changes the spatial support of the dedicated
total-suitable-area plausibility rule. In `multi_cell_region` scope, a positive
supported/classified proxy total below facility land demand has outcome UNKNOWN and
`cross_cell_land_support_unverified`; its original numeric evidence remains in
`evidence_json`. This says nothing about a contiguous or obtainable parcel.
Zero supported area remains FAIL, and other FAIL requirements are unchanged.
Regional `ScreeningEligibility` 1.1.0 records the resulting critical UNKNOWN;
STRICT still excludes it. Standalone `single_cell` screening retains the prior
1.1.0 result / 1.0.0 eligibility schemas and meaning. Old saved evidence is
preserved; consumers must use the recorded scope rather than reinterpret it.

`regional_catalog.json` 1.1.0 adds `land_search_scope`. The scope also enters the
run binding, so prior run folders cannot be resumed under the changed meaning.
`RegionalGridIndex` 1.1.0 retains `data_mode` and the existing exact
`county_geoid_all` administrative support string. Historical sparse 1.0.0 indexes
are read through checksum-verified catalog/native geography parts without
changing their bytes. Native support must match the entire evaluated grid.
Regional `CandidateRegion` 1.3.0 adds a semantic publication gate: the complete
bounded region must have enough known total classified land for the facility
minimum. A known insufficient sum rejects that region and its membership even
when its member-cell scores are high. An incomplete sum remains critical UNKNOWN;
adequate total area does not verify contiguity or land availability.
`RegionLandScreening` 1.0.0 retains the PASS/FAIL/UNKNOWN audit for every initial
component, including excluded ones. Legacy national clustering is unchanged.
The 1 km lattice, 20 km projected-axis extent, source precision, scoring weights
and cooling coefficients remain unchanged. Facility minimum land demand above
the projected bounding area is rejected before calculation.

`ExistingSiteCountyComparison` 1.0.0 is a separate diagnostic output. Its keys are
reference facility, design and external scenario within one model/grid domain.
County-geoid support includes every intersecting whole cell; min/max statistics
are conditional model ranges, never facility point estimates. Missing fine
coverage is `OUTSIDE_EVALUATED_DOMAIN`, and unmatched administrative labels are
`UNMATCHED_COUNTY`. Facility score and physical error remain null with reasons.
Real/synthetic modes, geographic identities and consumed saved-output checksums
must agree. No reference-derived quantity changes model scoring or physics.

# Phase 11 national fine surface contracts (2026-10-03)

`RegionalConfig` 3.0.0 adds `selection: national_fine_surface`, which requires
`delivery_version: phase11_national_fine_surface_v1` and vice versa. No field was added, so existing
`representative_parent_cells` configurations serialize identically and keep their binding identities;
their outputs and texts are unchanged.

The Phase 11 stage writes `national_fine_surface/` inside the regional run:

- `NationalFineSurfaceCell` 1.0.0 (`fine_surface_cells.parquet`): one row per retained 1 km cell, sorted by
  `grid_id`, with `parent_grid_id`, `row`, `col` (int32), `study_area_intersection_km2`, `is_boundary_cell`,
  `potentially_suitable_land_frac`, `nlcd_coverage_frac`, `transmission_distance_km`,
  `baseline_water_stress_score`, `baseline_water_stress_score_coverage_frac`,
  `grid_carbon_intensity_kg_per_mwh` and `egrid_coverage_frac`. Missing values are null.
- `NationalFineSurfaceParent` 1.0.0 (`fine_surface_parents.parquet`): per `parent_grid_id`, `design_id` and
  `scenario_id`: `cells`, `scored_cells`, `best_fine_score`, `best_grid_id` (ties: smallest ID) and
  `p90_fine_score`; null when no cell is scored.
- `fine_surface_manifest.json` 1.0.0: `stage_identity` (from the regional binding identity and both method
  versions), method versions, weights, design constants, source paths and checksums, counts, runtime,
  observed peak working set and output hashes. An identical stage is reused; another identity is refused.

Only in this mode, `RegionalRefinementWindows` 1.1.0 adds `fine_selection_rank`, `best_fine_score`,
`fine_best_grid_id`, `fine_best_design_id` and `fine_best_scenario_id`, and `regional_catalog.json` 1.2.0
adds a `national_fine_surface` object (manifest path and checksum, stage identity, method versions, valued
cells, scored alternatives, ranked parents, selection limit) with a mode-specific `coverage_warning`.
Representative runs keep windows 1.0.0 and catalog 1.1.0.

## National fine surface evidence revision (2026-10-03)

`NationalFineSurfaceCell` **1.1.0** adds seven companions for every stored feature:
`<metric>_status`, `_confidence`, `_missing_reason`, `_source_id`, `_source_field`, `_unit`,
and `_data_year`. `feature_provenance.parquet` carries one `FeatureMetadata` 1.1.0 row per
cell × each of the seven metrics, including source versions, retrieval dates, spatial resolution,
aggregation methods, coverage and real/synthetic mode. Infrastructure inventory coverage remains
null; it does not claim areal completeness. A measured zero coverage fraction remains a calculated
zero; the associated unobserved source value remains null with `source_nodata`.

The manifest is **1.1.0** and binds all three Parquet outputs, feature declarations and evidence-row
count. Reuse requires the exact three-output checksum ledger and matching schemas, grid definition
and data mode. Numeric-only 1.0.0 drafts cannot be reused by the revised stage. Both feature and
selection method versions are `v2`; this starts a new delivery identity.

Fine scoring validates source identity/field, unit, allowed status, confidence, source year and
declared coverage, plus the native annual-physics carbon-coverage rule. Missing or incompatible
evidence leaves the alternative unscored; it never changes weights. Energy/site-water constants
carry their archived annual-physics metadata. Parent selection requires one external scenario;
cooling designs remain decision alternatives. These are unscreened investigation values, separate
from the globally ranked, screened alternatives computed after full regional refinement.

GDAL cache is bounded to 64 MiB and provenance-to-Arrow conversion to 50,000 rows at a time.
The stage refuses completion above the existing 4 GiB process-memory bound. These are resource
settings, not geographic or engineering thresholds.

## County socioeconomic context revision (2026-10-04)

This additive geography/context delivery preserves existing technical tables and
their schemas. `county_socioeconomic_geography`,
`candidate_county_socioeconomic_crosswalk` and `candidate_county_coverage` use
**1.0.0**. The frontend transport advances to **1.6.0**, accepting legacy
1.4/1.5 payloads; the separate county context has **1.0.0**. See
`frontend/API_CONTRACT.md` for endpoints and wire fields.

The analytical candidate is the saved real grid cell (`grid_id`, represented as
`candidate_id` in this crosswalk), with its complete EPSG:5070 geometry. Its
technical alternatives remain grid × design × external scenario. The canonical
crosswalk key is unique `(candidate_id, county_geoid)`, sorted by both fields;
all positive-area intersections survive, including secondary jurisdictions.
Line/point contacts are excluded. County fragments are dissolved by GEOID before
intersection. `overlap_fraction = intersection_area_km2 / candidate_area_km2`
uses full saved cell area; unknown/missing county coverage is not renormalized.
The companion coverage table retains every cell, including no-overlap cells,
and records uncovered area and an explicit diagnostic reason.

The user approved mixed vintages: `socioeconomic_year=2024` with
`boundary_year=2025` (default) or `2023`. Boundary type is
`cartographic_500k`, never TIGER/Line. Geometry is generalized and may leave
coastal/border gaps. GEOIDs remain five-character strings and are the only
socioeconomic join key. Unmatched counties retain null values, unknown status,
unknown confidence and missing reasons. Fiscal fields also remain null/unknown.

Each important metric retains units, source, method, status, confidence and a
missing reason. SAIPE point estimates have observed dataset status; this does not
make model-based estimates direct household measurements. The official download
provides rounded 90% confidence bounds. MOE is explicitly calculated as half the
interval width, with original bounds retained. Percentiles are calculated across
all CONUS SAIPE counties with valid values before geometry/grid joins: average
ties, `100*(rank-1)/(n-1)`, singleton 50. Higher poverty and lower income indicate
economic disadvantage; no combined economic score is constructed.

Cache identities bind config, adapter code, raw URLs/checksums, chosen boundary
year and saved-grid bytes/metadata. Cache output checksums are verified before
reuse. The local server can build bounded context from verified local sources,
but cannot acquire data. Oversized grids fail explicitly before loading. A
display filter retains a region only when one positive-overlap county satisfies
every active condition; missing active-filter values do not match. Saved
technical scores, screening and global ranks are not recalculated.

Presentation requests and in-memory context caches include run, displayed
external scenario and boundary year. Future-scenario region IDs use that
scenario's persisted membership rather than baseline region IDs; geography and
2024 SAIPE source estimates remain shared. Unavailable context cannot satisfy an
active filter, and the page always permits clearing retained county thresholds.

Frontend presentation correction (2026-10-04): economic context is filter-only.
Optional thresholds are minimum poverty rate, maximum median household income,
minimum poverty percentile and minimum low-income percentile (percentiles 0–100).
All active thresholds must match one same positive-overlap county. County layer
controls, fetches and rendering are suppressed, including legacy URL selections.
The existing context/layer transport fields remain compatible; there is no wire
schema migration or change to source percentiles, technical outputs or ranks.

## Best fine parent per national region (2026-10-04)

`RegionalConfig` 3.0.0 also accepts `selection: national_fine_region_parents`, likewise bound to
`delivery_version: phase11_national_fine_surface_v1`. No field was added, so existing configurations
serialize identically and keep their binding identities.

In this mode `RegionalRefinementWindows` is **1.2.0**. It keeps the 1.1.0 fields: `fine_selection_rank`
(here the order of the selected parents by best fine value), and `best_fine_score` and the `fine_best_*` IDs,
which are null for a region without a scored member. It adds `fine_region_representative` (the national
representative parent the region would otherwise refine) and `fine_region_selection_basis`
(`fine_surface | representative | representative_unscored`). `national_region_ids_json` lists every
national region the parent was chosen for. The `national_fine_surface` object of `regional_catalog.json`
1.2.0 is unchanged; its `selection_limit` is the budget-derived parent limit, which this mode checks but
does not use to choose parents. Other modes keep windows 1.0.0 and 1.1.0.

The stage manifest stays 1.1.0. It is written as indented strict JSON, with missing values as `null`.

## Additional county model (PR #1 integration, 2026-10-04)

The separately packaged `backend/dataclocator/` model uses its versioned HTTP contract
at `backend/dataclocator/docs/api.md` and `docs/openapi.json`; it does not change any grid
schema or scientific coefficient. Its frontend adapter maps physical distributions and frozen
evidence into optional model discriminants, retains null scalar scores/ranks, and labels county
coverage separately from grid cells. `POST /runs` and `GET /runs/{run_id}` remain county-service
routes; the grid service keeps `/api/search` and its existing contracts. Model changes reset
workspace run/scenario/layer selections so stored results cannot cross model boundaries.

## Nationwide regional map choice (2026-10-04)

Frontend transport **1.7.0** adds optional capability
`nationwide_regional_run_id` (string or null). It identifies a registered completed
real 1 km regional result with a positive extent limit no greater than 20 km,
complete native stages, verified presentation artifacts and valid completed CONUS
parent lineage. The choice prefers `national_fine_region_parents`, falling back
to `representative_parent_cells`; global highest fine-score-window selection is
excluded from this presentation choice. Unscreened national surface output cannot
qualify. Missing fields in older 1.x responses disable the optional action.

Known external deliveries are advertised only after completion checks. Repeated
capability reads preserve the ordering of registered searches. The separate map
choice does not change `latest_run_id`, the scientific request configuration or
the computation baseline. Loading it reads the saved run's own facility,
geography, ranks and provenance without creating a model execution. Counts group
identical candidate geometry across cooling designs and reflect active display
filters. Scientific table schemas and socioeconomic context schema 1.0.0 retain
their existing meanings; the adapter cache revision refreshes transport only.

## Cached regional Grid mode (2026-10-04)

Frontend transport **1.8.0** adds optional capabilities `analysis_modes`,
`default_analysis_mode` and `cached_regional_baseline_run_id`. Available modes
are `cached_regional` and `full_rediscovery`; the page defaults to cached
evaluation when its verified static input cache is ready. Search bodies may
add a top-level `analysis_mode`. Legacy facility-only requests retain the
existing full workflow. The evaluation mode is separate from facility fields.

New fast results carry `analysis_mode: cached_regional`, regional
`selection: fixed_cached_cohort` and `diagnostics_status: NOT_ASSESSED`.
Their cell counts, source lineage, fixed windows, weights, scores and region
geometries describe the submitted facility on the cached universe. They do
not inherit a saved facility's performance or claim new nationwide discovery.
Missing optional fields preserve older 1.x responses and the County adapter.

The standalone production executor `src/dc_locator_fast.py` has its own
content identity outside the in-flight scientific package inventory. Its
outputs record exact existing mathematical-function, policy, environment,
cached-input and submitted-request bindings. Static cache and new outputs
are checksum verified; changed binding identities create new revisions.
This addition does not alter existing scientific table meanings or accepted
phase evidence. New compact/cache artifact contracts are explicitly named
in their file metadata rather than mislabeled as full scientific tables.

Fast execution identity uses the validated facility and active scoring profile;
equivalent integer/decimal representations and reordered object keys share a
calculation. The originally submitted representation remains in the immutable
configuration snapshot. Native clustering/land checks may execute in at most
two processes, partitioned by cooling design and external scenario only after
unchanged global ranking. Results are restored to the native global sort order;
each process retains the 4 GiB memory guard. This execution partition changes no
weights, selection thresholds, grid membership, region IDs or physical values.

## Rediscovery validation contracts (2026-10-04)

Additive and outside the hash-bound model package. `src/dc_rediscovery` reads a completed run and writes
`RediscoveryEvaluatedCell`, `RediscoveryCandidateBlind`, `RediscoveryCandidate`, `RediscoveryCandidateFactor`,
`RediscoveryFacility`, `RediscoveryHub` and `RediscoveryBaselineDraw` tables (all `schema_version 1.0.0`)
with the standard `dc_locator.*` Parquet metadata. It also writes `validation_summary.json` and
`rediscovery_manifest.json` (`schema_version 1.0.0`, `analysis_identity` = sha256 of the configuration,
model inputs, package code and environment). One candidate row represents one 1 km cell with its best
cooling design. Its `grid_id` follows the grid contract, its `lat`/`lon` is the cell-square centre in
EPSG:4326, and distances are spherical haversine kilometres (R = 6371.0088 km). Missing robustness is null
with a reason, never 0. An output folder is reused only with an identical identity and verified hashes.
Otherwise the run is refused. Existing-facility data never enters `src/dc_locator` or the blind table. The
read-only API contract is documented in `frontend/API_CONTRACT.md` ("Rediscovery check").
No existing schema changes.
