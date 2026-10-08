// The Agents, Tasks and Render panes.
import {memo, useEffect, useRef, useState} from 'react';
import {api, message} from '../api/client';
import type {Agent, OperatorTask, State} from '../api/schema';
import {isFree, isWaiting, quietFor} from '../lib/agents';
import {agentStatus, clock, entries, idleLine, since, snippet} from '../lib/format';
import {desktop, reducedMotion, standalone, useMedia} from '../lib/media';
import {closeThread, navBack, openAgent, openThread, selectAgent, setView, top} from '../nav';
import {board, dismissLocally, load} from '../store/board';
import {confirmSheet} from '../store/overlay';
import {useStore} from '../store/store';
import {thread} from '../store/thread';
import {ui} from '../store/ui';
import {Inline, Markdown, Orb, Slot} from './bits';
import {sortedAgents} from './Chat';
import {Icon} from './Icon';
import {ReplyBox} from './ReplyBox';

/* ---- Agents ---- */

/** The status line under an agent's name: idle, waiting on you, or what it says it is doing. */
function TaskLine({agent, state, dismissed}: {agent: Agent; state: State; dismissed: ReadonlySet<number>}) {
  if (isFree(agent, state, dismissed)) {
    // A quiet session whose line still names work shows that line as the last thing it said it was doing.
    return (
      <span className="agent-task" title={idleLine(agent) ? undefined : `Quiet for ${Math.floor(quietFor(agent, state.time) / 60)} min; its status line may be stale`}>
        <span className="free-tag">Idle</span>{idleLine(agent) ? ' No task' : ` Last: ${agent.task}`}
      </span>
    );
  }
  if (isWaiting(agent, state, dismissed)) {
    return <span className="agent-task"><span className="waiting-tag">Waiting on you</span>{idleLine(agent) ? '' : ` ${agent.task}`}</span>;
  }
  if (agent.session === 'busy' && idleLine(agent)) return <span className="agent-task">Working (no status line)</span>;
  return agent.task ? <span className="agent-task">{agent.task}</span> : null;
}

async function removeAgent(name: string, cell: HTMLElement | null, close: () => void): Promise<void> {
  const agent = board.get().state?.agents.find((a) => a.agent === name);
  const ok = await confirmSheet(`Remove ${name}?`, `${name} leaves the board and stops receiving messages${agent?.pending
    ? `, including ${agent.pending} still queued` : ''}. Its messages stay in the history, and it comes back if it subscribes again.`, `Remove ${name}`);
  if (!ok) { close(); return; }
  try {
    await api.remove(name);
    if (cell) { cell.style.height = `${cell.offsetHeight}px`; cell.classList.add('leaving'); }
    if (ui.get().agent === name) { if (top()?.kind === 'dm') navBack(); else selectAgent(''); }
    setTimeout(load, 280);
  } catch (error) {
    close();
    board.set({failed: true, error: message(error, 'Could not remove the agent.')});
  }
}

