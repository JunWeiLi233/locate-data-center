import { Pencil } from 'lucide-react';
import type { Capabilities, FacilityConfiguration } from '../types/domain';
import { coolingName, shortCooling } from '../utils/regions';

const SCREENING = { STRICT: 'strict screening', EXPLORATORY: 'exploratory screening' } as const;
const WEIGHTING = { equal: 'equal weights', user: 'custom weights', ahp: 'AHP weights' } as const;

/** The evaluated facility in one card; Edit opens the form in place, so results stay on screen. */
export function FacilitySummary({ configuration, county, coolingOptions, saved, stale, onEdit }: {
  configuration: FacilityConfiguration; county: boolean; coolingOptions: Capabilities['coolingOptions'];
  saved: boolean; stale: boolean; onEdit: () => void;
}) {
  const c = configuration;
  const cooling = c.cooling === 'all' ? 'all cooling designs' : shortCooling(coolingName(c.cooling, coolingOptions));
  return <section className="facility-summary" aria-label="Evaluated configuration">
    <div className="facility-summary-head"><p className="micro-label">{stale ? 'Previous search' : 'Your facility'}</p>
      <button className="text-button" aria-label="Edit facility" onClick={onEdit}><Pencil size={13} aria-hidden="true" />Edit</button></div>
    <strong>{c.peakItPowerMw} MW · {c.averageLoadPercent}% load · opens {c.targetOpeningYear}</strong>
    <p>{c.lifetimeYears}-year life · {cooling} · {SCREENING[c.screeningMode]} · {county ? 'unweighted tradeoffs' : WEIGHTING[c.weighting]}</p>
    {saved && <p className="facility-summary-note">Saved results for these inputs. Edit to run your own.</p>}
  </section>;
}
