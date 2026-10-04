"""Independent frontier and fractional-tail examples, including degenerate cases."""

import numpy as np
import pytest

from dataclocator.pareto import frontier_mask, cvar_upper, bootstrap_mc_error


def test_frontier_tradeoffs_dominance_and_ties():
    """Two tradeoffs and an exact tie survive; a uniformly worse option does not."""
    points = [[1, 3, 2], [3, 1, 2], [4, 4, 2], [1, 3, 2]]
    assert frontier_mask(points, absolute_tolerance=[0, 0, 0]).tolist() == [True, True, False, True]


def test_tolerance_and_ordering():
    """Roundoff ties survive, and permutation only permutes the same frontier."""
    points = np.array([[1, 3], [1.00001, 3], [2, 4]])
    expected = frontier_mask(points, absolute_tolerance=[0.001, 0.001])
    assert expected.tolist() == [True, True, False]
    order = [2, 0, 1]
    assert np.array_equal(frontier_mask(points[order], absolute_tolerance=[0.001, 0.001]), expected[order])


def test_draw_frontiers_and_empty_candidates():
    """Batched futures may have different tradeoffs; an empty frontier is valid."""
    points = [[[1, 2], [2, 3]], [[3, 3], [2, 2]]]
    assert frontier_mask(points, absolute_tolerance=[0, 0]).tolist() == [[True, False], [False, True]]
    assert frontier_mask(np.empty((0, 3)), absolute_tolerance=[0, 0, 0]).size == 0


@pytest.mark.parametrize("values,alpha,expected", [([1, 2, 10], 0.5, 22 / 3),
    ([1, 2, 10], 0.95, 10), ([1, 2, 3, 4], 0.625, 11 / 3),
    ([1, 2, 3, 4], 0.5, 3.5), ([2, 2, 2], 0.95, 2), ([1, 2, 3], 0, 2)])
def test_fractional_cvar_hand_calculations(values, alpha, expected):
    """Tail mass includes fractional boundary values rather than quantile ties."""
    assert cvar_upper(values, alpha) == pytest.approx(expected)


def test_cvar_multiple_objectives_and_invalid_values():
    """Axis zero is draws; invalid alpha or nonfinite samples are rejected."""
    assert cvar_upper([[1, 8], [9, 2]], 0.75).tolist() == [9, 8]
    for values, alpha in [([], .95), ([1], 1), ([np.nan], .95), ([1], -1)]:
        with pytest.raises(ValueError):
            cvar_upper(values, alpha)


def test_mc_error_differs_from_input_uncertainty():
    """Constant samples have zero mean estimator error; Wilson bounds remain finite."""
    samples = np.ones((20, 2, 3))
    membership = np.array([[True, False]] * 20)
    result = bootstrap_mc_error(samples, membership, seed=42, resamples=20)
    assert np.all(result["mean_bootstrap_se"] == 0)
    assert result["pareto_frequency_wilson_low"][0] < 1
    assert result["pareto_frequency_wilson_high"][1] > 0
