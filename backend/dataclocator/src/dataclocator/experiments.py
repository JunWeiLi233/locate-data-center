"""Frozen runs, cache identity, convergence checks and assumption sensitivity cases."""

import copy
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from . import MODEL_VERSION
from .pipeline import verify_raw_inputs, write_json
from .schemas import validate_config
from .simulation import simulate, OBJECTIVES, prepare_candidates


def file_hash(path):
    """Hash frozen inputs in streaming mode; preprocessing changes alter cache keys."""
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def validate_convergence(config, candidates, baseline):
    """Compare 1k/5k/10k prefixes per scenario under predeclared tolerances.

    The 10k run is a numerical reference, not a true expected outcome. Mean changes
    and frequency changes are evaluated for every candidate/objective. Exceptions
    remain visible rather than silently increasing draws until a chosen result wins.
    """
    references = {}
    for count in [1000, 5000, 10000]:
        if count == config["simulation_count"]:
            references[count] = baseline
        else:
            references[count] = simulate(config | {"simulation_count": count}, candidates, estimate_error=False)
    checks = []
    for index, scenario in enumerate(references[10000]["scenarios"]):
        reference_rows = scenario["candidates"]
        for count in [1000, 5000]:
            rows = references[count]["scenarios"][index]["candidates"]
            failures, max_mean, max_frequency = [], 0., 0.
            for row, reference in zip(rows, reference_rows):
                frequency_error = abs(row["pareto_frequency"] - reference["pareto_frequency"])
                max_frequency = max(max_frequency, frequency_error)
                for name in OBJECTIVES:
                    mean = reference["objectives"][name]["mean"]
                    difference = abs(row["objectives"][name]["mean"] - mean)
                    relative = difference / abs(mean) if mean != 0 else (0. if difference == 0 else None)
                    if relative is not None:
                        max_mean = max(max_mean, relative)
                    if relative is None or relative >= config["convergence_tolerances"]["relative_objective_mean"] or frequency_error >= config["convergence_tolerances"]["absolute_pareto_frequency"]:
                        failures.append({"candidate_id": row["candidate_id"], "objective": name,
                                         "relative_mean_change": relative, "absolute_frequency_change": frequency_error})
            checks.append({"scenario_id": scenario["scenario_id"], "draws": count, "reference_draws": 10000,
                           "max_relative_mean_change": max_mean, "max_absolute_frequency_change": max_frequency,
                           "passed": not failures, "exceptions": failures})
    return {"draw_counts": [1000, 5000, 10000], "paired_prefix_draws": True,
            "tolerances_predeclared": config["convergence_tolerances"], "checks": checks,
            "all_passed": all(c["passed"] for c in checks),
            "note": "Conditional simulation convergence only; cannot validate engineering priors, grid futures or site suitability."}


def sensitivity_cases(config, candidates, grid_rates):
    """Vary horizons, tariff sector, dependence and nonprobabilistic grid assignments.

    Sensitivity cases use the central scenario when present, otherwise the first
    explicitly configured one. Other structural scenarios remain in the main run.
    """
    scenario = next((s for s in config["scenario_set"] if s["id"] == "price01_carbon02"), config["scenario_set"][0])
    base = copy.deepcopy(config)
    base["scenario_set"] = [scenario]
    cases = []
    variants = [("horizon20", base | {"analysis_horizon_years": 20}, "industrial", None),
                ("horizon30", base | {"analysis_horizon_years": 30}, "industrial", None),
                ("commercial_tariff", base, "commercial", None),
                ("comonotonic_engineering", base | {"dependence": "shared_comonotonic_engineering"}, "industrial", None),
                ("verified_feasibility", base | {"feasibility_mode": "verified"}, "industrial", None)]
    for kind in ["lower", "upper"]:
        # These are deterministic map sensitivity envelopes, never supplier probabilities.
        anchors = {}
        for candidate in candidates:
            options = candidate.get("grid_region_options") or [candidate["grid_region"]]
            rates = [grid_rates[key] for key in options]
            anchors[candidate["candidate_id"]] = float(min(rates) if kind == "lower" else max(rates))
        variants.append((f"grid_{kind}_map_envelope", base, "industrial", anchors))
    for label, case_config, sector, anchors in variants:
        result = simulate(case_config, candidates, electricity_sector=sector, grid_anchors=anchors, estimate_error=False)
        cases.append({"case": label, "config": case_config, "electricity_sector": sector, "grid_anchors_kg_per_mwh": anchors,
                      "status": result["status"], "excluded_candidates": result["excluded"], "scenarios": result["scenarios"],
                      "note": "Grid envelopes use only known intersecting primary map regions; multiple-service overlays may conceal other utility assignments." if anchors is not None else None})
    return cases


