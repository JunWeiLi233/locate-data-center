"""Seek-independent common draws and bounded, explicitly assumed trajectories."""

import hashlib
import numpy as np


def uniform_draws(seed, factor, draws):
    """Use a named stream so candidate order, scenario order and draw count do not matter.

    A deterministic SHA-256 factor ID avoids Python's randomized hash. Smaller
    runs are prefixes of larger runs, which makes convergence comparisons paired.
    """
    identity = int.from_bytes(hashlib.sha256(factor.encode()).digest()[:8], "big")
    generator = np.random.default_rng(np.random.SeedSequence([seed, identity]))
    return generator.random(draws)


def sample_prior(prior, uniforms):
    """Inverse-CDF triangular sampling preserves shared latent quantile draws."""
    lo, mode, hi = prior["lower"], prior["mode"], prior["upper"]
    u = np.asarray(uniforms, dtype=float)
    if prior["kind"] == "fixed":
        return np.full(u.shape, mode, dtype=float)
    # The inverse transform handles mode at either endpoint without a division by zero.
    split = (mode - lo) / (hi - lo)
    return np.where(u <= split, lo + np.sqrt(u * (hi - lo) * (mode - lo)),
                    hi - np.sqrt((1 - u) * (hi - lo) * (hi - mode)))


def common_draws(config):
    """Draw lifetime engineering parameters once; no weather variance is invented.

    Both parameters are common to every county. Independence is an explicitly
    named simplification; comonotonic mode uses the same uniform for both and is
    a dependence sensitivity, not a calibrated cooling engineering relationship.
    """
    n, seed = config["simulation_count"], config["seed"]
    pue_u = uniform_draws(seed, "engineering_pue", n)
    wue_u = pue_u if config["dependence"] == "shared_comonotonic_engineering" else uniform_draws(seed, "engineering_wue", n)
    return {"pue": sample_prior(config["cooling"]["pue"], pue_u),
            "wue": sample_prior(config["cooling"]["wue"], wue_u),
            "price_u": uniform_draws(seed, "price_trajectory_rate", n),
            "carbon_u": uniform_draws(seed, "carbon_trajectory_rate", n)}


def candidate_trajectories(config, scenario, candidate, shared, *, electricity_sector="industrial", grid_anchor=None):
    """Apply separate annual rate scenarios to frozen regional price/carbon anchors.

    Region overrides apply first, then county overrides. Their priors share the
    global rate quantiles, maintaining global drivers and regional responses. Grid
    rates extrapolate from the observed 2023 anchor; price from 2025. This bridge
    is a visible assumption, not measured intervening data or a future forecast.
    """
    priors = {"price_growth": scenario["price_growth"], "carbon_decline": scenario["carbon_decline"]}
    for key in [candidate["grid_region"], candidate["county_fips"]]:
        priors.update(scenario["regional_overrides"].get(key, {}))
    growth = sample_prior(priors["price_growth"], shared["price_u"])
    decline = sample_prior(priors["carbon_decline"], shared["carbon_u"])
    years = np.arange(config["opening_year"], config["opening_year"] + config["analysis_horizon_years"])
    price_field = "electricity_price_usd_per_mwh" if electricity_sector == "industrial" else "commercial_price_usd_per_mwh"
    price = candidate[price_field] * (1 + growth[:, None]) ** (years - 2025)
    carbon_baseline = candidate["grid_co2e_kg_per_mwh"] if grid_anchor is None else grid_anchor
    carbon = carbon_baseline * (1 - decline[:, None]) ** (years - 2023)
    if not np.isfinite(price).all() or not np.isfinite(carbon).all():
        raise ValueError("nonfinite trajectory")
    return {"years": years, "price_usd_per_mwh": price, "grid_co2e_kg_per_mwh": carbon,
            "price_growth": growth, "carbon_decline": decline}
