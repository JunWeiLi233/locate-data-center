"""Transport tests against accepted real development outputs and strict API inputs."""
from __future__ import annotations

import copy
import hashlib
import json
import os
import shutil
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import numpy as np
import pandas as pd
import pytest
import yaml

from frontend.server.app import make_handler
from frontend.server.serialization import ApiError, ArtifactReader, clean, json_bytes, metric, screening_status, snapshot_configuration, valid_geometry
from frontend.server.service import GROUPS, LocatorService, validate_facility

ROOT = Path(__file__).resolve().parents[2]
EXPLORATORY = ROOT / "runs/phase7/root_v2_exploratory"


@pytest.fixture
def facility():
    return {"peak_it_power_mw": 100, "average_load_percent": 80, "target_opening_year": 2030, "lifetime_years": 25,
            "cooling": "all", "weighting": "equal", "screening_mode": "EXPLORATORY",
            "group_weights": dict.fromkeys(GROUPS, 0.25), "ahp_matrix": None}


@pytest.fixture
def service(tmp_path):
    result = LocatorService(ROOT, start_worker=False)
    # The parent may finish new real searches while these tests run. Pin this
    # fixture's registry to the accepted inputs whose artifact values are asserted.
    result.runs = {json.loads((ROOT / relative / "run_metadata.json").read_text(encoding="utf-8"))["run_id"]: ROOT / relative
                   for relative in ("runs/example", "runs/phase7/root_v2_exploratory")}
    result.reader = ArtifactReader(tmp_path / "responses")
    # HTTP POST tests record a queued job without executing or touching accepted outputs.
    result.registry_path = tmp_path / "registry.json"
    return result


def test_strict_json_preserves_missing_and_real_zero():
    payload = json.loads(json_bytes({"nested": [np.nan, np.inf, -np.inf, pd.NA, None, np.float64(0), np.bool_(True)]}))
    assert payload == {"nested": [None, None, None, None, None, 0.0, True]}
    unknown = metric("x", "x", np.nan, "water", {"status": "observed", "unit": "m3"})
    assert unknown["value"] is None and unknown["status"] == "unknown" and unknown["missing_reason"]
    observed = metric("x", "x", 0, "water", {"status": "observed", "confidence": "high", "unit": "m3"})
    assert observed["value"] == 0 and observed["status"] == "observed" and observed["missing_reason"] is None
    assert metric("x", "x", 4, "water", {"status": "unknown"})["value"] is None


def test_derived_metric_retains_formula_and_native_spatial_method():
    result = metric("carbon", "Carbon", 23, "power_carbon", {"status": "calculated", "unit": "tonnes_CO2e", "method": "c_electricity_kg / 1000",
                    "source_evidence": {"source_name": "EPA eGRID", "aggregation_method": "study-intersection area weighted overlay", "method": "raw source units retained"}})
    method = result["sources"][0]["method"]
    assert "Calculation: c_electricity_kg / 1000" in method
    assert "Source spatial aggregation: study-intersection area weighted overlay" in method
    assert "Source method: raw source units retained" in method


@pytest.mark.parametrize("field,value", [("peak_it_power_mw", True), ("peak_it_power_mw", "100"), ("peak_it_power_mw", 0), ("peak_it_power_mw", 1001),
    ("average_load_percent", 101), ("average_load_percent", np.nan), ("target_opening_year", 2030.0), ("target_opening_year", 2025),
    ("lifetime_years", False), ("lifetime_years", 0), ("cooling", "invented"), ("weighting", "browser_scores"), ("screening_mode", "PASS")])
def test_facility_strict_types_and_operational_bounds(facility, field, value):
    facility[field] = value
    with pytest.raises(ApiError):
        validate_facility({"facility": facility})


def test_weight_input_contract(facility):
    facility["weighting"] = "user"
    facility["group_weights"] = {"energy_carbon": 1}
    with pytest.raises(ApiError, match="four"):
        validate_facility({"facility": facility})
    facility["group_weights"] = dict.fromkeys(GROUPS, 0)
    with pytest.raises(ApiError, match="positive total"):
        validate_facility({"facility": facility})
    facility["group_weights"] = dict.fromkeys(GROUPS, 1)
    assert validate_facility({"facility": facility})["group_weights"] == dict.fromkeys(GROUPS, 1)
    facility["final_weights"] = {"fake": 1}
    with pytest.raises(ApiError, match="Unknown facility fields"):
        validate_facility({"facility": facility})


