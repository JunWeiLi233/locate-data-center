import { describe, expect, it } from 'vitest';
import { parseCapabilities, parseRunResult } from './regions';
import { demoCapabilities, demoRun } from '../mocks/data';

describe('additive cached Grid contract', () => {
  it('parses advertised modes/default and verified cohort lineage without changing the facility', () => {
    const value = parseCapabilities({ ...demoCapabilities, schema_version: '1.8.0', default_analysis_mode: 'cached_regional', cached_regional_baseline_run_id: 'BASELINE', analysis_modes: [
      { id: 'cached_regional', label: 'Cached nationwide regional evaluation', available: true, reason: null },
      { id: 'full_rediscovery', label: 'Full nationwide rediscovery', available: true, reason: null },
    ] });
    expect(value.defaultAnalysisMode).toBe('cached_regional'); expect(value.cachedRegionalBaselineRunId).toBe('BASELINE');
    expect(value.analysisModes?.map(mode => mode.id)).toEqual(['cached_regional', 'full_rediscovery']);
    expect(value.defaultConfiguration).toEqual(parseCapabilities(demoCapabilities).defaultConfiguration);
  });
  it('accepts actual cached cohort analysis and preserves unassessed diagnostics', () => {
    const value = parseRunResult({ ...demoRun(), schema_version: '1.8.0', analysis_mode: 'cached_regional', analysis: {
      analysis_level: 'regional', selection: 'fixed_cached_cohort', cell_size_m: 1000, maximum_region_extent_km: 20,
      refined_cells: 152500, refined_parent_cells: 61, diagnostics_status: 'NOT_ASSESSED', coverage_warning: 'Fixed cached cohort; no nationwide rediscovery.',
    } });
    expect(value.analysisMode).toBe('cached_regional');
    expect(value.analysis).toMatchObject({ selection: 'fixed_cached_cohort', diagnosticsStatus: 'NOT_ASSESSED', refinedCells: 152500, cellSizeM: 1000, maximumRegionExtentKm: 20 });
    expect(value.configuration).toEqual(parseRunResult(demoRun()).configuration);
  });
  it('keeps legacy responses mode-free and rejects unknown requested mode contracts', () => {
    expect(parseCapabilities(demoCapabilities).analysisModes ?? []).toEqual([]);
    expect(parseRunResult(demoRun()).analysisMode ?? null).toBeNull();
    expect(() => parseRunResult({ ...demoRun(), analysis_mode: 'invented_fast_mode' })).toThrow(/analysis mode/);
  });
});
