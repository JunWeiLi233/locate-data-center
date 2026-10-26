import type { FeatureCollection, Point } from 'geojson';
import type { Map as LibreMap, GeoJSONSource, StyleSpecification, ExpressionSpecification, FilterSpecification, SymbolLayerSpecification } from 'maplibre-gl';
import type { CandidateRegion, LayerData } from '../types/domain';
import { badgeImageId, candidatePayloads, indicatorLayerIds, layerPayload, layerSourceId, statusColor } from './mapData';
import { regionCoordinate, validCoordinate } from './geometry';

export const CANDIDATE_SOURCE = 'candidate-areas';
export const BADGE_SOURCE = 'candidate-badges';
export const SELECTED_BADGE_SOURCE = 'candidate-selected-badge';
export const CANDIDATE_LAYERS = ['candidate-fill', 'candidate-outline', 'candidate-selected-fill', 'candidate-selected', 'candidate-dot', 'candidate-badge-top', 'candidate-badge', 'candidate-selected-badge'];
/** From this zoom every badge is numbered; below it only the top places are numbered and the rest are dots. */
export const BADGE_DETAIL_ZOOM = 5;
export const EMPTY_COLLECTION: FeatureCollection = { type: 'FeatureCollection', features: [] };

/**
 * Physical-geography context for the bundled basemap: shaded terrain relief and forest canopy.
 * Both come from public, keyless tile services and are cartographic context only. They are never
 * analyzed model coverage, and a failed context tile must not take the results map down.
 */
export interface BasemapVisibility { relief: boolean; forest: boolean }
/** Canopy starts off: its green reads like results. Both stay one click away in Map layers. */
export const DEFAULT_BASEMAP: BasemapVisibility = { relief: true, forest: false };
export const TERRAIN_SOURCE = 'context-terrain';
export const FOREST_SOURCE = 'context-forest';
export const CONTEXT_LAYERS: Record<keyof BasemapVisibility, string> = { relief: 'context-relief', forest: 'context-forest-canopy' };
const CONTEXT_TILE_SOURCES: ReadonlySet<string> = new Set([TERRAIN_SOURCE, FOREST_SOURCE]);
/** AWS Open Data terrain tiles (Terrarium RGB elevation; USGS 3DEP within the United States). */
const TERRAIN_TILES = 'https://elevation-tiles-prod.s3.amazonaws.com/terrarium/{z}/{x}/{y}.png';
/** USFS / NLCD tree canopy cover 2021 for CONUS, rendered by the MRLC GeoServer WMS. */
const FOREST_TILES = 'https://www.mrlc.gov/geoserver/mrlc_display/wms?service=WMS&version=1.1.1&request=GetMap'
  + '&layers=nlcd_tcc_conus_2021_v2021-4&styles=&srs=EPSG:3857&bbox={bbox-epsg-3857}&width=256&height=256'
  + '&format=image/png&transparent=true';

/** True when a map error comes from an optional context tile source rather than from results. */
export function isContextSourceError(event: { sourceId?: unknown }): boolean {
  return typeof event.sourceId === 'string' && CONTEXT_TILE_SOURCES.has(event.sourceId);
}

const candidateCache = new WeakMap<LibreMap, { regions: CandidateRegion[]; selected: CandidateRegion | undefined }>();
const indicatorCache = new WeakMap<LibreMap, Map<string, LayerData>>();
const contextCache = new WeakMap<LibreMap, Map<string, FeatureCollection>>();

export function neutralStyle(): StyleSpecification {
  return { version: 8, sources: {}, layers: [{ id: 'neutral-background', type: 'background', paint: { 'background-color': '#d6e4ee' } }] };
}

function sourceData(map: LibreMap, id: string, data: FeatureCollection, attribution?: string): void {
  const existing = map.getSource(id) as GeoJSONSource | undefined;
  if (existing) existing.setData(data);
  else map.addSource(id, { type: 'geojson', data, attribution });
}

