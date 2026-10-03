import json
from pathlib import Path
import geopandas as gpd
import numpy as np
import pandas as pd
import pytest
from shapely.geometry import box,LineString
from dc_locator.geography.sources.expanded import build_expanded_features,expanded_default_source_inputs,_associate,_summary
from dc_locator.geography.sources.expanded_ingestion import acquire_file,acquire_arcgis
from dc_locator.geography.sources.ingestion import file_digest,request_identity
from dc_locator.schemas import FeatureMetadata
from dc_locator.io import write_geoparquet,write_parquet
from dc_locator.provenance import DataMode


def fixture_tables():
    grid=gpd.GeoDataFrame({'grid_id':['a'],'grid_definition_id':['gridA'],'data_mode':['synthetic'],
      'study_area_intersection_km2':[1.],'accepted_value':[17.]},geometry=[box(0,0,1000,1000)],crs=5070)
    prov=pd.DataFrame([FeatureMetadata(grid_id='a',metric='accepted_value',value=17,unit='x',source_id='fixture',status='observed',confidence='high',data_mode='synthetic').model_dump(mode='json')])
    prov.attrs['grid_definition_id']='gridA'
    return grid,prov


def test_missing_all_sources_preserves_baseline_and_dtypes(tmp_path):
    grid,prov=fixture_tables()
    a,b,c,m=build_expanded_features(grid,prov,source_inputs={},output_dir=tmp_path/'synthetic',study_geometry=box(0,0,1000,1000))
    pd.testing.assert_frame_equal(a[grid.columns],grid)
    pd.testing.assert_frame_equal(b.iloc[:len(prov)].reset_index(drop=True),prov)
    assert b.attrs==prov.attrs
    assert (b.iloc[len(prov):].status=='unknown').all()
    assert b.iloc[len(prov):].value.isna().all()
    assert not any(s.get('acquired') for s in c['sources'].values())


def test_public_identity_and_geometry_rejections(tmp_path):
    grid,prov=fixture_tables()
    prov.attrs={}
    with pytest.raises(ValueError,match='metadata'):build_expanded_features(grid,prov,{},study_geometry=box(0,0,1000,1000))
    prov.attrs['grid_definition_id']='gridA'
    with pytest.raises(ValueError,match='study polygon'):build_expanded_features(grid,prov,{},study_geometry=LineString([(0,0),(1,1)]))
    p=tmp_path/'g.parquet';q=tmp_path/'p.parquet'
    write_geoparquet(grid,p,schema_name='GeographicFeatureDataset',schema_version='1.2.0',data_mode=DataMode.SYNTHETIC,grid_definition_id='FORGED')
    write_parquet(prov,q,schema_name='FeatureMetadata',schema_version='1.1.0',data_mode=DataMode.SYNTHETIC,grid_definition_id='gridA')
    with pytest.raises(ValueError,match='row/file'):build_expanded_features(p,q,{})
    write_geoparquet(grid,p,schema_name='GeographicFeatureDataset',schema_version='1.2.0',data_mode=DataMode.SYNTHETIC,grid_definition_id='gridA')
    write_parquet(prov,q,schema_name='FeatureMetadata',schema_version='9.0.0',data_mode=DataMode.SYNTHETIC,grid_definition_id='gridA')
    with pytest.raises(ValueError,match='schema'):build_expanded_features(p,q,{})


def test_regional_overlap_is_not_silently_capped():
    cells=gpd.GeoDataFrame({'grid_id':['a']},geometry=[box(0,0,10,10)],crs=5070)
    regions=gpd.GeoDataFrame({'region':['r1','r2']},geometry=[box(0,0,10,10)]*2,crs=5070)
    table=pd.DataFrame({'region':['r1','r2'],'v':[1,2]})
    with pytest.raises(ValueError,match='Overlapping'):_associate(cells,regions,table,'region',['v'])


@pytest.mark.parametrize('bounds',[[0,0,np.inf,1],[-181,0,1,1],[0,-91,1,1],[2,0,1,1]])
def test_acquisition_invalid_bounds_before_http(tmp_path,bounds):
    with pytest.raises(ValueError,match='bounds'):acquire_arcgis(tmp_path,'s','v','https://invalid',bounds)
    from dc_locator.geography.sources.expanded_ingestion import acquire_nex_subset
    with pytest.raises(ValueError,match='bounds'):acquire_nex_subset(tmp_path,'https://invalid',model='ACCESS-CM2',scenario='ssp245',year=2030,bounds_4326=bounds,variable='tas')


