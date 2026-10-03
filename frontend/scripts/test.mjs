import { mkdirSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';
const root=fileURLToPath(new URL('../',import.meta.url));
const temp=fileURLToPath(new URL('../.tmp/',import.meta.url));
mkdirSync(temp,{recursive:true});
const result=spawnSync(process.execPath,[fileURLToPath(new URL('../node_modules/vitest/vitest.mjs',import.meta.url)),'run',...process.argv.slice(2)],{cwd:root,stdio:'inherit',env:{...process.env,TEMP:temp,TMP:temp}});
process.exit(result.status??1);