def test_ahp_uses_backend_review_no_override(facility):
    facility.update(weighting="ahp", ahp_matrix=[[1.0] * 4 for _ in range(4)])
    assert validate_facility({"facility": facility})["ahp_matrix"] == facility["ahp_matrix"]
    facility["ahp_matrix"][0][1] = 2
    with pytest.raises(ApiError, match="reciprocal"):
        validate_facility({"facility": facility})
    facility["ahp_matrix"] = [[1, 9, 1 / 9, 1], [1 / 9, 1, 9, 1], [9, 1 / 9, 1, 1], [1, 1, 1, 1]]
    with pytest.raises(ApiError, match="CR=") as error:
        validate_facility({"facility": facility})
    assert error.value.code == "ahp_review_required"


def test_existing_run_presentation_matches_authoritative_artifacts(service):
    run_id = service.latest_run_id()
    result = service.run_result(run_id)
    authoritative = pd.read_parquet(EXPLORATORY / "candidate_regions.parquet")
    assert result["state"] == "PARTIAL" and result["analyzed_cell_count"] == 42 and result["demo"] is False
    assert len(result["regions"]) == len(authoritative) == 2
    by_id = {row.region_id: row for row in authoritative.itertuples()}
    for region in result["regions"]:
        native = by_id[region["region_id"]]
        representative = json.loads(native.representative_json)
        assert region["rank"] == representative["mcda_rank"]
        assert region["overall_score"] == representative["mcda_score"]
        assert region["region_mean_score"] == native.mean_mcda_score
        assert region["overall_score"] != region["region_mean_score"]
        assert region["screening_status"] == "CONDITIONAL"
        assert region["verification_required"] and region["geometry"] and region["centroid"]
        assert region["data_quality"].startswith("Unknown;")
        assert "representative" in region["rank_basis"]
        assert all(m["unit"] and m["status"] and m["sources"] for m in region["raw_metrics"])
        unknown = next(m for m in region["raw_metrics"] if m["id"] == "peak_facility_demand_mw")
        assert unknown["value"] is None and unknown["missing_reason"] and unknown["status"] == "unknown"
        carbon = next(m for m in region["raw_metrics"] if m["id"] == "c_electricity_tonnes")
        assert carbon["value"] == representative["c_electricity_tonnes"] and carbon["sources"][0]["dataset_year"] == "2023"
        assert "c_electricity_kg / 1000" in carbon["sources"][0]["method"]
        assert "Source spatial aggregation:" in carbon["sources"][0]["method"]
        factors = {f["id"]: f for f in region["factors"]}
        assert factors["power_carbon"]["score"] == representative["annual_electricity_co2e"]
        assert factors["water"]["score"] == (representative["annual_site_water_consumption"] + representative["local_baseline_water_stress"]) / 2
        assert all(factors[f]["score"] is None for f in ("climate", "heat_reuse", "community_economic"))
        assert region["sensitivity"]["base_rank"] == region["rank"]
    json_bytes(result)  # strict NaN-free JSON throughout all nested source/geometry data


def test_old_strict_snapshot_is_not_replaced_by_current_ui(service):
    strict = service.run_result(next(iter(service.runs)))
    assert strict["state"] == "EMPTY" and strict["regions"] == []
    assert strict["configuration"]["screening_mode"] == "STRICT"
    assert strict["configuration"]["peak_it_power_mw"] == 100


def test_missing_core_result_artifact_is_error_while_present_empty_table_is_empty(tmp_path):
    # Copy only the immutable current result dependencies; no accepted run is edited.
    folder = tmp_path / "completed_strict"
    folder.mkdir()
    strict = ROOT / "runs/example"
    for filename in ("run_metadata.json", "config_snapshot.json", "us_grid_dataset.parquet", "feature_provenance.parquet",
                     "screening_results.parquet", "screening_summary.json", "candidate_regions.parquet", "candidate_regions.geojson",
                     "ranked_cells.parquet", "profile_snapshot.json", "weight_result.json"):
        shutil.copy2(strict / filename, folder / filename)
    reader = ArtifactReader(tmp_path / "responses")
    assert pd.read_parquet(folder / "candidate_regions.parquet").empty
    assert reader.run(folder)["state"] == "EMPTY"
    # A warmed cache must not hide an artifact that subsequently disappears.
    (folder / "candidate_regions.parquet").unlink()
    with pytest.raises(ApiError, match="candidate_regions.parquet") as error:
        reader.run(folder)
    assert error.value.code == "missing_artifact" and error.value.status == 422
    with pytest.raises(ApiError, match="candidate_regions.parquet"):
        reader._serialize_run(folder, folder, "current")
    with pytest.raises(ApiError, match="candidate_regions.parquet"):
        reader.layer(folder, "grid")


