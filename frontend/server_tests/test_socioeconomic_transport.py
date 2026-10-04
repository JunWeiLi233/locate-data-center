"""Independent county context: synthetic transport fixtures never become model inputs."""
from __future__ import annotations

import hashlib
import json
import threading
from http.server import ThreadingHTTPServer
from types import SimpleNamespace
from urllib.error import HTTPError
from urllib.request import urlopen

import geopandas as gpd
import numpy as np
import pandas as pd
import pytest
from shapely.geometry import box

from frontend.server.app import make_handler
from frontend.server.serialization import ApiError, json_bytes
from frontend.server.service import LocatorService


def test_county_context_endpoint_exists(tmp_path):
    service = LocatorService(tmp_path, start_worker=False)
    assert callable(getattr(service, "socioeconomic_result", None)), "County context endpoint is missing"


@pytest.fixture
def economic_service(tmp_path, monkeypatch):
    service = LocatorService(tmp_path, start_worker=False)
    assert callable(getattr(service, "socioeconomic_result", None)), "County context endpoint is missing"
    import frontend.server.socioeconomic as transport

    folder = tmp_path / "runs/synthetic_transport"
    folder.mkdir(parents=True)
    (folder / "run_metadata.json").write_text(json.dumps({"run_id": "fixture", "scope": {"data_mode": "synthetic"}}))
    grid = gpd.GeoDataFrame({"grid_id": ["a", "b", "c"], "study_area_intersection_km2": [1., 1., 1.]},
                           geometry=[box(0, 0, 1000, 1000), box(1000, 0, 2000, 1000), box(2000, 0, 3000, 1000)], crs=5070)
    grid.to_parquet(folder / "us_grid_dataset.parquet", index=False)
    pd.DataFrame({"region_id": ["region_ab", "region_c"], "member_grid_ids": [["a", "b"], ["c"]],
                  "n_cells": [2, 1]}).to_parquet(folder / "candidate_regions.parquet", index=False)
    pd.DataFrame({"region_id": ["region_ab", "region_ab", "region_c"], "grid_id": ["a", "b", "c"]}).to_parquet(
        folder / "region_membership.parquet", index=False)
    pd.DataFrame({"grid_id": ["a", "b", "c"], "mcda_score": [90., 80., 70.], "mcda_rank": [1, 2, 3]}).to_parquet(
        folder / "ranked_cells.parquet", index=False)
    cache = tmp_path / "data/processed/synthetic_transport"
    cache.mkdir(parents=True)
    counties = gpd.GeoDataFrame({"county_geoid": ["01001", "01003", "01005"], "county_name": ["A", "B", "C"],
        "socioeconomic_year": [2024] * 3,
        "state_fips": ["01"] * 3, "poverty_rate": [0., 20., np.nan], "poverty_rate_moe": [1., 2., np.nan],
        "median_household_income": [80000., np.nan, 50000.], "median_household_income_moe": [3000., np.nan, 2500.],
        "poverty_percentile": [0., 100., np.nan], "low_income_percentile": [0., np.nan, 100.],
        "poverty_rate_status": ["observed", "observed", "unknown"],
        "median_household_income_status": ["observed", "unknown", "observed"],
        "median_household_income_unit": ["USD/year"] * 3,
        "low_income_percentile_status": ["calculated", "unknown", "calculated"],
        "poverty_rate_missing_reason": [None, None, "source suppression"],
        "median_household_income_missing_reason": [None, "source suppression", None]},
        geometry=[box(0, 0, 600, 1000), box(600, 0, 1800, 1000), box(2000, 0, 3000, 1000)], crs=5070)
    counties.to_parquet(cache / "counties.parquet", index=False)
    pd.DataFrame({"candidate_id": ["a", "a", "b", "c"], "county_geoid": ["01001", "01003", "01003", "01005"],
                  "candidate_area_km2": [1.] * 4, "intersection_area_km2": [.6, .4, .8, 1.],
                  "overlap_fraction": [.6, .4, .8, 1.]}).to_parquet(cache / "crosswalk.parquet", index=False)
    pd.DataFrame({"candidate_id": ["a", "b", "c"], "candidate_area_km2": [1.] * 3,
                  "covered_area_km2": [1., .8, 1.]}).to_parquet(cache / "coverage.parquet", index=False)
    metadata = {"schema_version": "1.0.0", "data_mode": "synthetic", "boundary_year": 2025, "socioeconomic_year": 2024,
                "boundary_source_kind": "cartographic", "warnings": ["Generalized county boundaries; mixed vintages"],
                "source_metadata": {"estimate_source": {"name": "Synthetic SAIPE fixture", "url": "https://www.census.gov/"},
                                    "boundary_source": {"name": "Synthetic county fixture", "url": "https://www.census.gov/", "year": 2025,
                                                        "scale": "1:500000", "kind": "cartographic"}}}
    artifacts = SimpleNamespace(county_path=cache / "counties.parquet", crosswalk_path=cache / "crosswalk.parquet",
                               coverage_path=cache / "coverage.parquet", metadata=metadata)
    requests = []
    def cached(root, grid_path, boundary_year):
        requests.append((root, grid_path, boundary_year))
        return artifacts
    monkeypatch.setattr(transport, "cached_artifacts", cached)
    monkeypatch.setattr(transport, "cached_counties", lambda root, year: artifacts)
    service.runs = {"fixture": folder}
    return service, artifacts, requests


