// The artwork, pins and player share one cartographic projection and one view transform.
const $=id=>document.getElementById(id);
function project(v,knots){
 if(!knots?.length)return v;
 if(v<=knots[0][0])return knots[0][1];
 for(let i=1;i<knots.length;i++)if(v<=knots[i][0]){const a=knots[i-1],b=knots[i];return a[1]+(b[1]-a[1])*(v-a[0])/(b[0]-a[0]);}
 return knots.at(-1)[1];
}
export function createMap({send,onTravel}){
 let data=null,state=null,imageSource='',scale=1,offset={x:0,y:0},base={w:1,h:1},initialized=false,gesture=null,suppressClick=false;
 const touches=new Map();
 const dialog=$('map-dialog'),layout=$('map-layout'),frame=$('map-frame'),canvas=$('map-canvas'),img=$('map-image'),pins=$('map-pins'),list=$('map-zones'),player=$('map-player'),status=$('map-status');
 function pct(x,y){const [x0,y0,x1,y1]=data.bounds;return [(project(x,data.projection_x)-x0)/(x1-x0)*100,(y1-project(y,data.projection_y))/(y1-y0)*100];}
 function apply(){
  const w=frame.clientWidth,h=frame.clientHeight,sw=base.w*scale,sh=base.h*scale;
  offset.x=sw<w?(w-sw)/2:Math.max(w-sw,Math.min(0,offset.x));
  offset.y=sh<h?(h-sh)/2:Math.max(h-sh,Math.min(0,offset.y));
  canvas.style.width=base.w+'px';canvas.style.height=base.h+'px';
  canvas.style.transform=`translate(${offset.x}px,${offset.y}px) scale(${scale})`;
  canvas.style.setProperty('--pin-scale',1/scale);
  frame.dataset.zoom=scale.toFixed(3);
 }
 function whole(){scale=1;offset={x:0,y:0};apply();}
 function focus(){
  if(!data)return;
  const z=data.zones.find(z=>z.key==='spawn')||data.zones[0];
  const [u,v]=state&&typeof state.x==='number'?pct(state.x/100,-state.y/100):pct(z.x,z.y);
  scale=1.7;offset={x:frame.clientWidth/2-u/100*base.w*scale,y:frame.clientHeight/2-v/100*base.h*scale};apply();
 }
 function fit(){
  const box=layout.getBoundingClientRect(),portrait=matchMedia('(orientation: portrait)').matches;
  const w=portrait?box.width:Math.max(100,box.width-(list.getBoundingClientRect().width||200)-12);
  const h=portrait?Math.max(120,box.height*.57):box.height;
  frame.style.width=Math.floor(w)+'px';frame.style.height=Math.floor(h)+'px';
  const b=data?.bounds,aspect=img.naturalWidth?img.naturalWidth/img.naturalHeight:b?(b[2]-b[0])/(b[3]-b[1]):1.5;
  base={w:Math.min(w,h*aspect),h:Math.min(h,w/aspect)};apply();
 }
 function zoom(factor,point={x:frame.clientWidth/2,y:frame.clientHeight/2}){
  const next=Math.max(1,Math.min(6,scale*factor)),ratio=next/scale;
  offset={x:point.x-(point.x-offset.x)*ratio,y:point.y-(point.y-offset.y)*ratio};scale=next;apply();
 }
 function render(){
  if(!data)return;
  if(imageSource!==data.image){imageSource=data.image;img.src=data.image;}
  pins.replaceChildren();list.replaceChildren();
  data.zones.forEach((z,i)=>{
   const [l,t]=pct(z.x,z.y),pin=document.createElement('button');
   pin.className='map-pin';pin.dataset.key=z.key;pin.style.left=l+'%';pin.style.top=t+'%';pin.textContent=i+1;pin.setAttribute('aria-label',`Travel to ${z.name}`);pin.onclick=()=>{if(!suppressClick)travel(z);};pins.append(pin);
   const li=document.createElement('li'),b=document.createElement('button');b.dataset.key=z.key;
   const n=document.createElement('b');n.textContent=i+1;const name=document.createElement('span');name.textContent=z.name;
   const hint=document.createElement('small');hint.textContent=z.hint||'';name.append(hint);b.append(n,name);b.onclick=()=>travel(z);li.append(b);list.append(li);
  });
  status.textContent='Drag or pinch to explore. Tap a place to travel.';fit();
  if(!initialized){focus();initialized=true;}update(state);
 }
 function update(s){
  state=s;if(!data||!s||typeof s.x!=='number'){player.hidden=true;return;}
  const [l,t]=pct(s.x/100,-s.y/100);player.hidden=false;player.style.left=l+'%';player.style.top=t+'%';player.style.setProperty('--heading',`${s.yaw||0}deg`);
 }
 function travel(z){status.textContent=`Travelling to ${z.name}…`;send({action:'teleport',zone:z.key});dialog.close();onTravel?.(z);}
 function local(e){const b=frame.getBoundingClientRect();return {x:e.clientX-b.x,y:e.clientY-b.y};}
 function startGesture(){
  const p=[...touches.values()];
  gesture=p.length>=2?{pinch:true,distance:Math.hypot(p[1].x-p[0].x,p[1].y-p[0].y),center:{x:(p[0].x+p[1].x)/2,y:(p[0].y+p[1].y)/2}}:{point:p[0],start:p[0],moved:false};
 }
 frame.addEventListener('pointerdown',e=>{touches.set(e.pointerId,local(e));startGesture();if(touches.size>1){suppressClick=true;frame.setPointerCapture(e.pointerId);}});
 frame.addEventListener('pointermove',e=>{
  if(!touches.has(e.pointerId)||!gesture)return;
  touches.set(e.pointerId,local(e));const p=[...touches.values()];
  if(p.length>=2){
   const center={x:(p[0].x+p[1].x)/2,y:(p[0].y+p[1].y)/2},distance=Math.hypot(p[1].x-p[0].x,p[1].y-p[0].y);
   if(!gesture.pinch){startGesture();return;}
   zoom(distance/Math.max(1,gesture.distance),gesture.center);offset.x+=center.x-gesture.center.x;offset.y+=center.y-gesture.center.y;apply();gesture={pinch:true,distance,center};
  }else{
   const q=p[0];if(gesture.pinch){startGesture();return;}
   if(Math.hypot(q.x-gesture.start.x,q.y-gesture.start.y)>5){gesture.moved=true;suppressClick=true;frame.setPointerCapture(e.pointerId);}
   if(gesture.moved){offset.x+=q.x-gesture.point.x;offset.y+=q.y-gesture.point.y;apply();}
   gesture.point=q;
  }
 });
 function end(e){touches.delete(e.pointerId);if(touches.size)startGesture();else{gesture=null;setTimeout(()=>suppressClick=false,100);}}
 frame.addEventListener('pointerup',end);frame.addEventListener('pointercancel',end);
 frame.addEventListener('click',e=>{if(suppressClick){e.preventDefault();e.stopPropagation();}},true);
 frame.addEventListener('wheel',e=>{e.preventDefault();zoom(Math.exp(-e.deltaY*.002),local(e));},{passive:false});
 $('map-plus').onclick=()=>zoom(1.4);$('map-minus').onclick=()=>zoom(1/1.4);$('map-you').onclick=focus;$('map-whole').onclick=whole;
 img.onload=()=>{fit();if(initialized)focus();};
 addEventListener('resize',()=>{if(dialog.open){fit();focus();}});
 return {open(connected){dialog.showModal();fit();if(!connected){status.textContent='Connect to the game to load the map';return;}if(data){render();focus();}else{status.textContent='Loading the map…';send({action:'map'});}},receive(msg){data=msg;if(dialog.open)render();},update,get data(){return data;}};
}
