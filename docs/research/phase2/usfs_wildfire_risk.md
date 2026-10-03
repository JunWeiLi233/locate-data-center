# Data-source reconnaissance: `usfs_wildfire_risk`

Status: **READY** (both products are public, no-login, directly downloadable; native CRS matches the
project grid; core files verified by direct inspection). Pre-download: **PARTIAL** (WHP fully
pre-downloaded; WRC state files for the dev area exceed the 12 GB budget and were verified but not
fetched — see `data/raw/usfs_wildfire_risk/download_log.json`).

This source actually covers **two distinct, separately versioned USDA Forest Service Research Data
Archive (RDA) publications**, as the task anticipated:

| Short name | Full title | Current edition (verified) | DOI |
|---|---|---|---|
| **WRC** | Wildfire Risk to Communities: Spatial datasets of landscape-wide wildfire risk components for the United States | **2nd Edition**, 2024 | `10.2737/RDS-2020-0016-2` |
| **WHP** | Wildfire Hazard Potential for the United States (270-m), version 2023 | **4th Edition**, published 2023, updated 17 Jul 2024 | `10.2737/RDS-2015-0047-4` |

A third, related RDA publication — **Dillon, Gregory K. et al. 2023, "Spatial datasets of
probabilistic wildfire risk components for the United States (270m)", 3rd Edition,
`10.2737/RDS-2016-0034-3`** — is the raw 270‑m FSim burn-probability/flame-length-probability
simulation output that *both* WRC and WHP are built from. It is a different RDS number, was not
one of the two assigned products, and is not separately needed: its content is already incorporated
into WRC and WHP. Mentioned here only so it isn't confused with the two target products.
(`verified_from`: WRC methods white paper reference list, see §5.)

An AI-generated web-search summary (not a primary source) at one point called RDS-2020-0016 a "3rd
edition (2023)" — that appears to be a conflation with RDS-2016-0034-3's edition number. I did not
rely on it: the edition/date below were read directly from the official FGDC XML metadata and the
methods PDF, both fetched and opened in this session.

---

## 1. Product / version (verified)

### 1a. WRC — Wildfire Risk to Communities, 2nd Edition

- Citation (quoted from the live catalog page, `https://www.fs.usda.gov/rds/archive/catalog/RDS-2020-0016-2`, HTTP 200):
  Scott, Joe H.; Dillon, Gregory K.; Jaffe, Melissa R.; Vogler, Kevin C.; Olszewski, Julia H.;
  Callahan, Michael N.; Karau, Eva C.; Lazarz, Mitchell T.; Short, Karen C.; Riley, Karin L.;
  Finney, Mark A.; Grenfell, Isaac C. 2024. *Wildfire Risk to Communities: Spatial datasets of
  landscape-wide wildfire risk components for the United States.* 2nd Edition. Fort Collins, CO:
  Forest Service Research Data Archive. https://doi.org/10.2737/RDS-2020-0016-2
- `verified_from`: the FGDC-CSDGM metadata XML (`_metadata_RDS-2020-0016-2.xml`, fetched directly,
  HTTP 200, 64,342 bytes) contains `<edition>2nd</edition>` and `<pubdate>2024</pubdate>` verbatim.
  The bundled methods white paper (downloaded; see §9) is dated **May 15, 2024** and opens by
  calling itself "this second release of WRC data (WRC 2.0)".
- This product legitimately supersedes the original RDS-2020-0016 (1st edition, 2020); the 1st-edition
  catalog page (`.../catalog/RDS-2020-0016`, no `-2` suffix) still resolves (HTTP 200) but displays
  "Out-of-date version (current version: RDS-2020-0016-2)".
- Produced by USDA Forest Service Rocky Mountain Research Station (Fire Modeling Institute) with
  Pyrologix LLC; public outreach partner Headwaters Economics. Public web app: `wildfirerisk.org`.

### 1b. WHP — Wildfire Hazard Potential, 4th Edition

- Citation (quoted from the live catalog page, `https://www.fs.usda.gov/rds/archive/catalog/RDS-2015-0047-4`, HTTP 200):
  Dillon, Gregory K. 2023. *Wildfire Hazard Potential for the United States (270-m), version 2023.*
  4th Edition. Updated 17 July 2024. Fort Collins, CO: Forest Service Research Data Archive.
  https://doi.org/10.2737/RDS-2015-0047-4
- Edition history (verified via `_metadata_RDS-2015-0047-4.html` + web search cross-check): 1st Ed.
  2015 (v2014, `RDS-2015-0047`), 2nd Ed. 2018 (v2018, `-2`), 3rd Ed. 2020 (v2020, `-3`, first to add
  AK/HI), **4th Ed. 2023 (v2023, `-4`, current)**. No `RDS-2015-0047-5` was found by repeated web
  search as of this session (2026-10-02/03).
- The 17-Jul-2024 update note (quoted from the catalog page): it corrected "a processing error
  causing NoData values in classified pixels with WHP >100,000" (those pixels were reclassified as
  Very High) and added management-jurisdiction summary tables.
- This WHP (standalone, 270 m) is methodologically related to but **numerically different** from the
  WHP layer bundled inside the WRC per-state/CONUS zips (30 m) — see the discrepancy note in §4.

---

