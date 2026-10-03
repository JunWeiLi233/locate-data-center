"""Tests for dc_locator.geography.distance."""

from __future__ import annotations

import math

import numpy as np
import pytest

from dc_locator.geography.distance import (
    geodesic_distance_km,
    geodesic_distance_km_array,
    planar_distance_km,
    planar_distance_km_array,
)

GRS80_SEMI_MAJOR_AXIS_M = 6_378_137.0  # defining constant of the GRS80 ellipsoid (exact, by definition)


def test_geodesic_distance_zero_for_identical_points() -> None:
    assert geodesic_distance_km(-100.0, 40.0, -100.0, 40.0) == pytest.approx(0.0, abs=1e-9)


def test_geodesic_distance_symmetric() -> None:
    d1 = geodesic_distance_km(-100.0, 40.0, -90.0, 35.0)
    d2 = geodesic_distance_km(-90.0, 35.0, -100.0, 40.0)
    assert d1 == pytest.approx(d2)


def test_geodesic_distance_one_degree_on_equator_matches_ellipsoid_circumference() -> None:
    """The equator is an exact geodesic circle of an ellipsoid of revolution,
    so 1 degree of longitude along it must equal (2*pi*a)/360 for the GRS80
    semi-major axis 'a' -- an independently derivable expected value, not
    just a re-run of the function under test.
    """
    expected_km = (2 * math.pi * GRS80_SEMI_MAJOR_AXIS_M) / 360.0 / 1000.0
    actual_km = geodesic_distance_km(0.0, 0.0, 1.0, 0.0)
    assert actual_km == pytest.approx(expected_km, rel=1e-6)


def test_geodesic_distance_array_matches_scalar() -> None:
    lon1, lat1 = np.array([-100.0, 0.0]), np.array([40.0, 0.0])
    lon2, lat2 = np.array([-90.0, 1.0]), np.array([35.0, 0.0])
    array_result = geodesic_distance_km_array(lon1, lat1, lon2, lat2)
    scalar_results = [geodesic_distance_km(a, b, c, d) for a, b, c, d in zip(lon1, lat1, lon2, lat2)]
    np.testing.assert_allclose(array_result, scalar_results)


def test_planar_distance_3_4_5_triangle() -> None:
    # A 3-4-5 right triangle scaled by 1000: legs 3000m/4000m, hypotenuse 5000m = 5km exactly.
    assert planar_distance_km(0.0, 0.0, 3000.0, 4000.0) == pytest.approx(5.0)


def test_planar_distance_zero_for_identical_points() -> None:
    assert planar_distance_km(100.0, 200.0, 100.0, 200.0) == 0.0


def test_planar_distance_array_matches_scalar() -> None:
    x1, y1 = np.array([0.0, 1.0]), np.array([0.0, 1.0])
    x2, y2 = np.array([3000.0, 1.0]), np.array([4000.0, 1.0])
    array_result = planar_distance_km_array(x1, y1, x2, y2)
    scalar_results = [planar_distance_km(a, b, c, d) for a, b, c, d in zip(x1, y1, x2, y2)]
    np.testing.assert_allclose(array_result, scalar_results)


def test_epsg_5070_is_truly_equal_area_not_equal_distance() -> None:
    """Empirically confirms the docstring's claim: areal_scale is exactly 1.0
    (equal-area), while linear scale factors deviate from 1.0 away from the
    standard parallels -- i.e. distance is NOT preserved, only area is.
    """
    from pyproj import CRS, Proj

    proj = Proj(CRS.from_epsg(5070))
    f_on_parallel = proj.get_factors(-96.0, 29.5)  # exact standard parallel
    f_off_parallel = proj.get_factors(-96.0, 24.0)  # near the southern CONUS extreme

    assert f_on_parallel.areal_scale == pytest.approx(1.0, abs=1e-9)
    assert f_off_parallel.areal_scale == pytest.approx(1.0, abs=1e-9)
    assert f_on_parallel.meridional_scale == pytest.approx(1.0, abs=1e-6)
    assert f_off_parallel.meridional_scale != pytest.approx(1.0, abs=1e-3)
