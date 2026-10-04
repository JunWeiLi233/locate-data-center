"""Quarantined, hand-calculated county geography/source contracts."""
import json

import geopandas as gpd
import numpy as np
import pandas as pd
import pytest
from shapely.geometry import box

from dc_locator.geography.sources.saipe import parse_saipe, add_percentiles
from dc_locator.geography.socioeconomic import (candidate_county_crosswalk, load_config,
    _verified_source, _cache_manifest, ensure_socioeconomic_geography,
    socioeconomic_available, ensure_county_geography)


def record(state='01', county='001', *, rate='20.0', count='100', income='40000',
           rate_lo='18.0', rate_hi='22.0', income_lo='39000', income_hi='41000',
           count_lo='90',count_hi='110',year=2024):
    line = [' '] * 264
    for start, end, value in [(1, 2, state), (4, 6, county), (8, 15, count),
        (17, 24, count_lo), (26, 33, count_hi), (35, 38, rate), (40, 43, rate_lo),
        (45, 48, rate_hi), (134, 139, income), (141, 146, income_lo),
        (148, 153, income_hi), (194, 238, 'Test County'),
        (243, 264, f'est{year % 100:02d}all.txt 07JAN2026')]:
        line[start-1:end] = list(str(value).rjust(end-start+1))
    return ''.join(line)


def test_saipe_source_year_geoid_intervals_and_moe():
    result = parse_saipe(record() + '\n' + record('02', '001'), year=2024)
    assert result.county_geoid.tolist() == ['01001']
    row = result.iloc[0]
    assert row.poverty_rate == 20.0
    assert row.poverty_rate_moe == 2.0
    assert row.median_household_income_moe == 1000.0
    assert row.poverty_rate_status == 'observed'
    assert row.poverty_rate_moe_status == 'calculated'
    assert row.poverty_rate_unit == 'percent'
    assert row.poverty_rate_moe_unit == 'percentage_points'
    assert row.socioeconomic_year == 2024
    assert row.poverty_rate_moe_method == '(upper_90 - lower_90) / 2; rounded source interval half-width'
    with pytest.raises(ValueError, match='year'):
        parse_saipe(record(year=2023), year=2024)
    with pytest.raises(ValueError, match='FIPS'):
        parse_saipe(record(county='A01'), year=2024)


def test_suppression_is_unknown_not_zero_and_missing_intervals_stay_unknown():
    result = parse_saipe(record(rate='.', income='-1', rate_lo='.', rate_hi='.'), year=2024)
    row = result.iloc[0]
    assert pd.isna(row.poverty_rate) and pd.isna(row.poverty_rate_moe)
    assert pd.isna(row.median_household_income)
    assert row.poverty_rate_status == 'unknown'
    assert row.poverty_rate_confidence == 'unknown'
    assert row.poverty_rate_missing_reason == 'source_suppressed_or_missing'
    assert pd.isna(row.net_local_fiscal_revenue)
    assert row.net_local_fiscal_revenue_status == 'unknown'
    assert row.net_local_fiscal_revenue_missing_reason == 'future_fiscal_inputs_not_acquired'
    with pytest.raises(ValueError, match='numeric'):
        parse_saipe(record(rate='oops'), year=2024)


def test_percentiles_all_valid_conus_ties_and_nulls():
    data = pd.DataFrame({'county_geoid':['01001','01003','01005','01007'],
                         'poverty_rate':[5.,10.,10.,np.nan],
                         'median_household_income':[10.,20.,30.,np.nan]})
    result = add_percentiles(data)
    assert result.poverty_percentile.tolist()[:3] == [0.,75.,75.]
    assert result.income_percentile.tolist()[:3] == [0.,50.,100.]
    assert result.low_income_percentile.tolist()[:3] == [100.,50.,0.]
    assert pd.isna(result.loc[3,'poverty_percentile'])
    pd.testing.assert_frame_equal(add_percentiles(data.sample(frac=1,random_state=17)).sort_values('county_geoid').reset_index(drop=True), result)


