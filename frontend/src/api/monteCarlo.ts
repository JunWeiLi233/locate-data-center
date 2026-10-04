/** Present the existing county model through the frontend's view interfaces.
 * No scoring, normalization, optimization or simulation takes place here.
 */
import template from '../../../backend/dataclocator/configs/monte-carlo-demo.json';
import type { LocatorApi } from './client';
import type { CandidateRegion, Capabilities, FacilityConfiguration, Job, Metric, RunResult, Source } from '../types/domain';
import { FACTOR_LABELS } from '../types/domain';

type Row = Record<string, unknown>;
type Config = typeof template;
interface Envelope {
  api_version: '1.0'; run_id: string; status: 'queued' | 'running' | 'completed' | 'failed';
  submitted_at: string; finished_at: string | null; result: Row | null;
  error: { message: string } | null;
}

/** Report transport/contract problems through the existing request-notice UI. */
export class MonteCarloError extends Error {
  constructor(message: string, public status = 502) { super(message); this.name = 'MonteCarloError'; }
}

/** Reject missing structured results rather than mistaking corruption for an empty set. */
function object(value: unknown, name: string): Row {
  if (!value || typeof value !== 'object' || Array.isArray(value)) throw new MonteCarloError(`Missing or invalid ${name}.`);
  return value as Row;
}

/** Require explicit finite physical values; never use zero as a missing-data fallback. */
function number(value: unknown, name: string): number {
  if (typeof value !== 'number' || !Number.isFinite(value)) throw new MonteCarloError(`Invalid ${name}.`);
  return value;
}

/** Retain null for unsupported geographic context and missing physical evidence. */
function optionalNumber(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null;
}

/** Keep explicitly supplied notes; unknown objects are not promoted to evidence. */
function strings(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === 'string') : [];
}

/** Validate the agreed version/state envelope before polling or rendering. */
export function parseMonteCarloJob(value: unknown): Envelope {
  const row = object(value, 'job envelope');
  if (row.api_version !== '1.0' || typeof row.run_id !== 'string' || !/^run_[0-9a-f]{16}$/.test(row.run_id)
      || !['queued', 'running', 'completed', 'failed'].includes(String(row.status))) {
    throw new MonteCarloError('Unsupported county-model job envelope.');
  }
  if (row.status === 'completed') object(row.result, 'completed model result');
  return row as unknown as Envelope;
}

/** Preserve the full model config; only the visible facility fields override it. */
export function buildMonteCarloRequest(facility: FacilityConfiguration) {
  if (facility.cooling !== 'shared_priors' || facility.weighting !== 'equal' || facility.ahpMatrix !== null) {
    throw new MonteCarloError('The county model supports shared PUE/WUE priors and unweighted Pareto tradeoffs; grid cooling/AHP settings are unsupported.', 422);
  }
  let config: Config;
  try {
    config = object(JSON.parse(facility.monteCarlo?.settingsJson ?? JSON.stringify(template)), 'model settings') as Config;
  } catch (error) {
    throw new MonteCarloError(`Model settings must be a complete JSON object. ${error instanceof Error ? error.message : ''}`, 422);
  }
  // Backend validation owns ranges, units and dependencies; no engineering defaults are inferred.
  return { config: { ...config, it_nameplate_mw: facility.peakItPowerMw,
    utilization: facility.averageLoadPercent / 100, opening_year: facility.targetOpeningYear,
    analysis_horizon_years: facility.lifetimeYears,
    feasibility_mode: facility.screeningMode === 'STRICT' ? 'verified' : 'exploratory' },
    options: { sensitivity: facility.monteCarlo?.sensitivity ?? true, convergence: facility.monteCarlo?.convergence ?? true } };
}

