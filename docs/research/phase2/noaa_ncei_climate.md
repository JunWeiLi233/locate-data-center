# noaa_ncei_climate — NOAA NCEI U.S. Climate Normals 1991-2020 (Gridded)

Phase 2 data-source reconnaissance report. Prepared 2026-10-02. Status recommendation: **READY**.

Scope reminder (per `AGENTS.md` §1/§3): this report documents source values only. It does not rank,
score, or threshold anything. "Cooling-related conditions" below are observed/calculated physical
quantities, not a suitability judgement.

## 1. Product / version

NOAA National Centers for Environmental Information (NCEI) publishes the **U.S. Climate Normals**
every decade per WMO convention. The 1991-2020 edition ("2020 Normals") has multiple sibling products;
this project should use the **Gridded Normals**, not the ~15,000-station tabular product, as the task
specifies.

| Product | Version | NCEI Accession | DOI | Native format |
|---|---|---|---|---|
| **Monthly/Seasonal/Annual Gridded Normals** (tavg, tmax, tmin, prcp) | v1.0, released 2022-04-05 (doc dated 2022-02-24) | 0245564 | `10.25921/yya9-9769` | netCDF-4, CF-1.6 |
| **Daily Gridded Normals** (tavg, tmax, tmin, prcp, month-to-date & year-to-date prcp) | v1.0, released 2022-09-22 | 0259962 | `10.25921/4z0k-n484` | netCDF-4, CF-1.6 |
| Cloud-Optimized GeoTIFF derivative of both of the above | n/a (continuously mirrored) | n/a | n/a | COG (GeoTIFF) |
| (Reference only, NOT recommended) Station-based Monthly/Annual/Seasonal/Daily/Hourly Normals | 2020 Normals | C01619–C01622 (various) | `10.25921/wck8-er13` (monthly) and others | CSV |

Both gridded products are derived from **nClimGrid** (Vose et al. 2014) via climatologically-aided
spline interpolation of station data — i.e., already a spatially continuous field, not raw station
points. Three period baselines exist side by side: **1991-2020** (the conventional 30-yr normal to
use), 2006-2020 (15-yr), and 1901-2000 (100-yr baseline). This report and the pre-download only cover
**1991-2020**.

`verified_from`: `Documentation_Monthly_Gridded_Normals.pdf`, `Readme_Monthly_Gridded_Normals.pdf`,
`Documentation_Daily_Gridded_Normals V1.0.pdf` (all fetched and read directly, see §2), and the DOI
redirect chains in §2.

## 2. Endpoints (verified)

All URLs below were checked in this session with `curl -sI` / `curl -r 0-1023` / a full GET, or fetched
and read. Status codes are exactly what this session observed.

### 2a. Recommended operational path — NODD / Microsoft Planetary Computer COG mirror (fully verified end to end)

NOAA disseminates the gridded normals as Cloud-Optimized GeoTIFFs through its **Open Data
Dissemination (NODD)** program; Microsoft Planetary Computer hosts the STAC catalog and the blobs
(account `noaanormals`, container `gridded-normals-cogs`, Azure Blob Storage). This is the **same NOAA
data**, just repackaged per-variable/per-time-step as small GeoTIFFs instead of a few large netCDFs.

- STAC collection: `https://planetarycomputer.microsoft.com/api/stac/v1/collections/noaa-climate-normals-gridded` — **HTTP 200**
- STAC item search (POST): `https://planetarycomputer.microsoft.com/api/stac/v1/search` — **HTTP 200**, confirmed filterable by `noaa_climate_normals:period` (`1991-2020`/`2006-2020`/`1901-2000`) and `noaa_climate_normals:frequency` (`annual`/`seasonal`/`monthly`/`daily`) and `noaa_climate_normals:time_index`.
- Anonymous SAS token endpoint (no login/API key/account): `https://planetarycomputer.microsoft.com/api/sas/v1/token/noaanormals/gridded-normals-cogs` — **HTTP 200** (returns `{"token": "...", "msft:expiry": "..."}`; intermittently returned `504 upstream request timeout` on first try in this session, always succeeded within 2 retries). Token is container-scoped (works for any blob path in the container) and valid ~24–25 h.
- Blob pattern (requires `?<token>` query string from the line above):
  `https://noaanormals.blob.core.windows.net/gridded-normals-cogs/normals-{annual|seasonal|monthly|daily}/{period}/{period}-{freq}[-{month_or_doy}]-{var}_{stat}.tif`
  e.g. `.../normals-annual/1991-2020/1991_2020-annual-tavg_norm.tif`, `.../normals-daily/1991-2020/1991_2020-daily-182-tavg_norm.tif`.
  **375 individual files of exactly this pattern were HEAD/GET-verified with HTTP 200 and downloaded in this session** (see §2c and the pre-download manifest).
