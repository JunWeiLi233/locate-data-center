"""Hand-calculated and monotonic Phase 6 software-property checks."""

import numpy as np
import pandas as pd
import pytest

from dc_locator.model.ahp import evaluate_ahp
from dc_locator.model.mcda import score_alternatives
from dc_locator.model.normalization import normalize_values
from dc_locator.model.physics import calculate_annual


def physical(**changes):
    values = dict(
        peak_it_power_mw=100.0,
        average_it_load_factor=0.8,
        hours_in_modeled_year=8760.0,
        pue=1.2,
        grid_carbon_intensity_kg_per_mwh=100.0,
        wue_l_per_it_kwh=0.3,
    )
    values.update(changes)
    return calculate_annual(**values)


def test_hand_fixture_and_monotonic_physical_properties():
    base = physical()
    assert base["e_it_mwh"] == pytest.approx(700800)
    assert base["e_facility_mwh"] == pytest.approx(840960)
    assert base["c_electricity_tonnes"] == pytest.approx(84096)
    assert base["w_site_liters"] == pytest.approx(210240000)
    assert physical(pue=1.3)["e_facility_mwh"] > base["e_facility_mwh"]
    assert physical(wue_l_per_it_kwh=0.4)["w_site_liters"] > base["w_site_liters"]
    assert physical(grid_carbon_intensity_kg_per_mwh=120)["c_electricity_tonnes"] > base["c_electricity_tonnes"]
    assert physical(average_it_load_factor=0.9)["e_it_mwh"] > base["e_it_mwh"]


def test_worsening_cost_never_improves_normalized_score():
    scores, flags = normalize_values([0.0, 5.0, 10.0, 15.0], 0.0, 10.0, "minimize")
    assert scores == pytest.approx([100, 50, 0, 0])
    assert np.all(np.diff(scores) <= 0)
    assert flags.tolist()[-1] == "clipped_high"


def test_hard_failure_and_missing_never_gain_score_or_candidate_specific_reweight():
    frame = pd.DataFrame({
        "grid_id": ["complete", "hard", "missing"], "design_id": ["d"] * 3, "scenario_id": ["s"] * 3,
        "eligible": [True, False, True], "conditional": [False, False, False], "hard_fail": [False, True, False],
        "critical_unknown": [False, False, False], "mode": ["EXPLORATORY"] * 3,
        "m1": [80.0, 100.0, 100.0], "m2": [20.0, 100.0, np.nan],
    })
    result = score_alternatives(frame, ["m1", "m2"], {"m1": 0.5, "m2": 0.5})
    assert result.loc[0, "mcda_score"] == pytest.approx(50)
    assert result.loc[1:, "mcda_score"].isna().all()
    assert result.loc[2, "weights_used_json"] == result.loc[0, "weights_used_json"]
    assert result.loc[2, "contribution_by_metric_json"] == "{}"


def test_labelled_ratio_matrix_checks_right_eigenvector_without_claiming_expert_judgment():
    expected = np.array([0.4, 0.3, 0.2, 0.1])
    matrix = expected[:, None] / expected[None, :]
    result = evaluate_ahp(
        ["software_energy", "software_water", "software_grid", "software_land"], matrix.tolist(),
        active_criteria_ids=["software_energy", "software_water", "software_grid", "software_land"],
        consistency_threshold=0.1, reciprocal_tolerance=1e-9,
    )
    assert result["status"] == "ACCEPTED"
    assert list(result["weights"].values()) == pytest.approx(expected)
    assert result["CR"] == pytest.approx(0, abs=1e-12)
