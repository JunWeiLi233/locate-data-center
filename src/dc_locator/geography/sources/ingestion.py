"""Public downloads, verified manifests, and bounded ArcGIS source acquisition.

No access-control bypass, per-cell requests, or implicit downloads in feature
building. HTTP errors are surfaced; all downloaded content carries SHA256.
"""
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import zipfile

import requests

USER_AGENT='dc_locator/0.1 (research prototype)'
PROJECT_MAX_BYTES=60_000_000_000


def request_identity(source,version,parameters):
    return hashlib.sha256(json.dumps({'source':source,'version':version,'parameters':parameters},sort_keys=True).encode()).hexdigest()[:20]


def verified_cached_request(path,identity):
    path=Path(path)
    if not path.exists(): return False
    manifest=path.parent/'download_log.json'
    entries=json.loads(manifest.read_text()) if manifest.exists() else []
    entry=next((e for e in entries if e.get('path')==str(path) and e.get('request_identity')==identity),None)
    if entry is None or entry['bytes']!=path.stat().st_size or entry['sha256']!=file_digest(path):
        raise ValueError('Bounded cache request identity/size/checksum mismatch')
    return True


def file_digest(path):
    path=Path(path)
    digest=hashlib.sha256()
    if path.is_dir():
        for member in sorted(f for f in path.rglob('*') if f.is_file()):
            digest.update(member.relative_to(path).as_posix().encode())
            digest.update(file_digest(member).encode())
    else:
        with path.open('rb') as handle:
            for chunk in iter(lambda:handle.read(1024*1024),b''):
                digest.update(chunk)
    return digest.hexdigest()


def inventory_downloads(raw_dir):
    """Normalize inherited list/files/entries/downloads manifest conventions."""
    records=[]
    for manifest in sorted(Path(raw_dir).rglob('download_log*.json')):
        obj=json.loads(manifest.read_text(encoding='utf-8'))
        entries=obj if isinstance(obj,list) else obj.get('files',obj.get('entries',obj.get('downloads',[])))
        for entry in entries:
            if isinstance(entry,dict) and entry.get('path'):
                records.append(dict(entry,manifest=str(manifest)))
    return records


def extract_verified_member(archive,member,cache_dir,*,max_member_bytes=1_000_000_000):
    """Extract one bounded member once; validate source/member hash on every reuse.

    This avoids repeatedly decompressing national raster archives for cell windows.
    Huge optional raster payloads (e.g. PAD-US >60 GB) are never extracted.
    """
    archive=Path(archive); digest=file_digest(archive)
    key=request_identity(digest,'zip-member-v1',{'member':member})
    folder=Path(cache_dir)/key; target=folder/Path(member).name; log=folder/'member_manifest.json'
    if log.exists() and target.exists():
        info=json.loads(log.read_text())
        if info.get('archive_sha256')!=digest or info.get('member')!=member or info.get('sha256')!=file_digest(target) or info.get('bytes')!=target.stat().st_size:
            raise ValueError('Extracted member cache checksum mismatch')
        return target
    with zipfile.ZipFile(archive) as z:
        info=z.getinfo(member)
        if info.file_size>max_member_bytes: raise ValueError('Archive member exceeds bounded extraction budget')
        folder.mkdir(parents=True,exist_ok=True); partial=target.with_suffix(target.suffix+'.part')
        with z.open(member) as source,partial.open('wb') as sink:
            for chunk in iter(lambda:source.read(1024*1024),b''): sink.write(chunk)
        if partial.stat().st_size!=info.file_size: raise ValueError('Extracted member byte count mismatch')
        partial.replace(target)
        log.write_text(json.dumps({'archive_sha256':digest,'member':member,'member_crc32':info.CRC,'bytes':info.file_size,'sha256':file_digest(target)},indent=2),encoding='utf-8')
    return target


