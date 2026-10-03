"""Additive native Phase 5 geography builder. No network, ranking, or imputation.

The accepted baseline columns and provenance rows are copied unchanged. New
metrics are informational; each gets status/coverage/confidence and complete
source-specific evidence. The current acquired subset is development-only.
"""
import hashlib
import fnmatch
import json
import re
from urllib.parse import parse_qs,urlparse
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import shapely
import yaml

from dc_locator.geography.boundary import load_conus_boundary
from dc_locator.io import read_parquet_metadata, write_geoparquet, write_parquet
from dc_locator.paths import project_root as locate_root
from dc_locator.provenance import DataMode
from dc_locator.schemas import FeatureMetadata
from dc_locator.validation import validate_feature_provenance
from .ingestion import file_digest, inventory_downloads
from .spatial import region_intersections
from .native_expanded import (read_eia861,read_usdm,read_queue,read_ibtracs,
      read_ntad,read_wind_index,read_nsrdb,summarize_proximity)
from .native_climate import read_nex,TemperatureInterpretationError


AGGREGATION_VERSION='expanded-native-v1.0.0'


def _definitions():
    eia={}
    for basis in ['ieee_with_med','ieee_without_med','ieee_loss_supply_removed_with_med','any_with_med','any_without_med']:
        for metric,unit in [('saidi_minutes_per_year','minutes_per_year'),('saifi_interruptions_per_year','interruptions_per_year')]:
            name='eia861_'+basis+'_'+metric
            eia[name]=(unit,'State Totals; '+basis+'; '+metric,'proxy')
    for basis in ['ieee','any']:eia['eia861_'+basis+'_reporting_customers']=('customers','State Totals; '+basis+'; Number of Customers','proxy')
    return {'eia_861':eia,
      'us_drought_monitor':{'usdm_d2plus_area_time_frac':('frac','D2; cumulative area percent /100, weekly mean','proxy'),
       'usdm_d2plus_any_area_week_frac':('frac','D2>0; fraction of observed weeks, county','proxy'),
       'usdm_temporal_coverage_frac':('frac','MapDate; valid observed / expected Tuesday maps','calculated')},
      'berkeley_queued_up':{'queued_active_project_count':('projects','q_status=active; fips_code','proxy'),
       'queued_active_reported_capacity_mw':('MW','q_status=active; mw_1/mw_2/mw_3; type_1/2/3','proxy'),
       'queued_capacity_reporting_frac':('frac','fraction of active projects with all identified components reported','calculated')},
      'noaa_ibtracs':{'ibtracs_track_distance_km':('km','SID/ISO_TIME/LAT/LON/TRACK_TYPE=MAIN;1980-2024','proxy'),
       'ibtracs_track_count_within_100km':('storms','unique SID whose MAIN segments are within100km','proxy')},
      'ntad':{'ntad_rail_distance_km':('km','FRAARCID; native paths; complete bounded query','proxy')},
      'nrel_wind_toolkit':{'wind_toolkit_index_wind_speed_mean_m_per_s':('m_per_s','wind_speed; selected-site native summaries','proxy'),
       'wind_toolkit_index_capacity_factor_mean_frac':('frac','capacity_factor; selected-site modeled turbine summaries','proxy'),
       'wind_toolkit_index_site_count':('sites','site_id; selected native model sites within study polygon','observed')},
      'nrel_nsrdb':{'nsrdb_point_ghi_mean_w_per_m2':('W_per_m2','GHI; native CSV point-series observed sample mean','proxy')},
      'nasa_nex_gddp_cmip6':{'nex_access_cm2_ssp245_2030_tas_mean_c':('degC','tas; K-273.15; ACCESS-CM2/r1i1p1f1/ssp245/2030','scenario'),
       'nex_access_cm2_ssp245_2030_pr_mean_mm_per_day':('mm_per_day','pr; kg m-2 s-1 *86400; ACCESS-CM2/r1i1p1f1/ssp245/2030','scenario'),
       'nex_access_cm2_ssp245_2030_temporal_coverage_frac':('frac','time calendar; lesser of tas and pr area-weighted valid days/365; both required','calculated')}}


METRICS=_definitions()


