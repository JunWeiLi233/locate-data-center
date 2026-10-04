import { Layers } from 'lucide-react';
import type { LayerCapability, LayerSelection } from '../types/domain';
import type { BasemapVisibility } from '../map/mapStyle';

export function LayerControls({ capabilities, selections, onChange, availableRun, basemap, onBasemapChange, regional = false, activeWindow = false }: { capabilities: LayerCapability[]; selections: LayerSelection[]; onChange: (values: LayerSelection[]) => void; availableRun: boolean; basemap?: BasemapVisibility; onBasemapChange?: (value: BasemapVisibility) => void; regional?: boolean; activeWindow?: boolean }) {
  const update = (id: LayerCapability['id'], enabled: boolean, sublayer?: string) => onChange([...selections.filter(value => value.id !== id), { id, enabled, ...(sublayer ? { sublayer } : {}) }]);
  const option = (layer: LayerCapability) => {
    const selected = selections.find(value => value.id === layer.id); const disabled = !layer.available || !availableRun || (regional && !activeWindow && layer.id !== 'candidates');
    return <div className="layer-option" key={layer.id}><label><input type="checkbox" checked={selected?.enabled ?? false} disabled={disabled} onChange={event => update(layer.id, event.target.checked, selected?.sublayer ?? layer.sublayers.find(value => value.available)?.id)} /><span>{layer.label}</span></label>
      {/* Waiting for a selected region is explained once above the list, not under every indicator. */}
      {disabled && !(layer.available && availableRun && regional && !activeWindow) && <small>{layer.reason ?? (!availableRun ? 'Load or evaluate a run first.' : 'No supported source data.')}</small>}
      {layer.available && layer.sublayers.length > 1 && <select aria-label={`${layer.label} indicator`} disabled={disabled} value={selected?.sublayer ?? layer.sublayers.find(value => value.available)?.id ?? ''} onChange={event => update(layer.id, true, event.target.value)}>{layer.sublayers.map(value => <option key={value.id} value={value.id} disabled={!value.available}>{value.label}{!value.available ? ` — ${value.reason ?? 'Unavailable'}` : ''}</option>)}</select>}
      {layer.id === 'climate' && layer.available && <small>Each hazard is shown separately; no blended climate score is inferred.</small>}
    </div>;
  };
  const mapCapabilities = capabilities.filter(layer => layer.id !== 'community_economic');
  const offered = mapCapabilities.filter(layer => layer.available);
  const unavailable = mapCapabilities.filter(layer => !layer.available);
  return <details className="layer-controls"><summary><Layers size={15} /><span>Map layers</span></summary><div className="layer-options">
    {basemap && onBasemapChange && <section>
      <p className="micro-label">Base map</p>
      <div className="layer-option"><label><input type="checkbox" checked={basemap.relief} onChange={event => onBasemapChange({ ...basemap, relief: event.target.checked })} /><span>Terrain relief</span></label></div>
      <div className="layer-option"><label><input type="checkbox" checked={basemap.forest} onChange={event => onBasemapChange({ ...basemap, forest: event.target.checked })} /><span>Forest canopy</span></label></div>
    </section>}
    <section>
      <p className="micro-label">Model indicators</p>
      {!availableRun ? <p className="form-note">Available after a search or a loaded run.</p> : <>
        {regional && <p className="form-note">{activeWindow ? 'Indicators show the selected region’s refinement window only.' : 'Select a region to load its refinement window.'}</p>}
        {offered.map(option)}
      </>}
      {unavailable.length > 0 && <details className="layer-unavailable"><summary>Not available in this model ({unavailable.length})</summary>{unavailable.map(option)}</details>}
    </section>
    <details className="layer-about"><summary>About the map</summary>
      <p>Map context is not analyzed coverage. Indicators load on request; a missing layer is unavailable, not zero risk.</p>
      {basemap && <p>Terrain relief: shaded elevation from AWS Terrain Tiles (USGS 3DEP in the U.S.). Forest canopy: USFS tree canopy cover 2021 via MRLC.</p>}
      <p>U.S. boundary · Census 2025. Dark line: U.S. international border. Grey: state borders, including through rivers and bays. Pale line: shoreline, generalized 1:500,000 at national zoom and detailed TIGER/Line land and water from city zoom. Other countries: plain generalized fill and dashed borders (Natural Earth 1:10m), without geographic detail.</p>
      <a href={`${import.meta.env.BASE_URL}map/boundary-manifest.json`} target="_blank" rel="noopener">Boundary source and accuracy record</a>
    </details>
  </div></details>;
}
