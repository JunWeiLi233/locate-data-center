import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import App from '../App';
import { parseCapabilities, parseRunResult } from '../api/regions';
import { DEMO_CONFIG, demoCapabilities, demoRun } from '../mocks/data';
import type { CandidateMapProps } from '../map/CandidateMap';

const api = vi.hoisted(() => ({ capabilities: vi.fn(), run: vi.fn(), search: vi.fn(), layer: vi.fn(), socioeconomic: vi.fn() }));
vi.mock('../api/client', () => ({ locatorApi: api, isDemoMode: false }));
vi.mock('../api/monteCarlo', () => ({ createMonteCarloApi: () => api }));
vi.mock('../map/CandidateMap', () => ({ CandidateMap: (props: CandidateMapProps) => <div aria-label="Test geographic map" data-selected={props.selectedId ?? ''}>{props.regions.map(region => <span key={region.id}>{region.id}</span>)}</div> }));

const nationwideId = 'SAVED_NATIONWIDE';
beforeEach(() => {
  vi.clearAllMocks(); window.history.replaceState({}, '', '/');
  api.capabilities.mockResolvedValue({ ...parseCapabilities(demoCapabilities), latestRunId: 'CONCENTRATED', nationwideRegionalRunId: nationwideId });
  api.run.mockImplementation(id => Promise.resolve({ ...parseRunResult(demoRun({ ...DEMO_CONFIG, peakItPowerMw: id === nationwideId ? 175 : 100 })), runId: id }));
});
describe('completed nationwide saved-run navigation', () => {
  it('opens a fresh page on the facility form and loads the nationwide saved run, not the latest run, only on request', async () => {
    render(<App />);
    const start = await screen.findByRole('button', { name: 'open saved results' });
    expect(api.run).not.toHaveBeenCalled(); expect(screen.getByRole('spinbutton', { name: 'Peak IT power MW' })).toBeInTheDocument();
    await userEvent.click(start);
    const facility = await screen.findByRole('region', { name: 'Evaluated configuration' });
    expect(api.run).toHaveBeenCalledWith(nationwideId, 'current', expect.any(AbortSignal)); expect(api.run).toHaveBeenCalledTimes(1);
    expect(facility).toHaveTextContent('175 MW'); expect(facility).toHaveTextContent('Saved results for these inputs');
    expect(new URLSearchParams(window.location.search).get('run')).toBe(nationwideId);
    expect(screen.queryByRole('button', { name: 'Show nationwide areas · 1 km' })).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Edit facility' }));
    expect(screen.getByRole('spinbutton', { name: 'Peak IT power MW' })).toHaveValue(175);
    expect(api.search).not.toHaveBeenCalled();
  });
  it('keeps unevaluated edits when another saved run is loaded', async () => {
    window.history.replaceState({}, '', '/?run=CONCENTRATED');
    render(<App />); const coverage = await screen.findByRole('region', { name: 'Map analysis coverage' });
    await userEvent.click(screen.getByRole('button', { name: 'Edit facility' }));
    fireEvent.change(screen.getByRole('spinbutton', { name: 'Peak IT power MW' }), { target: { value: '140' } });
    await userEvent.click(within(coverage).getByRole('button', { name: 'Show nationwide areas · 1 km' }));
    await waitFor(() => expect(api.run).toHaveBeenCalledWith(nationwideId, 'current', expect.any(AbortSignal)));
    await waitFor(() => expect(screen.getByRole('status', { name: 'Evaluation status' })).toHaveTextContent('Configuration edited'));
    expect(screen.getByRole('spinbutton', { name: 'Peak IT power MW' })).toHaveValue(140);
    await userEvent.click(screen.getByRole('button', { name: 'Back to results' }));
    expect(screen.queryByRole('spinbutton', { name: 'Peak IT power MW' })).not.toBeInTheDocument();
    expect(screen.getByRole('region', { name: 'Evaluated configuration' })).toHaveTextContent('175 MW');
    expect(new URLSearchParams(window.location.search).get('run')).toBe(nationwideId);
    expect(api.search).not.toHaveBeenCalled(); expect(api.run).toHaveBeenCalledTimes(2);
  });
  it('keeps an explicit saved run until the user loads nationwide areas, clears selection and displays its saved configuration', async () => {
    window.history.replaceState({}, '', '/?run=CONCENTRATED&scenario=bau_2050&region=DEMO_ALPHA');
    render(<App />);
    const coverage = await screen.findByRole('region', { name: 'Map analysis coverage' });
    expect(coverage).toHaveTextContent('2 of 2 saved search areas match filters');
    expect(api.run).toHaveBeenCalledWith('CONCENTRATED', 'bau_2050', expect.any(AbortSignal));
    expect(api.run).toHaveBeenCalledTimes(1);
    await userEvent.click(within(coverage).getByRole('button', { name: 'Show nationwide areas · 1 km' }));
    await waitFor(() => expect(api.run).toHaveBeenCalledWith(nationwideId, 'current', expect.any(AbortSignal)));
    expect(screen.getByLabelText('Test geographic map')).toHaveAttribute('data-selected', '');
    expect(screen.getByRole('region', { name: 'Evaluated configuration' })).toHaveTextContent('175 MW');
    expect(new URLSearchParams(window.location.search).get('run')).toBe(nationwideId);
    expect(new URLSearchParams(window.location.search).get('scenario')).toBe('current');
    expect(screen.queryByRole('button', { name: 'Show nationwide areas · 1 km' })).not.toBeInTheDocument();
    act(() => window.history.back());
    await waitFor(() => expect(api.run).toHaveBeenLastCalledWith('CONCENTRATED', 'current', expect.any(AbortSignal)));
    await waitFor(() => expect(screen.getByRole('region', { name: 'Evaluated configuration' })).toHaveTextContent('100 MW'));
    expect(screen.getByLabelText('Test geographic map')).toHaveAttribute('data-selected', 'DEMO_ALPHA');
    expect(new URLSearchParams(window.location.search).get('run')).toBe('CONCENTRATED');
    expect(api.search).not.toHaveBeenCalled();
  });
  it('offers the latest completed run when no broad completed capability is available', async () => {
    api.capabilities.mockResolvedValue({ ...parseCapabilities(demoCapabilities), latestRunId: 'CONCENTRATED', nationwideRegionalRunId: null });
    render(<App />); await userEvent.click(await screen.findByRole('button', { name: 'open saved results' }));
    await screen.findByRole('region', { name: 'Evaluated configuration' });
    expect(api.run).toHaveBeenCalledWith('CONCENTRATED', 'current', expect.any(AbortSignal)); expect(api.run).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole('button', { name: 'Show nationwide areas · 1 km' })).not.toBeInTheDocument();
    expect(api.search).not.toHaveBeenCalled();
  });
  it('does not offer grid coverage navigation in County mode even if a capability supplies a grid run ID', async () => {
    window.history.replaceState({}, '', '/?model=county&run=COUNTY_SAVED');
    render(<App />); await screen.findByRole('region', { name: 'Evaluated configuration' });
    expect(screen.queryByRole('region', { name: 'Map analysis coverage' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Show nationwide areas · 1 km' })).not.toBeInTheDocument();
    expect(api.run).toHaveBeenCalledWith('COUNTY_SAVED', 'current', expect.any(AbortSignal));
  });
});
