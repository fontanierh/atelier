// One message in the feed or a thread: who, to whom, its text and files, its delivery receipt and its replies.
import {memo, useRef} from 'react';
import type {Agent, Message} from '../api/schema';
import {clock, isLong, isoTime, isSystem, longTime, snippet, TOPICS, type Group} from '../lib/format';
import {openAgent, openThread} from '../nav';
import {board} from '../store/board';
import {toggle, ui} from '../store/ui';
import {useStore} from '../store/store';
import {Attachments, Markdown, Orb} from './bits';
import {Icon} from './Icon';
import {useSwipe} from './swipe';

export interface MessageContext {
  agents: ReadonlyMap<string, Agent>;
  continued?: boolean;
  enter?: boolean;
  replies?: Group[] | undefined;
  inThread?: boolean;
  /** Everything the node shows; it re-renders only when this changes. */
  sig: string;
}

function Who({name, className, children}: {name: string; className: string; children: React.ReactNode}) {
  return (
    <button type="button" className={className} title={`Message ${name} directly`}
      aria-label={`Open your direct messages with ${name}`}
      onClick={(event) => { event.stopPropagation(); openAgent(name); }}>{children}</button>
  );
}

function ReplyButton({m}: {m: Message}) {
  return (
    <button type="button" className="reply-button" aria-label="Reply in thread" title="Reply in thread"
      onClick={(event) => { event.stopPropagation(); openThread(m.id, true); }}><Icon name="reply" /></button>
  );
}

function Receipt({group, agents}: {group: Group; agents: ReadonlyMap<string, Agent>}) {
  const open = useStore(ui, (u) => u.deliveryOpen.has(group.key));
  const got = (item: Message) => (agents.get(item.recipient)?.cursor || 0) >= item.id;
  const picked = group.messages.filter(got), acked = group.messages.filter((item) => item.acknowledged);
  const retrying = group.messages.some((item) => !got(item) && agents.get(item.recipient)?.delivery_error);
  if (!group.broadcast && group.first.recipient === '*') {
    return <details className="receipt"><summary><Icon name="check" /><span>Posted to the board</span></summary></details>;
  }
  let text: string, done: boolean;
  if (group.broadcast) {
    done = acked.length === group.messages.length;
    text = `Delivered ${picked.length}/${group.messages.length} · ${acked.length} acknowledged`;
  } else {
    done = acked.length > 0;
    text = done ? 'Acknowledged' : picked.length ? 'Delivered · awaiting ack' : retrying ? 'Retrying delivery' : 'Queued';
  }
  return (
    <details className="receipt" open={open} onToggle={(event) => toggle('deliveryOpen', group.key, event.currentTarget.open)}>
      <summary className={done ? 'done' : retrying ? 'warn' : ''}><Icon name="check" /><span>{text}</span></summary>
      <div className="receipt-list">
        {group.messages.map((item) => {
          const agent = agents.get(item.recipient);
          const status = item.acknowledged ? 'Acknowledged' : got(item) ? 'Delivered' : agent?.delivery_error ? 'Retrying' : 'Queued';
          return (
            <div key={item.id} className="receipt-row">
              <span>{item.recipient}</span><span className={`receipt-state ${status.toLowerCase()}`}>{status}</span>
            </div>
          );
        })}
      </div>
    </details>
  );
}

function ThreadBar({replies, me, onOpen}: {replies: Group[]; me: string; onOpen: () => void}) {
  const last = replies.at(-1)!.first;
  return (
    <button type="button" className="thread-bar" onClick={onOpen}>
      <span className="thread-faces">
        {[...new Set(replies.map((r) => r.first.sender))].slice(0, 3).map((s) => <Orb key={s} name={s === me ? '*' : s} />)}
      </span>
      <span className="thread-count">{`${replies.length} ${replies.length === 1 ? 'reply' : 'replies'}`}</span>
      <span className="thread-last">{`Last ${clock(last.created)}`}</span>
      <Icon name="right" />
    </button>
  );
}

function Quote({m}: {m: Message}) {
  const original = useStore(board, (b) => b.records.get(m.reply_to!));
  const me = useStore(board, (b) => b.state?.sender);
  return (
    <button type="button" className={`quote${original ? '' : ' quote-away'}`}
      onClick={(event) => { event.stopPropagation(); openThread(m.id); }}>
      {original ? <>
        <span className="quote-who">{original.sender === me ? 'You' : original.sender}</span>
        <span className="quote-text">{snippet(original.body)}</span>
      </> : <><Icon name="reply" /><span>In reply to an earlier message · open thread</span></>}
    </button>
  );
}

