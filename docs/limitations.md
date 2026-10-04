# Limitations

Specific caveats on supported geographic, model, temporal and delivery execution. See `docs/phase_handoff.md` for the
authoritative status/blockers list; this document is the narrative explanation behind those entries.

## Boundary precision

The CONUS boundary is the Census Bureau's **cartographic** boundary file (1:500,000 scale), chosen for
Phase 1's 10 km grid (see `docs/sources.md` for the justification). It is generalized for thematic mapping,
not a survey-grade or legal parcel boundary: small islands, narrow spits, and fine coastline detail below
roughly the scale of a 10 km cell are smoothed away. A future phase needing finer boundary detail (e.g. a
sub-kilometre grid, or precise coastline-adjacent siting) should switch to the full-resolution TIGER/Line
boundary files and regenerate the grid, recording the source/version change as a migration note in
`docs/data_contracts.md` (AGENTS.md section 9) -- cell IDs are stable under a resolution change but a
boundary-source change can shift which boundary cells are retained.

## County-attribution edge case is supported but unobserved

`GridCell.county_geoid_primary`/`n_counties=0` exists to handle a cell that intersects the state boundary
layer but no polygon in the independently-generalized county boundary layer (a coastline-generalization
mismatch between the two files). This did **not** occur anywhere in the Phase 1 national run (zero of
79,888 retained cells had a null county; see `docs/phase_handoff.md`). It remains untested against a real
occurrence -- only via a direct schema-level unit test (`tests/test_schemas.py::TestGridCell::test_allows_null_county_with_n_counties_zero`)
that constructs the null case by hand. A future, finer-resolution or different-vintage run could exercise
this path for the first time; if it does, verify the resulting `GridCell` rows manually at least once rather
than assuming the existing code path is correct merely because it is exercised.

## Grid-generation runtime at the 10 km production resolution

A full national `build-grid` run at the default 10 km resolution took approximately 7-8 minutes of wall
time end to end (boundary load, ~135,000-candidate intersection test, state/county attribution overlay,
GeoParquet write for national + 2 development areas) on the development machine (16 cores, 31 GB RAM
shared with other work), peaking at roughly 460 MB resident -- comfortably inside the ~4 GB budget
(AGENTS.md section 7), but noticeably slower than, for example, the `dev_tiny` selection alone would
suggest. The dominant costs are the exact-intersection computation against the unioned CONUS boundary and
the `geopandas.overlay` calls against 49 states and ~3,100 counties; neither step is parallelized across
the machine's 16 cores (geopandas/shapely's vectorized calls are single-process). This was judged acceptable
for a one-time, cached-afterward generation step rather than something requiring interactive speed, and was
not further optimized in this phase to avoid scope creep beyond "generate a configurable grid" -- a future
phase that needs faster iteration at national scale (e.g. repeated regeneration during Phase 2 adapter
development) should consider tiling the overlay by `tile_id`, using `joblib`/`multiprocessing` across tiles,
or caching the state/county attribution step separately from geometry generation.

## Why the automated test suite uses a coarser resolution for its one true end-to-end test

`tests/test_cli_build_grid_real.py` exercises the full `dc-locator build-grid` CLI pipeline (download-cache
check through GeoParquet write) against the real, cached Census boundary -- but at a 100 km cell size, not
the production 10 km default, specifically so the test suite runs in seconds rather than minutes. This is a
deliberate trade-off: it is the same code path and the same real data, just a coarser instance of the same
algorithm, so it still catches a real regression in boundary loading, CRS handling, the overlay joins, or
GeoParquet metadata -- but it does not, by itself, prove the 10 km production outputs are correct at that
specific resolution. `tests/test_grid.py`'s fully hand-calculated synthetic fixture is resolution-independent
or by design (it tests the algorithm's formulas directly, at a contrived tiny scale, which is the stronger
check for correctness); the coarse real-data CLI test is the integration check that the real Census data and
the real CLI wiring work end to end. The actual 10 km `data/processed/us_grid*.parquet` deliverables were
generated once, separately, by running `dc-locator build-grid` directly (commands recorded in
`docs/phase_handoff.md`), not by the automated test suite.

## Phase 2+ source data acquired ahead of Phase 1 acceptance

