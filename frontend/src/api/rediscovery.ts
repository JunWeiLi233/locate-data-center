import type { BaselineRow, CandidateClass, CandidateFactor, ExistingFacility, FacilityHub, HitRate, RecallRow, RediscoveryCandidate,
  RediscoveryIndex, RediscoveryResult, TieSpread } from '../types/rediscovery';

/** Read-only client for `/api/rediscovery`. The browser computes no distance, score or rate; it validates and renames. */
export const REDISCOVERY_SCHEMA = '1.0.0';
const base = (import.meta.env.VITE_API_BASE_URL ?? '').replace(/\/$/, '');
type Raw = Record<string, unknown>;

export class RediscoveryError extends Error { constructor(message: string, public status: number) { super(message); this.name = 'RediscoveryError'; } }

async function getJson(path: string, signal?: AbortSignal): Promise<unknown> {
  const controller = new AbortController();
  const abort = () => controller.abort(signal?.reason);
  if (signal?.aborted) abort(); else signal?.addEventListener('abort', abort, { once: true });
  const timeout = setTimeout(() => controller.abort(new DOMException('Rediscovery request timed out.', 'TimeoutError')), 30000);
  try {
    const response = await fetch(`${base}/api${path}`, { signal: controller.signal, headers: { Accept: 'application/json' } });
    let value: unknown;
    try { value = await response.json(); } catch { throw new RediscoveryError('The model service returned an invalid rediscovery response.', response.status); }
    if (!response.ok) {
      const message = (value as { error?: { message?: unknown } })?.error?.message;
      throw new RediscoveryError(typeof message === 'string' ? message
        : response.status === 404 ? 'The local API does not offer the rediscovery check yet. Restart it to load the new routes.' : `Rediscovery request failed (${response.status}).`, response.status);
    }
    return value;
  } catch (error) {
    if (controller.signal.aborted) {
      if (signal?.aborted) throw new DOMException('Request canceled.', 'AbortError');
      throw new RediscoveryError('Rediscovery request timed out. Retry when the service is available.', 408);
    }
    if (error instanceof TypeError) throw new RediscoveryError('Model service unavailable. Check that the local API is running.', 0);
    throw error;
  } finally { clearTimeout(timeout); signal?.removeEventListener('abort', abort); }
}

const object = (value: unknown, what: string): Raw => {
  if (!value || typeof value !== 'object' || Array.isArray(value)) throw new RediscoveryError(`Rediscovery response lacks ${what}.`, 502);
  return value as Raw;
};
const list = (value: unknown, what: string): unknown[] => { if (!Array.isArray(value)) throw new RediscoveryError(`Rediscovery response lacks ${what}.`, 502); return value; };
const num = (value: unknown): number | null => typeof value === 'number' && Number.isFinite(value) ? value : null;
const need = (value: unknown, what: string): number => { const n = num(value); if (n === null) throw new RediscoveryError(`Rediscovery response has an invalid ${what}.`, 502); return n; };
const str = (value: unknown): string | null => typeof value === 'string' ? value : null;
const strings = (value: unknown): string[] => Array.isArray(value) ? value.filter((item): item is string => typeof item === 'string') : [];
const CLASSES: CandidateClass[] = ['validated', 'unresolved', 'emerging'];

export function parseRediscoveryIndex(raw: unknown): RediscoveryIndex {
  const value = object(raw, 'an index');
  if (value.schema_version !== REDISCOVERY_SCHEMA) throw new RediscoveryError('Unsupported rediscovery index version.', 502);
  return {
    defaultAnalysisId: str(value.default_analysis_id),
    analyses: list(value.analyses, 'analyses').map(item => { const entry = object(item, 'an analysis'); return {
      analysisId: str(entry.analysis_id) ?? '', analysisName: str(entry.analysis_name), dataMode: str(entry.data_mode),
      finishedAt: str(entry.finished_at_utc), modelRun: str(entry.model_run), candidates: num(entry.candidates),
      facilitySource: str(entry.facility_source), available: entry.available === true, reason: str(entry.reason) }; }),
  };
}

function factor(raw: unknown): CandidateFactor {
  const value = object(raw, 'a factor');
  return { metricId: str(value.metric_id) ?? 'unknown', label: str(value.label) ?? '', groupId: str(value.group_id) ?? '',
    groupLabel: str(value.group_label), weight: need(value.weight, 'factor weight'), normalizedScore: num(value.normalized_score),
    contribution: num(value.contribution), nationalPercentile: num(value.national_percentile), direction: str(value.direction) ?? '',
    referenceLow: need(value.reference_low, 'reference'), referenceHigh: need(value.reference_high, 'reference'),
    rawValue: num(value.raw_value), rawUnit: str(value.raw_unit), valueStatus: str(value.value_status), confidence: str(value.confidence),
    sourceId: str(value.source_id), dataYear: str(value.data_year), role: str(value.role), locationDependent: value.location_dependent !== false,
    coverageFrac: num(value.coverage_frac) };
}

