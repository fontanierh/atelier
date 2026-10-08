// The board's media queries, read live and as React hooks.
import {useSyncExternalStore} from 'react';

const query = (text: string) => (typeof matchMedia === 'function' ? matchMedia(text) : null);
export const desktop = query('(min-width:1100px)');
export const touch = query('(hover:none)');
export const motion = query('(prefers-reduced-motion: reduce)');
export const snapScreen = query('(max-width: 699px)');
export const standalone = (query('(display-mode: standalone)')?.matches ?? false)
  || (navigator as Navigator & {standalone?: boolean}).standalone === true;

export const isDesktop = () => desktop?.matches ?? false;
export const isTouch = () => touch?.matches ?? false;
export const reducedMotion = () => motion?.matches ?? false;

export function useMedia(list: MediaQueryList | null): boolean {
  return useSyncExternalStore(
    (change) => { list?.addEventListener('change', change); return () => list?.removeEventListener('change', change); },
    () => list?.matches ?? false,
  );
}