def near_frontier_ties(result, config):
    """List objective-near ties separately from formal numeric dominance tolerance."""
    ties = []
    for scenario in result["scenarios"]:
        rows = [r for r in scenario["candidates"] if r["expected_frontier"]]
        for index, a in enumerate(rows):
            for b in rows[index + 1:]:
                close = []
                for name in OBJECTIVES[:2]:
                    av, bv = a["objectives"][name]["mean"], b["objectives"][name]["mean"]
                    if abs(av - bv) <= config["convergence_tolerances"]["relative_objective_mean"] * max(abs(av), abs(bv), 1):
                        close.append(name)
                if close:
                    ties.append({"scenario_id": scenario["scenario_id"], "candidate_ids": [a["candidate_id"], b["candidate_id"]], "close_objectives": close})
    return ties


def prepare_run(root: Path, config: dict, *, with_sensitivity=True, with_convergence=True):
    """Verify and freeze all model inputs before enqueueing an asynchronous run.

    Read each derived file once, hashing exactly the bytes parsed. Later changes
    to preprocessing cannot alter an accepted job or its historical evidence.
    """
    root = root.resolve()
    config = validate_config(config)
    manifest = verify_raw_inputs(root)
    candidate_path = root / "outputs/task2/candidates.json"
    candidate_bytes = candidate_path.read_bytes()
    evidence = json.loads(candidate_bytes)
    candidates = evidence["candidates"]
    prepare_candidates(candidates, config)
    grid_path = root / "data/processed/grid_regions.parquet"
    grid_bytes = grid_path.read_bytes()
    from io import BytesIO
    grid = pd.read_parquet(BytesIO(grid_bytes))
    inputs = {"candidate_evidence": hashlib.sha256(candidate_bytes).hexdigest(),
              "grid_regions": hashlib.sha256(grid_bytes).hexdigest()}
    raw_hashes = {s["source_id"]: s["sha256"] for s in manifest["sources"]}
    identity = {"config": config, "input_hashes": inputs, "dataset_hashes": raw_hashes, "model_version": MODEL_VERSION,
                "with_sensitivity": with_sensitivity, "with_convergence": with_convergence}
    digest = hashlib.sha256(json.dumps(identity, sort_keys=True, allow_nan=False).encode()).hexdigest()
    run_id = "run_" + digest[:16]
    return {"run_id": run_id, "identity": identity, "evidence": evidence, "manifest": manifest,
            "grid_rates": dict(zip(grid.grid_region, grid.grid_co2e_kg_per_mwh))}


