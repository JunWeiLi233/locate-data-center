"""Synthetic global sensitivity examples with native screening and fixed membership."""
import json

import geopandas as gpd
import numpy as np
import pandas as pd
import pytest
from shapely.geometry import box

from dc_locator.model.metrics import KEYS, profile_fingerprint
from dc_locator.model.physics import simulate
from dc_locator.model.regional_decision import prepare_batch, rank_compact
from dc_locator.model.screening import Requirement, screen
from dc_locator.provenance import DataMode
from dc_locator.regional_validation import validate_regional
from dc_locator.schemas import FeatureMetadata


@pytest.fixture
def regional_universe():
    from test_model_physics import model_inputs
    from test_regional_model import decision_universe

    geography, provenance, _, _, profile = decision_universe()
    duplicate_geo = geography.loc[geography.grid_id.eq('g1')].copy()
    duplicate_geo['grid_id'] = 'g4'
    duplicate_geo['col'] = 4
    duplicate_geo.geometry = [box(4000, 0, 5000, 1000)]
    duplicate_prov = provenance.loc[provenance.grid_id.eq('g1')].copy()
    duplicate_prov['grid_id'] = 'g4'
    geography = gpd.GeoDataFrame(pd.concat([geography, duplicate_geo], ignore_index=True),
                                geometry='geometry', crs=5070)
    provenance = pd.concat([provenance, duplicate_prov], ignore_index=True)
    land = 'potentially_suitable_land_frac'
    geography.loc[geography.grid_id.eq('g0'), land] = 1.
    provenance.loc[provenance.grid_id.eq('g0') & provenance.metric.eq(land), 'value'] = 1.

    # g0 has compatible observed synthetic parcel evidence; g3 fails it. The
    # other cells have UNKNOWN parcel evidence, and g2 also lacks basin stress.
    parcel = 'confirmed_developable_parcel_area_km2'
    values = {'g0': 2., 'g3': 0.}
    geography[parcel] = geography.grid_id.map(values)
    geography[parcel + '_status'] = np.where(geography[parcel].notna(), 'observed', 'unknown')
    geography[parcel + '_confidence'] = np.where(geography[parcel].notna(), 'high', 'unknown')
    geography[parcel + '_coverage_frac'] = np.where(geography[parcel].notna(), 1., 0.)
    records = []
    template = provenance.iloc[0].to_dict()
    for grid_id in geography.grid_id:
        known = grid_id in values
        record = dict(template, grid_id=grid_id, metric=parcel, value=values.get(grid_id),
                      unit='km2', source_id='synthetic_parcel_fixture', source_field='fixture area',
                      status='observed' if known else 'unknown',
                      confidence='high' if known else 'unknown', coverage_frac=1. if known else 0.,
                      missing_reason=None if known else 'source_nodata')
        records.append(FeatureMetadata.model_validate(record).model_dump(mode='json'))
    provenance = pd.concat([provenance, pd.DataFrame(records)], ignore_index=True)
    provenance.attrs['grid_definition_id'] = 'fixture'
    _, _, facility, design, scenario = model_inputs()
    scenarios = [scenario, scenario.model_copy(update={'scenario_id': 'other_static_2023'})]
    requirement = Requirement(requirement_id='parcel', metric=parcel, operator='ge', threshold=1.,
                              unit='km2', is_critical=True, basis='project_assumption',
                              rationale='Synthetic native screening example.', coverage_policy='full')
    performance = simulate(geography, provenance, facility, [design], scenarios)
    _, exploratory, _ = screen(geography, provenance, facility, [design], scenarios,
                               [requirement], mode='EXPLORATORY')
    _, strict, _ = screen(geography, provenance, facility, [design], scenarios,
                          [requirement], mode='STRICT')
    prepared = []
    for eligibility in (exploratory, strict):
        prepared.append(prepare_batch(geography, provenance, performance, eligibility, profile,
                                     profile_hash=profile_fingerprint(profile),
                                     provenance_grid_definition_id='fixture')['compact'])
    compact, strict_compact = prepared
    compact = compact.sample(frac=1, random_state=7).reset_index(drop=True)
    strict_compact = strict_compact.sample(frac=1, random_state=29).reset_index(drop=True)
    ranked = rank_compact(compact, profile, profile_hash=profile_fingerprint(profile))
    membership = ranked.loc[ranked.grid_id.isin({'g0', 'g1'}), KEYS].copy()
    membership['region_id'] = 'fixed_fixture_region'
    return compact, strict_compact, ranked, membership, profile


