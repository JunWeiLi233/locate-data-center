"""Native-field synthetic overlays; no synthetic data in processed geography."""
import importlib
import importlib.util
import json

import geopandas as gpd
import numpy as np
import pandas as pd
import pytest
from shapely.geometry import box, Polygon, Point
from dc_locator.schemas import FeatureMetadata


def adapter():
    assert importlib.util.find_spec('dc_locator.geography.sources.aqueduct_future') is not None
    return importlib.import_module('dc_locator.geography.sources.aqueduct_future')


def fixtures():
    cells=gpd.GeoDataFrame(dict(grid_id=['g'],grid_definition_id=['fixture'],data_mode=['synthetic'],study_area_intersection_km2=[.0001]),geometry=[box(0,0,10,10)],crs=5070)
    water=gpd.GeoDataFrame(dict(pfaf_id=[1,2],bau30_ws_x_r=[9999,.25],bau30_ws_x_s=[5.,1.],bau30_ws_x_c=[4,0],bau30_ws_x_l=['Extremely High','Low']),geometry=[box(0,0,5,10),box(5,0,10,10)],crs=5070)
    return cells,water


def baseline(cells):
    rows=[FeatureMetadata(grid_id=g,metric='fixture_baseline',value=0,unit='frac',source_id='fixture',status='observed',confidence='high',data_mode='synthetic').model_dump(mode='json') for g in cells.grid_id]
    p=pd.DataFrame(rows); p.attrs['grid_definition_id']='fixture'
    return p


def test_native_ratios_scores_category_label_and_scarcity_stay_distinct():
    c,w=fixtures()
    row=adapter().summarize_future_water_stress(c,w,pathway='bau',milestone_year=2030).iloc[0]
    prefix='aqueduct_bau_2030_water_stress_'
    assert row[prefix+'ratio']==.25
    assert row[prefix+'ratio_coverage_frac']==.5
    assert row[prefix+'score']==3
    assert row[prefix+'score_coverage_frac']==1
    assert row[prefix+'category']==0
    assert row[prefix+'label']=='Low'
    assert row[prefix+'extreme_scarcity_frac']==.5
    assert json.loads(row[prefix+'category_shares_json'])=={'0':.5,'4':.5}


def test_future_nulls_are_missing_and_no_2040_is_interpolated():
    c,w=fixtures(); w.loc[1,['bau30_ws_x_r','bau30_ws_x_s','bau30_ws_x_c','bau30_ws_x_l']]=None
    row=adapter().summarize_future_water_stress(c,w,pathway='bau',milestone_year=2030).iloc[0]
    assert pd.isna(row.aqueduct_bau_2030_water_stress_ratio)
    assert row.aqueduct_bau_2030_water_stress_score==5
    assert row.aqueduct_bau_2030_water_stress_score_coverage_frac==.5
    unsupported=adapter().summarize_future_water_stress(c,w,pathway='bau',milestone_year=2040).iloc[0]
    assert pd.isna(unsupported.aqueduct_bau_2040_water_stress_score)
    assert unsupported.aqueduct_bau_2040_water_stress_score_coverage_frac==0


@pytest.mark.parametrize('field,value',[('bau30_ws_x_r',-9999),('bau30_ws_x_s',7),('bau30_ws_x_c',1.5),('bau30_ws_x_s',np.inf)])
def test_invalid_native_future_values_are_rejected_not_reinterpreted(field,value):
    c,w=fixtures(); w[field]=w[field].astype(float) if field!='bau30_ws_x_l' else w[field]
    w.loc[0,field]=value
    with pytest.raises(ValueError):
        adapter().summarize_future_water_stress(c,w,pathway='bau',milestone_year=2030)


