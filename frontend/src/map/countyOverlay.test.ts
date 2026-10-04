import { describe, expect, it, vi } from 'vitest';
import type { Map as LibreMap } from 'maplibre-gl';
import { parseLayer } from '../api/regions';
import { demoLayer } from '../mocks/data';
import { indicatorLayerIds, selectedLayerIds } from './mapData';
import { syncIndicators } from './mapStyle';

describe('county map overlay retirement', () => {
  it('excludes county selections and removes stale county geometry while retaining technical indicators', () => {
    const county = { ...parseLayer(demoLayer('water')), id: 'community_economic' as const };
    const water = parseLayer(demoLayer('water'));
    const sourceIds = new Set(['indicator-source-community_economic']);
    const layerIds = new Set(indicatorLayerIds('community_economic'));
    const operations = {
      getStyle: () => ({ sources: Object.fromEntries([...sourceIds].map(id => [id, {}])) }),
      getSource: (id: string) => sourceIds.has(id) ? { setData: vi.fn() } : undefined,
      getLayer: (id: string) => layerIds.has(id),
      addSource: vi.fn((id: string) => sourceIds.add(id)),
      addLayer: vi.fn((layer: { id: string }) => layerIds.add(layer.id)),
      removeSource: vi.fn((id: string) => sourceIds.delete(id)),
      removeLayer: vi.fn((id: string) => layerIds.delete(id)),
      setLayoutProperty: vi.fn(), setPaintProperty: vi.fn(),
    };
    const enabled = selectedLayerIds([{ id: 'water', enabled: true }, { id: 'community_economic', enabled: true }]);
    expect(enabled.has('community_economic')).toBe(false);
    syncIndicators(operations as unknown as LibreMap, [county, water], new Set(['water', 'community_economic']));
    expect(sourceIds.has('indicator-source-community_economic')).toBe(false);
    expect([...layerIds].some(id => id.includes('community_economic'))).toBe(false);
    expect(operations.addSource).not.toHaveBeenCalledWith('indicator-source-community_economic', expect.anything());
    expect(sourceIds.has('indicator-source-water')).toBe(true);
  });
});
