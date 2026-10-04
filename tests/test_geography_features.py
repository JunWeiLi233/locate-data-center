"""Hand-calculated spatial/unit fixtures, always synthetic and outside processed/."""
import json
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import pytest
import rasterio
from rasterio.transform import from_origin
from shapely.geometry import box, LineString

from dc_locator.geography.sources.spatial import raster_zonal, region_intersections
from dc_locator.geography.sources.nlcd import summarize_land_cover
from dc_locator.geography.sources.aqueduct import summarize_water_stress
from dc_locator.geography.sources.egrid import pounds_per_mwh_to_kg_per_mwh, summarize_egrid
from dc_locator.geography.sources.flood import summarize_flood
from dc_locator.geography.sources.infrastructure import distances_to_infrastructure
from dc_locator.geography.sources.protected import summarize_protected
from dc_locator.geography.sources.wildfire import summarize_wildfire
from dc_locator.geography.features import build_features
from dc_locator.geography.sources.ingestion import file_digest
from dc_locator.geography.sources.ingestion import request_identity,verified_cached_request
from dc_locator.geography.sources.ingestion import extract_verified_member


@pytest.fixture
def cells():
    return gpd.GeoDataFrame({'grid_id':['a','b'], 'grid_definition_id':['fixture']*2,
                            'tile_id':['tile']*2, 'data_mode':['synthetic']*2,
                            'cell_area_km2':[.000004]*2,
                            'study_area_intersection_km2':[.000004]*2},
                           geometry=[box(0,0,2,2),box(2,0,4,2)],crs=5070)


def test_partial_pixels_and_nodata_stay_distinct(tmp_path):
    path=tmp_path/'pixels.tif'
    with rasterio.open(path,'w',driver='GTiff',height=2,width=2,count=1,dtype='uint8',
                       crs=5070,transform=from_origin(0,2,1,1),nodata=250) as ds:
        ds.write(np.array([[11,250],[31,31]],dtype='uint8'),1)
    z=raster_zonal(path,box(.5,0,2,2),valid_values={11,31})
    assert z.valid_area_m2==pytest.approx(2)
    assert z.coverage_frac==pytest.approx(2/3)
    assert z.class_area(11)==pytest.approx(.5)
    assert z.class_area(31)==pytest.approx(1.5)


def test_land_cover_no_decision_and_no_unknown_water(tmp_path):
    p=tmp_path/'nlcd.tif'
    with rasterio.open(p,'w',driver='GTiff',height=2,width=2,count=1,dtype='uint8',
                       crs=5070,transform=from_origin(0,2,1,1),nodata=250) as ds:
        ds.write(np.array([[11,90],[31,0]],dtype='uint8'),1)
    result=summarize_land_cover(p,box(0,0,2,2))
    assert result['nlcd_coverage_frac']==pytest.approx(.75)
    assert result['land_cover_water_frac']==pytest.approx(1/3)
    assert result['suitable_land_area_km2']==pytest.approx(.000001)
    assert result['nlcd_water_area_km2']==pytest.approx(.000001)


def test_spatial_region_shares_use_area_not_centroid(cells):
    regions=gpd.GeoDataFrame({'region':['x','y']},geometry=[box(0,0,1,2),box(1,0,4,2)],crs=5070)
    intersections=region_intersections(cells,regions,'region')
    a=intersections.loc[intersections.grid_id=='a']
    assert dict(zip(a.region,a.share_frac))=={'x':.5,'y':.5}


def test_aqueduct_sentinels_and_category_are_not_average(cells):
    water=gpd.GeoDataFrame({'pfaf_id':[1,2], 'bws_raw':[.3,9999],
                           'bws_score':[1.,5.], 'bws_cat':[-1,4]},
                           geometry=[box(0,0,1,2),box(1,0,4,2)],crs=5070)
    result=summarize_water_stress(cells,water)
    a=result.set_index('grid_id').loc['a']
    assert a.baseline_water_stress_ratio==pytest.approx(.3)
    assert a.baseline_water_stress_extreme_scarcity_frac==pytest.approx(.5)
    assert a.baseline_water_stress_score==pytest.approx(3.)
    assert a.baseline_water_stress_category==-1  # lowest category ties, never averaged
    water['bws_raw']=-9999
    assert summarize_water_stress(cells,water).baseline_water_stress_ratio.isna().all()


