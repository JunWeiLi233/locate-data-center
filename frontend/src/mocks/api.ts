import type { LocatorApi } from '../api/client';
import { parseCapabilities,parseLayer,parseRunResult } from '../api/regions';
import { DEMO_CONFIG,demoCapabilities,demoLayer,demoRun } from './data';
import type { FacilityConfiguration } from '../types/domain';
let configuration:FacilityConfiguration=DEMO_CONFIG;
function check(signal?:AbortSignal){if(signal?.aborted)throw new DOMException('Request canceled.','AbortError');}
export const mockApi:LocatorApi={
  async capabilities(signal){check(signal);return parseCapabilities(demoCapabilities);},
  async search(config,_onProgress,signal){check(signal);configuration=structuredClone(config);return parseRunResult(demoRun(config));},
  async run(id,scenario='current',signal){check(signal);if(id!=='DEMO_RUN')throw new Error('The requested demo run does not exist.');if(!demoCapabilities.scenarios.some(s=>s.id===scenario&&s.available))throw new Error('Unsupported demo scenario.');return parseRunResult(demoRun(configuration,scenario));},
  async layer(id,_run,_scenario,sublayer,signal){check(signal);if(['heat_reuse','community_economic'].includes(id))throw new Error('No synthetic layer data supplied.');return parseLayer(demoLayer(id,sublayer));},
};
