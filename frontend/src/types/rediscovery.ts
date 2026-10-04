/** Browser types for the read-only rediscovery API (snake_case on the wire, camelCase here). */
export type CandidateClass = 'validated' | 'unresolved' | 'emerging';

export interface RediscoveryIndexEntry {
  analysisId: string; analysisName: string | null; dataMode: string | null; finishedAt: string | null;
  modelRun: string | null; candidates: number | null; facilitySource: string | null; available: boolean; reason: string | null;
}
export interface RediscoveryIndex { analyses: RediscoveryIndexEntry[]; defaultAnalysisId: string | null }

export interface CandidateFactor {
  metricId: string; label: string; groupId: string; groupLabel: string | null; weight: number;
  normalizedScore: number | null; contribution: number | null; nationalPercentile: number | null;
  direction: string; referenceLow: number; referenceHigh: number;
  rawValue: number | null; rawUnit: string | null; valueStatus: string | null; confidence: string | null;
  sourceId: string | null; dataYear: string | null; role: string | null; locationDependent: boolean; coverageFrac: number | null;
}
export interface NearestFacility {
  facilityId: string; name: string | null; operator: string | null; county: string | null; stateAbbr: string | null;
  footprintType: string | null; lat: number; lon: number;
}
export interface Robustness {
  score: number | null; status: string; provider: string | null; method: string | null; source: string | null;
  spatialSupport: string | null; missingReason: string | null; details: Record<string, unknown> | null;
}
export interface RediscoveryCandidate {
  rank: number; candidateId: string; gridId: string; lat: number; lon: number; coordinateBasis: string;
  placeLabel: string | null; countyName: string | null; stateAbbr: string | null; countyGeoid: string | null;
  designId: string; scenarioId: string; suitabilityScore: number; scorePercentile: number;
  tiedCellsAtScore: number; scoreRankMin: number; scoreRankMax: number; topNBucket: number;
  screeningStatus: string; screeningNote: string; classification: CandidateClass;
  distanceKm: number; nearest: NearestFacility; withinKm: Record<string, number | null>;
  robustness: Robustness; weightCases: { retained: number; total: number; retainedIds: string[] };
  explanation: string; strengths: string[]; weaknesses: string[]; factors: CandidateFactor[];
}
export interface ExistingFacility {
  facilityId: string; name: string | null; operator: string | null; county: string | null; stateAbbr: string | null;
  lat: number; lon: number; footprintType: string | null; footprintSqft: number | null; hubId: string | null;
}
export interface FacilityHub {
  hubId: string; facilities: number; label: string | null; centroidLat: number; centroidLon: number;
  states: string[]; topOperators: string[]; nearestCandidateKm: Record<string, number | null>;
}
export interface HitRate { topN: number; radiusKm: number; hits: number; candidates: number; hitRate: number }
export interface TieSpread { topN: number; radiusKm: number; mean: number; p2_5: number; p97_5: number }
export interface BaselineRow {
  controlId: string; controlLabel: string; topN: number; radiusKm: number; draws: number; poolCells: number;
  modelHitRate: number | null; mean: number; p2_5: number; p97_5: number; lift: number | null; pValue: number | null;
}
export interface PresenceBackground {
  auc: number | null; medianScorePercentile: number | null; occupiedCellsValued: number; occupiedCells: number;
  shareInTopQuartile: number | null; shareAboveNationalMedian: number | null;
}
export interface RecallRow { topN: number; radiusKm: number; found: number; total: number; recall: number }
export interface SurfaceImage {
  url: string; coordinates: [[number, number], [number, number], [number, number], [number, number]];
  scoreLow: number; scoreHigh: number; inkRgb: [number, number, number]; opacityLow: number; opacityHigh: number;
}
export interface FacilitySource {
  name: string; version: string; doi: string; license: string; conusRecords: number; uniqueIds: number;
  retrievedAt: string | null; fileUrl: string | null; sha256: string | null; limitations: string[];
}
export interface RediscoveryResult {
  analysisId: string; analysisName: string; dataMode: string; finishedAt: string | null;
  interpretation: string; validationFraming: string; researchQuestion: string;
  model: { modelRun: string; profileId: string; scenarioId: string; cellsValued: number; cellsTotal: number; maxScore: number;
    cellsTiedAtMaxScore: number; screeningStatus: string; weights: Record<string, number>; verified: boolean };
  parameters: { topNValues: number[]; minCandidateDistanceKm: number; distanceMethod: string; hitRadiiKm: number[];
    validatedMaxKm: number; emergingMinKm: number; hubLinkageKm: number; hubMinFacilities: number; draws: number; seed: number };
  facilitySource: FacilitySource;
  hitRates: HitRate[]; tieSpread: TieSpread[]; tieBlockCandidates: number; tieBlockCells: number;
  baselines: BaselineRow[]; presence: PresenceBackground; presenceByCase: Record<string, number | null>;
  facilityRecall: RecallRow[]; hubRecall: RecallRow[]; hubCount: number;
  classificationCounts: Record<string, Record<CandidateClass, number>>;
  robustnessProviders: { providerId: string; label: string; available: boolean; missingReason: string | null; scoreDefinition: string | null }[];
  candidatesWithRobustness: number; weightCases: { caseId: string; groupWeights: Record<string, number> }[];
  notScored: Record<string, string>;
  candidates: RediscoveryCandidate[]; facilities: ExistingFacility[]; hubs: FacilityHub[];
  surface: SurfaceImage | null; limitations: string[];
}