function textImage(text: string, kind: 'state' | 'badge', color = '#2457d6', selected = false): ImageData | null {
  const canvas = document.createElement('canvas');
  const ratio = 2;
  canvas.width = (kind === 'state' ? 160 : 38) * ratio;
  canvas.height = (kind === 'state' ? 24 : 38) * ratio;
  const context = canvas.getContext('2d');
  if (!context) return null;
  context.scale(ratio, ratio);
  if (kind === 'badge') {
    context.beginPath(); context.arc(19, 19, selected ? 17 : 15, 0, Math.PI * 2);
    context.fillStyle = selected ? '#2457d6' : '#ffffff'; context.fill();
    context.lineWidth = selected ? 3 : 2; context.strokeStyle = selected ? '#ffffff' : color; context.stroke();
    context.fillStyle = selected ? '#ffffff' : '#12161c';
    context.font = '600 13px Arial, sans-serif';
  } else {
    context.fillStyle = '#5b6472'; context.font = '11px Arial, sans-serif';
  }
  context.textAlign = 'center'; context.textBaseline = 'middle';
  context.fillText(text, canvas.width / ratio / 2, canvas.height / ratio / 2, canvas.width / ratio - 8);
  return context.getImageData(0, 0, canvas.width, canvas.height);
}

/** Lowest results layer (indicator or candidate), so basemap context is always drawn beneath model output. */
function firstResultLayer(map: LibreMap): string | undefined {
  const ordered = map.getStyle()?.layers?.find((layer) => layer.id.startsWith('indicator-') || layer.id.startsWith('candidate-'));
  return ordered?.id ?? (map.getLayer('candidate-fill') ? 'candidate-fill' : undefined);
}

function addPhysicalContext(map: LibreMap, before: string | undefined, basemap: BasemapVisibility): void {
  if (!map.getSource(FOREST_SOURCE)) map.addSource(FOREST_SOURCE, {
    type: 'raster', tiles: [FOREST_TILES], tileSize: 256, minzoom: 2, maxzoom: 14, bounds: [-125.0, 24.0, -66.5, 49.6],
    attribution: '<a href="https://data.fs.usda.gov/geodata/rastergateway/treecanopycover/" target="_blank" rel="noopener">USFS tree canopy 2021 · MRLC</a>',
  });
  if (!map.getSource(TERRAIN_SOURCE)) map.addSource(TERRAIN_SOURCE, {
    type: 'raster-dem', tiles: [TERRAIN_TILES], tileSize: 256, maxzoom: 12, encoding: 'terrarium',
    attribution: '<a href="https://registry.opendata.aws/terrain-tiles/" target="_blank" rel="noopener">Terrain Tiles · USGS 3DEP, SRTM, GMTED2010, ETOPO1</a>',
  });
  if (!map.getLayer(CONTEXT_LAYERS.forest)) map.addLayer({ id: CONTEXT_LAYERS.forest, type: 'raster', source: FOREST_SOURCE,
    layout: { visibility: basemap.forest ? 'visible' : 'none' },
    paint: { 'raster-opacity': ['interpolate', ['linear'], ['zoom'], 3, 0.36, 9, 0.42], 'raster-saturation': -0.35, 'raster-resampling': 'linear' } }, before);
  if (!map.getLayer(CONTEXT_LAYERS.relief)) map.addLayer({ id: CONTEXT_LAYERS.relief, type: 'hillshade', source: TERRAIN_SOURCE,
    layout: { visibility: basemap.relief ? 'visible' : 'none' },
    paint: { 'hillshade-exaggeration': ['interpolate', ['linear'], ['zoom'], 3, 0.62, 7, 0.5, 10, 0.4, 11.5, 0.25, 13, 0], 'hillshade-illumination-direction': 315, 'hillshade-shadow-color': '#5b6472',
      'hillshade-highlight-color': '#ffffff', 'hillshade-accent-color': '#6b7480' } }, before);
}

export function setBasemapVisibility(map: LibreMap, basemap: BasemapVisibility): void {
  for (const key of Object.keys(CONTEXT_LAYERS) as (keyof BasemapVisibility)[]) {
    if (map.getLayer(CONTEXT_LAYERS[key])) map.setLayoutProperty(CONTEXT_LAYERS[key], 'visibility', basemap[key] ? 'visible' : 'none');
  }
}

/** Create a layer, or recreate it in place when its source must change (a newer asset arrived). */
function lineLayer(map: LibreMap, id: string, source: string, paint: Record<string, unknown>, before: string | undefined): void {
  const existing = map.getLayer(id) as { source?: string } | undefined;
  // Layers without reported source information are left in place.
  if (existing && (existing.source === undefined || existing.source === source)) return;
  let position = before;
  if (existing) {
    const layers = map.getStyle()?.layers ?? [];
    const index = layers.findIndex((layer) => layer.id === id);
    position = layers[index + 1]?.id ?? before;
    map.removeLayer(id);
  }
  map.addLayer({ id, type: 'line', source, paint } as Parameters<LibreMap['addLayer']>[0], position);
}

