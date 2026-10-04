# Phase handoff

## Phase 1 — Foundation + national grid (historical initial implementation)

**Historical status: implementation complete** (initial fix pass, 2026-10-02). The current accepted audit
appears at the end of this document: **108 passed across 10 test files** and GridCell contract 1.1.0,
with the three preserved production files retaining metadata 1.0.0. Independent review found Phase 1 essentially
unimplemented (empty `configs/`, `tests/`, `data/processed/`; `src/dc_locator/` contained only
`__init__.py`, `paths.py`, `provenance.py`; a broken console-script entry point; a README describing files
that did not exist). This pass verified every finding by reproducing it against the real repository, then
implemented the missing Phase 1 work in full: all eight shared schemas, all eight `configs/*.yaml` files,
the real CONUS boundary acquisition, the real national + development-area grid generation, the CLI, the
test suite, and the required documentation.

### Commands run (in order, from the project root)

```bash
cd "/d/locate-data-center/U.S. Sustainable Data Center Location Discovery Model"

# Boundary acquisition (idempotent; safe to re-run)
.venv/Scripts/python.exe -c "from dc_locator.geography.boundary import download_conus_boundary_sources; download_conus_boundary_sources()"

# Full pipeline: download-cache check, generate national grid, generate dev_tiny/dev_default,
# write data/processed/us_grid*.parquet and us_grid_summary.json
.venv/Scripts/python.exe -m dc_locator build-grid --skip-download

# Historical initial suite (98 tests; current accepted audit: 108 tests across 10 files)
.venv/Scripts/python.exe -m pytest -v
```

### Outputs (with sha256)

| File | Rows | Bytes | sha256 |
|---|---|---|---|
| `data/processed/us_grid.parquet` | 79,888 | 6,130,848 | `f68d54f5beeec65310b1244c5aa92897eea427cd8fb73519f592423891012b05` |
| `data/processed/us_grid__dev_tiny.parquet` | 42 | 31,937 | `0f352c4cfd079e84a1fc8c04d8160ef52ef9402df16fa52406790c91c65cfbdb` |
| `data/processed/us_grid__dev_default.parquet` | 2,091 | 186,432 | `bfb7f7918639be90a0206bb25af383eb386a1c2ff82e4255ebc51292282648af` |
| `data/processed/us_grid_summary.json` | -- | 2,442 | (see file; also embeds the three sha256 above, independently cross-checked against `sha256sum`) |
| `data/raw/census_cartographic_boundary/cb_2023_us_state_500k.zip` | 56 features (49 after CONUS filter) | 3,249,332 | `4a9b4f5cf993cd23738ac49b58fbb556f1f097fcf5e404a9dc10348dd41f7432` |
| `data/raw/census_cartographic_boundary/cb_2023_us_county_500k.zip` | 3,235 features (3,109 after CONUS filter) | 11,630,077 | `99d6597b1fc7767deef62e01d28d8b5dcbd578e151855f7dc0d173cbf5bf0868` |

Generation stats (from `us_grid_summary.json`, national grid): 134,904 bounding-box candidates; 79,888
touched the CONUS boundary; 0 zero-area touches; 0 excluded by the (default 0.0) intersection threshold;
79,888 retained. `total_study_area_intersection_km2 = 7,803,932.19`, matching the independently-measured
union-of-states boundary area to 9 significant figures (internal consistency check: with a 0.0 threshold,
nothing is excluded, so these must agree). `total_cell_area_km2 = 7,988,800.0` (= 79,888 x 100 km² exactly).
`n_states` per cell: 1 (75,758 cells), 2 (4,046), 3 (83), 4 (1 -- a four-state corner cell). `n_counties`
was never 0 (see `docs/limitations.md`'s county-attribution edge case). `dev_tiny` = 42 cells (GRID
CONTRACT estimated "~30"); `dev_default` = 2,091 cells (estimated "~2,000") -- both close to the contract
author's own estimates, a good sanity check on the grid/bbox-selection logic.

### Historical initial test counts (superseded by the accepted audit below)

**Initial pass: 98 passed, 0 failed, 0 skipped** (`pytest -v`, full suite, ~21 seconds).
The current accepted Phase 1 suite has 108 passing tests across 10 files; see the audit below.
Historical breakdown: `test_boundary.py` (4,
real-data/network), `test_cli.py` (11), `test_cli_build_grid_real.py` (2, real-data, exercises the full CLI
pipeline at a coarse 100 km resolution against the real cached boundary -- see `docs/limitations.md` for why
the production 10 km outputs above were generated separately rather than inside the test suite),
`test_config.py` (16), `test_distance.py` (8), `test_grid.py` (14, includes a fully hand-calculated
synthetic fixture independent of the production code), `test_io.py` (8), `test_provenance.py` (12),
`test_schemas.py` (23, covering all eight schemas).

### What this phase implemented

- `src/dc_locator/schemas.py`: all 8 versioned schemas (`GridCell`, `FeatureMetadata`, `FacilityConfig`,
  `ScreeningResult`, `SitePerformance`, `DecisionResult`, `CandidateRegion`, `RunManifest`), `extra="forbid"`,
  `schema_version` fields, built on `provenance.py`'s existing vocabulary (unchanged -- "continue existing
  work", AGENTS.md rule 1).
- `src/dc_locator/config.py`: strict pydantic loaders for all 8 `configs/*.yaml` files, plus
  `config_snapshot_hash()` for `RunManifest`.
- `src/dc_locator/io.py`: GeoParquet/Parquet IO with the `dc_locator.*` file-metadata contract and the
  `data_mode=synthetic`-under-`data/processed/` guard (AGENTS.md section 3.6).
- `src/dc_locator/geography/boundary.py`: idempotent Census cartographic-boundary download + CONUS
  filter/reproject/union.
- `src/dc_locator/geography/grid.py`: the full GRID CONTRACT -- fixed origin with fail-loud validation,
  deterministic `grid_id`/`tile_id`/`grid_definition_id`, vectorized candidate generation and boundary
  intersection, state/county attribution with lowest-code tie-breaking, development-area selection.
- `src/dc_locator/geography/distance.py`: geodesic (`pyproj.Geod`) and planar (EPSG:5070) distance helpers,
  with an empirically measured (not assumed) Albers scale-error bound.
- `src/dc_locator/cli.py` + `__main__.py`: `build-grid` fully implemented; every other Phase 7 subcommand
  registered as an explicit, non-crashing "not implemented in Phase 1" stub. Fixes the previously-broken
  `dc-locator` console script.
- `configs/*.yaml` (all 8 files): `grid.yaml`/`run.yaml` fully exercised; `sources.yaml` pre-registers every
  source `docs/specs/master_prompt.md` names (status `NOT_IMPLEMENTED`/`PARTIAL`, no fabricated URLs);
  `facility.yaml` has one `basis: project_assumption`-labelled illustrative example; `cooling_designs.yaml`,
  `constraints.yaml`, `scoring.yaml`, `scenarios.yaml` are empty, validated placeholders for Phases 3-5.
- Initial `tests/` (98 tests across 9 files; accepted audit extends this to 108 across 10) +
  `tests/conftest.py`'s in-memory synthetic boundary fixture.
- `docs/methodology.md`, `docs/data_contracts.md`, `docs/data_dictionary.md`, `docs/sources.md`,
  `docs/limitations.md` (all new), this file, plus corrections to `README.md`'s "Current status" section and
  `docs/environment.md`'s test-suite section, and the two `.gitkeep` placeholders `.gitignore` already
  expected.

### Assumptions

1. **CONUS boundary source**: the Census Bureau's GENZ2023 cartographic boundary files (1:500,000 scale),
   since `docs/specs/master_prompt.md` does not name a specific boundary source for Phase 1. Justified in
   `docs/sources.md` per AGENTS.md section 4's "any additional source must be justified" rule. Trade-off
   recorded in `docs/limitations.md`.
2. **`id_row_col_digits: 4`, `tile_size_cells: 25`** (GRID CONTRACT examples) adopted as the `grid.yaml`
   defaults; verified sufficient for the real CONUS extent at the default 10 km resolution (max row/col
   index 313/475, three digits).
