import { X, MapPin, ShieldAlert, FileText, ArrowUpRight } from 'lucide-react';
import type { ReactNode } from 'react';
import type { CandidateRegion, Metric, RunResult } from '../types/domain';
import { formatMetric, formatScore, safeExportUrl } from '../utils/format';
import { FactorBars } from './FactorBars';
import { SourceDetails } from './SourceDetails';

export function RawMetrics({ metrics }: { metrics: Metric[] }) {
  const groups = [...new Set(metrics.map(metric => metric.group))];
  return <div className="raw-metrics">{groups.map(group => <section key={group}><h4>{group}</h4>{metrics.filter(metric => metric.group === group).map(metric => <article className="metric-row" key={metric.id}>
    <div className="metric-title"><span>{metric.label}</span><strong>{formatMetric(metric)}</strong></div>
    <div className="metric-meta"><span className={`value-status ${metric.status}`}>{metric.status}</span><span>Confidence: {metric.confidence}</span></div>
    {(metric.value === null || metric.status === 'unknown') && <p className="missing-reason">{metric.missingReason ?? 'No supported value was supplied.'}</p>}
    <SourceDetails sources={metric.sources} />
  </article>)}</section>)}</div>;
}

export function RegionDetails({ region, result, onClose, onCompare, compared, canCompare = true, stale = false, notice }: { region: CandidateRegion; result: RunResult; onClose: () => void; onCompare: () => void; compared: boolean; canCompare?: boolean; stale?: boolean; notice?: ReactNode }) {
  return <aside className="detail-drawer" aria-label={`Details for ${region.label}`}><header className="drawer-heading"><div><p className="micro-label">Evaluated search region</p><h2>{region.label}</h2></div><button className="icon-button" aria-label="Close region details" onClick={onClose}><X size={18} /></button></header>
    {notice}{stale && <p className="stale-detail-notice">Previous evaluated region · these details retain the prior run’s configuration and context.</p>}
    <div className={`detail-scroll ${stale ? 'previous-results' : ''}`}><div className="detail-score"><strong>{formatScore(region.score)}<small> / 100</small></strong><div><span className={`status-badge ${region.screeningStatus.toLowerCase()}`}>{region.screeningStatus}</span><p>Representative alternative #{region.rank ?? 'Unknown'}</p></div></div>
      <p className="rank-basis">{region.rankBasis}</p><p className="quiet">Region mean score: <strong>{formatScore(region.regionMeanScore)}</strong>. Cooling: {region.designId}. Scenario: {region.scenarioId}.</p>
      <p className="pareto-note">Pareto efficiency: <strong>{region.paretoOptimal === true ? 'Yes' : region.paretoOptimal === false ? 'No' : 'Unknown'}</strong>. A frontier alternative has no assessed alternative that improves every selected objective. This does not establish an objectively best location.</p>
      <div className="geometry-notice"><MapPin size={16} /><p>This polygon is a <strong>search area</strong>. Its centroid is not an approved construction parcel. {region.geometryWarning}</p></div>
      <FactorBars factors={region.factors} />
      <section className="detail-section"><h3>Why this area?</h3>{region.strengths.length ? <ul>{region.strengths.map(value => <li key={value}>{value}</li>)}</ul> : <p>No supported strengths were supplied.</p>}<h4>Limits and trade-offs</h4>{region.limitations.length ? <ul>{region.limitations.map(value => <li key={value}>{value}</li>)}</ul> : <p>No additional structured explanation was supplied.</p>}</section>
      <section className="detail-section"><h3><ShieldAlert size={15} />Verification required</h3><ul>{region.verificationRequired.map(value => <li key={value}>{value}</li>)}</ul><p className="quiet">Data quality: {region.dataQuality}</p>{region.uncertainties.length > 0 && <details><summary>Critical Unknowns and uncertainty</summary><ul>{region.uncertainties.map(value => <li key={value}>{value}</li>)}</ul></details>}</section>
      <section className="detail-section"><h3>Sensitivity</h3>{region.sensitivity ? <><p>Backend representative rank: {region.sensitivity.baseRank ?? 'Unknown'}; evaluated range <strong>{region.sensitivity.minRank ?? 'Unknown'}–{region.sensitivity.maxRank ?? 'Unknown'}</strong>.</p><ul>{region.sensitivity.drivers.map(value => <li key={value}>{value}</li>)}</ul></> : <p>No matched sensitivity result is available for this region. No stability claim is made.</p>}</section>
      <section className="detail-section"><h3><FileText size={15} />Raw quantities and evidence</h3><p className="quiet">Physical values retain their units and source status. Risk values are not favorable factor scores.</p><RawMetrics metrics={region.metrics} /></section>
      <section className="detail-section"><h3>Model record</h3><dl className="record-meta"><dt>Run</dt><dd>{result.runId}</dd><dt>Model</dt><dd>{result.modelVersion}</dd><dt>Timestamp</dt><dd>{result.timestamp ?? 'Unknown'}</dd><dt>Coverage</dt><dd>{result.scope} · {result.analyzedCellCount} cells</dd></dl>
        <div className="export-links">{result.exports.map(value => { const url = safeExportUrl(value.url); return url ? <a key={value.label} href={url} target="_blank" rel="noopener noreferrer">{value.label}<ArrowUpRight size={13} /></a> : null; })}</div>
      </section>
    </div><footer className="drawer-footer"><button className="button secondary" disabled={!compared && !canCompare} onClick={onCompare}>{compared ? 'Remove from comparison' : 'Compare this region'}</button>{!compared && !canCompare && <p className="compare-limit">Three regions selected. Remove one to add this region.</p>}</footer>
  </aside>;
}
