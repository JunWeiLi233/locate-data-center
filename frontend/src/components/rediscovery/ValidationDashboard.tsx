import type { CandidateClass, RediscoveryCandidate, RediscoveryResult } from '../../types/rediscovery';
import { HitRateChart } from './HitRateChart';
import { COLORS } from './overlayData';

const pct = (value: number | null | undefined, digits = 1) => value === null || value === undefined ? '—' : `${(100 * value).toFixed(digits)}%`;
export const CLASS_LABEL: Record<CandidateClass, string> = { validated: 'Validated', unresolved: 'Unresolved', emerging: 'Emerging' };
export const CLASS_COLOR: Record<CandidateClass, string> = { validated: COLORS.validated, unresolved: '#66756f', emerging: '#996221' };
export const placeName = (candidate: Pick<RediscoveryCandidate, 'placeLabel' | 'lat' | 'lon'>) => candidate.placeLabel ?? `${candidate.lat.toFixed(3)}, ${candidate.lon.toFixed(3)}`;

export function ClassMark({ value, compact = false }: { value: CandidateClass; compact?: boolean }) {
  return <span className={`rd-class rd-class--${value}`}><i aria-hidden="true" />{compact ? <span className="sr-only">{CLASS_LABEL[value]}</span> : CLASS_LABEL[value]}</span>;
}

