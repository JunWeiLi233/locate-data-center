import type { FeatureCollection, Point, Polygon } from 'geojson';
import { circleRing, rankBadge, type MapOverlays } from '../../map/overlays';
import type { RediscoveryCandidate, RediscoveryResult } from '../../types/rediscovery';

/** Validated categorical palette (dataviz validator: all-pairs normal-vision ΔE ≥ 15; amber needs its dark outline). */
export const COLORS = { facility: '#2a78d6', candidate: '#e34948', validated: '#4a3aa7', emerging: '#eda100', emergingOutline: '#52514e', ink: '#203330' };
export interface LayerVisibility { facilities: boolean; candidates: boolean; validated: boolean; emerging: boolean; surface: boolean }
export const ALL_LAYERS: LayerVisibility = { facilities: true, candidates: true, validated: true, emerging: true, surface: false };
export const BADGED = 10;

const points = <P extends Record<string, unknown>>(rows: { lon: number; lat: number; properties: P }[]): FeatureCollection<Point, P> => ({
  type: 'FeatureCollection', features: rows.map(row => ({ type: 'Feature', geometry: { type: 'Point', coordinates: [row.lon, row.lat] }, properties: row.properties })),
});
const disks = (rows: RediscoveryCandidate[], radiusKm: number): FeatureCollection<Polygon> => ({
  type: 'FeatureCollection', features: rows.map(row => ({ type: 'Feature', geometry: { type: 'Polygon', coordinates: [circleRing(row.lon, row.lat, radiusKm)] },
    properties: { overlayId: `candidate:${row.rank}`, rank: row.rank } })),
});

/** Stable per-result GeoJSON, so selection and visibility changes never rebuild geometry. */
export function overlayGeometry(result: RediscoveryResult, topN: number) {
  const shown = result.candidates.slice(0, topN);
  return {
    facilities: points(result.facilities.map(item => ({ lon: item.lon, lat: item.lat, properties: { overlayId: `facility:${item.facilityId}` } }))),
    candidates: points(shown.map(item => ({ lon: item.lon, lat: item.lat, properties: { overlayId: `candidate:${item.rank}`, rank: item.rank,
      badge: item.rank <= BADGED ? `rediscovery-rank-${item.rank}` : '' } }))),
    validated: disks(shown.filter(item => item.classification === 'validated'), result.parameters.validatedMaxKm),
    emerging: disks(shown.filter(item => item.classification === 'emerging'), result.parameters.emergingMinKm),
  };
}

export function buildOverlays(result: RediscoveryResult, geometry: ReturnType<typeof overlayGeometry>, visible: LayerVisibility, selectedRank: number | null): MapOverlays {
  const selected = selectedRank ?? -1;
  const images = Object.fromEntries(Array.from({ length: BADGED }, (_, index) =>
    [`rediscovery-rank-${index + 1}`, rankBadge(String(index + 1), COLORS.candidate, '#ffffff')]));
  return {
    images: result.surface ? [{ id: 'rediscovery-surface', url: result.surface.url, coordinates: result.surface.coordinates, visible: visible.surface, opacity: 1 }] : [],
    layers: [
      { id: 'rediscovery-validated-fill', kind: 'fill', data: geometry.validated, visible: visible.validated,
        paint: { 'fill-color': COLORS.validated, 'fill-opacity': 0.2 } },
      { id: 'rediscovery-validated-line', kind: 'line', data: geometry.validated, visible: visible.validated,
        paint: { 'line-color': COLORS.validated, 'line-width': 1.4 } },
      { id: 'rediscovery-emerging-halo', kind: 'line', data: geometry.emerging, visible: visible.emerging,
        paint: { 'line-color': COLORS.emergingOutline, 'line-width': 2.6, 'line-opacity': 0.22 } },
      { id: 'rediscovery-emerging-line', kind: 'line', data: geometry.emerging, visible: visible.emerging,
        paint: { 'line-color': COLORS.emerging, 'line-width': 1.4, 'line-opacity': 0.9, 'line-dasharray': [2.4, 1.8] } },
      { id: 'rediscovery-facilities', kind: 'circle', data: geometry.facilities, visible: visible.facilities, clickable: true,
        paint: { 'circle-color': COLORS.facility, 'circle-opacity': 0.85, 'circle-stroke-color': '#ffffff', 'circle-stroke-width': 0.8,
          'circle-radius': ['interpolate', ['linear'], ['zoom'], 3, 2.6, 7, 4.5, 11, 6] } },
      { id: 'rediscovery-candidates', kind: 'circle', data: geometry.candidates, visible: visible.candidates, clickable: true,
        paint: { 'circle-color': COLORS.candidate, 'circle-stroke-color': '#ffffff', 'circle-stroke-width': 1.3,
          'circle-radius': ['interpolate', ['linear'], ['zoom'], 3, 4, 7, 6.5, 11, 8] } },
      { id: 'rediscovery-candidate-badges', kind: 'symbol', data: geometry.candidates, visible: visible.candidates, clickable: true,
        filter: ['all', ['<=', ['get', 'rank'], BADGED], ['!=', ['get', 'rank'], selected]], images,
        layout: { 'icon-image': ['get', 'badge'], 'icon-allow-overlap': true, 'icon-ignore-placement': true, 'symbol-sort-key': ['-', 1000, ['get', 'rank']] }, paint: {} },
      { id: 'rediscovery-candidate-selected', kind: 'circle', data: geometry.candidates, visible: visible.candidates || selectedRank !== null,
        filter: ['==', ['get', 'rank'], selected],
        paint: { 'circle-color': COLORS.candidate, 'circle-stroke-color': COLORS.ink, 'circle-stroke-width': 3,
          'circle-radius': ['interpolate', ['linear'], ['zoom'], 3, 8, 7, 11, 11, 13] } },
    ],
  };
}
