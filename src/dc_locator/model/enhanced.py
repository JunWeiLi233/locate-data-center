"""Phase5 integration through the accepted geography/physics/decision APIs.

No acquisition happens here. Native expanded sources remain informational;
predeclared water source bindings are evaluated as separate external contexts.
"""
import argparse
import json
import re
import os
import ctypes
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

import pandas as pd
import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from dc_locator.config import load_facility_config
from dc_locator.io import read_geoparquet, read_parquet, read_parquet_metadata, write_geoparquet, write_parquet
from dc_locator.geography.sources.aqueduct_future import build_aqueduct_future_features, future_period
from dc_locator.geography.sources.expanded import build_expanded_features, expanded_default_source_inputs
from dc_locator.model.cooling import load_cooling_designs, load_physical_scenarios
from dc_locator.model.decision import run_phase4, sha256
from dc_locator.model.lifecycle import calculate_lifecycle
from dc_locator.model.metrics import load_profile, ScoringProfile, json_text
from dc_locator.model.physics import run_phase3
from dc_locator.model.scenarios import AnnualExtensionPolicy, make_external_scenarios, build_temporal_scenarios, build_climate_source_context
from dc_locator.model.screening import load_requirements
from dc_locator.provenance import DataMode
from dc_locator.schemas import FacilityConfig
from dc_locator.validation import validate_feature_provenance


def peak_working_set_bytes():
    """Read this Windows process's actual OS lifetime peak; no sampling estimate."""
    if os.name!='nt': return None
    from ctypes import wintypes
    class Counters(ctypes.Structure):
        _fields_=[('cb',wintypes.DWORD),('PageFaultCount',wintypes.DWORD)]+[(name,ctypes.c_size_t) for name in
            ('PeakWorkingSetSize','WorkingSetSize','QuotaPeakPagedPoolUsage','QuotaPagedPoolUsage',
             'QuotaPeakNonPagedPoolUsage','QuotaNonPagedPoolUsage','PagefileUsage','PeakPagefileUsage')]
    kernel=ctypes.WinDLL('kernel32');kernel.GetCurrentProcess.restype=wintypes.HANDLE
    query=ctypes.WinDLL('psapi').GetProcessMemoryInfo
    query.argtypes=[wintypes.HANDLE,ctypes.POINTER(Counters),wintypes.DWORD];query.restype=wintypes.BOOL
    counters=Counters();counters.cb=ctypes.sizeof(counters)
    if not query(kernel.GetCurrentProcess(),ctypes.byref(counters),counters.cb): return None
    return int(counters.PeakWorkingSetSize)


class Phase5Config(BaseModel):
    model_config = ConfigDict(extra='forbid')
    schema_version: Literal['1.0.0']
    geography: str
    provenance: str
    facility: str
    cooling_designs: str
    physical_scenarios: str
    constraints: str
    baseline_profile: str
    enhanced_profile_declaration: str
    pathways: list[Literal['bau','opt','pes']] = Field(min_length=1)
    milestone_years: list[int] = Field(min_length=1)
    screening_modes: list[Literal['STRICT','EXPLORATORY']] = Field(min_length=1)
    annual_extension: AnnualExtensionPolicy
    lifecycle: str
    comparison_policy: dict

    @model_validator(mode='after')
    def unique_policies(self):
        for values in (self.pathways,self.milestone_years,self.screening_modes):
            if len(set(values)) != len(values): raise ValueError('Duplicate phase5 policy dimensions')
        if not self.comparison_policy.get('basis') or not self.comparison_policy.get('rationale'):
            raise ValueError('Comparison needs disclosed project/user policy rationale')
        return self