def download_public(url,path,*,raw_dir,source_id,version,license_note,
                    expected_bytes=None,expected_sha256=None,session=None,request_key=None):
    """Bounded streamed download; verified cache reuse; atomic manifest update.

    No unknown-size payload can exceed remaining cumulative budget. HTML/login/
    CAPTCHA responses are rejected, never interpreted as a raster or workbook.
    """
    path=Path(path); raw_dir=Path(raw_dir)
    path.resolve().relative_to(raw_dir.resolve())
    manifest=path.parent/'download_log.json'
    existing=json.loads(manifest.read_text()) if manifest.exists() else []
    if not isinstance(existing,list):
        raise ValueError('New acquisition manifests must be lists; use a dedicated acquisition subdirectory')
    cached=next((e for e in existing if e['path']==str(path)),None)
    if path.exists():
        digest=file_digest(path)
        if cached and cached['sha256']==digest and cached['bytes']==path.stat().st_size:
            return path
        if expected_sha256 and digest==expected_sha256:
            return path
        raise ValueError('Existing unverified file; inspect before replacement')
    total=sum(f.stat().st_size for f in raw_dir.rglob('*') if f.is_file())
    budget=PROJECT_MAX_BYTES-total
    if expected_bytes is not None and expected_bytes>budget:
        raise ValueError('Download would exceed authorized project 60 GB raw-data budget')
    s=session or requests.Session(); s.headers['User-Agent']=USER_AGENT
    path.parent.mkdir(parents=True,exist_ok=True); partial=path.with_suffix(path.suffix+'.part')
    with s.get(url,stream=True,timeout=(20,120)) as response:
        response.raise_for_status()
        if 'text/html' in response.headers.get('Content-Type','').lower():
            raise ValueError('HTML returned instead of data; blocked/manual acquisition required')
        length=response.headers.get('Content-Length')
        if length and int(length)>budget:
            raise ValueError('Download would exceed authorized budget')
        count=0
        try:
            with partial.open('wb') as handle:
                for chunk in response.iter_content(1024*1024):
                    count+=len(chunk)
                    if count>budget: raise ValueError('Download exceeded authorized budget')
                    handle.write(chunk)
            if expected_bytes is not None and count!=expected_bytes:
                raise ValueError('Downloaded byte count mismatch')
            digest=file_digest(partial)
            if expected_sha256 and digest!=expected_sha256:
                raise ValueError('Downloaded checksum mismatch')
            partial.replace(path)
        except Exception:
            partial.unlink(missing_ok=True)
            raise
    existing.append({'url':url,'path':str(path),'bytes':count,'sha256':digest,
                     'retrieved_at_utc':datetime.now(timezone.utc).isoformat(),
                     'source_id':source_id,'version':version,'license':license_note,'request_identity':request_key})
    temporary=manifest.with_suffix('.json.tmp'); temporary.write_text(json.dumps(existing,indent=2),encoding='utf-8'); temporary.replace(manifest)
    return path


def acquire_egrid(raw_dir):
    root=Path(raw_dir)/'epa_egrid'/'official_2023'
    files=[('egrid2023_data_rev2.xlsx','https://www.epa.gov/system/files/documents/2025-06/egrid2023_data_rev2.xlsx',21_213_301),
           ('egrid2023_subregions.zip','https://www.epa.gov/system/files/other-files/2025-01/egrid2023_subregions.zip',57_260_059),
           ('egrid2023_multiple_subregions.zip','https://www.epa.gov/system/files/other-files/2025-01/egrid2023_multiple_subregions.zip',16_188_767)]
    return {name:download_public(url,root/name,raw_dir=raw_dir,source_id='epa_egrid',version='eGRID2023 rev2',
                                license_note='U.S. Government data; EPA data license',expected_bytes=size) for name,url,size in files}


