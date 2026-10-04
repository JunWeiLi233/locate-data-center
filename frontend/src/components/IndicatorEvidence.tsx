import type { LayerData, MapFeatureInfo } from '../types/domain';

export function IndicatorEvidence({ layers, onInspect }: { layers: LayerData[]; onInspect: (feature: MapFeatureInfo) => void }) {
  const mapLayers = layers.filter(layer => layer.id !== 'community_economic');
  const grid = layers.find(layer => layer.id === 'grid');
  return <>
    {mapLayers.length > 0 && <section className="indicator-legends" aria-label="Selected indicator legends">{mapLayers.map(layer => <details key={layer.id}><summary>{layer.label}</summary>
      <p>{layer.unit || 'Categorical screening status'} · {layer.direction === 'higher_is_worse' ? 'Higher raw values indicate greater burden / risk' : layer.direction === 'higher_is_better' ? 'Higher values are favorable' : layer.direction === 'categorical' ? 'Categories are not numeric scores' : 'Raw context; no favorable direction assigned'}</p>
      {layer.min !== null && layer.max !== null && <><div className="legend-gradient" /><div className="legend-range"><span>{layer.min} {layer.unit}</span><span>{layer.max} {layer.unit}</span></div></>}
      <p className="legend-status">{layer.direction === 'categorical' ? 'PASS · teal / CONDITIONAL · amber / FAIL · red / UNKNOWN · gray.' : 'Known raw values · blue scale / missing values · gray. Source status remains observed, calculated, proxy or scenario in the inspector.'} Unknown is not zero.</p>
      <p>Source: {layer.source}</p>{layer.warning && <p>{layer.warning}</p>}
    </details>)}</section>}
    {grid && <details className="cell-inspector"><summary>Inspect a grid cell by keyboard</summary><label>Evaluated cell<select aria-label="Inspect evaluated grid cell" defaultValue="" onChange={event => {
      const feature = grid.data.features[Number(event.target.value)]; if (!feature || event.target.value === '') return;
      const properties = feature.properties ?? {};
      onInspect({ title: String(properties.grid_id ?? feature.id ?? 'Evaluated grid cell'), status: String(properties[grid.statusProperty] ?? 'UNKNOWN'), properties: { ...properties, source: properties.source ?? grid.source, indicator_unit: grid.unit, layer_warning: grid.warning } });
    }}><option value="">Choose a cell</option>{grid.data.features.map((feature, index) => <option key={String(feature.id ?? index)} value={index}>{String(feature.properties?.grid_id ?? feature.id ?? index)} · {String(feature.properties?.[grid.statusProperty] ?? 'UNKNOWN')}</option>)}</select></label><p className="quiet">Same returned grid evidence as the map. Inspect reasons, source status and Unknown requirements.</p></details>}
  </>;
}
