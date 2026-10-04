"""Evidence validation and bounded record reuse on quarantined fixtures."""
import json

import pandas as pd
import pytest

from dc_locator.model.metrics import KEYS, ScoringProfile, assemble_metrics
from dc_locator.schemas import FeatureMetadata
from test_phase4 import decision_fixture


def test_provenance_materialized_once_but_every_row_still_validated(monkeypatch):
    geography, provenance, performance, eligibility, profile = decision_fixture()
    calls, validated = [], []
    original_records = pd.DataFrame.to_dict
    original_validate = FeatureMetadata.model_validate

    def records(frame, *args, **kwargs):
        if frame is provenance:
            calls.append(True)
        return original_records(frame, *args, **kwargs)

    def validate(record, *args, **kwargs):
        validated.append((record['grid_id'], record['metric']))
        return original_validate(record, *args, **kwargs)

    monkeypatch.setattr(pd.DataFrame, 'to_dict', records)
    monkeypatch.setattr(FeatureMetadata, 'model_validate', staticmethod(validate))
    assemble_metrics(geography, provenance, performance, eligibility, profile)
    assert validated == list(zip(provenance.grid_id, provenance.metric))
    assert len(calls) == 1, 'Native provenance records must not be materialized twice'


def test_alternative_loop_materializes_only_stable_fields_once(monkeypatch):
    geography, provenance, performance, eligibility, profile = decision_fixture()
    calls = []
    original_records = pd.DataFrame.to_dict

    def records(frame, *args, **kwargs):
        if {'assumptions_json', *KEYS}.issubset(frame.columns) and (
                'eligible' in frame or list(frame.columns) == [*KEYS, 'assumptions_json']):
            calls.append(list(frame.columns))
        return original_records(frame, *args, **kwargs)

    monkeypatch.setattr(pd.DataFrame, 'to_dict', records)
    assemble_metrics(geography, provenance, performance, eligibility, profile)
    assert calls == [[*KEYS, 'assumptions_json']]


def test_cached_records_preserve_nested_evidence_nulls_and_inputs():
    geography, provenance, performance, eligibility, profile = decision_fixture()
    originals = [frame.copy(deep=True) for frame in (geography, provenance, performance, eligibility)]
    frame, evidence = assemble_metrics(geography, provenance, performance, eligibility, profile)
    carbon = evidence.loc[evidence.metric_id.eq(profile.metrics[0].metric_id)].iloc[0]
    nested = json.loads(carbon.evidence_json)['source_evidence']
    assert nested['source_id'] == 'epa_egrid' and nested['source_field'] == 'SRC2ERTA'
    assert frame.critical_unknown.all() and frame.conditional.all()
    assert not frame.hard_fail.any()
    assert evidence.missing_reason.isna().all()
    for actual, original in zip((geography, provenance, performance, eligibility), originals):
        pd.testing.assert_frame_equal(actual, original, check_exact=True)


def test_unused_invalid_provenance_is_not_skipped():
    geography, provenance, performance, eligibility, profile = decision_fixture()
    unused = provenance.iloc[0].copy()
    unused['metric'] = 'unused_fixture_metric'
    unused['confidence'] = 'invalid'
    provenance = pd.concat([provenance, unused.to_frame().T], ignore_index=True)
    with pytest.raises(ValueError, match='confidence'):
        assemble_metrics(geography, provenance, performance, eligibility, profile,
                         provenance_grid_definition_id='fixture')


def test_duplicate_provenance_still_fails_before_lookup_use():
    geography, provenance, performance, eligibility, profile = decision_fixture()
    provenance = pd.concat([provenance, provenance.iloc[:1]], ignore_index=True)
    with pytest.raises(ValueError, match='Duplicate geographic/provenance IDs'):
        assemble_metrics(geography, provenance, performance, eligibility, profile,
                         provenance_grid_definition_id='fixture')


def test_metric_id_collision_preserves_prior_assumption_row_error():
    geography, provenance, performance, eligibility, profile = decision_fixture()
    document = profile.model_dump(mode='json')
    original_id = document['metrics'][0]['metric_id']
    document['metrics'][0]['metric_id'] = 'assumptions_json'
    tolerances = document['pareto']['absolute_tolerances']
    tolerances['assumptions_json'] = tolerances.pop(original_id)
    collision = ScoringProfile.model_validate(document)
    # Previously, the first metric overwrote the assumption JSON column and
    # the later water metric rejected that numeric value during JSON parsing.
    with pytest.raises(TypeError, match='JSON object'):
        assemble_metrics(geography, provenance, performance, eligibility, collision)
