"""Bounded construction must preserve the fixed national lattice and attribution."""
from dataclasses import replace

import geopandas as gpd
import pandas as pd
import pytest
import shapely
from shapely.geometry import MultiPolygon, box

from dc_locator.config import GridConfig
from dc_locator.geography import grid as module
from dc_locator.geography.boundary import CONUSBoundary


def bounded(config, boundary, windows):
    assert hasattr(module, 'generate_bounded_grid'), 'Bounded grid construction is not implemented'
    return module.generate_bounded_grid(config, boundary, windows)


def assert_same_cells(actual, expected):
    expected = expected.reset_index(drop=True)
    pd.testing.assert_frame_equal(actual.drop(columns='geometry'), expected.drop(columns='geometry'))
    assert actual.crs == expected.crs
    assert shapely.equals_exact(actual.geometry.to_numpy(), expected.geometry.to_numpy(), 0).all()


def one_region_boundary(geometry):
    states = gpd.GeoDataFrame({'STATEFP':['48'], 'STUSPS':['TX']}, geometry=[geometry], crs=5070)
    counties = gpd.GeoDataFrame({'GEOID':['48001'], 'NAME':['Fixture']}, geometry=[geometry], crs=5070)
    return CONUSBoundary(geometry, states, counties, 'synthetic_fixture', 'fixture', 'fixture', 'fixture')


def national_origin_config():
    return GridConfig(crs='EPSG:5070', origin_x_m=-2500000, origin_y_m=3400000,
        cell_size_m=1000, grid_scheme_version=1, id_row_col_digits=4,
        tile_size_cells=25, min_intersection_km2=0, study_areas={})


def test_bounded_matches_selected_national_cells(synthetic_grid_config, synthetic_boundary):
    national, _ = module.generate_national_grid(synthetic_grid_config, synthetic_boundary)
    window = box(1,-9,9,1)
    expected = national.loc[shapely.area(shapely.intersection(national.geometry.to_numpy(), window)) > 0]
    actual, stats = bounded(synthetic_grid_config, synthetic_boundary, [window])
    assert_same_cells(actual, expected)
    assert stats['n_retained'] == 2
    assert stats['scope'] == 'bounded_windows'


def test_overlap_and_window_order_do_not_change_cells(synthetic_grid_config, synthetic_boundary):
    west, east = box(0,-10,20,10), box(10,-20,30,0)
    actual, _ = bounded(synthetic_grid_config, synthetic_boundary, [west,east,west])
    repeat, _ = bounded(synthetic_grid_config, synthetic_boundary, [east,west])
    national, _ = module.generate_national_grid(synthetic_grid_config, synthetic_boundary)
    union = west.union(east)
    expected = national.loc[shapely.area(shapely.intersection(national.geometry.to_numpy(), union)) > 0]
    assert_same_cells(actual, repeat)
    assert_same_cells(actual, expected)
    assert actual.grid_id.is_unique


def test_one_km_ids_are_global_without_national_allocation():
    config = national_origin_config()
    boundary = one_region_boundary(box(-2400000,200000,2300000,3300000))
    with pytest.raises(RuntimeError, match='Candidate grid would have'):
        module.generate_national_grid(config, boundary)
    window = box(-854000,2744000,-852000,2746000)
    actual, stats = bounded(config, boundary, [window])
    assert actual.grid_id.tolist() == ['g1000m-r0654-c1646','g1000m-r0654-c1647',
                                     'g1000m-r0655-c1646','g1000m-r0655-c1647']
    assert actual.grid_definition_id.eq('conus-epsg5070-ox-2500000-oy3400000-s1000m-v1').all()
    assert actual.cell_area_km2.eq(1).all()
    assert actual.study_area_intersection_km2.eq(1).all()
    assert stats['n_candidates_bbox'] == 4


def test_windows_select_full_coastal_squares(synthetic_grid_config):
    boundary = one_region_boundary(box(5,-5,15,5))
    actual, stats = bounded(synthetic_grid_config, boundary, [box(6,1,7,2)])
    assert len(actual) == 1
    assert actual.geometry.iloc[0].equals(box(0,0,10,10))
    assert actual.study_area_intersection_km2.iloc[0] == pytest.approx(25/1e6)
    assert actual.study_area_frac.iloc[0] == .25
    assert actual.state_share_primary_frac.iloc[0] == 1
    assert actual.county_share_primary_frac.iloc[0] == 1
    assert stats['n_retained'] == 1


def test_boundary_mismatch_is_not_silently_clamped(synthetic_grid_config):
    boundary = one_region_boundary(box(5,-5,15,5))
    counties = boundary.counties.copy()
    counties.geometry = [box(0,-5,15,5)]
    boundary = replace(boundary, counties=counties)
    with pytest.raises(module.GridIntegrityError, match='county_share_primary_frac outside'):
        bounded(synthetic_grid_config, boundary, [box(6,1,7,2)])


def test_bounded_threshold_retains_original_conus_area(synthetic_grid_config, synthetic_boundary):
    config = synthetic_grid_config.model_copy(update={'min_intersection_km2':10/1e6})
    actual, stats = bounded(config, synthetic_boundary, [box(0,-20,30,10)])
    national, _ = module.generate_national_grid(config, synthetic_boundary)
    assert_same_cells(actual, national)
    assert stats['n_excluded_by_min_intersection_threshold'] == 1
    assert stats['excluded_by_threshold_total_km2'] == pytest.approx(9/1e6)


@pytest.mark.parametrize('windows', [[], [box(0,0,0,1)], [None]])
def test_rejects_missing_or_nonareal_windows(synthetic_grid_config, synthetic_boundary, windows):
    with pytest.raises(ValueError, match='window'):
        bounded(synthetic_grid_config, synthetic_boundary, windows)


def test_rejects_geo_windows_with_wrong_crs(synthetic_grid_config, synthetic_boundary):
    windows = gpd.GeoSeries([box(0,0,1,1)], crs=4326)
    with pytest.raises(ValueError, match='EPSG:5070'):
        bounded(synthetic_grid_config, synthetic_boundary, windows)


def test_accepts_projected_geo_windows(synthetic_grid_config, synthetic_boundary):
    window = box(1,-9,9,1)
    shapes, _ = bounded(synthetic_grid_config, synthetic_boundary, [window])
    frame, _ = bounded(synthetic_grid_config, synthetic_boundary,
        gpd.GeoDataFrame(geometry=[window], crs=5070))
    assert_same_cells(frame, shapes)


def test_disjoint_multipolygon_does_not_enumerate_the_gap():
    config = national_origin_config()
    boundary = one_region_boundary(box(-2400000,200000,2300000,3300000))
    windows = MultiPolygon([box(-2300000,3100000,-2298000,3102000),
                            box(2200000,300000,2202000,302000)])
    actual, stats = bounded(config,boundary,[windows])
    assert len(actual) == 8
    assert stats['n_enumerated_window_bbox_cells'] == 8


def test_windows_with_holes_do_not_select_hole_cells(synthetic_grid_config, synthetic_boundary):
    window = box(0,-20,30,10).difference(box(10,-10,20,0))
    actual, _ = bounded(synthetic_grid_config,synthetic_boundary,[window])
    assert (1,1) not in set(zip(actual.row,actual.col))
    assert len(actual) == 8
