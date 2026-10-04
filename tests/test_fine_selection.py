"""Fine-surface scores follow the declared profile; Unknown is never zero; parent selection is deterministic."""
import geopandas as gpd
import numpy as np
import pandas as pd
import pytest
import shapely

from dc_locator.model.fine_selection import (design_constants, profile_weights, score_window, select_parents_by_surface,
                                             select_region_best_parents, summarize_window)
from dc_locator.model.metrics import load_profile
from dc_locator.paths import project_root
from dc_locator.geography.fine_features import attach_evidence


@pytest.fixture(scope='module')
def profile():
    return load_profile(project_root() / 'configs' / 'scoring_profile_regional.yaml')


def features(**overrides):
    base = dict(potentially_suitable_land_frac=[0.9], nlcd_coverage_frac=[1.0], transmission_distance_km=[10.0],
                baseline_water_stress_score=[2.5], baseline_water_stress_score_coverage_frac=[1.0],
                grid_carbon_intensity_kg_per_mwh=[200.0], egrid_coverage_frac=[1.0])
    frame = attach_evidence(pd.DataFrame(base), {})
    for key, value in overrides.items():
        frame[key] = value
    return frame


CONSTANTS = pd.DataFrame({'design_id': ['air_dry_assumed'], 'scenario_id': ['current'], 'e_facility_mwh': [840960.0], 'w_site_m3': [0.0]})
for column, unit in (('e_facility_mwh', 'mwh'), ('w_site_m3', 'm3_consumed')):
    CONSTANTS[column + '_status'] = 'calculated'
    CONSTANTS[column + '_confidence'] = 'low'
    CONSTANTS[column + '_unit'] = unit
CONSTANTS['carbon_data_year'] = '2023'


def test_hand_calculated_decision_value(profile):
    weights = profile_weights(profile)
    assert weights == pytest.approx({'annual_electricity_co2e': 0.25, 'annual_site_water_consumption': 0.125,
                                     'local_baseline_water_stress': 0.125, 'transmission_proximity': 0.25, 'suitable_land_fraction': 0.25})
    # CO2e 840960 MWh x 200 kg/MWh = 168192 t -> 83.1808; water 0 -> 100; stress 2.5/5 -> 50; 10/50 km -> 80; land 0.9 -> 90.
    expected = 0.25 * 83.1808 + 0.125 * 100 + 0.125 * 50 + 0.25 * 80 + 0.25 * 90
    assert score_window(features(), profile, weights, CONSTANTS).fine_score.iloc[0] == pytest.approx(expected, abs=1e-9)


def test_references_clip_and_unknown_or_low_coverage_is_unscored_never_zero(profile):
    weights = profile_weights(profile)
    clipped = score_window(features(transmission_distance_km=[80.0]), profile, weights, CONSTANTS).fine_score.iloc[0]
    assert clipped == pytest.approx(0.25 * 83.1808 + 0.125 * 100 + 0.125 * 50 + 0.25 * 0 + 0.25 * 90, abs=1e-9)
    for override in ({'potentially_suitable_land_frac': [np.nan]}, {'nlcd_coverage_frac': [0.9]}, {'egrid_coverage_frac': [0.5]},
                     {'baseline_water_stress_score_coverage_frac': [0.999]}, {'transmission_distance_km': [np.nan]}):
        assert np.isnan(score_window(features(**override), profile, weights, CONSTANTS).fine_score.iloc[0]), override
    unknown_water = CONSTANTS.assign(w_site_m3=np.nan)
    assert np.isnan(score_window(features(), profile, weights, unknown_water).fine_score.iloc[0])


