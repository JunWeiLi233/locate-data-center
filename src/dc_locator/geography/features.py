"""Phase 2 geography pipeline: real sources, nullable metrics, resumable tiles.

Call ``build_features(grid, source_inputs, output_dir)``. Acquisition is explicit
and independent (``geography.sources.ingestion``); no network calls occur here.
All original cells and square geometries are retained. Analysis geometries are
intersected with the Phase 1 study boundary, never with a convenient land proxy.
"""
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import zipfile

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
import shapely

from dc_locator.io import write_geoparquet,write_parquet
from dc_locator.provenance import DataMode
from dc_locator.schemas import FeatureMetadata
from .boundary import load_conus_boundary
from .sources.aqueduct import summarize_water_stress
from .sources.climate import summarize_temperature
from .sources.egrid import read_subregion_workbook,summarize_egrid
from .sources.flood import summarize_flood
from .sources.infrastructure import distances_to_infrastructure
from .sources.ingestion import file_digest,inventory_downloads,extract_verified_member
from .sources.nlcd import CLASSES,summarize_land_cover
from .sources.protected import summarize_protected
from .sources.spatial import read_vector
from .sources.wildfire import summarize_wildfire

SCHEMA_VERSION='1.1.0'
AGGREGATION_VERSION='phase2-area-weights-v1'
BOUNDED_VECTOR_SOURCES={'epa_egrid','wri_aqueduct40','fema_nfhl','usgs_padus'}
MAX_PREPARATION_SPAN_M=250_000

SOURCE_INFO={
 'usgs_annual_nlcd':('USGS Annual NLCD','https://www.usgs.gov/centers/eros/science/annual-national-land-cover-database','2024','Collection 1.1 public ImageServer export','30 m categorical; EPSG:5070 export'),
 'epa_egrid':('EPA eGRID','https://www.epa.gov/egrid/detailed-data','2023','eGRID2023 rev2','eGRID subregion polygon'),
 'wri_aqueduct40':('WRI Aqueduct 4.0','https://www.wri.org/data/aqueduct-water-risk-atlas','1979-2019 baseline','4.0 Y2023M07D05','HydroBASINS Level 6 subbasin polygons'),
 'noaa_ncei_climate':('NOAA NCEI gridded normals','https://www.ncei.noaa.gov/products/land-based-station/us-climate-normals','1991-2020','Gridded normals v1.0','1/24 degree (~4.63 km)'),
 'fema_nfhl':('FEMA effective NFHL','https://www.fema.gov/flood-maps/national-flood-hazard-layer','effective snapshot 2026-10-03','effective NFHL','FIRM hazard polygons, panel-dependent map scale'),
 'usfs_wildfire_risk':('USFS Wildfire Risk to Communities','https://www.fs.usda.gov/rds/archive/catalog/RDS-2020-0016-2','unverified service packing','WRC public ImageServer export (unverified scale/mask)','30 m service; nearest-neighbor EPSG:5070 export'),
 'eia_energy_atlas':('EIA U.S. Energy Atlas','https://atlas.eia.gov/','transmission archive 2024-09-30; plants 202502; pipeline vintage unverified','EIA national vector exports','mapped line/point vectors'),
 'usgs_padus':('USGS PAD-US','https://doi.org/10.5066/P96WBCHS','2024','PAD-US 4.1 flattened vector analysis','flattened protected-area polygons'),
 'usfs_whp':('USFS Wildfire Hazard Potential','https://www.fs.usda.gov/rds/archive/catalog/RDS-2015-0047-4','2023','WHP 4th edition','270 m EPSG:5070; not WRC')}

