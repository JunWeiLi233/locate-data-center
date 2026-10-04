# Sources

AGENTS.md section 4: "Use only authoritative/official sources... any additional source must be justified
here." This document records authoritative acquisitions, native integrations, methodology sources and
remaining access/coverage blockers (`configs/sources.yaml`).

## Used in Phase 1

### U.S. Census Bureau cartographic boundary files (GENZ2023)

- **What**: `cb_2023_us_state_500k.zip` (states/equivalents) and `cb_2023_us_county_500k.zip`
  (counties/equivalents), 1:500,000 scale, generalized for thematic mapping.
- **Why this source**: it is the authoritative, official U.S. government boundary dataset for states and
  counties; `docs/specs/master_prompt.md` does not name a specific CONUS-boundary source for Phase 1, so
  this was selected as the standard choice for a national administrative-boundary analysis grid, justified
  here per AGENTS.md section 4's "any additional source must be justified" rule.
- **Why cartographic boundary rather than full-resolution TIGER/Line**: scale-appropriate for a 10 km (or
  coarser) grid, and roughly an order of magnitude smaller to download/process. See `docs/limitations.md`
  for the precision this trades away.
- **URLs** (public HTTP, no authentication):
  - `https://www2.census.gov/geo/tiger/GENZ2023/shp/cb_2023_us_state_500k.zip`
  - `https://www2.census.gov/geo/tiger/GENZ2023/shp/cb_2023_us_county_500k.zip`
