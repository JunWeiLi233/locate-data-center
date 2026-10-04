"""Saved nationwide map choices are transport fixtures, never new model runs."""
import hashlib
import json
import shutil

import pytest

from frontend.server.service import LocatorService, STAGES
from frontend.server_tests.test_fine_surface_bridge import add_surface
from frontend.server_tests.test_regional_bridge import ACCEPTED, regional


def emit(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def saved_region(root, fixture, name, selection="representative_parent_cells", *, completed=True):
    folder = root / "runs" / name
    shutil.copytree(fixture, folder)
    meta = json.loads((folder / "run_metadata.json").read_text(encoding="utf-8"))
    parent = folder / "national_discovery"
    emit(parent / "run_metadata.json", {"run_id": name + "_parent", "stage_identity": "parent_transport_fixture",
         "scope": {"data_mode": "real", "scope": "conus", "national_model_supported": True},
         "completed_current_stages": list(STAGES)})
    meta.update(run_id=name, data_mode="real", scope={"data_mode": "real", "scope": "regional_refinement"},
                completed_current_stages=list(STAGES) if completed else ["rank", "validate"])
    emit(folder / "run_metadata.json", meta)
    if selection in {"national_fine_surface", "national_fine_region_parents"}:
        add_surface(folder)
    catalog = json.loads((folder / "regional_catalog.json").read_text(encoding="utf-8"))
    catalog.update(selection=selection, parent_run_path=parent.relative_to(root).as_posix(),
                   parent_run_id=name + "_parent", parent_stage_identity="parent_transport_fixture")
    emit(folder / "regional_catalog.json", catalog)
    meta = json.loads((folder / "run_metadata.json").read_text(encoding="utf-8"))
    meta["output_hashes"] = {p.relative_to(folder).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                             for p in folder.rglob("*") if p.is_file() and p.name != "run_metadata.json"}
    emit(folder / "run_metadata.json", meta)
    return folder


def evidence(folder):
    return {str(p.relative_to(folder)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in folder.rglob("*") if p.is_file()}


def test_nationwide_map_uses_latest_broad_saved_result_without_changing_scientific_default(tmp_path, regional):
    old = saved_region(tmp_path, regional, "regional_refinement_v4")
    broad = saved_region(tmp_path, regional, "cleanview_regional_v2")
    concentrated = saved_region(tmp_path, regional, "national_fine_regional_v1", "national_fine_surface")
    original = {p: evidence(p) for p in [old, broad, concentrated]}
    service = LocatorService(tmp_path, start_worker=False)
    result = service.capabilities()
    assert result["nationwide_regional_run_id"] == "cleanview_regional_v2"
    assert result["latest_run_id"] == "national_fine_regional_v1"
    assert service._regional_baseline() == concentrated
    assert result["schema_version"] == "1.8.0"
    assert {p: evidence(p) for p in original} == original


def test_completed_per_region_fine_selection_is_preferred_to_representatives(tmp_path, regional):
    saved_region(tmp_path, regional, "cleanview_regional_v2")
    fine = saved_region(tmp_path, regional, "national_fine_region_v1", "national_fine_region_parents")
    service = LocatorService(tmp_path, start_worker=False)
    assert service.capabilities()["nationwide_regional_run_id"] == "national_fine_region_v1"
    assert service.resolve_run("national_fine_region_v1") == fine


@pytest.mark.parametrize("selection", ["national_fine_surface", "manually_chosen_cities"])
def test_nationwide_map_never_labels_global_top_or_unknown_selection_as_broad(tmp_path, regional, selection):
    saved_region(tmp_path, regional, "cleanview_regional_v2", selection)
    service = LocatorService(tmp_path, start_worker=False)
    assert service.capabilities()["nationwide_regional_run_id"] is None


@pytest.mark.parametrize("damage", ["incomplete", "synthetic", "coarse", "oversized", "missing_native",
                                   "catalog_hash", "parent_partial", "parent_identity"])
def test_unusable_registered_broad_output_is_excluded(tmp_path, regional, damage):
    folder = saved_region(tmp_path, regional, "cleanview_regional_v2")
    saved_region(tmp_path, regional, "national_fine_regional_v1", "national_fine_surface")
    service = LocatorService(tmp_path, start_worker=False)
    meta = json.loads((folder / "run_metadata.json").read_text(encoding="utf-8"))
    catalog = json.loads((folder / "regional_catalog.json").read_text(encoding="utf-8"))
    if damage == "incomplete":
        meta["completed_current_stages"] = ["validate"]
    elif damage == "synthetic":
        meta["scope"]["data_mode"] = "synthetic"
    elif damage == "coarse":
        catalog["cell_size_m"] = 50000
    elif damage == "oversized":
        catalog["maximum_region_extent_km"] = 21
    elif damage == "missing_native":
        (folder / "parts/parent_fixture/site_performance.parquet").unlink()
    elif damage == "catalog_hash":
        catalog["refined_cells"] = 999999
    elif damage == "parent_partial":
        parent = folder / "national_discovery/run_metadata.json"
        data = json.loads(parent.read_text(encoding="utf-8"))
        data["completed_current_stages"] = ["validate"]
        emit(parent, data)
    elif damage == "parent_identity":
        catalog["parent_run_id"] = "different_parent"
    emit(folder / "regional_catalog.json", catalog)
    if damage != "catalog_hash":
        meta["output_hashes"]["regional_catalog.json"] = hashlib.sha256((folder / "regional_catalog.json").read_bytes()).hexdigest()
    emit(folder / "run_metadata.json", meta)
    assert service.capabilities()["nationwide_regional_run_id"] is None


def test_capabilities_registers_new_external_result_only_after_full_completion(tmp_path, regional):
    saved_region(tmp_path, regional, "cleanview_regional_v2")
    saved_region(tmp_path, regional, "national_fine_regional_v1", "national_fine_surface")
    future = saved_region(tmp_path, regional, "national_fine_region_v1", "national_fine_region_parents", completed=False)
    service = LocatorService(tmp_path, start_worker=False)
    before = service.latest_run_id()
    assert service.capabilities()["nationwide_regional_run_id"] == "cleanview_regional_v2"
    assert service.latest_run_id() == before and "national_fine_region_v1" not in service.runs
    meta = json.loads((future / "run_metadata.json").read_text(encoding="utf-8"))
    meta["completed_current_stages"] = list(STAGES)
    emit(future / "run_metadata.json", meta)
    assert service.capabilities()["nationwide_regional_run_id"] == "national_fine_region_v1"
    assert service.resolve_run("national_fine_region_v1") == future
    # A later saved user search retains registry ordering across subsequent refreshes.
    with service.lock:
        service.runs["later_user_search"] = service.runs[before]
    assert service.capabilities()["latest_run_id"] == "later_user_search"


def test_refresh_preserves_explicit_later_search_after_completed_baseline_is_removed(tmp_path, regional):
    saved_region(tmp_path, regional, "cleanview_regional_v2")
    service = LocatorService(tmp_path, start_worker=False)
    service.runs.pop("cleanview_regional_v2")
    later = tmp_path / "runs/explicit_legacy_search"
    emit(later / "run_metadata.json", {"run_id": "explicit_legacy_search",
         "scope": {"data_mode": "real", "scope": "development"}, "completed_current_stages": list(STAGES)})
    shutil.copy2(ACCEPTED / "config_snapshot.json", later / "config_snapshot.json")
    service.register_run(later)
    original_order = list(service.runs)
    result = service.capabilities()
    assert result["latest_run_id"] == "explicit_legacy_search"
    assert result["nationwide_regional_run_id"] is None
    assert list(service.runs) == original_order
    assert "cleanview_regional_v2" not in service.runs


def test_refresh_does_not_promote_a_complete_claim_with_missing_native_artifacts(tmp_path, regional):
    saved_region(tmp_path, regional, "cleanview_regional_v2")
    future = saved_region(tmp_path, regional, "national_fine_region_v1", "national_fine_region_parents", completed=False)
    service = LocatorService(tmp_path, start_worker=False)
    before = service.latest_run_id()
    meta = json.loads((future / "run_metadata.json").read_text(encoding="utf-8"))
    meta["completed_current_stages"] = list(STAGES)
    emit(future / "run_metadata.json", meta)
    (future / "candidate_regions.parquet").unlink()
    assert service.capabilities()["nationwide_regional_run_id"] == "cleanview_regional_v2"
    assert service.latest_run_id() == before and "national_fine_region_v1" not in service.runs
