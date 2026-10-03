"""Tests for dc_locator.provenance (previously had zero test coverage)."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from dc_locator.provenance import Confidence, DataMode, MissingReason, ProvenanceRecord, ValueStatus, ensure_utc_datetime


def _record(**overrides) -> dict:
    kwargs = dict(
        grid_id="g10000m-r0001-c0001",
        metric="land_cover_developed_frac",
        value=0.42,
        unit="frac",
        source_id="usgs_annual_nlcd",
        status=ValueStatus.OBSERVED,
        confidence=Confidence.HIGH,
        data_mode=DataMode.REAL,
    )
    kwargs.update(overrides)
    return kwargs


def test_observed_value_with_no_missing_reason_is_valid() -> None:
    rec = ProvenanceRecord(**_record())
    assert rec.value == 0.42
    assert rec.missing_reason is None


def test_observed_text_is_a_present_value() -> None:
    rec=ProvenanceRecord(**_record(value=None,value_text='ERCT'))
    assert rec.value_text=='ERCT' and rec.missing_reason is None


def test_unknown_status_forbids_text_value() -> None:
    with pytest.raises(ValidationError,match='value_text must be null'):
        ProvenanceRecord(**_record(value=None,value_text='ERCT',status=ValueStatus.UNKNOWN,
                                  missing_reason=MissingReason.NOT_PROCESSED))


def test_zero_value_is_not_treated_as_missing() -> None:
    """A real observation of exactly 0.0 must NOT be rejected as 'missing' (AGENTS.md section 3.3: UNKNOWN is never zero, but zero is not UNKNOWN either)."""
    rec = ProvenanceRecord(**_record(value=0.0))
    assert rec.value == 0.0
    assert rec.missing_reason is None


def test_unknown_status_requires_null_value() -> None:
    with pytest.raises(ValidationError, match="value must be null when status is UNKNOWN"):
        ProvenanceRecord(**_record(status=ValueStatus.UNKNOWN, confidence=Confidence.UNKNOWN, value=0.0, missing_reason=MissingReason.NOT_PROCESSED))


def test_unknown_status_requires_missing_reason() -> None:
    with pytest.raises(ValidationError, match="missing_reason is required"):
        ProvenanceRecord(**_record(status=ValueStatus.UNKNOWN, confidence=Confidence.UNKNOWN, value=None, missing_reason=None))


def test_null_value_with_non_unknown_status_requires_missing_reason() -> None:
    with pytest.raises(ValidationError, match="missing_reason is required"):
        ProvenanceRecord(**_record(value=None, missing_reason=None))  # status stays OBSERVED


def test_present_value_forbids_missing_reason() -> None:
    with pytest.raises(ValidationError, match="missing_reason must be null"):
        ProvenanceRecord(**_record(value=0.42, missing_reason=MissingReason.NOT_PROCESSED))


def test_valid_unknown_record() -> None:
    rec = ProvenanceRecord(**_record(status=ValueStatus.UNKNOWN, confidence=Confidence.UNKNOWN, value=None, missing_reason=MissingReason.SOURCE_NOT_ACQUIRED))
    assert rec.value is None
    assert rec.missing_reason == MissingReason.SOURCE_NOT_ACQUIRED


def test_extra_field_forbidden() -> None:
    with pytest.raises(ValidationError):
        ProvenanceRecord(**_record(), unexpected_field="nope")  # type: ignore[arg-type]


class TestEnsureUtcDatetime:
    def test_rejects_naive_datetime(self) -> None:
        with pytest.raises(ValueError, match="timezone-aware"):
            ensure_utc_datetime(datetime(2026, 10, 2, 12, 0, 0))

    def test_accepts_utc_datetime_unchanged(self) -> None:
        dt = datetime(2026, 10, 2, 12, 0, 0, tzinfo=timezone.utc)
        assert ensure_utc_datetime(dt) == dt

    def test_converts_non_utc_aware_datetime(self) -> None:
        from datetime import timedelta, timezone as tz

        eastern = tz(timedelta(hours=-5))
        dt = datetime(2026, 10, 2, 7, 0, 0, tzinfo=eastern)
        converted = ensure_utc_datetime(dt)
        assert converted.tzinfo == timezone.utc
        assert converted.hour == 12  # 07:00-05:00 -> 12:00 UTC


def test_retrieved_at_field_validator_applies_same_rule() -> None:
    with pytest.raises(ValidationError, match="timezone-aware"):
        ProvenanceRecord(**_record(retrieved_at=datetime(2026, 10, 2)))
