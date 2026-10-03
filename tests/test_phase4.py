"""Hand-calculated decision fixtures; synthetic inputs never leave pytest tmp_path."""
import copy
import json

import geopandas as gpd
import numpy as np
import pandas as pd
import pytest
from shapely.geometry import box

from dc_locator.model.metrics import load_profile,ScoringProfile,clean
from dc_locator.model.normalization import normalize_values
from dc_locator.model.mcda import equal_weights, user_weights, hierarchical_weights, score_alternatives
from dc_locator.model.pareto import pareto_frontier
from dc_locator.model.regions import cluster_regions


def test_fixed_normalization_direction_clipping_constant_missing():
    values, status = normalize_values([0,5,10,15,np.nan], 0,10,'minimize')
    assert values[:4] == pytest.approx([100,50,0,0])
    assert np.isnan(values[4]) and status.tolist() == ['within_reference','within_reference','within_reference','clipped_high','missing']
    values, _ = normalize_values([3,3], 0,10,'maximize')
    assert values == pytest.approx([30,30])


def test_profile_and_weights():
    p = load_profile('configs/scoring_profile.yaml')
    assert list(equal_weights(p).values()) == pytest.approx([.25,.125,.125,.25,.25])
    ids = p.metric_ids
    assert sum(user_weights(dict.fromkeys(ids,2), ids).values()) == pytest.approx(1)
    for bad in [dict.fromkeys(ids,0), {ids[0]:1}, dict.fromkeys(ids,float('inf')), dict.fromkeys(ids,-1),dict.fromkeys(ids,True),dict.fromkeys(ids,'1')]:
        with pytest.raises(ValueError): user_weights(bad, ids)


def test_pareto_directions_tolerance_and_scenario_separation():
    frame = pd.DataFrame({'grid_id':['a','b','c','d'], 'design_id':['x']*4, 'scenario_id':['s','s','s','other'], 'm':[1,2,1+1e-10,0], 'n':[2,1,2,9], 'rankable':[True]*4})
    result = pareto_frontier(frame, ['m','n'], ['minimize','maximize'], [1e-9,1e-9])
    assert result.is_pareto_optimal.tolist() == [True,False,True,True]
    frame.loc[0,'rankable'] = False
    assert pd.isna(pareto_frontier(frame, ['m','n'], ['minimize','maximize'], [1e-9]*2).is_pareto_optimal.iloc[0])


def test_hard_fail_missing_and_strict_unknown_never_rank():
    frame = pd.DataFrame({'grid_id':['a','b','c','d'], 'design_id':['x']*4, 'scenario_id':['s']*4, 'eligible':[True,False,True,False], 'conditional':[True,False,True,False], 'hard_fail':[False,True,False,False], 'critical_unknown':[True,False,True,True], 'mode':['EXPLORATORY','STRICT','EXPLORATORY','STRICT'], 'm':[100,100,np.nan,100], 'n':[50]*4})
    scored = score_alternatives(frame, ['m','n'], {'m':.5,'n':.5})
    assert scored.mcda_score.iloc[0] == 75
    assert scored.mcda_score.iloc[1:].isna().all()
    assert scored.rank_status.tolist() == ['CONDITIONAL','INELIGIBLE','UNRANKED','INELIGIBLE']
    assert json.loads(scored.weights_used_json.iloc[2]) == {'m':.5,'n':.5}
    assert scored.contribution_by_metric_json.iloc[2] == '{}'


def region_fixture():
    grid = gpd.GeoDataFrame({'grid_id':['a','b','c'], 'grid_definition_id':['fixture']*3, 'row':[0,0,0], 'col':[0,1,4], 'study_area_intersection_km2':[1.]*3, 'suitable_land_area_km2':[.8]*3}, geometry=[box(0,0,1000,1000),box(1000,0,2000,1000),box(4000,0,5000,1000)], crs=5070)
    ranked = pd.DataFrame({'grid_id':['a','b','c','a'], 'design_id':['x','x','x','y'], 'scenario_id':['s']*4, 'mcda_score':[90.,80.,70.,95.], 'rankable':[True]*4, 'conditional':[True]*4, 'hard_fail':[False]*4, 'critical_unknown':[True]*4, 'eligible':[True]*4, 'mode':['EXPLORATORY']*4, 'is_pareto_optimal':[True]*4, 'm':[1,2,3,4]})
    return grid, ranked


