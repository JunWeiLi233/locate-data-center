"""External validation inventory: IM3 Open Source Data Center Atlas (PNNL), never a model input.

Source: Mongird, K., Thurber, T., Vernon, C., Burleyson, C., Akdemir, K. Z., & Rice, J. (2026). IM3 Open
Source Data Center Atlas (v2026.02.09) [Data set]. MSD-LIVE Data Repository. doi:10.57931/3017294. The
licence is ODbL, and the data are derived from OpenStreetMap.

MSD-LIVE serves files only after a login, so that route is not used. The same database is published in the
publisher's own repository, ``IMMM-SFA/datacenter-atlas``. Commit ``74ab37d5b9d200400a01639f9ffc3c3a8b716314``
(2026-02-12) is titled "Updated existing dc db, citation, doi link". The URL is pinned to that commit and the
file to its SHA-256. A changed publisher payload therefore fails rather than silently replacing the
inventory.

The inventory is crowd-sourced and incomplete. ``lat``/``lon`` are IM3 centroids of OSM points, buildings
or campuses. A campus and its buildings can both appear. Rows that straddle counties share an OSM id; they
are merged here and every county is kept. IM3 provides no city field, so city stays null rather than being
inferred.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pyogrio

from dc_locator.geography.sources.ingestion import download_public, file_digest

from .config import FacilitySource

NON_CONUS_STATES = frozenset({"AK", "HI", "PR", "VI", "GU", "AS", "MP"})
CONUS_BOUNDS = (-125.0, 24.3, -66.8, 49.5)  # lon_min, lat_min, lon_max, lat_max: coarse sanity box only
SOURCE_NAME = "IM3 Open Source Data Center Atlas (PNNL)"


def acquire(source: FacilitySource, root: Path) -> Path:
    """Download the pinned public file once into ``data/raw``; reuse it only after checksum verification."""
    raw_dir = root / "data" / "raw"
    path = (root / source.path).resolve()
    return download_public(source.url, path, raw_dir=raw_dir, source_id=source.source_id, version=source.version,
                           license_note=source.license, expected_bytes=source.expected_bytes,
                           expected_sha256=source.expected_sha256)


def download_record(source: FacilitySource, root: Path) -> dict:
    """The verified manifest entry for the cached file (retrieval time, bytes, checksum, URL)."""
    import json

    path = (root / source.path).resolve()
    if not path.is_file():
        raise FileNotFoundError(f"Facility inventory missing: {path}. Run acquisition first; nothing is fabricated.")
    digest = file_digest(path)
    if digest != source.expected_sha256 or path.stat().st_size != source.expected_bytes:
        raise ValueError("Cached facility inventory does not match its pinned checksum; inspect before use")
    log = path.parent / "download_log.json"
    entries = json.loads(log.read_text(encoding="utf-8")) if log.is_file() else []
    entry = next((item for item in entries if Path(item.get("path", "")).resolve() == path and item.get("sha256") == digest), None)
    return {"path": path.relative_to(root.resolve()).as_posix() if path.is_relative_to(root.resolve()) else str(path),
            "sha256": digest, "bytes": path.stat().st_size, "url": source.url,
            "retrieved_at_utc": entry.get("retrieved_at_utc") if entry else None,
            "retrieved_at_missing_reason": None if entry else "No acquisition log entry; checksum verified against the pinned value"}


def _text(value) -> str | None:
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return None
    text = " ".join(str(value).split())
    return text or None


def load_inventory(source: FacilitySource, root: Path, record: dict, data_mode: str = "real") -> tuple[pd.DataFrame, dict]:
    """Return (CONUS facility records, inventory summary). Missing fields stay null with reasons."""
    path = (root / source.path).resolve()
    frames = []
    for layer in source.layers:
        frame = pyogrio.read_dataframe(path, layer=layer, read_geometry=False)
        frame["source_layer"] = layer
        frames.append(frame)
    raw = pd.concat(frames, ignore_index=True)
    required = {"id", "state", "state_abb", "state_id", "county", "county_id", "operator", "name", "sqft", "lat", "lon", "type"}
    if not required <= set(raw.columns):
        raise ValueError(f"IM3 inventory lacks expected fields: {sorted(required - set(raw.columns))}")
    raw["id"] = raw["id"].map(_text)
    if raw["id"].isna().any():
        raise ValueError("Every IM3 record must carry an OSM-derived identifier")
    raw["county_geoid"] = raw.state_id.map(_text).str.zfill(2) + raw.county_id.map(_text).str.zfill(3)
    rows, conflicts = [], 0
    for identifier, group in raw.sort_values(["id", "county_geoid"], kind="stable").groupby("id", sort=True):
        first = group.iloc[0]
        for field in ("lat", "lon", "name", "operator", "type", "state_abb"):
            if group[field].map(lambda value: _text(value) if not isinstance(value, float) else round(value, 9)).nunique(dropna=False) > 1:
                conflicts += 1
        rows.append({
            "facility_id": f"im3:{identifier}", "osm_id": identifier,
            "name": _text(first["name"]), "operator": _text(first["operator"]), "ref": _text(first.get("ref")),
            "city": None, "city_missing_reason": "IM3 atlas provides no city field; not inferred",
            "county": _text(first.county), "county_geoid": first.county_geoid,
            "counties_all": [_text(value) for value in group.county],
            "county_geoids_all": list(group.county_geoid),
            "state": _text(first.state), "state_abbr": _text(first.state_abb),
            "lat": float(first.lat), "lon": float(first.lon),
            "footprint_type": _text(first["type"]), "source_layer": first.source_layer,
            "footprint_sqft": float(first.sqft) if pd.notna(first.sqft) else None,
            "footprint_sqft_missing_reason": None if pd.notna(first.sqft) else "Point records have no footprint polygon",
        })
    facilities = pd.DataFrame(rows)
    excluded_state = facilities.state_abbr.isin(NON_CONUS_STATES)
    lon_min, lat_min, lon_max, lat_max = CONUS_BOUNDS
    outside = ~facilities.lon.between(lon_min, lon_max) | ~facilities.lat.between(lat_min, lat_max)
    nonfinite = ~np.isfinite(facilities.lat) | ~np.isfinite(facilities.lon)
    keep = ~(excluded_state | outside | nonfinite)
    conus = facilities.loc[keep].sort_values("facility_id").reset_index(drop=True)
    conus = conus.assign(source_id=source.source_id, source_name=SOURCE_NAME, source_version=source.version,
                         source_doi=source.doi, source_url=f"https://doi.org/{source.doi}", source_file_url=source.url,
                         source_sha256=record["sha256"], license=source.license, retrieved_at_utc=record["retrieved_at_utc"],
                         coordinate_basis="IM3 centroid of the OSM point, building or campus geometry (EPSG:4326)",
                         status="observed", confidence="low", data_mode=data_mode,
                         role="external_validation_only")
    summary = {
        "source_id": source.source_id, "source_name": SOURCE_NAME, "version": source.version, "doi": source.doi,
        "license": source.license, "file": record,
        "layers": {layer: int((raw.source_layer == layer).sum()) for layer in source.layers},
        "raw_rows": int(len(raw)), "unique_osm_ids": int(raw["id"].nunique()),
        "county_straddle_rows_merged": int(len(raw) - raw["id"].nunique()),
        "attribute_conflicts_within_id": int(conflicts),
        "excluded_non_conus": int((excluded_state & ~nonfinite).sum()),
        "excluded_outside_conus_bounds": int((outside & ~excluded_state & ~nonfinite).sum()),
        "excluded_nonfinite": int(nonfinite.sum()),
        "conus_facility_records": int(len(conus)),
        "with_operator": int(conus.operator.notna().sum()), "with_name": int(conus.name.notna().sum()),
        "footprint_types": conus.footprint_type.value_counts().sort_index().to_dict(),
        "states": int(conus.state_abbr.nunique()),
        "limitations": [
            "Crowd-sourced OpenStreetMap coverage; facilities not mapped in OSM are absent, and absence is not evidence of unsuitability.",
            "Campus and building footprints can overlap and are kept as separate records, as the publisher does.",
            "Records are facilities of every size, from small colocation rooms to hyperscale campuses; capacity is not provided.",
            "Coordinates are footprint centroids, not parcel boundaries; city is not provided.",
            "Operating status and date are not provided; records reflect the OSM snapshot behind v2026.02.09.",
        ],
    }
    return conus, summary