/** Translate workload units and retain the exact evaluated assumptions for saved-run editing. */
function configuration(config: Config): FacilityConfiguration {
  return { peakItPowerMw: config.it_nameplate_mw, averageLoadPercent: config.utilization * 100,
    targetOpeningYear: config.opening_year, lifetimeYears: config.analysis_horizon_years,
    cooling: 'shared_priors', weighting: 'equal', screeningMode: config.feasibility_mode === 'verified' ? 'STRICT' : 'EXPLORATORY',
    groupWeights: {}, ahpMatrix: null, monteCarlo: { settingsJson: JSON.stringify(config, null, 2), sensitivity: true, convergence: true } };
}

/** Associate every displayed physical quantity with actual source URLs/periods and assumptions. */
function sourceRecords(result: Row, evidence: Row, feature: string, scenarioId: string): Source[] {
  const provenance = object(evidence.provenance ?? {}, 'feature provenance');
  const requested = strings(Array.isArray(provenance[feature]) ? provenance[feature] : [provenance[feature]]);
  const records = Array.isArray(result.sources) ? result.sources.map(item => object(item, 'source record')) : [];
  return records.filter(source => requested.includes(String(source.source_id))).map(source => ({
    name: String(source.publisher ?? source.source_id), url: typeof source.source_page === 'string' ? source.source_page : null,
    datasetYear: Array.isArray(source.data_years) ? source.data_years.join(', ') : String(source.release ?? 'Unknown'),
    geography: String(source.geographic_scale ?? 'Unknown'), resolution: String(source.geographic_scale ?? 'Unknown'),
    method: `${String(provenance[feature])}; ${String(source.coverage_notes ?? 'See full JSON provenance')}`, scenario: scenarioId,
  }));
}

/** Attribute engineered consumption to explicit priors, never to an Aqueduct risk score. */
function priorSource(prior: Config['cooling']['pue'], name: string, scenarioId: string): Source {
  return { name: `${name}: ${prior.source}`, url: null, datasetYear: null, geography: 'Shared model assumption',
    resolution: 'All evaluated counties', method: JSON.stringify(prior), scenario: scenarioId };
}

