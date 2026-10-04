# Locator visualization API 1.7

This transport adapter reads the accepted deterministic model. It does not replace scientific schemas or recompute rankings. JSON uses snake_case; browser types use camelCase through `src/api/regions.ts`. Real responses include `schema_version: "1.7.0"`; existing 1.0–1.6 response fields remain compatible. Added fields describe regional analysis, resolution, lineage, an optional verified decision brief, independent county economic context and an optional completed nationwide regional map choice; older runs remain readable. Unknown numbers are null, never zero. Metric sources carry name, url, dataset_year, geography, resolution, method and scenario. All geometry is EPSG:4326 valid GeoJSON; one malformed region is retained with a geometry warning rather than breaking a run.

JSON bodies of at least 1 KiB may use `Content-Encoding: gzip` when the client accepts it. `Vary` includes `Accept-Encoding` and, for local browser origins, `Origin`. Decoded canonical response bytes and schema are unchanged. Required-artifact and content-identity checks also apply to cached byte responses. Identical default searches may reuse a completed baseline only after exact request and complete scientific input/output identity checks; changed revisions still calculate under a new identity.

## Endpoints

- `GET /api/capabilities`: schema_version, scope, default_configuration, cooling_options, weighting_groups, layers, scenarios, latest_run_id, optional nationwide_regional_run_id, demo.
- `POST /api/search`: body `facility` with peak_it_power_mw, average_load_percent, target_opening_year, lifetime_years, cooling, weighting, screening_mode, group_weights, ahp_matrix. Returns job_id. Backend validates bounds and builds accepted model configurations in its own run directory.
- `GET /api/jobs/{job_id}`: id, state (QUEUED/RUNNING/COMPLETE/ERROR), stage, run_id, error. Stages reflect actual pipeline execution. No synthetic percentages.
- `GET /api/runs/{run_id}?scenario=current`: run result defined below; unsupported contexts return an explicit error. Run IDs resolve through a server registry, never arbitrary paths.
- `GET /api/layers/{layer_id}?run_id=...&scenario=current&sublayer=...`: simplified GeoJSON FeatureCollection for available indicators only. No raw national rasters. Includes id, label, unit, min, max, direction, source, warning, value_property, status_property. Feature properties include value, status and explanations; grid also includes reasons and unknowns.
- `GET /api/socioeconomic?run_id=...&boundary_year=2025&scenario=current`: independent county context for the registered completed run and its loaded saved scenario, described below. Supported boundary years are exactly 2023 and 2025; 2025 is the default. Economic estimates remain 2024 SAIPE for both.
- `GET /api/exports/{run_id}/{export_id}?scenario=current`: authoritative backend output files from an allowlist.

Browser search polling has a two-hour operational allowance, separate from the 30-second timeout for each HTTP request and from scientific configuration limits. A browser abort or polling expiry does not cancel the worker job. The expiry message retains its job ID; inspect that existing job and load its `run_id` after `COMPLETE` via `/?run={run_id}&scenario=current`, without another `POST /api/search`.

## Completed nationwide regional map choice (1.7)

`nationwide_regional_run_id` is a registered completed real regional run, or null.
It prefers `national_fine_region_parents`, then a completed
`representative_parent_cells` baseline selected from national discovery. The
candidate must have all seven completed native stages, 1 km cells, a positive
region extent limit no greater than 20 km, verified bound presentation artifacts
and complete CONUS parent lineage. Global `national_fine_surface` top-window
selection is excluded from this separate map choice because it can concentrate
refinement in a few states. Unscreened national fine valuation is not a screened
regional delivery. Known external runs become available only after completing
these checks; repeated capability reads do not reorder registered user searches.

The field does not change `latest_run_id`, scientific request configuration,
ranking or computation-baseline selection. The browser opens on the facility form;
its optional "open saved results" action loads this nationwide choice (falling back
to `latest_run_id`), a URL that names a run opens that run, and a visible
map action can load it from another saved run; none queues a search. The result retains its own evaluated facility
configuration and ranks. Map counts group identical geometry across cooling
alternatives, reflect active display filters and preserve partial-coverage labels.
Absent fields in older API responses disable this optional action.

## Independent county economic context (added in 1.6)

