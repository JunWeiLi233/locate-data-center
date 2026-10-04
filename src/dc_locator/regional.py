"""National discovery followed by bounded, source-recomputed regional analysis.

This shared infrastructure composes geography and model APIs; selection policy
and decision mathematics remain in model modules, native parsing in geography.
"""
from __future__ import annotations

import gc
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

import geopandas as gpd
import numpy as np
import pandas as pd
import yaml
from pydantic import BaseModel, ConfigDict, Field, StrictInt, model_validator

from dc_locator.config import load_grid_config
from dc_locator.geography.boundary import load_conus_boundary
from dc_locator.geography.features import build_features
from dc_locator.geography.grid import generate_bounded_grid
from dc_locator.geography.sources.ingestion import file_digest
from dc_locator.io import write_geoparquet, write_parquet
from dc_locator.model.metrics import KEYS, ScoringProfile, clean, json_text, load_profile, profile_fingerprint
from dc_locator.model.physics import simulate
from dc_locator.model.regional_decision import select_refinement_parents as select_parents
from dc_locator.model.screening import screen
from dc_locator.paths import project_root
from dc_locator.pipeline import Pipeline, STAGES, digest_json, emit
from dc_locator.provenance import DataMode
from dc_locator.run_config import DeliveryConfig, load_source_document, resolve_path
from dc_locator.schemas import CandidateRegion, FacilityConfig


LAND_SEARCH_SCOPE = 'multi_cell_region'


class RegionalConfig(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False, strict=True)
    schema_version: Literal['3.0.0']
    delivery_version: Literal['phase9_regional_v1','phase11_national_fine_surface_v1']
    parent_config: str
    grid_config: str
    scoring_profile: str
    selection: Literal['representative_parent_cells','national_fine_surface','national_fine_region_parents']
    maximum_region_extent_km: float = Field(gt=0,le=100)
    maximum_refined_cells: StrictInt = Field(ge=1,le=200000)
    maximum_batch_cells: StrictInt = Field(ge=1,le=2500)
    basis: Literal['project_assumption']
    rationale: str = Field(min_length=1)

    @model_validator(mode='after')
    def budgets(self):
        if self.maximum_batch_cells>self.maximum_refined_cells or not self.rationale.strip():
            raise ValueError('Invalid regional resource budgets or rationale')
        if (self.selection in FINE_SELECTIONS)!=(self.delivery_version=='phase11_national_fine_surface_v1'):
            raise ValueError('National fine surface selection and the Phase 11 delivery version require each other')
        return self


FINE_SELECTIONS = ('national_fine_surface','national_fine_region_parents')
COVERAGE_WARNINGS = {
    'representative_parent_cells': 'Selected representative parent cells are refined in full; remaining shortlisted parent cells are unrefined. This is not exhaustive national 1 km analysis.',
    'national_fine_surface': 'Every national 1 km cell was valued on the national fine surface; the parents with the highest fine values were refined in full with recomputed native evidence. The surface applies no screening and unselected parents are unrefined, so this is not exhaustive national 1 km evidence.',
    'national_fine_region_parents': 'Every national 1 km cell was valued on the national fine surface; within each national discovery region the parent with the highest fine value was refined in full with recomputed native evidence. The surface applies no screening and unselected parents are unrefined, so this is not exhaustive national 1 km evidence.'}
PARENT_LABELS = {'representative_parent_cells': 'full representative parents',
                 'national_fine_surface': 'full parents selected by the national 1 km fine surface',
                 'national_fine_region_parents': 'full parents, the best national 1 km fine-surface parent of each national region'}