# source metric -> (unit, native field, default value status)
METRICS={
 'usgs_annual_nlcd':{**{f'land_cover_{n}_frac':('frac',f'class {c}','observed') for c,n in CLASSES.items()},
   'nlcd_coverage_frac':('frac','valid class mask','calculated'),
   'nlcd_observed_area_km2':('km2','valid class mask','calculated'),
   'nlcd_water_area_km2':('km2','class 11','calculated'),
   'nlcd_land_area_km2':('km2','all valid classes except 11','calculated'),
   'potentially_suitable_land_frac':('frac','valid classes except 11,12,90,95','proxy'),
   'suitable_land_area_km2':('km2','valid classes except 11,12,90,95','proxy')},
 'epa_egrid':{'grid_carbon_intensity_kg_per_mwh':('kg_CO2e_per_mwh','SRC2ERTA','proxy'),
   'grid_co2_intensity_kg_per_mwh':('kg_CO2_per_mwh','SRCO2RTA','proxy'),
   'egrid_coverage_frac':('frac','Subregion','calculated'),'egrid_n_subregions':('count','Subregion','calculated'),
   'egrid_subregion_primary':(None,'Subregion','observed'),'egrid_subregion_shares_json':(None,'Subregion','calculated'),
   'egrid_multiple_subregion_labels_json':(None,'MultipleSu','calculated'),
   'egrid_multiple_subregion_overlap_frac':('frac','MultipleSu','observed')},
 'wri_aqueduct40':{'baseline_water_stress_ratio':('ratio','bws_raw','observed'),
   'baseline_water_stress_score':('score_0_to_5','bws_score','observed'),
   'baseline_water_stress_category':('category_-1_to_4','bws_cat','observed'),
   'baseline_water_stress_extreme_scarcity_frac':('frac','bws_raw==9999','observed'),
   'baseline_water_stress_category_shares_json':(None,'bws_cat','calculated'),
   'aqueduct_coverage_frac':('frac','bws_raw valid including 9999','calculated'),
   'aqueduct_n_subbasins':('count','pfaf_id','calculated'),'aqueduct_subbasin_shares_json':(None,'pfaf_id','calculated')},
 'noaa_ncei_climate':{'temperature_mean_c':('degC','annual-tavg_norm','observed'),
   'temperature_annual_max_mean_c':('degC','annual-tmax_norm','observed'),
   'temperature_annual_min_mean_c':('degC','annual-tmin_norm','observed'),
   'temperature_warmest_month_daily_max_c':('degC','annual-tmax_max','observed')},
 'fema_nfhl':{'flood_overlap_frac':('frac','SFHA_TF=T','observed'),
   'flood_sfha_area_km2':('km2','SFHA_TF=T','calculated'),
   'flood_coverage_frac':('frac','SFHA_TF in T,F excluding D/OPEN WATER','calculated'),
   'flood_surveyed_coverage_frac':('frac','NFHL Availability layer 0','observed')},
 'usfs_wildfire_risk':{'wildfire_burn_probability':('annual_probability','BurnProbability','observed'),
   'wildfire_conditional_flame_length_ft':('ft','ConditionalFlameLength','observed')},
 'eia_energy_atlas':{'transmission_distance_km':('km','transmission line geometry','proxy'),
   'power_plant_distance_km':('km','power plant geometry','proxy'),
   'gas_pipeline_distance_km':('km','pipeline geometry','proxy')},
 'usgs_padus':{**{f'padus_gap{i}_frac':('frac','GAP_Sts='+str(i),'observed') for i in [1,2,3,4]},
   'protected_overlap_frac':('frac','GAP_Sts in 1,2','observed'),'padus_coverage_frac':('frac','valid GAP_Sts','calculated')},
 'usfs_whp':{'wildfire_hazard_potential_whp2023':('dimensionless_index','whp2023_cnt_conus','observed')}}


def _vsi(path,member=None):
    p=Path(path)
    return '/vsizip/'+p.resolve().as_posix()+(('/'+member) if member else '') if p.suffix=='.zip' else str(p)