def _catalog(root=None):
    root=Path(root) if root is not None else locate_root()
    return yaml.safe_load((root/'configs/expanded_sources.yaml').read_text(encoding='utf-8'))['sources']


def expanded_default_source_inputs(project_root=None):
    """Discover only checksum-verified native files, never initiate acquisition."""
    root=Path(project_root) if project_root is not None else locate_root();out={}
    entries=inventory_downloads(root/'data/raw')
    for source,definition in _catalog(root).items():
        cfg=dict(definition,paths={},data_mode='real')
        for entry in entries:
            if not definition.get('raw_namespace') or entry.get('source_id')!=definition['raw_namespace']:continue
            path=Path(entry['path']);path=path if path.is_absolute() else root/path
            pattern=definition.get('native_pattern')
            if pattern and not (fnmatch.fnmatch(path.name,pattern) or path.match(pattern)):continue
            if not path.exists():raise ValueError(f'Acquired source file missing: {path}')
            if entry.get('sha256')!=file_digest(path) or entry.get('bytes')!=path.stat().st_size:raise ValueError('Expanded native cache checksum mismatch')
            if source=='nasa_nex_gddp_cmip6':
                key=path.name.split('_')[0]
                if key not in {'tas','pr','tasmax','tasmin'}:continue
            else:key='native'
            if key in cfg['paths']:raise ValueError('Multiple native snapshots found; select explicit version/path')
            cfg['paths'][key]=str(path);cfg['retrieved_at']=entry.get('retrieved_at_utc')
            cfg.setdefault('acquisition_evidence',{})[key]=entry
            if source=='us_drought_monitor':cfg['requested_aoi']=parse_qs(urlparse(entry['url']).query).get('aoi',[None])[0]
        out[source]=cfg
    return out


def expanded_source_catalog(source_inputs=None):
    """Implementation/acquisition only; analysis is added by the builder report."""
    inputs=expanded_default_source_inputs() if source_inputs is None else source_inputs
    return {s:{'implemented':bool(c.get('implemented')),'acquired':bool(c.get('paths')),
               'analyzed':False,'status':c.get('status','NOT_IMPLEMENTED'),
               'source_url':c.get('source_url'),'source_version':c.get('source_version'),
               'limitation':c.get('limitation')} for s,c in inputs.items()}


def _associate(cells,regions,table,key,metrics):
    """Exact regional overlay with valid-area coverage and no centroid assignment."""
    pieces=region_intersections(cells,regions,key).merge(table,on=key,how='left',validate='many_to_one')
    if len(pieces) and (pieces.groupby('grid_id').share_frac.sum()>1+1e-6).any():raise ValueError('Overlapping native region shares exceed1; ambiguous association rejected')
    rows=[]
    for metric in metrics:
        values=pd.to_numeric(pieces.get(metric,pd.Series(dtype=float)),errors='coerce')
        valid=np.isfinite(values)
        p=pieces.loc[valid,['grid_id','area_m2','share_frac']].copy();p['weighted']=values[valid]*p.area_m2
        grouped=p.groupby('grid_id',sort=False).agg(total=('weighted','sum'),area=('area_m2','sum'),coverage=('share_frac','sum'))
        for gid in cells.grid_id:
            g=grouped.loc[gid] if gid in grouped.index else None
            rows.append({'grid_id':gid,'metric':metric,'value':g.total/g.area if g is not None and g.area else np.nan,
                         'coverage_frac':min(1.,float(g.coverage)) if g is not None else 0})
    frame=pd.DataFrame(rows);frame.attrs.update(table.attrs)
    if 'queued_invalid_capacity_project_count' in pieces:
        bad=pieces.loc[pieces.queued_invalid_capacity_project_count>0,'grid_id'].unique()
        frame.loc[frame.grid_id.isin(bad)&frame.metric.eq('queued_active_reported_capacity_mw')&frame.value.isna(),'missing_reason']='invalid_source_value'
    return frame


