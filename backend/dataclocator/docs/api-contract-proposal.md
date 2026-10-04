# Agreed HTTP API contract — implemented

The user agreed to this format before task 4 implementation. The HTTP layer now wraps the existing offline model and preserves its configuration/results. See [API usage and staged validation](api.md) for the implemented handoff; no frontend is included.

## Scope and execution

- JSON over HTTP, using the six endpoint paths below. API contract version `1.0`; existing model/results schema versions remain separate.
- Evaluate the frozen 45-county cohort. Client requests supply settings, not arbitrary datasets, source URLs, file paths or fabricated feasibility evidence.
- Asynchronous jobs: POST validates/enqueues and returns immediately; GET polls status/results. Default one active worker and four waiting jobs; queue saturation returns HTTP 503.
- Persist job metadata and artifacts in local files. Run IDs derive from validated config, dataset/input hashes, model version and audit options. Duplicate requests reuse the same pending/completed run; no duplicate execution.
- On restart, unfinished jobs become failed with `RUN_INTERRUPTED`; resubmitting the same request may retry. A complete cached run remains available after restart.
- Development defaults to localhost. CORS permits only explicit configured origins; no wildcard. No external deployment or frontend is included.

## Endpoints

| Method and path | Successful response |
|---|---|
| `GET /health` | HTTP 200 with API/model versions, readiness, queue counts and missing-input warnings; HTTP 503 if required frozen data are unavailable |
| `GET /datasets` | HTTP 200 with source manifest/releases/hashes, coverage and explicit missing-data/assumption notes |
| `GET /candidates` | HTTP 200 with the frozen 45-county evidence, FIPS strings, feasibility, coverage and provenance |
| `POST /runs` | HTTP 202 for new/queued/running jobs; HTTP 200 for an already completed identical run; returns the job envelope |
| `GET /runs/{run_id}` | HTTP 200 with the job envelope, including results only when completed or an error when failed |
| `GET /runs/{run_id}/candidates/{candidate_id}` | HTTP 200 with frozen candidate evidence and per-scenario objective summaries, Pareto membership/frequency, estimator error and exclusion reasons; HTTP 409 while pending, or when the job failed |

Unknown run/candidate IDs return HTTP 404. Candidate details remain available for candidates excluded from optimization, with reasons and no invented outcomes. Required candidate evidence is frozen per run so later preprocessing cannot change a historical run's evidence.

## Run request

```json
{
  "config": {
    "...": "the complete existing Monte Carlo configuration"
  },
  "options": {
    "sensitivity": true,
    "convergence": true
  }
}
```

The placeholder above illustrates the envelope only; use the complete executable [example request](api-request-example.json). `config` is required and has exactly the same fields/units as [the documented model config](monte-carlo-interface.md) and [monte-carlo-demo.json](../configs/monte-carlo-demo.json). `options` is optional; both audit flags default to true. Engineering priors, rates, bounds, source labels, workload, seed and monetary conventions remain explicit. A quick request can use the [500-draw smoke config](../configs/monte-carlo-smoke.json) with both audit options false.

Reject unknown fields, invalid ranges, NaN/Infinity, malformed identifiers and oversized runs. Existing limits: 10,000 draws, 12 scenarios, 50 candidates (the available cohort currently contains 45), and a 40-year horizon. Maximum request body: 1 MiB. No chance constraints from hazard scores, unsupported currencies/base years or undocumented engineering defaults.

## Job response envelope

Every successful POST/poll response has the same keys:

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
  "warnings": [
    "Engineering priors and future rates are conditional assumptions.",
    "Local power, water allocation, zoning and fiber feasibility remain unverified."
  ],
  "result": null,
  "error": null
}
```

Run ID/timestamp values above are illustrative, not actual run records. Job `status` is one of `queued`, `running`, `completed`, `failed`. UTC timestamps identify submission, worker start and terminal completion. `cached` identifies reuse of a completed result. Pending responses have null `result`/`error`; failed responses have an error object. Completed responses have the complete existing model JSON in `result`, without dropping provenance, feasibility or sensitivity/convergence evidence.

Model `result.status` can be `completed` or `no_eligible_candidates`; the latter is a successfully completed API job with an empty feasible set, not a server failure. Expected/robust frontiers and distributions stay separate by scenario. Every number is finite or null; FIPS identifiers remain strings.

## Completed result

`result` preserves the existing [result contract](monte-carlo-interface.md):

- schema/model version, run ID, seed and full validated configuration;
- dataset/input hashes, source URLs/releases, scope, excluded candidates and reasons;
- explicit objective units and monetary/physical discount boundaries;
- expected and robust frontier IDs by scenario, candidate distributions (`mean`, `median`, `p05`, `p95`, `cvar`), conditional `pareto_frequency` and Monte Carlo estimator error;
- scenario assumptions and null probability weights, sensitivity/convergence checks, feasibility, missing-data warnings and accounting exclusions.

JSON/CSV/config/report artifacts are also stored locally under `outputs/<run_id>/`; the HTTP result does not expose arbitrary filesystem paths. Download endpoints can be added later if needed, but are outside these six agreed endpoint paths.

## Error format

```json
{
  "api_version": "1.0",
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "The request contains invalid settings.",
    "details": [
      {"field": "config.cooling.pue", "message": "PUE must be at least 1."}
    ]
  }
}
```

The same error-object structure appears inside a failed job envelope. No stack traces, secrets or internal absolute paths are returned.

| HTTP status | Error class |
|---|---|
| 400 | Invalid/malformed JSON, including nonfinite constants |
| 413 | Request exceeds the body limit |
| 422 | Valid JSON with invalid/missing/unsupported settings |
| 404 | Unknown run or candidate |
| 409 | Requested candidate results unavailable while pending or after failure |
| 503 | Queue full, server not ready, or missing required frozen inputs |
| 500 | Unexpected server failure; details stay in server logs |

## Missing data and assumptions

Expose these in dataset/candidate/run responses, not just in documentation:

- Demo PUE/WUE priors and price/carbon rates remain proposed, unconfirmed assumptions. Source labels travel with every request/result.
- Local power commitments/capacity, water allocations, parcel/zoning and redundant fiber are unverified. Verified mode can return no candidates.
- Fifteen counties have grid-map ambiguity; 2025 prices are preliminary state retail proxies and grid carbon is a 2023 regional average.
- Equal WUE gives equal modeled direct water use. Basin stress is screening context, not a consumption volume/probability.
- No sampled weather/measurement error, outage model, full TCO, construction/IT embodied carbon, indirect generation-water factor or heat-reuse credit is presently supplied.
- Recommended reliability/Cambium and optional parcel/land/fiber datasets remain outside current modeled coverage.

## Stages after contract agreement

1. Add typed HTTP schemas, error mapping and read-only endpoints; test validation, missing data, strict JSON and explicit CORS.
2. Add a bounded worker/job store and POST/poll/candidate endpoints; test deduplication, caching, queue saturation, failure/restart and frozen candidate evidence.
3. Run a real-data request through HTTP, verify model-result parity/offline behavior, run all regression tests, and publish OpenAPI documentation plus curl/Python examples.

Implementation followed the user's explicit agreement to this format.
