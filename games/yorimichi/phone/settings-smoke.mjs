import {openTouchPage,playTouchPage,buildDir} from '../../../platform/web/stream/smoke.mjs';
const BUILD=buildDir('yorimichi');
import fs from 'node:fs/promises';
const {browser,page}=await openTouchPage({args:[]});
const errors=[];page.on('pageerror',e=>errors.push(e.message));
const settingsFile=new URL('../unreal/Saved/settings.txt',import.meta.url);
const out=new URL('stream/smoke/',BUILD);await fs.mkdir(out,{recursive:true});
let original=[];
// Desktop tuning stays session-only. Graphics choices have separate browser menu tests;
// a renderer restart or a costly tree mode must never be an incidental effect of this live smoke run.
const saved=()=>original.filter(r=>r.key!=='desktop'&&r.key!=='renderer'&&r.key!=='tree_optimization');
async function request(){await page.evaluate(()=>window.yorimichi.stream.emitUIInteraction({yorimichi:1,action:'settings'}));}
async function set(key,value){
 await page.evaluate(()=>window.yorimichi.settings=null);
 await page.evaluate(({key,value})=>window.yorimichi.stream.emitUIInteraction({yorimichi:1,action:'setSetting',key,value}),{key,value});
 await page.waitForFunction(({key,value})=>Math.abs((window.yorimichi.settings?.find(s=>s.key===key)?.value??-999)-value)<.001,{key,value},{timeout:8000});
 const saved=await fs.readFile(settingsFile,'utf8');const line=saved.split('\n').find(x=>x.startsWith(key+'='));
 if(!line||Math.abs(Number(line.split('=')[1])-value)>.001)throw Error(key+' not saved');
}
try{
 await playTouchPage(page,{telemetry:'yorimichi'});await page.click('#settings-button');await page.waitForFunction(()=>window.yorimichi.settings?.length>0);
 original=await page.evaluate(()=>window.yorimichi.settings);
 if(await page.locator('#settings-rows input,#settings-rows select').count()!==original.length)throw Error('Missing settings controls');
 // Drive a real rendered range control, then verify the authoritative response and disk.
 await page.locator('#setting-cam_dist').evaluate(el=>{el.value='620';el.dispatchEvent(new Event('input',{bubbles:true}));el.dispatchEvent(new Event('change',{bubbles:true}));});
 await page.waitForFunction(()=>window.yorimichi.settings.find(s=>s.key==='cam_dist').value===620);
 for(const row of saved()){const value=['performance','goofy','show_fps'].includes(row.key)?1-row.value:row.key==='stamina_rings'?(row.value===5?2:row.value+1):Math.min(row.max,row.value+(row.max-row.min)*.05);await set(row.key,value);}
 for(const row of saved())await set(row.key,row.value);
 await set('stamina_rings',4);
 await page.waitForFunction(()=>window.yorimichi.state.staminaRings===4);
 await page.screenshot({path:new URL('phone-settings.png',out).pathname});
 await fs.writeFile(new URL('settings-smoke.json',out),JSON.stringify({settings:original.map(s=>s.key),staminaRings:4,errors},null,2));
 if(errors.length)throw Error(errors.join('\n'));
 console.log('PASS',original.length,'settings; stamina capacity updated');
}finally{
 for(const row of saved())try{await set(row.key,row.value)}catch{}
 if(original.length){try{await page.locator('#close-settings').click();await page.locator('#spawn').tap();await page.waitForTimeout(500)}catch{}}
 await browser.close();
}
