"""Hand-calculated checks for great-circle distances, nearest queries and greedy minimum separation."""
import math

import numpy as np
import pytest
from pyproj import Geod

from dc_rediscovery.geodesy import (EARTH_RADIUS_KM, SphericalIndex, chord_to_km, greedy_separated, haversine_km,
                                    km_to_chord)

ONE_DEGREE_KM = EARTH_RADIUS_KM * math.pi / 180  # 111.19508372... km on the IUGG mean sphere


def test_haversine_hand_values():
    assert haversine_km(0, 0, 0, 1) == pytest.approx(ONE_DEGREE_KM, rel=1e-12)
    assert haversine_km(0, 0, 1, 0) == pytest.approx(ONE_DEGREE_KM, rel=1e-12)
    assert haversine_km(0, 0, 90, 0) == pytest.approx(EARTH_RADIUS_KM * math.pi / 2, rel=1e-12)
    assert haversine_km(10, 20, 10, 20) == 0
    # At latitude 60 a degree of longitude spans half the equatorial degree (small-angle check).
    assert haversine_km(60, 0, 60, 0.01) == pytest.approx(0.5 * ONE_DEGREE_KM * 0.01, rel=1e-4)
    # Symmetric and broadcasting.
    distances = haversine_km([0, 0], [0, 0], [0, 0], [1, 2])
    assert distances == pytest.approx([ONE_DEGREE_KM, 2 * ONE_DEGREE_KM], rel=1e-12)


def test_spherical_error_against_wgs84_is_bounded():
    geod = Geod(ellps="WGS84")
    pairs = [((38.95, -77.45), (40.71, -74.01)), ((32.78, -96.80), (33.45, -112.07)), ((47.23, -119.85), (44.30, -120.83)),
             ((44.97, -73.45), (42.65, -73.75))]
    for (lat1, lon1), (lat2, lon2) in pairs:
        _, _, metres = geod.inv(lon1, lat1, lon2, lat2)
        spherical = float(haversine_km(lat1, lon1, lat2, lon2))
        assert abs(spherical - metres / 1000) / (metres / 1000) < 0.006


def test_chord_conversion_round_trip():
    km = np.array([0.0, 10.0, 25.0, 1000.0, 5000.0])
    assert chord_to_km(km_to_chord(km)) == pytest.approx(km, abs=1e-9)
    with pytest.raises(ValueError):
        km_to_chord(-1)


def test_invalid_coordinates_are_refused():
    with pytest.raises(ValueError):
        haversine_km(np.nan, 0, 0, 0)
    with pytest.raises(ValueError):
        haversine_km(91, 0, 0, 0)
    with pytest.raises(ValueError):
        SphericalIndex([], [])


def test_nearest_and_counts():
    index = SphericalIndex([0, 0, 0], [0, 1, 3])
    distance, position = index.nearest([0, 0], [0.4, 2.6])
    assert position.tolist() == [0, 2]
    assert distance == pytest.approx([0.4 * ONE_DEGREE_KM, 0.4 * ONE_DEGREE_KM], rel=1e-9)
    # Inclusive radius: exactly one degree away counts.
    assert index.count_within([0], [0], ONE_DEGREE_KM).tolist() == [2]
    assert index.count_within([0], [0], ONE_DEGREE_KM * 0.999).tolist() == [1]


def test_greedy_separation_keeps_strongest_and_is_prefix_consistent():
    # Points in priority order along the equator (degrees of longitude):
    # 0.0 kept; 0.1 (11 km) suppressed; 0.3 (33 km) kept; 0.4 (11 km from 0.3) suppressed; 1.0 kept.
    lon = np.array([0.0, 0.1, 0.3, 0.4, 1.0, 1.1])
    lat = np.zeros_like(lon)
    kept = greedy_separated(lat, lon, limit=10, min_distance_km=25)
    assert kept.tolist() == [0, 2, 4]
    assert greedy_separated(lat, lon, limit=2, min_distance_km=25).tolist() == kept[:2].tolist()
    # Zero separation keeps the first `limit` points; separation is pairwise in the result.
    assert greedy_separated(lat, lon, limit=4, min_distance_km=0).tolist() == [0, 1, 2, 3]
    chosen_lon = lon[kept]
    for i in range(len(chosen_lon)):
        for j in range(i + 1, len(chosen_lon)):
            assert haversine_km(0, chosen_lon[i], 0, chosen_lon[j]) >= 25


def test_greedy_separation_across_chunks_matches_single_chunk():
    rng = np.random.default_rng(7)
    lat = rng.uniform(35, 45, 2000)
    lon = rng.uniform(-100, -80, 2000)
    whole = greedy_separated(lat, lon, limit=150, min_distance_km=50, chunk=5000)
    pieces = greedy_separated(lat, lon, limit=150, min_distance_km=50, chunk=37)
    assert whole.tolist() == pieces.tolist()


def test_greedy_separation_requires_valid_arguments():
    with pytest.raises(ValueError):
        greedy_separated([0], [0], limit=0, min_distance_km=1)
    with pytest.raises(ValueError):
        greedy_separated([0], [0], limit=1, min_distance_km=-1)
