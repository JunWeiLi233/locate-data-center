# usgs_padus — USGS Protected Areas Database of the United States (PAD-US)

Status: **PARTIAL** (ready for the primary GAP-status deliverable; one secondary field blocked — see Access)
Researched: 2026-10-02/03 (resumed from an interrupted prior session; see `data/raw/usgs_padus/download_log.json`)

## 1. Product / version

- **Official name**: Protected Areas Database of the United States (PAD-US) 4.1
- **Publisher**: U.S. Geological Survey (USGS), Gap Analysis Project (GAP); catalogued on ScienceBase
- **Version**: 4.1, ScienceBase publication date **2025-03-31** (confirmed the newest; no 4.2/5.0 found). Citation (verified via ScienceBase API): "U.S. Geological Survey (USGS) Gap Analysis Project (GAP), 2024, Protected Areas Database of the United States (PAD-US) 4.1: U.S. Geological Survey data release, https://doi.org/10.5066/P96WBCHS."
- **DOI**: https://doi.org/10.5066/P96WBCHS — verified: resolves `302 -> 200` to the ScienceBase parent item.
- **Data year/period**: Not a single-year observation. It is a continually-updated "best available data" inventory; this snapshot's `dates` block (ScienceBase API) reports Start=2005, End=2025, Publication=2025-03-31.
- **ScienceBase catalog structure** (all fetched via the public ScienceBase JSON API, `?format=json&fields=...`, no key/login needed):
  - Parent: *PAD-US 4* — `65294599d34e44db0e2ed7cf`
  - *PAD-US 4.1 Full Inventory Database* — `652d4fc5d34e44db0e2ee45e` (Fee/Easement/Designation/Proclamation/Marine/Combined, **not flattened**, full attribute set)
  - *PAD-US 4.1 Raster Analysis* — `6759b67ed34edfeb8710a3db` (30 m CONUS/AK/HI rasters **plus** a bundled flattened vector layer used to make them)
  - *PAD-US 4.1 Vector Analysis and Summary Statistics* — `6759b69fd34edfeb8710a3ea` (flattened/overlap-removed "Combined" layers + pre-aggregated CSV statistics)
  - *PAD-US 4.1 State Downloads* — `6759abcfd34edfeb8710a004` (not needed; we use the national/CONUS file)

## 2. Recommended product (re-evaluated from the prior session's download)

The prior interrupted session had downloaded `PADUS4_1_Raster_CONUS.zip` (744,032,421 bytes) expecting to use the **30 m raster**. I verified this file is complete and byte-identical to the source (MD5 match, see §3), but re-evaluated whether the raster itself is the right product, per the task instructions.

**Finding: the raster is the wrong primary product; a vector file already bundled inside the same zip is the right one.**

`PADUS4_1_Raster_CONUS.zip` actually contains **two different products**:
1. The CONUS 30 m categorical raster (ERDAS IMAGINE `.img` + external `.ige`/`.rde`/`.rrd` + a 307,052-row value-attribute-table `.dbf`). Fully decompressing it needs **~79 GB** of disk (see §8) — far beyond what is needed.
2. `PADUS4_1VectorAnalysis_CONUS.gdb` — a 322,263-feature polygon layer (layer name `PADUS4_1_VectorAnalysis_CONUS`) that is the **flattened/overlap-removed "Combined" vector file USGS itself rasterized to produce the raster above** (confirmed by reading `RasterizationReport_PADUS4_1CONUS.txt`, which is inside the same zip: *"Input file: PAD-US 4.1 Vector Analysis File ... Method: Created using QGIS ... Rasterize ... using: GAP_Sts field as the priority field for creating the raster and addressing overlaps"*).

This vector layer is **only 422 MB uncompressed**, is already dissolved of overlaps (exactly the "recommended overlay method" the task asks for — see §7), carries `GAP_Sts`, `Des_Tp`, `Pub_Access`, `Mang_Type` (see §5), and its own CRS is functionally identical to EPSG:5070 (§4). I extracted just this subfolder (skipping the huge raster payload) to `data/raw/usgs_padus/PADUS4_1VectorAnalysis_CONUS.gdb/` for direct use (441,838,654 bytes, 63 files).

**I therefore recommend `PADUS4_1VectorAnalysis_CONUS.gdb` → layer `PADUS4_1_VectorAnalysis_CONUS` as the primary Phase 2 input, not the raster.** No new download was needed for this — it was already present in the file the prior session had fetched.

