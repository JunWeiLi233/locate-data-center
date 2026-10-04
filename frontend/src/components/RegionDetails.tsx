import { X, MapPin, ShieldAlert, ArrowUpRight } from 'lucide-react';
import type { ReactNode } from 'react';
import type { Capabilities, CandidateRegion, Metric, RunResult, SocioeconomicContext } from '../types/domain';
import { formatMetric, formatScore, safeExportUrl } from '../utils/format';
import { coolingName, humanize, keyMetrics, regionName, shortCooling, spansLabel, verificationItem } from '../utils/regions';
import { FactorBars } from './FactorBars';
import { SourceDetails } from './SourceDetails';
import { CountyEconomicDetails } from './CountyEconomicContext';

export function RawMetrics({ metrics }: { metrics: Metric[] }) {
  const groups = [...new Set(metrics.map(metric => metric.group))];
  return <div className="raw-metrics">{groups.map(group => <section key={group}><h4>{humanize(group)}</h4>{metrics.filter(metric => metric.group === group).map(metric => <article className="metric-row" key={metric.id}>
    <div className="metric-title"><span>{metric.label}</span><strong>{formatMetric(metric)}</strong></div>
    <div className="metric-meta"><span className={`value-status ${metric.status}`}>{metric.status}</span><span>Confidence: {metric.confidence}</span></div>
    {(metric.value === null || metric.status === 'unknown') && <p className="missing-reason">{metric.missingReason ?? 'No supported value was supplied.'}</p>}
    <SourceDetails sources={metric.sources} />
  </article>)}</section>)}</div>;
}

function KeyFigures({ metrics }: { metrics: Metric[] }) {
  return <div className="key-figures">{metrics.map(metric => <div className="key-figure" key={metric.id}>
    <span>{metric.label}</span><strong>{formatMetric(metric)}</strong><small className={`value-status ${metric.status}`}>{metric.status}</small>
  </div>)}</div>;
}

function location(region: CandidateRegion): string | null {
  const parts = [region.placeLabel ? 'Primary county of the best-scoring cell' : null, spansLabel(region),
    region.cellCount ? `${region.cellCount.toLocaleString('en-US')} ${region.cellCount === 1 ? 'cell' : 'cells'}` : null];
  return parts.filter(Boolean).join(' · ') || null;
}

