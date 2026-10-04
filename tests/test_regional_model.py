"""Exact regional decision equivalence; all numeric examples are synthetic."""
import json

import geopandas as gpd
import numpy as np
import pandas as pd
import pytest
from shapely.geometry import box

from dc_locator.model.metrics import KEYS, ScoringProfile, load_profile
from dc_locator.model.pareto import pareto_frontier
from dc_locator.model.regions import cluster_regions


def test_refinement_parents_use_sorted_unique_evaluated_representatives():
    from dc_locator.model.regional_decision import select_refinement_parents
    grid=gpd.GeoDataFrame({'grid_id':['g2','g0','g1'],'row':[2,0,1]},
        geometry=[box(0,i*1000,1000,(i+1)*1000) for i in [2,0,1]],crs=5070)
    regions=pd.DataFrame({'representative_grid_id':['g2','g0','g2']})
    selected=select_refinement_parents(grid,regions)
    assert selected.grid_id.tolist()==['g0','g2']
    assert selected.row.tolist()==[0,2] and selected.crs==grid.crs
    pd.testing.assert_frame_equal(selected,select_refinement_parents(
        grid.sample(frac=1,random_state=2),regions.sample(frac=1,random_state=3)))
    with pytest.raises(ValueError,match='lineage'):
        select_refinement_parents(grid,pd.DataFrame({'representative_grid_id':['missing']}))
    with pytest.raises(ValueError,match='lineage'):
        select_refinement_parents(pd.concat([grid,grid.iloc[:1]]),regions)
    assert select_refinement_parents(grid,regions.iloc[:0]).empty


@pytest.mark.parametrize('relative',[0.,1e-12,.1,1.,2.])
def test_exact_pareto_tree_matches_block_oracle(relative):
    rng=np.random.default_rng(281)
    values=rng.normal(size=(180,5))*np.array([1.,10.,.01,1000.,1.])
    values[15:25]=values[:10]
    values[:,4]=4.
    values[26,0]=np.nan;values[27,1]=np.inf
    frame=pd.DataFrame(values,columns=list('abcde'))
    frame['scenario_id']=np.where(np.arange(len(frame))%3,'baseline','other')
    frame['rankable']=True;frame.loc[28,'rankable']=False
    directions=['minimize','maximize','minimize','maximize','maximize']
    tolerances=[1e-9,.1,.005,1.,0.]
    block=pareto_frontier(frame,list('abcde'),directions,tolerances,
        relative_tolerance=relative,block_size=13,algorithm='block')
    tree=pareto_frontier(frame,list('abcde'),directions,tolerances,
        relative_tolerance=relative,block_size=17,algorithm='tree')
    pd.testing.assert_frame_equal(block,tree)
    shuffled=frame.sample(frac=1,random_state=73)
    again=pareto_frontier(shuffled,list('abcde'),directions,tolerances,
        relative_tolerance=relative,block_size=11,algorithm='tree')
    pd.testing.assert_frame_equal(tree,again.sort_index())


def test_pareto_tree_preserves_tolerance_cycles_and_boundary_values():
    cycle=pd.DataFrame({'x':[2.,0.,1.],'y':[0.,1.,2.],'z':[1.,2.,0.],
        'scenario_id':['s']*3,'rankable':[True]*3})
    result=pareto_frontier(cycle,['x','y','z'],['maximize']*3,[1.]*3,
        algorithm='tree',block_size=1)
    assert result.pareto_status.tolist()==['DOMINATED']*3
    assert result.is_pareto_optimal.tolist()==[False]*3
    edge=pd.DataFrame({'x':[0.,1.,np.nextafter(1.,0.),np.nextafter(1.,np.inf),-1.,-1.],
        'y':[2.]*6,'scenario_id':['s']*6,'rankable':[True]*6})
    for directions in [['maximize']*2,['minimize']*2]:
        expected=pareto_frontier(edge,['x','y'],directions,[1.,0.],algorithm='block')
        actual=pareto_frontier(edge,['x','y'],directions,[1.,0.],algorithm='tree',block_size=1)
        pd.testing.assert_frame_equal(expected,actual)
    constant=edge.copy();constant[['x','y']]=0.
    assert pareto_frontier(constant,['x','y'],['maximize']*2,[0.,0.],algorithm='tree').is_pareto_optimal.all()