- Without a valid token, the identical blob URL returns **HTTP 404 "The specified blob does not exist"** (verified) — this is Azure's standard behavior for unauthorized access to a private container, not evidence the file is actually missing. Don't mistake it for a broken filename.

Minimal recipe:
```bash
TOKEN=$(curl -s "https://planetarycomputer.microsoft.com/api/sas/v1/token/noaanormals/gridded-normals-cogs" | python -c "import json,sys;print(json.load(sys.stdin)['token'])")
curl -o out.tif "https://noaanormals.blob.core.windows.net/gridded-normals-cogs/normals-annual/1991-2020/1991_2020-annual-tavg_norm.tif?${TOKEN}"
```

### 2b. Canonical official source — NCEI netCDF (names verified; bulk URL NOT independently obtained)

- Product landing page: `https://www.ncei.noaa.gov/products/land-based-station/us-climate-normals` — **HTTP 200**.
- Monthly/Annual/Seasonal doc: `https://www.ncei.noaa.gov/sites/default/files/2022-04/Documentation_Monthly_Gridded_Normals.pdf` — **HTTP 200**, `Content-Length: 909706`.
- Monthly/Annual/Seasonal readme (has the full `ncdump -h` structure dump): `https://www.ncei.noaa.gov/sites/default/files/2022-04/Readme_Monthly_Gridded_Normals.pdf` — **HTTP 200**, `Content-Length: 147526`.
- Daily doc: `https://www.ncei.noaa.gov/sites/default/files/2022-09/Documentation_Daily_Gridded_Normals%20V1.0.pdf` — **HTTP 200**, `Content-Length: 877676`.
- DOI `https://doi.org/10.25921/yya9-9769` → **302** → `https://www.ncei.noaa.gov/archive/accession/0245564` → **301** → ISO metadata landing page (`id=gov.noaa.nodc:0245564`) → **200**.
- DOI `https://doi.org/10.25921/4z0k-n484` → **302** → `https://www.ncei.noaa.gov/archive/accession/0259962` → **301** → ISO landing page (`id=gov.noaa.nodc:0259962`) → **200**.
- Exact netCDF filenames (confirmed from the documentation text, not guessed): `tavg-1991_2020-monthly-normals-v1.0.nc`, `tmax-...`, `tmin-...`, `prcp-1991_2020-monthly-normals-v1.0.nc` (~275 MB each per NOAA's own stated figure, one file = all of monthly+seasonal+annual for that variable); `tavg-1991_2020-daily-normals-v1.0.nc` etc. (~1.2 GB each, 365/366 days).
- **Not resolved automatically**: `https://www.ncei.noaa.gov/archive/accession/download/245564` returns `301`→`302`→`302`→... through `https://www.ncei.noaa.gov/archive/archive-management-system/OAS/bin/prd/jquery/accession/download/245564` setting a cookie `OAS_prd_client=restricted`, and this session's automated client never reached a final file listing (observed up to several redirect hops, each re-issuing a new `302` to the same relative path). **No login prompt, password field, CAPTCHA, or terms click-through was ever shown** — this looks like an interactive-browser-oriented session/cookie flow rather than a true access control, but it could not be completed here. FTP alternative stated on the metadata page, `ftp://ftp-oceans.ncei.noaa.gov/nodc/archive/arc0196/0245564/`, accepted a connection (exit 0) but its directory contents were not enumerated in this session.
- **Recommendation**: use §2a (verified, working) for the adapter; a human can likely get the native netCDF directly from a real browser at the DOI links above if the project specifically wants the netCDF instead of COG.

### 2c. Optional enrichment — station-based Normals (CSV, fully verified, for cross-checking only)

- Annual/Seasonal directory: `https://www.ncei.noaa.gov/data/normals-annualseasonal/1991-2020/` — **HTTP 200** (subfolders `access/`, `archive/`, `doc/`).
- Annual/Seasonal per-station files, e.g. `https://www.ncei.noaa.gov/data/normals-annualseasonal/1991-2020/access/AQC00914000.csv` — **HTTP 200**, `Content-Length: 19081`.
- Annual/Seasonal documentation: `.../1991-2020/doc/Normals_ANN_Documentation_1991-2020.pdf` — **HTTP 200**, 167,246 bytes (fetched and read in full).
- Annual/Seasonal sample CSV (header read directly): `.../1991-2020/doc/Normals_ANN_1991-2020_sample.csv` — **HTTP 200**, `Content-Length: 14756`.
- Hourly directory/doc/sample: `https://www.ncei.noaa.gov/data/normals-hourly/1991-2020/doc/` — **HTTP 200**; `Normals_HLY_Documentation_1991-2020.pdf` (166,048 bytes) and `Normals_HLY_1991-2020_sample.csv` (52,356 bytes) both fetched and read directly.
- AWS mirror of the **station** product (not gridded): bucket `noaa-normals-pds` (`https://noaa-normals-pds.s3.amazonaws.com`), prefixes `normals-annualseasonal/`, `normals-daily/`, `normals-hourly/`, `normals-monthly/` confirmed via a public `?list-type=2` S3 listing call (valid `ListBucketResult` XML returned, no `gridded` prefix exists in this bucket).

## 3. CRS / resolution / coverage

- **Native grid**: 1/24° × 1/24° (0.041666 67°) latitude/longitude, which NOAA's own documentation
  states is "approximately 5 km" (Monthly doc) and, more precisely, "4.63 km" (Readme ncdump comment:
  `lon:comment = "resolution is 1/24 degree, equivalent to 4.63 km"`).
- **Shape**: 596 rows × 1385 columns. `verified_from`: both the Readme's `ncdump -h` text (`lon=1385`,
  `lat=596`) and this session's own inspection of downloaded COG files (`numpy`/`PIL`: shape
  `(596, 1385)`, `dtype float32`).
