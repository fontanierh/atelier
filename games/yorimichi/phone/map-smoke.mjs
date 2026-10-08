// World map on the phone page: opens the map, checks the sheet, the pins and the player marker, travels to a zone
// by tapping its pin, confirms the game moved there, then returns to spawn. Needs a running stream
// (atelier stream yorimichi start [--local]); STREAM_URL selects another endpoint or port.
import {openTouchPage,playTouchPage,buildDir} from '../../../platform/web/stream/smoke.mjs';
const BUILD=buildDir('yorimichi');
import fs from 'node:fs/promises';
const out=new URL('stream/smoke/',BUILD);await fs.mkdir(out,{recursive:true});
const {browser,page}=await openTouchPage();const events=[];
page.on('console',m=>{events.push(m.type()+': '+m.text());if(m.type()==='error')console.log(m.text());});
page.on('pageerror',e=>{events.push('PAGE ERROR '+e.message);console.log('PAGE ERROR',e.message)});
const report={};
try{
 await playTouchPage(page,{telemetry:'yorimichi',ready:90000,video:{timeout:60000}});
 await page.waitForTimeout(1000);
 report.start=await page.evaluate(()=>window.yorimichi.state);
 // (The phone page has had no skateboard button since the player changed on 7 September; the travel checks below still
 // refuse carried equipment or momentum.)
 // open the map: the game answers with the sheet bounds and the zones, the page draws pins and the player
 await page.locator('#map-button').tap();
 await page.waitForFunction(()=>window.yorimichi.map?.zones?.length>0&&document.querySelectorAll('.map-pin').length>0,{},{timeout:10000});
 await page.waitForFunction(()=>{const i=document.getElementById('map-image');return i.complete&&i.naturalWidth>0;},{},{timeout:20000});
 const sheet=await page.evaluate(()=>({image:document.getElementById('map-image').naturalWidth+'x'+document.getElementById('map-image').naturalHeight,frame:document.getElementById('map-frame').getBoundingClientRect().toJSON(),pins:document.querySelectorAll('.map-pin').length,list:document.querySelectorAll('#map-zones button').length,player:!document.getElementById('map-player').hidden,playerStyle:document.getElementById('map-player').getAttribute('style'),zones:window.yorimichi.map.zones.map(z=>z.key)}));
 console.log('MAP',sheet);report.sheet=sheet;
 if(sheet.pins<10||sheet.list!==sheet.pins)throw Error('Map pins missing');
 if(!sheet.player)throw Error('Player marker hidden');
 await page.screenshot({path:new URL('phone-map.png',out).pathname});
 // travel to the clock square by its pin
 const target=(await page.evaluate(()=>window.yorimichi.map.zones)).find(z=>z.key==='plaza')||(await page.evaluate(()=>window.yorimichi.map.zones))[1];
 await page.locator(`.map-pin[data-key="${target.key}"]`).tap();
 await page.waitForFunction(t=>{const p=window.yorimichi.state;return p&&Math.hypot(p.x/100-t.x,-p.y/100-t.y)<6&&!p.falling;},target,{timeout:8000});
 await page.waitForTimeout(800);
 report.travelled=await page.evaluate(()=>window.yorimichi.state);console.log('TRAVELLED',target.key,report.travelled);
 if(report.travelled.skating||report.travelled.sailboat||report.travelled.speed>1)throw Error('Travel retained equipment or momentum');
 if(await page.locator('#map-dialog').evaluate(d=>d.open))throw Error('Map dialog should close after travelling');
 await page.screenshot({path:new URL('phone-map-arrived.png',out).pathname});
 // reopen: the marker must now sit at the zone's pin
 await page.locator('#map-button').tap();
 await page.waitForTimeout(600);
 const marker=await page.evaluate(k=>{const c=r=>[r.x+r.width/2,r.y+r.height/2],m=c(document.getElementById('map-player').getBoundingClientRect()),p=c(document.querySelector(`.map-pin[data-key="${k}"]`).getBoundingClientRect());return Math.hypot(m[0]-p[0],m[1]-p[1]);},target.key);
 console.log('MARKER distance to pin px',marker.toFixed(1));report.markerToPinPx=marker;
 if(marker>14)throw Error('Player marker not on the travelled pin');
 await page.screenshot({path:new URL('phone-map-reopened.png',out).pathname});
 await page.locator('#close-map').tap();
 // travel from the list too, then home
 await page.locator('#map-button').tap();await page.waitForTimeout(300);
 const second=(await page.evaluate(()=>window.yorimichi.map.zones)).find(z=>z.key==='landing');
 await page.locator(`#map-zones button[data-key="${second.key}"]`).tap();
 await page.waitForFunction(t=>{const p=window.yorimichi.state;return p&&Math.hypot(p.x/100-t.x,-p.y/100-t.y)<6&&!p.falling;},second,{timeout:8000});
 report.second=await page.evaluate(()=>window.yorimichi.state);console.log('LIST TRAVEL',second.key,report.second);
 await page.locator('#spawn').tap();
 try{await page.waitForFunction(s=>{const p=window.yorimichi.state;return !p.falling&&Math.hypot(p.x-s.x,p.y-s.y)<100;},report.start,{timeout:12000});}
 catch(e){console.log('SPAWN STATE',await page.evaluate(()=>window.yorimichi.state),'START',report.start);throw e;}
 await fs.writeFile(new URL('map-smoke.json',out),JSON.stringify(report,null,2));console.log('PASS');
}finally{await fs.writeFile(new URL('map-browser.log',out),events.join('\n'));await browser.close();}
