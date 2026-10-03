# Source recon: `wri_aqueduct40` — WRI Aqueduct 4.0 Water Risk

Status: **READY** (file acquired, integrity-verified, archive opened, schema and data dictionary
cross-checked against the official GitHub repo and against the actual shipped data).

Prepared for Phase 2 (geography / source adapters). This document does not rank, score, or threshold
anything; it only records what the Aqueduct 4.0 product contains and how to read it correctly.

---

## 1. Product / version

- **Official name**: Aqueduct 4.0 Current and Future Global Maps Data ("Water Risk Atlas" download, as
  distinct from the separate "Aqueduct 4.0 Country Rankings" product).
- **Version**: Aqueduct 4.0, published **2023-08-16**; the shipped package is internally timestamped
  `Y2023M07D05`. Confirmed still current (no 4.1/5.0) via WebSearch on 2026-10-02: WRI's FAQ states the
  global hydrological model is "re-run approximately every 3-4 years"; the most recent corroborating
  mention found (Feb 2026, ArcGIS Living Atlas republication Nov 2025) still describes the dataset as
  "Aqueduct 4.0" with the same Aug-2023 vintage — i.e. a republication/rehosting, not a methodology update.
  `verified_from`: WebSearch results on wri.org, github.com/wri/Aqueduct40, and ArcGIS Living Atlas, 2026-10-02.
- **Data year/period**:
  - Baseline: hydrological model run representing **1979–2019** (long-term chronic baseline, PCR-GLOBWB 2).
  - Future: three 30-year windows — **2030 (2015–2045)**, **2050 (2035–2065)**, **2080 (2065–2095)** —
    each as the median of 5 CMIP6 GCMs, under 3 scenarios (see §4).
  `verified_from`: `data_dictionary_water-risk-atlas.md` (official GitHub repo, fetched directly).
- **Citation** (from the bundled README and the official data dictionary): Kuzma, S., M.F.P. Bierkens,
  S. Lakshman, T. Luo, L. Saccoccia, E. H. Sutanudjaja, and R. Van Beek. 2023. "Aqueduct 4.0: Updated
  decision-relevant global water risk indicators." Technical Note. Washington, DC: World Resources
  Institute. `doi.org/10.46830/writn.23.00061`.
- **Recommended product to use**: the single national/global package already on disk,
  `aqueduct-4-0-water-risk-data.zip` — it contains **both** the baseline data and the future-projections
  data (Phase 5 need) in one archive; a vector geodatabase (needed for area-weighted overlay) **and**
  flat CSVs of the same attributes (useful for non-spatial QA, not for the spatial join — see §8). No
  separate/better product exists; this is WRI's one official sub-basin-level download.

## 2. Endpoints (verified)

