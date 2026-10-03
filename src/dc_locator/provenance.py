"""Shared vocabularies and the per-metric provenance record.

This module is the lowest layer of the shared contracts: it defines the
closed vocabularies (`str` enums) referenced throughout `AGENTS.md`, and the
`ProvenanceRecord` pydantic model that backs the long-form
`feature_provenance.parquet` table (one row per `grid_id x metric`;
see `docs/data_contracts.md`).

Nothing in this module depends on `dc_locator.schemas`; `schemas.py` imports
from here, never the reverse, so the vocabulary stays usable from any layer
(geography or model) without pulling in the full schema registry.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


# --------------------------------------------------------------------------
# Vocabularies
# --------------------------------------------------------------------------


class ValueStatus(str, Enum):
    """The epistemic status of one metric value (AGENTS.md section 3.4).

    Exactly one of these applies to every important metric:

    - OBSERVED: taken from a dataset (possibly spatially aggregated to the cell).
    - CALCULATED: derived by a documented formula from observed/scenario inputs.
    - SCENARIO: an explicit assumption or external scenario value (design
      PUE/WUE, SSP pathway, user input).
    - PROXY: an indirect indicator standing in for something unmeasured (e.g.
      distance to a transmission line as a proxy for -- NOT proof of -- grid
      access).
    - UNKNOWN: not available; the value is null and `missing_reason` explains why.

    UNKNOWN is never zero and never a PASS (AGENTS.md section 3.3).
    """

    OBSERVED = "observed"
    CALCULATED = "calculated"
    SCENARIO = "scenario"
    PROXY = "proxy"
    UNKNOWN = "unknown"


class Confidence(str, Enum):
    """Analyst/source confidence in a value, independent of its ValueStatus."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    UNKNOWN = "unknown"


class ScreeningOutcome(str, Enum):
    """Result of evaluating one screening requirement against one alternative.

    UNKNOWN is a distinct outcome, never silently folded into PASS or FAIL.
    """

    PASS = "PASS"
    FAIL = "FAIL"
    UNKNOWN = "UNKNOWN"


class ScreeningMode(str, Enum):
    """How an UNKNOWN critical requirement is handled during screening.

    - STRICT: an unknown critical requirement prevents acceptance.
    - EXPLORATORY: unknown requirements retain a conditional candidate,
      visibly flagged, rather than rejecting it outright.
    """

    STRICT = "STRICT"
    EXPLORATORY = "EXPLORATORY"


class SourceStatus(str, Enum):
    """Implementation/acquisition status of one data source or adapter.

    Distinguish *implemented* (code exists), *acquired* (data downloaded),
    and *analyzed* (features computed) in coverage reporting -- this
    enum alone only captures the coarse adapter-level status.
    """

    READY = "READY"
    PARTIAL = "PARTIAL"
    BLOCKED = "BLOCKED"
    NOT_IMPLEMENTED = "NOT_IMPLEMENTED"


class DataMode(str, Enum):
    """Whether a dataset or run is built from real acquired data or synthetic
    fixtures. Synthetic data must never appear under `data/processed/`
    (enforced by `dc_locator.io`, see AGENTS.md section 3.6).
    """

    REAL = "real"
    SYNTHETIC = "synthetic"


class AHPStatus(str, Enum):
    """Outcome of validating one AHP (Analytic Hierarchy Process) judgment matrix.

    - ACCEPTED: consistency ratio at or below the configured review threshold.
    - REVIEW_REQUIRED: consistency ratio exceeds the threshold; weights are
      preserved but must not be labeled accepted.
    - PROVISIONAL_OVERRIDE: a human explicitly recorded an override to use
      REVIEW_REQUIRED weights anyway; the override itself must be recorded.
    - NOT_APPLICABLE: AHP was not used for this run (e.g. equal-weight or
      user-weight baseline, or n < 2 criteria).
    """

    ACCEPTED = "ACCEPTED"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    PROVISIONAL_OVERRIDE = "PROVISIONAL_OVERRIDE"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class MissingReason(str, Enum):
    """Why a value is missing (status UNKNOWN or value is null).

    Extensible: later phases may append new members as new sources and
    processing steps are added. Never remove, rename, or renumber an
    existing member without a migration note in `docs/data_contracts.md`
    (schema changelog) -- existing stored data references these exact
    string values.
    """

    NOT_PROCESSED = "not_processed"  # pipeline has not reached this cell/metric yet
    OUTSIDE_SOURCE_COVERAGE = "outside_source_coverage"  # cell falls outside the source's spatial extent
    SOURCE_NODATA = "source_nodata"  # inside coverage, but the source itself reports no-data here
    SOURCE_BLOCKED = "source_blocked"  # source access is BLOCKED (login/CAPTCHA/manual-only); see docs/sources.md
    SOURCE_NOT_ACQUIRED = "source_not_acquired"  # adapter exists but this source has not been downloaded yet
    UNMAPPED = "unmapped"  # no documented mapping from source categories/fields to this metric
    NOT_APPLICABLE = "not_applicable"  # metric does not apply here (e.g. inherently non-numeric; see value_text)
    BELOW_MIN_COVERAGE = "below_min_coverage"  # spatial coverage fraction fell below a configured minimum
    INVALID_SOURCE_VALUE = "invalid_source_value"  # source value failed a sanity/range check and was rejected
    NOT_COMPUTED = "not_computed"  # a calculated metric whose required inputs are missing
    UNSUPPORTED_SOURCE_PERIOD = "unsupported_source_period"  # no native period; no interpolation/extension


