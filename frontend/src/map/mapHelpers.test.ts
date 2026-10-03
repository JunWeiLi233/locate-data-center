import { describe, expect, it, vi } from 'vitest';
import type { Geometry, Polygon } from 'geojson';
import type { Map as LibreMap } from 'maplibre-gl';
import type { CandidateRegion, LayerData, MapCamera } from '../types/domain';
import { geometryBounds, initialMapView, polygonGeometry, regionCoordinate, selectionViewport, US_CAMERA, validCoordinate, viewportPadding } from './geometry';
import { candidatePayloads, layerPayload, overlapRegions, selectedLayerIds, statusColor } from './mapData';
import { CANDIDATE_SOURCE, BADGE_SOURCE, SELECTED_BADGE_SOURCE, indicatorColor, syncCandidates, syncIndicators } from './mapStyle';

const polygon: Polygon = { type: 'Polygon', coordinates: [[[-106, 35], [-105, 35], [-105, 36], [-106, 36], [-106, 35]]] };
function region(patch: Partial<CandidateRegion> = {}): CandidateRegion {
  return { id: 'region-a', label: 'Backend region', rank: 1, rankBasis: 'Representative alternative', score: 0.6,
    regionMeanScore: 0.5, paretoOptimal: false, centroid: { lon: -105.5, lat: 35.5 }, geometry: polygon, geometryWarning: null,
    screeningStatus: 'CONDITIONAL', designId: 'dry', scenarioId: 'current', factors: [], metrics: [], verificationRequired: [],
    uncertainties: [], strengths: [], limitations: [], dataQuality: 'partial', sensitivity: null, ...patch };
}
function layer(patch: Partial<LayerData> = {}): LayerData {
  return { id: 'water', label: 'Water stress', unit: 'index', min: 0, max: 5, direction: 'higher_is_worse', source: 'Backend source',
    warning: null, valueProperty: 'stress', statusProperty: 'status', data: { type: 'FeatureCollection', features: [
      { type: 'Feature', id: 'cell-a', geometry: polygon, properties: { stress: 4, status: 'observed' } },
    ] }, ...patch };
}
function mockMap() {
  const sources = new Map<string, { setData: ReturnType<typeof vi.fn> }>();
  const layers = new Set<string>();
  const map = {
    getSource: (id: string) => sources.get(id),
    addSource: (id: string) => sources.set(id, { setData: vi.fn() }),
    hasImage: () => true,
    getLayer: (id: string) => layers.has(id),
    addLayer: (data: { id: string }) => layers.add(data.id),
    setLayoutProperty: vi.fn(), setFilter: vi.fn(), setPaintProperty: vi.fn(),
    getStyle: () => ({ sources: Object.fromEntries(sources) }),
    removeLayer: (id: string) => layers.delete(id), removeSource: (id: string) => sources.delete(id),
  };
  return { map: map as unknown as LibreMap, sources, operations: map };
}

