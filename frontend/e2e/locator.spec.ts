import {test,expect,type Page} from '@playwright/test';
import {demoCapabilities,demoRun,demoLayer,DEMO_CONFIG} from '../src/mocks/data';
import {parseConfiguration} from '../src/api/regions';
const apiRoute=/^https?:\/\/[^/]+\/api\//;

async function fixtureService(page:Page,state:'normal'|'error'|'empty'='normal',savedConfiguration=DEMO_CONFIG,advertiseSavedRun=true){
  let config=structuredClone(savedConfiguration);
  await page.route(apiRoute,async route=>{
    const url=new URL(route.request().url());const path=url.pathname;
    let body:unknown;let status=200;
    if(path==='/api/capabilities')body=advertiseSavedRun?demoCapabilities:{...demoCapabilities,latest_run_id:null};
    else if(path==='/api/search'){
      if(state==='error'){body={error:{message:'Synthetic test service failure'}};status=503;}
      else{config=parseConfiguration(route.request().postDataJSON().facility);body={job_id:'E2E_DEMO_JOB'};}
    }else if(path.startsWith('/api/jobs/'))body={id:'E2E_DEMO_JOB',state:'COMPLETE',stage:'Complete synthetic fixture',run_id:'DEMO_RUN',error:null};
    else if(path.startsWith('/api/runs/'))body=state==='empty'?{...demoRun(config),regions:[],state:'EMPTY'}:demoRun(config,url.searchParams.get('scenario')??'current');
    else if(path.startsWith('/api/layers/'))body=demoLayer(path.split('/').at(-1)!,url.searchParams.get('sublayer')??undefined);
    else{body={error:'Unknown synthetic test route'};status=404;}
    await route.fulfill({status,contentType:'application/json',body:JSON.stringify(body)});
  });
}
const placeCount=(regions:{geometry:unknown}[])=>new Set(regions.map(region=>JSON.stringify(region.geometry))).size;
async function expandSheet(page:Page){const button=page.getByRole('button',{name:'Expand bottom sheet'});if(await button.isVisible())await button.click();}
async function openEditor(page:Page){await expandSheet(page);const edit=page.getByRole('button',{name:'Edit facility'});const find=page.getByRole('button',{name:'Find locations',exact:true});await expect(edit.or(find)).toBeVisible();if(await edit.isVisible())await edit.click();await expect(find).toBeEnabled();}
async function configureAndSearch(page:Page){await openEditor(page);await page.getByLabel('Peak IT power MW').fill('100');await page.getByLabel('Average load percent').fill('80');await page.getByRole('button',{name:'Find locations',exact:true}).click();}

