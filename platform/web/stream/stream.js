// A browser connected to a streamed game (Epic's Pixel Streaming frontend): video, the launcher's diagnostics log, and a
// JSON message channel keyed by the game's protocol name, {"<protocol>": 1, ...}. Pages build on it: the plain player
// (player.js, the device's own keyboard, mouse or controller) or a game's touch page (its own controls, sent as
// messages; see touch.js).
import {Config, PixelStreaming, Logger, LogLevel} from '@epicgames-ps/lib-pixelstreamingfrontend-ue5.8';

/** Posts one diagnostic event to the stream server (build/<game>/stream/diagnostics.jsonl). */
export function diagnostic(event, data = {}) {
    fetch('/diagnostics', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({event, ...data}), keepalive: true}).catch(() => {});
}

let traced = false;
function traceConnection() {
    if (traced) return;
    traced = true;
    addEventListener('error', e => diagnostic('script-error', {message: e.message}));
    addEventListener('unhandledrejection', e => diagnostic('promise-error', {message: String(e.reason?.message || e.reason)}));
    const NativePeer = window.RTCPeerConnection;
    window.RTCPeerConnection = class extends NativePeer {
        constructor(...args) {
            super(...args); diagnostic('peer-created');
            this.addEventListener('signalingstatechange', () => diagnostic('sdp-state', {state: this.signalingState}));
            this.addEventListener('icegatheringstatechange', () => diagnostic('ice-gathering', {state: this.iceGatheringState}));
            this.addEventListener('icecandidateerror', e => diagnostic('ice-error', {code: e.errorCode, message: e.errorText}));
            this.addEventListener('icecandidate', e => diagnostic('ice-candidate', {type: e.candidate?.type || 'complete'}));
            this.addEventListener('iceconnectionstatechange', () => diagnostic('ice-state', {state: this.iceConnectionState}));
            this.addEventListener('connectionstatechange', () => diagnostic('peer-state', {state: this.connectionState}));
        }
        async setRemoteDescription(...args) { try { return await super.setRemoteDescription(...args); } catch (e) { diagnostic('remote-description-error', {message: e.message}); throw e; } }
        async addIceCandidate(...args) { try { return await super.addIceCandidate(...args); } catch (e) { diagnostic('remote-candidate-error', {message: e.message}); throw e; } }
    };
    diagnostic('page', {agent: navigator.userAgent});
}

/**
 * Connect to the game. `protocol` names the game's message channel; `nativeInput` forwards this device's keyboard, mouse
 * and gamepads to the game as its own input (a controller on a handheld PC, a friend's laptop); a touch page leaves it
 * off and sends its controls as messages. Returns {stream, config, send(message), on(kind, fn)}: `on` receives the
 * game's messages by their "kind" ("status" for messages without one).
 */
export function connectStream({protocol, videoParent, nativeInput = false}) {
    Logger.InitLogging(LogLevel.Warning, false);
    traceConnection();
    const config = new Config({useUrlParams: true, initialSettings: {
        AutoConnect: true, AutoPlayVideo: true, ForceTURN: true, StartVideoMuted: true, WaitForStreamer: true,
        KeyboardInput: nativeInput, MouseInput: nativeInput, GamepadInput: nativeInput, TouchInput: false, HoveringMouse: false,
        AFKDetection: false, MatchViewportResolution: false, MaxReconnectAttempts: 20}});
    const stream = new PixelStreaming(config, {videoElementParent: videoParent});
    for (const event of ['webRtcFailed', 'webRtcDisconnected', 'playStreamError', 'playStreamRejected'])
        stream.addEventListener(event, e => diagnostic(event, {detail: e.data}));
    const handlers = new Map();
    if (protocol) stream.addResponseEventListener(protocol, text => {
        let message;
        try { message = JSON.parse(text); } catch { return; }
        if (message?.[protocol] !== 1) return;
        const handler = handlers.get(message.kind || 'status');
        if (handler) { try { handler(message); } catch (e) { diagnostic('handler-error', {kind: message.kind, message: e.message}); } }
    });
    return {
        stream, config,
        send(message) { if (protocol) stream.emitUIInteraction({[protocol]: 1, ...message}); },
        on(kind, fn) { handlers.set(kind, fn); },
    };
}