def default_source_inputs(project_root=None):
    """Discover verified cached files. Local overrides use the same paths mapping.

    Default geographic study is 42-cell dev_tiny. Broader grids retain nulls where
    cached NLCD/WRC/FEMA clips do not cover them; no extrapolation is performed.
    """
    root=Path(project_root or Path(__file__).resolve().parents[3]); raw=root/'data'/'raw'
    sources={s:{'paths':{},'source_name':i[0],'source_url':i[1],'data_year':i[2],
                'source_version':i[3],'spatial_resolution':i[4],'data_mode':'real'} for s,i in SOURCE_INFO.items()}
    def found(s,key,relative):
        path=raw/relative
        if path.exists(): sources[s]['paths'][key]=str(path)
    found('usgs_annual_nlcd','land_cover','usgs_annual_nlcd/Annual_NLCD_LndCov_2024_devbbox_5070.tif')
    found('epa_egrid','workbook','epa_egrid/official_2023/egrid2023_data_rev2.xlsx')
    found('epa_egrid','regions','epa_egrid/official_2023/egrid2023_subregions.zip')
    found('epa_egrid','multiple_regions','epa_egrid/official_2023/egrid2023_multiple_subregions.zip')
    sources['epa_egrid'].update(region_field='Subregion',unit='lb_per_mwh',sheet='SRL23')
    found('wri_aqueduct40','baseline','wri_aqueduct40/aqueduct-4-0-water-risk-data.zip')
    sources['wri_aqueduct40'].update(layer='baseline_annual',zip_member='Aqueduct40_waterrisk_download_Y2023M07D05/GDB/Aq40_Y2023D07M05.gdb')
    for metric,native in [('temperature_mean_c','tavg_norm'),('temperature_annual_max_mean_c','tmax_norm'),
                          ('temperature_annual_min_mean_c','tmin_norm'),('temperature_warmest_month_daily_max_c','tmax_max')]:
        found('noaa_ncei_climate',metric,f'noaa_ncei_climate/gridded-normals-cogs/normals-annual/1991-2020/1991_2020-annual-{native}.tif')
    for key,pattern in [('hazards','nfhl_layer28_*.geojson'),('surveyed','nfhl_layer0_*.geojson')]:
        files=sorted((raw/'fema_nfhl'/'bounded').glob(pattern))
        if len(files)==1: sources['fema_nfhl']['paths'][key]=str(files[0])
    for metric,theme in [('wildfire_burn_probability','BurnProbability'),('wildfire_conditional_flame_length_ft','ConditionalFlameLength')]:
        files=sorted((raw/'usfs_wildfire_risk'/'wrc'/'bounded').glob(theme+'_*_5070.tif'))
        if len(files)==1: sources['usfs_wildfire_risk']['paths'][metric]=str(files[0])
    if sources['usfs_wildfire_risk']['paths']:
        sources['usfs_wildfire_risk']['quality_blocker']='invalid_source_value'
        sources['usfs_wildfire_risk']['blocker_detail']='ImageServer U16 packed values/scale and missing-data mask unverified; BP export0..35 is not probability. Provide native WRC archive rasters with documented units and nodata.'
    for key,filename in [('transmission','eia_electric_power_transmission_lines_archive_national.geojson'),
                         ('power_plants','eia_power_plants_national.geojson'),
                         ('pipelines','eia_natural_gas_interstate_intrastate_pipelines_national.geojson')]:
        found('eia_energy_atlas',key,'eia_energy_atlas/'+filename)
    found('usgs_padus','areas','usgs_padus/PADUS4_1VectorAnalysis_CONUS.gdb')
    sources['usgs_padus']['layer']='PADUS4_1_VectorAnalysis_CONUS'
    # Read only continuous CONUS WHP GeoTIFF from archive, never the huge PAD-US raster.
    found('usfs_whp','archive','usfs_wildfire_risk/whp/RDS-2015-0047-4_Data.zip')
    if 'archive' in sources['usfs_whp']['paths']:
        archive=sources['usfs_whp']['paths']['archive']
        member=next(n for n in zipfile.ZipFile(archive).namelist() if n.endswith('whp2023_cnt_conus.tif'))
        sources['usfs_whp']['zip_member']=member
    records=inventory_downloads(raw)
    for s,cfg in sources.items():
        entries=[e for e in records if any(Path(e['path']).name==Path(p).name for p in cfg['paths'].values())]
        timestamps=[e.get('retrieved_at_utc') or e.get('retrieved_at') for e in entries]
        cfg['retrieved_at']=max([t for t in timestamps if t],default=None)
        cfg['manifest_entries']=entries
        if s=='fema_nfhl':
            cfg['query_bounds_4326']={key:next((e.get('bounds_4326') for e in entries if Path(e['path']).name==Path(path).name),None) for key,path in cfg['paths'].items()}
    return sources


