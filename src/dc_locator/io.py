"""Parquet / GeoParquet IO helpers (AGENTS.md section 6).

Every table this project writes carries the file-metadata keys
`dc_locator.schema`, `dc_locator.schema_version`, `dc_locator.data_mode`,
`dc_locator.grid_definition_id` (geography tables only), and
`dc_locator.created_by`. Writing `data_mode=synthetic` under
`data/processed/` is refused outright (AGENTS.md section 3.6): synthetic
fixtures belong only in `tests/fixtures/` or a run folder whose own
`data_mode` is `synthetic`.
"""

from __future__ import annotations

import getpass
import platform
from pathlib import Path
from typing import Optional

import geopandas as gpd
import pandas as pd
import pyarrow.parquet as pq

import dc_locator
from dc_locator.paths import processed_dir
from dc_locator.provenance import DataMode

_METADATA_PREFIX = "dc_locator."


class SyntheticDataInProcessedDirError(RuntimeError):
    """Raised when code attempts to write data_mode=synthetic under data/processed/ (AGENTS.md section 3.6)."""


def _created_by() -> str:
    try:
        host = platform.node()
    except Exception:
        host = "unknown-host"
    try:
        user = getpass.getuser()
    except Exception:
        user = "unknown-user"
    return f"dc_locator/{dc_locator.__version__} ({host}/{user})"


def _build_metadata(
    schema_name: str,
    schema_version: str,
    data_mode: DataMode,
    grid_definition_id: Optional[str],
) -> dict[bytes, bytes]:
    meta = {
        f"{_METADATA_PREFIX}schema": schema_name,
        f"{_METADATA_PREFIX}schema_version": schema_version,
        f"{_METADATA_PREFIX}data_mode": data_mode.value,
        f"{_METADATA_PREFIX}created_by": _created_by(),
    }
    if grid_definition_id is not None:
        meta[f"{_METADATA_PREFIX}grid_definition_id"] = grid_definition_id
    return {k.encode("utf-8"): v.encode("utf-8") for k, v in meta.items()}


def _guard_processed_path(path: Path, data_mode: DataMode) -> None:
    """Refuse data_mode=synthetic anywhere under data/processed/."""
    resolved = path.resolve()
    try:
        resolved.relative_to(processed_dir().resolve())
    except ValueError:
        return  # path is not under data/processed/; no restriction here
    if data_mode is DataMode.SYNTHETIC:
        raise SyntheticDataInProcessedDirError(
            f"Refusing to write data_mode=synthetic to {path}: data/processed/ holds real-data "
            "geography outputs ONLY (AGENTS.md section 3.6). Write synthetic data under "
            "tests/fixtures/ or a run folder with data_mode=synthetic instead."
        )


def _attach_metadata(
    path: Path,
    schema_name: str,
    schema_version: str,
    data_mode: DataMode,
    grid_definition_id: Optional[str],
) -> None:
    """Merge dc_locator.* keys into an already-written parquet file's schema
    metadata without disturbing any existing keys (e.g. GeoParquet's own
    'geo' key, which GeoPandas writes and must survive this merge).
    """
    table = pq.read_table(path)
    merged = dict(table.schema.metadata or {})
    merged.update(_build_metadata(schema_name, schema_version, data_mode, grid_definition_id))
    table = table.replace_schema_metadata(merged)
    pq.write_table(table, path)


def write_geoparquet(
    gdf: gpd.GeoDataFrame,
    path: Path,
    *,
    schema_name: str,
    schema_version: str,
    data_mode: DataMode,
    grid_definition_id: Optional[str] = None,
) -> Path:
    """Write a GeoDataFrame as GeoParquet with the required dc_locator.* file metadata."""
    path = Path(path)
    _guard_processed_path(path, data_mode)
    path.parent.mkdir(parents=True, exist_ok=True)
    gdf.to_parquet(path, index=False)
    _attach_metadata(path, schema_name, schema_version, data_mode, grid_definition_id)
    return path


def read_geoparquet(path: Path) -> gpd.GeoDataFrame:
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"No GeoParquet file at {path}.")
    return gpd.read_parquet(path)


def write_parquet(
    df: pd.DataFrame,
    path: Path,
    *,
    schema_name: str,
    schema_version: str,
    data_mode: DataMode,
    grid_definition_id: Optional[str] = None,
) -> Path:
    """Write a plain (non-geometry) DataFrame as Parquet with the same
    dc_locator.* file metadata contract as write_geoparquet. For tables such
    as Phase 2's feature_provenance.parquet.
    """
    path = Path(path)
    _guard_processed_path(path, data_mode)
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path, index=False)
    _attach_metadata(path, schema_name, schema_version, data_mode, grid_definition_id)
    return path


def read_parquet(path: Path) -> pd.DataFrame:
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"No Parquet file at {path}.")
    return pd.read_parquet(path)


def read_parquet_metadata(path: Path) -> dict[str, str]:
    """Return only the dc_locator.* file-metadata keys (prefix stripped)."""
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"No Parquet file at {path}.")
    meta = pq.read_schema(path).metadata or {}
    out: dict[str, str] = {}
    for key, value in meta.items():
        decoded_key = key.decode("utf-8")
        if decoded_key.startswith(_METADATA_PREFIX):
            out[decoded_key[len(_METADATA_PREFIX):]] = value.decode("utf-8")
    return out


__all__ = [
    "SyntheticDataInProcessedDirError",
    "write_geoparquet",
    "read_geoparquet",
    "write_parquet",
    "read_parquet",
    "read_parquet_metadata",
]
