// Browser-only menu checks; this never talks to or restarts a running game.
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import {chromium,CHROME} from '../../../platform/web/stream/smoke.mjs';

const browser=await chromium.launch({executablePath:CHROME,headless:true,args:['--disable-gpu']});
const page=await browser.newPage();
let accept=false,warnings=[];
page.on('dialog',async dialog=>{warnings.push(dialog.message());if(accept)await dialog.accept();else await dialog.dismiss();});
try{
 await page.setContent('<div id="settings-rows"></div>');
 const source=await fs.readFile(new URL('./settings.js',import.meta.url),'utf8');
 await page.addScriptTag({type:'module',content:source.replace('export function renderSettings','window.renderSettings=function renderSettings')});
 await page.waitForFunction(()=>typeof window.renderSettings==='function');
 async function render({renderer=0,running=0,restart=true,trees=1}={}){
  warnings=[];
  await page.evaluate(({renderer,running,restart,trees})=>{
   window.changes=[];
   window.renderSettings([
    {key:'renderer',label:'Lighting',value:renderer,min:0,max:1,running,restart_supported:restart},
    {key:'tree_optimization',label:'Tree optimization',value:trees,min:0,max:1},
   ],(key,value)=>window.changes.push({key,value}));
  },{renderer,running,restart,trees});
 }
 const changes=()=>page.evaluate(()=>window.changes);
 await render();
 assert.equal(await page.locator('#settings-rows select').count(),2,'graphics choices must not be generic sliders');
 await page.selectOption('#setting-renderer','1');
 assert.deepEqual(await changes(),[],'cancel must send no renderer mutation');
 assert.equal(await page.inputValue('#setting-renderer'),'0','cancel must restore the saved choice');
 assert.match(warnings[0],/resource hog/);assert.match(warnings[0],/Restart now/);
 accept=true;
 await page.selectOption('#setting-renderer','1');
 assert.deepEqual(await changes(),[{key:'renderer',value:1}],'confirmed Lumen sends its exact enum');
 await render({restart:false});
 await page.selectOption('#setting-renderer','1');
 assert.match(warnings[0],/next launch/);assert.doesNotMatch(warnings[0],/Restart now/);
 await render();accept=false;
 await page.selectOption('#setting-tree_optimization','0');
 assert.deepEqual(await changes(),[],'cancel must keep optimized trees');
 assert.equal(await page.inputValue('#setting-tree_optimization'),'1');
 assert.match(warnings[0],/more GPU time/);
 accept=true;await page.selectOption('#setting-tree_optimization','0');
 assert.deepEqual(await changes(),[{key:'tree_optimization',value:0}]);
 await render({trees:0});accept=false;
 await page.selectOption('#setting-tree_optimization','1');
 assert.equal(warnings.length,0,'returning to optimized trees needs no resource warning');
 assert.deepEqual(await changes(),[{key:'tree_optimization',value:1}]);
 await render({renderer:1,running:0,restart:false});
 assert.equal(await page.locator('output').first().textContent(),'Restart pending');
 console.log('PASS graphics menu choices, cancellation, confirmation, restart messaging and tree toggles');
}finally{await browser.close();}
