# cooling_designs_pue_wue — evidence extraction for Phase 3 cooling designs (annual PUE, site WUE, climate dependence, peak PUE)

Prepared for the dc_locator technical lead by a research subagent (claude-sonnet-5-5).
Retrieval window: 2026-10-03 02:45–03:50 UTC (local 2026-10-02 22:45–23:50). Project root:
`D:\locate-data-center\U.S. Sustainable Data Center Location Discovery Model`.
Companion files: `docs/research/phase3/cooling_designs_zone_quantiles_derived.csv` (derived table, see §5.4);
cached sources and checksums: `data/raw/_literature/` (`download_log.json`, `download_log_cooling_designs_pue_wue.json`).

**How to read the evidence labels used in every table**

| label | meaning |
|---|---|
| **V** | number printed in a retrieved document (text, table, data label) or stored in a retrieved data file; copied unchanged |
| **D** | digitized by me from a raster figure that carries no numbers (pixel analysis, precision about ±0.01 PUE / ±0.02 L/kWh); approximate |
| **C** | computed by me from a retrieved data file with a stated formula (reproducible); NOT a published number |
| **S** | secondary citation (a retrieved document quoting another document I could not retrieve) |
| **UNVERIFIED** | could not be checked against a primary document |

Rules followed: no number comes from memory; vendor sources are flagged `VENDOR`; no log-in, form, CAPTCHA or bot-wall was
bypassed (ScienceDirect, IOP, eScholarship PDFs and the LBNL datacenters site returned 403/challenges and were not circumvented);
no downloaded code was executed and no pickle file was downloaded or loaded.
Quotations are kept to a minimum on purpose (copyright); every number carries a page/table/figure locator so it can be re-checked
in the cached copy.

---

## 0. Executive summary

1. **A documented climate-dependent relationship exists, but only at climate-zone resolution and only as tables/samples, not as a closed-form
   function and not per grid cell.** It is the Lei & Masanet hourly physics model (annual PUE and annual site WUE, simulated hour by hour from typical-meteorological-year
   weather of one representative city per IECC/ASHRAE climate zone, 50 Latin-hypercube "operating-practice" samples per design and zone).
   - The peer-reviewed article (Resour. Conserv. Recycl. 182:106323, 2022) is paywalled and **was not retrievable**
     (ScienceDirect returns an anti-bot 403; OpenAlex marks it closed with no repository copy). What *was* retrieved: the open CC BY 4.0 preprint v1
     (Research Square rs-769999, Aug 2021: full equations, assumptions, per-zone result figures), the authors' public GitHub code/data
     (no licence file), and two open-access 2025 LBNL papers that re-use the model (one of them with 16 cooling cases incl. IT liquid cooling).
     Therefore every number below is either from those retrieved documents/data files or computed from them; none was checked against the published 2022 tables.
   - **Climate input needed:** one IECC/ASHRAE climate zone per grid cell (thermal zone 1–8 plus moisture A/B/C), obtained from county FIPS via the PNNL
     county map (cached; §8). The underlying physical model additionally needs hourly dry-bulb temperature, relative humidity and pressure (TMY) per
     site; the Phase 2 NOAA normals (monthly/daily mean temperature only) cannot drive it.
   - **No documented function maps wet-bulb hours to PUE/WUE.** The only wet-bulb-hour statement found is a DOE rule of thumb for *when a waterside economizer is suitable*
     (wet-bulb below 55 °F for 3,000 or more hours per year, DOE/FEMP guide 2024, PDF p.28) — an applicability criterion, not a PUE/WUE relation.
2. **Annual PUE and site WUE per design** (pooled over the 15 CONUS zones, 750 samples each; **C** from the 2025 sample data; medians quoted). The pooled medians agree
   with the LBNL 2024 national study's Fig. 4.4 (digitized, **D**) to about ±0.01 PUE and ±0.05 L/kWh for most rows (§5.5), and with measured PUE of a 5A water-cooled facility (§6).
   Large-scale (hyperscale-practice) designs: AE+adiabatic with air-cooled-chiller backup PUE **1.17** / WUE **0.02**; AE+adiabatic with water-cooled-chiller backup **1.14** / **0.34**
   (strongly zone dependent, median 0.06 in zone 8 up to 1.46 in 2A); waterside economizer + water-cooled chiller + towers **1.12** / **2.19**; IT liquid cooling (cold plate) with waterside economizer + towers
   **1.13** / **1.96**; IT liquid cooling with dry cooler + adiabatic assist **1.10** / **0.16**; dry cooler + adiabatic assist (air-cooled IT) **1.20** / **0.28**.
   Mid-size air-cooled designs are far worse in PUE (1.58–1.84) because the mid-size cases assume ordinary operating practice, not because of the heat-rejection type (§5.6).
3. **Peak (design-day) PUE is NOT documented per design in any retrieved source.** Closest evidence: (i) the Lei–Masanet model is hourly but only annual means were published;
   (ii) ASHRAE 90.4 Addendum g (2019) distinguishes design vs annualized mechanical-load component and gives code *ceilings* by climate zone (e.g. zone 1A: max MLC 0.26 + max ELC 0.297, §7);
   (iii) vendor-measured quarterly PUE shows the summer quarter about 2 % above the trailing-twelve-month value for the fleet and the median campus and up to 7 % at the worst of 31 campuses (Google fleet 1.11 vs 1.09; Storey County NV 1.22 vs 1.14; §7) — quarterly means, not design hours.
   A peak PUE must therefore be an explicit `scenario` assumption.
4. **Metric boundaries differ and matter** (§2): the Lei–Masanet WUE counts cooling-tower evaporation **plus drift plus blowdown (draw-off)** plus adiabatic and humidification water, i.e. site water *use* (make-up) rather
   than strictly evaporated consumption; Meta's reported WUE is **withdrawal**-based; the LBNL 2016 figure of 1.8 L/kWh is per kWh of **total facility** energy; and the LBNL 2024 national-average WUE (0.36–0.375 L/kWh) is
   numerically consistent with water divided by **total** facility electricity, not IT electricity (§4.6) — do not use it as a per-IT-kWh value.
