"""Post-hoc spatial agreement between blind candidates and the external facility inventory.

Every statistic here is calculated after candidate generation and never feeds back into the model. Nothing
here is an accuracy claim. Existing facilities are an incomplete, historically shaped reference: a miss is
not a model error, and a hit does not show that a location is suitable.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from pyproj import Transformer

from .geodesy import SphericalIndex, haversine_km, km_to_chord, unit_vectors

CLASSES = ("validated", "unresolved", "emerging")


def nearest_facilities(candidates: pd.DataFrame, facilities: pd.DataFrame, radii_km: list[float]) -> pd.DataFrame:
    """Nearest existing facility (haversine) and facility counts within each radius, per candidate."""
    index = SphericalIndex(facilities.lat.to_numpy(), facilities.lon.to_numpy())
    distance, position = index.nearest(candidates.lat.to_numpy(), candidates.lon.to_numpy())
    nearest = facilities.iloc[position].reset_index(drop=True)
    result = pd.DataFrame({
        "grid_id": candidates.grid_id.to_numpy(),
        "distance_to_nearest_existing_dc_km": distance,
        "nearest_existing_dc_id": nearest.facility_id.to_numpy(),
        "nearest_existing_dc_name": nearest.name.to_numpy(),
        "nearest_existing_dc_operator": nearest.operator.to_numpy(),
        "nearest_existing_dc_county": nearest.county.to_numpy(),
        "nearest_existing_dc_state": nearest.state_abbr.to_numpy(),
        "nearest_existing_dc_type": nearest.footprint_type.to_numpy(),
        "nearest_existing_dc_lat": nearest.lat.to_numpy(),
        "nearest_existing_dc_lon": nearest.lon.to_numpy(),
    })
    for radius in radii_km:
        result[f"existing_dc_within_{_label(radius)}km"] = index.count_within(candidates.lat.to_numpy(), candidates.lon.to_numpy(), radius)
    return result


def _label(radius: float) -> str:
    return f"{radius:g}".replace(".", "p")


def hit_rates(distances: np.ndarray, radii_km: list[float], top_n_values: list[int]) -> list[dict]:
    """HitRate(r, N) = share of the first N candidates within r km (inclusive) of any existing facility."""
    distances = np.asarray(distances, dtype=float)
    if not np.isfinite(distances).all():
        raise ValueError("Every candidate needs a measured nearest-facility distance")
    rows = []
    for n in top_n_values:
        if n > len(distances):
            continue
        head = distances[:n]
        for radius in radii_km:
            hits = int(np.count_nonzero(head <= radius))
            rows.append({"top_n": n, "radius_km": radius, "hits": hits, "candidates": n, "hit_rate": hits / n})
    return rows


def classify(distances: np.ndarray, validated_max_km: float, emerging_min_km: float) -> np.ndarray:
    """validated: d ≤ validated_max_km; emerging: d > emerging_min_km; otherwise unresolved."""
    if emerging_min_km < validated_max_km:
        raise ValueError("Classification thresholds must satisfy validated_max_km ≤ emerging_min_km")
    distances = np.asarray(distances, dtype=float)
    return np.where(distances <= validated_max_km, "validated", np.where(distances > emerging_min_km, "emerging", "unresolved"))


def facility_recall(facilities: pd.DataFrame, candidates: pd.DataFrame, radii_km: list[float], top_n_values: list[int]) -> list[dict]:
    """Share of facility records within r km of at least one of the first N candidates."""
    rows = []
    for n in top_n_values:
        if n > len(candidates):
            continue
        head = candidates.iloc[:n]
        distance, _ = SphericalIndex(head.lat.to_numpy(), head.lon.to_numpy()).nearest(facilities.lat.to_numpy(), facilities.lon.to_numpy())
        for radius in radii_km:
            covered = int(np.count_nonzero(distance <= radius))
            rows.append({"top_n": n, "radius_km": radius, "facilities_covered": covered, "facilities": int(len(facilities)),
                         "recall": covered / len(facilities)})
    return rows


def _components(pairs: np.ndarray, size: int) -> np.ndarray:
    parent = np.arange(size)

    def find(item):
        while parent[item] != item:
            parent[item] = parent[parent[item]]
            item = parent[item]
        return item

    for left, right in pairs:
        a, b = find(left), find(right)
        if a != b:
            parent[max(a, b)] = min(a, b)
    return np.array([find(item) for item in range(size)])


def facility_hubs(facilities: pd.DataFrame, linkage_km: float, min_facilities: int) -> tuple[pd.DataFrame, pd.Series]:
    """Single-linkage clusters of facility records; clusters with at least ``min_facilities`` become hubs.

    Hub IDs are ordered by descending facility count, ties by the smallest facility ID, so they are
    deterministic. Hubs describe concentrations in the external inventory. They are not markets, and they
    say nothing about capacity.
    """
    from scipy.spatial import cKDTree

    vectors = unit_vectors(facilities.lat.to_numpy(), facilities.lon.to_numpy())
    pairs = np.array(sorted(cKDTree(vectors).query_pairs(r=float(km_to_chord(linkage_km)) * (1 + 1e-12))), dtype=int).reshape(-1, 2)
    labels = _components(pairs, len(facilities))
    frame = facilities.assign(_component=labels)
    groups = []
    for component, members in frame.groupby("_component", sort=False):
        if len(members) >= min_facilities:
            groups.append((-len(members), members.facility_id.min(), component, members))
    groups.sort(key=lambda item: (item[0], item[1]))
    hub_rows, membership = [], pd.Series(pd.NA, index=facilities.index, dtype="object")
    for number, (_, _, _, members) in enumerate(groups, start=1):
        hub_id = f"hub_{number:03d}"
        membership.loc[members.index] = hub_id
        mean = unit_vectors(members.lat.to_numpy(), members.lon.to_numpy()).mean(axis=0)
        mean /= np.linalg.norm(mean)
        operators = members.operator.dropna().value_counts()
        operators = operators.sort_index(kind="stable").sort_values(ascending=False, kind="stable")
        counties = (members.county + ", " + members.state_abbr).value_counts()
        counties = counties.sort_index(kind="stable").sort_values(ascending=False, kind="stable")
        hub_rows.append({
            "hub_id": hub_id, "facilities": int(len(members)),
            "centroid_lat": float(np.degrees(np.arcsin(mean[2]))), "centroid_lon": float(np.degrees(np.arctan2(mean[1], mean[0]))),
            "label": counties.index[0] if len(counties) else None,
            "states": sorted(members.state_abbr.dropna().unique().tolist()),
            "top_counties": counties.head(3).index.tolist(),
            "top_operators": operators.head(3).index.tolist(),
        })
    return pd.DataFrame(hub_rows), membership


def hub_recall(hubs: pd.DataFrame, facilities: pd.DataFrame, membership: pd.Series, candidates: pd.DataFrame,
               radii_km: list[float], top_n_values: list[int]) -> tuple[list[dict], pd.DataFrame]:
    """A hub is rediscovered at (r, N) when any of its facilities lies within r km of one of the first N candidates."""
    rows, distances = [], {}
    if hubs.empty:
        return rows, hubs.assign()
    for n in top_n_values:
        if n > len(candidates):
            continue
        head = candidates.iloc[:n]
        distance, _ = SphericalIndex(head.lat.to_numpy(), head.lon.to_numpy()).nearest(facilities.lat.to_numpy(), facilities.lon.to_numpy())
        per_hub = pd.Series(distance, index=facilities.index).groupby(membership).min()
        distances[n] = per_hub
        for radius in radii_km:
            found = int((per_hub.reindex(hubs.hub_id) <= radius).sum())
            rows.append({"top_n": n, "radius_km": radius, "hubs_rediscovered": found, "hubs": int(len(hubs)), "recall": found / len(hubs)})
    detail = hubs.copy()
    for n, per_hub in distances.items():
        detail[f"nearest_top{n}_candidate_km"] = per_hub.reindex(detail.hub_id).to_numpy()
    return rows, detail


def facility_cells(facilities: pd.DataFrame, grid) -> tuple[np.ndarray, np.ndarray]:
    """Fixed-grid (row, col) of the 1 km cell containing each facility coordinate (GRID CONTRACT)."""
    transformer = Transformer.from_crs("EPSG:4326", "EPSG:5070", always_xy=True)
    x, y = transformer.transform(facilities.lon.to_numpy(), facilities.lat.to_numpy())
    row = np.floor((grid.origin_y_m - np.asarray(y)) / grid.cell_size_m).astype(np.int64)
    col = np.floor((np.asarray(x) - grid.origin_x_m) / grid.cell_size_m).astype(np.int64)
    return row, col


def presence_background(scores: np.ndarray, positions: np.ndarray) -> dict:
    """Score percentile of occupied cells and the presence–background AUC against every valued cell.

    Each 1 km cell holding at least one facility counts once (``positions`` are unique cell positions).
    AUC = P(score of an occupied cell > score of a random valued cell), with ties counted as one half
    (Mann–Whitney). Chance is 0.5. This measures how the score ranks places where data centers already are.
    Those places were chosen for many reasons this model does not represent, so the AUC is not a classifier
    accuracy.
    """
    valued = np.sort(scores[np.isfinite(scores)])
    positions = np.unique(positions[positions >= 0])
    occupied = scores[positions]
    known = occupied[np.isfinite(occupied)]
    if not len(known) or not len(valued):
        return {"occupied_cells": int(len(positions)), "occupied_cells_valued": 0, "auc": None,
                "auc_missing_reason": "No facility cell has a model score"}
    lower = np.searchsorted(valued, known, side="left")
    upper = np.searchsorted(valued, known, side="right")
    percentile = (lower + 0.5 * (upper - lower)) / len(valued)
    return {
        "occupied_cells": int(len(positions)), "occupied_cells_valued": int(len(known)),
        "occupied_cells_unvalued": int(len(occupied) - len(known)),
        "auc": float(percentile.mean()),
        "median_score_percentile": float(np.median(percentile) * 100),
        "share_above_national_median": float(np.mean(percentile > 0.5)),
        "share_in_top_quartile": float(np.mean(percentile >= 0.75)),
        "share_in_top_decile": float(np.mean(percentile >= 0.9)),
        "occupied_median_score": float(np.median(known)), "national_median_score": float(np.median(valued)),
        "chance_auc": 0.5,
    }


def distance_check(candidates: pd.DataFrame, nearest: pd.DataFrame) -> float:
    """Recompute each reported nearest distance directly; returns the maximum discrepancy in km."""
    direct = haversine_km(candidates.lat.to_numpy(), candidates.lon.to_numpy(), nearest.nearest_existing_dc_lat.to_numpy(),
                          nearest.nearest_existing_dc_lon.to_numpy())
    return float(np.max(np.abs(direct - nearest.distance_to_nearest_existing_dc_km.to_numpy()))) if len(direct) else 0.0
