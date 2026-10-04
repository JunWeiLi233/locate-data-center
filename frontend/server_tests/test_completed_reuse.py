"""Exact completed-run reuse using small transport fixtures, never model execution."""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
import yaml

from dc_locator.geography.sources.ingestion import file_digest
from dc_locator.pipeline import digest_json, environment_identity
from dc_locator.run_config import load_delivery_config
from frontend.server.serialization import ApiError, snapshot_configuration
from frontend.server.service import GROUPS, STAGES, LocatorService

ROOT = Path(__file__).resolve().parents[2]


def emit(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


@pytest.fixture
def completed(tmp_path, request):
    """Checksummed opaque files stand in for artifacts; no geographic facts are invented."""
    folder = tmp_path / getattr(request, "param", "runs/regional_refinement_v4")
    parent = folder / "national_discovery"
    configs = tmp_path / "configs"
    configs.mkdir()
    wrapper_name = {"national_fine_regional_v1": "run_regional_fine_surface.yaml",
                    "national_fine_region_v1": "run_regional_fine_region.yaml"}.get(folder.name, "run_regional_exploratory.yaml")
    fine = wrapper_name != "run_regional_exploratory.yaml"
    wrapper = yaml.safe_load((ROOT / "configs" / wrapper_name).read_text(encoding="utf-8"))
    document = yaml.safe_load((ROOT / wrapper["parent_config"]).read_text(encoding="utf-8"))
    for field in ("grid_config", "source_registry", "core_source_inputs", "facility", "cooling_designs", "physical_scenarios", "constraints", "scoring_profile"):
        path = configs / Path(document[field]).name
        path.write_bytes((ROOT / document[field]).read_bytes())
        document[field] = path.relative_to(tmp_path).as_posix()
    grid = tmp_path / "runs/national_grid_v1/us_grid.parquet"
    grid.parent.mkdir(parents=True)
    grid.write_bytes(b"opaque transport grid fixture")
    document["grid_path"] = grid.relative_to(tmp_path).as_posix()
    for name in ("grid_regional.yaml", "scoring_profile_regional.yaml"):
        (configs / name).write_bytes((ROOT / "configs" / name).read_bytes())
    source = tmp_path / "data/raw/fixture.bin"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"opaque checksum fixture")
    source_directory = tmp_path / "data/raw/fixture_directory"
    source_directory.mkdir()
    (source_directory / "member.bin").write_bytes(b"opaque directory member")
    sources = {}
    records = []
    for path in (source, source_directory):
        sources[str(path)] = file_digest(path)
        size = sum(p.stat().st_size for p in path.rglob("*") if p.is_file()) if path.is_dir() else path.stat().st_size
        records.append({"path": str(path), "sha256": sources[str(path)], "bytes": size})
    source_config = configs / "local_national_sources.json"
    emit(source_config, {"files": records})
    document["local_sources"] = source_config.relative_to(tmp_path).as_posix()
    template = configs / "run_national_exploratory.yaml"
    template.write_text(yaml.safe_dump(document), encoding="utf-8")
    wrapper_path = configs / wrapper_name
    wrapper_path.write_text(yaml.safe_dump(wrapper), encoding="utf-8")
    configuration = load_delivery_config(template).model_dump(mode="json")
    references = {template, grid, source_config}
    references.update(tmp_path / configuration[name] for name in ("grid_config", "source_registry", "core_source_inputs", "facility", "cooling_designs", "physical_scenarios", "constraints", "scoring_profile"))
    hashes = {str(path): file_digest(path) for path in sorted(references)}
    code = tmp_path / "src/dc_locator/fixture.py"
    code.parent.mkdir(parents=True)
    code.write_bytes(b"# opaque transport identity fixture")
    models = {}
    for path in (code, tmp_path / "requirements.lock.txt", tmp_path / "pyproject.toml"):
        if path != code:
            path.write_bytes(b"opaque dependency identity fixture")
        models[str(path.relative_to(tmp_path))] = file_digest(path)
    environment = environment_identity()
    parent_identity = digest_json({"delivery_version": configuration["delivery_version"], "config": configuration,
                                   "config_hashes": hashes, "model_hashes": models, "source_hashes": sources,
                                   "grid_sha256": file_digest(grid), "environment": environment})
    parent_meta = {"run_id": "transport_parent__" + parent_identity[:16], "stage_identity": parent_identity,
                   "configuration": configuration, "config_hashes": hashes, "actual_working_code_sha256": models,
                   "source_checksums": sources, "environment": environment,
                   "scope": {"data_mode": "real", "scope": "conus"}, "completed_current_stages": list(STAGES)}
    emit(parent / "run_metadata.json", parent_meta)
    binding = {"config": wrapper, "parent_identity": parent_identity, "wrapper_sha256": file_digest(wrapper_path),
               "grid_config_sha256": file_digest(tmp_path / wrapper["grid_config"]),
               "profile_sha256": file_digest(tmp_path / wrapper["scoring_profile"]),
               "profile_fingerprint": "opaque transport profile fixture"}
    emit(folder / "regional_binding.json", binding)
    child = dict(configuration, study_area="regional_refinement", grid_config=wrapper["grid_config"],
                 grid_path=str(folder / "us_grid_dataset.parquet"), scoring_profile=wrapper["scoring_profile"])
    texts = {str(path): path.read_text(encoding="utf-8") for path in references if path.suffix in {".yaml", ".json"}}
    emit(folder / "config_snapshot.json", {"run": child, "files": texts})
    emit(folder / "profile_snapshot.json", {"groups": [{"group_id": group, "equal_parent_weight": .25} for group in GROUPS]})
    emit(folder / "regional_catalog.json", {"schema_version": "1.0.0", "analysis_level": "regional", "parts": [],
         "parent_run_path": parent.relative_to(tmp_path).as_posix(), "parent_run_id": parent_meta["run_id"],
         "parent_stage_identity": parent_identity, "parent_output_hashes": {}})
    for name in ("ranked_cells.parquet", "candidate_regions.parquet", "region_membership.parquet", "parts/example/evidence.bin"):
        path = folder / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"opaque checksummed artifact")
    identity = digest_json(binding)
    meta = {"run_id": "regional_refinement__" + identity[:16], "stage_identity": identity,
            "scope": {"data_mode": "real", "scope": "regional_refinement"}, "completed_current_stages": list(STAGES),
            "configuration": child, "source_checksums": sources, "actual_working_code_sha256": models, "environment": environment,
            "config_hashes": {**hashes, **{str(path): file_digest(path) for path in
                             (wrapper_path, tmp_path / wrapper["grid_config"], tmp_path / wrapper["scoring_profile"])}}}
    if fine:
        from dc_locator.fine_surface import stage_identity
        fine_folder = folder / "national_fine_surface"
        outputs = {}
        for name in ("fine_surface_cells.parquet", "fine_surface_parents.parquet", "feature_provenance.parquet"):
            path = fine_folder / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"opaque unscreened surface fixture")
            outputs[name] = file_digest(path)
        manifest = {"schema_version": "1.1.0", "stage_identity": digest_json(stage_identity(identity)),
                    "method_versions": stage_identity(identity), "data_mode": "real", "cell_size_m": 1000,
                    "grid_definition_id": "fine_transport_fixture", "source_checksums": sources,
                    "cells": 10000, "scored_alternatives": 18000, "alternatives": 20000,
                    "unscored_alternatives": 2000, "output_hashes": outputs}
        emit(fine_folder / "fine_surface_manifest.json", manifest)
        catalog = json.loads((folder / "regional_catalog.json").read_text(encoding="utf-8"))
        catalog.update(schema_version="1.2.0", selection=wrapper["selection"], grid_definition_id="fine_transport_fixture",
                       cell_size_m=1000, refined_cells=42, refined_parent_cells=1, coverage_warning="The surface applies no screening; refined coverage is partial.",
                       national_fine_surface={"manifest": "national_fine_surface/fine_surface_manifest.json",
                         "manifest_sha256": file_digest(fine_folder / "fine_surface_manifest.json"),
                         "stage_identity": manifest["stage_identity"], "method_versions": manifest["method_versions"],
                         "valued_cells": manifest["cells"], "scored_alternatives": manifest["scored_alternatives"],
                         "ranked_parent_windows": 4, "selection_limit": 1})
        emit(folder / "regional_catalog.json", catalog)
    meta["output_hashes"] = {p.relative_to(folder).as_posix(): file_digest(p) for p in folder.rglob("*") if p.is_file() and p.name != "run_metadata.json"}
    emit(folder / "run_metadata.json", meta)
    service = LocatorService(tmp_path, start_worker=False)
    return service, folder, snapshot_configuration(folder)


