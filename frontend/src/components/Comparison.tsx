import { X } from 'lucide-react';
import { useEffect, useRef } from 'react';
import type { CandidateRegion } from '../types/domain';
import { formatMetric, formatScore } from '../utils/format';
import { FactorBars } from './FactorBars';

export function Comparison({ regions, onClose, onRemove }: { regions: CandidateRegion[]; onClose: () => void; onRemove: (id: string) => void }) {
  const panel = useRef<HTMLElement>(null);
  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    panel.current?.querySelector<HTMLButtonElement>('button[aria-label="Close comparison"]')?.focus();
    return () => previous?.focus();
  }, []);
  const metricIds = [...new Set(regions.flatMap(region => region.metrics.map(metric => metric.id)))];
  return <section ref={panel} className="compare-panel" role="dialog" aria-modal="true" aria-label="Region comparison" onKeyDown={event => {
    if (event.key !== 'Tab') return;
    const focusable = [...(panel.current?.querySelectorAll<HTMLElement>('button:not(:disabled), a[href], summary, input, select') ?? [])].filter(element => {
      if (element.closest('[hidden], [aria-hidden="true"]')) return false;
      const closed = element.closest('details:not([open])');
      return !closed || closed.querySelector(':scope > summary') === element;
    });
    const first = focusable[0], last = focusable.at(-1);
    if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus(); }
    else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); }
  }}><header className="drawer-heading"><div><p className="micro-label">Up to three evaluated alternatives</p><h2>Compare search regions</h2></div><button className="icon-button" aria-label="Close comparison" onClick={onClose}><X size={18} /></button></header>
    <p className="compare-intro">Keep design and scenario together. Unknown values stay Unknown; no combined winner is invented.</p><div className="compare-scroll"><div className="compare-grid" style={{ gridTemplateColumns: `repeat(${regions.length}, minmax(240px, 1fr))` }}>{regions.map(region => <article key={region.id}><button className="text-button" onClick={() => onRemove(region.id)}>Remove {region.label}</button><h3>{region.label}</h3><p className="quiet">{region.designId} · {region.scenarioId}</p><strong className="compare-score">{formatScore(region.score)} / 100</strong><p>{region.screeningStatus} · {region.paretoOptimal === true ? 'Pareto frontier' : region.paretoOptimal === false ? 'Pareto dominated' : 'Pareto Unknown'}</p><p className="rank-basis">{region.rankBasis}</p><FactorBars factors={region.factors} /></article>)}</div>
      <table className="compare-table"><caption>Backend raw quantities · units and missing data retained</caption><thead><tr><th scope="col">Quantity</th>{regions.map(region => <th scope="col" key={region.id}>{region.label}<small>{region.designId}</small></th>)}</tr></thead><tbody>{metricIds.map(id => <tr key={id}><th scope="row">{regions.flatMap(region => region.metrics).find(metric => metric.id === id)?.label ?? id}</th>{regions.map(region => { const metric = region.metrics.find(value => value.id === id); return <td key={region.id}>{metric ? formatMetric(metric) : 'Unknown'}<small>{metric?.status ?? 'unknown'}{metric?.missingReason ? ` · ${metric.missingReason}` : ''}</small></td>; })}</tr>)}</tbody></table>
    </div>
  </section>;
}
