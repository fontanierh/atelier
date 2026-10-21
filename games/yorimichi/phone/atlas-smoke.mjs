// Browser contract for the regional atlas. Uses staged art/data and an isolated
// in-memory transport, so this test cannot rename or teleport a live player.
import {chromium,CHROME,buildDir} from '../../../platform/web/stream/smoke.mjs';
import fs from 'node:fs/promises';
const BUILD=buildDir('yorimichi'),here=new URL('./',import.meta.url);
const evidence=new URL('map/atlas-browser/',BUILD);await fs.mkdir(evidence,{recursive:true});
const source=JSON.parse(await fs.readFile(new URL('map/map.json',BUILD),'utf8'));
if(source.atlas?.regions.length!==7)throw Error('Build the complete regional atlas first');
const marker='marker_0123456789abcdef0123456789abcdef';
const peer='player_0123456789abcdef0123456789abcdef';
const home=source.atlas.landmarks.find(p=>p.key==='home_stables');
const data={...source,current_region:'haras_valley',loaded:true,image:'/map/map.jpg',zones:[...source.zones,
 {key:peer,name:'Online rider',x:home.x+30,y:home.y+30,region:'haras_valley',category:'player',hint:'Online player · teleport nearby'},
 {key:marker,name:'My saved ridge',x:home.x,y:home.y,region:'haras_valley',hint:'Saved place'}]};
const browser=await chromium.launch({executablePath:CHROME,headless:true});
try{
 for(const viewport of [{width:1920,height:1080},{width:844,height:390},{width:390,height:844}]){
  const context=await browser.newContext({viewport,hasTouch:true,isMobile:viewport.width<1000});
  const page=await context.newPage(),errors=[];
  page.on('pageerror',e=>errors.push(e.message));
  await page.route('http://atlas.test/**',async route=>{
   const path=new URL(route.request().url()).pathname;
   if(path==='/client.js')return route.fulfill({contentType:'text/javascript',body:`
import {createMap} from '/map.js';
let data=${JSON.stringify(data)};window.sent=[];
window.updateServerMap=()=>{data=structuredClone(data);data.atlas.landmarks.find(p=>p.key==='alder_stables').name='Changed at desktop';data.zones.push({...data.zones.at(-1),key:'marker_fresh',name:'Fresh saved stop'});};
window.map=createMap({send:m=>{window.sent.push(m);if(m.action==='map')map.receive(data);if(m.action==='renameStable'){data=structuredClone(data);data.atlas.landmarks.find(p=>p.key===m.key).name=m.name;map.receive(data);}}});
map.update({x:${home.x*100},y:${-home.y*100},yaw:90});map.open(true);
document.getElementById('close-map').onclick=()=>document.getElementById('map-dialog').close();`});
   if(path.startsWith('/map/atlas/'))return route.fulfill({contentType:'image/png',body:await fs.readFile(new URL(path.slice(1),BUILD))});
   const file={'/':'index.html','/map.js':'map.js','/style.css':'style.css'}[path];
   if(!file)return route.fulfill({status:404,body:''});
   return route.fulfill({contentType:path.endsWith('.js')?'text/javascript':path.endsWith('.css')?'text/css':'text/html',body:await fs.readFile(new URL(file,here))});
  });
  await page.goto('http://atlas.test/');
  const title=()=>page.locator('#map-title').textContent();
  const back=()=>page.locator('#map-back').click();
  const row=key=>page.locator(`#map-zones button[data-key="${key}"]`);
  await page.waitForFunction(()=>document.getElementById('map-title').textContent==='Stud Valley');
  if(await page.locator('.map-air-route line.air-leg').count()!==3)throw Error('Zeppelin itinerary is missing from the atlas');
  const airLegend=await page.locator('#map-air-legend').textContent();
  for(const name of ['Woodland','Hidamari','Mega Park','Belmonte'])if(!airLegend.includes(name))throw Error('Zeppelin legend misses '+name);
  if(await page.locator('#map-player').evaluate(p=>p.hidden))throw Error('Current regional player marker missing');
  for(const p of data.atlas.landmarks)if(!await row(p.key).count())throw Error('Stable missing: '+p.key);
  await row('alder_stables').click();
  await page.locator('#map-stable-name').fill('Cedar <Hill> & Grove');
  await page.locator('#map-stable-editor button').click();
  if(!(await row('alder_stables').textContent()).includes('Cedar <Hill> & Grove'))throw Error('Renamed label did not update');
  if(await row('alder_stables').locator('hill').count())throw Error('A custom name became HTML');
  const rename=await page.evaluate(()=>window.sent.at(-1));
  if(rename.action!=='renameStable'||rename.key!=='alder_stables')throw Error('Stable ID changed with its name');
  await back();
  if(!(await page.locator(`.map-pin[data-key="${peer}"]`).textContent()).startsWith('P'))throw Error('World overview hid the online player pin');
  const labels=await page.locator('.map-region').evaluateAll(nodes=>nodes.map(n=>({key:n.dataset.key,box:n.getBoundingClientRect().toJSON()})));
  for(let i=0;i<labels.length;i++)for(let j=i+1;j<labels.length;j++){
   const a=labels[i].box,b=labels[j].box;
   if(Math.min(a.right,b.right)-Math.max(a.left,b.left)>1&&Math.min(a.bottom,b.bottom)-Math.max(a.top,b.top)>1)throw Error('World captions overlap: '+labels[i].key+' / '+labels[j].key);
  }
  await page.screenshot({path:new URL(`world-${viewport.width}.png`,evidence).pathname});
  const keys=await page.locator('#map-zones button').evaluateAll(rows=>rows.map(r=>r.dataset.key));
  for(const z of data.zones)if(!keys.includes(z.key))throw Error('World overview dropped destination: '+z.key);
  for(const r of data.atlas.regions){
   await row(r.key).click();
   if(await title()!==r.name)throw Error('Region selection failed: '+r.key);
   await page.waitForFunction(()=>{const i=document.getElementById('map-image');return i.complete&&i.naturalWidth>0;});
   const shape=await page.locator('#map-canvas').boundingBox(),b=r.bounds;
   if(Math.abs(shape.width/shape.height-(b[2]-b[0])/(b[3]-b[1]))>.01)throw Error('Regional map is distorted: '+r.key);
   await back();
  }
  await row('haras_valley').click();
  await page.locator('#map-search').fill('Crater Park');
  if(!await row('craterpark').count())throw Error('Search cannot leave the current region');
  await row('craterpark').click();
  if(await page.locator('#map-dialog').evaluate(d=>d.open))throw Error('Travel failed to close atlas');
  if(await page.evaluate(()=>window.sent.at(-1).zone)!=='craterpark')throw Error('Search changed travel identity');
  await page.evaluate(()=>{window.updateServerMap();window.map.open(true);});
  if(!(await row('alder_stables').textContent()).includes('Changed at desktop')||!await row('marker_fresh').count())throw Error('Reopening kept stale names or saved places');
  if(await title()!=='Stud Valley'||await page.locator('#map-search').inputValue()!=='')throw Error('Reopening did not reset to current region');
  await page.locator('#map-search').fill('My saved ridge');
  await row(marker).click();
  if(await page.evaluate(()=>window.sent.at(-1).zone)!==marker)throw Error('39-character marker key was truncated');
  if(errors.length)throw Error(errors.join('\n'));
  console.log(`PASS ${viewport.width}x${viewport.height}: current region, seven regions, all destinations, global search, live names and saved marker identity`);
  await context.close();
 }
}finally{await browser.close();}
