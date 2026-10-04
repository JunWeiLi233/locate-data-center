import { act, renderHook } from '@testing-library/react';
import { beforeEach, expect, it, vi } from 'vitest';
import { useLocator } from './useLocator';
import { parseRunResult } from '../api/regions';
import { demoRun, DEMO_CONFIG } from '../mocks/data';
import type { RunResult } from '../types/domain';

const api = vi.hoisted(() => ({ search: vi.fn(), run: vi.fn() }));
vi.mock('../api/client', () => ({ locatorApi: api }));
function deferred() { let resolve!: (value: RunResult) => void; const promise = new Promise<RunResult>(yes => { resolve = yes; }); return { promise, resolve }; }
beforeEach(() => vi.clearAllMocks());

it('aborts superseded requests and ignores a response even if the transport ignores abort', async () => {
  const first = deferred(), second = deferred(); api.search.mockReturnValueOnce(first.promise).mockReturnValueOnce(second.promise);
  const { result } = renderHook(useLocator); let pendingFirst!: Promise<RunResult | null>, pendingSecond!: Promise<RunResult | null>;
  act(() => { pendingFirst = result.current.search(DEMO_CONFIG); }); const signal = api.search.mock.calls[0][2] as AbortSignal;
  act(() => { pendingSecond = result.current.search({ ...DEMO_CONFIG, peakItPowerMw: 150 }); }); expect(signal.aborted).toBe(true);
  const newest = parseRunResult(demoRun({ ...DEMO_CONFIG, peakItPowerMw: 150 })); newest.runId = 'LATEST';
  await act(async () => { second.resolve(newest); await pendingSecond; });
  await act(async () => { first.resolve(parseRunResult(demoRun())); await pendingFirst; });
  expect(result.current.result?.runId).toBe('LATEST'); expect(result.current.result?.configuration.peakItPowerMw).toBe(150);
});

it('reports whether the shown run was searched or loaded, keeping it across scenario reloads', async () => {
  const searched = parseRunResult(demoRun()); searched.runId = 'SEARCHED';
  const saved = parseRunResult(demoRun()); saved.runId = 'SAVED';
  api.search.mockResolvedValue(searched); api.run.mockImplementation((id: string) => Promise.resolve(id === 'SAVED' ? saved : searched));
  const { result } = renderHook(useLocator); expect(result.current.origin).toBeNull();
  await act(async () => { await result.current.load('SAVED'); }); expect(result.current.origin).toBe('saved');
  await act(async () => { await result.current.search(DEMO_CONFIG); }); expect(result.current.origin).toBe('search');
  await act(async () => { await result.current.load('SEARCHED', 'bau_2050'); }); expect(result.current.origin).toBe('search');
  await act(async () => { await result.current.load('SAVED'); }); expect(result.current.origin).toBe('saved');
});

it('aborts in-flight work on unmount without publishing an error', () => {
  const request = deferred(); api.run.mockReturnValue(request.promise); const { result, unmount } = renderHook(useLocator);
  act(() => { void result.current.load('REAL_RUN'); }); const signal = api.run.mock.calls[0][2] as AbortSignal; unmount(); expect(signal.aborted).toBe(true);
});
