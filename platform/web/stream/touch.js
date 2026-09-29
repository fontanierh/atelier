// Touch controls for a game streamed to a phone: a virtual stick, a drag-to-look pad, hold buttons and hold axes, plus
// the keyboard of a computer opening the same page. A game's touch page lays them out and sends its own control
// messages (usually {x, y, dx, dy, buttons, paused} every 50 ms: the game holds input only while messages keep coming).

/** A round stick: element with a knob inside. onMove(x, y) with y up, both in -1..1 and a small dead zone. */
export function createStick(element, knob, onMove, {radius = .35, deadZone = .08} = {}) {
    let pointer = null;
    const move = e => {
        const r = element.getBoundingClientRect(), reach = r.width * radius;
        let x = (e.clientX - r.left - r.width / 2) / reach, y = (e.clientY - r.top - r.height / 2) / reach;
        const n = Math.max(1, Math.hypot(x, y)); x /= n; y /= n;
        knob.style.transform = `translate(${x * reach}px,${y * reach}px)`;
        onMove(Math.abs(x) < deadZone ? 0 : x, Math.abs(y) < deadZone ? 0 : -y);
    };
    const release = () => { pointer = null; knob.style.transform = ''; onMove(0, 0); };
    element.addEventListener('pointerdown', e => { e.preventDefault(); if (pointer !== null) return; pointer = e.pointerId; element.setPointerCapture(e.pointerId); move(e); });
    element.addEventListener('pointermove', e => { if (e.pointerId === pointer) move(e); });
    for (const ev of ['pointerup', 'pointercancel', 'lostpointercapture']) element.addEventListener(ev, e => { if (e.pointerId === pointer) release(); });
    return {reset() { pointer = null; knob.style.transform = ''; }};
}

/** A drag area for the camera: onDelta(dx, dy) in scaled pixels while a finger moves; onEnd() when it lifts. */
export function createLookPad(element, onDelta, {scale = .22, onEnd = () => {}} = {}) {
    let pointer = null, last = null;
    element.addEventListener('pointerdown', e => { e.preventDefault(); if (pointer !== null) return; pointer = e.pointerId; last = [e.clientX, e.clientY]; element.setPointerCapture(e.pointerId); });
    element.addEventListener('pointermove', e => {
        if (e.pointerId !== pointer || !last) return;
        onDelta((e.clientX - last[0]) * scale, (e.clientY - last[1]) * scale); last = [e.clientX, e.clientY];
    });
    for (const ev of ['pointerup', 'pointercancel', 'lostpointercapture']) element.addEventListener(ev, e => { if (e.pointerId === pointer) { pointer = null; last = null; onEnd(); } });
    return {reset() { pointer = null; last = null; }};
}

/** Buttons with data-bit="<n>": held while a finger is on them (several at once). onChange(mask, pressedBit);
 *  beforePress(bit) runs before a press registers (a button that resets the other controls). */
export function createHoldButtons(buttons, onChange, {beforePress = () => {}} = {}) {
    const held = new Map();
    const mask = () => { let m = 0; for (const b of held.values()) m |= b; return m; };
    for (const button of buttons) {
        const bit = Number(button.dataset.bit);
        button.addEventListener('pointerdown', e => { e.preventDefault(); beforePress(bit); button.setPointerCapture(e.pointerId); held.set(e.pointerId, bit); button.classList.add('held'); onChange(mask(), bit); });
        for (const ev of ['pointerup', 'pointercancel', 'lostpointercapture'])
            button.addEventListener(ev, e => { held.delete(e.pointerId); button.classList.remove('held'); onChange(mask(), 0); });
    }
    return {mask, reset() { held.clear(); for (const b of buttons) b.classList.remove('held'); }};
}

/** Buttons with data-axis="<name>" data-value="<v>": while held, the axis reads the sum of its held values. */
export function createHoldAxes(buttons, onChange) {
    const held = new Map();
    const value = axis => [...held.values()].filter(h => h.axis === axis).reduce((sum, h) => sum + h.value, 0);
    const any = (axis, test) => [...held.values()].some(h => h.axis === axis && test(h.value));
    for (const button of buttons) {
        button.addEventListener('pointerdown', e => {
            e.preventDefault(); button.setPointerCapture(e.pointerId);
            held.set(e.pointerId, {axis: button.dataset.axis, value: Number(button.dataset.value)}); button.classList.add('held'); onChange();
        });
        for (const ev of ['pointerup', 'pointercancel', 'lostpointercapture'])
            button.addEventListener(ev, e => { held.delete(e.pointerId); button.classList.remove('held'); onChange(); });
    }
    return {value, any, reset() { held.clear(); for (const b of buttons) b.classList.remove('held'); }};
}

/** Keys of a computer's keyboard (KeyboardEvent.code) while isActive(): keys() is the held set, bits() maps them. */
export function createKeyboard(bitsByCode, isActive, onChange) {
    const held = new Set();
    addEventListener('keydown', e => {
        if (!isActive() || !(e.code in bitsByCode || /^Key[WASD]$/.test(e.code))) return;
        e.preventDefault(); held.add(e.code); onChange();
    });
    addEventListener('keyup', e => { held.delete(e.code); onChange(); });
    return {
        has: code => held.has(code),
        bits() { let m = 0; for (const k of held) m |= bitsByCode[k] || 0; return m; },
        reset() { held.clear(); },
    };
}

/** Calls fn every `ms` while the page is visible: the game releases the controls if these messages stop. */
export function keepSending(fn, ms = 50) {
    return setInterval(() => { if (!document.hidden) fn(); }, ms);
}
