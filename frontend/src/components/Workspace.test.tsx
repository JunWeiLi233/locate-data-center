import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import App from '../App';
import { parseCapabilities, parseLayer, parseRunResult } from '../api/regions';
import { demoCapabilities, demoLayer, demoRun, DEMO_CONFIG } from '../mocks/data';
import type { Job, RunResult } from '../types/domain';
import type { CandidateMapProps } from '../map/CandidateMap';

const api = vi.hoisted(() => ({ capabilities: vi.fn(), search: vi.fn(), run: vi.fn(), layer: vi.fn() }));
vi.mock('../api/client', () => ({ locatorApi: api, isDemoMode: false }));
vi.mock('../map/CandidateMap', () => ({ CandidateMap: (props: CandidateMapProps) => <div aria-label="Test geographic map" data-selected={props.selectedId ?? ''}>{props.regions.map(region => <button key={region.id} onClick={() => props.onSelect(region.id)}>Map select {region.id}</button>)}</div> }));

const configuration = { ...DEMO_CONFIG, screeningMode: 'STRICT' as const };
function result(): RunResult { return parseRunResult(demoRun({ ...DEMO_CONFIG, screeningMode: 'EXPLORATORY' })); }
function deferred<T>() { let resolve!: (value: T) => void; let reject!: (value: unknown) => void; const promise = new Promise<T>((yes, no) => { resolve = yes; reject = no; }); return { promise, resolve, reject }; }
async function ready() { render(<App />); await waitFor(() => expect(screen.getByRole('button', { name: 'Find locations' })).toBeEnabled()); }
async function evaluate() { await ready(); await userEvent.click(screen.getByRole('button', { name: 'Find locations' })); await screen.findByRole('button', { name: 'Select Candidate Alpha, air_dry_assumed' }); }

beforeEach(() => {
  window.history.replaceState({}, '', '/');
  vi.clearAllMocks();
  const capabilities = parseCapabilities(demoCapabilities); capabilities.demo = false; capabilities.defaultConfiguration = configuration; capabilities.scope = '42 real development cells'; capabilities.latestRunId = 'REAL_SAVED';
  api.capabilities.mockResolvedValue(capabilities); api.search.mockResolvedValue(result()); api.run.mockResolvedValue(result()); api.layer.mockImplementation((id: string, _run: string, _scenario: string, sublayer: string) => Promise.resolve(parseLayer(demoLayer(id, sublayer))));
  window.matchMedia = vi.fn().mockImplementation(query => ({ matches: false, media: query, addEventListener: vi.fn(), removeEventListener: vi.fn() }));
});

