/** Rediscovery view behavior with the labeled synthetic fixture; the map is replaced by a test double. */
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { CandidateMapProps } from '../../map/CandidateMap';
import { parseRediscovery, parseRediscoveryIndex, type RediscoveryApi } from '../../api/rediscovery';
import { syntheticRediscoveryIndex, syntheticRediscoveryPayload } from '../../mocks/rediscovery';
import { RediscoveryWorkspace } from './RediscoveryWorkspace';

const seen = vi.hoisted(() => ({ props: null as CandidateMapProps | null }));
vi.mock('../../map/CandidateMap', () => ({
  CandidateMap: (props: CandidateMapProps) => {
    seen.props = props;
    const layers = props.overlays?.layers ?? [];
    const candidates = layers.find(layer => layer.id === 'rediscovery-candidates');
    return <div aria-label="Rediscovery test map">
      {layers.filter(layer => layer.visible).map(layer => <span key={layer.id} data-testid={`visible-${layer.id}`} />)}
      {(props.overlays?.images ?? []).filter(image => image.visible).map(image => <span key={image.id} data-testid={`visible-${image.id}`} />)}
      {candidates?.data.features.map(feature => <button key={String(feature.properties?.overlayId)} onClick={() => props.onOverlaySelect?.(String(feature.properties?.overlayId))}>
        Map {String(feature.properties?.overlayId)}</button>)}
      <button onClick={() => props.onOverlaySelect?.('facility:fixture:dc1')}>Map facility</button>
    </div>;
  },
}));

function api(overrides: Partial<RediscoveryApi> = {}): RediscoveryApi {
  return {
    index: vi.fn().mockResolvedValue(parseRediscoveryIndex(syntheticRediscoveryIndex)),
    result: vi.fn().mockResolvedValue(parseRediscovery(syntheticRediscoveryPayload())),
    ...overrides,
  };
}
const visible = (id: string) => screen.queryByTestId(`visible-${id}`) !== null;

beforeEach(() => {
  window.history.replaceState({}, '', '/?view=rediscovery');
  window.matchMedia = vi.fn().mockImplementation(query => ({ matches: false, media: query, addEventListener: vi.fn(), removeEventListener: vi.fn() }));
});

