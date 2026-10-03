import importlib
import importlib.util
import json

import pandas as pd
import pytest

from dc_locator.schemas import FacilityConfig, SitePerformance, FeatureMetadata
from dc_locator.source_periods import AQUEDUCT_GCMS


def module():
    assert importlib.util.find_spec('dc_locator.model.scenarios') is not None
    return importlib.import_module('dc_locator.model.scenarios')


def fixture():
    f=FacilityConfig(facility_id='fixture',peak_it_power_mw=100,average_it_load_factor=.8,target_opening_year=2030,operating_lifetime_years=25,hours_in_modeled_year=8760)
    periods=[dict(pathway='bau',ssp_rcp='SSP3-RCP7.0',milestone_year=2030,window_start_year=2015,window_end_year=2045,supported=True,model='HYPFLOWSCI6; five-GCM median',gcms=AQUEDUCT_GCMS)]
    scenario=module().make_external_scenarios('historical_static_2023',periods)[0]
    evidence=dict(status='calculated',confidence='low',unit='kg_CO2e',method='energy*source',source_evidence=dict(source_id='fixture_carbon',coverage_frac=1,data_year='2023'))
    metadata=dict(c_electricity_kg=evidence,e_it_mwh=dict(status='calculated',confidence='low',unit='mwh',method='peak*load*hours'))
    p=pd.DataFrame([SitePerformance(grid_id='g',grid_definition_id='fixture',facility_id='fixture',design_id='dry',scenario_id=scenario.scenario_id,data_mode='synthetic',target_opening_year=2030,operating_lifetime_years=25,hours_in_modeled_year=8760,e_it_mwh=700800,c_electricity_kg=84096000,metric_metadata_json=json.dumps(metadata),assumptions_json=json.dumps(dict(external_scenario={'scenario_id':'historical_static_2023','historical_static':True,'carbon_data_year':'2023'}))).model_dump(mode='json')])
    return f,scenario,p


def test_explicit_lifetime_extension_is_exactly_25_annual_periods():
    f,s,p=fixture()
    policy=dict(enabled=True,method='repeat_opening_year_annual_scenario',basis='project_assumption',rationale='Synthetic constant lifetime test; not a forecast')
    result=module().build_temporal_scenarios(p,f,[s],extension_policy=policy)
    carbon=result.loc[result.variable=='c_electricity_kg']
    assert carbon.period_start_year.tolist()==list(range(2030,2055))
    assert len(carbon)==25 and carbon.value.sum()==84096000*25
    assert set(carbon.status)=={'calculated'}
    assert 'SSP3_RCP7_0' in s.scenario_id and '2015_2045' in s.scenario_id
    assert all(json.loads(a)['hours_policy']=='fixed_modeled_year_hours' for a in carbon.assumptions_json)
    assert set(carbon.hours_in_modeled_year)=={8760}


def test_later_years_stay_unknown_without_explicit_extension():
    f,s,p=fixture()
    result=module().build_temporal_scenarios(p,f,[s])
    carbon=result.loc[result.variable=='c_electricity_kg']
    assert carbon.iloc[0].value==84096000
    assert carbon.iloc[1:].value.isna().all()
    assert set(carbon.iloc[1:].status)=={'unknown'}
    assert set(carbon.iloc[1:].missing_reason)=={'missing_period_coverage_without_explicit_extension'}


def test_native_window_context_is_not_copied_to_annual_years_and_2040_unknown():
    f,s,p=fixture()
    evidence=pd.DataFrame([FeatureMetadata(grid_id='g',metric='aqueduct_bau_2030_water_stress_score',value=3.,value_text=None,unit='score_0_to_5',source_id='wri_aqueduct40_future',source_field='bau30_ws_x_s',source_version='4.0',data_year='2030;2015-2045',status='scenario',confidence='low',coverage_frac=1.,missing_reason=None,data_mode='synthetic',method='native').model_dump(mode='json')])
    evidence.attrs['grid_definition_id']='fixture'
    result=module().build_temporal_scenarios(p,f,[s],context_provenance=evidence)
    water=result.loc[result.variable=='future_water_stress_score']
    assert len(water)==1 and water.iloc[0].value==3
    assert (water.iloc[0].period_start_year,water.iloc[0].period_end_year)==(2015,2045)
    assert water.iloc[0].period_kind=='source_projection_window'
    assert water.iloc[0].ssp_rcp=='SSP3-RCP7.0'
    unsupported=module().make_external_scenarios('historical_static_2023',[dict(pathway='bau',ssp_rcp='SSP3-RCP7.0',milestone_year=2040,window_start_year=None,window_end_year=None,supported=False,model='HYPFLOWSCI6; five-GCM median',gcms=AQUEDUCT_GCMS)])[0]
    p['scenario_id']=unsupported.scenario_id
    missing=module().build_temporal_scenarios(p,f,[unsupported],context_provenance=evidence)
    row=missing.loc[missing.variable=='future_water_stress_score'].iloc[0]
    assert pd.isna(row.value) and row.status=='unknown'
    assert row.missing_reason=='unsupported_source_milestone_no_interpolation'