The response has `schema_version: "1.7.0"`, `context_schema_version: "1.0.0"`, `run_id`, `scenario_id`, `available`, `boundary_year`, `socioeconomic_year`, `boundary_source_kind`, `source_metadata`, `warnings`, `coverage_summary`, `fiscal_context` and `region_counties`. `source_metadata.estimate_source` and `.boundary_source` expose names, URLs and separate years; boundary source includes kind and scale. Native checksum/code/config bindings remain available in metadata. Generalized 1:500000 Cartographic boundaries and the mismatch with 2024 estimates are disclosed. County estimates stay 2024 even when a supported future physical context is selected. The existing saved-context validator selects that context's exact region IDs and membership; an unsupported or damaged context cannot fall back to baseline regions. Client context caches must include run ID, scenario ID and boundary year.

`region_counties` is keyed by the exact persisted `region_id`. Each value lists **all positive-area overlap counties**, ordered by GEOID, through native `region_membership` joined to the canonical EPSG:5070 grid–county crosswalk. Centroids and primary county labels never determine these relations. Each county contains `county_geoid`, `county_name`, `state_fips`, optional `state_name`, years, `overlap_area_km2`, `overlap_fraction`, and these numeric fields: `poverty_rate_pct`, `income_usd`, `poverty_rate_moe_pct`, `income_moe_usd`, `poverty_percentile`, `low_income_percentile`.

The `metrics` map uses the same six field names and records `value`, `unit`, `status`, `confidence`, `missing_reason`, native `method`, `source_id`, `source_url`, `source_field` and `data_year`. Poverty/income retain `lower_90` and `upper_90` when supplied. MOEs are the **calculated half-width of the source's rounded 90% confidence bounds**, rather than direct API MOE values. Percentiles use the geography module's documented national source universe; they are economic context rather than technical suitability scores. Missing values stay null. `fiscal_context.local_revenue` and `.service_pressure` are explicitly null/unknown with reasons.

Overlap fractions divide county intersection area by the full saved member-grid geometry area. Uncovered coastal/boundary area is retained, never renormalized; `coverage_summary` reports partial regions and the denominator. A selected region matches an active economic filter only when **one same overlapping county satisfies all active conditions**. Known values from different counties must not be combined to manufacture a match; unknown values cannot satisfy a condition. This filter changes presentation only. Scores, ranks, screening, weights, technical community/economic factor scores and model artifacts retain their original meaning and values.

The page consumes poverty, income, poverty percentile and low-income percentile exclusively as optional **Filter areas** thresholds and county detail evidence. It excludes `community_economic` from map controls, requests and rendering, including legacy layer selections. The existing `community_economic` endpoint and capability remain compatible for API consumers: sublayers are `poverty`, `income`, `poverty_percentile`, `low_income_percentile`; a suffix such as `@2025` chooses the county boundary year. This presentation correction changes no transport fields or schema version.

Capability availability checks explicit configuration enablement and local source inventory only; it does not claim every run's crosswalk is already built or sources checksum-verified. HTTP never acquires data. When enabled official sources are already present, the geography API may build/cache a bounded saved evaluated grid locally (up to 200,000 cells); it never loads the complete national fine surface. Missing local context returns `available: false` with reasons; unavailable layers return `422 unavailable_layer`. Damaged declared scientific/cache/source evidence returns an error. Attaching this independent context does not register a new physical model run or rewrite accepted outputs. Durable model response cache revisions refresh to 1.7 without resetting the run registry; old scientific snapshots remain readable.

## Run result

Fields: schema_version, run_id, timestamp, model_version, demo, state (SUCCESS/PARTIAL/EMPTY), scope, analyzed_cell_count, configuration, scenario_id, scenarios, analysis, analysis_resolution_m, regions, warnings, search_stages, weighting, exports. `scenarios` has the same structure as capabilities and describes this run's supported complete artifacts. The browser uses it when present and supports older responses without it. Scope names come from archived geographic extent; counts come from the actual geographic table or verified regional catalog. `analysis_resolution_m` is read from the archived grid configuration; absent resolution remains null.

