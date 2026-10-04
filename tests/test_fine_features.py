"""National fine features equal the authoritative adapters on hand-built EPSG:5070 fixtures."""
import geopandas as gpd
import numpy as np
import pandas as pd
import pytest
import rasterio
import shapely
from rasterio.transform import from_origin

from dc_locator.config import load_grid_config
from dc_locator.geography.fine_features import FineSources, area_weighted, land_cover_shares, overlaps, window_cells, window_features
from dc_locator.geography.sources.aqueduct import summarize_water_stress
from dc_locator.geography.sources.egrid import summarize_egrid
from dc_locator.geography.sources.infrastructure import distances_to_infrastructure
from dc_locator.geography.sources.nlcd import CLASSES, summarize_land_cover
from dc_locator.paths import project_root

X0, Y0 = -2_500_000.0, 3_400_000.0
# Parent (row 7, col 8) of 3 km covers 1 km rows 21-23 and cols 24-26.
PARENT = shapely.box(X0 + 24_000, Y0 - 24_000, X0 + 27_000, Y0 - 21_000)


@pytest.fixture(scope='module')
def grid_config():
    return load_grid_config(project_root() / 'configs' / 'grid_regional.yaml')


@pytest.fixture
def land_cover(tmp_path):
    """Synthetic 30 m classes whose pixel edges are offset from the 1 km cell edges."""
    rng = np.random.default_rng(20261003)
    codes = np.array(sorted(CLASSES) + [0, 250])  # 0 is not a class (invalid); 250 is nodata
    data = rng.choice(codes, size=(110, 110), p=[0.85 / len(CLASSES)] * len(CLASSES) + [0.05, 0.10]).astype('uint8')
    path = tmp_path / 'land_cover_5070.tif'
    with rasterio.open(path, 'w', driver='GTiff', width=110, height=110, count=1, dtype='uint8', crs='EPSG:5070',
                       transform=from_origin(X0 + 24_000 - 85, Y0 - 21_000 + 55, 30, 30), nodata=250) as raster:
        raster.write(data, 1)
    return path


def test_overlaps_are_exact_interval_lengths():
    expected = np.array([[30, 0], [20, 10], [0, 30]])
    np.testing.assert_array_equal(overlaps(np.array([0., 30, 60, 90]), np.array([0., 50, 100])), expected)


def test_window_cells_keep_whole_cells_and_clip_border_cells(grid_config):
    interior = window_cells(grid_config, 7, 8, 3)
    assert interior.grid_id.tolist()[:2] == ['g1000m-r0021-c0024', 'g1000m-r0021-c0025'] and interior.full_cell.all()
    study = shapely.box(X0 + 24_000, Y0 - 24_000, X0 + 25_500, Y0 - 21_000)  # 1.5 columns of the parent
    border = window_cells(grid_config, 7, 8, 3, study)
    assert sorted(set(border.col)) == [24, 25] and len(border) == 6
    assert border.loc[border.col == 24, 'full_cell'].all() and not border.loc[border.col == 25, 'full_cell'].any()
    np.testing.assert_allclose(border.loc[border.col == 25, 'study_area_intersection_km2'], 0.5)
    assert shapely.equals(border.loc[border.col == 25, 'geometry'].iloc[0], shapely.box(X0 + 25_000, Y0 - 22_000, X0 + 25_500, Y0 - 21_000))


def test_full_cells_use_the_native_analysis_ring_order(grid_config):
    cells = window_cells(grid_config, 7, 8, 3)
    x, y = X0 + cells.col.to_numpy() * 1000, Y0 - cells.row.to_numpy() * 1000
    grid_squares = shapely.box(x, y - 1000, x + 1000, y)
    native_analysis = shapely.intersection(grid_squares, PARENT.buffer(100))
    np.testing.assert_array_equal(shapely.to_wkb(cells.geometry.to_numpy()), shapely.to_wkb(native_analysis))