def _source_fingerprint(cfg):
    config={k:v for k,v in cfg.items() if k!='paths'}; inputs={}
    for key,path in cfg.get('paths',{}).items():
        if isinstance(path,gpd.GeoDataFrame):
            values=pd.util.hash_pandas_object(pd.DataFrame(path.drop(columns='geometry')),index=False).values.tobytes()
            digest=hashlib.sha256(values+b''.join(path.geometry.to_wkb().values)).hexdigest()
        else:
            digest=file_digest(path)
            entry=next((e for e in cfg.get('manifest_entries',[]) if Path(e['path']).name==Path(path).name),None)
            if entry and entry.get('sha256') and entry['sha256']!=digest:
                raise ValueError(f'Input manifest SHA256 mismatch: {path}')
        inputs[key]={'sha256':digest,'path':str(path) if not isinstance(path,gpd.GeoDataFrame) else '<in_memory_fixture>'}
    return {'config':config,'inputs':inputs}


def _prepare(cells,source_inputs,progress=None,*,egrid_attributes=None):
    prepared={}
    for source,cfg in source_inputs.items():
        if cfg.get('quality_blocker'):
            prepared[source]={}
            continue
        if progress: progress('Preparing '+source)
        paths=cfg.get('paths',{}); obj={}
        if source=='epa_egrid' and 'regions' in paths:
            r=read_vector(_vsi(paths['regions']),cells).rename(columns={cfg.get('region_field','Subregion'):'subregion'})
            if 'workbook' in paths:
                attributes=egrid_attributes if egrid_attributes is not None else read_subregion_workbook(paths['workbook'],sheet=cfg.get('sheet','SRL23'),unit=cfg.get('unit','lb_per_mwh'))
                r=r.merge(attributes,on='subregion',how='left',validate='many_to_one')
            else: r['SRCO2RTA']=np.nan; r['SRC2ERTA']=np.nan
            obj['regions']=r
            if 'multiple_regions' in paths: obj['multiple']=read_vector(_vsi(paths['multiple_regions']),cells)
        elif source=='wri_aqueduct40' and 'baseline' in paths:
            obj['baseline']=read_vector(_vsi(paths['baseline'],cfg.get('zip_member')),cells,layer=cfg.get('layer','baseline_annual'),columns=['pfaf_id','bws_raw','bws_score','bws_cat'],where='pfaf_id > 0')
        elif source=='fema_nfhl':
            for key in ['hazards','surveyed']:
                if key in paths: obj[key]=read_vector(paths[key],cells)
                bounds=cfg.get('query_bounds_4326',{}).get(key)
                if bounds:
                    geom=shapely.segmentize(shapely.box(*bounds),.01)
                    obj['hazard_query' if key=='hazards' else 'surveyed_query']=gpd.GeoSeries([geom],crs=4326).to_crs(5070).iloc[0]
        elif source=='usgs_padus' and 'areas' in paths:
            obj['areas']=read_vector(paths['areas'],cells,layer=cfg.get('layer'),columns=['GAP_Sts','RastDrop'])
        elif source=='eia_energy_atlas':
            for key,path in paths.items():
                # Nearest distances require the whole mapped inventory, not a cell bbox.
                obj[key]=read_vector(path,cells,columns=[],bounded=False)
        elif source=='usfs_whp' and 'archive' in paths:
            extracted=extract_verified_member(paths['archive'],cfg['zip_member'],Path(paths['archive']).parents[3]/'interim'/'usfs_whp')
            obj={'wildfire_hazard_potential_whp2023':extracted}
        else: obj=paths
        prepared[source]=obj
    return prepared


