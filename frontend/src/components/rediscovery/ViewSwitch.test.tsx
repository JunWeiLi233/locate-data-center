/** Header view switch: the rediscovery check is a separate read-only view with its own URL and Back entry. */
import { act, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import App from '../../App';
import { parseCapabilities } from '../../api/regions';
import { demoCapabilities } from '../../mocks/data';
import { syntheticRediscoveryIndex, syntheticRediscoveryPayload } from '../../mocks/rediscovery';
import type { CandidateMapProps } from '../../map/CandidateMap';

const adapters = vi.hoisted(() => ({
  grid: { capabilities: vi.fn(), search: vi.fn(), run: vi.fn(), layer: vi.fn(), socioeconomic: vi.fn() },
  rediscovery: { index: vi.fn(), result: vi.fn() },
}));
vi.mock('../../api/client', () => ({ locatorApi: adapters.grid, isDemoMode: false }));
vi.mock('../../api/rediscovery', async original => ({ ...(await original<typeof import('../../api/rediscovery')>()), rediscoveryApi: adapters.rediscovery }));
vi.mock('../../map/CandidateMap', () => ({ CandidateMap: (props: CandidateMapProps) => <div aria-label="View test map">{props.overlays ? 'overlays' : 'regions'}</div> }));

beforeEach(async () => {
  window.history.replaceState({}, '', '/');
  vi.clearAllMocks();
  const { parseRediscovery, parseRediscoveryIndex } = await vi.importActual<typeof import('../../api/rediscovery')>('../../api/rediscovery');
  const capabilities = parseCapabilities(demoCapabilities);
  capabilities.latestRunId = null; capabilities.demo = false;
  adapters.grid.capabilities.mockResolvedValue(capabilities);
  adapters.rediscovery.index.mockResolvedValue(parseRediscoveryIndex(syntheticRediscoveryIndex));
  adapters.rediscovery.result.mockResolvedValue(parseRediscovery(syntheticRediscoveryPayload()));
  window.matchMedia = vi.fn().mockImplementation(query => ({ matches: false, media: query, addEventListener: vi.fn(), removeEventListener: vi.fn() }));
});

describe('view switch', () => {
  it('opens the rediscovery check in a new history entry and Back returns to the search view', async () => {
    render(<App />);
    expect(await screen.findByRole('button', { name: 'Search areas' })).toHaveAttribute('aria-pressed', 'true');
    expect(adapters.rediscovery.index).not.toHaveBeenCalled();
    await userEvent.click(screen.getByRole('button', { name: 'Rediscovery check' }));
    expect(await screen.findByRole('heading', { name: 'Model validation' })).toBeInTheDocument();
    expect(window.location.search).toContain('view=rediscovery');
    expect(screen.getByRole('button', { name: 'Rediscovery check' })).toHaveAttribute('aria-pressed', 'true');
    expect(adapters.grid.search).not.toHaveBeenCalled();
    window.history.replaceState({ locator: true }, '', '/');
    await act(async () => { window.dispatchEvent(new PopStateEvent('popstate')); });
    expect(await screen.findByRole('button', { name: 'Search areas' })).toHaveAttribute('aria-pressed', 'true');
    expect(screen.queryByRole('heading', { name: 'Model validation' })).not.toBeInTheDocument();
  });

  it('restores the rediscovery view from its URL', async () => {
    window.history.replaceState({}, '', '/?view=rediscovery&top=2&candidate=2');
    render(<App />);
    expect(await screen.findByRole('complementary', { name: /Details for candidate 2/ })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '2' })).toHaveAttribute('aria-pressed', 'true');
  });
});
