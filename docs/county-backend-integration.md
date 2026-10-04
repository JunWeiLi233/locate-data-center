# County Monte Carlo backend integration

The existing `dataclocator` backend is imported under `backend/dataclocator/`, with its original accounting, dataset joins, Monte Carlo trajectories and exact Pareto/CVaR calculations. It is packaged separately from the current `src/dc_locator` grid model and retains its own Python 3.13 dependency lock. Earlier grid code, configs, accepted phase records and run artifacts are preserved. The frontend's layout, styles, basemap and component structure are reused.

GitHub fork metadata identifies `danish-puri/locate-data-center` as a fork of **`JunWeiLi233/locate-data-center`**, default branch **`main`**. The imported PR source starts from upstream commit `29ace50e831fefda52e77e2c9a0360693e64cddb`. The user authorized merging it as an additional model. It remains an additive county comparison and does not replace the current national grid model; deployment is outside this integration.

## Setup — macOS/Linux

Use Node 22.12+ and Python 3.13 for the county backend. Do not install its dependencies into the grid model's Python 3.12 environment.

```sh
# From the repository root: create the separate backend environment.
cd backend/dataclocator
python3.13 -m venv .venv
.venv/bin/python -m pip install -r requirements.lock
.venv/bin/python -m pip install --no-deps --no-build-isolation -e .

# Acquire checksum-pinned official files, then build county joins and evidence.
.venv/bin/python -m dataclocator.cli acquire
.venv/bin/python -m dataclocator.cli preprocess
.venv/bin/python -m dataclocator.cli check-inputs

# Serve one API process; this exact frontend origin is explicitly allowed by CORS.
.venv/bin/python -m dataclocator.cli serve --host 127.0.0.1 --port 8000 --cors-origin http://127.0.0.1:5173 --cors-origin http://localhost:5173
```

In another terminal, from the repository root:

```sh
cd frontend
npm ci
cp .env.example .env.local
# Edit .env.local to set:
# Model selection uses the visible Model control or /?model=county.
# VITE_MONTE_CARLO_API_URL=http://127.0.0.1:8000
# VITE_USE_MOCK_DATA=false
npm run dev
```

Open `http://127.0.0.1:5173`. Choose **County Monte Carlo** using the header's **Model** control, or open `/?model=county`. Changing models resets run/scenario/selection state; the current workspace cancels old browser requests so late results cannot cross model boundaries. Restart Vite after changing an API URL setting. `VITE_MONTE_CARLO_API_URL` is a public browser setting, never a place for secrets. The county adapter calls `/health` and `/candidates`, submits **`POST /runs`**, polls **`GET /runs/{run_id}`**, and reads frozen per-run evidence from `/runs/{run_id}/candidates/{fips}`. It does not use the grid bridge's `/api/search` endpoints or development proxy.

**Grid model** remains the default and uses the existing bridge at port 8787. `VITE_API_BASE_URL` belongs to that bridge only. Both model adapters are compiled into the frontend; no `VITE_MODEL_BACKEND` setting is required. Mock data requires the existing explicit `VITE_USE_MOCK_DATA=true` and is never selected on a real-service failure.

## Setup — Windows PowerShell

The isolated backend requires Python 3.13, alongside the grid model's Python 3.12 environment:

```powershell
cd backend/dataclocator
py -3.13 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.lock
.venv\Scripts\python.exe -m pip install --no-deps --no-build-isolation -e .
.venv\Scripts\python.exe -m dataclocator.cli acquire
.venv\Scripts\python.exe -m dataclocator.cli preprocess
.venv\Scripts\python.exe -m dataclocator.cli serve --port 8000 --cors-origin http://127.0.0.1:5173 --cors-origin http://localhost:5173
# Separate terminal, from repository root:
cd frontend
npm.cmd ci
Copy-Item .env.example .env.local
# Optionally set the public county API URL above, then:
npm.cmd run dev
```

Acquisition requires `curl` (`curl.exe` on Windows); the CLI passes its arguments directly. The imported queue owner lock now uses `msvcrt` on Windows and `fcntl` on Unix without changing model mathematics. Windows verification found and repaired privileged-symlink assumptions in official-data tests and locale-dependent report encoding. The final Python 3.13 Windows backend suite passed 113 tests with no failures or skips; it includes frozen official-data CLI/API parity and UTF-8 report verification. One existing Starlette/httpx deprecation warning remains.

## Data roots and reproducibility

The fresh checkout deliberately contains no raw/processed data or generated outputs. The pinned [manifest](../backend/dataclocator/data/source_manifest.json) covers 19 required files from six official source families (Census, EPA, EIA, WRI, NOAA and FEMA), totaling roughly 495 MB. The unused live FEMA item response is excluded because its public usage counters change; its release/terms metadata remains recorded separately. Scientific county pages and all other source pins remain unchanged. `acquire` downloads only missing files and rejects a changed publisher payload instead of silently substituting a new release. Review a changed scientific release deliberately; do not invent synthetic replacements. Aqueduct requires attribution and adherence to the recorded source terms.

`preprocess` creates `data/processed/*.parquet`, `outputs/task2/candidates.json` and `outputs/task2/coverage.json` beneath the isolated backend. Startup verifies the pinned raw hashes, complete source/model/selection lineage and checksums of consumed derived artifacts. Saved results also require matching input identity, frozen evidence and output checksums before reuse or polling. Missing/stale data returns useful readiness/API errors; reconnect after acquiring/preprocessing and restarting the server. Optional/local inputs remain missing rather than blocking the available screening model.

If the existing standalone data is already available, the imported server can read it without copying or editing it:

