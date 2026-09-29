// Real streamed touch controls: woodland trail, porch, jetty and water recovery.
import {chromium,CHROME,STREAM_URL,buildDir} from '../../../platform/web/stream/smoke.mjs';
const BUILD=buildDir('yorimichi');
import fs from 'node:fs/promises';
const out=new URL('forest_lake/phone/',BUILD);await fs.mkdir(out,{recursive:true});
const world=JSON.parse(await fs.readFile(new URL('world.json',BUILD),'utf8'));
const browser=await chromium.launch({executablePath:CHROME,headless:true,args:['--autoplay-policy=no-user-gesture-required']});
const context=await browser.newContext({viewport:{width:844,height:390},hasTouch:true,isMobile:true});const page=await context.newPage();let active=false;
const report={samples:[]};let yaw=0;
try{
 await page.goto(STREAM_URL);await page.waitForFunction(()=>window.yorimichi?.state?.ready,{},{timeout:60000});await page.locator('#play').click();await page.waitForFunction(()=>document.querySelector('video')?.currentTime>0,{},{timeout:30000});
 const cdp=await context.newCDPSession(page),b=await page.locator('#stick').boundingBox();const cx=b.x+b.width/2,cy=b.y+b.height/2;
 async function stop(){if(active){await cdp.send('Input.dispatchTouchEvent',{type:'touchEnd',touchPoints:[]});active=false;}await page.waitForTimeout(250);}
 async function route(points,label){
  for(const [tx,ty] of points){let reached=false;const start=Date.now();while(Date.now()-start<7000){
   const s=await page.evaluate(()=>window.yorimichi.state);report.samples.push({...s,section:label});let dx=tx-s.x/100,dy=-ty-s.y/100,d=Math.hypot(dx,dy);if(d<.65){reached=true;break;}
   const scale=Math.min(.65,d/2),mx=(-Math.sin(yaw)*dx+Math.cos(yaw)*dy)/d*scale,my=(Math.cos(yaw)*dx+Math.sin(yaw)*dy)/d*scale;
   if(!active){await cdp.send('Input.dispatchTouchEvent',{type:'touchStart',touchPoints:[{x:cx,y:cy,id:1}]});active=true;}
   await cdp.send('Input.dispatchTouchEvent',{type:'touchMove',touchPoints:[{x:cx+mx*b.width*.35,y:cy-my*b.width*.35,id:1}]});await page.waitForTimeout(120);
  }if(!reached)throw Error(`Blocked ${label} at ${tx},${ty}`);}
  await stop();
 }
 if(process.argv.includes('--preview')){
  await page.locator('#map-button').tap();await page.locator('.map-pin[data-key="forest_lake"]').tap();await page.waitForTimeout(1800);
  report.release=await page.evaluate(()=>window.yorimichi.state);await page.screenshot({path:new URL('release.png',out).pathname});
  if(Math.hypot(report.release.x+5400,report.release.y+22300)>120||report.release.falling)throw Error('Unsafe map arrival');report.passed=true;
 }else{
 await page.locator('#map-button').tap();await page.locator('.map-pin[data-key="mega"]').tap();await page.waitForTimeout(1200);yaw=(await page.evaluate(()=>window.yorimichi.state.yaw))*Math.PI/180;
 const path=world.forest_lake.trail.filter((p,i)=>i%5===0);path.push(world.forest_lake.trail.at(-1));await route(path,'forest-trail');report.trailArrival=await page.evaluate(()=>window.yorimichi.state);
 await page.screenshot({path:new URL('arrival.png',out).pathname});
 function local(x,y){const a=-135*Math.PI/180;return[-56+x*Math.cos(a)-y*Math.sin(a),215+x*Math.sin(a)+y*Math.cos(a)];}
 await route([local(-2,-4.65),local(-2,-3.65),local(0,-3.65),local(0,-6),local(0,-9),local(0,-12),local(-.4,-13.5)],'porch-and-jetty');
 report.jetty=await page.evaluate(()=>window.yorimichi.state);if(report.jetty.z<7600||report.jetty.falling)throw Error('No stable pier support');await page.screenshot({path:new URL('jetty.png',out).pathname});
 // Walk off the end and verify automatic return to the dry shoreline.
 const target=local(0,-20);const s=await page.evaluate(()=>window.yorimichi.state);const dx=target[0]-s.x/100,dy=-target[1]-s.y/100,d=Math.hypot(dx,dy);const mx=(-Math.sin(yaw)*dx+Math.cos(yaw)*dy)/d,my=(Math.cos(yaw)*dx+Math.sin(yaw)*dy)/d;
 await cdp.send('Input.dispatchTouchEvent',{type:'touchStart',touchPoints:[{x:cx,y:cy,id:1}]});active=true;await cdp.send('Input.dispatchTouchEvent',{type:'touchMove',touchPoints:[{x:cx+mx*40,y:cy-my*40,id:1}]});
 await page.waitForFunction(()=>{const s=window.yorimichi.state;return Math.hypot(s.x+5400,s.y+22300)<150;},{},{timeout:8000});await stop();report.recovery=await page.evaluate(()=>window.yorimichi.state);
 await page.locator('#map-button').tap();await page.locator('.map-pin[data-key="forest_lake"]').tap();await page.waitForTimeout(1000);report.mapArrival=await page.evaluate(()=>window.yorimichi.state);report.passed=true;
 }
}catch(e){report.error=String(e);await page.screenshot({path:new URL('failure.png',out).pathname}).catch(()=>{});throw e;}
finally{await fs.writeFile(new URL(process.argv.includes('--preview')?'release-check.json':'result.json',out),JSON.stringify(report,null,2));await page.locator('#spawn').tap().catch(()=>{});await browser.close();}
