// The composer's draft: its text, who it goes to, its uploads and its request id. The draft survives reloads, and a
// retry after a timeout reuses the request id, so the board never sends the same message twice.
import {api, message, upload as uploadFile} from '../api/client';
import type {Upload} from '../api/schema';
import {kindOf, mentionedIn, uuid, type Target} from '../lib/format';
import {board, liveAgents} from './board';
import {Store} from './store';

export interface Tile {
  key: string;
  name: string;
  mime: string;
  size: number;
  status: 'uploading' | 'done' | 'error';
  progress: number;
  preview: string;
  id?: string;
  file?: File;
  pixels?: [number, number] | null;
}

export interface Composer {
  body: string;
  recipient: string;
  /** The request id of the message being sent; kept until it is sent, or the draft changes. */
  key: string | null;
  uploads: readonly Tile[];
  sending: boolean;
  status: string;
  statusError: boolean;
}

const DRAFT = 'atelier.board.draft';

function restore(): Composer {
  const empty: Composer = {body: '', recipient: '*', key: null, uploads: [], sending: false, status: '', statusError: false};
  try {
    const draft = JSON.parse(localStorage.getItem(DRAFT) || 'null');
    if (!draft || typeof draft !== 'object') return empty;
    const files = Array.isArray(draft.files) ? draft.files : [];
    return {
      ...empty, body: String(draft.body || ''), recipient: String(draft.recipient || '*'), key: draft.key || null,
      uploads: files.filter((f: Upload) => f && f.id).map((f: Upload) => ({
        key: f.id, id: f.id, name: f.name, mime: f.mime, size: f.size, status: 'done', progress: 100,
        preview: `/api/attachment/${f.id}/${encodeURIComponent(f.name)}`,
      })),
    };
  } catch { return empty; }
}

export const composer = new Store<Composer>(restore());

composer.subscribe(() => {
  const c = composer.get();
  try {
    localStorage.setItem(DRAFT, JSON.stringify({
      body: c.body, recipient: c.recipient, key: c.key, topic: 'request',
      files: c.uploads.filter((u) => u.id).map(({id, name, mime, size}) => ({id, name, mime, size})),
    }));
  } catch { /* private mode */ }
});

let statusTimer = 0;
export function status(text: string, error = false): void {
  clearTimeout(statusTimer);
  composer.set({status: text, statusError: error});
  if (text && !error) statusTimer = window.setTimeout(() => composer.set({status: ''}), 4000);
}

/** The text changed: a new message from here on, with its own request id. */
export function setBody(body: string): void {
  composer.set((c) => ({body, key: body === c.body ? c.key : null}));
}
export function setRecipient(recipient: string): void {
  composer.set((c) => ({recipient, key: recipient === c.recipient ? c.key : null}));
}

/** Who a draft goes to: '*', one agent, or the agents it mentions (plus the one you're writing to). In a thread, its
 *  audience plus anyone mentioned. */
export function recipients(body: string, chosen: string, audience: string[] | null): Target {
  const names = new Set(liveAgents(board.get().state).map((a) => a.agent));
  const mentions = mentionedIn(body, names);
  if (audience) {
    const list = [...audience];
    for (const name of mentions) if (!list.includes(name)) list.push(name);
    return list;
  }
  if (!mentions.length) return chosen;
  if (chosen !== '*' && !mentions.includes(chosen)) mentions.unshift(chosen);
  return mentions.length === 1 ? mentions[0]! : mentions;
}

/* Attachments: files upload as soon as they are picked; the message only refers to them. */
const running = new Map<string, () => void>();

function update(key: string, patch: Partial<Tile>): void {
  composer.set((c) => ({uploads: c.uploads.map((u) => (u.key === key ? {...u, ...patch} : u))}));
}

async function pixels(file: File): Promise<[number, number] | null> {
  const kind = kindOf(file.type || '');
  try {
    if (kind === 'image' && 'createImageBitmap' in window) {
      const bitmap = await createImageBitmap(file);
      const size: [number, number] = [bitmap.width, bitmap.height];
      bitmap.close?.();
      return size;
    }
    if (kind === 'video') {
      return await new Promise((resolve) => {
        const video = document.createElement('video'), url = URL.createObjectURL(file);
        const done = (size: [number, number] | null) => { URL.revokeObjectURL(url); resolve(size); };
        video.preload = 'metadata'; video.muted = true;
        video.onloadedmetadata = () => done([video.videoWidth, video.videoHeight]);
        video.onerror = () => done(null);
        setTimeout(() => done(null), 3000);
        video.src = url;
      });
    }
  } catch { /* unknown size is fine */ }
  return null;
}

export async function startUpload(key: string): Promise<void> {
  const tile = composer.get().uploads.find((u) => u.key === key);
  if (!tile?.file) return;
  update(key, {status: 'uploading', progress: 0});
  const size = tile.pixels === undefined ? await pixels(tile.file) : tile.pixels;
  update(key, {pixels: size});
  const job = uploadFile(tile.file, tile.name, tile.mime, size, (progress) => update(key, {progress}));
  running.set(key, job.abort);
  try {
    const result = await job.done;
    update(key, {id: result.id, name: result.name, status: 'done', progress: 100});
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') return;
    update(key, {status: 'error'});
    status(message(error, `${tile.name} could not be uploaded. Tap it to retry.`), true);
  } finally {
    running.delete(key);
  }
}

export function addFiles(list: Iterable<File>): void {
  for (const file of list) {
    if (composer.get().uploads.length >= 10) { status('You can attach up to 10 files to one message.', true); break; }
    if (file.size > 512 * 1048576) { status(`${file.name} is larger than 512 MB.`, true); continue; }
    const tile: Tile = {
      key: uuid(), file, name: file.name || 'file', mime: file.type || 'application/octet-stream', size: file.size,
      status: 'uploading', progress: 0, preview: URL.createObjectURL(file),
    };
    composer.set((c) => ({uploads: [...c.uploads, tile], key: null}));
    startUpload(tile.key);
  }
}

export function removeUpload(key: string): void {
  running.get(key)?.();
  const tile = composer.get().uploads.find((u) => u.key === key);
  if (tile?.preview.startsWith('blob:')) URL.revokeObjectURL(tile.preview);
  composer.set((c) => ({uploads: c.uploads.filter((u) => u.key !== key), key: null}));
}

/** Send the draft. Resolves with who it went to, or null when it did not go (the draft is kept). */
export async function send(target: Target, replyTo: number | null): Promise<Target | null> {
  const c = composer.get();
  const files = c.uploads.filter((u) => u.status === 'done' && u.id).map((u) => u.id!);
  if (c.sending || !(c.body.trim() || files.length) || c.uploads.some((u) => u.status !== 'done')) return null;
  const key = c.key ?? uuid();
  composer.set({key, sending: true});
  status('Sending…');
  const abort = new AbortController(), timer = setTimeout(() => abort.abort(), 15_000);
  try {
    await api.send({body: c.body, topic: 'request', recipient: target, request_id: key, attachments: files,
      reply_to: replyTo}, abort.signal);
    status('');   // the message appearing in the feed is the confirmation
    for (const u of c.uploads) if (u.preview.startsWith('blob:')) URL.revokeObjectURL(u.preview);
    composer.set({body: '', key: null, uploads: []});
    return target;
  } catch (error) {
    status(abort.signal.aborted ? 'The connection timed out. Your draft is saved; tap send to finish this same message.'
      : message(error, 'Message failed. Your draft is saved; retry safely.'), true);
    return null;
  } finally {
    clearTimeout(timer);
    composer.set({sending: false});
  }
}
