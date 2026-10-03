# Phase 5 native source integration

This geography expansion is additive and informational. It preserves the accepted
42-cell development grid, every baseline column, and all 2,436 baseline provenance
rows. It adds 28 metrics (1,176 provenance rows) through working native parsers.
The complete run contains 42 cells and 3,612 provenance rows. Sources remain
`PARTIAL` because the selected products, geography or years have explicit limits.
No source is marked ready merely because a file was downloaded.

`configs/expanded_sources.yaml` defines the selected versions and interpretations.
`expanded_coverage_report.json` separates implemented, acquired and analyzed flags
from nonmissing cell counts. `expanded_data_manifest.json` records actual source
configurations, native paths, URLs, retrieval UTC timestamps, bytes, SHA256,
request identities, code/config fingerprints and raw/interim byte totals including
archives and extracted copies. The native acquisition inventory appended below is
a checked snapshot, not a claim of national analysis.

## Builder and acquisition interfaces

`dc_locator.geography.sources.expanded.build_expanded_features(geography,
baseline_provenance, source_inputs=None, output_dir=None, *, study_geometry=None)`
returns enhanced geography, enhanced provenance, coverage report and manifest.
Inputs can be validated Parquet paths or in-memory tables; the latter provenance
must carry verified `attrs['grid_definition_id']`. File schema/version, row/file
mode and grid identity, provenance records, polygon validity and study-intersection
areas are checked before association. Final files use GeographicFeatureDataset1.2
and FeatureMetadata1.1; the original baseline files are never overwritten.

`expanded_default_source_inputs(project_root=None)` discovers only verified native
data matching each configured filename pattern. `expanded_source_catalog(inputs)`
reports implementation/acquisition, with analysis added by the builder. Explicit
source inputs use source-ID keys and a configuration containing `paths`, data mode,
version/period, URL, retrieval and resolution. Native paths retain source-specific
formats rather than requiring prepared synthetic/normalized CSV files. NASA uses
`paths.tas` and `paths.pr`; `tasmax`/`tasmin` are verification dependencies only.
The manifest records the actual supplied configuration and its hash.

Acquisition is separate: `expanded_ingestion.acquire_file`, `acquire_eia861`,
`acquire_usdm`, `acquire_ibtracs`, `acquire_wind_index`, `acquire_ntad_rail` and
`acquire_nex_subset`. Request keys include source/version/URL/parameters and bounds.
Every reuse checks the manifest identity, byte count and current SHA256. ArcGIS
queries obtain object IDs first, retrieve bounded100-ID native batches, and verify
the exact unique returned ID sets. The builder performs no HTTP requests.

Regions are associated through exact study-polygon intersections with the accepted
Census state/county geometry. A county/state statistic is an area-weighted regional
context value, not a quantity physically located inside the cell. Numeric partial
coverage is retained, regional overlaps exceeding one are rejected, and missing
source values are never imputed. Wind points are samples with areal coverage null.
Distances use minimum study-polygon distance in EPSG:5070 metres/1,000; see the
existing projection-scale caveat in `docs/limitations.md` (about1.6% over CONUS).
Rail values additionally require a nearer feature than the bounded query boundary.
Historical track proximity is approximate and is not a wind/damage footprint.

## Native integrations and metric meanings

| Source | Implemented | Acquired | Analyzed | Nonmissing development cells |
|---|---|---|---|---|
| EIA861 | yes | yes | yes |42 for each of12 metrics |
| USDM | yes | yes, TX only | yes |42 for each of3 metrics |
| Berkeley Queued Up | yes | yes | yes |42 count/reporting;16 capacity |
| NOAA IBTrACS | yes | yes, NA product | yes |42 for both metrics |
| NTAD rail | yes | yes, bounded query | yes |42 distance |
| WIND Toolkit site index | yes | yes | yes |3 wind/CF means;42 site counts |
| NASA NEX-GDDP-CMIP6 | yes | yes, bounded2030 subset | yes |42 for each of3 metrics |
| NSRDB | yes, native local CSV | no | no |0; UNKNOWN |

### EIA861: reporting bases remain separate

