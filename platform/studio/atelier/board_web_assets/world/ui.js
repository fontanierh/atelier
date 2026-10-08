// Everything you read and write in the village is plain HTML over the scene: name tags, the thumb strip, the sheet
// (a thread or "Needs you"), the composer and the media viewer. Gestures follow networking's map (#7591): one owner
// per surface, a broad strip for paging and sheet sizes, native scrolling for text, the envelope for writing. A
// cancelled or interrupted gesture never sends, marks read, changes a recipient or loses a draft.
import {focus as focusScene, inset as insetScene} from "/world/board_world.js";

const $ = (id) => document.getElementById(id);
const el = (tag, cls, text) => { const n = document.createElement(tag); if (cls) n.className = cls; if (text != null) n.textContent = text; return n; };
const SLOP = 10, COMMIT = 48, LIFT = 64, CARD = 64;
const DETENTS = ["peek", "half", "full"], INSETS = {peek: 0.3, half: 0.52, full: 0.86};
const DRAFT_KEY = "atelier.world.draft", OPERATOR = "operator", TAUGHT_KEY = "atelier.world.taught";
const store = {
  get(key) { try { return JSON.parse(localStorage.getItem(key) || "null"); } catch { return null; } },
  set(key, value) { try { value == null ? localStorage.removeItem(key) : localStorage.setItem(key, JSON.stringify(value)); } catch { /* private mode */ } },
};

const S = {
  me: "operator", csrf: "", agents: new Map(), order: [], focus: -1,
  mode: "village", detent: "peek", needsIndex: 0, needs: [],
  threads: new Map(), tasks: [], draft: store.get(DRAFT_KEY), back: null,
};

// --- Small helpers -------------------------------------------------------------------------------------------------
function ago(seconds) {
  const s = Math.max(0, Date.now() / 1000 - seconds);
  return s < 60 ? "now" : s < 3600 ? `${Math.floor(s / 60)}m` : s < 86400 ? `${Math.floor(s / 3600)}h` : `${Math.floor(s / 86400)}d`;
}
const focused = () => S.order[S.focus] ?? null;
let swallowClickUntil = 0;
document.addEventListener("click", (e) => { if (performance.now() < swallowClickUntil) { e.preventDefault(); e.stopPropagation(); } }, true);

function request(path, body) {
  return fetch(path, body === undefined ? {cache: "no-store"} : {
    method: "POST", cache: "no-store", body: JSON.stringify(body),
    headers: {"Content-Type": "application/json", "X-Board-CSRF": S.csrf},
  }).then(async (r) => {
    const data = await r.json().catch(() => null);
    if (!r.ok) throw new Error(data?.error || `${r.status}`);
    return data;
  });
}

/** One-axis drag recognizer: picks an axis after a little movement and keeps it until release or cancellation. */
function drag(target, {move, commit, cancel, start}) {
  let id = null, x0 = 0, y0 = 0, t0 = 0, axis = null;
  const reset = () => { id = null; axis = null; };
  const abort = () => { if (id !== null) { reset(); cancel?.(); } };
  target.addEventListener("pointerdown", (e) => {
    if (id !== null) { abort(); return; } // a second finger cancels
    if (start && start(e) === false) return;
    id = e.pointerId; x0 = e.clientX; y0 = e.clientY; t0 = performance.now(); axis = null;
  });
  target.addEventListener("pointermove", (e) => {
    if (e.pointerId !== id) return;
    const dx = e.clientX - x0, dy = e.clientY - y0;
    if (!axis) {
      if (Math.hypot(dx, dy) < SLOP) return;
      axis = Math.abs(dx) > Math.abs(dy) ? "x" : "y";
      try { target.setPointerCapture(id); } catch { /* already gone */ }
    }
    move?.(axis, axis === "x" ? dx : dy, dx, dy, e);
  });
  target.addEventListener("pointerup", (e) => {
    if (e.pointerId !== id) return;
    const dx = e.clientX - x0, dy = e.clientY - y0, ms = performance.now() - t0, held = axis;
    reset();
    if (!held) { cancel?.(); return; }
    swallowClickUntil = performance.now() + 350;
    const d = held === "x" ? dx : dy, fast = Math.abs(d) / Math.max(ms, 1) > 0.5 && Math.abs(d) > 24;
    if (Math.abs(d) >= COMMIT || fast) commit?.(held, Math.sign(d), dx, dy, e); else cancel?.();
  });
  for (const type of ["pointercancel", "lostpointercapture"]) target.addEventListener(type, (e) => { if (e.pointerId === id) abort(); });
  document.addEventListener("visibilitychange", abort);
}

