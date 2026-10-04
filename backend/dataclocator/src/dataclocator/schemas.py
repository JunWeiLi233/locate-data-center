"""Strict run configuration validation with explicit, bounded assumptions."""

import copy
import math


def finite_number(value, name, lower, upper):
    """Reject booleans and nonfinite numbers, then enforce a physical/compute bound."""
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{name} must be a finite number")
    if not lower <= value <= upper:
        raise ValueError(f"{name} must be between {lower} and {upper}")
    return float(value)


def integer(value, name, lower, upper):
    """Integer identifiers and compute limits must not silently truncate floats."""
    if isinstance(value, bool) or not isinstance(value, int) or not lower <= value <= upper:
        raise ValueError(f"{name} must be an integer between {lower} and {upper}")
    return value


def exact_keys(value, expected, name):
    """Catch missing assumptions and misspelled settings instead of defaulting."""
    if not isinstance(value, dict) or set(value) != set(expected):
        raise ValueError(f"{name} must contain exactly {sorted(expected)}")


def validate_prior(prior, name, lower, upper, units):
    """A fixed/triangular prior always states bounds, units and assumption source."""
    exact_keys(prior, {"kind", "lower", "mode", "upper", "units", "source"}, name)
    if prior["kind"] not in {"fixed", "triangular"} or prior["units"] != units:
        raise ValueError(f"{name}: fixed/triangular kind and {units} units required")
    if not isinstance(prior["source"], str) or len(prior["source"].strip()) < 5:
        raise ValueError(f"{name} requires an explicit source or user-assumption label")
    values = [finite_number(prior[k], f"{name}.{k}", lower, upper) for k in ["lower", "mode", "upper"]]
    if not values[0] <= values[1] <= values[2]:
        raise ValueError(f"{name} requires lower <= mode <= upper")
    if prior["kind"] == "fixed" and len(set(values)) != 1:
        raise ValueError(f"{name}: fixed prior must have identical bounds")
    if prior["kind"] == "triangular" and values[0] == values[2]:
        raise ValueError(f"{name}: use fixed for a degenerate prior")


