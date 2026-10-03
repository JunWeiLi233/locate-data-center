"""Native public-format parsers for Phase 5; no downloading or scoring.

These parsers reject changed required headers/units rather than guessing. Regional
statistics are context, point resource samples are not areal observations, and
bounded inventories do not imply service/capacity commitments.
"""
import csv
import json
from pathlib import Path
import zipfile

import geopandas as gpd
import numpy as np
import pandas as pd
import shapely
from shapely.geometry import LineString, MultiLineString, Point, box
from pyproj import Transformer
from shapely.ops import transform


def require_columns(frame,columns):
    missing=set(columns)-set(frame.columns)
    if missing: raise ValueError(f'Native required headers missing: {sorted(missing)}')


def read_eia861(path):
    """Native Reliability workbook State Totals, IEEE and Any Standard separate.

    This intentionally does not infer a supplying utility from service territories.
    Customer counts retain each reporting population, never an invented percent
    of the cell's customers. CAIDI's native misleading header is not used.
    """
    archive=None
    if str(path).lower().endswith('.zip'):
        archive=zipfile.ZipFile(path)
        members=[n for n in archive.namelist() if Path(n).name.startswith('Reliability_') and n.endswith('.xlsx')]
        if len(members)!=1: raise ValueError('Expected one native EIA Reliability workbook')
        stream=archive.open(members[0])
    else: stream=path
    try: raw=pd.read_excel(stream,sheet_name='State Totals',header=None)
    finally:
        if archive: archive.close()
    if raw.shape[1]!=19 or raw.iloc[0,2]!='IEEE Standard' or raw.iloc[0,12]!='Any Standard':
        raise ValueError('Native EIA reporting-basis headers changed')
    for col,label in [(2,'All Events (With Major Event Days)'),(6,'Without Major Event Days'),
                      (9,'Loss of Supply Removed (With Major Event Days)'),
                      (12,'All Events (With Major Event Days)'),(16,'Without Major Event Days')]:
        if raw.iloc[1,col]!=label: raise ValueError('Native EIA MED/loss-of-supply headers changed')
    if list(raw.iloc[2,:2])!=['Data Year','State']: raise ValueError('Native EIA identity headers changed')
    out=pd.DataFrame({'State':raw.iloc[3:,1].astype(str).str.strip(),
                      'data_year':pd.to_numeric(raw.iloc[3:,0],errors='coerce')})
    out=out.loc[out.State.str.fullmatch('[A-Z]{2}')].copy()
    if out.State.duplicated().any(): raise ValueError('Duplicate EIA state totals')
    positions={'eia861_ieee_reporting_customers':2,'eia861_any_reporting_customers':12}
    for basis,start in [('ieee_with_med',3),('ieee_without_med',6),('ieee_loss_supply_removed_with_med',9),('any_with_med',13),('any_without_med',16)]:
        for metric,offset,label in [('saidi_minutes_per_year',0,'SAIDI (minutes per year)'),('saifi_interruptions_per_year',1,'SAIFI (times per year)')]:
            col=start+offset
            if raw.iloc[2,col]!=label: raise ValueError('Native EIA interruption unit headers changed')
            positions['eia861_'+basis+'_'+metric]=col
    for metric,col in positions.items():
        values=pd.to_numeric(raw.iloc[3:,col],errors='coerce').reindex(out.index)
        if col in {2,12} and raw.iloc[2,col]!='Number of Customers': raise ValueError('Native EIA customer basis header changed')
        out[metric]=values.where(np.isfinite(values)&(values>=0))
    return out.reset_index(drop=True)


