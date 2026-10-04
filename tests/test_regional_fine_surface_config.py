"""Phase 11 adds regional selection modes without changing existing regional configurations."""
import json
from types import SimpleNamespace

import geopandas as gpd
import pandas as pd
import pytest
import shapely
import yaml

from dc_locator.paths import project_root
from dc_locator.regional import COVERAGE_WARNINGS, PARENT_LABELS, RegionalConfig

FIELDS = {'schema_version', 'delivery_version', 'parent_config', 'grid_config', 'scoring_profile', 'selection',
          'maximum_region_extent_km', 'maximum_refined_cells', 'maximum_batch_cells', 'basis', 'rationale'}


def load(name):
    return yaml.safe_load((project_root() / 'configs' / name).read_text(encoding='utf-8'))


def test_existing_configuration_serializes_exactly_as_before():
    raw = load('run_regional_exploratory.yaml')
    config = RegionalConfig.model_validate(raw)
    assert set(config.model_dump(mode='json')) == FIELDS  # binding identities of completed runs are unchanged
    assert config.model_dump(mode='json') == {key: raw[key] for key in FIELDS}
    assert config.selection == 'representative_parent_cells' and config.delivery_version == 'phase9_regional_v1'


def test_fine_surface_configuration_is_bound_to_its_delivery_version():
    raw = load('run_regional_fine_surface.yaml')
    config = RegionalConfig.model_validate(raw)
    assert config.selection == 'national_fine_surface' and config.maximum_refined_cells // 2500 == 61
    for change in ({'delivery_version': 'phase9_regional_v1'}, {'selection': 'representative_parent_cells'}):
        with pytest.raises(ValueError, match='require each other'):
            RegionalConfig.model_validate({**raw, **change})
    assert set(COVERAGE_WARNINGS) == set(PARENT_LABELS) == {'representative_parent_cells', 'national_fine_surface',
                                                           'national_fine_region_parents'}
    assert COVERAGE_WARNINGS['representative_parent_cells'].startswith('Selected representative parent cells are refined in full')


def test_region_best_configuration_is_bound_to_the_same_delivery_version():
    raw = load('run_regional_fine_region.yaml')
    config = RegionalConfig.model_validate(raw)
    assert config.selection == 'national_fine_region_parents' and config.delivery_version == 'phase11_national_fine_surface_v1'
    assert config.model_dump(mode='json') == {key: raw[key] for key in FIELDS}
    with pytest.raises(ValueError, match='require each other'):
        RegionalConfig.model_validate({**raw, 'delivery_version': 'phase9_regional_v1'})


def test_selection_mode_decides_how_surface_parents_are_chosen(tmp_path, monkeypatch):
    """The fine stage runs once per mode; region mode picks each region's best member, the other the global top."""
    from dc_locator import fine_surface, regional
    summary = pd.DataFrame({'parent_grid_id': ['P1', 'P2', 'P3'], 'design_id': 'dry', 'scenario_id': 'current',
                            'best_grid_id': ['c1', 'c2', 'c3'], 'best_fine_score': [70.0, 90.0, 80.0]})
    calls = []

    def fake_stage(*, folder, identity, progress=None, **arguments):
        calls.append(sorted(arguments))
        folder.mkdir(parents=True, exist_ok=True)
        manifest = dict(stage_identity=identity, method_versions={}, cells=3, scored_alternatives=3)
        (folder / fine_surface.MANIFEST).write_text(json.dumps(manifest), encoding='utf-8')
        return summary, manifest

    monkeypatch.setattr(fine_surface, 'build_isolated', fake_stage)
    monkeypatch.setattr(regional, 'load_conus_boundary', lambda: SimpleNamespace(boundary=None))
    monkeypatch.setattr(regional, 'load_source_document', lambda *args: {})
    national = tmp_path / 'national'
    national.mkdir()
    pd.DataFrame({'grid_id': ['P1'], 'design_id': ['dry'], 'scenario_id': ['current']}).to_parquet(national / 'site_performance.parquet')
    pd.DataFrame({'region_id': ['R1', 'R1', 'R2'], 'grid_id': ['P1', 'P2', 'P3']}).to_parquet(national / 'region_membership.parquet')
    parent = SimpleNamespace(output=national, path=lambda value: value, config=SimpleNamespace(core_source_inputs='sources.json'),
                             source_hashes={})
    parent_grid = gpd.GeoDataFrame({'grid_id': ['P1', 'P2', 'P3']}, geometry=[shapely.box(i, 0, i + 1, 1) for i in range(3)], crs=5070)
    regions = pd.DataFrame({'region_id': ['R1', 'R2'], 'representative_grid_id': ['P1', 'P3']})
    by_region = RegionalConfig.model_validate(load('run_regional_fine_region.yaml'))
    by_score = RegionalConfig.model_validate({**load('run_regional_fine_surface.yaml'), 'maximum_refined_cells': 2500})
    for config, expected in ((by_region, ['P2', 'P3']), (by_score, ['P2'])):
        output = tmp_path / config.selection
        parents, record = regional._select_by_fine_surface(config, parent, parent_grid, regions, None, None, 'identity', output,
                                                           tmp_path, 2500.0, None)
        assert parents.grid_id.tolist() == expected
        assert record['manifest'] == 'national_fine_surface/' + fine_surface.MANIFEST and record['valued_cells'] == 3
    assert calls == [['boundary_geometry', 'grid_config', 'parent_grid', 'performance', 'profile', 'source_checksums',
                      'source_inputs']] * 2