describe('geographic map boundaries', () => {
  it('keeps initial national fit intent after pre-load map events publish a camera', () => {
    const props: { camera: MapCamera | undefined; selectedId: string | null } = { camera: undefined, selectedId: null };
    const initialView = initialMapView(props.camera, props.selectedId);
    props.camera = { ...US_CAMERA };
    expect(initialView.fitUS).toBe(true);
    expect(initialView.camera).toEqual(US_CAMERA);
  });
  it('preserves explicitly restored cameras and defers initial selected regions to their own fit', () => {
    const camera = { longitude: -83, latitude: 32, zoom: 7 };
    const restored = initialMapView(camera, null);
    camera.zoom = 3.5;
    expect(restored).toEqual({ camera: { longitude: -83, latitude: 32, zoom: 7 }, fitUS: false });
    expect(initialMapView(undefined, 'region-a').fitUS).toBe(false);
  });
  it('fits selected geography above a mobile sheet and clamps unusable viewport padding', () => {
    const container = { top: 60, bottom: 760, left: 0, right: 390, height: 700, width: 390 };
    expect(viewportPadding(container, { top: 122, bottom: 420, left: 0, right: 390 })).toEqual({ top: 86, bottom: 364, left: 24, right: 24 });
    const padding = viewportPadding(container, { top: 122, bottom: 80, left: 0, right: 390 });
    expect(padding.top + padding.bottom).toBeLessThanOrEqual(container.height - 80);
  });
  it('uses longitude/latitude and rejects swapped, missing and non-finite coordinates', () => {
    expect(validCoordinate([-105.5, 35.5])).toBe(true);
    expect(validCoordinate([35.5, -105.5])).toBe(false);
    for (const coordinate of [null, [], [NaN, 35], [0, Infinity], [-181, 0], [0, 91]]) expect(validCoordinate(coordinate)).toBe(false);
    expect(regionCoordinate(region())).toEqual([-105.5, 35.5]);
    expect(regionCoordinate(region({ centroid: null }))).toBeNull();
  });
  it('fits the full Polygon and MultiPolygon including separated parts', () => {
    expect(geometryBounds(polygon)).toEqual([[-106, 35], [-105, 36]]);
    expect(geometryBounds({ type: 'MultiPolygon', coordinates: [polygon.coordinates,
      [[[-102, 34], [-101, 34], [-101, 35], [-102, 35], [-102, 34]]]] })).toEqual([[-106, 34], [-101, 36]]);
    expect(selectionViewport(region({ centroid: null }))).toEqual({ bounds: [[-106, 35], [-105, 36]] });
  });
  it('rejects malformed, unclosed and degenerate areas without inventing a coordinate', () => {
    const invalid: Geometry[] = [
      { type: 'Polygon', coordinates: [] }, { type: 'MultiPolygon', coordinates: [] },
      { type: 'Polygon', coordinates: [[[-106, 35], [-105, 35], [-105, 36]]] },
      { type: 'Polygon', coordinates: [[[0, 0], [1, 0], [2, 0], [0, 0]]] },
      { type: 'Polygon', coordinates: [[[1800, 0], [1, 0], [1, 1], [1800, 0]]] },
      { type: 'Point', coordinates: [-105, 35] }, { type: 'MultiPolygon' } as Geometry,
    ];
    for (const geometry of invalid) {
      expect(polygonGeometry(geometry)).toBeNull();
      expect(geometryBounds(geometry)).toBeNull();
      expect(selectionViewport(region({ geometry, centroid: null }))).toBeNull();
    }
    expect(selectionViewport(region({ geometry: null }))).toEqual({ center: [-105.5, 35.5] });
  });
});

