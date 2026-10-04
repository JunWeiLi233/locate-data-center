import type { FeatureCollection } from 'geojson';
import type { FilterSpecification, GeoJSONSource, ImageSource, Map as LibreMap } from 'maplibre-gl';

/**
 * Presentation overlays drawn above the basemap and model results: GeoJSON layers plus optional
 * georeferenced images. They carry backend values only; nothing here scores, ranks or filters evidence.
 */
export interface OverlayLayer {
  id: string;
  data: FeatureCollection;
  kind: 'circle' | 'fill' | 'line' | 'symbol';
  visible: boolean;
  paint: Record<string, unknown>;
  layout?: Record<string, unknown>;
  filter?: FilterSpecification;
  /** Features carry `properties.overlayId`; a click reports it through `onOverlaySelect`. */
  clickable?: boolean;
  /** Canvas-drawn icon images keyed by name, created on demand for symbol layers. */
  images?: Record<string, () => ImageData | null>;
}
export interface ImageOverlay {
  id: string; url: string; visible: boolean; opacity: number;
  /** Top-left, top-right, bottom-right, bottom-left [lon, lat] corners. */
  coordinates: [[number, number], [number, number], [number, number], [number, number]];
}
export interface MapOverlays { images: ImageOverlay[]; layers: OverlayLayer[] }
export interface MapFocus { key: string; center?: [number, number]; zoom?: number; bounds?: [[number, number], [number, number]] }

export const OVERLAY_PREFIX = 'overlay-';
const sourceId = (id: string) => `${OVERLAY_PREFIX}source-${id}`;
const layerId = (id: string) => `${OVERLAY_PREFIX}${id}`;
const imageLayerId = (id: string) => `${OVERLAY_PREFIX}image-${id}`;
const dataCache = new WeakMap<LibreMap, Map<string, FeatureCollection>>();
const styleCache = new WeakMap<LibreMap, Map<string, string>>();

export function clickableOverlayLayers(map: LibreMap, overlays: MapOverlays | undefined): string[] {
  return (overlays?.layers ?? []).filter(layer => layer.clickable && layer.visible && map.getLayer(layerId(layer.id))).map(layer => layerId(layer.id));
}

function firstVectorOverlay(map: LibreMap): string | undefined {
  return map.getStyle()?.layers?.find(layer => layer.id.startsWith(OVERLAY_PREFIX) && !layer.id.startsWith(`${OVERLAY_PREFIX}image-`))?.id;
}

