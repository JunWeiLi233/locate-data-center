# Processed data dictionary

The complete column-to-dtype listing is generated in [processed_dictionary.json](../outputs/task2/processed_dictionary.json). Parquet tables have the same names as the entries in that file. Candidate JSON uses `null` for missing numbers and strings for all geographic IDs.

| Table | Grain and meaning | Units / notes |
|---|---|---|
| candidates | One row per selected county | FIPS strings; 2025 Census geography; screening proxies |
| candidate_polygons | One 2025 TIGER polygon per selected county | GeoParquet, EPSG:4326; original official boundaries |
| electricity_prices | State × sector × year × month, 2020–July 2026 | Nominal observation-year USD/MWh; retains cents/kWh, sales MWh, Preliminary/Final status |
| price_baselines | State × sector; full 2025 calendar year | Sales-weighted USD/MWh; requires 12 valid months; source status retained |
| grid_regions | One row per EPA eGRID region | 2023 total-output CO2e lb/MWh and kg/MWh; generation MWh; stored resource-mix fractions 0–1 |
| grid_overlaps | County × eGRID map region | m² in EPSG:5070; fraction of entire county geometry; not an electricity mix |
| water_overlaps | County × Aqueduct basin/admin/aquifer union | Raw stress/depletion, 0–5 scores, category/label, overlap m² and county-area fraction |
| water_future_overlaps | County × HydroBASINS region | 2030/2050 `bau`/`opt`/`pes` raw stress, scores and labels, plus overlap fractions |
| climate_monthly | County × assigned station × month | Source temperature °F plus converted °C; degree days °F·day above 65°F; station elevation m; completeness/measurement flags and years retained |
| hazards | One record per official NRI county/equivalent | Complete 3,232-row download; six hazard-specific frequencies, loss values, risk scores and ratings |

| Candidate feature | Definition / provenance |
|---|---|
| candidate_id / county_fips | 5-digit Census FIPS strings; initially identical |
| state_fips / state_abbr | 2-digit state FIPS string and postal abbreviation |
| name / lat / lon / land_area_m2 | Census 2025 county name, representative point in decimal degrees, land area m² |
| electricity_price_usd_per_mwh | Sales-weighted EIA 2025 industrial retail proxy; nominal 2025 USD; preliminary |
| commercial_price_usd_per_mwh | Same aggregation for commercial-sector sensitivity; not a negotiated tariff |
| electricity_price_base_year / source_status / valid_months | Observed price year, original release status, valid calendar months |
| grid_region | Unique primary polygon at county representative point; supplying utility unverified |
| grid_region_options | All primary grid-map regions intersecting county geometry |
| grid_border_or_multiple_subregions | True for multiple primary regions or any overlap with EPA's multiple-service layer |
| grid_multiple_subregion_area_fraction | Fraction intersecting EPA's multiple-service layer; not supplier probability |
| grid_co2e_kg_per_mwh | eGRID `SRC2ERTA` × 0.45359237; annual average CO2e, not marginal emissions |
| renewable/coal/gas_generation_fraction | Historical regional generation fractions stored in the Excel cells; not firm power or hourly clean supply |
| water_region_id / point_region_options | Aqueduct `string_id` at representative point; all border matches retained |
| water_stress_raw | `bws_raw`; demand/supply screening indicator; `-9999` → null; `9999` severe scarcity sentinel retained |
| water_stress_score / category / label | `bws_score` 0–5 and publisher category/label; arid-and-low-use category stays explicit |
| water_depletion_raw | `bwd_raw`; screening context, not an allocation or consumption volume |
| climate_station_id / distance_km / elevation_m | Actual NOAA station ID, haversine distance and station elevation; elevation compatibility remains unverified |
| climate_elevation_check | Explicit limitation: no parcel/county elevation suitability evidence |
| feasibility / feasibility_status | Power, water allocation, zoning/parcel and redundant fiber statuses with evidence; initially all unverified |
| coverage / provenance | Measured versus modeled/missing/assumed status and source IDs resolved in source manifest |
| reliability_indicators | Null until recommended utility reliability data are joined |

FEMA hazard prefixes: `IFLD` inland flood, `CFLD` coastal flood, `WFIR` wildfire, `HWAV` heat wave, `HRCN` hurricane, `DRGT` drought. Suffixes: `_AFREQ` documented annualized frequency (hazard-specific events or affected-area frequency; not facility incident probability); `_EALT` expected annual loss of existing assets in December 2024 dollars; `_RISKS` risk score, and `_RISKR` rating. Do not derive facility downtime, a monetary data center loss, or chance constraints from these values. Exact aliases and publisher definitions remain frozen in `data/raw/fema/1.20/fields.json` and the technical PDF.

`water_future_overlaps` uses `{scenario}{year}_ws_x_r` for raw water stress, `_s` for 0–5 score, `_l` for label; years 30 and 50 mean 2030 and 2050. Pathway labels remain independent scenarios without probabilities. The supplied dictionary contains an inconsistent SSP example; this export does not resolve it by guessing.

`accounting_coefficients.csv` is an annual parametric evidence artifact, not a simulated outcome. At 744,600 IT MWh/year, `annual_electricity_cost_usd_per_unit_pue` and `annual_co2e_tonnes_per_unit_pue` must be multiplied by a supplied PUE. `annual_direct_water_m3_per_unit_wue_it` must be multiplied by supplied IT-based WUE L/kWh. Every county has the same water coefficient; basin stress is kept separately.

County-area fractions include all county geometry, including water. Shares are not renormalized; coverage gaps remain visible. Region overlap shares are geometric descriptions, not a supply mix or probability. Invalid raw geometries are repaired only in derived working copies, with repair counts in the coverage artifact.