describe('candidate payloads', () => {
  it('never creates initial candidates and uses backend IDs, geometry and centroids', () => {
    expect(candidatePayloads([], null).areas.features).toEqual([]);
    const payload = candidatePayloads([region()], null);
    expect(payload.areas.features[0].id).toBe('region-a');
    expect(payload.areas.features[0].geometry).toBe(polygon);
    expect(payload.badges.features[0].geometry.coordinates).toEqual([-105.5, 35.5]);
    expect(payload.areas.features[0].properties?.selected).toBe(false);
    expect(candidatePayloads([region()], 'region-a').areas.features[0].properties?.selected).toBe(true);
  });
  it('limits rank badges to actual top 20 ranks and the selected result', () => {
    const payload = candidatePayloads([
      region({ id: 'one', rank: 1 }), region({ id: 'twenty', rank: 20 }), region({ id: 'twenty-one', rank: 21 }),
      region({ id: 'selected', rank: 30 }), region({ id: 'unknown', rank: null }), region({ id: 'no-centroid', centroid: null }),
    ], 'selected');
    expect(payload.badges.features.map((feature) => feature.id)).toEqual(['one', 'twenty', 'selected']);
    expect(candidatePayloads([region({ geometry: null, centroid: null })], 'region-a').areas.features).toEqual([]);
  });
  it('retains every identical cooling region as a selectable alternative', () => {
    const cooling = region({ id: 'region-b', rank: 2, designId: 'hybrid' });
    const distant = region({ id: 'region-c', geometry: null, centroid: { lon: -80, lat: 35 } });
    expect(overlapRegions([cooling, distant, region()], ['region-a']).map((item) => item.id)).toEqual(['region-a', 'region-b']);
    expect(overlapRegions([region(), cooling], []).length).toBe(0);
    const payload = candidatePayloads([region(), cooling], 'region-b');
    expect(payload.areas.features.length).toBe(2);
    expect(payload.badges.features.length).toBe(2);
  });
  it('preserves screening statuses and unknown gray', () => {
    expect(statusColor('PASS')).toBe('#167d84'); expect(statusColor('CONDITIONAL')).toBe('#b88932');
    expect(statusColor('FAIL')).toBe('#b35c58'); expect(statusColor('UNKNOWN')).toBe('#818b94');
    expect(statusColor('unrecognized')).toBe(statusColor('UNKNOWN'));
  });
  it('changes selection without resending candidate polygon or base badge data', () => {
    const { map, sources, operations } = mockMap();
    const regions = [region(), region({ id: 'region-b', rank: 2 })];
    syncCandidates(map, regions, null, true);
    syncCandidates(map, regions, 'region-b', true);
    syncCandidates(map, regions, 'region-a', false);
    expect(sources.get(CANDIDATE_SOURCE)?.setData).not.toHaveBeenCalled();
    expect(sources.get(BADGE_SOURCE)?.setData).not.toHaveBeenCalled();
    expect(sources.get(SELECTED_BADGE_SOURCE)?.setData).toHaveBeenCalledTimes(2);
    expect(operations.setFilter).toHaveBeenCalledWith('candidate-selected', ['==', ['get', 'regionId'], 'region-a']);
    expect(operations.setLayoutProperty).toHaveBeenCalledWith('candidate-fill', 'visibility', 'none');
    syncCandidates(map, [...regions], 'region-a', false);
    expect(sources.get(CANDIDATE_SOURCE)?.setData).toHaveBeenCalledTimes(1);
  });
});

describe('indicator updates', () => {
  it('keeps stable source feature IDs across payload updates and retains raw values', () => {
    const first = layerPayload(layer());
    const second = layerPayload(layer({ data: { type: 'FeatureCollection', features: [
      { type: 'Feature', id: 'cell-a', geometry: polygon, properties: { stress: 2, status: 'calculated' } },
    ] } }));
    expect(first.features[0].id).toBe(second.features[0].id);
    expect(first.features[0].properties?._value).toBe(4);
    expect(second.features[0].properties?._value).toBe(2);
    expect(second.features[0].properties?._status).toBe('calculated');
  });
  it('keeps missing numbers null and distinguishes duplicate alternative IDs', () => {
    const data = layerPayload(layer({ data: { type: 'FeatureCollection', features: [
      { type: 'Feature', id: 'cell-a', geometry: polygon, properties: { stress: null, status: 'unknown' } },
      { type: 'Feature', id: 'cell-a', geometry: polygon, properties: { stress: Infinity } },
    ] } }));
    expect(new Set(data.features.map((feature) => feature.id)).size).toBe(2);
    expect(data.features.every((feature) => feature.properties?._value === null)).toBe(true);
    expect(data.features.every((feature) => feature.properties?._status === 'unknown')).toBe(true);
  });
  it('uses the same raw quantitative scale for both directions without browser risk inversion', () => {
    expect(indicatorColor(layer())).toEqual(indicatorColor(layer({ direction: 'higher_is_better' })));
    expect(selectedLayerIds([{ id: 'water', enabled: true }, { id: 'climate', enabled: false }])).toEqual(new Set(['water']));
  });
  it('toggles cached indicators without resending GeoJSON, and replaces a changed sublayer', () => {
    const { map, sources } = mockMap();
    const water = layer();
    syncIndicators(map, [water], new Set(['water']));
    syncIndicators(map, [water], new Set());
    syncIndicators(map, [water], new Set(['water']));
    expect(sources.get('indicator-source-water')?.setData).not.toHaveBeenCalled();
    syncIndicators(map, [layer({ label: 'Different water sublayer' })], new Set(['water']));
    expect(sources.get('indicator-source-water')?.setData).toHaveBeenCalledTimes(1);
  });
});
