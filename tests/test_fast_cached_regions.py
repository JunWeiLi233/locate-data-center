"""Bounded native oracles for the separately bound cached-cohort runner."""
import importlib.util
import json
import os
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
BASELINE = ROOT / 'runs/cleanview_regional_v2'


def runner():
    spec = importlib.util.find_spec('dc_locator_fast')
    assert spec is not None, 'The separately bound production cached-cohort runner is missing'
    import dc_locator_fast
    return dc_locator_fast


def native_inputs(*, full=False):
    if not (BASELINE / 'run_metadata.json').exists():
        pytest.skip('Local accepted native cohort is not installed')
    from dc_locator.io import read_geoparquet
    from dc_locator.model.cooling import CoolingDesign, PhysicalScenario
    from dc_locator.model.metrics import ScoringProfile
    from dc_locator.schemas import FacilityConfig
    snapshot = json.loads((BASELINE / 'config_snapshot.json').read_text())
    documents = {Path(k).name: yaml.safe_load(v) for k, v in snapshot['files'].items()}
    facility = FacilityConfig.model_validate(documents['facility.yaml']['facilities'][0])
    designs = [CoolingDesign.model_validate(d) for d in documents['cooling_designs.yaml']['cooling_designs']]
    scenarios = [PhysicalScenario.model_validate(s) for s in documents['phase3_physical_scenarios.yaml']['scenarios']]
    profile = ScoringProfile.model_validate(json.loads((BASELINE / 'profile_snapshot.json').read_text())['profile'])
    catalog = json.loads((BASELINE / 'regional_catalog.json').read_text())
    part = BASELINE / catalog['parts'][0]['path']
    geo = read_geoparquet(part / 'us_grid_dataset.parquet')
    # Native known and unknown cells, selected independently of current winners.
    ids = sorted(geo.grid_id) if full else sorted(geo.grid_id)[::97]
    geo = geo.loc[geo.grid_id.isin(ids)].reset_index(drop=True)
    provenance = pd.read_parquet(part / 'feature_provenance.parquet')
    provenance = provenance.loc[provenance.grid_id.isin(ids)].reset_index(drop=True)
    return part, geo, provenance, facility, designs, scenarios, profile


def test_external_runner_does_not_enter_live_pipeline_binding_domain():
    module = runner()
    assert Path(module.__file__).resolve().parent == ROOT / 'src'
    assert callable(module.evaluate_cached_regions)


@pytest.mark.parametrize('mode', ['EXPLORATORY', 'STRICT'])
@pytest.mark.parametrize('load,full', [(0., False), (.47, True)])
def test_changed_native_facility_compact_exactly_matches_fresh_model(mode, load, full):
    module = runner()
    from dc_locator.model.physics import simulate
    from dc_locator.model.screening import Requirement, screen
    from dc_locator.model.regional_decision import prepare_batch, rank_compact
    from dc_locator.model.metrics import KEYS, profile_fingerprint
    part, geo, provenance, facility, designs, scenarios, profile = native_inputs(full=full)
    facility = type(facility).model_validate({**facility.model_dump(mode='json'),
        'facility_id': 'changed_native_fixture', 'peak_it_power_mw': 137.,
        'average_it_load_factor': load, 'target_opening_year': 2041, 'screening_mode': mode})
    constraints = yaml.safe_load((ROOT / 'configs/constraints.yaml').read_text())
    requirements = [Requirement.model_validate(r) for r in constraints['requirements']]
    _, eligibility, _ = screen(geo, provenance, facility, designs, scenarios, requirements,
        mode=mode, land_search_scope='multi_cell_region')
    performance = simulate(geo, provenance, facility, designs, scenarios)
    fingerprint = profile_fingerprint(profile)
    expected = prepare_batch(geo, provenance, performance, eligibility, profile,
        profile_hash=fingerprint, provenance_grid_definition_id=geo.grid_definition_id.iloc[0])['compact']
    filename = 'strict_compact.parquet' if mode == 'STRICT' else 'compact.parquet'
    cached = pd.read_parquet(part / filename)
    cached = cached.loc[cached.grid_id.isin(geo.grid_id)].reset_index(drop=True)
    carbon = provenance.loc[provenance.metric.eq('grid_carbon_intensity_kg_per_mwh')].reset_index(drop=True)
    actual = module.prepare_cached_compact(cached, carbon, facility, designs, scenarios, profile)
    expected = rank_compact(expected, profile, profile_hash=fingerprint)
    actual = rank_compact(actual, profile, profile_hash=fingerprint)
    pd.testing.assert_frame_equal(actual[expected.columns].sort_values(KEYS).reset_index(drop=True),
        expected.sort_values(KEYS).reset_index(drop=True), check_exact=True)
    assert actual.facility_id.eq(facility.facility_id).all()
    assert actual.critical_unknown.any()
    assert mode != 'STRICT' or actual.mcda_score.isna().all()


