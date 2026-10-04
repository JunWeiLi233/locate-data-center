import { render, renderHook, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { LayerControls } from './LayerControls';
import { IndicatorEvidence } from './IndicatorEvidence';
import { useLayers } from '../hooks/useLayers';
import { parseLayer, parseRegion, parseRunResult } from '../api/regions';
import { demoLayer, demoRun } from '../mocks/data';

const api = vi.hoisted(() => ({ layer: vi.fn() }));
vi.mock('../api/client', () => ({ locatorApi: api }));
const countyLayer = { id: 'community_economic' as const, label: 'County economic need (2024 SAIPE)', available: true, reason: null,
  sublayers: ['poverty', 'income', 'poverty_percentile', 'low_income_percentile'].map(id => ({ id, label: id, available: true })) };
const regional = () => parseRunResult({ ...demoRun(), analysis: { analysis_level: 'regional', cell_size_m: 1000, maximum_region_extent_km: 20 } });
beforeEach(() => { vi.clearAllMocks(); api.layer.mockResolvedValue({ ...parseLayer(demoLayer('water')), id: 'community_economic' }); });

describe('county economic layer isolation', () => {
  it('omits available county views from every map control', async () => {
    render(<LayerControls capabilities={[countyLayer]} selections={[]} onChange={vi.fn()} availableRun regional activeWindow={false} />);
    await userEvent.click(screen.getByText('Map layers'));
    expect(screen.queryByRole('checkbox', { name: countyLayer.label })).not.toBeInTheDocument();
    expect(screen.queryByRole('combobox', { name: `${countyLayer.label} indicator` })).not.toBeInTheDocument();
    expect(screen.queryByText('County map boundary vintage')).not.toBeInTheDocument();
  });
  it('omits unavailable county capabilities rather than listing them as map layers', async () => {
    render(<LayerControls capabilities={[{ ...countyLayer, available: false, reason: 'Not acquired' }]} selections={[]} onChange={vi.fn()} availableRun />);
    await userEvent.click(screen.getByText('Map layers'));
    expect(screen.queryByText(/Not available in this model/)).not.toBeInTheDocument();
    expect(screen.queryByText(countyLayer.label)).not.toBeInTheDocument();
  });
  it('ignores legacy county selections synchronously without requests or returned overlays', () => {
    const value = regional();
    const selections = [{ id: 'community_economic' as const, enabled: true, sublayer: 'poverty@2023' }];
    const exposures: ReturnType<typeof useLayers>['layers'][] = [];
    const view = renderHook(({ selected }) => { const result = useLayers(value, selections, selected); exposures.push(result.layers); return result; }, { initialProps: { selected: null as string | null } });
    expect(view.result.current.layers).toEqual([]); expect(api.layer).not.toHaveBeenCalled();
    view.rerender({ selected: 'DEMO_ALPHA' });
    expect(exposures.every(layers => layers.length === 0)).toBe(true); expect(api.layer).not.toHaveBeenCalled();
  });
  it('keeps economic context outside factor scores and preserves the technical score and rank', () => {
    const value = parseRegion({ region_id: 'REGION', screening_status: 'PASS', rank: 7, overall_score: 73,
      factors: [{ id: 'community_economic', direction: 'higher_is_better', score: 90 }, { id: 'water', direction: 'higher_is_better', score: 42 }] });
    expect(value.factors.find(factor => factor.id === 'community_economic')?.score).toBeNull();
    expect(value.factors.find(factor => factor.id === 'water')?.score).toBe(42);
    expect(value.rank).toBe(7); expect(value.score).toBe(73);
  });
  it('does not render a county legend from a stale overlay payload', () => {
    const layer = parseLayer({ ...demoLayer('water'), id: 'community_economic', schema_version: '1.6.0',
      label: 'Poverty rate', direction: 'neutral', socioeconomic_year: 2024, boundary_year: 2023,
      boundary_source_kind: 'cartographic_500k', source_metadata: { estimate_source: { name: 'DEMO SAIPE', url: 'https://example.gov/saipe', year: 2024 }, boundary_source: { name: 'DEMO county boundaries', url: 'https://example.gov/county', year: 2023, scale: '1:500000' } } });
    render(<IndicatorEvidence layers={[layer]} onInspect={vi.fn()} />);
    expect(screen.queryByRole('region', { name: 'Selected indicator legends' })).not.toBeInTheDocument();
    expect(screen.queryByText(/County economic need/)).not.toBeInTheDocument();
  });
});