def read_usdm(path,*,start='2000-01-01',end='2024-12-31'):
    """Native county cumulative area percentages, equal-weight weekly history.

    D2 is D2-or-worse, not D2 alone. Native percent becomes fraction by /100.
    Missing weeks do not become drought-free weeks; temporal coverage is separate.
    """
    d=pd.read_csv(path,dtype={'FIPS':'string'})
    require_columns(d,['MapDate','FIPS','D0','D1','D2','D3','D4','StatisticFormatID'])
    if not (pd.to_numeric(d.StatisticFormatID)==1).all(): raise ValueError('Only verified cumulative USDM statisticsType=1 supported')
    d['date']=pd.to_datetime(d.MapDate.astype(str),format='%Y%m%d',errors='raise')
    d=d.loc[d.date.between(pd.Timestamp(start),pd.Timestamp(end))].copy()
    if not (d.date.dt.dayofweek==1).all(): raise ValueError('Native USDM map dates must be Tuesday')
    d['GEOID']=d.FIPS.str.zfill(5)
    if not d.GEOID.str.fullmatch(r'\d{5}').all(): raise ValueError('Invalid native USDM county FIPS')
    if d.duplicated(['GEOID','date']).any(): raise ValueError('Duplicate USDM county/week')
    values=d[['D0','D1','D2','D3','D4']].apply(pd.to_numeric,errors='coerce')
    finite=values.notna().all(axis=1)
    if ((values[finite]<0)|(values[finite]>100)).any().any() or (np.diff(values[finite],axis=1)>1e-9).any():
        raise ValueError('Invalid cumulative drought percentages')
    d['D2_valid']=values.D2.where(finite)/100
    d['any_D2']=np.where(finite,(values.D2>0).astype(float),np.nan)
    expected=len(pd.date_range(start,end,freq='W-TUE'))
    if expected==0: raise ValueError('USDM period contains no expected weekly maps')
    g=d.groupby('GEOID',sort=True)
    out=g.agg(usdm_d2plus_area_time_frac=('D2_valid','mean'),
       usdm_d2plus_any_area_week_frac=('any_D2','mean'),valid_weeks=('D2_valid','count')).reset_index()
    out['expected_weeks']=expected;out['temporal_coverage_frac']=out.valid_weeks/expected
    return out


def read_queue(path):
    """2026 native Queued Up project sheet, county context and reported MW only.

    Only the first listed county is supplied by the native codebook. Counties
    absent from this non-comprehensive inventory stay missing; zero is not inferred.
    Missing active component capacity makes the county capacity total unknown.
    """
    d=pd.read_excel(path,sheet_name='03. Complete Queue Data',header=1)
    require_columns(d,['q_id','q_status','entity','fips_code','state','mw_1','mw_2','mw_3','type_1','type_2','type_3'])
    d=d.loc[d.q_status=='active'].copy()
    if d.duplicated(['entity','q_id']).any(): raise ValueError('Duplicate Queued Up entity/queue ID')
    native_count=len(d)
    invalid_native=d[['mw_1','mw_2','mw_3']].apply(pd.to_numeric,errors='coerce').lt(0).any(axis=1)
    invalid_ids=(d.loc[invalid_native,'entity'].astype(str)+':'+d.loc[invalid_native,'q_id'].astype(str)).sort_values().tolist()
    fips=pd.to_numeric(d.fips_code,errors='coerce')
    valid=fips.notna() & (fips%1==0) & fips.between(1001,99999)
    d=d.loc[valid].copy();d['GEOID']=fips.loc[valid].astype(int).astype(str).str.zfill(5)
    capacities=[];complete=[];invalid=[]
    for i in [1,2,3]:
        v=pd.to_numeric(d[f'mw_{i}'],errors='coerce')
        required=d[f'type_{i}'].notna()
        if (v.notna() & ~np.isfinite(v)).any(): raise ValueError('Nonfinite native queue MW')
        bad=(v.notna()&(v<0))|(v.notna()&~required)
        invalid.append(bad);v=v.where(~bad)
        complete.append(~required | (v.notna() & (v>=0)))
        capacities.append(v.where(required,0))
    d['reported']=np.logical_and.reduce(complete)&d[['type_1','type_2','type_3']].notna().any(axis=1)
    d['invalid']=np.logical_or.reduce(invalid);d['reported'] &= ~d.invalid
    d['capacity']=sum(capacities).where(d.reported)
    g=d.groupby('GEOID',sort=True)
    out=g.agg(queued_active_project_count=('q_status','size'),
              queued_capacity_reporting_frac=('reported','mean'),
              queued_invalid_capacity_project_count=('invalid','sum'),
              queued_active_reported_capacity_mw=('capacity',lambda s:s.sum() if s.notna().all() else np.nan)).reset_index()
    out.attrs['native_quality']={'invalid_active_capacity_projects':int(d.invalid.sum()),
      'invalid_active_capacity_projects_total_before_location_filter':len(invalid_ids),
      'invalid_active_capacity_project_ids':invalid_ids,
      'incomplete_active_capacity_projects':int((~d.reported).sum()),
      'located_active_projects':len(d),'native_active_projects':native_count,'unlocated_active_projects':native_count-len(d),
      'county_assignment':'native first-listed county only'}
    return out


