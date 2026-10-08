// Real multi-touch input over the local iPhone streaming frontend.
import {openTouchPage,playTouchPage,buildDir} from '../../../platform/web/stream/smoke.mjs';
const BUILD=buildDir('yorimichi');
import fs from 'node:fs/promises';
const out=new URL('cape_boy/double-jump/phone/',BUILD);
await fs.mkdir(out,{recursive:true});
const {browser,context,page}=await openTouchPage();
try {
 await playTouchPage(page,{telemetry:'yorimichi',video:{timeout:60000}});
 await page.evaluate(()=>{window.jumpEvents=[];for(const type of ['pointerdown','pointerup','pointercancel','lostpointercapture'])document.getElementById('jump').addEventListener(type,e=>window.jumpEvents.push({type,id:e.pointerId,time:Date.now()}));});
 const cdp=await context.newCDPSession(page);
 const box=await page.locator('#stick').boundingBox(),jump=await page.locator('#jump').boundingBox();
 const centre={x:box.x+box.width/2,y:box.y+box.height/2,id:1};
 const moving={...centre,y:centre.y-44};
 const button={x:jump.x+jump.width/2,y:jump.y+jump.height/2,id:2};
 const send=(type,touchPoints)=>cdp.send('Input.dispatchTouchEvent',{type,touchPoints});
 async function trial(name,double,third=false,hold=false){
  await page.locator('#spawn').tap();await page.waitForTimeout(500);
  await page.waitForFunction(()=>!window.yorimichi.state.falling&&window.yorimichi.state.speed<1);
  await send('touchStart',[centre]);await send('touchMove',[moving]);await page.waitForTimeout(1200);
  const start=await page.evaluate(()=>window.yorimichi.state),time=Date.now();
  await send('touchStart',[moving,button]);await page.waitForTimeout(hold?1050:45);
  await send('touchEnd',[button]);
  if(double){
   await page.waitForTimeout(170);await send('touchStart',[moving,button]);await page.waitForTimeout(45);await send('touchEnd',[button]);
   if(third){await page.waitForTimeout(100);await send('touchStart',[moving,button]);await page.waitForTimeout(45);await send('touchEnd',[button]);}
   if(!third){
    await page.waitForTimeout(100);
    for(let i=0;i<5;i++){await page.screenshot({path:new URL(`flip-${i}.png`,out).pathname});await page.waitForTimeout(70);}
   }
  }
  await page.waitForTimeout(1600);
  const history=await page.evaluate(t=>window.yorimichi.history.filter(s=>s.time>=t),time);
  await send('touchEnd',[]);
  if(!history.some(s=>s.falling))throw Error(name+': never airborne');
  if(history.at(-1).falling)throw Error(name+': did not land');
  const height=Math.max(...history.map(s=>s.z))-start.z;
  const displacement=Math.hypot(history.at(-1).x-start.x,history.at(-1).y-start.y);
  await fs.writeFile(new URL(name+'.json',out),JSON.stringify({start,height,displacement,history,events:await page.evaluate(()=>window.jumpEvents)},null,2));
  if(displacement<800)throw Error(name+': forward travel stopped');
  return {name,height_cm:height,displacement_cm:displacement,history};
 }
 const single=await trial('single-held',false,false,true);
 const double=await trial('double',true);
 const third=await trial('third-rejected',true,true);
 if(double.height_cm<single.height_cm+60)throw Error('Second tap did not add height');
 if(third.height_cm>double.height_cm+35)throw Error('Third tap added another jump');
 await page.locator('#spawn').tap();await page.waitForTimeout(600);
 const result={passed:true,single,double,third};await fs.writeFile(new URL('result.json',out),JSON.stringify(result,null,2));
 console.log('PHONE DOUBLE JUMP PASS',JSON.stringify({single:single.height_cm,double:double.height_cm,third:third.height_cm}));
}finally{await browser.close();}
