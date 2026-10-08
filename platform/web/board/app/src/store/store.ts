// A small external store: plain TypeScript, no React. Views subscribe with useStore; anything else (a native port, a
// test) can drive the same object. A snapshot is replaced, never mutated, so React sees every change.
import {useSyncExternalStore} from 'react';

export class Store<T extends object> {
  private listeners = new Set<() => void>();
  constructor(private value: T) {}

  get = (): T => this.value;

  set(patch: Partial<T> | ((current: T) => Partial<T>)): void {
    const next = typeof patch === 'function' ? patch(this.value) : patch;
    let changed = false;
    for (const key of Object.keys(next) as (keyof T)[]) if (!Object.is(next[key], this.value[key])) changed = true;
    if (!changed) return;
    this.value = {...this.value, ...next};
    for (const listener of [...this.listeners]) {
      try { listener(); } catch (error) { console.error(error); }
    }
  }

  subscribe = (listener: () => void): (() => void) => {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  };
}

/** A field (or anything else stable) of a store's snapshot; the view re-renders only when it changes. */
export function useStore<T extends object, S>(store: Store<T>, select: (value: T) => S): S {
  return useSyncExternalStore(store.subscribe, () => select(store.get()));
}
