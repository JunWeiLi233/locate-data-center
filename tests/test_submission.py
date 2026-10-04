"""Submission claims must follow saved alternatives and preserve UNKNOWN."""
import hashlib
import json

import pandas as pd
import pytest

from dc_locator.io import write_parquet
from dc_locator.provenance import DataMode


@pytest.fixture
def evidence():
    rows = []
    for grid, design, rank, carbon, water in [
        ('b', 'dry', 1, 164000.0, 0.0),
        ('b', 'tower', 3, 164000.0, 210240.0),
        ('a', 'dry', 2, 92000.0, 0.0),
    ]:
        rows.append(dict(grid_id=grid, design_id=design, scenario_id='historical',
            mcda_rank=rank, mcda_score=100-rank, rankable=True, hard_fail=False,
            critical_unknown=True, conditional=True, rank_status='CONDITIONAL',
            pareto_status='NONDOMINATED', data_mode='synthetic', grid_definition_id='test-grid',
            e_it_mwh=700800.0, e_facility_mwh=840960.0, c_electricity_tonnes=carbon,
            w_site_m3=water, w_electricity_m3=None, peak_facility_demand_mw=None,
            assumptions_json=json.dumps({'facility':dict(peak_it_power_mw=100,
                average_it_load_factor=.8, target_opening_year=2030,
                operating_lifetime_years=25, hours_in_modeled_year=8760,
                basis='project_assumption', rationale='Software fixture.'),
                'design':{'basis':'project_assumption','rationale':'Software fixture.'},
                'external_scenario':{'basis':'project_assumption','rationale':'Historical static fixture.'}}),
            metric_metadata_json=json.dumps({'w_electricity_m3':dict(status='unknown',
                confidence='unknown',missing_reason='Generation factor unavailable'),
                'w_site_m3':dict(status='calculated',confidence='low',missing_reason=None)}),
            carbon=80.0, raw_carbon=carbon, contribution_carbon=80.0))
    ranked = pd.DataFrame(rows)
    regions = pd.DataFrame([dict(region_id='region-b',representative_grid_id='b',design_id='dry',
        scenario_id='historical',centroid_lat=44.,centroid_lon=-120.,total_area_km2=387500.,n_cells=155),
        dict(region_id='region-a',representative_grid_id='a',design_id='dry',
        scenario_id='historical',centroid_lat=42.,centroid_lon=-77.,total_area_km2=2500.,n_cells=1)])
    geography = pd.DataFrame([dict(grid_id='b',centroid_lat=40.,centroid_lon=-123.,
        county_name_primary='Trinity',state_abbr_primary='CA',county_geoid_all='06105;06023'),
        dict(grid_id='a',centroid_lat=42.,centroid_lon=-77.,county_name_primary='Livingston',
        state_abbr_primary='NY',county_geoid_all='36051')])
    screening = pd.DataFrame([dict(grid_id='b',design_id='dry',scenario_id='historical',
        requirement='verified_power_capacity',outcome='UNKNOWN',missing_reason='Utility study missing')])
    tables = dict(ranked_cells=ranked, site_performance=ranked.copy(),candidate_regions=regions,
        us_grid_dataset=geography,screening_results=screening,feature_provenance=pd.DataFrame())
    profile = dict(profile_id='test',metrics=[dict(metric_id='carbon',definition='Electricity carbon',
        column='c_electricity_tonnes',unit='tonnes_CO2e',direction='minimize',group_id='carbon',
        local_weight=1.,reference_low=0.,reference_high=1000000.,role='decision_metric',
        basis='project_assumption',rationale='Fixture bounds.')],excluded_criteria=[])
    documents = dict(profile_snapshot={'profile':profile},weight_result={'weighting_method':'equal','weights':{'carbon':1.}},
        source_coverage={'core':{'sources':{}}},config_snapshot={'run':{'screening_mode':'EXPLORATORY'},'files':{}},
        validation_report={'external_validation':{'status':'UNAVAILABLE'},'overall_accuracy':None})
    metadata = dict(run_id='fixture',data_mode='synthetic',study_area='fixture',grid_definition_id='test-grid',
        geographic_cells=2,completed_current_stages=['ingest','build-features','screen','simulate','rank','cluster','validate'],
        source_versions_and_access={},actual_working_code_sha256={},config_hashes={},source_checksums={})
    return metadata,tables,documents


def assemble(evidence, **kwargs):
    from dc_locator.submission import assemble_submission_brief
    return assemble_submission_brief(*evidence, **kwargs)


def test_recommendation_uses_persisted_rank_and_cell_centroid(evidence):
    brief=assemble(evidence)
    recommended=brief['recommendation']
    assert recommended['grid_id']=='b'
    assert recommended['design_id']=='dry'
    assert recommended['rank']==1
    assert recommended['centroid']=={'lat':40.,'lon':-123.}
    assert recommended['region_centroid']=={'lat':44.,'lon':-120.}
    assert 'Trinity' in recommended['geographic_label']
    assert brief['alternatives'][0]['grid_id']=='a'
    assert brief['data_mode']=='synthetic'