/** Project one backend candidate without fabricating rank, polygon, score or favorable risk. */
function candidate(row: Row, evidence: Row, result: Row, scenarioId: string): CandidateRegion {
  const candidateId = String(row.candidate_id);
  if (!/^[0-9]{5}$/.test(candidateId) || evidence.candidate_id !== candidateId) throw new MonteCarloError('Candidate evidence identity mismatch.');
  const config = object(result.config, 'model configuration') as Config;
  const objectives = object(row.objectives, 'candidate objectives');
  const metrics: Metric[] = [];
  const units = object(result.objective_units, 'objective units');
  const objectiveLabels: Record<string, string> = {
    lifetime_electricity_cost_usd: 'Lifetime electricity cost (discounted; excludes full TCO)',
    lifetime_operational_co2e_tonnes: 'Lifetime operational grid carbon (undiscounted)',
    lifetime_direct_water_consumption_m3: 'Lifetime direct cooling consumption (undiscounted)',
  };
  const statistics: Record<string, string> = { mean: 'Mean', median: 'Median', p05: 'p05', p95: 'p95', cvar: `Upper-tail CVaR α=${config.cvar_alpha}` };
  const errors = object(row.monte_carlo_error ?? {}, 'Monte Carlo estimator error');
  const objectiveErrors = object(errors.objective_means ?? {}, 'objective estimator errors');
  // Show all five backend distribution summaries with their physical units, without browser math.
  for (const [id, label] of Object.entries(objectiveLabels)) {
    const summary = object(objectives[id], `${id} distribution`);
    const water = id.includes('water');
    const feature = id.includes('cost') ? 'electricity_price' : 'grid_carbon';
    const sources = water ? [priorSource(config.cooling.wue, 'WUE consumption prior', scenarioId)] :
      [...sourceRecords(result, evidence, feature, scenarioId), priorSource(config.cooling.pue, 'PUE prior', scenarioId)];
    if (water && config.cooling.wue_basis === 'facility') sources.push(priorSource(config.cooling.pue, 'Facility-energy PUE prior', scenarioId));
    const scenario = config.scenario_set.find(scenario => scenario.id === scenarioId);
    if (!water && scenario) sources.push(priorSource(id.includes('cost') ? scenario.price_growth : scenario.carbon_decline, 'Global trajectory prior; regional overrides remain explicit in full JSON', scenarioId));
    for (const [stat, statLabel] of Object.entries(statistics)) metrics.push({ id: `${id}_${stat}`, label: `${label} · ${statLabel}`,
      value: number(summary[stat], `${id}.${stat}`), unit: String(units[id]), group: 'Conditional Monte Carlo objectives',
      status: 'calculated', confidence: 'unknown', missingReason: null, sources });
    if (objectiveErrors[id]) {
      const error = object(objectiveErrors[id], 'bootstrap estimator error');
      for (const stat of ['mean_bootstrap_se', 'mean_bootstrap_p025', 'mean_bootstrap_p975']) metrics.push({ id: `${id}_${stat}`,
        label: `${label} · ${stat}`, value: number(error[stat], stat), unit: String(units[id]),
        group: 'Monte Carlo estimator error (separate from input uncertainty)', status: 'calculated', confidence: 'unknown', missingReason: null, sources });
    }
  }
  // The frequency is a conditional frontier frequency, never a calibrated site-success probability.
  metrics.push({ id: 'pareto_frequency', label: 'Conditional Pareto frequency (not probability of being best)',
    value: number(row.pareto_frequency, 'Pareto frequency'), unit: 'fraction (0–1)', group: 'Frontier evidence', status: 'calculated', confidence: 'unknown', missingReason: null, sources: [] },
    { id: 'robust_frontier', label: 'Upper-tail CVaR frontier membership', value: row.robust_frontier === true ? 'Yes' : 'No',
      unit: '', group: 'Frontier evidence', status: 'calculated', confidence: 'unknown', missingReason: null, sources: [] });
  for (const [id, label, unit, feature] of [
    ['electricity_price_usd_per_mwh', '2025 state industrial retail price proxy', 'USD/MWh', 'electricity_price'],
    ['grid_co2e_kg_per_mwh', '2023 regional grid average; utility supply unverified', 'kg CO2e/MWh', 'grid_carbon'],
    ['water_stress_score', 'Basin stress screening score (not a consumption volume)', 'index (0–5)', 'water_stress'],
  ]) metrics.push({ id, label, unit, value: optionalNumber(evidence[id]), group: 'Regional context',
    status: optionalNumber(evidence[id]) === null ? 'unknown' : 'proxy', confidence: 'unknown',
    missingReason: optionalNumber(evidence[id]) === null ? 'Regional input unavailable or nonnumeric' : null, sources: sourceRecords(result, evidence, feature, scenarioId) });
  // Hazards and station assignment remain source context, never sampled downtime or PUE curves.
  for (const [id, label, unit, feature] of [
    ['climate_station_distance_km', 'Assigned climate-normal station distance; elevation unverified', 'km', 'climate'],
    ['IFLD_RISKS', 'County inland flood risk score; not a facility event probability', 'score', 'hazards'],
    ['WFIR_RISKS', 'County wildfire risk score; not a facility event probability', 'score', 'hazards'],
    ['HWAV_RISKS', 'County heat-wave risk score; not a cooling performance model', 'score', 'hazards'],
    ['HRCN_RISKS', 'County hurricane risk score; not modeled downtime', 'score', 'hazards'],
  ]) metrics.push({ id, label, unit, value: optionalNumber(evidence[id]), group: 'Climate and hazard screening context',
    status: optionalNumber(evidence[id]) === null ? 'unknown' : 'proxy', confidence: 'unknown',
    missingReason: optionalNumber(evidence[id]) === null ? 'Context input unavailable' : null,
    sources: sourceRecords(result, evidence, feature, scenarioId) });
  const interval = Array.isArray(errors.pareto_frequency_wilson_95) ? errors.pareto_frequency_wilson_95 : [];
  for (const [index, label] of ['Wilson 95% lower', 'Wilson 95% upper'].entries()) metrics.push({
    id: `pareto_frequency_interval_${index}`, label: `Conditional Pareto frequency · ${label}`,
    value: optionalNumber(interval[index]), unit: 'fraction (0–1)', group: 'Monte Carlo estimator error (separate from input uncertainty)',
    status: optionalNumber(interval[index]) === null ? 'unknown' : 'calculated', confidence: 'unknown',
    missingReason: optionalNumber(interval[index]) === null ? 'Estimator interval unavailable or nonnumeric' : null, sources: [] });
  const feasibility = object(evidence.feasibility ?? {}, 'local feasibility');
  const required = ['power_capacity', 'water_allocation', 'parcel_zoning', 'fiber_redundancy'].flatMap(feature => {
    const entry = object(feasibility[feature] ?? {}, 'feasibility entry');
    return entry.status === 'verified' && entry.evidence ? [] : [`${feature}: ${String(entry.status ?? 'unverified')}; ${String(entry.evidence ?? 'no local evidence')}`];
  });
  for (const [id, label] of Object.entries({ embodied_carbon: 'Embodied carbon', indirect_water: 'Indirect generation water', heat_reuse: 'Heat reuse benefit', full_tco: 'Full total cost of ownership' })) {
    metrics.push({ id, label, unit: '', value: null, group: 'Missing accounting inputs', status: 'unknown', confidence: 'unknown',
      missingReason: 'Not modeled without sourced local/engineering inputs; consult boundary exclusions.', sources: [] });
  }
  const lat = optionalNumber(evidence.lat), lon = optionalNumber(evidence.lon);
  return { modelKind: 'monte-carlo', id: candidateId, label: `${String(row.name)}, ${String(row.state_abbr ?? '')}`, rank: null,
    rankBasis: 'Unweighted county Pareto tradeoff; no scalar rank or score is computed.', score: null, regionMeanScore: null,
    paretoOptimal: row.expected_frontier === true, centroid: lat !== null && lon !== null ? { lat, lon } : null,
    geometry: null, geometryWarning: 'County representative point only; no parcel or county polygon is supplied by this API.',
    screeningStatus: required.length ? 'CONDITIONAL' : 'PASS', designId: 'Shared PUE/WUE priors', scenarioId,
    factors: Object.entries(FACTOR_LABELS).map(([id, label]) => ({ id: id as keyof typeof FACTOR_LABELS, label, score: null,
      direction: 'higher_is_better', basis: 'The county model does not supply normalized favorable factor scores.', sources: [] })),
    metrics, verificationRequired: required, uncertainties: strings(result.warnings),
    strengths: [row.expected_frontier === true ? 'Member of the expected-objective frontier under this scenario.' : 'Dominated in the expected-objective comparison under this scenario.',
      row.robust_frontier === true ? 'Member of the separate upper-tail CVaR frontier.' : 'Not on the upper-tail CVaR frontier.'],
    limitations: [...strings(result.boundary_exclusions), `PUE prior: ${JSON.stringify(config.cooling.pue)}; WUE prior: ${JSON.stringify(config.cooling.wue)}`],
    dataQuality: JSON.stringify(evidence.coverage ?? {}), sensitivity: null };
}

