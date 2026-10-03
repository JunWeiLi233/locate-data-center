# Source recon: `usgs_annual_nlcd` — USGS Annual National Land Cover Database (NLCD)

Status: **PARTIAL** (fully documented and verified; authoritative national bulk archive is
CAPTCHA-gated and was not fetched; a working, license-compliant windowed-read substitute was
verified and used to pre-download the dev-area sample).

Scope covered: Land Cover (`LndCov`) class fractions (required) and Fractional Impervious
Surface (`FctImp`, optional), per the task's feature list.

All facts below are tagged with where they came from (`verified_from`). Anything I could not
confirm against an official source or a live HTTP response is explicitly marked `UNVERIFIED`.

---

## 1. Product / version

- **Official name**: Annual National Land Cover Database (NLCD), Collection 1 Science Products.
  "Annual NLCD" is a *different, newer product line* from legacy (non-annual) NLCD — it replaces
  the old ad hoc release years (2001, 2004, …, 2021) with one map per calendar year, produced by
  an ensemble of deep-learning models rather than the legacy production system.
  `verified_from`: ScienceBase parent catalog item JSON (title, body, revision history):
  `https://www.sciencebase.gov/catalog/item/655ceb8ad34ee4b6e05cc51a?format=json` (HTTP 200).
- **Latest collection/version**: **Collection 1, Version 1.2** ("Collection 1.2"), publication
  date **2026-06-30**, covering CONUS **1985–2025**. Version history (all under the same
  ScienceBase parent item and the same DOI):
  - v1.0 — first posted 2024-10-24, CONUS 1985–2023.
  - v1.1 — revised 2025-06-25, adds 2024 (CONUS 1985–2024).
  - v1.2 — revised 2026-06-30, adds 2025 (CONUS 1985–2025). **This is the current version; it is
    the only version MRLC's own data page links to (mrlc.gov says "the current version … offered
    on mrlc.gov is Collection 1 Version 2 (1.2) … the only version on www.mrlc.gov").**
  `verified_from`: ScienceBase parent item JSON `body`/revision history (HTTP 200, fetched
  2026-10-02), cross-checked against the User Guide PDF "Document History" section (see §7) and
  `WebSearch` results from mrlc.gov/usgs.gov pages.
- **Latest year available**: **2025** on ScienceBase (`Annual_NLCD_LndCov_2025_CU_C1V2.zip`,
  `Annual_NLCD_FctImp_2025_CU_C1V2.zip`). The public ArcGIS ImageServer windowed-read endpoint
  (§3) currently only goes through **2024** (one release behind) — re-check both before
  implementation, both will keep moving forward.
- **Six science products** in the suite (all CONUS, all single-band, all share one footprint):
  Land Cover (`LndCov`), Land Cover Change (`LndChg`), Land Cover Confidence (`LndCnf`),
  Fractional Impervious Surface (`FctImp`), Impervious Descriptor (`ImpDsc`), Spectral Change Day
  of Year (`SpcChg`). `verified_from`: User Guide §1 / ScienceBase parent item body.
- **Citation** (from MRLC FAQ and the ScienceBase DOI record):
  > U.S. Geological Survey (USGS), 2024, Annual NLCD Collection 1 Science Products: U.S.
  > Geological Survey data release, https://doi.org/10.5066/P94UXNTS
  `verified_from`: `https://www.mrlc.gov/faq` (WebFetch) and DOI resolution test (HTTP 200 on
  `https://doi.org/10.5066/P94UXNTS`). The same DOI covers the ongoing v1.0/1.1/1.2 revisions.

## 2. Endpoints (all verified live, 2026-10-02)

