import { describe, expect, it, vi } from 'vitest';
import type { FeatureCollection } from 'geojson';
import type { Map as LibreMap } from 'maplibre-gl';
import { gzipSync } from 'node:zlib';
import { BoundaryDetails, LAND_ZOOM, validBoundaryDetail, validLandTile, visibleBoundaryStates, visibleLandTiles } from './boundaryContext';

const polygon = { type: 'Polygon' as const, coordinates: [[[-106, 30], [-94, 30], [-94, 36], [-106, 36], [-106, 30]]] };
const states: FeatureCollection = { type: 'FeatureCollection', features: [
  { type: 'Feature', id: '48', geometry: polygon, properties: { detail_bounds: [[-106, 26, -94, 36]] } },
  { type: 'Feature', id: '02', geometry: polygon, properties: { detail_bounds: [[-170, 51, -130, 72], [172, 50, 179, 54]] } },
] };
const detail: FeatureCollection = { type: 'FeatureCollection', features: [
  { type: 'Feature', id: '48', geometry: polygon, properties: { kind: 'state', fips: '48' } },
] };
function mapFixture() {
  const sources = new Map<string, { setData: ReturnType<typeof vi.fn> }>([['context-states', { setData: vi.fn() }]]);
  const layers = new Set(['context-state-lines', 'context-national-lines', 'context-state-fill', 'context-shoreline']);
  // Border detail loads from zoom 6; land tiles only from LAND_ZOOM (9), tested separately.
  let zoom = 8;
  const options = vi.fn();
  const map = { getSource: (id: string) => sources.get(id), getLayer: (id: string) => layers.has(id),
    addSource: (id: string, data: unknown) => { options(id, data); sources.set(id, { setData: vi.fn() }); },
    addLayer: (layer: { id: string }) => layers.add(layer.id), setFilter: vi.fn(),
    getStyle: () => ({ layers: [{ id: 'candidate-fill' }] }), getZoom: () => zoom,
    getBounds: () => ({ getWest: () => -102, getEast: () => -99, getSouth: () => 31, getNorth: () => 34 }),
  };
  return { map: map as unknown as LibreMap, sources, options, operations: map, setZoom: (value: number) => { zoom = value; } };
}

