"""Focused contracts for the pure current-run validation helper."""

import copy
from dataclasses import replace
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import yaml
from pydantic import ValidationError

from dc_locator.model.decision import decide
from dc_locator.model.metrics import profile_fingerprint
from dc_locator.model.physics import simulate
from dc_locator.model.run_validation import (
    CurrentRunIdentity,
    CurrentSensitivityCase,
    CurrentValidationSettings,
    FutureValidationContext,
    validate_current_run,
)
from dc_locator.model.scenarios import make_external_scenarios
from dc_locator.model.screening import Requirement, screen
from dc_locator.geography.sources.aqueduct_future import future_period


def _identity():
    return CurrentRunIdentity(
        run_id="current-fixture",
        model_revision="phase7-test",
        model_hashes={"model.py": "a" * 64},
        config_hashes={"run.yaml": "b" * 64},
        source_hashes={"source.bin": "c" * 64},
    )


def _synthetic_inputs(mode="EXPLORATORY", *, facility_updates=None, missing_carbon=False):
    from test_model_physics import model_inputs
    from test_phase4 import decision_fixture

    geography, provenance, _, _, profile = decision_fixture()
    if missing_carbon:
        metric = "grid_carbon_intensity_kg_per_mwh"
        selected = provenance.metric.eq(metric)
        geography[metric] = np.nan
        geography[metric + "_status"] = "unknown"
        geography[metric + "_confidence"] = "unknown"
        geography[metric + "_coverage_frac"] = 0.0
        provenance.loc[selected, "value"] = np.nan
        provenance.loc[selected, "status"] = "unknown"
        provenance.loc[selected, "confidence"] = "unknown"
        provenance.loc[selected, "coverage_frac"] = 0.0
        provenance.loc[selected, "missing_reason"] = "source_nodata"
    _, _, facility, design, scenario = model_inputs()
    if facility_updates:
        facility = facility.model_copy(update=facility_updates)
    requirement = Requirement(
        requirement_id="parcel",
        metric="confirmed_developable_parcel_area_km2",
        operator="ge",
        threshold=1,
        unit="km2",
        is_critical=True,
        basis="project_assumption",
        rationale="Synthetic critical UNKNOWN fixture.",
        coverage_policy="full",
    )
    performance = simulate(geography, provenance, facility, [design], [scenario])
    _, eligibility, _ = screen(
        geography,
        provenance,
        facility,
        [design],
        [scenario],
        [requirement],
        mode=mode,
    )
    baseline = decide(
        geography,
        provenance,
        performance,
        eligibility,
        profile,
        profile_hash=profile_fingerprint(profile),
        provenance_grid_definition_id="fixture",
    )
    return geography, provenance, facility, [design], [scenario], [requirement], profile, baseline


def _validate(inputs, settings, **kwargs):
    geography, provenance, facility, designs, scenarios, requirements, profile, baseline = inputs
    return validate_current_run(
        geography=geography,
        provenance=provenance,
        facility=facility,
        designs=designs,
        physical_scenarios=scenarios,
        requirements=requirements,
        active_profile=profile,
        baseline_result=baseline,
        provenance_grid_definition_id="fixture",
        identity=_identity(),
        settings=settings,
        **kwargs,
    )


def _future_context(inputs, value):
    geography, provenance, _, _, scenarios, _, profile, _ = inputs
    geography = geography.copy()
    provenance = provenance.copy()
    geography.attrs.update(inputs[0].attrs)
    provenance.attrs.update(inputs[1].attrs)
    column = "aqueduct_bau_2030_water_stress_score"
    geography[column] = value
    geography[column + "_status"] = "scenario"
    geography[column + "_confidence"] = "high"
    geography[column + "_coverage_frac"] = 1.0
    source = provenance.loc[provenance.metric.eq("baseline_water_stress_score")].iloc[0].to_dict()
    source.update(
        metric=column,
        value=value,
        status="scenario",
        source_id="wri_aqueduct40_future",
        source_field="bau30_ws_x_s",
        data_year="2030 milestone; 2015-2045 trend window; SSP3-RCP7.0",
        missing_reason=None,
    )
    provenance = pd.concat([provenance, pd.DataFrame([source])], ignore_index=True)
    provenance.attrs.update(inputs[1].attrs)
    document = profile.model_dump(mode="json")
    document["profile_id"] = "fixture_bau_2030"
    document["description"] = "Synthetic future source-binding fixture."
    metric = next(item for item in document["metrics"] if item["metric_id"] == "local_baseline_water_stress")
    metric.update(
        column=column,
        definition="Synthetic future water-source binding fixture.",
        rationale="Same fixed preferences with a supplied scenario source binding.",
        allowed_statuses=["scenario"],
        source_id="wri_aqueduct40_future",
        source_field="bau30_ws_x_s",
    )
    profile = type(profile).model_validate(document)
    external = make_external_scenarios(scenarios[0].scenario_id, [future_period("bau", 2030)])[0]
    return FutureValidationContext(
        case_id="future_bau_2030",
        geography=geography,
        provenance=provenance,
        profile=profile,
        external_scenario=external,
        identity={"context-source": "d" * 64},
        rationale="Separately supplied native future-water fixture.",
    )


