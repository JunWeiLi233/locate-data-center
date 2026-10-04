"""Phase 11 metadata transport remains separate from fully evaluated regions."""
import json
import shutil

import pytest

from dc_locator.geography.sources.ingestion import file_digest
from frontend.server.serialization import ArtifactReader, ApiError
from frontend.server.service import LocatorService, STAGES
from frontend.server_tests.test_regional_bridge import regional, ACCEPTED


def add_surface(folder):
    """Opaque transport evidence; these fixtures are never a scientific run."""
    meta = json.loads((folder / "run_metadata.json").read_text(encoding="utf-8"))
    catalog = json.loads((folder / "regional_catalog.json").read_text(encoding="utf-8"))
    surface = folder / "national_fine_surface"
    surface.mkdir()
    hashes = {}
    for name in ("fine_surface_cells.parquet", "fine_surface_parents.parquet", "feature_provenance.parquet"):
        path = surface / name
        path.write_bytes(b"opaque unscreened transport fixture")
        hashes[name] = file_digest(path)
    manifest = {"schema_version": "1.1.0", "stage_identity": "fine_stage_fixture", "method_versions": {"features": "fixture", "selection": "fixture"},
                "cells": 10000, "scored_alternatives": 18000, "alternatives": 20000, "unscored_alternatives": 2000,
                "cell_size_m": 1000, "grid_definition_id": catalog["grid_definition_id"], "data_mode": "real",
                "source_checksums": meta.get("source_checksums", {}), "output_hashes": hashes}
    path = surface / "fine_surface_manifest.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    record = {"manifest": "national_fine_surface/fine_surface_manifest.json", "manifest_sha256": file_digest(path),
              "stage_identity": "fine_stage_fixture", "method_versions": manifest["method_versions"], "valued_cells": 10000,
              "scored_alternatives": 18000, "ranked_parent_windows": 10, "selection_limit": 1,
              "facility_score": 100, "best_fine_score": 100}
    catalog.update(schema_version="1.2.0", selection="national_fine_surface", national_fine_surface=record,
                   coverage_warning="The surface applies no screening; unselected parents are unrefined.")
    (folder / "regional_catalog.json").write_text(json.dumps(catalog), encoding="utf-8")
    meta.setdefault("output_hashes", {})[record["manifest"]] = file_digest(path)
    (folder / "run_metadata.json").write_text(json.dumps(meta), encoding="utf-8")
    return catalog


def test_fine_surface_summary_never_becomes_screened_counts_or_facility_scores(regional, tmp_path, monkeypatch):
    catalog = add_surface(regional)
    reader = ArtifactReader(tmp_path / "responses")
    original = reader.table
    def no_surface_tables(folder, *args, **kwargs):
        assert folder.name != "national_fine_surface"
        return original(folder, *args, **kwargs)
    monkeypatch.setattr(reader, "table", no_surface_tables)
    result = reader.run(regional)
    assert result["schema_version"] == "1.8.0"
    assert result["analyzed_cell_count"] == 42
    assert result["analysis"]["selection"] == "national_fine_surface"
    assert result["analysis"]["coverage_warning"] == catalog["coverage_warning"]
    surface = result["analysis"]["national_fine_surface"]
    assert surface["screening_status"] == "UNSCREENED" and surface["valued_cells"] == 10000
    assert surface["scored_alternatives"] == 18000 and surface["unscored_alternatives"] == 2000
    assert "facility_score" not in surface and "best_fine_score" not in surface
    assert "UNSCREENED" in result["scope"] and "42" in result["scope"]
    assert "of 690 shortlisted" not in result["scope"]
    assert all(region["overall_score"] != 100 for region in result["regions"])


def test_removed_fine_surface_artifact_rejects_warm_response(regional, tmp_path):
    add_surface(regional)
    reader = ArtifactReader(tmp_path / "responses")
    reader.run_bytes(regional)
    (regional / "national_fine_surface/fine_surface_cells.parquet").unlink()
    with pytest.raises(ApiError, match="missing required result artifacts"):
        reader.run_bytes(regional)


