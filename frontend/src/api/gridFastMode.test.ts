import { afterEach, describe, expect, it, vi } from 'vitest';
import { realApi } from './client';
import { serializeConfiguration } from './regions';
import { DEMO_CONFIG, demoRun } from '../mocks/data';

afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals(); });
describe('Grid evaluation mode transport', () => {
  it.each(['cached_regional', 'full_rediscovery'] as const)('submits %s alongside the exact changed facility/preferences, then polls the recomputation job', async mode => {
    const configuration = { ...DEMO_CONFIG, peakItPowerMw: 140, weighting: 'user' as const, groupWeights: { energy_carbon: 3, water_stewardship: 1 } };
    const fetch = vi.fn()
      .mockResolvedValueOnce(new Response(JSON.stringify({ job_id: 'RECOMPUTE' }), { status: 202 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ id: 'RECOMPUTE', state: 'COMPLETE', run_id: 'RECOMPUTED' }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ ...demoRun(configuration), run_id: 'RECOMPUTED', analysis_mode: mode }), { status: 200 }));
    vi.stubGlobal('fetch', fetch);
    const result = await realApi.search(configuration, undefined, undefined, mode);
    expect(fetch.mock.calls[0][0]).toBe('/api/search');
    expect(JSON.parse(fetch.mock.calls[0][1].body)).toEqual({ facility: serializeConfiguration(configuration), analysis_mode: mode });
    expect(fetch.mock.calls[1][0]).toBe('/api/jobs/RECOMPUTE');
    expect(fetch.mock.calls[2][0]).toBe('/api/runs/RECOMPUTED?scenario=current');
    expect(result.runId).toBe('RECOMPUTED'); expect(result.configuration.peakItPowerMw).toBe(140); expect(result.analysisMode).toBe(mode);
  });
  it('leaves legacy mode unspecified without adding request metadata', async () => {
    const fetch = vi.fn()
      .mockResolvedValueOnce(new Response(JSON.stringify({ job_id: 'LEGACY' }), { status: 202 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ id: 'LEGACY', state: 'COMPLETE', run_id: 'LEGACY' }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify(demoRun()), { status: 200 }));
    vi.stubGlobal('fetch', fetch); await realApi.search(DEMO_CONFIG);
    expect(JSON.parse(fetch.mock.calls[0][1].body)).toEqual({ facility: serializeConfiguration(DEMO_CONFIG) });
  });
});
