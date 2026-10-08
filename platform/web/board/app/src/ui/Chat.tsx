// The conversation pane: its top bar (title, Direct/All, search and filters, the agents' orbs), the feed, the thread
// view pushed over it and the dock with the composer.
import {memo, useEffect, useLayoutEffect, useRef, useState} from 'react';
import type {State} from '../api/schema';
import {isFree} from '../lib/agents';
import {feed, feedBadge} from '../lib/feed';
import {agentStatus, statusOf} from '../lib/format';
import {isDesktop, isTouch} from '../lib/media';
import {back, changedFilters, openAgent, selectAgent, swipeBack} from '../nav';
import {board, liveAgents} from '../store/board';
import {useStore} from '../store/store';
import {setShowSystem, ui} from '../store/ui';
import {Slot, Orb} from './bits';
import {Composer} from './Composer';
import {Feed} from './Feed';
import {threadFeed, ThreadView} from './ThreadView';

/** The meadow's layers; the playful layer adds its own creatures to them. Never re-rendered. */
export const Ambience = memo(function Ambience({painting = false}: {painting?: boolean}) {
  return (
    <div className="ambience" aria-hidden="true">
      {painting && <span className="painting" id="painting" />}
      <span className="mist" /><span className="mist far" />
      <span className="seed"><i /></span><span className="seed s2"><i /></span><span className="seed s3"><i /></span><span className="seed s4"><i /></span>
    </div>
  );
}, () => true);

function Subtitle() {
  const failed = useStore(board, (b) => b.failed), state = useStore(board, (b) => b.state), name = useStore(ui, (u) => u.agent);
  const agent = state?.agents.find((a) => a.agent === name), live = liveAgents(state), listening = live.filter((a) => a.listening).length;
  let dot = '', text: string;
  if (failed) { dot = 'error'; text = 'Reconnecting…'; }
  else if (!state) text = 'Connecting…';
  else if (agent) {
    dot = statusOf(agent);
    text = agentStatus(agent) + (agent.pending ? ` · ${agent.pending} queued` : '') + (agent.task ? ` · ${agent.task}` : '');
  } else { dot = listening ? 'live' : 'idle'; text = `${listening} of ${live.length} agents listening`; }
  return <p id="chatSubtitle"><span className={`dot${dot ? ` ${dot}` : ''}`} /><span>{text}</span></p>;
}

const TOPIC_OPTIONS: [string, string][] = [['', 'All topics'], ['request', 'Requests'], ['handoff', 'Handoffs'],
  ['ack', 'Acknowledgements'], ['blocked', 'Blocked'], ['release', 'Releases'], ['evidence', 'Evidence'], ['alert', 'Alerts'],
  ['info', 'Information']];

