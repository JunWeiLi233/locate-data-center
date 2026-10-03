"""Phase 6 contracts and the accepted-data pre-holdout integration path."""

from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path
from types import SimpleNamespace

import geopandas as gpd
import numpy as np
import pandas as pd
import pytest
import shapely
from pydantic import ValidationError

from dc_locator.io import read_parquet
from dc_locator.model.metrics import json_text
from dc_locator.model.validation.analysis import compare_ranked_cases, summarize_case, summarize_fixed_regions
from dc_locator.model.validation.config import Phase6Config, load_phase6_config
import dc_locator.model.validation.freeze as freeze_module
from dc_locator.model.validation.freeze import verify_freeze
from dc_locator.model.validation.runner import _data_quality, _resolution_summary, _verify_build_manifest, run_phase6
from dc_locator.model.validation.schemas import AlternativeRankRangeRow


RANKED = "runs/phase5/integrated/enhanced/bau_2030/exploratory/decision/ranked_cells.parquet"
MEMBERSHIP = "runs/phase5/integrated/enhanced/bau_2030/exploratory/decision/region_membership.parquet"


def ranked_pair():
    base = read_parquet(RANKED)
    case = base.copy()
    case["scenario_id"] = case.scenario_id + "__fixture"
    return base, case


@pytest.mark.parametrize("field,value", [
    ("grid_definition_id", "wrong"),
    ("data_mode", "synthetic"),
    ("facility_id", "wrong"),
])
def test_comparison_rejects_incompatible_identity(field, value):
    base, case = ranked_pair()
    case[field] = value
    with pytest.raises(ValueError, match=field):
        compare_ranked_cases(base, case, evaluation_version="v", freeze_id="f", case_id="c", case_category="land", k=10, case_metadata={})


@pytest.mark.parametrize("field", ["eligible", "rankable", "hard_fail", "critical_unknown", "conditional"])
def test_comparison_rejects_string_boolean_flags(field):
    base, case = ranked_pair()
    case[field] = case[field].map({True: "True", False: "False"})
    with pytest.raises(ValueError, match="boolean"):
        compare_ranked_cases(base, case, evaluation_version="v", freeze_id="f", case_id="c", case_category="land", k=10, case_metadata={})


def test_comparison_rejects_ranked_strict_unknown():
    base, case = ranked_pair()
    case["mode"] = "STRICT"
    case["conditional"] = False
    with pytest.raises(ValueError, match="strict UNKNOWN"):
        compare_ranked_cases(base, case, evaluation_version="v", freeze_id="f", case_id="c", case_category="screening", k=10, case_metadata={})


def test_driver_mean_includes_known_zero_deltas():
    base, case = ranked_pair()
    comparison = compare_ranked_cases(base, case, evaluation_version="v", freeze_id="f", case_id="c", case_category="weights", k=10, case_metadata={})
    values = []
    for index in range(len(comparison)):
        values.append(json_text({
            "annual_electricity_co2e": 0.1,
            "annual_site_water_consumption": 5.0 if index == 0 else 0.0,
            "local_baseline_water_stress": 0.0,
            "transmission_proximity": 0.0,
            "suitable_land_fraction": 0.0,
        }))
    comparison["contribution_delta_json"] = values
    summary = summarize_case(comparison, case, evaluation_version="v", freeze_id="f", case_id="c", case_category="weights", k=10, weighting_method="user")
    assert summary["main_driver"] == "annual_electricity_co2e"
    assert summary["main_driver_mean_abs_contribution_change"] == pytest.approx(0.1)


def test_fixed_region_partial_membership_has_no_survivor_only_mean():
    _, case = ranked_pair()
    membership = read_parquet(MEMBERSHIP)
    target = membership.iloc[0]
    selected = case.grid_id.eq(target.grid_id) & case.design_id.eq(target.design_id)
    case.loc[selected, ["mcda_rank", "mcda_score"]] = np.nan
    case.loc[selected, "rankable"] = False
    result = summarize_fixed_regions(
        membership, case, evaluation_version="v", freeze_id="f", case_id="partial",
        baseline_scenario_id=str(membership.scenario_id.iloc[0]),
    )
    row = result.loc[result.region_id.eq(target.region_id) & result.design_id.eq(target.design_id)].iloc[0]
    assert row.unranked_members == 1
    assert pd.isna(row.case_rank_mean)
    assert row.case_rank_range_basis == "ranked_members_only"
    assert row.case_rank_mean_basis == "all_members_only_or_null"


