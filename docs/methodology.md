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
# National discovery extension — 2026-10-03

The new national delivery applies the existing deterministic decision model to a complete CONUS
grid at 50 km resolution. It changes the geographic comparison domain, not the numeric scoring
weights, required metrics, normalization references or hard requirements. This resolution bounds
processing cost and native 30 m raster windows; it is an explicit project resource assumption.
National real preflight requires all 48 contiguous states and DC in the grid's jurisdiction union.

Official Annual NLCD 2024 C1.1 national classes are reprojected from WGS84 Albers to EPSG:5070 at
30 m with nearest-neighbor resampling, then summarized by the existing exact projected pixel-area
intersections. Source/output checksums, CRS, nodata, method and memory limits accompany the derived
cache. Vector overlays are prepared in envelopes no wider than 250 km, with at most 625 cells.
The full national nearest-infrastructure inventory and eGRID workbook are reused across those
tiles. Geography caches retain source/code/grid identity and exclude facility preferences.

The initial national baseline computes the original required ranking evidence and leaves optional
cached sources explicitly uncomputed. EXPLORATORY may retain critical UNKNOWN screening evidence
conditionally; incomplete required ranking metrics remain UNRANKED and hard failures are excluded.
STRICT remains the default command mode. It cannot turn missing parcel, utility, water or fiber
evidence into PASS. No rule forces state quotas or geographically dispersed winners.
# Regional refinement revision (2026-10-03)

The initial national discovery uses50km cells. Its unrestricted connected
components can span several states, so their geometries are insufficiently
local for regional investigation. The approved refinement evaluates the full
representative parent cell of every discovered region on a fixed 1 km lattice.
Cooling alternatives sharing a parent are deduplicated; no city/state quota
or centroid-centered assumption chooses the fine geography.

Each child receives fresh native source aggregation, eligibility and physics.
Fixed normalization references and complete preference weights remain the same.
All evaluated children are ranked together within their external scenario;
batch ranks and batch frontiers are never promoted to global results. An exact
bounding tree accelerates Pareto comparison using conservative pruning and the
existing pairwise tolerance rule; every comparable row can be a dominator.

Final regional polygons join selected adjacent cells within deterministic 20 km
global lattice partitions. The projected span bound is a documented project
assumption and is independent of map zoom. Investigated coverage is partial:
selected full representative parents are refined, while remaining shortlisted
parents await expansion. The catalog reports both areas and lineage explicitly.
# Submission presentation and heat-host scenarios — additive 2026-10-03

`submission` verifies saved output identities and presents stored decisions; it
does not rerank, choose an external scenario, infer missing weights, or revalidate
archived science against changed working code. It selects the lowest persisted
rank among exported region representatives in one explicit scenario and displays
two other distinct representative cells. Paired annual cooling differences use
the same cell and scenario. All important missing quantities remain null, and
source acquisition is reported separately from actual feature computation.

Optional supplied heat-host inputs calculate available thermal energy as
`e_it_mwh * recoverable_fraction * (1 - distribution_loss_fraction)`, cap delivery
by compatible annual heat demand, then subtract complete incremental auxiliary
electricity emissions from displaced heating. This is a separate signed scenario
comparison with explicit input basis, not a change to the facility carbon footprint
or scored profile. Missing input is never zero. The proposed operating roadmap
covers diligence, commissioning, adaptation, replacement inventories and retirement,
and does not multiply a historical annual carbon result into a future forecast.

## Existing-facility diagnosis and regional land support — 2026-10-03

The Cleanview public operating listings are an external diagnostic reference,
not labels for an optimum sustainability score. Public capacity-selected cards
are cached with raw-page checksums; exact county/state text is matched to Census
administrative identifiers. The comparison uses every intersecting whole cell
and reports conditional ranges separately by cooling design and scenario.
Absent fine-grid coverage is outside the evaluated domain. Exact site location,
measured operating energy/water/carbon and matching facility specifications are
unavailable, so facility scores, physical error and classifier accuracy remain
unknown. Existing development reflects other objectives and cannot determine
the model's weights or engineering coefficients.

Regional searches use `multi_cell_region` land support. A positive classified
area below facility demand in one cell becomes critical UNKNOWN, since adjacent
cells may jointly contain enough potential land. Zero area and other genuine
failures still exclude alternatives; STRICT excludes the unresolved case.
After bounded components form, the complete member-area sum is screened against
facility demand. A known insufficient component is excluded; an incomplete sum
stays UNKNOWN. A sufficient sum verifies only total-area plausibility and never
parcel contiguity, availability or permission. Every initial component retains
an audit row, including excluded regions. No Cleanview-derived value alters
scoring, normalization, source features or physical calculations.