## 2. Endpoints (all verified this session — HTTP status + size recorded)

`fs.usda.gov` catalog/search pages are slow (~35 s) but reliable; static product files and the
migrated ImageServer endpoint were fast. All requests used `User-Agent: dc_locator/0.1 (research prototype)`.

| URL | Method | Result |
|---|---|---|
| `https://www.fs.usda.gov/rds/archive/catalog/RDS-2020-0016-2` | GET | HTTP 200, 60,300 B |
| `https://doi.org/10.2737/RDS-2020-0016-2` | GET -L | HTTP 200 (redirects to the line above) |
| `https://www.fs.usda.gov/rds/archive/catalog/RDS-2015-0047-4` | GET | HTTP 200, 32,524 B |
| `https://www.fs.usda.gov/rds/archive/products/RDS-2020-0016-2/_metadata_RDS-2020-0016-2.xml` | GET | HTTP 200, 64,342 B |
| `https://www.fs.usda.gov/rds/archive/products/RDS-2015-0047-4/_metadata_RDS-2015-0047-4.xml` | GET | HTTP 200, 40,433 B |
| `https://www.fs.usda.gov/rds/archive/products/RDS-2020-0016-2/_fileindex_RDS-2020-0016-2.html` | GET | HTTP 200, 6,714 B |
| `https://www.fs.usda.gov/rds/archive/products/RDS-2015-0047-4/RDS-2015-0047-4_Data.zip` | GET (downloaded) | HTTP 200, **368,424,961 B** exactly, `Accept-Ranges: bytes` |
| `https://www.fs.usda.gov/rds/archive/products/RDS-2015-0047-4/RDS-2015-0047-4_Supplements.zip` | GET (downloaded) | HTTP 200, 27,394,253 B |
| `https://www.fs.usda.gov/rds/archive/products/RDS-2015-0047-4/RDS-2015-0047-4_Metadata_Fileindex.zip` | GET (downloaded) | HTTP 200, 22,410 B |
| `https://www.fs.usda.gov/rds/archive/products/RDS-2020-0016-2/RDS-2020-0016-2_Supplements.zip` | GET (downloaded) | HTTP 200, 730,940 B |
| `https://www.fs.usda.gov/rds/archive/products/RDS-2020-0016-2/RDS-2020-0016-2_Metadata_Fileindex.zip` | GET (downloaded) | HTTP 200, 35,575 B |
| `https://usfs-public.box.com/shared/static/8qztn7vbnyguzgtnmbsf367uzc6at4jn.zip` (Texas state zip) | GET -r 0-1023 | HTTP 301 → `public.boxcloud.com/.../download` → **HTTP 206** |
| `https://usfs-public.box.com/shared/static/tek1bx4vu3mbggxm3oad0242gizpqtbt.zip` (Louisiana) | GET -r 0-1023 | 301 → 206 (same pattern) |
| `https://usfs-public.box.com/shared/static/pys3hd29a2jdfh9v1yg1f0d2t1iz32ya.zip` (Arkansas) | GET -r 0-1023 | 301 → 206 (same pattern) |
| `https://usfs-public.box.com/shared/static/n1i3mhptsebdff0zlstofbm9ovkh3sk5.zip` (District of Columbia, 1.02 MB — downloaded **only** as a verification sample, not kept) | GET (downloaded) | HTTP 200, 1,324,033 B, sha256 matched catalog-listed value exactly |
| `https://apps.fs.usda.gov/fsgisx01/rest/services/RDW_Wildfire/RMRS_WRC_BurnProbability/ImageServer?f=json` (old endpoint) | GET | **HTTP 403** — body: *"The service being requested has been migrated to IIPP. Please visit https://imagery.geoplatform.gov/iipp/rest/services."* This is a documented relocation notice from the server itself, not a bot-block; I followed the stated new location rather than retrying with a different User-Agent. |
| `https://imagery.geoplatform.gov/iipp/rest/services/Fire_Aviation/USFS_EDW_RMRS_WRC_BurnProbability/ImageServer?f=json` | GET | HTTP 200, 11,524 B |
| …`/USFS_EDW_RMRS_WRC_ConditionalFlameLength/ImageServer?f=json` | GET | HTTP 200, 17,143 B |
| …`/USFS_EDW_RMRS_WRC_RiskToPotentialStructures/ImageServer?f=json` | GET | HTTP 200, 17,155 B |
| …`/USFS_EDW_RMRS_WRC_ConditionalRiskToPotentialStructures/ImageServer?f=json` | GET | HTTP 200, 17,124 B |
| …`/USFS_EDW_RMRS_WRC_WildfireHazardPotential/ImageServer?f=json` | GET | HTTP 200, 17,135 B |
| …`/USFS_EDW_RMRS_WRC_ExposureType/ImageServer?f=json` | GET | HTTP 200, 17,179 B |

### Files needed (bulk-download path — authoritative, used for the downloads above)

WRC ships as **one zip per raster theme × spatial extent** (never both dimensions combined in one
file): either "all 8 themes for one state/CONUS" or "all states for one theme". For the three
requested features (BP, CFL, WHP) in the dev area (TX, LA, AR), the only packaging available is the
**per-state, all-8-themes** bundle:

