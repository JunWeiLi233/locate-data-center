"""Phase 4 file runner: preserved physics → declared policy → search regions.

Run ``python -m dc_locator.model.decision --help``. Geography and Phase 3
inputs are read-only. This module is a temporary executable API until Phase7.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from datetime import datetime,timezone
from pathlib import Path

import pandas as pd

from dc_locator.io import read_geoparquet,read_parquet,read_parquet_metadata,write_parquet
from dc_locator.model.metrics import KEYS,ScoringProfile,assemble_metrics,clean,json_text,load_profile
from dc_locator.model.normalization import normalize_values
from dc_locator.model.mcda import equal_weights,user_weights,hierarchical_weights,score_alternatives
from dc_locator.model.pareto import pareto_frontier
from dc_locator.model.regions import cluster_regions
from dc_locator.provenance import DataMode
from dc_locator.schemas import CandidateRegion,DecisionResult,FeatureMetadata


def sha256(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''): h.update(block)
    return h.hexdigest()


def _read_inputs(paths):
    schemas = [('GeographicFeatureDataset',(1,1,0)),('FeatureMetadata',(1,1,0)),('SitePerformance',(1,1,0)),('ScreeningEligibility',(1,0,0))]
    tables,metadata = [],[]
    for i,(path,(schema,minimum)) in enumerate(zip(paths,schemas)):
        meta = read_parquet_metadata(path)
        match = re.fullmatch(r'(\d+)\.(\d+)\.(\d+)',meta.get('schema_version',''))
        version = tuple(map(int,match.groups())) if match else None
        if meta.get('schema') != schema or version is None or version[0] != minimum[0] or version < minimum: raise ValueError('Incompatible file schema/version: '+schema)
        table = read_geoparquet(path) if i == 0 else read_parquet(path)
        for field in ('grid_definition_id','data_mode'):
            if not meta.get(field): raise ValueError('Missing file identity: '+field)
            if field in table and (table[field].nunique() != 1 or table[field].iloc[0] != meta[field]): raise ValueError('Row/file identity mismatch: '+field)
        if 'schema_version' in table and not table.schema_version.eq(meta['schema_version']).all(): raise ValueError('Row/file schema version mismatch')
        tables.append(table);metadata.append(meta)
        table.attrs.update(meta)
    for field in ('grid_definition_id','data_mode'):
        if len({m[field] for m in metadata}) != 1: raise ValueError('Incompatible file '+field)
    for row in tables[1].to_dict('records'): FeatureMetadata.model_validate(clean(row))
    return tables,metadata[0]


def _freeze_profile(profile_path,profile,output_dir,declaration_path):
    fingerprint = sha256(profile_path)
    declaration = None
    if declaration_path is not None:
        declaration = json.loads(Path(declaration_path).read_text(encoding='utf-8'))
        if declaration.get('sha256') != fingerprint or ScoringProfile.model_validate(declaration.get('profile')).model_dump(mode='json') != profile.model_dump(mode='json') or declaration.get('status') != 'PREDECLARED_BEFORE_FIRST_RANKING': raise ValueError('Profile changed after predeclaration')
    elif profile.profile_id == 'reduced_geography_annual_v1':
        accepted = Path(__file__).resolve().parents[3]/'docs/phase_records/phase4_profile_predeclared.json'
        if accepted.is_file(): return _freeze_profile(profile_path,profile,output_dir,accepted)
    if declaration is None:
        declaration = dict(status='PREDECLARED_BEFORE_FIRST_RANKING',declared_at_utc=datetime.now(timezone.utc).isoformat(),sha256=fingerprint,profile=profile.model_dump(mode='json'),policy='New/custom profile frozen before this run; no claim of prior independent acceptance')
    (output_dir/'profile_snapshot.json').write_text(json_text(declaration)+'\n',encoding='utf-8')
    return fingerprint


def _weights(profile,frame):
    ahp_result = None
    method = profile.weighting_method
    if method == 'user': weights = hierarchical_weights(profile,profile.user_weights or {}) if profile.weight_scope == 'groups' else user_weights(profile.user_weights or {},profile.metric_ids)
    elif method == 'ahp' and profile.ahp_judgments:
        from dc_locator.model.ahp import evaluate_ahp
        judgments = profile.ahp_judgments
        ahp_result = evaluate_ahp(judgments['criteria_ids'],judgments['matrix'],active_criteria_ids=profile.weight_criterion_ids,consistency_threshold=profile.ahp['consistency_threshold'],reciprocal_tolerance=profile.ahp['reciprocal_tolerance'],provisional_override=judgments.get('provisional_override'))
        weights = hierarchical_weights(profile,ahp_result['weights']) if profile.weight_scope == 'groups' else ahp_result['weights']
        ahp_result['global_leaf_weights'] = weights
        ahp_result['weight_scope'] = profile.weight_scope
        ahp_result['local_weights'] = {m.metric_id:m.local_weight for m in profile.metrics}
    else:
        weights = equal_weights(profile)
        method = 'equal'
    template = None
    if ahp_result is None:
        definitions = [dict(metric_id=m.metric_id,definition=m.definition,unit=m.unit,direction=m.direction,local_weight=m.local_weight,reference_bounds=[m.reference_low,m.reference_high],observed_performance_range=[clean(frame['raw_'+m.metric_id].min()),clean(frame['raw_'+m.metric_id].max())]) for m in profile.metrics]
        criteria = [dict(criterion_id=g['group_id'],definition=g['label'],subcriteria=[d for d,m in zip(definitions,profile.metrics) if m.group_id == g['group_id']]) for g in profile.groups] if profile.weight_scope == 'groups' else definitions
        n = len(profile.weight_criterion_ids)
        template = dict(status='UNSUPPLIED',weight_scope=profile.weight_scope,criteria_ids=profile.weight_criterion_ids,elicitation_scale='1–9 intensities and reciprocals; ratios remain accepted for tests',matrix=[[1 if i==j else None for j in range(n)] for i in range(n)],criteria=criteria,instructions='Supply every off-diagonal judgment and reciprocal. Parent preferences multiply fixed local subcriterion weights. Comparisons are criteria preferences, not pairwise site comparisons. No expert judgments were generated.')
    return weights,method,ahp_result,template


def decide(geography,provenance,performance,eligibility,profile,*,profile_hash,provenance_grid_definition_id=None):
    """Pure table API with strict row schemas and provenance evidence checks."""
    frame,normalized = assemble_metrics(geography,provenance,performance,eligibility,profile,provenance_grid_definition_id=provenance_grid_definition_id)
    for metric in profile.metrics:
        values,flags = normalize_values(frame[metric.metric_id],metric.reference_low,metric.reference_high,metric.direction)
        frame[metric.metric_id] = values
        selected = normalized.metric_id == metric.metric_id
        normalized.loc[selected,'normalized_value'] = values
        normalized.loc[selected,'normalization_status'] = flags
        normalized.loc[selected,'reference_low'] = metric.reference_low
        normalized.loc[selected,'reference_high'] = metric.reference_high
        normalized.loc[selected,'direction'] = metric.direction
        normalized.loc[selected,'normalization_method'] = 'fixed_linear_clipped_0_100'
        normalized.loc[selected,'constant_observed_column'] = frame.loc[frame[metric.metric_id].notna(),metric.metric_id].nunique() <= 1
    weights,method,ahp_result,template = _weights(profile,frame)
    usable = ahp_result is None or ahp_result['status'] != 'REVIEW_REQUIRED'
    ranked = score_alternatives(frame,profile.metric_ids,weights,weights_usable=usable)
    raw = ranked.copy()
    for metric in profile.metrics: raw[metric.metric_id] = raw['raw_'+metric.metric_id]
    # Pareto is a physical comparison, independent of whether preference weights passed review.
    raw['rankable'] = ranked[profile.metric_ids].notna().all(axis=1) & ranked.eligible & ~ranked.hard_fail & ~((ranked['mode'] == 'STRICT') & ranked.critical_unknown)
    ranked['pareto_comparable'] = raw['rankable']
    pareto = pareto_frontier(raw,profile.metric_ids,[m.direction for m in profile.metrics],[profile.pareto['absolute_tolerances'][m.metric_id] for m in profile.metrics],relative_tolerance=profile.pareto['relative_tolerance'])
    for column in ('is_pareto_optimal','pareto_status','pareto_rank'): ranked[column] = pareto[column]
    ranked['schema_version'] = '1.1.0'
    ranked['profile_id'] = profile.profile_id
    ranked['profile_fingerprint'] = profile_hash
    ranked['weighting_method'] = method
    ranked['ahp_status'] = ahp_result['status'] if ahp_result else 'NOT_APPLICABLE'
    decision_fields = set(DecisionResult.model_fields)
    for row in ranked.to_dict('records'):
        canonical = {k:clean(v) for k,v in row.items() if k in decision_fields}
        canonical['weights_used'] = weights
        canonical['contribution_by_metric'] = json.loads(row['contribution_by_metric_json'])
        DecisionResult.model_validate(canonical)
    normalized['schema_version'] = '1.0.0'
    normalized['profile_id'] = profile.profile_id
    normalized['profile_fingerprint'] = profile_hash
    normalized['grid_definition_id'] = str(geography.grid_definition_id.iloc[0])
    normalized['data_mode'] = str(geography.data_mode.iloc[0])
    normalized = normalized.sort_values(KEYS+['metric_id']).reset_index(drop=True)
    physical = [m.column for m in profile.metrics]
    for metric in profile.metrics:
        if metric.table == 'geography': ranked[metric.column] = ranked.grid_id.map(geography.set_index('grid_id')[metric.column])
    regions,membership = cluster_regions(geography,ranked,profile.region_selection,physical,profile.profile_id,profile_hash)
    for row in regions.drop(columns='geometry').to_dict('records'): CandidateRegion.model_validate(clean(row))
    for table in (membership,):
        table['profile_id'] = profile.profile_id;table['profile_fingerprint'] = profile_hash
        table['grid_definition_id'] = str(geography.grid_definition_id.iloc[0]);table['data_mode'] = str(geography.data_mode.iloc[0])
    pareto_columns = KEYS+['profile_id','profile_fingerprint','grid_definition_id','data_mode','eligible','conditional','hard_fail','critical_unknown','mode','rankable','pareto_comparable','pareto_status','is_pareto_optimal','pareto_rank']+['raw_'+m.metric_id for m in profile.metrics]
    pareto_results = ranked[pareto_columns].copy()
    return dict(normalized_metrics=normalized,ranked_cells=ranked,pareto_results=pareto_results,candidate_regions=regions,region_membership=membership,weights=weights,weighting_method=method,ahp_result=ahp_result,ahp_template=template)


def run_phase4(geography_path,provenance_path,performance_path,eligibility_path,profile_path,output_dir,*,declaration_path=None):
    """Write real or quarantined synthetic run outputs, including valid empty sets."""
    paths = list(map(Path,[geography_path,provenance_path,performance_path,eligibility_path]))
    tables,metadata = _read_inputs(paths)
    profile = load_profile(profile_path)
    output_dir = Path(output_dir);output_dir.mkdir(parents=True,exist_ok=True)
    fingerprint = _freeze_profile(Path(profile_path),profile,output_dir,declaration_path)
    result = decide(*tables,profile,profile_hash=fingerprint)
    mode = DataMode(metadata['data_mode'])
    for key,schema,version in [('normalized_metrics','NormalizedMetricDataset','1.0.0'),('pareto_results','ParetoDataset','1.0.0'),('ranked_cells','RankedCellDataset','1.1.0'),('region_membership','RegionMembership','1.0.0')]:
        write_parquet(result[key],output_dir/(key+'.parquet'),schema_name=schema,schema_version=version,data_mode=mode,grid_definition_id=metadata['grid_definition_id'])
    regions = result['candidate_regions'].to_crs(4326)
    features = json.loads(regions.to_json(drop_id=True))['features'] if len(regions) else []
    geojson = dict(type='FeatureCollection',features=features,dc_locator=dict(schema='CandidateRegion',schema_version='1.1.0',data_mode=mode.value,grid_definition_id=metadata['grid_definition_id'],profile_id=profile.profile_id,profile_fingerprint=fingerprint,created_by='dc_locator.model.decision'))
    (output_dir/'candidate_regions.geojson').write_text(json_text(geojson)+'\n',encoding='utf-8')
    result['ranked_cells'].sort_values(['scenario_id','mcda_rank',*KEYS],na_position='last').to_csv(output_dir/'ranking.csv',index=False,lineterminator='\n')
    filename = 'ahp_result.json' if result['ahp_result'] else 'ahp_template.json'
    (output_dir/filename).write_text(json_text(result['ahp_result'] or result['ahp_template'])+'\n',encoding='utf-8')
    stale = output_dir/('ahp_template.json' if result['ahp_result'] else 'ahp_result.json')
    if stale.is_file(): stale.unlink()
    try: revision = subprocess.run(['git','rev-parse','HEAD'],capture_output=True,text=True,check=True).stdout.strip()
    except (OSError,subprocess.CalledProcessError): revision = None
    code_paths = list(Path(__file__).parent.glob('*.py'))+[Path(__file__).resolve().parents[1]/'schemas.py',Path(__file__).resolve().parents[1]/'io.py']
    manifest = dict(schema_version='1.0.0',phase=4,created_at_utc=datetime.now(timezone.utc).isoformat(),code_revision=revision,code_hashes={p.name:sha256(p) for p in sorted(code_paths)},data_mode=mode.value,grid_definition_id=metadata['grid_definition_id'],profile_id=profile.profile_id,profile_fingerprint=fingerprint,profile=profile.model_dump(mode='json'),input_hashes={str(p):sha256(p) for p in paths},weights=result['weights'],weighting_method=result['weighting_method'],ahp_status=result['ahp_result']['status'] if result['ahp_result'] else 'NOT_APPLICABLE',analyzed_scope='Provided development/subset grid; source coverage and critical screening uncertainties retained',geographic_cells=len(tables[0]),alternatives=len(result['ranked_cells']),rankable=int(result['ranked_cells'].rankable.sum()),conditional_ranked=int((result['ranked_cells'].rankable & result['ranked_cells'].conditional).sum()),candidate_regions=len(regions),region_memberships=len(result['region_membership']),rank_status_counts=result['ranked_cells'].rank_status.value_counts().to_dict(),source_valid_counts=result['normalized_metrics'].groupby('metric_id').source_valid.sum().to_dict(),warnings=['Development-only conditional investigation results; no proven buildable parcel','Historical-static annual electricity emissions; no future/lifecycle claim','Equal groups are a transparent project policy, not verified criterion importance','Critical parcel/power/water/fiber unknowns retained','National runtime and peak RAM are unvalidated'],output_hashes={p.name:sha256(p) for p in sorted(output_dir.iterdir()) if p.is_file() and p.name not in {'run_metadata.json'}})
    (output_dir/'run_metadata.json').write_text(json_text(manifest)+'\n',encoding='utf-8')
    return result,manifest


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--geography',default='data/processed/us_grid_dataset.parquet')
    parser.add_argument('--provenance',default='data/processed/feature_provenance.parquet')
    parser.add_argument('--performance',default='runs/phase3/exploratory/site_performance.parquet')
    parser.add_argument('--eligibility',default='runs/phase3/exploratory/screening_eligibility.parquet')
    parser.add_argument('--profile',default='configs/scoring_profile.yaml')
    parser.add_argument('--output-dir',default='runs/phase4/exploratory')
    args = parser.parse_args(argv)
    _,manifest = run_phase4(args.geography,args.provenance,args.performance,args.eligibility,args.profile,args.output_dir)
    print(json_text({k:manifest[k] for k in ('profile_id','profile_fingerprint','alternatives','rankable','conditional_ranked','candidate_regions','region_memberships')}))


if __name__ == '__main__': main()