# National 1 km fine surface for refinement selection — Phase 11 (2026-10-03)

Representative selection refines one 50 km parent per national region (61 of 3,384 parents, about 2% of
CONUS), chosen from 50 km box values. Measured on the 61 fully refined parents of the accepted
`runs/regional_refinement_v4`, a 1 km cell's exact decision value ranks against the value it inherits from
its 50 km box with Spearman rho 0.256. National transmission distance is measured from the nearest edge of
each 50 km polygon, so 94% of national cells read 0 km, and 1 km values inside one box spread a median 9.7
decision points between its 10th and 90th percentiles.

The optional Phase 11 mode (`selection: national_fine_surface`) values every retained CONUS 1 km cell
(about 8.46 million) before choosing parents. It computes only the five profile inputs, from the same
source files and formulas as regional refinement, vectorized per 50 km window:

- suitable-land share and NLCD coverage with exact pixel-area weights on the prepared EPSG:5070 30 m
  raster: separable x/y pixel overlaps for whole cells, the land-cover adapter itself for coast and border
  cells clipped to the CONUS study polygon;
- transmission distance from each cell's study polygon to the nearest mapped line;
- basin water stress and eGRID CO2e intensity as area-weighted means, with coverage, over key-dissolved
  polygons clipped to the window first; overlaps between keys are preserved as in the adapters.

Annual facility energy and direct site water are design/scenario constants of the national physics (annual
PUE and WUE are scenario values), so carbon scales with grid intensity; the stage refuses to run if either
varies by location. Fixed-reference normalization and the profile's resolved weights then give each
cell/design/scenario a decision value. Any metric that is missing or below its declared minimum coverage
leaves the alternative unscored, never zero. The surface applies no screening.

Parents are ranked by their best fine value over designs and scenarios (ties by `grid_id`). The
`floor(maximum_refined_cells / cells per parent)` best parents are refined exactly as before: fresh native
evidence, screening, physics, global ranking, Pareto comparison and bounded clustering. The surface only
chooses where to look; every published regional value comes from that refinement.

Against `runs/regional_refinement_v4` the surface reproduces the refinement's 152,500 cells and study areas
exactly; land share and transmission distance match to floating precision; eGRID intensity to 1.6e-5
kg/MWh. Basin stress differs by at most 0.0011 (0–5 scale) in 146 cells, because the adapter clips
basins per tile in native longitude/latitude before projecting, which densifies long straight basin edges
differently; the surface projects whole basins. All 301,900 rankable alternatives are scored, with Spearman
rho 0.999999999998 and a maximum difference of 0.0026 decision points.

The numeric-only draft has been superseded by evidence-bearing feature/selection methods v2.
The revised stage checks source/physical metadata as well as numeric coverage. It weights eGRID
native pound rates before the exact lb-to-kg conversion and sums individual polygon shares before
capping coverage, matching the native formulas. Aqueduct loading uses a densified transformed
CONUS envelope so curved projected edges are bounded. Native tile clipping and full-source
projection can still produce small geometric/floating differences; full published regional
results are independently recomputed with the native adapters. The current bounded source
comparison and its failed/revised evidence are in `runs/fine_surface_preflight_v1/`;
the earlier draft comparison above is not acceptance of this revised nationwide stage.

Cleanview is used to diagnose coverage of reported existing-center counties and explain area
scores. A county intersection is not an exact facility match. Reference records do not enter grid
generation, parent selection, physics, screening, weights or coefficients. National fine-surface
valuation and fully screened regional refinement have separate coverage counts.

## Separate county economic context

County economics attaches after geography/model execution to the actual saved
grid cells. Reproject the authorized Census county geometry to EPSG:5070,
dissolve fragments by five-character GEOID and use a spatial index plus bounded
vectorized intersections to retain every positive-area cell/county pair. Areas
use full saved cell geometry, even where generalized coastlines leave uncovered
area. Coverage diagnostics expose these gaps without rescaling known shares.
Saved region membership supplies the presentation grouping; centroids never
assign a region to a county.

Join official 2024 SAIPE poverty and income estimates by GEOID. The default 2025
and selectable 2023 county boundaries are generalized 1:500,000 cartographic
files, explicitly authorized by the user after the requested 2024 TIGER/Line
archive was found absent. The estimate year remains 2024. Retain point estimates,
rounded 90% bounds and calculated interval half-widths. Qualitative medium
confidence is a documented project assessment separate from the statistical
90% interval. Percentiles use the full valid CONUS SAIPE county universe before
spatial restriction, with average ties and endpoint scaling to 0–100.