// --- Name tags pinned to the homes ---------------------------------------------------------------------------------
const tags = new Map();
export function labels(json) {
  let rows;
  try { rows = JSON.parse(json); } catch { return; }
  const seen = new Set();
  const width = innerWidth, height = innerHeight;
  for (const [name, fx, fy] of rows) {
    seen.add(name);
    let tag = tags.get(name);
    if (!tag) {
      tag = el("button", "tag");
      tag.type = "button";
      tag.append(el("span", "dot"), el("span", "name", name === OPERATOR ? "You" : name));
      tag.addEventListener("click", () => { if (name === OPERATOR) openNeeds(); else { setFocus(S.order.indexOf(name)); openThread(); } });
      $("tags").append(tag);
      tags.set(name, tag);
    }
    const half = tag.offsetWidth / 2 + 8; // kept on screen, however close to the edge its house is
    const x = Math.round(Math.max(half, Math.min(width - half, fx / 10000 * width))), y = Math.round(fy / 10000 * height);
    tag.style.transform = `translate3d(${x}px, ${y}px, 0) translate(-50%, -100%)`;
  }
  for (const [name, tag] of tags) if (!seen.has(name)) { tag.remove(); tags.delete(name); }
  paintTags();
}
function paintTags() {
  for (const [name, tag] of tags) {
    const agent = S.agents.get(name);
    tag.classList.toggle("busy", Boolean(agent?.busy));
    tag.classList.toggle("focused", name === focused());
    tag.title = agent?.task || "";
  }
}

// --- Focus and the strip -------------------------------------------------------------------------------------------
function setFocus(index) {
  if (!S.order.length) return;
  S.focus = ((index % S.order.length) + S.order.length) % S.order.length;
  focusScene(focused() || "");
  paintTags(); paintStrip();
  if (S.mode === "thread") openThread(true);
}

function paintStrip(hint = "") {
  const n = S.order.length, name = focused();
  let label;
  if (S.mode === "needs") label = `Needs you · ${S.needs.length ? `${S.needsIndex + 1}/${S.needs.length}` : "all clear"}`;
  else if (S.mode === "thread") label = `Thread · ${name} · ${S.focus + 1}/${n}`;
  else label = name ? `Village · ${name} · ${S.focus + 1}/${n}` : `Village · ${n} agents`;
  $("stripLabel").textContent = label;
  const peek = (offset) => (S.mode === "needs" ? (S.needs[S.needsIndex + offset]?.title || "") : (n ? S.order[(S.focus + offset + n) % n] : ""));
  $("stripPrev").textContent = S.focus < 0 && S.mode !== "needs" ? "" : peek(-1);
  $("stripNext").textContent = S.focus < 0 && S.mode !== "needs" ? (S.order[0] || "") : peek(1);
  $("stripHint").textContent = hint;
  $("strip").classList.toggle("hinting", Boolean(hint));
}

function hintFor(axis, sign) {
  if (axis === "x") {
    if (S.mode === "needs") return sign < 0 ? "Next letter" : "Previous letter";
    const n = S.order.length; if (!n) return "";
    const to = S.order[(S.focus < 0 ? (sign < 0 ? 0 : n - 1) : S.focus - sign + n) % n];
    return `${sign < 0 ? "Next" : "Previous"}: ${to}`;
  }
  if (S.mode === "village") return sign < 0 ? "Open thread" : "Needs you";
  const at = DETENTS.indexOf(S.detent);
  if (sign < 0) return at < DETENTS.length - 1 ? "Expand" : "";
  return at > 0 ? "Lower" : "Back to village";
}