def validate_config(config):
    """Validate equal workload, trajectories, modes, constraints and compute limits.

    The MVP intentionally limits currency to the available 2025 USD price anchor,
    and supports explicit screening constraints without pretending that risk scores
    supply chance constraints. Unsupported input correlation matrices are rejected.
    """
    required = {"it_nameplate_mw", "utilization", "annual_hours", "opening_year", "analysis_horizon_years",
                "base_currency", "base_year", "currency_convention", "discount_rate", "cooling", "dependence",
                "scenario_set", "seed", "simulation_count", "feasibility_mode", "hard_constraints",
                "numerical_tolerances", "cvar_alpha", "bootstrap_resamples", "convergence_tolerances"}
    exact_keys(config, required, "run config")
    cfg = copy.deepcopy(config)
    finite_number(cfg["it_nameplate_mw"], "it_nameplate_mw", 0.001, 10000)
    finite_number(cfg["utilization"], "utilization", 0, 1)
    finite_number(cfg["annual_hours"], "annual_hours", 0, 8784)
    integer(cfg["opening_year"], "opening_year", 2025, 2050)
    integer(cfg["analysis_horizon_years"], "analysis_horizon_years", 1, 40)
    integer(cfg["seed"], "seed", 0, 2**32 - 1)
    integer(cfg["simulation_count"], "simulation_count", 1, 10000)
    integer(cfg["bootstrap_resamples"], "bootstrap_resamples", 20, 200)
    finite_number(cfg["discount_rate"], "discount_rate", 0, 0.3)
    finite_number(cfg["cvar_alpha"], "cvar_alpha", 0, 0.999)
    if cfg["base_currency"] != "USD" or cfg["base_year"] != 2025 or isinstance(cfg["base_year"], bool):
        raise ValueError("current frozen retail anchor supports USD base year 2025 only")
    if cfg["currency_convention"] not in {"real", "nominal"}:
        raise ValueError("currency_convention must be real or nominal")
    exact_keys(cfg["cooling"], {"pue", "wue", "wue_basis", "water_definition"}, "cooling")
    validate_prior(cfg["cooling"]["pue"], "pue", 1, 3, "dimensionless")
    validate_prior(cfg["cooling"]["wue"], "wue", 0, 10, "L/kWh")
    if cfg["cooling"]["wue_basis"] not in {"it", "facility"} or cfg["cooling"]["water_definition"] != "consumption":
        raise ValueError("cooling requires it/facility WUE basis and consumption definition")
    if cfg["dependence"] not in {"shared_independent_engineering", "shared_comonotonic_engineering"}:
        raise ValueError("choose a disclosed engineering dependence model; matrices not supported")
    if cfg["feasibility_mode"] not in {"exploratory", "verified"}:
        raise ValueError("feasibility_mode must be exploratory or verified")
    if not isinstance(cfg["scenario_set"], list) or not 1 <= len(cfg["scenario_set"]) <= 12:
        raise ValueError("supply 1–12 separate structural scenarios, without mixture weights")
    ids = []
    for scenario in cfg["scenario_set"]:
        exact_keys(scenario, {"id", "description", "price_growth", "carbon_decline", "regional_overrides"}, "scenario")
        if not isinstance(scenario["id"], str) or not scenario["id"] or len(scenario["id"]) > 80:
            raise ValueError("scenario id must be a short nonempty string")
        if not isinstance(scenario["description"], str) or len(scenario["description"].strip()) < 5:
            raise ValueError("scenario must describe its assumptions")
        ids.append(scenario["id"])
        validate_prior(scenario["price_growth"], "price_growth", -0.1, 0.3, "fraction/year")
        validate_prior(scenario["carbon_decline"], "carbon_decline", -0.1, 1, "fraction/year")
        if not isinstance(scenario["regional_overrides"], dict):
            raise ValueError("regional_overrides must be keyed by grid region or county FIPS")
        for region, overrides in scenario["regional_overrides"].items():
            if not isinstance(region, str) or not isinstance(overrides, dict) or not overrides or set(overrides) - {"price_growth", "carbon_decline"}:
                raise ValueError("regional overrides require valid keys and explicit rate priors")
            for name, prior in overrides.items():
                validate_prior(prior, name, -0.1, 0.3 if name == "price_growth" else 1, "fraction/year")
    if len(ids) != len(set(ids)):
        raise ValueError("scenario identifiers must be unique")
    if not isinstance(cfg["hard_constraints"], list) or len(cfg["hard_constraints"]) > 20:
        raise ValueError("hard_constraints must be a list with at most 20 entries")
    supported_fields = {"water_stress_score", "grid_co2e_kg_per_mwh", "electricity_price_usd_per_mwh"}
    for constraint in cfg["hard_constraints"]:
        exact_keys(constraint, {"field", "maximum", "label"}, "constraint")
        if constraint["field"] not in supported_fields or not isinstance(constraint["label"], str) or not constraint["label"].strip():
            raise ValueError("only explicit regional screening thresholds are supported")
        finite_number(constraint["maximum"], "constraint maximum", 0, 1e6)
    exact_keys(cfg["numerical_tolerances"], {"absolute", "relative"}, "numerical_tolerances")
    absolute = cfg["numerical_tolerances"]["absolute"]
    if not isinstance(absolute, list) or len(absolute) != 3:
        raise ValueError("three physical objective tolerances required: USD, tonnes, m3")
    for tolerance in absolute:
        finite_number(tolerance, "absolute tolerance", 0, 1e3)
    finite_number(cfg["numerical_tolerances"]["relative"], "relative tolerance", 0, 1e-3)
    exact_keys(cfg["convergence_tolerances"], {"relative_objective_mean", "absolute_pareto_frequency"}, "convergence_tolerances")
    for tolerance in cfg["convergence_tolerances"].values():
        finite_number(tolerance, "convergence tolerance", 0, 1)
    return cfg
