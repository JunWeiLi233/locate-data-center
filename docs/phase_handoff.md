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


## County backend integration — 2026-10-04 (local validation, pending teammate review)

- Upstream discovered from GitHub fork metadata: `JunWeiLi233/locate-data-center`, default branch `main`; isolated feature branch `feat/integrate-county-monte-carlo` starts from `29ace50e831fefda52e77e2c9a0360693e64cddb`.
- Existing `dataclocator` backend imported as a separate Python 3.13 package under `backend/dataclocator/`. Nine core accounting/data/scenario/Pareto modules are byte-identical to the original backend. Only queue file ownership is adapted for Unix/Windows portability. Original `src/dc_locator`, baseline configs, accepted phase records and historical run outputs are not rewritten.
- The selectable county frontend adapter submits `POST /runs`, polls `GET /runs/{run_id}`, and reads frozen candidate evidence. Existing layout, styles, map/list/detail/compare components and the default grid adapter are retained. County points have no fabricated polygons, score or rank; expected/CVaR tradeoffs and source/assumption/uncertainty evidence remain explicit.
- Local checks: imported backend **81 passed**; frontend **77 passed** with the opt-in real-data flow enabled; TypeScript/Vite production builds passed for both grid-default and county-selected modes. Fresh official-data React/adapter/ASGI flow submits a 32-draw debugging run, displays all 45 counties, restores its scenario and confirms the valid empty verified-feasibility result.
- Commands: county venv `python -m pytest -q`; frontend `npm test`; `VITE_MODEL_BACKEND=monte-carlo npm run build`; `DATACLOCATOR_TEST_PYTHON=<county-venv-python> npm test`. The ASGI bridge uses a fresh owned test root, not a previously completed run or synthetic fallback.
- Limitations: sandbox rejects live loopback bind/connect; live TCP/CORS/WebGL/Playwright verification and Windows runtime validation remain local-machine checks. Original grid backend suite was not run in the county package's incompatible Python 3.13 environment. Existing MapLibre build-size and Starlette test-client deprecation warnings remain visible.
- Scientific boundaries: 45 selected counties, unconfirmed engineering/rate priors, equal modeled direct water at equal WUE, preliminary state tariff proxies, 2023 grid averages/15 ambiguous assignments, unverified local power/water/zoning/fiber. No full TCO, embodied carbon, indirect generation-water, heat-reuse or community benefits are invented.
- Acquisition/preprocessing, separate environments, backend URL and explicit CORS origins are documented in [county-backend-integration.md](county-backend-integration.md). Datasets, outputs, arrays, virtualenvs, secrets and caches are ignored and excluded from the changes.
- Publication is verified after the commit via GitHub branch SHA, PR head/base and available check-run/status metadata; no CI workflow was present at the upstream base. No merge, default-branch push or deployment is authorized.