The only field in the task's requested list that this recommended layer does **not** carry is literal `Own_Type` (see §5.5 and §6 — that field lives only in the separate, CAPTCHA-gated Full Inventory Database).

## 3. Endpoints (verified)

All requests used `User-Agent: dc_locator/0.1 (research prototype)`. HTTP status and `Content-Length` were captured with `curl -sI` (HEAD) against the exact download URLs returned by ScienceBase's own JSON API (`https://www.sciencebase.gov/catalog/item/<id>?format=json&fields=files`).

| File | ScienceBase item | Size (bytes) | MD5 (ScienceBase) | HTTP HEAD | Already on disk? |
|---|---|---|---|---|---|
| `PADUS4_1_Raster_CONUS.zip` | `6759b67ed34edfeb8710a3db` | 744,032,421 | `1c0823bc087d54b604afc7922d5280e8` | **200**, `Content-Type: application/zip`, `Content-Length: 744032421` | Yes — local MD5 matches exactly |
| `PADUS4_1SummaryStatistics_TabularData_CSV.zip.zip` *(sic — see note)* | `6759b69fd34edfeb8710a3ea` | 4,086,817 | `e998e297c684f22185c94d9840953897` | **200**, `Content-Type: application/zip`, `Content-Length: 4086817` | Yes — local MD5 matches exactly |
| `PADUS4_1Geodatabase.zip` (Full Inventory) | `652d4fc5d34e44db0e2ee45e` | 1,523,434,496 | not published (S3-backed) | **200** on the item page, but see §6 — the actual *download* endpoint is CAPTCHA-gated | No |
| `PADUS4_1VectorAnalysis_PADUS_Only.zip` | `6759b69fd34edfeb8710a3ea` | 361,476,711 | not published (S3-backed) | Same CAPTCHA gate as above | No |
| `PADUS4_1VectorAnalysis_OtherExtents.zip` | `6759b69fd34edfeb8710a3ea` | 5,361,853,089 | not published (S3-backed) | Same CAPTCHA gate as above | No |
| `PADUS4_1_SourceData_ExtentBoundariesUsedForStatistics.zip` (Census boundaries; not needed) | `6759b69fd34edfeb8710a3ea` | 350,908,732 | `980547a1558058632ea0bbf6ab9b3767` | **200** direct (disk-backed, not S3) | No (not needed — our own grid supplies area accounting) |
| `PADUS41_VectorAnalysisFile_MetadataXML.xml` (FGDC metadata — primary source for §5 field domains) | `6759b69fd34edfeb8710a3ea` | 71,403 | `029426e37f8785efc58e219880596587` | **200**; fully downloaded and parsed in this session | n/a (doc, not data) |
| GAP status definitions page | `usgs.gov/programs/gap-analysis-project/science/pad-us-data-overview` | — | — | **200** (fetched and quoted in §5.1) | n/a |
| PAD-US Data Manual (landing page) | `usgs.gov/programs/gap-analysis-project/pad-us-data-manual` | — | — | **200** (HEAD only; full crosswalk tables not individually re-verified — see Open Questions) | n/a |
| DOI | `doi.org/10.5066/P96WBCHS` | — | — | **302 → 200** to the parent ScienceBase item | n/a |

**Note on the doubled `.zip.zip` filename**: this is the genuine upstream ScienceBase filename, confirmed by the ScienceBase API itself (`files[].name == "PADUS4_1SummaryStatistics_TabularData_CSV.zip.zip"`), not a local corruption. The inner content is one ordinary zip (`unzip -l` lists 22 CSV/XML members directly, no nested zip). I renamed the local copy to `PADUS4_1SummaryStatistics_TabularData_CSV.zip` and recorded the rename in `download_log.json`.

## 4. CRS / resolution / coverage

- **Native CRS** (read directly from `PADUS4_1VectorAnalysis_CONUS.gdb` with `pyogrio.read_info`): `ESRI:102039`, *"USA_Contiguous_Albers_Equal_Area_Conic_USGS_version"* — WKT shows `GEOGCS NAD83` (`SPHEROID["GRS 1980",6378137,298.257222101]`, EPSG:4269), Albers Conic Equal Area, `latitude_of_center=23`, `longitude_of_center=-96`, `standard_parallel_1=29.5`, `standard_parallel_2=45.5`, units = metres.
  - These are **exactly** EPSG:5070's defining parameters. I confirmed numerically: reprojecting the Albers origin point `(-96, 23)` from `ESRI:102039` to `EPSG:5070` with `pyproj` returns `(-96.0, 23.0)` — zero distortion. Still, **explicitly reproject to EPSG:5070** with `pyproj`/`geopandas.to_crs` rather than relying on the two authority codes being treated as interchangeable by every tool in the pipeline.