def test_egrid_conversion_and_ambiguity(cells):
    assert pounds_per_mwh_to_kg_per_mwh(1000)==pytest.approx(453.59237)
    regions=gpd.GeoDataFrame({'subregion':['x','y'],'SRCO2RTA':[1000,0],'SRC2ERTA':[1200,0]},
                            geometry=[box(0,0,1,2),box(1,0,4,2)],crs=5070)
    multiple=gpd.GeoDataFrame(geometry=[box(0,0,2,2)],crs=5070)
    result=summarize_egrid(cells,regions,multiple)
    assert result.iloc[0].grid_carbon_intensity_kg_per_mwh==pytest.approx(272.155422)
    assert result.iloc[0].grid_co2_intensity_kg_per_mwh==pytest.approx(226.796185)
    assert result.iloc[0].egrid_multiple_subregion_overlap_frac==1
    assert json.loads(result.iloc[0].egrid_subregion_shares_json)=={'x':.5,'y':.5}


def test_flood_unmapped_unknown_and_union_no_double_count(cells):
    hazard=gpd.GeoDataFrame({'SFHA_TF':['T','T','U']},
                           geometry=[box(0,0,1,2),box(0,0,1,2),box(2,0,4,2)],crs=5070)
    result=summarize_flood(cells,hazard).set_index('grid_id')
    assert result.loc['a','flood_overlap_frac']==.5
    assert pd.isna(result.loc['b','flood_overlap_frac'])
    assert result.loc['b','flood_coverage_frac']==0
    assert summarize_flood(cells,None).flood_overlap_frac.isna().all()


def test_distance_measured_from_cell_polygon_and_in_km(cells):
    lines=gpd.GeoDataFrame(geometry=[LineString([(5,0),(5,2)])],crs=5070)
    assert distances_to_infrastructure(cells,lines)==pytest.approx([.003,.001])


def test_protected_overlap_uses_full_cell_denominator(cells):
    areas=gpd.GeoDataFrame({'GAP_Sts':['1']},geometry=[box(0,0,1,2)],crs=5070)
    result=summarize_protected(cells,areas)
    assert result.iloc[0].protected_overlap_frac==.5
    assert result.iloc[0].padus_coverage_frac==.5
    assert pd.isna(result.iloc[1].protected_overlap_frac)


def test_surveyed_flood_footprint_is_not_known_classification(cells):
    hazards=gpd.GeoDataFrame({'SFHA_TF':['U']},geometry=[box(0,0,4,2)],crs=5070)
    surveyed=gpd.GeoDataFrame(geometry=[box(0,0,4,2)],crs=5070)
    result=summarize_flood(cells,hazards,surveyed)
    assert result.flood_surveyed_coverage_frac.tolist()==[1.,1.]
    assert result.flood_coverage_frac.tolist()==[0.,0.]
    assert result.flood_overlap_frac.isna().all()


def test_flood_acquisition_bbox_does_not_extrapolate_zero(cells):
    hazards=gpd.GeoDataFrame({'SFHA_TF':[]},geometry=[],crs=5070)
    surveyed=gpd.GeoDataFrame(geometry=[],crs=5070)
    result=summarize_flood(cells,hazards,surveyed,hazard_query=box(0,0,2,2),surveyed_query=box(0,0,2,2))
    assert result.iloc[0].flood_surveyed_coverage_frac==0
    assert pd.isna(result.iloc[1].flood_surveyed_coverage_frac)
    assert result.iloc[1].flood_surveyed_coverage_frac_missing_reason=='outside_source_coverage'


def test_missing_inputs_retain_every_cell_and_metric_provenance(cells,tmp_path):
    result=build_features(cells,{},tmp_path/'output',study_geometry=box(0,0,4,2),cache_dir=tmp_path/'cache')
    assert result.grid_id.tolist()==['a','b']
    assert result.flood_overlap_frac.isna().all()
    provenance=pd.read_parquet(tmp_path/'output'/'feature_provenance.parquet')
    assert not provenance.duplicated(['grid_id','metric']).any()
    assert provenance.loc[provenance.status=='unknown','missing_reason'].notna().all()
    assert set(provenance.grid_id)=={'a','b'}
    assert provenance.loc[provenance.source_id=='eia_energy_atlas','aggregation_method'].eq('minimum study-intersection-polygon distance in EPSG:5070').all()
    report=json.loads((tmp_path/'output'/'coverage_report.json').read_text())
    assert report['input_cells']==report['output_cells']==2
    assert all(s['implemented'] for s in report['sources'].values())