def test_phase6_config_requires_one_positive_holdout_count_and_one_ablation_per_group():
    document = load_phase6_config().model_dump(mode="json")
    document["holdout"]["expected_holdout_cells"] = 0
    with pytest.raises(ValidationError):
        Phase6Config.model_validate(document)
    document = load_phase6_config().model_dump(mode="json")
    document["ablation_cases"][1]["removed_group"] = document["ablation_cases"][0]["removed_group"]
    document["ablation_cases"].append({"case_id": "extra", "removed_group": "grid_infrastructure"})
    with pytest.raises(ValidationError, match="exactly once"):
        Phase6Config.model_validate(document)


def test_data_quality_counts_known_rows_once_and_partial_coverage_from_coverage():
    provenance = pd.DataFrame({
        "metric": ["m", "m"],
        "value": [1.0, None],
        "value_text": ["also-present", None],
        "status": ["observed", "unknown"],
        "coverage_frac": [0.5, 0.0],
        "source_id": ["s", "s"],
    })
    row = _data_quality(provenance, "fixture").iloc[0]
    assert row.rows == 2
    assert row.known_rows == 1
    assert row.unknown_rows == 1
    assert row.partial_coverage_rows == 1


def _resolution_case(grid):
    ranked = pd.DataFrame({
        "grid_id": grid.grid_id,
        "design_id": ["d"] * len(grid),
        "rankable": [True] * len(grid),
        "mcda_score": np.arange(len(grid), dtype=float),
    })
    members = pd.DataFrame({"grid_id": grid.grid_id.iloc[:1], "design_id": ["d"]})
    regions = pd.DataFrame({"design_id": ["d"]})
    return SimpleNamespace(result={"ranked_cells": ranked, "region_membership": members, "candidate_regions": regions})


def test_resolution_uses_topological_equal_footprint_not_vertex_encoding():
    fine_geometries, fine_ids = [], []
    for row in range(4):
        for col in range(4):
            fine_geometries.append(shapely.box(-180000 + col * 10000, 1060000 + row * 10000, -170000 + col * 10000, 1070000 + row * 10000))
            fine_ids.append(f"f{row}{col}")
    coarse_geometries = [
        shapely.box(-180000, 1060000, -160000, 1080000), shapely.box(-160000, 1060000, -140000, 1080000),
        shapely.box(-180000, 1080000, -160000, 1100000), shapely.box(-160000, 1080000, -140000, 1100000),
    ]
    fine = gpd.GeoDataFrame({"grid_id": fine_ids, "grid_definition_id": ["fine"] * 16, "study_area_intersection_km2": [100.0] * 16}, geometry=fine_geometries, crs=5070)
    coarse = gpd.GeoDataFrame({"grid_id": ["c0", "c1", "c2", "c3"], "grid_definition_id": ["coarse"] * 4, "study_area_intersection_km2": [400.0] * 4}, geometry=coarse_geometries, crs=5070)
    config = load_phase6_config()
    result = _resolution_summary(fine, coarse, _resolution_case(fine), _resolution_case(coarse), config)
    assert len(result) == 2
    assert set(result.selected_union_km2) == {100.0, 400.0}
    assert set(result.fine_coarse_selected_intersection_km2) == {100.0}
    assert set(result.fine_coarse_selected_union_km2) == {400.0}
    assert set(result.fine_coarse_selected_jaccard) == {0.25}


def test_alternative_rank_range_requires_complete_case_counts_and_exact_range():
    values = {
        "evaluation_version": "v", "freeze_id": "f", "grid_id": "g", "design_id": "d",
        "baseline_scenario_id": "s", "base_rank": 2, "evaluated_cases": 3,
        "ranked_cases": 2, "unranked_cases": 1, "minimum_rank": 2, "maximum_rank": 5,
        "rank_range": 3, "scope": "separate contexts",
    }
    assert AlternativeRankRangeRow(**values).rank_range == 3
    with pytest.raises(ValidationError, match="cover every"):
        AlternativeRankRangeRow(**{**values, "unranked_cases": 0})
    with pytest.raises(ValidationError, match="endpoints"):
        AlternativeRankRangeRow(**{**values, "rank_range": 2})