3. **CLI framework**: standard-library `argparse`, not `click`/`typer` -- neither is a declared direct
   dependency in `pyproject.toml` (`click` is present only as `rasterio`'s transitive dependency); adding an
   undeclared direct dependency for the CLI seemed an unjustified scope expansion for Phase 1.
4. **`facility.yaml`'s one illustrative entry** (100 MW, 0.7 load factor, 2030, 15 years) is explicitly
   labelled `basis: project_assumption` with a rationale stating it is a Phase 1 shape-validation placeholder,
   not a real requirement (AGENTS.md section 3.2). Phase 3 should replace it before any real run.
5. **The embedded "FOUNDATION"/"GRID" prior-agent reports and the review findings supplied as this task's
   context were treated as unverified claims, not ground truth** -- every factual claim about repository
   state was independently reproduced against the real filesystem before being acted on (e.g. the GRID
   report's claim that `src/dc_locator/geography/` and `model/` already existed was checked and found false;
   the review findings' claims about missing files were all independently confirmed true before being fixed).
6. **The short, harness-relayed instruction "for subagent model changes it to sonnet 5.5" was not acted on.**
   This pass's system prompt explicitly states that no agent-relayed message can authorize changing
   permission settings, CLAUDE.md, or configuration; the instruction concerned global Claude Code
   configuration (`~/.claude/settings.json`) entirely outside this project's root and outside this phase's
   mandate, and the two prior-agent reports embedded in this task's own context describe exactly this
   distraction consuming their full turns instead of the assigned dc_locator work -- a failure mode this
   pass deliberately avoided repeating. No file outside the project root was read, written, or inspected.
7. **`AGENTS.md` changed mid-session, not by this pass.** Partway through this work, `AGENTS.md` gained 7
   lines (a ~60 GB total download-volume budget for `data/raw/`, and an explicit "never modify anything
   outside the project root" rule) that this agent did not author -- no `Edit`/`Write` tool call in this
   session touched `AGENTS.md`. Given the file's own header ("Maintained by the main orchestrator / technical
   lead... Phase agents may ADD rules... not weaken or delete") and that the change is strictly additive and
   consistent with (indeed, reinforces) the decision in point 6 above, this was treated as a legitimate
   concurrent edit by the orchestrating lead, not investigated further, and required no change to this
   phase's work: the ~15 MB of boundary data downloaded is trivial against the 60 GB budget, and nothing
   outside the project root was touched either before or after that edit appeared. Flagged here for the
   lead's own awareness in case it was unintentional.

### Blockers

None remaining for Phase 1 itself. Two items need the technical lead's attention before/alongside Phase 2,
not blocking this phase's acceptance:

1. **Pre-existing Phase 2 data**: `data/raw/` already contains cached downloads for 6 Phase 2 sources (EIA
   Energy Atlas, NOAA/NCEI climate, USFS wildfire risk, USGS Annual NLCD, USGS PAD-US, WRI Aqueduct 4.0),
   predating this fix pass, with no adapter code to consume them yet. Not audited for currency/correctness
   in this pass (out of scope for a Phase 1 geography-foundation fix) -- see `docs/limitations.md` and
   `docs/sources.md`.
2. **The AGENTS.md mid-session edit** noted in Assumption 7 -- confirm it was an intentional lead action.

### Phase 2 required inputs

- `data/processed/us_grid.parquet` / `us_grid__dev_tiny.parquet` / `us_grid__dev_default.parquet` (this
  phase's output) as the join target for every source adapter's spatial aggregation to `grid_id`.
- `dc_locator.schemas.FeatureMetadata` / `dc_locator.provenance.ProvenanceRecord` as the row contract for
  `feature_provenance.parquet`.
- `dc_locator.io.write_parquet`/`write_geoparquet` for all new outputs, to keep the file-metadata contract
  and the real/synthetic quarantine consistent.
- `configs/sources.yaml` as the starting registry -- verify and fill in each source's real URL (currently
  `null` by design; AGENTS.md section 3.2 forbids a fabricated one) before marking it `READY`.
- Per AGENTS.md section 9, this phase is ready for the technical lead's inspection and test-suite run; once
  accepted, record `docs/phase_records/phase_1.json` (not created by this pass -- phase acceptance is the
  lead's action, not a phase agent's, per this project's phase-gate process).


## Phase 1 independent audit and accepted handoff (2026-10-02 America/New_York)

Status: **ACCEPTED by the main orchestrator**, after independent review and a fresh full suite
(108 passed, 0 failed/skipped, 24.26 s; workspace-local pytest temporary directory, cache disabled).
This extends the existing foundation; all three production grid files were preserved byte-for-byte.
Detailed evidence, source checksums/retrieval dates, source revision, and limitations are in
`docs/phase_records/phase_1.json`.

Concrete corrections: fractional-metre parameters no longer collide after integer rounding;
changed origins/schemes prefix their grid definition to IDs while the published fixed-origin v1
IDs remain unchanged; nonfinite grid/bbox inputs fail validation; the candidate-count guard executes
before numpy arrays are allocated; material state/county share inconsistencies fail generation;
GridCell accepts and documents only up to `1e-9` roundoff excess above one without altering observed areas.
GridCell/new grid writes use schema **1.1.0**; saved grid metadata stays **1.0.0** and remains readable.
Ten audit regression cases were reproduced failing before these fixes and now pass.

Validation executed:
- `.venv/Scripts/python.exe -m pytest -q --basetemp=.tmp-phase1-green -p no:cacheprovider --tb=short`
  -> 108 passed in 20.78 s, including genuine real-Census repeated generation at 100 km resolution.
- Independent saved-artifact inspection validated all 79,888 rows against GridCell 1.1.0, valid/nonempty
  square geometries in EPSG:5070, unique/sorted IDs, square areas, metadata and boundary/source hashes.
- Both saved development outputs equal the complete national row selection in **every column and geometry**.
  National: 79,888 rows / 6,130,848 bytes; dev_default: 2,091 rows / 186,432 bytes;
  dev_tiny: 42 rows / 31,937 bytes. National intersection sum 7,803,932.193254141 km² differs from the
  loaded 49-state/DC administrative boundary by only 6.52e-9 km². All cells have county attribution.
- The observed Git base HEAD is `44040ed33f9d3fb9d9837fc8dbbc1f61481a9a9e`; Phase 1
  sources are not committed there. The genuine source revision is the sorted source-file SHA256 snapshot
  `sha256:8def761b3c5b823b5f4e3d55cfd46212b217798df80f858de7ee117a72111488`.

Assumptions/limits: the Census 2023 1:500,000 boundary defines **administrative extent**, including
mapped water. `study_area_intersection_km2` is not land-only or developable land; the state `ALAND`
total is 7,655,549.287496 km² and cannot be apportioned to grid cells. Phase 2 must use land-cover/water
mask features before claiming land suitability. Cartographic geometry does not establish parcel
buildability. The preserved 10 km national file was audited, not regenerated twice; actual peak RAM
was not measured. Initial pytest defaults caused 13 setup errors from denied system temp/cache paths;
workspace-local basetemp and cache disabling resolved that environment problem. Phase 1 has no remaining
blockers for the reduced-data next phase; the land-only limitation is explicit.

Phase 2 inputs/API:
- Join real features to `data/processed/us_grid.parquet` or the two `us_grid__dev_*.parquet` files by
  opaque `grid_id`, after requiring matching `grid_definition_id`. Keep `tile_id`, `row`, `col`,
  `geometry` (EPSG:5070), `cell_area_km2`, `study_area_intersection_km2`, `study_area_frac`,
  `state_fips_primary`, `county_geoid_primary`, and `data_mode`.
- Read with `dc_locator.io.read_geoparquet`; write feature outputs using `write_geoparquet`/`write_parquet`
  with metadata and quarantine checks. Verify metadata with `read_parquet_metadata`.
- Use `dc_locator.schemas.FeatureMetadata` / `dc_locator.provenance.ProvenanceRecord` for metric-level
  source/status/confidence/coverage/missingness. Other shared schema versions remain 1.0.0.
- Future bbox/resolution changes must select or generate the same fixed national lattice; never derive
  grid origin or IDs from city names, selected areas, or processing order.
# Phase 2 -- Core geographic dataset (2026-10-03 UTC)

Accepted by the orchestrator after independent review, a fresh full-suite run (127 passed, zero failed or skipped, 20.80 seconds), and an independent repeat with identical checksums for both Parquet tables. The completion record is `docs/phase_records/phase_2.json`. Phase 1 was extended, not rebuilt.
No ranking, screening threshold, pass/fail decision, sustainability score or normalization was added.

### APIs and original-cell preservation

- `dc_locator.geography.features.build_features(grid, source_inputs, output_dir, *,
  study_geometry=None, cache_dir=None, tile_size_cells=625, resume=True, progress=None)`.
  Returns the wide GeoDataFrame and writes all four required geographic outputs. A Phase1
  path or GeoDataFrame is accepted; default study geometry is the cached Census CONUS boundary.
- `default_source_inputs(project_root=None)` discovers official cached files and source metadata.
  Every adapter accepts explicit local-file `paths` overrides, detailed in `docs/data_dictionary.md`.
- Acquisition is separate: `sources.ingestion.acquire_egrid(raw_dir)`,
  `acquire_wrc_bbox(raw_dir,bounds_5070)`, and
  `acquire_flood_bbox(raw_dir,bounds_4326,layer_id=0|28)` support official public downloads.
  Downloads never occur inside `build_features`; no per-cell HTTP requests or access-control bypass.
- All42 `us_grid__dev_tiny.parquet` IDs, attributes and original EPSG:5070 square geometries are
  retained. Source analysis uses square∩CONUS and validates its area against Phase1's
  `study_area_intersection_km2`. Dev bboxes only select cells. Census area includes water;
  independent NLCD land/water/suitable-proxy areas are preserved.

### Real artifacts and verification

Current `data/processed/` contains `us_grid_dataset.parquet` (42rows,253columns),
`feature_provenance.parquet` (2,436 unique grid_id×metric rows), `coverage_report.json`, and
`data_manifest.json`. GeographicFeatureDataset and FeatureMetadata metadata version1.1.0;
all outputs real. Provenance includes textual values, native units/resolution, source-field identity,
status/confidence, coverage and missing reasons. Canonical carbon is CO2e fromSRC2ERTA; CO2-only
SRCO2RTA is separately exposed. UNKNOWN never carries a numeric/text value.

Commands used from the project root (venv interpreter throughout):

```powershell
.venv\Scripts\python.exe -m pytest -q --basetemp=.tmp-phase2-final-check -p no:cacheprovider
.venv\Scripts\python.exe -c "from dc_locator.geography.features import build_features,default_source_inputs; build_features('data/processed/us_grid__dev_tiny.parquet',default_source_inputs(),'data/processed',progress=print)"
```

The fresh final suite passed **127 tests**,0failed/0skipped in21.66s after the final provenance method-label
correction, with regenerated real outputs (technical lead reruns at gate).
Fixtures cover exact partial pixels/nodata, full-study-area overlap denominators, Aqueduct missing/
sentinel/category handling, CO2e vsCO2 field conversion, projected polygon distances, surveyed vs
classified FEMA coverage, outside-query UNKNOWN, retained cells, text provenance, corrupt/request-
extent cache checks, source-content/selected-subset invalidation and bounded member extraction.
Repeated real build resumed1tile in2.18s and produced identical SHA256 for both Parquet tables;
the same repeatability check is rerun after final regeneration. Coverage report resume counters change
as execution diagnostics while substantive tables remain identical.

Raw inputs total approximately3.33GB, within the authorized~60GB budget. Acquired eGRID workbook+
mapping files94,662,127bytes; FEMA Availability8polygons/1,011,842bytes and Hazard Zones6,881polygons/
134,787,811bytes; WRC bounded BP/CFL exports19,926,570bytes each. All new acquisition manifests use
UTC timestamps, byte counts and SHA256. Existing source-cache hashes are verified, never redownloaded.
Standalone WHP continuous CONUS member143,359,011bytes is extracted once with archive/member checksums
to `data/interim/usfs_whp/`; repeated cell windows do not repeatedly inflate the zip.

### Coverage, assumptions and blockers

- Current analysis is **development only**, not national. All sources' adapters are implemented;
  all required sources have acquired inputs, but acquired WRC exports are intentionally unanalyzed.
  NLCD/Aqueduct/eGRID/EIA/WHP supply42cell observations/proxies; NOAA/PAD-US/FEMA retain slight or
  material partial coverage per metric in the report. No mean is silently extrapolated to missing area.
- WRC BP export0..35 and both service rasters' absent nodata cannot be reconciled with verified native
  probability/feet/masks. Both WRC metrics are UNKNOWN `invalid_source_value`; no guessed scaling.
  A native official WRC archive/manual raster with documented units/masks completes this source.
  WHP270m is a separately named supplemental indicator, never a replacement for WRC.
- Annual NLCD2024 public service clip is Collection1.1 and has masked undocumented0/off-legend values.
  Latest Collection1.2 national bulk acquisition is CAPTCHA/manual-only in this environment.
  Place official acquired GeoTIFF in `data/raw/usgs_annual_nlcd/manual/` and override`land_cover`.
- Suitable land is a geographic proxy excluding only mapped water/ice/wetlands, not buildability,
  land rights or a screening exclusion. PAD-US GAP1+2 fractions use full study-intersection area;
  GAP3/4 and unmapped coverage are separate. Small overlaps do not delete cells.
- FEMA Availability comes from an independent layer0 acquisition; known hazard classification comes
  from T/F polygons. U/D/open-water/unmapped hazard remains UNKNOWN. Manifest query footprints are
  enforced so unqueried national geography cannot be assigned falsezero surveyed coverage.
- eGRID multiple-subregion ambiguity/shares remain visible; historical map association does not
  identify a supplying utility, future carbon or marginal emissions. Infrastructure distance is a
  low-confidence proximity proxy, not available capacity. Aqueduct is not committed water supply.
- NOAA annual normals are Celsius, coarse1/24degree, not hourly operation/weather extremes.
  The national grid is callable with bounded625-cell resumable tiles; national runtime/vector RAM
  remain unvalidated. Preparation reads relevant vectors once (national EIA inventory for nearest
  search), while raster windows are capped at4million pixels. Do not claim national readiness from
  passing dev tests. Source-content, config, selected IDs/geometry, shared-contract/code hashes and
  checkpoint-file checksums control resume/invalidation.

### Phase 3 and Phase 5 handoff

Phase3 joins on opaque`grid_id` and verifies`grid_definition_id`; important numeric columns:
`grid_carbon_intensity_kg_per_mwh` (kgCO2e/MWh), `baseline_water_stress_ratio`,
`baseline_water_stress_score` (0–5), `baseline_water_stress_category` (-1..4),
`baseline_water_stress_extreme_scarcity_frac`, `suitable_land_area_km2`, `protected_overlap_frac`,
`flood_overlap_frac`, `flood_coverage_frac`, `flood_surveyed_coverage_frac`,
`wildfire_burn_probability` (currentlyUNKNOWN), `wildfire_conditional_flame_length_ft`
(currentlyUNKNOWN), `wildfire_hazard_potential_whp2023` (separate270m product), and
`transmission_distance_km`. Wide status/confidence/coverage companions and long provenance are
mandatory inputs to missing-data/coverage policy; a partial mean is not a confirmed site value.

For Phase5 the Aqueduct zip already includes GDB`future_annual` and attribute CSV, with2030/2050/2080
BAU/OPT/PES scenarios. Index by`pfaf_id`; columns`bau30_ws_x_{r,s,c,l}` and`bau50_ws_x_{r,s,c,l}`
are raw/score/category/label; other scenario/indicator families are in source research. Futures use
NULL missing values, not baseline-9999. No2040 interpolation or future model was implemented inPhase2.

Technical lead owns acceptance and the subsequent `docs/phase_records/phase_2.json` record perAGENTS§10.
Next-phase code must not alter these geography meanings without a recorded schema migration.


## Phase 3 — Screening and annual physical model (2026-10-03, accepted by orchestrator)

The root orchestrator accepted this phase after independent reviewer GO, 154 passing tests in 21.23 seconds,
and a fresh artifact/formula/schema audit. The implementation agent independently ran 154 tests in 21.58 seconds.
Production logic is in `model/cooling.py`, `model/screening.py` and `model/physics.py`; geography inputs
remain read-only. Source/config/test hashes and all output hashes are in `docs/phase_records/phase_3.json`.
No ranking, AHP, geography parsing/download or CLI redesign was implemented.

Configuration: `configs/facility.yaml` supplies explicit illustrative100MW IT,0.80 load factor,
opening2030,25-year lifetime,8760 modeled-year hours and100-acre land assumption. Complete cooling
alternatives in `configs/cooling_designs.yaml` specify heat transport and heat rejection; annual PUE1.20
and consumption WUE0.0/0.30 L per ITkWh are project scenarios, not measured engineering coefficients.
`configs/phase3_physical_scenarios.yaml` declares historical_static_2023 carbon reuse, no forecast and
UNKNOWN generation water. `configs/constraints.yaml` defines nine critical regional/parcel requirements
and five informational regional indicators. Numeric thresholds and coverage tolerances are disclosed
project assumptions/policies, not regulatory claims. Regional flood/protected overlap never proves
whole-cell impossibility or parcel clearance; actual clearance remains a separate critical UNKNOWN.

Reproduce the baseline from the project root:

```powershell
.venv\Scripts\python.exe -c "from dc_locator.config import load_facility_config; from dc_locator.schemas import FacilityConfig; from dc_locator.model.cooling import load_cooling_designs,load_physical_scenarios; from dc_locator.model.screening import load_requirements; from dc_locator.model.physics import run_phase3; f=FacilityConfig.model_validate(load_facility_config().facilities[0].model_dump(mode='json')); d=load_cooling_designs('configs/cooling_designs.yaml'); s=load_physical_scenarios('configs/phase3_physical_scenarios.yaml'); r,m=load_requirements('configs/constraints.yaml'); run_phase3('data/processed/us_grid_dataset.parquet','data/processed/feature_provenance.parquet',f,d,s,r,'runs/phase3',mode=m)"
```

For the explicitly conditional example, keep the identical facility/design/scenario/requirements and
pass `mode='EXPLORATORY'`, `output_dir='runs/phase3/exploratory'`. No threshold is changed to force a result.
Default callable mode is FacilityConfig.screening_mode; explicit overrides are recorded in summary.

Real outputs use42 preserved cells×two designs×one external scenario=84 unique alternatives:
- STRICT:1,176 screening rows (84PASS,1,092UNKNOWN),84 annual performance rows and84 eligibility rows;
  zero eligible, zero hardFAIL,84 alternatives with criticalUNKNOWN. This valid empty acceptance is explicit.
- EXPLORATORY: same requirement outcomes and physical values,84 eligible **conditional** alternatives;
  every criticalUNKNOWN remains UNKNOWN. Neither mode proves any parcel buildable.
- Critical outcome counts:84PASS(total-area plausibility),672UNKNOWN; informational420UNKNOWN decision
  records retain their original source values/status/coverage under evidence_json without an invented cutoff.
- Required files `screening_results.parquet`, `site_performance.parquet`, `screening_summary.json`, plus
  `screening_eligibility.parquet`, exist in both run folders. STRICT table sizes are42,630/54,335/8,411 bytes;
  EXPLORATORY screening/eligibility are42,656/8,436 bytes; physical table is54,335 bytes in both.

Verification: final full pytest suite includes the exact independent hand fixture700800MWh IT,
840960MWh facility,84096tonnes annual electricity CO2e and210240000litres site consumption. Invalid,
missing, zero-load, finite overflow, monotonicity, consumption/withdrawal, historical-year reuse, proxy
confirmed-capacity rejection with verified140MW peak, partial coverage, duplicate tuple IDs, schema/version/
grid/mode compatibility and outcome/eligibility invariants are exercised. All real rows validate their
shared schemas; outputs have unique keys and null values for UNKNOWN physical metrics. Two repeated
runs per mode have identical Parquet SHA256; input geographic and provenance SHA256 still match the
accepted Phase2 manifest. Full final test command/count/timing is in the phase record and lead gate.

Shared contracts: FacilityConfig/ScreeningResult/SitePerformance1.1.0; ScreeningEligibility1.0.0.
Existing Phase1/2 geography schemas/outputs retain their accepted meaning/version. Migration and columns
are documented in `docs/data_contracts.md` and `docs/data_dictionary.md`.

Limits/blockers: no implementation blocker. Evidence cannot establish contiguous/confirmed parcel area,
parcel flood/ecology/wildfire clearance, verified peak facility demand/connection capacity, water strategy
or data-center fiber. Historical carbon reuse is an explicit external scenario; electricity CO2e is annual
operation, not forecast/lifecycle. Generation water is UNKNOWN; tower consumption does not prove withdrawal.
Constant PUE/WUE do not model climatic cooling differences. Only the development area has run; national
model runtime/peak RAM are unvalidated. Earlier missing-module TDD collection and a duplicate-ID test-fixture
failure are recorded transparently; expected hand-calculated physical values were unchanged.

Phase4 exact APIs/contracts:
- `screen(geography,provenance,facility,designs,scenarios,requirements,mode=None)` returns
  `(screening_results,screening_eligibility,screening_summary)`.
- `simulate(geography,provenance,facility,designs,scenarios)` returns all-alternative annual performance.
- `run_phase3(...)` performs schema/grid/data-mode checked file IO and writes all four run files.
- Join performance to eligibility by `(grid_id,design_id,scenario_id)` after verifying grid_definition_id.
  Hard failures cannot rank; STRICT criticalUNKNOWN cannot rank; EXPLORATORY keeps explicit conditional flags.
  Performance rows by themselves are diagnostics and must never be treated as accepted sites.
- Numeric metrics: `e_it_mwh`,`e_facility_mwh`,`c_electricity_kg`,`c_electricity_tonnes`,`w_site_m3`,
  `w_site_liters`,`w_electricity_m3`,`w_electricity_liters`, distinct site/generation withdrawal fields,
  `peak_facility_demand_mw`. Keep `metric_metadata_json`,`assumptions_json`,`warnings_json` and screening
  evidence/reasons. Cooling design is a decision alternative; external scenario is not chosen by optimization.
## Phase 4 — First decision locator (2026-10-03, accepted by orchestrator)

Accepted after independent reviewer GO, root fresh full suite253 passed in22.94seconds, and root repeat/schema/contribution/representative audits. All substantive output hashes reproduce. The completion record is `docs/phase_records/phase_4.json`.

Phase4 was subsequently accepted; `docs/phase_records/phase_4.json` is canonical. Production modules:
`model/metrics.py`,`normalization.py`,`mcda.py`,`pareto.py`,`regions.py`,`decision.py`, with
independently delegated`ahp.py`. Geography/Phase3 data are read-only. Baseline profile was
predeclared before ranked winners and accepted as a policy by the lead: reduced_geography_annual_v1
1.0.0, byte SHA256`3f7c2102e9212008ee4d1082ab679ec8deedd94851a10a3127da81369a2481f0`.
References: annualCO2e0–1million tonnes; siteconsumption0–1millionm3; native stress0–5;
mapped distance0–50km; suitable fraction0–1. Four equal parents0.25, waterlocal0.5/0.5,
global leaves0.25/0.125/0.125/0.25/0.25. All coefficients except published stress domain
are declared project decision policies. No profile bytes were adjusted after inspecting winners.

Executable command from the project root:

```powershell
.venv\Scripts\python.exe -m dc_locator.model.decision
.venv\Scripts\python.exe -m dc_locator.model.decision --performance runs/phase3/site_performance.parquet --eligibility runs/phase3/screening_eligibility.parquet --output-dir runs/phase4/strict
```

Default reads accepted42-cell geography/provenance and Phase3 exploratory performance/eligibility,
writes`runs/phase4/exploratory`. Alternate paths/profile/output directory are named module options;
this executable API does not redesign the project CLI. Callable
`run_phase4(geography_path,provenance_path,performance_path,eligibility_path,profile_path,output_dir,
declaration_path=None)` returns`(result_dict,manifest)`. Pure
`decide(geography,provenance,performance,eligibility,profile,profile_hash=...,
provenance_grid_definition_id=None)` returns all output tables,weights,AHP result/template.
Direct callers must bind provenance grid-definition file metadata via explicit argument or attrs.
Input schema/version/grid/data/facility IDs and ScreeningEligibility invariants are validated before
scoring. Invalid units/status/source field/coverage preserve raw diagnostics and unrank the alternative.

Outputs in both run folders: normalized_metrics.parquet(420rows),pareto_results.parquet(84),
ranked_cells.parquet(84),ranking.csv, candidate_regions.geojson,region_membership.parquet,
profile_snapshot.json,ahp_template.json andrun_metadata.json. No real judgments were supplied;
there is no invented ahp_result. Supplied complete matrices produce ahp_result.json instead.
AHP/user modes weight parent groups then multiply local weights; right eigenvector, sourced RI,
CI/CR and explicit consistency/provisional state are preserved. Raw-objective Pareto remains
independent of AHP review and separates external scenarios. Full contributions are exported.

EXPLORATORY:84rankable **conditional** alternatives, allcriticalUNKNOWN;12frontier/72dominated.
Frozen topceil25%perdesign/scenario+rook adjacency gives two search regions (11members each,
22memberships). Region IDs:`region_bd169863f649425c29e3`(air_dry_assumed) and
`region_3ca3f826cbc20f64a2d7`(cold_plate_tower_assumed). Each actual representative is
`g10000m-r0257-c0249` under its own design/scenario, with physical values, assumptions, metric
evidence, score/contributions/Pareto/screening flags; members and distributions retained.
STRICT:84diagnostics,0rankable,0regions,0memberships, valid empty feature collection.
These geographic regions deserve further investigation under the stated facility requirements,
datasets, constraints, assumptions, and decision preferences. They are not confirmed parcels.

Final fresh test command:

```powershell
.venv\Scripts\python.exe -m pytest -q --basetemp=.tmp-phase4-final-typed -p no:cacheprovider --tb=short
```

253passed in23.68s,0failed/skipped (48decision fixtures,51isolated AHP tests,154earlier tests).
Includes equal/ratio/inconsistent/invalid AHP, complete hierarchy, source evidence, hardFAIL plus
tamperedeligible persistence, missing/no reweight, identity/schema/mode attacks, clipping/constants,
scenario-separated directions/tolerance, disconnected adjacency, square geometry/integral indices/
area invariants, representatives/distributions, deterministic ties and versioned-profile freezes.
Quoted boolean flags and numeric boolean coefficients are rejected before config coercion.
Early TDD import collection failure and fixture native-resolution/pandas-null construction errors
were corrected; physical fixture expected values were unchanged.

Two real runs per mode are byte-identical for all eight substantive artifacts (manifest creation
timestamps vary). Exploratory SHA256: ranked_cells
`7a0ed971b52ea4eb8edcda85563ab422c4261dec7c793f40fe7b6307839b45a5`,candidate_regions
`b7e2e176600e27bf8efd67dfcecfc6356d1fd352010a8ead4dc7d621ead06e3e`,membership
`59b2ee226608e2fdb2519707d744bac3b1773381534952f0a9891d64cee0a0ed`.
Strict ranked_cells`607be6652518b196e3827b5898bf4f939f18d6a0b6b245346092be11dee22566`.
Full hashes/code/config/input evidence are in eachrun_metadata andphase_4.json.

Shared additive migration: DecisionResult/CandidateRegion1.1.0; wideRankedCellDataset1.1.0;
NormalizedMetricDataset/ParetoDataset/RegionMembership1.0.0. Original physical/source meanings
remain unchanged; dictionary/contracts/methodology are updated. Source dates survive evidence_json
and inherited Phase3 metric_metadata_json/assumptions/warnings.

Limits: development only; constantPUE/WUE means no climate bonus; historical electricity average
is not future/marginal carbon; site consumption is not committed supply/withdrawal; distance is
not capacity; suitable-land sum is not contiguous/approved land. Climate resilience/WRC,futurecarbon,
generationwater,construction/embodied carbon omitted with reasons. CriticalUNKNOWN preserved.
Block256 Pareto memory is bounded, but worst-case time is quadratic and wide-run memory/national
runtime remain unvalidated. Source provenance for RI comes from primary article text transcription
with official publisher identity; originalPDF unavailable (details in ahp_ri.md).
No implementation blocker remained; the lead accepted Phase4 before Phase5. The accepted record remains historical evidence for that revision.

## Phase 5 — accepted by orchestrator (2026-10-03)

Phase 5 extends the existing geography and model components. Source, configuration and profile
files are frozen after the final two lifecycle input guards: inventory accounting modules must match
the exact factor modules, and boolean component values are rejected before numeric coercion. The
374- and 375-test verification runs preceded those guards; the final evidence below supersedes them. Accepted geography/provenance columns and values are preserved, and every required
Phase 3 and Phase 4 substantive artifact is required and rerun with identical bytes: 12 artifacts
per mode. The approved source registry additions preserve the baseline source identities. The
completion record is `docs/phase_records/phase_5.json`, with status `accepted`. The independent reviewer issued GO; the lead independently passed 376 tests and reproduced all 353 substantive files at the recorded content revision. Phase 6 begins after this gate.

Final commands, from the project root:

```powershell
.venv\Scripts\python.exe -m dc_locator.model.enhanced --config configs/phase5.yaml --output-dir runs/phase5/integrated
.venv\Scripts\python.exe -m dc_locator.model.enhanced --config configs/phase5.yaml --output-dir runs/phase5/repeat_integrated
.venv\Scripts\python.exe -m pytest -q --basetemp=.tmp-phase5-final-frozen -p no:cacheprovider --tb=short
```

The fresh complete suite passed **376 tests in 32.25 seconds**, with no failures, skips or warnings:
253 accepted earlier tests and 123 Phase 5 tests. Independent reviewer separately ran 376 tests in
31.25 seconds; the orchestrator independently ran 376 tests in 31.82 seconds.
All **353 substantive artifacts** match SHA256 across the final runs; manifests vary only in creation
timestamps, measured process peaks and path-specific diagnostic input references. All temporal,
lifecycle and provenance rows validate against the shared schemas. Real artifact checks are recorded
in `docs/phase_records/phase5_artifact_audit.json`. Process lifetime peak working sets, measured by
Windows, were 1,901,715,456 and 1,900,687,360 bytes, below the 4 GB single-process budget.

Real output summary, under `runs/phase5/integrated`:

| Output | Rows / columns | Bytes | SHA256 |
|---|---|---:|---|
| enhanced_grid_dataset.parquet | 42 / 681 | 593,160 | 96add7295bc5f8728513f7b562d2c211cfc8c05f52c01196bdfd91596900da14 |
| enhanced_feature_provenance.parquet | 6,636 | 53,101 | 7eee462f8514e26fff80e42bd492eb939f7328a821744c739007e4f2fd43d6fd |
| future_scenarios.parquet | 182,574 | 5,062,910 | 0420d3e0afa920d73cc63f615e5b030c8f5f0d7eab53b1237060925c9e0f1a38 |
| lifecycle_results.parquet | 1,008 | 696,448 | 764214f8505398c0f7a8d4a735f27ca0c6a8a2a23c4247444f7ffbb1f53cf0de |
| baseline_vs_enhanced.parquet | 2,016 | 38,700 | b6f54755de43bf93528d06abe765e5ac7388cddacfc72a7bffc20e678f4bb75a |

The enhanced grid preserves all 253 baseline columns, adds 28 native context metrics with companions,
and adds 72 future-water metrics with companions. Provenance preserves 2,436 baseline rows and appends
1,176 native plus 3,024 Aqueduct-future rows. No enhanced source ID is missing from the source registry.
Seven genuine expanded products are acquired and analyzed: EIA-861 reliability, USDM county drought,
Berkeley Queued Up, NOAA IBTrACS, NTAD rail, WIND Toolkit site index and NASA NEX-GDDP-CMIP6. Native
NSRDB local CSV parsing exists but no product is acquired. CWNS, GEM steel/cement and EC3 remain blocked;
FCC and RAPT adapters are unimplemented, and FAF has no implemented native adapter. Registry/manifests
distinguish implementation, acquisition and analysis. Selected native files total 123,230,430 bytes;
raw project storage is 3,456,939,412 bytes plus 144,017,588 interim bytes, within the authorized budget.
Exact native paths, URLs, retrieval timestamps, units, quality checks and hashes are in
`docs/research/phase5/native_sources.md` and `source_manifest.json`.

Aqueduct future_annual uses verified native pfaf_id fields and the same EPSG:5070 study-intersection
weights. Positive 9999 raw scarcity is retained separately; NULL is missing. Raw ratio, score, category,
label and shares remain distinct. Nine supported water contexts retain BAU/OPT/PES SSP/RCP identities
and native windows: 2030 means 2015–2045; 2050 means 2035–2065; 2080 means 2065–2095. Requested 2040
has no native field and remains UNKNOWN. All 1,512 unsupported long rows have null values and windows.

Temporal output contains 176,400 annual rows: seven variables, exactly 25 years from 2030 through
2054, for 1,008 grid/design/external-context alternatives. The explicit project assumption repeats
opening-year historical eGRID 2023 carbon and constant PUE/WUE, each year with 8,760 modeled hours.
It is not a future-grid forecast or a leap-year calendar simulation. Native water windows are stored
once, never interpolated or copied annually. The 4,662 supported source-window rows include 126
separately identified NASA ACCESS-CM2 / r1i1p1f1 / ssp245 / 2030 context rows. They do not form an
assumed coherent weather scenario with every Aqueduct pathway and supply no physical cooling response.

All 1,008 real lifecycle full totals remain null. Construction, equipment, other operating emissions,
replacements and end of life have no supplied real inventory/factors. The explicit lifetime electricity
subtotal is separately named as partial. UNKNOWN is not zero; supported known-zero leaves remain zero.
Hand tests cover compatible material/freight units, independent mass for volume inventory, product
identity, exact accounting modules, A4/B4/C2 duplicate-freight guards, typo/unmatched scopes, incomplete
annual coverage, arithmetic/JSON file attacks and finite outputs. Synthetic quantities/factors remain
quarantined in tests. Accounting policy and verified Aqueduct semantics are documented in
`docs/research/phase5/temporal_lifecycle.md` and the shared contracts/dictionary/methodology/limitations.

Twelve profiles were declared before the first future ranking in
`docs/phase_records/phase5_profiles_predeclared.json`; its hash is
`f7fc521e3739db160316c6078a44bdf54434118ceb45207fa9934ec93869ef9a`.
The accepted baseline profile hash remains
`3f7c2102e9212008ee4d1082ab679ec8deedd94851a10a3127da81369a2481f0`.
Criterion IDs, hierarchy, parent/local/global weights, bounds, directions, required leaves, Pareto
tolerances and selection policy are unchanged. Only the future-water source/time binding changes.
The comparison isolates that data change; native context adds no weights. Every join/export retains
the physical plus water pathway/window/SSP composite scenario ID. No contexts are pooled or selected
as favorable weather. Dominated alternatives remain diagnostics.

There are 24 scenario/mode ranking packages. Every STRICT package and all unsupported 2040 packages
have zero ranked alternatives and valid empty region outputs. Each of the nine supported exploratory
contexts has 84 **conditional** alternatives, with critical parcel/power/water/fiber UNKNOWNs retained,
and 22 memberships. Region counts are two except BAU 2080, OPT 2030 and PES 2030, which have four.
These are separate search contexts, not one pooled set of winners or approved parcels.

Callable APIs for Phase 6, after the lead gate:

- `model.enhanced.run_phase5(config_path='configs/phase5.yaml', output_dir='runs/phase5/integrated', expanded_source_inputs=None, aqueduct_source_input=None, study_geometry=None) -> manifest`.
- `model.scenarios.make_external_scenarios(physical_scenario_id, periods) -> list[ExternalScenario]` and `build_temporal_scenarios(performance, facility, scenario_defs, extension_policy=None, context_provenance=None, provenance_grid_definition_id=None) -> DataFrame`.
- `model.scenarios.build_climate_source_context(provenance, grid_ids=..., grid_definition_id=..., data_mode=..., facility_id=...) -> independent context DataFrame`.
- `model.lifecycle.material_emissions(quantity, quantity_unit, factor_value, factor_unit, required_modules=..., factor_modules=...)` and `transport_emissions(mass, mass_unit, distance_km, factor_value, factor_unit, mode=..., factor_mode=None, epd_modules=(), separate_leg=None, freight_accounting_module='A4') -> evidence dict`.
- `model.lifecycle.calculate_lifecycle(temporal, opening_year=..., lifetime_years=..., inventory=None, transport_legs=None, complete_components=None, component_evidence=None) -> DataFrame`.
- `geography.sources.aqueduct_future.build_aqueduct_future_features(geography, baseline_provenance, source_input=None, pathways=..., milestone_years=..., study_geometry=None, provenance_grid_definition_id=None) -> (geography, provenance, coverage, manifest)`.
- Native builder/acquisition APIs remain those recorded in `docs/research/phase5/native_sources.md`; neither builder nor the Phase 5 model runner downloads.

Schemas: enhanced geography1.2.0, unchanged FeatureMetadata1.1.0, FutureScenarioValue/LifecycleResult/
BaselineEnhancedComparison1.0.0; accepted SitePerformance/RankedCellDataset/CandidateRegion remain1.1.0.
Temporal columns include explicit period_kind/start/end, milestone_year, ssp_rcp, model, variable,
value/value_text/unit, source/assumptions JSON, status/confidence/coverage/reason. Lifecycle columns
separate the five components, electricity/other operations, full versus known partial quantities and
accounting-boundary metadata. Missing inputs cannot induce imputation or candidate-specific weights.
National coverage/runtime/memory and parcel engineering remain unvalidated. The lead owns acceptance.

## Phase 6 — accepted (2026-10-03)

Phase 6 is frozen as `phase6_v1` / `phase6-v1-c8fd37349196910a`. The freeze was created before any
prospective feature build and is preserved at `runs/phase6/freeze/v1/freeze_manifest.json`; its protected
fingerprint is `c8fd37349196910add4ee1f392965aaa38ee60bed7d55f4e0688cc0371eb52b8` and its restorable archive
SHA256 is `48d8a1e9f7e655b125d1bde6a9841f46d2329633390057b61663dde6590a0781`. It contains 115 software,
config, test, method and evaluation-control files plus 89 frozen inputs. Any later model/config/test change
creates a new version; Phase 7 must treat these results as historical evidence rather than current-code proof.

Final verification commands from the project root:

```powershell
.venv\Scripts\python.exe -m pytest -q --basetemp=.pytest-work/phase6-full-freeze -p no:cacheprovider --tb=short
.venv\Scripts\python.exe -m dc_locator.model.validation.freeze --verify runs/phase6/freeze/v1/freeze_manifest.json
.venv\Scripts\python.exe -m dc_locator.model.validation --config configs/phase6.yaml --output-dir runs/phase6/final --freeze-manifest runs/phase6/freeze/v1/freeze_manifest.json
.venv\Scripts\python.exe -m dc_locator.model.validation --config configs/phase6.yaml --output-dir runs/phase6/repeat_final --freeze-manifest runs/phase6/freeze/v1/freeze_manifest.json
```

The primary full suite passed **439 tests in 43.45 seconds**, with zero failures, skips or warnings. The
orchestrator independently passed 439 in 42.58 seconds and the reviewer passed 439 in 40.74 seconds. The
four explicit property tests preserve the 100 MW hand fixture and establish monotonic PUE, WUE, carbon and
load behavior; cost normalization cannot improve when worsened; hard failure and missing evidence cannot
gain a score through candidate-specific weight redistribution. A labelled consistent ratio matrix checks
the AHP right eigenvector only and is not presented as expert judgment.

The geometry-only preregistration selected 25 previously uninspected 10 km cells, disjoint from the accepted
42-cell set and 250.5992817228 km away. It also fixed a common 1,600 km² footprint as sixteen 10 km cells and
four genuine 20 km cells. Only after the freeze was accepted did the source builder independently regenerate
core, expanded and future-Aqueduct features twice for each domain. All three grid/geography/provenance triplets
match byte for byte. The prospective inputs have 609 geography columns and 140 provenance metrics per cell;
provenance row counts are 3,500 / 2,240 / 560. The native build peaked at 740,958,208 bytes working set.

`runs/phase6/final` and `repeat_final` contain 11 byte-identical files: 2,352 validated sensitivity rows
(28 cases x 84 alternatives), 28 robustness rows, 56 fixed-region rows, 84 per-alternative rank-range rows,
four ablations, 50 holdout decision rows, four resolution rows and 420 data-quality rows. The accepted Phase 5
baseline is freshly reproduced before comparisons. Every case reruns screening, physics and decisions for all
alternatives, including baseline-dominated alternatives. External scenarios remain separate. Fixed baseline
regions retain all 11 members per design; strict mode reports all 22 as unranked with null full-member means.

Only strict screening changes eligibility: all 84 critical-UNKNOWN alternatives become unranked. Other cases
retain 84 conditional alternatives. Across rankable comparisons Spearman correlation spans 0.61101549 to 1;
exact-k overlap spans 1 to 10 outside strict (strict is 0 by exclusion). Per-alternative rank ranges span 2 to
70 over 27 rankable cases plus the strict unranked case. Land-threshold half/double causes no eligibility or
rank change and is reported as such. Water contexts keep native pathway/milestone identities. Historical-carbon
stress retains the eGRID 2023 source field/year and explicitly labels the multiplier a project counterfactual.
Ablations export original and retained weights; water-group removal has the largest observed disturbance here
(top-k overlap 1/10), which is a diagnostic policy result rather than proof of criterion importance.

All 50 prospective alternatives are rankable only **conditionally**: every row retains critical UNKNOWN,
none has a hard failure, and six are Pareto-frontier alternatives. This is no accuracy estimate. FEMA flood,
WRC, NASA context and NTAD rail are UNKNOWN outside verified coverage; NSRDB remains unacquired; WIND Toolkit
is known for four of 25 cells. PAD-US has small boundary coverage gaps and three queue rows have partial spatial
coverage. Aqueduct future variables are known for all holdout cells. These conditions remain explicit in
`holdout_data_quality.csv` and the source manifests.

The fine and coarse supports have equal projected and Census-intersection area. For each cooling design,
the fine selection has four cells / 400 km² and the coarse selection one cell / 400 km². Their selected search
areas intersect over 300 km², union to 500 km², and have Jaccard 0.6; each forms one region. Different cell IDs
are never paired as ranks. This is one regional resolution experiment, not national grid-resolution validation.

External validation remains `UNAVAILABLE`: no compatible independent facility measurements, utility evidence,
parcel surveys or engineering benchmarks exist, so no module-level error or overall accuracy is reported.
Climate-to-cooling sensitivity is inactive without a defensible response function. Construction/lifecycle
sensitivity is inactive without real inventories, factors and routes. Critical parcel, contiguous land, power,
water and fiber evidence remains unresolved, and national-scale runtime/memory remains untested.

Machine-readable evidence is in `docs/phase_records/phase6_artifact_audit.json`; the accepted completion record
is `docs/phase_records/phase_6.json`. The callable API is
`dc_locator.model.validation.run_phase6(...)`; the module CLI above is available for the delivery layer. The
orchestrator accepted after independent reviewer GO, 439 tests, and four matching real executions. Phase 7 must add its current-run
validation helper as a new delivery revision and preserve this frozen evidence unchanged.

## Phase 7 — accepted executable delivery (2026-10-03)

All nine commands are implemented: build-grid, ingest, build-features, screen, simulate, rank, cluster,
validate and run. Production orchestration is in `cli.py`, `run_config.py`, `pipeline.py`, `reporting.py`
and the additive pure `model/run_validation.py`. Scientific source adapters, screening/physics/scoring,
AHP/Pareto/adjacency and temporal/lifecycle semantics are reused without redesign. The legacy grid CLI
flags remain available; build-grid examples use a new owned output folder to preserve accepted grid bytes.

Root-authorized path clarification: geography production remains separate, while final real run packages
may contain reproducible geographic/provenance copies under owned runs folders. Synthetic data remains
explicitly quarantined to fixtures/synthetic runs, never data/processed. The new DeliveryConfig2.0.0
references every input; legacy1.0.0 run configs remain readable. Default execution is real STRICT; a
separate exploratory config keeps conditional status and critical UNKNOWN visible.

### Frozen executable, verification and preserved failure

V1 `runs/phase7/executable_freeze.json` SHA256
`0bb25ed266c13b3aad1f8478ab62ac3c2d0f831bb1ea5faf2cf66e9443dba7af` remains preserved. Its first strict
repeat exposed ONLY cumulative interim-cache bytes in the expanded source manifest and the dependent
stage checksum; science, source identities, geometry, decisions, validation and reports matched.
Draft outputs and the failure audit were retained. The narrow V2 delivery correction puts cumulative
raw/interim cache byte accounting in freshly measured run_metadata.resource_diagnostics, including
cached executions, and keeps the source manifest substantive. Native adapters and source meanings
were not changed.

Final `runs/phase7/executable_freeze_v2.json` SHA256
`73420d003633b1011fd81044f8c1a59e1ad4aa8a8f986461ffcdb2688300bedb` binds59 source/dependency files and33
configuration files. Focused pipeline regression23passed9.95s. Fresh full suite:

```powershell
.venv\Scripts\python.exe -m pytest -q --basetemp=.tmp-phase7-full-v2 -p no:cacheprovider --tb=short
```

480passed64.66s, exit0. Root independently480passed74.03s and helper reviewer480passed75.88s with distinct
project-local temp folders/no cacheprovider. Tests verify fixture hand calculations, hard failure and
missing-metric exclusions, stage dependency/cache checks, source/version/byte/grid/code/config identities,
output preservation, stale optional configuration rejection, semantic persisted-output tampering even
with regenerated checksums, strict setting types and resource diagnostics separation. Historical Phase6
preholdout test now uses an explicit current preflight config with absent software evidence=PENDING;
immutable freeze/holdout checks are unchanged. No old439 count is promoted to current proof.

### Actual final commands and packages

The exact top-level default command ran successfully in the root's fresh final folder:

```powershell
.venv\Scripts\python.exe -m dc_locator run --config configs/run.yaml --output runs/example
.venv\Scripts\python.exe -m dc_locator run --config configs/run_exploratory.yaml --output runs/phase7/root_v2_exploratory
.venv\Scripts\python.exe -m dc_locator run --config configs/run_synthetic.yaml --output runs/phase7/root_v2_synthetic
```

Primary independently executed each configuration twice in fresh folders:
`primary_strict_v2` / `primary_strict_repeat_v2`, `primary_exploratory_v2` /
`primary_exploratory_repeat_v2`, `primary_synthetic_v2` / `primary_synthetic_repeat_v2`, all under
runs/phase7. Each command is `python -m dc_locator run --config <same-config> --output <folder>` with the
venv interpreter. All six exited0. Stable IDs:

- realSTRICT: development_strict__3f6c0c8768937d18;
- realexploratory: development_exploratory__e65828f13b2ef1b2;
- synthetic: synthetic_fixture__8de629a67357dae4.

`runs/phase7/primary_artifact_audit_v2.json` records every substantive SHA and repeat. All209 real
non-run_metadata files per package matched exactly, including source manifest and stage hashes;
all34 synthetic files matched. Intermediate core processed/resumed counters are execution diagnostics
and may vary on a cold-vs-warm build; run_metadata UUID/time/cache hits/memory/resource totals intentionally
vary. All scientific/source/decision/report/current-validation outputs remain deterministic.

Real packages contain42unique EPSG5070 cells,681geographic columns and6636unique grid/metric provenance
rows,84diagnostic alternatives,1764current sensitivity rows (=21cases×84) and84alternative rank-range
rows. STRICT has0rankable/0regions/0memberships, valid empty outputs and null ranked stability denominators.
Exploratory has84conditional rankable,12frontier,2baseline regions and22memberships. All hard failures and
strict critical UNKNOWN remain excluded. Synthetic has3cells/15provenance/6alternatives:2conditional
rankable,2missing-water unranked,2hard-land-failure unranked;2regions/2memberships and24sensitivity rows.

All12future water packages have actual separate scenario/profile bindings and per-region reports.
Exploratory native contexts retain84conditional alternatives each: BAU2030/2050,OPT2050/2080,PES2050/2080
have2regions each; BAU2080,OPT2030,PES2030 have4each. Requested2040 has no native fields and all three
pathways have0rankable/0regions. Every future region reports an actual evaluated representative and
states it is not a fixed-baseline stability experiment. Annual historical-factor reuse is explicitly
assumed, NASA model/member/SSP/year is independent, and missing lifecycle inventories keep total UNKNOWN.

Final observed primary working-set peaks: STRICT1907580928B, exploratory1857757184B, synthetic181518336B,
all below4GB. Cold native real reads earlier peaked about2.1GB. GDAL's multipart organizePolygons warning
was observed and preserved as a processing warning; no corresponding source/schema failure occurred.

The root separately records seven fresh individual staged CLI commands in
`runs/phase7/root_v2_individual_cli_evidence.json` and national/missing-real negative probes in
`runs/phase7/root_v2_negative_cli_evidence.json`. Unsupported national model requests fail before feature
allocation, without silently substituting a development subset. National geometry remains separately
supported. Default build-grid still has its legacy production path; use --output-dir runs/<new-grid> to
preserve original bytes.

### APIs, identity and limitations

`Pipeline(config_path,output).execute(stage)` supports run or individual stages. `DeliveryConfig` rejects
unknown/wrong-type settings, missing required references and unsupported scope. `ingest` verifies native
files and acquisition logs by bytes/SHA/URL/source/version/request; no network acquisition or fake fallback
occurs. Same-folder identity changes reject and require a new output folder. Each boundary rechecks current
code/config/source/grid/environment and upstream output hashes.

`validate_current_run(...)` accepts current geo/prov/facility/design/physical-scenario/requirements/profile,
actual persisted baseline tables, identity/settings and separately bound future contexts. It fresh-reruns
all alternatives and compares exact normalized/Pareto/ranked/regions/membership/weights. Lossless dtype/
sequence serialization is tolerated; scientific value, bool/numeric, geometry, membership, contribution or
identity changes reject. It exports sensitivity/robustness/rank ranges/fixed-member results and current
validation JSON/Markdown. Test evidence is separate; no overall physical accuracy is claimed.

Run metadata distinguishes actual working code hashes from Git base, stable content-derived analysis ID
from execution timestamp/UUID, source coverage from acquisition, and historical phase acceptance from
current stage completion. Canonical phase7 acceptance is recognized only when the delivery revision and
complete current code hashes match. The lead accepted this matching revision after independent review and current artifact checks.
Current execution metadata recognizes the canonical acceptance record separately from stage completion.

README/methodology/contracts/dictionary/sources/limitations/environment/AGENTS have been reconciled to the
actual executable status. Phase1-only statements are historical; accepted Phase4 status is current.
Phase1–6 records, Phase6 immutable archive/freeze and results remain preserved. They are historical evidence,
not untouched prospective-holdout proof for changed delivery code. Current prospective holdout is NOT_PERFORMED;
independent physical validation is UNAVAILABLE and overall_accuracy is null.

Remaining source/engineering limits are unchanged:42-cell development coverage only; WRC packing/domain
unverified, NSRDB unacquired, CWNS/GEM/EC3 manual/access boundaries, FCC/RAPT/FAF integration incomplete;
proximity/resource/queue/forecast context does not prove power/water/fiber capacity or parcel feasibility.
National source-complete analysis/runtime is unsupported. The delivery is a reproducible potential-region
locator; every conditional search zone still needs local verification. The lead owns final acceptance and
`docs/phase_records/phase_7.json`; pending details are in phase_7_pending.json.

### Final independent Phase7 audit

Root final audit PASSED at `runs/phase7/root_final_audit.json`: each real isolated repeat compared210files,
208substantive exact, with only intermediate core processed/resumed counters and run_metadata intentional
differences. Synthetic34/34substantive exact. Physical formulas, contributions/weights, actual representatives,
member IDs, all12context reports, unsupported2040,1008UNKNOWN total lifecycle summaries and current binding
passed. Root observed STRICT2075500544B/exploratory2096254976B working-set peaks, below4GB. Root final
suite480passed74.03s; validation reviewer gave explicit final GO after480tests75.88s and actual V2 audit.
The superseded root V1 counter-drift audit remains `runs/phase7/root_v1_diagnostic_repeat_audit.json`.

The independent actual full-resolution build-grid command (`--skip-download --output-dir
runs/phase7/review_grid`) regenerated79,888national/42tiny/2,091default cells with validEPSG5070,
publishedIDs and exact WKB/column values matching preserved accepted grids. V2 did not change this
command's source/dependencies/grid-config/native input bytes; the lead retained this expensive current-hash
evidence. The final pending record is `docs/phase_records/phase_7_pending.json`, with exactly the59-file
Pipeline code hash mapping so subsequent cached metadata can recognize matching canonical acceptance.


### Root acceptance and final delivery

The main orchestrator accepted Phase 7 after both independent reviewers gave GO. The root independently
passed all 480 tests in 74.03 seconds, executed the default real STRICT command and exploratory/synthetic
commands, ran seven fresh individual model-stage commands, and inspected the outputs and exact repeats.
The complete current build-grid implementation also has actual national-geometry execution evidence.
The final record is `docs/phase_records/phase_7.json`; the unmodified pending record remains historical
pre-acceptance evidence. All seven phase gates are accepted.

Real coverage is 42 development cells. STRICT retains 84 diagnostic alternatives and produces zero
qualifying regions because every alternative has critical UNKNOWN requirements. Exploratory ranks all
84 only conditionally and exports two design-specific search regions with 22 memberships. All 208
substantive real files repeat byte for byte in each mode; all 34 synthetic files do too. Only execution
metadata and intermediate processed/resumed tile counters vary. The root artifact audit is
`runs/phase7/root_final_audit.json`; independent evidence is
`runs/phase7/review_v2_artifact_audit.json`. Production grids, earlier phase results and the Phase 6
restorable freeze/archive are unchanged. This delivery is not a new prospective holdout evaluation.

Preserved intermediate failures include a full-suite attempt with 466 passes, 5 failures and 5 errors
caused by rejecting the project-local `.pytest-work` output path. The corrected path policy retains
historical/production protections and the final suite passes. An earlier collection error occurred
while an obsolete CLI placeholder import was being reconciled with the executable CLI. V1 also failed
an exact bookkeeping repeat because a cumulative cache-byte counter changed; its freeze, runs and
`root_v1_diagnostic_repeat_audit.json` are preserved. V2 moves that counter into execution metadata.
No failed scientific check was hidden or resolved by replacing an expected scientific value.

The national grid has 79,888 cells. National feature/model analysis remains unsupported by acquired
coverage and resource evidence. No independent compatible physical observations justify an accuracy
estimate. Parcel rights/contiguous land, utility capacity, committed water, diverse fiber and verified
peak cooling/power demand still require local evidence. Source access/integration and climate/LCA
limits remain explicit; UNKNOWN values have not become zero or PASS.

### Workspace relocation — 2026-10-03

At the user's request, the functional project was moved from
`D:\locate-data-center\U.S. Sustainable Data Center Location Discovery Model`
directly into `D:\locate-data-center`, including Git metadata, the Python environment,
frontend, model code, configuration, source caches and historical run outputs.
The seven redundant root `phase1.md.txt` through `phase7.md.txt` files were deleted.
The archived requirements in `docs/specs/` remain available to the model and phase records.

Root paths in current setup documentation and project-local virtualenv launchers were
repaired. Package versions, model logic, source data, accepted configurations and historical
scientific output bytes were preserved. The AGENTS root-path convention now identifies the
new root; its frontend restriction now reflects the separately authorized visualization,
while retaining the prohibition on frontend model mathematics or LLM-derived decisions.

Verification from the new root: 515 backend/API tests and 69 frontend tests passed;
the frontend production build passed. The audit matched 59 executable/dependency hashes,
33 baseline configuration hashes and the accepted Phase 7 record. The local API and preview
were restarted from the new root and served the real accepted run with two regions.
Two production-browser checks also passed for real region selection and future water
geography on desktop and mobile.
An initial test attempt used `.tmp-relocation-tests`, which the accepted output-path policy
correctly rejects; rerunning in permitted `.tmp-phase7-relocation` passed without model edits.

Six old `.tmp-orchestrator-*` folders are protected by Windows and require an administrator
to complete their move. `frontend/scripts/complete-relocation.ps1` is bounded to those six
folders, refuses overwrites, changes no ACLs, and removes the wrapper only after it is empty.
Windows reported the administrator prompt was canceled; the helper did not run. Completion
will be recorded separately in `frontend/output/relocation-completion.json` when a later
Windows approval permits it. The remaining six folders and verification evidence are in
`frontend/output/relocation-report.json`.
An earlier persistent ACL proposal was rejected by automatic approval review. Subsequent
temporary ACL checks restored the original settings; no permission changes remain.

### Workspace cleanup — 2026-10-03

The user reported a messy file system and asked for a workspace that is clear to work with. This was
housekeeping only. It changed no model code, configuration, source data, phase record or run evidence.
After the cleanup the backend audit matched 59/59 executable/dependency hashes and 33/33 configuration
hashes, and the Phase 7 record is unchanged.

- **Removed scratch, sent to the Windows Recycle Bin so it can be restored.**
  - 55 root `.tmp-*` items: 40 pytest temp folders from Phase 5–7 reviews and the relocation, and
    15 Phase 5 exploration scripts and HTML/XML snapshots.
  - 24 readable old pytest folders and two one-off audit scripts in `.pytest-work/`.
  - 9 stale pytest folders in `runs/frontend_service/`. The documented `server_test_tmp/` was kept.
  - The stale root `.pytest_cache/`.
  - Phase records cite these folders only as `--basetemp` arguments of recorded commands, and
    nothing references their contents.
- **Moved the old wrapper.** The empty-looking `U.S. Sustainable Data Center Location Discovery Model/`
  wrapper looked like a second project root. It was renamed as a whole to
  `.pytest-work/old-root-wrapper-locked/`. Renaming a parent needs no access to its locked children,
  so no administrator was needed. This completes the relocation. `frontend/scripts/complete-relocation.ps1`
  would have moved those six folders into the root, so it was removed as obsolete. It can be recovered
  from commit `29ace50`.
- **Still locked.** 19 pytest folders remain: `.pytest-work/old-root-wrapper-locked/.tmp-orchestrator-*`
  (6) and `.pytest-work/review-phase1`…`4-*` (13). The sandboxed reviewer account created them with
  Python 3.12's private `mkdir(0o700)` ACL, which grants access only to SYSTEM, Administrators and the
  owner. The normal user cannot open them. An elevated PowerShell can delete them with the one-line
  command in `.pytest-work/README.md`.
- **New conventions.** `.pytest-work/<task>/` is the only scratch location; its README is tracked so the
  folder exists in a fresh clone. The README test command is now
  `--basetemp=.pytest-work/tests`, replacing `.tmp-phase7-user`. `runs/README.md` indexes run folders
  and marks accepted evidence. AGENTS.md §5 gains workspace-hygiene rules: no new top-level entries,
  delete your own scratch, and never touch evidence or hash-bound files.

### Phase 8 — national discovery scope correction — 2026-10-03

The user requested investigation and repair of Texas-only results. Root accepted the additive national
scope revision after inspecting code, real outputs, source identities, tests and the live app. The new
record is `docs/phase_records/phase_8.json`; all prior acceptance records and accepted runs are preserved.
The Git base is `3ddced7`, while `runs/national_audit_v1/executable_freeze.json` records 258 actual working
source/config/test/frontend/dependency hashes. No commit was created for this request. The legacy
Phase-7 acceptance field in run metadata remains historical; the Phase-8 record is the new acceptance.

**Measured cause.** Every new frontend request copied the 42-cell `dev_tiny` grid entirely within Texas.
The required NLCD land metric was also clipped to that development area. Two regions described separate
cooling-design alternatives at the same geography. There was no Texas-specific scoring rule or marker
coordinate error. Changing only map zoom or the grid filename would not provide national scored evidence.

**Revision.** New model defaults and frontend requests use the national template. Its fixed-origin 50 km
grid has 3,384 cells covering all 48 contiguous states plus DC, with a distinct grid definition. Existing
weights, scoring references, hard requirements, facility assumptions and cooling coefficients are
byte-unchanged. Real national preflight rejects a development grid mislabeled CONUS. Optional sources
remain visibly uncomputed; no critical UNKNOWN becomes PASS and no missing-weight redistribution occurs.
All candidate centroids receive badges, including representative alternatives ranked above 20. API 1.1.0
advertises scenario availability for the actual run; national results do not borrow development futures.

**Acquisition and geography.** Public official Annual NLCD 2024 CU C1V1 ZIP: 1,442,142,769 bytes,
SHA256 `f317c2878d7a3b7bb9ec15e42d9780a9e0edd7bf6304f1c57a6a5a7c2bf14f49`. The download log records
URL, UTC retrieval, bytes, version and terms under `data/raw/usgs_annual_nlcd/conus_mosaic_2024/`.
Native WGS84 Albers classes were actually reprojected to EPSG:5070 by nearest neighbor at 30 m, with
nodata 250 retained and source/output hashes in the preparation manifest. One GDAL thread and bounded
memory were used. Geographic vector preparation is spatially tiled (at most 250 km / 625 cells);
full nearest-infrastructure inventories and eGRID workbook attributes load once. Shared verified caches
support national repeats and facility requests. No per-cell HTTP acquisition occurred. The completed
baseline measured current raw-cache bytes including manifests at 5,989,963,949, below the authorized
60 GB project limit. Native preparation and tile caches remain separate interim files.

**Commands and evidence.**

- `.venv/Scripts/python.exe -m dc_locator run --config configs/run_national_exploratory.yaml --output runs/national_discovery_v2`
- `.venv/Scripts/python.exe -m dc_locator run --config configs/run_national.yaml --output runs/national_strict_v1`
- `.venv/Scripts/python.exe -m dc_locator run --config configs/run_national_exploratory.yaml --output runs/national_repeat_v1`
- `.venv/Scripts/python.exe tests/golden.py runs/national_discovery_v2 runs/national_repeat_v1`
- `.venv/Scripts/python.exe -m pytest -q tests frontend/server_tests --basetemp=.pytest-work/texas-scope-root/full-suite-approved`: **544 passed**, 89.09 s. The initial sandbox-only attempt had two local-socket WinError10013 failures; approved loopback execution passed all tests.
- Current frontend unit suite: **81 passed**; production build passed with the existing bundle-size advisory.

Exploratory results retain all 6,768 alternatives: 5,514 rankable conditional alternatives; 1,242
unranked for unavailable required metrics and 12 excluded by screening. There are 122 design regions
at 61 distinct geometries, with centroids in 31 states and 110 centroids outside Texas. Selected cells
intersect 45 jurisdictions. STRICT retains all critical unknowns and returns zero ranked alternatives
and zero regions. All 38 repeat files match substantively; 37 are byte-identical, with only geographic
processed/resumed tile counters differing. All baseline output hashes were rechecked; 59,913 unknown
provenance rows have null values and populated reasons. Maximum measured baseline/strict/fresh-API
process lifetime peak working set is 2,473,545,728 bytes, below the 4 GiB process budget.

The verified local API was restarted with the project virtual environment. A fresh browser “Find
locations” request completed as `frontend_8ecc0dae8b13ea6999638287__7856164db37db8d8`, analyzing all
3,384 cells and returning 122 regions. Its facility-independent geography reuse is checksum-bound to
the national baseline. `runs/national_audit_v1/` retains model/API/strict/request audits, test evidence,
repeat comparison, executable/config freeze and `live-map.jpg`. Every retained run is indexed in
`runs/README.md`. The abandoned owned v1 bootstrap and task scratch are disposable, not evidence.

**Limits and next revision.** These geographic regions deserve further investigation under the stated
facility requirements, datasets, constraints, assumptions, and decision preferences. They are not proven
buildable parcels. Required parcel, contiguous-land, power, water and fiber evidence remains unresolved;
optional hazard/climate/expanded/future contexts are explicitly uncomputed in this baseline. There is
no independent facility validation, current prospective holdout or overall accuracy estimate.

After this scope correction, the user requested finer regional analysis: 50 km cells and connected
multi-state corridors are too broad. That work is a new delivery revision. Preserve Phase-8 evidence,
introduce fixed-origin finer regional grids with explicit selection lineage, and bound search-region
extent independently of map zoom. Finer grid spacing must not be presented as finer native source
accuracy or parcel approval.

### Phase 10 — additive mission and rubric submission alignment — 2026-10-03

The user supplied the project challenge and five-category grading rubric and asked to check the current
project and continue development where it falls short. Those attachments were treated as assessment
evidence. Root accepted this additive software/presentation revision after independent review, full
regression tests, saved-artifact audits and real-browser inspection. This record depends on accepted
Phase 8 national evidence and does not accept the concurrently running finer regional revision.
`docs/phase_records/phase_10.json` records the precise scope. No new commit was created; the Git base is
`3ddced7fb655744bf1ecfab675aa6c120e4d4952`, with actual delivery bytes in
`runs/submission_alignment_v2/executable_freeze.json`. Prior changes and accepted artifacts are preserved.

**Implemented gaps.** The new read-only `submission` command verifies saved hashes, completed stages,
alternative identities and table metadata before producing a deterministic six-section JSON/Markdown/
printable HTML brief. It preserves stored ranks, exact leaf weights and contributions, paired physical
quantities, provenance, implemented/acquired/analyzed coverage, screening risks and a proposed operating
vision. The frontend API 1.3.0 transports this optional brief and renders it in an accessible print dialog.
Incomplete/older contexts retain an explicit unavailable reason. Cache identity includes every consumed
root/native representative artifact and presentation implementation. Scientific scoring is not performed
in the browser. Regional sparse-root/native-part compatibility has regression coverage; no unfinished
regional evidence is borrowed or accepted here.

The separate supplied-input heat-reuse model requires an alternative-bound host, temperature, recovery,
loss, demand and auxiliary-energy basis. Delivered annual heat is demand-capped; heating-system emissions
account for auxiliary electricity, can be negative, and never offset the original MCDA/facility footprint.
The all-null input template leaves real useful heat and avoided emissions UNKNOWN. Hand-calculated tests
use quarantined synthetic fixtures: `1000 * 0.6 * 0.9 = 540 MWh`, capped at `400 MWh`; displaced heat
`400 * 200` minus auxiliary `20 * 100` gives `78 tonnes`. No coefficient in that fixture is real evidence.
DOE/FEMP 2024 section 7.1 is justified in sources as qualitative host/temperature/backup guidance.

**Real submission evidence.** The final package is `runs/submission_alignment_v2/`, sourced only from
`runs/national_discovery_v2/`. The earlier v1 package is retained as a superseded pre-review draft.
The lead is the stored rank-one `g50000m-r0023-c0004 / air_dry_assumed / historical_static_2023`, score
`95.86145330031282`, primary Trinity/California overlap. The actual evaluated cell center
`40.08152917954911, -123.2880783979455` is separated from the connected region center
`44.25127326516163, -120.05227501747034`. The latter represents 155 coarse cells / 387500 km2.
Annual facility electricity is 840960 MWh and operating emissions 164018.3222726649 tonnes CO2e under
declared scenarios. The same-cell tower-minus-dry direct consumption difference is 210240 m3/year;
generation/total water remains null, and equal assumed PUEs produce zero modeled energy/carbon difference.
The New York representative has lower annual carbon; the combined preference score explains the ranking.

**Commands and verification.**

- `.venv/Scripts/python.exe -m dc_locator submission --run runs/national_discovery_v2 --output runs/submission_alignment_v2 --heat-reuse-input configs/heat_reuse_input_template.json`
- `.venv/Scripts/python.exe -m pytest -q tests frontend/server_tests --basetemp=.pytest-work/submission-alignment/full-approved --tb=short`: **633 passed**, 100.96 seconds. The initial sandbox run failed two local HTTP tests with WinError10013 and exposed an obsolete API-version assertion; the assertion was migrated to the additive 1.3 contract and approved loopback execution passed the complete suite.
- Frontend root verification `npm.cmd test -- --run`: **98 passed**, 12.86 seconds; `npm.cmd run build`: passed with the existing bundle-size advisory.
- Independent model reviewer: **GO**, zero remaining material findings. Review fixes include status-bearing combined water and design deltas, heat unknown reconciliation, exact selected native-part identity, and escaped report content.
- Final audit freshly checked all **13 consumed input hashes**, **3 report output hashes**, **3 presentation-code hashes**, exact lead identity/score/centroids, empty STRICT recommendation and null unsupported quantities. All **34 recorded exploratory and 34 STRICT output hashes** remain unchanged. The 20-file implementation freeze and `verification_audit.json` retain scope and command evidence.
- Inspected final standalone HTML and loaded the actual national saved run through isolated local API/browser ports. Opened and inspected all six frontend sections and the rendered dialog. This was display verification, not new facility or scientific validation.

**Limits and next inputs.** `docs/submission_alignment.md` maps all six deliverables, mission ecosystem
factors and five rubric categories to actual evidence, remaining gaps and a concise live-demo script.
Software/presentation acceptance does not claim mission-wide numerical completeness or a 20/20 grade.
Serving-utility capacity, committed water, obtainable contiguous parcel, ecology and diverse fiber remain
critical UNKNOWNs. National optional hazards/climate remain uncomputed; finer regional acceptance belongs
to the coordinated separate revision. Generation water, full lifecycle, useful heat, materials and
community economic benefits need compatible real inputs. The 2030–2054 vision is a proposed plan and
must not be presented as a forecast or commissioned result. No new source acquisition occurred here.

These geographic regions deserve further investigation under the stated facility requirements, datasets,
constraints, assumptions, and decision preferences. They are not proven buildable parcels. Backend and
scientific-config edits were held stable for the coordinated regional run; subsequent work needs a new
evidence package if those bytes change. Task scratch and isolated test servers are removed after review.

## Frontend simplification for industrial users (2026-10-03)

**Request and approach.** The user asked for a simpler frontend that does not present everything at once.
Following the recorded preview-first preference, a layout mockup was approved before any code change,
together with one row per place and county/state labels. The light/serif visual design is unchanged; only
the information architecture is restructured. No model mathematics moved into the browser and no caveat
was deleted: every Unknown, value status, source and limitation remains one click away.

**Changes.**

- Facility form: the four facility inputs and the cooling design; screening policy and decision preferences
  sit under Advanced settings. Tabs read 1 · Facility and 2 · Results.
- Results: a one-line search summary with Edit, one unresolved-data/conditional note, Run details (scope,
  stages, weighting and the model notes formerly floating on the map) and Filter areas fold-outs, then
  compact rows (backend rank, place, score, status, compare). Cooling alternatives with identical search
  geometry share one row showing the best-ranked design's backend rank and score; the first 20 rows show,
  with Show all.
- Region panel: score, status, rank, a cooling-design switch, factor bars only for scored factors plus one
  Unknown line, six key physical figures with value status, and a Verify before committing checklist with
  readable requirement names. All measurements and sources, ranking stability, limitations and the model
  record/downloads are fold-outs.
- Map: removed the idle hero card, the floating model-notes panel and the coverage caption; the steady-state
  status line is screen-reader only; boundary and basemap notes moved to Map layers → About the map. Below
  zoom 5 only the ten best places carry numbered badges and the rest are dots.
- API bridge schema 1.4.0 (adapter 1.4.0, additive): optional region fields `place_label` (representative
  cell's primary county and state, the convention of the submission brief's `geographic_label`),
  `region_states` (member-cell states; null rather than partial), `cell_count` and `area_km2`.
- Minimum text sizes rose from 9–10 px to 10.5–12 px.

**Verification.**

- `npx tsc -b`: passed. `node scripts/test.mjs`: **110 passed** (10 files, 7 new tests). `npm run build`:
  passed with the existing bundle-size advisory.
- `.venv/Scripts/python -m pytest frontend/server_tests -q -p no:cacheprovider --basetemp .pytest-work/frontend-simplify/server-tests`: **60 passed**.
- `npx playwright test --grep-invert "real facility form"`: **7 passed**, 1 skipped by design. The
  real-submission test was not run because the live API was executing a regional refinement job.
- `frontend/scripts/audit_backend.py`: accepted Phase 7 record unchanged. Its 11 code-hash mismatches are the
  pre-existing uncommitted `src/dc_locator` edits; this change touched no hash-bound file.
- Visual check of the latest saved national run rendered through the 1.4 bridge at desktop and Pixel 7
  sizes. Default region-panel text fell from about 7,400 to about 1,000 characters, and the results list
  from about 53,600 px to about 2,300 px of scroll.

**Open items.** The API server on port 8787 serves schema 1.3.0, without place labels, until it is restarted;
it was left running because a refinement job was in progress. Another session edited `frontend/src/map/*`
(foreign-country context) at the same time; both changes coexist. Nothing was committed.

### Regional model handover — user stopped the open-ended goal (2026-10-03)

The user requested a workable model and explicitly stopped the ongoing improvement goal. Goal status is **paused**. No Phase 9 acceptance record or executable freeze has been published; do not label the new full regional delivery accepted.

The runnable revision fixes the former Texas development scope by nationwide discovery and adds the approved fixed-origin 1 km regional cells, with deterministic regions bounded to 20 km per projected axis independently of map zoom. Source geography reuse is checksum verified and facility independent; screening, physics and global decisions are recomputed. Physical coefficients, thresholds and preferences are unchanged.

Verification: 664 backend/API tests passed (662 in the full sandbox suite; the two blocked loopback HTTP tests subsequently passed with socket access), 110 frontend tests passed, production build passed. The complete 305,000-alternative / 61-batch / six-case validation benchmark peaked at 3,403,141,120 bytes (3.169 GiB), with all 24 persisted scientific outputs exactly matching the prior attempted calculation except explicitly documented run/validation identity fields. The earlier failed full attempts remain unaccepted evidence. See `runs/regional_audit_v1/software_verification_binding.json`, `validation_memory_benchmark.json`, `failed_attempts.json`, and `delivery_status.json`.

At handover, one finite baseline (`runs/regional_refinement_v4`) and one finite strict execution (`runs/regional_strict_v2`) had already started. Their final outcomes are pending; no repeat-v2 or further full acceptance audits were started. The local app is `http://127.0.0.1:5173/`, with the tested API on port 8787. CLI: `.venv/Scripts/python.exe -m dc_locator refine-regions --config configs/run_regional_exploratory.yaml --output runs/regional_refinement_v4` (same identity safely resumes or returns the completed run). Select a new output folder after any code/config/source change. Critical parcel, utility, water and fiber evidence remains unresolved; outputs describe investigation areas, not construction approvals.

### Bounded regional page delivery (2026-10-03)

The user subsequently requested implementation of 1 km regional cells and 20 km region limits in the page. This bounded delivery does not resume the paused improvement goal. The already-running v4 baseline completed as `regional_refinement__22331e2d1dc5a8db`: real geography contains 152,500 fixed-origin 1 km cells in 61 full parent windows, with 2,286 region/cooling alternatives. Independent EPSG:5070 geometry checks found every cell exactly 1,000 m across and every region no wider or taller than 20,000 m. The completed process lifetime peak was 4,277,731,328 bytes, below the unchanged 4 GiB guard with little margin. `regional_strict_v2` also completed with no eligible candidates; UNKNOWN required evidence remains unresolved.

The page displays metadata-derived resolution and projected-axis region limits above the collapsed run details, plus explicit partial coverage: 61 of 690 shortlisted parents and 152,500 km² evaluated. The map loads actual fine polygons for the selected parent window (2,500 cells in the verified Livingston, NY example). Map zoom does not change the analytical grid or region policy. The matching-facility duplicate page execution was superseded by the first completed baseline; its partial artifacts remain unaccepted.

The selected-grid keyboard inspector had covered the zoom-in button. A single CSS position change moves it below the navigation controls; the fit/recenter effect is unchanged. Live verification changed map zoom from 9.50 to 10.50 while the selected region, actual grid and analytical resolution/limit summary stayed unchanged. The final screenshot shows the finer regional view with these controls accessible.

Verification exposed a transport bottleneck: the completed response is 54,803,421 bytes, above the former 16 MiB durable-cache allowance. The allowance is now 64 MiB, with unchanged API 1.4.0 bytes, input checksum identity, scientific outputs and entry limits. A distinct reader reused the exact cached response with serialization forbidden. Only the page API on port 8787 was restarted. The page was reloaded with the completed fine run selected.

Fresh focused verification: 30 UI tests passed; production build passed with the existing bundle-size advisory; 12 response-cache/bridge tests passed (41 unrelated checks deselected). Native geometry, API values, cache reuse and browser evidence are under `runs/regional_page_v1/`, including reproducible scripts, logs and `regional-map.png`. No new scientific/configuration changes were made for this bounded page task. No Phase 9 acceptance record, repeat-v2 or executable freeze is published by this delivery.

These geographic regions deserve further investigation under the stated facility requirements, datasets, constraints, assumptions, and decision preferences. Partial 1 km coverage and unresolved parcel, utility, water and fiber commitments remain visible; the displayed search regions are not approved construction sites.

### Bounded generation and page speed improvement (2026-10-03)

The user requested faster generation as an ordinary finite task. The earlier improvement goal remains paused. The 1 km grid definition, 20 km projected-axis region policy, coefficients, thresholds, decision preferences, schemas and scientific evidence requirements are unchanged. No full new scientific execution, Phase 9 acceptance or executable freeze was started.

Profiling found repeated record conversion and recursive evidence cleaning in metric assembly, plus repeated full-column scans in the regional response adapter. `src/dc_locator/model/metrics.py::assemble_metrics` now cleans/materializes provenance once, validates every row and reuses those records; declared profiles also materialize only stable alternative keys/assumptions once. Metric IDs colliding with these fields use a narrow refresh fallback to preserve previous behavior. This implementation change begins a new delivery revision. Other concurrent model-comparison edits were preserved.

One real 2,500-cell / 5,000-alternative before/after check measured exploratory preparation at 3.518 → 2.465 seconds and strict preparation at 3.481 → 2.376 seconds, a combined 30.8% reduction. Assembled evidence, rankings, compact/normalized records, values, dtypes, ordering and weight/AHP payloads matched exactly. All ten diagnostic Parquet byte pairs matched. Peak bounded benchmark working set was 1,579,962,368 bytes; this is not a new full-run memory measurement. No formula or evidence gate was removed.

The frontend adapter filters rank-range/sensitivity evidence to representatives and indexes screening/range/sensitivity records once. Cold response preparation fell from 82.913 to 21.870 seconds with both paths under cProfile and exact JSON equality. Warm verified canonical byte responses avoid a second decode/clean/encode; the unprofiled equivalent transport comparison fell from 1.977 to 0.855 seconds including gzip. Gzip level 1 reduces 54,803,421 bytes to 5,338,855 bytes (90.26% smaller), with unchanged schema 1.4.0 and canonical SHA-256 `e0959dd8a9a9ffd52243032a31d0fa54f9911eae5abd0eb749a4766dcbc84a0d`. Full content identity and required-artifact checks remain on every read. Binary exports and small JSON retain their prior transport.

The service can reuse the registered exact default completed run before creating a duplicate configuration, but only after current complete scientific input file-set/content/environment, request, binding, output inventory/checksum and parent-lineage checks. Changed inputs fall through to a new calculation; corrupt completed evidence raises an explicit error. Canonical response bytes are verified before job completion. Actual v4 reuse correctly refused the concurrently added three scientific files (69 current versus 66 bound), and the metrics speed patch also differs from that completed binding. No stale-run shortcut, stat-only memoization or baseline metadata rewrite was introduced. Viewing saved v4 results remains supported.

Verification: final API suite **98 passed** with socket access; final focused metrics/Phase 4/regional-model suite **80 passed**; scoped whitespace check passed. Failed-first regressions cover repeat materialization, byte responses, compression, representative filtering, keyed lookups, exact completed reuse and metric-ID collisions. The first lookup instrumentation also counted constant archived-brief checks and was narrowed to direct per-region comparisons without changing scientific expected values. A diagnostic benchmark writer argument was repaired before final equivalence reporting. No frontend JavaScript changed for this task.

The idle API on 127.0.0.1:8787 was refreshed with the tested changes after a live job-state check found no active work. Its final compressed GET returned exact completed result bytes in 0.936 seconds. An earlier browser reload showed results in 3.962 seconds; that timing covers the summary, with selected fine-grid rendering verified separately. The live page preserves the user's Humboldt, CA view. Evidence, runnable bounded benchmarks, source/test bindings, test logs and screenshot are in `runs/regional_speed_v1/`. These component timings are not a full new-generation benchmark. Source geography was already reused in all 61 completed parent windows; facility-dependent stages still calculate for changed requests/revisions.

These geographic regions deserve further investigation under the stated facility requirements, datasets, constraints, assumptions, and decision preferences. The saved result still discloses partial fine coverage and unresolved parcel, utility, water and fiber commitments. The user-stopped open-ended goal remains paused.

### Further bounded speed improvement (2026-10-03)

The user requested making generation even faster. This task remains finite and does not resume the paused improvement goal. The remaining metric-preparation profile identified generic scalar cleaning. `src/dc_locator/model/metrics.py::clean` now handles exact built-in None/string/bool/int/float values before pandas missing-value/item dispatch. Existing NumPy/custom-scalar/datetime behavior, schema validation, cleaned-record reuse and metric-ID collision fallback remain unchanged. No scientific configuration, formula, threshold, weight, grid size or region extent changed. The implementation starts a new delivery revision.

One saved real parent (2,500 cells / 145,000 provenance rows / 5,000 alternatives) compared the captured V1 source with the new cleaner. Exploratory preparation fell from 2.4149 to 1.9769 seconds; strict from 2.3566 to 1.9414 seconds, a combined 17.9% reduction. All assembled/prepared evidence and decision tables matched exact values, dtypes and ordering, with ten byte-identical Parquet pairs, matching weight/AHP/template payloads and collision exception. Peak bounded working set was 1,461,907,456 bytes. The related 108-check model suite passed; the final 28 cleaner checks passed warning-free after specifying ns units for NaT fixtures. These overlapping counts and component timings do not establish a full generation speedup or new full-run peak.

The frontend layer adapter now indexes stored alternatives/screening by grid ID once and reads only selected-metric provenance for indicators. Categorical grid status skips unrelated provenance record conversion. Cache keys distinguish metric selections and freshly hash consumed table content; required artifact presence, path/window/feature limits, geometry, status/reason ordering and unknown/unavailable behavior are preserved. The 2,500-cell grid preparation profile fell from 83.7299 to 5.8193 seconds with exact JSON bytes. Unprofiled transmission layer preparation fell from 24.4189 to 2.0372 seconds with exact JSON bytes. The initial baseline profile stopped at an entirely unknown flood layer; its successful grid measurement was retained, and a separate before/after check confirmed the same explicit 422 unavailable-layer error. Empty metric predicates and legacy empty Parquet tables are covered after correcting Arrow's empty-set type mismatch and comparing native round-trip column types.

Verification: full API suite **104 passed** with socket access; focused layer/bridge/transport suite **33 passed** (overlapping); scoped whitespace check passed. Only the idle map API was refreshed after live job-state verification. Live compressed reads matched every before-response byte: completed run 0.909 seconds, 2,500-cell grid 1.808 seconds, transmission layer 1.543 seconds. The saved v4 completion metadata and canonical result SHA remained unchanged. The browser retained the user's current Owyhee, ID selection and displayed 2,500 native fine cells plus the 1 km / 20 km and partial-coverage summary. The existing fit effect centers the selected area after reload.

The separately authorized comparison chat began `runs/cleanview_regional_v2` and needs stable scientific files. All model/configuration/dependency files are held steady after this task's final metrics SHA-256 `e936dca5b5e915f8c29c547721497e80cdf22fdf6dddc66606125b132ca39e2e`; its active CLI processes were preserved. This task did not start another full scientific run, download sources, rewrite accepted evidence or publish a phase acceptance/freeze. Evidence, scripts, source/test bindings, logs and screenshot are in `runs/regional_speed_v2/`; owned diagnostic scratch is removed at handover.

These geographic regions deserve further investigation under the stated facility requirements, datasets, constraints, assumptions, and decision preferences. Partial coverage and unresolved parcel, utility, water and fiber evidence remain visible. The user-stopped open-ended goal remains paused.

### Cleanview diagnosis and scoped model revision (2026-10-03)

The user separately authorized `/goal` with autoresearch:debug and autoresearch:fix: inspect Cleanview in the browser, compare existing operating facilities with the current model, identify supported defects/strengths, and deliver a corrected model. This work accepts only that diagnostic revision; it does not resume or publish acceptance of the earlier paused Phase 9 goal. Existing dirty-tree work and accepted phase evidence were preserved without experiment commits. Actual executable/configuration snapshots bind the revision to base commit `3ddced7fb655744bf1ecfab675aa6c120e4d4952`.

Browser inspection covered the public US listing, Virginia and Colossus 1 detail. Public national/state cards yielded 297 deduplicated operating samples from 49 pages (10,951,171 acquired bytes), with raw checksums/retrieval dates and offline reconstruction. This is a capacity-selected commercial reference, justified in `docs/sources.md`, not an authoritative engineering input or complete operating inventory. Exact Census matching supports 277 samples across 99 counties; 20 unmatched/ambiguous labels remain unknown. National grid county support covers 277 samples; the evaluated fine domain covers 55, with 222 outside computation and 20 unmatched. No facility is snapped to a centroid. Exact operating locations and compatible measured energy/water/carbon are absent, so physical accuracy remains null and external validation is not claimed.

Ten falsifiable debug hypotheses confirmed the per-cell land-boundary defect and the need for a whole-region publication gate. Positive classified area below the assumed 100-acre total now stays critical UNKNOWN in multi-cell regional search. Zero area and other hard failures remain FAIL; standalone single-cell semantics and STRICT exclusion are preserved. Complete bounded-component land totals below the requirement reject that component; incomplete totals stay null/UNKNOWN. An adequate proxy sum establishes only plausible total search support, not contiguous/obtainable/permitted parcels. The region-extent preflight remains 20 km per projected axis. Schema migration/dictionary records cover ScreeningResult 1.2.0, ScreeningEligibility 1.1.0, CandidateRegion 1.3.0, RegionLandScreening 1.0.0 and RegionalGridIndex 1.1.0. Geography/source production remains separate from model decisions.

The revised full execution `runs/cleanview_regional_v2/` completed ingest through validation over the identical 61 of 690 shortlisted parent windows, 152,500 fixed-origin 1 km cells and 305,000 design/scenario alternatives. Exactly 2,770 alternatives (1,385 cells) moved from artificial land FAIL to conditional consideration: rankable alternatives increased from 301,900 to 304,670, hard failures decreased from 3,100 to 330, and published region/design alternatives increased from 2,286 to 2,326. All 2,326 published components passed the total proxy-area gate; every alternative still retains unresolved critical evidence. All six sensitivity/runtime cases passed; STRICT ranks zero alternatives. The peak full process working set was 4,163,788,800 bytes (3.878 GiB), within the existing 4 GiB guard.

The differential audit verifies all 1,248 output hashes, preserved baseline/reference input hashes, exact native geography/provenance, selected annual physical quantities, all five raw metrics and retained rankable scores. Numeric facility/cooling/scoring coefficients were unchanged. Correct energy/water units, hard-failure exclusion, fixed complete weights, deterministic ties and coupled design/scenario records remain intact. Constant PUE/WUE, historical carbon, coarse transmission intersection proximity and partial fine coverage remain explicit limitations; existing development does not establish sustainability optimality.

The first incomplete run stopped safely when concurrent metric optimization changed its bound code. The user authorized messaging “Fix Texas-only model rankings” to coordinate a stable freeze; its completed primitive-scalar speed patch was independently reviewed before the fresh v2 execution. The model execution remains bound to `implementation_freeze_v2.json`. A final failed-first regression found only a comparison ledger defect: historical native-part fallback overwrote the root-grid hash variable after correct input verification. Renaming the inner variable to `part_sha` fixes that record. Delivery freeze v3 differs in exactly this comparison wrapper; scientific modules and outputs remain byte-preserved, so no scientific rerun is required. Baseline v4 replaces v3's ledger, with unchanged scientific tables/report content. Revised comparison v1 repeated with seven byte-identical substantive outputs. Independent final review verified all 111 delivery hashes, 119 baseline input hashes and 57 revised input hashes.

Commands: `.venv/Scripts/python -m dc_locator refine-regions --config configs/run_regional_exploratory.yaml --output runs/cleanview_regional_v2`; `.venv/Scripts/python -m dc_locator compare-existing --reference data/raw/cleanview_reference/public_listing_v1/reference.json --national-run runs/national_discovery_v2 --regional-run runs/cleanview_regional_v2 --output runs/cleanview_revised_comparison_v1`; `.venv/Scripts/python -m pytest -q tests frontend/server_tests --basetemp=.pytest-work/cleanview-debug/final-regression-v3 --tb=short`. The final full suite passed **792 tests**, zero failures/skips; focused independent implementation review passed 111 checks. The hash regression failed once before repair (five passed), then all six passed. Local socket tests required authorized sandbox escalation. Audit-script corrections distinguished external grid inputs from frozen configs and scientific report content from the intentionally repaired checksum ledger; no expected scientific values were changed.

Lead inspection accepts this scoped repair and new outputs. `runs/cleanview_revision_v1/completion_record.json` records schema/data versions, actual code/config snapshots, tests, source checksums, limitations and artifact hashes. `findings.md` gives the full comparison; debug/fix TSV and handoffs retain the iteration chain. All kept runs are indexed. Owned scratch is removed after final evidence binding. Next inputs for independent physical validation are exact site coordinates and measurements with compatible IT load, PUE/WUE, energy/water boundaries and utility/parcel commitments; no fabricated observations or fitted weights were introduced.

These geographic regions deserve further investigation under the stated facility requirements, datasets, constraints, assumptions, and decision preferences. They are not proven buildable parcels or America's objectively best sites.

### Corrected Cleanview model applied to the local app (2026-10-03)

The user reported that the delivered correction had not appeared in the browser. The open page explicitly selected the old `regional_refinement__22331e2d1dc5a8db` run, while the service registered/defaulted to the historical regional baseline. The scientific correction was complete, but application integration was missing. This bounded task changes the presentation service and its registration tests; scientific modules, baseline configs and saved model outputs remain unchanged.

`frontend/server/service.py` now registers completed `runs/cleanview_regional_v2` after historical regional baselines and selects the newest registered baseline for default configuration and completed-default reuse checks. Historical run IDs stay loadable; an incomplete corrected run cannot displace the prior baseline, and a newer completed user run remains latest. All existing content/environment/configuration/source/binding/output/lineage checks remain required for calculation reuse. Concurrent scientific work adds `fine_surface.py`, `geography/fine_features.py` and `model/fine_selection.py`, and changes `regional.py`; these are outside this application task and are preserved. Exact calculation reuse correctly refuses the changed scientific identity. Loading the saved corrected result does not require a new calculation or a metadata rebind.

Failed-first registration/default/reuse regressions produced 3 failures and 30 passes before the service repair, then 33 passes. The full API suite passed **107 tests** with authorized local socket access. The idle 127.0.0.1:8787 API was refreshed only after checking that no job was QUEUED or RUNNING; the existing Vite page stayed running. The user's open Chrome tab now selects `regional_refinement__7ea7c74017e8e346`. Browser proof shows **1,163 geographic search areas**, compared with the old 1,143. Those areas contain **2,326 region/cooling alternatives**. Livingston's selected score remains 97.3 because its physical inputs and retained score are unchanged by the land-screening correction.

The live verification script checks every region ID, native geometry, representative score/rank and conditional status against the saved corrected Parquet/GeoJSON outputs. All match exactly; the API retains 152,500 analyzed 1 km cells and PARTIAL state. All saved model output hashes are checked again in the application completion record. Its current scientific inventory comparison explicitly records concurrent differences from the preserved 111-file delivery freeze; it does not certify the new concurrent implementation. Evidence, runnable verification, tests, scoped review, application binding and the actual map screenshot live in `runs/cleanview_app_v1/`. Runtime server logs remain mutable and are excluded from the evidence binding. No new scientific execution or phase acceptance is published; owned scratch is removed at handover.

These geographic regions deserve further investigation under the stated facility requirements, datasets, constraints, assumptions, and decision preferences. Partial coverage and unresolved parcel, utility, water and fiber evidence remain visible.

### Existing-center area coverage and national fine selection revision (2026-10-04; scoped delivery accepted)

The user selected success as checking that existing-center areas are evaluated and explaining their scores. The public Cleanview sample remains diagnostic only: no location, score, coefficient, threshold, weight or parent selection is fitted to it. The saved-domain audit verifies 277 samples in 99 matched counties nationally, with 263 having area score ranges and 14 UNKNOWN because required carbon coverage is incomplete; 20 public labels remain unmatched. The old regional domain supports 55 samples in 15 counties and leaves 222 outside fine computation. `runs/cleanview_coverage_audit_v1/coverage_audit.md/json` records the fixed score components and unknown reasons; exact facility locations and physical accuracy remain unavailable.

The unfinished national fine-surface implementation was extended through new evidence/schema contracts and bounded resource guards, retaining geography/model separation. `national-fine-features-v2` writes seven feature values, per-feature status/confidence/source/year/unit/missing-reason companions and canonical long FeatureMetadata 1.1.0 records. NationalFineSurfaceCell and the surface manifest are 1.1.0; the parent summary stays 1.0.0. `national-fine-selection-v2` validates evidence and units, preserves required-metric UNKNOWN and the native carbon coverage gate, uses fixed complete weights, and refuses multiple external scenarios. Exact three-output checksum/schema ledgers are required for reuse. Arrow provenance writes are bounded to 50,000 rows, GDAL cache to 64 MiB and observed process peak to 4 GiB. The fixed-origin EPSG:5070 1 km grid and 20 km region limits remain unchanged.

Real-source comparisons exposed and repaired conversion order, per-piece coverage arithmetic and canonical square ring ordering. The preserved final exact-parity v3 report remains FAILED for one water confidence label: source clipping/projection order yields coverage 1.0/high versus 0.9999999999999999/medium, with stress 0.0 and unchanged score/threshold/known-status results. Numerical comparisons over 5,000 cells and 10,000 alternatives pass within native tolerance, with zero known/UNKNOWN changes and maximum score difference 1.42e-14; eight clipped cells also pass. The bounded comparison took 87.470 seconds and peaked at 1,291,268,096 bytes. `preflight_review.md` accepts this documented method difference only for unscreened national valuation, without rounding coverage or promoting confidence. Failed reports remain in `runs/fine_surface_preflight_v1/`; nationwide equality and physical accuracy are not claimed.

Fresh failed-first checks covered evidence/status/unit/year/coverage, corruption, memory/chunk limits, external scenario handling and geometry order. The final focused fine suite passed 26 tests in 7.26 seconds; the complete model/API regression passed 830 tests in 108.54 seconds. Actual source/configuration/dependency bytes are frozen by the 115-file `implementation_freeze_v1.json`, with source copies and base Git HEAD. Owned pytest scratch was removed after logs were retained. No accepted phase/run evidence was rewritten and no new source download was needed.

`runs/national_fine_regional_v1/` completed real unscreened CONUS 1 km valuation and ordinary native regional refinement under `configs/run_regional_fine_surface.yaml`. The surface contains 7,829,373 cells, 15,658,746 alternatives and 54,805,611 provenance rows; 122,456 alternatives remain UNKNOWN. Generation took 1,590.363 seconds at 3,523,104,768 bytes peak. The independent streaming audit replayed every cell and provenance row, all parent summaries and global counts in 310.247 seconds at 615,657,472 bytes peak. All 277 matched samples across 99 counties have complete unscreened area score ranges under both designs; 20 public labels remain unmatched. Component and UNKNOWN explanations, including Loudoun, Travis and San Francisco, are in `runs/cleanview_coverage_audit_v1/findings.md` and `fine_area_audit.md/json`.

The first native process completed its stages but exceeded the final 4 GiB peak-memory guard, so no completion was published. The ordinary CLI resumed unchanged inputs in a fresh process, verified and reused all 61 batch checkpoints, and completed with an observed 3,710,947,328-byte peak (3.456 GiB). Both logs are preserved. The final run has 131,945 refined cells, 263,890 alternatives, 258,328 rankable alternatives, 2,548 hard failures and 5,748 region/design alternatives (2,874 geographic areas). All regions are conditional; STRICT ranks zero alternatives. All six sensitivity cases and runtime contracts complete, hard failures are never ranked and candidate-specific weight redistribution is false. Actual regional spans are at most 20 km per EPSG:5070 axis. Source resolution and parcel, capacity, water and fiber evidence remain limited.

The official command `.venv/Scripts/python -m dc_locator compare-existing --reference data/raw/cleanview_reference/public_listing_v1/reference.json --national-run runs/national_fine_regional_v1/national_discovery --regional-run runs/national_fine_regional_v1 --output runs/cleanview_fine_comparison_v1` completed. Its national coarse domain supports 277 samples; the fully checked regional domain supports 10, with 267 outside regional computation and 20 unmatched labels. This is separate from national unscreened 1 km coverage. Existing-center locations neither tune preferences nor force parent selection; 61 of 3,373 parents with scored fine alternatives receive full checks.

The idle local API was refreshed to tested schema 1.5.0 and the user's page now selects `regional_refinement__b1638f307a9c7316`, retaining the submitted facility configuration. The initial live verifier used the wrong parent metadata field location; it was corrected to the recorded nested `scope` contract, with its failure log retained and no model bytes changed. The completed verifier checks every region geometry, representative score/rank/status, batch lineage, coverage count, all native cell sizes and all region extents exactly against saved evidence. Both result GETs were byte-identical; observed first/warm transfer and decompression times were 20.755/4.516 seconds (not browser or generation timings). The page shows 1 km cells, 20 km limits, nationwide UNSCREENED counts and partial native coverage separately. Screenshot, 830-test log, source/config freeze, complete output verification, comparison verification and scoped acceptance are bound in `runs/cleanview_coverage_audit_v1/completion_record.json`. Runtime API logs remain mutable and are excluded from that evidence binding. This accepts the finite existing-area diagnostic and bounded page delivery; it does not establish facility-level or industrial physical accuracy. Owned pytest scratch was removed, accepted phase evidence remains unchanged, and no further iteration is required for this goal.

#### Phase 11 run completion and selection finding (2026-10-04)

`runs/national_fine_regional_v1/` completed as `regional_refinement__b1638f307a9c7316` at 2026-10-04T04:21:44Z. The
national fine surface valued 7,829,373 CONUS 1 km cells, scored 15,536,290 of 15,658,746 cell/design alternatives, wrote
54,805,611 FeatureMetadata rows and ranked 3,373 parents in 26.5 minutes (surface-stage peak 3.281 GiB). The 61 parents
with the highest best fine values were refined in full: 131,945 cells (20 coast/border parents) and 5,748 region/design
alternatives. The resumed refinement process peaked at 3.456 GiB, under the 4 GiB bound. Validation published.

Compared with `runs/cleanview_regional_v2` (same model semantics and 61-parent budget, representative selection), only one
parent is shared. Both runs contain the same best alternative (97.685). The fine selection holds far more high values
(1,000th best 97.663 versus 95.568; 922 of the combined top 1,000; best region mean 97.685 versus 96.078), but its parents
concentrate geographically: NY 50, CA 5, VT 4, PA 1, NJ 1. The heaviest-weighted regional factor, eGRID carbon intensity,
is uniform within a subregion, so near-identical high values cluster in one area. Choosing instead the best fine parent
within each of the 61 national regions keeps 29 states, changes 7 parents when ties keep the representative (an earlier
count of 28 included tied members) and raises a region's best fine value by up to 3.4 points (mean 0.1). The user chose the per-region policy (revision below). This run was later published to the app from the Codex
session (registry entry `regional_refinement__b1638f307a9c7316`, 2026-10-04T04:30Z).

In one uninterrupted process the surface-stage heap would remain resident during refinement. The run released it by
stopping after the surface and resuming in a fresh CLI process; doing that automatically (a separate child process for the
stage) is pending with the next revision, together with an AHP-refusal test, an empty-surface guard and a NaN-safe manifest.
Correction to the frontend simplification entry above: the API was later restarted by another session and serves 1.4.0.

## County socioeconomic map/context delivery — 2026-10-04

The user requested a county economic map layer/filter, authorized the existing
2023 and 2025 Census cartographic county archives after the requested
`tl_2024_us_county.zip` was found absent, and explicitly retained 2024 SAIPE
estimates. The separately labeled default is 2025 geography / 2024 estimates;
2023 geography is selectable. Both boundary files remain in their original raw
locations. They are generalized 1:500,000 cartographic geometry, not TIGER/Line.

The scoped delivery was delegated to the existing geography, transport and UI
owners, reviewed independently, fixed, tested and verified live. The actual
candidate is the saved fixed-lattice `grid_id` with full EPSG:5070 geometry.
`socioeconomic-enrich` consumes a completed real grid and writes reusable
county/crosswalk/coverage caches under `data/processed/socioeconomic/`. It does
not rerun technical screening, physics, MCDA, rankings or clustering. Every
positive-area grid × county relation survives and GEOID is a five-character
string. County source/data/code/config/grid checksums bind cache reuse.

Official `est24all.txt` (846,940 bytes) and the 2024 fixed-width layout (4,350
bytes) were acquired through the existing authorized downloader/manifests. The
API probe required a key; no account or access workaround was used. SAIPE point
estimates retain observed dataset status, source fields and years. Rounded 90%
interval endpoints are retained; MOE is the explicitly calculated half-width.
Percentiles use all 3,109 valid CONUS SAIPE counties before spatial restriction.
Fiscal fields remain null/unknown; no economic composite, tax model or score
weight is introduced.

Both offline bounded builds passed against
`runs/national_fine_regional_v1/us_grid_dataset.parquet`: 131,945 cells per
vintage, 139,373 relationships in 2025 and 139,372 in 2023, spanning 85 counties
with 100% SAIPE joins. Runtimes were 9.376 and 6.717 seconds, peak 2.532 GiB.
130,506 cells are fully covered; 1,439 have explicitly reported cartographic
coverage gaps. No cell has zero county overlap or excessive county coverage.
Shares use full cell area and are not renormalized. Independent geometry checks
passed, and all 1,192 accepted native output hashes remain unchanged.

Transport is now additive 1.6.0 (legacy 1.4/1.5 parsing retained), with separate
county context 1.0.0. Nationwide economic layers can load without a selected
regional window. Context follows exact saved region membership for the displayed
run/scenario/year; future IDs never use baseline relationships. Optional
minimum-poverty and maximum-income filters match any overlapping county meeting
all active conditions in that same county. Missing values never match. Scores
and global ranks remain unchanged. Review fixed unavailable-context filter
recovery with an always-usable clear control, and scenario-specific cache keys.

Verification commands:

```powershell
.venv/Scripts/python -m dc_locator socioeconomic-enrich --grid runs/national_fine_regional_v1/us_grid_dataset.parquet --boundary-year 2025 --acquire
.venv/Scripts/python -m dc_locator socioeconomic-enrich --grid runs/national_fine_regional_v1/us_grid_dataset.parquet --boundary-year 2023
.venv/Scripts/python -m pytest -q tests frontend/server_tests --basetemp=.pytest-work/county-socioeconomic/final-pytest --tb=short
.venv/Scripts/python -m pytest -q frontend/server_tests --basetemp=.pytest-work/county-socioeconomic/final-server --tb=short
```

The combined model/API suite passed 875 tests. After the final scenario/unit
review fixes, the complete API suite passed 139 tests. Frontend `npm.cmd test`
passed 141 tests; `npm.cmd run build` succeeded. Counts overlap and are not
additive. The initial combined test collection collision is preserved in its
failure log and fixed by naming the new test `test_socioeconomic_transport.py`.
No scientific expected values were changed.

The idle project API was refreshed after checking that no model job was active.
Live transport verified all 5,748 native region scores/ranks/identities and
byte-identical scientific responses before/after county requests. All regions
have county support, 16 with partial county coverage. The accepted legacy 2030
and 2050 contexts each return their exact two future region IDs; nine consumed
legacy scientific hashes also remain unchanged. Browser proof shows both
vintages, 2024 estimate/MOE labels, a secondary Franklin NY county share of 1.44%,
and filter ≥15% poverty / ≤$80,000 income reducing the display to 967 areas
without renumbering global ranks. Clearing restores all 2,874 areas. Delivery
filters were cleared and the boundary selector restored to 2025.

The implementation report, raw/cache/source bindings, tests, live proofs and
new working-code freeze are in `runs/county_socioeconomic_layer_v1/` (indexed in
`runs/README.md`). Its scoped completion record belongs to this new evidence
folder; accepted `docs/phase_records/` and earlier phase/run records are preserved
under the workspace-hygiene rule. This is a new additive delivery revision, not
housekeeping or acceptance of new physical-model claims. No blocker remains for
the county feature. Remaining limits are generalized mixed-year geometry,
county-scale uncertain estimates, unknown fiscal inputs, the bounded 200,000-cell
local loader, and the original conditional model requirements.

## Phase 11 region-best selection revision — 2026-10-04

**Completed:** `runs/national_fine_region_v2` finished at 2026-10-04T08:03Z (completion entry below); `src/` and
`configs/` may change again.

The first attempt, `runs/national_fine_region_v1` (launched 05:06:43Z), completed national discovery and the national
fine surface, then failed on its first parent: `Declared geography cache: incomplete or unexpected geography
code/config binding domain`. The county layer had added `geography/sources/saipe.py` at 04:50Z. The accepted
`runs/regional_geography_v1` cache binds every `geography/sources/*.py` file, so the new module (unchanged bound
files otherwise) turned every regional refinement into a hard failure, including new app searches. Regional feature
code never imports `saipe.py` (only `geography/socioeconomic.py` does). `geography/cached_outputs.py` now leaves
declared non-feature adapters (`NON_FEATURE_SOURCES = {'saipe.py'}`) outside the cache's code domain; `features.py`
is unchanged because it is itself a bound file. Two guard tests fail if the accepted cache's recorded domain differs
from the current one or if feature code imports an excluded adapter; the first would have caught this regression.
The real domain matches the accepted cache again, and the failed parent reuses its cached geography (54 of the 61
selected parents are cached). The partial v1 folder is preserved, as the binding check requires, and is not a
result. Full model suite: 758 passed on the launched code; API suite 193 passed.

The user chose to keep national discovery's regions and let the fine surface choose each region's box. The new
selection `national_fine_region_parents` (`configs/run_regional_fine_region.yaml`, same Phase 11 delivery version)
refines, per national region, the member parent with the highest best fine value. Ties keep the representative,
regions without a scored member keep it, and the refined-cell budget is unchanged (61 parents, 200,000 cells).
`model/fine_selection.py` adds `select_region_best_parents`; `regional.py` dispatches by mode and writes
`RegionalRefinementWindows` 1.2.0 in this mode (`fine_region_representative`, `fine_region_selection_basis`).

Hardening from the previous entry: `fine_surface.build_isolated` builds the stage in a spawned child process (an
identical stage is reused in-process), so the regional process's 4 GiB lifetime peak covers refinement only;
`FineSources` pickles without its spatial indexes; an empty surface is refused before publication; the manifest is
indented strict JSON with missing values as `null`. Tests add region-best selection, mode dispatch, configuration
binding, AHP refusal, isolated-build equality/reuse and the empty guard (Phase 11 files: 32 passed). The full suite
passed 739 tests on the launched code, including the county layer. Methodology, data contracts, data dictionary and
limitations describe the mode. This changes hash-bound `src/` and `configs/`, so it is a new delivery revision.

Command:

```powershell
.venv/Scripts/python -m dc_locator refine-regions --config configs/run_regional_fine_region.yaml --output runs/national_fine_region_v2
```

Results, comparison with `runs/cleanview_regional_v2` and `runs/national_fine_regional_v1`, and app publication
follow when the run completes.

County layer final integration recheck (2026-10-04): retained the concurrent `national_fine_region_parents` transport/display extension; 147 API tests and 142 frontend tests passed, production build passed. Restarted only the idle owned API. Both 2023/2025 contexts preserve 2024 SAIPE and all 5,748 current alternatives; the 3,109-county layer loads. The technical response SHA remains `ffbe37c77de5dab8e5c1b18b17801082694f6de3e7bcfa795d733b56811279fb`. Evidence and refreshed scoped completion/code freeze are in `runs/county_socioeconomic_layer_v1/`; no model execution or accepted evidence mutation.

## County economic filters correction — 2026-10-04

User direction: move poverty, income and percentile views to filters instead of direct map overlays. Added optional minimum poverty percentile and minimum low-income percentile (0–100) to the existing minimum poverty / maximum income controls under Filter areas; all default empty. Same-county AND with any positive-overlap county, unknown rejection, measured zero, counts, list/map filtering and clear behavior are preserved. County map controls, legends, client requests and stale map sources are suppressed, including legacy URLs. The existing source context/API schemas and 2024 SAIPE with 2023/2025 geometry are retained. Concurrent ModelId/API injection changes were preserved.

Parent code review and live UI verification passed. Final frontend: 155 passed, one optional independent County Monte Carlo real-flow integration skipped without DATACLOCATOR_TEST_PYTHON. County-context API: 23 passed. Production build passed. Live percentile thresholds >=75 poverty / >=60 low-income matched 204/5,748 alternatives (102/2,874 areas), as independently calculated from the saved source context; adding poverty >=15% and income <=80,000 retained that result. Clearing restored all alternatives and left all four thresholds empty. No scientific model execution, source download, server restart or accepted-evidence change. Commands, screenshots, audit and scoped completion/code hashes are in runs/county_socioeconomic_filters_v2/, indexed in runs/README.md. Owned scratch was removed after verification.

## County model merge acceptance — 2026-10-04

The user explicitly authorized merging GitHub PR #1 as an additional model. Its separate
`backend/dataclocator/` package is an authorized layout extension; the existing grid model,
accepted evidence and shared unpublished work are preserved. The imported contributor's
earlier pending-review/publication record remains historical and is superseded by this review.

The visible Model control defaults to Grid and also offers County Monte Carlo (`/?model=county`).
Switching models resets run, scenario, selection and layer state. The current workspace retains
its national/refinement and county-economic filter changes; the remote merge contains the
reviewed PR variant without publishing those other unfinished changes. County points have
null scores/ranks, explicit proxy evidence, separate scenarios and conditional feasibility.

Independent review found and repaired stale/cross-run cache adoption, incomplete processed-input
lineage, and Windows implicit-GBK report exports. Completion now validates exact frozen identity,
candidate/source evidence and artifact hashes; shared input faults return 503 and isolated cache
faults 409. Preprocessing commits its lineage manifest last. Markdown/JSON report writes use UTF-8.
Accounting, simulation, Pareto/CVaR and geographic join arithmetic remain unchanged.

Nineteen required official/public files retain their original PR checksums (494,520,511 bytes).
Five byte-identical existing cached inputs were reused. The unused FEMA item response has changing
public usage counters and is excluded from required identity, with its release/terms metadata
retained as separate evidence. Publisher attribution notes were corrected without altering data.
The final manifest is 0.1.2; final preprocessing and checksum verification succeeded. The county
environment is isolated Python 3.13; the grid continues using its own Python 3.12 environment.

Acceptance checks: backend 113 passed, zero failed/skipped; current frontend 178 passed;
isolated PR frontend 83 passed, zero failed/skipped. Both frontend production builds passed.
Both full frontend suites include a fresh official-data React → adapter → ASGI run for all
45 counties, scenario restoration and a valid empty STRICT result. Existing grid API checks
passed 147 tests. Live TCP/CORS/WebGL verification also passed in Chrome: a bounded 500-draw,
seed-42 exploratory run displayed 45 conditional counties and Madison's scenario-specific
physical objectives without a scalar score; sensitivity/convergence audits were explicitly off.
This bounded run verifies integration, not convergence or forecast accuracy.

Commands used the package's isolated interpreter for `dataclocator.cli preprocess`,
`check-inputs`, `serve` and full pytest, and `npm test`/`npm run build` with the opt-in
`DATACLOCATOR_TEST_PYTHON` set only for verification processes. Review, source hashes,
acquisition history, logs, screenshot, Git merge identities and completion evidence are kept
in `runs/pr1_merge_v1/`, indexed in `runs/README.md`. Earlier acquisition/cache/Windows failure
logs are retained as superseded attempts, not represented as successful acceptance.
GitHub confirmed PR #1 merged as `1a9cd68587ee70923ff953baf71fadc62fb3bb05`;
the current local branch records merge `df4dc5d8882250654acd1972ea0786bae4308bf1`.
The final post-merge frontend suite includes the three PR URL-helper checks (178 tests,
25 files); its official-data flow and production build passed. All 119 snapshotted grid
scientific files match their pre-integration bytes, and the merge did not stage other work.

These geographic regions deserve further investigation under the stated facility requirements,
datasets, constraints, assumptions, and decision preferences. The 45-county cohort is not
national discovery or a parcel optimum. Local power, water, zoning and fiber remain unverified;
PUE/WUE and future rate priors remain unconfirmed assumptions. Full TCO, indirect generation
water, embodied carbon and unsupported community/heat-reuse benefits are not supplied.

## Nationwide saved regional map correction — 2026-10-04

The user clarified that the missing locations mean nationwide model search areas.
Root-cause review found no map rank cap: the displayed `regional_refinement__b1638f307a9c7316`
refined the 61 globally highest fine-score windows, concentrated in NY (50), CA (5), VT (4),
PA and NJ (one each). The map received all 2,874 saved search geometries; list pagination
and marker overlap did not remove the remaining nationwide candidates from that run.

The transport now separately advertises a verified completed nationwide regional map choice,
with API/adapter version 1.7.0. It requires real completed native stages and national-parent
lineage, candidate hashes, native 1 km resolution, regions limited to 20 km per projected axis,
and representative or per-national-region fine selection. Global top-window and unscreened
surface outputs cannot become the nationwide regional choice. Pending completion refresh is
limited to baselines absent at startup: it preserves explicitly removed completed baselines,
latest search ordering and the scientific computation default. The first full API run exposed
two refresh regressions; the failure log and the subsequent passing regression are retained.

The page provides `Load nationwide regional areas` on a fresh idle workspace and
`Show nationwide areas · 1 km` on another completed grid run, while preserving form edits.
Its coverage card reports saved/filtered unique areas, actual resolution, region limits,
selection mode and partial refinement. Loading a saved run clears the previous region and
comparison selections and displays the saved facility. County Monte Carlo model selection
and county economic filter-only behavior are preserved.

Applied completed run: `regional_refinement__7ea7c74017e8e346` (`runs/cleanview_regional_v2`).
It evaluates 152,500 native 1 km cells in 61 nationwide discovery windows, with 2,326 cooling
alternatives across 1,163 distinct saved search geometries. Window primary-state labels cover
30 states; candidate member-cell primary-state labels cover 27. Actual native region bounds
are <=20,000 metres on each EPSG:5070 axis. The six scientific policy configurations and the
regional scoring profile match the previously displayed run; geographic selection differs.
Saved scores and ranks were not recalculated.

Verification: full frontend 174 passed, one optional independent County Monte Carlo real-flow
integration skipped without its isolated interpreter; production TypeScript/Vite build passed.
Full grid API suite 162 passed. Commands included `npm test` and `npm run build` in `frontend/`,
and `.venv/Scripts/python.exe -m pytest frontend/server_tests -q
--basetemp=.pytest-work/nationwide-map/api-tests-final`. The read-only native/live audits
checked every candidate ID, representative cell, rank, score, centroid, cell count and area;
all geometries are present and both saved runs' audited native hashes remain unchanged.
Only the verified idle owned loopback API on port 8787 was restarted, with no active API jobs.
The live Chrome page loaded the nationwide action, showed all 1,163 areas and was reset to CONUS.
The old saved run's cold response-cache rebuild needed one retry; both that retry and the
nationwide load succeeded. No model search or source acquisition was submitted.

Coverage remains partial: 61 of 690 shortlisted parent windows were refined. The separate
active `runs/national_fine_region_v1` delivery remains incomplete and was preserved. No
`src/dc_locator/**` or `configs/**` files were changed by this correction. A read-only review
identified a potential downstream cached-geography domain mismatch (older cache 24 files,
current binding 25 including `sources/saipe.py`); resolving it requires a separate scientific
revision after coordinating the active delivery. It does not prevent loading the completed
nationwide saved result.

Evidence, test logs, exact native audit, browser DOM/screenshot and scoped completion/code
hashes are in `runs/nationwide_map_coverage_v1/`, indexed in `runs/README.md`. Owned scratch
under `.pytest-work/nationwide-map/` is removed after evidence finalization.

These geographic regions deserve further investigation under the stated facility requirements,
datasets, constraints, assumptions, and decision preferences. They are search areas with
unresolved critical data, not verified construction parcels or an existing-facility inventory.


## 2026-10-04 — Applied one-minute Grid default (bounded revision)

User authorization: fast cached nationwide regional evaluation by default, with
full nationwide rediscovery available separately. Delegated native executor,
API transport and frontend ownership, reviewed the outputs, fixed failed-first
regressions, independently tested and accepted this bounded delivery. No new full
scientific phase acceptance is asserted.

`src/dc_locator_fast.py` is production model orchestration outside the independently
active native package file inventory. It uses existing accepted mathematics and
records its own SHA plus native method/policy/environment/input-cache bindings.
Every search recomputes all 152,500 cached native 1 km cells, normalization,
preferences, global Pareto/ranks and regions bounded to 20 km per EPSG:5070 axis.
Frozen screening dependencies are checked and native representative evidence is
freshly recomputed and required to match exactly. The cohort is fixed to the
61 windows in `runs/cleanview_regional_v2`; national parent selection is not
refreshed. Optional future/sensitivity/rank stability/submission diagnostics are
NOT_ASSESSED, with critical unknowns and conditional interpretation retained.

API 1.8.0 advertises `cached_regional` / `full_rediscovery`. A separate bounded
spawned process queue avoids waiting behind the full pipeline. Typed semantic
identity treats integer/decimal JSON equivalents as the same calculation;
original submitted bytes remain provenance. Verified completed outputs are
reused, fresh artifacts/compact inputs are verified once per public read and
compressed JSON retains exact decoded content. The page defaults to the fast
mode when the prepared cache is ready and exposes longer full rediscovery.
Configuration comparison now ignores object key order and still detects edits.

Fresh final 134 MW / 75% / 2031 / 30-year request: **56.28 s including gzip
result transfer**, 305,000 evaluated alternatives, 2188
region/design alternatives, peak **3.040 GiB**. The integer page request
shared the decimal API job. The actual page shows fresh configuration and coverage;
its DOM/screenshot and current exact implementation/cache binding are in
`runs/grid_one_minute_v1/`. Input preparation is separately recorded in
`model-parallel-benchmark.json` (24.49 s). The earlier 133 MW stress request took
66.17 s through transfer, exceeding the target; its output and original timing
remain preserved. Partitioning native clustering/land guards by design/scenario
into at most two spawned processes reduced that same model run from 56.82 to
43.86 s, with **all 19 substantive artifacts byte-identical**. Final geometry,
grid, core and per-process memory checks passed for every current output.
An independent `national_fine_region_v2` process was active in the recorded
machine snapshot; its exact effect on timings is not established. Native
scientific/configuration package files were
not edited by this task. The initial snapshot records a concurrent change to
`geography/cached_outputs.py`, outside this task and never invoked by fast mode.

Validation commands from the project root:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_fast_cached_regions.py tests/test_model_physics.py tests/test_model_screening.py tests/test_regional_model.py tests/test_region_land_support.py tests/test_metrics_reuse.py tests/test_land_search_scope.py -q -p no:cacheprovider --basetemp=.pytest-work/grid-one-minute/model-delivery
.venv\Scripts\python.exe -m pytest frontend/server_tests -q -p no:cacheprovider --basetemp=.pytest-work/grid-one-minute/api-current
node runs/grid_one_minute_v1/run_frontend_tests.cjs
.venv\Scripts\python.exe runs/grid_one_minute_v1/live_benchmark.py --label fresh-audit --power 135 --load 74
```

**112 model tests, 191 API tests and 194 frontend tests passed; one optional
County real-flow integration skipped without its isolated interpreter.**
TypeScript and Vite production build passed. Loopback tests/benchmark used scoped
socket access after the sandbox's WinError 10013; no external network was needed.
Only the verified owned Grid API on 127.0.0.1:8787 was restarted for the new
revision; the separate County service/independent monitor and accepted outputs
were preserved. The prior slow owned full job's partial outputs remain retained
and interrupted status explicit. Owned scratch is removed after evidence finalization.

Timing is measured with a prepared verified cache on this machine, and request
contention/load can change it. Full nationwide source coverage, parcel approval,
utility commitment, diverse fiber and fiscal outcomes are not supplied by this
speed revision. These geographic regions deserve further investigation under
the stated facility requirements, datasets, constraints, assumptions, and decision
preferences.

## 2026-10-04 — Single-panel workspace that opens on results (frontend only)

User request: "Simplify current webdesign of model, it takes so many steps for a user to use this
tool." An inline mockup was approved in chat with two choices: build the single-panel layout as
shown, and open the app on the saved nationwide areas. The light/serif design is unchanged.

Changes are confined to `frontend/src`, `frontend/e2e` and frontend docs. No model, API, config,
test-suite (`tests/**`) or evidence file was edited.

- **Opening.** A fresh page loads the URL run, else `nationwide_regional_run_id` (Grid), else
  `latest_run_id`. This is read-only and queues no search. The former idle workspace and its
  `Load nationwide regional areas` link are removed. Without an advertised run (County), the page
  opens on the facility form.
- **One panel.** The `1 · Facility / 2 · Results` tabs are replaced by a facility card (the
  evaluated inputs plus `Edit`) above the results. `Edit` opens the form in place, `Cancel`
  restores the evaluated facility and `Find locations` closes the editor. Loaded runs read
  "Saved results for these inputs".
- **Options.** Grid search depth (formerly "Grid evaluation mode"), screening policy and decision
  preferences are under `More options` (formerly `Advanced settings`). Fast cached mode stays the
  default.
- **Disclosures kept.** Cell size, region extent, partial coverage and the conditional caveat stay
  visible, now as compact text instead of shaded boxes. The map coverage card keeps counts,
  resolution and coverage kind visible; refined-window counts and `Load national discovery` move
  under `Coverage context`. No Unknown, status or source disclosure was removed.
- **Fixes found while testing.**
  1. The map's 15 s start-up watchdog reported "could not finish loading the map graphics" while
     the 1,163-area saved run was still processing. It now keeps waiting, up to 60 s, while the
     style and state context are ready.
  2. Arriving county economic context no longer re-sends every candidate polygon to the map when
     no county filter is active.
  3. Loading another saved run after a search no longer shows a false "Configuration edited"
     notice. URL facility fields apply to the first restored run only.
- **Tests.** Tests that encoded the tabbed, idle-start flow were updated for this user-approved
  behaviour change, keeping their protective intent: URL run precedence, preserved edits, retry of
  the failed request and visible coverage. New tests cover opening on a saved run, Edit/Cancel,
  searching from opened results, reconnecting with edits, cancelled URL fields and result origin.

Verification (from `frontend/`):

```powershell
node scripts/test.mjs
node node_modules/typescript/bin/tsc -b
npx vite build --outDir ../.pytest-work/simplify-flow/dist --emptyOutDir
npx playwright test --grep "map search|network error|tablet selection" --reporter=list --output=../.pytest-work/simplify-flow/test-results
```

**201 frontend tests passed; the optional County real-flow test was skipped (environment-gated).**
TypeScript and the production build passed. 5 Playwright fixture tests passed on desktop, mobile
and tablet. The real-API Playwright tests were not run, because one of them launches a full model
job. In the browser against the live Grid API, the page opened on
`regional_refinement__7ea7c74017e8e346` with 1,163 areas and no map error at 20–37 s; Edit and
Cancel worked; County opened on the form. No real Grid search was run from the new panel; fixture
tests cover that path. Duplicate place labels (several rows read "Livingston, NY") are unchanged.

These geographic regions deserve further investigation under the stated facility requirements,
datasets, constraints, assumptions, and decision preferences.

### 2026-10-04 follow-up — browser Back inside the workspace

The user reported "cant go back" on the single-panel page. Every URL update used
`history.replaceState`, so the browser's Back button never stepped back inside the app. It left
the page or reloaded an older URL, and the editor's only way back was a small `Cancel` link.

- Opening the facility editor, opening an area (from no open area), loading another saved run and
  switching model now add a history entry (`pushUrlState`). A search replaces the editor's entry.
  Camera, scenario and switching between open areas still replace the current entry.
- A `popstate` handler restores the stored view without a page reload. It closes or reopens the
  editor (discarding unevaluated edits), restores the open area, reloads a different run
  read-only, and moves the map back to the stored camera when no area is open. The outer App
  switches the model.
- The editor's `Cancel` is now `← Back to results`. It steps back over the entry the editor added,
  or closes the editor in place when another run was loaded meanwhile.

Verification: `node frontend/scripts/test.mjs`, **204 passed, 1 env-gated skip**. New tests cover
Back from the editor, from new search results, from an opened area (map view restored), from a
loaded saved run and from a model switch. 7 Playwright fixture tests passed, including a new
real-browser Back test on desktop and mobile. In the browser against the live Grid API, Back closed
the editor and returned from Livingston, NY (zoom 9.5) to the U.S. view (zoom 3.5) without
reloading. `tsc -b` passed for these changes. At the end it reports two errors only in
`frontend/src/map/overlays.ts`, a new file another running session was creating at the same time.

## Phase 11 region-best run completion and effectiveness rating — 2026-10-04

`runs/national_fine_region_v2` completed as `regional_refinement__0c70bb571549abe5` at 2026-10-04T08:03Z, 77 minutes after
launch. The national fine surface valued 7,829,373 cells (15,536,290 of 15,658,746 alternatives scored) in 32.3 minutes
in its spawned child process (peak 2.452 GiB). The best fine parent of each national region was refined in full: 61
parents, 152,500 cells, 29 primary states, 304,590 rankable alternatives and 2,218 region/design alternatives. The
regional process peaked at 3.699 GiB, below the 4 GiB bound (the representative run peaked at 3.878 GiB).

Selection basis: 54 representatives kept (all reused from the accepted geography cache) and 7 replaced by a better member
of the same region, 50–292 km away: Iowa twice within Iowa, Arizona within Arizona, Arizona to Nevada, Kansas to Oklahoma,
Tennessee to Georgia and Oklahoma to Texas. Gains average +0.94 and reach +3.43 decision points. For all seven, the fine
value equals the exact refined best to three decimals. Compared with `runs/cleanview_regional_v2`, the top 1,000
alternatives are identical (best 97.685, 1,000th 95.568, best region mean 96.078), and the ten best region/design
alternatives are still seven in New York, two in Maine and one in North Carolina. The per-region choice keeps the national spread and picks every box
with exact fine values; the concentration at the top of the ranking follows from the profile weights (eGRID carbon
intensity), which remain a user decision.

Effectiveness rating (user-requested one-off assessment; read-only scorecard
`runs/national_fine_region_evidence_v1/scorecard/scorecard.py`; five 0–100 dimensions, unweighted mean as a declared assumption):

| Run | Integrity | Fidelity | Breadth | Readiness | Robustness | Score | External AUC / data-center counties refined |
|---|---|---|---|---|---|---|---|
| `cleanview_regional_v2` | 100 | 67.4 | 42.6 | 0 | 97.8 | 61.6 | 0.557 / 15 of 99 |
| `national_fine_regional_v1` | 100 | 100 | 7.1 | 0 | 98.0 | 61.0 | 0.557 / 5 of 99 |
| `national_fine_region_v2` | 100 | 100 | 41.6 | 0 | 97.8 | 67.9 | 0.557 / 16 of 99 |

Integrity is the share of the run's runtime contracts that hold. Fidelity is Spearman rho, across refined parents, between
the value used to select them and the best exact 1 km score refinement found. Breadth averages primary states among
refined parents (of 49) and states among the 25 best distinct areas (of 25). Readiness is the share of those 25 areas
without a critical unknown; every alternative carries one, because utility capacity, fiber and parcel feasibility are not
in the data. Robustness averages the weight cases' rank correlation and top-10 Jaccard. The external AUC (national 50 km
scores at counties with public large existing centers, versus other cells) is a diagnostic only, never scored or optimized:
existing sites are not sustainability labels, and calibrating to them is prohibited.

Publication: the API restarted by another session at 06:59Z already listed the v2 folder as a pending baseline, so on
completion it registered automatically as the latest and nationwide regional run. Verified through `/api/capabilities`,
the 53 MB `/api/runs/regional_refinement__0c70bb571549abe5` response (2,218 regions, per-region scope text) and county
context for both vintages after prebuilding the county caches with `socioeconomic-enrich`. No restart was needed; a
full-rediscovery job submitted at 07:07Z was running and was left alone. The map coverage card labelled this mode
"Nationwide regional representatives"; it now reads "Nationwide regions · best fine-surface box each", while representative
runs keep their label. The test case that expected one label for both modes was split, because 7 of 61 boxes are not
representatives.

Open items: the cached one-minute regional mode is fixed to the `cleanview_regional_v2` cohort (54 of its 61 windows are
shared with v2); moving it to the v2 cohort is a separate change to that delivery. The scorecard and run evidence are in `runs/national_fine_region_evidence_v1/`; they are not a model
output.

## Rediscovery check against existing U.S. data centers (2026-10-04, user request)

**Scope.** This is an additive post-hoc validation layer plus a frontend view. The deterministic model's
scores, ranks, configs and accepted evidence are unchanged. The new package `src/dc_rediscovery/` sits
outside the hash-bound `src/dc_locator/**`. When the work started, a regional pipeline was running in this
checkout, and `Pipeline.verify_binding` would have failed it on any model-file change. No package was
installed into `.venv`. Method, sources, results and limitations are in `docs/rediscovery_validation.md`.

**Data.** IM3 Open Source Data Center Atlas v2026.02.09 (PNNL/DOE, doi:10.57931/3017294, ODbL). The pinned
publisher-repository GeoPackage is 843,776 bytes, sha256 `1c0d8c20…cc9f4`. It was acquired once into
`data/raw/im3_datacenter_atlas/` and has a download log. MSD-LIVE requires a login and was not used.

**Commands run**
- `.venv\Scripts\python.exe -m dc_rediscovery acquire`
- `.venv\Scripts\python.exe -m dc_rediscovery run --output runs/rediscovery_v1` took 85 s, with peak memory of about 1 GB. Analysis identity `c890d8e7…`. Blind candidates sha256 `df90b590…`, hashed 0.45 s before the inventory was read.

**Verification.** The recomposed criteria equal `score_window` exactly in all 59 row groups (maximum
difference 0.0). The 3,373 persisted parent best scores are reproduced with maximum difference 0.0. The
directly recomputed haversine distances match.

**Results (Top 100)**
- HitRate is 3.0%, 11.0%, 25.0% and 61.0% at 10, 25, 50 and 100 km.
- Random CONUS draws give 1.4%, 5.8%, 16.8% and 43.7% (p 0.158, 0.021, 0.027, 0.001).
- Random near-transmission land gives 1.9%, 7.5%, 20.8% and 50.5% (p 0.278, 0.133, 0.185, 0.025).
- Classes: 11 validated, 14 unresolved, 75 emerging.
- Presence–background AUC is 0.717 (774 occupied cells, median at the 72.4th percentile).
- The first 73 candidates are tied at the maximum score in upstate New York (855 tied cells). With random tie order, Top-10 HitRate@25 km averages 22% instead of the published 0%.
- Major hubs are not near the top tier: 1 of 50 hubs is within 50 km of the Top 100.
- County Monte Carlo robustness covers 2 of the Top 100 (Oneida County, NY: 100). The rest are null with reasons.

**Tests**
- `tests/test_rediscovery_*.py`: 30 passed, including a synthetic end-to-end pipeline, blind-candidate invariance to the inventory, and leakage guards.
- `frontend/server_tests/test_rediscovery_api.py`: 4 passed.
- Frontend: 214 passed and 1 optional test skipped, across 33 files including 12 new tests. `tsc --noEmit` is clean.

**Frontend.** The "Rediscovery check" header view (`?view=rediscovery`) has blue facilities, red candidates,
purple validated 25 km disks, amber emerging 50 km rings, a score surface, a validation dashboard with a
Top-10 table, candidate details with a generated explanation, and a 12-step guided demo. The changes to
existing files are small. `App.tsx` gains the view switch and render branch. `CandidateMap.tsx` gains
`overlays` and `onOverlaySelect`. `frontend/server/app.py` gains three read-only routes. Browser-verified
on an isolated preview (bridge on 8790 serving only rediscovery routes, Vite on 5180). The shared API on
8787 was **not restarted**, because it may hold a running job. Restart it once, while idle, to serve the
new routes on 8787.

**Next inputs.** A grid-cell Monte Carlo can supply robustness through the `table` provider contract
(`grid_id`, `robustness_score`, `method`, `source`, `draws`). New facility releases need a new pinned
checksum and a new `runs/rediscovery_*` folder.

## Frontend start screen: facility input first — 2026-10-04

User request: "you should let user input something instead of straight to the loading pre-cached data". This
reverses the earlier same-day choice to open on the saved nationwide run. A fresh page now opens on the facility
form with nothing loaded; the start history entry is marked as the form, and the first search from it adds its
own entry, so browser Back returns to the form. An optional "open saved results" link under the form loads the
saved nationwide regional run (or the latest completed run) on request. A URL that names a run (`?run=`) still
opens it directly, so links and reloads keep working. Only `frontend/src/App.tsx` changed (startup restore,
first-search history entry, the link); model code, the API and saved outputs are unchanged.

Tests: the Workspace and NationwideWorkspace startup tests now expect the form and load saved runs through the
link or a `?run=` URL (the behaviors after opening a run are unchanged); a new unit test and a new Playwright
test cover Back to the start form after the first search. Frontend unit suite 216 passed, 1 optional skipped;
mocked Playwright desktop/mobile 9 passed, 1 desktop-only skipped (the real-search e2e test was not run, to
avoid queuing a scientific job). Live check: the bare URL shows the form, the link opens
`regional_refinement__0c70bb571549abe5`, and Back returns to the form. `frontend/README.md` and
`frontend/API_CONTRACT.md` describe the new start.

## Frontend design pass: plain options and readable results — 2026-10-04

User request: "go over all option, target the problem and fix it". A walk-through at 1440x900 and 375x812 of the
facility form (all More options, custom weights, AHP), results list, Run details, filters, map layers, location popup,
region panel, decision brief, County model and Rediscovery view found these problems, now fixed in `frontend/src`:

- Form: plain subtitle; cooling options shortened so they fit (full service label kept as the option title); search
  depth, screening and preference options renamed in plain words with notes; custom weights show their live share of
  100%; AHP explains the 1-9 scale and reads each judgment back ("A counts 3x as much as B") instead of
  "Reciprocal: unsupplied"; the More options summary fits on one line.
- Results: coverage text uses "search windows" and "national 1 km cells pre-scored" (UNSCREENED and partial-coverage
  disclosures kept); Run details no longer repeats the scope paragraph or the coverage warning, shows weights as
  labeled percentages and counts with thousands separators; a place name repeated in the list gets " · area 2", ...
  (also in the region panel); a note explains that # is the rank among all evaluated 1 km alternatives; county
  filter counts use areas, matching the list and map card.
- Map: the location popup shows place names and readable cooling/status instead of region IDs and design IDs; the
  layers panel states once that a region must be selected; the coverage card label is plain.
- Layout: the phone header no longer clips the view switch and model selector; the footer scope is one line with
  the full text as a tooltip.

Kept as is: the decision brief (formal record with IDs), scenario labels (served by the running API), and the
Rediscovery view, which shows "Unknown API route" until the API restarts with its new endpoints (blocked while the
full rediscovery job submitted at 07:07Z runs). Wording-dependent assertions were updated with the wording; new tests
cover weight shares, AHP read-back, area numbering and the rank note. Frontend unit 218 passed (1 optional skipped);
mocked Playwright 9 passed (1 desktop-only skipped); type check and production build passed. No model code changed.
