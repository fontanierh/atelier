import * as THREE from 'three';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';

const canvas=document.querySelector('#view');
const stage=document.querySelector('#stage');
const loading=document.querySelector('#loading');
const renderer=new THREE.WebGLRenderer({canvas,antialias:true,powerPreference:'default'});
renderer.setPixelRatio(Math.min(devicePixelRatio,1.25));
renderer.outputColorSpace=THREE.SRGBColorSpace;
renderer.toneMapping=THREE.ACESFilmicToneMapping;
renderer.toneMappingExposure=1.08;
renderer.shadowMap.enabled=false;

const scene=new THREE.Scene();
scene.background=new THREE.Color('#789b9d');
scene.fog=new THREE.FogExp2('#8ea78e',0.00046);
const camera=new THREE.PerspectiveCamera(42,1,1,3200);
const controls=new OrbitControls(camera,canvas);
controls.enableDamping=true;controls.dampingFactor=.065;controls.screenSpacePanning=true;
controls.minDistance=18;controls.maxDistance=1550;controls.maxPolarAngle=Math.PI*.492;

scene.add(new THREE.HemisphereLight('#e6f2df','#233b2b',1.72));
const sun=new THREE.DirectionalLight('#ffe2a6',3.35);sun.position.set(-360,520,280);scene.add(sun);
const rim=new THREE.DirectionalLight('#77b9bb',.52);rim.position.set(420,180,-360);scene.add(rim);

const locations={
  aerial:{target:[0,22,-10],position:[425,315,-435],description:'Whole city'},
  east:{target:[80,15,0],position:[315,66,-48],description:'East causeway'},
  temple:{target:[0,34,-7],position:[158,106,-148],description:'Temple mountain'},
  market:{target:[184,15,25],position:[305,72,168],description:'Market city'},
  baray:{target:[-218,10,20],position:[-325,82,138],description:'West baray'},
  gate:{target:[0,18,190],position:[26,62,248],description:'South gate'},
  bridge:{target:[0,7,119],position:[112,50,174],description:'Naga bridge'},
  jungle:{target:[-275,15,-35],position:[-385,92,-145],description:'Jungle edge'},
};
let cameraTween=null,tourTimer=0,touring=false;

function resize(){const w=stage.clientWidth,h=stage.clientHeight;renderer.setSize(w,h,false);camera.aspect=w/h;camera.updateProjectionMatrix();}
new ResizeObserver(resize).observe(stage);

function setView(name,immediate=false){
  const view=locations[name];if(!view)return;
  document.querySelectorAll('[data-view]').forEach(b=>b.classList.toggle('active',b.dataset.view===name));
  const endPosition=new THREE.Vector3(...view.position),endTarget=new THREE.Vector3(...view.target);
  if(immediate){camera.position.copy(endPosition);controls.target.copy(endTarget);controls.update();return;}
  cameraTween={start:performance.now(),duration:1250,fromPosition:camera.position.clone(),fromTarget:controls.target.clone(),endPosition,endTarget};
}

function updateCameraTween(now){
  if(!cameraTween)return false;
  const t=Math.min(1,(now-cameraTween.start)/cameraTween.duration),e=t<.5?4*t*t*t:1-Math.pow(-2*t+2,3)/2;
  camera.position.lerpVectors(cameraTween.fromPosition,cameraTween.endPosition,e);controls.target.lerpVectors(cameraTween.fromTarget,cameraTween.endTarget,e);
  if(t===1)cameraTween=null;return true;
}

function animate(now=0){
  requestAnimationFrame(animate);
  const tweening=updateCameraTween(now);controls.update();
  if(touring&&!tweening){tourTimer+=1;if(tourTimer>540){tourTimer=0;const keys=Object.keys(locations);const current=keys.findIndex(k=>document.querySelector(`[data-view="${k}"]`)?.classList.contains('active'));setView(keys[(current+1)%keys.length]);}}
  renderer.render(scene,camera);
}

document.querySelectorAll('[data-view]').forEach(button=>button.addEventListener('click',()=>{touring=false;document.querySelector('#tour').textContent='Start tour';setView(button.dataset.view);}));
document.querySelector('#tour').onclick=event=>{touring=!touring;tourTimer=0;event.currentTarget.textContent=touring?'Pause tour':'Start tour';};
document.querySelector('#fullscreen').onclick=async()=>{if(document.fullscreenElement)await document.exitFullscreen();else await document.documentElement.requestFullscreen();};
const infoPanel=document.querySelector('#info-panel'),infoToggle=document.querySelector('#info-toggle');
if(matchMedia('(max-width:720px)').matches){infoPanel.classList.add('collapsed');infoToggle.setAttribute('aria-expanded','false');}
infoToggle.onclick=event=>{infoPanel.classList.toggle('collapsed');event.currentTarget.setAttribute('aria-expanded',String(!infoPanel.classList.contains('collapsed')));};
controls.addEventListener('start',()=>{touring=false;document.querySelector('#tour').textContent='Start tour';cameraTween=null;});

const loader=new GLTFLoader();
loader.load('./models/JungleCity.glb',gltf=>{
  const model=gltf.scene;
  const tintMaterial=material=>{
    const name=(material.name||'').toLowerCase();
    if(material.map){material.color.setRGB(1,1,1);material.envMapIntensity=1.05;return;}
    if(name.includes('water')){material.color.setRGB(.025,.22,.25);material.roughness=.3;material.metalness=.015;}
    else if(name.includes('leaf')||name.includes('grass')) material.color.setRGB(1.02,1.28,.9);
    else if(name.includes('flower')) material.color.setRGB(1.4,.86,.58);
    else if(name.includes('roof')) material.color.setRGB(.88,1.12,1.06);
    else if(name.includes('laterite')) material.color.setRGB(1.18,.82,.62);
    else if(name.includes('sandstone')||name.includes('earth')) material.color.setRGB(1.02,.89,.72);
    else if(name.includes('timber')) material.color.setRGB(1.18,.9,.66);
  };
  model.traverse(object=>{if(object.isMesh){object.castShadow=false;object.receiveShadow=false;if(Array.isArray(object.material))object.material.forEach(tintMaterial);else if(object.material)tintMaterial(object.material);}});
  scene.add(model);
  window.jungleCityViewer={loaded:true,model,locations,setView,renderer,scene,camera,sampleCanvas(){
    renderer.render(scene,camera);
    const gl=renderer.getContext(),width=gl.drawingBufferWidth,height=gl.drawingBufferHeight;
    const pixels=new Uint8Array(width*height*4);gl.readPixels(0,0,width,height,gl.RGBA,gl.UNSIGNED_BYTE,pixels);
    let visible=0;const colors=new Set();
    for(let i=0;i<pixels.length;i+=160){const key=(pixels[i]<<16)|(pixels[i+1]<<8)|pixels[i+2];colors.add(key);if(pixels[i+3])visible++;}
    return {width,height,visibleSamples:visible,uniqueSampleColors:colors.size,contextLost:gl.isContextLost(),drawCalls:renderer.info.render.calls,triangles:renderer.info.render.triangles};
  }};
  loading.hidden=true;setView(new URLSearchParams(location.search).get('view')||'aerial',true);
},event=>{if(event.total)loading.textContent=`Building the city view… ${Math.round(event.loaded/event.total*100)}%`;},error=>{
  console.error(error);loading.textContent='The proposal model could not load. Reload to try again.';window.jungleCityViewer={loaded:false,error:String(error)};
});
resize();setView('aerial',true);animate();