| # | URL | Method | Result | Notes |
|---|---|---|---|---|
| 1 | `https://www.mrlc.gov/data/project/annual-nlcd` | GET | 200 | Project overview page |
| 2 | `https://www.mrlc.gov/data` | GET | 200 | "Direct download" portal; in practice a thin wrapper that links straight to the ScienceBase item below — no separate MRLC-hosted mirror was found |
| 3 | `https://www.usgs.gov/centers/eros/science/annual-nlcd-data-access` | GET | 200 | Lists all 6 access channels (EarthExplorer, MRLC viewer, MRLC direct download, ScienceBase, AWS S3, WMS) |
| 4 | `https://www.usgs.gov/centers/eros/science/annual-national-land-cover-database` | GET | 200 | Project description page |
| 5 | `https://www.sciencebase.gov/catalog/item/655ceb8ad34ee4b6e05cc51a?format=json` | GET | 200 | Parent catalog item — JSON API, has the full revision history and links to all 23 child items (one per product × collection) |
| 6 | `https://www.sciencebase.gov/catalog/item/697b9279b66b0197c3043cc3?format=json` | GET | 200 | **Collection 1.2 Land Cover** child item — full per-year file list with exact byte sizes |
| 7 | `https://www.sciencebase.gov/catalog/item/697b907eb66b0197c3043c9f?format=json` | GET | 200 | **Collection 1.2 Fractional Impervious Surface** child item |
| 8 | `.../catalog/file/get/<itemId>?f=__disk__<hash>` (small files: FGDC XML, PNG, the User Guide PDF) | GET | 200 | Direct, immediate download, **no CAPTCHA** — used to fetch the 1,995,189-byte User Guide PDF (exact byte match to the declared size) |
| 9 | `https://sciencebase.usgs.gov/manager/item/<itemId>/file/<cuid>` and `.../manager/download/<cuid>` (the big per-year ZIPs) | GET | 200 | **Not the file.** Returns a 4,255-byte HTML "ScienceBase File Manager" single-page-app shell — resolving the real bytes needs that JS app (see §5) |
| 10 | `https://www.sciencebase.gov/catalog/item/requestDownload/<itemId>?filePath=__s3__` | GET | 200 | **CAPTCHA wall.** Page title is literally "Captcha check - ScienceBase-Catalog"; embeds `https://www.google.com/recaptcha/api.js`. Not solved (see §5/§6). |
| 11 | `https://usgs-landcover.s3.us-west-2.amazonaws.com/annualnlcd/c1/v0/cu/mosaic/Annual_NLCD_FctImp_1985_CU_C1V0.tif` | HEAD (anon, with/without `x-amz-request-payer: requester`) | **403 Forbidden** | Requester-pays bucket; needs a signed AWS request + billed account, not just an HTTP request |
| 12 | `https://di-nlcd.img.arcgis.com/arcgis/rest/services/USA_NLCD_Annual_LandCover/ImageServer?f=json` | GET | 200 | **Public, unauthenticated** ArcGIS ImageServer for Land Cover — windowed reads, no login |
| 13 | `https://di-nlcd.img.arcgis.com/arcgis/rest/services/USA_NLCD_Annual_LandCover_Fractional_Impervious_Surface/ImageServer?f=json` | GET | 200 | Same, for Fractional Impervious Surface |
| 14 | `https://di-nlcd.img.arcgis.com/arcgis/rest/services?f=json` | GET | 200 | Directory listing — confirms **all 6 products** are published as individual public ImageServer endpoints: `USA_NLCD_Annual_LandCover`, `..._Change`, `..._Confidence`, `..._Date_Spectral_Change`, `..._Fractional_Impervious_Surface`, `..._Impervious_Descriptor` |
| 15 | `.../USA_NLCD_Annual_LandCover/ImageServer/exportImage?...&f=image` | GET | **200**, `image/tiff` | Real pixel data confirmed (downloaded; see §9) |
| 16 | `https://www.mrlc.gov/data/legends/national-land-cover-database-class-legend-and-description` | GET | 200 | Secondary/corroborating legend reference (legacy-NLCD page, same 16-class scheme) |
| 17 | `https://www.usgs.gov/information-policies-and-instructions/copyrights-and-credits` | GET | 200 | USGS public-domain policy (§6) |
| 18 | `https://doi.org/10.5066/P94UXNTS` | GET | 200 | Citation DOI resolves |

