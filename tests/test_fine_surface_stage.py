"""The national fine surface stage publishes sorted, metadata-bearing outputs, reuses itself and is deterministic."""
import json

import geopandas as gpd
import numpy as np
import pandas as pd
import pytest
import rasterio
import shapely
from rasterio.transform import from_origin

from dc_locator import fine_surface
from dc_locator.config import load_grid_config
from dc_locator.fine_surface import CELLS, MANIFEST, PARENTS, build_national_fine_surface
from dc_locator.geography.fine_features import FineSources
from dc_locator.geography.sources.ingestion import file_digest
from dc_locator.io import read_parquet_metadata
from dc_locator.model.fine_selection import select_parents_by_surface
from dc_locator.model.metrics import load_profile
from dc_locator.paths import project_root
from dc_locator.provenance import DataMode

X0, Y0 = -2_500_000.0, 3_400_000.0


@pytest.fixture
def stage(tmp_path):
    """Two synthetic 3 km parents: one interior, one half inside the study polygon (synthetic data only)."""
    rng = np.random.default_rng(7)
    raster = tmp_path / 'land.tif'
    with rasterio.open(raster, 'w', driver='GTiff', width=210, height=110, count=1, dtype='uint8', crs='EPSG:5070', nodata=250,
                       transform=from_origin(X0 + 24_000 - 85, Y0 - 21_000 + 55, 30, 30)) as output:
        output.write(rng.choice(np.array([11, 21, 41, 71, 82, 90]), size=(110, 210)).astype('uint8'), 1)
    parents = gpd.GeoDataFrame({'grid_id': ['g3000m-r0007-c0008', 'g3000m-r0007-c0009'], 'row': [7, 7], 'col': [8, 9],
                                'study_area_frac': [1.0, 0.5], 'is_boundary_cell': [False, True]},
                               geometry=[shapely.box(X0 + 24_000, Y0 - 24_000, X0 + 27_000, Y0 - 21_000),
                                         shapely.box(X0 + 27_000, Y0 - 24_000, X0 + 30_000, Y0 - 21_000)], crs=5070)
    study = shapely.box(X0 + 20_000, Y0 - 30_000, X0 + 28_500, Y0 - 15_000)
    lines = np.array([shapely.LineString([(X0 + 24_500, Y0 - 30_000), (X0 + 24_500, Y0 - 15_000)])])
    sources = FineSources(land_cover=raster, transmission=lines, basins=np.array([study]), basin_stress=np.array([1.0]),
                          egrid=np.array([study]), egrid_kg_per_mwh=np.array([300.0]), files={'land_cover': raster})
    performance = pd.DataFrame({'grid_id': ['a', 'a'], 'design_id': ['dry', 'tower'], 'scenario_id': ['current', 'current'],
                                'e_facility_mwh': [840960.0, 840960.0], 'w_site_m3': [0.0, 210240.0]})
    performance['metric_metadata_json'] = json.dumps({column: dict(status='calculated', confidence='low', unit=unit)
        for column, unit in (('e_facility_mwh', 'mwh'), ('w_site_m3', 'm3_consumed'))})
    performance['assumptions_json'] = json.dumps({'external_scenario': {'carbon_data_year': '2023'}})
    return dict(parent_grid=parents, grid_config=load_grid_config(project_root() / 'configs' / 'grid_regional.yaml'), boundary_geometry=study,
                source_inputs={}, profile=load_profile(project_root() / 'configs' / 'scoring_profile_regional.yaml'), performance=performance,
                data_mode=DataMode.SYNTHETIC, sources=sources)


