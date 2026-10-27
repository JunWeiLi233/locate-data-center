"""Search-scope preview: the cached cohort's refined windows as EPSG:4326 outlines."""
from __future__ import annotations

import json

import pyarrow as pa
import pyarrow.parquet as pq

from frontend.server.coverage import cached_window_coverage

DEFINITION = "conus-epsg5070-ox-2500000-oy3400000-s50000m-v1"


def cohort(folder, grid_ids, rows, cols, definition=DEFINITION, catalog=None):
    folder.mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.table({"grid_id": grid_ids, "grid_definition_id": [definition] * len(grid_ids), "row": rows, "col": cols}),
                   folder / "refinement_windows.parquet")
    if catalog is not None:
        (folder / "regional_catalog.json").write_text(json.dumps(catalog), encoding="utf-8")
    return folder


def test_windows_become_closed_lonlat_rings_around_the_recorded_window_centroid(tmp_path):
    # Row 7, column 8 is the Grays Harbor, WA window; the model recorded its centroid at 47.4723 N, 123.7463 W.
    folder = cohort(tmp_path / "cohort", ["g50000m-r0007-c0008", "g50000m-r0009-c0091"], [7, 9], [8, 91],
                    catalog={"cell_size_m": 1000, "refined_cells": 5000, "shortlisted_parent_cells": 690})
    result = cached_window_coverage(folder, "RUN")
    assert result["run_id"] == "RUN" and result["refined_windows"] == 2 and result["window_size_m"] == 50000
    assert (result["cell_size_m"], result["refined_cells"], result["shortlisted_windows"]) == (1000, 5000, 690)
    features = result["windows"]["features"]
    assert [feature["properties"]["grid_id"] for feature in features] == ["g50000m-r0007-c0008", "g50000m-r0009-c0091"]
    ring = features[0]["geometry"]["coordinates"][0]
    assert ring[0] == ring[-1] and len(ring) == 17
    lons, lats = [point[0] for point in ring], [point[1] for point in ring]
    assert min(lons) < -123.7463 < max(lons) and min(lats) < 47.4723 < max(lats)
    # 50 km is about 0.45 degrees of latitude; this far west the Albers square sits rotated, so its extent is larger.
    assert 0.45 < max(lats) - min(lats) < 0.65


def test_missing_windows_or_an_unknown_grid_give_no_preview(tmp_path):
    assert cached_window_coverage(tmp_path / "absent", "RUN") is None
    folder = cohort(tmp_path / "other", ["g1"], [1], [1], definition="wgs84-degree-grid")
    assert cached_window_coverage(folder, "RUN") is None


def test_counts_absent_from_the_catalog_stay_unknown(tmp_path):
    result = cached_window_coverage(cohort(tmp_path / "cohort", ["g50000m-r0007-c0008"], [7], [8]), None)
    assert result["refined_windows"] == 1
    assert (result["cell_size_m"], result["refined_cells"], result["shortlisted_windows"]) == (None, None, None)