- **Native CRS — netCDF**: plain geographic lat/lon in degrees; the ncdump global attributes shown in
  the Readme do **not** state an explicit horizontal datum name (no CRS/datum/EPSG attribute present in
  the excerpt read). Given the US station network underlying nClimGrid, NAD83 is the conventional
  assumption for NOAA CONUS products, but this is **UNVERIFIED** for this specific file — no attribute
  says so.
- **Native CRS — COG derivative**: **explicitly EPSG:4326 / WGS84**, verified directly from the
  downloaded GeoTIFF's own tags in this session (GeoKeyDirectory key 2048 = 4326; `GeoAsciiParamsTag`
  = `"WGS 84|"`). Pixel origin/transform verified from the same files: origin
  `(-124.70833333, 49.37500127)`, pixel size `(0.04166667, -0.04166667)`.
- **Coverage**: CONUS only (48 states + DC; confirmed bounding rectangle lon
  `[-124.708, -67.000]`, lat `[24.542, 49.375]` — matches both the netCDF global attributes
  (`geospatial_lat_min/max`, `geospatial_lon_min/max`) and the COG STAC collection extent). The
  project's dev bbox `[-98.0, 29.0, -93.0, 33.0]` is well inside this coverage.
  Does **not** cover Alaska, Hawaii, Puerto Rico, or other territories (gridded product only; the
  **station**-based normals do cover territories and are broader).
- **NoData fraction**: directly measured in this session on the downloaded annual `tmax_max` COG:
  **355,702 of 825,460 pixels (43.1%) are NoData** within the rectangular array. This is expected and
  not a defect — the array is a rectangle bounding a non-rectangular CONUS landmass, so ocean, Great
  Lakes, and the rectangle's corners are legitimately outside the data domain. The same ~43.1% NoData
  fraction was confirmed on three different daily files (days 1, 100, 366), consistent with a fixed
  land/water mask reused every day. **Interior (non-coastal) gaps within CONUS land were not
  specifically tested** — see Open Questions.