Region fields: region_id, label, rank, rank_basis, overall_score, region_mean_score, pareto_optimal, centroid {lat,lon}, geometry, screening_status, design_id, scenario_id, representative_grid_id, parent_grid_id, factors, raw_metrics, verification_required, uncertainties, strengths, limitations, data_quality, sensitivity, place_label, region_states, cell_count, area_km2.

Factor fields: id (power_carbon/water/land/climate/heat_reuse/community_economic), label, score, direction (higher_is_better only), basis, sources. A raw risk metric cannot substitute for a favorable factor. Null scores remain Unknown. The bridge maps stored normalized model components, documenting any display aggregation of accepted parent-group contributions. No browser normalization or scoring is permitted.

Raw metric fields: id, label, value, unit, group, status (observed/calculated/scenario/proxy/unknown), confidence, missing_reason, sources. Sensitivity: base_rank, min_rank, max_rank, drivers, directly from accepted model outputs. Explanations contain structured backend evidence only.

Mapped potentially suitable land area uses the native `suitable_land_area_km2` key, value and provenance. Its NLCD proxy status remains explicit; mapped area does not establish obtainable, contiguous or buildable parcel acreage. Adapter cache revision 1.2.1 corrects the earlier unavailable field alias without changing model data or ranks.

The accepted model has no independent region rank. `rank` and `overall_score` therefore refer to the region's representative cell/cooling alternative and `rank_basis` must say so. `region_mean_score` is separately labeled. Alternative, design and scenario remain paired. Overlapping cooling regions remain distinct IDs/geometries.

## Regional refinement (1.2)

`analysis` is null for older development/national runs. Regional runs supply `analysis_level: regional`, `parent_run_id`, `parent_run_path`, `grid_definition_id`, `cell_size_m`, `maximum_region_extent_km`, `refined_cells`, `national_cells`, `shortlisted_parent_cells`, `refined_parent_cells`, `refined_area_km2`, `shortlisted_parent_area_km2` and `ranking_universe`. Values come from `regional_catalog.json`. Counts and refined area disclose the bounded subset: unrefined shortlisted parents were not evaluated at 1 km. The 20 km maximum span per EPSG:5070 projected axis is a declared project assumption, independent of browser zoom. Rankings compare all evaluated refined alternatives, not all national 1 km cells.

`GET /api/layers/...` requires an active refinement window for regional runs. Encode `sublayer=flood@<region_id>` (or `<indicator>@<parent_grid_id>`). A plain region/parent ID uses the indicator's default sublayer. Missing selection returns `422 regional_window_required`; unknown windows and unavailable indicators are explicit errors. Only the selected batch is read; a layer cannot exceed 10,000 features. Legacy layer requests retain their original meaning. Candidate polygons remain the global refined result, while optional indicators cover one selected window.

The reader uses Parquet predicate filters for representative geography, provenance, screening and performance. Hydrated representative records and compact global ranks are combined by the exact grid/design/scenario key. Global rank/Pareto flags remain authoritative. Archived parent runs are registered for explicit lineage loading. Regional validation exports also support `model_validation_summary.json`.

## National fine surface selection (1.5)

Regional `analysis` adds nullable `selection`, `coverage_warning`, `land_search_scope` and `national_fine_surface`. The selection identifies `representative_parent_cells`, `national_fine_surface` (parents with the highest fine values) or `national_fine_region_parents` (the best fine-surface parent of each national region). Older catalogs without these fields remain readable. The surface summary carries manifest path/checksum, stage identity, method versions, `valued_cells`, `scored_alternatives`, `alternatives`, `unscored_alternatives`, `ranked_parent_windows`, `selection_limit` and explicit `screening_status: UNSCREENED`. Counts come from the checksum-bound native catalog/manifest; unavailable values remain null. The summary contains no facility score or per-cell surface scores, and the API does not load national fine Parquet tables to build a response.

Surface valuation selects parent windows for full regional evaluation. `analyzed_cell_count`, regional `refined_cells`, region ranks, MCDA scores, Pareto status and metrics describe the screened/refined outputs. The visible coverage note keeps these counts separate from unscreened valuation. In this mode the coarse national shortlist is a separate historical domain; it is not the denominator for refined parent coverage. The archived warning, actual cell size, projected region extent and evaluated ranking universe remain explicit. Optional map layers still require one bounded selected regional window.

