import { X } from 'lucide-react';
import type { MapFeatureInfo } from '../types/domain';
import { safeSourceUrl } from '../utils/format';

function EvidenceValue({ value }: { value: unknown }) {
  if (value === null || value === undefined) return <>Unknown</>;
  if (Array.isArray(value)) return value.length ? <ul className="feature-property-list">{value.map((item, index) => <li key={index}><EvidenceValue value={item} /></li>)}</ul> : <>None reported</>;
  if (typeof value === 'object') {
    const entries = Object.entries(value);
    return <details><summary>Evidence fields ({entries.length})</summary><dl>{entries.map(([key, item]) => <div key={key}><dt>{key.replaceAll('_', ' ')}</dt><dd><EvidenceValue value={item} /></dd></div>)}</dl></details>;
  }
  if (typeof value === 'string') {
    const url = safeSourceUrl(value); if (url) return <a href={url} target="_blank" rel="noopener noreferrer">Open source</a>;
    return <>{value || 'Unknown'}</>;
  }
  return <>{String(value)}</>;
}

export function FeatureInformation({ feature, onClose }: { feature: MapFeatureInfo; onClose: () => void }) {
  return <section className="feature-info" aria-label="Map feature information"><button className="icon-button" aria-label="Close map feature information" onClick={onClose}><X size={15} /></button><h3>{feature.title}</h3><p className={`status-badge ${feature.status.toLowerCase()}`}>{feature.status}</p>
    <dl>{Object.entries(feature.properties).map(([key, value]) => <div key={key}><dt title={key}>{key.replaceAll('_', ' ')}</dt><dd><EvidenceValue value={value} /></dd></div>)}</dl>
  </section>;
}
