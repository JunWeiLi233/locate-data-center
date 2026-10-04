import { describe, expect, it } from 'vitest';
import { parseCapabilities } from './regions';
import { demoCapabilities } from '../mocks/data';

describe('completed nationwide regional capability', () => {
  it('retains the additive 1.7 completed run identity independently of latest run', () => {
    expect(parseCapabilities({ ...demoCapabilities, schema_version: '1.7.0', latest_run_id: 'CONCENTRATED', nationwide_regional_run_id: 'NATIONWIDE' })).toMatchObject({ latestRunId: 'CONCENTRATED', nationwideRegionalRunId: 'NATIONWIDE' });
  });
  it.each([undefined, null, '', 7])('leaves an absent or invalid completed-run identity unavailable (%s)', id => {
    expect(parseCapabilities({ ...demoCapabilities, nationwide_regional_run_id: id }).nationwideRegionalRunId).toBeNull();
  });
});
