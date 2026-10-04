"""Hand-checked synthetic county support; no real observations are fabricated."""
import numpy as np
import pandas as pd
import pytest

from dc_locator.model.validation.existing_sites import compare_county_support, comparison_summary


def inputs():
    reference = pd.DataFrame([
        dict(facility_id="a", name="Synthetic county A", operating_status="operating", county_geoid="00001"),
        dict(facility_id="b", name="Synthetic outside", operating_status="operating", county_geoid="00003"),
        dict(facility_id="c", name="Synthetic unmatched", operating_status="operating", county_geoid=None),
    ])
    grid = pd.DataFrame(dict(grid_id=["g1", "g2"], grid_definition_id=["synthetic"]*2,
                             data_mode=["synthetic"]*2, county_geoid_all=[["00001", "00002"], ["00001"]]))
    ranked = pd.DataFrame(dict(grid_id=["g1", "g2"], design_id=["dry"]*2, scenario_id=["historical"]*2,
        grid_definition_id=["synthetic"]*2, data_mode=["synthetic"]*2, rankable=[True, False],
        eligible=[True, False], hard_fail=[False, True], critical_unknown=[True, False], conditional=[True, False],
        mcda_score=[60., np.nan], mcda_rank=[1., np.nan], raw_transmission_proximity=[0., 10.]))
    return reference, grid, ranked


def test_county_range_keeps_unknowns_and_never_assigns_facility_score():
    result = compare_county_support(*inputs()).set_index("reference_facility_id")
    assert result.loc["a", "support_cells"] == 2
    assert result.loc["a", "hard_failure_cells"] == 1
    assert result.loc["a", "conditional_ranked_cells"] == 1
    assert result.loc["a", "mcda_score_min"] == result.loc["a", "mcda_score_max"] == 60
    assert result.loc["a", "raw_transmission_proximity_max"] == 10
    assert result.facility_score.isna().all()
    assert result.loc["b", "comparison_status"] == "OUTSIDE_EVALUATED_DOMAIN"
    assert result.loc["b", "mcda_score_min"] is None or pd.isna(result.loc["b", "mcda_score_min"])
    assert result.loc["c", "comparison_status"] == "UNMATCHED_COUNTY"
    assert comparison_summary(result.reset_index())["accuracy"] is None


def test_comparison_is_order_invariant_and_scenarios_remain_separate():
    ref, grid, ranked = inputs()
    second = ranked.assign(scenario_id="future", mcda_score=[30., np.nan])
    ranked = pd.concat([ranked, second], ignore_index=True)
    first = compare_county_support(ref, grid, ranked)
    pd.testing.assert_frame_equal(first, compare_county_support(ref.iloc[::-1], grid.iloc[::-1], ranked.iloc[::-1]))
    a = first.loc[first.reference_facility_id.eq("a")]
    assert a.mcda_score_min.tolist() == [30., 60.]
    assert comparison_summary(first)["reference_facilities"] == 3


@pytest.mark.parametrize("attack", ["planned", "duplicate", "boolean", "rank", "identity", "county", "hard_fail"])
def test_invalid_comparison_inputs_rejected(attack):
    ref, grid, ranked = inputs()
    if attack == "planned": ref.loc[0, "operating_status"] = "planned"
    if attack == "duplicate": ref.loc[1, "facility_id"] = "a"
    if attack == "boolean": ranked["conditional"] = [1, 0]
    if attack == "rank": ranked.loc[1, "mcda_rank"] = 2
    if attack == "identity": ranked["grid_definition_id"] = "wrong"
    if attack == "county": grid["county_geoid_all"] = '["00001"]'
    if attack == "hard_fail": ranked.loc[0, "hard_fail"] = True
    with pytest.raises(ValueError): compare_county_support(ref, grid, ranked)


def test_incomplete_design_scenario_domain_is_rejected():
    ref, grid, ranked = inputs()
    with pytest.raises(ValueError, match="every evaluated grid"):
        compare_county_support(ref, grid, ranked.iloc[:1])
