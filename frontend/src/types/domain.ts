import type { Geometry, FeatureCollection } from 'geojson';

export type SearchState = 'IDLE' | 'LOADING' | 'SUCCESS' | 'PARTIAL' | 'ERROR' | 'EMPTY';
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
  id: string; label: string; rank: number | null; rankBasis: string;
  score: number | null; regionMeanScore: number | null; paretoOptimal: boolean | null;
  centroid: { lat: number; lon: number } | null; geometry: Geometry | null; geometryWarning: string | null;
  screeningStatus: ScreeningStatus; designId: string; scenarioId: string;
  factors: Factor[]; metrics: Metric[]; verificationRequired: string[]; uncertainties: string[];
  strengths: string[]; limitations: string[]; dataQuality: string;
  sensitivity: { baseRank: number | null; minRank: number | null; maxRank: number | null; drivers: string[] } | null;
}
export interface FacilityConfiguration {
  peakItPowerMw: number; averageLoadPercent: number; targetOpeningYear: number; lifetimeYears: number;
  cooling: string; weighting: 'equal' | 'user' | 'ahp'; screeningMode: 'STRICT' | 'EXPLORATORY';
  groupWeights: Record<string, number>; ahpMatrix: number[][] | null;
}
export interface LayerCapability {
  id: LayerId; label: string; available: boolean; reason: string | null;
  sublayers: { id: string; label: string; available: boolean; reason?: string }[];
}
export interface Scenario { id: string; label: string; year: number | null; pathway: string | null; available: boolean; reason: string | null }
export interface Capabilities {
  schemaVersion: string; scope: string; defaultConfiguration: FacilityConfiguration;
  coolingOptions: { id: string; label: string }[];
  weightingGroups: { id: string; label: string }[];
  layers: LayerCapability[]; scenarios: Scenario[]; latestRunId: string | null; demo: boolean;
}
export interface RunResult {
  schemaVersion: string; runId: string; timestamp: string | null; modelVersion: string; demo: boolean;
  state: 'SUCCESS' | 'PARTIAL' | 'EMPTY'; scope: string; analyzedCellCount: number;
  configuration: FacilityConfiguration; scenarioId: string; regions: CandidateRegion[];
  warnings: string[]; searchStages: { label: string; count: number | null }[];
  weighting: { status: string; weights: Record<string, number>; consistencyRatio: number | null } | null;
  exports: { label: string; url: string }[];
}
export interface Job { id: string; state: 'QUEUED' | 'RUNNING' | 'COMPLETE' | 'ERROR'; stage: string; runId: string | null; error: string | null }
export interface LayerData {
  id: LayerId; data: FeatureCollection; label: string; unit: string;
  min: number | null; max: number | null; direction: 'higher_is_better' | 'higher_is_worse' | 'categorical' | 'neutral';
  source: string; warning: string | null; valueProperty: string; statusProperty: string;
}
export interface LayerSelection { id: LayerId; enabled: boolean; sublayer?: string }
export interface MapCamera { longitude: number; latitude: number; zoom: number }
export interface MapFeatureInfo { title: string; status: string; properties: Record<string, unknown> }
export const FACTOR_LABELS: Record<FactorId, string> = {
  power_carbon: 'Power & Carbon', water: 'Water Availability', land: 'Land Impact', climate: 'Climate Risk',
  heat_reuse: 'Heat Reuse Potential', community_economic: 'Community / Economic',
};
