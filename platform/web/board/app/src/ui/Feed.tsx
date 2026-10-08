// The feed: oldest at the top, newest by the composer, like a chat. Day separators, automatic notices folded into one
// quiet line, replies folded under their thread. An unchanged message keeps its node (it is memoised on what it
// shows), so photos and videos never reload and nothing above the newest message moves when it arrives.
import {memo, useCallback, useEffect, useLayoutEffect, useMemo, useRef} from 'react';
import type {Agent, Message} from '../api/schema';
import {feed, feedBadge} from '../lib/feed';
import {clock, continues, dayLabel, groupsFrom, isSystem, threadIndex} from '../lib/format';
import {isDesktop, reducedMotion} from '../lib/media';
import {board, load, loadOlder} from '../store/board';
import {useStore} from '../store/store';
import {thread} from '../store/thread';
import {filtered as isFiltered, filterKey, ui} from '../store/ui';
import {Slot} from './bits';
import {Icon} from './Icon';
import {MessageNode, type MessageContext} from './Message';
import {useSeen} from './useSeen';

type Item =
  | {kind: 'empty'; key: string}
  | {kind: 'day'; key: string; label: string; enter: boolean}
  | {kind: 'notices'; key: string; list: Message[]; enter: boolean}
  | {kind: 'message'; key: string; group: ReturnType<typeof groupsFrom>[number]; ctx: MessageContext};

const Notices = memo(function Notices({list, enter}: {list: Message[]; enter: boolean}) {
  const last = list.at(-1)!, sections = new Set<string>();
  for (const m of list) {
    for (const part of ((m.body.match(/changed \(([^)]*)\)/) || [])[1] || '').split(/,\s*/)) if (part) sections.add(part);
  }
  const what = /render scheduling board changed/i.test(last.body)
    ? `Render schedule updated${sections.size ? ` · ${[...sections].join(', ')}` : ''}` : `${last.sender}: ${last.body.slice(0, 80)}`;
  const first = useRef(enter);
  return (
    <details className={`notice${first.current ? ' enter' : ''}`} data-ids={list.map((m) => m.id).join(' ')}>
      <summary><Icon name="board" /><span className="notice-text">{`${what}${list.length > 1 ? ` · ${list.length}×` : ''}`}</span>
        <time>{clock(last.created)}</time></summary>
      <p>{last.body}</p>
    </details>
  );
}, (a, b) => a.list.length === b.list.length && a.list.at(-1)?.id === b.list.at(-1)?.id);

function Empty() {
  const state = useStore(board, (b) => b.state), failed = useStore(board, (b) => b.failed);
  const agent = useStore(ui, (u) => u.agent), mode = useStore(ui, (u) => u.mode), filtered = useStore(ui, isFiltered);
  if (!state) {
    return (
      <div className="empty"><Slot name="messages" />
        <h2>{failed ? 'Can’t reach your board' : 'Connecting to your board'}</h2>
        <p>{failed ? 'It will keep trying.' : 'Your messages will appear here.'}</p>
        {failed && <button type="button" className="text-button" onClick={() => load({reset: true})}>Try now</button>}
      </div>
    );
  }
  return (
    <div className="empty"><Slot name="messages" />
      <h2>{filtered ? 'No matching messages' : 'A quiet board, for now'}</h2>
      <p>{agent ? (mode === 'dm' ? `Nothing between you and ${agent} yet. Say hello below.` : `Say hello to ${agent} below.`)
        : filtered ? 'Try a different search or topic.' : 'Send a message to start the conversation.'}</p>
    </div>
  );
}

function useItems(newestShown: React.RefObject<number>): {items: Item[]; newest: number; unreadAbove: (seen: number) => number} {
  const records = useStore(board, (b) => b.records), state = useStore(board, (b) => b.state);
  const showSystem = useStore(ui, (u) => u.showSystem);
  return useMemo(() => {
    const me = state?.sender ?? 'operator', agents = new Map<string, Agent>((state?.agents || []).map((a) => [a.agent, a]));
    const groups = groupsFrom(records.values()), {replies, threaded} = threadIndex(groups);
    const visible = groups.filter((g) => (showSystem || !isSystem(g.first)) && !threaded.has(g.key));
    // Only messages that arrive after the first paint animate in; history and filter changes appear at rest.
    const above = feed.painted ? newestShown.current : Infinity;
    const items: Item[] = [];
    let day = '', previous: (typeof groups)[number] | null = null, run: Extract<Item, {kind: 'notices'}> | null = null;
    if (!visible.length) items.push({kind: 'empty', key: 'empty'});
    for (const group of visible) {
      const m = group.first, label = dayLabel(m.created), enter = m.id > above;
      if (label !== day) { day = label; previous = null; run = null; items.push({kind: 'day', key: `d:${label}`, label, enter}); }
      if (isSystem(m)) {
        // Consecutive automatic notices collapse into one quiet line.
        if (run) { run.list.push(m); continue; }
        run = {kind: 'notices', key: `n:${m.id}`, list: [m], enter};
        items.push(run); previous = null; continue;
      }
      run = null;
      const mine = m.sender === me, threadReplies = replies.get(group.key);
      const continued = continues(previous, group) && !replies.get(previous!.key)?.length;
      const sig = JSON.stringify([group.messages.map((x) => [x.id, x.acknowledged, mine
        ? [(agents.get(x.recipient)?.cursor || 0) >= x.id, Boolean(agents.get(x.recipient)?.delivery_error)] : 0]),
      continued, (threadReplies || []).map((r) => r.first.id), me]);
      items.push({kind: 'message', key: `m:${group.key}`, group, ctx: {agents, continued, enter, replies: threadReplies, sig}});
      previous = group;
    }
    const newest = records.size ? Math.max(...records.keys()) : 0;
    const unreadAbove = (seenId: number) =>
      groups.filter((g) => !isSystem(g.first) && g.first.id > seenId && g.first.sender !== me).length;
    return {items, newest, unreadAbove};
  }, [records, state, showSystem, newestShown]);
}