export interface ContextBackdrop {
  land: FeatureCollection | null;
  national: FeatureCollection | null;
  /** Edges shared by two states; without it, state polygon outlines (including seaward limits) are drawn. */
  borders?: FeatureCollection | null;
  /** Generalized shoreline lines cut by land tile; without it, land polygon outlines are drawn. */
  shoreline?: FeatureCollection | null;
  /** Countries outside the 50 states and DC: a plain fill and their mutual borders, no geographic detail. */
  foreign?: FeatureCollection | null;
}

export function syncContext(map: LibreMap, states: FeatureCollection | null, useLocalFill: boolean, basemap: BasemapVisibility = DEFAULT_BASEMAP,
  backdrop?: ContextBackdrop): void {
  if (!states) return;
  let cache = contextCache.get(map);
  if (!cache) { cache = new Map(); contextCache.set(map, cache); }
  const update = (id: string, data: FeatureCollection, attribution?: string) => {
    if (cache!.get(id) === data && map.getSource(id)) return;
    if (map.getSource(id)) sourceData(map, id, data);
    else map.addSource(id, { type: 'geojson', data, attribution, tolerance: 0, maxzoom: 18 });
    cache!.set(id, data);
  };
  update('context-states', states,
    '<a href="https://www.census.gov/geographies/mapping-files/time-series/geo/tiger-line-file.html" target="_blank" rel="noopener">U.S. Census Bureau · 2025</a>');
  const before = firstResultLayer(map);
  if (useLocalFill && backdrop?.land) {
    update('context-land', backdrop.land);
    const landBefore = map.getLayer(CONTEXT_LAYERS.forest) ? CONTEXT_LAYERS.forest : map.getLayer('context-state-lines') ? 'context-state-lines' : before;
    if (!map.getLayer('context-state-fill')) map.addLayer({ id: 'context-state-fill', type: 'fill', source: 'context-land',
      paint: { 'fill-color': '#f7f8fa', 'fill-opacity': 1 } }, landBefore);
    if (backdrop.shoreline) update('context-shore-overview', backdrop.shoreline);
    lineLayer(map, 'context-shoreline', backdrop.shoreline ? 'context-shore-overview' : 'context-land',
      { 'line-color': '#a7bccb', 'line-width': 0.7 }, landBefore);
  }
  // Land fill, then forest and relief, then other countries, state lines and labels; results stay above all of it.
  if (useLocalFill) addPhysicalContext(map, before, basemap);
  if (useLocalFill && backdrop?.foreign) {
    update('context-foreign', backdrop.foreign, '<a href="https://www.naturalearthdata.com/" target="_blank" rel="noopener">Natural Earth</a>');
    // Opaque and above relief: other countries show their outline and borders, not their terrain.
    const foreignBefore = map.getLayer('context-state-lines') ? 'context-state-lines' : before;
    if (!map.getLayer('context-foreign-fill')) map.addLayer({ id: 'context-foreign-fill', type: 'fill', source: 'context-foreign',
      filter: ['==', ['get', 'kind'], 'land'], paint: { 'fill-color': '#eceff3', 'fill-opacity': 1 } }, foreignBefore);
    if (!map.getLayer('context-foreign-borders')) map.addLayer({ id: 'context-foreign-borders', type: 'line', source: 'context-foreign',
      filter: ['==', ['get', 'kind'], 'border'], paint: { 'line-color': '#a3acb8', 'line-width': 0.8, 'line-dasharray': [3, 2] } }, foreignBefore);
  }
  if (backdrop?.borders) update('context-borders', backdrop.borders);
  lineLayer(map, 'context-state-lines', backdrop?.borders ? 'context-borders' : 'context-states',
    { 'line-color': '#a3acb8', 'line-width': 0.85 }, map.getLayer('context-national-lines') ? 'context-national-lines' : before);
  if (backdrop?.national) {
    update('context-national', backdrop.national);
    if (!map.getLayer('context-national-lines')) map.addLayer({ id: 'context-national-lines', type: 'line', source: 'context-national',
      paint: { 'line-color': '#5b6472', 'line-width': 1.4 } }, before);
  }
  if (!useLocalFill || map.getLayer('context-state-labels')) return;
  const features: FeatureCollection<Point>['features'] = [];
  for (const state of states.features) {
    const props = state.properties;
    const coordinate = [props?.label_lon, props?.label_lat];
    if (!validCoordinate(coordinate) || typeof props?.name !== 'string') continue;
    const imageId = `state-label-${state.id}`;
    const data = textImage(props.name, 'state');
    if (data && !map.hasImage(imageId)) map.addImage(imageId, data, { pixelRatio: 2 });
    features.push({ type: 'Feature', id: state.id, geometry: { type: 'Point', coordinates: coordinate }, properties: { image: imageId } });
  }
  sourceData(map, 'context-state-labels', { type: 'FeatureCollection', features });
  map.addLayer({ id: 'context-state-labels', type: 'symbol', source: 'context-state-labels', minzoom: 2.8,
    layout: { 'icon-image': ['get', 'image'], 'icon-allow-overlap': false, 'icon-padding': 1 } }, before);
}

