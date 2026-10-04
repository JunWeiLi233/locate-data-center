import { useEffect, useState, type FormEvent } from 'react';
import { ArrowLeft, ArrowRight } from 'lucide-react';
import type { Capabilities, FacilityConfiguration, GridAnalysisMode } from '../types/domain';
const EMPTY_GROUPS: Capabilities['weightingGroups'] = [];
const WEIGHTING_LABELS: Record<FacilityConfiguration['weighting'], string> = { equal: 'equal weights', user: 'custom weights', ahp: 'AHP comparisons' };
/** Short display names so the options fit the panel; the full service label stays in each option's title. */
const COOLING_SHORT: Record<string, string> = { all: 'Compare both cooling designs', air_dry_assumed: 'Air / dry cooling (assumed)',
  cold_plate_tower_assumed: 'Direct-to-chip / tower (assumed)', shared_priors: 'Shared PUE/WUE assumptions' };
const ratio = (value: number) => value.toLocaleString('en-US', { maximumFractionDigits: 2 });
/** Plain reading of one pairwise judgment; the model alone turns judgments into weights. */
function judgmentText(first: string, second: string, input: string | undefined): string {
  const value = Number(input);
  if (!input || !Number.isFinite(value) || value <= 0) return 'Not entered yet.';
  if (value === 1) return 'Equally important.';
  return value > 1 ? `${first} counts ${ratio(value)}× as much as ${second}.` : `${second} counts ${ratio(1 / value)}× as much as ${first}.`;
}

