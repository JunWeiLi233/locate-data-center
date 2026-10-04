import type { Geometry, Position } from 'geojson';
import { FACTOR_LABELS } from '../types/domain';
import type { BriefAlternative, BriefMetric, Capabilities, CandidateRegion, CountyBoundaryYear, CountyEconomicMetric, DecisionBrief, FacilityConfiguration, Factor, FactorId, GridAnalysisMode, Job, LayerData, LayerId, Metric, RegionalAnalysis, RunResult, SocioeconomicContext, Source } from '../types/domain';

type Row = Record<string, unknown>;
export class ApiContractError extends Error { constructor(message: string) {super(message); this.name='ApiContractError';} }
function row(value: unknown, name='response'): Row { if(!value || typeof value!=='object' || Array.isArray(value)) throw new ApiContractError(`Invalid ${name}: expected an object.`); return value as Row; }
function rows(value: unknown): unknown[] {return Array.isArray(value) ? value : [];}
function str(value: unknown, fallback=''): string {return typeof value==='string' ? value : fallback;}
function num(value: unknown): number | null {return typeof value==='number' && Number.isFinite(value) ? value : null;}
function strings(value: unknown): string[] {return rows(value).filter((v):v is string=>typeof v==='string');}
function booleanOrNull(value: unknown): boolean | null {return typeof value==='boolean' ? value : null;}
function nullableText(value: unknown): string | null {return typeof value==='string'?value:null;}
function objects(value: unknown): Row[] {return rows(value).filter((v):v is Row=>!!v&&typeof v==='object'&&!Array.isArray(v));}
function analysisMode(value: unknown): GridAnalysisMode | null {if(value == null)return null;if(value==='cached_regional'||value==='full_rediscovery')return value;throw new ApiContractError('Unsupported Grid analysis mode.');}
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
    return {id,label:FACTOR_LABELS[id],score:failed||!directionKnown||id==='community_economic'?null:score(f?.score),direction:'higher_is_better',basis:id==='community_economic'?'County economic context is separate from technical MCDA; no community economic factor score is supplied.':failed?'Hard screening failure; favorable scores are not shown.':f&&!directionKnown?'Score direction was not declared favorable by the model.':str(f?.basis,'No factor score supplied by the model.'),sources:sources(f?.sources)};
  });
  const sens=r.sensitivity&&typeof r.sensitivity==='object'?r.sensitivity as Row:null;
  const rawMetrics=Array.isArray(r.raw_metrics)?r.raw_metrics:[];
  return {id,label:str(r.label,`Candidate Region ${id}`),rank:failed?null:rank(r.rank),rankBasis:str(r.rank_basis,'Model ranking'),score:failed?null:score(r.overall_score),regionMeanScore:failed?null:score(r.region_mean_score),paretoOptimal:booleanOrNull(r.pareto_optimal),centroid,geometry,geometryWarning:geometry?null:str(r.geometry_warning,'Region geometry unavailable. Metrics can still be viewed.'),screeningStatus,designId:str(r.design_id,'Unknown'),scenarioId:str(r.scenario_id,'Unknown'),representativeGridId:typeof r.representative_grid_id==='string'?r.representative_grid_id:null,parentGridId:typeof r.parent_grid_id==='string'?r.parent_grid_id:null,placeLabel:typeof r.place_label==='string'&&r.place_label.trim()?r.place_label.trim():null,regionStates:Array.isArray(r.region_states)&&r.region_states.length>0&&r.region_states.every(v=>typeof v==='string'&&v.trim())?strings(r.region_states):null,cellCount:rank(r.cell_count),areaKm2:(()=>{const n=num(r.area_km2);return n!==null&&n>=0?n:null;})(),factors,metrics:rawMetrics.flatMap(v=>{try{return [parseMetric(v)];}catch{return [];}}),verificationRequired:strings(r.verification_required),uncertainties:strings(r.uncertainties),strengths:strings(r.strengths),limitations:strings(r.limitations),dataQuality:str(r.data_quality,'Unknown'),sensitivity:sens?{baseRank:rank(sens.base_rank),minRank:rank(sens.min_rank),maxRank:rank(sens.max_rank),drivers:strings(sens.drivers)}:null};
}
export function parseRunResult(value: unknown): RunResult {
  const r=row(value);const runId=str(r.run_id);if(!runId)throw new ApiContractError('Response is missing run_id.');
  if(!Array.isArray(r.regions))throw new ApiContractError('Response is missing a regions array.');
  const warnings=strings(r.warnings);const ids=new Set<string>();
  const regions=r.regions.flatMap((v,i)=>{try{const p=parseRegion(v);if(ids.has(p.id))throw new ApiContractError('Duplicate region ID.');ids.add(p.id);return [p];}catch(e){warnings.push(`Region ${i+1} could not be displayed: ${e instanceof Error?e.message:'invalid data'}`);return [];}});
  if(r.regions.length>0&&regions.length===0)throw new ApiContractError('The response contains no valid candidate records. This is an invalid response, not an empty model result.');
  const w=r.weighting&&typeof r.weighting==='object'?r.weighting as Row:null;const weights:Record<string,number>={};if(w?.weights&&typeof w.weights==='object')Object.entries(w.weights).forEach(([k,v])=>{if(num(v)!==null)weights[k]=v as number;});
  const suppliedState=str(r.state);const state=regions.length===0?'EMPTY':suppliedState==='PARTIAL'||warnings.length>0||regions.some(c=>c.screeningStatus==='UNKNOWN'||c.screeningStatus==='CONDITIONAL'||c.geometry===null)?'PARTIAL':'SUCCESS';
  let decisionBrief:DecisionBrief|null=null;let briefReason=nullableText(r.decision_brief_unavailable_reason);
  if(r.decision_brief){try{decisionBrief=parseDecisionBrief(r.decision_brief);const context=str(r.decision_brief_context_id,decisionBrief.scenario_id);if(decisionBrief.run_id!==runId||(context!==str(r.scenario_id,'current')&&!(r.scenario_id==='current'&&regions.some(region=>region.scenarioId===context))))throw new ApiContractError('Decision brief does not match this run or scenario.');}catch(cause){decisionBrief=null;briefReason=cause instanceof Error?cause.message:'Invalid decision brief.';}}
  return {schemaVersion:schema(r.schema_version),runId,timestamp:typeof r.timestamp==='string'?r.timestamp:null,modelVersion:str(r.model_version,'Unspecified'),demo:r.demo===true,state,scope:str(r.scope,'Analyzed coverage not specified'),analyzedCellCount:num(r.analyzed_cell_count)??0,configuration:parseConfiguration(r.configuration??r.facility??{}),scenarioId:str(r.scenario_id,'current'),regions,analysis:parseAnalysis(r.analysis),analysisResolutionM:num(r.analysis_resolution_m),analysisMode:analysisMode(r.analysis_mode),scenarios:Array.isArray(r.scenarios)?parseScenarios(r.scenarios):undefined,warnings,searchStages:rows(r.search_stages).flatMap(v=>{try{const s=row(v);return [{label:str(s.label),count:num(s.count)}];}catch{return [];}}),weighting:w?{status:str(w.status,'Unknown'),weights,consistencyRatio:num(w.consistency_ratio)}:null,exports:rows(r.exports).flatMap(v=>{try{const e=row(v);return [{label:str(e.label,'Export'),url:str(e.url)}];}catch{return [];}}),decisionBrief,decisionBriefUnavailableReason:briefReason};
}
function briefMetrics(value:unknown):BriefMetric[]{return objects(value).map(m=>{const status=['observed','calculated','scenario','proxy','unknown'].includes(str(m.status))?m.status as BriefMetric['status']:'unknown';const measured=status==='unknown'?null:typeof m.value==='string'?m.value:num(m.value);return{id:str(m.id),value:measured,unit:str(m.unit,'unit unreported'),status:measured===null?'unknown':status,confidence:str(m.confidence,'unknown'),missing_reason:nullableText(m.missing_reason)??(measured===null?'No supported value was supplied.':null)};});}
function briefAlternative(value:unknown):BriefAlternative{
  const a=row(value,'brief alternative');const coordinates=(value:unknown)=>{if(!value||typeof value!=='object')return null;const c=value as Row;const lat=num(c.lat),lon=num(c.lon);return lat!==null&&lon!==null&&Math.abs(lat)<=90&&Math.abs(lon)<=180?{lat,lon}:null;};
  return{region_id:nullableText(a.region_id),grid_id:nullableText(a.grid_id),design_id:nullableText(a.design_id),scenario_id:nullableText(a.scenario_id),rank:rank(a.rank),score:score(a.score),metrics:briefMetrics(a.metrics),geographic_label:nullableText(a.geographic_label),centroid:coordinates(a.centroid),region_centroid:coordinates(a.region_centroid),region_area_km2:num(a.region_area_km2),region_cell_count:num(a.region_cell_count),pareto_status:typeof a.pareto_status==='string'?a.pareto_status:booleanOrNull(a.pareto_status)};
}
export function parseDecisionBrief(value:unknown):DecisionBrief{
  const b=row(value,'decision brief');if(!str(b.schema_version).startsWith('1.')||!str(b.run_id)||!str(b.scenario_id))throw new ApiContractError('Unsupported or incomplete decision brief.');
  const f=row(b.facility,'brief facility'),r=row(b.recommendation,'brief recommendation'),w=row(b.framework,'brief framework'),e=row(b.evidence,'brief evidence'),i=row(b.impact,'brief impact');
  return{schema_version:str(b.schema_version),run_id:str(b.run_id),data_mode:str(b.data_mode,'unknown'),scenario_id:str(b.scenario_id),interpretation:str(b.interpretation),scope:str(b.scope),analyzed_cell_count:num(b.analyzed_cell_count),resolution_m:num(b.resolution_m),facility:{peak_it_power_mw:num(f.peak_it_power_mw),average_it_load_factor:num(f.average_it_load_factor),target_opening_year:num(f.target_opening_year),operating_lifetime_years:num(f.operating_lifetime_years),hours_in_modeled_year:num(f.hours_in_modeled_year),basis:str(f.basis),rationale:str(f.rationale)},recommendation:{...briefAlternative(r),status:str(r.status),rationale:str(r.rationale)},alternatives:objects(b.alternatives).map(briefAlternative),framework:{profile_id:str(w.profile_id),weighting_method:str(w.weighting_method),method:str(w.method,'Decision method was not supplied.'),criteria:objects(w.criteria).map(c=>({metric_id:str(c.metric_id),label:str(c.label,str(c.metric_id)),unit:str(c.unit),direction:str(c.direction),weight:num(c.weight),reference_low:num(c.reference_low),reference_high:num(c.reference_high),role:str(c.role),basis:str(c.basis),rationale:str(c.rationale),normalized_score:score(c.normalized_score),contribution:num(c.contribution)})),excluded_criteria:rows(w.excluded_criteria).flatMap(value=>{if(typeof value==='string')return[value];if(value&&typeof value==='object'&&!Array.isArray(value)){const c=value as Row;return[`${str(c.criterion,'Unreported criterion')} (${str(c.role,'unreported role')}): ${str(c.reason,'No exclusion reason supplied.')}`];}return[];}),missing_data_policy:str(w.missing_data_policy)},evidence:{sources:objects(e.sources).map(s=>({source_id:str(s.source_id),implemented:booleanOrNull(s.implemented),acquired:booleanOrNull(s.acquired),analyzed:booleanOrNull(s.analyzed),analyzed_cells:num(s.analyzed_cells),status:str(s.status),source_url:nullableText(s.source_url),source_version:str(s.source_version),data_year:s.data_year==null?'Unknown':String(s.data_year),retrieved_at:nullableText(s.retrieved_at)})),assumptions:strings(e.assumptions),input_hashes:e.input_hashes&&typeof e.input_hashes==='object'&&!Array.isArray(e.input_hashes)?e.input_hashes as Row:{}},impact:{total_water_consumption:i.total_water_consumption?briefMetrics([i.total_water_consumption])[0]??null:null,cooling_comparisons:objects(i.cooling_comparisons).map(c=>({grid_id:str(c.grid_id),scenario_id:str(c.scenario_id),reference_design_id:str(c.reference_design_id),alternative_design_id:str(c.alternative_design_id),reference_minus_alternative:Object.fromEntries(Object.entries(c.reference_minus_alternative&&typeof c.reference_minus_alternative==='object'?c.reference_minus_alternative:{}).map(([k,v])=>[k,num(v)])),basis:str(c.basis)})),unknowns:briefMetrics(i.unknowns),boundary:str(i.boundary)},risks:objects(b.risks).map(r=>({requirement:str(r.requirement),outcome:str(r.outcome),missing_reason:nullableText(r.missing_reason),action:str(r.action)})),implementation_vision:objects(b.implementation_vision).map(v=>({period:str(v.period),label:str(v.label),actions:strings(v.actions),evidence_gate:str(v.evidence_gate)})),limitations:strings(b.limitations)};
}
const FINE_SELECTIONS=['national_fine_surface','national_fine_region_parents'];
function parseAnalysis(value: unknown): RegionalAnalysis | null {
  if(!value)return null;
  const a=row(value,'analysis coverage');if(a.analysis_level!=='regional')throw new ApiContractError('Unsupported analysis level.');
  const text=(key:string)=>typeof a[key]==='string'?a[key] as string:null;
  const selection=text('selection');
  if(selection!==null&&!['representative_parent_cells','fixed_cached_cohort',...FINE_SELECTIONS].includes(selection))throw new ApiContractError('Unsupported regional parent selection.');
  let nationalFineSurface: RegionalAnalysis['nationalFineSurface']=null;
  if(a.national_fine_surface!=null){
    const f=row(a.national_fine_surface,'national fine surface');
    if(!FINE_SELECTIONS.includes(selection??'')||f.screening_status!=='UNSCREENED')throw new ApiContractError('National fine surface must be explicitly UNSCREENED.');
    const versions=f.method_versions&&typeof f.method_versions==='object'&&!Array.isArray(f.method_versions)?f.method_versions as Row:{};
    nationalFineSurface={screeningStatus:'UNSCREENED',valuedCells:num(f.valued_cells),scoredAlternatives:num(f.scored_alternatives),alternatives:num(f.alternatives),unscoredAlternatives:num(f.unscored_alternatives),rankedParentWindows:num(f.ranked_parent_windows),selectionLimit:num(f.selection_limit),stageIdentity:nullableText(f.stage_identity),manifest:nullableText(f.manifest),manifestSha256:nullableText(f.manifest_sha256),methodVersions:Object.fromEntries(Object.entries(versions).filter((entry):entry is [string,string]=>typeof entry[1]==='string'))};
  }
  return {analysisLevel:'regional',parentRunId:text('parent_run_id'),parentRunPath:text('parent_run_path'),gridDefinitionId:text('grid_definition_id'),cellSizeM:num(a.cell_size_m),maximumRegionExtentKm:num(a.maximum_region_extent_km),refinedCells:num(a.refined_cells),nationalCells:num(a.national_cells),shortlistedParentCells:num(a.shortlisted_parent_cells),refinedParentCells:num(a.refined_parent_cells),refinedAreaKm2:num(a.refined_area_km2),shortlistedParentAreaKm2:num(a.shortlisted_parent_area_km2),rankingUniverse:text('ranking_universe'),selection:selection as RegionalAnalysis['selection'],coverageWarning:text('coverage_warning'),diagnosticsStatus:text('diagnostics_status'),landSearchScope:text('land_search_scope'),nationalFineSurface};
}
function parseScenarios(value: unknown): Capabilities['scenarios'] {return rows(value).map(v=>{const s=row(v);return{id:str(s.id),label:str(s.label),year:num(s.year),pathway:typeof s.pathway==='string'?s.pathway:null,available:s.available===true,reason:typeof s.reason==='string'?s.reason:null};});}
export function parseCapabilities(value: unknown): Capabilities {
  const c=row(value);const modes=c.analysis_modes==null?undefined:rows(c.analysis_modes).map(value=>{const mode=row(value,'analysis mode');const id=analysisMode(mode.id);if(!id)throw new ApiContractError('Analysis mode capability is missing its ID.');return{id,label:str(mode.label),available:mode.available===true,reason:nullableText(mode.reason)};});return {analysisModes:modes,defaultAnalysisMode:analysisMode(c.default_analysis_mode),cachedRegionalBaselineRunId:nullableText(c.cached_regional_baseline_run_id),schemaVersion:schema(c.schema_version),scope:str(c.scope,'Coverage not specified'),defaultConfiguration:parseConfiguration(c.default_configuration??{}),coolingOptions:rows(c.cooling_options).map(v=>{const r=row(v);return{id:str(r.id),label:str(r.label)};}),weightingGroups:rows(c.weighting_groups).map(v=>{const r=row(v);return{id:str(r.id),label:str(r.label)};}),layers:rows(c.layers).map(v=>{const l=row(v);if(!layerIds.includes(l.id as LayerId))throw new ApiContractError('Unknown layer capability.');return{id:l.id as LayerId,label:str(l.label),available:l.available===true,reason:typeof l.reason==='string'?l.reason:null,sublayers:rows(l.sublayers).map(v=>{const s=row(v);return{id:str(s.id),label:str(s.label),available:s.available===true,reason:typeof s.reason==='string'?s.reason:undefined};})};}),scenarios:parseScenarios(c.scenarios),latestRunId:typeof c.latest_run_id==='string'?c.latest_run_id:null,nationwideRegionalRunId:typeof c.nationwide_regional_run_id==='string'&&c.nationwide_regional_run_id.trim()?c.nationwide_regional_run_id:null,demo:c.demo===true};
}
export function parseJob(value: unknown): Job {const j=row(value);schema(j.schema_version);if(!['QUEUED','RUNNING','COMPLETE','ERROR'].includes(str(j.state)))throw new ApiContractError('Invalid job state.');return{id:str(j.id),state:j.state as Job['state'],stage:str(j.stage,'Searching geographic model...'),runId:typeof j.run_id==='string'?j.run_id:null,error:typeof j.error==='string'?j.error:null};}
export function parseLayer(value: unknown): LayerData {
  const l=row(value);schema(l.schema_version);const d=row(l.data,'layer data');if(!layerIds.includes(l.id as LayerId)||d.type!=='FeatureCollection'||!Array.isArray(d.features))throw new ApiContractError('Invalid geographic layer.');
  if(d.features.length>10000)throw new ApiContractError('Layer exceeds browser GeoJSON limit. Use a simplified or tiled backend source.');
  return {id:l.id as LayerId,data:d as unknown as LayerData['data'],label:str(l.label),unit:str(l.unit),min:num(l.min),max:num(l.max),direction:l.id==='community_economic'?'neutral':['higher_is_better','higher_is_worse','categorical'].includes(str(l.direction))?l.direction as LayerData['direction']:'neutral',source:str(l.source,'Source not specified'),warning:typeof l.warning==='string'?l.warning:null,valueProperty:str(l.value_property,'value'),statusProperty:str(l.status_property,'status'),
    socioeconomicYear:num(l.socioeconomic_year),boundaryYear:l.boundary_year===2023||l.boundary_year===2025?l.boundary_year:null,boundarySourceKind:nullableText(l.boundary_source_kind),sourceMetadata:l.source_metadata&&typeof l.source_metadata==='object'&&!Array.isArray(l.source_metadata)?l.source_metadata as Row:{}};
}

