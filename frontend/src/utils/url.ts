import type { FacilityConfiguration, LayerId, LayerSelection, MapCamera, ModelId } from '../types/domain';
export interface UrlState {model:ModelId;runId:string|null;regionId:string|null;scenarioId:string;layers:LayerSelection[];camera:MapCamera|undefined;configuration?:Partial<FacilityConfiguration>}
const validLayers:LayerId[]=['candidates','grid','water','power_carbon','land','climate','heat_reuse','infrastructure'];
export function readUrlState(search=window.location.search):UrlState {
  const p=new URLSearchParams(search);const lon=Number(p.get('lon')),lat=Number(p.get('lat')),zoom=Number(p.get('zoom'));
  const camera=p.has('lon')&&p.has('lat')&&p.has('zoom')&&Number.isFinite(lon)&&Math.abs(lon)<=180&&Number.isFinite(lat)&&Math.abs(lat)<=85&&Number.isFinite(zoom)&&zoom>=0&&zoom<=22?{longitude:lon,latitude:lat,zoom}:undefined;
  const layers=(p.get('layers')??'candidates').split(',').flatMap(s=>{const [id,sublayer]=s.split(':');return validLayers.includes(id as LayerId)?[{id:id as LayerId,enabled:true,...sublayer?{sublayer}:{}}]:[];});
  const configuration:Partial<FacilityConfiguration>={};const numeric=[['mw','peakItPowerMw'],['load','averageLoadPercent'],['opening','targetOpeningYear'],['life','lifetimeYears']] as const;
  numeric.forEach(([key,field])=>{const v=p.get(key);if(v!==null&&Number.isFinite(Number(v)))configuration[field]=Number(v);});
  return{model:p.get('model')==='county'?'county':'grid',runId:p.get('run'),regionId:p.get('region'),scenarioId:p.get('scenario')??'current',layers,camera,configuration};
}
/** In-app history entry: Back reverses opening the editor, selecting an area, loading other results or switching model. */
export interface NavigationState {locator:true;editing?:boolean;/** This entry was added by opening the facility editor. */editorEntry?:boolean}
export const navigationState=():NavigationState|null=>{const state=window.history.state as Partial<NavigationState>|null;return state?.locator===true?state as NavigationState:null;};
/** Replaces the current entry; its navigation state is kept unless one is supplied. */
export function writeUrlState(state:Partial<UrlState>,navigation:NavigationState|null=navigationState()):void {window.history.replaceState(navigation,'',urlFor(state));}
/** Adds an entry so the browser's Back button returns to the current view. */
export function pushUrlState(state:Partial<UrlState>,navigation:NavigationState):void {window.history.pushState(navigation,'',urlFor(state));}
function urlFor(state:Partial<UrlState>):URL {
  const u=new URL(window.location.href);const put=(k:string,v:string|null|undefined)=>{if(v)u.searchParams.set(k,v);else u.searchParams.delete(k);};
  if('model'in state)put('model',state.model==='county'?'county':null);
  if('runId'in state)put('run',state.runId);if('regionId'in state)put('region',state.regionId);if('scenarioId'in state)put('scenario',state.scenarioId);
  if(state.layers)u.searchParams.set('layers',state.layers.filter(l=>l.enabled&&validLayers.includes(l.id)).map(l=>l.sublayer?`${l.id}:${l.sublayer}`:l.id).join(','));
  if(state.camera){put('lon',state.camera.longitude.toFixed(5));put('lat',state.camera.latitude.toFixed(5));put('zoom',state.camera.zoom.toFixed(2));}
  if(state.configuration){const c=state.configuration;if(c.peakItPowerMw!==undefined)put('mw',String(c.peakItPowerMw));if(c.averageLoadPercent!==undefined)put('load',String(c.averageLoadPercent));if(c.targetOpeningYear!==undefined)put('opening',String(c.targetOpeningYear));if(c.lifetimeYears!==undefined)put('life',String(c.lifetimeYears));}
  return u;
}
