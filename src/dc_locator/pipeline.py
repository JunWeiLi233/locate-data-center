"""Delivery orchestration over accepted geographic and scientific APIs.

Acquisition is separate. Every stage verifies native inputs and upstream output
identities; no real-data execution falls back to synthetic data.
"""
from __future__ import annotations

import hashlib
import importlib.metadata
import json
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import shapely

from dc_locator.config import load_facility_config
from dc_locator.geography.sources.ingestion import file_digest
from dc_locator.io import read_parquet_metadata,write_geoparquet,write_parquet
from dc_locator.model.cooling import load_cooling_designs,load_physical_scenarios
from dc_locator.model.decision import decide
from dc_locator.model.metrics import clean,json_text,load_profile,profile_fingerprint,ScoringProfile
from dc_locator.model.screening import load_requirements,screen
from dc_locator.model.physics import simulate
from dc_locator.paths import project_root
from dc_locator.provenance import DataMode
from dc_locator.run_config import load_delivery_config,resolve_path,load_source_document,preflight,check_table_identity
from dc_locator.schemas import FacilityConfig,GridCell,CandidateRegion
from dc_locator.validation import validate_feature_provenance


STAGES=('ingest','build-features','screen','simulate','rank','cluster','validate')
TABLES={'normalized_metrics':('NormalizedMetricDataset','1.0.0'),'pareto_results':('ParetoDataset','1.0.0'),
        'ranked_cells':('RankedCellDataset','1.1.0'),'region_membership':('RegionMembership','1.0.0')}


def digest_json(value):
    return hashlib.sha256(json_text(clean(value)).encode()).hexdigest()


def emit(path,value):
    Path(path).parent.mkdir(parents=True,exist_ok=True)
    Path(path).write_text(json_text(clean(value))+'\n',encoding='utf-8')


def substantive_source_manifest(manifest):
    """Keep source/content evidence independent of cumulative cache accounting."""
    import copy
    result=copy.deepcopy(manifest)
    expanded=result.get('expanded',{})
    for key in ('raw_total_bytes_including_manifests','interim_total_bytes_including_extracted_copies'):
        expanded.pop(key,None)
    return result


def verify_acquisition_evidence(document,root,source_hashes):
    """Bind embedded acquisition identities to the checksum-verified native log."""
    def records(value):
        if isinstance(value,dict):
            if 'manifest' in value and 'path' in value and 'sha256' in value:yield value
            for item in value.values():yield from records(item)
        elif isinstance(value,list):
            for item in value:yield from records(item)
    verified=[]
    for record in records(document):
        manifest=resolve_path(root,record['manifest']);path=resolve_path(root,record['path'])
        if str(manifest) not in source_hashes or str(path) not in source_hashes:raise ValueError('Acquisition evidence references an unbound source/log')
        entries=json.loads(manifest.read_text(encoding='utf-8'))
        if isinstance(entries,dict):entries=entries.get('files',entries.get('downloads',entries.get('entries',[])))
        matches=[entry for entry in entries if resolve_path(root,entry.get('path',''))==path]
        keys=('sha256','bytes','url','source_id','version','request_identity','request_key','bounds_4326','parameters')
        if not any(all(clean(entry.get(key))==clean(record[key]) for key in keys if key in record) for entry in matches):
            raise ValueError('Acquisition request/source/version identity mismatch: '+str(path))
        verified.append({'path':str(path),'manifest':str(manifest),'source_id':record.get('source_id'),'native_version':record.get('version'),'request_identity':record.get('request_identity',record.get('request_key'))})
    return verified


def environment_identity():
    import platform
    packages={name:importlib.metadata.version(name) for name in ('numpy','pandas','geopandas','shapely','pyproj','rasterio','pyogrio','pyarrow','pydantic','PyYAML')}
    return {'python':platform.python_version(),'platform':platform.platform(),'packages':packages}


