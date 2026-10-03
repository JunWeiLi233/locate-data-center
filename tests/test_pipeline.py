"""Current delivery stage/identity tests using an explicit quarantined fixture."""
import json
from pathlib import Path

import pandas as pd
import pytest
import yaml

from dc_locator.cli import main
from dc_locator.io import write_parquet
from dc_locator.pipeline import Pipeline,STAGES,emit
from dc_locator.paths import project_root
from dc_locator.provenance import DataMode
from dc_locator.run_config import DeliveryConfig,load_delivery_config,preflight,check_table_identity


ROOT=project_root()


def config_copy(tmp_path,**changes):
    document=yaml.safe_load((ROOT/'configs/run_synthetic.yaml').read_text(encoding='utf-8'))
    document.update(changes)
    path=tmp_path/'run.yaml';path.write_text(yaml.safe_dump(document,sort_keys=False),encoding='utf-8')
    return path


@pytest.fixture(scope='module')
def completed(tmp_path_factory):
    output=tmp_path_factory.mktemp('delivery')
    pipeline=Pipeline('configs/run_synthetic.yaml',output)
    pipeline.execute('run')
    return pipeline


def test_native_fixture_physics_missing_and_hard_fail(completed):
    perf=pd.read_parquet(completed.output/'site_performance.parquet')
    first=perf.loc[perf.grid_id.eq(perf.grid_id.iloc[0])]
    assert first.e_facility_mwh.to_numpy()==pytest.approx([840960,840960])
    assert first.c_electricity_kg.to_numpy()==pytest.approx([84096000,84096000])
    assert sorted(first.w_site_m3)==pytest.approx([0,210240])
    ranked=pd.read_parquet(completed.output/'ranked_cells.parquet')
    assert len(ranked)==6
    assert ranked.rankable.sum()==2
    assert not ranked.loc[ranked.hard_fail,'rankable'].any()
    assert not ranked.loc[ranked.raw_local_baseline_water_stress.isna(),'rankable'].any()
    assert ranked.loc[ranked.rankable,'conditional'].all()
    report=json.loads((completed.output/'validation_report.json').read_text(encoding='utf-8'))
    assert report['external_validation']['overall_accuracy'] is None
    assert (completed.output/'recommendation_report.md').is_file()


def test_all_stages_use_verified_cache(completed):
    repeated=Pipeline('configs/run_synthetic.yaml',completed.output)
    for stage in STAGES:repeated.execute(stage)
    assert set(repeated.cache_hits)==set(STAGES)
    for stage in STAGES:
        assert json.loads((completed.output/'stage_manifests'/f'{stage}.json').read_text(encoding='utf-8'))['stage_identity']==repeated.identity


def test_fresh_repeat_has_identical_substantive_outputs(completed,tmp_path):
    repeated=Pipeline('configs/run_synthetic.yaml',tmp_path/'repeat');repeated.execute('run')
    for path in completed.output.rglob('*'):
        if path.is_file() and path.name!='run_metadata.json':
            assert path.read_bytes()==(repeated.output/path.relative_to(completed.output)).read_bytes(),path.name


def test_pipeline_rejects_missing_upstream(tmp_path):
    with pytest.raises(ValueError,match='upstream stage'):
        Pipeline('configs/run_synthetic.yaml',tmp_path/'no_ingest').execute('build-features')


def test_native_source_tamper_fails_before_ingest(tmp_path):
    document=json.loads((ROOT/'tests/fixtures/phase7/sources.json').read_text(encoding='utf-8'))
    document['files'][0]['sha256']='0'*64
    local=tmp_path/'sources.json';local.write_text(json.dumps(document),encoding='utf-8')
    with pytest.raises(ValueError,match='checksum mismatch'):
        Pipeline(config_copy(tmp_path,local_sources=str(local)),tmp_path/'run')


def test_grid_mutation_is_detected_between_stages(tmp_path):
    grid=tmp_path/'grid.parquet';grid.write_bytes((ROOT/'tests/fixtures/phase7/grid.parquet').read_bytes())
    p=Pipeline(config_copy(tmp_path,grid_path=str(grid)),tmp_path/'run')
    p.ingest();grid.write_bytes(grid.read_bytes()+b'changed')
    with pytest.raises(ValueError,match='Configured input changed'):p.build_features()


@pytest.mark.parametrize('change',[{'validation':{'enabled':False,'allow_synthetic':True,'validation_revision':'phase7_current_v1'}}, {'weighting_method':'ahp'}])
def test_changed_optional_configuration_cannot_rebind_old_outputs(completed,tmp_path,change):
    cfg=config_copy(tmp_path,**change)
    with pytest.raises(ValueError,match='another model/config/source revision'):Pipeline(cfg,completed.output)


def test_semantic_validation_rejects_tampered_ranking_even_with_new_manifest(tmp_path):
    p=Pipeline('configs/run_synthetic.yaml',tmp_path/'attack')
    for stage in STAGES[:-1]:getattr(p,stage.replace('-','_'))()
    ranked=pd.read_parquet(p.output/'ranked_cells.parquet');ranked.loc[ranked.rankable,'mcda_score']+=1
    write_parquet(ranked,p.output/'ranked_cells.parquet',schema_name='RankedCellDataset',schema_version='1.1.0',data_mode=DataMode.SYNTHETIC,grid_definition_id=p.config.grid_definition_id)
    m=json.loads(p._manifest('rank').read_text(encoding='utf-8'))
    p.finish('rank',list(m['output_hashes']),m['details'])
    with pytest.raises(ValueError,match='stale or incompatible'):p.validate()