/** Convert a completed job and its frozen candidate details into the existing panels. */
export function presentMonteCarloRun(job: Envelope, details: Map<string, Row>, selectedScenario = 'current'): RunResult {
  const result = object(job.result, 'completed model result');
  if (result.run_id !== job.run_id || !Array.isArray(result.scenarios) || !Array.isArray(result.excluded_candidates)) throw new MonteCarloError('Invalid completed result identity/schema.');
  const config = object(result.config, 'evaluated configuration') as Config;
  const scenarios = result.scenarios.map(value => object(value, 'scenario'));
  const scenario = selectedScenario === 'current' ? scenarios[0] : scenarios.find(value => value.scenario_id === selectedScenario);
  if (!scenario && scenarios.length) throw new MonteCarloError('The requested structural scenario is not present in this run.', 422);
  if (!scenario && result.status !== 'no_eligible_candidates') throw new MonteCarloError('Missing scenarios are not a valid empty result.');
  const scenarioId = String(scenario?.scenario_id ?? config.scenario_set[0].id);
  if (scenario && !Array.isArray(scenario.candidates)) throw new MonteCarloError('Scenario has no candidate result array.');
  const rows = scenario ? (scenario.candidates as unknown[]).map(value => object(value, 'candidate outcome')) : [];
  const regions = rows.map(row => {
    const detail = details.get(String(row.candidate_id));
    if (!detail) throw new MonteCarloError('Frozen candidate evidence is unavailable; outcomes cannot be safely mapped.');
    return candidate(row, object(detail.evidence, 'frozen candidate evidence'), result, scenarioId);
  });
  // Retain scenario/audit/provenance metadata verbatim as inspectable notes, not interpreted scores.
  const warnings = [...strings(result.warnings), ...strings(result.boundary_exclusions),
    `Scenario assumptions: ${JSON.stringify(scenario?.assumptions ?? config.scenario_set)}; no pooled scenario probabilities.`,
    `Excluded candidates: ${JSON.stringify(result.excluded_candidates)}`,
    `Convergence evidence: ${JSON.stringify(result.convergence ?? 'Audit not run')}`,
    `Sensitivity cases: ${JSON.stringify(Array.isArray(result.sensitivity_results) ? result.sensitivity_results.map(value => { const item = object(value, 'sensitivity case'); return { case: item.case, status: item.status, frontiers: Array.isArray(item.scenarios) ? item.scenarios.map(value => { const scenario = object(value, 'sensitivity scenario'); return { scenario_id: scenario.scenario_id, expected: scenario.expected_frontier_ids, robust: scenario.robust_frontier_ids }; }) : [] }; }) : [])}`,
    `Dataset SHA-256: ${JSON.stringify(result.dataset_hashes)}; derived-input SHA-256: ${JSON.stringify(result.input_hashes)}`];
  const facility = configuration(config);
  facility.monteCarlo!.sensitivity = Array.isArray(result.sensitivity_results) && result.sensitivity_results.length > 0;
  facility.monteCarlo!.convergence = result.convergence !== null;
  return { schemaVersion: '1.0.0', modelKind: 'monte-carlo', coverageUnit: 'counties', runId: job.run_id,
    modelEvidence: result, structuralScenarios: config.scenario_set.map(scenario => ({ id: scenario.id, label: scenario.id, year: null, pathway: null, available: true, reason: null })),
    timestamp: job.finished_at ?? job.submitted_at, modelVersion: String(result.model_version), demo: false,
    state: regions.length ? 'PARTIAL' : 'EMPTY', scope: String(result.scope),
    analyzedCellCount: regions.length + result.excluded_candidates.length, configuration: facility, scenarioId,
    regions, warnings, searchStages: [{ label: 'Eligible counties', count: regions.length }, { label: 'Excluded counties', count: result.excluded_candidates.length },
      { label: 'Draws per scenario', count: config.simulation_count }, { label: 'Separate structural scenarios', count: config.scenario_set.length }],
    weighting: null, exports: [] };
}

