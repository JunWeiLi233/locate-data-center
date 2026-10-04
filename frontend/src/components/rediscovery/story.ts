import type { MapCamera } from '../../types/domain';
import type { RediscoveryResult } from '../../types/rediscovery';
import type { LayerVisibility } from './overlayData';

/** Guided demo: every sentence is built from the loaded backend result; nothing is pre-written as a finding. */
export interface StoryStep {
  id: string; title: string; body: string; layers: LayerVisibility; camera: MapCamera | null; selectRank: number | null;
  section: 'question' | 'facilities' | 'blind' | 'surface' | 'candidates' | 'overlap' | 'hits' | 'baseline' | 'validated' | 'emerging' | 'robustness';
}
const US: MapCamera = { longitude: -96, latitude: 38.5, zoom: 3.5 };
const NONE: LayerVisibility = { facilities: false, candidates: false, validated: false, emerging: false, surface: false };
const pct = (value: number | null | undefined) => value === null || value === undefined ? '—' : `${(100 * value).toFixed(value < 0.1 && value > 0 ? 1 : 0)}%`;

export function storySteps(result: RediscoveryResult, topN: number): StoryStep[] {
  const shown = result.candidates.slice(0, topN);
  const radius = result.parameters.hitRadiiKm.includes(25) ? 25 : result.parameters.hitRadiiKm[0];
  const hit = result.hitRates.find(row => row.topN === topN && row.radiusKm === radius);
  const random = result.baselines.find(row => row.topN === topN && row.radiusKm === radius && row.controlId === 'uniform_conus');
  const plausible = result.baselines.find(row => row.topN === topN && row.radiusKm === radius && row.controlId === 'infrastructure_plausible');
  const counts = result.classificationCounts[String(topN)];
  const validated = shown.find(item => item.classification === 'validated') ?? null;
  const emerging = shown.find(item => item.classification === 'emerging') ?? null;
  const hubs = result.hubs.slice(0, 4).map(hub => hub.label).filter(Boolean).join(', ');
  const robust = shown.filter(item => item.robustness.score !== null).length;
  const allCases = shown.filter(item => item.weightCases.total > 0 && item.weightCases.retained === item.weightCases.total).length;
  const camera = (lat: number, lon: number, zoom = 7): MapCamera => ({ latitude: lat, longitude: lon, zoom });
  const place = (item: { placeLabel: string | null; lat: number; lon: number }) => item.placeLabel ?? `${item.lat.toFixed(3)}, ${item.lon.toFixed(3)}`;
  return [
    { id: 'question', section: 'question', title: 'Start with the contiguous United States', layers: NONE, camera: US, selectRank: null,
      body: result.researchQuestion },
    { id: 'facilities', section: 'facilities', title: 'Where data centers are today', layers: { ...NONE, facilities: true }, camera: US, selectRank: null,
      body: `${result.facilitySource.conusRecords.toLocaleString('en-US')} existing facility records from the ${result.facilitySource.name} (${result.facilitySource.version.split(' (')[0]}), derived from OpenStreetMap. The largest concentrations include ${hubs || 'several metropolitan hubs'}. This inventory is incomplete and is not ground truth.` },
    { id: 'blind', section: 'blind', title: 'Hide them: the model never sees these locations', layers: NONE, camera: US, selectRank: null,
      body: 'The score uses only grid carbon (EPA eGRID), basin water stress (WRI Aqueduct), mapped transmission proximity (EIA) and land cover (USGS NLCD). The candidate list was written and hashed before the facility inventory was opened.' },
    { id: 'surface', section: 'surface', title: 'The model scores every 1 km cell', layers: { ...NONE, surface: !!result.surface }, camera: US, selectRank: null,
      body: `${result.model.cellsValued.toLocaleString('en-US')} of ${result.model.cellsTotal.toLocaleString('en-US')} CONUS cells carry a score (darker means higher). The maximum, ${result.model.maxScore.toFixed(2)}, is shared by ${result.model.cellsTiedAtMaxScore.toLocaleString('en-US')} cells. The valuation is unscreened: parcel, utility, water, fiber and hazard checks remain open.` },
    { id: 'candidates', section: 'candidates', title: `Reveal the model's Top ${topN} candidates`, layers: { ...NONE, candidates: true }, camera: US, selectRank: null,
      body: `Each red point is the strongest 1 km cell in its neighbourhood. Candidates are kept at least ${result.parameters.minCandidateDistanceKm} km apart, and the first ten carry rank badges.` },
    { id: 'reveal', section: 'overlap', title: 'Reveal existing data centers again', layers: { ...NONE, candidates: true, facilities: true }, camera: US, selectRank: null,
      body: 'Blue points are existing facilities and red points are model candidates. The model chose the red points without seeing the blue ones.' },
    { id: 'overlap', section: 'overlap', title: 'Geographic overlap', layers: { ...NONE, candidates: true, facilities: true, validated: true, emerging: true }, camera: US, selectRank: null,
      body: counts ? `Of the Top ${topN}, ${counts.validated} are validated (a facility within ${result.parameters.validatedMaxKm} km, purple), ${counts.emerging} are emerging (none within ${result.parameters.emergingMinKm} km, amber) and ${counts.unresolved} are unresolved.` : 'Classification counts are unavailable.' },
    { id: 'hits', section: 'hits', title: 'Quantitative hit rate', layers: { ...NONE, candidates: true, facilities: true, validated: true, emerging: true }, camera: US, selectRank: null,
      body: hit ? `${pct(hit.hitRate)} of the Top ${topN} lie within ${radius} km of an existing facility (${hit.hits} of ${hit.candidates}). The other radii are in the panel.` : 'Hit rates are unavailable for this N.' },
    { id: 'baseline', section: 'baseline', title: 'Compared with chance', layers: { ...NONE, candidates: true, facilities: true, validated: true, emerging: true }, camera: US, selectRank: null,
      body: random ? `Random CONUS locations with the same spacing reach ${pct(random.mean)} on average (95% of draws ${pct(random.p2_5)} to ${pct(random.p97_5)}; lift ${random.lift?.toFixed(2) ?? '—'}×, one-sided p = ${random.pValue?.toFixed(3) ?? '—'}).${plausible ? ` Random near-transmission land reaches ${pct(plausible.mean)} (p = ${plausible.pValue?.toFixed(3) ?? '—'}).` : ''} Existing data-center cells sit at the ${result.presence.medianScorePercentile?.toFixed(0) ?? '—'}th score percentile (AUC ${result.presence.auc?.toFixed(2) ?? '—'}; chance is 0.50).` : 'Baselines are unavailable.' },
    { id: 'validated', section: 'validated', title: 'Locations the model rediscovered', layers: { ...NONE, candidates: true, facilities: true, validated: true }, selectRank: validated?.rank ?? null,
      camera: validated ? camera(validated.lat, validated.lon, 8) : US,
      body: validated ? `#${validated.rank} ${place(validated)} lies ${validated.distanceKm.toFixed(1)} km from ${validated.nearest.name ?? validated.nearest.operator ?? 'an existing facility'}. The model reached this area independently.` : `No Top ${topN} candidate lies within ${result.parameters.validatedMaxKm} km of an existing facility.` },
    { id: 'emerging', section: 'emerging', title: 'High-scoring areas with little existing development', layers: { ...NONE, candidates: true, facilities: true, emerging: true }, selectRank: emerging?.rank ?? null,
      camera: emerging ? camera(emerging.lat, emerging.lon, 6.5) : US,
      body: emerging ? `#${emerging.rank} ${place(emerging)} is ${emerging.distanceKm.toFixed(0)} km from the nearest known facility. It deserves engineering, economic, regulatory and site-level due diligence. It is not shown to be buildable.` : `No Top ${topN} candidate is more than ${result.parameters.emergingMinKm} km from an existing facility.` },
    { id: 'robustness', section: 'robustness', title: 'How robust are these recommendations?', layers: { ...NONE, candidates: true, facilities: true, validated: true, emerging: true }, camera: US, selectRank: null,
      body: `Monte Carlo robustness is available for ${robust} of the Top ${topN}, from the county model's cohort (county-level). The rest stay null rather than invented. ${allCases} of the Top ${topN} are retained under every one of the ${result.weightCases.length} declared weighting cases (deterministic sensitivity, not Monte Carlo).` },
  ];
}
