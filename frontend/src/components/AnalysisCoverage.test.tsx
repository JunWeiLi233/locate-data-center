import { fireEvent, render, screen, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { parseRunResult } from '../api/regions';
import { demoRun } from '../mocks/data';
import type { RegionalAnalysis, RunResult } from '../types/domain';
import { AnalysisCoverage } from './AnalysisCoverage';
import { RunSummary } from './RunSummary';

const analysis: RegionalAnalysis = {
  analysisLevel: 'regional', parentRunId: 'PARENT_FIXTURE', parentRunPath: 'runs/parent_fixture',
  gridDefinitionId: 'UI_FIXTURE_GRID', cellSizeM: 1000, maximumRegionExtentKm: 20,
  refinedCells: 5000, nationalCells: 3384, shortlistedParentCells: 690,
  refinedParentCells: 2, refinedAreaKm2: 5000, shortlistedParentAreaKm2: 1725000,
  rankingUniverse: 'all_evaluated_refined_alternatives',
};

function summary(overrides: Partial<RunResult> = {}) {
  const result = { ...parseRunResult(demoRun()), analysis, analysisResolutionM: 50000, analyzedCellCount: 5000, ...overrides };
  return render(<RunSummary result={result} groups={[]} />);
}

describe('visible run analysis coverage', () => {
  it('shows actual regional cells, extent limit and partial coverage before Run details opens', () => {
    summary();
    const details = screen.getByText('Run details').closest('details');
    expect(details).not.toHaveAttribute('open');
    const coverage = screen.getByRole('region', { name: 'Regional analysis summary' });
    expect(coverage.closest('details')).toBeNull();
    expect(within(coverage).getByText('1 km cells')).toBeVisible();
    expect(within(coverage).getByText('Regions up to 20 km per projected axis')).toBeVisible();
    expect(coverage).toHaveTextContent('Partial coverage: 2 of 690 shortlisted search windows analyzed');
    expect(coverage).toHaveTextContent('5,000 km² evaluated');
    expect(coverage).toHaveTextContent('Other shortlisted areas were not analyzed at this resolution');
  });

  it('reads resolution and region extent from loaded regional metadata', () => {
    summary({ analysis: { ...analysis, cellSizeM: 2500, maximumRegionExtentKm: 12.5 } });
    const coverage = screen.getByRole('region', { name: 'Regional analysis summary' });
    expect(within(coverage).getByText('2.5 km cells')).toBeVisible();
    expect(within(coverage).getByText('Regions up to 12.5 km per projected axis')).toBeVisible();
    expect(within(coverage).queryByText('1 km cells')).not.toBeInTheDocument();
    expect(within(coverage).queryByText('Regions up to 20 km per projected axis')).not.toBeInTheDocument();
    expect(screen.queryByText(/cells at 50 km/)).not.toBeInTheDocument();
  });

  it('keeps a saved national overview at its actual coarse resolution and scope', () => {
    const scope = '3,384 analyzed cells (CONUS national discovery)';
    summary({ analysis: null, analyzedCellCount: 3384, analysisResolutionM: 50000, scope });
    const coverage = screen.getByText(/3,384 cells at 50 km/);
    expect(coverage).toBeVisible(); expect(coverage.closest('details')).toBeNull();
    const visibleScope = screen.getAllByText(scope).find(node => node.closest('details') === null);
    expect(visibleScope).toBeVisible();
    expect(screen.queryByRole('region', { name: 'Regional analysis summary' })).not.toBeInTheDocument();
    expect(screen.queryByText('1 km cells')).not.toBeInTheDocument();
    expect(screen.queryByText('Regions up to 20 km per projected axis')).not.toBeInTheDocument();
  });

  it('keeps unknown regional metadata unknown rather than supplying standard limits', () => {
    summary({ analysis: { ...analysis, cellSizeM: null, maximumRegionExtentKm: null } });
    const coverage = screen.getByRole('region', { name: 'Regional analysis summary' });
    expect(within(coverage).getByText('Cell size not reported')).toBeVisible();
    expect(within(coverage).getByText('Region extent limit not reported')).toBeVisible();
    expect(screen.queryByText(/cells at 50 km/)).not.toBeInTheDocument();
    expect(within(coverage).queryByText('1 km cells')).not.toBeInTheDocument();
    expect(within(coverage).queryByText('Regions up to 20 km per projected axis')).not.toBeInTheDocument();
  });

  it('retains detailed national lineage and its explicit load action', () => {
    const onLoadParent = vi.fn();
    render(<AnalysisCoverage analysis={analysis} onLoadParent={onLoadParent} />);
    fireEvent.click(screen.getByText('National discovery lineage'));
    expect(screen.getByText(/Parent run: PARENT_FIXTURE/)).toBeVisible();
    fireEvent.click(screen.getByRole('button', { name: 'Load national discovery' }));
    expect(onLoadParent).toHaveBeenCalledTimes(1);
  });
});
