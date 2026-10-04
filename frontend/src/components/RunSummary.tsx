import type { RunResult } from '../types/domain';
import { humanize, type PlaceGroup } from '../utils/regions';
import { AnalysisCoverage } from './AnalysisCoverage';
import { MonteCarloEvidence } from './MonteCarloEvidence';

const GROUP_LABELS: Record<string, string> = { energy_carbon: 'Energy / carbon', water_stewardship: 'Water stewardship', grid_infrastructure: 'Grid infrastructure', land: 'Land' };
const count = (value: number | null | undefined) => value == null ? 'not reported' : value.toLocaleString('en-US');
const percent = (value: number) => `${(value * 100).toLocaleString('en-US', { maximumFractionDigits: 1 })}%`;

/** Coverage and caveats of the displayed run; the facility itself is summarized by FacilitySummary. */
export function RunSummary({ result, groups, onLoadParent }: { result: RunResult; groups: PlaceGroup[]; onLoadParent?: () => void }) {
  const county = result.modelKind === 'monte-carlo';
  const resolution = result.analysis ? result.analysis.cellSizeM : result.analysisResolutionM ?? null;
  const conditional = groups.filter(group => group.alternatives.every(region => region.screeningStatus === 'CONDITIONAL')).length;
  const coverage = `${result.analyzedCellCount.toLocaleString('en-US')} ${result.coverageUnit ?? 'cells'}${resolution === null ? '' : ` at ${resolution / 1000} km`}${result.analysis ? ' (regional refinement)' : ''}`;
  // The coverage warning is already printed in the coverage section.
  const notes = result.warnings.filter(value => value !== result.analysis?.coverageWarning);
  return <section className="run-summary" aria-label="Run coverage">
    {/* Regional runs state cells, extent and coverage in the compact analysis line instead. */}
    {!result.analysis && <p className="run-summary-scope">{coverage}</p>}
    {!county && result.analysisMode === 'full_rediscovery' && <p className="run-summary-scope">Full nationwide rediscovery.</p>}
    {result.analysis ? <AnalysisCoverage analysis={result.analysis} compact /> : <p className="summary-note">{result.scope}</p>}
    {result.state === 'PARTIAL' && <p className="summary-note summary-caveat">Results contain unresolved critical data.{conditional > 0 && ` ${conditional === groups.length ? groups.length === 1 ? 'The only area is' : `All ${conditional} areas are` : `${conditional} of ${groups.length} areas ${conditional === 1 ? 'is' : 'are'}`} conditional: check each area’s verification list before investing.`}</p>}
    <details className="run-details"><summary>Run details</summary>
      {/* A regional run's scope sentence repeats its coverage section, so only other runs print it. */}
      {!result.analysis && <p>{result.scope}</p>}
      {result.analysis ? <AnalysisCoverage analysis={result.analysis} onLoadParent={onLoadParent} /> : result.analysisResolutionM != null && <p>{result.analysisResolutionM / 1000} km analysis resolution · inspect recorded geographic scope.</p>}
      <h4>Screening and search stages</h4><ul>{result.searchStages.map(value => <li key={value.label}>{value.label}: {count(value.count)}</li>)}</ul>
      {county ? <p>{groups.length} county representative points. Expected and upper-tail CVaR frontiers describe separate physical tradeoffs; no scalar rank or score is computed.</p> : <p>{count(result.regions.length)} evaluated cooling alternatives across {count(groups.length)} search {groups.length === 1 ? 'area' : 'areas'}. Rank and score describe each area’s representative alternative, not an independent region ranking.</p>}
      {result.weighting && <><h4>Weights used</h4><p>{humanize(result.weighting.status.toLowerCase())} · Consistency ratio: {result.weighting.consistencyRatio ?? 'not applicable'}</p><dl>{Object.entries(result.weighting.weights).map(([id, value]) => <div key={id}><dt>{GROUP_LABELS[id] ?? humanize(id)}</dt><dd>{percent(value)}</dd></div>)}</dl></>}
      {notes.length > 0 && <><h4>Model notes and limitations ({notes.length})</h4><ul>{notes.map(value => <li key={value}>{value}</li>)}</ul></>}
      <p className="quiet">Run {result.runId} · {result.modelVersion}</p>
    </details>
    {county && <MonteCarloEvidence result={result} />}
  </section>;
}
