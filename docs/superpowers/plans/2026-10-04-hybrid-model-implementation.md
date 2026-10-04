# Hybrid Model Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox syntax for tracking.

**Goal:** Apply the approved grid-first hybrid to the existing app as its default, preserving all grid evidence while adding transparent lifetime sensitivity and physical Pareto analysis.

**Architecture:** An additive `backend/hybrid_locator` package in Python 3.13 reads a frozen native grid bridge and verified full-jurisdiction EIA prices. It reuses the county package's pure Monte Carlo/statistics kernels, exposes a separate HTTP coordinator, and delivers additional evidence to the existing presentation-only React application. The grid service and Python 3.12 science remain independent.

**Tech Stack:** Existing Python 3.13 county environment; NumPy, pandas, PyArrow, GeoPandas, FastAPI/Pydantic/Uvicorn; existing Python 3.12 grid service; React/TypeScript/Vite/Vitest.

**Approved specification:** `docs/superpowers/plans/2026-10-04-hybrid-model-design.md`.

**Workspace:** `D:/locate-data-center/.pytest-work/hybrid-model/worktree`, branch `codex/hybrid-model`, initially seeded with the current frontend in commit `66f2939`, then refreshed from the primary checkout in frontend-only baseline commits `1c430f8` and `bd193f6`. The latest refresh inventories all 193 current frontend files and preserves 26 changed/new files, including the separate rediscovery workspace. Scientific inputs and existing services come from `D:/locate-data-center`. Apply the new backend package and owned documents; apply only the Hybrid frontend delta after its latest recorded baseline, checking and merging concurrent primary edits first. No accepted run or baseline science/configuration is modified.

## Contracts and ownership

- Package: `backend/hybrid_locator/src/hybrid_locator/`; tests: `backend/hybrid_locator/tests/`.
- `contracts.py`: validated hybrid settings and alternative input records; hybrid schema version `0.1.0`, independent of source grid API/schema.
- `model.py`, `frontier.py`: engineering sensitivity, accounting, exact equivalence and blocked global dominance. No geography parsing or HTTP.
- `geography.py`, `bridge.py`: verified EIA normalization and native grid joins/provenance; no ranking mathematics.
- `store.py`, `service.py`, `api.py`, `__main__.py`: source registry/freeze/artifact integrity, asynchronous run lifecycle, grid transport proxy, CLI/server.
- `frontend/src/api/hybrid.ts`, `components/HybridEvidence.tsx`: hybrid adapter/evidence; existing App/domain/URL/form/map/list components receive bounded integration changes.
- The root owns delivery documentation, real-run acceptance, application, browser proof and cleanup. Each implementer owns only its assigned module/tests. All workers must preserve others' changes.

The frozen bridge has `schema_version`, `source_grid_run_id`, native configuration/facility/screening/coverage, source hashes, every region geometry/member identity and an `alternatives` list. Each alternative carries `candidate_id`, `region_id`, `representative_grid_id`, `facility_id`, `design_id`, `native_grid_scenario_id`, nominal PUE/WUE/basis, `grid_carbon_intensity_kg_per_mwh`, primary state identity/share/ambiguity, verified industrial price anchor, native flags/score/rank and complete source evidence. Results retain each alternative and add assessment/exclusions plus per-`rate_scenario_id` summaries. Both scenario axes enter every cache key and comparison domain.

## Task 1: Pure hybrid accounting and exact frontiers

**Create:** package metadata, `contracts.py`, `model.py`, `frontier.py`, `__init__.py`.
**Tests:** `test_model.py`, `test_frontier.py`, `test_contracts.py`.

- [x] Write meaningful failing tests for fixed/no-change accounting, IT/facility WUE, dry zero, missing anchors/FAIL/STRICT exclusions, design-specific transfer, separate scenario axes, prefix/permutation stability, exact compression and blocked tolerance dominance.

```python
def test_fixed_no_change_matches_grid_workload():
    result = evaluate_alternatives([dry, tower], fixed_settings(discount_rate=0))
    dry_values = result['scenarios'][0]['alternatives'][0]['objectives']
    assert dry_values['lifetime_operational_co2e_tonnes']['mean'] == 700800 * 1.2 * 100 / 1000 * 25
    assert dry_values['lifetime_direct_water_consumption_m3']['mean'] == 0
    assert result['scenarios'][0]['alternatives'][1]['objectives']['lifetime_direct_water_consumption_m3']['mean'] == 700800 * .3 * 25
```

- [x] Run red tests with the existing county interpreter and hybrid `src` on `PYTHONPATH`; record the expected feature-missing failure.
- [x] Implement validated fixed/sensitivity/per-design priors using named shared latent quantiles. Transfer PUE overhead and WUE exactly as approved. Preserve 2023 carbon/2025 price clocks and end-year discount exponent. Reuse `dataclocator.scenarios.sample_prior/uniform_draws` and `dataclocator.pareto.distribution_summary/bootstrap_mc_error`.
- [x] Implement exact signature grouping and a global blocked dominance function accumulating all pairwise dominators. Compare against original kernel on ties/nontransitive tolerances; never prune classes. Return all rows with `NOT_ASSESSED`/null where excluded and per-scenario physical-domain counts.
- [x] Run green tests, then spec review and code-quality review. Commit only owned package code/tests after corrections.