## 4. Fields / units / codes

### 4a. Gridded product (recommended primary source) — no CDD/HDD field exists here

| Field (netCDF name / COG asset key) | Description | Units | Fill/no-data | `verified_from` |
|---|---|---|---|---|
| `anntavg_norm` / `tavg_norm` (annual item) | Annual mean temperature normal | °C | `-9999.0` (netCDF `_FillValue`) / `NaN` (COG, GDAL tag 42113) | Readme ncdump dump; COG tag read directly in this session |
| `anntmax_norm` / `tmax_norm` (annual item) | Annual mean-of-monthly maximum-temperature normal | °C | same | same |
| `anntmin_norm` / `tmin_norm` (annual item) | Annual mean-of-monthly minimum-temperature normal | °C | same | same |
| `annprcp_norm` / `prcp_norm` (annual item) | Annual total precipitation normal | mm | same | Daily Gridded Normals doc explicit statement ("data is stored in metric units of °C and mm"); unit attribute for the monthly/annual prcp file itself was not individually re-opened, inferred from NOAA's stated parallel file structure — **high confidence, not independently re-verified per-file** |
| `mlytmax_norm` (12, one per month) / `tmax_norm` (monthly items, `time_index`=1–12) | Monthly mean-of-daily-maximum-temperature normal | °C | same | same |
| `anntmax_max` / `tmax_max` (annual item) | **= max over the 12 `mlytmax_norm` values**, i.e. the mean daily max of the warmest calendar month | °C | same | Readme ncdump pattern (`anntavg_max` long_name = "Maximum values of monthly mean temperature normals") **plus an empirical check performed in this session**: downloaded the annual `tmax_max` COG and all 12 monthly `tmax_norm` COGs and confirmed `tmax_max[row,col] == max(tmax_norm[month,row,col] for month in 1..12)` exactly at 3 independent pixels (TX/LA dev-bbox center, Houston, Minneapolis) |
| `*_flag` (e.g. `anntavg_flag`) | Count of months/years of valid input behind the normal (0–30) | count | n/a (itself the QA signal) | Readme ncdump dump |
| `*_std`, `*_min`, `*_max` (non-annual aggregates) | Interannual/intermonth standard deviation and extremes of the *inputs* feeding a normal | °C (or mm) | same | Readme ncdump dump (not independently re-verified for every combination) |
| `tavg_norm` (**daily** items, `time_index`=1–366, zero-padded `001`–`366` in COG filenames) | Daily mean-temperature normal, smoothed day-to-day, constrained to match the monthly normals | °C | same | Daily Gridded Normals Documentation PDF (read in full) + this session's own file inspection |

**There is no cooling-degree-day, heating-degree-day, or growing-degree-day field anywhere in the
gridded product**, at any frequency. This was checked exhaustively against the full "Primary Variables"
list in both documentation PDFs and against the full COG asset-key list returned by the STAC API — confirmed absent both times.

### 4b. Deriving the four requested features

| Requested feature | Recommended source field(s) | Value status |
|---|---|---|
| Annual mean temperature | `annual tavg_norm` | `observed` |
| Mean daily max of warmest month | `annual tmax_max` (1 file; do **not** need to fetch and max over 12 monthly files, see §4a) | `observed` |
| Annual precipitation | `annual prcp_norm` | `observed` |
| Cooling degree days, base 65 °F / 18.3 °C | **Not published gridded.** Calculate per native pixel: convert each of the 366 `daily tavg_norm` values to °F, `CDD65 = Σ max(0, T_F − 65)` over all days, **then** spatially aggregate the resulting per-pixel annual CDD65 raster to 10 km cells (see §7). Heating degree days (`HDD65 = Σ max(0, 65 − T_F)`) are symmetric. | `calculated` (documented formula over `observed` daily normals) |

### 4c. Station-based Normals (optional enrichment / cross-check only, per the task)

Verified directly from `Normals_ANN_Documentation_1991-2020.pdf` and the matching sample CSV header
(`Normals_ANN_1991-2020_sample.csv`):

