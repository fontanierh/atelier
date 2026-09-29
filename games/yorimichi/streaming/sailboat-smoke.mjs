// Actual Pixel Streaming transport, touch controls and modal reset regression.
import {chromium} from '@playwright/test';
import fs from 'node:fs/promises';
const out=new URL('../out/pixel-streaming/',import.meta.url);
await fs.mkdir(out,{recursive:true});
const browser=await chromium.launch({executablePath:'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',headless:true,args:['--autoplay-policy=no-user-gesture-required']});
const context=await browser.newContext({viewport:{width:844,height:390},hasTouch:true,isMobile:true}),page=await context.newPage(),cdp=await context.newCDPSession(page);
const report={};let touches=[];
async function touch(id,selector,down){
 if(down){const b=await page.locator(selector).boundingBox();if(!b)throw Error('Missing control '+selector);touches.push({id,x:b.x+b.width/2,y:b.y+b.height/2});}else touches=touches.filter(t=>t.id!==id);
 await cdp.send('Input.dispatchTouchEvent',{type:down?'touchStart':touches.length?'touchMove':'touchEnd',touchPoints:touches});
}
const state=()=>page.evaluate(()=>window.yorimichi.state);
// A real finger stays down across several game frames. Instant CDP tap can put
// drive=1 and drive=0 into the same native tick, so no propulsion input is sampled.
async function drive(selector){await touch(7,selector,true);await page.waitForTimeout(160);await touch(7,selector,false);}
const angleDelta=(a,b)=>((a-b+540)%360)-180;
try{
 await page.goto(process.env.STREAM_URL||'http://127.0.0.1:8080');
 await page.waitForFunction(()=>window.yorimichi?.state?.ready,{},{timeout:90000});await page.click('#play');
 await page.locator('#spawn').tap();await page.waitForTimeout(600);
 await page.locator('#map-button').tap();await page.waitForFunction(()=>window.yorimichi.map?.zones?.length);
 // Pins near the southwest shore overlap at whole-world zoom. The visible list
 // is the same travel action, with an unambiguous touch target for this control test.
 const cove=page.locator('#map-zones button[data-key="cove"]');
 await cove.scrollIntoViewIfNeeded();await cove.tap();
 await page.waitForFunction(()=>!document.getElementById('map-dialog').open);
 await page.waitForFunction(()=>{const s=window.yorimichi.state;return Math.hypot(s.x+21600,s.y-16900)<600&&!s.falling;},{},{timeout:10000});
 await page.locator('#sailboat').tap();await page.waitForFunction(()=>window.yorimichi.state.sailboat,{},{timeout:7000});
 if(await page.locator('#stick').isVisible()||!await page.locator('#skate-steering').isVisible())throw Error('Sailing control layout missing');
 if(await page.locator('#push').innerText()!=='Raise sail'||await page.locator('#brake').innerText()!=='Lower sail')throw Error('Sailing labels incorrect');
 await drive('#push');await page.waitForFunction(()=>window.yorimichi.state.speed>500,{},{timeout:10000});
 report.cruise=await state();
 await page.waitForTimeout(700);if((await state()).speed<500)throw Error('Released raise lost propulsion');
 await touch(1,'[data-turn="-1"]',true);await page.waitForTimeout(650);await touch(1,'[data-turn="-1"]',false);
 report.left=await state();if(Math.abs(angleDelta(report.left.yaw,report.cruise.yaw))<8)throw Error('Touch steering did not turn');
 // Simultaneous propulsion + steering, then cancellation clears all held controls.
 await touch(1,'#push',true);await touch(2,'[data-turn="1"]',true);await page.waitForTimeout(300);
 await cdp.send('Input.dispatchTouchEvent',{type:'touchCancel',touchPoints:[]});touches=[];
 await page.waitForFunction(()=>document.querySelectorAll('.held').length===0,{},{timeout:2000});
 await page.locator('#settings-button').tap();
 await page.waitForFunction(()=>window.yorimichi.settings?.length&&document.getElementById('setting-stamina_rings'));
 report.settings=await page.evaluate(()=>window.yorimichi.settings.map(row=>({key:row.key,present:!!document.getElementById('setting-'+row.key),value:Number(document.getElementById('setting-'+row.key)?.value),expected:row.value,tolerance:Math.max(.011,Number(document.getElementById('setting-'+row.key)?.step||0)/2+.001)})));
 if(report.settings.some(row=>!row.present||Math.abs(row.value-row.expected)>row.tolerance))throw Error('Settings controls disagree with native values');
 await page.waitForFunction(()=>window.yorimichi.state.speed<1,{},{timeout:3000});
 report.menu=await state();if(report.menu.speed>1)throw Error('Settings did not stop boat');
 await page.locator('#close-settings').tap();await page.waitForTimeout(500);if((await state()).speed>1)throw Error('Boat resumed without Raise');
 await drive('#push');await page.waitForFunction(()=>window.yorimichi.state.speed>100);
 await drive('#brake');await page.waitForFunction(()=>window.yorimichi.state.speed<1,{},{timeout:4000});
 report.stopped=await state();
 await page.screenshot({path:new URL('phone-sailboat.png',out).pathname});
 await drive('#push');await page.waitForFunction(()=>window.yorimichi.state.speed>100);
 await page.evaluate(()=>window.dispatchEvent(new Event('blur')));
 await page.locator('#play').waitFor({state:'visible'});
 if(await page.locator('#play').innerText()!=='Resume Yorimichi')throw Error('Suspend did not offer resume');
 await page.waitForFunction(()=>window.yorimichi.state.speed<1,{},{timeout:3000});
 report.suspended=await state();if(report.suspended.speed>1)throw Error('Phone suspension did not stop boat');
 await page.locator('#play').tap();await page.waitForFunction(()=>!document.getElementById('controls').hidden);await page.locator('#push').waitFor({state:'visible'});await page.locator('#skate-steering').waitFor({state:'visible'});await page.locator('#spawn').tap();await page.waitForFunction(()=>{const s=window.yorimichi.state;return !s.sailboat&&!s.skating&&!s.falling;},{},{timeout:10000});
 if(!await page.locator('#stick').isVisible())throw Error('Foot joystick did not return');
 report.returned=await state();report.passed=true;
 await fs.writeFile(new URL('sailboat-smoke.json',out),JSON.stringify(report,null,2));console.log('PASS',JSON.stringify(report));
}catch(error){
 report.passed=false;report.error=String(error?.stack||error);
 await fs.writeFile(new URL('sailboat-smoke.json',out),JSON.stringify(report,null,2));
 await page.screenshot({path:new URL('sailboat-smoke-failure.png',out).pathname}).catch(()=>{});
 throw error;
}finally{
 await cdp.send('Input.dispatchTouchEvent',{type:'touchCancel',touchPoints:[]}).catch(()=>{});
 await page.locator('#spawn').tap({timeout:1000}).catch(()=>{});await browser.close();
}
