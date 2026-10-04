"""Synthetic preprocessing lineage rejects stale official-input bindings."""

import hashlib
import json
import copy

from fastapi.testclient import TestClient
import pytest

from dataclocator.api import create_app
from dataclocator.experiments import prepare_run
from dataclocator.pipeline import PREPROCESS_MANIFEST, write_json, write_preprocess_manifest
from test_api_jobs import body, job_root


@pytest.mark.parametrize("mutation", ["missing", "malformed", "missing_coverage"])
def test_processed_damage_after_startup_marks_shared_inputs_unavailable(job_root, body, mutation):
    """Shared preprocessing damage disables readiness instead of reporting a run-cache error."""
    with TestClient(create_app(job_root)) as client:
        assert client.get("/health").json()["ready"] is True
        marker = job_root / PREPROCESS_MANIFEST
        if mutation == "missing":
            marker.unlink()
        elif mutation == "malformed":
            marker.write_text("{")
        else:
            (job_root / "outputs/task2/coverage.json").unlink()
        response = client.post("/runs", json=body)
        assert response.status_code == 503
        assert response.json()["error"]["code"] == "INPUTS_UNAVAILABLE"
        assert client.get("/health").status_code == 503


@pytest.mark.parametrize("mutation", ["missing", "model", "candidates", "grid", "coverage", "selection", "raw_repin"])
def test_prepare_rejects_missing_or_stale_processed_lineage(job_root, body, mutation):
    """A legitimate new raw checksum cannot silently authorize older processed data."""
    prepare_run(job_root, body["config"], with_sensitivity=False, with_convergence=False)
    marker = job_root / PREPROCESS_MANIFEST
    if mutation == "missing":
        marker.unlink()
    elif mutation == "model":
        record = json.loads(marker.read_text())
        record["model_version"] = "old-transformation"
        write_json(marker, record)
    elif mutation == "raw_repin":
        source = job_root / "data/raw/fixture/revised.txt"
        source.parent.mkdir(parents=True)
        source.write_bytes(b"legitimate revised synthetic source")
        write_json(job_root / "data/source_manifest.json", {"sources": [{
            "source_id": "synthetic_revised_source", "local_path": "data/raw/fixture/revised.txt",
            "sha256": hashlib.sha256(source.read_bytes()).hexdigest()}]})
    else:
        name = {"candidates": "outputs/task2/candidates.json", "grid": "data/processed/grid_regions.parquet",
                "coverage": "outputs/task2/coverage.json", "selection": "configs/candidates.json"}[mutation]
        with (job_root / name).open("ab") as stream:
            stream.write(b" ")
    with pytest.raises(ValueError):
        prepare_run(job_root, body["config"], with_sensitivity=False, with_convergence=False)
    with TestClient(create_app(job_root)) as client:
        assert client.get("/health").status_code == 503
        assert client.post("/runs", json=body).status_code == 503


@pytest.mark.parametrize("mutation", ["sources", "model_version"])
def test_candidate_embedded_lineage_cannot_be_rebound_by_file_checksums(job_root, body, mutation):
    """Even a newly recorded file checksum cannot disguise stale source semantics."""
    path = job_root / "outputs/task2/candidates.json"
    evidence = json.loads(path.read_text())
    evidence[mutation] = [{"source_id": "wrong_source", "sha256": "0" * 64}] if mutation == "sources" else "stale-model"
    write_json(path, evidence)
    write_preprocess_manifest(job_root, {"sources": []})
    with pytest.raises(ValueError, match="candidate evidence"):
        prepare_run(job_root, body["config"], with_sensitivity=False, with_convergence=False)


def test_source_metadata_must_match_exact_frozen_provenance(job_root, body):
    """Matching data hashes cannot authorize invented publisher/release/source records."""
    from dataclocator.cache import validate_frozen
    source_path = job_root / "data/raw/fixture/source.txt"
    source_path.parent.mkdir(parents=True)
    source_path.write_bytes(b"synthetic provenance test only")
    manifest = {"sources": [{"source_id": "fixture", "local_path": "data/raw/fixture/source.txt",
                              "publisher": "Synthetic fixture publisher",
                              "sha256": hashlib.sha256(source_path.read_bytes()).hexdigest()}]}
    write_json(job_root / "data/source_manifest.json", manifest)
    path = job_root / "outputs/task2/candidates.json"
    evidence = json.loads(path.read_text())
    evidence["sources"] = copy.deepcopy(manifest["sources"])
    write_json(path, evidence)
    write_preprocess_manifest(job_root, manifest)
    frozen = prepare_run(job_root, body["config"], with_sensitivity=False, with_convergence=False)
    frozen["evidence"]["sources"][0]["publisher"] = "Invented replacement publisher"
    with pytest.raises(ValueError, match="cache"):
        validate_frozen(frozen)
    write_json(path, frozen["evidence"])
    write_preprocess_manifest(job_root, manifest)
    with pytest.raises(ValueError, match="candidate evidence"):
        prepare_run(job_root, body["config"], with_sensitivity=False, with_convergence=False)
