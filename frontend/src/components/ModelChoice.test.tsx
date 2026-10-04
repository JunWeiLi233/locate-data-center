import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, expect, it, vi } from 'vitest';
import App from '../App';
import { parseCapabilities } from '../api/regions';
import { demoCapabilities } from '../mocks/data';

const control = vi.hoisted(() => ({ capabilities: vi.fn(), switchModel: vi.fn() }));
vi.mock('../api/client', () => ({ locatorApi: { capabilities: control.capabilities }, isDemoMode: false }));
vi.mock('../utils/modelChoice', async importOriginal => ({ ...await importOriginal<typeof import('../utils/modelChoice')>(), switchModel: control.switchModel }));
vi.mock('../map/CandidateMap', () => ({ CandidateMap: () => <div aria-label="Synthetic model-choice map fixture" /> }));

beforeEach(() => {
  window.history.replaceState({}, '', '/'); vi.clearAllMocks();
  const capabilities = parseCapabilities(demoCapabilities); capabilities.latestRunId = null;
  control.capabilities.mockResolvedValue(capabilities);
});

it('shows the grid default and a visible county choice that requests an isolated reload', async () => {
  render(<App />);
  await waitFor(() => expect(screen.getByRole('button', { name: 'Find locations' })).toBeEnabled());
  const choice = screen.getByRole('combobox', { name: 'Model' });
  expect(choice).toHaveValue('grid');
  await userEvent.selectOptions(choice, 'county');
  expect(control.switchModel).toHaveBeenCalledWith('county');
});

it('reflects the county URL before capabilities are available and reports readiness errors', async () => {
  window.history.replaceState({}, '', '/?model=county');
  control.capabilities.mockRejectedValue(new Error('County frozen inputs unavailable.'));
  render(<App />);
  await screen.findByText('County frozen inputs unavailable.');
  expect(screen.getByRole('combobox', { name: 'Model' })).toHaveValue('county');
  expect(screen.getByRole('button', { name: 'Find locations' })).toBeDisabled();
});