def test_all_positive_counties_use_membership_and_unrenormalized_overlap(economic_service):
    service, _, requests = economic_service
    result = service.socioeconomic_result("fixture")
    counties = result["region_counties"]["region_ab"]
    assert [r["county_geoid"] for r in counties] == ["01001", "01003"]
    assert [r["overlap_area_km2"] for r in counties] == pytest.approx([.6, 1.2])
    assert [r["overlap_fraction"] for r in counties] == pytest.approx([.3, .6])
    assert result["coverage_summary"]["regions_with_partial_county_coverage"] == 1
    assert set(result["region_counties"]) == {"region_ab", "region_c"}
    assert requests[0][2] == 2025


def test_unknown_is_null_and_zero_is_observed(economic_service):
    service, _, _ = economic_service
    result = service.socioeconomic_result("fixture")
    a, b = result["region_counties"]["region_ab"]
    assert a["poverty_rate_pct"] == 0
    assert a["metrics"]["poverty_rate_pct"]["status"] == "observed"
    assert b["income_usd"] is None and b["income_moe_usd"] is None
    assert b["metrics"]["income_usd"]["status"] == "unknown"
    assert b["metrics"]["income_usd"]["missing_reason"] == "source suppression"
    assert result["fiscal_context"]["local_revenue"]["value"] is None
    assert result["fiscal_context"]["service_pressure"]["status"] == "unknown"
    assert json.loads(json_bytes(result))["region_counties"]["region_ab"][1]["income_usd"] is None


@pytest.mark.parametrize("year", [2024, 2026, True, "../2025", "2025@region_ab", 2025.0, None])
def test_boundary_year_validation_precedes_cache_access(economic_service, year):
    service, _, requests = economic_service
    with pytest.raises(ApiError) as error:
        service.socioeconomic_result("fixture", boundary_year=year)
    assert error.value.code == "invalid_boundary_year"
    assert not requests


def test_national_county_layer_has_no_regional_window(economic_service):
    service, _, _ = economic_service
    result = service.layer_result("community_economic", "fixture", sublayer="income@2025")
    assert result["schema_version"] == "1.8.0"
    assert result["direction"] == "neutral"
    assert len(result["data"]["features"]) == 3
    assert result["value_property"] == "value" and result["status_property"] == "status"
    b = next(f for f in result["data"]["features"] if f["id"] == "01003")
    assert b["properties"]["value"] is None and b["properties"]["status"] == "unknown"
    assert "2024" in result["label"] and "2025" in result["label"]
    assert "Generalized" in result["warning"]
    coordinates = result["data"]["features"][0]["geometry"]["coordinates"]
    assert -180 <= coordinates[0][0][0] <= 180 and -90 <= coordinates[0][0][1] <= 90
    assert service.layer_result("community_economic", "fixture")["data"]["features"]
    with pytest.raises(ApiError):
        service.layer_result("community_economic", "fixture", sublayer="income@region_ab")


