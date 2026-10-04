"""Fast API scheduling fixtures; no native model run is launched."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from frontend.server import service as module
from frontend.server.serialization import ApiError
from frontend.server.service import GROUPS, LocatorService


FACILITY = dict(peak_it_power_mw=100, average_load_percent=80, target_opening_year=2030,
               lifetime_years=25, cooling="all", weighting="equal", screening_mode="EXPLORATORY",
               group_weights=dict.fromkeys(GROUPS, .25), ahp_matrix=None)


@pytest.fixture
def fast_service(tmp_path, monkeypatch):
    service = LocatorService(tmp_path, start_worker=False)
    monkeypatch.setattr(module, "cached_cohort_status", lambda *args: dict(ready=True, available=True,
        reason=None, baseline_run_id="native_baseline", cohort_cells=152500, parent_windows=61), raising=False)
    monkeypatch.setattr(module, "fast_request_identity", lambda root, baseline, facility:
        hashlib.sha256(json.dumps(facility, sort_keys=True).encode()).hexdigest(), raising=False)
    return service


def request(facility=None, mode="cached_regional"):
    return {"facility": facility or FACILITY, "analysis_mode": mode}


def test_cached_requests_are_exactly_deduplicated_and_do_not_use_full_queue(fast_service):
    service = fast_service
    for _ in range(service.queue.maxsize):
        service.queue.put_nowait("unrelated_full_job")
    first = service.search(request())
    second = service.search(request())
    assert second["job_id"] == first["job_id"]
    assert service.fast_queue.qsize() == 1
    assert service.jobs[first["job_id"]]["analysis_mode"] == "cached_regional"
    changed = dict(FACILITY, peak_it_power_mw=101)
    assert service.search(request(changed))["job_id"] != first["job_id"]
    assert not (service.owned / "configurations").exists()


def test_omitted_and_explicit_full_mode_retain_legacy_queue(fast_service):
    service = fast_service
    service.search({"facility": FACILITY})
    service.search(request(mode="full_rediscovery"))
    assert service.queue.qsize() == 2
    assert service.fast_queue.qsize() == 0


@pytest.mark.parametrize("mode", [None, "fast", 1, {}, []])
def test_invalid_explicit_mode_fails_without_enqueue(fast_service, mode):
    with pytest.raises(ApiError, match="analysis_mode"):
        fast_service.search(request(mode=mode))
    assert not fast_service.jobs


def test_fast_unprepared_cache_is_explicit_and_does_not_build(fast_service, monkeypatch):
    monkeypatch.setattr(module, "cached_cohort_status", lambda *args: dict(ready=False, available=False,
        reason="Static native cache is not prepared"))
    with pytest.raises(ApiError, match="not prepared") as error:
        fast_service.search(request())
    assert error.value.code == "cached_regional_unavailable"
    assert not fast_service.jobs


def test_completed_fast_dedup_verifies_content_and_never_swallows_corruption(fast_service, monkeypatch):
    service = fast_service
    identifier = service.search(request())["job_id"]
    record = service.jobs[identifier]
    folder = Path(record["output_path"])
    folder.mkdir(parents=True)
    (folder / "run_metadata.json").write_text('{"run_id":"fresh_fast"}', encoding="utf-8")
    record.update(state="COMPLETE", run_id="fresh_fast")
    service.runs["fresh_fast"] = folder
    calls = []
    monkeypatch.setattr(module, "verify_fast_artifacts", lambda root, path: calls.append(path) or {"run_id": "fresh_fast", "stage_identity": record["request_identity"]}, raising=False)
    assert service.search(request())["job_id"] == identifier
    assert calls == [folder]
    monkeypatch.setattr(module, "verify_fast_artifacts", lambda *args: (_ for _ in ()).throw(
        ApiError("Fast artifact checksum mismatch", 422, "completed_run_checksum_mismatch")))
    with pytest.raises(ApiError, match="checksum mismatch"):
        service.search(request())
    assert len(service.jobs) == 1


def test_fast_completion_includes_materializing_response_before_complete(fast_service, monkeypatch):
    service = fast_service
    identifier = service.search(request())["job_id"]
    output = Path(service.jobs[identifier]["output_path"])
    observed = []
    def runner(facility, path):
        assert service.jobs[identifier]["state"] == "RUNNING"
        observed.append(("evaluate", facility, path))
        return path
    monkeypatch.setattr(service, "_invoke_fast_runner", runner, raising=False)
    monkeypatch.setattr(module, "verify_fast_artifacts", lambda *args: {"run_id": "fresh_fast", "stage_identity": service.jobs[identifier]["request_identity"]}, raising=False)
    monkeypatch.setattr(service, "register_run", lambda path: service.runs.update(fresh_fast=path))
    def materialize(run_id):
        assert service.jobs[identifier]["state"] == "RUNNING"
        assert run_id == "fresh_fast"
        observed.append(("materialize",))
        return b"{}"
    monkeypatch.setattr(service, "run_response", materialize)
    service._execute_fast_job(identifier)
    assert service.job(identifier)["state"] == "COMPLETE"
    assert [entry[0] for entry in observed] == ["evaluate", "materialize"]
    assert service.jobs[identifier]["evaluation_seconds"] >= 0
    assert service.jobs[identifier]["response_materialization_seconds"] >= 0
    assert service.queue.empty()


def test_completed_fast_folder_survives_pruned_job_history_without_enqueue(fast_service, monkeypatch):
    service = fast_service
    identity = module.fast_request_identity(service.root, service.root / "runs/cleanview_regional_v2", FACILITY)
    output = service.owned / "cached_regional_runs" / identity
    output.mkdir(parents=True)
    (output / "run_metadata.json").write_text('{"run_id":"fresh_fast"}', encoding="utf-8")
    monkeypatch.setattr(module, "verify_fast_artifacts", lambda *args: {"run_id": "fresh_fast", "stage_identity": identity})
    monkeypatch.setattr(service, "register_run", lambda path: service.runs.update(fresh_fast=path))
    reads = []
    monkeypatch.setattr(service, "run_response", lambda identifier: reads.append(identifier) or b"{}")
    identifier = service.search(request())["job_id"]
    assert service.job(identifier)["state"] == "COMPLETE"
    assert service.fast_queue.empty() and reads == ["fresh_fast"]