**Every URL above returned 2xx to a live request in this session.** Row 9/10/11 are documented
*because they are blocked*, not because they are usable download endpoints.

## 3. The practical recommendation: two different official access paths

1. **Authoritative bulk archive (ScienceBase)** — the real, citable, versioned national CU-mosaic
   GeoTIFF-in-a-zip per year per product. **Blocked for automated/scripted download** by a
   CAPTCHA once ScienceBase routes the file through its large-file ("S3-backed") path (rows 9–10
   above). See §5 for the manual path.
2. **Public ArcGIS ImageServer REST endpoints** (`di-nlcd.img.arcgis.com`, row 12–15) — no login,
   no CAPTCHA, standard Esri `exportImage` windowed reads, confirmed working end-to-end including
   an on-the-fly reprojection to the project's own EPSG:5070. **Currently one annual release
   behind** ScienceBase (serves through 2024, not yet 2025) and has some data-quality caveats
   documented in §9/§11. I could not confirm from the MRLC viewer's own JS bundle that this is
   literally the engine behind `mrlc.gov/viewer` (no literal hostname match in the minified JS,
   which may load its config at runtime) — treat it as "independently verified, spec-consistent,
   public" rather than "officially MRLC's".

Both are documented in full below so the Phase 2 adapter author can choose per need (production
national run → wait for/obtain the authoritative ScienceBase file via the manual path once;
quick dev-area iteration or prototyping → the ImageServer is immediately usable).

## 4. CRS, resolution, coverage

- **Projection**: Albers Equal Area Conic. Exact parameters, from the official User Guide's
  GeoTIFF key table (Table 2-8) — `verified_from`: LSDS-2103 v1.2 User Guide §2.2.2, read
  directly from the downloaded PDF:
  - `GTCitationGeoKey = "AEA WGS84"`, `ProjCoordTransGeoKey = CT_AlbersEqualArea`
  - Standard parallels: **29.5°N and 45.5°N**; Latitude of origin: **23°N**; Central meridian:
    **-96°**; False easting/northing: **0 / 0**; linear unit: metre.
  - Ellipsoid/datum: **WGS84** (`GeographicTypeGeoKey = GCS_WGS_84`, semi-major axis 6378137.0,
    inverse flattening 298.257223563) — **not NAD83**.
  - The GeoTIFF's `ProjectionGeoKey`/`ProjectedCSTypeGeoKey` fall in GeoTIFF's "User-Defined"
    ranges (10000–19999 / 20000–32760): the product defines its CRS by explicit parameters, it
    does **not** cite one clean registered EPSG CRS code.
  - **Cross-checked independently** two more ways: (a) the ArcGIS ImageServer's own `?f=json`
    metadata reports the identical parameters under a WKT `PROJCRS["AEA_WGS84", BASEGEOGCRS["GCS_WGS_1984", DATUM["D_WGS_1984", ...]]]`;
    (b) an actual exported GeoTIFF (§9) carries an embedded ESRI PE string
    `GCS Name = WGS 84|Datum = WGS_1984|...`.
  - **Pitfall for Phase 2** (flagging explicitly because the project's canonical CRS,
    AGENTS.md §6, is **EPSG:5070 = NAD83** Conus Albers with the *same* projection parameters but
    a *different datum*): do a real coordinate transform (e.g. `pyproj`) from this WGS84-Albers
    definition into EPSG:5070, don't just relabel the CRS tag. The WGS84/NAD83 shift is
    conventionally treated as negligible (sub-2 m) at 30 m CONUS resolution, but that is an
    approximation that should be stated in provenance, not silently assumed.