def test_layer_uses_native_annual_income_unit_and_derived_source_year(economic_service):
    service, _, _ = economic_service
    layer = service.layer_result("community_economic", "fixture", sublayer="income@2025")
    assert layer["unit"] == "USD/year"
    assert all(feature["properties"]["unit"] == layer["unit"] for feature in layer["data"]["features"])
    county = service.socioeconomic_result("fixture")["region_counties"]["region_ab"][0]
    assert county["metrics"]["low_income_percentile"]["data_year"] == 2024


def test_future_context_uses_its_exact_native_regions_and_membership(economic_service):
    service, _, requests = economic_service
    folder = service.runs["fixture"]
    future = folder / "future_contexts/bau_2030"
    future.mkdir(parents=True)
    (future / "external_scenario.json").write_text(json.dumps({"supported": True}))
    pd.DataFrame({"region_id": ["future_b", "future_c"], "member_grid_ids": [["b"], ["c"]], "n_cells": [1, 1]}).to_parquet(
        future / "candidate_regions.parquet", index=False)
    pd.DataFrame({"region_id": ["future_b", "future_c"], "grid_id": ["b", "c"]}).to_parquet(
        future / "region_membership.parquet", index=False)
    result = service.socioeconomic_result("fixture", scenario="bau_2030")
    assert result["scenario_id"] == "bau_2030"
    assert set(result["region_counties"]) == {"future_b", "future_c"}
    assert [c["county_geoid"] for c in result["region_counties"]["future_b"]] == ["01003"]
    assert result["region_counties"]["future_b"][0]["overlap_fraction"] == pytest.approx(.8)
    assert requests[0][1] == folder / "us_grid_dataset.parquet"
    assert result["socioeconomic_year"] == 2024
    assert service.socioeconomic_result("fixture")["scenario_id"] == "current"
    with pytest.raises(ApiError) as error:
        service.socioeconomic_result("fixture", scenario="bau_2040")
    assert error.value.code == "unsupported_scenario"


def test_supported_future_cannot_fall_back_to_baseline_membership(economic_service):
    service, _, _ = economic_service
    future = service.runs["fixture"] / "future_contexts/bau_2050"
    future.mkdir(parents=True)
    (future / "external_scenario.json").write_text(json.dumps({"supported": True}))
    with pytest.raises(ApiError) as error:
        service.socioeconomic_result("fixture", scenario="bau_2050")
    assert error.value.code == "missing_artifact"


def test_context_does_not_mutate_scores_ranks_or_legacy_registry(economic_service):
    service, _, _ = economic_service
    before = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in service.runs["fixture"].iterdir() if p.is_file()}
    registry = service.runs.copy()
    service.socioeconomic_result("fixture", boundary_year="2023")
    service.layer_result("community_economic", "fixture", sublayer="poverty@2023")
    after = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in service.runs["fixture"].iterdir() if p.is_file()}
    assert after == before and service.runs == registry
    with pytest.raises(ApiError) as error:
        service.socioeconomic_result("../../unregistered")
    assert error.value.code == "run_not_found"


def test_corrupt_bound_membership_is_not_silently_reported_as_unknown(economic_service):
    service, _, _ = economic_service
    folder = service.runs["fixture"]
    native = folder / "region_membership.parquet"
    metadata = json.loads((folder / "run_metadata.json").read_text())
    metadata["output_hashes"] = {native.name: hashlib.sha256(native.read_bytes()).hexdigest()}
    (folder / "run_metadata.json").write_text(json.dumps(metadata))
    frame = pd.read_parquet(native)
    frame.loc[0, "grid_id"] = "damaged"
    frame.to_parquet(native, index=False)
    with pytest.raises(ApiError) as error:
        service.socioeconomic_result("fixture")
    assert error.value.code == "completed_run_checksum_mismatch"


def test_missing_native_member_cannot_silently_drop_a_county(economic_service):
    service, _, _ = economic_service
    path = service.runs["fixture"] / "region_membership.parquet"
    frame = pd.read_parquet(path)
    frame.loc[~frame.grid_id.eq("b")].to_parquet(path, index=False)
    with pytest.raises(ApiError) as error:
        service.socioeconomic_result("fixture")
    assert error.value.code == "invalid_region_membership"