def test_holdout_build_manifest_binds_frozen_builder_inputs_and_repeats(tmp_path):
    root = tmp_path
    dataset = root / "runs" / "phase6" / "inputs" / "holdout25"
    enhanced = dataset / "enhanced"
    repeated = dataset / "repeat"
    preselection = root / "runs" / "phase6" / "inputs" / "preselection"
    freeze_dir = root / "runs" / "phase6" / "freeze" / "v1"
    for directory in (enhanced, repeated, preselection, freeze_dir):
        directory.mkdir(parents=True, exist_ok=True)
    geography, provenance = enhanced / "enhanced_grid_dataset.parquet", enhanced / "enhanced_feature_provenance.parquet"
    geography.write_bytes(b"geography")
    provenance.write_bytes(b"provenance")
    repeat_geography, repeat_provenance = repeated / geography.name, repeated / provenance.name
    repeat_geography.write_bytes(geography.read_bytes())
    repeat_provenance.write_bytes(provenance.read_bytes())
    script = preselection / "build_inputs.py"
    protected = preselection / "source_config.json"
    script.write_text("# frozen builder\n", encoding="utf-8")
    protected.write_text("{}\n", encoding="utf-8")
    freeze_path = freeze_dir / "freeze_manifest.json"
    freeze_path.write_text("{}\n", encoding="utf-8")
    records = {
        str(script.relative_to(root)): {"path": str(script.relative_to(root)), "sha256": _digest(script)},
        str(protected.relative_to(root)): {"path": str(protected.relative_to(root)), "sha256": _digest(protected)},
    }
    freeze = {"software_files": {}, "input_files": records}
    binding = dataset / "evaluation_manifest.json"
    binding.write_text(json_text({
        "schema_version": "1.0.0", "phase6_freeze_id": "freeze", "dataset_id": "holdout25",
        "grid_definition_id": "grid", "grid_ids": ["g"],
        "output_hashes": {
            str(geography.relative_to(dataset)): _digest(geography),
            str(provenance.relative_to(dataset)): _digest(provenance),
        },
        "repeat_output_hashes": {
            str(repeat_geography.relative_to(dataset)): _digest(repeat_geography),
            str(repeat_provenance.relative_to(dataset)): _digest(repeat_provenance),
        },
        "repeat_identical": True,
        "build_evidence": {
            "build_script": {"path": "../preselection/build_inputs.py", "sha256": _digest(script)},
            "freeze_manifest_sha256": _digest(freeze_path),
            "protected_input_hashes": {"../preselection/source_config.json": _digest(protected)},
        },
    }), encoding="utf-8")
    document = _verify_build_manifest(root, binding, "holdout25", "freeze", geography, provenance, freeze_path, freeze)
    assert document["repeat_identical"] is True
    protected.write_text('{"changed": true}\n', encoding="utf-8")
    with pytest.raises(ValueError, match="missing or changed"):
        _verify_build_manifest(root, binding, "holdout25", "freeze", geography, provenance, freeze_path, freeze)


