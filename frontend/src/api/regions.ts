import type { Geometry, Position } from 'geojson';
import { FACTOR_LABELS } from '../types/domain';
import type { Capabilities, CandidateRegion, FacilityConfiguration, Factor, FactorId, Job, LayerData, LayerId, Metric, RunResult, Source } from '../types/domain';

type Row = Record<string, unknown>;
export class ApiContractError extends Error { constructor(message: string) {super(message); this.name='ApiContractError';} }
function row(value: unknown, name='response'): Row { if(!value || typeof value!=='object' || Array.isArray(value)) throw new ApiContractError(`Invalid ${name}: expected an object.`); return value as Row; }
function rows(value: unknown): unknown[] {return Array.isArray(value) ? value : [];}
function str(value: unknown, fallback=''): string {return typeof value==='string' ? value : fallback;}
function num(value: unknown): number | null {return typeof value==='number' && Number.isFinite(value) ? value : null;}
function strings(value: unknown): string[] {return rows(value).filter((v):v is string=>typeof v==='string');}
function booleanOrNull(value: unknown): boolean | null {return typeof value==='boolean' ? value : null;}
function score(value: unknown): number | null {const n=num(value);return n!==null && n>=0 && n<=100 ? n : null;}
function rank(value: unknown):number|null {const n=num(value);return n!==null&&Number.isInteger(n)&&n>0?n:null;}
function schema(value: unknown): string {const v=str(value,'1.0.0');if(!v.startsWith('1.'))throw new ApiContractError(`Unsupported API schema ${v}.`);return v;}
const layerIds: LayerId[]=['candidates','grid','power_carbon','water','land','climate','heat_reuse','community_economic','infrastructure'];

export function parseSource(value: unknown): Source {
  const s=row(value,'source'); return {name:str(s.name,'Unspecified source'),url:typeof s.url==='string'?s.url:null,datasetYear:s.dataset_year==null?null:String(s.dataset_year),geography:typeof s.geography==='string'?s.geography:null,resolution:typeof s.resolution==='string'?s.resolution:null,method:typeof s.method==='string'?s.method:null,scenario:typeof s.scenario==='string'?s.scenario:null};
}
function sources(value: unknown): Source[] {return rows(value).flatMap(v=>{try{return [parseSource(v)];}catch{return [];}});}
export function parseMetric(value: unknown): Metric {
  const m=row(value,'metric');const states=['observed','calculated','scenario','proxy','unknown'];
  const status=states.includes(str(m.status))?str(m.status) as Metric['status']:'unknown';
  const measured=status==='unknown'?null:typeof m.value==='string'?m.value:num(m.value);
  return {id:str(m.id),label:str(m.label,str(m.id,'Measurement')),value:measured,unit:str(m.unit),group:str(m.group,'Other'),status:measured===null?'unknown':status,confidence:str(m.confidence,'unknown'),missingReason:typeof m.missing_reason==='string'?m.missing_reason:measured===null?'Requires verification.':null,sources:sources(m.sources)};
}

function validPosition(p: unknown): p is Position {return Array.isArray(p)&&p.length>=2&&typeof p[0]==='number'&&typeof p[1]==='number'&&Number.isFinite(p[0])&&Number.isFinite(p[1])&&Math.abs(p[0])<=180&&Math.abs(p[1])<=90;}
function validRing(r: unknown): boolean {if(!Array.isArray(r)||r.length<4||!r.every(validPosition))return false;const a=r[0] as Position,b=r[r.length-1] as Position;return a[0]===b[0]&&a[1]===b[1];}
function validPolygon(p: unknown): boolean {return Array.isArray(p)&&p.length>0&&p.every(validRing);}
export function parseRegionGeometry(value: unknown): Geometry | null {
  if(!value||typeof value!=='object')return null;
  const g=value as Row;
  if(g.type==='Polygon'&&validPolygon(g.coordinates))return g as unknown as Geometry;
  if(g.type==='MultiPolygon'&&Array.isArray(g.coordinates)&&g.coordinates.length>0&&g.coordinates.every(validPolygon))return g as unknown as Geometry;
  return null;
}
export function parseConfiguration(value: unknown): FacilityConfiguration {
  const c=row(value,'facility configuration'); const weights:Record<string,number>={};
  const peak=num(c.peak_it_power_mw),load=num(c.average_load_percent)??(num(c.average_load_factor)!==null?(c.average_load_factor as number)*100:null),opening=num(c.target_opening_year),life=num(c.lifetime_years);
  if(peak===null||peak<=0||load===null||load<=0||load>100||opening===null||!Number.isInteger(opening)||life===null||life<=0||!Number.isInteger(life))throw new ApiContractError('Run configuration is incomplete or invalid; no facility assumptions are inferred.');
  if(c.group_weights&&typeof c.group_weights==='object')Object.entries(c.group_weights).forEach(([id,v])=>{if(num(v)!==null)weights[id]=v as number;});
  const matrix=Array.isArray(c.ahp_matrix)&&c.ahp_matrix.every(r=>Array.isArray(r)&&r.every(v=>num(v)!==null))?c.ahp_matrix as number[][]:null;
  return {peakItPowerMw:peak,averageLoadPercent:load,targetOpeningYear:opening,lifetimeYears:life,cooling:str(c.cooling,'all'),weighting:['user','ahp'].includes(str(c.weighting))?c.weighting as 'user'|'ahp':'equal',screeningMode:c.screening_mode==='STRICT'?'STRICT':'EXPLORATORY',groupWeights:weights,ahpMatrix:matrix};
}
export function serializeConfiguration(c:FacilityConfiguration): Row {return {peak_it_power_mw:c.peakItPowerMw,average_load_percent:c.averageLoadPercent,target_opening_year:c.targetOpeningYear,lifetime_years:c.lifetimeYears,cooling:c.cooling,weighting:c.weighting,screening_mode:c.screeningMode,group_weights:c.groupWeights,ahp_matrix:c.ahpMatrix};}