Optional poverty rate, income, poverty percentile and low-income percentile
thresholds under Filter areas describe economic need; county map overlays are
not offered. Percentile thresholds compare supplied national county values,
and all four filters use the same county-overlap matching rule.
They do not enter screening, technical metrics, MCDA, AHP, clustering or
rank calculation. A display filter matches any overlapping county that meets
all active conditions in that same county; missing values cannot satisfy an
active condition. Raw global ranks remain visible after filtering. Fiscal
fields prepare a later GEOID join but contain no estimated tax revenue, public
cost or incentive values in this delivery.

## Best fine parent per national region — Phase 11 (2026-10-04)

Ranking parents by their best fine value concentrated the completed `runs/national_fine_regional_v1`: 50 of
its 61 parents are in New York. eGRID carbon intensity, the heaviest-weighted regional factor, is uniform
within a subregion, so near-identical high values cluster in one place.

The second Phase 11 mode, `selection: national_fine_region_parents` (`configs/run_regional_fine_region.yaml`),
keeps national discovery's regions as the unit of choice and uses the fine surface only inside each region.
Regions that share a representative parent (the cooling-design variants of one national region) count as one.
In each region the member parent with the highest best fine value replaces the 50 km representative. If the
representative ties for the best value it is kept; if several other members tie, the smallest `grid_id` wins.
A region with no scored member keeps its representative (`representative_unscored`). A parent chosen by more
than one region is refined once and lists every region. The refined-cell budget is checked as in the other
modes, with no silent truncation. Refinement, screening, ranking and clustering are unchanged.

In both fine modes the national surface is built in a spawned child process. Its national source heap is
released when the child exits, so the regional process's lifetime peak working set covers refinement alone;
the child enforces the same 4 GiB bound. An identical completed stage is reused in-process.

## Fast fixed regional cohort evaluation (2026-10-04)

The user authorized a fast default that re-evaluates the facility and preferences
within the already evaluated nationwide representative windows. Its cohort is
the complete 152,500-cell native domain of `runs/cleanview_regional_v2`, not a
list of hand-picked cities or representative cells alone. Its 61 windows are
fixed across facility requests. A separately selectable full rediscovery repeats
national selection and may identify different windows.

The separately content-bound production runner `src/dc_locator_fast.py` verifies
the frozen native evidence, current mathematical functions, policies and
environment. An immutable consolidated cache retains stable grid IDs,
geometry, source-carbon evidence, prepared static metrics and native screening
outcomes for both modes. Every use verifies its content checksums. Cache
preparation is timed separately from a changed facility evaluation.

Facility-dependent outputs are recomputed from native inputs using
`calculate_annual`; they are never obtained by scaling an old result. Fixed
reference normalization, complete preference weights, exact global MCDA/Pareto,
region clustering and region land support use existing mathematical functions.
Screening reuse requires the unchanged minimum-land policy and frozen cooling
designs with unverified peak demand; unsupported dependencies fail explicitly.
UNKNOWN remains unknown, hard failures remain excluded, and strict screening
can produce an empty result.

The new ranking universe is the fixed cached regional cohort. Published
regions retain 1 km cells and at most 20 km spans along each EPSG:5070 axis.
Historical-static carbon reuse remains an explicit scenario rather than a
forecast. Broad sensitivity and diagnostic case reruns are not assessed by
this faster mode. Its completion metadata does not claim nationwide
rediscovery or acceptance of a new scientific phase.

## Post-hoc rediscovery validation (2026-10-04)

The separate package `src/dc_rediscovery` (see `docs/rediscovery_validation.md`) evaluates every national
1 km cell of a completed run with the model's own `score_window`. Per-criterion values must recompose the
model score exactly in every row group. The package then ranks cells (ties by grid_id) and keeps the
strongest cell of each neighbourhood with greedy non-maximum suppression: candidates are at least 25 km
apart, measured as haversine distance on R = 6371.0088 km. The blind candidate table is hashed before an
external facility inventory is opened. The package then measures nearest-facility distances,
HitRate(r, N), facility and hub recall, and presence–background AUC, and compares them with 1,000 seeded,
equally spaced random controls (area-uniform, and near-transmission land). A candidate is validated at
25 km or less, emerging beyond 50 km and otherwise unresolved. Monte Carlo robustness attaches through a
provider interface, or stays null. No threshold or weight is fitted to the facility inventory, and the
deterministic model's scores, ranks and outputs are unchanged.
