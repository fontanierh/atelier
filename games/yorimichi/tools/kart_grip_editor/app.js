import * as T from 'three';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { matrix, frame, position, rotation, sideNames, wheelFrame, wheelHub, wheelTilt, mirrorLeft, twoBone, frontSteering } from './grip_math.js';

const $=s=>document.querySelector(s), config=await fetch('config.json').then(r=>r.json());
const chooser=$('#character');chooser.replaceChildren(...config.characters.map(id=>{const option=document.createElement('option');option.value=id;option.textContent=id[0].toUpperCase()+id.slice(1);return option;}));
const renderer=new T.WebGLRenderer({canvas:$('#view'),antialias:true,powerPreference:'low-power'});
renderer.setPixelRatio(Math.min(devicePixelRatio,2));renderer.outputColorSpace=T.SRGBColorSpace;
renderer.toneMapping=T.ACESFilmicToneMapping;renderer.toneMappingExposure=1.2;
const scene=new T.Scene();scene.background=new T.Color('#d8ddd6');
const camera=new T.PerspectiveCamera(35,1,.005,100);camera.up.set(0,0,1);
const orbit=new OrbitControls(camera,$('#view'));orbit.enableDamping=true;orbit.minDistance=.07;orbit.maxDistance=7;
const sky=new T.HemisphereLight(0xfff8e8,0x6d7e68,2.3);sky.position.set(0,0,4);scene.add(sky);
for(const [p,power] of [[[2,-3,4],3],[[-2,2,3],1.4]]){const l=new T.DirectionalLight(0xfff9ea,power);l.position.fromArray(p);scene.add(l);}
const grid=new T.GridHelper(8,40,0xc1c9ba,0xcbd2c4);grid.rotation.x=Math.PI/2;grid.position.z=-.02;scene.add(grid);
const loader=new GLTFLoader(), handles=new T.Group(), wheel=new T.Group(), kart=new T.Group();scene.add(handles,wheel,kart);
const column=new T.Mesh(new T.CylinderGeometry(.019,.019,1,20),new T.MeshStandardMaterial({color:0x97978b,roughness:.65}));scene.add(column);
const wheelMaterial=new T.MeshStandardMaterial({color:0x252b2b,roughness:.82});
const roadWheels=[];
let shoulderLean=0,shoulderDown=0,elbowBend=0;
let armPole=null,wristUpAxis=new T.Vector3(0,1,0);
let model=null,meta=null,bones={},correction={},left=null,right=null,savedRevision='',dirty=false;
let selected='hand_L',editBase=null,palmBase=null,history=[],future=[],angle=0,playing=false,loading=0,reach=0,ready=false;
let queued=false,remaining=0,activeView='left',lastStamp=0;
const status=message=>$('#status').textContent=message;
function requestDraw(count=2){remaining=Math.max(remaining,count);if(!queued){queued=true;requestAnimationFrame(draw);}}
function draw(stamp){queued=false;if(document.hidden)return;const dt=Math.min(.05,(stamp-lastStamp)/1000||0);lastStamp=stamp;
  if(playing){angle=Math.sin(stamp/1700)*T.MathUtils.degToRad(45);$('#steer').value=T.MathUtils.radToDeg(angle);updateSteering();}
  orbit.update();renderer.render(scene,camera);if(playing||remaining-->0)requestDraw(0);}
orbit.addEventListener('change',()=>requestDraw());orbit.addEventListener('start',()=>requestDraw(30));orbit.addEventListener('end',()=>requestDraw(35));
function resize(){const s=$('#stage');renderer.setSize(s.clientWidth,s.clientHeight,false);camera.aspect=s.clientWidth/s.clientHeight;camera.updateProjectionMatrix();requestDraw();}
new ResizeObserver(resize).observe($('#stage'));document.addEventListener('visibilitychange',()=>requestDraw());