/** Removing an agent: swipe its row left (or hover it with a mouse) to show Remove, then confirm on an action sheet. */
function useRowSwipe(list: React.RefObject<HTMLElement | null>): void {
  useEffect(() => {
    const box = list.current!;
    let swipe: {cell: HTMLElement; row: HTMLElement; x: number; y: number; axis: 'x' | 'y' | null; base: number; dx: number} | null = null;
    const close = (except?: Element | null) => {
      let closed = false;
      box.querySelectorAll<HTMLElement>('.agent-cell.open').forEach((cell) => {
        if (cell === except) return;
        cell.classList.remove('open');
        cell.querySelector<HTMLElement>('.agent-row')!.style.transform = '';
        closed = true;
      });
      return closed;
    };
    (box as HTMLElement & {closeSwiped?: typeof close}).closeSwiped = close;
    const start = (event: TouchEvent) => {
      const target = event.target as Element, cell = target.closest<HTMLElement>('.agent-cell');
      if (event.touches.length !== 1 || !cell?.querySelector('.agent-remove') || target.closest('.agent-remove')) return;
      const t = event.touches[0]!;
      swipe = {cell, row: cell.querySelector('.agent-row')!, x: t.clientX, y: t.clientY, axis: null,
        base: cell.classList.contains('open') ? -92 : 0, dx: 0};
    };
    const move = (event: TouchEvent) => {
      if (!swipe) return;
      const t = event.touches[0]!, dx = t.clientX - swipe.x, dy = t.clientY - swipe.y;
      if (!swipe.axis) {
        if (Math.hypot(dx, dy) < 8) return;
        swipe.axis = Math.abs(dx) > Math.abs(dy) ? 'x' : 'y';
        if (swipe.axis === 'y') { swipe = null; return; }
        close(swipe.cell); swipe.row.style.transition = 'none';
      }
      event.preventDefault();
      let x = swipe.base + dx;
      if (x > 0) x = 0;
      if (x < -92) x = -92 + (x + 92) / 3;   // resists past the button, like a native list
      swipe.dx = dx; swipe.row.style.transform = `translateX(${x}px)`;
    };
    const end = () => {
      const s = swipe;
      swipe = null;
      if (!s || s.axis !== 'x') return;
      s.row.style.transition = '';
      const open = s.base + s.dx < -46;
      s.cell.classList.toggle('open', open);
      s.row.style.transform = open ? 'translateX(-92px)' : '';
    };
    const outside = (event: PointerEvent) => { if (!(event.target as Element).closest('.agent-cell.open')) close(); };
    box.addEventListener('touchstart', start, {passive: true});
    box.addEventListener('touchmove', move, {passive: false});
    box.addEventListener('touchend', end); box.addEventListener('touchcancel', end);
    document.addEventListener('pointerdown', outside, {capture: true});
    return () => {
      box.removeEventListener('touchstart', start); box.removeEventListener('touchmove', move);
      box.removeEventListener('touchend', end); box.removeEventListener('touchcancel', end);
      document.removeEventListener('pointerdown', outside, {capture: true});
    };
  }, [list]);
}

const closeSwiped = (list: HTMLElement | null) =>
  (list as (HTMLElement & {closeSwiped?: () => boolean}) | null)?.closeSwiped?.() ?? false;

const AgentRow = memo(function AgentRow({name, agent, index, chosen, state, dismissed, list}: {
  name: string; agent?: Agent | undefined; index: number; chosen: boolean; state: State; dismissed: ReadonlySet<number>;
  list: React.RefObject<HTMLElement | null>;
}) {
  const cell = useRef<HTMLDivElement>(null);
  return (
    <div ref={cell} className="agent-cell" role="listitem" data-agent={name} style={{'--i': index} as React.CSSProperties}>
      {agent && (
        // Behind the row, revealed by swiping it left (or shown on hover with a mouse): take an evicted agent off the board.
        <button type="button" className="agent-remove" aria-label={`Remove ${name}`}
          onClick={(event) => { event.stopPropagation(); removeAgent(name, cell.current, () => closeSwiped(list.current)); }}>
          <Icon name="remove" /><span>Remove</span>
        </button>
      )}
      <button type="button" className={`agent-row${agent?.stop ? ' retired' : ''}${agent && agent.unread > 0 ? ' unread' : ''}`}
        aria-current={chosen ? 'true' : undefined} onClick={() => { if (!closeSwiped(list.current)) openAgent(name); }}>
        <Orb name={name || '*'} agent={agent} />
        <span className="agent-text">
          <span className="agent-name">{name || 'Everyone'}</span>
          {agent && <TaskLine agent={agent} state={state} dismissed={dismissed} />}
          <span className="agent-detail">
            {agent ? <>
              <span className={`state ${agent.delivery_error ? 'error' : agent.listening ? 'live' : 'idle'}`}>{agentStatus(agent)}</span>
              {[!agent.supervised && !agent.stop ? 'no auto-recovery' : '', agent.checkout || ''].filter(Boolean).map((part) => ` · ${part}`).join('')}
            </> : 'Broadcasts and every conversation'}
          </span>
        </span>
        {agent?.pending ? <span className="count">{`${agent.pending} queued`}</span> : null}
        <Icon name="right" />
      </button>
    </div>
  );
}, (a, b) => a.name === b.name && a.index === b.index && a.chosen === b.chosen && a.dismissed === b.dismissed
  && JSON.stringify(a.agent) === JSON.stringify(b.agent) && Math.floor(a.state.time / 60) === Math.floor(b.state.time / 60)
  && (a.state.tasks.length === b.state.tasks.length));

/* Notifications: an agent flags a message with board post --notify-operator, this device gets it as a push, and
   tapping it opens that message's thread. */