def validate_matched_preferences(baseline, enhanced):
    """A data-binding comparison cannot silently become a preference comparison."""
    for field in ('weighting_method','weight_scope','user_weights','ahp_judgments','groups',
                  'excluded_criteria','pareto','region_selection','ahp'):
        if getattr(baseline,field) != getattr(enhanced,field):
            raise ValueError('Enhanced comparison changed baseline decision preferences: '+field)
    if baseline.metric_ids != enhanced.metric_ids: raise ValueError('Enhanced criteria differ from baseline')
    for a,b in zip(baseline.metrics, enhanced.metrics):
        av,bv = a.model_dump(),b.model_dump()
        if a.metric_id == 'local_baseline_water_stress':
            for field in ('column','definition','rationale','allowed_statuses','source_id','source_field'):
                av.pop(field);bv.pop(field)
        if av != bv: raise ValueError('Enhanced metric preferences/bounds differ: '+a.metric_id)
    return True


def rebind_external_scenario(table, scenario, *, physical_metadata=False):
    """Copy one physical scenario to a declared context; retain original evidence."""
    if table.empty or set(table.scenario_id) != {scenario.physical_scenario_id}:
        raise ValueError('Only the exact declared original physical scenario may be rebound')
    result = table.copy(); result['scenario_id'] = scenario.scenario_id
    if physical_metadata:
        assumptions=[]
        for encoded in table.assumptions_json:
            original=json.loads(encoded)
            if original.get('external_scenario',{}).get('scenario_id') != scenario.physical_scenario_id:
                raise ValueError('Original physical scenario identity differs from rebinding request')
            assumptions.append(json_text(dict(original, external_context=scenario.model_dump(mode='json'))))
        result['assumptions_json']=assumptions
    return result


def _read_baseline(geo_path, prov_path):
    geo_meta, prov_meta = read_parquet_metadata(geo_path), read_parquet_metadata(prov_path)
    for meta, schema in ((geo_meta,'GeographicFeatureDataset'),(prov_meta,'FeatureMetadata')):
        match=re.fullmatch(r'1\.(\d+)\.(\d+)',meta.get('schema_version',''))
        if meta.get('schema') != schema or not match or int(match.group(1)) < 1:
            raise ValueError('Phase5 requires compatible baseline '+schema+'1.1+')
    for key in ('data_mode','grid_definition_id'):
        if not geo_meta.get(key) or geo_meta[key] != prov_meta.get(key): raise ValueError('Baseline file identity mismatch: '+key)
    grid,provenance=read_geoparquet(geo_path),read_parquet(prov_path)
    if grid.empty or set(grid.grid_definition_id) != {geo_meta['grid_definition_id']} or set(grid.data_mode) != {geo_meta['data_mode']}:
        raise ValueError('Baseline row/file identity mismatch')
    grid.attrs.update(geo_meta);provenance.attrs.update(prov_meta)
    validate_feature_provenance(provenance,grid_ids=grid.grid_id,data_mode=geo_meta['data_mode'],grid_definition_id=geo_meta['grid_definition_id'])
    return grid,provenance,geo_meta


def _write_table(table,path,schema,version,metadata):
    write_parquet(table,path,schema_name=schema,schema_version=version,
        data_mode=DataMode(metadata['data_mode']),grid_definition_id=metadata['grid_definition_id'])


def verify_baseline_repeat(folder, mode, root):
    """Every required accepted artifact must exist and have identical bytes."""
    strict = mode == 'STRICT'
    accepted_physical = root/'runs/phase3' if strict else root/'runs/phase3/exploratory'
    accepted_decision = root/'runs/phase4'/mode.lower()
    checks = {}
    for family,accepted,names in [
        ('physical',accepted_physical,['screening_results.parquet','site_performance.parquet','screening_eligibility.parquet','screening_summary.json']),
        ('decision',accepted_decision,['normalized_metrics.parquet','pareto_results.parquet','ranked_cells.parquet','region_membership.parquet','candidate_regions.geojson','ranking.csv','ahp_template.json','profile_snapshot.json'])]:
        for name in names:
            original,repeated=accepted/name,folder/family/name
            if not original.is_file() or not repeated.is_file(): raise ValueError('Required baseline artifact missing: '+str(original)+' or '+str(repeated))
            checks[family+'/'+name] = sha256(original)==sha256(repeated)
    if not all(checks.values()): raise ValueError('Accepted baseline rerun changed substantive artifacts: '+str([k for k,v in checks.items() if not v]))
    return checks