`data/raw/` already contains cached downloads for several Phase 2 sources (EIA Energy Atlas, NOAA/NCEI
climate, USFS wildfire risk, USGS Annual NLCD, USGS PAD-US, WRI Aqueduct 4.0) with `download_log.json`
manifests, alongside Phase 2 research notes under `docs/research/phase2/`. This Phase 1 fix pass did not
audit those files' currency, completeness, or correctness -- that is explicitly out of scope for a Phase 1
geography-foundation fix and belongs to whichever agent builds the Phase 2 adapters, per AGENTS.md section 9
(a phase is accepted, and the next phase begins, only after the technical lead inspects code and outputs and
runs the test suite). Flagged here, and in `docs/phase_handoff.md`, as a fact for the technical lead to be
aware of, not as something this phase resolved.

## Historical Phase1 model boundary

At Phase1 acceptance, `src/dc_locator/model/` was an empty geography-only-phase placeholder and only
GridCell had real outputs. Later accepted phases implemented screening, physical calculations, decisions,
clustering, temporal/lifecycle context and validation. Phase7 now executes those APIs through all nine
commands. The earlier statement is a historical phase boundary, not the current implementation status.
# Phase 2 limitations (2026-10-03 UTC)

- Real geographic features cover42 development cells only. The79,888-cell national grid exists,
  but national source acquisition and source-complete analysis have not been executed. Bounded
  tiling/resume are implemented and tested; full national runtime is unvalidated. Partial-source
  means carry coverage and must not be treated as complete observations in later model scoring.
- The Phase1 Census study-intersection is administrative area including water. NLCD-derived land,
  water and non-water/ice/wetland proxy areas are separate. The proxy does not establish usable
  land, ownership, environmental permission or development feasibility.
- NLCD public service2024 clip differs from latest authoritative Collection1.2 bulk mosaics. It
  contains0/off-legend artifacts that are masked. Official national acquisition remains manual
  where ScienceBase presents CAPTCHA; no bypass was attempted.
- WRC public ImageServer exports are acquired but **not analyzed**: packed U16 scales and absent
  nodata have not been independently verified. BP0..35 cannot be interpreted as probability and
  is UNKNOWN invalid_source_value. The separately observed WHP2023 indicator is a different
  product and never fills missing WRC probability/conditional flame length.
- FEMA Availability is distinct from known T/F hazard classification. U/D/open water and missing
  polygons do not prove safety. Queried empty availability can be0 only inside the recorded query
  footprint; broader/partial-query geography remains UNKNOWN.
- eGRID is2023 historical generation average, carbon is CO2e total-output rate fromSRC2ERTA.
  Geographic primary/multiple-subregion association cannot identify the actual utility supplying
  a future site. No future/marginal emissions or firm electricity capacity are inferred.
- Aqueduct basins model regional baseline ratios/scores/categories, with explicit-9999 missing,
  valid-1 category and9999 severe scarcity. It is not a committed water supply. Ordinary ratio
  means exclude9999 and carry their own limited coverage; scarcity area remains visible.
- NOAA annual1991–2020 normals are coarse1/24degree geographic grids, not hourly design weather,
  single-day extremes, wet-bulb observations or an operating-year cooling simulation.
- PAD-US GAP1+2 overlap uses flattened analysis inventory. It does not establish a parcel's
  environmental approval or protected ownership; GAP3/4 remain separate. Coast/source coverage
  remains visible. Large national raster payloads are not extracted.
- EIA transmission map is an archived2024 layer; plants are202502 and pipeline vintage is
  unverified. Polygon-to-map proximity is a proxy with ~1.6% projection scale uncertainty;
  no line capacity, queue access, transformer availability or utility connection is confirmed.


## Phase 3 model limitations

Current results cover42 development cells only. STRICT accepts none because critical parcel, contiguous
land, utility capacity, verified peak facility demand, water supply/withdrawal strategy and fiber evidence
are missing. EXPLORATORY alternatives are conditional regions for investigation, not approved parcels.
Whole-cell hazard/ecology indicators are informational because regional overlap cannot prove parcel
impossibility or clearance. No regulatory or scientific cutoff is claimed.

