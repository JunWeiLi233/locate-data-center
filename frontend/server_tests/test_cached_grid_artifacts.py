"""Checksummed transport fixtures copied from accepted small native evidence."""
from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

import pandas as pd
import pytest

from frontend.server.artifacts import FAST_REQUIRED, ModelArtifactReader, verify_fast_artifacts
from frontend.server.serialization import ApiError, clean, file_digest


ACCEPTED = Path(__file__).resolve().parents[2] / "runs/phase7/root_v2_exploratory"


def emit(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(clean(value)), encoding="utf-8")


def rebind(folder):
    meta = json.loads((folder / "run_metadata.json").read_text())
    meta["output_hashes"] = {p.relative_to(folder).as_posix(): file_digest(p)
                             for p in folder.rglob("*") if p.is_file() and p.name != "run_metadata.json"}
    emit(folder / "run_metadata.json", meta)


@pytest.fixture
def fast_artifacts(tmp_path):
    folder = tmp_path / "runs/frontend_service/cached_regional_runs" / ("a" * 64)
    baseline = tmp_path / "runs/cleanview_regional_v2"
    part = baseline / "parts/native_fixture"
    part.mkdir(parents=True)
    folder.mkdir(parents=True)
    for source, destination in (("us_grid_dataset", "representative_geography"), ("feature_provenance", "representative_provenance"),
                                ("site_performance", "representative_evidence"), ("screening_results", "representative_screening"),
                                ("us_grid_dataset", "us_grid_dataset"), ("screening_results", "screening_checks")):
        shutil.copyfile(ACCEPTED / (source + ".parquet"), folder / (destination + ".parquet"))
    for name in ("us_grid_dataset", "feature_provenance"):
        shutil.copyfile(ACCEPTED / (name + ".parquet"), part / (name + ".parquet"))
    for name in ("config_snapshot.json", "profile_snapshot.json", "weight_result.json", "screening_summary.json",
                 "candidate_regions.parquet", "candidate_regions.geojson"):
        shutil.copyfile(ACCEPTED / name, folder / name)
    from frontend.server.serialization import snapshot_configuration
    import yaml
    submitted = snapshot_configuration(ACCEPTED)
    snapshot = json.loads((folder / "config_snapshot.json").read_text())
    facility_text = next(text for path, text in snapshot["files"].items() if Path(path).name == "facility.yaml")
    native = yaml.safe_load(facility_text)["facilities"][0]
    native.update(screening_mode=submitted["screening_mode"], cooling_designs=["air_dry_assumed", "cold_plate_tower_assumed"])
    snapshot.update(submitted_facility=submitted, facility=native)
    emit(folder / "config_snapshot.json", snapshot)
    ranked = pd.read_parquet(ACCEPTED / "ranked_cells.parquet")
    ranked["mcda_score"] = 12.34
    ranked["mcda_rank"] = 3
    ranked["e_facility_mwh"] = 123456.0
    ranked.drop(columns=[c for c in ranked if c.endswith("_json")]).to_parquet(folder / "ranked_cells.parquet", index=False)
    fresh = pd.read_parquet(folder / "representative_evidence.parquet")
    fresh["e_facility_mwh"] = 123456.0
    fresh.to_parquet(folder / "representative_evidence.parquet", index=False)
    regions = pd.read_parquet(folder / "candidate_regions.parquet")
    fresh_by_key = {(r["grid_id"], r["design_id"], r["scenario_id"]): r for r in ranked.to_dict("records")}
    regions["representative_json"] = [json.dumps(clean(fresh_by_key[(r.representative_grid_id, r.design_id, r.scenario_id)]))
                                       for r in regions.itertuples()]
    regions.to_parquet(folder / "candidate_regions.parquet", index=False)
    count = len(pd.read_parquet(folder / "us_grid_dataset.parquet"))
    emit(folder / "region_membership.parquet", {"opaque": "not loaded by reader fixture"})
    emit(folder / "regional_catalog.json", dict(analysis_level="regional", selection="fixed_cached_cohort",
        grid_definition_id="native_transport_fixture", cell_size_m=1000, maximum_region_extent_km=20,
        refined_cells=count, refined_parent_cells=1, coverage_warning="Fixed cached cohort; other areas unassessed.",
        representative_parts=dict.fromkeys(regions.representative_grid_id, "parts/native_fixture"),
        parts=[dict(path="parts/native_fixture", parent_grid_id="native_fixture", cell_count=count)]))
    emit(folder / "validation_report.json", {"status": "NOT_ASSESSED"})
    emit(baseline / "run_metadata.json", {"run_id": "native_fixture", "data_mode": "real"})
    cache = tmp_path / "data/interim/fast_cached_regions/fixture"
    cache.mkdir(parents=True)
    for name in ("compact.parquet", "strict_compact.parquet", "carbon.parquet", "screening_checks.parquet", "geometry.parquet"):
        (cache / name).write_bytes(b"opaque checksum fixture")
    hashes = {p.name: file_digest(p) for p in cache.glob("*.parquet")}
    native_hashes = {p.relative_to(baseline).as_posix(): file_digest(p) for p in part.glob("*.parquet")}
    baseline_sha = file_digest(baseline / "run_metadata.json")
    manifest = dict(data_mode="real", cache_identity="fixture", baseline_run_id="native_fixture", baseline_path=str(baseline),
        baseline_run_metadata_sha256=baseline_sha, cohort_cells=count, parent_windows=1, grid_definition_id="native_transport_fixture",
        output_hashes=hashes, method_hashes={"native_method": "bound"}, external_runner_sha256="bound_runner",
        source_checksums={"native_source": "bound"}, baseline_input_hashes=native_hashes)
    emit(cache / "manifest.json", manifest)
    meta = dict(delivery_version="fixed_cohort_cached_v1", stage_identity="a" * 64, run_id="cached_regional__" + "a" * 16,
        data_mode="real", grid_definition_id="native_transport_fixture", geographic_cells=count,
        scope=dict(kind="fixed_cached_national_regional_cohort", data_mode="real", evaluated_cells=count),
        source_checksums=manifest["source_checksums"], actual_working_code_sha256=manifest["method_hashes"],
        external_runner_sha256=manifest["external_runner_sha256"], baseline_lineage=dict(path=str(baseline), run_id="native_fixture", run_metadata_sha256=baseline_sha),
        input_cache=dict(manifest_path=str(cache / "manifest.json"), manifest_sha256=file_digest(cache / "manifest.json"),
                         cache_identity="fixture", output_hashes=hashes, baseline_run_id="native_fixture"))
    emit(folder / "run_metadata.json", meta)
    rebind(folder)
    assert FAST_REQUIRED.issubset(meta := json.loads((folder / "run_metadata.json").read_text())["output_hashes"])
    return tmp_path, folder, baseline, cache