def test_missing_inputs_never_become_zero_and_metadata_is_preserved():
    f,s,p=fixture(); p['c_electricity_kg']=None
    metadata=json.loads(p.loc[0,'metric_metadata_json']); metadata['c_electricity_kg'].update(status='unknown',confidence='unknown',missing_reason='missing_carbon_source')
    p['metric_metadata_json']=json.dumps(metadata)
    result=module().build_temporal_scenarios(p,f,[s],extension_policy=dict(enabled=True,method='repeat_opening_year_annual_scenario',basis='project_assumption',rationale='Fixture'))
    carbon=result.loc[result.variable=='c_electricity_kg']
    assert carbon.value.isna().all() and set(carbon.status)=={'unknown'}
    assert 'fixture_carbon' in carbon.iloc[0].source_json


def test_invalid_duplicate_identity_and_quoted_extension_flags_raise():
    f,s,p=fixture()
    with pytest.raises(ValueError): module().build_temporal_scenarios(pd.concat([p,p]),f,[s])
    with pytest.raises(ValueError): module().build_temporal_scenarios(p,f,[s,s])
    with pytest.raises(ValueError): module().build_temporal_scenarios(p,f,[s],extension_policy=dict(enabled='true',method='repeat_opening_year_annual_scenario',basis='project_assumption',rationale='Fixture'))
    p['target_opening_year']=2031
    with pytest.raises(ValueError): module().build_temporal_scenarios(p,f,[s])


def test_temporal_results_repeat_deterministically():
    f,s,p=fixture()
    pd.testing.assert_frame_equal(module().build_temporal_scenarios(p,f,[s]),module().build_temporal_scenarios(p,f,[s]))


@pytest.mark.parametrize('change',[dict(window_start_year=2030),dict(ssp_rcp='SSP2-RCP4.5'),dict(gcms=['invented']),dict(supported=False)])
def test_native_temporal_identity_cannot_be_relabelled(change):
    _,s,_=fixture(); definition=s.model_dump(); definition.update(change)
    with pytest.raises(ValueError): module().ExternalScenario.model_validate(definition)


def test_rectangular_coverage_and_original_physical_binding_required():
    f,s,p=fixture()
    other=s.model_copy(update={'scenario_id':'other'})
    q=p.copy(); q['scenario_id']='other'; q['grid_id']='g2'
    with pytest.raises(ValueError,match='Cartesian'): module().build_temporal_scenarios(pd.concat([p,q]),f,[s,other])
    p['assumptions_json']=json.dumps(dict(external_scenario={'scenario_id':'other_physical'}))
    with pytest.raises(ValueError,match='physical scenario'): module().build_temporal_scenarios(p,f,[s])


@pytest.mark.parametrize('fault',['missing_identity','wrong_identity','wrong_grid','wrong_mode','malformed','duplicate','wrong_source','wrong_unit','wrong_status','zero_coverage'])
def test_context_provenance_requires_complete_identity_and_binding(fault):
    f,s,p=fixture()
    ctx=pd.DataFrame([FeatureMetadata(grid_id='g',metric='aqueduct_bau_2030_water_stress_score',value=3,unit='score_0_to_5',source_id='wri_aqueduct40_future',source_field='bau30_ws_x_s',status='scenario',confidence='low',coverage_frac=1,data_mode='synthetic').model_dump(mode='json')])
    ctx.attrs['grid_definition_id']='fixture'
    if fault=='missing_identity': ctx.attrs.clear()
    elif fault=='wrong_identity': ctx.attrs['grid_definition_id']='other'
    elif fault=='malformed': ctx=ctx[['grid_id','metric','status']]
    elif fault=='duplicate': ctx=pd.concat([ctx,ctx])
    else:
        field,value={'wrong_grid':('grid_id','other'),'wrong_mode':('data_mode','real'),'wrong_source':('source_id','other'),'wrong_unit':('unit','ratio'),'wrong_status':('status','observed'),'zero_coverage':('coverage_frac',0)}[fault]
        ctx[field]=value
    with pytest.raises(ValueError): module().build_temporal_scenarios(p,f,[s],context_provenance=ctx)
