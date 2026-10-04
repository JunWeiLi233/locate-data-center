import { render, screen, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { parseRunResult } from '../api/regions';
import { demoRun } from '../mocks/data';
import { AnalysisCoverage } from './AnalysisCoverage';
import { RunSummary } from './RunSummary';

const coverage = {
  analysis_level: 'regional', parent_run_id: 'TRANSPORT_PARENT', parent_run_path: 'runs/transport_parent',
  grid_definition_id: 'TRANSPORT_GRID', cell_size_m: 1000, maximum_region_extent_km: 20,
  refined_cells: 42, refined_parent_cells: 1, refined_area_km2: 42, national_cells: 3384,
  shortlisted_parent_cells: 690, shortlisted_parent_area_km2: 1725000,
  ranking_universe: 'all_evaluated_refined_alternatives', selection: 'national_fine_surface',
  coverage_warning: 'The surface applies no screening; unselected parents are unrefined.',
  national_fine_surface: {
    screening_status: 'UNSCREENED', valued_cells: 10000, scored_alternatives: 18000,
    alternatives: 20000, unscored_alternatives: 2000, ranked_parent_windows: 10, selection_limit: 1,
    stage_identity: 'TRANSPORT_STAGE', manifest: 'national_fine_surface/fine_surface_manifest.json',
    manifest_sha256: 'TRANSPORT_HASH', method_versions: { features: 'fixture', selection: 'fixture' },
    facility_score: 100, best_fine_score: 100,
  },
};
const result = () => parseRunResult({ ...demoRun(), schema_version: '1.5.0', analyzed_cell_count: 42, analysis: coverage });

describe('national fine surface coverage', () => {
  it('parses unscreened valuation separately while preserving the evaluated alternatives', () => {
    const actual = result();
    expect(actual.analyzedCellCount).toBe(42);
    expect(actual.analysis?.selection).toBe('national_fine_surface');
    expect(actual.analysis?.coverageWarning).toBe(coverage.coverage_warning);
    expect(actual.analysis?.nationalFineSurface).toMatchObject({ screeningStatus: 'UNSCREENED', valuedCells: 10000, unscoredAlternatives: 2000 });
    expect(actual.analysis?.nationalFineSurface).not.toHaveProperty('facilityScore');
    expect(actual.analysis?.nationalFineSurface).not.toHaveProperty('bestFineScore');
    expect(actual.regions).toEqual(parseRunResult(demoRun()).regions);
  });

  it('keeps the actual 1 km and 20 km bounds visible with separate unscreened and refined counts', () => {
    render(<RunSummary result={result()} groups={[]} />);
    const compact = screen.getByRole('region', { name: 'Regional analysis summary' });
    expect(compact.closest('details')).toBeNull();
    expect(within(compact).getByText('1 km cells')).toBeVisible();
    expect(within(compact).getByText('Regions up to 20 km per projected axis')).toBeVisible();
    expect(compact).toHaveTextContent('10,000 national 1 km cells pre-scored · UNSCREENED');
    expect(compact).toHaveTextContent('42 cells screened and evaluated');
    expect(compact).toHaveTextContent('1 of 10 ranked search windows');
    expect(compact).not.toHaveTextContent('of 690 shortlisted');
  });

  it('discloses native partial coverage and keeps refined ranking distinct from the surface', () => {
    render(<AnalysisCoverage analysis={result().analysis!} />);
    const details = screen.getByRole('region', { name: 'Regional analysis coverage' });
    expect(details).toHaveTextContent(coverage.coverage_warning);
    expect(details).toHaveTextContent('18,000 scored alternatives');
    expect(details).toHaveTextContent('2,000 without a complete value');
    expect(details).toHaveTextContent('Ranks compare all evaluated refined alternatives');
    expect(details).not.toHaveTextContent('of 690 shortlisted search windows');
  });

  it('keeps absent surface counts unknown and rejects a misleading screened surface status', () => {
    const partial = parseRunResult({ ...demoRun(), analysis: { ...coverage, national_fine_surface: { ...coverage.national_fine_surface, valued_cells: null } } });
    render(<AnalysisCoverage analysis={partial.analysis!} compact />);
    expect(screen.getByRole('region', { name: 'Regional analysis summary' })).toHaveTextContent('not reported national 1 km cells pre-scored');
    expect(() => parseRunResult({ ...demoRun(), analysis: { ...coverage, national_fine_surface: { ...coverage.national_fine_surface, screening_status: 'PASS' } } })).toThrow('UNSCREENED');
  });

  it('keeps the old regional analysis shape readable without a surface', () => {
    const { selection, coverage_warning, national_fine_surface, ...legacy } = coverage;
    const old = parseRunResult({ ...demoRun(), schema_version: '1.4.0', analysis: legacy });
    expect(old.analysis?.cellSizeM).toBe(1000);
    expect(old.analysis?.nationalFineSurface).toBeNull();
    expect(old.regions).toEqual(parseRunResult(demoRun()).regions);
    render(<RunSummary result={old} groups={[]} />);
    const compact = screen.getByRole('region', { name: 'Regional analysis summary' });
    expect(within(compact).getByText('1 km cells')).toBeVisible();
    expect(within(compact).getByText('Regions up to 20 km per projected axis')).toBeVisible();
    expect(compact).toHaveTextContent('of 690 shortlisted search windows analyzed');
    expect(compact).not.toHaveTextContent('UNSCREENED');
  });

  it('describes the per-region fine selection without a global parent ranking', () => {
    const regionMode = parseRunResult({ ...demoRun(), schema_version: '1.5.0', analyzed_cell_count: 42,
      analysis: { ...coverage, selection: 'national_fine_region_parents', refined_parent_cells: 61 } });
    expect(regionMode.analysis?.selection).toBe('national_fine_region_parents');
    expect(regionMode.analysis?.nationalFineSurface).toMatchObject({ screeningStatus: 'UNSCREENED', valuedCells: 10000 });
    render(<AnalysisCoverage analysis={regionMode.analysis!} compact />);
    const compact = screen.getByRole('region', { name: 'Regional analysis summary' });
    expect(compact).toHaveTextContent('61 search windows, the best window of each national region');
    expect(compact).not.toHaveTextContent('ranked search windows');
    expect(() => parseRunResult({ ...demoRun(), analysis: { ...coverage, selection: 'nearest_city' } })).toThrow('Unsupported regional parent selection');
  });
});
