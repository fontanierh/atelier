// Navigation, as in a native iOS app. A conversation or a thread pushes in from the right over the screen it came from,
// which drifts a third of the way left under a dim. The back button, a swipe right from anywhere on the screen and the
// browser's own back all pop it. A swipe follows the finger and is released onto a spring that keeps the flick's
// speed, so a quick flick finishes fast and a slow drag that stops short settles back.
//
// The panes are React's; the motion is not. Moving screens are styled directly (transform, translate, clip-path),
// which React never touches, and every move settles on time even if the browser never reports an animation finished.
import {flushSync} from 'react-dom';
import {feed, waitFor} from './lib/feed';
import {isView, VIEWS, type View} from './lib/format';
import {isDesktop, reducedMotion, standalone} from './lib/media';
import {board, refresh} from './store/board';
import {composer, setRecipient} from './store/composer';
import {loadInbox} from './store/inbox';
import {clearThread, setThread, thread, type OpenThread} from './store/thread';
import {filterKey, ui, type Mode} from './store/ui';

const $ = (id: string) => document.getElementById(id)!;
const PARALLAX = .3, DIM = .24;
const springs = CSS.supports?.('animation-timing-function', 'linear(0, 1)') ?? false;

interface Entry { kind: 'dm' | 'thread'; from?: View; underlay?: HTMLElement | null }
const nav: Entry[] = [];
let moving: Promise<void> | null = null, backEntry = false, ignorePops = 0, historyTimer = 0;
export const navDepth = () => nav.length;
export const top = () => nav.at(-1);
export const isMoving = () => moving !== null;

/* App-level state lives on #app itself (React renders inside it), as the stylesheet and the scene expect. */
export const appClass = (name: string, on: boolean) => $('app').classList.toggle(name, on);
export const currentView = (): View => { const v = $('app').dataset.view; return isView(v) ? v : 'messages'; };

// A critically damped spring, sampled into a CSS linear() easing so the compositor runs it. Its starting velocity is
// in fractions of the remaining distance per second, and it never overshoots: a screen can't bounce past the edge.
export function spring(velocity = 0): {easing: string; duration: number} {
  if (!springs) return {easing: 'cubic-bezier(.32, .72, 0, 1)', duration: 500};
  const w = 2 * Math.PI / .42, at = (t: number) => Math.min(1, 1 + (-1 + (velocity - w) * t) * Math.exp(-w * t));
  let end = 1 / 60;
  while (end < 1 && at(end) < .999) end += 1 / 120;
  const points: number[] = [];
  for (let i = 0; i <= 40; i++) points.push(i === 40 ? 1 : +at(end * i / 40).toFixed(4));
  return {easing: `linear(${points.join(', ')})`, duration: Math.round(end * 1000)};
}

export interface Scene {
  entry: Entry; top: HTMLElement; under: HTMLElement[]; scrim: HTMLElement; left: number; width: number;
  boxes: {left: number; right: number}[];
}
// What moves: the pushed screen on top, what it covers underneath, and the dim between them.
export function scene(entry: Entry): Scene {
  // A thread opened from Threads or Activity lies over a still copy of that list, not over the conversation.
  const parts = entry.kind === 'thread'
    ? {top: $('threadView'), under: entry.underlay ? [entry.underlay] : [$('topbar'), $('feed'), $('errorBanner')], scrim: $('threadScrim')}
    : {top: $('chatPane'), under: entry.underlay ? [entry.underlay] : [], scrim: $('navScrim')};
  const r = parts.top.getBoundingClientRect();
  return {entry, ...parts, left: r.left, width: parts.top.offsetWidth,
    boxes: parts.under.map((n) => { const b = n.getBoundingClientRect(); return {left: b.left, right: b.right}; })};
}
// p is how far the top screen has gone: 0 covers everything, 1 is off to the right. The screen underneath and the dim
// are clipped to the strip the top screen has not yet covered: a see-through screen (over the scenery) then never
// shows the one beneath it, and nothing changes in the frame where the move ends and that screen is hidden. They move
// by `translate`, which adds to their own transform (the top bar tucked away while scrolling) instead of replacing it.
const strip = (right: number, cut: number) =>
  `polygon(-200px -200px, ${right - cut}px -200px, ${right - cut}px calc(100% + 200px), -200px calc(100% + 200px))`;
