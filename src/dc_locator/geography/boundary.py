"""Authoritative CONUS boundary acquisition and loading (AGENTS.md section 4;
GRID CONTRACT).

Source: U.S. Census Bureau cartographic boundary files (GENZ2023 vintage),
served over plain public HTTP under www2.census.gov with no authentication,
no CAPTCHA, and no click-through license -- U.S. Government work, public
domain. See `data/raw/census_cartographic_boundary/download_log.json` for
the exact URLs, retrieval timestamp, byte counts, and sha256 actually
recorded for the files cached in this checkout.

Cartographic boundary files (as opposed to full-resolution TIGER/Line files)
are generalized for thematic mapping at 1:500,000 scale -- appropriate for a
10 km (or coarser) analysis grid, and far smaller to download/process than
the full-resolution files. This is documented as a deliberate choice in
docs/sources.md; a future phase needing finer coastline detail should
upgrade to TIGER/Line and re-generate the grid, noting the schema/version
change per AGENTS.md section 9.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import geopandas as gpd
import requests
from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union

from dc_locator.paths import source_raw_dir

SOURCE_ID = "census_cartographic_boundary"
STATE_URL = "https://www2.census.gov/geo/tiger/GENZ2023/shp/cb_2023_us_state_500k.zip"
COUNTY_URL = "https://www2.census.gov/geo/tiger/GENZ2023/shp/cb_2023_us_county_500k.zip"
VINTAGE = "2023"  # GENZ2023 cartographic boundary release (server Last-Modified: 2024-04-16).
USER_AGENT = "dc_locator/0.1 (research prototype)"
REQUEST_TIMEOUT_S = 120

# CONUS = 48 states + DC; excludes Alaska (02), Hawaii (15), and the island
# territories: American Samoa (60), Guam (66), Northern Mariana Islands (69),
# Puerto Rico (72), U.S. Virgin Islands (78).
EXCLUDED_STATE_FIPS = frozenset({"02", "15", "60", "66", "69", "72", "78"})
EXPECTED_CONUS_STATE_COUNT = 49  # 48 states + DC

TARGET_CRS = "EPSG:5070"


class BoundarySourceNotCachedError(FileNotFoundError):
    """Raised when load_conus_boundary() is called before the source zips are downloaded."""


class BoundarySourceSchemaError(RuntimeError):
    """Raised when the downloaded source no longer matches the schema this module expects."""


@dataclass(frozen=True)
class CONUSBoundary:
    """The loaded, CONUS-filtered, EPSG:5070 boundary and its attribution layers."""

    boundary: BaseGeometry  # unary_union of the 48 states + DC geometries, EPSG:5070
    states: gpd.GeoDataFrame  # EXPECTED_CONUS_STATE_COUNT rows, EPSG:5070
    counties: gpd.GeoDataFrame  # CONUS-only counties, EPSG:5070
    source_id: str
    vintage: str
    state_zip_sha256: str
    county_zip_sha256: str


def _sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_manifest(manifest_path: Path) -> list[dict]:
    if not manifest_path.is_file():
        return []
    return json.loads(manifest_path.read_text(encoding="utf-8"))


def _write_manifest(manifest_path: Path, entries: list[dict]) -> None:
    manifest_path.write_text(json.dumps(entries, indent=2) + "\n", encoding="utf-8")


def download_conus_boundary_sources(raw_dir: Optional[Path] = None, *, force: bool = False) -> dict[str, Path]:
    """Idempotently fetch the state and county cartographic boundary zips.

    Skips a file whose cached bytes already match its download_log.json
    sha256 entry (AGENTS.md section 4: "Never re-download a cached, verified
    file."). Pass force=True to re-download anyway. Raises on HTTP failure or
    a response that is not actually a zip (e.g. an HTML error/consent page),
    rather than silently caching bad data.
    """
    target_dir = raw_dir if raw_dir is not None else source_raw_dir(SOURCE_ID)
    target_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = target_dir / "download_log.json"
    manifest = _read_manifest(manifest_path)
    manifest_by_name = {Path(entry["path"]).name: entry for entry in manifest}

    out: dict[str, Path] = {}
    for key, url in (("states", STATE_URL), ("counties", COUNTY_URL)):
        dest = target_dir / Path(url).name
        cached_entry = manifest_by_name.get(dest.name)
        if dest.is_file() and cached_entry is not None and not force:
            if _sha256_of(dest) == cached_entry.get("sha256"):
                out[key] = dest
                continue

        response = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=REQUEST_TIMEOUT_S)
        response.raise_for_status()
        content_type = response.headers.get("Content-Type", "")
        if "zip" not in content_type and not response.content.startswith(b"PK"):
            raise RuntimeError(
                f"Unexpected response fetching {url}: Content-Type={content_type!r} and content does not "
                "start with the zip magic bytes 'PK'; refusing to cache a non-zip payload."
            )
        dest.write_bytes(response.content)
        sha256 = _sha256_of(dest)
        retrieved_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        entry = {
            "url": url,
            "path": f"data/raw/{SOURCE_ID}/{dest.name}",
            "bytes": dest.stat().st_size,
            "sha256": sha256,
            "retrieved_at_utc": retrieved_at,
            "notes": cached_entry.get("notes") if cached_entry else None,
        }
        manifest_by_name[dest.name] = entry
        out[key] = dest

    _write_manifest(manifest_path, list(manifest_by_name.values()))
    return out


def load_conus_boundary(raw_dir: Optional[Path] = None) -> CONUSBoundary:
    """Load the cached state/county boundary zips, filter to CONUS (48
    states + DC), reproject to EPSG:5070, and union the states into one
    boundary polygon.

    Raises BoundarySourceNotCachedError with an actionable message if the
    source zips have not been downloaded yet -- call
    download_conus_boundary_sources() first (AGENTS.md section 4: batch
    download once, then reuse the cache; no implicit network access here).
    """
    target_dir = raw_dir if raw_dir is not None else source_raw_dir(SOURCE_ID)
    state_zip = target_dir / Path(STATE_URL).name
    county_zip = target_dir / Path(COUNTY_URL).name
    for path in (state_zip, county_zip):
        if not path.is_file():
            raise BoundarySourceNotCachedError(
                f"{path} is not cached. Call "
                "dc_locator.geography.boundary.download_conus_boundary_sources() first."
            )

    states_all = gpd.read_file(f"zip://{state_zip}")
    counties_all = gpd.read_file(f"zip://{county_zip}")

    for name, gdf in (("state", states_all), ("county", counties_all)):
        if "STATEFP" not in gdf.columns:
            raise BoundarySourceSchemaError(f"Expected a STATEFP column in the {name} cartographic boundary file; columns were {list(gdf.columns)}.")

    states = states_all.loc[~states_all["STATEFP"].isin(EXCLUDED_STATE_FIPS)].to_crs(TARGET_CRS).reset_index(drop=True)
    counties = counties_all.loc[~counties_all["STATEFP"].isin(EXCLUDED_STATE_FIPS)].to_crs(TARGET_CRS).reset_index(drop=True)

    if len(states) != EXPECTED_CONUS_STATE_COUNT:
        raise BoundarySourceSchemaError(
            f"Expected {EXPECTED_CONUS_STATE_COUNT} CONUS state/DC features after filtering, got {len(states)}; "
            "the source schema or FIPS coding may have changed -- do not silently proceed."
        )

    boundary = unary_union(states.geometry.to_numpy())
    if not boundary.is_valid:
        boundary = boundary.buffer(0)  # standard shapely fix for a self-intersection introduced by unioning

    return CONUSBoundary(
        boundary=boundary,
        states=states,
        counties=counties,
        source_id=SOURCE_ID,
        vintage=VINTAGE,
        state_zip_sha256=_sha256_of(state_zip),
        county_zip_sha256=_sha256_of(county_zip),
    )


__all__ = [
    "SOURCE_ID",
    "STATE_URL",
    "COUNTY_URL",
    "VINTAGE",
    "USER_AGENT",
    "EXCLUDED_STATE_FIPS",
    "EXPECTED_CONUS_STATE_COUNT",
    "TARGET_CRS",
    "BoundarySourceNotCachedError",
    "BoundarySourceSchemaError",
    "CONUSBoundary",
    "download_conus_boundary_sources",
    "load_conus_boundary",
]
