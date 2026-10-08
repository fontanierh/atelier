// Threads and Activity, as in Slack. Threads lists every conversation with replies that you started, joined, starred,
// or were addressed or @mentioned in: unread ones first, then newest reply first, each with its latest replies and a
// reply box. Activity is everything that involves you, newest first. Read state and stars are kept by the board, so
// every device agrees.
//
// Neither list ever goes blank: until the first answer it says it is loading, through a failure it keeps the last
// list and says so, and coming back to the view shows what it had while the new answer loads.
import {memo, useEffect, useLayoutEffect, useMemo, useRef, useState} from 'react';
import {api} from '../api/client';
import type {ActivityItem, Agent, Card, State, ThreadItem} from '../api/schema';
import {isLong, isoTime, longTime, replyHint, since, TOPICS} from '../lib/format';
import {snapScreen, isTouch, useMedia} from '../lib/media';
import {openFromInbox, threadsOrder} from '../nav';
import {board, load} from '../store/board';
import {inbox, loadInbox, type InboxView} from '../store/inbox';
import {setStar} from '../store/stars';
import {useStore} from '../store/store';
import {ui} from '../store/ui';
import {Attachments, Markdown, Orb, Slot} from './bits';
import {Icon} from './Icon';
import {replyTarget, ReplyBox, sendReply} from './ReplyBox';
import {useSwipe} from './swipe';
import {useSeen} from './useSeen';

const who = (name: string, me: string) => (name === me ? 'You' : name);
function people(names: string[], me: string): string {
  const list = [...new Set(names.map((n) => who(n, me)))];
  return list.length <= 3 ? list.join(', ') : `${list.slice(0, 2).join(', ')} and ${list.length - 2} others`;
}
const opens = (event: React.MouseEvent) => !(event.target as Element).closest('a,button,video,audio,summary,details,textarea');

async function markRead(body: {id?: number; through?: number; all?: boolean; follow?: boolean}, view: InboxView): Promise<void> {
  try { await api.read(body); } catch { /* the next refresh shows the truth */ }
  load();
  loadInbox(view, true);
}

/** Long messages fold as in the chat, with the same Read more, and stay open across refreshes. */
const unfolded = new Set<number>();
const InboxMessage = memo(function InboxMessage({m, me, agent, className = '', onOpen}:
  {m: Card; me: string; agent: Agent | undefined; className?: string; onOpen?: (() => void) | undefined}) {
  const long = isLong(m.body), [open, setOpen] = useState(unfolded.has(m.id));
  return (
    <div className={`inbox-message${m.unread ? ' unread' : ''}${className ? ` ${className}` : ''}`}
      onClick={onOpen ? (event) => { if (opens(event)) onOpen(); } : undefined}>
      <Orb name={m.sender === me ? 'you' : m.sender} agent={agent} />
      <div className="inbox-column">
        <div className="inbox-meta">
          <b>{who(m.sender, me)}</b>
          {m.topic !== 'info' && <span className={`topic ${m.topic}`}>{TOPICS[m.topic] || m.topic}</span>}
          <time className="time" dateTime={isoTime(m.created)} title={`${longTime(m.created)} · #${m.id}`}>{since(m.created)}</time>
        </div>
        <Markdown className={`body${long && !open ? ' collapsed' : ''}`} html={m.body_html} raw={m.body} />
        {long && (
          <button type="button" className="more" onClick={() => {
            if (open) unfolded.delete(m.id); else unfolded.add(m.id);
            setOpen(!open);
          }}>{open ? 'Show less' : 'Read more'}</button>
        )}
        {m.attachments?.length ? <Attachments files={m.attachments} /> : null}
      </div>
    </div>
  );
});

/* New threads and replies never shove what you are reading. Scrolled down, the item you are on stays exactly where it
   is while others arrive or move above it, and a pill says how many; at the top, they slide in and the rest glide
   down to make room. */