function step(axis, sign) {
  if (axis === "x") {
    if (S.mode === "needs") { S.needsIndex = Math.max(0, Math.min(S.needs.length - 1, S.needsIndex - sign)); paintNeeds(); paintStrip(); return; }
    setFocus(S.focus < 0 ? (sign < 0 ? 0 : S.order.length - 1) : S.focus - sign);
    return;
  }
  if (S.mode === "village") { sign < 0 ? openThread() : openNeeds(); return; }
  const at = DETENTS.indexOf(S.detent);
  if (sign < 0) { if (S.mode === "needs" && at === DETENTS.length - 1) openNeedsItem(); else setDetent(DETENTS[Math.min(at + 1, 2)]); }
  else if (at > 0) setDetent(DETENTS[at - 1]);
  else back();
}

function wireStrip(surface, active) {
  drag(surface, {
    start: () => active(),
    move: (axis, d) => {
      const armed = Math.abs(d) >= COMMIT;
      $("stripLabel").style.transform = axis === "x" ? `translateX(${d * 0.35}px)` : "";
      paintStrip(Math.abs(d) > SLOP * 2 ? hintFor(axis, Math.sign(d)) : "");
      $("strip").classList.toggle("armed", armed);
    },
    commit: (axis, sign) => { $("stripLabel").style.transform = ""; $("strip").classList.remove("armed"); step(axis, sign); paintStrip(); },
    cancel: () => { $("stripLabel").style.transform = ""; $("strip").classList.remove("armed"); paintStrip(); },
  });
}

// --- Modes, the sheet and history ----------------------------------------------------------------------------------
// Back only ever undoes something this page opened; it never leaves the village.
function back() {
  if (history.state?.world) history.back();
  else if (!$("lightbox").hidden) $("lightbox").hidden = true;
  else if ($("composer").classList.contains("open")) foldComposer();
  else if (S.mode !== "village") enter("village");
}
function enter(mode, detent = "half") {
  const was = S.mode;
  S.mode = mode;
  document.body.dataset.mode = mode;
  if (mode === "village") { $("sheet").hidden = true; insetScene(0); }
  else setDetent(detent);
  // One history entry for "a sheet is open", however many sheets you pass through, so Back always lands in the village.
  if (was === "village" && mode !== "village") history.pushState({world: "sheet"}, "");
  paintStrip();
}
function setDetent(detent) {
  S.detent = detent;
  const sheet = $("sheet");
  sheet.hidden = false;
  sheet.dataset.detent = detent;
  insetScene(INSETS[detent]);
}
// Back closes the topmost thing: the media viewer, then the letter (kept as a draft), then the sheet.
window.addEventListener("popstate", () => {
  if (!$("lightbox").hidden) { $("lightbox").hidden = true; return; }
  if ($("composer").classList.contains("open")) { foldComposer(); return; }
  if (S.mode !== "village") enter("village");
});

function openThread(keepDetent = false) {
  if (S.focus < 0) setFocus(0);
  const name = focused();
  if (!name) return;
  if (S.mode !== "thread") enter("thread", "half"); else if (!keepDetent) setDetent(S.detent);
  $("sheetTitle").textContent = name;
  $("sheetSub").textContent = S.agents.get(name)?.task || "";
  paintThread(true);
  loadThread(name);
}