- `ANN-CLDD-NORMAL` = "Long-term averages of annual cooling degree days **with base 65F**"; sibling
  fields `ANN-CLDD-BASE40/45/50/55/57/60/70/72` give alternate bases. `ANN-HTDD-NORMAL` = heating degree
  days base 65°F (same alternate-base siblings). `ANN-GRDD-*` = growing degree days (agricultural,
  multiple bases + two capped/truncated variants `TB4886`/`TB5086`). Units: °F-days (bases are stated
  in °F; NOAA's public CSV normals are customary units throughout, unlike the metric gridded netCDF).
  Seasonal equivalents exist with `MAM-`/`JJA-`/`SON-`/`DJF-` prefixes.
- **Missing value**: literal `-9999` in the CSV ("missing or insufficient data"). **Measurement flags**:
  `M`=Missing, `V`="too cold to compute", `W`=not used, `X`=rounded to zero, `Y`=insufficient values,
  `Z`=logical inconsistency. **Completeness flags**: `S`=Standard (≥24/30 yr), `R`=Representative
  (≥10 yr, gap-filled from neighbors), `P`=Provisional (≥10 yr, no reliable neighbors),
  `E`=Estimated (≥2 yr, statistically estimated), blank = special missing value shown elsewhere in
  the row.
- Station coverage: "more than 15,000 locations" report precipitation normals, "more than 7,300" report
  temperature normals (verified quote from the doc), predominantly NWS/FAA/COOP/SNOTEL/CoCoRaHS
  stations — this is the "station interpolation" approach the task says to prefer the gridded product
  over; use only to spot-check the gridded-derived CDD65 at a handful of stations inside the dev bbox.
- **Hourly Normals** (checked specifically per the task's question): verified directly from
  `Normals_HLY_1991-2020_sample.csv`'s header and `Normals_HLY_Documentation_1991-2020.pdf`. Elements
  present: `HLY-TEMP-NORMAL/10PCTL/90PCTL`, `HLY-DEWP-NORMAL/10PCTL/90PCTL` (**dew point, confirmed
  present**), `HLY-HIDX-NORMAL` (heat index), `HLY-WCHL-NORMAL` (wind chill), `HLY-PRES-*` (sea-level
  pressure), `HLY-CLOD-*` (cloud-cover percentages), `HLY-WIND-*` (direction/speed), and
  `HLY-CLDH-NORMAL` / `HLY-HTDH-NORMAL` — **cooling/heating *degree-hours*, base 65 °F, verified by
  direct quote**: "Cooling degree hour normals were computed by subtracting 65 from each valid
  temperature... Positive differences were summed and divided by the number of valid values" — this is
  a mean **hourly** degree-hour value, not an accumulated daily/annual total; don't confuse it with the
  annual CLDD-NORMAL (degree-*days*, a true annual accumulation). **Wet-bulb temperature is NOT present**
  in this product (confirmed by reading the complete column header of the official sample CSV — no
  `WETB`/wet-bulb field of any kind). Wet-bulb temperature does appear in a different, related NOAA
  product, Local Climatological Data (LCD), which is not part of the Climate Normals suite.

## 5. License

Verified directly from the native netCDF's own global attribute, as shown in NOAA's
`Readme_Monthly_Gridded_Normals.pdf` `ncdump -h` listing: **`:license = "no restrictitons"`** (verbatim,
including NOAA's own typo). This is consistent with NOAA data generally being a U.S. Government work
with no copyright restriction domestically. NOAA's Open Data Dissemination (NODD) program, through
which the COG mirror is served, requests (but does not legally require) attribution — see
`https://www.noaa.gov/information-technology/open-data-dissemination`.

**Caveat found in this session**: the Microsoft Planetary Computer STAC **collection** record for
`noaa-climate-normals-gridded` itself carries `"license": "proprietary"` as a literal field value. This
reads as a cataloging default/placeholder rather than an actual restriction — it directly contradicts
NOAA's own file-level statement and the fact that this is openly disseminated U.S. government data — but
it was not independently resolved with NOAA or Microsoft in this session. Flagging per `AGENTS.md` §4
("any additional source must be justified... never silently substitute"): if a strict license-compliance
reading is required, treat NOAA's own "no restrictions" statement as authoritative for the *data*, and
treat the COG repackaging as a redistribution under NODD's open-data policy.

## 6. Access requirements

**No login, account, API key, form, terms click-through, CAPTCHA, or bot-challenge was encountered
anywhere in this source.** Specifically:
- COG path (§2a): requires one HTTP GET to a public, anonymous, keyless token-issuance endpoint before
  each file download. Tokens are short-lived (~24–25 h) and must be re-requested, not hardcoded.
- Documentation, product pages, and all station-based CSVs (§2b, §2c): plain HTTPS GET, nothing else
  needed.
- Native netCDF bulk files (§2b): the one path that did not fully resolve automatically was NCEI's
  archive-manager redirect flow — but it never presented a credential prompt, so it is not classified as
  a login wall; it is simply unresolved by this session's automated client. See §2b recommendation.

## 7. Recommended aggregation to 10 km EPSG:5070 cells

1. **Reproject**: warp the native ~4.63 km EPSG:4326 raster(s) to EPSG:5070 (e.g. `rasterio`/GDAL
   `Resampling.bilinear`, appropriate for a smooth, continuously-varying climate field; avoid
   nearest-neighbor, which would introduce blocky artifacts at this resolution ratio).
2. **Per 10 km cell, use area-weighted zonal statistics (mean), not centroid sampling** — consistent
   with `AGENTS.md` §Phase-2 guidance to not assign heterogeneous values from a centroid alone. At a
   ~4.63 km native pixel vs. 10 km target cell, each cell typically spans roughly 2×2 to 3×3 source
   pixels, so a proper area-weighted mean (e.g. `exactextract`/`rasterstats`, or GDAL's
   average-resampling during warp directly to the 10 km grid) is cheap and meaningfully more correct
   than nearest/bilinear-at-centroid.
3. **Compute and record `coverage_fraction`** = (valid, non-NaN source pixel area) / (cell area) for
   every cell, every field. If `coverage_fraction == 0` (cell entirely over water/outside the CONUS
   nClimGrid domain — relevant mainly for coastal dev-bbox cells near the Gulf), set
   `status=unknown`, `value=null`, `missing_reason="outside NOAA nClimGrid CONUS coverage"` — never 0.
   If `0 < coverage_fraction < 1`, still compute the mean from available pixels (`status=observed` or
   `calculated` as appropriate) but reduce `confidence` (e.g. `medium` below some threshold such as
   50–80% coverage, project to decide) and keep `coverage_fraction` visible in provenance — never
   silently treat a partially-covered cell as fully observed.
4. **No multi-region reconciliation is needed** for this source in the sense `AGENTS.md` describes for
   tiled/multi-provider datasets — the gridded normals are one seamless national array, not stitched
   regional tiles. The only analogous phenomenon is the CONUS land/water NoData mask in point 3.
5. **Cooling/heating degree days — compute before aggregating, not after**: calculate CDD65/HDD65 at
   native pixel resolution first (sum the 366 daily `tavg_norm` pixels, in °F, per native pixel), then
   area-weight-aggregate that derived per-pixel annual raster to the 10 km grid using the same method as
   point 2. Aggregating the already-coarse *monthly* normals into a monthly-mean-based CDD proxy instead
   (`Σ days_in_month × max(0, monthly_tavg_F − 65)`) is a cheaper fallback but is a known biased
   underestimate of true CDD (Jensen's-inequality effect of using a monthly mean instead of daily
   values) — prefer the daily-based calculation documented here; if the monthly proxy is ever used
   instead, it must be labeled `calculated` with the approximation stated in `missing_reason`/method
   text, never presented as equivalent.
6. Precipitation is a depth normal (mm); use area-weighted **mean**, not a sum, when aggregating to
   10 km (summing would incorrectly imply accumulation across sub-cells).

## 8. Volume and memory estimate

- **Dev bbox** (`[-98.0, 29.0, -93.0, 33.0]`, ~5.0°×4.0° ≈ 480 km × 445 km): the source raster window
  needed is only about 120 × 96 ≈ 11,520 pixels per band — trivial (tens of KB per band in memory).
- **National (CONUS)**: each single-band file is 596×1385 = 825,460 pixels; as float32 that is ≈3.2 MB
  uncompressed per band in memory — far under the project's ~4 GB/process budget (`AGENTS.md` §7), even
  for all four base variables simultaneously.
- **CDD65/HDD65 calculation**: process the 366 daily files one at a time and maintain a single running
  accumulator array (596×1385 float64 ≈ 6.6 MB) — do **not** stack all 366 days in memory at once
  (that would be ≈1.2 GB, avoidable and unnecessary). This mirrors `AGENTS.md`'s windowed/streaming
  raster-read guidance.
- **On-disk, this session's pre-download** (§9 below): **375 files, 308,664,334 bytes (≈294 MiB / 296 MB
  on disk)** — far inside the 12 GB optional pre-download budget.
- If the adapter instead uses the native netCDF path (§2b) once a working bulk URL is obtained: 4 files
  ≈275 MB each (monthly/seasonal/annual combined per variable) + 1 daily file ≈1.2 GB per variable
  needed (tavg only, for CDD/HDD) ≈ 2.3 GB total for the four features — still well under 12 GB, and
  fewer, larger files (better matches `AGENTS.md`'s "no per-cell/many small requests" batching
  preference) **if** that URL can be obtained by a human/browser session.

## 9. What was pre-downloaded (`data/raw/noaa_ncei_climate/`)

Downloaded via the verified §2a COG path (curl, User-Agent `dc_locator/0.1 (research prototype)`,
anonymous SAS token). **375 files, 308,664,334 bytes total.** Every file's URL, local path, byte count,
sha256, and retrieval timestamp is recorded in `data/raw/noaa_ncei_climate/download_log.json`.

- `gridded-normals-cogs/normals-annual/1991-2020/` — 9 files: `{tavg,tmax,tmin,prcp}_norm.tif`,
  `{tavg,tmax,tmin,prcp}_flag.tif`, `tmax_max.tif` (the warmest-month field, see §4a).
- `gridded-normals-cogs/normals-daily/1991-2020/` — 366 files: `tavg_norm.tif` for day-of-year 001–366
  (needed to calculate CDD65/HDD65, see §4b/§7).

**Not pre-downloaded** (documented above instead, fetch on demand if needed): 2006-2020 and 1901-2000
period files; seasonal-frequency files; `_std`/`_min` bands; `tmin`/`prcp` daily files; the native NCEI
netCDF originals (§2b, URL not resolved); station-based CSV normals (§2c, already tiny and
directly fetchable per-station on demand for the optional cross-check).

**Pitfall hit and fixed during download** (kept here since it is not documented anywhere official):
the daily COG filenames need the day-of-year **zero-padded to exactly 3 digits for days 1–99**
(`1991_2020-daily-001-tavg_norm.tif`), while days 100–366 use the plain number. An unpadded day number
below 100 (e.g. `.../1991_2020-daily-1-tavg_norm.tif`) returns `HTTP 404` with an Azure
`BlobNotFound` XML body that is easy to mistake for "file doesn't exist" rather than a formatting bug.
This was discovered empirically in this session (all of days 1–99 failed on first pass, 100–366 all
succeeded; confirmed by testing `01` vs `001` directly) and is **not** stated in any NOAA or Planetary
Computer documentation read.

## 10. Interpretation limits (project-standard + source-specific)

- Climate normals are a smoothed 30-year average, **not an hourly operating-year simulation** — a data
  center energy/cooling model needs an hourly or TMY-like series for actual simulation; these normals
  are only a baseline climatological characterization of a cell (per `AGENTS.md` §3.5 and this task's
  own framing).
- A 30-year normal describes the past; it is not a future-climate projection and carries no built-in
  trend/uncertainty band for coming decades.
- `tmax_max`/`tavg_max`/etc. (annual) are **not** record/extreme single-day temperatures — they are
  "the maximum of the 12 monthly normal values," a specific, moderate statistic (confirmed empirically
  in §4a). Do not present these as climate extremes.
- Degree-day values computed here are derived from **smoothed gridded normals**, not from actual
  year-by-year station observations; they will not exactly reproduce a specific station's published
  CLDD/HTDD normal, especially in complex terrain. The documentation itself notes gridded daily normals
  "are best used to aggregate values for areas consisting of substantially more than one grid location"
  and that a single grid cell is less reliable than an actual station due to spline smoothing.
- Gridded coverage is CONUS land only; the dev bbox and national runs will have legitimate `UNKNOWN`
  cells near the coastline/Gulf where a 10 km cell is mostly water.

## 11. Pitfalls

- **Fill-value convention differs by format**: netCDF uses `-9999.0`; the COG derivative uses IEEE
  `NaN` (confirmed via `GDAL_NODATA` GeoTIFF tag). A single hardcoded sentinel check will silently
  mishandle one of the two formats.
- **Zero-padding gotcha** in COG daily filenames for day 1–99 — see §9.
- **No gridded CDD/HDD field exists at all** (any frequency) — must be calculated from daily `tavg_norm`;
  don't confuse with the station-based `ANN-CLDD-NORMAL`, which is real NOAA-computed CDD but only at
  ~7,300 discrete station points.
- **`*_max`/`*_min` COG/netCDF bands are not what their name suggests** at first glance — they are
  extremes *across the 12 months* (or across input years, for the monthly-frequency file's own
  `_min`/`_max`), not daily temperature extremes. Verify semantics before wiring a field blindly off its
  name; this session verified the annual `tmax_max` meaning empirically (§4a) but did not re-verify
  every `_min`/`_max` variant for every frequency/variable combination.
- **STAC collection license field says "proprietary"**, contradicting NOAA's own netCDF attribute — see
  §5; don't let an automated license gate block on the STAC field alone without checking the source.
- **NCEI's archive-manager bulk-download UI did not resolve automatically** in this session (§2b) —
  it is not confirmed to be a hard login wall, but a working direct URL to the native `.nc` files was
  not obtained; use the verified COG mirror, or have a human check the DOI landing pages in a real
  browser if the netCDF format specifically is required.
- **SAS tokens expire** (~24–25 h) — do not store a signed URL in configuration or in the download
  manifest as if it were permanent; this project's own `download_log.json` stores the clean blob URL
  without the token for that reason.
- **Three period baselines live side by side** in the same STAC collection and the same NCEI
  directories (1991-2020, 2006-2020, 1901-2000) — an adapter filter bug could silently pull the wrong
  30-year baseline.

## 12. Open questions

1. The exact, stable HTTPS URL for the native NCEI netCDF bulk files (`tavg-1991_2020-monthly-normals-v1.0.nc`
   etc., and the ~1.2 GB daily files) was not obtained by this automated session (§2b). If the Phase 2
   adapter specifically needs netCDF rather than COG, a human should retrieve it via a real browser from
   the DOI landing pages, or this should be re-attempted with a stateful browser session.
2. Whether any **interior** (non-coastal, non-water) gaps exist within CONUS land in the gridded product
   was not specifically tested — only the overall ~43.1% rectangular-array NoData fraction (concentrated
   at ocean/domain edges) was confirmed. Recommend differencing the pre-downloaded annual `tavg_norm`
   NaN mask against the project's own CONUS land polygon once that polygon exists (Phase 1 output).
3. The magnitude of bias between this project's planned daily-based gridded CDD65 calculation and the
   official station-based `ANN-CLDD-NORMAL` has not been numerically quantified for the dev bbox. Once
   the adapter exists, cross-check a handful of §2c per-station CSVs against the co-located gridded cell
   as a sanity check (this is the "optional enrichment" the task asked about).
4. The Planetary Computer STAC collection's `license: "proprietary"` field (§5) was not resolved with
   NOAA or Microsoft; this project should make its own documented call per `AGENTS.md` §4 if a strict
   reading is required.
5. The exact unit attribute string for `prcp` in the monthly/annual netCDF file itself was not
   individually re-opened in this session (inferred from the Daily doc's explicit "°C and mm" statement
   and NOAA's stated parallel file structure across variables) — low-risk, but worth a quick confirmation
   when the adapter first opens a real prcp file.
