# Frontend verification — 2026-10-03

The separate React/TypeScript/Vite/MapLibre application is implemented and verified against the existing model. The default view fits the contiguous United States; globe is optional. Candidate polygons, centroids, ranking, raw measurements, uncertainties and source evidence come from model outputs. Synthetic fixtures require explicit demo mode and remain labeled.

## Final checks

| Check | Result |
|---|---|
| `npm.cmd test` | 69 tests passed across 7 files |
| Python `frontend/server_tests` | 35 tests passed |
| `npm.cmd run build` | Passed; emitted the MapLibre worker asset |
| Production Playwright suite at port 5174 | 8 checks passed; 2 intentional project skips |
| Backend preservation audit | 59 executable/dependency hashes and 33 baseline configuration hashes unchanged |
| Accepted Phase 7 record | SHA-256 `29d0fc1aa4ab807fd6263a011a69207377290930cc77e32452e1a9ab878bc16f`, unchanged |

The two browser skips avoid repeating the real facility submission and dedicated 900px tablet check in the mobile project. Both checks passed in the desktop project. Production browser checks cover actual MapLibre rendering, polygon/list selection, overlapping alternatives, comparison, explicit errors/empty output, future water geography, mobile U.S. fitting, tablet controls and saved-facility restoration.

Unit/API regressions cover favorable score direction, missing values versus measured zero, hard FAIL suppression, malformed results, API major versions, canceled/stale requests, AHP transitions and reciprocals, selection persistence, all-layers-off restoration, bounded caches, required artifacts, immutable configuration identity, provenance and safe exports. Independent spec and code-quality review findings were repaired and approved.

## Actual model integration

- A real browser form submitted **100 MW, 80% load, opening 2030, 25 years**, both accepted cooling assumptions, exploratory screening and equal parent-group preferences. The existing pipeline produced run `frontend_89aedec7113785ea6ecc6c80__ecc4e55d68ce5d54`: 42 cells, 84 evaluated alternatives, two conditional search regions, state PARTIAL, `demo=false`.
- A changed **120 MW / 75%** configuration produced run `frontend_584bb47b9ef9b5bf78c4ee76__02d1313e3fa321db` through the same pipeline. Original accepted outputs were preserved.
- Browser tests also read accepted run `development_exploratory__e65828f13b2ef1b2` and verify its actual geometry plus distinct current/2050 water values across 42 returned cells.

Scientific inputs and outputs created by the bridge remain in `runs/frontend_service/`. Local evidence under `frontend/output/` includes the real API responses, preservation audit and production browser screenshots. Playwright's HTML report is in `frontend/playwright-report/`.

## Interpretation and remaining limits

Coverage is 42 development cells. National model execution remains unsupported; the national basemap is context. Strict screening can return scientifically empty output because critical evidence is unknown. Exploratory polygons are search regions requiring parcel, utility, water and fiber verification.

The backend ranks representative cell/cooling alternatives rather than independently ranking regions. Climate, heat-reuse and community factor scores remain Unknown. Unavailable layer/scenario data are disabled with reasons. The frontend invents no heat consumers, transmission lines, available capacity, future interpolation or model explanations.

The build emits a bundle-size advisory: approximately 367 KB gzipped application JavaScript and a 510 KB MapLibre worker. Current geographic payloads are small; a future national visualization service should supply simplified/vector-tiled data. The current adapter rejects oversized optional GeoJSON rather than loading national scientific datasets in the browser.

See [README.md](README.md) for setup, environment configuration and test commands, and [API_CONTRACT.md](API_CONTRACT.md) for integration.