def test_corrupt_bound_grid_is_rejected_before_context_preparation(economic_service):
    service, _, requests = economic_service
    folder = service.runs["fixture"]
    path = folder / "us_grid_dataset.parquet"
    meta = json.loads((folder / "run_metadata.json").read_text())
    meta["output_hashes"] = {path.name: "0" * 64}
    (folder / "run_metadata.json").write_text(json.dumps(meta))
    with pytest.raises(ApiError) as error:
        service.socioeconomic_result("fixture")
    assert error.value.code == "completed_run_checksum_mismatch" and not requests


def test_native_generalization_and_mixed_vintage_provenance_are_visible(economic_service):
    service, artifacts, _ = economic_service
    artifacts.metadata = {"boundary_year": 2025, "socioeconomic_year": 2024, "boundary_type": "cartographic_500k",
        "geometry_warning": "Generalized 1:500000 county boundaries", "binding": {"county_binding": {
            "config": {"saipe_year": 2024, "boundary_type": "cartographic_500k"},
            "sources": [{"url": "https://www2.census.gov/counties.zip"}, {"url": "https://www2.census.gov/est24all.txt"}]}}}
    result = service.socioeconomic_result("fixture")
    assert result["source_metadata"]["boundary_source"]["year"] == 2025
    assert result["source_metadata"]["boundary_source"]["scale"] == "1:500000"
    assert result["source_metadata"]["estimate_source"]["url"].endswith("est24all.txt")
    assert any("Generalized" in warning for warning in result["warnings"])
    assert any("2024" in warning and "2025" in warning for warning in result["warnings"])


def test_disabled_context_never_builds_or_downloads(tmp_path, monkeypatch):
    import frontend.server.socioeconomic as transport
    def forbidden(*args, **kwargs):
        raise AssertionError("Disabled context must never prepare geography")
    module = SimpleNamespace(source_availability=lambda *args, **kwargs: {"available": False},
                             ensure_county_geography=forbidden)
    monkeypatch.setattr(transport, "_geography", lambda: module)
    with pytest.raises(FileNotFoundError):
        transport.cached_counties(tmp_path, 2025)


def test_http_cannot_load_entire_national_fine_surface(tmp_path, monkeypatch):
    import frontend.server.socioeconomic as transport
    grid = tmp_path / "grid.parquet"
    grid.touch()
    monkeypatch.setattr(transport.pq, "read_metadata", lambda path: SimpleNamespace(num_rows=7_829_373))
    with pytest.raises(ApiError) as error:
        transport.cached_artifacts(tmp_path, grid, 2025)
    assert error.value.code == "socioeconomic_grid_budget"


def test_unprewarmed_legacy_context_stays_explicitly_unavailable(economic_service, monkeypatch):
    service, _, _ = economic_service
    import frontend.server.socioeconomic as transport
    def missing(*args):
        raise FileNotFoundError("Independent county context has not been prewarmed")
    monkeypatch.setattr(transport, "cached_artifacts", missing)
    monkeypatch.setattr(transport, "cached_counties", missing)
    result = service.socioeconomic_result("fixture")
    assert result["available"] is False and result["region_counties"] == {}
    assert result["warnings"] and result["socioeconomic_year"] == 2024
    assert service.resolve_run("fixture").is_dir()
    with pytest.raises(ApiError) as error:
        service.layer_result("community_economic", "fixture", sublayer="poverty@2025")
    assert error.value.code == "unavailable_layer"


def test_http_socioeconomic_route_and_repeated_year_rejection(economic_service):
    service, _, _ = economic_service
    server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(service))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"
    try:
        with urlopen(base + "/api/socioeconomic?run_id=fixture&boundary_year=2025&scenario=current", timeout=5) as response:
            result = json.load(response)
        assert result["boundary_year"] == 2025 and result["region_counties"] and result["scenario_id"] == "current"
        with pytest.raises(HTTPError) as unsupported:
            urlopen(base + "/api/socioeconomic?run_id=fixture&scenario=bau_2040", timeout=5)
        assert unsupported.value.code == 422
        with pytest.raises(HTTPError) as error:
            urlopen(base + "/api/socioeconomic?run_id=fixture&boundary_year=2025&boundary_year=2023", timeout=5)
        assert error.value.code == 400
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
