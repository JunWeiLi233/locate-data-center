"""Annual energy/carbon/water identities, with explicit scenario boundaries.

Electricity emissions are annual operating emissions, never lifecycle carbon.
No geographic values, hourly cooling curves or missing factors are invented.
"""

import math
import re
from numbers import Real
from pathlib import Path

import pandas as pd

from dc_locator.io import read_geoparquet, read_parquet, read_parquet_metadata, write_parquet
from dc_locator.model.cooling import CoolingDesign, PhysicalScenario, validate_alternative_ids
from dc_locator.model.screening import feature_evidence, json_text, prepare_inputs, screen
from dc_locator.provenance import DataMode
from dc_locator.schemas import FacilityConfig, SitePerformance


def calculate_annual(peak_it_power_mw, average_it_load_factor, hours_in_modeled_year, pue, grid_carbon_intensity_kg_per_mwh, wue_l_per_it_kwh, grid_water_l_per_kwh=None):
    """Return exact named-unit annual calculations; missing factors stay null.

    Multiplying a zero load by an unknown factor still returns UNKNOWN; a
    verified factor is needed to assert a modeled zero quantity.
    """
    values = dict(peak=peak_it_power_mw, load=average_it_load_factor, hours=hours_in_modeled_year, pue=pue, carbon=grid_carbon_intensity_kg_per_mwh, wue=wue_l_per_it_kwh, grid_water=grid_water_l_per_kwh)
    for name, value in values.items():
        if value is None:
            continue
        if isinstance(value, bool) or not isinstance(value, Real) or not math.isfinite(float(value)) or value < 0:
            raise ValueError(f"{name} must be finite nonnegative numeric input, not a boolean")
    if average_it_load_factor is not None and average_it_load_factor > 1:
        raise ValueError("load factor must be in [0,1]")
    if hours_in_modeled_year is not None and not 0 < hours_in_modeled_year <= 8784:
        raise ValueError("modeled year hours must be in (0,8784]")
    if pue is not None and pue < 1:
        raise ValueError("annual PUE must be at least 1")
    it = None if any(v is None for v in (peak_it_power_mw, average_it_load_factor, hours_in_modeled_year)) else peak_it_power_mw * average_it_load_factor * hours_in_modeled_year
    energy = None if it is None or pue is None else it * pue
    carbon = None if energy is None or grid_carbon_intensity_kg_per_mwh is None else energy * grid_carbon_intensity_kg_per_mwh
    site = None if it is None or wue_l_per_it_kwh is None else it * wue_l_per_it_kwh
    electricity_water = None if energy is None or grid_water_l_per_kwh is None else energy * grid_water_l_per_kwh
    result = dict(e_it_mwh=it, e_facility_mwh=energy, c_electricity_kg=carbon, c_electricity_tonnes=None if carbon is None else carbon / 1000, w_site_m3=site, w_site_liters=None if site is None else site * 1000, w_electricity_m3=electricity_water, w_electricity_liters=None if electricity_water is None else electricity_water * 1000)
    if any(value is not None and not math.isfinite(value) for value in result.values()):
        raise ValueError("Finite inputs overflowed a physical output")
    return result


def _validate_alternatives(facility, designs, scenarios):
    validate_alternative_ids(designs, scenarios)
    selected = set(facility.cooling_designs)
    if facility.cooling_design_id:
        selected.add(facility.cooling_design_id)
    if selected and selected != {d.design_id for d in designs}:
        raise ValueError("Provided cooling designs disagree with facility selection")


