import { FACTOR_LABELS, type Factor, type FactorId } from '../types/domain';
import { formatScore } from '../utils/format';
import { SourceDetails } from './SourceDetails';

export const FACTOR_ORDER: FactorId[] = ['power_carbon', 'water', 'land', 'climate', 'heat_reuse', 'community_economic'];
const knownScore = (factor: Factor | undefined): factor is Factor & { score: number } => typeof factor?.score === 'number' && Number.isFinite(factor.score);

/** Backend factor scores only. Unknown factors are listed as Unknown, never drawn as empty or zero bars. */
export function FactorBars({ factors, compact = false }: { factors: Factor[]; compact?: boolean }) {
  const rows = FACTOR_ORDER.map(id => ({ id, factor: factors.find(value => value.id === id) }));
  const unknown = rows.filter(({ factor }) => !knownScore(factor));
  return <div className={`factor-bars ${compact ? 'compact' : ''}`}>
    {rows.map(({ id, factor }) => knownScore(factor) && <div className="factor-row" key={id} title={factor.basis}>
      <div className="factor-heading"><span>{FACTOR_LABELS[id]}</span><strong>{formatScore(factor.score)}</strong></div>
      <div className="factor-track" role="img" aria-label={`${FACTOR_LABELS[id]}: ${formatScore(factor.score)} out of 100, higher is better`}>
        <div className="factor-fill" style={{ width: `${factor.score}%` }} />
      </div>
    </div>)}
    {unknown.length > 0 && <p className="factor-unknown"><span>Unknown</span>{unknown.map(({ id }) => FACTOR_LABELS[id]).join(' · ')}</p>}
    {!compact && <details className="factor-method"><summary>How these scores are built</summary>
      <p className="quiet">Backend factor scores, 0–100, higher is better. The browser does not compute or re-weight them.</p>
      {rows.map(({ id, factor }) => <div className="factor-basis" key={id}><strong>{FACTOR_LABELS[id]}</strong><p>{factor?.basis ?? 'Not supported by the current model.'}</p><SourceDetails sources={factor?.sources ?? []} label="Factor evidence" /></div>)}
    </details>}
  </div>;
}
