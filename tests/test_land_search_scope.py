"""Synthetic boundary support is UNKNOWN until a cross-cell parcel is verified."""
import json

import pandas as pd
import pytest

from dc_locator.model.screening import Requirement, screen
from test_model_physics import model_inputs


def land_inputs(areas=(0.30, 0.30)):
    geography, _, facility, design, scenario = model_inputs()
    facility = facility.model_copy(update={"minimum_land_area_km2": 0.40468564224})
    geography = pd.concat(
        [geography.assign(grid_id=f"synthetic_land_{i}") for i in range(len(areas))],
        ignore_index=True,
    )
    geography["suitable_land_area_km2"] = areas
    geography["suitable_land_area_km2_status"] = "proxy"
    provenance = pd.DataFrame([
        dict(grid_id=grid_id, metric="suitable_land_area_km2", value=area,
             status="proxy", confidence="low", coverage_frac=1.0, unit="km2",
             source_id="synthetic_boundary_fixture", data_mode="synthetic")
        for grid_id, area in zip(geography.grid_id, areas)
    ])
    requirement = Requirement(
        requirement_id="total_suitable_area_plausibility",
        metric="suitable_land_area_km2", operator="ge",
        threshold_from="minimum_land_area_km2", unit="km2",
        accepted_statuses=["observed", "calculated", "proxy"],
        basis="project_assumption", rationale="Synthetic boundary support test",
    )
    return geography, provenance, facility, [design], [scenario], [requirement]


def test_multi_cell_search_does_not_disprove_land_split_across_cells():
    inputs = land_inputs()
    assert inputs[0].suitable_land_area_km2.sum() > inputs[2].minimum_land_area_km2
    results, eligibility, summary = screen(
        *inputs, mode="EXPLORATORY", land_search_scope="multi_cell_region",
    )
    assert results.outcome.tolist() == ["UNKNOWN", "UNKNOWN"]
    assert results.missing_reason.tolist() == ["cross_cell_land_support_unverified"] * 2
    assert results.value.isna().all()
    assert [json.loads(value)["value"] for value in results.evidence_json] == [0.30, 0.30]
    assert eligibility.eligible.all() and eligibility.conditional.all()
    assert not eligibility.hard_fail.any()
    assert summary["land_search_scope"] == "multi_cell_region"
    assert set(results.schema_version) == {"1.2.0"}
    assert set(eligibility.schema_version) == {"1.1.0"}


def test_single_cell_default_preserves_insufficient_area_failure():
    inputs = land_inputs()
    default = screen(*inputs, mode="EXPLORATORY")
    explicit = screen(*inputs, mode="EXPLORATORY", land_search_scope="single_cell")
    for left, right in zip(default[:2], explicit[:2]):
        pd.testing.assert_frame_equal(left, right)
    assert default[2] == explicit[2]
    assert default[0].outcome.tolist() == ["FAIL", "FAIL"]
    assert default[1].hard_fail.all() and not default[1].eligible.any()


def test_strict_multi_cell_support_stays_ineligible():
    results, eligibility, _ = screen(
        *land_inputs(), mode="STRICT", land_search_scope="multi_cell_region",
    )
    assert results.outcome.eq("UNKNOWN").all()
    assert eligibility.critical_unknown.all()
    assert not eligibility.eligible.any() and not eligibility.conditional.any()


def test_multi_cell_scope_retains_zero_failure_and_total_area_pass():
    results, eligibility, _ = screen(
        *land_inputs((0.0, 0.50)), mode="EXPLORATORY", land_search_scope="multi_cell_region",
    )
    assert results.outcome.tolist() == ["FAIL", "PASS"]
    assert eligibility.hard_fail.tolist() == [True, False]
    assert eligibility.eligible.tolist() == [False, True]


def test_multi_cell_scope_cannot_compensate_confirmed_parcel_failure():
    inputs = list(land_inputs((0.30,)))
    metric = "confirmed_developable_parcel_area_km2"
    inputs[0][metric] = 0.20
    inputs[0][metric + "_status"] = "observed"
    inputs[1] = pd.concat([inputs[1], pd.DataFrame([
        dict(grid_id=inputs[0].grid_id.iloc[0], metric=metric, value=0.20,
             status="observed", confidence="high", coverage_frac=1.0,
             unit="km2", source_id="synthetic_confirmed_fixture", data_mode="synthetic")
    ])], ignore_index=True)
    inputs[-1].append(Requirement(
        requirement_id="confirmed_developable_parcel", metric=metric,
        operator="ge", threshold_from="minimum_land_area_km2", unit="km2",
        basis="project_assumption", rationale="Synthetic confirmed parcel rejection",
    ))
    results, eligibility, _ = screen(
        *inputs, mode="EXPLORATORY", land_search_scope="multi_cell_region",
    )
    assert results.set_index("requirement").outcome.to_dict() == {
        "confirmed_developable_parcel": "FAIL", "total_suitable_area_plausibility": "UNKNOWN",
    }
    assert eligibility.hard_fail.all() and not eligibility.eligible.any()


def test_scope_does_not_weaken_other_area_rules_or_incomplete_evidence():
    inputs = list(land_inputs((0.30,)))
    inputs[-1] = [inputs[-1][0].model_copy(update={"requirement_id": "custom_single_cell_area"})]
    results, _, _ = screen(*inputs, mode="EXPLORATORY", land_search_scope="multi_cell_region")
    assert results.outcome.tolist() == ["FAIL"]
    inputs = list(land_inputs((0.30,)))
    inputs[1]["coverage_frac"] = 0.5
    results, _, _ = screen(*inputs, mode="EXPLORATORY", land_search_scope="multi_cell_region")
    assert results.missing_reason.tolist() == ["partial_coverage"]


@pytest.mark.parametrize("scope", ["region", "", None, True, [], {}])
def test_invalid_land_search_scope_rejected(scope):
    with pytest.raises(ValueError, match="land_search_scope"):
        screen(*land_inputs(), land_search_scope=scope)


def test_facility_land_cannot_exceed_bounded_regional_area():
    from dc_locator.regional import RegionalConfig, _validate_facility_land_extent
    from test_regional import document
    config = RegionalConfig.model_validate(document())
    facility = land_inputs()[2]
    _validate_facility_land_extent(facility.model_copy(update={"minimum_land_area_km2": 400.0}), config)
    with pytest.raises(ValueError, match="maximum regional bounding area"):
        _validate_facility_land_extent(facility.model_copy(update={"minimum_land_area_km2": 400.01}), config)