def settings():
    return {'top_k': 1, 'cases': [
        {'case_id': 'land_only', 'category': 'weights', 'basis': 'project_assumption',
         'rationale': 'Synthetic preference reversal with complete fixed weights.',
         'group_weights': {'energy_carbon': 0., 'water_stewardship': 0.,
                           'grid_infrastructure': 0., 'land': 1.}},
        {'case_id': 'strict', 'category': 'screening', 'mode': 'STRICT',
         'basis': 'project_assumption', 'rationale': 'Synthetic native STRICT rescreen.'},
    ]}


def run_validation(universe, output, *, strict_override=None):
    compact, strict, ranked, membership, profile = universe
    return validate_regional(compact, strict if strict_override is None else strict_override,
                             ranked, membership, {'g0', 'g4'}, profile, settings(), output,
                             'synthetic-regional-validation', DataMode.SYNTHETIC)


def test_rank_ranges_and_numeric_comparisons_align_global_keys(regional_universe, tmp_path):
    report = run_validation(regional_universe, tmp_path)
    ranges = pd.read_parquet(tmp_path / 'alternative_rank_ranges.parquet')
    assert len(ranges) == 10
    assert not ranges.duplicated(['grid_id', 'design_id', 'baseline_scenario_id']).any()
    for scenario, group in ranges.groupby('baseline_scenario_id'):
        rows = group.set_index('grid_id')
        assert rows.loc['g0', ['base_rank', 'minimum_rank', 'maximum_rank', 'rank_range']].tolist() == [3., 1., 3., 2.]
        assert rows.loc['g1', ['base_rank', 'minimum_rank', 'maximum_rank', 'rank_range']].tolist() == [1., 1., 2., 1.]
        assert rows.loc['g4', ['base_rank', 'minimum_rank', 'maximum_rank', 'rank_range']].tolist() == [2., 2., 3., 1.]
        assert rows.loc['g0', ['evaluated_cases', 'ranked_cases', 'unranked_cases']].tolist() == [3, 3, 0]
        assert rows.loc['g1', ['evaluated_cases', 'ranked_cases', 'unranked_cases']].tolist() == [3, 2, 1]
        assert rows.loc[['g2', 'g3'], ['base_rank', 'minimum_rank', 'maximum_rank', 'rank_range']].isna().all().all()
        assert rows.loc[['g2', 'g3'], 'unranked_cases'].eq(3).all()
    comparison = pd.read_parquet(tmp_path / 'validation_cases/land_only/comparison.parquet')
    for scenario, group in comparison.groupby('scenario_id'):
        rows = group.set_index('grid_id')
        assert rows.loc[['g0', 'g1', 'g4'], 'rank_change'].tolist() == [-2., 1., 1.]
        assert rows.loc[['g2', 'g3'], 'rank_change'].isna().all()
    weighted = [item for item in report['ranking_stability']['case_scenario_summaries']
                if item['case_id'] == 'land_only']
    assert len(weighted) == 2
    assert all(item['rank_correlation'] == pytest.approx(-.5) for item in weighted)
    assert all(item['top_k_overlap_count'] == 0 and item['top_k_jaccard'] == 0 for item in weighted)


def test_representative_top_k_is_global_and_ties_use_grid_id(regional_universe, tmp_path):
    run_validation(regional_universe, tmp_path)
    extract = pd.read_parquet(tmp_path / 'sensitivity_results.parquet')
    assert set(extract.grid_id) == {'g0', 'g4'}
    for scenario, group in extract.groupby('baseline_scenario_id'):
        baseline = group.loc[group.case_id.eq('baseline')].set_index('grid_id')
        # g1 and g4 tie, but the unextracted g1 wins exact global top-1.
        assert baseline.base_rank.to_dict() == {'g0': 3., 'g4': 2.}
        assert not baseline.base_top_k.any()
        assert not baseline.case_top_k.any()
        weighted = group.loc[group.case_id.eq('land_only')].set_index('grid_id')
        assert weighted.case_top_k.to_dict() == {'g0': True, 'g4': False}