@pytest.mark.parametrize("invalid", [True, "1"])
def test_validation_policy_rejects_coerced_numeric_values(invalid):
    with pytest.raises(ValidationError, match="numeric"):
        CurrentSensitivityCase(
            case_id="weights",
            category="weights",
            basis="project_assumption",
            rationale="Typed project stress fixture.",
            group_weights={"energy": invalid},
        )
    for field in ("top_k", "max_cases"):
        values = {
            "validation_revision": "phase7-test",
            "baseline_mode": "EXPLORATORY",
            field: invalid,
        }
        with pytest.raises(ValidationError, match="integer"):
            CurrentValidationSettings.model_validate(values)


def test_weight_policy_rejects_nonmapping_input_as_validation_error():
    with pytest.raises(ValidationError, match="mapping"):
        CurrentSensitivityCase.model_validate(
            {
                "case_id": "weights",
                "category": "weights",
                "basis": "project_assumption",
                "rationale": "Malformed policy fixture.",
                "group_weights": [1, 2],
            }
        )


def test_tampered_baseline_membership_is_rejected():
    inputs = list(_synthetic_inputs())
    inputs[-1] = copy.deepcopy(inputs[-1])
    inputs[-1]["region_membership"] = inputs[-1]["region_membership"].copy()
    inputs[-1]["region_membership"]["region_id"] = "tampered-region"
    settings = CurrentValidationSettings(
        validation_revision="phase7-test",
        baseline_mode="EXPLORATORY",
        allow_synthetic=True,
    )
    with pytest.raises(ValueError, match="stale|incompatible"):
        _validate(tuple(inputs), settings)


def test_semantically_exact_baseline_accepts_parquet_dtype_and_array_roundtrip():
    inputs = list(_synthetic_inputs())
    inputs[-1] = copy.deepcopy(inputs[-1])
    normalized = inputs[-1]["normalized_metrics"].copy()
    normalized["raw_value"] = normalized["raw_value"].astype(object)
    inputs[-1]["normalized_metrics"] = normalized
    regions = inputs[-1]["candidate_regions"].copy()
    regions["member_grid_ids"] = regions["member_grid_ids"].map(
        lambda value: np.asarray(value, dtype=object)
    )
    inputs[-1]["candidate_regions"] = regions
    settings = CurrentValidationSettings(
        validation_revision="phase7-test",
        baseline_mode="EXPLORATORY",
        allow_synthetic=True,
    )
    result = _validate(tuple(inputs), settings)
    assert len(result.sensitivity_results) == 1


def test_semantic_baseline_rejects_boolean_substituted_for_numeric_value():
    inputs = list(_synthetic_inputs())
    inputs[-1] = copy.deepcopy(inputs[-1])
    regions = inputs[-1]["candidate_regions"].copy()
    assert regions.loc[0, "n_cells"] == 1
    regions["n_cells"] = regions["n_cells"].astype(object)
    regions.loc[0, "n_cells"] = True
    inputs[-1]["candidate_regions"] = regions
    settings = CurrentValidationSettings(
        validation_revision="phase7-test",
        baseline_mode="EXPLORATORY",
        allow_synthetic=True,
    )
    with pytest.raises(ValueError, match="candidate_regions.*stale|candidate_regions.*incompatible"):
        _validate(tuple(inputs), settings)


