import { useCallback, useEffect, useRef, useState } from 'react';
import * as maplibregl from 'maplibre-gl';
import type { Map as LibreMap, MapMouseEvent } from 'maplibre-gl';
import type { FeatureCollection } from 'geojson';
import type { CandidateRegion, LayerData, LayerSelection, MapCamera, MapFeatureInfo } from '../types/domain';
import { overlapRegions, selectedLayerIds } from './mapData';
import { coolingName, regionName, shortCooling, statusWord } from '../utils/regions';
import { initialMapView, selectionViewport, US_BOUNDS, viewportPadding } from './geometry';
import { CANDIDATE_LAYERS, CANDIDATE_SOURCE, DEFAULT_BASEMAP, isContextSourceError, neutralStyle, setBasemapVisibility, syncCandidates, syncContext, syncIndicators, type BasemapVisibility, type ContextBackdrop } from './mapStyle';
import 'maplibre-gl/dist/maplibre-gl.css';
import './map.css';
import { BoundaryDetails } from './boundaryContext';
import { clickableOverlayLayers, syncOverlays, type MapOverlays } from './overlays';

export interface CandidateMapProps {
  regions: CandidateRegion[];
  selectedId: string | null;
  onSelect: (id: string) => void;
  layers: LayerData[];
  layerSelections: LayerSelection[];
  onFeatureInfo?: (info: MapFeatureInfo) => void;
  camera?: MapCamera;
  onCameraChange?: (camera: MapCamera) => void;
  projection?: 'mercator' | 'globe';
  /** Visibility of the bundled basemap's terrain relief and forest canopy context. */
  basemap?: BasemapVisibility;
  /** Moves the map to a stored view, e.g. when the browser's Back button returns to it; `id` changes per request. */
  viewRequest?: { camera: MapCamera; id: number };
  /** Optional presentation overlays (points, rings, images) drawn above model results. */
  overlays?: MapOverlays;
  /** Receives `properties.overlayId` of a clicked clickable overlay feature. */
  onOverlaySelect?: (id: string) => void;
  className?: string;
}

function motionDuration(): number {
  return window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 0 : 550;
}