@pytest.mark.parametrize('field,value',[('future',{'enabled':'false'}),('future',{'enabled':False,'ignored':1}),('validation',{'enabled':True,'allow_synthetic':True,'top_k':True}),('maximum_model_cells',True)])
def test_unknown_and_wrong_type_settings_rejected(tmp_path,field,value):
    with pytest.raises(ValueError):load_delivery_config(config_copy(tmp_path,**{field:value}))


def test_national_scope_fails_before_missing_inputs_or_outputs(tmp_path):
    document=load_delivery_config(ROOT/'configs/run_synthetic.yaml').model_dump(mode='json')
    document.update(study_area='conus',grid_path='missing.parquet')
    with pytest.raises(ValueError,match='National model execution is unsupported'):
        preflight(DeliveryConfig.model_validate(document),ROOT,tmp_path/'national')
    assert not (tmp_path/'national').exists()


@pytest.mark.parametrize('path',['data/processed/overwrite','tests/fixtures/overwrite','runs/phase6/final/overwrite'])
def test_output_does_not_overwrite_production_or_historical_inputs(path):
    with pytest.raises(ValueError,match='must not overwrite'):
        preflight(load_delivery_config(ROOT/'configs/run_synthetic.yaml'),ROOT,ROOT/path)


def test_output_cannot_leave_workspace(tmp_path):
    with pytest.raises(ValueError,match='must not overwrite'):
        preflight(load_delivery_config(ROOT/'configs/run_synthetic.yaml'),ROOT,ROOT.parent/'outside')


def test_current_schema_rejects_negative_semver(monkeypatch):
    import dc_locator.run_config as config
    monkeypatch.setattr(config,'read_parquet_metadata',lambda _:dict(schema='GridCell',schema_version='1.2.-1',data_mode='real',grid_definition_id='x'))
    with pytest.raises(ValueError,match='invalid file schema version'):check_table_identity('unused','GridCell','real','x')


def test_acquisition_same_bytes_wrong_version_is_not_reused(tmp_path):
    from dc_locator.pipeline import verify_acquisition_evidence
    from dc_locator.geography.sources.ingestion import file_digest
    native=tmp_path/'native.csv';native.write_text('id,value\n1,2\n',encoding='utf-8')
    log=tmp_path/'log.json'
    entry={'path':str(native),'sha256':file_digest(native),'bytes':native.stat().st_size,'source_id':'official_fixture','version':'v1','url':'https://example.test/native'}
    emit(log,[entry]);embedded={**entry,'manifest':str(log)}
    bound={str(native):entry['sha256'],str(log):file_digest(log)}
    assert len(verify_acquisition_evidence({'acquisition_evidence':embedded},ROOT,bound))==1
    with pytest.raises(ValueError,match='version identity mismatch'):
        verify_acquisition_evidence({'acquisition_evidence':{**embedded,'version':'v2'}},ROOT,bound)


def test_nonempty_unowned_output_is_preserved(tmp_path):
    output=tmp_path/'user_work';output.mkdir();(output/'notes.txt').write_text('preserve',encoding='utf-8')
    with pytest.raises(ValueError,match='Nonempty output'):
        Pipeline('configs/run_synthetic.yaml',output)
    assert (output/'notes.txt').read_text(encoding='utf-8')=='preserve'


def test_cumulative_cache_bytes_do_not_change_substantive_source_manifest(tmp_path):
    from dc_locator.pipeline import substantive_source_manifest
    from dc_locator.reporting import resource_diagnostics
    raw=tmp_path/'data/raw';interim=tmp_path/'data/interim';raw.mkdir(parents=True);interim.mkdir(parents=True)
    (raw/'native').write_bytes(b'abc');(interim/'tile').write_bytes(b'12345')
    first=resource_diagnostics(tmp_path)
    (interim/'another_tile').write_bytes(b'67')
    second=resource_diagnostics(tmp_path)
    assert first['raw_total_bytes_including_manifests']==second['raw_total_bytes_including_manifests']==3
    assert first['interim_total_bytes_including_extracted_copies']==5
    assert second['interim_total_bytes_including_extracted_copies']==7
    science={'source_files':{'official':{'bytes':3,'sha256':'a'*64}},'grid_geometry_sha256':'b'*64,'quality_flags':['unknown']}
    a={'expanded':{**science,**{k:v for k,v in first.items() if k!='scope'}}}
    b={'expanded':{**science,**{k:v for k,v in second.items() if k!='scope'}}}
    assert substantive_source_manifest(a)==substantive_source_manifest(b)=={'expanded':science}
    assert a['expanded']['interim_total_bytes_including_extracted_copies']==5


def test_cli_reports_actionable_missing_stage(tmp_path,capsys):
    assert main(['rank','--config','configs/run_synthetic.yaml','--output',str(tmp_path/'missing')])==2
    assert 'upstream stage' in capsys.readouterr().err
