# Data dictionary

Column reference for accepted grid, geography, model, temporal, validation and delivery files.
For scientific definitions and current versioned contracts, see `docs/data_contracts.md`; this
document is the quick-lookup table AGENTS.md section 11 requires separately from it.

## `data/processed/us_grid.parquet`, `us_grid__dev_tiny.parquet`, `us_grid__dev_default.parquet`

GeoParquet, one row per grid cell, sorted by `(row, col)`. Geometry column: `geometry` (Polygon, EPSG:5070).

| Column | Type | Unit | Nullable |
|---|---|---|---|
| `grid_id` | string | -- | no (primary key) |
| `grid_definition_id` | string | -- | no |
| `row` | int32 | -- | no |
| `col` | int32 | -- | no |
| `tile_id` | string | -- | no |
| `geometry` | Polygon (EPSG:5070) | metres | no |
| `cell_area_km2` | float64 | km² | no |
| `study_area_intersection_km2` | float64 | km² | no |
| `study_area_frac` | float64 | fraction (0-1) | no |
| `is_boundary_cell` | bool | -- | no |
| `centroid_x_m` | float64 | metres (EPSG:5070) | no |
| `centroid_y_m` | float64 | metres (EPSG:5070) | no |
| `centroid_lat` | float64 | degrees (EPSG:4326) | no |
| `centroid_lon` | float64 | degrees (EPSG:4326) | no |
| `rep_point_lat` | float64 | degrees (EPSG:4326) | no |
| `rep_point_lon` | float64 | degrees (EPSG:4326) | no |
| `state_fips_primary` | string(2) | -- | no |
| `state_abbr_primary` | string(2) | -- | no |
| `state_share_primary_frac` | float64 | fraction (0-1) | no |
| `state_fips_all` | string | -- | no |
| `n_states` | int64 | count | no |
| `county_geoid_primary` | string(5) | -- | yes (see `docs/limitations.md`) |
| `county_name_primary` | string | -- | yes |
| `county_share_primary_frac` | float64 | fraction (0-1) | yes |
| `county_geoid_all` | string | -- | yes |
| `n_counties` | int64 | count | no (0 in the null-county case) |
| `data_mode` | string (`real`) | -- | no |

`study_area_intersection_km2` measures the CONUS administrative-boundary intersection, including mapped
inland/coastal water. It is not land-only or developable-land area; Phase 2 land-cover masking is required.

File-level Parquet key-value metadata: `dc_locator.schema=GridCell`,
`dc_locator.schema_version=1.0.0` for the three preserved existing grid files and `1.1.0` for newly generated
grid files, `dc_locator.data_mode=real`, `dc_locator.grid_definition_id=<id>`,
`dc_locator.created_by=<...>` -- see `docs/data_contracts.md`'s "File-level Parquet metadata contract".

## `data/processed/us_grid_summary.json`

| Key | Type | Description |
|---|---|---|
| `grid_definition_id` | string | Matches every row's `grid_definition_id` in the three Parquet files. |
| `crs`, `origin_x_m`, `origin_y_m`, `cell_size_m` | -- | The grid definition actually used. |
| `boundary_source_id` | string | `"census_cartographic_boundary"`. |
| `boundary_vintage` | string | `"2023"` (GENZ2023). |
| `boundary_state_zip_sha256`, `boundary_county_zip_sha256` | string | sha256 of the exact cached source zips used for this generation. |
| `generation_stats` | object | `row_range`, `col_range`, `n_candidates_bbox`, `n_touching_boundary`, `n_zero_area_touches_excluded`, `n_excluded_by_min_intersection_threshold`, `excluded_by_threshold_total_km2`, `n_retained`. |
| `total_study_area_intersection_km2` | float | Sum of the national grid's `study_area_intersection_km2` -- administrative extent including mapped water, not land-only area. |
| `total_cell_area_km2` | float | Sum of the national grid's `cell_area_km2` (every retained cell's *full* square area, including the part outside CONUS for boundary cells). |
| `per_state_cell_counts` | object | `state_fips_primary -> cell count`, national grid only. |
| `files` | object | Per output file: `path`, `n_cells`, `sha256`. |

## `data/raw/census_cartographic_boundary/download_log.json`