5. **Design-vs-size confounding.** In the source data, "large-scale" cases carry hyperscale operating practice (UPS 90–99 %, wide thermal envelope), "mid-size" and "small" cases carry ordinary practice. The dataset has
   no large-scale "air-cooled chiller + airside economizer without adiabatic" and no large-scale "water-cooled chiller without economizer"; all simulated designs include a supplementary chiller (no chiller-less design; NREL's measured
   chiller-less facility lies below the model's 5th percentile, §6).

---

## 1. What was retrieved and what was not

| item | status | how / why |
|---|---|---|
| LBNL 2024 US Data Center Energy Usage Report (LBNL-2001637) | **retrieved** | `eta-publications.lbl.gov/.../lbnl-2024-united-states-data-center-energy-usage-report_1.pdf`, 4,031,183 B (the URL without `_1` 301-redirects to eScholarship, which returned 403 to curl) |
| Lei & Masanet 2022, RCR 182:106323 (published article) | **NOT retrievable** | ScienceDirect 403 (Cloudflare challenge, not bypassed); OpenAlex `is_oa=false`, no repository full text; Semantic Scholar `isOpenAccess=false`, no abstract; Crossref deposits only the reference list |
| Lei & Masanet preprint v1 (Research Square rs-769999, 2021-08-03, CC BY 4.0) | **retrieved** | full text incl. equations, Tables 1–3, Figures 1–6 (figures only for results) |
| Authors' GitHub: Data-Center-Water-footprint (code + `Simulation Results/UE.xlsx`) | **retrieved (read only)** | no licence file; HEAD `2cc53bee…` (2025-07-31); `.pkl` COP regressors NOT downloaded; nothing executed |
| Lei, Lu, Shehabi, Masanet 2025, RCR 219:108310 (accepted manuscript, OSTI 2572888, CC BY) + repo `UEs_16cases.csv` | **retrieved** | 19,000 sample rows; 16 cooling cases incl. IT liquid cooling; 19 climate zones; repo HEAD `155b0216…` |
| Lei, Ganeshalingam, Masanet, Smith, Shehabi 2025, Energy & Buildings 339:115734 (OSTI 3398559, CC BY) + repo `UE_by_CZ_CS.csv`, `climate_zones.csv` | **retrieved** | 5-quantile PUE/WUE by zone and design; repo HEAD `322e1601…` |
| Lei et al. 2023, J. Phys.: Conf. Ser. 2600:172003 (hyperscale geospatial water footprint) | **NOT retrievable** | IOP bot-manager redirect (not bypassed). Its sample workbooks exist in the authors' repo (`Geospatial-assessment…`, HEAD `56c1a9cc…`) and were inspected only for structure (each row is one hourly-condition evaluation for a sampled parameter set, a layout consistent with a Sobol/Saltelli design; not usable as a lookup) |
| The Green Grid WP#35 (WUE), 2011 | **retrieved** | `thegreengrid.org/system/files/store/WUE_v1.pdf`, 333,876 B |
| The Green Grid WP#49 (PUE), ISO/IEC 30134-2 and -9, ASHRAE 90.4 base standard, ASHRAE Thermal Guidelines 5th ed. | **NOT retrieved** | member-only/paywalled (LBNL page hosting WP#49 returned 403); PUE/WUE definitions taken from WP#35, DOE/FEMP guide 2024, LBNL 2024; ISO WUE definition only as secondary citation (arXiv 2607.02531) |
| DOE/FEMP Best Practices Guide for Energy-Efficient Data Center Design (rev. July 2024) | **retrieved** | |
| Uptime Institute Global Data Center Survey 2025 (keynote report) | **retrieved** | |
| NREL ESIF reports (TP-7A40-72196, PR-7A40-74464) | **retrieved** | `nrel.gov` no longer resolves from this machine (NXDOMAIN); files fetched from `docs.nlr.gov` (NREL appears to have moved to nlr.gov) |
| Sharma et al. 2017 (MGHPCC), IEEE Internet Computing | **retrieved** (authors' copy at UMass) | |
| ASHRAE 90.4 Addendum g (2016 ed., 2019) and Addendum g (2022 ed., 2024); ASHRAE TC 9.9 liquid-cooling white paper (2021) | **retrieved** | copyrighted "personal use" files: only a few numbers are reproduced here |
| LBNL 2016 report (LBNL-1005775) | **retrieved** | OSTI purl 1372902 |
| Google, Meta, Microsoft pages/reports | **retrieved, VENDOR** | self-reported |
| PNNL/DOE climate-zone county data (shapefile) and Building America guide v7.3 | **retrieved** | |
| Koomey blog (fleet WUE/PUE of top-20 operators), ORNL ESIF news item | read through the WebFetch summariser only | not cached; treated as pointers, UNVERIFIED |

---

## 2. Metric definitions and system boundaries (what a "PUE" or "WUE" number means in each source)

| source (locator) | PUE | WUE | water basis / what is inside the boundary | time basis |
|---|---|---|---|---|
| The Green Grid WP#35, 2011 (PDF pp.4–7, Eq. 1–4, §III; Table A-1 p.11) | not defined there beyond reference to WP#22; total facility energy = IT + power delivery (UPS, switchgear, generators, PDUs, batteries, losses) + cooling (chillers, CRACs, pumps, towers) + misc (lighting); IT energy = equipment that manages, processes, stores or routes data (p.7) | **WUE = annual site water usage ÷ IT-equipment energy, L/kWh** (Eq. 2); **WUEsource = EWIF × PUE + WUE** (Eq. 4) | site water includes humidification and water consumed for cooling, explicitly listing cooling-tower evaporation, blowdown and drift (p.7); off-site generation water only in WUEsource; life-cycle water excluded; ideal values PUE 1.0, WUE 0.0, no theoretical upper bound (p.4) | annual |
| DOE/FEMP Best Practices Guide, rev. 2024-07 (PDF pp.38–39, printed 29–30) | ratio of total annual facility energy to total annual IT energy; benchmark labels Standard 1.6 / Good 1.4 / Better 1.1 | site WUE = annual site water usage ÷ annual IT energy (L/kWh) | not detailed | annual (explicitly credits annual averaging for free-cooling savings) |
| LBNL 2024 (PDF p.39) | total electricity demand of the data center ÷ electricity demand of IT equipment | total water consumption of the data center ÷ IT electricity demand; "WUE (site)" = on-site cooling water, versus "WUE (source)" = generation water | model includes cooling equipment plus UPS, power transformation/distribution, fans, pumps | annual average of simulations |
| Lei & Masanet preprint (PDF pp.10–12, Eq. 1–13) | hourly PUE = total DC power ÷ IT power (Eq. 3, 10); components: IT, UPS loss, distribution loss, lighting, isothermal humidifier, pumps, fans, chiller (DX counted as chiller) | hourly WUE = 3600 × water rate ÷ IT power (Eq. 11), L/kWh | water rate = cooling tower **(evaporation + windage + draw-off/blowdown)** + adiabatic (direct evaporative) cooling + space humidification (Eq. 1, 5–9); draw-off = evaporation/(cycles−1) − windage (Eq. 7) | annual value = arithmetic mean of 8,760 hourly values (Eq. 12–13). The authors' code sets IT power = 1 (constant) in every hour (**C**, from `simulation_funs_DC.py`), so mean of hourly ratios = ratio of annual sums |
| Lei et al. 2025 review (PDF pp.9–10) | same model | "WUE-site" counts adiabatic cooling, humidification and cooling-tower water: evaporation for heat removal, windage and draw-off (blowdown) | confirms blowdown is inside the number | annual averages |
| NREL TP-7A40-72196, 2018 (PDF pp.10, 17–18) | total system input energy ÷ IT input energy | water use (L) ÷ IT input energy (kWh) | measured: city-water meters + estimated filter blowdown; cooling-tower cycles of concentration 12.8; makeup-air-unit humidification water NOT metered/included | first full year (2016-09-01 to 2017-08-31) |
| Meta 2025 Environmental Data Index (PDF p.18) | energy consumed at the data center ÷ IT load | **water withdrawal** (L) ÷ IT load (kWh) — not consumption | consumption reported separately, estimated as withdrawal minus discharge or from cycles of concentration | annual, fleet |
| Microsoft datacenters page; blog 2024-12-09 | total energy for facility ÷ energy used for computing | annual litres for humidification and cooling ÷ annual IT kWh; blog text says "consumption" while its own footnote says "withdrawal WUE" (ambiguous) | VENDOR | fiscal year, fleet |
| Uptime Institute 2025 (PDF p.7) | total facility power ÷ IT power; self-reported annual PUE, weighted average | — | PUE explicitly excludes water | annual |
| LBNL 2016 (PDF p.37, printed p.28) | — | **1.8 L (0.46 gal) per kWh of TOTAL data-center site energy** for all but closet/room data centers (DX) | cooling-tower evaporation, drift, blowdown | annual, national assumption |

Consequences for the Phase 3 formulas (`W_site = E_IT × WUE`, `E_facility = E_IT × PUE`): the sources' WUE is already per **IT** kWh (do not multiply by PUE again),
except the LBNL 2016 constant (per total kWh) and, numerically, the LBNL 2024 national average (§4.6). PUE/WUE from the Lei–Masanet model are annual means at constant IT load: **no source documents how PUE or WUE change with IT utilization**
(the load factor 0.80 in the project spec is therefore not a documented input of these values; UNVERIFIED whether any utilization was assumed beyond the sampled "chiller partial load factor" parameter, Table 3 of the preprint).

---

## 3. Mapping of the five Phase 3 cooling designs onto documented simulation cases

"Design" in the sources = IT-side heat transport + economizer + supplementary cooling + heat rejection. All Lei–Masanet cases include a supplementary chiller that runs only when free cooling cannot meet the load (parentheses in the source names).

| project design | heat transport | economizer / heat rejection | source case (2025 sample data `case_original`; size class) | LBNL 2024 Table 4.2 / Fig. 4.4 name | preprint case no. (2021) |
|---|---|---|---|---|---|
| (a) air-cooled chiller / dry cooler with airside economization, no evaporative water | air to rack | airside economizer or dry cooler; air-cooled chiller backup | **6** (mid, AE + air-cooled chiller), **7** (mid, air-cooled chiller), **17** (mid, dry cooler + air-cooled chiller), **9** (small); closest large-scale analogue **0** (AE + *sporadic* adiabatic, air-cooled chiller backup; WUE 0.004–0.05) | "Airside economizer (air-cooled chiller)", "Air-cooled chiller", "Dry cooler (air-cooled chiller)"; large: "Airside economizer & adiabatic cooling (air-cooled chiller)" | 6, 7, 9 (case 0 is new in 2025) |
| (b) water-cooled chiller with evaporative cooling tower (+ waterside economizer) | air to rack | cooling tower; waterside economizer in front of the water-cooled chiller | **5** (mid), **4** (mid, WSE), **2** (large, WSE), **8** (small); hybrid **3** (mid, AE + WCC backup) | "Water-cooled chiller", "Waterside economizer (water-cooled chiller)" | 5, 4, 2, 8, 3 |
| (c) direct / indirect evaporative (adiabatic) air cooling | air to rack | airside economizer with direct adiabatic (evaporative) humidification of outside air; chiller backup | **1** (large, AE + adiabatic, water-cooled chiller backup), **0** (large, air-cooled chiller backup); **18** (large, dry cooler with adiabatic assist = evaporatively pre-cooled dry heat rejection) | "Airside economizer & adiabatic cooling (water-/air-cooled chiller)", "Dry cooler with adiabatic assist (air-cooled chiller)" | 1 |
| (d) direct-to-chip liquid with dry coolers | liquid (cold plate; also RDHx, immersion scenarios) | dry cooler with adiabatic assist; air-cooled chiller backup | **16_2** (cold plate; suffix mapping inferred, §5.8); 16_1 = RDHx, 16_3 = immersion. Pure dry cooler without adiabatic assist: only in LBNL Fig. 4.4 ("IT liquid cooling: dry cooler (air-cooled chiller)") | "IT liquid cooling: dry cooler with or without adiabatic assist (air-cooled chiller)" | — |
| (e) direct-to-chip liquid with evaporative heat rejection | liquid (cold plate) | waterside economizer + cooling tower; water-cooled chiller backup | **15_2** (cold plate; suffix mapping inferred); 15_1 RDHx, 15_3 immersion | "IT liquid cooling: waterside economizer (water-cooled chiller)" | — |
| baseline (not requested) | air | direct expansion | **10** (small), **11** (mid) | "Direct expansion" | 10 |

Facility-water supply temperatures assumed for the liquid scenarios (ASHRAE liquid classes): RDHx 2–32 °C, cold plate (direct to chip) 2–40 °C, immersion 2–45 °C (review SI Table S6.1, PDF p.53/54; **V**). LBNL 2024 Table 4.3 assigns ASHRAE class W45 to "AI (IT liquid cooling)", thermal envelope A1 to internal/colocation, A2 to hyperscale and AI air-cooled (PDF p.43; **V**). ASHRAE TC 9.9 (2021) renamed the water classes W17, W27, W32, W40, W45, W+ (upper supply temperature in °C, lower limit 2 °C; PDF p.8; **V**).
Indirect evaporative CRAC units (IEC) are named in the ASHRAE 90.4 addendum but **no PUE/WUE numbers for them were found** (gap).

---

## 4. LBNL "2024 United States Data Center Energy Usage Report" (Shehabi et al., LBNL-2001637, 19 Dec 2024)

Citation: Shehabi A., Smith S.J., Hubbard A., Newkirk A., Lei N., Siddik M.A.B., Holecek B., Koomey J.G., Masanet E.R., Sartor D.A. (2024), *2024 United States Data Center Energy Usage Report*, Lawrence Berkeley National Laboratory.
URL (retrieved): https://eta-publications.lbl.gov/sites/default/files/2024-12/lbnl-2024-united-states-data-center-energy-usage-report_1.pdf — 4,031,183 B, sha256 `3a2257cd…c2eb`, 79 PDF pages.
Page numbers below are PDF page = printed page for pp.38 onward (front-matter printed numbers are PDF−1).

### 4.1 What the report actually provides (and what it does not)

* PUE and site WUE are **simulated**, not surveyed, with the Lei–Masanet thermodynamic model (p.39): 18 simulation cases (space type × cooling system), 50 operating scenarios per case, TMY weather from **965 U.S. weather stations**, >1 million simulations (pp.39–40, 43). Figure 4.4 draws 17 case rows (not 18; discrepancy not explained in the report).
* The report says the simulation results were reviewed by industry experts and then adjusted toward industry-reported PUE/WUE until they matched expected ranges (p.43) — the published ranges are therefore **expert-adjusted**, not raw model output.
* Simulated PUEs assume facilities are commissioned and operated as designed; the authors state that real PUE and WUE will likely be worse than simulated (p.44). The median of the uncertainty range is taken as representative through 2023; for 2024–2028 the space-type PUE/WUE are varied ±10 % (p.44).
* Range semantics (p.44): lower limits = best-practice efficiency in favourable climates; upper limits = poor efficiency in hot-humid climates. So the Fig. 4.4 spread mixes *operating practice* and *climate*; **no per-climate-zone or per-station PUE/WUE table is published** in the report, and the report carries no data/code availability statement (searched).
* The distribution of cooling systems over space types (Fig. 4.2, 2023) was built from Dell'Oro revenue data plus an expert-constrained optimisation (p.38). Fig. 4.2 is a stacked bar without numbers; read visually (not digitized): hyperscale is dominated by the two "airside economizer & adiabatic cooling" systems, AI-specialized splits between those and the IT-liquid systems, small is mostly direct expansion.

### 4.2 Table 4.2 (cooling-system taxonomy, PDF pp.40–42, **V** text) — nine system families

Direct expansion (CRAC); air-cooled chiller; water-cooled chiller; airside economizer (air- or water-cooled chiller backup); waterside economizer (water-cooled chiller); dry cooler with or without adiabatic assist (air- or water-cooled chiller);
airside economizer & adiabatic cooling (air- or water-cooled chiller); **IT liquid cooling: dry cooler with or without adiabatic assist (air-cooled chiller)**; **IT liquid cooling: waterside economizer (water-cooled chiller)**.
Notes in the table (p.42): parentheses mark a supplementary system that may not run in favourable climates; names not beginning with "liquid cooling" are air-cooled IT. For the simulation the dry-cooler liquid case assumes an air-cooled chiller as backup and the liquid waterside-economizer case a water-cooled chiller (p.42).
The text states that the air-cooled chiller is the option where minimal on-site water is crucial (p.40), that dry coolers with adiabatic assist consume water mainly in wet mode when dry-bulb is high and wet-bulb low (p.41–42, 45), and that water-cooled chillers without economizers show the highest WUE (p.44).

### 4.3 Tables 4.1 and 4.3 (space types and model assumptions, PDF pp.36, 43, **V**)

Table 4.1 (PDF p.36) defines nine space types: telco edge, commercial edge, small and medium businesses (SMB), enterprise branch, internal (enterprise-run) data centers, communications service providers, colocation small/medium scale, colocation large scale, and hyperscale; Fig. 4.2/4.5 regroup them as Small, Midsize and Colo, Hyperscale and AI Specialized. Figure 4.4 uses the size labels Small, Midsize and Large-scale without mapping them explicitly to the Table 4.1 types.
Table 4.3 (PDF p.43; model assumptions on the major determinants of PUE and WUE by space type, incl. AI):

| space type | UPS efficiency | ASHRAE thermal envelope (2021) | ASHRAE liquid cooling class (2014) |
|---|---|---|---|
| Commercial edge, enterprise branch, SMB, telco edge | 77–85 % | "Recommended" | N/A |
| Comms SPs, internal, colocation sm/med, colocation large | 80–94 % | A1 | N/A |
| Hyperscale, AI (IT air cooling) | 90–99 % | A2 | N/A |
| AI (IT liquid cooling) | 90–99 % | N/A | W45 |

### 4.4 Figure 4.4 — simulated annual PUE and site WUE by cooling system and size (the only per-design numbers in the report)

Figure 4.4 (PDF p.46) is a seaborn box plot (green = Small, orange = Midsize, blue = Large-scale; box edges and median line plus whiskers) with **no printed numbers and no definition of the box/whisker percentiles**.
I digitized the embedded 1002×756 raster (pixel centres of the box edges, median line and whisker caps, calibrated on the gridlines; ±1 px ≈ ±0.005 PUE, ±0.014 L/kWh). Values are **D**. The right-hand columns are my **C** percentiles of the 2025 sample data (§5.4) for the matching case, shown only as a cross-check (they agree with the digitized medians and quartiles, not with the whiskers, which are wider because the LBNL figure spans 965 stations).
(Whisker-lo/hi = whisker caps; LBNL does not say whether they are extremes or 1.5×IQR fences — UNVERIFIED.)

**PUE (kWh/kWh, annual average)**

| size class (Fig. 4.4 legend) | system (Fig. 4.4 row label) | LBNL Fig 4.4, digitized: whisker-lo / Q1 / **median** / Q3 / whisker-hi | dc_locator-derived from 2025 sample data (15 US zones pooled): P5 / P25 / **P50** / P75 / P95 | source case_original |
|---|---|---|---|---|
| Small | Direct expansion | 1.657 / 1.954 / **2.049** / 2.185 / 2.533 | 1.841 / 1.950 / **2.053** / 2.195 / 2.386 | 10 |
| Small | Air-cooled chiller | 1.536 / 1.883 / **1.984** / 2.140 / 2.523 | 1.778 / 1.893 / **2.004** / 2.159 / 2.520 | 9 |
| Small | Water-cooled chiller | 1.440 / 1.637 / **1.697** / 1.768 / 1.964 | 1.567 / 1.639 / **1.704** / 1.773 / 1.891 | 8 |
| Midsize | Direct expansion | 1.435 / 1.755 / **1.853** / 1.989 / 2.341 | 1.629 / 1.754 / **1.860** / 2.000 / 2.191 | 11 |
| Midsize | Air-cooled chiller | 1.395 / 1.722 / **1.828** / 1.959 / 2.321 | 1.604 / 1.728 / **1.840** / 1.981 / 2.268 | 7 |
| Midsize | Dry cooler (air-cooled chiller) | 1.234 / 1.493 / **1.586** / 1.692 / 1.989 | 1.395 / 1.498 / **1.587** / 1.720 / 2.008 | 17 |
| Midsize | Airside economizer (air-cooled chiller) | 1.219 / 1.491 / **1.576** / 1.672 / 1.944 | 1.387 / 1.489 / **1.581** / 1.698 / 1.901 | 6 |
| Midsize | Water-cooled chiller | 1.289 / 1.461 / **1.521** / 1.581 / 1.763 | 1.395 / 1.458 / **1.529** / 1.591 / 1.678 | 5 |
| Midsize | Airside economizer (water-cooled chiller) | 1.219 / 1.385 / **1.445** / 1.511 / 1.692 | 1.326 / 1.390 / **1.444** / 1.510 / 1.591 | 3 |
| Midsize | Waterside economizer (water-cooled chiller) | 1.184 / 1.320 / **1.375** / 1.430 / 1.586 | 1.264 / 1.320 / **1.370** / 1.428 / 1.496 | 4 |
| Large-scale | Dry cooler with adiabatic assist (air-cooled chiller) | 1.058 / 1.164 / **1.199** / 1.239 / 1.345 | 1.123 / 1.162 / **1.197** / 1.235 / 1.324 | 18 |
| Large-scale | Airside economizer & adiabatic cooling (air-cooled chiller) | 1.018 / 1.133 / **1.169** / 1.209 / 1.330 | 1.092 / 1.128 / **1.165** / 1.206 / 1.297 | 0 |
| Large-scale | Airside economizer & adiabatic cooling (water-cooled chiller) | 1.013 / 1.108 / **1.143** / 1.174 / 1.274 | 1.071 / 1.106 / **1.140** / 1.174 / 1.228 | 1 |
| Large-scale | Waterside economizer (water-cooled chiller) | 1.033 / 1.093 / **1.118** / 1.143 / 1.224 | 1.065 / 1.092 / **1.120** / 1.145 / 1.176 | 2 |
| Large-scale | IT liquid cooling: waterside economizer (water-cooled chiller) | 1.018 / 1.098 / **1.133** / 1.164 / 1.254 | 1.065 / 1.102 / **1.133** / 1.163 / 1.223 | 15_1, 15_2, 15_3 |
| Large-scale | IT liquid cooling: dry cooler with adiabatic assist (air-cooled chiller) | 1.033 / 1.073 / **1.093** / 1.118 / 1.148 | 1.054 / 1.073 / **1.098** / 1.124 / 1.143 | 16_1, 16_2, 16_3 |
| Large-scale | IT liquid cooling: dry cooler (air-cooled chiller) | 1.023 / 1.073 / **1.093** / 1.118 / 1.164 | no equivalent case in the 2025 sample data | – |

**Site WUE (L per IT kWh, annual average)**

| size class (Fig. 4.4 legend) | system (Fig. 4.4 row label) | LBNL Fig 4.4, digitized (L per IT kWh): whisker-lo / Q1 / **median** / Q3 / whisker-hi | dc_locator-derived from 2025 sample data (15 US zones pooled): P5 / P25 / **P50** / P75 / P95 | source case_original |
|---|---|---|---|---|
| Small | Direct expansion | glyph unresolved; spans ≈0.01–0.10 (single mark) | 0.025 / 0.042 / **0.063** / 0.086 / 0.104 | 10 |
| Small | Air-cooled chiller | glyph unresolved; spans ≈0.01–0.10 (single mark) | 0.025 / 0.042 / **0.064** / 0.086 / 0.104 | 9 |
| Small | Water-cooled chiller | 2.34 / 2.99 / **3.21** / 3.45 / 4.12 | 2.728 / 3.000 / **3.215** / 3.451 / 3.823 | 8 |
| Midsize | Direct expansion | glyph unresolved; spans ≈0.01–0.10 (single mark) | 0.024 / 0.040 / **0.060** / 0.080 / 0.098 | 11 |
| Midsize | Air-cooled chiller | glyph unresolved; spans ≈0.01–0.10 (single mark) | 0.024 / 0.040 / **0.060** / 0.081 / 0.098 | 7 |
| Midsize | Dry cooler (air-cooled chiller) | glyph unresolved; spans ≈0.01–0.10 (single mark) | 0.024 / 0.039 / **0.059** / 0.080 / 0.098 | 17 |
| Midsize | Airside economizer (air-cooled chiller) | glyph unresolved; spans ≈0.00–0.06 (single mark) | 0.006 / 0.016 / **0.025** / 0.038 / 0.056 | 6 |
| Midsize | Water-cooled chiller | 2.15 / 2.70 / **2.89** / 3.09 / 3.68 | 2.469 / 2.689 / **2.904** / 3.108 / 3.401 | 5 |
| Midsize | Airside economizer (water-cooled chiller) | 0.29 / 1.06 / **1.32** / 1.58 / 2.34 | 0.589 / 1.071 / **1.342** / 1.611 / 2.069 | 3 |
| Midsize | Waterside economizer (water-cooled chiller) | 1.96 / 2.31 / **2.49** / 2.65 / 3.17 | 2.127 / 2.300 / **2.480** / 2.668 / 2.903 | 4 |
| Large-scale | Dry cooler with adiabatic assist (air-cooled chiller) | 0.00 / 0.16 / **0.23** / 0.32 / 0.57 | 0.103 / 0.188 / **0.283** / 0.431 / 0.728 | 18 |
| Large-scale | Airside economizer & adiabatic cooling (air-cooled chiller) | glyph unresolved; spans ≈0.00–0.03 (single mark) | 0.004 / 0.013 / **0.020** / 0.027 / 0.048 | 0 |
| Large-scale | Airside economizer & adiabatic cooling (water-cooled chiller) | 0.00 / 0.20 / **0.42** / 0.73 / 1.55 | 0.031 / 0.156 / **0.342** / 0.665 / 1.584 | 1 |
| Large-scale | Waterside economizer (water-cooled chiller) | 1.73 / 2.03 / **2.18** / 2.33 / 2.77 | 1.885 / 2.037 / **2.191** / 2.319 / 2.556 | 2 |
| Large-scale | IT liquid cooling: waterside economizer (water-cooled chiller) | 1.63 / 1.82 / **1.96** / 2.14 / 2.46 | 1.738 / 1.835 / **1.966** / 2.144 / 2.328 | 15_1, 15_2, 15_3 |
| Large-scale | IT liquid cooling: dry cooler with adiabatic assist (air-cooled chiller) | 0.00 / 0.09 / **0.13** / 0.17 / 0.31 | 0.001 / 0.100 / **0.155** / 0.223 / 0.311 | 16_1, 16_2, 16_3 |
| Large-scale | IT liquid cooling: dry cooler (air-cooled chiller) | glyph unresolved; spans ≈0.00–0.00 (single mark) | no equivalent case in the 2025 sample data | – |

Reading notes: for direct-expansion, air-cooled-chiller, dry-cooler-without-adiabatic and airside-economizer-with-air-cooled-chiller rows the WUE mark in Fig. 4.4 collapses to a single glyph at 0–0.1 L/kWh; the text attributes that water to occasional humidification (p.45).
The report itself flags that the large-scale "airside economizer & adiabatic cooling (air-cooled chiller)" WUE is probably too low (p.46–47): some hyperscale facilities report 0.1–0.3 L/kWh for similar systems, and a 0.2 L/kWh median for that system would raise the hyperscale aggregate median from 0.32 to 0.40.
The report also states the trade-off explicitly (p.45): water-cooled chillers and evaporative systems are generally more energy efficient than air-cooled chillers or waterless systems, so low site WUE is not automatically "good".

### 4.5 Figure 4.5 — aggregate PUE/WUE by space type for 2023 (cooling mix and facility locations folded in; **V** for medians, printed range for whiskers)

Medians are the red data labels printed in Fig. 4.5 (PDF p.47). The ranges are the 10th–90th percentile of the aggregate (p.46); the same ranges are printed numerically in Table 2 of Lei et al. 2025 (E&B 339:115734, PDF p.13), which agrees with a visual reading of the figure.

| space type | PUE median | PUE 10th–90th | WUE median (L/kWh_IT) | WUE 10th–90th |
|---|---|---|---|---|
| Small | 1.91 | 1.78–2.12 | 0.32 | 0.25–0.40 |
| Midsize and colo | 1.68 | 1.55–1.88 | 0.67 | 0.55–0.80 |
| Hyperscale | 1.22 | 1.16–1.28 | 0.32 | 0.20–0.46 |
| AI specialized | 1.14 | 1.09–1.19 | 0.61 | 0.52–0.73 |

National aggregates (**V**): annual-average PUE of all U.S. data centers falls from 1.6 (2014) to 1.4 (2023), and to 1.15–1.35 by 2028 (p.47, Fig. 4.6); average site WUE stays just above 0.36 L/kWh through 2023 and rises to 0.45–0.48 L/kWh by 2028 (p.48, Fig. 4.7); infrastructure energy is 40 % of total in 2014 and 30 % in 2023 (p.53).
Direct on-site water: 21.2 billion L in 2014 (64 % in internal data centers) and 66 billion L in 2023 (hyperscale + colocation 84 %, internal 12 %); hyperscale 2028: 60–124 billion L (pp.55–56).
Indirect (electricity-related) water: 4.52 L/kWh national average for U.S. data-center electricity in 2023 versus 4.35 L/kWh for U.S. electricity overall; GHG 0.34 vs 0.35 kg CO2e/kWh; about 800 billion L and 61 billion kg CO2e in total (p.57). Balancing-authority-level factors are in Siddik et al. 2024 (cited, not retrieved).

### 4.6 Caution: the national-average WUE appears to be normalised by total facility electricity (**C**, arithmetic from printed numbers)

| quantity | 2014 | 2023 | source |
|---|---|---|---|
| direct water | 21.2 billion L | 66 billion L | p.55 (V) |
| total data-center electricity | about 60 TWh (2014–2016) | 176 TWh | printed p.5 = PDF p.6 (V) |
| IT share of electricity (1 − infrastructure share) | 60 % | 70 % | p.53 (V) |
| water ÷ **total** electricity | 0.35 L/kWh (21.2/60) | **0.375 L/kWh** (66/176) | C |
| water ÷ **IT** electricity | 0.59 L/kWh | 0.54 L/kWh (66/123.2) | C |
| national average WUE plotted in Fig. 4.7 | ≈0.36 | ≈0.375 (text: just above 0.36 until 2023) | p.48 (V) |

The plotted national average matches water ÷ total facility electricity, not water ÷ IT electricity (the report's own definition, p.39). Either the national WUE is per total kWh, or the national water totals were computed with total instead of IT electricity.
**UNVERIFIED which; do not take 0.36 L/kWh as a per-IT-kWh WUE.** The space-type values of Fig. 4.5 (and the per-system values of Fig. 4.4) are the ones stated per IT kWh; ask the LBNL authors to confirm the national normalisation before any national-average WUE is used.

---

## 5. Lei & Masanet — the climate- and technology-specific PUE/WUE model and its results by climate zone

### 5.1 Documents, versions and accessibility

| document | what it is | access |
|---|---|---|
| Lei N., Masanet E. (2022), *Climate- and technology-specific PUE and WUE estimations for U.S. data centers using a hybrid statistical and thermodynamics-based approach*, Resour. Conserv. Recycl. 182:106323, doi:10.1016/j.resconrec.2022.106323 | peer-reviewed article; per the search-engine record of the abstract it covers 10 archetypes in 15 U.S. climate zones (UNVERIFIED: abstract not retrievable from a primary page) | **not retrievable** (paywall + bot challenge; not circumvented) |
| Lei N., Masanet E. (2021), preprint v1 "Climate- and Technology-Specific PUE and WUE Predictions for U.S. Data Centers using a Physics-Based Approach", Research Square rs-769999, posted 2021-08-03, CC BY 4.0 | earlier version; open full text (1,493,965 B, sha256 `e310a6f2…c8c`) | retrieved; **not** the peer-reviewed text — numbers may differ from the published tables |
| authors' repo `nuoaleon/Data-Center-Water-footprint` | code `simulation_funs_DC.py` (1,208 lines, 52 KB), demo notebook, `Simulation Results/UE.xlsx` (uploaded 2022-08-10, README cites the published DOI); no licence; COP regressors stored as `.pkl` (not downloaded) | retrieved read-only |
| Lei, Lu, Shehabi, Masanet (2025), *The water use of data center workloads: a review and assessment of key determinants*, RCR 219:108310 (accepted manuscript, CC BY 4.0, OSTI 2572888) + repo data `UEs_16cases.csv` | re-uses the model for 10 cooling technologies × 19 climate zones × 50 scenarios (SI S3, PDF pp.38–46) plus 3 IT-liquid scenarios (SI S6) | retrieved |
| Lei, Ganeshalingam, Masanet, Smith, Shehabi (2025), *Shedding light on U.S. small and midsize data centers*, Energy & Buildings 339:115734 (OSTI 3398559, CC BY 4.0) + repo data `UE_by_CZ_CS.csv`, `climate_zones.csv` | uses PUE/WUE values categorized by data center size, climate zone and cooling system type (§2.4, PDF p.6) | retrieved |

### 5.2 Model structure (preprint PDF pp.7–12; **V**) and the climate inputs it needs

* Hourly model, 8,760 h per case (Eq. 12–13 average the hourly values). Eq. 2–3: IT heat load and total DC power (IT + UPS loss + power-distribution loss + lighting + isothermal humidifier + pumps + fans + chiller). Eq. 4: heat to the cooling tower = DC heat + chiller sensible cooling ÷ (SHR × COP(load, outdoor temperature)); the amount of free cooling comes from the **enthalpy difference** of supply vs outside air (large-scale airside economizer + adiabatic, case 1), the **dry-bulb difference** (other airside-economizer cases) or return-facility-water temperature vs **outdoor wet-bulb** (waterside-economizer cases).
  Eq. 5–7: evaporation = Q_CT / H_vap; windage = φ_w Q_CT / (c_w ΔT_CT); draw-off = evaporation/(cycles of concentration − 1) − windage. Eq. 8: adiabatic water = dry-air mass flow × (humidity ratio of humidified air − outdoor humidity ratio). Eq. 9: humidification water from latent heat removed by the chiller.
* **Climate inputs:** hourly dry-bulb temperature, relative humidity and atmospheric pressure for a typical meteorological year (EnergyPlus weather files); wet-bulb is derived internally (code: `HAPropsSI('Twb', …)`, **C**). One representative city per climate zone (Fig. 2, **V**): 1A Miami FL, 2A Houston TX, 2B Phoenix AZ, 3A Atlanta GA, 3B Las Vegas NV, 3C San Francisco CA, 4A Baltimore MD, 4B Albuquerque NM, 4C Seattle WA, 5A Chicago IL, 5B Denver CO, 6A Minneapolis MN, 6B Helena MT, 7 Duluth MN, 8 Fairbanks AK
  (the text says "sixteen" zones but the legend shows 15; the 2022/2025 data files contain these 15; the 2025 sample file adds 5C and non-U.S. zones 0A, 0B, 1B).
  Within-zone climate variation is therefore **not** represented. The national LBNL study instead used 965 stations (§4).
* **Facility inputs** (Table 3, **V**; uniform ranges, 50 Latin-hypercube samples per case × zone, each a full 8,760-hour run; Sobol total-effect analysis shows climate and indoor setpoints dominate PUE variance, and cycles of concentration / windage dominate WUE variance of tower-based designs; preprint §3.4, §4.4):

| parameter (unit) | large-scale cases 1–2 | mid-size cases 3–7 | small cases 8–10 |
|---|---|---|---|
| UPS efficiency (%) | 90–99 | 80–94 | 77–85 |
| power loss in transformation/distribution (%) | 0–2 | 2–5 | 2–4 |
| lighting power ÷ IT power (%) | 0–0.2 | 2–5 | 2–4 |
| supply-air dry-bulb set point, lower / upper bound (°C) | 10–18 / 27–35 | 15–18 / 27–32 | 18–22.5 / 22.5–27 |
| supply-air dew point, lower / upper bound (°C) | −12 to −9 / 15–27 | −12 to −9 / 15–27 | −9.9 to −8.1 / 13.5–16.5 |
| sensible heat ratio (%) | 95–99 | 95–99 | 95–99 |
| cooling-tower approach (°C) | 2.8–6.7 | 2.8–6.7 (towered cases) | 2.8–6.7 (case 8) |
| economizer heat-exchanger approach (°C) | 1.7–2.8 (case 2) | 1.7–2.8 (case 4) | — |
| chiller partial-load factor (–) | 0.2–0.8 | 0.1–0.5 | 0.1–0.5 |
| cycles of concentration (–) | 3–15 | 3–12 | 3–12 (case 8) |
| tower windage loss (% of circulating water) | 0.005–0.5 | 0.005–0.5 | 0.05–0.5 (case 8) |
| COP deviation from regressed value (%) | −11 to 11 | −40 to 0 (towered) / −40 to 25 (air-cooled) | −60 to 20 / −45 to 30 / −45 to 20 |

  These are the source's **assumed ranges** (literature + engineering estimates), not measurements. IT utilization is not a listed parameter (UNVERIFIED how load enters beyond the chiller partial-load factor); the authors' code sets IT power to 1 in every hour (**C**).
  The chiller COP is a Gaussian-process regression on data from Gullo 2017, Squillo 2018 and Yu & Chan 2007 (pickles in the repo, regression not tabulated in the paper), so the model **cannot be re-implemented from the paper alone** and the repo has no licence.

### 5.3 Authors' qualitative statements about climate dependence (preprint §4.2–4.3, PDF pp.19–21; paraphrased)

PUE is lowest in the coldest zones and highest in 1A for almost all cases (exceptions: case 10 highest in 2B; cases 3 and 6 lowest in 4C; cases 2 and 4 lowest in 3C). WUE is much less zone-sensitive than PUE except for the airside-economizer cases 1 and 3 (free-cooling hours differ strongly by zone) and, to a lesser extent, the water-cooled-chiller cases 5 and 8; in towered designs most water is driven by internal heat (climate-independent) rather than compressor heat.
Direct-expansion and air-cooled-chiller WUE (cases 6, 7, 9, 10) is tiny and its climate dependence negligible. Hot-humid zones are bad even for evaporative-free-cooling designs because dehumidification needs chiller work; dry zones allow direct/indirect evaporative free cooling.
Medians by size class stated in the text (V): large-scale (cases 1–2) PUE 1.12–1.25, mid-size (cases 3–7) 1.39–1.98, small (cases 8–10) 1.71–2.22. The authors note extreme hot hours would raise capital cost for supplementary cooling but treat that as out of scope (p.21) — i.e. **no peak/design-day result**.
Validation (p.17–18, Fig. 3): reported annual PUE/WUE of Facebook data centers and of the MGHPCC facility fall inside the model's prediction intervals (Fig. 3 plots minimum, 5th, 25th, 50th, 75th, 95th percentile and maximum), mostly in the lower-to-middle part (the authors suspect efficient operators report more often).

### 5.4 Where the per-zone numbers exist, and the derived table I built

| form | content | rows | note |
|---|---|---|---|
| preprint Fig. 4 (PUE) and Fig. 5 (WUE), PDF pp.18–19 | per case × zone: min, 5th, 50th, 95th, max of annual-average PUE/WUE | 10 cases × 15–16 zones | **figures only, no numbers**; not digitized |
| `Simulation Results/UE.xlsx` (authors' repo, uploaded 2022-08-10; sha256 `adc2a6ca…0e96`) | PUE, WUE, Climate Zone, Case, Quantile ∈ {5th, 95th} | 300 (10 cases × 15 zones × 2) | **V**; case numbering = preprint Table 2 (checked: all five zone exceptions named in the preprint text — case 10 highest PUE in 2B, cases 3 and 6 lowest in 4C, cases 2 and 4 lowest in 3C — reproduce from the 5th-percentile columns of this file) |
| `Datasets/UE_by_CZ_CS.csv` (E&B 2025 repo; sha256 `b4764be3…bb7d`) | PUE_quantiles and WUE_quantiles, 5 values each; order [5th, 25th, 50th, 75th, 95th] (the repo notebook labels them so, cell 64) | 210 (14 cases × 15 zones); case ids 0,1,3–13,17 | **V**; **no large-scale WSE case (2), no IT-liquid cases** |
| `data/UEs_16cases.csv` (RCR 2025 review repo; sha256 `4924fdb4…c031`) | sample level: PUE, WUE, Case, Climate Zone, cooling system, size, cluster, Case (Original) | 19,000 (20 case variants × 19 zones × 50) | **V**; includes IT liquid cases 15_x/16_x and dry-cooler cases 17/18; no data dictionary |
| published RCR 182:106323 article: tables, appendices, supplementary data | the authors' demo notebook points to "Table B.1 in our RCR paper" for the model-input vector, so the article has an Appendix B input table; whether it also tabulates per-zone PUE/WUE is unknown | — | **NOT retrieved; UNVERIFIED** (existence and format of published per-zone tables unknown; Elsevier supplementary files not reachable without a bot-wall) |

**Derived table (C):** `docs/research/phase3/cooling_designs_zone_quantiles_derived.csv` = for each `case_original` × zone (16 zones: 15 CONUS + 5C) the 5th/25th/50th/75th/95th percentiles of the 50 samples (`numpy.percentile`, linear interpolation) for PUE and WUE, plus a pooled-15-CONUS-zone row (750 samples, equal zone weights). PUE and WUE of one design/zone come from the **same** 50 simulated facilities, so they are physically compatible only sample by sample (the quantiles of the two metrics are not joint quantiles; use the sample file for joint draws).

### 5.5 Pooled design matrix — annual PUE and site WUE by design (15 CONUS zones pooled; **C**)

P5 = efficient operating practice in the best zones, P50 = typical, P95 = inefficient operating practice in the worst zones (the spread mixes practice and climate; use the per-zone tables to isolate climate).

| case_original | design (size class; as labelled in source) | PUE P5 / **P50** / P95 | WUE P5 / **P50** / P95 (L per IT kWh) |
|---|---|---|---|
| 6 | Mid: AE (air-cooled chiller suppl.) | 1.387 / **1.581** / 1.901 | 0.006 / **0.025** / 0.056 |
| 7 | Mid: air-cooled chiller | 1.604 / **1.840** / 2.268 | 0.024 / **0.060** / 0.099 |
| 17 | Mid: dry cooler (air-cooled chiller) | 1.395 / **1.587** / 2.008 | 0.024 / **0.059** / 0.098 |
| 0 | Large: AE + adiabatic (air-cooled chiller suppl.) | 1.092 / **1.165** / 1.297 | 0.004 / **0.020** / 0.048 |
| 9 | Small: air-cooled chiller | 1.778 / **2.004** / 2.520 | 0.025 / **0.064** / 0.104 |
| 10 | Small: direct expansion | 1.841 / **2.053** / 2.386 | 0.025 / **0.063** / 0.104 |
| 11 | Mid: direct expansion | 1.629 / **1.861** / 2.191 | 0.024 / **0.060** / 0.098 |
| 5 | Mid: water-cooled chiller + tower | 1.395 / **1.529** / 1.678 | 2.469 / **2.904** / 3.401 |
| 4 | Mid: waterside econ (WCC + tower) | 1.264 / **1.370** / 1.496 | 2.127 / **2.480** / 2.902 |
| 2 | Large: waterside econ (WCC + tower) | 1.065 / **1.120** / 1.175 | 1.885 / **2.191** / 2.556 |
| 8 | Small: water-cooled chiller + tower | 1.567 / **1.704** / 1.891 | 2.728 / **3.215** / 3.823 |
| 3 | Mid: AE (water-cooled chiller suppl.) | 1.326 / **1.444** / 1.591 | 0.589 / **1.342** / 2.069 |
| 1 | Large: AE + adiabatic (water-cooled chiller suppl.) | 1.071 / **1.140** / 1.228 | 0.031 / **0.342** / 1.584 |
| 18 | Large: dry cooler + adiabatic assist (air-cooled chiller) | 1.123 / **1.197** / 1.324 | 0.103 / **0.283** / 0.729 |
| 16_2 | Large: IT liquid, dry cooler+adiabatic assist (ACC), cold plate (D2C) | 1.053 / **1.098** / 1.143 | 0.002 / **0.155** / 0.315 |
| 16_1 | Large: IT liquid, dry cooler+adiabatic assist (ACC), RDHx | 1.052 / **1.098** / 1.143 | 0.001 / **0.155** / 0.304 |
| 16_3 | Large: IT liquid, dry cooler+adiabatic assist (ACC), immersion | 1.056 / **1.098** / 1.144 | 0.001 / **0.156** / 0.309 |
| 15_2 | Large: IT liquid, WSE+WCC, cold plate (D2C) | 1.066 / **1.130** / 1.222 | 1.738 / **1.960** / 2.321 |
| 15_1 | Large: IT liquid, WSE+WCC, RDHx | 1.072 / **1.141** / 1.225 | 1.736 / **1.960** / 2.331 |
| 15_3 | Large: IT liquid, WSE+WCC, immersion | 1.060 / **1.129** / 1.218 | 1.738 / **1.976** / 2.329 |

Cross-check against LBNL 2024 (Fig. 4.4 digitized, §4.4): medians agree within about ±0.01 PUE (rows 6, 7, 17, 0, 1, 2, 3, 4, 5, 8, 9, 10, 11, 18, 15_x) and ±0.05 L/kWh for most water-using rows; largest WUE gaps are the adiabatic rows (case 1: 0.34 vs 0.42; case 18: 0.28 vs 0.23; case 16_x: 0.155 vs 0.13). Whiskers differ by construction. The agreement is expected rather than independent (LBNL 2024 states it used the same simulation framework); it indicates that the 2025 sample file and the LBNL figure share the same framework and parameter ranges, up to the zone-vs-station difference and the expert adjustment (that they are the same runs is UNVERIFIED).

### 5.6 What "design" does and does not explain — size/practice confounding

* Mid-size air-cooled designs (cases 6, 7, 17: PUE 1.58–1.84) and large-scale designs with the same kind of backup (case 0: 1.17; case 18: 1.20) differ by 0.4 PUE mostly because of the **assumed operating practice** (Table 3: UPS 80–94 % vs 90–99 %, narrower vs wider thermal envelope, higher fan/pump losses), not because of the heat-rejection equipment.
  For a 100 MW hyperscale-type project only the large-scale rows (0, 1, 2, 18, 15_x, 16_x) are meaningful; large-scale versions of "airside economizer + air-cooled chiller without adiabatic" and "water-cooled chiller without economizer" **do not exist** in the data.
* Every simulated design carries a supplementary chiller. A chiller-less liquid design (NREL ESIF, §6) is outside the model envelope: measured PUE 1.034 and WUE 0.70 (hybrid dry/wet) to 1.27–1.42 (towers only) lie below the model's P5 for the closest design (15_2 in zone 5B: PUE P5 1.057, WUE P5 1.74).

### 5.7 Climate sensitivity of the median (P50 across the 15 CONUS zones; **C**)

| case_original | design | PUE P50: min (zone) – max (zone) | WUE P50: min (zone) – max (zone) |
|---|---|---|---|
| 6 | Mid: AE (air-cooled chiller suppl.) | 1.444 (4C) – 1.765 (1A) | 0.009 (4C) – 0.042 (1A) |
| 7 | Mid: air-cooled chiller | 1.685 (8) – 2.001 (1A) | 0.057 (6B) – 0.062 (6A) |
| 17 | Mid: dry cooler (air-cooled chiller) | 1.454 (8) – 1.955 (1A) | 0.058 (3A) – 0.062 (4C) |
| 0 | Large: AE + adiabatic (air-cooled chiller suppl.) | 1.120 (6B) – 1.284 (2A) | 0.005 (4C) – 0.051 (2B) |
| 9 | Small: air-cooled chiller | 1.803 (8) – 2.145 (1A) | 0.063 (5A) – 0.066 (7) |
| 10 | Small: direct expansion | 1.887 (8) – 2.174 (2B) | 0.062 (3B) – 0.065 (7) |
| 11 | Mid: direct expansion | 1.696 (8) – 1.948 (1A) | 0.058 (5B) – 0.062 (6B) |
| 5 | Mid: water-cooled chiller + tower | 1.452 (8) – 1.624 (1A) | 2.733 (8) – 3.123 (2A) |
| 4 | Mid: waterside econ (WCC + tower) | 1.356 (5B) – 1.417 (2A) | 2.421 (5A) – 2.553 (1A) |
| 2 | Large: waterside econ (WCC + tower) | 1.110 (4C) – 1.145 (2A) | 2.163 (4C) – 2.216 (1A) |
| 8 | Small: water-cooled chiller + tower | 1.616 (8) – 1.850 (1A) | 2.975 (8) – 3.562 (2A) |
| 3 | Mid: AE (water-cooled chiller suppl.) | 1.403 (6B) – 1.555 (2A) | 0.480 (4C) – 2.016 (2A) |
| 1 | Large: AE + adiabatic (water-cooled chiller suppl.) | 1.112 (6B) – 1.218 (2A) | 0.057 (8) – 1.460 (2A) |
| 18 | Large: dry cooler + adiabatic assist (air-cooled chiller) | 1.161 (8) – 1.323 (1A) | 0.171 (8) – 0.759 (2B) |
| 16_2 | Large: IT liquid, dry cooler+adiabatic assist (ACC), cold plate (D2C) | 1.094 (6B) – 1.102 (5B) | 0.000 (1A) – 0.295 (4B) |
| 16_1 | Large: IT liquid, dry cooler+adiabatic assist (ACC), RDHx | 1.095 (5B) – 1.102 (2A) | 0.000 (1A) – 0.285 (4B) |
| 16_3 | Large: IT liquid, dry cooler+adiabatic assist (ACC), immersion | 1.094 (5B) – 1.102 (4C) | 0.000 (1A) – 0.298 (4B) |
| 15_2 | Large: IT liquid, WSE+WCC, cold plate (D2C) | 1.114 (8) – 1.210 (1A) | 1.934 (6B) – 2.004 (6A) |
| 15_1 | Large: IT liquid, WSE+WCC, RDHx | 1.112 (8) – 1.217 (1A) | 1.928 (8) – 1.998 (4A) |
| 15_3 | Large: IT liquid, WSE+WCC, immersion | 1.102 (8) – 1.174 (1A) | 1.944 (5A) – 2.060 (3B) |

Reading: the zone-to-zone spread of the median PUE of large-scale designs is only 0.01–0.17 (case 2: 0.035; case 1: 0.11; cases 0 and 18: 0.16; IT-liquid dry cooler: 0.01); WUE is strongly zone-dependent only for the airside-economizer/adiabatic designs (case 1: 0.057 L/kWh in zone 8 to 1.46 in 2A; case 3: 0.48 to 2.02; case 18: 0.17 to 0.76) and almost zone-independent for towered designs (cases 2, 4, 5, 8: within about ±10 %) and for dry-cooler/air-cooled designs (≈0.06 or ≈0).
For IT liquid cooling with dry cooler + adiabatic assist the median WUE is ≈0 in the hot-humid zone 1A and highest (≈0.3 L/kWh) in the mixed-dry zone 4B — non-monotonic in temperature (interpretation, not stated by the authors: adiabatic assist only helps where the wet-bulb depression is large; in humid zones the air-cooled chiller carries the residual load instead).

Representative zones (cities in §5.2; median [P5–P95]; **C**):

| case_original | design | 2A PUE P50 [P5–P95] | 2B PUE P50 [P5–P95] | 4C PUE P50 [P5–P95] | 5A PUE P50 [P5–P95] | 7 PUE P50 [P5–P95] | 2A WUE P50 [P5–P95] | 2B WUE P50 [P5–P95] | 4C WUE P50 [P5–P95] | 5A WUE P50 [P5–P95] | 7 WUE P50 [P5–P95] |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 6 | Mid: AE (air-cooled chiller suppl.) | 1.76 [1.61–2.03] | 1.76 [1.59–2.15] | 1.44 [1.32–1.60] | 1.49 [1.35–1.70] | 1.51 [1.39–1.66] | 0.04 [0.01–0.06] | 0.03 [0.01–0.06] | 0.01 [0.00–0.03] | 0.02 [0.01–0.04] | 0.03 [0.01–0.05] |
| 7 | Mid: air-cooled chiller | 1.93 [1.77–2.46] | 1.99 [1.73–2.54] | 1.84 [1.64–2.15] | 1.81 [1.57–2.03] | 1.74 [1.57–1.94] | 0.06 [0.02–0.10] | 0.06 [0.02–0.10] | 0.06 [0.02–0.10] | 0.06 [0.03–0.10] | 0.06 [0.03–0.10] |
| 17 | Mid: dry cooler (air-cooled chiller) | 1.84 [1.66–2.14] | 1.79 [1.64–2.27] | 1.49 [1.35–1.59] | 1.52 [1.41–1.66] | 1.51 [1.39–1.61] | 0.06 [0.02–0.10] | 0.06 [0.02–0.10] | 0.06 [0.02–0.10] | 0.06 [0.02–0.10] | 0.06 [0.02–0.10] |
| 0 | Large: AE + adiabatic (air-cooled chiller suppl.) | 1.28 [1.20–1.35] | 1.20 [1.15–1.27] | 1.13 [1.08–1.20] | 1.15 [1.08–1.21] | 1.15 [1.08–1.20] | 0.03 [0.01–0.04] | 0.05 [0.04–0.09] | 0.00 [0.00–0.01] | 0.01 [0.00–0.02] | 0.02 [0.01–0.04] |
| 9 | Small: air-cooled chiller | 2.10 [1.93–2.65] | 2.13 [1.96–2.77] | 1.97 [1.82–2.37] | 1.90 [1.79–2.28] | 1.87 [1.73–2.17] | 0.07 [0.03–0.10] | 0.06 [0.03–0.10] | 0.06 [0.03–0.10] | 0.06 [0.03–0.10] | 0.07 [0.03–0.10] |
| 10 | Small: direct expansion | 2.12 [1.96–2.46] | 2.17 [2.01–2.51] | 2.03 [1.85–2.29] | 2.00 [1.89–2.29] | 1.94 [1.82–2.17] | 0.06 [0.03–0.10] | 0.06 [0.03–0.10] | 0.06 [0.03–0.10] | 0.06 [0.02–0.10] | 0.07 [0.02–0.10] |
| 11 | Mid: direct expansion | 1.91 [1.70–2.28] | 1.94 [1.78–2.32] | 1.82 [1.65–2.12] | 1.82 [1.62–2.08] | 1.78 [1.57–2.04] | 0.06 [0.02–0.10] | 0.06 [0.02–0.10] | 0.06 [0.02–0.10] | 0.06 [0.03–0.10] | 0.06 [0.02–0.10] |
| 5 | Mid: water-cooled chiller + tower | 1.61 [1.49–1.74] | 1.56 [1.43–1.69] | 1.51 [1.40–1.63] | 1.50 [1.40–1.64] | 1.48 [1.40–1.60] | 3.12 [2.73–3.57] | 2.96 [2.58–3.42] | 2.84 [2.47–3.39] | 2.84 [2.46–3.42] | 2.78 [2.44–3.26] |
| 4 | Mid: waterside econ (WCC + tower) | 1.42 [1.31–1.52] | 1.37 [1.28–1.49] | 1.38 [1.25–1.45] | 1.36 [1.26–1.48] | 1.37 [1.25–1.48] | 2.45 [2.20–3.00] | 2.53 [2.20–2.89] | 2.46 [2.18–2.94] | 2.42 [2.11–2.90] | 2.49 [2.12–2.89] |
| 2 | Large: waterside econ (WCC + tower) | 1.15 [1.10–1.20] | 1.12 [1.08–1.17] | 1.11 [1.06–1.16] | 1.12 [1.06–1.16] | 1.11 [1.06–1.17] | 2.21 [1.92–2.61] | 2.19 [1.86–2.52] | 2.16 [1.91–2.60] | 2.20 [1.91–2.51] | 2.20 [1.88–2.49] |
| 8 | Small: water-cooled chiller + tower | 1.81 [1.68–2.02] | 1.74 [1.62–1.86] | 1.68 [1.60–1.81] | 1.67 [1.57–1.81] | 1.64 [1.56–1.76] | 3.56 [3.04–4.04] | 3.28 [2.81–3.83] | 3.19 [2.78–3.59] | 3.19 [2.76–3.76] | 3.12 [2.60–3.62] |
| 3 | Mid: AE (water-cooled chiller suppl.) | 1.55 [1.42–1.67] | 1.47 [1.40–1.59] | 1.41 [1.31–1.51] | 1.41 [1.33–1.56] | 1.43 [1.31–1.52] | 2.02 [1.51–2.53] | 1.55 [1.23–2.05] | 0.48 [0.22–0.93] | 1.14 [0.79–1.58] | 1.52 [1.17–1.73] |
| 1 | Large: AE + adiabatic (water-cooled chiller suppl.) | 1.22 [1.13–1.28] | 1.16 [1.10–1.21] | 1.13 [1.06–1.17] | 1.13 [1.06–1.18] | 1.13 [1.07–1.19] | 1.46 [0.63–1.99] | 0.64 [0.41–0.93] | 0.10 [0.02–0.60] | 0.32 [0.11–0.69] | 0.24 [0.11–0.59] |
| 18 | Large: dry cooler + adiabatic assist (air-cooled chiller) | 1.30 [1.23–1.37] | 1.22 [1.16–1.28] | 1.17 [1.12–1.23] | 1.18 [1.13–1.24] | 1.18 [1.12–1.24] | 0.21 [0.07–0.41] | 0.76 [0.62–0.97] | 0.20 [0.10–0.37] | 0.21 [0.10–0.38] | 0.18 [0.08–0.30] |
| 16_2 | Large: IT liquid, dry cooler+adiabatic assist (ACC), cold plate (D2C) | 1.10 [1.05–1.14] | 1.10 [1.05–1.14] | 1.10 [1.05–1.14] | 1.10 [1.05–1.14] | 1.10 [1.06–1.14] | 0.07 [0.04–0.11] | 0.20 [0.11–0.25] | 0.22 [0.08–0.37] | 0.14 [0.07–0.20] | 0.11 [0.06–0.16] |
| 16_1 | Large: IT liquid, dry cooler+adiabatic assist (ACC), RDHx | 1.10 [1.05–1.14] | 1.10 [1.05–1.14] | 1.10 [1.06–1.14] | 1.10 [1.05–1.14] | 1.10 [1.05–1.14] | 0.07 [0.04–0.11] | 0.20 [0.11–0.25] | 0.22 [0.09–0.34] | 0.14 [0.08–0.20] | 0.11 [0.07–0.15] |
| 16_3 | Large: IT liquid, dry cooler+adiabatic assist (ACC), immersion | 1.10 [1.05–1.14] | 1.10 [1.06–1.15] | 1.10 [1.06–1.14] | 1.10 [1.05–1.14] | 1.10 [1.06–1.15] | 0.07 [0.04–0.11] | 0.20 [0.12–0.25] | 0.23 [0.11–0.35] | 0.15 [0.06–0.20] | 0.11 [0.05–0.17] |
| 15_2 | Large: IT liquid, WSE+WCC, cold plate (D2C) | 1.17 [1.08–1.25] | 1.14 [1.07–1.20] | 1.13 [1.08–1.19] | 1.12 [1.06–1.19] | 1.12 [1.06–1.16] | 1.97 [1.79–2.29] | 1.97 [1.76–2.30] | 1.97 [1.72–2.32] | 1.94 [1.75–2.28] | 1.94 [1.74–2.26] |
| 15_1 | Large: IT liquid, WSE+WCC, RDHx | 1.20 [1.10–1.25] | 1.15 [1.09–1.21] | 1.13 [1.08–1.18] | 1.13 [1.07–1.19] | 1.13 [1.07–1.18] | 1.96 [1.73–2.27] | 1.95 [1.76–2.36] | 1.96 [1.72–2.32] | 1.95 [1.74–2.31] | 1.99 [1.73–2.35] |
| 15_3 | Large: IT liquid, WSE+WCC, immersion | 1.16 [1.06–1.26] | 1.13 [1.08–1.20] | 1.13 [1.06–1.16] | 1.13 [1.06–1.18] | 1.11 [1.07–1.17] | 1.99 [1.74–2.33] | 1.99 [1.70–2.32] | 1.94 [1.77–2.27] | 1.94 [1.75–2.31] | 1.97 [1.73–2.34] |

### 5.8 IT liquid cooling scenarios (review SI S6; **V** text, **C** mapping check)

* Three IT-liquid scenarios are simulated for each of the two liquid designs: rear-door heat exchanger, cold plate (direct to chip) and immersion (SI p.50–53/54). The repo labels them only as suffixes `_1/_2/_3` of cases 15 and 16.
  The mapping `_1 = RDHx, _2 = cold plate, _3 = immersion` is **inferred** from (i) the order printed in SI Fig. S6.3(a) and in the SI text and (ii) a check against the figure: pooled over all 19 zones the medians of PUE for 15_1/15_2/15_3 are 1.148/1.136/1.131 and for 16_x ≈1.098, matching the box medians read by eye from Fig. S6.3(a) (≈1.145/1.135/1.13 and ≈1.098) and the SI statement that PUE/WUE are highest for RDHx and lowest for immersion with cold plate in between. Confidence: medium; not confirmed by the authors.
* The SI states the scenario differences are small because the allowable facility-water supply range (2–32 / 2–40 / 2–45 °C) lets free and adiabatic cooling cover most hours even in warm zones (SI PDF p.53). In the pooled CONUS medians the RDHx vs cold-plate vs immersion differences are ≤0.012 PUE and ≤0.016 L/kWh, so **choosing the cold-plate case for "direct-to-chip" is not a material source of error**; the heat-rejection choice (towers vs dry cooler) is (WUE 1.96 vs 0.16 L/kWh).

### 5.9 Per-zone tables for the key designs (15 CONUS zones + 5C; n = 50 per row; **C** from the 2025 sample file)

**case_original 6: Mid: AE (air-cooled chiller suppl.)** (source label: Airside economizer (air-cooled chiller); n=50 per zone)

| zone | PUE P5 | PUE P50 | PUE P95 | WUE P5 | WUE P50 | WUE P95 |
|---|---|---|---|---|---|---|
| 1A | 1.631 | 1.765 | 2.105 | 0.013 | 0.042 | 0.062 |
| 2A | 1.613 | 1.761 | 2.034 | 0.013 | 0.038 | 0.064 |
| 2B | 1.595 | 1.762 | 2.150 | 0.013 | 0.033 | 0.063 |
| 3A | 1.490 | 1.635 | 1.894 | 0.010 | 0.026 | 0.053 |
| 3B | 1.497 | 1.662 | 1.891 | 0.008 | 0.027 | 0.056 |
| 3C | 1.422 | 1.548 | 1.825 | 0.009 | 0.019 | 0.050 |
| 4A | 1.436 | 1.572 | 1.742 | 0.007 | 0.025 | 0.056 |
| 4B | 1.458 | 1.586 | 1.782 | 0.004 | 0.024 | 0.047 |
| 4C | 1.321 | 1.444 | 1.602 | 0.002 | 0.009 | 0.026 |
| 5A | 1.346 | 1.492 | 1.696 | 0.005 | 0.021 | 0.043 |
| 5B | 1.347 | 1.575 | 1.797 | 0.006 | 0.019 | 0.044 |
| 5C | 1.317 | 1.459 | 1.656 | 0.001 | 0.009 | 0.028 |
| 6A | 1.393 | 1.535 | 1.703 | 0.011 | 0.026 | 0.058 |
| 6B | 1.381 | 1.501 | 1.668 | 0.004 | 0.020 | 0.049 |
| 7 | 1.390 | 1.513 | 1.664 | 0.011 | 0.030 | 0.053 |
| 8 | 1.356 | 1.484 | 1.687 | 0.013 | 0.033 | 0.054 |
| pooled US15 | 1.387 | 1.581 | 1.901 | 0.006 | 0.025 | 0.056 |

**case_original 7: Mid: air-cooled chiller** (source label: Air-cooled chiller; n=50 per zone)

| zone | PUE P5 | PUE P50 | PUE P95 | WUE P5 | WUE P50 | WUE P95 |
|---|---|---|---|---|---|---|
| 1A | 1.751 | 2.001 | 2.405 | 0.024 | 0.062 | 0.099 |
| 2A | 1.765 | 1.932 | 2.462 | 0.025 | 0.061 | 0.096 |
| 2B | 1.734 | 1.988 | 2.538 | 0.024 | 0.059 | 0.095 |
| 3A | 1.675 | 1.885 | 2.239 | 0.024 | 0.060 | 0.100 |
| 3B | 1.682 | 1.926 | 2.249 | 0.024 | 0.061 | 0.097 |
| 3C | 1.632 | 1.827 | 2.266 | 0.025 | 0.059 | 0.094 |
| 4A | 1.661 | 1.840 | 2.165 | 0.023 | 0.060 | 0.099 |
| 4B | 1.699 | 1.812 | 2.227 | 0.025 | 0.060 | 0.101 |
| 4C | 1.644 | 1.836 | 2.152 | 0.024 | 0.059 | 0.099 |
| 5A | 1.566 | 1.812 | 2.026 | 0.025 | 0.058 | 0.099 |
| 5B | 1.625 | 1.816 | 2.090 | 0.024 | 0.060 | 0.099 |
| 5C | 1.611 | 1.806 | 2.083 | 0.024 | 0.060 | 0.098 |
| 6A | 1.605 | 1.768 | 2.030 | 0.024 | 0.062 | 0.101 |
| 6B | 1.586 | 1.780 | 2.079 | 0.025 | 0.057 | 0.098 |
| 7 | 1.568 | 1.744 | 1.944 | 0.025 | 0.061 | 0.098 |
| 8 | 1.538 | 1.685 | 1.895 | 0.025 | 0.058 | 0.097 |
| pooled US15 | 1.604 | 1.840 | 2.268 | 0.024 | 0.060 | 0.099 |

**case_original 17: Mid: dry cooler (air-cooled chiller)** (source label: Dry cooler (air-cooled chiller); n=50 per zone)

| zone | PUE P5 | PUE P50 | PUE P95 | WUE P5 | WUE P50 | WUE P95 |
|---|---|---|---|---|---|---|
| 1A | 1.738 | 1.955 | 2.367 | 0.025 | 0.059 | 0.097 |
| 2A | 1.665 | 1.844 | 2.138 | 0.025 | 0.058 | 0.096 |
| 2B | 1.638 | 1.794 | 2.269 | 0.025 | 0.060 | 0.100 |
| 3A | 1.557 | 1.671 | 1.920 | 0.024 | 0.058 | 0.100 |
| 3B | 1.542 | 1.705 | 1.989 | 0.024 | 0.059 | 0.097 |
| 3C | 1.440 | 1.561 | 1.672 | 0.025 | 0.059 | 0.099 |
| 4A | 1.483 | 1.597 | 1.789 | 0.024 | 0.059 | 0.100 |
| 4B | 1.473 | 1.611 | 1.827 | 0.025 | 0.061 | 0.098 |
| 4C | 1.355 | 1.486 | 1.591 | 0.024 | 0.062 | 0.095 |
| 5A | 1.412 | 1.516 | 1.663 | 0.024 | 0.059 | 0.100 |
| 5B | 1.450 | 1.556 | 1.724 | 0.025 | 0.059 | 0.096 |
| 5C | 1.324 | 1.427 | 1.578 | 0.025 | 0.059 | 0.098 |
| 6A | 1.417 | 1.519 | 1.698 | 0.024 | 0.059 | 0.094 |
| 6B | 1.384 | 1.521 | 1.652 | 0.024 | 0.060 | 0.100 |
| 7 | 1.392 | 1.514 | 1.609 | 0.024 | 0.060 | 0.096 |
| 8 | 1.339 | 1.454 | 1.610 | 0.025 | 0.059 | 0.099 |
| pooled US15 | 1.395 | 1.587 | 2.008 | 0.024 | 0.059 | 0.098 |

**case_original 0: Large: AE + adiabatic (air-cooled chiller suppl.)** (source label: Airside economizer& adiabatic cooling (air-cooled chiller); n=50 per zone)

| zone | PUE P5 | PUE P50 | PUE P95 | WUE P5 | WUE P50 | WUE P95 |
|---|---|---|---|---|---|---|
| 1A | 1.198 | 1.267 | 1.351 | 0.013 | 0.025 | 0.050 |
| 2A | 1.204 | 1.284 | 1.350 | 0.014 | 0.026 | 0.041 |
| 2B | 1.151 | 1.204 | 1.275 | 0.035 | 0.051 | 0.089 |
| 3A | 1.123 | 1.200 | 1.293 | 0.008 | 0.018 | 0.029 |
| 3B | 1.111 | 1.169 | 1.254 | 0.018 | 0.029 | 0.046 |
| 3C | 1.097 | 1.181 | 1.258 | 0.006 | 0.013 | 0.028 |
| 4A | 1.114 | 1.176 | 1.236 | 0.004 | 0.016 | 0.028 |
| 4B | 1.106 | 1.152 | 1.198 | 0.014 | 0.024 | 0.035 |
| 4C | 1.075 | 1.130 | 1.200 | 0.000 | 0.005 | 0.014 |
| 5A | 1.084 | 1.146 | 1.205 | 0.000 | 0.012 | 0.019 |
| 5B | 1.098 | 1.151 | 1.209 | 0.009 | 0.024 | 0.038 |
| 5C | 1.084 | 1.132 | 1.180 | 0.000 | 0.007 | 0.024 |
| 6A | 1.089 | 1.154 | 1.207 | 0.008 | 0.017 | 0.027 |
| 6B | 1.080 | 1.120 | 1.192 | 0.007 | 0.015 | 0.027 |
| 7 | 1.084 | 1.149 | 1.195 | 0.012 | 0.021 | 0.038 |
| 8 | 1.069 | 1.120 | 1.179 | 0.016 | 0.024 | 0.035 |
| pooled US15 | 1.092 | 1.165 | 1.297 | 0.004 | 0.020 | 0.048 |

**case_original 5: Mid: water-cooled chiller + tower** (source label: Water-cooled chiller; n=50 per zone)

| zone | PUE P5 | PUE P50 | PUE P95 | WUE P5 | WUE P50 | WUE P95 |
|---|---|---|---|---|---|---|
| 1A | 1.513 | 1.624 | 1.735 | 2.832 | 3.115 | 3.579 |
| 2A | 1.492 | 1.612 | 1.740 | 2.728 | 3.123 | 3.569 |
| 2B | 1.426 | 1.558 | 1.691 | 2.576 | 2.955 | 3.417 |
| 3A | 1.441 | 1.561 | 1.691 | 2.578 | 2.984 | 3.360 |
| 3B | 1.431 | 1.553 | 1.659 | 2.520 | 2.921 | 3.386 |
| 3C | 1.441 | 1.540 | 1.666 | 2.467 | 2.920 | 3.448 |
| 4A | 1.425 | 1.515 | 1.631 | 2.563 | 2.859 | 3.395 |
| 4B | 1.395 | 1.507 | 1.627 | 2.502 | 2.916 | 3.316 |
| 4C | 1.397 | 1.510 | 1.634 | 2.469 | 2.837 | 3.390 |
| 5A | 1.395 | 1.496 | 1.635 | 2.462 | 2.839 | 3.422 |
| 5B | 1.389 | 1.498 | 1.611 | 2.507 | 2.837 | 3.255 |
| 5C | 1.392 | 1.510 | 1.605 | 2.453 | 2.837 | 3.257 |
| 6A | 1.397 | 1.492 | 1.604 | 2.495 | 2.832 | 3.267 |
| 6B | 1.369 | 1.476 | 1.599 | 2.423 | 2.856 | 3.231 |
| 7 | 1.397 | 1.480 | 1.603 | 2.444 | 2.777 | 3.265 |
| 8 | 1.352 | 1.452 | 1.581 | 2.383 | 2.733 | 3.207 |
| pooled US15 | 1.395 | 1.529 | 1.678 | 2.469 | 2.904 | 3.401 |

**case_original 4: Mid: waterside econ (WCC + tower)** (source label: Waterside economizer (water-cooled chiller); n=50 per zone)

| zone | PUE P5 | PUE P50 | PUE P95 | WUE P5 | WUE P50 | WUE P95 |
|---|---|---|---|---|---|---|
| 1A | 1.298 | 1.415 | 1.517 | 2.138 | 2.553 | 2.876 |
| 2A | 1.311 | 1.417 | 1.524 | 2.200 | 2.454 | 3.001 |
| 2B | 1.277 | 1.370 | 1.492 | 2.204 | 2.527 | 2.889 |
| 3A | 1.293 | 1.385 | 1.500 | 2.109 | 2.461 | 2.866 |
| 3B | 1.258 | 1.359 | 1.493 | 2.088 | 2.497 | 2.887 |
| 3C | 1.259 | 1.356 | 1.493 | 2.114 | 2.551 | 2.850 |
| 4A | 1.277 | 1.371 | 1.467 | 2.229 | 2.493 | 2.861 |
| 4B | 1.262 | 1.371 | 1.488 | 2.136 | 2.497 | 2.909 |
| 4C | 1.253 | 1.376 | 1.451 | 2.183 | 2.461 | 2.941 |
| 5A | 1.259 | 1.360 | 1.482 | 2.112 | 2.421 | 2.903 |
| 5B | 1.261 | 1.356 | 1.494 | 2.170 | 2.457 | 2.889 |
| 5C | 1.258 | 1.363 | 1.483 | 2.156 | 2.508 | 2.935 |
| 6A | 1.260 | 1.366 | 1.495 | 2.143 | 2.524 | 2.846 |
| 6B | 1.267 | 1.362 | 1.463 | 2.114 | 2.511 | 2.921 |
| 7 | 1.248 | 1.370 | 1.481 | 2.124 | 2.494 | 2.890 |
| 8 | 1.264 | 1.365 | 1.470 | 2.134 | 2.486 | 2.896 |
| pooled US15 | 1.264 | 1.370 | 1.496 | 2.127 | 2.480 | 2.902 |

**case_original 2: Large: waterside econ (WCC + tower)** (source label: Waterside economizer (water-cooled chiller); n=50 per zone)

| zone | PUE P5 | PUE P50 | PUE P95 | WUE P5 | WUE P50 | WUE P95 |
|---|---|---|---|---|---|---|
| 1A | 1.097 | 1.143 | 1.216 | 1.961 | 2.216 | 2.544 |
| 2A | 1.104 | 1.145 | 1.203 | 1.916 | 2.209 | 2.606 |
| 2B | 1.077 | 1.123 | 1.170 | 1.861 | 2.185 | 2.522 |
| 3A | 1.075 | 1.130 | 1.190 | 1.877 | 2.203 | 2.556 |
| 3B | 1.067 | 1.118 | 1.165 | 1.892 | 2.189 | 2.502 |
| 3C | 1.065 | 1.113 | 1.168 | 1.966 | 2.184 | 2.617 |
| 4A | 1.071 | 1.119 | 1.170 | 1.885 | 2.166 | 2.556 |
| 4B | 1.062 | 1.112 | 1.164 | 1.911 | 2.189 | 2.534 |
| 4C | 1.064 | 1.110 | 1.163 | 1.911 | 2.163 | 2.604 |
| 5A | 1.064 | 1.115 | 1.160 | 1.907 | 2.196 | 2.507 |
| 5B | 1.066 | 1.113 | 1.161 | 1.874 | 2.191 | 2.551 |
| 5C | 1.056 | 1.117 | 1.156 | 1.899 | 2.183 | 2.506 |
| 6A | 1.065 | 1.117 | 1.164 | 1.875 | 2.185 | 2.492 |
| 6B | 1.062 | 1.112 | 1.169 | 1.843 | 2.201 | 2.501 |
| 7 | 1.060 | 1.115 | 1.172 | 1.879 | 2.201 | 2.486 |
| 8 | 1.062 | 1.112 | 1.160 | 1.859 | 2.170 | 2.535 |
| pooled US15 | 1.065 | 1.120 | 1.175 | 1.885 | 2.191 | 2.556 |

**case_original 1: Large: AE + adiabatic (water-cooled chiller suppl.)** (source label: Airside economizer& adiabatic cooling (water-cooled chiller); n=50 per zone)

| zone | PUE P5 | PUE P50 | PUE P95 | WUE P5 | WUE P50 | WUE P95 |
|---|---|---|---|---|---|---|
| 1A | 1.123 | 1.197 | 1.264 | 0.723 | 1.368 | 2.069 |
| 2A | 1.129 | 1.218 | 1.284 | 0.626 | 1.460 | 1.990 |
| 2B | 1.103 | 1.155 | 1.214 | 0.411 | 0.641 | 0.934 |
| 3A | 1.094 | 1.162 | 1.220 | 0.384 | 0.785 | 1.130 |
| 3B | 1.066 | 1.132 | 1.209 | 0.116 | 0.368 | 0.728 |
| 3C | 1.072 | 1.131 | 1.195 | 0.039 | 0.418 | 0.810 |
| 4A | 1.088 | 1.150 | 1.210 | 0.282 | 0.540 | 1.022 |
| 4B | 1.052 | 1.119 | 1.183 | 0.046 | 0.192 | 0.403 |
| 4C | 1.064 | 1.126 | 1.175 | 0.017 | 0.103 | 0.598 |
| 5A | 1.059 | 1.133 | 1.180 | 0.109 | 0.315 | 0.691 |
| 5B | 1.072 | 1.124 | 1.182 | 0.018 | 0.143 | 0.346 |
| 5C | 1.060 | 1.124 | 1.180 | 0.000 | 0.092 | 0.435 |
| 6A | 1.073 | 1.131 | 1.187 | 0.169 | 0.318 | 0.616 |
| 6B | 1.072 | 1.112 | 1.188 | 0.000 | 0.074 | 0.480 |
| 7 | 1.073 | 1.127 | 1.189 | 0.115 | 0.237 | 0.592 |
| 8 | 1.068 | 1.127 | 1.175 | 0.000 | 0.057 | 0.247 |
| pooled US15 | 1.071 | 1.140 | 1.228 | 0.031 | 0.342 | 1.584 |

**case_original 18: Large: dry cooler + adiabatic assist (air-cooled chiller)** (source label: Dry cooler with adiabatic assist (air-cooled chiller); n=50 per zone)

| zone | PUE P5 | PUE P50 | PUE P95 | WUE P5 | WUE P50 | WUE P95 |
|---|---|---|---|---|---|---|
| 1A | 1.264 | 1.323 | 1.394 | 0.122 | 0.339 | 0.623 |
| 2A | 1.226 | 1.305 | 1.366 | 0.066 | 0.206 | 0.414 |
| 2B | 1.159 | 1.224 | 1.280 | 0.622 | 0.759 | 0.967 |
| 3A | 1.175 | 1.233 | 1.289 | 0.174 | 0.310 | 0.444 |
| 3B | 1.158 | 1.203 | 1.268 | 0.427 | 0.598 | 0.781 |
| 3C | 1.130 | 1.185 | 1.251 | 0.115 | 0.319 | 0.513 |
| 4A | 1.155 | 1.200 | 1.260 | 0.043 | 0.216 | 0.356 |
| 4B | 1.141 | 1.174 | 1.238 | 0.346 | 0.475 | 0.607 |
| 4C | 1.116 | 1.170 | 1.225 | 0.095 | 0.196 | 0.374 |
| 5A | 1.131 | 1.183 | 1.244 | 0.098 | 0.213 | 0.377 |
| 5B | 1.117 | 1.170 | 1.214 | 0.315 | 0.427 | 0.522 |
| 5C | 1.119 | 1.149 | 1.236 | 0.043 | 0.125 | 0.252 |
| 6A | 1.123 | 1.195 | 1.235 | 0.092 | 0.190 | 0.291 |
| 6B | 1.113 | 1.170 | 1.218 | 0.191 | 0.302 | 0.478 |
| 7 | 1.123 | 1.175 | 1.238 | 0.078 | 0.180 | 0.296 |
| 8 | 1.103 | 1.161 | 1.217 | 0.072 | 0.171 | 0.266 |
| pooled US15 | 1.123 | 1.197 | 1.324 | 0.103 | 0.283 | 0.729 |

**case_original 16_2: Large: IT liquid, dry cooler+adiabatic assist (ACC), cold plate (D2C)** (source label: IT Liquid cooling: dry cooler with adiabatic assist (air-cooled chiller); n=50 per zone)

| zone | PUE P5 | PUE P50 | PUE P95 | WUE P5 | WUE P50 | WUE P95 |
|---|---|---|---|---|---|---|
| 1A | 1.058 | 1.098 | 1.140 | 0.000 | 0.000 | 0.005 |
| 2A | 1.054 | 1.099 | 1.142 | 0.043 | 0.074 | 0.110 |
| 2B | 1.054 | 1.098 | 1.144 | 0.108 | 0.199 | 0.254 |
| 3A | 1.058 | 1.098 | 1.137 | 0.093 | 0.164 | 0.221 |
| 3B | 1.057 | 1.095 | 1.140 | 0.207 | 0.282 | 0.344 |
| 3C | 1.051 | 1.101 | 1.145 | 0.020 | 0.096 | 0.172 |
| 4A | 1.055 | 1.099 | 1.143 | 0.083 | 0.147 | 0.248 |
| 4B | 1.056 | 1.097 | 1.143 | 0.209 | 0.295 | 0.329 |
| 4C | 1.053 | 1.097 | 1.142 | 0.083 | 0.220 | 0.375 |
| 5A | 1.053 | 1.099 | 1.144 | 0.068 | 0.138 | 0.203 |
| 5B | 1.054 | 1.102 | 1.143 | 0.144 | 0.211 | 0.259 |
| 5C | 1.055 | 1.098 | 1.143 | 0.045 | 0.223 | 0.387 |
| 6A | 1.054 | 1.100 | 1.143 | 0.052 | 0.101 | 0.179 |
| 6B | 1.051 | 1.094 | 1.143 | 0.145 | 0.240 | 0.325 |
| 7 | 1.057 | 1.098 | 1.141 | 0.065 | 0.113 | 0.158 |
| 8 | 1.056 | 1.095 | 1.141 | 0.086 | 0.137 | 0.203 |
| pooled US15 | 1.053 | 1.098 | 1.143 | 0.002 | 0.155 | 0.315 |

**case_original 15_2: Large: IT liquid, WSE+WCC, cold plate (D2C)** (source label: IT Liquid cooling: waterside economizer (water-cooled chiller); n=50 per zone)

| zone | PUE P5 | PUE P50 | PUE P95 | WUE P5 | WUE P50 | WUE P95 |
|---|---|---|---|---|---|---|
| 1A | 1.081 | 1.210 | 1.277 | 1.752 | 2.001 | 2.344 |
| 2A | 1.085 | 1.175 | 1.247 | 1.795 | 1.971 | 2.286 |
| 2B | 1.067 | 1.138 | 1.195 | 1.756 | 1.969 | 2.296 |
| 3A | 1.064 | 1.156 | 1.213 | 1.730 | 1.983 | 2.344 |
| 3B | 1.069 | 1.135 | 1.187 | 1.749 | 1.942 | 2.328 |
| 3C | 1.087 | 1.138 | 1.189 | 1.726 | 1.952 | 2.357 |
| 4A | 1.065 | 1.138 | 1.199 | 1.753 | 1.984 | 2.281 |
| 4B | 1.070 | 1.123 | 1.167 | 1.728 | 1.943 | 2.329 |
| 4C | 1.075 | 1.129 | 1.187 | 1.721 | 1.969 | 2.324 |
| 5A | 1.062 | 1.124 | 1.187 | 1.750 | 1.940 | 2.278 |
| 5B | 1.057 | 1.115 | 1.180 | 1.738 | 1.953 | 2.271 |
| 5C | 1.067 | 1.125 | 1.177 | 1.776 | 1.982 | 2.236 |
| 6A | 1.069 | 1.124 | 1.173 | 1.746 | 2.004 | 2.276 |
| 6B | 1.067 | 1.115 | 1.166 | 1.724 | 1.934 | 2.226 |
| 7 | 1.065 | 1.122 | 1.165 | 1.741 | 1.945 | 2.264 |
| 8 | 1.057 | 1.114 | 1.157 | 1.737 | 1.954 | 2.337 |
| pooled US15 | 1.066 | 1.130 | 1.222 | 1.738 | 1.960 | 2.321 |

### 5.10 Reproducibility between the authors' own datasets (**C**) — use medians, treat P5/P95 as noisy

With only 50 Latin-hypercube samples per cell the tails move between runs. For the 12 cases present in both the 2025 `UE_by_CZ_CS.csv` and the 2025 sample file: mean |Δ| of the zone medians is 0.016 PUE (max 0.062) and 0.028 L/kWh (max 0.33, cases 1 and 3, the airside-economizer designs); mean |Δ| of P5/P95 is 0.017/0.025 PUE (max 0.07/0.12) and 0.030/0.036 L/kWh (max 0.60/0.56).
The 2022 `UE.xlsx` differs more from the sample file: mean |Δ| of P5/P95 is 0.047/0.099 PUE (max 0.16/0.44) and 0.071/0.121 L/kWh (max 0.60/0.78). Which run corresponds to the published 2022 figures is UNVERIFIED.

---

## 6. Measured facility data points and other (non-simulated) PUE/WUE evidence

### 6.1 Primary measured data (government lab / peer-reviewed)

| facility, design, climate | measurement window | PUE | WUE (L per IT kWh) | notes and locator |
|---|---|---|---|---|
| **NREL ESIF HPC data center**, Golden CO (Jefferson County, IECC 5B). Direct component-level warm-water liquid cooling (cold plates), 24 °C (75 °F) supply, 35–40 °C return reused for building heat, **no mechanical chillers**; heat rejection hierarchy: heat reuse → thermosyphon cooler (dry) → open evaporative cooling towers | first full year with the thermosyphon hybrid, 2016-09-01 to 2017-08-31; hourly average IT load 888 kW, IT energy 7,776 MWh | **1.034** (trailing-12-month average; design target ≤1.06; ERE 0.929) | **0.70** with the hybrid; would have been **1.27** with heat recovery + towers only and **1.42** with towers only | NREL TP-7A40-72196 PDF pp.6, 12–13, 17–18 and NREL/PR-7A40-74464 PDF pp.4, 18 (**V**). Annual heat rejection: building reuse 10.5 %, thermosyphon 42.5 %, towers 47 %; tower cycles of concentration 12.8; humidification (makeup-air-unit) water not metered; water = make-up meters + estimated blowdown (so blowdown is inside the number). Two-year water saving 7,950 m³ (2.10 million gal). The report notes the tower must still be sized for the entire IT load on the hottest hours (PDF p.14) — the only design-day statement found, with no PUE figure. |
| **MGHPCC**, Holyoke MA (Hampden County, IECC 5A). Air-cooled racks with in-row coolers on chilled water; water-cooled chillers + evaporative towers with free cooling when weather allows (Lei & Masanet's preprint classes it as water-cooled chiller + waterside economizer, p.4) | years ending Sept 2015 and Sept 2016; IT load ≈1 MW, about 10 % of provisioned IT power (strong part-load effect) | **1.37** (year to Sept 2015), **1.29** (year to Sept 2016); lowest monthly 1.21; PUE rises in summer; chillers off Oct–Mar | monthly range **1.3–2.5**; makes the point that blowdown is a fixed rate at low load and WUE falls toward ≈1.4 as load grows | Sharma et al. 2017, IEEE Internet Comput., PDF pp.3–4 (**V**). Water includes windage, blowdown and filter backwash. The same paper cites Facebook-reported WUE of 0.28 (Prineville) and 0.34 L/kWh (Forest City) (**S**, p.5). Model comparison (**C**): 2025 sample file case 4 (mid-size waterside economizer, water-cooled chiller) in zone 5A: PUE P5/P50/P95 = 1.259/1.360/1.482, WUE 2.112/2.421/2.903 — measured PUE inside the band, measured WUE at the low end/below. |

### 6.2 Surveys and vendor-reported fleet values (self-reported; boundaries differ, see §2)

| source | values | locator / flag |
|---|---|---|
| Uptime Institute Global Data Center Survey 2025 (survey statistic, self-reported, global) | weighted-average annual PUE **1.54** (2025, n = 681); 1.56 (2024), 1.58 (2023), 1.55 (2022), 1.57 (2021), 1.59 (2020), 1.67 (2019), 1.58 (2018), 1.65 (2014), 1.98 (2011), 2.50 (2007); facilities commissioned within five years 1.48; facilities ≥20 MW 1.44; many new facilities at high latitudes in North America and Europe reach 1.3 or better, reported by 15 % of respondents | Keynote report PDF pp.7–8, Fig. 2 (**V**); not climate- or design-resolved |
| DOE/FEMP Best Practices Guide (2024) | average data center PUE 1.6; "super-efficient" below 1.1; labels Standard 1.6 / Good 1.4 / Better 1.1; Uptime 2022 large-data-center annual average 1.55 (**S**) | PDF p.38 (printed 29) (**V**) |
| ASHRAE TC 9.9 liquid-cooling white paper (2021) | states that liquid-cooled solutions allow PUE below 1.1 and warm-water cooling reduces or eliminates chillers; example SuperMUC-NG (Garching, Germany): direct warm-water cooling at 40–45 °C with adsorption chillers, cooling partial PUE below 0.07 | PDF pp.8, 21 (**V**; a claim without climate qualifier; copyrighted, paraphrased) |
| **VENDOR** Google Data Centers, "Power usage effectiveness" page (retrieved 2026-10-03) | fleet-wide trailing-twelve-month PUE **1.09** (2025), **1.09** (2024), 1.10 (2019–2023); fleet quarterly 1.08–1.11 in 2025; boundary stated as all large-scale sites at stable operation, all seasons and all overhead sources; campus TTM PUE (2025, e.g.) Lancaster OH 1.04, Omaha NE 1.05, Henderson NV 1.09, Midlothian TX 1.10, Council Bluffs IA 1.11, Mayes County OK 1.12, Storey County NV 1.14, Singapore 1.12–1.14. No WUE and no cooling design stated | page text parsed from cached HTML (**V**, VENDOR) |
| **VENDOR** Meta 2025 Environmental Data Index (FY2024) | PUE 1.10 (2020), 1.09, 1.08, 1.08, **1.08** (2024); **WUE (withdrawal-based)** 0.30, 0.26, 0.20, 0.18, **0.19** (2024); data-center water withdrawal 3,000 / 3,418 / 3,618 / 3,881 / **4,145 ML** (2020–2024); data-center water consumption 2,197 (2020), 2,511 (2022), 2,938 (2023), **2,974 ML** (2024); consumption ÷ withdrawal = 0.73 (2020), 0.69 (2022), 0.76 (2023), **0.72 (2024)** (**C**); the 2021 consumption row (data centers 162, offices 2,406) looks transposed in the source and is not used | PDF pp.8–11, 18 (**V**, VENDOR); consumption estimated as withdrawal minus discharge or from cycles of concentration |
| **VENDOR** Microsoft datacenter efficiency page | PUE / WUE (L/kWh): global FY24 1.16 / 0.30, FY25 1.17 / 0.27; Americas FY24 1.16 / 0.38, FY25 1.16 / 0.34; Asia-Pacific FY24 1.25 / 0.03, FY25 1.28 / 0.25; EMEA 1.16 / 0.03 in both years | HTML table (**V**, VENDOR); owned and controlled sites operational ≥12 months |
| **VENDOR** Microsoft blog, 2024-12-09 | new design (from Aug 2024) with chip-level liquid cooling in a closed loop and heat rejection by economizing chillers run at elevated water temperature; states that replacing evaporative with mechanical cooling will raise PUE, with only a nominal increase in fleet annual energy use; claims >125 million L/yr avoided per datacenter relative to a fleet WUE of 0.30 L/kWh; pilots Phoenix AZ and Mt. Pleasant WI in 2026, sites online late 2027 | cached HTML; claims, no measured values for the new design (**V** text, VENDOR, UNVERIFIED performance) |
| LBNL 2016 report (LBNL-1005775) | national assumption 1.8 L per kWh of total facility energy; the same report uses 7.6 L per kWh of electricity for generation water (a different method from the 4.52 L/kWh of LBNL 2024) | PDF p.37 (**V**) |

Cross-check summary (**C**): the measured PUE of the two primary facilities lies inside (MGHPCC) or below (NREL) the simulated bands of the closest designs; the vendor fleet PUE of 1.08–1.17 is consistent with the hyperscale-practice rows (1.10–1.20). Measured WUE of tower-based facilities (NREL 0.70–1.42, MGHPCC monthly 1.3–2.5) sits at or below the lower part of the simulated bands for towered designs (P5 1.74 for large-scale IT-liquid, 2.1–2.7 for mid-size), i.e. the model's WUE for towered designs is conservative relative to the measured cases retrieved; **chiller-less warm-water liquid designs (NREL) fall below the model's P5 for both PUE and WUE**.
No measured source retrieved gives PUE/WUE for an air-cooled, no-evaporation hyperscale design in a named climate.

---

## 7. Peak (design-day) PUE — what is and is not documented

**Result: no source retrieved publishes a peak-hour or design-day PUE for any cooling design.** The facility demand needed for the power-capacity check (`peak_facility_MW = peak_IT_MW × PUE_peak`) therefore has no documented per-design coefficient.

| evidence | what it gives | limits |
|---|---|---|
| Lei–Masanet model (hourly PUE, Eq. 10) | hourly PUE exists inside the model; published/repo results are annual means only; extreme hot hours explicitly out of scope (preprint p.21) | the hourly series are not published; the repo samples are Sobol-type single-hour evaluations over a wide range of dry-bulb/RH, not a usable design-day lookup (inspected: 17,500–25,900 rows per hyperscale design; each facility parameter set appears about once) |
| vendor-measured quarterly PUE (Google, **VENDOR**, **C** ratios) | fleet max-quarter PUE ÷ trailing-twelve-month PUE = 1.018 (2017, 2018, 2021–2025) or 1.027 (2019, 2020); across the 31 campuses with four quarters and a TTM value in 2025: median 1.018, mean 1.018, maximum 1.070 (absolute uplift median 0.02, maximum 0.08) (Storey County NV: quarters 1.09/1.16/1.22/1.11, TTM 1.14; Mayes County OK: 1.09/1.16/1.15/1.09, TTM 1.12); Mesa AZ (new site) quarterly 1.22 (Q1 2026) and 1.28 (Q2 2026) without a TTM yet | quarterly means, not hourly peaks; vendor-reported; design not disclosed; summer-quarter factor only |
| measured MGHPCC | PUE rises in summer; lowest monthly 1.21 vs annual 1.29–1.37 (about +6 to +13 % between best month and annual mean, at low load) | monthly; low IT load |
| ASHRAE Standard 90.4 Addendum g to the 2016 edition (approved 2019; **V**, copyrighted — few numbers quoted) | defines **design MLC** (all cooling, fan, pump and heat-rejection *design* power ÷ ITE design power) and removes the design-MLC compliance path in favour of an **annualized MLC** evaluated at 100 % and 50 % ITE load (foreword, PDF p.3). Maximum annualized MLC by ASHRAE-169 zone, ITE design power > 300 kW (≤ 300 kW): 1A 0.26 (0.31), 2A 0.23 (0.29), 3A 0.21 (0.27), 5A 0.16 (0.25), 8 0.13 (0.22) (Table 6.6, PDF p.5; the 2016-edition values 0.36/0.35/0.33/0.33/0.32 for > 300 kW were lowered). Worked example for zone 1A: max MLC 0.260 (was 0.460) + max ELC 0.297 → maximum overall systems value 0.557 (was 0.757) (PDF p.4) | these are **compliance ceilings**, not expected performance; a PUE-like ceiling would be 1 + MLC + ELC (+ other loads) — not stated in the standard as a PUE; the 2022 edition's Addendum g (2024) redefines annualized MLC relative to total data-center energy and loosens the targets, so which numbers are in force is UNVERIFIED |
| NREL TP-72196 | cooling-tower capacity must cover the entire IT load in the hottest hours (PDF p.14); design target PUE ≤1.06 (PR-74464 p.4) | no peak PUE number |

Implication for Phase 3: a peak/design-day PUE must be entered as an explicit, labelled `scenario` assumption (for example `PUE_peak = PUE_annual × k` with a user-supplied k). The documented evidence brackets the *summer-quarter* uplift of well-run hyperscale fleets at about +2 % (fleet and median campus) to +7 % (worst of 31 campuses), which is **not** a design-hour value and should not be presented as one. If no k is supplied the peak demand must stay UNKNOWN and the power-capacity requirement UNKNOWN (never PASS).

---

## 8. Climate inputs: what a per-grid-cell application needs

### 8.1 Zone map for cells (cached, retrieved)

PNNL "Guide to Determining Climate Zone by County: Building America and IECC 2021 Updates" data files (https://basc.pnnl.gov/sites/default/files/ClimateZoneDataFiles.zip, 855,435 B, sha256 `4ca82aae…5b8c`): shapefile `ClimateZones.shp`, EPSG:4269 (NAD83), 3,220 county polygons with fields `GEOID` (G+FIPS), `IECC15`, `IECC21`, `BA15`, `BA21`, `Moisture15`, `Moisture21` (**V**; report number PNNL-33270 per search result, UNVERIFIED). CONUS + DC: 3,108 polygons.
The Lei–Masanet zones follow Baechler et al. 2015 (cited in the preprint) = the pre-2021 designation. Third-party `climate_zones.csv` in the authors' repo equals the PNNL **2015** assignment for 99.9 % of 3,141 comparable counties and the 2021 assignment for only 88.1 % (**C**).
Counties per zone in CONUS (**C** from the shapefile; IECC15 → IECC21): 1A 3 → 7; 2A 222 → 239; 2B 20 → 20; 3A 577 → 637; 3B 109 → 110; 3C 14 → 14; 4A 736 → 717; 4B 57 → 66; 4C 38 → 34; 5A 617 → 637; 5B 150 → 146; **5C 0 → 4 (Kitsap, Island, San Juan, Clallam, WA)**; 6A 337 → 299; 6B 125 → 119; 7 102 → 58; plus one record (Bristol city VA) with zone 4 and no moisture letter in both editions; 359 CONUS counties change zone between 2015 and 2021 (e.g. Ellis County TX 3A → 2A).
Consequence: pick the zone vintage deliberately and record it. The 2025 sample file contains zone 5C values (the 2022 xlsx and the 2025 quantile CSV do not), so the IECC21 map is usable with the sample file; the IECC15 map is the vintage of the original model.

### 8.2 Options for applying a documented climate relationship per cell

| option | documented? | climate inputs per cell | resolution/limits | feasible now? |
|---|---|---|---|---|
| A. zone lookup of annual PUE/WUE quantiles per design (derived CSV / source files) | yes — tables/samples from the hourly physics model (§5) | IECC/ASHRAE zone (thermal 1–8 + moisture A/B/C) via county FIPS or area-majority | 15 CONUS zones (+5C); one representative-city TMY per zone; zone-boundary discontinuities; annual means only; no peak; no future climate | **yes** |
| B. run the hourly physics model per cell | equations published (preprint CC BY); code public but unlicensed and needs pickled COP regressors not described in the paper | hourly dry-bulb, RH, pressure (TMY) for each cell (wet-bulb derived) | would give cell-level annual PUE/WUE and hourly extremes | **no**: Phase 2 has only monthly/daily mean temperature normals (no RH, no hourly, no wet-bulb; internal note `docs/research/phase2/noaa_ncei_climate.md`), and re-implementation is blocked by the unspecified COP regression and licence |
| C. wet-bulb-hour criterion | only as a DOE applicability rule of thumb for waterside economizers (wet-bulb < 55 °F for ≥3,000 h/yr, PDF p.28) | hourly or binned wet-bulb | gives a yes/no suitability flag, not PUE/WUE | no (needs hourly wet-bulb); could serve as a later cross-check of the zone lookup |
| D. constant-assumption scenario per design | yes (this report supplies sourced values) | none | does **not** model geographic differences and must be labelled so | yes (fallback) |

---

## 9. Recommendations for the Phase 3 cooling-design representation (non-binding; for the technical lead)

1. **Represent a design as a complete record**, not as "liquid" or "dry": `it_heat_transport` (air / rear-door / cold plate / immersion), `facility_water_class_or_range` (e.g. cold plate 2–40 °C in the source scenarios), `economizer` (none / airside / waterside), `supplementary_cooling` (air- or water-cooled chiller; the source data always has one), `heat_rejection` (dry / adiabatic-assisted dry / evaporative tower), `humidification`, plus `source_case_id` and `size_practice_class` (large-scale = hyperscale operating practice). Never pair the PUE of one design with the WUE of another; take both from the same (case, zone) distribution (§5.4).
2. **Use the zone-level quantile tables as the documented climate-dependent option**, labelled `scenario` (documented-model output, not observed) with a `proxy` flag for the zone resolution; confidence medium for PUE (cross-checked against LBNL 2024 and two measured facilities), low–medium for WUE (boundary issues in §2, blowdown inside the number, towered-design values above all measured values retrieved).
   The documented operating-practice spread is large relative to the zone effect for most designs, so treat **P50 as the baseline and P5/P95 as sensitivity cases**; P5/P95 are sampling-limited (n = 50) and moved by up to 0.12 PUE / 0.6 L/kWh between the authors' own runs (§5.10).
3. **If the zone lookup is not adopted, use a clearly labelled constant-assumption scenario** and do not claim it models geographic cooling differences. Sourced constants: pooled-CONUS P50 per design (§5.5); or LBNL 2024 aggregates for hyperscale (PUE 1.22, WUE 0.32 L/kWh_IT, 10th–90th 1.16–1.28 and 0.20–0.46) or AI-specialized (1.14; 0.61) facilities (§4.5); or the Uptime global average PUE 1.54 for legacy/enterprise-type facilities (§6.2).
4. **Peak PUE:** no documented design-day value exists. Provide `peak_pue` as a user-supplied scenario assumption (`basis: project_assumption`, rationale citing §7), or leave the peak facility demand and the power-capacity requirement UNKNOWN; do not derive it by scaling with a made-up factor. The only quantitative anchors (summer-quarter uplift about +2 % fleet/median campus, up to +7 %; vendor quarterly means) are not design-hour values.
5. **Water definitions:** store the source WUE as "site water use per IT kWh (source definition: includes cooling-tower blowdown/draw-off, adiabatic and humidification water)". Do not label it pure consumption. If a consumption-only value is needed, the documented route is the model's own split: make-up = evaporation × CC/(CC−1) so the blowdown share is about 1/CC (7 % at CC = 15, 33 % at CC = 3, ignoring windage; cycles of concentration range 3–15 in the large-scale cases, NREL measured 12.8) — a **C** derivation from Eq. 5–7, to be confirmed with the authors. Meta's fleet consumption/withdrawal ratio (0.69–0.76; vendor; mixed cooling systems) is a vendor cross-check, not a coefficient for this model. Keep W_electricity separate (the other research tasks cover grid water factors; LBNL 2024's 4.52 L/kWh national average is a context value only).
6. **Do not use** the LBNL 2024 national-average WUE (0.36–0.375 L/kWh) or the LBNL 2016 1.8 L/kWh constant as per-IT-kWh WUE without re-basing (§4.6, §2). Do not use the "Lei–Masanet climate-specific PUE" numbers of arXiv 2606.05420 (not traceable to a table).
7. **Climate input:** assign each cell a zone through county FIPS using the PNNL shapefile; record the vintage (IECC15 matches the original model; IECC21 adds 5C, which only the 2025 sample file covers). Decide a rule for cells spanning counties (area-majority or centroid) and record it. Cells in zones without data (e.g. any future 8-zone or Alaska) stay UNKNOWN.
8. **Use measured data as validation anchors, not inputs** (NREL ESIF, MGHPCC; §6.1). Report that chiller-less warm-water liquid designs outperform the model's P5, so a "best case" scenario for design (d)/(e) can legitimately sit below P5 only with a cited measured source (NREL: PUE 1.034, WUE 0.70 hybrid / 1.27–1.42 towers-only, zone 5B, 888 kW IT).
9. **Ask the sources, not an LLM:** (i) obtain the published RCR 182:106323 tables/supplement through institutional access or the authors and check which of the three authors' datasets reproduces them; (ii) ask the authors for a licence for the data (the repos have none) and for the hourly series if design-day values are wanted; (iii) ask LBNL which normalisation the national WUE uses.

---

## 10. Caveats, UNVERIFIED items and gaps

* **Published article not read.** All Lei–Masanet numbers come from the 2021 preprint, the authors' repos (no licence; read only; nothing executed) and the 2025 papers. The 2022 xlsx, the 2025 quantile CSV and the 2025 sample file are three different runs of the same framework (§5.10); which one equals the published tables is UNVERIFIED.
* **Derived values are mine.** The pooled and per-zone percentiles in §5 and the CSV are computed from `UEs_16cases.csv` by `numpy.percentile`; they are not published numbers. Digitized Fig. 4.4 values (§4.4) are approximate (±0.005 PUE, ±0.014 L/kWh).
* **Zone resolution.** One representative-city TMY per zone (national study: 965 stations) and annual means only; no hourly/design-day values; no future-climate result. Sample size 50 per cell.
* **Constant IT load.** The model has no IT-utilization dependence beyond a sampled chiller partial-load factor; PUE at a 0.80 load factor is not documented (the MGHPCC case at ≈10 % load shows the sign of the effect: higher PUE at low load).
* **Design set.** Every simulated design has a supplementary chiller; no chiller-less design; no indirect-evaporative CRAC design; no large-scale airside-economizer-without-adiabatic design; the "large-scale / mid-size / small" classes bundle operating practice with design.
* **LBNL 2024 figures are expert-adjusted and "as designed";** Fig. 4.4 has no printed numbers; 17 rows vs 18 cases; national WUE normalisation unclear (§4.6).
* **Vendor numbers** (Google, Meta, Microsoft) are self-reported; Microsoft's WUE basis is ambiguous (consumption vs withdrawal), Meta's is withdrawal; Meta's 2021 consumption row looks transposed.
* **ASHRAE 90.4 numbers** are code ceilings from a 2019 addendum to the 2016 edition; later editions redefine the quantity (§7). Only a few numbers are reproduced because the files are copyrighted.
* **Not retrieved:** ISO/IEC 30134-2/-9 (ISO's WUE wording is only a secondary citation), Green Grid WP#49, ASHRAE Thermal Guidelines (5th ed.), the 90.4 base standard, Lei et al. 2023, Siddik et al. 2024 balancing-authority factors, the PNNL report text (number PNNL-33270 from a search result only).
* **Infrastructure notes:** `nrel.gov` stopped resolving (NXDOMAIN) from this machine; NREL material is served from `docs.nlr.gov` (the National Laboratory of the Rockies successor domain) — other Phase 2/3 source URLs under nrel.gov may need the same substitution. Some publisher/aggregator sites (ScienceDirect, IOP, eScholarship PDFs, LBNL datacenters site) block non-browser clients; none was circumvented.

### Open questions for the technical lead / the authors

1. Which zone-map vintage (PNNL IECC15 vs IECC21) and which per-cell assignment rule will the project use?
2. Should `scenario_id` encode operating-efficiency quantiles (P5/P50/P95), or should cooling-design alternatives keep a single P50 with quantiles reserved for Phase 6 sensitivity?
3. Which design is the project default for a 100 MW AI campus: the data support large-scale rows only (cases 0, 1, 2, 18, 15_x, 16_x); is a chiller-less liquid design to be added from NREL measurements as a separately cited scenario?
4. Peak PUE: accept a user-supplied scenario, or request the authors' hourly series?
5. Confirmation from LBNL of the national WUE normalisation and of whether Fig. 4.4's whiskers are extremes or fences.

---

## Appendix A. Retrieved sources (key documents; full list with all cached files in `data/raw/_literature/download_log_cooling_designs_pue_wue.json`)

| id | document | URL | bytes | sha256 (first 16 hex) | retrieved UTC |
|---|---|---|---|---|---|
| S1 | LBNL-2001637, Shehabi et al., 2024 | https://eta-publications.lbl.gov/sites/default/files/2024-12/lbnl-2024-united-states-data-center-energy-usage-report_1.pdf | 4,031,183 | `3a2257cdf4c35035` | 2026-10-03T02:46:02Z |
| S2 | Lei & Masanet preprint v1 (CC BY 4.0), 2021 | https://assets-eu.researchsquare.com/files/rs-769999/v1_covered.pdf | 1,493,965 | `e310a6f25c979fbc` | 2026-10-03T02:53:28Z |
| S3a | authors' repo: UE.xlsx (5th/95th, 10 cases x 15 zones) | https://raw.githubusercontent.com/nuoaleon/Data-Center-Water-footprint/main/Simulation%20Results/UE.xlsx | 21,774 | `adc2a6ca4ad96fb7` | 2026-10-03T02:54:02Z |
| S3b | authors' repo: hourly model code (read only) | https://raw.githubusercontent.com/nuoaleon/Data-Center-Water-footprint/main/simulation_funs_DC.py | 52,202 | `74ea9da658482a29` | 2026-10-03T02:54:03Z |
| S4a | Lei, Lu, Shehabi, Masanet 2025, RCR 219:108310 (accepted ms.) | https://www.osti.gov/pages/servlets/purl/2572888 | 7,693,301 | `63380b8a8237a477` | 2026-10-03T03:01:32Z |
| S4b | authors' repo: 19,000 PUE/WUE samples (source of the derived CSV) | https://raw.githubusercontent.com/nuoaleon/The-Water-Use-of-Data-Center-Workloads-A-Review-and-Assessment-of-Key-Determinants/main/data/UEs_16cases.csv | 2,811,275 | `4924fdb451dfefc4` | 2026-10-03T03:00:27Z |
| S5a | Lei, Ganeshalingam, Masanet, Smith, Shehabi 2025, E&B 339:115734 | https://www.osti.gov/pages/servlets/purl/3398559 | 1,132,162 | `e5218a1392820e72` | 2026-10-03T02:58:16Z |
| S5b | authors' repo: 5-quantile PUE/WUE by zone/design | https://raw.githubusercontent.com/nuoaleon/Shedding-Light-on-U.S.-Small-and-Midsize-Data-Centers-Exploring-Insights-from-the-CBECS-Survey/main/Datasets/UE_by_CZ_CS.csv | 48,415 | `b4764be34f9b37d9` | 2026-10-03T02:59:01Z |
| S5c | authors' repo: county -> IECC zone (third-party-schema table) | https://raw.githubusercontent.com/nuoaleon/Shedding-Light-on-U.S.-Small-and-Midsize-Data-Centers-Exploring-Insights-from-the-CBECS-Survey/main/Datasets/climate_zones.csv | 100,067 | `36abbdb80d0b968f` | 2026-10-03T02:59:01Z |
| S6 | The Green Grid WP#35 (WUE), 2011 | https://www.thegreengrid.org/system/files/store/WUE_v1.pdf | 333,876 | `737871d9fc5c8585` | 2026-10-03T03:13:33Z |
| S7 | DOE/FEMP Best Practices Guide, rev. July 2024 | https://www.energy.gov/sites/default/files/2024-07/best-practice-guide-data-center-design_0.pdf | 1,428,000 | `f4db5c0151549334` | 2026-10-03T03:34:12Z |
| S8 | Uptime Institute Global Data Center Survey 2025 keynote | https://datacenter.uptimeinstitute.com/rs/711-RIA-145/images/2025.Annual.Survey.Report.pdf?version=0 | 1,534,208 | `b4e1075cb8ee6a72` | 2026-10-03T03:16:36Z |
| S9a | NREL/TP-7A40-72196 (2018) | https://docs.nlr.gov/docs/fy18osti/72196.pdf | 1,030,424 | `c850d6b4bc344b24` | 2026-10-03T03:18:29Z |
| S9b | NREL/PR-7A40-74464 (2019) | https://docs.nlr.gov/docs/fy19osti/74464.pdf | 2,709,611 | `e78fccfd0ad42da2` | 2026-10-03T03:18:16Z |
| S10 | Sharma et al. 2017 (MGHPCC) | https://lass.cs.umass.edu/papers/pdf/mghpcc-ic.pdf | 505,090 | `ce7d77781edc2e4d` | 2026-10-03T03:12:15Z |
| S11a | VENDOR: Google PUE page snapshot | https://datacenters.google/efficiency/ | 644,505 | `69c480ae6d2f0430` | 2026-10-03T03:19:22Z |
| S11b | VENDOR: Meta 2025 Environmental Data Index | https://sustainability.atmeta.com/wp-content/uploads/2025/10/Meta_2025-Environmental-Data-Index.pdf | 2,266,742 | `d7527cd233088691` | 2026-10-03T03:22:00Z |
| S11c | VENDOR: Microsoft efficiency page snapshot | https://datacenters.microsoft.com/sustainability/efficiency/ | 144,281 | `97b5a4d2c5580842` | 2026-10-03T03:22:34Z |
| S11d | VENDOR: Microsoft blog 2024-12-09 | https://www.microsoft.com/en-us/microsoft-cloud/blog/2024/12/09/sustainable-by-design-next-generation-datacenters-consume-zero-water-for-cooling/ | 268,193 | `1235844975e5839d` | 2026-10-03T03:23:08Z |
| S12a | ASHRAE 90.4-2016 Addendum g (2019) | https://www.ashrae.org/file%20library/technical%20resources/standards%20and%20guidelines/standards%20addenda/90_4_2016_g_20190627.pdf | 750,215 | `c5bae11e824a97e6` | 2026-10-03T03:09:18Z |
| S12b | ASHRAE 90.4-2022 Addendum g (2024) | https://www.ashrae.org/file%20library/technical%20resources/standards%20and%20guidelines/standards%20addenda/90_4_2022_g_20240131.pdf | 1,106,128 | `150a1e1585c27b1c` | 2026-10-03T03:09:19Z |
| S12c | ASHRAE TC 9.9 liquid-cooling white paper (2021) | https://www.ashrae.org/file%20library/technical%20resources/bookstore/emergence-and-expansion-of-liquid-cooling-in-mainstream-data-centers_wp.pdf | 1,042,420 | `56e7c3739f6f1af0` | 2026-10-03T03:34:10Z |
| S13 | LBNL-1005775 (2016) | https://www.osti.gov/servlets/purl/1372902 | 2,142,873 | `ce4fcb565713814e` | 2026-10-03T03:23:22Z |
| S14a | PNNL climate-zone county shapefile (IECC15/IECC21) | https://basc.pnnl.gov/sites/default/files/ClimateZoneDataFiles.zip | 855,435 | `4ca82aae8dec09da` | 2026-10-03T03:26:06Z |
| S14b | DOE Building America climate guide v7.3 (2015) | https://www.energy.gov/sites/prod/files/2015/10/f27/ba_climate_region_guide_7.3.pdf | 6,356,555 | `7058971811d4aa26` | 2026-10-03T03:24:49Z |
| S15a | secondary: arXiv 2606.05420 | https://arxiv.org/pdf/2606.05420 | 7,628,284 | `463a1f38c01cf89c` | 2026-10-03T03:26:55Z |
| S15b | secondary: arXiv 2607.02531 | https://arxiv.org/pdf/2607.02531 | 35,326,793 | `248e856cf556669f` | 2026-10-03T03:31:36Z |

## Appendix B. Methods and checks performed

* **Fig. 4.4 digitization.** `pdfimages` extracted the native 1002×756 PNG of PDF p.46. Gridlines (light-grey, 3 px) calibrate the axes: PUE gridlines at x = 308, 358, 407, 457, 507, 556, 606 px ↔ 1.00…2.50; WUE gridlines at x = 676, 749, 822, 896, 969 px ↔ 0…4. Box rows were located from the three fill colours (seaborn desaturated green/orange/blue; 17 rows). Whisker caps = outermost dark pixels on the row centre line; box edges and median = dark-pixel runs two pixels below the box top (where no whisker line crosses). Result file: `data/raw/_literature/_img_cooling_designs/fig44_digitized.json`.
* **Derived percentiles.** `numpy.percentile(series, [5, 25, 50, 75, 95])` (linear interpolation) on the 50 samples of each (`Case (Original)`, `Climate Zone`) in `UEs_16cases.csv`; pooled row = 750 samples over the 15 CONUS zones.
* **Checks that passed:** (1) the five climate-zone exceptions named in the preprint text reproduce from the 5th-percentile columns of `UE.xlsx`; (2) pooled sample medians/quartiles match the digitized LBNL Fig. 4.4 boxes within ~0.01–0.02 PUE; (3) the printed aggregate ranges in E&B Table 2 match LBNL Fig. 4.5; (4) the 15_x/16_x suffix order matches Fig. S6.3(a) medians; (5) the third-party `climate_zones.csv` equals PNNL IECC15 for 99.9 % of counties; (6) the quantile order in `UE_by_CZ_CS.csv` is confirmed by the repo notebook; (7) Google fleet seasonal ratios recomputed from the parsed page.
* **Checks that failed or could not be done:** national LBNL WUE normalisation is inconsistent with its stated definition (§4.6); published RCR tables not compared; the model was not re-run (no licence; pickled COP regressors; no execution of downloaded code).
* **Quotations** are intentionally minimal; locators (PDF page, table/figure, equation) are given for each number so the cached copies can be used to re-verify.
