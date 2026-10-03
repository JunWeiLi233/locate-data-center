import type { FeatureCollection, Point } from 'geojson';
import type { Map as LibreMap, GeoJSONSource, StyleSpecification, ExpressionSpecification } from 'maplibre-gl';
import type { CandidateRegion, LayerData } from '../types/domain';
import { badgeImageId, candidatePayloads, indicatorLayerIds, layerPayload, layerSourceId, statusColor } from './mapData';
import { regionCoordinate, validCoordinate } from './geometry';

export const CANDIDATE_SOURCE = 'candidate-areas';
export const BADGE_SOURCE = 'candidate-badges';
export const SELECTED_BADGE_SOURCE = 'candidate-selected-badge';
export const CANDIDATE_LAYERS = ['candidate-fill', 'candidate-outline', 'candidate-selected-fill', 'candidate-selected', 'candidate-badge', 'candidate-selected-badge'];
export const EMPTY_COLLECTION: FeatureCollection = { type: 'FeatureCollection', features: [] };
const candidateCache = new WeakMap<LibreMap, { regions: CandidateRegion[]; selected: CandidateRegion | undefined }>();
const indicatorCache = new WeakMap<LibreMap, Map<string, LayerData>>();

export function neutralStyle(): StyleSpecification {
  return { version: 8, sources: {}, layers: [{ id: 'neutral-background', type: 'background', paint: { 'background-color': '#eaf0f2' } }] };
}

function sourceData(map: LibreMap, id: string, data: FeatureCollection, attribution?: string): void {
  const existing = map.getSource(id) as GeoJSONSource | undefined;
  if (existing) existing.setData(data);
  else map.addSource(id, { type: 'geojson', data, attribution });
}

function textImage(text: string, kind: 'state' | 'badge', color = '#167d84', selected = false): ImageData | null {
  const canvas = document.createElement('canvas');
  const ratio = 2;
  canvas.width = (kind === 'state' ? 160 : 38) * ratio;
  canvas.height = (kind === 'state' ? 24 : 38) * ratio;
  const context = canvas.getContext('2d');
  if (!context) return null;
  context.scale(ratio, ratio);
  if (kind === 'badge') {
    context.beginPath(); context.arc(19, 19, selected ? 17 : 15, 0, Math.PI * 2);
    context.fillStyle = selected ? '#167d84' : '#ffffff'; context.fill();
    context.lineWidth = selected ? 3 : 2; context.strokeStyle = selected ? '#ffffff' : color; context.stroke();
    context.fillStyle = selected ? '#ffffff' : '#22343c';
    context.font = '600 13px Arial, sans-serif';
  } else {
    context.fillStyle = '#74808a'; context.font = '11px Arial, sans-serif';
  }
  context.textAlign = 'center'; context.textBaseline = 'middle';
  context.fillText(text, canvas.width / ratio / 2, canvas.height / ratio / 2, canvas.width / ratio - 8);
  return context.getImageData(0, 0, canvas.width, canvas.height);
}

export function syncContext(map: LibreMap, states: FeatureCollection | null, useLocalFill: boolean): void {
  if (!states || map.getSource('context-states')) return;
  sourceData(map, 'context-states', states,
    '<a href="https://www.census.gov/geographies/mapping-files/time-series/geo/carto-boundary-file.html" target="_blank" rel="noopener">U.S. Census Bureau · 2023</a>');
  const before = map.getLayer('candidate-fill') ? 'candidate-fill' : undefined;
  if (useLocalFill) map.addLayer({ id: 'context-state-fill', type: 'fill', source: 'context-states',
    paint: { 'fill-color': '#f5f5ef', 'fill-opacity': 1 } }, before);
  map.addLayer({ id: 'context-state-lines', type: 'line', source: 'context-states',
    paint: { 'line-color': '#c1ccce', 'line-width': 0.8 } }, before);
  if (!useLocalFill) return;
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
      paint: { 'fill-color': '#08747d', 'fill-opacity': 0.14 } },
    { id: 'candidate-selected', type: 'line', source: CANDIDATE_SOURCE, filter: ['==', ['get', 'regionId'], selectedId ?? ''],
      paint: { 'line-color': '#08747d', 'line-width': 4, 'line-opacity': 1 } },
    { id: 'candidate-badge', type: 'symbol', source: BADGE_SOURCE, filter: ['!=', ['get', 'regionId'], selectedId ?? ''],
      layout: { 'icon-image': ['get', 'badge'], 'icon-allow-overlap': true, 'icon-ignore-placement': true,
        'symbol-sort-key': ['-', 100000, ['coalesce', ['get', 'rank'], 100000]] } },
    { id: 'candidate-selected-badge', type: 'symbol', source: SELECTED_BADGE_SOURCE,
      layout: { 'icon-image': ['get', 'badge'], 'icon-allow-overlap': true, 'icon-ignore-placement': true } },
  ] as Parameters<LibreMap['addLayer']>[0][];
  for (const layer of layers) if (!map.getLayer(layer.id)) map.addLayer(layer);
  map.setFilter('candidate-selected-fill', ['==', ['get', 'regionId'], selectedId ?? '']);
  map.setFilter('candidate-selected', ['==', ['get', 'regionId'], selectedId ?? '']);
  map.setFilter('candidate-badge', ['!=', ['get', 'regionId'], selectedId ?? '']);
  for (const id of ['candidate-fill', 'candidate-outline', 'candidate-badge']) {
    map.setLayoutProperty(id, 'visibility', enabled ? 'visible' : 'none');
  }
}

export function indicatorColor(layer: LayerData): ExpressionSpecification | string {
  if (layer.id === 'grid') return ['match', ['get', '_status'], 'PASS', '#167d84', 'CONDITIONAL', '#b88932', 'FAIL', '#b35c58', '#818b94'];
  if (layer.min === null || layer.max === null || layer.min >= layer.max || layer.direction === 'categorical') {
    return ['case', ['any', ['==', ['get', '_status'], 'unknown'], ['==', ['get', '_value'], null]], '#969fa6', '#667f91'];
  }
  return ['case', ['any', ['==', ['get', '_status'], 'unknown'], ['==', ['get', '_value'], null]], '#969fa6',
    ['interpolate', ['linear'], ['get', '_value'], layer.min, '#d6e3e8', layer.max, '#52678d']];
}

export function syncIndicators(map: LibreMap, layers: LayerData[], enabled: Set<string>): void {
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
