"""Read-only rediscovery transport over a synthetic analysis built by the real dc_rediscovery pipeline."""
import gzip
import io
import json
from types import SimpleNamespace

import pytest

from frontend.server.app import make_handler
from frontend.server.rediscovery import RediscoveryReader
from frontend.server.serialization import ApiError
from dc_rediscovery.pipeline import run
from tests.test_rediscovery_pipeline import _config, _write_counties, _write_facilities, _write_model_run, _write_monte_carlo


@pytest.fixture
def analysis(tmp_path):
    _write_model_run(tmp_path)
    _write_counties(tmp_path)
    _write_monte_carlo(tmp_path)
    run(_config(tmp_path, _write_facilities(tmp_path)), "runs/rediscovery_fixture", root=tmp_path, progress=None)
    return tmp_path


def request(root, path):
    handler = object.__new__(make_handler(SimpleNamespace(root=root)))
    handler.path = path
    handler.headers = {"Host": "127.0.0.1:8787", "Accept-Encoding": "gzip"}
    handler.wfile = io.BytesIO()
    sent = {"headers": {}}
    handler.send_response = lambda status: sent.__setitem__("status", status)
    handler.send_header = lambda name, value: sent["headers"].__setitem__(name, value)
    handler.end_headers = lambda: None
    handler._handle("GET")
    body = handler.wfile.getvalue()
    if sent["headers"].get("Content-Encoding") == "gzip":
        body = gzip.decompress(body)
    return sent["status"], sent["headers"], body


def test_index_lists_analyses_but_defaults_only_to_real_data(analysis):
    index = RediscoveryReader(analysis).index()
    assert [item["analysis_id"] for item in index["analyses"]] == ["rediscovery_fixture"]
    assert index["analyses"][0]["available"] and index["analyses"][0]["data_mode"] == "synthetic"
    assert index["default_analysis_id"] is None


def test_payload_transports_backend_values(analysis):
    payload = json.loads(RediscoveryReader(analysis).payload_bytes("rediscovery_fixture"))
    assert payload["schema_version"] == "1.0.0" and payload["data_mode"] == "synthetic"
    candidates = payload["candidates"]
    assert [item["rank"] for item in candidates] == [1, 2, 3, 4]
    first = candidates[0]
    assert set(first["nearest_existing_dc"]) >= {"facility_id", "name", "lat", "lon"}
    assert first["robustness"]["score"] == 100.0 and first["robustness"]["spatial_support"] == "county"
    assert sum(item["contribution"] for item in first["factors"]) == pytest.approx(first["suitability_score"])
    assert set(first["existing_dc_within_km"]) == {"2", "10"}
    assert len(payload["facilities"]) == 4 and payload["surface"]["url"] == "/api/rediscovery/rediscovery_fixture/surface.png"
    assert payload["results"]["hit_rates"] and payload["results"]["baseline_comparison"]
    assert "interpretation" in payload and payload["limitations"]


def test_http_routes_and_refusals(analysis):
    status, headers, body = request(analysis, "/api/rediscovery")
    assert status == 200 and json.loads(body)["analyses"][0]["analysis_id"] == "rediscovery_fixture"
    status, headers, body = request(analysis, "/api/rediscovery/rediscovery_fixture")
    assert status == 200 and headers["Content-Encoding"] == "gzip" and json.loads(body)["analysis_id"] == "rediscovery_fixture"
    status, headers, body = request(analysis, "/api/rediscovery/rediscovery_fixture/surface.png")
    assert status == 200 and headers["Content-Type"] == "image/png" and body[:8] == b"\x89PNG\r\n\x1a\n"
    for path in ("/api/rediscovery/missing", "/api/rediscovery/..%2F..%2Fdata", "/api/rediscovery/rediscovery_fixture/other.png"):
        status, _, body = request(analysis, path)
        assert status == 404, path
    status, _, _ = request(analysis, "/api/rediscovery/rediscovery_fixture?top=5")
    assert status == 400


def test_damaged_artifacts_fail_instead_of_partial_views(analysis):
    reader = RediscoveryReader(analysis)
    reader.payload_bytes("rediscovery_fixture")
    target = analysis / "runs" / "rediscovery_fixture" / "validation_summary.json"
    original = target.read_text(encoding="utf-8")
    changed = original.replace('"data_mode": "synthetic"', '"data_mode": "synthetiC"', 1)
    assert changed != original
    target.write_text(changed, encoding="utf-8")
    with pytest.raises(ApiError, match="checksum mismatch"):
        reader.payload_bytes("rediscovery_fixture")
    (analysis / "runs" / "rediscovery_fixture" / "candidates.parquet").unlink()
    with pytest.raises(ApiError, match="required artifact"):
        RediscoveryReader(analysis).payload_bytes("rediscovery_fixture")
