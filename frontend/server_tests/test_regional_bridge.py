"""Regional transport regressions using private copies of accepted evidence.

Catalog values describe the transport fixture, not a new scientific run.
"""
from __future__ import annotations

import json
import shutil
import sys
from types import ModuleType
from pathlib import Path

import pandas as pd
import pytest
import yaml

from frontend.server.serialization import ApiError, ArtifactReader
from frontend.server.service import GROUPS, LocatorService

ROOT = Path(__file__).resolve().parents[2]
ACCEPTED = ROOT / "runs/phase7/root_v2_exploratory"


@pytest.fixture
def regional(tmp_path):
    folder = tmp_path / "regional"
    part = folder / "parts/parent_fixture"
    part.mkdir(parents=True)
    for name in ("us_grid_dataset", "feature_provenance", "site_performance", "screening_results", "ranked_cells"):
        shutil.copy2(ACCEPTED / f"{name}.parquet", part / f"{name}.parquet")
    for name in ("run_metadata.json", "config_snapshot.json", "screening_summary.json", "candidate_regions.parquet",
                 "candidate_regions.geojson", "profile_snapshot.json", "weight_result.json"):
        shutil.copy2(ACCEPTED / name, folder / name)
    ranked = pd.read_parquet(ACCEPTED / "ranked_cells.parquet")
    ranked.drop(columns=[c for c in ranked if c.endswith("_json")]).to_parquet(folder / "ranked_cells.parquet", index=False)
    representatives = pd.read_parquet(folder / "candidate_regions.parquet").representative_grid_id.unique().tolist()
    catalog = {"schema_version": "1.0.0", "analysis_level": "regional", "parent_run_path": "runs/parent_fixture",
               "parent_run_id": "parent_fixture", "grid_definition_id": "transport_fixture", "cell_size_m": 1000,
               "maximum_region_extent_km": 20, "refined_cells": 42, "national_cells": 3384,
               "shortlisted_parent_cells": 690, "refined_parent_cells": 1, "refined_area_km2": 42,
               "shortlisted_parent_area_km2": 1725000, "ranking_universe": "all_evaluated_refined_alternatives",
               "representative_parts": dict.fromkeys(representatives, "parts/parent_fixture"),
               "parts": [{"parent_grid_id": "parent_fixture", "path": "parts/parent_fixture", "cell_count": 42}]}
    (folder / "regional_catalog.json").write_text(json.dumps(catalog), encoding="utf-8")
    return folder


def test_regional_result_reads_filtered_representatives_with_exact_global_values(regional, tmp_path, monkeypatch):
    reader = ArtifactReader(tmp_path / "responses")
    original = reader.table
    reads = []
    def recorded(folder, name, **kwargs):
        frame = original(folder, name, **kwargs)
        reads.append((folder, name, kwargs, len(frame)))
        return frame
    monkeypatch.setattr(reader, "table", recorded)
    result = reader.run(regional)
    assert result["schema_version"] == "1.8.0"
    assert result["analyzed_cell_count"] == 42
    assert "partial regional refinement" in result["scope"]
    assert result["analysis"]["cell_size_m"] == 1000
    assert result["analysis"]["maximum_region_extent_km"] == 20
    assert result["analysis"]["parent_run_id"] == "parent_fixture"
    assert result["analysis"]["shortlisted_parent_cells"] == 690
    assert {s["id"] for s in result["scenarios"] if s["available"]} == {"current"}
    native = pd.read_parquet(regional / "ranked_cells.parquet")
    for region in result["regions"]:
        assert region["parent_grid_id"] == "parent_fixture"
        exact = native[(native.grid_id == region["representative_grid_id"]) & (native.design_id == region["design_id"])].iloc[0]
        assert region["rank"] == exact.mcda_rank and region["overall_score"] == exact.mcda_score
        electricity = next(m for m in region["raw_metrics"] if m["id"] == "e_facility_mwh")
        assert electricity["status"] == "calculated" and electricity["value"] == exact.e_facility_mwh
        assert region["verification_required"]
    private = [r for r in reads if r[0].name == "parent_fixture" and r[1] in {"us_grid_dataset", "feature_provenance", "site_performance", "screening_results"}]
    assert len(private) == 4 and all(r[2].get("grid_ids") for r in private)
    assert next(r[3] for r in private if r[1] == "us_grid_dataset") == 1