Command: `D:/locate-data-center/backend/dataclocator/.venv/Scripts/python.exe -m pytest backend/hybrid_locator/tests/test_model.py backend/hybrid_locator/tests/test_frontier.py backend/hybrid_locator/tests/test_contracts.py --basetemp=.pytest-work/hybrid-model-tests -q`.

## Task 2: Official prices and frozen native grid bridge

**Create:** `geography.py`, `bridge.py`; tests `test_geography.py`, `test_bridge.py`.

- [x] Write failing tests for all 51 jurisdictions, sales-weighted industrial prices, invalid/incomplete months, source/checksum/status, unique complete joins, wrong physical units/year, immutable facility/screening/native scenarios, source tampering and retained all-member context.

```python
def test_sales_weighted_price_retains_preliminary_status():
    rows = [month(price=5, sales=1), month(price=10, sales=3)]
    assert weighted_price(rows, require_months=2)['price_usd_per_mwh'] == 87.5

def test_duplicate_representative_is_rejected():
    with pytest.raises(ValueError, match='unique'):
        build_bridge(duplicated_native_run, verified_prices)
```

- [x] Observe red, then normalize the already cached checksum-bound EIA workbook and official Census state identifiers. No download, selected-cohort filtering, centroid inference or synthetic fallback.
- [x] Read root region/membership/rank/land/binding/configuration files and projected native part columns with grid-ID filters. Preserve exact representative state attribution and complete screening/provenance. Bind all native artifact hashes before enqueue. Reject mixed/missing/duplicate identities and transformed native future scenarios.
- [x] Extract the immutable facility/design/external-scenario JSON already in native `site_performance.assumptions_json`; cached regional outputs additionally have a JSON facility snapshot in `config_snapshot.json`. Cross-check these complete records and preserve `schema_version` context. Native scenario identity is `historical_static_2023`; frontend `current` is a transport alias only. This avoids adding a YAML parser or inferring assumptions from mutable configuration files.
- [x] Return all real normalized prices and checksum-bound source records without reader-side writes; persist the derived real geography during Task 5 in the isolated processed namespace. Bridges/frozen metadata belong in new hybrid runs. Keep each universe independent.
- [x] Run green unit tests and real bridge probes for both saved universes (2,326/5,748 rows), then spec and quality review and scoped commit.

Command: `D:/locate-data-center/backend/dataclocator/.venv/Scripts/python.exe -m pytest backend/hybrid_locator/tests/test_geography.py backend/hybrid_locator/tests/test_bridge.py --basetemp=.pytest-work/hybrid-bridge-tests -q`.

## Task 3: Integrity-bound hybrid runtime and HTTP coordinator

**Create:** `store.py`, `service.py`, `api.py`, `__main__.py`; tests `test_store.py`, `test_api.py`, `test_service.py`.

- [ ] Write failing tests for opaque registered source IDs, path traversal, freeze-before-enqueue, deterministic reuse, stale code/source/config, output corruption, partial writes, process restart, source/run error distinction, matching facility/preferences/mode, valid empty strict results and bound economic/layer proxy requests.

```python
def test_completed_output_tamper_is_rejected(client, completed_run):
    completed_run.summary.write_text('{}', encoding='utf-8')
    response = client.get(f'/runs/{completed_run.id}')
    assert response.status_code == 409
```

- [ ] Observe red; implement canonical run identity from frozen native bridge/settings/code/shared-kernel/environment hashes. Use owned immutable run directories and atomic writes; write completion last and validate every required hash on read/reuse/export. Enforce existing validated draw/scenario limits.
- [ ] Provide `/capabilities`, `POST /runs`, `GET /runs/{id}`, scenario results/export endpoints, plus bound source-grid layers/economic transport. Accept one facility/preference request; submit to existing grid search when no matching run exists, then freeze the completed native run and simulate. Registered roots are the two accepted regional outputs and grid service-owned completed runs; never arbitrary client paths.
- [ ] Record `source_grid_run_id`, `native_grid_scenario_id` and `rate_scenario_id` distinctly. Proxy economic context with the exact source ID and reject stale identity. Return all grid context for physically unassessed rows.
- [ ] Run green tests and real FastAPI flow; spec/quality review and scoped commit.

Command: `D:/locate-data-center/backend/dataclocator/.venv/Scripts/python.exe -m pytest backend/hybrid_locator/tests/test_store.py backend/hybrid_locator/tests/test_api.py backend/hybrid_locator/tests/test_service.py --basetemp=.pytest-work/hybrid-service-tests -q`.

## Task 4: Default Hybrid workspace and inspectable evidence