def compare_rankings(baseline, enhanced, scenario, mode):
    """Matched grid/design comparisons, explicitly within one external context."""
    if set(enhanced.scenario_id) != {scenario.scenario_id} or set(baseline.scenario_id) != {scenario.physical_scenario_id}:
        raise ValueError('Comparison cannot pool physical/external scenarios')
    keys=['grid_id','design_id']
    if baseline.duplicated(keys).any() or enhanced.duplicated(keys).any() or set(map(tuple,baseline[keys].values)) != set(map(tuple,enhanced[keys].values)):
        raise ValueError('Baseline/enhanced alternative domains differ')
    fields=['mcda_score','mcda_rank','rankable','rank_status','conditional','critical_unknown','hard_fail',
            'raw_local_baseline_water_stress','raw_annual_electricity_co2e','raw_annual_site_water_consumption']
    result=baseline[keys+fields].merge(enhanced[keys+fields],on=keys,suffixes=('_baseline','_enhanced'),validate='one_to_one')
    result['scenario_id']=scenario.scenario_id;result['physical_scenario_id']=scenario.physical_scenario_id
    result['mode']=mode;result['pathway']=scenario.pathway;result['ssp_rcp']=scenario.ssp_rcp
    result['milestone_year']=scenario.milestone_year;result['native_window_start_year']=scenario.window_start_year
    result['native_window_end_year']=scenario.window_end_year;result['native_period_supported']=scenario.supported
    result['mcda_score_delta']=result.mcda_score_enhanced-result.mcda_score_baseline
    result['mcda_rank_delta']=result.mcda_rank_enhanced-result.mcda_rank_baseline
    result['preferences_unchanged']=True;result['change_basis']='water source/time context only; other expanded sources informational'
    for metric in ('raw_annual_electricity_co2e','raw_annual_site_water_consumption'):
        a,b=result[metric+'_baseline'],result[metric+'_enhanced']
        if not (a.eq(b) | (a.isna() & b.isna())).all(): raise ValueError('Matched physical assumption unexpectedly changed')
    return result.sort_values(keys).reset_index(drop=True)


def combine_temporal_context(temporal, climate):
    """Explicit nullable long-table dtypes preserve absent native milestones."""
    tables=[]
    for frame in (temporal,climate):
        copy=frame.copy()
        for field in ('period_start_year','period_end_year','milestone_year'):
            copy[field]=copy[field].astype('Int64')
        for field in ('value','coverage_frac','hours_in_modeled_year'):
            copy[field]=copy[field].astype('Float64')
        tables.append(copy)
    return pd.concat(tables,ignore_index=True).sort_values(['grid_id','design_id','scenario_id','variable','period_start_year'],na_position='last').reset_index(drop=True)