def test_regional_sensitivity_reads_only_representative_cells(regional, tmp_path, monkeypatch):
    for name in ("alternative_rank_ranges", "sensitivity_results"):
        shutil.copy2(ACCEPTED / f"{name}.parquet", regional / f"{name}.parquet")
    reader = ArtifactReader(tmp_path / "responses")
    original = reader.table
    reads = []
    def recorded(folder, name, **kwargs):
        if name in {"alternative_rank_ranges", "sensitivity_results"}:
            reads.append((name, kwargs.get("grid_ids")))
        return original(folder, name, **kwargs)
    monkeypatch.setattr(reader, "table", recorded)
    result = reader.run(regional)
    representatives = pd.read_parquet(regional / "candidate_regions.parquet").representative_grid_id.unique().tolist()
    assert len(reads) == 2 and all(ids == representatives for _, ids in reads)
    ranges = pd.read_parquet(ACCEPTED / "alternative_rank_ranges.parquet")
    for region in result["regions"]:
        native = ranges[(ranges.grid_id == region["representative_grid_id"]) &
                        (ranges.design_id == region["design_id"]) &
                        (ranges.baseline_scenario_id == region["scenario_id"])].iloc[0]
        assert region["sensitivity"]["base_rank"] == native.base_rank
        assert region["sensitivity"]["min_rank"] == native.minimum_rank
        assert region["sensitivity"]["max_rank"] == native.maximum_rank


def test_regional_place_label_resolves_but_region_states_stays_null(regional, tmp_path):
    # The regional-catalog path only loads representative geography rows (see
    # ArtifactReader._regional_representatives), so full region membership cannot be
    # resolved here; region_states must stay null rather than report a partial list.
    reader = ArtifactReader(tmp_path / "responses")
    result = reader.run(regional)
    geography = pd.read_parquet(ACCEPTED / "us_grid_dataset.parquet").set_index("grid_id")
    native = pd.read_parquet(regional / "candidate_regions.parquet").set_index("region_id")
    assert result["regions"]
    for region in result["regions"]:
        row = geography.loc[region["representative_grid_id"]]
        assert region["place_label"] == f"{row.county_name_primary}, {row.state_abbr_primary}"
        assert region["cell_count"] == native.loc[region["region_id"], "n_cells"]
        assert region["area_km2"] == native.loc[region["region_id"], "total_area_km2"]
        assert region["region_states"] is None


