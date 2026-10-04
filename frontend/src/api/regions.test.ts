import { describe,it,expect } from 'vitest';
import { demoRun,DEMO_REGIONS } from '../mocks/data';
import { parseMetric,parseRegion,parseRunResult,parseLayer,parseJob,serializeConfiguration,parseConfiguration } from './regions';
import { formatMetric,formatScore,safeSourceUrl } from '../utils/format';
import { DEMO_DECISION_BRIEF } from '../mocks/decisionBrief';
describe('versioned model response adapter',()=>{
  it('preserves a matching backend decision brief with distinct cell and region centers',()=>{
    const run=parseRunResult({...demoRun(),schema_version:'1.3.0',decision_brief:DEMO_DECISION_BRIEF});
    expect(run.decisionBrief?.recommendation.centroid).toEqual({lat:39.325,lon:-101.5});
    expect(run.decisionBrief?.recommendation.region_centroid).toEqual({lat:40,lon:-102});
    expect(run.decisionBrief?.framework.criteria[0].contribution).toBe(12.5);
    expect(run.decisionBrief?.impact.unknowns[0].value).toBeNull();
    expect(parseRunResult(demoRun()).decisionBrief).toBeNull();
  });
  it('does not attach another run or scenario decision brief to the displayed result',()=>{
    const run=parseRunResult({...demoRun(),decision_brief:{...DEMO_DECISION_BRIEF,run_id:'OTHER'}});
    expect(run.decisionBrief).toBeNull();expect(run.decisionBriefUnavailableReason).toContain('run or scenario');
    expect(parseRunResult({...demoRun(),decision_brief:null,decision_brief_unavailable_reason:'Archived output hashes unavailable'}).decisionBriefUnavailableReason).toBe('Archived output hashes unavailable');
  });
  it('retains archived excluded-criterion reasons and decision method in a brief',()=>{
    const run=parseRunResult({...demoRun(),decision_brief:{...DEMO_DECISION_BRIEF,framework:{...DEMO_DECISION_BRIEF.framework,method:'Saved hard screening and paired physics',excluded_criteria:[{criterion:'generation_water',role:'omitted',reason:'Defensible factors unavailable; UNKNOWN.'}]}}});
    expect(run.decisionBrief?.framework.excluded_criteria).toEqual(['generation_water (omitted): Defensible factors unavailable; UNKNOWN.']);
    expect(run.decisionBrief?.framework.method).toBe('Saved hard screening and paired physics');
  });
  it('preserves a supplied total-water value and never turns UNKNOWN into a quantified benefit',()=>{
    const total={id:'total_water_consumption_m3',value:800,unit:'m3 consumed/year',status:'calculated',confidence:'low',missing_reason:null};
    const run=parseRunResult({...demoRun(),decision_brief:{...DEMO_DECISION_BRIEF,impact:{...DEMO_DECISION_BRIEF.impact,total_water_consumption:total}}});
    expect(run.decisionBrief?.impact.total_water_consumption?.value).toBe(800);
    const unknown=parseRunResult({...demoRun(),decision_brief:{...DEMO_DECISION_BRIEF,impact:{...DEMO_DECISION_BRIEF.impact,total_water_consumption:{...total,status:'unknown',missing_reason:'Generation water unavailable'}}}});
    expect(unknown.decisionBrief?.impact.total_water_consumption?.value).toBeNull();
  });
  it('preserves regional resolution, coverage and parent lineage without inferring missing caps',()=>{
    const run=parseRunResult({...demoRun(),schema_version:'1.2.0',analysis:{analysis_level:'regional',parent_run_id:'PARENT',parent_run_path:'runs/parent',cell_size_m:1000,maximum_region_extent_km:20,refined_cells:2500,national_cells:3384,shortlisted_parent_cells:690,refined_parent_cells:1,refined_area_km2:2500,shortlisted_parent_area_km2:1725000,ranking_universe:'all_evaluated_refined_alternatives'},regions:[{...DEMO_REGIONS[0],representative_grid_id:'fine_cell',parent_grid_id:'parent_cell'}]});
    expect(run.analysis?.cellSizeM).toBe(1000);expect(run.analysis?.maximumRegionExtentKm).toBe(20);expect(run.analysis?.parentRunId).toBe('PARENT');expect(run.regions[0].parentGridId).toBe('parent_cell');expect(run.regions[0].representativeGridId).toBe('fine_cell');
    expect(parseRunResult(demoRun()).analysis).toBeNull();
    expect(parseRunResult({...demoRun(),analysis:{analysis_level:'regional'}}).analysis?.maximumRegionExtentKm).toBeNull();
  });
  it('keeps actual longitude/latitude, polygons and stable IDs',()=>{const run=parseRunResult(demoRun());expect(run.regions[0].centroid).toEqual({lat:39.325,lon:-101.5});expect(run.regions[0].geometry).toEqual(DEMO_REGIONS[0].geometry);expect(run.regions[2].geometry?.type).toBe('MultiPolygon');expect(run.regions[0].id).toBe('DEMO_ALPHA');});
  it('shows missing and unknown measurements as Unknown, while preserving measured zero',()=>{const unknown=parseMetric({id:'capacity',value:90,status:'unknown',unit:'MW'});expect(unknown.value).toBeNull();expect(formatMetric(unknown)).toBe('Unknown');const measured=parseMetric({id:'water',value:0,status:'scenario',unit:'ML'});expect(formatMetric(measured)).toBe('0 ML');expect(formatScore(null)).toBe('Unknown');});
  it('does not turn raw risk or unspecified score direction into favorable scores',()=>{const r=parseRegion({...DEMO_REGIONS[0],factors:[{id:'climate',score:90,direction:'higher_is_worse'}]});expect(r.factors.find(f=>f.id==='climate')?.score).toBeNull();expect(r.factors).toHaveLength(6);});
  it('never presents FAIL as favorable or a ranked candidate',()=>{const r=parseRegion({...DEMO_REGIONS[0],screening_status:'FAIL'});expect(r.score).toBeNull();expect(r.rank).toBeNull();expect(r.factors.every(f=>f.score===null)).toBe(true);expect(r.screeningStatus).toBe('FAIL');});
  it('rejects nonfinite and out-of-range scores instead of clamping them into good values',()=>{const r=parseRegion({...DEMO_REGIONS[0],overall_score:Infinity,factors:[{id:'water',score:102,direction:'higher_is_better'}]});expect(r.score).toBeNull();expect(r.factors.find(f=>f.id==='water')?.score).toBeNull();});
  it('retains metrics for invalid geometry and does not drop other valid candidates',()=>{const bad={...DEMO_REGIONS[0],geometry:{type:'Polygon',coordinates:[[[200,39],[201,39],[201,40],[200,39]]]}};const run=parseRunResult({...demoRun(),regions:[bad,DEMO_REGIONS[1]]});expect(run.regions).toHaveLength(2);expect(run.regions[0].geometry).toBeNull();expect(run.regions[0].metrics.length).toBeGreaterThan(0);expect(run.regions[1].geometry).not.toBeNull();expect(run.state).toBe('PARTIAL');});
  it('retains polygon when centroid is missing; does not invent its navigation coordinate',()=>{const r=parseRegion({...DEMO_REGIONS[0],centroid:null});expect(r.centroid).toBeNull();expect(r.geometry).not.toBeNull();});
  it('distinguishes empty, partial and invalid responses',()=>{expect(parseRunResult({...demoRun(),regions:[]}).state).toBe('EMPTY');expect(parseRunResult(demoRun()).state).toBe('PARTIAL');expect(()=>parseRunResult({run_id:'a'})).toThrow('regions array');expect(()=>parseRunResult({...demoRun(),schema_version:'2.0.0'})).toThrow('Unsupported API schema');});
  it('does not merge duplicate region IDs or overlap designs',()=>{const run=parseRunResult({...demoRun(),regions:[DEMO_REGIONS[0],DEMO_REGIONS[1],DEMO_REGIONS[0]]});expect(run.regions.map(r=>r.id)).toEqual(['DEMO_ALPHA','DEMO_BETA']);expect(run.warnings.join(' ')).toContain('Duplicate region ID');});
  it('roundtrips model request input without calculations',()=>{const run=parseRunResult(demoRun());expect(parseConfiguration(serializeConfiguration(run.configuration))).toEqual(run.configuration);});
  it('refuses to invent a run facility configuration when absent',()=>{expect(()=>parseRunResult({...demoRun(),configuration:{}})).toThrow('no facility assumptions');});
  it('reads 1.4 place labels as presentation text and keeps malformed values null',()=>{const r=parseRegion({...DEMO_REGIONS[0],place_label:' Trinity, CA ',region_states:['WA','CA','OR'],cell_count:155,area_km2:387500});expect([r.placeLabel,r.regionStates,r.cellCount,r.areaKm2]).toEqual(['Trinity, CA',['WA','CA','OR'],155,387500]);expect(r.label).toBe('Candidate Alpha');const bad=parseRegion({...DEMO_REGIONS[0],place_label:'  ',region_states:['WA',7],cell_count:0,area_km2:-1});expect([bad.placeLabel,bad.regionStates,bad.cellCount,bad.areaKm2]).toEqual([null,null,null,null]);const legacy=parseRegion(DEMO_REGIONS[0]);expect([legacy.placeLabel,legacy.regionStates,legacy.cellCount,legacy.areaKm2]).toEqual([null,null,null,null]);});
  it('does not display invalid backend rank badges',()=>{expect(parseRegion({...DEMO_REGIONS[0],rank:-1}).rank).toBeNull();expect(parseRegion({...DEMO_REGIONS[0],rank:1.5}).rank).toBeNull();});
  it('distinguishes a corrupt nonempty response from a genuinely empty model output',()=>{expect(()=>parseRunResult({...demoRun(),regions:[{}]})).toThrow('invalid response, not an empty');expect(parseRunResult({...demoRun(),regions:[{},DEMO_REGIONS[0]]}).state).toBe('PARTIAL');});
  it('validates API major versions on optional layers and jobs as well',()=>{expect(()=>parseJob({schema_version:'2.0.0',id:'X',state:'COMPLETE'})).toThrow('Unsupported');expect(()=>parseLayer({schema_version:'2.0.0',id:'grid',data:{type:'FeatureCollection',features:[]}})).toThrow('Unsupported');});
  it('refuses national-scale unbounded GeoJSON payloads',()=>{expect(()=>parseLayer({id:'grid',data:{type:'FeatureCollection',features:Array(10001).fill({})}})).toThrow('tiled backend source');});
  it('only permits source links with safe protocols and no credentials',()=>{expect(safeSourceUrl('javascript:alert(1)')).toBeNull();expect(safeSourceUrl('https://user:secret@example.org')).toBeNull();expect(safeSourceUrl('https://www.epa.gov/egrid')).toBe('https://www.epa.gov/egrid');});
});
