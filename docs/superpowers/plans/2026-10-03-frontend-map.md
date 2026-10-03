# Sustainable Data Center Locator frontend plan

**Goal:** Deliver an interactive U.S. map that displays the existing model's actual candidate polygons, decisions, measurements, uncertainties and sources. No model mathematics are rebuilt.

**Architecture:** A separate `frontend/` React/TypeScript/Vite application uses MapLibre sources and layers. A small local Python HTTP adapter reads accepted outputs and calls the existing `Pipeline` for searches. A versioned, validated API adapter separates the browser domain from backend output schemas. Demo data requires an explicit environment flag.

**Design:** Neutral cartography, ink typography, teal selection and amber conditional status. Desktop has a collapsible configuration/results rail and detail drawer; mobile has a map and adjustable bottom sheet. Initial view is the United States with no invented results. Globe is optional presentation mode.

**Important interpretation:** Real analyzed coverage currently comprises 42 development cells. The backend ranks cell/cooling alternatives rather than independently ranking clustered regions. Display representative ranks/scores with this basis and region mean separately. Missing climate, heat-reuse and community factor scores remain Unknown. Region geometry describes a search area requiring parcel verification. Basemap geography does not claim analyzed national coverage.

## Implementation

- [x] F1: Scaffold `frontend/package.json`, Vite, TypeScript, styles and shared typed domain/API contracts. Preserve backend source/configuration files.
- [x] F2: Build `frontend/src/map/` with actual Polygon/MultiPolygon data, centroid badges, stable selection, overlapping-region selector, cached optional layers, context basemap and graceful WebGL/style failure.
- [x] F3: Build `frontend/server/` HTTP adapter, jobs with actual pipeline stages, safe run registry, capabilities, scenario/layer/exports endpoints and request validation. Write generated request configs only in owned run folders.
- [x] F4: Build `frontend/src/components/`, form, results, six factors, raw metrics, uncertainty, sources and all six request states; abort stale requests and preserve previous results visibly.
- [x] F5: Integrate actual grid/environmental layers, separate climate hazards, supported future contexts, up-to-three comparison, backend-owned AHP and URL restoration.
- [x] F6: Add optional globe after working map; verify keyboard, desktop/mobile and overlapping cooling regions.
- [x] F7: Unit/component/API tests, browser acceptance flow, real existing-output check and actual model submission; production build, documentation and completion evidence.

## Verification

Use Vitest/Testing Library for domain parsing, missing/invalid geometry and values, score direction, source validation, selection, toggles, AHP reciprocal input, search states and explicit demo labeling. Use Playwright for the complete map search/select/details/unknown/compare/scenario flow and mobile sheet. Run Python adapter tests with the project virtual environment. Check backend executable/configuration hashes remain intact; no new math tests or full national dataset downloads are necessary.

## Ownership

Main agent: scaffold, shared types, client/adapter, synthetic fixtures, integration and final verification. Separate delegated tasks own map modules, HTTP bridge, and interface modules, with shared contracts established first. Review spec compliance before code quality; repair findings before completion. No commits or publishing are required by the user.
