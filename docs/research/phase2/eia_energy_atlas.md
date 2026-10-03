# Source recon: `eia_energy_atlas` — EIA U.S. Energy Atlas energy-infrastructure layers

Status: **PARTIAL** (power plants + natural gas pipelines + transmission lines: READY with caveats; electric
substations: **BLOCKED**, no public authoritative layer found).
Researched: 2026-10-02. All URLs below were fetched live on this date; HTTP status and size are as observed then
and may drift (these are live government/ArcGIS services, not a frozen release).

## 1. Product / version

The EIA **U.S. Energy Atlas** (`atlas.eia.gov`) is EIA's ArcGIS Online/ArcGIS Hub mapping platform, relaunched
January 4, 2021 with "84 map layers, 60 … based on EIA surveys" (EIA, *Today in Energy*, "EIA releases new U.S.
Energy Atlas…", `verified_from`: https://www.eia.gov/todayinenergy/detail.php?id=45697, fetched 2026-10-02,
HTTP 200). The layers relevant to this brief live in the ArcGIS Online organization `FiaPA4ga0iQKduv3`
(a shared federal-agency hosting org; public display name resolves through `atlas-eia.opendata.arcgis.com` and
`fedmaps.maps.arcgis.com`), under the publishing account `Federal_User_Community`. These are **hosted feature
*views*** over data EIA/Esri periodically refresh from federal source systems — not static file releases, so
"version" here means "the live service state observed on 2026-10-02," identified below by each layer's own
data-vintage field where one exists.

| Layer (assigned feature) | ArcGIS item id | Status on 2026-10-02 | Data vintage |
|---|---|---|---|
| U.S. Electric Power Transmission Lines (Archive) | `d4090758322c4d32a4cd002ffaa0aa12` | **ARCHIVED** — "This feature layer has been archived. It will no longer be updated or maintained." | Last Data Update **2024-09-30** (item description); per-segment `SOURCEDATE`/`VAL_DATE` range from 1996 to 2024-09-26 |
| Electric substations | *(no item exists)* | **BLOCKED** — no public EIA/HIFLD substation point layer | n/a |
| Power Plants in the U.S. | `b063316fac7345dba4bae96eaa813b2f` | Active, "checked monthly for updates" (item snippet) | `Period` field = **"202502"** (Feb 2025, EIA-860M) for all 13,445 exported records |
| Natural Gas Interstate and Intrastate Pipelines | `9833ca6c8103490b8ad145a30f0522ee` | Active, "checked monthly for updates" (item snippet) | No per-record date field; item `modified` = 2026-09-22 (weak signal only, see §9) |

`verified_from` for the whole table: ArcGIS Online item API, `https://www.arcgis.com/sharing/rest/content/items/<id>?f=json`, fetched 2026-10-02, all HTTP 200 (sizes 6.1–10.9 KB).

### IMPORTANT — HIFLD Open status (as requested)

