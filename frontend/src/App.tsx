import { useCallback, useEffect, useMemo, useRef, useState, type CSSProperties, type ReactNode } from 'react';
import { Compass, PanelLeftClose, PanelLeftOpen, Globe2, Map, RefreshCw, AlertTriangle, FileText } from 'lucide-react';
import { locatorApi, isDemoMode, type LocatorApi } from './api/client';
import { createMonteCarloApi } from './api/monteCarlo';
import { navigationState, pushUrlState, readUrlState, writeUrlState } from './utils/url';
import { groupPlaces, matchesCountyEconomicFilters, placeAlternatives, placeNameSuffixes } from './utils/regions';
import { placeKey } from './map/mapData';
import type { Capabilities, CountyBoundaryYear, FacilityConfiguration, GridAnalysisMode, LayerSelection, MapCamera, MapFeatureInfo, ModelId, RunResult } from './types/domain';
import { CandidateMap } from './map/CandidateMap';
import { DEFAULT_BASEMAP, type BasemapVisibility } from './map/mapStyle';
import { ConfigurationForm } from './components/ConfigurationForm';
import { FacilitySummary } from './components/FacilitySummary';
import { RegionList } from './components/RegionList';
import { RegionDetails } from './components/RegionDetails';
import { RunSummary } from './components/RunSummary';
import { MapCoverage } from './components/MapCoverage';
import { Comparison } from './components/Comparison';
import { MobileSheet } from './components/MobileSheet';
import { LayerControls } from './components/LayerControls';
import { IndicatorEvidence } from './components/IndicatorEvidence';
import { FeatureInformation } from './components/FeatureInformation';
import { RequestNotice } from './components/RequestNotice';
import { DecisionBrief } from './components/DecisionBrief';
import { CountyEconomicFilters } from './components/CountyEconomicContext';
import { useLocator } from './hooks/useLocator';
import { useLayers } from './hooks/useLayers';
import { useMobile } from './hooks/useMobile';
import { useSocioeconomic } from './hooks/useSocioeconomic';
import { RediscoveryWorkspace } from './components/rediscovery/RediscoveryWorkspace';
import { ViewSwitch, readView, type AppView } from './components/rediscovery/ViewSwitch';
import './styles.css';

const DEFAULT: FacilityConfiguration = { peakItPowerMw: 100, averageLoadPercent: 80, targetOpeningYear: 2030, lifetimeYears: 25, cooling: 'all', weighting: 'equal', screeningMode: 'STRICT', groupWeights: {}, ahpMatrix: null };
const configurationSignature = (configuration: FacilityConfiguration) => JSON.stringify(configuration, (_key, value) =>
  value && typeof value === 'object' && !Array.isArray(value) ? Object.fromEntries(Object.entries(value).sort(([left], [right]) => left < right ? -1 : left > right ? 1 : 0)) : value);
/** A model change mounts a fresh workspace and cancels requests from the prior model. */
export default function App() {
  const [model, setModel] = useState<ModelId>(() => readUrlState().model);
  const api = useMemo(() => model === 'county' ? createMonteCarloApi(import.meta.env.VITE_MONTE_CARLO_API_URL ?? 'http://127.0.0.1:8000') : locatorApi, [model]);
  const changeModel = (next: ModelId) => {
    if (next === model) return;
    const url = new URL(window.location.href);
    for (const key of ['run', 'scenario', 'region', 'layers', 'mw', 'load', 'opening', 'life']) url.searchParams.delete(key);
    if (next === 'county') url.searchParams.set('model', 'county'); else url.searchParams.delete('model');
    // A new entry lets the browser's Back button return to the previous model and its results.
    window.history.pushState({ locator: true }, '', url);
    setModel(next);
  };
  // The post-hoc rediscovery check is a separate read-only view of the grid model; it never alters searches.
  const [view, setView] = useState<AppView>(() => readView());
  const changeView = (next: AppView) => {
    if (next === view) return;
    const url = new URL(window.location.href);
    if (next === 'rediscovery') url.searchParams.set('view', 'rediscovery');
    else for (const key of ['view', 'top', 'candidate', 'analysis']) url.searchParams.delete(key);
    window.history.pushState({ locator: true }, '', url);
    setView(next);
  };
  useEffect(() => {
    const restore = () => { setModel(readUrlState().model); setView(readView()); };
    window.addEventListener('popstate', restore);
    return () => window.removeEventListener('popstate', restore);
  }, []);
  const viewSwitch = <ViewSwitch view={view} onChange={changeView} />;
  if (view === 'rediscovery') return <RediscoveryWorkspace viewSwitch={viewSwitch} demo={isDemoMode} />;
  return <LocatorWorkspace key={model} model={model} api={api} onModelChange={changeModel} viewSwitch={viewSwitch} />;
}

