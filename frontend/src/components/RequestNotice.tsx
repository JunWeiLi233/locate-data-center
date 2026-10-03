import { AlertTriangle, RefreshCw } from 'lucide-react';
import type { SearchState } from '../types/domain';

export function RequestNotice({ state, stage, error, previous, onRetry }: { state: SearchState; stage: string; error: string | null; previous: boolean; onRetry: () => void }) {
  if (state !== 'LOADING' && state !== 'ERROR') return null;
  return <section className={`request-notice ${state.toLowerCase()}`} role={state === 'ERROR' ? 'alert' : 'status'} aria-live="polite" aria-label="Evaluation request">
    {state === 'LOADING' ? <><span className="loading-spinner" /><div><strong>{stage || 'Evaluating configuration'}</strong><p>{previous ? 'Previous results remain visible and are not this request’s result.' : 'Waiting for actual model output. No progress percentage is estimated.'}</p></div></> : <><AlertTriangle size={16} /><div><strong>{error ?? 'The request could not be completed.'}</strong><p>{previous ? 'Previous evaluated results are retained.' : 'Your configuration is retained.'}</p><button className="text-button" onClick={onRetry}><RefreshCw size={13} />Retry</button></div></>}
  </section>;
}