function SearchBar() {
  const open = useStore(ui, (u) => u.searchOpen), topic = useStore(ui, (u) => u.topic), showSystem = useStore(ui, (u) => u.showSystem);
  const applied = useStore(ui, (u) => u.search);
  const [text, setText] = useState(applied), input = useRef<HTMLInputElement>(null);
  useEffect(() => { setText(applied); }, [applied]);
  useEffect(() => {
    if (text === ui.get().search) return;
    const timer = setTimeout(() => { ui.set({search: text}); changedFilters(); }, 250);
    return () => clearTimeout(timer);
  }, [text]);
  useEffect(() => { if (open && !isTouch()) input.current?.focus(); }, [open]);
  return (
    <div className="searchbar" id="searchBar" hidden={!open}>
      <label className="search"><Slot name="search" />
        <input ref={input} id="search" type="search" placeholder="Search messages" aria-label="Search message history"
          autoComplete="off" enterKeyHint="search" value={text} onChange={(event) => setText(event.target.value)} />
      </label>
      <div className="search-options">
        <label className="select-pill">
          <span className="pill-value" aria-hidden="true">{TOPIC_OPTIONS.find(([value]) => value === topic)?.[1]}</span>
          <select id="topicFilter" aria-label="Filter by topic" value={topic}
            onChange={(event) => { ui.set({topic: event.target.value}); changedFilters(); }}>
            {TOPIC_OPTIONS.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
          </select>
          <Slot name="chevron" />
        </label>
        <label className="toggle">
          <input type="checkbox" id="showSystem" checked={showSystem} onChange={(event) => setShowSystem(event.target.checked)} />
          <span className="toggle-track" /><span>Board notices</span>
        </label>
      </div>
    </div>
  );
}

function toggleSearch(): void {
  const u = ui.get(), show = !u.searchOpen;
  ui.set({searchOpen: show});
  if (!show && (u.search || u.topic)) { ui.set({search: '', topic: ''}); changedFilters(); }
}

/** The agents' orbs above the feed (on a phone): tap one to open your conversation with them. */
function Orbs() {
  const state = useStore(board, (b) => b.state), chosen = useStore(ui, (u) => u.agent);
  const dismissed = useStore(board, (b) => b.dismissed), row = useRef<HTMLElement>(null);
  const agents = sortedAgents(state, dismissed).filter((a) => !a.stop);
  useLayoutEffect(() => {
    const orbs = row.current, current = orbs?.querySelector<HTMLElement>('[aria-current="true"]');
    if (orbs && current && (current.offsetLeft < orbs.scrollLeft || current.offsetLeft + current.offsetWidth > orbs.scrollLeft + orbs.clientWidth)) {
      orbs.scrollLeft = current.offsetLeft - 14;
    }
  }, [chosen, agents.length]);
  return (
    <nav className="orbs" id="agentChips" aria-label="Conversations" ref={row}>
      <button type="button" className="orb-button" aria-current={chosen === '' ? 'true' : undefined} title="All conversations"
        aria-label="All conversations" onClick={() => openAgent('')}>
        <Orb name="*" /><span className="orb-name">Everyone</span>
      </button>
      {agents.map((a) => {
        const title = `${a.agent} · ${agentStatus(a)}${a.task ? ` · ${a.task}` : ''}`;
        return (
          <button key={a.agent} type="button" className="orb-button" aria-current={chosen === a.agent ? 'true' : undefined}
            title={title} aria-label={title} onClick={() => openAgent(a.agent)}>
            {/* The orb marks unread direct messages from the agent; what is queued for it lives in the Agents list. */}
            <Orb name={a.agent} agent={a}>{a.unread > 0 ? <span className="unread-dot" /> : null}</Orb>
            <span className="orb-name">{a.agent}</span>
          </button>
        );
      })}
    </nav>
  );
}

/** Agents in the board's order: live first, listening first, free first, then by name. */
export function sortedAgents(state: State | null, dismissed: ReadonlySet<number>) {
  const free = (a: State['agents'][number]) => Number(isFree(a, state, dismissed));
  return [...(state?.agents || [])].sort((a, b) => a.stop - b.stop || Number(b.listening) - Number(a.listening)
    || free(b) - free(a) || a.agent.localeCompare(b.agent));
}

function Topbar() {
  const agent = useStore(ui, (u) => u.agent), mode = useStore(ui, (u) => u.mode), searchOpen = useStore(ui, (u) => u.searchOpen);
  useLayoutEffect(() => { document.getElementById('app')!.classList.toggle('in-conversation', Boolean(agent)); }, [agent]);
  return (
    <header className="topbar" id="topbar">
      <div className="titlerow">
        <button type="button" className="back-button" id="backButton" aria-label="Back to everyone" hidden={!agent} onClick={back}>
          <Slot name="back" />
        </button>
        <div className="title-text"><h1 id="chatTitle">{agent || 'Everyone'}</h1><Subtitle /></div>
        <div className="mode-switch" id="modeSwitch" role="group" aria-label="Conversation" hidden={!agent}>
          {(['dm', 'all'] as const).map((m) => (
            <button key={m} type="button" data-mode={m} aria-pressed={mode === m}
              onClick={() => { if (agent && mode !== m) selectAgent(agent, m); }}>{m === 'dm' ? 'Direct' : 'All'}</button>
          ))}
        </div>
        <button type="button" className={`round-button${searchOpen ? ' active' : ''}`} id="searchToggle" aria-label="Search and filter"
          aria-expanded={searchOpen} aria-controls="searchBar" onClick={toggleSearch}><Slot name="search" /></button>
      </div>
      <SearchBar />
      <Orbs />
    </header>
  );
}

function Banner() {
  const failed = useStore(board, (b) => b.failed), error = useStore(board, (b) => b.error);
  return <div id="errorBanner" className="banner" role="status" hidden={!failed || !error}>{error}</div>;
}

function JumpLatest() {
  const jump = useStore(feedBadge, (b) => b.jump), unread = useStore(feedBadge, (b) => b.unread);
  return (
    <button type="button" id="jumpLatest" className="jump-latest" hidden={!jump} onClick={() => feed.scrollToLatest(true)}>
      <span id="jumpLabel">{unread ? `${unread} new` : 'Latest'}</span><Slot name="down" />
    </button>
  );
}

export function ChatPane() {
  const pane = useRef<HTMLElement>(null);
  useEffect(() => swipeBack(pane.current!), []);
  useEffect(() => {
    const app = document.getElementById('app')!, f = document.getElementById('feed')!, form = document.getElementById('broadcastForm')!;
    const chips = document.getElementById('agentChips')!, top = document.getElementById('topbar')!;
    // Opening search, a growing draft or the keyboard shrinks the feed: stay pinned to the latest message.
    // A hidden pane measures 0 throughout: its insets keep what they were until it shows again.
    const hidden = () => pane.current!.offsetHeight === 0;
    const pin = new ResizeObserver(() => {
      if (hidden()) return;
      app.style.setProperty('--dock-h', `${form.offsetHeight}px`);
      if (feed.stick) f.scrollTop = f.scrollHeight;
      const tf = document.getElementById('threadFeed');
      if (threadFeed.stick && tf) tf.scrollTop = tf.scrollHeight;
    });
    pin.observe(f); pin.observe(form); pin.observe(document.getElementById('messages')!);
    // The floating agent row's height is the feed's top inset (0 where the row is not shown, e.g. wide screens).
    const orbs = new ResizeObserver(() => { if (!hidden()) app.style.setProperty('--orbs-h', `${chips.offsetHeight}px`); });
    orbs.observe(chips);
    // On a phone the top bar floats over the feed (it hides on scroll), so the feed keeps an inset of its height.
    const bar = new ResizeObserver(() => { if (!hidden()) app.style.setProperty('--top-h', `${isDesktop() ? 0 : top.offsetHeight}px`); });
    bar.observe(top);
    return () => { pin.disconnect(); orbs.disconnect(); bar.disconnect(); };
  }, []);
  return (
    <main className="pane chat-pane" id="chatPane" ref={pane}>
      <Ambience painting />
      <Topbar />
      <Banner />
      <Feed />
      <div className="thread-scrim" id="threadScrim" hidden />
      <ThreadView />
      <div className="dock" id="dock">
        <JumpLatest />
        <Composer />
      </div>
    </main>
  );
}