function frame(s: Scene, p: number) {
  const edge = s.left + p * s.width, shift = -(1 - p) * PARALLAX * s.width;
  return {
    top: {transform: `translate3d(${p * s.width}px,0,0)`},
    under: s.boxes.map((b) => ({translate: `${shift}px 0`,
      clipPath: strip(b.right - b.left, Math.min(b.right - b.left, Math.max(0, b.right + shift - edge)))})),
    scrim: {opacity: String((1 - p) * DIM), clipPath: strip(s.width, (1 - p) * s.width)},
  };
}
export function paint(s: Scene, p: number): void {
  const f = frame(s, p);
  s.top.style.transform = f.top.transform;
  s.under.forEach((n, i) => { n.style.translate = f.under[i]!.translate; n.style.clipPath = f.under[i]!.clipPath; });
  s.scrim.style.opacity = f.scrim.opacity; s.scrim.style.clipPath = f.scrim.clipPath;
}
// Only this scene's layers take part: a conversation's still copy stays hidden while a thread moves over it.
export function begin(s: Scene): void {
  appClass('navigating', true); appClass('over-list', s.entry.kind === 'thread' && Boolean(s.entry.underlay)); s.top.classList.add('nav-top');
  for (const n of s.under) n.classList.add('nav-under');
  s.scrim.hidden = false;
}
export function end(s: Scene): void {
  appClass('navigating', false); appClass('over-list', false); s.top.classList.remove('nav-top');
  for (const n of s.under) n.classList.remove('nav-under');
  s.scrim.hidden = true;
  for (const n of [s.top, ...s.under, s.scrim]) { n.style.transform = n.style.translate = n.style.opacity = n.style.clipPath = ''; }
}
export function glide(s: Scene, from: number, to: number, velocity = 0): Promise<void> {
  const {easing, duration} = reducedMotion() ? {easing: 'linear', duration: 1} : spring(velocity);
  const a = frame(s, from), b = frame(s, to);
  paint(s, to);
  const runs = [s.top.animate([a.top, b.top], {duration, easing}),
    ...s.under.map((n, i) => n.animate([a.under[i]!, b.under[i]!], {duration, easing})),
    s.scrim.animate([a.scrim, b.scrim], {duration, easing})];
  // Settle on time even if the browser never reports an animation finished, so nothing stays mid-transition.
  const done = Promise.race([Promise.all(runs.map((r) => r.finished.catch(() => undefined))),
    new Promise((resolve) => setTimeout(resolve, duration + 250))])
    .then(() => { for (const r of runs) r.cancel(); moving = null; });
  moving = done;
  return done;
}

// A still copy of the screen a conversation was opened from. It sits underneath while the conversation is open and is
// what a swipe back reveals, so the live pane can switch to the conversation without losing the screen behind it.
function still(pane: HTMLElement): HTMLElement {
  const copy = pane.cloneNode(true) as HTMLElement, selector = '.feed, .pane-body, .orbs';
  const scrollers = [...pane.querySelectorAll<HTMLElement>(selector)], drafts = [...pane.querySelectorAll('textarea')];
  copy.removeAttribute('id');
  copy.querySelectorAll('[id]').forEach((n) => n.removeAttribute('id'));
  copy.classList.remove('entering'); copy.classList.add('nav-underlay');
  copy.inert = true; copy.setAttribute('aria-hidden', 'true');
  copy.querySelectorAll('textarea').forEach((n, i) => { n.value = drafts[i]?.value || ''; });
  $('navScrim').before(copy);
  copy.querySelectorAll<HTMLElement>(selector).forEach((n, i) => {
    n.scrollTop = scrollers[i]?.scrollTop || 0; n.scrollLeft = scrollers[i]?.scrollLeft || 0;
  });
  return copy;
}