# --------------------------------------------------------------------------
# Shared datetime helper
# --------------------------------------------------------------------------


def ensure_utc_datetime(value: datetime) -> datetime:
    """Require a timezone-aware UTC `datetime`.

    A naive datetime (no tzinfo) is rejected rather than silently assumed to
    be UTC, because AGENTS.md requires recorded timestamps to be
    unambiguous UTC. A non-UTC aware datetime is converted to UTC rather
    than rejected, since that conversion is exact and lossless.
    """
    if value.tzinfo is None:
        raise ValueError(
            "datetime must be timezone-aware (UTC); got a naive datetime. "
            "Use e.g. datetime.now(timezone.utc) or append 'Z'/'+00:00' to an ISO string."
        )
    return value.astimezone(timezone.utc)


# --------------------------------------------------------------------------
# ProvenanceRecord
# --------------------------------------------------------------------------


class ProvenanceRecord(BaseModel):
    """One row of the long-form provenance table (`feature_provenance.parquet`):
    the full history of exactly one `(grid_id, metric)` value.

    See `docs/data_contracts.md` for the authoritative column-by-column
    description, nullability, and the parquet schema this backs
    (`dc_locator.schemas.FEATURE_METADATA` / `FeatureMetadata`).
    """

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    # Identity
    grid_id: str = Field(min_length=1, description="Foreign key to GridCell.grid_id.")
    metric: str = Field(min_length=1, description="Canonical metric name, e.g. 'land_cover_developed_frac'.")

    # Value
    value: Optional[float] = Field(default=None, description="Numeric value in `unit`, or null -- see `value_text`.")
    value_text: Optional[str] = Field(default=None, description="Textual value when the metric is not numeric, or a label alongside `value`.")
    unit: Optional[str] = Field(default=None, description="Explicit unit (e.g. 'km2', 'frac', 'kg_per_mwh'); null for dimensionless/text metrics.")

    # Source
    source_id: str = Field(min_length=1, description="Foreign key to the source registry in configs/sources.yaml.")
    source_name: Optional[str] = Field(default=None, description="Human-readable source name.")
    source_url: Optional[str] = Field(default=None, description="Documentation or landing-page URL for the source; null if unverified (see configs/sources.yaml).")
    source_field: Optional[str] = Field(default=None, description="Field/column/band name within the source dataset.")
    source_version: Optional[str] = Field(default=None, description="Source dataset version or release identifier.")
    data_year: Optional[str] = Field(default=None, description="Data year or period, e.g. '2021' or '2016-2021'. A string to allow periods, not just single years.")
    retrieved_at: Optional[datetime] = Field(default=None, description="UTC timestamp the source was retrieved.")

    # Spatial / aggregation
    spatial_resolution: Optional[str] = Field(default=None, description="Native spatial resolution of the source, e.g. '30m', '4km', 'county', 'point'.")
    aggregation_method: Optional[str] = Field(default=None, description="How the source was aggregated to the cell, e.g. 'area-weighted mean', 'majority', 'nearest'.")
    coverage_frac: Optional[float] = Field(default=None, ge=0.0, le=1.0, description="Fraction (0-1) of the cell's study-area-intersection area actually covered by the source.")

    # Status
    status: ValueStatus
    confidence: Confidence
    missing_reason: Optional[MissingReason] = Field(
        default=None,
        description="Required when status is UNKNOWN or value is null; must be null otherwise.",
    )
    method: Optional[str] = Field(default=None, description="Free-text description of a CALCULATED value's formula, or notes on how a value was derived.")
    data_mode: DataMode

    @field_validator("retrieved_at")
    @classmethod
    def _validate_retrieved_at(cls, value: Optional[datetime]) -> Optional[datetime]:
        if value is None:
            return None
        return ensure_utc_datetime(value)

    @model_validator(mode="after")
    def _validate_status_value_missing_reason(self) -> "ProvenanceRecord":
        # Rule 1: UNKNOWN status means there is no value -- not even zero.
        # Checked as an explicit `is not None` comparison (not `if self.value`)
        # so that a value of exactly 0.0 is correctly treated as "present" and
        # rejected here, rather than slipping through a falsy-value bug.
        if self.status == ValueStatus.UNKNOWN and self.value is not None:
            raise ValueError(
                "ProvenanceRecord: value must be null when status is UNKNOWN "
                f"(got value={self.value!r} for grid_id={self.grid_id!r}, metric={self.metric!r}); "
                "this includes value == 0.0, which is a real observation, not 'unknown'."
            )

        if self.status == ValueStatus.UNKNOWN and self.value_text is not None:
            raise ValueError('ProvenanceRecord: value_text must be null when status is UNKNOWN')
        is_missing = self.status == ValueStatus.UNKNOWN or (self.value is None and self.value_text is None)
        if is_missing and self.missing_reason is None:
            raise ValueError(
                "ProvenanceRecord: missing_reason is required when status is UNKNOWN or value is null "
                f"(grid_id={self.grid_id!r}, metric={self.metric!r})."
            )
        if not is_missing and self.missing_reason is not None:
            raise ValueError(
                "ProvenanceRecord: missing_reason must be null when a non-null value is present and "
                f"status is not UNKNOWN (grid_id={self.grid_id!r}, metric={self.metric!r})."
            )
        return self


__all__ = [
    "ValueStatus",
    "Confidence",
    "ScreeningOutcome",
    "ScreeningMode",
    "SourceStatus",
    "DataMode",
    "AHPStatus",
    "MissingReason",
    "ensure_utc_datetime",
    "ProvenanceRecord",
]