const pushSupported = 'serviceWorker' in navigator && 'PushManager' in window && 'Notification' in window;
function unb64(text: string): Uint8Array {
  const raw = atob(text.replace(/-/g, '+').replace(/_/g, '/') + '='.repeat((4 - text.length % 4) % 4));
  return Uint8Array.from(raw, (c) => c.charCodeAt(0));
}

const THEMES: Record<string, string> = {auto: 'Auto', light: 'Light', dark: 'Dark'};
type BoardTheme = {choice: string; dark: boolean; set: (choice: string) => void};
const boardTheme = () => (window as Window & {boardTheme?: BoardTheme}).boardTheme;

function Settings() {
  const ready = useStore(board, (b) => Boolean(b.state));
  const [theme, setTheme] = useState(() => ({choice: boardTheme()?.choice || 'auto', dark: Boolean(boardTheme()?.dark)}));
  const [push, setPush] = useState({on: false, enabled: false, busy: false});
  const [note, setNote] = useState('Only when an agent flags something for you.');
  const [playful, setPlayful] = useState(true), registration = useRef<ServiceWorkerRegistration | null>(null);
  const details = useRef<HTMLDetailsElement>(null);
  useEffect(() => {
    const changed = () => setTheme({choice: boardTheme()?.choice || 'auto', dark: Boolean(boardTheme()?.dark)});
    addEventListener('boardtheme', changed);
    const toggle = document.getElementById('playfulToggle') as HTMLInputElement | null;
    setPlayful(toggle?.checked ?? true);
    return () => removeEventListener('boardtheme', changed);
  }, []);
  // Set up once the board has answered, as the old page did.
  useEffect(() => {
    if (!ready) return;
    (async () => {
      if (!pushSupported) {
        setNote(/iPhone|iPad/.test(navigator.userAgent) && !standalone
          ? 'To get notifications, add the board to your Home Screen (Share, then Add to Home Screen) and open it from there.'
          : 'This browser can’t show notifications.');
        return;
      }
      try { registration.current = await navigator.serviceWorker.register('/sw.js'); } catch { setNote('Notifications aren’t available here.'); return; }
      const subscription = await registration.current.pushManager.getSubscription(), on = Boolean(subscription) && Notification.permission === 'granted';
      setPush({on, enabled: true, busy: false});
      // Re-register an existing subscription, in case the board lost it.
      if (on && subscription) api.pushSubscribe(subscription.toJSON()).catch(() => undefined);
      if (Notification.permission === 'denied') setNote('Notifications are turned off for the board in Settings.');
    })();
  }, [ready]);
  async function toggleNotifications(on: boolean): Promise<void> {
    const reg = registration.current;
    if (!reg) return;
    setPush({on, enabled: true, busy: true});
    try {
      if (on) {
        if (await Notification.requestPermission() !== 'granted') throw new Error('Allow notifications for the board to turn them on.');
        const {key} = await api.pushKey();
        const subscription = await reg.pushManager.getSubscription()
          || await reg.pushManager.subscribe({userVisibleOnly: true, applicationServerKey: unb64(key) as BufferSource});
        await api.pushSubscribe(subscription.toJSON());
        setNote('On. Agents notify you only when you’ve asked to be told, or it’s urgent.');
      } else {
        const subscription = await reg.pushManager.getSubscription();
        if (subscription) { await api.pushUnsubscribe(subscription.endpoint); await subscription.unsubscribe(); }
        setNote('Off. Flagged messages still appear on the board.');
      }
      setPush({on, enabled: true, busy: false});
    } catch (error) {
      setPush({on: !on, enabled: true, busy: false});
      setNote(message(error));
    }
  }
  const themeNote = theme.choice === 'auto' ? `Follows this device: ${theme.dark ? 'dark' : 'light'} now.`
    : theme.choice === 'dark' ? 'The meadow by moonlight.' : 'The misty morning meadow.';
  // Settings fold away under Agents; their row says how they are set.
  const summary = [`Notifications ${push.on ? 'on' : 'off'}`, playful ? 'Playful' : 'Calm', THEMES[theme.choice] || 'Auto'].join(' · ');
  return (
    <details className="settings" id="settings" ref={details}
      onChange={() => setPlayful((document.getElementById('playfulToggle') as HTMLInputElement | null)?.checked ?? true)}
      onToggle={() => {
        if (details.current?.open) requestAnimationFrame(() => details.current?.scrollIntoView({block: 'end', behavior: reducedMotion() ? 'instant' : 'smooth'}));
      }}>
      <summary><Slot name="board" /><span className="settings-text"><b>Settings</b><small id="settingsSummary">{summary}</small></span><Slot name="chevron" /></summary>
      <div className="settings-body">
        <section className="card notify-card" aria-labelledby="themeHeading">
          <div className="notify-text"><h2 id="themeHeading">Appearance</h2><p id="themeNote">{themeNote}</p></div>
          <div className="mode-switch theme-switch" role="group" aria-labelledby="themeHeading">
            {Object.entries(THEMES).map(([value, label]) => (
              <button key={value} type="button" data-theme-choice={value} aria-pressed={theme.choice === value}
                onClick={() => boardTheme()?.set(value)}>{label}</button>
            ))}
          </div>
        </section>
        <section className="card notify-card" aria-labelledby="notifyHeading">
          <div className="notify-row">
            <div className="notify-text"><h2 id="notifyHeading">Notifications</h2><p id="notifyNote">{note}</p></div>
            <label className="toggle">
              <input type="checkbox" id="notifyToggle" aria-label="Notifications on this device" disabled={!push.enabled || push.busy}
                checked={push.on} onChange={(event) => toggleNotifications(event.target.checked)} />
              <span className="toggle-track" />
            </label>
          </div>
          <button type="button" className="text-button" id="notifyTest" hidden={!push.on || push.busy} onClick={async () => {
            try {
              const result = await api.pushTest();
              setNote(result.delivered ? 'Test sent; it should arrive in a moment.' : 'No device received it. Turn notifications off and on again.');
            } catch (error) { setNote(message(error)); }
          }}>Send a test notification</button>
        </section>
        <section className="card notify-card" aria-labelledby="playfulHeading">
          <div className="notify-row">
            {/* The playful layer (board-fx.js) owns this switch and its note. */}
            <div className="notify-text"><h2 id="playfulHeading">Playful motion</h2><p id="playfulNote">Comets, fireworks and a living meadow.</p></div>
            <label className="toggle"><input type="checkbox" id="playfulToggle" aria-label="Playful motion on this device" defaultChecked /><span className="toggle-track" /></label>
          </div>
        </section>
      </div>
    </details>
  );
}