function canonical(name){bones[name].updateWorldMatrix(true,false);return bones[name].matrixWorld.clone().multiply(correction[name].clone().invert());}
function setCanonical(name, desired){const bone=bones[name];bone.parent?.updateWorldMatrix(true,false);
  const local=desired.clone().multiply(correction[name]);if(bone.parent)local.premultiply(bone.parent.matrixWorld.clone().invert());
  local.decompose(bone.position,bone.quaternion,bone.scale);bone.updateMatrix();bone.updateWorldMatrix(false,true);}
function setAll(frames){for(const name of Object.keys(frames).sort((a,b)=>depth(a)-depth(b)))if(bones[name])setCanonical(name,matrix(frames[name]));}
function depth(name){let n=0;while(meta.parents[name]){name=meta.parents[name];n++;}return n;}
function captureLeft(){const inverse=wheelFrame(meta).invert();return Object.fromEntries(sideNames('L').map(n=>[n,inverse.clone().multiply(canonical(n)).toArray()]));}
function snapshot(){return {left:structuredClone(left),pole:[...armPole],lean:shoulderLean,shoulderDown,elbowBend,wheelHeight:meta.wheel_height_offset??0,wheelTilt:meta.wheel_tilt_offset_degrees??0};}
function restore(value){left=value.left;armPole=value.pole;shoulderLean=value.lean;shoulderDown=value.shoulderDown;elbowBend=value.elbowBend;meta.wheel_height_offset=value.wheelHeight;meta.wheel_tilt_offset_degrees=value.wheelTilt;syncArmControls();}
function remember(){if(!ready)return;history.push(snapshot());if(history.length>100)history.shift();future=[];}
function changed(){dirty=true;$('#save-state').textContent='Unsaved changes';$('#save').disabled=false;}

function solveArm(side,target){const upper=`upperarm_${side}`,fore=`forearm_${side}`,hand=`hand_${side}`;
  const oldUpper=canonical(upper),oldFore=canonical(fore),oldHand=canonical(hand);
  const hip=position(oldUpper),elbow=position(oldFore),wrist=position(oldHand);
  // Reference lengths come from the prepared bind skeleton, independently of the edited grip.
  const bind=meta.bind_world,a=position(matrix(bind[upper])).distanceTo(position(matrix(bind[fore]))),b=position(matrix(bind[fore])).distanceTo(position(matrix(bind[hand])));
  const elbowReference=elbow.clone().sub(hip).normalize().multiplyScalar(a).add(hip);
  const wristReference=wrist.clone().sub(elbow).normalize().multiplyScalar(b).add(elbowReference);
  const pole=new T.Vector3(...armPole).multiplyScalar(meta.scale);pole.y=Math.abs(pole.y)*(side==='L'?1:-1);
  const solved=twoBone(hip,elbowReference,wristReference,target,pole);reach=Math.max(reach,solved.miss);
  const qUpper=new T.Quaternion().setFromUnitVectors(elbow.clone().sub(hip).normalize(),solved.elbow.clone().sub(hip).normalize());
  setCanonical(upper,frame(hip,qUpper.multiply(rotation(oldUpper))));
  const nowFore=canonical(fore),nowHand=canonical(hand),foreHead=position(nowFore);
  const qFore=new T.Quaternion().setFromUnitVectors(position(nowHand).sub(foreHead).normalize(),target.clone().sub(foreHead).normalize());
  setCanonical(fore,frame(foreHead,qFore.multiply(rotation(nowFore))));
}
function applyBody(){
  setAll(meta.seated_world);
  if(Math.abs(shoulderLean)<1e-6)return;
  const pivot=position(matrix(meta.seated_world.pelvis));
  const turn=new T.Quaternion().setFromAxisAngle(new T.Vector3(0,1,0),T.MathUtils.degToRad(shoulderLean));
  const transformed={};
  for(const [name,values] of Object.entries(meta.seated_world)){
    let ancestor=name;while(ancestor&&ancestor!=='spine')ancestor=meta.parents[ancestor];if(!ancestor)continue;
    const original=matrix(values),at=position(original).sub(pivot).applyQuaternion(turn).add(pivot);
    transformed[name]=frame(at,turn.clone().multiply(rotation(original))).toArray();
  }
  setAll(transformed);
  // Match the stance's compensating head look as recline changes.
  const neck=position(canonical('neck')),look=new T.Quaternion().setFromAxisAngle(new T.Vector3(0,1,0),T.MathUtils.degToRad(-shoulderLean*.6));
  for(const name of ['neck','head']){const old=canonical(name);setCanonical(name,frame(position(old).sub(neck).applyQuaternion(look).add(neck),look.clone().multiply(rotation(old))));}
}
function applyGrip(){if(!ready)return;applyBody();const w=wheelFrame(meta,angle);wheel.matrixAutoUpdate=false;wheel.matrix.copy(w);wheel.updateMatrixWorld(true);const base=new T.Vector3(...meta.layout.steering_column_base).multiplyScalar(meta.scale),hub=wheelHub(meta);column.position.copy(base).add(hub).multiplyScalar(.5);column.quaternion.setFromUnitVectors(new T.Vector3(0,1,0),hub.clone().sub(base).normalize());column.scale.set(meta.scale,hub.distanceTo(base),meta.scale);reach=0;
  for(const [side,poses] of [['L',left],['R',right]]){
    const target=w.clone().multiply(matrix(poses[`hand_${side}`]));solveArm(side,position(target));
    for(const name of sideNames(side))setCanonical(name,w.clone().multiply(matrix(poses[name])));
  }
  steerRoadWheels();updateHandles();$('#reach').textContent=reach>.002?`Arm reach exceeded by ${(reach*1000).toFixed(0)} mm`:'Hands locked to the wheel';$('#reach').classList.toggle('warning',reach>.002);requestDraw();
}
function steerRoadWheels(){
  if(!meta)return;
  const turns=frontSteering(meta.layout,angle);
  for(const item of roadWheels)item.pivot.rotation.z=item.front?turns[item.left?0:1]:0;
}
function updateSteering(){if(!ready)return;$('#steer-value').textContent=`${T.MathUtils.radToDeg(angle).toFixed(1)}°`;const locked=Math.abs(angle)>.0001||playing;
  $('#edit-controls').disabled=locked;$('#edit-lock').hidden=!locked;applyGrip();}
