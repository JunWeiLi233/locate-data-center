"""Synthetic tests validate simulation mechanics; real recommendations use frozen data."""

import copy
import numpy as np
import pytest

from dataclocator.accounting import annual_accounting, lifetime_accounting
from dataclocator.schemas import validate_config
from dataclocator.scenarios import common_draws, sample_prior
from dataclocator.simulation import simulate


def prior(value, units):
    """Explicit fixed test assumptions require no measured-data interpretation."""
    return {"kind": "fixed", "lower": value, "mode": value, "upper": value, "units": units, "source": "synthetic test fixture only"}


@pytest.fixture
def config():
    """A small hand-checkable 500-draw run separates deterministic from random inputs."""
    return {"it_nameplate_mw": 100, "utilization": .85, "annual_hours": 8760, "opening_year": 2027,
            "analysis_horizon_years": 3, "base_currency": "USD", "base_year": 2025, "currency_convention": "real",
            "discount_rate": .05, "cooling": {"pue": prior(1.2, "dimensionless"), "wue": prior(.2, "L/kWh"), "wue_basis": "it", "water_definition": "consumption"},
            "dependence": "shared_independent_engineering", "scenario_set": [{"id": "test", "description": "synthetic fixture scenario",
                "price_growth": prior(.01, "fraction/year"), "carbon_decline": prior(.02, "fraction/year"), "regional_overrides": {}}],
            "seed": 42, "simulation_count": 500, "feasibility_mode": "exploratory", "hard_constraints": [],
            "numerical_tolerances": {"absolute": [1, .001, .001], "relative": 1e-10}, "cvar_alpha": .95,
            "bootstrap_resamples": 20, "convergence_tolerances": {"relative_objective_mean": .02, "absolute_pareto_frequency": .03}}


@pytest.fixture
def candidates():
    """Three fictional counties form two price/carbon tradeoffs and one dominated row."""
    rows = []
    for fips, price, carbon in [("01001", 50, 400), ("01003", 80, 100), ("01005", 90, 500)]:
        rows.append({"candidate_id": fips, "county_fips": fips, "name": f"Fixture {fips}", "grid_region": "TEST",
                     "electricity_price_usd_per_mwh": price, "commercial_price_usd_per_mwh": price * 1.5,
                     "grid_co2e_kg_per_mwh": carbon, "water_stress_score": 1,
                     "feasibility": {key: {"status": "unverified", "evidence": None} for key in ["power_capacity", "water_allocation", "parcel_zoning", "fiber_redundancy"]}})
    return rows


def triangular(base, lower, mode, upper):
    """Turn an explicit fixture prior into a bounded triangular uncertainty input."""
    return base | {"kind": "triangular", "lower": lower, "mode": mode, "upper": upper}


def test_deterministic_collapse_and_accounting(config, candidates):
    """Fixed inputs collapse every draw to independently checked annual accounting."""
    result = simulate(config, candidates)
    samples = result["samples"]["test"]
    assert np.all(samples == samples[0])
    annual = []
    for year in [2027, 2028, 2029]:
        annual.append(annual_accounting(it_mw=100, utilization=.85, annual_hours=8760, pue=1.2, wue_l_per_kwh=.2,
            price_usd_per_mwh=50 * 1.01 ** (year - 2025), grid_kg_per_mwh=400 * .98 ** (year - 2023)))
    expected = lifetime_accounting(annual, years=[2027, 2028, 2029], base_year=2025, discount_rate=.05, currency_convention="real")["totals"]
    assert samples[0, 0].tolist() == pytest.approx([expected["electricity_cost_usd"], expected["operational_co2e_tonnes"], expected["direct_water_consumption_m3"]])
    assert result["scenarios"][0]["expected_frontier_ids"] == ["01001", "01003"]
    assert result["scenarios"][0]["robust_frontier_ids"] == ["01001", "01003"]


def test_seed_order_common_draws_and_prefix(config, candidates):
    """Seed reproducibility, candidate-order invariance and larger-run prefixes agree."""
    config["cooling"]["pue"] = triangular(config["cooling"]["pue"], 1.1, 1.2, 1.3)
    config["cooling"]["wue"] = triangular(config["cooling"]["wue"], .1, .2, .3)
    a = simulate(config, candidates, estimate_error=False)
    b = simulate(config, list(reversed(candidates)), estimate_error=False)
    assert np.array_equal(a["samples"]["test"], b["samples"]["test"])
    c = simulate(config | {"simulation_count": 1000}, candidates, estimate_error=False)
    assert np.array_equal(a["samples"]["test"], c["samples"]["test"][:500])
    assert np.array_equal(a["samples"]["test"][:, 0, 2], a["samples"]["test"][:, 1, 2])
    assert a["samples"]["test"][:, 1, 0] == pytest.approx(a["samples"]["test"][:, 0, 0] * 1.6)
    changed = simulate(config | {"seed": 43}, candidates, estimate_error=False)
    assert not np.array_equal(a["samples"]["test"], changed["samples"]["test"])