**Create:** `frontend/src/api/hybrid.ts`, `frontend/src/components/HybridEvidence.tsx`, relevant API/flow/evidence tests.
**Modify:** domain types, App, URL helpers, ConfigurationForm, RegionDetails/Comparison/RunSummary and bounded styling/integration points.

- [ ] Write failing tests for no-model Hybrid default, explicit legacy `?model=grid|county`, source/run/scenario selection resets, source-grid economic transport, two cooling alternatives, no-change rate default, original grid score label, null uncertainty, conditional feasibility, and no on-by-default frontier filters.

```typescript
it('defaults to hybrid while preserving explicit grid links', () => {
  history.replaceState(null, '', '/');
  expect(readUrlState().model).toBe('hybrid');
  history.replaceState(null, '', '/?model=grid');
  expect(readUrlState().model).toBe('grid');
});
```

- [ ] Observe red, then implement presentation/transport only. Hybrid uses grid polygons/context plus added objective distributions, upper-tail CVaR and conditional physical frontier flags/frequencies. Label original score “grid preference score”; disclose uncalibrated engineering sensitivity, source years/sector/proxy, dry dominance/common-factor invariance and unavailable temperatures.
- [ ] Expose saved universe selection and supported settings (fixed/sensitivity/per-design priors, factor dependence, discount, draw/seed, rate scenarios) through validated API requests. Retain existing land/water/infrastructure, economic filters, source inspection, export and comparison behavior.
- [ ] Run all frontend tests and production build; spec/quality review and scoped commit.

Commands: `node scripts/test.mjs`; `npm.cmd run build`, cwd worktree `frontend`.

## Task 5: Whole-model acceptance, application and delivery

**Modify:** root/backend/frontend methodology, source/schema/dictionary/limitations/integration documentation and phase handoff; new phase revision record; run index.
**Create evidence:** new `runs/hybrid_v1/` and service-owned hybrid run folders; never rewrite accepted phase evidence.

- [ ] Run full hybrid tests, legacy county tests, grid API regressions and frontend production checks; preserve executed commands/counts/results.
- [ ] Compute all alternatives in each saved universe, separately, across all nine external rate scenarios. Verify counts, exact identity/geometry/native-score/screening parity, dry/tower distinction, current invariant frontiers, pricing/source coverage, distributions/CVaR, exclusions and actual runtime/peak process memory under 4 GiB.
- [x] Persist the verified 51-jurisdiction real price normalization as a new isolated `data/processed/hybrid/` Parquet/manifest with the native schema/data-mode/grid-definition/creator metadata and complete source/checksum/method records; bind its hashes in delivery evidence. Packaged under `industrial_prices_2025_6b91cfc8629d21b8`; all records and metadata reproduce after Parquet read-back. Delivery evidence currently resides in the owned scratch lane for final preservation.
- [ ] Review the complete implementation independently for spec compliance then quality/security/science correctness; correct and rerun affected checks.
- [ ] Generate the owned package/document delta and the Hybrid frontend delta after its refreshed baseline; verify primary frontend still matches the recorded per-file seed hashes or merge concurrent edits safely. Apply only Hybrid-owned deltas/package, leaving other ongoing work intact. Run final primary checks.
- [ ] Start the hybrid API on local port 8001 using a hidden process and the existing Python 3.13 runtime. Confirm grid 8787/county 8000 remain healthy. Use the current Vite app at 5173; inspect Hybrid in Chrome, interact with both cooling designs, rate scenarios, universe/model selection and economic/source evidence, save screenshot and browser proof, and mark the demonstrated tab deliverable.
- [ ] Write a completion/freeze manifest binding code/source/environment/settings/real-run/results/browser evidence. Add run index and new revision handoff/phase record; validate every required output hash.
- [ ] Remove only owned scratch and the isolated worktree after preserving commits/evidence; unlink its dependency junction before recursive cleanup. Finish only after the full approved specification passes the evidence audit.

## Review and test discipline

Use one implementation worker at a time with explicit ownership. Review each completed task for specification compliance, then code quality, and resolve all findings before the next dependency task. No worker changes root accepted science/configuration or another worker's code. Red logs demonstrate feature absence; green logs prove required behavior. Synthetic fixtures live only in tests/fixtures or explicitly synthetic test run folders; production data never falls back to them.

## Executed baseline evidence

The isolated current frontend passed 194 tests (one optional skip); the existing county package
passed 113 tests (one existing Starlette testclient deprecation warning); the current grid API
passed all 193 tests. Initial sandbox-only Python-runtime and loopback restrictions were
resolved by running the same commands with their required local access. Logs and command
results are preserved in `.pytest-work/hybrid-model/evidence/baselines.json` and its referenced
logs, to be copied into the final new delivery run.

## Self-review

Tasks 1–2 cover science/identity/source requirements, Task 3 covers reproducible runtime/cache/security, Task 4 covers the applied default and preserved comparison/context, and Task 5 covers full-domain verification, review, application, documentation/evidence and cleanup. All eight approved acceptance criteria map to these tasks. Separate scenario axes, immutable source screening, official price status, currency timing, no double-PUE carbon and source-bound economics are explicit above.