- **Native resolution**: the recommended product is **vector** (polygons), so "resolution" is not applicable in the raster sense — it is exact boundary geometry, 322,263 features. The companion raster (not recommended) is **30 m × 30 m** (confirmed two ways: (a) `RasterizationReport_PADUS4_1CONUS.txt` states *"The output Cell size is: 30 square meters"*; (b) cross-check — the raster's value-attribute-table first record has `Count=54,537,083` pixels and `GIS_Acres=12,128,747`; `54,537,083 × 900 m² = 4.908×10^10 m² ≈ 12,131,858 acres`, matching to within rounding).
- **Spatial coverage**: National/CONUS. I verified the dev-area bbox `[-98.0, 29.0, -93.0, 33.0]` (EPSG:4326) falls entirely inside the layer's `total_bounds` in its native CRS (`(-2,361,582, 252,185)` to `(2,263,786, 3,177,425)` metres) by transforming the four bbox corners with `pyproj` — all land comfortably inside. More strongly: summing the layer's own `GIS_Acres` field over all 322,263 features gives **2,000,691,717 acres ≈ 8,096,221 km²**, matching the commonly-cited conterminous-U.S. land area (~8.08 million km²) to within ~0.2% — strong evidence this single file is a **complete, gap-free partition of all CONUS land** (protected areas *and* a "no known mandate" fill for everything else), not just the protected-area polygons alone. Separate `PADUS4_1_Raster_AK.zip` / `_HI.zip` exist for Alaska/Hawaii if the project ever expands past CONUS; out of scope here.

## 5. Fields / units / codes

All of the following were read directly from `data/raw/usgs_padus/PADUS4_1VectorAnalysis_CONUS.gdb` (`pyogrio.read_info` for the schema, `pyogrio.read_dataframe` for value counts) and/or from `PADUS41_VectorAnalysisFile_MetadataXML.xml` (official FGDC metadata, fully downloaded and parsed — this is the `verified_from` for every domain-code list below unless noted otherwise).

### 5.1 `GAP_Sts` (text, also duplicated as integer `GAP_Sts_cd`)
"GAP Status Code" — measure of management intent to conserve biodiversity. Values, quoted from the metadata XML `edom`/`edomvd` and cross-checked against the fuller text on `usgs.gov/programs/gap-analysis-project/science/pad-us-data-overview` (fetched directly):

| Code | Meaning |
|---|---|
| 1 | "An area having permanent protection from conversion of natural land cover and a mandated management plan in operation to maintain a natural state within which disturbance events ... are permitted to proceed without interference or are mimicked through management." (e.g. Wilderness Areas) |
| 2 | Permanent protection + mandated management plan, but may allow degrading uses/suppression of natural disturbance (e.g. National Wildlife Refuges) |
| 3 | Permanent protection for the majority of the area but subject to extractive uses (logging, OHV, mining) (e.g. National Forests, BLM land) |
| 4 | "No known public or private institutional mandates ... to prevent conversion of natural habitat types to anthropogenic habitat types" — **this is the fill value for everything not otherwise mapped as 1-3**, not a no-data code |

National area sums computed directly from this file (`GIS_Acres` grouped by `GAP_Sts_cd`): GAP1=72,539,170 ac; GAP2=89,248,502 ac; GAP3=338,783,234 ac; GAP4=1,500,120,811 ac. These match the officially-published `PADUS4_1_Raster_CONUS_Stats.txt` (bundled in the same zip) national totals (72,538,953 / 89,248,197 / 338,782,114 / 1,500,116,215 acres respectively) to **<0.01%** — a strong correctness cross-check.

### 5.2 `Des_Tp` — Designation Type of the winning (highest-priority) record
~70 categorical codes read directly from the metadata XML, e.g. `NP`=National Park, `NM`=National Monument, `NF`=National Forest, `WA`=Wilderness Area, `NWR`=National Wildlife Refuge, `WSR`=Wild and Scenic River, `ACEC`=Area of Critical Environmental Concern, `MIL`=Military Land, `CONE`=Conservation Easement, `ND`=Not Designated, `UNK`=Unknown, `OCS`=Outer Continental Shelf Area, `FACY`=Facility, plus state/local/private parallels (`SP`,`SW`,`SCA`,`LP`,`LCA`,`PCON`,`PRAN`, …). Full ~70-value list is in the metadata XML (saved at `/tmp` during research, not committed — re-derivable with one HTTP GET, see §3).

### 5.3 `Pub_Access`
Values (quoted from metadata XML): `OA`="Open" (no special requirements); `RA`="Restricted" (special permit from owner / registration required); `XA`="Closed" (no public access, e.g. land bank, military, many easements); `UK`="Unknown" (information not currently available). Measured national counts (322,263 records): OA=200,013; XA=54,359; UK=43,231; RA=24,660.

### 5.4 `Mang_Type` — managing-agency type
Values (metadata XML): `FED`=Federal, `STAT`=State, `LOC`=Local Government, `DIST`=Regional Agency Special District, `PVT`=Private, `JNT`=Joint, `NGO`=Non-Governmental Organization, `TRIB`=American Indian Lands, `TERR`=Territorial, `UNK`=Unknown. Measured counts: LOC=148,192; STAT=59,711; NGO=37,544; UNK=32,830; FED=17,112; DIST=13,381; PVT=8,560; JNT=4,326; TRIB=607.

### 5.5 `Own_Type` — **not present in the recommended layer**
Confirmed absent by enumerating all 23 fields of `PADUS4_1_VectorAnalysis_CONUS` (`Category, Mang_Type, Mang_Name, Des_Tp, Loc_Ds, Unit_Nm, Agg_Src, Pub_Access, GAP_Sts, IUCN_Cat, FeatClass, GAP_Sts_Prity, MngTp_Desc, MngNm_Desc, STUSPS, NAME, ST_Name, SUM_GIS_AcrsDb, GAP_Sts_cd, JnID, GIS_Acres, Shape_Length, Shape_Area, RastDrop`) — no `Own_Type`. It exists only on the Fee/Easement feature classes inside the separate **Full Inventory Database** (`PADUS4_1Geodatabase.zip`), confirmed via the ScienceBase item page's text (field list stated: "GAP_Sts, Des_Tp, Own_Type, Mang_Type, Pub_Access"). That file is CAPTCHA-gated (§6) and was **not** downloaded or opened by this agent, so I cannot state its exact `Own_Type` domain codes from direct inspection — **UNVERIFIED**, mark as such if quoted elsewhere (historical PAD-US versions used codes like FED/STAT/LOC/PVT/NGO/JNT/TRIB/UNK, similar to `Mang_Type`, but I have not confirmed this for 4.1).

### 5.6 Other available but not explicitly requested fields
`Category`/`FeatClass` (which original PAD-US feature class the winning polygon came from: Fee=223,929–227,958 records / Easement=82,375 / Designation=10,322–10,487 / Proclamation=1,394 / blank or "Unknown"=~80 — counts differ slightly between the two because `Category` is blank, not "Fee", for some fill records); `RastDrop` (1 = flagged and excluded from USGS's own raster because an overlap tie could not be resolved — **only 178 acres nationally** out of 2,000,691,717, i.e. ~9×10⁻⁸ of total area, despite being ~4.7% of *records*; recommend excluding these to match USGS's own published statistics, which I confirmed reproduces the official totals almost exactly); `GAP_Sts_Prity`/`GAP_Prity` (integer priority rank used to break overlap ties — exact rank table not independently re-verified, UNVERIFIED); `IUCN_Cat` (IUCN management category, often blank for U.S. designations); `GIS_Acres`/`SUM_GIS_AcrsDb`/`Shape_Area`/`Shape_Length` (pre-computed area/length in the source CRS; `Shape_Area` units are inferred to be square metres from the projected CRS's linear unit, not independently documented in the metadata XML's attribute block — **recommend recomputing exact intersection area from geometry after reprojection** rather than trusting these whole-polygon pre-computed fields, since Phase 2 needs intersection-with-grid-cell areas, not whole-polygon areas, anyway).

### 5.7 Missing/no-data semantics (important for AGENTS.md §3.3 "UNKNOWN is never zero")
Within this layer, `UNK`/`Unknown`/blank values in `Mang_Type`, `Pub_Access`, `Category` are **observed PAD-US attribution gaps** (the source explicitly recorded "we don't know this attribute for this real polygon") — they are not missing geometry, and should be carried through as `status: observed` with the raw code preserved, not silently collapsed into the project's generic `unknown`/`missing_reason` convention. True **UNKNOWN**, in this project's sense, should apply only to any grid-cell area that falls **outside this layer's polygon coverage entirely** — given the file appears to be a gap-free CONUS land partition (§4), this should be rare/zero over land and is not fully characterized for inland water bodies (see Open Questions).

## 6. License

Public Domain. Quoted directly from the ScienceBase API (`rights` field, item `652d4fc5d34e44db0e2ee45e`):
> "Public Domain. Unless otherwise stated, all data, metadata and related materials are considered to satisfy the quality standards relative to the purpose for which the data were collected. Although these data and associated metadata have been reviewed for accuracy and completeness and approved for release by the U.S. Geological Survey (USGS), no warranty expressed or implied is made regarding the display or utility of the data for other purposes, nor on all computer systems, nor shall the act of distribution constitute any such warranty."

Standard USGS no-warranty/no-liability disclaimer; not a usage restriction. No attribution is legally required, though citing the DOI (§1) is good practice and is what `download_log.json` records.

## 7. Access requirements

- **The recommended product (already acquired)**: plain public HTTPS GET, no login, no form, no click-through terms, no CAPTCHA, no API key. Verified by direct `curl -sI` (200, correct `Content-Length`/`Content-Type`) and by the fact the local files' MD5s match ScienceBase's published checksums exactly.
- **The CAPTCHA-gated files** (`PADUS4_1Geodatabase.zip` / Full Inventory — needed only for literal `Own_Type`; `PADUS4_1VectorAnalysis_PADUS_Only.zip`; `PADUS4_1VectorAnalysis_OtherExtents.zip`): these three are hosted on ScienceBase's newer S3-backed storage. Their `"url"`/`"downloadUri"` fields both resolve to `https://sciencebase.usgs.gov/manager/...`, which serves the **ScienceBase File Manager**, a JavaScript single-page app, not file bytes (confirmed: `curl` returns a 4,255-byte HTML/JS shell regardless of `cuid`, even with `-L` and with a ranged GET). The JSON also exposes `"s3DownloadRequestPageUri": ".../catalog/item/requestDownload/<id>?filePath=__s3__"`; fetching that page returns an HTML document titled **"Captcha check - ScienceBase-Catalog"** (a Google reCAPTCHA gate) — confirmed by direct `curl` GET of that exact URL.
  - Per this project's data-access policy (AGENTS.md §4) and this agent's instructions, **I did not attempt to solve or bypass this CAPTCHA, log in, or impersonate a browser.** These three files are marked **BLOCKED for automated access**.
  - **Manual acquisition path** (for a human): open `https://www.sciencebase.gov/catalog/item/652d4fc5d34e44db0e2ee45e` (or the Vector-Analysis item `6759b69fd34edfeb8710a3ea` for the other two) in an ordinary browser — no account/sign-in needed, the data is public — click the file's "Download" button, complete the one-time reCAPTCHA, save to `data/raw/usgs_padus/manual/`.
  - Given the already-acquired flattened CONUS layer independently reproduces the official national GAP-status totals (§5.1), **this blocked file is only needed if the project later decides it must have the literal `Own_Type` field** rather than the already-available `Mang_Type` proxy (see Open Questions).
- No credentials/API keys are involved anywhere in this source.

## 8. Recommended aggregation method

1. **Use the already-dissolved layer, don't dissolve it yourself.** `PADUS4_1VectorAnalysis_CONUS.gdb` → `PADUS4_1_VectorAnalysis_CONUS` is *already* the flattened "combined, overlap-removed-by-priority" product the task asks for (USGS's own documented methodology: overlaps are resolved by GAP Status Code priority, then public-access value, then geodatabase load order — see §2). **Exclude `RastDrop == 1`** records first (178 acres nationally, negligible) to exactly match USGS's own published statistics.
2. **Reproject** the layer from `ESRI:102039` to `EPSG:5070` with `pyproj`/`geopandas.to_crs` (negligible distortion expected given identical defining parameters, §4) so it matches the project's grid CRS exactly.
3. **Area-weighted polygon overlay** (e.g. `geopandas.overlay(grid, padus, how="intersection")`, spatial-indexed) between the 10 km grid cells and this polygon layer — **not** the 30 m raster, and **not** centroid/nearest-distance sampling, because the task needs true area fractions and the source is categorical/irregular-boundary by nature.
4. Per grid cell, compute `area_frac = intersection_area_m2 / cell_area_m2`, grouped by `GAP_Sts` (1/2/3/4 — should sum to ~1.0 per cell since the source is a gap-free CONUS partition), and optionally by `Pub_Access` and `Mang_Type` using the same intersection (no extra overlay cost). Recompute areas from geometry after reprojection rather than trusting the source's pre-computed `GIS_Acres`/`Shape_Area` (those are whole-polygon areas, not per-cell intersection areas).
5. **Record, per AGENTS.md §3.3/§6**: `padus_n_source_polygons` (count of distinct source polygons intersected — directly satisfies "when a cell intersects multiple source regions, record that fact"), a `padus_mapped_coverage_frac` (sum of all GAP_Sts fractions; should be ≈1.0 — any shortfall is the signal for true `UNKNOWN`, not zero), native resolution = "vector, exact geometry", aggregation method = "area-weighted polygon overlay, overlaps pre-resolved by USGS priority rule", status = `observed`.
6. **`Own_Type` (if later required)**: overlay the separate Full Inventory's `Fee` and `Easement` feature classes *independently* against the grid (each is individually low-overlap per USGS's own guidance — "while minor boundary discrepancies remain... this is the best source for overall land area calculations by land manager"). Treat these results as a **separate, independently-overlapping** feature set — they can legitimately coexist with (and are not additive to) the GAP-status fractions from step 4, since a cell can simultaneously be e.g. 80% `Own_Type=FED` (from Fee) **and** 80% `GAP_Sts=1` (from an overlapping Wilderness Designation on top of that same Federal fee land). Document this non-additivity explicitly in the data dictionary so the Phase 2/model layer never sums across these two independent breakdowns.
7. **Volume/memory** (see §9 for numbers): process nationally in spatial chunks (e.g. by state, using `STUSPS`/`ST_Name`, which are already fields on this layer) to stay within the project's ~4 GB per-process budget; the dev-area bbox needs no chunking at all.