async function loadThread(name, before = 0) {
  const thread = S.threads.get(name) || {messages: new Map(), more: true, loading: false};
  S.threads.set(name, thread);
  if (thread.loading) return;
  thread.loading = true;
  try {
    const q = new URLSearchParams({agent: name, limit: "60", log: "1"});
    if (before) q.set("before", String(before));
    const state = await request(`/api/state?${q}`);
    if (!Array.isArray(state?.messages)) throw new Error("bad thread");
    // What this agent said or was told, not every broadcast it overheard.
    for (const m of state.messages) if (m.sender === name || m.recipient === name) thread.messages.set(m.id, m);
    if (before || thread.more === true) thread.more = Boolean(state.has_more);
  } catch {
    // Keep what is already shown; the next refresh tries again.
  } finally {
    thread.loading = false;
    if (S.mode === "thread" && focused() === name) paintThread(!before);
  }
}

function media(attachments) {
  const box = el("div", "media");
  for (const a of attachments || []) {
    if (a.missing) continue;
    if (a.mime?.startsWith("image/")) {
      const img = el("img"); img.src = a.url; img.alt = a.name; img.loading = "lazy";
      if (a.width && a.height) { img.width = a.width; img.height = a.height; }
      img.addEventListener("click", () => openLightbox(a));
      box.append(img);
    } else if (a.mime?.startsWith("video/")) {
      const video = el("video"); video.src = a.url; video.controls = true; video.playsInline = true; video.preload = "metadata";
      box.append(video);
    } else {
      const link = el("a", "file", a.name); link.href = a.url; link.target = "_blank"; link.rel = "noopener";
      box.append(link);
    }
  }
  return box;
}

function messageCard(m) {
  const card = el("article", `msg${m.sender === S.me ? " mine" : ""}`);
  card.dataset.id = m.id;
  const head = el("header");
  head.append(el("b", "", m.sender === S.me ? "You" : m.sender), el("span", "to", `→ ${m.recipient === "*" ? "everyone" : m.recipient === S.me ? "you" : m.recipient}`),
              el("span", `topic ${m.topic}`, m.topic), el("time", "", ago(m.created)));
  const body = el("div", "body");
  body.innerHTML = m.body_html || ""; // the server's own sanitised Markdown, as on the classic board
  const reply = el("button", "reply", "Reply");
  reply.type = "button";
  reply.addEventListener("click", () => openComposer({to: replyTarget(m), replyTo: m}));
  card.append(head, body, media(m.attachments), reply);
  wireReplySwipe(card, m);
  return card;
}
const replyTarget = (m) => (m.sender === S.me ? (m.recipient === "*" ? null : m.recipient) : m.sender);

function wireReplySwipe(card, m) {
  drag(card, {
    start: (e) => !e.target.closest("a, button, img, video, pre, code") && !String(getSelection()).length,
    move: (axis, d) => { if (axis === "x" && d > 0) { card.style.transform = `translateX(${Math.min(d, 96)}px)`; card.classList.toggle("replying", d >= COMMIT); } },
    commit: (axis, sign) => { card.style.transform = ""; card.classList.remove("replying"); if (axis === "x" && sign > 0) openComposer({to: replyTarget(m), replyTo: m}); },
    cancel: () => { card.style.transform = ""; card.classList.remove("replying"); },
  });
}

function paintThread(stick) {
  const name = focused(), thread = S.threads.get(name);
  const scroller = $("sheetBody");
  const atBottom = scroller.scrollHeight - scroller.scrollTop - scroller.clientHeight < 40;
  const anchor = scroller.scrollHeight - scroller.scrollTop;
  scroller.replaceChildren();
  if (!thread || !thread.messages.size) { scroller.append(el("p", "empty", thread?.loading === false ? "No messages with this agent yet." : "Opening the letters…")); return; }
  if (thread.more) {
    const older = el("button", "older", "Load earlier");
    older.type = "button";
    older.addEventListener("click", () => loadThread(name, Math.min(...thread.messages.keys())));
    scroller.append(older);
  }
  for (const m of [...thread.messages.values()].sort((a, b) => a.id - b.id)) scroller.append(messageCard(m));
  // Arriving letters keep you at the newest one; reading older ones stays put while new ones land below.
  if (stick || atBottom) scroller.scrollTop = scroller.scrollHeight; else scroller.scrollTop = scroller.scrollHeight - anchor;
}

