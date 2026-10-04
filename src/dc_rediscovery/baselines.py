"""Random control locations with the same size and separation rule as the model's candidates.

A high hit rate alone means little: existing facilities cluster where people, fiber and power are, and any
spread-out sample will sometimes land near them. Each control draws valued cells at random and applies the
same greedy minimum separation as candidate generation (in random order). It then measures HitRate(r, N)
for every configured N, using prefixes of one draw, which keeps them consistent.

- ``uniform_conus``: area-uniform over every valued CONUS 1 km cell, weighted by each cell's in-study area.
- ``infrastructure_plausible``: the same, restricted to cells with mapped transmission and land-cover
  thresholds. These thresholds are declared assumptions, not siting rules. This control asks whether the
  model's ranking adds anything beyond being "near transmission, on land".

Draws use one seeded ``numpy`` generator per control, spawned from the configured seed, so the results are
deterministic.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .geodesy import SphericalIndex, greedy_separated


def draw_separated(rng: np.random.Generator, cumulative: np.ndarray, pool: np.ndarray, size: int, min_distance_km: float,
                   coordinates) -> tuple[np.ndarray, np.ndarray]:
    """Random pool cells (probability ∝ weight) kept in draw order with greedy separation, ``size`` points."""
    oversample = max(2 * size, size + 50)
    for _ in range(20):
        picks = np.searchsorted(cumulative, rng.random(oversample) * cumulative[-1], side="right")
        picks = np.minimum(picks, len(pool) - 1)
        _, first = np.unique(picks, return_index=True)
        picks = picks[np.sort(first)]  # drop repeated cells, keep draw order
        lat, lon = coordinates(pool[picks])
        kept = greedy_separated(lat, lon, size, min_distance_km)
        if len(kept) == size:
            return lat[kept], lon[kept]
        oversample *= 2
    raise ValueError("Could not draw enough separated control locations; the pool is too small for the separation")


def run_controls(controls, *, masks: dict[str, np.ndarray], weights: np.ndarray, coordinates, facilities: pd.DataFrame,
                 model_rates: list[dict], top_n_values: list[int], radii_km: list[float], min_distance_km: float,
                 draws: int, seed: int, area_weighted: bool) -> tuple[pd.DataFrame, list[dict]]:
    """Return (per-draw hit rates, comparison summary rows) for every control, N and radius."""
    index = SphericalIndex(facilities.lat.to_numpy(), facilities.lon.to_numpy())
    model = {(row["top_n"], row["radius_km"]): row["hit_rate"] for row in model_rates}
    largest = max(n for n in top_n_values)
    children = np.random.SeedSequence(seed).spawn(len(controls))
    records, summary = [], []
    for control, child in zip(controls, children):
        pool = np.flatnonzero(masks[control.control_id])
        if len(pool) < largest:
            raise ValueError(f"Control {control.control_id} has fewer valued cells than candidates requested")
        pool_weights = np.asarray(weights[pool], dtype=float) if area_weighted else np.ones(len(pool))
        if not (np.isfinite(pool_weights).all() and (pool_weights >= 0).all() and pool_weights.sum() > 0):
            raise ValueError("Control sampling weights must be finite, nonnegative and positive in total")
        cumulative = np.cumsum(pool_weights)
        rng = np.random.default_rng(child)
        rates = np.zeros((draws, len(top_n_values), len(radii_km)))
        for draw in range(draws):
            lat, lon = draw_separated(rng, cumulative, pool, largest, min_distance_km, coordinates)
            distance, _ = index.nearest(lat, lon)
            for i, n in enumerate(top_n_values):
                head = distance[:n]
                for j, radius in enumerate(radii_km):
                    rates[draw, i, j] = np.count_nonzero(head <= radius) / n
        for i, n in enumerate(top_n_values):
            for j, radius in enumerate(radii_km):
                values = rates[:, i, j]
                records.extend({"control_id": control.control_id, "draw": draw, "top_n": n, "radius_km": radius,
                                "hit_rate": float(value)} for draw, value in enumerate(values))
                observed = model.get((n, radius))
                exceed = None if observed is None else int(np.count_nonzero(values >= observed - 1e-12))
                mean = float(values.mean())
                summary.append({
                    "control_id": control.control_id, "control_label": control.label, "top_n": n, "radius_km": radius,
                    "pool_cells": int(len(pool)), "draws": draws,
                    "model_hit_rate": observed, "mean": mean, "std": float(values.std(ddof=1)),
                    "p2_5": float(np.percentile(values, 2.5)), "median": float(np.median(values)), "p97_5": float(np.percentile(values, 97.5)),
                    "lift": None if observed is None or mean == 0 else float(observed / mean),
                    "draws_at_or_above_model": exceed,
                    "p_value_one_sided": None if exceed is None else float((1 + exceed) / (1 + draws)),
                })
    return pd.DataFrame(records), summary
