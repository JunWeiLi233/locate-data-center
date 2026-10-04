import type { CandidateRegion, Capabilities, CountyEconomicFilters, CountyEconomicRecord, Metric, ScreeningStatus } from '../types/domain';
import { compareRegions, placeKey } from '../map/mapData';

/** Presentation only: groups backend alternatives that share one search geometry. Ranks and scores stay the backend's. */
export interface PlaceGroup { key: string; primary: CandidateRegion; alternatives: CandidateRegion[] }

export function groupPlaces(regions: CandidateRegion[]): PlaceGroup[] {
  const groups = new Map<string, CandidateRegion[]>();
  for (const region of [...regions].sort(compareRegions)) {
    const key = placeKey(region);
    groups.set(key, [...(groups.get(key) ?? []), region]);
  }
  return [...groups].map(([key, alternatives]) => ({ key, primary: alternatives[0], alternatives }));
}

export function placeAlternatives(region: CandidateRegion, regions: CandidateRegion[]): CandidateRegion[] {
  const key = placeKey(region);
  return regions.filter(item => placeKey(item) === key).sort(compareRegions);
}

export function regionName(region: Pick<CandidateRegion, 'label' | 'placeLabel'>): string {
  return region.placeLabel || region.label;
}

/** Area numbers for repeated place labels, per place key: the second-ranked place named "Livingston, NY" gets " · area 2", and so on. */
export function placeNameSuffixes(regions: CandidateRegion[]): Map<string, string> {
  const suffixes = new Map<string, string>();
  const seen = new Map<string, number>();
  for (const { key, primary } of groupPlaces(regions)) {
    const base = regionName(primary);
    const occurrence = (seen.get(base) ?? 0) + 1;
    seen.set(base, occurrence);
    if (occurrence > 1) suffixes.set(key, ` · area ${occurrence}`);
  }
  return suffixes;
}

export function humanize(value: string): string {
  const text = value.replaceAll('_', ' ').trim();
  return text ? text[0].toUpperCase() + text.slice(1) : value;
}

const KNOWN_COOLING: Record<string, string> = { air_dry_assumed: 'Air / dry cooling (assumed)', cold_plate_tower_assumed: 'Direct-to-chip / tower (assumed)' };
export function coolingName(designId: string, options: Capabilities['coolingOptions'] = []): string {
  return options.find(option => option.id === designId)?.label || KNOWN_COOLING[designId] || humanize(designId);
}

/** Drops the trailing assumption marker for compact rows; full labels appear in the region panel. */
export function shortCooling(label: string): string {
  return label.replace(/\s*(\(assumed\)|assumption)$/i, '').trim() || label;
}

export function statusWord(status: ScreeningStatus): string {
  return status[0] + status.slice(1).toLowerCase();
}

export function spansLabel(region: Pick<CandidateRegion, 'regionStates'>): string | null {
  const states = region.regionStates ?? [];
  if (states.length < 2) return null;
  return `Spans ${states.slice(0, 3).join(', ')}${states.length > 3 ? ` +${states.length - 3}` : ''}`;
}

/** Splits backend requirement text such as "utility_capacity: reason" into a readable title and its reason. */
export function verificationItem(value: string): { title: string; detail: string | null } {
  const match = /^([a-z0-9_]+):\s*(.+)$/.exec(value);
  return match ? { title: humanize(match[1]), detail: match[2] } : { title: value, detail: null };
}

const KEY_METRICS = ['e_facility_mwh', 'c_electricity_tonnes', 'w_site_m3', 'grid_carbon_intensity_kg_per_mwh', 'transmission_distance_km', 'baseline_water_stress_score'];
/** The headline physical quantities, in a fixed order; other runs fall back to their first non-verification metrics. */
export function keyMetrics(metrics: Metric[]): Metric[] {
  const measured = metrics.filter(metric => metric.group !== 'verification');
  const preferred = KEY_METRICS.flatMap(id => measured.find(metric => metric.id === id) ?? []);
  if (preferred.length >= 4) return preferred;
  return [...preferred, ...measured.filter(metric => !preferred.includes(metric))].slice(0, 4);
}

/** Display filter only: one intersecting county must satisfy every active preference. */
export function matchesCountyEconomicFilters(counties: CountyEconomicRecord[] | undefined, filters: CountyEconomicFilters): boolean {
  const poverty = filters.minimumPovertyRatePct, income = filters.maximumMedianHouseholdIncomeUsd;
  const povertyPercentile = filters.minimumPovertyPercentile ?? null, lowIncomePercentile = filters.minimumLowIncomePercentile ?? null;
  if (poverty === null && income === null && povertyPercentile === null && lowIncomePercentile === null) return true;
  const invalidPercent = (value: number | null) => value !== null && (!Number.isFinite(value) || value < 0 || value > 100);
  if (invalidPercent(poverty) || invalidPercent(povertyPercentile) || invalidPercent(lowIncomePercentile) || (income !== null && (!Number.isFinite(income) || income < 0))) return false;
  return (counties??[]).some(county=>{
    if(!(county.overlapAreaKm2!==null&&county.overlapAreaKm2>0)&&!(county.overlapFraction!==null&&county.overlapFraction>0))return false;
    return (poverty===null||(county.povertyRatePct!==null&&county.metrics.poverty_rate_pct?.status!=='unknown'&&county.povertyRatePct>=poverty))
      &&(income===null||(county.medianHouseholdIncomeUsd!==null&&county.metrics.income_usd?.status!=='unknown'&&county.medianHouseholdIncomeUsd<=income))
      &&(povertyPercentile===null||(county.povertyPercentile!==null&&county.metrics.poverty_percentile?.status!=='unknown'&&county.povertyPercentile>=povertyPercentile))
      &&(lowIncomePercentile===null||(county.lowIncomePercentile!==null&&county.metrics.low_income_percentile?.status!=='unknown'&&county.lowIncomePercentile>=lowIncomePercentile));
  });
}
