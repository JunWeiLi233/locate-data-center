"""Tests for dc_locator.geography.boundary.

Marked `real_data` (needs the Census cartographic boundary files already
cached under data/raw/census_cartographic_boundary/ -- see
docs/sources.md) and `network` (download_conus_boundary_sources talks to
www2.census.gov, though it should be a cache hit in CI if the files are
already present). Per AGENTS.md section 10 / the Phase 1 fix instructions,
these must actually execute, not be skipped by default.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from dc_locator.geography.boundary import (
    EXCLUDED_STATE_FIPS,
    EXPECTED_CONUS_STATE_COUNT,
    TARGET_CRS,
    BoundarySourceNotCachedError,
    download_conus_boundary_sources,
    load_conus_boundary,
)


@pytest.mark.real_data
@pytest.mark.network
def test_download_is_idempotent_cache_hit() -> None:
    paths_first = download_conus_boundary_sources()
    mtimes_before = {k: p.stat().st_mtime for k, p in paths_first.items()}
    paths_second = download_conus_boundary_sources()
    mtimes_after = {k: p.stat().st_mtime for k, p in paths_second.items()}
    assert mtimes_before == mtimes_after  # second call must not re-download/rewrite the cached files


@pytest.mark.real_data
def test_load_conus_boundary_shape() -> None:
    download_conus_boundary_sources()
    boundary = load_conus_boundary()

    assert len(boundary.states) == EXPECTED_CONUS_STATE_COUNT == 49
    assert boundary.states.crs.to_string() == TARGET_CRS
    assert boundary.counties.crs.to_string() == TARGET_CRS
    assert boundary.boundary.is_valid
    assert not boundary.boundary.is_empty

    # CONUS = 48 states + DC; AK/HI/territories excluded.
    assert not set(boundary.states["STATEFP"]).intersection(EXCLUDED_STATE_FIPS)
    assert len(boundary.counties) > 3000  # CONUS has ~3,100 counties/equivalents

    # Plausible CONUS land+water area order of magnitude (public knowledge:
    # roughly 8 million km2); a wildly wrong number would indicate a CRS or
    # filtering bug, not a precise check against an external authority.
    area_km2 = boundary.boundary.area / 1e6
    assert 7_000_000 < area_km2 < 9_000_000


@pytest.mark.real_data
def test_loaded_zip_sha256_matches_download_manifest() -> None:
    import json

    from dc_locator.paths import source_raw_dir

    boundary = load_conus_boundary()
    manifest = json.loads((source_raw_dir(boundary.source_id) / "download_log.json").read_text("utf-8"))
    sha_by_name = {Path(entry["path"]).name: entry["sha256"] for entry in manifest}
    assert sha_by_name["cb_2023_us_state_500k.zip"] == boundary.state_zip_sha256
    assert sha_by_name["cb_2023_us_county_500k.zip"] == boundary.county_zip_sha256


def test_load_conus_boundary_raises_actionable_error_when_not_cached(tmp_path: Path) -> None:
    with pytest.raises(BoundarySourceNotCachedError, match="download_conus_boundary_sources"):
        load_conus_boundary(raw_dir=tmp_path)
