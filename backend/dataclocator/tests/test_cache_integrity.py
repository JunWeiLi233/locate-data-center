"""Synthetic cache corruption must not be accepted as frozen county evidence."""

import copy
import json
import shutil

import pytest
from fastapi.testclient import TestClient

from dataclocator.experiments import run_experiment
from dataclocator.jobs import JobStore
from dataclocator.api import create_app
from dataclocator.pipeline import write_json
from test_api_jobs import body, job_root, stub_result


@pytest.fixture
def completed_cache(job_root, body, monkeypatch):
    """Create real artifact orchestration with an empty synthetic model response."""
    def empty_simulation(config, candidates):
        """No geographic or model values are manufactured for this cache fixture."""
        return {"status": "no_eligible_candidates", "eligible": [], "excluded": [],
                "scenarios": [], "samples": {}, "shared_draws": {}, "annual_trajectories": []}
    monkeypatch.setattr("dataclocator.experiments.simulate", empty_simulation)
    result = run_experiment(job_root, body["config"], with_sensitivity=False, with_convergence=False)
    directory = job_root / "outputs" / result["run_id"]
    return job_root, body, result, directory


@pytest.mark.parametrize("mutation", [
    "run_id", "model_version", "config", "seed", "input_hashes", "dataset_hashes",
    "sources", "result_values", "identity", "config_file", "evidence",
    "missing_identity", "missing_evidence", "missing_draws",
])
def test_cli_rejects_corrupted_cache(completed_cache, mutation):
    """Reject identity/evidence corruption and damaged recorded output artifacts."""
    root, body, result, directory = completed_cache
    if mutation.startswith("missing_"):
        name = {"missing_identity": "run_identity.json", "missing_evidence": "candidate_evidence.json",
                "missing_draws": "common_draws.npz"}[mutation]
        (directory / name).unlink()
    elif mutation in {"identity", "config_file", "evidence"}:
        name = {"identity": "run_identity.json", "config_file": "config.json",
                "evidence": "candidate_evidence.json"}[mutation]
        value = json.loads((directory / name).read_text())
        if mutation == "identity":
            value["model_version"] = "stale-model"
        elif mutation == "config_file":
            value["seed"] += 1
        else:
            value["candidates"][0]["name"] = "Rebound evidence"
        write_json(directory / name, value)
    else:
        value = copy.deepcopy(result)
        if mutation == "config":
            value["config"]["seed"] += 1
        elif mutation == "seed":
            value["seed"] += 1
        elif mutation == "input_hashes":
            value["input_hashes"]["candidate_evidence"] = "0" * 64
        elif mutation == "dataset_hashes":
            value["dataset_hashes"] = {"fictional_source": "0" * 64}
        elif mutation == "sources":
            value["sources"] = [{"source_id": "fictional_source", "sha256": "0" * 64}]
        elif mutation == "result_values":
            value["scenarios"] = [{"candidate_id": "invented-result"}]
        else:
            value[mutation] = "run_" + "0" * 16 if mutation == "run_id" else "stale-model"
        write_json(directory / "results.json", value)
    # Invalid cache evidence must remain inspectable; no implicit migration repairs it.
    assert not (directory / "input_snapshot.json").exists()
    with pytest.raises(ValueError, match="cache"):
        run_experiment(root, body["config"], with_sensitivity=False, with_convergence=False)
    assert not (directory / "input_snapshot.json").exists()
    if mutation == "missing_evidence":
        assert not (directory / "candidate_evidence.json").exists()


def test_cli_rejects_results_copied_from_another_valid_run(completed_cache):
    """An otherwise valid response from a distinct seed cannot identify this run."""
    root, body, result, directory = completed_cache
    config = copy.deepcopy(body["config"])
    config["seed"] += 1
    other = run_experiment(root, config, with_sensitivity=False, with_convergence=False)
    assert other["run_id"] != result["run_id"]
    shutil.copyfile(root / "outputs" / other["run_id"] / "results.json", directory / "results.json")
    with pytest.raises(ValueError, match="cache"):
        run_experiment(root, body["config"], with_sensitivity=False, with_convergence=False)


def test_api_adoption_rejects_cache_before_rebinding_evidence(completed_cache):
    """A corrupt CLI cache cannot become a completed API job or gain a snapshot."""
    root, body, _, directory = completed_cache
    evidence_path = directory / "candidate_evidence.json"
    evidence = json.loads(evidence_path.read_text())
    evidence["candidates"][0]["name"] = "Corrupt frozen county"
    write_json(evidence_path, evidence)
    damaged_bytes = evidence_path.read_bytes()
    store = JobStore(root, [])
    store.start()
    try:
        with pytest.raises(ValueError, match="cache"):
            store.submit(body["config"], body["options"])
        assert not store.records
        assert not (directory / "input_snapshot.json").exists()
        assert evidence_path.read_bytes() == damaged_bytes
    finally:
        store.close()


def test_completed_job_poll_rejects_tampered_results(completed_cache):
    """Polling must expose a failed integrity state instead of stale success data."""
    root, body, result, directory = completed_cache
    store = JobStore(root, [])
    store.start()
    try:
        assert store.submit(body["config"], body["options"])["status"] == "completed"
        damaged = copy.deepcopy(result)
        damaged["run_id"] = "run_" + "0" * 16
        write_json(directory / "results.json", damaged)
        record = store.get(result["run_id"])
        assert record["status"] == "failed"
        assert record["error"]["code"] == "CACHE_INTEGRITY_FAILED"
        assert record["result"] is None
        assert record["cached"] is False
    finally:
        store.close()


def test_valid_cache_uses_historical_frozen_evidence(completed_cache, monkeypatch):
    """Legitimate immutable history survives changes to later preprocessing."""
    root, body, result, directory = completed_cache
    def simulation_forbidden(*args, **kwargs):
        """Validated cache reads must not repeat computation."""
        raise AssertionError("valid cache recomputed")
    monkeypatch.setattr("dataclocator.experiments.simulate", simulation_forbidden)
    assert run_experiment(root, body["config"], with_sensitivity=False, with_convergence=False) == result
    store = JobStore(root, [])
    store.start()
    try:
        assert store.submit(body["config"], body["options"])["cached"] is True
        changed = json.loads((root / "outputs/task2/candidates.json").read_text())
        changed["candidates"][0]["name"] = "New preprocessing"
        write_json(root / "outputs/task2/candidates.json", changed)
        assert store.get(result["run_id"])["result"] == result
        assert json.loads((directory / "candidate_evidence.json").read_text())["candidates"][0]["name"] == "Fixture only"
    finally:
        store.close()


def test_corrupt_cache_does_not_disable_unrelated_http_runs(completed_cache):
    """One damaged run returns a conflict while healthy datasets remain ready."""
    root, body, result, directory = completed_cache
    def injected_runner(root, config, **kwargs):
        """Return a contract-bound empty fixture without model computation."""
        return stub_result(kwargs["prepared"])
    with TestClient(create_app(root, runner=injected_runner)) as client:
        assert client.post("/runs", json=body).status_code == 200
        damaged = copy.deepcopy(result)
        damaged["run_id"] = "run_" + "0" * 16
        write_json(directory / "results.json", damaged)
        response = client.post("/runs", json=body)
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "CACHE_INTEGRITY_FAILED"
        assert client.get("/health").json()["ready"] is True
        other = copy.deepcopy(body)
        other["config"]["seed"] += 1
        assert client.post("/runs", json=other).status_code == 202