export function ConfigurationForm({ configuration, capabilities, busy, onChange, onSubmit, onCancel, analysisMode, onAnalysisModeChange }: {
  configuration: FacilityConfiguration; capabilities: Capabilities | null; busy: boolean;
  onChange: (value: FacilityConfiguration) => void; onSubmit: () => void;
  /** Present when evaluated results exist: returns to them and restores their facility, like the browser's Back. */
  onCancel?: () => void;
  analysisMode?: GridAnalysisMode; onAnalysisModeChange?: (value: GridAnalysisMode) => void;
}) {
  const groups = capabilities?.weightingGroups ?? EMPTY_GROUPS;
  const county = capabilities?.modelKind === 'monte-carlo';
  const modes = !county && onAnalysisModeChange ? capabilities?.analysisModes ?? [] : [];
  const mode = analysisMode ?? capabilities?.defaultAnalysisMode ?? 'full_rediscovery';
  const [matrix, setMatrix] = useState<string[][]>([]);
  const [message, setMessage] = useState<string | null>(null);
  const [advanced, setAdvanced] = useState(configuration.weighting !== 'equal');
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
    if (county) {
      try { JSON.parse(configuration.monteCarlo?.settingsJson ?? ''); }
      catch { setAdvanced(true); setMessage('Monte Carlo settings must be valid JSON; no assumptions have been submitted.'); return; }
    }
    if (configuration.weighting === 'ahp' && !configuration.ahpMatrix) { setAdvanced(true); setMessage('Complete every criteria comparison before running AHP.'); return; }
    setMessage(null); onSubmit();
  };
  const summary = [configuration.screeningMode === 'STRICT' ? 'Strict' : 'Exploratory', county ? 'unweighted tradeoffs' : WEIGHTING_LABELS[configuration.weighting],
    ...(modes.length ? [mode === 'cached_regional' ? 'fast' : 'full search'] : [])].join(' · ');
  const weightTotal = groups.reduce((sum, group) => { const value = configuration.groupWeights[group.id]; return sum + (Number.isFinite(value) && value > 0 ? value : 0); }, 0);
  const share = (id: string) => { const value = configuration.groupWeights[id]; return weightTotal > 0 && Number.isFinite(value) && value >= 0 ? `${Math.round(value / weightTotal * 100)}%` : '—'; };
  const coolingOptions = capabilities?.coolingOptions ?? [{ id: 'all', label: 'Evaluate cooling alternatives' }];
  return <form className="configuration-form" onSubmit={submit} onInvalidCapture={event => { if ((event.target as HTMLElement).closest('.advanced-settings')) setAdvanced(true); }}>
    {onCancel && <button type="button" className="text-button form-back" onClick={onCancel}><ArrowLeft size={14} aria-hidden="true" />Back to results</button>}
    <h2>Your facility</h2>
    <p className="quiet">{county ? 'Enter your facility. The model compares a fixed set of candidate counties under explicit assumptions; each county point still needs local checks.' : 'Enter your facility. The model searches the contiguous U.S. for areas worth investigating.'}</p>
    <div className="field-pair"><label>Peak IT power <span>MW</span><input aria-label="Peak IT power MW" type="number" required min="0.01" max={county ? 10000 : 1000} step="any" value={configuration.peakItPowerMw} onChange={e => update('peakItPowerMw', Number(e.target.value))} /></label>
      <label>Average load <span>%</span><input aria-label="Average load percent" type="number" required min="0.01" max="100" step="any" value={configuration.averageLoadPercent} onChange={e => update('averageLoadPercent', Number(e.target.value))} /></label></div>
    <div className="field-pair"><label>Opening year<input aria-label="Target opening year" type="number" required min={county ? 2025 : 2026} max={county ? 2050 : 2100} step="1" value={configuration.targetOpeningYear} onChange={e => update('targetOpeningYear', Number(e.target.value))} /></label>
      <label>Operating life <span>years</span><input aria-label="Operating lifetime years" type="number" required min="1" max={county ? 40 : 100} step="1" value={configuration.lifetimeYears} onChange={e => update('lifetimeYears', Number(e.target.value))} /></label></div>
    <label>Cooling design<select value={configuration.cooling} title={coolingOptions.find(option => option.id === configuration.cooling)?.label} onChange={e => update('cooling', e.target.value)}>{coolingOptions.map(option => <option key={option.id} value={option.id} title={option.label}>{COOLING_SHORT[option.id] ?? option.label}</option>)}</select></label>
    <details className="advanced-settings" open={advanced} onToggle={event => setAdvanced(event.currentTarget.open)}>
      <summary><span>More options</span><small>{summary}</small></summary>
      {modes.length > 0 && onAnalysisModeChange && <div className="grid-evaluation-mode">
        <label>Search depth<select value={mode} disabled={busy} onChange={event => onAnalysisModeChange(event.target.value as GridAnalysisMode)}>{modes.map(value => <option key={value.id} value={value.id} disabled={!value.available}>{value.id === 'cached_regional' ? 'Fast — re-score cached regions' : 'Full — new nationwide search (slow)'}{!value.available ? ` — ${value.reason ?? 'Unavailable'}` : ''}</option>)}</select></label>
        <p className="form-note">{mode === 'cached_regional' ? 'About 1 minute. Re-scores the regions already analyzed at 1 km for your facility and preferences; no new regions are searched.' : 'Repeats the national search and 1 km analysis. It can find new regions but takes much longer.'}</p>
      </div>}
      <label>Screening policy<select value={configuration.screeningMode} onChange={e => update('screeningMode', e.target.value)}><option value="STRICT">Strict — drop unresolved areas</option><option value="EXPLORATORY">Exploratory — keep and flag them</option></select></label>
      <p className="form-note">Unknown never counts as a pass. Exploratory keeps areas with unresolved critical data and marks them Conditional; Strict removes them and can return no areas.</p>
      {!county && <label>Decision preferences<select value={configuration.weighting} onChange={e => changeWeighting(e.target.value as FacilityConfiguration['weighting'])}><option value="equal">Equal weights (4 criteria groups)</option><option value="user">Custom weights</option><option value="ahp">Pairwise comparisons (AHP)</option></select></label>}
      {county && <fieldset><legend>Explicit Monte Carlo assumptions</legend>
        <p className="form-note">Unweighted expected and CVaR Pareto frontiers; no combined score. PUE/WUE priors and future rates are unconfirmed assumptions. Equal WUE gives equal direct water use.</p>
        <details><summary>Review / edit complete model JSON</summary><p className="form-note">Facility controls override IT MW, utilization, opening year, lifetime and feasibility mode. Other JSON settings are submitted unchanged; the backend validates every assumption.</p>
          <label>Model settings<textarea aria-label="Monte Carlo model settings" rows={18} value={configuration.monteCarlo?.settingsJson ?? ''} onChange={e => update('monteCarlo', { sensitivity: true, convergence: true, ...configuration.monteCarlo, settingsJson: e.target.value })} /></label>
        </details>
        <label><input type="checkbox" checked={configuration.monteCarlo?.sensitivity ?? true} onChange={e => update('monteCarlo', { settingsJson: '', convergence: true, ...configuration.monteCarlo, sensitivity: e.target.checked })} />Run sensitivity audit</label>
        <label><input type="checkbox" checked={configuration.monteCarlo?.convergence ?? true} onChange={e => update('monteCarlo', { settingsJson: '', sensitivity: true, ...configuration.monteCarlo, convergence: e.target.checked })} />Run 1k / 5k / 10k convergence audit</label>
        <p className="form-note">Audits add computation. Skipped audits remain explicitly unperformed.</p>
      </fieldset>}
      {!county && configuration.weighting === 'user' && <fieldset><legend>Relative importance of criteria groups</legend><p className="quiet">Enter any numbers of zero or more; they are scaled to 100% before ranking. Each metric's weight within its group stays as declared.</p>{groups.map(group => <label key={group.id}><span className="weight-label">{group.label}<output className="weight-share" aria-label={`${group.label} share`}>{share(group.id)}</output></span><input aria-label={`${group.label} weight`} type="number" required min="0" step="0.05" value={configuration.groupWeights[group.id] ?? 0} onChange={e => update('groupWeights', { ...configuration.groupWeights, [group.id]: Number(e.target.value) })} /></label>)}</fieldset>}
      {!county && configuration.weighting === 'ahp' && <fieldset><legend>Compare criteria, not locations</legend><p className="quiet">For each pair, enter how many times more important the first criterion is: 1 equal, 3 moderately, 5 strongly, 7 very strongly, 9 extremely. Enter a decimal below 1 (for example 0.33) when the second matters more. The model computes the weights and checks consistency.</p><div className="ahp-pairs">{groups.flatMap((a, row) => groups.slice(row + 1).map((b, offset) => {
        const col = row + offset + 1; return <label key={`${a.id}-${b.id}`}><span>{a.label} vs {b.label}</span><input aria-label={`${a.label} compared with ${b.label}`} type="number" required min="0.000001" step="any" placeholder="1–9" value={matrix[row]?.[col] ?? ''} onChange={e => judgment(row, col, e.target.value)} /><small>{judgmentText(a.label, b.label, matrix[row]?.[col])}</small></label>;
      }))}</div></fieldset>}
    </details>
    {message && <p className="error-note" role="alert">{message}</p>}
    <button className="button primary run-button" type="submit" disabled={!capabilities || busy}>{busy ? 'Evaluating configuration…' : 'Find locations'}<ArrowRight size={16} aria-hidden="true" /></button>
  </form>;
}