export function parseRegion(value: unknown): CandidateRegion {
  const r=row(value,'candidate region');const id=str(r.region_id,str(r.id));if(!id)throw new ApiContractError('Region is missing a stable ID.');
  const statuses=['PASS','CONDITIONAL','FAIL','UNKNOWN'];const screeningStatus=statuses.includes(str(r.screening_status))?r.screening_status as CandidateRegion['screeningStatus']:'UNKNOWN';
  const failed=screeningStatus==='FAIL';const geometry=parseRegionGeometry(r.geometry);
  const c=r.centroid&&typeof r.centroid==='object'?r.centroid as Row:{};const lat=num(c.lat),lon=num(c.lon);
  const centroid=lat!==null&&lon!==null&&Math.abs(lat)<=90&&Math.abs(lon)<=180?{lat,lon}:null;
  const provided=rows(r.factors).filter(v=>v&&typeof v==='object') as Row[];
  const factors: Factor[]=(Object.keys(FACTOR_LABELS) as FactorId[]).map(id=>{
    const f=provided.find(v=>v.id===id);const directionKnown=f?.direction==='higher_is_better';
    return {id,label:FACTOR_LABELS[id],score:failed||!directionKnown?null:score(f?.score),direction:'higher_is_better',basis:failed?'Hard screening failure; favorable scores are not shown.':f&&!directionKnown?'Score direction was not declared favorable by the model.':str(f?.basis,'No factor score supplied by the model.'),sources:sources(f?.sources)};
  });
  const sens=r.sensitivity&&typeof r.sensitivity==='object'?r.sensitivity as Row:null;
  const rawMetrics=Array.isArray(r.raw_metrics)?r.raw_metrics:[];
  return {id,label:str(r.label,`Candidate Region ${id}`),rank:failed?null:rank(r.rank),rankBasis:str(r.rank_basis,'Model ranking'),score:failed?null:score(r.overall_score),regionMeanScore:failed?null:score(r.region_mean_score),paretoOptimal:booleanOrNull(r.pareto_optimal),centroid,geometry,geometryWarning:geometry?null:str(r.geometry_warning,'Region geometry unavailable. Metrics can still be viewed.'),screeningStatus,designId:str(r.design_id,'Unknown'),scenarioId:str(r.scenario_id,'Unknown'),factors,metrics:rawMetrics.flatMap(v=>{try{return [parseMetric(v)];}catch{return [];}}),verificationRequired:strings(r.verification_required),uncertainties:strings(r.uncertainties),strengths:strings(r.strengths),limitations:strings(r.limitations),dataQuality:str(r.data_quality,'Unknown'),sensitivity:sens?{baseRank:rank(sens.base_rank),minRank:rank(sens.min_rank),maxRank:rank(sens.max_rank),drivers:strings(sens.drivers)}:null};
}
export function parseRunResult(value: unknown): RunResult {
  const r=row(value);const runId=str(r.run_id);if(!runId)throw new ApiContractError('Response is missing run_id.');
  if(!Array.isArray(r.regions))throw new ApiContractError('Response is missing a regions array.');
  const warnings=strings(r.warnings);const ids=new Set<string>();
  const regions=r.regions.flatMap((v,i)=>{try{const p=parseRegion(v);if(ids.has(p.id))throw new ApiContractError('Duplicate region ID.');ids.add(p.id);return [p];}catch(e){warnings.push(`Region ${i+1} could not be displayed: ${e instanceof Error?e.message:'invalid data'}`);return [];}});
  if(r.regions.length>0&&regions.length===0)throw new ApiContractError('The response contains no valid candidate records. This is an invalid response, not an empty model result.');
  const w=r.weighting&&typeof r.weighting==='object'?r.weighting as Row:null;const weights:Record<string,number>={};if(w?.weights&&typeof w.weights==='object')Object.entries(w.weights).forEach(([k,v])=>{if(num(v)!==null)weights[k]=v as number;});
  const suppliedState=str(r.state);const state=regions.length===0?'EMPTY':suppliedState==='PARTIAL'||warnings.length>0||regions.some(c=>c.screeningStatus==='UNKNOWN'||c.screeningStatus==='CONDITIONAL'||c.geometry===null)?'PARTIAL':'SUCCESS';
  return {schemaVersion:schema(r.schema_version),runId,timestamp:typeof r.timestamp==='string'?r.timestamp:null,modelVersion:str(r.model_version,'Unspecified'),demo:r.demo===true,state,scope:str(r.scope,'Analyzed coverage not specified'),analyzedCellCount:num(r.analyzed_cell_count)??0,configuration:parseConfiguration(r.configuration??r.facility??{}),scenarioId:str(r.scenario_id,'current'),regions,warnings,searchStages:rows(r.search_stages).flatMap(v=>{try{const s=row(v);return [{label:str(s.label),count:num(s.count)}];}catch{return [];}}),weighting:w?{status:str(w.status,'Unknown'),weights,consistencyRatio:num(w.consistency_ratio)}:null,exports:rows(r.exports).flatMap(v=>{try{const e=row(v);return [{label:str(e.label,'Export'),url:str(e.url)}];}catch{return [];}})};
}
export function parseCapabilities(value: unknown): Capabilities {
  const c=row(value);return {schemaVersion:schema(c.schema_version),scope:str(c.scope,'Coverage not specified'),defaultConfiguration:parseConfiguration(c.default_configuration??{}),coolingOptions:rows(c.cooling_options).map(v=>{const r=row(v);return{id:str(r.id),label:str(r.label)};}),weightingGroups:rows(c.weighting_groups).map(v=>{const r=row(v);return{id:str(r.id),label:str(r.label)};}),layers:rows(c.layers).map(v=>{const l=row(v);if(!layerIds.includes(l.id as LayerId))throw new ApiContractError('Unknown layer capability.');return{id:l.id as LayerId,label:str(l.label),available:l.available===true,reason:typeof l.reason==='string'?l.reason:null,sublayers:rows(l.sublayers).map(v=>{const s=row(v);return{id:str(s.id),label:str(s.label),available:s.available===true,reason:typeof s.reason==='string'?s.reason:undefined};})};}),scenarios:rows(c.scenarios).map(v=>{const s=row(v);return{id:str(s.id),label:str(s.label),year:num(s.year),pathway:typeof s.pathway==='string'?s.pathway:null,available:s.available===true,reason:typeof s.reason==='string'?s.reason:null};}),latestRunId:typeof c.latest_run_id==='string'?c.latest_run_id:null,demo:c.demo===true};
}
export function parseJob(value: unknown): Job {const j=row(value);schema(j.schema_version);if(!['QUEUED','RUNNING','COMPLETE','ERROR'].includes(str(j.state)))throw new ApiContractError('Invalid job state.');return{id:str(j.id),state:j.state as Job['state'],stage:str(j.stage,'Searching geographic model...'),runId:typeof j.run_id==='string'?j.run_id:null,error:typeof j.error==='string'?j.error:null};}
export function parseLayer(value: unknown): LayerData {
  const l=row(value);schema(l.schema_version);const d=row(l.data,'layer data');if(!layerIds.includes(l.id as LayerId)||d.type!=='FeatureCollection'||!Array.isArray(d.features))throw new ApiContractError('Invalid geographic layer.');
  if(d.features.length>10000)throw new ApiContractError('Layer exceeds browser GeoJSON limit. Use a simplified or tiled backend source.');
  return {id:l.id as LayerId,data:d as unknown as LayerData['data'],label:str(l.label),unit:str(l.unit),min:num(l.min),max:num(l.max),direction:['higher_is_better','higher_is_worse','categorical'].includes(str(l.direction))?l.direction as LayerData['direction']:'neutral',source:str(l.source,'Source not specified'),warning:typeof l.warning==='string'?l.warning:null,valueProperty:str(l.value_property,'value'),statusProperty:str(l.status_property,'status')};
}
