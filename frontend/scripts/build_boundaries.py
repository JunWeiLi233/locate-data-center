"""Acquire and build Census context boundaries, separately from model inputs."""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import geopandas as gpd
import numpy as np
import requests
import shapely
from pyproj import Transformer
from shapely.geometry import mapping, shape
from shapely.ops import transform

ROOT = Path(__file__).resolve().parents[2]
CACHE = ROOT / "data/raw/census_frontend_boundary"
OUTPUT = ROOT / "frontend/public/map"
SOURCES = {
    "administrative": "https://www2.census.gov/geo/tiger/TIGER2025/STATE/tl_2025_us_state.zip",
    "cartographic": "https://www2.census.gov/geo/tiger/GENZ2025/shp/cb_2025_us_state_500k.zip",
}
EXCLUDE = {"60", "66", "69", "72", "78"}
MAX_DOWNLOAD_BYTES = 25_000_000
TO_METRIC = Transformer.from_crs(4326, 3857, always_xy=True).transform
FROM_METRIC = Transformer.from_crs(3857, 4326, always_xy=True).transform


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    def compact(item):
        if isinstance(item, float):
            return round(item, 7)
        if isinstance(item, dict):
            return {k: compact(v) for k, v in item.items()}
        if isinstance(item, (list, tuple)):
            return [compact(v) for v in item]
        return item
    value = compact(value)
    path.write_text(json.dumps(value, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


def acquire():
    CACHE.mkdir(parents=True, exist_ok=True)
    manifest_path = CACHE / "download_manifest.json"
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
    raw_bytes = sum(p.stat().st_size for p in (ROOT / "data/raw").rglob("*") if p.is_file())
    if raw_bytes + MAX_DOWNLOAD_BYTES > 60_000_000_000:
        raise ValueError("Boundary download would exceed the project raw-data budget")
    session = requests.Session()
    session.headers["User-Agent"] = "dc_locator/0.1 (Census frontend boundary preparation)"
    for role, url in SOURCES.items():
        path = CACHE / url.rsplit("/", 1)[-1]
        if path.exists():
            record = manifest.get(role)
            if not record or digest(path) != record["sha256"] or path.stat().st_size != record["bytes"]:
                raise ValueError(f"Existing source is unverified: {path.name}")
            continue
        with session.get(url, stream=True, timeout=(15, 120)) as response:
            response.raise_for_status()
            size = int(response.headers.get("Content-Length", "0"))
            if size > MAX_DOWNLOAD_BYTES:
                raise ValueError("Source exceeds the bounded download policy")
            temporary = ROOT / ".pytest-work/us-boundary" / (path.name + ".part")
            temporary.parent.mkdir(parents=True, exist_ok=True)
            try:
                total = 0
                with temporary.open("wb") as file:
                    for chunk in response.iter_content(1024 * 256):
                        total += len(chunk)
                        if total > MAX_DOWNLOAD_BYTES:
                            raise ValueError("Download exceeds advertised bounded size")
                        file.write(chunk)
                if size and size != total:
                    raise ValueError("Incomplete source download")
                temporary.replace(path)
            finally:
                temporary.unlink(missing_ok=True)
            manifest[role] = {"url": url, "path": path.relative_to(ROOT).as_posix(),
                "bytes": total, "sha256": digest(path), "vintage": 2025,
                "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
                "last_modified": response.headers.get("Last-Modified"),
                "license": "U.S. Government work; public domain", "access": "Public HTTP; no authentication"}
            write_json(manifest_path, manifest)
    return manifest


def load(role, manifest):
    path = ROOT / manifest[role]["path"]
    if digest(path) != manifest[role]["sha256"]:
        raise ValueError("Boundary source checksum mismatch")
    frame = gpd.read_file(path)
    frame = frame[~frame.STATEFP.isin(EXCLUDE)].sort_values("STATEFP").to_crs(4326)
    if len(frame) != 51 or frame.STATEFP.nunique() != 51 or not frame.geometry.is_valid.all():
        raise ValueError("Expected 50 states and DC, all with valid original geometries")
    return frame


def feature(geometry, properties, identifier):
    return {"type": "Feature", "id": identifier, "properties": properties,
        "geometry": mapping(shapely.orient_polygons(geometry))}


def simplify_coverage(geometries, maximum_error):
    projected = [transform(TO_METRIC, geometry) for geometry in geometries]
    if not shapely.coverage_is_valid(projected):
        raise ValueError("Original Census polygons do not form a valid shared-edge coverage")
    tolerance = maximum_error / 2
    for _ in range(12):
        simplified = shapely.coverage_simplify(projected, tolerance)
        errors = [displacement_bound(original.boundary, result.boundary)
            for original, result in zip(projected, simplified)]
        if max(errors) <= maximum_error and all(shapely.is_valid(simplified)) and shapely.coverage_is_valid(simplified):
            return [transform(FROM_METRIC, g) for g in simplified], errors, tolerance
        tolerance /= 2
    raise ValueError("No coverage simplification satisfies the measured error budget")


def displacement_bound(first, second, spacing=50):
    """Upper-bound continuous symmetric distance using indexed segment distances.

    Sampling both boundaries at <= spacing gives a conservative spacing/2 bound
    between samples because distance to a closed set is 1-Lipschitz. The index
    computes exact point-to-segment distances, not nearest-vertex distances.
    """
    def directed(source, target):
        lines = list(shapely.get_parts(target))
        segments = []
        for line in lines:
            points = shapely.get_coordinates(line)
            if len(points) > 1:
                segments.append(np.stack((points[:-1], points[1:]), axis=1))
        tree = shapely.STRtree(shapely.linestrings(np.concatenate(segments)))
        points = shapely.points(shapely.get_coordinates(shapely.segmentize(source, spacing)))
        _, distances = tree.query_nearest(points, return_distance=True, all_matches=False)
        return float(max(distances)) + spacing / 2
    return max(directed(first, second), directed(second, first))


def build(manifest):
    admin = load("administrative", manifest)
    land = load("cartographic", manifest)
    geometries = list(admin.geometry)
    overview, errors, tolerance = simplify_coverage(geometries, 500)
    land_overview, land_errors, land_tolerance = simplify_coverage(list(land.geometry), 100)
    country = shapely.coverage_union_all(geometries)
    overview_country = shapely.coverage_union_all(overview)
    features = []
    national_features = []
    detail_records = []
    for index, (_, row) in enumerate(admin.iterrows()):
        original = row.geometry
        parts = list(original.geoms) if original.geom_type == "MultiPolygon" else [original]
        label = max(parts, key=lambda p: p.area).representative_point()
        props = {"name": row.NAME, "abbreviation": row.STUSPS, "fips": row.STATEFP,
            "label_lon": label.x, "label_lat": label.y,
            "detail_bounds": [list(part.bounds) for part in parts]}
        features.append(feature(overview[index], props, row.STATEFP))
        overview_border = overview[index].boundary.intersection(overview_country.boundary)
        if not overview_border.is_empty:
            national_features.append(feature(overview_border, {"fips": row.STATEFP}, "national-" + row.STATEFP))
        national = original.boundary.intersection(country.boundary)
        details = [feature(original, {"kind": "state", "fips": row.STATEFP}, row.STATEFP)]
        if not national.is_empty:
            details.append(feature(national, {"kind": "national", "fips": row.STATEFP}, "national-" + row.STATEFP))
        target = OUTPUT / "detail" / (row.STATEFP + ".geojson")
        write_json(target, {"type": "FeatureCollection", "features": details})
        detail_records.append({"fips": row.STATEFP, "bytes": target.stat().st_size, "sha256": digest(target),
            "original_coordinate_count": int(shapely.get_num_coordinates(original)), "additional_simplification_m": 0})
    write_json(OUTPUT / "states.geojson", {"type": "FeatureCollection", "features": features})
    write_json(OUTPUT / "national.geojson", {"type": "FeatureCollection", "features": national_features})
    write_json(OUTPUT / "land.geojson", {"type": "FeatureCollection", "features": [feature(shapely.coverage_union_all(land_overview), {}, "land")]})
    qa = {"schema_version": 1, "vintage": 2025, "source_records": manifest,
        "state_count": 51, "source_crs": str(gpd.read_file(ROOT / manifest['administrative']['path']).crs),
        "display_crs": "EPSG:4326", "measurement_crs": "EPSG:3857",
        "overview_boundary_displacement_upper_bound_projected_m": max(errors),
        "overview_error_budget_projected_m": 500, "coverage_simplification_tolerance_projected_m": tolerance,
        "land_boundary_displacement_upper_bound_projected_m": max(land_errors),
        "distance_validation": "Exact indexed point-to-segment distances sampled every <=50 m in both directions, plus 25 m Lipschitz bound; serialized output is revalidated separately",
        "land_simplification_tolerance_projected_m": land_tolerance,
        "overview_shared_edge_coverage_valid": True, "detail_additional_simplification_m": 0,
        "original_ground_positional_accuracy": "Not certified by this application",
        "detail": detail_records}
    write_json(OUTPUT / "boundary-manifest.json", qa)
    print(json.dumps({"state_count": 51, "max_overview_error_projected_m": max(errors),
        "overview_bytes": (OUTPUT / 'states.geojson').stat().st_size,
        "detail_bytes": sum(r['bytes'] for r in detail_records)}, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--download-only", action="store_true")
    args = parser.parse_args()
    records = acquire()
    if not args.download_only:
        build(records)
