# AHP random index and supplied-judgment contract

This module uses one versioned RI table, `saaty-rw-1987-p171-500-v1.0.0`.
The source is **R. W. Saaty (1987)**, *The analytic hierarchy process—what it is
and how it is used*, Mathematical Modelling 9(3–5), 161–176, Section 4,
unnumbered RI table on printed page 171. The article describes 500 randomly
generated reciprocal matrices using the standard judgment scale and reciprocals.
[Primary article DOI](https://doi.org/10.1016/0270-0255(87)90473-8).

| Matrix dimension n | RI |
|---:|---:|
| 1 | 0.00 |
| 2 | 0.00 |
| 3 | 0.58 |
| 4 | 0.90 |
| 5 | 1.12 |
| 6 | 1.24 |
| 7 | 1.32 |
| 8 | 1.41 |
| 9 | 1.45 |
| 10 | 1.49 |

Verification on 2026-10-03 UTC inspected the original article's publicly indexed
[full-text transcription](https://studylib.net/doc/28260469/1987-saaty-ahp),
including the Section 4 RI table and sample description. Publisher bibliographic
metadata corroborated the title, author, year and DOI. Publisher PDF access returned
403 here; no original PDF was downloaded or represented as cached. This is a
transcription of the primary article, rather than an RI table inferred from a
secondary application paper. The transcription host is not the original publisher.

The canonical numeric table SHA256 is
`00ea0f7f32addd0e86b76fa0783fc24929bd1426d3fb7e8b3e3b8cf8018545f1`.
It hashes UTF-8 `json.dumps(RI_TABLE, sort_keys=True, separators=(",", ":"))`
with integer keys 1 through 10 and the float values above. This checksum identifies
the implemented table, **not source PDF bytes**. `ri_source` in every result carries
this checksum, the DOI, page, sample size and verification method.

Published RI variants differ; values such as 1.48 or 1.51 at dimension 10 are not
mixed into this version. Thomas L. Saaty's 2008 article is not cited as the source
of this table. Dimensions above 10 raise `ValueError`; no RI value is invented or
extrapolated. A different documented table would require a new RI version.

`evaluate_ahp(criteria_ids, matrix, *, active_criteria_ids=None,
consistency_threshold=0.1, reciprocal_tolerance=1e-8, provisional_override=None)`
evaluates supplied judgments only. IDs must be an ordered sequence of unique
nonempty strings without leading/trailing whitespace; sets and mappings are rejected.
Both matrix axes use the supplied ID order. Active
profile ID membership must match exactly, although its listing order may differ.
The evaluator neither selects criteria nor creates expert judgments.

Matrix entries must be real, finite and positive; booleans and complex values are
rejected. The matrix must be square, nonempty and match the criterion count.
Diagonal entries differ from 1 by at most `1e-12` in absolute terms. Reciprocity
uses `abs(A_ij * A_ji - 1) <= reciprocal_tolerance`, with no relative tolerance.
No input comparisons are rounded, clipped, completed, made reciprocal or repaired.
The independent `original_matrix` snapshot preserves supplied numeric judgments,
including integer precision that may exceed the eigensolver's float64 precision.

Weights use the normalized **principal right eigenvector** of the supplied matrix
via `numpy.linalg.eig`, with arbitrary eigenvector sign made positive. The solver
checks finite eigenpairs, numerical reality at relative tolerance `1e-10`, strictly
positive components, and an eigen-equation residual within `1e-10` after division
by `max(1, max(abs(A @ w)))`. Numerically unresolved inputs raise `ValueError`
instead of returning approximate or nonfinite weights. No geometric-mean or
column-average approximation substitutes for the principal eigenvector.

For `n >= 3`, `CI = (lambda_max - n)/(n - 1)` and `CR = CI/RI[n]`.
An absolute CI of at most `1e-12` is reported as zero for numerical roundoff;
`validation.ci_raw` and `ci_roundoff_adjusted` disclose that adjustment. Other
computed CI values are preserved, including small signed deviations possible
when reciprocity was accepted within tolerance. The comparisons themselves stay
unchanged. The review threshold is a finite nonnegative configurable convention.
The default `CR <= 0.10` establishes only numerical consistency acceptance;
it does not establish expert validity or suitability of a site.

For one/two criteria, RI is zero and CR is null; status is `NOT_APPLICABLE` and
validated weights remain available with `accepted=True`. CI is null for one
criterion and calculated for two. No division by zero occurs. For three or more,
an acceptable CR yields `ACCEPTED`. Excess CR yields `REVIEW_REQUIRED`,
`accepted=False`, with original comparisons and computed weights retained for review.

Provisional use requires a portable finite JSON record with nonempty `reason`
and `authorized_by` strings. If a review is required, it changes only the usage
label to `PROVISIONAL_OVERRIDE`, with `provisional=True`, `accepted=False` and
`original_status="REVIEW_REQUIRED"`. The override record is independently copied;
an override supplied with already-consistent judgments remains recorded but does
not make those judgments provisional. The evaluator checks the record's presence,
not the real-world identity or authority of its author.

Result keys are `criteria_ids`, `active_criteria_ids`, `original_matrix`, `weights`,
`lambda_max`, `CI`, `CR`, `RI`, `ri_version`, `ri_source`, `status`, `original_status`,
`accepted`, `provisional`, `provisional_override`, `consistency_threshold` and
`validation`. Equal/user/global hierarchical weighting and elicitation templates
belong to the Phase 4 runner, outside this module.

Independent fixtures include all-equal comparisons, exact ratios of
`[0.5, 0.3, 0.2]`, a cyclic inconsistent matrix, one/two criteria, preserved
nonstandard ratios and large integer judgments, invalid numeric/ID/shape evidence,
explicit overrides, deterministic results and the principal eigen-equation.
No expert comparisons are invented for a real run.