export function AgentsPane() {
  const state = useStore(board, (b) => b.state), dismissed = useStore(board, (b) => b.dismissed);
  const chosen = useStore(ui, (u) => u.agent), counts = state?.inbox, view = useStore(ui, (u) => u.view);
  const list = useRef<HTMLDivElement>(null);
  useRowSwipe(list);
  const live = (state?.agents || []).filter((a) => !a.stop), listening = live.filter((a) => a.listening).length;
  const errors = live.filter((a) => a.delivery_error).length, free = live.filter((a) => isFree(a, state, dismissed)).length;
  return (
    <aside className="pane agents-pane" id="agentsPane" aria-label="Agents">
      <header className="pane-head">
        <div className="wordmark">Atelier<small>Agent board</small></div>
        <h1>Agents</h1>
        <p className="pane-sub" id="agentsSummary">{state ? `${listening} of ${live.length} listening${free ? ` · ${free} idle` : ''}${errors ? ` · ${errors} retrying delivery` : ''}` : 'Loading'}</p>
      </header>
      <div className="pane-body">
        <nav className="inbox-nav" aria-label="Your threads and activity">
          {(['threads', 'activity'] as const).map((v) => {
            const n = counts?.[v] || 0;
            return (
              <button key={v} type="button" className="inbox-link" data-view={v} aria-current={view === v ? 'page' : undefined}
                onClick={() => { if (thread.get().open) closeThread(); setView(v); }}>
                <Slot name={v === 'threads' ? 'thread' : 'activity'} /><span>{v === 'threads' ? 'Threads' : 'Activity'}</span>
                <span className="inbox-count" id={`${v}Count`} hidden={!n}>{n > 99 ? '99+' : n}</span>
              </button>
            );
          })}
        </nav>
        <div id="agents" className="agent-list" role="list" ref={list}>
          {state && <AgentRow name="" index={0} chosen={chosen === ''} state={state} dismissed={dismissed} list={list} />}
          {state && sortedAgents(state, dismissed).map((a, i) => (
            <AgentRow key={a.agent} name={a.agent} agent={a} index={i + 1} chosen={chosen === a.agent} state={state} dismissed={dismissed} list={list} />
          ))}
        </div>
        <p className="pane-note">Tap an agent to open your conversation with them.</p>
        <Settings />
      </div>
    </aside>
  );
}