def test_cache_digests_change_with_content(tmp_path):
    path=tmp_path/'data.bin'; path.write_bytes(b'a'); first=file_digest(path)
    path.write_bytes(b'b')
    assert first!=file_digest(path)


def test_bounded_source_request_key_and_corrupt_cache(tmp_path):
    first=request_identity('source','version',{'bbox':[0,0,1,1]})
    assert first==request_identity('source','version',{'bbox':[0,0,1,1]})
    assert first!=request_identity('source','version',{'bbox':[0,0,2,1]})
    path=tmp_path/'data.tif'; path.write_bytes(b'good')
    (tmp_path/'download_log.json').write_text(json.dumps([{'path':str(path),'bytes':4,'sha256':file_digest(path),'request_identity':first}]))
    assert verified_cached_request(path,first)
    with pytest.raises(ValueError,match='mismatch'): verified_cached_request(path,'other')
    path.write_bytes(b'bad!')
    with pytest.raises(ValueError,match='mismatch'): verified_cached_request(path,first)


def test_extract_only_requested_raster_and_verify_reuse(tmp_path):
    import zipfile
    path=tmp_path/'archive.zip'
    with zipfile.ZipFile(path,'w') as z:
        z.writestr('Data/needed.tif',b'needed')
        z.writestr('Data/unneeded.ige',b'unneeded')
    extracted=extract_verified_member(path,'Data/needed.tif',tmp_path/'cache')
    assert extracted.read_bytes()==b'needed'
    assert extract_verified_member(path,'Data/needed.tif',tmp_path/'cache')==extracted
    assert not list((tmp_path/'cache').rglob('*.ige'))
    extracted.write_bytes(b'broken')
    with pytest.raises(ValueError,match='checksum'): extract_verified_member(path,'Data/needed.tif',tmp_path/'cache')


def test_repeatable_source_free_build(cells,tmp_path):
    build_features(cells,{},tmp_path/'one',study_geometry=box(0,0,4,2),cache_dir=tmp_path/'cache')
    build_features(cells,{},tmp_path/'two',study_geometry=box(0,0,4,2),cache_dir=tmp_path/'cache')
    one=gpd.read_parquet(tmp_path/'one'/'us_grid_dataset.parquet')
    two=gpd.read_parquet(tmp_path/'two'/'us_grid_dataset.parquet')
    pd.testing.assert_frame_equal(one,two)
    assert json.loads((tmp_path/'two'/'coverage_report.json').read_text())['resumed_tiles']==1


def test_packed_wrc_probability_is_rejected_not_filtered(tmp_path):
    path=tmp_path/'packed.tif'
    with rasterio.open(path,'w',driver='GTiff',height=1,width=2,count=1,dtype='float32',
                       crs=5070,transform=from_origin(0,1,1,1),nodata=-9999) as ds:
        ds.write(np.array([[0,35]],dtype='float32'),1)
    result=summarize_wildfire({'wildfire_burn_probability':path},box(0,0,2,1))
    assert np.isnan(result['wildfire_burn_probability'])
    assert result['wildfire_burn_probability_missing_reason']=='invalid_source_value'


def test_source_content_and_grid_subset_invalidate_builder_cache(cells,tmp_path):
    path=tmp_path/'nlcd.tif'
    def write(code):
        with rasterio.open(path,'w',driver='GTiff',height=2,width=4,count=1,dtype='uint8',
                           crs=5070,transform=from_origin(0,2,1,1),nodata=250) as ds:
            ds.write(np.full((2,4),code,dtype='uint8'),1)
    source={'usgs_annual_nlcd':{'paths':{'land_cover':path},'data_mode':'synthetic'}}
    write(11)
    first=build_features(cells,source,tmp_path/'one',study_geometry=box(0,0,4,2),cache_dir=tmp_path/'cache')
    assert first.land_cover_water_frac.tolist()==[1,1]
    write(31)
    second=build_features(cells,source,tmp_path/'two',study_geometry=box(0,0,4,2),cache_dir=tmp_path/'cache')
    assert second.land_cover_water_frac.tolist()==[0,0]
    assert json.loads((tmp_path/'two'/'coverage_report.json').read_text())['resumed_tiles']==0
    build_features(cells.iloc[:1],source,tmp_path/'three',study_geometry=box(0,0,4,2),cache_dir=tmp_path/'cache')
    assert json.loads((tmp_path/'three'/'coverage_report.json').read_text())['resumed_tiles']==0