def test_saved_parquet_baseline_roundtrip_passes_but_tampered_payload_fails(tmp_path):
    from dc_locator.io import read_geoparquet, read_parquet, write_geoparquet, write_parquet
    from dc_locator.provenance import DataMode

    inputs = list(_synthetic_inputs())
    original = inputs[-1]
    persisted = copy.deepcopy(original)
    tables = {
        "normalized_metrics": ("NormalizedMetricDataset", "1.0.0", False),
        "pareto_results": ("ParetoDataset", "1.0.0", False),
        "ranked_cells": ("RankedCellDataset", "1.1.0", False),
        "region_membership": ("RegionMembership", "1.0.0", False),
        "candidate_regions": ("CandidateRegion", "1.1.0", True),
    }
    for name, (schema, version, geographic) in tables.items():
        path = tmp_path / f"{name}.parquet"
        writer = write_geoparquet if geographic else write_parquet
        reader = read_geoparquet if geographic else read_parquet
        writer(
            original[name],
            path,
            schema_name=schema,
            schema_version=version,
            data_mode=DataMode.SYNTHETIC,
            grid_definition_id="fixture",
        )
        persisted[name] = reader(path)
    inputs[-1] = persisted
    settings = CurrentValidationSettings(
        validation_revision="phase7-test",
        baseline_mode="EXPLORATORY",
        allow_synthetic=True,
    )
    assert len(_validate(tuple(inputs), settings).sensitivity_results) == 1

    tampered = copy.deepcopy(persisted)
    tampered["normalized_metrics"] = tampered["normalized_metrics"].copy()
    tampered["normalized_metrics"].loc[0, "normalized_value"] += 1
    inputs[-1] = tampered
    with pytest.raises(ValueError, match="normalized_metrics.*stale|normalized_metrics.*incompatible"):
        _validate(tuple(inputs), settings)


def test_strict_empty_domain_is_valid_without_stability_claims():
    inputs = _synthetic_inputs(mode="STRICT")
    ordinary = CurrentValidationSettings(
        validation_revision="phase7-test",
        baseline_mode="STRICT",
    )
    with pytest.raises(ValueError, match="quarantined"):
        _validate(inputs, ordinary)

    settings = ordinary.model_copy(update={"allow_synthetic": True})
    result = _validate(inputs, settings)
    assert len(result.sensitivity_results) == 1
    assert not result.sensitivity_results.base_rankable.any()
    assert not result.sensitivity_results.case_rankable.any()
    summary = result.robustness_summary.iloc[0]
    assert summary.alternatives == 1
    assert summary.rankable == 0
    assert summary.top_k_overlap_count == 0
    assert summary.top_k_jaccard is None
    assert summary.rank_correlation is None
    assert result.validation_report["ranking_stability"]["rank_correlation_range"] is None
    assert result.validation_report["ranking_stability"]["top_k_overlap_range"] is None
    assert result.validation_report["overall_accuracy"] is None
    assert result.validation_report["external_validation"]["status"] == "UNAVAILABLE"
    assert "No ranked top-k comparison was available" in result.validation_markdown


def test_scalar_cases_recompute_upstream_physics_from_current_inputs():
    inputs = _synthetic_inputs()
    cases = tuple(
        CurrentSensitivityCase(
            case_id=case_id,
            category=category,
            basis="project_assumption",
            rationale="Explicit scalar software fixture.",
            multiplier=multiplier,
        )
        for case_id, category, multiplier in (
            ("pue_up", "pue", 1.1),
            ("wue_up", "wue", 2.0),
            ("load_down", "load", 0.5),
            ("carbon_down", "carbon", 0.5),
        )
    )
    settings = CurrentValidationSettings(
        validation_revision="phase7-test",
        baseline_mode="EXPLORATORY",
        cases=cases,
        allow_synthetic=True,
    )
    result = _validate(inputs, settings, reference_evidence={"phase6_freeze": "historical-only"})
    rows = result.sensitivity_results.set_index("case_id")
    baseline = json.loads(rows.loc["baseline", "base_raw_metrics_json"])
    pue = json.loads(rows.loc["pue_up", "case_raw_metrics_json"])
    wue = json.loads(rows.loc["wue_up", "case_raw_metrics_json"])
    load = json.loads(rows.loc["load_down", "case_raw_metrics_json"])
    carbon = json.loads(rows.loc["carbon_down", "case_raw_metrics_json"])
    assert pue["annual_electricity_co2e"] == pytest.approx(
        baseline["annual_electricity_co2e"] * 1.1
    )
    assert wue["annual_site_water_consumption"] == pytest.approx(
        baseline["annual_site_water_consumption"] * 2
    )
    assert load["annual_electricity_co2e"] == pytest.approx(
        baseline["annual_electricity_co2e"] * 0.5
    )
    assert load["annual_site_water_consumption"] == pytest.approx(
        baseline["annual_site_water_consumption"] * 0.5
    )
    assert carbon["annual_electricity_co2e"] == pytest.approx(
        baseline["annual_electricity_co2e"] * 0.5
    )
    assumptions = json.loads(rows.loc["carbon_down", "case_assumptions_json"])
    assert assumptions["carbon_transform"]["source_fields"] == ["SRC2ERTA"]
    assert assumptions["carbon_transform"]["interpretation"].startswith("Counterfactual")
    assert result.validation_report["historical_reference"]["status"] == "HISTORICAL_REFERENCE_ONLY"
    assert result.validation_report["runtime_contracts"]["test_suite_status"] == "NOT_EMBEDDED_IN_RUNTIME_HELPER"


