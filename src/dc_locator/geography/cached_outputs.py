"""Reuse bound regional geography without reading raw datasets or model outputs."""
from __future__ import annotations

import hashlib
import json
import shutil
from collections.abc import Mapping
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import shapely

from dc_locator.io import read_parquet_metadata
from .features import AGGREGATION_VERSION, METRICS, SCHEMA_VERSION
from .sources.ingestion import file_digest


_DEFINITION = 'conus-epsg5070-ox-2500000-oy3400000-s1000m-v1'
_ARTIFACTS = ('us_grid.parquet', 'us_grid_dataset.parquet',
              'feature_provenance.parquet', 'data_manifest.json')


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError('Declared geography cache: ' + message)


def _document(path: Path) -> dict:
    try:
        document = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError) as error:
        raise ValueError(f'Declared geography cache: invalid document {path}') from error
    _require(isinstance(document, dict), f'document is not an object: {path}')
    return document


def _normalized(value):
    return json.loads(json.dumps(value, sort_keys=True, default=str))


# Source adapters that regional feature engineering never imports (county context for geography/socioeconomic.py).
# They cannot change regional geography, so they stay outside its code binding domain.
NON_FEATURE_SOURCES = frozenset({'saipe.py'})


def _feature_sources(package: Path) -> list[Path]:
    return [path for path in (package / 'geography/sources').glob('*.py') if path.name not in NON_FEATURE_SOURCES]


def _code_paths(root: Path) -> set[Path]:
    package = root / 'src/dc_locator'
    return {root / 'configs/grid_regional.yaml', root / 'configs/local_national_core_sources.json',
            *(package / name for name in ('geography/features.py', 'geography/grid.py',
                                         'geography/boundary.py', 'schemas.py', 'io.py', 'provenance.py')),
            *_feature_sources(package)}


def _same_grid(left: gpd.GeoDataFrame, right: gpd.GeoDataFrame) -> bool:
    if left.crs != right.crs or set(left.columns) != set(right.columns):
        return False
    if len(left) != len(right) or left.grid_id.duplicated().any() or right.grid_id.duplicated().any():
        return False
    left, right = (frame.sort_values('grid_id').reset_index(drop=True) for frame in (left, right))
    if not np.array_equal(left.geometry.to_wkb().to_numpy(), right.geometry.to_wkb().to_numpy()):
        return False
    try:
        pd.testing.assert_frame_equal(pd.DataFrame(left.drop(columns='geometry')).sort_index(axis=1),
                                      pd.DataFrame(right.drop(columns='geometry')).sort_index(axis=1),
                                      check_dtype=False, check_exact=True)
    except AssertionError:
        return False
    return True