def acquire_wrc_bbox(raw_dir,bounds_5070):
    """WRC ImageServer nearest-neighbor 30 m development clip, two themes.

    Service exports may differ in vintage from archive WRC2; metadata is saved
    alongside clips and the release claim must be verified independently.
    """
    s=requests.Session(); s.headers['User-Agent']=USER_AGENT
    root=Path(raw_dir)/'usfs_wildfire_risk'/'wrc'/'bounded'
    x0,y0,x1,y1=bounds_5070; width=int((x1-x0)/30)+1; height=int((y1-y0)/30)+1
    if width*height>10_000_000:
        raise ValueError('WRC export must be bounded <=10 million pixels per theme; tile nationally')
    output={}
    for theme in ['BurnProbability','ConditionalFlameLength']:
        endpoint='https://imagery.geoplatform.gov/iipp/rest/services/Fire_Aviation/USFS_EDW_RMRS_WRC_'+theme+'/ImageServer'
        key=request_identity(endpoint,'public WRC service',{'bounds_5070':list(bounds_5070),'width':width,'height':height,'resampling':'nearest'})
        path=root/(theme+'_'+key+'_5070.tif')
        if verified_cached_request(path,key): output[theme]=path; continue
        info=s.get(endpoint,params={'f':'json'},timeout=45); info.raise_for_status()
        root.mkdir(parents=True,exist_ok=True)
        (root/(theme+'_service_metadata.json')).write_text(json.dumps(info.json(),indent=2),encoding='utf-8')
        params={'bbox':','.join(map(str,bounds_5070)),'bboxSR':5070,'imageSR':5070,'size':f'{width},{height}',
                'format':'tiff','pixelType':'F32','interpolation':'RSP_NearestNeighbor','f':'json'}
        response=s.get(endpoint+'/exportImage',params=params,timeout=120); response.raise_for_status(); obj=response.json()
        if 'href' not in obj: raise ValueError(f'WRC export unavailable: {obj.get("error")}')
        download_public(obj['href'],path,raw_dir=raw_dir,source_id='usfs_wildfire_risk',version='public WRC ImageServer, observed 2026-10-03',
                        license_note='USDA Forest Service public data',session=s,request_key=key)
        # Preserve stable request separately; ephemeral server output URL is not reusable.
        (root/(theme+'_export_request.json')).write_text(json.dumps({'url':response.url,'response':obj},indent=2),encoding='utf-8')
        output[theme]=path
    return output


def acquire_flood_bbox(raw_dir,bounds_4326,*,max_features=100_000,layer_id=28):
    """One bbox ID query plus bounded ID batches, never one request per grid cell."""
    s=requests.Session(); s.headers['User-Agent']=USER_AGENT
    root=Path(raw_dir)/'fema_nfhl'/'bounded'
    endpoint=f'https://hazards.fema.gov/arcgis/rest/services/public/NFHL/MapServer/{layer_id}/query'
    base={'f':'json','where':'1=1','geometry':','.join(map(str,bounds_4326)),
          'geometryType':'esriGeometryEnvelope','inSR':4326,'spatialRel':'esriSpatialRelIntersects','returnIdsOnly':'true'}
    key=request_identity(endpoint,'effective NFHL snapshot',base)
    path=root/f'nfhl_layer{layer_id}_{key}.geojson'
    if verified_cached_request(path,key): return path
    r=s.get(endpoint,params=base,timeout=120); r.raise_for_status(); obj=r.json()
    if 'error' in obj: raise ValueError(f'FEMA bbox query blocked: {obj["error"]}')
    ids=sorted(obj.get('objectIds') or [])
    if len(ids)>max_features: raise ValueError('FEMA query exceeds bounded feature budget; tile the study area')
    features=[]
    for start in range(0,len(ids),100):
        params={'f':'geojson','objectIds':','.join(map(str,ids[start:start+100])),
                'outFields':'*' if layer_id!=28 else 'OBJECTID,FLD_ZONE,ZONE_SUBTY,SFHA_TF','returnGeometry':'true','outSR':4326}
        r=s.get(endpoint,params=params,timeout=120); r.raise_for_status(); batch=r.json()
        if 'error' in batch or batch.get('exceededTransferLimit'):
            raise ValueError('FEMA batch incomplete; no partial file accepted')
        features.extend(batch.get('features',[]))
    if len(features)!=len(ids): raise ValueError('FEMA ID/geometry record counts disagree')
    root.mkdir(parents=True,exist_ok=True)
    payload=json.dumps({'type':'FeatureCollection','features':features}).encode('utf-8')
    total=sum(f.stat().st_size for f in Path(raw_dir).rglob('*') if f.is_file())
    if total+len(payload)>PROJECT_MAX_BYTES: raise ValueError('FEMA output exceeds authorized raw-data budget')
    path.write_bytes(payload)
    manifest=json.loads((root/'download_log.json').read_text()) if (root/'download_log.json').exists() else []
    manifest.append({'url':endpoint+'?'+requests.compat.urlencode(base),'path':str(path),
               'bytes':path.stat().st_size,'sha256':file_digest(path),'source_id':'fema_nfhl',
               'version':'effective NFHL snapshot','retrieved_at_utc':datetime.now(timezone.utc).isoformat(),
               'license':'U.S. Government work','feature_count':len(features),'bounds_4326':list(bounds_4326),'request_identity':key})
    (root/'download_log.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    return path
