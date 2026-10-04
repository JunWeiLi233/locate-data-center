export type ModelChoice = 'grid' | 'county';

/** The URL chooses the model; an absent or unsupported value keeps the grid default. */
export function modelFromUrl(search = window.location.search): ModelChoice {
  return new URLSearchParams(search).get('model') === 'county' ? 'county' : 'grid';
}

/** Clear every model-bound selection before loading the other scientific service. */
export function modelSwitchUrl(href: string, model: ModelChoice): string {
  const url = new URL(href);
  for (const key of ['run', 'scenario', 'region', 'layers', 'mw', 'load', 'opening', 'life']) url.searchParams.delete(key);
  if (model === 'county') url.searchParams.set('model', 'county'); else url.searchParams.delete('model');
  return url.href;
}

/** Reload isolates adapter caches and aborts the prior model's browser requests. */
export function switchModel(model: ModelChoice, navigate = (url: string) => window.location.assign(url)): void {
  navigate(modelSwitchUrl(window.location.href, model));
}