describe('authoritative boundary loading', () => {
  it('loads no detail at national zoom and limits detail by actual component bounds', () => {
    expect(visibleBoundaryStates(states, [-125, 24, -66, 50], 4)).toEqual([]);
    expect(visibleBoundaryStates(states, [-102, 31, -99, 34], 9)).toEqual(['48']);
    expect(visibleBoundaryStates(states, [173, 51, 185, 55], 9)).toEqual(['02']);
    expect(visibleBoundaryStates(states, [-188, 51, -175, 55], 9)).toEqual(['02']);
  });
  it('rejects mismatched state IDs, missing geometry and fabricated point borders', () => {
    expect(validBoundaryDetail(detail, '48')).toBe(true);
    expect(validBoundaryDetail(detail, '02')).toBe(false);
    // Seaward limits are no longer drawn, so a state with no land or river border (Hawaii) has none.
    expect(validBoundaryDetail({ type: 'FeatureCollection', features: [] }, '15')).toBe(true);
    expect(validBoundaryDetail({ type: 'FeatureCollection', features: [{ type: 'Feature', geometry: { type: 'MultiLineString', coordinates: [[[-106, 31], [-104, 32]]] },
      properties: { kind: 'state', fips: '48' } }] }, '48')).toBe(true);
    expect(validBoundaryDetail({ ...detail, features: [{ ...detail.features[0], geometry: null }] }, '48')).toBe(false);
    expect(validBoundaryDetail({ ...detail, features: [{ ...detail.features[0], geometry: { type: 'Point' } }] }, '48')).toBe(false);
  });
  it('retains source coordinates, reuses cache and disables browser simplification', async () => {
    const fixture = mapFixture(); const status = vi.fn();
    const fetcher = vi.fn().mockResolvedValue({ ok: true, json: async () => detail });
    const controller = new BoundaryDetails(fixture.map, states, '/locator/', status, fetcher);
    controller.refresh();
    await vi.waitFor(() => expect(fixture.sources.get('context-boundary-detail')!.setData).toHaveBeenLastCalledWith(detail));
    expect(fetcher).toHaveBeenCalledWith('/locator/map/detail/48.geojson', expect.anything());
    expect(fixture.options).toHaveBeenCalledWith('context-boundary-detail', expect.objectContaining({ tolerance: 0, maxzoom: 18 }));
    controller.refresh(); expect(fetcher).toHaveBeenCalledTimes(1);
    fixture.setZoom(4); controller.refresh();
    expect(fixture.sources.get('context-boundary-detail')!.setData).toHaveBeenLastCalledWith({ type: 'FeatureCollection', features: [] });
    fixture.setZoom(8); controller.refresh(); expect(fetcher).toHaveBeenCalledTimes(1);
    controller.dispose();
  });
  it('calls the global fetch with a valid receiver when no fetcher is injected', async () => {
    const fixture = mapFixture(); const status = vi.fn(); const calls: string[] = [];
    // Browsers throw "Illegal invocation" unless fetch is called unbound or on the global object.
    vi.stubGlobal('fetch', function (this: unknown, input: RequestInfo | URL) {
      if (this !== undefined && this !== globalThis) throw new TypeError('Illegal invocation');
      calls.push(String(input));
      return Promise.resolve({ ok: true, json: async () => detail } as Response);
    });
    try {
      const controller = new BoundaryDetails(fixture.map, states, '/', status);
      controller.refresh();
      await vi.waitFor(() => expect(fixture.sources.get('context-boundary-detail')!.setData).toHaveBeenLastCalledWith(detail));
      expect(calls).toEqual(['/map/detail/48.geojson']);
      expect(status).toHaveBeenLastCalledWith(null);
      controller.dispose();
    } finally { vi.unstubAllGlobals(); }
  });
  it('keeps overview visible and explicitly reports a failed detail load; retry works', async () => {
    const fixture = mapFixture(); const status = vi.fn();
    const fetcher = vi.fn().mockResolvedValueOnce({ ok: false }).mockResolvedValue({ ok: true, json: async () => detail });
    const controller = new BoundaryDetails(fixture.map, states, '/', status, fetcher);
    controller.refresh();
    await vi.waitFor(() => expect(status).toHaveBeenLastCalledWith(expect.stringContaining('overview shown')));
    expect(fixture.operations.setFilter).toHaveBeenCalledWith('context-state-lines', ['!', ['in', ['get', 'fips'], ['literal', []]]]);
    controller.retry();
    await vi.waitFor(() => expect(fixture.sources.get('context-boundary-detail')!.setData).toHaveBeenLastCalledWith(detail));
    expect(fetcher).toHaveBeenCalledTimes(2); controller.dispose();
  });
  it('cancels obsolete viewport fetches without reporting an error', async () => {
    const fixture = mapFixture(); const status = vi.fn();
    const fetcher = vi.fn().mockImplementation((_url: string, options: RequestInit) => new Promise((_resolve, reject) => {
      options.signal?.addEventListener('abort', () => reject(new DOMException('Abort', 'AbortError')));
    }));
    const controller = new BoundaryDetails(fixture.map, states, '/', status, fetcher);
    controller.refresh(); fixture.setZoom(4); controller.refresh();
    await Promise.resolve();
    expect(fetcher.mock.calls[0][1].signal.aborted).toBe(true);
    expect(status).toHaveBeenLastCalledWith(null); controller.dispose();
  });
  it('selects published land tiles only at city zoom and inside the viewport', () => {
    const index = { tile_degrees: 1, tiles: { '-102_31': [-102, 31, -101, 32] as [number, number, number, number],
      '-100_33': [-100, 33, -99, 34] as [number, number, number, number], '-90_40': [-90, 40, -89, 41] as [number, number, number, number] } };
    expect(visibleLandTiles(index, [-102, 31, -99, 34], LAND_ZOOM - 0.5)).toEqual([]);
    expect(visibleLandTiles(index, [-102, 31, -99, 34], LAND_ZOOM)).toEqual(['-100_33', '-102_31']);
    expect(visibleLandTiles(null, [-102, 31, -99, 34], 12)).toEqual([]);
  });
  it('accepts only land polygons and shoreline lines of the requested tile', () => {
    const land = { type: 'Feature', geometry: polygon, properties: { kind: 'land', tile: '-106_30' } };
    const shore = { type: 'Feature', geometry: { type: 'MultiLineString', coordinates: [[[-106, 30], [-105, 31]]] }, properties: { kind: 'shore', tile: '-106_30' } };
    expect(validLandTile({ type: 'FeatureCollection', features: [land, shore] }, '-106_30')).toBe(true);
    expect(validLandTile({ type: 'FeatureCollection', features: [land] }, '-105_30')).toBe(false);
    expect(validLandTile({ type: 'FeatureCollection', features: [{ ...land, properties: { kind: 'water', tile: '-106_30' } }] }, '-106_30')).toBe(false);
    expect(validLandTile({ type: 'FeatureCollection', features: [{ ...shore, geometry: polygon }] }, '-106_30')).toBe(false);
    expect(validLandTile({ type: 'FeatureCollection', features: [] }, '-106_30')).toBe(false);
  });
  it('loads compressed land tiles and hides exactly the generalized pieces they replace', async () => {
    const fixture = mapFixture(); const status = vi.fn();
    const tile = (id: string) => ({ type: 'FeatureCollection', features: [{ type: 'Feature', geometry: polygon, properties: { kind: 'land', tile: id } }] });
    const bytes = (value: unknown) => {
      const text = new TextEncoder().encode(JSON.stringify(value));
      // Browsers decompress via DecompressionStream; plain JSON is accepted when a server already decoded it.
      return typeof DecompressionStream === 'undefined' ? text : new Uint8Array(gzipSync(text));
    };
    const index = { tile_degrees: 1, tiles: { '-102_31': [-102, 31, -101, 32], '-90_40': [-90, 40, -89, 41] } };
    const fetcher = vi.fn().mockImplementation(async (url: string) => {
      if (url.endsWith('/map/land/index.json')) return { ok: true, json: async () => index };
      if (url.endsWith('/map/land/-102_31.geojson.gz')) return { ok: true, arrayBuffer: async () => bytes(tile('-102_31')).buffer };
      return { ok: true, json: async () => detail };
    });
    const controller = new BoundaryDetails(fixture.map, states, '/', status, fetcher);
    fixture.setZoom(LAND_ZOOM); controller.refresh();
    await vi.waitFor(() => expect(fixture.sources.get('context-land-detail')!.setData).toHaveBeenLastCalledWith(tile('-102_31')));
    expect(fetcher).not.toHaveBeenCalledWith('/map/land/-90_40.geojson.gz', expect.anything());
    const hidden = ['!', ['in', ['coalesce', ['get', 'tile'], ''], ['literal', ['-102_31']]]];
    expect(fixture.operations.setFilter).toHaveBeenCalledWith('context-state-fill', hidden);
    expect(fixture.operations.setFilter).toHaveBeenCalledWith('context-shoreline', hidden);
    await vi.waitFor(() => expect(status).toHaveBeenLastCalledWith(null));
    controller.dispose();
  });
});