function paneEdge(pane: HTMLElement): number {
  const style = getComputedStyle(pane);
  return pane.getBoundingClientRect().top + (parseFloat(style.scrollPaddingTop) || parseFloat(style.paddingTop) || 0);
}
interface Steady { snap: boolean; release: boolean; anchor: HTMLElement | null }
function useSteady(list: React.RefObject<HTMLElement | null>, keys: string, steady: Steady, onUnseen: (n: number) => void) {
  // Where everything was, read before this render changes the DOM.
  const before = useRef<{tops: Map<string, number>; anchor: string | null; anchorTop: number; above: Set<string>; atTop: boolean} | null>(null);
  const unseen = useRef(new Set<string>()), lastKeys = useRef('');
  if (keys !== lastKeys.current && list.current) {
    const box = list.current, pane = box.closest<HTMLElement>('.pane-body')!, edge = paneEdge(pane);
    const keyed = [...box.children].filter((n): n is HTMLElement => n instanceof HTMLElement && Boolean(n.dataset.key));
    const anchor = steady.snap && steady.anchor?.isConnected ? steady.anchor
      : keyed.find((n) => n.getBoundingClientRect().bottom > edge + 1) ?? null;
    before.current = {
      tops: new Map(keyed.map((n) => [n.dataset.key!, n.getBoundingClientRect().top])),
      anchor: anchor?.dataset.key ?? null, anchorTop: anchor?.getBoundingClientRect().top ?? 0,
      above: new Set(keyed.slice(0, anchor ? keyed.indexOf(anchor) : 0).map((n) => n.dataset.key!)),
      atTop: steady.release || (!steady.snap && pane.scrollTop < 24 && !pane.contains(document.activeElement)),
    };
  }
  useLayoutEffect(() => {
    if (keys === lastKeys.current) return;
    lastKeys.current = keys;
    const box = list.current, b = before.current;
    before.current = null;
    if (!box) return;
    const pane = box.closest<HTMLElement>('.pane-body')!;
    // A snapping pane would otherwise snap back to the card that was first.
    if (steady.release) { pane.scrollTop = 0; requestAnimationFrame(() => { pane.scrollTop = 0; }); unseen.current.clear(); }
    if (!b || !b.tops.size) return;
    const nodes = [...box.children].filter((n): n is HTMLElement => n instanceof HTMLElement && Boolean(n.dataset.key));
    if (b.atTop) {
      for (const n of nodes) {
        const key = n.dataset.key!;
        if (!b.tops.has(key)) { n.classList.remove('arrive'); void n.offsetWidth; n.classList.add('arrive'); continue; }
        // Snap points follow transforms, so a snapping pane would be dragged along by the glide.
        const shift = b.tops.get(key)! - n.getBoundingClientRect().top;
        if (steady.snap || Math.abs(shift) < 1) continue;
        n.style.transition = 'none'; n.style.transform = `translateY(${shift}px)`; void n.offsetWidth;
        n.style.transition = 'transform .45s cubic-bezier(.2, .9, .25, 1)'; n.style.transform = '';
        n.addEventListener('transitionend', () => { n.style.transition = ''; }, {once: true});
      }
      return;
    }
    const now = nodes.find((n) => n.dataset.key === b.anchor);
    if (!now) return;
    const shift = now.getBoundingClientRect().top - b.anchorTop;
    if (Math.abs(shift) >= 1) { pane.scrollTop += shift; keyboardShift(pane, shift); }
    for (const n of nodes) { if (n === now) break; if (!b.above.has(n.dataset.key!)) unseen.current.add(n.dataset.key!); }
    onUnseen(unseen.current.size);
  });
  // Scrolling up to them counts them as seen.
  useEffect(() => {
    const pane = list.current?.closest<HTMLElement>('.pane-body');
    if (!pane) return;
    const scroll = () => {
      if (!unseen.current.size) return;
      const edge = paneEdge(pane);
      for (const key of [...unseen.current]) {
        const n = pane.querySelector(`[data-key="${CSS.escape(key)}"]`);
        if (!n || pane.scrollTop < 4 || n.getBoundingClientRect().bottom > edge + 1) unseen.current.delete(key);
      }
      onUnseen(unseen.current.size);
    };
    pane.addEventListener('scroll', scroll, {passive: true});
    return () => pane.removeEventListener('scroll', scroll);
  }, [list, onUnseen]);
}

/* The phone keyboard in Threads and Activity: what you were looking at moves up by the keyboard's height, and once the
   keyboard has gone the pane is exactly where it was, unless you scrolled meanwhile. */