export function ValidationDashboard({ result, topN, onTopN, selectedRank, onSelect, highlight }: {
  result: RediscoveryResult; topN: number; onTopN: (value: number) => void; selectedRank: number | null; onSelect: (rank: number) => void; highlight: string | null;
}) {
  const radii = result.parameters.hitRadiiKm;
  const counts = result.classificationCounts[String(topN)];
  const rates = new Map(result.hitRates.filter(row => row.topN === topN).map(row => [row.radiusKm, row]));
  const baseline = (control: string, radius: number) => result.baselines.find(row => row.controlId === control && row.topN === topN && row.radiusKm === radius);
  const tie = (radius: number) => result.tieSpread.find(row => row.topN === topN && row.radiusKm === radius);
  const tieTouched = result.tieBlockCandidates > 1;
  const hubRadius = radii.includes(50) ? 50 : radii[radii.length - 1];
  const hubs = result.hubRecall.find(row => row.topN === topN && row.radiusKm === hubRadius);
  const top = result.candidates.slice(0, 10);
  const section = (id: string) => `rd-section${highlight === id ? ' rd-section--active' : ''}`;
  return <div className="rd-dashboard">
    <header className={section('question')}>
      <p className="micro-label">Rediscovery check · {result.analysisName}</p>
      <h2>Model validation</h2>
      <p className="rd-lede">{result.validationFraming.split('. ')[0]}.</p>
    </header>
    <div className="rd-topn" role="group" aria-label="Candidates compared">
      <span>Top</span>{result.parameters.topNValues.map(value => <button key={value} type="button" aria-pressed={value === topN} onClick={() => onTopN(value)}>{value}</button>)}
      <span className="rd-note">kept ≥ {result.parameters.minCandidateDistanceKm} km apart</span>
    </div>
    <section className={section('hits')} aria-labelledby="rd-hit-heading">
      <h3 id="rd-hit-heading">Hit rate · within r km of an existing facility</h3>
      <table className="rd-table">
        <caption className="sr-only">Share of the Top {topN} candidates within each radius, with random-control means</caption>
        <thead><tr><th scope="col">Radius</th><th scope="col">Model</th><th scope="col">Random CONUS</th><th scope="col">Near transmission</th></tr></thead>
        <tbody>{radii.map(radius => { const row = rates.get(radius); const random = baseline('uniform_conus', radius); const plausible = baseline('infrastructure_plausible', radius);
          return <tr key={radius}><th scope="row">{radius} km</th><td className="rd-strong">{pct(row?.hitRate)}<small>{row ? ` ${row.hits}/${row.candidates}` : ''}</small></td>
            <td>{pct(random?.mean)}{random?.pValue !== null && random?.pValue !== undefined && <small title="One-sided empirical p-value"> p={random.pValue.toFixed(3)}</small>}</td>
            <td>{pct(plausible?.mean)}{plausible?.pValue !== null && plausible?.pValue !== undefined && <small title="One-sided empirical p-value"> p={plausible.pValue.toFixed(3)}</small>}</td></tr>; })}</tbody>
      </table>
      {tieTouched && <p className="rd-note">Ranks 1–{result.tieBlockCandidates} share the maximum score ({result.tieBlockCells.toLocaleString('en-US')} tied cells). Their published order follows grid_id. With a random tie order, the Top {topN} averages {pct(tie(25)?.mean ?? tie(radii[0])?.mean)} within {tie(25) ? 25 : radii[0]} km.</p>}
    </section>
    <section className={section('baseline')} aria-label="Model versus random controls">
      <h3>Model versus chance</h3>
      <HitRateChart topN={topN} radii={radii} rates={result.hitRates} baselines={result.baselines} ties={result.tieSpread} />
      <p className="rd-note">{result.parameters.draws.toLocaleString('en-US')} seeded draws per control with the same spacing. p is one-sided: (1 + draws ≥ model) / (1 + draws).</p>
    </section>
    <section className={section('overlap')} aria-label="Candidate classification">
      <h3>Classification</h3>
      {counts && <div className="rd-counts">{(['validated', 'unresolved', 'emerging'] as CandidateClass[]).map(key => <div key={key}>
        <strong style={{ color: CLASS_COLOR[key] }}>{counts[key]}</strong><ClassMark value={key} /></div>)}</div>}
      <p className="rd-note">Validated: a facility within {result.parameters.validatedMaxKm} km. Emerging: none within {result.parameters.emergingMinKm} km. An emerging candidate needs engineering, economic, regulatory and site-level due diligence; it is not shown to be suitable.</p>
    </section>
    <section className={section('surface')} aria-label="Existing facilities on the score surface">
      <h3>Where existing facilities score</h3>
      <div className="rd-stat"><strong>AUC {result.presence.auc?.toFixed(2) ?? '—'}</strong><span>chance 0.50 · median facility cell at the {result.presence.medianScorePercentile?.toFixed(0) ?? '—'}th percentile · {pct(result.presence.shareInTopQuartile, 0)} in the top quartile</span></div>
      <p className="rd-note">{result.presence.occupiedCellsValued.toLocaleString('en-US')} occupied 1 km cells against {result.model.cellsValued.toLocaleString('en-US')} valued cells. This measures agreement, not accuracy.</p>
    </section>
    {hubs && <section className={section('validated')} aria-label="Facility hubs">
      <h3>Hubs reached</h3>
      <p className="rd-stat-line"><strong>{hubs.found}</strong> of {hubs.total} facility hubs have a Top {topN} candidate within {hubRadius} km.</p>
      <details className="rd-details"><summary>Largest hubs</summary><ul className="rd-hubs">{result.hubs.slice(0, 12).map(hub => {
        const distance = hub.nearestCandidateKm[String(topN)];
        return <li key={hub.hubId}><span>{hub.label ?? hub.hubId}</span><small>{hub.facilities} records · nearest candidate {distance === null || distance === undefined ? '—' : `${distance.toFixed(0)} km`}</small></li>; })}</ul>
        <p className="rd-note">A hub is {result.parameters.hubMinFacilities}+ records linked by gaps ≤ {result.parameters.hubLinkageKm} km. It is not a market or capacity measure.</p></details>
    </section>}
    <section className={section('candidates')} aria-labelledby="rd-top-heading">
      <h3 id="rd-top-heading">Top 10 candidate locations</h3>
      <table className="rd-table rd-top">
        <colgroup><col className="rd-col-rank" /><col className="rd-col-place" /><col className="rd-col-num" /><col className="rd-col-num" /><col className="rd-col-dc" /><col className="rd-col-num" /><col className="rd-col-class" /></colgroup>
        <thead><tr><th scope="col">#</th><th scope="col">Location</th><th scope="col" title="Suitability score (0–100)">Suit.</th><th scope="col" title="Monte Carlo robustness (0–100)">Rob.</th><th scope="col">Nearest existing DC</th><th scope="col" title="Distance to the nearest existing facility">km</th><th scope="col">Class</th></tr></thead>
        <tbody>{top.map(candidate => { const dc = candidate.nearest.name ?? candidate.nearest.operator ?? 'Unnamed record'; const place = placeName(candidate);
          return <tr key={candidate.rank} className={candidate.rank === selectedRank ? 'rd-selected' : ''}>
          <th scope="row"><button type="button" className="rd-rank" onClick={() => onSelect(candidate.rank)} aria-label={`Show candidate ${candidate.rank}, ${place}`}>{candidate.rank}</button></th>
          <td title={place}>{place.replace(/ County,/, ',')}</td><td>{candidate.suitabilityScore.toFixed(1)}</td>
          <td title={candidate.robustness.missingReason ?? candidate.robustness.method ?? ''}>{candidate.robustness.score === null ? '—' : candidate.robustness.score.toFixed(0)}</td>
          <td title={`${dc}${candidate.nearest.stateAbbr ? ` (${candidate.nearest.stateAbbr})` : ''}`}>{dc}</td><td>{candidate.distanceKm.toFixed(0)}</td>
          <td title={CLASS_LABEL[candidate.classification]}><ClassMark value={candidate.classification} compact /></td></tr>; })}</tbody>
      </table>
      <p className="rd-note">Robustness “—” means no Monte Carlo evidence covers that location. It is not a low score.</p>
    </section>
    <details className={`rd-details ${section('robustness')}`}><summary>Data, method and limitations</summary>
      <dl className="rd-dl">
        <div><dt>Model run</dt><dd>{result.model.modelRun} · {result.model.profileId} · {result.model.scenarioId}{result.model.verified ? ' · scores reproduced exactly' : ''}</dd></div>
        <div><dt>Candidates</dt><dd>{result.model.screeningStatus}</dd></div>
        <div><dt>Existing facilities</dt><dd>{result.facilitySource.name}, {result.facilitySource.version} (<a href={`https://doi.org/${result.facilitySource.doi}`} target="_blank" rel="noopener noreferrer">doi:{result.facilitySource.doi}</a>), {result.facilitySource.license}. Retrieved {result.facilitySource.retrievedAt?.slice(0, 10) ?? 'unknown'}.</dd></div>
        <div><dt>Distances</dt><dd>{result.parameters.distanceMethod}</dd></div>
        <div><dt>Robustness</dt><dd>{result.robustnessProviders.map(provider => `${provider.label}: ${provider.available ? 'available' : provider.missingReason ?? 'unavailable'}`).join('; ')}</dd></div>
        <div><dt>Not scored</dt><dd>{Object.values(result.notScored).join(' ')}</dd></div>
      </dl>
      <ul className="rd-limitations">{result.limitations.map(item => <li key={item}>{item}</li>)}</ul>
      <p className="rd-note">{result.interpretation}</p>
    </details>
  </div>;
}
