// Verify the painted map while standing on the actual mini-mega deck.
import {chromium,CHROME,STREAM_URL,buildDir} from '../../../platform/web/stream/smoke.mjs';
const BUILD=buildDir('yorimichi');
import fs from 'node:fs/promises';
const out=new URL('map/mini-mega-fix/phone/',BUILD);await fs.mkdir(out,{recursive:true});
const browser=await chromium.launch({executablePath:CHROME,headless:true,args:['--autoplay-policy=no-user-gesture-required']});
const context=await browser.newContext({viewport:{width:1280,height:589},hasTouch:true,isMobile:true});
const page=await context.newPage();const report={};
try {
 await page.goto(STREAM_URL);
 await page.waitForFunction(()=>window.yorimichi?.state?.ready,{},{timeout:60000});await page.locator('#play').click();
 await page.waitForFunction(()=>document.querySelector('video')?.currentTime>0,{},{timeout:30000});
 await page.locator('#map-button').tap();
 await page.locator('.map-pin[data-key="mega"]').tap();await page.waitForTimeout(1500);
 report.arrival=await page.evaluate(()=>window.yorimichi.state);
 const cdp=await context.newCDPSession(page),box=await page.locator('#stick').boundingBox();
 const x=box.x+box.width/2,y=box.y+box.height/2;
 await cdp.send('Input.dispatchTouchEvent',{type:'touchStart',touchPoints:[{x,y,id:1}]});
 await cdp.send('Input.dispatchTouchEvent',{type:'touchMove',touchPoints:[{x,y:y-40,id:1}]});
 // Stop as soon as the actual ladder is in reach (centimetres in Unreal space).
 await page.waitForFunction(()=>{const s=window.yorimichi.state;return Math.hypot(s.x-6295,s.y+23645)<175;},{},{timeout:5000});
 await cdp.send('Input.dispatchTouchEvent',{type:'touchEnd',touchPoints:[]});
 await page.locator('#use').tap();
 await page.waitForFunction(()=>window.yorimichi.state.megaStage===0,{},{timeout:5000});
 await page.waitForFunction(()=>window.yorimichi.state.megaStage===1,{},{timeout:30000});
 await page.waitForTimeout(1500);
 report.deck=await page.evaluate(()=>window.yorimichi.state);
 await page.locator('#map-button').tap();
 await page.locator('#map-you').tap();await page.locator('#map-plus').tap();await page.locator('#map-plus').tap();
 await page.waitForTimeout(500);
 const marker=await page.locator('#map-player').boundingBox();
 await page.mouse.move(marker.x+marker.width/2,marker.y+marker.height/2);await page.mouse.wheel(0,-500);await page.waitForTimeout(300);
 const m=await page.locator('#map-player').boundingBox(),f=await page.locator('#map-frame').boundingBox();
 const delta=f.x+f.width/2-(m.x+m.width/2);
 await page.mouse.move(f.x+f.width/2,f.y+f.height*.75);await page.mouse.down();await page.mouse.move(f.x+f.width/2+delta,f.y+f.height*.75,{steps:10});await page.mouse.up();
 await page.waitForTimeout(400);
 await page.screenshot({path:new URL('phone-map.png',out).pathname});
 report.map=await page.evaluate(()=>({bounds:window.yorimichi.map.bounds,markerVisible:!document.querySelector('#map-player').hidden,imageWidth:document.querySelector('#map-image').naturalWidth,zoom:document.querySelector('#map-frame').dataset.zoom}));
 if(!report.map.markerVisible||report.map.imageWidth!==1536)throw Error('Map did not load updated painting and marker');
 await page.locator('#close-map').tap();report.passed=true;console.log(JSON.stringify(report,null,2));
} finally {
 await fs.writeFile(new URL('result.json',out),JSON.stringify(report,null,2));
 await page.locator('#spawn').tap().catch(()=>{});await page.waitForTimeout(500);await browser.close();
}
