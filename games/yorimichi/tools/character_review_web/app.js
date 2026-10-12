import { setupHairPreview as setupSpringHair } from './hair-motion.js';
import * as THREE from 'three';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';

const config=await fetch('config.json').then(r=>r.json());
document.querySelector('h1').textContent=config.label;
const stage=document.querySelector('#stage'),canvas=document.querySelector('#view'),loading=document.querySelector('#loading');
const renderer=new THREE.WebGLRenderer({canvas,antialias:true,powerPreference:'low-power'});
renderer.setPixelRatio(Math.min(devicePixelRatio,2));renderer.outputColorSpace=THREE.SRGBColorSpace;
renderer.toneMapping=THREE.NoToneMapping;
const scene=new THREE.Scene();scene.background=new THREE.Color('#e7e9ee');
const camera=new THREE.PerspectiveCamera(32,1,.01,50);
const orbit=new OrbitControls(camera,canvas);orbit.enableDamping=true;orbit.dampingFactor=.12;
orbit.minDistance=.32;orbit.maxDistance=8;orbit.screenSpacePanning=true;orbit.rotateSpeed=.75;orbit.zoomSpeed=.8;
scene.add(new THREE.HemisphereLight(0xffffff,0xa7adbb,2));
const key=new THREE.DirectionalLight(0xffffff,2.5);key.position.set(2,3,4);scene.add(key);
const fill=new THREE.DirectionalLight(0xc9d7ff,1);fill.position.set(-3,1,-2);scene.add(fill);
let model=null,materials=[],fitDistance=2,frames=0,queued=false,spin=false,modelReady=false;
function draw(){queued=false;if(document.hidden)return;orbit.update();if(window.characterMotion)window.characterMotion();renderer.render(scene,camera);if(spin||frames-->0)requestDraw();}
function requestDraw(count=0){frames=Math.max(frames,count);if(!queued&&!document.hidden){queued=true;requestAnimationFrame(draw);}}
orbit.addEventListener('change',()=>requestDraw());orbit.addEventListener('start',()=>{document.querySelectorAll('[data-view]').forEach(b=>b.classList.remove('active'));requestDraw(40);});
orbit.addEventListener('end',()=>requestDraw(40));
function resize(){const w=stage.clientWidth,h=stage.clientHeight;renderer.setSize(w,h,false);camera.aspect=w/h;camera.updateProjectionMatrix();requestDraw();}
new ResizeObserver(resize).observe(stage);
function setView(name='front'){
  if(!modelReady)return;
  if(name==='collar'&&!bodyMode)return setView('front');
  if(name==='collar'&&bodyMode){orbit.target.set(0,.39,0);camera.position.set(.34,.39,.5);camera.up.set(0,1,0);orbit.update();document.querySelectorAll('[data-view]').forEach(b=>b.classList.toggle('active',b.dataset.view===name));requestDraw(3);return;}
  const direction={front:[0,0,1],left:[-1,0,0],right:[1,0,0],back:[0,0,-1],under:[0,-1,.18]}[name];
  orbit.target.set(0,0,0);camera.position.fromArray(direction).normalize().multiplyScalar(fitDistance);camera.up.set(0,1,0);orbit.update();
  document.querySelectorAll('[data-view]').forEach(b=>b.classList.toggle('active',b.dataset.view===name));requestDraw(3);
}
document.querySelectorAll('[data-view]').forEach(b=>b.addEventListener('click',()=>setView(b.dataset.view)));
document.querySelector('#reset').onclick=()=>{spin=false;orbit.autoRotate=false;document.querySelector('#spin').setAttribute('aria-pressed','false');setView('front');};
document.querySelector('#spin').onclick=event=>{spin=!spin;orbit.autoRotate=spin;orbit.autoRotateSpeed=1.2;event.currentTarget.setAttribute('aria-pressed',String(spin));requestDraw(2);};
document.querySelector('#background').onclick=event=>{const dark=document.body.classList.toggle('dark');scene.background.set(dark?'#222630':'#e7e9ee');event.currentTarget.setAttribute('aria-pressed',String(dark));requestDraw();};
document.querySelector('#material').onchange=event=>{
  const mode=event.target.value;
  for(const entry of materials)entry.mesh.material=mode==='lit'?entry.lit:mode==='wire'?entry.wire:entry.texture;
  requestDraw();
};
document.querySelector('#fullscreen').onclick=async()=>{
  try{if(document.fullscreenElement)await document.exitFullscreen();else if(document.body.requestFullscreen)await document.body.requestFullscreen();else document.querySelector('#fullscreen').textContent='Use browser fullscreen';}catch{}
};
document.addEventListener('visibilitychange',()=>requestDraw(3));
const bodyMode=true;
const modelFile='model.glb';
if(!bodyMode)document.querySelector('[data-view=collar]').hidden=true;
document.querySelector('#body-tools').hidden=false;
document.querySelector('#download').href=modelFile;document.querySelector('#download').download=config.filename;
const loader=new GLTFLoader();
loader.load(modelFile+'?v='+encodeURIComponent(document.body.dataset.revision||config.sha256),gltf=>{
  model=gltf.scene;window.characterDebugModel=model;
  const box=new THREE.Box3().setFromObject(model),centre=box.getCenter(new THREE.Vector3()),size=box.getSize(new THREE.Vector3());
  model.position.sub(centre);scene.add(model);
  let triangles=0;
  model.traverse(mesh=>{
    if(!mesh.isMesh)return;
    triangles+=(mesh.geometry.index?.count??mesh.geometry.attributes.position.count)/3;
    const originals=Array.isArray(mesh.material)?mesh.material:[mesh.material];
    const textures=originals.map(m=>new THREE.MeshBasicMaterial({map:m.map,color:m.color.clone(),side:m.side,transparent:m.transparent,opacity:m.opacity,alphaTest:m.alphaTest}));
    const wire=originals.map(()=>new THREE.MeshBasicMaterial({color:0x627491,wireframe:true}));
    materials.push({mesh,lit:mesh.material,texture:Array.isArray(mesh.material)?textures:textures[0],wire:Array.isArray(mesh.material)?wire:wire[0]});
    mesh.material=materials.at(-1).texture;
  });
  fitDistance=Math.max(size.y,size.x/camera.aspect)*.5/Math.tan(THREE.MathUtils.degToRad(camera.fov*.5))*1.18;
  modelReady=true;window.characterViewer={loaded:true,triangles,bounds:size.toArray(),materials:materials.length,
    focusPoint:p=>{orbit.minDistance=.065;orbit.target.copy(p);camera.position.copy(p).add(new THREE.Vector3(.025,.17,.15));orbit.update();requestDraw(3);},state:()=>({camera:camera.position.toArray(),target:orbit.target.toArray(),mode:document.querySelector('#material').value,spin,
      textures:materials.map(e=>{const m=Array.isArray(e.mesh.material)?e.mesh.material[0]:e.mesh.material;return {type:m.type,map:!!m.map,dimensions:m.map?[m.map.image?.width,m.map.image?.height]:null,uv:!!e.mesh.geometry.attributes.uv};}),
      render:renderer.info.memory}),setView};
  const initial=new URLSearchParams(location.search).get('view');
  if(bodyMode)setupBodyTools(model);
  loading.hidden=true;setView(['front','left','right','back','under','collar'].includes(initial)?initial:'front');
},event=>{if(event.total)loading.textContent=`Loading model… ${Math.round(event.loaded/event.total*100)}%`;},error=>{
  console.error(error);loading.textContent='The model could not load. Please reload this page.';window.characterViewer={loaded:false,error:String(error)};
});
resize();