/** Keep each model's results, configuration, scenarios and evidence caches isolated. */
function LocatorWorkspace({ model, api, onModelChange, viewSwitch }: { model: ModelId; api: LocatorApi; onModelChange: (model: ModelId) => void; viewSwitch?: ReactNode }) {
  const initialUrl = useRef(readUrlState()).current;
  const mobile = useMobile();
  const [capabilities, setCapabilities] = useState<Capabilities | null>(null);
  const [capabilityError, setCapabilityError] = useState<string | null>(null);
  const [capabilityAttempt, setCapabilityAttempt] = useState(0);
  const [configuration, setConfiguration] = useState<FacilityConfiguration>({ ...DEFAULT, ...initialUrl.configuration });
  const [selectedId, setSelectedId] = useState<string | null>(initialUrl.regionId);
  const [scenarioId, setScenarioId] = useState(initialUrl.scenarioId);
  const [analysisMode, setAnalysisMode] = useState<GridAnalysisMode | undefined>();
  const [layerSelections, setLayerSelections] = useState<LayerSelection[]>(initialUrl.layers);
  const [camera, setCamera] = useState<MapCamera | undefined>(initialUrl.camera);
  const [projection, setProjection] = useState<'mercator' | 'globe'>('mercator');
  const [basemap, setBasemap] = useState<BasemapVisibility>(DEFAULT_BASEMAP);
  const localBasemap = !import.meta.env.VITE_MAP_STYLE_URL;
  const [railOpen, setRailOpen] = useState(true);
  const [sheetHeight, setSheetHeight] = useState(initialUrl.regionId ? 48 : 42);
  const [editing, setEditing] = useState(false);
  const [viewRequest, setViewRequest] = useState<{ camera: MapCamera; id: number }>();
  const [comparisonIds, setComparisonIds] = useState<string[]>([]);
  const [comparisonOpen, setComparisonOpen] = useState(false);
  const [briefOpen, setBriefOpen] = useState(false);
  const [paretoOnly, setParetoOnly] = useState(false);
  const [conditionalOnly, setConditionalOnly] = useState(false);
  const [minimumScore, setMinimumScore] = useState(0);
  const [countyBoundaryYear, setCountyBoundaryYear] = useState<CountyBoundaryYear>(2025);
  const [minimumCountyPoverty, setMinimumCountyPoverty] = useState('');
  const [maximumCountyIncome, setMaximumCountyIncome] = useState('');
  const [minimumPovertyPercentile, setMinimumPovertyPercentile] = useState('');
  const [minimumLowIncomePercentile, setMinimumLowIncomePercentile] = useState('');
  const [feature, setFeature] = useState<MapFeatureInfo | null>(null);
  const restored = useRef(false);
  const configured = useRef(false);
  const edited = useRef(false);
  const shownResult = useRef<RunResult | null>(null);
  const lastRequest = useRef<{ type: 'search'; configuration: FacilityConfiguration; analysisMode?: GridAnalysisMode } | { type: 'run'; runId: string; scenarioId: string } | null>(null);
  const { result, origin, state, stage, error, search, load } = useLocator(api);
  // Current values for the history handlers, which outlive individual renders.
  const live = useRef({ result, editing, selectedId }); live.current = { result, editing, selectedId };
  const viewRequests = useRef(0);
  const { layers, errors: layerErrors, loading: layersLoading } = useLayers(result, layerSelections, selectedId, countyBoundaryYear, api);
  const economicAvailable = !!capabilities?.layers.find(layer => layer.id === 'community_economic')?.available;
  const { context: economicContext, loading: economicLoading, error: economicError } = useSocioeconomic(result?.runId ?? null, countyBoundaryYear, result?.scenarioId ?? 'current', economicAvailable, api);
  const stale = !!result && (state === 'LOADING' || state === 'ERROR');
  const changed = !!result && configurationSignature(result.configuration) !== configurationSignature(configuration);
  const demo = (model === 'grid' && isDemoMode) || !!capabilities?.demo || !!result?.demo;
  const county = model === 'county';
  const coolingOptions = capabilities?.coolingOptions ?? [];

  useEffect(() => {
    const controller = new AbortController(); let active = true; setCapabilityError(null);
    api.capabilities(controller.signal).then(value => {
      if (!active) return;
      setCapabilities(value);
      if (model === 'grid') setAnalysisMode(previous => {
        const modes = value.analysisModes;
        if (!modes?.length) return undefined;
        if (previous && modes.some(mode => mode.id === previous && mode.available)) return previous;
        return modes.find(mode => mode.id === value.defaultAnalysisMode && mode.available)?.id
          ?? modes.find(mode => mode.id === 'full_rediscovery' && mode.available)?.id
          ?? modes.find(mode => mode.available)?.id;
      });
      if (!configured.current) { configured.current = true; setConfiguration(old => edited.current ? { ...value.defaultConfiguration, ...old, groupWeights: Object.keys(old.groupWeights).length ? old.groupWeights : value.defaultConfiguration.groupWeights } : { ...value.defaultConfiguration, ...initialUrl.configuration }); }
      setLayerSelections(old => old.filter(selection => selection.id !== 'community_economic').map(selection => ({ ...selection, enabled: selection.enabled && !!value.layers.find(layer => layer.id === selection.id)?.available })));
      if (!restored.current) {
        restored.current = true;
        // A fresh page waits for the user's facility; only a link that names a run reopens completed results.
        // The start entry is marked as the form, so Back from later results returns to it.
        if (initialUrl.runId) {
          if (edited.current) setEditing(true);
          lastRequest.current = { type: 'run', runId: initialUrl.runId, scenarioId: initialUrl.scenarioId };
          void load(initialUrl.runId, initialUrl.scenarioId);
        } else writeUrlState({}, { locator: true, editing: true });
      }
    }).catch(cause => { if (active && !controller.signal.aborted) setCapabilityError(cause instanceof Error ? cause.message : 'Capabilities are unavailable.'); });
    return () => { active = false; controller.abort(); };
  }, [capabilityAttempt, load, initialUrl, api, model]);
  useEffect(() => {
    if (!result) return;
    const previous = shownResult.current; shownResult.current = result;
    setBriefOpen(false);
    setComparisonIds(ids => ids.filter(id => result.regions.some(region => region.id === id)));
    const restoredSelection = selectedId && result.regions.some(region => region.id === selectedId) ? selectedId : null;
    setSelectedId(restoredSelection);
    // A loaded run brings its own facility unless the form holds edits the user has not evaluated yet;
    // explicit URL facility fields apply to the first restored run only.
    const pendingEdits = previous ? configurationSignature(configuration) !== configurationSignature(previous.configuration) : edited.current;
    if (lastRequest.current?.type === 'run' && !pendingEdits) setConfiguration({ ...result.configuration, ...(previous ? {} : initialUrl.configuration) });
    setScenarioId(result.scenarioId); setFeature(null);
    writeUrlState({ runId: result.runId, scenarioId: result.scenarioId, regionId: restoredSelection });
  }, [result]);
  const economicFilters = useMemo(() => ({
    minimumPovertyRatePct: minimumCountyPoverty === '' ? null : Number(minimumCountyPoverty),
    maximumMedianHouseholdIncomeUsd: maximumCountyIncome === '' ? null : Number(maximumCountyIncome),
    minimumPovertyPercentile: minimumPovertyPercentile === '' ? null : Number(minimumPovertyPercentile),
    minimumLowIncomePercentile: minimumLowIncomePercentile === '' ? null : Number(minimumLowIncomePercentile),
  }), [minimumCountyPoverty, maximumCountyIncome, minimumPovertyPercentile, minimumLowIncomePercentile]);
  const economicFiltersActive = Object.values(economicFilters).some(value => value !== null);
  // Without an active county threshold the arriving county context cannot change the list, so the
  // map is not handed every polygon a second time.
  const filterContext = economicFiltersActive ? economicContext : null;
  const visibleRegions = useMemo(() => (result?.regions ?? []).filter(region => (!paretoOnly || region.paretoOptimal === true) && (!conditionalOnly || region.screeningStatus === 'CONDITIONAL') && (minimumScore === 0 || (region.score !== null && region.score >= minimumScore)) && matchesCountyEconomicFilters(filterContext?.available ? filterContext.regionCounties[region.id] : undefined, economicFilters)), [result, paretoOnly, conditionalOnly, minimumScore, filterContext, economicFilters]);
  const allGroups = useMemo(() => groupPlaces(result?.regions ?? []), [result]);
  // Area numbers come from all areas, so a filter never renumbers "Livingston, NY · area 2".
  const placeSuffixes = useMemo(() => placeNameSuffixes(result?.regions ?? []), [result]);
  const groups = useMemo(() => groupPlaces(visibleRegions), [visibleRegions]);
  const selectionHidden = !!selectedId && !!result && !visibleRegions.some(region => region.id === selectedId);
  const selected = result?.regions.find(region => region.id === selectedId) ?? null;
  const alternatives = useMemo(() => selected && result ? placeAlternatives(selected, result.regions) : [], [selected, result]);
  const compared = result?.regions.filter(region => comparisonIds.includes(region.id)) ?? [];
  const mapRegions = selectionHidden && selected && !economicFiltersActive ? [...visibleRegions, selected] : visibleRegions;
  const activeFilters = [paretoOnly, conditionalOnly, minimumScore > 0, ...Object.values(economicFilters).map(value => value !== null)].filter(Boolean).length;
  // Opening an area adds a history entry, so Back closes it and returns the map to the earlier view;
  // switching between open areas replaces it.
  const select = useCallback((id: string) => {
    if (live.current.selectedId) writeUrlState({ regionId: id });
    else pushUrlState({ regionId: id }, { locator: true, editing: live.current.editing });
    setSelectedId(id); setFeature(null);
  }, []);
  const closeSelection = () => { setSelectedId(null); writeUrlState({ regionId: null }); };
  const compare = (id: string) => setComparisonIds(ids => ids.includes(id) ? ids.filter(value => value !== id) : ids.length < 3 ? [...ids, id] : ids);
  const changeLayers = (values: LayerSelection[]) => {
    const selections = values.filter(layer => layer.id !== 'community_economic');
    setLayerSelections(selections); writeUrlState({ layers: selections });
  };
  const changeCountyBoundary = (year: CountyBoundaryYear) => {
    setCountyBoundaryYear(year); setFeature(null);
  };
  const cameraChanged = useCallback((value: MapCamera) => { setCamera(value); writeUrlState({ camera: value }); }, []);
  const submit = async () => {
    // The editor's history entry becomes the new results' entry, so Back returns to the previous results;
    // the first search from the start form adds its own entry, so Back returns to the form.
    setEditing(false); setComparisonOpen(false); setFeature(null);
    if (live.current.result) writeUrlState({ configuration }, { locator: true }); else pushUrlState({ configuration }, { locator: true });
    const submittedMode = model === 'grid' ? analysisMode : undefined;
    lastRequest.current = { type: 'search', configuration: structuredClone(configuration), analysisMode: submittedMode };
    const value = await search(configuration, submittedMode);
    if (value) setScenarioId(value.scenarioId);
  };
  const changeScenario = (value: string) => { setScenarioId(value); if (result) { setComparisonOpen(false); lastRequest.current = { type: 'run', runId: result.runId, scenarioId: value }; void load(result.runId, value); } };
  const retry = () => { const request = lastRequest.current; if (request?.type === 'run') void load(request.runId, request.scenarioId); else if (request?.type === 'search') void search(request.configuration, request.analysisMode); };
  const loadSaved = (runId: string) => {
    pushUrlState({ runId, scenarioId: 'current', regionId: null }, { locator: true, editing });
    setSelectedId(null); setFeature(null); setComparisonOpen(false);
    lastRequest.current = { type: 'run', runId, scenarioId: 'current' };
    void load(runId, 'current');
  };
  /** Closing the editor discards unevaluated edits, so the summary and results describe the same facility. */
  const cancelEdit = () => { if (live.current.result) setConfiguration(live.current.result.configuration); edited.current = false; setEditing(false); };
  const openEditor = () => { pushUrlState({}, { locator: true, editing: true, editorEntry: true }); setEditing(true); };
  /** Steps back over the entry the editor added; otherwise (e.g. another run loaded meanwhile) closes it in place. */
  const backToResults = () => {
    if (navigationState()?.editorEntry) window.history.back();
    else { cancelEdit(); writeUrlState({}, { locator: true }); }
  };
  useEffect(() => {
    // Back and Forward restore the stored view: editor open or closed, run and scenario, open area and map view.
    const restore = () => {
      const url = readUrlState();
      if (url.model !== model) return; // App switches the model, which remounts this workspace.
      const { result: shown, editing: open } = live.current;
      const wantEditing = !!navigationState()?.editing;
      if (open && !wantEditing) cancelEdit(); else if (!open && wantEditing) setEditing(true);
      setSelectedId(url.regionId); setFeature(null); setBriefOpen(false); setComparisonOpen(false);
      if (url.runId && (url.runId !== shown?.runId || url.scenarioId !== shown?.scenarioId)) {
        lastRequest.current = { type: 'run', runId: url.runId, scenarioId: url.scenarioId };
        void load(url.runId, url.scenarioId);
      }
      if (url.camera && !url.regionId) { setCamera(url.camera); setViewRequest({ camera: url.camera, id: ++viewRequests.current }); }
    };
    window.addEventListener('popstate', restore);
    return () => window.removeEventListener('popstate', restore);
  }, [model, load]);
  const nationwideRunId = model === 'grid' ? capabilities?.nationwideRegionalRunId : null;
  const loadNationwide = nationwideRunId && result?.runId !== nationwideRunId ? () => loadSaved(nationwideRunId) : undefined;
  const loadParent = result?.analysis?.parentRunId ? () => loadSaved(result.analysis!.parentRunId!) : undefined;
  // Completed results stay one optional click away from the start form; nothing loads until asked.
  const savedStartId = nationwideRunId ?? capabilities?.latestRunId ?? null;
  const openSavedStart = savedStartId ? () => loadSaved(savedStartId) : undefined;
  const openBrief = () => { setComparisonOpen(false); setBriefOpen(true); };
  useEffect(() => { const escape = (event: KeyboardEvent) => { if (event.key !== 'Escape') return; if (briefOpen) setBriefOpen(false); else if (comparisonOpen) setComparisonOpen(false); else if (feature) setFeature(null); else { setSelectedId(null); writeUrlState({ regionId: null }); } }; window.addEventListener('keydown', escape); return () => window.removeEventListener('keydown', escape); }, [briefOpen, comparisonOpen, feature]);
  const statusVisible = !!capabilityError || state === 'LOADING' || state === 'ERROR' || changed;
  const details = (notice?: ReactNode) => selected && result ? <RegionDetails region={selected} nameSuffix={placeSuffixes.get(placeKey(selected))} result={result} alternatives={alternatives} coolingOptions={coolingOptions} onSelectAlternative={select} onClose={closeSelection} onCompare={() => compare(selected.id)} compared={comparisonIds.includes(selected.id)} canCompare={compared.length < 3} stale={stale} notice={notice} economicContext={economicContext} economicLoading={economicLoading} economicError={economicError} /> : null;
  const loadingSaved = state === 'LOADING' && lastRequest.current?.type === 'run';
  const searching = state === 'LOADING' && lastRequest.current?.type === 'search';
  // One panel: the facility (summary or inline editor) above its results, so no step switching is needed.
  const formOpen = editing || (!result && !loadingSaved);
  const panel = <div className="rail-inner">
    {mobile && <RequestNotice state={state} stage={stage} error={error} previous={!!result} onRetry={retry} />}
    {mobile && capabilityError && <div className="request-notice error" role="alert"><p>{capabilityError}</p><button className="text-button" onClick={() => setCapabilityAttempt(value => value + 1)}>Reconnect</button></div>}
    <div className="rail-scroll">
      {formOpen ? <ConfigurationForm configuration={configuration} capabilities={capabilities} busy={searching} analysisMode={model === 'grid' ? analysisMode : undefined} onAnalysisModeChange={model === 'grid' ? setAnalysisMode : undefined} onChange={value => { edited.current = true; setConfiguration(value); }} onSubmit={() => void submit()} onCancel={result ? backToResults : undefined} />
        : result && <FacilitySummary configuration={result.configuration} county={county} coolingOptions={coolingOptions} saved={origin === 'saved'} stale={stale} onEdit={openEditor} />}
      {formOpen && !result && !searching && openSavedStart && <p className="form-note">Or <button className="text-button" type="button" onClick={openSavedStart}>open saved results</button> instead; nothing is recomputed.</p>}
      {state === 'LOADING' && !result && !mobile && <div className="idle-message"><span className="loading-spinner" />{loadingSaved ? <><h2>Loading search areas…</h2><p>Opening completed model results. Nothing is recomputed.</p></> : <><h2>Searching…</h2><p>{stage || 'Preparing request'}. {analysisMode === 'cached_regional' ? 'Reevaluating the cached regional cohort for this facility and its preferences.' : 'A new facility’s first search can take several minutes; repeated searches reuse completed stages.'}</p></>}</div>}
      {result && <div className={stale ? 'previous-results' : ''}><RegionList groups={groups} total={allGroups.length} selectedId={selectedId} comparisonIds={comparisonIds} onSelect={select} onCompare={compare} coolingOptions={coolingOptions} suffixes={placeSuffixes}>
        <RunSummary result={result} groups={allGroups} onLoadParent={loadParent} />
        {result.regions.length > 0 && <details className="display-filters"><summary>Filter areas{activeFilters > 0 && <span className="filter-count">{activeFilters} active</span>}</summary><p className="micro-label">Display only · {county ? 'unweighted tradeoffs unchanged' : 'ranking unchanged'}</p><label><input type="checkbox" checked={paretoOnly} onChange={e => setParetoOnly(e.target.checked)} />Pareto frontier only</label><label><input type="checkbox" checked={conditionalOnly} onChange={e => setConditionalOnly(e.target.checked)} />Conditional regions only</label>{!county && <label className="score-filter">Minimum representative score <output>{minimumScore}</output><input aria-label="Minimum representative score" type="range" min="0" max="100" step="1" value={minimumScore} onChange={e => setMinimumScore(Number(e.target.value))} /></label>}
          {county ? <p className="form-note">County economic filters are unavailable from this model's API.</p> : <CountyEconomicFilters boundaryYear={countyBoundaryYear} onBoundaryChange={changeCountyBoundary} poverty={minimumCountyPoverty} income={maximumCountyIncome} povertyPercentile={minimumPovertyPercentile} lowIncomePercentile={minimumLowIncomePercentile} onPovertyChange={setMinimumCountyPoverty} onIncomeChange={setMaximumCountyIncome} onPovertyPercentileChange={setMinimumPovertyPercentile} onLowIncomePercentileChange={setMinimumLowIncomePercentile} onClear={() => { setMinimumCountyPoverty(''); setMaximumCountyIncome(''); setMinimumPovertyPercentile(''); setMinimumLowIncomePercentile(''); }} context={economicContext} loading={economicLoading} error={economicError} shown={groups.length} total={allGroups.length} />}
        </details>}
      </RegionList></div>}
      {selectionHidden && <p className="filtered-selection">Selected region is outside the display filters. {economicFiltersActive ? 'Its details remain selected; its polygon is excluded from the filtered map.' : 'Its details and map outline remain selected until you choose another region or close it.'}</p>}
      {state === 'EMPTY' && <div className="empty-message"><h3>No regions satisfied the current hard constraints.</h3><p>{result?.configuration.screeningMode === 'STRICT' ? 'Critical Unknown requirements exclude these alternatives under strict screening.' : 'This configuration produced no qualifying regions.'} No winner is invented.</p>{!formOpen && <button className="text-button" onClick={openEditor}>Review requirements and preferences</button>}</div>}
    </div>
    {(result || compared.length > 0) && <div className="rail-actions">{result && <button className="button secondary" onClick={openBrief}><FileText size={15} aria-hidden="true" />Decision brief</button>}{compared.length > 0 && <button className="button primary" onClick={() => setComparisonOpen(true)}>Compare ({compared.length})</button>}</div>}
  </div>;

  // One line in the footer; the full scope stays in the tooltip.
  const footerCoverage = demo ? result ? `${result.analyzedCellCount} synthetic fixture ${result.coverageUnit ?? 'cells'}` : 'Synthetic fixture coverage' : result ? `${result.analyzedCellCount.toLocaleString('en-US')} analyzed geographic ${result.coverageUnit ?? 'cells'} · ${result.modelVersion}` : capabilities?.scope ?? 'Analyzed coverage is loading';
  return <div className="locator-app"><header className="app-header"><a className="brand" href={window.location.pathname} aria-label="Sustainable Data Center Locator home"><span className="brand-mark"><Compass size={23} /></span><span><strong>Sustainable Data Center Locator</strong><small>Geographic decision support</small></span></a><div className="header-context">{viewSwitch}<label className="model-control">Model<select aria-label="Model" value={model} onChange={event => onModelChange(event.target.value as ModelId)}><option value="grid">Grid model</option><option value="county">County Monte Carlo</option></select></label>{demo && <strong className="demo-badge">DEMO DATA</strong>}</div></header>
    {demo && <div className="demo-banner">DEMO DATA · Explicit software fixtures. Values are not real geographic evidence. No automatic fallback to demo data.</div>}
    <main className={`workspace ${railOpen ? '' : 'rail-collapsed'} ${selected ? 'has-detail' : ''}`} style={{ '--mobile-map-bottom': `${sheetHeight}dvh` } as CSSProperties}>
      {!mobile && <aside className="desktop-rail" aria-label="Configuration and results">{panel}</aside>}
      <section className="map-workspace" aria-label="Geographic exploration"><CandidateMap regions={mapRegions} selectedId={selectedId} onSelect={select} layers={layers} layerSelections={layerSelections} onFeatureInfo={setFeature} camera={camera} onCameraChange={cameraChanged} projection={projection} basemap={basemap} viewRequest={viewRequest} className={stale ? 'stale-map' : ''} />
        <div className="map-toolbar"><button className="icon-button rail-toggle" aria-label={railOpen ? 'Collapse controls' : 'Expand controls'} onClick={() => setRailOpen(!railOpen)}>{railOpen ? <PanelLeftClose size={19} /> : <PanelLeftOpen size={19} />}</button>{result && <div className="scenario-control"><label htmlFor="scenario-select">Scenario</label><select id="scenario-select" value={scenarioId} disabled={state === 'LOADING'} onChange={event => changeScenario(event.target.value)}>{(result.scenarios ?? capabilities?.scenarios ?? [{ id: 'current', label: 'Current baseline', available: true, reason: null }]).map(scenario => <option key={scenario.id} value={scenario.id} disabled={!scenario.available}>{scenario.label}{!scenario.available ? ' — ' + (scenario.reason ?? 'Unavailable source context') : ''}</option>)}</select></div>}{mobile && selected && result && <button className="icon-button" aria-label="Decision brief" onClick={() => setBriefOpen(true)}><FileText size={18} /></button>}<button className="icon-button projection-toggle" aria-label={projection === 'mercator' ? 'Show globe view' : 'Show map view'} onClick={() => setProjection(projection === 'mercator' ? 'globe' : 'mercator')}>{projection === 'mercator' ? <Globe2 size={18} /> : <Map size={18} />}</button></div>
        <div className="map-notices"><div className={`map-status ${statusVisible ? '' : 'sr-only'}`} aria-label="Evaluation status" role={mobile ? undefined : state === 'ERROR' || capabilityError ? 'alert' : 'status'} aria-live={mobile ? 'off' : 'polite'}>{capabilityError ? <><AlertTriangle size={16} /><span>{capabilityError}</span>{!mobile && <button className="text-button" onClick={() => setCapabilityAttempt(value => value + 1)}>Reconnect</button>}</> : state === 'LOADING' ? <><span className="loading-spinner" /><span>{stage || 'Evaluating'}{result ? ' · previous results remain visible' : ''}</span></> : state === 'ERROR' ? <><AlertTriangle size={16} /><span>{error}{result ? ' Previous results are retained.' : ''}</span>{!mobile && <button className="text-button" onClick={retry}><RefreshCw size={13} />Retry</button>}</> : state === 'PARTIAL' ? <><AlertTriangle size={16} /><span>Results contain unresolved critical data.{changed ? ' Configuration edited; displayed results are from the last evaluated facility.' : ''}</span></> : changed ? <span>Configuration edited. Results reflect the last evaluated facility.</span> : state === 'EMPTY' ? <span>No regions satisfied the current hard constraints.</span> : state === 'SUCCESS' ? <span>Evaluation complete · inspect assumptions and evidence.</span> : <span>Ready · no regions evaluated yet.</span>}</div>
          {result && !county && <MapCoverage result={result} shownAreas={groups.length} totalAreas={allGroups.length} onLoadNationwide={loadNationwide} onLoadParent={loadParent} busy={state === 'LOADING'} />}
        </div>
        <div className="map-bottom-controls"><LayerControls capabilities={capabilities?.layers ?? []} selections={layerSelections} onChange={changeLayers} availableRun={!!result} regional={result?.analysis?.analysisLevel === 'regional'} activeWindow={!!selected} basemap={localBasemap ? basemap : undefined} onBasemapChange={setBasemap} /></div>
        {(layersLoading || layerErrors.length > 0) && <div className="layer-status" role="status">{layersLoading ? 'Loading selected indicator…' : layerErrors.join(' ')}</div>}
        <IndicatorEvidence key={`${result?.runId}-${result?.scenarioId}-${result?.analysis ? selectedId : ''}`} layers={layers.filter(layer => layerSelections.some(selection => selection.id === layer.id && selection.enabled))} onInspect={setFeature} />
        {feature && <FeatureInformation feature={feature} onClose={() => setFeature(null)} />}
      </section>
      {!mobile && details()}
      {mobile && <MobileSheet className={selected ? 'detail-active' : ''} onHeightChange={setSheetHeight} selectionKey={selectedId}>{details(<RequestNotice state={state} stage={stage} error={error} previous={true} onRetry={retry} />) ?? panel}</MobileSheet>}
      {comparisonOpen && compared.length > 0 && <><div className="modal-backdrop" onClick={() => setComparisonOpen(false)} /><Comparison regions={compared} coolingOptions={coolingOptions} onClose={() => setComparisonOpen(false)} onRemove={compare} /></>}
      {briefOpen && result && <><div className="brief-backdrop" onClick={() => setBriefOpen(false)} /><DecisionBrief result={result} selectedRegionId={selectedId} onClose={() => setBriefOpen(false)} /></>}
    </main><footer className="app-footer"><span>Search areas for further investigation, not approved sites. Unknown is never zero or pass.</span><span className="footer-coverage" title={footerCoverage}>{footerCoverage}</span></footer>
  </div>;
}
