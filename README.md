# U.S. Sustainable Data Center Location Discovery Model

`dc_locator` is an executable, deterministic potential-region locator: fixed CONUS grid → geographic
evidence → facility screening → annual energy/CO2e/water → Pareto/preferences → adjacent search regions
→ current sensitivity and reports. Regions deserve investigation under stated assumptions. They are
not approved parcels or a proven national optimum.

The default model stage commands use **CONUS discovery**, with a separate
50 km grid of **3,384 cells covering all 48 contiguous states and DC**. The national revision uses
the existing scoring weights, required criteria and physical scenarios, with official nationwide
NLCD, eGRID, Aqueduct and EIA inputs. Optional cached hazard/climate sources are explicitly not
computed in this initial national baseline. Default **STRICT** execution keeps critical UNKNOWN
requirements excluded; **EXPLORATORY** exports conditional investigation regions.

The map's default fast Grid search re-evaluates the facility and preferences on
**152,500 cached 1 km cells in 61 nationwide regional windows**. The separate
**Full · nationwide rediscovery** option repeats national discovery and regional
refinement. Final search polygons span at most **20 km per projected axis**.
The map reports each run's fixed or newly selected partial refinement coverage;
its zoom level never sets the analytical grid resolution.

The accepted Phase 7 evidence remains **42 Texas development cells**, with its original configurations
and outputs preserved. The original 10 km national grid has **79,888 cells**. A national discovery
grid does not establish parcel feasibility, complete hazard evidence or a nationally optimal site.

## Additional county Monte Carlo model

PR #1 adds the independent `dataclocator` package under `backend/dataclocator/`.
Choose **County Monte Carlo** in the map's Model selector to compare 45 explicitly selected counties;
the deterministic grid model remains the default. County results have unweighted physical tradeoffs,
separate structural scenarios and unverified local feasibility, with no invented MCDA score or rank.
The county service uses its own Python 3.13 environment and port 8000. See
[county model setup and limitations](docs/county-backend-integration.md).

## Install

For the challenge description, six requested deliverables and grading rubric, see
[submission alignment](docs/submission_alignment.md). The new `submission` command
creates a verified JSON/Markdown/printable HTML brief from a completed saved run;
the map UI's **Decision brief** presents the same backend evidence. Remaining heat,
generation-water, lifecycle and community gaps are explicitly documented.

The project root is **`D:\locate-data-center`**. Backend code, `configs/`, cached `data/`,
scientific `runs/`, tests, documentation and the separate `frontend/` live directly here.
See [frontend setup](frontend/README.md) for the interactive map and local model API.

Use Python3.12, `uv` and PowerShell from the project directory. The global Python lacks the recorded
geospatial environment; always use the venv interpreter.

```powershell
uv venv --python 3.12 .venv
uv pip install --python .venv/Scripts/python.exe -r requirements.lock.txt
uv pip install --python .venv/Scripts/python.exe --no-deps -e .
.venv\Scripts\python.exe -m dc_locator --help
.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider --basetemp=.pytest-work/tests
```

Always pass a `--basetemp` under `.pytest-work/`. The pipeline accepts outputs only inside the project,
so with pytest's default system temp folder the pipeline tests fail.

[environment.md](docs/environment.md) records package/GDAL/PROJ/GEOS versions. Raw caches and run folders
are git-ignored, so a clean checkout requires official native files or documented manual exports.

## Repository layout

| Path | Contents |
|---|---|
| `src/dc_locator/` | Python package. `geography/` holds the grid, source adapters and features; `model/` holds screening through regions, plus `validation/`. |
| `configs/` | Run, facility, cooling, constraint, scoring and source configurations |
| `tests/` | pytest suite. Synthetic fixtures live only in `tests/fixtures/`. |
| `data/` | `raw/` cached downloads, `interim/` resumable builds, `processed/` real geography outputs. Git-ignored except small JSON manifests. |
| `runs/` | One folder per model run. [runs/README.md](runs/README.md) lists which are accepted evidence. |
| `docs/` | Methodology, contracts, dictionary, sources, limitations and the [phase handoff](docs/phase_handoff.md). `phase_records/` holds acceptance records, which the code reads. Also `research/` (per-phase source research), `specs/` (original requirements) and `superpowers/plans/` (implementation plans). |
| `frontend/` | Separate map interface and local model API. See [frontend/README.md](frontend/README.md). |
| `.pytest-work/` | The only scratch location (pytest temp folders, one-off scripts). See [its README](.pytest-work/README.md). |