def _summary(cells,source,cfg,boundary):
    paths=cfg.get('paths',{})
    if not paths:return pd.DataFrame(columns=['grid_id','metric','value','coverage_frac'])
    native=paths.get('native')
    if source=='eia_861':
        table=read_eia861(native)
        if set(table.data_year.dropna().astype(int))!={2024}:raise ValueError('EIA profile explicitly selects2024')
        regions=boundary.states.rename(columns={'STUSPS':'State'})
        return _associate(cells,regions,table,'State',METRICS[source])
    if source=='us_drought_monitor':
        table=read_usdm(native);table=table.rename(columns={'temporal_coverage_frac':'usdm_temporal_coverage_frac'})
        frame=_associate(cells,boundary.counties,table,'GEOID',METRICS[source])
        temporal=frame.loc[frame.metric=='usdm_temporal_coverage_frac'].set_index('grid_id').value
        frame['temporal_coverage_frac']=frame.grid_id.map(temporal)
        frame.loc[frame.coverage_frac<=0,'missing_reason']='outside_source_coverage'
        return frame
    if source=='berkeley_queued_up':return _associate(cells,boundary.counties,read_queue(native),'GEOID',METRICS[source])
    if source=='ntad':
        lines,footprint=read_ntad(native);return summarize_proximity(cells,lines,footprint,'ntad_rail_distance_km')
    if source=='noaa_ibtracs':
        tracks=read_ibtracs(native);frame=summarize_proximity(cells,tracks,None,'ibtracs_track_distance_km')
        counts=[]
        for c in cells.itertuples():
            ids=tracks.sindex.query(c.geometry.buffer(100000),predicate='intersects')
            count=int((tracks.iloc[ids].geometry.distance(c.geometry)<=100000).sum())
            counts.append({'grid_id':c.grid_id,'metric':'ibtracs_track_count_within_100km','value':count if len(tracks) else np.nan,'coverage_frac':1. if len(tracks) else 0.})
        return pd.concat([frame,pd.DataFrame(counts)],ignore_index=True)
    if source=='nrel_wind_toolkit':
        sites=read_wind_index(native)
        pairs=sites.sindex.query(cells.geometry,predicate='contains')
        groups={i:sites.iloc[pairs[1,pairs[0]==i]] for i in np.unique(pairs[0])}
        rows=[]
        for i,c in enumerate(cells.itertuples()):
            g=groups.get(i)
            values={'wind_toolkit_index_site_count':0 if g is None else len(g),
                'wind_toolkit_index_wind_speed_mean_m_per_s':np.nan if g is None else g.wind_speed.mean(),
                'wind_toolkit_index_capacity_factor_mean_frac':np.nan if g is None else g.capacity_factor.mean()}
            for metric,value in values.items():rows.append({'grid_id':c.grid_id,'metric':metric,'value':value,'coverage_frac':None})
        return pd.DataFrame(rows)
    if source=='nrel_nsrdb':
        r=read_nsrdb(native)
        point=gpd.GeoSeries(gpd.points_from_xy([r['longitude']],[r['latitude']]),crs=4326).to_crs(5070).iloc[0]
        return pd.DataFrame([{'grid_id':c.grid_id,'metric':'nsrdb_point_ghi_mean_w_per_m2',
          'value':r['ghi_mean_w_per_m2'] if c.geometry.covers(point) else np.nan,'coverage_frac':None,
          'temporal_coverage_frac':r['valid_sample_count']/r['sample_count']} for c in cells.itertuples()])
    if source=='nasa_nex_gddp_cmip6':
        frames=[];times=[];quality={}
        for variable,metric in [('tas','nex_access_cm2_ssp245_2030_tas_mean_c'),('pr','nex_access_cm2_ssp245_2030_pr_mean_mm_per_day')]:
            if variable not in paths:continue
            try:
                components={k:paths[k] for k in ['tasmax','tasmin'] if k in paths}
                pixels,meta=read_nex(paths[variable],variable,temperature_components=components)
            except TemperatureInterpretationError as error:
                quality[variable]={'status':'UNKNOWN','reason':str(error),'missing_reason':'invalid_source_value'}
                frames.append(pd.DataFrame({'grid_id':cells.grid_id,'metric':metric,'value':np.nan,
                    'coverage_frac':None,'missing_reason':'invalid_source_value'}))
                continue
            pixels[metric]=pixels.value
            table=pixels.drop(columns='geometry')
            frame=_associate(cells,pixels,table,'pixel_id',[metric]);frame['native_metadata_json']=json.dumps(meta,sort_keys=True)
            frame['temporal_coverage_frac']=meta['time_coverage_frac']
            frames.append(frame)
            temporal=_associate(cells,pixels,pixels.drop(columns='geometry'),'pixel_id',['temporal_coverage_frac'])
            times.append(temporal.set_index('grid_id')[['value','coverage_frac']])
        if len(times)==2:
            temporal=pd.concat([t.value for t in times],axis=1).min(axis=1,skipna=False)
            coverage=pd.concat([t.coverage_frac for t in times],axis=1).min(axis=1)
            frames.append(pd.DataFrame({'grid_id':cells.grid_id,'metric':'nex_access_cm2_ssp245_2030_temporal_coverage_frac',
                'value':cells.grid_id.map(temporal),'coverage_frac':cells.grid_id.map(coverage)}))
        result=pd.concat(frames,ignore_index=True) if frames else pd.DataFrame()
        result.attrs['analysis_executed']=bool(times)
        if quality:result.attrs['native_quality']=quality
        return result
    return pd.DataFrame()


