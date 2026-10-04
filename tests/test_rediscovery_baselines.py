"""Random controls: separation, area weighting, determinism and the empirical p-value."""
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from dc_rediscovery.baselines import draw_separated, run_controls
from dc_rediscovery.geodesy import haversine_km

# A synthetic pool: a 40 x 40 lattice of points 0.25 degrees apart (synthetic test geometry, not real cells).
LAT, LON = np.meshgrid(np.arange(40) * 0.25 + 30.0, np.arange(40) * 0.25 - 100.0, indexing="ij")
POOL_LAT, POOL_LON = LAT.ravel(), LON.ravel()


def coordinates(indices):
    return POOL_LAT[indices], POOL_LON[indices]


def test_draws_respect_separation_and_weights():
    rng = np.random.default_rng(1)
    weights = np.ones(len(POOL_LAT))
    weights[:800] = 0.0  # the southern half can never be drawn
    pool = np.arange(len(POOL_LAT))
    lat, lon = draw_separated(rng, np.cumsum(weights), pool, 20, 40.0, coordinates)
    assert len(lat) == 20
    assert (lat >= POOL_LAT[800]).all()
    for i in range(len(lat)):
        for j in range(i + 1, len(lat)):
            assert haversine_km(lat[i], lon[i], lat[j], lon[j]) >= 40.0


def _controls():
    declared = SimpleNamespace(basis="project_assumption", rationale="synthetic test control")
    return [SimpleNamespace(control_id="uniform_conus", label="Uniform", declared=declared,
                            max_transmission_distance_km=None, min_suitable_land_frac=None)]


def test_controls_are_deterministic_and_p_value_is_empirical():
    facilities = pd.DataFrame({"lat": [32.0, 36.0], "lon": [-98.0, -95.0]})
    masks = {"uniform_conus": np.ones(len(POOL_LAT), dtype=bool)}
    model_rates = [{"top_n": 5, "radius_km": 50.0, "hit_rate": 1.0}, {"top_n": 5, "radius_km": 500.0, "hit_rate": 0.0}]
    arguments = dict(masks=masks, weights=np.ones(len(POOL_LAT)), coordinates=coordinates, facilities=facilities,
                     model_rates=model_rates, top_n_values=[5], radii_km=[50.0, 500.0], min_distance_km=30.0, draws=50,
                     seed=11, area_weighted=True)
    first_draws, first = run_controls(_controls(), **arguments)
    second_draws, second = run_controls(_controls(), **arguments)
    pd.testing.assert_frame_equal(first_draws, second_draws)
    assert first == second
    rows = {row["radius_km"]: row for row in first}
    # A model hit rate of 1.0 that no draw reaches has p = 1 / (draws + 1); a rate of 0 is reached by every draw.
    exceed = rows[50.0]["draws_at_or_above_model"]
    assert rows[50.0]["p_value_one_sided"] == pytest.approx((1 + exceed) / 51)
    assert rows[500.0]["draws_at_or_above_model"] == 50 and rows[500.0]["p_value_one_sided"] == pytest.approx(1.0)
    assert len(first_draws) == 2 * 50
    assert rows[50.0]["p2_5"] <= rows[50.0]["mean"] <= rows[50.0]["p97_5"]


def test_control_pool_must_hold_enough_cells():
    facilities = pd.DataFrame({"lat": [32.0], "lon": [-98.0]})
    masks = {"uniform_conus": np.zeros(len(POOL_LAT), dtype=bool)}
    masks["uniform_conus"][:3] = True
    with pytest.raises(ValueError):
        run_controls(_controls(), masks=masks, weights=np.ones(len(POOL_LAT)), coordinates=coordinates, facilities=facilities,
                     model_rates=[], top_n_values=[5], radii_km=[10.0], min_distance_km=1.0, draws=20, seed=1, area_weighted=True)