// The browser keeps one history entry while anything is pushed, so the system back (Android, a desktop browser, or
// Safari's own edge swipe in a tab) pops the board instead of leaving it.
function syncHistory(): void {
  clearTimeout(historyTimer);
  historyTimer = window.setTimeout(() => {
    if (nav.length && !backEntry) { history.pushState({board: 'pushed'}, ''); backEntry = true; }
    else if (!nav.length && backEntry) { backEntry = false; ignorePops++; history.back(); }
  });
}
addEventListener('popstate', () => {
  if (ignorePops) { ignorePops--; return; }
  if (!backEntry) return;
  backEntry = false;
  // Safari in a tab has already animated its own snapshot of the previous screen; animating again would play it twice.
  navBack({instant: !standalone || isDesktop()});
});
function navPush(entry: Entry): void { nav.push(entry); syncHistory(); }
// The app closed a screen itself: drop it (and anything above it) from the stack.
function navForget(kind: Entry['kind']): void {
  const index = nav.findLastIndex((e) => e.kind === kind);
  if (index < 0) return;
  for (const e of nav.splice(index)) e.underlay?.remove();
  syncHistory();
}

// A short entrance (on a wide screen, instead of a slide); the class goes once its own animation has played.
export function enter(nodes: HTMLElement[], name: string): void {
  for (const n of nodes) {
    n.classList.remove(name); void n.offsetWidth; n.classList.add(name);
    const done = (event: AnimationEvent) => {
      if (event.target !== n) return;
      n.classList.remove(name); n.removeEventListener('animationend', done);
    };
    n.addEventListener('animationend', done);
  }
}

const PANES: Record<View, string> = {messages: 'chatPane', threads: 'threadsPane', activity: 'activityPane',
  tasks: 'tasksPane', agents: 'agentsPane', render: 'renderPane'};

/* Views: one pane at a time on phones, all side by side on wide screens. */
export function setView(next: View, animate = true): void {
  const app = $('app'), from = VIEWS.indexOf(currentView()), to = VIEWS.indexOf(next);
  app.dataset.view = next;
  ui.set({view: next});
  if (from !== to && animate && !isDesktop()) {
    const pane = $(PANES[next]);
    pane.style.setProperty('--dir', String(to > from ? 1 : -1));
    pane.classList.remove('entering'); void pane.offsetWidth; pane.classList.add('entering');
    setTimeout(() => pane.classList.remove('entering'), 900);
  }
  // Coming back to the conversation lands on its latest message and keeps following new ones.
  // The pane lays out again as it shows, and the moves that causes are not the reader scrolling away.
  if (next === 'messages') { feed.stick = true; feed.settle(600); requestAnimationFrame(() => feed.scrollToLatest()); }
  if (next === 'threads' && from !== to && animate) threadsOrder.reset = true;
  if (next === 'threads' || next === 'activity') loadInbox(next);
}
/** Threads keeps its order while on screen; coming back to it brings the current order. */
export const threadsOrder = {reset: false};

export function selectAgent(name: string, mode: Mode = 'dm', view: View = 'messages', animate = true): void {
  if (thread.get().open) closeThread();
  if (!name) navForget('dm');
  const before = filterKey(ui.get());
  flushSync(() => ui.set({agent: name, mode}));
  const state = board.get().state, agent = state?.agents.find((a) => a.agent === name && !a.stop);
  const target = name === '' ? '*' : agent ? name : null;
  if (target && composer.get().recipient !== target) setRecipient(target);
  setView(view, animate);
  if (filterKey(ui.get()) !== before) changedFilters();
}
/** The conversation or a filter changed: it paints afresh from its own answer. */
export function changedFilters(): void {
  feed.settle(1500); feed.stick = true; feed.painted = false;
  refresh();
}

export function openAgent(name: string): void {
  const u = ui.get();
  if (name === u.agent) { if (thread.get().open) navBack(); setView('messages'); return; }
  if (!name) {
    const entry = top();
    if (entry?.kind === 'dm' && entry.from === 'messages') navBack(); else selectAgent('');
    return;
  }
  if (u.agent) { selectAgent(name); return; }
  pushConversation(name);
}

