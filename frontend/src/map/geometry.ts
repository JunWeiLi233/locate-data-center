import type { Geometry, Position, Polygon, MultiPolygon } from 'geojson';
import type { CandidateRegion, MapCamera } from '../types/domain';

export type Bounds = [[number, number], [number, number]];
export const US_BOUNDS: Bounds = [[-125.2, 24.2], [-66.2, 50.2]];
export const US_CAMERA = { longitude: -96, latitude: 38.5, zoom: 3.5 };

export function initialMapView(camera: MapCamera | undefined, selectedId: string | null) {
  return { camera: { ...(camera ?? US_CAMERA) }, fitUS: camera === undefined && selectedId === null };
}

export interface ViewportPadding { top: number; right: number; bottom: number; left: number }
export function viewportPadding(container: Pick<DOMRect, 'top' | 'right' | 'bottom' | 'left' | 'height' | 'width'>,
  visible: Pick<DOMRect, 'top' | 'right' | 'bottom' | 'left'>, gap = 24): ViewportPadding {
  const maxVertical = Math.max(0, container.height - 80);
  const maxHorizontal = Math.max(0, container.width - 80);
  const top = Math.min(maxVertical / 2, Math.max(0, visible.top - container.top) + gap);
  const left = Math.min(maxHorizontal / 2, Math.max(0, visible.left - container.left) + gap);
  return { top, left,
    bottom: Math.min(Math.max(0, maxVertical - top), Math.max(0, container.bottom - visible.bottom) + gap),
    right: Math.min(Math.max(0, maxHorizontal - left), Math.max(0, container.right - visible.right) + gap) };
}

export function validCoordinate(value: unknown): value is [number, number] {
  if (!Array.isArray(value) || value.length < 2) return false;
  return typeof value[0] === 'number' && Number.isFinite(value[0]) && value[0] >= -180 && value[0] <= 180
    && typeof value[1] === 'number' && Number.isFinite(value[1]) && value[1] >= -90 && value[1] <= 90;
}

function validRing(ring: Position[]): boolean {
  if (!Array.isArray(ring) || ring.length < 4 || !ring.every(validCoordinate)) return false;
  if (ring[0][0] !== ring.at(-1)![0] || ring[0][1] !== ring.at(-1)![1]) return false;
  const area = ring.slice(1).reduce((sum, point, index) => sum
    + ring[index][0] * point[1] - point[0] * ring[index][1], 0);
  return Number.isFinite(area) && Math.abs(area) > 1e-12;
}

export function polygonGeometry(geometry: Geometry | null | undefined): Polygon | MultiPolygon | null {
  if (!geometry || (geometry.type !== 'Polygon' && geometry.type !== 'MultiPolygon')) return null;
  const polygons = geometry.type === 'Polygon' ? [geometry.coordinates] : geometry.coordinates;
  if (!Array.isArray(polygons) || !polygons.length || !polygons.every((polygon) => Array.isArray(polygon)
    && polygon.length > 0 && polygon.every(validRing))) return null;
  return geometry;
}

export function geometryBounds(geometry: Geometry | null | undefined): Bounds | null {
  const validated = polygonGeometry(geometry);
  if (!validated) return null;
  const polygons = validated.type === 'Polygon' ? [validated.coordinates] : validated.coordinates;
  let west = Infinity, south = Infinity, east = -Infinity, north = -Infinity;
  for (const polygon of polygons) for (const ring of polygon) for (const [lon, lat] of ring) {
    west = Math.min(west, lon); south = Math.min(south, lat);
    east = Math.max(east, lon); north = Math.max(north, lat);
  }
  return west < east && south < north ? [[west, south], [east, north]] : null;
}

export function regionCoordinate(region: Pick<CandidateRegion, 'centroid'>): [number, number] | null {
  const coordinate = region.centroid ? [region.centroid.lon, region.centroid.lat] : null;
  return validCoordinate(coordinate) ? coordinate : null;
}

export function selectionViewport(region: Pick<CandidateRegion, 'geometry' | 'centroid'>):
  { bounds: Bounds; center?: never } | { center: [number, number]; bounds?: never } | null {
  const bounds = geometryBounds(region.geometry);
  if (bounds) return { bounds };
  const center = regionCoordinate(region);
  return center ? { center } : null;
}

export function geometryKey(region: Pick<CandidateRegion, 'geometry' | 'centroid'>): string | null {
  const geometry = polygonGeometry(region.geometry);
  if (geometry) return JSON.stringify(geometry);
  const point = regionCoordinate(region);
  return point ? `point:${point.join(',')}` : null;
}