def test_request_cache_extent_version_and_tamper(tmp_path,monkeypatch):
    import dc_locator.geography.sources.expanded_ingestion as module
    calls=[]
    def download(url,path,**kwargs):
        calls.append(url);path.parent.mkdir(parents=True);path.write_bytes(b'real-native-test')
        (path.parent/'download_log.json').write_text(json.dumps([{'path':str(path),'bytes':path.stat().st_size,'sha256':file_digest(path),'request_identity':kwargs['request_key']}]))
        return path
    monkeypatch.setattr(module,'download_public',download)
    a=acquire_file(tmp_path,'s','v','https://official/a','native.csv',parameters={'bounds':[0,0,1,1]})
    assert acquire_file(tmp_path,'s','v','https://official/a','native.csv',parameters={'bounds':[0,0,1,1]})==a
    b=acquire_file(tmp_path,'s','v','https://official/a','native.csv',parameters={'bounds':[0,0,2,2]})
    assert a!=b and len(calls)==2
    a.write_bytes(b'tampered')
    with pytest.raises(ValueError,match='checksum'):acquire_file(tmp_path,'s','v','https://official/a','native.csv',parameters={'bounds':[0,0,1,1]})


def test_real_native_workbook_and_manifest_schema_when_cached():
    from dc_locator.geography.sources.native_expanded import read_queue,read_wind_index,read_ntad
    root=Path(__file__).parents[1];inputs=expanded_default_source_inputs(root)
    if not inputs['berkeley_queued_up']['paths']:pytest.skip('Optional official native cache unavailable')
    d=read_queue(inputs['berkeley_queued_up']['paths']['native'])
    assert len(d)>0;assert d.attrs['native_quality']['invalid_active_capacity_projects_total_before_location_filter']==11
    assert d.loc[d.queued_invalid_capacity_project_count>0,'queued_active_reported_capacity_mw'].isna().all()
    w=read_wind_index(inputs['nrel_wind_toolkit']['paths']['native']);assert len(w)==126692
    lines,footprint=read_ntad(inputs['ntad']['paths']['native']);assert len(lines)==4173;assert footprint.is_valid


def test_arcgis_wrong_ids_are_rejected(tmp_path,monkeypatch):
    import dc_locator.geography.sources.expanded_ingestion as module
    class Response:
        def __init__(self,obj):self.obj=obj;self.url='https://official/query'
        def raise_for_status(self):pass
        def json(self):return self.obj
    class Session:
        headers={}
        def get(self,url,params,**kwargs):
            if 'returnIdsOnly' in params:return Response({'objectIds':[1,2]})
            if 'objectIds' in params:return Response({'features':[{'attributes':{'OID':1}},{'attributes':{'OID':3}}]})
            return Response({'objectIdField':'OID','geometryType':'esriGeometryPolyline'})
    monkeypatch.setattr(module.requests,'Session',Session)
    with pytest.raises(ValueError,match='ID set'):acquire_arcgis(tmp_path,'s','v','https://official',[-97,29,-95,31])


def test_native_rail_recorded_id_tamper(tmp_path):
    from dc_locator.geography.sources.native_expanded import read_ntad
    p=tmp_path/'r.json';p.write_text(json.dumps({'spatialReference':{'wkid':4326},'geometryType':'esriGeometryPolyline',
       'fields':[{'name':'FRAARCID'},{'name':'OBJECTID','type':'esriFieldTypeOID'}],
       'features':[{'attributes':{'OBJECTID':2,'FRAARCID':9},'geometry':{'paths':[[[-96,30],[-96.1,30.1]]]}}],
       'acquisition':{'complete':True,'bounds_4326':[-97,29,-95,31],'object_ids':[1]}}))
    with pytest.raises(ValueError,match='ID set'):read_ntad(p)


def test_nasa_combined_coverage_requires_both_and_observed_footprint(monkeypatch):
    import dc_locator.geography.sources.expanded as module
    cells=gpd.GeoDataFrame({'grid_id':['in','out']},geometry=[box(0,0,10,10),box(20,0,30,10)],crs=5070)
    def reader(path,variable,**kwargs):
        frame=gpd.GeoDataFrame({'pixel_id':[1],'value':[5.],'temporal_coverage_frac':[1.]},geometry=[box(0,0,10,10)],crs=5070)
        return frame,{'time_coverage_frac':1}
    monkeypatch.setattr(module,'read_nex',reader)
    single=_summary(cells,'nasa_nex_gddp_cmip6',{'paths':{'tas':'local'}},None)
    assert not single.metric.str.endswith('temporal_coverage_frac').any()
    both=_summary(cells,'nasa_nex_gddp_cmip6',{'paths':{'tas':'local','pr':'local'}},None)
    result=both.loc[both.metric.str.endswith('temporal_coverage_frac')].set_index('grid_id')
    assert result.loc['in','value']==1 and result.loc['in','coverage_frac']==1
    assert pd.isna(result.loc['out','value']) and result.loc['out','coverage_frac']==0


def test_default_discovery_filters_non_native_evidence(tmp_path,monkeypatch):
    import dc_locator.geography.sources.expanded as module
    monkeypatch.setattr(module,'_catalog',lambda root:{'nasa_nex_gddp_cmip6':{'raw_namespace':'nasa','native_pattern':'*.nc'}})
    documentation=tmp_path/'tas_verification.json';documentation.write_text('{}')
    monkeypatch.setattr(module,'inventory_downloads',lambda raw:[{'source_id':'nasa','path':str(documentation)}])
    assert not expanded_default_source_inputs(tmp_path)['nasa_nex_gddp_cmip6']['paths']