def test_regions_adjacent_disconnected_designs_and_representative():
    grid, ranked = region_fixture()
    policy = dict(top_fraction=1.,adjacency='rook',minimum_cells=1,require_pareto=False)
    regions, membership = cluster_regions(grid, ranked, policy, ['m'], 'profile','fingerprint')
    assert sorted(regions.n_cells) == [1,1,2]
    two = regions.loc[regions.n_cells == 2].iloc[0]
    assert two.representative_grid_id == 'a'
    assert json.loads(two.representative_json)['m'] == 1
    assert set(membership.design_id) == {'x','y'}
    other, members = cluster_regions(grid, ranked.sample(frac=1,random_state=2), policy, ['m'], 'profile','fingerprint')
    assert regions.drop(columns='geometry').to_json() == other.drop(columns='geometry').to_json()
    assert membership.equals(members)


def test_empty_regions_and_ties_are_deterministic():
    grid, ranked = region_fixture()
    ranked['mcda_score'] = 80.
    policy = dict(top_fraction=.5,adjacency='rook',minimum_cells=1,require_pareto=False)
    regions, members = cluster_regions(grid, ranked, policy, ['m'], 'p','h')
    assert set(members.loc[members.design_id == 'x','grid_id']) == {'a','b'}
    ranked['rankable'] = False
    regions, members = cluster_regions(grid, ranked, policy, ['m'], 'p','h')
    assert len(regions) == len(members) == 0


def decision_fixture():
    from datetime import datetime,timezone
    from dc_locator.model.physics import simulate
    from dc_locator.model.screening import screen,Requirement
    from dc_locator.schemas import FeatureMetadata
    from test_model_physics import model_inputs
    g,p,f,d,s = model_inputs()
    profile = load_profile('configs/scoring_profile.yaml')
    g['grid_carbon_intensity_kg_per_mwh_status'] = 'proxy'
    p.loc[0,'status'] = 'proxy'
    p.loc[0,'source_id'] = 'epa_egrid'
    p.loc[0,'source_field'] = 'SRC2ERTA'
    g['row'] = 3;g['col'] = 2
    g['study_area_intersection_km2'] = 1.;g['suitable_land_area_km2'] = .8
    g = gpd.GeoDataFrame(g,geometry=[box(2000,-4000,3000,-3000)],crs=5070)
    source_rows = p.to_dict('records')
    for metric,value in [(profile.metrics[2],2.),(profile.metrics[3],10.),(profile.metrics[4],.8)]:
        g[metric.column] = value;g[metric.column+'_status'] = metric.allowed_statuses[0]
        g[metric.column+'_confidence'] = 'high';g[metric.column+'_coverage_frac'] = None if metric.minimum_coverage_frac is None else 1.
        source_rows.append(dict(grid_id='g1',metric=metric.column,value=value,status=metric.allowed_statuses[0],confidence='high',coverage_frac=None if metric.minimum_coverage_frac is None else 1.,unit=metric.unit,source_id=metric.source_id,source_field=metric.source_field,data_year='2023',data_mode='synthetic'))
    records = []
    for row in source_rows:
        row.update(schema_version='1.1.0',source_name='Synthetic test fixture',source_url='https://example.com/fixture',retrieved_at=datetime(2026,1,1,tzinfo=timezone.utc),aggregation_method='synthetic fixture only',missing_reason=None)
        records.append(FeatureMetadata.model_validate(clean(row)).model_dump(mode='json'))
    p = pd.DataFrame(records)
    p.attrs['grid_definition_id']='fixture'
    perf = simulate(g,p,f,[d],[s])
    req = Requirement(requirement_id='parcel',metric='confirmed_developable_parcel_area_km2',operator='ge',threshold=1,unit='km2',is_critical=True,basis='project_assumption',rationale='Synthetic critical unknown',coverage_policy='full')
    _,elig,_ = screen(g,p,f,[d],[s],[req],mode='EXPLORATORY')
    return g,p,perf,elig,profile