const viewing = () => ui.get().view === 'messages' || isDesktop();

export function Feed() {
  const box = useRef<HTMLDivElement>(null), newestShown = useRef(0), lastSeen = useRef(0);
  const historyComplete = useStore(board, (b) => b.historyComplete), size = useStore(board, (b) => b.records.size);
  const prepended = useStore(board, (b) => b.prepended), recordsKey = useStore(board, (b) => b.recordsKey);
  const view = useStore(ui, (u) => u.view);
  const {items, newest, unreadAbove} = useItems(newestShown);

  // Where the reader was, read before this render changes the DOM.
  const before = useRef({top: 0, fromBottom: 0, prepended: 0});
  if (box.current) before.current = {...before.current, top: box.current.scrollTop, fromBottom: box.current.scrollHeight - box.current.scrollTop};

  const badge = useCallback((unread: number) => {
    const away = !viewing();
    feedBadge.set({unread: away || !feed.stick ? unread : 0, jump: !feed.nearBottom()});
  }, []);
  const markSeen = useCallback(() => {
    if (!viewing()) return;
    if (feed.nearBottom() || feed.stick) { lastSeen.current = Math.max(lastSeen.current, newestShown.current); badge(0); }
  }, [badge]);
  useEffect(() => { feed.onLatest = markSeen; return () => { feed.onLatest = null; }; }, [markSeen]);

  useLayoutEffect(() => {
    const f = box.current;
    if (!f) return;
    feed.settle();
    if (prepended !== before.current.prepended) { f.scrollTop = f.scrollHeight - before.current.fromBottom; before.current.prepended = prepended; }
    else if (feed.stick) f.scrollTop = f.scrollHeight;
    else f.scrollTop = before.current.top;
    if (recordsKey === filterKey(ui.get()) && board.get().state) feed.painted = true;
    newestShown.current = newest;
    if (!lastSeen.current || (feed.stick && viewing())) lastSeen.current = newest;
    badge(feed.stick && viewing() ? 0 : unreadAbove(lastSeen.current));
  }, [items, newest, prepended, recordsKey, unreadAbove, badge]);

  // Coming back to the conversation counts what was new while away as seen once it is at the bottom.
  useEffect(() => { if (view === 'messages') markSeen(); else badge(unreadAbove(lastSeen.current)); }, [view, markSeen, badge, unreadAbove]);

  useEffect(() => {
    const f = box.current!, app = document.getElementById('app')!, painting = document.getElementById('painting');
    let lastTop = f.scrollTop, travel = 0, frame = 0;
    // Parallax: as you scroll back through history the meadow follows at a fraction of the speed, up to 44 px.
    const parallax = () => {
      if (frame || reducedMotion() || isDesktop() || !painting) return;
      frame = requestAnimationFrame(() => {
        frame = 0;
        const gap = Math.max(0, f.scrollHeight - f.scrollTop - f.clientHeight);
        painting.style.transform = `translate3d(0,${Math.min(44, gap * .035).toFixed(1)}px,0)`;
      });
    };
    const scroll = () => {
      parallax();
      // Our own re-renders and filter switches move the scroll position too; those are not the reader scrolling.
      if (performance.now() < feed.settleUntil) { if (feed.stick) f.scrollTop = f.scrollHeight; return; }
      feed.stick = feed.nearBottom();
      const gap = f.scrollHeight - f.scrollTop - f.clientHeight;
      if (gap > 320) app.classList.add('reading'); else if (gap < 60) app.classList.remove('reading');
      // The top bar slides away while you scroll back through history and returns as you scroll down, like Safari's.
      const delta = f.scrollTop - lastTop;
      lastTop = f.scrollTop;
      travel = Math.sign(delta) === Math.sign(travel) ? travel + delta : delta;
      if (gap < 60 || travel > 36) app.classList.remove('hide-top'); else if (travel < -36 && gap > 160) app.classList.add('hide-top');
      if (feed.stick) markSeen(); else feedBadge.set({jump: true});
      const b = board.get();
      if (f.scrollTop < 120 && !b.historyComplete && b.records.size && !b.loadingOlder) loadOlder();
    };
    f.addEventListener('scroll', scroll, {passive: true});
    return () => { f.removeEventListener('scroll', scroll); cancelAnimationFrame(frame); };
  }, [markSeen]);

  // What is on screen counts as read, unless a thread covers the feed on a phone.
  useSeen(box, () => viewing() && (isDesktop() || !thread.get().open), items);

  return (
    <div className="feed" id="feed" ref={box} tabIndex={-1} role="log" aria-label="Messages" aria-live="polite">
      <button type="button" id="loadOlder" className="load-older" hidden={historyComplete || !size} onClick={loadOlder}>
        Load earlier messages
      </button>
      <div id="messages" className="messages">
        {items.map((item) => {
          switch (item.kind) {
            case 'empty': return <Empty key={item.key} />;
            case 'day': return <div key={item.key} className={`day${item.enter ? ' enter' : ''}`}><span>{item.label}</span></div>;
            case 'notices': return <Notices key={item.key} list={item.list} enter={item.enter} />;
            case 'message': return <MessageNode key={item.key} group={item.group} ctx={item.ctx} />;
          }
        })}
      </div>
    </div>
  );
}