`src/dc_locator/`, `configs/`, `pyproject.toml` and `requirements.lock.txt` are hash-bound by the accepted
`runs/phase7/executable_freeze_v2.json`. Changing them starts a new delivery revision. Create no new
top-level files or folders. Workspace rules for agents are in [AGENTS.md](AGENTS.md) §5.

## Data access and configuration

`configs/sources.yaml` records authoritative sources, versions and status. `configs/local_sources.json`
binds the acquired demonstration files/manifests by path, bytes and SHA256. Native parser settings,
query footprints and quality evidence are in `local_core_sources.json`, `local_expanded_sources.json`
and `local_aqueduct_source.json`. Paths resolve from the project root.

`ingest` loads and validates this existing cache; acquisition is separate. Bounded public-acquisition
APIs in geography retain native request/download manifests. It never claims to download unavailable
files. See [sources.md](docs/sources.md) and [native source research](docs/research/phase5/native_sources.md)
for official URLs, units, versions, verified acquisitions and manual paths. No forms, account creation,
click-through agreements or access-control bypasses are automated. Credentials remain in environment
variables. Missing files or mismatched identity/checksums fail; unavailable measurements remain UNKNOWN.

`configs/run.yaml` references grid/study area, native sources, facility, cooling designs, physical
scenarios, hard requirements, scoring profile, weighting mode, optional AHP and future/current-validation
settings. Facility assumptions are illustrative:100MW peak IT,0.80 average load, opening2030,25-year life
and8760 modeled hours/year. Annual PUE/WUE are constant design scenarios, not verified peak/hourly models.
Change the referenced files explicitly to evaluate another facility.

The fixed policy profile scores annual electricity CO2e, site consumption, local baseline water stress,
transmission proximity and suitable-land fraction. Equal parent groups multiply declared local water
weights. User parent weights or supplied AHP can replace equal preferences; no expert judgments are
invented. Inconsistent AHP requires review and blocks accepted MCDA ranking. Required missing metrics
produce UNRANKED without candidate-specific reweighting. Energy+carbon and area+fraction are not double-scored.

## Execute

```powershell
.venv\Scripts\python.exe -m dc_locator run --config configs/run_national.yaml --output runs/national_strict_check
.venv\Scripts\python.exe -m dc_locator run --config configs/run_national_exploratory.yaml --output runs/national_exploratory_check
.venv\Scripts\python.exe -m dc_locator run --config configs/run_synthetic.yaml --output runs/phase7_synthetic
```

`run` without flags uses `configs/run_national.yaml` and `runs/national_default_v1`.
Use a new output folder after changing model/configuration identities. Explicit
`configs/run.yaml` and `configs/run_exploratory.yaml` retain the historical development scope.
The frontend's saved national evidence is `runs/national_discovery_v2`.

`configs/grid_national.yaml` retains the fixed national origin and ID rules at 50 km resolution,
chosen as a processing-budget assumption. The native 2024 NLCD C1.1 CONUS mosaic uses WGS84 Albers;
its derived 30 m EPSG:5070 raster uses bounded nearest-neighbor reprojection with source/output
checksums and CRS in `preparation_manifest.json`. Land-class aggregation remains area weighted,
and classified land remains a geographic proxy. No missing value is extrapolated or reweighted.

Synthetic mode explicitly loads the quarantined three-cell fixture in `tests/fixtures/phase7`. Its
invented metric values test formulas, missing-water exclusion and hard land failure; they are not
geographic evidence. All exports carry `data_mode=synthetic`, outside `data/processed`. Real execution
never falls back to a fixture.

Use an owned project `runs/<name>` folder. **Use a new folder after changing code/config/environment/
grid/source identity.** Identical identity verifies output hashes and resumes. A changed identity or
corrupted stage fails rather than promoting stale AHP/future files. Accepted Phase1–6 evidence is protected.

Grid generation retains its original flags. This example preserves accepted production grid bytes:

```powershell
.venv\Scripts\python.exe -m dc_locator build-grid --grid-config configs/grid.yaml --output-dir runs/phase7_grid --skip-download
```

Its legacy default is `data/processed`; use a fresh explicit output folder to avoid replacing accepted
grid files. `--national-only` skips development subsets. National geometry is distinct from model coverage.
All other stages share `--config` and `--output`. Run them in dependency order:

