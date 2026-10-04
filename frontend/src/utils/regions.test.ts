import { describe, expect, it } from 'vitest';
import type { Polygon } from 'geojson';
import type { CandidateRegion, Metric } from '../types/domain';
import { prominentRegions } from '../map/mapData';
import { coolingName, groupPlaces, keyMetrics, placeAlternatives, placeNameSuffixes, regionName, shortCooling, spansLabel, verificationItem } from './regions';

const square = (x: number): Polygon => ({ type: 'Polygon', coordinates: [[[x, 35], [x + 1, 35], [x + 1, 36], [x, 36], [x, 35]]] });
function region(patch: Partial<CandidateRegion> = {}): CandidateRegion {
  return { id: 'a', label: 'Search region a', rank: 1, rankBasis: 'Representative alternative', score: 90, regionMeanScore: 88,
    paretoOptimal: null, centroid: { lon: -105.5, lat: 35.5 }, geometry: square(-106), geometryWarning: null, screeningStatus: 'CONDITIONAL',
    designId: 'air_dry_assumed', scenarioId: 'current', factors: [], metrics: [], verificationRequired: [], uncertainties: [],
    strengths: [], limitations: [], dataQuality: 'Unknown', sensitivity: null, ...patch };
}
const metric = (id: string, group = 'water'): Metric => ({ id, label: id, value: 1, unit: '', group, status: 'calculated', confidence: 'low', missingReason: null, sources: [] });

describe('place presentation', () => {
  it('groups cooling alternatives that share one search geometry without changing backend ranks', () => {
    const groups = groupPlaces([
      region({ id: 'cold-a', rank: 88, designId: 'cold_plate_tower_assumed' }), region({ id: 'b', rank: 3, geometry: square(-80), centroid: { lon: -79.5, lat: 35.5 } }), region(),
      region({ id: 'no-geometry', rank: 5, geometry: null, centroid: null }),
    ]);
    expect(groups.map(group => group.primary.id)).toEqual(['a', 'b', 'no-geometry']);
    expect(groups[0].alternatives.map(item => [item.id, item.rank])).toEqual([['a', 1], ['cold-a', 88]]);
    expect(groups[2].alternatives).toHaveLength(1);
    expect(placeAlternatives(region({ id: 'cold-a', rank: 88 }), [region(), region({ id: 'cold-a', rank: 88 })]).map(item => item.id)).toEqual(['a', 'cold-a']);
  });
  it('numbers only the best alternative of the top places at national zoom', () => {
    const regions = Array.from({ length: 12 }, (_, index) => region({ id: `place-${index}`, rank: index * 2 + 1, geometry: square(-120 + index * 2), centroid: { lon: -119.5 + index * 2, lat: 35.5 } }));
    regions.push(region({ id: 'place-0-cold', rank: 2, geometry: square(-120), centroid: { lon: -119.5, lat: 35.5 } }));
    const prominent = prominentRegions(regions);
    expect(prominent.size).toBe(10);
    expect(prominent.has('place-0')).toBe(true);
    expect(prominent.has('place-0-cold')).toBe(false);
    expect(prominent.has('place-9')).toBe(true);
    expect(prominent.has('place-10')).toBe(false);
  });
  it('prefers geography-table place names and keeps the backend label otherwise', () => {
    expect(regionName(region({ placeLabel: 'Trinity, CA' }))).toBe('Trinity, CA');
    expect(regionName(region())).toBe('Search region a');
    expect(spansLabel(region({ regionStates: ['WA', 'CA', 'OR', 'ID', 'MT'] }))).toBe('Spans WA, CA, OR +2');
    expect(spansLabel(region({ regionStates: ['UT'] }))).toBeNull();
    expect(spansLabel(region())).toBeNull();
  });
  it('uses declared cooling labels and readable requirement names', () => {
    const options = [{ id: 'air_dry_assumed', label: 'Air / dry cooling assumption' }];
    expect(coolingName('air_dry_assumed', options)).toBe('Air / dry cooling assumption');
    expect(coolingName('cold_plate_tower_assumed', options)).toBe('Direct-to-chip / tower (assumed)'); // known design without a declared label
    expect(coolingName('immersion_assumed', options)).toBe('Immersion assumed');
    expect(shortCooling('Air / dry cooling assumption')).toBe('Air / dry cooling');
    expect(shortCooling('Cold plate / tower (assumed)')).toBe('Cold plate / tower');
    expect(verificationItem('utility_capacity: Required peak facility demand is unverified')).toEqual({ title: 'Utility capacity', detail: 'Required peak facility demand is unverified' });
    expect(verificationItem('Local zoning')).toEqual({ title: 'Local zoning', detail: null });
  });
  it('shows headline physical quantities and never verification placeholders as key figures', () => {
    const real = ['w_site_m3', 'e_facility_mwh', 'pue', 'c_electricity_tonnes', 'baseline_water_stress_score', 'transmission_distance_km', 'grid_carbon_intensity_kg_per_mwh'].map(id => metric(id));
    real.push(metric('transmission_distance_km', 'verification'), metric('baseline_water_stress_score', 'verification'));
    expect(keyMetrics(real).map(item => item.id)).toEqual(['e_facility_mwh', 'c_electricity_tonnes', 'w_site_m3', 'grid_carbon_intensity_kg_per_mwh', 'transmission_distance_km', 'baseline_water_stress_score']);
    const other = [metric('parcel', 'verification'), metric('energy', 'Energy'), metric('water', 'Water')];
    expect(keyMetrics(other).map(item => item.id)).toEqual(['energy', 'water']);
  });
});

describe('repeated place names', () => {
  it('numbers later places that share a county name without splitting the cooling variants of one place', () => {
    const first = region({ id: 'a', placeLabel: 'Livingston, NY', rank: 1 });
    const firstTower = region({ id: 'a2', placeLabel: 'Livingston, NY', rank: 4, designId: 'cold_plate_tower_assumed' });
    const other = region({ id: 'b', placeLabel: 'Wyoming, NY', rank: 2, geometry: square(-104) });
    const second = region({ id: 'c', placeLabel: 'Livingston, NY', rank: 5, geometry: square(-102) });
    const suffixes = placeNameSuffixes([second, other, firstTower, first]);
    const names = groupPlaces([first, firstTower, other, second]).map(group => regionName(group.primary) + (suffixes.get(group.key) ?? ''));
    expect(names).toEqual(['Livingston, NY', 'Wyoming, NY', 'Livingston, NY · area 2']);
  });
});
