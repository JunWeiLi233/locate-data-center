"""Tests for dc_locator.io: Parquet/GeoParquet IO and the file-metadata contract (AGENTS.md section 6)."""

from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import pandas as pd
import pytest
from shapely.geometry import box

from dc_locator.io import (
    SyntheticDataInProcessedDirError,
    read_geoparquet,
    read_parquet,
    read_parquet_metadata,
    write_geoparquet,
    write_parquet,
)
from dc_locator.paths import processed_dir
from dc_locator.provenance import DataMode


def _synthetic_gdf() -> gpd.GeoDataFrame:
    return gpd.GeoDataFrame(
        {"grid_id": ["g1", "g2"], "value": [1.0, 2.0]},
        geometry=[box(0, 0, 1, 1), box(1, 1, 2, 2)],
        crs="EPSG:5070",
    )


def test_write_read_geoparquet_roundtrip(tmp_path: Path) -> None:
    gdf = _synthetic_gdf()
    path = write_geoparquet(
        gdf, tmp_path / "test.parquet",
        schema_name="GridCell", schema_version="1.0.0",
        data_mode=DataMode.SYNTHETIC, grid_definition_id="test-def-v1",
    )
    assert path.is_file()
    loaded = read_geoparquet(path)
    assert list(loaded["grid_id"]) == ["g1", "g2"]
    assert loaded.crs.to_string() == "EPSG:5070"
    assert loaded.geometry.iloc[0].equals(gdf.geometry.iloc[0])


def test_geoparquet_metadata_contract_keys_present(tmp_path: Path) -> None:
    gdf = _synthetic_gdf()
    path = write_geoparquet(
        gdf, tmp_path / "test.parquet",
        schema_name="GridCell", schema_version="1.0.0",
        data_mode=DataMode.SYNTHETIC, grid_definition_id="test-def-v1",
    )
    meta = read_parquet_metadata(path)
    assert meta["schema"] == "GridCell"
    assert meta["schema_version"] == "1.0.0"
    assert meta["data_mode"] == "synthetic"
    assert meta["grid_definition_id"] == "test-def-v1"
    assert meta["created_by"].startswith("dc_locator/")


def test_geoparquet_metadata_preserves_geo_key_for_valid_geoparquet(tmp_path: Path) -> None:
    import pyarrow.parquet as pq

    path = write_geoparquet(
        _synthetic_gdf(), tmp_path / "test.parquet",
        schema_name="GridCell", schema_version="1.0.0", data_mode=DataMode.SYNTHETIC,
    )
    raw_meta = pq.read_schema(path).metadata
    assert b"geo" in raw_meta  # GeoParquet's own spec key must survive our metadata merge


def test_write_plain_parquet_roundtrip(tmp_path: Path) -> None:
    df = pd.DataFrame({"grid_id": ["g1", "g2"], "metric": ["a", "b"]})
    path = write_parquet(df, tmp_path / "plain.parquet", schema_name="FeatureMetadata", schema_version="1.0.0", data_mode=DataMode.SYNTHETIC)
    loaded = read_parquet(path)
    assert list(loaded["grid_id"]) == ["g1", "g2"]


def test_refuses_synthetic_data_under_processed_dir() -> None:
    bad_path = processed_dir() / "should_never_be_written.parquet"
    with pytest.raises(SyntheticDataInProcessedDirError):
        write_geoparquet(_synthetic_gdf(), bad_path, schema_name="GridCell", schema_version="1.0.0", data_mode=DataMode.SYNTHETIC)
    assert not bad_path.exists()  # guard must fire BEFORE any file is written


def test_allows_real_data_under_processed_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Redirect processed_dir() to a throwaway tmp_path so this test cannot
    # leave a stray file under the real data/processed/ (AGENTS.md section 3.6
    # still applies even to a REAL-mode write in a test).
    import dc_locator.io as io_module

    monkeypatch.setattr(io_module, "processed_dir", lambda: tmp_path)
    path = write_geoparquet(_synthetic_gdf(), tmp_path / "real_output.parquet", schema_name="GridCell", schema_version="1.0.0", data_mode=DataMode.REAL)
    assert path.is_file()


def test_read_geoparquet_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        read_geoparquet(tmp_path / "nope.parquet")


def test_read_parquet_metadata_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        read_parquet_metadata(tmp_path / "nope.parquet")
