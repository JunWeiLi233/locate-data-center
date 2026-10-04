import type { FeatureCollection, Feature, Geometry } from 'geojson';
import type { Map as LibreMap, GeoJSONSource } from 'maplibre-gl';

export const DETAIL_ZOOM = 6;
/** Detailed land and shoreline (TIGER land minus AREAWATER) replace the generalized backdrop. */
export const LAND_ZOOM = 9;
const EMPTY: FeatureCollection = { type: 'FeatureCollection', features: [] };
const LINES = ['LineString', 'MultiLineString'];
const AREAS = ['Polygon', 'MultiPolygon'];
type Box = [number, number, number, number];
export interface LandIndex { tile_degrees: number; tiles: Record<string, Box> }

function wrappedBoxes(bounds: Box): Box[] {
  const [west, south, east, north] = bounds;
  const width = east - west;
  const start = ((west + 180) % 360 + 360) % 360 - 180;
  return width >= 360 ? [[-180, south, 180, north]] : start + width <= 180
    ? [[start, south, start + width, north]] : [[start, south, 180, north], [-180, south, start + width - 360, north]];
}

const intersects = (a: Box, b: Box) => a[0] <= b[2] && a[2] >= b[0] && a[1] <= b[3] && a[3] >= b[1];

export function visibleBoundaryStates(states: FeatureCollection, bounds: Box, zoom: number): string[] {
  if (zoom < DETAIL_ZOOM) return [];
  const boxes = wrappedBoxes(bounds);
  return states.features.filter(feature => {
    const parts = feature.properties?.detail_bounds as Box[] | undefined;
    return parts?.some(part => boxes.some(box => intersects(part, box)));
  }).map(feature => String(feature.id)).sort();
}

/** Published 1-degree land tiles intersecting the viewport; none below LAND_ZOOM. */
export function visibleLandTiles(index: LandIndex | null, bounds: Box, zoom: number): string[] {
  if (!index || zoom < LAND_ZOOM) return [];
  const boxes = wrappedBoxes(bounds);
  return Object.entries(index.tiles).filter(([, box]) => boxes.some(view => intersects(box, view))).map(([id]) => id).sort();
}

export function validBoundaryDetail(value: unknown, id: string): value is FeatureCollection {
  if (!value || typeof value !== 'object') return false;
  const data = value as FeatureCollection;
  // A state without land or river borders (Hawaii) has an empty collection.
  if (data.type !== 'FeatureCollection' || !Array.isArray(data.features) || data.features.length > 2) return false;
  return data.features.every((feature: Feature<Geometry>) => feature.type === 'Feature' && feature.properties?.fips === id
    && ((feature.properties.kind === 'state' && [...AREAS, ...LINES].includes(feature.geometry?.type))
      || (feature.properties.kind === 'national' && [...LINES, 'GeometryCollection'].includes(feature.geometry?.type))));
}

export function validLandTile(value: unknown, id: string): value is FeatureCollection {
  if (!value || typeof value !== 'object') return false;
  const data = value as FeatureCollection;
  if (data.type !== 'FeatureCollection' || !Array.isArray(data.features) || data.features.length < 1 || data.features.length > 2) return false;
  return data.features.every((feature: Feature<Geometry>) => feature.type === 'Feature' && feature.properties?.tile === id
    && ((feature.properties.kind === 'land' && AREAS.includes(feature.geometry?.type))
      || (feature.properties.kind === 'shore' && LINES.includes(feature.geometry?.type))));
}

/** Viewport-scoped cache: at most `limit` non-visible payloads are retained. */
class PayloadCache {
  private cache = new Map<string, FeatureCollection>();
  private pending = new Map<string, AbortController>();
  failed = new Set<string>();
  needed: string[] = [];
  constructor(private limit: number) {}
  has(id: string) { return this.cache.has(id); }
  get(id: string) { return this.cache.get(id)!; }
  loaded() { return this.needed.filter(id => this.cache.has(id)); }
  busy() { return this.needed.some(id => this.pending.has(id)); }
  broken() { return this.needed.some(id => this.failed.has(id)); }
  update(needed: string[], load: (id: string, signal: AbortSignal) => Promise<FeatureCollection>, done: () => void) {
    this.needed = needed;
    for (const [id, abort] of this.pending) if (!needed.includes(id)) { abort.abort(); this.pending.delete(id); }
    for (const id of needed) {
      if (this.cache.has(id) || this.pending.has(id) || this.failed.has(id)) continue;
      const abort = new AbortController();
      this.pending.set(id, abort);
      void load(id, abort.signal)
        .then(data => {
          if (abort.signal.aborted) return;
          this.cache.set(id, data);
          for (const key of this.cache.keys()) {
            if (this.cache.size <= Math.max(this.limit, this.needed.length)) break;
            if (!this.needed.includes(key)) this.cache.delete(key);
          }
        })
        .catch(() => { if (!abort.signal.aborted) this.failed.add(id); })
        .finally(() => { if (!abort.signal.aborted) { this.pending.delete(id); done(); } });
    }
  }
  abort() { for (const abort of this.pending.values()) abort.abort(); this.pending.clear(); this.cache.clear(); }
}

