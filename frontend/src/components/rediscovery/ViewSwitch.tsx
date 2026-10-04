export type AppView = 'search' | 'rediscovery';

/** Header switch between the model's search workspace and the post-hoc rediscovery check. */
export function ViewSwitch({ view, onChange }: { view: AppView; onChange: (view: AppView) => void }) {
  return <div className="rd-view-switch" role="group" aria-label="View">
    <button type="button" aria-pressed={view === 'search'} onClick={() => onChange('search')}>Search areas</button>
    <button type="button" aria-pressed={view === 'rediscovery'} onClick={() => onChange('rediscovery')}>Rediscovery check</button>
  </div>;
}

export function readView(search = window.location.search): AppView {
  return new URLSearchParams(search).get('view') === 'rediscovery' ? 'rediscovery' : 'search';
}
