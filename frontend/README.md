# Sustainable Data Center Locator

A map-first React/TypeScript application for the existing deterministic U.S. location-discovery model. MapLibre draws returned region geometry and actual representative centroids; it does not choose locations or calculate MCDA scores. Initial view opens directly on the United States. Globe is an optional presentation view.

## Run locally

Node 22.12+ (this workspace used Node 24.14.1) and the existing project Python virtual environment are required. Open two terminals in the project root:

The project root is `D:\locate-data-center`; run all commands from this root.

```powershell
.venv\Scripts\python.exe frontend/server/app.py --port 8787
```

```powershell
cd frontend
npm.cmd ci
npm.cmd run dev
```

Open <http://127.0.0.1:5173/>. The Vite development server proxies `/api` to the loopback model service. The initial map has no candidate claims. Configure a facility and select **Find locations**, or explicitly load a completed run. Searches execute the existing pipeline with configuration and outputs owned by `runs/frontend_service/`; identical scientific identities reuse completed stages. Geography can be reused only after source/configuration/environment/output checksums match. Jobs report actual stages and use no invented percentages.

## Environment

Copy `.env.example` to `.env.local` if needed, then restart Vite:

| Variable | Meaning |
|---|---|
| `VITE_USE_MOCK_DATA` | `false` by default; `true` explicitly enables synthetic UI fixtures and a persistent DEMO DATA banner. |
| `VITE_API_BASE_URL` | Optional API origin, without trailing slash. Empty uses same-origin `/api`. |
| `VITE_MAP_STYLE_URL` | Optional replaceable MapLibre style URL. Empty uses the bundled neutral Census state context. |

Vite variables are visible in the browser. Keep private tokens outside browser configuration. There is no automatic synthetic fallback when the real service fails. The local HTTP bridge accepts loopback hosts/origins; replace its transport for an externally hosted service while preserving the API contract.

The bundled basemap is a 121 KB simplified 2023 U.S. Census state/DC geometry derived from the project's checksum-verified source. It needs no map token, remote font server or scientific dataset download. Its boundaries are context rather than parcel data. See `public/map/README.md` for provenance and simplification.

## Display and interpretation

- Candidate polygons, badges, list and details share stable region IDs. Selecting a result fits its actual polygon; missing geometry retains metrics and uses only an actual reported centroid for navigation. Identical cooling regions remain separately selectable through the overlap menu and results list.
- Category scores require explicitly declared `higher_is_better` direction. Missing values remain **Unknown**. Raw risks retain their physical units and are never passed off as favorable scores. Hard FAIL receives no favorable score/rank display.
- Raw measurements expose value status, confidence, missing reason and expandable provenance. Structured explanations and sensitivity ranges come from backend artifacts. Comparison is limited to three candidates and preserves backend ranking.
- Candidate, grid and environmental data use MapLibre sources/layers. Optional layers load on demand and cache by run, scenario and sublayer. Selection changes use layer filters and a small selected badge source rather than reloading polygon geometry. The browser rejects optional GeoJSON payloads exceeding 10,000 features; a future national service should provide simplified/tiled data.
- URL query parameters restore run, region, scenario, active layers and map camera. Small facility inputs are optional; geometry and secrets never enter the URL. New searches cancel stale browser requests and generation checks prevent late responses replacing newer results. A canceled browser request does not corrupt its scientific job.
- Desktop supports a collapsible control rail and detail panel. Mobile and tablet widths through 1190 px use collapsed/half/expanded sheets, touch drag, and explicit sheet controls. All map candidates also appear in normal keyboard-accessible controls. Globe has the same U.S.-only results.

## Current model limits

Actual analyzed coverage is **42 development cells**. National geography is visible, but national model execution is unsupported. Strict screening returns no regions because critical evidence is unresolved; exploratory mode produces conditional search areas. Search polygons and centroids are not approved parcels.

The accepted backend ranks cell/cooling alternatives and then clusters them; it does not separately rank regions. Badges and the displayed decision score therefore refer to each region's **representative alternative**. Region mean score is displayed separately. Power/carbon and land factors map stored normalized components; the water factor is a documented presentation aggregation of stored normalized leaves using archived local weights. Climate, heat reuse and community scores remain Unknown because the accepted profile does not supply them.

Supported external water contexts use actual Current/2030/2050/2080 outputs and BAU/OPT/PES pathways. 2040 is unavailable; no interpolation occurs. Historical eGRID reuse and constant cooling assumptions are scenario assumptions, not future electricity forecasts. Flood and wildfire are separate indicators. Unavailable hurricane, drought, future hazard, heat-consumer and community geometry are disabled with reasons. Transmission proximity is a cell-level proxy; no transmission line or available utility capacity is invented.

AHP input uses the backend's four actual parent groups. The interface constructs reciprocal comparisons; the existing backend computes weights and consistency. Inconsistent preferences require review with the actual returned consistency ratio, with no automatic override. Utility capacity, committed water, data-center fiber, parcel ownership and zoning remain verification requirements.

Optional satellite imagery, geocoding, run-to-run comparison and animated presentation stories are not included. The working geographic analysis interface and existing output exports take priority.

## Tests and build

From `frontend/`:

```powershell
npm.cmd test
npm.cmd run build
npm.cmd run test:e2e
```

Vitest uses a workspace-local temporary directory automatically. Browser tests use installed Chrome with WebGL; start the API and Vite servers first. Test fixtures simulate the versioned service explicitly, with DEMO DATA labeling. Browser tests also exercise the real local service, actual accepted run geometry and a real 100 MW / 80% facility submission. The first uncached scientific run can take several minutes; later identical submissions reuse validated stages. See `e2e/` for desktop, tablet and mobile acceptance flows.

From the project root:

```powershell
.venv\Scripts\python.exe -m pytest frontend/server_tests -q -p no:cacheprovider --basetemp runs/frontend_service/server_test_tmp
.venv\Scripts\python.exe frontend/scripts/audit_backend.py
```

Adapter tests read real accepted outputs and verify missing values, provenance, geometry, scenarios, request validation, AHP, safe exports and HTTP routes. Loopback networking must be allowed for HTTP/browser tests. The audit checks 59 backend executable/dependency hashes, 33 baseline configuration hashes and the accepted Phase 7 record. Generated verification output is under `frontend/output/`; authoritative new scientific runs remain under `runs/frontend_service/`.

## API and organization

See [API_CONTRACT.md](API_CONTRACT.md) for the versioned transport schema. `src/api/regions.ts` is the schema adapter; `src/types/domain.ts` defines browser types. `src/map/` contains cartography/layers; `src/components/` and `src/hooks/` own interface/state; `src/mocks/` contains quarantined synthetic fixtures. `server/` is a presentation/transport bridge that calls the existing model rather than changing its mathematics.

Primary library references: [MapLibre API](https://maplibre.org/maplibre-gl-js/docs/API/classes/Map/), [Vite documentation](https://vite.dev/guide/), [React documentation](https://react.dev/learn).
