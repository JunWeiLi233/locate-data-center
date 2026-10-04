"""Stage 1 HTTP contract checks using clearly identified temporary fixtures."""

import copy
import json
from pathlib import Path

from fastapi.testclient import TestClient
import pytest

from dataclocator.api import BODY_LIMIT, create_app
from dataclocator.http_schemas import RunRequest
from dataclocator.pipeline import write_json, write_preprocess_manifest
from dataclocator import MODEL_VERSION

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def request_body():
    """Use the documented real settings, without claiming fixture site evidence."""
    return copy.deepcopy(json.loads((ROOT / "docs/api-request-example.json").read_text()))


@pytest.fixture
def read_client(tmp_path):
    """Make a minimal input-ready fixture for read/validation HTTP behavior only."""
    write_json(tmp_path / "data/source_manifest.json", {"sources": []})
    write_json(tmp_path / "outputs/task2/candidates.json", {"model_version": MODEL_VERSION, "sources": [], "candidates": [{"candidate_id": "01089"}]})
    write_json(tmp_path / "outputs/task2/coverage.json", {"fixture_only": True})
    grid = tmp_path / "data/processed/grid_regions.parquet"
    grid.parent.mkdir(parents=True)
    grid.touch()
    write_json(tmp_path / "configs/candidates.json", {"fixture_only": True})
    write_preprocess_manifest(tmp_path, {"sources": []})
    app = create_app(tmp_path, cors_origins=["http://localhost:3000"])
    # Preserve stage 1 parsing isolation after production job endpoints are installed.
    app.router.routes = [route for route in app.router.routes if getattr(route, "path", None) != "/runs"]

    @app.post("/runs")
    def validation_probe(body: RunRequest):
        """Exercise parsing before stage 2 introduces job execution."""
        return body.model_dump()
    with TestClient(app) as client:
        yield client


def test_read_endpoints_and_cors(read_client):
    """Retain FIPS strings and allow only the configured frontend origin."""
    assert read_client.get("/health").json()["ready"] is True
    assert read_client.get("/datasets").json()["coverage"]["fixture_only"]
    assert read_client.get("/candidates").json()["evidence"]["candidates"][0]["candidate_id"] == "01089"
    for origin, allowed in [("http://localhost:3000", True), ("https://untrusted.example", False)]:
        response = read_client.get("/health", headers={"Origin": origin})
        assert ("access-control-allow-origin" in response.headers) is allowed


def test_missing_inputs_are_explicit(tmp_path):
    """A checkout without frozen data must stay inspectable and cannot run."""
    with TestClient(create_app(tmp_path)) as client:
        assert client.get("/health").status_code == 503
        assert client.get("/datasets").json()["manifest"] is None
        assert client.get("/candidates").status_code == 503
        error = client.get("/unknown").json()
        assert error["error"]["code"] == "NOT_FOUND"
        assert str(tmp_path) not in json.dumps(client.get("/health").json())
    with pytest.raises(ValueError, match="wildcard"):
        create_app(tmp_path, cors_origins=["*"])


def test_full_request_defaults_preserve_cli_config(read_client, request_body):
    """HTTP must not alter numerical representation and break CLI cache identity."""
    request_body.pop("options")
    response = read_client.post("/runs", json=request_body)
    assert response.status_code == 200
    assert json.dumps(response.json()["config"], sort_keys=True) == json.dumps(request_body["config"], sort_keys=True)
    assert response.json()["options"] == {"sensitivity": True, "convergence": True}


@pytest.mark.parametrize("mutation", ["unknown", "pue", "draws", "bool", "options", "source", "structure", "regional"])
def test_invalid_settings(read_client, request_body, mutation):
    """Reject malformed assumptions, unsupported controls and compute violations."""
    if mutation == "unknown":
        request_body["config"]["mispelled"] = 1
    elif mutation == "pue":
        request_body["config"]["cooling"]["pue"]["lower"] = .9
    elif mutation == "draws":
        request_body["config"]["simulation_count"] = 10001
    elif mutation == "bool":
        request_body["config"]["utilization"] = True
    elif mutation == "options":
        request_body["options"]["convergence"] = "false"
    elif mutation == "source":
        request_body["config"]["cooling"]["wue"]["source"] = ""
    elif mutation == "structure":
        request_body["config"]["cooling"]["wue"]["kind"] = []
    else:
        request_body["config"]["scenario_set"][0]["regional_overrides"] = {"ZZZZ": {"price_growth": request_body["config"]["scenario_set"][0]["price_growth"]}}
        # Geographic validity needs real candidate evidence and is tested in stage 2.
        assert read_client.post("/runs", json=request_body).status_code == 200
        return
    response = read_client.post("/runs", json=request_body)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


@pytest.mark.parametrize(
    "body,status",
    [("{", 400), ('{"config":NaN}', 400), ('{"config":Infinity}', 400), ('{"config":1e999}', 400), ("x" * (BODY_LIMIT + 1), 413)],
    # Keep the 1 MiB payload out of Windows pytest temporary-directory names.
    ids=["malformed", "nan", "infinity", "overflow", "too_large"],
)
def test_strict_json_and_body_limit(read_client, body, status):
    """Bound requests and reject nonfinite JSON before numerical execution."""
    assert read_client.post("/runs", content=body, headers={"Content-Type": "application/json"}).status_code == status