Annual PUE/WUE constants and the100MW specification are explicit project assumptions. Dry zero cooling
water is an ideal assumed boundary, not a measured total-site water requirement; sanitary/construction
water is outside that boundary. Tower consumption does not establish withdrawal or supply needs.
Grid electricity water remains UNKNOWN. Future carbon is a historical-static assumption, not forecast;
annual electricity CO2e is not lifecycle carbon. Peak-demand verification is unavailable.
# Phase 4 interpretation and scale limits

The first locator evaluates42 actual Texas development cells×two assumed cooling designs in
one historical-static external scenario. Its two exploratory search zones are conditional on
unverified critical parcel/power/water/fiber requirements. Strict screening produces no accepted
ranking or region. The reduced score excludes verified wildfire/climate resilience, future
grid carbon, generation water and construction/embodied emissions. The predeclared normalization
references and group/local weights are project preferences, not engineering or scientific claims.

No AHP judgments were supplied: equal parent groups are used and a blank template is exported.
The available RI source content is verified via a primary-article transcription; the original
publisher PDF was unavailable. AHP consistency does not establish stakeholder validity.
Block-based Pareto bounds temporary comparison memory but remains worst-case quadratic in time;
the runner retains wide diagnostics/evidence in memory. National Phase4 runtime/peak RAM are
unvalidated. Region unions contain full square search areas, and summed suitable area can be
fragmented or contain developed land; neither centroid nor representative cell is an approved parcel.

## Phase 5 limits

The enhanced run still covers42 development cells. Native context does not verify utility capacity,
parcel flood/ecology clearance, contiguous land, water supply or diverse fiber. Strict results stay
empty; exploratory regions remain conditional. Scenarios retain each water pathway/window, including
unsupported2040 UNKNOWN diagnostics. Matched preferences change only the predeclared water binding.
Aqueduct trend context is not annual parcel supply. Native NASA model/member/ssp245/2030 context is
independent of the water pathways and supplies no engineering cooling response or ranking bonus.

Lifetime electricity repeats historical eGRID2023 only through an explicit project extension;
it is neither a future/marginal factor nor full operations. Configured8760 modeled hours do not
vary with calendar leap years. Real material/equipment/EPD/freight/replacement/endoflife inventories
are absent and remain UNKNOWN; full lifecycle is null. Synthetic examples are confined to tests.
National coverage/runtime/peak RAM have not been validated. Complete period/accounting policies and
known source limits are in `docs/research/phase5/temporal_lifecycle.md` and native-source research.

## Phase 6 validation limits

The 25-cell geographic holdout is prospective with respect to model feature and ranking inspection, but it
uses the same cached source products and the same regional development domain. It therefore measures
software/data behavior under a new location block, not generalization to the United States or future source
conditions. No independent, system-boundary-compatible facility measurements, utility confirmations,
parcel surveys or engineering benchmarks are available. Accuracy, calibration, causal effects and site
feasibility cannot be estimated. Every physical, screening, future-water, ranking and region module remains
externally unvalidated even when its software properties and joins pass.

Sensitivity bounds are disclosed project stress assumptions, not empirical confidence intervals. Historical
eGRID2023 multipliers are counterfactuals, not grid forecasts. Aqueduct cases retain native pathways/windows
and do not optimize over weather. Land-threshold results concern a regional mapped proxy, not contiguous
buildable land. Group ablations redistribute all removed weight to retained groups globally, so rank changes
describe that policy change rather than group importance. AHP ratio fixtures test mathematics only and are
not stakeholder judgments.

The equal-footprint 10/20 km comparison reruns source aggregation, but only one 1,600 km² block is tested;
grid effects elsewhere remain unknown. Climate-to-cooling response is inactive because no defensible
coefficient exists. Construction/lifecycle sensitivity is inactive because real inventories, factors and
routes are absent. UNKNOWN inputs remain UNKNOWN. National runtime/memory and production source refreshes
remain outside Phase 6.

## Phase7 delivery scope and current evidence

Default real STRICT outputs are valid empty because critical parcel/contiguous-land/power/water/fiber
requirements remain UNKNOWN. Exploratory alternatives are conditional, including every reported
search region. The delivery preflight rejects national feature/model requests before allocating a
national enhanced table. It permits national grid geometry separately; source coverage and national
vector-memory feasibility remain unverified. The declared1000-cell run budget is a project execution
policy, not an engineering threshold or proof of source coverage elsewhere.