export const SCOPE_SOURCE = 'search-scope';
export const SCOPE_LAYERS = ['scope-unassessed', 'scope-window-fill', 'scope-window-line'];
const SCOPE_HATCH = 'scope-hatch';
const scopeCache = new WeakMap<LibreMap, FeatureCollection | null>();

/** Diagonal hatch for land outside the search scope: not assessed at 1 km, which is never zero or a pass. */
function hatchImage(): ImageData | null {
  const size = 8, ratio = 2;
  const canvas = document.createElement('canvas');
  canvas.width = canvas.height = size * ratio;
  const context = canvas.getContext('2d');
  if (!context) return null;
  context.scale(ratio, ratio);
  context.strokeStyle = 'rgba(91, 100, 114, 0.30)';
  context.lineWidth = 1;
  context.beginPath();
  for (const offset of [-size, 0, size]) { context.moveTo(offset, size); context.lineTo(offset + size, 0); }
  context.stroke();
  return context.getImageData(0, 0, canvas.width, canvas.height);
}

/**
 * Start-screen search scope: refined windows over land hatched as not assessed at 1 km.
 * `null` hides it; it sits beneath state lines and every result layer.
 */
export function syncScope(map: LibreMap, windows: FeatureCollection | null): void {
  const visible = !!windows && windows.features.length > 0;
  if (scopeCache.get(map) !== windows || !map.getSource(SCOPE_SOURCE)) {
    sourceData(map, SCOPE_SOURCE, windows ?? EMPTY_COLLECTION);
    scopeCache.set(map, windows);
  }
  if (!map.getLayer('scope-window-fill')) map.addLayer({ id: 'scope-window-fill', type: 'fill', source: SCOPE_SOURCE,
    paint: { 'fill-color': '#e8effd', 'fill-opacity': 0.92 } });
  if (!map.getLayer('scope-window-line')) map.addLayer({ id: 'scope-window-line', type: 'line', source: SCOPE_SOURCE,
    paint: { 'line-color': '#2457d6', 'line-width': 1.2 } });
  if (map.getSource('context-land') && !map.getLayer('scope-unassessed')) {
    if (!map.hasImage(SCOPE_HATCH)) { const image = hatchImage(); if (image) map.addImage(SCOPE_HATCH, image, { pixelRatio: 2 }); }
    if (map.hasImage(SCOPE_HATCH)) map.addLayer({ id: 'scope-unassessed', type: 'fill', source: 'context-land',
      paint: { 'fill-pattern': SCOPE_HATCH } });
  }
  // Context layers keep arriving after the first paint, so re-seat the scope on every sync:
  // above land fill, relief and canopy, beneath other countries, state lines, labels and every result.
  const before = map.getLayer('context-foreign-fill') ? 'context-foreign-fill' : map.getLayer('context-state-lines') ? 'context-state-lines' : firstResultLayer(map);
  for (const id of SCOPE_LAYERS) {
    if (!map.getLayer(id)) continue;
    if (before !== id) map.moveLayer(id, before);
    map.setLayoutProperty(id, 'visibility', visible ? 'visible' : 'none');
  }
}

