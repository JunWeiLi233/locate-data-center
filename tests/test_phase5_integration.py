"""Matched preferences, native identity and baseline preservation contracts."""
import copy
import json
from pathlib import Path

import pandas as pd
import pytest

from dc_locator.model.enhanced import validate_matched_preferences, verify_baseline_repeat, rebind_external_scenario, compare_rankings, combine_temporal_context
from dc_locator.model.metrics import load_profile, ScoringProfile
from dc_locator.model.scenarios import make_external_scenarios, build_climate_source_context
from dc_locator.geography.sources.aqueduct_future import future_period
from dc_locator.schemas import FeatureMetadata, FutureScenarioValue, LifecycleResult
from dc_locator.config import load_sources_config
from dc_locator.validation import nullable_record


def test_all_predeclared_profiles_keep_accepted_preferences():
    baseline=load_profile('configs/scoring_profile.yaml')
    declaration=json.loads(Path('docs/phase_records/phase5_profiles_predeclared.json').read_text(encoding='utf-8'))
    for entry in declaration['profiles']:
        assert validate_matched_preferences(baseline,load_profile(entry['path']))
        assert entry['declared_at_utc'] and entry['status']=='PREDECLARED_BEFORE_FIRST_RANKING'
    altered=baseline.model_dump();altered['metrics'][0]['reference_high']*=2
    with pytest.raises(ValueError):validate_matched_preferences(baseline,ScoringProfile.model_validate(altered))


def baseline_files(tmp_path):
    folder=tmp_path/'repeat';root=tmp_path/'project'
    files=[('physical',root/'runs/phase3',['screening_results.parquet','site_performance.parquet','screening_eligibility.parquet','screening_summary.json']),
           ('decision',root/'runs/phase4/strict',['normalized_metrics.parquet','pareto_results.parquet','ranked_cells.parquet','region_membership.parquet','candidate_regions.geojson','ranking.csv','ahp_template.json','profile_snapshot.json'])]
    for family,accepted,names in files:
        accepted.mkdir(parents=True);(folder/family).mkdir(parents=True)
        for name in names:(accepted/name).write_text(name);(folder/family/name).write_text(name)
    return folder,root


def test_strict_root_physical_artifacts_are_all_required_and_compared(tmp_path):
    folder,root=baseline_files(tmp_path)
    assert len(verify_baseline_repeat(folder,'STRICT',root))==12
    (root/'runs/phase3/site_performance.parquet').write_text('changed')
    with pytest.raises(ValueError,match='changed'):verify_baseline_repeat(folder,'STRICT',root)
    (root/'runs/phase3/site_performance.parquet').unlink()
    with pytest.raises(ValueError,match='missing'):verify_baseline_repeat(folder,'STRICT',root)


def test_rebinding_preserves_original_physics_and_adds_explicit_water_context():
    scenario=make_external_scenarios('historical_static_2023',[future_period('bau',2050)])[0]
    original=pd.DataFrame([dict(grid_id='g',design_id='dry',scenario_id='historical_static_2023',c_electricity_kg=123,assumptions_json=json.dumps(dict(external_scenario={'scenario_id':'historical_static_2023'})))])
    rebound=rebind_external_scenario(original,scenario,physical_metadata=True)
    assert rebound.iloc[0].c_electricity_kg==123 and rebound.iloc[0].scenario_id==scenario.scenario_id
    assumptions=json.loads(rebound.iloc[0].assumptions_json)
    assert assumptions['external_scenario']['scenario_id']=='historical_static_2023'
    assert assumptions['external_context']['ssp_rcp']=='SSP3-RCP7.0'
    assert assumptions['external_context']['window_start_year']==2035
    assert original.iloc[0].scenario_id=='historical_static_2023'


def climate_fixture():
    method=dict(model='ACCESS-CM2',ensemble='r1i1p1f1',ssp='ssp245',period_start_year=2030,period_end_year=2030,variable='tas',temporal_coverage_frac=1.)
    p=pd.DataFrame([FeatureMetadata(grid_id='g',metric='nex_access_cm2_ssp245_2030_tas_mean_c',value=12,unit='degC',source_id='nasa_nex_gddp_cmip6',source_field='tas',data_year='2030',status='scenario',confidence='low',coverage_frac=1,data_mode='synthetic',method=json.dumps(method)).model_dump(mode='json')])
    p.attrs['grid_definition_id']='fixture';return p


def test_nasa_context_keeps_own_ssp_and_never_binds_to_water_or_design():
    result=build_climate_source_context(climate_fixture(),grid_ids=['g'],grid_definition_id='fixture',data_mode='synthetic',facility_id='fixture')
    row=result.iloc[0]
    assert row.ssp_rcp=='ssp245' and row.design_id=='source_context'
    assert 'ACCESS_CM2_r1i1p1f1_ssp245' in row.scenario_id
    assert 'aqueduct' not in row.scenario_id
    assert json.loads(row.assumptions_json)['paired_aqueduct_scenario'] is False
    FutureScenarioValue.model_validate(nullable_record(row.to_dict()))


def test_known_temporal_file_rows_require_source_assumptions_units_coverage():
    row=build_climate_source_context(climate_fixture(),grid_ids=['g'],grid_definition_id='fixture',data_mode='synthetic',facility_id='fixture').iloc[0].to_dict()
    for key,value in [('source_json','{}'),('assumptions_json','{}'),('source_id',None),('unit',None),('coverage_frac',None)]:
        bad=dict(row);bad[key]=value
        with pytest.raises(ValueError):FutureScenarioValue.model_validate(bad)


def test_every_implemented_enhanced_source_id_is_registered():
    from dc_locator.geography.sources.expanded import METRICS
    from dc_locator.geography.sources.aqueduct_future import FUTURE_SOURCE_ID
    registry=load_sources_config()
    assert set(METRICS)|{FUTURE_SOURCE_ID} <= {s.source_id for s in registry.sources}


def test_native_context_null_milestone_survives_temporal_union():
    climate=build_climate_source_context(climate_fixture(),grid_ids=['g'],grid_definition_id='fixture',data_mode='synthetic',facility_id='fixture')
    annual=climate.copy();annual['design_id']='dry';annual['milestone_year']=2030;annual['hours_in_modeled_year']=8760
    annual['period_kind']='annual_operating'
    result=combine_temporal_context(annual,climate)
    native=result.loc[result.design_id.eq('source_context')].iloc[0]
    assert pd.isna(native.milestone_year) and native.period_start_year==2030
    assert str(result.milestone_year.dtype)=='Int64'