| File | URL (box.com, redirects to signed boxcloud.com link) | Size (claimed) | sha256 (claimed, quoted from catalog page) | Pre-downloaded? |
|---|---|---|---|---|
| `RDS-2020-0016-2_Texas.zip` | `https://usfs-public.box.com/shared/static/8qztn7vbnyguzgtnmbsf367uzc6at4jn.zip` | 18 GB | `3acbc68b715bbe10ce3cacf03f2cf6151ddb432cdb2043c5c0e2cb02cb271e60` | No (budget) |
| `RDS-2020-0016-2_Louisiana.zip` | `https://usfs-public.box.com/shared/static/tek1bx4vu3mbggxm3oad0242gizpqtbt.zip` | 2.4 GB | `e39fa2e9c474d3a71ae9aca50b754d55e96aed8228c7f465d5950791a3370593` | No (budget) |
| `RDS-2020-0016-2_Arkansas.zip` | `https://usfs-public.box.com/shared/static/pys3hd29a2jdfh9v1yg1f0d2t1iz32ya.zip` | 2.71 GB | `a0fe6af72fe6fe4bf88681fa3c908221fe427a84cbfa4e29c13c7173ec208f62` | No (budget) |
| `RDS-2015-0047-4_Data.zip` (WHP, CONUS+AK+HI, gdb + GeoTIFF) | `https://www.fs.usda.gov/rds/archive/products/RDS-2015-0047-4/RDS-2015-0047-4_Data.zip` | 368,424,961 B | `7f10f1f8dd97551b8be1458fe0ec924df60b2cea7ece2d1af4c3c1166d1895ab` | **Yes** |

TX+LA+AR = **23.11 GB**, over the 12 GB pre-download cap, so none were fetched — see §7 for why this
is also the wrong granularity for a dev-area-only workflow, and the ImageServer alternative.
CONUS-wide per-theme zips exist too (`RDS-2020-0016-2__BP_CONUS.zip` = 32.3 GB,
`__CFL_CONUS.zip` = 29.1 GB, `__WHP_CONUS.zip` = 8.17 GB, …) — these are documented in full in
`data/raw/usfs_wildfire_risk/download_log.json` and §8, with their sha256 values, but also were not
downloaded.

### REST / ImageServer option (verified, migrated endpoint)

The old `apps.fs.usda.gov/fsgisx01/rest/services/RDW_Wildfire/...` ImageServer path now returns
HTTP 403 with an explicit migration notice. The live replacement, folder `Fire_Aviation`, host
`imagery.geoplatform.gov`:

```
https://imagery.geoplatform.gov/iipp/rest/services/Fire_Aviation/USFS_EDW_RMRS_WRC_BurnProbability/ImageServer
https://imagery.geoplatform.gov/iipp/rest/services/Fire_Aviation/USFS_EDW_RMRS_WRC_ConditionalFlameLength/ImageServer
https://imagery.geoplatform.gov/iipp/rest/services/Fire_Aviation/USFS_EDW_RMRS_WRC_RiskToPotentialStructures/ImageServer
https://imagery.geoplatform.gov/iipp/rest/services/Fire_Aviation/USFS_EDW_RMRS_WRC_ConditionalRiskToPotentialStructures/ImageServer
https://imagery.geoplatform.gov/iipp/rest/services/Fire_Aviation/USFS_EDW_RMRS_WRC_WildfireHazardPotential/ImageServer
https://imagery.geoplatform.gov/iipp/rest/services/Fire_Aviation/USFS_EDW_RMRS_WRC_ExposureType/ImageServer
```

Each supports standard Esri `exportImage` (bbox clip + resample, `f=image`) and `getSamples`/`identify`
point queries — no key, no login. Server-advertised limits (`verified_from`: the JSON metadata itself):
`maxImageWidth`/`maxImageHeight` = 100,000 px, `maxRecordCount` = 1000, `maxDownloadImageCount` = 20,
`capabilities: "Image,Metadata,Catalog,Mensuration"`. The standalone WHP 2023 service is at
`apps.fs.usda.gov/fsgisx01/rest/services/RDW_Wildfire/RMRS_WildfireHazardPotential_Continuous_2023/ImageServer`
(found via search; **UNVERIFIED** whether it has also migrated to IIPP — not tested directly this
session; test before relying on it, with the same 403-migration pattern in mind).

**Important caveat (verified by comparing two sources):** the IIPP ImageServer's self-reported
`pixelType` for the WRC WHP layer is `U16`, but the real downloadable `WHP_DC.tif` I opened is
`int32`. The IIPP `maxValues` for BP/RPS/cRPS (1352 / 1301 / 999) look like they might be the
documented true ranges (0.14 / 13.2 / 100) scaled by 10,000 / 100 / 10 respectively for integer
service storage — but I could not confirm the scale factor from documentation, and CFL's reported
max (475) does **not** cleanly reconcile with the documented 861.7 ft this way. **Treat any value
read through the ImageServer as UNVERIFIED until cross-checked against a downloaded GeoTIFF**; the
bulk-download GeoTIFFs are the authoritative representation.

---

## 3. CRS / resolution / coverage

