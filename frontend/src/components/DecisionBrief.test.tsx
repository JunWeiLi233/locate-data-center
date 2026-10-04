import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { DecisionBrief } from './DecisionBrief';
import { parseRunResult } from '../api/regions';
import { demoRun } from '../mocks/data';
import { DEMO_DECISION_BRIEF } from '../mocks/decisionBrief';

const result = () => parseRunResult({ ...demoRun(), decision_brief: DEMO_DECISION_BRIEF });
describe('six-deliverable decision brief', () => {
  it('displays the backend total-water value with its status and confidence', () => {
    const run=parseRunResult({...demoRun(),decision_brief:{...DEMO_DECISION_BRIEF,impact:{...DEMO_DECISION_BRIEF.impact,total_water_consumption:{id:'total_water_consumption_m3',value:800,unit:'m3 consumed/year',status:'calculated',confidence:'low',missing_reason:null}}}});
    render(<DecisionBrief result={run} onClose={vi.fn()} />);
    expect(screen.getByText('800 m3 consumed/year')).toBeInTheDocument();
    expect(screen.getByText('calculated · confidence low')).toBeInTheDocument();
  });
  it('shows six sections, exact contributions, distinct geography and unknown impact boundaries', () => {
    render(<DecisionBrief result={result()} selectedRegionId="DEMO_BETA" onClose={vi.fn()} />);
    const dialog = screen.getByRole('dialog', { name: 'Decision brief' });
    for (const name of ['1. Investigation geography', '2. Decision framework', '3. Evidence and assumptions', '4. Resource impact', '5. Risks and verification', '6. Operating vision']) expect(within(dialog).getByRole('heading', { name })).toBeInTheDocument();
    expect(within(dialog).getByText('DEMO DATA · Synthetic software fixture')).toBeInTheDocument();
    expect(within(dialog).getByText(/Representative cell center: 39.325, -101.5/)).toBeInTheDocument();
    expect(within(dialog).getByText(/Search region center: 40, -102/)).toBeInTheDocument();
    expect(within(dialog).getByText('12.5')).toBeInTheDocument();
    expect(within(dialog).getByText('Electricity-generation water is unavailable.')).toBeInTheDocument();
    expect(within(dialog).getByText(/Proposed project plan/)).toBeInTheDocument();
    expect(within(dialog).getByText(/Selected region: DEMO_BETA/)).toBeInTheDocument();
    expect(within(dialog).getByText('210,240 m3/year')).toBeInTheDocument();
  });
  it('keeps a legacy run usable and explains why its verified brief is unavailable', () => {
    const run = parseRunResult({ ...demoRun(), decision_brief_unavailable_reason: 'Legacy run lacks verified lifecycle artifacts.' });
    render(<DecisionBrief result={run} onClose={vi.fn()} />);
    expect(screen.getByText('Legacy run lacks verified lifecycle artifacts.')).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: '1. Investigation geography' })).not.toBeInTheDocument();
  });
  it('presents an empty strict finding without inventing a selected geography', () => {
    const run = parseRunResult({ ...demoRun(), regions: [], decision_brief: { ...DEMO_DECISION_BRIEF, recommendation: { ...DEMO_DECISION_BRIEF.recommendation, status: 'NO_QUALIFYING_REGION', region_id: null, rank: null, score: null, centroid: null, region_centroid: null, metrics: [], rationale: 'Critical unknowns exclude alternatives.' }, alternatives: [] } });
    render(<DecisionBrief result={run} onClose={vi.fn()} />);
    expect(screen.getByText('No qualifying investigation region')).toBeInTheDocument();
    expect(screen.getByText('Critical unknowns exclude alternatives.')).toBeInTheDocument();
    expect(screen.queryByText(/Representative cell center:/)).not.toBeInTheDocument();
  });
  it('restores focus and uses only the supplied brief for printing', async () => {
    const close = vi.fn(); const print = vi.spyOn(window, 'print').mockImplementation(() => {});
    render(<DecisionBrief result={result()} onClose={close} />);
    expect(screen.getByRole('button', { name: 'Close decision brief' })).toHaveFocus();
    await userEvent.click(screen.getByRole('button', { name: 'Print decision brief' }));expect(print).toHaveBeenCalledOnce();
    await userEvent.keyboard('{Escape}');expect(close).toHaveBeenCalledOnce();print.mockRestore();
  });
});
