import type { RunResult } from '../types/domain';

const quantity = (value: number | null | undefined) => value == null ? 'not reported' : value.toLocaleString('en-US', { maximumFractionDigits: 1 });

export function MapCoverage({ result, shownAreas, totalAreas, onLoadNationwide, onLoadParent, busy = false }: {
  result: RunResult; shownAreas: number; totalAreas: number; onLoadNationwide?: () => void; onLoadParent?: () => void; busy?: boolean;
}) {
  const analysis = result.analysis;
  const cached = analysis?.selection === 'fixed_cached_cohort';
  const global = analysis?.selection === 'national_fine_surface';
  const perRegion = analysis?.selection === 'national_fine_region_parents';
  const nationwide = analysis?.selection === 'representative_parent_cells' || perRegion;
  const resolution = analysis ? analysis.cellSizeM : result.analysisResolutionM;
  const parentTotal = global ? analysis?.nationalFineSurface?.rankedParentWindows : analysis?.shortlistedParentCells;
  const extent = analysis ? ` · ${analysis.maximumRegionExtentKm === null ? 'Region extent not reported' : `regions up to ${quantity(analysis.maximumRegionExtentKm)} km per projected axis`}` : '';
  const kind = analysis ? ` · ${cached ? 'Cached nationwide regions · Fixed coverage' : `${global ? 'Global top-window selection' : perRegion ? 'Best search window per national region' : nationwide ? 'Nationwide regional representatives' : 'Regional refinement'} · Partial coverage`}` : '';
  return <section className="map-coverage" aria-label="Map analysis coverage">
    <strong>{quantity(shownAreas)} of {quantity(totalAreas)} saved search areas match filters</strong>
    <p>{resolution == null ? 'Cell size not reported' : `${quantity(resolution / 1000)} km cells`}{extent}{kind}</p>
    {!analysis && <p>{result.scope}</p>}
    {onLoadNationwide && <div className="map-coverage-actions"><button className="text-button" disabled={busy} onClick={onLoadNationwide}>Show nationwide areas · 1 km</button></div>}
    <details className="map-coverage-context"><summary>Coverage context</summary>
      {analysis && (cached ? <p>{quantity(analysis.refinedParentCells)} cached search windows · {quantity(analysis.refinedCells)} cells evaluated.</p> : <p>{quantity(analysis.refinedParentCells)}{parentTotal == null ? '' : ` of ${quantity(parentTotal)}`} {global ? 'ranked search windows' : 'search windows'} analyzed · {quantity(analysis.refinedCells)} cells evaluated.</p>)}
      {analysis && <p>{cached ? analysis.coverageWarning ?? 'Fixed cached regions; no new nationwide search.' : global ? 'Global top-window selection can concentrate areas; other national regions may not be analyzed.' : 'Other cells remain unassessed at this resolution.'}</p>}
      {cached && analysis?.diagnosticsStatus === 'NOT_ASSESSED' && <p>Sensitivity and score ranges: not assessed in this mode.</p>}
      {analysis?.nationalFineSurface && <p>{quantity(analysis.nationalFineSurface.valuedCells)} national 1 km cells pre-scored · UNSCREENED.</p>}
      <p className="quiet">Saved search areas, not an inventory of existing data centers. Nearby markers overlap; zoom to inspect them.</p>
      {onLoadParent && <div className="map-coverage-actions"><button className="text-button" disabled={busy} onClick={onLoadParent}>Load national discovery</button></div>}
    </details>
  </section>;
}