function Body({group}: {group: Group}) {
  const m = group.first, long = isLong(m.body);
  const open = useStore(ui, (u) => u.expanded.has(group.key)), collapsed = long && !open;
  if (!m.body_html?.trim()) return null;
  return <>
    <Markdown className={`body${collapsed ? ' collapsed' : ''}`} html={m.body_html} raw={m.body} onMention={openAgent} />
    {long && (
      <button type="button" className="more" onClick={(event) => { event.stopPropagation(); toggle('expanded', group.key); }}>
        {collapsed ? 'Read more' : 'Show less'}
      </button>
    )}
  </>;
}

export const MessageNode = memo(function MessageNode({group, ctx}: {group: Group; ctx: MessageContext}) {
  const me = useStore(board, (b) => b.state?.sender ?? 'operator');
  const m = group.first, mine = m.sender === me, agents = ctx.agents, inThread = Boolean(ctx.inThread);
  // It animates in once, as it first arrives; later changes leave the class (and the playful layer's) alone.
  const entered = useRef(ctx.enter);
  const urgent = m.topic === 'alert' || m.topic === 'blocked';
  const className = `message${mine ? ' mine' : ''}${ctx.continued ? ' continued' : ''}${urgent ? ' urgent' : ''}${entered.current ? ' enter' : ''}`;
  const to = group.broadcast || m.recipient === '*' ? 'everyone' : m.recipient === me ? 'you' : m.recipient;
  const people = group.messages.map((x) => (x.recipient === me ? 'you' : x.recipient));
  const replyable = !inThread && !ctx.replies?.length;
  const tappable = !inThread && !isSystem(m);
  const bubbleRef = useRef<HTMLDivElement>(null);
  // Swipe a message left to reply to it in its thread.
  useSwipe(bubbleRef, {left: tappable ? {icon: 'reply', label: 'Reply', act: () => openThread(m.id, true)} : undefined});
  const bubble = (
    <div ref={bubbleRef} className={`card bubble${tappable ? ' tappable' : ''}`} onClick={tappable ? (event) => {
      if ((event.target as Element).closest('a,button,video,audio,summary,details,input,select,textarea')) return;
      if (String(window.getSelection?.() || '')) return;
      openThread(m.id, !ctx.replies?.length);
    } : undefined}>
      {!ctx.continued && (
        <div className="meta">
          {mine || isSystem(m) ? <span className="sender">{mine ? 'You' : m.sender}</span>
            : <Who name={m.sender} className="sender who">{m.sender}</Who>}
          <span className="route">{group.merged || group.mentions
            ? `to ${people.length > 3 ? `${people.length} agents` : people.join(', ')}`
            : `to ${to === 'everyone' && group.broadcast ? `everyone (${group.messages.length})` : to}`}</span>
          {m.topic !== 'info' && <span className={`topic ${m.topic}`}>{TOPICS[m.topic] || m.topic}</span>}
          <time className="time" dateTime={isoTime(m.created)} title={`${longTime(m.created)} · #${m.id}`}>{clock(m.created)}</time>
          {replyable && <ReplyButton m={m} />}
        </div>
      )}
      {m.reply_to && !inThread ? <Quote m={m} /> : null}
      <Body group={group} />
      {m.attachments?.length ? <Attachments files={m.attachments} /> : null}
      {ctx.continued && (
        <div className="bubble-time">
          <time title={`#${m.id}`}>{clock(m.created)}</time>
          {replyable && <ReplyButton m={m} />}
        </div>
      )}
    </div>
  );
  return (
    <article className={className} data-ids={group.messages.map((x) => x.id).join(' ')}>
      {!mine && (ctx.continued ? <span className="orb-space" /> : <Who name={m.sender} className="orb-link"><Orb name={m.sender} /></Who>)}
      <div className="message-column">
        {bubble}
        {mine && <Receipt group={group} agents={agents} />}
        {ctx.replies?.length ? <ThreadBar replies={ctx.replies} me={me} onOpen={() => openThread(m.id)} /> : null}
      </div>
    </article>
  );
}, (a, b) => a.group.key === b.group.key && a.ctx.sig === b.ctx.sig);
