import { useEffect, useState } from 'react';
import { rediscoveryApi, type RediscoveryApi } from '../api/rediscovery';
import type { RediscoveryIndex, RediscoveryResult } from '../types/rediscovery';

export type RediscoveryState = 'LOADING' | 'READY' | 'EMPTY' | 'ERROR';

/** Load the index, then the requested (or default real) analysis; stale responses are aborted. */
export function useRediscovery(requestedId: string | null, attempt: number, api: RediscoveryApi = rediscoveryApi, enabled = true) {
  const [index, setIndex] = useState<RediscoveryIndex | null>(null);
  const [result, setResult] = useState<RediscoveryResult | null>(null);
  const [state, setState] = useState<RediscoveryState>('LOADING');
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    const controller = new AbortController();
    if (!enabled) { setResult(null); setState('EMPTY'); return () => controller.abort(); }
    setState('LOADING'); setError(null);
    (async () => {
      const value = await api.index(controller.signal);
      setIndex(value);
      const available = value.analyses.filter(item => item.available);
      const id = requestedId && available.some(item => item.analysisId === requestedId) ? requestedId : value.defaultAnalysisId;
      if (!id) { setResult(null); setState('EMPTY'); return; }
      const loaded = await api.result(id, controller.signal);
      setResult(loaded); setState('READY');
    })().catch(cause => {
      if (controller.signal.aborted) return;
      setError(cause instanceof Error ? cause.message : 'The rediscovery check could not load.');
      setState('ERROR');
    });
    return () => controller.abort();
  }, [requestedId, attempt, api, enabled]);
  return { index, result, state, error };
}
