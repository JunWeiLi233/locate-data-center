"""Pure Monte Carlo accounting and exact expected/robust county tradeoffs."""

import math
import numpy as np

from .schemas import validate_config
from .scenarios import common_draws, candidate_trajectories
from .pareto import frontier_mask, distribution_summary, bootstrap_mc_error

# Array order is part of the run contract and its objective-unit tolerances.
OBJECTIVES = ["lifetime_electricity_cost_usd", "lifetime_operational_co2e_tonnes", "lifetime_direct_water_consumption_m3"]


def prepare_candidates(candidates, config, electricity_sector="industrial"):
    """Filter failures/missing inputs before simulation; retain exploratory unknowns."""
    if not 1 <= len(candidates) <= 50:
        raise ValueError("current engine supports 1–50 screening counties")
    if electricity_sector not in {"industrial", "commercial"}:
        raise ValueError("electricity_sector must be industrial or commercial")
    ids = [c.get("candidate_id") for c in candidates]
    if any(not isinstance(i, str) or len(i) != 5 or not i.isascii() or not i.isdigit() for i in ids) or len(set(ids)) != len(ids):
        raise ValueError("candidate IDs must be unique 5-digit FIPS strings")
    eligible, excluded = [], []
    price_key = "electricity_price_usd_per_mwh" if electricity_sector == "industrial" else "commercial_price_usd_per_mwh"
    for candidate in sorted(candidates, key=lambda c: c["candidate_id"]):
        reasons = []
        if candidate.get("county_fips") != candidate["candidate_id"]:
            reasons.append("candidate and county FIPS disagree")
        for key in [price_key, "grid_co2e_kg_per_mwh"]:
            value = candidate.get(key)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
                reasons.append(f"missing/invalid {key}")
        if not candidate.get("grid_region"):
            reasons.append("missing/ambiguous grid assignment")
        feasibility = candidate.get("feasibility", {})
        for feature in ["power_capacity", "water_allocation", "parcel_zoning", "fiber_redundancy"]:
            evidence = feasibility.get(feature, {})
            status = evidence.get("status", "unverified")
            if status not in {"verified", "unverified", "failed"}:
                reasons.append(f"invalid feasibility status for {feature}")
            if status == "failed":
                reasons.append(f"failed feasibility: {feature}")
            if config["feasibility_mode"] == "verified" and (status != "verified" or not evidence.get("evidence")):
                reasons.append(f"unverified feasibility: {feature}")
        for constraint in config["hard_constraints"]:
            value = candidate.get(constraint["field"])
            if value is None or not isinstance(value, (int, float)) or not math.isfinite(value):
                reasons.append(f"unknown threshold input: {constraint['label']}")
            elif value > constraint["maximum"]:
                reasons.append(f"screening threshold exceeded: {constraint['label']}")
        if reasons:
            excluded.append({"candidate_id": candidate["candidate_id"], "reasons": reasons})
        else:
            eligible.append(candidate)
    # Unknown override labels must not silently fail to affect the intended county.
    valid_labels = set(ids) | {c.get("grid_region") for c in candidates}
    for scenario in config["scenario_set"]:
        if set(scenario["regional_overrides"]) - valid_labels:
            raise ValueError("regional override does not match a candidate county or grid region")
    return eligible, excluded


def evaluate_samples(config, scenario, candidates, shared, *, electricity_sector="industrial", grid_anchors=None):
    """Vectorized physical accounting with identical workload/common engineering draws.

    Annual energy, prices and carbon are aligned before summing. Water is equal
    across counties when shared IT-based WUE is equal; no stress multiplier is
    invented to differentiate that objective. Engineering draws describe lifetime
    design uncertainty, not annual weather variability.
    """
    n = config["simulation_count"]
    samples = np.empty((n, len(candidates), 3), dtype=float)
    annual_it = config["it_nameplate_mw"] * config["utilization"] * config["annual_hours"]
    facility = annual_it * shared["pue"]
    water_energy = annual_it if config["cooling"]["wue_basis"] == "it" else facility
    direct_water = water_energy * shared["wue"] * config["analysis_horizon_years"]
    trajectories = []
    for index, candidate in enumerate(candidates):
        anchor = None if grid_anchors is None else grid_anchors[candidate["candidate_id"]]
        trajectory = candidate_trajectories(config, scenario, candidate, shared,
                                            electricity_sector=electricity_sector, grid_anchor=anchor)
        years = trajectory["years"]
        discount = (1 + config["discount_rate"]) ** (years - config["base_year"] + 1)
        samples[:, index, 0] = facility * (trajectory["price_usd_per_mwh"] / discount).sum(axis=1)
        samples[:, index, 1] = facility * trajectory["grid_co2e_kg_per_mwh"].sum(axis=1) / 1000
        samples[:, index, 2] = direct_water
        # Compact annual mean trajectories remain auditable without a live data call.
        for year_index, year in enumerate(years):
            trajectories.append({"candidate_id": candidate["candidate_id"], "scenario_id": scenario["id"], "year": int(year),
                                 "electricity_price_mean_usd_per_mwh": float(trajectory["price_usd_per_mwh"][:, year_index].mean()),
                                 "grid_co2e_mean_kg_per_mwh": float(trajectory["grid_co2e_kg_per_mwh"][:, year_index].mean()),
                                 "status": "assumed rate trajectory anchored to historical regional proxy",
                                 "currency_convention": config["currency_convention"]})
    if not np.isfinite(samples).all() or (samples < 0).any():
        raise ValueError("nonfinite or negative Monte Carlo outcome")
    return samples, trajectories


