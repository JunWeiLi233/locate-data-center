"""Hand-calculated tests for `dc_locator.geography.grid` (AGENTS.md section
3.10: hand-calculated fixtures for formulas).

See tests/conftest.py::synthetic_boundary for the fixture layout. The table
below was computed by hand (axis-aligned rectangle intersections; every
subtotal is cross-checked against the fixture's own known county/state
areas in the test body) and is NOT derived by running the code under test.
"""

from __future__ import annotations

import math

import pytest
from pyproj import Transformer
from shapely.geometry import Point, box

from dc_locator.config import GridConfig, StudyAreaBBox
from dc_locator.geography.grid import (
    GridIdOverflowError,
    GridOriginViolationError,
    _aggregate_primary_and_all,
    generate_national_grid,
    make_grid_id,
    make_tile_id,
    row_col_for_point,
    select_study_area,
    validate_boundary_within_origin,
)

# grid_id -> (study_area_intersection, frac, is_boundary,
#             state_fips_primary, state_share, n_states, state_fips_all,
#             county_primary, county_share, n_counties, counties_all)
# State fixture: STATEFP "01"/"02" <-> STUSPS "AA"/"BB" (see conftest.py::synthetic_boundary).
EXPECTED = {
    (0, 0): (21.0, 0.21, True, "01", 1.0, 1, "01", "A2000", 1.0, 1, "A2000"),
    (0, 1): (30.0, 0.30, True, "02", 0.7, 2, "01;02", "B0100", 0.7, 2, "A2000;B0100"),
    (0, 2): (9.0, 0.09, True, "02", 1.0, 1, "02", "B0100", 1.0, 1, "B0100"),
    (1, 0): (70.0, 0.70, True, "01", 1.0, 1, "01", "A2000", 49.0 / 70.0, 2, "A1000;A2000"),
    (1, 1): (100.0, 1.00, False, "02", 0.7, 2, "01;02", "B0100", 0.7, 3, "A1000;A2000;B0100"),
    (1, 2): (30.0, 0.30, True, "02", 1.0, 1, "02", "B0100", 1.0, 1, "B0100"),
    (2, 0): (49.0, 0.49, True, "01", 1.0, 1, "01", "A1000", 1.0, 1, "A1000"),
    (2, 1): (70.0, 0.70, True, "02", 49.0 / 70.0, 2, "01;02", "B0100", 49.0 / 70.0, 2, "A1000;B0100"),
    (2, 2): (21.0, 0.21, True, "02", 1.0, 1, "02", "B0100", 1.0, 1, "B0100"),
}
_STATE_ABBR = {"01": "AA", "02": "BB"}
# Internal consistency check on the hand-derived table itself: the 9 cells'
# intersection areas must sum to the boundary's own area (20 x 20 = 400).
assert math.isclose(sum(v[0] for v in EXPECTED.values()), 400.0)