@pytest.mark.parametrize("finished", [False, True])
def test_phase11_is_default_only_after_complete_native_delivery(tmp_path, monkeypatch, finished):
    for name, complete in (("cleanview_regional_v2", True), ("national_fine_regional_v1", finished)):
        folder = tmp_path / "runs" / name
        folder.mkdir(parents=True)
        shutil.copy2(ACCEPTED / "config_snapshot.json", folder / "config_snapshot.json")
        meta = {"run_id": name, "scope": {"data_mode": "real", "scope": "regional_refinement"},
                "configuration": {"study_area": "regional_refinement"}, "completed_current_stages": list(STAGES) if complete else ["rank", "validate"]}
        (folder / "run_metadata.json").write_text(json.dumps(meta), encoding="utf-8")
        catalog = {"analysis_level": "regional", "grid_definition_id": "transport_fixture", "cell_size_m": 1000, "parts": []}
        (folder / "regional_catalog.json").write_text(json.dumps(catalog), encoding="utf-8")
        if name == "national_fine_regional_v1":
            add_surface(folder)
    service = LocatorService(tmp_path, start_worker=False)
    expected = "national_fine_regional_v1" if finished else "cleanview_regional_v2"
    assert service.latest_run_id() == expected
    assert service._regional_baseline() == tmp_path / "runs" / expected
    assert service.capabilities()["latest_run_id"] == expected
    assert service.resolve_run("cleanview_regional_v2") == tmp_path / "runs/cleanview_regional_v2"


def test_region_mode_scope_names_the_per_region_choice(regional, tmp_path):
    catalog = add_surface(regional)
    (regional / "regional_catalog.json").write_text(json.dumps({**catalog, "selection": "national_fine_region_parents"}), encoding="utf-8")
    result = ArtifactReader(tmp_path / "responses").run(regional)
    assert result["analysis"]["selection"] == "national_fine_region_parents"
    assert result["analysis"]["national_fine_surface"]["screening_status"] == "UNSCREENED"
    assert "the best fine-surface parent of each national region" in result["scope"]
    assert "ranked parent windows" not in result["scope"]


@pytest.mark.parametrize("region_run", ["national_fine_region_v1", "national_fine_region_v2"])
@pytest.mark.parametrize("finished", [False, True])
def test_region_mode_run_is_default_only_after_complete_native_delivery(tmp_path, finished, region_run):
    for name, complete, selection in (("national_fine_regional_v1", True, "national_fine_surface"),
                                      (region_run, finished, "national_fine_region_parents")):
        folder = tmp_path / "runs" / name
        folder.mkdir(parents=True)
        shutil.copy2(ACCEPTED / "config_snapshot.json", folder / "config_snapshot.json")
        meta = {"run_id": name, "scope": {"data_mode": "real", "scope": "regional_refinement"},
                "configuration": {"study_area": "regional_refinement"}, "completed_current_stages": list(STAGES) if complete else ["rank", "validate"]}
        (folder / "run_metadata.json").write_text(json.dumps(meta), encoding="utf-8")
        catalog = {"analysis_level": "regional", "grid_definition_id": "transport_fixture", "cell_size_m": 1000, "parts": []}
        (folder / "regional_catalog.json").write_text(json.dumps(catalog), encoding="utf-8")
        catalog = add_surface(folder)
        (folder / "regional_catalog.json").write_text(json.dumps({**catalog, "selection": selection}), encoding="utf-8")
    service = LocatorService(tmp_path, start_worker=False)
    expected = region_run if finished else "national_fine_regional_v1"
    assert service.latest_run_id() == expected
    assert service._regional_baseline() == tmp_path / "runs" / expected
    assert service.resolve_run("national_fine_regional_v1") == tmp_path / "runs/national_fine_regional_v1"