Current validation freshly recomputes the actual facility/design/profile/source context and checks the
persisted baseline tables, then runs only declared sensitivity cases. Historical Phase6 freeze,
prospective holdout and equal-footprint resolution evidence remain unchanged and reference-only for
this new delivery revision. A new current prospective holdout is NOT_PERFORMED. Independent physical
validation remains UNAVAILABLE; overall accuracy is null. Climate-to-cooling and construction sensitivity
are INAPPLICABLE without response coefficients/inventories. Repeated deterministic bytes establish
software reproducibility, not buildability, future supply, engineering adequacy or accuracy.

Same-folder current identity changes fail and require a new output folder. Cached-stage corruption,
source/config/code/grid mutation during execution and incompatible file/row identities fail explicitly.
The legacy build-grid default writes to production; delivery examples use a fresh owned output folder
so accepted source/grid bytes remain preserved. No national model execution is advertised.
# Current national discovery revision — 2026-10-03

The added schema 2.1.0 configuration extends search coverage to 3,384 fixed-origin 50 km cells across
CONUS. Statements below describing national execution as unsupported refer to the historical
Phase 7 development delivery. The national baseline retains original decision weights and required
metrics, using nationwide NLCD, eGRID, Aqueduct and EIA evidence. It does not imply that every cell
has complete coverage or can be ranked. Required incomplete metrics remain unranked.

Optional cached climate/hazard sources and expanded future/LCA contexts are explicitly not computed
in this initial national baseline. Their values remain UNKNOWN with `missing_reason=not_computed`;
source acquisition is reported separately. Older development future contexts remain readable only
for their own runs. Native NLCD undergoes documented nearest-neighbor 30 m CRS conversion, which
can affect class boundaries. A 50 km cell and adjacent search region are broad investigation areas,
not a parcel, contiguous land commitment or local engineering determination.
# Regional 1 km precision and industrial evidence limits

The user-approved 1 km lattice improves regional land aggregation and distance
proxies. It does not create parcel boundaries, industrial zoning, obtainable
contiguous acreage, verified electrical connection/capacity, committed water
supply or diverse fiber routes. These retain their existing UNKNOWN treatment.
STRICT screening does not accept unknown critical evidence.

Refining representative parent areas is a bounded investigation strategy; it
does not exhaust all shortlisted land or perform exhaustive national 1 km analysis.
Aqueduct basin values and eGRID subregion averages retain native spatial meaning.
The Census2023 cartographic1:500000 boundary remains generalized; initial refined
parents are inland, and future coastal expansion must audit this limitation or
upgrade to compatible official higher-resolution boundaries. No fractional
overflow or incomplete attribution is silently clamped.
# Submission alignment limits — additive 2026-10-03

Cleanview inspection and reference comparison are limited to the public largest
operating listings. The sample is capacity-selected, incomplete, may include
cryptocurrency mining, and contains county labels without exact site coordinates
or measured PUE/WUE/annual performance. Repeated facilities in one county share
model support and are not independent geographic validations. Unmatched labels
remain unresolved without fuzzy correction. A whole-cell county intersection
does not locate or validate a facility. The comparison cannot establish predictive
accuracy, causality, optimal weights or engineering coefficients.

The regional land repair removes an artificial single-cell area rejection but
does not prove connected suitable land across cells. Region total-area screening
rejects known undersized components; even a PASS remains a classified proxy.
The fixed 20 km partition can split potential land, and only the selected 61
representative parent windows are refined. Expansion beyond those windows needs
a separate bounded source computation. Minimum polygon distance to transmission
is particularly optimistic on the 50 km grid; zero means intersection somewhere
in the cell, never utility connection or available power. Cooling comparisons
remain scenario-dependent and externally unvalidated.

The six-deliverable submission package and frontend brief improve explanation;
they do not fill missing scientific evidence or establish a grade. National hazard,
climate and future contexts remain uncomputed where the archived run says so.
Generation-water consumption, full lifecycle, confirmed useful heat, construction
resource benefits, and community economic benefits remain UNKNOWN without compatible
inputs. The optional heat module calculates a supplied annual host scenario with no
default recovery or avoided-carbon factors and no automatic facility/MCDA offset.
Its annual-demand input must match usable temperatures and timing; this is not an
hourly thermal dispatch simulation. Operating actions through 2054 are a proposed
project plan. The coarse national representative and large connected-region center
are separate; neither certifies a parcel. Supporting the regional output layout is
not acceptance of the independently ongoing regional delivery revision.

