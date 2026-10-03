import json

import pandas as pd
import pytest

from dc_locator.model.cooling import CoolingDesign, PhysicalScenario
from dc_locator.model.physics import calculate_annual, simulate
from dc_locator.schemas import FacilityConfig


def test_mandatory_hand_calculation():
    result = calculate_annual(100, .8, 8760, 1.2, 100, .3)
    assert result["e_it_mwh"] == 700800
    assert result["e_facility_mwh"] == 840960
    assert result["c_electricity_tonnes"] == 84096
    assert result["w_site_liters"] == 210240000
    assert result["c_electricity_kg"] == 84096000
    assert result["w_site_m3"] == 210240


@pytest.mark.parametrize("index,value", [(0,-1),(1,-.1),(1,1.1),(2,0),(3,.9),(4,-1),(5,-1),(0,float('inf')),(3,float('nan'))])
def test_invalid_inputs_fail(index,value):
    values=[100,.8,8760,1.2,100,.3]
    values[index]=value
    with pytest.raises(ValueError):
        calculate_annual(*values)


@pytest.mark.parametrize("index", range(7))
def test_physical_calculator_rejects_boolean_coefficients(index):
    values=[100,.8,8760,1.2,100,.3,2]
    values[index]=True
    with pytest.raises(ValueError,match="numeric"):
        calculate_annual(*values)


@pytest.mark.parametrize("field", ["annual_pue","wue_l_per_it_kwh","peak_pue"])
def test_cooling_design_rejects_boolean_numeric_fields(field):
    values=dict(design_id="typed",heat_transport="fixture loop",heat_rejection="fixture rejection",
        annual_pue=1.2,wue_l_per_it_kwh=.3,water_basis="consumption",peak_pue=None,
        peak_pue_verified=False,basis="project_assumption",rationale="Typed software fixture")
    values[field]=True
    with pytest.raises(ValueError,match="numeric"):
        CoolingDesign.model_validate(values)


def test_physical_scenario_rejects_boolean_grid_water_but_accepts_numeric_zero():
    values=dict(scenario_id="typed",carbon_data_year="2023",historical_static=True,
        grid_water_l_per_kwh=True,grid_water_geography="fixture boundary",
        basis="project_assumption",rationale="Typed software fixture")
    with pytest.raises(ValueError,match="numeric"):
        PhysicalScenario.model_validate(values)
    values["grid_water_l_per_kwh"]=0
    assert PhysicalScenario.model_validate(values).grid_water_l_per_kwh==0


def test_missing_factors_are_unknown_even_at_zero_load():
    result=calculate_annual(100,0,8760,None,None,None)
    assert result["e_it_mwh"]==0
    assert result["e_facility_mwh"] is None
    assert result["c_electricity_kg"] is None
    assert result["w_site_m3"] is None
    known=calculate_annual(100,0,8760,1.2,100,.3)
    assert known["e_facility_mwh"]==known["c_electricity_kg"]==known["w_site_m3"]==0


def test_monotonicity_and_electricity_water_conversion():
    baseline=calculate_annual(100,.8,8760,1.2,100,.3,2)
    assert baseline["w_electricity_m3"]==1681920
    assert calculate_annual(100,.8,8760,1.3,100,.3)["e_facility_mwh"]>baseline["e_facility_mwh"]
    assert calculate_annual(100,.8,8760,1.2,110,.3)["c_electricity_kg"]>baseline["c_electricity_kg"]
    assert calculate_annual(100,.8,8760,1.2,100,.4)["w_site_m3"]>baseline["w_site_m3"]


def model_inputs():
    facility=FacilityConfig(facility_id="fixture",peak_it_power_mw=100,average_it_load_factor=.8,target_opening_year=2030,operating_lifetime_years=25,hours_in_modeled_year=8760,minimum_land_area_km2=1)
    design=CoolingDesign(design_id="complete",heat_transport="cold plate water loop",heat_rejection="dry cooler with adiabatic assist",annual_pue=1.2,wue_l_per_it_kwh=.3,water_basis="consumption",basis="project_assumption",rationale="Synthetic hand-calculation fixture only")
    scenario=PhysicalScenario(scenario_id="historical_static_2023",carbon_data_year="2023",historical_static=True,basis="project_assumption",rationale="Static historical factor; not a forecast")
    geography=pd.DataFrame([dict(grid_id="g1",grid_definition_id="fixture",data_mode="synthetic",grid_carbon_intensity_kg_per_mwh=100,grid_carbon_intensity_kg_per_mwh_status="observed",grid_carbon_intensity_kg_per_mwh_confidence="high",grid_carbon_intensity_kg_per_mwh_coverage_frac=1)])
    provenance=pd.DataFrame([dict(grid_id="g1",metric="grid_carbon_intensity_kg_per_mwh",value=100,status="observed",confidence="high",coverage_frac=1.0,unit="kg_CO2e_per_mwh",source_id="fixture",data_year="2023",data_mode="synthetic")])
    return geography,provenance,facility,design,scenario


def test_design_records_and_water_basis_are_separate():
    geography,provenance,facility,design,scenario=model_inputs()
    withdrawal=design.model_copy(update={"design_id":"withdrawal","water_basis":"withdrawal"})
    result=simulate(geography,provenance,facility,[design,withdrawal],[scenario])
    assert len(result)==2
    assert result["design_id"].tolist()==["complete","withdrawal"]
    first,second=result.iloc[0],result.iloc[1]
    assert first.w_site_m3==210240 and pd.isna(first.w_site_withdrawal_m3)
    assert pd.isna(second.w_site_m3) and second.w_site_withdrawal_m3==210240
    assert pd.isna(first.peak_facility_demand_mw)
    metadata=json.loads(first.metric_metadata_json)
    assert metadata["pue"]["status"]=="scenario"
    assert metadata["grid_carbon_intensity_kg_per_mwh"]["status"]=="scenario"
    assert metadata["grid_carbon_intensity_kg_per_mwh"]["source_evidence"]["status"]=="observed"
    assert metadata["w_electricity_m3"]["status"]=="unknown"


def test_historical_factor_year_and_partial_coverage_are_not_silent():
    geography,provenance,facility,design,scenario=model_inputs()
    wrong=scenario.model_copy(update={"carbon_data_year":"2022"})
    with pytest.raises(ValueError,match="year"):
        simulate(geography,provenance,facility,[design],[wrong])
    provenance.loc[0,"coverage_frac"]=.5
    geography["grid_carbon_intensity_kg_per_mwh_coverage_frac"]=.5
    result=simulate(geography,provenance,facility,[design],[scenario])
    assert pd.isna(result.iloc[0].c_electricity_kg)
    assert json.loads(result.iloc[0].metric_metadata_json)["c_electricity_kg"]["status"]=="unknown"


def test_finite_product_overflow_is_rejected():
    with pytest.raises(ValueError,match="overflow"):
        calculate_annual(1e308,.8,8760,1.2,100,.3)


def test_generation_withdrawal_preserves_liters_and_m3_separately():
    g,p,f,d,s=model_inputs()
    s=s.model_copy(update={"grid_water_l_per_kwh":2,"grid_water_basis":"withdrawal","grid_water_geography":"Synthetic generation-boundary factor"})
    result=simulate(g,p,f,[d],[s]).iloc[0]
    assert result.w_electricity_withdrawal_m3==1681920
    assert result.w_electricity_withdrawal_liters==1681920000
    assert pd.isna(result.w_electricity_m3) and pd.isna(result.w_electricity_liters)
    assert json.loads(result.metric_metadata_json)["w_electricity_withdrawal_liters"]["unit"]=="liters_withdrawn"
