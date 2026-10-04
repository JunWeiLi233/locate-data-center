"""Scope warnings must describe the configured analysis, not a development default."""
from types import SimpleNamespace

from dc_locator import reporting


def test_national_scope_warning_reports_resolution_and_partial_evidence():
    pipeline = SimpleNamespace(config=SimpleNamespace(schema_version='2.1.0',data_mode=SimpleNamespace(value='real'),study_area='conus'))
    warning = reporting.scope_warning(pipeline)
    assert 'CONUS' in warning and 'source' in warning
    assert 'unsupported' not in warning and 'Development subset' not in warning


def test_legacy_scope_warning_is_preserved():
    pipeline = SimpleNamespace(config=SimpleNamespace(schema_version='2.0.0'))
    assert reporting.scope_warning(pipeline) == 'Development subset only; national feature/model execution is unsupported'
