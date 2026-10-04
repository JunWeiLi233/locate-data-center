import type { Capabilities, FacilityConfiguration, Job, LayerData, LayerId, RunResult } from '../types/domain';
import { parseCapabilities, parseJob, parseLayer, parseRunResult, serializeConfiguration } from './regions';
import { createMonteCarloApi } from './monteCarlo';
import { modelFromUrl } from '../utils/modelChoice';

export interface LocatorApi {
  capabilities(signal?:AbortSignal):Promise<Capabilities>;
  search(configuration:FacilityConfiguration,onProgress?:(job:Job)=>void,signal?:AbortSignal):Promise<RunResult>;
  run(runId:string,scenarioId?:string,signal?:AbortSignal):Promise<RunResult>;
  layer(id:LayerId,runId:string,scenarioId:string,sublayer?:string,signal?:AbortSignal):Promise<LayerData>;
}
export class ServiceError extends Error {constructor(message:string,public status:number){super(message);this.name='ServiceError';}}
const base=(import.meta.env.VITE_API_BASE_URL??'').replace(/\/$/,'');
export const isDemoMode=import.meta.env.VITE_USE_MOCK_DATA==='true';
async function request(path:string,options:RequestInit={},signal?:AbortSignal):Promise<unknown> {
  const controller=new AbortController();const abort=()=>controller.abort(signal?.reason);if(signal?.aborted)abort();else signal?.addEventListener('abort',abort,{once:true});
  const timeout=setTimeout(()=>controller.abort(new DOMException('Model service request timed out.','TimeoutError')),30000);
  try {
    const response=await fetch(`${base}/api${path}`,{...options,signal:controller.signal,headers:{'Accept':'application/json',...options.body?{'Content-Type':'application/json'}:{},...options.headers}});
    let value:unknown;try{value=await response.json();}catch{throw new ServiceError('Model service returned an invalid JSON response.',response.status);}
    if(!response.ok){const data=value as {error?:unknown,message?:unknown};const nested=data?.error&&typeof data.error==='object'?data.error as {message?:unknown}:null;throw new ServiceError(typeof data?.error==='string'?data.error:typeof nested?.message==='string'?nested.message:typeof data?.message==='string'?data.message:`Model service request failed (${response.status}).`,response.status);}
    return value;
  }catch(e){if(controller.signal.aborted){if(signal?.aborted)throw new DOMException('Request canceled.','AbortError');throw new ServiceError('Model service request timed out. Retry when the service is available.',408);}if(e instanceof TypeError)throw new ServiceError('Model service unavailable. Check that the local API is running.',0);throw e;}
  finally{clearTimeout(timeout);signal?.removeEventListener('abort',abort);}
}
function pause(ms:number,signal?:AbortSignal):Promise<void>{return new Promise((resolve,reject)=>{if(signal?.aborted){reject(new DOMException('Request canceled.','AbortError'));return;}const abort=()=>{clearTimeout(timer);reject(new DOMException('Request canceled.','AbortError'));};const timer=setTimeout(()=>{signal?.removeEventListener('abort',abort);resolve();},ms);signal?.addEventListener('abort',abort,{once:true});});}
const layerCache=new Map<string,LayerData>();
export const realApi:LocatorApi={
  capabilities:async signal=>parseCapabilities(await request('/capabilities',{},signal)),
  run:async(runId,scenarioId='current',signal)=>parseRunResult(await request(`/runs/${encodeURIComponent(runId)}?scenario=${encodeURIComponent(scenarioId)}`,{},signal)),
  search:async(configuration,onProgress,signal)=>{
    const created=await request('/search',{method:'POST',body:JSON.stringify({facility:serializeConfiguration(configuration)})},signal) as {job_id?:unknown};
    if(typeof created.job_id!=='string')throw new ServiceError('Model service did not return a job identifier.',502);
    const deadline=Date.now()+45*60*1000;
    while(Date.now()<deadline){const job=parseJob(await request(`/jobs/${encodeURIComponent(created.job_id)}`,{},signal));onProgress?.(job);if(job.state==='ERROR')throw new ServiceError(job.error??'The model run failed.',422);if(job.state==='COMPLETE'){if(!job.runId)throw new ServiceError('Completed model job is missing its run ID.',502);return realApi.run(job.runId,'current',signal);}await pause(1000,signal);}
    throw new ServiceError('Model search is still running. Load its completed run later or retry.',408);
  },
  layer:async(id,runId,scenarioId,sublayer,signal)=>{const key=JSON.stringify([id,runId,scenarioId,sublayer??'']);if(signal?.aborted)throw new DOMException('Request canceled.','AbortError');const existing=layerCache.get(key);if(existing)return existing;const q=new URLSearchParams({run_id:runId,scenario:scenarioId});if(sublayer)q.set('sublayer',sublayer);const layer=parseLayer(await request(`/layers/${encodeURIComponent(id)}?${q}`,{},signal));layerCache.set(key,layer);if(layerCache.size>48)layerCache.delete(layerCache.keys().next().value!);return layer;},
};
// Demo is explicit. A service error must never select this adapter automatically.
const demoApi:LocatorApi={
  capabilities:async signal=>(await import('../mocks/api')).mockApi.capabilities(signal),
  search:async(config,onProgress,signal)=>(await import('../mocks/api')).mockApi.search(config,onProgress,signal),
  run:async(id,scenario,signal)=>(await import('../mocks/api')).mockApi.run(id,scenario,signal),
  layer:async(id,run,scenario,sublayer,signal)=>(await import('../mocks/api')).mockApi.layer(id,run,scenario,sublayer,signal),
};
// Selection is explicit; unavailable services never trigger a switch of scientific models.
export const isCountyModel=modelFromUrl()==='county';
export const locatorApi=isCountyModel?createMonteCarloApi(import.meta.env.VITE_MONTE_CARLO_API_URL??'http://127.0.0.1:8000'):isDemoMode?demoApi:realApi;