class Pipeline:
    """One configured delivery revision, reusable by individual CLI stages."""
    def __init__(self,config_path,output,*,root=None):
        self.root=Path(root or project_root()).resolve()
        self.config_path=resolve_path(self.root,config_path)
        self.config=load_delivery_config(self.config_path)
        self.output=resolve_path(self.root,output)
        self.scope=preflight(self.config,self.root,self.output)
        if self.output.exists() and any(self.output.iterdir()) and not list((self.output/'stage_manifests').glob('*.json')):
            raise ValueError('Nonempty output has no matching delivery stage manifests; preserve it and choose a new output directory')
        self.output.mkdir(parents=True,exist_ok=True)
        self.path=lambda value:resolve_path(self.root,value)
        self.source_document=load_source_document(self.path(self.config.local_sources),self.root)
        self.source_hashes={}
        for record in self.source_document['files']:
            path=self.path(record['path'])
            if not path.exists():raise FileNotFoundError('Required acquired input missing: '+str(path))
            size=sum(f.stat().st_size for f in path.rglob('*') if f.is_file()) if path.is_dir() else path.stat().st_size
            actual=file_digest(path)
            if actual!=record['sha256'] or size!=record['bytes']:
                raise ValueError('Source bytes/checksum mismatch: '+str(path))
            self.source_hashes[str(path)]=actual
        references=[self.config_path,self.path(self.config.grid_path),self.path(self.config.grid_config),self.path(self.config.source_registry),self.path(self.config.local_sources)]
        for field in ('core_source_inputs','expanded_source_inputs','aqueduct_source_input','fixture_geography','fixture_provenance','facility','cooling_designs','physical_scenarios','constraints','scoring_profile','ahp_input'):
            value=getattr(self.config,field)
            if value:references.append(self.path(value))
        if self.config.future['enabled']:
            references+=[self.path(self.config.future[k]) for k in ('profile_declaration','lifecycle')]
            references+=[self.path(self.config.future['profiles_directory'])/f'{p}_{y}.yaml' for p in self.config.future['pathways'] for y in self.config.future['milestone_years']]
        self.config_hashes={str(p):file_digest(p) for p in sorted(set(references))}
        self.acquisition_checks=[]
        for field in ('core_source_inputs','expanded_source_inputs','aqueduct_source_input'):
            value=getattr(self.config,field)
            if not value:continue
            document=load_source_document(self.path(value),self.root)
            self.acquisition_checks+=verify_acquisition_evidence(document,self.root,self.source_hashes)
            if document.get('expected_sha256'):
                if any(self.source_hashes.get(str(self.path(p)))!=document['expected_sha256'] for p in document.get('paths',{}).values()):raise ValueError('Configured native archive checksum identity mismatch')
            def bound_paths(obj):
                if isinstance(obj,dict):
                    for key,item in obj.items():
                        if key=='paths':yield from item.values()
                        elif key=='interpretation_verification_path':yield item
                        else:yield from bound_paths(item)
                elif isinstance(obj,list):
                    for item in obj:yield from bound_paths(item)
            for value in bound_paths(document):
                if str(self.path(value)) not in self.source_hashes:
                    raise ValueError('Native input is not registered with bytes/checksum evidence: '+str(value))
        self.model_hashes={str(p.relative_to(self.root)):file_digest(p) for p in sorted((self.root/'src/dc_locator').rglob('*.py'))}
        for name in ('requirements.lock.txt','pyproject.toml'):
            self.model_hashes[name]=file_digest(self.root/name)
        self.environment=environment_identity()
        self.identity=digest_json({'delivery_version':self.config.delivery_version,'config':self.config.model_dump(mode='json'),
            'config_hashes':self.config_hashes,'model_hashes':self.model_hashes,'source_hashes':self.source_hashes,
            'grid_sha256':file_digest(self.path(self.config.grid_path)),'environment':self.environment})
        self.run_id=self.config.run_name+'__'+self.identity[:16]
        self.cache_hits=[]
        for previous in sorted((self.output/'stage_manifests').glob('*.json')):
            if json.loads(previous.read_text(encoding='utf-8')).get('stage_identity')!=self.identity:
                raise ValueError('Output belongs to another model/config/source revision; choose a new output directory instead of rebinding stale results')

    def _manifest(self,stage):return self.output/'stage_manifests'/f'{stage}.json'

    def verify_binding(self):
        current=set(str(p.relative_to(self.root)) for p in (self.root/'src/dc_locator').rglob('*.py'))|{'requirements.lock.txt','pyproject.toml'}
        if current!=set(self.model_hashes) or any(file_digest(self.root/name)!=sha for name,sha in self.model_hashes.items()):
            raise ValueError('Working model changed during current-run execution; use a new delivery run')
        if any(file_digest(path)!=sha for path,sha in self.config_hashes.items()):
            raise ValueError('Configured input changed during current-run execution')
        if any(file_digest(path)!=sha for path,sha in self.source_hashes.items()):
            raise ValueError('Acquired source changed during current-run execution')
        if environment_identity()!=self.environment:raise ValueError('Environment changed during current-run execution')

    def cached(self,stage):
        self.verify_binding()
        path=self._manifest(stage)
        if not path.exists():return False
        value=json.loads(path.read_text(encoding='utf-8'))
        if value.get('stage_identity')!=self.identity:return False
        if any(not (self.output/name).is_file() or file_digest(self.output/name)!=sha for name,sha in value['output_hashes'].items()):
            raise ValueError('Stage output checksum mismatch: '+stage)
        self.cache_hits.append(stage)
        return True

    def require(self,*stages):
        for stage in stages:
            if not self.cached(stage):raise ValueError('Missing or stale upstream stage '+stage+'; run it with the current configuration first')

    def finish(self,stage,files,details=None):
        self.verify_binding()
        emit(self._manifest(stage),{'schema_version':'1.0.0','delivery_version':self.config.delivery_version,'stage':stage,
            'stage_identity':self.identity,'grid_definition_id':self.config.grid_definition_id,'data_mode':self.config.data_mode.value,
            'output_hashes':{str(Path(name).as_posix()):file_digest(self.output/name) for name in files},'details':details or {}})

    def table(self,frame,name,schema,version,folder=None):
        target=(folder or self.output)/(name+'.parquet')
        return write_parquet(frame,target,schema_name=schema,schema_version=version,data_mode=self.config.data_mode,grid_definition_id=self.config.grid_definition_id)

    def geography(self):
        from dc_locator.model.enhanced import _read_baseline
        g,p,_=_read_baseline(self.output/'us_grid_dataset.parquet',self.output/'feature_provenance.parquet')
        if set(g.grid_definition_id)!={self.config.grid_definition_id} or set(g.data_mode)!={self.config.data_mode.value}:
            raise ValueError('Current geographic rows disagree with run identity')
        return g,p

    def inputs(self):
        facilities=load_facility_config(self.path(self.config.facility)).facilities
        if len(facilities)!=1:raise ValueError('One facility is required per delivery run')
        values=facilities[0].model_dump(mode='json');values['screening_mode']=self.config.screening_mode
        facility=FacilityConfig.model_validate(values)
        designs=load_cooling_designs(self.path(self.config.cooling_designs))
        scenarios=load_physical_scenarios(self.path(self.config.physical_scenarios))
        requirements,_=load_requirements(self.path(self.config.constraints))
        return facility,designs,scenarios,requirements

    def profile(self,path=None):
        profile=load_profile(path or self.path(self.config.scoring_profile))
        document=profile.model_dump(mode='json')
        document.update(weighting_method=self.config.weighting_method,user_weights=self.config.user_group_weights,
            ahp_judgments=json.loads(self.path(self.config.ahp_input).read_text(encoding='utf-8')) if self.config.ahp_input else None)
        if document!=profile.model_dump(mode='json'):
            document.update(profile_id=profile.profile_id+'__'+self.config.delivery_version+'_'+self.config.weighting_method,profile_version=self.config.delivery_version)
        return ScoringProfile.model_validate(document)

    def ingest(self):
        if self.cached('ingest'):return
        registry=json.loads(json.dumps(__import__('yaml').safe_load(self.path(self.config.source_registry).read_text(encoding='utf-8'))))
        inventory={'operation':'load and validate existing acquired native cache; no network acquisition',
            'data_mode':self.config.data_mode.value,'source_records':self.source_document,
            'source_registry':registry,'verified_file_count':len(self.source_hashes),'native_parsing_stage':'build-features',
            'source_hashes':self.source_hashes,'required_local_inputs_missing':[]}
        inventory['verified_acquisition_identities']=self.acquisition_checks
        emit(self.output/'source_inventory.json',inventory)
        emit(self.output/'config_snapshot.json',{'run':self.config.model_dump(mode='json'),'config_hashes':self.config_hashes,
            'files':{str(p):Path(p).read_text(encoding='utf-8') for p in self.config_hashes if Path(p).suffix in {'.yaml','.json'} }})
        self.finish('ingest',['source_inventory.json','config_snapshot.json'],{'verified_files':len(self.source_hashes)})

    def build_features(self):
        self.require('ingest')
        if self.cached('build-features'):return
        grid_path=self.path(self.config.grid_path);grid=gpd.read_parquet(grid_path)
        if grid.crs is None or grid.crs.to_epsg()!=5070 or set(grid.data_mode)!={self.config.data_mode.value} or set(grid.grid_definition_id)!={self.config.grid_definition_id}:
            raise ValueError('Grid row/file identity or CRS mismatch')
        for row in grid.to_dict('records'):GridCell.model_validate(clean(row))
        if self.config.data_mode==DataMode.SYNTHETIC:
            from dc_locator.model.enhanced import _read_baseline
            geo,prov,_=_read_baseline(self.path(self.config.fixture_geography),self.path(self.config.fixture_provenance))
            if geo.grid_id.tolist()!=grid.grid_id.tolist():raise ValueError('Synthetic fixture geographic domain differs from configured grid')
            coverage={'scope':'explicit synthetic fixture','cells':len(geo),'data_mode':'synthetic'};manifest={'fixture_only':True}
        else:
            from dc_locator.geography.boundary import load_conus_boundary
            from dc_locator.geography.features import build_features
            boundary=load_conus_boundary()
            core_inputs=load_source_document(self.path(self.config.core_source_inputs),self.root)
            geo=build_features(grid_path,core_inputs,self.output/'geography_core',study_geometry=boundary.boundary,
                cache_dir=self.root/'data/interim'/self.config.delivery_version/self.identity,resume=True,progress=print)
            prov=pd.read_parquet(self.output/'geography_core/feature_provenance.parquet')
            prov.attrs.update(grid_definition_id=self.config.grid_definition_id,data_mode='real')
            coverage={'core':json.loads((self.output/'geography_core/coverage_report.json').read_text(encoding='utf-8'))}
            manifest={'core':json.loads((self.output/'geography_core/data_manifest.json').read_text(encoding='utf-8'))}
            for key in ('processed_tiles','resumed_tiles'):coverage['core'].pop(key,None)
            if self.config.expanded_features:
                from dc_locator.geography.sources.expanded import build_expanded_features
                geo,prov,coverage['expanded'],manifest['expanded']=build_expanded_features(geo,prov,
                    source_inputs=load_source_document(self.path(self.config.expanded_source_inputs),self.root),study_geometry=boundary.boundary)
            if self.config.future['enabled']:
                from dc_locator.geography.sources.aqueduct_future import build_aqueduct_future_features
                geo,prov,coverage['aqueduct_future'],manifest['aqueduct_future']=build_aqueduct_future_features(geo,prov,
                    load_source_document(self.path(self.config.aqueduct_source_input),self.root),study_geometry=boundary.boundary,
                    pathways=self.config.future['pathways'],milestone_years=self.config.future['milestone_years'])
        validate_feature_provenance(prov,grid_ids=grid.grid_id,data_mode=self.config.data_mode.value,grid_definition_id=self.config.grid_definition_id)
        write_geoparquet(geo,self.output/'us_grid_dataset.parquet',schema_name='GeographicFeatureDataset',schema_version='1.2.0',data_mode=self.config.data_mode,grid_definition_id=self.config.grid_definition_id)
        self.table(prov,'feature_provenance','FeatureMetadata','1.1.0')
        emit(self.output/'source_coverage.json',coverage);emit(self.output/'source_data_manifest.json',substantive_source_manifest(manifest))
        self.finish('build-features',['us_grid_dataset.parquet','feature_provenance.parquet','source_coverage.json','source_data_manifest.json'],{'cells':len(geo),'metrics':prov.metric.nunique()})

    def screen(self):
        self.require('build-features')
        if self.cached('screen'):return
        g,p=self.geography();f,d,s,r=self.inputs()
        records,eligible,summary=screen(g,p,f,d,s,r,mode=self.config.screening_mode)
        self.table(records,'screening_results','ScreeningResult','1.1.0');self.table(eligible,'screening_eligibility','ScreeningEligibility','1.0.0')
        emit(self.output/'screening_summary.json',summary)
        self.finish('screen',['screening_results.parquet','screening_eligibility.parquet','screening_summary.json'],summary)

    def simulate(self):
        self.require('build-features')
        if self.cached('simulate'):return
        g,p=self.geography();f,d,s,_=self.inputs()
        performance=simulate(g,p,f,d,s)
        self.table(performance,'site_performance','SitePerformance','1.1.0')
        self.finish('simulate',['site_performance.parquet'],{'diagnostic_alternatives':len(performance)})

    def read_table(self,name,schema,minimum=(1,0,0),folder=None):
        target=(folder or self.output)/(name+'.parquet')
        meta=check_table_identity(target,schema,self.config.data_mode.value,self.config.grid_definition_id,minimum)
        frame=pd.read_parquet(target);frame.attrs.update(meta)
        for field in ('data_mode','grid_definition_id'):
            if field in frame and len(frame) and set(frame[field])!={meta[field]}:raise ValueError('Table row/file identity mismatch: '+field)
        return frame

    def write_decision(self,result,profile,folder,*,include_regions=False):
        folder.mkdir(parents=True,exist_ok=True)
        for name in ('normalized_metrics','pareto_results','ranked_cells'):
            self.table(result[name],name,*TABLES[name],folder=folder)
        result['ranked_cells'].sort_values(['scenario_id','mcda_rank','grid_id','design_id'],na_position='last').to_csv(folder/'ranking.csv',index=False,lineterminator='\n')
        emit(folder/('ahp_result.json' if result['ahp_result'] else 'ahp_template.json'),result['ahp_result'] or result['ahp_template'])
        emit(folder/'weight_result.json',{'weights':result['weights'],'weighting_method':result['weighting_method']})
        if include_regions:self.write_regions(result['candidate_regions'],result['region_membership'],profile,folder)

    def write_regions(self,regions,members,profile,folder):
        for row in regions.drop(columns='geometry').to_dict('records'):CandidateRegion.model_validate(clean(row))
        write_geoparquet(regions,folder/'candidate_regions.parquet',schema_name='CandidateRegion',schema_version='1.1.0',data_mode=self.config.data_mode,grid_definition_id=self.config.grid_definition_id)
        members=members.copy();members['profile_id']=profile.profile_id;members['profile_fingerprint']=profile_fingerprint(profile)
        members['grid_definition_id']=self.config.grid_definition_id;members['data_mode']=self.config.data_mode.value
        self.table(members,'region_membership',*TABLES['region_membership'],folder=folder)
        features=json.loads(regions.to_crs(4326).to_json(drop_id=True))['features'] if len(regions) else []
        emit(folder/'candidate_regions.geojson',{'type':'FeatureCollection','features':features,'dc_locator':{'schema':'CandidateRegion','schema_version':'1.1.0',
            'grid_definition_id':self.config.grid_definition_id,'data_mode':self.config.data_mode.value,'profile_id':profile.profile_id,
            'profile_fingerprint':profile_fingerprint(profile),'interpretation':'Search areas for investigation; no approved parcel'}})

    def rank(self):
        self.require('build-features','screen','simulate')
        if self.cached('rank'):return
        g,p=self.geography();profile=self.profile()
        emit(self.output/'profile_snapshot.json',{'status':'DECLARED_BEFORE_CURRENT_RANKING','delivery_version':self.config.delivery_version,
            'source_profile_sha256':file_digest(self.path(self.config.scoring_profile)),'resolved_profile_fingerprint':profile_fingerprint(profile),'profile':profile.model_dump(mode='json')})
        result=decide(g,p,self.read_table('site_performance','SitePerformance',(1,1,0)),self.read_table('screening_eligibility','ScreeningEligibility'),profile,
            profile_hash=profile_fingerprint(profile),provenance_grid_definition_id=self.config.grid_definition_id)
        self.write_decision(result,profile,self.output)
        files=['normalized_metrics.parquet','pareto_results.parquet','ranked_cells.parquet','ranking.csv','profile_snapshot.json','weight_result.json',
            'ahp_result.json' if result['ahp_result'] else 'ahp_template.json']
        self.finish('rank',files,{'alternatives':len(result['ranked_cells']),'rankable':int(result['ranked_cells'].rankable.sum()),'weighting_method':result['weighting_method']})

    def cluster(self):
        self.require('build-features','rank')
        if self.cached('cluster'):return
        from dc_locator.model.regions import cluster_regions
        g,_=self.geography();profile=self.profile()
        ranked=self.read_table('ranked_cells','RankedCellDataset',(1,1,0))
        if len(ranked) and (set(ranked.profile_fingerprint)!={profile_fingerprint(profile)} or set(ranked.profile_id)!={profile.profile_id}):
            raise ValueError('Ranked policy differs from configured clustering profile')
        regions,members=cluster_regions(g,ranked,profile.region_selection,[m.column for m in profile.metrics],profile.profile_id,profile_fingerprint(profile))
        self.write_regions(regions,members,profile,self.output)
        self.finish('cluster',['candidate_regions.geojson','candidate_regions.parquet','region_membership.parquet'],{'candidate_regions':len(regions),'memberships':len(members)})

    def future_contexts(self):
        if not self.config.future['enabled']:return []
        from dc_locator.geography.sources.aqueduct_future import future_period
        from dc_locator.model.enhanced import rebind_external_scenario,compare_rankings,validate_matched_preferences,combine_temporal_context
        from dc_locator.model.scenarios import make_external_scenarios,build_temporal_scenarios,build_climate_source_context
        from dc_locator.model.lifecycle import calculate_lifecycle
        import yaml
        g,p=self.geography();f,d,physical,r=self.inputs()
        if len(physical)!=1:raise ValueError('Configured water-context rebinding requires one physical baseline scenario')
        periods=[future_period(w,y) for w in self.config.future['pathways'] for y in self.config.future['milestone_years']]
        scenarios=make_external_scenarios(physical[0].scenario_id,periods)
        performance=self.read_table('site_performance','SitePerformance',(1,1,0));eligible=self.read_table('screening_eligibility','ScreeningEligibility')
        original=self.read_table('ranked_cells','RankedCellDataset',(1,1,0))
        declared=json.loads(self.path(self.config.future['profile_declaration']).read_text(encoding='utf-8'))
        if declared['status']!='PREDECLARED_BEFORE_FIRST_RANKING' or declared['baseline_profile_sha256']!=file_digest(self.path(self.config.scoring_profile)):
            raise ValueError('Future profiles lack accepted baseline/predeclaration binding')
        declaration={Path(entry['path']).stem:entry for entry in declared['profiles']}
        contexts=[];bound=[];comparisons=[]
        for scenario in scenarios:
            key=f'{scenario.pathway}_{scenario.milestone_year}'
            profile_path=self.path(self.config.future['profiles_directory'])/(key+'.yaml')
            if declaration[key]['sha256']!=file_digest(profile_path) or ScoringProfile.model_validate(declaration[key]['profile']).model_dump(mode='json')!=load_profile(profile_path).model_dump(mode='json'):
                raise ValueError('Future profile changed from accepted declaration: '+key)
            profile=self.profile(profile_path);validate_matched_preferences(self.profile(),profile)
            folder=self.output/'future_contexts'/key
            emit(folder/'profile_snapshot.json',{'status':'DECLARED_BEFORE_CURRENT_RANKING','profile':profile.model_dump(mode='json'),'profile_fingerprint':profile_fingerprint(profile)})
            perf=rebind_external_scenario(performance,scenario,physical_metadata=True);elig=rebind_external_scenario(eligible,scenario)
            result=decide(g,p,perf,elig,profile,profile_hash=profile_fingerprint(profile),provenance_grid_definition_id=self.config.grid_definition_id)
            self.write_decision(result,profile,folder,include_regions=True)
            self.table(perf,'site_performance','SitePerformance','1.1.0',folder=folder);self.table(elig,'screening_eligibility','ScreeningEligibility','1.0.0',folder=folder)
            emit(folder/'external_scenario.json',scenario.model_dump(mode='json'))
            bound.append(perf);comparisons.append(compare_rankings(original,result['ranked_cells'],scenario,self.config.screening_mode))
            contexts.append({'case_id':key,'geography':g,'provenance':p,'profile':profile,'external_scenario':scenario,'result':result,'rationale':'Separate configured native water scenario; no favorable-weather selection'})
        temporal=build_temporal_scenarios(pd.concat(bound,ignore_index=True),f,scenarios,
            extension_policy=self.config.future['annual_extension'],context_provenance=p,provenance_grid_definition_id=self.config.grid_definition_id)
        lc=yaml.safe_load(self.path(self.config.future['lifecycle']).read_text(encoding='utf-8'))
        lifecycle=calculate_lifecycle(temporal,opening_year=f.target_opening_year,lifetime_years=f.operating_lifetime_years,
            **{k:lc[k] for k in ('inventory','transport_legs','complete_components','component_evidence')})
        climate=build_climate_source_context(p,grid_ids=g.grid_id,grid_definition_id=self.config.grid_definition_id,data_mode=self.config.data_mode.value,facility_id=f.facility_id)
        temporal=combine_temporal_context(temporal,climate)
        self.table(temporal,'future_scenarios','FutureScenarioValue','1.0.0');self.table(lifecycle,'lifecycle_results','LifecycleResult','1.0.0')
        self.table(pd.concat(comparisons,ignore_index=True),'baseline_vs_enhanced','BaselineEnhancedComparison','1.0.0')
        return contexts

    def validate(self):
        self.require('build-features','screen','simulate','rank','cluster')
        if self.cached('validate'):return
        from dc_locator.model.run_validation import (CurrentRunIdentity,CurrentValidationSettings,FutureValidationContext,validate_current_run)
        g,p=self.geography();f,d,s,r=self.inputs();profile=self.profile()
        base={name:self.read_table(name,*TABLES[name][:1],minimum=tuple(map(int,TABLES[name][1].split('.')))) for name in ('normalized_metrics','pareto_results','ranked_cells','region_membership')}
        check_table_identity(self.output/'candidate_regions.parquet','CandidateRegion',self.config.data_mode.value,self.config.grid_definition_id,(1,1,0))
        base['candidate_regions']=gpd.read_parquet(self.output/'candidate_regions.parquet')
        for column in base['candidate_regions'].columns:
            if column!='geometry':base['candidate_regions'][column]=base['candidate_regions'][column].map(lambda v:clean(v) if isinstance(v,(list,tuple,dict,np.ndarray)) else v)
        base.update(json.loads((self.output/'weight_result.json').read_text(encoding='utf-8')))
        for table in ('ranked_cells','normalized_metrics','pareto_results','region_membership','candidate_regions'):
            frame=base[table]
            if len(frame) and any(field not in frame or set(frame[field])!={expected} for field,expected in [('profile_id',profile.profile_id),('profile_fingerprint',profile_fingerprint(profile)),('grid_definition_id',self.config.grid_definition_id)]):raise ValueError('Persisted decision profile/grid identity mismatch: '+table)
        regions=base['candidate_regions']
        exported=json.loads((self.output/'candidate_regions.geojson').read_text(encoding='utf-8'))
        expected=json.loads(regions.to_crs(4326).to_json(drop_id=True))['features'] if len(regions) else []
        if exported.get('features')!=expected:raise ValueError('Persisted region GeoJSON differs from evaluated region geometry/properties')
        identity=CurrentRunIdentity(run_id=self.run_id,model_revision=self.config.delivery_version,model_hashes=self.model_hashes,
            config_hashes=self.config_hashes,source_hashes=self.source_hashes)
        contexts=self.future_contexts()
        settings=dict(self.config.validation);settings.pop('enabled')
        requested=settings.pop('future_contexts',[])
        future=[FutureValidationContext(**{k:c[k] for k in ('case_id','geography','provenance','profile','external_scenario','rationale')},
            identity={'geography':file_digest(self.output/'us_grid_dataset.parquet'),'provenance':file_digest(self.output/'feature_provenance.parquet'),
                'profile':profile_fingerprint(c['profile']),'scenario':digest_json(c['external_scenario'].model_dump(mode='json'))}) for c in contexts if c['case_id'] in requested]
        if set(requested)!={c.case_id for c in future}:raise ValueError('Requested validation context is not configured')
        if not self.config.validation['enabled']:settings['cases']=[];future=[]
        settings['baseline_mode']=self.config.screening_mode
        result=validate_current_run(geography=g,provenance=p,facility=f,designs=d,physical_scenarios=s,requirements=r,
            active_profile=profile,baseline_result=base,baseline_regions=base['region_membership'],
            provenance_grid_definition_id=self.config.grid_definition_id,identity=identity,settings=CurrentValidationSettings.model_validate(settings),future_contexts=future)
        self.table(result.sensitivity_results,'sensitivity_results','CurrentSensitivityResult','1.0.0')
        self.table(result.alternative_rank_ranges,'alternative_rank_ranges','CurrentAlternativeRankRange','1.0.0')
        result.robustness_summary.to_csv(self.output/'robustness_summary.csv',index=False,lineterminator='\n')
        result.fixed_region_summary.to_csv(self.output/'fixed_region_summary.csv',index=False,lineterminator='\n')
        emit(self.output/'validation_report.json',result.validation_report)
        (self.output/'validation_report.md').write_text(result.validation_markdown,encoding='utf-8')
        from dc_locator.reporting import recommendation_report
        (self.output/'recommendation_report.md').write_text(recommendation_report(self,base,result,contexts),encoding='utf-8')
        files=['sensitivity_results.parquet','alternative_rank_ranges.parquet','robustness_summary.csv','fixed_region_summary.csv','validation_report.json','validation_report.md','recommendation_report.md']
        files += [str(path.relative_to(self.output)) for path in sorted((self.output/'future_contexts').rglob('*')) if path.is_file()]
        files += [name+'.parquet' for name in ('future_scenarios','lifecycle_results','baseline_vs_enhanced') if (self.output/(name+'.parquet')).exists()]
        self.finish('validate',files,{'current_revision':self.config.delivery_version,'requested_future_contexts':requested})

    def execute(self,stage):
        if stage=='run':
            for name in STAGES:getattr(self,name.replace('-','_'))()
        else:getattr(self,stage.replace('-','_'))()
        self.verify_binding()
        from dc_locator.reporting import run_metadata
        emit(self.output/'run_metadata.json',run_metadata(self,stage))
        return {'run_id':self.run_id,'stage':stage,'data_mode':self.config.data_mode.value,'output':str(self.output),'scope':self.scope,
            'stage_identity':self.identity,'cache_hits':sorted(set(self.cache_hits))}


def execute_stage(stage,config_path='configs/run.yaml',output='runs/example'):
    return Pipeline(config_path,output).execute(stage)