// --- Needs you -----------------------------------------------------------------------------------------------------
async function openNeeds() {
  enter("needs", "half");
  $("sheetTitle").textContent = "Needs you";
  $("sheetSub").textContent = "Open tasks and unread mentions";
  paintNeeds();
  try {
    const activity = await request("/api/activity?unread=1&limit=20");
    const letters = S.tasks.filter((t) => !t.closed).map((t) => ({kind: "task", title: `${t.agent} asks`, agent: t.agent, html: t.body_html || "", created: t.created, id: t.message}));
    for (const item of activity?.items || []) {
      const m = item.message || {};
      letters.push({kind: item.kind, title: `${m.sender} · ${item.kind}`, agent: m.sender, html: m.body_html || m.snippet || "", created: m.created, id: m.id});
    }
    S.needs = letters;
    S.needsIndex = Math.min(S.needsIndex, Math.max(0, letters.length - 1));
  } catch { /* keep the last list */ }
  if (S.mode === "needs") { paintNeeds(); paintStrip(); }
}
function paintNeeds() {
  const scroller = $("sheetBody");
  scroller.replaceChildren();
  if (!S.needs.length) { scroller.append(el("p", "empty", "Nothing needs you right now.")); return; }
  S.needs.forEach((letter, i) => {
    const card = el("button", `letter${i === S.needsIndex ? " current" : ""}`);
    card.type = "button";
    const head = el("header"); head.append(el("b", "", letter.title), el("time", "", ago(letter.created)));
    const body = el("div", "body"); body.innerHTML = letter.html;
    card.append(head, body);
    card.addEventListener("click", () => { S.needsIndex = i; openNeedsItem(); });
    scroller.append(card);
  });
  scroller.querySelector(".current")?.scrollIntoView({block: "nearest"});
}
function openNeedsItem() {
  const letter = S.needs[S.needsIndex];
  if (!letter) return;
  const index = S.order.indexOf(letter.agent);
  if (index < 0) return;
  setFocus(index);
  enter("thread", "full");
  openThread(true);
}

// --- The composer and the envelope ---------------------------------------------------------------------------------
function saveDraft() { store.set(DRAFT_KEY, S.draft); }

function openComposer({to = null, replyTo = null, picking = false} = {}) {
  // The recipient is frozen here: nothing that arrives later retargets an open draft.
  if (!S.draft || S.draft.sent || (replyTo && S.draft.reply_to !== replyTo.id) || (to && S.draft.recipient !== to && !S.draft.body)) {
    S.draft = {recipient: to, reply_to: replyTo?.id ?? null, quote: replyTo ? `${replyTo.sender}: ${replyTo.body.slice(0, 140)}` : "",
               body: "", topic: "request", request_id: crypto.randomUUID()};
  }
  saveDraft();
  const composer = $("composer");
  composer.classList.add("open");
  composer.hidden = false;
  paintComposer(picking || !S.draft.recipient);
  if (!$("sheet").hidden && S.mode === "village") $("sheet").hidden = true;
  history.pushState({world: "compose"}, "");
  // Focus now, inside the gesture, or iOS won't raise the keyboard.
  if (S.draft.recipient && !picking) $("composeText").focus({preventScroll: true});
}

function paintComposer(picking) {
  const d = S.draft;
  $("composeTo").textContent = d.recipient ? (d.recipient === "*" ? "Everyone" : d.recipient) : "Choose who";
  $("composeQuote").hidden = !d.quote;
  $("composeQuote").textContent = d.quote || "";
  $("composeText").value = d.body;
  for (const b of $("composeTopics").querySelectorAll("button")) b.setAttribute("aria-pressed", String(b.dataset.topic === d.topic));
  const picker = $("composePicker");
  picker.hidden = !picking;
  if (picking) {
    picker.replaceChildren();
    for (const name of [...S.order, "*"]) {
      const chip = el("button", `chip${name === d.recipient ? " on" : ""}`, name === "*" ? "Everyone" : name);
      chip.type = "button";
      chip.addEventListener("click", () => { d.recipient = name; saveDraft(); paintComposer(false); $("composeText").focus(); });
      picker.append(chip);
    }
  }
  $("composeSend").disabled = !d.recipient || !d.body.trim();
  $("composeStatus").textContent = "";
}