def read_ibtracs(path,*,start_year=1980,end_year=2024,max_gap_hours=6):
    """Native v04r01 NA CSV, MAIN segments; no bridging blanks or >6 h gaps.

    All storm natures retained; winds are deliberately unused because agencies'
    averaging periods differ. Distance is to historical track segments, not winds.
    """
    columns=['SID','SEASON','ISO_TIME','LAT','LON','TRACK_TYPE']
    header=pd.read_csv(path,nrows=1);require_columns(header,columns)
    units=header.iloc[0]
    if str(units.LAT).strip()!='degrees_north' or str(units.LON).strip()!='degrees_east':
        raise ValueError('Native IBTrACS coordinate units missing')
    chunks=[]
    for d in pd.read_csv(path,skiprows=[1],usecols=columns,chunksize=50000):
        season=pd.to_numeric(d.SEASON,errors='coerce')
        d=d.loc[season.between(start_year,end_year) & d.TRACK_TYPE.astype(str).str.strip().str.lower().eq('main')].copy()
        chunks.append(d)
    d=pd.concat(chunks,ignore_index=True)
    d['ISO_TIME']=pd.to_datetime(d.ISO_TIME,utc=True,errors='coerce')
    d['LAT']=pd.to_numeric(d.LAT,errors='coerce');d['LON']=pd.to_numeric(d.LON,errors='coerce')
    records=[]
    for sid,g in d.sort_values(['SID','ISO_TIME']).groupby('SID',sort=True):
        if g.ISO_TIME.duplicated().any(): raise ValueError('Duplicate MAIN storm timestamps')
        coords=g[['LON','LAT']].to_numpy();times=g.ISO_TIME
        valid=np.isfinite(coords).all(axis=1)&(abs(coords[:,0])<=180)&(abs(coords[:,1])<=90)
        gaps=times.diff().dt.total_seconds().to_numpy()/3600
        segments=[]
        for i in np.flatnonzero(valid[1:] & valid[:-1] & (gaps[1:]>0) & (gaps[1:]<=max_gap_hours))+1:
            if abs(coords[i,0]-coords[i-1,0])>180: continue # do not bridge dateline
            if np.array_equal(coords[i],coords[i-1]): segments.append(Point(coords[i]))
            else:segments.append(LineString(coords[i-1:i+1]))
        if segments:records.append({'SID':sid,'geometry':shapely.union_all(segments)})
    frame=gpd.GeoDataFrame(records,columns=['SID','geometry'],crs=4326)
    frame.geometry=shapely.segmentize(frame.geometry.values,.05)
    frame=frame.to_crs(5070)
    # Projection can collapse tiny stationary segments to a point; preserve the
    # historical position through explicit validity repair instead of dropping it.
    frame.geometry=shapely.make_valid(frame.geometry.values)
    return frame


