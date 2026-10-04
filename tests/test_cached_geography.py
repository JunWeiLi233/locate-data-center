"""Small quarantined fixtures for verified, geography-only regional reuse."""
from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import pytest
import shapely

from dc_locator.geography.features import AGGREGATION_VERSION, METRICS, SCHEMA_VERSION
from dc_locator.geography.sources.ingestion import file_digest
from dc_locator.io import write_geoparquet, write_parquet
from dc_locator.provenance import DataMode


ROOT = Path(__file__).resolve().parents[1]
DEFINITION = 'conus-epsg5070-ox-2500000-oy3400000-s1000m-v1'
PARENT = 'g50000m-r0007-c0036'
ARTIFACTS = ('us_grid.parquet', 'us_grid_dataset.parquet',
             'feature_provenance.parquet', 'data_manifest.json')


def emit(path, document):
    path.write_text(json.dumps(document, sort_keys=True, default=str), encoding='utf-8')


def code_files(root):
    from dc_locator.geography.cached_outputs import NON_FEATURE_SOURCES
    package = root / 'src/dc_locator'
    return [root / 'configs/grid_regional.yaml', root / 'configs/local_national_core_sources.json',
            *(package / name for name in ('geography/features.py', 'geography/grid.py',
                                         'geography/boundary.py', 'schemas.py', 'io.py', 'provenance.py')),
            *sorted(path for path in (ROOT / 'src/dc_locator/geography/sources').glob('*.py')
                    if path.name not in NON_FEATURE_SOURCES)]


def test_accepted_cache_producer_binds_the_current_feature_code_domain():
    """A new source module must not turn the accepted regional geography cache into a hard failure."""
    from dc_locator.geography.cached_outputs import _code_paths
    manifest = ROOT / 'runs/regional_geography_v1/geography_manifest.json'
    if not manifest.is_file():
        pytest.skip('accepted regional geography cache is not present in this checkout')
    bound = json.loads(manifest.read_text(encoding='utf-8'))['geography_code_config_hashes']
    assert {Path(path).resolve() for path in bound} == _code_paths(ROOT)


def test_non_feature_sources_are_never_imported_by_feature_code():
    import ast
    from dc_locator.geography.cached_outputs import NON_FEATURE_SOURCES, _code_paths
    excluded = {name.removesuffix('.py') for name in NON_FEATURE_SOURCES}
    assert all((ROOT / 'src/dc_locator/geography/sources' / name).is_file() for name in NON_FEATURE_SOURCES)
    for path in (path for path in _code_paths(ROOT) if path.suffix == '.py'):
        tree = ast.parse(path.read_text(encoding='utf-8'))
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split('.')[-1])
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                imported.update(alias.name.split('.')[-1] for alias in node.names)
        assert not imported & excluded, path