function centre(){playing=false;$('#play').textContent='▶ Play';angle=0;$('#steer').value=0;updateSteering();}

function buildWheel(){wheel.clear();const l=meta.layout;
  const rim=new T.Mesh(new T.TorusGeometry(l.steering_radius,l.steering_tube_radius,16,80),wheelMaterial);rim.rotation.y=Math.PI/2;wheel.add(rim);
  const hub=new T.Mesh(new T.CylinderGeometry(.028,.028,.04,20),new T.MeshStandardMaterial({color:0x6f7269,roughness:.7}));hub.rotation.z=Math.PI/2;wheel.add(hub);
  for(const a of [Math.PI/2,7*Math.PI/6,11*Math.PI/6]){
    const end=new T.Vector3(0,Math.cos(a)*l.steering_radius,Math.sin(a)*l.steering_radius),spoke=new T.Mesh(new T.BoxGeometry(.008,.023,end.length()),new T.MeshStandardMaterial({color:0x878a80,roughness:.8}));
    spoke.position.copy(end).multiplyScalar(.5);spoke.quaternion.setFromUnitVectors(new T.Vector3(0,0,1),end.clone().normalize());wheel.add(spoke);}
}
async function loadCharacter(name){const ticket=++loading;ready=false;centre();$('#loading').hidden=false;$('#loading').textContent=`Loading ${name}…`;$('#save').disabled=true;$('#edit-controls').disabled=true;
  try{
    const [data,saved,gltf]=await Promise.all([fetch(`meta/${name}`).then(r=>{if(!r.ok)throw Error('Character export is not ready');return r.json();}),fetch(`saved/${name}`).then(r=>r.json()),loader.loadAsync(`models/${name}.glb`)]);
    if(ticket!==loading)return;
    if(model){scene.remove(model);model.traverse(o=>{if(o.isMesh){o.geometry.dispose();for(const m of Array.isArray(o.material)?o.material:[o.material]){m.map?.dispose();m.dispose();}}});}
    meta=data;model=gltf.scene;scene.add(model);model.updateMatrixWorld(true);bones={};correction={};
    model.traverse(o=>{if(o.isBone)bones[o.name]=o;});
    for(const [name,bind] of Object.entries(meta.bind_world))if(bones[name])correction[name]=matrix(bind).invert().multiply(bones[name].matrixWorld);
    for(const name of [...sideNames('L'),...sideNames('R')])if(!bones[name])throw Error(`Missing joint ${name}`);
    setAll(meta.seated_world);buildWheel();kart.scale.setScalar(meta.scale);
    armPole=[...meta.layout.elbow];shoulderLean=0;shoulderDown=0;elbowBend=0;meta.wheel_height_offset=0;meta.wheel_tilt_offset_degrees=0;
    savedRevision=saved.revision;left=structuredClone(meta.initial_hands.L);dirty=false;
    if(saved.pose){if(saved.pose.model_sha256===meta.model_sha256){left=structuredClone(saved.pose.hands.L);armPole=[...(saved.pose.arm_poles?.L??meta.layout.elbow)];shoulderLean=saved.pose.shoulder_lean_degrees??0;meta.wheel_height_offset=saved.pose.wheel_height_offset??0;meta.wheel_tilt_offset_degrees=saved.pose.wheel_tilt_offset_degrees??0;}else status('The saved grip uses an older model. Starting from this model’s pose.');}
    right=mirrorLeft(left,meta);history=[];future=[];ready=true;syncArmControls();applyGrip();selectJoint('hand_L');
    $('#loading').hidden=true;$('#edit-controls').disabled=false;$('#save').disabled=false;$('#save-state').textContent=saved.pose?'Saved on this machine':'Starting pose · not saved';
    setView('left');status('Edit the left hand. The other hand updates automatically.');window.gripEditor.loaded=true;
  }catch(error){console.error(error);$('#loading').textContent=error.message;window.gripEditor.error=String(error);}
}