## 9. Volume and memory estimate

- **Disk, already on hand**: 744 MB (`PADUS4_1_Raster_CONUS.zip`, kept as-is/not re-extracted in full) + 4 MB (CSV stats zip) + 422 MB (extracted `PADUS4_1VectorAnalysis_CONUS.gdb`) ≈ **1.17 GB total**, well under the 12 GB pre-download budget. No further download is required for the core deliverable.
- **Avoid**: fully extracting the raster payload inside `PADUS4_1_Raster_CONUS.zip` needs **~79 GB** free disk (60,176,270,877-byte `.ige` + 18,808,206,082-byte `.rde` + 1,262,097,172-byte `.rrd`, all highly compressible in the zip at ~100:1 but not on disk once extracted) — unnecessary, since the vector layer is both smaller and the better-suited product.
- **Dev area** (`[-98.0, 29.0, -93.0, 33.0]`, ≈ 212,000 km² ≈ **~2,100–2,300** 10 km cells by rough estimate): the PAD-US layer subset intersecting this bbox is a small fraction of the national 322,263 features; overlay should run in well under 1 GB RAM and take seconds to a couple of minutes on a laptop with a spatial index.
- **National** (CONUS land area ≈ 8.08 million km² ≈ **~80,000–81,000** 10 km cells, exact count depends on `configs/grid.yaml`, which this agent did not touch): loading the full 322,263-feature, 422 MB `PADUS4_1_VectorAnalysis_CONUS` layer into GeoPandas is estimated at roughly 1–2 GB RAM (schema + geometries). Recommend chunked/tiled processing (by state or grid row-band) per AGENTS.md §7's "~4 GB per process" and "windowed/chunked" rules rather than one single national overlay call; a per-state loop (reusing the layer's own `STUSPS` field to pre-filter) is the simplest chunking key.

