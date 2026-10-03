"""Evaluate supplied criterion judgments; never elicit or repair comparisons.

Weights are the normalized principal RIGHT eigenvector, not row averages or
geometric-mean approximations. See docs/research/phase4/ahp_ri.md for the exact
RI experiment/table version and the distinction between consistency and validity.
"""

from __future__ import annotations

from collections.abc import Sequence
import hashlib
import json
from numbers import Real
from typing import Any

import numpy as np


RI_VERSION = "saaty-rw-1987-p171-500-v1.0.0"
# R. W. Saaty (1987), Section 4, unnumbered RI table, printed page 171.
RI_TABLE = {1: 0.0, 2: 0.0, 3: 0.58, 4: 0.90, 5: 1.12,
            6: 1.24, 7: 1.32, 8: 1.41, 9: 1.45, 10: 1.49}
_RI_CANONICAL = json.dumps(RI_TABLE, sort_keys=True, separators=(",", ":"))
RI_SOURCE = {
    "author": "R. W. Saaty",
    "year": 1987,
    "title": "The analytic hierarchy process—what it is and how it is used",
    "journal": "Mathematical Modelling 9(3–5), 161–176",
    "doi": "10.1016/0270-0255(87)90473-8",
    "url": "https://doi.org/10.1016/0270-0255(87)90473-8",
    "section": 4,
    "page": 171,
    "table": "unnumbered average random consistency index table",
    "experiment_sample_size": 500,
    "verified_transcription_url": "https://studylib.net/doc/28260469/1987-saaty-ahp",
    "verified_at_utc": "2026-10-03",
    "verification_method": "Primary article text transcription; publisher bibliographic metadata corroborated; original PDF not cached",
    "table_sha256": hashlib.sha256(_RI_CANONICAL.encode("utf-8")).hexdigest(),
}
DIAGONAL_ABS_TOLERANCE = 1e-12
EIGEN_IMAGINARY_REL_TOLERANCE = 1e-10
EIGEN_RESIDUAL_REL_TOLERANCE = 1e-10
CI_ROUNDOFF_ABS_TOLERANCE = 1e-12


def _ids(value: Sequence[str], label: str) -> list[str]:
    if isinstance(value, (str, bytes)) or not isinstance(value, (Sequence, np.ndarray)):
        raise ValueError(f"{label} must be a sequence of unique criterion ID strings")
    try:
        result = list(value)
    except TypeError as exc:
        raise ValueError(f"{label} must be a sequence of criterion ID strings") from exc
    if not result or any(not isinstance(v, str) or not v or v != v.strip() for v in result):
        raise ValueError(f"{label} must contain nonempty, unmodified ID strings")
    if len(result) != len(set(result)):
        raise ValueError(f"{label} contains duplicate criterion IDs")
    return result


def _nonnegative_finite(value: float, label: str) -> float:
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, Real):
        raise ValueError(f"{label} must be a finite nonnegative number")
    value = float(value)
    if not np.isfinite(value) or value < 0:
        raise ValueError(f"{label} must be a finite nonnegative number")
    return value


def _override_record(value: dict | None) -> dict | None:
    if value is None:
        return None
    if not isinstance(value, dict) or any(
        not isinstance(value.get(key), str) or not value[key].strip()
        for key in ("reason", "authorized_by")
    ):
        raise ValueError("provisional_override requires nonempty reason and authorized_by strings")
    try:
        # Independent portable snapshot: later caller mutations cannot alter it.
        return json.loads(json.dumps(value, allow_nan=False))
    except (ValueError, TypeError) as exc:
        raise ValueError("provisional_override must be a finite JSON-compatible record") from exc