def _select_by_fine_surface(config, parent, parent_grid, parent_regions, grid_config, profile, identity, output, root, ratio, progress):
    """Phase 11: value every national 1 km cell in a child process, then choose parents by the declared mode."""
    from dc_locator.fine_surface import MANIFEST, build_isolated, stage_identity
    from dc_locator.model.fine_selection import select_parents_by_surface, select_region_best_parents
    folder = output/'national_fine_surface'
    summary, manifest = build_isolated(parent_grid=parent_grid, grid_config=grid_config,
        boundary_geometry=load_conus_boundary().boundary, source_inputs=load_source_document(parent.path(parent.config.core_source_inputs),root),
        profile=profile, performance=pd.read_parquet(parent.output/'site_performance.parquet'), folder=folder,
        identity=digest_json(stage_identity(identity)), source_checksums=parent.source_hashes, progress=progress)
    limit = int(config.maximum_refined_cells//ratio)
    if config.selection=='national_fine_region_parents':
        parents = select_region_best_parents(parent_grid, summary, parent_regions, pd.read_parquet(parent.output/'region_membership.parquet'))
    else:
        parents = select_parents_by_surface(parent_grid, summary, limit)
    record = dict(manifest=(folder/MANIFEST).relative_to(output).as_posix(), manifest_sha256=file_digest(folder/MANIFEST),
        stage_identity=manifest['stage_identity'], method_versions=manifest['method_versions'], valued_cells=manifest['cells'],
        scored_alternatives=manifest['scored_alternatives'], ranked_parent_windows=int(summary.dropna(subset=['best_fine_score']).parent_grid_id.nunique()),
        selection_limit=limit)
    return parents, record


def _validate_facility_land_extent(facility: FacilityConfig, config: RegionalConfig):
    """A bounded region cannot contain more land than its projected bounding box."""
    maximum_area_km2 = config.maximum_region_extent_km ** 2
    if facility.minimum_land_area_km2 > maximum_area_km2:
        raise ValueError(f'Minimum facility land area exceeds maximum regional bounding area ({maximum_area_km2:g} km2)')


def owned_output(root, output):
    root = Path(root).resolve()
    target = resolve_path(root, output)
    relative = target.relative_to(root) if target.is_relative_to(root) else None
    allowed = relative is not None and len(relative.parts)>1 and relative.parts[0] in {'runs','.pytest-work'}
    protected = relative is not None and relative.parts[0]=='runs' and (relative.parts[1].startswith(('phase','orchestrator_')) or relative.parts[1]=='example')
    if not allowed or protected:
        raise ValueError('Regional output must be an owned run or task scratch folder and preserve accepted evidence')
    return target


def _write(frame, path, schema, definition, *, version='1.0.0', geo=False):
    writer = write_geoparquet if geo else write_parquet
    writer(frame,path,schema_name=schema,schema_version=version,data_mode=DataMode.REAL,grid_definition_id=definition)


def _hashes(folder):
    return {p.relative_to(folder).as_posix():file_digest(p) for p in sorted(folder.rglob('*'))
            if p.is_file() and p.name not in {'run_metadata.json','checkpoint.json'}}


def _reconcile(wide, global_ranked):
    index = pd.MultiIndex.from_frame(wide[KEYS])
    values = global_ranked.set_index(KEYS).reindex(index)
    if len(values)!=len(wide) or values.grid_definition_id.isna().any():
        raise ValueError('Native batch does not match globally evaluated alternatives')
    result = wide.copy()
    for column in values:
        if column in result: result[column] = values[column].array
    return result


def run_regional(config_path, output, *, root=None, progress=None):
    """Return completed owned output, or resume checksum-bound batch evidence.

    Native parsing/physics stays bounded to one full parent at a time. Compact
    ranking and clustering cover the complete explicitly refined universe.
    """
    from dc_locator.model.regional_decision import prepare_batch, rank_compact, finalize_normalized
    from dc_locator.model.regions import cluster_regions, screen_region_land_support
    from dc_locator.model.enhanced import peak_working_set_bytes
    from dc_locator.geography.cached_outputs import reuse_regional_geography
    from dc_locator.regional_validation import validate_regional
    from dc_locator.reporting import INTERPRETATION, resource_diagnostics

    root = Path(root or project_root()).resolve()
    config_path = resolve_path(root, config_path)
    config = RegionalConfig.model_validate(yaml.safe_load(config_path.read_text(encoding='utf-8')))
    output = owned_output(root,output)
    if output.exists() and any(output.iterdir()) and not (output/'regional_binding.json').exists():
        raise ValueError('Nonempty output is not a bound regional run; choose a new folder')
    parent = Pipeline(config.parent_config, output/'national_discovery', root=root)
    if parent.config.data_mode!=DataMode.REAL or parent.config.study_area.lower() not in {'conus','national'}:
        raise ValueError('Regional refinement requires a real nationwide parent discovery')
    if parent.config.future['enabled'] or parent.config.expanded_features:
        raise ValueError('Initial regional revision requires the declared core-only current national source model')
    if any(c['category'] not in {'weights','screening'} or (c['category']=='screening' and c.get('mode')!='STRICT') for c in parent.config.validation.get('cases',[])):
        raise ValueError('Regional sensitivity supports declared weights and STRICT cases only')
    facility, designs, scenarios, requirements = parent.inputs()
    _validate_facility_land_extent(facility, config)
    grid_config = load_grid_config(resolve_path(root,config.grid_config))
    if grid_config.cell_size_m!=1000 or grid_config.origin_x_m!=-2500000 or grid_config.origin_y_m!=3400000:
        raise ValueError('Regional revision requires the approved fixed-origin 1 km grid')
    definition = grid_config.grid_definition_id()
    base_profile = load_profile(resolve_path(root,config.scoring_profile))
    if base_profile.region_selection.get('maximum_extent_km')!=config.maximum_region_extent_km:
        raise ValueError('Wrapper and bounded region profile extent disagree')
    # Preferences belong to the submitted parent; references and physical criteria
    # must match exactly before changing the region formation rule.
    parent_profile = parent.profile()
    if [m.model_dump() for m in base_profile.metrics]!=[m.model_dump() for m in parent_profile.metrics]:
        raise ValueError('Regional and national parent metric definitions differ')
    policy = base_profile.model_dump(mode='json')
    policy.update(weighting_method=parent_profile.weighting_method,user_weights=parent_profile.user_weights,
                  ahp_judgments=parent_profile.ahp_judgments)
    profile = ScoringProfile.model_validate(policy)
    fingerprint = profile_fingerprint(profile)
    binding = {'config':config.model_dump(mode='json'),'parent_identity':parent.identity,
               'land_search_scope':LAND_SEARCH_SCOPE,
               'wrapper_sha256':file_digest(config_path),'grid_config_sha256':file_digest(resolve_path(root,config.grid_config)),
               'profile_sha256':file_digest(resolve_path(root,config.scoring_profile)),'profile_fingerprint':fingerprint}
    identity = digest_json(binding)
    run_id = 'regional_refinement__'+identity[:16]
    completed = output/'run_metadata.json'
    if completed.is_file():
        old = json.loads(completed.read_text(encoding='utf-8'))
        if old.get('stage_identity')!=identity: raise ValueError('Regional output belongs to another revision; select a new folder')
        for name, sha in old['output_hashes'].items():
            if not (output/name).is_file() or file_digest(output/name)!=sha: raise ValueError('Regional result checksum mismatch: '+name)
        return output
    previous = output/'regional_binding.json'
    if previous.is_file() and json.loads(previous.read_text(encoding='utf-8'))!=binding:
        raise ValueError('Partial regional output belongs to another revision; preserve it and choose a new folder')
    output.mkdir(parents=True,exist_ok=True)
    emit(previous,binding)
    for stage in STAGES:
        if progress: progress(stage)
        getattr(parent,stage.replace('-','_'))()
    parent.execute('run')
    parent_grid = gpd.read_parquet(parent.path(parent.config.grid_path))
    parent_regions = gpd.read_parquet(parent.output/'candidate_regions.parquet')
    ratio = float(parent_grid.geometry.area.iloc[0]/grid_config.cell_size_m**2)
    fine_surface = None
    if config.selection in FINE_SELECTIONS:
        parents, fine_surface = _select_by_fine_surface(config,parent,parent_grid,parent_regions,grid_config,profile,identity,output,root,ratio,progress)
    else:
        parents = select_parents(parent_grid,parent_regions)
    parent_membership = pd.read_parquet(parent.output/'region_membership.parquet')
    shortlisted = sorted(set(parent_membership.grid_id))
    if len(parents)*ratio>config.maximum_refined_cells:
        raise ValueError('Selected full parents exceed the declared refined-cell budget; no silent truncation')
    if ratio>config.maximum_batch_cells:
        raise ValueError('A selected full parent exceeds the bounded batch budget')
    if 'national_region_ids_json' not in parents:
        parents['national_region_ids_json'] = [json_text(sorted(parent_regions.loc[parent_regions.representative_grid_id.eq(g),'region_id'])) for g in parents.grid_id]
    _write(parents,output/'refinement_windows.parquet','RegionalRefinementWindows',parent.config.grid_definition_id,
        version=('1.2.0' if config.selection=='national_fine_region_parents' else '1.1.0') if fine_surface else '1.0.0',geo=True)
    boundary = load_conus_boundary()
    source_inputs = load_source_document(parent.path(parent.config.core_source_inputs),root)
    parts, compact_parts, strict_parts, geo_parts = [], [], [], []
    summaries = []
    for position, window in enumerate(parents.itertuples(),1):
        if progress: progress('build-features')
        print(f'Refining parent {position}/{len(parents)}: {window.grid_id}',flush=True)
        parent.verify_binding()
        part = output/'parts'/window.grid_id
        part.mkdir(parents=True,exist_ok=True)
        checkpoint = part/'checkpoint.json'
        if checkpoint.is_file():
            record = json.loads(checkpoint.read_text(encoding='utf-8'))
            if record.get('stage_identity')!=identity or any(not (part/n).is_file() or file_digest(part/n)!=sha for n,sha in record['output_hashes'].items()):
                raise ValueError('Stale or damaged regional batch: '+window.grid_id)
            compact = pd.read_parquet(part/'compact.parquet')
            strict = pd.read_parquet(part/'strict_compact.parquet')
            geography = gpd.read_parquet(part/'us_grid_dataset.parquet')
            summary = json.loads((part/'screening_summary.json').read_text(encoding='utf-8'))
        else:
            grid, stats = generate_bounded_grid(grid_config,boundary,[window.geometry])
            if len(grid)>config.maximum_batch_cells or grid.empty: raise ValueError('Invalid bounded child grid size')
            _write(grid,part/'us_grid.parquet','GridCell',definition,version='1.1.0',geo=True)
            emit(part/'grid_summary.json',stats)
            geography = reuse_regional_geography(grid,source_inputs,parent.source_hashes,part,
                root=root,parent_grid_id=window.grid_id)
            if geography is None:
                geography = build_features(grid,source_inputs,part,study_geometry=boundary.boundary,
                    cache_dir=root/'data/interim/phase9_regional_v1/geography',prepare_per_tile=True,resume=True)
            provenance = pd.read_parquet(part/'feature_provenance.parquet')
            provenance.attrs.update(grid_definition_id=definition,data_mode='real')
            if progress: progress('screen')
            screening, eligible, summary = screen(geography,provenance,facility,designs,scenarios,requirements,mode=parent.config.screening_mode,land_search_scope=LAND_SEARCH_SCOPE)
            _write(screening,part/'screening_results.parquet','ScreeningResult',definition,version='1.2.0')
            _write(eligible,part/'screening_eligibility.parquet','ScreeningEligibility',definition,version='1.1.0')
            emit(part/'screening_summary.json',summary)
            if progress: progress('simulate')
            performance = simulate(geography,provenance,facility,designs,scenarios)
            _write(performance,part/'site_performance.parquet','SitePerformance',definition,version='1.1.0')
            batch = prepare_batch(geography,provenance,performance,eligible,profile,profile_hash=fingerprint,provenance_grid_definition_id=definition)
            # Fresh physical and screening recomputation precedes publication.
            fresh_performance = simulate(geography,provenance,facility,designs,scenarios)
            pd.testing.assert_frame_equal(performance,fresh_performance)
            fresh_screening, fresh_eligible, fresh_summary = screen(geography,provenance,facility,designs,scenarios,requirements,mode=parent.config.screening_mode,land_search_scope=LAND_SEARCH_SCOPE)
            pd.testing.assert_frame_equal(eligible,fresh_eligible)
            fresh_batch = prepare_batch(geography,provenance,fresh_performance,fresh_eligible,profile,profile_hash=fingerprint,provenance_grid_definition_id=definition)
            pd.testing.assert_frame_equal(batch['compact'],fresh_batch['compact'])
            del fresh_batch,fresh_performance,fresh_eligible,fresh_screening,fresh_summary
            strict_screening, strict_eligible, strict_summary = screen(geography,provenance,facility,designs,scenarios,requirements,mode='STRICT',land_search_scope=LAND_SEARCH_SCOPE)
            strict_batch = prepare_batch(geography,provenance,performance,strict_eligible,profile,profile_hash=fingerprint,provenance_grid_definition_id=definition)
            compact, strict = batch['compact'], strict_batch['compact']
            for frame,name,schema,version in [(compact,'compact','RegionalPreparedDecisionDataset','1.0.0'),
                    (strict,'strict_compact','RegionalPreparedDecisionDataset','1.0.0'),
                    (batch['ranked_cells'],'batch_ranked_cells','RegionalPreparedRankedCellDataset','1.0.0'),
                    (batch['normalized_metrics'],'batch_normalized_metrics','NormalizedMetricDataset','1.0.0')]:
                _write(frame,part/(name+'.parquet'),schema,definition,version=version)
            emit(part/'strict_screening_summary.json',strict_summary)
            emit(part/'batch_validation.json',dict(baseline_fresh_recomputation_exact=True,
                physics_exact=True,screening_exact=True,decision_exact=True,global_rank_pending=True))
            record = dict(stage_identity=identity,output_hashes=_hashes(part))
            emit(checkpoint,record)
            del batch,strict_batch,provenance,screening,eligible,performance,strict_eligible,strict_screening,grid,frame
        if geography.county_geoid_primary.isna().any() or geography.state_fips_primary.isna().any():
            raise ValueError('Refined child lacks required geographic attribution')
        compact_parts.append(compact);strict_parts.append(strict)
        geo_parts.append(geography[['grid_id','grid_definition_id','data_mode','county_geoid_all','row','col','cell_area_km2','study_area_intersection_km2','suitable_land_area_km2','geometry']].copy())
        summaries.append(summary)
        parts.append(dict(parent_grid_id=window.grid_id,path=part.relative_to(output).as_posix(),
            grid_path=(part/'us_grid.parquet').relative_to(output).as_posix(),cell_count=len(geography),output_hashes=record['output_hashes']))
        del geography,compact,strict
        gc.collect()
    if progress: progress('rank')
    if compact_parts:
        compact = pd.concat(compact_parts,ignore_index=True).sort_values(KEYS).reset_index(drop=True)
        strict = pd.concat(strict_parts,ignore_index=True).sort_values(KEYS).reset_index(drop=True)
        del compact_parts,strict_parts
        geography = gpd.GeoDataFrame(pd.concat(geo_parts,ignore_index=True),geometry='geometry',crs=5070).sort_values('grid_id').reset_index(drop=True)
        del geo_parts
        ranked = rank_compact(compact,profile,profile_hash=fingerprint)
        weight_info = {key:ranked.attrs[key] for key in ('weights','weighting_method','ahp_result','ahp_template')}
        if progress: progress('cluster')
        regions,membership = cluster_regions(geography,ranked,profile.region_selection,[m.column for m in profile.metrics],profile.profile_id,fingerprint)
        regions,membership,land_audit = screen_region_land_support(regions,membership,facility.minimum_land_area_km2)
    else:
        ranked = pd.read_parquet(parent.output/'ranked_cells.parquet').iloc[:0].copy()
        regions = parent_regions.iloc[:0].copy();regions['schema_version']='1.3.0'
        membership = parent_membership.iloc[:0].copy()
        geography = parent_grid.iloc[:0].copy()
        weight_info = {'weights':json.loads((parent.output/'weight_result.json').read_text(encoding='utf-8'))['weights'],
            'weighting_method':json.loads((parent.output/'weight_result.json').read_text(encoding='utf-8'))['weighting_method'],
            'ahp_result':json.loads((parent.output/'ahp_result.json').read_text(encoding='utf-8')) if (parent.output/'ahp_result.json').is_file() else None,
            'ahp_template':json.loads((parent.output/'ahp_template.json').read_text(encoding='utf-8')) if (parent.output/'ahp_template.json').is_file() else {}}
        regions,membership,land_audit = screen_region_land_support(regions,membership,facility.minimum_land_area_km2)
    _write(land_audit,output/'region_land_screening.parquet','RegionLandScreening',definition)
    _write(ranked,output/'ranked_cells.parquet','RegionalRankedCellDataset',definition)
    ranked.sort_values(['scenario_id','mcda_rank','grid_id','design_id'],na_position='last').to_csv(output/'ranking.csv',index=False,lineterminator='\n')
    _write(geography,output/'us_grid_dataset.parquet','RegionalGridIndex',definition,version='1.1.0',geo=True)
    representative_parts = {}
    representatives = set(regions.representative_grid_id)
    for part_info in parts:
        part = output/part_info['path']
        wide = pd.read_parquet(part/'batch_ranked_cells.parquet')
        final = _reconcile(wide,ranked)
        _write(final,part/'ranked_cells.parquet','RankedCellDataset',definition,version='1.1.0')
        normalized = finalize_normalized(pd.read_parquet(part/'batch_normalized_metrics.parquet'),ranked)
        _write(normalized,part/'normalized_metrics.parquet','NormalizedMetricDataset',definition)
        selected = final.loc[final.grid_id.isin(representatives)]
        rows = {tuple(row[k] for k in KEYS):row for row in clean(selected.to_dict('records'))}
        for i,row in regions.loc[regions.representative_grid_id.isin(selected.grid_id)].iterrows():
            key = (row.representative_grid_id,row.design_id,row.scenario_id)
            if key not in rows: raise ValueError('Regional representative lacks evaluated native evidence')
            regions.at[i,'representative_json'] = json_text(rows[key])
            representative_parts[row.representative_grid_id] = part_info['path']
        part_info['output_hashes'] = _hashes(part)
        del wide,final,normalized,selected,rows
    for row in regions.drop(columns='geometry').to_dict('records'): CandidateRegion.model_validate(clean(row))
    _write(regions,output/'candidate_regions.parquet','CandidateRegion',definition,version='1.3.0',geo=True)
    membership['grid_definition_id']=definition;membership['data_mode']='real'
    membership['profile_id']=profile.profile_id;membership['profile_fingerprint']=fingerprint
    _write(membership,output/'region_membership.parquet','RegionMembership',definition)
    features = json.loads(regions.to_crs(4326).to_json(drop_id=True))['features'] if len(regions) else []
    emit(output/'candidate_regions.geojson',dict(type='FeatureCollection',features=features,
         dc_locator=dict(schema='CandidateRegion',schema_version='1.3.0',grid_definition_id=definition,data_mode='real',
             maximum_extent_km=config.maximum_region_extent_km,interpretation=INTERPRETATION)))
    if progress: progress('validate')
    if len(ranked):
        report = validate_regional(compact,strict,ranked,membership,representatives,profile,parent.config.validation,output,run_id,DataMode.REAL)
        del compact,strict
    else:
        report = dict(validation_scope='empty_refined_universe',runtime_contracts=dict(status='PASSED'),
                      reason='No evaluated national representative qualifies; no fine coverage or winner invented.')
        emit(output/'validation_report.json',report)
        for name in ('sensitivity_results','alternative_rank_ranges'):_write(pd.DataFrame(),output/(name+'.parquet'),'RegionalEmptyDataset',definition)
    child = dict(parent.config.model_dump(mode='json'),schema_version='2.2.0',delivery_version=config.delivery_version,
        study_area='regional_refinement',grid_config=config.grid_config,grid_path=str(output/'us_grid_dataset.parquet'),
        grid_definition_id=definition,scoring_profile=config.scoring_profile,maximum_model_cells=config.maximum_batch_cells)
    policy_paths = [config_path,resolve_path(root,config.grid_config),resolve_path(root,config.scoring_profile)]
    policy_hashes = {str(path):file_digest(path) for path in policy_paths}
    snapshot_files = json.loads((parent.output/'config_snapshot.json').read_text(encoding='utf-8'))['files']
    snapshot_files.update({str(path):path.read_text(encoding='utf-8') for path in policy_paths})
    emit(output/'config_snapshot.json',dict(run=child,regional=config.model_dump(mode='json'),files=snapshot_files))
    emit(output/'profile_snapshot.json',dict(status='DECLARED_BEFORE_CURRENT_RANKING',profile=profile.model_dump(mode='json'),resolved_profile_fingerprint=fingerprint))
    emit(output/'weight_result.json',dict(weights=weight_info['weights'],weighting_method=weight_info['weighting_method']))
    emit(output/('ahp_result.json' if weight_info['ahp_result'] else 'ahp_template.json'),weight_info['ahp_result'] or weight_info['ahp_template'])
    summary = {'n_alternatives':len(ranked),'rankable':int(ranked.rankable.sum()),'hard_fail':int(ranked.hard_fail.sum()),'critical_unknown':int(ranked.critical_unknown.sum()),'scope':'all evaluated refined children','land_search_scope':LAND_SEARCH_SCOPE}
    summary['region_land_outcomes'] = land_audit.outcome.value_counts().sort_index().to_dict()
    emit(output/'screening_summary.json',summary)
    shutil.copy2(parent.output/'source_inventory.json',output/'source_inventory.json')
    fine_coverage = {'scope':'all evaluated refined children','input_cells':len(geography),'sources':{}}
    for part_info in parts:
        coverage = json.loads((output/part_info['path']/'coverage_report.json').read_text(encoding='utf-8'))
        for source, values in coverage['sources'].items():
            entry = fine_coverage['sources'].setdefault(source,dict(implemented=values['implemented'],acquired=values['acquired'],
                analyzed=False,analyzed_cells=0,metric_nonmissing_cells={},coverage_min=None,coverage_max=None))
            entry['analyzed'] |= values['analyzed']
            entry['analyzed_cells'] += values['analyzed_cells']
            for metric,count in values['metric_nonmissing_cells'].items():
                entry['metric_nonmissing_cells'][metric] = entry['metric_nonmissing_cells'].get(metric,0)+count
            for key,aggregate in [('coverage_min',min),('coverage_max',max)]:
                value = values[key]
                if value is not None: entry[key] = value if entry[key] is None else aggregate(entry[key],value)
    for entry in fine_coverage['sources'].values():
        complete = all(count==len(geography) for count in entry['metric_nonmissing_cells'].values())
        entry['status'] = 'READY' if complete and (entry['coverage_min'] is None or entry['coverage_min']>=1-1e-6) else 'PARTIAL' if entry['acquired'] else 'BLOCKED'
    emit(output/'source_coverage.json',fine_coverage)
    emit(output/'source_data_manifest.json',dict(scope='regional part manifests with parent acquisition lineage',
        source_checksums=parent.source_hashes,parts={part['parent_grid_id']:{'path':part['path']+'/data_manifest.json',
            'sha256':file_digest(output/part['path']/'data_manifest.json')} for part in parts}))
    refined_area = float(geography.study_area_intersection_km2.sum())
    shortlist_area = float(parent_grid.loc[parent_grid.grid_id.isin(shortlisted),'study_area_intersection_km2'].sum())
    catalog = dict(schema_version='1.2.0' if fine_surface else '1.1.0',analysis_level='regional',parent_run_path=parent.output.relative_to(root).as_posix(),
        parent_run_id=parent.run_id,parent_stage_identity=parent.identity,grid_definition_id=definition,cell_size_m=1000,
        refined_cells=len(geography),national_cells=len(parent_grid),shortlisted_parent_cells=len(shortlisted),
        refined_parent_cells=len(parents),refined_area_km2=refined_area,shortlisted_parent_area_km2=shortlist_area,
        maximum_region_extent_km=config.maximum_region_extent_km,ranking_universe='all_evaluated_refined_alternatives',
        land_search_scope=LAND_SEARCH_SCOPE,
        selection=config.selection,selection_basis=config.basis,selection_rationale=config.rationale,
        parent_footprints_path='refinement_windows.parquet',parts=parts,representative_parts=representative_parts,
        parent_output_hashes=json.loads((parent.output/'run_metadata.json').read_text(encoding='utf-8'))['output_hashes'],
        coverage_warning=COVERAGE_WARNINGS[config.selection])
    if fine_surface:
        catalog['national_fine_surface'] = fine_surface
    emit(output/'regional_catalog.json',catalog)
    parent.verify_binding()
    if file_digest(config_path)!=binding['wrapper_sha256'] or file_digest(resolve_path(root,config.scoring_profile))!=binding['profile_sha256'] or file_digest(resolve_path(root,config.grid_config))!=binding['grid_config_sha256']:
        raise ValueError('Regional policy changed during execution')
    if len(regions):
        spans = regions.geometry.bounds
        if ((spans.maxx-spans.minx)>config.maximum_region_extent_km*1000+1e-6).any() or ((spans.maxy-spans.miny)>config.maximum_region_extent_km*1000+1e-6).any():
            raise ValueError('A regional polygon exceeds the declared projected extent')
    if (ranked.rankable & ranked.hard_fail).any():raise ValueError('Hard failure was ranked')
    report_text = f'# Regional investigation evidence\n\n{INTERPRETATION}\n\n{len(parent_grid)} national discovery cells; {len(parents)} {PARENT_LABELS[config.selection]} refined into {len(geography)} 1 km cells. {len(regions)} bounded search regions. Maximum projected span: {config.maximum_region_extent_km:g} km per axis.\n\n{catalog["coverage_warning"]}\n\nEvery fine cell uses recomputed native evidence, screening and physics. Ranks and Pareto labels describe the complete evaluated refined universe, separately by external scenario. Parcel zoning, contiguous obtainable land, verified utility capacity, water commitments and diverse fiber remain unverified. Native source resolution is not improved by finer analytical cells.\n'
    (output/'recommendation_report.md').write_text(report_text,encoding='utf-8')
    (output/'validation_report.md').write_text('# Regional validation\n\n'+json.dumps(clean(report),indent=2)+'\n',encoding='utf-8')
    hashes = _hashes(output)
    for stage in STAGES:
        emit(output/'stage_manifests'/(stage+'.json'),dict(stage=stage,stage_identity=identity,
            delivery_version=config.delivery_version,output_hashes={'regional_catalog.json':hashes['regional_catalog.json']},
            details=dict(refined_cells=len(geography),validated_current_run=True)))
    hashes = _hashes(output)
    metadata = dict(schema_version='2.0.0',delivery_version=config.delivery_version,run_id=run_id,
        created_at_utc=datetime.now(timezone.utc).isoformat(),stage_identity=identity,data_mode='real',study_area='regional_refinement',
        geographic_cells=len(geography),grid_definition_id=definition,configuration=child,
        scope=dict(scope='regional_refinement',data_mode='real',geographic_cells=len(geography),grid_definition_id=definition),
        completed_current_stages=list(STAGES),actual_working_code_sha256=parent.model_hashes,
        config_hashes={**parent.config_hashes,**policy_hashes},source_checksums=parent.source_hashes,
        source_versions_and_access=parent.source_document.get('declared_sources',{}),environment=parent.environment,
        output_hashes=hashes,observed_process_lifetime_peak_working_set_bytes=peak_working_set_bytes(),
        resource_diagnostics=resource_diagnostics(root),warnings=[catalog['coverage_warning'],
            '1 km analytical cells do not establish industrial zoning, parcels, utility capacity, water or fiber commitments.'],
        interpretation=INTERPRETATION)
    if metadata['observed_process_lifetime_peak_working_set_bytes']>4*1024**3:
        raise ValueError('Regional process exceeded the declared 4 GiB resource bound; no completion published')
    emit(completed,metadata)
    return output