const controls={};
function slider(container,key,label,min,max,step,fn){const div=document.createElement('div');div.className='control';
  const axis=document.createElement('label');axis.textContent=label;axis.className=key.at(-1);axis.htmlFor=key;
  const range=document.createElement('input');range.type='range';range.id=key;range.min=min;range.max=max;range.step=step;range.value=0;
  const number=document.createElement('input');number.type='number';number.setAttribute('aria-label',label);number.min=min;number.max=max;number.step=step;number.value=0;
  for(const input of [range,number]){input.addEventListener('pointerdown',()=>remember());input.addEventListener('keydown',e=>{if(['ArrowUp','ArrowDown','ArrowLeft','ArrowRight'].includes(e.key))remember();});
    input.addEventListener('input',()=>{const value=Number(input.value);if(!Number.isFinite(value))return;range.value=value;number.value=value;fn();});}
  div.append(axis,range,number);container.append(div);controls[key]={range,number,set:v=>{range.value=v;number.value=v;}};return div;}
function syncArmControls(){controls['wheel-angle'].set(wheelTilt(meta).toFixed(1));controls['shoulder-down'].set(shoulderDown);controls['elbow-bend'].set(elbowBend);controls['wheel-height'].set(((meta.wheel_height_offset??0)*meta.scale*1000).toFixed(1));controls['shoulder-lean'].set(shoulderLean);for(const [key,i] of [['arm-height',2],['arm-width',1]])controls[key].set(((armPole[i]-meta.layout.elbow[i])*meta.scale*1000).toFixed(1));}
function editArms(){if(!ready)return;shoulderLean=Number(controls['shoulder-lean'].number.value);armPole[2]=meta.layout.elbow[2]+Number(controls['arm-height'].number.value)/1000/meta.scale;armPole[1]=meta.layout.elbow[1]+Number(controls['arm-width'].number.value)/1000/meta.scale;changed();applyGrip();}
slider($('#wheel-controls'),'wheel-angle','Wheel angle °',15,75,.5,()=>{if(!ready)return;meta.wheel_tilt_offset_degrees=Number(controls['wheel-angle'].number.value)-meta.layout.steering_tilt_degrees;changed();applyGrip();});
slider($('#wheel-controls'),'wheel-height','Height mm',-180,180,1,()=>{if(!ready)return;meta.wheel_height_offset=Number(controls['wheel-height'].number.value)/1000/meta.scale;changed();applyGrip();});
function rotateArmJoint(which,value){
  if(!ready)return;
  const previous=which==='shoulder'?shoulderDown:elbowBend,delta=T.MathUtils.degToRad(value-previous);
  if(which==='shoulder')shoulderDown=value;else elbowBend=value;
  const shoulder=position(canonical('upperarm_L')),elbow=position(canonical('forearm_L')),wrist=position(canonical('hand_L'));
  const pivot=which==='shoulder'?shoulder:elbow,direction=(which==='shoulder'?elbow.clone().sub(shoulder):wrist.clone().sub(elbow)).normalize();
  const axis=direction.clone().cross(new T.Vector3(0,0,which==='shoulder'?-1:1)).normalize();
  if(axis.lengthSq()<.01)return;
  const turn=new T.Quaternion().setFromAxisAngle(axis,delta),w=wheelFrame(meta),inverse=w.clone().invert();
  // FK edits move the grip with the arm. Preserve real bone lengths before rotating;
  // the user can then place the wheel and wrist without an IK solver undoing the shoulder edit.
  const foreLength=position(matrix(meta.bind_world.forearm_L)).distanceTo(position(matrix(meta.bind_world.hand_L)));
  const physicalWrist=elbow.clone().add(wrist.clone().sub(elbow).normalize().multiplyScalar(foreLength));
  const correction=physicalWrist.sub(wrist),next={};
  for(const name of sideNames('L')){
    const old=w.clone().multiply(matrix(left[name]));
    const at=position(old).add(correction).sub(pivot).applyQuaternion(turn).add(pivot);
    next[name]=inverse.clone().multiply(frame(at,turn.clone().multiply(rotation(old)))).toArray();
  }
  const movedElbow=which==='shoulder'?elbow.clone().sub(pivot).applyQuaternion(turn).add(pivot):elbow;
  armPole=movedElbow.divideScalar(meta.scale).toArray();left=next;right=mirrorLeft(left,meta);changed();applyGrip();syncArmControls();selectJoint('hand_L');
}
slider($('#arm-controls'),'shoulder-down','Shoulder down °',-45,100,1,()=>rotateArmJoint('shoulder',Number(controls['shoulder-down'].number.value)));
slider($('#arm-controls'),'elbow-bend','Elbow bend °',-60,120,1,()=>rotateArmJoint('elbow',Number(controls['elbow-bend'].number.value)));
slider($('#arm-controls'),'shoulder-lean','Lean forward °',-15,45,.5,editArms);
slider($('#arm-controls'),'arm-height','Height mm',-180,180,1,editArms);
slider($('#arm-controls'),'arm-width','Spread mm',-180,180,1,editArms);
for(const axis of ['x','y','z'])slider($('#palm-controls'),`position-${axis}`,`${axis.toUpperCase()} mm`,-120,120,.1,edit);
slider($('#palm-controls'),'wrist-tilt','Tilt up °',-80,80,.5,edit);
for(const axis of ['x','y','z'])slider($('#rotation-controls'),`rotation-${axis}`,`${axis.toUpperCase()} °`,-150,150,.1,edit);
const names=['Index','Middle','Ring','Little','Thumb'];
for(let digit=0;digit<5;digit++){const row=document.createElement('div');row.className='finger-row';const label=document.createElement('span');label.textContent=names[digit];row.append(label);
  for(let joint=0;joint<3;joint++){const name=digit===4?['thumb_L','thumb_tip_L','thumb_end_L'][joint]:[`finger_${digit}_L`,`finger_tip_${digit}_L`,`finger_end_${digit}_L`][joint];
    const button=document.createElement('button');button.textContent=['Base','Middle','Tip'][joint];button.dataset.bone=name;button.onclick=()=>selectJoint(name);row.append(button);}$('#joints').append(row);}
