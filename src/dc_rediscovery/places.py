"""County/state presentation labels for candidates from cached Census cartographic boundaries.

The labels are presentation and robustness keys only. They are never suitability evidence. A cell centre
that falls outside every generalized county polygon, for example on a coastline, takes the nearest county
within the declared distance and is marked as such. Otherwise its label stays null.
"""
from __future__ import annotations

import json
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd

from dc_locator.geography.sources.ingestion import file_digest


def load_counties(root: Path, path: str, manifest: str) -> tuple[gpd.GeoDataFrame, dict]:
    archive = (root / path).resolve()
    entries = json.loads((root / manifest).read_text(encoding="utf-8"))
    entry = entries.get(archive.name) if isinstance(entries, dict) else None
    if entry is None:
        raise ValueError(f"County boundary file {archive.name} is not registered in {manifest}")
    digest = file_digest(archive)
    if digest != entry["sha256"] or archive.stat().st_size != entry["bytes"]:
        raise ValueError("County boundary file does not match its download manifest")
    counties = gpd.read_file(archive)[["GEOID", "NAME", "NAMELSAD", "STUSPS", "STATE_NAME", "geometry"]]
    record = {"path": path, "sha256": digest, "bytes": entry["bytes"], "url": entry["url"], "vintage": entry.get("vintage"),
              "retrieved_at_utc": entry.get("retrieved_at_utc"), "license": entry.get("license"),
              "scale": "1:500,000 generalized cartographic boundary"}
    return counties, record


def label_points(points: pd.DataFrame, counties: gpd.GeoDataFrame, nearest_max_km: float) -> pd.DataFrame:
    """county_geoid, county_name, state_abbr, state_name, place_label and label_basis for each point."""
    frame = gpd.GeoDataFrame(points[["grid_id"]].copy(), geometry=gpd.points_from_xy(points.lon, points.lat), crs="EPSG:4326")
    frame = frame.to_crs("EPSG:5070")
    polygons = counties.to_crs("EPSG:5070")
    within = gpd.sjoin(frame, polygons, how="left", predicate="within").sort_values(["grid_id", "GEOID"])
    within = within[~within.index.duplicated(keep="first")].sort_index()
    rows = []
    missing = within.GEOID.isna()
    nearest = None
    if missing.any() and nearest_max_km > 0:
        nearest = gpd.sjoin_nearest(frame.loc[missing], polygons, how="left", max_distance=nearest_max_km * 1000.0, distance_col="_distance_m")
        nearest = nearest[~nearest.index.duplicated(keep="first")]
    for index, record in within.iterrows():
        basis = "cell_centre_within_county"
        source = record
        if pd.isna(record.GEOID):
            if nearest is not None and index in nearest.index and pd.notna(nearest.at[index, "GEOID"]):
                source = nearest.loc[index]
                basis = f"nearest_county_within_{nearest_max_km:g}km ({float(source['_distance_m']) / 1000:.2f} km)"
            else:
                rows.append({"county_geoid": None, "county_name": None, "state_abbr": None, "state_name": None, "place_label": None,
                             "place_label_basis": "cell centre outside generalized county polygons"})
                continue
        rows.append({"county_geoid": str(source.GEOID), "county_name": str(source.NAMELSAD), "state_abbr": str(source.STUSPS),
                     "state_name": str(source.STATE_NAME), "place_label": f"{source.NAMELSAD}, {source.STUSPS}",
                     "place_label_basis": basis})
    return pd.DataFrame(rows, index=points.index)
