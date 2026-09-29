// Exercise real touch gestures on the map UI without connecting to or moving the live game.
import {chromium} from '@playwright/test';
import fs from 'node:fs/promises';
const here=new URL('./',import.meta.url);
const mapData=JSON.parse(await fs.readFile(new URL('../out/map/map.json',here),'utf8'));
const data={...mapData,loaded:true,image:'/map/map.jpg'};
const browser=await chromium.launch({executablePath:'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',headless:true});
try{
 for(const viewport of [{width:844,height:390},{width:390,height:844}]){
  const context=await browser.newContext({viewport,hasTouch:true,isMobile:true});
  const page=await context.newPage();
  await page.route('http://map.test/**',async route=>{
   const path=new URL(route.request().url()).pathname;
   if(path==='/client.js')return route.fulfill({contentType:'text/javascript',body:`import {createMap} from '/map.js';window.travels=[];const map=createMap({send:m=>{if(m.action==='map')map.receive(${JSON.stringify(data)});else window.travels.push(m);}});map.open(true);`});
   const files={'/':'index.html','/style.css':'style.css','/map.js':'map.js','/map/map.jpg':'../out/map/map.jpg'};
   if(!files[path])return route.fulfill({status:404,body:''});
   const contentType=path.endsWith('.css')?'text/css':path.endsWith('.js')?'text/javascript':path.endsWith('.jpg')?'image/jpeg':'text/html';
   const body=path==='/style.css'&&process.env.MAP_TEST_CSS?await fs.readFile(process.env.MAP_TEST_CSS):await fs.readFile(new URL(files[path],here));
   await route.fulfill({contentType,body});
  });
  await page.goto('http://map.test/');
  await page.waitForSelector('#map-zones button');
  const cdp=await context.newCDPSession(page);
  async function swipe(up){
   const b=await page.locator('#map-zones').boundingBox();
   const x=b.x+b.width*.6,target=b.y+b.height*(up?.8:.2),to=b.y+b.height*(up?.2:.8);
   const from=await page.locator('#map-zones button').evaluateAll((buttons,{target,top,bottom})=>buttons.map(el=>el.getBoundingClientRect()).map(r=>(Math.max(r.top,top)+Math.min(r.bottom,bottom))/2).filter(y=>y>top+5&&y<bottom-5).sort((a,b)=>Math.abs(a-target)-Math.abs(b-target))[0],{target,top:b.y,bottom:b.y+b.height});
   const overButton=await page.evaluate(({x,y})=>!!document.elementFromPoint(x,y)?.closest('#map-zones button'),{x,y:from});
   if(!overButton)throw Error('Swipe must begin over a destination button');
   await cdp.send('Input.dispatchTouchEvent',{type:'touchStart',touchPoints:[{x,y:from,id:1}]});
   for(let i=1;i<=16;i++){await cdp.send('Input.dispatchTouchEvent',{type:'touchMove',touchPoints:[{x,y:from+(to-from)*i/16,id:1}]});await page.waitForTimeout(18);}
   await cdp.send('Input.dispatchTouchEvent',{type:'touchEnd',touchPoints:[]});await page.waitForTimeout(450);
  }
  await swipe(true);
  const first=await page.locator('#map-zones').evaluate(el=>el.scrollTop);
  if(first<30)throw Error(`Touch scroll blocked at ${viewport.width}x${viewport.height}: ${first}`);
  await swipe(false);
  if(await page.locator('#map-zones').evaluate(el=>el.scrollTop)>=first)throw Error('Reverse swipe did not scroll back');
  for(let i=0;i<12;i++){
   const bottom=await page.locator('#map-zones').evaluate(el=>el.scrollTop+el.clientHeight>=el.scrollHeight-2);
   if(bottom)break;await swipe(true);
  }
  if(await page.evaluate(()=>window.travels.length))throw Error('A swipe accidentally triggered travel');
  await page.locator('#map-zones button').last().tap();
  if(await page.evaluate(()=>window.travels.at(-1)?.zone)!==data.zones.at(-1).key)throw Error('Final destination not reachable');
  console.log(`PASS ${viewport.width}x${viewport.height}: swipe both ways, reach last destination, tap to travel`);
  // Reopen and exercise the separate map view gestures.
  await page.evaluate(()=>document.getElementById('map-dialog').showModal());
  await page.locator('#map-whole').tap();
  const sheet=page.locator('#map-canvas');
  const shape=await sheet.boundingBox();
  if(Math.abs(shape.width/shape.height-1.5)>.01)throw Error('Map aspect distorted');
  await page.locator('#map-plus').tap();
  if(Number(await page.locator('#map-frame').getAttribute('data-zoom'))<=1)throw Error('Zoom button failed');
  const pinError=await page.locator('.map-pin').first().evaluate(el=>{const r=el.getBoundingClientRect(),c=document.getElementById('map-canvas').getBoundingClientRect();return Math.hypot(r.x+r.width/2-c.x-parseFloat(el.style.left)/100*c.width,r.y+r.height/2-c.y-parseFloat(el.style.top)/100*c.height);});
  if(pinError>1)throw Error('Zoom shifted marker off its map coordinate: '+pinError);
  const f=await page.locator('#map-frame').boundingBox(),cx=f.x+f.width/2,cy=f.y+f.height/2;
  const before=Number(await page.locator('#map-frame').getAttribute('data-zoom'));
  await cdp.send('Input.dispatchTouchEvent',{type:'touchStart',touchPoints:[{x:cx-20,y:cy,id:1},{x:cx+20,y:cy,id:2}]});
  for(let i=1;i<=8;i++)await cdp.send('Input.dispatchTouchEvent',{type:'touchMove',touchPoints:[{x:cx-20-i*3,y:cy,id:1},{x:cx+20+i*3,y:cy,id:2}]});
  await cdp.send('Input.dispatchTouchEvent',{type:'touchEnd',touchPoints:[]});
  if(Number(await page.locator('#map-frame').getAttribute('data-zoom'))<=before)throw Error('Pinch failed');
  const oldTransform=await sheet.evaluate(el=>el.style.transform);
  await page.mouse.move(cx,cy);await page.mouse.down();await page.mouse.move(cx-35,cy+30,{steps:8});await page.mouse.up();
  if(await sheet.evaluate(el=>el.style.transform)===oldTransform)throw Error('Map drag failed');
  if(await page.evaluate(()=>window.travels.length)!==1)throw Error('Map gesture accidentally travelled');
  await page.locator('#map-whole').tap();
  if(await page.locator('#map-frame').getAttribute('data-zoom')!=='1.000')throw Error('Whole map reset failed');
  await page.screenshot({path:new URL(`../out/map/phone-${viewport.width}.png`,here).pathname});
  console.log(`PASS ${viewport.width}x${viewport.height}: aspect, zoom, pinch, pan, whole map, no accidental travel`);
  await context.close();
 }
}finally{await browser.close();}
