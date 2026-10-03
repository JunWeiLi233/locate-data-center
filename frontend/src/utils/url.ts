import type { FacilityConfiguration, LayerId, LayerSelection, MapCamera } from '../types/domain';
export interface UrlState {runId:string|null;regionId:string|null;scenarioId:string;layers:LayerSelection[];camera:MapCamera|undefined;configuration?:Partial<FacilityConfiguration>}
const validLayers:LayerId[]=['candidates','grid','water','power_carbon','land','climate','heat_reuse','community_economic','infrastructure'];
export function readUrlState(search=window.location.search):UrlState {
  const p=new URLSearchParams(search);const lon=Number(p.get('lon')),lat=Number(p.get('lat')),zoom=Number(p.get('zoom'));
  const camera=p.has('lon')&&p.has('lat')&&p.has('zoom')&&Number.isFinite(lon)&&Math.abs(lon)<=180&&Number.isFinite(lat)&&Math.abs(lat)<=85&&Number.isFinite(zoom)&&zoom>=0&&zoom<=22?{longitude:lon,latitude:lat,zoom}:undefined;
  const layers=(p.get('layers')??'candidates').split(',').flatMap(s=>{const [id,sublayer]=s.split(':');return validLayers.includes(id as LayerId)?[{id:id as LayerId,enabled:true,...sublayer?{sublayer}:{}}]:[];});
  const configuration:Partial<FacilityConfiguration>={};const numeric=[['mw','peakItPowerMw'],['load','averageLoadPercent'],['opening','targetOpeningYear'],['life','lifetimeYears']] as const;
  numeric.forEach(([key,field])=>{const v=p.get(key);if(v!==null&&Number.isFinite(Number(v)))configuration[field]=Number(v);});
  return{runId:p.get('run'),regionId:p.get('region'),scenarioId:p.get('scenario')??'current',layers,camera,configuration};
}
export function writeUrlState(state:Partial<UrlState>):void {
  const u=new URL(window.location.href);const put=(k:string,v:string|null|undefined)=>{if(v)u.searchParams.set(k,v);else u.searchParams.delete(k);};
  if('runId'in state)put('run',state.runId);if('regionId'in state)put('region',state.regionId);if('scenarioId'in state)put('scenario',state.scenarioId);
  if(state.layers)u.searchParams.set('layers',state.layers.filter(l=>l.enabled).map(l=>l.sublayer?`${l.id}:${l.sublayer}`:l.id).join(','));
  if(state.camera){put('lon',state.camera.longitude.toFixed(5));put('lat',state.camera.latitude.toFixed(5));put('zoom',state.camera.zoom.toFixed(2));}
  if(state.configuration){const c=state.configuration;if(c.peakItPowerMw!==undefined)put('mw',String(c.peakItPowerMw));if(c.averageLoadPercent!==undefined)put('load',String(c.averageLoadPercent));if(c.targetOpeningYear!==undefined)put('opening',String(c.targetOpeningYear));if(c.lifetimeYears!==undefined)put('life',String(c.lifetimeYears));}
  window.history.replaceState(null,'',u);
}