function selectJoint(name){if(!ready)return;selected=name;editBase=canonical(name);const parent=meta.parents[name];editBase=parent&&bones[parent]?canonical(parent).invert().multiply(editBase):editBase;
  palmBase=wheelFrame(meta).invert().multiply(canonical('hand_L'));
  const knuckles=new T.Vector3();for(let i=0;i<4;i++)knuckles.add(position(canonical(`finger_${i}_L`)));knuckles.multiplyScalar(.25);
  wristUpAxis.copy(knuckles.sub(position(canonical('hand_L'))).normalize().cross(new T.Vector3(0,0,1)).normalize());
  wristUpAxis.applyQuaternion(rotation(wheelFrame(meta)).invert());
  for(const [key,control] of Object.entries(controls))if(!key.startsWith('arm-')&&key!=='shoulder-lean'&&key!=='wheel-height'&&key!=='wheel-angle'&&key!=='shoulder-down'&&key!=='elbow-bend')control.set(0);$('#palm-controls').hidden=name!=='hand_L';
  $('#selected-label').textContent=name==='hand_L'?'Palm & wrist rotation':`${names[name.includes('thumb')?4:Number(name.match(/\d/)[0])]} · ${name.includes('end')?'tip':name.includes('tip')?'middle':'base'} joint`;
  document.querySelectorAll('[data-bone]').forEach(b=>b.classList.toggle('active',b.dataset.bone===name));$('#palm').classList.toggle('active',name==='hand_L');updateHandles();requestDraw();}