def test_design_physics_must_be_location_independent():
    performance = pd.DataFrame({'grid_id': ['a', 'b', 'a', 'b'], 'design_id': ['dry', 'dry', 'tower', 'tower'], 'scenario_id': ['current'] * 4,
                                'e_facility_mwh': [10.0, 10.0, 12.0, 12.0], 'w_site_m3': [0.0, 0.0, 5.0, 5.0]})
    constants = design_constants(performance)
    assert constants[['design_id', 'scenario_id', 'e_facility_mwh', 'w_site_m3']].to_dict('records') == [{'design_id': 'dry', 'scenario_id': 'current', 'e_facility_mwh': 10.0, 'w_site_m3': 0.0},
                                            {'design_id': 'tower', 'scenario_id': 'current', 'e_facility_mwh': 12.0, 'w_site_m3': 5.0}]
    with pytest.raises(ValueError, match='varies by location'):
        design_constants(performance.assign(e_facility_mwh=[10.0, 11.0, 12.0, 12.0]))


def test_numeric_values_with_invalid_evidence_are_unscored(profile):
    weights = profile_weights(profile)
    for override in ({'transmission_distance_km_status': ['unknown']},
                     {'baseline_water_stress_score_confidence': ['unknown']},
                     {'grid_carbon_intensity_kg_per_mwh_source_id': ['unverified']},
                     {'grid_carbon_intensity_kg_per_mwh_source_field': ['SRCO2RTA']}):
        assert np.isnan(score_window(features(**override), profile, weights, CONSTANTS).fine_score.iloc[0])


def test_missing_evidence_does_not_inherit_an_accepted_status(profile):
    bare = features()[[column for column in features().columns if not column.endswith(('_status', '_confidence', '_missing_reason', '_source_id', '_source_field', '_unit', '_data_year'))]]
    assert np.isnan(score_window(bare, profile, profile_weights(profile), CONSTANTS).fine_score.iloc[0])
    for bad in (CONSTANTS.assign(w_site_m3_unit='m3_withdrawn'), CONSTANTS.assign(e_facility_mwh_status='unknown'),
                CONSTANTS.assign(carbon_data_year='2030')):
        assert np.isnan(score_window(features(), profile, profile_weights(profile), bad).fine_score.iloc[0])


def test_partial_carbon_remains_unknown_with_a_weaker_score_policy(profile):
    policy = profile.model_copy(deep=True)
    policy.metrics[0].minimum_coverage_frac = 0.5
    result = score_window(features(egrid_coverage_frac=[0.9]), policy, profile_weights(policy), CONSTANTS)
    assert result.fine_score.isna().all()
    assert result.unscored_reason.iloc[0] == 'annual_electricity_co2e'


def test_summary_and_selection_are_deterministic_and_skip_unscored_parents():
    scores = pd.DataFrame({'design_id': ['dry'] * 3, 'scenario_id': ['current'] * 3, 'fine_score': [70.0, 90.0, 90.0]}, index=[0, 1, 2])
    grid_ids = pd.Series(['g-c', 'g-b', 'g-a'])
    summary = summarize_window('P2', grid_ids, scores)
    assert summary.loc[0, 'best_grid_id'] == 'g-a' and summary.loc[0, 'best_fine_score'] == 90.0 and summary.loc[0, 'scored_cells'] == 3
    empty = summarize_window('P3', pd.Series(['x']), pd.DataFrame({'design_id': ['dry'], 'scenario_id': ['current'], 'fine_score': [np.nan]}))
    other = summarize_window('P1', pd.Series(['y']), pd.DataFrame({'design_id': ['dry'], 'scenario_id': ['current'], 'fine_score': [90.0]}))
    parents = gpd.GeoDataFrame({'grid_id': ['P1', 'P2', 'P3']}, geometry=[shapely.box(i, 0, i + 1, 1) for i in range(3)], crs=5070)
    selected = select_parents_by_surface(parents, pd.concat([summary, empty, other], ignore_index=True), limit=5)
    assert selected.grid_id.tolist() == ['P1', 'P2']
    assert selected.set_index('grid_id').fine_selection_rank.to_dict() == {'P1': 1, 'P2': 2}  # tie broken by grid_id
    assert select_parents_by_surface(parents, pd.concat([summary, other]), limit=1).grid_id.tolist() == ['P1']
    with pytest.raises(ValueError):
        select_parents_by_surface(parents, empty, limit=1)
    scenarios = pd.concat([summary, summary.assign(scenario_id='external_future')], ignore_index=True)
    with pytest.raises(ValueError, match='one external scenario'):
        select_parents_by_surface(parents, scenarios, limit=1)