interface Lift { pane: HTMLElement; field: HTMLElement; top: number; height: number; base: number; opened: boolean; moved: boolean }
let lift: Lift | null = null, restoring: Lift | null = null;
function keyboardShift(pane: HTMLElement, shift: number): void { for (const k of [lift, restoring]) if (k?.pane === pane) k.top += shift; }
export function inboxKeyboardFit(): void {
  const k = lift;
  if (!k) return;
  const shrink = Math.max(0, k.height - k.pane.clientHeight);
  if (shrink > 120) k.opened = true;
  // Dismissed without leaving the field (Android back): leave it, as the chat composer does.
  else if (k.opened && shrink < 40) { keyboardEnd(); k.field.blur(); return; }
  if (k.moved) return;
  // Room below for the push, then up by the keyboard, but never so far that the field being typed in leaves the top.
  // Only real changes are written: rewriting an unchanged scroll position makes phones repaint the list mid-animation.
  const padding = `${k.base + shrink}px`;
  if (k.pane.style.paddingBottom !== padding) k.pane.style.paddingBottom = padding;
  const field = k.field.getBoundingClientRect().top - k.pane.getBoundingClientRect().top + k.pane.scrollTop;
  const top = Math.round(k.top + Math.max(0, Math.min(shrink, field - k.top - 8)));
  if (Math.abs(k.pane.scrollTop - top) >= 1) k.pane.scrollTop = top;
}
function keyboardEnd(): void {
  const k = lift;
  lift = null;
  if (!k) return;
  k.pane.style.paddingBottom = '';
  if (k.moved) return;
  // Again once the keyboard's animation and the viewport have settled.
  restoring = k;
  const restore = () => { if (restoring === k && !lift && Math.abs(k.pane.scrollTop - k.top) >= 1) k.pane.scrollTop = k.top; };
  restore();
  for (const ms of [350, 750]) setTimeout(restore, ms);
}
function useKeyboardLift(paneRef: React.RefObject<HTMLElement | null>, snapping: () => boolean): void {
  useEffect(() => {
    const pane = paneRef.current!;
    let touchTop: number | null = null;
    // Where the pane was before a tap, since the browser may scroll to the field as it takes focus.
    const down = () => { if (!lift) touchTop = pane.scrollTop; };
    const focusin = (event: FocusEvent) => {
      const target = event.target as HTMLElement;
      if (!isTouch() || !target.matches('textarea') || snapping()) return;
      if (lift?.pane === pane) { lift.field = target; return; }   // another reply box, same keyboard
      keyboardEnd(); restoring = null;
      lift = {pane, field: target, top: touchTop ?? pane.scrollTop, height: pane.clientHeight,
        base: parseFloat(getComputedStyle(pane).paddingBottom) || 0, opened: false, moved: false};
      touchTop = null;
      inboxKeyboardFit();
    };
    const focusout = () => setTimeout(() => { if (lift?.pane === pane && !pane.contains(document.activeElement)) keyboardEnd(); }, 120);
    const move = () => { if (lift?.pane === pane) lift.moved = true; if (restoring?.pane === pane) restoring = null; };
    pane.addEventListener('pointerdown', down, {capture: true, passive: true});
    pane.addEventListener('focusin', focusin);
    pane.addEventListener('focusout', focusout);
    pane.addEventListener('touchmove', move, {passive: true});
    return () => {
      pane.removeEventListener('pointerdown', down, {capture: true});
      pane.removeEventListener('focusin', focusin); pane.removeEventListener('focusout', focusout);
      pane.removeEventListener('touchmove', move);
    };
  }, [paneRef, snapping]);
}

function NewAbove({count, onClick}: {count: number; onClick: () => void}) {
  if (!count) return null;
  return <button type="button" className="inbox-new-above" style={{top: 'calc(var(--pane-top, 0px) + 10px)'}} onClick={onClick}>
    <Icon name="up" /><span>{`${count} new`}</span>
  </button>;
}

function Loading({view, error}: {view: InboxView; error: string}) {
  return (
    <div className="empty inbox-empty"><Slot name={view === 'threads' ? 'thread' : 'activity'} />
      <h2>{error ? 'Can’t load this right now' : 'Loading…'}</h2>
      {error && <><p>{error}</p><button type="button" className="text-button" onClick={() => loadInbox(view, true)}>Try again</button></>}
    </div>
  );
}