def test_strict_native_flags_unknowns_and_fixed_membership_are_preserved(regional_universe, tmp_path):
    run_validation(regional_universe, tmp_path)
    compact, strict, ranked, membership, profile = regional_universe
    actual = pd.read_parquet(tmp_path / 'validation_cases/strict/ranked_cells.parquet').set_index(KEYS)
    expected = strict.set_index(KEYS).reindex(actual.index)
    flags = ['eligible', 'conditional', 'hard_fail', 'critical_unknown', 'mode']
    pd.testing.assert_frame_equal(actual[flags], expected[flags])
    assert actual.loc[actual.critical_unknown, 'mcda_rank'].isna().all()
    assert not actual.loc[actual.critical_unknown, 'eligible'].any()
    assert not actual.conditional.any()
    assert actual.loc[actual.hard_fail, 'mcda_score'].isna().all()
    missing = actual.loc[actual.index.get_level_values('grid_id') == 'g2']
    assert missing.raw_local_baseline_water_stress.isna().all()
    assert missing.local_baseline_water_stress.isna().all()
    assert missing.local_baseline_water_stress_status.eq('unknown').all()
    assert not missing.local_baseline_water_stress_source_valid.any()
    fixed = pd.read_parquet(tmp_path / 'fixed_region_summary.parquet')
    assert fixed.total_baseline_members.eq(2).all()
    assert fixed.matched_members.eq(2).all()
    strict_regions = fixed.loc[fixed.case_id.eq('strict')]
    assert len(strict_regions) == 2
    assert strict_regions.rankable_members.eq(1).all()
    assert strict_regions.unranked_members.eq(1).all()
    assert strict_regions.case_rank_min.eq(1).all() and strict_regions.case_rank_max.eq(1).all()
    assert strict_regions.case_rank_mean.isna().all()
    assert fixed.loc[fixed.case_id.eq('baseline'), 'case_rank_mean'].eq(2.).all()
    assert fixed.loc[fixed.case_id.eq('land_only'), 'case_rank_mean'].eq(1.5).all()


def test_weight_sensitivity_changes_preferences_only(regional_universe, tmp_path):
    compact, strict, ranked, membership, profile = regional_universe
    original_compact, original_strict = compact.copy(deep=True), strict.copy(deep=True)
    original_profile = profile.model_dump(mode='json')
    run_validation(regional_universe, tmp_path)
    base = pd.read_parquet(tmp_path / 'validation_cases/baseline/ranked_cells.parquet').set_index(KEYS)
    weighted = pd.read_parquet(tmp_path / 'validation_cases/land_only/ranked_cells.parquet').set_index(KEYS)
    columns = [column for column in base if column.startswith('raw_') or column in profile.metric_ids
               or column.endswith(('_status', '_confidence', '_coverage_frac', '_source_valid', '_missing_reason', '_unit'))]
    pd.testing.assert_frame_equal(base[columns], weighted[columns])
    for encoded in weighted.weights_used_json:
        weights = json.loads(encoded)
        assert set(weights) == set(profile.metric_ids)
        assert weights['suitable_land_fraction'] == 1.
        assert sum(weights.values()) == 1.
        assert all(value == 0. for key, value in weights.items() if key != 'suitable_land_fraction')
    extract = pd.read_parquet(tmp_path / 'sensitivity_results.parquet')
    weights_case = extract.loc[extract.case_id.eq('land_only')]
    assert (weights_case.base_raw_metrics_json == weights_case.case_raw_metrics_json).all()
    assert all(all(delta == 0. or delta is None for delta in json.loads(encoded).values())
               for encoded in weights_case.raw_metric_delta_json)
    pd.testing.assert_frame_equal(compact, original_compact)
    pd.testing.assert_frame_equal(strict, original_strict)
    assert profile.model_dump(mode='json') == original_profile


