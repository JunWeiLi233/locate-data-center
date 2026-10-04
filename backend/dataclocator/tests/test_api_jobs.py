"""Stage 2 queue/persistence tests; synthetic fixtures test behavior only."""

import copy
import hashlib
import json
from pathlib import Path
import threading
import time

from fastapi.testclient import TestClient
import pandas as pd
import pytest

from dataclocator.api import create_app
from dataclocator.jobs import JobStore
from dataclocator.pipeline import write_json
from dataclocator.pipeline import write_preprocess_manifest
from dataclocator import MODEL_VERSION

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def job_root(tmp_path):
    """Supply a labeled fictitious county only for orchestration, never screening."""
    write_json(tmp_path / "data/source_manifest.json", {"sources": []})
    evidence = {"model_version": MODEL_VERSION, "sources": [], "scope": "synthetic queue test only", "boundaries": [], "candidates": [{
        "candidate_id": "01089", "county_fips": "01089", "name": "Fixture only", "grid_region": "TEST",
        "electricity_price_usd_per_mwh": 50, "grid_co2e_kg_per_mwh": 400, "feasibility": {}, "coverage": {}}]}
    write_json(tmp_path / "outputs/task2/candidates.json", evidence)
    write_json(tmp_path / "outputs/task2/coverage.json", {"fixture_only": True})
    path = tmp_path / "data/processed/grid_regions.parquet"
    path.parent.mkdir(parents=True)
    pd.DataFrame([{"grid_region": "TEST", "grid_co2e_kg_per_mwh": 400}]).to_parquet(path)
    write_json(tmp_path / "configs/candidates.json", {"fixture_only": True})
    write_preprocess_manifest(tmp_path, {"sources": []})
    return tmp_path


@pytest.fixture
def body():
    """Disable expensive audits for lifecycle tests, retaining real config validation."""
    config = json.loads((ROOT / "configs/monte-carlo-smoke.json").read_text())
    return {"config": config, "options": {"sensitivity": False, "convergence": False}}


def stub_result(frozen):
    """Return a clearly empty fixture result compatible with candidate detail reads."""
    identity = frozen["identity"]
    return {"run_id": frozen["run_id"], "model_version": identity["model_version"],
            "config": identity["config"], "seed": identity["config"]["seed"],
            "input_hashes": identity["input_hashes"], "dataset_hashes": identity["dataset_hashes"],
            "sources": frozen["manifest"]["sources"], "scope": frozen["evidence"]["scope"],
            "status": "no_eligible_candidates", "scenarios": [],
            "objective_units": {}, "warnings": ["fixture only"], "boundary_exclusions": [],
            "excluded_candidates": [{"candidate_id": "01089", "reasons": ["fixture exclusion"]}]}


def wait_terminal(client, run_id):
    """Poll with a short deadline; fail clearly if a background job stalls."""
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        record = client.get(f"/runs/{run_id}").json()
        if record["status"] in {"completed", "failed"}:
            return record
        time.sleep(.01)
    pytest.fail("job did not reach a terminal state")


def test_dedup_queue_freezing_cache_and_restart(job_root, body):
    """Bound active+waiting jobs, deduplicate, freeze evidence and persist cache."""
    entered, release = threading.Event(), threading.Event()
    calls = []

    def controlled_runner(root, config, **kwargs):
        """Hold the worker so duplicate and full-queue behavior are deterministic."""
        calls.append(kwargs["prepared"])
        entered.set()
        assert release.wait(5)
        return stub_result(kwargs["prepared"])

    with TestClient(create_app(job_root, queue_size=1, runner=controlled_runner)) as client:
        try:
            response = client.post("/runs", json=body)
            assert response.status_code == 202
            first = response.json()["run_id"]
            assert entered.wait(2)
            assert client.get(f"/runs/{first}/candidates/01089").status_code == 409
            assert client.get(f"/runs/{first}/candidates/99999").status_code == 404
            assert client.post("/runs", json=body).json()["run_id"] == first
            second_body = copy.deepcopy(body)
            second_body["config"]["seed"] += 1
            second = client.post("/runs", json=second_body).json()["run_id"]
            third_body = copy.deepcopy(body)
            third_body["config"]["seed"] += 2
            assert client.post("/runs", json=third_body).json()["error"]["code"] == "QUEUE_FULL"
            assert client.get("/health").json()["queue"] == {"running": 1, "queued": 1}
            # A queued job must retain evidence captured before later preprocessing.
            path = job_root / "outputs/task2/candidates.json"
            changed = json.loads(path.read_text())
            changed["candidates"][0]["name"] = "Changed after submission"
            write_json(path, changed)
            release.set()
            assert wait_terminal(client, first)["status"] == "completed"
            assert wait_terminal(client, second)["status"] == "completed"
            detail = client.get(f"/runs/{second}/candidates/01089").json()
            assert detail["evidence"]["name"] == "Fixture only"
            assert detail["exclusion_reasons"] == ["fixture exclusion"]
            assert detail["scenarios"] == []
            # Restore the original hash to submit the identical cached request.
            changed["candidates"][0]["name"] = "Fixture only"
            write_json(path, changed)
            write_preprocess_manifest(job_root, {"sources": []})
            cached = client.post("/runs", json=body)
            assert cached.status_code == 200 and cached.json()["cached"] is True
            assert len(calls) == 2
        finally:
            release.set()
    with TestClient(create_app(job_root, runner=controlled_runner)) as client:
        assert client.get(f"/runs/{first}").json()["status"] == "completed"
        assert client.post("/runs", json=body).status_code == 200
        assert len(calls) == 2
        assert client.get("/runs/not-a-run").status_code == 404