## 10. Interpretation limits

- GAP Status Code measures management **intent**, not measured ecological condition or conservation effectiveness — GAP 1–3 are all "permanently protected from conversion" to differing degrees; GAP 4 means "no known protective mandate" (a default/fill value), not "destroyed land" or literally zero ecological value.
- These fractions are a proxy for conservation/permitting friction and co-located ecological sensitivity — not a direct predictor of permitting timelines, environmental-review outcomes, or site buildability (per AGENTS.md §3.5, proxies are not facts).
- USGS explicitly discourages comparing PAD-US versions over time to infer real-world protection change, since most inter-version differences reflect mapping/attribution improvements rather than new acquisitions or protections — relevant if any future feature tries to use PAD-US "trend."
- PAD-US is an aggregated, agency-submitted inventory; USGS's own `PAD_US_Fee_Topology` service documentation notes boundary topology mismatches can occur between adjoining agencies' independently-submitted polygons.
- This source says nothing about regulatory/permitting process timelines, state/local zoning, or non-PAD-US conservation easements that were never submitted to USGS.

## 11. Pitfalls

1. **Do not extract the raster.** The bundled 30 m raster needs ~79 GB of disk once decompressed; the bundled vector layer (422 MB) is both smaller and the right product for area fractions.
2. **`RastDrop` records are numerous but area-negligible.** 15,211 of 322,263 records (4.7% of *records*) are flagged, but they total only 178 of 2,000,691,717 acres nationally. Exclude them (matching USGS's own raster convention) rather than treating 4.7% as a material data gap.
3. **`Own_Type` is not in the recommended layer**; it requires the CAPTCHA-gated Full Inventory Database (§6/§7). `Mang_Type` (available now) is a reasonable but *conceptually distinct* documented proxy — label it `status: proxy`, not `observed`, if substituted for `Own_Type`.
4. **Native CRS is `ESRI:102039`, not literally `EPSG:5070`** — parameters are numerically identical (verified), but always reproject explicitly rather than assuming every tool treats the two authority codes as interchangeable.
5. **`UNK`/`Unknown`/blank codes are an observed PAD-US attribution gap**, not a missing-geometry/no-data gap — don't conflate with the project's `unknown` value-status.
6. **`Des_Tp` has ~70 distinct codes** — a per-cell one-hot of all of them is likely too granular; needs a deliberate grouping decision before it becomes wide-table columns (flagged as an open question, not decided here, since that is a schema/design choice for the Phase 2 implementer, not a geography-recon fact).
7. **The doubled `.zip.zip` filename is real upstream naming**, not a local download bug — confirmed via the ScienceBase API itself.
8. GAP_Sts fractions should sum to ≈1.0 per cell (gap-free CONUS partition, §4) — a shortfall is the signal to use for true `UNKNOWN`, but inland-water handling within that partition was not exhaustively verified (see Open Questions).

## 12. Open questions

1. Should literal `Own_Type` be acquired via a one-time **manual** browser download of the CAPTCHA-gated `PADUS4_1Geodatabase.zip` (1.42 GB), or is the already-available `Mang_Type` an acceptable documented proxy for this project's purposes?
2. How should the Phase 2 wide feature table encode the ~70-value `Des_Tp` domain — full one-hot, a curated smaller taxonomy, or "top category by area per cell"? Left to the Phase 2 schema designers; this is a geography-adapter design choice, not a sourcing fact.
3. Does `PADUS4_1_VectorAnalysis_CONUS`'s CONUS-land-area-matching "fill" include or exclude inland water bodies (Great Lakes, large reservoirs)? Not exhaustively verified polygon-by-polygon in this session — matters for correctly distinguishing true `UNKNOWN` (open water / outside coverage) from genuine `GAP_Sts=4` fill.
4. Should `RastDrop == 1` polygons be silently excluded (this report's recommendation, matching USGS's own raster convention and reproducing official totals) or retained with an explicit lower-confidence flag instead?

## 13. Files in this repository

- `data/raw/usgs_padus/PADUS4_1_Raster_CONUS.zip` (744,032,421 bytes) — verified complete, not re-downloaded
- `data/raw/usgs_padus/PADUS4_1SummaryStatistics_TabularData_CSV.zip` (4,086,817 bytes; renamed from the upstream `....zip.zip`) — verified complete, not re-downloaded
- `data/raw/usgs_padus/PADUS4_1VectorAnalysis_CONUS.gdb/` (441,838,654 bytes, 63 files) — extracted in this session from the verified raster zip; **this is the recommended Phase 2 input**
- `data/raw/usgs_padus/download_log.json` — full provenance for all of the above
- `docs/research/phase2/usgs_padus.md` — this report