def write_decision_fixture(tmp_path, tables, *, schema_override=None):
    from dc_locator.io import write_geoparquet,write_parquet
    from dc_locator.provenance import DataMode
    paths = [tmp_path/(name+'.parquet') for name in ['geography','provenance','performance','eligibility']]
    names = ['GeographicFeatureDataset','FeatureMetadata','SitePerformance','ScreeningEligibility']
    versions = ['1.1.0','1.1.0','1.1.0','1.0.0']
    for i,(path,table) in enumerate(zip(paths,tables)):
        writer = write_geoparquet if i == 0 else write_parquet
        writer(table,path,schema_name=schema_override if i == 2 and schema_override else names[i],schema_version=versions[i],data_mode=DataMode.SYNTHETIC,grid_definition_id='fixture')
    return paths


def test_complete_file_run_repeat_and_strict_empty(tmp_path):
    from dc_locator.model.decision import run_phase4
    g,p,perf,elig,profile = decision_fixture()
    paths = write_decision_fixture(tmp_path,[g,p,perf,elig])
    first,manifest = run_phase4(*paths,'configs/scoring_profile.yaml',tmp_path/'one')
    second,repeated = run_phase4(*paths,'configs/scoring_profile.yaml',tmp_path/'two')
    assert manifest['output_hashes'] == repeated['output_hashes']
    assert manifest['rankable'] == 1 and manifest['candidate_regions'] == 1
    assert first['ranked_cells'].facility_id.iloc[0] == 'fixture'
    assert set(first['normalized_metrics'].normalization_status) == {'within_reference'}
    region = first['candidate_regions'].iloc[0]
    assert region.suitable_land_area_km2 == .8
    assert json.loads(region.metric_distributions_json)['w_site_m3']['median'] == 210240
    elig['mode']='STRICT';elig['eligible']=False;elig['conditional']=False
    paths = write_decision_fixture(tmp_path,[g,p,perf,elig])
    strict,manifest = run_phase4(*paths,'configs/scoring_profile.yaml',tmp_path/'strict')
    assert manifest['rankable'] == manifest['candidate_regions'] == 0
    assert not strict['ranked_cells'].mcda_score.notna().any()
    assert json.loads((tmp_path/'strict/candidate_regions.geojson').read_text())['features'] == []


@pytest.mark.parametrize('attack',['hard_fail','duplicate','facility','definition','data_mode','mode','schema','row_version'])
def test_file_contract_attacks_rejected(tmp_path,attack):
    from dc_locator.model.decision import run_phase4
    g,p,perf,elig,_ = decision_fixture()
    if attack == 'hard_fail': elig['hard_fail']=True
    if attack == 'duplicate': elig=pd.concat([elig,elig])
    if attack == 'facility': elig['facility_id']='other'
    if attack == 'definition': elig['grid_definition_id']='other'
    if attack == 'data_mode': elig['data_mode']='real'
    if attack == 'mode': elig['mode']='STRICT'
    if attack == 'row_version': perf['schema_version']='2.0.0'
    paths = write_decision_fixture(tmp_path,[g,p,perf,elig],schema_override='Wrong' if attack == 'schema' else None)
    with pytest.raises(ValueError): run_phase4(*paths,'configs/scoring_profile.yaml',tmp_path/'run')


@pytest.mark.parametrize('attack',['unit','status','field','source','coverage','wide_status','water_basis'])
def test_invalid_required_evidence_unranked_without_reweight(attack):
    from dc_locator.model.decision import decide
    g,p,perf,elig,profile = decision_fixture()
    metadata = json.loads(perf.metric_metadata_json.iloc[0])
    carbon = metadata['c_electricity_tonnes']
    if attack == 'unit': carbon['unit']='kg_CO2e'
    if attack == 'status': carbon['status']='proxy'
    if attack == 'field': carbon['source_evidence']['source_field']='SRCO2RTA'
    if attack == 'source': carbon['source_evidence']['source_id']='other'
    if attack == 'coverage': carbon['source_evidence']['coverage_frac']=.5
    if attack == 'wide_status': g['baseline_water_stress_score_status']='proxy'
    if attack == 'water_basis':
        assumptions=json.loads(perf.assumptions_json.iloc[0]);assumptions['design']['water_basis']='withdrawal';perf['assumptions_json']=json.dumps(assumptions)
    perf['metric_metadata_json']=json.dumps(metadata)
    result = decide(g,p,perf,elig,profile,profile_hash='synthetic')
    assert result['ranked_cells'].rank_status.iloc[0] == 'UNRANKED'
    assert pd.isna(result['ranked_cells'].mcda_score.iloc[0])
    assert result['weights'] == pytest.approx(equal_weights(profile))


