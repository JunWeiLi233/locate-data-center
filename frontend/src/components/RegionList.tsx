import { useState, type ReactNode } from 'react';
import { Check, Plus } from 'lucide-react';
import type { Capabilities } from '../types/domain';
import { formatScore } from '../utils/format';
import { coolingName, regionName, shortCooling, statusWord, type PlaceGroup } from '../utils/regions';

const INITIAL_ROWS = 20;

/** `children` (run coverage, display filters) sit between the heading and the rows. */
export function RegionList({ groups, total, selectedId, comparisonIds, onSelect, onCompare, coolingOptions = [], suffixes, children }: {
  groups: PlaceGroup[]; total: number; selectedId: string | null; comparisonIds: string[];
  onSelect: (id: string) => void; onCompare: (id: string) => void; coolingOptions?: Capabilities['coolingOptions'];
  /** Area numbers per place key, so repeated county names stay distinguishable. */
  suffixes?: Map<string, string>; children?: ReactNode;
}) {
  const ranked = groups.some(group => group.primary.rank !== null);
  const [expanded, setExpanded] = useState(false);
  const selectedIndex = groups.findIndex(group => group.alternatives.some(region => region.id === selectedId));
  const shown = expanded ? groups.length : Math.max(INITIAL_ROWS, selectedIndex + 1);
  return <section className="results-list" aria-label="Potential regions">
    <div className="section-heading"><h2>Search areas</h2><span className="count-tag">{groups.length === total ? `${total.toLocaleString('en-US')} ${total === 1 ? 'area' : 'areas'}` : `${groups.length.toLocaleString('en-US')} of ${total.toLocaleString('en-US')} areas`}</span></div>
    {children}
    {!groups.length && total > 0 && <div className="empty-mini">No areas match the filters. The model results have not changed.</div>}
    {ranked && groups.length > 0 && <p className="rank-basis list-rank-basis">Areas are listed by their best alternative; # is its rank among all evaluated 1 km alternatives, so numbers can skip.</p>}
    <ol className="place-list">{groups.slice(0, shown).map(({ key, primary: region, alternatives }) => {
      const name = regionName(region) + (suffixes?.get(key) ?? '');
      const cooling = coolingName(region.designId, coolingOptions);
      const selected = alternatives.some(item => item.id === selectedId);
      const compared = comparisonIds.includes(region.id);
      return <li className={`place-row ${selected ? 'selected' : ''}`} key={key}>
        <button className="region-select" aria-label={`Select ${name}, ${cooling}`} aria-pressed={selected} onClick={() => onSelect(selected && selectedId ? selectedId : region.id)}>
          <span className="place-rank">{region.rank === null ? '—' : `#${region.rank}`}</span>
          <span className="place-name"><strong>{name}</strong><small>{shortCooling(cooling)}</small></span>
          <span className="place-score"><strong>{region.modelKind === 'monte-carlo' ? 'Tradeoff' : formatScore(region.score)}</strong><small className={`status-text ${region.screeningStatus.toLowerCase()}`}>{statusWord(region.screeningStatus)}</small></span>
        </button>
        <button className="compare-toggle" aria-label={`${compared ? 'Remove' : 'Add'} ${name}, ${cooling} ${compared ? 'from' : 'to'} comparison`} aria-pressed={compared} title={compared ? 'Remove from comparison' : 'Add to comparison'} onClick={() => onCompare(region.id)} disabled={!compared && comparisonIds.length >= 3}>{compared ? <Check size={14} /> : <Plus size={14} />}</button>
      </li>;
    })}</ol>
    {shown < groups.length && <button className="text-button show-all" onClick={() => setExpanded(true)}>Show all {groups.length} areas</button>}
  </section>;
}
