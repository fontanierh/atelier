// Yorimichi's touch page for the phone stream: the stick, look pad and buttons (platform/web/stream/touch.js), the map,
// settings and stamina panels, and the status line, over the platform's stream connection. The other page, /play/, is
// the platform's plain player for a device with its own keyboard, mouse or controller.
import {connectStream} from '../../../platform/web/stream/stream.js';
import {createStick, createLookPad, createHoldButtons, createHoldAxes, createKeyboard, keepSending} from '../../../platform/web/stream/touch.js';
import {updateStamina} from './stamina.js';
import {renderSettings} from './settings.js';
import {createMap} from './map.js';
const $=id=>document.getElementById(id);
const {stream,config,send:message,on}=connectStream({protocol:'yorimichi',videoParent:$('video')});
const standalone=matchMedia('(display-mode: standalone)').matches||navigator.standalone;
$('install-hint').hidden=standalone||!/iPhone|iPad|iPod/.test(navigator.userAgent);
$('screen').hidden=!!standalone;
let connected=false,playing=false,muted=true,dx=0,dy=0,mx=0,my=0,lastState=null;
function status(s){$('status').textContent=s;$('welcome-status').textContent=s;}
const clamp=v=>Math.max(-1,Math.min(1,v));
// Buttons: 1 jump, 2 dash, 4 use, 8 sailboat, 16 wave, 32 walk, 64 back to spawn, 128 sprint, 256 roll.
const keyboard=createKeyboard({Space:1,KeyF:2,KeyE:4,KeyK:8,KeyQ:16,KeyJ:32,ShiftLeft:128,ShiftRight:128,ControlLeft:256,ControlRight:256},()=>playing,()=>send());
const holds=createHoldButtons(document.querySelectorAll('[data-bit]'),()=>send(),{beforePress:bit=>{if(bit===64)reset();}});
// Sailing: hold buttons steer (turn) and raise or lower the sail (drive) instead of the stick.
const axes=createHoldAxes(document.querySelectorAll('[data-axis]'),()=>send());
const stick=createStick($('stick'),$('knob'),(x,y)=>{mx=x;my=y;send();});
const look=createLookPad($('look'),(ddx,ddy)=>{dx+=ddx;dy+=ddy;},{onEnd:()=>send()});
function send(){
 if(!connected)return;
 const kx=(keyboard.has('KeyD')?1:0)-(keyboard.has('KeyA')?1:0),ky=(keyboard.has('KeyW')?1:0)-(keyboard.has('KeyS')?1:0);
 const riding=!!lastState?.sailboat;
 const braking=keyboard.has('KeyS')||axes.any('drive',v=>v<0);
 const pushing=keyboard.has('KeyW')||axes.any('drive',v=>v>0);
 const x=riding?axes.value('turn')+kx:mx+kx,y=riding?(braking?-1:pushing?1:0):my+ky;
 message({paused:!playing,x:playing?clamp(x):0,y:playing?clamp(y):(riding?-1:0),dx:playing?dx:0,dy:playing?dy:0,buttons:playing?holds.mask()|keyboard.bits():0});dx=dy=0;
}
function reset(){mx=my=dx=dy=0;keyboard.reset();holds.reset();axes.reset();stick.reset();look.reset();document.querySelectorAll('.held').forEach(b=>b.classList.remove('held'));send();}
// The ride speed the passenger picked, shown on the status line and set by the two flight buttons.
const speedLabel=value=>(value&&value!==1?String(Number(value.toFixed(2))):'1')+'×';
for(const [id,delta] of [['slower',-1],['faster',1]]){
 const button=$(id);
 button.addEventListener('pointerdown',event=>{event.preventDefault();event.stopPropagation();if(connected)message({action:'flightSpeed',delta});});
 button.addEventListener('click',event=>event.preventDefault());
}
function lost(text){connected=false;reset();playing=false;document.querySelectorAll('dialog[open]').forEach(d=>d.close());$('controls').hidden=true;$('welcome').hidden=false;$('play').textContent='Reconnect';status(text);}
stream.addEventListener('webRtcConnected',()=>status('Connected · starting video…'));
stream.addEventListener('dataChannelOpen',()=>{connected=true;$('play').textContent='Play Yorimichi';send();});
stream.addEventListener('dataChannelClose',()=>{connected=false;reset();});
stream.addEventListener('webRtcDisconnected',()=>lost('Connection lost · tap Reconnect'));
stream.addEventListener('webRtcFailed',()=>lost('Could not connect · keep Tailscale on and tap Reconnect'));
stream.addEventListener('subscribeFailed',()=>{status('Game is in use · close other play tabs, then reconnect');$('welcome').hidden=false;$('play').textContent='Reconnect';});
stream.addEventListener('playStreamRejected',()=>{$('welcome').hidden=false;status('Tap Play to start the video');});
on('hint',state=>toast(state.text));
on('settings',state=>{window.yorimichi.settings=state.values;renderSettings(state.values,changeSetting);$('settings-status').textContent='Saved in the game';});
on('map',state=>{map.receive(state);window.yorimichi.map=state;});
on('teleport',state=>{const zone=map.data?.zones.find(z=>z.key===state.zone);toast(state.ok?`Arrived: ${zone?.name||state.zone}`:'That place is not on the map');});
on('status',state=>{
 const hint=state.rampHint;
 $('ramp-hint').textContent=hint||'';$('ramp-hint').hidden=!hint;
 $('use').textContent=hint?.startsWith('Flying to')?'Skip flight':hint?.startsWith('Use to board')?'Fly':hint?.startsWith('Use to call')?'Call ship':'Use';
 updateStamina(state);map.update(state);
 const aboard=state.zeppelinStage>=2&&state.zeppelinStage<=6;
 $('controls').classList.toggle('aboard',aboard);if(aboard)$('stamina').hidden=true;
 $('slower').hidden=!aboard;$('faster').hidden=!aboard;$('slower').textContent='Slower';$('faster').textContent='Faster · '+speedLabel(state.flightSpeed);
 window.yorimichi.flightSpeed=state.flightSpeed;
 const changedMode=!!lastState?.sailboat!==!!state.sailboat;
 lastState=state;
 if(changedMode){reset();const riding=!!state.sailboat;$('controls').classList.toggle('skating',!!riding);$('controls').classList.toggle('sailing',!!state.sailboat);$('stick').hidden=!!riding;$('skate-steering').hidden=!riding;}
 window.yorimichi.state=state;window.yorimichi.history.push({...state,time:Date.now()});if(window.yorimichi.history.length>200)window.yorimichi.history.shift();
 $('push').textContent=state.sailboat?'Raise sail':'Push';$('brake').textContent=state.sailboat?'Lower sail':'Brake';
 $('sailboat').textContent=state.sailboat?'Step ashore':'Sailboat';
 status(state.ready?(aboard?(state.zeppelinStage===2?'Boarding the zeppelin':state.zeppelinStage===6?'Arriving':'Flying · '+speedLabel(state.flightSpeed)):(state.sailboat?'Sailing':'Exploring')+' · '+Math.round(state.speed*.036)+' km/h')+(state.showFps?' · '+Math.round(state.fps)+' FPS':''):'Loading the world…');
});
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
const map=createMap({send:m=>{if(connected)message(m);},onTravel:z=>{toast(`Travelling to ${z.name}…`);closeMap();}});
$('map-button').onclick=()=>{resumeAfterMap=playing;playing=false;reset();map.open(connected);};
function closeMap(){playing=resumeAfterMap&&connected;send();}
$('close-map').onclick=()=>{$('map-dialog').close();closeMap();};
$('map-dialog').addEventListener('cancel',closeMap);
let resumeAfterSettings=false;
function requestSettings(){if(connected)message({action:'settings'});}
function changeSetting(key,value){
 if(!connected){$('settings-status').textContent='Disconnected — reconnect before changing settings';return;}
 $('settings-status').textContent='Saving…';message({action:'setSetting',key,value});
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
function suspend(){playing=false;reset();$('controls').hidden=true;$('welcome').hidden=false;$('play').textContent='Resume Yorimichi';}
addEventListener('blur',suspend);addEventListener('pagehide',suspend);document.addEventListener('visibilitychange',()=>{if(document.hidden)suspend();});
addEventListener('contextmenu',e=>e.preventDefault());
keepSending(send);
// Read-only telemetry helps diagnose the actual stream and input path (the smoke tests read it).
window.yorimichi={state:lastState,history:[],stream,config,map:null};
