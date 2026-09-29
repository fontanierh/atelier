// Manual live-stream diagnostic. Uses the single player slot and returns to spawn.
// Reports sampled native FPS separately from actual decoded video throughput.
import {chromium,CHROME,STREAM_URL,buildDir} from '../../../platform/web/stream/smoke.mjs';
const BUILD=buildDir('yorimichi');
import fs from 'node:fs/promises';
const url=STREAM_URL;
const label=process.argv[2]||'stream-performance';
const out=new URL('stream/smoke/',BUILD);await fs.mkdir(out,{recursive:true});
const health=await(await fetch(new URL('/health',url))).json();
if(health.players)throw Error('A player is already connected; do not displace the phone.');
const browser=await chromium.launch({executablePath:CHROME,headless:true,args:['--autoplay-policy=no-user-gesture-required']});
try{
 const page=await browser.newPage({viewport:{width:844,height:390},hasTouch:true,isMobile:true});
 await page.addInitScript(()=>{window.testPeers=[];const Base=window.RTCPeerConnection;window.RTCPeerConnection=class extends Base{constructor(...args){super(...args);window.testPeers.push(this);}};});
 await page.goto(url);
 await page.waitForFunction(()=>window.yorimichi?.state?.ready,null,{timeout:45000});
 await page.locator('#play').click();
 await page.waitForFunction(()=>document.querySelector('video')?.videoWidth>0);
 await page.waitForTimeout(3000);
 const sample=()=>page.evaluate(async()=>{
  const reports=(await Promise.all(window.testPeers.map(async p=>[...await p.getStats()].map(x=>x[1])))).flat();
  return {time:performance.now(),native:window.yorimichi.state,
   video:reports.find(r=>r.type==='inbound-rtp'&&r.kind==='video'),
   rtt:reports.find(r=>r.type==='candidate-pair'&&r.nominated&&r.state==='succeeded')?.currentRoundTripTime};
 });
 const phases=[];
 for(const phase of ['idle','sprint']){
  if(phase==='sprint'){await page.keyboard.down('ShiftLeft');await page.keyboard.down('KeyW');}
  await page.evaluate(()=>window.yorimichi.history.length=0);
  const start=await sample();await page.waitForTimeout(10000);const end=await sample();
  await page.keyboard.up('KeyW');await page.keyboard.up('ShiftLeft');
  const history=await page.evaluate(()=>window.yorimichi.history);
  const fps=history.map(s=>s.fps).filter(Number.isFinite).sort((a,b)=>a-b);
  const q=v=>fps[Math.round((fps.length-1)*v)];
  const frames=end.video.framesDecoded-start.video.framesDecoded;
  if(frames<=0||history.length<20)throw Error('Insufficient video/native telemetry for '+phase);
  if(phase==='sprint'&&Math.hypot(end.native.x-start.native.x,end.native.y-start.native.y)<100)throw Error('Movement did not reach the game');
  phases.push({phase,decodedFps:1000*frames/(end.time-start.time),nativeFps:{p05:q(.05),median:q(.5),p95:q(.95)},
   deltaDropped:end.video.framesDropped-start.video.framesDropped,
   deltaFreezes:(end.video.freezeCount||0)-(start.video.freezeCount||0),
   distanceCm:Math.hypot(end.native.x-start.native.x,end.native.y-start.native.y),start,end,history});
  await page.screenshot({path:new URL(`${label}-${phase}.png`,out).pathname});
 }
 await page.locator('#spawn').tap();
 await fs.writeFile(new URL(`${label}.json`,out),JSON.stringify({url,phases},null,2));
 console.log(JSON.stringify(phases.map(({phase,decodedFps,nativeFps,deltaDropped,deltaFreezes,distanceCm})=>({phase,decodedFps,nativeFps,deltaDropped,deltaFreezes,distanceCm})),null,2));
}finally{await browser.close();}
