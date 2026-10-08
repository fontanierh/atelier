// The app around the panes: the tab bar, what sits over the board (photo, reader, action sheet, drop hint), and the
// page-level wiring (viewport, keys, links from notifications, coming back from the background).
import {Component, useEffect, useLayoutEffect, useRef, useState, type ReactNode} from 'react';
import {feed, feedBadge} from '../lib/feed';
import {VIEWS, type View} from '../lib/format';
import {isDesktop, isTouch} from '../lib/media';
import {navBack, openLink, setView} from '../nav';
import {board, resume} from '../store/board';
import {addFiles} from '../store/composer';
import {loadInbox} from '../store/inbox';
import {closePhoto, closeReader, overlay} from '../store/overlay';
import {useStore} from '../store/store';
import {loadThread, thread} from '../store/thread';
import {ui} from '../store/ui';
import {Ambience, ChatPane} from './Chat';
import {ActivityPane, inboxKeyboardFit, ThreadsPane} from './Inbox';
import {AgentsPane, RenderPane, TasksPane} from './Panes';
import {Markdown, Slot} from './bits';
import type {IconName} from './Icon';

/** A pane that fails to render shows a card in its place instead of taking the board down with it, and tries again
 *  by itself with the board's next update (or at once, with the button). */
export class Guard extends Component<{name: string; id: string; className: string; children: ReactNode}, {error: Error | null}> {
  state = {error: null as Error | null};
  private failed = 0;
  private stop: (() => void) | null = null;
  static getDerivedStateFromError(error: Error) { return {error}; }
  componentDidCatch(error: Error) { this.failed = Date.now(); console.error(`The ${this.props.name} view failed`, error); }
  componentDidMount() {
    this.stop = board.subscribe(() => { if (this.state.error && Date.now() - this.failed > 5000) this.setState({error: null}); });
  }
  componentWillUnmount() { this.stop?.(); }
  render() {
    if (!this.state.error) return this.props.children;
    return (
      <section className={this.props.className} id={this.props.id}>
        <div className="empty pane-error" role="alert"><Slot name="board" />
          <h2>{`${this.props.name} hit a snag`}</h2>
          <p>The rest of the board is fine. This view will try again in a moment.</p>
          <button type="button" className="text-button" onClick={() => this.setState({error: null})}>Try again</button>
        </div>
      </section>
    );
  }
}

const TABS: {view: View; icon: IconName; label: string}[] = [
  {view: 'messages', icon: 'messages', label: 'Messages'}, {view: 'threads', icon: 'thread', label: 'Threads'},
  {view: 'activity', icon: 'activity', label: 'Activity'}, {view: 'tasks', icon: 'tasks', label: 'Tasks'},
  {view: 'agents', icon: 'agents', label: 'Agents'}, {view: 'render', icon: 'render', label: 'Render'},
];
const count = (n: number) => (n > 99 ? '99+' : String(n));

function pick(view: View): void {
  if (view === 'messages' && ui.get().view === 'messages') { if (thread.get().open) navBack(); else feed.scrollToLatest(true); }
  setView(view);
}

/** Slide along the tab bar to switch views: the highlight follows the thumb and the view under it opens on release.
 *  A tap still works as a tap; a drag that leaves the bar upwards is a cancel. */
function useScrub(bar: React.RefObject<HTMLElement | null>): void {
  useEffect(() => {
    const el = bar.current!;
    let s: {x: number; y: number; on: boolean; at: number; from: number} | null = null;
    const slot = (x: number) => {
      const r = el.getBoundingClientRect(), f = (x - r.left - 4) / (r.width - 8) * VIEWS.length;
      return Math.max(0, Math.min(VIEWS.length - 1, f - .5));
    };
    const start = (event: TouchEvent) => {
      if (event.touches.length !== 1) return;
      const t = event.touches[0]!;
      s = {x: t.clientX, y: t.clientY, on: false, at: -1, from: VIEWS.indexOf(ui.get().view)};
    };
    const move = (event: TouchEvent) => {
      if (!s) return;
      const t = event.touches[0]!, dx = t.clientX - s.x, dy = t.clientY - s.y;
      if (!s.on) {
        if (Math.abs(dx) < 10 || Math.abs(dx) < Math.abs(dy)) { if (Math.abs(dy) > 14) s = null; return; }
        s.on = true;
        el.classList.add('scrubbing');
      }
      event.preventDefault();
      const at = slot(t.clientX), index = Math.round(at);
      el.style.setProperty('--tab', at.toFixed(3));
      if (index !== s.at) {
        s.at = index;
        el.querySelectorAll<HTMLElement>('.tab').forEach((tab, i) => tab.classList.toggle('scrub-over', i === index));
        navigator.vibrate?.(6);
      }
    };
    const finish = (event: TouchEvent) => {
      const g = s;
      s = null;
      if (!g?.on) return;
      el.classList.remove('scrubbing');
      el.querySelectorAll('.tab.scrub-over').forEach((tab) => tab.classList.remove('scrub-over'));
      const t = event.changedTouches[0], r = el.getBoundingClientRect();
      const kept = event.type === 'touchend' && t && t.clientY > r.top - 40;
      event.preventDefault();   // no click after a slide
      const to = kept ? VIEWS[g.at] : undefined;
      el.style.setProperty('--tab', String(VIEWS.indexOf(to ?? ui.get().view)));
      if (to && to !== ui.get().view) setView(to);
    };
    el.addEventListener('touchstart', start, {passive: true});
    el.addEventListener('touchmove', move, {passive: false});
    el.addEventListener('touchend', finish);
    el.addEventListener('touchcancel', finish);
    return () => {
      el.removeEventListener('touchstart', start); el.removeEventListener('touchmove', move);
      el.removeEventListener('touchend', finish); el.removeEventListener('touchcancel', finish);
    };
  }, [bar]);
}

