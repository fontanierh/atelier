// The plain player: the stream with this device's own input (keyboard, mouse, gamepads) going straight to the game,
// as if it were plugged into the machine running it. For a handheld PC with a controller or a friend's computer.
import {connectStream} from './stream.js';
const $ = id => document.getElementById(id);
const {stream} = connectStream({videoParent: $('video'), nativeInput: true});
let muted = true;
const status = text => { $('status').textContent = text; };
stream.addEventListener('webRtcConnected', () => status('Connected · starting video…'));
stream.addEventListener('dataChannelOpen', () => { $('play').disabled = false; $('play').textContent = 'Play'; status('Ready'); });
const lost = text => () => { $('welcome').hidden = false; $('bar').hidden = true; $('play').disabled = false; $('play').textContent = 'Reconnect'; status(text); };
stream.addEventListener('webRtcDisconnected', lost('Connection lost'));
stream.addEventListener('webRtcFailed', lost('Could not connect'));
stream.addEventListener('subscribeFailed', lost('Someone else is playing; try again when they stop'));
$('play').onclick = async () => {
    if ($('play').textContent === 'Reconnect') { location.reload(); return; }
    stream.play(); $('welcome').hidden = true; $('bar').hidden = false;
    try { await navigator.wakeLock?.request('screen'); } catch {}
};
$('fullscreen').onclick = async () => { try { await document.documentElement.requestFullscreen(); } catch {} };
$('sound').onclick = () => {
    muted = !muted;
    for (const el of document.querySelectorAll('video,audio')) el.muted = muted;
    stream.play(); $('sound').textContent = muted ? 'Sound off' : 'Sound on';
};
window.atelierStream = {stream};