def test_shared_dependence_and_triangle_bounds(config):
    """Comonotonic sensitivity couples parameters; independent mode is a simplification."""
    config["cooling"]["pue"] = triangular(config["cooling"]["pue"], 1.1, 1.2, 1.3)
    config["cooling"]["wue"] = triangular(config["cooling"]["wue"], .1, .2, .3)
    shared = common_draws(config | {"dependence": "shared_comonotonic_engineering"})
    assert shared["pue"].min() >= 1.1 and shared["pue"].max() <= 1.3
    assert np.corrcoef(shared["pue"], shared["wue"])[0, 1] == pytest.approx(1)
    independent = common_draws(config)
    assert abs(np.corrcoef(independent["pue"], independent["wue"])[0, 1]) < .2
    for mode in [0, 1]:
        endpoints = sample_prior(triangular(prior(0, "L/kWh"), 0, mode, 1), [0, .5, 1])
        assert np.isfinite(endpoints).all() and endpoints[0] == 0 and endpoints[-1] == 1


def test_scenario_paths_and_regional_override(config, candidates):
    """Regional rates alter outcomes while a scenario stays separately labeled."""
    altered = copy.deepcopy(config["scenario_set"][0])
    altered["id"] = "altered"
    altered["regional_overrides"] = {"01001": {"carbon_decline": prior(.1, "fraction/year")}}
    config["scenario_set"].append(altered)
    result = simulate(config, candidates, estimate_error=False)
    assert result["samples"]["altered"][0, 0, 1] < result["samples"]["test"][0, 0, 1]
    assert result["samples"]["altered"][0, 1, 1] == result["samples"]["test"][0, 1, 1]
    assert all(s["scenario_weight"] is None for s in result["scenarios"])
    first = [r for r in result["annual_trajectories"] if r["candidate_id"] == "01001" and r["scenario_id"] == "test"]
    assert first[0]["electricity_price_mean_usd_per_mwh"] < first[-1]["electricity_price_mean_usd_per_mwh"]
    assert first[0]["grid_co2e_mean_kg_per_mwh"] > first[-1]["grid_co2e_mean_kg_per_mwh"]


def test_verified_mode_and_missing_failed_inputs(config, candidates):
    """Unknown feasibility yields an empty verified run, and failed candidates never rank."""
    verified = simulate(config | {"feasibility_mode": "verified"}, candidates)
    assert verified["status"] == "no_eligible_candidates" and not verified["scenarios"]
    candidates[0]["feasibility"]["power_capacity"]["status"] = "failed"
    candidates[1]["grid_co2e_kg_per_mwh"] = None
    result = simulate(config, candidates, estimate_error=False)
    assert len(result["excluded"]) == 2
    assert result["scenarios"][0]["expected_frontier_ids"] == ["01005"]


@pytest.mark.parametrize("field,value", [("simulation_count", 10001), ("seed", True), ("discount_rate", float("nan")),
    ("opening_year", 2027.5), ("base_year", 2024), ("currency_convention", "unknown"), ("dependence", "undisclosed")])
def test_config_rejects_invalid_values(config, field, value):
    """Physical, monetary and compute-limit settings are validated before execution."""
    with pytest.raises(ValueError):
        validate_config(config | {field: value})


def test_constraints_and_unknown_scenario_labels(config, candidates):
    """Screening thresholds exclude unknowns; typoed regional priors are not ignored."""
    config["hard_constraints"] = [{"field": "water_stress_score", "maximum": 2, "label": "water screening threshold"}]
    candidates[0]["water_stress_score"] = None
    candidates[1]["water_stress_score"] = 3
    result = simulate(config, candidates, estimate_error=False)
    assert len(result["excluded"]) == 2
    config["scenario_set"][0]["regional_overrides"] = {"TYPO": {"carbon_decline": prior(.1, "fraction/year")}}
    with pytest.raises(ValueError):
        simulate(config, candidates)


def test_oversized_and_unlabeled_priors_rejected(config):
    """No silent engineering default or unlabeled probability model is accepted."""
    config["cooling"]["pue"]["source"] = ""
    with pytest.raises(ValueError):
        validate_config(config)


def test_expected_and_robust_frontiers_can_differ(config, candidates):
    """A cheap county with an assumed high-growth tail can lose on robust cost."""
    candidates[0]["grid_co2e_kg_per_mwh"] = 100
    config["scenario_set"][0]["regional_overrides"] = {"01001": {
        "price_growth": triangular(prior(0, "fraction/year"), 0, 0, .3)}}
    result = simulate(config | {"simulation_count": 5000}, candidates, estimate_error=False)
    scenario = result["scenarios"][0]
    assert scenario["expected_frontier_ids"] == ["01001"]
    assert scenario["robust_frontier_ids"] == ["01003"]