def test_spatial_preparation_matches_full_prepare_and_reads_inventory_once(tmp_path,monkeypatch):
    from dc_locator.geography import features
    # Grid IDs interleave distant cells so ordinary row chunks span both areas.
    grid=gpd.GeoDataFrame({'grid_id':['a','b','c','d'],
        'grid_definition_id':['fixture']*4,'tile_id':['west','east','west','east'],
        'row':[0]*4,'col':[0,500000,1,500001],'data_mode':['synthetic']*4,
        'cell_area_km2':[.000004]*4,'study_area_intersection_km2':[.000004]*4},
        geometry=[box(0,0,2,2),box(1000000,0,1000002,2),
                  box(2,0,4,2),box(1000002,0,1000004,2)],crs=5070)
    water=gpd.GeoDataFrame({'pfaf_id':[1,2],'bws_raw':[.25,.75],
        'bws_score':[1.,3.],'bws_cat':[0,2]},
        geometry=[box(-1,-1,5,3),box(999999,-1,1000005,3)],crs=5070)
    water_path=tmp_path/'water.gpkg';water.to_file(water_path,layer='water',driver='GPKG')
    regions=gpd.GeoDataFrame({'Subregion':['west','east']},geometry=water.geometry,crs=5070)
    regions_path=tmp_path/'regions.gpkg';regions.to_file(regions_path,driver='GPKG')
    workbook_path=tmp_path/'egrid.xlsx'
    pd.DataFrame({'SUBRGN':['west','east'],'SRCO2RTA':[100.,500.],
        'SRC2ERTA':[110.,510.]}).to_excel(workbook_path,sheet_name='SRL23',index=False)
    # This mapped line lies outside every preparation bbox; nearest distance
    # requires the full inventory even for a tile with no intersecting feature.
    line=gpd.GeoDataFrame(geometry=[LineString([(500000,0),(500000,2)])],crs=5070)
    line_path=tmp_path/'line.gpkg';line.to_file(line_path,driver='GPKG')
    source={'wri_aqueduct40':{'paths':{'baseline':water_path},'layer':'water','data_mode':'synthetic'},
        'epa_egrid':{'paths':{'regions':regions_path,'workbook':workbook_path},'data_mode':'synthetic'},
        'eia_energy_atlas':{'paths':{'transmission':line_path},'data_mode':'synthetic'}}
    study=box(0,0,1000004,2)
    baseline=build_features(grid,source,tmp_path/'baseline',study_geometry=study,cache_dir=tmp_path/'baseline_cache')
    calls=[];original=features.read_vector
    def record(path,selected,**kwargs):
        calls.append((str(path),len(selected),selected.total_bounds,kwargs.get('bounded',True)))
        return original(path,selected,**kwargs)
    monkeypatch.setattr(features,'read_vector',record)
    workbook_calls=[];original_workbook=features.read_subregion_workbook
    def record_workbook(path,**kwargs):
        workbook_calls.append(str(path))
        return original_workbook(path,**kwargs)
    monkeypatch.setattr(features,'read_subregion_workbook',record_workbook)
    bounded=build_features(grid,source,tmp_path/'bounded',study_geometry=study,
        cache_dir=tmp_path/'bounded_cache',prepare_per_tile=True)
    pd.testing.assert_frame_equal(baseline,bounded)
    pd.testing.assert_frame_equal(pd.read_parquet(tmp_path/'baseline/feature_provenance.parquet'),
        pd.read_parquet(tmp_path/'bounded/feature_provenance.parquet'))
    water_calls=[c for c in calls if c[0]==str(water_path)]
    assert len(water_calls)==2
    assert all(c[1]==2 and c[2][2]-c[2][0]==4 for c in water_calls)
    line_calls=[c for c in calls if c[0]==str(line_path)]
    assert len(line_calls)==1 and line_calls[0][3] is False
    assert len([c for c in calls if c[0]==str(regions_path)])==2
    assert workbook_calls==[str(workbook_path)]
    assert bounded.transmission_distance_km.tolist()==pytest.approx([499.998,500.,499.996,500.002])
    calls.clear()
    workbook_calls.clear()
    repeat=build_features(grid,source,tmp_path/'repeat',study_geometry=study,
        cache_dir=tmp_path/'bounded_cache',prepare_per_tile=True)
    pd.testing.assert_frame_equal(bounded,repeat)
    assert not calls and not workbook_calls
    assert json.loads((tmp_path/'repeat/coverage_report.json').read_text())['resumed_tiles']==2