def test_weight_stress_and_strict_screening_are_explicit_project_cases():
    inputs = _synthetic_inputs()
    profile = inputs[-2]
    group_ids = profile.weight_criterion_ids
    requested = {group_id: index + 1 for index, group_id in enumerate(group_ids)}
    settings = CurrentValidationSettings(
        validation_revision="phase7-test",
        baseline_mode="EXPLORATORY",
        allow_synthetic=True,
        cases=(
            CurrentSensitivityCase(
                case_id="project_weights",
                category="weights",
                basis="project_assumption",
                rationale="Transparent project preference stress.",
                group_weights=requested,
            ),
            CurrentSensitivityCase(
                case_id="strict_policy",
                category="screening",
                basis="project_assumption",
                rationale="Precautionary strict UNKNOWN policy.",
                mode="STRICT",
            ),
        ),
    )
    result = _validate(inputs, settings)
    weight_row = result.sensitivity_results.loc[
        result.sensitivity_results.case_id.eq("project_weights")
    ].iloc[0]
    strict_row = result.sensitivity_results.loc[
        result.sensitivity_results.case_id.eq("strict_policy")
    ].iloc[0]
    weight_assumptions = json.loads(weight_row.case_assumptions_json)
    assert sum(weight_assumptions["normalized_group_weights"].values()) == pytest.approx(1)
    assert "not elicited expert judgment" in weight_assumptions["interpretation"]
    assert not strict_row.case_rankable
    assert strict_row.case_critical_unknown
    assert not strict_row.case_eligible
    assert result.validation_report["preference_evidence"][
        "stress_weight_cases_are_expert_judgments"
    ] is False


def test_current_zero_load_remains_known_zero_and_rankable():
    inputs = _synthetic_inputs(facility_updates={"average_it_load_factor": 0})
    settings = CurrentValidationSettings(
        validation_revision="phase7-test",
        baseline_mode="EXPLORATORY",
        allow_synthetic=True,
    )
    result = _validate(inputs, settings)
    row = result.sensitivity_results.iloc[0]
    raw = json.loads(row.case_raw_metrics_json)
    assert raw["annual_electricity_co2e"] == 0
    assert raw["annual_site_water_consumption"] == 0
    assert row.case_rankable
    binding = result.validation_report["input_binding"]["actual_objects"]
    assert len(binding["facility_object_sha256"]) == 64


def test_missing_carbon_stays_unknown_without_candidate_weight_redistribution():
    inputs = _synthetic_inputs(missing_carbon=True)
    case = CurrentSensitivityCase(
        case_id="carbon_down",
        category="carbon",
        basis="project_assumption",
        rationale="Unknown-source preservation fixture.",
        multiplier=0.5,
    )
    settings = CurrentValidationSettings(
        validation_revision="phase7-test",
        baseline_mode="EXPLORATORY",
        cases=(case,),
        allow_synthetic=True,
    )
    result = _validate(inputs, settings)
    carbon = result.sensitivity_results.loc[
        result.sensitivity_results.case_id.eq("carbon_down")
    ].iloc[0]
    raw = json.loads(carbon.case_raw_metrics_json)
    assumptions = json.loads(carbon.case_assumptions_json)
    assert raw["annual_electricity_co2e"] is None
    assert not carbon.case_rankable
    assert assumptions["carbon_transform"]["known_values_scaled"] == 0
    assert assumptions["carbon_transform"]["unknown_values_preserved"] == 1
    assert result.validation_report["runtime_contracts"][
        "candidate_specific_missing_weight_redistribution"
    ] is False


