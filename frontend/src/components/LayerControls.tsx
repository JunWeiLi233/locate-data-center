import { Layers } from 'lucide-react';
import type { LayerCapability, LayerSelection } from '../types/domain';

export function LayerControls({ capabilities, selections, onChange, availableRun }: { capabilities: LayerCapability[]; selections: LayerSelection[]; onChange: (values: LayerSelection[]) => void; availableRun: boolean }) {
  const update = (id: LayerCapability['id'], enabled: boolean, sublayer?: string) => onChange([...selections.filter(value => value.id !== id), { id, enabled, ...(sublayer ? { sublayer } : {}) }]);
  return <details className="layer-controls"><summary><Layers size={15} /><span>Map layers</span></summary><div className="layer-options"><p className="form-note">Optional indicators load on request. Missing layers are unavailable, not zero risk.</p>{capabilities.map(layer => {
    const selected = selections.find(value => value.id === layer.id); const disabled = !layer.available || !availableRun;
    return <div className="layer-option" key={layer.id}><label><input type="checkbox" checked={selected?.enabled ?? false} disabled={disabled} onChange={event => update(layer.id, event.target.checked, selected?.sublayer ?? layer.sublayers.find(value => value.available)?.id)} /><span>{layer.label}</span></label>
      {disabled && <small>{layer.reason ?? (!availableRun ? 'Load or evaluate a run first.' : 'No supported source data.')}</small>}
      {layer.sublayers.length > 0 && <select aria-label={`${layer.label} indicator`} disabled={disabled} value={selected?.sublayer ?? layer.sublayers.find(value => value.available)?.id ?? ''} onChange={event => update(layer.id, true, event.target.value)}>{layer.sublayers.map(value => <option key={value.id} value={value.id} disabled={!value.available}>{value.label}{!value.available ? ` — ${value.reason ?? 'Unavailable'}` : ''}</option>)}</select>}
      {layer.id === 'climate' && <small>View each hazard separately. No blended climate score is inferred.</small>}
    </div>;
  })}</div></details>;
}
