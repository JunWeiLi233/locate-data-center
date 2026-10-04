import { useEffect, useRef, useState } from 'react';
import { locatorApi, type LocatorApi } from '../api/client';
import type { CountyBoundaryYear, LayerData, LayerSelection, RunResult } from '../types/domain';

export function useLayers(result: RunResult | null, selections: LayerSelection[], selectedRegionId: string | null = null, boundaryYear: CountyBoundaryYear = 2025, api: LocatorApi = locatorApi) {
  const [layers, setLayers] = useState<LayerData[]>([]);
  const [errors, setErrors] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);
  const cache = useRef(new Map<string, LayerData>());
  useEffect(() => {
    if (!result) { setLayers([]); setErrors([]); setLoading(false); return; }
    const controller = new AbortController(); let active = true;
    const regional = result.analysis?.analysisLevel === 'regional';
    const validWindow = !!selectedRegionId && result.regions.some(region => region.id === selectedRegionId);
    const requested = selections.filter(layer => layer.enabled && layer.id !== 'candidates' && layer.id !== 'community_economic' && (!regional || validWindow));
    const sublayerFor = (layer: LayerSelection) => regional ? `${layer.sublayer ?? ''}@${selectedRegionId}` : layer.sublayer;
    const keyFor = (layer: LayerSelection) => `${result.runId}/${result.scenarioId}/${layer.id}/${sublayerFor(layer) ?? ''}`;
    setLayers(requested.flatMap(layer => { const value = cache.current.get(keyFor(layer)); return value ? [value] : []; }));
    setLoading(requested.some(layer => !cache.current.has(keyFor(layer)))); setErrors([]);
    Promise.all(requested.map(async layer => {
      const key = keyFor(layer);
      try {
        const value = cache.current.get(key) ?? await api.layer(layer.id, result.runId, result.scenarioId, sublayerFor(layer), controller.signal);
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
  }, [result, selections, selectedRegionId, boundaryYear, api]);
  // Render before effects is also filter-only, including stale cached overlay data.
  const visibleLayers = layers.filter(layer => layer.id !== 'community_economic');
  return { layers: visibleLayers, errors, loading };
}
