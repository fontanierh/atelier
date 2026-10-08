// Stars: a thread starred on any device is starred on every device (the board keeps them). The change shows at once
// and is put back if the board refuses it.
import {api, message} from '../api/client';
import {inbox, loadInbox} from './inbox';
import {patchThread, thread} from './thread';

function show(id: number, starred: boolean): void {
  const open = thread.get().open;
  if (open?.data && (open.id === id || open.data.root.some((m) => m.id === id))) patchThread({starred});
  inbox.set((i) => {
    if (!i.threads) return {};
    const threads = i.threads.threads.map((t) => (t.root.id === id ? {...t, starred} : t));
    const count = threads.filter((t) => t.starred).length - i.threads.threads.filter((t) => t.starred).length;
    return {threads: {...i.threads, threads, starred: Math.max(0, i.threads.starred + count)}};
  });
}

export async function setStar(id: number, starred: boolean): Promise<void> {
  show(id, starred);
  try {
    await api.star(id, starred);
  } catch (error) {
    show(id, !starred);
    inbox.set((i) => ({error: {...i.error, threads: message(error, 'The star could not be saved. Try again.')}}));
  }
  if (inbox.get().threads) loadInbox('threads', true);
}