def simulate(geography, provenance, facility: FacilityConfig, designs: list[CoolingDesign], scenarios: list[PhysicalScenario]) -> pd.DataFrame:
    """Compute all alternatives for diagnostics; eligibility is a separate join.

    Annual PUE/WUE are constant scenario assumptions. Carbon uses only the
    declared source year with full coverage; future reuse requires an explicit
    historical-static assumption. No lifetime multiplication is performed.
    """
    _validate_alternatives(facility, designs, scenarios)
    rows, evidence = prepare_inputs(geography, provenance)
    results = []
    for row in rows:
        carbon_evidence = feature_evidence(row, evidence, "grid_carbon_intensity_kg_per_mwh")
        for design in sorted(designs, key=lambda d: d.design_id):
            for scenario in sorted(scenarios, key=lambda s: s.scenario_id):
                warnings = ["Annual operating electricity emissions only; no complete lifecycle carbon", "Constant annual PUE/WUE scenario; no geographic cooling differences or hourly weather simulation", "Annual PUE does not verify design-day peak demand"]
                carbon = carbon_evidence.get("value")
                if carbon is not None:
                    if carbon_evidence.get("unit") != "kg_CO2e_per_mwh":
                        raise ValueError("Carbon input must have explicit kg_CO2e_per_mwh units")
                    if carbon_evidence.get("data_year") != scenario.carbon_data_year:
                        raise ValueError("Carbon source year disagrees with external scenario year")
                    if str(facility.target_opening_year) != scenario.carbon_data_year:
                        if not scenario.historical_static:
                            raise ValueError("Historical carbon reused for another year requires historical_static scenario")
                        warnings.append(f"Opening {facility.target_opening_year} uses historical {scenario.carbon_data_year} carbon unchanged by explicit scenario; not a forecast")
                    coverage = carbon_evidence.get("coverage_frac")
                    if coverage is None or coverage < 1 - 1e-6:
                        carbon = None
                        warnings.append("Partial grid-carbon source coverage; emissions UNKNOWN, no extrapolation")
                if carbon_evidence.get("status") == "unknown":
                    carbon = None
                result = calculate_annual(facility.peak_it_power_mw, facility.average_it_load_factor, facility.hours_in_modeled_year, design.annual_pue, carbon, design.wue_l_per_it_kwh, scenario.grid_water_l_per_kwh)
                result["w_site_withdrawal_m3"] = None
                result["w_site_withdrawal_liters"] = None
                result["w_electricity_withdrawal_m3"] = None
                result["w_electricity_withdrawal_liters"] = None
                if design.water_basis == "withdrawal":
                    result["w_site_withdrawal_m3"] = result["w_site_m3"]
                    result["w_site_withdrawal_liters"] = result["w_site_liters"]
                    result["w_site_m3"] = result["w_site_liters"] = None
                    warnings.append("WUE is withdrawal-based; site consumption remains UNKNOWN")
                if scenario.grid_water_basis == "withdrawal":
                    result["w_electricity_withdrawal_m3"] = result["w_electricity_m3"]
                    result["w_electricity_withdrawal_liters"] = result["w_electricity_liters"]
                    result["w_electricity_m3"] = result["w_electricity_liters"] = None
                    warnings.append("Generation factor is withdrawal-based; generation consumption remains UNKNOWN")
                peak = facility.peak_it_power_mw * design.peak_pue if design.peak_pue_verified else None
                result.update(pue=design.annual_pue, wue_l_per_kwh=design.wue_l_per_it_kwh, grid_carbon_intensity_kg_per_mwh=carbon, peak_facility_demand_mw=peak)
                units = dict(e_it_mwh="mwh", e_facility_mwh="mwh", c_electricity_kg="kg_CO2e", c_electricity_tonnes="tonnes_CO2e", w_site_m3="m3_consumed", w_site_liters="liters_consumed", w_electricity_m3="m3_consumed", w_electricity_liters="liters_consumed", w_site_withdrawal_m3="m3_withdrawn", w_site_withdrawal_liters="liters_withdrawn", w_electricity_withdrawal_m3="m3_withdrawn", w_electricity_withdrawal_liters="liters_withdrawn", pue="ratio", wue_l_per_kwh=f"liters_{design.water_basis}_per_IT_kwh", grid_carbon_intensity_kg_per_mwh="kg_CO2e_per_mwh", peak_facility_demand_mw="mw")
                methods = dict(e_it_mwh="peak_it_power_mw * average_it_load_factor * hours_in_modeled_year", e_facility_mwh="e_it_mwh * annual_pue", c_electricity_kg="e_facility_mwh * grid_carbon_intensity_kg_per_mwh", c_electricity_tonnes="c_electricity_kg / 1000", w_site_m3="e_it_mwh * consumption_WUE_L_per_IT_kWh", w_site_liters="w_site_m3 * 1000", w_electricity_m3="e_facility_mwh * grid_water_consumption_L_per_kWh", w_electricity_liters="w_electricity_m3 * 1000", w_site_withdrawal_m3="e_it_mwh * withdrawal_WUE_L_per_IT_kWh", w_site_withdrawal_liters="w_site_withdrawal_m3 * 1000", w_electricity_withdrawal_m3="e_facility_mwh * grid_water_withdrawal_L_per_kWh", w_electricity_withdrawal_liters="w_electricity_withdrawal_m3 * 1000", peak_facility_demand_mw="peak_it_power_mw * verified_peak_pue", pue="configured constant annual scenario", wue_l_per_kwh="configured constant annual scenario", grid_carbon_intensity_kg_per_mwh="declared-year geographic source factor; historical-static when opening year differs")
                metadata = {}
                for metric, value in result.items():
                    status = "unknown" if value is None else ("scenario" if metric in {"pue", "wue_l_per_kwh"} else carbon_evidence.get("status") if metric == "grid_carbon_intensity_kg_per_mwh" else "calculated")
                    if metric == "grid_carbon_intensity_kg_per_mwh" and value is not None and str(facility.target_opening_year) != scenario.carbon_data_year:
                        status = "scenario"
                    metadata[metric] = dict(status=status, confidence="unknown" if value is None else "low", missing_reason="missing_input_or_incompatible_water_basis" if value is None else None, unit=units[metric], method=methods[metric], facility_basis=facility.basis, design_basis=design.basis, external_scenario_basis=scenario.basis)
                    if metric.startswith("c_electricity") or metric == "grid_carbon_intensity_kg_per_mwh":
                        metadata[metric]["source_evidence"] = carbon_evidence
                    if metric.startswith("w_electricity"):
                        metadata[metric]["generation_water_geography"] = scenario.grid_water_geography
                        metadata[metric]["local_water_stress_applied"] = False
                record = SitePerformance(grid_id=row["grid_id"], grid_definition_id=row["grid_definition_id"], facility_id=facility.facility_id, design_id=design.design_id, scenario_id=scenario.scenario_id, target_opening_year=facility.target_opening_year, operating_lifetime_years=facility.operating_lifetime_years, hours_in_modeled_year=facility.hours_in_modeled_year, metric_metadata_json=json_text(metadata), assumptions_json=json_text(dict(facility=facility.model_dump(mode="json"), design=design.model_dump(mode="json"), external_scenario=scenario.model_dump(mode="json"))), warnings_json=json_text(warnings), data_mode=row["data_mode"], **result)
                results.append(record.model_dump(mode="json"))
    return pd.DataFrame(results).sort_values(["grid_id", "design_id", "scenario_id"]).reset_index(drop=True)


