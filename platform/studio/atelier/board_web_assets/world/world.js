// The board village: loads the Bevy scene (wasm) behind the splash, then feeds it live board state. It measures what
// decides whether this approach works on a phone (download, compile, first frame, resume after the background) and
// reports those numbers to the board server, so they can be read without anyone copying them from a screen.
import init, {run, set_agents, fly} from "/world/board_world.js";
import * as ui from "/world/ui.js";

const $ = (id) => document.getElementById(id);
const now = () => performance.now();
const marks = {start: 0};
const resumes = [];
let frames = 0, lastFrameAt = 0, csrf = "", me = "operator", lastId = 0, firstPoll = true, contextLost = 0, hiddenAt = 0;

// --- Frames from the scene ----------------------------------------------------------------------------------------
let waitingFrame = null;
window.boardWorldLabels = ui.labels;
window.boardWorldFrame = (n) => {
  frames = n; lastFrameAt = now();
  if (n === 1) { marks.firstFrame = lastFrameAt; reveal(); }
  if (waitingFrame) { const resolve = waitingFrame; waitingFrame = null; resolve(lastFrameAt); }
};
const nextFrame = (ms) => new Promise((resolve) => {
  waitingFrame = resolve;
  setTimeout(() => { if (waitingFrame === resolve) { waitingFrame = null; resolve(null); } }, ms);
});

// --- Loading --------------------------------------------------------------------------------------------------------
function splash(note, fraction) {
  if (note) $("splashNote").textContent = note;
  if (fraction !== undefined) $("splashBar").style.width = `${Math.max(4, Math.min(100, fraction * 100))}%`;
}

async function download() {
  const response = await fetch("/world/board_world_bg.wasm", {cache: "no-cache"});
  if (!response.ok) throw new Error(`the village isn't built here yet (${response.status})`);
  marks.firstByte = now();
  const total = Number(response.headers.get("X-Uncompressed-Length")) || 0;
  const reader = response.body.getReader();
  const chunks = [];
  let received = 0;
  for (;;) {
    const {done, value} = await reader.read();
    if (done) break;
    chunks.push(value); received += value.length;
    if (total) splash(null, 0.08 + 0.72 * received / total);
  }
  const bytes = new Uint8Array(received);
  let at = 0;
  for (const chunk of chunks) { bytes.set(chunk, at); at += chunk.length; }
  marks.downloaded = now();
  const entry = performance.getEntriesByName(new URL("/world/board_world_bg.wasm", location.href).href).pop();
  marks.transfer = entry ? entry.transferSize : null; // 0 means it came from the browser cache
  marks.bytes = received;
  return bytes;
}

async function start() {
  try {
    splash("Fetching the village", 0.05);
    const bytes = await download();
    splash("Building the houses", 0.84);
    const module = await WebAssembly.compile(bytes);
    marks.compiled = now();
    splash("Lighting the fire", 0.94);
    await init({module_or_path: module});
    marks.instantiated = now();
    try { run(); } catch (error) {
      // winit on the web may unwind out of run() on purpose to hand the loop to the browser; that one is fine.
      if (!String(error?.message || error).includes("control flow")) throw error;
    }
    poll();
    setTimeout(() => { if (!marks.firstFrame) splash("Still lighting the fire…"); }, 4000);
  } catch (error) {
    $("splash").classList.add("failed");
    splash(`Couldn't open the village: ${error?.message || error}`, 1);
    report("failed", {error: String(error?.message || error)});
  }
}

function reveal() {
  $("splash").classList.add("gone");
  $("hud").hidden = false;
  $("controls").hidden = false;
  ui.start();
  setTimeout(() => { $("splash").hidden = true; }, 1000);
  const s = (a, b) => ((marks[b] - marks[a]) / 1000).toFixed(2);
  const mb = (marks.bytes / 1048576).toFixed(1);
  const cached = marks.transfer === 0 ? " · cached" : "";
  $("timings").textContent = `${mb} MB${cached} · ↓ ${s("start", "downloaded")} s · compile ${s("downloaded", "compiled")} s · `
    + `start ${s("compiled", "firstFrame")} s · total ${s("start", "firstFrame")} s`;
  report("cold", {});
}

// --- Live board state ----------------------------------------------------------------------------------------------
const SYSTEM = /(^|-)watch$/;

