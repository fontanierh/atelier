// Reports the messages a view has on screen as read (see store/seen.ts). A message counts once at least half of it,
// or a good part of the screen if it is taller than that, has been in view of its scroller for a moment, so
// scrolling past something does not read it.
import {useEffect, useLayoutEffect, useRef, type RefObject} from 'react';
import {seen} from '../store/seen';

const DWELL = 700;

export function useSeen(root: RefObject<HTMLElement | null>, active: () => boolean, version: unknown): void {
  const observer = useRef<IntersectionObserver | null>(null), visible = useRef(new Map<HTMLElement, number>());
  const live = useRef(active);
  live.current = active;
  useEffect(() => {
    const box = root.current;
    if (!box || typeof IntersectionObserver !== 'function') return;
    let check = 0;
    const report = () => {
      if (!live.current() || !visible.current.size) return;
      const ids: number[] = [], now = performance.now();
      for (const [n, since] of visible.current) {
        if (now - since < DWELL) continue;
        for (const id of (n.dataset.ids || '').split(' ')) if (+id > 0) ids.push(+id);
      }
      if (ids.length) seen(ids);
    };
    observer.current = new IntersectionObserver((entries) => {
      for (const e of entries) {
        const n = e.target as HTMLElement, room = e.rootBounds?.height ?? innerHeight;
        if (e.isIntersecting && (e.intersectionRatio >= .5 || e.intersectionRect.height >= room * .4)) {
          if (!visible.current.has(n)) visible.current.set(n, performance.now());
        } else visible.current.delete(n);
      }
      clearTimeout(check);
      check = window.setTimeout(report, DWELL + 50);
    }, {root: box, threshold: [0, .25, .5, .75, 1]});
    box.querySelectorAll<HTMLElement>('[data-ids]').forEach((n) => observer.current!.observe(n));
    // Coming back to the page, or to this view, reads what is already on screen.
    const timer = setInterval(report, 2000);
    document.addEventListener('visibilitychange', report);
    return () => {
      observer.current?.disconnect(); observer.current = null; visible.current.clear();
      clearInterval(timer); clearTimeout(check); document.removeEventListener('visibilitychange', report);
    };
  }, [root]);
  useLayoutEffect(() => {
    const box = root.current, io = observer.current;
    if (!box || !io) return;
    for (const n of [...visible.current.keys()]) if (!n.isConnected) visible.current.delete(n);
    box.querySelectorAll<HTMLElement>('[data-ids]').forEach((n) => io.observe(n));
  }, [root, version]);
}