def test_stage_outputs_reuse_refusal_and_determinism(stage, tmp_path, monkeypatch):
    summary, manifest = build_national_fine_surface(folder=tmp_path / 'a', identity='identity-1', **stage)
    cells = pd.read_parquet(tmp_path / 'a' / CELLS)
    assert len(cells) == 9 + 6 and cells.grid_id.is_monotonic_increasing and cells.grid_id.is_unique
    assert cells.loc[cells.col == 28, 'is_boundary_cell'].all() and not cells.loc[cells.col < 28, 'is_boundary_cell'].any()
    assert read_parquet_metadata(tmp_path / 'a' / CELLS)['schema'] == 'NationalFineSurfaceCell'
    assert read_parquet_metadata(tmp_path / 'a' / CELLS)['schema_version'] == '1.1.0'
    assert cells.transmission_distance_km_status.eq('proxy').all()
    provenance = pd.read_parquet(tmp_path / 'a' / 'feature_provenance.parquet')
    assert len(provenance) == len(cells) * 7
    assert not provenance.duplicated(['grid_id', 'metric']).any()
    assert provenance.loc[provenance.metric.eq('transmission_distance_km'), 'status'].eq('proxy').all()
    from dc_locator.schemas import FeatureMetadata
    from dc_locator.model.metrics import clean
    for row in provenance.to_dict('records'):
        FeatureMetadata.model_validate(clean(row))
    assert read_parquet_metadata(tmp_path / 'a' / CELLS)['data_mode'] == 'synthetic'
    assert read_parquet_metadata(tmp_path / 'a' / PARENTS)['schema'] == 'NationalFineSurfaceParent'
    assert len(summary) == 4 and summary.parent_grid_id.is_monotonic_increasing
    assert manifest['cells'] == 15 and manifest['alternatives'] == 30 and manifest['scored_alternatives'] + manifest['unscored_alternatives'] == 30
    assert manifest['output_hashes'] == {name: file_digest(tmp_path / 'a' / name) for name in (CELLS, PARENTS, 'feature_provenance.parquet')}
    # Reuse: a completed identical stage is never recomputed.
    monkeypatch.setattr(fine_surface, 'window_features', lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError('recomputed')))
    reused, _ = build_national_fine_surface(folder=tmp_path / 'a', identity='identity-1', **stage)
    pd.testing.assert_frame_equal(reused, summary)
    with pytest.raises(ValueError, match='another revision'):
        build_national_fine_surface(folder=tmp_path / 'a', identity='identity-2', **stage)
    ledger = json.loads((tmp_path / 'a' / MANIFEST).read_text(encoding='utf-8'))
    del ledger['output_hashes'][CELLS]
    (tmp_path / 'a' / MANIFEST).write_text(json.dumps(ledger), encoding='utf-8')
    with pytest.raises(ValueError, match='checksum ledger'):
        build_national_fine_surface(folder=tmp_path / 'a', identity='identity-1', **stage)
    monkeypatch.undo()
    _, again = build_national_fine_surface(folder=tmp_path / 'b', identity='identity-1', **stage)
    assert again['output_hashes'] == manifest['output_hashes']
    selected = select_parents_by_surface(stage['parent_grid'], summary, limit=1)
    assert len(selected) == 1 and selected.fine_selection_rank.tolist() == [1]
    assert json.loads((tmp_path / 'a' / MANIFEST).read_text(encoding='utf-8'))['data_mode'] == 'synthetic'


def test_surface_refuses_publication_above_the_memory_budget(stage, tmp_path, monkeypatch):
    from dc_locator.model import enhanced
    monkeypatch.setattr(enhanced, 'peak_working_set_bytes', lambda: 4 * 1024 ** 3 + 1)
    with pytest.raises(MemoryError, match='4 GiB'):
        build_national_fine_surface(folder=tmp_path / 'over-budget', identity='resource-test', **stage)
    assert not (tmp_path / 'over-budget' / MANIFEST).exists()


def test_long_evidence_is_written_in_memory_bounded_chunks(stage, tmp_path, monkeypatch):
    import pyarrow.parquet as pq
    monkeypatch.setattr(fine_surface, 'MAX_PROVENANCE_WRITE_ROWS', 10, raising=False)
    build_national_fine_surface(folder=tmp_path / 'bounded', identity='write-budget', **stage)
    metadata = pq.read_metadata(tmp_path / 'bounded' / 'feature_provenance.parquet')
    assert metadata.num_rows == 105
    assert all(metadata.row_group(i).num_rows <= 10 for i in range(metadata.num_row_groups))


def test_isolated_build_matches_in_process_outputs_and_reuses(stage, tmp_path):
    _, local = build_national_fine_surface(folder=tmp_path / 'local', identity='identity-1', **stage)
    calls = []
    summary, isolated = fine_surface.build_isolated(folder=tmp_path / 'child', identity='identity-1', progress=calls.append, **stage)
    assert isolated['output_hashes'] == local['output_hashes'] and calls == [fine_surface.STAGE]
    reused, again = fine_surface.build_isolated(folder=tmp_path / 'child', identity='identity-1', progress=calls.append, **stage)
    assert again['output_hashes'] == isolated['output_hashes'] and calls == [fine_surface.STAGE]  # reuse never spawns or reports again
    pd.testing.assert_frame_equal(reused, summary)
    text = (tmp_path / 'child' / MANIFEST).read_text(encoding='utf-8')
    assert text.startswith('{\n  ') and 'NaN' not in text  # indented, strict JSON


def test_a_surface_without_any_fine_cell_is_refused(stage, tmp_path):
    outside = {**stage, 'parent_grid': stage['parent_grid'].assign(study_area_frac=0.5),
               'boundary_geometry': shapely.box(X0 + 100_000, Y0 - 101_000, X0 + 101_000, Y0 - 100_000)}
    with pytest.raises(ValueError, match='national fine surface is empty'):
        build_national_fine_surface(folder=tmp_path / 'empty', identity='empty-test', **outside)
    assert not (tmp_path / 'empty' / MANIFEST).exists() and not (tmp_path / 'empty' / CELLS).exists()
