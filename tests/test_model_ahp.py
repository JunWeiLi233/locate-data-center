"""Independent mathematical and contract tests for supplied AHP judgments."""

import importlib
import importlib.util

import numpy as np
import pytest


def evaluate(*args, **kwargs):
    assert importlib.util.find_spec("dc_locator.model.ahp") is not None, "AHP evaluator is missing"
    return importlib.import_module("dc_locator.model.ahp").evaluate_ahp(*args, **kwargs)


def test_all_equal_judgments_recover_equal_weights():
    result = evaluate(["energy", "water", "land"], np.ones((3, 3)))
    assert result["weights"] == pytest.approx(dict(energy=1 / 3, water=1 / 3, land=1 / 3))
    assert result["lambda_max"] == pytest.approx(3)
    assert result["CI"] == pytest.approx(0, abs=1e-12)
    assert result["CR"] == pytest.approx(0, abs=1e-12)
    assert result["status"] == "ACCEPTED"
    assert result["accepted"] is True
    assert result["provisional"] is False


def test_exact_ratio_fixture_recovers_supplied_weights_and_preserves_matrix():
    values = np.array([0.5, 0.3, 0.2])
    matrix = (values[:, None] / values[None, :]).tolist()
    original = [row[:] for row in matrix]
    result = evaluate(["energy", "water", "land"], matrix, active_criteria_ids=["land", "energy", "water"])
    assert result["weights"] == pytest.approx(dict(energy=0.5, water=0.3, land=0.2))
    assert result["CI"] == pytest.approx(0, abs=1e-12)
    assert result["CR"] == pytest.approx(0, abs=1e-12)
    assert result["original_matrix"] == original == matrix
    assert result["criteria_ids"] == ["energy", "water", "land"]
    assert result["validation"]["active_criteria_match"] is True


def test_nonstandard_positive_ratios_are_not_rounded_to_elicitation_scale():
    values = np.array([0.99, 0.009, 0.001])
    matrix = values[:, None] / values[None, :]
    result = evaluate(["a", "b", "c"], matrix)
    assert list(result["weights"].values()) == pytest.approx(values)
    assert result["original_matrix"] == matrix.tolist()


@pytest.mark.parametrize("ids,matrix", [
    ([], []),
    (["a", "b"], [[1, 2]]),
    (["a", "b"], [[1, 2], [0.5]]),
    (["a"], [[[1]]]),
    (["a", "b"], [[1, 0], [1, 1]]),
    (["a", "b"], [[1, -2], [-0.5, 1]]),
    (["a", "b"], [[1, np.inf], [0.5, 1]]),
    (["a", "b"], [[1, np.nan], [0.5, 1]]),
    (["a", "b"], [[1.01, 2], [0.5, 1]]),
    (["a", "b"], [[1, 2], [1, 1]]),
    (["a", "a"], [[1, 2], [0.5, 1]]),
    ([""], [[1]]),
    ([" a"], [[1]]),
    ([1], [[1]]),
    ("a", [[1]]),
    ({"a", "b"}, [[1, 2], [0.5, 1]]),
    ({"a": 1, "b": 2}, [[1, 2], [0.5, 1]]),
    (["a", "b"], [[True, True], [True, True]]),
    (["a", "b"], [[1, 1j], [-1j, 1]]),
])
def test_invalid_judgment_inputs_raise_instead_of_returning_weights(ids, matrix):
    with pytest.raises(ValueError):
        evaluate(ids, matrix)


@pytest.mark.parametrize("active", [["a"], ["a", "c"], ["a", "a"], ["a", 2], "ab"])
def test_active_profile_ids_must_match_exactly(active):
    with pytest.raises(ValueError):
        evaluate(["a", "b"], [[1, 2], [0.5, 1]], active_criteria_ids=active)


@pytest.mark.parametrize("keyword,value", [
    ("consistency_threshold", -0.1), ("consistency_threshold", np.nan),
    ("consistency_threshold", np.inf), ("consistency_threshold", True),
    ("reciprocal_tolerance", -1), ("reciprocal_tolerance", np.nan),
    ("reciprocal_tolerance", np.inf), ("reciprocal_tolerance", True),
])
def test_invalid_policy_numbers_raise(keyword, value):
    with pytest.raises(ValueError):
        evaluate(["a", "b", "c"], np.ones((3, 3)), **{keyword: value})


def test_tolerance_is_absolute_and_does_not_repair_supplied_judgments():
    matrix = [[1, 2], [0.500000001, 1]]
    result = evaluate(["a", "b"], matrix)
    assert result["original_matrix"] == matrix
    assert result["validation"]["reciprocal_max_abs_error"] == pytest.approx(2e-9, abs=1e-15)
    with pytest.raises(ValueError):
        evaluate(["a", "b"], matrix, reciprocal_tolerance=1e-10)