/* ---- Threads ---- */

// Replies that outgrow their card show the newest, just above the reply box, fading out at the top. The rows are
// watched too, since an image or video can grow one after it renders.
function useFit(box: React.RefObject<HTMLElement | null>, version: unknown): void {
  useLayoutEffect(() => {
    const el = box.current;
    if (!el) return;
    const fit = () => {
      const rows = [...el.children] as HTMLElement[], gap = parseFloat(getComputedStyle(el).rowGap) || 0;
      const need = rows.reduce((sum, row) => sum + row.offsetHeight, 0) + gap * Math.max(0, rows.length - 1);
      el.classList.toggle('overflowing', need > el.clientHeight + 1);
    };
    const watch = new ResizeObserver(fit);
    watch.observe(el);
    for (const row of el.children) watch.observe(row);
    fit();
    return () => watch.disconnect();
  }, [box, version]);
}

const ThreadCard = memo(function ThreadCard({t, me, agents, snap, now}:
  {t: ThreadItem; me: string; agents: ReadonlyMap<string, Agent>; snap: boolean; now: number}) {
  const card = useRef<HTMLElement>(null), replies = useRef<HTMLDivElement>(null);
  const [leaving, setLeaving] = useState(false);
  const state = board.get().state;
  useFit(replies, t.latest.map((m) => m.id).join());
  // Mail's swipes: right marks it read, left stars it (or takes the star off).
  useSwipe(card, {
    right: t.unread ? {icon: 'check', label: 'Read', tone: 'read', act: () => markRead({id: t.id, through: t.newest}, 'threads')} : undefined,
    left: {icon: 'star', label: t.starred ? 'Unstar' : 'Star', tone: 'star', act: () => setStar(t.id, !t.starred)},
  });
  const more = t.replies - t.latest.length;
  return (
    <article ref={card} className={`card inbox-thread${t.unread ? ' unread' : ''}${t.starred ? ' starred' : ''}${leaving ? ' leaving' : ''}`}
      role="listitem" data-key={t.id} data-ids={[t.root.id, ...t.latest.map((m) => m.id)].join(' ')}>
      <header className="inbox-thread-head">
        <div className="inbox-thread-title">
          {t.starred && <span className="star-mark" aria-label="Starred"><Icon name="star" /></span>}
          <span className="inbox-people">{people(t.participants, me)}</span>
          {t.unread > 0 && <span className="new-pill">{`${t.unread} new`}</span>}
          <span className="inbox-when">{`${t.replies} ${t.replies === 1 ? 'reply' : 'replies'} · ${since(t.last_activity, now)}`}</span>
        </div>
        <div className="inbox-actions">
          {t.unread > 0 && <button type="button" className="text-button mark-read" onClick={() => markRead({id: t.id, through: t.newest}, 'threads')}>Mark read</button>}
          <button type="button" className={`text-button star-toggle${t.starred ? ' on' : ''}`} aria-pressed={t.starred}
            aria-label={t.starred ? 'Unstar this thread' : 'Star this thread'} title={t.starred ? 'Starred' : 'Star'}
            onClick={() => setStar(t.id, !t.starred)}><Icon name="star" /></button>
          <button type="button" className="text-button quiet-button" title="Hide this thread until someone @mentions you in it"
            onClick={() => { setLeaving(true); markRead({id: t.id, through: t.newest, follow: false}, 'threads'); }}>Unfollow</button>
          <button type="button" className="text-button" onClick={() => openFromInbox(t.id)}>Open</button>
        </div>
      </header>
      <div className="inbox-thread-body">
        <InboxMessage m={t.root} me={me} agent={agents.get(t.root.sender)} className="inbox-root" onOpen={() => openFromInbox(t.id)} />
        {more > 0 && (
          <button type="button" className="text-button inbox-earlier" onClick={() => openFromInbox(t.id)}>
            {`Show ${more} more ${more === 1 ? 'reply' : 'replies'}`}
          </button>
        )}
        {/* On a phone a thread is one screen with no Read more: a tap on a reply opens the whole thread. */}
        <div className="inbox-replies" ref={replies} onClick={(event) => { if (snap && opens(event)) openFromInbox(t.id); }}>
          {t.latest.map((m) => <InboxMessage key={m.id} m={m} me={me} agent={agents.get(m.sender)} className="inbox-reply-row" />)}
        </div>
      </div>
      <ReplyBox label="Reply in thread" placeholder={replyHint(replyTarget(t.reply_audience, '', state))}
        onSend={async (text, key) => {
          const target = await sendReply(text, key, replyTarget(t.reply_audience, text, board.get().state), t.id);
          load(); loadInbox('threads', true);
          return target;
        }} />
    </article>
  );
}, (a, b) => a.me === b.me && a.snap === b.snap && a.agents === b.agents && Math.floor(a.now / 60) === Math.floor(b.now / 60)
  && JSON.stringify(a.t) === JSON.stringify(b.t));

