import type { Source } from '../types/domain';
import { safeSourceUrl } from '../utils/format';
import { ExternalLink } from 'lucide-react';

export function SourceDetails({ sources, label = 'Sources and method' }: { sources: Source[]; label?: string }) {
  return <details className="source-details"><summary>{label} <span>{sources.length ? `${sources.length} source${sources.length === 1 ? '' : 's'}` : 'Unavailable'}</span></summary>
    {!sources.length && <p>No source evidence was supplied for this value.</p>}
    {sources.map((source, index) => {
      const url = safeSourceUrl(source.url);
      return <article key={`${source.name}-${index}`}><strong>{source.name}</strong>
        <dl><dt>Dataset year / period</dt><dd>{source.datasetYear ?? 'Unknown'}</dd><dt>Geography</dt><dd>{source.geography ?? 'Unknown'}</dd><dt>Native resolution</dt><dd>{source.resolution ?? 'Unknown'}</dd><dt>Method</dt><dd>{source.method ?? 'Unknown'}</dd><dt>Scenario</dt><dd>{source.scenario ?? 'Current / not specified'}</dd></dl>
        {url ? <a href={url} target="_blank" rel="noopener noreferrer">Open authoritative source <ExternalLink size={12} aria-hidden="true" /></a> : <small>Source link unavailable or unsafe.</small>}
      </article>;
    })}
  </details>;
}
