/**
 * DEMO DATA: a synthetic rediscovery payload in the `/api/rediscovery/{id}` wire format, for tests only.
 * Coordinates, scores and facilities are invented and are not geographic evidence. The interface never falls
 * back to this fixture.
 */
const factor = (metric: string, weight: number, normalized: number, raw: number, unit: string, locationDependent = true) => ({
  metric_id: metric, label: metric, group_id: metric, group_label: metric, weight, normalized_score: normalized, contribution: weight * normalized,
  national_percentile: 90, direction: 'minimize', reference_low: 0, reference_high: 100, raw_value: raw, raw_unit: unit, value_status: 'proxy',
  confidence: 'low', source_id: 'synthetic', data_year: '2023', role: 'decision_metric', location_dependent: locationDependent, coverage_frac: 1,
});

function candidate(rank: number, classification: string, distance: number, robustness: number | null) {
  return {
    rank, candidate_id: `fixture:${rank}`, grid_id: `g1000m-r${String(1000 + rank).padStart(4, '0')}-c4000`, lat: 40 + rank * 0.5, lon: -80 + rank,
    coordinate_basis: 'synthetic', place_label: `DEMO County ${rank}, ZZ`, county_name: `DEMO County ${rank}`, state_abbr: 'ZZ', county_geoid: '99001',
    place_label_basis: 'synthetic', design_id: 'air_dry_assumed', scenario_id: 'historical_static_2023', suitability_score: 95 - rank,
    score_percentile: 99.9, tied_cells_at_score: rank <= 2 ? 2 : 1, score_rank_min: rank <= 2 ? 1 : rank, score_rank_max: rank <= 2 ? 2 : rank,
    top_n_bucket: rank <= 2 ? 2 : 4, screening_status: 'UNSCREENED', screening_note: 'Synthetic fixture', classification,
    distance_to_nearest_existing_dc_km: distance,
    nearest_existing_dc: { facility_id: 'fixture:dc1', name: 'DEMO facility', operator: 'DEMO operator', county: 'DEMO County', state_abbr: 'ZZ',
      footprint_type: 'building', lat: 40, lon: -80 },
    existing_dc_within_km: { '10': distance <= 10 ? 1 : 0, '25': distance <= 25 ? 1 : 0 },
    robustness: { score: robustness, status: robustness === null ? 'unknown' : 'calculated', provider: robustness === null ? null : 'county_monte_carlo',
      method: robustness === null ? null : 'county_monte_carlo_pareto_frequency', source: robustness === null ? null : 'run_fixture',
      spatial_support: robustness === null ? null : 'county', missing_reason: robustness === null ? 'Synthetic: county not in cohort' : null,
      details: robustness === null ? null : { county_name: 'DEMO County', state_abbr: 'ZZ', structural_scenarios: 9, expected_frontier_scenarios: 9 } },
    weight_cases: { retained: 4, total: 4, retained_ids: ['weight_energy_focus', 'weight_water_focus', 'weight_infrastructure_focus', 'weight_land_focus'] },
    explanation: `DEMO County ${rank}, ZZ ranks highly because of synthetic fixture criteria.`, strengths: ['suitable_land_fraction'], weaknesses: [],
    factors: [factor('suitable_land_fraction', 0.25, 100, 1, 'frac'), factor('transmission_proximity', 0.25, 90, 5, 'km'),
      factor('annual_electricity_co2e', 0.25, 80, 168000, 'tonnes_CO2e_per_year'), factor('local_baseline_water_stress', 0.125, 70, 1.5, 'score_0_to_5'),
      factor('annual_site_water_consumption', 0.125, 100, 0, 'm3_consumed_per_year', false)],
  };
}