def simulate(config, candidates, *, electricity_sector="industrial", grid_anchors=None, estimate_error=True):
    """Return conditional scenario results plus samples for artifact/convergence work."""
    config = validate_config(config)
    eligible, excluded = prepare_candidates(candidates, config, electricity_sector)
    ids = [c["candidate_id"] for c in eligible]
    shared = common_draws(config)
    tolerance = config["numerical_tolerances"]
    # Empty verified-feasibility runs legitimately produce no frontier.
    if not eligible:
        return {"scenarios": [], "eligible": [], "excluded": excluded, "samples": {}, "shared_draws": shared,
                "annual_trajectories": [], "status": "no_eligible_candidates"}
    scenario_results, sample_store, trajectory_store = [], {}, []
    for scenario in config["scenario_set"]:
        samples, trajectories = evaluate_samples(config, scenario, eligible, shared,
                                                 electricity_sector=electricity_sector, grid_anchors=grid_anchors)
        summary = distribution_summary(samples, config["cvar_alpha"])
        expected = frontier_mask(summary["mean"], absolute_tolerance=tolerance["absolute"], relative_tolerance=tolerance["relative"])
        robust = frontier_mask(summary["cvar"], absolute_tolerance=tolerance["absolute"], relative_tolerance=tolerance["relative"])
        membership = np.empty(samples.shape[:2], dtype=bool)
        for start in range(0, len(samples), 128):
            # Batching limits pairwise array memory; all comparisons remain exact.
            membership[start:start + 128] = frontier_mask(samples[start:start + 128], absolute_tolerance=tolerance["absolute"], relative_tolerance=tolerance["relative"])
        frequency = membership.mean(axis=0)
        errors = bootstrap_mc_error(samples, membership, seed=config["seed"] + 1,
                                    resamples=config["bootstrap_resamples"]) if estimate_error else None
        details = []
        for index, candidate in enumerate(eligible):
            objectives = {name: {stat: float(array[index, objective]) for stat, array in summary.items()}
                          for objective, name in enumerate(OBJECTIVES)}
            entry = {"candidate_id": candidate["candidate_id"], "name": candidate["name"], "state_abbr": candidate.get("state_abbr"),
                     "objectives": objectives, "expected_frontier": bool(expected[index]), "robust_frontier": bool(robust[index]),
                     "pareto_frequency": float(frequency[index]), "feasibility": candidate.get("feasibility", {}),
                     "feasibility_status": "verified" if all(item.get("status") == "verified" and item.get("evidence") for item in candidate.get("feasibility", {}).values()) and candidate.get("feasibility") else "unverified",
                     "grid_border_or_multiple_subregions": candidate.get("grid_border_or_multiple_subregions", True),
                     "water_stress_score": candidate.get("water_stress_score"), "water_stress_label": candidate.get("water_stress_label"),
                     "coverage": candidate.get("coverage", {}), "provenance": candidate.get("provenance", {})}
            if errors is not None:
                entry["monte_carlo_error"] = {
                    "objective_means": {name: {key: float(errors[key][index, objective]) for key in ["mean_bootstrap_se", "mean_bootstrap_p025", "mean_bootstrap_p975"]}
                                        for objective, name in enumerate(OBJECTIVES)},
                    "pareto_frequency_wilson_95": [float(errors["pareto_frequency_wilson_low"][index]), float(errors["pareto_frequency_wilson_high"][index])]}
            details.append(entry)
        scenario_results.append({"scenario_id": scenario["id"], "assumptions": scenario, "scenario_weight": None,
                                 "expected_frontier_ids": [i for i, flag in zip(ids, expected) if flag],
                                 "robust_frontier_ids": [i for i, flag in zip(ids, robust) if flag], "candidates": details})
        sample_store[scenario["id"]] = samples
        trajectory_store.extend(trajectories)
    return {"scenarios": scenario_results, "eligible": eligible, "excluded": excluded, "samples": sample_store,
            "shared_draws": shared, "annual_trajectories": trajectory_store, "status": "completed"}