def test_future_context_actual_tables_are_bound_into_validation_identity():
    inputs = _synthetic_inputs()
    settings = CurrentValidationSettings(
        validation_revision="phase7-test",
        baseline_mode="EXPLORATORY",
        allow_synthetic=True,
    )
    first = _validate(inputs, settings, future_contexts=[_future_context(inputs, 2.0)])
    second = _validate(inputs, settings, future_contexts=[_future_context(inputs, 3.0)])
    assert first.validation_report["validation_id"] != second.validation_report["validation_id"]
    first_context = first.validation_report["input_binding"]["future_contexts"][0]
    second_context = second.validation_report["input_binding"]["future_contexts"][0]
    assert first_context["actual_geography_table_sha256"] != second_context["actual_geography_table_sha256"]
    assert len(first_context["actual_provenance_table_sha256"]) == 64


def test_future_context_rejects_relabelled_pathway_and_native_period():
    inputs = _synthetic_inputs()
    context = _future_context(inputs, 2.0)
    mismatched = make_external_scenarios(
        inputs[4][0].scenario_id, [future_period("opt", 2050)]
    )[0]
    context = replace(
        context,
        case_id="mismatched_opt_2050",
        external_scenario=mismatched,
    )
    settings = CurrentValidationSettings(
        validation_revision="phase7-test",
        baseline_mode="EXPLORATORY",
        allow_synthetic=True,
    )
    with pytest.raises(ValueError, match="future-water|source binding|external scenario"):
        _validate(inputs, settings, future_contexts=[context])


def test_supported_future_context_keeps_source_nodata_unknown_and_unranked():
    inputs = _synthetic_inputs()
    context = _future_context(inputs, 2.0)
    column = "aqueduct_bau_2030_water_stress_score"
    geography = context.geography.copy()
    provenance = context.provenance.copy()
    geography.attrs.update(context.geography.attrs)
    provenance.attrs.update(context.provenance.attrs)
    geography[column] = np.nan
    geography[column + "_status"] = "unknown"
    geography[column + "_confidence"] = "unknown"
    geography[column + "_coverage_frac"] = 0.0
    selected = provenance.metric.eq(column)
    provenance.loc[selected, "value"] = np.nan
    provenance.loc[selected, "status"] = "unknown"
    provenance.loc[selected, "confidence"] = "unknown"
    provenance.loc[selected, "coverage_frac"] = 0.0
    provenance.loc[selected, "missing_reason"] = "source_nodata"
    context = replace(context, geography=geography, provenance=provenance)
    settings = CurrentValidationSettings(
        validation_revision="phase7-test",
        baseline_mode="EXPLORATORY",
        allow_synthetic=True,
    )
    result = _validate(inputs, settings, future_contexts=[context])
    future = result.sensitivity_results.loc[
        result.sensitivity_results.case_id.eq("future_bau_2030")
    ]
    assert len(future) == 1
    assert not future.case_rankable.any()
    assert json.loads(future.iloc[0].case_raw_metrics_json)[
        "local_baseline_water_stress"
    ] is None


@pytest.fixture(scope="module")
def real_current_inputs():
    from dc_locator.config import load_facility_config
    from dc_locator.model.cooling import load_cooling_designs, load_physical_scenarios
    from dc_locator.model.enhanced import _read_baseline
    from dc_locator.model.metrics import load_profile
    from dc_locator.model.screening import load_requirements
    from dc_locator.schemas import FacilityConfig

    geography, provenance, _ = _read_baseline(
        "runs/phase5/integrated/enhanced_grid_dataset.parquet",
        "runs/phase5/integrated/enhanced_feature_provenance.parquet",
    )
    loaded = load_facility_config(Path("configs/facility.yaml")).facilities
    assert len(loaded) == 1
    facility = FacilityConfig.model_validate(loaded[0].model_dump(mode="json"))
    designs = load_cooling_designs("configs/cooling_designs.yaml")
    scenarios = load_physical_scenarios("configs/phase3_physical_scenarios.yaml")
    requirements, _ = load_requirements("configs/constraints.yaml")
    profile = load_profile("configs/phase5_scoring_profiles/bau_2030.yaml")
    return geography, provenance, facility, designs, scenarios, requirements, profile


