import { useEffect, useState, type FormEvent } from 'react';
import { SlidersHorizontal, ArrowRight } from 'lucide-react';
import type { Capabilities, FacilityConfiguration } from '../types/domain';
const EMPTY_GROUPS: Capabilities['weightingGroups'] = [];

export function ConfigurationForm({ configuration, capabilities, busy, onChange, onSubmit }: {
  configuration: FacilityConfiguration; capabilities: Capabilities | null; busy: boolean;
  onChange: (value: FacilityConfiguration) => void; onSubmit: () => void;
}) {
  const groups = capabilities?.weightingGroups ?? EMPTY_GROUPS;
  const [matrix, setMatrix] = useState<string[][]>([]);
  const [message, setMessage] = useState<string | null>(null);
  useEffect(() => {
    setMatrix(old => configuration.ahpMatrix || old.length !== groups.length ? groups.map((_, row) => groups.map((__, col) => row === col ? '1' : configuration.ahpMatrix?.[row]?.[col]?.toString() ?? '')) : old);
  }, [groups, configuration.ahpMatrix]);
  const update = (field: keyof FacilityConfiguration, value: unknown) => onChange({ ...configuration, [field]: value });
  const changeWeighting = (weighting: FacilityConfiguration['weighting']) => {
    setMessage(null);
    if (weighting !== 'ahp') setMatrix(groups.map((_, row) => groups.map((__, col) => row === col ? '1' : '')));
    onChange({ ...configuration, weighting, ahpMatrix: weighting === 'ahp' ? configuration.ahpMatrix : null });
  };
  const judgment = (row: number, col: number, input: string) => {
    const next = matrix.map(values => [...values]); const number = Number(input);
    next[row][col] = input; next[col][row] = input && Number.isFinite(number) && number > 0 ? String(1 / number) : '';
    setMatrix(next);
    const complete = next.every(values => values.every(value => value !== '' && Number.isFinite(Number(value)) && Number(value) > 0));
    update('ahpMatrix', complete ? next.map(values => values.map(Number)) : null);
  };
  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (configuration.weighting === 'ahp' && !configuration.ahpMatrix) { setMessage('Complete every criteria comparison before running AHP.'); return; }
    setMessage(null); onSubmit();
  };
  return <form className="configuration-form" onSubmit={submit}>
    <div className="section-heading"><SlidersHorizontal size={16} /><h2>Facility configuration</h2></div>
    <p className="quiet">A stated facility, a declared decision policy.</p>
    <div className="field-pair"><label>Peak IT power <span>MW</span><input aria-label="Peak IT power MW" type="number" required min="0.01" max="1000" step="any" value={configuration.peakItPowerMw} onChange={e => update('peakItPowerMw', Number(e.target.value))} /></label>
      <label>Average load <span>%</span><input aria-label="Average load percent" type="number" required min="0.01" max="100" step="any" value={configuration.averageLoadPercent} onChange={e => update('averageLoadPercent', Number(e.target.value))} /></label></div>
    <div className="field-pair"><label>Opening year<input aria-label="Target opening year" type="number" required min="2026" max="2100" step="1" value={configuration.targetOpeningYear} onChange={e => update('targetOpeningYear', Number(e.target.value))} /></label>
      <label>Operating life <span>years</span><input aria-label="Operating lifetime years" type="number" required min="1" max="100" step="1" value={configuration.lifetimeYears} onChange={e => update('lifetimeYears', Number(e.target.value))} /></label></div>
    <label>Cooling design<select value={configuration.cooling} onChange={e => update('cooling', e.target.value)}>{(capabilities?.coolingOptions ?? [{ id: 'all', label: 'Evaluate cooling alternatives' }]).map(option => <option key={option.id} value={option.id}>{option.label}</option>)}</select></label>
    <label>Screening policy<select value={configuration.screeningMode} onChange={e => update('screeningMode', e.target.value)}><option value="STRICT">Strict — critical Unknown excludes</option><option value="EXPLORATORY">Exploratory — conditional search zones</option></select></label>
    <p className="form-note">UNKNOWN is never a pass. Cooling options are evaluated as separate alternatives.</p>
    <label>Decision preferences<select value={configuration.weighting} onChange={e => changeWeighting(e.target.value as FacilityConfiguration['weighting'])}><option value="equal">Equal parent groups</option><option value="user">User group weights</option><option value="ahp">AHP criteria comparisons</option></select></label>
    {configuration.weighting === 'user' && <fieldset><legend>Relative parent-group weights</legend><p className="quiet">The backend normalizes these preferences and applies declared local weights.</p>{groups.map(group => <label key={group.id}>{group.label}<input aria-label={`${group.label} weight`} type="number" required min="0" step="0.05" value={configuration.groupWeights[group.id] ?? 0} onChange={e => update('groupWeights', { ...configuration.groupWeights, [group.id]: Number(e.target.value) })} /></label>)}</fieldset>}
    {configuration.weighting === 'ahp' && <fieldset><legend>Compare criteria, not locations</legend><p className="quiet">Enter all pairs. Reciprocal entries are preserved; only the backend computes weights and consistency.</p><div className="ahp-pairs">{groups.flatMap((a, row) => groups.slice(row + 1).map((b, offset) => {
      const col = row + offset + 1; return <label key={`${a.id}-${b.id}`}><span>{a.label} / {b.label}</span><input aria-label={`${a.label} compared with ${b.label}`} type="number" required min="0.000001" step="any" placeholder="Judgment" value={matrix[row]?.[col] ?? ''} onChange={e => judgment(row, col, e.target.value)} /><small>Reciprocal: {matrix[col]?.[row] || 'unsupplied'}</small></label>;
    }))}</div></fieldset>}
    {message && <p className="error-note" role="alert">{message}</p>}
    <button className="button primary run-button" type="submit" disabled={!capabilities || busy}>{busy ? 'Evaluating configuration…' : 'Find locations'}<ArrowRight size={16} aria-hidden="true" /></button>
    <p className="form-note">Search regions require local parcel, utility, water and engineering verification.</p>
  </form>;
}