const badgeLayout: SymbolLayerSpecification['layout'] = { 'icon-image': ['get', 'badge'], 'icon-allow-overlap': true, 'icon-ignore-placement': true,
  'symbol-sort-key': ['-', 100000, ['coalesce', ['get', 'rank'], 100000]] };
const topBadgeFilter = (selectedId: string | null): FilterSpecification => ['all', ['!=', ['get', 'regionId'], selectedId ?? ''], ['==', ['get', 'prominent'], true]];
const dotFilter = (selectedId: string | null): FilterSpecification => ['all', ['!=', ['get', 'regionId'], selectedId ?? ''], ['!=', ['get', 'prominent'], true]];

export function syncCandidates(map: LibreMap, regions: CandidateRegion[], selectedId: string | null, enabled: boolean): void {
  const previous = candidateCache.get(map);
  const changed = previous?.regions !== regions || !map.getSource(CANDIDATE_SOURCE);
  const selected = regions.find((region) => region.id === selectedId);
  const ensureBadge = (feature: FeatureCollection<Point>['features'][number]) => {
    const props = feature.properties!;
    if (!map.hasImage(props.badge)) {
      const image = textImage(props.rank === null ? '•' : String(props.rank), 'badge', statusColor(props.status), props.selected);
      if (image) map.addImage(props.badge, image, { pixelRatio: 2 });
    }
  };
  if (changed) {
    const payload = candidatePayloads(regions, null);
    for (const feature of payload.badges.features) ensureBadge(feature);
    sourceData(map, CANDIDATE_SOURCE, payload.areas);
    sourceData(map, BADGE_SOURCE, payload.badges);
  }
  if (changed || previous?.selected !== selected || !map.getSource(SELECTED_BADGE_SOURCE)) {
    const coordinate = selected && regionCoordinate(selected);
    const features: FeatureCollection<Point>['features'] = coordinate && selected ? [{
      type: 'Feature', id: selected.id, geometry: { type: 'Point', coordinates: coordinate },
      properties: { regionId: selected.id, rank: selected.rank, status: selected.screeningStatus, selected: true,
        badge: badgeImageId(selected.rank, selected.screeningStatus, true) },
    }] : [];
    for (const feature of features) ensureBadge(feature);
    sourceData(map, SELECTED_BADGE_SOURCE, { type: 'FeatureCollection', features });
  }
  candidateCache.set(map, { regions, selected });
  const layers = [
    { id: 'candidate-fill', type: 'fill', source: CANDIDATE_SOURCE,
      paint: { 'fill-color': ['get', 'color'], 'fill-opacity': 0.20 } },
    { id: 'candidate-outline', type: 'line', source: CANDIDATE_SOURCE,
      paint: { 'line-color': ['get', 'color'], 'line-width': ['case', ['boolean', ['feature-state', 'hover'], false], 2.5, 1.4] } },
    { id: 'candidate-selected-fill', type: 'fill', source: CANDIDATE_SOURCE, filter: ['==', ['get', 'regionId'], selectedId ?? ''],
      paint: { 'fill-color': '#2457d6', 'fill-opacity': 0.14 } },
    { id: 'candidate-selected', type: 'line', source: CANDIDATE_SOURCE, filter: ['==', ['get', 'regionId'], selectedId ?? ''],
      paint: { 'line-color': '#2457d6', 'line-width': 4, 'line-opacity': 1 } },
    { id: 'candidate-dot', type: 'circle', source: BADGE_SOURCE, maxzoom: BADGE_DETAIL_ZOOM, filter: dotFilter(selectedId),
      paint: { 'circle-radius': 4.5, 'circle-color': '#ffffff', 'circle-stroke-color': ['get', 'color'], 'circle-stroke-width': 2 } },
    { id: 'candidate-badge-top', type: 'symbol', source: BADGE_SOURCE, maxzoom: BADGE_DETAIL_ZOOM, filter: topBadgeFilter(selectedId),
      layout: badgeLayout },
    { id: 'candidate-badge', type: 'symbol', source: BADGE_SOURCE, minzoom: BADGE_DETAIL_ZOOM, filter: ['!=', ['get', 'regionId'], selectedId ?? ''],
      layout: badgeLayout },
    { id: 'candidate-selected-badge', type: 'symbol', source: SELECTED_BADGE_SOURCE,
      layout: { 'icon-image': ['get', 'badge'], 'icon-allow-overlap': true, 'icon-ignore-placement': true } },
  ] as Parameters<LibreMap['addLayer']>[0][];
  for (const layer of layers) if (!map.getLayer(layer.id)) map.addLayer(layer);
  map.setFilter('candidate-selected-fill', ['==', ['get', 'regionId'], selectedId ?? '']);
  map.setFilter('candidate-selected', ['==', ['get', 'regionId'], selectedId ?? '']);
  map.setFilter('candidate-dot', dotFilter(selectedId));
  map.setFilter('candidate-badge-top', topBadgeFilter(selectedId));
  map.setFilter('candidate-badge', ['!=', ['get', 'regionId'], selectedId ?? '']);
  for (const id of ['candidate-fill', 'candidate-outline', 'candidate-dot', 'candidate-badge-top', 'candidate-badge']) {
    map.setLayoutProperty(id, 'visibility', enabled ? 'visible' : 'none');
  }
}