HIFLD Open (`hifld-open-geoplatform…`), the Department of Homeland Security portal that used to be the
canonical upstream for the transmission-line layer, **was shut down on 2025-08-26 and the HIFLD website/portal
were fully offline by 2025-09-16** (NAPSG Foundation / community reporting; `verified_from`:
https://atcoordinates.info/2025/08/08/hifld-open-gis-portal-shuts-down-aug-26-2025/ and
https://blog.geomusings.com/2025/07/02/hifld-open-is-dead-long-live-hifld/, both fetched 2026-10-02, HTTP 200).
DHS gave no operational reason beyond "no longer a priority." The restricted "HIFLD Secure" site remains for
vetted DHS partners only; most Open HIFLD layers were **not** migrated there.

Consequence for this project: EIA's own FAQ (`faq.php?id=567`) still tells users to "contact HIFLD directly" for
transmission-line shapefiles — **that instruction is now stale**, because HIFLD Open no longer exists. The only
currently working public access path for this particular dataset is EIA's own cached copy on `atlas.eia.gov`,
and that copy has itself been explicitly archived (frozen 2024-09-30, i.e. *before* the HIFLD shutdown). There is
currently **no actively-maintained public transmission-line feature service** anywhere in the EIA/HIFLD chain.
I confirmed this by searching the entire ArcGIS Online org that hosts the EIA Atlas (`orgid:FiaPA4ga0iQKduv3`)
for every item with "Transmission" in the title: the only Feature Service returned is the archived one; the other
five hits are screen-capture images and a metadata PDF (`verified_from`: ArcGIS Online search API,
`https://www.arcgis.com/sharing/rest/search?q=orgid:FiaPA4ga0iQKduv3 AND title:Transmission&f=json`, fetched
2026-10-02, HTTP 200, total=6).

## 2. Endpoints (verified)

All endpoints below were checked live with `curl` on 2026-10-02 (HTTP status + bytes as shown; `-L` follows the
one redirect some Hub URLs issue).

| # | URL | Method | HTTP | Bytes | What it is |
|---|---|---|---|---|---|
| 1 | https://atlas.eia.gov/ | GET | 200 | 27,776 | Atlas homepage (JS SPA shell) |
| 2 | https://www.eia.gov/maps/ | GET | 200 | 60,508 | EIA Maps landing page |
| 3 | https://atlas.eia.gov/datasets/d4090758322c4d32a4cd002ffaa0aa12_0/about | GET | 200 | 28,260 | Transmission lines (Archive) catalog page |
| 4 | https://atlas.eia.gov/datasets/b063316fac7345dba4bae96eaa813b2f_0/about | GET | 200 | 28,263 | Power Plants catalog page |
| 5 | https://atlas.eia.gov/datasets/9833ca6c8103490b8ad145a30f0522ee_0/about | GET | 200 | 28,476 | Natural Gas Pipelines catalog page |
| 6 | https://www.eia.gov/tools/faqs/faq.php?id=567 | GET | 200 | 47,847 | Official FAQ: plants/transmission/**substations** publication status |
| 7 | https://www.eia.gov/todayinenergy/detail.php?id=45697 | GET | 200 | 51,499 | "EIA releases new U.S. Energy Atlas" article |
| 8 | https://www.eia.gov/about/copyrights_reuse.php | GET | 200 | 52,512 | EIA copyright/reuse policy |
| 9 | https://services2.arcgis.com/FiaPA4ga0iQKduv3/arcgis/rest/services/US_Electric_Power_Transmission_Lines/FeatureServer?f=json | GET | 200 | 3,429 | Transmission lines service root |
| 10 | …/US_Electric_Power_Transmission_Lines/FeatureServer/**0**?f=json | GET | 200 | 16,448 | Transmission lines layer schema (fields, domains) |
| 11 | https://services2.arcgis.com/FiaPA4ga0iQKduv3/arcgis/rest/services/Power_Plants_in_the_US/FeatureServer?f=json | GET | 200 | 2,912 | Power plants service root |
| 12 | …/Power_Plants_in_the_US/FeatureServer/**0**?f=json | GET | 200 | 79,107 | Power plants layer schema |
| 13 | https://services2.arcgis.com/FiaPA4ga0iQKduv3/arcgis/rest/services/Natural_Gas_Interstate_and_Intrastate_Pipelines_1/FeatureServer?f=json | GET | 200 | 2,941 | Gas pipelines service root |
| 14 | …/Natural_Gas_Interstate_and_Intrastate_Pipelines_1/FeatureServer/**0**?f=json | GET | 200 | 10,943 | Gas pipelines layer schema |
| 15 | `.../FeatureServer/0/query?where=1=1&returnCountOnly=true&f=json` (any of the 3 layers) | GET | 200 | small | Live record count |
| 16 | https://hub.arcgis.com/api/download/v1/items/`<itemid>`/geojson?layers=0&spatialRefId=4326 | GET | 200/206 | varies | **Bulk GeoJSON export** (used for pre-download, see §8) |
| 17 | https://www.arcgis.com/sharing/rest/content/items/`<itemid>`?f=json | GET | 200 | 6.1–10.9 KB | Item metadata (owner, org, license, modified date) |
| 18 | https://www.arcgis.com/sharing/rest/content/items/3efd0f1b88d4495facba8161570e84af/data | GET | 200 | 197,830 | `Metadata_transmission_lines_hifld_v5` PDF (supplementary field documentation) |
| 19 | https://www.eia.gov/electricity/data/eia860m/ | GET | 200 | 93,644 | EIA-860M raw monthly CSV/XLSX (has an explicit plant **status** code EIA's Atlas layer lacks, see §9) |

ArcGIS item ids used above: transmission (archive) = `d4090758322c4d32a4cd002ffaa0aa12`; power plants =
`b063316fac7345dba4bae96eaa813b2f`; natural gas pipelines = `9833ca6c8103490b8ad145a30f0522ee`. These three ids
were found by searching the ArcGIS Online org that backs the EIA Atlas (org id `FiaPA4ga0iQKduv3`), not by
guessing — see the search calls referenced in §1.

No endpoint in this brief required a login, API key, click-through terms, or CAPTCHA. The ArcGIS `/sharing/rest`
and `/FeatureServer` endpoints are anonymous public REST, consistent with AGENTS.md §4.

## 3. CRS / resolution / coverage

- **Native hosted-service spatial reference**: `wkid 102100` / `latestWkid 3857` (Web Mercator) for all three
  FeatureServer layers (`verified_from`: each `FeatureServer/0?f=json` response, field `spatialReference`).
- **GeoJSON export CRS is NOT reliable by default** — see the CRS gotcha in §9/§10; `spatialRefId=4326` must be
  requested explicitly.
- **Geometry types**: transmission lines and gas pipelines = `esriGeometryPolyline`; power plants =
  `esriGeometryPoint`.
- **Coverage**: nationwide (CONUS + AK/HI/territories are mixed in; the dev-area bbox below is CONUS Gulf
  coast). No native "resolution" in the raster sense — these are discrete engineering features (plants, line
  segments, pipeline segments), so coverage is a function of how completely HIFLD/EIA's source compilation
  mapped each utility's infrastructure, which is **known to be incomplete and non-uniform** (import dates on
  individual transmission segments range from 1996 to 2024; §9).
- **Record counts, verified by live query** (`returnCountOnly=true`, fetched 2026-10-02):

  | Layer | National count | Count inside dev bbox `[-98.0,29.0,-93.0,33.0]` (EPSG:4326 envelope, `esriSpatialRelIntersects`) |
  |---|---|---|
  | Transmission lines (archive) | 94,619 | 4,010 |
  | Power plants | 13,446 (13,445 in the GeoJSON export, see §9) | 365 |
  | Natural gas pipelines | 32,892 | 3,976 |

## 4. Fields / units / codes

All of the following are `verified_from` the live layer schema (`FeatureServer/0?f=json`) plus distinct-value and
min/max queries against the live data on 2026-10-02 (exact query URLs are reproducible: append
`/query?where=1=1&outFields=<FIELD>&returnDistinctValues=true&returnGeometry=false&f=json` to the layer URLs in
§2). Field lists below are not exhaustive (full lists are in the schema JSON); they cover the attributes needed
for the requested features.

### 4.1 Electric Power Transmission Lines (Archive) — `FeatureServer/0`, polyline, 94,619 features

| Field | Alias | Type | Values / range | Missing/no-data code |
|---|---|---|---|---|
| `VOLTAGE` | Voltage (Kilovolts) | double | observed range **-999999 to 1000 kV** | **`-999999` is a sentinel for unknown voltage — NOT a real value, never average/sum it in.** |
| `VOLT_CLASS` | Voltage Class | string(13) | `UNDER 100`, `100-161`, `220-287`, `345`, `500`, `735 AND ABOVE`, `DC`, `SUB 100`, `NOT AVAILABLE`, `Unknown` | `NOT AVAILABLE` / `Unknown` are both no-data sentinels (distinct strings, not blank) |
| `STATUS` | Operational Status of Line | string(18) | `IN SERVICE`, `INACTIVE`, `UNDER CONSTRUCTION`, `NOT AVAILABLE` | `NOT AVAILABLE` |
| `TYPE` | Line Type | string(15) | `AC; OVERHEAD`, `AC; UNDERGROUND`, `DC; OVERHEAD`, `DC; UNDERGROUND`, `OVERHEAD`, `UNDERGROUND`, `NOT AVAILABLE` | `NOT AVAILABLE` |
| `OWNER` | Transmission Line Ownership Entity | string(62) | utility/company name | `NOT AVAILABLE` |
| `SUB_1` / `SUB_2` | Origin/Destination Substation Name | string(44/60) | free text | frequently `UNKNOWN######` or `TAP######` placeholders (see §9 — **not a usable substation inventory**) |
| `SOURCE` | Data Source Reference | string(254) | free text, e.g. `"IMAGERY, OpenStreetMap"`, `"IMAGERY, EIA 861"` | — |
| `SOURCEDATE` / `VAL_DATE` | Source publication / validation date | date | **min 1996-01-02, max 2024-09-26** (epoch ms 820454400000–1727308800000) | per-segment, highly heterogeneous |
| `NAICS_CODE` / `NAICS_DESC` | — | string | e.g. `221121` / `ELECTRIC BULK POWER TRANSMISSION AND CONTROL` | — |
| `Shape__Length` | — | double, meters (service units `esriMeters`) | line length | — |

Dev-bbox `VOLT_CLASS` distribution (4,010 segments): `100-161`=2,623, `UNDER 100`=916, `345`=310, `220-287`=65,
`500`=11, `NOT AVAILABLE`=85 (≈2.1%). Nationally, `VOLT_CLASS` is `NOT AVAILABLE`/`Unknown` for 8,823/94,619
(≈9.3%) segments.

No `VOLT_CLASS`/`STATUS`/`TYPE` field has an ArcGIS **coded-value domain** (`"domain":null` in the schema) — the
code lists above come from actually querying distinct values, not from a domain definition, and are therefore
not contractually guaranteed to be exhaustive if the source data changes.

### 4.2 Power Plants in the U.S. — `FeatureServer/0`, point, 13,446 features (13,445 in GeoJSON export)

| Field | Alias | Type | Values / range | Notes |
|---|---|---|---|---|
| `Plant_Code` | EIA Plant ID | integer | — | join key to EIA-860/860M/923 |
| `PrimSource` | Primary Energy Source | string(14) | `batteries, biomass, coal, geothermal, hydroelectric, natural gas, nuclear, other, petroleum, pumped storage, solar, wind` (12 values, all populated — no UNKNOWN sentinel observed) | fuel category requested by the task |
| `sector_nam` | Electric Power Sector | string(18) | `Commercial Non-CHP, Commercial CHP, Electric Utility, Industrial CHP, Industrial Non-CHP, IPP CHP, IPP Non-CHP` (7, the canonical EIA-860 sector codes) | — |
| `Install_MW` | Installed Nameplate Capacity | double, MW | e.g. 21.3 | **nameplate**, not the same as `Total_MW` |
| `Total_MW` | Maximum Summer Capacity | double, MW | e.g. 19.3 | **summer net capacity** — different engineering quantity from nameplate; pick one explicitly, document which |
| `Coal_MW,Hydro_MW,HydroPS_MW,NG_MW,Nuclear_MW,Crude_MW,Solar_MW,Wind_MW` | per-fuel MW | **double** | — | clean numeric |
| `Bat_MW,Bio_MW,Geo_MW,Other_MW` | per-fuel MW | schema says **string(4000)**, but observed JSON values are unquoted numbers (e.g. `"Bat_MW":0`) | **schema/data type mismatch — coerce explicitly, verify null vs 0 per field** |
| `Period` | Data Reporting Period | string "YYYYMM" | **uniformly `"202502"` across all 13,445 exported records** (confirmed via `returnDistinctValues`) | this is the authoritative data-vintage field, *not* the ArcGIS item "modified" timestamp (see §9) |
| `Longitude`/`Latitude` | — | double, decimal degrees | — | redundant with point geometry |

No `Status`/operating-state field is exposed in this layer at all. Per the item description, the layer
intentionally "depicts **all operable** electric generating plants … This includes plants that are operating, on
standby, or short- or long-term out of service," with a ≥1 MW combined nameplate-capacity cutoff
(`verified_from`: ArcGIS item description for `b063316fac7345dba4bae96eaa813b2f`, fetched 2026-10-02). That means
**you cannot filter to "currently generating" plants from this layer's attributes alone**; a plant with
`Total_MW` > 0 for a fuel is not proof it is online today, and the EIA-860M raw file (endpoint #19 above) carries
an explicit status code (`OP`, `SB`, `OA`, `OS`, `RE`, …) this Atlas layer does not expose.

### 4.3 Natural Gas Interstate and Intrastate Pipelines — `FeatureServer/0`, polyline, 32,892 features

| Field | Alias | Type | Values |
|---|---|---|---|
| `TYPEPIPE` | Type of Pipe | string(10) | `Interstate`, `Intrastate` |
| `Operator` | Company Operator | string(50) | free text |
| `Status` | Operational Status | string(9) | **only `Operating` observed** across all 32,892 features, even though the field's own description text mentions "Active, Inactive, or Abandoned" as the general domain |
| `Shape__Length` | — | double, meters | pipeline segment length |

No capacity, diameter, or throughput attribute exists in this layer (confirmed by reading the full field list in
the schema — there are exactly 5 substantive fields). If pipeline capacity-weighting is ever required, it is not
available from this spatial layer and would need EIA's separate non-spatial natural-gas pipeline-capacity tables
— flagged as an open question, not implemented here.

### 4.4 Electric substations — **no field schema to report (BLOCKED)**

EIA's own FAQ states in plain language: **"EIA and HIFLD do not publish the location of electric substations."**
(`verified_from`: https://www.eia.gov/tools/faqs/faq.php?id=567, fetched 2026-10-02, HTTP 200, quoted verbatim).
I independently confirmed this by searching the hosting ArcGIS org for any item with "Substation" in the title:
zero results (`orgid:FiaPA4ga0iQKduv3 AND title:Substation` → `total: 0`). The only substation-adjacent data that
exists is the free-text `SUB_1`/`SUB_2` name fields on the transmission-line layer (§4.1), which are frequently
placeholders and carry no coordinates of their own — see §9 for why these are not a usable substitute.

## 5. License

- **Underlying data**: EIA states plainly that "U.S. government publications are in the public domain and are
  not subject to copyright protection," and that users "may use and/or distribute any of our data, files,
  databases, reports, graphs, charts, and other information products," with a recommended (not mandatory)
  attribution such as "Source: U.S. Energy Information Administration (Oct 2008)."
  (`verified_from`: https://www.eia.gov/about/copyrights_reuse.php, fetched 2026-10-02, HTTP 200, quoted).
  Each ArcGIS item's `accessInformation` field independently confirms attribution: `"Energy Information
  Administration (EIA)"` for the power-plants and gas-pipelines items, `"U.S. Government"` for the archived
  transmission-lines item.
- **Hosting platform wrapper**: every item's `licenseInfo` carries Esri's standard boilerplate — "This work is
  licensed under the Esri Master License Agreement" with links to `links.esri.com/tou_summary` and
  `links.esri.com/agol_tou`. This is Esri's generic ArcGIS Online hosting-service terms (how you may use the
  *service*), layered on top of — not replacing — the public-domain status of the underlying federal data. I did
  not find anything in this layer's boilerplate that purports to restrict redistribution of the public-domain
  content itself.
- Net assessment: safe to cache, redistribute internally, and use for this project with attribution to EIA; no
  separate data license needs to be negotiated.

## 6. Access

No login, account creation, API key, click-through terms, or CAPTCHA was encountered anywhere in this chain
(Atlas pages, ArcGIS Hub catalog pages, `/sharing/rest` item API, `/FeatureServer` REST endpoints, or the Hub
bulk-download API). Everything in this report was retrieved with anonymous `curl`/`requests` GETs. This is
consistent with AGENTS.md §4 (no access-control bypass was needed or attempted).

## 7. Recommended aggregation (CONUS 10 km × 10 km, EPSG:5070)

These are **point/line proximity features**, not polygon zonal statistics, so the recommended method differs
from, e.g., a land-cover or Aqueduct polygon adapter:

1. **Reproject once, up front**: load each cached layer, reproject geometries from their *verified* CRS (see
   §9 CRS gotcha — do not assume EPSG:4326) into EPSG:5070 metres, build a spatial index (e.g. `geopandas`
   `.sindex`, a `STRtree`) over the reprojected geometries. This is a one-time, in-memory, national-scale
   operation (no network calls — the cache under `data/raw/eia_energy_atlas/` already contains the full
   national extent for all three implemented layers; see §8).
2. **Nearest-distance features** (transmission line, gas pipeline, power plant): for each grid cell, compute the
   minimum distance in EPSG:5070 metres from the cell geometry (recommend cell **boundary**, not just centroid,
   since a 10 km cell can contain or be crossed by a line — distance to a cell that is actually intersected
   should be 0, not centroid-to-feature) to the nearest feature using the spatial index (`nearest()` /
   `sindex.nearest`). Record the winning feature's id and key attributes (voltage class, status, owner for
   transmission; plant fuel/capacity for plants; interstate/intrastate for pipelines) alongside the distance, so
   the "nearest feature" is auditable, not just a number.
3. **"Nearest feature with known attribute" is a second, separate query** when needed — e.g. "nearest
   transmission line with a non-`NOT AVAILABLE` `VOLT_CLASS`" will generally return a larger-or-equal distance
   than "nearest transmission line of any kind." Compute and store both explicitly rather than silently filtering
   the no-data sentinel rows out of the general nearest-distance query (which would just increase distance
   without saying why).
4. **Counts / capacity within a radius** (power plants): buffer each cell by the configured radius in EPSG:5070
   and spatial-join against plant points, summing a clearly-named capacity field (decide and document whether
   `Install_MW` or `Total_MW` is the project's standard — they are not the same quantity). Because the layer
   includes standby/out-of-service plants with no status flag (§4.2, §9), label this metric's status as
   `observed` capacity-on-the-books, not `calculated` available generation, and note the limitation inline.
5. **Multiple qualifying features per cell**: when more than one line/pipeline segment or plant is the basis for
   a cell's feature (e.g., two transmission lines of different voltage both cross one cell, or several plants
   fall inside one radius), record the **count** of qualifying source features alongside the aggregate, per the
   project's general rule for cells touching multiple source records — for point/line data this means "N
   features contributed" rather than "N source regions overlapped," but the intent (don't silently blend without
   disclosure) is the same.
6. **No per-cell HTTP requests are needed at all**: because the national layers are small enough to fully cache
   locally (§8), the entire computation is local vector geometry work, consistent with AGENTS.md §4/§7's
   batch-processing and no-per-cell-request rules.

## 8. Volume / memory estimate

National feature counts (verified, §3): 94,619 transmission-line segments, 13,446 power plants, 32,892 gas
pipeline segments. These were pre-downloaded in full (see below) as GeoJSON:

| File | Bytes | Features |
|---|---|---|
| `eia_electric_power_transmission_lines_archive_national.geojson` | 160,785,995 (~153 MiB) | 94,619 |
| `eia_power_plants_national.geojson` | 10,385,398 (~9.9 MiB) | 13,445 |
| `eia_natural_gas_interstate_intrastate_pipelines_national.geojson` | 14,773,757 (~14.1 MiB) | 32,892 |
| **Total** | **185,945,150 bytes (~177 MiB ≈ 0.19 GB)** | — |

This is well inside the 12 GB optional-pre-download budget and far inside the project's ~4 GB per-process memory
budget (AGENTS.md §7) — loading all three national layers, reprojecting, and spatially indexing them
simultaneously is reasonably estimated (not measured/benchmarked) at a few hundred MB of resident memory, since
these are modest point/line feature counts with short attribute rows, not a raster.

- **Dev area** (4,010 + 365 + 3,976 = 8,351 candidate features intersecting the bbox): trivial, sub-second
  nearest-distance computation against ~90,000 CONUS 10 km cells is not the bottleneck; the bbox itself covers a
  small fraction of the grid.
- **National processing**: a CONUS 10 km × 10 km grid is on the order of 80,000–100,000 cells (order-of-magnitude
  estimate from CONUS land area ÷ 100 km² per cell; the authoritative count comes from Phase 1's
  `us_grid.parquet`, not from this recon). Nearest-neighbor queries against a pre-built spatial index over
  ~95,000 line segments / ~13,000 points are `O(log n)` per cell and should complete in low single-digit minutes
  single-threaded, well under the memory budget. This is an estimate based on feature/cell counts, not a
  measured benchmark — the Phase 2 implementer should confirm with a real timing run.

## 9. Interpretation limits (binding language per AGENTS.md §8 applies to any output derived from this source)

- **Proximity to transmission/pipeline/plant infrastructure is NOT power availability, interconnection capacity,
  or a guarantee of grid access** — a cell can be 200 m from a 500 kV line and still face a multi-year
  interconnection queue, or be near a line with no spare capacity. This must be stated wherever this source's
  features are used (per AGENTS.md §3.5 and the task's own instruction).
- **The transmission-line layer is a frozen archive** (last updated 2024-09-30) and will **not** reflect any
  transmission built, retired, or re-rated after that date; there is currently no active public replacement
  (§1). Any "distance to nearest transmission line" feature computed from this source is therefore a 2024
  snapshot by construction, not a live figure.
- **Electric substations cannot be mapped from any public EIA/HIFLD source today.** This is a hard gap, not an
  oversight — mark the corresponding feature `UNKNOWN`/adapter status `BLOCKED`, never zero or silently omitted.
- **Per-segment data currency inside the transmission layer is highly heterogeneous**: `SOURCEDATE`/`VAL_DATE`
  range from 1996 to 2024 within the same file, so "last updated 2024-09-30" describes the layer's last
  *republish*, not the age of any individual line segment's underlying survey.
- **Power-plant capacity figures mix nameplate and summer-net capacity** (`Install_MW` vs `Total_MW`) and include
  standby/out-of-service units with no way to filter them out from this layer alone (§4.2) — any capacity-within-
  radius metric should be labeled accordingly and cross-referenced against raw EIA-860M status codes if a
  "currently operating only" cut is required.
- **The natural-gas pipeline layer carries no capacity/diameter/throughput data**, so proximity cannot be
  capacity-weighted from this source.
- **The `Period` field (power plants) is the authoritative data-vintage indicator, not the ArcGIS item's
  "modified" timestamp.** The item's `modified` date for the power-plants layer was 2026-09-22 and its snippet
  claims monthly checks, yet every one of the 13,445 exported records carries `Period="202502"` (February 2025)
  — i.e. the cached service had not actually advanced its EIA-860M vintage in the ~19 months before this recon,
  despite being "touched" far more recently. Trust the in-data field, not the catalog metadata, for currency
  claims.

## 10. Pitfalls (hard-won from this recon — verified by direct testing, not assumption)

1. **GeoJSON export CRS is inconsistent and sometimes mislabeled.** Calling the ArcGIS Hub bulk-download API
   (`/api/download/v1/items/<id>/geojson?layers=0`) **without** `&spatialRefId=4326` silently returned
   EPSG:3857 (Web Mercator, metres) coordinates for both the transmission-lines and power-plants layers — and
   the resulting `.geojson` file's own `crs` member even says `"EPSG:3857"`, which is itself non-conformant with
   the GeoJSON spec (RFC 7946 mandates WGS84 lon/lat and discourages a `crs` member entirely). I verified this by
   downloading both ways and inspecting raw coordinate magnitude (e.g. first vertex `[-9397293.05, 5271551.21]`
   without the parameter vs. the correct `[-84.417…, 42.734…]` with `spatialRefId=4326`). The natural-gas
   pipelines endpoint, by contrast, returned correct EPSG:4326 (`CRS84`) **by default**, with no parameter needed
   — the API's default behavior is inconsistent per item/layer. **Always pass `spatialRefId=4326` explicitly and
   verify the resulting `crs` member and coordinate magnitude; never trust the default.**
2. **`VOLTAGE = -999999` is a sentinel, not data.** A naive numeric aggregate (mean/sum/min) over this field
   without excluding this sentinel will silently corrupt results (e.g. a "minimum voltage near this cell" query
   would always return -999999). The categorical sibling `VOLT_CLASS` has its own separate textual sentinels
   (`"NOT AVAILABLE"`, `"Unknown"`) that must also be excluded from any categorical summary, not coerced to a
   fabricated numeric midpoint.
3. **`SUB_1`/`SUB_2` (transmission-line endpoint "substation" names) are not a usable substation inventory.**
   Sampled values include `"UNKNOWN128553"` and `"TAP139917"` — i.e. many are auto-generated placeholders for an
   unresolved endpoint or a mid-line tap point, not a real named substation, and none of them carry their own
   coordinate (only the line's endpoint vertex does). Treat any count of "distinct SUB_1/SUB_2 values" as a very
   rough upper bound on substation-like nodes, not a verified count, and never geocode the name string.
4. **Schema/data type mismatch on several Power Plants fields.** `Bat_MW`, `Bio_MW`, `Geo_MW`, `Other_MW` are
   declared `esriFieldTypeString(4000)` in the schema but the query/export API returns unquoted JSON numbers
   (e.g. `"Bat_MW":0`) for them in practice — a strict-typed reader expecting a string will misbehave. Coerce
   explicitly and test null-vs-zero handling per field before trusting any aggregate built from them.
5. **The power-plants GeoJSON export is missing exactly one record relative to the live service's own count**
   (13,445 exported vs. 13,446 via `returnCountOnly=true`), reproduced identically across two independent export
   requests on 2026-10-02. Cause not verified (most likely one record with null/invalid geometry dropped by the
   exporter, since GeoJSON requires geometry and the FeatureServer count does not). Treat as a small, apparently
   stable discrepancy to re-check on any future re-pull, not as a sign the whole download is corrupt.
6. **`returnDistinctValues=true` without `returnGeometry=false` returns full geometries anyway** (and sets
   `exceededTransferLimit:true`), which is a slow, multi-megabyte way to get a tiny list of codes. Always add
   `returnGeometry=false` to distinct-value / statistics queries against these layers.
7. **EIA's own FAQ page's redirection to HIFLD for transmission shapefiles is now stale** (HIFLD Open shut down
   2025-08-26; see §1) — do not follow that specific instruction literally; use the archived EIA-hosted copy
   instead and document it as a frozen 2024-09-30 snapshot.

## 11. Open questions (for the Phase 2 technical lead / orchestrator to decide — not decided here)

1. **Substations**: accept the gap as `BLOCKED`/`UNKNOWN` for now, or approve a documented `proxy`-status
   workaround (e.g., deriving candidate substation-like point locations from transmission-line endpoint vertices,
   excluding `TAP######`/`UNKNOWN######` placeholders)? This project's source policy (`master_prompt.md`,
   "Source policy") says not to silently substitute a weaker proxy for a requested source without justification
   — this recon flags the option but does not adopt it.
2. Should capacity-within-radius use `Install_MW` (nameplate) or `Total_MW` (summer net) as the project standard
   unit for "plant capacity," and should standby/out-of-service plants be included or excluded (requires joining
   to raw EIA-860M status codes, which this Atlas layer does not expose)?
3. Is a non-spatial EIA natural-gas pipeline capacity table worth adding as a second source to capacity-weight
   the pipeline-proximity feature, given the Atlas pipeline layer itself has no capacity/diameter attribute?
4. Should the adapter re-pull these layers from the live FeatureServer periodically (they are "checked monthly"
   per EIA, though the power-plants `Period` value shows that cadence is not always honored in practice — see
   §9), or treat this recon's cached national GeoJSON snapshot (§8) as the frozen Phase 2 input and re-run this
   recon's download step on a documented schedule?

---

### Appendix: files written by this recon agent

- `data/raw/eia_energy_atlas/eia_electric_power_transmission_lines_archive_national.geojson` (160,785,995 bytes)
- `data/raw/eia_energy_atlas/eia_power_plants_national.geojson` (10,385,398 bytes)
- `data/raw/eia_energy_atlas/eia_natural_gas_interstate_intrastate_pipelines_national.geojson` (14,773,757 bytes)
- `data/raw/eia_energy_atlas/download_log.json` (manifest: url, path, bytes, sha256, retrieved_at_utc, notes for
  each file above)

All three are national, EPSG:4326, public, no-login direct downloads via the ArcGIS Hub bulk-download API,
combined size ≈0.19 GB (within the 12 GB optional pre-download budget). No files were pre-downloaded for
electric substations because no public dataset exists to download (§1, §4.4).
