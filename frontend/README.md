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

Open <http://127.0.0.1:5173/>. The Vite development server proxies `/api` to the loopback model service. The page opens on the facility form: enter the facility and select **Find locations**; nothing loads before that. **open saved results** under the form loads the saved nationwide regional run (or, without one, the latest completed run) advertised by the service, and a URL that names a run reopens that run directly. Loading a saved run computes nothing, and its facility card says **Saved results for these inputs**. Browser Back from the first results returns to the start form. To evaluate another facility from results, select **Edit**, change the inputs and select **Find locations**; the results stay visible below the form, and **Cancel** restores the evaluated facility. With API 1.8, Grid searches default to **Fast — re-score cached regions** (Search depth under More options): the submitted facility and preferences are recalculated on all 152,500 cached cells in 61 nationwide regional windows. The **Full — new nationwide search** option executes the longer existing pipeline and selects new refinement windows. Both modes write new outputs under `runs/frontend_service/`, retain 20 km limits per projected axis, and disclose their actual partial coverage. Jobs report actual stages and use no invented percentages.

The opening saved-run load prefers a completed nationwide regional choice advertised by API 1.7: the best fine-surface parent of each national discovery region when complete, otherwise the saved national representative refinement. Global highest-score-window refinement remains accessible by run ID, but can concentrate coverage in a few states. The page shows unique saved/filtered area counts, actual cell resolution, projected region limits and partial refinement coverage directly on the map. A visible action loads the nationwide saved areas without another calculation. National fine-surface valuation remains **UNSCREENED**, separate from screened/refined cells and the regional ranking universe. Incomplete deliveries cannot become this map choice. Older API responses without the optional field retain their previous saved-run controls.

## Environment

Copy `.env.example` to `.env.local` if needed, then restart Vite:

| Variable | Meaning |
|---|---|
| `VITE_USE_MOCK_DATA` | `false` by default; `true` explicitly enables synthetic UI fixtures and a persistent DEMO DATA banner. |
| `VITE_API_BASE_URL` | Optional API origin, without trailing slash. Empty uses same-origin `/api`. |
| `VITE_MAP_STYLE_URL` | Optional replaceable MapLibre style URL. Empty uses the bundled Census state context with terrain relief and forest canopy. A custom style supplies its own geography, so the bundled relief/forest layers and their toggles are omitted. |

Vite variables are visible in the browser. Keep private tokens outside browser configuration. There is no automatic synthetic fallback when the real service fails. The local HTTP bridge accepts loopback hosts/origins; replace its transport for an externally hosted service while preserving the API contract.

The bundled boundaries use Census 2025 TIGER/Line administrative geometry, including all 50 states and DC. State borders are edges shared by two states (including rivers and bays) and the dark line is the international border; seaward jurisdiction limits are not drawn. Zoomed views load original border detail only for visible states. A shoreline-clipped 1:500,000 cartographic backdrop depicts land at national zoom; from city zoom (9+), generated tiles of TIGER/Line land minus AREAWATER water show the actual shoreline, rivers and harbors in the contiguous U.S., DC and Hawaii (build with `frontend/scripts/build_land_detail.py`). These layers need no map token or external boundary service. Open **Map layers → About the map** for their meanings and source record. See `public/map/README.md` and `public/map/boundary-qa.json` for measured source-relative error bounds and limits; this is GIS context, not survey or parcel certification.

When online, two physical-geography layers are drawn over the land fill and beneath every result and indicator layer. Both come from keyless public tile services:

- **Terrain relief.** MapLibre hillshading computed from [AWS Open Data Terrain Tiles](https://registry.opendata.aws/terrain-tiles/) (Terrarium RGB elevation). The source is USGS 3DEP within the United States and SRTM, GMTED2010 and ETOPO1 elsewhere, so mountains outside the country and seafloor relief also appear.
- **Forest canopy.** [USFS NLCD Tree Canopy Cover 2021](https://data.fs.usda.gov/geodata/rastergateway/treecanopycover/) for the conterminous U.S., rendered by the MRLC GeoServer WMS.

Both are cartographic context only. They are not analyzed model coverage and are never read by the model. Toggle them under **Map layers → Base map**; the toggles are not stored in the URL. A failed context tile never triggers the map error state. If a service is unreachable, the map keeps the local state geometry and all results.

## Display and interpretation

- The interface is summary-first and uses one panel, not separate Facility and Results steps. A facility card summarizes the evaluated inputs with an **Edit** button that opens the form in place above the results. The form shows the four facility inputs and the cooling design; Grid search depth (fast cached regions or full rediscovery), screening policy and decision preferences sit under **More options**. Results show one compact row per search area (backend rank, place, score and status). Cell size, region extent, partial coverage and the conditional-results caveat stay visible as compact text under the list heading; model notes, search stages and weighting results are under **Run details** and display filters under **Filter areas**. The map coverage card shows counts, resolution and coverage kind, with refined-window counts and the national discovery load action under **Coverage context**. The region panel opens on score, status, rank, a cooling-design switch, the score breakdown, key physical figures and a verification checklist; all measurements and sources, ranking stability, limitations and the model record and downloads are fold-out sections. Nothing is removed: every Unknown, value status, caveat and source stays one click away.
- With API schema 1.4, rows and the region panel are labeled with the representative (best-scoring) cell's primary county and state, for example `Trinity, CA`, plus the states the region spans. These are presentation labels from the geography table, not suitability evidence; older responses keep the backend region label.
- Candidate polygons, badges, list and details share stable region IDs. Every supplied centroid gets a map marker: below zoom 5 only the ten best places carry numbered rank badges and the others show as dots; from zoom 5 every badge is numbered. Selecting a result fits its actual polygon; missing geometry retains metrics and uses only an actual reported centroid for navigation. Identical cooling regions share one results row, which shows the best-ranked design's backend rank and score; each design stays separately selectable through the region panel's cooling switch and the map's overlap menu.
- Category scores require explicitly declared `higher_is_better` direction. Missing values remain **Unknown**. Raw risks retain their physical units and are never passed off as favorable scores. Hard FAIL receives no favorable score/rank display.
- Raw measurements expose value status, confidence, missing reason and expandable provenance. Structured explanations and sensitivity ranges come from backend artifacts. Comparison is limited to three candidates and preserves backend ranking.
- Candidate, grid and environmental data use MapLibre sources/layers. Optional layers load on demand and cache by run, scenario, sublayer and selected refinement window. Selection changes use layer filters and a small selected badge source rather than reloading polygon geometry. The browser rejects optional GeoJSON payloads exceeding 10,000 features; the coarse national grid fits within this bound. Regional fine-grid indicators load only the selected bounded batch; select a region before enabling them.
- URL query parameters restore run, region, scenario, active layers and map camera. The browser's Back and Forward buttons step through views inside the page, never reloading it. Back closes the facility editor (discarding unevaluated edits, like **Back to results**). It closes an opened area and returns the map to its earlier view. After a new search or a saved-run load it returns to the previous results, which are reloaded read-only, and after a model switch it returns to the previous model. Small facility inputs are optional; geometry and secrets never enter the URL. New searches cancel stale browser requests and generation checks prevent late responses replacing newer results. A canceled browser request does not corrupt its scientific job.
- Desktop supports a collapsible control rail and detail panel. Mobile and tablet widths through 1190 px use collapsed/half/expanded sheets, touch drag, and explicit sheet controls. All map candidates also appear in normal keyboard-accessible controls. Globe has the same U.S.-only results.

The browser polls a submitted job for up to two hours, with a 30-second timeout on each API request. This is an operational allowance for the bounded regional workload (up to 200,000 refined cells), not a scientific coefficient or a promised completion time. Browser cancellation, reload or the polling limit leaves the submitted worker job running. To recover that existing job, read `GET /api/jobs/{job_id}`; after `COMPLETE`, open `/?run={run_id}&scenario=current` using its returned run ID, or use “Load latest completed run.” Loading a run performs a read and does not enqueue another search.

## Current model limits

Full nationwide rediscovery customizes the real CONUS configuration in `configs/run_national_exploratory.yaml` and execute `configs/run_regional_exploratory.yaml`. National discovery is followed by bounded 1 km refinement of representative parent cells selected for that facility and its preferences. The former default analyzed only 42 Texas development cells, which explains why every result was in Texas. Old runs remain loadable by ID. When completed, `runs/national_discovery_v2` is registered as national evidence and `runs/cleanview_regional_v2` as the preferred corrected regional baseline; historical `runs/regional_refinement_v4` remains accessible. An older saved development search cannot hide regional evidence as the latest run. Explicit run URLs continue to load that saved revision until another run is selected. The interface displays each run's actual extent, cell count and archived grid resolution. Regional results disclose refined area, shortlisted/refined parent counts, national lineage and the recorded 20 km span limit per projected axis. Map zoom changes presentation only. Fine ranks compare the evaluated subset; unrefined shortlisted cells remain unassessed at 1 km. National discovery can be explicitly loaded from the lineage panel. A national grid does not imply complete nationwide source evidence for every metric. Strict screening can return no regions because critical evidence is unresolved; exploratory mode produces conditional search areas. Search polygons and centroids are not approved parcels.

The accepted backend ranks cell/cooling alternatives and then clusters them; it does not separately rank regions. Badges and the displayed decision score therefore refer to each region's **representative alternative**. Region mean score is displayed separately. Power/carbon and land factors map stored normalized components; the water factor is a documented presentation aggregation of stored normalized leaves using archived local weights. Climate, heat reuse and community scores remain Unknown because the accepted profile does not supply them.

External water contexts are available only when that run has supported, complete Current/2030/2050/2080 outputs and BAU/OPT/PES pathways. The initial national template disables future execution; the dropdown reflects that run rather than offering older development-run outputs. 2040 is unavailable; no interpolation occurs. Historical eGRID reuse and constant cooling assumptions are scenario assumptions, not future electricity forecasts. Flood and wildfire are separate indicators. Unavailable hurricane, drought, future hazard and heat-consumer geometry are disabled with reasons. Transmission proximity is a cell-level proxy; no transmission line or available utility capacity is invented.

AHP input uses the backend's four actual parent groups. The interface constructs reciprocal comparisons; the existing backend computes weights and consistency. Inconsistent preferences require review with the actual returned consistency ratio, with no automatic override. Utility capacity, committed water, data-center fiber, parcel ownership and zoning remain verification requirements.

Optional satellite imagery, geocoding, run-to-run comparison and animated presentation stories are not included. The working geographic analysis interface and existing output exports take priority.

County economic context uses **2024 Census SAIPE estimates** and separately labeled **2025 (default) or 2023 Census cartographic boundaries**, generalized at 1:500,000. Poverty, median household income and their supplied percentiles appear in **Filter areas**, with supporting county evidence in area details. They are outside technical MCDA and the Community / Economic factor remains Unknown. Source links, metric status, confidence and recorded MOE calculation methods accompany the estimates. Boundary vintage is selected with the county filters. County economic overlays are absent from **Map layers**, and legacy county-layer URLs cannot request or render them.

Optional minimum poverty rate, maximum median household income, minimum poverty percentile and minimum low-income percentile thresholds filter the list and candidate polygons only. Percentiles range from 0 to 100 and use the supplied national county comparison; higher poverty and low-income percentiles indicate greater economic disadvantage. Empty thresholds are disabled. At least one positively overlapping county must satisfy **every active condition in that same county**; missing estimates never match. The filter uses the native polygon crosswalk rather than a centroid and retains technical scores/global ranks. County requests and caches are bound to the displayed run, scenario and boundary vintage; SAIPE estimates remain 2024 in future scenarios. Details list every overlapping county, its estimate and boundary years, and overlap share against full saved member-grid geometry in EPSG:5070, retaining uncovered area. Selected details remain available when their polygon is filtered out. Fiscal significance stays **Unknown — fiscal inputs not acquired**; no tax revenue, service pressure or economic benefit is inferred. Older API/run responses keep their existing results when county context is unavailable; unsupported economic filters are disabled and no synthetic fallback is used. **Clear county filters** remains usable when an active filter's source request fails.

## Tests and build

Use **Decision brief** after loading or evaluating a run to present the six submission deliverables together: investigation geography, archived criteria/weights/contributions, source evidence and assumptions, resource impacts, risks, and a proposed operating vision. **Print decision brief** prints that view. The representative cell center and broader region center are explicitly separate; the brief retains the stored recommendation even when another region is selected on the map. Cooling differences are supplied by the backend and preserve the same cell and scenario. Missing generation-water, full lifecycle, heat reuse, materials and community benefits remain Unknown. This presentation does not change model decisions or promise outcomes over the operating lifetime.

Older saved runs keep their existing map and exports when complete verified submission inputs are unavailable; the brief displays the actual reason. Future context folders need their own complete submission evidence. Explicit synthetic brief fixtures display DEMO DATA. Region explanations now expose recorded score contributions with their proxy limitations.

From `frontend/`:

```powershell
npm.cmd test
npm.cmd run build
npm.cmd run test:e2e
```

Vitest uses a workspace-local temporary directory automatically. Browser tests use installed Chrome with WebGL; start the API and Vite servers first. Test fixtures simulate the versioned service explicitly, with DEMO DATA labeling. Browser tests also exercise the real local service, actual accepted run geometry and a real 100 MW / 80% facility submission. The first uncached scientific run can take several minutes; later identical submissions reuse validated stages. See `e2e/` for desktop, tablet and mobile acceptance flows.

From the project root:

```powershell
.venv\Scripts\python.exe -m pytest frontend/server_tests -q -p no:cacheprovider --basetemp .pytest-work/frontend-server-tests
.venv\Scripts\python.exe frontend/scripts/audit_backend.py
```

Adapter tests read real accepted outputs and verify missing values, provenance, geometry, scenarios, request validation, AHP, safe exports and HTTP routes. Loopback networking must be allowed for HTTP/browser tests. The audit checks 59 backend executable/dependency hashes, 33 baseline configuration hashes and the accepted Phase 7 record. Generated verification output is under `frontend/output/`; authoritative new scientific runs remain under `runs/frontend_service/`.

## API and organization

See [API_CONTRACT.md](API_CONTRACT.md) for the versioned transport schema. `src/api/regions.ts` is the schema adapter; `src/types/domain.ts` defines browser types. `src/map/` contains cartography/layers; `src/components/` and `src/hooks/` own interface/state; `src/mocks/` contains quarantined synthetic fixtures. `server/` is a presentation/transport bridge that calls the existing model rather than changing its mathematics.

Primary library references: [MapLibre API](https://maplibre.org/maplibre-gl-js/docs/API/classes/Map/), [Vite documentation](https://vite.dev/guide/), [React documentation](https://react.dev/learn).

## Rediscovery check view

Use **Rediscovery check** in the header (`/?view=rediscovery`) to compare the deterministic model's blind
national candidates with existing U.S. data centers from the IM3 Open Source Data Center Atlas (PNNL,
OpenStreetMap-derived, ODbL).

**Map layers.** Each can be turned on or off:

- Existing data centers (blue).
- Model candidates (red, with rank badges for the first ten).
- Validated candidates (purple disks: a facility within 25 km).
- Emerging candidates (amber dashed 50 km rings: no facility nearby).
- The model's score surface.

**Left panel.** It shows, for the chosen Top N:

- hit rates within 10, 25, 50 and 100 km against random-control means;
- a model-versus-chance chart;
- classification counts;
- the presence–background AUC;
- hubs reached;
- a Top 10 table: rank, location, suitability, robustness, nearest existing data center, distance and class.

**Candidate details.** Clicking a candidate opens its coordinates, suitability, Monte Carlo robustness (or
"Not evaluated" with the reason), classification, nearest facility, factor breakdown and a generated
"Why was this location recommended?" explanation.

**Guided demo.** It walks through 12 steps: show existing facilities, hide them, show the model surface,
reveal the candidates, reveal the facilities again, then overlap, hit rates, chance, rediscovered areas,
emerging areas and robustness.

All values come from `GET /api/rediscovery/{id}`. Restart the local API once to load these routes, while no
search job is running. See `docs/rediscovery_validation.md`.