test('map search → polygons/overlap → physical evidence → comparison → supported scenario',async({page},testInfo)=>{
  const errors:string[]=[];page.on('pageerror',e=>errors.push(e.message));
  await fixtureService(page);await page.goto('/');
  await expect(page.getByText('DEMO DATA',{exact:true})).toBeVisible();
  await expect(page.locator('.maplibregl-canvas')).toBeVisible();
  if(testInfo.project.name==='mobile')await expect.poll(()=>Number(new URL(page.url()).searchParams.get('zoom'))).toBeLessThan(2.8);
  await expandSheet(page);await expect(page.getByLabel('Peak IT power MW')).toBeVisible();
  await expect(page.locator('.region-select')).toHaveCount(0);
  await configureAndSearch(page);
  await expect(page.getByRole('region',{name:'Evaluated configuration'})).not.toContainText('Saved results');
  await expect(page.locator('.region-select')).toHaveCount(2);
  await expect(page.locator('.run-summary').getByText('Results contain unresolved critical data.',{exact:false})).toBeVisible();
  await page.getByRole('button',{name:'Select Candidate Alpha, Air / dry (assumed)',exact:true}).click();
  const details=page.getByRole('complementary',{name:'Details for Candidate Alpha'});
  await expect(details).toBeVisible();await expect(details.locator('.key-figure').getByText('Annual facility electricity',{exact:true})).toBeVisible();
  await details.getByText('All measurements and sources').click();
  await expect(details.locator('.metric-row').filter({hasText:'Utility power capacity'}).getByText('Utility power capacity',{exact:true})).toBeVisible();
  await expect(details.locator('.metric-row').filter({hasText:'Utility power capacity'}).getByText('Unknown',{exact:true})).toBeVisible();
  await expect.poll(()=>new URL(page.url()).searchParams.get('region')).toBe('DEMO_ALPHA');
  await expect.poll(()=>Number(new URL(page.url()).searchParams.get('zoom'))).toBeGreaterThan(6);
  if(testInfo.project.name==='desktop'){
    const canvas=page.locator('.maplibregl-canvas');const box=await canvas.boundingBox();
    expect(box!.height).toBeLessThanOrEqual(page.viewportSize()!.height);
    await expect(page.locator('.app-header')).toBeInViewport();
    expect(await page.locator('.locator-app').evaluate(el=>el.scrollTop)).toBe(0);
    await canvas.click({position:{x:box!.width/2,y:box!.height/2}});
    const overlaps=page.getByRole('dialog',{name:'Overlapping region alternatives'});await expect(overlaps).toBeVisible();
    await overlaps.getByRole('button',{name:/Candidate Beta/}).click();
    await expect(page.getByRole('complementary',{name:'Details for Candidate Beta'})).toBeVisible();
    await overlaps.getByRole('button',{name:'Close alternatives'}).click();
  }
  await page.getByRole('button',{name:'Close region details'}).click();
  await page.getByRole('button',{name:'Add Candidate Alpha, Air / dry (assumed) to comparison'}).click();
  await page.getByRole('button',{name:'Add Candidate Gamma, Air / dry (assumed) to comparison'}).click();
  await page.getByRole('button',{name:'Compare (2)',exact:true}).click();
  await expect(page.getByRole('dialog',{name:'Region comparison'})).toBeVisible();
  await expect(page.getByRole('table').getByText('Unknown',{exact:false}).first()).toBeVisible();
  await page.getByRole('button',{name:'Close comparison'}).click();
  if(testInfo.project.name==='mobile')await page.getByRole('button',{name:'Minimize bottom sheet'}).click();
  await page.locator('.layer-controls > summary').click();await page.getByRole('checkbox',{name:'Water',exact:true}).check();
  await expect(page.locator('.indicator-legends')).toContainText('Synthetic water indicator');
  await page.locator('.layer-controls > summary').click();
  await page.getByLabel('Scenario',{exact:true}).selectOption('bau_2050');
  await expect.poll(()=>new URL(page.url()).searchParams.get('scenario')).toBe('bau_2050');
  await expect(page.getByLabel('Scenario',{exact:true}).locator('option[value="bau_2040"]')).toBeDisabled();
  await page.getByRole('button',{name:'Show globe view'}).click();await expect(page.getByRole('button',{name:'Show map view'})).toBeVisible();
  await page.getByRole('button',{name:'Show map view'}).click();
  expect(errors).toEqual([]);
  await page.screenshot({path:`output/playwright/${testInfo.project.name}-demo-map.png`,fullPage:true});
});

test('a fresh page waits for facility input and Back returns to it after the first search',async({page})=>{
  const errors:string[]=[];page.on('pageerror',e=>errors.push(e.message));
  let runs=0;page.on('request',request=>{if(new URL(request.url()).pathname.startsWith('/api/runs/'))runs++;});
  await fixtureService(page);await page.goto('/');await expandSheet(page);
  await expect(page.getByRole('button',{name:'Find locations',exact:true})).toBeEnabled();
  await expect(page.getByLabel('Peak IT power MW')).toBeVisible();await expect(page.locator('.region-select')).toHaveCount(0);expect(runs).toBe(0);
  await configureAndSearch(page);await expect(page.locator('.region-select')).toHaveCount(2);
  await page.goBack();await expandSheet(page);
  await expect(page.getByLabel('Peak IT power MW')).toBeVisible();
  await expect(page.locator('.app-header')).toBeVisible();expect(errors).toEqual([]);
});

