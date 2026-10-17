import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
const canvas=document.querySelector('#view'),stage=document.querySelector('#stage'),loading=document.querySelector('#loading');
const renderer=new THREE.WebGLRenderer({canvas,antialias:true,alpha:true,powerPreference:'low-power'});
renderer.setPixelRatio(Math.min(devicePixelRatio,1.5));renderer.setClearColor(0x000000,0);renderer.outputColorSpace=THREE.SRGBColorSpace;renderer.toneMapping=THREE.ACESFilmicToneMapping;renderer.toneMappingExposure=1.2;
const scene=new THREE.Scene(),camera=new THREE.PerspectiveCamera(34,1,.01,30);
const controls=new OrbitControls(camera,canvas);controls.enableDamping=true;controls.dampingFactor=.12;controls.minDistance=.5;controls.maxDistance=6;
scene.add(new THREE.HemisphereLight(0xe8efff,0x333139,2.2));
for(const [color,intensity,position] of [[0xffedcf,3,[3,4,5]],[0xaac5f7,1.5,[-4,2,-1]]]){const l=new THREE.DirectionalLight(color,intensity);l.position.fromArray(position);scene.add(l);}
let queued=false,frames=0,spin=false,mesh=null,wire=false,colored=true;
function requestDraw(n=0){frames=Math.max(frames,n);if(!queued&&!document.hidden){queued=true;requestAnimationFrame(draw);}}
function draw(){queued=false;if(document.hidden)return;controls.update();renderer.render(scene,camera);if(spin||frames-->0)requestDraw();}
controls.addEventListener('change',()=>requestDraw());controls.addEventListener('start',()=>requestDraw(45));controls.addEventListener('end',()=>requestDraw(45));
function resize(){const w=stage.clientWidth,h=stage.clientHeight;renderer.setSize(w,h,false);camera.aspect=w/h;camera.updateProjectionMatrix();requestDraw();}
new ResizeObserver(resize).observe(stage);document.addEventListener('visibilitychange',()=>requestDraw(3));
function reset(){controls.target.set(0,.48,0);camera.position.set(1.5,1.25,2.2);controls.update();requestDraw(3);}
function updateMaterial(){if(!mesh)return;for(const m of mesh.material){m.wireframe=wire;m.color.set(colored?m.userData.color:0xa6adb5);m.needsUpdate=true;}requestDraw();}
document.querySelector('#reset').onclick=reset;
document.querySelector('#wire').onclick=e=>{wire=!wire;e.currentTarget.setAttribute('aria-pressed',String(wire));updateMaterial();};
document.querySelector('#color').onclick=e=>{colored=!colored;e.currentTarget.setAttribute('aria-pressed',String(colored));updateMaterial();};
document.querySelector('#spin').onclick=e=>{spin=!spin;controls.autoRotate=spin;controls.autoRotateSpeed=1.2;e.currentTarget.setAttribute('aria-pressed',String(spin));requestDraw(2);};
try{
 const response=await fetch('mesh.json');if(!response.ok)throw new Error(`Mesh HTTP ${response.status}`);const data=await response.json();
 const lo=[0,1,2].map(i=>Math.min(...data.vertices.map(v=>v[i]))),hi=[0,1,2].map(i=>Math.max(...data.vertices.map(v=>v[i]))),scale=1/(hi[2]-lo[2]);
 const geometry=new THREE.BufferGeometry(),buckets=[[],[]];
 const palette=[new THREE.MeshStandardMaterial({color:0x354f6f,roughness:.86,side:THREE.DoubleSide}),new THREE.MeshStandardMaterial({color:0xc4953f,roughness:.86,side:THREE.DoubleSide})];for(const m of palette)m.userData.color=m.color.getHex();
 for(const face of data.faces){const z=face.reduce((sum,index)=>sum+(data.vertices[index][2]-lo[2])*scale/3,0);const positions=buckets[z>.78?1:0];for(const index of face){const v=data.vertices[index];positions.push((v[0]-(lo[0]+hi[0])/2)*scale,(v[2]-lo[2])*scale,-(v[1]-(lo[1]+hi[1])/2)*scale);}}
 const positions=buckets.flat();let offset=0;for(let i=0;i<buckets.length;i++){geometry.addGroup(offset,buckets[i].length/3,i);offset+=buckets[i].length/3;}
 geometry.setAttribute('position',new THREE.Float32BufferAttribute(positions,3));geometry.computeVertexNormals();mesh=new THREE.Mesh(geometry,palette);scene.add(mesh);
 const grid=new THREE.GridHelper(4,20,0x40516b,0x2d3c50);grid.position.y=-.015;grid.material.transparent=true;grid.material.opacity=.45;scene.add(grid);
 window.meshaxiomViewer={loaded:true,triangles:data.faces.length,sourceVertices:data.vertices.length,reset};loading.hidden=true;reset();
}catch(error){console.error(error);loading.textContent='The mesh could not load. Please reload.';window.meshaxiomViewer={loaded:false,error:String(error)};}
resize();
