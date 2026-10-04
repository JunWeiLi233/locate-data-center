/** Synthetic transport fixtures exercise the adapter; they are never location evidence. */
import { afterEach, describe, expect, it, vi } from 'vitest';
import template from '../../../backend/dataclocator/configs/monte-carlo-demo.json';
import { buildMonteCarloRequest, createMonteCarloApi, parseMonteCarloJob, presentMonteCarloRun } from './monteCarlo';
import type { FacilityConfiguration } from '../types/domain';
import { candidatePayloads } from '../map/mapData';

const runId = 'run_0123456789abcdef';

/** Construct explicit test settings rather than inferring priors from a cooling label. */
function facility(): FacilityConfiguration {
  return { peakItPowerMw: 120, averageLoadPercent: 75, targetOpeningYear: 2030, lifetimeYears: 20,
    cooling: 'shared_priors', weighting: 'equal', screeningMode: 'EXPLORATORY', groupWeights: {}, ahpMatrix: null,
    monteCarlo: { settingsJson: JSON.stringify(template), sensitivity: false, convergence: false } };
}

/** Use invented objective numbers solely to verify preservation of finite backend quantities. */
function completed() {
  const config = buildMonteCarloRequest(facility()).config;
  const distribution = { mean: 100, median: 99, p05: 80, p95: 130, cvar: 140 };
  const outcome = { candidate_id: '01089', name: 'Synthetic transport fixture', state_abbr: 'AL', expected_frontier: true, robust_frontier: true,
    pareto_frequency: .7, objectives: { lifetime_electricity_cost_usd: distribution, lifetime_operational_co2e_tonnes: distribution, lifetime_direct_water_consumption_m3: distribution } };
  return { api_version: '1.0', run_id: runId, status: 'completed', submitted_at: '2026-10-03T00:00:00Z', finished_at: '2026-10-03T00:01:00Z', error: null,
    result: { run_id: runId, status: 'completed', config, model_version: 'fixture-only', scope: 'Synthetic adapter unit fixture only', warnings: ['Fixture only'],
      scenarios: [{ scenario_id: 'price00_carbon00', assumptions: config.scenario_set[0], candidates: [outcome] }],
      excluded_candidates: [], objective_units: { lifetime_electricity_cost_usd: 'USD (2025)', lifetime_operational_co2e_tonnes: 'tonnes CO2e', lifetime_direct_water_consumption_m3: 'm3' },
      boundary_exclusions: ['Full TCO excluded'], sources: [{ source_id: 'test', publisher: 'Fixture only', source_page: 'https://example.test', data_years: [2025], geographic_scale: 'fixture' }],
      input_hashes: {}, dataset_hashes: {}, sensitivity_results: [], convergence: null } };
}

/** Mimic frozen evidence with a leading-zero FIPS and genuinely unknown feasibility. */
function detail() {
  return { api_version: '1.0', run_id: runId, candidate_id: '01089', evidence: { candidate_id: '01089', lat: 34.7, lon: -86.5,
    provenance: { electricity_price: 'test', grid_carbon: 'test' }, coverage: { fixture_only: true },
    feasibility: { power_capacity: { status: 'unverified', evidence: null }, water_allocation: { status: 'unverified', evidence: null },
      parcel_zoning: { status: 'unverified', evidence: null }, fiber_redundancy: { status: 'unverified', evidence: null } } } };
}

/** Return standards-compliant JSON from a mocked network response. */
function json(value: unknown, status = 200) {
  return new Response(JSON.stringify(value), { status, headers: { 'Content-Type': 'application/json' } });
}

afterEach(() => vi.unstubAllGlobals());

