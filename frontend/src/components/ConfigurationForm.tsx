import { useEffect, useState, type FormEvent } from 'react';
import { SlidersHorizontal, ArrowRight } from 'lucide-react';
import type { Capabilities, FacilityConfiguration } from '../types/domain';
const EMPTY_GROUPS: Capabilities['weightingGroups'] = [];

/** Reuse the original form layout while exposing only the selected model's controls. */
export function ConfigurationForm({ configuration, capabilities, busy, onChange, onSubmit }: {
  configuration: FacilityConfiguration; capabilities: Capabilities | null; busy: boolean;
  onChange: (value: FacilityConfiguration) => void; onSubmit: () => void;
}) {
  const groups = capabilities?.weightingGroups ?? EMPTY_GROUPS;
  // The county adapter has explicit priors/audits and no MCDA or cooling-curve alternatives.
  const county = capabilities?.modelKind === 'monte-carlo';
  const [matrix, setMatrix] = useState<string[][]>([]);
  const [message, setMessage] = useState<string | null>(null);
  useEffect(() => {
    setMatrix(old => configuration.ahpMatrix || old.length !== groups.length ? groups.map((_, row) => groups.map((__, col) => row === col ? '1' : configuration.ahpMatrix?.[row]?.[col]?.toString() ?? '')) : old);
  }, [groups, configuration.ahpMatrix]);
  // Change settings immutably so the existing stale-result notice still detects edits.
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
  // Catch JSON syntax locally; the backend remains authoritative on numeric/model validity.
  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (county) {
      try { JSON.parse(configuration.monteCarlo?.settingsJson ?? ''); }
      catch { setMessage('Monte Carlo settings must be valid JSON; no assumptions have been submitted.'); return; }
    }
    if (configuration.weighting === 'ahp' && !configuration.ahpMatrix) { setMessage('Complete every criteria comparison before running AHP.'); return; }
    setMessage(null); onSubmit();
  };
  return <form className="configuration-form" onSubmit={submit}>
    <div className="section-heading"><SlidersHorizontal size={16} /><h2>Facility configuration</h2></div>
    <p className="quiet">A stated facility, a declared decision policy.</p>
    <div className="field-pair"><label>Peak IT power <span>MW</span><input aria-label="Peak IT power MW" type="number" required min="0.01" max={county ? 10000 : 1000} step="any" value={configuration.peakItPowerMw} onChange={e => update('peakItPowerMw', Number(e.target.value))} /></label>
      <label>Average load <span>%</span><input aria-label="Average load percent" type="number" required min="0.01" max="100" step="any" value={configuration.averageLoadPercent} onChange={e => update('averageLoadPercent', Number(e.target.value))} /></label></div>
    <div className="field-pair"><label>Opening year<input aria-label="Target opening year" type="number" required min={county ? 2025 : 2026} max={county ? 2050 : 2100} step="1" value={configuration.targetOpeningYear} onChange={e => update('targetOpeningYear', Number(e.target.value))} /></label>
      <label>Operating life <span>years</span><input aria-label="Operating lifetime years" type="number" required min="1" max={county ? 40 : 100} step="1" value={configuration.lifetimeYears} onChange={e => update('lifetimeYears', Number(e.target.value))} /></label></div>
    <label>Cooling design<select value={configuration.cooling} onChange={e => update('cooling', e.target.value)}>{(capabilities?.coolingOptions ?? [{ id: 'all', label: 'Evaluate cooling alternatives' }]).map(option => <option key={option.id} value={option.id}>{option.label}</option>)}</select></label>
    <label>Screening policy<select value={configuration.screeningMode} onChange={e => update('screeningMode', e.target.value)}><option value="STRICT">Strict — critical Unknown excludes</option><option value="EXPLORATORY">Exploratory — conditional search zones</option></select></label>
    <p className="form-note">{county ? 'Verified mode can return no counties: power, water allocation, zoning and fiber remain unverified. Exploratory results are conditional tradeoffs.' : 'UNKNOWN is never a pass. Cooling options are evaluated as separate alternatives.'}</p>
    {!county && <label>Decision preferences<select value={configuration.weighting} onChange={e => changeWeighting(e.target.value as FacilityConfiguration['weighting'])}><option value="equal">Equal parent groups</option><option value="user">User group weights</option><option value="ahp">AHP criteria comparisons</option></select></label>}
    {county && <fieldset><legend>Explicit Monte Carlo assumptions</legend>
      <p className="form-note">Unweighted expected and CVaR Pareto frontiers; no combined score. Demo PUE/WUE priors and future rates are unconfirmed assumptions. Equal WUE gives equal direct water use.</p>
      <details><summary>Review / edit complete model JSON</summary><p className="form-note">The facility controls above override IT MW, utilization, opening year, horizon and feasibility mode. All remaining JSON settings are submitted unchanged, including priors, source labels, scenario IDs, draws, seed, hours and discounting.</p>
        <label>Model settings<textarea aria-label="Monte Carlo model settings" rows={18} value={configuration.monteCarlo?.settingsJson ?? ''} onChange={e => update('monteCarlo', { sensitivity: true, convergence: true, ...configuration.monteCarlo, settingsJson: e.target.value })} /></label>
      </details>
      <label><input type="checkbox" checked={configuration.monteCarlo?.sensitivity ?? true} onChange={e => update('monteCarlo', { settingsJson: '', convergence: true, ...configuration.monteCarlo, sensitivity: e.target.checked })} />Run sensitivity audit</label>
      <label><input type="checkbox" checked={configuration.monteCarlo?.convergence ?? true} onChange={e => update('monteCarlo', { settingsJson: '', sensitivity: true, ...configuration.monteCarlo, convergence: e.target.checked })} />Run 1k / 5k / 10k convergence audit</label>
      <p className="form-note">Audits add computation. For a quick check, set simulation_count to 500 and disable both audits; skipped audits are not reported as passed.</p>
    </fieldset>}
    {configuration.weighting === 'user' && <fieldset><legend>Relative parent-group weights</legend><p className="quiet">The backend normalizes these preferences and applies declared local weights.</p>{groups.map(group => <label key={group.id}>{group.label}<input aria-label={`${group.label} weight`} type="number" required min="0" step="0.05" value={configuration.groupWeights[group.id] ?? 0} onChange={e => update('groupWeights', { ...configuration.groupWeights, [group.id]: Number(e.target.value) })} /></label>)}</fieldset>}
    {configuration.weighting === 'ahp' && <fieldset><legend>Compare criteria, not locations</legend><p className="quiet">Enter all pairs. Reciprocal entries are preserved; only the backend computes weights and consistency.</p><div className="ahp-pairs">{groups.flatMap((a, row) => groups.slice(row + 1).map((b, offset) => {
      const col = row + offset + 1; return <label key={`${a.id}-${b.id}`}><span>{a.label} / {b.label}</span><input aria-label={`${a.label} compared with ${b.label}`} type="number" required min="0.000001" step="any" placeholder="Judgment" value={matrix[row]?.[col] ?? ''} onChange={e => judgment(row, col, e.target.value)} /><small>Reciprocal: {matrix[col]?.[row] || 'unsupplied'}</small></label>;
    }))}</div></fieldset>}
    {message && <p className="error-note" role="alert">{message}</p>}
    <button className="button primary run-button" type="submit" disabled={!capabilities || busy}>{busy ? 'Evaluating configuration…' : 'Find locations'}<ArrowRight size={16} aria-hidden="true" /></button>
    <p className="form-note">Search regions require local parcel, utility, water and engineering verification.</p>
  </form>;
}