def evaluate_ahp(
    criteria_ids: Sequence[str],
    matrix: Sequence[Sequence[float]] | np.ndarray,
    *,
    active_criteria_ids: Sequence[str] | None = None,
    consistency_threshold: float = 0.1,
    reciprocal_tolerance: float = 1e-8,
    provisional_override: dict | None = None,
) -> dict[str, Any]:
    """Validate and evaluate one complete matrix of supplied criterion judgments.

    Matrix axes follow ``criteria_ids`` exactly. The active profile must have
    identical ID membership; its listing order may differ because weights are
    returned by ID. No judgment is reordered, rounded to the elicitation scale,
    clipped, completed, or made reciprocal by this function.

    Invalid input or numerically unresolved eigensystems raise ``ValueError``.
    A valid but inconsistent input returns REVIEW_REQUIRED. An explicit override
    permits only a PROVISIONAL_OVERRIDE result, never ``accepted=True``. For one
    or two criteria weights are available but CR is NOT_APPLICABLE.
    """
    ids = _ids(criteria_ids, "criteria_ids")
    active_ids = ids if active_criteria_ids is None else _ids(active_criteria_ids, "active_criteria_ids")
    if set(ids) != set(active_ids):
        raise ValueError("criterion IDs must match the active scoring profile exactly")
    threshold = _nonnegative_finite(consistency_threshold, "consistency_threshold")
    reciprocal_tol = _nonnegative_finite(reciprocal_tolerance, "reciprocal_tolerance")
    override = _override_record(provisional_override)
    n = len(ids)
    if n not in RI_TABLE:
        raise ValueError(f"RI table {RI_VERSION} does not support dimension {n}; supported dimensions are 1–10")
    try:
        supplied = np.asarray(matrix)
        original = np.asarray(matrix, dtype=object)
    except (ValueError, TypeError) as exc:
        raise ValueError("matrix must be square, nonempty, and numeric") from exc
    if supplied.ndim != 2 or supplied.shape != (n, n):
        raise ValueError("matrix must be square and match the supplied criterion count")
    if supplied.dtype.kind not in "iuf" or any(isinstance(v, (bool, np.bool_)) for v in original.flat):
        raise ValueError("matrix entries must be real numeric judgments, not booleans or complex values")
    values = supplied.astype(np.float64, copy=True)
    if not np.isfinite(values).all() or not (values > 0).all():
        raise ValueError("matrix entries must be finite and strictly positive")
    diagonal_error = float(np.max(np.abs(np.diag(values) - 1)))
    if diagonal_error > DIAGONAL_ABS_TOLERANCE:
        raise ValueError("matrix diagonal must equal 1 within the documented absolute tolerance")
    with np.errstate(over="ignore", invalid="ignore"):
        products = values * values.T
    reciprocal_error = float(np.max(np.abs(products - 1)))
    if not np.isfinite(reciprocal_error) or reciprocal_error > reciprocal_tol:
        raise ValueError("matrix must be reciprocal: abs(A_ij * A_ji - 1) exceeds tolerance")

    try:
        eigenvalues, eigenvectors = np.linalg.eig(values)
    except np.linalg.LinAlgError as exc:
        raise ValueError("principal eigenvector could not be resolved numerically") from exc
    principal = int(np.argmax(eigenvalues.real))
    eigenvalue = eigenvalues[principal]
    eigenvector = eigenvectors[:, principal]
    if not np.isfinite(eigenvalue) or abs(eigenvalue.imag) > EIGEN_IMAGINARY_REL_TOLERANCE * max(1.0, abs(eigenvalue.real)):
        raise ValueError("principal eigenvalue is nonfinite or not numerically real")
    if not np.isfinite(eigenvector).all() or np.max(np.abs(eigenvector.imag)) > EIGEN_IMAGINARY_REL_TOLERANCE * max(1.0, float(np.max(np.abs(eigenvector.real)))):
        raise ValueError("principal right eigenvector is nonfinite or not numerically real")
    vector = eigenvector.real.copy()
    if vector.sum() < 0:
        vector *= -1  # Eigenvectors have arbitrary sign; judgments are unchanged.
    if not (vector > 0).all() or not np.isfinite(vector.sum()) or vector.sum() <= 0:
        raise ValueError("principal right eigenvector is not strictly positive")
    weights = vector / vector.sum()
    lambda_max = float(eigenvalue.real)
    with np.errstate(over="ignore", invalid="ignore"):
        aw = values @ weights
        residual = float(np.max(np.abs(aw - lambda_max * weights)))
    residual_scale = max(1.0, float(np.max(np.abs(aw))))
    if not np.isfinite(residual) or residual / residual_scale > EIGEN_RESIDUAL_REL_TOLERANCE:
        raise ValueError("principal right eigenvector residual exceeds numerical tolerance")

    raw_ci = None if n == 1 else (lambda_max - n) / (n - 1)
    ci = raw_ci
    roundoff_adjusted = ci is not None and abs(ci) <= CI_ROUNDOFF_ABS_TOLERANCE
    if roundoff_adjusted:
        ci = 0.0
    cr = None if n < 3 else ci / RI_TABLE[n]
    original_status = "NOT_APPLICABLE" if n < 3 else "ACCEPTED" if cr <= threshold else "REVIEW_REQUIRED"
    provisional = original_status == "REVIEW_REQUIRED" and override is not None
    status = "PROVISIONAL_OVERRIDE" if provisional else original_status
    return {
        "criteria_ids": ids,
        "active_criteria_ids": active_ids,
        "original_matrix": original.tolist(),
        "weights": {criterion: float(weight) for criterion, weight in zip(ids, weights, strict=True)},
        "lambda_max": lambda_max,
        "CI": ci,
        "CR": cr,
        "RI": RI_TABLE[n],
        "ri_version": RI_VERSION,
        "ri_source": dict(RI_SOURCE),
        "status": status,
        "original_status": original_status,
        "accepted": original_status != "REVIEW_REQUIRED",
        "provisional": provisional,
        "provisional_override": override,
        "consistency_threshold": threshold,
        "validation": {
            "square_nonempty": True, "criterion_ids_unique": True,
            "active_criteria_match": True, "finite_positive": True,
            "diagonal_max_abs_error": diagonal_error,
            "diagonal_abs_tolerance": DIAGONAL_ABS_TOLERANCE,
            "reciprocal_max_abs_error": reciprocal_error,
            "reciprocal_abs_tolerance": reciprocal_tol,
            "eigenvector_method": "normalized principal right eigenvector (numpy.linalg.eig)",
            "eigen_imaginary_relative_tolerance": EIGEN_IMAGINARY_REL_TOLERANCE,
            "eigen_residual_relative_tolerance": EIGEN_RESIDUAL_REL_TOLERANCE,
            "eigen_residual_relative": residual / residual_scale,
            "ci_raw": raw_ci, "ci_roundoff_adjusted": roundoff_adjusted,
            "ci_roundoff_abs_tolerance": CI_ROUNDOFF_ABS_TOLERANCE,
            "consistency_check_applicable": n >= 3,
            "consistency_threshold_met": None if n < 3 else cr <= threshold,
            "interpretation": "Consistency acceptance only; does not establish expert validity or site suitability",
            "judgments_repaired": False,
        },
    }
