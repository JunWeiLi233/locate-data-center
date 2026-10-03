"""Distance helpers (GRID CONTRACT).

Never compute a distance in kilometres directly from a plain difference in
degrees of latitude/longitude (AGENTS.md section 6): a degree of longitude
spans roughly 111.3 km at the equator and shrinks toward the poles
(`cos(latitude)` scaling), so a naive degree-based distance is wrong by a
location-dependent factor across CONUS. This module provides two correct
alternatives:

- `geodesic_distance_km(_array)`: exact ellipsoidal (geodesic) distance via
  `pyproj.Geod`, for EPSG:4326 lon/lat points. Use this whenever accuracy
  matters more than raw speed.
- `planar_distance_km`: straight-line Euclidean distance on already-projected
  EPSG:5070 coordinates. Fast and adequate for most within-CONUS uses, but
  subject to the scale-error bound documented below.

EPSG:5070 (NAD83 / Conus Albers Equal Area) scale-error bound
--------------------------------------------------------------
Albers Equal Area is an equal-AREA projection (confirmed below: its point
areal-scale factor is exactly 1.0 everywhere), not an equal-DISTANCE one: it
is exact (scale factor 1.0) only along its two standard parallels (29.5N and
45.5N for this CRS's EPSG definition) and distorts straight-line distances
elsewhere. This bound was measured directly against `pyproj`, not assumed:

    from pyproj import CRS, Proj
    proj = Proj(CRS.from_epsg(5070))
    # swept latitude 24.0 to 49.4 in 0.1 deg steps, longitude fixed at -96
    # (the CRS's own false-origin meridian; Albers point scale depends only
    # on latitude, not longitude), reading .meridional_scale/.parallel_scale
    # at each point.

Result (recorded here verbatim; re-run the snippet above to reproduce):
over that latitude sweep, `areal_scale` was exactly 1.000000 at every point
(confirms the equal-area property), while the linear (meridional/parallel)
point-scale factor ranged from a minimum of 0.984698 (-1.53%, at the
southernmost latitude sampled, 24.0N -- roughly the Florida Keys) to a
maximum of 1.015540 (+1.55%, also at 24.0N, in the other axis) across CONUS
latitudes, with scale factor exactly 1.0 at the two standard parallels
(29.5N, 45.5N) and smallest distortion near them. In practical terms: a
straight-line distance measured directly in EPSG:5070 metres between two
CONUS points can read up to roughly 1.5-1.6% off the true geodesic distance,
worst for point pairs near the latitude extremes of CONUS and smallest near
29.5N/45.5N. A phase whose use case needs a tighter, pair-specific bound
should compare `geodesic_distance_km` against `planar_distance_km` for its
own actual point pairs rather than relying on this general figure alone.
"""

from __future__ import annotations

import numpy as np
from numpy.typing import ArrayLike
from pyproj import Geod

# GRS80 is the reference ellipsoid NAD83 (and therefore EPSG:5070 and the
# EPSG:4326-equivalent lon/lat this module expects) is defined against.
_GEOD = Geod(ellps="GRS80")


def geodesic_distance_km(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    """Exact ellipsoidal (geodesic) distance between two EPSG:4326 points, km."""
    _, _, distance_m = _GEOD.inv(lon1, lat1, lon2, lat2)
    return float(distance_m) / 1000.0


def geodesic_distance_km_array(lon1: ArrayLike, lat1: ArrayLike, lon2: ArrayLike, lat2: ArrayLike) -> np.ndarray:
    """Vectorized geodesic distance, km, for equal-shaped array-likes of
    EPSG:4326 coordinates (one `pyproj.Geod.inv` call for the whole batch --
    no per-pair Python loop).
    """
    _, _, distance_m = _GEOD.inv(
        np.asarray(lon1, dtype=float),
        np.asarray(lat1, dtype=float),
        np.asarray(lon2, dtype=float),
        np.asarray(lat2, dtype=float),
    )
    return np.asarray(distance_m, dtype=float) / 1000.0


def planar_distance_km(x1_m: float, y1_m: float, x2_m: float, y2_m: float) -> float:
    """Straight-line distance between two EPSG:5070 points, km.

    Subject to this module's documented Albers scale-error bound (up to
    roughly +/-1.5-1.6% across CONUS latitudes); prefer
    `geodesic_distance_km` wherever that error bound matters more than speed.
    """
    return float(np.hypot(x2_m - x1_m, y2_m - y1_m)) / 1000.0


def planar_distance_km_array(x1_m: ArrayLike, y1_m: ArrayLike, x2_m: ArrayLike, y2_m: ArrayLike) -> np.ndarray:
    """Vectorized straight-line EPSG:5070 distance, km. Same scale-error bound as `planar_distance_km`."""
    x1_m = np.asarray(x1_m, dtype=float)
    y1_m = np.asarray(y1_m, dtype=float)
    x2_m = np.asarray(x2_m, dtype=float)
    y2_m = np.asarray(y2_m, dtype=float)
    return np.hypot(x2_m - x1_m, y2_m - y1_m) / 1000.0


__all__ = [
    "geodesic_distance_km",
    "geodesic_distance_km_array",
    "planar_distance_km",
    "planar_distance_km_array",
]
