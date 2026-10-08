// The plain player: the stream with this device's own input (keyboard, mouse, gamepads) going straight to the game,
// as if it were plugged into the machine running it. For a handheld PC with a controller or a friend's computer.
import {connectStream} from './stream.js';
import {createPageLifecycle} from './page.js';
const $ = id => document.getElementById(id);
const {stream} = connectStream({videoParent: $('video'), nativeInput: true});
createPageLifecycle({stream, play: $('play'), welcome: $('welcome'), controls: $('bar'), status: [$('status')],
    sound: $('sound'), fullscreen: $('fullscreen'), readyText: 'Ready',
    lost: {webRtcDisconnected: 'Connection lost', webRtcFailed: 'Could not connect',
        subscribeFailed: 'Someone else is playing; try again when they stop'}});
window.atelierStream = {stream};