- **Native resolution**: 30 m × 30 m pixels. `verified_from`: User Guide §2.1.4 ("fractional
  impervious surface product provides the percentage of a 30-meter pixel…") and both
  ImageServers' `pixelSizeX`/`pixelSizeY` = 30 (HTTP 200 JSON).
- **Pixel alignment**: `GTRasterTypeGeoKey = RasterPixelsPoint`, coordinate at the pixel's
  upper-left corner, explicitly stated to match the Landsat U.S. Analysis-Ready-Data (ARD) tile
  grid. `verified_from`: User Guide Table 2-8 note ("This matches the Level-2 source U.S. ARD
  tiles."). I did not independently re-derive the exact grid-origin offset from a downloaded
  authoritative national GeoTIFF (blocked by the CAPTCHA, §5); the ImageServer's own canvas
  extent (`xmin=-2415585, ymin=164805, xmax=2384415, ymax=3314805`, all exact multiples of 30 m)
  is a reasonable but unconfirmed proxy — re-verify against the real file's `GeoTransform` once a
  human has downloaded one.
- **Spatial coverage**: Conterminous United States (CONUS; 48 states + DC) only. Alaska, Hawaii,
  and Puerto Rico are **not** covered by Annual NLCD; those remain on separate *legacy* (non-
  annual) NLCD products/ScienceBase items with older end years (Hawaii through 2001, Alaska
  through 2016, Puerto Rico through 2001). `verified_from`: WebSearch summary of
  `usgs.gov/centers/eros/science/annual-nlcd-data-access` (consistent with this project's
  explicitly CONUS-only scope, so not a blocker). Within CONUS the product is wall-to-wall/
  complete; NoData (see §7) appears only outside the mapped footprint (open ocean beyond the
  coastline, etc.), not as gaps inside CONUS.

## 5. Access requirements — what's open, what's blocked, and why

| Path | Auth/forms needed? | Status | Evidence |
|---|---|---|---|
| MRLC/USGS documentation pages | None | OK | Plain GET, 200 |
| ScienceBase catalog JSON API + small files | None | OK | Plain GET, 200, exact byte-size match on the User Guide PDF |
| ScienceBase big per-year ZIPs | **CAPTCHA** (Google reCAPTCHA) once routed to the S3-backed large-file flow | **BLOCKED** (not solved, per AGENTS.md §4 "never bypass access controls … no CAPTCHA/bot-challenge circumvention") | `requestDownload` page titled "Captcha check - ScienceBase-Catalog", loads `google.com/recaptcha/api.js` |
| AWS S3 `usgs-landcover` bucket | AWS account + billing (requester-pays), SigV4-signed requests | **BLOCKED** for anonymous/scripted use (no credentials used) | Anonymous HEAD → 403 Forbidden, with or without `x-amz-request-payer: requester` |
| Public ArcGIS ImageServer (`di-nlcd.img.arcgis.com`) | None | **OK, verified working** | `exportImage` returned 200 `image/tiff` with real, structurally valid pixel data |
| EarthExplorer (`earthexplorer.usgs.gov`) | Free USGS/EROS login typically required for ordering/bulk download | Not tested — not needed since the above two paths already cover the requirement | `UNVERIFIED` (secondary channel, out of scope given working alternatives) |

**Manual acquisition path for the authoritative file** (documented per task instructions, not
executed): a person opens
`https://www.sciencebase.gov/catalog/item/697b9279b66b0197c3043cc3` in an ordinary browser, picks
the desired year's ZIP (e.g. `Annual_NLCD_LndCov_2025_CU_C1V2.zip`, 1,457,983,950 bytes), solves
the reCAPTCHA / confirms the large-file prompt, lets ScienceBase mint a presigned S3 URL, and
downloads it — then drops it under `data/raw/usgs_annual_nlcd/manual/` and records its sha256 in
`download_log.json`. Same idea for the AWS path with a funded AWS account and
`aws s3 cp ... --request-payer requester`.

## 6. License / terms of use

USGS-produced data is U.S. Government work and is in the **public domain**. `verified_from`:
`https://www.usgs.gov/information-policies-and-instructions/copyrights-and-credits` (HTTP 200):

> "USGS-authored or produced data and information are considered to be in the U.S. Public
> Domain."

No login, click-through license, or usage fee applies to the data itself (caveat: some
*photographs/multimedia* elsewhere on USGS sites can be separately copyrighted — not relevant to
this raster product). Attribution is **requested, not legally required**; use the citation in §1.

## 7. Fields / units / codes (all `verified_from` LSDS-2103 "Annual National Land Cover Database
   (NLCD) Collection 1 Science Product User Guide", **Version 1.2, June 2026**, downloaded in
   full from ScienceBase — `https://www.sciencebase.gov/catalog/file/get/655ceb8ad34ee4b6e05cc51a?f=__disk__34%2F28%2Fc7%2F3428c70d12fc5cf04aecdcc7df872c1dc6d75337`,
   1,995,189 bytes, read directly with `pdftotext`)

### 7.1 Land Cover (`LndCov`) — required

Single band, `UINT8`. **Valid pixel values are exactly these 16 codes; NoData = 250** (Table 2-1,
"Land Cover Legend for Conterminous United States (CONUS)"):

| Code | Class |
|---|---|
| 11 | Open Water |
| 12 | Perennial Ice/Snow |
| 21 | Developed, Open Space (<20% impervious) |
| 22 | Developed, Low Intensity (20–49% impervious) |
| 23 | Developed, Medium Intensity (50–79% impervious) |
| 24 | Developed, High Intensity (80–100% impervious) |
| 31 | Barren Land (Rock/Sand/Clay) |
| 41 | Deciduous Forest |
| 42 | Evergreen Forest |
| 43 | Mixed Forest |
| 52 | Shrub/Scrub |
| 71 | Grassland/Herbaceous |
| 81 | Pasture/Hay |
| 82 | Cultivated Crops |
| 90 | Woody Wetlands |
| 95 | Emergent Herbaceous Wetlands |
| **250** | **NoData** |

**NoData is 250, not 0** — confirmed twice: (a) literally in the official table above, and (b)
independently by reading the embedded `GDAL_NODATA` TIFF tag of an actual downloaded raster,
which reads `"250"` (see §9). Four additional codes (51 Dwarf Scrub, 72 Sedge/Herbaceous, 73
Lichens, 74 Moss) appear in the ArcGIS ImageServer's generic `/legend` endpoint output but are
**not** in the CONUS-specific Table 2-1 of the official User Guide — they are presumed Alaska-
oriented legacy-legend leftovers bundled into a shared renderer; none were observed in the
dev-bbox sample (§9).

No explicit units (categorical class codes). Recommended downstream field naming per AGENTS.md
(`_frac` suffix for 0–1 fractions): `landcover_<code>_frac` or a semantic name per class, e.g.
`landcover_developed_high_frac`.

### 7.2 Fractional Impervious Surface (`FctImp`) — optional, requested

Single band, `UINT8`. **Valid value range 0–100** (percent impervious surface area within the
30 m pixel, continuous), **NoData = 250** (Table 2-5). `0` is a legitimate, documented value
("zero represents no mapped impervious surface on the landscape") — **not** missing data.
Units: percent (`_pct` per AGENTS.md convention), or convert to a `_frac` by `/100`.

### 7.3 Other four products (same source, same access pattern; out of this task's required scope
    but documented for completeness since they cost nothing extra to know about)

