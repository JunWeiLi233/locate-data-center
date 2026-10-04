import { describe, expect, it } from 'vitest';
import * as api from '../api/regions';
import * as regions from './regions';
import { demoCountyEconomic, demoSocioeconomic } from '../mocks/socioeconomic';
import type { SocioeconomicContext, CountyEconomicRecord, CountyEconomicFilters } from '../types/domain';

function parse(value: unknown): SocioeconomicContext {
  expect(api).toHaveProperty('parseSocioeconomic');
  return (api as unknown as { parseSocioeconomic: (value: unknown) => SocioeconomicContext }).parseSocioeconomic(value);
}
function matches(counties: CountyEconomicRecord[] | undefined, filters: CountyEconomicFilters): boolean {
  expect(regions).toHaveProperty('matchesCountyEconomicFilters');
  return (regions as unknown as { matchesCountyEconomicFilters: (counties: CountyEconomicRecord[] | undefined, filters: CountyEconomicFilters) => boolean }).matchesCountyEconomicFilters(counties, filters);
}
const both = { minimumPovertyRatePct: 20, maximumMedianHouseholdIncomeUsd: 50000 };

describe('county economic context parsing and display filters', () => {
  it('requires persisted poverty and low-income percentiles to match in the same county with raw thresholds', () => {
    const filters = { ...both, minimumPovertyPercentile: 80, minimumLowIncomePercentile: 75 };
    const split = parse(demoSocioeconomic({ REGION: [
      demoCountyEconomic({ poverty_percentile: 90, low_income_percentile: 10 }),
      demoCountyEconomic({ county_geoid: '01003', poverty_percentile: 10, low_income_percentile: 90 }),
    ] })).regionCounties.REGION;
    expect(matches(split, filters)).toBe(false);
    const qualified = parse(demoSocioeconomic({ REGION: [demoCountyEconomic({ county_geoid: '01005' })] })).regionCounties.REGION;
    expect(matches([...split, ...qualified], filters)).toBe(true);
    qualified[0].medianHouseholdIncomeUsd = 90000;
    expect(matches([...split, ...qualified], filters)).toBe(false);
  });
  it('rejects missing/unknown percentiles and zero overlap, while measured percentile zero is valid', () => {
    const filters = { minimumPovertyRatePct: null, maximumMedianHouseholdIncomeUsd: null, minimumPovertyPercentile: 0, minimumLowIncomePercentile: 0 };
    const unknown = demoCountyEconomic(); unknown.metrics.poverty_percentile.status = 'unknown';
    const context = parse(demoSocioeconomic({
      MISSING: [demoCountyEconomic({ low_income_percentile: null })], UNKNOWN: [unknown],
      ZERO: [demoCountyEconomic({ poverty_percentile: 0, low_income_percentile: 0 })],
      NO_OVERLAP: [demoCountyEconomic({ overlap_area_km2: 0, overlap_fraction: 0 })],
    }));
    expect(matches(context.regionCounties.MISSING, filters)).toBe(false);
    expect(matches(context.regionCounties.UNKNOWN, filters)).toBe(false);
    expect(matches(undefined, filters)).toBe(false);
    expect(matches(context.regionCounties.NO_OVERLAP, filters)).toBe(false);
    expect(matches(context.regionCounties.ZERO, filters)).toBe(true);
    expect(matches(context.regionCounties.ZERO, { ...filters, minimumPovertyPercentile: 101 })).toBe(false);
    expect(matches(context.regionCounties.ZERO, { ...filters, minimumLowIncomePercentile: -1 })).toBe(false);
    expect(matches(undefined, { ...filters, minimumPovertyPercentile: null, minimumLowIncomePercentile: null })).toBe(true);
  });
  it('requires ALL active thresholds in the SAME positively overlapping county', () => {
    const counties = parse(demoSocioeconomic({ REGION: [demoCountyEconomic({ poverty_rate_pct: 30, income_usd: 90000 }), demoCountyEconomic({ county_geoid: '01003', poverty_rate_pct: 10, income_usd: 40000 })] })).regionCounties.REGION;
    expect(matches(counties, both)).toBe(false);
    expect(matches([...counties, ...parse(demoSocioeconomic({ REGION: [demoCountyEconomic({ county_geoid: '01005' })] })).regionCounties.REGION], both)).toBe(true);
  });
  it('does not treat missing county/estimate evidence as a filter match', () => {
    const counties = parse(demoSocioeconomic({ REGION: [demoCountyEconomic({ poverty_rate_pct: null }), demoCountyEconomic({ county_geoid: '01003', income_usd: null })] })).regionCounties.REGION;
    expect(matches(counties, both)).toBe(false); expect(matches(undefined, both)).toBe(false);
    expect(matches([], both)).toBe(false);
  });
  it('leaves all regions eligible when empty thresholds are disabled, even without county evidence', () => {
    expect(matches(undefined, { minimumPovertyRatePct: null, maximumMedianHouseholdIncomeUsd: null })).toBe(true);
  });
  it('allows a measured zero while rejecting zero overlap and unknown non-null wire values', () => {
    const unknown = demoCountyEconomic({ poverty_rate_pct: 40 }); unknown.metrics.poverty_rate_pct.status = 'unknown';
    const context = parse(demoSocioeconomic({ ZERO: [demoCountyEconomic({ poverty_rate_pct: 0 })], NO_OVERLAP: [demoCountyEconomic({ overlap_area_km2: 0, overlap_fraction: 0 })], UNKNOWN: [unknown] }));
    expect(matches(context.regionCounties.ZERO, { minimumPovertyRatePct: 0, maximumMedianHouseholdIncomeUsd: null })).toBe(true);
    expect(matches(context.regionCounties.NO_OVERLAP, both)).toBe(false);
    expect(context.regionCounties.UNKNOWN[0].povertyRatePct).toBeNull(); expect(matches(context.regionCounties.UNKNOWN, both)).toBe(false);
  });
  it('preserves five-character GEOIDs, estimate/boundary years, MOEs and metric source statuses', () => {
    const context = parse(demoSocioeconomic({ REGION: [demoCountyEconomic({ county_geoid: '01001' })] })); const county = context.regionCounties.REGION[0];
    expect(county.countyGeoid).toBe('01001'); expect(county.boundaryYear).toBe(2025); expect(county.socioeconomicYear).toBe(2024);
    expect(county.povertyRateMoePct).toBe(2); expect(county.incomeMoeUsd).toBe(3000); expect(county.metrics.poverty_rate_pct.status).toBe('observed');
    expect(context.sourceMetadata).toMatchObject({ estimate_source: { url: 'https://example.gov/saipe' } });
  });
  it('rejects invalid county identifiers and unsupported boundary vintages rather than guessing', () => {
    expect(() => parse(demoSocioeconomic({ REGION: [demoCountyEconomic({ county_geoid: 1001 })] }))).toThrow();
    expect(() => parse(demoSocioeconomic({}, 2024))).toThrow();
  });
});
