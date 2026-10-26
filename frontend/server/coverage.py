"""Outlines of the fixed cached cohort's refined windows, for the start screen's search-scope preview.

Presentation only: the squares are rebuilt from the cohort's own refinement_windows.parquet grid IDs and
projected from EPSG:5070 to EPSG:4326 for the map. No model value, screening result or rank is computed here.
"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

import pyarrow.parquet as pq

GRID_DEFINITION = re.compile(r"^conus-epsg5070-ox(-?\d+)-oy(-?\d+)-s(\d+)m-v\d+$")
# Straight Albers edges curve slightly in longitude/latitude, so each side keeps intermediate points.
EDGE_SEGMENTS = 4
# About 11 m; the windows are 50 km squares drawn for orientation, not measured coverage.
DECIMALS = 4


def cached_window_coverage(folder: Path, run_id: str | None) -> dict | None:
    """Window outlines and counts of a cached cohort, or None when its windows cannot be read."""
    path = folder / "refinement_windows.parquet"
    try:
        stat = path.stat()
    except OSError:
        return None
    return _coverage(str(path), stat.st_mtime_ns, stat.st_size, str(folder / "regional_catalog.json"), run_id)


@lru_cache(maxsize=4)
def _coverage(path: str, _mtime: int, _size: int, catalog_path: str, run_id: str | None) -> dict | None:
    try:
        records = pq.read_table(path, columns=["grid_id", "grid_definition_id", "row", "col"]).to_pylist()
    except (OSError, ValueError, KeyError):
        return None
    if not records:
        return None
    from pyproj import Transformer

    to_lonlat = Transformer.from_crs("EPSG:5070", "EPSG:4326", always_xy=True)
    features, sizes = [], set()
    for record in records:
        match = GRID_DEFINITION.match(record.get("grid_definition_id") or "")
        if not match or not isinstance(record.get("row"), int) or not isinstance(record.get("col"), int):
            return None
        origin_x, origin_y, size = (int(value) for value in match.groups())
        west, north = origin_x + record["col"] * size, origin_y - record["row"] * size
        corners = [(west, north - size), (west + size, north - size), (west + size, north), (west, north)]
        xs, ys = [], []
        for (x0, y0), (x1, y1) in zip(corners, corners[1:] + corners[:1]):
            for step in range(EDGE_SEGMENTS):
                xs.append(x0 + (x1 - x0) * step / EDGE_SEGMENTS)
                ys.append(y0 + (y1 - y0) * step / EDGE_SEGMENTS)
        lons, lats = to_lonlat.transform(xs, ys)
        ring = [[round(lon, DECIMALS), round(lat, DECIMALS)] for lon, lat in zip(lons, lats)]
        ring.append(ring[0])
        features.append({"type": "Feature", "properties": {"grid_id": record["grid_id"]},
                         "geometry": {"type": "Polygon", "coordinates": [ring]}})
        sizes.add(size)
    if len(sizes) != 1:
        return None
    try:
        catalog = json.loads(Path(catalog_path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        catalog = {}
    count = lambda key: catalog.get(key) if type(catalog.get(key)) is int else None
    return {"run_id": run_id, "window_size_m": sizes.pop(), "cell_size_m": count("cell_size_m"),
            "refined_windows": len(features), "refined_cells": count("refined_cells"),
            "shortlisted_windows": count("shortlisted_parent_cells"),
            "windows": {"type": "FeatureCollection", "features": features}}