/** While Threads is on screen its order holds: a thread with a new reply updates where it is, and threads new to the
 *  list wait behind the pill, which also counts unread threads that would now move up. Coming back to the view, or
 *  tapping the pill, brings the current order. */
function arrange(threads: ThreadItem[], order: number[] | null) {
  if (!order) return {shown: threads, waiting: 0};
  const rank = new Map(threads.map((t, i) => [t.id, i])), kept = order.filter((id) => rank.has(id));
  const last = Math.max(-1, ...kept.map((id) => rank.get(id)!));
  const fresh = threads.filter((t) => !order.includes(t.id));
  // Older threads loaded with Show more go after the rest; newer ones are held.
  const held = new Set(fresh.filter((t) => rank.get(t.id)! < last).map((t) => t.id));
  let moved = 0, latest = -1;
  for (const id of kept) { const r = rank.get(id)!; if (r < latest && threads[r]!.unread) moved++; latest = Math.max(latest, r); }
  return {shown: [...kept.map((id) => threads[rank.get(id)!]!), ...fresh.filter((t) => !held.has(t.id))], waiting: held.size + moved};
}

export function ThreadsPane() {
  const data = useStore(inbox, (i) => i.threads), starredOnly = useStore(inbox, (i) => i.starredOnly);
  const listStarred = useStore(inbox, (i) => i.threadsStarred), error = useStore(inbox, (i) => i.error.threads);
  const state = useStore(board, (b) => b.state), view = useStore(ui, (u) => u.view);
  const phone = useMedia(snapScreen);
  const pane = useRef<HTMLDivElement>(null), list = useRef<HTMLDivElement>(null);
  const order = useRef<number[] | null>(null), snapCard = useRef<HTMLElement | null>(null), hold = useRef(0);
  const [release, setRelease] = useState(0), [unseen, setUnseen] = useState(0);
  const released = useRef(0), orderOf = useRef<boolean | undefined>(undefined);
  const me = state?.sender ?? 'operator';
  const agents = useMemo(() => new Map((state?.agents || []).map((a) => [a.agent, a])), [state?.agents]);

  if (threadsOrder.reset) { order.current = null; threadsOrder.reset = false; }
  // The order held on screen is the list's it was taken from: All and Starred each arrive in the board's own order.
  if (orderOf.current !== listStarred) order.current = null;
  const releasing = release !== released.current;
  const {shown, waiting} = data ? arrange(data.threads, releasing ? null : order.current) : {shown: [], waiting: 0};
  const keys = shown.map((t) => t.id).join();
  const snapping = () => snapScreen?.matches === true;
  useSteady(list, keys + (releasing ? `:${release}` : ''), {snap: phone, release: releasing, anchor: snapCard.current}, setUnseen);
  useLayoutEffect(() => { order.current = shown.map((t) => t.id); orderOf.current = listStarred; released.current = release; });

  // Phones: Threads is one thread per screen, as in a short-video feed. A swipe moves to the next thread, or back to
  // the one above; a thread's latest replies sit just over its reply box, and the keyboard lifts the box with them,
  // since the card shrinks to the room left rather than the list scrolling.
  useEffect(() => {
    const body = pane.current!;
    let timer = 0, blur = 0;
    const top = (card: HTMLElement) => card.getBoundingClientRect().top - paneEdge(body) + body.scrollTop;
    const align = () => {
      if (!snapping() || !snapCard.current?.isConnected || ui.get().view !== 'threads') return;
      const y = Math.round(top(snapCard.current));
      if (Math.abs(body.scrollTop - y) >= 1) body.scrollTop = y;
    };
    // As the keyboard opens the browser may scroll toward the field, so for a moment the pane holds on to the thread.
    const follow = (ms = 900) => {
      const running = performance.now() < hold.current;
      hold.current = performance.now() + ms;
      if (running) return;
      const step = () => { align(); if (performance.now() < hold.current) requestAnimationFrame(step); };
      requestAnimationFrame(step);
    };
    // The thread you are on is where the pane rests once you stop swiping; near the end, older threads load.
    const scroll = () => {
      clearTimeout(timer);
      timer = window.setTimeout(() => {
        if (!snapping() || performance.now() < hold.current) return;
        const cards = [...list.current!.querySelectorAll<HTMLElement>(':scope > .inbox-thread')];
        if (!cards.length) return;
        snapCard.current = cards.reduce((best, card) => (Math.abs(top(card) - body.scrollTop) < Math.abs(top(best) - body.scrollTop) ? card : best));
        const i = inbox.get();
        if (cards.indexOf(snapCard.current) >= cards.length - 3 && i.threads && i.threads.total > i.threads.threads.length) more();
      }, 140);
    };
    const focusin = (event: FocusEvent) => {
      const target = event.target as HTMLElement;
      if (!isTouch() || !target.matches('textarea') || !snapping()) return;
      clearTimeout(blur);
      snapCard.current = target.closest<HTMLElement>('.inbox-thread') || snapCard.current;
      document.getElementById('app')!.classList.add('typing');
      follow();
    };
    const focusout = () => {
      blur = window.setTimeout(() => {
        if (!body.contains(document.activeElement) && document.activeElement !== document.getElementById('message')) {
          document.getElementById('app')!.classList.remove('typing');
          follow();
        }
      }, 120);
    };
    const move = () => { hold.current = 0; };
    // The keyboard, a growing reply or a phone turning resizes the pane: it stays on the same thread.
    const resize = new ResizeObserver(align);
    resize.observe(body);
    body.addEventListener('scroll', scroll, {passive: true});
    body.addEventListener('focusin', focusin);
    body.addEventListener('focusout', focusout);
    body.addEventListener('touchmove', move, {passive: true});
    return () => {
      clearTimeout(timer); clearTimeout(blur); resize.disconnect();
      body.removeEventListener('scroll', scroll); body.removeEventListener('focusin', focusin);
      body.removeEventListener('focusout', focusout); body.removeEventListener('touchmove', move);
    };
  }, []);
  useKeyboardLift(pane, snapping);
  useLayoutEffect(() => {
    const p = pane.current;
    if (p) p.parentElement!.style.setProperty('--pane-top', `${p.offsetTop}px`);
  });
  useSeen(pane, () => view === 'threads' || ui.get().view === 'threads', keys);

  const filter = (on: boolean) => {
    if (on === inbox.get().starredOnly) return;
    inbox.set({starredOnly: on, threadLimit: 30});
    order.current = null; setRelease((r) => r + 1);
    loadInbox('threads', true);
  };
  function more(): void {
    inbox.set((i) => ({threadLimit: Math.min(200, i.threadLimit + 30)}));
    loadInbox('threads');
  }

  // Until the list asked for (All or Starred) arrives, the other one stays, dimmed.
  const stale = Boolean(data) && listStarred !== starredOnly;
  const summary = !data ? (error || 'Loading')
    : starredOnly ? (data.total ? `${data.total} starred` : 'Nothing starred yet')
      : data.total ? `${data.unread ? `${data.unread} with new replies · ` : ''}${data.total} ${data.total === 1 ? 'thread' : 'threads'} you're part of`
        : 'No threads yet';
  return (
    <section className="pane inbox-pane threads-pane" id="threadsPane" aria-labelledby="threadsHeading">
      <header className="pane-head">
        <div className="inbox-title">
          <h1 id="threadsHeading">Threads</h1>
          <div className="mode-switch filter-switch threads-filter" role="group" aria-label="Show">
            <button type="button" aria-pressed={!starredOnly} onClick={() => filter(false)}>All</button>
            <button type="button" aria-pressed={starredOnly} onClick={() => filter(true)}>
              <Icon name="star" /><span>Starred</span>
            </button>
          </div>
          <button type="button" className="text-button" id="threadsAllRead" hidden={!data?.unread || starredOnly}
            onClick={() => markRead({all: true}, 'threads')}>Mark all read</button>
        </div>
        <p className="pane-sub" id="threadsSummary">{summary}{error && data ? ' · Reconnecting…' : ''}</p>
      </header>
      <div className="pane-body" ref={pane}>
        <div id="threadsList" className={`inbox-list${stale ? ' stale' : ''}`} role="list" ref={list}>
          {!data ? <Loading view="threads" error={error} />
            : shown.length ? shown.map((t) => <ThreadCard key={t.id} t={t} me={me} agents={agents} snap={phone} now={state?.time ?? 0} />)
              : (
                <div className="empty inbox-empty"><Slot name={starredOnly ? 'star' : 'thread'} />
                  <h2>{starredOnly ? 'No starred threads' : 'No threads yet'}</h2>
                  <p>{starredOnly ? 'Star a thread (swipe a card left, or tap its star) to keep it here.'
                    : 'When you reply to an agent, or one replies to you, the conversation shows up here.'}</p>
                </div>
              )}
        </div>
        <button type="button" className="text-button inbox-more" id="threadsMore" hidden={!data || data.total <= data.threads.length}
          onClick={more}>Show more threads</button>
        <p className="pane-note" id="threadsNote">Every conversation you started, joined, starred, or were addressed or @mentioned in.
          Unread ones come first, then the most recent. Swipe a card right to mark it read, or left to star it.</p>
      </div>
      <NewAbove count={unseen + waiting} onClick={() => { snapCard.current = null; setRelease((r) => r + 1); setUnseen(0); }} />
    </section>
  );
}

