import { useCallback, useEffect, useMemo, useRef, useState, type CSSProperties } from 'react';
import { Compass, PanelLeftClose, PanelLeftOpen, Globe2, Map, RefreshCw, AlertTriangle, ArrowUpRight } from 'lucide-react';
import { locatorApi, isDemoMode } from './api/client';
import { readUrlState, writeUrlState } from './utils/url';
import type { Capabilities, FacilityConfiguration, LayerSelection, MapCamera, MapFeatureInfo } from './types/domain';
import { CandidateMap } from './map/CandidateMap';
import { ConfigurationForm } from './components/ConfigurationForm';
import { RegionList } from './components/RegionList';
import { RegionDetails } from './components/RegionDetails';
import { Comparison } from './components/Comparison';
import { MobileSheet } from './components/MobileSheet';
import { LayerControls } from './components/LayerControls';
import { IndicatorEvidence } from './components/IndicatorEvidence';
import { FeatureInformation } from './components/FeatureInformation';
import { MonteCarloEvidence } from './components/MonteCarloEvidence';
import { RequestNotice } from './components/RequestNotice';
import { useLocator } from './hooks/useLocator';
import { useLayers } from './hooks/useLayers';
import { useMobile } from './hooks/useMobile';
import './styles.css';

const DEFAULT: FacilityConfiguration = { peakItPowerMw: 100, averageLoadPercent: 80, targetOpeningYear: 2030, lifetimeYears: 25, cooling: 'all', weighting: 'equal', screeningMode: 'STRICT', groupWeights: {}, ahpMatrix: null };
// Before capabilities arrive, label the explicitly selected service without claiming its coverage.
const isCountyModel = import.meta.env.VITE_MODEL_BACKEND === 'monte-carlo';
/** Keep the map workspace design while switching evidence semantics by selected backend. */
export default function App() {
  const initialUrl = useRef(readUrlState()).current;
  const mobile = useMobile();
  const [capabilities, setCapabilities] = useState<Capabilities | null>(null);
  const [capabilityError, setCapabilityError] = useState<string | null>(null);
  const [capabilityAttempt, setCapabilityAttempt] = useState(0);
  const [configuration, setConfiguration] = useState<FacilityConfiguration>({ ...DEFAULT, ...initialUrl.configuration });
  const [selectedId, setSelectedId] = useState<string | null>(initialUrl.regionId);
  const [scenarioId, setScenarioId] = useState(initialUrl.scenarioId);
  const [layerSelections, setLayerSelections] = useState<LayerSelection[]>(initialUrl.layers);
  const [camera, setCamera] = useState<MapCamera | undefined>(initialUrl.camera);
  const [projection, setProjection] = useState<'mercator' | 'globe'>('mercator');
  const [railOpen, setRailOpen] = useState(true);
  const [sheetHeight, setSheetHeight] = useState(initialUrl.regionId ? 48 : 42);
  const [tab, setTab] = useState<'configure' | 'results'>('configure');
  const [comparisonIds, setComparisonIds] = useState<string[]>([]);
  const [comparisonOpen, setComparisonOpen] = useState(false);
  const [paretoOnly, setParetoOnly] = useState(false);
  const [conditionalOnly, setConditionalOnly] = useState(false);
  const [minimumScore, setMinimumScore] = useState(0);
  const [feature, setFeature] = useState<MapFeatureInfo | null>(null);
  const restored = useRef(false);
  const configured = useRef(false);
  const edited = useRef(false);
  const lastRequest = useRef<{ type: 'search'; configuration: FacilityConfiguration } | { type: 'run'; runId: string; scenarioId: string } | null>(null);
  const { result, state, stage, error, search, load } = useLocator();
  const { layers, errors: layerErrors, loading: layersLoading } = useLayers(result, layerSelections);
  // County runs use physical tradeoffs, representative points and their actual structural scenarios.
  const county = result?.modelKind === 'monte-carlo' || capabilities?.modelKind === 'monte-carlo';
  const scenarioOptions = result?.structuralScenarios ?? capabilities?.scenarios;
  const stale = !!result && (state === 'LOADING' || state === 'ERROR');
  const changed = !!result && JSON.stringify(result.configuration) !== JSON.stringify(configuration);
  const demo = isDemoMode || !!capabilities?.demo || !!result?.demo;

  useEffect(() => {
    const controller = new AbortController(); let active = true; setCapabilityError(null);
    locatorApi.capabilities(controller.signal).then(value => {
      if (!active) return;
      setCapabilities(value);
      if (!configured.current) { configured.current = true; setConfiguration(old => edited.current ? { ...value.defaultConfiguration, ...old, groupWeights: Object.keys(old.groupWeights).length ? old.groupWeights : value.defaultConfiguration.groupWeights } : { ...value.defaultConfiguration, ...initialUrl.configuration }); }
      setLayerSelections(old => old.map(selection => ({ ...selection, enabled: selection.enabled && !!value.layers.find(layer => layer.id === selection.id)?.available })));
      if (!restored.current && initialUrl.runId) {
        restored.current = true; setTab('results');
        lastRequest.current = { type: 'run', runId: initialUrl.runId, scenarioId: initialUrl.scenarioId };
        void load(initialUrl.runId, initialUrl.scenarioId);
      }
    }).catch(cause => { if (active && !controller.signal.aborted) setCapabilityError(cause instanceof Error ? cause.message : 'Capabilities are unavailable.'); });
    return () => { active = false; controller.abort(); };
  }, [capabilityAttempt, load, initialUrl]);
  useEffect(() => {
    if (!result) return;
    setComparisonIds(ids => ids.filter(id => result.regions.some(region => region.id === id)));
    const restoredSelection = selectedId && result.regions.some(region => region.id === selectedId) ? selectedId : null;
    setSelectedId(restoredSelection);
    if (lastRequest.current?.type === 'run' && !edited.current) setConfiguration({ ...result.configuration, ...initialUrl.configuration });
    setScenarioId(result.scenarioId); setFeature(null);
    writeUrlState({ runId: result.runId, scenarioId: result.scenarioId, regionId: restoredSelection });
  }, [result]);
  const visibleRegions = useMemo(() => (result?.regions ?? []).filter(region => (!paretoOnly || region.paretoOptimal === true) && (!conditionalOnly || region.screeningStatus === 'CONDITIONAL') && (minimumScore === 0 || (region.score !== null && region.score >= minimumScore))), [result, paretoOnly, conditionalOnly, minimumScore]);
  const selectionHidden = !!selectedId && !!result && !visibleRegions.some(region => region.id === selectedId);
  const selected = result?.regions.find(region => region.id === selectedId) ?? null;
  const compared = result?.regions.filter(region => comparisonIds.includes(region.id)) ?? [];
  const mapRegions = selectionHidden && selected ? [...visibleRegions, selected] : visibleRegions;
  const select = useCallback((id: string) => { setSelectedId(id); setFeature(null); writeUrlState({ regionId: id }); }, []);
  const closeSelection = () => { setSelectedId(null); writeUrlState({ regionId: null }); };
  const compare = (id: string) => setComparisonIds(ids => ids.includes(id) ? ids.filter(value => value !== id) : ids.length < 3 ? [...ids, id] : ids);
  const changeLayers = (values: LayerSelection[]) => { setLayerSelections(values); writeUrlState({ layers: values }); };
  const cameraChanged = useCallback((value: MapCamera) => { setCamera(value); writeUrlState({ camera: value }); }, []);
  const submit = async () => {
    setTab('results'); setComparisonOpen(false); setFeature(null); writeUrlState({ configuration });
    lastRequest.current = { type: 'search', configuration: structuredClone(configuration) };
    const value = await search(configuration);
    if (value) setScenarioId(value.scenarioId);
  };
  const changeScenario = (value: string) => { setScenarioId(value); if (result) { setComparisonOpen(false); lastRequest.current = { type: 'run', runId: result.runId, scenarioId: value }; void load(result.runId, value); } };
  const retry = () => { const request = lastRequest.current; if (request?.type === 'run') void load(request.runId, request.scenarioId); else if (request?.type === 'search') void search(request.configuration); };
  useEffect(() => { const escape = (event: KeyboardEvent) => { if (event.key !== 'Escape') return; if (comparisonOpen) setComparisonOpen(false); else if (feature) setFeature(null); else { setSelectedId(null); writeUrlState({ regionId: null }); } }; window.addEventListener('keydown', escape); return () => window.removeEventListener('keydown', escape); }, [comparisonOpen, feature]);
  const panel = <div className="rail-inner"><nav className="rail-tabs" aria-label="Workspace"><button className={tab === 'configure' ? 'active' : ''} onClick={() => setTab('configure')}>Configure</button><button className={tab === 'results' ? 'active' : ''} onClick={() => setTab('results')}>Results{result ? <span>{result.regions.length}</span> : null}</button></nav>
    {mobile && <RequestNotice state={state} stage={stage} error={error} previous={!!result} onRetry={retry} />}
    {mobile && capabilityError && <div className="request-notice error" role="alert"><p>{capabilityError}</p><button className="text-button" onClick={() => setCapabilityAttempt(value => value + 1)}>Reconnect</button></div>}
    <div className="rail-scroll">{tab === 'configure' ? <ConfigurationForm configuration={configuration} capabilities={capabilities} busy={state === 'LOADING'} onChange={value => { edited.current = true; setConfiguration(value); }} onSubmit={() => void submit()} /> : <>
      {state === 'IDLE' && <div className="idle-message"><Compass size={29} /><h2>Start with a facility.</h2><p>Evaluate a configuration to discover potential search regions. National map context is not national analyzed coverage.</p><button className="button secondary" onClick={() => setTab('configure')}>Configure a search</button></div>}
      {result && <><div className="run-summary"><p className="micro-label">{stale ? 'Previous evaluated run' : 'Evaluated configuration'}</p><strong>{result.configuration.peakItPowerMw} MW · {result.configuration.averageLoadPercent}% load</strong><p>Opening {result.configuration.targetOpeningYear} · {result.configuration.lifetimeYears} years<br />{capabilities?.coolingOptions.find(option => option.id === result.configuration.cooling)?.label ?? result.configuration.cooling}<br />{county ? 'Unweighted Pareto' : `${result.configuration.weighting} preferences`} · {result.scenarioId}<br />{result.analyzedCellCount} {result.coverageUnit ?? 'cells'} · {result.configuration.screeningMode} · {result.scope}</p><details><summary>Actual screening / search stages</summary><ul>{result.searchStages.map(value => <li key={value.label}>{value.label}: {value.count ?? 'not reported'}</li>)}</ul></details>{result.weighting && <details><summary>Backend weighting result</summary><p>{result.weighting.status} · Consistency ratio: {result.weighting.consistencyRatio ?? 'not applicable'}</p><dl>{Object.entries(result.weighting.weights).map(([id, value]) => <div key={id}><dt>{id}</dt><dd>{value}</dd></div>)}</dl></details>}</div>
        <MonteCarloEvidence result={result} /><div className="display-filters"><p className="micro-label">Display filters · ranking unchanged</p><label><input type="checkbox" checked={paretoOnly} onChange={e => setParetoOnly(e.target.checked)} />Pareto frontier only</label><label><input type="checkbox" checked={conditionalOnly} onChange={e => setConditionalOnly(e.target.checked)} />Conditional regions only</label>{!county && <label className="score-filter">Minimum representative score <output>{minimumScore}</output><input aria-label="Minimum representative score" type="range" min="0" max="100" step="1" value={minimumScore} onChange={e => setMinimumScore(Number(e.target.value))} /></label>}</div>
        <div className={stale ? 'previous-results' : ''}><RegionList regions={visibleRegions} displayCount={result.regions.length} selectedId={selectedId} comparisonIds={comparisonIds} onSelect={select} onCompare={compare} /></div>
        {selectionHidden && <p className="filtered-selection">Selected region is outside the display filters. Its details and map outline remain selected until you choose another region or close it.</p>}
      </>}
      {state === 'EMPTY' && <div className="empty-message"><h3>No regions satisfied the current hard constraints.</h3><p>{result?.configuration.screeningMode === 'STRICT' ? 'Critical Unknown requirements exclude these alternatives under strict screening.' : 'This configuration produced no qualifying regions.'} No winner is invented.</p><button className="text-button" onClick={() => setTab('configure')}>Review requirements and preferences</button></div>}
    </>}</div>
    {capabilities?.latestRunId && state === 'IDLE' && <button className="saved-run-button" onClick={() => { setTab('results'); lastRequest.current = { type: 'run', runId: capabilities.latestRunId!, scenarioId }; void load(capabilities.latestRunId!, scenarioId); }}>Load latest completed run<ArrowUpRight size={14} /></button>}
    {compared.length > 0 && <div className="comparison-tray"><span>{compared.length} / 3 selected</span><button className="button primary" onClick={() => setComparisonOpen(true)}>Compare ({compared.length})</button></div>}
  </div>;

  return <div className="locator-app"><header className="app-header"><a className="brand" href={window.location.pathname} aria-label="Sustainable Data Center Locator home"><span className="brand-mark"><Compass size={23} /></span><span><strong>Sustainable Data Center Locator</strong><small>Geographic decision support</small></span></a><div className="header-context"><span className="scope-pill">{result?.scope ?? capabilities?.scope ?? (demo ? 'Synthetic demonstration fixtures' : isCountyModel ? 'County screening API: awaiting coverage' : 'Real coverage: 42 development cells')}</span>{demo && <strong className="demo-badge">DEMO DATA</strong>}<span className="version-tag">{result?.modelVersion ?? (isCountyModel ? 'County Monte Carlo model' : 'Deterministic model')}</span></div></header>
    {demo && <div className="demo-banner">DEMO DATA · Explicit software fixtures. Values are not real geographic evidence. No automatic fallback to demo data.</div>}
    <main className={`workspace ${railOpen ? '' : 'rail-collapsed'} ${selected ? 'has-detail' : ''}`} style={{ '--mobile-map-bottom': `${sheetHeight}dvh` } as CSSProperties}>
      {!mobile && <aside className="desktop-rail" aria-label="Configuration and results">{panel}</aside>}
      <section className="map-workspace" aria-label="Geographic exploration"><CandidateMap regions={mapRegions} selectedId={selectedId} onSelect={select} layers={layers} layerSelections={layerSelections} onFeatureInfo={setFeature} camera={camera} onCameraChange={cameraChanged} projection={projection} className={stale ? 'stale-map' : ''} />
        <div className="map-toolbar"><button className="icon-button rail-toggle" aria-label={railOpen ? 'Collapse controls' : 'Expand controls'} onClick={() => setRailOpen(!railOpen)}>{railOpen ? <PanelLeftClose size={19} /> : <PanelLeftOpen size={19} />}</button><div className="scenario-control"><label htmlFor="scenario-select">External context</label><select id="scenario-select" value={scenarioId} disabled={!result || state === 'LOADING'} onChange={event => changeScenario(event.target.value)}>{(scenarioOptions ?? [{ id: 'current', label: 'Current baseline', available: true, reason: null }]).map(scenario => <option key={scenario.id} value={scenario.id} disabled={!scenario.available}>{scenario.label}{!scenario.available ? ' — ' + (scenario.reason ?? 'Unavailable source context') : ''}</option>)}</select></div><button className="icon-button projection-toggle" aria-label={projection === 'mercator' ? 'Show globe view' : 'Show map view'} onClick={() => setProjection(projection === 'mercator' ? 'globe' : 'mercator')}>{projection === 'mercator' ? <Globe2 size={18} /> : <Map size={18} />}</button></div>
        {state === 'IDLE' && !capabilityError && <div className="map-idle-note"><span className="micro-label">United States · geographic context</span><h1>A place to investigate.<br />Evidence to inspect.</h1><p>Configure a facility or load an actual saved run. {capabilities?.scope ?? (isCountyModel ? 'County coverage loads from the API.' : 'Current model coverage is 42 development cells.')}</p></div>}
        <div className="map-status" aria-label="Evaluation status" role={mobile ? undefined : state === 'ERROR' || capabilityError ? 'alert' : 'status'} aria-live={mobile ? 'off' : 'polite'}>{capabilityError ? <><AlertTriangle size={16} /><span>{capabilityError}</span>{!mobile && <button className="text-button" onClick={() => setCapabilityAttempt(value => value + 1)}>Reconnect</button>}</> : state === 'LOADING' ? <><span className="loading-spinner" /><span>{stage || 'Evaluating'}{result ? ' · previous results remain visible' : ''}</span></> : state === 'ERROR' ? <><AlertTriangle size={16} /><span>{error}{result ? ' Previous results are retained.' : ''}</span>{!mobile && <button className="text-button" onClick={retry}><RefreshCw size={13} />Retry</button>}</> : state === 'PARTIAL' ? <><AlertTriangle size={16} /><span>Results contain unresolved critical data.{changed ? ' Configuration edited; displayed results are from the last evaluated facility.' : ''}</span></> : changed ? <span>Configuration edited. Results reflect the last evaluated facility.</span> : state === 'EMPTY' ? <span>No regions satisfied the current hard constraints.</span> : state === 'SUCCESS' ? <span>Evaluation complete · inspect assumptions and evidence.</span> : <span>Ready · no regions evaluated yet.</span>}</div>
        {result?.warnings.length ? <details className="run-warnings"><summary><AlertTriangle size={13} />{result.warnings.length} model notes and limitations</summary><ul>{result.warnings.map(value => <li key={value}>{value}</li>)}</ul></details> : null}
        <div className="map-bottom-controls"><LayerControls capabilities={capabilities?.layers ?? []} selections={layerSelections} onChange={changeLayers} availableRun={!!result} /><span className="coverage-caption">Map context ≠ analyzed coverage</span></div>
        {(layersLoading || layerErrors.length > 0) && <div className="layer-status" role="status">{layersLoading ? 'Loading selected indicator…' : layerErrors.join(' ')}</div>}
        <IndicatorEvidence key={`${result?.runId}-${result?.scenarioId}`} layers={layers.filter(layer => layerSelections.some(selection => selection.id === layer.id && selection.enabled))} onInspect={setFeature} />
        {feature && <FeatureInformation feature={feature} onClose={() => setFeature(null)} />}
      </section>
      {!mobile && selected && result && <RegionDetails region={selected} result={result} onClose={closeSelection} onCompare={() => compare(selected.id)} compared={comparisonIds.includes(selected.id)} canCompare={compared.length < 3} stale={stale} />}
      {mobile && <MobileSheet className={selected ? 'detail-active' : ''} onHeightChange={setSheetHeight} selectionKey={selectedId}>{selected && result ? <RegionDetails region={selected} result={result} onClose={closeSelection} onCompare={() => compare(selected.id)} compared={comparisonIds.includes(selected.id)} canCompare={compared.length < 3} stale={stale} notice={<RequestNotice state={state} stage={stage} error={error} previous={true} onRetry={retry} />} /> : panel}</MobileSheet>}
      {comparisonOpen && compared.length > 0 && <><div className="modal-backdrop" onClick={() => setComparisonOpen(false)} /><Comparison regions={compared} onClose={() => setComparisonOpen(false)} onRemove={compare} /></>}
    </main><footer className="app-footer">Potential regions, not approved parcels. UNKNOWN ≠ zero or PASS. <span>{demo ? result ? `${result.analyzedCellCount} synthetic fixture cells` : 'Synthetic fixture coverage' : county || isCountyModel ? `${result?.analyzedCellCount ?? 'Selected'} counties` : `${result?.analyzedCellCount ?? 42} development cells`} · no national optimum claimed.</span></footer>
  </div>;
}
