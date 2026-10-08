// Threads and Activity, as in Slack. Each view loads on its own with the board's rules: a deadline per request, the
// last good list kept through failures, and a request older than 15 s abandoned (iOS can freeze one mid-flight, which
// used to hold the view on "Loading" until a reload).
import {api, message, offline} from '../api/client';
import type {Activity, Threads} from '../api/schema';
import {Store} from './store';

export type InboxView = 'threads' | 'activity';

export interface Inbox {
  threads: Threads | null;
  /** Which list `threads` holds: all, or starred only. */
  threadsStarred: boolean;
  activity: Activity | null;
  activityKey: string;
  threadLimit: number;
  activityLimit: number;
  starredOnly: boolean;
  kind: string;
  unreadOnly: boolean;
  error: Record<InboxView, string>;
}

export const inbox = new Store<Inbox>({
  threads: null, threadsStarred: false, activity: null, activityKey: '', threadLimit: 30, activityLimit: 60,
  starredOnly: false, kind: '', unreadOnly: false, error: {threads: '', activity: ''},
});

export const activityKey = (i: Inbox) => `${i.kind}:${i.unreadOnly}`;

const loading: Record<InboxView, {abort: AbortController; started: number} | null> = {threads: null, activity: null};

export async function loadInbox(view: InboxView, restart = false): Promise<void> {
  const busy = loading[view];
  if (busy && !restart && Date.now() - busy.started < 15_000) return;
  busy?.abort.abort();
  const mine = {abort: new AbortController(), started: Date.now()};
  loading[view] = mine;
  const i = inbox.get();
  try {
    if (view === 'threads') {
      const starred = i.starredOnly;
      const result = await api.threads({limit: i.threadLimit, starred}, mine.abort.signal);
      if (loading[view] !== mine) return;
      if (!Array.isArray(result.threads)) throw new Error('The board sent an answer this page does not understand.');
      inbox.set((now) => ({threads: result, threadsStarred: starred, error: {...now.error, threads: ''}}));
    } else {
      const key = activityKey(i);
      const result = await api.activity({limit: i.activityLimit, kind: i.kind, unread: i.unreadOnly}, mine.abort.signal);
      if (loading[view] !== mine) return;
      if (!Array.isArray(result.items)) throw new Error('The board sent an answer this page does not understand.');
      inbox.set((now) => ({activity: result, activityKey: key, error: {...now.error, activity: ''}}));
    }
  } catch (error) {
    if (loading[view] !== mine) return;
    const text = offline(error) ? 'Reconnecting…' : message(error);
    inbox.set((now) => ({error: {...now.error, [view]: text}}));
  } finally {
    if (loading[view] === mine) loading[view] = null;
  }
}

export const inboxBusy = (view: InboxView) => loading[view] !== null;