/** Add, update, show/hide and remove overlay sources and layers to match `overlays`. */
export function syncOverlays(map: LibreMap, overlays: MapOverlays | undefined): void {
  let data = dataCache.get(map);
  if (!data) { data = new Map(); dataCache.set(map, data); }
  let styles = styleCache.get(map);
  if (!styles) { styles = new Map(); styleCache.set(map, styles); }
  const wanted = new Set<string>();
  for (const image of overlays?.images ?? []) {
    const source = `${OVERLAY_PREFIX}image-source-${image.id}`;
    const layer = imageLayerId(image.id);
    wanted.add(source); wanted.add(layer);
    const existing = map.getSource(source) as ImageSource | undefined;
    const signature = JSON.stringify([image.url, image.coordinates]);
    if (!existing) map.addSource(source, { type: 'image', url: image.url, coordinates: image.coordinates });
    else if (styles.get(source) !== signature) existing.updateImage({ url: image.url, coordinates: image.coordinates });
    styles.set(source, signature);
    if (!map.getLayer(layer)) map.addLayer({ id: layer, type: 'raster', source, paint: { 'raster-opacity': image.opacity, 'raster-fade-duration': 0 } }, firstVectorOverlay(map));
    map.setLayoutProperty(layer, 'visibility', image.visible ? 'visible' : 'none');
    map.setPaintProperty(layer, 'raster-opacity', image.opacity);
  }
  for (const overlay of overlays?.layers ?? []) {
    const source = sourceId(overlay.id);
    const layer = layerId(overlay.id);
    wanted.add(source); wanted.add(layer);
    for (const [name, draw] of Object.entries(overlay.images ?? {})) {
      if (map.hasImage(name)) continue;
      const image = draw();
      if (image) map.addImage(name, image, { pixelRatio: 2 });
    }
    const existing = map.getSource(source) as GeoJSONSource | undefined;
    if (!existing) map.addSource(source, { type: 'geojson', data: overlay.data });
    else if (data.get(source) !== overlay.data) existing.setData(overlay.data);
    data.set(source, overlay.data);
    const signature = JSON.stringify([overlay.kind, overlay.paint, overlay.layout ?? {}, overlay.filter ?? null]);
    if (!map.getLayer(layer)) {
      map.addLayer({ id: layer, type: overlay.kind, source, paint: overlay.paint, layout: overlay.layout ?? {},
        ...(overlay.filter ? { filter: overlay.filter } : {}) } as Parameters<LibreMap['addLayer']>[0]);
    } else if (styles.get(layer) !== signature) {
      // Restyle in place so the drawing order of overlays never changes.
      for (const [key, value] of Object.entries(overlay.paint)) map.setPaintProperty(layer, key as Parameters<LibreMap['setPaintProperty']>[1], value as Parameters<LibreMap['setPaintProperty']>[2]);
      for (const [key, value] of Object.entries(overlay.layout ?? {})) map.setLayoutProperty(layer, key as Parameters<LibreMap['setLayoutProperty']>[1], value as Parameters<LibreMap['setLayoutProperty']>[2]);
      map.setFilter(layer, overlay.filter ?? null);
    }
    styles.set(layer, signature);
    map.setLayoutProperty(layer, 'visibility', overlay.visible ? 'visible' : 'none');
  }
  for (const layer of map.getStyle()?.layers ?? []) {
    if (layer.id.startsWith(OVERLAY_PREFIX) && !wanted.has(layer.id)) { map.removeLayer(layer.id); styles.delete(layer.id); }
  }
  for (const source of Object.keys(map.getStyle()?.sources ?? {})) {
    if (source.startsWith(OVERLAY_PREFIX) && !wanted.has(source)) { map.removeSource(source); data.delete(source); styles.delete(source); }
  }
}

const EARTH_RADIUS_KM = 6371.0088;
/** A geodesic circle of `radiusKm` around [lon, lat] (spherical destination formula), for display only. */
export function circleRing(lon: number, lat: number, radiusKm: number, steps = 64): [number, number][] {
  const phi1 = lat * Math.PI / 180, lambda1 = lon * Math.PI / 180, delta = radiusKm / EARTH_RADIUS_KM;
  const ring: [number, number][] = [];
  for (let step = 0; step <= steps; step += 1) {
    const theta = 2 * Math.PI * (step % steps) / steps;
    const phi2 = Math.asin(Math.sin(phi1) * Math.cos(delta) + Math.cos(phi1) * Math.sin(delta) * Math.cos(theta));
    const lambda2 = lambda1 + Math.atan2(Math.sin(theta) * Math.sin(delta) * Math.cos(phi1), Math.cos(delta) - Math.sin(phi1) * Math.sin(phi2));
    ring.push([Number((lambda2 * 180 / Math.PI).toFixed(6)), Number((phi2 * 180 / Math.PI).toFixed(6))]);
  }
  return ring;
}

/** Numbered badge image (canvas) for rank symbols; null where canvas is unavailable. */
export function rankBadge(text: string, fill: string, ring: string, ink = '#ffffff'): () => ImageData | null {
  return () => {
    const canvas = document.createElement('canvas');
    const ratio = 2, size = 30;
    canvas.width = size * ratio; canvas.height = size * ratio;
    const context = canvas.getContext('2d');
    if (!context) return null;
    context.scale(ratio, ratio);
    context.beginPath(); context.arc(size / 2, size / 2, 11.5, 0, Math.PI * 2);
    context.fillStyle = fill; context.fill();
    context.lineWidth = 2; context.strokeStyle = ring; context.stroke();
    context.fillStyle = ink; context.font = '700 11px Arial, sans-serif';
    context.textAlign = 'center'; context.textBaseline = 'middle';
    context.fillText(text, size / 2, size / 2 + 0.5);
    return context.getImageData(0, 0, canvas.width, canvas.height);
  };
}