def counties():
    return gpd.GeoDataFrame({'county_geoid':['01001','01003','01001'],
        'county_name':['A','B','A'], 'state_fips':['01']*3,'county_fips':['001','003','001'],
        'poverty_rate':[10.,20.,10.]},
        geometry=[box(0,0,500,1000),box(500,0,1000,1000),box(0,0,500,1000)],crs=5070)


def test_crosswalk_split_and_duplicate_fragments_all_positive_pairs():
    cells = gpd.GeoDataFrame({'grid_id':['g1000m-r0000-c0000']},geometry=[box(0,0,1000,1000)],crs=5070)
    crosswalk, coverage = candidate_county_crosswalk(cells,counties(),chunk_size=1)
    assert crosswalk.county_geoid.tolist() == ['01001','01003']
    assert crosswalk.candidate_id.tolist() == cells.grid_id.tolist()*2
    assert crosswalk.overlap_fraction.tolist() == [0.5,0.5]
    assert crosswalk.intersection_area_km2.tolist() == [0.5,0.5]
    assert crosswalk.candidate_area_km2.tolist() == [1.,1.]
    assert coverage.iloc[0].county_coverage_fraction == 1.


def test_partial_and_no_coverage_no_renormalization_or_missing_zero():
    cells = gpd.GeoDataFrame({'grid_id':['g1000m-r0000-c0000','g1000m-r0000-c0001']},
        geometry=[box(-500,0,500,1000),box(2000,0,3000,1000)],crs=5070)
    crosswalk,coverage = candidate_county_crosswalk(cells,counties())
    assert len(crosswalk) == 1 and crosswalk.iloc[0].overlap_fraction == .5
    assert coverage.county_coverage_fraction.tolist() == [.5,0.]
    assert coverage.uncovered_fraction.tolist() == [.5,1.]
    assert coverage.coverage_reason.tolist() == ['cartographic_boundary_uncovered_area','no_positive_county_overlap']
    with pytest.raises(ValueError,match='5070'):
        candidate_county_crosswalk(cells.to_crs(4326), counties())


def test_configuration_records_two_geometry_vintages_and_independent_saipe_year():
    config = load_config('.', 'configs/socioeconomic.yaml')
    assert config['saipe_year'] == 2024
    assert config['boundary_year'] == 2025
    assert set(config['county_boundaries']) == {2023,2025}
    assert config['boundary_type'] == 'cartographic_500k'


def test_duplicate_saipe_county_or_impossible_interval_rejected():
    with pytest.raises(ValueError,match='duplicate'):
        parse_saipe(record()+'\n'+record(),year=2024)
    with pytest.raises(ValueError,match='interval'):
        parse_saipe(record(rate_lo='22.0',rate_hi='18.0'),year=2024)


def test_no_network_capability_and_grid_source_failure_guards(tmp_path):
    config=load_config('.')
    config_path=tmp_path/'configs/socioeconomic.yaml'
    config_path.parent.mkdir()
    import yaml
    config_path.write_text(yaml.safe_dump(config))
    assert socioeconomic_available(tmp_path) is False
    with pytest.raises(ValueError,match='owned saved real'):
        ensure_socioeconomic_geography(tmp_path,tmp_path/'outside.parquet',config=config)
    with pytest.raises(FileNotFoundError):
        ensure_socioeconomic_geography(tmp_path,tmp_path/'runs/new/us_grid_dataset.parquet',config=config)