export function syntheticRediscoveryPayload() {
  const rates = [2, 4].flatMap(n => [10, 25].map(radius => ({ top_n: n, radius_km: radius, hits: n === 2 ? (radius === 10 ? 0 : 1) : 2, candidates: n,
    hit_rate: n === 2 ? (radius === 10 ? 0 : 0.5) : 0.5 })));
  return {
    schema_version: '1.0.0', analysis_id: 'demo_fixture', analysis_name: 'DEMO_SYNTHETIC_FIXTURE', analysis_identity: 'fixture', data_mode: 'synthetic',
    finished_at_utc: '2026-10-04T00:00:00+00:00', timeline: {}, interpretation: 'DEMO interpretation: search areas for further investigation.',
    validation_framing: 'DEMO framing. Existing facilities are not ground truth.', research_question: 'DEMO research question?',
    model: { model_run: 'runs/demo', profile_id: 'demo_profile', scenario_id: 'historical_static_2023', cells_valued: 1000, cells_total: 1100,
      max_score: 94, cells_tied_at_max_score: 2, screening_status: 'UNSCREENED', weights: { suitable_land_fraction: 0.25 }, designs: ['air_dry_assumed'],
      verification: { recomposed_score_max_abs_difference: 0, persisted_parent_best_reproduction: { status: 'verified' } }, unscored_reasons: {} },
    parameters: { top_n_values: [2, 4], min_candidate_distance_km: 25, distance_method: 'haversine_spherical_r6371.0088km', separation_rule: 'greedy',
      ranking: 'score', hit_radii_km: [10, 25], classification: { validated_max_km: 25, emerging_min_km: 50, counts_by_top_n: {} },
      hubs: { linkage_km: 10, min_facilities: 5, declared: {} }, baselines: { draws: 100, seed: 1, area_weighted: true, controls: [], p_value: 'one-sided' } },
    facility_source: { source_name: 'DEMO inventory', version: 'v0 (fixture)', doi: '10.0000/demo', license: 'fixture', conus_facility_records: 2,
      unique_osm_ids: 2, file: { retrieved_at_utc: '2026-10-04T00:00:00+00:00', url: 'synthetic://', sha256: 'f'.repeat(64) },
      limitations: ['DEMO limitation'] },
    results: {
      hit_rates: rates,
      tie_sensitivity: { hit_rates: rates.map(row => ({ top_n: row.top_n, radius_km: row.radius_km, mean: row.hit_rate, p2_5: 0, p97_5: 1 })) },
      tie_blocks: { candidates_in_top_score_block: 2, top_score_block_cells: 2 },
      baseline_comparison: [2, 4].flatMap(n => [10, 25].flatMap(radius => ['uniform_conus', 'infrastructure_plausible'].map(control => ({
        control_id: control, control_label: control === 'uniform_conus' ? 'Random CONUS locations' : 'Random near-transmission land', top_n: n, radius_km: radius,
        draws: 100, pool_cells: 1000, model_hit_rate: 0.5, mean: 0.1, p2_5: 0, p97_5: 0.3, lift: 5, p_value_one_sided: 0.02 })))),
      presence_background: { baseline: { auc: 0.71, median_score_percentile: 72, occupied_cells_valued: 3, occupied_cells: 3, share_in_top_quartile: 0.4,
        share_above_national_median: 0.8 }, weight_land_focus: { auc: 0.7 } },
      facility_recall: [{ top_n: 2, radius_km: 25, facilities_covered: 1, facilities: 2, recall: 0.5 }],
      hub_recall: [{ top_n: 2, radius_km: 25, hubs_rediscovered: 1, hubs: 1, recall: 1 }, { top_n: 4, radius_km: 25, hubs_rediscovered: 1, hubs: 1, recall: 1 }],
      hub_count: 1,
      classification_counts: { '2': { validated: 1, unresolved: 0, emerging: 1 }, '4': { validated: 1, unresolved: 1, emerging: 2 } },
      nearest_distance_quantiles: {},
    },
    robustness: { providers: [{ provider_id: 'county_monte_carlo', label: 'DEMO county Monte Carlo', available: true, missing_reason: null,
      score_definition: 'synthetic' }], candidates_with_score: 1,
      weight_cases: [{ case_id: 'weight_land_focus', group_weights: { energy_carbon: 0.2, water_stewardship: 0.2, grid_infrastructure: 0.2, land: 0.4 } }] },
    factors: { not_scored: { fiber: 'DEMO: fiber not scored.', climate: 'DEMO: climate not scored.' } },
    explanation_rule: {}, places: {},
    candidates: [candidate(1, 'emerging', 220, null), candidate(2, 'validated', 12, 100), candidate(3, 'unresolved', 30, null), candidate(4, 'emerging', 90, null)],
    facilities: [{ facility_id: 'fixture:dc1', name: 'DEMO facility', operator: 'DEMO operator', county: 'DEMO County', state_abbr: 'ZZ', lat: 40, lon: -80,
      footprint_type: 'building', footprint_sqft: 1000, hub_id: 'hub_001' },
    { facility_id: 'fixture:dc2', name: null, operator: null, county: 'DEMO County', state_abbr: 'ZZ', lat: 41, lon: -79, footprint_type: 'point',
      footprint_sqft: null, hub_id: null }],
    hubs: [{ hub_id: 'hub_001', facilities: 5, label: 'DEMO County, ZZ', centroid_lat: 40, centroid_lon: -80, states: ['ZZ'], top_operators: ['DEMO operator'],
      nearest_top2_candidate_km: 12, nearest_top4_candidate_km: 12 }],
    surface: { url: '/api/rediscovery/demo_fixture/surface.png', coordinates: [[-125, 49.6], [-66.5, 49.6], [-66.5, 24], [-125, 24]], score_low: 70,
      score_high: 94, ink_rgb: [34, 52, 60], opacity_low: 0.06, opacity_high: 0.8 },
    limitations: ['DEMO limitation one'], files: {},
  };
}

export const syntheticRediscoveryIndex = {
  schema_version: '1.0.0', default_analysis_id: 'demo_fixture',
  analyses: [{ analysis_id: 'demo_fixture', analysis_name: 'DEMO_SYNTHETIC_FIXTURE', data_mode: 'synthetic', finished_at_utc: null,
    model_run: 'runs/demo', candidates: 4, facility_source: 'DEMO inventory', available: true, reason: null }],
};
