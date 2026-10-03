import pandas as pd
import pytest
from pydantic import ValidationError

from dc_locator.model.screening import Requirement, screen
from test_model_physics import model_inputs
from dc_locator.schemas import ScreeningResult


def requirement(**changes):
    fields=dict(requirement_id="parcel",metric="confirmed_developable_parcel_area_km2",operator="ge",threshold=1,unit="km2",is_critical=True,basis="project_assumption",rationale="Require a confirmed parcel; total classified pixels are insufficient",coverage_policy="full")
    fields.update(changes)
    return Requirement(**fields)


def test_strict_and_exploratory_keep_unknown_and_hard_fail():
    g,p,f,d,s=model_inputs()
    strict,eligible,summary=screen(g,p,f,[d],[s],[requirement()],mode="STRICT")
    assert strict.iloc[0].outcome=="UNKNOWN"
    assert not eligible.iloc[0].eligible
    exploratory,eligible,_=screen(g,p,f,[d],[s],[requirement()],mode="EXPLORATORY")
    assert exploratory.iloc[0].outcome=="UNKNOWN"
    assert eligible.iloc[0].eligible and eligible.iloc[0].conditional
    fail=requirement(requirement_id="carbon_limit",metric="grid_carbon_intensity_kg_per_mwh",operator="le",threshold=50,unit="kg_CO2e_per_mwh")
    _,eligible,_=screen(g,p,f,[d],[s],[fail,requirement()],mode="EXPLORATORY")
    assert eligible.iloc[0].hard_fail and not eligible.iloc[0].eligible


def test_partial_coverage_cannot_pass_and_proxies_do_not_verify_capacity():
    g,p,f,d,s=model_inputs()
    g["grid_carbon_intensity_kg_per_mwh_coverage_frac"]=.5
    p.loc[0,"coverage_frac"]=.5
    r=requirement(metric="grid_carbon_intensity_kg_per_mwh",operator="le",threshold=200,unit="kg_CO2e_per_mwh")
    result,_,_=screen(g,p,f,[d],[s],[r],mode="EXPLORATORY")
    assert result.iloc[0].outcome=="UNKNOWN"
    g["transmission_distance_km"]=0
    capacity=requirement(requirement_id="capacity",metric="confirmed_utility_capacity_mw",threshold_from="peak_facility_demand_mw",threshold=None,unit="mw")
    result,_,_=screen(g,p,f,[d],[s],[capacity],mode="EXPLORATORY")
    assert result.iloc[0].outcome=="UNKNOWN"
    assert "peak" in result.iloc[0].reason.lower()


def test_proxy_capacity_cannot_verify_peak_connection_demand():
    g,p,f,d,s=model_inputs()
    d=d.model_copy(update={"peak_pue":1.4,"peak_pue_verified":True,"peak_pue_evidence":"Synthetic engineer design-day certification"})
    metric="confirmed_utility_capacity_mw"
    g[metric]=1000
    g[metric+"_status"]="proxy"
    p=pd.concat([p,pd.DataFrame([dict(grid_id="g1",metric=metric,value=1000,status="proxy",confidence="low",coverage_frac=1,unit="mw",source_id="fixture",data_mode="synthetic")])],ignore_index=True)
    r=requirement(requirement_id="capacity",metric=metric,threshold=None,threshold_from="peak_facility_demand_mw",unit="mw",coverage_policy="not_applicable")
    result,eligible,_=screen(g,p,f,[d],[s],[r],mode="EXPLORATORY")
    assert result.iloc[0].threshold==140
    assert result.iloc[0].outcome=="UNKNOWN"
    assert result.iloc[0].missing_reason=="unsupported_evidence_status"
    assert eligible.iloc[0].conditional
    g[metric+"_status"]="observed"
    p.loc[p.metric==metric,"status"]="observed"
    g[metric]=130
    p.loc[p.metric==metric,"value"]=130
    result,eligible,_=screen(g,p,f,[d],[s],[r],mode="EXPLORATORY")
    assert result.iloc[0].outcome=="FAIL" and eligible.iloc[0].hard_fail


@pytest.mark.parametrize("duplicate", ["design","scenario","requirement"])
def test_public_screen_api_rejects_duplicate_alternatives(duplicate):
    g,p,f,d,s=model_inputs()
    with pytest.raises(ValueError,match="Duplicate"):
        screen(g,p,f,[d,d] if duplicate=="design" else [d],[s,s] if duplicate=="scenario" else [s],[requirement(),requirement()] if duplicate=="requirement" else [requirement()])


def test_informational_threshold_and_invalid_outcome_contract_fail():
    with pytest.raises(ValidationError,match="threshold"):
        requirement(operator="informational",is_critical=False)
    with pytest.raises(ValidationError,match="UNKNOWN"):
        ScreeningResult(grid_id="g",design_id="d",scenario_id="s",requirement="r",outcome="UNKNOWN",mode="STRICT")
    with pytest.raises(ValidationError,match="PASS/FAIL"):
        ScreeningResult(grid_id="g",design_id="d",scenario_id="s",requirement="r",outcome="PASS",mode="STRICT")


def test_facility_configured_mode_is_default_and_explicit_override_is_recorded():
    g,p,f,d,s=model_inputs()
    f=f.model_copy(update={"screening_mode":"EXPLORATORY"})
    _,eligible,summary=screen(g,p,f,[d],[s],[requirement()])
    assert eligible.iloc[0].eligible and eligible.iloc[0].conditional
    assert summary["mode"]=="EXPLORATORY" and not summary["mode_override_requested"]
    _,eligible,summary=screen(g,p,f,[d],[s],[requirement()],mode="STRICT")
    assert not eligible.iloc[0].eligible and summary["mode_override_requested"]


@pytest.mark.parametrize("mismatch", ["definition", "schema", "version"])
def test_run_rejects_incompatible_metadata(tmp_path,mismatch):
    import geopandas as gpd
    from shapely.geometry import box
    from dc_locator.io import write_geoparquet,write_parquet
    from dc_locator.model.physics import run_phase3
    from dc_locator.provenance import DataMode
    g,p,f,d,s=model_inputs()
    geo=gpd.GeoDataFrame(g,geometry=[box(0,0,1,1)],crs=5070)
    gp=tmp_path/"grid.parquet"
    pp=tmp_path/"provenance.parquet"
    write_geoparquet(geo,gp,schema_name="GeographicFeatureDataset",schema_version="1.1.0",data_mode=DataMode.SYNTHETIC,grid_definition_id="fixture")
    write_parquet(p,pp,schema_name="WrongSchema" if mismatch=="schema" else "FeatureMetadata",schema_version="1.0.0" if mismatch=="version" else "1.1.0",data_mode=DataMode.SYNTHETIC,grid_definition_id="other_definition" if mismatch=="definition" else "fixture")
    with pytest.raises(ValueError,match="metadata mismatch|schema/version"):
        run_phase3(gp,pp,f,[d],[s],[requirement()],tmp_path/"run")