async function pushConversation(name: string): Promise<void> {
  if (thread.get().open) closeThread();
  const from = currentView(), animate = !isDesktop() && !reducedMotion();
  const entry: Entry = {kind: 'dm', from, underlay: animate ? still($(from === 'agents' ? 'agentsPane' : 'chatPane')) : null};
  navPush(entry);
  selectAgent(name, 'dm', 'messages', !animate);
  if (!animate) return;
  const s = scene(entry);
  begin(s); paint(s, 1);
  // Push once the conversation has painted, as a native app pushes a ready screen, but never keep a tap waiting long.
  await waitFor(() => feed.painted, 260);
  if (top() !== entry) { end(s); return; }
  await glide(s, 1, 0);
  end(s);
}

/** Pop the top screen. A swipe hands over its scene, position and speed; the browser's back asks for no animation. */
export async function navBack({scene: given = null as Scene | null, from = 0, velocity = 0, instant = false} = {}): Promise<void> {
  const entry = top();
  if (!entry) { if (given) end(given); return; }
  const open = thread.get().open;
  const animate = !instant && !reducedMotion() && !isDesktop() && !(entry.kind === 'thread' && open?.origin && !entry.underlay);
  let s = given;
  if (animate) {
    if (!s) { if (moving) return; s = scene(entry); begin(s); }
    await glide(s, from, 1, velocity);
  }
  if (entry.kind === 'thread') {
    closeThread();
    if (s) end(s);
    else if (isDesktop() && !instant && !reducedMotion()) enter([$('topbar'), $('feed')], 'view-in');
    return;
  }
  const underlay = entry.underlay;
  entry.underlay = null;
  selectAgent('', 'dm', entry.from ?? 'messages', false);
  // The live pane stays off to the right, behind the still copy, until the full conversation has painted again.
  if (entry.from === 'messages' && s) await waitFor(() => feed.painted, 1200);
  if (s) end(s);
  underlay?.remove();
}

/* Thread view: the original and every reply, with the composer replying in the thread. */
export async function openThread(id: number, focus = false, origin: OpenThread['origin'] = '', underlay: HTMLElement | null = null): Promise<void> {
  const current = thread.get().open, nested = Boolean(current);
  const saved = nested ? current!.savedRecipient : composer.get().recipient;
  flushSync(() => setThread(id, nested ? current!.origin : origin, focus, saved));
  appClass('in-thread', true);
  if (nested) { underlay?.remove(); return; }
  const entry: Entry = {kind: 'thread', underlay};
  navPush(entry);
  // A wide screen opens the thread in place over the conversation, which steps out of sight; a phone pushes it, over
  // the conversation or over the list it came from.
  if (isDesktop() || (origin && !underlay)) { if (!reducedMotion()) enter([$('threadView')], 'thread-in'); return; }
  if (reducedMotion() || moving) return;
  const s = scene(entry);
  begin(s); paint(s, 1);
  await waitFor(() => thread.get().open?.data, 220);
  if (thread.get().open && top() === entry) {
    await glide(s, 1, 0);
    // The feed behind is out of sight now, so it can settle on the latest message without anyone seeing it move.
    feed.scrollToLatest();
  }
  end(s);
}

export function closeThread(): void {
  const open = thread.get().open;
  if (!open) return;
  clearThread();
  navForget('thread');
  appClass('in-thread', false);
  const names = new Set((board.get().state?.agents || []).filter((a) => !a.stop).map((a) => a.agent));
  if ((open.savedRecipient === '*' || names.has(open.savedRecipient)) && composer.get().recipient !== open.savedRecipient) {
    setRecipient(open.savedRecipient);
  }
  feed.stick = true;
  requestAnimationFrame(() => feed.scrollToLatest());
  if (open.origin && currentView() === 'messages') setView(open.origin, false);
}