`runs/national_fine_regional_v1` becomes a registered default only after all seven model stages complete and its surface manifest/artifacts are present with matching lineage. Until then the previous completed Cleanview baseline remains the default. The completed baseline's selector determines the wrapper used for a new request. Exact completed reuse verifies the request, current code/config/source/environment identities, regional/fine stage bindings, all output checksums and parent lineage before materializing canonical adapter bytes. Stale science inputs keep the normal new-run path; damaged evidence fails explicitly. Loading a historical saved run does not rebind it to current scientific code.

## Verified decision brief (1.3)

Run results add `decision_brief`, `decision_brief_context_id` and `decision_brief_unavailable_reason`. The first is the read-only `dc_locator.submission.build_submission_brief` output for this run's selected artifact folder; the second binds it to the UI external context independently of its stored physical `scenario_id`. Missing or unverifiable legacy submission evidence returns a null brief with the actual reason while preserving existing map/evidence outputs. Future folders without their own complete submission evidence are unavailable; evidence is never borrowed from a different scope. API response cache identities include all declared submission inputs and builder source identity.

The brief has its own `schema_version`, run/data-mode/scenario identity, facility and recorded geographic scope, recommendation, alternatives, framework, evidence, impact, risks, implementation vision and limitations. Recommendations copy persisted representative ranks, without creating an independent region rank or choosing a future scenario. `recommendation.centroid` is the actual representative cell center; `region_centroid` is a separate search-region center. Region area/member count and grid resolution remain explicit. County/state labels identify primary cell overlap and can span several counties.

`framework.criteria` transports archived leaf weights, direction, reference bounds, basis/rationale, normalized score and stored contribution. Excluded criteria retain their reasons. `impact.cooling_comparisons` carries signed, same-cell, same-scenario design differences from the backend. Null generation-water, full lifecycle, useful-heat, materials and community quantities remain Unknown. The operating vision is a proposed project plan with evidence gates, not a forecast. Synthetic brief responses retain DEMO DATA disclosure. The browser performs display formatting only.

Region `strengths` now describe positive persisted criterion contributions and their proxy boundaries. They do not assert buildability, committed water, available utility capacity or verified future performance.

The impact section also transports `total_water_consumption` as a metric object with value, unit, status, confidence and missing reason. A known total requires compatible direct and generation-water inputs; UNKNOWN remains null. Regional cache identity includes native ranked/performance/geography/provenance/screening files through catalog-declared part paths, with no recursive run-tree scan.

## Region place and membership labels (1.4)

Each region additionally carries `place_label`, `region_states`, `cell_count` and `area_km2`. These are presentation labels read from the geography and candidate-region tables, not suitability evidence or scores. `place_label` is `"{county}, {state}"` for the region's representative grid cell (its primary-overlap TIGER county name and state abbreviation, unmodified, e.g. "Trinity, CA"), or null if either part is missing. `region_states` lists the distinct member-cell state abbreviations, ordered by descending member-cell count with alphabetical tie-breaking; it is null (never a partial list) unless every member grid id resolves to a known state. On the regional-refinement path only representative-cell geography is loaded, so `region_states` is typically null there even when `place_label` resolves. `cell_count` and `area_km2` echo the candidate region's own `n_cells` and `total_area_km2`. All four are null when the underlying value is unavailable, never zero or invented. Adapter cache revision 1.4.0 adds these fields; older cached responses regenerate.

## Current capabilities

New real searches customize the national CONUS template and execute its regional refinement wrapper; the old 42-cell Texas development runs remain available by ID. A completed national evidence package is registered when present. The map displays all supplied region centroids, including representatives whose national alternative rank exceeds 20. Optional GeoJSON layers remain bounded to 10,000 features. Coverage and future contexts are run-specific; a national extent does not imply complete evidence for every metric. Strict screening can produce no candidates due to critical unknowns. Exploratory screening produces conditional search regions. Four weighting groups are energy/carbon, water stewardship, grid infrastructure and land. Climate, heat reuse and community scores are currently unavailable. Current and available 2030/2050/2080 external contexts can be displayed; 2040 is unavailable, with no interpolation. Power capacity, fiber redundancy, parcel/zoning and committed water remain unverified.