[Official detailed files](https://www.eia.gov/electricity/data/eia861/) list the2024
final archive, updated2025-12-03. The native `Reliability_2024.xlsx` `State Totals`
sheet has three header rows and 51 state/DC records. `Data Year`, `State`, both
`Number of Customers` headers and the interruption unit/basis headers are verified.
`SAIDI (minutes per year)` and `SAIFI (times per year)` are retained separately for
IEEE all events, IEEE without Major Event Days, IEEE loss-of-supply removed with
MED, Any Standard all events, and Any Standard without MED. Native invalid/blank
numbers remain null. CAIDI is not used.

Columns are `eia861_{ieee_with_med|ieee_without_med|
ieee_loss_supply_removed_with_med|any_with_med|any_without_med}_{
saidi_minutes_per_year|saifi_interruptions_per_year}` and
`eia861_{ieee|any}_reporting_customers`. The customer populations are native
reporting populations, not a percent of cell customers. These state-associated
proxies cannot identify the serving utility or predict a data-center outage.

### USDM: cumulative weekly county history

[Official web-service documentation](https://droughtmonitor.unl.edu/DmData/DataDownload/WebServiceInfo.aspx)
and [statistics explanation](https://droughtmonitor.unl.edu/About/AbouttheData/StatisticsExplanation.aspx)
distinguish cumulative from nonoverlapping categories. Acquisition selects TX,
2000-01-01 through2024-12-31, `statisticsType=1`. Native `MapDate,FIPS,D0..D4,
StatisticFormatID` are validated; dates are Tuesdays, county/week keys unique, and
cumulative percentages nested within0..100. D2 already means D2-or-worse; summing
D2+D3+D4 would double-count. Native county coverage is254 TX counties.

`usdm_d2plus_area_time_frac` is the equal-week observed mean D2/100;
`usdm_d2plus_any_area_week_frac` is the observed fraction of weeks with D2>0;
`usdm_temporal_coverage_frac` is valid observed weeks/expected Tuesdays. Missing
weeks are not drought-free weeks. County overlay retains spatial and temporal
coverage separately; outside the acquired TX counties is UNKNOWN
`outside_source_coverage`. Neither metric establishes water supply or future risk.

### Berkeley Lab Queued Up: native capacity quality flags

The [2026 edition](https://emp.lbl.gov/publications/queued-2026-edition-characteristics)
covers requests through 2025; the public official XLSX is licensed CC BY4.0.
`03. Complete Queue Data` has machine headers at row2. The parser requires
`entity,q_id,q_status,fips_code,state,type_1..3,mw_1..3`; `(entity,q_id)` is the
project identity because q_id alone is not unique. The workbook codebook explicitly
uses the first listed county for projects with multiple counties.

There are 8,513 active projects, 8,424 located, 89 unlocated, and 1,777 reported
counties. Eleven active projects have negative native capacity before location
filtering (ten located); 1,533 located capacities are incomplete. Their quantities
stay UNKNOWN, with affected project IDs/counts in native quality evidence.
Six hundred twenty-four county capacity totals are unknown. Explicit reported0MW
is preserved; all missing component types/capacities are not known zero.

`queued_active_project_count`, `queued_active_reported_capacity_mw` and
`queued_capacity_reporting_frac` are area-weighted county context. A county total
is null if any active identified component is missing/invalid. Absent counties are
UNKNOWN because this is not a complete county inventory. Native queue MW does not
establish supply, load-connection feasibility, or future emissions intensity.

### NOAA IBTrACS: historical track geometry only

[Official product](https://www.ncei.noaa.gov/products/international-best-track-archive)
and [v04r01 column dictionary](https://www.ncei.noaa.gov/sites/default/files/2025-09/IBTrACS_v04r01_column_documentation.pdf)
document the native CSV units row, blank missing values and agency differences.
The parser reads `SID,SEASON,ISO_TIME,LAT,LON,TRACK_TYPE` in chunks, selects NA
MAIN tracks1980–2024, validates degree units, and retains730 storms with usable
segments. Missing positions and gaps greater than6hours are not bridged. All storm
natures remain; winds are unused because agency averaging periods differ.

`ibtracs_track_distance_km` is minimum distance to densified historical segments;
`ibtracs_track_count_within_100km` counts distinct native SID geometries within a
declared descriptive100km radius. Inventory search coverage is not an estimate of
observational completeness. These proxies do not estimate future landfall or damage.

### NTAD: verified bounded native rail inventory

[BTS continuous updates](https://www.bts.gov/ntad/continuousupdates) and
[FRA GIS maps](https://railroads.dot.gov/rail-network-development/maps-and-data/maps-geographic-information-system/maps-geographic)
link the official native North American Rail Network Lines service. The2026-07-21
layer is queried over[-97.1,28.9,-94.4,31.6], returning 4,173 exact object IDs.
Native EPSG:4326 `paths`, `FRAARCID` and the service object-ID field are validated;
the saved native JSON also carries the complete query footprint and ID inventory.
`ntad_rail_distance_km` is UNKNOWN outside/partly outside that footprint or when
the nearest-search boundary could hide a closer line. Rail proximity is not a
delivery route, usable siding, service agreement or capacity.

### WIND Toolkit and the exact WRDB

[WRDB](https://wrdb.nlr.gov/) is NLR's Wind Resource Database. This run explicitly
uses the older [WIND Toolkit Power Data Site Index](https://data.nlr.gov/submissions/54),
v1 dated2016-10-17, DOI10.7799/1329290, public domain. The
[model report](https://docs.nlr.gov/docs/fy16osti/66189.pdf), printed pp3,18,27,
describes2007–2013 modeled power and100m wind-speed/power-curve summaries.
Native `site_id,latitude,longitude,wind_speed,capacity_factor,
fraction_of_usable_area,capacity,power_curve` headers are required. There are 126,692
selected modeled sites; invalid resource quantities remain null.

`wind_toolkit_index_wind_speed_mean_m_per_s` and
`wind_toolkit_index_capacity_factor_mean_frac` average only native selected points
inside each study polygon. `wind_toolkit_index_site_count=0` describes no selected
site, not zero wind. Areal coverage remains null. The separate native SRW local
parser verifies five headers, units, height, interval and sample count; SRW data
was not acquired or analyzed. Official public no-sign-request S3 also exists;
API credentials are not the sole access route. Resource is not contracted power.

### NASA: version, calendar and tas metadata conflict verified

[NASA collection](https://nccs.smce.nasa.gov/data-collections/nex-gddp-cmip6/) and the
[v2 technical note](https://www.nccs.nasa.gov/wp-content/uploads/2025/06/NEX-GDDP-CMIP6-v2-Tech_Note.pdf),
pp2–3 and§4.3.7 printed p24, document quarter-degree daily cells, units and average
tas. Native bounded NetCDF3 files are verified version2.0, ACCESS-CM2,
r1i1p1f1, SSP245,2030, standard calendar:25 pixels×365days. Pixel edges are
densified before projection/area overlay. Native CF missing values/ranges are used;
no invented upper physical limits are applied. K→°C subtracts273.15;
kgm-2s-1→mm/day multiplies86,400.

The actual tas file has `cell_methods='area: mean time: maximum'`, conflicting
with its derived-average comment and the documented definition. Matching-version
tasmax/tasmin have identical model/member/scenario/time/coordinates. All 9,125
tas values equal their float32 mean exactly; a float64 comparison differs by at
most 0.0000152587890625K, below an explicit 0.0001K floating-point rounding
tolerance. This is a numerical identity check, not a physical threshold. The
original conflicting tag, identity checks, comparison method and all three file
hashes are preserved in FeatureMetadata.method. Missing or failed verification
makes tas UNKNOWN `invalid_source_value`; components are never additional metrics.

`nex_access_cm2_ssp245_2030_tas_mean_c` and
`nex_access_cm2_ssp245_2030_pr_mean_mm_per_day` require every native daily value
for a complete annual pixel mean. Combined
`nex_access_cm2_ssp245_2030_temporal_coverage_frac` requires both variables and uses
the lesser area-weighted valid-day fraction, preserving actual spatial footprint
coverage. Source metadata explicitly retains model, ensemble, SSP,2030 period,
variable, calendar, native version, per-file license and temporal coverage. The
2031–2054 operating-year gap is unfilled; no climate-PUE function is invented.

### NSRDB: working local parser, unacquired data

[Official native CSV examples](https://developer.nlr.gov/docs/solar/nsrdb/python-examples/)
document two metadata rows followed by a time-series header. The parser verifies
GHIW/m², finite lat/lon and unique uniformly spaced native dates. It exports an
observed sample mean, full-period irradiation only for complete valid samples, and
an explicitly named known-interval subtotal/coverage for partial samples. All-missing
data stays null. `nsrdb_point_ghi_mean_w_per_m2` has no acquired data and is UNKNOWN.
Point-series values never imply cell-wide coverage.

Public `s3://nrel-pds-nsrdb/` exists without signing. An actual public listing of
GOES/aggregated/v4.0.0 shows annual objects around1.6TB, above the project's60GB
budget; none was downloaded. Bounded HDF5 byte-range integration is not implemented.
The API needs credentials and personal fields, which were not submitted. No source
is labeled blocked solely because that API needs a key; the tested local path is
`PARTIAL`, implemented but unacquired/unanalyzed.

## Unimplemented or inaccessible native products

| Source | Current state and exact remaining requirement |
|---|---|
| EPA CWNS | `BLOCKED`, no native parser/acquisition/analysis. [Current public app](https://sdwis.epa.gov/ords/sfdw_pub/r/sfdw/cwns_pub/about) describes snapshot2022-01-01 and variable voluntary technical-data quality. CSV/Access download opens a personal-data popup; it was not submitted or bypassed. A publicly linked dictionary request disconnected without a file. Obtain a native export through the user's own authorized download, place it under `data/raw/epa_cwns/manual/`, then verify exact headers before implementing. [Scope/methods](https://www.epa.gov/system/files/documents/2024-05/2022-cwns-detailed-scope-and-methods.pdf) and [coordinator manual§5.12](https://www.epa.gov/system/files/documents/2024-05/2022-cwns-state-coordinator-manual.pdf) distinguish wastewater points from other infrastructure centroids. Modeled sewersheds are not substituted. Proximity would not establish a reuse agreement. |
| FCC | `NOT_IMPLEMENTED`; [official broadband data](https://www.fcc.gov/BroadbandData). A selected dated native availability export and its location-linkage license/headers remain unverified/unacquired. Availability would not prove diverse data-center fiber. |
| GEM steel | `BLOCKED`; [official tracker](https://globalenergymonitor.org/projects/global-iron-steel-tracker/), September2026 intended edition. The download form was not submitted; native workbook headers remain unverified. Authorized user-supplied original workbook is needed. Plant methods/proximity are not product EPDs. |
| GEM cement | `BLOCKED`; [official tracker](https://globalenergymonitor.org/projects/global-cement-and-concrete-tracker/), July2026 intended edition. Same form/native-header blocker. No plant or product quantities were fabricated. |
| FAF | `PARTIAL` research/access, not implemented/acquired/analyzed. [BTS FAF5](https://www.bts.gov/faf/faf5) and [official partner](https://faf.ornl.gov/faf5/) list5.7.1 July2026; the public [state2018–2024 native CSV ZIP](https://faf.ornl.gov/faf5/data/download_files/FAF5.7.1_State_2018-2024.zip) disconnected during acquisition. Exact local headers remain unverified. Documented units are thousands of US short tons, millions of2017constant dollars and millions of ton-miles. Regional flows would not establish a delivery route. |
| EC3 | `BLOCKED`; [current access terms](https://www.buildingtransparency.org/api-access-pricing/) verified July2026 require organization/account access. Free-tier terms prohibit caching/redistribution; a paid contract's rights are not assumed. No account, notification message, API data or native schema was acquired. User-authorized compatible EPD factors in the lifecycle module are separate inputs. |
| FEMA RAPT | `NOT_IMPLEMENTED`; [FEMA2026 update](https://content.govdelivery.com/accounts/USDHSFEMA/bulletins/426af63) confirms the tool is available. No user agreement was accepted. Appropriate underlying native dataset/export remains unverified; the source is not described as retired. |

Automatic approval review initially rejected a combined acquisition command that
included the CWNS dictionary, stating that fetching a CWNS artifact could continue
the stopped popup flow. No command ran. The lead then clarified that ordinary
read-only public documentation and independently linked dictionary access were
authorized; the narrower dictionary GET was allowed but disconnected. The popup
was never submitted, opened through a bypass, or accepted. Unaffected acquisitions
continued. This access rejection is an operational blocker record, not source data.

## Verification and limits

Focused native/parser/builder suite: 40 tests passed using
`.venv\Scripts\python.exe -m pytest -q tests\test_expanded_native.py tests\test_expanded_builder.py --basetemp=.tmp-phase5-native-final-check -p no:cacheprovider --tb=short`.
Tests cover native headers/units, nulls, reporting populations, cumulative drought,
track gaps, bounded query/ID integrity, changed request/tampered cache, coordinate
validity, NASA year/version/axes/missing pixels and CF derivation, additive
provenance identities/dtypes and coverage. Cached real queue, WIND and rail native
files are parsed in an optional integration check.

Two identical real builder runs in `runs/phase5/native` and `native_repeat` verify
all four artifacts byte-for-byte and revalidate every long provenance record.
All important values have status/unit/confidence/coverage/missing reason.
New source metadata JSON rejects NaN/Infinity. Raw download caches are resumable;
the builder itself recomputes this bounded subset. Chunked IBTrACS reads, bounded
ArcGIS batches and the NEX array budget control selected native work. National
vector runtime and peak RAM are unvalidated; this is not national readiness.
Supply capacity, committed water and diverse fiber hard checks remain UNKNOWN.

## Checked acquisition snapshot

| Source / native file | Retrieved UTC | Bytes | SHA256 |
|---|---|---:|---|
| berkeley_queued_up / `lbnl_ix_queue_data_file_thru2025.xlsx` | 2026-10-03T06:09:04.519874+00:00 | 15,571,236 | `794582d3281c6a305e9615fcfec3fae9dc85be2165216d33760b677e976a08b6` |
| eia_861 / `f8612024.zip` | 2026-10-03T06:05:24.789080+00:00 | 4,568,208 | `77ce49c60ac5a6bad50c442fc401aad5404a21da875dc5cbaba353af5ede54de` |
| nasa_nex_gddp_cmip6 / `pr_2030.nc` | 2026-10-03T06:14:21.409830+00:00 | 42,480 | `d56baca4a7a7746d2bec2e7fba6773d8a1511db205eacf3a2ef9d67a48907bbd` |
| nasa_nex_gddp_cmip6 / `tas_2030.nc` | 2026-10-03T06:14:14.935321+00:00 | 42,776 | `7aa087083f747009de718a210625dffc074d5b04a7b24434d5996c89417e97a1` |
| nasa_nex_gddp_cmip6 / `tasmax_2030.nc` | 2026-10-03T06:32:56.785752+00:00 | 42,796 | `8d55b052f7a2a3f5929a467558b566f7b4fa3e992b5acd3510ddaf3f47d9a966` |
| nasa_nex_gddp_cmip6 / `tasmin_2030.nc` | 2026-10-03T06:33:02.946890+00:00 | 42,208 | `44e648adb62aa7727258bc228f8f7b38e3078f8caab8b1723442a403cb45f865` |
| noaa_ibtracs / `ibtracs.NA.list.v04r01.csv` | 2026-10-03T06:05:47.248800+00:00 | 57,552,255 | `9e41cf9d3c4e6ae82fe35f218a3f1baea3e44b9e768857d62149ed9e73348e7b` |
| nrel_wind_toolkit / `wtk_site_metadata.csv` | 2026-10-03T06:06:00.703949+00:00 | 10,242,519 | `285b46161371974dc88b1f389ec623a5796f1075eb5576336fd951fd7aa82475` |
| ntad / `features.esri.json` | 2026-10-03T06:08:55.826801+00:00 | 4,943,918 | `8c71910a6b8c54fe9028420bb22e112a82fe5e06f925ea2bd13203cd1f84fe33` |
| us_drought_monitor / `county_drought.csv` | 2026-10-03T06:05:32.382820+00:00 | 30,182,034 | `8d062b6f61c41ca7d11c86cff5a459cdd7aa800a639428febc0d27fbec3dc19a` |

Native URLs and local cache identities (credentials are absent):

- berkeley_queued_up/native: [official native request](https://eta-publications.lbl.gov/sites/default/files/2026-05/lbnl_ix_queue_data_file_thru2025.xlsx); request identity `01c41c5ee800be873bd2`.
- eia_861/native: [official native request](https://www.eia.gov/electricity/data/eia861/zip/f8612024.zip); request identity `a8e2f2dbe78584cd90ee`.
- nasa_nex_gddp_cmip6/pr: [official native request](https://ds.nccs.nasa.gov/thredds/ncss/grid/AMES/NEX/GDDP-CMIP6/ACCESS-CM2/ssp245/r1i1p1f1/pr/pr_day_ACCESS-CM2_ssp245_r1i1p1f1_gn_2030_v2.0.nc?var=pr&north=30.75&south=29.75&west=-96.25&east=-95.25&horizStride=1&time_start=2030-01-01T00%3A00%3A00Z&time_end=2030-12-31T23%3A59%3A59Z&accept=netcdf3&addLatLon=true); request identity `e5a39194b7941795091d`.
- nasa_nex_gddp_cmip6/tas: [official native request](https://ds.nccs.nasa.gov/thredds/ncss/grid/AMES/NEX/GDDP-CMIP6/ACCESS-CM2/ssp245/r1i1p1f1/tas/tas_day_ACCESS-CM2_ssp245_r1i1p1f1_gn_2030_v2.0.nc?var=tas&north=30.75&south=29.75&west=-96.25&east=-95.25&horizStride=1&time_start=2030-01-01T00%3A00%3A00Z&time_end=2030-12-31T23%3A59%3A59Z&accept=netcdf3&addLatLon=true); request identity `4b1fec7b44a805b54eb3`.
- nasa_nex_gddp_cmip6/tasmax: [official native request](https://ds.nccs.nasa.gov/thredds/ncss/grid/AMES/NEX/GDDP-CMIP6/ACCESS-CM2/ssp245/r1i1p1f1/tasmax/tasmax_day_ACCESS-CM2_ssp245_r1i1p1f1_gn_2030_v2.0.nc?var=tasmax&north=30.75&south=29.75&west=-96.25&east=-95.25&horizStride=1&time_start=2030-01-01T00%3A00%3A00Z&time_end=2030-12-31T23%3A59%3A59Z&accept=netcdf3&addLatLon=true); request identity `20d67841bc794501af22`.
- nasa_nex_gddp_cmip6/tasmin: [official native request](https://ds.nccs.nasa.gov/thredds/ncss/grid/AMES/NEX/GDDP-CMIP6/ACCESS-CM2/ssp245/r1i1p1f1/tasmin/tasmin_day_ACCESS-CM2_ssp245_r1i1p1f1_gn_2030_v2.0.nc?var=tasmin&north=30.75&south=29.75&west=-96.25&east=-95.25&horizStride=1&time_start=2030-01-01T00%3A00%3A00Z&time_end=2030-12-31T23%3A59%3A59Z&accept=netcdf3&addLatLon=true); request identity `2d34533e539368792500`.
- noaa_ibtracs/native: [official native request](https://www.ncei.noaa.gov/data/international-best-track-archive-for-climate-stewardship-ibtracs/v04r01/access/csv/ibtracs.NA.list.v04r01.csv); request identity `4e74f25b18aba9d567e2`.
- nrel_wind_toolkit/native: [official native request](https://data.nlr.gov/system/files/54/wtk_site_metadata.csv); request identity `5e80ed87cfe12788d7b1`.
- ntad/native: [official native request](https://services.arcgis.com/xOi1kZaI0eWDREZv/ArcGIS/rest/services/NTAD_North_American_Rail_Network_Lines/FeatureServer/0/query?f=json&objectIds=289419%2C289420%2C289426%2C289427%2C289428%2C289470%2C289510%2C289511%2C289512%2C289513%2C289514%2C289515%2C289516%2C289578%2C289581%2C289582%2C289583%2C289595%2C289596%2C289597%2C289630%2C289632%2C289650%2C289651%2C289652%2C289653%2C289654%2C289656%2C289665%2C289666%2C289667%2C289668%2C289669%2C289670%2C289671%2C289696%2C289732%2C289733%2C289752%2C289753%2C301744%2C303155%2C303156%2C303157%2C303158%2C303185%2C303186%2C303187%2C303188%2C303189%2C303190%2C303191%2C303192%2C303193%2C303194%2C303195%2C303196%2C303197%2C303198%2C303199%2C303200%2C303201%2C303202%2C303203%2C303204%2C303205%2C303206%2C303207%2C303208%2C303209%2C303210%2C303211%2C303212&outFields=%2A&outSR=4326&returnGeometry=true); request identity `80d519ee16bed31da370`.
- us_drought_monitor/native: [official native request](https://usdmdataservices.unl.edu/api/CountyStatistics/GetDroughtSeverityStatisticsByAreaPercent?aoi=TX&startdate=1%2F1%2F2000&enddate=12%2F31%2F2024&statisticsType=1); request identity `364e8d37b621912e0c1e`.

Selected native data total: 123,230,430 bytes. The run manifest separately counts every current raw/interim file, including other phases and extracted copies.