def run_phase3(geography_path, provenance_path, facility, designs, scenarios, requirements, output_dir, *, mode=None):
    """Write a Phase 3 run without modifying source geography or exposing a CLI."""
    geography, provenance = read_geoparquet(Path(geography_path)), read_parquet(Path(provenance_path))
    grid_metadata, provenance_metadata = read_parquet_metadata(Path(geography_path)), read_parquet_metadata(Path(provenance_path))
    for metadata, expected_schema in ((grid_metadata, "GeographicFeatureDataset"), (provenance_metadata, "FeatureMetadata")):
        version_match = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)", metadata.get("schema_version", ""))
        version = tuple(int(v) for v in version_match.groups()) if version_match else None
        if metadata.get("schema") != expected_schema or version is None or version[0] != 1 or version < (1, 1, 0):
            raise ValueError(f"Unsupported input schema/version; expected {expected_schema} compatible with 1.1.0")
    for key in ("data_mode", "grid_definition_id"):
        if not grid_metadata.get(key) or grid_metadata[key] != provenance_metadata.get(key):
            raise ValueError(f"Geography/provenance file metadata mismatch: {key}")
    if geography.data_mode.nunique() != 1 or geography.grid_definition_id.nunique() != 1 or geography.data_mode.iloc[0] != grid_metadata["data_mode"] or geography.grid_definition_id.iloc[0] != grid_metadata["grid_definition_id"]:
        raise ValueError("Geographic table identity disagrees with file metadata")
    screening, eligibility, summary = screen(geography, provenance, facility, designs, scenarios, requirements, mode=mode)
    performance = simulate(geography, provenance, facility, designs, scenarios)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    grid_definition_id = geography.grid_definition_id.iloc[0]
    data_mode = DataMode(geography.data_mode.iloc[0])
    for filename, table, schema, version in (
        ("screening_results.parquet", screening, "ScreeningResult", "1.1.0"),
        ("site_performance.parquet", performance, "SitePerformance", "1.1.0"),
        ("screening_eligibility.parquet", eligibility, "ScreeningEligibility", "1.0.0"),
    ):
        write_parquet(table, output_dir / filename, schema_name=schema, schema_version=version, data_mode=data_mode, grid_definition_id=grid_definition_id)
    summary.update(data_mode=data_mode.value, grid_definition_id=grid_definition_id, geographic_cells=len(geography), n_performance_rows=len(performance), performance_scope="All alternatives for diagnostics, including ineligible ones; join screening_eligibility before decision analysis", configuration=dict(facility=facility.model_dump(mode="json"), designs=[d.model_dump(mode="json") for d in designs], scenarios=[s.model_dump(mode="json") for s in scenarios], requirements=[r.model_dump(mode="json") for r in requirements]))
    (output_dir / "screening_summary.json").write_text(json_text(summary) + "\n", encoding="utf-8")
    return screening, performance, eligibility, summary
