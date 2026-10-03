"""Synthetic native-format fixtures, never used as processed real data."""
import json
import numpy as np
import pandas as pd
import geopandas as gpd
import pytest
from shapely.geometry import box
from dc_locator.geography.sources.native_expanded import (
    read_usdm, read_ibtracs, read_ntad, summarize_proximity,
    read_nsrdb, read_wind_srw, read_eia861, read_queue,
)


def test_usdm_cumulative_and_missing_week(tmp_path):
    p=tmp_path/'d.csv'
    pd.DataFrame({'MapDate':[20000104,20000111], 'FIPS':[48001]*2,
       'D0':[90,60],'D1':[80,50],'D2':[50,20],'D3':[10,0],'D4':[0,0],
       'StatisticFormatID':[1,1]}).to_csv(p,index=False)
    f=read_usdm(p,start='2000-01-01',end='2000-01-18')
    assert f.iloc[0].usdm_d2plus_area_time_frac==pytest.approx(.35)
    assert f.iloc[0].temporal_coverage_frac==pytest.approx(2/3)
    assert f.iloc[0].usdm_d2plus_any_area_week_frac==1
    d=pd.read_csv(p);d.loc[1,'D3']=30;d.to_csv(p,index=False)
    with pytest.raises(ValueError,match='cumulative'):read_usdm(p)


def test_usdm_format_and_duplicates_rejected(tmp_path):
    p=tmp_path/'d.csv';d=pd.DataFrame({'MapDate':[20000104]*2,'FIPS':[48001]*2,
        'D0':[0]*2,'D1':[0]*2,'D2':[0]*2,'D3':[0]*2,'D4':[0]*2,'StatisticFormatID':[1]*2})
    d.to_csv(p,index=False)
    with pytest.raises(ValueError,match='Duplicate'):read_usdm(p)
    d=d.iloc[:1];d['StatisticFormatID']=2;d.to_csv(p,index=False)
    with pytest.raises(ValueError,match='cumulative'):read_usdm(p)


def test_ibtracs_missing_position_does_not_bridge(tmp_path):
    p=tmp_path/'track.csv'
    p.write_text('SID,SEASON,ISO_TIME,LAT,LON,TRACK_TYPE\n,Year,,degrees_north,degrees_east,\n'
      'A,2000,2000-08-01 00:00:00,30,-96,main\n'
      'A,2000,2000-08-01 03:00:00,, ,main\n'
      'A,2000,2000-08-01 06:00:00,30,-95,main\n'
      'B,2000,2000-08-01 00:00:00,30,-96,main\n'
      'B,2000,2000-08-01 06:00:00,30,-95,main\n'
      'C,2000,2000-08-01 00:00:00,30,-96,PROVISIONAL\n')
    f=read_ibtracs(p,start_year=2000,end_year=2000)
    assert f.SID.tolist()==['B']
    assert f.crs.to_epsg()==5070


def test_bounded_native_rail_empty_inside_vs_outside(tmp_path):
    p=tmp_path/'rail.json';p.write_text(json.dumps({'spatialReference':{'wkid':4326},
      'geometryType':'esriGeometryPolyline','fields':[{'name':'FRAARCID'}], 'features':[],
      'acquisition':{'complete':True,'bounds_4326':[-97,29,-95,31],'object_ids':[]}}))
    lines,footprint=read_ntad(p)
    cells=gpd.GeoDataFrame({'grid_id':['in','out']},geometry=[box(-96.2,30,-96.1,30.1),box(-94,30,-93.9,30.1)],crs=4326).to_crs(5070)
    f=summarize_proximity(cells,lines,footprint,'ntad_rail_distance_km')
    assert f.iloc[0].coverage_frac==1
    assert f.iloc[1].coverage_frac==0
    assert f.value.isna().all() # no finite nearest feature is established