def build_expanded_features(geography,baseline_provenance,source_inputs=None,output_dir=None,*,study_geometry=None):
    """Return (enhanced geography, provenance, coverage, manifest).

    Optional output_dir writes GFD1.2 and FeatureMetadata1.1 without replacing the
    baseline files. File provenance identity is read into attrs; in-memory inputs
    must already carry verified attrs['grid_definition_id']. No implicit network.
    """
    if isinstance(geography,(str,Path)):
        info=read_parquet_metadata(geography)
        if info.get('schema')!='GeographicFeatureDataset':raise ValueError('GeographicFeatureDataset required')
        if not re.fullmatch(r'1\.[1-9]\d*\.\d+',info.get('schema_version','')):raise ValueError('Compatible geography schema1.1+ required')
        grid=gpd.read_parquet(geography)
        if set(grid.grid_definition_id)!={info.get('grid_definition_id')} or set(grid.data_mode)!={info.get('data_mode')}:raise ValueError('Geography row/file identity mismatch')
    else:grid=geography.copy()
    if isinstance(baseline_provenance,(str,Path)):
        info=read_parquet_metadata(baseline_provenance)
        if info.get('schema')!='FeatureMetadata':raise ValueError('FeatureMetadata required')
        if not re.fullmatch(r'1\.[1-9]\d*\.\d+',info.get('schema_version','')):raise ValueError('Compatible FeatureMetadata schema1.1+ required')
        provenance=pd.read_parquet(baseline_provenance);provenance.attrs['grid_definition_id']=info.get('grid_definition_id')
        if set(provenance.data_mode)!={info.get('data_mode')}:raise ValueError('Provenance row/file data_mode mismatch')
    else:provenance=baseline_provenance.copy()
    if grid.empty or grid.grid_id.duplicated().any() or grid.grid_definition_id.nunique()!=1 or grid.data_mode.nunique()!=1:
        raise ValueError('Expanded input requires unique nonempty grid and uniform identity/mode')
    if grid.crs is None or grid.crs.to_epsg()!=5070 or grid.geometry.isna().any() or grid.geometry.is_empty.any() or not grid.geometry.is_valid.all() or not grid.geometry.geom_type.eq('Polygon').all() or not np.isfinite(grid.geometry.area).all() or (grid.geometry.area<=0).any():raise ValueError('Valid positive-area EPSG:5070 polygon grid required')
    gid=grid.grid_definition_id.iloc[0];mode=str(grid.data_mode.iloc[0])
    validate_feature_provenance(provenance,grid_ids=set(grid.grid_id),data_mode=mode,grid_definition_id=gid)
    inputs=expanded_default_source_inputs() if source_inputs is None else source_inputs
    for cfg in inputs.values():
        if cfg.get('paths') and cfg.get('data_mode','real')!=mode:raise ValueError('Expanded source/grid data_mode mismatch')
    boundary=load_conus_boundary()
    study=boundary.boundary if study_geometry is None else study_geometry
    if study is None or study.is_empty or not study.is_valid or study.geom_type not in {'Polygon','MultiPolygon'} or not np.isfinite(study.area) or study.area<=0:raise ValueError('Valid positive-area study polygon required')
    cells=grid.copy();cells.geometry=shapely.intersection(grid.geometry.values,study)
    if not np.allclose(cells.geometry.area,grid.study_area_intersection_km2*1e6,rtol=1e-7,atol=.05):raise ValueError('Study intersection does not match accepted grid area')
    new=[];columns={};counts={};source_hashes={}
    catalog=expanded_source_catalog(inputs)
    for source,definitions in METRICS.items():
        cfg=inputs.get(source,{});summary=_summary(cells,source,cfg,boundary)
        lookup={(r['grid_id'],r['metric']):r for r in summary.to_dict('records')}
        source_hashes[source]={k:{'path':str(p),'sha256':file_digest(p),'bytes':Path(p).stat().st_size} for k,p in cfg.get('paths',{}).items()}
        known={}
        for metric,(unit,field,status) in definitions.items():
            if metric in grid or metric in set(provenance.metric):raise ValueError('Expanded metric would overwrite accepted baseline')
            records=[]
            for grid_id in grid.grid_id:
                row=lookup.get((grid_id,metric),{});value=row.get('value')
                value=float(value) if value is not None and pd.notna(value) and np.isfinite(value) else None
                coverage=row.get('coverage_frac',0.);coverage=None if pd.isna(coverage) else float(coverage)
                present=value is not None
                row_reason=row.get('missing_reason');row_reason=None if pd.isna(row_reason) else row_reason
                reason=None if present else (row_reason or ('source_not_acquired' if not cfg.get('paths') else 'source_nodata'))
                method={'eia_861':'State-associated area-weighted context; reporting basis retained; not supplying utility reliability',
                  'us_drought_monitor':'County exact-area overlay; cumulative D2-or-worse; equal weekly observed maps; temporal coverage separate',
                  'berkeley_queued_up':'County exact-area overlay; first-listed native county only; no missing MW imputation; absence UNKNOWN',
                  'noaa_ibtracs':'Minimum study-polygon distance in EPSG5070 to densified historical MAIN segments; 100km count is descriptive, not hazard footprint',
                  'ntad':'Minimum study-polygon distance in EPSG5070; nearest feature must be closer than complete query boundary',
                  'nrel_wind_toolkit':'Selected-site arithmetic means within study polygon; native modeled index, no spatial interpolation or areal coverage',
                  'nrel_nsrdb':'Native point series only; sample mean, no areal interpolation; temporal valid-sample fraction retained',
                  'nasa_nex_gddp_cmip6':'Complete-calendar daily mean then exact native pixel-area overlay; one2030 ACCESS-CM2/ssp245/r1i1p1f1 scenario, no lifetime extension'}[source]
                detail={k:row[k] for k in ['temporal_coverage_frac','native_metadata_json'] if k in row and pd.notna(row[k])}
                method_metadata={'interpretation':cfg.get('limitation'),'details':detail}
                if source=='nasa_nex_gddp_cmip6':
                    temporal=value if metric.endswith('temporal_coverage_frac') else row.get('temporal_coverage_frac')
                    temporal=None if temporal is None or pd.isna(temporal) else float(temporal)
                    method_metadata.update(model='ACCESS-CM2',ensemble='r1i1p1f1',ssp='ssp245',period_start_year=2030,period_end_year=2030,
                        variable='tas' if '_tas_' in metric else ('pr' if '_pr_' in metric else 'temporal_coverage'),temporal_coverage_frac=temporal)
                record=FeatureMetadata(grid_id=grid_id,metric=metric,value=value,unit=unit,source_id=source,
                  source_name=cfg.get('source_name',source),source_url=cfg.get('source_url'),source_field=field,
                  source_version=cfg.get('source_version'),data_year=cfg.get('data_year'),retrieved_at=cfg.get('retrieved_at'),
                  spatial_resolution=cfg.get('spatial_resolution'),aggregation_method=method,coverage_frac=coverage,
                  status=status if present else 'unknown',confidence='low' if present else 'unknown',missing_reason=reason,
                  method=json.dumps(method_metadata,sort_keys=True,allow_nan=False),data_mode=mode)
                records.append(record.model_dump(mode='json'));new.append(records[-1])
            columns[metric]=[r['value'] for r in records]
            for suffix,key in [('status','status'),('confidence','confidence'),('coverage_frac','coverage_frac'),('missing_reason','missing_reason')]:columns[metric+'_'+suffix]=[r[key] for r in records]
            known[metric]=sum(r['status']!='unknown' for r in records)
        counts[source]=known
        catalog.setdefault(source,{'implemented':True,'acquired':bool(cfg.get('paths')),'status':'PARTIAL'})
        analyzed=bool(summary.attrs.get('analysis_executed',len(summary)>0))
        catalog[source].update(analyzed=analyzed,analyzed_cells=len(grid) if analyzed else 0,
            nonmissing_cells=len({r['grid_id'] for r in new if r['source_id']==source and r['status']!='unknown'}),metric_nonmissing_cells=known)
        if summary.attrs.get('native_quality'):catalog[source]['native_quality']=summary.attrs['native_quality']
    enhanced=grid.copy()
    enhanced=pd.concat([enhanced,pd.DataFrame(columns,index=enhanced.index)],axis=1)
    enhanced=gpd.GeoDataFrame(enhanced,geometry='geometry',crs=grid.crs);enhanced.attrs.update(grid.attrs)
    appended=pd.DataFrame(new).sort_values(['grid_id','metric']).reset_index(drop=True)
    for column in provenance.columns:
        if column in appended:appended[column]=appended[column].astype(provenance[column].dtype)
    enhanced_provenance=pd.concat([provenance,appended],ignore_index=True);enhanced_provenance.attrs.update(provenance.attrs)
    if enhanced_provenance.duplicated(['grid_id','metric']).any():raise ValueError('Duplicate additive provenance')
    raw=locate_root()/'data/raw';interim=locate_root()/'data/interim'
    report={'schema_version':'1.0.0','data_mode':mode,'grid_definition_id':gid,'input_cells':len(grid),'output_cells':len(enhanced),
      'analysis_extent':'provided development subset; no national analysis claim','sources':catalog,
      'baseline_columns_preserved':list(grid.columns),'baseline_provenance_rows_preserved':len(provenance)}
    manifest={'aggregation_version':AGGREGATION_VERSION,'grid_definition_id':gid,'data_mode':mode,
      'selected_grid_ids':grid.grid_id.tolist(),'source_files':source_hashes,
      'source_configuration':inputs,
      'source_configuration_sha256':hashlib.sha256(json.dumps(inputs,sort_keys=True,default=str).encode()).hexdigest(),
      'grid_geometry_sha256':hashlib.sha256(b''.join(cells.geometry.to_wkb().values)).hexdigest(),
      'code_sha256':hashlib.sha256(''.join(file_digest(Path(__file__).parent/f) for f in ['expanded.py','native_expanded.py','native_climate.py']).encode()).hexdigest(),
      'expanded_config_sha256':file_digest(locate_root()/'configs/expanded_sources.yaml'),
      'raw_total_bytes_including_manifests':sum(p.stat().st_size for p in raw.rglob('*') if p.is_file()),
      'interim_total_bytes_including_extracted_copies':sum(p.stat().st_size for p in interim.rglob('*') if p.is_file()),
      'output_schema_versions':{'GeographicFeatureDataset':'1.2.0','FeatureMetadata':'1.1.0'}}
    if output_dir is not None:
        output=Path(output_dir);output.mkdir(parents=True,exist_ok=True)
        write_geoparquet(enhanced,output/'enhanced_grid_dataset.parquet',schema_name='GeographicFeatureDataset',schema_version='1.2.0',data_mode=DataMode(mode),grid_definition_id=gid)
        write_parquet(enhanced_provenance,output/'enhanced_feature_provenance.parquet',schema_name='FeatureMetadata',schema_version='1.1.0',data_mode=DataMode(mode),grid_definition_id=gid)
        manifest['outputs']={n:{'sha256':file_digest(output/n),'bytes':(output/n).stat().st_size} for n in ['enhanced_grid_dataset.parquet','enhanced_feature_provenance.parquet']}
        (output/'expanded_coverage_report.json').write_text(json.dumps(report,indent=2,sort_keys=True),encoding='utf-8')
        (output/'expanded_data_manifest.json').write_text(json.dumps(manifest,indent=2,sort_keys=True,default=str),encoding='utf-8')
    return enhanced,enhanced_provenance,report,manifest
