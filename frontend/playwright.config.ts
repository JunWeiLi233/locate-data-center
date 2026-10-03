import {defineConfig,devices} from '@playwright/test';
export default defineConfig({
  testDir:'./e2e',timeout:60000,expect:{timeout:15000},fullyParallel:false,workers:1,
  reporter:[['list'],['html',{open:'never'}]],
  use:{baseURL:process.env.LOCATOR_E2E_URL??'http://127.0.0.1:5173',channel:'chrome',headless:true,trace:'retain-on-failure',screenshot:'only-on-failure',launchOptions:{args:['--enable-webgl','--use-angle=swiftshader','--enable-unsafe-swiftshader']}},
  projects:[{name:'desktop',use:{viewport:{width:1440,height:1000}}},{name:'mobile',use:{...devices['Pixel 7'],defaultBrowserType:'chromium'}}],
});