def test_nsrdb_native_two_metadata_rows_units(tmp_path):
    p=tmp_path/'solar.csv';p.write_text('Source,Latitude,Longitude,GHI Units,Time Zone\nNSRDB,30,-96,w/m2,-6\n'
     'Year,Month,Day,Hour,Minute,GHI,DNI,DHI\n2024,1,1,0,0,0,0,0\n2024,1,1,0,30,100,120,20\n')
    f=read_nsrdb(p)
    assert f['ghi_mean_w_per_m2']==50
    assert f['ghi_integrated_kwh_per_m2']==pytest.approx(.05)
    assert f['sample_count']==2
    p.write_text(p.read_text().replace('w/m2','kw/m2'))
    with pytest.raises(ValueError,match='units'):read_nsrdb(p)


@pytest.mark.parametrize('values',['nan,nan','0,nan'])
def test_nsrdb_missing_integral_never_zero(tmp_path,values):
    p=tmp_path/'s.csv';a,b=values.split(',')
    p.write_text('Source,Latitude,Longitude,GHI Units\nNSRDB,30,-96,w/m2\nYear,Month,Day,Hour,Minute,GHI\n'
                 f'2024,1,1,0,0,{a}\n2024,1,1,1,0,{b}\n')
    r=read_nsrdb(p);assert pd.isna(r['ghi_integrated_kwh_per_m2'])
    if a=='nan':assert pd.isna(r['ghi_known_interval_subtotal_kwh_per_m2'])


def test_wind_index_native_fields_and_infinite_rejected(tmp_path):
    from dc_locator.geography.sources.native_expanded import read_wind_index
    p=tmp_path/'w.csv'
    pd.DataFrame({'site_id':[1,2],'longitude':[-96,-95],'latitude':[30,30],
      'wind_speed':[6,np.inf],'capacity_factor':[.3,.4],'fraction_of_usable_area':[1,1],
      'capacity':[16,16],'power_curve':['1','2']}).to_csv(p,index=False)
    f=read_wind_index(p);assert f.iloc[0].wind_speed==6;assert pd.isna(f.iloc[1].wind_speed)
    d=pd.read_csv(p);d['longitude']=d.longitude.astype(float);d.loc[0,'longitude']=np.inf;d.to_csv(p,index=False)
    with pytest.raises(ValueError,match='coordinates'):read_wind_index(p)


def test_proximity_rejects_degrees():
    cells=gpd.GeoDataFrame({'grid_id':['a']},geometry=[box(-96,30,-95,31)],crs=4326)
    lines=gpd.GeoDataFrame(geometry=[],crs=4326)
    with pytest.raises(ValueError,match='5070'):summarize_proximity(cells,lines,None,'d')


def test_wind_srw_native_height_and_units(tmp_path):
    p=tmp_path/'w.srw';p.write_text('1,City,TX,US,2014,30,-96,NA,1,2\nWIND Toolkit\nTemperature,Pressure,Speed,Direction\nC,atm,m/s,Degrees\n100,100,100,100\n20,1,5,90\n20,1,7,100\n')
    r=read_wind_srw(p);assert r['wind_speed_mean_m_per_s']==6
    assert r['height_m']==100
    p.write_text(p.read_text().replace('m/s','mph'))
    with pytest.raises(ValueError,match='units'):read_wind_srw(p)


def test_eia_multilevel_native_reporting_bases(tmp_path):
    p=tmp_path/'eia.xlsx'
    rows=[['Characteristics',None,'IEEE Standard',None,None,None,None,None,None,None,None,None,'Any Standard'],
          [None,None,'All Events (With Major Event Days)',None,None,None,'Without Major Event Days',None,None,'Loss of Supply Removed (With Major Event Days)',None,None,'All Events (With Major Event Days)',None,None,None,'Without Major Event Days'],
          ['Data Year','State','Number of Customers','SAIDI (minutes per year)','SAIFI (times per year)','CAIDI (minutes per year)','SAIDI (minutes per year)','SAIFI (times per year)','CAIDI (minutes per year)','SAIDI (minutes per year)','SAIFI (times per year)','CAIDI (minutes per year)','Number of Customers','SAIDI (minutes per year)','SAIFI (times per year)','CAIDI (minutes per year)','SAIDI (minutes per year)','SAIFI (times per year)','CAIDI (minutes per year)'],
          [2024,'TX',100,200,2,100,20,1,20,180,1.8,100,150,300,3,100,30,1.5,20]]
    pd.DataFrame(rows).to_excel(p,sheet_name='State Totals',header=False,index=False)
    f=read_eia861(p)
    assert f.iloc[0].eia861_ieee_with_med_saidi_minutes_per_year==200
    assert f.iloc[0].eia861_ieee_without_med_saidi_minutes_per_year==20
    assert f.iloc[0].eia861_any_with_med_saidi_minutes_per_year==300
    assert f.iloc[0].eia861_ieee_reporting_customers==100


