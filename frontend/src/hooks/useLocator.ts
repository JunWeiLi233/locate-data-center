import { useCallback, useEffect, useRef, useState } from 'react';
import { locatorApi, type LocatorApi } from '../api/client';
import type { FacilityConfiguration, GridAnalysisMode, Job, RunResult, SearchState } from '../types/domain';

/** Whether the displayed run came from this session's search or from loading a completed run. */
export type ResultOrigin = 'search' | 'saved';

export function useLocator(api: LocatorApi = locatorApi) {
  const [result, setResult] = useState<RunResult | null>(null);
  const [origin, setOrigin] = useState<ResultOrigin | null>(null);
  const [state, setState] = useState<SearchState>('IDLE');
  const [stage, setStage] = useState('');
  const [error, setError] = useState<string | null>(null);
  const generation = useRef(0);
  const request = useRef<AbortController | null>(null);
  const resultRunId = useRef<string | null>(null);
  const execute = useCallback(async (operation: (signal: AbortSignal, progress: (job: Job) => void) => Promise<RunResult>, kind: ResultOrigin, initialStage: string) => {
    request.current?.abort();
    const controller = new AbortController(); request.current = controller;
    const current = ++generation.current;
    setState('LOADING'); setError(null); setStage(initialStage);
    try {
      const value = await operation(controller.signal, job => {
        if (generation.current === current && !controller.signal.aborted) setStage(job.stage);
      });
      if (generation.current !== current || controller.signal.aborted) return null;
      // Reloading the same run for another scenario keeps the origin of that run.
      const sameRun = resultRunId.current === value.runId;
      resultRunId.current = value.runId;
      setOrigin(previous => kind === 'saved' && sameRun && previous ? previous : kind);
      setResult(value); setState(value.state); setStage('');
      return value;
    } catch (cause) {
      if (generation.current !== current || controller.signal.aborted) return null;
      setError(cause instanceof Error ? cause.message : 'The request could not be completed.');
      setState('ERROR'); setStage(''); return null;
    }
  }, []);
  const search = useCallback((configuration: FacilityConfiguration, analysisMode?: GridAnalysisMode) => execute((signal, progress) => analysisMode ? api.search(configuration, progress, signal, analysisMode) : api.search(configuration, progress, signal), 'search', 'Preparing request'), [execute, api]);
  const load = useCallback((runId: string, scenarioId = 'current') => execute(signal => api.run(runId, scenarioId, signal), 'saved', 'Loading saved results'), [execute, api]);
  useEffect(() => () => { request.current?.abort(); generation.current++; }, []);
  return { result, origin, state, stage, error, search, load };
}