def test_empty_regional_result_explains_recorded_validation_reason(regional, tmp_path, monkeypatch):
    import frontend.server.serialization as module
    for name in ("ranked_cells.parquet", "candidate_regions.parquet"):
        # Native zero-row regional outputs infer null types for empty object columns.
        pd.read_parquet(regional / name).iloc[:0].to_parquet(regional / name, index=False)
    (regional / "candidate_regions.geojson").write_text('{"type":"FeatureCollection","features":[]}', encoding="utf-8")
    catalog = json.loads((regional / "regional_catalog.json").read_text())
    catalog.update(refined_cells=0, refined_parent_cells=0, shortlisted_parent_cells=0,
                   refined_area_km2=0, shortlisted_parent_area_km2=0, parts=[], representative_parts={})
    (regional / "regional_catalog.json").write_text(json.dumps(catalog), encoding="utf-8")
    reason = "No evaluated national representative qualifies; no fine coverage or winner invented."
    (regional / "validation_report.json").write_text(json.dumps({"validation_scope": "empty_refined_universe", "reason": reason}), encoding="utf-8")
    calls = []
    def unavailable_brief(*args, **kwargs):
        calls.append(args)
        raise ValueError("Select an explicit scenario; the report never chooses an external scenario")
    monkeypatch.setattr(module, "build_submission_brief", unavailable_brief)
    result = ArtifactReader(tmp_path / "responses").run(regional)
    assert result["state"] == "EMPTY" and result["regions"] == [] and result["analyzed_cell_count"] == 0
    assert result["decision_brief"] is None and result["decision_brief_unavailable_reason"] == reason
    assert reason in result["warnings"]
    assert result["analysis"]["parent_run_id"] == catalog["parent_run_id"]
    assert result["analysis"]["parent_run_path"] == catalog["parent_run_path"]
    assert result["analysis"]["national_cells"] == 3384
    assert result["scenario_id"] == "current"
    assert {s["id"] for s in result["scenarios"] if s["available"]} == {"current"}
    assert not calls, "An empty fine universe must not ask a brief builder to choose a scenario"


def test_regional_layers_require_active_window_and_keep_indicator_selection(regional, tmp_path):
    reader = ArtifactReader(tmp_path / "responses")
    with pytest.raises(ApiError) as error:
        reader.layer(regional, "grid")
    assert error.value.code == "regional_window_required"
    region = reader.run(regional)["regions"][0]
    grid = reader.layer(regional, "grid", sublayer=region["region_id"])
    assert len(grid["data"]["features"]) == 42
    flood = reader.layer(regional, "climate", sublayer="flood@parent_fixture")
    assert flood["label"] == "Mapped flood overlap"
    assert "active refinement window" in flood["warning"]
    with pytest.raises(ApiError):
        reader.layer(regional, "grid", sublayer="screening@../../elsewhere")
    with pytest.raises(ApiError):
        reader.layer(regional, "climate", sublayer="hurricane@parent_fixture")


def test_regional_catalog_cannot_escape_output_or_hide_missing_part(regional, tmp_path):
    reader = ArtifactReader(tmp_path / "responses")
    assert reader.run(regional)["regions"]
    evidence = regional / "parts/parent_fixture/feature_provenance.parquet"
    evidence.unlink()
    with pytest.raises(ApiError, match="feature_provenance.parquet"):
        reader.run(regional)
    catalog = json.loads((regional / "regional_catalog.json").read_text())
    catalog["parts"][0]["path"] = "../../outside"
    (regional / "regional_catalog.json").write_text(json.dumps(catalog))
    with pytest.raises(ApiError):
        ArtifactReader(tmp_path / "responses").run(regional)


def test_regional_layer_budget_is_enforced_before_loading_window(regional, tmp_path):
    catalog = json.loads((regional / "regional_catalog.json").read_text())
    catalog["parts"][0]["cell_count"] = 10001
    (regional / "regional_catalog.json").write_text(json.dumps(catalog))
    with pytest.raises(ApiError) as error:
        ArtifactReader(tmp_path / "responses").layer(regional, "grid", sublayer="parent_fixture")
    assert error.value.code == "layer_budget"


def test_registry_registers_completed_regional_baseline(monkeypatch, tmp_path):
    seen = []
    monkeypatch.setattr(LocatorService, "register_run", lambda self, folder, **kwargs: seen.append(folder))
    LocatorService(tmp_path, start_worker=False)
    assert tmp_path / "runs/regional_refinement_v3" in seen
    assert tmp_path / "runs/regional_refinement_v4" in seen
    assert seen.index(tmp_path / "runs/regional_refinement_v3") < seen.index(tmp_path / "runs/regional_refinement_v4")
    assert tmp_path / "runs/cleanview_regional_v2" in seen
    assert seen.index(tmp_path / "runs/regional_refinement_v4") < seen.index(tmp_path / "runs/cleanview_regional_v2")


