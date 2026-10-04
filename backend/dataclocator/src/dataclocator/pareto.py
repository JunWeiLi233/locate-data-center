"""Exact minimization frontiers and empirical upper-tail risk summaries."""

import numpy as np


def frontier_mask(objectives, *, absolute_tolerance, relative_tolerance=1e-10):
    """Enumerate all pairs; ties survive and no preference scaling is applied.

    A dominates B when A is at most B plus tolerance in every objective and below
    B minus tolerance in at least one. Tolerance is symmetric per pair, with one
    absolute tolerance per physical objective plus a relative roundoff allowance.
    Input may be (candidates, objectives) or (draws, candidates, objectives).
    """
    values = np.asarray(objectives, dtype=float)
    if values.ndim not in {2, 3} or not np.isfinite(values).all():
        raise ValueError("Pareto objectives must be finite 2D or 3D arrays")
    atol = np.asarray(absolute_tolerance, dtype=float)
    if atol.shape != (values.shape[-1],) or not np.isfinite(atol).all() or (atol < 0).any():
        raise ValueError("one finite nonnegative tolerance per objective is required")
    if not np.isfinite(relative_tolerance) or relative_tolerance < 0:
        raise ValueError("relative tolerance must be finite and nonnegative")
    # Broadcasting builds A-by-B comparisons; the leading draw dimension is kept.
    a, b = values[..., :, None, :], values[..., None, :, :]
    tolerance = atol + relative_tolerance * np.maximum(np.abs(a), np.abs(b))
    dominates = np.all(a <= b + tolerance, axis=-1) & np.any(a < b - tolerance, axis=-1)
    return ~np.any(dominates, axis=-2)


def cvar_upper(values, alpha=0.95):
    """Average exactly the worst (1-alpha) empirical mass, including a fraction.

    Each of n observations has mass 1/n. If the requested tail contains k+f
    observations, take the k largest and fraction f of the next observation.
    This avoids selecting an oversized quantile-inclusive tail in small samples.
    """
    samples = np.asarray(values, dtype=float)
    if samples.ndim < 1 or samples.shape[0] == 0 or not np.isfinite(samples).all():
        raise ValueError("CVaR requires nonempty finite samples on axis zero")
    if isinstance(alpha, bool) or not np.isfinite(alpha) or not 0 <= alpha < 1:
        raise ValueError("alpha must lie in [0,1)")
    ordered = np.sort(samples, axis=0)[::-1]
    mass = samples.shape[0] * (1 - alpha)
    whole = int(np.floor(mass))
    fraction = mass - whole
    total = ordered[:whole].sum(axis=0)
    if fraction > 0 and whole < len(ordered):
        total = total + fraction * ordered[whole]
    return total / mass


def distribution_summary(samples, alpha=0.95):
    """Compute conditional uncertainty summaries without calling them forecasts."""
    values = np.asarray(samples, dtype=float)
    return {"mean": values.mean(axis=0), "median": np.median(values, axis=0),
            "p05": np.quantile(values, 0.05, axis=0), "p95": np.quantile(values, 0.95, axis=0),
            "cvar": cvar_upper(values, alpha)}


def bootstrap_mc_error(samples, membership, *, seed, resamples=100):
    """Resample draw indices jointly across counties to estimate Monte Carlo error.

    This is simulation estimator error, separate from the modeled input interval.
    Frontier-frequency bounds use a binomial Wilson interval, which remains
    informative when observed frequencies are zero or one. Bootstrap estimates
    the mean error only, not structural scenario or source-data uncertainty.
    """
    values = np.asarray(samples, dtype=float)
    members = np.asarray(membership, dtype=bool)
    if values.ndim != 3 or members.shape != values.shape[:2] or len(values) == 0:
        raise ValueError("bootstrap expects aligned draw/candidate/objective arrays")
    if not np.isfinite(values).all() or not 2 <= resamples <= 500:
        raise ValueError("bootstrap requires finite values and 2–500 resamples")
    rng = np.random.default_rng(seed)
    means = []
    for _ in range(resamples):
        # Common indices retain cross-county and cross-objective dependencies.
        indices = rng.integers(0, len(values), size=len(values))
        means.append(values[indices].mean(axis=0))
    means = np.asarray(means)
    n = len(values)
    frequency = members.mean(axis=0)
    z = 1.959963984540054
    denominator = 1 + z * z / n
    center = (frequency + z * z / (2 * n)) / denominator
    half = z * np.sqrt(frequency * (1 - frequency) / n + z * z / (4 * n * n)) / denominator
    return {"mean_bootstrap_se": means.std(axis=0, ddof=1),
            "mean_bootstrap_p025": np.quantile(means, 0.025, axis=0),
            "mean_bootstrap_p975": np.quantile(means, 0.975, axis=0),
            "pareto_frequency_wilson_low": np.clip(center - half, 0, 1),
            "pareto_frequency_wilson_high": np.clip(center + half, 0, 1)}