# National fine surface limits — Phase 11 (2026-10-03)

The fine surface decides only which parents receive full refinement. It applies no screening, so a high
fine value can belong to a cell that refinement later marks ineligible (3,100 of 305,000 alternatives in the
`regional_refinement_v4` comparison). Its inputs carry the same proxy limits as the regional features:
mapped transmission distance is not utility capacity, the land share is not a parcel or zoning test, basin
stress is not a water-supply commitment and historical eGRID intensity is not a forecast.

Selection takes the parents with the highest best fine values. It adds no regional diversity rule, so
selected parents can concentrate where many high-value cells cluster. Unselected parents are unrefined, and
coverage of exact 1 km evidence stays partial. Basin stress can differ from the adapter by up to about 0.001
on its 0–5 scale where long straight basin edges cross tile boundaries.

## Region mode limits (2026-10-04)

The region mode (`national_fine_region_parents`) refines one parent per national discovery region, so its
spread follows the 50 km national regions. Their number, shape and membership still come from 50 km box
values. A region's best fine parent is sought only among its members, never in a neighbouring region, and
parents outside every national region are not considered. Regions remain search areas, not sites.

## County economic context limits (2026-10-04)

The user authorized 2023 and 2025 Census cartographic counties at 1:500,000,
with 2024 SAIPE estimates retained. These are mixed-year generalized geometries,
not the unavailable 2024 TIGER/Line file or parcel boundaries. Matching GEOID
does not prove unchanged jurisdiction geometry. Coastline and border differences
can leave full-grid area uncovered; reported county shares are not renormalized.

SAIPE poverty and household income are county-scale model estimates with
uncertainty, not household/site observations. The download's rounded 90% bounds
give a calculated interval half-width; it may differ from a separately published
API MOE. Percentiles describe the valid CONUS county universe, not people or
project impact. An overlapping county's poverty rate does not estimate poverty
inside the particular search area. All county intersections remain visible.

Economic display filters cannot establish community support, equitable benefits,
buildability or fiscal returns. Technical model values and global ranks remain
unchanged. Fiscal revenues, costs, incentives and significance remain unknown.
Local enrichment is bounded to at most 200,000 saved real grid cells, with
10,000-cell chunks; oversized domains fail explicitly rather than loading the
national 7.8-million-cell surface. Cached national county display can remain
available independently of bounded regional enrichment.

## Fast Grid evaluation scope (2026-10-04)

The default cached regional mode recalculates a submitted facility across all
152,500 already evaluated 1 km cells in 61 fixed nationwide representative
windows. It does not discover new windows for that facility or evaluate every
CONUS 1 km cell. Its global ranks compare the cached regional universe only.
Changing requirements or preferences may therefore make other, unevaluated
windows worth investigating. Full nationwide rediscovery remains a separate
longer option. Existing UNKNOWN critical requirements, proxy boundaries and
the 20 km per-axis region limit remain in force.

The one-minute generation target applies after preparation of the validated
static input cache. Actual runtime depends on machine load and configuration;
the evidence records preparation and changed-request timing separately. Broad
sensitivity and diagnostic cases are not assessed by this mode, and historical
carbon is not a future grid forecast. Cached inputs fail explicitly when their
contents, calculation methods, policies or environment do not match.

## Rediscovery check against existing data centers (2026-10-04)

`docs/rediscovery_validation.md` compares unscreened national 1 km candidates with an OpenStreetMap-derived
facility inventory. Hit rates, recall and presence–background AUC measure geographic agreement, not
accuracy. Existing facilities are not ground truth. Their siting reflects latency, markets, fiber, tax policy,
history and company strategy, which the model does not score. The inventory is also incomplete and mixes
facility sizes. An "emerging" candidate (no facility within 50 km) is not shown to be suitable, and a
"validated" one is not shown to be correct. The score's regional proxies produce large tie blocks: 855 cells
share the maximum. Their published order follows grid_id, and a tie-sensitivity table reports the resulting
spread. Random controls account for spatial chance and for transmission/land plausibility only. Monte Carlo
robustness covers only the county model's 45-county cohort, at county support. Every other value is null,
never invented.
