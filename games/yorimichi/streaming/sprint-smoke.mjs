import {chromium} from '@playwright/test';
import fs from 'node:fs/promises';
const out=new URL('../out/sprint/',import.meta.url);
const browser=await chromium.launch({executablePath:'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',headless:true,args:['--autoplay-policy=no-user-gesture-required']});
const context=await browser.newContext({viewport:{width:844,height:390},hasTouch:true,isMobile:true});const page=await context.newPage();const report={};
let original=2;
const state=()=>page.evaluate(()=>window.yorimichi.state);
async function rings(n){await page.locator('#settings-button').tap();await page.locator('#setting-stamina_rings').evaluate((el,n)=>{el.value=n;el.dispatchEvent(new Event('change',{bubbles:true}));},n);await page.waitForFunction(n=>window.yorimichi.state.staminaRings===n,n);await page.locator('#close-settings').tap();}
try {
 await page.goto('http://127.0.0.1:8080');await page.waitForFunction(()=>window.yorimichi?.state?.ready,{},{timeout:60000});await page.locator('#play').click();
 await page.waitForTimeout(1000);original=(await state()).staminaRings;report.initialRings=original;
 await rings(3);if(await page.locator('#stamina .stamina-fill').count()!==3)throw Error('Ring count not reflected');
 const disk=await fs.readFile(new URL('../unreal/Saved/settings.txt',import.meta.url),'utf8');if(!disk.includes('stamina_rings=3'))throw Error('Capacity not saved');
 await rings(1);await page.locator('#spawn').tap();await page.waitForTimeout(600);
 const cdp=await context.newCDPSession(page),box=await page.locator('#stick').boundingBox();const left={x:box.x+box.width/2,y:box.y+box.height/2-42,id:1};
 await cdp.send('Input.dispatchTouchEvent',{type:'touchStart',touchPoints:[left]});
 await page.waitForTimeout(1400);report.run=await state();
 if(Math.abs(report.run.speed-580)>20)throw Error('Default speed not 2x');
 const jogBox=await page.locator('[data-bit="32"]').boundingBox(),jog={x:jogBox.x+20,y:jogBox.y+20,id:2};
 await cdp.send('Input.dispatchTouchEvent',{type:'touchStart',touchPoints:[left,jog]});await page.waitForTimeout(1000);report.jog=await state();
 if(Math.abs(report.jog.speed-290)>20)throw Error('Jog not 1x');
 await cdp.send('Input.dispatchTouchEvent',{type:'touchEnd',touchPoints:[jog]});
 const b=await page.locator('#sprint').boundingBox(),sprint={x:b.x+b.width/2,y:b.y+b.height/2,id:3};
 await cdp.send('Input.dispatchTouchEvent',{type:'touchStart',touchPoints:[left,sprint]});await page.waitForTimeout(1500);report.sprint=await state();
 if(Math.abs(report.sprint.speed-725)>20||!report.sprint.sprinting||report.sprint.stamina>=1)throw Error('Held touch sprint not draining at 2.5x');
 await page.screenshot({path:new URL('sprinting.png',out).pathname});
 await page.waitForFunction(()=>window.yorimichi.state.exhausted,{},{timeout:7000});report.exhausted=await state();
 await page.waitForTimeout(4500);report.heldEmpty=await state();if(report.heldEmpty.sprinting||!report.heldEmpty.exhausted)throw Error('Held button restarted after exhaustion');
 await cdp.send('Input.dispatchTouchEvent',{type:'touchEnd',touchPoints:[sprint]});await page.waitForTimeout(500);if((await state()).exhausted)throw Error('Full gauge did not unlock after release');
 await cdp.send('Input.dispatchTouchEvent',{type:'touchEnd',touchPoints:[]});
 await page.locator('#spawn').tap();await rings(2);await page.screenshot({path:new URL('two-rings.png',out).pathname});
 report.passed=true;console.log(JSON.stringify(report,null,2));
} catch(e){report.error=String(e);report.last=await state().catch(()=>null);await page.screenshot({path:new URL('failure.png',out).pathname}).catch(()=>{});throw e;}
finally{await fs.writeFile(new URL('phone-results.json',out),JSON.stringify(report,null,2));await page.keyboard.up('KeyW').catch(()=>{});await page.locator('#spawn').tap().catch(()=>{});await rings(original).catch(()=>{});await browser.close();}