async function poll() {
  const abort = new AbortController();
  const timer = setTimeout(() => abort.abort(), 12000);
  try {
    const response = await fetch("/api/state?limit=40&log=1", {cache: "no-store", signal: abort.signal});
    if (!response.ok) throw new Error(String(response.status));
    const state = await response.json();
    if (!state || !Array.isArray(state.agents) || !Array.isArray(state.messages)) throw new Error("bad state");
    csrf = state.csrf || csrf;
    me = state.sender || me;
    ui.update(state);
    const agents = state.agents.map((a) => ({
      name: a.agent,
      busy: a.session === "busy" && !String(a.task || "").trim().toLowerCase().startsWith("idle"),
    }));
    set_agents(JSON.stringify(agents));
    const fresh = state.messages.filter((m) => m.id > lastId && !SYSTEM.test(m.sender)).sort((a, b) => a.id - b.id);
    if (fresh.length) {
      // A burst (a reconnect, or the first look) becomes one plane per sender and recipient, never a storm; the
      // card shows the newest and how many more arrived. On the first poll only the last few wake the village.
      const shown = firstPoll ? fresh.slice(-6) : fresh;
      const pairs = new Map();
      for (const m of shown) pairs.set(`${m.sender}>${m.recipient}`, m);
      [...pairs.values()].slice(-8).forEach((m, i) => setTimeout(() => arrive(m, agents, 0), (firstPoll ? 900 : 0) + i * 650));
      const newest = shown[shown.length - 1];
      setTimeout(() => arrive(newest, agents, shown.length - 1, true), (firstPoll ? 900 : 0) + Math.min(pairs.size, 8) * 650);
      lastId = Math.max(lastId, ...state.messages.map((m) => m.id));
    }
    firstPoll = false;
  } catch {
    // A failed poll changes nothing on screen; the next one tries again.
  } finally {
    clearTimeout(timer);
    setTimeout(poll, document.hidden ? 15000 : 3000);
  }
}

function arrive(message, agents, more, cardOnly = false) {
  if (!cardOnly) {
    const to = message.recipient === "*" ? agents.map((a) => a.name).filter((n) => n !== message.sender).slice(0, 8)
      : [message.recipient];
    for (const name of to) fly(message.sender, name, message.topic || "info");
    return;
  }
  $("card").dataset.agent = message.sender === me ? message.recipient : message.sender;
  $("cardFrom").textContent = message.sender;
  $("cardTo").textContent = message.recipient === "*" ? "everyone" : message.recipient;
  $("cardTopic").textContent = more > 0 ? `${message.topic || ""} · +${more} more` : (message.topic || "");
  // body_html is the server's own sanitised Markdown rendering, the same the classic board shows.
  $("cardBody").innerHTML = message.body_html || "";
  const card = $("card");
  card.hidden = false;
  card.classList.remove("arrive"); void card.offsetWidth; card.classList.add("arrive");
}

// Tapping the arrival card opens that conversation.
$("card").addEventListener("click", (e) => { if (!e.target.closest("a")) ui.openAgent($("card").dataset.agent); });

// --- Resume and context loss ---------------------------------------------------------------------------------------
$("world").addEventListener("webglcontextlost", () => { contextLost += 1; });
document.addEventListener("visibilitychange", async () => {
  if (document.hidden) { hiddenAt = now(); return; }
  if (!marks.firstFrame) return;
  const shown = now();
  const lostBefore = contextLost;
  const frameAt = await nextFrame(5000);
  const entry = {away_s: +((shown - hiddenAt) / 1000).toFixed(1), resume_ms: frameAt ? Math.round(frameAt - shown) : null,
    context_lost: contextLost > lostBefore};
  resumes.push(entry);
  report("resume", entry);
  if (!frameAt || entry.context_lost) location.reload(); // the scene can't rebuild a lost GPU context yet
});

function report(kind, extra) {
  const ms = (a, b) => (marks[a] !== undefined && marks[b] !== undefined ? Math.round(marks[b] - marks[a]) : null);
  const body = {
    kind, ...extra,
    navigation: performance.getEntriesByType("navigation")[0]?.type || null,
    standalone: matchMedia("(display-mode: standalone)").matches || navigator.standalone === true,
    bytes: marks.bytes ?? null, transfer: marks.transfer ?? null,
    first_byte_ms: ms("start", "firstByte"), download_ms: ms("start", "downloaded"), compile_ms: ms("downloaded", "compiled"),
    instantiate_ms: ms("compiled", "instantiated"), first_frame_ms: ms("instantiated", "firstFrame"),
    total_ms: ms("start", "firstFrame"), page_ms: marks.firstFrame !== undefined ? Math.round(marks.firstFrame) : null,
    frames, dpr: devicePixelRatio, screen: `${screen.width}x${screen.height}`, ua: navigator.userAgent,
  };
  const send = () => fetch("/api/world/timing", {method: "POST", headers: {"Content-Type": "application/json", "X-Board-CSRF": csrf},
    body: JSON.stringify(body)}).catch(() => {});
  if (csrf) send(); else setTimeout(() => csrf && send(), 4000);
}

start();