export function RegionDetails({ region, result, onClose, onCompare, compared, canCompare = true, stale = false, notice, alternatives = [region], coolingOptions = [], onSelectAlternative, economicContext = null, economicLoading = false, economicError = null, nameSuffix }: {
  region: CandidateRegion; result: RunResult; onClose: () => void; onCompare: () => void; compared: boolean; canCompare?: boolean; stale?: boolean; notice?: ReactNode;
  alternatives?: CandidateRegion[]; coolingOptions?: Capabilities['coolingOptions']; onSelectAlternative?: (id: string) => void;
  economicContext?: SocioeconomicContext | null; economicLoading?: boolean; economicError?: string | null;
  /** The list's area number for a repeated county name, e.g. " · area 2". */
  nameSuffix?: string;
}) {
  const name = regionName(region) + (nameSuffix ?? '');
  const county = region.modelKind === 'monte-carlo';
  const subtitle = location(region);
  const checks = region.verificationRequired.map(verificationItem);
  const sensitivity = region.sensitivity;
  const files = result.exports.flatMap(value => { const url = safeExportUrl(value.url); return url ? [{ label: value.label, url }] : []; });
  return <aside className="detail-drawer" aria-label={`Details for ${name}`}><header className="drawer-heading"><div><p className="micro-label">Search area</p><h2>{name}</h2>{subtitle && <p className="drawer-subtitle">{subtitle}</p>}</div><button className="icon-button" aria-label="Close region details" onClick={onClose}><X size={18} /></button></header>
    {notice}{stale && <p className="stale-detail-notice">Previous evaluated region · these details retain the prior run’s configuration and context.</p>}
    <div className={`detail-scroll ${stale ? 'previous-results' : ''}`}>
      <section className="detail-summary" aria-label="Summary">
        <div className={`detail-score ${county ? 'county-tradeoff' : ''}`}><strong>{county ? 'Physical tradeoff' : <>{formatScore(region.score)}<small> / 100</small></>}</strong><div><span className={`status-badge ${region.screeningStatus.toLowerCase()}`}>{region.screeningStatus}</span><p>{county ? 'No scalar rank or score' : region.rank === null ? 'Rank unknown' : `Rank #${region.rank}`}{region.paretoOptimal === true ? ' · Pareto-efficient' : ''}</p></div></div>
        {alternatives.length > 1 && onSelectAlternative ? <div className="cooling-switch" role="group" aria-label="Cooling design">{alternatives.map(item => <button key={item.id} aria-pressed={item.id === region.id} onClick={() => onSelectAlternative(item.id)}>
          <span>{shortCooling(coolingName(item.designId, coolingOptions))}</span><strong>{formatScore(item.score)}</strong></button>)}</div>
          : <p className="detail-cooling">Cooling: {coolingName(region.designId, coolingOptions)}</p>}
      </section>
      {!county && <section className="detail-block"><h3>Score breakdown</h3><FactorBars factors={region.factors} /></section>}
      <section className="detail-block"><h3>{county ? 'Conditional physical objectives' : 'Key figures'}</h3><KeyFigures metrics={county ? region.metrics.filter(metric => /_(mean|cvar)$/.test(metric.id)) : keyMetrics(region.metrics)} /></section>
      {county ? <section className="detail-block"><h3>County economic context</h3><p className="quiet">Unavailable from the county Monte Carlo API. No county economic estimates or mapped layers are supplied.</p></section> : <CountyEconomicDetails regionId={region.id} context={economicContext} loading={economicLoading} error={economicError} />}
      <section className="detail-block verify-block"><h3><ShieldAlert size={16} aria-hidden="true" />Verify before committing{checks.length ? ` (${checks.length})` : ''}</h3>
        {checks.length ? <ul className="verify-list">{checks.map((item, index) => <li key={`${item.title}-${index}`} title={item.detail ?? undefined}>{item.title}</li>)}</ul> : <p className="quiet">No open verification items were reported. That does not establish parcel feasibility.</p>}
        {checks.some(item => item.detail) && <details className="detail-more inline"><summary>Why these are open</summary><ul>{checks.map((item, index) => <li key={`${item.title}-${index}`}><strong>{item.title}:</strong> {item.detail ?? 'Requires verification.'}</li>)}</ul></details>}
      </section>
      <details className="detail-more"><summary>All measurements and sources <span>{region.metrics.length}</span></summary><p className="quiet">Physical values keep their units and source status. Risk values are not favorable scores.</p><RawMetrics metrics={region.metrics} /></details>
      <details className="detail-more"><summary>{county ? 'Frontiers and uncertainty' : 'Ranking and stability'} {sensitivity && <span>rank {sensitivity.minRank ?? '?'}–{sensitivity.maxRank ?? '?'}</span>}</summary>
        <p className="rank-basis">{region.rankBasis}</p>
        <p>{!county && <>Region mean score: <strong>{formatScore(region.regionMeanScore)}</strong> across member cells. </>}Cooling: {coolingName(region.designId, coolingOptions)}. Scenario: {region.scenarioId}.</p>
        <p className="pareto-note">Pareto efficiency: <strong>{region.paretoOptimal === true ? 'Yes' : region.paretoOptimal === false ? 'No' : 'Unknown'}</strong>. A frontier alternative has no assessed alternative that improves every selected objective. This does not establish an objectively best location.</p>
        {county ? <p>Input uncertainty and Monte Carlo estimator error are distinct. Requested sensitivity and convergence audits remain inspectable in the full model record.</p> : sensitivity ? <><p>Backend representative rank {sensitivity.baseRank ?? 'Unknown'}; evaluated range <strong>{sensitivity.minRank ?? 'Unknown'}–{sensitivity.maxRank ?? 'Unknown'}</strong> under the tested preference changes.</p>{sensitivity.drivers.length > 0 && <><h4>Main drivers</h4><ul>{sensitivity.drivers.map(value => <li key={value}>{humanize(value)}</li>)}</ul></>}</> : <p>No matched sensitivity result is available for this region. No stability claim is made.</p>}
        {result.analysis && <p className="quiet">Regional analysis at {result.analysis.cellSizeM === null ? 'unreported' : result.analysis.cellSizeM / 1000} km resolution. Maximum region span: {result.analysis.maximumRegionExtentKm ?? 'not reported'} km per projected axis. Representative evaluated cell: {region.representativeGridId ?? 'not reported'}. Parent discovery cell: {region.parentGridId ?? 'not reported'}. Indicator layers cover this refinement window; parcel zoning and industrial suitability require verification.</p>}
      </details>
      <details className="detail-more"><summary>Why this area and its limits</summary>
        <h4>Strengths</h4>{region.strengths.length ? <ul>{region.strengths.map(value => <li key={value}>{value}</li>)}</ul> : <p className="quiet">No supported strengths were supplied.</p>}
        <h4>Limits and trade-offs</h4>{region.limitations.length ? <ul>{region.limitations.map(value => <li key={value}>{value}</li>)}</ul> : <p className="quiet">No additional structured explanation was supplied.</p>}
        <p className="quiet">Data quality: {region.dataQuality}</p>
        {region.uncertainties.length > 0 && <><h4>Critical Unknowns and uncertainty</h4><ul>{region.uncertainties.map(value => <li key={value}>{value}</li>)}</ul></>}
      </details>
      <details className="detail-more"><summary>Model record and downloads {files.length > 0 && <span>{files.length} {files.length === 1 ? 'file' : 'files'}</span>}</summary>
        <dl className="record-meta"><dt>Run</dt><dd>{result.runId}</dd><dt>Model</dt><dd>{result.modelVersion}</dd><dt>Timestamp</dt><dd>{result.timestamp ?? 'Unknown'}</dd><dt>Coverage</dt><dd>{result.scope} · {result.analyzedCellCount} {result.coverageUnit ?? 'cells'}</dd>{region.areaKm2 != null && <><dt>Region area</dt><dd>{region.areaKm2.toLocaleString('en-US')} km²</dd></>}</dl>
        <div className="export-links">{files.map(value => <a key={value.label} href={value.url} target="_blank" rel="noopener noreferrer">{value.label}<ArrowUpRight size={13} /></a>)}</div>
      </details>
      <p className="geometry-notice"><MapPin size={15} aria-hidden="true" /><span>{county ? 'This county representative point is screening context, not an approved parcel.' : <>This polygon is a <strong>search area</strong>, not an approved construction parcel.</>} {region.geometryWarning}</span></p>
    </div><footer className="drawer-footer"><button className="button secondary" disabled={!compared && !canCompare} onClick={onCompare}>{compared ? 'Remove from comparison' : 'Compare this region'}</button>{!compared && !canCompare && <p className="compare-limit">Three regions selected. Remove one to add this region.</p>}</footer>
  </aside>;
}
