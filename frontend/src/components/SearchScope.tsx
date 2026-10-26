import type { CachedRegionalCoverage, GridAnalysisMode } from '../types/domain';

const count = (value: number) => value.toLocaleString('en-US');
const km = (metres: number) => count(metres / 1000);

/** Start-screen card beside the map: where the chosen search depth looks, before anything is run. */
export function SearchScope({ mode, coverage, scope }: { mode: GridAnalysisMode | undefined; coverage: CachedRegionalCoverage | null | undefined; scope: string }) {
  if (mode === 'full_rediscovery') return <section className="search-scope" aria-label="Search scope">
    <p className="micro-label">Where a full search looks</p>
    <p>The whole contiguous U.S. It repeats the national search, then analyzes the windows it selects at 1 km.</p>
  </section>;
  if (!coverage) return <section className="search-scope" aria-label="Search scope">
    <p className="micro-label">Where a fast search looks</p>
    <p>{scope}</p>
  </section>;
  const windows = coverage.refinedWindows ?? coverage.windows.features.length;
  const side = coverage.windowSizeM === null ? '' : `, each ${km(coverage.windowSizeM)} × ${km(coverage.windowSizeM)} km`;
  const cells = coverage.refinedCells === null ? '' : `: ${count(coverage.refinedCells)} cells already analyzed${coverage.cellSizeM === null ? '' : ` at ${km(coverage.cellSizeM)} km`}`;
  return <section className="search-scope" aria-label="Search scope">
    <p className="micro-label">Where a fast search looks</p>
    <p><strong>{count(windows)} refined {windows === 1 ? 'window' : 'windows'}</strong>{side}{cells}.</p>
    <ul className="scope-key">
      <li><span className="scope-swatch window" aria-hidden="true" />Refined window, re-scored for your facility</li>
      <li><span className="scope-swatch unassessed" aria-hidden="true" />Not assessed at 1 km: Unknown, never zero or pass</li>
    </ul>
  </section>;
}
