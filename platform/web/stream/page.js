// What every stream page does around the stream: the status line, the Play/Reconnect button, wake lock and full screen,
// the sound toggle, dialogs that pause the input while they are open, a toast, and suspending when the page goes to the
// background. The page passes its elements and texts, and its input: reset() lets go of every held control and send()
// sends the input state once (a page whose input goes straight to the game, like the plain player, has neither).

/**
 * Wire a page to `stream` (from connectStream). Elements: `play`, `welcome` (shown until Play), `controls` (shown while
 * playing), `status` (a list; each shows the status line), and optionally `sound`, `fullscreen`, `toast` and `install`
 * (the Home Screen hint for iOS, which has no full screen; an installed page hides it and the full screen button).
 * `fullscreenHelp` ({dialog, close}) opens where full screen fails; `fullscreenOnPlay` asks for full screen on Play.
 * Texts: `playText` once the data channel opens (`readyText` on the status line then), `lost` and `retry` ({stream
 * event: status}: the connection ended and the input stops, or nothing was playing yet), `rejected` (the browser would
 * not start the video) and `suspendText` (Play's text once the page lost focus; without it the page keeps playing).
 * Returns {connected, playing, status(text), toast(text), pauseWhile(dialog, options)}.
 */
export function createPageLifecycle({stream, play, welcome, controls, status: lines = [], sound, fullscreen,
    fullscreenHelp, fullscreenOnPlay = false, toast: note, install, playText = 'Play', readyText, lost = {}, retry = {},
    rejected, suspendText, reset = () => {}, send = () => {}}) {
    let muted = true, toastTimer = null;
    const page = {
        connected: false, playing: false,
        status(text) { for (const el of lines) el.textContent = text; },
        toast(text) {
            note.textContent = text; note.hidden = false;
            clearTimeout(toastTimer); toastTimer = setTimeout(() => { note.hidden = true; }, 2600);
        },
        /**
         * Pause the input while `dialog` is open. open() (also `button`'s click) remembers whether the page was
         * playing, pauses, calls reset() and `show()` (default showModal()); closing with `close` or Escape resumes
         * (only while connected, unless `connected` is false) and calls send(). Returns {open, done}: done() resumes
         * for a dialog that closed itself.
         */
        pauseWhile(dialog, {button, close, show = () => dialog.showModal(), connected = true} = {}) {
            let resume = false;
            const open = () => { resume = page.playing; page.playing = false; reset(); show(); };
            const done = () => { page.playing = resume && (!connected || page.connected); send(); };
            if (button) button.onclick = open;
            if (close) close.onclick = () => { dialog.close(); done(); };
            dialog.addEventListener('cancel', done);
            return {open, done};
        },
    };
    const reconnect = () => { welcome.hidden = false; play.textContent = 'Reconnect'; };
    const drop = text => {
        page.connected = false; reset(); page.playing = false;
        document.querySelectorAll('dialog[open]').forEach(d => d.close());
        controls.hidden = true; play.disabled = false; reconnect(); page.status(text);
    };
    stream.addEventListener('webRtcConnected', () => page.status('Connected · starting video…'));
    stream.addEventListener('dataChannelOpen', () => {
        page.connected = true; play.disabled = false; play.textContent = playText;
        if (readyText) page.status(readyText);
        send();
    });
    stream.addEventListener('dataChannelClose', () => { page.connected = false; reset(); });
    for (const [event, text] of Object.entries(lost)) stream.addEventListener(event, () => drop(text));
    for (const [event, text] of Object.entries(retry)) stream.addEventListener(event, () => { page.status(text); reconnect(); });
    if (rejected) stream.addEventListener('playStreamRejected', () => { welcome.hidden = false; page.status(rejected); });
    play.onclick = async () => {
        if (play.textContent === 'Reconnect') { location.reload(); return; }
        stream.play(); page.playing = true; welcome.hidden = true; controls.hidden = false;
        if (fullscreenOnPlay) try { await document.documentElement.requestFullscreen?.(); } catch {}
        try { await navigator.wakeLock?.request('screen'); } catch {}
        send();
    };
    if (sound) sound.onclick = () => {
        muted = !muted;
        for (const el of document.querySelectorAll('video,audio')) el.muted = muted;
        stream.play(); sound.textContent = muted ? 'Sound off' : 'Sound on';
    };
    if (install) {
        const standalone = matchMedia('(display-mode: standalone)').matches || navigator.standalone;
        install.hidden = standalone || !/iPhone|iPad|iPod/.test(navigator.userAgent);
        if (fullscreen) fullscreen.hidden = !!standalone;
    }
    if (fullscreen) {
        const help = fullscreenHelp && page.pauseWhile(fullscreenHelp.dialog, {close: fullscreenHelp.close, connected: false});
        fullscreen.onclick = async () => {
            if (!help || document.fullscreenEnabled) {
                try { await document.documentElement.requestFullscreen(); return; } catch {}
            }
            help?.open();
        };
    }
    if (suspendText) {
        const suspend = () => {
            page.playing = false; reset(); controls.hidden = true; welcome.hidden = false; play.textContent = suspendText;
        };
        addEventListener('blur', suspend); addEventListener('pagehide', suspend);
        document.addEventListener('visibilitychange', () => { if (document.hidden) suspend(); });
    }
    return page;
}