| | WRC (30 m, 8 themes) | WHP standalone (270 m) |
|---|---|---|
| Native CRS | **EPSG:5070** (NAD83 / Conus Albers) | **EPSG:5070** (NAD83 / Conus Albers) |
| `verified_from` | Direct `rasterio` inspection of a real downloaded sample (`BP_DC.tif`, `CFL_DC.tif`, `CRPS_DC.tif`, `Exposure_DC.tif`, `FLEP4_DC.tif`, `FLEP8_DC.tif`, `RPS_DC.tif`, `WHP_DC.tif` — all 8 themes checked, all report `PROJCS["NAD83 / Conus Albers", ...]`). The official FGDC XML metadata for WRC has **no** `<spref>` element at all (confirmed: 0 matches for the tag across the full 64 KB file) — native CRS is simply undocumented in the official metadata and had to be verified empirically. | Direct `rasterio` inspection of `whp2023_cls_conus.tif` and `whp2023_cnt_conus.tif`, extracted from the downloaded `RDS-2015-0047-4_Data.zip`. The methods white paper separately confirms "Albers CONUS" qualitatively (LANDFIRE 2.2.0 input table, `verified_from` WRC methods PDF p.3 — applies to both products since both are LANDFIRE-based) but does not give an EPSG code. |
| Pixel size | 30.0 m × 30.0 m exactly (verified) | 270.0 m × 270.0 m exactly (verified) |
| Resolution basis | Upsampled from the native 270-m FSim burn-probability grid to match LANDFIRE's native 30-m fuel/vegetation grid (see §5 for the exact 6-step method); fire-intensity layers (CFL, FLEP4/8, cRPS, RPS, WHP) were modeled natively at 30 m via WildEST/FlamMap, not resampled. | Native 270 m — this is FSim's native simulation resolution, not resampled from something finer. |
| Dev-area sample confirmed | `BP/CFL/CRPS/Exposure/FLEP4/FLEP8/RPS/WHP_DC.tif`, 747×622 px, bounds `(1610775, 1913775)–(1629435, 1936185)` in EPSG:5070 metres | `whp2023_cnt_conus.tif`, 11283×17372 px, bounds `(-2362635, 221265)–(2327805, 3267675)` in EPSG:5070 metres (single seamless CONUS array, confirmed by direct read) |
| CONUS completeness | WRC: "wall-to-wall (all U.S. lands)" per `wildfirerisk.org/download/`; per-state zips are clipped to the **state polygon**, not merely the state's bounding box — confirmed empirically: the DC sample has 267,959 of 464,634 pixels (57.7%) set to the float32 nodata sentinel even though DC's small bounding box is itself nearly equal to DC's full extent, i.e. padding/edge pixels outside the actual DC polygon are nodata, not the whole state missing data. **Gaps**: none documented; AK is split into North/South zips for size reasons only. | CONUS, AK, HI each shipped as **separate, single, seamless national raster files** (not tiled/split). No documented gaps. |

Because both products are already in **EPSG:5070 at a resolution that evenly divides the project's
10 km × 10 km EPSG:5070 grid** (10,000 m / 30 m = 333.33; 10,000 m / 270 m = 37.04 — not perfectly
integer, but close enough that a standard zonal/area-weighted overlay needs no special handling),
**no reprojection is required** before zonal statistics — a significant simplification versus most
other candidate sources.

---

## 4. Fields / units / codes (data dictionary)

All value ranges below are the **documented CONUS range** (`verified_from`: the official file-index
HTML page, `_fileindex_RDS-2020-0016-2.html`, quoted directly) unless marked otherwise. dtype/nodata
are from my own `rasterio` inspection of the real, checksum-verified `DC` sample files (all 8 WRC
themes) and the real `whp2023_*_conus.tif` files (standalone WHP) — both sets of facts are
independently confirmed, not guessed.

### WRC themes (30 m, EPSG:5070), file pattern `<THEME>_<EXTENT>.tif`

| Theme | Meaning | Units | Documented range | dtype (verified) | nodata (verified) | Data vintage |
|---|---|---|---|---|---|---|
| `BP` | Burn Probability ("Wildfire Likelihood" in the web app) | annual probability, 0–1 | 0 to 0.14 | float32 | **-3.4028235e+38** (GDAL float32 sentinel) | circa 2021 ground conditions |
| `CFL` | Conditional Flame Length | feet | 0 to 861.7 | float32 | -3.4028235e+38 | fuels as of beginning of 2023 fire season (disturbances through 2022) |
| `FLEP4` | Flame-Length Exceedance Probability, 4 ft (limit of hand-crew/manual control) | probability, 0–1 | 0 to 1 | float32 | -3.4028235e+38 | same as CFL |
| `FLEP8` | Flame-Length Exceedance Probability, 8 ft (limit of mechanical control) | probability, 0–1 | 0 to 1 | float32 | -3.4028235e+38 | same as CFL |
| `Exposure` | Exposure Type: 1 = home directly exposed (burnable pixel); 0–1 = indirectly exposed, decaying with distance from burnable fuel out to ~1530 m; 0 = non-exposed | unitless index, 0–1 | 0 to 1 | float32 | -3.4028235e+38 | same as CFL |
| `cRPS` | Conditional Risk to Potential Structures ("Wildfire Consequence") — expected damage to a hypothetical structure *if* fire occurs there, independent of BP | index, 0–100 (0 = no damage, 100 = complete loss, by convention; stored as the negative −10..−100 response-function values made positive) | 0 to 100 | float32 | -3.4028235e+38 | same as CFL |
| `RPS` | Risk to Potential Structures ("Risk to Homes") = `cRPS × BP` | index (probability-weighted consequence) | 0 to 13.2 | float32 | -3.4028235e+38 | combines BP (circa 2021) and cRPS (2023) vintages |
| `WHP` (WRC-bundled, 30 m) | Wildfire Hazard Potential, integrated BP+FLP+ignition-density+resistance-to-control | unitless index | 0 to 99,853 | **int32** (file-level); **but the live ImageServer reports `U16`** — see caveat above, trust the file | **-128** (file-level, confirmed on the real downloaded sample — NOT the float sentinel used by the other 7 themes) | same as CFL |

