import { useCallback, useEffect, useMemo, useRef, useState, type CSSProperties, type ReactNode } from 'react';
import { AlertTriangle, Compass, Globe2, Map as MapIcon, PanelLeftClose, PanelLeftOpen, RefreshCw } from 'lucide-react';
import { CandidateMap } from '../../map/CandidateMap';
import { DEFAULT_BASEMAP } from '../../map/mapStyle';
import { MobileSheet } from '../MobileSheet';
import { FeatureInformation } from '../FeatureInformation';
import { useMobile } from '../../hooks/useMobile';
import { useRediscovery } from '../../hooks/useRediscovery';
import { rediscoveryApi, type RediscoveryApi } from '../../api/rediscovery';
import type { MapCamera, MapFeatureInfo } from '../../types/domain';
import { ALL_LAYERS, buildOverlays, COLORS, overlayGeometry, type LayerVisibility } from './overlayData';
import { storySteps } from './story';
import { StoryBar } from './StoryBar';
import { CandidateDetails } from './CandidateDetails';
import { ValidationDashboard, placeName } from './ValidationDashboard';
import './rediscovery.css';

const NO_REGIONS: never[] = [];
const NO_LAYERS: never[] = [];
const ignore = () => undefined;
const DEFAULT_TOP_N = 100;
const BASEMAP = { ...DEFAULT_BASEMAP, forest: false };

function urlNumber(key: string): number | null {
  const value = Number(new URLSearchParams(window.location.search).get(key));
  return Number.isInteger(value) && value > 0 ? value : null;
}
function writeParams(values: Record<string, string | null>) {
  const url = new URL(window.location.href);
  for (const [key, value] of Object.entries(values)) { if (value) url.searchParams.set(key, value); else url.searchParams.delete(key); }
  window.history.replaceState(window.history.state, '', url);
}

/**
 * Post-hoc rediscovery check: the deterministic model's blind national candidates compared with existing
 * data centers. Every number shown comes from the backend analysis; the browser only filters by the chosen N,
 * toggles layers and formats text.
 */