def read_ntad(path):
    """Native ESRI JSON polylines plus independent complete query footprint."""
    obj=json.loads(Path(path).read_text(encoding='utf-8'))
    if obj.get('geometryType')!='esriGeometryPolyline' or obj.get('spatialReference',{}).get('wkid')!=4326:
        raise ValueError('NTAD native polyline/EPSG:4326 contract required')
    if 'FRAARCID' not in {f['name'] for f in obj.get('fields',[])}: raise ValueError('NTAD native FRAARCID header missing')
    acquisition=obj.get('acquisition',{})
    if acquisition.get('complete') is not True: raise ValueError('Incomplete bounded NTAD inventory')
    bounds=acquisition.get('bounds_4326')
    if bounds is None: raise ValueError('Independent acquisition bounds required')
    if len(bounds)!=4 or not np.isfinite(bounds).all() or not (-180<=bounds[0]<bounds[2]<=180) or not (-90<=bounds[1]<bounds[3]<=90): raise ValueError('Invalid native query bounds')
    if 'object_ids' not in acquisition:raise ValueError('Complete native query object IDs required')
    if 'object_ids' in acquisition:
        oid=obj.get('service_metadata',{}).get('objectIdField') or next((f['name'] for f in obj.get('fields',[]) if f.get('type')=='esriFieldTypeOID'), 'OBJECTID')
        ids=[f.get('attributes',{}).get(oid) for f in obj['features']]
        if len(ids)!=len(set(ids)) or set(ids)!=set(acquisition['object_ids']): raise ValueError('Native query object ID set mismatch')
    rows=[]
    for f in obj['features']:
        paths=f.get('geometry',{}).get('paths')
        if not paths: raise ValueError('NTAD native geometry missing')
        for p in paths:
            coords=np.asarray(p,dtype=float)
            if coords.ndim!=2 or coords.shape[1]<2 or not np.isfinite(coords[:,:2]).all() or (abs(coords[:,0])>180).any() or (abs(coords[:,1])>90).any(): raise ValueError('Invalid native NTAD coordinates')
        lines=[LineString(np.asarray(p)[:,:2]) for p in paths if len(p)>=2]
        if not lines: raise ValueError('NTAD native polyline empty')
        rows.append(dict(f['attributes'],geometry=MultiLineString(lines)))
    lines=gpd.GeoDataFrame(rows,columns=None if rows else ['geometry'],crs=4326).to_crs(5070)
    footprint=transform(Transformer.from_crs(4326,5070,always_xy=True).transform,shapely.segmentize(box(*bounds),.01))
    return lines,footprint


def summarize_proximity(cells,features,footprint,metric):
    """Bounded minimum study-polygon distance, with nearest-search completeness.

    A known nearest feature requires full query coverage and a feature closer
    than the query boundary. No feature in a finite inventory does not prove an
    infinite distance or a genuinely absent national feature.
    """
    if cells.crs is None or cells.crs.to_epsg()!=5070 or features.crs is None or features.crs.to_epsg()!=5070:
        raise ValueError('Proximity inputs must be EPSG:5070')
    if cells.grid_id.duplicated().any() or cells.geometry.isna().any() or cells.geometry.is_empty.any() or not cells.geometry.is_valid.all() or not cells.geometry.geom_type.isin(['Polygon','MultiPolygon']).all() or not np.isfinite(cells.geometry.area).all() or (cells.geometry.area<=0).any():
        raise ValueError('Proximity cells must have unique IDs and valid positive-area geometries')
    if features.geometry.isna().any() or features.geometry.is_empty.any() or not features.geometry.is_valid.all(): raise ValueError('Proximity source geometries must be valid nonempty')
    union=shapely.union_all(features.geometry.values) if len(features) else None
    rows=[]
    for c in cells.itertuples():
        coverage=1. if footprint is None else min(1.,c.geometry.intersection(footprint).area/c.geometry.area)
        distance=c.geometry.distance(union)/1000 if union is not None else np.nan
        known=coverage>=1-1e-7 and np.isfinite(distance)
        if known and footprint is not None:
            known=distance*1000<c.geometry.distance(footprint.boundary)
        rows.append({'grid_id':c.grid_id,'metric':metric,'value':distance if known else np.nan,
                     'coverage_frac':coverage,'missing_reason':None if known else 'outside_source_coverage'})
    return pd.DataFrame(rows)


def read_wind_index(path):
    d=pd.read_csv(path)
    require_columns(d,['site_id','longitude','latitude','wind_speed','capacity_factor','fraction_of_usable_area','capacity','power_curve'])
    if d.site_id.duplicated().any(): raise ValueError('Duplicate WIND site index IDs')
    for name in ['longitude','latitude','wind_speed','capacity_factor']:
        d[name]=pd.to_numeric(d[name],errors='coerce')
    if not (d.longitude.between(-180,180)&d.latitude.between(-90,90)).all():raise ValueError('Invalid native WIND site coordinates')
    d['wind_speed']=d.wind_speed.where(np.isfinite(d.wind_speed)&(d.wind_speed>=0))
    d['capacity_factor']=d.capacity_factor.where(d.capacity_factor.between(0,1))
    return gpd.GeoDataFrame(d,geometry=gpd.points_from_xy(d.longitude,d.latitude),crs=4326).to_crs(5070)