def test_same_cell_cooling_delta_and_unknown_total_boundaries(evidence):
    brief=assemble(evidence)
    delta=brief['impact']['cooling_comparisons'][0]['reference_minus_alternative']
    assert delta['w_site_m3']==210240.0
    assert delta['c_electricity_tonnes']==0.0
    assert delta['e_facility_mwh']==0.0
    assert delta['w_electricity_m3'] is None
    unknowns={x['id']:x for x in brief['impact']['unknowns']}
    for metric in ['total_water_consumption_m3','total_lifecycle_co2e_tonnes','useful_heat_mwh','community_economic_benefit']:
        assert unknowns[metric]['value'] is None
        assert unknowns[metric]['missing_reason']
    assert brief['implementation_vision'][-1]['period']=='2054 and end of life'
    assert brief['framework']['criteria'][0]['weight']==1.
    assert brief['framework']['criteria'][0]['contribution']==80.
    assert brief['risks'][0]['outcome']=='UNKNOWN'


def test_strict_empty_cannot_manufacture_recommendation(evidence):
    evidence[1]['ranked_cells']['rankable']=False
    evidence[1]['ranked_cells']['mcda_rank']=None
    evidence[1]['candidate_regions']=evidence[1]['candidate_regions'].iloc[:0]
    evidence[2]['config_snapshot']['run']['screening_mode']='STRICT'
    brief=assemble(evidence)
    assert brief['recommendation']['status']=='NO_QUALIFYING_REGION'
    assert brief['alternatives']==[]
    assert brief['impact']['cooling_comparisons']==[]


def test_multiple_external_scenarios_require_explicit_selection(evidence):
    rows=evidence[1]['ranked_cells'].copy()
    rows['scenario_id']='future'
    evidence[1]['ranked_cells']=pd.concat([rows,evidence[1]['ranked_cells']],ignore_index=True)
    with pytest.raises(ValueError,match='scenario'):
        assemble(evidence)
    assert assemble(evidence,scenario_id='historical')['scenario_id']=='historical'
    with pytest.raises(ValueError,match='scenario'):
        assemble(evidence,scenario_id='unavailable')


def test_duplicate_or_hard_failed_representative_rejected(evidence):
    evidence[1]['ranked_cells']=pd.concat([evidence[1]['ranked_cells'],evidence[1]['ranked_cells'].iloc[:1]])
    with pytest.raises(ValueError,match='Duplicate'):
        assemble(evidence)


def saved_fixture(path,evidence):
    metadata,tables,documents=evidence
    path.mkdir()
    hashes={}
    for name,table in tables.items():
        file=path/(name+'.parquet')
        write_parquet(table,file,schema_name='SubmissionTest',schema_version='1.0.0',
            data_mode=DataMode.SYNTHETIC,grid_definition_id='test-grid')
        hashes[file.name]=hashlib.sha256(file.read_bytes()).hexdigest()
    for name,document in documents.items():
        file=path/(name+'.json');file.write_text(json.dumps(document),encoding='utf-8')
        hashes[file.name]=hashlib.sha256(file.read_bytes()).hexdigest()
    metadata['output_hashes']=hashes
    (path/'run_metadata.json').write_text(json.dumps(metadata),encoding='utf-8')
    return path


def test_writer_is_deterministic_read_only_and_rejects_corruption(tmp_path,evidence):
    from dc_locator.submission import build_submission_brief,write_submission
    run=saved_fixture(tmp_path/'source',evidence)
    before={f.name:hashlib.sha256(f.read_bytes()).hexdigest() for f in run.iterdir()}
    for name in ['first','second']:
        write_submission(run,tmp_path/name)
    for name in ['submission_brief.json','submission_brief.md','submission_brief.html']:
        assert (tmp_path/'first'/name).read_bytes()==(tmp_path/'second'/name).read_bytes()
    assert before=={f.name:hashlib.sha256(f.read_bytes()).hexdigest() for f in run.iterdir()}
    with pytest.raises(ValueError,match='exist'):
        write_submission(run,tmp_path/'first')
    (run/'weight_result.json').write_text('{}',encoding='utf-8')
    with pytest.raises(ValueError,match='hash|checksum'):
        build_submission_brief(run)


def test_html_escapes_evidence_and_synthetic_label(evidence):
    from dc_locator.submission_rendering import render_html
    evidence[1]['us_grid_dataset'].loc[0,'county_name_primary']='<script>alert(1)</script>'
    html=render_html(assemble(evidence))
    assert '<script>alert(1)</script>' not in html
    assert '&lt;script&gt;' in html
    assert 'DEMO DATA' in html
    assert 'UNKNOWN' in html
    assert '@media print' in html


def test_current_metadata_nested_scope_contract(tmp_path,evidence):
    from dc_locator.submission import build_submission_brief
    metadata=evidence[0]
    metadata['scope']={'data_mode':metadata.pop('data_mode'),
        'grid_definition_id':metadata.pop('grid_definition_id'),
        'geographic_cells':metadata.pop('geographic_cells'),'scope':metadata.pop('study_area')}
    run=saved_fixture(tmp_path/'source',evidence)
    brief=build_submission_brief(run)
    assert brief['scope']=='fixture'
    assert brief['data_mode']=='synthetic'


