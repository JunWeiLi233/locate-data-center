# Methodology

This document explains the geographic, physical, decision, temporal and delivery methods. For output shapes,
see `docs/data_contracts.md`; for what is and is not implemented, see `docs/phase_handoff.md`.

## Scope of Phase 1

Phase 1 builds only the **geography foundation**: shared data contracts (`src/dc_locator/schemas.py`,
reusing `src/dc_locator/provenance.py`), configuration loading (`src/dc_locator/config.py`), the
real/synthetic-data-aware Parquet IO layer (`src/dc_locator/io.py`), and the national + development-area
grid (`src/dc_locator/geography/{boundary,grid,distance}.py`). No screening, physical calculation, decision
analysis, or clustering was implemented in that initial phase. Phase 3 screening and physical calculation
are documented below; accepted decision analysis, clustering, temporal integration and validation also appear below -- see
`docs/specs/master_prompt.md` for the full seven-phase plan.

## 1. Boundary acquisition (`geography/boundary.py`)

The authoritative study-area boundary is the U.S. Census Bureau's GENZ2023 cartographic boundary files
(1:500,000 scale), for two layers:

- `cb_2023_us_state_500k.zip` -- states and state-equivalents.
- `cb_2023_us_county_500k.zip` -- counties and county-equivalents.

Both are public HTTP downloads under `www2.census.gov` (no login, no CAPTCHA, no click-through license;
U.S. Government work, public domain) fetched with the descriptive User-Agent `dc_locator/0.1 (research
prototype)`. `download_conus_boundary_sources()` is idempotent: it compares each cached file's sha256
against `data/raw/census_cartographic_boundary/download_log.json` and skips re-downloading a file that
already matches (AGENTS.md section 4). `load_conus_boundary()` then:

1. Reads both shapefiles directly from their zip archives (`geopandas.read_file("zip://...")`, via the
   `pyogrio` engine -- `fiona` is not installed; `pyogrio` is the declared dependency and geopandas 1.x's
   default engine).
2. Filters out Alaska (`STATEFP 02`), Hawaii (`15`), and the five island territories (`60/66/69/72/78`),
   leaving exactly 48 states + DC (asserted; `BoundarySourceSchemaError` if that count is ever wrong, e.g.
   after a future vintage change).
3. Reprojects both layers to EPSG:5070 (NAD83 / Conus Albers Equal Area).
4. Unions the 49 state/DC geometries (`shapely.ops.unary_union`) into one CONUS boundary polygon, repairing
   a self-intersection from the union (if any) with the standard `buffer(0)` fix.

Cartographic boundary files were chosen over full-resolution TIGER/Line files because they are already
generalized to a scale appropriate for a 10 km analysis grid and are an order of magnitude smaller to
download and process; see `docs/limitations.md` for the precision trade-off this implies.

## 2. Grid generation (`geography/grid.py`)

Given the loaded boundary and `configs/grid.yaml`, `generate_national_grid()`:

1. **Fails loudly** (`GridOriginViolationError`) if any part of the boundary lies west of the fixed origin
   `origin_x_m` or north of `origin_y_m` -- the origin is a constant of the grid definition, never adjusted
   to fit the data.
2. Computes the `(row, col)` range that covers the boundary's bounding box using the grid's own
   `floor((coord - origin) / size)` formula, then builds every cell square in that rectangle in one
   vectorized pass: a `numpy.meshgrid` of row/col indices feeds `shapely.box(...)` with array arguments (no
   per-cell Python loop for geometry construction).
3. Fails loudly (`GridIdOverflowError`) if the real extent needs more row/col digits than
   `configs/grid.yaml:id_row_col_digits` allows, rather than truncating IDs into silent collisions.
4. Uses the candidate grid's spatial index (`GeoDataFrame.sindex.query(boundary, predicate="intersects")`)
   to cheaply discard candidates that cannot possibly touch CONUS, then computes the exact intersection
   geometry/area only for the remainder.
5. Splits candidates into retained (`intersection area > min_intersection_km2`), zero-area touches (always
   excluded), and excluded-by-threshold (counted in the summary, never silently dropped).
