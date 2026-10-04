import { fireEvent, render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { useState } from 'react';
import { describe, expect, it, vi } from 'vitest';
import { ConfigurationForm } from './ConfigurationForm';
import { FactorBars } from './FactorBars';
import { SourceDetails } from './SourceDetails';
import { MobileSheet } from './MobileSheet';
import { LayerControls } from './LayerControls';
import { parseCapabilities } from '../api/regions';
import { demoCapabilities, DEMO_CONFIG } from '../mocks/data';
import { FACTOR_LABELS, type FacilityConfiguration, type Source } from '../types/domain';

const capabilities = parseCapabilities(demoCapabilities);
const source: Source = { name: 'Official study', url: 'https://example.gov/study', datasetYear: '2023', geography: 'Study intersection', resolution: '30 m', method: 'Area-weighted source aggregation', scenario: 'Historical baseline' };

describe('evidence and preferences', () => {
  it('renders six unknown factors when none are supplied instead of zero scores', () => {
    render(<FactorBars factors={[]} />); expect(screen.queryAllByRole('img')).toHaveLength(0); expect(document.querySelectorAll('.factor-fill')).toHaveLength(0);
    const unknown = document.querySelector('.factor-unknown') as HTMLElement; expect(within(unknown).getByText('Unknown')).toBeInTheDocument();
    for (const label of Object.values(FACTOR_LABELS)) expect(unknown).toHaveTextContent(label); expect(screen.queryByText(/^0(\.0)?$/)).not.toBeInTheDocument();
  });
  it('displays only a supplied backend score and its source method', () => {
    render(<FactorBars factors={[{ id: 'water', label: 'Water Availability', score: 72.5, direction: 'higher_is_better', basis: 'Fixed bounds supplied by backend', sources: [source] }]} />);
    expect(screen.getByRole('img', { name: 'Water Availability: 72.5 out of 100, higher is better' })).toBeInTheDocument(); expect(document.querySelector('.factor-fill')).toHaveStyle('width: 72.5%');
    expect(screen.getByText('Fixed bounds supplied by backend')).toBeInTheDocument(); expect(screen.getByText('Official study')).toBeInTheDocument();
  });
  it('retains source dates, units of resolution and safe external link behavior', () => {
    render(<SourceDetails sources={[source, { ...source, name: 'Unsafe source', url: 'javascript:alert(1)' }]} />);
    expect(screen.getAllByText('2023')).toHaveLength(2); expect(screen.getAllByText('30 m')).toHaveLength(2);
    const links = screen.getAllByRole('link', { hidden: true }); expect(links).toHaveLength(1); expect(links[0]).toHaveAttribute('rel', 'noopener noreferrer'); expect(links[0]).toHaveAttribute('href', source.url);
  });
  it('starts AHP with six unsupplied pair judgments and submits reciprocals without computing weights', async () => {
    const submitted = vi.fn();
    function Harness() { const [configuration, setConfiguration] = useState<FacilityConfiguration>({ ...DEMO_CONFIG, weighting: 'ahp', ahpMatrix: null }); return <ConfigurationForm configuration={configuration} capabilities={capabilities} busy={false} onChange={setConfiguration} onSubmit={() => submitted(configuration)} />; }
    render(<Harness />); const pairs = screen.getAllByPlaceholderText('1–9'); expect(pairs).toHaveLength(6); pairs.forEach(input => expect(input).toHaveValue(null));
    for (const [index, input] of pairs.entries()) fireEvent.change(input, { target: { value: index === 0 ? '3' : '1' } });
    await userEvent.click(screen.getByRole('button', { name: 'Find locations' }));
    expect(submitted).toHaveBeenCalledTimes(1); const config = submitted.mock.calls[0][0] as FacilityConfiguration;
    expect(config.ahpMatrix?.[0][1]).toBe(3); expect(config.ahpMatrix?.[1][0]).toBe(1 / 3); expect(config.ahpMatrix?.every((row, i) => row[i] === 1)).toBe(true);
    expect(screen.queryByText(/Final AHP weights/)).not.toBeInTheDocument();
  });
  it('requires positive facility load and power while retaining the actual four backend group identifiers', () => {
    render(<ConfigurationForm configuration={{ ...DEMO_CONFIG, peakItPowerMw: 0, weighting: 'user' }} capabilities={capabilities} busy={false} onChange={vi.fn()} onSubmit={vi.fn()} />);
    const power = screen.getByRole('spinbutton', { name: 'Peak IT power MW' }); expect(power).toBeInvalid();
    expect(screen.getByRole('spinbutton', { name: 'Average load percent' })).toHaveAttribute('min', '0.01');
    expect(screen.getByRole('group', { name: 'Relative importance of criteria groups' })).toBeInTheDocument();
    for (const group of capabilities.weightingGroups) expect(screen.getByRole('spinbutton', { name: `${group.label} weight` })).toBeInTheDocument();
  });
  it('supports pointer adjustment plus bounded accessible positions on the mobile sheet', async () => {
    const height = vi.fn(); render(<MobileSheet onHeightChange={height}><p>Mobile contents</p></MobileSheet>);
    const handle = document.querySelector('.sheet-handle') as HTMLElement; handle.setPointerCapture = vi.fn();
    fireEvent.pointerDown(handle, { pointerId: 1, clientY: 500 }); fireEvent.pointerMove(handle, { pointerId: 1, clientY: -500 }); fireEvent.pointerUp(handle);
    await userEvent.click(screen.getByRole('button', { name: 'Expand bottom sheet' })); expect(height).toHaveBeenLastCalledWith(88);
    await userEvent.click(screen.getByRole('button', { name: 'Minimize bottom sheet' })); expect(height).toHaveBeenLastCalledWith(18);
    expect(within(document.querySelector('.sheet-content') as HTMLElement).getByText('Mobile contents')).toBeInTheDocument();
  });
  it('starts URL-selected details at half height and preserves explicit resizing across same-selection updates', async () => {
    const view = render(<MobileSheet selectionKey="URL_SELECTED"><p>Original evaluated detail</p></MobileSheet>);
    const sheet = screen.getByRole('button', { name: 'Expand bottom sheet' }).closest('.mobile-sheet')!;
    expect(sheet).toHaveStyle('--sheet-height: 48dvh'); await userEvent.click(screen.getByRole('button', { name: 'Expand bottom sheet' }));
    view.rerender(<MobileSheet selectionKey="URL_SELECTED"><p>Updated request detail</p></MobileSheet>);
    expect(screen.getByText('Updated request detail')).toBeInTheDocument(); expect(sheet).toHaveStyle('--sheet-height: 88dvh');
  });
  it('toggles terrain relief and forest canopy context independently of model indicators', async () => {
    const change = vi.fn();
    render(<LayerControls capabilities={capabilities.layers} selections={[]} onChange={vi.fn()} availableRun={false} basemap={{ relief: true, forest: true }} onBasemapChange={change} />);
    await userEvent.click(screen.getByText('Map layers'));
    expect(screen.getByRole('checkbox', { name: 'Terrain relief' })).toBeEnabled();
    await userEvent.click(screen.getByRole('checkbox', { name: 'Forest canopy' }));
    expect(change).toHaveBeenLastCalledWith({ relief: true, forest: false });
    await userEvent.click(screen.getByRole('checkbox', { name: 'Terrain relief' }));
    expect(change).toHaveBeenLastCalledWith({ relief: false, forest: true });
    expect(screen.getByText(/not analyzed coverage/)).toBeInTheDocument();
  });
  it('omits basemap context toggles when a custom basemap style supplies its own geography', () => {
    render(<LayerControls capabilities={capabilities.layers} selections={[]} onChange={vi.fn()} availableRun={false} />);
    expect(screen.queryByRole('checkbox', { name: 'Terrain relief' })).not.toBeInTheDocument();
  });
  it('shows each custom weight as its share of the total and reads AHP judgments in plain words', () => {
    const view = render(<ConfigurationForm configuration={{ ...DEMO_CONFIG, weighting: 'user', groupWeights: { energy_carbon: 2, water_stewardship: 1, grid_infrastructure: 1, land: 0 } }} capabilities={capabilities} busy={false} onChange={vi.fn()} onSubmit={vi.fn()} />);
    expect(screen.getByRole('status', { name: 'Power & Carbon share' })).toHaveTextContent('50%');
    expect(screen.getByRole('status', { name: 'Water Stewardship share' })).toHaveTextContent('25%');
    expect(screen.getByRole('status', { name: 'Land share' })).toHaveTextContent('0%');
    view.rerender(<ConfigurationForm configuration={{ ...DEMO_CONFIG, weighting: 'ahp', ahpMatrix: null }} capabilities={capabilities} busy={false} onChange={vi.fn()} onSubmit={vi.fn()} />);
    const pair = screen.getByRole('spinbutton', { name: 'Power & Carbon compared with Water Stewardship' });
    expect(pair.closest('label')).toHaveTextContent('Not entered yet.');
    fireEvent.change(pair, { target: { value: '3' } });
    expect(pair.closest('label')).toHaveTextContent('Power & Carbon counts 3× as much as Water Stewardship.');
    fireEvent.change(pair, { target: { value: '0.5' } });
    expect(pair.closest('label')).toHaveTextContent('Water Stewardship counts 2× as much as Power & Carbon.');
  });
});
