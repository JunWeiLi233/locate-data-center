import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { useState } from 'react';
import { describe, expect, it, vi } from 'vitest';
import { ConfigurationForm } from './ConfigurationForm';
import { SearchScope } from './SearchScope';
import { parseCapabilities } from '../api/regions';
import { demoCapabilities, DEMO_CONFIG } from '../mocks/data';
import type { CachedRegionalCoverage, FacilityConfiguration } from '../types/domain';

const square = (west: number, south: number) => ({ type: 'Feature' as const, properties: { grid_id: `g-${west}` },
  geometry: { type: 'Polygon' as const, coordinates: [[[west, south], [west + 0.6, south], [west + 0.6, south + 0.45], [west, south + 0.45], [west, south]]] } });
const coverage: CachedRegionalCoverage = { runId: 'BASELINE', windowSizeM: 50000, cellSizeM: 1000, refinedWindows: 61, refinedCells: 152500,
  shortlistedWindows: 690, windows: { type: 'FeatureCollection', features: [square(-78, 42.6), square(-124, 47.2)] } };

describe('start screen search scope', () => {
  it('states where a fast search looks and that unassessed land is Unknown', () => {
    render(<SearchScope mode="cached_regional" coverage={coverage} scope="service scope" />);
    const card = screen.getByRole('region', { name: 'Search scope' });
    expect(card).toHaveTextContent('Where a fast search looks');
    expect(card).toHaveTextContent('61 refined windows, each 50 × 50 km: 152,500 cells already analyzed at 1 km.');
    expect(within(card).getByText('Not assessed at 1 km: Unknown, never zero or pass')).toBeInTheDocument();
  });
  it('falls back to the service scope text when the service sends no window outlines', () => {
    render(<SearchScope mode="cached_regional" coverage={null} scope="152500 evaluated 1 km cells in 61 fixed cached nationwide regional windows" />);
    expect(screen.getByRole('region', { name: 'Search scope' })).toHaveTextContent('152500 evaluated 1 km cells in 61 fixed cached nationwide regional windows');
    expect(screen.queryByText(/refined windows,/)).not.toBeInTheDocument();
  });
  it('describes a full search as covering the whole contiguous U.S.', () => {
    render(<SearchScope mode="full_rediscovery" coverage={coverage} scope="service scope" />);
    expect(screen.getByRole('region', { name: 'Search scope' })).toHaveTextContent(/Where a full search looks.*whole contiguous U\.S\./);
    expect(screen.queryByText(/refined windows/)).not.toBeInTheDocument();
  });
});

describe('start screen facility form', () => {
  const capabilities = parseCapabilities(demoCapabilities);
  function Harness({ onSubmit }: { onSubmit: (value: FacilityConfiguration) => void }) {
    const [configuration, setConfiguration] = useState<FacilityConfiguration>(DEMO_CONFIG);
    return <ConfigurationForm configuration={configuration} capabilities={capabilities} busy={false} onChange={setConfiguration} onSubmit={() => onSubmit(configuration)} />;
  }

  it('reads the facility back in plain terms and updates it as the inputs change', async () => {
    render(<Harness onSubmit={vi.fn()} />);
    expect(screen.getByText('80 MW average IT draw · in service 2030–2054')).toBeInTheDocument();
    const load = screen.getByRole('spinbutton', { name: 'Average load percent' });
    await userEvent.clear(load); await userEvent.type(load, '65');
    expect(screen.getByText('65 MW average IT draw · in service 2030–2054')).toBeInTheDocument();
  });
  it('offers cooling designs as one radio group and submits the chosen design', async () => {
    const submitted = vi.fn();
    render(<Harness onSubmit={submitted} />);
    const group = screen.getByRole('radiogroup', { name: 'Cooling design' });
    expect(within(group).getByRole('radio', { name: 'Compare both' })).toBeChecked();
    await userEvent.click(within(group).getByRole('radio', { name: 'Air · dry' }));
    await userEvent.click(screen.getByRole('button', { name: 'Find search areas' }));
    expect(submitted).toHaveBeenCalledWith(expect.objectContaining({ cooling: 'air_dry_assumed' }));
  });
  it('explains the output on the start form, not when editing evaluated results', () => {
    const { rerender } = render(<ConfigurationForm configuration={DEMO_CONFIG} capabilities={capabilities} busy={false} onChange={vi.fn()} onSubmit={vi.fn()} />);
    expect(screen.getByText(/You get search areas, not approved sites\./)).toBeInTheDocument();
    rerender(<ConfigurationForm configuration={DEMO_CONFIG} capabilities={capabilities} busy={false} onChange={vi.fn()} onSubmit={vi.fn()} onCancel={vi.fn()} />);
    expect(screen.queryByText(/You get search areas, not approved sites\./)).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Back to results' })).toBeInTheDocument();
  });
  it('offers saved results as the secondary action and says nothing is recomputed', async () => {
    const open = vi.fn();
    render(<ConfigurationForm configuration={DEMO_CONFIG} capabilities={capabilities} busy={false} onChange={vi.fn()} onSubmit={vi.fn()}
      savedResults={{ onOpen: open, note: 'The saved nationwide run opens instantly; nothing is recomputed.' }} />);
    const saved = screen.getByRole('button', { name: 'Open saved results' });
    expect(saved).toHaveAccessibleDescription('The saved nationwide run opens instantly; nothing is recomputed.');
    await userEvent.click(saved);
    expect(open).toHaveBeenCalledTimes(1);
  });
});
