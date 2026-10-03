"""Shared pytest fixtures.

The synthetic boundary/states/counties fixture below is built in memory (pure
shapely/geopandas construction, no files on disk) rather than loaded from a
file under `tests/fixtures/` -- it never touches `data/processed/` and
contains no real geographic data, so it stays well inside AGENTS.md section
3.6's synthetic-data quarantine while keeping the hand-calculated expected
values (see `tests/test_grid.py`) easy to audit directly in the test source.

Geometry note: the fixture's coordinates are small synthetic numbers (tens of
metres) rather than real-world EPSG:5070 CONUS coordinates. They are
*labelled* EPSG:5070 only so `dc_locator.geography.grid` (which assumes that
CRS) runs unmodified; the fixture exists to hand-verify the grid-generation
*algorithm* (row/col math, area bookkeeping, state/county attribution), not
to represent an actual place.
"""

from __future__ import annotations

import geopandas as gpd
import pytest
from shapely.geometry import box

from dc_locator.config import GridConfig, StudyAreaBBox
from dc_locator.geography.boundary import TARGET_CRS, CONUSBoundary


@pytest.fixture
def synthetic_grid_config() -> GridConfig:
    """A GridConfig with the same shape as configs/grid.yaml, but a tiny
    origin/cell-size chosen to match `synthetic_boundary`'s hand-calculated
    geometry (see tests/test_grid.py for the worked-out expected areas).
    """
    return GridConfig(
        crs="EPSG:5070",
        origin_x_m=0.0,
        origin_y_m=10.0,
        cell_size_m=10.0,
        grid_scheme_version=1,
        id_row_col_digits=2,
        tile_size_cells=2,
        min_intersection_km2=0.0,
        study_areas={"dev_tiny": StudyAreaBBox(lon_min=-96.0, lat_min=30.0, lon_max=-95.5, lat_max=30.5)},
    )


@pytest.fixture
def synthetic_boundary() -> CONUSBoundary:
    """A tiny, fully hand-calculable 'boundary': one rectangle split into two
    'states' (A, B), split in turn into three 'counties' (A1, A2, B01).

    Layout (x, y in synthetic metres):

        boundary = [3,23] x [-17,3]   (20 x 20 = 400 area units^2)
        state A  = [3,13] x [-17,3]   state B = [13,23] x [-17,3]
        county A1 = [3,13] x [-17,-7] county A2 = [3,13] x [-7,3]
        county B01 = [13,23] x [-17,3]  (== state B, one county)

    With `synthetic_grid_config` (origin (0,10), cell_size 10), this produces
    exactly the 3x3 candidate grid (rows 0-2, cols 0-2) hand-worked-out in
    tests/test_grid.py::test_generate_national_grid_matches_hand_calculation.
    """
    boundary_geom = box(3, -17, 23, 3)

    states = gpd.GeoDataFrame(
        {"STATEFP": ["01", "02"], "STUSPS": ["AA", "BB"]},
        geometry=[box(3, -17, 13, 3), box(13, -17, 23, 3)],
        crs=TARGET_CRS,
    )
    counties = gpd.GeoDataFrame(
        {
            "GEOID": ["A1000", "A2000", "B0100"],
            "NAME": ["County A1", "County A2", "County B01"],
            "STATEFP": ["01", "01", "02"],
        },
        geometry=[box(3, -17, 13, -7), box(3, -7, 13, 3), box(13, -17, 23, 3)],
        crs=TARGET_CRS,
    )

    return CONUSBoundary(
        boundary=boundary_geom,
        states=states,
        counties=counties,
        source_id="synthetic_test_fixture",
        vintage="n/a",
        state_zip_sha256="0" * 64,
        county_zip_sha256="0" * 64,
    )