describe('rediscovery workspace', () => {
  it('shows backend hit rates, baselines and classification for the chosen Top N', async () => {
    const client = api();
    render(<RediscoveryWorkspace viewSwitch={<span>switch</span>} api={client} />);
    await screen.findByRole('heading', { name: 'Model validation' });
    expect(client.result).toHaveBeenCalledWith('demo_fixture', expect.any(AbortSignal));
    // 100 is not offered by this fixture, so the largest available N up to 100 (4) is shown.
    expect(screen.getByRole('button', { name: '4' })).toHaveAttribute('aria-pressed', 'true');
    const table = screen.getAllByRole('table')[0];
    expect(within(table).getByRole('row', { name: /25 km/ })).toHaveTextContent('50.0%');
    expect(within(table).getByRole('row', { name: /25 km/ })).toHaveTextContent('10.0%');
    await userEvent.click(screen.getByRole('button', { name: '2' }));
    expect(within(screen.getAllByRole('table')[0]).getByRole('row', { name: /10 km/ })).toHaveTextContent('0.0%');
    expect(window.location.search).toContain('top=2');
    expect(screen.getByText(/AUC 0.71/)).toBeInTheDocument();
  });

  it('opens candidate details with the generated explanation, factors and honest robustness', async () => {
    render(<RediscoveryWorkspace viewSwitch={null} api={api()} />);
    await screen.findByRole('heading', { name: 'Model validation' });
    await userEvent.click(screen.getByRole('button', { name: 'Show candidate 1, DEMO County 1, ZZ' }));
    const panel = screen.getByRole('complementary', { name: /Details for candidate 1/ });
    expect(within(panel).getByText('DEMO County 1, ZZ ranks highly because of synthetic fixture criteria.')).toBeInTheDocument();
    expect(within(panel).getByText('Not evaluated')).toBeInTheDocument();
    expect(within(panel).getByText('Synthetic: county not in cohort')).toBeInTheDocument();
    expect(within(panel).getByText('Suitable land cover')).toBeInTheDocument();
    expect(within(panel).getByText(/shares its score with 1 other cell/)).toBeInTheDocument();
    expect(window.location.search).toContain('candidate=1');
    await userEvent.click(screen.getByRole('button', { name: 'Map candidate:2' }));
    const second = screen.getByRole('complementary', { name: /Details for candidate 2/ });
    expect(within(second).getByText(/county-level Monte Carlo/)).toBeInTheDocument();
    await userEvent.click(within(second).getByRole('button', { name: 'Close candidate details' }));
    expect(screen.queryByRole('complementary', { name: /Details for candidate/ })).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Map facility' }));
    expect(screen.getByRole('region', { name: 'Map feature information' })).toHaveTextContent('External validation only');
  });

  it('toggles layers and runs the guided demo from hidden facilities to revealed overlap', async () => {
    render(<RediscoveryWorkspace viewSwitch={null} api={api()} />);
    await screen.findByRole('heading', { name: 'Model validation' });
    expect(visible('rediscovery-facilities') && visible('rediscovery-candidates')).toBe(true);
    await userEvent.click(screen.getByRole('button', { name: /Existing data centers \(2\)/ }));
    expect(visible('rediscovery-facilities')).toBe(false);
    await userEvent.click(screen.getByRole('button', { name: 'Model score surface' }));
    expect(visible('rediscovery-surface')).toBe(true);
    await userEvent.click(screen.getByRole('button', { name: 'Guided demo' }));
    expect(screen.getByRole('heading', { name: 'Start with the contiguous United States' })).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Next' }));
    expect(visible('rediscovery-facilities')).toBe(true);
    await userEvent.click(screen.getByRole('button', { name: 'Next' }));
    expect(screen.getByRole('heading', { name: /Hide them/ })).toBeInTheDocument();
    expect(visible('rediscovery-facilities') || visible('rediscovery-candidates')).toBe(false);
    for (let step = 0; step < 4; step += 1) await userEvent.click(screen.getByRole('button', { name: 'Next' }));
    expect(screen.getByRole('heading', { name: 'Geographic overlap' })).toBeInTheDocument();
    expect(screen.getByText(/1 are validated .* 2 are emerging/)).toBeInTheDocument();
    expect(visible('rediscovery-validated-fill') && visible('rediscovery-emerging-line')).toBe(true);
    for (let step = 0; step < 3; step += 1) await userEvent.click(screen.getByRole('button', { name: 'Next' }));
    expect(screen.getByRole('heading', { name: 'Locations the model rediscovered' })).toBeInTheDocument();
    expect(screen.getByRole('complementary', { name: /Details for candidate 2/ })).toBeInTheDocument();
    expect(seen.props?.viewRequest?.camera.latitude).toBeCloseTo(41);
    await userEvent.click(screen.getByRole('button', { name: 'Exit guided demo' }));
    expect(visible('rediscovery-facilities') && visible('rediscovery-candidates')).toBe(true);
  });

  it('reports service errors with a retry and never substitutes demo data', async () => {
    const failing = api({ index: vi.fn().mockRejectedValueOnce(new Error('The local API does not offer the rediscovery check yet.'))
      .mockResolvedValue(parseRediscoveryIndex(syntheticRediscoveryIndex)) });
    render(<RediscoveryWorkspace viewSwitch={null} api={failing} />);
    expect(await screen.findAllByText('The local API does not offer the rediscovery check yet.')).not.toHaveLength(0);
    await userEvent.click(screen.getAllByRole('button', { name: 'Retry' })[0]);
    await screen.findByRole('heading', { name: 'Model validation' });
  });

  it('explains that DEMO DATA mode has no rediscovery fixture', async () => {
    const client = api();
    render(<RediscoveryWorkspace viewSwitch={null} api={client} demo />);
    await waitFor(() => expect(screen.getByRole('heading', { name: 'Real analysis required' })).toBeInTheDocument());
    expect(client.index).not.toHaveBeenCalled();
  });
});