/** Create direct /runs transport, bounded polling and frozen-evidence presentation caches. */
export function createMonteCarloApi(baseUrl: string, pollInterval = 1000): LocatorApi {
  const base = baseUrl.replace(/\/$/, '');
  const cache = new Map<string, { job: Envelope; details: Map<string, Row>; submittedFacility?: FacilityConfiguration }>();

  /** Bound each HTTP operation, relay user cancellation and retain useful API errors. */
  async function request(path: string, options: RequestInit = {}, signal?: AbortSignal): Promise<unknown> {
    const controller = new AbortController();
    const abort = () => controller.abort();
    if (signal?.aborted) abort(); else signal?.addEventListener('abort', abort, { once: true });
    const timer = setTimeout(() => controller.abort(), 30000);
    try {
      const response = await fetch(`${base}${path}`, { ...options, signal: controller.signal,
        headers: { Accept: 'application/json', ...(options.body ? { 'Content-Type': 'application/json' } : {}) } });
      let value: unknown;
      try { value = await response.json(); } catch { throw new MonteCarloError('The county API returned invalid JSON.', response.status); }
      if (!response.ok) {
        const row = object(value, 'error response');
        const error = row.error && typeof row.error === 'object' ? row.error as Row : {};
        const details = Array.isArray(error.details) ? error.details.map(value => { const item = object(value, 'validation detail'); return `${item.field}: ${item.message}`; }).join('; ') : '';
        throw new MonteCarloError(`${String(error.message ?? (strings(row.warnings).join(' ') || `County API request failed (${response.status})`))}${details ? ` ${details}` : ''}`, response.status);
      }
      return value;
    } catch (error) {
      if (signal?.aborted) throw new DOMException('Request canceled.', 'AbortError');
      if (controller.signal.aborted) throw new MonteCarloError('County API request timed out; the job may still be running.', 408);
      if (error instanceof TypeError) throw new MonteCarloError('County API unavailable. Check its URL, startup, frozen datasets and explicit CORS origin.', 0);
      throw error;
    } finally { clearTimeout(timer); signal?.removeEventListener('abort', abort); }
  }

  /** Stop polling on navigation/unmount without pretending to cancel server computation. */
  function pause(signal?: AbortSignal): Promise<void> {
    return new Promise((resolve, reject) => {
      if (signal?.aborted) { reject(new DOMException('Request canceled.', 'AbortError')); return; }
      const abort = () => { clearTimeout(timer); reject(new DOMException('Request canceled.', 'AbortError')); };
      const timer = setTimeout(() => { signal?.removeEventListener('abort', abort); resolve(); }, pollInterval);
      signal?.addEventListener('abort', abort, { once: true });
    });
  }

  /** Read immutable per-run geographic evidence with at most four simultaneous requests. */
  async function snapshot(job: Envelope, signal?: AbortSignal) {
    const existing = cache.get(job.run_id);
    if (existing) return existing;
    const result = object(job.result, 'completed result');
    const scenarios = Array.isArray(result.scenarios) ? result.scenarios.map(value => object(value, 'scenario')) : [];
    const ids = [...new Set(scenarios.flatMap(scenario => Array.isArray(scenario.candidates) ? scenario.candidates.map(value => String(object(value, 'candidate').candidate_id)) : []))];
    if (ids.length > 50 || ids.some(id => !/^[0-9]{5}$/.test(id))) throw new MonteCarloError('Candidate cohort violates the bounded county API contract.');
    const details = new Map<string, Row>();
    let next = 0;
    await Promise.all(Array.from({ length: Math.min(4, ids.length) }, async () => {
      while (next < ids.length) {
        const id = ids[next++];
        const detail = object(await request(`/runs/${job.run_id}/candidates/${id}`, {}, signal), 'candidate snapshot');
        if (detail.run_id !== job.run_id || detail.candidate_id !== id || detail.api_version !== '1.0') throw new MonteCarloError('Candidate snapshot does not match this job.');
        details.set(id, detail);
      }
    }));
    const value: { job: Envelope; details: Map<string, Row>; submittedFacility?: FacilityConfiguration } = { job, details };
    cache.set(job.run_id, value);
    if (cache.size > 8) cache.delete(cache.keys().next().value!);
    return value;
  }

  /** Project real job states into the existing progress indicator, without fake percentages. */
  function progress(job: Envelope): Job {
    return { id: job.run_id, runId: job.run_id, state: ({ queued: 'QUEUED', running: 'RUNNING', completed: 'COMPLETE', failed: 'ERROR' } as const)[job.status],
      stage: ({ queued: 'Queued for county Monte Carlo evaluation', running: 'Computing county scenarios and requested audits', completed: 'County computation completed; reading frozen evidence', failed: 'County computation failed' })[job.status],
      error: job.error?.message ?? null };
  }

  const api: LocatorApi = {
    /** Advertise county scope and only supported controls/layers; never mimic grid-model capabilities. */
    capabilities: async signal => {
      await request('/health', {}, signal);
      const response = object(await request('/candidates', {}, signal), 'candidate response');
      if (response.api_version !== '1.0') throw new MonteCarloError('Unsupported county API version.');
      const evidence = object(response.evidence, 'candidate evidence');
      const defaultConfiguration = configuration(template);
      defaultConfiguration.screeningMode = 'STRICT';
      return { schemaVersion: '1.0.0', modelKind: 'monte-carlo', coverageUnit: 'counties', scope: String(evidence.scope), defaultConfiguration,
        coolingOptions: [{ id: 'shared_priors', label: 'Shared PUE/WUE priors — explicitly assumed' }], weightingGroups: [],
        layers: [{ id: 'candidates', label: 'County representative points', available: true, reason: null, sublayers: [] },
          ...(['grid', 'power_carbon', 'water', 'land', 'climate', 'heat_reuse', 'community_economic', 'infrastructure'] as const).map(id => ({ id, label: id,
            available: false, reason: 'No mapped layer is supplied by the county API; inspect raw regional evidence in details.', sublayers: [] }))],
        scenarios: template.scenario_set.map(scenario => ({ id: scenario.id, label: scenario.id, year: null, pathway: null, available: true, reason: null })),
        latestRunId: null, demo: false } satisfies Capabilities;
    },
    /** Submit the exact explicit config to POST /runs, then poll the same run ID to completion. */
    search: async (facility, onProgress, signal) => {
      let job = parseMonteCarloJob(await request('/runs', { method: 'POST', body: JSON.stringify(buildMonteCarloRequest(facility)) }, signal));
      const runId = job.run_id;
      const deadline = Date.now() + 45 * 60 * 1000;
      while (true) {
        onProgress?.(progress(job));
        if (job.status === 'failed') throw new MonteCarloError(job.error?.message ?? 'County model computation failed.', 500);
        if (job.status === 'completed') {
          const value = await snapshot(job, signal);
          value.submittedFacility = structuredClone(facility);
          const view = presentMonteCarloRun(job, value.details);
          // Retain the actual form submission to avoid false edited-state notices after overrides.
          view.configuration = structuredClone(facility);
          return view;
        }
        if (Date.now() >= deadline) throw new MonteCarloError(`Run ${runId} is still pending; retain this ID and poll it later.`, 408);
        await pause(signal);
        job = parseMonteCarloJob(await request(`/runs/${runId}`, {}, signal));
        if (job.run_id !== runId) throw new MonteCarloError('Polling returned a different run ID.');
      }
    },
    /** Restore a completed run or view one of its separate structural scenarios without recomputing. */
    run: async (runId, scenario = 'current', signal) => {
      if (signal?.aborted) throw new DOMException('Request canceled.', 'AbortError');
      if (!/^run_[0-9a-f]{16}$/.test(runId)) throw new MonteCarloError('Invalid county run ID.', 422);
      const cached = cache.get(runId);
      const job = cached?.job ?? parseMonteCarloJob(await request(`/runs/${runId}`, {}, signal));
      if (job.status !== 'completed') throw new MonteCarloError(job.error?.message ?? `Run ${runId} is ${job.status}; results are not yet available.`, 409);
      const value = cached ?? await snapshot(job, signal);
      const view = presentMonteCarloRun(job, value.details, scenario);
      if (value.submittedFacility) view.configuration = structuredClone(value.submittedFacility);
      return view;
    },
    /** Reject unavailable mapped layers explicitly; do not draw fabricated polygons or utilities. */
    layer: async () => { throw new MonteCarloError('This county API supplies representative points and raw evidence, not mapped indicator layers.', 422); },
  };
  return api;
}