def test_fast_region_states_never_reports_partial_unknown_membership(fast_artifacts):
    root, folder, _, _ = fast_artifacts
    geography = pd.read_parquet(folder / "us_grid_dataset.parquet")
    regions = pd.read_parquet(folder / "candidate_regions.parquet")
    for members in regions.member_grid_ids:
        ids = json.loads(members) if isinstance(members, str) else list(members)
        if len(ids) > 1:
            geography.loc[geography.grid_id == ids[-1], "state_abbr_primary"] = None
            break
    else:
        pytest.fail("Accepted fixture must contain a multi-cell region")
    geography.to_parquet(folder / "us_grid_dataset.parquet", index=False)
    rebind(folder)
    result = ModelArtifactReader(root / ".responses", root).run(folder)
    assert any(region["region_states"] is None for region in result["regions"])


def test_fast_reader_uses_fresh_persisted_values_without_archived_physics(fast_artifacts, monkeypatch):
    root, folder, baseline, _ = fast_artifacts
    reader = ModelArtifactReader(root / ".responses", root)
    original = reader.table
    def read(path, name, **kwargs):
        assert not path.is_relative_to(baseline), "Run hydration must not load archived model outputs"
        return original(path, name, **kwargs)
    monkeypatch.setattr(reader, "table", read)
    result = reader.run(folder)
    assert result["analysis_mode"] == "cached_regional"
    assert result["analysis"]["diagnostics_status"] == "NOT_ASSESSED"
    assert "national_fine_surface" not in result["analysis"]
    assert result["regions"]
    for region in result["regions"]:
        assert region["overall_score"] == 12.34 and region["rank"] == 3
        assert region["sensitivity"] is None
        assert next(m for m in region["raw_metrics"] if m["id"] == "e_facility_mwh")["value"] == 123456
        assert region["verification_required"]