def _digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def test_freeze_requires_and_verifies_restorable_hash_bound_snapshot(tmp_path, monkeypatch):
    software = tmp_path / "software.py"
    source_input = tmp_path / "input.dat"
    software.write_text("x=1\n", encoding="utf-8")
    source_input.write_text("input\n", encoding="utf-8")
    snapshot = tmp_path / "snapshot" / "software.py"
    snapshot.parent.mkdir(parents=True)
    snapshot.write_bytes(software.read_bytes())
    archive = tmp_path / "snapshot.zip"
    with zipfile.ZipFile(archive, "w") as stream:
        stream.write(snapshot, "software.py")
    software_records = {"software.py": {"path": str(software), "sha256": _digest(software), "bytes": software.stat().st_size, "directory_member_count": None}}
    input_records = {str(source_input): {"path": str(source_input), "sha256": _digest(source_input), "bytes": source_input.stat().st_size, "directory_member_count": None}}
    payload = {"evaluation_version": "phase6_v1", "software": {"software.py": _digest(software)}, "inputs": {str(source_input): _digest(source_input)}}
    fingerprint = hashlib.sha256(json_text(payload).encode()).hexdigest()
    document = {
        "schema_version": "1.0.0", "status": "FROZEN_BEFORE_HOLDOUT", "freeze_id": f"phase6-v1-{fingerprint[:16]}",
        "evaluation_version": "phase6_v1", "created_at_utc": "2026-01-01T00:00:00+00:00", "holdout_feature_evaluation_started": False,
        "fingerprint_sha256": fingerprint, "software_files": software_records, "input_files": input_records,
        "snapshot_files": {"software.py": _digest(snapshot)},
        "snapshot_archive": {"path": str(archive), "sha256": _digest(archive), "bytes": archive.stat().st_size},
        "change_policy": "new version after evaluation",
    }
    manifest = tmp_path / "freeze_manifest.json"
    manifest.write_text(json_text(document), encoding="utf-8")
    monkeypatch.setattr(freeze_module, "_root", lambda: tmp_path)
    monkeypatch.setattr(freeze_module, "_software_files", lambda root: [software])
    assert verify_freeze(manifest)["freeze_id"] == document["freeze_id"]
    software.write_text("x=2\n", encoding="utf-8")
    with pytest.raises(ValueError, match="new evaluation version"):
        verify_freeze(manifest)


def test_phase6_real_preholdout_recomputes_every_case_and_exports_rank_ranges(tmp_path):
    import yaml
    from dc_locator.paths import project_root
    document=yaml.safe_load((project_root()/'configs/phase6.yaml').read_text(encoding='utf-8'))
    document['software_evidence']=str(tmp_path/'absent_current_preflight_evidence.json')
    config=tmp_path/'current_preflight.yaml'
    config.write_text(yaml.safe_dump(document,sort_keys=False),encoding='utf-8')
    result = run_phase6(config_path=config, output_dir=tmp_path, include_holdout=False)
    assert result['report']['software_verification']['status']=='PENDING'
    assert result["manifest"]["cases"] == 28
    assert result["manifest"]["sensitivity_rows"] == 28 * 84
    strict = next(case for case in result["cases"] if case.case_id == "screening_strict")
    assert strict.result["ranked_cells"].rankable.sum() == 0
    carbon = next(case for case in result["cases"] if case.case_id == "carbon_half_historical_intensity")
    baseline = result["cases"][0]
    assert carbon.result["ranked_cells"].raw_annual_electricity_co2e.to_numpy() == pytest.approx(
        baseline.result["ranked_cells"].raw_annual_electricity_co2e.to_numpy() * 0.5
    )
    assumptions = json.loads(carbon.result["ranked_cells"].assumptions_json.iloc[0])["phase6_validation_case"]
    evidence = json.loads(carbon.result["ranked_cells"].metric_metadata_json.iloc[0])["grid_carbon_intensity_kg_per_mwh"]["source_evidence"]
    assert assumptions["carbon_source_transform"]["input_source_year"] == "2023"
    assert evidence["source_field"] == "SRC2ERTA" and evidence["status"] == "scenario"
    assert "not publisher-observed SRC2ERTA" in evidence["aggregation_method"]
    ranges = pd.read_csv(tmp_path / "alternative_rank_ranges.csv")
    assert len(ranges) == 84
    assert (ranges.evaluated_cases == 28).all()
    assert (ranges.ranked_cases + ranges.unranked_cases == 28).all()


@pytest.mark.parametrize("value", ["False", 0, 1, None])
def test_phase6_rejects_nonboolean_holdout_control(tmp_path, value):
    with pytest.raises(ValueError, match="explicit boolean"):
        run_phase6(output_dir=tmp_path, include_holdout=value)


@pytest.mark.parametrize("relative", ["runs/phase6/inputs/overwrite", "runs/phase6/freeze/overwrite"])
def test_phase6_rejects_outputs_inside_inputs_or_freeze(relative):
    with pytest.raises(ValueError, match="cannot overwrite"):
        run_phase6(output_dir=relative, include_holdout=False)
