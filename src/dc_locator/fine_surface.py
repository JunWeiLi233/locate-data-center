"""National 1 km screening surface stage (Phase 11): fine features for every CONUS cell, scores, parent ranking.

Shared infrastructure composing ``geography.fine_features`` and ``model.fine_selection``. A stage folder holds:

- ``fine_surface_cells.parquet``: values and evidence companions per retained 1 km cell (NationalFineSurfaceCell 1.1.0);
- ``feature_provenance.parquet``: seven FeatureMetadata 1.1.0 records per retained cell;
- ``fine_surface_parents.parquet``: best/90th-percentile fine score per 50 km parent and design/scenario
  (NationalFineSurfaceParent 1.0.0);
- ``fine_surface_manifest.json``: stage identity, method versions, weights, design constants, source checksums,
  counts, resources and output hashes.

A completed stage with the same identity and intact outputs is reused; any other identity is refused.
The surface ranks parents for refinement only. It never replaces the regional evidence of a refined cell.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import rasterio
import shapely

from dc_locator.geography.fine_features import (FEATURE_COLUMNS, EVIDENCE_COLUMNS, FINE_FEATURE_VERSION,
    feature_metadata, feature_provenance, load_fine_sources, window_cells, window_features)
from dc_locator.geography.sources.ingestion import file_digest
from dc_locator.io import _build_metadata, read_parquet_metadata, write_parquet
from dc_locator.model.fine_selection import FINE_SELECTION_VERSION, design_constants, profile_weights, score_window, summarize_window
from dc_locator.model.metrics import clean
from dc_locator.provenance import DataMode

STAGE = 'national-fine-surface'
CELLS, PARENTS, MANIFEST = 'fine_surface_cells.parquet', 'fine_surface_parents.parquet', 'fine_surface_manifest.json'
PROVENANCE = 'feature_provenance.parquet'
MAX_PROVENANCE_WRITE_ROWS = 50_000  # resource bound; limits repeated source strings in Arrow conversion
CELL_SCHEMA = pa.schema([pa.field('grid_id', pa.string()), pa.field('parent_grid_id', pa.string()), pa.field('row', pa.int32()),
                         pa.field('col', pa.int32()), pa.field('study_area_intersection_km2', pa.float64()), pa.field('is_boundary_cell', pa.bool_()),
                         *[pa.field(column, pa.float64()) for column in FEATURE_COLUMNS],
                         *[pa.field(column, pa.string()) for column in EVIDENCE_COLUMNS]])
PROVENANCE_SCHEMA = pa.schema([pa.field(column, pa.float64() if column in {'value', 'coverage_frac'} else pa.string())
    for column in ('schema_version', 'grid_id', 'metric', 'value', 'value_text', 'unit', 'source_id', 'source_name',
        'source_url', 'source_field', 'source_version', 'data_year', 'retrieved_at', 'spatial_resolution',
        'aggregation_method', 'coverage_frac', 'status', 'confidence', 'missing_reason', 'method', 'data_mode')])


def stage_identity(regional_identity: str) -> dict:
    return {'stage': STAGE, 'regional_identity': regional_identity, 'features': FINE_FEATURE_VERSION, 'selection': FINE_SELECTION_VERSION}


def _reuse(folder: Path, identity: str, definition: str, data_mode: DataMode):
    manifest = json.loads((folder / MANIFEST).read_text(encoding='utf-8'))
    if manifest.get('stage_identity') != identity:
        raise ValueError('National fine surface belongs to another revision; choose a new output folder')
    if set(manifest.get('output_hashes', {})) != {CELLS, PARENTS, PROVENANCE}:
        raise ValueError('National fine surface checksum ledger is incomplete or unsupported')
    for name, schema, version in ((CELLS, 'NationalFineSurfaceCell', '1.1.0'),
                                  (PARENTS, 'NationalFineSurfaceParent', '1.0.0'), (PROVENANCE, 'FeatureMetadata', '1.1.0')):
        if not (folder / name).is_file():
            raise ValueError('National fine surface checksum mismatch: ' + name)
        metadata = read_parquet_metadata(folder / name)
        if any(metadata.get(key) != value for key, value in dict(schema=schema, schema_version=version,
                grid_definition_id=definition, data_mode=data_mode.value).items()):
            raise ValueError('National fine surface metadata mismatch: ' + name)
    for name, sha in manifest['output_hashes'].items():
        if not (folder / name).is_file() or file_digest(folder / name) != sha:
            raise ValueError('National fine surface checksum mismatch: ' + name)
    return pd.read_parquet(folder / PARENTS), manifest


def _study_piece(boundary_parts, tree, box):
    parts = boundary_parts[tree.query(box, predicate='intersects')]
    return shapely.union_all(shapely.intersection(parts, box)) if len(parts) else None


def _check_memory_budget():
    from dc_locator.model.enhanced import peak_working_set_bytes
    peak = peak_working_set_bytes()
    if peak is not None and peak > 4 * 1024 ** 3:
        raise MemoryError('National fine surface exceeds the project 4 GiB process budget; output remains incomplete')


def build_isolated(*, folder, identity: str, progress=None, **arguments):
    """Reuse an identical stage in-process; otherwise build it in a spawned child process.

    The child returns the national source heap to the OS on exit, so the calling regional process's lifetime
    peak working set (bounded at 4 GiB) does not carry the stage's memory into refinement.
    """
    if (Path(folder) / MANIFEST).is_file():
        return _reuse(Path(folder), identity, arguments['grid_config'].grid_definition_id(), arguments.get('data_mode', DataMode.REAL))
    if progress:
        progress(STAGE)
    import multiprocessing
    from concurrent.futures import ProcessPoolExecutor
    with ProcessPoolExecutor(max_workers=1, mp_context=multiprocessing.get_context('spawn')) as pool:
        return pool.submit(build_national_fine_surface, folder=folder, identity=identity, **arguments).result()


def build_national_fine_surface(*, parent_grid, grid_config, boundary_geometry, source_inputs, profile, performance, folder,
                                identity: str, source_checksums: dict | None = None, data_mode: DataMode = DataMode.REAL,
                                progress=None, sources=None):
    """Return ``(parent summary, manifest)``; compute and publish the stage unless an identical one exists.

    ``sources`` (a loaded ``FineSources``) is for tests; production reads ``source_inputs``.
    """
    folder = Path(folder)
    if (folder / MANIFEST).is_file():
        return _reuse(folder, identity, grid_config.grid_definition_id(), data_mode)
    if progress:
        progress(STAGE)
    started = time.perf_counter()
    folder.mkdir(parents=True, exist_ok=True)
    cell_size = float(grid_config.cell_size_m)
    widths = parent_grid.geometry.bounds.maxx - parent_grid.geometry.bounds.minx
    ratio = int(round(float(widths.iloc[0]) / cell_size))
    if ratio < 1 or not np.allclose(widths, ratio * cell_size):
        raise ValueError('Parent windows must be whole multiples of the fine cell size')
    weights = profile_weights(profile)
    constants = design_constants(performance)
    sources = sources or load_fine_sources(source_inputs, shapely.bounds(boundary_geometry))
    _check_memory_budget()
    boundary_parts = shapely.get_parts(boundary_geometry)
    boundary_tree = shapely.STRtree(boundary_parts)
    parents = parent_grid.sort_values('grid_id').reset_index(drop=True)
    partial = (parents.study_area_frac < 1 - 1e-9).to_numpy() if 'study_area_frac' in parents else parents.is_boundary_cell.to_numpy()
    summaries, written, scored, alternatives = [], 0, 0, 0
    partial_path = folder / (CELLS + '.part')
    provenance_path = folder / (PROVENANCE + '.part')
    metadata = _build_metadata('NationalFineSurfaceCell', '1.1.0', data_mode, grid_config.grid_definition_id())
    provenance_metadata = _build_metadata('FeatureMetadata', '1.1.0', data_mode, grid_config.grid_definition_id())
    with rasterio.Env(GDAL_CACHEMAX=64 * 1024 * 1024), rasterio.open(sources.land_cover) as raster, \
            pq.ParquetWriter(partial_path, CELL_SCHEMA.with_metadata(metadata), compression='zstd') as writer, \
            pq.ParquetWriter(provenance_path, PROVENANCE_SCHEMA.with_metadata(provenance_metadata), compression='zstd') as provenance_writer:
        for band, members in parents.groupby('row', sort=True):
            frames, evidence_frames = [], []
            for position, parent in members.iterrows():
                box = shapely.box(*parent.geometry.bounds)
                study = _study_piece(boundary_parts, boundary_tree, box) if partial[position] else None
                if partial[position] and (study is None or study.is_empty):
                    continue
                cells = window_cells(grid_config, int(parent.row), int(parent.col), ratio, study)
                if cells.empty:
                    continue
                features = window_features(cells, sources, raster, box, cell_size)
                evidence_frames.append(feature_provenance(cells, features, sources.source_inputs, data_mode.value))
                scores = score_window(features, profile, weights, constants)
                summaries.append(summarize_window(parent.grid_id, cells.grid_id, scores))
                scored += int(np.isfinite(scores.fine_score).sum())
                alternatives += len(scores)
                frames.append(pd.concat([cells[['grid_id', 'row', 'col', 'study_area_intersection_km2']].assign(
                    parent_grid_id=parent.grid_id, is_boundary_cell=~cells.full_cell), features], axis=1))
            if frames:
                table = pd.concat(frames, ignore_index=True).sort_values('grid_id', kind='stable')
                writer.write_table(pa.Table.from_pandas(table[CELL_SCHEMA.names], schema=CELL_SCHEMA, preserve_index=False))
                evidence = pd.concat(evidence_frames, ignore_index=True).sort_values(['grid_id', 'metric'], kind='stable')
                for start in range(0, len(evidence), MAX_PROVENANCE_WRITE_ROWS):
                    block = evidence.iloc[start:start + MAX_PROVENANCE_WRITE_ROWS]
                    provenance_writer.write_table(pa.Table.from_pandas(block[PROVENANCE_SCHEMA.names], schema=PROVENANCE_SCHEMA, preserve_index=False))
                written += len(table)
            _check_memory_budget()
            print(f'National fine surface: parent row {band} done ({written:,} cells)', flush=True)
    if not summaries:
        raise ValueError('No parent window retained a fine cell; the national fine surface is empty')
    partial_path.replace(folder / CELLS)
    provenance_path.replace(folder / PROVENANCE)
    summary = pd.concat(summaries, ignore_index=True).sort_values(['parent_grid_id', 'design_id', 'scenario_id']).reset_index(drop=True)
    write_parquet(summary, folder / PARENTS, schema_name='NationalFineSurfaceParent', schema_version='1.0.0',
                  data_mode=data_mode, grid_definition_id=grid_config.grid_definition_id())
    from dc_locator.model.enhanced import peak_working_set_bytes
    manifest = dict(schema_version='1.1.0', stage=STAGE, stage_identity=identity,
                    method_versions={'features': FINE_FEATURE_VERSION, 'selection': FINE_SELECTION_VERSION},
                    grid_definition_id=grid_config.grid_definition_id(), cell_size_m=cell_size, parent_windows=int(len(parents)),
                    partial_parent_windows=int(partial.sum()), cells=int(written), alternatives=int(alternatives),
                    scored_alternatives=int(scored), unscored_alternatives=int(alternatives - scored),
                    profile_id=profile.profile_id, weights=weights,
                    feature_metadata=feature_metadata(sources.source_inputs), provenance_records=int(written * len(FEATURE_COLUMNS)),
                    design_constants=constants.astype(object).where(constants.notna(), None).to_dict('records'),
                    source_files={name: str(path) for name, path in sources.files.items()}, source_checksums=source_checksums or {},
                    data_mode=data_mode.value, runtime_seconds=round(time.perf_counter() - started, 3),
                    observed_process_lifetime_peak_working_set_bytes=peak_working_set_bytes(),
                    interpretation='Ranks 50 km parents for 1 km refinement with the declared profile. Values are not screened, '
                                   'carry the same proxy limits as the regional features and never replace refined evidence.',
                    output_hashes={name: file_digest(folder / name) for name in (CELLS, PARENTS, PROVENANCE)})
    (folder / MANIFEST).write_text(json.dumps(clean(manifest), indent=2, sort_keys=True, allow_nan=False, default=str) + '\n',
                                   encoding='utf-8')
    return summary, manifest