@pytest.mark.parametrize("completed_revision", [True, False])
def test_corrected_baseline_registration_defaults_and_historical_access(monkeypatch, tmp_path, completed_revision):
    import frontend.server.service as module
    folders = ["regional_refinement_v3", "regional_refinement_v4", "cleanview_regional_v2"]
    for name in folders:
        folder = tmp_path / "runs" / name
        folder.mkdir(parents=True)
        metadata = {"run_id": "registration_" + name, "scope": {"data_mode": "real", "scope": "regional_refinement"},
                    "configuration": {"study_area": "regional_refinement"},
                    "completed_current_stages": ["rank"] if name == "cleanview_regional_v2" and not completed_revision else ["validate"]}
        (folder / "run_metadata.json").write_text(json.dumps(metadata), encoding="utf-8")
        shutil.copy2(ACCEPTED / "config_snapshot.json", folder / "config_snapshot.json")
    defaults_read_from = []
    actual = module.snapshot_configuration
    def recorded(folder):
        defaults_read_from.append(folder)
        return actual(folder)
    monkeypatch.setattr(module, "snapshot_configuration", recorded)
    service = LocatorService(tmp_path, start_worker=False)
    expected = "cleanview_regional_v2" if completed_revision else "regional_refinement_v4"
    assert service.capabilities()["latest_run_id"] == "registration_" + expected
    assert defaults_read_from == [tmp_path / "runs" / expected]
    assert service.resolve_run("registration_regional_refinement_v3") == tmp_path / "runs/regional_refinement_v3"
    assert service.resolve_run("registration_regional_refinement_v4") == tmp_path / "runs/regional_refinement_v4"


def test_completed_v4_baseline_is_preferred_and_completed_v3_remains_loadable(monkeypatch, tmp_path):
    import frontend.server.service as module
    # Metadata-only registration fixtures; no geographic values or model outputs are invented.
    for revision in (3, 4):
        folder = tmp_path / f"runs/regional_refinement_v{revision}"
        folder.mkdir(parents=True)
        metadata = {"run_id": f"registration_v{revision}_fixture", "scope": {"data_mode": "real", "scope": "regional_refinement"},
                    "configuration": {"study_area": "regional_refinement"}, "completed_current_stages": ["validate"]}
        (folder / "run_metadata.json").write_text(json.dumps(metadata), encoding="utf-8")
        shutil.copy2(ACCEPTED / "config_snapshot.json", folder / "config_snapshot.json")
    actual = module.snapshot_configuration
    defaults_read_from = []
    def recorded(folder):
        defaults_read_from.append(folder)
        return actual(folder)
    monkeypatch.setattr(module, "snapshot_configuration", recorded)
    service = LocatorService(tmp_path, start_worker=False)
    assert service.latest_run_id() == "registration_v4_fixture"
    assert service.resolve_run("registration_v3_fixture") == tmp_path / "runs/regional_refinement_v3"
    assert service.capabilities()["latest_run_id"] == "registration_v4_fixture"
    assert defaults_read_from == [tmp_path / "runs/regional_refinement_v4"]


@pytest.mark.parametrize("level", ["legacy", "regional"])
def test_land_area_uses_native_value_units_and_provenance(level, regional, tmp_path):
    folder = ACCEPTED if level == "legacy" else regional
    result = ArtifactReader(tmp_path / "responses").run(folder)
    geography = pd.read_parquet(ACCEPTED / "us_grid_dataset.parquet").set_index("grid_id")
    provenance = pd.read_parquet(ACCEPTED / "feature_provenance.parquet")
    for region in result["regions"]:
        grid = region["representative_grid_id"]
        native = provenance[(provenance.grid_id == grid) & (provenance.metric == "suitable_land_area_km2")].iloc[0]
        area = next((m for m in region["raw_metrics"] if m["id"] == "suitable_land_area_km2"), None)
        assert area is not None, "The adapter must expose the actual native metric key"
        assert area["label"] == "Mapped potentially suitable land area"
        assert area["value"] == geography.loc[grid, "suitable_land_area_km2"] == native.value
        assert area["unit"] == native.unit == "km2"
        assert area["status"] == native.status == "proxy"
        assert area["confidence"] == native.confidence
        assert area["sources"][0]["name"] == native.source_name
        assert region["verification_required"] and region["screening_status"] == "CONDITIONAL"