def test_declared_strict_case_rejects_exploratory_compact(regional_universe, tmp_path):
    with pytest.raises(ValueError, match='STRICT|strict'):
        run_validation(regional_universe, tmp_path, strict_override=regional_universe[0])


def test_stale_baseline_ranks_cannot_be_reused(regional_universe, tmp_path):
    compact, strict, ranked, membership, profile = regional_universe
    stale = ranked.copy()
    stale.loc[stale.grid_id.eq('g1'), 'mcda_rank'] = 99
    with pytest.raises(AssertionError, match='mcda_rank'):
        run_validation((compact, strict, stale, membership, profile), tmp_path)


def test_validation_identity_distinguishes_regional_runs(regional_universe, tmp_path):
    compact, strict, ranked, membership, profile = regional_universe
    first = validate_regional(compact, strict, ranked, membership, {'g0'}, profile, settings(),
                              tmp_path/'first', 'regional_refinement__1111111111111111', DataMode.SYNTHETIC)
    second = validate_regional(compact, strict, ranked, membership, {'g0'}, profile, settings(),
                               tmp_path/'second', 'regional_refinement__2222222222222222', DataMode.SYNTHETIC)
    assert first['validation_id'] != second['validation_id']


def test_global_validation_does_not_index_full_decision_copies(regional_universe,tmp_path,monkeypatch):
    original=pd.DataFrame.set_index
    rows=len(regional_universe[2])
    def bounded_index(frame,keys,*args,**kwargs):
        if list(keys)==KEYS and len(frame)==rows:
            assert len(frame.columns)<=20,'Validation copied the full global decision for key alignment'
        return original(frame,keys,*args,**kwargs)
    monkeypatch.setattr(pd.DataFrame,'set_index',bounded_index)
    run_validation(regional_universe,tmp_path)


def test_previous_scenario_frames_are_released_before_next_rank_case(regional_universe,tmp_path,monkeypatch):
    import gc
    import weakref
    import dc_locator.regional_validation as validation
    import dc_locator.model.regional_decision as decision
    frames=[];original_top=validation.stable_top_k;original_rank=decision.rank_compact
    def tracked_top(frame,*args,**kwargs):
        assert len(frame.columns)<=20,'Scenario summaries retained full decision evidence'
        frames.append(weakref.ref(frame))
        return original_top(frame,*args,**kwargs)
    def isolated_rank(*args,**kwargs):
        gc.collect()
        assert all(reference() is None for reference in frames),'Previous scenario frames survived into global ranking'
        return original_rank(*args,**kwargs)
    monkeypatch.setattr(validation,'stable_top_k',tracked_top)
    monkeypatch.setattr(decision,'rank_compact',isolated_rank)
    run_validation(regional_universe,tmp_path)
    assert len(frames)==12
    assert all(reference() is None for reference in frames)


def test_case_ranked_evidence_is_written_before_comparison_temporaries(regional_universe,tmp_path,monkeypatch):
    import dc_locator.regional_validation as validation
    original=validation.write_parquet;first={}
    def ordered_write(frame,path,*args,**kwargs):
        if path.parent.parent.name=='validation_cases':
            first.setdefault(path.parent.name,path.name)
        return original(frame,path,*args,**kwargs)
    monkeypatch.setattr(validation,'write_parquet',ordered_write)
    run_validation(regional_universe,tmp_path)
    assert first=={case:'ranked_cells.parquet' for case in ['baseline','land_only','strict']}


def test_validation_outputs_are_exact_under_shuffled_prepared_inputs(regional_universe,tmp_path):
    compact,strict,ranked,membership,profile=regional_universe
    run_validation(regional_universe,tmp_path/'first')
    shuffled=(compact.sample(frac=1,random_state=101).reset_index(drop=True),
        strict.sample(frac=1,random_state=103).reset_index(drop=True),ranked,
        membership.sample(frac=1,random_state=107).reset_index(drop=True),profile)
    run_validation(shuffled,tmp_path/'shuffled')
    first=tmp_path/'first';second=tmp_path/'shuffled'
    for path in first.rglob('*'):
        if path.is_file():
            assert path.read_bytes()==(second/path.relative_to(first)).read_bytes(),path.name