/* ---- Tasks ---- */

/** An agent blocked on the operator asks once, and the Tasks page holds the ask until someone dismisses it. The reply
 *  being typed survives the board's refreshes. */
function TaskCard({task, state}: {task: OperatorTask; state: State}) {
  const [leaving, setLeaving] = useState(false), [busy, setBusy] = useState(false), [error, setError] = useState('');
  const r = task.last_reply;
  return (
    <article className={`card task-card${leaving ? ' leaving' : ''}`} role="listitem">
      <header className="task-head">
        <Orb name={task.agent} agent={state.agents.find((a) => a.agent === task.agent)} />
        <span className="task-who"><b>{task.agent}</b><span className="task-age">{` · ${since(task.asked, state.time)}${task.edited ? ' · edited' : ''}`}</span></span>
        <button type="button" className="text-button task-thread" onClick={() => { setView('messages'); openThread(task.message); }}>
          <span>Thread</span><Icon name="right" />
        </button>
      </header>
      <Markdown className="task-body" html={task.body_html} raw={task.body} />
      <p className="task-last" hidden={!r}>{r ? `${r.sender === state.sender ? 'You' : r.sender}: ${snippet(r.body)} · ${since(r.created, state.time)}` : ''}</p>
      <ReplyBox label={`Reply to ${task.agent}`} placeholder={`Reply to ${task.agent}…`} className="task-reply"
        onSend={async (text, key) => {
          await api.send({body: text, topic: 'info', recipient: task.agent, request_id: key, reply_to: task.message});
          load();
          return task.agent;
        }} />
      {error && <p className="task-status error" role="status">{error}</p>}
      <button type="button" className="text-button task-dismiss" disabled={busy} onClick={async () => {
        setBusy(true); setError('');
        try {
          await api.dismissTask(task.id);
          setLeaving(true);
          setTimeout(() => { dismissLocally(task.id); load(); }, reducedMotion() ? 0 : 220);
        } catch (e) { setError(message(e)); setBusy(false); }
      }}>Dismiss</button>
    </article>
  );
}

export function TasksPane() {
  const state = useStore(board, (b) => b.state), dismissed = useStore(board, (b) => b.dismissed), wide = useMedia(desktop);
  // A snapshot already in flight when a task was dismissed must not bring its card back.
  const list = (state?.tasks || []).filter((t) => !dismissed.has(t.id)), n = list.length, who = new Set(list.map((t) => t.agent)).size;
  useEffect(() => { document.getElementById('app')!.classList.toggle('has-tasks', n > 0); }, [n]);
  return (
    <aside className="pane tasks-pane" id="tasksPane" aria-labelledby="tasksHeading">
      <header className="pane-head"><h1 id="tasksHeading">Tasks</h1>
        <p className="pane-sub" id="tasksSummary">{n ? `${who} ${who === 1 ? 'agent is' : 'agents are'} waiting on you` : 'Nobody is waiting on you'}</p>
      </header>
      <div className="pane-body">
        <div id="tasks" className="task-list" role="list">
          {state && list.map((t) => <TaskCard key={t.id} task={t} state={state} />)}
        </div>
        <p className="pane-note" id="tasksNote" hidden={n > 0 && wide}>When an agent can’t go on without your answer or OK, it asks here. Reply in place, or dismiss it.</p>
      </div>
    </aside>
  );
}

/* ---- Render floor ---- */

const BLURBS: Record<string, string> = {Holding: 'Nobody is holding a render slot.', Waiting: 'Nobody is waiting for a slot.',
  Handoffs: 'No handoffs recorded.', Log: 'No log entries yet.'};

