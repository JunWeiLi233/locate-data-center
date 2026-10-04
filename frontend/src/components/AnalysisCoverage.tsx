import type { RegionalAnalysis } from '../types/domain';

const quantity = (value: number | null) => value === null ? 'not reported' : value.toLocaleString('en-US', { maximumFractionDigits: 1 });
const windows = (value: number | null) => `${quantity(value)} search window${value === 1 ? '' : 's'}`;

/** Coverage of a regional run in plain terms; "search window" is the national block whose 1 km cells were analyzed. */
export function AnalysisCoverage({ analysis, onLoadParent, compact = false }: { analysis: RegionalAnalysis; onLoadParent?: () => void; compact?: boolean }) {
  const perRegion = analysis.selection === 'national_fine_region_parents';
  const cached = analysis.selection === 'fixed_cached_cohort';
  const fine = perRegion || analysis.selection === 'national_fine_surface';
  const surface = analysis.nationalFineSurface;
  const chosen = perRegion ? `${windows(analysis.refinedParentCells)}, the best window of each national region`
    : `${quantity(analysis.refinedParentCells)} of ${quantity(surface?.rankedParentWindows ?? null)} ranked search windows`;
  if (compact) return <section aria-label="Regional analysis summary" className="summary-note coverage-compact">
    <strong>{analysis.cellSizeM === null ? 'Cell size not reported' : `${quantity(analysis.cellSizeM / 1000)} km cells`}</strong>
    <p>{analysis.maximumRegionExtentKm === null ? 'Region extent limit not reported' : `Regions up to ${quantity(analysis.maximumRegionExtentKm)} km per projected axis`}</p>
    {cached ? <><p>Cached nationwide regions, re-scored for this facility.</p><p>Fixed coverage: {quantity(analysis.refinedCells)} cells in {quantity(analysis.refinedParentCells)} cached search windows; no new nationwide search.</p></> : fine ? <><p>{quantity(surface?.valuedCells ?? null)} national 1 km cells pre-scored · UNSCREENED.</p>
      <p>Partial coverage: {quantity(analysis.refinedCells)} cells screened and evaluated in {chosen}. Other windows were not analyzed at 1 km.</p></>
      : <p>Partial coverage: {quantity(analysis.refinedParentCells)} of {quantity(analysis.shortlistedParentCells)} shortlisted search windows analyzed; {quantity(analysis.refinedAreaKm2)} km² evaluated. Other shortlisted areas were not analyzed at this resolution.</p>}
  </section>;
  return <section aria-label="Regional analysis coverage"><p className="micro-label">{cached ? 'Cached nationwide regions' : 'Partial regional analysis'}</p>
    <strong>{analysis.cellSizeM === null ? 'Analysis resolution not reported' : `${quantity(analysis.cellSizeM / 1000)} km analysis resolution`}</strong>
    <p>{quantity(analysis.maximumRegionExtentKm)} km maximum region span per projected axis · a declared search-area limit. Map zoom changes presentation only.</p>
    {cached ? <><p>{quantity(analysis.refinedCells)} cells re-scored in {quantity(analysis.refinedParentCells)} cached search windows for the submitted facility and decision preferences.</p>
      <p>{analysis.coverageWarning ?? 'Fixed cached nationwide regions; no new nationwide search.'}</p>
      <p>Sensitivity and score ranges: {analysis.diagnosticsStatus === 'NOT_ASSESSED' ? 'not assessed in this mode.' : analysis.diagnosticsStatus ?? 'not reported.'}</p></> : fine ? <><p>{quantity(surface?.valuedCells ?? null)} national 1 km cells pre-scored · UNSCREENED: {quantity(surface?.scoredAlternatives ?? null)} scored alternatives, {quantity(surface?.unscoredAlternatives ?? null)} without a complete value.</p>
      <p>{quantity(analysis.refinedCells)} cells screened and evaluated in {chosen}; {quantity(analysis.refinedAreaKm2)} km² analyzed.</p>
      <p>{analysis.coverageWarning ?? 'The national pre-score is unscreened; unselected windows were not analyzed at 1 km.'}</p></>
      : <><p>{quantity(analysis.refinedParentCells)} of {quantity(analysis.shortlistedParentCells)} shortlisted search windows analyzed, from {quantity(analysis.nationalCells)} national discovery cells.</p>
        <p>{quantity(analysis.refinedAreaKm2)} km² analyzed of {quantity(analysis.shortlistedParentAreaKm2)} km² shortlisted. Other shortlisted cells were not evaluated at this resolution.</p></>}
    <p>Ranks compare all evaluated {cached ? 'cached' : 'refined'} alternatives. Native source resolution remains in each metric’s provenance. No nationwide optimum at this resolution or buildable industrial parcel is established.</p>
    {analysis.parentRunId && <details><summary>National discovery lineage</summary><p>Parent run: {analysis.parentRunId}<br />Grid: {analysis.gridDefinitionId ?? 'not reported'}</p>{onLoadParent && <button className="text-button" onClick={onLoadParent}>Load national discovery</button>}</details>}
  </section>;
}