function foldComposer() {
  saveDraft();
  $("composer").classList.remove("open");
  $("composeText").blur();
  setTimeout(() => { if (!$("composer").classList.contains("open")) $("composer").hidden = true; }, 350);
  $("envelope").classList.toggle("has-draft", Boolean(S.draft?.body?.trim()));
}

async function send() {
  const d = S.draft;
  if (!d?.recipient || !d.body.trim()) return;
  const button = $("composeSend");
  button.disabled = true;
  $("composeStatus").textContent = "Sending…";
  try {
    await request("/api/send", {body: d.body, topic: d.topic, recipient: d.recipient, request_id: d.request_id,
                                attachments: [], reply_to: d.reply_to});
    d.sent = true;
    S.draft = null; saveDraft();
    $("envelope").classList.remove("has-draft");
    $("composeStatus").textContent = "Sent";
    back();
  } catch (error) {
    // Same request_id on retry, so a send whose answer was lost is never posted twice.
    $("composeStatus").textContent = `Not sent: ${error.message}. Your draft is kept.`;
    button.disabled = false;
    button.textContent = "Retry";
  }
}

function wireComposer() {
  $("composeText").addEventListener("input", (e) => { S.draft.body = e.target.value; saveDraft(); $("composeSend").disabled = !S.draft.recipient || !S.draft.body.trim(); $("composeSend").textContent = "Send"; });
  $("composeTopics").addEventListener("click", (e) => { const b = e.target.closest("button"); if (!b) return; S.draft.topic = b.dataset.topic; saveDraft(); paintComposer(false); });
  $("composeTo").addEventListener("click", () => paintComposer(true));
  $("composeSend").addEventListener("click", send);
  $("composeFold").addEventListener("click", () => back());
  drag($("composeHandle"), {move: (axis, d) => { if (axis === "y" && d > 0) $("composer").style.transform = `translateY(${d}px)`; },
                            commit: (axis, sign) => { $("composer").style.transform = ""; if (axis === "y" && sign > 0) back(); },
                            cancel: () => { $("composer").style.transform = ""; }});
}