function setupBodyTools(root){
 const ray=new THREE.Raycaster(),pointer=new THREE.Vector2(),marks=[],markers=new THREE.Group();scene.add(markers);
 let marking=false,down=null;
 const status=document.querySelector('#mark-status');
 const update=()=>status.textContent=`${marks.length} mark${marks.length===1?'':'s'}. ${marking?'Tap a clipping spot; drag to rotate.':'Tap Mark clipping to add a spot.'}`;
 document.querySelector('#mark').onclick=e=>{marking=!marking;if(marking&&window.characterHair?.active())window.characterHair.pause();e.currentTarget.setAttribute('aria-pressed',String(marking));update();};
 canvas.addEventListener('pointerdown',e=>{down={x:e.clientX,y:e.clientY};});
 canvas.addEventListener('pointerup',e=>{
  if(!marking||!down||Math.hypot(e.clientX-down.x,e.clientY-down.y)>8)return;
  const rect=canvas.getBoundingClientRect();pointer.set((e.clientX-rect.left)/rect.width*2-1,-(e.clientY-rect.top)/rect.height*2+1);
  root.updateMatrixWorld(true);ray.setFromCamera(pointer,camera);const hits=ray.intersectObject(root,true);if(!hits.length)return;
  const h=hits[0],point=root.worldToLocal(h.point.clone());
  marks.push({mesh:h.object.name,faceIndex:h.faceIndex,modelPoint:point.toArray(),camera:camera.position.toArray(),target:orbit.target.toArray(),pose:{rootPosition:root.position.toArray(),rootQuaternion:root.quaternion.toArray(),bones:(()=>{const poses=[];root.traverse(o=>{if(o.isBone)poses.push([o.name,o.quaternion.toArray()]);});return poses;})()},time:new Date().toISOString()});
  const sphere=new THREE.Mesh(new THREE.SphereGeometry(.005,12,8),new THREE.MeshBasicMaterial({color:0xff364a,depthTest:false}));sphere.position.copy(h.point);sphere.renderOrder=1000;markers.add(sphere);update();requestDraw();
 });
 document.querySelector('#undo-mark').onclick=()=>{marks.pop();const last=markers.children.at(-1);if(last){markers.remove(last);last.geometry.dispose();last.material.dispose();}update();requestDraw();};
 document.querySelector('#save-marks').onclick=async()=>{
  const payload={schema:1,model:config.sha256,by:'operator',marks};
  try{const r=await fetch('feedback',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});if(!r.ok)throw new Error('save failed');status.textContent=`Saved ${marks.length} clipping marks. I can read these directly.`;}catch{const blob=new Blob([JSON.stringify(payload,null,2)],{type:'application/json'}),url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download='character-clipping-marks.json';a.click();URL.revokeObjectURL(url);status.textContent='Marks downloaded as JSON.';}
 };
 window.characterMarks={marks,count:()=>marks.length};
 if(config.hair)setupSpringHair(root,requestDraw,new URL('hair.json',location.href)).catch(error=>{console.error(error);document.querySelector('#motion').textContent='Reload for motion';});
}