/* ---- Activity ---- */

const KIND_TEXT: Record<string, string> = {mention: 'Mentioned you', dm: 'Direct message', ack: 'Acknowledged', reply: 'Replied'};
function activityText(item: ActivityItem, me: string): string {
  const m = item.message;
  if (item.kind === 'ack') return `${people(item.senders, me)} acknowledged your message`;
  if (item.kind === 'reply' && item.count > 1) return `${item.count} new replies from ${people(item.senders, me)}`;
  if (!m) return people(item.senders, me);
  if (item.kind === 'reply') return `${who(m.sender, me)} replied${m.recipient === me ? ' to you' : ''} in a thread`;
  if (item.kind === 'mention') return `${who(m.sender, me)} mentioned you`;
  return `${who(m.sender, me)} messaged you`;
}

const ActivityRow = memo(function ActivityRow({item, state}: {item: ActivityItem; state: State}) {
  const row = useRef<HTMLElement>(null), [replying, setReplying] = useState(false);
  const me = state.sender, m = item.message, sender = m?.sender ?? item.senders[0] ?? '';
  useSwipe(row, {right: item.unread ? {icon: 'check', label: 'Read', tone: 'read',
    act: () => markRead({id: item.id, through: item.id}, 'activity')} : undefined});
  const quoted = item.kind === 'ack' ? item.target : m;
  return (
    <article ref={row} className={`activity-item${item.unread ? ' unread' : ''}`} role="listitem" data-key={item.id} data-ids={item.id}>
      <button type="button" className="activity-main" onClick={() => {
        if (item.unread) api.read({id: item.id, through: item.id}).catch(() => undefined);
        openFromInbox(item.id);
      }}>
        <Orb name={sender === me ? 'you' : sender} agent={state.agents.find((a) => a.agent === sender)} />
        <span className="activity-text">
          <span className="activity-line"><span className={`kind-tag ${item.kind}`}>{KIND_TEXT[item.kind] || item.kind}</span>
            <span className="inbox-when">{since(item.created, state.time)}</span></span>
          <span className="activity-summary">{activityText(item, me)}</span>
          {quoted && <span className="activity-snippet">{quoted.snippet || ''}</span>}
          {item.root && item.kind !== 'ack' && <span className="activity-context">{`in thread: ${who(item.root.sender, me)}: ${item.root.snippet}`}</span>}
        </span>
      </button>
      <div className="inbox-actions">
        {item.unread > 0 && <button type="button" className="text-button" onClick={() => markRead({id: item.id, through: item.id}, 'activity')}>Mark read</button>}
        {item.kind !== 'ack' && <button type="button" className="text-button" onClick={() => setReplying(true)}>Reply</button>}
      </div>
      {replying && (
        <ReplyBox label={`Reply to ${sender}`} placeholder={replyHint(replyTarget(item.reply_audience, '', state))} autoFocus
          onSend={async (text, key) => {
            const target = await sendReply(text, key, replyTarget(item.reply_audience, text, board.get().state), item.id);
            load(); loadInbox('activity', true);
            return target;
          }} />
      )}
    </article>
  );
}, (a, b) => a.item.id === b.item.id && a.item.unread === b.item.unread && a.item.count === b.item.count
  && Math.floor(a.state.time / 60) === Math.floor(b.state.time / 60));