Zero-vs-nodata, verified from the methods white paper (`verified_from`: WRC methods PDF pp. 5–7,
quoted/paraphrased):
- In the **national 270-m FSim input**, "all burnable pixels ... have valid non-zero values, and all
  non-burnable pixels have a value of zero" — zero is a real, meaningful value (non-burnable land),
  not missing data.
- The 270→30 m upsampling temporarily converts zero to nodata to let two 3×3 (270 m) moving-window
  means smooth the data, then explicitly resets remaining nodata back to zero, resamples (cubic
  convolution), and finally force-sets water/snow-ice pixels and any negative artifacts to zero
  (steps 5–6 of a documented 6-step process). A second "oozing" pass spreads BP up to **1,530 m**
  (three iterative 510-m circular moving-window means) into adjacent non-burnable (developed/bare/ag)
  land so simulated fire can realistically threaten the edges of towns; cRPS is oozed the same
  distance but without decay. CFL/FLEP4/FLEP8/WHP(30m) were **not** oozed into developed areas.
  ⇒ **In the delivered files, BP/cRPS = 0 is a genuine "not expected to burn here" value. The
  GeoTIFF nodata sentinel means "outside the clipped state/CONUS extent," a different concept.**
  This directly satisfies AGENTS.md §3's "keep source no-data distinct from genuine zero."
- `RPS = cRPS × BP` (exact formula, quoted from the methods PDF, p.9).
- `CFL = Σ(i=1..216) FlameLength_i × WeatherTypeProbability_i` — a probability-weighted mean of 216
  FlamMap runs spanning 9 wind-speed × 8 wind-direction × 3 moisture classes (exact formula, methods
  PDF p.7).
- cRPS response functions (methods PDF p.9, "complete" table, values = relative damage, 0 = none,
  -100 = total loss, by lifeform and flame-length-probability class FLP1(lowest)…FLP6(highest)):

  | Lifeform | FLP1 | FLP2 | FLP3 | FLP4 | FLP5 | FLP6 |
  |---|---|---|---|---|---|---|
  | Tree | -25 | -40 | -55 | -70 | -85 | -100 |
  | Shrub | -20 | -35 | -50 | -65 | -80 | -95 |
  | Grass | -10 | -25 | -40 | -55 | -70 | -85 |

### WHP standalone (270 m, EPSG:5070), files `whp2023_cls_conus.tif` / `whp2023_cnt_conus.tif` (+ AK/HI)

