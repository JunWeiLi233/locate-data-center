import { describe,it,expect } from 'vitest';
import { readUrlState,writeUrlState } from './url';
describe('shareable state',()=>{
  it('reads identifiers, available layer syntax and bounded map camera',()=>{const state=readUrlState('?run=R1&region=G1&scenario=bau_2050&layers=candidates,climate:flood&lon=-96&lat=30&zoom=8&mw=150');expect(state).toMatchObject({runId:'R1',regionId:'G1',scenarioId:'bau_2050',camera:{longitude:-96,latitude:30,zoom:8},configuration:{peakItPowerMw:150}});expect(state.layers[1]).toEqual({id:'climate',enabled:true,sublayer:'flood'});});
  it('does not accept invalid map coordinates or unknown layers',()=>{const state=readUrlState('?lon=999&lat=99&zoom=99&layers=fake,water');expect(state.camera).toBeUndefined();expect(state.layers.map(l=>l.id)).toEqual(['water']);});
  it('writes small state without geometry or secrets',()=>{writeUrlState({runId:'R2',regionId:'G2',scenarioId:'current',layers:[{id:'water',enabled:true}],camera:{longitude:-96,latitude:30,zoom:6}});expect(window.location.search).toContain('run=R2');expect(window.location.search).toContain('region=G2');expect(window.location.search).not.toContain('geometry');});
  it('preserves explicit all-layers-off through URL restoration',()=>{writeUrlState({layers:[{id:'candidates',enabled:false},{id:'water',enabled:false}]});expect(new URLSearchParams(window.location.search).has('layers')).toBe(true);expect(readUrlState().layers).toEqual([]);expect(readUrlState('').layers).toEqual([{id:'candidates',enabled:true}]);});
});
