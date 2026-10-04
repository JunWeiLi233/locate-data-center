import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import App from '../App';
import { parseCapabilities, parseRunResult } from '../api/regions';
import { DEMO_CONFIG, demoCapabilities, demoRun } from '../mocks/data';
import type { FacilityConfiguration } from '../types/domain';

const api = vi.hoisted(() => ({ capabilities: vi.fn(), run: vi.fn(), search: vi.fn(), layer: vi.fn(), socioeconomic: vi.fn() }));
vi.mock('../api/client', () => ({ locatorApi: api, isDemoMode: false }));
vi.mock('../api/monteCarlo', () => ({ createMonteCarloApi: () => api }));
vi.mock('../map/CandidateMap', () => ({ CandidateMap: () => <div aria-label="Test geographic map" /> }));

beforeEach(() => {
  vi.clearAllMocks(); window.history.replaceState({}, '', '/');
  api.capabilities.mockResolvedValue(parseCapabilities({ ...demoCapabilities, latest_run_id: null, default_analysis_mode: 'cached_regional', analysis_modes: [
    { id: 'cached_regional', label: 'Cached regional evaluation', available: true, reason: null },
    { id: 'full_rediscovery', label: 'Full rediscovery', available: true, reason: null },
  ] }));
});

describe('evaluated facility comparison', () => {
  it('accepts reordered weight keys from a fresh fast response while detecting an actual changed weight', async () => {
    api.search.mockImplementation((configuration: FacilityConfiguration) => {
      const result = parseRunResult(demoRun(configuration));
      result.configuration = { ...result.configuration, groupWeights: Object.fromEntries(Object.entries(configuration.groupWeights).reverse()) };
      return Promise.resolve(result);
    });
    render(<App />); await screen.findByRole('combobox', { name: 'Search depth' });
    fireEvent.change(screen.getByRole('spinbutton', { name: 'Peak IT power MW' }), { target: { value: '131' } });
    fireEvent.change(screen.getByRole('spinbutton', { name: 'Average load percent' }), { target: { value: '79' } });
    fireEvent.change(screen.getByRole('spinbutton', { name: 'Target opening year' }), { target: { value: '2031' } });
    fireEvent.change(screen.getByRole('spinbutton', { name: 'Operating lifetime years' }), { target: { value: '30' } });
    await userEvent.click(screen.getByText('More options'));
    await userEvent.selectOptions(screen.getByRole('combobox', { name: 'Decision preferences' }), 'user');
    fireEvent.change(screen.getByRole('spinbutton', { name: 'Power & Carbon weight' }), { target: { value: '3' } });
    fireEvent.change(screen.getByRole('spinbutton', { name: 'Water Stewardship weight' }), { target: { value: '1' } });
    await userEvent.click(screen.getByRole('button', { name: 'Find locations' }));
    await screen.findByRole('region', { name: 'Evaluated configuration' });
    expect(api.search.mock.calls[0][3]).toBe('cached_regional');
    expect(screen.getByRole('status', { name: 'Evaluation status' })).not.toHaveTextContent('Configuration edited');
    await userEvent.click(screen.getByRole('button', { name: 'Edit facility' }));
    fireEvent.change(screen.getByRole('spinbutton', { name: 'Power & Carbon weight' }), { target: { value: '4' } });
    expect(screen.getByRole('status', { name: 'Evaluation status' })).toHaveTextContent('Configuration edited');
  });
  it('compares nested County settings independent of property order while preserving changed audit flags', async () => {
    window.history.replaceState({}, '', '/?model=county');
    const configuration: FacilityConfiguration = { ...DEMO_CONFIG, monteCarlo: { settingsJson: '{}', sensitivity: true, convergence: true } };
    api.capabilities.mockResolvedValue({ ...parseCapabilities(demoCapabilities), latestRunId: null, modelKind: 'monte-carlo', defaultConfiguration: configuration });
    api.search.mockImplementation((submitted: FacilityConfiguration) => {
      const result = parseRunResult(demoRun(submitted));
      result.configuration.monteCarlo = { convergence: true, sensitivity: true, settingsJson: '{}' };
      return Promise.resolve(result);
    });
    render(<App />); await waitFor(() => expect(screen.getByRole('button', { name: 'Find locations' })).toBeEnabled());
    await userEvent.click(screen.getByRole('button', { name: 'Find locations' }));
    await screen.findByRole('region', { name: 'Evaluated configuration' });
    expect(screen.getByRole('status', { name: 'Evaluation status' })).not.toHaveTextContent('Configuration edited');
    await userEvent.click(screen.getByRole('button', { name: 'Edit facility' }));
    await userEvent.click(screen.getByText('More options'));
    await userEvent.click(screen.getByRole('checkbox', { name: 'Run sensitivity audit' }));
    expect(screen.getByRole('status', { name: 'Evaluation status' })).toHaveTextContent('Configuration edited');
  });
});