export function indicatorColor(layer: LayerData): ExpressionSpecification | string {
  if (layer.id === 'grid') return ['match', ['get', '_status'], 'PASS', '#127a3e', 'CONDITIONAL', '#b86e00', 'FAIL', '#c4363b', '#8a93a0'];
  if (layer.min === null || layer.max === null || layer.min >= layer.max || layer.direction === 'categorical') {
    return ['case', ['any', ['==', ['get', '_status'], 'unknown'], ['==', ['get', '_value'], null]], '#9aa3af', '#5b6472'];
  }
  return ['case', ['any', ['==', ['get', '_status'], 'unknown'], ['==', ['get', '_value'], null]], '#9aa3af',
    ['interpolate', ['linear'], ['get', '_value'], layer.min, '#dbe5fb', layer.max, '#2457d6']];
}

export function syncIndicators(map: LibreMap, layers: LayerData[], enabled: Set<string>): void {
  layers = layers.filter(layer => layer.id !== 'community_economic');
  let cache = indicatorCache.get(map);
  if (!cache) { cache = new Map(); indicatorCache.set(map, cache); }
  const keep = new Set(layers.map((layer) => layerSourceId(layer.id)));
  for (const sourceId of Object.keys(map.getStyle()?.sources ?? {})) {
    if (!sourceId.startsWith('indicator-source-') || keep.has(sourceId)) continue;
    const id = sourceId.replace('indicator-source-', '');
    for (const layerId of indicatorLayerIds(id)) if (map.getLayer(layerId)) map.removeLayer(layerId);
    map.removeSource(sourceId);
    cache.delete(id);
  }
  for (const layer of layers) {
    const sourceId = layerSourceId(layer.id);
    if (cache.get(layer.id) !== layer || !map.getSource(sourceId)) {
      sourceData(map, sourceId, layerPayload(layer));
      cache.set(layer.id, layer);
    }
    const color = indicatorColor(layer);
    const visibility = enabled.has(layer.id) ? 'visible' : 'none';
    const [fillId, lineId, pointId] = indicatorLayerIds(layer.id);
    const entries = [
      { id: fillId, type: 'fill', source: sourceId, filter: ['==', ['geometry-type'], 'Polygon'],
        layout: { visibility }, paint: { 'fill-color': color, 'fill-opacity': layer.id === 'grid' ? 0.12 : 0.30 } },
      { id: lineId, type: 'line', source: sourceId, filter: ['!=', ['geometry-type'], 'Point'],
        layout: { visibility }, paint: { 'line-color': color, 'line-width': layer.id === 'grid' ? 0.9 : 1.5 } },
      { id: pointId, type: 'circle', source: sourceId, filter: ['==', ['geometry-type'], 'Point'],
        layout: { visibility }, paint: { 'circle-color': color, 'circle-radius': 5, 'circle-stroke-color': '#ffffff', 'circle-stroke-width': 1 } },
    ] as Parameters<LibreMap['addLayer']>[0][];
    for (const entry of entries) {
      if (!map.getLayer(entry.id)) map.addLayer(entry, map.getLayer('candidate-fill') ? 'candidate-fill' : undefined);
      else {
        map.setLayoutProperty(entry.id, 'visibility', visibility);
        const property = entry.type === 'fill' ? 'fill-color' : entry.type === 'line' ? 'line-color' : 'circle-color';
        map.setPaintProperty(entry.id, property, color);
      }
    }
  }
}
