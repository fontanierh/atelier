import {updateStamina} from './stamina.js';
import {Config,PixelStreaming,Logger,LogLevel} from '@epicgames-ps/lib-pixelstreamingfrontend-ue5.8';
import {renderSettings} from './settings.js';
import {createMap} from './map.js';
Logger.InitLogging(LogLevel.Warning,false);
const $=id=>document.getElementById(id);
function diagnostic(event,data={}){fetch('/diagnostics',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({event,...data}),keepalive:true}).catch(()=>{});}
addEventListener('error',e=>diagnostic('script-error',{message:e.message}));
addEventListener('unhandledrejection',e=>diagnostic('promise-error',{message:String(e.reason?.message||e.reason)}));
const NativePeer=window.RTCPeerConnection;
window.RTCPeerConnection=class extends NativePeer{
 constructor(...args){super(...args);diagnostic('peer-created');
  this.addEventListener('signalingstatechange',()=>diagnostic('sdp-state',{state:this.signalingState}));
  this.addEventListener('icegatheringstatechange',()=>diagnostic('ice-gathering',{state:this.iceGatheringState}));
  this.addEventListener('icecandidateerror',e=>diagnostic('ice-error',{code:e.errorCode,message:e.errorText}));
  this.addEventListener('icecandidate',e=>diagnostic('ice-candidate',{type:e.candidate?.type||'complete'}));
  this.addEventListener('iceconnectionstatechange',()=>diagnostic('ice-state',{state:this.iceConnectionState}));
  this.addEventListener('connectionstatechange',()=>diagnostic('peer-state',{state:this.connectionState}));
 }
 async setRemoteDescription(...args){try{return await super.setRemoteDescription(...args);}catch(e){diagnostic('remote-description-error',{message:e.message});throw e;}}
 async addIceCandidate(...args){try{return await super.addIceCandidate(...args);}catch(e){diagnostic('remote-candidate-error',{message:e.message});throw e;}}
};
diagnostic('page',{agent:navigator.userAgent});
const config=new Config({useUrlParams:true,initialSettings:{AutoConnect:true,AutoPlayVideo:true,ForceTURN:true,StartVideoMuted:true,WaitForStreamer:true,KeyboardInput:false,MouseInput:false,TouchInput:false,GamepadInput:false,AFKDetection:false,MatchViewportResolution:false,MaxReconnectAttempts:20}});
const stream=new PixelStreaming(config,{videoElementParent:$('video')});
const standalone=matchMedia('(display-mode: standalone)').matches||navigator.standalone;
$('install-hint').hidden=standalone||!/iPhone|iPad|iPod/.test(navigator.userAgent);
$('screen').hidden=!!standalone;
for(const event of ['webRtcFailed','webRtcDisconnected','playStreamError','playStreamRejected'])stream.addEventListener(event,e=>diagnostic(event,{detail:e.data}));
let connected=false,playing=false,muted=true,buttons=0,dx=0,dy=0,mx=0,my=0;
let stickPointer=null,lookPointer=null,lookLast=null,lastState=null;
const keys=new Set(),buttonPointers=new Map(),skatePointers=new Map();
function status(s){$('status').textContent=s;$('welcome-status').textContent=s;}
function send(){
 if(!connected)return;
 const kx=(keys.has('KeyD')?1:0)-(keys.has('KeyA')?1:0),ky=(keys.has('KeyW')?1:0)-(keys.has('KeyS')?1:0);
 const skate=!!(lastState?.skating||lastState?.sailboat),touches=[...skatePointers.values()];
 const steer=touches.filter(t=>t.axis==='turn').reduce((sum,t)=>sum+t.value,0);
 const braking=keys.has('KeyS')||touches.some(t=>t.axis==='drive'&&t.value<0);
 const pushing=keys.has('KeyW')||touches.some(t=>t.axis==='drive'&&t.value>0);
 const x=skate?steer+kx:mx+kx,y=skate?(braking?-1:pushing?1:0):my+ky;
 stream.emitUIInteraction({yorimichi:1,paused:!playing,x:playing?Math.max(-1,Math.min(1,x)):0,y:playing?Math.max(-1,Math.min(1,y)):(lastState?.skating||lastState?.sailboat?-1:0),dx:playing?dx:0,dy:playing?dy:0,buttons:playing?buttons:0});dx=dy=0;
}
function reset(){mx=my=dx=dy=buttons=0;keys.clear();buttonPointers.clear();skatePointers.clear();stickPointer=lookPointer=null;lookLast=null;$('knob').style.transform='';document.querySelectorAll('.held').forEach(b=>b.classList.remove('held'));send();}
// The ride speed the passenger picked, shown on the status line and set by the two flight buttons.
const speedLabel=value=>(value&&value!==1?String(Number(value.toFixed(2))):'1')+'\u00d7';
const flightSpeed=delta=>{if(connected)stream.emitUIInteraction({yorimichi:1,action:'flightSpeed',delta});};
for(const [id,delta] of [['slower',-1],['faster',1]]){
 const button=$(id);
 const press=event=>{event.preventDefault();event.stopPropagation();flightSpeed(delta);};
 button.addEventListener('pointerdown',press);
 button.addEventListener('click',event=>event.preventDefault());
}
function updateButtons(){buttons=0;for(const b of buttonPointers.values())buttons|=b;const map={Space:1,KeyF:2,KeyE:4,KeyK:8,KeyQ:16,KeyJ:32,ShiftLeft:128,ShiftRight:128,ControlLeft:256,ControlRight:256};for(const k of keys)buttons|=map[k]||0;send();}
stream.addEventListener('webRtcConnected',()=>status('Connected · starting video…'));
stream.addEventListener('dataChannelOpen',()=>{connected=true;$('play').textContent='Play Yorimichi';send();});
stream.addEventListener('dataChannelClose',()=>{connected=false;reset();});
stream.addEventListener('webRtcDisconnected',()=>{connected=false;reset();playing=false;document.querySelectorAll('dialog[open]').forEach(d=>d.close());$('controls').hidden=true;$('welcome').hidden=false;$('play').textContent='Reconnect';status('Connection lost · tap Reconnect');});
stream.addEventListener('webRtcFailed',()=>{connected=false;reset();playing=false;document.querySelectorAll('dialog[open]').forEach(d=>d.close());$('controls').hidden=true;$('welcome').hidden=false;$('play').textContent='Reconnect';status('Could not connect · keep Tailscale on and tap Reconnect');});
stream.addEventListener('subscribeFailed',()=>{status('Game is in use · close other play tabs, then reconnect');$('welcome').hidden=false;$('play').textContent='Reconnect';});
stream.addEventListener('playStreamRejected',()=>{$('welcome').hidden=false;status('Tap Play to start the video');});
stream.addResponseEventListener('yorimichi',response=>{try{const state=JSON.parse(response);if(state.yorimichi!==1)return;if(state.kind==='hint'){toast(state.text);return;}if(state.kind==='settings'){window.yorimichi.settings=state.values;renderSettings(state.values,changeSetting);$('settings-status').textContent='Saved in the game';return;}if(state.kind==='map'){map.receive(state);window.yorimichi.map=state;return;}if(state.kind==='teleport'){const zone=map.data?.zones.find(z=>z.key===state.zone);toast(state.ok?`Arrived: ${zone?.name||state.zone}`:'That place is not on the map');return;}$('ramp-hint').textContent=state.rampHint||'';$('ramp-hint').hidden=!state.rampHint;$('use').textContent=state.rampHint?.startsWith('Flying to')?'Skip flight':state.rampHint?.startsWith('Use to board')?'Fly':state.rampHint?.startsWith('Use to call')?'Call ship':(state.megaStage===1||state.rampHint?.startsWith('Use to drop'))?'Drop in':state.rampHint?.includes('ladder')?'Climb':'Use';updateStamina(state);map.update(state);const aboard=state.zeppelinStage>=2&&state.zeppelinStage<=6;$('controls').classList.toggle('aboard',aboard);if(aboard)$('stamina').hidden=true;$('slower').hidden=!aboard;$('faster').hidden=!aboard;$('slower').textContent='Slower';$('faster').textContent='Faster · '+speedLabel(state.flightSpeed);window.yorimichi.flightSpeed=state.flightSpeed;const changedMode=!!lastState?.skating!==!!state.skating||!!lastState?.sailboat!==!!state.sailboat;lastState=state;if(changedMode){reset();const riding=state.skating||state.sailboat;$('controls').classList.toggle('skating',!!riding);$('controls').classList.toggle('sailing',!!state.sailboat);$('stick').hidden=!!riding;$('skate-steering').hidden=!riding;}window.yorimichi.state=state;window.yorimichi.history.push({...state,time:Date.now()});if(window.yorimichi.history.length>200)window.yorimichi.history.shift();$('push').textContent=state.sailboat?'Raise sail':'Push';$('brake').textContent=state.sailboat?'Lower sail':'Brake';$('sailboat').textContent=state.sailboat?'Step ashore':'Sailboat';$('jump').textContent=state.skating?'Ollie':'Jump';status(state.ready?(aboard?(state.zeppelinStage===2?'Boarding the zeppelin':state.zeppelinStage===6?'Arriving':'Flying · '+speedLabel(state.flightSpeed)):(state.sailboat?'Sailing':state.skating?'Skating':'Exploring')+' · '+Math.round(state.speed*.036)+' km/h')+(state.showFps?' · '+Math.round(state.fps)+' FPS':''):'Loading the world…');}catch{}});
$('play').onclick=async()=>{if($('play').textContent==='Reconnect'){location.reload();return;}stream.play();playing=true;$('welcome').hidden=true;$('controls').hidden=false;try{await document.documentElement.requestFullscreen?.();}catch{}try{await navigator.wakeLock?.request('screen');}catch{}send();};
$('sound').onclick=()=>{muted=!muted;for(const el of document.querySelectorAll('video,audio'))el.muted=muted;stream.play();$('sound').textContent=muted?'Sound off':'Sound on';};
let resumeAfterScreen=false;
$('screen').onclick=async()=>{
 if(document.fullscreenEnabled){try{await document.documentElement.requestFullscreen();return;}catch{}}
 resumeAfterScreen=playing;playing=false;reset();$('screen-help').showModal();
};
function closeScreen(){playing=resumeAfterScreen;send();}
$('close-screen').onclick=()=>{$('screen-help').close();closeScreen();};
$('screen-help').addEventListener('cancel',closeScreen);
let toastTimer=null;
function toast(text){const el=$('toast');el.textContent=text;el.hidden=false;clearTimeout(toastTimer);toastTimer=setTimeout(()=>{el.hidden=true;},2600);}
let resumeAfterMap=false;
const map=createMap({send:m=>{if(connected)stream.emitUIInteraction({yorimichi:1,...m});},onTravel:z=>{toast(`Travelling to ${z.name}…`);closeMap();}});
$('map-button').onclick=()=>{resumeAfterMap=playing;playing=false;reset();map.open(connected);};
function closeMap(){playing=resumeAfterMap&&connected;send();}
$('close-map').onclick=()=>{$('map-dialog').close();closeMap();};
$('map-dialog').addEventListener('cancel',closeMap);
let resumeAfterSettings=false;
function requestSettings(){if(connected)stream.emitUIInteraction({yorimichi:1,action:'settings'});}
function changeSetting(key,value){
 if(!connected){$('settings-status').textContent='Disconnected — reconnect before changing settings';return;}
 $('settings-status').textContent='Saving…';stream.emitUIInteraction({yorimichi:1,action:'setSetting',key,value});
}
$('settings-button').onclick=()=>{
 resumeAfterSettings=playing;playing=false;reset();$('settings-dialog').showModal();
 $('settings-status').textContent=connected?'Loading settings…':'Connect to the game to load settings';requestSettings();
};
function closeSettings(){playing=resumeAfterSettings&&connected;send();}
$('close-settings').onclick=()=>{$('settings-dialog').close();closeSettings();};
$('settings-dialog').addEventListener('cancel',closeSettings);
$('help').onclick=()=>{reset();playing=false;$('instructions').showModal();};
$('close-help').onclick=()=>{$('instructions').close();playing=true;send();};
$('instructions').addEventListener('cancel',()=>{playing=true;send();});
const stick=$('stick');
function moveStick(e){const r=stick.getBoundingClientRect(),radius=r.width*.35;let x=(e.clientX-r.left-r.width/2)/radius,y=(e.clientY-r.top-r.height/2)/radius;const n=Math.max(1,Math.hypot(x,y));x/=n;y/=n;mx=Math.abs(x)<.08?0:x;my=Math.abs(y)<.08?0:-y;$('knob').style.transform=`translate(${x*radius}px,${y*radius}px)`;send();}
stick.addEventListener('pointerdown',e=>{e.preventDefault();if(stickPointer!==null)return;stickPointer=e.pointerId;stick.setPointerCapture(e.pointerId);moveStick(e);});
stick.addEventListener('pointermove',e=>{if(e.pointerId===stickPointer)moveStick(e);});
for(const ev of ['pointerup','pointercancel','lostpointercapture'])stick.addEventListener(ev,e=>{if(e.pointerId!==stickPointer)return;stickPointer=null;mx=my=0;$('knob').style.transform='';send();});
const look=$('look');
look.addEventListener('pointerdown',e=>{e.preventDefault();if(lookPointer!==null)return;lookPointer=e.pointerId;lookLast=[e.clientX,e.clientY];look.setPointerCapture(e.pointerId);});
look.addEventListener('pointermove',e=>{if(e.pointerId!==lookPointer||!lookLast)return;dx+=(e.clientX-lookLast[0])*.22;dy+=(e.clientY-lookLast[1])*.22;lookLast=[e.clientX,e.clientY];});
for(const ev of ['pointerup','pointercancel','lostpointercapture'])look.addEventListener(ev,e=>{if(e.pointerId===lookPointer){lookPointer=null;lookLast=null;send();}});
for(const button of document.querySelectorAll('[data-bit]')){
 button.addEventListener('pointerdown',e=>{e.preventDefault();if(Number(button.dataset.bit)===64)reset();button.setPointerCapture(e.pointerId);buttonPointers.set(e.pointerId,Number(button.dataset.bit));button.classList.add('held');updateButtons();});
 for(const ev of ['pointerup','pointercancel','lostpointercapture'])button.addEventListener(ev,e=>{buttonPointers.delete(e.pointerId);button.classList.remove('held');updateButtons();});
}
for(const button of document.querySelectorAll('[data-turn],[data-drive]')){
 button.addEventListener('pointerdown',e=>{e.preventDefault();button.setPointerCapture(e.pointerId);skatePointers.set(e.pointerId,{axis:button.dataset.turn!==undefined?'turn':'drive',value:Number(button.dataset.turn??button.dataset.drive)});button.classList.add('held');send();});
 for(const ev of ['pointerup','pointercancel','lostpointercapture'])button.addEventListener(ev,e=>{skatePointers.delete(e.pointerId);button.classList.remove('held');send();});
}
const supported=new Set(['KeyW','KeyA','KeyS','KeyD','Space','KeyF','KeyE','KeyK','KeyQ','ShiftLeft','ShiftRight','ControlLeft','ControlRight','KeyJ']);
addEventListener('keydown',e=>{if(!playing||!supported.has(e.code))return;e.preventDefault();keys.add(e.code);updateButtons();});
addEventListener('keyup',e=>{keys.delete(e.code);updateButtons();});
function suspend(){playing=false;reset();$('controls').hidden=true;$('welcome').hidden=false;$('play').textContent='Resume Yorimichi';}
addEventListener('blur',suspend);addEventListener('pagehide',suspend);document.addEventListener('visibilitychange',()=>{if(document.hidden)suspend();});
addEventListener('contextmenu',e=>e.preventDefault());
setInterval(()=>{if(!document.hidden)send();},50);
// Read-only telemetry helps diagnose the actual stream and input path.
window.yorimichi={state:lastState,history:[],stream,config,map:null};