| URL | Method | Result | Verified |
|---|---|---|---|
| `https://files.wri.org/aqueduct/aqueduct-4-0-water-risk-data.zip` | HEAD | `200 OK`, `Content-Type: application/zip`, `Content-Length: 261527511`, `Last-Modified: Mon, 07 Aug 2023 16:11:26 GMT`, served via CloudFront/S3 | 2026-10-02 (fresh HEAD this session; identical `ETag` to the prior session's HEAD, confirming the file has not changed) |
| `https://www.wri.org/data/aqueduct-global-maps-40-data` | GET | `200 OK` — official download landing page | 2026-10-02 |
| `https://www.wri.org/research/aqueduct-40-updated-decision-relevant-global-water-risk-indicators` | GET | `200 OK` — technical-note landing page (PDF gated behind a "Download publication" webform at `wri.org/webform/download_publication...`; **not submitted**, per the no-forms rule — see §9 and Open Questions) | 2026-10-02 |
| `https://www.wri.org/data/aqueduct-40-country-rankings` | GET | `200 OK` — related (not needed) country/province-aggregated product | 2026-10-02 |
| `https://github.com/wri/Aqueduct40` | GET | `200 OK` — official metadata/data-dictionary repo | 2026-10-02 |
| `https://github.com/wri/Aqueduct40/blob/master/data_dictionary_water-risk-atlas.md` (raw: `raw.githubusercontent.com/wri/Aqueduct40/master/data_dictionary_water-risk-atlas.md`) | GET | `200 OK` — **the correct field dictionary for this download** (see §9 pitfall: the bundled README links to the wrong one) | 2026-10-02 |
| `https://github.com/wri/Aqueduct40/blob/master/data_FAQ.md` | GET | `200 OK` | 2026-10-02 |
| `https://github.com/wri/Aqueduct40/blob/master/LICENSE.txt` | GET | `200 OK` | 2026-10-02 |
| `https://creativecommons.org/licenses/by/4.0/` | GET | `200 OK` | 2026-10-02 |
| `https://doi.org/10.46830/writn.23.00061` | GET (redirect) | `200 OK`, resolves to the WRI research page above | 2026-10-02 |

**Files needed** (all inside the one zip, no other file required):
- `Aqueduct40_waterrisk_download_Y2023M07D05/GDB/Aq40_Y2023D07M05.gdb/` — Esri File Geodatabase, 3 layers
  (`baseline_annual`, `baseline_monthly`, `future_annual`) — **this is the input for spatial aggregation**.
- `Aqueduct40_waterrisk_download_Y2023M07D05/CVS/Aqueduct40_baseline_annual_y2023m07d05.csv` (202,140,225 B),
  `..._baseline_monthly_y2023m07d05.csv` (29,243,354 B), `..._future_annual_y2023m07d05.csv` (29,009,593 B) —
  same attributes as the GDB layers, **no geometry**; useful only for attribute-only QA/joins by `string_id`/`pfaf_id`.
  (Note: WRI's own folder name is `CVS`, not `CSV` — confirmed in the actual archive listing, not a typo on our side.)
- `Aqueduct40_waterrisk_download_Y2023M07D05/Aqueduct40_README.xlsx` — top-level readme/citations (one sheet,
  "Read Me"); its "data dictionary" hyperlinks are wrong (§9).

## 3. CRS / resolution / coverage

- **Native CRS**: `EPSG:4326` for all three GDB layers (verified via `pyogrio.read_info` on each layer).
- **Native resolution**: vector polygons, **not a fixed grid** — HydroBASINS Level 6 sub-basins
  (`pfaf_id`, 6-digit Pfafstetter code), further intersected with GADM provinces (`gid_1`) and WHYMAP
  groundwater aquifers (`aqid`); each row's `string_id` is the `pfaf_id-gid_1-aqid` combination (see §9
  pitfall #1 — this is a tiling scheme, not one non-overlapping polygon per place).
  In the project's dev-area bbox `[-98.0, 29.0, -93.0, 33.0]`: 110 raw polygon rows, but only **45 distinct
  sub-basins** (`pfaf_id`), **7 distinct aquifers** (`aqid`), **3 distinct provinces** (`gid_1`); sub-basin
  `area_km2` in that sample ranges **0.02 km² to 25,959 km²** (median **836.6 km²**) — i.e. roughly
  8× a 10 km × 10 km (100 km²) cell at the median, but **well below one cell** at the small end, so many
  cells (especially coastal/deltaic ones) will span multiple sub-basins.
  `verified_from`: direct `pyogrio.read_dataframe(..., bbox=...)` query against the shipped GDB, this session.
- **Spatial coverage**: global land area at HydroBASINS resolution. A CONUS-wide bbox query
  (`[-125, 24, -66, 50]`) returns 4,267 polygon rows (2,850 with `gid_0 == "USA"`; the remainder are
  border-crossing Canadian/Mexican/Bahamian sub-basins/aquifers that legitimately matter for grid cells
  near the border/coast) — no indication of a geometric gap over CONUS. **Geometric coverage is not the
  same as data coverage**: within the dev-area sample, 6/110 rows (same underlying 45 basins) carry
  `bws_cat == -9999` ("No Data"), rising to higher fractions for less-complete indicators like `drr`
  (see §4 valid-count columns) — i.e. a cell can sit inside a real Aqueduct polygon and still have no
  usable value for a given indicator.
  `verified_from`: direct bbox queries against the shipped GDB, this session.

## 4. Fields / units / codes

All values below were read directly from the shipped `Aqueduct40_baseline_annual_y2023m07d05` layer/CSV
(68,510 rows total) and cross-checked against the official
`data_dictionary_water-risk-atlas.md`. Every indicator follows the column pattern
`{indicator}_raw | _score | _cat | _label`. **Keep all four separate — never derive one from another.**

| Indicator | Full name | Methodology vintage | Raw unit / meaning | Valid raw range (sentinels excluded) | `_score` | `_cat` codes (from actual data) |
|---|---|---|---|---|---|---|
| `bws` | Baseline Water Stress | Aqueduct 4.0 (updated) | dimensionless ratio, withdrawal ÷ available renewable supply (label bins in %) | 0 – 30.14 (mean 0.43) — **unbounded, can exceed 1** | [0–5] | `-9999`=No Data, `-1`="Arid and Low Water Use", `0`="Low (<10%)", `1`="Low - Medium (10-20%)", `2`="Medium - High (20-40%)", `3`="High (40-80%)", `4`="Extremely High (>80%)" |
| `bwd` | Baseline Water Depletion | Aqueduct 4.0 (updated) | dimensionless ratio, consumptive use ÷ available renewable supply | 0 – 16.25 (mean 0.27) | [0–5] | `-9999`=No Data, `-1`="Arid and Low Water Use", `0`="Low (<5%)", `1`="Low - Medium (5-25%)", `2`="Medium - High (25-50%)", `3`="High (50-75%)", `4`="Extremely High (>75%)" |
| `iav` | Interannual Variability | Aqueduct 4.0 (updated) | dimensionless variability index | 0.0012 – 6.40 (mean 0.57) | [0–5] | `-9999`=No Data, `0`="Low (<0.25)" … `4`="Extremely High (>1.00)" (no `-1` category) |
| `sev` | Seasonal Variability | Aqueduct 4.0 (updated) | dimensionless variability index | 0.013 – 3.46 (mean 0.51) | [0–5] | `-9999`=No Data, `0`="Low (<0.33)" … `4`="Extremely High (>1.33)" (no `-1`) |
| `gtd` | Groundwater Table Decline | **Aqueduct 3.0** (not updated in 4.0) | cm/year (negative = water table rising) | **-33.69 – +44.10** cm/yr (mean 0.12) | [0–5] | `-9999`="Insignificant Trend" (same meaning as "No Data" elsewhere, different label text — see §9), `0`="Low (<0 cm/y)" … `4`="Extremely High (>8 cm/y)"; defined **only** where an aquifer polygon (`aqid`) exists, independent of sub-basin |
| `rfr` | Riverine Flood Risk | Aqueduct 3.0 | dimensionless annual probability/fraction; label is "N in M" annual odds | 0 – 0.350 (mean 0.0096) | [0–5] | `-9999`=No Data, `0`="Low (0 to 1 in 1,000)" … `4`="Extremely High (more than 1 in 100)" |
| `cfr` | Coastal Flood Risk | Aqueduct 3.0 | dimensionless annual probability/fraction | 0 – 0.360 (mean 0.0006) | [0–5] | `-9999`=No Data, `-1`="No Risk" (a **real** "not coastally exposed" code, distinct from missing), `0`="Low (0 to 9 in 1,000,000)" … `4`="Extremely High (more than 2 in 1,000)" |
| `drr` | Drought Risk | Aqueduct 3.0 | dimensionless index, 0–1 | 0.00087 – 0.960 (mean 0.46) | [0–5] (note: max observed score 4.80, not exactly 5) | `-9999`=No Data, `0`="Low (0.0-0.2)" … `4`="High (0.8-1.0)" |
| `w_awr_def_tot` | **Overall water risk, default industry weighting** (the closest thing to "the overall score" in this data dictionary — see Open Questions) | composite | composite 0–5-like score, weighted-quantile aggregate of all applicable indicators | 0.084 – 4.636 (mean 1.93) | [0–5] (quantile-remapped; official quantile table is in `data_dictionary_water-risk-atlas.md`) | same `-9999/0-4` pattern; also carries `_weight_fraction` [0–1] = realized weight after excluding NoData inputs |

Also present but **not** in the task's named list (do not pull these in as if sub-basin-resolved — see §9):
`ucw` (Untreated Connected Wastewater), `cep` (Coastal Eutrophication Potential), `udw` (Unimproved/No
Drinking Water), `usa` (Unimproved/No Sanitation), `rri` (Peak RepRisk country ESG risk index) — all
Aqueduct-3.0-vintage, country/province-level, so constant across every sub-basin in a state/country.
A full 10-industry weighting-scheme family (`def/agr/che/con/elp/fnb/min/ong/smc/tex`) exists for the
grouped `w_awr_*` scores if Phase 5 wants a data-center-relevant weighting instead of `def`.

**Special/missing codes, summarized** (three distinct meanings — do not conflate):
1. `-9999` in any `_raw`/`_score`/`_cat` field = genuine no data → **UNKNOWN**, never zero (per AGENTS.md §3.3).
2. `-1` in `_cat` = a **real, valid** category, not missing (`bws`/`bwd`: "Arid and Low Water Use"; `cfr`: "No Risk").
3. `9999` in `_raw` (observed on `bws_raw`/`bwd_raw`, 1,334 of 68,510 rows each) = a **real, extreme** sentinel
   meaning "supply practically exhausted" (per WRI's FAQ: supply `< 0.0005 m/month` for ≥6 months) — not
   missing, but must not be blindly averaged with normal-range ratios.

**Future (`future_annual`) layer** — 16,395 rows, same CRS/geometry style, column pattern
`{bau|opt|pes}{30|50|80}_{indicator}_x_{r|s|l|c}`:

| | |
|---|---|
| Scenarios | `bau` = Business as Usual (SSP3 RCP7.0), `opt` = Optimistic (SSP1 RCP2.6), `pes` = Pessimistic (SSP5 RCP8.5) |
| Years | `30` = 2030 (2015-2045), `50` = 2050 (2035-2065), `80` = 2080 (2065-2095) |
| Indicators | `ba` = Available Blue Water (cm/yr, flux not volume — see §9 pitfall), `ww` = Gross Water Demand (cm/yr), `ws` = Water Stress, `wd` = Water Depletion, `iv` = Interannual Variability, `sv` = Seasonal Variability |
| Types | `_r` raw (double), `_s` score [0–5], `_l` label (string), `_c` category [-1,4] (`ba`/`ww` have only `_r`/`_l`, no score/cat) |
| Missing data | On the sampled fields (`bau30_ws_x_r`, `bau30_ba_x_r`, `bau30_ww_x_r`, `pes80_ws_x_r`), missing is a **blank/NULL** cell (563/16,395 rows), **not** `-9999` — a different convention from the baseline layers. `9999` sentinel still appears for `ws` (368–414 rows per scenario/year, same "severe scarcity" meaning). |

`verified_from` for this whole section: (a) `pyogrio.read_info()` schema dump of all 3 GDB layers; (b)
official `data_dictionary_water-risk-atlas.md` (raw GitHub content, fetched directly, 200 OK); (c)
`data_FAQ.md` (raw GitHub content) for the 9999/-9999 explanation and the "Arid and Low Water Use"
interpretation guidance; (d) direct pandas computation of min/max/valid-counts and
`drop_duplicates()` on every `(cat, label)` pair, run against the actual shipped CSV, this session.

## 5. License

- **Data**: Creative Commons **CC BY 4.0** ("licensed in accordance with the terms of a creative commons
  license (CC BY 4.0)"), Copyright 2023 World Resources Institute. Confirmed in `LICENSE.txt`,
  `data_dictionary_water-risk-atlas.md` header, and the WRI data page. Attribution requested using the
  citation in §1.
- **Repository code** (`production_scripts/`, i.e. WRI's own processing scripts, not the data itself):
  separate permissive "AS IS" warranty-disclaimer text in the same `LICENSE.txt` (MIT-style, no
  endorsement/liability) — not relevant to data use, noted for completeness.
- `verified_from`: `https://raw.githubusercontent.com/wri/Aqueduct40/master/LICENSE.txt` (200 OK, fetched
  and read directly this session).

## 6. Access

- **No login, account, API key, CAPTCHA, or click-through terms** required to fetch the zip — confirmed by
  a direct HEAD request returning `200 OK` straight from `files.wri.org` (CloudFront/S3), with no redirect
  through any gated page.
- The `wri.org` data landing page offers an *optional* newsletter/updates signup; this was not used (not
  needed — the direct file URL already resolves publicly).
- The **technical note PDF** (methodology detail, exact statistical formulas) is distributed through a
  `wri.org/webform/download_publication...` form. Per AGENTS.md §4 ("no filling personal-data forms,
  no accepting click-through licenses on the user's behalf"), **this form was not submitted**. All facts
  in this report instead come from the GitHub data dictionary/FAQ and from directly inspecting the shipped
  data — sufficient for an ingestion adapter, but see Open Questions for what remains behind that form.
- **Status**: `READY`. Implemented/acquired/analyzed in AGENTS.md §4 terms: data is acquired (file on disk,
  checksum-verified) and analyzed-for-recon (schema, codes, and ranges confirmed); feature computation
  into grid cells is Phase 2's implementation work, not done here.

## 7. Recommended aggregation

**Method: area-weighted overlay**, reprojected to `EPSG:5070` (per AGENTS.md §6 — never compute areas from
degrees), from HydroBASINS/aquifer/province polygons onto 10 km grid cells. Recommended because the source
is natively polygon/vector, not raster — zonal-statistics-on-raster and nearest-distance are not
appropriate as the primary method for this source.

1. Reproject the three needed ID families **once**, cached under `data/interim/wri_aqueduct40/`:
   - sub-basin indicators (`bws, bwd, iav, sev, rfr, cfr, drr`, all `w_awr_*`): keyed by `pfaf_id`.
   - `gtd`: keyed by `aqid` (separate, generally larger aquifer polygons).
   - `ucw/cep/udw/usa/rri` (if ever used): keyed by `gid_0`/`gid_1` (country/province).
   Doing this per-ID-family, rather than treating every raw row as an independent polygon, avoids the
   tiling inflation in §9 pitfall #1.
2. For each grid cell × each indicator, intersect the cell with all polygons carrying a valid (not
   `-9999`) value for that indicator, compute `intersection_area / cell_area` weights, and take the
   area-weighted mean of `_raw` (and separately of `_score`; never average `_cat`/`_label` — pick the
   value of the plurality-area contributor and record the rest as overlap detail, or carry them as a list).
3. Per cell, per indicator, record (matching AGENTS.md §6 long-form provenance exactly):
   - `coverage_fraction` = (area with a valid value) / (cell area). If `0`, the metric is `unknown`
     (never zero), per AGENTS.md §3.3 and the Phase 2 spec's explicit "Aqueduct ratios ... must remain
     distinguishable" / "do not assume every field is 0-1" instruction.
   - `n_contributing_regions` = count of **distinct** `pfaf_id` (or `aqid`, or `gid_0`, matching the
     indicator's own ID family) intersecting the cell — **not** the raw row count (see §9 pitfall #1).
     When `> 1`, the cell intersects multiple source regions; record their shares.
   - native resolution note = "HydroBASINS Level 6 sub-basin polygon" (or "WHYMAP aquifer polygon" for
     `gtd`), plus the specific `pfaf_id`/`aqid` list, so source resolution stays visible after the join.
   - `value_status` = `observed` for a cell fully inside valid-data polygons; `unknown` with
     `missing_reason="aqueduct_no_data"` where `coverage_fraction == 0`, or where the only intersecting
     source rows are `-9999` for that field.
4. Treat `9999` (`bws_raw`/`bwd_raw` "severe scarcity" sentinel) as a real, extreme, flaggable value —
   do not let it silently dominate an area-weighted mean with ordinary 0–2-range neighbors; consider
   carrying a `has_extreme_scarcity_flag` alongside the area-weighted raw mean rather than discarding the
   information.
5. For the future layer, join on `pfaf_id` the same way, once per `(scenario, year)` combination needed
   by Phase 5; remember its missing-data convention is blank/NULL, not `-9999` (§4).

## 8. Volume / memory

- **On disk**: zip 261,527,511 B (249.4 MiB); uncompressed archive 772,582,596 B (736.6 MiB) across 59
  files. Already within the task's 12 GB budget by a wide margin (both compressed and uncompressed).
- **Dev area** (`[-98.0, 29.0, -93.0, 33.0]`): bbox-filtered read of `baseline_annual` returns 110 rows in
  <1 s directly from the zip via GDAL's `/vsizip/` virtual filesystem (no extraction needed); trivial
  memory (a few MB for the needed columns).
- **National (CONUS)**: a CONUS bbox (`-125, 24, -66, 50`) read returns 4,267 rows in ~0.6 s; reading all
  236 `baseline_annual` fields for all 68,510 **global** rows (i.e. no bbox filter at all) measured at
  under 100 MB of pandas memory for a ~40-column subset scaled up — comfortably inside the project's
  ~4 GB/process budget with no tiling/chunking required for this source specifically. The practical cost
  center is the **polygon-polygon overlay against the national grid** (hundreds of thousands of cells),
  not reading Aqueduct itself; recommend a spatial-index (STRtree) pre-filter before exact `shapely`
  intersection (standard `geopandas.overlay` pattern), and dissolving to distinct `pfaf_id`/`aqid` first
  to shrink the polygon count feeding the overlay.
- Recommend **extracting the GDB folder to local disk once** (e.g. `data/interim/wri_aqueduct40/`) for
  repeated production reads rather than re-opening `/vsizip/...zip/...gdb` on every run — reading through
  the zip repeatedly re-pays GDAL's directory-parsing cost and is slower on the one geometry discussed in
  §9 pitfall #3 (hundreds of parts).
- `verified_from`: direct timed `pyogrio.read_dataframe()` calls against the shipped archive, this session.

## 9. Limits and pitfalls

**Project-level limits** (already stated in AGENTS.md §3.5 / Phase 2 spec, reiterated here because they
apply directly to this source): Aqueduct is **not** a water-supply commitment; it is a global model
output that "cannot be measured directly and therefore ha[s] not been validated" (WRI's own FAQ caution);
it does not model interbasin transfers; local precision is limited (two nearby points can fall in
different sub-basins and show different values); future demand assumptions hold livestock demand constant
from 2014 and irrigation/crop extent constant after 2050; the optimistic/pessimistic future scenarios are
distinct socioeconomic storylines, not simply best/worst case (WRI's FAQ gives an explicit example of
optimistic-scenario water stress exceeding pessimistic in some basins). `gtd`, `rfr`, `cfr`, `drr`, `ucw`,
`cep`, `udw`, `usa`, `rri` are all still **Aqueduct 3.0** vintage — only `bws`, `bwd`, `iav`, `sev` got new
hydrology in 4.0.

**Concrete pitfalls found by directly inspecting this download** (each independently verified this session):

1. **Row count ≠ region count.** The polygon layer tiles three ID families together
   (`string_id = pfaf_id-gid_1-aqid`). In the dev-area sample, 110 raw rows reduce to only 45 distinct
   sub-basins / 7 aquifers / 3 provinces. Counting raw intersecting rows to flag "multiple source regions"
   overstates overlap by roughly 2.4×; dedupe by the ID relevant to each indicator (§7).
2. **One feature's bounding box spans half the country.** `string_id = "None-None-1400"` (`aqid=1400`,
   no `pfaf_id`/`gid_1`) is a single `MultiPolygon` with **722 disjoint parts** running from the Texas
   coast to New England (`minx/miny/maxx/maxy = -95.81, 25.32, -73.95, 40.50`); only `gtd` has a value on
   this row. A bounding-box-only spatial pre-filter will match this feature against almost every national
   grid cell; use true polygon intersection, not bbox-only filtering, and expect GDAL's
   `organizePolygons(): >100 parts` slow-path warning when reading it.
3. **`bws_raw`/`bwd_raw` are unbounded ratios**, observed up to 30.14 / 16.25 respectively — not a 0–1 or
   0–100% value. Only `_score` is bounded to [0, 5]. This directly matches (and is now numerically
   confirmed for) the Phase 2 spec's own warning: "Do not assume every field is a 0–1 index."
4. **Three different "special code" meanings, not one.** `-9999` = missing; `-1` in `_cat` = a real
   category (`"Arid and Low Water Use"` for `bws`/`bwd`, `"No Risk"` for `cfr`); `9999` in `_raw` = a real
   extreme-scarcity sentinel. Conflating any two of these will corrupt an area-weighted mean or a coverage
   calculation.
5. **`gtd`'s missing-sentinel label text differs** ("Insignificant Trend" at `cat == -9999`, instead of
   "No Data" used everywhere else) even though the numeric sentinel is identical — key logic off the
   number, not the label string.
6. **The bundled `Aqueduct40_README.xlsx` links to the wrong data dictionary.** Its "data dictionary"
   hyperlinks (for all three layers) point to `data_dictionary_country-rankings.md` (the separate
   country/province product), not `data_dictionary_water-risk-atlas.md` (the correct one for this
   sub-basin geodatabase). Found by inspecting the hyperlink targets directly, not just the display text.
7. **Missing-data convention differs between layers.** Baseline layers use the numeric `-9999` sentinel;
   the sampled `future_annual` fields instead leave the cell blank/NULL for missing (no `-9999` observed
   there). A shared ingestion path must handle both.
8. **The CSVs have no geometry.** They are attribute-only exports of the same GDB tables; any spatial join
   must use the GDB.
9. **Future `ba` (Available Blue Water) is a depth-equivalent flux (cm/yr), not a volume**, and can reach
   extreme values (up to ~6.1×10⁶ cm/yr observed) at small coastal/river-mouth sub-basins that carry large
   upstream discharge relative to their own tiny area — sanity-check against `area_km2` before use
   (per WRI's own guidance: "Volume = Flux × Area").
10. **Country/province-level fields can look sub-basin-resolved but are not** — `ucw/cep/udw/usa/rri` are
    constant across every sub-basin within the same state/country; don't treat them as locally-varying
    hydrology alongside `bws`/`bwd`/etc.

## 10. Open questions

1. The precise statistical formulas behind `iav`/`sev` (exact variability-index definition) and the exact
   raw-value derivation for `rfr`/`cfr`/`drr` live only in the full technical note PDF, which WRI gates
   behind a "Download publication" webform (`wri.org/webform/download_publication?...`). Per AGENTS.md
   (no form submissions), this was not retrieved; the units/ranges/categories above were instead verified
   directly from the official GitHub data dictionary and by computing real min/max/category tables from
   the shipped data, which is sufficient for ingestion but not for reproducing WRI's internal derivations.
   If an adapter author needs the exact formulas, the manual path is: open that WRI page and complete the
   publication-download form as a person (outside this agent's access-control boundary).
2. Phase 5 should decide which `w_awr_*` weighting scheme represents "overall water risk" for a data
   center: the default (`w_awr_def_tot`, used above) or a more facility-specific one (closest built-ins
   are `elp` = Electric Power or `smc` = Semiconductor). This is a Phase 5/model decision, not a Phase 2
   one; this report surfaces the option without choosing.
3. **Not part of this data source, flagged for the user/orchestrator**: the workflow harness's relayed
   "user request" for this run was only the fragment `for subagent model changes it to sonnet 5.5`. That
   reads as an orchestration-level instruction about which model should run *subagents* in general, not an
   instruction this already-running subagent can act on — there is no "sonnet 5.5" model, this session is
   `claude-sonnet-5`, and no tool available here changes a workflow's subagent-model configuration. No
   action was taken on it; it is noted here only so the user/orchestrator can confirm intent.

## Appendix: what is already on disk

- `data/raw/wri_aqueduct40/aqueduct-4-0-water-risk-data.zip` — 261,527,511 bytes.
  Re-verified this session: local `sha256sum` =
  `bd3ed2bce88d6ff1b89191632ad134a2436e1e1d49599382f23a04d513624fc3`, which **matches**
  `download_log.json`'s logged hash exactly; size matches a fresh server `HEAD` `Content-Length` exactly;
  `zipfile.testzip()` reports no corrupt members; all 59 archive members listed and opened; all three GDB
  layers opened with `pyogrio` (`geopandas`/`GDAL` stack) directly out of the zip via `/vsizip/` with no
  errors. **No re-download was necessary or performed** — the prior session's download was complete and
  correct, and this is the right product (vector sub-basin polygons, as needed for area-weighted overlay;
  no raster product exists or is needed for this source). `data/raw/wri_aqueduct40/download_log.json` is
  accurate as written and was left unmodified.
- A `_scratch/` subfolder was created during this session to extract the README workbook and the two CSVs
  for inspection (data dictionary cross-check, value-range/category computation); it has been **removed**
  after use, leaving only the original zip and `download_log.json` in place.
