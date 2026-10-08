// What the feed is doing, shared by the feed view and navigation: whether it follows the newest message, whether its
// current conversation has painted, and our own scroll moves (which must not count as the reader scrolling).
import {Store} from '../store/store';

const byId = (id: string) => document.getElementById(id);

export const feed = {
  /** Follow the newest message (the reader is at the bottom). */
  stick: true,
  /** The current conversation has painted at least once. */
  painted: false,
  /** Until then, scroll events are ours. */
  settleUntil: 0,
  settle(ms = 500) { this.settleUntil = performance.now() + ms; },
  nearBottom(): boolean {
    const f = byId('feed');
    return !f || f.scrollHeight - f.scrollTop - f.clientHeight < 96;
  },
  /** Land on the newest message and keep following new ones. */
  scrollToLatest(smooth = false) {
    byId('app')?.classList.remove('reading', 'hide-top');
    const f = byId('feed');
    f?.scrollTo({top: f.scrollHeight, behavior: smooth ? 'smooth' : 'auto'});
    this.stick = true;
    this.onLatest?.();
  },
  onLatest: null as null | (() => void),
};

/** Waits for a condition, checked every frame, for at most `ms`. */
export const waitFor = (ready: () => unknown, ms: number) => new Promise<void>((done) => {
  const start = performance.now();
  (function check() { if (ready() || performance.now() - start > ms) done(); else requestAnimationFrame(check); })();
});

/** New messages below what the reader has seen in the feed: the Messages tab's badge and the jump button's label. */
export const feedBadge = new Store<{unread: number; jump: boolean}>({unread: 0, jump: false});
