import type { Geometry, FeatureCollection } from 'geojson';

export type SearchState = 'IDLE' | 'LOADING' | 'SUCCESS' | 'PARTIAL' | 'ERROR' | 'EMPTY';
export type ModelId = 'grid' | 'county';
export type GridAnalysisMode = 'cached_regional' | 'full_rediscovery';
export interface AnalysisModeCapability { id: GridAnalysisMode; label: string; available: boolean; reason: string | null }
export type ScreeningStatus = 'PASS' | 'CONDITIONAL' | 'FAIL' | 'UNKNOWN';
export type ValueStatus = 'observed' | 'calculated' | 'scenario' | 'proxy' | 'unknown';
export type FactorId = 'power_carbon' | 'water' | 'land' | 'climate' | 'heat_reuse' | 'community_economic';
export type LayerId = 'candidates' | 'grid' | 'power_carbon' | 'water' | 'land' | 'climate' | 'heat_reuse' | 'community_economic' | 'infrastructure';
export interface Source {
  name: string; url: string | null; datasetYear: string | null; geography: string | null;
  resolution: string | null; method: string | null; scenario: string | null;
}
export interface Metric {
  id: string; label: string; value: number | string | null; unit: string;
  group: string; status: ValueStatus; confidence: string; missingReason: string | null; sources: Source[];
}
export interface Factor { id: FactorId; label: string; score: number | null; direction: 'higher_is_better'; basis: string; sources: Source[] }
export interface CandidateRegion {
  modelKind?: 'monte-carlo';
  id: string; label: string; rank: number | null; rankBasis: string;
  score: number | null; regionMeanScore: number | null; paretoOptimal: boolean | null;
  centroid: { lat: number; lon: number } | null; geometry: Geometry | null; geometryWarning: string | null;
  screeningStatus: ScreeningStatus; designId: string; scenarioId: string;
  representativeGridId?: string | null; parentGridId?: string | null;
  /** Presentation labels from the geography table; never suitability evidence. */
  placeLabel?: string | null; regionStates?: string[] | null; cellCount?: number | null; areaKm2?: number | null;
  factors: Factor[]; metrics: Metric[]; verificationRequired: string[]; uncertainties: string[];
  strengths: string[]; limitations: string[]; dataQuality: string;
  sensitivity: { baseRank: number | null; minRank: number | null; maxRank: number | null; drivers: string[] } | null;
}
export interface FacilityConfiguration {
  peakItPowerMw: number; averageLoadPercent: number; targetOpeningYear: number; lifetimeYears: number;
  cooling: string; weighting: 'equal' | 'user' | 'ahp'; screeningMode: 'STRICT' | 'EXPLORATORY';
  groupWeights: Record<string, number>; ahpMatrix: number[][] | null;
  /** Explicit county assumptions; validation and all model mathematics remain in the backend. */
  monteCarlo?: { settingsJson: string; sensitivity: boolean; convergence: boolean };
}
export interface LayerCapability {
  id: LayerId; label: string; available: boolean; reason: string | null;
  sublayers: { id: string; label: string; available: boolean; reason?: string }[];
}
export interface Scenario { id: string; label: string; year: number | null; pathway: string | null; available: boolean; reason: string | null }
export interface Capabilities {
  modelKind?: 'monte-carlo';
  coverageUnit?: 'counties';
  schemaVersion: string; scope: string; defaultConfiguration: FacilityConfiguration;
  coolingOptions: { id: string; label: string }[];
  weightingGroups: { id: string; label: string }[];
  layers: LayerCapability[]; scenarios: Scenario[]; latestRunId: string | null; demo: boolean;
  /** Completed 1 km nationwide regional evidence; independent of the execution default. */
  nationwideRegionalRunId?: string | null;
  analysisModes?: AnalysisModeCapability[];
  defaultAnalysisMode?: GridAnalysisMode | null;
  cachedRegionalBaselineRunId?: string | null;
}
export interface RunResult {
  modelKind?: 'monte-carlo';
  coverageUnit?: 'counties';
  modelEvidence?: Record<string, unknown>;
  structuralScenarios?: Scenario[];
  schemaVersion: string; runId: string; timestamp: string | null; modelVersion: string; demo: boolean;
  state: 'SUCCESS' | 'PARTIAL' | 'EMPTY'; scope: string; analyzedCellCount: number;
  configuration: FacilityConfiguration; scenarioId: string; regions: CandidateRegion[];
  scenarios?: Scenario[];
  analysis?: RegionalAnalysis | null;
  analysisResolutionM?: number | null;
  analysisMode?: GridAnalysisMode | null;
  warnings: string[]; searchStages: { label: string; count: number | null }[];
  weighting: { status: string; weights: Record<string, number>; consistencyRatio: number | null } | null;
  exports: { label: string; url: string }[];
  decisionBrief?: DecisionBrief | null;
  decisionBriefUnavailableReason?: string | null;
}
export interface BriefMetric {
  id: string; value: number | string | null; unit: string; status: ValueStatus;
  confidence: string; missing_reason: string | null;
}
export interface BriefAlternative {
  region_id: string | null; grid_id: string | null; design_id: string | null; scenario_id: string | null;
  rank: number | null; score: number | null; metrics: BriefMetric[];
  geographic_label?: string | null; centroid?: {lat: number; lon: number} | null;
  region_centroid?: {lat: number; lon: number} | null; region_area_km2?: number | null;
  region_cell_count?: number | null; pareto_status?: boolean | string | null;
}
export interface DecisionBrief {
  schema_version: string; run_id: string; data_mode: string; scenario_id: string;
  interpretation: string; scope: string; analyzed_cell_count: number | null; resolution_m: number | null;
  facility: {peak_it_power_mw: number | null; average_it_load_factor: number | null; target_opening_year: number | null; operating_lifetime_years: number | null; hours_in_modeled_year: number | null; basis: string; rationale: string};
  recommendation: BriefAlternative & {status: string; rationale: string}; alternatives: BriefAlternative[];
  framework: {profile_id: string; weighting_method: string; method: string; criteria: {metric_id: string; label: string; unit: string; direction: string; weight: number | null; reference_low: number | null; reference_high: number | null; role: string; basis: string; rationale: string; normalized_score: number | null; contribution: number | null}[]; excluded_criteria: string[]; missing_data_policy: string};
  evidence: {sources: {source_id: string; implemented: boolean | null; acquired: boolean | null; analyzed: boolean | null; analyzed_cells: number | null; status: string; source_url: string | null; source_version: string; data_year: string; retrieved_at: string | null}[]; assumptions: string[]; input_hashes: Record<string, unknown>};
  impact: {total_water_consumption?: BriefMetric | null; cooling_comparisons: {grid_id: string; scenario_id: string; reference_design_id: string; alternative_design_id: string; reference_minus_alternative: Record<string, number | null>; basis: string}[]; unknowns: BriefMetric[]; boundary: string};
  risks: {requirement: string; outcome: string; missing_reason: string | null; action: string}[];
  implementation_vision: {period: string; label: string; actions: string[]; evidence_gate: string}[];
  limitations: string[];
}
export interface RegionalAnalysis {
  analysisLevel: 'regional'; parentRunId: string | null; parentRunPath: string | null;
  gridDefinitionId: string | null; cellSizeM: number | null; maximumRegionExtentKm: number | null;
  refinedCells: number | null; nationalCells: number | null; shortlistedParentCells: number | null;
  refinedParentCells: number | null; refinedAreaKm2: number | null; shortlistedParentAreaKm2: number | null;
  rankingUniverse: string | null;
  selection?: 'representative_parent_cells' | 'national_fine_surface' | 'national_fine_region_parents' | 'fixed_cached_cohort' | null;
  diagnosticsStatus?: string | null;
  coverageWarning?: string | null;
  landSearchScope?: string | null;
  nationalFineSurface?: NationalFineSurface | null;
}
export interface NationalFineSurface {
  screeningStatus: 'UNSCREENED'; valuedCells: number | null; scoredAlternatives: number | null;
  alternatives: number | null; unscoredAlternatives: number | null;
  rankedParentWindows: number | null; selectionLimit: number | null;
  stageIdentity: string | null; manifest: string | null; manifestSha256: string | null;
  methodVersions: Record<string, string>;
}
export interface Job { id: string; state: 'QUEUED' | 'RUNNING' | 'COMPLETE' | 'ERROR'; stage: string; runId: string | null; error: string | null }
export interface LayerData {
  id: LayerId; data: FeatureCollection; label: string; unit: string;
  min: number | null; max: number | null; direction: 'higher_is_better' | 'higher_is_worse' | 'categorical' | 'neutral';
  source: string; warning: string | null; valueProperty: string; statusProperty: string;
  socioeconomicYear?: number | null; boundaryYear?: CountyBoundaryYear | null;
  boundarySourceKind?: string | null; sourceMetadata?: Record<string, unknown>;
}
export interface LayerSelection { id: LayerId; enabled: boolean; sublayer?: string }
export type CountyBoundaryYear = 2023 | 2025;
export interface CountyEconomicMetric {
  value: number | null; unit: string; status: ValueStatus; confidence: string; missingReason: string | null;
  method?: string | null; sourceId?: string | null; dataYear?: string | null;
  lower90?: number | null; upper90?: number | null;
}
export interface CountyEconomicRecord {
  countyGeoid: string; countyName: string; stateFips: string | null; stateName: string | null;
  boundaryYear: CountyBoundaryYear; socioeconomicYear: number | null;
  overlapAreaKm2: number | null; overlapFraction: number | null;
  povertyRatePct: number | null; medianHouseholdIncomeUsd: number | null;
  povertyRateMoePct: number | null; incomeMoeUsd: number | null;
  povertyPercentile: number | null; lowIncomePercentile: number | null;
  metrics: Record<string, CountyEconomicMetric>;
}
export interface CountyEconomicFilters {
  minimumPovertyRatePct: number | null; maximumMedianHouseholdIncomeUsd: number | null;
  minimumPovertyPercentile?: number | null; minimumLowIncomePercentile?: number | null;
}
export interface SocioeconomicContext {
  schemaVersion: string; contextSchemaVersion: string; runId: string; scenarioId: string; available: boolean;
  boundaryYear: CountyBoundaryYear; socioeconomicYear: number | null; boundarySourceKind: string | null;
  sourceMetadata: Record<string, unknown>; coverageSummary: Record<string, unknown>; warnings: string[];
  regionCounties: Record<string, CountyEconomicRecord[]>;
  fiscalContext: { localRevenue: CountyEconomicMetric; servicePressure: CountyEconomicMetric };
}
export interface MapCamera { longitude: number; latitude: number; zoom: number }
export interface MapFeatureInfo { title: string; status: string; properties: Record<string, unknown> }
export const FACTOR_LABELS: Record<FactorId, string> = {
  power_carbon: 'Power & Carbon', water: 'Water Availability', land: 'Land Impact', climate: 'Climate Risk',
  heat_reuse: 'Heat Reuse Potential', community_economic: 'Community / Economic',
};
