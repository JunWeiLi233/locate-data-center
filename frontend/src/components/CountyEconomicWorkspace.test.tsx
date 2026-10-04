import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import App from '../App';
import { parseCapabilities, parseLayer, parseRunResult, parseSocioeconomic } from '../api/regions';
import { demoCapabilities, demoLayer, demoRun } from '../mocks/data';
import { demoCountyEconomic, demoSocioeconomic } from '../mocks/socioeconomic';
import type { CandidateMapProps } from '../map/CandidateMap';

const api = vi.hoisted(() => ({ capabilities: vi.fn(), search: vi.fn(), run: vi.fn(), layer: vi.fn(), socioeconomic: vi.fn() }));
vi.mock('../api/client', () => ({ locatorApi: api, isDemoMode: false }));
vi.mock('../map/CandidateMap', () => ({ CandidateMap: (props: CandidateMapProps) => <div aria-label="Test geographic map" data-layer-ids={props.layers?.map(layer => layer.id).join(',')}>{props.regions.map(region => <button key={region.id} onClick={() => props.onSelect(region.id)}>Map select {region.id}</button>)}</div> }));

function context(year = 2025, scenario = 'current') {
  const split = [demoCountyEconomic({ boundary_year: year, poverty_rate_pct: 30, income_usd: 90000, poverty_percentile: 90, low_income_percentile: 10 }), demoCountyEconomic({ county_geoid: '01003', county_name: 'DEMO County Beta', boundary_year: year, poverty_rate_pct: 10, income_usd: 40000, poverty_percentile: 10, low_income_percentile: 90 })];
  return parseSocioeconomic({ ...demoSocioeconomic({ DEMO_ALPHA: split, DEMO_BETA: split, DEMO_GAMMA: [demoCountyEconomic({ county_geoid: '01005', county_name: 'DEMO County Gamma', boundary_year: year })] }, year), scenario_id: scenario });
}
beforeEach(() => {
  vi.clearAllMocks(); window.history.replaceState({}, '', '/?run=DEMO_RUN&region=DEMO_ALPHA');
  const capabilities = parseCapabilities(demoCapabilities);
  capabilities.layers = capabilities.layers.map(layer => layer.id === 'community_economic' ? { ...layer, available: true, label: 'County economic need (2024 SAIPE)', reason: null, sublayers: ['poverty', 'income', 'poverty_percentile', 'low_income_percentile'].map(id => ({ id, label: id, available: true })) } : layer);
  api.capabilities.mockResolvedValue(capabilities); api.run.mockResolvedValue(parseRunResult(demoRun()));
  api.socioeconomic.mockImplementation((_run, year, scenario) => Promise.resolve(context(year, scenario)));
  api.layer.mockResolvedValue({ ...parseLayer(demoLayer('water')), id: 'community_economic' });
});