function edit(){if(!ready||Math.abs(angle)>.0001)return;
  const e=new T.Euler(...['x','y','z'].map(a=>T.MathUtils.degToRad(Number(controls[`rotation-${a}`].number.value))),'XYZ');
  const q=rotation(editBase).multiply(new T.Quaternion().setFromEuler(e)),p=position(editBase);
  if(selected==='hand_L'){
    // Palm translation uses wheel axes and actual millimetres, while fingers use their own joint axes.
    const delta=new T.Vector3(...['x','y','z'].map(a=>Number(controls[`position-${a}`].number.value)/1000/meta.scale));
    const palmRotation=new T.Quaternion().setFromAxisAngle(wristUpAxis,T.MathUtils.degToRad(Number(controls['wrist-tilt'].number.value))).multiply(rotation(palmBase)).multiply(new T.Quaternion().setFromEuler(e));
    const local=frame(position(palmBase).add(delta),palmRotation,new T.Vector3().setScalar(1/meta.scale));
    setCanonical(selected,wheelFrame(meta).multiply(local));
  }else{const parent=meta.parents[selected];setCanonical(selected,canonical(parent).multiply(frame(p,q)));}
  left=captureLeft();right=mirrorLeft(left,meta);changed();applyGrip();}
$('#palm').onclick=()=>selectJoint('hand_L');
$('#undo').onclick=()=>{if(!history.length||!ready)return;future.push(snapshot());restore(history.pop());right=mirrorLeft(left,meta);changed();applyGrip();selectJoint(selected);};
$('#redo').onclick=()=>{if(!future.length||!ready)return;history.push(snapshot());restore(future.pop());right=mirrorLeft(left,meta);changed();applyGrip();selectJoint(selected);};
$('#reset-joint').onclick=()=>{if(!ready)return;remember();const parent=meta.parents[selected];const base=matrix(meta.seated_world[selected]),local=matrix(meta.seated_world[parent]).invert().multiply(base);
  setCanonical(selected,canonical(parent).multiply(local));left=captureLeft();right=mirrorLeft(left,meta);changed();applyGrip();selectJoint(selected);};
