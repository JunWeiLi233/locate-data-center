import { afterEach,describe,it,expect,vi } from 'vitest';
import { realApi,isDemoMode } from './client';
import { DEMO_CONFIG,demoLayer,demoRun } from '../mocks/data';
function json(value:unknown,status=200){return new Response(JSON.stringify(value),{status,headers:{'Content-Type':'application/json'}});}
afterEach(()=>{vi.useRealTimers();vi.restoreAllMocks();vi.unstubAllGlobals();});
describe('real model transport',()=>{
  it('submits inputs and reads a completed backend job and authoritative results',async()=>{const fetchMock=vi.fn().mockResolvedValueOnce(json({job_id:'job1'})).mockResolvedValueOnce(json({id:'job1',state:'COMPLETE',stage:'Validation complete',run_id:'REAL_RUN',error:null})).mockResolvedValueOnce(json({...demoRun(),run_id:'REAL_RUN',demo:false}));vi.stubGlobal('fetch',fetchMock);const onProgress=vi.fn();const result=await realApi.search(DEMO_CONFIG,onProgress);expect(fetchMock.mock.calls[0][0]).toBe('/api/search');expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toMatchObject({facility:{peak_it_power_mw:100,average_load_percent:80}});expect(onProgress).toHaveBeenCalledWith(expect.objectContaining({state:'COMPLETE'}));expect(result.runId).toBe('REAL_RUN');expect(result.demo).toBe(false);});
  it('does not silently fall back to synthetic data on service failure',async()=>{vi.stubGlobal('fetch',vi.fn().mockRejectedValue(new TypeError('Network error')));expect(isDemoMode).toBe(false);await expect(realApi.capabilities()).rejects.toThrow('Model service unavailable');});
  it('preserves backend errors for preference consistency review',async()=>{vi.stubGlobal('fetch',vi.fn().mockResolvedValue(json({error:'Your priorities require review.'},422)));await expect(realApi.search(DEMO_CONFIG)).rejects.toThrow('priorities require review');});
  it('caches unchanged optional layer responses',async()=>{const fetchMock=vi.fn().mockImplementation(async()=>json(demoLayer('water')));vi.stubGlobal('fetch',fetchMock);const a=await realApi.layer('water','CACHE_TEST','current');const b=await realApi.layer('water','CACHE_TEST','current');expect(a).toBe(b);expect(fetchMock).toHaveBeenCalledTimes(1);await realApi.layer('water','CACHE_TEST','bau_2050');expect(fetchMock).toHaveBeenCalledTimes(2);});
  it('passes cancellation to fetch and never returns a cached value after abort',async()=>{const controller=new AbortController();controller.abort();vi.stubGlobal('fetch',vi.fn((_url,opts)=>{expect(opts.signal.aborted).toBe(true);return Promise.reject(new DOMException('Aborted','AbortError'));}));await expect(realApi.run('X','current',controller.signal)).rejects.toMatchObject({name:'AbortError'});await expect(realApi.layer('water','CACHE_TEST','current',undefined,controller.signal)).rejects.toMatchObject({name:'AbortError'});});
  it('keeps polling a progressing regional job that completes after 45 minutes',async()=>{
    vi.useFakeTimers();const started=Date.UTC(2026,9,3,20,14);vi.setSystemTime(started);
    const fetchMock=vi.fn().mockResolvedValueOnce(json({job_id:'regional-long'}))
      .mockResolvedValueOnce(json({id:'regional-long',state:'RUNNING',stage:'Regional model batch 30 of 61',run_id:null,error:null}))
      .mockResolvedValueOnce(json({id:'regional-long',state:'COMPLETE',stage:'Validation complete',run_id:'REGIONAL_LONG',error:null}))
      .mockResolvedValueOnce(json({...demoRun(),run_id:'REGIONAL_LONG',demo:false}));
    vi.stubGlobal('fetch',fetchMock);const onProgress=vi.fn();
    const pending=realApi.search(DEMO_CONFIG,onProgress).then(result=>({result,error:null}),error=>({result:null,error}));
    await vi.advanceTimersByTimeAsync(0);
    expect(onProgress).toHaveBeenCalledWith(expect.objectContaining({state:'RUNNING'}));
    vi.setSystemTime(started+60*60*1000);await vi.advanceTimersByTimeAsync(1000);
    const outcome=await pending;expect(outcome.error).toBeNull();expect(outcome.result?.runId).toBe('REGIONAL_LONG');
    expect(onProgress).toHaveBeenCalledWith(expect.objectContaining({state:'COMPLETE'}));
    expect(fetchMock.mock.calls.filter(([url])=>url==='/api/search')).toHaveLength(1);
  });
  it('stops browser polling at two hours without submitting another scientific job',async()=>{
    vi.useFakeTimers();const started=Date.UTC(2026,9,3,20,14);vi.setSystemTime(started);
    const fetchMock=vi.fn().mockResolvedValueOnce(json({job_id:'regional-pending'}))
      .mockResolvedValue(json({id:'regional-pending',state:'RUNNING',stage:'Regional validation',run_id:null,error:null}));
    vi.stubGlobal('fetch',fetchMock);
    const pending=realApi.search(DEMO_CONFIG).then(()=>null,error=>error);
    await vi.advanceTimersByTimeAsync(0);vi.setSystemTime(started+2*60*60*1000);await vi.advanceTimersByTimeAsync(1000);
    const error=await pending;expect(error).toMatchObject({name:'ServiceError',status:408});
    expect(error.message).toContain('regional-pending');expect(error.message).toContain('completed run');
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });
  it('cancels during the polling pause without another request',async()=>{
    vi.useFakeTimers();const controller=new AbortController();
    const fetchMock=vi.fn().mockResolvedValueOnce(json({job_id:'regional-cancel'}))
      .mockResolvedValueOnce(json({id:'regional-cancel',state:'RUNNING',stage:'Regional model batch 1 of 61',run_id:null,error:null}));
    vi.stubGlobal('fetch',fetchMock);
    const pending=realApi.search(DEMO_CONFIG,undefined,controller.signal).then(()=>null,error=>error);
    await vi.advanceTimersByTimeAsync(0);controller.abort();
    expect(await pending).toMatchObject({name:'AbortError'});await vi.advanceTimersByTimeAsync(1000);
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });
  it('retains the 30-second timeout for each individual service request',async()=>{
    vi.useFakeTimers();vi.stubGlobal('fetch',vi.fn((_url,opts)=>new Promise((_resolve,reject)=>{
      opts.signal.addEventListener('abort',()=>reject(opts.signal.reason),{once:true});
    })));
    let settled=false;const pending=realApi.run('SLOW_REQUEST').then(()=>null,error=>error).then(error=>{settled=true;return error;});
    await vi.advanceTimersByTimeAsync(29999);expect(settled).toBe(false);await vi.advanceTimersByTimeAsync(1);
    expect(await pending).toMatchObject({name:'ServiceError',status:408,message:expect.stringContaining('request timed out')});
  });
});