@pytest.mark.parametrize("completed", ["runs/regional_refinement_v4", "runs/cleanview_regional_v2", "runs/national_fine_regional_v1",
                                       "runs/national_fine_region_v1"], indirect=True)
def test_identical_default_search_reuses_verified_completed_run_without_configuration_or_pipeline(completed, monkeypatch):
    service, folder, facility = completed
    observed = []
    monkeypatch.setattr(service, "_write_configuration", lambda *args: pytest.fail("An identical completed facility was regenerated"))
    monkeypatch.setattr(service, "run_response", lambda identifier: observed.append(identifier) or b'{"schema_version":"1.4.0"}')
    job = service.search({"facility": facility})["job_id"]
    original = (folder / "run_metadata.json").read_bytes()
    service._execute_job(job)
    assert service.job(job)["state"] == "COMPLETE"
    assert service.job(job)["stage"] == "reused verified completed run"
    assert observed == [service.job(job)["run_id"]]
    assert service.resolve_run(observed[0]) == folder
    assert (folder / "run_metadata.json").read_bytes() == original


@pytest.mark.parametrize("completed", ["runs/national_fine_regional_v1", "runs/national_fine_region_v1"], indirect=True)
def test_phase11_new_requests_keep_selected_fine_surface_wrapper(completed):
    service, folder, _ = completed
    parent = service.owned / "configurations/request/run.yaml"
    parent.parent.mkdir(parents=True)
    parent.write_bytes(b"opaque customized parent")
    written = service._write_regional_configuration(parent)
    wrapper = yaml.safe_load(written.read_text(encoding="utf-8"))
    assert wrapper["selection"] == {"national_fine_regional_v1": "national_fine_surface",
                                    "national_fine_region_v1": "national_fine_region_parents"}[folder.name]
    assert wrapper["delivery_version"] == "phase11_national_fine_surface_v1"
    assert wrapper["parent_config"] == parent.relative_to(service.root).as_posix()
    assert wrapper["maximum_region_extent_km"] == 20


