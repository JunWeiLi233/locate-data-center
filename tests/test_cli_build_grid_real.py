"""End-to-end `dc-locator build-grid` test against the real, cached CONUS
boundary (AGENTS.md section 10: real_data tests must actually execute).

Uses a coarse 100 km cell size (instead of the production 10 km default) so
the full pipeline -- download-cache check, boundary load, national grid
generation, state/county attribution overlay, development-area selection,
GeoParquet write -- runs in seconds rather than minutes. This is still a
genuine real-data integration test (same code path, same real Census
boundary, same algorithm), just at a coarser resolution; see
docs/limitations.md for why the 10 km production outputs are generated
separately rather than regenerated on every test run.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
import yaml


def _sha256_of_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

from dc_locator.cli import main
from dc_locator.geography.boundary import download_conus_boundary_sources
from dc_locator.io import read_geoparquet, read_parquet_metadata
from dc_locator.paths import configs_dir


@pytest.fixture
def coarse_grid_config_path(tmp_path: Path) -> Path:
    real_config = yaml.safe_load((configs_dir() / "grid.yaml").read_text("utf-8"))
    real_config["cell_size_m"] = 100_000.0  # 100 km: ~800-1300 candidate cells instead of ~135,000
    real_config["id_row_col_digits"] = 3
    path = tmp_path / "grid.yaml"
    path.write_text(yaml.dump(real_config), encoding="utf-8")
    return path


@pytest.mark.real_data
def test_build_grid_end_to_end(coarse_grid_config_path: Path, tmp_path: Path) -> None:
    download_conus_boundary_sources()  # ensure cached; idempotent, no-op if already present

    out_dir = tmp_path / "out"
    exit_code = main([
        "build-grid",
        "--grid-config", str(coarse_grid_config_path),
        "--output-dir", str(out_dir),
        "--skip-download",
    ])
    assert exit_code == 0

    national_path = out_dir / "us_grid.parquet"
    assert national_path.is_file()
    national = read_geoparquet(national_path)
    assert len(national) > 100  # sanity: a real (if coarse) national grid, not an empty/trivial one
    assert national["grid_id"].is_unique
    assert national.geometry.is_valid.all()
    assert list(zip(national["row"], national["col"])) == sorted(zip(national["row"], national["col"]))  # sorted by row, col

    summary_path = out_dir / "us_grid_summary.json"
    assert summary_path.is_file()
    summary = json.loads(summary_path.read_text("utf-8"))
    assert summary["generation_stats"]["n_retained"] == len(national)
    assert summary["files"]["national"]["sha256"] == _sha256_of_file(national_path)
    assert sum(summary["per_state_cell_counts"].values()) == len(national)

    meta = read_parquet_metadata(national_path)
    assert meta["schema"] == "GridCell"
    assert meta["data_mode"] == "real"

    # The bulk pipeline builds columns directly (vectorized) rather than
    # instantiating GridCell per row (AGENTS.md section 7: no per-cell Python
    # loop over national-scale data) -- spot-check real rows against the
    # pydantic contract itself so "matches the schema" is verified, not just
    # assumed from column-name similarity.
    from dc_locator.schemas import GridCell

    sample = national.sample(n=min(25, len(national)), random_state=0)
    for _, row in sample.iterrows():
        GridCell(**row.to_dict())  # raises pydantic.ValidationError if the real row violates the contract

    dev_tiny_path = out_dir / "us_grid__dev_tiny.parquet"
    dev_default_path = out_dir / "us_grid__dev_default.parquet"
    assert dev_tiny_path.is_file()
    assert dev_default_path.is_file()

    dev_tiny = read_geoparquet(dev_tiny_path)
    assert len(dev_tiny) >= 1
    assert set(dev_tiny["grid_id"]).issubset(set(national["grid_id"]))  # GRID CONTRACT: selection, not re-derivation

    # GRID CONTRACT acceptance check: a cell retained in both outputs is
    # byte-for-byte identical in every non-geometry-subsetting attribute.
    merged = dev_tiny.drop(columns="geometry").merge(
        national.drop(columns="geometry"), on="grid_id", suffixes=("_dev", "_national"),
    )
    assert len(merged) == len(dev_tiny)
    for col in ("study_area_intersection_km2", "state_fips_primary", "county_geoid_primary", "cell_area_km2"):
        assert (merged[f"{col}_dev"] == merged[f"{col}_national"]).all()


@pytest.mark.real_data
def test_build_grid_is_repeatable(coarse_grid_config_path: Path, tmp_path: Path) -> None:
    """GRID CONTRACT acceptance check: identical grid configuration produces identical IDs and geometries."""
    download_conus_boundary_sources()

    out_dir_1 = tmp_path / "run1"
    out_dir_2 = tmp_path / "run2"
    for out_dir in (out_dir_1, out_dir_2):
        code = main(["build-grid", "--grid-config", str(coarse_grid_config_path), "--output-dir", str(out_dir), "--national-only", "--skip-download"])
        assert code == 0

    grid_1 = read_geoparquet(out_dir_1 / "us_grid.parquet")
    grid_2 = read_geoparquet(out_dir_2 / "us_grid.parquet")
    assert grid_1.drop(columns="geometry").equals(grid_2.drop(columns="geometry"))
    assert grid_1.geometry.geom_equals_exact(grid_2.geometry, tolerance=1e-9).all()