export function openFromInbox(id: number, focus = false): void {
  const from = currentView(), origin = from === 'threads' || from === 'activity' ? from : '';
  // On a phone the thread pushes over a still copy of the list, so a swipe right goes back to it.
  const underlay = origin && !thread.get().open && !isDesktop() && !reducedMotion() && !moving ? still($(PANES[origin])) : null;
  setView('messages', false);
  openThread(id, focus, origin, underlay);
}

/** A notification links to /?m=ID, that message's thread, or /?task=ID, the Tasks page. */
export function openLink(url: string): void {
  const params = new URL(url, location.href).searchParams;
  if (params.has('task')) { setView('tasks'); return; }
  const id = Number(params.get('m'));
  if (!(id > 0)) return;
  setView('messages');
  if (thread.get().open?.id !== id) { if (thread.get().open) closeThread(); openThread(id); }
}

/* Swipe back: from the left edge, or (as on iOS 26) a rightward drag anywhere that isn't on something that scrolls
   sideways or takes text. A mostly vertical drag stays a scroll. */
export function swipeBack(pane: HTMLElement): () => void {
  let swipe: {entry: Entry; x: number; y: number; axis: 'x' | 'y' | null; samples: [number, number][]; scene: Scene | null} | null = null;
  const start = (event: TouchEvent) => {
    const entry = top();
    if (event.touches.length !== 1 || !entry || moving || isDesktop() || (entry.kind === 'dm' && !entry.underlay)
      || (entry.kind === 'thread' && thread.get().open?.origin && !entry.underlay)) return;
    const t = event.touches[0]!, target = event.target as Element;
    if (t.clientX > 24 && target.closest('textarea, input, select, pre, table, video, audio, .orbs, .dock, .attachments')) return;
    swipe = {entry, x: t.clientX, y: t.clientY, axis: null, samples: [[t.clientX, event.timeStamp]], scene: null};
  };
  const move = (event: TouchEvent) => {
    if (!swipe) return;
    if (event.touches.length !== 1) { cancel(event); return; }
    const t = event.touches[0]!, dx = t.clientX - swipe.x, dy = t.clientY - swipe.y;
    if (!swipe.axis) {
      if (Math.hypot(dx, dy) < 10) return;
      swipe.axis = dx > 0 && Math.abs(dx) > Math.abs(dy) * 1.2 ? 'x' : 'y';
      if (swipe.axis === 'y' || top() !== swipe.entry || moving) { swipe = null; return; }
      swipe.scene = scene(swipe.entry); begin(swipe.scene);
    }
    event.preventDefault();
    swipe.samples.push([t.clientX, event.timeStamp]);
    if (swipe.samples.length > 8) swipe.samples.shift();
    paint(swipe.scene!, Math.max(0, Math.min(1, dx / swipe.scene!.width)));
  };
  const cancel = (event: TouchEvent) => {
    const s = swipe;
    swipe = null;
    if (!s?.scene) return;
    const last = s.samples.at(-1)!, recent = s.samples.filter(([, at]) => at >= last[1] - 100), [x0, t0] = recent[0]!;
    const speed = last[1] > t0 ? (last[0] - x0) / (last[1] - t0) * 1000 : 0;
    const p = Math.max(0, Math.min(1, (last[0] - s.x) / s.scene.width));
    const done = event.type === 'touchend' && (speed > 350 || (speed > -350 && p > .5));
    const remaining = (done ? 1 - p : p) * s.scene.width, velocity = remaining > 1 ? (done ? speed : -speed) / remaining : 0;
    if (done) navBack({scene: s.scene, from: p, velocity});
    else glide(s.scene, p, 0, velocity).then(() => end(s.scene!));
  };
  pane.addEventListener('touchstart', start, {passive: true});
  pane.addEventListener('touchmove', move, {passive: false});
  pane.addEventListener('touchend', cancel);
  pane.addEventListener('touchcancel', cancel);
  return () => {
    pane.removeEventListener('touchstart', start); pane.removeEventListener('touchmove', move);
    pane.removeEventListener('touchend', cancel); pane.removeEventListener('touchcancel', cancel);
  };
}

/** Back from a conversation: the stack if something is pushed, else everyone. */
export function back(): void { if (nav.length) navBack(); else selectAgent(''); }