@pytest.mark.parametrize(
    ("mode", "expected_rankable"),
    [("EXPLORATORY", 84), ("STRICT", 0)],
)
def test_real_current_run_preserves_exploratory_and_strict_semantics(
    real_current_inputs, mode, expected_rankable
):
    geography, provenance, facility, designs, scenarios, requirements, profile = real_current_inputs
    performance = simulate(geography, provenance, facility, designs, scenarios)
    _, eligibility, _ = screen(
        geography,
        provenance,
        facility,
        designs,
        scenarios,
        requirements,
        mode=mode,
    )
    baseline = decide(
        geography,
        provenance,
        performance,
        eligibility,
        profile,
        profile_hash=profile_fingerprint(profile),
        provenance_grid_definition_id=geography.grid_definition_id.iloc[0],
    )
    result = validate_current_run(
        geography=geography,
        provenance=provenance,
        facility=facility,
        designs=designs,
        physical_scenarios=scenarios,
        requirements=requirements,
        active_profile=profile,
        baseline_result=baseline,
        provenance_grid_definition_id=geography.grid_definition_id.iloc[0],
        identity=_identity().model_copy(update={"run_id": "current-real-" + mode.lower()}),
        settings=CurrentValidationSettings(
            validation_revision="phase7-test",
            baseline_mode=mode,
            cases=(
                CurrentSensitivityCase(
                    case_id="land_double",
                    category="land",
                    basis="project_assumption",
                    rationale="Double the configured regional land-area threshold.",
                    multiplier=2.0,
                ),
            ),
        ),
    )
    assert len(result.sensitivity_results) == 168
    baseline_rows = result.sensitivity_results.loc[
        result.sensitivity_results.case_id.eq("baseline")
    ]
    land_rows = result.sensitivity_results.loc[
        result.sensitivity_results.case_id.eq("land_double")
    ]
    assert len(baseline_rows) == len(land_rows) == 84
    assert int(baseline_rows.case_rankable.sum()) == expected_rankable
    assert int(land_rows.case_rankable.sum()) == expected_rankable
    if mode == "EXPLORATORY":
        assert baseline_rows.case_conditional.all()
        assert land_rows.case_conditional.all()
    else:
        assert not result.sensitivity_results.case_conditional.any()
        assert result.validation_report["ranking_stability"]["top_k_overlap_range"] is None
    assert result.validation_report["data_mode"] == "real"
    assert result.validation_report["prospective_holdout"]["status"] == "NOT_PERFORMED_FOR_CURRENT_RUN"


def test_all_configured_current_cases_recompute_the_real_alternative_domain(real_current_inputs):
    from dc_locator.model.metrics import load_profile

    geography, provenance, facility, designs, scenarios, requirements, _ = real_current_inputs
    profile = load_profile("configs/scoring_profile.yaml")
    performance = simulate(geography, provenance, facility, designs, scenarios)
    _, eligibility, _ = screen(
        geography,
        provenance,
        facility,
        designs,
        scenarios,
        requirements,
        mode="EXPLORATORY",
    )
    baseline = decide(
        geography,
        provenance,
        performance,
        eligibility,
        profile,
        profile_hash=profile_fingerprint(profile),
        provenance_grid_definition_id=geography.grid_definition_id.iloc[0],
    )
    document = yaml.safe_load(Path("configs/run_exploratory.yaml").read_text(encoding="utf-8"))[
        "validation"
    ]
    document.pop("enabled")
    document.pop("future_contexts")
    document["baseline_mode"] = "EXPLORATORY"
    settings = CurrentValidationSettings.model_validate(document)
    result = validate_current_run(
        geography=geography,
        provenance=provenance,
        facility=facility,
        designs=designs,
        physical_scenarios=scenarios,
        requirements=requirements,
        active_profile=profile,
        baseline_result=baseline,
        provenance_grid_definition_id=geography.grid_definition_id.iloc[0],
        identity=_identity().model_copy(update={"run_id": "configured-real-cases"}),
        settings=settings,
    )
    assert len(settings.cases) == 15
    assert len(result.sensitivity_results) == 16 * 84
    assert len(result.robustness_summary) == 16
    assert set(result.sensitivity_results.case_id) == {"baseline", *[c.case_id for c in settings.cases]}
    strict = result.sensitivity_results.loc[
        result.sensitivity_results.case_id.eq("screening_strict")
    ]
    assert len(strict) == 84
    assert not strict.case_rankable.any()
    assert strict.case_critical_unknown.all()
