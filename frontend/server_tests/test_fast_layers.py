"""Regional layer reads preserve exact evidence without repeated cell scans."""
import inspect

import pandas as pd
import pytest

from frontend.server.serialization import ApiError, ArtifactReader, clean, screening_status
from test_regional_bridge import regional


def test_layer_cells_use_indexed_evidence_and_keep_native_status(regional, tmp_path, monkeypatch):
    reader = ArtifactReader(tmp_path/'responses')
    original = pd.Series.__eq__
    scans = []
    def recorded(series, value):
        if series.name == 'grid_id' and inspect.currentframe().f_back.f_code.co_name == 'layer':
            scans.append(len(series))
        return original(series, value)
    monkeypatch.setattr(pd.Series, '__eq__', recorded)
    result = reader.layer(regional, 'grid', sublayer='screening@parent_fixture')
    native = pd.read_parquet(regional/'ranked_cells.parquet')
    checks = pd.read_parquet(regional/'parts/parent_fixture/screening_results.parquet')
    assert len(result['data']['features']) == 42
    for feature in result['data']['features']:
        grid_id = feature['id']
        alternatives = clean(native[native.grid_id.eq(grid_id)].to_dict('records'))
        statuses = [screening_status(row) for row in alternatives]
        expected = next((status for status in ('FAIL','UNKNOWN','CONDITIONAL','PASS') if status in statuses),'UNKNOWN')
        assert feature['properties']['screening_status'] == feature['properties']['value'] == expected
        rows = clean(checks[checks.grid_id.eq(grid_id)].to_dict('records'))
        assert feature['properties']['reasons'] == sorted(set(
            f"{row['requirement']}: {row.get('reason') or row.get('missing_reason') or row['outcome']}"
            for row in rows if row['outcome']=='FAIL'))
        assert feature['properties']['unknowns'] == sorted(set(
            f"{row['requirement']}: {row.get('missing_reason') or 'Unknown'}"
            for row in rows if row['outcome']=='UNKNOWN'))
    assert not scans, 'Each regional cell must use indexed alternative and screening evidence'


def test_grid_layer_skips_unused_provenance_but_still_requires_it(regional, tmp_path, monkeypatch):
    reader = ArtifactReader(tmp_path/'responses')
    original = reader.table
    def recorded(folder, name, **kwargs):
        assert name != 'feature_provenance', 'Categorical screening does not display geographic metric provenance'
        return original(folder, name, **kwargs)
    monkeypatch.setattr(reader, 'table', recorded)
    assert reader.layer(regional,'grid',sublayer='parent_fixture')['data']['features']
    (regional/'parts/parent_fixture/feature_provenance.parquet').unlink()
    with pytest.raises(ApiError, match='feature_provenance.parquet'):
        reader.layer(regional,'grid',sublayer='parent_fixture')


def test_indicator_reads_only_its_metric_and_preserves_unknown(regional, tmp_path, monkeypatch):
    reader = ArtifactReader(tmp_path/'responses')
    original = reader.table
    reads = []
    def recorded(folder, name, **kwargs):
        frame = original(folder, name, **kwargs)
        if name == 'feature_provenance':
            reads.append((kwargs.get('metric_ids'),set(frame.metric)))
        return frame
    monkeypatch.setattr(reader, 'table', recorded)
    result = reader.layer(regional,'climate',sublayer='flood@parent_fixture')
    assert reads == [(['flood_overlap_frac'], {'flood_overlap_frac'})]
    assert len(result['data']['features']) == 42
    for feature in result['data']['features']:
        properties = feature['properties']
        if properties['status'] == 'unknown':
            assert properties['value'] is None and properties['missing_reason']


def test_metric_projection_has_distinct_content_checked_cache_keys(regional, tmp_path):
    reader = ArtifactReader(tmp_path/'responses')
    part = regional/'parts/parent_fixture'
    flood = reader.table(part, 'feature_provenance', metric_ids=['flood_overlap_frac'])
    land = reader.table(part, 'feature_provenance', metric_ids=['potentially_suitable_land_frac'])
    assert set(flood.metric) == {'flood_overlap_frac'}
    assert set(land.metric) == {'potentially_suitable_land_frac'}
    assert reader.table(part,'feature_provenance',metric_ids=[]).empty
    path=part/'feature_provenance.parquet'
    original=pd.read_parquet(path)
    original.loc[original.metric.eq('flood_overlap_frac'),'missing_reason']='transport cache invalidation fixture'
    original.to_parquet(path,index=False)
    refreshed=reader.table(part,'feature_provenance',metric_ids=['flood_overlap_frac'])
    assert set(refreshed.missing_reason)=={'transport cache invalidation fixture'}


@pytest.mark.parametrize('frame', [pd.DataFrame(), pd.DataFrame({'metric': pd.Series(dtype=object)})])
def test_metric_projection_preserves_legacy_empty_tables(tmp_path, frame):
    frame.to_parquet(tmp_path/'feature_provenance.parquet', index=False)
    reader = ArtifactReader(tmp_path/'responses')
    projected = reader.table(tmp_path, 'feature_provenance', metric_ids=['flood_overlap_frac'])
    pd.testing.assert_frame_equal(projected, pd.read_parquet(tmp_path/'feature_provenance.parquet'))