Unavailable layer data must be disabled with an explanation. Transmission distance does not permit drawing transmission lines. Heat consumers/confirmed partners cannot be invented. AHP reciprocal matrices use the actual weighting-group order; accepted model owns derived weights and consistency review. No automatic inconsistent-preference override.

## Fast Grid evaluation (1.8)

Capabilities add optional `analysis_modes` entries `{id,label,available,reason}`,
`default_analysis_mode` and `cached_regional_baseline_run_id`. The two mode IDs
are `cached_regional` and `full_rediscovery`. A search may include
`{"facility": {...}, "analysis_mode": "cached_regional"}`. An omitted mode
retains legacy full execution; the page selects the advertised fast default
when its input cache is ready. The mode is independent of the facility fields
and is omitted by the County adapter.

Fast requests evaluate the submitted facility across the complete fixed
cached regional cohort. Identical in-flight requests share a job; identical
completed requests reuse checksum-verified outputs. A separate bounded worker
and child process allow fast evaluation alongside a longer full rediscovery.
`COMPLETE` requires the result to be materialized and readable.

Fast runs add `analysis_mode: cached_regional`. Their regional analysis has
`selection: fixed_cached_cohort` and `diagnostics_status: NOT_ASSESSED`, with
actual evaluated cell/window counts, fixed-cohort coverage warning and cached
native lineage. The 1 km cell size and 20 km per-axis extent limit remain
explicit. Scores/ranks/Pareto and facility physical values come from fresh
persisted model outputs, rather than the baseline's old facility results.
Unsupported future contexts and uncomputed sensitivity ranges stay unavailable.
Optional layers still read one verified native window, and county filters
remain display-only. Older 1.x responses omit these additive fields safely.

## Rediscovery check (read-only, separate schema `1.0.0`)

These routes serve post-hoc comparisons written by `python -m dc_rediscovery run` under `runs/<id>/`, where
`<id>` is a folder name matching `^[A-Za-z0-9][A-Za-z0-9_.-]{0,79}$` and containing
`rediscovery_manifest.json`. The bridge verifies every artifact it reads against the manifest SHA-256 ledger
before serializing. A missing or changed artifact returns `422`. It never runs the analysis, never computes
scores, distances or rates, and never feeds facilities back into the model. Query parameters are refused,
and unknown IDs return `404`. The routes need no capability or scenario and do not change `/api/capabilities`.

- `GET /api/rediscovery` returns `{schema_version, analyses: [{analysis_id, analysis_name, data_mode, finished_at_utc, model_run, candidates, facility_source, available, reason}], default_analysis_id}`. The default is the newest available real analysis, or null.
- `GET /api/rediscovery/{id}` returns `{schema_version, analysis_id, analysis_name, analysis_identity, data_mode, finished_at_utc, timeline, interpretation, validation_framing, research_question, model, parameters, facility_source, results, robustness, factors, explanation_rule, places, candidates, facilities, hubs, surface, limitations, files}`.
  - `results` holds `hit_rates`, `tie_sensitivity`, `tie_blocks`, `baseline_comparison`, `presence_background`, `facility_recall`, `hub_recall`, `hub_count`, `classification_counts` (by Top N) and `nearest_distance_quantiles`.
  - Each candidate carries `rank`, `grid_id`, `lat`, `lon`, `place_label`, `design_id`, `suitability_score`, `score_percentile`, `tied_cells_at_score`, `score_rank_min/max`, `classification`, `distance_to_nearest_existing_dc_km`, `nearest_existing_dc{…}`, `existing_dc_within_km{radius: count}`, `robustness{score, status, provider, method, source, spatial_support, missing_reason, details}`, `weight_cases{retained, total, retained_ids}`, `explanation`, `strengths`, `weaknesses` and `factors[]`. Factor contributions sum to the suitability score.
  - Robustness without evidence is null with a reason, never 0.
- `GET /api/rediscovery/{id}/surface.png` returns the checksum-verified presentation image of the national score. Its corner coordinates are in the result's `surface`.

The browser adapter is `src/api/rediscovery.ts`. The **Rediscovery check** header view (`?view=rediscovery&top=N&candidate=rank`) filters the backend list by N and toggles layers only.
