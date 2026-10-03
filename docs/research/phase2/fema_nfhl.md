# FEMA National Flood Hazard Layer (NFHL) — Phase 2 source reconnaissance

`source_id`: `fema_nfhl`
Researched: 2026-10-02 (local session date); all HTTP verifications below carry the
server-observed UTC timestamp (FEMA responses were stamped `2026-10-03T02:0x:xxZ`,
i.e. the same calendar session, UTC a few hours ahead of local date).
Status recommendation: **PARTIAL** — see §6 Access.

This report is reconnaissance only. No code, config, or `docs/*.md` other than this file
was touched. Nothing was pre-downloaded (see §6/§8 for why) — `data/raw/fema_nfhl/` was not
created.

---

## 1. Product / version

- **Dataset**: National Flood Hazard Layer (NFHL) — FEMA's seamless GIS compilation of
  effective Flood Insurance Rate Map (FIRM) databases and Letters of Map Change (LOMC),
  built to support the National Flood Insurance Program (NFIP).
- **Not a fixed-vintage dataset.** NFHL has no single "data year": it is continuously
  revised as individual communities get new/updated FIRMs. The FGDC metadata record's own
  `<update>` tag reads **`Monthly`** (verified by fetching and parsing
  `NFHL_metadata.xml` directly). A secondary, *unverified* claim surfaced by web search
  (not independently confirmed by fetching FEMA's own FAQ text) says state-level MSC
  extracts refresh biweekly and county/community extracts daily — treat that cadence as
  **UNVERIFIED**.
  - Directly verified via a live `outStatistics` query on `S_FIRM_PAN.EFF_DATE`
    (layer 3): the oldest *still-effective* FIRM panel nationally has `EFF_DATE =
    1981-10-06`. The reported maximum was an out-of-range sentinel value
    (`253392451200000` ms since epoch — not a valid calendar date), i.e. a placeholder/
    dirty value, not a real future effective date.
  - The FGDC metadata record itself has `pubdate = 2015-01-30`; that is the metadata
    document's authoring date, not the data vintage.
- **Effective vs. preliminary**: the public MapServer used here (`public/NFHL`) serves
  **effective data only**. FEMA's own page states preliminary data is a distinct product
  ("Before they become effective, the preliminary products go through a formal review
  period…") with its own viewer — verified by fetching
  `https://www.fema.gov/flood-maps/national-flood-hazard-layer` directly and reading the
  page text (quoted briefly above, under 15 words per excerpt, per copyright limits).
- **Publisher**: Federal Emergency Management Agency, Washington, D.C. (`origin`/`publish`
  tags in the FGDC record).

## 2. Endpoints (verified)

All rows below were checked today with `curl -I` (HEAD) or a ranged/small GET and
returned the HTTP status and `Content-Length` shown. Everything in this table returned
2xx/3xx.

| # | URL | Method | Status | Content-Length / notes |
|---|---|---|---|---|
| 1 | `https://hazards.fema.gov/arcgis/rest/services/public/NFHL/MapServer?f=json` | HEAD | 200 | 9,520 B — service root, `currentVersion 11.1`, 32 feature layers, `maxRecordCount: 2000` |
| 2 | `https://hazards.fema.gov/arcgis/rest/services/public/NFHL/MapServer/28?f=json` | HEAD | 200 | 52,139 B — layer 28 = **Flood Hazard Zones** (`S_FLD_HAZ_AR`) |
| 3 | `https://hazards.fema.gov/arcgis/rest/services/public/NFHL/MapServer/3?f=json` | GET | 200 | 6,563 B — layer 3 = **FIRM Panels** (`S_FIRM_PAN`) |
| 4 | `https://hazards.fema.gov/arcgis/rest/services/public/NFHL/MapServer/0?f=json` | GET | 200 | 4,185 B — layer 0 = **NFHL Availability** (coarse "is this area studied at all" polygon) |
| 5 | `https://hazards.fema.gov/arcgis/rest/services/public/NFHL/MapServer/4?f=json` | GET | 200 | 4,777 B — layer 4 = **Base Index** |
| 6 | `https://hazards.fema.gov/arcgis/rest/services/public/NFHL/MapServer/22?f=json` | GET | 200 | layer 22 = **Political Jurisdictions** (`ST_FIPS`, `CO_FIPS`, `DFIRM_ID` join key) |
| 7 | `https://hazards.fema.gov/arcgis/rest/services/public/NFHL/MapServer/28/query?...` | GET (ranged 0-1023 also tried) | 200 | sample attribute+count queries all 200; see §8 for one that **timed out** (not in this table) |
| 8 | `https://hazards.fema.gov/filedownload/metadata/NFHL/NFHL_metadata.xml` | HEAD | 200 | 40,159 B — FGDC/CSDGM metadata record (license text, update cadence) |
| 9 | `https://www.fema.gov/flood-maps/national-flood-hazard-layer` | GET | 200 | official documentation/landing page |
| 10 | `https://www.fema.gov/sites/default/files/documents/fema_rm-firm-database-technical-reference-nov-2024.pdf` | HEAD | 200 | 2,081,162 B — **FIRM Database Technical Reference, Nov 2024** (latest; data dictionary, field specs, Table 14 zone/subtype cross-walk) |
| 11 | `https://www.fema.gov/sites/default/files/2020-02/FIRM_Database_Technical_Reference_Feb_2019.pdf` | HEAD | 200 | 1,460,539 B — same reference, older (Feb 2019) edition, still live |
| 12 | `https://www.fema.gov/sites/default/files/2020-02/NFHL_Guidance_Feb_2019.pdf` | HEAD | 200 | 417,340 B — NFHL Guidance |
| 13 | `https://catalog.data.gov/dataset/national-flood-hazard-layer` | HEAD | 200 | 114,740 B — data.gov catalog entry; license link `https://www.usa.gov/government-works`; "last updated April 01, 2025" per catalog record |
| 14 | `https://msc.fema.gov/portal/home` | HEAD | 200 | FEMA Map Service Center landing page |
| 15 | `https://msc.fema.gov/portal/advanceSearch` | HEAD/GET | 200 | 199,118 B — interactive search UI (JS/AJAX app; see §6, not a static download) |
| 16 | `https://msc.fema.gov/nfhl` | HEAD | 302 | redirects into the NFHL interactive viewer |
| 17 | `https://www.fema.gov/about/organization/region-6/available-flood-hazard-data-tables-texas` | HEAD | 200 | FEMA Region 6 "Available Flood Hazard Information" (AFHI) table page for TX (quarterly PDF/XLSX of effective/preliminary/work-map status by community; not a GIS size source) |
| 18 | `https://www.fema.gov/about/organization/region-6/available-flood-hazard-data-tables-louisiana` | HEAD | **503** | consistently returned Service Unavailable on retry — **not verified reachable today**; not relied on for any fact in this report |
| 19 (negative controls) | `https://hazards.fema.gov/nfhlv2/output/National/NFHL_National.gdb.zip`, `https://hazards.fema.gov/nfhlv2/output/State/NFHL_48_20261001.zip` | HEAD | 404 | confirms no guessable static bulk-file URL exists at these plausible paths (see §6) |

## 3. CRS / resolution / coverage

- **Native CRS**: every layer's `extent.spatialReference` reports **`wkid 4269`
  (NAD83 geographic, EPSG:4269)** — i.e. unprojected lat/lon on the NAD83 datum, not
  EPSG:4326 and not already projected. Must be explicitly reprojected to EPSG:5070; do not
  relabel 4269 as 4326 (they are close but not identical).
- **Native resolution**: vector polygon data; "resolution" is expressed through FIRM
  mapping/base-map scale, carried per panel in the `SCALE` text field on `S_FIRM_PAN`
  (exact distinct values not enumerated in this pass — **UNVERIFIED**, low priority).
- **Coverage, population basis (verified quote)**: FEMA states NFHL "digital data covers
  over 90% of the U.S. population" — fetched directly from the official page.
- **Coverage, area/county basis (directly measured, imperfect proxy)**: querying
  `Political Jurisdictions` (layer 22) for distinct `DFIRM_ID` values gives **139** for
  `ST_FIPS='48'` (Texas, which has 254 counties) and **52** for `ST_FIPS='22'` (Louisiana,
  64 parishes). This is **not** a clean "percent of counties mapped" figure — one
  `DFIRM_ID` study can cover several incorporated places inside one county, and some
  studies are multi-jurisdiction — but it directly demonstrates that area/county coverage
  is well below 100% and must never be assumed complete.
- **Dev bbox** `[-98.0, 29.0, -93.0, 33.0]` (EPSG:4326): spans most of the Texas Gulf
  coast (Corpus Christi/Houston/Beaumont corridor) and western/central Louisiana; it does
  **not** reach New Orleans or the easternmost Louisiana coast (≈ −90°), and only grazes
  southern Arkansas at its northeast corner. Verified **3,481** effective FIRM panels
  intersect this bbox (fast query, 0.2 s). A direct feature count of hazard-zone polygons
  (`S_FLD_HAZ_AR`) inside the full bbox could **not** be obtained — see §8/§10 for the
  timeout. No official statement exists that the dev bbox is 100%-mapped; unmapped slivers
  must be detected per cell at run time, never assumed.
- **National**: FEMA does not publish one seamless national file (see §6); coverage must
  be assembled from 50 states + DC + PR (+ territories) extracts, or queried live
  per-area from the REST service.

## 4. Fields / units / codes

Primary layer for the hazard features: **`S_FLD_HAZ_AR`, MapServer layer id `28`**
("Flood Hazard Zones"), geometry = polygon, 24 fields, `maxRecordCount 2000`,
`spatialReference wkid 4269`. Key fields (verified from the live layer's field list,
cross-checked against the FIRM Database Technical Reference, Nov 2024):

| Field | Type | Meaning | Verified values / notes | `verified_from` |
|---|---|---|---|---|
| `FLD_ZONE` | string(17) | Flood zone code | Live distinct values today: `A, A99, AE, AH, AO, D, OPEN WATER, V, VE, X`. `AR` is a real, documented FEMA code but returned **0 features nationwide** (`where FLD_ZONE='AR'` → `count:0`) — defined but currently empty, do not assume populated. | live REST distinct-value + count query, 2026-10-02; cross-checked against FIRM DB Technical Reference field spec |
| `ZONE_SUBTY` | string(76) | Flood zone subtype | Free-text but drawn from a controlled list; 78 distinct `(FLD_ZONE, ZONE_SUBTY, SFHA_TF)` combinations observed nationwide today. See grouped list below. | live REST `returnDistinctValues` query, 2026-10-02 |
| `SFHA_TF` | string(1) | "In a Special Flood Hazard Area" flag | **Three** observed values: `T` (true), `F` (false), **`U`** (undetermined) — not strictly binary. `U` occurs on `OPEN WATER` and even on some `X;AREA OF MINIMAL FLOOD HAZARD` records. | live REST distinct-value query, 2026-10-02 |
| `STATIC_BFE` | double | Base Flood Elevation (feet, vertical datum per `V_DATUM`) | no national summary pulled; `-9999`-style sentinel for n/a is typical of this FEMA field family — **UNVERIFIED exact sentinel for this layer**, confirm per-panel before trusting literal 0/negative values | field list only |
| `DEPTH` / `VELOCITY` | double | Flood depth (ft, AO zones) / velocity | units per `LEN_UNIT`/`VEL_UNIT` sibling fields (both present on the layer) | field list only |
| `DFIRM_ID` | string(6) | Study-area identifier | Observed convention (inferred, not in the spec text I pulled): `ST_FIPS`(2) + `CO_FIPS`(3) + check letter, e.g. `48179C` = Gray County, TX. Cross-checked against `Political Jurisdictions` sample rows for TX and LA only — **open question** whether this always holds (e.g. joint multi-county/cross-state studies). | sample query against layers 22 and 28/3, 2026-10-02 |
| `SOURCE_CIT` | string(21) | Citation key into the FIRM database's source-citation table | not resolved in this pass | field list only |

**Grouped `ZONE_SUBTY` categories** (from the live layer's own cartographic
`uniqueValueInfos`, i.e. FEMA's own grouping of the raw strings — more reliable than a
hand-written substring match):

- **1% Annual Chance Flood Hazard** (the SFHA, 55 raw combos) — `FLD_ZONE` in
  `{A, AE, AH, AO, A99, V, VE}` with `ZONE_SUBTY` typically `<Null>`/blank or a
  descriptor like `COASTAL FLOODPLAIN`, `AREA WITH FLOOD HAZARD DUE TO LEVEE SYSTEM`,
  etc. `SFHA_TF='T'` in every nationwide sample row seen.
- **Regulatory Floodway** (19 raw combos, all `SFHA_TF` mostly `T`, one `F` variant seen)
  — `ZONE_SUBTY` containing any of: `FLOODWAY`, `FLOODWAY CONTAINED IN CHANNEL`,
  `FLOODWAY CONTAINED IN STRUCTURE`, `ADMINISTRATIVE FLOODWAY`,
  `COMMUNITY ENCROACHMENT AREA`, `STATE ENCROACHMENT AREA`, `FLOWAGE EASEMENT AREA`,
  `NARROW FLOODWAY`, `RIVERINE FLOODWAY SHOWN IN COASTAL ZONE`,
  `RIVERINE FLOODWAY IN COMBINED RIVERINE AND COASTAL ZONE`. A naive
  `ZONE_SUBTY = 'FLOODWAY'` equality check **undercounts** — use this full set.
- **Special Floodway** (4 combos; `AE;AREA OF SPECIAL CONSIDERATION`,
  `AE;COLORADO RIVER[,] FLOODWAY`, `AE;DENSITY FRINGE AREA`) — a Colorado-River-specific
  regulatory variant, not expected in the TX/LA/AR dev area.
- **0.2% Annual Chance Flood Hazard** (15 combos) — `FLD_ZONE='X'` with `ZONE_SUBTY`
  matching `0.2 PCT ANNUAL CHANCE FLOOD HAZARD` (and its `...CONTAINED IN CHANNEL` /
  `...CONTAINED IN STRUCTURE` / `...IN COASTAL ZONE` / `...IN COMBINED RIVERINE AND
  COASTAL ZONE` variants, plus `1 PCT DRAINAGE AREA LESS THAN 1 SQUARE MILE` and
  `1 PCT DEPTH LESS THAN 1 FOOT`, and `AREA WITH FLOOD HAZARD DUE TO NON-ACCREDITED LEVEE
  SYSTEM`). **This confirms the exact string the task description named**
  (`'0.2 PCT ANNUAL CHANCE FLOOD HAZARD'`) is a real, currently-used value.
- **Future Conditions 1% Annual Chance Flood Hazard** (6 combos) — `FLD_ZONE='X'`,
  `ZONE_SUBTY` containing `FUTURE CONDITIONS` — a forward-looking but still-regulatory
  category; keep separate from both the current SFHA and the 0.2% bucket.
- **Area with Reduced / Area with Risk Due to Levee** (6 combos total) — levee-interacted
  zones, split across `X` (reduced risk, non/provisionally-accredited or accredited
  levees) and `D` (undetermined due to levee).
- **Area of Undetermined Flood Hazard** — `FLD_ZONE='D'`, `ZONE_SUBTY` null/blank, plus the
  levee-related `D` combos above. This sits *inside* an effective FIRM panel but the
  hazard itself is **not determined** — must be treated as unknown/undetermined for
  hazard-fraction purposes, not as "mapped, zero risk."
- Not drawn by FEMA's own symbology (and therefore absent from the renderer list, but
  confirmed present as real attribute data via direct distinct-value query):
  `FLD_ZONE='X', ZONE_SUBTY='AREA OF MINIMAL FLOOD HAZARD'` (`SFHA_TF` one of `F`/`T`/`U`
  — the `T` and `U` occurrences on a nominally "minimal hazard" zone are a data-quality
  oddity worth defensive handling) and `FLD_ZONE='OPEN WATER'`.
- `ZONE_SUBTY = 'AREA NOT INCLUDED'` (named in the task prompt) returned **0** matches
  live (`count:0`, both exact and `LIKE '%NOT INCLUDED%'`). It instead appears as
  free-text in the **FIRM Panel** layer's `PNP_REASON` field (e.g. `"ALL AREA NOT
  INCLUDED"`, `"CITY OF PORTLAND (AREA NOT INCLUDED)"`) on panels whose `PANEL_TYP`
  contains "Not Printed" — i.e., in current data this concept is a panel-level gap, not a
  queryable hazard-zone attribute.

**`S_FIRM_PAN`, layer id `3`** ("FIRM Panels" — the effective-map-extent layer):
`DFIRM_ID`, `PANEL`, `SUFFIX`, `FIRM_PAN`, `PANEL_TYP`, `PRE_DATE`/`EFF_DATE` (dates),
`SCALE`, `BASE_TYP` (`NP` / `Orthophoto` / `Vector`), `PNP_REASON` (free text, 548
distinct values sampled). `PANEL_TYP` distinct values observed: `Countywide, Panel
Printed`, `Countywide, Not Printed`, `Statewide, Panel Printed`, `Statewide, Not
Printed`, `Community Based, Panel Printed`, `Community Based, Not Printed`, plus one
dirty value `Countywide, Panel Printed'` (stray trailing apostrophe — normalize
defensively). **"Not Printed" does not mean unmapped** — most "Not Printed" panels exist
because there is no SFHA to show, the area is all open water, or all Zone D/X; the panel
and its hazard determination are still part of the effective, mapped extent.

**NFHL Availability, layer id `0`**: single field `STUDY_ID` (6-char, same pattern as
`DFIRM_ID`) — large, simple polygons, one per study area; cheapest layer to query first
for a coarse "is anything studied here at all" pre-filter before paying for the much
heavier `S_FLD_HAZ_AR` overlay.

**Political Jurisdictions, layer id `22`**: `ST_FIPS`, `CO_FIPS`, `DFIRM_ID`, `POL_NAME1/2/3`,
`CID`, `COMM_NO`, `ANI_TF` — the join key set for scoping any of the above by state/county.

## 5. License

- FGDC metadata `<useconst>` (quoted, fetched directly, under the 15-word/response
  copyright-quoting limit used verbatim here as a short citation): *"Acknowledgement of
  FEMA would be appreciated in products derived from these data."* The same field states
  the hardcopy FIRM/FIS remains the official NFIP determination and that only FEMA can
  change it through NFIP regulatory mechanisms (44 CFR Parts 59–78) — a usage caveat, not
  a legal restriction on redistribution.
- `<accconst>` (access constraints): **`None`**.
- `catalog.data.gov` lists the dataset's license as **`https://www.usa.gov/government-works`**
  — the standard "works of the U.S. Government are generally not subject to copyright"
  statement.
- No click-through license, API key, or login was encountered on any endpoint actually
  queried (REST API or documentation).

## 6. Access

Three candidate paths were compared, as requested:

1. **ArcGIS REST MapServer** (`https://hazards.fema.gov/arcgis/rest/services/public/NFHL/MapServer`)
   — **public, no key/login/CAPTCHA**, verified working for metadata and query calls
   against every layer tested (0, 3, 4, 22, 28). `maxRecordCount = 2000` at both the
   service root and every layer (verified) — any single query beyond 2000 matching
   features truncates and sets `exceededTransferLimit:true`; must page with
   `resultOffset`. No `X-RateLimit-*` or similar header was observed on any response, so
   there is no documented *formal* rate limit — but large spatial queries have a real,
   observed *cost* limit (§8/§10). Best fit for: the dev area, bounded tiles, and
   spot-checks; **not** recommended for a from-scratch national mirror (see §8).
2. **Per-state/county download via FEMA Map Service Center**
   (`https://msc.fema.gov/portal/advanceSearch`) — the search UI itself returns HTTP 200
   and is a plain page, but it is a client-rendered app whose download links
   (`downloadProduct`, `downloadAllProductsData`, found as JS hooks in the page source)
   are generated by session-bound AJAX calls, not stable static URLs. No public,
   guessable, stable per-state URL pattern could be found (two plausible guesses at
   `hazards.fema.gov/nfhlv2/output/...` both returned `404`, verified). Per this task's
   instructions not to script interactive forms, **this path was not automated**; it is
   documented here as the manual path: open the Advance Search page → Jurisdiction →
   State = Texas (or Louisiana) → product "NFHL Data – State" → click the download icon.
   Output is a ZIP containing an Esri File Geodatabase + FGDC metadata XML (per FEMA's own
   page text). **No account, login, payment, or CAPTCHA was observed on this page** — it
   is a plain search form, not an auth wall — but it cannot be driven by a handful of
   `curl` calls, so exact TX/LA ZIP byte sizes are **UNVERIFIED** (see §9 open questions).
3. **Single national geodatabase file** — **not found**. `catalog.data.gov`'s own
   "download" link points back to `msc.fema.gov/nfhl` (the interactive viewer), not a
   file. Two guessed bulk-file URLs both 404'd (verified today). This is consistent with
   independent third-party research (a public GitHub issue investigating exactly this
   question, cited for context only, not relied on as a primary fact) concluding FEMA
   does not publish one seamless national NFHL file and that a national mosaic has to be
   assembled from the 50-state+DC+PR per-jurisdiction downloads.

**Recommended overall source status: `PARTIAL`.** The REST API fully covers bounded
(dev-area / tiled) acquisition with no manual step. National-scale acquisition requires
either (a) a one-time manual per-state download through the MSC search form (52
jurisdictions) — consistent with AGENTS.md's "implement a local-file input path
(`data/raw/fema_nfhl/manual/<ST>/`) and document exact manual-acquisition steps" — or (b)
a large number of paced REST calls, which this report recommends against doing as an
unattended bulk mirror (see §8).

## 7. Recommended aggregation

- Reproject `S_FLD_HAZ_AR`/`S_FIRM_PAN` geometry from EPSG:4269 to EPSG:5070 once per
  batch/tile (keep 4269 explicit in provenance; do not relabel it 4326).
- Per grid cell, via **area-weighted vector overlay** (not centroid sampling, per the
  master prompt's explicit prohibition on assigning hazard data from a centroid alone):
  - `frac_mapped` = area(cell ∩ union of `S_FLD_HAZ_AR` polygons, equivalently the
    effective `S_FIRM_PAN` footprint) / cell area. Recommend reconciling both layers'
    footprints (take the union) since minor edge mismatches between panel neatlines and
    hazard-zone polygon extents are expected.
  - `frac_sfha_1pct` = area where `FLD_ZONE` ∈ `{A, AE, AH, AO, A99, AR, V, VE}` **and**
    `SFHA_TF='T'`, divided by cell area.
  - `frac_0_2pct` = area where `FLD_ZONE='X'` and `ZONE_SUBTY` matches the verified
    0.2%-annual-chance combo list (§4), divided by cell area.
  - `frac_floodway` = area where `ZONE_SUBTY` matches the verified 19-value "Regulatory
    Floodway" set (§4), divided by cell area.
  - `frac_undetermined` = area where `FLD_ZONE='D'` **or** `SFHA_TF='U'`, divided by cell
    area — report distinctly; fold into the cell's UNKNOWN/undetermined accounting even
    though it is technically inside the mapped extent (AGENTS.md: UNKNOWN is never zero).
  - `unmapped_fraction = 1 - frac_mapped` drives the cell's `missing_reason`/`UNKNOWN`
    status for anything not falling in a studied area; never backfilled as zero hazard.
- When a cell's geometry intersects more than one `DFIRM_ID` study area, record
  `n_source_regions` and the list of intersecting `DFIRM_ID`s (a plain spatial join
  naturally produces one row per cell×region before the area-weighted collapse) — this is
  the master prompt's "when a cell intersects multiple source regions, record that fact."
- **Do not loop the live REST API per grid cell** (AGENTS.md explicitly bans per-cell HTTP
  requests). Instead:
  - *Dev area*: pull `S_FLD_HAZ_AR`/`S_FIRM_PAN` once via a handful of tiled bbox queries
    sized to stay safely under the 2000-record cap (the measured density — 54 hazard-zone
    features in a ~0.1°×0.11° tile — suggests tiles on the order of 0.3–0.5° per side,
    but verify each tile's count before pulling it, since density is highly non-uniform;
    see §8), stitch into one local GeoDataFrame, build a spatial index, then run the
    overlay against the already-built grid locally.
  - *National*: acquire per-state File Geodatabases manually via MSC (§6) into
    `data/raw/fema_nfhl/manual/<ST>/`, and process state-by-state, chunked per county
    (`DFIRM_ID`) or per grid tile to respect the project's ~4 GB/process memory budget
    (justified by the vertex-density finding in §8 — a whole large coastal state should
    not be loaded into one GeoDataFrame at once).
- Preserve unsimplified source geometry for anything recorded as an `observed` value;
  only simplify a working copy used purely for overlay performance, if needed.

## 8. Volume

- **Verified feature counts** (live REST, 2026-10-02): nationally, `S_FLD_HAZ_AR` =
  **5,810,744** polygons; `S_FIRM_PAN` = **183,680** panels; `NFHL Availability` = 3,199
  study-area polygons. Texas (`DFIRM_ID LIKE '48%'`): **235,932** hazard-zone polygons /
  **5,445** panels. Louisiana (`DFIRM_ID LIKE '22%'`): **130,567** hazard-zone polygons /
  **2,193** panels.
- **Vertex density is extremely right-skewed.** A 500-feature OBJECTID-ordered sample from
  Texas had mean **1,882** vertices/feature but **median 36.5**, max **335,781** (a single
  polygon) — a small number of very complex coastal/marsh polygons dominate total size.
  Two further offset samples (resultOffset 100,000 and 230,000; n=500 each) measured
  6,124 and 7,708 bytes/record respectively (verbose JSON, 5-decimal coordinate
  precision, 4 attribute fields); the first OBJECTID-ordered sample measured 39,257
  bytes/record. Blended over all 1,500 sampled records: **≈17.7 KB/record** (JSON text).
  Naively extrapolated: **≈4.2 GB (TX) / ≈2.3 GB (LA)** for the `S_FLD_HAZ_AR` layer alone
  as verbose JSON — the real File Geodatabase/shapefile will differ (binary coordinate
  encoding, no JSON punctuation overhead) but is expected to stay the same order of
  magnitude (low single-digit GB per large coastal state, for this one layer), and a full
  state download bundles roughly 20 more `S_*`/`L_*` layers on top of this one.
- **The dev bbox sits inside exactly this high-complexity coastal belt.** A direct feature
  count of `S_FLD_HAZ_AR` across the full dev bbox could **not** be obtained: two
  consecutive `returnCountOnly` calls against the full `[-98,29,-93,33]` envelope each ran
  past a 120-second timeout with no response. The identical query restricted to a single
  ~0.1°×0.11° tile (one grid-cell-sized area) returned in **0.17 s** with 54 features, and
  the bbox-wide `S_FIRM_PAN` count returned in **0.2 s** with **3,481** panels — i.e. the
  *panel* layer is cheap at any of these scales, but the *hazard-zone* layer is only cheap
  at small-tile scale. Using the national panel : zone ratios as a rough cross-check
  (TX ≈ 43.3, LA ≈ 59.5 zone-polygons per panel) against 3,481 dev-bbox panels suggests
  **on the order of 1.5–2 × 10⁵ hazard-zone polygons** intersect the dev bbox — an
  estimate, not a verified count; get the real number via tiled counting before
  provisioning.
- **Memory**: given the vertex-density tail above, do not load a whole large coastal
  state's `S_FLD_HAZ_AR` into one in-memory GeoDataFrame under the project's ~4 GB/process
  budget; chunk per county (`DFIRM_ID`) or per grid-tile batch and build a spatial index
  before overlay.

## 9. Interpretation limits

- NFHL "effective" status reflects FEMA's current *regulatory* flood designation for NFIP
  purposes — it is not a freshly re-run hydrologic/hydraulic model, and some effective
  panels date to the 1980s (oldest verified: 1981-10-06). An old effective date does not
  itself imply the hazard is understated or overstated; it means the zone has not been
  restudied since that date. This is the flood-specific instance of the project's general
  "historical averages ≠ future/updated conditions" caution.
- `SFHA_TF` is **not** strictly binary (`T`/`F`); a verified third value `U`
  (undetermined) occurs, including on some nominally-minimal-hazard `X` records and on
  `OPEN WATER`. Always read `SFHA_TF` directly; do not infer it purely from `FLD_ZONE`.
- Zone `D` ("Area of Undetermined Flood Hazard") sits inside the mapped FIRM-panel extent,
  but its hazard status is explicitly undetermined — counting it as "mapped, zero hazard"
  would violate the project's own UNKNOWN rule (AGENTS.md §3.3); it must flow into the
  undetermined/unknown accounting, not the 0.2%/minimal-hazard bucket.
- `ZONE_SUBTY='AREA NOT INCLUDED'` is **not present** in today's live hazard-zone data
  (0 matches, verified); the concept instead shows up as free text in FIRM Panel
  `PNP_REASON` on "Not Printed" panels. A query that only checks `ZONE_SUBTY` for this
  string will silently miss these gaps.
- `FLD_ZONE='AR'` is a real documented code with **zero** current features nationwide
  (verified) — support it for completeness but do not expect it to contribute today.
- Floodway is spread across 19 distinct `(FLD_ZONE, ZONE_SUBTY)` combinations (§4); a
  naive `ZONE_SUBTY = 'FLOODWAY'` equality filter undercounts it.
- A FIRM panel's `PANEL_TYP` containing "Not Printed" does **not** mean unmapped — most
  sampled "Not Printed" panels exist because there is no SFHA, the area is open water, or
  it is all Zone D/X; the panel and its hazard determination remain part of the mapped,
  effective extent.
- At least one dirty categorical value was observed directly
  (`PANEL_TYP = "Countywide, Panel Printed'"`, stray trailing apostrophe) — normalize/trim
  string fields defensively, as with any large government shapefile/GDB export.
  `PNP_REASON` is effectively free text (548 distinct values in one national sample) —
  do not treat it as a clean coded field.
- The MapServer's advertised `extent` spans a near-global bbox (it covers every U.S.
  state/territory, including Pacific islands at very different longitudes) — that is the
  *service's* combined extent, not evidence about any one feature's coordinate system;
  still reproject explicitly from the per-feature 4269 rather than assuming 4326.
- This service is effective-data-only; FEMA's preliminary/pending flood data is a
  separate product (own viewer/service, not independently investigated here) and must
  never be blended into "effective SFHA" fractions without distinct labeling.

## 10. Pitfalls (operational / access)

- A `returnCountOnly`/`query` call against `S_FLD_HAZ_AR` (layer 28) with a multi-state
  bounding box can hang past 120 seconds with no error returned at all (reproduced twice,
  verified) — always bound geometry queries to small tiles, and/or prefer
  attribute-indexed paging (`DFIRM_ID` prefix, `resultOffset`) over large spatial filters
  for anything bigger than a handful of cells.
- `maxRecordCount` is 2000 on every layer and the service root (verified) — any query
  silently truncates at 2000 and sets `"exceededTransferLimit": true`; code must check
  that flag and page with `resultOffset`, never assume one call returns everything.
- No `X-RateLimit-*` or similar throttling header was observed on any response — the only
  practical "rate limit" is the large-query timeout behavior above; self-imposed pacing
  and small tile sizes are this project's own responsibility.
- `msc.fema.gov/portal/advanceSearch` renders via client-side JS calling session-bound
  AJAX endpoints; no stable static download URL could be found or guessed (two plausible
  guesses both 404'd, verified) — this path cannot be scripted without simulating the
  interactive form, which this task does not do; treat it as a manual, one-time
  per-jurisdiction step.
- An independent, publicly-queryable mirror of NFHL-derived layers exists at NASA NCCS
  (`maps.nccs.nasa.gov/.../hifld_open/national_flood_hazard`, sourced from DHS HIFLD
  Open) — noted for awareness only; not verified or used in this report, and any such
  mirror can lag FEMA's own live effective data, so it should not be treated as
  authoritative.

## 11. Open questions

- Exact byte size of the official per-state File Geodatabase ZIP for Texas and Louisiana
  (the actual MSC download) — could not be verified without using the interactive search
  form. A human should download each once, then record the real size + sha256 in a future
  `data/raw/fema_nfhl/manual/download_log.json`.
- Whether the observed `DFIRM_ID = ST_FIPS(2) + CO_FIPS(3) + check-letter` convention
  holds universally, or breaks for joint multi-county/cross-state studies — only checked
  against TX and LA samples here.
- Whether the `NFHLWMS` service (mentioned on fema.gov alongside the plain `NFHL`
  MapServer) exposes preliminary data in addition to effective data — not verified in
  this pass.
- Where `S_FLD_HAZ_AR` and `S_FIRM_PAN` footprints disagree at panel-neatline edges,
  which should be authoritative for `frac_mapped` — both layers were verified to exist
  and be queryable, but their edge-case reconciliation was not tested.
- Typical `SCALE` (FIRM base-map scale) values and `STATIC_BFE`/vertical-datum handling
  per `V_DATUM` were not enumerated in this pass (low priority for the fraction-based
  features requested, but relevant if a future feature needs elevation).
