import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { parseRunResult } from '../api/regions';
import { demoRun } from '../mocks/data';
import { groupPlaces } from '../utils/regions';
import { RunSummary } from './RunSummary';
import { MapCoverage } from './MapCoverage';
import type { RunResult } from '../types/domain';

const result = { ...parseRunResult(demoRun()), analysisMode: 'cached_regional', analysis: {
  analysisLevel: 'regional', selection: 'fixed_cached_cohort', cellSizeM: 1000, maximumRegionExtentKm: 20,
  refinedCells: 152500, refinedParentCells: 61, diagnosticsStatus: 'NOT_ASSESSED', coverageWarning: 'Fixed cached cohort; no nationwide rediscovery.',
  parentRunId: 'PARENT', parentRunPath: 'runs/parent', gridDefinitionId: 'DEMO_GRID', nationalCells: 3384, shortlistedParentCells: 690,
  refinedAreaKm2: 152500, shortlistedParentAreaKm2: 1725000, rankingUniverse: 'all_evaluated_cached_alternatives',
} } as RunResult;
describe('actual fast Grid result scope', () => {
  it('labels evaluated cached results as a fixed nationwide cohort with actual 1 km/20 km limits and unassessed diagnostics', () => {
    render(<RunSummary result={result} groups={groupPlaces(result.regions)} />);
    const summary = screen.getByRole('region', { name: 'Regional analysis summary' });
    expect(summary).toHaveTextContent('Cached nationwide regions');
    expect(summary).toHaveTextContent('1 km cells'); expect(summary).toHaveTextContent('Regions up to 20 km per projected axis');
    expect(summary).toHaveTextContent('152,500 cells'); expect(summary).toHaveTextContent('61 cached search windows');
    expect(summary).toHaveTextContent('no new nationwide search');
    fireEvent.click(screen.getByText('Run details'));
    expect(screen.getByRole('region', { name: 'Regional analysis coverage' })).toHaveTextContent('not assessed');
  });
  it('labels map scope as cached reevaluation without claiming new refinement or complete CONUS discovery', () => {
    render(<MapCoverage result={result} shownAreas={2} totalAreas={2} />);
    const coverage = screen.getByRole('region', { name: 'Map analysis coverage' });
    expect(coverage).toHaveTextContent('Cached nationwide regions'); expect(coverage).toHaveTextContent('Fixed coverage');
    expect(coverage).toHaveTextContent('61 cached search windows'); expect(coverage).toHaveTextContent('152,500 cells evaluated');
    expect(coverage).not.toHaveTextContent('parent cells refined');
  });
});