def test_queue_native_unknown_capacity_and_first_county(tmp_path):
    p=tmp_path/'queue.xlsx'
    d=pd.DataFrame({'q_id':['A','B','C'],'q_status':['active','active','withdrawn'],
      'entity':['E']*3,'fips_code':[48001]*3,'state':['TX']*3,
      'mw_1':[10,np.nan,100],'mw_2':[np.nan,2,np.nan],'mw_3':[np.nan]*3,
      'type_1':['Solar']*3,'type_2':[np.nan,'Battery',np.nan],'type_3':[np.nan]*3})
    with pd.ExcelWriter(p) as w:d.to_excel(w,sheet_name='03. Complete Queue Data',startrow=1,index=False)
    f=read_queue(p)
    assert f.iloc[0].queued_active_project_count==2
    assert pd.isna(f.iloc[0].queued_active_reported_capacity_mw) # never impute missing active MW
    assert f.iloc[0].queued_capacity_reporting_frac==.5


@pytest.mark.parametrize('types,mw,known',[([None,None,None],[None,None,None],False),(['Solar',None,None],[0,None,None],True),(['Solar',None,None],[-2,None,None],False)])
def test_queue_missing_components_and_native_outlier(tmp_path,types,mw,known):
    p=tmp_path/'q.xlsx';d=pd.DataFrame({'q_id':['A'],'q_status':['active'],'entity':['E'],'fips_code':[48001],'state':['TX']})
    for i in range(3):d[f'type_{i+1}']=types[i];d[f'mw_{i+1}']=mw[i]
    with pd.ExcelWriter(p) as w:d.to_excel(w,sheet_name='03. Complete Queue Data',startrow=1,index=False)
    f=read_queue(p)
    assert f.iloc[0].queued_active_project_count==1
    assert pd.notna(f.iloc[0].queued_active_reported_capacity_mw)==known
    if known:assert f.iloc[0].queued_active_reported_capacity_mw==0


def test_nex_nonmonotonic_coordinates_and_missing_pixel(tmp_path):
    import xarray as xr
    from dc_locator.geography.sources.native_climate import read_nex
    p=tmp_path/'n.nc';values=np.full((365,2,3),300.);values[0,0,0]=np.nan
    d=xr.Dataset({'tas':(('time','lat','lon'),values)},coords={'time':pd.date_range('2030-01-01',periods=365),'lat':[30,30.25],'lon':[264,264.25,264.5]},
      attrs={'cmip6_source_id':'ACCESS-CM2','scenario':'ssp245','variant_label':'r1i1p1f1','frequency':'day','resolution_id':'0.25 degree','version':'2.0'})
    d.tas.attrs['units']='K';d.to_netcdf(p,engine='scipy')
    f,m=read_nex(p,'tas');assert pd.isna(f.iloc[0].value);assert f.iloc[0].temporal_coverage_frac==364/365
    d=d.assign_coords(lon=[264,264.25,264]);d.to_netcdf(p,engine='scipy')
    with pytest.raises(ValueError,match='monotonic'):read_nex(p,'tas')


