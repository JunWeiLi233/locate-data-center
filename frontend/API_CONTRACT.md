# Locator visualization API 1.0

## Optional county adapter

`VITE_MODEL_BACKEND=monte-carlo` selects the separate `backend/dataclocator` API at `VITE_MONTE_CARLO_API_URL`. Its wire contract is JSON `api_version: "1.0"`, `POST /runs` with `{config, options}`, and `GET /runs/{run_id}` with queued/running/completed/failed envelopes. Frozen candidate evidence comes from `/runs/{run_id}/candidates/{fips}`. This adapter does not use `/api/search` or rewrite the grid API below. See [complete setup and scientific boundaries](../docs/county-backend-integration.md).

The internal frontend view adds optional `modelKind: "monte-carlo"`, `coverageUnit: "counties"`, `modelEvidence` (verbatim completed model JSON) and `structuralScenarios` (the actual evaluated IDs). Facility configuration carries optional `monteCarlo: {settingsJson, sensitivity, convergence}`. County candidate score/rank/region mean/polygon remain null; centroids are actual frozen representative points. The backend owns expected/robust frontiers, distributions and all engineering/scenario mathematics. The UI reads and labels physical values rather than synthesizing normalized favorable factors or AHP weights. No scientific grid schema or original HTTP transport below changes.

This transport adapter reads the accepted deterministic model. It does not replace scientific schemas or recompute rankings. JSON uses snake_case; browser types use camelCase through `src/api/regions.ts`. All responses include `schema_version: "1.0.0"`. Unknown numbers are null, never zero. Metric sources carry name, url, dataset_year, geography, resolution, method and scenario. All geometry is EPSG:4326 valid GeoJSON; one malformed region is retained with a geometry warning rather than breaking a run.

## Endpoints

- `GET /api/capabilities`: schema_version, scope, default_configuration, cooling_options, weighting_groups, layers, scenarios, latest_run_id, demo.
- `POST /api/search`: body `facility` with peak_it_power_mw, average_load_percent, target_opening_year, lifetime_years, cooling, weighting, screening_mode, group_weights, ahp_matrix. Returns job_id. Backend validates bounds and builds accepted model configurations in its own run directory.
- `GET /api/jobs/{job_id}`: id, state (QUEUED/RUNNING/COMPLETE/ERROR), stage, run_id, error. Stages reflect actual pipeline execution. No synthetic percentages.
- `GET /api/runs/{run_id}?scenario=current`: run result defined below; unsupported contexts return an explicit error. Run IDs resolve through a server registry, never arbitrary paths.
- `GET /api/layers/{layer_id}?run_id=...&scenario=current&sublayer=...`: simplified GeoJSON FeatureCollection for available indicators only. No raw national rasters. Includes id, label, unit, min, max, direction, source, warning, value_property, status_property. Feature properties include value, status and explanations; grid also includes reasons and unknowns.
- `GET /api/exports/{run_id}/{export_id}?scenario=current`: authoritative backend output files from an allowlist.

## Run result

Fields: schema_version, run_id, timestamp, model_version, demo, state (SUCCESS/PARTIAL/EMPTY), scope, analyzed_cell_count, configuration, scenario_id, regions, warnings, search_stages, weighting, exports.

Region fields: region_id, label, rank, rank_basis, overall_score, region_mean_score, pareto_optimal, centroid {lat,lon}, geometry, screening_status, design_id, scenario_id, factors, raw_metrics, verification_required, uncertainties, strengths, limitations, data_quality, sensitivity.

Factor fields: id (power_carbon/water/land/climate/heat_reuse/community_economic), label, score, direction (higher_is_better only), basis, sources. A raw risk metric cannot substitute for a favorable factor. Null scores remain Unknown. The bridge maps stored normalized model components, documenting any display aggregation of accepted parent-group contributions. No browser normalization or scoring is permitted.

Raw metric fields: id, label, value, unit, group, status (observed/calculated/scenario/proxy/unknown), confidence, missing_reason, sources. Sensitivity: base_rank, min_rank, max_rank, drivers, directly from accepted model outputs. Explanations contain structured backend evidence only.

The accepted model has no independent region rank. `rank` and `overall_score` therefore refer to the region's representative cell/cooling alternative and `rank_basis` must say so. `region_mean_score` is separately labeled. Alternative, design and scenario remain paired. Overlapping cooling regions remain distinct IDs/geometries.

## Current capabilities

Real analyzed coverage is 42 development cells; national map context is not national result coverage. Strict screening produces no candidates due to critical unknowns. Exploratory screening produces conditional search regions. Four weighting groups are energy/carbon, water stewardship, grid infrastructure and land. Climate, heat reuse and community scores are currently unavailable. Current and available 2030/2050/2080 external contexts can be displayed; 2040 is unavailable, with no interpolation. Power capacity, fiber redundancy, parcel/zoning and committed water remain unverified.

Unavailable layer data must be disabled with an explanation. Transmission distance does not permit drawing transmission lines. Heat consumers/confirmed partners cannot be invented. AHP reciprocal matrices use the actual weighting-group order; accepted model owns derived weights and consistency review. No automatic inconsistent-preference override.