describe('locator workspace', () => {
  it('starts idle with the declared facility and no automatic results or saved-run load', async () => {
    await ready(); expect(api.search).not.toHaveBeenCalled(); expect(api.run).not.toHaveBeenCalled();
    expect(screen.getByRole('spinbutton', { name: 'Peak IT power MW' })).toHaveValue(100);
    expect(screen.getByRole('spinbutton', { name: 'Average load percent' })).toHaveValue(80);
    expect(screen.getByRole('spinbutton', { name: 'Target opening year' })).toHaveValue(2030);
    expect(screen.getByRole('spinbutton', { name: 'Operating lifetime years' })).toHaveValue(25);
    expect(screen.queryByRole('button', { name: /Select Candidate Alpha/ })).not.toBeInTheDocument();
  });
  it('sends changed physical inputs to the API and displays only actual stages while loading', async () => {
    const pending = deferred<RunResult>(); api.search.mockImplementation((_config, progress: (job: Job) => void) => { progress({ id: 'JOB', state: 'RUNNING', stage: 'Simulating facility', runId: null, error: null }); return pending.promise; });
    await ready(); fireEvent.change(screen.getByRole('spinbutton', { name: 'Peak IT power MW' }), { target: { value: '120' } });
    await userEvent.click(screen.getByRole('button', { name: 'Find locations' }));
    expect(api.search.mock.calls[0][0].peakItPowerMw).toBe(120);
    expect(screen.getByRole('status', { name: 'Evaluation status' })).toHaveTextContent('Simulating facility'); expect(screen.queryByRole('progressbar')).not.toBeInTheDocument();
    await act(async () => { pending.resolve(result()); }); expect(screen.getByRole('status', { name: 'Evaluation status' })).toHaveTextContent('Results contain unresolved critical data.');
  });
  it('restores URL run and selected region after the async load', async () => {
    window.history.replaceState({}, '', '/?run=REAL_SAVED&region=DEMO_ALPHA&scenario=current');
    render(<App />); await screen.findByRole('complementary', { name: 'Details for Candidate Alpha' });
    expect(api.run).toHaveBeenCalledWith('REAL_SAVED', 'current', expect.any(AbortSignal));
    expect(screen.getByLabelText('Test geographic map')).toHaveAttribute('data-selected', 'DEMO_ALPHA');
  });
  it('keeps a selected region when display filters hide it and records selection in the URL', async () => {
    await evaluate(); await userEvent.click(screen.getByRole('button', { name: 'Map select DEMO_GAMMA' }));
    await userEvent.click(screen.getByRole('checkbox', { name: 'Pareto frontier only' }));
    expect(screen.getByRole('complementary', { name: 'Details for Candidate Gamma' })).toBeInTheDocument();
    expect(screen.getByText(/Selected region is outside the display filters/)).toBeInTheDocument();
    expect(new URLSearchParams(window.location.search).get('region')).toBe('DEMO_GAMMA');
    await userEvent.click(screen.getByRole('button', { name: 'Close region details' })); expect(new URLSearchParams(window.location.search).has('region')).toBe(false);
  });
  it('syncs list selection, raw Unknowns, representative rank, and safe backend exports', async () => {
    const value = result(); value.exports = [{ label: 'Ranking CSV', url: '/api/exports/REAL/ranking.csv' }, { label: 'Unsafe export', url: 'javascript:alert(1)' }]; api.search.mockResolvedValue(value);
    await evaluate(); await userEvent.click(screen.getByRole('button', { name: 'Select Candidate Alpha, air_dry_assumed' }));
    const drawer = screen.getByRole('complementary', { name: 'Details for Candidate Alpha' });
    expect(within(drawer).getByText(/Region mean score:/)).toHaveTextContent('86.2');
    expect(within(drawer).getByText(/Representative alternative #1/)).toBeInTheDocument();
    expect(within(drawer).getByText('Synthetic fixture demonstrates missing water measurement.')).toBeInTheDocument();
    expect(within(drawer).getByRole('link', { name: 'Ranking CSV' })).toHaveAttribute('href', '/api/exports/REAL/ranking.csv');
    expect(within(drawer).queryByRole('link', { name: 'Unsafe export' })).not.toBeInTheDocument();
    expect(within(drawer).getByText(/does not establish an objectively best location/)).toBeInTheDocument();
  });
  it('caps comparison at three and shows backend raw metrics without an invented winner', async () => {
    const value = result(); value.regions.push({ ...value.regions[0], id: 'FOUR', label: 'Candidate Delta' }); api.search.mockResolvedValue(value);
    await evaluate(); for (const name of ['Candidate Alpha, air_dry_assumed', 'Candidate Beta, cold_plate_tower_assumed', 'Candidate Gamma, air_dry_assumed']) await userEvent.click(screen.getByRole('button', { name: `Add ${name} to comparison` }));
    expect(screen.getByRole('button', { name: 'Add Candidate Delta, air_dry_assumed to comparison' })).toBeDisabled();
    await userEvent.click(screen.getByRole('button', { name: 'Select Candidate Delta, air_dry_assumed' })); expect(screen.getByRole('button', { name: 'Compare this region' })).toBeDisabled();
    await userEvent.click(screen.getByRole('button', { name: 'Compare (3)' }));
    const dialog = screen.getByRole('dialog', { name: 'Region comparison' });
    expect(within(dialog).getByText(/no combined winner is invented/)).toBeInTheDocument(); expect(within(dialog).getAllByText('Unknown').length).toBeGreaterThan(0);
    expect(within(dialog).getByRole('button', { name: 'Close comparison' })).toHaveFocus(); await userEvent.keyboard('{Escape}'); expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });
  it('retains previous evaluated results and edited inputs after error; retry preserves the failed request', async () => {
    await evaluate(); await userEvent.click(screen.getByRole('button', { name: 'Configure' }));
    fireEvent.change(screen.getByRole('spinbutton', { name: 'Peak IT power MW' }), { target: { value: '125' } }); api.search.mockRejectedValueOnce(new Error('Native source unavailable'));
    await userEvent.click(screen.getByRole('button', { name: 'Find locations' })); await screen.findByRole('alert');
    expect(screen.getByRole('alert')).toHaveTextContent('Previous results are retained.'); expect(screen.getByRole('button', { name: 'Select Candidate Alpha, air_dry_assumed' })).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Retry' })); await waitFor(() => expect(api.search).toHaveBeenCalledTimes(3));
    expect(api.search.mock.calls[2][0].peakItPowerMw).toBe(125);
  });
  it('shows a valid empty strict result and never creates a candidate', async () => {
    api.search.mockResolvedValue(parseRunResult(demoRun(configuration))); await ready(); await userEvent.click(screen.getByRole('button', { name: 'Find locations' }));
    await screen.findByRole('heading', { name: 'No regions satisfied the current hard constraints.' }); expect(screen.queryByRole('button', { name: /Select Candidate Alpha/ })).not.toBeInTheDocument();
  });
  it('loads optional layers only on request and keeps unavailable sources disabled', async () => {
    await evaluate(); expect(api.layer).not.toHaveBeenCalled(); await userEvent.click(screen.getByText('Map layers'));
    expect(screen.getByRole('checkbox', { name: 'Heat Reuse' })).toBeDisabled(); expect(screen.getAllByText('No opportunity geometry supplied in this fixture.')).toHaveLength(2);
    await userEvent.click(screen.getByRole('checkbox', { name: 'Suitability Grid' })); await screen.findByRole('combobox', { name: 'Inspect evaluated grid cell' });
    expect(api.layer).toHaveBeenCalledWith('grid', 'DEMO_RUN', 'current', undefined, expect.any(AbortSignal));
    fireEvent.change(screen.getByRole('combobox', { name: 'Inspect evaluated grid cell' }), { target: { value: '3' } });
    const info = screen.getByRole('region', { name: 'Map feature information' }); expect(within(info).getAllByText('UNKNOWN')).toHaveLength(2); expect(within(info).getByText('Synthetic utility capacity unknown')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('checkbox', { name: 'Suitability Grid' })); await userEvent.click(screen.getByRole('checkbox', { name: 'Suitability Grid' })); await waitFor(() => expect(api.layer).toHaveBeenCalledTimes(1));
  });
  it('disables 2040 and loads supported contexts independently', async () => {
    await evaluate(); const context = screen.getByRole('combobox', { name: 'External context' });
    expect(within(context).getByRole('option', { name: /2040/ })).toBeDisabled();
    const value = result(); value.scenarioId = 'bau_2050'; api.run.mockResolvedValue(value); await userEvent.selectOptions(context, 'bau_2050');
    await waitFor(() => expect(api.run).toHaveBeenCalledWith('DEMO_RUN', 'bau_2050', expect.any(AbortSignal)));
  });
  it('keeps an explicit persistent demo disclosure after evaluation', async () => {
    const capabilities = parseCapabilities(demoCapabilities); api.capabilities.mockResolvedValue(capabilities); await evaluate();
    expect(screen.getByText(/Explicit software fixtures/)).toBeInTheDocument(); expect(screen.getAllByText('DEMO DATA').length).toBeGreaterThan(0);
  });
  it('renders one mobile form with keyboard adjustable sheet positions', async () => {
    window.matchMedia = vi.fn().mockImplementation(query => ({ matches: query === '(max-width: 1190px)', media: query, addEventListener: vi.fn(), removeEventListener: vi.fn() }));
    await ready(); expect(screen.getAllByRole('spinbutton', { name: 'Peak IT power MW' })).toHaveLength(1);
    const sheet = screen.getByRole('button', { name: 'Expand bottom sheet' }).closest('.mobile-sheet')!;
    await userEvent.click(screen.getByRole('button', { name: 'Expand bottom sheet' })); expect(sheet).toHaveStyle('--sheet-height: 88dvh');
    await userEvent.click(screen.getByRole('button', { name: 'Minimize bottom sheet' })); expect(sheet).toHaveStyle('--sheet-height: 18dvh');
    await userEvent.click(screen.getByRole('button', { name: 'Half-height bottom sheet' })); expect(sheet).toHaveStyle('--sheet-height: 48dvh');
  });
  it('keeps progress and error retry reachable inside an expanded mobile sheet', async () => {
    window.matchMedia = vi.fn().mockImplementation(query => ({ matches: query === '(max-width: 1190px)', media: query, addEventListener: vi.fn(), removeEventListener: vi.fn() }));
    const request = deferred<RunResult>(); api.search.mockReturnValueOnce(request.promise);
    await ready(); await userEvent.click(screen.getByRole('button', { name: 'Expand bottom sheet' })); await userEvent.click(screen.getByRole('button', { name: 'Find locations' }));
    expect(screen.getByRole('status', { name: 'Evaluation request' }).closest('.mobile-sheet')).not.toBeNull();
    await act(async () => { request.reject(new Error('Official source access failed')); });
    const notice = screen.getByRole('alert', { name: 'Evaluation request' }); expect(notice.closest('.mobile-sheet')).not.toBeNull();
    expect(screen.getAllByRole('button', { name: 'Retry' })).toHaveLength(1); await userEvent.click(within(notice).getByRole('button', { name: 'Retry' }));
    await waitFor(() => expect(api.search).toHaveBeenCalledTimes(2)); expect(screen.queryByRole('status', { name: 'Evaluation status' })).not.toBeInTheDocument();
  });
  it('retains edited configuration when capabilities are reconnected', async () => {
    api.capabilities.mockRejectedValueOnce(new Error('Service disconnected')); render(<App />); await screen.findByRole('alert');
    fireEvent.change(screen.getByRole('spinbutton', { name: 'Peak IT power MW' }), { target: { value: '140' } });
    await userEvent.click(screen.getByRole('button', { name: 'Reconnect' })); await waitFor(() => expect(screen.getByRole('button', { name: 'Find locations' })).toBeEnabled());
    expect(screen.getByRole('spinbutton', { name: 'Peak IT power MW' })).toHaveValue(140);
  });
  it('keeps mobile retry accessible in selected previous details after a context fails', async () => {
    window.matchMedia = vi.fn().mockImplementation(query => ({ matches: query === '(max-width: 1190px)', media: query, addEventListener: vi.fn(), removeEventListener: vi.fn() }));
    await evaluate(); await userEvent.click(screen.getByRole('button', { name: 'Select Candidate Alpha, air_dry_assumed' }));
    api.run.mockRejectedValueOnce(new Error('Future source unavailable'));
    await userEvent.selectOptions(screen.getByRole('combobox', { name: 'External context' }), 'bau_2050');
    const drawer = screen.getByRole('complementary', { name: 'Details for Candidate Alpha' });
    await within(drawer).findByRole('alert', { name: 'Evaluation request' }); expect(within(drawer).getByText(/Previous evaluated region/)).toBeInTheDocument();
    const value = result(); value.scenarioId = 'bau_2050'; api.run.mockResolvedValue(value);
    await userEvent.click(within(drawer).getByRole('button', { name: 'Retry' })); await waitFor(() => expect(api.run).toHaveBeenCalledTimes(2));
    expect(api.run.mock.calls[1][1]).toBe('bau_2050');
  });
  it.each(['equal', 'user'])('clears supplied AHP judgments before submitting %s preferences', async weighting => {
    await ready(); await userEvent.selectOptions(screen.getByRole('combobox', { name: 'Decision preferences' }), 'ahp');
    const judgments = screen.getAllByPlaceholderText('Judgment'); expect(judgments).toHaveLength(6);
    for (const input of judgments) fireEvent.change(input, { target: { value: '1' } });
    await userEvent.selectOptions(screen.getByRole('combobox', { name: 'Decision preferences' }), weighting);
    await userEvent.click(screen.getByRole('button', { name: 'Find locations' }));
    expect(api.search.mock.calls[0][0].weighting).toBe(weighting); expect(api.search.mock.calls[0][0].ahpMatrix).toBeNull();
  });
  it('restores the actual saved facility configuration without a false edited warning', async () => {
    window.history.replaceState({}, '', '/?run=SAVED120'); const value = result(); value.configuration = { ...value.configuration, peakItPowerMw: 120, averageLoadPercent: 75 }; api.run.mockResolvedValue(value);
    render(<App />); await screen.findByRole('button', { name: 'Select Candidate Alpha, air_dry_assumed' });
    await waitFor(() => expect(screen.getByRole('status', { name: 'Evaluation status' })).not.toHaveTextContent('Configuration edited'));
    await userEvent.click(screen.getByRole('button', { name: 'Configure' }));
    expect(screen.getByRole('spinbutton', { name: 'Peak IT power MW' })).toHaveValue(120); expect(screen.getByRole('spinbutton', { name: 'Average load percent' })).toHaveValue(75);
  });
  it('applies explicit URL fields over saved settings while retaining the other actual facility values', async () => {
    window.history.replaceState({}, '', '/?run=SAVED120&mw=140&opening=2050'); const value = result(); value.configuration = { ...value.configuration, peakItPowerMw: 120, averageLoadPercent: 75, cooling: 'cold_plate_tower_assumed' }; api.run.mockResolvedValue(value);
    render(<App />); await screen.findByRole('button', { name: 'Select Candidate Alpha, air_dry_assumed' }); await userEvent.click(screen.getByRole('button', { name: 'Configure' }));
    expect(screen.getByRole('spinbutton', { name: 'Peak IT power MW' })).toHaveValue(140); expect(screen.getByRole('spinbutton', { name: 'Average load percent' })).toHaveValue(75); expect(screen.getByRole('spinbutton', { name: 'Target opening year' })).toHaveValue(2050);
    expect(screen.getByRole('combobox', { name: 'Cooling design' })).toHaveValue('cold_plate_tower_assumed');
  });
  it('returns an expanded result sheet to half height for a new selection and preserves later resizing for the same region', async () => {
    window.matchMedia = vi.fn().mockImplementation(query => ({ matches: query === '(max-width: 1190px)', media: query, addEventListener: vi.fn(), removeEventListener: vi.fn() }));
    await ready(); await userEvent.click(screen.getByRole('button', { name: 'Expand bottom sheet' })); await userEvent.click(screen.getByRole('button', { name: 'Find locations' }));
    await screen.findByRole('button', { name: 'Select Candidate Alpha, air_dry_assumed' });
    const sheet = screen.getByRole('button', { name: 'Expand bottom sheet' }).closest('.mobile-sheet')!;
    expect(sheet).toHaveStyle('--sheet-height: 88dvh');
    await userEvent.click(screen.getByRole('button', { name: 'Select Candidate Alpha, air_dry_assumed' }));
    await waitFor(() => expect(sheet).toHaveStyle('--sheet-height: 48dvh')); expect(document.querySelector('.workspace')).toHaveStyle('--mobile-map-bottom: 48dvh');
    await userEvent.click(screen.getByRole('button', { name: 'Expand bottom sheet' })); await userEvent.click(screen.getByRole('button', { name: 'Map select DEMO_ALPHA' }));
    expect(sheet).toHaveStyle('--sheet-height: 88dvh');
    await userEvent.click(screen.getByRole('button', { name: 'Close region details' }));
    await userEvent.click(screen.getByRole('button', { name: 'Select Candidate Alpha, air_dry_assumed' }));
    await waitFor(() => expect(sheet).toHaveStyle('--sheet-height: 48dvh'));
    await userEvent.click(screen.getByRole('button', { name: 'Expand bottom sheet' }));
    await userEvent.click(screen.getByRole('button', { name: 'Close region details' })); await userEvent.click(screen.getByRole('button', { name: 'Select Candidate Beta, cold_plate_tower_assumed' }));
    await waitFor(() => expect(sheet).toHaveStyle('--sheet-height: 48dvh'));
  });
});