@pytest.mark.parametrize('attack',['duplicate_id','family','unequal','overflow'])
def test_invalid_profile_and_overflow(attack):
    profile = load_profile('configs/scoring_profile.yaml').model_dump(mode='json')
    if attack == 'duplicate_id': profile['metrics'][1]['metric_id']=profile['metrics'][0]['metric_id']
    if attack == 'family': profile['metrics'][1]['double_count_family']=profile['metrics'][0]['double_count_family']
    if attack == 'unequal': profile['groups'][0]['equal_parent_weight']=.4;profile['groups'][1]['equal_parent_weight']=.1
    if attack == 'overflow': profile['metrics'][0]['reference_low']=-1e308;profile['metrics'][0]['reference_high']=1e308
    with pytest.raises(ValueError): ScoringProfile.model_validate(profile)
    with pytest.raises(ValueError): normalize_values([0],-1e308,1e308,'maximize')


def test_custom_versioned_ahp_and_profile_freeze(tmp_path):
    import yaml
    from dc_locator.model.decision import run_phase4
    g,p,perf,elig,profile = decision_fixture()
    paths=write_decision_fixture(tmp_path,[g,p,perf,elig])
    document=profile.model_dump(mode='json');document['profile_id']='fixture_ahp_v1';document['weighting_method']='ahp'
    n=len(profile.groups);document['ahp_judgments']={'criteria_ids':profile.weight_criterion_ids,'matrix':np.ones((n,n)).tolist()}
    pp=tmp_path/'profile.yaml';pp.write_text(yaml.safe_dump(document),encoding='utf-8')
    result,manifest=run_phase4(*paths,pp,tmp_path/'ahp')
    assert result['ahp_result']['status']=='ACCEPTED' and manifest['weighting_method']=='ahp'
    assert result['weights'] == pytest.approx(equal_weights(profile))
    assert (tmp_path/'ahp/ahp_result.json').is_file()
    assert not (tmp_path/'ahp/ahp_template.json').is_file()
    # The accepted baseline is protected; a separately named custom profile is allowed.
    document['profile_id']='reduced_geography_annual_v1';pp.write_text(yaml.safe_dump(document),encoding='utf-8')
    with pytest.raises(ValueError,match='predeclaration'): run_phase4(*paths,pp,tmp_path/'changed')


def test_hierarchical_user_weights_and_ahp_independent_pareto():
    from dc_locator.model.decision import decide
    g,p,perf,elig,profile=decision_fixture()
    base=decide(g,p,perf,elig,profile,profile_hash='p')
    document=profile.model_dump(mode='json');document['profile_id']='fixture_user_v1';document['weighting_method']='user'
    document['user_weights']=dict(zip(profile.weight_criterion_ids,[1,2,1,1]))
    custom=ScoringProfile.model_validate(document)
    weighted=decide(g,p,perf,elig,custom,profile_hash='user')
    assert weighted['weights'] == dict(zip(profile.metric_ids,[.2,.2,.2,.2,.2]))
    document['weighting_method']='ahp';document['user_weights']=None
    matrix=np.ones((4,4));matrix[0,1]=9;matrix[1,0]=1/9;matrix[1,2]=9;matrix[2,1]=1/9;matrix[2,0]=9;matrix[0,2]=1/9
    document['ahp_judgments']={'criteria_ids':profile.weight_criterion_ids,'matrix':matrix.tolist()}
    inconsistent=ScoringProfile.model_validate(document)
    reviewed=decide(g,p,perf,elig,inconsistent,profile_hash='ahp')
    assert reviewed['ahp_result']['status']=='REVIEW_REQUIRED'
    assert reviewed['ranked_cells'].rank_status.iloc[0]=='WEIGHTS_REVIEW_REQUIRED'
    assert reviewed['ranked_cells'].is_pareto_optimal.tolist()==base['ranked_cells'].is_pareto_optimal.tolist()
    assert pd.isna(reviewed['ranked_cells'].mcda_score.iloc[0])
    ratios=np.array([.4,.3,.2,.1]);document['ahp_judgments']['matrix']=(ratios[:,None]/ratios[None,:]).tolist()
    ratio_profile=ScoringProfile.model_validate(document)
    ratio_result=decide(g,p,perf,elig,ratio_profile,profile_hash='ratio')
    assert ratio_result['weights'] == pytest.approx(dict(zip(profile.metric_ids,[.4,.15,.15,.2,.1])))
    assert sum(json.loads(ratio_result['ranked_cells'].contribution_by_metric_json.iloc[0]).values()) == pytest.approx(ratio_result['ranked_cells'].mcda_score.iloc[0])


