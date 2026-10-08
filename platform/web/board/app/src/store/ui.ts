// What the person is looking at: the view, the conversation, filters, and what they opened or folded. Kept apart from
// the data so a refresh never moves them.
import {Store} from './store';
import type {View} from '../lib/format';

export type Mode = 'dm' | 'all';

export interface Ui {
  view: View;
  /** The agent whose conversation is open; '' is everyone. */
  agent: string;
  mode: Mode;
  searchOpen: boolean;
  search: string;
  topic: string;
  showSystem: boolean;
  logShown: number;
  /** Long messages opened with Read more, and receipts opened, by group key. */
  expanded: ReadonlySet<string>;
  deliveryOpen: ReadonlySet<string>;
  readerOpen: boolean;
}

const SYSTEM = 'atelier.board.system-notices';
let shown = false;
try { shown = localStorage.getItem(SYSTEM) === 'shown'; } catch { /* private mode */ }

export const ui = new Store<Ui>({
  view: 'messages', agent: '', mode: 'dm', searchOpen: false, search: '', topic: '', showSystem: shown, logShown: 12,
  expanded: new Set(), deliveryOpen: new Set(), readerOpen: false,
});

export function setShowSystem(on: boolean): void {
  try { localStorage.setItem(SYSTEM, on ? 'shown' : 'hidden'); } catch { /* private mode */ }
  ui.set({showSystem: on});
}

export function toggle(field: 'expanded' | 'deliveryOpen', key: string, open?: boolean): void {
  ui.set((u) => {
    const next = new Set(u[field]);
    if (open ?? !next.has(key)) next.add(key); else next.delete(key);
    return {[field]: next};
  });
}

/** The feed's query: who, how, and what it searches for. */
export const filterKey = (u: Ui) => JSON.stringify([u.agent, u.agent ? u.mode : '', u.search.trim(), u.topic]);
export const filtered = (u: Ui) => Boolean(u.agent || u.search.trim() || u.topic);