def test_land_cover_shares_equal_the_nlcd_adapter(grid_config, land_cover):
    study = shapely.box(X0 + 24_000, Y0 - 24_000, X0 + 26_400, Y0 - 21_000)
    cells = window_cells(grid_config, 7, 8, 3, study)
    assert (~cells.full_cell).any() and cells.full_cell.any()
    with rasterio.open(land_cover) as raster:
        share, coverage = land_cover_shares(cells, raster, land_cover, 1000.0)
    expected = [summarize_land_cover(land_cover, geometry) for geometry in cells.geometry]
    np.testing.assert_allclose(share, [value['potentially_suitable_land_frac'] for value in expected], rtol=0, atol=1e-12)
    np.testing.assert_allclose(coverage, [value['nlcd_coverage_frac'] for value in expected], rtol=0, atol=1e-12)
    assert (coverage < 1).all()  # invalid and nodata pixels never count as observed land


def test_unobserved_land_stays_unknown_not_zero(grid_config, land_cover):
    cells = window_cells(grid_config, 9, 9, 3)  # outside the synthetic raster
    with rasterio.open(land_cover) as raster:
        share, coverage = land_cover_shares(cells, raster, land_cover, 1000.0)
    assert np.isnan(share).all() and (coverage == 0).all()


def test_area_weighting_equals_basin_and_egrid_adapters():
    cells = gpd.GeoDataFrame({'grid_id': ['a', 'b', 'c']}, geometry=[shapely.box(0, 0, 1000, 1000), shapely.box(1000, 0, 2000, 1000),
                                                                      shapely.box(2000, 0, 3000, 1000)], crs=5070)
    polygons = [shapely.box(0, -10, 1500, 1010), shapely.box(1500, -10, 2500, 1010), shapely.box(-10, -10, 1010, 1010)]
    values = np.array([1.0, 4.0, 3.0])  # the third key overlaps the first cell entirely: overlaps are preserved
    basins = gpd.GeoDataFrame({'pfaf_id': [1, 2, 3], 'bws_raw': values, 'bws_score': values, 'bws_cat': [1, 4, 3]}, geometry=polygons, crs=5070)
    adapter = summarize_water_stress(cells, basins)
    window = shapely.box(-100, -100, 3100, 1100)
    mean, coverage = area_weighted(cells.geometry.values, np.array(polygons), values, shapely.STRtree(np.array(polygons)), window)
    np.testing.assert_allclose(mean, adapter.baseline_water_stress_score, rtol=0, atol=1e-12)
    np.testing.assert_allclose(coverage, adapter.baseline_water_stress_score_coverage_frac, rtol=0, atol=1e-12)
    assert coverage[2] == pytest.approx(0.5)
    regions = gpd.GeoDataFrame({'subregion': ['N', 'S', 'O'], 'SRCO2RTA': values, 'SRC2ERTA': values}, geometry=polygons, crs=5070)
    egrid = summarize_egrid(cells, regions, unit='kg_per_mwh')
    np.testing.assert_allclose(mean, egrid.grid_carbon_intensity_kg_per_mwh, rtol=0, atol=1e-12)
    np.testing.assert_allclose(coverage, egrid.egrid_coverage_frac, rtol=0, atol=1e-12)


def test_coverage_sums_piece_shares_in_native_order():
    rng = np.random.default_rng(317)
    cells = gpd.GeoDataFrame({'grid_id': [str(i) for i in range(20)]},
        geometry=[shapely.box(0.123 + i * 1200, 0.379, 1000.234 + i * 1200, 1000.337) for i in range(20)], crs=5070)
    polygons, keys = [], []
    for i, geometry in enumerate(cells.geometry):
        x0, y0, x1, y1 = geometry.bounds
        split = x0 + (x1 - x0) * rng.uniform(.1, .9)
        polygons.extend([shapely.box(x0, y0, split, y1), shapely.box(split, y0, x1, y1)])
        keys.extend([str(2*i), str(2*i+1)])
    values = np.ones(len(polygons))
    regions = gpd.GeoDataFrame({'subregion': keys, 'SRCO2RTA': values, 'SRC2ERTA': values}, geometry=polygons, crs=5070)
    native = summarize_egrid(cells, regions, unit='kg_per_mwh')
    _, coverage = area_weighted(cells.geometry.values, np.array(polygons), values, shapely.STRtree(polygons), shapely.box(-1, -1, 26000, 1100))
    np.testing.assert_array_equal(coverage, native.egrid_coverage_frac)


