import * as THREE from 'three';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';

const canvas=document.querySelector('#view');
const stage=document.querySelector('#stage');
const loading=document.querySelector('#loading');
const renderer=new THREE.WebGLRenderer({canvas,antialias:true,powerPreference:'default'});
renderer.setPixelRatio(Math.min(devicePixelRatio,1.25));
renderer.outputColorSpace=THREE.SRGBColorSpace;
renderer.toneMapping=THREE.NoToneMapping;
renderer.toneMappingExposure=1.0;
renderer.shadowMap.enabled=false;

const scene=new THREE.Scene();
scene.background=new THREE.Color('#74a2aa');
scene.fog=new THREE.FogExp2('#789b91',0.00125);
const camera=new THREE.PerspectiveCamera(43,1,1,2400);
const controls=new OrbitControls(camera,canvas);
controls.enableDamping=true;controls.dampingFactor=.065;controls.screenSpacePanning=true;
controls.minDistance=28;controls.maxDistance=980;controls.maxPolarAngle=Math.PI*.485;

scene.add(new THREE.HemisphereLight('#d9edf0','#263b26',1.25));
const sun=new THREE.DirectionalLight('#fff1cb',2.45);sun.position.set(-280,420,210);scene.add(sun);
const rim=new THREE.DirectionalLight('#8bc9c4',.55);rim.position.set(360,180,-310);scene.add(rim);

const locations={
  aerial:{target:[0,16,0],position:[415,360,470],description:'City whole'},
  east:{target:[130,18,18],position:[365,82,112],description:'East causeway'},
  temple:{target:[0,32,12],position:[168,118,188],description:'Temple mountain'},
  market:{target:[118,18,-82],position:[242,86,-208],description:'Market terraces'},
  baray:{target:[-248,15,-22],position:[-390,122,-190],description:'West baray'},
  jungle:{target:[-210,24,160],position:[-348,96,278],description:'Jungle edge'},
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
  model.traverse(object=>{if(object.isMesh){object.castShadow=false;object.receiveShadow=false;}});
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