@pytest.fixture
def cache(tmp_path):
    root = tmp_path / 'workspace'
    producer = root / 'runs/regional_geography_v1'
    part = producer / 'parts' / PARENT
    part.mkdir(parents=True)
    bindings = {}
    for original in code_files(ROOT):
        target = root / original.relative_to(ROOT)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(original, target)
        bindings[str(target)] = file_digest(target)
    native = root / 'data/raw/test-native.bin'
    native.parent.mkdir(parents=True)
    native.write_bytes(b'quarantined unit-test native input')
    source_inputs = {source: {'data_mode': 'real', 'source_name': source, 'paths': {}}
                     for source in METRICS}
    source_inputs['usgs_annual_nlcd']['paths'] = {'land_cover': str(native)}
    source_hashes = {str(native): file_digest(native)}
    fingerprints = {source: {'config': {k: v for k, v in cfg.items() if k != 'paths'},
        'inputs': {field: {'path': path, 'sha256': source_hashes[path]}
                   for field, path in cfg['paths'].items()}}
                   for source, cfg in source_inputs.items()}
    rows, cols = np.array([350, 350]), np.array([1800, 1801])
    x, y = -2500000 + cols * 1000, 3400000 - rows * 1000
    grid = gpd.GeoDataFrame(dict(grid_id=[f'g1000m-r{r:04d}-c{c:04d}' for r, c in zip(rows, cols)],
        row=rows, col=cols, grid_definition_id=DEFINITION, data_mode='real',
        cell_area_km2=1., study_area_intersection_km2=1., study_area_frac=1.,
        is_boundary_cell=False, county_geoid_primary=['00001', '00002']),
        geometry=shapely.box(x, y - 1000, x + 1000, y), crs=5070)
    wide = grid.copy()
    records, values = [], {}
    for source, definitions in METRICS.items():
        for metric, (unit, field, status) in definitions.items():
            known = metric == 'potentially_suitable_land_frac'
            values[metric] = [.75 if known else None, None]
            values[metric + '_status'] = [status if known else 'unknown', 'unknown']
            values[metric + '_confidence'] = ['low' if known else 'unknown', 'unknown']
            for index, grid_id in enumerate(grid.grid_id):
                present = known and index == 0
                records.append(dict(grid_id=grid_id, metric=metric, value=.75 if present else None,
                    value_text=None, unit=unit, source_id=source, source_field=field,
                    data_mode='real', status=status if present else 'unknown',
                    confidence='low' if present else 'unknown',
                    missing_reason=None if present else 'quarantined_fixture_no_observation',
                    coverage_frac=1. if present else 0.))
    wide = gpd.GeoDataFrame(pd.concat([wide, pd.DataFrame(values)], axis=1), crs=grid.crs)
    provenance = pd.DataFrame(records)
    write_geoparquet(grid, part / 'us_grid.parquet', schema_name='GridCell', schema_version=SCHEMA_VERSION,
                    data_mode=DataMode.REAL, grid_definition_id=DEFINITION)
    write_geoparquet(wide, part / 'us_grid_dataset.parquet', schema_name='GeographicFeatureDataset',
                    schema_version=SCHEMA_VERSION, data_mode=DataMode.REAL, grid_definition_id=DEFINITION)
    write_parquet(provenance, part / 'feature_provenance.parquet', schema_name='FeatureMetadata',
                  schema_version=SCHEMA_VERSION, data_mode=DataMode.REAL, grid_definition_id=DEFINITION)
    package = root / 'src/dc_locator'
    aggregation_files = [package / 'geography/features.py',
                         *(package / 'geography/sources').glob('*.py'),
                         *(package / name for name in ('provenance.py', 'schemas.py', 'io.py'))]
    revision = hashlib.sha256(''.join(file_digest(p) for p in sorted(aggregation_files)).encode()).hexdigest()
    manifest = dict(aggregation_version=AGGREGATION_VERSION, code_sha256=revision, data_mode='real',
        grid_definition_id=DEFINITION, selected_grid_ids=grid.grid_id.tolist(),
        sources=fingerprints, source_inputs=fingerprints, tile_keys=['fixture-tile'],
        outputs={name: {'sha256': file_digest(part / name), 'bytes': (part / name).stat().st_size}
                 for name in ARTIFACTS[1:3]})
    emit(part / 'data_manifest.json', manifest)
    producer_manifest = dict(data_mode='real', grid_definition_id=DEFINITION,
        geography_code_config_hashes=bindings,
        parts=[dict(parent_grid_id=PARENT, cells=len(grid), path=f'parts/{PARENT}',
                    output_hashes={name: file_digest(part / name) for name in ARTIFACTS})])
    emit(producer / 'geography_manifest.json', producer_manifest)
    (part / 'coverage_report.json').write_text('unbound and intentionally invalid JSON')
    (part / 'mcda_rankings.parquet').write_bytes(b'never copy scientific decisions')
    return dict(root=root, producer=producer, part=part, grid=grid, wide=wide,
                provenance=provenance, source_inputs=source_inputs, source_hashes=source_hashes,
                output=root / 'runs/model/parts' / PARENT)


def reuse(cache, **kwargs):
    from dc_locator.geography.cached_outputs import reuse_regional_geography
    return reuse_regional_geography(cache['grid'], cache['source_inputs'], cache['source_hashes'],
                                   cache['output'], root=cache['root'], **kwargs)


def rebind_artifacts(cache):
    part = cache['part']
    manifest = json.loads((part / 'data_manifest.json').read_text())
    for name in ARTIFACTS[1:3]:
        manifest['outputs'][name] = dict(sha256=file_digest(part / name), bytes=(part / name).stat().st_size)
    emit(part / 'data_manifest.json', manifest)
    producer = cache['producer'] / 'geography_manifest.json'
    document = json.loads(producer.read_text())
    document['parts'][0]['output_hashes'] = {name: file_digest(part / name) for name in ARTIFACTS}
    emit(producer, document)