const KINDS: [string, string][] = [['', 'All'], ['mention', 'Mentions'], ['reply', 'Threads'], ['dm', 'DMs'], ['ack', 'Acks']];

export function ActivityPane() {
  const data = useStore(inbox, (i) => i.activity), kind = useStore(inbox, (i) => i.kind), unreadOnly = useStore(inbox, (i) => i.unreadOnly);
  const error = useStore(inbox, (i) => i.error.activity), state = useStore(board, (b) => b.state);
  const pane = useRef<HTMLDivElement>(null), list = useRef<HTMLDivElement>(null), [unseen, setUnseen] = useState(0);
  const keys = (data?.items || []).map((i) => `${i.kind}:${i.id}`).join();
  useSteady(list, keys, {snap: false, release: false, anchor: null}, setUnseen);
  useKeyboardLift(pane, () => false);
  useLayoutEffect(() => {
    const p = pane.current;
    if (p) p.parentElement!.style.setProperty('--pane-top', `${p.offsetTop}px`);
  });
  useSeen(pane, () => ui.get().view === 'activity', keys);
  const n = data?.unread.all ?? 0;
  return (
    <section className="pane inbox-pane activity-pane" id="activityPane" aria-labelledby="activityHeading">
      <header className="pane-head">
        <div className="inbox-title">
          <h1 id="activityHeading">Activity</h1>
          <button type="button" className="text-button" id="activityAllRead" hidden={!n && !data?.unread.ack}
            onClick={() => markRead({all: true}, 'activity')}>Mark all read</button>
        </div>
        <p className="pane-sub" id="activitySummary">{!data ? (error || 'Loading') : n ? `${n} unread` : 'You’re all caught up'}
          {error && data ? ' · Reconnecting…' : ''}</p>
        <div className="activity-filters">
          <div className="mode-switch filter-switch" id="activityKinds" role="group" aria-label="Show">
            {KINDS.map(([value, label]) => {
              const count = value && value !== 'ack' ? data?.unread[value as keyof typeof data.unread] || 0 : 0;
              return (
                <button key={value} type="button" data-kind={value} aria-pressed={kind === value} data-count={count || ''}
                  onClick={() => { inbox.set({kind: value, activityLimit: 60}); loadInbox('activity', true); }}>{label}</button>
              );
            })}
          </div>
          <label className="unread-toggle">
            <input type="checkbox" id="activityUnread" checked={unreadOnly}
              onChange={(event) => { inbox.set({unreadOnly: event.target.checked}); loadInbox('activity', true); }} />
            <span>Unreads</span>
          </label>
        </div>
      </header>
      <div className="pane-body" ref={pane}>
        <div id="activityList" className="inbox-list activity-list" role="list" ref={list}>
          {!data || !state ? <Loading view="activity" error={error} />
            : data.items.length ? data.items.map((item) => <ActivityRow key={`${item.kind}:${item.id}`} item={item} state={state} />)
              : (
                <div className="empty inbox-empty"><Slot name="activity" />
                  <h2>{unreadOnly ? 'Nothing unread' : 'No activity yet'}</h2>
                  <p>Mentions, replies to you and direct messages land here.</p>
                </div>
              )}
        </div>
        <button type="button" className="text-button inbox-more" id="activityMore" hidden={!data || data.total <= data.items.length}
          onClick={() => { inbox.set((i) => ({activityLimit: Math.min(300, i.activityLimit + 60)})); loadInbox('activity'); }}>
          Show older activity
        </button>
      </div>
      <NewAbove count={unseen} onClick={() => pane.current?.scrollTo({top: 0, behavior: 'smooth'})} />
    </section>
  );
}