def test_capabilities_defaults_stay_baseline_when_latest_run_changes(service):
    strict_id = next(iter(service.runs))
    strict_path = service.runs.pop(strict_id)
    service.runs[strict_id] = strict_path
    capabilities = service.capabilities()
    assert capabilities["latest_run_id"] == strict_id
    assert capabilities["default_configuration"]["screening_mode"] == "EXPLORATORY"
    assert capabilities["default_configuration"]["peak_it_power_mw"] == 100
    assert capabilities["default_configuration"]["average_load_percent"] == 80


def test_successful_cached_run_becomes_latest_again(service):
    strict = ROOT / "runs/example"
    exploratory = EXPLORATORY
    strict_id = json.loads((strict / "run_metadata.json").read_text(encoding="utf-8"))["run_id"]
    exploratory_id = json.loads((exploratory / "run_metadata.json").read_text(encoding="utf-8"))["run_id"]
    service.runs.clear()
    service.register_run(strict, save=False)
    assert service.latest_run_id() == strict_id
    service.register_run(exploratory, save=False)
    assert service.latest_run_id() == exploratory_id
    service.register_run(strict)
    assert service.latest_run_id() == strict_id
    assert list(service.runs) == [exploratory_id, strict_id]
    assert len(service.runs) == 2
    durable = json.loads(service.registry_path.read_text(encoding="utf-8"))
    assert list(durable["runs"])[-1] == strict_id


def test_job_history_is_bounded_in_memory_and_registry_without_dropping_active(service):
    service.jobs = {"older_queued": {"state": "QUEUED"}, "older_running": {"state": "RUNNING"}}
    service.jobs.update({f"terminal_{index}": {"state": "COMPLETE" if index % 2 else "ERROR"} for index in range(600)})
    service._save()
    assert len(service.jobs) == 102
    assert set(service.jobs) == {"older_queued", "older_running"} | {f"terminal_{index}" for index in range(500, 600)}
    durable = json.loads(service.registry_path.read_text(encoding="utf-8"))
    assert durable["jobs"] == service.jobs
    assert len(durable["runs"]) == 2


def test_scenarios_supported_and_unsupported(service):
    identifier = service.latest_run_id()
    for scenario in ("bau_2030", "opt_2050", "pes_2080"):
        result = service.run_result(identifier, scenario)
        assert result["scenario_id"] == scenario and result["state"] == "PARTIAL"
        assert all("aqueduct" in r["scenario_id"] for r in result["regions"])
        for region in result["regions"]:
            water = next(m for m in region["raw_metrics"] if m["id"] == f"aqueduct_{scenario}_water_stress_score")
            assert water["status"] == "scenario" and water["value"] is not None
    for scenario in ("bau_2040", "current/../../example", "not_real"):
        with pytest.raises(ApiError) as error:
            service.run_result(identifier, scenario)
        assert error.value.code == "unsupported_scenario"


def test_failed_alternative_never_promoted_as_region(service, monkeypatch):
    reader = service.reader
    original = reader.table
    def altered(folder, name, **kwargs):
        frame = original(folder, name, **kwargs)
        if name == "ranked_cells":
            frame = frame.copy()
            frame["hard_fail"] = True
        return frame
    monkeypatch.setattr(reader, "table", altered)
    result = reader._serialize_run(EXPLORATORY, EXPLORATORY, "current")
    assert result["regions"] == [] and result["state"] == "EMPTY"
    assert any("hard failure" in w for w in result["warnings"])
    assert screening_status({"hard_fail": True, "eligible": True, "conditional": True}) == "FAIL"