export function CandidateMap(props: CandidateMapProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const viewportRef = useRef<HTMLDivElement>(null);
  const choiceRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<LibreMap | null>(null);
  const styleReadyRef = useRef(false);
  const current = useRef(props);
  current.current = props;
  const contextRef = useRef<FeatureCollection | null>(null);
  const boundaryDetailsRef = useRef<BoundaryDetails | null>(null);
  const backdropRef = useRef<ContextBackdrop>({ land: null, national: null, borders: null, shoreline: null, foreign: null });
  const localStyleRef = useRef(!import.meta.env.VITE_MAP_STYLE_URL);
  const fittedSelection = useRef<string | null>(null);
  const [revision, setRevision] = useState(0);
  const [retry, setRetry] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [mapNote, setMapNote] = useState<string | null>(null);
  const [boundaryStatus, setBoundaryStatus] = useState<string | null>(null);
  const [choices, setChoices] = useState<CandidateRegion[]>([]);
  const visiblePadding = useCallback(() => containerRef.current && viewportRef.current
    ? viewportPadding(containerRef.current.getBoundingClientRect(), viewportRef.current.getBoundingClientRect()) : 65, []);

  useEffect(() => {
    if (!containerRef.current) return;
    const abort = new AbortController();
    let disposed = false;
    let hoverId: string | null = null;
    let fallbackUsed = false;
    let styleTimeout: number | undefined;
    let renderTimeout: number | undefined;
    let boundaryDetails: BoundaryDetails | undefined;
    const customStyle = import.meta.env.VITE_MAP_STYLE_URL as string | undefined;
    localStyleRef.current = !customStyle;
    styleReadyRef.current = false;
    fittedSelection.current = null;
    setError(null);
    setMapNote(null);
    setBoundaryStatus(null);
    // Snapshot intent before projection/resize events report the map's initial camera.
    const initialView = initialMapView(current.current.camera, current.current.selectedId);
    let map: LibreMap;
    try {
      const camera = initialView.camera;
      map = new maplibregl.Map({
        container: containerRef.current,
        style: customStyle || neutralStyle(),
        center: [camera.longitude, camera.latitude], zoom: camera.zoom,
        minZoom: 1.5, maxZoom: 17, maxPitch: 60,
        attributionControl: false, renderWorldCopies: false,
        canvasContextAttributes: { antialias: true },
      });
    } catch {
      setError('The interactive map could not start. WebGL may be unavailable in this browser. Results and region details remain available.');
      return () => abort.abort();
    }
    mapRef.current = map;
    map.addControl(new maplibregl.AttributionControl({ compact: false }), 'bottom-right');
    map.getCanvas().setAttribute('aria-label', 'United States candidate region map. Use arrow keys to pan and plus or minus to zoom.');
    map.getCanvas().setAttribute('aria-describedby', 'candidate-map-context');

    const synchronize = () => {
      if (disposed || !styleReadyRef.current) return;
      try {
        const value = current.current;
        syncContext(map, contextRef.current, localStyleRef.current, value.basemap ?? DEFAULT_BASEMAP, backdropRef.current);
        boundaryDetails?.refresh();
        const enabled = selectedLayerIds(value.layerSelections);
        syncCandidates(map, value.regions, value.selectedId, enabled.has('candidates'));
        syncIndicators(map, value.layers, enabled);
        syncOverlays(map, value.overlays);
        map.setProjection({ type: value.projection ?? 'mercator' });
        setRevision((number) => number + 1);
      } catch {
        setError('The map could not render its geographic data. Results and region details remain available. Retry to restore the map.');
      }
    };
    const fallback = () => {
      if (!customStyle || fallbackUsed || disposed) return;
      fallbackUsed = true;
      styleReadyRef.current = false;
      localStyleRef.current = true;
      setMapNote('The configured basemap is unavailable. Showing local Census state context.');
      map.setStyle(neutralStyle());
    };
    map.on('style.load', () => { styleReadyRef.current = true; synchronize(); });
    map.on('error', (event) => {
      if (disposed) return;
      // Terrain/forest tiles are optional context; results and state geometry never depend on them.
      if (isContextSourceError(event as { sourceId?: unknown })) return;
      if (customStyle && !fallbackUsed) fallback();
      else setError('A map source could not load or render. Results and region details remain available. Retry to restore the map.');
    });
    map.once('load', () => {
      if (styleTimeout) window.clearTimeout(styleTimeout);
      if (initialView.fitUS && !current.current.selectedId) map.fitBounds(US_BOUNDS, { padding: visiblePadding(), duration: 0 });
    });
    if (customStyle) styleTimeout = window.setTimeout(() => { if (!map.isStyleLoaded()) fallback(); }, 10000);
    const sourcesReady = () => styleReadyRef.current && ['context-states', CANDIDATE_SOURCE].every((id) => !map.getSource(id) || map.isSourceLoaded(id));
    map.on('idle', () => {
      if (map.getSource('context-states') && sourcesReady() && renderTimeout) window.clearTimeout(renderTimeout);
    });
    // A large candidate payload can still be in the worker when the page opens on saved results;
    // keep waiting while the style and state context are ready, then report a real stall.
    const contextReady = () => styleReadyRef.current && (!map.getSource('context-states') || map.isSourceLoaded('context-states'));
    const watchdog = (attempt: number): number => window.setTimeout(() => {
      if (disposed || sourcesReady()) return;
      if (attempt < 3 && contextReady()) { renderTimeout = watchdog(attempt + 1); return; }
      setError('The browser could not finish loading the map graphics or geographic sources. Results and region details remain available. Retry to restore the map.');
    }, 15000);
    renderTimeout = watchdog(0);
    map.on('moveend', () => {
      if (disposed) return;
      const center = map.getCenter();
      current.current.onCameraChange?.({ longitude: center.lng, latitude: center.lat, zoom: map.getZoom() });
      boundaryDetails?.refresh();
    });
    const candidateAt = (event: MapMouseEvent) => map.queryRenderedFeatures(
      [[event.point.x - 4, event.point.y - 4], [event.point.x + 4, event.point.y + 4]],
      { layers: CANDIDATE_LAYERS.filter((id) => map.getLayer(id)) },
    );
    const overlayAt = (event: MapMouseEvent) => {
      const layers = clickableOverlayLayers(map, current.current.overlays);
      return layers.length ? map.queryRenderedFeatures([[event.point.x - 5, event.point.y - 5], [event.point.x + 5, event.point.y + 5]], { layers })
        .map((feature) => feature.properties?.overlayId).find((id): id is string => typeof id === 'string') : undefined;
    };
    map.on('click', (event) => {
      if (!styleReadyRef.current) return;
      const overlayId = current.current.onOverlaySelect ? overlayAt(event) : undefined;
      if (overlayId) { current.current.onOverlaySelect!(overlayId); return; }
      const features = candidateAt(event);
      const ids = features.map((feature) => feature.properties?.regionId).filter((id): id is string => typeof id === 'string');
      const regions = overlapRegions(current.current.regions, ids);
      if (regions.length) {
        if (regions.length > 1) {
          const index = regions.findIndex((region) => region.id === current.current.selectedId);
          current.current.onSelect(regions[(index + 1) % regions.length].id);
          setChoices(regions);
        } else {
          current.current.onSelect(regions[0].id);
          setChoices([]);
        }
        return;
      }
      setChoices([]);
      const indicatorIds = current.current.layers.flatMap((layer) => [`indicator-fill-${layer.id}`, `indicator-line-${layer.id}`, `indicator-point-${layer.id}`])
        .filter((id) => map.getLayer(id));
      if (!indicatorIds.length) return;
      const feature = map.queryRenderedFeatures(event.point, { layers: indicatorIds })[0];
      if (!feature) return;
      const layer = current.current.layers.find((item) => item.id === feature.properties?._layerId);
      const properties = Object.fromEntries(Object.entries(feature.properties ?? {}).filter(([key]) => !key.startsWith('_')));
      current.current.onFeatureInfo?.({ title: layer?.label ?? 'Map feature', status: String(feature.properties?._status ?? 'unknown'), properties });
    });
    map.on('mousemove', (event) => {
      if (!styleReadyRef.current) return;
      const nextId = candidateAt(event)[0]?.properties?.regionId as string | undefined;
      if (hoverId && map.getSource(CANDIDATE_SOURCE)) map.setFeatureState({ source: CANDIDATE_SOURCE, id: hoverId }, { hover: false });
      hoverId = nextId ?? null;
      if (hoverId && map.getSource(CANDIDATE_SOURCE)) map.setFeatureState({ source: CANDIDATE_SOURCE, id: hoverId }, { hover: true });
      map.getCanvas().style.cursor = nextId || (current.current.onOverlaySelect && overlayAt(event)) ? 'pointer' : '';
    });
    const lostContext = (event: Event) => {
      event.preventDefault();
      setError('The browser lost the map graphics context. Results and region details remain available. Retry to restore the map.');
    };
    map.getCanvas().addEventListener('webglcontextlost', lostContext);
    const resize = new ResizeObserver(() => {
      if (!disposed) { map.resize(); setRevision((number) => number + 1); }
    });
    resize.observe(containerRef.current);
    if (viewportRef.current) resize.observe(viewportRef.current);
    void fetch(`${import.meta.env.BASE_URL}map/states.geojson`, { signal: abort.signal })
      .then((response) => { if (!response.ok) throw new Error('State context unavailable'); return response.json() as Promise<FeatureCollection>; })
      .then((states) => {
        if (disposed) return;
        contextRef.current = states;
        boundaryDetails = new BoundaryDetails(map, states, import.meta.env.BASE_URL, setBoundaryStatus);
        boundaryDetailsRef.current = boundaryDetails;
        synchronize();
      }).catch(() => { if (!disposed && !abort.signal.aborted) setMapNote('State context could not load. Candidate data remains tied to its reported coordinates.'); });
    for (const kind of ['land', 'national', 'borders', 'shoreline', 'foreign'] as const) {
      void fetch(`${import.meta.env.BASE_URL}map/${kind}.geojson`, { signal: abort.signal })
        .then(response => { if (!response.ok) throw new Error('Boundary backdrop unavailable'); return response.json() as Promise<FeatureCollection>; })
        .then(data => { if (!disposed) { backdropRef.current[kind] = data; synchronize(); } })
        .catch(() => { if (!disposed && !abort.signal.aborted) setMapNote('Part of the Census boundary context is unavailable. Candidate coordinates remain unchanged.'); });
    }
    return () => {
      disposed = true;
      abort.abort();
      boundaryDetails?.dispose();
      if (boundaryDetailsRef.current === boundaryDetails) boundaryDetailsRef.current = null;
      resize.disconnect();
      if (styleTimeout) window.clearTimeout(styleTimeout);
      if (renderTimeout) window.clearTimeout(renderTimeout);
      map.getCanvas().removeEventListener('webglcontextlost', lostContext);
      map.remove();
      mapRef.current = null;
      styleReadyRef.current = false;
    };
  }, [retry, visiblePadding]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !styleReadyRef.current) return;
    const enabled = selectedLayerIds(props.layerSelections);
    syncCandidates(map, props.regions, props.selectedId, enabled.has('candidates'));
    syncIndicators(map, props.layers, enabled);
  }, [props.regions, props.selectedId, props.layers, props.layerSelections, revision]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !styleReadyRef.current) return;
    map.setProjection({ type: props.projection ?? 'mercator' });
  }, [props.projection, revision]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !styleReadyRef.current) return;
    setBasemapVisibility(map, props.basemap ?? DEFAULT_BASEMAP);
  }, [props.basemap, revision]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !styleReadyRef.current) return;
    const region = props.regions.find((item) => item.id === props.selectedId);
    if (!region) { fittedSelection.current = null; return; }
    const viewport = selectionViewport(region);
    const padding = visiblePadding();
    const key = `${region.id}:${JSON.stringify(viewport)}:${JSON.stringify(padding)}`;
    if (!viewport || key === fittedSelection.current) return;
    fittedSelection.current = key;
    if (viewport.bounds) map.fitBounds(viewport.bounds, { padding, maxZoom: 9.5, duration: motionDuration() });
    else map.easeTo({ center: viewport.center, padding, zoom: Math.max(map.getZoom(), 7), duration: motionDuration() });
  }, [props.selectedId, props.regions, revision, visiblePadding]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !styleReadyRef.current || !props.viewRequest) return;
    const { camera } = props.viewRequest;
    map.easeTo({ center: [camera.longitude, camera.latitude], zoom: camera.zoom, duration: motionDuration() });
  }, [props.viewRequest?.id]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !styleReadyRef.current) return;
    syncOverlays(map, props.overlays);
  }, [props.overlays, revision]);

  useEffect(() => { if (choices.length) choiceRef.current?.querySelector<HTMLButtonElement>('button')?.focus(); }, [choices]);

  const reset = () => {
    setChoices([]);
    mapRef.current?.fitBounds(US_BOUNDS, { padding: visiblePadding(), duration: motionDuration() });
  };
  const selected = props.regions.find((region) => region.id === props.selectedId);
  const unmappable = selected && !selectionViewport(selected);
  return (
    <section className={`candidate-map ${props.className ?? ''}`} aria-label="Geographic results" onKeyDown={(event) => {
      if (event.key === 'Escape') { setChoices([]); mapRef.current?.getCanvas().focus(); }
    }}>
      <div ref={containerRef} className="candidate-map__canvas" aria-hidden={!!error} />
      <div ref={viewportRef} className="candidate-map__visible-viewport" aria-hidden="true" />
      {!error && <div className="candidate-map__controls" aria-label="Map controls">
        <button type="button" onClick={reset} aria-label="Reset map to contiguous United States" title="Reset U.S. view">U.S.</button>
        <button type="button" onClick={() => mapRef.current?.zoomIn({ duration: motionDuration() })} aria-label="Zoom in" title="Zoom in">+</button>
        <button type="button" onClick={() => mapRef.current?.zoomOut({ duration: motionDuration() })} aria-label="Zoom out" title="Zoom out">−</button>
      </div>}
      <div className="candidate-map__context">
        <p id="candidate-map-context" className="sr-only">Census 2025 U.S. state and international borders; other countries are plain generalized context. Map context is not analyzed coverage; evaluated coverage follows the selected run.</p>
        {boundaryStatus && <p role="status">{boundaryStatus}{boundaryStatus.includes('unavailable') && <button type="button" onClick={() => boundaryDetailsRef.current?.retry()}>Retry boundary detail</button>}</p>}
      </div>
      {(mapNote || unmappable) && !error && <div className="candidate-map__note" role="status"><p>{unmappable
        ? 'This region has no valid polygon or reported centroid. It remains available in the results list.' : mapNote}</p>
        {mapNote && !unmappable && <button type="button" onClick={() => setRetry((number) => number + 1)}>Retry map</button>}</div>}
      {!!choices.length && !error && <div ref={choiceRef} className="candidate-map__choices" role="dialog" aria-label="Overlapping region alternatives">
        <div className="candidate-map__choices-heading"><strong>{choices.length} alternatives at this location</strong>
          <button type="button" onClick={() => { setChoices([]); mapRef.current?.getCanvas().focus(); }} aria-label="Close alternatives">×</button></div>
        <p>Choose a region or cooling alternative under this tap.</p>
        <ul>{choices.map((region) => <li key={region.id}><button type="button" aria-pressed={region.id === props.selectedId}
          onClick={() => props.onSelect(region.id)}>
          <span>{region.rank === null ? '—' : `#${region.rank}`}</span><span>{regionName(region)}<small>{shortCooling(coolingName(region.designId))} · {statusWord(region.screeningStatus)}</small></span>
        </button></li>)}</ul>
      </div>}
      {error && <div className="candidate-map__error" role="status"><strong>Map unavailable</strong><p>{error}</p>
        <button type="button" onClick={() => setRetry((number) => number + 1)}>Retry map</button></div>}
    </section>
  );
}

export default CandidateMap;