def _feature_tiles(analysis,tile_size_cells,*,spatial,cell_side_m):
    """Yield deterministic local source envelopes without changing grid identity."""
    if spatial:
        required={'tile_id','row','col'}
        if not required.issubset(analysis.columns):
            raise ValueError('Spatial source preparation requires tile_id, row, col')
        if cell_side_m>MAX_PREPARATION_SPAN_M:
            raise ValueError('Grid cell side exceeds spatial source preparation bound')
        edge=max(1,int(MAX_PREPARATION_SPAN_M/cell_side_m))
        groups=analysis.groupby([analysis.tile_id,analysis.row//edge,analysis.col//edge],sort=True)
        tile_size_cells=min(tile_size_cells,625)
        frames=(frame for _,frame in groups)
    else:
        frames=[analysis]
    for frame in frames:
        for start in range(0,len(frame),tile_size_cells):
            yield frame.iloc[start:start+tile_size_cells].reset_index(drop=True)


def _summaries(cells,source,cfg,obj):
    empty=pd.DataFrame({'grid_id':cells.grid_id})
    if cfg.get('quality_blocker'): return empty
    if not obj: return empty
    if source=='usgs_annual_nlcd':
        return pd.DataFrame([dict(grid_id=c.grid_id,**summarize_land_cover(obj['land_cover'],c.geometry)) for c in cells.itertuples()])
    if source=='epa_egrid': return summarize_egrid(cells,obj['regions'],obj.get('multiple'),unit=cfg.get('unit','lb_per_mwh')) if 'regions' in obj else empty
    if source=='wri_aqueduct40': return summarize_water_stress(cells,obj['baseline'])
    if source=='fema_nfhl': return summarize_flood(cells,obj.get('hazards'),obj.get('surveyed'),hazard_query=obj.get('hazard_query'),surveyed_query=obj.get('surveyed_query'))
    if source=='usgs_padus': return summarize_protected(cells,obj['areas'])
    if source=='eia_energy_atlas':
        for metric,key in [('transmission_distance_km','transmission'),('power_plant_distance_km','power_plants'),('gas_pipeline_distance_km','pipelines')]:
            empty[metric]=distances_to_infrastructure(cells,obj.get(key))
        return empty
    if source=='noaa_ncei_climate':
        return pd.DataFrame([dict(grid_id=c.grid_id,**summarize_temperature(obj,c.geometry)) for c in cells.itertuples()])
    if source in {'usfs_wildfire_risk','usfs_whp'}:
        return pd.DataFrame([dict(grid_id=c.grid_id,**summarize_wildfire(obj,c.geometry)) for c in cells.itertuples()])
    return empty


def _coverage(source,metric,row):
    if metric+'_coverage_frac' in row: return float(row[metric+'_coverage_frac'])
    if metric=='egrid_multiple_subregion_overlap_frac': return 1. if pd.notna(row.get(metric)) else 0.
    if metric=='flood_surveyed_coverage_frac': return float(row.get('flood_surveyed_query_coverage_frac',0))
    if source=='fema_nfhl' and row.get('flood_hazard_query_coverage_frac',0)<1-1e-6:
        return float(row.get('flood_hazard_query_coverage_frac',0))
    key={'usgs_annual_nlcd':'nlcd_coverage_frac','epa_egrid':'egrid_coverage_frac',
         'wri_aqueduct40':'aqueduct_coverage_frac','fema_nfhl':'flood_coverage_frac',
         'usgs_padus':'padus_coverage_frac'}.get(source)
    if key:
        cov=row.get(key,0)
        return min(1.,float(cov)) if pd.notna(cov) else 0.
    # Infrastructure export coverage describes an inventory, not raster areal completeness.
    if source=='eia_energy_atlas': return None
    return 0.


def _tile(cells,source_inputs,prepared,data_mode,progress=None):
    values={'grid_id':cells.grid_id.tolist()}; provenance=[]
    for source,definitions in METRICS.items():
        if progress: progress('Analyzing '+source+f' for {len(cells)} cells')
        cfg=source_inputs.get(source,{})
        summary=_summaries(cells,source,cfg,prepared.get(source,{})).set_index('grid_id')
        for metric,(unit,field,base_status) in definitions.items():
            vals=[]; statuses=[]; confidences=[]; coverages=[]
            for grid_id in cells.grid_id:
                row=summary.loc[grid_id].to_dict() if grid_id in summary.index else {}
                value=row.get(metric); text=value if isinstance(value,str) else None
                numeric=None if text is not None or pd.isna(value) else float(value)
                present=numeric is not None or (text is not None and text not in {'{}','[]',''})
                # Count 0 with no valid regional coverage does not claim a measured metric.
                coverage=_coverage(source,metric,row)
                if metric.endswith('_n_subregions') or metric.endswith('_n_subbasins'):
                    present=present and (coverage or 0)>0
                status=base_status if present else 'unknown'
                confidence=('low' if base_status=='proxy' else ('high' if coverage==1 else 'medium')) if present else 'unknown'
                if present and coverage is not None and coverage<.95: confidence='low'
                reason=None if present else (cfg.get('quality_blocker') or row.get(metric+'_missing_reason') or ('source_nodata' if cfg.get('paths') else 'source_not_acquired'))
                if not present: numeric=None; text=None
                record=FeatureMetadata(grid_id=grid_id,metric=metric,value=numeric,value_text=text,unit=unit,
                   source_id=source,source_name=cfg.get('source_name',SOURCE_INFO[source][0]),
                   source_url=cfg.get('source_url',SOURCE_INFO[source][1]),source_field=field,
                   source_version=cfg.get('source_version',SOURCE_INFO[source][3]),data_year=cfg.get('data_year',SOURCE_INFO[source][2]),
                   retrieved_at=cfg.get('retrieved_at'),spatial_resolution=cfg.get('spatial_resolution',SOURCE_INFO[source][4]),
                   aggregation_method=cfg.get('aggregation_method','minimum study-intersection-polygon distance in EPSG:5070' if source=='eia_energy_atlas' else ('plurality category; lowest code tie' if metric.endswith('_category') else 'study-intersection area-weighted zonal/overlay')),
                   coverage_frac=coverage,status=status,confidence=confidence,missing_reason=reason,data_mode=data_mode,
                   method=cfg.get('method','See docs/data_dictionary.md; raw units retained; partial coverage is not extrapolated'))
                provenance.append(record.model_dump(mode='json'))
                vals.append(text if text is not None else numeric); statuses.append(status); confidences.append(confidence); coverages.append(coverage)
            values[metric]=vals
            values[metric+'_status']=statuses
            values[metric+'_confidence']=confidences
            if not metric.endswith('_coverage_frac'): values[metric+'_coverage_frac']=coverages
    return pd.DataFrame(values),pd.DataFrame(provenance)


def build_features(grid,source_inputs=None,output_dir=None,*,study_geometry=None,cache_dir=None,
                   tile_size_cells=625,resume=True,progress=None,prepare_per_tile=False):
    """Return/write a wide feature GeoDataFrame plus long provenance and JSON reports.

    ``grid`` is a path or Phase1 GeoDataFrame. ``source_inputs`` maps source IDs to
    metadata + explicit local ``paths`` (see default_source_inputs). Synthetic
    fixtures require source ``data_mode=synthetic`` and grid synthetic labels.
    Raster reads remain bounded by each cell. ``prepare_per_tile`` additionally
    prepares vector overlays in spatial tiles with at most 625 cells and 250 km
    per side. Nearest-distance inventories are loaded once in full; eGRID
    workbook attributes are read once. The default retains the legacy grouping.
    """
    grid=gpd.read_parquet(grid) if isinstance(grid,(str,Path)) else grid.copy()
    if grid.empty or grid.grid_id.duplicated().any(): raise ValueError('Grid must be nonempty with unique grid IDs')
    if grid.crs is None or grid.crs.to_epsg()!=5070: raise ValueError('Grid must be EPSG:5070')
    if grid.grid_definition_id.nunique()!=1: raise ValueError('Mixed grid definitions cannot be joined')
    modes=set(grid.data_mode)
    if len(modes)!=1: raise ValueError('Grid data modes must be uniform')
    mode=DataMode(next(iter(modes))); grid=grid.sort_values('grid_id').reset_index(drop=True)
    source_inputs=default_source_inputs() if source_inputs is None else source_inputs
    for cfg in source_inputs.values():
        if cfg.get('paths') and cfg.get('data_mode','real')!=mode.value:
            raise ValueError('Source and grid data modes disagree; synthetic sources cannot enter real outputs')
    output=Path(output_dir or 'data/processed'); cache=Path(cache_dir or 'data/interim/phase2_features')
    if tile_size_cells<1: raise ValueError('tile_size_cells must be positive')
    if study_geometry is None: study_geometry=load_conus_boundary().boundary
    analysis=grid.copy(); analysis.geometry=shapely.intersection(grid.geometry.values,study_geometry)
    expected=grid.study_area_intersection_km2.to_numpy()*1e6
    if not np.allclose(shapely.area(analysis.geometry.values),expected,rtol=1e-7,atol=.05):
        raise ValueError('Analysis study-intersection geometry does not match Phase1 recorded area')
    fingerprints={s:_source_fingerprint(c) for s,c in sorted(source_inputs.items())}
    package=Path(__file__).parent.parent
    code_files=[Path(__file__),*Path(__file__).parent.joinpath('sources').glob('*.py'),
                *[package/name for name in ['provenance.py','schemas.py','io.py']]]
    revision=hashlib.sha256(''.join(file_digest(p) for p in sorted(code_files)).encode()).hexdigest()
    base={'aggregation_version':AGGREGATION_VERSION,'code_sha256':revision,'sources':fingerprints,
          'grid_definition_id':grid.grid_definition_id.iloc[0],'data_mode':mode.value}
    if prepare_per_tile:
        base['source_preparation']={'mode':'spatial_tiles','maximum_span_m':MAX_PREPARATION_SPAN_M,
                                    'maximum_cells':min(tile_size_cells,625)}
    base_key=hashlib.sha256(json.dumps(base,sort_keys=True,default=str).encode()).hexdigest()
    all_values=[]; all_provenance=[]; resumed=0; prepared=None; shared=None; egrid_attributes=None; keys=[]
    bounds=grid.bounds
    cell_side_m=float(max((bounds.maxx-bounds.minx).max(),(bounds.maxy-bounds.miny).max()))
    for cells in _feature_tiles(analysis,tile_size_cells,spatial=prepare_per_tile,cell_side_m=cell_side_m):
        subset=hashlib.sha256(pd.util.hash_pandas_object(cells.drop(columns='geometry'),index=False).values.tobytes()+b''.join(cells.geometry.to_wkb().values)).hexdigest()
        key=hashlib.sha256((base_key+subset).encode()).hexdigest(); keys.append(key)
        folder=cache/key; vp=folder/'features.parquet'; pp=folder/'provenance.parquet'; checkpoint=folder/'checkpoint.json'
        cached=json.loads(checkpoint.read_text()) if resume and checkpoint.exists() else None
        if cached and vp.exists() and pp.exists() and cached.get('files')=={'features':file_digest(vp),'provenance':file_digest(pp)}:
            vals=pd.read_parquet(vp); prov=pd.read_parquet(pp); resumed+=1
        else:
            if prepare_per_tile:
                if shared is None:
                    shared=_prepare(analysis,{s:c for s,c in source_inputs.items() if s not in BOUNDED_VECTOR_SOURCES},progress)
                    egrid=source_inputs.get('epa_egrid',{})
                    if not egrid.get('quality_blocker') and 'workbook' in egrid.get('paths',{}):
                        egrid_attributes=read_subregion_workbook(egrid['paths']['workbook'],sheet=egrid.get('sheet','SRL23'),unit=egrid.get('unit','lb_per_mwh'))
                prepared=dict(shared)
                prepared.update(_prepare(cells,{s:c for s,c in source_inputs.items() if s in BOUNDED_VECTOR_SOURCES},progress,
                                         egrid_attributes=egrid_attributes))
            elif prepared is None: prepared=_prepare(analysis,source_inputs,progress)
            vals,prov=_tile(cells,source_inputs,prepared,mode,progress)
            write_parquet(vals,vp,schema_name='GeographicFeatureTile',schema_version=SCHEMA_VERSION,data_mode=mode,grid_definition_id=base['grid_definition_id'])
            write_parquet(prov,pp,schema_name='FeatureMetadata',schema_version=SCHEMA_VERSION,data_mode=mode,grid_definition_id=base['grid_definition_id'])
            checkpoint.write_text(json.dumps({'key':key,'files':{'features':file_digest(vp),'provenance':file_digest(pp)}}),encoding='utf-8')
        all_values.append(vals); all_provenance.append(prov)
    values=pd.concat(all_values,ignore_index=True); prov=pd.concat(all_provenance,ignore_index=True).sort_values(['grid_id','metric']).reset_index(drop=True)
    result=grid.merge(values,on='grid_id',how='left',validate='one_to_one')
    if len(result)!=len(grid) or prov.duplicated(['grid_id','metric']).any(): raise RuntimeError('Output cell/provenance identity violation')
    output.mkdir(parents=True,exist_ok=True)
    write_geoparquet(result,output/'us_grid_dataset.parquet',schema_name='GeographicFeatureDataset',schema_version=SCHEMA_VERSION,data_mode=mode,grid_definition_id=base['grid_definition_id'])
    write_parquet(prov,output/'feature_provenance.parquet',schema_name='FeatureMetadata',schema_version=SCHEMA_VERSION,data_mode=mode,grid_definition_id=base['grid_definition_id'])
    report={'schema_version':SCHEMA_VERSION,'data_mode':mode.value,'input_cells':len(grid),'output_cells':len(result),
            'analysis_extent':f'provided grid of {len(grid)} cells; source coverage reported separately',
            'analysis_bounds_5070_m':[float(value) for value in analysis.total_bounds],
            'analysis_study_area_km2':float(expected.sum()/1e6),
            'resumed_tiles':resumed,'processed_tiles':len(keys)-resumed,'sources':{}}
    for source,definitions in METRICS.items():
        source_prov=prov.loc[prov.source_id==source]; known=source_prov.loc[source_prov.status!='unknown']
        counts={m:int((source_prov.loc[source_prov.metric==m,'status']!='unknown').sum()) for m in definitions}
        coverage=source_prov.coverage_frac.dropna()
        ready=all(n==len(grid) for n in counts.values()) and (coverage.empty or coverage.min()>=1-1e-6)
        acquired=bool(source_inputs.get(source,{}).get('paths'))
        report['sources'][source]={'implemented':True,'acquired':acquired,'analyzed':bool(len(known)),
            'status':'READY' if ready else ('PARTIAL' if acquired else 'BLOCKED'),
            'analyzed_cells':int(known.grid_id.nunique()),'metric_nonmissing_cells':counts,
            'coverage_min':float(coverage.min()) if len(coverage) else None,'coverage_max':float(coverage.max()) if len(coverage) else None,
            'usable_local_inputs':list(source_inputs.get(source,{}).get('paths',{})),
            'remaining_requirements':[] if ready else ['Inspect metric coverage and source-specific limitations; provide official local files for missing geography/fields']}
    (output/'coverage_report.json').write_text(json.dumps(report,indent=2,sort_keys=True),encoding='utf-8')
    manifest=dict(base,selected_grid_ids=grid.grid_id.tolist(),tile_keys=keys,source_inputs=fingerprints,
                  outputs={n:{'sha256':file_digest(output/n),'bytes':(output/n).stat().st_size} for n in ['us_grid_dataset.parquet','feature_provenance.parquet']})
    (output/'data_manifest.json').write_text(json.dumps(manifest,indent=2,sort_keys=True,default=str),encoding='utf-8')
    return result
