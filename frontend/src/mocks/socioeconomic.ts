/** Explicit synthetic county transport fixtures; never selected after a real API error. */
export function demoCountyEconomic(overrides: Record<string, unknown> = {}) {
  const value = { county_geoid: '01001', county_name: 'DEMO County Alpha', state_fips: '01', state_name: 'DEMO State',
    boundary_year: 2025, socioeconomic_year: 2024, overlap_area_km2: 1, overlap_fraction: 0.5,
    poverty_rate_pct: 24, income_usd: 42000, poverty_rate_moe_pct: 2, income_moe_usd: 3000,
    poverty_percentile: 80, low_income_percentile: 75, ...overrides };
  const metrics = Object.fromEntries(['poverty_rate_pct', 'income_usd', 'poverty_rate_moe_pct', 'income_moe_usd', 'poverty_percentile', 'low_income_percentile'].map(key => {
    const measured = value[key as keyof typeof value];
    return [key, { value: measured ?? null, unit: key.includes('usd') ? 'USD' : key.includes('percentile') ? 'percentile' : '%',
      status: measured == null ? 'unknown' : key.includes('percentile') || key.includes('moe') ? 'calculated' : 'observed', confidence: measured == null ? 'unknown' : 'medium', missing_reason: measured == null ? 'DEMO estimate unavailable' : null,
      method: key.includes('moe') ? 'DEMO calculated half-width of rounded 90% interval' : null, source_id: 'DEMO_SAIPE', data_year: 2024 }];
  }));
  return { ...value, metrics };
}
export function demoSocioeconomic(regionCounties: Record<string, unknown[]> = {}, boundaryYear = 2025) {
  return { schema_version: '1.6.0', context_schema_version: '1.0.0', run_id: 'DEMO_RUN', available: true,
    boundary_year: boundaryYear, socioeconomic_year: 2024, boundary_source_kind: 'Census cartographic boundary (generalized 1:500,000)',
    source_metadata: { estimate_source: { name: 'DEMO SAIPE county estimates', url: 'https://example.gov/saipe', year: 2024 }, boundary_source: { name: 'DEMO cartographic boundary', url: 'https://example.gov/county', year: boundaryYear, scale: '1:500,000' } },
    warnings: ['DEMO DATA · Synthetic county context; no technical score or fiscal estimate.'], coverage_summary: {},
    fiscal_context: { local_revenue: { value: null, status: 'unknown', missing_reason: 'Fiscal inputs not acquired' }, service_pressure: { value: null, status: 'unknown', missing_reason: 'Fiscal inputs not acquired' } },
    region_counties: regionCounties };
}
