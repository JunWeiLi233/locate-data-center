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