def test_invalid_geometry_is_reported_not_repaired_or_invented():
    geometry, warning = valid_geometry({"type": "Polygon", "coordinates": [[[0, 0], [1, 1], [1, 0], [0, 1], [0, 0]]]})
    assert geometry is None and warning
    assert valid_geometry({"type": "Polygon", "coordinates": [[[200, 0], [201, 0], [201, 1], [200, 0]]]})[0] is None


def test_one_malformed_region_retains_other_regions_and_evidence(service, monkeypatch):
    import frontend.server.serialization as module
    original = module.read_json
    def altered(path, fallback=None):
        result = original(path, fallback)
        if path.name == "candidate_regions.geojson":
            result = copy.deepcopy(result)
            result["features"][0]["geometry"] = {"type": "Polygon", "coordinates": []}
        return result
    monkeypatch.setattr(module, "read_json", altered)
    result = service.reader._serialize_run(EXPLORATORY, EXPLORATORY, "current")
    assert len(result["regions"]) == 2
    assert sum(r["geometry"] is None for r in result["regions"]) == 1
    unavailable = next(r for r in result["regions"] if r["geometry"] is None)
    assert unavailable["geometry_warning"] and unavailable["rank"] and unavailable["raw_metrics"]


def test_layers_real_cells_units_metadata_no_lines(service):
    identifier = service.latest_run_id()
    for layer in ("grid", "power_carbon", "water", "land", "climate", "infrastructure"):
        result = service.layer_result(layer, identifier)
        assert len(result["data"]["features"]) == 42
        assert all(f["geometry"]["type"] in {"Polygon", "MultiPolygon"} for f in result["data"]["features"])
        assert result["unit"] and result["source"] and result["warning"]
        assert all("status" in f["properties"] and "unit" in f["properties"] for f in result["data"]["features"])
        json_bytes(result)
    grid = service.layer_result("grid", identifier)
    assert all(f["properties"]["unknowns"] and f["properties"]["alternatives"] for f in grid["data"]["features"])
    assert all(f["properties"]["status"] == "CONDITIONAL" for f in grid["data"]["features"])
    with pytest.raises(ApiError):
        service.layer_result("heat_reuse", identifier)
    with pytest.raises(ApiError):
        service.layer_result("climate", identifier, sublayer="invented_hurricanes")


def test_durable_cache_and_export_allowlist(service, tmp_path):
    identifier = service.latest_run_id()
    result = service.run_result(identifier)
    assert list((tmp_path / "responses").glob("*.json"))
    other = ArtifactReader(tmp_path / "responses")
    assert other.run(EXPLORATORY) == result
    assert service.export(identifier, "ranking").name == "ranking.csv"
    assert service.export(identifier, "regions", "bau_2030").parent.name == "bau_2030"
    with pytest.raises(ApiError):
        service.export(identifier, "../../configs/facility.yaml")
    with pytest.raises(ApiError):
        service.resolve_run("runs/example")


@pytest.mark.parametrize("filename", ["candidate_regions.geojson", "us_grid_dataset.parquet", "screening_summary.json"])
def test_cache_key_uses_content_checksums_even_when_size_and_timestamp_match(tmp_path, filename):
    root = tmp_path / "artifacts"
    root.mkdir()
    for dependency in ("run_metadata.json", filename):
        shutil.copy2(EXPLORATORY / dependency, root / dependency)
    reader = ArtifactReader(tmp_path / "responses")
    _, before = reader.identity(root, root)
    path = root / filename
    stat = path.stat()
    original = path.read_bytes()
    changed = original.replace(b"region_", b"regiun_", 1) if filename.endswith("geojson") else original.replace(b'"n_alternatives":84', b'"n_alternatives":83', 1) if filename.endswith("json") else b"X" + original[1:]
    assert len(changed) == len(original) and changed != original
    path.write_bytes(changed)
    os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns))
    _, after = reader.identity(root, root)
    assert before != after