def test_regional_search_binds_customized_parent_and_executes_orchestrator(tmp_path, monkeypatch):
    import dc_locator.pipeline as pipeline_module
    configs = tmp_path / "configs"
    configs.mkdir()
    for name in ("run_national_exploratory.yaml", "facility.yaml", "cooling_designs.yaml"):
        shutil.copy2(ROOT / "configs" / name, configs / name)
    wrapper = {"schema_version": "3.0.0", "delivery_version": "phase9_regional_v1",
               "parent_config": "configs/run_national_exploratory.yaml", "selection": "representative_parent_cells",
               "grid_config": "configs/grid_regional.yaml", "scoring_profile": "configs/scoring_profile_regional.yaml",
               "maximum_region_extent_km": 20, "maximum_refined_cells": 200000, "maximum_batch_cells": 2500}
    (configs / "run_regional_exploratory.yaml").write_text(yaml.safe_dump(wrapper))
    for name in ("grid_regional.yaml", "scoring_profile_regional.yaml"):
        (configs / name).write_text("transport_fixture: true\n")
    facility = {"peak_it_power_mw": 130, "average_load_percent": 70, "target_opening_year": 2031, "lifetime_years": 20,
                "cooling": "air_dry_assumed", "weighting": "user", "screening_mode": "EXPLORATORY",
                "group_weights": dict(zip(GROUPS, (0.1, 0.2, 0.3, 0.4))), "ahp_matrix": None}
    class Probe:
        identity = "verified_parent_identity_fixture"
        def __init__(self, configuration, output, **kwargs):
            output.mkdir(parents=True)
    monkeypatch.setattr(pipeline_module, "Pipeline", Probe)
    calls = []
    def regional_run(configuration, output, *, root, progress):
        actual = yaml.safe_load(configuration.read_text())
        parent = yaml.safe_load((root / actual["parent_config"]).read_text())
        requirements = yaml.safe_load((root / parent["facility"]).read_text())["facilities"][0]
        assert parent["study_area"] == "conus" and requirements["peak_it_power_mw"] == 130
        assert requirements["average_it_load_factor"] == 0.7 and parent["user_group_weights"] == facility["group_weights"]
        assert actual["maximum_region_extent_km"] == 20 and actual["selection"] == "representative_parent_cells"
        output.mkdir(parents=True)
        metadata = {"run_id": "regional_execution_fixture", "scope": {"data_mode": "real", "scope": "regional_refinement"}, "completed_current_stages": ["validate"]}
        (output / "run_metadata.json").write_text(json.dumps(metadata))
        progress("regional batch 1: rank")
        calls.append((configuration, output))
        return output
    module = ModuleType("dc_locator.regional")
    module.run_regional = regional_run
    monkeypatch.setitem(sys.modules, "dc_locator.regional", module)
    service = LocatorService(tmp_path, start_worker=False)
    monkeypatch.setattr(service, "run_response", lambda identifier: json.dumps({"run_id": identifier}).encode())
    job = service.search({"facility": facility})["job_id"]
    service._execute_job(job)
    assert service.job(job)["state"] == "COMPLETE"
    assert service.job(job)["run_id"] == "regional_execution_fixture"
    assert calls[0][0].is_relative_to(tmp_path / "runs/frontend_service/configurations")
    assert calls[0][1].is_relative_to(tmp_path / "runs/frontend_service/regional_runs")
    assert service._write_regional_configuration(service._write_configuration(facility)) == calls[0][0]