def extent_policy(**changes):
    return dict(top_fraction=1.,adjacency='rook',minimum_cells=1,require_pareto=False,
        maximum_extent_km=20.,extent_basis='project_assumption',
        extent_rationale='Bound regional investigation areas on the fixed lattice',**changes)


def test_regions_split_connected_corridor_on_global_lattice_deterministically():
    n=61
    grid=gpd.GeoDataFrame({'grid_id':[f'g{i:03}' for i in range(n)],
        'grid_definition_id':['fixture']*n,'row':[7]*n,'col':list(range(3,3+n)),
        'study_area_intersection_km2':[1.]*n,'suitable_land_area_km2':[.8]*n},
        geometry=[box(i*1000,-8000,(i+1)*1000,-7000) for i in range(3,3+n)],crs=5070)
    ranked=pd.DataFrame({'grid_id':grid.grid_id,'design_id':['d']*n,'scenario_id':['s']*n,
        'mcda_score':np.arange(n,dtype=float),'rankable':[True]*n,'conditional':[True]*n,
        'critical_unknown':[True]*n,'is_pareto_optimal':[True]*n})
    legacy={k:v for k,v in extent_policy().items() if k not in {'maximum_extent_km','extent_basis','extent_rationale'}}
    old,members=cluster_regions(grid,ranked,legacy,[],'p','h')
    assert old.n_cells.tolist()==[61] and old.schema_version.tolist()==['1.1.0']
    bounded,split=cluster_regions(grid,ranked,extent_policy(),[],'p','bounded')
    assert sorted(bounded.n_cells)==[4,17,20,20]
    assert set(bounded.schema_version)=={'1.2.0'}
    assert len(split)==len(members)==n
    bounds=bounded.bounds
    assert ((bounds.maxx-bounds.minx)<=20000).all()
    assert ((bounds.maxy-bounds.miny)<=20000).all()
    for ids in bounded.member_grid_ids:
        cols=sorted(grid.set_index('grid_id').loc[ids,'col'])
        assert cols==list(range(cols[0],cols[-1]+1))
        assert len({col//20 for col in cols})==1
    again,repeated=cluster_regions(grid.sample(frac=1,random_state=9),
        ranked.sample(frac=1,random_state=8),extent_policy(),[],'p','bounded')
    pd.testing.assert_frame_equal(bounded,again)
    pd.testing.assert_frame_equal(split,repeated)


@pytest.mark.parametrize('change',[{'maximum_extent_km':True},{'maximum_extent_km':'20'},
    {'maximum_extent_km':0},{'maximum_extent_km':np.inf},{'maximum_extent_km':np.nan},
    {'extent_basis':'published_source_scale'},{'extent_rationale':''},{'extent_rationale':None}])
def test_bounded_region_policy_requires_explicit_numeric_project_assumption(change):
    document=load_profile('configs/scoring_profile.yaml').model_dump(mode='json')
    document['region_selection'].update(extent_policy());document['region_selection'].update(change)
    with pytest.raises(ValueError):ScoringProfile.model_validate(document)


def decision_universe():
    from test_phase4 import decision_fixture
    from dc_locator.model.metrics import clean
    from dc_locator.schemas import FeatureMetadata
    g,p,performance,eligibility,profile=decision_fixture()
    geos=[];provs=[];perfs=[];eligs=[]
    for i,stress in enumerate([3.,1.,None,2.]):
        grid_id=f'g{i}'
        geo=g.copy();geo['grid_id']=grid_id;geo['row']=0;geo['col']=i
        geo.geometry=[box(i*1000,0,(i+1)*1000,1000)]
        prov=p.copy();prov['grid_id']=grid_id
        for metric,value in zip(profile.metrics[2:],[stress,[30.,10.,5.,1.][i],[.5,.7,.9,1.][i]]):
            known=value is not None
            status=metric.allowed_statuses[0] if known else 'unknown'
            confidence='high' if known else 'unknown'
            coverage=(None if metric.minimum_coverage_frac is None else 1.) if known else 0.
            geo[metric.column]=np.nan if value is None else value
            geo[metric.column+'_status']=status;geo[metric.column+'_confidence']=confidence
            geo[metric.column+'_coverage_frac']=coverage
            index=prov.index[prov.metric.eq(metric.column)][0]
            row=clean(prov.loc[index].to_dict())
            row.update(value=value,status=status,confidence=confidence,coverage_frac=coverage,
                missing_reason=None if known else 'source_nodata')
            for key,val in FeatureMetadata.model_validate(row).model_dump(mode='json').items():
                prov.loc[index,key]=val
        perf=performance.copy();perf['grid_id']=grid_id
        metadata=json.loads(perf.metric_metadata_json.iloc[0])
        for definition in metadata.values():
            if definition.get('source_evidence'):definition['source_evidence']['grid_id']=grid_id
        perf['metric_metadata_json']=json.dumps(metadata,sort_keys=True)
        elig=eligibility.copy();elig['grid_id']=grid_id
        if i==3:elig['eligible']=False;elig['conditional']=False;elig['hard_fail']=True
        geos.append(geo);provs.append(prov);perfs.append(perf);eligs.append(elig)
    geography=gpd.GeoDataFrame(pd.concat(geos,ignore_index=True),geometry='geometry',crs=5070)
    provenance=pd.concat(provs,ignore_index=True);provenance.attrs['grid_definition_id']='fixture'
    return geography,provenance,pd.concat(perfs,ignore_index=True),pd.concat(eligs,ignore_index=True),profile


@pytest.mark.parametrize('method',['equal','user','ahp_review'])
def test_batch_then_global_decision_matches_existing_full_universe(method):
    from dc_locator.model.decision import decide
    from dc_locator.model.regional_decision import prepare_batch,rank_compact,finalize_normalized
    geography,provenance,performance,eligibility,profile=decision_universe()
    document=profile.model_dump(mode='json')
    if method=='user':
        document['weighting_method']='user';document['user_weights']=dict(zip(profile.weight_criterion_ids,[1.,2.,1.,3.]))
    if method=='ahp_review':
        matrix=np.ones((4,4));matrix[0,1]=9;matrix[1,0]=1/9
        matrix[1,2]=9;matrix[2,1]=1/9;matrix[2,0]=9;matrix[0,2]=1/9
        document['weighting_method']='ahp';document['ahp_judgments']={'criteria_ids':profile.weight_criterion_ids,'matrix':matrix.tolist()}
    profile=ScoringProfile.model_validate(document)
    expected=decide(geography,provenance,performance,eligibility,profile,profile_hash='fixture')
    batches=[]
    for ids in [{'g0','g2'},{'g1','g3'}]:
        p=provenance.loc[provenance.grid_id.isin(ids)].copy();p.attrs['grid_definition_id']='fixture'
        batch=prepare_batch(geography.loc[geography.grid_id.isin(ids)],p,
            performance.loc[performance.grid_id.isin(ids)],eligibility.loc[eligibility.grid_id.isin(ids)],
            profile,profile_hash='fixture',provenance_grid_definition_id='fixture')
        assert batch['ranked_cells'].mcda_rank.isna().all()
        assert batch['ranked_cells'].is_pareto_optimal.isna().all()
        assert not {'metric_metadata_json','assumptions_json','warnings_json'} & set(batch['compact'])
        batches.append(batch)
    compact=pd.concat([batch['compact'] for batch in batches],ignore_index=True)
    actual=rank_compact(compact,profile,profile_hash='fixture')
    columns=[column for column in actual if column in expected['ranked_cells']]
    pd.testing.assert_frame_equal(actual[columns],expected['ranked_cells'][columns])
    for batch in batches:
        normalized=finalize_normalized(batch['normalized_metrics'],actual)
        ids=set(normalized.grid_id)
        oracle=expected['normalized_metrics'].loc[expected['normalized_metrics'].grid_id.isin(ids)].reset_index(drop=True)
        pd.testing.assert_frame_equal(normalized,oracle)
    assert actual.loc[actual.grid_id.eq('g3'),'mcda_score'].isna().all()
    assert actual.loc[actual.grid_id.eq('g2'),'rank_status'].tolist()==['UNRANKED']
    if method!='ahp_review':assert actual.is_pareto_optimal.tolist()==[False,True,pd.NA,pd.NA]
    again=rank_compact(compact.sample(frac=1,random_state=11),profile,profile_hash='fixture')
    pd.testing.assert_frame_equal(actual,again)


def test_global_compact_rejects_duplicate_identity_and_changed_metric_policy():
    from dc_locator.model.regional_decision import prepare_batch,rank_compact
    g,p,f,e,profile=decision_universe()
    compact=prepare_batch(g,p,f,e,profile,profile_hash='fixture',provenance_grid_definition_id='fixture')['compact']
    with pytest.raises(ValueError,match='Duplicate'):rank_compact(pd.concat([compact,compact]),profile,profile_hash='fixture')
    document=profile.model_dump(mode='json');document['metrics'][0]['reference_high']*=2
    with pytest.raises(ValueError,match='metric policy'):rank_compact(compact,ScoringProfile.model_validate(document),profile_hash='changed')


def test_global_compact_cannot_claim_valid_partial_required_evidence():
    from dc_locator.model.regional_decision import prepare_batch,rank_compact
    g,p,f,e,profile=decision_universe()
    compact=prepare_batch(g,p,f,e,profile,profile_hash='fixture',provenance_grid_definition_id='fixture')['compact']
    compact.loc[0,'annual_electricity_co2e_coverage_frac']=.5
    with pytest.raises(ValueError,match='coverage'):rank_compact(compact,profile,profile_hash='fixture')


def test_bounded_file_runner_uses_candidate_schema_1_2(tmp_path):
    import yaml
    from test_phase4 import decision_fixture,write_decision_fixture
    from dc_locator.model.decision import run_phase4
    g,p,f,e,profile=decision_fixture()
    paths=write_decision_fixture(tmp_path,[g,p,f,e])
    document=profile.model_dump(mode='json');document['profile_id']='synthetic_bounded_v1'
    document['region_selection'].update(extent_policy())
    path=tmp_path/'profile.yaml';path.write_text(yaml.safe_dump(document),encoding='utf-8')
    result,_=run_phase4(*paths,path,tmp_path/'bounded')
    assert set(result['candidate_regions'].schema_version)=={'1.2.0'}
    assert json.loads((tmp_path/'bounded/candidate_regions.geojson').read_text())['dc_locator']['schema_version']=='1.2.0'


def test_global_decision_schema_validation_uses_bounded_row_batches(monkeypatch):
    from dc_locator.model.regional_decision import prepare_batch,rank_compact
    g,p,f,e,profile=decision_universe()
    base=prepare_batch(g,p,f,e,profile,profile_hash='fixture',provenance_grid_definition_id='fixture')['compact']
    compact=pd.concat([base]*751,ignore_index=True)
    compact['grid_id']=[f'synthetic-{i:05}' for i in range(len(compact))]
    original=pd.DataFrame.to_dict;seen=[]
    def bounded_records(frame,*args,**kwargs):
        orient=args[0] if args else kwargs.get('orient','dict')
        if orient=='records':
            seen.append(len(frame))
            assert len(frame)<=1000,'Decision validation allocated the complete global row dictionary list'
        return original(frame,*args,**kwargs)
    monkeypatch.setattr(pd.DataFrame,'to_dict',bounded_records)
    ranked=rank_compact(compact,profile,profile_hash='fixture')
    assert len(ranked)==3004
    assert len(seen)==4 and max(seen)<=1000


def test_normalized_finalization_reuses_global_key_index(monkeypatch,tmp_path):
    from dc_locator.model.regional_decision import prepare_batch,rank_compact,finalize_normalized
    g,p,f,e,profile=decision_universe()
    batch=prepare_batch(g,p,f,e,profile,profile_hash='fixture',provenance_grid_definition_id='fixture')
    ranked=rank_compact(batch['compact'],profile,profile_hash='fixture')
    original=pd.MultiIndex.from_frame;calls=[]
    def record(frame,*args,**kwargs):
        calls.append(len(frame))
        return original(frame,*args,**kwargs)
    monkeypatch.setattr(pd.MultiIndex,'from_frame',record)
    one=finalize_normalized(batch['normalized_metrics'],ranked)
    two=finalize_normalized(batch['normalized_metrics'],ranked)
    pd.testing.assert_frame_equal(one,two)
    # The global key index is constructed once; batch membership is tested
    # against that index instead of rebuilding every global tuple set.
    assert calls.count(len(ranked))<=1
    assert len(calls)>=2
    # Runtime indexes must not become nonserializable artifact attributes.
    ranked.to_parquet(tmp_path/'synthetic-global.parquet',index=False)
    pd.testing.assert_frame_equal(ranked,pd.read_parquet(tmp_path/'synthetic-global.parquet'))


def test_compact_validation_passes_read_only_input_to_copying_scorer(monkeypatch):
    import dc_locator.model.regional_decision as decision
    g,p,f,e,profile=decision_universe()
    compact=decision.prepare_batch(g,p,f,e,profile,profile_hash='fixture',provenance_grid_definition_id='fixture')['compact']
    original=compact.copy(deep=True);score=decision.score_alternatives
    def one_owned_copy(frame,*args,**kwargs):
        assert frame is compact,'Read-only compact validation allocated an extra full evidence copy'
        return score(frame,*args,**kwargs)
    monkeypatch.setattr(decision,'score_alternatives',one_owned_copy)
    decision.rank_compact(compact,profile,profile_hash='fixture')
    pd.testing.assert_frame_equal(compact,original)


def test_mcda_rank_sort_carries_only_ordering_columns_and_preserves_evidence(monkeypatch):
    from dc_locator.model.mcda import score_alternatives
    frame=pd.DataFrame({'grid_id':['g2','g1','g0','g4','g3'],'design_id':['d']*5,
        'scenario_id':['s','s','s','other','other'],'a':[80.,80.,50.,100.,np.nan],
        'b':[60.,60.,50.,100.,50.],'eligible':[True]*5,
        'hard_fail':[False,False,False,True,False],
        'critical_unknown':[False,False,False,False,True],'conditional':[False]*5,
        'mode':['EXPLORATORY']*4+['STRICT'],'unused_evidence_json':['x'*16384]*5})
    frame.attrs['fixture_identity']={'source':'synthetic in-memory evidence'}
    before=frame.copy(deep=True);original=pd.DataFrame.sort_values;seen=[]
    def narrow_sort(table,by,*args,**kwargs):
        if list(by)==['scenario_id','mcda_score','grid_id','design_id']:
            assert set(table)==set(by),'Rank assignment sorted every physical evidence column'
            seen.append(len(table))
        return original(table,by,*args,**kwargs)
    monkeypatch.setattr(pd.DataFrame,'sort_values',narrow_sort)
    result=score_alternatives(frame,['a','b'],{'a':.5,'b':.5})
    assert seen==[3]
    assert result.grid_id.tolist()==['g0','g1','g2','g3','g4']
    assert result.mcda_rank.iloc[:3].tolist()==[3,1,2]
    assert result.mcda_score.iloc[:3].tolist()==[50.,70.,70.]
    assert result.mcda_rank.iloc[3:].isna().all() and result.mcda_score.iloc[3:].isna().all()
    assert result.contribution_by_metric_json.iloc[3:].tolist()==['{}','{}']
    assert result.unused_evidence_json.eq('x'*16384).all()
    assert result.attrs==frame.attrs
    pd.testing.assert_frame_equal(frame,before)