```powershell
.venv\Scripts\python.exe -m dc_locator ingest --config configs/run_national.yaml --output runs/national_stages_check
.venv\Scripts\python.exe -m dc_locator build-features --config configs/run_national.yaml --output runs/national_stages_check
.venv\Scripts\python.exe -m dc_locator screen --config configs/run_national.yaml --output runs/national_stages_check
.venv\Scripts\python.exe -m dc_locator simulate --config configs/run_national.yaml --output runs/national_stages_check
.venv\Scripts\python.exe -m dc_locator rank --config configs/run_national.yaml --output runs/national_stages_check
.venv\Scripts\python.exe -m dc_locator cluster --config configs/run_national.yaml --output runs/national_stages_check
.venv\Scripts\python.exe -m dc_locator validate --config configs/run_national.yaml --output runs/national_stages_check
```

`screen`/`simulate` both require features; `rank` requires both; `cluster` actually clusters persisted
ranked cells. `validate` freshly recomputes the configured inputs and compares every persisted baseline
decision/region/membership/weight table before sensitivity exports. `run` orchestrates the stages.
Stale/missing upstream stages fail clearly.

All12 BAU/OPT/PES×2030/2040/2050/2080 water packages remain separate. Native2030/2050/2080 windows are
not individual operating years. **2040 stays UNKNOWN; no interpolation.** Annual historical-carbon
reuse is a declared constant scenario, not a forecast. NASA model/member/SSP/year is independent and
does not modify PUE/WUE. Missing inventories keep total lifecycle emissions UNKNOWN.

## Output files

| File(s) | Meaning |
|---|---|
| `us_grid_dataset.parquet`, `feature_provenance.parquet` | Geographic values/status/units/coverage/source periods/missing reasons |
| `screening_results.parquet`, `screening_eligibility.parquet` | PASS/FAIL/UNKNOWN and strict/conditional gate |
| `site_performance.parquet` | Every diagnostic grid/design/scenario annual energy,CO2e,consumption/withdrawal; diagnostics are not accepted alternatives |
| `normalized_metrics.parquet`, `pareto_results.parquet` | Fixed0–100 transforms and separate-scenario physical frontier |
| `ranked_cells.parquet`, `ranking.csv`, `weight_result.json` | Raw quantities, all contributions, actual weights, conditional/unranked flags, deterministic ranks |
| `ahp_template.json` or `ahp_result.json` | Unsupplied template or original matrix/eigenvector/consistency/review result |
| `candidate_regions.geojson`, `candidate_regions.parquet`, `region_membership.parquet` | Search zones; actual representative, member IDs, suitable-area proxy and distributions |
| `future_contexts/<pathway_year>/` | Separate decisions and full linked per-region investigation reports |
| `future_scenarios.parquet`, `lifecycle_results.parquet`, `baseline_vs_enhanced.parquet` | Source windows, independent climate, explicit annual reuse, partial LCA and comparisons |
| `sensitivity_results.parquet`, `alternative_rank_ranges.parquet`, `robustness_summary.csv`, `fixed_region_summary.csv` | Current reruns and rankability/stability; fixed baseline members remain fixed |
| `validation_report.json`, `validation_report.md` | Exact current baseline recomputation and unavailable external validation |
| `recommendation_report.md` | Baseline/future representatives, raw units, contributions, source dates/coverage, unknowns and local verification |
| `profile_snapshot.json`, `source_inventory.json`, `source_coverage.json`, `source_data_manifest.json`, `config_snapshot.json`, `stage_manifests/` | Declared policy and verified source/config/cache/output identity |
| `run_metadata.json` | Stable content-derived analysis ID, intentional execution timestamp/instance, actual code/config/source/environment hashes and phase status |

No qualifying candidates means valid empty region/membership outputs and an explanation, never a fake
winner. Exploratory regions require parcel/contiguous-land, utility connection/capacity, committed water,
diverse fiber and engineering verification. Transmission proximity is not available power, Aqueduct is
not supply, and queue MW is not guaranteed future capacity. No independent measurements justify an
overall physical accuracy claim.

Actual commands, test counts, byte repeats and memory are recorded in [phase_handoff.md](docs/phase_handoff.md)
and the accepted [Phase 7 completion record](docs/phase_records/phase_7.json). Phase6 freeze/results remain historical evidence;
this new `phase7_delivery_v1` code is not the unchanged prospective-holdout revision. Scientific detail:
[methodology](docs/methodology.md), [contracts](docs/data_contracts.md), [dictionary](docs/data_dictionary.md),
[sources](docs/sources.md), [limitations](docs/limitations.md).
# Regional refinement

Run `.venv/Scripts/python -m dc_locator refine-regions --output runs/<new-name>`
to perform national discovery and then recompute selected full parent areas on
the user-approved 1 km grid. Search polygons have a declared maximum projected
span of 20 km per axis, independent of map zoom. The frontend uses this workflow
for new searches and shows the actual bounded refinement coverage.