function Tabbar() {
  const view = useStore(ui, (u) => u.view), unread = useStore(feedBadge, (b) => b.unread);
  const state = useStore(board, (b) => b.state), dismissed = useStore(board, (b) => b.dismissed);
  const bar = useRef<HTMLElement>(null);
  useScrub(bar);
  useLayoutEffect(() => { bar.current?.style.setProperty('--tab', String(VIEWS.indexOf(view))); }, [view]);
  const live = (state?.agents || []).filter((a) => !a.stop), errors = live.filter((a) => a.delivery_error).length;
  const tasks = (state?.tasks || []).filter((t) => !dismissed.has(t.id)).length;
  const jobs = state ? Object.values(state.holders).filter(Boolean).length : 0;
  const away = view !== 'messages' && !isDesktop();
  const badges: Record<View, number> = {messages: away ? unread : 0, threads: state?.inbox.threads || 0,
    activity: state?.inbox.activity || 0, tasks, agents: errors, render: 0};
  return (
    <nav className="tabbar glass" id="tabbar" aria-label="Views" ref={bar}>
      <span className="tab-indicator" aria-hidden="true" />
      {TABS.map((tab) => (
        <button key={tab.view} type="button" className="tab" data-view={tab.view} aria-current={view === tab.view ? 'page' : undefined}
          onClick={() => pick(tab.view)}>
          <Slot name={tab.icon} /><span>{tab.label}</span>
          {tab.view === 'render'
            ? <span className="tab-dot" id="renderBadge" hidden={!jobs} />
            : <span className={`tab-badge${tab.view === 'agents' ? ' warn' : ''}`} id={`${tab.view}Badge`} hidden={!badges[tab.view]}>{count(badges[tab.view])}</span>}
        </button>
      ))}
    </nav>
  );
}

function Lightbox() {
  const photo = useStore(overlay, (o) => o.photo), close = useRef<HTMLButtonElement>(null);
  useEffect(() => { if (photo) close.current?.focus(); }, [photo]);
  return (
    <div className="lightbox" id="lightbox" role="dialog" aria-modal="true" aria-label="Photo" hidden={!photo}
      onClick={(event) => { if (!(event.target as Element).closest('#lightboxOpen')) closePhoto(); }}>
      {photo && <img id="lightboxImage" src={photo.url} alt={photo.name} />}
      <div className="lightbox-bar"><span id="lightboxName">{photo?.name}</span>
        <a id="lightboxOpen" href={photo?.url} target="_blank" rel="noopener noreferrer">Open original</a></div>
      <button ref={close} type="button" className="round-button lightbox-close" id="lightboxClose" aria-label="Close"><Slot name="close" /></button>
    </div>
  );
}

/** Markdown and text attachments open in a reader over the board (rendered by the server) instead of downloading.
 *  While it is open the rest of the board is inert, so Tab and screen readers stay inside it, and the meadow rests. */