@pytest.mark.parametrize("completed", ["runs/national_fine_regional_v1", "runs/national_fine_region_v1"], indirect=True)
def test_completed_phase11_takes_priority_over_a_saved_representative_mode(completed):
    service, folder, _ = completed
    old = service.owned / "regional_runs/old_mode"
    emit(old / "run_metadata.json", {"run_id": "OLD_MODE", "scope": {"data_mode": "real", "scope": "regional_refinement"},
                                    "completed_current_stages": list(STAGES)})
    emit(old / "regional_catalog.json", {"analysis_level": "regional", "selection": "representative_parent_cells", "parts": []})
    emit(service.registry_path, {"runs": {"OLD_MODE": old.relative_to(service.root).as_posix()}, "jobs": {}})
    restarted = LocatorService(service.root, start_worker=False)
    expected = json.loads((folder / "run_metadata.json").read_text(encoding="utf-8"))["run_id"]
    assert restarted.latest_run_id() == expected
    assert restarted.resolve_run("OLD_MODE") == old


@pytest.mark.parametrize("completed", ["runs/national_fine_regional_v1", "runs/national_fine_region_v1"], indirect=True)
@pytest.mark.parametrize("damage", ["manifest", "surface_table"])
def test_phase11_reuse_rechecks_fine_stage_content(completed, damage):
    service, folder, facility = completed
    name = "fine_surface_manifest.json" if damage == "manifest" else "fine_surface_cells.parquet"
    path = folder / "national_fine_surface" / name
    stat = path.stat()
    content = path.read_bytes()
    path.write_bytes(bytes([content[0] ^ 1]) + content[1:])
    os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns))
    with pytest.raises(ApiError) as error:
        service._completed_default_run(facility)
    assert error.value.code == "completed_run_checksum_mismatch"