$('#reset-all').onclick=()=>{if(!ready)return;centre();remember();left=structuredClone(meta.initial_hands.L);armPole=[...meta.layout.elbow];shoulderLean=0;shoulderDown=0;elbowBend=0;meta.wheel_height_offset=0;meta.wheel_tilt_offset_degrees=0;syncArmControls();right=mirrorLeft(left,meta);changed();applyGrip();selectJoint('hand_L');};
$('#save').onclick=async()=>{if(!ready)return;$('#save').disabled=true;
  try{const payload={schema:1,character:meta.id,model_sha256:meta.model_sha256,authored_side:'L',mirror:'anatomical-bind',hands:{L:left,R:right},wheel_tilt_offset_degrees:meta.wheel_tilt_offset_degrees??0,wheel_height_offset:meta.wheel_height_offset??0,shoulder_lean_degrees:shoulderLean,arm_poles:{L:armPole,R:[armPole[0],-armPole[1],armPole[2]]},revision:savedRevision};
    const response=await fetch('save',{method:'POST',headers:{'Content-Type':'application/json','X-Grip-Token':config.token},body:JSON.stringify(payload)}),result=await response.json();
    if(!response.ok)throw Error(result.error);savedRevision=result.revision;dirty=false;$('#save-state').textContent='Saved on this machine';status(`${meta.label} grip saved. Both hands remain locked to the wheel.`);
  }catch(error){status(error.message);$('#save-state').textContent='Save failed';}finally{$('#save').disabled=false;}};
$('#character').onchange=()=>{if(dirty&&!confirm('Switch characters and discard unsaved changes?')){$('#character').value=meta.id;return;}loadCharacter($('#character').value);};
$('#steer').oninput=()=>{playing=false;$('#play').textContent='▶ Play';angle=T.MathUtils.degToRad(Number($('#steer').value));updateSteering();};
$('#centre').onclick=$('#straight').onclick=centre;
$('#play').onclick=()=>{playing=!playing;$('#play').textContent=playing?'❚❚ Pause':'▶ Play';updateSteering();requestDraw();};
$('#ghost').onchange=()=>{wheelMaterial.transparent=$('#ghost').checked;wheelMaterial.opacity=$('#ghost').checked?.25:1;wheelMaterial.depthWrite=!$('#ghost').checked;requestDraw();};

const markerGeometry=new T.SphereGeometry(1,10,8),markerNormal=new T.MeshBasicMaterial({color:0x779773,depthTest:false,transparent:true,opacity:.85}),markerSelected=new T.MeshBasicMaterial({color:0xea8954,depthTest:false,transparent:true,opacity:.95});
function updateHandles(){if(!handles.children.length)for(const name of sideNames('L')){const marker=new T.Mesh(markerGeometry,markerNormal);marker.userData.bone=name;marker.renderOrder=20;handles.add(marker);}
  for(const marker of handles.children){const name=marker.userData.bone;marker.position.copy(position(canonical(name)));marker.scale.setScalar(name===selected?.0045:.0028);marker.material=name===selected?markerSelected:markerNormal;}
  handles.visible=!playing&&Math.abs(angle)<.0001;}
const ray=new T.Raycaster();let down;
$('#view').addEventListener('pointerdown',e=>down=[e.clientX,e.clientY]);
$('#view').addEventListener('pointerup',e=>{if(!ready||!handles.visible||!down||Math.hypot(e.clientX-down[0],e.clientY-down[1])>5)return;
  const r=$('#view').getBoundingClientRect();ray.setFromCamera(new T.Vector2((e.clientX-r.left)/r.width*2-1,-(e.clientY-r.top)/r.height*2+1),camera);const hit=ray.intersectObject(handles,true)[0];if(hit)selectJoint(hit.object.userData.bone);});
function setView(name){if(!ready)return;activeView=name;const side=name.startsWith('right')?'R':'L',sign=side==='L'?1:-1;
  const overviews={full:[2.1,-2.3,1.5],front:[2.65,-1.9,1.3],rear:[-2.4,1.9,1.4],side:[.1,3.3,1.0],elevated:[1.9,2.4,2.8]};
  const target=overviews[name]?new T.Vector3(-.05,0,.55).multiplyScalar(meta.scale):position(canonical(`hand_${side}`)).lerp(position(wheelFrame(meta)),.12);
  const offset=overviews[name]?new T.Vector3(...overviews[name]):name.endsWith('palm')?new T.Vector3(.04,-sign*.28,.10):new T.Vector3(.28,sign*.27,.17);
  orbit.target.copy(target);camera.position.copy(target).add(offset.multiplyScalar(meta.scale*(overviews[name]&&name!=='full'?1.3:1)));orbit.update();document.querySelectorAll('[data-view]').forEach(b=>b.classList.toggle('active',b.dataset.view===name));requestDraw(4);}
