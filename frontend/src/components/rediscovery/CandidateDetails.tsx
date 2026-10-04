import { X } from 'lucide-react';
import type { RediscoveryCandidate, RediscoveryResult } from '../../types/rediscovery';
import { ClassMark, placeName } from './ValidationDashboard';

const FACTOR_NAMES: Record<string, string> = {
  annual_electricity_co2e: 'Grid carbon (annual CO2e)', annual_site_water_consumption: 'Site water (cooling design)',
  local_baseline_water_stress: 'Basin water stress', transmission_proximity: 'Transmission proximity', suitable_land_fraction: 'Suitable land cover',
};
const NOT_SCORED_NAMES: Record<string, string> = { fiber: 'Fiber / connectivity', climate: 'Climate / cooling', natural_hazard: 'Natural hazard', energy_cost: 'Energy cost' };

function rawValue(value: number | null, unit: string | null): string {
  if (value === null) return 'Unknown';
  if (unit === 'frac') return `${(100 * value).toFixed(0)}%`;
  const digits = Math.abs(value) >= 1000 ? 0 : Math.abs(value) >= 10 ? 1 : 2;
  return `${value.toLocaleString('en-US', { maximumFractionDigits: digits })} ${unit?.replaceAll('_', ' ') ?? ''}`.trim();
}

