import type { FeatureCollection, Feature, Geometry, Point } from 'geojson';
import type { CandidateRegion, LayerData, LayerSelection, ScreeningStatus } from '../types/domain';
import { geometryKey, polygonGeometry, regionCoordinate } from './geometry';

export const STATUS_COLORS: Record<ScreeningStatus, string> = {
  PASS: '#167d84', CONDITIONAL: '#b88932', FAIL: '#b35c58', UNKNOWN: '#818b94',
};
export function statusColor(status: string): string {
  return STATUS_COLORS[status as ScreeningStatus] ?? STATUS_COLORS.UNKNOWN;
}

export function compareRegions(a: CandidateRegion, b: CandidateRegion): number {
  return (a.rank ?? Infinity) - (b.rank ?? Infinity) || a.id.localeCompare(b.id);
}

export function overlapRegions(regions: CandidateRegion[], ids: string[]): CandidateRegion[] {
  const matched = new Set(ids);
  const keys = new Set(regions.filter((region) => matched.has(region.id)).map(geometryKey).filter(Boolean));
  return regions.filter((region) => matched.has(region.id) || keys.has(geometryKey(region))).sort(compareRegions);
}

const placeKeys = new WeakMap<CandidateRegion, string>();
/** Identical search geometry identifies one place; its cooling designs remain separate backend alternatives. */
export function placeKey(region: CandidateRegion): string {
  let key = placeKeys.get(region);
  if (key === undefined) { key = geometryKey(region) ?? `id:${region.id}`; placeKeys.set(region, key); }
  return key;
}

/** Places whose best alternative keeps a numbered badge at national zoom; the rest show as dots until zoomed in. */
export const PROMINENT_PLACES = 10;
export function prominentRegions(regions: CandidateRegion[], count = PROMINENT_PLACES): Set<string> {
  const places = new Set<string>();
  const ids = new Set<string>();
  for (const region of [...regions].sort(compareRegions)) {
    const key = placeKey(region);
    if (places.has(key)) continue;
    if (places.size >= count) break;
    places.add(key); ids.add(region.id);
  }
  return ids;
}

export function candidatePayloads(regions: CandidateRegion[], selectedId: string | null): {
  areas: FeatureCollection; badges: FeatureCollection<Point>;
} {
  const areas: Feature[] = [];
  const badges: Feature<Point>[] = [];
  const prominent = prominentRegions(regions);
  for (const region of regions) {
    const selected = region.id === selectedId;
    const properties = {
      regionId: region.id, status: region.screeningStatus, color: statusColor(region.screeningStatus),
      selected, rank: region.rank, label: region.label, prominent: prominent.has(region.id),
      badge: badgeImageId(region.rank, region.screeningStatus, selected),
    };
    const geometry = polygonGeometry(region.geometry);
    if (geometry) areas.push({ type: 'Feature', id: region.id, geometry, properties });
    const coordinate = regionCoordinate(region);
    if (coordinate) {
      badges.push({ type: 'Feature', id: region.id, geometry: { type: 'Point', coordinates: coordinate }, properties });
    }
  }
  return {
    areas: { type: 'FeatureCollection', features: areas },
    badges: { type: 'FeatureCollection', features: badges },
  };
}

export function badgeImageId(rank: number | null, status: string, selected: boolean): string {
  const text = rank !== null && Number.isInteger(rank) && rank > 0 ? String(rank) : '•';
  return `candidate-badge-${text}-${status}-${selected ? 'selected' : 'default'}`;
}

function hash(value: string): string {
  let result = 2166136261;
  for (let index = 0; index < value.length; index++) result = Math.imul(result ^ value.charCodeAt(index), 16777619);
  return (result >>> 0).toString(36);
}

export function layerPayload(layer: LayerData): FeatureCollection {
  const usedIds = new Set<string>();
  const features: Feature<Geometry>[] = [];
  for (const feature of layer.data.features) {
    if (!feature.geometry) continue;
    const original = feature.properties ?? {};
    const rawValue = original[layer.valueProperty];
    const value = typeof rawValue === 'number' && Number.isFinite(rawValue) ? rawValue : null;
    const status = typeof original[layer.statusProperty] === 'string' ? original[layer.statusProperty] : 'unknown';
    const baseId = String(feature.id ?? original.grid_id ?? original.region_id ?? original.id
      ?? hash(JSON.stringify(feature.geometry)));
    let id = `${layer.id}:${baseId}`;
    if (usedIds.has(id)) id += `:${hash(JSON.stringify(feature.properties) + JSON.stringify(feature.geometry))}`;
    let suffix = 2;
    const uniqueBase = id;
    while (usedIds.has(id)) id = `${uniqueBase}:${suffix++}`;
    usedIds.add(id);
    features.push({ ...feature, id, properties: { ...original, _layerId: layer.id, _value: value, _status: status } });
  }
  return { type: 'FeatureCollection', features };
}

export function selectedLayerIds(selections: LayerSelection[]): Set<string> {
  return new Set(selections.filter((selection) => selection.enabled && selection.id !== 'community_economic').map((selection) => selection.id));
}

export function layerSourceId(id: string): string { return `indicator-source-${id}`; }
export function indicatorLayerIds(id: string): string[] {
  return [`indicator-fill-${id}`, `indicator-line-${id}`, `indicator-point-${id}`];
}
