import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
const canvas=document.querySelector('#view'),stage=document.querySelector('#stage'),loading=document.querySelector('#loading');
const renderer=new THREE.WebGLRenderer({canvas,antialias:true,alpha:true,powerPreference:'low-power'});
renderer.setPixelRatio(Math.min(devicePixelRatio,1.5));renderer.setClearColor(0x000000,0);renderer.outputColorSpace=THREE.SRGBColorSpace;renderer.toneMapping=THREE.ACESFilmicToneMapping;renderer.toneMappingExposure=1.2;
const scene=new THREE.Scene(),camera=new THREE.PerspectiveCamera(34,1,.01,30);
const controls=new OrbitControls(camera,canvas);controls.enableDamping=true;controls.dampingFactor=.12;controls.minDistance=.5;controls.maxDistance=6;
scene.add(new THREE.HemisphereLight(0xe8efff,0x333139,2.2));
for(const [color,intensity,position] of [[0xffedcf,3,[3,4,5]],[0xaac5f7,1.5,[-4,2,-1]]]){const l=new THREE.DirectionalLight(color,intensity);l.position.fromArray(position);scene.add(l);}
let queued=false,frames=0,spin=false,mesh=null,wire=false,colored=true,boundaries=null,materials=[];
function requestDraw(n=0){frames=Math.max(frames,n);if(!queued&&!document.hidden){queued=true;requestAnimationFrame(draw);}}
function draw(){queued=false;if(document.hidden)return;controls.update();renderer.render(scene,camera);if(spin||frames-->0)requestDraw();}
controls.addEventListener('change',()=>requestDraw());controls.addEventListener('start',()=>requestDraw(45));controls.addEventListener('end',()=>requestDraw(45));
function resize(){const w=stage.clientWidth,h=stage.clientHeight;renderer.setSize(w,h,false);camera.aspect=w/h;camera.updateProjectionMatrix();requestDraw();}
new ResizeObserver(resize).observe(stage);document.addEventListener('visibilitychange',()=>requestDraw(3));
function reset(){controls.target.set(0,.48,0);camera.position.set(1.5,1.25,2.2);controls.update();requestDraw(3);}
function updateMaterial(){if(!mesh)return;for(const m of materials){m.wireframe=wire;m.color.set(colored?m.userData.color:0xa6adb5);m.map=colored?m.userData.map:null;m.needsUpdate=true;}requestDraw();}
document.querySelector('#reset').onclick=reset;
document.querySelector('#wire').onclick=e=>{wire=!wire;e.currentTarget.setAttribute('aria-pressed',String(wire));updateMaterial();};
document.querySelector('#edges').onclick=e=>{if(!boundaries)return;boundaries.visible=!boundaries.visible;e.currentTarget.setAttribute('aria-pressed',String(boundaries.visible));requestDraw();};
document.querySelector('#color').onclick=e=>{colored=!colored;e.currentTarget.setAttribute('aria-pressed',String(colored));updateMaterial();};
document.querySelector('#spin').onclick=e=>{spin=!spin;controls.autoRotate=spin;controls.autoRotateSpeed=1.2;e.currentTarget.setAttribute('aria-pressed',String(spin));requestDraw(2);};
try{
 const catalogResponse=await fetch('catalog.json');if(!catalogResponse.ok)throw new Error('Catalog could not load');
 const catalog=await catalogResponse.json(),requested=new URLSearchParams(location.search).get('asset');
 const asset=catalog.assets.find(a=>a.id===requested)||catalog.assets[0];if(!asset)throw new Error('No completed model available');
 const picker=document.querySelector('#asset');for(const entry of catalog.assets){const option=document.createElement('option');option.value=entry.id;option.textContent=entry.title;picker.append(option);}picker.value=asset.id;
 picker.onchange=()=>{const url=new URL(location.href);url.searchParams.set('asset',picker.value);location.href=url;};
 document.querySelector('#title').textContent=asset.title;document.title=`${asset.title} · MeshAxiom`;
 document.querySelector('#duration').textContent=asset.seconds==null?'—':`${Math.floor(asset.seconds/60)}m ${Math.round(asset.seconds%60)}s`;
 document.querySelector('#memory').textContent=asset.peak_gib==null?'—':`${asset.peak_gib.toFixed(2)} GiB`;
 const reference=document.querySelector('#reference');reference.src=asset.reference;reference.alt=`Sunburst reference for ${asset.title}`;
 document.querySelector('#note').textContent=asset.note;
 if(asset.model){const link=document.querySelector('#download');link.href=asset.model;link.download=`meshaxiom_${asset.id}.glb`;link.hidden=false;}
 const response=await fetch(asset.mesh);if(!response.ok)throw new Error(`Mesh HTTP ${response.status}`);const data=await response.json();
 const lo=[0,1,2].map(i=>Math.min(...data.vertices.map(v=>v[i]))),hi=[0,1,2].map(i=>Math.max(...data.vertices.map(v=>v[i]))),scale=1/(hi[2]-lo[2]);
 if(asset.render_glb){
  const gltf=await new GLTFLoader().loadAsync(asset.model);mesh=gltf.scene;
  let displayedTriangles=0;mesh.traverse(node=>{if(!node.isMesh)return;displayedTriangles+=(node.geometry.index?node.geometry.index.count:node.geometry.attributes.position.count)/3;for(const m of Array.isArray(node.material)?node.material:[node.material]){m.side=THREE.DoubleSide;m.userData.color=m.color.getHex();m.userData.map=m.map;materials.push(m);}});
  if(displayedTriangles!==data.faces.length)throw new Error('GLB and generated mesh triangle counts differ');
  const box=new THREE.Box3().setFromObject(mesh),height=box.max.y-box.min.y,center=box.getCenter(new THREE.Vector3());
  if(!(height>0))throw new Error('GLB has no height');
  mesh.scale.setScalar(1/height);mesh.position.set(-center.x/height,-box.min.y/height,-center.z/height);scene.add(mesh);
 }else{
 const geometry=new THREE.BufferGeometry(),buckets=[[],[]];
 const shades=asset.palette==='bin'?[0x354f6f,0xc4953f]:asset.palette==='cart'?[0x977344,0x354f6f]:[0xb5aca0,0xb5aca0];
 const palette=shades.map(color=>new THREE.MeshStandardMaterial({color,roughness:.86,side:THREE.DoubleSide}));for(const m of palette)m.userData.color=m.color.getHex();
 for(const face of data.faces){const z=face.reduce((sum,index)=>sum+(data.vertices[index][2]-lo[2])*scale/3,0);const positions=buckets[z>(asset.palette==='cart' ? .68 : .78)?1:0];for(const index of face){const v=data.vertices[index];positions.push((v[0]-(lo[0]+hi[0])/2)*scale,(v[2]-lo[2])*scale,-(v[1]-(lo[1]+hi[1])/2)*scale);}}
 const positions=buckets.flat();let offset=0;for(let i=0;i<buckets.length;i++){geometry.addGroup(offset,buckets[i].length/3,i);offset+=buckets[i].length/3;}
 geometry.setAttribute('position',new THREE.Float32BufferAttribute(positions,3));geometry.computeVertexNormals();mesh=new THREE.Mesh(geometry,palette);scene.add(mesh);

 materials=palette;for(const m of materials)m.userData.map=null;
 }
 const edgeCounts=new Map();for(const face of data.faces){for(let k=0;k<3;k++){const a=face[k],b=face[(k+1)%3],key=a<b?`${a},${b}`:`${b},${a}`;edgeCounts.set(key,(edgeCounts.get(key)||0)+1);}}
 const openPositions=[];let nonmanifold=0;for(const [key,count] of edgeCounts){if(count>2)nonmanifold++;if(count!==1)continue;for(const index of key.split(',').map(Number)){const v=data.vertices[index];openPositions.push((v[0]-(lo[0]+hi[0])/2)*scale,(v[2]-lo[2])*scale,-(v[1]-(lo[1]+hi[1])/2)*scale);}}
 const edgeGeometry=new THREE.BufferGeometry();edgeGeometry.setAttribute('position',new THREE.Float32BufferAttribute(openPositions,3));
 boundaries=new THREE.LineSegments(edgeGeometry,new THREE.LineBasicMaterial({color:0xff8066,depthTest:false}));boundaries.visible=false;boundaries.renderOrder=2;scene.add(boundaries);
 document.querySelector('#topology').textContent=`${openPositions.length/6} open edges · ${nonmanifold} nonmanifold edges. Open edges are highlighted in red when enabled; some openings may be intentional.`;
 const grid=new THREE.GridHelper(4,20,0x40516b,0x2d3c50);grid.position.y=-.015;grid.material.transparent=true;grid.material.opacity=.45;scene.add(grid);
 document.querySelector('#triangles').textContent=data.faces.length.toLocaleString();
 window.meshaxiomViewer={loaded:true,asset:asset.id,triangles:data.faces.length,sourceVertices:data.vertices.length,renderMode:asset.render_glb?'glb':'mesh-json',reset};loading.hidden=true;reset();
}catch(error){console.error(error);loading.textContent='The mesh could not load. Please reload.';window.meshaxiomViewer={loaded:false,error:String(error)};}
resize();
