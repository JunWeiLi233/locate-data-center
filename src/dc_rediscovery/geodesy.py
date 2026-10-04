"""Great-circle distances, nearest-neighbour queries and greedy minimum-separation selection.

All distances are haversine distances on a sphere of radius ``EARTH_RADIUS_KM`` (IUGG mean radius R1).
Against the WGS84 ellipsoid (``pyproj.Geod``) the spherical approximation errs by at most about 0.5%,
which is about 0.5 km at 100 km. ``tests/test_rediscovery_geodesy.py`` checks this bound.

Nearest-neighbour searches use a k-d tree on unit vectors. Chord length is a strictly increasing function
of the central angle, so the chord-nearest point is the great-circle-nearest point. Converting the chord
with ``2·R·asin(c/2)`` gives the same haversine distance up to floating rounding.
"""
from __future__ import annotations

import numpy as np
from scipy.spatial import cKDTree

EARTH_RADIUS_KM = 6371.0088
DISTANCE_METHOD = "haversine_spherical_r6371.0088km"


def _validated(lat, lon) -> tuple[np.ndarray, np.ndarray]:
    lat = np.asarray(lat, dtype=float)
    lon = np.asarray(lon, dtype=float)
    if lat.shape != lon.shape:
        raise ValueError("Latitude and longitude arrays must have the same shape")
    if not (np.isfinite(lat).all() and np.isfinite(lon).all()):
        raise ValueError("Coordinates must be finite; unknown locations cannot be measured")
    if (np.abs(lat) > 90).any() or (np.abs(lon) > 180).any():
        raise ValueError("Coordinates must be latitude/longitude degrees (EPSG:4326)")
    return lat, lon


def haversine_km(lat1, lon1, lat2, lon2) -> np.ndarray:
    """Vectorized (broadcasting) great-circle distance in kilometres."""
    lat1, lon1 = _validated(*np.broadcast_arrays(np.asarray(lat1, float), np.asarray(lon1, float)))
    lat2, lon2 = _validated(*np.broadcast_arrays(np.asarray(lat2, float), np.asarray(lon2, float)))
    phi1, phi2 = np.radians(lat1), np.radians(lat2)
    half_dphi = (phi2 - phi1) / 2.0
    half_dlambda = np.radians(lon2 - lon1) / 2.0
    a = np.sin(half_dphi) ** 2 + np.cos(phi1) * np.cos(phi2) * np.sin(half_dlambda) ** 2
    return 2.0 * EARTH_RADIUS_KM * np.arcsin(np.sqrt(np.clip(a, 0.0, 1.0)))


def unit_vectors(lat, lon) -> np.ndarray:
    lat, lon = _validated(lat, lon)
    phi, lam = np.radians(lat).ravel(), np.radians(lon).ravel()
    return np.column_stack([np.cos(phi) * np.cos(lam), np.cos(phi) * np.sin(lam), np.sin(phi)])


def km_to_chord(km: float | np.ndarray) -> np.ndarray:
    km = np.asarray(km, dtype=float)
    if (km < 0).any() or (km > np.pi * EARTH_RADIUS_KM).any():
        raise ValueError("Distance must lie between zero and half the Earth's circumference")
    return 2.0 * np.sin(km / (2.0 * EARTH_RADIUS_KM))


def chord_to_km(chord: float | np.ndarray) -> np.ndarray:
    return 2.0 * EARTH_RADIUS_KM * np.arcsin(np.clip(np.asarray(chord, dtype=float) / 2.0, 0.0, 1.0))


class SphericalIndex:
    """Nearest-point queries against a fixed set of latitude/longitude points."""

    def __init__(self, lat, lon):
        self.lat, self.lon = _validated(lat, lon)
        if self.lat.ndim != 1 or self.lat.size == 0:
            raise ValueError("A spherical index needs a nonempty one-dimensional point set")
        self.tree = cKDTree(unit_vectors(self.lat, self.lon))

    def nearest(self, lat, lon) -> tuple[np.ndarray, np.ndarray]:
        """Return (haversine km, index) of the nearest indexed point for each query point."""
        lat, lon = _validated(lat, lon)
        if lat.size == 0:
            return np.empty(0), np.empty(0, dtype=int)
        _, index = self.tree.query(unit_vectors(lat, lon), k=1)
        index = np.asarray(index, dtype=int)
        return haversine_km(lat.ravel(), lon.ravel(), self.lat[index], self.lon[index]), index

    def count_within(self, lat, lon, km: float) -> np.ndarray:
        """Indexed points within ``km`` (inclusive, up to floating rounding) of each query point."""
        lat, lon = _validated(lat, lon)
        if lat.size == 0:
            return np.empty(0, dtype=int)
        radius = float(km_to_chord(km)) * (1 + 1e-12)
        return np.asarray(self.tree.query_ball_point(unit_vectors(lat, lon), r=radius, return_length=True), dtype=int)


def greedy_separated(lat, lon, limit: int, min_distance_km: float, *, chunk: int = 20_000) -> np.ndarray:
    """Greedy non-maximum suppression over points already in priority order.

    Walks the points in the given order and keeps a point only when it is at least ``min_distance_km`` from
    every point kept so far. Returns the kept positions, in order, stopping at ``limit``. The strongest
    representative of a neighbourhood is therefore the first one in priority order. Because the walk is
    greedy, the first ``n`` kept points are exactly the result for ``limit = n`` (prefix consistency).
    """
    lat, lon = _validated(lat, lon)
    return greedy_separated_lazy(lat.size, lambda start, stop: (lat[start:stop], lon[start:stop]), limit,
                                 min_distance_km, chunk=chunk)


def greedy_separated_lazy(total: int, coordinates, limit: int, min_distance_km: float, *, chunk: int = 20_000) -> np.ndarray:
    """``greedy_separated`` when coordinates are produced per chunk by ``coordinates(start, stop)``.

    This avoids materializing coordinates for millions of ranked cells when only a short prefix is scanned.
    """
    if limit < 1:
        raise ValueError("At least one separated point must be requested")
    if min_distance_km < 0:
        raise ValueError("The minimum separation cannot be negative")
    separation = float(km_to_chord(min_distance_km))
    kept: list[int] = []
    kept_vectors = np.empty((0, 3))
    for start in range(0, total, chunk):
        stop = min(total, start + chunk)
        block = unit_vectors(*coordinates(start, stop))
        alive = np.ones(len(block), dtype=bool)
        if len(kept_vectors) and separation > 0:
            distance, _ = cKDTree(kept_vectors).query(block, k=1)
            alive &= distance >= separation
        for position in np.flatnonzero(alive):
            if not alive[position]:
                continue
            kept.append(start + int(position))
            kept_vectors = np.vstack([kept_vectors, block[position]])
            if len(kept) >= limit:
                return np.asarray(kept, dtype=int)
            if separation > 0:
                alive[position + 1:] &= np.linalg.norm(block[position + 1:] - block[position], axis=1) >= separation
    return np.asarray(kept, dtype=int)
