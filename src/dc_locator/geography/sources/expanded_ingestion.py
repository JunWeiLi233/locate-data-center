"""Explicit public Phase 5 acquisition, separate from feature computation.

Requests are source/version/parameter keyed; every cache hit verifies bytes and
SHA256. No credentials, forms, or HTTP calls occur in the analysis builder.
"""
from datetime import datetime, timezone
import json
import math
from pathlib import Path
from urllib.parse import urlencode

import requests

from .ingestion import (download_public, file_digest, request_identity,
                        verified_cached_request, USER_AGENT, PROJECT_MAX_BYTES)


def acquire_file(raw_dir, source_id, version, url, filename, *, parameters=None,
                 license_note='Public official data; see source-specific terms'):
    params=parameters or {}
    key=request_identity(source_id,version,{'url':url,'parameters':params})
    path=Path(raw_dir)/source_id/'phase5'/key/filename
    if verified_cached_request(path,key): return path
    full_url=url+('?' + urlencode(params) if params else '')
    return download_public(full_url,path,raw_dir=raw_dir,source_id=source_id,
                           version=version,license_note=license_note,request_key=key)


def acquire_eia861(raw_dir):
    return acquire_file(raw_dir,'eia861','2024 final, updated 2025-12-03',
        'https://www.eia.gov/electricity/data/eia861/zip/f8612024.zip','f8612024.zip',
        license_note='U.S. Government public data')


def acquire_usdm(raw_dir, *, area='TX', start='1/1/2000', end='12/31/2024'):
    return acquire_file(raw_dir,'usdm','weekly county cumulative area, snapshot',
        'https://usdmdataservices.unl.edu/api/CountyStatistics/GetDroughtSeverityStatisticsByAreaPercent',
        'county_drought.csv',parameters={'aoi':area,'startdate':start,'enddate':end,'statisticsType':1},
        license_note='USDM public data; credit NDMC/USDA/NOAA/NASA')


def acquire_ibtracs(raw_dir):
    return acquire_file(raw_dir,'noaa_ibtracs','v04r01 snapshot',
        'https://www.ncei.noaa.gov/data/international-best-track-archive-for-climate-stewardship-ibtracs/v04r01/access/csv/ibtracs.NA.list.v04r01.csv',
        'ibtracs.NA.list.v04r01.csv',license_note='NOAA public data; cite IBTrACS')


def acquire_wind_index(raw_dir):
    return acquire_file(raw_dir,'nlr_wind_toolkit','site index v1 2016-10-17',
        'https://data.nlr.gov/system/files/54/wtk_site_metadata.csv','wtk_site_metadata.csv',
        license_note='Public domain, DOI 10.7799/1329290')


