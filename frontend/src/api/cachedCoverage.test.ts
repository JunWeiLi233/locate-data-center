import { describe, expect, it } from 'vitest';
import { parseCapabilities } from './regions';
import { demoCapabilities } from '../mocks/data';

const window = { type: 'Feature', properties: { grid_id: 'g50000m-r0007-c0008' },
  geometry: { type: 'Polygon', coordinates: [[[-124.1, 47.2], [-123.4, 47.2], [-123.4, 47.75], [-124.1, 47.75], [-124.1, 47.2]]] } };
const wire = (coverage: unknown) => parseCapabilities({ ...demoCapabilities, schema_version: '1.8.0', cached_regional_coverage: coverage });

describe('cached cohort coverage contract', () => {
  it('reads window outlines and counts; missing counts stay unknown', () => {
    const value = wire({ run_id: 'BASELINE', window_size_m: 50000, cell_size_m: 1000, refined_windows: 1, refined_cells: null,
      shortlisted_windows: 690, windows: { type: 'FeatureCollection', features: [window] } }).cachedRegionalCoverage;
    expect(value).toMatchObject({ runId: 'BASELINE', windowSizeM: 50000, cellSizeM: 1000, refinedWindows: 1, refinedCells: null, shortlistedWindows: 690 });
    expect(value?.windows.features).toHaveLength(1);
  });
  it('hides the preview instead of failing the page when outlines are absent or malformed', () => {
    expect(parseCapabilities(demoCapabilities).cachedRegionalCoverage).toBeNull();
    expect(wire(null).cachedRegionalCoverage).toBeNull();
    expect(wire({ windows: { type: 'FeatureCollection', features: [] } }).cachedRegionalCoverage).toBeNull();
    expect(wire({ windows: { type: 'FeatureCollection', features: [{ ...window, geometry: { type: 'Point', coordinates: [-124, 47] } }] } }).cachedRegionalCoverage).toBeNull();
    expect(wire({ windows: { type: 'FeatureCollection', features: [{ ...window, geometry: { type: 'Polygon', coordinates: [[[-124, 47], [-123, 47]]] } }] } }).cachedRegionalCoverage).toBeNull();
  });
});