test('browser Back steps back inside the workspace instead of leaving it',async({page})=>{
  const errors:string[]=[];page.on('pageerror',e=>errors.push(e.message));
  await fixtureService(page);await page.goto('/?run=DEMO_RUN');
  await expect(page.locator('.region-select')).toHaveCount(2);await expandSheet(page);
  await page.getByRole('button',{name:'Select Candidate Alpha, Air / dry (assumed)',exact:true}).click();
  await expect(page.getByRole('complementary',{name:'Details for Candidate Alpha'})).toBeVisible();
  await page.goBack();
  await expect(page.getByRole('complementary',{name:'Details for Candidate Alpha'})).toHaveCount(0);
  await expect.poll(()=>new URL(page.url()).searchParams.get('region')).toBeNull();
  await expect(page.locator('.region-select')).toHaveCount(2);
  await openEditor(page);await page.getByLabel('Peak IT power MW').fill('60');
  await page.goBack();
  await expect(page.getByLabel('Peak IT power MW')).toHaveCount(0);
  await expect(page.getByRole('region',{name:'Evaluated configuration'})).toContainText('100 MW');
  await openEditor(page);await page.getByRole('button',{name:'Back to results'}).click();
  await expect(page.getByLabel('Peak IT power MW')).toHaveCount(0);
  await expect(page.locator('.region-select')).toHaveCount(2);
  await expect(page.locator('.app-header')).toBeVisible();expect(errors).toEqual([]);
});

test('network error and empty response remain explicit without invented candidates',async({page})=>{
  await fixtureService(page,'error',DEMO_CONFIG,false);await page.goto('/');await configureAndSearch(page);
  await expect(page.getByRole('alert')).toContainText('Synthetic test service failure');
  await expect(page.locator('.region-select')).toHaveCount(0);
  await page.unroute(apiRoute);await fixtureService(page,'empty',DEMO_CONFIG,false);await page.getByRole('button',{name:'Retry',exact:false}).click();
  await expect(page.getByText('No regions satisfied the current hard constraints.',{exact:false}).first()).toBeVisible();
  await expect(page.locator('.region-select')).toHaveCount(0);
});

test('real accepted outputs restore actual selection and future water geography',async({page},testInfo)=>{
  const run='development_exploratory__e65828f13b2ef1b2';
  const response=await page.request.get(`/api/runs/${run}`);expect(response.ok()).toBeTruthy();const data=await response.json();
  expect(data.demo).toBe(false);expect(data.regions.length).toBeGreaterThan(0);
  const region=data.regions[0];expect(region.geometry.type).toMatch(/Polygon/);
  await page.goto(`/?run=${run}&region=${encodeURIComponent(region.region_id)}`);
  await expect(page.getByRole('complementary',{name:`Details for ${region.place_label??region.label}`})).toBeVisible();
  await expect(page.getByText('DEMO DATA',{exact:true})).toHaveCount(0);
  await expect.poll(()=>new URL(page.url()).searchParams.get('region')).toBe(region.region_id);
  await expect.poll(()=>Math.abs(Number(new URL(page.url()).searchParams.get('lat'))-region.centroid.lat)).toBeLessThan(1);
  await page.getByRole('button',{name:'Close region details'}).click();
  if(testInfo.project.name==='mobile')await page.getByRole('button',{name:'Minimize bottom sheet'}).click();
  await page.locator('.layer-controls > summary').click();await page.getByRole('checkbox',{name:'Water',exact:true}).check();
  await page.locator('.layer-controls > summary').click();
  await expect(page.locator('.indicator-legends')).toContainText('Basin water stress');
  const current=await (await page.request.get(`/api/layers/water?run_id=${run}&scenario=current`)).json();
  await page.getByLabel('Scenario',{exact:true}).selectOption('bau_2050');
  await expect.poll(()=>new URL(page.url()).searchParams.get('scenario')).toBe('bau_2050');
  const future=await (await page.request.get(`/api/layers/water?run_id=${run}&scenario=bau_2050`)).json();
  expect(future.data.features).toHaveLength(42);expect(future.data.features.map((f:any)=>f.properties.value)).not.toEqual(current.data.features.map((f:any)=>f.properties.value));
  await page.screenshot({path:`output/playwright/${testInfo.project.name}-real-map.png`,fullPage:true});
  await page.getByRole('button',{name:'Reset map to contiguous United States'}).click();
  await expect.poll(()=>Number(new URL(page.url()).searchParams.get('zoom'))).toBeLessThan(5);
  await page.screenshot({path:`output/playwright/${testInfo.project.name}-real-overview.png`,fullPage:true});
});

