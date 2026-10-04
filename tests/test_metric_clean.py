"""Scalar cleaning preserves evidence and avoids pandas for built-in scalars."""
from datetime import date, datetime, timedelta, timezone

import numpy as np
import pandas as pd
import pytest

from dc_locator.model.metrics import clean, json_text


def test_builtin_scalar_records_do_not_dispatch_through_pandas(monkeypatch):
    original = pd.isna
    calls = []

    def tracked(value):
        calls.append(value)
        return original(value)

    monkeypatch.setattr(pd, 'isna', tracked)
    actual = clean({'source_evidence': {'value': 12.5, 'coverage_frac': 1.,
                    'source_id': 'fixture', 'unknown': None, 'count': 7, 'valid': True},
                    'other': [float('nan'), False, '']})
    assert actual == {'source_evidence': {'value': 12.5, 'coverage_frac': 1.,
                      'source_id': 'fixture', 'unknown': None, 'count': 7, 'valid': True},
                      'other': [None, False, '']}
    assert not calls, 'Built-in scalar cleaning must not repeat pandas missing-value dispatch'


@pytest.mark.parametrize(('value', 'expected'), [
    (None, None), (pd.NA, None), (float('nan'), None),
    (np.float32('nan'), None), (np.float64('nan'), None),
    (np.datetime64('NaT', 'ns'), None), (np.timedelta64('NaT', 'ns'), None),
    (pd.NaT, 'NaT'),
    (np.int64(7), 7), (np.uint64(7), 7), (np.bool_(True), True),
    (np.float32(1.5), 1.5), (np.float64(1.5), 1.5),
    (datetime(2026, 1, 1), '2026-01-01T00:00:00'),
    (datetime(2026, 1, 1, tzinfo=timezone(timedelta(hours=2))), '2025-12-31T22:00:00+00:00'),
    (pd.Timestamp('2026-01-01T01:00:00+01:00'), '2026-01-01T00:00:00+00:00'),
    (date(2026, 1, 1), date(2026, 1, 1)),
    (np.datetime64('2026-01-01'), date(2026, 1, 1)),
    ('', ''), (False, False), (0, 0), (-0., -0.),
])
def test_scalar_cleaning_matches_prior_values_and_types(value, expected):
    actual = clean(value)
    assert actual == expected and type(actual) is type(expected)


def test_nested_numpy_arrays_and_source_evidence_keep_nulls_and_inputs():
    values = np.array([[1.5, np.nan], [0., 2.]])
    record = {'source_evidence': {'values': values, 'status': 'unknown',
                                 'missing_reason': 'source_nodata', 'value': pd.NA},
              'alternatives': (np.int64(2), np.bool_(False))}
    assert clean(record) == {'source_evidence': {'values': [[1.5, None], [0., 2.]],
                            'status': 'unknown', 'missing_reason': 'source_nodata', 'value': None},
                            'alternatives': [2, False]}
    assert record['source_evidence']['values'] is values
    assert np.isnan(values[0, 1]) and record['source_evidence']['value'] is pd.NA


@pytest.mark.parametrize('value', [float('inf'), float('-inf'), np.float64('inf')])
def test_infinity_still_reaches_existing_json_rejection(value):
    assert clean(value) == value
    with pytest.raises(ValueError, match='Out of range float'):
        json_text(clean(value))


def test_subclasses_keep_original_item_conversion_and_zero_dimensional_error():
    class Scalar(int):
        def item(self):
            return 9

    class Text(str):
        def item(self):
            return 'converted'

    assert clean(Scalar(3)) == 9 and clean(Text('source')) == 'converted'
    with pytest.raises(TypeError, match='0-d array'):
        clean(np.array(3.))