def run_experiment(root: Path, config: dict, *, with_sensitivity=True, with_convergence=True, use_cache=True, prepared=None):
    """Run frozen evidence to artifacts, sharing exactly the CLI/API cache key."""
    root = root.resolve()
    frozen = prepared if prepared is not None else prepare_run(root, config, with_sensitivity=with_sensitivity, with_convergence=with_convergence)
    identity = frozen["identity"]
    if identity["config"] != validate_config(config) or identity["with_sensitivity"] != with_sensitivity or identity["with_convergence"] != with_convergence:
        raise ValueError("frozen run settings do not match execution settings")
    config = identity["config"]
    run_id, evidence, manifest = frozen["run_id"], frozen["evidence"], frozen["manifest"]
    candidates = evidence["candidates"]
    inputs, raw_hashes = identity["input_hashes"], identity["dataset_hashes"]
    directory = root / "outputs" / run_id
    if use_cache and (directory / "results.json").is_file():
        # Old CLI caches can be upgraded only with evidence matching their input hash.
        if not (directory / "candidate_evidence.json").exists():
            write_json(directory / "candidate_evidence.json", evidence)
        return json.loads((directory / "results.json").read_text())
    directory.mkdir(parents=True, exist_ok=True)
    write_json(directory / "config.json", config)
    write_json(directory / "run_identity.json", identity)
    write_json(directory / "candidate_evidence.json", evidence)
    print(f"Running {config['simulation_count']} draws in {len(config['scenario_set'])} separate scenarios.", flush=True)
    result = simulate(config, candidates)
    print("Expected/robust frontiers and Monte Carlo estimator errors computed.", flush=True)
    convergence = validate_convergence(config, candidates, result) if with_convergence and result["eligible"] else None
    if with_convergence and result["eligible"]:
        print("Convergence validation complete.", flush=True)
    grid_rates = frozen["grid_rates"]
    sensitivities = sensitivity_cases(config, candidates, grid_rates) if with_sensitivity and result["eligible"] else []
    if with_sensitivity and result["eligible"]:
        print("Horizon, tariff, dependence, grid-map and feasibility sensitivities complete.", flush=True)
    response = {"schema_version": "0.2.0", "model_version": MODEL_VERSION, "run_id": run_id, "status": result["status"],
                "seed": config["seed"], "config": config, "dataset_hashes": raw_hashes, "input_hashes": inputs,
                "sources": manifest["sources"], "objective_units": dict(zip(OBJECTIVES, ["USD (2025 base year)", "tonnes CO2e", "m3 consumption"])),
                "discounting": {"currency_convention": config["currency_convention"], "monetary_payment_timing": "end of operating year", "physical_totals_discounted": False},
                "scope": evidence["scope"], "excluded_candidates": result["excluded"], "scenarios": result["scenarios"],
                "scenario_mixture": None, "sensitivity_results": sensitivities, "convergence": convergence,
                "near_frontier_ties": near_frontier_ties(result, config), "boundary_exclusions": evidence["boundaries"],
                "warnings": ["Supplied priors/rates are conditional assumptions; consult their source labels for calibration and user confirmation. Demo inputs are unconfirmed.",
                             "Exploratory candidates retain unknown power, water allocation, zoning and fiber feasibility.",
                             "Direct water is equal across counties at common WUE; water stress remains separate context.",
                             "Shared design uncertainty alone cannot change regional dominance under uniform fixed-rate trajectories; frontier frequencies can be exactly 0 or 1 without validating a site.",
                             "No measured-input error or future weather variability is sampled; grid and tariff anchors are held at their reported historical values.",
                             "Independent PUE/WUE is a disclosed simplification; comonotonic sensitivity is not a sourced cooling curve.",
                             "Structural scenarios have no assigned future probabilities and no pooled ranking.",
                             "2025 prices are preliminary state retail proxies; grid anchors are 2023 regional averages, not verified utility supply.",
                             "Grid decline is extrapolated from 2023 through opening; real price growth is anchored to 2025 USD.",
                             "Hazard scores are not sampled downtime or incident probabilities; no full TCO or embodied-carbon benefits are estimated."]}

    # Freeze exact draw arrays and annual mean paths; they allow independent offline review.
    np.savez_compressed(directory / "samples.npz", **{f"scenario_{index}": result["samples"][s["id"]] for index, s in enumerate(config["scenario_set"]) if s["id"] in result["samples"]})
    np.savez_compressed(directory / "common_draws.npz", **result["shared_draws"])
    pd.DataFrame(result["annual_trajectories"]).to_csv(directory / "annual_trajectories.csv", index=False)
    rows = []
    for scenario in result["scenarios"]:
        for candidate in scenario["candidates"]:
            row = {"scenario_id": scenario["scenario_id"], "candidate_id": candidate["candidate_id"], "name": candidate["name"],
                   "state_abbr": candidate["state_abbr"], "expected_frontier": candidate["expected_frontier"], "robust_frontier": candidate["robust_frontier"],
                   "pareto_frequency": candidate["pareto_frequency"], "feasibility_status": candidate["feasibility_status"],
                   "grid_ambiguous": candidate["grid_border_or_multiple_subregions"], "water_stress_score": candidate["water_stress_score"]}
            row.update({f"{objective}_{stat}": value for objective, summary in candidate["objectives"].items() for stat, value in summary.items()})
            rows.append(row)
    pd.DataFrame(rows).to_csv(directory / "candidates.csv", index=False)
    from .run_report import write_run_report
    write_run_report(directory, response)
    # Commit the results marker last so partial artifact generation cannot be cached.
    write_json(directory / "results.json", response)
    return response