| Product | Type | Valid range | NoData | Notes |
|---|---|---|---|---|
| Land Cover Change (`LndChg`) | UINT16/UINT8 | two-digit "from" + two-digit "to" class codes concatenated (e.g. 9590) | 9999 | Year-over-year change vs. the prior annual map |
| Land Cover Confidence (`LndCnf`) | UINT8 | 1–100 (uncalibrated model probability, %) | 250 | Not an accuracy/error metric — "does not correspond to the absolute likelihood of the land cover being correct" |
| Impervious Descriptor (`ImpDsc`) | UINT8 | 0 = Non-Urban, 1 = Roads, 2 = Urban | 250 | Distinguishes road vs. non-road impervious surface |
| Spectral Change Day of Year (`SpcChg`) | UINT16 | 1–366 = day of year of a detected spectral change; 0 = no change (valid, not missing) | 9999 | Not necessarily a land-cover-class change (e.g., drought/fire spectral shifts) |

All six products share **one identical geospatial extent and footprint** (User Guide §2.2.3:
"All products are single-band rasters with an identical geospatial extent and mapping
footprint. Areas within the raster that are outside of the mapping area are assigned the NoData
value.").

### 7.4 File format

Cloud-Optimized GeoTIFF (COG): internally tiled, HTTP range-request friendly, often internally
compressed, commonly includes overviews/pyramids. `verified_from`: User Guide §2.2.1.
**This confirms windowed reads without a full download are supported** by the format itself —
the practical blocker to exploiting that directly against the *authoritative* ScienceBase file is
the CAPTCHA wall in front of the file bytes (§5), not the file format. The ArcGIS ImageServer
(§3) is the verified-working windowed-read path in practice.

## 8. Recommended aggregation (native 30 m → 10 km EPSG:5070 cells)

1. **Land Cover → per-cell class fractions** (matches the task's framing exactly): for each
   10 km × 10 km target cell, count native pixels by class within the cell footprint and divide
   by the count of *valid* (non-NoData) pixels in that cell → one `_frac` column per class,
   summing to 1.0 over valid pixels. **Never average or bilinear-interpolate the categorical
   codes** — use nearest-neighbor only if any resampling is unavoidable, and prefer exact pixel
   counting (zonal histogram) over resampling entirely.
   - Implementation: reproject each 10 km cell polygon into the source Albers/WGS84 CRS (one
     coordinate transform of a simple rectangle, done once per cell) and do the zonal count there
     — this avoids a second resampling pass of the categorical raster. Equivalently, reproject
     the whole raster once with nearest-neighbor if that's operationally simpler; either is fine
     as long as it's documented (AGENTS.md provenance).
   - At 30 m resolution a 10 km cell holds ~333 × 333 ≈ 110,889 source pixels — cheap to count
     per cell; use `rasterio`/`rioxarray` windowed reads (or `rasterstats`), batched per tile, not
     a national in-memory array (see Volume/Memory below).
2. **Fractional Impervious Surface → area-weighted mean** of the continuous 0–100 value over
   valid pixels in the cell (simple arithmetic mean of native pixel values is already
   area-weighted since all source pixels are equal-area 30 m cells).
3. **Cells spanning multiple source "regions"**: Annual NLCD is one seamless national CONUS
   product (no state/vendor tiling), so the main case of a cell seeing more than one "region" is a
   **coastal/boundary cell** where part of the 10 km cell falls outside the mapped CONUS footprint
   (open ocean, etc.). For those: record `coverage_fraction = valid_pixel_count / total_pixel_count`
   explicitly, and keep the non-covered portion **UNKNOWN**, never fold it into any class's
   fraction and never treat it as zero, per AGENTS.md §3.3 and the Phase 2 spec's "Unmapped flood
   coverage is UNKNOWN, not zero flood risk" principle applied the same way here. If a future
   national run ever blends in Alaska/Hawaii/Puerto Rico's separate legacy-NLCD products, record
   which source/vintage covered each cell explicitly (a provenance field), since those are a
   genuinely different product with different class codes/years.
4. Record `native_spatial_resolution = 30 m`, `data_year` (the map year used), `aggregation_method`,
   and `coverage_fraction` per the long-form provenance table required by the Phase 2 spec.

## 9. Volume / memory estimate (verified empirically with a real pre-download)

**Dev area** (`EPSG:4326` bbox `[-98.0, 29.0, -93.0, 33.0]`, reprojected to EPSG:5070 for the
export: `-195082.5, 658531.4` to `292597.5, 1107691.4`, i.e. **487.68 km × 449.16 km**):

- 16,256 × 14,972 px per single-band product-year → **243,384,832 pixels** →
  **230,367,480 bytes (~219.7 MiB) actual, per product-year**, confirmed by two real downloads
  (see below).
- Land Cover + Fractional Impervious Surface for one year, dev area: **~440 MiB combined**
  (actually downloaded).
- All 6 products, one year, dev area: roughly **~1.1–1.3 GiB** combined (2 of the 6 are UINT16,
  roughly doubling their per-pixel cost) — an `UNVERIFIED` extrapolation, not downloaded.
- **National** scope, authoritative ScienceBase ZIPs, *one year*: Land Cover ≈ 1.3–1.46 GB + FctImp
  ≈ 0.93–0.98 GB ≈ **~2.3–2.4 GB total** for the two required products — well inside the 12 GB
  optional-pre-download budget per source, but **could not be spent automatically** because of the
  CAPTCHA (§5).
- **National, all years (1985–2025, 41 years)**, just these two products: roughly
  **41 × 2.3 GB ≈ 94–97 GB**. The task only needs the *latest year* for current-state features, so
  **do not** bulk the full 41-year history — pull one year nationally (~2.3–2.4 GB), not the
  archive.
- **Memory**: the ImageServer's own reported national canvas (`xmin -2,415,585`, `xmax 2,384,415`,
  `ymin 164,805`, `ymax 3,314,805`, in its native Albers metres) is ≈160,000 × 105,000 px ≈ 16.8
  billion pixels ≈ ~16 GB if ever materialized uncompressed in memory as one array — far over
  AGENTS.md's ~4 GB/process budget. **Always window/tile the read** (per-cell or per-batch
  `rasterio` windows); never load a national array at once, exactly as AGENTS.md §7 and the Phase
  2 spec require.

