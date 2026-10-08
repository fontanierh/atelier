// The thread view: the original and every reply, with the composer replying in the thread. What it shows counts as
// read, and the star in its header keeps it in Threads → Starred on every device.
import {useEffect, useLayoutEffect, useMemo, useRef} from 'react';
import type {Agent, State} from '../api/schema';
import {continues, groupsFrom, type Group} from '../lib/format';
import {navBack} from '../nav';
import {board, liveAgents} from '../store/board';
import {composer, setRecipient} from '../store/composer';
import {setStar} from '../store/stars';
import {useStore} from '../store/store';
import {loadThread, thread, type OpenThread} from '../store/thread';
import {Slot} from './bits';
import {Icon} from './Icon';
import {MessageNode} from './Message';
import {useSeen} from './useSeen';

/** Whether the thread follows its newest reply (the reader is at its end). */
export const threadFeed = {stick: true};

/** Who a thread's replies go to: the agent who started it, or the agents your opening message mentioned, plus every
 *  agent who has joined in. A message you sent to the whole board keeps its replies there. */
export function threadAudience(root: Group, replies: Group[], state: State): string | string[] {
  const m = root.first, me = state.sender, live = new Set(liveAgents(state).map((a) => a.agent));
  if (m.sender === me && !root.mentions && (root.broadcast || m.recipient === '*')) return '*';
  const names = new Set(m.sender === me ? root.messages.map((x) => x.recipient) : [m.sender]);
  for (const g of replies) for (const x of g.messages) names.add(x.sender === me ? x.recipient : x.sender);
  const list = [...names].filter((name) => live.has(name) && name !== me);
  return list.length === 0 ? '*' : list.length === 1 ? list[0]! : list;
}

/** What the composer needs from the open thread: what it replies to, and to whom. */
export function replyContext(open: OpenThread | null, state: State | null) {
  if (!open?.data || !state) return {replyTo: open ? open.id : null, target: null, audience: null};
  const [root] = groupsFrom(open.data.root), replies = groupsFrom(open.data.replies);
  if (!root) return {replyTo: open.id, target: null, audience: null};
  const target = threadAudience(root, replies, state);
  // Several agents: the thread keeps them all as its audience, so a reply never falls back to everyone.
  return {replyTo: root.first.id, target, audience: Array.isArray(target) ? target : null};
}

function Star({open}: {open: OpenThread}) {
  if (!open.data) return null;
  const on = open.data.starred, id = open.data.root[0]?.id ?? open.id;
  return (
    <button type="button" className={`round-button star-button${on ? ' on' : ''}`} aria-pressed={on}
      aria-label={on ? 'Unstar this thread' : 'Star this thread'} title={on ? 'Starred' : 'Star'}
      onClick={() => setStar(id, !on)}><Icon name="star" /></button>
  );
}

export function ThreadView() {
  const open = useStore(thread, (t) => t.open), state = useStore(board, (b) => b.state);
  const box = useRef<HTMLDivElement>(null), newest = useRef(Infinity), focused = useRef(0), aimed = useRef(0);
  const opened = open?.opened ?? 0;

  // Each poll of the board also refreshes the open thread (a request already in flight is not repeated).
  const time = useStore(board, (b) => b.state?.time);
  useEffect(() => { if (thread.get().open) loadThread(); }, [time]);
  useLayoutEffect(() => { threadFeed.stick = true; newest.current = Infinity; }, [opened]);

  const view = useMemo(() => {
    if (!open?.data || !state) return null;
    const agents = new Map<string, Agent>(state.agents.map((a) => [a.agent, a]));
    const [root] = groupsFrom(open.data.root), replies = groupsFrom(open.data.replies);
    if (!root) return null;
    const me = state.sender, sigOf = (g: Group) => JSON.stringify(g.messages.map((x) => [x.id, x.acknowledged,
      (agents.get(x.recipient)?.cursor || 0) >= x.id, Boolean(agents.get(x.recipient)?.delivery_error)]));
    const people = [...new Set([root, ...replies].map((g) => (g.first.sender === me ? 'you' : g.first.sender)))];
    let previous: Group | null = null;
    const items = replies.map((g) => {
      const continued = continues(previous, g), enter = g.first.id > newest.current;
      previous = g;
      return {g, ctx: {agents, inThread: true, continued, enter, sig: sigOf(g) + continued}};
    });
    return {root, rootCtx: {agents, inThread: true, sig: sigOf(root)}, items, people,
      newest: Math.max(0, ...open.data.replies.map((r) => r.id))};
  }, [open?.data, state]);

  useLayoutEffect(() => {
    const f = box.current;
    if (!view || !f) return;
    newest.current = view.newest;
    if (threadFeed.stick) f.scrollTop = f.scrollHeight;
  }, [view]);

  // The thread takes over the composer: it replies in the thread, to the thread's people.
  useEffect(() => {
    if (!open?.data || !state || aimed.current === opened) return;
    aimed.current = opened;
    const {target} = replyContext(open, state);
    if (typeof target === 'string' && composer.get().recipient !== target
      && (target === '*' || liveAgents(state).some((a) => a.agent === target))) setRecipient(target);
  }, [open, state, opened]);
  useEffect(() => {
    if (!open?.data || !open.focus || focused.current === opened) return;
    focused.current = opened;
    document.getElementById('message')?.focus();
  }, [open, opened]);

  useSeen(box, () => Boolean(thread.get().open?.data), view);

  const replies = view?.items.length ?? 0;
  const label = replies ? `${replies} ${replies === 1 ? 'reply' : 'replies'}` : 'No replies yet';
  return (
    <section className="thread-view" id="threadView" aria-label="Thread" hidden={!open}>
      <header className="thread-head">
        <button type="button" className="back-button" id="threadBack" aria-label="Close thread" onClick={() => navBack()}>
          <Slot name="back" /><span className="back-label">Back</span>
        </button>
        <div className="title-text">
          <h1 id="threadTitle">Thread</h1>
          <p id="threadSubtitle">{open?.status || (view ? `${label} · ${view.people.join(', ')}` : '')}</p>
        </div>
        {open && <Star open={open} />}
      </header>
      <div className="thread-feed" id="threadFeed" ref={box} onScroll={(event) => {
        const f = event.currentTarget;
        threadFeed.stick = f.scrollHeight - f.scrollTop - f.clientHeight < 96;
      }}>
        {view && <>
          <MessageNode key={`r:${view.root.key}`} group={view.root} ctx={view.rootCtx} />
          <div className="thread-divider"><span>{label}</span></div>
          {view.items.map(({g, ctx}) => <MessageNode key={`m:${g.key}`} group={g} ctx={ctx} />)}
        </>}
      </div>
    </section>
  );
}
