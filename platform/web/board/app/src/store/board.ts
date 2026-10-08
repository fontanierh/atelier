// The board's live state: one poll of /api/state every 3 seconds, merged into the messages already on the page.
//
// It never blanks: the last good snapshot stays on screen through any failure, and a failure only sets `failed`, which
// the header shows as Reconnecting. Every request has a deadline; a newer request supersedes an older one; a request
// frozen by iOS in the background is abandoned once it is 15 s old by the wall clock, and coming back to the app
// always starts over. A changed conversation or filter swaps the messages only once its answer arrives.
import {api, message, offline, setCsrf, type StateQuery} from '../api/client';
import type {Message, State} from '../api/schema';
import {Store} from './store';
import {filterKey, ui} from './ui';

export interface Board {
  state: State | null;
  records: ReadonlyMap<number, Message>;
  /** Which conversation and filters `records` hold (ui.filterKey). */
  recordsKey: string;
  historyComplete: boolean;
  failed: boolean;
  error: string;
  /** Bumped when older history was added above, so the feed can keep what you are reading where it is. */
  prepended: number;
  loadingOlder: boolean;
  /** Operator tasks dismissed here, which a snapshot already in flight must not bring back. */
  dismissed: ReadonlySet<number>;
}

export const board = new Store<Board>({
  state: null, records: new Map(), recordsKey: '', historyComplete: false, failed: false, error: '', prepended: 0,
  loadingOlder: false, dismissed: new Set(),
});

function query(before: number): StateQuery {
  const u = ui.get(), q: StateQuery = {log: Math.min(u.logShown, 5000)};
  if (u.agent) q[u.mode === 'dm' ? 'dm' : 'agent'] = u.agent;
  if (u.search.trim()) q.q = u.search.trim();
  if (u.topic) q.topic = u.topic;
  if (before) q.before = before;
  return q;
}

function valid(result: State): boolean {
  return Boolean(result) && typeof result.time === 'number' && Array.isArray(result.messages)
    && Array.isArray(result.agents) && Array.isArray(result.tasks) && typeof result.csrf === 'string';
}

let number = 0, current: AbortController | null = null, started = 0;
const busy = () => current !== null;

/** Fetch the board. `reset` supersedes whatever is in flight; `before` asks for older history. */
export async function load({reset = false, before = 0} = {}): Promise<void> {
  if (busy() && !reset) return;
  current?.abort();
  const mine = ++number, controller = new AbortController(), key = filterKey(ui.get());
  current = controller; started = Date.now();
  if (before) board.set({loadingOlder: true});
  try {
    const result = await api.state(query(before), controller.signal);
    if (mine !== number) return;
    if (!valid(result)) throw new Error('The board sent an answer this page does not understand.');
    setCsrf(result.csrf);
    const b = board.get(), fresh = b.recordsKey !== key;
    // A different conversation starts from its own answer; the same one only grows.
    const records = new Map(fresh ? [] : b.records);
    for (const m of result.messages) records.set(m.id, m);
    board.set({
      state: result, records, recordsKey: key, failed: false, error: '',
      historyComplete: before || fresh || !b.records.size ? !result.has_more : b.historyComplete,
      prepended: before ? b.prepended + 1 : b.prepended,
    });
  } catch (error) {
    if (mine !== number) return;
    board.set({
      failed: true,
      error: offline(error) ? 'The board isn’t reachable right now. Your draft is saved. Reconnecting…' : message(error),
    });
  } finally {
    if (mine === number) { current = null; board.set({loadingOlder: false}); }
  }
}

/** The conversation or a filter changed: fetch it now, whatever is in flight. */
export const refresh = () => load({reset: true});

export function loadOlder(): void {
  const b = board.get();
  if (busy() || !b.records.size || b.historyComplete) return;
  load({before: Math.min(...b.records.keys())});
}

/** Starts over after the app was frozen or offline. */
export function resume(): void {
  if (!document.hidden) load({reset: true});
}

let timer = 0;
export function startPolling(): void {
  if (timer) return;
  load();
  timer = window.setInterval(() => {
    if (document.hidden) return;
    if (busy() && Date.now() - started > 15_000) load({reset: true});
    else load();
  }, 3000);
}

export function dismissLocally(id: number): void {
  board.set((b) => ({
    dismissed: new Set([...b.dismissed, id]),
    state: b.state && {...b.state, tasks: b.state.tasks.filter((t) => t.id !== id)},
  }));
}

/** Live agents (not retired), and helpers the views share. */
export const liveAgents = (state: State | null) => (state ? state.agents.filter((a) => !a.stop) : []);