def test_duplicate_conflicting_pfaf_and_overlapping_basins_fail_loud():
    c,w=fixtures()
    duplicate=pd.concat([w,w.iloc[[0]]],ignore_index=True); duplicate.loc[2,'bau30_ws_x_s']=2
    with pytest.raises(ValueError,match='pfaf'):
        adapter().summarize_future_water_stress(c,duplicate,pathway='bau',milestone_year=2030)
    w.geometry=[box(0,0,6,10),box(4,0,10,10)]
    with pytest.raises(ValueError,match='overlap'):
        adapter().summarize_future_water_stress(c,w,pathway='bau',milestone_year=2030)


def test_feature_builder_preserves_baseline_and_carries_window_native_evidence():
    c,w=fixtures(); p=baseline(c)
    result,provenance,coverage,manifest=adapter().build_aqueduct_future_features(c,p,dict(paths={'future':w},data_mode='synthetic'),pathways=['bau'],milestone_years=[2030,2040],study_geometry=box(0,0,10,10))
    pd.testing.assert_frame_equal(result[c.columns],c)
    native=provenance.loc[provenance.metric=='aqueduct_bau_2030_water_stress_score'].iloc[0]
    assert native.status=='scenario'
    assert native.source_field=='bau30_ws_x_s'
    assert native.data_year=='2030 milestone; 2015-2045 trend window; SSP3-RCP7.0'
    assert native.unit=='score_0_to_5'
    assert native.value==3
    unknown=provenance.loc[provenance.metric=='aqueduct_bau_2040_water_stress_score'].iloc[0]
    assert unknown.status=='unknown' and pd.isna(unknown.value)
    assert unknown.missing_reason=='unsupported_source_period'
    assert provenance.attrs['grid_definition_id']=='fixture'
    pd.testing.assert_frame_equal(provenance.iloc[:len(p)].reset_index(drop=True),p)
    assert coverage['analyzed_cells']==1 and manifest['source']['implemented'] is True
    assert 'five-GCM median' in native.method


@pytest.mark.parametrize('fault',['wrong_crs','no_crs','duplicate_id','empty','invalid','point','nonfinite'])
def test_overlay_rejects_invalid_cell_geometry_and_identity(fault):
    c,w=fixtures()
    if fault=='wrong_crs': c=c.set_crs(4326,allow_override=True)
    elif fault=='no_crs': c=c.set_crs(None,allow_override=True)
    elif fault=='duplicate_id': c=pd.concat([c,c],ignore_index=True)
    elif fault=='empty': c.geometry=[Polygon()]
    elif fault=='invalid': c.geometry=[Polygon([(0,0),(10,10),(10,0),(0,10),(0,0)])]
    elif fault=='point': c.geometry=[Point(0,0)]
    else: c.geometry=[Polygon([(0,0),(float('inf'),0),(10,10),(0,0)])]
    with pytest.raises(ValueError): adapter().summarize_future_water_stress(c,w,pathway='bau',milestone_year=2030)
    with pytest.raises(ValueError): adapter().build_aqueduct_future_features(c,baseline(c),dict(paths={'future':w},data_mode='synthetic'),pathways=['bau'],milestone_years=[2030],study_geometry=box(0,0,10,10))


@pytest.mark.parametrize('fault',['missing_identity','wrong_identity','malformed','wrong_grid','wrong_mode','duplicate','nonfinite'])
def test_builder_rejects_invalid_baseline_provenance(fault):
    c,w=fixtures(); p=baseline(c)
    if fault=='missing_identity': p.attrs.clear()
    elif fault=='wrong_identity': p.attrs['grid_definition_id']='other'
    elif fault=='malformed': p=p[['grid_id','metric','status']]
    elif fault=='wrong_grid': p['grid_id']='WRONG'
    elif fault=='wrong_mode': p['data_mode']='real'
    elif fault=='duplicate': p=pd.concat([p,p],ignore_index=True)
    else: p['value']=float('inf')
    with pytest.raises(ValueError): adapter().build_aqueduct_future_features(c,p,dict(paths={'future':w},data_mode='synthetic'),pathways=['bau'],milestone_years=[2030],study_geometry=box(0,0,10,10))