def test_window_features_use_adapter_distances_and_keep_missing_unknown(grid_config, land_cover):
    cells = window_cells(grid_config, 7, 8, 3)
    lines = gpd.GeoDataFrame(geometry=[shapely.LineString([(X0 + 20_000, Y0 - 30_000), (X0 + 20_000, Y0 - 10_000)]),
                                       shapely.LineString([(X0 + 26_500, Y0 - 22_500), (X0 + 40_000, Y0 - 22_500)])], crs=5070)
    basin = shapely.box(X0 + 24_000, Y0 - 24_000, X0 + 25_000, Y0 - 21_000)  # only column 24 has basin evidence
    sources = FineSources(land_cover=land_cover, transmission=lines.geometry.values, basins=np.array([basin]), basin_stress=np.array([2.0]),
                          egrid=np.array([PARENT.buffer(10)]), egrid_kg_per_mwh=np.array([400.0]), files={})
    with rasterio.open(land_cover) as raster:
        features = window_features(cells, sources, raster, PARENT, 1000.0)
    np.testing.assert_allclose(features.transmission_distance_km, distances_to_infrastructure(gpd.GeoDataFrame(cells, crs=5070), lines), rtol=0, atol=1e-12)
    assert features.loc[cells.col.eq(24).to_numpy(), 'baseline_water_stress_score'].eq(2.0).all()
    assert features.loc[cells.col.ne(24).to_numpy(), 'baseline_water_stress_score'].isna().all()
    assert features.loc[cells.col.ne(24).to_numpy(), 'baseline_water_stress_score_coverage_frac'].eq(0).all()
    np.testing.assert_allclose(features.grid_carbon_intensity_kg_per_mwh, 400.0)
    assert set(features.columns) >= {'potentially_suitable_land_frac', 'nlcd_coverage_frac', 'egrid_coverage_frac'}
    assert features.transmission_distance_km_status.eq('proxy').all()
    assert features.transmission_distance_km_confidence.eq('low').all()
    missing = cells.col.ne(24).to_numpy()
    assert features.loc[missing, 'baseline_water_stress_score_status'].eq('unknown').all()
    assert features.loc[missing, 'baseline_water_stress_score_confidence'].eq('unknown').all()
    assert features.loc[missing, 'baseline_water_stress_score_missing_reason'].eq('source_nodata').all()


def test_blocked_sources_cannot_enter_the_fast_surface():
    from dc_locator.geography.fine_features import load_fine_sources
    with pytest.raises(ValueError, match='quality blocker'):
        load_fine_sources({'usgs_annual_nlcd': {'quality_blocker': 'invalid_source_value'}}, shapely.bounds(PARENT))


def test_egrid_native_pounds_are_weighted_before_conversion(grid_config, land_cover):
    cells = window_cells(grid_config, 7, 8, 3)
    polygons = np.array([shapely.box(X0 + 24_000, Y0 - 24_000, X0 + 25_400, Y0 - 21_000),
                         shapely.box(X0 + 25_400, Y0 - 24_000, X0 + 27_000, Y0 - 21_000)])
    rates = np.array([213.289763, 1412.658952])
    from dc_locator.geography.sources.egrid import pounds_per_mwh_to_kg_per_mwh
    sources = FineSources(land_cover=land_cover, transmission=np.array([PARENT.boundary]), basins=polygons,
        basin_stress=np.array([1., 2.]), egrid=polygons, egrid_kg_per_mwh=pounds_per_mwh_to_kg_per_mwh(rates),
        egrid_lb_per_mwh=rates, files={})
    with rasterio.open(land_cover) as raster:
        features = window_features(cells, sources, raster, PARENT, 1000.)
    native = summarize_egrid(gpd.GeoDataFrame(cells, crs=5070),
        gpd.GeoDataFrame({'subregion': ['a', 'b'], 'SRCO2RTA': rates, 'SRC2ERTA': rates}, geometry=polygons, crs=5070),
        unit='lb_per_mwh')
    np.testing.assert_allclose(features.grid_carbon_intensity_kg_per_mwh, native.grid_carbon_intensity_kg_per_mwh, rtol=0, atol=1e-12)
