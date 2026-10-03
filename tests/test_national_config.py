"""Delivery schema 2.1.0 (national revision) is additive; 2.0.0 keeps its Phase 7 bounds."""
import pytest
import yaml

from dc_locator.paths import project_root
from dc_locator.run_config import DeliveryConfig, load_delivery_config, preflight

ROOT = project_root()


def synthetic(**changes):
    document = yaml.safe_load((ROOT / 'configs/run_synthetic.yaml').read_text(encoding='utf-8'))
    document.update(changes)
    return document


def national(**changes):
    return synthetic(schema_version='2.1.0', delivery_version='phase8_national_v1', **changes)


@pytest.mark.parametrize('changes', [
    dict(maximum_model_cells=10001),
    dict(geography_workers=1),
    dict(delivery_version='phase8_national_v1'),
])
def test_development_schema_keeps_phase7_bounds(changes):
    with pytest.raises(ValueError):
        DeliveryConfig.model_validate(synthetic(**changes))


def test_development_schema_rejects_temporal_scope():
    document = synthetic()
    document['future'] = dict(document['future'], temporal_output_scope='all_alternatives')
    with pytest.raises(ValueError, match='Unknown future configuration key'):
        DeliveryConfig.model_validate(document)


def test_national_schema_requires_national_revision():
    with pytest.raises(ValueError, match='phase8_national_v1'):
        DeliveryConfig.model_validate(synthetic(schema_version='2.1.0'))


@pytest.mark.parametrize('scope', ['all_alternatives', 'candidate_region_members'])
def test_national_schema_accepts_declared_temporal_scope(scope):
    document = national(maximum_model_cells=80000, geography_workers=4)
    document['future'] = dict(document['future'], temporal_output_scope=scope)
    config = DeliveryConfig.model_validate(document)
    assert config.maximum_model_cells == 80000 and config.geography_workers == 4


@pytest.mark.parametrize('changes', [dict(maximum_model_cells=100001), dict(geography_workers=9), dict(geography_workers=True)])
def test_national_schema_bounds(changes):
    with pytest.raises(ValueError):
        DeliveryConfig.model_validate(national(**changes))


def test_national_schema_rejects_unknown_temporal_scope():
    document = national()
    document['future'] = dict(document['future'], temporal_output_scope='everything')
    with pytest.raises(ValueError, match='temporal_output_scope'):
        DeliveryConfig.model_validate(document)


def test_national_scope_passes_preflight_only_under_national_schema(tmp_path):
    config = DeliveryConfig.model_validate(national(study_area='conus'))
    scope = preflight(config, ROOT, ROOT / '.pytest-work' / tmp_path.name / 'national')
    assert scope['national_model_supported'] is True and scope['scope'] == 'conus'
    with pytest.raises(ValueError, match='National model execution is unsupported'):
        preflight(DeliveryConfig.model_validate(synthetic(study_area='conus')), ROOT, None)


def test_accepted_phase7_runs_are_protected():
    with pytest.raises(ValueError, match='must not overwrite'):
        preflight(load_delivery_config(ROOT / 'configs/run_synthetic.yaml'), ROOT, ROOT / 'runs/phase7/overwrite')
