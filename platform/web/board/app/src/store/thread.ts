// The open thread: the original and every reply. Opening another thread supersedes the one in flight.
import {api, HttpError, message, offline} from '../api/client';
import type {Thread} from '../api/schema';
import {Store} from './store';

export interface OpenThread {
  id: number;
  /** Where it was opened from: Threads or Activity, which closing returns to; '' for the feed. */
  origin: '' | 'threads' | 'activity';
  data: Thread | null;
  status: string;
  /** Bumped each time it is opened, so views can tell a new opening from a refresh. */
  opened: number;
  /** Put the cursor in the composer once it has loaded. */
  focus: boolean;
  /** The composer's recipient before the thread took it over. */
  savedRecipient: string;
}

export const thread = new Store<{open: OpenThread | null}>({open: null});

let controller: AbortController | null = null, started = 0, openings = 0;

export function setThread(id: number, origin: OpenThread['origin'], focus: boolean, savedRecipient: string): void {
  openings += 1;
  thread.set({open: {id, origin, data: null, status: 'Loading…', opened: openings, focus, savedRecipient}});
  loadThread(true);
}

export function clearThread(): void {
  controller?.abort();
  controller = null;
  thread.set({open: null});
}

export async function loadThread(restart = false): Promise<void> {
  const open = thread.get().open;
  if (!open) return;
  if (controller && !restart && Date.now() - started < 15_000) return;
  controller?.abort();
  const mine = new AbortController();
  controller = mine; started = Date.now();
  try {
    const data = await api.thread(open.id, mine.signal);
    if (controller !== mine || thread.get().open?.opened !== open.opened) return;
    if (!Array.isArray(data.root) || !data.root.length || !Array.isArray(data.replies)) {
      throw new Error('This conversation could not be loaded.');
    }
    thread.set({open: {...thread.get().open!, data, status: ''}});
  } catch (error) {
    if (controller !== mine || thread.get().open?.opened !== open.opened) return;
    const status = error instanceof HttpError && error.status === 404 ? message(error)
      : offline(error) ? 'Reconnecting…' : message(error, 'This conversation could not be loaded.');
    thread.set({open: {...thread.get().open!, status}});
  } finally {
    if (controller === mine) controller = null;
  }
}

/** The thread changed on the server (starred, read): keep it in step without a reload. */
export function patchThread(patch: Partial<Thread>): void {
  const open = thread.get().open;
  if (open?.data) thread.set({open: {...open, data: {...open.data, ...patch}}});
}
