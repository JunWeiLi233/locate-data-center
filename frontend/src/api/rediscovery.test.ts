/** Wire-format parsing of the read-only rediscovery API, using the labeled synthetic fixture. */
import { describe, expect, it } from 'vitest';
import { parseRediscovery, parseRediscoveryIndex, RediscoveryError } from './rediscovery';
import { syntheticRediscoveryIndex, syntheticRediscoveryPayload } from '../mocks/rediscovery';

describe('rediscovery adapter', () => {
  it('renames backend fields without recomputing values', () => {
    const result = parseRediscovery(syntheticRediscoveryPayload());
    expect(result.analysisName).toBe('DEMO_SYNTHETIC_FIXTURE');
    expect(result.candidates.map(item => item.rank)).toEqual([1, 2, 3, 4]);
    const second = result.candidates[1];
    expect(second.classification).toBe('validated');
    expect(second.distanceKm).toBe(12);
    expect(second.robustness).toMatchObject({ score: 100, spatialSupport: 'county', provider: 'county_monte_carlo' });
    expect(result.candidates[0].robustness).toMatchObject({ score: null, missingReason: 'Synthetic: county not in cohort' });
    expect(second.factors.reduce((sum, item) => sum + (item.contribution ?? 0), 0)).toBeCloseTo(25 + 22.5 + 20 + 8.75 + 12.5, 6);
    expect(result.hitRates.find(row => row.topN === 2 && row.radiusKm === 25)?.hitRate).toBe(0.5);
    expect(result.baselines).toHaveLength(8);
    expect(result.presence.auc).toBe(0.71);
    expect(result.presenceByCase).toEqual({ weight_land_focus: 0.7 });
    expect(result.hubs[0].nearestCandidateKm).toEqual({ '2': 12, '4': 12 });
    expect(result.classificationCounts['4']).toEqual({ validated: 1, unresolved: 1, emerging: 2 });
    expect(result.surface?.url).toBe('/api/rediscovery/demo_fixture/surface.png');
    expect(result.surface?.coordinates).toHaveLength(4);
    expect(result.facilities[1].name).toBeNull();
  });

  it('rejects other schema versions, unknown classes and out-of-order ranks', () => {
    expect(() => parseRediscovery({ ...syntheticRediscoveryPayload(), schema_version: '2.0.0' })).toThrow(RediscoveryError);
    const badClass = syntheticRediscoveryPayload();
    (badClass.candidates[0] as { classification: string }).classification = 'great';
    expect(() => parseRediscovery(badClass)).toThrow(/classification/);
    const reordered = syntheticRediscoveryPayload();
    reordered.candidates.reverse();
    expect(() => parseRediscovery(reordered)).toThrow(/rank order/);
    const missing = syntheticRediscoveryPayload() as Record<string, unknown>;
    delete missing.results;
    expect(() => parseRediscovery(missing)).toThrow(/results/);
  });

  it('parses the analysis index', () => {
    const index = parseRediscoveryIndex(syntheticRediscoveryIndex);
    expect(index.defaultAnalysisId).toBe('demo_fixture');
    expect(index.analyses[0]).toMatchObject({ analysisId: 'demo_fixture', available: true, candidates: 4 });
    expect(() => parseRediscoveryIndex({ analyses: [] })).toThrow(RediscoveryError);
  });
});