def test_cache_hash_rejects_same_length_same_timestamp_corruption(tmp_path):
    module = runner()
    artifact = tmp_path / 'static.bin'
    artifact.write_bytes(b'original')
    manifest = {'output_hashes': {'static.bin': module.file_digest(artifact)}}
    module.verify_cache(tmp_path, manifest)
    timestamp = artifact.stat().st_mtime_ns
    artifact.write_bytes(b'changed!')
    os.utime(artifact, ns=(timestamp, timestamp))
    with pytest.raises(ValueError, match='checksum'):
        module.verify_cache(tmp_path, manifest)


def test_unknown_carbon_stays_unknown_even_at_zero_load():
    module = runner()
    part, geo, provenance, facility, designs, scenarios, profile = native_inputs()
    facility = facility.model_copy(update={'average_it_load_factor': 0.})
    cached = pd.read_parquet(part / 'compact.parquet').iloc[:2].copy()
    carbon = provenance.loc[provenance.metric.eq('grid_carbon_intensity_kg_per_mwh')].iloc[:1].copy()
    carbon['grid_id'] = cached.grid_id.iloc[0]
    carbon['value'] = np.nan; carbon['status'] = 'unknown'; carbon['confidence'] = 'unknown'
    carbon['missing_reason'] = 'source_nodata'
    # Prepared evidence cannot assert source validity for this unknown factor.
    cached['annual_electricity_co2e_source_valid'] = False
    cached['annual_electricity_co2e_status'] = 'unknown'
    actual = module.prepare_cached_compact(cached, carbon, facility, designs, scenarios, profile)
    assert actual.c_electricity_tonnes.isna().all()
    assert actual.annual_electricity_co2e.isna().all()
    assert actual.w_site_m3.eq(0.).all()


def test_ui_request_changes_physics_design_and_preferences_with_frozen_land():
    module = runner()
    _, _, _, baseline, _, _, profile = native_inputs()
    body = dict(peak_it_power_mw=137., average_load_percent=47., target_opening_year=2041,
        lifetime_years=31, cooling='air_dry_assumed', weighting='user', screening_mode='EXPLORATORY',
        group_weights={g['group_id']: i+1 for i, g in enumerate(profile.groups)}, ahp_matrix=None)
    facility, active = module.parse_request(body, baseline, profile)
    assert facility.peak_it_power_mw == 137. and facility.average_it_load_factor == .47
    assert facility.target_opening_year == 2041 and facility.operating_lifetime_years == 31
    assert facility.cooling_designs == ['air_dry_assumed']
    assert facility.minimum_land_area_km2 == baseline.minimum_land_area_km2
    assert active.user_weights == body['group_weights'] and active.weighting_method == 'user'
    assert active.metrics == profile.metrics


def test_changed_land_threshold_and_invalid_exposed_values_are_rejected():
    module = runner()
    _, _, _, baseline, _, _, profile = native_inputs()
    with pytest.raises(ValueError, match='land threshold'):
        module.parse_request({**baseline.model_dump(mode='json'), 'minimum_land_area_km2': .8}, baseline, profile)
    for field, value in [('peak_it_power_mw', True), ('average_it_load_factor', '0.5'),
                         ('target_opening_year', 2030.5), ('hours_in_modeled_year', None)]:
        with pytest.raises(ValueError):
            module.parse_request({**baseline.model_dump(mode='json'), field: value}, baseline, profile)


