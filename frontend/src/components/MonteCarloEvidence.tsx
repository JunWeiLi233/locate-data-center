import type { RunResult } from '../types/domain';

/** Keep the backend's complete JSON available without recalculating model evidence. */
export function MonteCarloEvidence({ result }: { result: RunResult }) {
  if (!result.modelEvidence) return null;

  /** Download the received model JSON, including all priors, provenance and audit results. */
  const download = () => {
    const url = URL.createObjectURL(new Blob([JSON.stringify(result.modelEvidence, null, 2)], { type: 'application/json' }));
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = `${result.runId}.json`;
    anchor.click();
    // Defer cleanup so the browser can consume its own generated download URL.
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  };
  return <details><summary>Full assumptions, provenance and uncertainty</summary>
    <p className="form-note">45 selected counties; representative points are screening context. Unconfirmed priors, unverified feasibility, all separate scenario results and requested audits remain in this backend record.</p>
    <button type="button" className="text-button" onClick={download}>Download full model JSON</button>
    <pre style={{ whiteSpace: 'pre-wrap', overflowWrap: 'anywhere', maxHeight: 360, overflow: 'auto' }}>{JSON.stringify(result.modelEvidence, null, 2)}</pre>
  </details>;
}