document.querySelectorAll('[data-view]').forEach(button=>button.onclick=()=>setView(button.dataset.view));
window.addEventListener('beforeunload',e=>{if(dirty){e.preventDefault();e.returnValue='';}});
document.addEventListener('keydown',e=>{if((e.metaKey||e.ctrlKey)&&e.key.toLowerCase()==='s'){e.preventDefault();$('#save').click();}if((e.metaKey||e.ctrlKey)&&e.key.toLowerCase()==='z'){e.preventDefault();$(e.shiftKey?'#redo':'#undo').click();}});
window.gripEditor={loaded:false,
  wheelReport:()=>roadWheels.map(w=>({front:w.front,left:w.left,yaw:w.pivot.rotation.z,position:w.pivot.position.toArray(),scale:w.pivot.scale.toArray()})),state:()=>({character:meta?.id,left:structuredClone(left),right:structuredClone(right),angle,reach,selected,dirty,armPole:[...armPole],shoulderLean,wheelHeight:meta.wheel_height_offset??0,elbow:position(canonical('forearm_L')).toArray(),shoulder:position(canonical('upperarm_L')).toArray()}),setAngle:degrees=>{angle=T.MathUtils.degToRad(degrees);updateSteering();},selectJoint,setView,
  lockError:()=>{const inverse=wheelFrame(meta,angle).invert();let error=0;for(const [side,poses] of [['L',left],['R',right]])for(const name of sideNames(side)){const local=inverse.clone().multiply(canonical(name));error=Math.max(error,...local.elements.map((v,i)=>Math.abs(v-poses[name][i])));}return error;}};
resize();await loadCharacter($('#character').value);
loader.load('models/kart.glb',gltf=>{
  kart.add(gltf.scene);kart.updateMatrixWorld(true);
  // Older context exports include a fixed column in the body. Remove just that tube;
  // the live column above is telescopic and always meets the wheel at its new angle.
  const base=new T.Vector3(...meta.layout.steering_column_base),hub=new T.Vector3(...meta.layout.steering),axis=hub.clone().sub(base),length=axis.length();axis.normalize();let removed=0;
  gltf.scene.traverse(ob=>{if(!ob.isMesh||!ob.name.includes('SM_Kart_Body'))return;const g=ob.geometry,p=g.attributes.position,index=g.index?.array??Array.from({length:p.count},(_,i)=>i),keep=[];
    const onTube=i=>{const v=new T.Vector3().fromBufferAttribute(p,i).applyMatrix4(ob.matrixWorld).divideScalar(meta.scale).sub(base),along=v.dot(axis);return along>=-.002&&along<=length+.002&&v.addScaledVector(axis,-along).length()<.0205;};
    for(let i=0;i<index.length;i+=3){if([index[i],index[i+1],index[i+2]].every(onTube))removed++;else keep.push(index[i],index[i+1],index[i+2]);}g.setIndex(keep);
  });window.gripEditor.columnTrianglesRemoved=removed;
  const meshes=[];gltf.scene.traverse(ob=>{if(ob.isMesh&&ob.name.includes('SM_Kart_Wheel'))meshes.push(ob);});
  for(const mesh of meshes){
    const centre=kart.worldToLocal(mesh.getWorldPosition(new T.Vector3()));
    const pivot=new T.Group();pivot.position.copy(centre);kart.add(pivot);pivot.updateMatrixWorld(true);pivot.attach(mesh);
    roadWheels.push({pivot,front:centre.x>0,left:centre.y>0});
  }
  steerRoadWheels();requestDraw();},undefined,error=>console.warn('Kart context not loaded',error));
