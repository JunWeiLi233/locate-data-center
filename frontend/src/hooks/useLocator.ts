import { useCallback, useEffect, useRef, useState } from 'react';
import { locatorApi } from '../api/client';
import type { FacilityConfiguration, Job, RunResult, SearchState } from '../types/domain';

export function useLocator() {
  const [result, setResult] = useState<RunResult | null>(null);
  const [state, setState] = useState<SearchState>('IDLE');
  const [stage, setStage] = useState('');
  const [error, setError] = useState<string | null>(null);
  const generation = useRef(0);
  const request = useRef<AbortController | null>(null);
  const execute = useCallback(async (operation: (signal: AbortSignal, progress: (job: Job) => void) => Promise<RunResult>) => {
    request.current?.abort();
    const controller = new AbortController(); request.current = controller;
    const current = ++generation.current;
    setState('LOADING'); setError(null); setStage('Preparing request');
    try {
      const value = await operation(controller.signal, job => {
        if (generation.current === current && !controller.signal.aborted) setStage(job.stage);
      });
      if (generation.current !== current || controller.signal.aborted) return null;
      setResult(value); setState(value.state); setStage('');
      return value;
    } catch (cause) {
      if (generation.current !== current || controller.signal.aborted) return null;
      setError(cause instanceof Error ? cause.message : 'The request could not be completed.');
      setState('ERROR'); setStage(''); return null;
    }
  }, []);
  const search = useCallback((configuration: FacilityConfiguration) => execute((signal, progress) => locatorApi.search(configuration, progress, signal)), [execute]);
  const load = useCallback((runId: string, scenarioId = 'current') => execute(signal => locatorApi.run(runId, scenarioId, signal)), [execute]);
  useEffect(() => () => { request.current?.abort(); generation.current++; }, []);
  return { result, state, stage, error, search, load };
}