describe('county economic workspace', () => {
  it('filters list and map by same-county percentiles and clears all four optional thresholds', async () => {
    render(<App />); await screen.findByRole('button', { name: 'Select Candidate Alpha, Air / dry (assumed)' });
    await userEvent.click(screen.getByText('Filter areas'));
    const povertyPercentile = screen.getByRole('spinbutton', { name: 'Minimum 2024 poverty percentile (0–100)' });
    const lowIncomePercentile = screen.getByRole('spinbutton', { name: 'Minimum 2024 low-income percentile (0–100)' });
    await waitFor(() => expect(povertyPercentile).toBeEnabled());
    expect(povertyPercentile).toHaveValue(null); expect(lowIncomePercentile).toHaveValue(null);
    expect(screen.getByRole('button', { name: 'Clear county filters' })).toBeDisabled();
    fireEvent.change(povertyPercentile, { target: { value: '80' } }); fireEvent.change(lowIncomePercentile, { target: { value: '75' } });
    expect(screen.getByText('2 active')).toBeInTheDocument();
    const list = screen.getByRole('region', { name: 'Potential regions' });
    expect(within(list).queryByRole('button', { name: /Select Candidate Alpha/ })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Map select DEMO_ALPHA' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Map select DEMO_BETA' })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Map select DEMO_GAMMA' })).toBeInTheDocument();
    expect(screen.getByText('1 of 2 areas shown')).toBeInTheDocument();
    expect(screen.getByRole('region', { name: 'Map analysis coverage' })).toHaveTextContent('1 of 2 saved search areas match filters');
    expect(screen.getByRole('complementary', { name: 'Details for Candidate Alpha' })).toHaveTextContent('Rank #1');
    fireEvent.change(screen.getByRole('spinbutton', { name: 'Minimum 2024 county poverty rate (%)' }), { target: { value: '20' } });
    fireEvent.change(screen.getByRole('spinbutton', { name: 'Maximum 2024 median household income (USD)' }), { target: { value: '50000' } });
    expect(screen.getByText('4 active')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Clear county filters' }));
    for (const input of within(screen.getByRole('group', { name: 'County economic context' })).getAllByRole('spinbutton')) expect(input).toHaveValue(null);
    expect(screen.queryByText(/\d active/)).not.toBeInTheDocument();
    expect(screen.getByRole('region', { name: 'Map analysis coverage' })).toHaveTextContent('2 of 2 saved search areas match filters');
    expect(screen.getByRole('button', { name: 'Map select DEMO_ALPHA' })).toBeInTheDocument();
    expect(within(list).getByRole('button', { name: 'Select Candidate Alpha, Air / dry (assumed)' })).toHaveTextContent('#1');
    expect(api.search).not.toHaveBeenCalled();
  });
  it('filters list and map with same-county thresholds while retaining technical values and selected details', async () => {
    render(<App />); await screen.findByRole('button', { name: 'Select Candidate Alpha, Air / dry (assumed)' });
    await userEvent.click(screen.getByText('Filter areas'));
    const poverty = screen.getByRole('spinbutton', { name: 'Minimum 2024 county poverty rate (%)' });
    const income = screen.getByRole('spinbutton', { name: 'Maximum 2024 median household income (USD)' });
    await waitFor(() => expect(poverty).toBeEnabled());
    expect(poverty).toHaveValue(null); expect(income).toHaveValue(null);
    fireEvent.change(poverty, { target: { value: '20' } }); fireEvent.change(income, { target: { value: '50000' } });
    const list = screen.getByRole('region', { name: 'Potential regions' });
    expect(within(list).queryByRole('button', { name: 'Select Candidate Alpha, Air / dry (assumed)' })).not.toBeInTheDocument();
    expect(within(list).getByRole('button', { name: 'Select Candidate Gamma, Air / dry (assumed)' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Map select DEMO_ALPHA' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Map select DEMO_BETA' })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Map select DEMO_GAMMA' })).toBeInTheDocument();
    expect(screen.getByText('1 of 2 areas shown')).toBeInTheDocument();
    const details = screen.getByRole('complementary', { name: 'Details for Candidate Alpha' });
    expect(details).toHaveTextContent('87.4'); expect(details).toHaveTextContent('Rank #1');
    expect(details).toHaveTextContent('DEMO County Alpha'); expect(details).toHaveTextContent('DEMO County Beta');
    expect(details).toHaveTextContent('2024 poverty rate'); expect(details).toHaveTextContent('2024 median household income');
    expect(details).toHaveTextContent('all valid CONUS SAIPE counties');
    expect(details).toHaveTextContent('Unknown — fiscal inputs not acquired');
    expect(api.search).not.toHaveBeenCalled(); expect(api.run).toHaveBeenCalledTimes(1);
    fireEvent.change(poverty, { target: { value: '' } }); fireEvent.change(income, { target: { value: '' } });
    expect(screen.getByRole('button', { name: 'Map select DEMO_ALPHA' })).toBeInTheDocument();
    expect(within(list).getByRole('button', { name: 'Select Candidate Alpha, Air / dry (assumed)' })).toHaveTextContent('#1');
  });
  it('changes filter boundary context without map controls or requests, including a legacy county URL', async () => {
    window.history.replaceState({}, '', '/?run=DEMO_RUN&layers=candidates,community_economic:poverty@2023');
    render(<App />); await screen.findByRole('button', { name: 'Select Candidate Alpha, Air / dry (assumed)' });
    await userEvent.click(screen.getByText('Filter areas'));
    const vintage = screen.getByRole('combobox', { name: 'Boundary vintage' }); expect(vintage).toHaveValue('2025');
    await userEvent.click(screen.getByText('Map layers'));
    expect(screen.queryByRole('checkbox', { name: 'County economic need (2024 SAIPE)' })).not.toBeInTheDocument();
    expect(screen.queryByRole('combobox', { name: 'County economic need (2024 SAIPE) indicator' })).not.toBeInTheDocument();
    expect(api.layer).not.toHaveBeenCalled();
    await userEvent.selectOptions(vintage, '2023');
    await waitFor(() => expect(api.socioeconomic).toHaveBeenCalledWith('DEMO_RUN', 2023, 'current', expect.any(AbortSignal)));
    expect(within(screen.getByRole('group', { name: 'County economic context' })).getByText(/Generalized Census cartographic boundaries · 1:500,000/)).toBeInTheDocument();
    expect(api.layer).not.toHaveBeenCalled();
    expect(screen.getByLabelText('Test geographic map')).toHaveAttribute('data-layer-ids', '');
    expect(api.search).not.toHaveBeenCalled(); expect(api.run).toHaveBeenCalledTimes(1);
  });
  it('retains legacy results when county context is unavailable and disables unsupported filters', async () => {
    const capabilities = parseCapabilities(demoCapabilities); api.capabilities.mockResolvedValue(capabilities);
    render(<App />); await screen.findByRole('button', { name: 'Select Candidate Alpha, Air / dry (assumed)' });
    await userEvent.click(screen.getByText('Filter areas'));
    expect(screen.getByRole('spinbutton', { name: 'Minimum 2024 county poverty rate (%)' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Map select DEMO_ALPHA' })).toBeInTheDocument();
    expect(api.socioeconomic).not.toHaveBeenCalled(); expect(api.search).not.toHaveBeenCalled();
  });
  it('lets users clear active county filters after an unavailable vintage request without treating missing values as matches', async () => {
    api.socioeconomic.mockImplementation((_run, year) => year === 2025 ? Promise.resolve(context(year)) : Promise.reject(new Error('County vintage unavailable')));
    render(<App />); await screen.findByRole('button', { name: 'Select Candidate Alpha, Air / dry (assumed)' });
    await userEvent.click(screen.getByText('Filter areas'));
    const poverty = screen.getByRole('spinbutton', { name: 'Minimum 2024 county poverty rate (%)' });
    const income = screen.getByRole('spinbutton', { name: 'Maximum 2024 median household income (USD)' });
    await waitFor(() => expect(poverty).toBeEnabled());
    fireEvent.change(poverty, { target: { value: '20' } }); fireEvent.change(income, { target: { value: '50000' } });
    await userEvent.selectOptions(screen.getByRole('combobox', { name: 'Boundary vintage' }), '2023');
    await waitFor(() => expect(poverty).toBeDisabled());
    const list = screen.getByRole('region', { name: 'Potential regions' });
    expect(within(list).queryByRole('button', { name: /Select Candidate/ })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Map select DEMO_GAMMA' })).not.toBeInTheDocument();
    const clear = screen.getByRole('button', { name: 'Clear county filters' }); expect(clear).toBeEnabled();
    await userEvent.click(clear);
    expect(poverty).toHaveValue(null); expect(income).toHaveValue(null);
    expect(screen.getByRole('button', { name: 'Map select DEMO_ALPHA' })).toBeInTheDocument();
    expect(within(list).getByRole('button', { name: 'Select Candidate Alpha, Air / dry (assumed)' })).toHaveTextContent('#1');
    expect(clear).toBeDisabled(); expect(api.search).not.toHaveBeenCalled();
  });
});
