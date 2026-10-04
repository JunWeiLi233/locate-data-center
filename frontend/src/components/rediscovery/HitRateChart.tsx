import { useState } from 'react';
import type { BaselineRow, HitRate, TieSpread } from '../../types/rediscovery';
import { COLORS } from './overlayData';

/**
 * Dot-and-interval comparison per radius: the model's hit rate (red dot) against the 95% range of two random
 * controls (gray bars, mean tick). A light red line shows the model's range over random tie orders. One axis
 * (share of candidates, 0–100%). Values are backend outputs; the table beside it is the accessible view.
 */
const CONTROLS = [
  { id: 'uniform_conus', color: '#898781', label: 'Random CONUS' },
  { id: 'infrastructure_plausible', color: '#52514e', label: 'Random near transmission' },
];
const pct = (value: number) => `${(100 * value).toFixed(1)}%`;

export function HitRateChart({ topN, radii, rates, baselines, ties }: { topN: number; radii: number[]; rates: HitRate[]; baselines: BaselineRow[]; ties: TieSpread[] }) {
  const [hover, setHover] = useState<number | null>(null);
  const width = 300, left = 46, right = 12, rowHeight = 30, top = 8;
  const height = top + radii.length * rowHeight + 22;
  const x = (value: number) => left + value * (width - left - right);
  return <figure className="rd-chart">
    <div className="rd-chart-legend" aria-hidden="true">
      <span><i className="rd-key-dot" style={{ background: COLORS.candidate }} />Model</span>
      {CONTROLS.map(control => <span key={control.id}><i className="rd-key-bar" style={{ background: control.color }} />{control.label}</span>)}
    </div>
    <svg viewBox={`0 0 ${width} ${height}`} width="100%" role="img" aria-label={`Hit rates of the Top ${topN} candidates against random controls; see the table for values`}>
      {[0, 0.25, 0.5, 0.75, 1].map(tick => <g key={tick}>
        <line x1={x(tick)} x2={x(tick)} y1={top - 2} y2={top + radii.length * rowHeight} stroke="#e1e0d9" strokeWidth={1} />
        <text x={x(tick)} y={height - 6} textAnchor="middle" className="rd-axis">{tick * 100}%</text>
      </g>)}
      {radii.map((radius, index) => {
        const y = top + index * rowHeight + rowHeight / 2;
        const model = rates.find(row => row.topN === topN && row.radiusKm === radius);
        const tie = ties.find(row => row.topN === topN && row.radiusKm === radius);
        const controls = CONTROLS.map(control => ({ ...control, row: baselines.find(row => row.controlId === control.id && row.topN === topN && row.radiusKm === radius) }));
        const summary = [`Within ${radius} km: model ${model ? pct(model.hitRate) : 'unavailable'}`,
          ...controls.filter(item => item.row).map(item => `${item.label} mean ${pct(item.row!.mean)} (95% ${pct(item.row!.p2_5)}–${pct(item.row!.p97_5)})`),
          ...(tie ? [`model with random tie order ${pct(tie.mean)} (${pct(tie.p2_5)}–${pct(tie.p97_5)})`] : [])].join('; ');
        return <g key={radius} onMouseEnter={() => setHover(index)} onMouseLeave={() => setHover(null)} tabIndex={0} aria-label={summary}
          onFocus={() => setHover(index)} onBlur={() => setHover(null)}>
          <title>{summary}</title>
          <rect x={0} y={y - rowHeight / 2} width={width} height={rowHeight} fill={hover === index ? '#eef3ee' : 'transparent'} />
          <text x={4} y={y + 4} className="rd-axis">≤ {radius} km</text>
          {controls.map((item, offset) => item.row && <g key={item.id}>
            <rect x={x(item.row.p2_5)} y={y - 7 + offset * 8} width={Math.max(2, x(item.row.p97_5) - x(item.row.p2_5))} height={4} rx={2} fill={item.color} opacity={0.75} />
            <rect x={x(item.row.mean) - 1} y={y - 9 + offset * 8} width={2} height={8} fill={item.color} />
          </g>)}
          {tie && <line x1={x(tie.p2_5)} x2={x(tie.p97_5)} y1={y + 9} y2={y + 9} stroke={COLORS.candidate} strokeOpacity={0.45} strokeWidth={2} strokeLinecap="round" />}
          {model && <circle cx={x(model.hitRate)} cy={y + 1} r={5} fill={COLORS.candidate} stroke="#ffffff" strokeWidth={2} />}
        </g>;
      })}
    </svg>
    <figcaption className="rd-note">Gray bars: 95% of random draws (tick = mean). Light red line: model range when tied scores are shuffled.</figcaption>
  </figure>;
}