@pytest.mark.parametrize('variable,native,expected,unit',[('tas',300,26.85,'K'),('pr',1/86400,1,'kg m-2 s-1')])
def test_nex_units_calendar_and_complete_annual(tmp_path,variable,native,expected,unit):
    import xarray as xr
    from dc_locator.geography.sources.native_climate import read_nex
    p=tmp_path/'n.nc';times=pd.date_range('2030-01-01',periods=365)
    d=xr.Dataset({variable:(('time','lat','lon'),np.full((365,2,2),native))},
       coords={'time':times,'lat':[30,30.25],'lon':[264,264.25]},
       attrs={'cmip6_source_id':'ACCESS-CM2','scenario':'ssp245','variant_label':'r1i1p1f1',
        'frequency':'day','resolution_id':'0.25 degree','version':'2.0'})
    d[variable].attrs['units']=unit;d.to_netcdf(p,engine='scipy')
    f,m=read_nex(p,variable);assert np.allclose(f.value,expected);assert m['expected_days']==365
    d=d.isel(time=slice(None,-1));d.to_netcdf(p,engine='scipy')
    f,m=read_nex(p,variable);assert f.value.isna().all();assert m['time_coverage_frac']==364/365
    with pytest.raises(ValueError,match='identity'):read_nex(p,variable,scenario='ssp585')
    d.attrs.pop('version');d.to_netcdf(p,engine='scipy')
    with pytest.raises(ValueError,match='version'):read_nex(p,variable)


@pytest.mark.parametrize('latitude,longitude',[(np.inf,-96),(30,np.nan),(91,-96),(30,-181)])
def test_nsrdb_invalid_point_coordinates(tmp_path,latitude,longitude):
    p=tmp_path/'s.csv';p.write_text(f'Source,Latitude,Longitude,GHI Units\nNSRDB,{latitude},{longitude},w/m2\n'
      'Year,Month,Day,Hour,Minute,GHI\n2024,1,1,0,0,1\n2024,1,1,1,0,2\n')
    with pytest.raises(ValueError,match='coordinates'):read_nsrdb(p)


@pytest.mark.parametrize('interval,height',[('inf',100),(0,100),(1,'nan'),(1,-1)])
def test_wind_srw_invalid_native_metadata(tmp_path,interval,height):
    p=tmp_path/'w.srw';p.write_text(f'1,City,TX,US,2014,30,-96,NA,{interval},2\nWIND Toolkit\n'
      f'Temperature,Pressure,Speed,Direction\nC,atm,m/s,Degrees\n100,100,{height},100\n20,1,5,90\n20,1,7,90\n')
    with pytest.raises(ValueError,match='finite'):read_wind_srw(p)


def test_nex_conflicting_cf_requires_verified_components(tmp_path):
    import xarray as xr
    from dc_locator.geography.sources.native_climate import read_nex,TemperatureInterpretationError
    attrs={'cmip6_source_id':'ACCESS-CM2','scenario':'ssp245','variant_label':'r1i1p1f1',
       'frequency':'day','resolution_id':'0.25 degree','version':'2.0'}
    paths={}
    for variable,value in [('tas',300),('tasmax',310),('tasmin',290)]:
        d=xr.Dataset({variable:(('time','lat','lon'),np.full((365,2,2),value,dtype=np.float32))},
            coords={'time':pd.date_range('2030-01-01',periods=365),'lat':[30,30.25],'lon':[264,264.25]},attrs=attrs)
        d[variable].attrs.update(units='K',cell_methods='area: mean time: maximum' if variable=='tas' else 'area: mean')
        paths[variable]=tmp_path/f'{variable}.nc';d.to_netcdf(paths[variable],engine='scipy')
    with pytest.raises(TemperatureInterpretationError,match='requires'):read_nex(paths['tas'],'tas')
    components={k:paths[k] for k in ['tasmax','tasmin']}
    frame,metadata=read_nex(paths['tas'],'tas',temperature_components=components)
    verification=metadata['temperature_derivation_verification']
    assert verification['valid_sample_count']==1460
    assert verification['maximum_absolute_difference_k']==0
    assert set(verification['dependencies'])=={'tas','tasmax','tasmin'}
    assert 'time: maximum' in verification['raw_cf_metadata_conflict']
    with xr.open_dataset(paths['tasmin'],engine='scipy') as d: changed=d.load()
    changed['tasmin']+=2;changed.tasmin.attrs['units']='K';changed.to_netcdf(paths['tasmin'],engine='scipy')
    with pytest.raises(TemperatureInterpretationError,match='does not match'):read_nex(paths['tas'],'tas',temperature_components=components)
