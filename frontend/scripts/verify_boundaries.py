"""Validate serialized frontend boundaries against acquired authoritative sources."""
from __future__ import annotations

import gzip
import hashlib
import json
from pathlib import Path

import numpy as np
import shapely
from shapely.geometry import Point, shape
from shapely.ops import transform

from build_boundaries import ROOT, OUTPUT, TO_METRIC, displacement_bound, load

ON_LINE_DEGREES = 1e-6  # serialized lines must lie on their source edges (7-decimal output)
TILE_EDGE_DEGREES = 1e-9


def read(path: Path):
    data = path.read_bytes()
    return json.loads(gzip.decompress(data) if path.suffix == ".gz" else data)


def within(geometry, reference, tolerance) -> bool:
    """Every vertex of ``geometry`` lies within ``tolerance`` of ``reference`` (prepared, vectorized).
    Serialized lines and tiles reuse their source vertices, so a vertex test suffices."""
    shapely.prepare(reference)
    return bool(shapely.dwithin(reference, shapely.points(shapely.get_coordinates(geometry)), tolerance).all())


def lies_on(line, edge, tolerance=ON_LINE_DEGREES) -> bool:
    return within(line, edge, tolerance)


def finite(geometry) -> bool:
    coordinates = shapely.get_coordinates(geometry)
    return bool(np.isfinite(coordinates).all() and (abs(coordinates[:, 0]) <= 180).all() and (abs(coordinates[:, 1]) <= 90).all())