function Schedule({state}: {state: State}) {
  const shown = useStore(ui, (u) => u.logShown);
  return <div id="scheduleView" className="stack">
    {['Holding', 'Waiting', 'Handoffs', 'Log'].map((title, i) => {
      let items = entries(state.schedule[title]);
      if (title === 'Log') items = items.reverse();
      const total = title === 'Log' ? state.log_total ?? items.length : items.length;
      return (
        <details key={title} className="card schedule-card" open={title !== 'Handoffs' ? true : undefined} style={{'--i': i + 3} as React.CSSProperties}>
          <summary><span>{title}</span><span className="count-pill">{String(total)}</span><Icon name="chevron" /></summary>
          {!items.length ? <p className="quiet">{BLURBS[title]}</p> : <>
            <ul className="entries">{(title === 'Log' ? items.slice(0, shown) : items).map((item, k) => <li key={k}><Inline text={item} /></li>)}</ul>
            {/* The server sends only the newest entries the page shows; older ones arrive on request. */}
            {title === 'Log' && total > shown && (
              <button type="button" className="text-button" onClick={() => { ui.set({logShown: shown + 30}); load({reset: true}); }}>
                {`Show ${Math.min(30, total - shown)} older entries`}
              </button>
            )}
          </>}
        </details>
      );
    })}
  </div>;
}

const text = (value: unknown) => (typeof value === 'string' ? value : value == null ? '' : String(value));

export function RenderPane() {
  const state = useStore(board, (b) => b.state);
  const jobs = state ? Object.entries(state.holders).filter(([, h]) => h) as [string, NonNullable<State['holders']['big']>][] : [];
  const r = state?.resources;
  return (
    <aside className="pane render-pane" id="renderPane" aria-label="Render floor">
      <header className="pane-head"><h1>Render floor</h1>
        <p className="pane-sub" id="renderSummary">{!state ? 'Checking live jobs' : jobs.length ? `${jobs.map(([slot]) => slot).join(' + ')} slot busy` : 'Both slots free'}</p>
      </header>
      <div className="pane-body">
        <section className="card" aria-labelledby="liveHeading" style={{'--i': 0} as React.CSSProperties}>
          <h2 className="eyebrow" id="liveHeading">Running now</h2>
          <div id="liveJobs">
            {jobs.map(([slot, holder]) => (
              <div key={slot} className="job">
                <div className="job-label"><span className="dot live" /><span>{`${slot} slot`}</span>
                  <span className="job-since">{typeof holder.time === 'number' ? `since ${clock(holder.time)}` : ''}</span></div>
                <div className="job-purpose">{text(holder.purpose)}</div><div className="job-checkout">{holder.checkout}</div>
              </div>
            ))}
            {state && !jobs.length && <p className="quiet">The render floor is clear.</p>}
          </div>
          <div className="resources" id="resourceLine">{r && <>
            <span>{r.fresh && r.cpu != null ? `CPU ${Math.round(r.cpu)}%` : 'CPU · no telemetry'}</span>
            <span>{r.fresh && r.available_gib != null ? `${r.available_gib.toFixed(1)} GiB free` : 'Memory · no telemetry'}</span>
          </>}</div>
        </section>
        <section className="stack" aria-labelledby="scheduleHeading">
          <h2 className="eyebrow" id="scheduleHeading" style={{'--i': 1} as React.CSSProperties}>Schedule</h2>
          {state && <Schedule state={state} />}
        </section>
        <section className="stack" aria-labelledby="sessionsHeading">
          <h2 className="eyebrow" id="sessionsHeading" style={{'--i': 2} as React.CSSProperties}>Remote sessions</h2>
          <div className="card list-card" id="sessions" style={{'--i': 3} as React.CSSProperties}>
            {state?.sessions.map((s, i) => {
              const online = s.fresh && s.connection === 'connected' && s.health === 'healthy';
              return (
                <a key={i} className="session" href={s.url} target="_blank" rel="noopener noreferrer">
                  <span className="session-name"><span className={`dot${online ? ' live' : ''}`} /><span>{text(s.name) || `Session ${i + 1}`}</span></span>
                  <span className="session-state">{!s.fresh ? 'Status stale' : online ? 'Online'
                    : text(s.health).startsWith('recovery_deferred') ? 'Recovery waiting' : 'Reconnecting'}</span>
                  <Icon name="right" />
                </a>
              );
            })}
            {state && !state.sessions.length && <p className="quiet">No remote session monitor configured.</p>}
          </div>
        </section>
        <p className="pane-note" id="lastUpdated">{state ? `Live · last synced ${clock(state.time)} · updates every 3 seconds` : 'Waiting for the first update'}</p>
      </div>
    </aside>
  );
}