function countyMetric(value: unknown): CountyEconomicMetric {
  const m=value&&typeof value==='object'&&!Array.isArray(value)?value as Row:{};
  const status=['observed','calculated','scenario','proxy','unknown'].includes(str(m.status))?m.status as Metric['status']:'unknown';
  const measured=status==='unknown'?null:num(m.value);
  return {value:measured,unit:str(m.unit),status:measured===null?'unknown':status,confidence:str(m.confidence,'unknown'),missingReason:nullableText(m.missing_reason)??(measured===null?'County estimate not available.':null),method:nullableText(m.method),sourceId:nullableText(m.source_id),dataYear:m.data_year==null?null:String(m.data_year),lower90:num(m.lower_90),upper90:num(m.upper_90)};
}
export function parseSocioeconomic(value: unknown): SocioeconomicContext {
  const c=row(value,'county economic context');
  const boundary=c.boundary_year;
  if(boundary!==2023&&boundary!==2025)throw new ApiContractError('Unsupported county boundary vintage.');
  if(c.socioeconomic_year!==2024)throw new ApiContractError('County economic filters require the declared 2024 SAIPE estimate vintage.');
  const regions=row(c.region_counties??{},'region county crosswalk');
  const regionCounties:SocioeconomicContext['regionCounties']={};
  for(const [id,values] of Object.entries(regions)){
    if(!Array.isArray(values))throw new ApiContractError('Invalid overlapping county list.');
    regionCounties[id]=values.map(value=>{
      const county=row(value,'county record');
      if(typeof county.county_geoid!=='string'||!/^\d{5}$/.test(county.county_geoid))throw new ApiContractError('County GEOID must remain a five-character string.');
      if(county.boundary_year!==boundary)throw new ApiContractError('County boundary vintage does not match the requested context.');
      if(num(county.socioeconomic_year)!==num(c.socioeconomic_year))throw new ApiContractError('County estimate year does not match its source context.');
      const raw=county.metrics&&typeof county.metrics==='object'&&!Array.isArray(county.metrics)?county.metrics as Row:{};
      const metrics=Object.fromEntries(Object.entries(raw).map(([key,value])=>[key,countyMetric(value)]));
      const measured=(key:string)=>metrics[key]?.value??null;
      return {countyGeoid:county.county_geoid,countyName:str(county.county_name,county.county_geoid),stateFips:typeof county.state_fips==='string'&&/^\d{2}$/.test(county.state_fips)?county.state_fips:null,stateName:nullableText(county.state_name),
        boundaryYear:boundary as CountyBoundaryYear,socioeconomicYear:num(county.socioeconomic_year),overlapAreaKm2:num(county.overlap_area_km2),overlapFraction:num(county.overlap_fraction),
        povertyRatePct:measured('poverty_rate_pct'),medianHouseholdIncomeUsd:measured('income_usd'),povertyRateMoePct:measured('poverty_rate_moe_pct'),incomeMoeUsd:measured('income_moe_usd'),
        povertyPercentile:measured('poverty_percentile'),lowIncomePercentile:measured('low_income_percentile'),metrics};
    });
    if(new Set(regionCounties[id].map(county=>county.countyGeoid)).size!==regionCounties[id].length)throw new ApiContractError('Duplicate overlapping county record.');
  }
  const fiscal=c.fiscal_context&&typeof c.fiscal_context==='object'&&!Array.isArray(c.fiscal_context)?c.fiscal_context as Row:{};
  const metadata=(value:unknown)=>value&&typeof value==='object'&&!Array.isArray(value)?value as Row:{};
  return {schemaVersion:schema(c.schema_version),contextSchemaVersion:str(c.context_schema_version,'1.0.0'),runId:str(c.run_id),scenarioId:str(c.scenario_id,'current'),available:c.available===true,boundaryYear:boundary,socioeconomicYear:num(c.socioeconomic_year),boundarySourceKind:nullableText(c.boundary_source_kind),sourceMetadata:metadata(c.source_metadata),coverageSummary:metadata(c.coverage_summary),warnings:strings(c.warnings),regionCounties,
    fiscalContext:{localRevenue:countyMetric(fiscal.local_revenue),servicePressure:countyMetric(fiscal.service_pressure)}};
}
