import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import App from '../App';
import { parseCapabilities, parseRunResult } from '../api/regions';
import { DEMO_CONFIG, demoCapabilities, demoRun } from '../mocks/data';
import type { CandidateMapProps } from '../map/CandidateMap';

const api = vi.hoisted(() => ({ capabilities: vi.fn(), run: vi.fn(), search: vi.fn(), layer: vi.fn(), socioeconomic: vi.fn() }));
vi.mock('../api/client', () => ({ locatorApi: api, isDemoMode: false }));
vi.mock('../api/monteCarlo', () => ({ createMonteCarloApi: () => api }));
vi.mock('../map/CandidateMap', () => ({ CandidateMap: (props: CandidateMapProps) => <div aria-label="Test geographic map">{props.regions.length} alternatives</div> }));

// No advertised completed run: these tests start on the form and exercise searches.
const wire = { ...demoCapabilities, latest_run_id: null, schema_version: '1.8.0', default_analysis_mode: 'cached_regional', analysis_modes: [
  { id: 'cached_regional', label: 'Cached nationwide regional evaluation', available: true, reason: null },
  { id: 'full_rediscovery', label: 'Full nationwide rediscovery', available: true, reason: null },
] };
beforeEach(() => {
  vi.clearAllMocks(); window.history.replaceState({}, '', '/');
  api.capabilities.mockResolvedValue(parseCapabilities(wire));
  api.search.mockImplementation(configuration => Promise.resolve(parseRunResult(demoRun(configuration))));
});
describe('Grid cached cohort evaluation controls', () => {
  it('defaults to advertised fast mode and recomputes the edited facility and weights rather than loading a saved run', async () => {
    render(<App />); const mode = await screen.findByRole('combobox', { name: 'Search depth' });
    expect(mode).toHaveValue('cached_regional'); expect(screen.getByText(/Re-scores the regions already analyzed at 1 km/)).toBeInTheDocument();
    expect(screen.getByText(/no new regions are searched/i)).toBeInTheDocument();
    fireEvent.change(screen.getByRole('spinbutton', { name: 'Peak IT power MW' }), { target: { value: '140' } });
    await userEvent.click(screen.getByText('More options'));
    await userEvent.selectOptions(screen.getByRole('combobox', { name: 'Decision preferences' }), 'user');
    fireEvent.change(screen.getByRole('spinbutton', { name: 'Power & Carbon weight' }), { target: { value: '3' } });
    fireEvent.change(screen.getByRole('spinbutton', { name: 'Water Stewardship weight' }), { target: { value: '1' } });
    await userEvent.click(screen.getByRole('button', { name: 'Find locations' }));
    await waitFor(() => expect(api.search).toHaveBeenCalledWith(expect.objectContaining({ peakItPowerMw: 140, weighting: 'user', groupWeights: expect.objectContaining({ energy_carbon: 3, water_stewardship: 1 }) }), expect.any(Function), expect.any(AbortSignal), 'cached_regional'));
    expect(api.run).not.toHaveBeenCalled();
  });
  it('lets Grid users explicitly select full nationwide rediscovery', async () => {
    render(<App />); const mode = await screen.findByRole('combobox', { name: 'Search depth' });
    await userEvent.selectOptions(mode, 'full_rediscovery');
    expect(screen.getByText(/Repeats the national search.*much longer/i)).toBeInTheDocument();
    expect(screen.queryByText(/Re-scores the regions already analyzed at 1 km/)).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Find locations' }));
    await waitFor(() => expect(api.search).toHaveBeenCalledWith(expect.any(Object), expect.any(Function), expect.any(AbortSignal), 'full_rediscovery'));
    expect(api.run).not.toHaveBeenCalled();
  });
  it('falls back to full mode when the cached cohort is unavailable', async () => {
    api.capabilities.mockResolvedValue(parseCapabilities({ ...wire, default_analysis_mode: 'full_rediscovery', analysis_modes: [
      { ...wire.analysis_modes[0], available: false, reason: 'Verified cached cohort unavailable' }, wire.analysis_modes[1],
    ] }));
    render(<App />); const mode = await screen.findByRole('combobox', { name: 'Search depth' });
    expect(mode).toHaveValue('full_rediscovery');
    expect(within(mode).getByRole('option', { name: /Fast.*cached/ })).toBeDisabled();
  });
  it('keeps legacy Grid evaluation requests unchanged when modes are not advertised', async () => {
    api.capabilities.mockResolvedValue(parseCapabilities(demoCapabilities));
    render(<App />); await waitFor(() => expect(screen.getByRole('button', { name: 'Find locations' })).toBeEnabled());
    expect(screen.queryByRole('combobox', { name: 'Search depth' })).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Find locations' }));
    await waitFor(() => expect(api.search).toHaveBeenCalledWith(expect.any(Object), expect.any(Function), expect.any(AbortSignal)));
    expect(api.search.mock.calls[0]).toHaveLength(3);
  });
  it('does not send Grid mode metadata through the independent County model', async () => {
    window.history.replaceState({}, '', '/?model=county');
    api.capabilities.mockResolvedValue({ ...parseCapabilities(wire), modelKind: 'monte-carlo', defaultConfiguration: { ...DEMO_CONFIG, monteCarlo: { settingsJson: '{}', sensitivity: true, convergence: true } } });
    render(<App />); await waitFor(() => expect(screen.getByRole('button', { name: 'Find locations' })).toBeEnabled());
    expect(screen.queryByRole('combobox', { name: 'Search depth' })).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Find locations' }));
    await waitFor(() => expect(api.search).toHaveBeenCalledWith(expect.any(Object), expect.any(Function), expect.any(AbortSignal)));
    expect(api.search.mock.calls[0]).toHaveLength(3);
  });
  it('omits Grid mode after switching an initialized fast Grid workspace to County', async () => {
    render(<App />);
    expect(await screen.findByRole('combobox', { name: 'Search depth' })).toHaveValue('cached_regional');
    api.capabilities.mockResolvedValue({ ...parseCapabilities(wire), modelKind: 'monte-carlo', defaultConfiguration: { ...DEMO_CONFIG, monteCarlo: { settingsJson: '{}', sensitivity: true, convergence: true } } });
    await userEvent.selectOptions(screen.getByRole('combobox', { name: 'Model' }), 'county');
    await waitFor(() => expect(screen.getByRole('button', { name: 'Find locations' })).toBeEnabled());
    expect(screen.queryByRole('combobox', { name: 'Search depth' })).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Find locations' }));
    await waitFor(() => expect(api.search).toHaveBeenCalledOnce());
    expect(api.search.mock.calls[0]).toHaveLength(3);
    expect(api.search.mock.calls[0][0].monteCarlo.settingsJson).toBe('{}');
  });
  it('retries the submitted facility and mode even after controls are edited', async () => {
    api.search.mockRejectedValueOnce(new Error('Temporary request failure'));
    render(<App />);
    await userEvent.selectOptions(await screen.findByRole('combobox', { name: 'Search depth' }), 'full_rediscovery');
    fireEvent.change(screen.getByRole('spinbutton', { name: 'Peak IT power MW' }), { target: { value: '147' } });
    await userEvent.click(screen.getByRole('button', { name: 'Find locations' }));
    await screen.findByText('Temporary request failure');
    await userEvent.selectOptions(screen.getByRole('combobox', { name: 'Search depth' }), 'cached_regional');
    fireEvent.change(screen.getByRole('spinbutton', { name: 'Peak IT power MW' }), { target: { value: '190' } });
    await userEvent.click(screen.getByRole('button', { name: 'Retry' }));
    await waitFor(() => expect(api.search).toHaveBeenCalledTimes(2));
    expect(api.search.mock.calls[1]).toEqual([expect.objectContaining({ peakItPowerMw: 147 }), expect.any(Function), expect.any(AbortSignal), 'full_rediscovery']);
  });
});
