# DataCLocator backend API — version 1.0

The agreed [contract](api-contract-proposal.md) is implemented without a frontend. It wraps the existing offline model; HTTP and CLI use the same configuration validator, calculations and cache identity. Compare a fixed cohort of 45 contiguous-US counties, not arbitrary parcels or all possible locations worldwide.

## Start and reproduce

Use Python 3.13, install `requirements.lock`, and set `PYTHONPATH=src` unless the package is installed. The backend requires the official archives and processed evidence from tasks 2–3.

```sh
python3.13 -m venv .venv
.venv/bin/python -m pip install -r requirements.lock
export PYTHONPATH=src
.venv/bin/python -m dataclocator.cli acquire
.venv/bin/python -m dataclocator.cli preprocess
.venv/bin/python -m dataclocator.cli serve --host 127.0.0.1 --port 8000 --cors-origin http://localhost:3000
```

Omit `--cors-origin` when no cross-origin client is needed; repeat it for multiple explicit origins. Alternatively set comma-separated `DATACLOCATOR_CORS_ORIGINS`. Wildcards are rejected. `DATACLOCATOR_ROOT` selects the data root when launching `uvicorn dataclocator.api:app`; the CLI uses `--root` instead. No secrets are required for frozen-input runs.

One API process owns a data root, enforced by a filesystem lock. Use one Uvicorn worker. The model worker accepts at most one active job plus four waiting jobs; change waiting capacity with `--queue-size`. Requests exceeding capacity return 503. Graceful shutdown drains accepted work. After an unexpected stop, queued/running records become failed with `RUN_INTERRUPTED`; resubmit to retry. Completed results survive restarts.