test('real facility form executes the existing model and plots returned regions',async({page},testInfo)=>{
  test.skip(testInfo.project.name!=='desktop','One actual scientific run verifies the form-to-model integration.');
  test.setTimeout(7_200_000);
  const stages=new Set<string>();
  page.on('response',async response=>{
    if(new URL(response.url()).pathname.startsWith('/api/jobs/')&&response.ok()){
      const job=await response.json();if(job.stage)stages.add(job.stage);
    }
  });
  await page.goto('/');
  await openEditor(page);
  await page.getByText('More options').click();await page.getByLabel('Screening policy').selectOption('EXPLORATORY');
  const submitted=page.waitForRequest(request=>new URL(request.url()).pathname==='/api/search');
  const completed=page.waitForResponse(response=>new URL(response.url()).pathname.startsWith('/api/runs/')&&response.ok(),{timeout:7_140_000});
  await configureAndSearch(page);
  const request=await submitted;expect(request.postDataJSON().facility).toMatchObject({peak_it_power_mw:100,average_load_percent:80});
  const data=await(await completed).json();
  expect(data.demo).toBe(false);expect(data.configuration).toMatchObject({peak_it_power_mw:100,average_load_percent:80});
  expect(data.analysis).toMatchObject({analysis_level:'regional',cell_size_m:1000,maximum_region_extent_km:20,ranking_universe:'all_evaluated_refined_alternatives'});
  expect(data.scope).toContain('partial regional refinement');expect(data.analyzed_cell_count).toBeGreaterThan(42);expect(data.analyzed_cell_count).toBeLessThanOrEqual(200000);expect(data.regions.length).toBeGreaterThan(0);
  await expect(page.locator('.region-select')).toHaveCount(placeCount(data.regions));
  await expect(page.getByText('DEMO DATA',{exact:true})).toHaveCount(0);
  const region=data.regions[0];await page.locator('.region-select').first().click();
  const grid=await page.request.get(`/api/layers/grid?run_id=${encodeURIComponent(data.run_id)}&sublayer=${encodeURIComponent('screening@'+region.region_id)}`);
  expect(grid.ok()).toBeTruthy();const window=await grid.json();expect(window.data.features.length).toBeGreaterThan(0);expect(window.data.features.length).toBeLessThanOrEqual(10000);
  await expect.poll(()=>new URL(page.url()).searchParams.get('region')).toBe(region.region_id);
  await expect.poll(()=>Math.abs(Number(new URL(page.url()).searchParams.get('lat'))-region.centroid.lat)).toBeLessThan(1);
  expect(stages.size).toBeGreaterThan(0);
  await page.screenshot({path:'output/playwright/desktop-real-submission.png',fullPage:true});
});

test('tablet selection keeps map controls reachable and restores the saved facility',async({page},testInfo)=>{
  test.skip(testInfo.project.name!=='desktop','The dedicated tablet viewport is tested once.');
  await page.setViewportSize({width:900,height:900});
  const configuration={...DEMO_CONFIG,peakItPowerMw:120,averageLoadPercent:75};
  await fixtureService(page,'normal',configuration);
  const data=demoRun(configuration);
  await page.goto('/?run=DEMO_RUN');
  await expect(page.locator('.region-select')).toHaveCount(placeCount(data.regions));
  await expandSheet(page);await page.getByRole('button',{name:'Edit facility'}).click();
  await expect(page.getByLabel('Peak IT power MW')).toHaveValue('120');
  await expect(page.getByLabel('Average load percent')).toHaveValue('75');
  await expect(page.getByText('Configuration edited.',{exact:false})).toHaveCount(0);
  const region=data.regions[0];await page.getByRole('button',{name:`Select ${region.label}, Air / dry (assumed)`,exact:true}).click();
  await expect(page.getByRole('complementary',{name:`Details for ${region.label}`})).toBeVisible();
  await expect.poll(()=>Number(new URL(page.url()).searchParams.get('zoom'))).toBeGreaterThan(6);
  await page.getByRole('button',{name:'Show globe view'}).click();
  await page.getByRole('button',{name:'Show map view'}).click();
  await page.getByRole('button',{name:'Reset map to contiguous United States'}).click();
  await expect(page.locator('.app-header')).toBeInViewport();
  expect(await page.locator('.locator-app').evaluate(el=>el.scrollTop)).toBe(0);
  await page.screenshot({path:'output/playwright/tablet-demo-map.png',fullPage:true});
});
