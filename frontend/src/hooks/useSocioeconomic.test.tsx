import { renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { useSocioeconomic } from './useSocioeconomic';
import { parseSocioeconomic } from '../api/regions';
import { demoCountyEconomic, demoSocioeconomic } from '../mocks/socioeconomic';

const api = vi.hoisted(() => ({ socioeconomic: vi.fn() }));
vi.mock('../api/client', () => ({ locatorApi: api }));
function context(scenario: string) { return { ...parseSocioeconomic(demoSocioeconomic({ [scenario === 'current' ? 'DEMO_BASELINE' : 'DEMO_FUTURE']: [demoCountyEconomic()] })), scenarioId: scenario }; }
beforeEach(() => vi.clearAllMocks());
describe('county context scenario identity', () => {
  it('loads and caches each exact scenario crosswalk without exposing baseline counties on a future switch', async () => {
    api.socioeconomic.mockResolvedValueOnce(context('current')).mockResolvedValueOnce(context('bau_2050'));
    const exposures: ReturnType<typeof useSocioeconomic>['context'][] = [];
    const view = renderHook(({ scenario }) => { const result = useSocioeconomic('DEMO_RUN', 2025, scenario, true); exposures.push(result.context); return result; }, { initialProps: { scenario: 'current' } });
    await waitFor(() => expect(view.result.current.context?.regionCounties.DEMO_BASELINE).toHaveLength(1));
    exposures.length = 0; view.rerender({ scenario: 'bau_2050' });
    expect(exposures[0]).toBeNull();
    await waitFor(() => expect(view.result.current.context?.regionCounties.DEMO_FUTURE).toHaveLength(1));
    expect(view.result.current.context?.regionCounties.DEMO_BASELINE).toBeUndefined();
    expect(api.socioeconomic).toHaveBeenLastCalledWith('DEMO_RUN', 2025, 'bau_2050', expect.any(AbortSignal));
    view.rerender({ scenario: 'current' });
    await waitFor(() => expect(view.result.current.context?.regionCounties.DEMO_BASELINE).toHaveLength(1));
    expect(api.socioeconomic).toHaveBeenCalledTimes(2);
  });
  it('rejects a county response for the wrong external scenario rather than silently filtering against baseline', async () => {
    api.socioeconomic.mockResolvedValue(context('current'));
    const view = renderHook(() => useSocioeconomic('DEMO_RUN', 2025, 'bau_2050', true));
    await waitFor(() => expect(view.result.current.loading).toBe(false));
    expect(view.result.current.context).toBeNull(); expect(view.result.current.error).toMatch(/scenario/);
  });
});
