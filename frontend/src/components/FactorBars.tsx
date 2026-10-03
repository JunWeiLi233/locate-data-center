import { FACTOR_LABELS, type Factor, type FactorId } from '../types/domain';
import { formatScore } from '../utils/format';
import { SourceDetails } from './SourceDetails';

export const FACTOR_ORDER: FactorId[] = ['power_carbon', 'water', 'land', 'climate', 'heat_reuse', 'community_economic'];
export function FactorBars({ factors, compact = false }: { factors: Factor[]; compact?: boolean }) {
  return <div className={`factor-bars ${compact ? 'compact' : ''}`}>
    {!compact && <p className="micro-label">Backend factor scores · 0–100 · higher is better</p>}
    {FACTOR_ORDER.map(id => {
      const factor = factors.find(value => value.id === id);
      const score = factor?.score;
      const known = typeof score === 'number' && Number.isFinite(score);
      return <div className={`factor-row ${known ? '' : 'unknown'}`} key={id} title={factor?.basis ?? 'No supported metric in this model.'}>
        <div className="factor-heading"><span>{FACTOR_LABELS[id]}</span><strong>{known ? formatScore(score) : 'Unknown'}</strong></div>
        <div className="factor-track" role="img" aria-label={`${FACTOR_LABELS[id]}: ${known ? `${formatScore(score)} out of 100, higher is better` : 'Unknown'}`}>
          {known && <div className="factor-fill" style={{ width: `${score}%` }} />}
        </div>
        {!compact && <small>{factor?.basis ?? 'Not supported by the current model.'}</small>}
        {!compact && <div className="factor-evidence"><SourceDetails sources={factor?.sources ?? []} label="Factor evidence" /></div>}
      </div>;
    })}
  </div>;
}
