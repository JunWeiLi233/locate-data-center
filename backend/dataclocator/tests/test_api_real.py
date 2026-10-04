"""Stage 3 frozen official-data HTTP parity checks without live network access."""

import json
from pathlib import Path
import socket
import time

from fastapi.testclient import TestClient
import pytest

from dataclocator.api import create_app
from dataclocator.experiments import run_experiment
from dataclocator.simulation import simulate
from offline_inputs import mount_offline_inputs

ROOT = Path(__file__).resolve().parents[1]
pytestmark = pytest.mark.skipif(not (ROOT / "data/processed/grid_regions.parquet").exists(), reason="acquire/preprocess required")


def test_real_offline_http_model_parity(tmp_path, monkeypatch):
    """Execute 45 actual counties through HTTP and compare exact pure/CLI results."""
    def no_live_network(*args, **kwargs):
        """Any attempted network connection is a failure, not a fallback data source."""
        raise AssertionError("Frozen HTTP run attempted a live network connection")
    monkeypatch.setattr(socket, "create_connection", no_live_network)
    mount_offline_inputs(ROOT, tmp_path)
    config = json.loads((ROOT / "configs/monte-carlo-smoke.json").read_text())
    config.update(simulation_count=32, analysis_horizon_years=3, bootstrap_resamples=20)
    request = {"config": config, "options": {"sensitivity": False, "convergence": False}}
    with TestClient(create_app(tmp_path)) as client:
        submitted = client.post("/runs", json=request)
        assert submitted.status_code == 202
        run_id = submitted.json()["run_id"]
        deadline = time.monotonic() + 40
        while time.monotonic() < deadline:
            record = client.get(f"/runs/{run_id}").json()
            if record["status"] in {"failed", "completed"}:
                break
            time.sleep(.05)
        assert record["status"] == "completed", record.get("error")
        result = record["result"]
        evidence = json.loads((tmp_path / "outputs" / run_id / "candidate_evidence.json").read_text())
        pure = simulate(config, evidence["candidates"])
        assert result["scenarios"] == pure["scenarios"]
        assert len(result["scenarios"][0]["candidates"]) == 45
        # Unused live FEMA item counters are excluded; all 19 scientific source pins remain.
        assert len(result["dataset_hashes"]) == 19
        assert run_experiment(tmp_path, config, with_sensitivity=False, with_convergence=False) == result
        assert client.post("/runs", json=request).status_code == 200
        detail = client.get(f"/runs/{run_id}/candidates/01089").json()
        assert detail["evidence"]["county_fips"] == "01089"
        assert detail["scenarios"][0]["outcome"]["objectives"]
        # The complete typed request and stable polling envelope must be in OpenAPI.
        schema = client.get("/openapi.json").json()
        assert len([path for path in schema["paths"]]) == 6
        assert set(schema["components"]["schemas"]["RunConfig"]["required"]) == set(config)
        json.dumps(record, allow_nan=False)
        # Verified mode legitimately completes with no suitable evidence-backed counties.
        request["config"]["feasibility_mode"] = "verified"
        verified_id = client.post("/runs", json=request).json()["run_id"]
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            verified = client.get(f"/runs/{verified_id}").json()
            if verified["status"] in {"completed", "failed"}:
                break
            time.sleep(.05)
        assert verified["status"] == "completed"
        assert verified["result"]["status"] == "no_eligible_candidates"
        assert len(verified["result"]["excluded_candidates"]) == 45
        excluded = client.get(f"/runs/{verified_id}/candidates/01089").json()
        assert len(excluded["exclusion_reasons"]) == 4
        assert excluded["scenarios"] == []