def test_configuration_files_are_scoped_and_preserve_backend_contract(facility, tmp_path):
    configs = tmp_path / "configs"
    configs.mkdir()
    for name in ("run_exploratory.yaml", "facility.yaml", "cooling_designs.yaml"):
        (configs / name).write_bytes((ROOT / "configs" / name).read_bytes())
    service = LocatorService(tmp_path, start_worker=False)
    facility.update(peak_it_power_mw=130, average_load_percent=70, cooling="air_dry_assumed", weighting="ahp", ahp_matrix=[[1.0]*4 for _ in range(4)])
    before = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in configs.iterdir()}
    path = service._write_configuration(validate_facility({"facility": facility}))
    assert path.is_relative_to(tmp_path / "runs/frontend_service")
    run = yaml.safe_load(path.read_text(encoding="utf-8"))
    actual_facility = yaml.safe_load((tmp_path / run["facility"]).read_text(encoding="utf-8"))["facilities"][0]
    assert actual_facility["peak_it_power_mw"] == 130 and actual_facility["average_it_load_factor"] == 0.7
    assert actual_facility["cooling_designs"] == ["air_dry_assumed"]
    ahp = json.loads((tmp_path / run["ahp_input"]).read_text(encoding="utf-8"))
    assert ahp["criteria_ids"] == list(GROUPS) and ahp["matrix"] == facility["ahp_matrix"]
    assert run["user_group_weights"] is None
    assert before == {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in configs.iterdir()}
    first_bytes = {p.name: p.read_bytes() for p in path.parent.iterdir()}
    assert service._write_configuration(facility) == path
    assert first_bytes == {p.name: p.read_bytes() for p in path.parent.iterdir()}
    # Even a tampered owned file is rejected instead of overwritten under its identity.
    path.write_bytes(path.read_bytes() + b"\n# modified\n")
    with pytest.raises(ValueError, match="immutable identity"):
        service._write_configuration(facility)


@pytest.fixture
def http_server(service):
    server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(service))
    server.daemon_threads = True
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}", service
    server.shutdown()
    server.server_close()
    thread.join(timeout=2)


def fetch(base, path, *, body=None, headers=None):
    data = json_bytes(body) if body is not None else None
    request = Request(base + path, data=data, headers=headers or ({"Content-Type": "application/json"} if body is not None else {}))
    try:
        with urlopen(request, timeout=5) as response:
            return response.status, response.headers, response.read()
    except HTTPError as response:
        return response.code, response.headers, response.read()


def test_http_routes_queue_progress_and_whitelisted_export(http_server, facility):
    base, service = http_server
    status, _, body = fetch(base, "/api/capabilities")
    assert status == 200
    caps = json.loads(body)
    assert caps["default_configuration"]["peak_it_power_mw"] == 100
    assert caps["default_configuration"]["average_load_percent"] == 80
    identifier = caps["latest_run_id"]
    assert all(s["available"] is False for s in caps["scenarios"] if s["year"] == 2040)
    assert fetch(base, f"/api/runs/{identifier}")[0] == 200
    assert fetch(base, f"/api/layers/water?run_id={identifier}")[0] == 200
    status, headers, body = fetch(base, f"/api/exports/{identifier}/ranking")
    assert status == 200 and "attachment" in headers["Content-Disposition"] and b"mcda_rank" in body
    status, _, body = fetch(base, "/api/search", body={"facility": facility})
    assert status == 202
    job_id = json.loads(body)["job_id"]
    status, _, body = fetch(base, f"/api/jobs/{job_id}")
    assert status == 200 and json.loads(body)["state"] == "QUEUED" and json.loads(body)["stage"] == "queued"
    assert fetch(base, "/api/layers/water")[0] == 400
    assert fetch(base, f"/api/runs/{identifier}?scenario=bau_2040")[0] == 422
    assert fetch(base, f"/api/runs/{identifier}?scenario=current&scenario=bau_2030")[0] == 400
    assert fetch(base, "/api/runs/not_a_run")[0] == 404
    assert fetch(base, "/api/not_a_route")[0] == 404


def test_http_rejects_cross_origin_and_nonfinite(http_server, facility):
    base, _ = http_server
    assert fetch(base, "/api/capabilities", headers={"Origin": "https://untrusted.example"})[0] == 403
    request = Request(base + "/api/search", data=b'{"facility":{"peak_it_power_mw":NaN}}', headers={"Content-Type": "application/json"})
    with pytest.raises(HTTPError) as response:
        urlopen(request, timeout=5)
    assert response.value.code == 400 and b"finite" in response.value.read()
    status, headers, _ = fetch(base, "/api/capabilities", headers={"Origin": "http://localhost:5173"})
    assert status == 200 and headers["Access-Control-Allow-Origin"] == "http://localhost:5173"
