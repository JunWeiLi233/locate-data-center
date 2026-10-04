import type { CountyBoundaryYear, CountyEconomicMetric, SocioeconomicContext, Source } from '../types/domain';
import { safeSourceUrl } from '../utils/format';
import { SourceDetails } from './SourceDetails';

const number = new Intl.NumberFormat('en-US', { maximumFractionDigits: 2 });
function sources(metadata: Record<string, unknown>): Source[] {
  const found: Source[] = [];
  const visit = (value: unknown, key: string, depth: number) => {
    if (!value || typeof value !== 'object' || Array.isArray(value) || depth > 3) return;
    const row = value as Record<string, unknown>;
    const url = [row.url, row.source_url, row.download_url].find(value => typeof value === 'string');
    if (typeof url === 'string' && safeSourceUrl(url)) found.push({ name: typeof row.name === 'string' ? row.name : typeof row.source_name === 'string' ? row.source_name : key.replaceAll('_', ' '),
      url: safeSourceUrl(url), datasetYear: row.year == null && row.data_year == null ? null : String(row.data_year ?? row.year), geography: 'County context', resolution: row.scale == null ? null : String(row.scale), method: typeof row.method === 'string' ? row.method : null, scenario: null });
    for (const [name, child] of Object.entries(row)) visit(child, name, depth + 1);
  };
  visit({estimate_source:metadata.estimate_source,boundary_source:metadata.boundary_source}, 'County data', 0); return found;
}

export function CountySourceDetails({ metadata }: { metadata: Record<string, unknown> }) { return <SourceDetails sources={sources(metadata)} />; }

export function CountyBoundarySelector({ year, onChange, label = 'Boundary vintage' }: { year: CountyBoundaryYear; onChange: (year: CountyBoundaryYear) => void; label?: string }) {
  return <label className="county-boundary-select">{label}<select aria-label={label} value={year} onChange={event => onChange(Number(event.target.value) as CountyBoundaryYear)}><option value="2025">2025 county boundaries</option><option value="2023">2023 county boundaries</option></select></label>;
}

export function CountyEconomicFilters({ boundaryYear, onBoundaryChange, poverty, income, povertyPercentile, lowIncomePercentile, onPovertyChange, onIncomeChange, onPovertyPercentileChange, onLowIncomePercentileChange, onClear, context, loading, error, shown, total }: {
  boundaryYear: CountyBoundaryYear; onBoundaryChange: (year: CountyBoundaryYear) => void;
  poverty: string; income: string; onPovertyChange: (value: string) => void; onIncomeChange: (value: string) => void;
  povertyPercentile: string; lowIncomePercentile: string; onPovertyPercentileChange: (value: string) => void; onLowIncomePercentileChange: (value: string) => void;
  onClear: () => void;
  context: SocioeconomicContext | null; loading: boolean; error: string | null; shown: number; total: number;
}) {
  const available = !!context?.available;
  const active = [poverty, income, povertyPercentile, lowIncomePercentile].some(value => value !== '');
  return <fieldset className="county-economic-filters"><legend>County economic context</legend>
    <CountyBoundarySelector year={boundaryYear} onChange={onBoundaryChange} />
    <p className="quiet">Generalized Census cartographic boundaries · 1:500,000. Boundary year selects the county overlap geometry; SAIPE estimates remain 2024.</p>
    <label>Minimum 2024 county poverty rate (%)<input aria-label="Minimum 2024 county poverty rate (%)" type="number" min="0" max="100" step="0.1" placeholder="No minimum" value={poverty} disabled={!available} onChange={event => onPovertyChange(event.target.value)} /></label>
    <label>Maximum 2024 median household income (USD)<input aria-label="Maximum 2024 median household income (USD)" type="number" min="0" step="1" placeholder="No maximum" value={income} disabled={!available} onChange={event => onIncomeChange(event.target.value)} /></label>
    <label>Minimum 2024 poverty percentile (0–100)<input aria-label="Minimum 2024 poverty percentile (0–100)" type="number" min="0" max="100" step="1" placeholder="No minimum" value={povertyPercentile} disabled={!available} onChange={event => onPovertyPercentileChange(event.target.value)} /></label>
    <label>Minimum 2024 low-income percentile (0–100)<input aria-label="Minimum 2024 low-income percentile (0–100)" type="number" min="0" max="100" step="1" placeholder="No minimum" value={lowIncomePercentile} disabled={!available} onChange={event => onLowIncomePercentileChange(event.target.value)} /></label>
    <p className="quiet">Supplied percentiles compare all valid CONUS SAIPE counties. Higher poverty and low-income percentiles indicate greater economic disadvantage.</p>
    <p className="quiet">Empty thresholds are disabled. Any overlapping county must satisfy every active threshold in that same county; missing estimates never match. Uses polygon overlap, not a centroid. Technical scores and global ranks are unchanged.</p>
    <p className="county-filter-count" aria-live="polite">{shown.toLocaleString('en-US')} of {total.toLocaleString('en-US')} {total === 1 ? 'area' : 'areas'} shown</p>
    <button className="text-button" type="button" disabled={!active} onClick={onClear}>Clear county filters</button>
    {(loading || error || !available) && <p className="quiet" role="status">{loading ? 'Loading county evidence for this boundary vintage…' : error ?? 'County economic evidence is unavailable for this run.'} {active && 'Active county filters cannot match unavailable evidence.'}</p>}
    {context?.warnings.map(warning => <p className="quiet" key={warning}>{warning}</p>)}
  </fieldset>;
}

