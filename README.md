# U.S. Sustainable Data Center Location Discovery Model

`dc_locator` is an executable, deterministic potential-region locator: fixed CONUS grid → geographic
evidence → facility screening → annual energy/CO2e/water → Pareto/preferences → adjacent search regions
→ current sensitivity and reports. Regions deserve investigation under stated assumptions. They are
not approved parcels or a proven national optimum.

All nine commands work. Real model coverage is **42 Texas development cells**, two cooling designs
and an explicit historical-electricity scenario. The national grid has **79,888 cells**; national
feature/model execution fails preflight because complete coverage and vector RAM are unvalidated.
Default **STRICT** execution intentionally produces a valid empty accepted ranking. The separate
exploratory configuration exports conditional alternatives with critical UNKNOWN requirements visible.

## Optional county Monte Carlo backend

The existing 45-county `dataclocator` backend is now separately packaged under `backend/dataclocator/` and selectable in the same frontend with `VITE_MODEL_BACKEND=monte-carlo` and `VITE_MONTE_CARLO_API_URL=http://127.0.0.1:8000`. The default grid bridge remains available. See [county integration setup, validation and limitations](docs/county-backend-integration.md) for Python 3.13 installation, official data acquisition/preprocessing, explicit CORS origins and frontend startup. County results are unweighted conditional tradeoffs with unverified local feasibility, not scored or verified site recommendations.

## Install

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
.venv\Scripts\python.exe -m pytest -q --basetemp=.tmp-phase7-user -p no:cacheprovider
```

[environment.md](docs/environment.md) records package/GDAL/PROJ/GEOS versions. Raw caches and run folders
are git-ignored, so a clean checkout requires official native files or documented manual exports.

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
.venv\Scripts\python.exe -m dc_locator run --config configs/run.yaml --output runs/example
.venv\Scripts\python.exe -m dc_locator run --config configs/run_exploratory.yaml --output runs/phase7_exploratory
.venv\Scripts\python.exe -m dc_locator run --config configs/run_synthetic.yaml --output runs/phase7_synthetic
```

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
.venv\Scripts\python.exe -m dc_locator ingest --config configs/run.yaml --output runs/example
.venv\Scripts\python.exe -m dc_locator build-features --config configs/run.yaml --output runs/example
.venv\Scripts\python.exe -m dc_locator screen --config configs/run.yaml --output runs/example
.venv\Scripts\python.exe -m dc_locator simulate --config configs/run.yaml --output runs/example
.venv\Scripts\python.exe -m dc_locator rank --config configs/run.yaml --output runs/example
.venv\Scripts\python.exe -m dc_locator cluster --config configs/run.yaml --output runs/example
.venv\Scripts\python.exe -m dc_locator validate --config configs/run.yaml --output runs/example
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

## Additional county Monte Carlo model

PR #1 adds the independent `dataclocator` package under `backend/dataclocator/`.
Choose **County Monte Carlo** in the map's Model selector to compare 45 explicitly selected counties;
the deterministic grid model remains the default. County results have unweighted physical tradeoffs,
separate structural scenarios and unverified local feasibility, with no invented MCDA score or rank.
The county service uses its own Python 3.13 environment and port 8000. See
[county model setup and limitations](docs/county-backend-integration.md).