@pytest.mark.parametrize("target", ["ranked_cells.parquet", "representative_evidence.parquet", "cache"])
def test_fast_content_corruption_never_uses_a_warm_response(fast_artifacts, target):
    root, folder, _, cache = fast_artifacts
    reader = ModelArtifactReader(root / ".responses", root)
    reader.run_bytes(folder)
    path = cache / "compact.parquet" if target == "cache" else folder / target
    stat = path.stat()
    content = bytearray(path.read_bytes())
    content[0] ^= 1
    path.write_bytes(content)
    os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns))
    with pytest.raises(ApiError, match="checksum mismatch"):
        reader.run_bytes(folder)


def test_native_window_layers_retain_unknown_and_check_the_native_part(fast_artifacts):
    root, folder, baseline, _ = fast_artifacts
    reader = ModelArtifactReader(root / ".responses", root)
    layer = reader.layer(folder, "grid", sublayer="screening@native_fixture")
    assert layer["data"]["features"]
    assert any(f["properties"]["unknowns"] for f in layer["data"]["features"])
    with pytest.raises(ApiError, match="regional search area"):
        reader.layer(folder, "grid")
    path = baseline / "parts/native_fixture/feature_provenance.parquet"
    path.write_bytes(b"damaged native part")
    with pytest.raises(ApiError, match="native layer checksum mismatch"):
        reader.layer(folder, "power_carbon", sublayer="carbon_intensity@native_fixture")


def test_cache_path_escape_and_inconsistent_scope_fail_closed(fast_artifacts):
    root, folder, _, _ = fast_artifacts
    meta = json.loads((folder / "run_metadata.json").read_text())
    meta["input_cache"]["manifest_path"] = str(root / "outside/manifest.json")
    emit(folder / "run_metadata.json", meta)
    with pytest.raises(ApiError, match="escapes"):
        verify_fast_artifacts(root, folder)


@pytest.mark.parametrize("weighting", ["equal", "user", "ahp"])
def test_fast_configuration_comes_from_fresh_submitted_and_native_parameters(fast_artifacts, weighting):
    from frontend.server.serialization import GROUPS, snapshot_configuration
    root, folder, _, _ = fast_artifacts
    submitted = dict(peak_it_power_mw=130, average_load_percent=73, target_opening_year=2037, lifetime_years=17,
        cooling="air_dry_assumed", weighting=weighting, screening_mode="STRICT", group_weights=dict(zip(GROUPS, [.1, .2, .3, .4])),
        ahp_matrix=[[1.] * 4 for _ in range(4)] if weighting == "ahp" else None)
    snapshot = json.loads((folder / "config_snapshot.json").read_text())
    snapshot["submitted_facility"] = submitted
    snapshot["facility"] = dict(peak_it_power_mw=130, average_it_load_factor=.73, target_opening_year=2037,
        operating_lifetime_years=17, cooling_designs=["air_dry_assumed"], screening_mode="STRICT")
    snapshot["run"].update(weighting_method=weighting, screening_mode="STRICT")
    emit(folder / "config_snapshot.json", snapshot)
    rebind(folder)
    assert snapshot_configuration(folder) == submitted
    snapshot["facility"]["peak_it_power_mw"] = 100
    emit(folder / "config_snapshot.json", snapshot)
    rebind(folder)
    with pytest.raises(ApiError, match="configuration"):
        snapshot_configuration(folder)


def test_legacy_narrow_geometry_without_all_cell_state_attribution_stays_unknown(fast_artifacts):
    root, folder, _, _ = fast_artifacts
    geography = pd.read_parquet(folder / "us_grid_dataset.parquet").drop(columns="state_abbr_primary")
    geography.to_parquet(folder / "us_grid_dataset.parquet", index=False)
    rebind(folder)
    result = ModelArtifactReader(root / ".responses", root).run(folder)
    assert result["regions"] and all(r["region_states"] is None for r in result["regions"])