def main():
    manifest = read(OUTPUT / "boundary-manifest.json")
    administrative = load("administrative", manifest["source_records"])
    cartographic = load("cartographic", manifest["source_records"])
    overview = read(OUTPUT / "states.geojson")
    by_id = {f["id"]: f for f in overview["features"]}
    expected = set(administrative.STATEFP)
    assert set(by_id) == expected and len(by_id) == 51, "Missing state or DC"
    sources = dict(zip(administrative.STATEFP, administrative.geometry))
    original_country = shapely.coverage_union_all(list(administrative.geometry))
    projected_overview, errors = [], []
    detail_lengths = {"state": 0.0, "national": 0.0}
    for code, source in sources.items():
        context = by_id[code]
        geometry = shape(context["geometry"])
        assert geometry.is_valid and not geometry.is_empty
        assert source.covers(Point(context["properties"]["label_lon"], context["properties"]["label_lat"]))
        projected = transform(TO_METRIC, geometry)
        projected_overview.append(projected)
        error = displacement_bound(transform(TO_METRIC, source).boundary, projected.boundary)
        assert error <= 500, f"Overview exceeds its error budget: {code}"
        errors.append(error)
        # Detailed borders: shared state edges and international lines, never seaward limits.
        path = OUTPUT / "detail" / f"{code}.geojson"
        record = next(item for item in manifest["detail"] if item["fips"] == code)
        assert hashlib.sha256(path.read_bytes()).hexdigest() == record["sha256"], f"Detail hash mismatch: {code}"
        neighbours = shapely.union_all([other.boundary for other_code, other in sources.items()
                                        if other_code != code and other.intersects(source)]) if len(sources) > 1 else None
        for feature in read(path)["features"]:
            line = shape(feature["geometry"])
            kind = feature["properties"]["kind"]
            assert feature["properties"]["fips"] == code and kind in detail_lengths and finite(line)
            assert lies_on(line, source.boundary), f"Detail {kind} line leaves its TIGER state boundary: {code}"
            if kind == "state":
                assert neighbours is not None and lies_on(line, neighbours), f"State border is not shared with a neighbour: {code}"
            else:
                assert lies_on(line, original_country.boundary), f"National line is not on the U.S. outline: {code}"
            detail_lengths[kind] += line.length
    assert shapely.coverage_is_valid(projected_overview), "Shared borders are inconsistent"
    overview_geometries = {f["id"]: shape(f["geometry"]) for f in overview["features"]}
    country = shapely.coverage_union_all(list(overview_geometries.values()))
    national = read(OUTPUT / "national.geojson")
    published = shapely.union_all([shape(f["geometry"]) for f in national["features"]])
    assert lies_on(published, country.boundary), "Overview national line includes interior state lines"
    assert published.length < country.boundary.length, "Seaward limits were not removed from the national line"
    borders = read(OUTPUT / "borders.geojson")
    pairs = set()
    for feature in borders["features"]:
        a, b = feature["properties"]["fips_a"], feature["properties"]["fips_b"]
        assert a < b and (a, b) not in pairs, "Each state pair appears once, ordered"
        pairs.add((a, b))
        line = shape(feature["geometry"])
        assert lies_on(line, overview_geometries[a].boundary) and lies_on(line, overview_geometries[b].boundary), f"Border {a}-{b} is not shared"
    # Generalized backdrop, cut by 1-degree tile, still within its additional error budget.
    pieces = read(OUTPUT / "land.geojson")["features"]
    land = shapely.union_all([shape(f["geometry"]) for f in pieces])
    assert land.is_valid and all("tile" in f["properties"] for f in pieces)
    original_land = shapely.coverage_union_all(list(cartographic.geometry))
    land_error = displacement_bound(transform(TO_METRIC, original_land).boundary, transform(TO_METRIC, land).boundary)
    assert land_error <= 100, "Cartographic backdrop exceeds its additional error budget"
    shoreline = shapely.union_all([shape(f["geometry"]) for f in read(OUTPUT / "shoreline.geojson")["features"]])
    assert lies_on(shoreline, land.boundary), "Overview shoreline leaves the backdrop outline"
    # Detailed land tiles.
    land_detail = manifest["land_detail"]
    index = read(OUTPUT / "land" / "index.json")
    records = {r["tile"]: r for r in land_detail["tiles"]}
    files = {p.name.removesuffix(".geojson.gz") for p in (OUTPUT / "land").glob("*.geojson.gz")}
    assert set(index["tiles"]) == set(records) == files, "Land tile index, manifest and files disagree"
    # Land tiles are simplified by <= 0.00005 degrees and snapped to a 1e-5 grid.
    shapely.prepare(original_country)
    tile_bytes = 0
    for identifier, record in sorted(records.items()):
        path = OUTPUT / "land" / f"{identifier}.geojson.gz"
        assert hashlib.sha256(path.read_bytes()).hexdigest() == record["sha256"], f"Land tile hash mismatch: {identifier}"
        tile_bytes += path.stat().st_size
        box = shapely.box(*index["tiles"][identifier]).buffer(TILE_EDGE_DEGREES)
        for feature in read(path)["features"]:
            geometry = shape(feature["geometry"])
            assert feature["properties"]["tile"] == identifier and finite(geometry), identifier
            assert box.covers(geometry), f"Land tile geometry leaves its tile: {identifier}"
            if feature["properties"]["kind"] == "land":
                assert geometry.is_valid and not geometry.is_empty, f"Invalid land polygon: {identifier}"
                assert within(geometry, original_country, 6e-5), f"Detailed land extends beyond TIGER states: {identifier}"
    # Context outside the United States: plain fill that never covers U.S. territory.
    foreign_record = manifest["foreign_context"]
    foreign_path = OUTPUT / "foreign.geojson"
    assert hashlib.sha256(foreign_path.read_bytes()).hexdigest() == foreign_record["sha256"], "Foreign context hash mismatch"
    foreign = {f["properties"]["kind"]: shape(f["geometry"]) for f in read(foreign_path)["features"]}
    assert set(foreign) <= {"land", "border"} and foreign["land"].is_valid and finite(foreign["land"])
    foreign_overlap = foreign["land"].intersection(original_country).area
    assert foreign_overlap < 1e-6, "Foreign context covers U.S. territory"
    projected_m_per_pixel_at_switch = 40075016.68557849 / (512 * 2**6)
    paths = [OUTPUT / n for n in ("states.geojson", "national.geojson", "borders.geojson", "land.geojson", "shoreline.geojson", "foreign.geojson")]
    result = {"passed": True, "source_vintage": 2025, "states_and_dc": 51,
        "overview_shared_edge_coverage_valid": True,
        "serialized_overview_displacement_upper_bound_projected_m": max(errors),
        "serialized_land_displacement_upper_bound_projected_m": land_error,
        "detail_border_lines_on_tiger_state_boundaries": True,
        "detail_line_length_degrees": detail_lengths,
        "national_line": "International borders only; seaward limits removed (published length below the full outline)",
        "overview_geometry_error_upper_bound_screen_pixels_at_zoom_6": max(errors) / projected_m_per_pixel_at_switch,
        "land_tiles": len(records), "land_tile_bytes": tile_bytes,
        "land_tiles_within_tiger_states_degrees": 6e-5,
        "blocked_areawater_county_files": land_detail.get("blocked_county_files", {}),
        "block_water_substitutes": land_detail.get("block_water_substitutes", {}),
        "foreign_context_us_overlap_square_degrees": foreign_overlap,
        "source_ground_positional_accuracy": "Not certified; coordinate and display precision do not establish ground accuracy",
        "artifact_hashes": {p.relative_to(OUTPUT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}}
    (OUTPUT / "boundary-qa.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in result.items() if k != "artifact_hashes"}, indent=2))


if __name__ == "__main__":
    main()
