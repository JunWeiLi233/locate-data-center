"""Hand-calculated hit rates, classification, recall, hubs and presence–background statistics."""
import math

import numpy as np
import pandas as pd
import pytest

from dc_rediscovery.geodesy import EARTH_RADIUS_KM
from dc_rediscovery.validation import (classify, facility_hubs, facility_recall, hit_rates, hub_recall, nearest_facilities,
                                       presence_background)

DEG = EARTH_RADIUS_KM * math.pi / 180


def _facilities(points):
    return pd.DataFrame({"facility_id": [f"f{i}" for i in range(len(points))], "name": [f"DC {i}" for i in range(len(points))],
                         "operator": ["Op A"] * len(points), "county": ["County"] * len(points), "state_abbr": ["VA"] * len(points),
                         "footprint_type": ["building"] * len(points), "lat": [p[0] for p in points], "lon": [p[1] for p in points]})


def test_hit_rates_hand_calculated():
    distances = np.array([5.0, 12.0, 30.0, 60.0, 120.0])
    rows = {(r["top_n"], r["radius_km"]): r["hit_rate"] for r in hit_rates(distances, [10, 25, 50, 100], [2, 5, 9])}
    assert rows[(2, 10)] == 0.5 and rows[(2, 25)] == 1.0
    assert rows[(5, 10)] == 0.2 and rows[(5, 25)] == 0.4 and rows[(5, 50)] == 0.6 and rows[(5, 100)] == 0.8
    assert (9, 10) not in rows  # N larger than the candidate list is skipped, never padded
    assert hit_rates(np.array([25.0]), [25], [1])[0]["hit_rate"] == 1.0  # inclusive boundary
    with pytest.raises(ValueError):
        hit_rates(np.array([np.nan]), [10], [1])


def test_classification_boundaries():
    labels = classify(np.array([0, 25, 25.0001, 50, 50.0001, 400]), validated_max_km=25, emerging_min_km=50)
    assert labels.tolist() == ["validated", "validated", "unresolved", "unresolved", "emerging", "emerging"]
    with pytest.raises(ValueError):
        classify(np.array([1.0]), validated_max_km=50, emerging_min_km=25)


def test_nearest_facilities_and_counts():
    facilities = _facilities([(0, 0), (0, 0.5), (0, 3)])
    candidates = pd.DataFrame({"grid_id": ["a", "b"], "lat": [0.0, 0.0], "lon": [0.1, 2.0]})
    result = nearest_facilities(candidates, facilities, [25, 100])
    assert result.nearest_existing_dc_id.tolist() == ["f0", "f2"]
    assert result.distance_to_nearest_existing_dc_km.tolist() == pytest.approx([0.1 * DEG, 1.0 * DEG])
    assert result.existing_dc_within_25km.tolist() == [1, 0]
    assert result.existing_dc_within_100km.tolist() == [2, 0]


def test_facility_recall():
    facilities = _facilities([(0, 0), (0, 1), (0, 5)])
    candidates = pd.DataFrame({"grid_id": ["a", "b"], "lat": [0.0, 0.0], "lon": [0.0, 5.0]})
    rows = {(r["top_n"], r["radius_km"]): r["recall"] for r in facility_recall(facilities, candidates, [10, 150], [1, 2])}
    assert rows[(1, 10)] == pytest.approx(1 / 3)
    assert rows[(1, 150)] == pytest.approx(2 / 3)
    assert rows[(2, 10)] == pytest.approx(2 / 3)


def test_hubs_single_linkage_and_recall():
    step = 0.05  # about 5.6 km per step: a chain of five points links at 10 km
    chain = [(0, i * step) for i in range(5)]
    pair = [(5, 0), (5, 0.05)]
    lonely = [(10, 10)]
    facilities = _facilities(chain + pair + lonely)
    hubs, membership = facility_hubs(facilities, linkage_km=10, min_facilities=2)
    assert hubs.hub_id.tolist() == ["hub_001", "hub_002"]
    assert hubs.facilities.tolist() == [5, 2]
    assert membership.iloc[:5].eq("hub_001").all() and membership.iloc[5:7].eq("hub_002").all() and pd.isna(membership.iloc[7])
    candidates = pd.DataFrame({"grid_id": ["a"], "lat": [0.0], "lon": [0.1]})
    rows, detail = hub_recall(hubs, facilities, membership, candidates, [10, 1000], [1])
    recall = {(r["top_n"], r["radius_km"]): r["hubs_rediscovered"] for r in rows}
    assert recall[(1, 10)] == 1 and recall[(1, 1000)] == 2
    assert detail.nearest_top1_candidate_km.iloc[0] == pytest.approx(0.0, abs=1e-9)


def test_presence_background_auc_with_ties():
    scores = np.array([1.0, 2.0, 3.0, 4.0, np.nan])
    # Occupied cell with the top score: (3 lower + 0.5 * 1 tie) / 4 valued = 0.875.
    result = presence_background(scores, np.array([3, 3]))
    assert result["auc"] == pytest.approx(0.875)
    assert result["occupied_cells"] == 1
    # An unvalued occupied cell is reported, not scored as zero.
    result = presence_background(scores, np.array([0, 4]))
    assert result["occupied_cells_valued"] == 1 and result["occupied_cells_unvalued"] == 1
    assert result["auc"] == pytest.approx(0.125)
    # Constant scores give exactly chance.
    assert presence_background(np.ones(10), np.array([0, 5]))["auc"] == pytest.approx(0.5)
    assert presence_background(scores, np.array([4]))["auc"] is None
