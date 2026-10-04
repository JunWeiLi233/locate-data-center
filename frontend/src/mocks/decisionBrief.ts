/** Explicit synthetic presentation fixture. Never geographic evidence. */
export const DEMO_DECISION_BRIEF = {
  schema_version: '1.0.0', run_id: 'DEMO_RUN', data_mode: 'synthetic', scenario_id: 'current',
  interpretation: 'These geographic regions deserve further investigation under the stated facility requirements, datasets, constraints, assumptions, and decision preferences.',
  scope: 'Synthetic three-cell software fixture', analyzed_cell_count: 3, resolution_m: 50000,
  facility: { peak_it_power_mw: 100, average_it_load_factor: 0.8, target_opening_year: 2030, operating_lifetime_years: 25, hours_in_modeled_year: 8760, basis: 'project_assumption', rationale: 'Synthetic facility assumption for interface verification.' },
  recommendation: {
    status: 'CONDITIONAL_INVESTIGATION', rationale: 'Stored representative rank identifies this conditional investigation area.',
    region_id: 'DEMO_ALPHA', grid_id: 'DEMO_CELL', design_id: 'air_dry_assumed', scenario_id: 'current', rank: 1, score: 88,
    pareto_status: true, geographic_label: 'Synthetic county context; cell spans multiple counties',
    centroid: { lat: 39.325, lon: -101.5 }, region_centroid: { lat: 40, lon: -102 }, region_area_km2: 5000, region_cell_count: 2,
    metrics: [{ id: 'w_site_m3', value: 0, unit: 'm3/year', status: 'scenario', confidence: 'low', missing_reason: null }],
  },
  alternatives: [{ region_id: 'DEMO_BETA', grid_id: 'DEMO_CELL', design_id: 'cold_plate_tower_assumed', scenario_id: 'current', rank: 2, score: 83, metrics: [{ id: 'w_site_m3', value: 210240, unit: 'm3/year', status: 'scenario', confidence: 'low', missing_reason: null }] }],
  framework: { profile_id: 'synthetic_profile', weighting_method: 'equal', criteria: [{ metric_id: 'annual_site_water_consumption', label: 'Site water consumption', unit: 'm3/year', direction: 'lower_is_better', weight: 0.125, reference_low: 0, reference_high: 1000000, role: 'scored', basis: 'project_assumption', rationale: 'Explicit synthetic normalization bounds.', normalized_score: 100, contribution: 12.5 }], excluded_criteria: ['Heat reuse: supported measurement unavailable'], missing_data_policy: 'Required missing metrics remain unranked; no candidate-specific weight renormalization.' },
  evidence: { sources: [{ source_id: 'DEMO_SOURCE', implemented: true, acquired: false, analyzed: true, analyzed_cells: 3, status: 'PARTIAL', source_url: null, source_version: 'synthetic', data_year: 'fixture', retrieved_at: null }], assumptions: ['Synthetic constant annual cooling design.'], input_hashes: { fixture: 'demo-hash' } },
  impact: { cooling_comparisons: [{ grid_id: 'DEMO_CELL', scenario_id: 'current', reference_design_id: 'cold_plate_tower_assumed', alternative_design_id: 'air_dry_assumed', reference_minus_alternative: { e_facility_mwh: null, c_electricity_tonnes: null, w_site_m3: 210240, w_electricity_m3: null }, basis: 'Paired same-cell synthetic annual quantities; not total-water savings.' }], unknowns: [{ id: 'total_lifecycle_co2e', value: null, status: 'unknown', missing_reason: 'Construction inventory unavailable.' }, { id: 'total_water_benefit', value: null, status: 'unknown', missing_reason: 'Electricity-generation water is unavailable.' }], boundary: 'Operational estimates only; no construction or useful heat credit is inferred.' },
  risks: [{ requirement: 'power_capacity', outcome: 'UNKNOWN', missing_reason: 'Utility commitment unavailable.', action: 'Verify utility connection and capacity.' }],
  implementation_vision: [{ period: '2030–2054', label: 'Proposed operation and adaptation', actions: ['Meter energy and water and review external scenarios.'], evidence_gate: 'Approve changes only after verified engineering evidence.' }],
  limitations: ['Synthetic software fixture; no approved parcel or national optimum.'],
};
