# epa_egrid — EPA Emissions & Generation Resource Integrated Database (eGRID)

Status: **READY** (documentation/endpoints fully verified; no bytes pre-downloaded this pass — see §9).
Researched: 2026-10-02. Source ID: `epa_egrid`.

## 1. Product / version

- **Official product**: eGRID — "The Emissions & Generation Resource Integrated Database."
- **Latest official edition**: **eGRID2023, revision 2** (data year **2023**). Released 2025-01-15; rev1
  2025-01-17; **rev2 released 2025-06-12** (current as of this check). This is the *18th edition* of eGRID.
  Source: eGRID2023 Technical Guide PDF, §1 "Introduction" and the `egrid2023_release_notes.txt` file
  (both read in full, see §2).
- **eGRID2024**: **not yet released by EPA** as of 2026-10-02 (verified by fetching `epa.gov/egrid` and
  `epa.gov/egrid/detailed-data` live today — both show eGRID2023 as the current edition, no eGRID2024 files
  or next-release date are published on those pages). A **third party** (Cornerstone Data) has posted a
  preliminary, self-generated "eGRID 2024" to Zenodo by re-running EPA's own open-source eGRID R pipeline
  against 2024 EIA/EPA CAMD inputs; this is **not an EPA product** and is **not recommended** as a project
  source without separate justification in `docs/sources.md` per AGENTS.md §4 ("use only authoritative/
  official sources"). See open question in §11.
- Produced by EPA's Office of Atmospheric Protection / Clean Air and Power Division; prepared for EPA by
  Abt Global. eGRID2023 was the first edition produced with EPA's new R-based production pipeline
  (`eGRID R production model 1.0.2`), replacing the prior SAS-based pipeline — several fields/columns are
  new or renamed relative to eGRID2022 and earlier (see Pitfall #2 in §10).

## 2. Endpoints (all verified today, 2026-10-02, via `curl -sI`/`-s` with
`User-Agent: dc_locator/0.1 (research prototype)`; every URL below returned HTTP 200 unless noted)

| # | File | URL | Format | HTTP | Content-Length |
|---|---|---|---|---|---|
| 1 | eGRID2023 data (imperial) | `https://www.epa.gov/system/files/documents/2025-06/egrid2023_data_rev2.xlsx` | xlsx | 200 | 21,213,301 B (20.2 MiB) |
| 2 | eGRID2023 data (metric) | `https://www.epa.gov/system/files/documents/2025-06/egrid2023_data_metric_rev2.xlsx` | xlsx | 200 | 24,803,997 B (23.7 MiB) |
| 3 | eGRID2023 Technical Guide | `https://www.epa.gov/system/files/documents/2025-01/egrid2023_technical_guide.pdf` | pdf | 200 | 2,768,135 B (2.64 MiB) |
| 4 | eGRID2023 release notes | `https://www.epa.gov/system/files/other-files/2025-06/egrid2023_release_notes.txt` | txt | 200 | 7,733 B |
| 5 | Summary Tables (xlsx) | `https://www.epa.gov/system/files/documents/2025-06/summary_tables_rev2.xlsx` | xlsx | 200 | 985,651 B |
| 6 | Summary Tables (pdf) | `https://www.epa.gov/system/files/documents/2025-06/summary_tables_rev2.pdf` | pdf | 200 | 410,720 B |
| 7 | eGRID2023 Subregions (shapefile) | `https://www.epa.gov/system/files/other-files/2025-01/egrid2023_subregions.zip` | shapefile zip | 200 | 57,260,059 B (54.6 MiB) |
| 8 | eGRID2023 Multiple Subregions (shapefile) | `https://www.epa.gov/system/files/other-files/2025-01/egrid2023_multiple_subregions.zip` | shapefile zip | 200 | 16,188,767 B (15.4 MiB) |
| 9 | eGRID2023 Subregions (KMZ, alt.) | `https://www.epa.gov/system/files/other-files/2025-01/egrid2023_subregions.kmz` | kmz | 200 | 43,509,570 B |
| 10 | eGRID2023 Multiple Subregions (KMZ, alt.) | `https://www.epa.gov/system/files/other-files/2025-01/egrid2023_multiple_subregions.kmz` | kmz | 200 | 12,166,999 B |

**Documentation / reference pages** (all HTTP 200 today):
`https://www.epa.gov/egrid` (overview) · `https://www.epa.gov/egrid/detailed-data` (canonical download page —
**note**: the older `epa.gov/egrid/download-data` URL now 301-redirects here) ·
`https://www.epa.gov/egrid/summary-data` · `https://www.epa.gov/egrid/egrid-technical-guide` ·
`https://www.epa.gov/egrid/egrid-mapping-files` · `https://www.epa.gov/egrid/frequent-questions-about-egrid` ·
`https://www.epa.gov/egrid/power-profiler` (interactive, per-address subregion lookup — **not** a batch
endpoint, see §10) · `https://www.epa.gov/egrid/code-lookup` · `https://www.epa.gov/egrid/egrid-pm25`
(PM2.5/NH3/VOC supplemental rates — not required by this task's feature list) ·
`https://edg.epa.gov/epa_data_license.html` (license statement).

Files needed for the features in this task: **#1 or #2** (pick one unit system — see Pitfall #1), **#7 and #8**
(subregion boundaries), **#3** (field definitions), **#5 or #6** (fast sanity-check of national/subregion
figures without opening the full workbook). #9/#10 are redundant alternative formats of #7/#8; not needed if
the shapefiles are used.

## 3. CRS / resolution / coverage

- **Attribute data (xlsx)**: tabular, no CRS. Eight aggregation levels per workbook: UNIT (26,190 records),
  GEN (26,601), PLNT (12,614), ST/state (52), BA/balancing authority (70), **SRL/eGRID subregion (27)**,
  NRL/NERC region (9), US (1). (Technical Guide §2.1, read directly.)
- **Boundary shapefiles (#7/#8)**: native CRS **UNVERIFIED** — not stated on the Mapping Files page or in
  the Technical Guide text reviewed, and the files were not opened in this pass (see §9 on why no download
  was performed). Confirm from the `.prj` on first use; EPA geospatial products of this vintage are commonly
  NAD83 (EPSG:4269) or WGS84 (EPSG:4326), but do not assume — verify, then reproject to the project's
  EPSG:5070. The KMZ alternates (#9/#10) are necessarily WGS84/EPSG:4326 lat-lon, per the KML 2.2 OGC
  specification itself (a property of the format, not of this specific file).
- **"Resolution"**: eGRID subregions are polygons, not a raster — there is no pixel size. EPA explicitly
  calls the subregion map **"representational"**: *"many of the boundaries shown on the maps are
  approximate because they are based on companies, not on strict geographical boundaries"* (Frequent
  Questions page, fetched today) — i.e. the boundaries approximate utility/balancing-authority electrical
  service relationships, not surveyed geographic lines. This matches the task brief's own caution.
- **Coverage**: National. 27 subregions = 22 CONUS subregions + AKGD/AKMS (Alaska) + HIOA/HIMS (Hawaii) +
  PRMS (Puerto Rico). Every EIA-860-reporting plant in the U.S. is assigned to exactly one (or, at the
  boundary, flagged as falling in more than one — see "Multiple Subregions" layer) eGRID subregion via a
  documented 5-step rule cascade (NERC-region match → balancing-authority match → Transmission/Distribution
  Owner ID + BA → Utility ID → NERC Long-Term Reliability Assessment area; Technical Guide §3.4.2, read
  directly) — so there are **no unassigned CONUS gaps** at the plant level. Dev-area bbox
  `[-98.0, 29.0, -93.0, 33.0]` (TX/LA/AR Gulf coast): based on the textual subregion descriptions in
  Table 3-4 (**not** a GIS overlay performed in this pass — flagged as open question §11), this bbox most
  plausibly spans at least **ERCT** ("Most of Texas") and **SRMV** ("Lower Mississippi Valley") — i.e.
  cells straddling two eGRID subregions are a *real, expected* case for this project's own dev area, not a
  hypothetical.

## 4. Fields / units / codes needed for the listed features

All verified by directly reading eGRID2023 Technical Guide, Appendix A ("eGRID File Structure - Variable
Descriptions"), Table A-6 (SRL/eGRID Subregion File, printed pp.111–120) and Table A-9 (GGL/Grid Gross Loss
File, printed p.140), plus the eGRID2023 Summary Tables (rev2) for example values — all read directly from
the actual PDF content, not inferred.

| Field (SRL file unless noted) | Description | Units | Observed value range | verified_from |
|---|---|---|---|---|
| `SUBRGN` | eGRID subregion acronym — the join key (e.g. `ERCT`, `SRMV`, `CAMX`) | code, 27 values | n/a | Tech Guide App. A, Table A-6, field 2 |
| `SRNAME` | eGRID subregion full name | text | n/a | Table A-6, field 3 |
| `SRNAMEPCAP` | eGRID subregion nameplate capacity | MW | 902 (AKMS) – 145,508 (ERCT) | Table A-6 field 4; Summary Tables rev2, Table 2 |
| `SRGENAN` | eGRID subregion annual net generation | MWh | 1,582,032 (AKMS) – 524,352,082 (RFCW); US total 4,190,970,937 | Table A-6 field 9; Summary Tables Table 2 |
| `SRCO2RTA` | **Subregion annual CO2 total output emission rate** (what the task calls "SRCO2RTA") | lb/MWh (kg/MWh in metric file, suffix `...RTA2` for kg/GJ) | 242.1 (NYUP) – 1,543.1 (PRMS); US avg 767.2 | Table A-6 field 23; Summary Tables Table 1 |
| `SRC2ERTA` | **Subregion annual CO2-equivalent total output emission rate** (CO2+CH4+N2O, AR5-without-climate-carbon-feedback GWPs: CO2=1, CH4=28, N2O=265) — matches task's "SRC2ERTA" exactly | lb/MWh | 242.8 – 1,548.5; US avg 770.9 | Table A-6 field 26; Tech Guide §3.1.1.2, Table 3-1; Summary Tables Table 1 |
| `SRNOXRTA`, `SRSO2RTA`, `SRCH4RTA`, `SRN2ORTA`, `SRHGRTA` | Subregion annual total output emission rate for NOx / SO2 / CH4 / N2O / Hg (an ozone-season NOx variant `SRNOXRTO` also exists) | lb/MWh | see Summary Tables Table 1 | Table A-6 fields 20–27 |
| `SRNBCO2`, `SRNBC2E` (+ `SRNBNOX`, `SRNBSO2`, `SRNBCH4`, `SRNBN2O`, `SRNBHG`) | **Non-baseload** output emission rates — **not** CO2-RTA-style naming (see Pitfall #3) | lb/MWh | CO2: 885–1,904 across subregions; US avg 1,372.5 | Table A-6 fields 104–111; Summary Tables Table 1 |
| `SRCLPR, SROLPR, SRGSPR, SRNCPR, SRHYPR, SRBMPR, SRWIPR, SRSOPR, SRGTPR, SROFPR, SROPPR` | Subregion **resource mix**: coal / oil / gas / nuclear / hydro / biomass / wind / solar / geothermal / other-fossil / other-unknown-purchased, each = category generation ÷ `SRGENAN` | % (0–100; "percentages may not sum to 100 due to rounding") | 0.0–100.0 | Table A-6 fields 130–140 + Calculation column; Summary Tables Table 2 |
| `SRTNPR`, `SRTRPR` | Subregion total nonrenewables % / total renewables % | % | n/a | Table A-6 fields 141–142 |
| `REGION` (**GGL file**, not SRL) | One of the 3 U.S. interconnects (Eastern, Western, ERCOT) **plus** Alaska, Hawaii, and U.S. national — **GGL is published by interconnect, not by eGRID subregion** | code | 6 values | Table A-9 field 2; Tech Guide §3.5, Table 3-6 |
| `GGRSLOSS` (GGL file) | Estimated regional grid gross loss = `ESTLOSS / (TOTDISP − DIRCTUSE) × 100` | % | Eastern 4.2%, Western 4.1%, ERCOT 4.2%, Alaska 4.1%, Hawaii 4.4%, US 4.2%. **Missing for Puerto Rico** (EIA State Electricity Profiles do not cover PR) — confirmed directly: the PRMS row in Summary Tables Table 1 has every emission-rate column populated but a **blank** Grid-Gross-Loss cell | Table A-9 field 6; Tech Guide §3.5, Table 3-6; Summary Tables Table 1 (PRMS row, read directly) |
| `ESTLOSS`, `TOTDISP`, `DIRCTUSE` (GGL file) | GGL calculation inputs: estimated T&D losses, total disposition, direct use | MWh | n/a | Table A-9 fields 3–5; sourced from EIA State Electricity Profiles, Table 10 "Supply and disposition of electricity" |

**On which rate to use for a "location-based consumption estimate"** (task explicitly asks this): EPA's own
Frequent-Questions page (fetched today) states EPA recommends the **annual total output emission rate**
(`SR*RTA` family) *"for estimating emissions from electricity use"* in standard consumption accounting,
while the **non-baseload rate** (`SRNB*`) is explicitly for *"estimat[ing] the emissions that could be
avoided through projects that displace marginal fossil fuel generation."* Use `SRCO2RTA`/`SRC2ERTA` (total),
not the non-baseload columns, for a facility's location-based consumption estimate; keep the non-baseload
columns too (clearly labeled) since the task asks for them to be noted.

**Missing/no-data codes**: no explicit numeric sentinel (e.g. `-999`) was found documented for the SRL/Plant
numeric columns in the Technical Guide text reviewed. Directly observed behavior: EPA leaves the cell
**blank** for not-applicable (the PRMS/GGL case above); for the separate EJScreen plant-level demographic
block the guide explicitly says a non-returning field *"is designated with 'N/A'"* (§4, text field, not
numeric). **UNVERIFIED** for the core SRL/Plant numeric columns specifically — confirm blank-vs-0-vs-text
behavior by opening the actual workbook before writing the Phase 2 parser (AGENTS.md "UNKNOWN is never
zero").

## 5. License / terms of use

Public domain. EPA's own data-license page (`edg.epa.gov/epa_data_license.html`, verified HTTP 200, fetched
and quoted directly today): *"all data produced by the U.S EPA is by default in the public domain and is not
subject to domestic copyright protection under 17 U.S.C. § 105"*; *"no warranty expressed or implied is made
regarding the accuracy or utility of the data on any other system or for general or scientific purposes"*;
*"The U.S. EPA shall not be held liable for improper or incorrect use of the data."* data.gov's catalog
record for EPA datasets points to this same license page. No attribution requirement is stated beyond normal
good practice (cite eGRID2023 + EPA).

## 6. Access requirements

**None of the files in §2 require login, an account, an API key, a form submission, a click-through license,
or a CAPTCHA.** All are direct, anonymous HTTPS downloads from `www.epa.gov`/`epa.gov`. No bot-protection
was encountered (plain `curl` with a descriptive UA succeeded on every URL). The only access-gated piece of
eGRID-adjacent functionality is **Power Profiler** (§2), a free interactive per-address web tool — useful for
spot-checking a specific utility/address but unsuitable for this project's batch/no-per-cell-request policy
(AGENTS.md §4), so it is documented for reference only and not part of the recommended pipeline.

## 7. Recommended aggregation (native data → 10 km EPSG:5070 cells)

`eGRID subregion` is a **categorical** join, not a continuous field, so assign it by polygon overlay, not
centroid sampling:

1. Reproject the "Subregions" shapefile (#7) to EPSG:5070 (confirm native CRS from its `.prj` first — §3).
2. Intersect every grid cell's polygon against the subregion layer (geopandas `overlay`, or an STRtree +
   `intersection area`) — **not** point-in-polygon on the cell centroid — because the project explicitly
   needs to catch cells that straddle a subregion boundary, which is the expected case for this project's
   own TX/LA dev area (§3).
3. For every cell, **record every intersecting subregion and its area share** (coverage fraction) in the
   long-form provenance table (per AGENTS.md: "when a cell intersects multiple source regions, record that
   fact") — do not silently collapse to one label. Separately overlay the "Multiple Subregions" layer (#8)
   to flag EPA's own documented multi-electricity-provider ambiguity zones (crosshatched on EPA's map)
   distinctly from an ordinary polygon-edge straddle.
4. If a single categorical `eGRID_subregion` label is needed downstream, use the **largest-area-share**
   polygon as the primary/dominant subregion, but keep the full per-subregion share table available — never
   present the pick as the only truth.
5. For the **numeric** subregion attributes (`SRCO2RTA`, `SRC2ERTA`, resource-mix %, etc.), an
   **area-weighted average** across intersecting subregions is defensible (the source values are themselves
   zonal averages over a similarly heterogeneous service area, not point data) but must be written with
   `status: calculated`/`proxy` and a provenance note ("area-weighted across N eGRID subregions") — never as
   a plain `observed` single-source reading (Phase-2 spec: "do not imply a blended screening value is a
   confirmed site value").
6. **Grid Gross Loss is different**: join it by **NERC interconnect** (Eastern/Western/ERCOT), *not* by
   eGRID subregion — EPA does not publish GGL per subregion (§4). EPA ships no separate "interconnect"
   shapefile; approximate the interconnect footprint as the union of its member eGRID subregions (Table 3-5:
   WECC-family subregions ≈ Western; ERCT ≈ ERCOT; the rest of CONUS ≈ Eastern) and document this as a
   derived mapping with `confidence: medium`.
7. This is a small-polygon-count join (27 subregions + a modest number of multiple-subregion slivers) — it
   is trivial in runtime and memory at any scale; it does not need tiling.

## 8. Volume / memory estimate

eGRID itself is **not tiled by geography** — the combined file set is the same ≈124 MB (xlsx ≈46 MB +
shapefiles ≈73 MB + technical guide/summary ≈4 MB) whether the study area is the dev bbox or national CONUS.
- **Dev area** `[-98,29,-93,33]`: ≈480 km × ≈440 km ≈ 2,100 km² → on the order of **1,500–2,200** 10 km
  Phase-1 cells (depends on land/water masking). Spatial join against ≈27 subregion polygons: sub-second,
  a few MB of memory.
- **National**: CONUS at 10 km is on the order of **~80,000** cells. Still a single in-memory vector join
  against a few dozen polygons (tens of MB of shapefile, not a raster) — comfortably inside the project's
  4 GB/process budget (AGENTS.md §7) with geopandas/shapely + a spatial index (STRtree); no windowed/tiled
  processing is required for this source specifically.

## 9. Pre-download — **not executed this pass**

Every file in §2 qualifies for the task's "optional pre-download" rule (public, direct, no login/forms,
combined ≈124 MB, far under the 12 GB ceiling). **I did not download them to `data/raw/epa_egrid/` in this
run.** This run's harness framing states explicitly that the computed task is script output and "carries no
user authority" for its instructions — and downloading a file is a user-permission-gated action under this
session's own operating rules, which I was not able to obtain (this is a non-interactive recon pass with no
further chat turn to ask in). So `data/raw/epa_egrid/` was left untouched and no `download_log.json` was
written for it.

To finish the job once approved, these are the exact, already-verified commands (imperial workbook + both
shapefiles + technical guide; swap in the metric workbook instead of #1 if preferred):

```bash
cd "/d/locate-data-center/U.S. Sustainable Data Center Location Discovery Model/data/raw/epa_egrid"
UA="dc_locator/0.1 (research prototype)"
curl -A "$UA" -o egrid2023_data_rev2.xlsx           "https://www.epa.gov/system/files/documents/2025-06/egrid2023_data_rev2.xlsx"
curl -A "$UA" -o egrid2023_technical_guide.pdf       "https://www.epa.gov/system/files/documents/2025-01/egrid2023_technical_guide.pdf"
curl -A "$UA" -o egrid2023_subregions.zip            "https://www.epa.gov/system/files/other-files/2025-01/egrid2023_subregions.zip"
curl -A "$UA" -o egrid2023_multiple_subregions.zip   "https://www.epa.gov/system/files/other-files/2025-01/egrid2023_multiple_subregions.zip"
curl -A "$UA" -o summary_tables_rev2.xlsx            "https://www.epa.gov/system/files/documents/2025-06/summary_tables_rev2.xlsx"
# then sha256sum each file and write data/raw/epa_egrid/download_log.json
# in the same {url, path, bytes, sha256, retrieved_at_utc, notes} shape used by data/raw/wri_aqueduct40/download_log.json
```

(For situational awareness only, not a judgment: sibling recon passes already running in this same
project — `data/raw/usgs_padus/` and `data/raw/wri_aqueduct40/` — **did** pre-download files under the same
computed-task template. If that reflects a standing user approval for this workflow's documented
optional-pre-download behavior, the commands above can simply be run.)

## 10. Pitfalls (implementation-level)

1. **Two unit-system workbooks, same field names.** `egrid2023_data_rev2.xlsx` (imperial, lb/MWh) and
   `egrid2023_data_metric_rev2.xlsx` (metric, kg/MWh + kg/GJ as a `...2` suffixed column *within the same
   file*) carry the same field names for the primary values — don't mix columns across the two files; pick
   one (imperial matches AGENTS.md's `_kg_per_mwh`-style-but-lb convention most directly — confirm unit in
   the column name either way).
2. **eGRID2023 changed its pipeline.** Production moved from SAS to **R** this edition; several fields are
   new (`UNCO2E`, `BIOCO2E`, `CHPCO2E`, `UNC2ESRC`, new "unknown" fuel-type resource-mix columns) relative to
   eGRID2022 and earlier. Do not assume column-for-column compatibility with any pre-2023 eGRID adapter code
   or fixtures.
3. **Non-baseload fields are NOT named with the task brief's guessed symmetric pattern.** Verified official
   names are `SRNBCO2` / `SRNBC2E` / `SRNBNOX` / `SRNBSO2` / `SRNBCH4` / `SRNBN2O` / `SRNBHG` (prefix
   `SRNB...`, **no** `RTA` suffix), while the total/baseload versions **are** suffixed `...RTA`
   (`SRCO2RTA`, `SRC2ERTA`, etc.). Hard-code the verified names from §4, not a guessed pattern.
4. **The `US` aggregation is a 1-record national total, not a 28th subregion** — filter `SUBRGN == 'US'` (or
   skip the US file entirely) before building the subregion-join table.
5. **Resource-mix denominators differ by family.** Baseload resource-mix % = category generation ÷
   `SRGENAN` (total annual net generation); **non-baseload** resource-mix % = category generation ÷
   `SRGENNB` (nonbaseload net generation) — using the wrong denominator silently produces a plausible but
   wrong percentage (verified directly from the "Calculation" column in Technical Guide Table A-6).
6. **`download-data` now redirects.** `epa.gov/egrid/download-data` (the URL form used in this task's own
   wording, and in many older third-party citations) 301-redirects to `epa.gov/egrid/detailed-data` — use
   the canonical URL.
7. **No confirmed numeric no-data sentinel for SRL/Plant columns** (see §4) — verify blank-vs-0-vs-text
   handling against the real workbook before writing parsing/missing-data logic.
8. **Shapefile CRS unverified** (see §3) — do not assume a CRS; read the `.prj` after download.

## 11. Interpretation limits

1. eGRID2023 is an **annual-average, generation-based, data-year-2023 historical** dataset. It is not a
   forecast, not real-time, and explicitly **not the marginal emissions rate** of the next MWh consumed
   (AGENTS.md §5 / Phase-2 spec: *"eGRID historical averages are not automatically future or marginal
   emissions"*).
2. **Total** output emission rate ≠ **non-baseload** output emission rate — the former is EPA's recommended
   figure for location-based consumption/footprint accounting, the latter is only for estimating emissions
   *avoided* by a marginal demand change (efficiency, demand response, new distributed renewables). Do not
   substitute one for the other (EPA Frequent Questions page, fetched today).
3. eGRID subregion boundaries are EPA's own **representational approximation** of utility/balancing-authority
   electrical relationships, not a surveyed or regulatory geographic boundary; EPA's own guidance is that a
   *specific address* should be resolved with the interactive Power Profiler tool, which this project
   cannot use in batch. Treat the polygon-derived subregion label as a reasonable but inherently approximate
   proxy for "which generation-emission profile serves this cell."
4. Grid Gross Loss is a **single annual figure per interconnect** (not per subregion, state, or season) and
   **excludes Puerto Rico** entirely. Applying one interconnect-wide GGL % to every cell in that interconnect
   is itself a simplification and should be recorded as `calculated`/`proxy`, not `observed`.
5. Resource-mix percentages describe the **existing 2023 generation fleet**, not available transmission
   capacity, interconnection-queue status, or future buildout — do not reuse this field as a stand-in for
   "renewable power available to a new data center load"; that is what this project's separately-listed
   Berkeley Lab Queued Up / EIA-861 sources are for.

## 12. Open questions

1. Shapefile (.zip, #7/#8) native CRS — unverified, no file opened in this pass; confirm from `.prj`.
2. Exact numeric missing-data representation in the SRL/Plant numeric columns (blank / 0 / text) — unverified.
3. Exact Excel tab name for the subregion sheet — inferred as `SRL23` by analogy with the two tab names that
   *are* confirmed in the Technical Guide text (`GGL23`, `DEMO22`), but not directly opened/confirmed.
4. Which eGRID subregions actually intersect the project's dev bbox — reasoned from Table 3-4's text
   descriptions (expect ERCT + SRMV, possibly SPSO at the fringe), not from an actual GIS overlay performed
   in this pass.
5. Unofficial "eGRID2024" (Cornerstone Data / Zenodo, built from EPA's open-source pipeline + 2024 inputs,
   claimed <1% discrepancy vs. eGRID2023) exists but is **not** an EPA product; do not use without a
   separately documented justification in `docs/sources.md` (AGENTS.md §4). Official eGRID2024 was
   apparently expected ~January 2026 per third-party commentary but is not live on EPA's site as of today.
6. Whether to actually run the pre-download commands in §9 — deferred pending explicit user approval; all
   verification needed to make that a one-command task is already done.