/** Touch the envelope, slide to choose a recipient from big name cards, lift to unfold the letter. */
function wireEnvelope() {
  const envelope = $("envelope"), fan = $("fan");
  let id = null, x0 = 0, y0 = 0, base = 0, choice = null, slid = false, lifted = false;
  const names = () => [...S.order, "*"];
  const close = () => { fan.hidden = true; document.body.classList.remove("picking"); envelope.style.transform = ""; envelope.classList.remove("lifting"); id = null; };
  const paintFan = (index) => {
    const list = names();
    choice = list[index];
    fan.replaceChildren();
    for (let i = Math.max(0, index - 1); i <= Math.min(list.length - 1, index + 1); i++) {
      const card = el("div", `card${i === index ? " on" : ""}`, list[i] === "*" ? "Everyone" : list[i]);
      card.style.setProperty("--k", String(i - index));
      fan.append(card);
    }
    $("fanHint").textContent = `Write to ${choice === "*" ? "everyone" : choice} · lift`;
  };
  envelope.addEventListener("pointerdown", (e) => {
    if (id !== null) { close(); return; }
    if (document.body.classList.contains("first-use")) { document.body.classList.remove("first-use"); store.set(TAUGHT_KEY, true); }
    id = e.pointerId; x0 = e.clientX; y0 = e.clientY; slid = false; lifted = false;
    base = Math.max(0, S.focus); choice = focused();
    try { envelope.setPointerCapture(id); } catch { /* fine */ }
  });
  envelope.addEventListener("pointermove", (e) => {
    if (e.pointerId !== id) return;
    const dx = e.clientX - x0, dy = e.clientY - y0;
    if (!slid && Math.abs(dx) > SLOP * 1.4 && Math.abs(dx) > Math.abs(dy)) { slid = true; fan.hidden = false; document.body.classList.add("picking"); }
    const lifting = dy < -SLOP * 2.4; // once the letter lifts, sideways drift no longer changes who it is for
    if (slid && !lifting) paintFan(Math.max(0, Math.min(names().length - 1, base + Math.round(dx / CARD))));
    lifted = dy < -LIFT;
    envelope.classList.toggle("lifting", lifted);
    envelope.style.transform = `translate(${slid ? 0 : dx * 0.2}px, ${Math.min(0, dy) * 0.5}px) rotate(${Math.max(-8, dy / -12)}deg)`;
  });
  envelope.addEventListener("pointerup", (e) => {
    if (e.pointerId !== id) return;
    const dx = e.clientX - x0, dy = e.clientY - y0, moved = Math.hypot(dx, dy) > SLOP;
    const picked = choice, wasSlid = slid;
    close();
    swallowClickUntil = performance.now() + 350;
    if (!moved) { openComposer({to: focused(), picking: !focused()}); return; }
    if (lifted) { openComposer({to: picked, picking: !picked}); return; }
    // Back over the handle before release cancels; a slide without the lift opens the picker on that name.
    if (wasSlid && Math.abs(dx) > CARD / 2) openComposer({to: picked, picking: true});
  });
  for (const type of ["pointercancel", "lostpointercapture"]) envelope.addEventListener(type, (e) => { if (e.pointerId === id) close(); });
}

// --- The media viewer ----------------------------------------------------------------------------------------------
function openLightbox(a) {
  const box = $("lightbox");
  const img = el("img"); img.src = a.url; img.alt = a.name;
  box.replaceChildren(img);
  box.hidden = false;
  history.pushState({world: "media"}, "");
}

export function openAgent(name) {
  const index = S.order.indexOf(name);
  if (name === OPERATOR || name === S.me || index < 0) { openNeeds(); return; }
  setFocus(index);
  openThread();
}

// --- Wiring and updates from the poll ------------------------------------------------------------------------------
export function start() {
  wireStrip($("strip"), () => true);
  wireStrip($("world"), () => S.mode === "village"); // the exposed village shares the strip's map
  wireStrip($("sheetLip"), () => S.mode !== "village");
  wireEnvelope();
  wireComposer();
  $("lightbox").addEventListener("click", () => back());
  $("envelope").classList.toggle("has-draft", Boolean(S.draft?.body?.trim()));
  document.body.dataset.mode = "village";
  document.body.classList.toggle("first-use", !store.get(TAUGHT_KEY));
  paintStrip();
}

export function update(state) {
  S.me = state.sender || S.me;
  S.csrf = state.csrf || S.csrf;
  S.tasks = Array.isArray(state.tasks) ? state.tasks : S.tasks;
  const was = focused();
  S.agents = new Map(state.agents.filter((a) => a.agent !== S.me && a.agent !== OPERATOR).map((a) => [a.agent, {
    busy: a.session === "busy" && !String(a.task || "").trim().toLowerCase().startsWith("idle"), task: a.task || "",
  }]));
  // Same order as the ring in the scene; the focus follows its agent, never its slot.
  S.order = [...S.agents.keys()].sort();
  S.focus = was ? S.order.indexOf(was) : -1;
  paintTags(); paintStrip();
  if (S.mode === "thread" && focused()) { $("sheetSub").textContent = S.agents.get(focused())?.task || ""; loadThread(focused()); }
  const waiting = S.tasks.filter((t) => !t.closed).length + (Number(state.inbox?.activity) || 0);
  $("needsCount").textContent = waiting ? String(waiting) : "";
}