describe('county Monte Carlo adapter', () => {
  it('reports unsupported economic context explicitly without making a network request', async () => {
    const fetchMock = vi.fn(); vi.stubGlobal('fetch', fetchMock);
    await expect(createMonteCarloApi('').socioeconomic(runId, 2025)).rejects.toThrow('economic context is unavailable');
    expect(fetchMock).not.toHaveBeenCalled();
  });
  it('keeps county-applied regional price and carbon as proxies with unknown invalid inputs', () => {
    const evidence = { ...detail().evidence, electricity_price_usd_per_mwh: 100, grid_co2e_kg_per_mwh: 300, water_stress_score: 'unsupported' };
    const view = presentMonteCarloRun(parseMonteCarloJob(completed()), new Map([['01089', { ...detail(), evidence }]]));
    expect(view.regions[0].metrics.find(metric => metric.id === 'electricity_price_usd_per_mwh')).toMatchObject({ value: 100, status: 'proxy' });
    expect(view.regions[0].metrics.find(metric => metric.id === 'grid_co2e_kg_per_mwh')).toMatchObject({ value: 300, status: 'proxy' });
    expect(view.regions[0].metrics.find(metric => metric.id === 'water_stress_score')).toMatchObject({ value: null, status: 'unknown', missingReason: 'Regional input unavailable or nonnumeric' });
  });
  it('converts only workload units and preserves assumptions/seed/scenarios/audit controls', () => {
    const request = buildMonteCarloRequest(facility());
    expect(request.config).toMatchObject({ it_nameplate_mw: 120, utilization: .75, opening_year: 2030, analysis_horizon_years: 20, feasibility_mode: 'exploratory' });
    expect(request.config.cooling).toEqual(template.cooling);
    expect(request.config.scenario_set).toEqual(template.scenario_set);
    expect(request.options).toEqual({ sensitivity: false, convergence: false });
    expect(buildMonteCarloRequest({ ...facility(), screeningMode: 'STRICT' }).config.feasibility_mode).toBe('verified');
    expect(() => buildMonteCarloRequest({ ...facility(), weighting: 'ahp' })).toThrow('unsupported');
    expect(() => buildMonteCarloRequest({ ...facility(), cooling: 'all' })).toThrow('unsupported');
  });

  it('posts /runs and polls queued/running to completed before reading frozen candidate evidence', async () => {
    const done = completed();
    const fetchMock = vi.fn().mockResolvedValueOnce(json({ ...done, status: 'queued', result: null }))
      .mockResolvedValueOnce(json({ ...done, status: 'running', result: null })).mockResolvedValueOnce(json(done)).mockResolvedValueOnce(json(detail()));
    vi.stubGlobal('fetch', fetchMock);
    const progress = vi.fn();
    const api = createMonteCarloApi('http://localhost:8000', 0);
    const view = await api.search(facility(), progress);
    expect(fetchMock.mock.calls.map(call => call[0])).toEqual(['http://localhost:8000/runs', `http://localhost:8000/runs/${runId}`, `http://localhost:8000/runs/${runId}`, `http://localhost:8000/runs/${runId}/candidates/01089`]);
    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual(buildMonteCarloRequest(facility()));
    expect(progress.mock.calls.map(call => call[0].state)).toEqual(['QUEUED', 'RUNNING', 'COMPLETE']);
    expect(view.configuration).toEqual(facility());
    expect(view.modelEvidence).toEqual(done.result);
    expect(view.demo).toBe(false);
    expect(view.regions[0]).toMatchObject({ id: '01089', score: null, rank: null, geometry: null, screeningStatus: 'CONDITIONAL', paretoOptimal: true });
    expect(view.regions[0].metrics.find(metric => metric.id === 'lifetime_electricity_cost_usd_cvar')?.value).toBe(140);
    expect(view.regions[0].metrics.find(metric => metric.id === 'indirect_water')).toMatchObject({ status: 'unknown', value: null });
    expect(view.regions[0].metrics.find(metric => metric.id === 'lifetime_electricity_cost_usd_mean')?.sources[0].url).toBe('https://example.test');
    expect(view.regions[0].metrics.find(metric => metric.id === 'lifetime_direct_water_consumption_m3_mean')?.sources[0].name).toContain('WUE consumption prior');
    // Unranked county points are visible, with no invented polygon or rank-number badge.
    const map = candidatePayloads(view.regions, null);
    expect(map.areas.features).toHaveLength(0);
    expect(map.badges.features).toHaveLength(1);
    expect(map.badges.features[0].properties?.rank).toBeNull();
    await api.run(runId, 'price00_carbon00');
    expect(fetchMock).toHaveBeenCalledTimes(4);
    await expect(api.run(runId, 'not-this-scenario')).rejects.toThrow('not present');
  });

  it('handles a completed POST cache hit without polling a nonexistent job endpoint', async () => {
    const fetchMock = vi.fn().mockResolvedValueOnce(json(completed())).mockResolvedValueOnce(json(detail()));
    vi.stubGlobal('fetch', fetchMock);
    await createMonteCarloApi('', 0).search(facility());
    expect(fetchMock.mock.calls.map(call => call[0])).toEqual(['/runs', `/runs/${runId}/candidates/01089`]);
  });

  it('retains validation details, queue failures and offline errors without fixture fallback', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(json({ api_version: '1.0', error: { message: 'Invalid settings', details: [{ field: 'config', message: 'PUE is invalid' }] } }, 422)));
    await expect(createMonteCarloApi('').search(facility())).rejects.toThrow('config: PUE is invalid');
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(json({ error: { message: 'Queue is full' } }, 503)));
    await expect(createMonteCarloApi('').search(facility())).rejects.toThrow('Queue is full');
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Network error')));
    await expect(createMonteCarloApi('').search(facility())).rejects.toThrow('County API unavailable');
  });

  it('reports failed jobs, invalid envelopes and evidence mismatches explicitly', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(json({ ...completed(), status: 'failed', result: null, error: { message: 'Run interrupted; retry' } })));
    await expect(createMonteCarloApi('').search(facility())).rejects.toThrow('Run interrupted');
    expect(() => parseMonteCarloJob({ ...completed(), api_version: '2.0' })).toThrow('Unsupported');
    expect(() => parseMonteCarloJob({ ...completed(), result: null })).toThrow('completed model');
    vi.stubGlobal('fetch', vi.fn().mockResolvedValueOnce(json(completed())).mockResolvedValueOnce(json({ ...detail(), run_id: 'wrong' })));
    await expect(createMonteCarloApi('').search(facility())).rejects.toThrow('does not match');
  });

  it('treats no eligible candidates as a legitimate empty model result', () => {
    const done = completed();
    done.result.status = 'no_eligible_candidates';
    done.result.scenarios = [];
    const view = presentMonteCarloRun(parseMonteCarloJob(done), new Map());
    expect(view.state).toBe('EMPTY');
    expect(view.regions).toEqual([]);
    expect(view.warnings.join(' ')).toContain('Excluded candidates');
  });

  it('cancels browser polling and rejects unsupported layers without changing model behavior', async () => {
    const controller = new AbortController();
    controller.abort();
    vi.stubGlobal('fetch', vi.fn((_url, options) => { expect(options.signal.aborted).toBe(true); throw new DOMException('Canceled', 'AbortError'); }));
    await expect(createMonteCarloApi('').search(facility(), undefined, controller.signal)).rejects.toMatchObject({ name: 'AbortError' });
    await expect(createMonteCarloApi('').layer('water', runId, 'current')).rejects.toThrow('not mapped');
  });
});
