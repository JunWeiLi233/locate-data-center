"""Reusable county economic context and complete candidate×county relationships.

This layer never changes screening, technical metrics, weights, or rankings.
Candidate denominators use full saved EPSG:5070 grid geometry. Generalized
cartographic coastlines may leave uncovered area; shares are never renormalized.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import re

import geopandas as gpd
import numpy as np
import pandas as pd
import pyarrow.parquet as pq
import shapely
import yaml

from dc_locator.io import read_parquet_metadata,write_geoparquet,write_parquet
from dc_locator.provenance import DataMode
from .sources import saipe
from .sources.ingestion import file_digest

SCHEMA_VERSION='1.0.0'
METHOD_VERSION='county-economic-context-v1'


@dataclass(frozen=True)
class SocioeconomicCountyArtifacts:
    county_path: Path
    metadata_path: Path
    metadata: dict


@dataclass(frozen=True)
class SocioeconomicArtifacts:
    county_path: Path
    crosswalk_path: Path
    coverage_path: Path
    metadata_path: Path
    metadata: dict


def load_config(root, path='configs/socioeconomic.yaml') -> dict:
    path=Path(path)
    path=path if path.is_absolute() else Path(root)/path
    config=yaml.safe_load(path.read_text(encoding='utf-8'))
    _validate_config(config)
    return config


def _validate_config(config):
    if not isinstance(config.get('socioeconomic_enabled'),bool):
        raise ValueError('Socioeconomic config requires explicit socioeconomic_enabled boolean')
    if config.get('schema_version') != SCHEMA_VERSION or config.get('saipe_year') != 2024:
        raise ValueError('Socioeconomic config requires schema 1.0.0 and SAIPE year 2024')
    if config.get('boundary_type') != 'cartographic_500k' or config.get('boundary_year') not in {2023,2025}:
        raise ValueError('Only authorized 2023/2025 cartographic county geometry is supported')
    for year in (2023,2025):
        path=Path(config['county_boundaries'][year])
        if path.name != f'cb_{year}_us_county_500k.zip':
            raise ValueError('County archive filename must match boundary year and cartographic source')
    if not 1 <= config.get('chunk_size',0) <= 10000 or not 1 <= config.get('max_grid_cells',0) <= 200000:
        raise ValueError('Socioeconomic grid/chunk limits exceed bounded saved-grid policy')
    if config.get('confidence',{}).get('value') != 'medium' or config['confidence'].get('basis') != 'project_assumption':
        raise ValueError('SAIPE qualitative confidence requires the documented medium project assessment')
    if config.get('percentiles',{}).get('method') != 'average_rank_endpoints_0_100_singleton_50':
        raise ValueError('Unsupported percentile method')


def _settings(root,config,boundary_year):
    config=load_config(root) if config is None else config
    _validate_config(config)
    year=config['boundary_year'] if boundary_year is None else boundary_year
    if year not in {2023,2025}:
        raise ValueError('Unsupported cartographic boundary year')
    archive=(Path(root)/config['county_boundaries'][year]).resolve()
    archive.relative_to((Path(root)/'data/raw').resolve())
    if archive.name != f'cb_{year}_us_county_500k.zip':
        raise ValueError('Boundary vintage does not match archive filename')
    return config,year,archive


def source_availability(root,*,config=None,boundary_year=None) -> dict:
    """Cheap capability inventory only; existence is not checksum verification."""
    config,year,archive=_settings(root,config,boundary_year)
    data,layout=saipe.source_paths(root,config['saipe_year'])
    acquired=all(p.is_file() for p in (archive,data,layout))
    return {'enabled':config['socioeconomic_enabled'],'acquired':acquired,
            'available':config['socioeconomic_enabled'] and acquired,'checksum_verified':False,
            'boundary_year':year,'socioeconomic_year':config['saipe_year'],
            'boundary_type':'cartographic_500k','source_paths':[str(p) for p in (archive,data,layout)]}


def socioeconomic_available(root) -> bool:
    """Existence-only inventory; callers still verify sources when loading."""
    try:
        return source_availability(root)['available']
    except (FileNotFoundError,KeyError,TypeError,ValueError):
        return False


def _verified_source(path,root,expected_url):
    if not path.is_file():
        raise FileNotFoundError(f'Official socioeconomic source not cached: {path}')
    entries=[]
    for name in ('download_log.json','download_manifest.json'):
        manifest=path.parent/name
        if manifest.is_file():
            obj=json.loads(manifest.read_text(encoding='utf-8'))
            entries.extend(obj if isinstance(obj,list) else obj.values())
    entry=next((e for e in entries if isinstance(e,dict) and
        Path(e.get('path','')).name==path.name and e.get('url')==expected_url),None)
    digest=file_digest(path)
    if not entry or entry.get('bytes')!=path.stat().st_size or entry.get('sha256')!=digest:
        raise ValueError(f'Official source manifest URL/size/checksum mismatch: {path.name}')
    return {'path':path.relative_to(Path(root).resolve()).as_posix(),'url':expected_url,
            'sha256':digest,'bytes':path.stat().st_size,
            'retrieved_at_utc':entry.get('retrieved_at_utc',entry.get('retrieved_at'))}


def _identity(binding):
    return hashlib.sha256(json.dumps(binding,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def _code_binding():
    return {Path(p).name:file_digest(p) for p in (__file__,saipe.__file__)}


def _cache_manifest(path,binding,outputs,cached_only):
    if not path.exists():
        if cached_only:
            raise FileNotFoundError(f'No verified socioeconomic cache: {path}')
        return None
    metadata=json.loads(path.read_text(encoding='utf-8'))
    if metadata.get('binding')!=json.loads(json.dumps(binding)) or any(not p.is_file() or
        metadata.get('output_sha256',{}).get(p.name)!=file_digest(p) for p in outputs):
        raise ValueError('Socioeconomic cache binding/output checksum mismatch')
    return metadata


def _save_manifest(path,binding,outputs,details):
    metadata={'schema_version':SCHEMA_VERSION,'method_version':METHOD_VERSION,
              'created_at_utc':datetime.now(timezone.utc).isoformat(),
              'binding':binding,'output_sha256':{p.name:file_digest(p) for p in outputs},**details}
    partial=path.with_suffix('.json.part')
    partial.write_text(json.dumps(metadata,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    partial.replace(path)
    return metadata


def ensure_county_geography(root,*,config=None,boundary_year=None,cached_only=False,acquire=False):
    root=Path(root).resolve()
    config,year,archive=_settings(root,config,boundary_year)
    if not config['socioeconomic_enabled']:
        raise ValueError('Socioeconomic geography is disabled by config')
    if cached_only and acquire:
        raise ValueError('Cached-only socioeconomic access cannot acquire sources')
    if acquire:
        saipe.acquire_saipe(root,year=config['saipe_year'])
    data,layout=saipe.source_paths(root,config['saipe_year'])
    sources=[_verified_source(archive,root,f'https://www2.census.gov/geo/tiger/GENZ{year}/shp/{archive.name}'),
        _verified_source(data,root,saipe.SOURCE_URL.format(year=2024,short='24')),
        _verified_source(layout,root,saipe.LAYOUT_URL.format(year=2024))]
    binding={'config':config,'boundary_year':year,'sources':sources,'code':_code_binding()}
    folder=root/'data/processed/socioeconomic'/_identity(binding)[:24]
    county_path=folder/'counties.parquet'; metadata_path=folder/'county_manifest.json'
    metadata=_cache_manifest(metadata_path,binding,[county_path],cached_only)
    if metadata is None:
        estimates=saipe.parse_saipe(data.read_text(encoding='utf-8'),year=config['saipe_year'])
        counties=gpd.read_file(f'zip://{archive}')
        if counties.crs is None or not {'GEOID','NAME','STATEFP','COUNTYFP'} <= set(counties):
            raise ValueError('Cartographic county source CRS/schema missing')
        counties=counties.loc[~counties.STATEFP.isin(saipe.EXCLUDED_STATES),['GEOID','NAME','STATEFP','COUNTYFP','geometry']]
        counties=counties.rename(columns={'GEOID':'county_geoid','NAME':'county_name','STATEFP':'state_fips','COUNTYFP':'county_fips'})
        if not counties.county_geoid.str.fullmatch(r'\d{5}').all() or not (counties.state_fips+counties.county_fips==counties.county_geoid).all():
            raise ValueError('Invalid cartographic county GEOID/FIPS')
        counties=counties.to_crs(5070)
        counties.geometry=shapely.make_valid(counties.geometry.values)
        counties=counties.dissolve(by='county_geoid',as_index=False,aggfunc='first').sort_values('county_geoid').reset_index(drop=True)
        if counties.geometry.is_empty.any() or not (counties.area>0).all():
            raise ValueError('County geometry must have positive area')
        missing_source=sorted(set(counties.county_geoid)-set(estimates.county_geoid))
        missing_geometry=sorted(set(estimates.county_geoid)-set(counties.county_geoid))
        counties=counties.merge(estimates.drop(columns=['state_fips','county_fips']),on='county_geoid',how='left',validate='one_to_one')
        absent=counties.socioeconomic_year.isna()
        counties['socioeconomic_year']=config['saipe_year']
        for column in estimates:
            if column.endswith('_status') or column.endswith('_confidence'):
                counties.loc[absent,column]='unknown'
            elif column.endswith('_missing_reason'):
                fiscal=any(column==metric+'_missing_reason' for metric in saipe.FISCAL_FIELDS)
                counties.loc[absent,column]='future_fiscal_inputs_not_acquired' if fiscal else 'county_geoid_absent_from_saipe_source'
            elif column.endswith(('_unit','_source_id','_source_url','_source_field','_method')):
                constants=estimates[column].dropna().unique()
                if len(constants)==1:
                    counties.loc[absent,column]=constants[0]
            elif column.endswith('_data_year'):
                counties.loc[absent,column]=config['saipe_year']
        counties['boundary_year']=year
        counties['boundary_type']='cartographic_500k'
        counties['geometry_vintage_mismatch']=year!=config['saipe_year']
        counties['economic_observation_type']='SAIPE model-based county estimate, not direct household measurement'
        write_geoparquet(counties,county_path,schema_name='county_socioeconomic_geography',
            schema_version=SCHEMA_VERSION,data_mode=DataMode.REAL,grid_definition_id=f'county-cartographic-{year}-500k')
        metadata=_save_manifest(metadata_path,binding,[county_path],{
            'county_count':len(counties),'boundary_year':year,'socioeconomic_year':config['saipe_year'],
            'boundary_type':'cartographic_500k','geometry_warning':config['geometry_warning'],
            'geometry_vintage_mismatch':year!=config['saipe_year'],
            'unmatched_boundary_geoids':missing_source,'unmatched_saipe_geoids':missing_geometry,
            'percentile_universe':'all CONUS SAIPE counties with valid metric, before geometry/grid joins',
            'percentile_method':saipe.PERCENTILE_METHOD,'moe_method':saipe.MOE_METHOD,
            'percentile_valid_count':{'poverty_rate':int(estimates.poverty_rate.notna().sum()),
                                     'median_household_income':int(estimates.median_household_income.notna().sum())},
            'uncertainty_interval_confidence_level':0.90,'technical_scores_modified':False})
    return SocioeconomicCountyArtifacts(county_path,metadata_path,metadata)


def candidate_county_crosswalk(grid,counties,*,chunk_size=10000):
    """All positive overlaps; dissolved fragments, full grid area, stable pairs."""
    if grid.crs is None or counties.crs is None or grid.crs.to_epsg()!=5070 or counties.crs.to_epsg()!=5070:
        raise ValueError('Candidate/county geometries require EPSG:5070')
    if not 1<=chunk_size<=10000:
        raise ValueError('Invalid bounded crosswalk chunk size')
    if grid.geometry.isna().any() or grid.geometry.is_empty.any() or not grid.geometry.is_valid.all():
        raise ValueError('Candidate geometries must be valid, non-null and non-empty')
    if grid.grid_id.isna().any() or grid.grid_id.duplicated().any() or not (grid.area>0).all():
        raise ValueError('Candidate IDs must be unique and geometries positive-area')
    counties=counties.dissolve(by='county_geoid',as_index=False,aggfunc='first').sort_values('county_geoid').reset_index(drop=True)
    pieces=[]
    for start in range(0,len(grid),chunk_size):
        cells=grid.iloc[start:start+chunk_size]
        ci,ri=counties.sindex.query(cells.geometry,predicate='intersects')
        area=shapely.area(shapely.intersection(cells.geometry.values[ci],counties.geometry.values[ri]))
        positive=area>0
        ci,ri,area=ci[positive],ri[positive],area[positive]
        if len(area):
            total=shapely.area(cells.geometry.values[ci])
            pieces.append(pd.DataFrame({'candidate_id':cells.grid_id.values[ci],
                'county_geoid':counties.county_geoid.values[ri],
                'candidate_area_km2':total/1e6,'intersection_area_km2':area/1e6,
                'overlap_fraction':area/total}))
    columns=['candidate_id','county_geoid','candidate_area_km2','intersection_area_km2','overlap_fraction']
    crosswalk=pd.concat(pieces,ignore_index=True) if pieces else pd.DataFrame(columns=columns)
    crosswalk=crosswalk.merge(counties.drop(columns='geometry'),on='county_geoid',how='left',validate='many_to_one')
    crosswalk=crosswalk.sort_values(['candidate_id','county_geoid']).reset_index(drop=True)
    if crosswalk.duplicated(['candidate_id','county_geoid']).any() or (crosswalk.overlap_fraction>1+1e-10).any():
        raise ValueError('Invalid duplicate or excessive county overlap')
    coverage=pd.DataFrame({'candidate_id':grid.grid_id.values,'candidate_area_km2':grid.area.values/1e6})
    totals=crosswalk.groupby('candidate_id').agg(county_coverage_fraction=('overlap_fraction','sum'),county_count=('county_geoid','size'))
    coverage=coverage.merge(totals,on='candidate_id',how='left',validate='one_to_one')
    coverage[['county_coverage_fraction','county_count']]=coverage[['county_coverage_fraction','county_count']].fillna(0)
    coverage['county_count']=coverage.county_count.astype(int)
    coverage['uncovered_fraction']=np.maximum(0,1-coverage.county_coverage_fraction)
    coverage['coverage_reason']=np.select([coverage.county_count.eq(0),coverage.county_coverage_fraction<1-1e-10,coverage.county_coverage_fraction>1+1e-10],
        ['no_positive_county_overlap','cartographic_boundary_uncovered_area','overlapping_county_geometry'],default=None)
    return crosswalk,coverage.sort_values('candidate_id').reset_index(drop=True)


def ensure_socioeconomic_geography(root,grid_path,*,config=None,boundary_year=None,cached_only=False,acquire=False):
    root=Path(root).resolve(); grid_path=Path(grid_path)
    grid_path=grid_path.resolve() if grid_path.is_absolute() else (root/grid_path).resolve()
    relative=grid_path.relative_to(root)
    if relative.parts[0]!='runs' and relative.parts[:2]!=('data','processed'):
        raise ValueError('Socioeconomic candidate grid must be an owned saved real geography artifact')
    config=load_config(root) if config is None else config
    meta=read_parquet_metadata(grid_path)
    if meta.get('data_mode')!='real' or not meta.get('grid_definition_id'):
        raise ValueError('Socioeconomic grid requires real metadata and grid definition identity')
    if pq.ParquetFile(grid_path).metadata.num_rows>config['max_grid_cells']:
        raise ValueError('Saved candidate grid exceeds bounded socioeconomic 200,000-cell limit')
    county=ensure_county_geography(root,config=config,boundary_year=boundary_year,cached_only=cached_only,acquire=acquire)
    grid_hash=file_digest(grid_path)
    folder=county.county_path.parent/'grids'/grid_hash[:24]
    crosswalk_path=folder/'candidate_county_crosswalk.parquet'; coverage_path=folder/'candidate_county_coverage.parquet'
    metadata_path=folder/'manifest.json'
    binding={'county_binding':county.metadata['binding'],'county_sha256':file_digest(county.county_path),
             'grid_path':relative.as_posix(),'grid_sha256':grid_hash,'grid_metadata':meta}
    metadata=_cache_manifest(metadata_path,binding,[crosswalk_path,coverage_path],cached_only)
    if metadata is None:
        grid=gpd.read_parquet(grid_path,columns=['grid_id','geometry'])
        if not grid.grid_id.str.fullmatch(r'g\d+m-r\d+-c\d+').all():
            raise ValueError('Candidate grid IDs violate fixed national lattice identity')
        counties=gpd.read_parquet(county.county_path)
        crosswalk,coverage=candidate_county_crosswalk(grid,counties,chunk_size=config['chunk_size'])
        for frame,path,schema in [(crosswalk,crosswalk_path,'candidate_county_socioeconomic_crosswalk'),
                                 (coverage,coverage_path,'candidate_county_coverage')]:
            write_parquet(frame,path,schema_name=schema,schema_version=SCHEMA_VERSION,data_mode=DataMode.REAL,grid_definition_id=meta['grid_definition_id'])
        metadata=_save_manifest(metadata_path,binding,[crosswalk_path,coverage_path],{
            'candidate_count':len(grid),'relationship_count':len(crosswalk),
            'boundary_year':county.metadata['boundary_year'],'socioeconomic_year':config['saipe_year'],
            'boundary_type':'cartographic_500k','geometry_warning':config['geometry_warning'],
            'coverage_denominator':'full saved grid geometry in EPSG:5070; no renormalization',
            'uncovered_candidate_count':int((coverage.uncovered_fraction>1e-10).sum()),
            'no_county_candidate_count':int(coverage.county_count.eq(0).sum()),
            'excess_coverage_candidate_count':int((coverage.county_coverage_fraction>1+1e-10).sum()),
            'technical_scores_modified':False,'county_metadata_path':county.metadata_path.relative_to(root).as_posix()})
    return SocioeconomicArtifacts(county.county_path,crosswalk_path,coverage_path,metadata_path,metadata)
