"""Detailed land, shoreline and border display assets from Census TIGER/Line 2025.

The generalized 1:500,000 backdrop has no city-scale water (Manhattan merges with
Brooklyn), and TIGER state polygons extend about 3 nautical miles offshore, so their
outer edge is not a coastline. This step adds, for zoomed-in display:

- ``land/<tile>.geojson`` (1-degree tiles, zoom >= 9): TIGER state land minus TIGER
  AREAWATER water bodies, dissolved across state lines, with its shoreline;
- ``land.geojson`` / ``shoreline.geojson``: the existing generalized backdrop split by
  the same tiles, so a loaded detail tile replaces exactly its generalized piece;
- ``borders.geojson`` and detail ``state`` lines: borders shared by two states (on land
  or through water), never seaward limits;
- ``national.geojson`` and detail ``national`` lines: the U.S. outline minus seaward
  limits along ocean and bay water, i.e. international borders.

Display context only; never a model input. Run after build_boundaries.py:
``.venv\\Scripts\\python.exe frontend/scripts/build_land_detail.py``
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import math
import re
import time
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import requests
import shapely
from pyproj import Transformer
from shapely.geometry import mapping, shape

ROOT = Path(__file__).resolve().parents[2]
CACHE = ROOT / "data/raw/census_frontend_boundary"
WATER_CACHE = CACHE / "areawater"
OUTPUT = ROOT / "frontend/public/map"
AREAWATER_INDEX = "https://www2.census.gov/geo/tiger/TIGER2025/AREAWATER/"
# Generalized county outlines, used only to withhold detailed land around refused county files.
COUNTY_OUTLINES = "https://www2.census.gov/geo/tiger/GENZ2025/shp/cb_2025_us_county_500k.zip"
# Official per-state TIGER/Line 2025 geodatabases: all-water Census blocks (ALAND = 0) stand in
# for a county AREAWATER file that Census refused to serve.
STATE_GDB = "https://www2.census.gov/geo/tiger/TGRGDB25/tlgdb_2025_a_{fips}_{abbreviation}.gdb.zip"
GDB_CACHE = WATER_CACHE / "state_gdb"
MAX_STATE_GDB_BYTES = 400_000_000
EXCLUDE = {"60", "66", "69", "72", "78"}
# City-scale land/water covers the contiguous model domain, DC and Hawaii. Alaska keeps the
# generalized backdrop (its coast and lakes would dominate the asset size).
WITHOUT_LAND_DETAIL = {"02"}
PROJECT_RAW_BUDGET = 60_000_000_000
MAX_COUNTY_BYTES = 60_000_000
SEAWARD_WATER = {"H2051", "H2053"}  # bay/estuary/gulf/sound, ocean/sea
RIVERS = {"H3010"}
OCEAN = {"H2053"}  # shared state borders are not drawn across open ocean
# Minimum display areas (EPSG:6933): rivers keep narrow channels continuous; bays and ocean
# drop marsh coves below ~140 x 140 m; lakes, ponds, reservoirs, canals and swamps from 1 km2.
MINIMUM_AREA_M2 = {"river": 1_000, "seaward": 20_000, "other": 1_000_000}
TILE_DEGREES = 1
TILE_PAD_DEGREES = 0.01
SIMPLIFY_DEGREES = 0.00005  # ~5 m; below one screen pixel up to zoom 14
TILE_DIGITS = 5  # ~1 m coordinate precision in land tiles
SEAWARD_TOLERANCE_DEGREES = 0.0003  # ~30 m: detailed outline vs seaward water edge
OVERVIEW_SEAWARD_TOLERANCE_DEGREES = 0.008  # overview borders are simplified by <= 500 m
EQUAL_AREA = Transformer.from_crs(4326, 6933, always_xy=True)  # thresholds only
# Countries outside the 50 states and DC: borders and a plain fill only, no geographic detail.
NATURAL_EARTH = CACHE / "natural_earth"
FOREIGN_SIMPLIFY_DEGREES = {"near": 0.003, "far": 0.02}  # ~300 m near the U.S., ~2 km elsewhere
# Polygon parts seen at regional zoom next to the contiguous United States keep finer detail.
FOREIGN_NEAR_BOX = (-170.0, 5.0, -50.0, 56.0)
FOREIGN_US_GAP_DEGREES = 0.0005  # foreign fill stops ~50 m short of the detailed U.S. boundary
FOREIGN_DIGITS = 4  # ~10 m coordinates for 1:10,000,000 context
SUBSTITUTED: dict[str, dict] = {}  # county GEOID -> evidence for block-derived water
FOREIGN: dict = {}  # record of the foreign-country context build


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def compact(item, digits: int = 6):
    if isinstance(item, float):
        return round(item, digits)
    if isinstance(item, dict):
        return {k: compact(v, digits) for k, v in item.items()}
    if isinstance(item, (list, tuple)):
        return [compact(v, digits) for v in item]
    return item


def write_json(path: Path, value, digits: int = 6) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(compact(value, digits), ensure_ascii=False, separators=(",", ":"))
    if path.suffix == ".gz":
        # mtime=0 keeps gzip bytes deterministic for identical content.
        path.write_bytes(gzip.compress(text.encode("utf-8"), compresslevel=9, mtime=0))
    else:
        path.write_text(text, encoding="utf-8")


def to_equal_area(coordinates: np.ndarray) -> np.ndarray:
    x, y = EQUAL_AREA.transform(coordinates[:, 0], coordinates[:, 1])
    return np.column_stack([x, y])


def polygons_only(geometry):
    parts = [g for g in shapely.get_parts(shapely.make_valid(geometry)) if g.geom_type in {"Polygon", "MultiPolygon"}]
    polygons = [p for g in parts for p in shapely.get_parts(g) if not p.is_empty]
    return shapely.orient_polygons(shapely.MultiPolygon(polygons)) if polygons else None


def lines_only(geometry):
    parts = [p for g in shapely.get_parts(geometry) if g.geom_type in {"LineString", "MultiLineString", "LinearRing"}
             for p in shapely.get_parts(g) if not p.is_empty]
    return shapely.line_merge(shapely.MultiLineString(parts)) if parts else None


def feature(geometry, properties, identifier):
    return {"type": "Feature", "id": identifier, "properties": properties, "geometry": mapping(geometry)}


def tile_id(x: int, y: int) -> str:
    return f"{x}_{y}"


def tiles_for(bounds) -> list[tuple[int, int]]:
    west, south, east, north = bounds
    return [(x, y) for x in range(math.floor(west), math.ceil(east)) for y in range(math.floor(south), math.ceil(north))]


# --- acquisition -----------------------------------------------------------------------------

def acquire_water(states: set[str]) -> dict:
    """Download each county AREAWATER file once; verify cached files by size and SHA-256."""
    WATER_CACHE.mkdir(parents=True, exist_ok=True)
    manifest_path = WATER_CACHE / "download_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}
    session = requests.Session()
    session.headers["User-Agent"] = "dc_locator/0.1 (Census frontend boundary preparation)"
    listing = session.get(AREAWATER_INDEX, timeout=60)
    listing.raise_for_status()
    names = sorted({name for name, county in re.findall(r'href="(tl_2025_(\d{5})_areawater\.zip)"', listing.text) if county[:2] in states})
    for number, name in enumerate(names, 1):
        path = WATER_CACHE / name
        if manifest.get(name, {}).get("status") == "BLOCKED":
            continue
        if path.exists():
            record = manifest.get(name)
            if not record or record["bytes"] != path.stat().st_size or record["sha256"] != digest(path):
                raise ValueError(f"Existing AREAWATER file is unverified: {name}")
            continue
        raw_bytes = sum(p.stat().st_size for p in (ROOT / "data/raw").rglob("*") if p.is_file())
        if raw_bytes + MAX_COUNTY_BYTES > PROJECT_RAW_BUDGET:
            raise ValueError("AREAWATER download would exceed the project raw-data budget")
        url = AREAWATER_INDEX + name
        response = None
        for attempt in range(3):
            # Polite retries for transient failures. A firewall "Request Rejected" page is an access
            # decision: it is recorded as BLOCKED and never circumvented (AGENTS.md section 4).
            try:
                response = session.get(url, timeout=(15, 120))
                if response.ok and response.content.startswith(b"PK"):
                    break
            except requests.RequestException:
                response = None
            time.sleep(15 * (attempt + 1))
        else:
            rejected = response is not None and b"Request Rejected" in response.content[:2000]
            manifest[name] = {"url": url, "status": "BLOCKED",
                "reason": ("Census web firewall returned an HTML 'Request Rejected' page on repeated polite requests; not circumvented"
                           if rejected else "No archive after repeated polite requests"),
                "http_status": None if response is None else response.status_code,
                "observed_at_utc": datetime.now(timezone.utc).isoformat()}
            write_json(manifest_path, manifest)
            print(f"BLOCKED {name}", flush=True)
            continue
        if len(response.content) > MAX_COUNTY_BYTES:
            raise ValueError(f"AREAWATER file exceeds bounded size: {name}")
        temporary = path.with_suffix(".zip.part")
        temporary.write_bytes(response.content)
        if zipfile.ZipFile(temporary).testzip() is not None:
            raise ValueError(f"Corrupt AREAWATER archive: {name}")
        temporary.replace(path)
        manifest[name] = {"url": url, "path": path.relative_to(ROOT).as_posix(), "bytes": path.stat().st_size,
            "sha256": digest(path), "vintage": 2025, "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
            "last_modified": response.headers.get("Last-Modified"),
            "license": "U.S. Government work; public domain", "access": "Public HTTP; no authentication"}
        write_json(manifest_path, manifest)  # after every file, so an interrupted batch resumes cleanly
        if number % 50 == 0:
            print(f"AREAWATER {number}/{len(names)}", flush=True)
    blocked = [name for name, record in manifest.items() if record.get("status") == "BLOCKED"]
    acquire_state_gdbs(session, {name[8:10] for name in blocked})
    outlines = COUNTY_OUTLINES.rsplit("/", 1)[-1]
    if blocked and outlines not in manifest:
        response = session.get(COUNTY_OUTLINES, timeout=(15, 120))
        response.raise_for_status()
        if not response.content.startswith(b"PK") or len(response.content) > MAX_COUNTY_BYTES:
            raise ValueError("Unexpected county outline response")
        path = WATER_CACHE / outlines
        path.write_bytes(response.content)
        manifest[outlines] = {"url": COUNTY_OUTLINES, "path": path.relative_to(ROOT).as_posix(), "bytes": path.stat().st_size,
            "sha256": digest(path), "vintage": 2025, "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
            "role": "county extents for withholding detailed land around BLOCKED AREAWATER files",
            "license": "U.S. Government work; public domain", "access": "Public HTTP; no authentication"}
    write_json(manifest_path, manifest)
    return manifest


def acquire_state_gdbs(session: requests.Session, states: set[str]) -> dict:
    """Download each needed per-state TIGER/Line geodatabase once; verify cached copies."""
    GDB_CACHE.mkdir(parents=True, exist_ok=True)
    path_manifest = GDB_CACHE / "download_manifest.json"
    manifest = json.loads(path_manifest.read_text(encoding="utf-8")) if path_manifest.exists() else {}
    abbreviations = dict(zip(*[load_states()[column] for column in ("STATEFP", "STUSPS")])) if states else {}
    for fips in sorted(states):
        url = STATE_GDB.format(fips=fips, abbreviation=abbreviations[fips].lower())
        name = url.rsplit("/", 1)[-1]
        path = GDB_CACHE / name
        record = manifest.get(name)
        if path.exists():
            if not record or record["bytes"] != path.stat().st_size or record["sha256"] != digest(path):
                raise ValueError(f"Existing state geodatabase is unverified: {name}")
            continue
        response = session.get(url, timeout=(15, 600))
        response.raise_for_status()
        if not response.content.startswith(b"PK") or len(response.content) > MAX_STATE_GDB_BYTES:
            manifest[name] = {"url": url, "status": "BLOCKED", "observed_at_utc": datetime.now(timezone.utc).isoformat()}
        else:
            path.write_bytes(response.content)
            manifest[name] = {"url": url, "path": path.relative_to(ROOT).as_posix(), "bytes": path.stat().st_size,
                "sha256": digest(path), "vintage": 2025, "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
                "last_modified": response.headers.get("Last-Modified"),
                "role": "official per-state TIGER/Line 2025 geodatabase; used only for AREAWATER of counties whose county file Census refused",
                "license": "U.S. Government work; public domain", "access": "Public HTTP; no authentication"}
        write_json(path_manifest, manifest)
    return manifest


def block_water(county: str):
    """All-water 2020 tabulation blocks (ALAND = 0) of one county from its state geodatabase."""
    path_manifest = GDB_CACHE / "download_manifest.json"
    if not path_manifest.exists():
        return None
    for name, record in json.loads(path_manifest.read_text(encoding="utf-8")).items():
        if not name.startswith(f"tlgdb_2025_a_{county[:2]}_") or record.get("status") == "BLOCKED":
            continue
        path = ROOT / record["path"]
        if digest(path) != record["sha256"]:
            raise ValueError(f"State geodatabase checksum mismatch: {name}")
        blocks = gpd.read_file("/vsizip/" + path.resolve().as_posix(), layer="Block20",
                               columns=["GEOID20", "ALAND", "AWATER"], where=f"GEOID20 LIKE '{county}%'")
        water = blocks.loc[blocks.ALAND == 0, ["geometry"]].to_crs(4326)
        water["MTFCC"] = "BLOCK_WATER"
        union = shapely.union_all(water.geometry.values) if len(water) else None
        area = float(gpd.GeoSeries([union], crs=4326).to_crs(6933).area.iloc[0]) if union is not None else 0.0
        evidence = {"source": record["url"], "sha256": record["sha256"],
            "method": "2020 tabulation blocks with zero land area (ALAND = 0) in the county, from the TIGER/Line 2025 state geodatabase",
            "water_blocks": int(len(water)), "water_block_area_km2": round(area / 1e6, 1),
            "county_recorded_water_area_km2": round(float(blocks.AWATER.sum()) / 1e6, 1)}
        return water.reset_index(drop=True), evidence
    return None


def blocked_extent(manifest: dict, substituted=frozenset()):
    """Union of counties whose AREAWATER file Census refused; detailed land is withheld there."""
    blocked = {name[8:13] for name, record in manifest.items() if record.get("status") == "BLOCKED"} - set(substituted)
    if not blocked:
        return None
    record = manifest[COUNTY_OUTLINES.rsplit("/", 1)[-1]]
    path = ROOT / record["path"]
    if digest(path) != record["sha256"]:
        raise ValueError("County outline checksum mismatch")
    counties = gpd.read_file(path).to_crs(4326)
    return shapely.union_all(counties.loc[counties.GEOID.isin(blocked)].geometry.values)


# --- sources ---------------------------------------------------------------------------------

def load_states() -> gpd.GeoDataFrame:
    record = json.loads((CACHE / "download_manifest.json").read_text(encoding="utf-8"))["administrative"]
    path = ROOT / record["path"]
    if digest(path) != record["sha256"]:
        raise ValueError("TIGER state source checksum mismatch")
    frame = gpd.read_file(path)
    frame = frame[~frame.STATEFP.isin(EXCLUDE)].sort_values("STATEFP").to_crs(4326).reset_index(drop=True)
    if len(frame) != 51:
        raise ValueError("Expected 50 states and DC")
    return frame


def state_water(fips: str, manifest: dict) -> gpd.GeoDataFrame:
    frames = []
    for name, record in sorted(manifest.items()):
        if name.startswith(f"tl_2025_{fips}") and name.endswith("_areawater.zip") and record.get("status") != "BLOCKED":
            path = ROOT / record["path"]
            if digest(path) != record["sha256"]:
                raise ValueError(f"AREAWATER checksum mismatch: {name}")
            frames.append(gpd.read_file(path, columns=["MTFCC"]).to_crs(4326))
    for name, record in sorted(manifest.items()):
        if name.startswith(f"tl_2025_{fips}") and record.get("status") == "BLOCKED":
            fallback = block_water(name[8:13])
            if fallback is not None:
                frames.append(fallback[0])
                SUBSTITUTED[name[8:13]] = fallback[1]
    if not frames:
        return gpd.GeoDataFrame({"MTFCC": []}, geometry=[], crs=4326)
    water = pd.concat(frames, ignore_index=True).to_crs(4326)
    water = water.loc[water.geometry.notna() & ~water.geometry.is_empty].reset_index(drop=True)
    area = shapely.area(shapely.transform(water.geometry.values, to_equal_area))
    group = np.where(water.MTFCC.isin(RIVERS | {"BLOCK_WATER"}), "river", np.where(water.MTFCC.isin(SEAWARD_WATER), "seaward", "other"))
    keep = area >= np.vectorize(MINIMUM_AREA_M2.get)(group)
    water = water.loc[keep].reset_index(drop=True)
    water["geometry"] = shapely.make_valid(water.geometry.values)
    return water


# --- borders ---------------------------------------------------------------------------------

def segment_filter(line, tree: shapely.STRtree | None, drop_within: float):
    """Keep the segments of ``line`` whose midpoints are farther than ``drop_within`` from every
    indexed polygon (vectorized; avoids overlaying lines with huge dissolved water polygons)."""
    if line is None or tree is None:
        return line
    pieces = []
    for part in shapely.get_parts(line):
        coordinates = shapely.get_coordinates(part)
        if len(coordinates) < 2:
            continue
        starts, ends = coordinates[:-1], coordinates[1:]
        midpoints = shapely.points((starts + ends) / 2)
        hits = tree.query(midpoints, predicate="dwithin", distance=drop_within) if drop_within > 0 else tree.query(midpoints, predicate="intersects")
        drop = np.zeros(len(midpoints), dtype=bool)
        drop[hits[0]] = True
        # Rebuild runs of kept, consecutive segments as lines.
        run = []
        for index, dropped in enumerate(drop):
            if dropped:
                if len(run) > 1:
                    pieces.append(shapely.linestrings(run))
                run = []
                continue
            if not run:
                run = [starts[index]]
            run.append(ends[index])
        if len(run) > 1:
            pieces.append(shapely.linestrings(run))
    return shapely.line_merge(shapely.MultiLineString(pieces)) if pieces else None


def shared_and_international(geometries: list, fips: list[str], seaward: dict, tolerance: float, ocean: shapely.STRtree | None = None):
    """Per state: edges shared with other states (not across open ocean), and the outline minus
    seaward limits along ocean and bay water."""
    country = shapely.coverage_union_all(geometries)
    tree = shapely.STRtree(geometries)
    shared, international = {}, {}
    for index, geometry in enumerate(geometries):
        neighbours = [i for i in tree.query(geometry, predicate="intersects") if i != index]
        lines = {fips[i]: lines_only(geometry.boundary.intersection(geometries[i].boundary)) for i in neighbours}
        lines = {key: segment_filter(line, ocean, 0 if tolerance < 0.001 else tolerance) for key, line in lines.items()}
        shared[fips[index]] = {key: line for key, line in lines.items() if line is not None}
        outline = lines_only(geometry.boundary.intersection(country.boundary))
        international[fips[index]] = segment_filter(outline, seaward.get(fips[index]), tolerance)
    return shared, international


# --- land tiles ------------------------------------------------------------------------------

def build_land_tiles(land_by_state: dict, country_outline, done: set[str], withheld=None) -> list[dict]:
    """Dissolved detailed land per 1-degree tile, plus shoreline lines that exclude tile
    edges and land borders with Canada or Mexico."""
    fips = sorted(land_by_state)
    geometries = [land_by_state[f] for f in fips]
    tree = shapely.STRtree(geometries)
    border_zone = shapely.buffer(country_outline, SEAWARD_TOLERANCE_DEGREES)
    keys = sorted({key for g in geometries for part in shapely.get_parts(g) for key in tiles_for(part.bounds)})
    records = []
    for x, y in keys:
        exact = (x, y, x + TILE_DEGREES, y + TILE_DEGREES)
        if withheld is not None and withheld.intersects(shapely.box(*exact)):
            continue  # generalized backdrop stays: a county water file in this tile was refused
        padded = (x - TILE_PAD_DEGREES, y - TILE_PAD_DEGREES, x + TILE_DEGREES + TILE_PAD_DEGREES, y + TILE_DEGREES + TILE_PAD_DEGREES)
        hits = tree.query(shapely.box(*padded), predicate="intersects")
        if not len(hits):
            continue
        pieces = [polygons_only(shapely.clip_by_rect(geometries[i], *padded)) for i in hits]
        pieces = [p for p in pieces if p is not None]
        if not pieces:
            continue
        land = shapely.make_valid(shapely.simplify(shapely.union_all(pieces), SIMPLIFY_DEGREES, preserve_topology=True))
        grid = 10 ** -TILE_DIGITS
        # Snap to the serialized grid with topology repair, so rounding on write cannot invalidate polygons.
        fill = polygons_only(shapely.set_precision(shapely.clip_by_rect(land, *exact), grid))
        if fill is None:
            continue
        shore = lines_only(shapely.clip_by_rect(land.boundary, *exact))
        if shore is not None:
            shore = lines_only(shapely.set_precision(shore.difference(border_zone), grid))
        identifier = tile_id(x, y)
        features = [feature(fill, {"kind": "land", "tile": identifier}, "land-" + identifier)]
        if shore is not None:
            features.append(feature(shore, {"kind": "shore", "tile": identifier}, "shore-" + identifier))
        path = OUTPUT / "land" / f"{identifier}.geojson.gz"
        write_json(path, {"type": "FeatureCollection", "features": features}, TILE_DIGITS)
        records.append({"tile": identifier, "bounds": list(exact), "bytes": path.stat().st_size, "sha256": digest(path),
            "states": sorted(fips[i] for i in hits), "coordinate_count": int(shapely.get_num_coordinates(fill))})
        done.add(identifier)
    return records


def split_overview(land_overview, tiles: set[str]) -> tuple[list, list]:
    """The generalized backdrop and its shoreline, cut along the same 1-degree tile edges."""
    fills, shores = [], []
    for x, y in sorted({key for part in shapely.get_parts(land_overview) for key in tiles_for(part.bounds)}):
        exact = (x, y, x + TILE_DEGREES, y + TILE_DEGREES)
        identifier = tile_id(x, y)
        fill = polygons_only(shapely.set_precision(shapely.clip_by_rect(land_overview, *exact), 1e-6))
        if fill is not None:
            fills.append(feature(fill, {"tile": identifier, "detail": identifier in tiles}, "land-" + identifier))
        shore = lines_only(shapely.clip_by_rect(land_overview.boundary, *exact))
        if shore is not None:
            shores.append(feature(shore, {"tile": identifier, "detail": identifier in tiles}, "shore-" + identifier))
    return fills, shores


# --- build -----------------------------------------------------------------------------------

def build(chosen: list[str], manifest: dict) -> dict:
    states = load_states()
    fips = list(states.STATEFP)
    geometries = list(states.geometry)
    water, seaward, land_by_state, ocean_parts = {}, {}, {}, []
    for code in fips:
        frame = state_water(code, manifest) if code in chosen else None
        if frame is not None and len(frame):
            water[code] = frame
            sea = frame.loc[frame.MTFCC.isin(SEAWARD_WATER)]
            if len(sea):
                seaward[code] = shapely.STRtree(sea.geometry.values)
            ocean_parts.extend(frame.loc[frame.MTFCC.isin(OCEAN)].geometry.values)
        print(f"water {code}: {0 if frame is None else len(frame)} polygons", flush=True)
    # Open-ocean polygons of all states: a border whose segment midpoints touch them crosses open ocean.
    ocean = shapely.STRtree(ocean_parts) if ocean_parts else None
    # Detailed borders.
    shared, international = shared_and_international(geometries, fips, seaward, SEAWARD_TOLERANCE_DEGREES, ocean)
    detail_records = []
    for code in fips:
        lines = [g for g in shared[code].values()]
        features = []
        if lines:
            features.append(feature(lines_only(shapely.union_all(lines)), {"kind": "state", "fips": code}, code))
        if international[code] is not None:
            features.append(feature(international[code], {"kind": "national", "fips": code}, "national-" + code))
        path = OUTPUT / "detail" / f"{code}.geojson"
        write_json(path, {"type": "FeatureCollection", "features": features})
        detail_records.append({"fips": code, "bytes": path.stat().st_size, "sha256": digest(path),
            "features": [f["properties"]["kind"] for f in features], "additional_simplification_m": 0})
    # Overview borders from the published coverage-simplified state overview.
    overview = json.loads((OUTPUT / "states.geojson").read_text(encoding="utf-8"))
    overview_geometries = [shape(f["geometry"]) for f in overview["features"]]
    overview_fips = [f["properties"]["fips"] for f in overview["features"]]
    overview_shared, overview_international = shared_and_international(overview_geometries, overview_fips, seaward, OVERVIEW_SEAWARD_TOLERANCE_DEGREES, ocean)
    borders, seen = [], set()
    for code in overview_fips:
        for other, line in sorted(overview_shared[code].items()):
            pair = tuple(sorted((code, other)))
            if pair in seen:
                continue
            seen.add(pair)
            borders.append(feature(line, {"fips_a": pair[0], "fips_b": pair[1]}, f"border-{pair[0]}-{pair[1]}"))
    national = [feature(line, {"fips": code}, "national-" + code) for code, line in overview_international.items() if line is not None]
    write_json(OUTPUT / "borders.geojson", {"type": "FeatureCollection", "features": borders})
    write_json(OUTPUT / "national.geojson", {"type": "FeatureCollection", "features": national})
    # Detailed land tiles.
    for code in fips:
        if code in water and code not in WITHOUT_LAND_DETAIL:
            land = polygons_only(shapely.difference(geometries[fips.index(code)], shapely.union_all(water[code].geometry.values)))
            if land is not None:
                land_by_state[code] = land
    country_outline = shapely.coverage_union_all(geometries).boundary
    done: set[str] = set()
    withheld = blocked_extent(manifest, set(SUBSTITUTED))
    land_records = build_land_tiles(land_by_state, country_outline, done, withheld)
    write_json(OUTPUT / "land" / "index.json", {"tile_degrees": TILE_DEGREES, "tiles": {r["tile"]: r["bounds"] for r in land_records}})
    # Generalized backdrop split by tile.
    land_overview = shape(json.loads((OUTPUT / "land.geojson").read_text(encoding="utf-8"))["features"][0]["geometry"]) \
        if len(json.loads((OUTPUT / "land.geojson").read_text(encoding="utf-8"))["features"]) == 1 else \
        shapely.union_all([shape(f["geometry"]) for f in json.loads((OUTPUT / "land.geojson").read_text(encoding="utf-8"))["features"]])
    FOREIGN.update(build_foreign_context(states))
    fills, shores = split_overview(land_overview, done)
    write_json(OUTPUT / "land.geojson", {"type": "FeatureCollection", "features": fills})
    write_json(OUTPUT / "shoreline.geojson", {"type": "FeatureCollection", "features": shores})
    summary = {"water_states": sorted(water), "land_detail_states": sorted(land_by_state), "land_tiles": len(land_records),
        "land_tile_bytes": sum(r["bytes"] for r in land_records), "largest_land_tile_bytes": max((r["bytes"] for r in land_records), default=0),
        "detail_bytes": sum(r["bytes"] for r in detail_records), "borders": len(borders), "national_parts": len(national)}
    record_manifest(manifest, detail_records, land_records, summary)
    print(json.dumps(summary, indent=2))
    return summary


def build_foreign_context(states: gpd.GeoDataFrame) -> dict:
    """Land outside the 50 states and DC as one plain fill, plus borders between other countries.

    Natural Earth 1:10m land minus the major lakes that touch U.S. territory (the Great Lakes stay
    water), minus the TIGER/Line U.S. polygon, so foreign land meets the U.S. at the TIGER border
    without gaps. Interior foreign lakes, rivers and terrain are deliberately not drawn.
    """
    manifest = json.loads((NATURAL_EARTH / "download_manifest.json").read_text(encoding="utf-8"))
    for name, record in manifest.items():
        if digest(ROOT / record["path"]) != record["sha256"]:
            raise ValueError(f"Natural Earth checksum mismatch: {name}")
    read = lambda name: gpd.read_file(ROOT / manifest[name]["path"]).to_crs(4326)
    land, lakes, lines = read("ne_10m_land.zip"), read("ne_10m_lakes.zip"), read("ne_10m_admin_0_boundary_lines_land.zip")
    united_states = shapely.coverage_union_all(list(states.geometry))
    shapely.prepare(united_states)
    near_box = shapely.box(*FOREIGN_NEAR_BOX)
    shapely.prepare(near_box)
    parts = shapely.get_parts(shapely.make_valid(np.asarray(land.geometry.values)))
    parts = parts[shapely.get_type_id(parts) == 3]
    near = shapely.intersects(near_box, shapely.point_on_surface(parts))
    tolerances = np.where(near, FOREIGN_SIMPLIFY_DEGREES["near"], FOREIGN_SIMPLIFY_DEGREES["far"])
    world = shapely.union_all([shapely.simplify(part, tol, preserve_topology=True) for part, tol in zip(parts, tolerances)])
    # Border lakes: partly U.S., partly foreign (Great Lakes, Lake of the Woods, ...).
    shared_lakes = lakes.loc[shapely.intersects(united_states, lakes.geometry.values) & ~shapely.contains(united_states, lakes.geometry.values)]
    if len(shared_lakes):
        world = shapely.difference(world, shapely.union_all(shapely.simplify(shared_lakes.geometry.values, FOREIGN_SIMPLIFY_DEGREES["near"], preserve_topology=True)))
    # Remove U.S. territory (TIGER/Line, including state waters), leaving a ~10 m margin for rounding.
    zone = shapely.simplify(shapely.buffer(united_states, FOREIGN_US_GAP_DEGREES, quad_segs=1), 0.0001)
    foreign = polygons_only(shapely.set_precision(shapely.difference(world, zone), 10 ** -FOREIGN_DIGITS))
    features = [feature(foreign, {"kind": "land"}, "foreign-land")]
    foreign_borders = shapely.union_all(lines.loc[(lines.ADM0_A3_L != "USA") & (lines.ADM0_A3_R != "USA")].geometry.values)
    near_lines = shapely.simplify(shapely.clip_by_rect(foreign_borders, *FOREIGN_NEAR_BOX), FOREIGN_SIMPLIFY_DEGREES["near"])
    far_lines = shapely.simplify(shapely.difference(foreign_borders, near_box), FOREIGN_SIMPLIFY_DEGREES["far"])
    border = lines_only(shapely.set_precision(shapely.union_all([near_lines, far_lines]), 10 ** -FOREIGN_DIGITS))
    if border is not None:
        features.append(feature(border, {"kind": "border"}, "foreign-border"))
    path = OUTPUT / "foreign.geojson"
    write_json(path, {"type": "FeatureCollection", "features": features}, FOREIGN_DIGITS)
    overlap = shapely.intersection(shape(features[0]["geometry"]), united_states).area
    if overlap > 1e-6:
        raise ValueError("Foreign context overlaps U.S. territory")
    record = {"sources": manifest, "file": path.relative_to(ROOT).as_posix(), "bytes": path.stat().st_size, "sha256": digest(path),
        "shared_lakes_kept_as_water": sorted(str(n) for n in shared_lakes.name.dropna()),
        "processing": "Natural Earth 1:10m land minus major lakes touching U.S. territory, minus the TIGER/Line U.S. polygon (~50 m margin): one plain fill without interior lakes, rivers or terrain; borders between two non-U.S. countries from Natural Earth land boundary lines; parts and borders within lon -170..-50, lat 5..56 simplified 0.003 degrees, others 0.02 degrees; 4-decimal coordinates",
        "us_overlap_square_degrees": overlap}
    print(json.dumps({k: v for k, v in record.items() if k != "sources"}), flush=True)
    return record


def record_manifest(water_manifest: dict, detail_records: list, land_records: list, summary: dict) -> None:
    path = OUTPUT / "boundary-manifest.json"
    record = json.loads(path.read_text(encoding="utf-8"))
    record["detail"] = detail_records
    record["land_detail"] = {
        "source": AREAWATER_INDEX, "vintage": 2025,
        "county_files": sum(1 for n, r in water_manifest.items() if n.endswith("_areawater.zip") and r.get("status") != "BLOCKED"),
        "county_bytes": sum(r.get("bytes", 0) for n, r in water_manifest.items() if n.endswith("_areawater.zip")),
        "blocked_county_files": {name: r["reason"] for name, r in sorted(water_manifest.items()) if r.get("status") == "BLOCKED"},
        "blocked_policy": "A refused county AREAWATER file is replaced by the county's all-water blocks from the official TIGER/Line 2025 state geodatabase; only if that is unavailable, 1-degree tiles that intersect the county publish no detailed land",
        "block_water_substitutes": SUBSTITUTED,
        "download_manifest": (WATER_CACHE / "download_manifest.json").relative_to(ROOT).as_posix(),
        "download_manifest_sha256": digest(WATER_CACHE / "download_manifest.json"),
        "processing": "TIGER/Line state polygon minus AREAWATER water; rivers kept from 1,000 m2, bays/estuaries/sounds and ocean from 20,000 m2, other water from 1 km2 (EPSG:6933 areas); dissolved across state lines per 1-degree tile; Douglas-Peucker simplification 0.00005 degrees (~5 m) preserving topology; 5-decimal coordinates; gzip; shoreline excludes tile edges and international land borders",
        "coverage": "Contiguous United States, DC and Hawaii; Alaska keeps the generalized backdrop",
        "minimum_display_zoom": 9, "tiles": land_records}
    record["borders"] = {"state": "edges shared by two states (land or water); seaward limits are not drawn",
        "national": "U.S. outline minus seaward limits along TIGER AREAWATER ocean (H2053) and bay/estuary/sound (H2051) water, i.e. international borders",
        "state_open_ocean": "Shared state borders are trimmed where they cross dissolved open-ocean (H2053) water; they remain through bays, sounds, rivers and lakes",
        "overview_seaward_tolerance_degrees": OVERVIEW_SEAWARD_TOLERANCE_DEGREES, "detail_seaward_tolerance_degrees": SEAWARD_TOLERANCE_DEGREES}
    record["land_detail_summary"] = summary
    if FOREIGN:
        record["foreign_context"] = FOREIGN
    write_json(path, record)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--states", help="Comma-separated state FIPS (default: 50 states and DC)")
    parser.add_argument("--download-only", action="store_true")
    parser.add_argument("--foreign-only", action="store_true", help="Rebuild only foreign.geojson and its manifest record")
    args = parser.parse_args()
    if args.foreign_only:
        manifest_path = OUTPUT / "boundary-manifest.json"
        record = json.loads(manifest_path.read_text(encoding="utf-8"))
        record["foreign_context"] = build_foreign_context(load_states())
        write_json(manifest_path, record)
        raise SystemExit(0)
    all_fips = sorted(set(load_states().STATEFP))
    chosen = sorted(args.states.split(",")) if args.states else all_fips
    water_manifest = acquire_water(set(chosen))
    if not args.download_only:
        build(chosen, water_manifest)