**Actually downloaded in this session** (both via the public ImageServer, EPSG:5070, nearest-
neighbor, map year 2024 = latest year currently in that service):

| File | Bytes | SHA-256 |
|---|---|---|
| `data/raw/usgs_annual_nlcd/Annual_NLCD_LndCov_2024_devbbox_5070.tif` | 230,367,480 | `d60479c1d5ee951d8caa2fb211ad2f87da1a1a41aa178ac25ed98d94a93c83ba` |
| `data/raw/usgs_annual_nlcd/Annual_NLCD_FctImp_2024_devbbox_5070.tif` | 230,367,480 | `77de8b0c821d10804b244cb81993000a59a1c3c779d4b820195da216bb03fb27` |

Full request URLs, timestamps, and notes are in `data/raw/usgs_annual_nlcd/download_log.json`.
Both files were opened and validated with Pillow/numpy (correct dimensions, `uint8`, single
band) and histogrammed against the official code list (see §11 for what that check found).

## 10. Interpretation limits

- Annual NLCD classes are the output of a supervised deep-learning ensemble classification of
  Landsat imagery (User Guide §4), not a ground survey — treat as `value_status: observed` (it is
  the dataset's own reported value) but remember it carries classification uncertainty. The
  companion Land Cover Confidence product (§7.3, same access pattern) can quantify this per pixel
  if ever needed; it was not pre-downloaded (out of this task's required scope).
- Annual NLCD is CONUS-only; it cannot answer anything about Alaska, Hawaii, or Puerto Rico (not
  a concern for this project's stated CONUS scope, but worth stating explicitly rather than
  silently).
- A land-cover class fraction is a description of surface cover, not a direct statement about
  land availability, ownership, zoning, or buildability — consistent with AGENTS.md §3.5's general
  "proxies are not facts" principle and the Phase 2 spec's "Land-cover composition is a geographic
  feature… Do not exclude an entire cell merely because a small portion overlaps water, wetlands,
  or protected land."
- The "Developed" intensity classes (21–24) are themselves impervious-surface-percentage bins,
  not calibrated building-density/occupancy; if finer granularity than four bins is wanted, use
  the continuous Fractional Impervious Surface product instead/in addition.

## 11. Pitfalls (ranked by how easy they are to get wrong)

1. **NoData is 250, not 0.** The single easiest and most consequential mistake. Verified twice,
   independently (official doc Table 2-1, and the embedded `GDAL_NODATA` tag of an actual
   downloaded file).
2. **A "0" that is not documented anywhere showed up in a real Land Cover export** over the dev
   bbox: 2.70% of pixels (6,574,408 of 243,384,832), concentrated in a pattern consistent with
   Gulf-of-Mexico open water beyond the product's mapped footprint (the dev bbox extends
   offshore). This is a **different value than the documented NoData (250)**. Hypothesis, not
   fully confirmed: the ImageServer's mosaic returns a service-level background fill (0) for area
   outside its source-raster footprint, distinct from the product's own internal NoData (250) for
   gaps inside a mapped tile. **Treat both 0 and 250 as missing/UNKNOWN** when reading Land Cover
   from this ImageServer; this specific ambiguity has not been checked against the authoritative
   ScienceBase GeoTIFF directly (blocked by the CAPTCHA).
3. A long tail of rare off-legend pixel values (tens to a couple-thousand pixels each, <0.01% of
   the image cumulatively, e.g. 117, 122, 128, 164, 198…) appeared in both dev-bbox exports —
   consistent with thin seam-line resampling artifacts at internal mosaic/tile boundaries.
   Validate every pixel against the official code list; treat anything unrecognized as UNKNOWN.
4. Source CRS is Albers on **WGS84**, the project's canonical CRS is Albers on **NAD83**
   (EPSG:5070) — same projection parameters, different datum. Do a real transform.
5. The convenient public ImageServer is **one annual release behind** the authoritative
   ScienceBase archive (through 2024 vs. 2025 as of this writing) — re-check both at
   implementation time.
6. The bulk authoritative per-year ZIP is CAPTCHA-gated; budget for a one-time **manual** human
   download (then cache/never re-download, per AGENTS.md §4) rather than assuming it can be
   scripted end-to-end.
7. Four legend codes (51/72/73/74) appear in the ImageServer's generic legend endpoint but not in
   the CONUS-specific official table — don't require them, don't crash if they appear.
8. Land Cover Change packs two class codes into one integer (`AABB`) — don't confuse with plain
   Land Cover codes if that product is added later.
9. `0` in **Fractional Impervious Surface** (unlike in Land Cover) **is legitimate** ("0% paved"),
   not missing — don't apply the same "treat 0 as suspicious" logic across both products.

## 12. Open questions

- Is `di-nlcd.img.arcgis.com` an official USGS/MRLC-operated endpoint, or an Esri-side mirror
  built to spec? Not confirmed from the MRLC viewer's minified JS bundle (no literal hostname
  match found; the viewer may fetch its service config at runtime rather than hardcoding it).
- Root cause of the value-0 anomaly and the rare off-legend pixel tail in ImageServer exports —
  not diagnosed beyond the hypotheses in §11.2–11.3.
- Exact native pixel-grid phase/origin (to snap zonal windows pixel-exactly) was not re-derived
  from an authoritative downloaded GeoTIFF's own `GeoTransform` (blocked by the CAPTCHA); the
  ImageServer's reported canvas extent is a reasonable but unconfirmed proxy.
- Whether EarthExplorer's bulk-download path truly requires a login for this specific product —
  not tested, since the two paths above already satisfy the task.

## 13. Files referenced / produced

- Report (this file): `docs/research/phase2/usgs_annual_nlcd.md`
- Pre-downloaded dev-area samples + full provenance: `data/raw/usgs_annual_nlcd/download_log.json`,
  `data/raw/usgs_annual_nlcd/Annual_NLCD_LndCov_2024_devbbox_5070.tif`,
  `data/raw/usgs_annual_nlcd/Annual_NLCD_FctImp_2024_devbbox_5070.tif`
- Nothing under `src/`, `configs/`, `tests/`, other `docs/*.md`, `pyproject.toml`, or `AGENTS.md`
  was modified, per this task's constraints.