function Reader() {
  const reader = useStore(overlay, (o) => o.reader), box = useRef<HTMLDivElement>(null), close = useRef<HTMLButtonElement>(null);
  const back = useRef<Element | null>(null), open = Boolean(reader);
  useLayoutEffect(() => {
    const app = document.getElementById('app')!;
    if (!open) return;
    back.current = document.activeElement;
    const behind = [...app.children].filter((el): el is HTMLElement => el instanceof HTMLElement && el !== box.current && !el.inert);
    for (const el of behind) el.inert = true;
    app.classList.add('reader-open');
    close.current?.focus();
    return () => {
      for (const el of behind) el.inert = false;
      app.classList.remove('reader-open');
      (back.current as HTMLElement | null)?.focus?.();
    };
  }, [open]);
  useEffect(() => { if (reader?.file) box.current?.querySelector('.reader-body')?.scrollTo(0, 0); }, [reader?.file]);
  return (
    <div className="reader" id="reader" role="dialog" aria-modal="true" aria-labelledby="readerTitle" hidden={!reader} ref={box}
      onClick={(event) => { if (event.target === event.currentTarget) closeReader(); }}
      onKeyDown={(event) => {
        // Tab and Shift+Tab wrap around the reader's own controls and links.
        if (event.key !== 'Tab') return;
        const stops = [...event.currentTarget.querySelectorAll<HTMLElement>("a[href],button:not(:disabled),[tabindex]:not([tabindex='-1'])")]
          .filter((el) => el.getClientRects().length);
        const first = stops[0], last = stops.at(-1);
        if (!first || !last) return;
        if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
        else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
      }}>
      <article className="reader-card">
        <header className="reader-head">
          <Slot name="file" /><h2 id="readerTitle">{reader?.file.name}</h2>
          <a className="text-button" id="readerOpen" href={reader?.file.url} download={reader?.file.name}>Download</a>
          <button ref={close} type="button" className="round-button" id="readerClose" aria-label="Close" onClick={closeReader}><Slot name="close" /></button>
        </header>
        <div className="reader-body" id="readerBody">
          {reader && (reader.html !== null ? <Markdown html={reader.html} /> : <p className="quiet">{reader.status}</p>)}
        </div>
      </article>
    </div>
  );
}

function Sheet() {
  const sheet = useStore(overlay, (o) => o.sheet), [shown, setShown] = useState(false), [visible, setVisible] = useState(false);
  const cancel = useRef<HTMLButtonElement>(null), last = useRef(sheet);
  if (sheet) last.current = sheet;
  useEffect(() => {
    if (sheet) {
      setVisible(true);
      const frame = requestAnimationFrame(() => { setShown(true); cancel.current?.focus(); });
      return () => cancelAnimationFrame(frame);
    }
    setShown(false);
    const timer = setTimeout(() => setVisible(false), 260);
    return () => clearTimeout(timer);
  }, [sheet]);
  const finish = (ok: boolean) => { const s = overlay.get().sheet; overlay.set({sheet: null}); s?.resolve(ok); };
  const s = last.current;
  return (
    <div className={`sheet-backdrop${shown ? ' shown' : ''}`} id="sheet" hidden={!visible} onClick={(event) => { if (event.target === event.currentTarget) finish(false); }}>
      <div className="sheet" role="alertdialog" aria-modal="true" aria-labelledby="sheetTitle" aria-describedby="sheetText">
        <div className="sheet-card"><h2 id="sheetTitle">{s?.title}</h2><p id="sheetText">{s?.text}</p>
          <button type="button" className="sheet-danger" id="sheetConfirm" onClick={() => finish(true)}>{s?.action}</button></div>
        <button ref={cancel} type="button" className="sheet-cancel" id="sheetCancel" onClick={() => finish(false)}>Cancel</button>
      </div>
    </div>
  );
}

function DropHint() {
  const [on, setOn] = useState(false);
  useEffect(() => {
    let depth = 0;
    const files = (event: DragEvent) => [...(event.dataTransfer?.types || [])].includes('Files');
    const enter = (event: DragEvent) => { if (files(event)) { depth++; setOn(true); } };
    const leave = () => { if (--depth <= 0) { depth = 0; setOn(false); } };
    const over = (event: DragEvent) => { if (files(event)) event.preventDefault(); };
    const drop = (event: DragEvent) => {
      if (!event.dataTransfer?.files?.length) return;
      event.preventDefault(); depth = 0; setOn(false);
      setView('messages'); addFiles([...event.dataTransfer.files]);
    };
    addEventListener('dragenter', enter); addEventListener('dragleave', leave);
    addEventListener('dragover', over); addEventListener('drop', drop);
    return () => {
      removeEventListener('dragenter', enter); removeEventListener('dragleave', leave);
      removeEventListener('dragover', over); removeEventListener('drop', drop);
    };
  }, []);
  return <div className="drop-hint" id="dropHint" hidden={!on}><Slot name="plus" />Drop files to attach</div>;
}