def test_generate_national_grid_matches_hand_calculation(synthetic_grid_config: GridConfig, synthetic_boundary) -> None:
    grid, stats = generate_national_grid(synthetic_grid_config, synthetic_boundary)

    assert stats["n_retained"] == 9
    assert stats["n_zero_area_touches_excluded"] == 0
    assert stats["n_excluded_by_min_intersection_threshold"] == 0
    assert set(zip(grid["row"], grid["col"])) == set(EXPECTED.keys())

    # Rows sorted by (row, col) ascending (GRID CONTRACT: national output sorted by row, col).
    assert list(zip(grid["row"], grid["col"])) == sorted(EXPECTED.keys())

    by_rc = {(int(r), int(c)): row for (r, c), row in zip(zip(grid["row"], grid["col"]), grid.to_dict("records"))}

    for (row, col), (
        exp_area, exp_frac, exp_boundary,
        exp_state, exp_state_share, exp_n_states, exp_states_all,
        exp_county, exp_county_share, exp_n_counties, exp_counties_all,
    ) in EXPECTED.items():
        cell = by_rc[(row, col)]
        label = f"cell(row={row},col={col})"

        assert cell["cell_area_km2"] == pytest.approx(100.0 / 1e6), label
        assert cell["study_area_intersection_km2"] == pytest.approx(exp_area / 1e6), label
        assert cell["study_area_frac"] == pytest.approx(exp_frac), label
        assert cell["is_boundary_cell"] == exp_boundary, label

        assert cell["state_fips_primary"] == exp_state, label
        assert cell["state_abbr_primary"] == _STATE_ABBR[exp_state], label
        assert cell["state_share_primary_frac"] == pytest.approx(exp_state_share), label
        assert cell["n_states"] == exp_n_states, label
        assert cell["state_fips_all"] == exp_states_all, label

        assert cell["county_geoid_primary"] == exp_county, label
        assert cell["county_share_primary_frac"] == pytest.approx(exp_county_share), label
        assert cell["n_counties"] == exp_n_counties, label
        assert cell["county_geoid_all"] == exp_counties_all, label

        # Centroid of the FULL cell square (not the CONUS-clipped shape):
        # centroid_x = origin_x + col*size + size/2; centroid_y = origin_y - row*size - size/2.
        assert cell["centroid_x_m"] == pytest.approx(0.0 + col * 10.0 + 5.0), label
        assert cell["centroid_y_m"] == pytest.approx(10.0 - row * 10.0 - 5.0), label

        assert cell["grid_id"] == make_grid_id(
            10.0, row, col, 2, grid_definition_id=synthetic_grid_config.grid_definition_id(),
        ), label
        assert cell["tile_id"] == make_tile_id(row, col, 2), label
        assert cell["data_mode"] == "real", label

    # A couple of exact string checks on the ID format itself (not just round-tripped via the same function).
    # The fixture uses a different origin from the published national v1,
    # so the 1.1 identity contract prefixes its definition to avoid collisions.
    assert by_rc[(0, 0)]["grid_id"] == "conus-epsg5070-ox0-oy10-s10m-v1--g10m-r00-c00"
    assert by_rc[(1, 1)]["grid_id"] == "conus-epsg5070-ox0-oy10-s10m-v1--g10m-r01-c01"
    assert by_rc[(2, 2)]["grid_id"] == "conus-epsg5070-ox0-oy10-s10m-v1--g10m-r02-c02"
    # tile_id always zero-pads to 4 digits regardless of grid.yaml:id_row_col_digits (an
    # independent formatting choice -- only grid_id's width is configurable).
    assert by_rc[(1, 1)]["tile_id"] == "t2-tr0000-tc0000"  # row1,col1 // tile_size 2 -> tile (0,0)
    assert by_rc[(2, 2)]["tile_id"] == "t2-tr0001-tc0001"  # row2,col2 // 2 -> tile (1,1)

    # grid_definition_id matches the config, and is identical for every row (GRID CONTRACT).
    assert (grid["grid_definition_id"] == synthetic_grid_config.grid_definition_id()).all()

    # Representative point is guaranteed to fall inside (cell ∩ CONUS); spot-check
    # by reprojecting EPSG:4326 rep_point back to EPSG:5070 and comparing against
    # the hand-known intersection bounds (cell(0,0) ∩ boundary == [3,10] x [0,3]).
    to_5070 = Transformer.from_crs("EPSG:4326", "EPSG:5070", always_xy=True)
    cell00 = by_rc[(0, 0)]
    x, y = to_5070.transform(cell00["rep_point_lon"], cell00["rep_point_lat"])
    assert 3.0 - 1e-6 <= x <= 10.0 + 1e-6
    assert 0.0 - 1e-6 <= y <= 3.0 + 1e-6


def test_generate_national_grid_is_deterministic(synthetic_grid_config: GridConfig, synthetic_boundary) -> None:
    grid_a, stats_a = generate_national_grid(synthetic_grid_config, synthetic_boundary)
    grid_b, stats_b = generate_national_grid(synthetic_grid_config, synthetic_boundary)
    assert stats_a == stats_b
    assert grid_a.drop(columns="geometry").equals(grid_b.drop(columns="geometry"))
    assert grid_a.geometry.geom_equals_exact(grid_b.geometry, tolerance=1e-9).all()


def test_generate_national_grid_ids_unique_and_geometries_valid(synthetic_grid_config: GridConfig, synthetic_boundary) -> None:
    grid, _ = generate_national_grid(synthetic_grid_config, synthetic_boundary)
    assert grid["grid_id"].is_unique
    assert grid.geometry.is_valid.all()
    assert (grid.geom_type == "Polygon").all()


def test_min_intersection_threshold_excludes_small_slivers(synthetic_grid_config: GridConfig, synthetic_boundary) -> None:
    # cell(0,2) has the single smallest area (9 units^2 = 9e-6 km2; the next
    # smallest, 21, is shared by two cells). A threshold strictly between 9
    # and 21 should exclude exactly that one cell and report it, never
    # silently drop it.
    cfg = synthetic_grid_config.model_copy(update={"min_intersection_km2": 10.0 / 1e6})
    grid, stats = generate_national_grid(cfg, synthetic_boundary)
    assert stats["n_retained"] == 8
    assert stats["n_excluded_by_min_intersection_threshold"] == 1
    assert stats["excluded_by_threshold_total_km2"] == pytest.approx(9.0 / 1e6)
    assert set(zip(grid["row"], grid["col"])) == set(EXPECTED.keys()) - {(0, 2)}