- **Vintage**: GENZ2023 (server `Last-Modified: 2024-04-16`).
- **License**: U.S. Government work, public domain
  (https://www.census.gov/about/policies/open-gov/open-data.html). No account, login, CAPTCHA, or
  click-through terms were encountered or required.
- **Retrieval**: `dc_locator.geography.boundary.download_conus_boundary_sources()`; see
  `data/raw/census_cartographic_boundary/download_log.json` for the exact retrieval timestamp, byte counts,
  and sha256 for the files actually cached in this checkout, and `docs/phase_handoff.md` for the values
  recorded at Phase 1 handoff time.
- **User-Agent**: `dc_locator/0.1 (research prototype)` (AGENTS.md section "Data access policy").

## Phase 2 source integration (2026-10-03 UTC)

All eight required geographic adapters are implemented. Real analysis is the42-cell `dev_tiny`
subset from Phase1, preserving all original IDs and geometries. `data/processed/coverage_report.json`
is authoritative for per-metric analyzed counts and valid areal coverage; implementation, acquired
inputs and analysis are separate flags. Cached files are checksum-verified before build. Actual
download request URLs, timestamps, SHA256 and bytes are in each source's download manifest and
the final `data_manifest.json` snapshot. No national source-complete analysis is claimed.

| Source | Actual inputs / semantics / remaining requirements |
|---|---|
| USGS Annual NLCD | Cached2024 Collection1.1 30m public ImageServer devbbox export. Landing page: [USGS Annual NLCD](https://www.usgs.gov/centers/eros/science/annual-national-land-cover-database). Valid16-class legend only;0/250 and off-legend artifacts are missing. Latest authoritative Collection1.2 national files remain CAPTCHA/manual acquisition per existing research. Local `land_cover` path supports official GeoTIFFs. |
| EPA eGRID | [Detailed data](https://www.epa.gov/egrid/detailed-data), [mapping files](https://www.epa.gov/egrid/egrid-mapping-files). Downloaded eGRID2023 rev2 imperial workbook21,213,301bytes, primary map57,260,059bytes and multiple-region map16,188,767bytes (94,662,127bytes total). Opened `SRL23` machine field header; primary geometry field`Subregion`, ambiguity label`MultipleSu`. Canonical carbon is`SRC2ERTA` CO2e, CO2-only`SRCO2RTA` separately preserved. Native shapefile CRS read from GDAL rather than assumed. Maps are geographic historical screening associations, not utility supply confirmation. |
| WRI Aqueduct4 | [Water Risk Atlas](https://www.wri.org/data/aqueduct-water-risk-atlas), [official source dictionary](https://github.com/wri/Aqueduct40/blob/master/data_dictionary_water-risk-atlas.md). Cached zip261,527,511bytes; `baseline_annual` GDB layer; `pfaf_id,bws_raw,bws_score,bws_cat` read with bbox and valid basin IDs. Source ratio/score/category/missing and9999 sentinel remain separate. No technical-publication form was submitted. |
| NOAA NCEI | [U.S. Climate Normals](https://www.ncei.noaa.gov/products/land-based-station/us-climate-normals), DOI[10.25921/yya9-9769](https://doi.org/10.25921/yya9-9769). Cached annual1991–2020 gridded-normal COGs in Celsius (`tavg_norm,tmax_norm,tmin_norm,tmax_max`);1/24degree, masked NaN. Daily normals also cached but not analyzed in Phase2; cooling degree days/hourly weather are not inferred from annual normals. |
| FEMA NFHL | [Official NFHL documentation](https://www.fema.gov/flood-maps/national-flood-hazard-layer), public `https://hazards.fema.gov/arcgis/rest/services/public/NFHL/MapServer`. Acquired independent layer0 Availability polygons and layer28 effective Hazard Zone polygons using one bbox IDs query and100-ID batches. The original500-ID GET causedHTTP500 (long URL); bounded100-ID requests succeeded. Query bounds retained in manifests and enforced in analysis; areas outside/partially covered by query bounds are UNKNOWN. T/F classification coverage is independent from Availability and SFHA. U/D/open-water classifications are not zero hazard. |
| USFS WRC | [WRC2 official catalog](https://www.fs.usda.gov/rds/archive/catalog/RDS-2020-0016-2). Acquired bounded30m BP/CFL public exports and complete service/export metadata; current endpoints under `https://imagery.geoplatform.gov/iipp/rest/services/Fire_Aviation/USFS_EDW_RMRS_WRC_{BurnProbability,ConditionalFlameLength}/ImageServer`. Service native U16 packing/scales and no-data are unverified (BP clip0..35, no nodata, not probability0..1). Both actual WRC metrics remain UNKNOWN `invalid_source_value`; no guessed conversion. Use native archive BP/CFL rasters with verified units/masks in local `paths` to complete analysis. State bundles remain optional and large (TX~18GB); no login/forms/CAPTCHA used. |
| EIA U.S. Energy Atlas | [Official Atlas](https://atlas.eia.gov/). Cached national point/line GeoJSONs: transmission archive2024-09-30, power plantsPeriod202502, pipelinesdateunverified. Original export CRS verified before projection. Minimum study-polygon distance in EPSG:5070; archived transmission layer is not maintained and proximity gives no capacity, service availability or connection feasibility. |
| USGS PAD-US | [PAD-US4.1 DOI](https://doi.org/10.5066/P96WBCHS). Cached flattened `PADUS4_1_VectorAnalysis_CONUS` GDB layer, not huge national raster payload. GAP1/2/3/4 andRastDrop consumed with indexed exact overlay/union. GAP1+2 ecological overlap is separate fromGAP3/4. No full-inventory ownership attribute is invented. |
| Supplemental USFS WHP | [WHP2023 4th edition catalog](https://www.fs.usda.gov/rds/archive/catalog/RDS-2015-0047-4). Official standalone270m continuous CONUS TIFF from cached verified archive, labeled source_id`usfs_whp`. This additional official source is justified as an explicitly separate landscape hazard-potential indicator; it never substitutes for required WRC probability/CFL. Only143,359,011byte continuous raster member is extracted to a checksum-keyed interim cache, not GDB/all states. |

WRI future data already exists in the same archive: GDB `future_annual`, polygon family`pfaf_id`,
scenarios`bau,opt,pes`, years`30,50,80` (2030/2050/2080), indicator columns such as
`bau30_ws_x_r, bau30_ws_x_s, bau30_ws_x_c, bau30_ws_x_l` (raw/score/category/label),
with`bau50_*` equivalents. Future annual missing values are NULL, not baseline-9999. This is a
Phase5 input opportunity, not an analyzed Phase2 future feature;2040 values are not fabricated.

Public acquisition functions in `geography.sources.ingestion` provide quota-limited manifest downloads,
`acquire_egrid`, bounded `acquire_wrc_bbox`, and `acquire_flood_bbox(layer_id=0|28)`. Bounded source
cache keys include request extent/product/parameters; each reuse verifies identity,bytes,SHA256.
Raw local paths work independently when source automation is unavailable. No access controls are bypassed.

## Sources registered for later phases (`configs/sources.yaml`)

The registry preserves the Phase1 source list and now records verified Phase2 URLs/statuses.
Phase2 rows below retain the historical Phase1 inventory and do not override the current Phase2
coverage report. Phase5 rows are reconciled to the expanded native-source registry below. Status
does not substitute for separate implementation/acquisition/analysis flags.

| source_id | name | phase | status |
|---|---|---|---|
| nrel_nsrdb | NREL National Solar Radiation Database | 5 | PARTIAL |
| nrel_wind_toolkit | NREL WIND Toolkit | 5 | PARTIAL |
| epa_egrid | EPA eGRID | 2 | NOT_IMPLEMENTED |
| berkeley_queued_up | Berkeley Lab Queued Up | 5 | PARTIAL |
| eia_861 | EIA Form EIA-861 | 5 | PARTIAL |
| eia_energy_atlas | EIA / U.S. Energy Atlas | 2 | PARTIAL (raw data cached, no adapter) |
| wri_aqueduct40 | WRI Aqueduct 4.0 | 2 | PARTIAL (raw data cached, no adapter) |
| noaa_ncei_climate | NOAA/NCEI climate normals | 2 | PARTIAL (raw data cached, no adapter) |
| epa_cwns | EPA Clean Watersheds Needs Survey | 5 | BLOCKED |
| global_iron_steel_tracker | Global Iron and Steel Tracker | 5 | BLOCKED |
| global_cement_concrete_tracker | Global Cement and Concrete Tracker | 5 | BLOCKED |
| freight_analysis_framework | Freight Analysis Framework (FAF) | 5 | PARTIAL |
| building_transparency_ec3 | Building Transparency / EC3 | 5 | BLOCKED |
| usgs_annual_nlcd | USGS Annual NLCD | 2 | PARTIAL (raw data cached, no adapter) |
| fcc_broadband | FCC broadband availability | 5 | NOT_IMPLEMENTED |
| ntad | National Transportation Atlas Database | 5 | PARTIAL |
| fema_nfhl | FEMA National Flood Hazard Layer | 2 | NOT_IMPLEMENTED |
| usfs_wildfire_risk | USFS Wildfire Risk to Communities | 2 | PARTIAL (raw data cached, no adapter) |
| noaa_ibtracs | NOAA IBTrACS | 5 | PARTIAL |
| us_drought_monitor | U.S. Drought Monitor | 5 | PARTIAL |
| nasa_nex_gddp_cmip6 | NASA NEX-GDDP-CMIP6 | 5 | PARTIAL |
| fema_rapt | FEMA RAPT | 5 | NOT_IMPLEMENTED |
| usgs_padus | USGS PAD-US | 2 | PARTIAL (raw data cached, no adapter) |

"PARTIAL (raw data cached, no adapter)" means `data/raw/<source_id>/` already contains downloaded files
with a `download_log.json` manifest (pre-dating this Phase 1 fix pass), but no `dc_locator.geography`
adapter code exists to parse, join, or feature-engineer from them yet -- i.e. *acquired* but neither
*implemented* nor *analyzed*, per AGENTS.md section 4's three-way coverage distinction. This Phase 1 fix
pass did not audit those cached files' currency or completeness; Phase 2 should re-verify each one's
`download_log.json` before building its adapter.
# Phase 4 methodological source: AHP random consistency index

The primary methodology is R.W.Saaty, “The analytic hierarchy process—what it is and how it is
used”, Mathematical Modelling9(3–5),1987,161–176,
[DOI10.1016/0270-0255(87)90473-8](https://doi.org/10.1016/0270-0255(87)90473-8).
Section4,p171 gives RI values based on500 random matrices: n1..10=
0,0,0.58,0.90,1.12,1.24,1.32,1.41,1.45,1.49. Primary article text was verified through the
[full article transcription](https://studylib.net/doc/28260469/1987-saaty-ahp), with official
publisher metadata corroborating identity; publisher PDF access was unavailable. This is a
methodological source, not geographic evidence. Table version/checksum/verification limitation
are recorded in`docs/research/phase4/ahp_ri.md` and every supplied AHP result. n>10 is rejected,
not extrapolated. The CR0.10 cutoff remains a declared configurable review convention. No source
or expert supplies the real baseline's equal preference weights.

## Phase 5 expanded native sources (2026-10-03 UTC)

The geography expansion has seven acquired and analyzed native products: EIA861
2024 State Totals, USDM TX weekly cumulative county history2000–2024, Queued Up
2026 edition through2025, NOAA IBTrACS v04r01 MAIN NA tracks1980–2024, bounded
NTAD2026 rail JSON, the WIND Toolkit native modeled site index, and NASA NEX
v2.0 ACCESS-CM2/r1i1p1f1/SSP245 daily2030 subsets. Their scope is deliberately
`PARTIAL`; real development coverage is42 cells. A tested NSRDB native CSV parser
is implemented but unacquired and unanalyzed. CWNS/GEM/EC3 access requirements,
unverified FCC/RAPT native exports and the failed FAF acquisition remain explicit.

The authoritative native documentation, exact headers/units, access evidence,
manual paths, actual file URLs/UTC retrieval/bytes/SHA256 and source-specific
limitations are in [Phase5 native sources](research/phase5/native_sources.md).
`configs/expanded_sources.yaml` selects actual versions; `expanded_coverage_report.json`
and `expanded_data_manifest.json` distinguish implemented/acquired/analyzed data,
nonmissing metrics, temporal/spatial coverage, native quality flags and raw/interim
byte accounting. `configs/sources.yaml` preserves all Phase2 entries and adds
the separate `wri_aqueduct40_future` source; the primary's
[temporal/lifecycle note](research/phase5/temporal_lifecycle.md) documents that integration.

NASA tas has a conflicting native CF time-maximum tag. Matching native v2.0
tasmax/tasmin verify the documented mean at all9,125 cached samples, with the
raw conflict, identities, rounding tolerance and component hashes preserved.
Queue capacity retains native negative/missing quantities as UNKNOWN. State
reliability does not identify the serving utility; resources/queue MW do not
establish purchased power; historical tracks do not imply future probability.
The expanded metrics are informational and add no scores or hard-check PASS.
Baseline columns, provenance rows and original bytes remain preserved.

## Phase 6 source scope

Phase 6 adds no external measurement source. It reuses the frozen Phase 5 native inputs and future Aqueduct
profiles, then records exact source/config/grid hashes in the preregistration, software evidence, freeze and
prospective build manifests. Geometry and cached-coverage availability alone select the unseen block before
feature inspection. Repeated source aggregation is a provenance/data-quality check and must not be described
as independent facility validation. The NASA context still supplies no cooling response, queue capacity still
supplies no confirmed power, and cached geographic evidence still supplies no parcel approval.

## Phase7 source reuse and cache binding

Delivery performs no additional acquisition. `configs/local_sources.json` binds the existing real
cache, native download logs and selected grid by bytes and SHA; the three native input JSON documents
preserve actual paths, source versions, query bounds and numerical verification dependencies. Ingest
cross-checks embedded acquisition records against the verified native logs, including URL/version/request
identity, rather than treating a file-exists hit as a new acquisition. Native parsing/area aggregation
happens in build-features. Registry status is not upgraded merely by a checksum check; computed coverage
and nonmissing counts remain in the run package.

WRC packing/domain remains unverifiable and UNKNOWN; WHP is a separate product. NFHL absence outside
queried/mapped coverage is UNKNOWN. NOAA normals and NASA one-year projected context are not hourly
cooling models; NASA tas interpretation retains numerical tasmax/tasmin equality evidence and original
CF metadata conflict. Queue negative native capacity outliers remain UNKNOWN while counts survive.
Solar/wind context is not purchased power. CWNS proximity is not a reuse commitment, FCC availability
is not diverse data-center fiber, FAF regional flow is not a delivery route, and plant process is not
product EPD. Unacquired/blocked/stub states documented in Phase5 are retained honestly.

## Isolated county Monte Carlo inputs (2026-10-04)

The additional model imported from PR #1 keeps its own 19-file checksum-pinned manifest at
`backend/dataclocator/data/source_manifest.json`. Census 2025 gazetteer/TIGER, EPA eGRID 2023
revision 2 and supplier maps, EIA September 2026 monthly prices, WRI Aqueduct 4.0, NOAA normals
and FEMA NRI are official/public inputs used for an explicit 45-county cohort. These inputs
belong only to the county model; they do not silently replace the grid model's geography.
The cohort is not a representative national sample, and county/state averages remain proxies
for site engineering commitments. WRI attribution and each manifest terms note are retained.

Five archived inputs match existing project cache checksums exactly. New downloads are cached
under `data/raw/county_monte_carlo/pr1_frozen_v1/` with a local download manifest, then copied
to the isolated runtime's declared paths. The PR's original retrieval metadata stays intact;
current acquisition/reuse times and outcomes are recorded in `runs/pr1_merge_v1/acquisition.json`.
A changed checksum or blocked publisher remains explicit and prevents real runs; no synthetic
substitution or access-control workaround is permitted. The unused FEMA item metadata has live
usage counters and is retained as release/terms documentation outside the required input identity;
all 19 required scientific/definition files retain their original PR checksums.
