"""Comparison input integrity and stored geographic-support format."""
import json

import pandas as pd
import pytest

from dc_locator.geography.sources.ingestion import file_digest
from dc_locator.io import write_parquet
from dc_locator.provenance import DataMode
from dc_locator.reference_comparison import _saved_inputs


def test_synthetic_saved_run_cannot_be_compared_as_real_reference(tmp_path):
    frame = pd.DataFrame({"grid_id": ["g"], "grid_definition_id": ["synthetic"],
                          "data_mode": ["synthetic"], "county_geoid_all": ["00001;00002"]})
    path = tmp_path / "us_grid_dataset.parquet"
    write_parquet(frame, path, schema_name="SyntheticGridFixture", schema_version="1.0.0",
                  data_mode=DataMode.SYNTHETIC, grid_definition_id="synthetic")
    (tmp_path / "run_metadata.json").write_text(json.dumps({"output_hashes": {path.name: file_digest(path)}}))
    with pytest.raises(ValueError, match="requires a real model"):
        _saved_inputs(tmp_path)


def test_saved_run_checksum_must_precede_parquet_read(tmp_path):
    path = tmp_path / "us_grid_dataset.parquet"
    path.write_bytes(b"synthetic corrupted input")
    (tmp_path / "run_metadata.json").write_text(json.dumps({"output_hashes": {path.name: "0"*64}}))
    with pytest.raises(ValueError, match="missing or changed"):
        _saved_inputs(tmp_path)


def test_real_metadata_cannot_hide_synthetic_rows(tmp_path, monkeypatch):
    frame = pd.DataFrame({"grid_id": ["g"], "grid_definition_id": ["synthetic"],
                          "data_mode": ["synthetic"], "county_geoid_all": ["00001"]})
    path = tmp_path / "us_grid_dataset.parquet"
    write_parquet(frame, path, schema_name="SyntheticGridFixture", schema_version="1.0.0",
                  data_mode=DataMode.SYNTHETIC, grid_definition_id="synthetic")
    (tmp_path / "run_metadata.json").write_text(json.dumps({"output_hashes": {path.name: file_digest(path)}}))
    monkeypatch.setattr("dc_locator.reference_comparison.read_parquet_metadata",
                        lambda _: {"data_mode": "real", "grid_definition_id": "synthetic"})
    with pytest.raises(ValueError, match="rows disagree"):
        _saved_inputs(tmp_path)


def test_current_real_saved_grid_support_is_read_without_point_inference():
    from pathlib import Path
    path = Path("runs/national_discovery_v2")
    if not path.is_dir():
        pytest.skip("No real saved national evidence in this checkout")
    grid, ranked, _, hashes = _saved_inputs(path)
    assert isinstance(grid.county_geoid_all.iloc[0], list)
    assert set(grid.data_mode) == set(ranked.data_mode) == {"real"}
    assert len(hashes) == 3


def test_historical_sparse_regional_grid_uses_verified_native_county_support():
    from pathlib import Path
    path = Path("runs/regional_refinement_v4")
    if not path.is_dir():
        pytest.skip("No real saved regional evidence in this checkout")
    grid, ranked, _, hashes = _saved_inputs(path)
    assert len(grid) == 152500
    assert set(grid.data_mode) == {"real"}
    assert all(isinstance(value, list) for value in grid.county_geoid_all)
    assert set(grid.grid_id) == set(ranked.grid_id)
    assert len(hashes) == 65
    assert all(file_digest(Path(name)) == sha for name, sha in hashes.items())


def test_reference_county_mutation_is_rejected_by_raw_public_lineage():
    from pathlib import Path
    from dc_locator.reference_comparison import _verify_reference_lineage
    root = Path.cwd()
    folder = root / "data/raw/cleanview_reference/public_listing_v1"
    if not (folder / "reference.json").is_file():
        pytest.skip("No acquired public Cleanview reference in this checkout")
    document = json.loads((folder / "reference.json").read_text(encoding="utf-8"))
    entries = json.loads((folder / "download_log.json").read_text(encoding="utf-8"))
    assert len(_verify_reference_lineage(document, entries, root)) == len(entries)
    document["rows"][0]["county_text"] = "Synthetic impostor county"
    with pytest.raises(ValueError, match="do not match acquired"):
        _verify_reference_lineage(document, entries, root)