These geographic regions deserve further investigation under the stated
facility requirements, datasets, constraints, assumptions, and decision
preferences. They remain search areas requiring parcel, utility, water and
fiber verification.

## Existing-facility comparison and land-support revision

The Cleanview diagnosis uses public operating listings as a separate county-level
reference. It preserves capacity selection, unmatched labels, missing exact site
locations and uncomputed fine coverage. Existing development never sets model
weights or engineering coefficients. See
[the diagnosis](docs/research/cleanview_revision_2026-10-03.md) and
`runs/cleanview_revision_v1/` for findings, review, tests and the executable freeze.

New regional runs distinguish single-cell land insufficiency from multi-cell
search support, then screen complete bounded regions for total classified land.
Adequate total area remains conditional; parcel contiguity and availability
require verification. Zero area and other hard failures remain exclusions.

```powershell
.venv/Scripts/python -m dc_locator refine-regions --config configs/run_regional_exploratory.yaml --output runs/<new-name>
.venv/Scripts/python -m dc_locator compare-existing --reference data/raw/cleanview_reference/public_listing_v1/reference.json --national-run runs/national_discovery_v2 --regional-run runs/<completed-regional-run> --output runs/<new-comparison-name>
```

`compare-existing` verifies saved model hashes and reconstructs the reference
from its cached raw-page manifests before writing Parquet/CSV comparisons and
reports. It performs no download or calibration. A facility point score and
physical prediction error stay UNKNOWN without compatible independent evidence.

## County economic area filters

The page uses **2024 Census SAIPE county poverty and median household income**
in **Filter areas**, with optional minimum poverty rate, maximum income,
minimum poverty percentile and minimum low-income percentile thresholds.
County economic indicators do not paint a map overlay. The user authorized the
cached **2025** county geometry (default) and
**2023** geometry (selectable). Both are generalized Census cartographic
boundaries at 1:500,000; the requested 2024 TIGER/Line archive was not present.
Boundary and estimate years are labeled independently. These values do not
change technical screening, scores, weights or global ranks.

Build reusable context from a completed real grid without rerunning the model:

```powershell
.venv/Scripts/python -m dc_locator socioeconomic-enrich --grid runs/national_fine_regional_v1/us_grid_dataset.parquet --boundary-year 2025 --acquire
.venv/Scripts/python -m dc_locator socioeconomic-enrich --grid runs/national_fine_regional_v1/us_grid_dataset.parquet --boundary-year 2023
```

Only explicit `--acquire` permits official source acquisition; verified raw
files are reused. Configuration is `configs/socioeconomic.yaml`. Outputs under
`data/processed/socioeconomic/` retain every positive-area grid-cell × county
relationship, five-character GEOIDs, full-cell overlap fractions, missing-value
evidence and source checksums. The page joins these relationships to saved region
membership. A region matches an active economic filter when at least one
overlapping county meets all its conditions. Fiscal revenues, incentives and
costs remain unknown pending separate evidence.

## Nationwide regional map coverage

The Grid model page can load a completed nationwide regional result directly,
without another calculation. The available representative refinement has 1,163
saved search geometries from 152,500 native 1 km cells in 61 nationwide discovery
windows; primary-window labels cover 30 states. All regions retain the 20 km
projected-axis limit. The map shows saved/filtered area counts and partial
refinement coverage. The global highest-score-window run remains accessible by
ID, with its concentrated geographic coverage labeled. A newer per-national-region
fine-selector delivery becomes available only after completing native validation.
See `runs/nationwide_map_coverage_v1/` for the correction and evidence.

## Rediscovery check against existing data centers

`python -m dc_rediscovery run` scores every national 1 km cell of `runs/national_fine_regional_v1` with the
model's own function. It keeps separated Top-N candidates (at least 25 km apart) and hashes them. Only then
does it reveal 1,472 existing CONUS facilities from the IM3 Open Source Data Center Atlas (PNNL, ODbL) and
measure:

- hit rates within 10, 25, 50 and 100 km, against seeded random controls;
- presence–background AUC;
- validated, emerging and unresolved classes;
- Monte Carlo robustness where the county model applies.

Existing facilities never enter the score. The map's **Rediscovery check** view presents the results with a
guided demo. See [docs/rediscovery_validation.md](docs/rediscovery_validation.md).

```powershell
.venv\Scripts\python.exe -m dc_rediscovery run --acquire --output runs/rediscovery_v1
```
