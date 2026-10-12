import * as THREE from 'three';

// Stable quaternion springs. Every strand has a moving proximal joint.
export async function setupHairPreview(root,requestDraw,configUrl=new URL('./hair-physics-r03.json',import.meta.url)){
 const config=await fetch(configUrl).then(r=>r.json());
 const boneMap=new Map();root.traverse(o=>{if(o.isBone)boneMap.set(o.name,o);});
 const find=n=>boneMap.get(n)||boneMap.get(n.replaceAll(':','_'))||boneMap.get(n.replaceAll(':',''));
 const head=find(config.anchor_bone),spine=find(config.garment_bone);if(!head||!spine)throw Error('Missing anchors');
 const headRest=head.quaternion.clone(),spineRest=spine.quaternion.clone(),rootPosition=root.position.clone(),rootRotation=root.quaternion.clone();
 root.updateMatrixWorld(true);
 const restRootInv=root.matrixWorld.clone().invert(),restHeadInv=head.matrixWorld.clone().invert(),restHeadMatrix=head.matrixWorld.clone(),restSpineInv=spine.matrixWorld.clone().invert(),restSpineMatrix=spine.matrixWorld.clone();
 const chains=config.chains.map(c=>({config:c,bones:c.bones.map(find),states:[],probeIndices:[],restQuaternion:[],maxRootLag:0,rootAcceleration:new THREE.Vector3(),previousRoot:null,previousVelocity:new THREE.Vector3()}));
 const byComponent=new Map(chains.map(c=>[c.config.component,c]));
 for(const c of chains){
  if(c.bones.some(b=>!b))throw Error('Missing strand bone');
  c.restQuaternion=c.bones.map(b=>b.quaternion.clone());
  c.states=c.bones.map((b,j)=>({q:b.getWorldQuaternion(new THREE.Quaternion()),velocity:new THREE.Vector3(),relativeHead:head.getWorldQuaternion(new THREE.Quaternion()).invert().multiply(b.getWorldQuaternion(new THREE.Quaternion())),omega:c.config.spring_omega*.72*(1-.10*j)}));
 }
 const skinned=[];let bodyMesh;root.traverse(o=>{if(o.isSkinnedMesh&&o.name.startsWith('Nox_head'))skinned.push(o);if(o.isSkinnedMesh&&o.name.startsWith('Nox_body'))bodyMesh=o;});
 if(skinned.length!==1)throw Error('Missing skinned head');const mesh=skinned[0];
 const skin=mesh.geometry.attributes.skinIndex,weight=mesh.geometry.attributes.skinWeight,position=mesh.geometry.attributes.position;
 for(let i=0;i<position.count;i++){
  let component=null,best=0;
  for(let k=0;k<4;k++){
   const w=weight.getComponent(i,k),bone=mesh.skeleton.bones[skin.getComponent(i,k)];
   const match=bone?.name.match(/NoxLoc_(\d+)_/);if(match&&w>best){component=Number(match[1]);best=w;}
  }
  if(component!==null&&i%3===0)byComponent.get(component)?.probeIndices.push(i);
 }
 // Measured garment envelope. Probe the actual skinned surface, with no extra tube radius.
 let toNeutralRoot=restRootInv.clone().multiply(restSpineMatrix).multiply(spine.matrixWorld.clone().invert());
 const env=config.collider,na=env.angles.length,nz=env.z_samples.length,z0=env.z_samples[0],z1=env.z_samples.at(-1);
 function garmentGap(world){
  const p=world.clone().applyMatrix4(toNeutralRoot),z=p.y;if(z<z0||z>z1)return Infinity;
  const x=p.x-env.axis_xy[0],y=-p.z-env.axis_xy[1],ai=((Math.atan2(y,x)+Math.PI)/(2*Math.PI)*na+na)%na;
  const zi=Math.max(0,Math.min(nz-1,Math.round((z-z0)/(z1-z0)*(nz-1))));
  let radius=0;for(const off of [-1,0,1])radius=Math.max(radius,env.radius_samples[zi][(Math.round(ai)+off+na)%na]);
  return radius>0?Math.hypot(x,y)-radius:Infinity;
 }
 const probeWorld=i=>mesh.getVertexPosition(i,new THREE.Vector3()).applyMatrix4(mesh.matrixWorld);
 for(const c of chains){
  c.probes=c.probeIndices.filter(i=>probeWorld(i).applyMatrix4(restRootInv).y<.948).map(i=>({index:i,minimum:Math.min(0,garmentGap(probeWorld(i)))-.0003}));
 }
 // Exact static garment triangles in the demo's neutral frame. The demo moves
 // the whole avatar; native game animation needs its own moving colliders.
 const vertexComponent=i=>{let best=0,cid=null;for(let k=0;k<4;k++){const w=weight.getComponent(i,k),m=mesh.skeleton.bones[skin.getComponent(i,k)]?.name.match(/NoxLoc_(\d+)_/);if(m&&w>best){best=w;cid=Number(m[1]);}}return cid;};
 for(const c of chains)c.triangles=[];
 const headIndex=mesh.geometry.index;
 for(let k=0;k<headIndex.count;k+=3){const ids=[headIndex.getX(k),headIndex.getX(k+1),headIndex.getX(k+2)],cid=ids.map(vertexComponent).find(v=>v!==null);if(cid!==undefined&&ids.some(i=>probeWorld(i).applyMatrix4(restRootInv).y<.96))byComponent.get(cid)?.triangles.push(ids);}
 const bodyIndex=bodyMesh.geometry.index,bodyPoints=[];
 for(let i=0;i<bodyMesh.geometry.attributes.position.count;i++)bodyPoints.push(bodyMesh.getVertexPosition(i,new THREE.Vector3()).applyMatrix4(bodyMesh.matrixWorld).applyMatrix4(restRootInv));
 const bodyTriangles=[];
 for(let k=0;k<bodyIndex.count;k+=3){const t=[bodyPoints[bodyIndex.getX(k)],bodyPoints[bodyIndex.getX(k+1)],bodyPoints[bodyIndex.getX(k+2)]];const box=new THREE.Box3().setFromPoints(t);if(box.max.y>.80&&box.min.x<.14&&box.max.x>-.14)bodyTriangles.push({t,box,centre:box.getCenter(new THREE.Vector3())});}
 function tree(items){const box=new THREE.Box3();for(const t of items)box.union(t.box);if(items.length<=8)return {box,items};const size=box.getSize(new THREE.Vector3()),axis=size.x>size.y&&size.x>size.z?'x':size.y>size.z?'y':'z';items.sort((a,b)=>a.centre[axis]-b.centre[axis]);const mid=items.length>>1;return {box,left:tree(items.slice(0,mid)),right:tree(items.slice(mid))};}
 const garmentTree=tree(bodyTriangles);
 function overlaps(a,b){
  const ae=a.map((p,i)=>a[(i+1)%3].clone().sub(p)),be=b.map((p,i)=>b[(i+1)%3].clone().sub(p)),an=ae[0].clone().cross(ae[1]),bn=be[0].clone().cross(be[1]);
  const axes=[an,bn];for(const e of ae)for(const f of be)axes.push(e.clone().cross(f));for(const e of [...ae,...be])axes.push(an.clone().cross(e));
  for(const axis of axes){if(axis.lengthSq()<1e-18)continue;const ap=a.map(p=>p.dot(axis)),bp=b.map(p=>p.dot(axis));if(Math.max(...ap)<Math.min(...bp)-1e-12||Math.max(...bp)<Math.min(...ap)-1e-12)return false;}return true;
 }
 function touches(t,box,node){if(!box.intersectsBox(node.box))return false;if(node.items)return node.items.some(o=>box.intersectsBox(o.box)&&overlaps(t,o.t));return touches(t,box,node.left)||touches(t,box,node.right);}
 function exactSafe(c){const points=new Map(),point=i=>{if(!points.has(i))points.set(i,probeWorld(i).applyMatrix4(toNeutralRoot));return points.get(i);};for(const ids of c.triangles){const t=ids.map(point),box=new THREE.Box3().setFromPoints(t);if(touches(t,box,garmentTree))return false;}return true;}
 const headSpacePoint=i=>probeWorld(i).applyMatrix4(head.matrixWorld.clone().invert());
 const geometryTracks=chains.map(c=>{
  const vertices=[];for(let i=0;i<position.count;i++){
   let member=false;for(let k=0;k<4;k++){const bone=mesh.skeleton.bones[skin.getComponent(i,k)];if(weight.getComponent(i,k)>0&&bone?.name.startsWith('NoxLoc_'+String(c.config.component).padStart(5,'0')+'_'))member=true;}
   if(member)vertices.push(i);
  }
  const ys=vertices.map(i=>probeWorld(i).applyMatrix4(restRootInv).y),lo=Math.min(...ys),hi=Math.max(...ys);
  return {component:c.config.component,vertices:vertices.map((i,j)=>({i,t:(hi-ys[j])/Math.max(hi-lo,1e-8),rest:headSpacePoint(i)})),upper:0,middle:0,tip:0};
 });
 function sampleGeometry(){
  root.updateMatrixWorld(true);mesh.skeleton.update();
  for(const track of geometryTracks)for(const point of track.vertices){
   const distance=headSpacePoint(point.i).distanceTo(point.rest),zone=point.t<.34?'upper':point.t<.68?'middle':'tip';track[zone]=Math.max(track[zone],distance);
  }
  return geometryTracks.map(t=>({component:t.component,upper:t.upper,middle:t.middle,tip:t.tip}));
 }
 const button=document.querySelector('#motion');let active=false,start=0,last=0,accumulator=0,elapsed=0;
 function setPose(t){
  root.position.copy(rootPosition).add(new THREE.Vector3(.012*Math.sin(t*1.2),.005*Math.sin(t*2.4),.007*Math.sin(t*1.4)));
  root.quaternion.copy(rootRotation).multiply(new THREE.Quaternion().setFromEuler(new THREE.Euler(.10*Math.sin(t*1.3),.10*Math.sin(t*.9),.06*Math.sin(t*1.65))));
  head.quaternion.copy(headRest);spine.quaternion.copy(spineRest);root.updateMatrixWorld(true);
 }
 function updateSpring(state,target,dt,damping,cap){
  const error=target.clone().multiply(state.q.clone().invert());if(error.w<0){error.x*=-1;error.y*=-1;error.z*=-1;error.w*=-1;}
  const e=new THREE.Vector3(error.x,error.y,error.z),length=e.length();if(length>1e-9)e.multiplyScalar(2*Math.atan2(length,error.w)/length);
  // Closed-form critically damped step in the small-angle rotation space.
  const omega=state.omega*damping,u=state.velocity.clone().addScaledVector(e,-omega),decay=Math.exp(-omega*dt);
  const remaining=e.clone().addScaledVector(u,-dt).multiplyScalar(decay),advance=e.clone().sub(remaining);
  state.velocity.addScaledVector(u,-omega*dt).multiplyScalar(decay);
  const angle=advance.length();if(angle>1e-9)state.q.premultiply(new THREE.Quaternion().setFromAxisAngle(advance.divideScalar(angle),angle)).normalize();
  const lag=state.q.angleTo(target);if(lag>cap)state.q.slerp(target,1-cap/lag);
 }
 function apply(c,blend=1){
  for(let j=0;j<c.bones.length;j++){
   const b=c.bones[j],neutral=c.restQuaternion[j],desired=b.parent.getWorldQuaternion(new THREE.Quaternion()).invert().multiply(c.states[j].q);
   b.quaternion.copy(neutral).slerp(desired,blend);b.updateWorldMatrix(false,true);
  }
 }
 function safe(c){
  for(const probe of c.probes)if(garmentGap(probeWorld(probe.index))<probe.minimum)return false;return exactSafe(c);
 }
 function reset(){
  root.position.copy(rootPosition);root.quaternion.copy(rootRotation);head.quaternion.copy(headRest);spine.quaternion.copy(spineRest);
  for(const c of chains)c.bones.forEach((b,j)=>b.quaternion.copy(c.restQuaternion[j]));root.updateMatrixWorld(true);
  for(const c of chains)c.states.forEach((s,j)=>{s.q.copy(c.bones[j].getWorldQuaternion(new THREE.Quaternion()));s.velocity.set(0,0,0);});
  for(const c of chains){c.previousRoot=null;c.previousVelocity.set(0,0,0);c.rootAcceleration.set(0,0,0);}
 }
 button.onclick=()=>{active=!active;button.setAttribute('aria-pressed',String(active));button.textContent=active?'Pause motion':'Motion preview';start=performance.now()/1000;last=start;elapsed=0;accumulator=0;if(!active)reset();requestDraw(3);};
 window.characterMotion=()=>{
  if(!active)return;const frameStart=performance.now(),now=frameStart/1000,dt=Math.min(.25,Math.max(.001,now-last));last=now;elapsed=now-start;
  setPose(elapsed);toNeutralRoot=restRootInv.clone().multiply(restSpineMatrix).multiply(spine.matrixWorld.clone().invert());
  const headWorld=head.getWorldQuaternion(new THREE.Quaternion());
  for(const c of chains){
   const rootPoint=c.bones[0].getWorldPosition(new THREE.Vector3());
   if(c.previousRoot){
    const velocity=rootPoint.clone().sub(c.previousRoot).divideScalar(dt),acceleration=velocity.clone().sub(c.previousVelocity).divideScalar(dt);
    acceleration.clampLength(0,.15);c.rootAcceleration.lerp(acceleration,1-Math.exp(-8*dt));c.previousVelocity.copy(velocity);
   }
   c.previousRoot=rootPoint;
   const strandLength=Math.max(.03,c.config.rest_nodes_world.slice(1).reduce((n,p,i)=>n+new THREE.Vector3(...p).distanceTo(new THREE.Vector3(...c.config.rest_nodes_world[i])),0));
   c.states.forEach(s=>{
    const target=headWorld.clone().multiply(s.relativeHead),tangent=new THREE.Vector3(0,1,0).applyQuaternion(target);
    const torque=tangent.cross(c.rootAcceleration).negate().divideScalar(strandLength*s.omega*s.omega),angle=torque.length();
    if(angle>1e-8)target.premultiply(new THREE.Quaternion().setFromAxisAngle(torque.divideScalar(angle),Math.min(angle,.02)));
    updateSpring(s,target,dt,c.config.spring_damping,THREE.MathUtils.degToRad(c.config.max_lag_degrees));
   });
  }
  for(const c of chains){
   apply(c);
   // Reduce lag toward the clear neutral pose when a surface approaches the hood.
   if(!safe(c)){
    let blend=.8;while(blend>.015&&!safe(c)){apply(c,blend);blend*=.65;}
    if(!safe(c))apply(c,0);
   }
   const lag=c.bones[0].quaternion.angleTo(c.restQuaternion[0]);c.maxRootLag=Math.max(c.maxRootLag,lag);
  }
  root.updateMatrixWorld(true);mesh.skeleton.update();window.characterHair.frameMilliseconds=performance.now()-frameStart;requestDraw(1);
 };
 button.disabled=false;button.textContent='Motion preview';
 window.characterHair={sampleGeometry,chains:chains.length,bones:boneMap.size,active:()=>active,stats:()=>({elapsed,allRootsMoving:chains.filter(c=>c.maxRootLag>1e-5).length,rootLagDegrees:chains.map(c=>({component:c.config.component,max:THREE.MathUtils.radToDeg(c.maxRootLag)}))}),reset,pause:()=>{active=false;button.setAttribute('aria-pressed','false');button.textContent='Motion preview';requestDraw(2);}};
}