def test_preparation_and_identity_interfaces_are_explicit_and_status_never_builds():
    module = runner()
    assert callable(module.prepare_cached_cohort)
    assert callable(module.stable_request_identity)
    result = module.cached_cohort_status(ROOT, BASELINE)
    assert isinstance(result, dict) and 'ready' in result


def test_evaluator_preserves_existing_baseline_evidence():
    module = runner()
    with pytest.raises(ValueError, match='new owned output'):
        module.evaluate_cached_regions(ROOT, BASELINE, {}, BASELINE)


def test_fast_clusters_and_land_support_match_whole_native_oracle():
    module = runner()
    from dc_locator.model.physics import simulate
    from dc_locator.model.screening import Requirement, screen
    from dc_locator.model.regional_decision import prepare_batch, rank_compact
    from dc_locator.model.regions import cluster_regions, screen_region_land_support
    from dc_locator.model.metrics import profile_fingerprint
    part, geo, provenance, facility, designs, scenarios, profile = native_inputs()
    facility = type(facility).model_validate({**facility.model_dump(mode='json'),
        'peak_it_power_mw': 131., 'average_it_load_factor': .79, 'screening_mode': 'EXPLORATORY'})
    constraints = yaml.safe_load((ROOT / 'configs/constraints.yaml').read_text())
    requirements = [Requirement.model_validate(r) for r in constraints['requirements']]
    _, eligible, _ = screen(geo, provenance, facility, designs, scenarios, requirements,
        mode='EXPLORATORY', land_search_scope='multi_cell_region')
    performance = simulate(geo, provenance, facility, designs, scenarios)
    fingerprint = profile_fingerprint(profile)
    prepared = prepare_batch(geo, provenance, performance, eligible, profile,
        profile_hash=fingerprint, provenance_grid_definition_id=geo.grid_definition_id.iloc[0])['compact']
    expected_rank = rank_compact(prepared, profile, profile_hash=fingerprint)
    expected_regions, expected_members = cluster_regions(geo, expected_rank, profile.region_selection,
        [m.column for m in profile.metrics], profile.profile_id, fingerprint)
    expected_regions, expected_members, expected_land = screen_region_land_support(
        expected_regions, expected_members, facility.minimum_land_area_km2)
    cached = pd.read_parquet(part / 'compact.parquet')
    cached = cached.loc[cached.grid_id.isin(geo.grid_id)].reset_index(drop=True)
    carbon = provenance.loc[provenance.metric.eq('grid_carbon_intensity_kg_per_mwh')].reset_index(drop=True)
    ranked, regions, members, land = module.evaluate_prepared_cohort(
        cached, carbon, geo, facility, designs, scenarios, profile)
    pd.testing.assert_frame_equal(ranked[expected_rank.columns], expected_rank, check_exact=True)
    pd.testing.assert_frame_equal(regions.drop(columns='representative_json'),
        expected_regions.drop(columns='representative_json'), check_exact=True)
    pd.testing.assert_frame_equal(members, expected_members, check_exact=True)
    pd.testing.assert_frame_equal(land, expected_land, check_exact=True)


def test_fresh_representative_invariant_rejects_metric_or_screen_disagreement():
    module = runner()
    from dc_locator.model.metrics import load_profile
    profile = load_profile(ROOT / 'configs/scoring_profile_regional.yaml')
    frame = pd.DataFrame({'grid_id': ['synthetic_a', 'synthetic_b'], 'design_id': ['d', 'd'],
        'scenario_id': ['s', 's'], 'mcda_score': [20., np.nan], 'eligible': [True, False],
        'conditional': [True, False], 'hard_fail': [False, True], 'critical_unknown': [True, True]})
    for metric in profile.metrics:
        frame[metric.metric_id] = [1., np.nan]
        frame['raw_' + metric.metric_id] = [2., np.nan]
    module.validate_representative_equivalence(frame, frame.sample(frac=1, random_state=2), profile)
    for column, value in [('raw_' + profile.metric_ids[0], 2.1), ('eligible', False)]:
        changed = frame.copy(); changed.loc[0, column] = value
        with pytest.raises(ValueError, match='Fresh representative'):
            module.validate_representative_equivalence(frame, changed, profile)