/** Viewport-scoped source geometry: detailed borders per state, detailed land per tile. */
export class BoundaryDetails {
  private borders = new PayloadCache(12);
  private land = new PayloadCache(24);
  private landIndex: LandIndex | null = null;
  private landIndexState: 'idle' | 'loading' | 'ready' | 'failed' = 'idle';
  private rendered = '';
  private renderedLand = '';
  private disposed = false;
  // The default must not be the bare `fetch`: calling it as `this.fetcher(...)` makes the instance its
  // receiver, which browsers reject with "Illegal invocation" before any request is sent.
  constructor(private map: LibreMap, private states: FeatureCollection, private baseUrl: string,
    private status: (message: string | null) => void, private fetcher: typeof fetch = (input, init) => fetch(input, init)) {}

  private async json(url: string, signal?: AbortSignal): Promise<unknown> {
    const response = await this.fetcher(url, { signal });
    if (!response.ok) throw new Error('Boundary context unavailable');
    return response.json() as Promise<unknown>;
  }

  /** Land tiles are stored gzip-compressed; a server that already decoded them is also accepted. */
  private async gzipJson(url: string, signal?: AbortSignal): Promise<unknown> {
    const response = await this.fetcher(url, { signal });
    if (!response.ok) throw new Error('Land tile unavailable');
    const bytes = new Uint8Array(await response.arrayBuffer());
    if (bytes[0] !== 0x1f || bytes[1] !== 0x8b) return JSON.parse(new TextDecoder().decode(bytes)) as unknown;
    if (typeof DecompressionStream === 'undefined') throw new Error('Browser cannot decompress land tiles');
    const source = new ReadableStream<BufferSource>({ start(controller) { controller.enqueue(bytes); controller.close(); } });
    const reader = source.pipeThrough(new DecompressionStream('gzip')).getReader();
    const chunks: Uint8Array[] = [];
    for (let part = await reader.read(); !part.done; part = await reader.read()) chunks.push(part.value);
    const output = new Uint8Array(chunks.reduce((total, chunk) => total + chunk.length, 0));
    chunks.reduce((offset, chunk) => { output.set(chunk, offset); return offset + chunk.length; }, 0);
    return JSON.parse(new TextDecoder().decode(output)) as unknown;
  }

  refresh = () => {
    if (this.disposed || !this.map.getSource('context-states')) return;
    const b = this.map.getBounds();
    const bounds: Box = [b.getWest(), b.getSouth(), b.getEast(), b.getNorth()];
    const zoom = this.map.getZoom();
    this.borders.update(visibleBoundaryStates(this.states, bounds, zoom), async (id, signal) => {
      const data = await this.json(`${this.baseUrl}map/detail/${id}.geojson`, signal);
      if (!validBoundaryDetail(data, id)) throw new Error('Invalid boundary detail');
      return data;
    }, () => this.render());
    if (zoom >= LAND_ZOOM && this.landIndexState === 'idle') {
      this.landIndexState = 'loading';
      void this.json(`${this.baseUrl}map/land/index.json`)
        .then(data => {
          const index = data as LandIndex;
          if (!index || typeof index.tiles !== 'object') throw new Error('Invalid land index');
          this.landIndex = index; this.landIndexState = 'ready';
        })
        .catch(() => { this.landIndexState = 'failed'; })
        .finally(() => { if (!this.disposed) this.refresh(); });
    }
    this.land.update(visibleLandTiles(this.landIndex, bounds, zoom), async (id, signal) => {
      const data = await this.gzipJson(`${this.baseUrl}map/land/${id}.geojson.gz`, signal);
      if (!validLandTile(data, id)) throw new Error('Invalid land tile');
      return data;
    }, () => this.render());
    this.render();
  };

