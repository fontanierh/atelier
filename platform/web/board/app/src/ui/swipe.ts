// Swipe actions, as in Mail: drag a row sideways and an action shows behind it; let go past the line and it happens.
// One gesture owns a surface at a time: a row takes only the directions it has an action for, so a rightward drag on
// a message is still the screen's swipe back. A mostly vertical drag stays a scroll, and a gesture that is cancelled
// (a second finger, the system taking over, the page hiding) does nothing.
import {useEffect, useRef, type RefObject} from 'react';
import {reducedMotion} from '../lib/media';
import type {IconName} from './Icon';

export interface SwipeAction { icon: IconName; label: string; act: () => void; tone?: string }
export interface SwipeActions { left?: SwipeAction | undefined; right?: SwipeAction | undefined }

const ARM = 72, MAX = 116;
const SKIP = 'textarea, input, select, pre, table, video, audio, .attachments, .mention, summary';

const ICONS: Partial<Record<IconName, string>> = {
  reply: '<path d="M9 14 4 9l5-5"/><path d="M4 9h10a6 6 0 0 1 6 6v5"/>',
  check: '<path d="m5 12 4 4L19 6"/>',
  star: '<path d="m12 3.5 2.6 5.3 5.9.9-4.3 4.1 1 5.8-5.2-2.7-5.2 2.7 1-5.8-4.3-4.1 5.9-.9L12 3.5Z"/>',
};

function hint(row: HTMLElement, side: 'left' | 'right', action: SwipeAction): HTMLElement {
  const host = row.parentElement!, el = document.createElement('span');
  el.className = `swipe-hint ${side}${action.tone ? ` ${action.tone}` : ''}`;
  el.setAttribute('aria-hidden', 'true');
  el.innerHTML = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" `
    + `stroke-linejoin="round">${ICONS[action.icon] || ''}</svg><b></b>`;
  el.querySelector('b')!.textContent = action.label;
  host.classList.add('swipe-host');
  el.style.top = `${row.offsetTop}px`; el.style.height = `${row.offsetHeight}px`;
  el.style.left = `${row.offsetLeft}px`; el.style.width = `${row.offsetWidth}px`;
  host.prepend(el);   // first, so the row (positioned too) paints over it
  return el;
}

export function useSwipe(ref: RefObject<HTMLElement | null>, actions: SwipeActions): void {
  const latest = useRef(actions);
  latest.current = actions;
  useEffect(() => {
    const row = ref.current;
    if (!row) return;
    let g: {x: number; y: number; axis: 'x' | 'y' | null; dx: number; side: 'left' | 'right' | null; hint: HTMLElement | null;
      armed: boolean} | null = null;
    const reset = (animate: boolean) => {
      const s = g;
      g = null;
      if (!s) return;
      row.style.transition = animate && !reducedMotion() ? 'transform .32s cubic-bezier(.2, .9, .25, 1)' : '';
      row.style.transform = '';
      const el = s.hint;
      if (el) { el.classList.add('gone'); setTimeout(() => el.remove(), 320); }
      setTimeout(() => { row.style.transition = ''; }, 340);
    };
    const start = (event: TouchEvent) => {
      if (event.touches.length !== 1 || (event.target as Element).closest(SKIP)) { reset(false); return; }
      const t = event.touches[0]!;
      g = {x: t.clientX, y: t.clientY, axis: null, dx: 0, side: null, hint: null, armed: false};
    };
    const move = (event: TouchEvent) => {
      if (!g) return;
      if (event.touches.length !== 1) { reset(true); return; }
      const t = event.touches[0]!, dx = t.clientX - g.x, dy = t.clientY - g.y;
      if (!g.axis) {
        if (Math.hypot(dx, dy) < 10) return;
        const side = dx < 0 ? 'left' : 'right';
        if (Math.abs(dx) <= Math.abs(dy) * 1.3 || !latest.current[side]) { g = null; return; }
        g.axis = 'x'; g.side = side;
        g.hint = hint(row, side, latest.current[side]!);
        row.style.transition = 'none';
      }
      event.preventDefault();
      event.stopPropagation();
      const sign = g.side === 'left' ? -1 : 1;
      let travel = Math.max(0, dx * sign);
      if (travel > MAX) travel = MAX + (travel - MAX) / 3;   // resists past the action, like a native list
      g.dx = travel;
      row.style.transform = `translateX(${travel * sign}px)`;
      const armed = travel >= ARM;
      if (armed !== g.armed) { g.armed = armed; g.hint?.classList.toggle('armed', armed); if (armed) navigator.vibrate?.(8); }
      g.hint?.style.setProperty('--p', String(Math.min(1, travel / ARM)));
    };
    const finish = (event: TouchEvent) => {
      if (!g?.axis) { g = null; return; }
      const action = event.type === 'touchend' && g.armed && g.side ? latest.current[g.side] : undefined;
      reset(true);
      action?.act();
    };
    const hide = () => reset(false);
    row.addEventListener('touchstart', start, {passive: true});
    row.addEventListener('touchmove', move, {passive: false});
    row.addEventListener('touchend', finish);
    row.addEventListener('touchcancel', finish);
    document.addEventListener('visibilitychange', hide);
    return () => {
      reset(false);
      row.removeEventListener('touchstart', start); row.removeEventListener('touchmove', move);
      row.removeEventListener('touchend', finish); row.removeEventListener('touchcancel', finish);
      document.removeEventListener('visibilitychange', hide);
    };
  }, [ref]);
}
