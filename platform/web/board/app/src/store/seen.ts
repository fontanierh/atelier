// One read state, on the board: a message counts as read once it has been on screen, wherever that was (the feed, a
// direct conversation, a thread, the Threads view), on any device. Views report what they show; this batches it to
// /api/seen, which moves each thread's read mark up to the newest message seen in it. Nothing is sent while the page
// is hidden, so a phone in a pocket never reads anything.
import {api} from '../api/client';
import {load} from './board';
import {inbox, loadInbox} from './inbox';

const queued = new Set<number>(), sent = new Set<number>();
let timer = 0, flushing = false;

export function seen(ids: Iterable<number>): void {
  if (document.hidden) return;
  for (const id of ids) if (id > 0 && !sent.has(id)) queued.add(id);
  if (queued.size && !timer) timer = window.setTimeout(flush, 600);
}

async function flush(): Promise<void> {
  timer = 0;
  if (flushing || document.hidden || !queued.size) return;
  const ids = [...queued].slice(0, 500);
  for (const id of ids) queued.delete(id);
  flushing = true;
  try {
    const result = await api.seen(ids);
    for (const id of ids) sent.add(id);
    // Only a mark that moved changes a badge or a list.
    if (result.threads > 0) {
      load();
      if (inbox.get().threads) loadInbox('threads', true);
      if (inbox.get().activity) loadInbox('activity', true);
    }
  } catch {
    for (const id of ids) queued.add(id);   // tried again with the next batch
  } finally {
    flushing = false;
    if (queued.size && !timer) timer = window.setTimeout(flush, 3000);
  }
}