def test_representative_hydration_has_portable_json_and_fresh_facility():
    module = runner()
    part, geo, provenance, facility, designs, scenarios, profile = native_inputs()
    facility = type(facility).model_validate({**facility.model_dump(mode='json'),
        'peak_it_power_mw': 130., 'average_it_load_factor': .77,
        'target_opening_year': 2031, 'screening_mode': 'EXPLORATORY'})
    compact = pd.read_parquet(part / 'compact.parquet')
    compact = compact.loc[compact.grid_id.isin(geo.grid_id)].reset_index(drop=True)
    carbon = provenance.loc[provenance.metric.eq('grid_carbon_intensity_kg_per_mwh')]
    ranked, regions, _, _ = module.evaluate_prepared_cohort(compact, carbon, geo, facility, designs, scenarios, profile)
    context = module._baseline_context(ROOT, BASELINE)
    evidence, checks, repgeo, repprov, lineage = module._representatives(context, regions.iloc[:1].copy(), ranked, facility, profile)
    assert len(evidence) and len(checks) and len(repgeo) and len(repprov) and lineage
    assert evidence.target_opening_year.eq(2031).all()
    assert evidence.e_it_mwh.eq(130. * .77 * 8760).all()
    assert evidence.w_electricity_m3.isna().all()


def test_geographic_labels_are_exact_complete_and_never_imputed():
    module = runner()
    geometry = pd.DataFrame({'grid_id': ['synthetic_a', 'synthetic_b']})
    labels = pd.DataFrame({'grid_id': ['synthetic_b', 'synthetic_a'],
        'state_abbr_primary': [None, 'TX'], 'county_name_primary': [None, 'Synthetic County']})
    enriched = module.enrich_geographic_labels(geometry, labels)
    assert enriched.state_abbr_primary.tolist() == ['TX', None]
    assert enriched.county_name_primary.tolist() == ['Synthetic County', None]
    with pytest.raises(ValueError, match='label coverage'):
        module.enrich_geographic_labels(geometry, labels.iloc[:1])


def test_ahp_method_byte_change_invalidates_native_cache_without_file_mutation(monkeypatch):
    module = runner()
    original = module.file_digest
    def changed_digest(path):
        return '0' * 64 if Path(path).as_posix().endswith('model/ahp.py') else original(path)
    monkeypatch.setattr(module, 'file_digest', changed_digest)
    with pytest.raises(ValueError, match='Current calculation method.*model/ahp.py'):
        module._baseline_context(ROOT, BASELINE)


def test_runtime_memory_guard_is_independently_content_bound(monkeypatch):
    module = runner()
    original = module.file_digest
    before = module._baseline_context(ROOT, BASELINE)
    def changed_digest(path):
        return '1' * 64 if Path(path).as_posix().endswith('model/enhanced.py') else original(path)
    monkeypatch.setattr(module, 'file_digest', changed_digest)
    after = module._baseline_context(ROOT, BASELINE)
    assert before['identity'] != after['identity']
    assert after['guard_hashes']['src/dc_locator/model/enhanced.py'] == '1' * 64