function candidate(raw: unknown): RediscoveryCandidate {
  const value = object(raw, 'a candidate');
  const nearest = object(value.nearest_existing_dc, 'a nearest facility');
  const robustness = object(value.robustness, 'robustness');
  const cases = object(value.weight_cases, 'weight cases');
  const classification = str(value.classification) as CandidateClass;
  if (!CLASSES.includes(classification)) throw new RediscoveryError('Unknown candidate classification.', 502);
  const within = object(value.existing_dc_within_km, 'facility counts');
  return {
    rank: need(value.rank, 'rank'), candidateId: str(value.candidate_id) ?? '', gridId: str(value.grid_id) ?? '',
    lat: need(value.lat, 'latitude'), lon: need(value.lon, 'longitude'), coordinateBasis: str(value.coordinate_basis) ?? '',
    placeLabel: str(value.place_label), countyName: str(value.county_name), stateAbbr: str(value.state_abbr), countyGeoid: str(value.county_geoid),
    designId: str(value.design_id) ?? '', scenarioId: str(value.scenario_id) ?? '', suitabilityScore: need(value.suitability_score, 'score'),
    scorePercentile: need(value.score_percentile, 'score percentile'), tiedCellsAtScore: need(value.tied_cells_at_score, 'tie count'),
    scoreRankMin: need(value.score_rank_min, 'score rank'), scoreRankMax: need(value.score_rank_max, 'score rank'),
    topNBucket: need(value.top_n_bucket, 'Top-N bucket'), screeningStatus: str(value.screening_status) ?? 'UNKNOWN',
    screeningNote: str(value.screening_note) ?? '', classification, distanceKm: need(value.distance_to_nearest_existing_dc_km, 'distance'),
    nearest: { facilityId: str(nearest.facility_id) ?? '', name: str(nearest.name), operator: str(nearest.operator), county: str(nearest.county),
      stateAbbr: str(nearest.state_abbr), footprintType: str(nearest.footprint_type), lat: need(nearest.lat, 'facility latitude'),
      lon: need(nearest.lon, 'facility longitude') },
    withinKm: Object.fromEntries(Object.entries(within).map(([key, count]) => [key, num(count)])),
    robustness: { score: num(robustness.score), status: str(robustness.status) ?? 'unknown', provider: str(robustness.provider),
      method: str(robustness.method), source: str(robustness.source), spatialSupport: str(robustness.spatial_support),
      missingReason: str(robustness.missing_reason),
      details: robustness.details && typeof robustness.details === 'object' ? robustness.details as Record<string, unknown> : null },
    weightCases: { retained: num(cases.retained) ?? 0, total: num(cases.total) ?? 0, retainedIds: strings(cases.retained_ids) },
    explanation: str(value.explanation) ?? '', strengths: strings(value.strengths), weaknesses: strings(value.weaknesses),
    factors: list(value.factors, 'factors').map(factor),
  };
}

const rate = (raw: unknown): HitRate => { const value = object(raw, 'a hit rate'); return { topN: need(value.top_n, 'N'), radiusKm: need(value.radius_km, 'radius'),
  hits: need(value.hits, 'hits'), candidates: need(value.candidates, 'candidates'), hitRate: need(value.hit_rate, 'hit rate') }; };
const spread = (raw: unknown): TieSpread => { const value = object(raw, 'a tie spread'); return { topN: need(value.top_n, 'N'), radiusKm: need(value.radius_km, 'radius'),
  mean: need(value.mean, 'mean'), p2_5: need(value.p2_5, 'interval'), p97_5: need(value.p97_5, 'interval') }; };
const baseline = (raw: unknown): BaselineRow => { const value = object(raw, 'a baseline'); return { controlId: str(value.control_id) ?? '',
  controlLabel: str(value.control_label) ?? '', topN: need(value.top_n, 'N'), radiusKm: need(value.radius_km, 'radius'), draws: need(value.draws, 'draws'),
  poolCells: need(value.pool_cells, 'pool'), modelHitRate: num(value.model_hit_rate), mean: need(value.mean, 'mean'), p2_5: need(value.p2_5, 'interval'),
  p97_5: need(value.p97_5, 'interval'), lift: num(value.lift), pValue: num(value.p_value_one_sided) }; };