def test_empty_strict_result_reports_all_evaluated_cells_without_a_winner(fast_artifacts):
    root, folder, _, _ = fast_artifacts
    regions = pd.read_parquet(folder / "candidate_regions.parquet")
    regions.iloc[:0].to_parquet(folder / "candidate_regions.parquet", index=False)
    emit(folder / "candidate_regions.geojson", {"type": "FeatureCollection", "features": []})
    for name in ("representative_evidence", "representative_screening", "representative_geography", "representative_provenance"):
        frame = pd.read_parquet(folder / (name + ".parquet"))
        frame.iloc[:0].to_parquet(folder / (name + ".parquet"), index=False)
    ranked = pd.read_parquet(folder / "ranked_cells.parquet")
    ranked["eligible"] = False
    ranked["rankable"] = False
    ranked["mcda_rank"] = None
    ranked["mcda_score"] = None
    ranked.to_parquet(folder / "ranked_cells.parquet", index=False)
    snapshot = json.loads((folder / "config_snapshot.json").read_text())
    snapshot["run"]["screening_mode"] = "STRICT"
    snapshot["submitted_facility"]["screening_mode"] = "STRICT"
    snapshot["facility"]["screening_mode"] = "STRICT"
    emit(folder / "config_snapshot.json", snapshot)
    rebind(folder)
    result = ModelArtifactReader(root / ".responses", root).run(folder)
    assert result["state"] == "EMPTY" and result["regions"] == []
    assert result["analyzed_cell_count"] > 0
    assert result["analysis"]["diagnostics_status"] == "NOT_ASSESSED"
    assert result["decision_brief"] is None
    assert {s["id"] for s in result["scenarios"] if s["available"]} == {"current"}


@pytest.mark.parametrize("case", ["metadata_only", "manifest_only", "mismatch", "both_empty", "content_drift"])
def test_new_runtime_guard_binding_rejects_incomplete_or_changed_evidence(fast_artifacts, case):
    root, folder, _, cache = fast_artifacts
    guard = root / "src/dc_locator/model/enhanced.py"
    guard.parent.mkdir(parents=True)
    guard.write_bytes(b"# opaque runtime guard fixture\n")
    expected = {guard.relative_to(root).as_posix(): file_digest(guard)}
    meta = json.loads((folder / "run_metadata.json").read_text())
    manifest = json.loads((cache / "manifest.json").read_text())
    if case != "manifest_only":
        meta["guard_hashes"] = expected
    if case != "metadata_only":
        manifest["guard_hashes"] = expected
    if case == "mismatch":
        meta["guard_hashes"] = dict.fromkeys(expected, "f" * 64)
    if case == "both_empty":
        meta["guard_hashes"] = manifest["guard_hashes"] = {}
    if case == "content_drift":
        stat = guard.stat()
        guard.write_bytes(b"# opaque runtime guard fixturE\n")
        os.utime(guard, ns=(stat.st_atime_ns, stat.st_mtime_ns))
    emit(cache / "manifest.json", manifest)
    meta["input_cache"]["manifest_sha256"] = file_digest(cache / "manifest.json")
    emit(folder / "run_metadata.json", meta)
    with pytest.raises(ApiError, match="guard"):
        verify_fast_artifacts(root, folder)


def test_new_guard_binding_verifies_current_content_and_old_both_absent_remains_readable(fast_artifacts):
    root, folder, _, cache = fast_artifacts
    verify_fast_artifacts(root, folder)
    guard = root / "src/dc_locator/model/enhanced.py"
    guard.parent.mkdir(parents=True)
    guard.write_bytes(b"# opaque runtime guard fixture\n")
    expected = {guard.relative_to(root).as_posix(): file_digest(guard)}
    meta = json.loads((folder / "run_metadata.json").read_text())
    manifest = json.loads((cache / "manifest.json").read_text())
    meta["guard_hashes"] = manifest["guard_hashes"] = expected
    emit(cache / "manifest.json", manifest)
    meta["input_cache"]["manifest_sha256"] = file_digest(cache / "manifest.json")
    emit(folder / "run_metadata.json", meta)
    assert verify_fast_artifacts(root, folder)["guard_hashes"] == expected