def test_semantic_request_identity_deduplicates_typed_numbers_and_weight_key_order():
    module = runner()
    _, _, _, baseline, _, _, profile = native_inputs()
    weights = {g['group_id']: i + 1 for i, g in enumerate(profile.groups)}
    integer_body = dict(peak_it_power_mw=132, average_load_percent=78, target_opening_year=2031,
        lifetime_years=30, cooling='all', weighting='user', screening_mode='EXPLORATORY',
        group_weights=weights, ahp_matrix=None)
    float_body = {**integer_body, 'peak_it_power_mw': 132., 'average_load_percent': 78.,
        'group_weights': {key: float(weights[key]) for key in reversed(weights)}}
    first_facility, first_profile = module.parse_request(integer_body, baseline, profile)
    second_facility, second_profile = module.parse_request(float_body, baseline, profile)
    assert first_facility.model_dump(mode='json') == second_facility.model_dump(mode='json')
    assert first_profile.model_dump(mode='json') == second_profile.model_dump(mode='json')
    context = {'identity': 'same_native_cache'}
    status = {'manifest_sha256': 'same_verified_manifest'}
    first = module._request_identity(context, status, first_facility, first_profile, integer_body)
    second = module._request_identity(context, status, second_facility, second_profile, float_body)
    assert first == second
    changed_body = {**integer_body, 'peak_it_power_mw': 133}
    changed_facility, changed_profile = module.parse_request(changed_body, baseline, profile)
    assert first_facility.facility_id != changed_facility.facility_id
    assert first != module._request_identity(context, status, changed_facility, changed_profile, changed_body)


@pytest.mark.parametrize('empty', [False, True])
def test_bounded_parallel_cluster_matches_native_complete_outputs_and_preserves_inputs(empty):
    module = runner()
    import geopandas as gpd
    from shapely.geometry import box
    from dc_locator.model.regions import cluster_regions, screen_region_land_support
    from dc_locator.model.metrics import KEYS
    geography = gpd.GeoDataFrame([dict(grid_id=f'synthetic_{row}_{col}', row=row, col=col,
        grid_definition_id='synthetic_lattice', cell_area_km2=1., study_area_intersection_km2=1.,
        suitable_land_area_km2=np.nan if (row, col) == (0, 1) else .1,
        geometry=box(col*1000, (1-row)*1000, (col+1)*1000, (2-row)*1000))
        for row in range(2) for col in range(4)], geometry='geometry', crs=5070)
    ranked = pd.DataFrame([dict(grid_id=grid_id, design_id=design, scenario_id=scenario,
        mcda_score=1. if i < 4 else .5, rankable=not empty, conditional=i == 1,
        critical_unknown=i == 1, is_pareto_optimal=i % 2 == 0, w_site_m3=float(i))
        for design in ('synthetic_dry', 'synthetic_wet') for scenario in ('synthetic_a', 'synthetic_b')
        for i, grid_id in enumerate(geography.grid_id)]).sample(frac=1, random_state=43).reset_index(drop=True)
    policy = dict(adjacency='rook', top_fraction=.5, minimum_cells=1, require_pareto=False,
        maximum_extent_km=2., extent_basis='project_assumption', extent_rationale='Synthetic test partition')
    expected_regions, expected_members = cluster_regions(geography, ranked, policy,
        ['w_site_m3'], 'synthetic_profile', 'synthetic_profile_hash')
    expected_regions, expected_members, expected_land = screen_region_land_support(
        expected_regions, expected_members, .3)
    before_geo, before_ranked = geography.copy(deep=True), ranked.copy(deep=True)
    report = {}
    regions, members, land = module._cluster_cohort_bounded(geography, ranked, policy,
        ['w_site_m3'], 'synthetic_profile', 'synthetic_profile_hash', .3,
        max_workers=2, parallel_minimum_rows=0, execution_report=report)
    pd.testing.assert_frame_equal(regions, expected_regions, check_exact=True)
    pd.testing.assert_frame_equal(members, expected_members, check_exact=True)
    pd.testing.assert_frame_equal(land, expected_land, check_exact=True)
    pd.testing.assert_frame_equal(geography, before_geo, check_exact=True)
    pd.testing.assert_frame_equal(ranked, before_ranked, check_exact=True)
    assert report['workers'] == (1 if empty else 2) and report['groups'] == 4
    assert len(report['worker_observations']) == (0 if empty else 4)
    assert all(row['process_peak_bytes'] < 4 * 1024**3 for row in report['worker_observations'])