function Estimate({ value, metric, unit, moe, moeMetric }: { value: number | null; metric?: CountyEconomicMetric; unit: string; moe: number | null; moeMetric?: CountyEconomicMetric }) {
  return <><strong>{value === null ? 'Unknown' : `${unit === 'USD' ? '$' : ''}${number.format(value)}${unit === '%' ? '%' : ''}`}</strong>
    <span className={`value-status ${metric?.status ?? 'unknown'}`}>{metric?.status ?? 'unknown'}</span>
    {value === null && <small>{metric?.missingReason ?? 'County estimate not acquired.'}</small>}
    <small>Confidence: {metric?.confidence ?? 'unknown'}</small>
    <small>{moe === null ? `MOE: Unknown — ${moeMetric?.missingReason ?? 'Not available.'}` : `MOE: ±${unit === 'USD' ? '$' : ''}${number.format(moe)}${unit === '%' ? ' percentage points' : ''} · ${moeMetric?.status ?? 'unknown'}`}</small>
    {moeMetric?.method && <small>{moeMetric.method}</small>}</>;
}

export function CountyEconomicDetails({ regionId, context, loading = false, error = null }: { regionId: string; context: SocioeconomicContext | null; loading?: boolean; error?: string | null }) {
  const counties = context?.regionCounties[regionId] ?? [];
  return <section className="detail-block county-economic-details" aria-label="Intersecting county economic context"><h3>County economic context</h3>
    <p className="quiet">All intersecting counties · polygon overlap, not the representative cell or centroid. This context does not adjust technical scores or ranks.</p>
    <p className="quiet">Supplied percentiles compare all valid CONUS SAIPE counties. Higher poverty and low-income percentiles indicate greater economic disadvantage.</p>
    {context && <p className="quiet">SAIPE {context.socioeconomicYear ?? 'Unknown'} estimates · {context.boundaryYear} boundaries · {context.boundarySourceKind ?? 'Boundary source kind not reported'}</p>}
    {counties.length > 0 ? <div className="county-context-list">{counties.map(county => <article key={county.countyGeoid}><h4>{county.countyName}{county.stateName ? `, ${county.stateName}` : ''}</h4>
      <p className="quiet">GEOID {county.countyGeoid} · {county.socioeconomicYear ?? 'Unknown'} estimates / {county.boundaryYear} boundaries · {county.overlapFraction === null ? 'Overlap share unknown' : `${number.format(county.overlapFraction * 100)}% of full member-grid geometry`}{county.overlapAreaKm2 === null ? '' : ` (${number.format(county.overlapAreaKm2)} km²)`}</p>
      <dl><dt>{county.socioeconomicYear ?? 'Unknown year'} poverty rate</dt><dd><Estimate value={county.povertyRatePct} metric={county.metrics.poverty_rate_pct} unit="%" moe={county.povertyRateMoePct} moeMetric={county.metrics.poverty_rate_moe_pct} /></dd>
        <dt>{county.socioeconomicYear ?? 'Unknown year'} median household income</dt><dd><Estimate value={county.medianHouseholdIncomeUsd} metric={county.metrics.income_usd} unit="USD" moe={county.incomeMoeUsd} moeMetric={county.metrics.income_moe_usd} /></dd>
        <dt>Poverty percentile</dt><dd>{county.povertyPercentile === null ? `Unknown — ${county.metrics.poverty_percentile?.missingReason ?? 'Not acquired'}` : number.format(county.povertyPercentile)} <span className={`value-status ${county.metrics.poverty_percentile?.status ?? 'unknown'}`}>{county.metrics.poverty_percentile?.status ?? 'unknown'}</span></dd>
        <dt>Low-income percentile</dt><dd>{county.lowIncomePercentile === null ? `Unknown — ${county.metrics.low_income_percentile?.missingReason ?? 'Not acquired'}` : number.format(county.lowIncomePercentile)} <span className={`value-status ${county.metrics.low_income_percentile?.status ?? 'unknown'}`}>{county.metrics.low_income_percentile?.status ?? 'unknown'}</span></dd></dl>
    </article>)}</div> : <p className="quiet">{loading ? 'Loading overlapping county evidence…' : error ?? 'No supported overlapping county record is available.'}</p>}
    <p className="quiet">Fiscal significance: <strong>Unknown — fiscal inputs not acquired</strong>. Local revenue and service pressure require acquired fiscal evidence.</p>
    {context && <><p className="quiet">Overlap denominator: {typeof context.coverageSummary.overlap_denominator === 'string' ? context.coverageSummary.overlap_denominator : 'Full saved member-grid geometry area in EPSG:5070; uncovered county area is retained.'}</p><CountySourceDetails metadata={context.sourceMetadata} />{context.warnings.map(warning => <p className="quiet" key={warning}>{warning}</p>)}</>}
  </section>;
}