def run_phase5(config_path='configs/phase5.yaml', output_dir='runs/phase5/integrated', *,
        expanded_source_inputs=None, aqueduct_source_input=None, study_geometry=None):
    """Run cached real data (or quarantined fixtures), without replacing baseline.

    All profiles are checked against their prior declaration before aggregation
    or ranking. Each mode/pathway/native period gets its own ranking package.
    """
    root=Path(__file__).resolve().parents[3]
    config_path=Path(config_path).resolve(); output=Path(output_dir).resolve()
    if output==root or any(output.is_relative_to(root/'runs'/name) for name in ('phase3','phase4')):
        raise ValueError('Enhanced output must not overwrite accepted baseline folders')
    config=Phase5Config.model_validate(yaml.safe_load(config_path.read_text(encoding='utf-8')))
    path=lambda value: Path(value) if Path(value).is_absolute() else root/value
    geo_path,prov_path=path(config.geography),path(config.provenance)
    preserved = [geo_path,prov_path]+[p for p in (root/'configs').glob('*.yaml') if not p.name.startswith('phase5') and p.name!='expanded_sources.yaml']
    preserved += [p for folder in ('phase3','phase4') for p in (root/'runs'/folder).rglob('*') if p.is_file()]
    before={str(p.relative_to(root)):sha256(p) for p in preserved}
    grid,provenance,metadata=_read_baseline(geo_path,prov_path)
    facilities=load_facility_config(path(config.facility)).facilities
    if len(facilities)!=1: raise ValueError('Phase5 runner requires one configured facility per run')
    facility=FacilityConfig.model_validate(facilities[0].model_dump(mode='json'))
    designs=load_cooling_designs(path(config.cooling_designs));physical=load_physical_scenarios(path(config.physical_scenarios))
    if len(physical)!=1: raise ValueError('One physical baseline per matched comparison run required')
    requirements,_=load_requirements(path(config.constraints))
    baseline_profile=load_profile(path(config.baseline_profile))
    declaration_path=path(config.enhanced_profile_declaration)
    declaration=json.loads(declaration_path.read_text(encoding='utf-8'))
    if declaration.get('status')!='PREDECLARED_BEFORE_FIRST_RANKING' or declaration.get('baseline_profile_sha256')!=sha256(path(config.baseline_profile)):
        raise ValueError('Enhanced declaration/baseline profile binding changed')
    entries={Path(e['path']).stem:e for e in declaration['profiles']}
    scenarios=make_external_scenarios(physical[0].scenario_id,[future_period(p,y) for p in config.pathways for y in config.milestone_years])
    for scenario in scenarios:
        entry=entries.get(f'{scenario.pathway}_{scenario.milestone_year}')
        if entry is None or not entry.get('declared_at_utc') or entry.get('status')!='PREDECLARED_BEFORE_FIRST_RANKING': raise ValueError('Missing prior enhanced profile declaration')
        profile_path=path(entry['path']);profile=load_profile(profile_path)
        if sha256(profile_path)!=entry['sha256'] or profile.model_dump(mode='json')!=ScoringProfile.model_validate(entry['profile']).model_dump(mode='json'):
            raise ValueError('Enhanced profile changed after predeclaration')
        validate_matched_preferences(baseline_profile,profile)
    lifecycle_cfg=yaml.safe_load(path(config.lifecycle).read_text(encoding='utf-8'))
    allowed={'schema_version','basis','rationale','inventory','transport_legs','complete_components','component_evidence'}
    if set(lifecycle_cfg)!=allowed or lifecycle_cfg['schema_version']!='1.0.0' or not lifecycle_cfg['basis'] or not lifecycle_cfg['rationale']:
        raise ValueError('Invalid explicit lifecycle configuration')
    output.mkdir(parents=True,exist_ok=True)
    snapshots=output/'configuration';snapshots.mkdir(exist_ok=True)
    used=[config_path,path(config.facility),path(config.cooling_designs),path(config.physical_scenarios),path(config.constraints),path(config.baseline_profile),path(config.lifecycle),declaration_path,root/'configs/expanded_sources.yaml']
    for p in used: (snapshots/p.name).write_bytes(p.read_bytes())
    inputs=expanded_default_source_inputs(root) if expanded_source_inputs is None else expanded_source_inputs
    expanded,expanded_prov,expanded_coverage,expanded_manifest=build_expanded_features(grid,provenance,inputs,study_geometry=study_geometry)
    enhanced,enhanced_prov,future_coverage,future_manifest=build_aqueduct_future_features(expanded,expanded_prov,aqueduct_source_input,
        pathways=config.pathways,milestone_years=config.milestone_years,study_geometry=study_geometry)
    pd.testing.assert_frame_equal(enhanced[grid.columns],grid)
    pd.testing.assert_frame_equal(enhanced_prov.iloc[:len(provenance)].reset_index(drop=True),provenance)
    enhanced.attrs.update(schema='GeographicFeatureDataset',schema_version='1.2.0')
    enhanced_prov.attrs.update(schema='FeatureMetadata',schema_version='1.1.0')
    enhanced_geo_path=output/'enhanced_grid_dataset.parquet';enhanced_prov_path=output/'enhanced_feature_provenance.parquet'
    write_geoparquet(enhanced,enhanced_geo_path,schema_name='GeographicFeatureDataset',schema_version='1.2.0',data_mode=DataMode(metadata['data_mode']),grid_definition_id=metadata['grid_definition_id'])
    _write_table(enhanced_prov,enhanced_prov_path,'FeatureMetadata','1.1.0',metadata)
    baseline_results={};baseline_tables={};baseline_repeat={}
    for mode in config.screening_modes:
        folder=output/'baseline'/mode.lower()
        screening,performance,eligibility,_=run_phase3(geo_path,prov_path,facility,designs,physical,requirements,folder/'physical',mode=mode)
        result,manifest=run_phase4(geo_path,prov_path,folder/'physical/site_performance.parquet',folder/'physical/screening_eligibility.parquet',path(config.baseline_profile),folder/'decision')
        baseline_results[mode]=result;baseline_tables[mode]=(screening,performance,eligibility)
        baseline_repeat[mode]=verify_baseline_repeat(folder,mode,root) if metadata['data_mode']=='real' else {'synthetic_no_accepted_baseline':True}
    bound_performance=[];comparisons=[];packages={}
    for scenario in scenarios:
        entry=entries[f'{scenario.pathway}_{scenario.milestone_year}'];profile_path=path(entry['path'])
        declaration_copy=snapshots/(profile_path.stem+'_declaration.json')
        declaration_copy.write_text(json_text(entry)+'\n',encoding='utf-8')
        (snapshots/profile_path.name).write_bytes(profile_path.read_bytes())
        for index,mode in enumerate(config.screening_modes):
            screening,performance,eligibility=baseline_tables[mode]
            folder=output/'enhanced'/f'{scenario.pathway}_{scenario.milestone_year}'/mode.lower();folder.mkdir(parents=True,exist_ok=True)
            rebound=rebind_external_scenario(performance,scenario,physical_metadata=True)
            if index==0: bound_performance.append(rebound)
            for name,table,schema,version in [
                ('site_performance',rebound,'SitePerformance','1.1.0'),
                ('screening_eligibility',rebind_external_scenario(eligibility,scenario),'ScreeningEligibility','1.0.0'),
                ('screening_results',rebind_external_scenario(screening,scenario),'ScreeningResult','1.1.0')]:
                _write_table(table,folder/(name+'.parquet'),schema,version,metadata)
            (folder/'external_scenario.json').write_text(json_text(scenario.model_dump(mode='json'))+'\n',encoding='utf-8')
            result,manifest=run_phase4(enhanced_geo_path,enhanced_prov_path,folder/'site_performance.parquet',folder/'screening_eligibility.parquet',profile_path,folder/'decision',declaration_path=declaration_copy)
            comparisons.append(compare_rankings(baseline_results[mode]['ranked_cells'],result['ranked_cells'],scenario,mode))
            packages[f'{scenario.pathway}_{scenario.milestone_year}/{mode}']={k:manifest[k] for k in ('alternatives','rankable','conditional_ranked','candidate_regions','region_memberships','output_hashes')}
    physical_all=pd.concat(bound_performance,ignore_index=True)
    temporal=build_temporal_scenarios(physical_all,facility,scenarios,extension_policy=config.annual_extension.model_dump(mode='json'),context_provenance=enhanced_prov)
    climate=build_climate_source_context(enhanced_prov,grid_ids=grid.grid_id,grid_definition_id=metadata['grid_definition_id'],data_mode=metadata['data_mode'],facility_id=facility.facility_id)
    lifecycle=calculate_lifecycle(temporal,opening_year=facility.target_opening_year,lifetime_years=facility.operating_lifetime_years,
        **{k:lifecycle_cfg[k] for k in ('inventory','transport_legs','complete_components','component_evidence')})
    temporal=combine_temporal_context(temporal,climate)
    temporal.attrs.update(grid_definition_id=metadata['grid_definition_id'],data_mode=metadata['data_mode'])
    comparison=pd.concat(comparisons,ignore_index=True).sort_values(['scenario_id','mode','grid_id','design_id']).reset_index(drop=True)
    for filename,table,schema in [('future_scenarios',temporal,'FutureScenarioValue'),('lifecycle_results',lifecycle,'LifecycleResult'),('baseline_vs_enhanced',comparison,'BaselineEnhancedComparison')]:
        _write_table(table,output/(filename+'.parquet'),schema,'1.0.0',metadata)
    comparison.to_csv(output/'baseline_vs_enhanced.csv',index=False,lineterminator='\n')
    coverage=dict(expanded=expanded_coverage,aqueduct_future=future_coverage)
    (output/'source_coverage.json').write_text(json_text(coverage)+'\n',encoding='utf-8')
    (output/'source_manifest.json').write_text(json_text(dict(expanded=expanded_manifest,aqueduct_future=future_manifest))+'\n',encoding='utf-8')
    after={str(p.relative_to(root)):sha256(p) for p in preserved}
    if before!=after: raise ValueError('Accepted baseline input/config/output bytes changed during Phase5')
    code_paths=[Path(__file__).parent/name for name in ('scenarios.py','lifecycle.py','enhanced.py')]+[root/'src/dc_locator/geography/sources/aqueduct_future.py',root/'src/dc_locator/schemas.py',root/'src/dc_locator/validation.py',root/'src/dc_locator/source_periods.py']
    manifest=dict(phase=5,status='awaiting_orchestrator_acceptance',created_at_utc=datetime.now(timezone.utc).isoformat(),
        grid_definition_id=metadata['grid_definition_id'],data_mode=metadata['data_mode'],geographic_cells=len(grid),enhanced_columns=len(enhanced.columns),
        provenance_rows=len(enhanced_prov),temporal_rows=len(temporal),lifecycle_rows=len(lifecycle),comparison_rows=len(comparison),
        annual_periods=facility.operating_lifetime_years,annual_years=[facility.target_opening_year,facility.target_opening_year+facility.operating_lifetime_years-1],
        temporal_kind_counts=temporal.period_kind.value_counts().to_dict(),climate_source_context_rows=len(climate),
        lifecycle_status_counts=lifecycle.status.value_counts().to_dict(),null_full_lifecycle_count=int(lifecycle.total_lifecycle_kg.isna().sum()),
        peak_working_set_bytes=peak_working_set_bytes(),memory_measurement='Windows OS process lifetime peak; development run only',
        baseline_preserved=before,baseline_repeat_artifacts_identical=baseline_repeat,profiles_predeclaration_sha256=sha256(declaration_path),
        configuration=config.model_dump(mode='json'),lifecycle_configuration=lifecycle_cfg,enhanced_packages=packages,
        code_hashes={str(p.relative_to(root)):sha256(p) for p in code_paths},
        warnings=['Development42-cell subset only; national runtime/peak RAM unvalidated',
            'Critical parcel/power/water/fiber evidence UNKNOWN; exploratory regions remain conditional',
            'Historical2023 carbon repeated2030..2054 only by explicit constant scenario assumption; not future grid forecast',
            'Aqueduct native trend windows are never individual operating-year observations',
            'Independent NASA model/ssp245 source context does not form coherent combined weather with every Aqueduct pathway',
            'Electricity-only partial lifetime carbon is not complete operating or lifecycle emissions',
            'Expanded native datasets informational; only predeclared future water binding changes ranking'])
    manifest['output_hashes']={str(p.relative_to(output)):sha256(p) for p in sorted(output.rglob('*')) if p.is_file() and p.name!='run_metadata.json'}
    (output/'run_metadata.json').write_text(json_text(manifest)+'\n',encoding='utf-8')
    return manifest


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config',default='configs/phase5.yaml');parser.add_argument('--output-dir',default='runs/phase5/integrated')
    args=parser.parse_args(argv);manifest=run_phase5(args.config,args.output_dir)
    print(json_text({k:manifest[k] for k in ('status','geographic_cells','enhanced_columns','provenance_rows','temporal_rows','lifecycle_rows','comparison_rows','null_full_lifecycle_count')}))


if __name__=='__main__':main()