@pytest.mark.parametrize("field,value", [("peak_it_power_mw", 101), ("cooling", "air_dry_assumed"), ("weighting", "user"),
                                          ("screening_mode", "STRICT"), ("group_weights", dict.fromkeys(GROUPS, .3))])
def test_changed_facility_or_preferences_do_not_reuse_completed_default(completed, field, value):
    service, _, facility = completed
    facility[field] = value
    path, reason = service._completed_default_run(facility)
    assert path is None and "facility or preferences differ" in reason


@pytest.mark.parametrize("kind", ["model", "added_model", "config", "source", "source_directory", "environment"])
def test_changed_native_identity_falls_through_with_reason_even_with_same_size_and_mtime(completed, kind, monkeypatch):
    service, folder, facility = completed
    import dc_locator.pipeline as pipeline
    meta = json.loads((folder / "run_metadata.json").read_text(encoding="utf-8"))
    if kind == "environment":
        monkeypatch.setattr(pipeline, "environment_identity", lambda: {"different": True})
    elif kind == "added_model":
        (service.root / "src/dc_locator/added.py").write_bytes(b"# new model file")
    else:
        paths = {"model": service.root / "src/dc_locator/fixture.py", "config": service.root / "configs/grid_regional.yaml",
                 "source": Path(next(iter(meta["source_checksums"]))),
                 "source_directory": service.root / "data/raw/fixture_directory/member.bin"}
        path = paths[kind]
        stat = path.stat()
        content = path.read_bytes()
        path.write_bytes(bytes([content[0] ^ 1]) + content[1:])
        os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns))
    path, reason = service._completed_default_run(facility)
    assert path is None and "differs" in reason


@pytest.mark.parametrize("damage", ["changed", "missing", "unlisted", "escaped"])
def test_damaged_completed_artifact_never_reuses_or_regenerates_silently(completed, damage):
    service, folder, facility = completed
    artifact = folder / "parts/example/evidence.bin"
    if damage == "changed":
        stat = artifact.stat()
        content = artifact.read_bytes()
        artifact.write_bytes(b"X" + content[1:])
        os.utime(artifact, ns=(stat.st_atime_ns, stat.st_mtime_ns))
    elif damage == "missing":
        artifact.unlink()
    else:
        meta = json.loads((folder / "run_metadata.json").read_text(encoding="utf-8"))
        if damage == "unlisted":
            meta["output_hashes"].pop("parts/example/evidence.bin")
        else:
            escaped = folder.parent / "outside.bin"
            escaped.write_bytes(b"outside output")
            meta["output_hashes"]["../outside.bin"] = file_digest(escaped)
        emit(folder / "run_metadata.json", meta)
    with pytest.raises(ApiError) as error:
        service._completed_default_run(facility)
    assert error.value.code == "completed_run_checksum_mismatch"


def test_reuse_job_is_not_complete_when_adapter_rejects_result(completed, monkeypatch):
    service, _, facility = completed
    monkeypatch.setattr(service, "run_response", lambda *args: (_ for _ in ()).throw(ApiError("incompatible transport", 422)))
    job = service.search({"facility": facility})["job_id"]
    with pytest.raises(ApiError, match="incompatible transport"):
        service._execute_job(job)
    assert service.job(job)["state"] != "COMPLETE" and service.job(job)["run_id"] is None


def test_run_response_resolves_registered_run_and_preserves_exact_wire_bytes_under_reader_lock(completed, monkeypatch):
    service, folder, _ = completed
    identifier = json.loads((folder / "run_metadata.json").read_text(encoding="utf-8"))["run_id"]
    payload = b'{"schema_version":"1.4.0","unknown":null}'
    calls = []
    class ObservedLock:
        held = False
        def __enter__(self):
            self.held = True
        def __exit__(self, *args):
            self.held = False
    lock = ObservedLock()
    service.reader_lock = lock
    def run_bytes(actual, scenario):
        assert lock.held
        calls.append((actual, scenario))
        return payload
    monkeypatch.setattr(service.reader, "run_bytes", run_bytes)
    assert service.run_response(identifier, "current") is payload
    assert calls == [(folder, "current")]
    with pytest.raises(ApiError) as error:
        service.run_response("missing")
    assert error.value.code == "run_not_found" and len(calls) == 1
