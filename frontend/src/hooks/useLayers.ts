import { useEffect, useRef, useState } from 'react';
import { locatorApi } from '../api/client';
import type { LayerData, LayerSelection, RunResult } from '../types/domain';

export function useLayers(result: RunResult | null, selections: LayerSelection[]) {
  const [layers, setLayers] = useState<LayerData[]>([]);
  const [errors, setErrors] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);
  const cache = useRef(new Map<string, LayerData>());
  useEffect(() => {
    if (!result) { setLayers([]); setErrors([]); setLoading(false); return; }
    const controller = new AbortController(); let active = true;
    const requested = selections.filter(layer => layer.enabled && layer.id !== 'candidates');
    const keyFor = (layer: LayerSelection) => `${result.runId}/${result.scenarioId}/${layer.id}/${layer.sublayer ?? ''}`;
    setLayers(requested.flatMap(layer => { const value = cache.current.get(keyFor(layer)); return value ? [value] : []; }));
    setLoading(requested.some(layer => !cache.current.has(keyFor(layer)))); setErrors([]);
    Promise.all(requested.map(async layer => {
      const key = keyFor(layer);
      try {
        const value = cache.current.get(key) ?? await locatorApi.layer(layer.id, result.runId, result.scenarioId, layer.sublayer, controller.signal);
        if (active) { cache.current.delete(key); cache.current.set(key, value); while (cache.current.size > 48) cache.current.delete(cache.current.keys().next().value!); }
        return { value, error: null };
      } catch (cause) {
        return { value: null, error: cause instanceof Error ? cause.message : `Unable to load ${layer.id}.` };
      }
    })).then(values => {
      if (!active) return;
      setLayers(values.flatMap(value => value.value ? [value.value] : []));
      setErrors(values.flatMap(value => value.error ? [value.error] : [])); setLoading(false);
    });
    return () => { active = false; controller.abort(); };
  }, [result, selections]);
  return { layers, errors, loading };
}
