import { afterEach, describe, expect, it, vi } from 'vitest';
import { modelFromUrl, modelSwitchUrl, switchModel } from './modelChoice';

afterEach(() => vi.unstubAllEnvs());

describe('runtime model selection', () => {
  it('keeps grid default despite a retired global model setting', () => {
    vi.stubEnv('VITE_MODEL_BACKEND', 'monte-carlo');
    expect(modelFromUrl('')).toBe('grid');
    expect(modelFromUrl('?model=unsupported')).toBe('grid');
    expect(modelFromUrl('?model=county')).toBe('county');
  });
  it('clears model-bound run, scenario, selection, layers and configuration in both directions', () => {
    const from = 'http://127.0.0.1:5173/?run=GRID&scenario=current&region=R1&layers=water&mw=100&load=80&opening=2030&life=25&lon=-96&lat=40&zoom=5';
    const county = new URL(modelSwitchUrl(from, 'county'));
    expect(county.searchParams.get('model')).toBe('county');
    for (const key of ['run', 'scenario', 'region', 'layers', 'mw', 'load', 'opening', 'life']) expect(county.searchParams.has(key)).toBe(false);
    expect(county.searchParams.get('lon')).toBe('-96');
    const grid = new URL(modelSwitchUrl(county.href + '&run=COUNTY&scenario=county_context&region=01089', 'grid'));
    expect(grid.searchParams.has('model')).toBe(false); expect(grid.searchParams.has('run')).toBe(false);
    expect(grid.searchParams.has('scenario')).toBe(false); expect(grid.searchParams.has('region')).toBe(false);
  });
  it('loads the selected model with a clean URL', () => {
    window.history.replaceState({}, '', '/?run=OLD&scenario=old&region=OLD');
    const navigate = vi.fn(); switchModel('county', navigate);
    expect(navigate).toHaveBeenCalledOnce();
    const next = new URL(navigate.mock.calls[0][0]);
    expect(next.searchParams.get('model')).toBe('county');
    expect(next.searchParams.has('run')).toBe(false);
  });
});