def test_valid_inconsistent_matrix_requires_review_without_repair():
    # Three cyclic strong preferences cannot all be transitively satisfied.
    matrix = [[1, 9, 1 / 9], [1 / 9, 1, 9], [9, 1 / 9, 1]]
    result = evaluate(["a", "b", "c"], matrix)
    assert result["lambda_max"] == pytest.approx(1 + 9 + 1 / 9)
    assert result["CI"] == pytest.approx((1 + 9 + 1 / 9 - 3) / 2)
    assert result["CR"] == pytest.approx(result["CI"] / 0.58)
    assert result["CR"] > 0.1
    assert result["status"] == result["original_status"] == "REVIEW_REQUIRED"
    assert result["accepted"] is False
    assert result["provisional"] is False
    assert result["provisional_override"] is None
    assert result["original_matrix"] == matrix


def test_explicit_provisional_override_is_recorded_but_not_accepted_as_verified():
    matrix = [[1, 9, 1 / 9], [1 / 9, 1, 9], [9, 1 / 9, 1]]
    override = dict(reason="Explicit temporary stakeholder preference", authorized_by="fixture stakeholder")
    result = evaluate(["a", "b", "c"], matrix, provisional_override=override)
    assert result["status"] == "PROVISIONAL_OVERRIDE"
    assert result["original_status"] == "REVIEW_REQUIRED"
    assert result["accepted"] is False
    assert result["provisional"] is True
    assert result["provisional_override"] == override
    assert result["original_matrix"] == matrix
    override["reason"] = "changed later"
    assert result["provisional_override"]["reason"] != override["reason"]


@pytest.mark.parametrize("override", [True, "yes", {}, {"reason": ""},
    {"reason": "temporary", "authorized_by": "  "},
    {"reason": "temporary", "authorized_by": 5},
    {"reason": "temporary", "authorized_by": "fixture", "bad": np.inf}])
def test_override_requires_explicit_nonempty_portable_record(override):
    with pytest.raises(ValueError):
        evaluate(["a", "b", "c"], np.ones((3, 3)), provisional_override=override)


@pytest.mark.parametrize("ids,matrix,weights", [
    (["a"], [[1]], {"a": 1}),
    (["a", "b"], [[1, 3], [1 / 3, 1]], {"a": 0.75, "b": 0.25}),
])
def test_one_two_criteria_have_weights_but_no_cr_check(ids, matrix, weights):
    result = evaluate(ids, matrix)
    assert result["weights"] == pytest.approx(weights)
    assert result["CR"] is None
    assert result["status"] == "NOT_APPLICABLE"
    assert result["accepted"] is True
    assert result["validation"]["consistency_check_applicable"] is False


def test_exact_verified_ri_table_version_and_dimension_limit():
    result = evaluate([f"c{i}" for i in range(10)], np.ones((10, 10)))
    assert result["RI"] == 1.49
    assert result["ri_version"] == "saaty-rw-1987-p171-500-v1.0.0"
    assert result["ri_source"]["doi"] == "10.1016/0270-0255(87)90473-8"
    assert result["ri_source"]["page"] == 171
    assert len(result["ri_source"]["table_sha256"]) == 64
    with pytest.raises(ValueError, match="RI"):
        evaluate([f"c{i}" for i in range(11)], np.ones((11, 11)))


def test_result_is_deterministic_portable_and_principal_right_eigenvector():
    import json

    matrix = np.array([[1, 3, 5], [1 / 3, 1, 2], [1 / 5, 0.5, 1]])
    result = evaluate(["a", "b", "c"], matrix)
    assert result == evaluate(["a", "b", "c"], matrix)
    json.dumps(result, allow_nan=False)
    w = np.array(list(result["weights"].values()))
    assert matrix @ w == pytest.approx(result["lambda_max"] * w, rel=1e-10, abs=1e-12)
    assert sum(w) == pytest.approx(1)
    assert (w > 0).all()


def test_custom_review_convention_can_accept_same_unrepaired_matrix():
    matrix = [[1, 9, 1 / 9], [1 / 9, 1, 9], [9, 1 / 9, 1]]
    result = evaluate(["a", "b", "c"], matrix, consistency_threshold=10)
    assert result["status"] == "ACCEPTED"
    assert result["consistency_threshold"] == 10
    assert result["original_matrix"] == matrix


def test_original_numeric_judgments_preserve_integer_precision_and_snapshot():
    ratio = 9007199254740993
    matrix = [[1, ratio], [1 / ratio, 1]]
    result = evaluate(["a", "b"], matrix)
    assert result["original_matrix"][0][1] == ratio
    matrix[0][1] = 3
    assert result["original_matrix"][0][1] == ratio