def test_failure_retry_and_interrupted_recovery(job_root, body):
    """Sanitize model failures, allow retry and report crash-interrupted work."""
    attempts = []

    def failing_once(root, config, **kwargs):
        """Raise a sensitive-looking internal error once to test response redaction."""
        attempts.append(1)
        if len(attempts) == 1:
            raise RuntimeError("secret /private/internal/path")
        return stub_result(kwargs["prepared"])

    with TestClient(create_app(job_root, runner=failing_once)) as client:
        run_id = client.post("/runs", json=body).json()["run_id"]
        failed = wait_terminal(client, run_id)
        assert failed["error"]["code"] == "RUN_FAILED"
        assert "secret" not in json.dumps(failed)
        assert client.get(f"/runs/{run_id}/candidates/01089").status_code == 409
        assert client.post("/runs", json=body).status_code == 202
        assert wait_terminal(client, run_id)["status"] == "completed"
    path = job_root / "outputs/api-jobs" / f"{run_id}.json"
    interrupted = json.loads(path.read_text())
    interrupted["status"] = "running"
    write_json(path, interrupted)
    with TestClient(create_app(job_root, runner=failing_once)) as client:
        record = client.get(f"/runs/{run_id}").json()
        assert record["status"] == "failed"
        assert record["error"]["code"] == "RUN_INTERRUPTED"
        assert client.post("/runs", json=body).status_code == 200


def test_data_and_geographic_validation(job_root, body):
    """Reject unknown overrides before jobs exist and report unavailable inputs."""
    with TestClient(create_app(job_root)) as client:
        body["config"]["scenario_set"][0]["regional_overrides"] = {"UNKNOWN": {
            "price_growth": body["config"]["scenario_set"][0]["price_growth"]}}
        assert client.post("/runs", json=body).status_code == 422
        assert client.get("/health").json()["queue"] == {"running": 0, "queued": 0}
        (job_root / "data/processed/grid_regions.parquet").unlink()
        body["config"]["scenario_set"][0]["regional_overrides"] = {}
        assert client.post("/runs", json=body).status_code == 503
    with TestClient(create_app(job_root)) as client:
        assert client.post("/runs", json=body).status_code == 503


def test_exclusive_process_ownership(job_root):
    """Two processes/app instances must not overwrite each other's run metadata."""
    owner, other = JobStore(job_root, []), JobStore(job_root, [])
    owner.start()
    try:
        with pytest.raises(RuntimeError, match="API owner"):
            other.start()
    finally:
        owner.close()
    other.start()
    other.close()


def test_changed_source_checksums_block_new_jobs(job_root, body):
    """Detect frozen-source changes after startup instead of silently recomputing."""
    source = job_root / "data/raw/fixture/source.txt"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"original fixture only")
    manifest = {"sources": [{
        "source_id": "fixture_only", "local_path": "data/raw/fixture/source.txt",
        "sha256": hashlib.sha256(source.read_bytes()).hexdigest()}]}
    write_json(job_root / "data/source_manifest.json", manifest)
    evidence_path = job_root / "outputs/task2/candidates.json"
    evidence = json.loads(evidence_path.read_text())
    evidence["sources"] = manifest["sources"]
    write_json(evidence_path, evidence)
    write_preprocess_manifest(job_root, manifest)
    with TestClient(create_app(job_root)) as client:
        assert client.get("/health").status_code == 200
        source.write_bytes(b"tampered fixture")
        response = client.post("/runs", json=body)
        assert response.status_code == 503
        assert response.json()["error"]["code"] == "INPUTS_UNAVAILABLE"
        assert client.get("/health").status_code == 503
        assert str(job_root) not in json.dumps(response.json())
        assert client.get("/health").json()["queue"] == {"running": 0, "queued": 0}
