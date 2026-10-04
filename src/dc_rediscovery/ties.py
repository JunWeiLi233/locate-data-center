"""Sensitivity of Top-N statistics to the order of tied scores.

The model's score uses regional proxies, so many 1 km cells share exactly the same value. In the reference
run, 855 cells tie at the maximum. The model's convention orders ties by ``grid_id``. That is deterministic,
but it is arbitrary in space: lower grid rows lie further north, so north-first. When N cuts through a tie
block, the Top-N set depends on the convention. This module repeats candidate selection with ties shuffled
uniformly at random (seeded) and reports the resulting hit-rate distribution next to the convention's value.
It never changes the published ranking.
"""
from __future__ import annotations

import numpy as np

from .geodesy import SphericalIndex, greedy_separated_lazy
from .surface import cell_centers, ranking_order


def _scan_prefix(scores_sorted: np.ndarray, position: int) -> int:
    """Smallest prefix length ≥ position + 1 that ends on a tie-block boundary."""
    if position + 1 >= len(scores_sorted):
        return len(scores_sorted)
    end = np.searchsorted(-scores_sorted, -scores_sorted[position], side="right")
    return int(max(end, position + 1))


def tie_block_structure(scores: np.ndarray, positions: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """For each selected position: (number of valued cells with a strictly higher score, number tied with it)."""
    valued = np.sort(scores[np.isfinite(scores)])
    values = scores[positions]
    higher = len(valued) - np.searchsorted(valued, values, side="right")
    tied = np.searchsorted(valued, values, side="right") - np.searchsorted(valued, values, side="left")
    return higher.astype(np.int64), tied.astype(np.int64)


def tie_shuffled_hit_rates(scores, national, grid, limit: int, min_distance_km: float, facilities, radii_km, top_n_values,
                           classification, permutations: int, seed: int) -> dict:
    """Hit rates and class counts over random tie orders; the convention's own values are reported separately."""
    order = ranking_order(scores, national.row, national.col)
    ordered_scores = scores[order]

    def selection(sequence):
        def coordinates(start, stop):
            positions = sequence[start:stop]
            return cell_centers(grid, national.row[positions], national.col[positions])
        return greedy_separated_lazy(len(sequence), coordinates, limit, min_distance_km)

    base = selection(order)
    prefix = _scan_prefix(ordered_scores, int(base[-1]) if len(base) else 0)
    index = SphericalIndex(facilities.lat.to_numpy(), facilities.lon.to_numpy())
    rng = np.random.default_rng(np.random.SeedSequence(seed))
    rates = np.zeros((permutations, len(top_n_values), len(radii_km)))
    classes = {label: np.zeros((permutations, len(top_n_values))) for label in ("validated", "unresolved", "emerging")}
    scanned = []
    for draw in range(permutations):
        length = prefix
        while True:
            head = order[:length]
            shuffled = head[np.lexsort((rng.random(length), -scores[head]))]
            kept = selection(shuffled)
            if len(kept) >= limit or length >= len(order):
                break
            length = _scan_prefix(ordered_scores, min(len(order) - 1, 2 * length))
        scanned.append(length)
        chosen = shuffled[kept]
        lat, lon = cell_centers(grid, national.row[chosen], national.col[chosen])
        distance, _ = index.nearest(lat, lon)
        labels = classification(distance)
        for i, n in enumerate(top_n_values):
            for j, radius in enumerate(radii_km):
                rates[draw, i, j] = np.count_nonzero(distance[:n] <= radius) / n
            for label in classes:
                classes[label][draw, i] = np.count_nonzero(labels[:n] == label)
    rows = []
    for i, n in enumerate(top_n_values):
        for j, radius in enumerate(radii_km):
            values = rates[:, i, j]
            rows.append({"top_n": n, "radius_km": radius, "mean": float(values.mean()), "p2_5": float(np.percentile(values, 2.5)),
                         "p97_5": float(np.percentile(values, 97.5)), "min": float(values.min()), "max": float(values.max())})
    class_rows = [{"top_n": n, **{label: float(classes[label][:, i].mean()) for label in classes}} for i, n in enumerate(top_n_values)]
    return {"permutations": permutations, "seed": seed, "hit_rates": rows, "class_means": class_rows,
            "scan_prefix_cells": {"minimum": int(min(scanned)), "maximum": int(max(scanned))},
            "method": "Ties shuffled uniformly (seeded) within equal scores, then the same greedy separation; published ranks unchanged"}