def test_exact_geography_reuse_preserves_native_bytes_and_unknowns(cache):
    result = reuse(cache, parent_grid_id=PARENT)
    pd.testing.assert_frame_equal(result, cache['wide'], check_dtype=False)
    for name in ARTIFACTS[1:]:
        assert file_digest(cache['output'] / name) == file_digest(cache['part'] / name)
    assert not (cache['output'] / 'mcda_rankings.parquet').exists()
    provenance = pd.read_parquet(cache['output'] / 'feature_provenance.parquet')
    unknown = provenance.status.eq('unknown')
    assert provenance.loc[unknown, ['value', 'value_text']].isna().all().all()
    assert provenance.loc[unknown, 'missing_reason'].notna().all()
    coverage = json.loads((cache['output'] / 'coverage_report.json').read_text())
    nlcd = coverage['sources']['usgs_annual_nlcd']
    assert nlcd['acquired'] and nlcd['analyzed'] and nlcd['analyzed_cells'] == 1
    assert nlcd['metric_nonmissing_cells']['potentially_suitable_land_frac'] == 1
    assert coverage['sources']['epa_egrid']['acquired'] is False
    ledger = json.loads((cache['output'] / 'geography_reuse.json').read_text())
    assert ledger['scope'] == 'facility-independent geography only'
    assert ledger['producer_manifest_sha256'] == file_digest(cache['producer'] / 'geography_manifest.json')
    assert ledger['verified_output_hashes'] == {name: file_digest(cache['part'] / name) for name in ARTIFACTS}
    assert ledger['verified_source_hashes'] == cache['source_hashes']


def test_missing_cache_returns_none_without_output(cache):
    (cache['producer'] / 'geography_manifest.json').unlink()
    assert reuse(cache) is None
    assert not cache['output'].exists()


@pytest.mark.parametrize('mismatch', ['code', 'source_config', 'source_hash', 'domain', 'geometry', 'attribute'])
def test_incompatible_request_falls_back_without_copying(cache, mismatch):
    if mismatch == 'code':
        (cache['root'] / 'src/dc_locator/geography/grid.py').write_text('changed geography code')
    elif mismatch == 'source_config':
        cache['source_inputs']['usgs_annual_nlcd']['source_version'] = 'different native version'
    elif mismatch == 'source_hash':
        cache['source_hashes'][next(iter(cache['source_hashes']))] = '0' * 64
    elif mismatch == 'domain':
        cache['grid'] = cache['grid'].iloc[:1].copy()
    elif mismatch == 'geometry':
        cache['grid'].geometry = cache['grid'].geometry.translate(xoff=1.)
    else:
        cache['grid'].loc[0, 'county_geoid_primary'] = '99999'
    assert reuse(cache) is None
    assert not cache['output'].exists()


@pytest.mark.parametrize('name', ARTIFACTS)
def test_corrupt_declared_artifact_is_an_error(cache, name):
    with (cache['part'] / name).open('ab') as handle:
        handle.write(b'damage')
    with pytest.raises(ValueError, match='(?i)checksum'):
        reuse(cache)
    assert not cache['output'].exists()


def test_omitted_code_binding_is_an_error(cache):
    path = cache['producer'] / 'geography_manifest.json'
    document = json.loads(path.read_text())
    document['geography_code_config_hashes'].pop(next(iter(document['geography_code_config_hashes'])))
    emit(path, document)
    with pytest.raises(ValueError, match='(?i)binding'):
        reuse(cache)


@pytest.mark.parametrize('mutation', ['unknown_zero', 'wide_domain'])
def test_rebound_internal_corruption_cannot_hide_unknown_or_identity(cache, mutation):
    if mutation == 'unknown_zero':
        provenance = cache['provenance'].copy()
        provenance.loc[provenance.status.eq('unknown').idxmax(), 'value'] = 0.
        write_parquet(provenance, cache['part'] / 'feature_provenance.parquet', schema_name='FeatureMetadata',
                      schema_version=SCHEMA_VERSION, data_mode=DataMode.REAL, grid_definition_id=DEFINITION)
    else:
        wide = cache['wide'].copy()
        wide.loc[0, 'grid_id'] = 'g1000m-r0350-c9999'
        write_geoparquet(wide, cache['part'] / 'us_grid_dataset.parquet', schema_name='GeographicFeatureDataset',
                        schema_version=SCHEMA_VERSION, data_mode=DataMode.REAL, grid_definition_id=DEFINITION)
    rebind_artifacts(cache)
    with pytest.raises(ValueError, match='(?i)unknown|identity|domain'):
        reuse(cache)
    assert not cache['output'].exists()


def test_reuse_does_not_rehash_native_sources(cache, monkeypatch):
    import dc_locator.geography.cached_outputs as module
    original = module.file_digest
    def limited_digest(path):
        assert not Path(path).is_relative_to(cache['root'] / 'data/raw'), 'Repeated raw source hash'
        return original(path)
    monkeypatch.setattr(module, 'file_digest', limited_digest)
    assert reuse(cache) is not None


def test_supplied_parent_must_match_global_child_indices(cache):
    assert reuse(cache, parent_grid_id='g50000m-r0000-c0000') is None
    assert not cache['output'].exists()
