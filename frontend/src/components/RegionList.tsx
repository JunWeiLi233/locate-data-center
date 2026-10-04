import { Check, Plus, ChevronRight } from 'lucide-react';
import type { CandidateRegion } from '../types/domain';
import { formatMetric, formatScore } from '../utils/format';
import { FactorBars } from './FactorBars';

/** Retain the existing result cards while distinguishing physical county tradeoffs from ranks. */
export function RegionList({ regions, selectedId, comparisonIds, onSelect, onCompare, displayCount }: {
  regions: CandidateRegion[]; selectedId: string | null; comparisonIds: string[];
  onSelect: (id: string) => void; onCompare: (id: string) => void; displayCount: number;
}) {
  return <section className="results-list" aria-label="Potential regions"><div className="section-heading"><h2>Potential regions</h2><span className="count-tag">{regions.length} / {displayCount}</span></div>
    <p className="form-note">{regions.some(region => region.modelKind === 'monte-carlo') ? 'County tradeoffs have no scalar rank or score. Pareto membership is conditional on the selected scenario; local feasibility remains unverified.' : 'Rank and score describe the evaluated representative alternative, not an independent region ranking.'}</p>
    {!regions.length && <div className="empty-mini">No regions match the display filters. The model results have not been changed.</div>}
    {regions.map(region => <article className={`region-card ${selectedId === region.id ? 'selected' : ''}`} key={region.id}>
      <button className="region-select" aria-label={`Select ${region.label}, ${region.designId}`} aria-pressed={selectedId === region.id} onClick={() => onSelect(region.id)}>
        <span className="region-index">{region.rank ?? '—'}</span><span className="region-name"><strong>{region.label}</strong><small>{region.designId}</small></span><ChevronRight size={16} />
      </button>
      <div className="card-score"><strong>{region.modelKind === 'monte-carlo' ? 'Unweighted tradeoff' : <>{formatScore(region.score)}<small> / 100</small></>}</strong><span className={`status-badge ${region.screeningStatus.toLowerCase()}`}>{region.screeningStatus}</span></div>
      {/* County cards expose backend means without converting them to favorable factor scores. */}
      {region.modelKind === 'monte-carlo' && <p className="form-note">{region.metrics.filter(metric => metric.id === 'lifetime_electricity_cost_usd_mean' || metric.id === 'lifetime_operational_co2e_tonnes_mean').map(metric => <span key={metric.id}>{metric.label}: {formatMetric(metric)}<br /></span>)}</p>}
      <p className="rank-basis">{region.rankBasis}</p>{region.modelKind !== 'monte-carlo' && <FactorBars factors={region.factors} compact />}
      <div className="card-footer"><span>{region.paretoOptimal === true ? 'Pareto frontier' : region.paretoOptimal === false ? 'Pareto dominated' : 'Pareto Unknown'}</span>
        <button className="text-button" aria-label={`${comparisonIds.includes(region.id) ? 'Remove' : 'Add'} ${region.label}, ${region.designId} ${comparisonIds.includes(region.id) ? 'from' : 'to'} comparison`} onClick={() => onCompare(region.id)} disabled={!comparisonIds.includes(region.id) && comparisonIds.length >= 3}>{comparisonIds.includes(region.id) ? <Check size={13} /> : <Plus size={13} />}{comparisonIds.includes(region.id) ? 'Added' : 'Compare'}</button>
      </div>
    </article>)}
  </section>;
}