def _parent_identity(grid: gpd.GeoDataFrame) -> str | None:
    required = {'grid_id', 'grid_definition_id', 'data_mode', 'row', 'col', 'geometry'}
    if not required <= set(grid.columns) or grid.empty or grid.crs is None or grid.crs.to_epsg() != 5070:
        return None
    if set(grid.data_mode) != {'real'} or set(grid.grid_definition_id) != {_DEFINITION} or not grid.grid_id.is_unique:
        return None
    indices = grid[['row', 'col']].to_numpy(dtype=float)
    if not np.isfinite(indices).all() or not np.equal(indices, np.floor(indices)).all() or (indices < 0).any():
        return None
    rows, cols = indices[:, 0].astype(int), indices[:, 1].astype(int)
    expected_ids = [f'g1000m-r{row:04d}-c{col:04d}' for row, col in zip(rows, cols)]
    if grid.grid_id.tolist() != expected_ids:
        return None
    x, y = -2500000. + cols * 1000., 3400000. - rows * 1000.
    if not shapely.equals_exact(grid.geometry.to_numpy(), shapely.box(x, y - 1000., x + 1000., y), 0).all():
        return None
    parents = {(row // 50, col // 50) for row, col in zip(rows, cols)}
    if len(parents) != 1:
        return None
    row, col = parents.pop()
    return f'g50000m-r{row:04d}-c{col:04d}'


def _verify_provenance(grid: gpd.GeoDataFrame, wide: gpd.GeoDataFrame, provenance: pd.DataFrame) -> None:
    definitions = {metric: (source, unit, field, status) for source, metrics in METRICS.items()
                   for metric, (unit, field, status) in metrics.items()}
    required = {'grid_id', 'metric', 'value', 'value_text', 'source_id', 'source_field', 'unit',
                'status', 'confidence', 'coverage_frac', 'missing_reason', 'data_mode'}
    _require(required <= set(provenance.columns), 'provenance fields missing')
    _require(set(provenance.grid_id) == set(grid.grid_id) and set(provenance.metric) == set(definitions)
             and len(provenance) == len(grid) * len(definitions)
             and not provenance.duplicated(['grid_id', 'metric']).any(), 'provenance identity/domain mismatch')
    _require(set(provenance.data_mode) == {'real'}, 'provenance data mode is not real')
    _require(provenance.status.isin(['observed', 'calculated', 'scenario', 'proxy', 'unknown']).all()
             and provenance.confidence.isin(['high', 'medium', 'low', 'unknown']).all(), 'invalid value metadata')
    unknown = provenance.status.eq('unknown')
    _require(provenance.loc[unknown, ['value', 'value_text']].isna().all().all()
             and provenance.loc[unknown, 'confidence'].eq('unknown').all()
             and provenance.loc[unknown, 'missing_reason'].map(lambda value: isinstance(value, str) and bool(value.strip())).all(),
             'UNKNOWN must retain null values, confidence and a missing reason')
    known = ~unknown
    _require((provenance.loc[known, 'value'].notna() ^ provenance.loc[known, 'value_text'].notna()).all()
             and provenance.loc[known, 'missing_reason'].isna().all(), 'known value is absent or contradictory')
    _require(np.isfinite(provenance.value.dropna().to_numpy(dtype=float)).all()
             and provenance.coverage_frac.dropna().between(0, 1 + 1e-9).all(), 'invalid numeric value/coverage')
    allowed = set(grid.columns) | {metric + suffix for metric in definitions
                                  for suffix in ('', '_status', '_confidence', '_coverage_frac')}
    _require(set(wide.columns) <= allowed, 'geography contains undeclared fields or model outputs')
    indexed = wide.set_index('grid_id').reindex(grid.grid_id)
    for metric, (source, unit, field, expected_status) in definitions.items():
        _require({metric, metric + '_status', metric + '_confidence'} <= set(wide.columns), 'wide metric missing: ' + metric)
        rows = provenance.loc[provenance.metric.eq(metric)].set_index('grid_id').reindex(indexed.index)
        _require(rows.source_id.eq(source).all() and rows.source_field.eq(field).all()
                 and rows.unit.fillna('<NULL>').eq(unit if unit is not None else '<NULL>').all(), 'native metric identity mismatch: ' + metric)
        _require(rows.status.isin([expected_status, 'unknown']).all(), 'native metric value status mismatch: ' + metric)
        _require(rows.status.equals(indexed[metric + '_status'].rename('status'))
                 and rows.confidence.equals(indexed[metric + '_confidence'].rename('confidence')), 'wide/provenance status mismatch: ' + metric)
        numeric, text = rows.value.notna(), rows.value_text.notna()
        _require(not numeric.any() or np.array_equal(indexed.loc[numeric, metric].to_numpy(dtype=float),
                                                     rows.loc[numeric, 'value'].to_numpy(dtype=float)), 'wide/provenance numeric mismatch: ' + metric)
        _require(not text.any() or indexed.loc[text, metric].equals(rows.loc[text, 'value_text'].rename(metric)), 'wide/provenance text mismatch: ' + metric)
        _require(indexed.loc[rows.status.eq('unknown'), metric].isna().all(), 'wide UNKNOWN is not null: ' + metric)


def _coverage(grid: gpd.GeoDataFrame, provenance: pd.DataFrame, source_inputs: Mapping) -> dict:
    report = dict(schema_version=SCHEMA_VERSION, data_mode='real', input_cells=len(grid), output_cells=len(grid),
                  analysis_extent=f'provided grid of {len(grid)} cells; source coverage reported separately',
                  analysis_bounds_5070_m=[float(value) for value in grid.total_bounds],
                  analysis_bounds_basis='full analytical squares; features use recorded CONUS intersections',
                  analysis_study_area_km2=float(grid.study_area_intersection_km2.sum()),
                  processed_tiles=0, resumed_tiles=0, geography_reused=True, sources={})
    for source, definitions in METRICS.items():
        source_prov = provenance.loc[provenance.source_id.eq(source)]
        known = source_prov.loc[~source_prov.status.eq('unknown')]
        counts = {metric: int((source_prov.loc[source_prov.metric.eq(metric), 'status'] != 'unknown').sum())
                  for metric in definitions}
        coverage = source_prov.coverage_frac.dropna()
        ready = all(count == len(grid) for count in counts.values()) and (coverage.empty or coverage.min() >= 1 - 1e-6)
        paths = source_inputs.get(source, {}).get('paths', {})
        acquired = bool(paths)
        report['sources'][source] = dict(implemented=True, acquired=acquired, analyzed=bool(len(known)),
            status='READY' if ready else 'PARTIAL' if acquired else 'BLOCKED', analyzed_cells=int(known.grid_id.nunique()),
            metric_nonmissing_cells=counts, coverage_min=float(coverage.min()) if len(coverage) else None,
            coverage_max=float(coverage.max()) if len(coverage) else None, usable_local_inputs=list(paths),
            remaining_requirements=[] if ready else ['Inspect metric coverage and source-specific limitations; provide official local files for missing geography/fields'])
    return report


def reuse_regional_geography(grid: gpd.GeoDataFrame, source_inputs: Mapping, source_hashes: Mapping[str, str],
                             output: str | Path, *, root: str | Path,
                             parent_grid_id: str | None = None) -> gpd.GeoDataFrame | None:
    """Copy compatible, verified geography only, or return ``None`` to rebuild.

    The caller must freshly verify native ``source_hashes`` before this call.
    Large raw files are never read here. Declared cache corruption raises
    ``ValueError``; absent caches and changed current inputs are cache misses.
    Only the fixed national 1 km children of one 50 km parent are supported.
    """
    root, output = Path(root).resolve(), Path(output).resolve()
    producer = root / 'runs/regional_geography_v1'
    manifest_path = producer / 'geography_manifest.json'
    inferred_parent = _parent_identity(grid)
    if inferred_parent is None or parent_grid_id is not None and parent_grid_id != inferred_parent or not manifest_path.is_file():
        return None
    _require(output.is_relative_to(root) and not output.is_relative_to(producer), 'reuse destination is outside the workspace or inside producer evidence')
    document = _document(manifest_path)
    if document.get('data_mode') != 'real' or document.get('grid_definition_id') != _DEFINITION:
        return None
    bindings = document.get('geography_code_config_hashes')
    _require(isinstance(bindings, dict), 'geography code/config bindings missing')
    paths = {Path(path).resolve(): sha for path, sha in bindings.items()}
    _require(set(paths) == _code_paths(root), 'incomplete or unexpected geography code/config binding domain')
    for path, sha in paths.items():
        if not path.is_file() or file_digest(path) != sha:
            return None
    records = document.get('parts')
    _require(isinstance(records, list) and all(isinstance(record, dict) for record in records), 'part bindings missing')
    _require(len({record.get('parent_grid_id') for record in records}) == len(records), 'duplicate parent bindings')
    record = next((record for record in records if record.get('parent_grid_id') == inferred_parent), None)
    if record is None:
        return None
    part = (producer / record.get('path', '')).resolve()
    _require(part.is_relative_to(producer / 'parts') and part.name == inferred_parent, 'part path/parent identity mismatch')
    hashes = record.get('output_hashes')
    _require(isinstance(hashes, dict) and set(hashes) == set(_ARTIFACTS), 'declared artifact binding domain mismatch')
    for name, sha in hashes.items():
        _require((part / name).is_file() and file_digest(part / name) == sha, 'artifact checksum mismatch: ' + name)
    manifest = _document(part / 'data_manifest.json')
    _require(manifest.get('data_mode') == 'real' and manifest.get('grid_definition_id') == _DEFINITION, 'part metadata identity mismatch')
    if manifest.get('aggregation_version') != AGGREGATION_VERSION:
        return None
    package = root / 'src/dc_locator'
    aggregation_paths = [package / 'geography/features.py', *_feature_sources(package),
                         *(package / name for name in ('provenance.py', 'schemas.py', 'io.py'))]
    revision = hashlib.sha256(''.join(paths[path] for path in sorted(aggregation_paths)).encode()).hexdigest()
    _require(manifest.get('code_sha256') == revision, 'part aggregation code binding mismatch')
    fingerprints = manifest.get('sources')
    _require(isinstance(fingerprints, dict) and fingerprints == manifest.get('source_inputs'), 'part source binding copies disagree')
    if set(fingerprints) != set(source_inputs):
        return None
    verified_sources = {}
    for source, cfg in source_inputs.items():
        binding = fingerprints[source]
        _require(isinstance(binding, dict) and isinstance(binding.get('inputs'), dict), 'native source binding malformed')
        if _normalized(binding.get('config')) != _normalized({key: value for key, value in cfg.items() if key != 'paths'}):
            return None
        inputs = cfg.get('paths', {})
        if set(binding['inputs']) != set(inputs) or cfg.get('data_mode', 'real') != 'real':
            return None
        for field, path in inputs.items():
            native = binding['inputs'][field]
            _require(isinstance(native, dict) and {'path', 'sha256'} <= set(native), 'native input binding missing')
            if str(path) != native['path'] or source_hashes.get(str(path)) != native['sha256']:
                return None
            verified_sources[str(path)] = native['sha256']
    declared_outputs = manifest.get('outputs')
    _require(isinstance(declared_outputs, dict) and set(declared_outputs) == set(_ARTIFACTS[1:3]), 'part output bindings missing')
    for name, binding in declared_outputs.items():
        _require(binding.get('sha256') == hashes[name] and binding.get('bytes') == (part / name).stat().st_size,
                 'part output byte/checksum binding mismatch: ' + name)
    for name, schema in zip(_ARTIFACTS[:3], ('GridCell', 'GeographicFeatureDataset', 'FeatureMetadata')):
        metadata = read_parquet_metadata(part / name)
        _require(metadata.get('schema') == schema and metadata.get('data_mode') == 'real'
                 and metadata.get('grid_definition_id') == _DEFINITION and bool(metadata.get('created_by')),
                 'Parquet metadata mismatch: ' + name)
        if metadata.get('schema_version') != SCHEMA_VERSION:
            return None
    cached_grid = gpd.read_parquet(part / 'us_grid.parquet')
    _require(_parent_identity(cached_grid) == inferred_parent and len(cached_grid) == record.get('cells'), 'cached grid identity/domain mismatch')
    if not _same_grid(grid, cached_grid):
        return None
    wide = gpd.read_parquet(part / 'us_grid_dataset.parquet')
    _require(set(cached_grid.columns) <= set(wide.columns)
             and _same_grid(cached_grid, wide[list(cached_grid.columns)]), 'cached geography/grid identity mismatch')
    _require(manifest.get('selected_grid_ids') == wide.grid_id.tolist(), 'manifest cell domain mismatch')
    provenance = pd.read_parquet(part / 'feature_provenance.parquet')
    _verify_provenance(cached_grid, wide, provenance)
    coverage = _coverage(cached_grid, provenance, source_inputs)
    native_rows = pd.util.hash_pandas_object(pd.DataFrame(grid.drop(columns='geometry')), index=False).values.tobytes()
    grid_sha = hashlib.sha256(native_rows + b''.join(grid.geometry.to_wkb()) + str(grid.crs).encode()).hexdigest()
    ledger = dict(schema_version='1.0.0', scope='facility-independent geography only',
        producer_path=str(producer), producer_manifest_sha256=file_digest(manifest_path), parent_grid_id=inferred_parent,
        grid_definition_id=_DEFINITION, requested_grid_content_sha256=grid_sha, requested_grid_ids=sorted(grid.grid_id),
        verified_code_config_hashes=bindings, verified_source_hashes=verified_sources,
        source_hash_verification='Fresh native hashes supplied by caller; native files are not reread during reuse',
        verified_output_hashes=hashes, copied_output_hashes={name: hashes[name] for name in _ARTIFACTS[1:]},
        coverage_report_method='Rebuilt from verified native provenance, current METRICS and current source inputs')
    output.mkdir(parents=True, exist_ok=True)
    for name in _ARTIFACTS[1:]:
        shutil.copyfile(part / name, output / name)
        _require(file_digest(output / name) == hashes[name], 'copied artifact checksum mismatch: ' + name)
    (output / 'coverage_report.json').write_text(json.dumps(coverage, indent=2, sort_keys=True), encoding='utf-8')
    (output / 'geography_reuse.json').write_text(json.dumps(ledger, indent=2, sort_keys=True), encoding='utf-8')
    return wide


__all__ = ['reuse_regional_geography']