def test_known_total_water_is_rendered_and_markdown_evidence_escaped(evidence):
    from dc_locator.submission_rendering import render_markdown,render_html
    evidence[1]['ranked_cells'].loc[0,'w_electricity_m3']=50.
    evidence[1]['ranked_cells'].loc[0,'metric_metadata_json']=json.dumps({'w_electricity_m3':{
        'status':'calculated','confidence':'low'}})
    evidence[1]['us_grid_dataset'].loc[0,'county_name_primary']='<script>alert(1)</script> | [fake](https://example.org)'
    brief=assemble(evidence)
    markdown=render_markdown(brief)
    assert '<script>alert(1)</script>' not in markdown
    assert '[fake](https://example.org)' not in markdown
    assert '&lt;script&gt;' in markdown
    assert r'total\_water\_consumption\_m3' in markdown
    assert 'total_water_consumption_m3' in render_html(brief)
    assert brief['impact']['total_water_consumption']['value']==50.
    assert brief['impact']['total_water_consumption']['status']=='calculated'


def test_supplied_heat_reconciles_unknown_claims(tmp_path,evidence):
    from dc_locator.submission import write_submission
    run=saved_fixture(tmp_path/'source',evidence)
    inputs=tmp_path/'heat.json'
    inputs.write_text(json.dumps(dict(grid_id='b',design_id='dry',scenario_id='historical',
        basis='project_assumption',rationale='Synthetic scenario',consumer_name='Synthetic host',
        temperature_compatible=True,recoverable_fraction=.6,distribution_loss_fraction=.1,
        annual_heat_demand_mwh=400.,annual_auxiliary_electricity_mwh=20.,
        displaced_heating_kg_co2e_per_mwh=200.,auxiliary_electricity_kg_co2e_per_mwh=100.)),encoding='utf-8')
    output=write_submission(run,tmp_path/'output',heat_reuse_input=inputs)
    brief=json.loads((output/'submission_brief.json').read_text())
    assert brief['impact']['heat_reuse_scenario']['delivered_heat_mwh']['value']==400.
    ids=[item['id'] for item in brief['impact']['unknowns']]
    assert 'useful_heat_mwh' not in ids
    assert 'heat_reuse_avoided_co2e_tonnes' not in ids


def test_regional_catalog_reads_native_representative_parts(tmp_path,evidence):
    from dc_locator.submission import build_submission_brief
    run=saved_fixture(tmp_path/'regional',evidence)
    part=run/'parts'/'parent';part.mkdir(parents=True)
    metadata=json.loads((run/'run_metadata.json').read_text())
    for name in ['site_performance','us_grid_dataset','screening_results','feature_provenance']:
        file=run/(name+'.parquet');destination=part/file.name
        file.rename(destination)
        metadata['output_hashes'][destination.relative_to(run).as_posix()]=metadata['output_hashes'].pop(file.name)
    (part/'ranked_cells.parquet').write_bytes((run/'ranked_cells.parquet').read_bytes())
    metadata['output_hashes']['parts/parent/ranked_cells.parquet']=hashlib.sha256((part/'ranked_cells.parquet').read_bytes()).hexdigest()
    compact=evidence[1]['ranked_cells'].drop(columns=['assumptions_json','metric_metadata_json'])
    write_parquet(compact,run/'ranked_cells.parquet',schema_name='RegionalRankedCellDataset',schema_version='1.0.0',
        data_mode=DataMode.SYNTHETIC,grid_definition_id='test-grid')
    metadata['output_hashes']['ranked_cells.parquet']=hashlib.sha256((run/'ranked_cells.parquet').read_bytes()).hexdigest()
    catalog={'cell_size_m':1000,'representative_parts':{'a':'parts/parent','b':'parts/parent'},
        'parts':[{'path':'parts/parent','parent_grid_id':'parent'}],'coverage_warning':'Selected regional parents only.'}
    (run/'regional_catalog.json').write_text(json.dumps(catalog),encoding='utf-8')
    metadata['output_hashes']['regional_catalog.json']=hashlib.sha256((run/'regional_catalog.json').read_bytes()).hexdigest()
    (run/'run_metadata.json').write_text(json.dumps(metadata),encoding='utf-8')
    brief=build_submission_brief(run)
    assert brief['recommendation']['grid_id']=='b'
    assert brief['resolution_m']==1000
    assert brief['facility']['target_opening_year']==2030
    assert 'parts/parent/site_performance.parquet' in brief['evidence']['input_hashes']
    assert 'Selected regional parents only.' in brief['limitations']


def test_cli_submission_command_is_registered():
    from dc_locator.cli import build_parser
    args=build_parser().parse_args(['submission','--run','runs/national_discovery_v2','--output','runs/submission-test'])
    assert args.command=='submission'
    assert args.func.__name__=='_cmd_submission'
