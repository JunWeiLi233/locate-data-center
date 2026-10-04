import { afterEach, describe, expect, it, vi } from 'vitest';
import { realApi } from './client';
import { demoSocioeconomic } from '../mocks/socioeconomic';
import type { CountyBoundaryYear, SocioeconomicContext } from '../types/domain';
function read(run: string, year: CountyBoundaryYear, scenario = 'current', signal?: AbortSignal) {
  expect(realApi).toHaveProperty('socioeconomic');
  return (realApi as typeof realApi & { socioeconomic: (run: string, year: CountyBoundaryYear, scenario: string, signal?: AbortSignal) => Promise<SocioeconomicContext> }).socioeconomic(run, year, scenario, signal);
}
afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals(); });
describe('county context transport', () => {
  it('blocks county choropleth requests even when a legacy caller asks directly', async () => {
    const fetch = vi.fn(); vi.stubGlobal('fetch', fetch);
    await expect(realApi.layer('community_economic', 'DEMO_RUN', 'current', 'poverty@2025')).rejects.toThrow(/filters/);
    expect(fetch).not.toHaveBeenCalled();
  });
  it('requests an exact run and boundary year without a facility search or scenario substitution', async () => {
    const fetch = vi.fn().mockResolvedValue(new Response(JSON.stringify(demoSocioeconomic({}, 2023)), { status: 200 })); vi.stubGlobal('fetch', fetch);
    const context = await read('DEMO_RUN', 2023);
    expect(fetch).toHaveBeenCalledTimes(1); expect(fetch.mock.calls[0][0]).toBe('/api/socioeconomic?run_id=DEMO_RUN&boundary_year=2023&scenario=current');
    expect(context.boundaryYear).toBe(2023); expect(context.socioeconomicYear).toBe(2024);
  });
  it('preserves cancellation and reports a missing legacy endpoint without synthetic fallback', async () => {
    const controller = new AbortController(); controller.abort();
    vi.stubGlobal('fetch', vi.fn((_url, options) => options.signal.aborted ? Promise.reject(new DOMException('Aborted', 'AbortError')) : Promise.resolve(new Response(JSON.stringify({ error: 'Endpoint not available' }), { status: 404 }))));
    await expect(read('LEGACY', 2025, 'current', controller.signal)).rejects.toMatchObject({ name: 'AbortError' });
    await expect(read('LEGACY', 2025)).rejects.toMatchObject({ status: 404 });
  });
  it('sends and retains an exact future scenario identity while leaving estimate vintage fixed', async () => {
    const fetch = vi.fn().mockResolvedValue(new Response(JSON.stringify({ ...demoSocioeconomic({}, 2025), scenario_id: 'bau_2050' }), { status: 200 })); vi.stubGlobal('fetch', fetch);
    const context = await read('DEMO_RUN', 2025, 'bau_2050');
    expect(fetch.mock.calls[0][0]).toBe('/api/socioeconomic?run_id=DEMO_RUN&boundary_year=2025&scenario=bau_2050');
    expect(context.scenarioId).toBe('bau_2050'); expect(context.socioeconomicYear).toBe(2024);
  });
});
