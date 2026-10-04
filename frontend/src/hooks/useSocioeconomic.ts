import { useEffect, useRef, useState } from 'react';
import { locatorApi, type LocatorApi } from '../api/client';
import type { CountyBoundaryYear, SocioeconomicContext } from '../types/domain';

export function useSocioeconomic(runId: string | null, boundaryYear: CountyBoundaryYear, scenarioId: string, enabled: boolean, api: LocatorApi = locatorApi) {
  const [context, setContext] = useState<SocioeconomicContext | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const cache = useRef(new Map<string, SocioeconomicContext>());
  useEffect(() => {
    if (!runId || !enabled) { setContext(null); setLoading(false); setError(null); return; }
    const key = `${runId}/${scenarioId}/${boundaryYear}`;
    const cached = cache.current.get(key);
    setContext(cached ?? null); setError(null); setLoading(!cached);
    if (cached) return;
    const controller = new AbortController(); let active = true;
    api.socioeconomic(runId, boundaryYear, scenarioId, controller.signal).then(value => {
      if (!active) return;
      if (value.runId !== runId || value.boundaryYear !== boundaryYear || value.scenarioId !== scenarioId) throw new Error('County evidence does not match this run, scenario and boundary vintage.');
      cache.current.set(key, value); while (cache.current.size > 8) cache.current.delete(cache.current.keys().next().value!);
      setContext(value); setLoading(false);
    }).catch(cause => {
      if (!active || controller.signal.aborted) return;
      setContext(null); setError(cause instanceof Error ? cause.message : 'County economic evidence is unavailable.'); setLoading(false);
    });
    return () => { active = false; controller.abort(); };
  }, [runId, boundaryYear, scenarioId, enabled, api]);
  // On a vintage/run/scenario switch, never expose the prior crosswalk even for one render.
  return { context: context?.runId === runId && context.boundaryYear === boundaryYear && context.scenarioId === scenarioId && enabled ? context : null, loading, error };
}