| Variant | Units | dtype (verified) | nodata (verified) | Value meaning |
|---|---|---|---|---|
| `whp2023_cnt_*` (continuous) | unitless index (×10,000, rounded) | **int32** (verified) | **2147483647** = INT32_MAX (verified) | Full CONUS documented range 0 to 120,650 (`verified_from`: web search of the ImageServer `computeStatistics`/`RMRS_WildfireHazardPotential_Continuous_2023` summary — a secondary source, not independently re-verified by me against the downloaded file's full-array statistics due to time/compute budget; my own sampled 2000×2000-px NW-corner window of the real downloaded file showed values 0–90,611, same order of magnitude, consistent but not a full-array check) |
| `whp2023_cls_*` (classified) | categorical | **uint8** (verified) | **255** (verified) | 1=Very Low, 2=Low, 3=Moderate, 4=High, 5=Very High, 6=Non-burnable (LANDFIRE FBFM40 codes 91/93/99), 7=Water (FBFM40 code 98). Verified by reading actual pixel values from the downloaded CONUS file: class pixel counts are {1: 32,721,418; 2: 19,304,184; 3: 15,442,036; 4: 9,854,998; 5: 3,608,841; 6: 23,880,691; 7: 6,005,049}. |

Standard class-break percentiles (quoted from the official file-index page): WHP classes at the
44th/67th/84th/95th percentile of the continuous value; RPS (web-app "Risk to Homes") displayed at
40th/70th/90th/95th percentile. The exact CONUS- and per-state percentile lookup tables (0–100th,
1% steps, for RPS/cRPS/WHP) are in the downloaded `WRC_V2_DataPercentiles.xlsx`
(`data/raw/usfs_wildfire_risk/wrc/RDS-2020-0016-2_Supplements.zip`) — opened and confirmed to parse
with `pandas`/`openpyxl` (3 sheets × 101 rows × 53 columns). AGENTS.md forbids Phase 2 from making
screening decisions, so these are offered only as a documented, non-arbitrary threshold source for
*future* model-layer use, not for anything Phase 2 itself should act on.

**Discrepancy to flag, not silently resolve:** the 30-m WRC-bundled `WHP` and the 270-m standalone
WHP are built from the same general methodology (Dillon et al. 2015) but **different input
vintages** — WRC's 30-m WHP uses fuels updated through 2022 and the native 30-m WildEST intensity
results; the standalone 270-m WHP (2023/4th-ed.) uses LANDFIRE 2.2.0 with FSim run on "ground
conditions as of the end of 2020". They are **not interchangeable** and should not be averaged or
substituted for one another; Phase 2 should keep them as two distinct `source_field`s if both are
used.

---

## 5. License / terms of use

Both publications carry the **identical** rights statement (quoted, catalog pages for
`RDS-2020-0016-2` and `RDS-2015-0047-4`, both fetched this session, HTTP 200): data "were collected
using funding from the U.S. Government and can be used without additional permissions or fees,"
citation requested when used in a publication/presentation. Both also carry a standard no-warranty
disclaimer: no warranty as to accuracy, reliability, or completeness for individual or aggregate use
or for purposes not intended by the originator. This is consistent with U.S. federal government work
(17 U.S.C. §105, not separately re-verified by me this session but standard for Forest Service RDA
products) — i.e., effectively public domain in the U.S., cite-but-no-permission-needed.

---

## 6. Access requirements

- **No login, no API key, no click-through terms, no CAPTCHA observed anywhere in this source** — every
  URL in §2 returned data directly to an unauthenticated `curl` request with a descriptive
  User-Agent. The one 403 encountered (`apps.fs.usda.gov` ImageServer) was a **documented service
  migration notice with an explicit replacement URL**, not a bot-block; I followed the stated new
  endpoint rather than attempting to defeat anything, consistent with AGENTS.md §4 ("never bypass
  access controls ... no browser-UA impersonation to defeat a block").
- Box.com-hosted state zips redirect (HTTP 301) to a signed, time-limited `public.boxcloud.com`
  URL — this is normal box.com behavior, not an access restriction; `curl -L` follows it
  transparently and no credentials are involved.
- **Status: READY**, not PARTIAL/BLOCKED — the only limitation is the pre-download size budget, not
  access control.

---

## 7. Recommended aggregation (10 km × 10 km, EPSG:5070 — zonal statistics, no screening)

1. **Mosaic before zonal stats.** For WRC, either (a) use the single CONUS-wide per-theme zip for
   each of BP/CFL/WHP, or (b) merge/mosaic the downloaded state GeoTIFFs for all states a dev/run
   area touches (TX+LA+AR here) into one virtual raster (e.g. `rasterio` `WarpedVRT`/`merge`, or a
   GDAL VRT) *before* computing zonal stats. Do **not** compute a cell's statistic from only one
   state's file: per-state files are clipped to the **state polygon** (confirmed empirically, §3),
   so a 10 km cell straddling e.g. the TX/LA line would silently lose the TX-side pixels if only the
   Louisiana file were consulted. Because the underlying raster is one seamless national surface
   (confirmed by directly opening the WHP CONUS files — single array, no internal tiling seams),
   this is a **distribution-packaging artifact**, not a genuine multi-source-region case; AGENTS.md's
   "record when a cell intersects multiple source regions" is more about datasets whose underlying
   methodology differs by region, which does not apply here as long as the mosaic is done correctly.
   Still, record `source_region_count` per cell (states touched) as useful provenance even though
   values don't change at the seam.
2. **Zonal statistics per cell, per theme:** windowed/blocked reads (`rasterio.mask` or
   `rasterstats.zonal_stats` with the cell polygon, `all_touched=False`, area-weighted if a pixel
   straddles the cell boundary) computing, as **features only** (AGENTS.md: no PASS/FAIL, no
   ranking):
   - `mean` (area-weighted average of valid — non-nodata — pixels),
   - `p90` (90th percentile; matches the web app's own RPS display convention),
   - `frac_above_<class_or_percentile>` — e.g. fraction of a cell's *valid* (non-nodata) area with
     WHP class ≥ High, or BP above the CONUS 90th/95th percentile from the official percentile
     table — stored as a plain metric, never as a pass/fail flag.
   - `coverage_fraction` = (valid pixel count)/(total pixel count) per cell, so a cell that is mostly
     nodata (e.g., outside the state-clip extent, or — for coastal/Gulf cells in this dev area —
     mostly open water) is visibly partial rather than silently treated as zero risk.
3. **BP=0 vs nodata.** Because BP/cRPS legitimately use 0 for "non-burnable, not oozed into," do
   **not** treat 0 as missing. Only the float32 sentinel (`-3.4028235e+38`) or int32 sentinel
   (`-128` for WRC's WHP, `2147483647` for standalone WHP, `255` for standalone WHP classified) is
   "missing" (`status: unknown`, `missing_reason: outside clipped source extent`).
4. **Which product to use for which WHP feature:** use the WRC-bundled 30-m `WHP` theme if the
   project wants WHP at the same native resolution/vintage as BP/CFL (simpler single-source
   consistency); use the standalone 270-m WHP (classified *and* continuous) if the project wants the
   Forest Service's officially citable national fuel-treatment-prioritization product. Record which
   was used in `source_field`/`native_spatial_resolution`; do not blend them into one value.
5. **Fraction-above-threshold features only** (per the task's explicit instruction): e.g.
   `whp_frac_class_ge_high`, `bp_frac_above_p90_national` — computed, recorded, never used by the
   geography layer to exclude or pass a cell.

---

## 8. Volume & memory estimates

All "verified" rows are either a quoted file size or a directly-measured array shape; all
"calculated" rows are my own arithmetic from those verified numbers, explicitly marked.

| Scope | Product | Size | Basis |
|---|---|---|---|
| Dev area (TX+LA+AR), bulk download | WRC, 3 themes needed (BP/CFL/WHP) only available bundled with all 8 | 23.11 GB compressed (whole-state zips, all themes) | verified (catalog sizes) |
| Dev area (TX+LA+AR), bulk download | WRC, all 8 themes | same 23.11 GB (themes aren't separable in the state-zip packaging) | verified |
| National (CONUS), bulk download | WRC, BP+CFL+WHP only | 32.3 + 29.1 + 8.17 = **69.57 GB** compressed | verified (summed from catalog) |
| National (CONUS), bulk download | WRC, all 8 themes | **175.8 GB** compressed | verified (summed from catalog) |
| National (CONUS), bulk download | WHP standalone (cls+cnt, CONUS only, excl. AK/HI/gdb) | 23.1 MB + 143.4 MB ≈ **167 MB** | verified (zip-listing sizes) |
| Already on disk | WHP (Data+Supplements+Fileindex) | **396 MB** | verified (downloaded, sha256-checked) |
| Dev bbox, in-memory, uncompressed, 1 float32 WRC layer | — | ≈ 2.36×10⁸ px × 4 B ≈ **944 MB** | calculated: dev bbox ≈ 478 km × 444 km at 30 m |
| Dev bbox, in-memory, 3 layers (BP+CFL+WHP) | — | ≈ **2.8 GB** | calculated |
| National, in-memory, 1 float32 WRC layer, whole array | — | ≈ 8.98×10⁹ px × 4 B ≈ **35.9 GB** | calculated (CONUS ≈ 8.08M km² / 0.0009 km² per 30-m px) — **must** use windowed/blocked reads, matches AGENTS.md §7's "never load a national 30 m raster into memory at once" |
| National, in-memory, WHP continuous, whole array | — | 11,283×17,372 px × 4 B ≈ **784 MB** | calculated from the verified real array shape — small enough to load whole within the 4 GB/process budget, windowing still recommended for consistency |
| Dev area grid cells (10 km) | — | ≈48×44 ≈ **2,100 cells** (bounding rectangle; fewer after land/CONUS clipping) | calculated from dev bbox |
| National grid cells (10 km) | — | ≈ **80,800 cells** | calculated, CONUS area / 100 km² |

Recommendation: for development, prefer the ImageServer `exportImage` clipped to the exact dev bbox
(within the server's advertised 100,000×100,000 px limit, so a single native-resolution export of
the whole dev bbox is technically possible) instead of downloading whole-state zips that are mostly
outside the bbox (e.g. Texas's zip is 18 GB but the dev bbox only touches eastern Texas; Arkansas's
2.71 GB zip is touched by only a sliver near Texarkana). This was not exercised this session (kept
within the "optional pre-download" scope, and the ImageServer value-scaling caveat in §2 needs
resolving first) — flagged as an open question below.

---

## 9. Interpretation limits (quoted/paraphrased from the official methods documentation)

- Modeled, relative-likelihood products, not a forecast: WHP "is not a forecast or outlook for any
  particular fire season" (no current/forecast weather or fuel moisture).
- "Quantitative accuracy cannot be evaluated" for WHP; FSim outputs were calibrated against
  historical fire-occurrence statistics within 136 "pyromes" (contemporary-fire-activity regions),
  not validated pixel-by-pixel.
- RPS/cRPS assume **uniform structure susceptibility** (same response function for every building
  regardless of construction/defensible space) — explicitly called out in the methods PDF as a
  simplification; local Home Ignition Zone conditions are out of scope.
- The developed-area "oozing" is a deliberate GIS approximation of ember-driven urban conflagration
  risk, capped at 1,530 m, chosen as "a balance" rather than derived from a fire-spread simulation
  into structures (models for that don't yet exist per the authors).
- BP/intensity layers are circa-2020/2021/2022/2023 ground conditions; they do **not** reflect any
  fire disturbance, build-out, or fuel treatment after those dates (and will get stale over the life
  of a project without a re-download/re-check against the catalog page).
- WHP "on its own is not an explicit map of wildfire threat or risk" — it needs pairing with assets
  data to approximate risk (which is exactly what RPS/cRPS already do).

## 10. Pitfalls

- **Zero ≠ nodata, but the two products use different nodata sentinels** per dtype (float32
  `-3.4028235e+38` for 7 of 8 WRC themes; int32 `-128` for WRC's own WHP theme; int32
  `2147483647` / uint8 `255` for the two standalone WHP variants). A naive adapter that assumes one
  nodata convention across all 8+ files will silently corrupt results.
- **Per-state WRC zips are polygon-clipped, not bbox-clipped** — majority-nodata-looking small
  states (like the DC check, 57.7% nodata) are normal, not a download error; but a cell straddling a
  state line needs both states' files mosaicked (§7.1).
- **Two unrelated WHP products with the same acronym and similar methodology, different resolution
  and vintage** (30 m WRC-bundled vs 270 m standalone) — do not merge or average them (§4).
- **ImageServer-reported value ranges/pixel types do not match the downloadable GeoTIFFs** for at
  least WHP's pixel type and possibly BP/RPS/cRPS's scale factor (§2 caveat) — verify against the
  actual downloaded file, don't trust the live service's self-reported stats blindly.
- **The old `apps.fs.usda.gov/fsgisx01` ImageServer host is deprecated** (403, migrated to
  `imagery.geoplatform.gov/iipp`) — don't hardcode the old host; re-check the `imagery.geoplatform.gov`
  path still resolves before Phase 2 ships, since federal GIS hosting migrations like this can
  recur.
- **`fs.usda.gov/rds/archive` catalog/search pages are slow** (~35 s observed, consistent with the
  task's warning) — budget generous timeouts/retries; the static product-file and REST endpoints
  were fast by contrast, so slowness is isolated to the search/catalog UI, not the actual data
  transfer.
- **RPS/cRPS/WHP are indices, not physical units** — do not present them to users as probabilities or
  percentages without the documented scale; only BP, FLEP4, FLEP8, and Exposure are true 0–1
  probabilities/fractions.
- Texas's state zip (18 GB) is disproportionate to how little of Texas the dev bbox actually covers
  — a reminder that "prefer national files when they are the only option" (task wording) doesn't
  automatically mean "download the state file," when a clipped REST export could be far smaller for
  development-scale work.

## 11. Open questions

- Whether `imagery.geoplatform.gov/iipp/.../USFS_EDW_RMRS_WRC_*` `exportImage` actually returns
  true (unscaled) float32/int32 values matching the downloadable GeoTIFFs, or integer-scaled values
  — needs a direct `exportImage` pull + comparison against a known pixel from a downloaded file
  before Phase 2 relies on the REST path for anything beyond quick-look/dev convenience.
  **UNVERIFIED** this session (time-boxed in favor of verifying the bulk-download path, which is
  the documented primary distribution channel).
- Whether the standalone WHP 2023 ImageServer (`RMRS_WildfireHazardPotential_Continuous_2023` /
  `_Classified_2023`) has also migrated off `apps.fs.usda.gov` to IIPP — not tested this session
  (only the WRC-folder services were checked after the migration notice).
- The true full-CONUS max/mean for `whp2023_cnt_conus.tif` was taken from a secondary (search-engine
  summarized) source citing the ImageServer's `computeStatistics`; I independently confirmed CRS,
  resolution, dtype, nodata, and a representative 2000×2000-px sample window directly from the
  downloaded file, but did not run a full-array `min/max` over the complete 11,283×17,372 array in
  this session (compute-time tradeoff) — worth a quick `rasterio`/`gdalinfo -stats` pass when the
  adapter is actually built, since the file is already on disk.
- Whether a Phase-2 "national" run should bulk-download all 8 WRC CONUS-theme zips (175.8 GB) or
  only the 3 requested themes (69.57 GB) or assemble national coverage from 51 state zips instead —
  left as a Phase-2 design decision; this report provides verified sizes for all options.
- `RDS-2020-0060-2` (WRC "Populated Areas" companion: housing-unit density/exposure/risk) and
  `RDS-2024-0030` (Community Wildfire Risk Reduction Zones) are related USDA products surfaced
  during this research but were **not** part of the assigned feature list (burn probability,
  conditional flame length, WHP classes) and were not investigated further — flagged in case a
  future phase wants population-weighted wildfire exposure.

---

## Appendix: verification method notes

- Native CRS/resolution/dtype/nodata for WRC: downloaded the smallest available real sample
  (District of Columbia, `RDS-2020-0016-2_DistrictOfColumbia.zip`, 1.02 MB, sha256 matched the
  catalog-listed value exactly), unzipped, and opened **all 8** of its GeoTIFFs with `rasterio`
  1.5.2 (the exact version pinned in this project's `requirements.lock.txt`). This file was a
  verification aid only — it is outside the TX/LA/AR dev area, so it was **not** kept under
  `data/raw/usfs_wildfire_risk/` and was deleted from the scratch location after inspection.
- Native CRS/resolution/dtype/nodata for standalone WHP: extracted `whp2023_cls_conus.tif` and
  `whp2023_cnt_conus.tif` directly from the pre-downloaded, sha256-verified
  `RDS-2015-0047-4_Data.zip` (the real file now sitting in `data/raw/usfs_wildfire_risk/whp/`) and
  opened both with `rasterio`.
- Percentile-table structure verified by loading `WRC_V2_DataPercentiles.xlsx` (from the
  pre-downloaded WRC Supplements zip) with `pandas`/`openpyxl`.
- Methodology/formulas verified by reading the actual pages of
  `WRC_V2_Methods_Landscape-wideRisk.pdf` (from the same Supplements zip) — page images read
  directly, not summarized by a third party.
- All HTTP status/size claims in §2 came from `curl -sI` / `curl -r 0-1023` / full `GET` with
  `-w '%{http_code} %{size_download}'`, run in this session, not from search-result text.