def read_nsrdb(path):
    """Native API CSV two metadata rows; bounded point-series summary only."""
    with open(path,newline='',encoding='utf-8-sig') as h:
        rows=csv.reader(h);keys=next(rows);vals=next(rows);meta=dict(zip(keys,vals))
    if str(meta.get('GHI Units','')).lower() not in {'w/m2','w/m^2','w/m²'}: raise ValueError('NSRDB GHI native units must be W/m2')
    latitude,longitude=float(meta['Latitude']),float(meta['Longitude'])
    if not np.isfinite([latitude,longitude]).all() or not -90<=latitude<=90 or not -180<=longitude<=180:raise ValueError('NSRDB coordinates must be finite valid latitude/longitude')
    d=pd.read_csv(path,skiprows=2)
    require_columns(d,['Year','Month','Day','Hour','Minute','GHI'])
    t=pd.to_datetime(dict(year=d.Year,month=d.Month,day=d.Day,hour=d.Hour,minute=d.Minute),errors='raise')
    if t.duplicated().any() or not t.is_monotonic_increasing: raise ValueError('NSRDB timestamps must be unique increasing native times')
    intervals=t.diff().dropna().dt.total_seconds()/3600
    if intervals.empty or not np.allclose(intervals,intervals.iloc[0]): raise ValueError('NSRDB uniform native interval required; no gap bridging')
    v=pd.to_numeric(d.GHI,errors='coerce');v=v.where(np.isfinite(v)&(v>=0))
    return {'latitude':latitude,'longitude':longitude,
       'ghi_mean_w_per_m2':v.mean(),'ghi_integrated_kwh_per_m2':v.sum(min_count=1)*intervals.iloc[0]/1000 if v.notna().all() else np.nan,
       'ghi_known_interval_subtotal_kwh_per_m2':v.sum(min_count=1)*intervals.iloc[0]/1000,
       'sample_count':len(d),'valid_sample_count':int(v.notna().sum()),'interval_hours':intervals.iloc[0],
       'time_zone':meta.get('Time Zone'),'period_start':str(t.iloc[0]),'period_end':str(t.iloc[-1]),'metadata':meta}


def read_wind_srw(path):
    """Native WIND Toolkit SRW five-header-row local parser, one native height."""
    with open(path,newline='',encoding='utf-8-sig') as h:
        rows=list(csv.reader(h))
    if len(rows)<6: raise ValueError('WIND SRW native five headers required')
    metadata=rows[0];names=rows[2];units=rows[3];heights=rows[4]
    if names.count('Speed')!=1: raise ValueError('Exactly one declared SRW wind height required')
    i=names.index('Speed')
    if units[i]!='m/s': raise ValueError('WIND SRW native speed units must be m/s')
    latitude,longitude=float(metadata[5]),float(metadata[6])
    interval,height=float(metadata[8]),float(heights[i])
    if not np.isfinite([latitude,longitude,interval,height]).all() or not -90<=latitude<=90 or not -180<=longitude<=180 or interval<=0 or height<=0:raise ValueError('WIND SRW coordinates, interval and height must be finite valid native values')
    vals=pd.to_numeric(pd.Series([r[i] for r in rows[5:]]),errors='coerce');vals=vals.where(np.isfinite(vals)&(vals>=0))
    if len(vals)!=int(metadata[9]): raise ValueError('WIND SRW native sample count mismatch')
    return {'latitude':latitude,'longitude':longitude,'year':int(metadata[4]),
       'interval_hours':interval,'height_m':height,'wind_speed_mean_m_per_s':vals.mean(),
       'sample_count':len(vals),'valid_sample_count':int(vals.notna().sum())}
