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
scene.background=new THREE.Color('#82b9c2');
scene.fog=new THREE.FogExp2('#8eb4a7',0.00072);
const camera=new THREE.PerspectiveCamera(42,1,1,3200);
const controls=new OrbitControls(camera,canvas);
controls.enableDamping=true;controls.dampingFactor=.065;controls.screenSpacePanning=true;
controls.minDistance=18;controls.maxDistance=1550;controls.maxPolarAngle=Math.PI*.492;

scene.add(new THREE.HemisphereLight('#e4f7f2','#31583a',2.05));
const sun=new THREE.DirectionalLight('#fff0c2',3.65);sun.position.set(-360,520,280);scene.add(sun);
const rim=new THREE.DirectionalLight('#8bd1d2',.95);rim.position.set(420,180,-360);scene.add(rim);

const locations={
  aerial:{target:[0,25,-12],position:[455,505,-445],description:'Whole city'},
  east:{target:[80,15,0],position:[360,85,-40],description:'East causeway'},
  temple:{target:[0,35,-7],position:[195,175,-175],description:'Temple mountain'},
  market:{target:[180,15,20],position:[325,105,195],description:'Market city'},
  baray:{target:[-218,10,20],position:[-345,125,155],description:'West baray'},
  gate:{target:[0,18,104],position:[20,105,235],description:'South gate'},
  bridge:{target:[0,7,119],position:[135,75,210],description:'Naga bridge'},
  jungle:{target:[-275,15,-35],position:[-425,150,-170],description:'Jungle edge'},
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
document.querySelector('#info-toggle').onclick=event=>{const panel=document.querySelector('#info-panel');panel.classList.toggle('collapsed');event.currentTarget.setAttribute('aria-expanded',String(!panel.classList.contains('collapsed')));};
controls.addEventListener('start',()=>{touring=false;document.querySelector('#tour').textContent='Start tour';cameraTween=null;});

const loader=new GLTFLoader();
loader.load('./models/JungleCity.glb',gltf=>{
  const model=gltf.scene;
  const tintMaterial=material=>{
    const name=(material.name||'').toLowerCase();
    if(name.includes('water')){material.color.setRGB(.03,.31,.38);material.roughness=.27;material.metalness=.02;}
    else if(name.includes('leaf')||name.includes('grass')) material.color.setRGB(1.35,1.75,1.25);
    else if(name.includes('flower')) material.color.setRGB(1.8,1.25,.9);
    else if(name.includes('roof')) material.color.setRGB(1.25,1.55,1.48);
    else if(name.includes('laterite')) material.color.setRGB(1.42,1.02,.82);
    else if(name.includes('sandstone')||name.includes('earth')) material.color.setRGB(1.16,1.05,.86);
    else if(name.includes('timber')) material.color.setRGB(1.5,1.18,.9);
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