def test_validate_boundary_within_origin_fails_loudly_west() -> None:
    with pytest.raises(GridOriginViolationError, match="west of origin_x_m"):
        validate_boundary_within_origin((-10.0, 0.0, 10.0, 5.0), origin_x_m=0.0, origin_y_m=10.0)


def test_validate_boundary_within_origin_fails_loudly_north() -> None:
    with pytest.raises(GridOriginViolationError, match="north of origin_y_m"):
        validate_boundary_within_origin((0.0, 0.0, 10.0, 20.0), origin_x_m=0.0, origin_y_m=10.0)


def test_validate_boundary_within_origin_passes_when_enclosed() -> None:
    validate_boundary_within_origin((1.0, -5.0, 9.0, 9.0), origin_x_m=0.0, origin_y_m=10.0)  # must not raise


def test_generate_national_grid_fails_loudly_when_boundary_violates_origin(synthetic_grid_config: GridConfig, synthetic_boundary) -> None:
    import dataclasses

    bad_boundary = dataclasses.replace(synthetic_boundary, boundary=box(-5, -17, 23, 3))  # now west of origin_x_m=0
    with pytest.raises(GridOriginViolationError):
        generate_national_grid(synthetic_grid_config, bad_boundary)


def test_make_grid_id_format() -> None:
    assert make_grid_id(10000.0, 123, 456, 4) == "g10000m-r0123-c0456"
    assert make_grid_id(10000.0, 0, 0, 4) == "g10000m-r0000-c0000"


def test_make_grid_id_overflow_raises() -> None:
    with pytest.raises(GridIdOverflowError):
        make_grid_id(10000.0, 100, 0, 2)  # 100 needs 3 digits, digits=2


def test_make_grid_id_rejects_negative() -> None:
    with pytest.raises(ValueError):
        make_grid_id(10000.0, -1, 0, 4)


def test_make_tile_id() -> None:
    assert make_tile_id(0, 0, 25) == "t25-tr0000-tc0000"
    assert make_tile_id(24, 24, 25) == "t25-tr0000-tc0000"
    assert make_tile_id(25, 25, 25) == "t25-tr0001-tc0001"


def test_row_col_for_point() -> None:
    # row = floor((origin_y - y)/size); col = floor((x - origin_x)/size).
    assert row_col_for_point(x_m=5.0, y_m=5.0, origin_x_m=0.0, origin_y_m=10.0, cell_size_m=10.0) == (0, 0)
    assert row_col_for_point(x_m=15.0, y_m=-5.0, origin_x_m=0.0, origin_y_m=10.0, cell_size_m=10.0) == (1, 1)
    assert row_col_for_point(x_m=0.0, y_m=10.0, origin_x_m=0.0, origin_y_m=10.0, cell_size_m=10.0) == (0, 0)


def test_aggregate_primary_and_all_ties_broken_by_lowest_code() -> None:
    import pandas as pd

    df = pd.DataFrame(
        {
            "grid_id": ["g1", "g1", "g2"],
            "code": ["Z", "A", "M"],
            "area_m2": [50.0, 50.0, 10.0],  # g1: exact tie between Z and A
        }
    )
    out = _aggregate_primary_and_all(df, group_col="grid_id", code_col="code", area_col="area_m2")
    assert out.loc["g1", "primary_code"] == "A"  # lowest code wins the tie
    assert out.loc["g1", "all_codes"] == "A;Z"
    assert out.loc["g1", "n_distinct"] == 2
    assert out.loc["g2", "primary_code"] == "M"


def test_select_study_area_subsets_without_changing_attributes(synthetic_grid_config: GridConfig, synthetic_boundary) -> None:
    national, _ = generate_national_grid(synthetic_grid_config, synthetic_boundary)
    # A bbox is specified in EPSG:4326; synthetic coordinates aren't real lon/lat,
    # so this test only checks the *mechanism* (subset + attribute equality),
    # using a bbox wide enough to select everything after reprojection.
    wide_bbox = StudyAreaBBox(lon_min=-179.0, lat_min=-89.0, lon_max=179.0, lat_max=89.0)
    selected = select_study_area(national, wide_bbox)
    assert len(selected) == len(national)
    pd_national = national.drop(columns="geometry").set_index("grid_id").sort_index()
    pd_selected = selected.drop(columns="geometry").set_index("grid_id").sort_index()
    assert pd_national.equals(pd_selected)  # GRID CONTRACT: selection never changes a retained cell's attributes