/** The app shell follows the visual viewport so the composer stays above the on-screen keyboard. */
function useViewport(): void {
  useEffect(() => {
    let full = 0, width = 0, keyboard = false;
    const fit = () => {
      const vv = window.visualViewport, root = document.documentElement.style, height = vv ? vv.height : innerHeight;
      root.setProperty('--app-height', `${height}px`); root.setProperty('--app-top', `${vv ? vv.offsetTop : 0}px`);
      if (innerWidth !== width) { width = innerWidth; full = height; }
      full = Math.max(full, height);
      // A keyboard dismissed without leaving the field (Android back, iOS "Done") should bring the tab bar back.
      const open = full - height > 120, message = document.getElementById('message');
      if (keyboard && !open && isTouch() && document.activeElement === message) message?.blur();
      keyboard = open;
      inboxKeyboardFit();
    };
    window.visualViewport?.addEventListener('resize', fit);
    window.visualViewport?.addEventListener('scroll', fit);
    addEventListener('resize', fit);
    fit();
    return () => {
      window.visualViewport?.removeEventListener('resize', fit);
      window.visualViewport?.removeEventListener('scroll', fit);
      removeEventListener('resize', fit);
    };
  }, []);
}

// iOS freezes the app in the background, and a request caught mid-flight may never settle, which used to block every
// later refresh until the app was killed. Coming back always starts over: the board, the open thread and the inbox.
function comeBack(): void {
  if (document.hidden) return;
  resume();
  if (thread.get().open) loadThread(true);
  const view = ui.get().view;
  if (view === 'threads' || view === 'activity') loadInbox(view, true);
}

function usePage(): void {
  useEffect(() => {
    const app = document.getElementById('app')!;
    const key = (event: KeyboardEvent) => {
      if (event.key !== 'Escape') return;
      const o = overlay.get();
      if (o.reader) closeReader(); else if (o.photo) closePhoto(); else if (thread.get().open) navBack();
    };
    // A window behind others holds its looping animations where they are, as the scene does. A toggle that changes
    // nothing records no mutation, which the scene's class observer relies on.
    const rest = () => app.classList.toggle('at-rest', document.hidden || !document.hasFocus());
    const shown = (event: PageTransitionEvent) => { if (event.persisted) comeBack(); };
    const focus = () => { comeBack(); rest(); };
    addEventListener('keydown', key);
    document.addEventListener('visibilitychange', comeBack);
    document.addEventListener('visibilitychange', rest);
    addEventListener('pageshow', shown);
    addEventListener('focus', focus);
    addEventListener('blur', rest);
    addEventListener('online', comeBack);
    rest();
    // A notification links to /?m=ID, that message's thread, or /?task=ID, the Tasks page; whether the app was closed or open.
    const worker = (event: MessageEvent) => { if (event.data?.open) openLink(event.data.open); };
    navigator.serviceWorker?.addEventListener('message', worker);
    return () => {
      removeEventListener('keydown', key);
      document.removeEventListener('visibilitychange', comeBack); document.removeEventListener('visibilitychange', rest);
      removeEventListener('pageshow', shown); removeEventListener('focus', focus); removeEventListener('blur', rest);
      removeEventListener('online', comeBack);
      navigator.serviceWorker?.removeEventListener('message', worker);
    };
  }, []);
  // The link a notification opened the app with, once the board has answered.
  const ready = useStore(board, (b) => Boolean(b.state));
  useEffect(() => {
    if (!ready) return;
    const params = new URLSearchParams(location.search);
    if (params.has('m') || params.has('task')) { openLink(location.href); history.replaceState(history.state, '', '/'); }
  }, [ready]);
}

export function App() {
  useViewport();
  usePage();
  // Opening Threads or Activity shows what it had at once and refreshes it; each poll refreshes the one on screen.
  const time = useStore(board, (b) => b.state?.time), view = useStore(ui, (u) => u.view);
  useEffect(() => { if (view === 'threads' || view === 'activity') loadInbox(view); }, [time, view]);
  return <>
    <Ambience />
    <Guard name="Agents" id="agentsPane" className="pane agents-pane"><AgentsPane /></Guard>
    <div className="nav-scrim" id="navScrim" hidden />
    <Guard name="Messages" id="chatPane" className="pane chat-pane"><ChatPane /></Guard>
    <Guard name="Threads" id="threadsPane" className="pane inbox-pane threads-pane"><ThreadsPane /></Guard>
    <Guard name="Activity" id="activityPane" className="pane inbox-pane activity-pane"><ActivityPane /></Guard>
    <Guard name="Tasks" id="tasksPane" className="pane tasks-pane"><TasksPane /></Guard>
    <Guard name="Render floor" id="renderPane" className="pane render-pane"><RenderPane /></Guard>
    <Tabbar />
    <Lightbox />
    <Reader />
    <Sheet />
    <DropHint />
  </>;
}