  retry = () => {
    this.borders.failed.clear(); this.land.failed.clear();
    if (this.landIndexState === 'failed') this.landIndexState = 'idle';
    this.refresh();
  };

  private ensureLayers(before: string | undefined) {
    if (!this.map.getSource('context-boundary-detail')) this.map.addSource('context-boundary-detail', { type: 'geojson', data: EMPTY, tolerance: 0, maxzoom: 18 });
    for (const kind of ['state', 'national']) {
      const id = `context-${kind}-detail-lines`;
      if (!this.map.getLayer(id)) this.map.addLayer({ id, type: 'line', source: 'context-boundary-detail',
        filter: ['==', ['get', 'kind'], kind], paint: { 'line-color': kind === 'national' ? '#4c737f' : '#8c9ca2',
          'line-width': kind === 'national' ? 1.4 : 0.85 } }, before);
    }
    if (!this.map.getSource('context-land-detail')) this.map.addSource('context-land-detail', { type: 'geojson', data: EMPTY, tolerance: 0, maxzoom: 18 });
    // Detailed land sits exactly where the generalized backdrop does: under forest, relief and borders.
    const landBefore = ['context-forest-canopy', 'context-relief', 'context-state-lines'].find(id => this.map.getLayer(id)) ?? before;
    if (!this.map.getLayer('context-land-detail-fill')) this.map.addLayer({ id: 'context-land-detail-fill', type: 'fill', source: 'context-land-detail',
      filter: ['==', ['get', 'kind'], 'land'], paint: { 'fill-color': '#f5f5ef', 'fill-opacity': 1 } }, landBefore);
    if (!this.map.getLayer('context-land-detail-shore')) this.map.addLayer({ id: 'context-land-detail-shore', type: 'line', source: 'context-land-detail',
      filter: ['==', ['get', 'kind'], 'shore'], paint: { 'line-color': '#a9c3cc', 'line-width': 0.7 } }, landBefore);
  }

  private render() {
    if (this.disposed || !this.map.getSource('context-states')) return;
    const before = this.map.getStyle()?.layers?.find(layer => layer.id === 'context-state-labels'
      || layer.id.startsWith('indicator-') || layer.id.startsWith('candidate-'))?.id;
    this.ensureLayers(before);
    const loaded = this.borders.loaded();
    const signature = loaded.join(',');
    if (signature !== this.rendered) {
      const data: FeatureCollection = { type: 'FeatureCollection', features: loaded.flatMap(id => this.borders.get(id).features) };
      (this.map.getSource('context-boundary-detail') as GeoJSONSource).setData(data);
      this.rendered = signature;
    }
    const tiles = this.land.loaded();
    const landSignature = tiles.join(',');
    if (landSignature !== this.renderedLand) {
      const data: FeatureCollection = { type: 'FeatureCollection', features: tiles.flatMap(id => this.land.get(id).features) };
      (this.map.getSource('context-land-detail') as GeoJSONSource).setData(data);
      this.renderedLand = landSignature;
    }
    const hide = (key: string) => ['!', ['in', ['get', key], ['literal', loaded]]];
    const lineSource = (this.map.getLayer('context-state-lines') as { source?: string } | undefined)?.source;
    this.map.setFilter('context-state-lines', (lineSource === 'context-borders'
      ? ['all', hide('fips_a'), hide('fips_b')] : hide('fips')) as Parameters<LibreMap['setFilter']>[1]);
    if (this.map.getLayer('context-national-lines')) this.map.setFilter('context-national-lines', hide('fips') as Parameters<LibreMap['setFilter']>[1]);
    const tileFilter = ['!', ['in', ['coalesce', ['get', 'tile'], ''], ['literal', tiles]]] as Parameters<LibreMap['setFilter']>[1];
    for (const id of ['context-state-fill', 'context-shoreline']) if (this.map.getLayer(id)) this.map.setFilter(id, tileFilter);
    this.status(this.borders.broken() || this.land.broken() || this.landIndexState === 'failed'
      ? 'Detailed borders or shoreline unavailable here; generalized overview shown.'
      : this.borders.busy() || this.land.busy() || this.landIndexState === 'loading' ? 'Loading detailed Census borders and shoreline…' : null);
  }

  dispose() {
    this.disposed = true;
    this.borders.abort(); this.land.abort();
  }
}