def test_inconsistent_ahp_preferences_are_refused(profile):
    groups = profile.weight_criterion_ids
    matrix = [[1, 9, 1 / 9, 1], [1 / 9, 1, 9, 1], [9, 1 / 9, 1, 1], [1, 1, 1, 1]]  # cyclic 9:1 judgments
    inconsistent = profile.model_copy(update={'weighting_method': 'ahp', 'ahp_judgments': {'criteria_ids': groups, 'matrix': matrix}})
    with pytest.raises(ValueError, match='AHP preferences require review'):
        profile_weights(inconsistent)


def test_region_best_parents_keep_one_parent_per_national_region():
    """Hand-built regions: a better member replaces the representative; ties and unscored regions keep it."""
    best = {'P1': 80.0, 'P2': 90.0, 'P6': 90.0, 'P3': 85.0, 'P4': 85.0, 'P5': np.nan}
    summary = pd.DataFrame({'parent_grid_id': list(best), 'design_id': 'dry', 'scenario_id': 'current',
                            'best_grid_id': [f'{grid_id}-cell' for grid_id in best], 'best_fine_score': list(best.values())})
    summary = pd.concat([summary, summary.assign(design_id='tower', best_fine_score=summary.best_fine_score - 1)], ignore_index=True)
    regions = pd.DataFrame({'region_id': ['R1', 'R2', 'R2b', 'R3'], 'representative_grid_id': ['P1', 'P3', 'P3', 'P5']})
    membership = pd.DataFrame({'region_id': ['R1', 'R1', 'R1', 'R2', 'R2', 'R2b', 'R3'],
                               'grid_id': ['P1', 'P2', 'P6', 'P3', 'P4', 'P3', 'P5']})
    parents = gpd.GeoDataFrame({'grid_id': ['P1', 'P2', 'P3', 'P4', 'P5', 'P6']},
                               geometry=[shapely.box(i, 0, i + 1, 1) for i in range(6)], crs=5070)
    selected = select_region_best_parents(parents, summary, regions, membership).set_index('grid_id')
    assert selected.index.tolist() == ['P2', 'P3', 'P5']  # tie between P2 and P6 broken by grid_id
    assert selected.fine_region_selection_basis.to_dict() == {'P2': 'fine_surface', 'P3': 'representative', 'P5': 'representative_unscored'}
    assert selected.fine_region_representative.to_dict() == {'P2': 'P1', 'P3': 'P3', 'P5': 'P5'}
    assert selected.national_region_ids_json.to_dict() == {'P2': '["R1"]', 'P3': '["R2","R2b"]', 'P5': '["R3"]'}
    assert selected.loc['P2', 'best_fine_score'] == 90.0 and selected.loc['P2', 'fine_best_design_id'] == 'dry'
    assert selected.loc['P2', 'fine_best_grid_id'] == 'P2-cell' and np.isnan(selected.loc['P5', 'best_fine_score'])
    assert selected.fine_selection_rank.to_dict() == {'P2': 1, 'P3': 2, 'P5': 3}
    assert selected.geometry.notna().all()
    again = select_region_best_parents(parents, summary.iloc[::-1], regions.iloc[::-1], membership.iloc[::-1])
    pd.testing.assert_frame_equal(again, selected.reset_index())  # input order never changes the choice
    with pytest.raises(ValueError, match='one external scenario'):
        select_region_best_parents(parents, pd.concat([summary, summary.assign(scenario_id='future')]), regions, membership)
    with pytest.raises(ValueError, match='no regions'):
        select_region_best_parents(parents, summary, regions.iloc[:0], membership.iloc[:0])
