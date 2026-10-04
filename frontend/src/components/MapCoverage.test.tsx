import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { parseRunResult } from '../api/regions';
import { demoRun } from '../mocks/data';
import { MapCoverage } from './MapCoverage';

function result(selection = 'national_fine_surface') {
  return parseRunResult({ ...demoRun(), analysis: {
    analysis_level: 'regional', selection, cell_size_m: 1000, maximum_region_extent_km: 20,
    refined_cells: 152500, refined_parent_cells: 61, shortlisted_parent_cells: 690,
    parent_run_id: 'PARENT', national_fine_surface: selection === 'representative_parent_cells' ? null : {
      screening_status: 'UNSCREENED', valued_cells: 8460000, ranked_parent_windows: 400, selection_limit: 61,
    },
  } });
}
describe('map-visible saved analysis coverage', () => {
  it('states unique filtered/saved counts and the limited global fine-window selection', () => {
    const nationwide = vi.fn(), parent = vi.fn();
    render(<MapCoverage result={result()} shownAreas={2} totalAreas={3} onLoadNationwide={nationwide} onLoadParent={parent} />);
    const coverage = screen.getByRole('region', { name: 'Map analysis coverage' });
    expect(coverage).toHaveTextContent('2 of 3 saved search areas match filters');
    expect(coverage).toHaveTextContent('1 km cells · regions up to 20 km per projected axis');
    expect(coverage).toHaveTextContent('61 of 400 ranked search windows analyzed · 152,500 cells evaluated');
    const context = screen.getByText('Coverage context').closest('details');
    expect(context).not.toHaveAttribute('open');
    fireEvent.click(screen.getByText('Coverage context'));
    expect(coverage).toHaveTextContent('Global top-window selection can concentrate areas');
    expect(coverage).toHaveTextContent('UNSCREENED'); expect(coverage).toHaveTextContent('not an inventory of existing data centers');
    expect(coverage.closest('details')).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: 'Show nationwide areas · 1 km' })); expect(nationwide).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByRole('button', { name: 'Load national discovery' })); expect(parent).toHaveBeenCalledTimes(1);
  });
  it.each([['representative_parent_cells', 'Nationwide regional representatives'],
    ['national_fine_region_parents', 'Best search window per national region']])('distinguishes nationwide selection %s and partial evaluation', (selection, label) => {
    render(<MapCoverage result={result(selection)} shownAreas={3} totalAreas={3} />);
    const coverage = screen.getByRole('region', { name: 'Map analysis coverage' });
    expect(coverage).toHaveTextContent(label);
    expect(coverage).toHaveTextContent('Partial coverage');
    expect(coverage).not.toHaveTextContent('Global top-window selection');
    expect(screen.queryByRole('button', { name: 'Show nationwide areas · 1 km' })).not.toBeInTheDocument();
  });
  it('retains unknown metadata and actual coarse national resolution', () => {
    render(<MapCoverage result={{ ...result(), analysis: null, analysisResolutionM: 50000 }} shownAreas={3} totalAreas={3} />);
    const coverage = screen.getByRole('region', { name: 'Map analysis coverage' });
    expect(coverage).toHaveTextContent('50 km cells'); expect(coverage).not.toHaveTextContent('1 km cells');
    expect(coverage).not.toHaveTextContent('regions up to 20 km');
  });
});