def test_direct_api_requires_explicit_provenance_grid_identity():
    from dc_locator.model.decision import decide
    g,p,perf,elig,profile=decision_fixture()
    p.attrs.clear()
    with pytest.raises(ValueError,match='provenance grid_definition_id'): decide(g,p,perf,elig,profile,profile_hash='p')
    assert decide(g,p,perf,elig,profile,profile_hash='p',provenance_grid_definition_id='fixture')['ranked_cells'].rankable.iloc[0]


@pytest.mark.parametrize('attack',['triangle','hole','invalid','null','empty','fractional','infinite','cell_area','study_area'])
def test_invalid_grid_geometry_and_indices_rejected(attack):
    from shapely.geometry import Polygon
    grid,ranked=region_fixture()
    if attack=='triangle': grid.loc[0,'geometry']=Polygon([(0,0),(1000,0),(1000,1000),(0,0)])
    if attack=='hole': grid.loc[0,'geometry']=Polygon([(0,0),(1000,0),(1000,1000),(0,1000)],holes=[[(100,100),(200,100),(200,200),(100,200)]])
    if attack=='invalid': grid.loc[0,'geometry']=Polygon([(0,0),(1000,1000),(1000,0),(0,1000),(0,0)])
    if attack=='null': grid.loc[0,'geometry']=None
    if attack=='empty': grid.loc[0,'geometry']=Polygon()
    if attack=='fractional': grid['row']=.5
    if attack=='infinite': grid['col']=float('inf')
    if attack=='cell_area': grid['cell_area_km2']=2
    if attack=='study_area': grid['study_area_intersection_km2']=2
    with pytest.raises(ValueError): cluster_regions(grid,ranked,dict(top_fraction=1,adjacency='rook',minimum_cells=1,require_pareto=False),['m'],'p','h')


@pytest.mark.parametrize('field',['top_fraction','minimum_cells','require_pareto','relative_tolerance','absolute_tolerance','local_weight','reference_high','minimum_coverage','ahp_threshold'])
def test_policy_rejects_quoted_flags_and_boolean_coefficients(field):
    document=load_profile('configs/scoring_profile.yaml').model_dump(mode='json')
    if field in {'top_fraction','minimum_cells'}: document['region_selection'][field]=True
    if field=='require_pareto': document['region_selection'][field]='false'
    if field=='relative_tolerance': document['pareto'][field]=False
    if field=='absolute_tolerance': document['pareto']['absolute_tolerances']['annual_electricity_co2e']=False
    if field in {'local_weight','reference_high'}: document['metrics'][0][field]=True
    if field=='minimum_coverage': document['metrics'][0]['minimum_coverage_frac']=True
    if field=='ahp_threshold': document['ahp']['consistency_threshold']=False
    with pytest.raises(ValueError): ScoringProfile.model_validate(document)


def test_public_numeric_and_policy_types_are_strict():
    grid,ranked=region_fixture()
    with pytest.raises(ValueError): cluster_regions(grid,ranked,dict(top_fraction=1.,adjacency='rook',minimum_cells=1,require_pareto='false'),['m'],'p','h')
    with pytest.raises(ValueError): normalize_values([0],False,1.,'maximize')
    with pytest.raises(ValueError): pareto_frontier(ranked,['m'],['minimize'],[False])