export function CandidateDetails({ candidate, result, onClose }: { candidate: RediscoveryCandidate; result: RediscoveryResult; onClose: () => void }) {
  const tied = candidate.scoreRankMax > candidate.scoreRankMin;
  const factors = [...candidate.factors].sort((a, b) => (b.contribution ?? -1) - (a.contribution ?? -1));
  const robustness = candidate.robustness;
  const details = robustness.details;
  return <aside className="detail-drawer rd-drawer" aria-label={`Details for candidate ${candidate.rank}, ${placeName(candidate)}`}>
    <header className="drawer-heading"><div><p className="micro-label">Candidate rank {candidate.rank}</p><h2>{placeName(candidate)}</h2>
      <p className="drawer-subtitle">{candidate.lat.toFixed(4)}, {candidate.lon.toFixed(4)} · 1 km cell {candidate.gridId}</p></div>
      <button type="button" className="icon-button" aria-label="Close candidate details" onClick={onClose}><X size={18} /></button></header>
    <div className="rd-drawer-body">
      <div className="rd-figures">
        <div><span>Suitability</span><strong>{candidate.suitabilityScore.toFixed(1)}</strong><small>of 100 · {candidate.scorePercentile.toFixed(2)} percentile</small></div>
        <div><span>Classification</span><strong><ClassMark value={candidate.classification} /></strong><small>{candidate.distanceKm.toFixed(1)} km to nearest facility</small></div>
        <div><span>Robustness</span><strong>{robustness.score === null ? 'Not evaluated' : robustness.score.toFixed(0)}</strong>
          <small>{robustness.score === null ? 'No Monte Carlo evidence here' : `${robustness.spatialSupport}-level Monte Carlo`}</small></div>
        <div><span>Weight sensitivity</span><strong>{candidate.weightCases.total ? `${candidate.weightCases.retained}/${candidate.weightCases.total}` : '—'}</strong><small>declared weighting cases retained</small></div>
      </div>
      {tied && <p className="rd-note rd-callout">This cell shares its score with {(candidate.tiedCellsAtScore - 1).toLocaleString('en-US')} other {candidate.tiedCellsAtScore === 2 ? 'cell' : 'cells'} (score ranks {candidate.scoreRankMin.toLocaleString('en-US')}–{candidate.scoreRankMax.toLocaleString('en-US')}). Its published rank follows the grid_id tie order, which is arbitrary in space.</p>}
      <section className="rd-why" aria-labelledby="rd-why-heading">
        <h3 id="rd-why-heading">Why was this location recommended?</h3>
        <p>{candidate.explanation}</p>
      </section>
      <section aria-labelledby="rd-factor-heading">
        <h3 id="rd-factor-heading">Factor breakdown</h3>
        <p className="rd-note">Contribution = weight × criterion score (0–100). Contributions add up to the suitability score.</p>
        <ul className="rd-factors">{factors.map(factor => <li key={factor.metricId}>
          <div className="rd-factor-head"><span>{FACTOR_NAMES[factor.metricId] ?? factor.label}</span><strong>{factor.contribution?.toFixed(1) ?? '—'}</strong></div>
          <div className="rd-factor-bar" aria-hidden="true"><span style={{ width: `${Math.max(0, Math.min(100, factor.normalizedScore ?? 0))}%` }} /></div>
          <small>Score {factor.normalizedScore?.toFixed(1) ?? 'Unknown'} × weight {factor.weight.toFixed(3)} · {rawValue(factor.rawValue, factor.rawUnit)} · {factor.valueStatus ?? 'unknown'}{factor.sourceId ? ` · ${factor.sourceId}` : ''}{factor.dataYear ? ` ${factor.dataYear}` : ''}{!factor.locationDependent ? ' · design-level, same everywhere' : ''}{factor.nationalPercentile !== null && factor.locationDependent ? ` · national percentile ${factor.nationalPercentile.toFixed(0)} (ties mid-ranked)` : ''}</small>
        </li>)}</ul>
        <details className="rd-details"><summary>Not scored by this model ({Object.keys(result.notScored).length})</summary>
          <ul className="rd-limitations">{Object.entries(result.notScored).map(([key, reason]) => <li key={key}><strong>{NOT_SCORED_NAMES[key] ?? key}:</strong> {reason}</li>)}</ul></details>
      </section>
      <section aria-labelledby="rd-nearest-heading">
        <h3 id="rd-nearest-heading">Nearest existing data center</h3>
        <dl className="rd-dl">
          <div><dt>Facility</dt><dd>{candidate.nearest.name ?? 'Unnamed record'}{candidate.nearest.operator ? ` · ${candidate.nearest.operator}` : ''}</dd></div>
          <div><dt>Where</dt><dd>{[candidate.nearest.county, candidate.nearest.stateAbbr].filter(Boolean).join(', ') || 'Unknown'} · {candidate.nearest.footprintType ?? 'record'}</dd></div>
          <div><dt>Distance</dt><dd>{candidate.distanceKm.toFixed(1)} km ({result.parameters.distanceMethod.split('_')[0]})</dd></div>
          <div><dt>Facility records within</dt><dd>{Object.entries(candidate.withinKm).map(([radius, count]) => `${radius} km: ${count ?? '—'}`).join(' · ')}</dd></div>
        </dl>
      </section>
      <section aria-labelledby="rd-robust-heading">
        <h3 id="rd-robust-heading">Monte Carlo robustness</h3>
        {robustness.score === null ? <p className="rd-note">{robustness.missingReason ?? 'Not supplied.'}</p> : <>
          <p>{robustness.score.toFixed(0)} / 100: {robustness.method?.replaceAll('_', ' ')} from {robustness.source}.</p>
          {details && <p className="rd-note">{String(details.county_name ?? '')} {String(details.state_abbr ?? '')}: on the expected frontier in {String(details.expected_frontier_scenarios ?? '—')} of {String(details.structural_scenarios ?? '—')} structural scenarios. Robustness is a county-level value, not a property of this 1 km cell.</p>}
        </>}
        {candidate.weightCases.total > 0 && <p className="rd-note">Declared weighting cases retained: {candidate.weightCases.retainedIds.map(id => id.replace('weight_', '').replaceAll('_', ' ')).join(', ') || 'none'}. These are deterministic sensitivity checks, not Monte Carlo draws.</p>}
      </section>
      <section aria-labelledby="rd-check-heading">
        <h3 id="rd-check-heading">Before any decision</h3>
        <p className="rd-note">{candidate.screeningStatus}: {candidate.screeningNote}. Verify parcel availability and zoning, utility capacity and interconnection, committed water, diverse fiber and hazards. A search area, not an approved site.</p>
        <p className="rd-note">Cooling design {candidate.designId} · scenario {candidate.scenarioId}.</p>
      </section>
    </div>
  </aside>;
}
