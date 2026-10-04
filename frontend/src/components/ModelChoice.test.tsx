/** Synthetic view fixtures verify model isolation, never geographic suitability. */
import { act, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import App from '../App';
import { parseCapabilities, parseRunResult } from '../api/regions';
import { demoCapabilities, demoRun, DEMO_CONFIG } from '../mocks/data';
import type { Capabilities, RunResult } from '../types/domain';
import type { CandidateMapProps } from '../map/CandidateMap';

const adapters = vi.hoisted(() => ({
  grid: { capabilities: vi.fn(), search: vi.fn(), run: vi.fn(), layer: vi.fn(), socioeconomic: vi.fn() },
  county: { capabilities: vi.fn(), search: vi.fn(), run: vi.fn(), layer: vi.fn(), socioeconomic: vi.fn() },
}));
vi.mock('../api/client', () => ({ locatorApi: adapters.grid, isDemoMode: false }));
vi.mock('../api/monteCarlo', () => ({ createMonteCarloApi: () => adapters.county }));
vi.mock('../map/CandidateMap', () => ({ CandidateMap: (props: CandidateMapProps) => <div aria-label="Model switch test map">{props.regions.map(region => <button key={region.id} onClick={() => props.onSelect(region.id)}>Point {region.id}</button>)}</div> }));

/** Preserve missing rank/score while identifying a clearly synthetic county view. */
function countyResult(): RunResult {
  const value = parseRunResult(demoRun());
  return { ...value, modelKind: 'monte-carlo', coverageUnit: 'counties', runId: 'run_0123456789abcdef',
    scenarioId: 'county_context', configuration: { ...DEMO_CONFIG, cooling: 'shared_priors', monteCarlo: { settingsJson: '{}', sensitivity: false, convergence: false } },
    scenarios: [{ id: 'county_context', label: 'County fixture context', year: null, pathway: null, available: true, reason: null }],
    regions: [{ ...value.regions[0], modelKind: 'monte-carlo', id: '01089', label: 'Synthetic county fixture', placeLabel: null,
      rank: null, score: null, regionMeanScore: null, geometry: null, screeningStatus: 'CONDITIONAL',
      rankBasis: 'Unweighted physical tradeoff; no scalar rank or score.', scenarioId: 'county_context' }],
    modelEvidence: { fixture_only: true }, decisionBrief: null };
}

beforeEach(() => {
  window.history.replaceState({}, '', '/');
  vi.clearAllMocks();
  const grid = parseCapabilities(demoCapabilities);
  grid.latestRunId = null; grid.demo = false;
  adapters.grid.capabilities.mockResolvedValue(grid);
  adapters.grid.search.mockResolvedValue(parseRunResult(demoRun()));
  adapters.grid.run.mockResolvedValue(parseRunResult(demoRun()));
  const county: Capabilities = { ...grid, modelKind: 'monte-carlo', coverageUnit: 'counties',
    scope: 'Synthetic county fixture only', defaultConfiguration: countyResult().configuration,
    coolingOptions: [{ id: 'shared_priors', label: 'Shared PUE/WUE priors' }], weightingGroups: [],
    layers: grid.layers.map(layer => ({ ...layer, available: layer.id === 'candidates', reason: layer.id === 'candidates' ? null : 'Not provided by this model' })),
    scenarios: countyResult().scenarios! };
  adapters.county.capabilities.mockResolvedValue(county);
  adapters.county.search.mockResolvedValue(countyResult());
  adapters.county.run.mockResolvedValue(countyResult());
  window.matchMedia = vi.fn().mockImplementation(query => ({ matches: false, media: query, addEventListener: vi.fn(), removeEventListener: vi.fn() }));
});

describe('runtime model choice', () => {
  it('keeps grid default and clears results, selection, scenario and URL run when switching either way', async () => {
    render(<App />);
    await waitFor(() => expect(screen.getByRole('button', { name: 'Find locations' })).toBeEnabled());
    expect(screen.getByRole('combobox', { name: 'Model' })).toHaveValue('grid');
    expect(adapters.county.capabilities).not.toHaveBeenCalled();
    await userEvent.click(screen.getByRole('button', { name: 'Find locations' }));
    await screen.findByRole('button', { name: 'Point DEMO_ALPHA' });
    await userEvent.click(screen.getByRole('button', { name: 'Point DEMO_ALPHA' }));
    expect(screen.getByRole('complementary', { name: /Details for Candidate Alpha/ })).toBeInTheDocument();
    await userEvent.selectOptions(screen.getByRole('combobox', { name: 'Model' }), 'county');
    await waitFor(() => expect(screen.getByRole('button', { name: 'Find locations' })).toBeEnabled());
    expect(screen.queryByRole('button', { name: 'Point DEMO_ALPHA' })).not.toBeInTheDocument();
    expect(screen.queryByRole('combobox', { name: 'Scenario' })).not.toBeInTheDocument();
    expect(screen.queryByRole('complementary', { name: /Details for/ })).not.toBeInTheDocument();
    const url = new URLSearchParams(window.location.search);
    expect(url.get('model')).toBe('county'); expect(url.has('run')).toBe(false); expect(url.has('region')).toBe(false); expect(url.has('scenario')).toBe(false);
    expect(adapters.county.run).not.toHaveBeenCalled();
    await userEvent.click(screen.getByRole('button', { name: 'Find locations' }));
    await screen.findByRole('button', { name: 'Point 01089' });
    expect(screen.getByRole('combobox', { name: 'Scenario' })).toHaveValue('county_context');
    expect(screen.getByRole('contentinfo')).toHaveTextContent('synthetic fixture counties');
    await userEvent.click(screen.getByRole('button', { name: 'Point 01089' }));
    const details = screen.getByRole('complementary', { name: 'Details for Synthetic county fixture' });
    expect(within(details).getByText(/^No scalar rank or score/)).toBeInTheDocument();
    expect(within(details).queryByText('Score breakdown')).not.toBeInTheDocument();
    expect(within(details).getByText(/Unavailable from the county Monte Carlo API/)).toBeInTheDocument();
    expect(adapters.county.socioeconomic).not.toHaveBeenCalled();
    await userEvent.selectOptions(screen.getByRole('combobox', { name: 'Model' }), 'grid');
    await waitFor(() => expect(screen.getByRole('button', { name: 'Find locations' })).toBeEnabled());
    expect(screen.queryByRole('button', { name: 'Point 01089' })).not.toBeInTheDocument();
    expect(new URLSearchParams(window.location.search).has('run')).toBe(false);
    expect(adapters.grid.run).not.toHaveBeenCalled();
  });

  it('returns to the previous model and its results with the browser Back button', async () => {
    render(<App />);
    await waitFor(() => expect(screen.getByRole('button', { name: 'Find locations' })).toBeEnabled());
    await userEvent.click(screen.getByRole('button', { name: 'Find locations' }));
    await screen.findByRole('button', { name: 'Point DEMO_ALPHA' });
    await userEvent.selectOptions(screen.getByRole('combobox', { name: 'Model' }), 'county');
    await waitFor(() => expect(screen.getByRole('button', { name: 'Find locations' })).toBeEnabled());
    act(() => window.history.back());
    await waitFor(() => expect(screen.getByRole('combobox', { name: 'Model' })).toHaveValue('grid'));
    await screen.findByRole('button', { name: 'Point DEMO_ALPHA' });
    expect(adapters.grid.run).toHaveBeenCalledWith('DEMO_RUN', 'current', expect.any(AbortSignal));
    expect(new URLSearchParams(window.location.search).has('model')).toBe(false);
    expect(adapters.grid.search).toHaveBeenCalledTimes(1); expect(adapters.county.search).not.toHaveBeenCalled();
  });

  it('aborts the old model request and ignores its late completion', async () => {
    let complete!: (value: RunResult) => void;
    let requestSignal!: AbortSignal;
    adapters.grid.search.mockImplementation((_configuration, _progress, signal) => {
      requestSignal = signal;
      return new Promise<RunResult>(resolve => { complete = resolve; });
    });
    render(<App />);
    await waitFor(() => expect(screen.getByRole('button', { name: 'Find locations' })).toBeEnabled());
    await userEvent.click(screen.getByRole('button', { name: 'Find locations' }));
    await userEvent.selectOptions(screen.getByRole('combobox', { name: 'Model' }), 'county');
    expect(requestSignal.aborted).toBe(true);
    await act(async () => { complete(parseRunResult(demoRun())); });
    expect(screen.queryByRole('button', { name: 'Point DEMO_ALPHA' })).not.toBeInTheDocument();
    expect(new URLSearchParams(window.location.search).has('run')).toBe(false);
  });

  it('restores a county URL only through the county adapter', async () => {
    window.history.replaceState({}, '', '/?model=county&run=run_0123456789abcdef&scenario=county_context&region=01089');
    render(<App />);
    await screen.findByRole('button', { name: 'Point 01089' });
    expect(adapters.county.run).toHaveBeenCalledWith('run_0123456789abcdef', 'county_context', expect.any(AbortSignal));
    expect(adapters.grid.capabilities).not.toHaveBeenCalled();
    expect(adapters.grid.run).not.toHaveBeenCalled();
    expect(screen.getByRole('combobox', { name: 'Model' })).toHaveValue('county');
  });

  it('reports county readiness failure without showing grid results or submitting a run', async () => {
    adapters.county.capabilities.mockRejectedValue(new Error('Frozen county datasets are unavailable.'));
    window.history.replaceState({}, '', '/?model=county');
    render(<App />);
    await screen.findByText('Frozen county datasets are unavailable.');
    expect(screen.getByRole('button', { name: 'Find locations' })).toBeDisabled();
    expect(adapters.grid.capabilities).not.toHaveBeenCalled();
    expect(adapters.county.search).not.toHaveBeenCalled();
  });
});