def acquire_arcgis(raw_dir,source_id,version,endpoint,bounds_4326,*,max_features=100000):
    """Native ESRI JSON, one bounded ID query and geometry batches.

    Query footprint is recorded independently from returned feature geometries.
    Empty queried areas are distinguishable from locations outside acquisition.
    """
    bounds=list(map(float,bounds_4326))
    if len(bounds)!=4 or not all(math.isfinite(b) for b in bounds) or not (-180<=bounds[0]<bounds[2]<=180) or not (-90<=bounds[1]<bounds[3]<=90):
        raise ValueError('Expected finite ordered EPSG:4326 bounds')
    params={'f':'json','where':'1=1','geometry':','.join(map(str,bounds)),
            'geometryType':'esriGeometryEnvelope','inSR':4326,
            'spatialRel':'esriSpatialRelIntersects','returnIdsOnly':'true'}
    key=request_identity(source_id,version,{'endpoint':endpoint,'parameters':params,'fields':'*'})
    path=Path(raw_dir)/source_id/'phase5'/key/'features.esri.json'
    if verified_cached_request(path,key): return path
    s=requests.Session(); s.headers['User-Agent']=USER_AGENT
    meta=s.get(endpoint,params={'f':'json'},timeout=60); meta.raise_for_status(); metadata=meta.json()
    object_id_field=metadata.get('objectIdField') or next((f['name'] for f in metadata.get('fields',[]) if f.get('type')=='esriFieldTypeOID'),None)
    if not object_id_field: raise ValueError('Official ArcGIS object ID field is required')
    r=s.get(endpoint+'/query',params=params,timeout=120); r.raise_for_status(); obj=r.json()
    if 'error' in obj: raise ValueError(f'Official ArcGIS query unavailable: {obj["error"]}')
    ids=sorted(obj.get('objectIds') or [])
    if len(ids)>max_features: raise ValueError('Bounded feature budget exceeded; request smaller tiles')
    features=[]; fields=None
    for start in range(0,len(ids),100):
        r=s.get(endpoint+'/query',params={'f':'json','objectIds':','.join(map(str,ids[start:start+100])),
              'outFields':'*','outSR':4326,'returnGeometry':'true'},timeout=120)
        r.raise_for_status(); batch=r.json()
        if 'error' in batch or batch.get('exceededTransferLimit'):
            raise ValueError('Incomplete ArcGIS native batch rejected')
        items=batch.get('features',[])
        returned=[f.get('attributes',{}).get(object_id_field) for f in items]
        if len(returned)!=len(set(returned)) or set(returned)!=set(ids[start:start+100]):
            raise ValueError('ArcGIS returned ID set differs from requested batch')
        fields=batch.get('fields',fields); features.extend(items)
    all_ids=[f['attributes'][object_id_field] for f in features]
    if len(all_ids)!=len(set(all_ids)) or set(all_ids)!=set(ids): raise ValueError('ArcGIS ID and geometry sets disagree')
    payload={'spatialReference':{'wkid':4326},'fields':fields or metadata.get('fields',[]),
             'geometryType':metadata.get('geometryType'),'features':features,
             'acquisition':{'bounds_4326':bounds,'complete':True,'object_ids':ids,
                            'endpoint':endpoint,'source_version':version},'service_metadata':metadata}
    encoded=json.dumps(payload,sort_keys=True).encode()
    total=sum(p.stat().st_size for p in Path(raw_dir).rglob('*') if p.is_file())
    if total+len(encoded)>PROJECT_MAX_BYTES: raise ValueError('Authorized raw budget exceeded')
    path.parent.mkdir(parents=True,exist_ok=True)
    temporary=path.with_suffix('.part'); temporary.write_bytes(encoded); temporary.replace(path)
    record={'url':r.url,'path':str(path),'source_id':source_id,'version':version,
            'bytes':len(encoded),'sha256':file_digest(path),'request_identity':key,
            'bounds_4326':bounds,'feature_count':len(features),'license':'Public official data',
            'retrieved_at_utc':datetime.now(timezone.utc).isoformat()}
    (path.parent/'download_log.json').write_text(json.dumps([record],indent=2),encoding='utf-8')
    return path


def acquire_ntad_rail(raw_dir,bounds_4326):
    return acquire_arcgis(raw_dir,'ntad','rail network 2026-07-21',
      'https://services.arcgis.com/xOi1kZaI0eWDREZv/ArcGIS/rest/services/NTAD_North_American_Rail_Network_Lines/FeatureServer/0',bounds_4326)


def acquire_nex_subset(raw_dir,endpoint,*,model,scenario,year,bounds_4326,variable):
    """NCSS NetCDF3 bounded subset of one documented model/scenario/year file."""
    if len(bounds_4326)!=4 or not all(math.isfinite(v) for v in bounds_4326) or not (-180<=bounds_4326[0]<bounds_4326[2]<=180) or not (-90<=bounds_4326[1]<bounds_4326[3]<=90):raise ValueError('Invalid native NEX request bounds')
    x0,y0,x1,y1=bounds_4326
    params={'var':variable,'north':y1,'south':y0,'west':x0,'east':x1,'horizStride':1,
            'time_start':f'{year}-01-01T00:00:00Z','time_end':f'{year}-12-31T23:59:59Z',
            'accept':'netcdf3','addLatLon':'true'}
    return acquire_file(raw_dir,'nasa_nex_gddp_cmip6',f'{model}/{scenario}/{year}',endpoint,
                        f'{variable}_{year}.nc',parameters=params,
                        license_note='NASA NEX-GDDP-CMIP6 public data; cite model and dataset')
