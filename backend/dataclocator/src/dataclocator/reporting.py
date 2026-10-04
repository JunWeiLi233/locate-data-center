"""Generate a reviewable regional evidence report and processed-table dictionary."""

import json
from pathlib import Path

import pandas as pd


def generate_report(root: Path) -> None:
    """Write real-data comparisons without selecting PUE/WUE or claiming a winner."""
    directory = root / "outputs/task2"
    coverage = json.loads((directory / "coverage.json").read_text())
    manifest = json.loads((root / "data/source_manifest.json").read_text())
    candidates = pd.read_parquet(root / "data/processed/candidates.parquet")
    prices = pd.read_parquet(root / "data/processed/electricity_prices.parquet")
    # Example workload comes from the brief; coefficients keep cooling unspecified.
    comparison = candidates[["county_fips", "name", "state_abbr", "electricity_price_usd_per_mwh",
                             "grid_co2e_kg_per_mwh", "water_stress_score", "water_stress_label",
                             "grid_border_or_multiple_subregions"]].copy()
    comparison["annual_it_energy_mwh"] = 744600.0
    comparison["annual_electricity_cost_usd_per_unit_pue"] = 744600 * comparison.electricity_price_usd_per_mwh
    comparison["annual_co2e_tonnes_per_unit_pue"] = 744600 * comparison.grid_co2e_kg_per_mwh / 1000
    comparison["annual_direct_water_m3_per_unit_wue_it"] = 744600.0
    comparison.to_csv(directory / "accounting_coefficients.csv", index=False)
    lines = ["# Task 2: acquisition, location joins and accounting verification", "",
             "This report covers 45 preselected counties in 45 contiguous states. The cohort was frozen before outcomes, for geographic breadth, without screening known data center markets. It excludes CT, NJ and RI; it is not a national optimum search. Counties are screening regions, not construction sites.", "",
             "## Coverage", "",
             f"All {coverage['candidate_count']} counties have price, representative-point grid, representative-point water, suitable climate-station and hazard matches. {coverage['grid_ambiguous_count']} counties intersect multiple grid areas or EPA's multiple-service overlay. Every feasibility item remains unverified.", "",
             f"Monthly history contains {len(prices):,} industrial/commercial state observations from January 2020 through July 2026. The fixed annual baseline is sales-weighted 2025, with 12 months per state; EIA labels 2025 prices Preliminary. Earlier 2020–2024 observations are Final. Prices are nominal observation-year USD; these have not been inflation-adjusted into a future trajectory.", "",
             f"Climate assignments use complete monthly temperature and CDD records and actual great-circle distance, capped at 100 km; the most distant accepted station is {coverage['climate_max_station_distance_km']:.2f} km. Elevations and completeness flags are retained. No county/parcel elevation was available to verify elevation compatibility, so climate is screening context and does not set PUE/WUE.", "",
             "## Official sources and joins", "",
             "| Source | Frozen release | Join |", "|---|---|---|",
             "| Census Gazetteer + TIGER | 2025 | Exact 5-digit county FIPS; compatible polygon vintage |",
             "| EPA eGRID | 2023 revision 2 (June 2025) | Official primary and multiple-service polygons; representative-point assignment plus complete county overlap distributions |",
             "| EIA-861M | September 24, 2026 snapshot | State FIPS; industrial baseline plus commercial sensitivity series |",
             "| WRI Aqueduct | 4.0 Y2023M07D05 | County polygons intersect basin/admin/aquifer unions; representative-point value plus full area distribution |",
             "| NOAA NCEI normals | 1991–2020 v1.0.1 c20230404 | Nearest station with all 12 temperature/CDD months and matching inventory coordinates |",
             "| FEMA NRI | December 2025 v1.20.0 | Exact county FIPS; 3,232 national records verified against service count |", "",
             "FEMA's old NRI entry point redirects to RAPT. The county service was resolved from FEMA's linked public RAPT configuration and its item owner is `FEMA_NationalRiskIndex`; both metadata and field aliases are frozen. Frequency, exposure-related loss, and risk scores remain distinct. NRI uses 2021 TIGER geometry (with a CT exception); FIPS matches alone do not certify equivalence to 2025 boundaries.", "",
             "Area intersections use EPSG:5070, not angular-degree area. Invalid geometries are repaired only in derived working copies: 50 baseline WRI features and 111 future features in the CONUS bounding window. County overlap shares are not renormalized. Kent County, DE, has about 75.16% water-layer coverage of its entire county geometry; uncovered geometry includes coastal water. This is not a missing-land or withdrawal-volume estimate. St. Louis County, MN, has a small remaining coverage gap. Coverage fractions are exported.", "",
             "Aqueduct raw `-9999` becomes null; `9999` remains an explicit severe-scarcity sentinel. Arid/low-water-use categories remain visible and must not be treated as safe. Water scores are not volumes or calibrated probabilities. Future 2030/2050 basin distributions retain `bau`, `opt`, `pes` labels without scenario probabilities. WRI's dictionary has an inconsistent SSP example, so no remapping is inferred.", "",
             "## Real-data comparison", "",
             "The following are observed regional proxies, not future outcomes. EIA prices are preliminary 2025 nominal USD/MWh; carbon is 2023 eGRID average kg CO2e/MWh; water is a modeled 0–5 representative-point stress score. A `yes` ambiguity flag requires supplier clarification. No preference score or site recommendation is produced.", "",
             "| FIPS | County | State | Price USD/MWh | Grid kg CO2e/MWh | Water score | Grid ambiguity |", "|---|---|---|---:|---:|---:|---|"]
    for row in comparison.itertuples():
        lines.append(f"| {row.county_fips} | {row.name} | {row.state_abbr} | {row.electricity_price_usd_per_mwh:.2f} | {row.grid_co2e_kg_per_mwh:.2f} | {row.water_stress_score:.2f} | {'yes' if row.grid_border_or_multiple_subregions else 'no'} |")
    lines += ["", "## Accounting boundaries and checks", "",
              "For 100 MW IT × 0.85 utilization × 8,760 hours, annual IT energy is 744,600 MWh. These workload values are illustrative brief assumptions. No PUE, WUE, cost escalation, decarbonization, or discount-rate default has been chosen for real counties.", "",
              "- Facility MWh = IT MWh × PUE, enforcing PUE ≥ 1.",
              "- Electricity USD = facility MWh × USD/MWh; cents/kWh × 10 gives USD/MWh.",
              "- Operational tonnes CO2e = facility MWh × kg/MWh ÷ 1,000; lb/MWh × 0.45359237 gives kg/MWh.",
              "- Direct consumption m³ = IT MWh × WUE L/kWh IT. If WUE is facility-based, facility MWh is used instead. The 1,000 unit factors cancel.",
              "- Optional indirect generation consumption is facility MWh × sourced m³/MWh; retained separately. No factor has been supplied.",
              "- Monetary totals use supplied annual trajectories and end-of-operating-year payments, discounted to base year with exponent year − base year + 1. Real prices require real rates; nominal prices require nominal rates. Physical totals are not discounted.", "",
              "`accounting_coefficients.csv` provides an honest parametric comparison: multiply annual cost/carbon coefficients by a supplied PUE, and water coefficients by a supplied IT-based WUE. Equal WUE produces identical direct water use; stress stays separate. This is an annual historical-proxy calculation, not a 25-year prediction.", "",
              "The arithmetic-only test fixture uses PUE 1.2, WUE 0.2 L/kWh IT, price $50/MWh and grid carbon 400 kg/MWh. It yields 893,520 facility MWh, $44,676,000 electricity cost, 357,408 tonnes CO2e and 148,920 m³ direct consumption. These fixture numbers are not sourced county engineering assumptions. `accounting_verification.json` preserves inputs and independent expected values.", "",
              "Tests verify conversions, workload doubling, monotonicity, IT/facility WUE definitions, missing versus zero, invalid ranges/nonfinite values, delayed opening and end-year discounting, explicit varying trajectories, and 20/25/30-year summation fixtures. Geographic tests cover string FIPS, duplicate detection, border ambiguity, equal-area shares, station distances, source missing codes, full-year prices, and sales weighting. The JUnit test artifact records the executed test count and result.", "",
              "## Remaining inputs", "",
              "Engineering PUE/WUE values or validated cooling response curves; cooling consumption definition; real/nominal price and carbon trajectories; opening year and discount convention; utility commitment, deliverable MW and energization date; water allocation/permit; parcel/zoning and protected-area evidence; redundant fiber; elevation suitability; power-generation consumptive-water factors; capex/water tariffs; material quantities/emission factors; verified heat recipients and coincident demand; workforce/community evidence.", "",
              "Reliability (EIA-861), Cambium and optional land/climate/fiber/queue datasets are not yet integrated. Monte Carlo, Pareto optimization and HTTP endpoints are later tasks. This task verifies deterministic accounting and regional joins. No construction, IT manufacturing, backup fuel or heat-displacement carbon is included, and cost is electricity-only.", "",
              "## Provenance and access", "",
              "All source files have SHA-256, bytes, retrieval UTC, official discovery/file URLs, release, dictionary and attribution in [source_manifest.json](../../data/source_manifest.json). Raw files are immutable; preprocessing verifies hashes before reading. Public links that change require a new reviewed manifest rather than replacing pinned files. WRI permits CC BY 4.0 reuse with attribution; its FAQ requests registration for adaptation/sharing. The public direct download was used; no personal information was submitted. Cite Kuzma et al. (2023), DOI 10.46830/writn.23.00061.", ""]
    for source in manifest["sources"]:
        if source["source_id"] in {"census_gazetteer", "egrid_data", "eia_monthly", "aqueduct", "noaa_monthly", "fema_counties"}:
            lines.append(f"- [{source['publisher']}: {source['source_id']}]({source['source_page']})")
    (directory / "report.md").write_text("\n".join(lines) + "\n")

    # A complete machine dictionary records every physical column and dtype.
    dictionary = {}
    for path in sorted((root / "data/processed").glob("*.parquet")):
        if path.stem == "candidate_polygons":
            dictionary[path.stem] = {"county_fips": "string; 5-digit Census FIPS", "geometry": "GeoParquet geometry; EPSG:4326"}
            continue
        frame = pd.read_parquet(path)
        dictionary[path.stem] = {column: str(dtype) for column, dtype in frame.dtypes.items()}
    (directory / "processed_dictionary.json").write_text(json.dumps(dictionary, indent=2) + "\n")