```sh
# From backend/dataclocator after installing this package:
.venv/bin/python -m dataclocator.cli serve --root /Users/danishpuri/CS/projects/dataCLocator --port 8000 --cors-origin http://127.0.0.1:5173
```

That root holds any newly submitted run artifacts; use the isolated default root if you want outputs separate from the original workspace. The integration itself was developed in an isolated checkout and did not overwrite the original backend or other local changes.

## Request, progress and evidence semantics

The form exposes the actual model JSON initialized from the original explicitly labeled demonstration config. Visible MW, average-load percentage, opening year, lifetime and screening mode override their matching JSON fields. Percentage-to-utilization conversion is a transport unit conversion; the backend owns validation and all calculations. All other settings are submitted unchanged, including hours, currency/base year, real/nominal convention, discount rate, priors/source labels, dependence, separate scenario trajectories, seed, draw count, hard constraints and tolerances. Sensitivity and convergence audit flags are explicit. For a quick run use 500 draws and disable the audits; skipped audits do not claim to pass.

STRICT maps to `feasibility_mode=verified`; EXPLORATORY maps to `exploratory`. Since local power, water allocation, parcel/zoning and fiber evidence are currently unverified, strict mode legitimately returns no candidates. Exploratory rows remain conditional. The frontend does not add favorable scores, preference weights, AHP judgments or an overall recommendation to this model. Its MCDA widgets and score filter are hidden for county runs; raw distributions and expected frontier membership remain visible.

Queued/running/completed/failed states come from actual job status, without invented percentages. HTTP validation details, saturation, failure and missing-data errors are retained; retry preserves settings. Browser cancellation stops polling but does not claim to cancel server work. The existing UI preserves and labels prior results during a new request/failure. Completed cache hits work immediately; scenario switching selects an actual structural scenario from the stored run, without pooling pathways or recomputation. Frozen evidence is fetched with at most four concurrent requests and the presentation cache is bounded to eight runs.

The county API supplies representative latitude/longitude, not polygons. Unranked point markers remain visible; no parcel polygon or fake rank is inferred. Existing map/list/detail/compare controls remain in place. Unsupported mapped layers are disabled with an explanation. Source URLs and historical periods, mean/median/p05/p95/CVaR, robust frontier membership, conditional Pareto frequency and estimator intervals are displayed with units/status. Full model JSON remains inspectable/downloadable, including seed, all configuration/source labels, source hashes, scenario assumptions, exclusions and sensitivity/convergence evidence. This browser download preserves backend JSON; it does not calculate a result.

## Material limitations

- Only **45 selected contiguous-US counties** are evaluated, not the national grid model's cell/region search or all U.S. parcels. Counties are screening regions, not certified sites or a national optimum.
- PUE/WUE priors and future electricity/carbon rates are **unconfirmed demonstration assumptions**, not calibrated cooling curves or forecasts. Shared WUE yields equal direct water consumption; basin stress remains separate context. Scenario frequencies are not calibrated probabilities of future events or of being best.
- Tariffs are preliminary 2025 state retail proxies; grid factors are 2023 regional averages, with ambiguity in 15 county assignments. Utility supply, power capacity, water rights, zoning/parcel availability and redundant fiber remain unverified.
- No full TCO, embodied carbon, compatible indirect generation-water factor, heat-reuse evidence/credit, community/workforce model, sourced weather variability/outage model or reliability/Cambium trajectory is supplied. These remain visible nulls/gaps and boundary exclusions rather than invented benefits.
- The API is a local single-process MVP. One worker plus four waiting jobs, file persistence and explicit origins are supported; no authentication, deployment or distributed job service is added.

See the imported [API contract](../backend/dataclocator/docs/api.md), [model interface](../backend/dataclocator/docs/monte-carlo-interface.md), [instructions](../backend/dataclocator/md/model-agent-instructions.md) and [source dictionary](../backend/dataclocator/docs/data-dictionary.md).

## Checks

```sh
# From backend/dataclocator, with its own venv and acquired/preprocessed data:
.venv/bin/python -m pytest -q

# From frontend:
npm test
npm run build

# Opt-in real official-data React → county adapter → backend integration:
DATACLOCATOR_TEST_PYTHON="$PWD/../backend/dataclocator/.venv/bin/python" npm test -- src/components/CountyFlow.test.tsx
```

The opt-in flow uses fresh test output storage and actual frozen official inputs; it submits a 32-draw debugging run through the production adapter/API, renders 45 county results and source evidence, reloads its structural scenario and confirms a valid empty verified result. Only TCP and the WebGL renderer are replaced with test transport/rendering. Normal frontend tests use clearly labeled synthetic fixtures only to validate transport and UI behavior.

Backend/API and full React submission-to-results can be checked through ASGI/JSON-lines transport without replacing either model's environment. The final county backend suite passed 113 tests on Windows. The integrated frontend passed 175 tests and its production build; the minimal remote integration variant passed 83 tests and its production build. The real-data React-to-adapter-to-ASGI flow passed in both variants with all 45 exploratory counties plus the valid empty verified set. The current live browser also passed explicit CORS/TCP loading and WebGL rendering for all 45 counties; the saved screenshot shows conditional results with no scalar rank or score. Both production builds retain the existing bundle-size advisory. The grid model's scientific code/configs remain separate and unchanged; its original API suite passed 147 tests. Frontend regression tests continue to cover the grid adapter. No upstream CI workflow existed at the inspected base revision; available PR check runs/statuses are inspected after publication.

Datasets, processed tables, outputs, simulation arrays, environments, `.env.local`, secrets, caches and frontend build/test artifacts are ignored and excluded from the commit. Source manifests, locks, config examples and tests are committed for reproducibility.