def test_source_manifest_failure_and_cached_output_tamper(tmp_path):
    from dc_locator.geography.sources.ingestion import file_digest
    source=tmp_path/'data/raw/source/est24all.txt'
    source.parent.mkdir(parents=True)
    source.write_text(record())
    url='https://www2.census.gov/official.txt'
    manifest=source.parent/'download_log.json'
    entry={'path':str(source),'url':url,'bytes':source.stat().st_size,'sha256':file_digest(source)}
    manifest.write_text(json.dumps([entry]))
    assert _verified_source(source,tmp_path,url)['sha256']==entry['sha256']
    with pytest.raises(ValueError,match='manifest'):
        _verified_source(source,tmp_path,url+'wrong')
    source.write_text(record(rate='21.0'))
    with pytest.raises(ValueError,match='checksum'):
        _verified_source(source,tmp_path,url)
    output=tmp_path/'output.parquet'; output.write_bytes(b'owned-output')
    cache=tmp_path/'manifest.json'; binding={'saipe_year':2024,'boundary_year':2025}
    cache.write_text(json.dumps({'binding':binding,'output_sha256':{output.name:file_digest(output)}}))
    assert _cache_manifest(cache,binding,[output],True)['binding']==binding
    output.write_bytes(b'changed')
    with pytest.raises(ValueError,match='cache binding/output'):
        _cache_manifest(cache,binding,[output],False)


def test_invalid_positive_area_geometry_rejected_before_overlay():
    from shapely.geometry import Polygon
    cells=gpd.GeoDataFrame({'grid_id':['g1000m-r0000-c0000']},
        geometry=[Polygon([(0,0),(1000,1000),(0,1000),(500,0),(0,0)])],crs=5070)
    assert cells.area.iloc[0]>0
    with pytest.raises(ValueError,match='valid'):
        candidate_county_crosswalk(cells,counties())


def test_source_year_geometry_label_guards_and_acquire_false(monkeypatch,tmp_path):
    config=load_config('.')
    from dc_locator.geography.sources import saipe
    monkeypatch.setattr(saipe,'acquire_saipe',lambda *a,**kw: pytest.fail('acquire=False performed network acquisition'))
    with pytest.raises(FileNotFoundError):
        ensure_county_geography(tmp_path,config=config,acquire=False)
    with pytest.raises(ValueError,match='Cached-only'):
        ensure_county_geography(tmp_path,config=config,cached_only=True,acquire=True)
    with pytest.raises(ValueError,match='boundary year'):
        ensure_county_geography(tmp_path,config=config,boundary_year=2024)
    config=dict(config,saipe_year=2023)
    with pytest.raises(ValueError,match='SAIPE year 2024'):
        ensure_county_geography(tmp_path,config=config)


def test_known_zero_and_single_valid_percentile_have_distinct_unknown_contract():
    result=parse_saipe(record(rate='0.0',count='0',count_lo='0',count_hi='0',rate_lo='0.0',rate_hi='0.0'),year=2024)
    row=result.iloc[0]
    assert row.poverty_rate==0 and row.poverty_rate_status=='observed'
    assert row.poverty_percentile==50 and row.poverty_percentile_status=='calculated'


def test_disabled_context_reports_unavailable_and_refuses_build(tmp_path):
    config=load_config('.')
    assert config['socioeconomic_enabled'] is True
    config=dict(config,socioeconomic_enabled=False)
    from dc_locator.geography.socioeconomic import source_availability
    assert source_availability(tmp_path,config=config)['available'] is False
    with pytest.raises(ValueError,match='disabled'):
        ensure_county_geography(tmp_path,config=config)


def test_metric_source_fields_and_missing_interval_reason():
    frame=parse_saipe(record(rate_lo='.',rate_hi='.'),year=2024)
    row=frame.iloc[0]
    assert row.poverty_rate_source_field=='positions 35-38; SAEPOVRTALL_PT equivalent'
    assert row.poverty_rate_moe_source_field=='positions 40-43 and 45-48; SAEPOVRTALL_LB90/UB90 equivalents'
    assert row.poverty_rate_moe_missing_reason=='source_interval_missing'


def test_manifest_binding_roundtrips_integer_config_year_keys(tmp_path):
    from dc_locator.geography.socioeconomic import _save_manifest
    output=tmp_path/'table.parquet'; output.write_bytes(b'cache')
    manifest=tmp_path/'manifest.json'
    binding={'config':{'county_boundaries':{2023:'a',2025:'b'}}}
    _save_manifest(manifest,binding,[output],{})
    assert _cache_manifest(manifest,binding,[output],True) is not None