const recall = (raw: unknown, found: string, total: string): RecallRow => { const value = object(raw, 'a recall'); return { topN: need(value.top_n, 'N'),
  radiusKm: need(value.radius_km, 'radius'), found: need(value[found], 'count'), total: need(value[total], 'total'), recall: need(value.recall, 'recall') }; };

export function parseRediscovery(raw: unknown): RediscoveryResult {
  const value = object(raw, 'a result');
  if (value.schema_version !== REDISCOVERY_SCHEMA) throw new RediscoveryError('Unsupported rediscovery result version.', 502);
  const model = object(value.model, 'model identity');
  const parameters = object(value.parameters, 'parameters');
  const classification = object(parameters.classification, 'classification thresholds');
  const hubs = object(parameters.hubs, 'hub parameters');
  const baselines = object(parameters.baselines, 'baseline parameters');
  const results = object(value.results, 'results');
  const source = object(value.facility_source, 'the facility source');
  const file = object(source.file, 'the facility file');
  const presence = object(results.presence_background, 'presence statistics');
  const overall = object(presence.baseline, 'baseline presence statistics');
  const ties = results.tie_sensitivity ? object(results.tie_sensitivity, 'tie sensitivity') : null;
  const blocks = results.tie_blocks ? object(results.tie_blocks, 'tie blocks') : null;
  const robustness = object(value.robustness, 'robustness');
  const factors = object(value.factors, 'factor definitions');
  const surface = value.surface ? object(value.surface, 'surface') : null;
  const corners = surface ? list(surface.coordinates, 'surface corners').map(point => list(point, 'a corner').map(Number) as [number, number]) : [];
  const verification = object(model.verification, 'verification');
  const reproduction = verification.persisted_parent_best_reproduction as Raw | undefined;
  const counts = object(results.classification_counts, 'classification counts');
  const candidates = list(value.candidates, 'candidates').map(candidate);
  if (candidates.some((item, index) => item.rank !== index + 1)) throw new RediscoveryError('Rediscovery candidates are not in rank order.', 502);
  return {
    analysisId: str(value.analysis_id) ?? '', analysisName: str(value.analysis_name) ?? '', dataMode: str(value.data_mode) ?? 'unknown',
    finishedAt: str(value.finished_at_utc), interpretation: str(value.interpretation) ?? '', validationFraming: str(value.validation_framing) ?? '',
    researchQuestion: str(value.research_question) ?? '',
    model: { modelRun: str(model.model_run) ?? '', profileId: str(model.profile_id) ?? '', scenarioId: str(model.scenario_id) ?? '',
      cellsValued: need(model.cells_valued, 'valued cells'), cellsTotal: need(model.cells_total, 'cells'), maxScore: need(model.max_score, 'maximum score'),
      cellsTiedAtMaxScore: need(model.cells_tied_at_max_score, 'tied cells'), screeningStatus: str(model.screening_status) ?? '',
      weights: Object.fromEntries(Object.entries(object(model.weights, 'weights')).map(([key, weight]) => [key, need(weight, 'weight')])),
      verified: num(verification.recomposed_score_max_abs_difference) === 0 || (reproduction?.status === 'verified') },
    parameters: { topNValues: list(parameters.top_n_values, 'Top-N values').map(n => need(n, 'N')),
      minCandidateDistanceKm: need(parameters.min_candidate_distance_km, 'separation'), distanceMethod: str(parameters.distance_method) ?? '',
      hitRadiiKm: list(parameters.hit_radii_km, 'radii').map(r => need(r, 'radius')),
      validatedMaxKm: need(classification.validated_max_km, 'validated threshold'), emergingMinKm: need(classification.emerging_min_km, 'emerging threshold'),
      hubLinkageKm: need(hubs.linkage_km, 'hub linkage'), hubMinFacilities: need(hubs.min_facilities, 'hub size'),
      draws: need(baselines.draws, 'draws'), seed: need(baselines.seed, 'seed') },
    facilitySource: { name: str(source.source_name) ?? '', version: str(source.version) ?? '', doi: str(source.doi) ?? '', license: str(source.license) ?? '',
      conusRecords: need(source.conus_facility_records, 'facility count'), uniqueIds: need(source.unique_osm_ids, 'facility ids'),
      retrievedAt: str(file.retrieved_at_utc), fileUrl: str(file.url), sha256: str(file.sha256), limitations: strings(source.limitations) },
    hitRates: list(results.hit_rates, 'hit rates').map(rate), tieSpread: ties ? list(ties.hit_rates, 'tie spreads').map(spread) : [],
    tieBlockCandidates: num(blocks?.candidates_in_top_score_block) ?? 0, tieBlockCells: num(blocks?.top_score_block_cells) ?? 0,
    baselines: list(results.baseline_comparison, 'baselines').map(baseline),
    presence: { auc: num(overall.auc), medianScorePercentile: num(overall.median_score_percentile), occupiedCellsValued: num(overall.occupied_cells_valued) ?? 0,
      occupiedCells: num(overall.occupied_cells) ?? 0, shareInTopQuartile: num(overall.share_in_top_quartile), shareAboveNationalMedian: num(overall.share_above_national_median) },
    presenceByCase: Object.fromEntries(Object.entries(presence).filter(([key]) => key !== 'baseline').map(([key, item]) => [key, num((item as Raw)?.auc)])),
    facilityRecall: list(results.facility_recall, 'facility recall').map(row => recall(row, 'facilities_covered', 'facilities')),
    hubRecall: list(results.hub_recall, 'hub recall').map(row => recall(row, 'hubs_rediscovered', 'hubs')), hubCount: num(results.hub_count) ?? 0,
    classificationCounts: Object.fromEntries(Object.entries(counts).map(([key, item]) => { const row = object(item, 'counts');
      return [key, { validated: need(row.validated, 'count'), unresolved: need(row.unresolved, 'count'), emerging: need(row.emerging, 'count') }]; })),
    robustnessProviders: list(robustness.providers, 'robustness providers').map(item => { const row = object(item, 'a provider'); return {
      providerId: str(row.provider_id) ?? '', label: str(row.label) ?? '', available: row.available === true, missingReason: str(row.missing_reason),
      scoreDefinition: str(row.score_definition) }; }),
    candidatesWithRobustness: num(robustness.candidates_with_score) ?? 0,
    weightCases: list(robustness.weight_cases, 'weight cases').map(item => { const row = object(item, 'a weight case'); return {
      caseId: str(row.case_id) ?? '', groupWeights: Object.fromEntries(Object.entries(object(row.group_weights, 'group weights')).map(([k, w]) => [k, Number(w)])) }; }),
    notScored: Object.fromEntries(Object.entries(object(factors.not_scored, 'unscored factors')).map(([key, reason]) => [key, String(reason)])),
    candidates,
    facilities: list(value.facilities, 'facilities').map((item): ExistingFacility => { const row = object(item, 'a facility'); return {
      facilityId: str(row.facility_id) ?? '', name: str(row.name), operator: str(row.operator), county: str(row.county), stateAbbr: str(row.state_abbr),
      lat: need(row.lat, 'facility latitude'), lon: need(row.lon, 'facility longitude'), footprintType: str(row.footprint_type),
      footprintSqft: num(row.footprint_sqft), hubId: str(row.hub_id) }; }),
    hubs: list(value.hubs, 'hubs').map((item): FacilityHub => { const row = object(item, 'a hub'); return {
      hubId: str(row.hub_id) ?? '', facilities: need(row.facilities, 'hub size'), label: str(row.label),
      centroidLat: need(row.centroid_lat, 'hub latitude'), centroidLon: need(row.centroid_lon, 'hub longitude'), states: strings(row.states),
      topOperators: strings(row.top_operators),
      nearestCandidateKm: Object.fromEntries(Object.entries(row).filter(([key]) => /^nearest_top\d+_candidate_km$/.test(key))
        .map(([key, distance]) => [key.replace(/^nearest_top(\d+)_candidate_km$/, '$1'), num(distance)])) }; }),
    surface: surface && corners.length === 4 && corners.every(corner => corner.length === 2 && corner.every(Number.isFinite)) ? {
      url: `${base}${str(surface.url) ?? ''}`, coordinates: corners as [[number, number], [number, number], [number, number], [number, number]],
      scoreLow: need(surface.score_low, 'surface low'), scoreHigh: need(surface.score_high, 'surface high'),
      inkRgb: list(surface.ink_rgb, 'surface ink').map(Number) as [number, number, number],
      opacityLow: need(surface.opacity_low, 'surface opacity'), opacityHigh: need(surface.opacity_high, 'surface opacity') } : null,
    limitations: strings(value.limitations),
  };
}

export const rediscoveryApi = {
  index: async (signal?: AbortSignal) => parseRediscoveryIndex(await getJson('/rediscovery', signal)),
  result: async (analysisId: string, signal?: AbortSignal) => parseRediscovery(await getJson(`/rediscovery/${encodeURIComponent(analysisId)}`, signal)),
};
export type RediscoveryApi = typeof rediscoveryApi;