Array of `{url, path, bytes, sha256, retrieved_at_utc, notes}` -- one entry per cached source file
(AGENTS.md section 4's download-manifest contract). See `docs/sources.md`.
# Phase 2 geographic features (2026-10-03)

`geography.features.build_features(grid, source_inputs, output_dir, *, study_geometry=None,
cache_dir=None, tile_size_cells=625, resume=True, progress=None)` writes `us_grid_dataset.parquet`,
`feature_provenance.parquet`, `coverage_report.json`, and `data_manifest.json`; it also returns the
wide GeoDataFrame. `grid` accepts a Phase 1 GeoParquet path or GeoDataFrame. `study_geometry` is
the CONUS boundary in EPSG:5070; by default the cached Phase 1 Census boundary is loaded.
`default_source_inputs(project_root=None)` discovers cached official inputs and metadata without
network calls. Explicit local sources use the same `paths` keys below. Real source configs must
carry `data_mode: real`; synthetic configs and grids are refused in real output directories.

All area fractions below use **cell square ∩ CONUS boundary**, except NLCD class fractions and
the suitable fraction, which explicitly use **valid observed NLCD class area**. Actual NLCD
areas in km² remain unextrapolated. Every metric has status/confidence/coverage companions, and
long provenance includes source field, release, native resolution, units, method and missing reason.
Numeric null means UNKNOWN; category/region strings use `value_text` in provenance. Fractions
are 0–1, scores and categories retain their native scales, ratios need not be ≤1.

| Metric(s) | Meaning / unit / aggregation |
|---|---|
| `land_cover_{water,ice_snow,developed_open,developed_low,developed_medium,developed_high,barren,deciduous_forest,evergreen_forest,mixed_forest,shrub,grassland,pasture,cultivated,woody_wetland,emergent_wetland}_frac` | Fraction of valid NLCD area in classes 11,12,21,22,23,24,31,41,42,43,52,71,81,82,90,95 respectively. Exact area intersections at pixel edges; 30 m interior pixels retain native area. Zero/off-legend/250 pixels are missing, never water. |
| `nlcd_coverage_frac`, `nlcd_observed_area_km2` | Valid NLCD area divided by study-intersection area; measured valid area in km². |
| `nlcd_water_area_km2`, `nlcd_land_area_km2` | Observed class11 area; all other valid-class area. Census study area includes water and is separately preserved. |
| `potentially_suitable_land_frac`, `suitable_land_area_km2` | Descriptive **proxy**: valid classes excluding11,12,90,95 (water/ice/wetlands); fraction of mapped NLCD area and measured km². Forest, agricultural and developed land remain in the proxy. No property rights, slope, habitat, foundations or buildability inferred. |
| `protected_overlap_frac`, `padus_gap1_frac` … `padus_gap4_frac` | GAP1+2 union, and each GAP category area, divided by study-intersection area. GAP3/4 retained separately; not all PAD-US inventory polygons have GAP1 protection. `RastDrop=1` excluded per USGS flattened analysis product. |
| `padus_coverage_frac` | Study area with valid GAP1–4 classification; uncovered area remains distinct. |
| `grid_carbon_intensity_kg_per_mwh` | Historical **CO2-equivalent** proxy from EPA `SRC2ERTA`, total-output lb CO2e/MWh × exact0.45359237 kg/lb; area-weighted across primary subregion polygons. It is not future/marginal electricity carbon or a supplying-utility determination. |
| `grid_co2_intensity_kg_per_mwh` | EPA `SRCO2RTA`, CO2-only historical rate with same lb→kg conversion. Never substituted for CO2e. |
| `egrid_subregion_primary`, `egrid_n_subregions`, `egrid_subregion_shares_json` | Largest-area primary map association (lexicographic tie), distinct regions and `{region:study_area_share}`. Geographic region mixing does not confirm a site's actual supplying utility. |
| `egrid_multiple_subregion_overlap_frac`, `egrid_multiple_subregion_labels_json` | Union area in EPA multiple-subregion polygons / study area, plus published ambiguity labels and shares. Resolve actual supplier with utility evidence before site analysis. |
| `baseline_water_stress_ratio` | Aqueduct `bws_raw` demand/renewable-supply ratio; mean over ordinary valid subbasin areas, excluding `-9999` missing and `9999` extreme-scarcity sentinel. Its own coverage excludes sentinel area; no 0–1 clipping. |
| `baseline_water_stress_score` | Separately area-weighted `bws_score` on native0–5 scale; `-9999` missing. |
| `baseline_water_stress_category`, `baseline_water_stress_category_shares_json` | Plurality-area `bws_cat`, lowest category on tie, with area shares. `-1` is valid Arid and Low Water Use; `-9999` is missing. Categories never averaged. |
| `baseline_water_stress_extreme_scarcity_frac` | Study-area share with `bws_raw=9999`, preserving severe scarcity outside ordinary ratio means. |
| `aqueduct_coverage_frac`, `aqueduct_n_subbasins`, `aqueduct_subbasin_shares_json` | Coverage including extreme sentinel, distinct `pfaf_id` and shares. Baseline rows are tiled across ID families; union/dissolve by `pfaf_id` prevents counting duplicate basin geography. Not water-supply commitment. |
| `temperature_mean_c`, `temperature_annual_max_mean_c`, `temperature_annual_min_mean_c` | NOAA1991–2020 annual temperature normals, Celsius, projected pixel-area weighted. Native1/24degree cells are retained as spatial-resolution metadata. |
| `temperature_warmest_month_daily_max_c` | `annual-tmax_max`: maximum monthly mean daily maximum normal, Celsius. It is not a single-day design extreme or hourly operating weather. |
| `flood_overlap_frac`, `flood_sfha_area_km2` | Union of known FEMA `SFHA_TF=T` polygons / study area and measured km². SFHA area is never divided by only mapped hazard area. Missing/undetermined mapping remains null. |
| `flood_coverage_frac` | Area with T/F SFHA classification excluding zoneD/OPEN WATER / study area. `U` is undetermined. This is independent of hazard overlap and independent of availability footprint. |
| `flood_surveyed_coverage_frac` | Separate NFHL Availability layer0 footprint / study area. Queried empty footprint can be observed0; outside or partial acquisition bbox is UNKNOWN. A surveyed footprint alone does not make missing hazard classification low risk. |
| `wildfire_burn_probability`, `wildfire_conditional_flame_length_ft` | Native WRC annual burn probability and conditional flame length in feet. Local-file interfaces implemented. Acquired public ImageServer exports have unverified U16 packing/scales/no-data: current real features are UNKNOWN `invalid_source_value`. BP export0..35 is rejected rather than filtered to0..1. |
| `wildfire_hazard_potential_whp2023` | Separately identified USFS **WHP2023** continuous dimensionless potential index; 270 m zonal mean. It is not WRC burn probability and cannot fill a missing WRC feature. |
| `transmission_distance_km`, `power_plant_distance_km`, `gas_pipeline_distance_km` | Minimum distance from full study-intersection polygon to mapped national EIA line/point geometry, EPSG:5070 m/1000. Proximity proxy only, no available capacity or connection claim. Native inventory coverage is not a measurable area fraction (provenance coverage null). Projection scale uncertainty ~1.6% across CONUS per `geography.distance`. |

Local path keys: NLCD`land_cover`; eGRID`workbook,regions,multiple_regions` plus
`region_field,unit,sheet`; Aqueduct`baseline` plus`layer,zip_member`; NOAA named temperature
metrics; FEMA`hazards,surveyed` plus each layer's`query_bounds_4326`; WRC named wildfire metrics
with verified native units/masks; EIA`transmission,power_plants,pipelines`; PAD-US`areas` plus
`layer`; WHP`archive` plus`zip_member`. Metadata keys:`source_name,source_url,source_version,
data_year,retrieved_at,spatial_resolution,data_mode`. A `quality_blocker` forces UNKNOWN.

Raster reads are cell-window bounded (4 million pixels maximum); projected pixel edges intersect
exactly, geographic pixel edges are densified before EPSG:5070 projection (≤0.008degrees segments).
Vector sources use spatial indexes, padded study-envelope clipping and union to avoid double counts.
National runs process at most625 cells per tile by default. Checkpoints are keyed by source-content
SHA256, selected IDs/geometry/full Phase1 attributes, grid definition, configuration, aggregation version
and relevant implementation/shared-contract hashes; checkpoint files are checksum-verified on resume.


## Phase 3 run tables (runs/phase3 and runs/phase3/exploratory)

- screening_results.parquet: ScreeningResult1.1.0, one grid_id/design_id/scenario_id/requirement row.
  value is the decision evidence; UNKNOWN has null value and missing_reason. evidence_json retains
  the complete geographic source record, including informational values with no parcel decision.
- screening_eligibility.parquet: ScreeningEligibility1.0.0, one grid/design/scenario row.
  hard_fail, critical_unknown, eligible and conditional are explicit booleans; mode is STRICT or EXPLORATORY.
- site_performance.parquet: SitePerformance1.1.0, one grid/design/scenario annual diagnostic row.
  e_it_mwh/e_facility_mwh are MWh; c_electricity_kg and c_electricity_tonnes are annual operating CO2e.
  w_site_m3/w_site_liters and w_electricity_m3/w_electricity_liters are separate consumption quantities.
  w_site_withdrawal_m3/w_site_withdrawal_liters and w_electricity_withdrawal_m3/w_electricity_withdrawal_liters are distinct withdrawal.
  peak_facility_demand_mw is null without verified peak PUE. metric_metadata_json maps every physical
  metric to status, confidence, unit, formula, missing reason and source evidence. assumptions_json
  retains full facility/design/external-scenario configuration; warnings_json preserves interpretation.
- screening_summary.json: counts, mode, critical vs informational outcomes, full configuration snapshot
  and interpretation. Performance is all-alternative diagnostics, not a list of accepted sites.

Original geographic output files and their meanings remain unchanged. Read full schemas and migration
notes in docs/data_contracts.md. The table units never equate water consumption with withdrawal.
# Phase 4 decision columns

| Column | Unit/meaning |
|---|---|
|profile_id/profile_fingerprint|Declared policy ID and SHA256 of profile bytes for file runs|
|raw_annual_electricity_co2e|tonnesCO2e annually, retained diagnostic physical value|
|raw_annual_site_water_consumption|m3_consumed annually, not withdrawal|
|raw_local_baseline_water_stress|native score0–5, local basin pressure|
|raw_transmission_proximity|km minimum study-intersection distance to mapped inventory, capacity unconfirmed|
|raw_suitable_land_fraction|0–1 NLCD proxy excluding water/ice/wetlands, contiguity unconfirmed|
|annual_electricity_co2e/annual_site_water_consumption/local_baseline_water_stress/transmission_proximity/suitable_land_fraction|0–100 fixed-reference higher-is-better preference values|
|rankable/rank_status/unranked_reason|Eligibility+complete required metrics+usable preference weights; CONDITIONAL remains visible|
|weights_used_json/contribution_by_metric_json|Complete fixed global leaf weights and every weighted contribution|
|contribution_<metric_id>/mcda_score|0–100 weighted preference points/sum; null for unranked|
|mcda_rank|1-based ordinal within scenario; deterministic tuple tie rule, null unranked|
|pareto_comparable/pareto_status/is_pareto_optimal|Physical comparison independent of AHP review; NOT_ASSESSED/FRONTIER/DOMINATED and nullable bool|
|representative_json|Actual evaluated member tuple with physical outputs, score, contributions, Pareto and screening evidence|
|metric_distributions_json|Per-member known count, min,p25,median,p75,max for active physical columns and score|
|suitable_land_area_km2 (region)|Sum of member NLCD proxy areas; null if any member missing; never contiguous parcel capacity|

Normalized long-form evidence preserves source vintage/retrieval/native-resolution and original
metric status/confidence. `source_valid=false` values remain raw diagnostics with null normalized
value and explicit missing_reason. `constant_observed_column` marks constant valid values in the
provided dataset; fixed reference normalization still applies. Region membership counts are
design/scenario-specific: one cell may belong to separate investigated design alternatives.

## Phase 5 enhanced and temporal columns

Enhanced files use GeographicFeatureDataset1.2.0; preserved baseline files remain1.1.0.
Aqueduct columns are `aqueduct_<bau|opt|pes>_<2030|2040|2050|2080>_water_stress_<suffix>`
with status/confidence/coverage_frac companions. Suffixes ratio, score, category, label,
extreme_scarcity_frac and category_shares_json retain distinct native meanings. Positive9999 raw
scarcity is a separate area fraction, not an ordinary ratio mean. NULL is missing. Unsupported2040
is UNKNOWN with unsupported_source_period. Native windows/SSP/five-model median are in method JSON.

Temporal annual variables: e_it_mwh, e_facility_mwh, c_electricity_kg, w_site_m3, w_electricity_m3,
w_site_withdrawal_m3 and w_electricity_withdrawal_m3. Units are MWh, kgCO2e and separate consumed/
withdrawn m3. Tonnes/liters stay in unchanged SitePerformance. Source-window context is never copied
annually; NASA model/member/SSP/year is separately identified. Lifecycle `_kg` values are gross
kgCO2e; known_subtotal_partial_kg is incomplete when required components are unknown, and full total
remains null in the real no-inventory run. See contracts and temporal_lifecycle research for keys,
source/assumption metadata, units, period identities and accounting modules.

## Phase 6 validation outputs

`sensitivity_results.parquet` uses `SensitivityResult` 1.0.0 and contains one row per
case/grid/design correspondence. Its identity columns are `evaluation_version`, `freeze_id`, `case_id`,
`case_category`, grid definition/data mode, grid/design, baseline and case scenario IDs, and both profile
IDs. Baseline/case eligibility, rankability, hard-fail, critical-UNKNOWN, conditional, rank, score,
Pareto and exact top-k fields are retained. `rank_change` is case minus baseline rank. Raw metrics,
metric deltas, contributions, contribution deltas and assumptions are finite JSON objects. A driver is
reported only for a positive mean absolute known contribution change; omitted ablation metrics remain
explicitly omitted.

`robustness_summary.csv` contains case-level alternative/eligible/rankable/conditional/hard-fail and
eligibility-change counts, exact-k overlap/Jaccard, matched rank correlation, rank-change statistics,
driver scope, weighting method, scenario identities and comparison key. `fixed_region_summary.csv`
contains every accepted baseline region/design member count, matched/eligible/rankable/unranked counts,
ranked-member min/max, and an all-members-only mean. `alternative_rank_ranges.csv` uses
`AlternativeRankRange` 1.0.0: evaluation/freeze identity, grid/design, baseline scenario/rank, evaluated,
ranked and unranked case counts, min/max/range, and the separate-context scope statement.

`ablation_results.csv` stores the removed group, global renormalization policy, original/retained weights,
removed metric IDs and outcome diagnostics. `resolution_results.csv` stores resolution/grid definition,
design, cell/rankable/member/region counts, Census-intersection and selected-union areas, and cross-
resolution selected-area intersection/union/Jaccard. `holdout_data_quality.csv` reports each dataset/
metric row count, known/UNKNOWN count, partial-coverage count, coverage minimum/mean and source IDs.
`validation_report.json`/`.md` and `run_metadata.json` bind scope, limitations, hashes and output counts.

## Phase7 current delivery fields

The real run-package geographic/provenance copies retain all accepted physical source units and row
identities; original `data/processed` files remain preserved. See the earlier metric tables for the
681-column enhanced development geography and one grid/metric provenance row.

`weight_result.json`: `weights` (global leaf weights) and `weighting_method` (actual resolved mode).
`source_inventory.json`: verified native/acquisition-log paths, bytes/SHA/request/source/version evidence
and separate implemented/acquired/analyzed registry states. `source_coverage.json` retains all source
coverage/unknown reasons while execution-only tile resume counters remain intermediate diagnostics.
`profile_snapshot.json` stores the resolved complete policy/fingerprint before current ranking.

Current sensitivity rows retain `case_id`, category, full grid/design/scenario key, raw performance,
score/rankability/conditional/hard-failure/critical-UNKNOWN, criterion/contribution fields and
`validation_revision`/`validation_id`. Alternative rank ranges retain ranked/unranked/evaluated case
counts; unavailable ranks are null. Robustness/fixed-region CSVs document comparison denominator and
member retention. Current validation JSON binds actual table/config/source/model hashes, unavailable
independent validation and null overall accuracy. Substantive report text and table bytes are deterministic;
execution UUID/timestamp/process lifetime memory/cache-hit diagnostics are intentionally changing metadata.

Each future context has its own profile/scenario/performance/ranking/regions/report. Requested2040 water
contexts have no native fields and remain UNKNOWN/UNRANKED. Independent NASA model/member/SSP/year rows use
`design_id=source_context`; no weather-to-cooling response is invented. Lifecycle partial components
retain accounting module boundaries and total UNKNOWN when required modules are missing.

Resource accounting revision: cumulative project raw/interim byte totals are recorded only in
`run_metadata.resource_diagnostics`, freshly measured on fresh and cached executions. They do not alter
source evidence, physical outputs, cache identity or substantive source-manifest checksums. The initial
V1 counter drift and narrowly corrected V2 executable evidence are preserved in `runs/phase7`.

## National discovery scope fields

The national delivery configuration is version 2.1.0; existing table metric columns and units retain
their contracts. `grid_definition_id=conus-epsg5070-ox-2500000-oy3400000-s50000m-v1` identifies the
new 50 km regular grid. `state_fips_all` is a semicolon-delimited list of intersecting jurisdiction FIPS,
including cells crossing
state boundaries. `study_area=conus` requires all 48 contiguous states plus DC at preflight.

NLCD provenance `aggregation_method` identifies native WGS84 Albers reprojection by nearest-neighbor
resampling to a 30 m EPSG:5070 raster, followed by categorical pixel fractions in each cell. Values remain
observed aggregates; neither a regional fraction nor a 50 km cell establishes parcel availability.
Coverage reports describe the actual grid extent, cell count and source nonmissing counts. API version
1.1.0 adds per-run scenario availability and presents this actual scope; optional uncomputed metrics
retain null values and their missing reasons.
# Regional revision additions

| Field | Meaning |
|---|---|
| `cell_size_m` | Fixed analytical lattice spacing;1000m in the approved regional revision. |
| `maximum_region_extent_km` | Project-assumed maximum bounding-box span per EPSG5070 axis; not diameter or parcel size. |
| `parent_grid_id` | Actual evaluated national representative parent selected for full refinement. |
| `prepared_metric_policy_sha256` | Binding to metric definitions and fixed references used to validate batch evidence. |
| `refined_area_km2` | Sum of actual CONUS child intersections evaluated at 1 km. |
| `shortlisted_parent_area_km2` | National selected-parent area before representative refinement; omitted coverage is explicit. |
| `ranking_universe` | All evaluated refined alternatives, with external scenarios assessed separately. |
| `representative_parts` | Catalog lookup from evaluated representative grid ID to checksum-bound native evidence batch. |
# Submission and optional heat quantities — additive 2026-10-03

| Field | Unit / interpretation |
|---|---|
| `recommendation.centroid` | EPSG:4326 lat/lon of the actual evaluated representative cell |
| `recommendation.region_centroid` | EPSG:4326 lat/lon of its separate connected search region |
| `framework.criteria[].weight` / `contribution` | Actual archived leaf weight / copied weighted contribution; no browser calculation |
| `impact.total_water_consumption` | m³ consumed/year, direct plus generation consumption only when both boundaries are supported; otherwise UNKNOWN |
| `impact.cooling_comparisons[].metric_results` | Per-quantity signed reference-minus-proposed annual difference with unit/status/confidence/missing reason |
| `available_heat_after_losses_mwh` | MWh thermal/year; IT-electricity-equivalent energy times supplied recoverability and one minus supplied distribution losses |
| `delivered_heat_mwh` | MWh thermal/year; compatible supplied heat demand caps the available heat; absent host/temperature/demand/factors remains UNKNOWN |
| `net_heating_system_avoided_co2e_tonnes` | Signed tonnes CO2e/year of displaced heating minus incremental auxiliary electricity; a supplied separate system scenario, no facility-footprint credit |

## Cleanview diagnostic revision fields — 2026-10-03

`CandidateRegion` 1.3.0 retains the prior fields and units, with an additional
publication gate on complete member suitable-land support. A sufficient sum is
only classified geographic plausibility; parcel contiguity and availability
remain unverified. Insufficient components are absent from published regions
and membership, and remain recorded in `region_land_screening.parquet`.

| `RegionLandScreening` 1.0.0 field | Unit / interpretation |
|---|---|
| `region_id`, `design_id`, `scenario_id` | Identity of the initial bounded component and its single decision/external context |
| `member_grid_ids` | Complete deterministic list of evaluated grid members; no cross-design or cross-scenario mixing |
| `value_km2` | km²; complete sum of classified suitable-land proxy area; null if any member support is missing |
| `threshold_km2` | km²; supplied facility minimum land demand, retaining its project-assumption basis |
| `outcome` | PASS / FAIL / UNKNOWN for total-area plausibility only |
| `status` | calculated for a complete sum, unknown for a missing sum |
| `confidence` | low for classified proxy support, unknown when missing |
| `missing_reason` | `incomplete_member_land_support` for an unknown sum; otherwise null |
| `interpretation` | Explicit limitation: no contiguous or obtainable parcel is inferred |

`ExistingSiteCountyComparison` 1.0.0 records one reference facility × design ×
external scenario in a saved model domain. `county_geoid` is an exact matched
Census identifier; every intersecting whole grid cell contributes to county
support. `comparison_status` distinguishes COUNTY_SUPPORTED,
OUTSIDE_EVALUATED_DOMAIN and UNMATCHED_COUNTY. Count fields are counts of cells
or alternatives, never accuracy or facility suitability. Metric min/max fields
retain the underlying model units listed below.
Range status is calculated or unknown with a missing reason. `facility_score`
is null/unknown because exact point locations are unavailable;
`physical_validation_status` remains EXTERNALLY_UNVALIDATED.

| Comparison min/max fields | Unit / interpretation |
|---|---|
| `mcda_score_min`, `mcda_score_max` | Weighted score 0–100 among rankable supported cells |
| `mcda_rank_min`, `mcda_rank_max` | Ordinal rank within the complete evaluated external-scenario universe |
| `raw_annual_electricity_co2e_min`, `raw_annual_electricity_co2e_max` | tonnes CO2e/year under the saved illustrative facility/scenario |
| `raw_annual_site_water_consumption_min`, `raw_annual_site_water_consumption_max` | m³ consumed/year within the modeled site-cooling boundary |
| `raw_local_baseline_water_stress_min`, `raw_local_baseline_water_stress_max` | Dimensionless Aqueduct 0–5 baseline scale |
| `raw_transmission_proximity_min`, `raw_transmission_proximity_max` | km; minimum cell-polygon distance to mapped transmission geometry |
| `raw_suitable_land_fraction_min`, `raw_suitable_land_fraction_max` | Fraction 0–1 of classified potentially suitable land, not contiguous parcels |

# Phase 11 national fine surface fields (2026-10-03)

| Field | Unit | Meaning |
|---|---|---|
| `fine_surface_cells.potentially_suitable_land_frac` | fraction 0–1 | Valid Annual NLCD area outside classes 11, 12, 90 and 95 over valid area of the cell's study polygon (proxy, not buildability) |
| `fine_surface_cells.nlcd_coverage_frac` | fraction 0–1 | Valid land-cover area over study-polygon area |
| `fine_surface_cells.transmission_distance_km` | km | Distance from the study polygon to the nearest mapped transmission line (proxy, not capacity) |
| `fine_surface_cells.baseline_water_stress_score` | index 0–5 | Area-weighted Aqueduct 4.0 baseline `bws_score` |
| `fine_surface_cells.baseline_water_stress_score_coverage_frac` | fraction 0–1 | Share of the study polygon covered by valid basins (capped at 1) |
| `fine_surface_cells.grid_carbon_intensity_kg_per_mwh` | kg CO2e/MWh | Area-weighted eGRID2023 `SRC2ERTA`, converted from lb/MWh |
| `fine_surface_cells.egrid_coverage_frac` | fraction 0–1 | Share of the study polygon covered by valid eGRID subregions (capped at 1) |
| `fine_surface_cells.is_boundary_cell` | boolean | Study polygon is clipped by the CONUS boundary |
| `fine_surface_parents.best_fine_score` | score 0–100 | Highest fine decision value among the parent's scored cells for one design/scenario |
| `fine_surface_parents.p90_fine_score` | score 0–100 | 90th percentile of those values |
| `fine_surface_parents.scored_cells` | count | Cells with every profile metric known and above minimum coverage |
| `refinement_windows.fine_selection_rank` | rank | Order of the parent by best fine value: among all parents (`national_fine_surface`) or among the selected parents (`national_fine_region_parents`) |
| `refinement_windows.fine_region_representative` | grid ID | National representative parent of the region(s) the parent was chosen for (`national_fine_region_parents` only) |
| `refinement_windows.fine_region_selection_basis` | category | `fine_surface`: a member parent scored above the representative; `representative`: the representative scored best or tied; `representative_unscored`: no member was scored |

The revised cell table is `NationalFineSurfaceCell` 1.1.0. Each of the seven feature columns
has explicit status, confidence, missing reason, source ID/field, unit and source-year companions.
The long-form `feature_provenance.parquet` uses `FeatureMetadata` 1.1.0, with exactly seven rows
per retained cell. Coverage fractions are calculated diagnostics; an underlying unknown source
value is null even when the calculated coverage is zero. `unscored_reason` in replayed fine scoring
lists unavailable metric IDs and is diagnostic, not a screening outcome.

## County socioeconomic geography and crosswalk (1.0.0)

| Field | Unit / meaning |
|---|---|
| `candidate_id` | Existing fixed-lattice `grid_id`; complete saved real candidate cell |
| `county_geoid`, `state_fips`, `county_fips` | Five-, two- and three-character strings; leading zeros retained |
| `county_name`, `saipe_county_name` | Source labels for display; never join keys |
| `candidate_area_km2`, `intersection_area_km2` | Full candidate and candidate∩county areas calculated in EPSG:5070 |
| `overlap_fraction` | Positive intersection share of full candidate area; no renormalization |
| `poverty_rate` | 2024 SAIPE all-age poverty estimate, percent 0–100 |
| `poverty_count` | 2024 SAIPE all-age number of people in poverty |
| `median_household_income` | 2024 SAIPE median household income, USD/year |
| `<metric>_lower_90`, `<metric>_upper_90` | Original rounded 90% confidence interval endpoints in the metric's units |
| `<metric>_moe` | Calculated half-width of the source 90% interval; not an independently downloaded API MOE |
| `poverty_percentile`, `income_percentile` | Calculated 0–100 valid-CONUS-county percentiles, average ties |
| `low_income_percentile` | `100-income_percentile`; higher means greater income disadvantage |
| `<metric>_status`, `_confidence`, `_missing_reason` | Dataset evidence classification, qualitative confidence and explicit null reason |
| `<metric>_unit`, `_source_id`, `_source_url`, `_method` | Units and traceable source/calculation evidence |
| `socioeconomic_year`, `boundary_year`, `boundary_type` | 2024 estimates; authorized 2023/2025 cartographic geography; `cartographic_500k` |
| `geometry_vintage_mismatch`, `economic_observation_type` | Visible mixed-year notice; SAIPE model-based estimate interpretation |
| `county_coverage_fraction`, `uncovered_fraction`, `county_count`, `coverage_reason` | Companion per-cell area-coverage diagnostics, including no-overlap cells |
| `county_own_source_revenue`, `county_property_tax_revenue`, `county_population` | Future inputs, null/unknown with reason `future_fiscal_inputs_not_acquired` |
| `estimated_dc_tax_revenue`, `tax_incentives`, `public_cost`, `net_local_fiscal_revenue`, `fiscal_significance` | Future fiscal inputs/results, null/unknown; no tax assumptions in this delivery |

The frontend uses explicitly unit-bearing aliases such as `poverty_rate_pct`
and `income_usd`; these represent the same county estimates. Region county shares
use the sum of member-cell intersection areas over the full member-cell area.
They are geographic context, not the share of residents, taxes or project impact.


## Fixed cached regional evaluation artifacts (2026-10-04)

The separate `src/dc_locator_fast.py` executor writes fresh model outputs under
`runs/frontend_service/cached_regional_runs/<request identity>/`. Cached input
geography and native feature/screening evidence remain under
`data/interim/fast_cached_regions/<cache identity>/` and retain their source
lineage. This domain consists of 152,500 existing 1 km cells in 61 nationwide
regional windows; its parent selection is fixed.

| Artifact/field | Meaning |
|---|---|
| `ranked_cells.parquet` | Fresh full-cohort cell/design rankings, normalized leaves, eligibility flags and calculated annual physical columns; schema `CachedRegionalRankedDataset` |
| `physical_schema.json` | Shared units, calculation methods, status/confidence and null reasons for calculated annual physical fields; native carbon input retains observed evidence |
| `representative_evidence.parquet` | Fresh accepted native physical evidence for every returned representative grid/design/scenario, checked against the compact global calculation |
| `representative_screening.parquet`, `screening_checks.parquet` | Native representative checks and explicit frozen-dependency full-cohort screening evidence; critical UNKNOWN never becomes PASS |
| `candidate_regions.parquet`, `candidate_regions.geojson` | Fresh bounded search regions in EPSG:5070 and 4326 respectively; width and height each at most 20,000 m in EPSG:5070 |
| `region_membership.parquet`, `region_land_screening.parquet` | Fresh membership and the accepted native multi-cell land-support checks |
| `scope.kind`, `regional_catalog.selection` | `fixed_cached_national_regional_cohort` / `fixed_cached_cohort`; no new national parent selection |
| `run_metadata.input_cache`, `actual_working_code_sha256`, `guard_hashes` | SHA-bound immutable cache, mathematical dependencies including AHP, and separately bound runtime memory guard |
| `validation_report.status`, `sensitivity_status`, `rank_ranges_status` | `NOT_ASSESSED`; optional diagnostics were not repeated and cannot inherit baseline claims |

No annual physical column silently supplies missing source values. Missing carbon
or other evidence stays null with its stated status/reason. Historical static
carbon and constant design assumptions are not future or marginal forecasts.

## Rediscovery check artifacts (`runs/rediscovery_v1/`, 2026-10-04)

Written by `python -m dc_rediscovery run`; see `docs/rediscovery_validation.md`. Every table carries the
`dc_locator.*` Parquet metadata. `rediscovery_manifest.json` binds the configuration, inputs, code,
environment, timeline and output hashes.

| Artifact/field | Meaning |
|---|---|
| `evaluated_cells.parquet` | All 7,829,373 national 1 km cells: `grid_id`, `row`, `col`, cell-centre `lat`/`lon` (EPSG:4326), best `design_id`, `suitability_score` (model decision value 0–100; null when unscored), `factor_<metric_id>` (normalized criterion 0–100, float32), raw carbon/water-stress/transmission/land values and `unscored_reason` |
| `candidates_blind.parquet` | Separated Top-250 candidates written before any facility data was read. Its sha256 is in the manifest and summary |
| `candidates.parquet` / `.csv` | Blind fields, then `distance_to_nearest_existing_dc_km` (haversine), `nearest_existing_dc_*`, `existing_dc_within_<r>km`, `classification` (`validated` ≤ 25 km, `emerging` > 50 km, otherwise `unresolved`), `top_n_bucket`, `weight_cases_retained/total/ids`, `robustness_*` (score 0–100 or null with `robustness_missing_reason`; `robustness_spatial_support`), `explanation`, `strengths`, `weaknesses` |
| `rank`, `score_rank_min`, `score_rank_max`, `tied_cells_at_score`, `cells_with_higher_score` | Published rank (ties by grid_id) and the candidate's exact tie block on the national score distribution |
| `score_percentile`, `national_percentile` | Mid-rank percentiles (ties count ½) among valued cells; presentation context only |
| `candidate_factors.parquet` | One row per candidate × criterion: `weight`, `normalized_score`, `contribution` (= weight × normalized; the row sum equals `suitability_score`), raw value/unit/status/confidence/source/data year, `location_dependent` (false for the cooling-design water term) |
| `existing_facilities.parquet` | 1,472 CONUS IM3 records: `facility_id` (`im3:<osm id>`), name, operator, county/GEOID, state, `lat`/`lon` (IM3 footprint centroid), `footprint_type`, `footprint_sqft`, `hub_id`, the 1 km cell row/col/score, source/licence/DOI/sha256, `role=external_validation_only`. `city` is null (not provided) |
| `facility_hubs.parquet` | Single-linkage hubs (≥ 5 records, gaps ≤ 10 km): size, centroid, label, states, top operators, `nearest_top<N>_candidate_km` |
| `baseline_draws.parquet` | Per control × draw × N × radius random hit rate (1,000 seeded draws per control) |
| `validation_summary.json` | Hit rates, tie sensitivity, baseline comparison (mean, 95% range, lift, one-sided p), presence–background statistics, recall, classification counts, providers, factor map, limitations |
| `suitability_surface.png` / `.json` | Web-Mercator-aligned presentation image of the national score (ink from the national median up to the maximum; unvalued cells are transparent) and its legend and corner coordinates |