export function RediscoveryWorkspace({ viewSwitch, api = rediscoveryApi, demo = false }: { viewSwitch: ReactNode; api?: RediscoveryApi; demo?: boolean }) {
  const mobile = useMobile();
  const [requestedId] = useState(() => new URLSearchParams(window.location.search).get('analysis'));
  const [attempt, setAttempt] = useState(0);
  const { result, state, error } = useRediscovery(requestedId, attempt, api, !demo);
  const [requestedTopN, setRequestedTopN] = useState(() => urlNumber('top') ?? DEFAULT_TOP_N);
  const [layers, setLayers] = useState<LayerVisibility>(ALL_LAYERS);
  const [selectedRank, setSelectedRank] = useState<number | null>(() => urlNumber('candidate'));
  const [stepIndex, setStepIndex] = useState<number | null>(null);
  const [viewRequest, setViewRequest] = useState<{ camera: MapCamera; id: number } | undefined>();
  const [projection, setProjection] = useState<'mercator' | 'globe'>('mercator');
  const [railOpen, setRailOpen] = useState(true);
  const [facility, setFacility] = useState<MapFeatureInfo | null>(null);
  const [sheetHeight, setSheetHeight] = useState(42);
  const topValues = result?.parameters.topNValues ?? [];
  const topN = topValues.includes(requestedTopN) ? requestedTopN
    : topValues.filter(value => value <= DEFAULT_TOP_N).at(-1) ?? topValues[0] ?? requestedTopN;
  const geometry = useMemo(() => result ? overlayGeometry(result, topN) : null, [result, topN]);
  const overlays = useMemo(() => result && geometry ? buildOverlays(result, geometry, layers, selectedRank) : undefined, [result, geometry, layers, selectedRank]);
  const steps = useMemo(() => result ? storySteps(result, topN) : [], [result, topN]);
  const selected = result?.candidates.find(candidate => candidate.rank === selectedRank) ?? null;
  const shown = result?.candidates.slice(0, topN) ?? [];
  const counts = result?.classificationCounts[String(topN)];

  const fly = useCallback((camera: MapCamera) => setViewRequest({ camera, id: Date.now() + Math.random() }), []);
  const select = useCallback((rank: number | null, focus = true) => {
    setSelectedRank(rank); setFacility(null); writeParams({ candidate: rank === null ? null : String(rank) });
    const candidate = rank === null ? null : result?.candidates.find(item => item.rank === rank);
    if (candidate && focus) fly({ latitude: candidate.lat, longitude: candidate.lon, zoom: 7.5 });
  }, [fly, result]);
  // The map mounts once the result is known, so a candidate restored from the URL is its initial view.
  const initialRank = useRef(selectedRank);
  const initialCamera = useMemo<MapCamera | undefined>(() => {
    const candidate = result?.candidates.find(item => item.rank === initialRank.current);
    return candidate ? { latitude: candidate.lat, longitude: candidate.lon, zoom: 7.5 } : undefined;
  }, [result]);
  const goToStep = (index: number) => {
    const step = steps[index];
    if (!step) return;
    setStepIndex(index); setLayers(step.layers); setFacility(null);
    setSelectedRank(step.selectRank); writeParams({ candidate: step.selectRank === null ? null : String(step.selectRank) });
    if (step.camera) fly(step.camera);
  };
  const exitStory = () => { setStepIndex(null); setLayers(ALL_LAYERS); };
  const changeTopN = (value: number) => { setRequestedTopN(value); writeParams({ top: String(value) }); };
  const toggle = (key: keyof LayerVisibility) => setLayers(value => ({ ...value, [key]: !value[key] }));
  const onOverlaySelect = useCallback((id: string) => {
    if (id.startsWith('candidate:')) { select(Number(id.slice('candidate:'.length)), false); return; }
    const record = result?.facilities.find(item => `facility:${item.facilityId}` === id);
    if (record) setFacility({ title: record.name ?? record.operator ?? 'Existing data center record', status: 'observed',
      properties: { operator: record.operator, county: record.county, state: record.stateAbbr, footprint: record.footprintType,
        footprint_sqft: record.footprintSqft, hub: record.hubId, source: `${result!.facilitySource.name} ${result!.facilitySource.version.split(' (')[0]}`,
        role: 'External validation only; never a model input' } });
  }, [result, select]);
  useEffect(() => {
    const escape = (event: KeyboardEvent) => { if (event.key !== 'Escape') return; if (facility) setFacility(null); else if (selectedRank !== null) select(null, false); };
    window.addEventListener('keydown', escape);
    return () => window.removeEventListener('keydown', escape);
  }, [facility, selectedRank, select]);

  const highlight = stepIndex === null ? null : steps[stepIndex]?.section ?? null;
  const dashboard = result ? <ValidationDashboard result={result} topN={topN} onTopN={changeTopN} selectedRank={selectedRank} onSelect={rank => select(rank)} highlight={highlight} />
    : <div className="idle-message">{state === 'LOADING' ? <><span className="loading-spinner" /><h2>Loading the rediscovery check…</h2><p>Reading the verified analysis artifacts.</p></>
      : demo ? <><h2>Real analysis required</h2><p>The rediscovery check compares real model outputs with a real facility inventory. No demo fixture is provided, so it is unavailable in DEMO DATA mode.</p></>
      : state === 'EMPTY' ? <><h2>No rediscovery analysis yet</h2><p>Run <code>.venv\Scripts\python.exe -m dc_rediscovery run --acquire</code> from the project root, then reload.</p></>
      : <><h2>Rediscovery check unavailable</h2><p>{error}</p><button className="text-button" onClick={() => setAttempt(value => value + 1)}><RefreshCw size={13} />Retry</button></>}</div>;
  const details = selected && result ? <CandidateDetails candidate={selected} result={result} onClose={() => select(null, false)} /> : null;
  const chips: { key: keyof LayerVisibility; label: string; swatch: CSSProperties; available: boolean }[] = result ? [
    { key: 'facilities', label: `Existing data centers (${result.facilities.length.toLocaleString('en-US')})`, swatch: { background: COLORS.facility }, available: true },
    { key: 'candidates', label: `Model candidates (Top ${topN})`, swatch: { background: COLORS.candidate }, available: true },
    { key: 'validated', label: `Validated ≤ ${result.parameters.validatedMaxKm} km (${counts?.validated ?? 0})`, swatch: { background: COLORS.validated }, available: true },
    { key: 'emerging', label: `Emerging > ${result.parameters.emergingMinKm} km (${counts?.emerging ?? 0})`, swatch: { background: '#fffefa', border: `2px dashed ${COLORS.emerging}`, outline: `1px solid ${COLORS.emergingOutline}` }, available: true },
    { key: 'surface', label: 'Model score surface', swatch: { background: 'linear-gradient(90deg, #22343c22, #22343ccc)' }, available: !!result.surface },
  ] : [];

  return <div className="locator-app rd-app">
    <header className="app-header"><a className="brand" href={window.location.pathname} aria-label="Sustainable Data Center Locator home"><span className="brand-mark"><Compass size={23} /></span><span><strong>Sustainable Data Center Locator</strong><small>Geographic decision support</small></span></a>
      <div className="header-context">{viewSwitch}<span className="model-control">Model <strong>Grid model · national 1 km surface</strong></span></div></header>
    <main className={`workspace ${railOpen ? '' : 'rail-collapsed'} ${details ? 'has-detail' : ''}`} style={{ '--mobile-map-bottom': `${sheetHeight}dvh` } as CSSProperties}>
      {!mobile && <aside className="desktop-rail" aria-label="Validation results"><div className="rail-inner"><div className="rail-scroll">{dashboard}</div></div></aside>}
      <section className="map-workspace" aria-label="Rediscovery map">
        {state !== 'LOADING' && <CandidateMap regions={NO_REGIONS} selectedId={null} onSelect={ignore} layers={NO_LAYERS} layerSelections={NO_LAYERS} projection={projection}
          basemap={BASEMAP} overlays={overlays} onOverlaySelect={onOverlaySelect} viewRequest={viewRequest} camera={initialCamera} />}
        <div className="map-toolbar">
          {!mobile && <button className="icon-button rail-toggle" aria-label={railOpen ? 'Collapse validation panel' : 'Expand validation panel'} onClick={() => setRailOpen(!railOpen)}>{railOpen ? <PanelLeftClose size={19} /> : <PanelLeftOpen size={19} />}</button>}
          {result && <p className="rd-map-title"><strong>Top {topN}</strong> blind candidates vs. {result.facilities.length.toLocaleString('en-US')} existing facility records</p>}
          <button className="icon-button projection-toggle" aria-label={projection === 'mercator' ? 'Show globe view' : 'Show map view'} onClick={() => setProjection(projection === 'mercator' ? 'globe' : 'mercator')}>{projection === 'mercator' ? <Globe2 size={18} /> : <MapIcon size={18} />}</button>
        </div>
        {state === 'ERROR' && <div className="map-status" role="alert"><AlertTriangle size={16} /><span>{error}</span><button className="text-button" onClick={() => setAttempt(value => value + 1)}><RefreshCw size={13} />Retry</button></div>}
        {result && <div className="rd-map-controls">
          <div className="rd-chips" role="group" aria-label="Rediscovery layers">{chips.map(chip => <button key={chip.key} type="button" className="rd-chip" aria-pressed={layers[chip.key]}
            disabled={!chip.available} title={chip.available ? undefined : 'No score surface image in this analysis'} onClick={() => toggle(chip.key)}>
            <i className="rd-swatch" style={chip.swatch} aria-hidden="true" />{chip.label}</button>)}</div>
          <StoryBar steps={steps} index={stepIndex} onIndex={goToStep} onExit={exitStory} />
        </div>}
        {result && layers.surface && result.surface && <div className="rd-surface-legend" aria-label="Score surface legend"><span>Score ≤ {result.surface.scoreLow.toFixed(1)} (median)</span><i aria-hidden="true" /><span>{result.surface.scoreHigh.toFixed(1)} (max)</span></div>}
        {facility && <FeatureInformation feature={facility} onClose={() => setFacility(null)} />}
        {selected && !layers.candidates && <p className="rd-hidden-note" role="status">Candidate {selected.rank} is selected. Turn on Model candidates to see every point.</p>}
      </section>
      {!mobile && details}
      {mobile && <MobileSheet className={details ? 'detail-active' : ''} onHeightChange={setSheetHeight} selectionKey={selected ? String(selected.rank) : null}>{details ?? <div className="rail-inner"><div className="rail-scroll">{dashboard}</div></div>}</MobileSheet>}
    </main>
    <footer className="app-footer"><span>{result?.interpretation ?? 'Candidates are search areas for further investigation, not approved sites.'}</span>
      <span className="footer-coverage">{result ? `${shown.length} candidates · ${result.model.cellsValued.toLocaleString('en-US')} valued 1 km cells · ${result.analysisName}${selected ? ` · selected #${selected.rank} ${placeName(selected)}` : ''}` : 'Rediscovery check'}</span></footer>
  </div>;
}