Interactive developer documentation is at `/docs`, machine-readable OpenAPI at `/openapi.json`, and a frozen copy at [openapi.json](openapi.json). These describe the backend; no product frontend is built. The HTTP layer follows the official [FastAPI lifespan documentation](https://fastapi.tiangolo.com/advanced/events/) and [Pydantic model documentation](https://docs.pydantic.dev/latest/concepts/models/).

## Submit settings and poll

`POST /runs` requires `Content-Type: application/json` with this envelope:

```json
{
  "config": {"...": "complete model configuration, not this placeholder"},
  "options": {"sensitivity": true, "convergence": true}
}
```

`config` is mandatory. All 20 configuration fields, ranges, units and nested priors are documented in [the model interface](monte-carlo-interface.md); the complete executable request is [api-request-example.json](api-request-example.json). `options` is optional, with both flags defaulting to true. Unknown fields and boolean/string coercions are rejected. Priors must include bounds, units and an explicit source or assumption label. Regional overrides must match an actual candidate FIPS or its assigned grid region. Request bodies, including streamed bodies, are limited to 1 MiB; malformed/nonfinite JSON returns 400.

Limits are 10,000 draws, 12 separate scenarios, 40 analysis years and the fixed 45-county cohort (engine maximum 50). Sensitivity compares 20/30 years, commercial tariffs, engineering dependence, grid-map envelopes and verified feasibility. Convergence compares 1,000/5,000/10,000 draws. Skipping an audit does not claim it passed; the result records empty sensitivity results or null convergence.

```sh
# Submit the full nine-scenario example with both audits enabled.
curl -sS -H 'Content-Type: application/json' --data-binary @docs/api-request-example.json http://127.0.0.1:8000/runs

# Replace the illustrative ID with the returned run_id.
curl -sS http://127.0.0.1:8000/runs/run_0123456789abcdef
curl -sS http://127.0.0.1:8000/runs/run_0123456789abcdef/candidates/01089
```

For a quick real-data run, use [api-smoke-request.json](api-smoke-request.json): 500 draws, one scenario, and both audits disabled. A complete polling client is [examples/api_client.py](../examples/api_client.py).

## Successful job response

POST returns 202 for a newly accepted or identical pending run, and 200 for a completed identical cache hit. GET `/runs/{run_id}` returns 200 for all known job states. Both use exactly this envelope:

```json
{
  "api_version": "1.0",
  "run_id": "run_0123456789abcdef",
  "status": "queued",
  "cached": false,
  "submitted_at": "2026-10-03T00:00:00Z",
  "started_at": null,
  "finished_at": null,
  "links": {
    "self": "/runs/run_0123456789abcdef",
    "candidates": "/runs/run_0123456789abcdef/candidates/{candidate_id}"
  },
  "warnings": ["Conditional assumptions and unverified feasibility remain visible."],
  "result": null,
  "error": null
}
```

IDs/timestamps above are illustrative. Status is `queued`, `running`, `completed` or `failed`. Timestamps use UTC. A completed job has the entire model result in `result` and null `error`; a failed job has null `result` and a safe error object. `cached` reports completed-cache reuse for a POST response; polling retains whether the original job was adopted from a completed CLI cache.

The completed [model result format](monte-carlo-interface.md) contains schema/model versions, seed, config, scenario assumptions without probability weights, dataset/input hashes, source provenance, physical/monetary units, exclusions, feasibility, distributions, expected/robust frontiers, conditional Pareto frequencies, Monte Carlo estimator error and requested audit results. Model status `no_eligible_candidates` is a successful completed job: there is no evidence-backed feasible set, rather than a server error. JSON numbers are finite or null; county FIPS remain strings.

Identity uses config + frozen dataset/derived-input hashes + model version + audit flags. Identical pending submissions are deduplicated. Per-run `candidate_evidence.json` and `input_snapshot.json` capture evidence and rates at acceptance; workers use those captured inputs even if preprocessing changes later. `results.json` is committed after all model artifacts. CLI and API results are identical under the same settings and inputs.

## Remaining endpoints

| Endpoint | Response fields and behavior |
|---|---|
| `GET /health` | `api_version`, `model_version`, `ready`, `queue: {running, queued}`, `warnings`. 200 when required frozen inputs pass startup verification; 503 otherwise. Optional/local gaps do not masquerade as input readiness failures. |
| `GET /datasets` | `api_version`, `ready`, `manifest`, `coverage`, `warnings`. Manifest contains pinned releases, SHA-256 values, source/dictionary URLs and licensing. Missing manifest/coverage is null and reported; no fabricated replacements. |
| `GET /candidates` | `api_version`, `evidence`, `warnings`. Evidence contains scope, selection, boundaries, source references and the `candidates` array with county FIPS, regional factors, climate/hazard context, feasibility, coverage and feature provenance. Missing evidence returns 503. |
| `GET /runs/{run_id}/candidates/{candidate_id}` | `api_version`, `run_id`, `candidate_id`, `evidence`, `objective_units`, `scenarios`, `exclusion_reasons`, `warnings`, `boundary_exclusions`. Each scenario has `scenario_id` and `outcome` containing the existing candidate summaries/frontier flags/estimator error; excluded outcomes are null. A run with no scenarios returns an empty scenario list and explicit exclusions. Evidence comes from the run snapshot. |

Unknown run/candidate IDs return 404. Candidate outcomes return 409 for queued/running/failed jobs; known candidates remain distinguishable from unknown candidates. Restart after restoring/reviewing frozen inputs if startup or a submission marks inputs unavailable. A fresh checkout must acquire and preprocess official files; frozen large files are intentionally ignored by Git.

## Errors

```json
{
  "api_version": "1.0",
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "The request contains invalid settings.",
    "details": [{"field": "config", "message": "PUE bounds must be between 1 and 3."}]
  }
}
```

`details` is an array of `{field, message}` and can be empty. Nested parser errors locate their field; whole-config checks can report `config` with a specific bounded-input message. Failed jobs use the same inner error shape. Internal exceptions are logged, with no traceback, secret or absolute path returned to clients.

| HTTP | Code |
|---|---|
| 400 | `INVALID_JSON` |
| 413 | `BODY_TOO_LARGE` |
| 422 | `VALIDATION_ERROR` |
| 404 | `NOT_FOUND` |
| 409 | `RESULTS_UNAVAILABLE` |
| 503 | `QUEUE_FULL` or `INPUTS_UNAVAILABLE` |
| 500 | `INTERNAL_ERROR` |

Failed-job codes are `RUN_FAILED` or `RUN_INTERRUPTED`. Retrying identical failed submissions is allowed. HTTP method errors use `HTTP_ERROR`.

## Data gaps and assumptions

All six required regional sources were acquired and joined for the 45 counties. Their pinned manifests and geographic caveats are included in API evidence. Fifteen counties have ambiguous grid mapping; tariffs are preliminary state retail proxies for 2025, grid averages are from 2023, and climate normals cannot establish annual weather variance or engineering cooling performance.

Power commitments/deliverable MW, water rights/allocations, parcel/zoning and redundant fiber remain unverified. Verified mode currently returns no candidates. Cooling and price/carbon trajectory priors remain explicitly labeled, unconfirmed demo assumptions. Equal WUE gives equal direct cooling consumption; Aqueduct stress scores are separate context, not withdrawal availability, water volume or event probability.

Not supplied: reliability/Cambium futures, sourced cooling curves/weather variability, capex/land/demand-charge/water-tariff estimates for full TCO, construction/IT embodied carbon, compatible indirect-generation consumptive-water factors, heat recipients/demand/delivery economics, or workforce/community impacts. No benefit, downtime or feasibility certificate is invented for these missing inputs. Construction, IT manufacturing, backup fuel and heat displacement remain excluded from operational accounting.

## Staged validation

Completed checks: stage 1 **16 passed**, stage 2 **5 passed**, stage 3 **1 passed**; full regression **81 passed**, with no failures or skips. Exact results are recorded in [task4-summary.json](../outputs/task4-summary.json) and the JUnit XML files below. `pip check` passed.

Stage 1 checks typed settings, read endpoints, strict/nonfinite JSON, body limits, missing inputs and explicit CORS. Stage 2 checks bounded queues, duplicate/cache reuse, failures/retries, interrupted restart, frozen evidence and exclusive process ownership. Stage 3 runs the actual 45-county data with network connections forbidden, verifies exact pure-model/CLI parity, exposes real candidate details and confirms the legitimate empty verified set. Existing accounting/geographic/scenario/Pareto/convergence tests remain part of the full regression suite.

A complete 500-draw, 25-year real-data API response can be generated with the smoke request and polling client. Generated `outputs/` artifacts are not bundled in this integration checkout. The environment used for development blocks local socket binding (`Operation not permitted`), so request/response integration was verified through FastAPI's in-process ASGI HTTP client; a live TCP/curl check remains to run on the user's machine. The tests do not replace official evidence with synthetic data. A test-client deprecation warning from the pinned Starlette/httpx compatibility layer does not affect the passing checks.

```sh
.venv/bin/python -m pytest -q tests/test_api_read.py --junitxml=outputs/task4-stage1-tests.xml
.venv/bin/python -m pytest -q tests/test_api_jobs.py --junitxml=outputs/task4-stage2-tests.xml
.venv/bin/python -m pytest -q tests/test_api_real.py --junitxml=outputs/task4-stage3-tests.xml
.venv/bin/python -m pytest -q --junitxml=outputs/task4-tests.xml
```

This is a local, single-process MVP with file persistence, not a distributed job service. No authentication or external deployment was requested or added.