6. Derives every `GridCell` column from that intersection: areas, fractions, `is_boundary_cell`, the full
   square's centroid (projected and lat/lon), and a representative point of the *clipped* intersection
   (guaranteed inside CONUS, unlike the centroid of a boundary cell).
7. Attributes state/county by overlaying each retained cell's full square against the state/county layers
   (`geopandas.overlay(..., how="intersection")`), then picking the largest-area match per cell (ties
   broken by lowest FIPS/GEOID) via `_aggregate_primary_and_all`.
8. Assembles, sorts by `(row, col)`, and validates the result: unique `grid_id`, valid geometries.

`select_study_area()` then reduces the national grid to a named development bounding box (`dev_tiny`,
`dev_default`) by testing `national_grid.geometry.intersects(projected_bbox)` -- a pure row filter that
never recomputes an ID or attribute, after densifying the EPSG:4326 box (`shapely.segmentize`, 0.01 degree
steps) so its edges approximate a curve under the Albers projection rather than 4 straight chords.

### Why vectorized, and what is not

AGENTS.md section 7 requires vectorized operations over per-cell Python loops for national-scale data.
Geometry construction, intersection, area, and centroid computation are all vectorized (numpy array
construction, shapely 2's array-input C functions, geopandas spatial-index queries and overlay). The two
exceptions are `grid_id`/`tile_id` string formatting, which are simple per-row `f"..."` passes with no
feasible numpy-only equivalent; at national scale (~80,000 cells) this is on the order of tens of
milliseconds, negligible next to the overlay steps.

## 3. Distances (`geography/distance.py`)

Two correct alternatives to "degrees as kilometres" (AGENTS.md section 6, explicitly forbidden):

- `geodesic_distance_km(_array)`: exact ellipsoidal distance via `pyproj.Geod(ellps="GRS80")`, for
  EPSG:4326 points. Verified in `tests/test_distance.py` against an independently derivable value (the
  ellipsoid's own equatorial circumference formula), not just a re-run of the function under test.
- `planar_distance_km(_array)`: straight-line distance on already-projected EPSG:5070 coordinates, subject
  to a scale-error bound that was *measured*, not assumed -- see the module's docstring for the exact
  `pyproj.Proj.get_factors()` sweep used and its result (point scale factor ranges from about -1.53% to
  +1.55% across CONUS latitudes, exactly 1.0 areal / equal-area everywhere).

## 4. Configuration and IO

`dc_locator.config` retains legacy loaders. Delivery `RunConfig`2.0.0 uses `DeliveryConfig`, referenced
native inputs and accepted facility/design/scenario/constraint/scoring contracts. Unknown settings and
incorrect boolean/numeric types reject instead of silently changing decisions. Historical Phase1
configuration status remains in its completion record; active scientific configurations are implemented.

`dc_locator.io` wraps GeoPandas/pyarrow Parquet IO with the shared file-metadata contract (schema name,
version, data mode, grid definition id, creator) and refuses outright to write `data_mode=synthetic`
anywhere under `data/processed/` (AGENTS.md section 3.6), independently of which code path tries it.

## 5. Command-line interface

`dc-locator build-grid` (and `python -m dc_locator build-grid`) runs the full pipeline: idempotent boundary
download, national grid generation, write `us_grid.parquet`, then write one `us_grid__<name>.parquet` per
`configs/grid.yaml:study_areas` entry. All delivery stages are executable: `ingest` validates acquired
native inputs; `build-features` performs source aggregation; `screen`, `simulate`, `rank`, `cluster`,
`validate` call accepted science/current recomputation; `run` orchestrates them. Stages verify current
input/config/code/environment identities and upstream output hashes before reuse.


## Phase 3: regional screening and annual physical calculations

Geography is read-only input. A100km² search cell can contain a river, protected corner and potential
usable land. Default flood/PAD-US/Aqueduct/transmission/wildfire indicators are informational;
no numeric exposure cutoff is invented. Actual parcel flood/ecology/wildfire clearance, largest
contiguous suitable area, confirmed developable parcel, utility capacity, water strategy and fiber
are separate critical requirements. Missing evidence stays UNKNOWN. The total NLCD suitable-area
proxy is only a regional plausibility check against the explicit facility land assumption.

Each constraint states its unit, operator, threshold or threshold source, basis/rationale, accepted
value statuses and coverage policy. Confirmed evidence defaults to observed/calculated; proxy and
scenario values cannot verify it. Regional total-area plausibility explicitly permits the NLCD proxy.
Calculated confirmed evidence needs a documented method; optional accepted_source_ids narrows sources.
Full source coverage is required by default (1e-6 numerical tolerance); no partial mean is extrapolated.
An informational record has UNKNOWN decision outcome and no threshold, retaining its source value
under evidence_json. Its noncritical status cannot establish parcel approval or exclude a whole region.

A critical FAIL prevents acceptance in both modes. STRICT additionally prevents acceptance on critical
UNKNOWN. EXPLORATORY retains conditional alternatives while all their unknown requirement records remain
UNKNOWN. No score can compensate a hard failure. Empty eligibility is valid and is exported.

Annual formulas, with E in MWh: E_IT=peak_IT_MW×load_factor×modeled_year_hours; E_facility=E_IT×annual_PUE;
C_electricity_kg=E_facility×kg_CO2e_per_MWh; tonnes=kg/1000. Site consumption m³=E_IT×consumption_WUE_L_per_ITkWh;
litres=m³×1000. Generation-water m³=E_facility×generation_consumption_L_per_kWh only with an explicit
factor and generation geography. Withdrawal factors populate distinct withdrawal fields. Local
Aqueduct stress is never applied to electricity water without generation geography. Missing factors
stay null, even when modeled IT load is zero; known-factor zero-load calculations are zero.

Complete cooling alternatives specify heat transport and heat rejection. Current annual PUE/WUE are
constant project-assumption scenarios; neither geographic cooling efficiency nor hourly weather is
modeled. Annual PUE cannot verify peak connection demand. Peak demand=peak_IT_MW×verified_peak_PUE only
with separate design-day evidence; current peak demand and utility capacity are UNKNOWN.

Opening2030 uses eGRID2023 CO2e unchanged only under the explicit historical_static_2023 external
scenario. The modeled carbon factor is scenario status; its original historical proxy evidence is
retained, and annual electricity emissions are calculated. This is not a forecast or lifetime footprint.
The25-year lifetime is metadata; no unsupported future/lifecycle multiplication is performed.

Callable APIs: model.screening.screen returns requirements, eligibility and summary;
model.physics.simulate returns one annual row per grid_id×design_id×scenario_id for diagnostics.
model.physics.run_phase3 reads compatible1.1+ geographic/provenance schemas, checks matching grid/mode
metadata, and writes the three Phase3 tables plus summary without changing geography. Decision analysis
must join screening_eligibility and preserve conditional/unknown evidence.
# Phase 4 decision policy and investigation regions

`configs/scoring_profile.yaml` was frozen before the first ranking, with byte SHA256
`3f7c2102e9212008ee4d1082ab679ec8deedd94851a10a3127da81369a2481f0` recorded in
`docs/phase_records/phase4_profile_predeclared.json`. The illustrative development profile is
`reduced_geography_annual_v1`1.0.0. References are decision policies, not engineering limits.
Four equal parent groups have weights0.25. Water has two explicit local weights0.5 each;
the global leaves are electricityCO2e0.25, site consumption0.125, local water stress0.125,
transmission proximity0.25 and suitable-land fraction0.25. Equal importance is a transparent
baseline preference, not an empirical result.

| Leaf | Physical unit | Direction | Fixed low/high |
|---|---|---|---|
| Annual electricity CO2e | tonnes_CO2e | minimize |0 /1,000,000|
| Annual site water consumption | m3_consumed | minimize |0 /1,000,000|
| Local baseline water stress | score_0_to_5 | minimize |0 /5 native score|
| Mapped transmission distance | km | minimize |0 /50|
| Potentially suitable land | frac | maximize |0 /1|

For a maximizing metric, value=`100*(clip(raw,low,high)-low)/(high-low)`; minimizing
uses100 minus that value. Every raw value, unit, status/confidence, source evidence and clipping
flag is retained. Constant observed columns retain the declared function's value, not an arbitrary
relative score. Invalid evidence or missing required values make the alternative UNRANKED with
unchanged full-run weights. All active metrics remain required even when their weight is zero.
The profile checks nested carbon source evidence (`SRC2ERTA`, kgCO2e/MWh input), local coverage,
status and units. Site consumption is never substituted by withdrawal. Inventory proximity has
no areal coverage requirement and remains a low-confidence proxy.

User and AHP preferences apply to the four active parent groups and multiply the declared local
weights. A flat profile requires explicitly separate single-leaf groups and `weight_scope: leaves`;
changing method cannot silently discard the water hierarchy. AHP computes the principal right
eigenvector and CI/CR, preserving the original matrix. Its RI table is R.W.Saaty1987§4,p171,
sample500,n1–10 (version`saaty-rw-1987-p171-500-v1.0.0`); detailed provenance is in
`docs/research/phase4/ahp_ri.md`. CR<=0.10 is a configurable review convention. Inconsistent
judgments block MCDA until revised or explicitly recorded as provisional. No judgments were
supplied in the real baseline; the result uses equal groups and exports null off-diagonal
judgments in an AHP template with definitions, fixed references and observed ranges.

Pareto compares raw physical objectives, separately by external scenario, independently of
preference weights. Other is no worse if each higher-is-better objective is >=candidate-tolerance,
and strictly better if any is >candidate+tolerance. Absolute numerical tolerances are1e-6 tonnes
andm3,1e-9 for stress/km/fraction; relative tolerance0, all project numerical policies. Failed,
strict-unknown or incomplete alternatives are NOT_ASSESSED. Only frontier index0 is calculated;
dominated rows have null pareto_rank and remain stored. Block256 comparisons bound working arrays
to O(block²×metrics), not nationalN² memory; worst-case computation remains quadratic and national
runtime is unvalidated.

MCDA exports each weighted contribution and full weights. Score-descending ties use grid_id,
design_id,scenario_id; ranks are separate per scenario. Exploratory ranks carry CONDITIONAL and
critical_unknown flags, never accepted parcel status. The frozen region policy selects ceil25%
within each design/scenario, with deterministic ties, then forms rook-connected components using
the checked EPSG5070 lattice (`maxy+row*size=origin_y`). Different designs/scenarios and disconnected
cells never merge. Each region stores actual evaluated representative (highest score, same tie
rule), physical metrics/assumptions/evidence/contributions/Pareto/screening flags, member IDs,
suitable-area proxy and member metric distributions. Region geometry is the union of full grid
search squares; the centroid describes that search zone and is never an approved construction site.

Energy/carbon and area/fraction duplicates are excluded. Temperature receives no bonus because the
annual PUE/WUE scenarios are constant. Verified WRC climate resilience, future carbon, generation
water and construction/embodied carbon are omitted from this reduced profile, with reasons stored
in the config/run snapshot. These omissions and critical screening UNKNOWNs limit interpretation.

## Phase 5 extension

Cached native adapters append context to the same geography component; acquisition remains separate.
The model extends the accepted physics/decision APIs through explicit temporal and lifecycle tables.
Each prior baseline artifact is required and checked for identical bytes on rerun. Twelve enhanced
profiles were hashed/dated before future ranking. Criterion IDs, hierarchy, weights, normalization
and selection policy are matched; only the disclosed future-water source/time binding changes.
Every pathway/native window is separately ranked, with missing-required metrics unranked and full
preference weights unchanged. Native expanded context never automatically becomes a weighted metric.

Operating years are exactly opening through opening+lifetime-1. Explicit project extension repeats
the opening-year historical-static physical scenario for25 years2030..2054, each with8760 modeled
hours; without it later years are UNKNOWN. Aqueduct2030/2050/2080 trend windows2015–2045/2035–2065/
2065–2095 are stored once, not interpolated/copied annually. Requested2040 is unsupported. NASA
model/member/SSP/year context retains an independent source-context identity, never an assumed
coherent weather pairing or cooling response. Site/generation consumption and withdrawal stay distinct.

Lifecycle quantities/factors must have compatible units, product identity and accounting modules;
freight uses explicit mass/route/mode factors with included-transport duplication checks. No density,
inventory, EPD or expert preference is invented. Full total requires all five component boundaries;
electricity alone is a named partial subtotal. Missing components remain UNKNOWN rather than zero.
Detailed source inspection, formulas, units, accounting modules and file-contract checks are in
`docs/research/phase5/temporal_lifecycle.md` and the updated contracts/dictionary.

## Phase 6 validation protocol

Phase 6 is a prospective, versioned validation exercise. Before any new feature value or ranking is
read, a geometry-only rule selects a 25-cell EPSG:5070 block outside the inspected 42-cell development
set and at least 50 km from it. A separate 40 x 40 km footprint is preregistered as sixteen 10 km cells
and four 20 km cells. The selection manifest fixes IDs, row/column indices, bounds, geometry hashes,
source inputs, and the selection algorithm. A freeze manifest then hashes every model/config/test/
method document and input, saves a restorable source/config snapshot, and binds the full-suite evidence.
Any change after prospective feature inspection requires a new evaluation version and freeze.

The sensitivity runner freshly calls screening, physical simulation, and decision scoring for every
alternative in every case. The preregistered cases are the accepted BAU-2030 baseline; four group-weight
policies; paired PUE, WUE, load, historical-carbon and regional land-threshold stress cases; eight native
Aqueduct pathway/milestone contexts; strict screening; and one ablation for each scored parent group.
Carbon multipliers operate on an ephemeral scenario input before simulation, retain the original 2023
eGRID source/year, and are labeled project assumptions rather than publisher observations or forecasts.
Future-water cases are ranked separately within their native external context. No case selects favorable
weather, pools scenarios, edits an accepted score, or reweights around missing candidate evidence.

Top-k stability uses exact k=10 after the declared score-descending and identity tie rule. Within one
scenario it uses the full grid/design/scenario key; cross-context correspondence uses grid/design only
after each context has been evaluated separately. Per-alternative rank ranges retain ranked and unranked
case counts. Fixed-region summaries use the accepted baseline memberships and retain every member;
min/max ranges describe ranked members, while the mean is null unless all original members rank.
Group ablations remove the complete group and equalize the remaining parent-group weights globally,
with original and retained weights exported.

The prospective block reruns the same source aggregation and model stages. Resolution sensitivity also
reruns native aggregation and the complete pipeline at both resolutions over the exact same projected and
Census-intersection footprint. It compares selected search-area intersection, union, and Jaccard by design;
it never pairs ranks across unlike cell IDs. Climate-to-cooling and construction-lifecycle sensitivity are
declared inactive because no defensible response function or real inventory/factor set exists. Software
properties and source/identity/coverage checks are validation evidence; without independent compatible
facility observations they do not establish prediction accuracy or engineering validity.

## Phase7 orchestration and current-run verification

Delivery reuses accepted scientific APIs without changing source semantics or scoring bounds. Run stages
are actual operations with content-bound cache manifests. Real geographic features use Census study
intersections and native query/domain masks, while original full-square geometries support adjacency.
Native/core/expanded/future aggregation remains separate from model decisions. `cluster` reruns adjacency
from persisted ranked alternatives; actual representatives preserve full row quantities/contributions.

A stable analysis ID derives from complete working model/config/source/grid/environment content; execution
UUID/time are separate. Before and after stages, input identity and output checksums are verified.
Current validation independently reruns physics, screening and decision analysis and exactly compares
persisted normalized/Pareto/ranked/regions/membership/weights. Serialization dtype/sequence differences
are tolerated only when scientific values/geometry/identities are unchanged. Tampered values, including
boolean substitutions for numeric quantities, reject. Configured scalar/weight/screening cases recompute
all alternatives, including those excluded at baseline; no winner-only sensitivity occurs.

All native future water contexts are separately rebound to matching predeclared profiles/windows.
2040 remains unsupported; NASA source context stays independent. Annual historical electricity/carbon
reuse and constant PUE/WUE are explicit project assumptions. Lifecycle inventory/transport/accounting
module absence propagates UNKNOWN. Current sensitivity does not manufacture expert judgments, engineering
thresholds, climate-cooling response or external accuracy. Fixed baseline members remain fixed; newly
selected future regions have no matched fixed-region stability claim.