def test_spatial_preparation_subdivides_large_grid_tiles(tmp_path,monkeypatch):
    from dc_locator.geography import features
    geometries=[box(c*50000,0,(c+1)*50000,50000) for c in range(7)]
    grid=gpd.GeoDataFrame({'grid_id':[str(c) for c in range(7)],
        'grid_definition_id':['fixture']*7,'tile_id':['one']*7,'row':[0]*7,
        'col':list(range(7)),'data_mode':['synthetic']*7,'cell_area_km2':[2500.]*7,
        'study_area_intersection_km2':[2500.]*7},geometry=geometries,crs=5070)
    calls=[];original=features._prepare
    def record(selected,source_inputs,*args,**kwargs):
        if 'wri_aqueduct40' in source_inputs:calls.append(selected.total_bounds)
        return original(selected,source_inputs,*args,**kwargs)
    monkeypatch.setattr(features,'_prepare',record)
    build_features(grid,{'wri_aqueduct40':{'paths':{}}},tmp_path/'output',
        study_geometry=box(0,0,350000,50000),cache_dir=tmp_path/'cache',
        prepare_per_tile=True,tile_size_cells=3)
    assert len(calls)==3
    assert all(bounds[2]-bounds[0]<=250000 and bounds[3]-bounds[1]<=250000 for bounds in calls)


def test_blocked_analysis_sources_remain_acquired_but_are_not_prepared(cells,tmp_path,monkeypatch):
    from dc_locator.geography import features
    line=gpd.GeoDataFrame({'inventory_id':['mapped']},geometry=[LineString([(5,0),(5,2)])],crs=5070)
    source={'eia_energy_atlas':{'paths':{'transmission':line},'data_mode':'synthetic',
        'quality_blocker':'not_computed','blocker_detail':'Excluded from the declared national baseline'}}
    def unexpected_read(*args,**kwargs):
        pytest.fail('A source intentionally excluded from analysis must not be loaded')
    monkeypatch.setattr(features,'read_vector',unexpected_read)
    result=build_features(cells,source,tmp_path/'output',study_geometry=box(0,0,4,2),cache_dir=tmp_path/'cache')
    assert result.transmission_distance_km.isna().all()
    provenance=pd.read_parquet(tmp_path/'output/feature_provenance.parquet')
    assert provenance.loc[provenance.source_id=='eia_energy_atlas','missing_reason'].eq('not_computed').all()
    report=json.loads((tmp_path/'output/coverage_report.json').read_text())
    assert report['sources']['eia_energy_atlas']['acquired'] is True
    assert report['sources']['eia_energy_atlas']['analyzed'] is False


def test_coverage_extent_describes_supplied_grid(cells,tmp_path):
    build_features(cells,{},tmp_path/'output',study_geometry=box(0,0,4,2),cache_dir=tmp_path/'cache')
    report=json.loads((tmp_path/'output/coverage_report.json').read_text())
    assert 'dev_tiny' not in report['analysis_extent']
    assert report['analysis_bounds_5070_m']==[0.,0.,4.,2.]
    assert report['analysis_study_area_km2']==pytest.approx(.000008)


def test_explicit_source_calculation_method_is_recorded(cells,tmp_path):
    source={'usgs_annual_nlcd':{'paths':{},'method':'Native categorical raster projected with nearest-neighbor sampling',
        'aggregation_method':'area-weighted classes after declared raster reprojection'}}
    build_features(cells,source,tmp_path/'output',study_geometry=box(0,0,4,2),cache_dir=tmp_path/'cache')
    provenance=pd.read_parquet(tmp_path/'output/feature_provenance.parquet')
    nlcd=provenance.loc[provenance.source_id=='usgs_annual_nlcd']
    assert nlcd.method.eq(source['usgs_annual_nlcd']['method']).all()
    assert nlcd.aggregation_method.eq(source['usgs_annual_nlcd']['aggregation_method']).all()
