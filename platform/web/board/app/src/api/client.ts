// Every request has a deadline and can be cancelled, so a request frozen by iOS (or a dead network) never holds up the
// board. POSTs carry the CSRF token the last /api/state handed out; the server also checks the Origin.
import type {
  Activity, Delivered, Dismissed, Document, Preview, PushKey, Read, Removed, Seen, Sent, SendRequest, Starred, State,
  Thread, Threads, Upload,
} from './schema';

export const TIMEOUT = 12_000;

export class HttpError extends Error {
  constructor(readonly status: number, message: string) { super(message); }
}

/** A failure that is the network's, not the request's: the board says it is reconnecting. */
export function offline(error: unknown): boolean {
  if (error instanceof HttpError) return error.status === 0 || error.status >= 502;
  return error instanceof TypeError || error instanceof SyntaxError
    || (error instanceof DOMException && (error.name === 'AbortError' || error.name === 'TimeoutError'));
}
export const aborted = (error: unknown) => error instanceof DOMException && error.name === 'AbortError';
export const message = (error: unknown, fallback = 'Something went wrong. Try again.') =>
  error instanceof Error && error.message ? error.message : fallback;

let csrf = '';
export const setCsrf = (token: string) => { csrf = token; };

async function request<T>(path: string, init: RequestInit & {timeout?: number} = {}): Promise<T> {
  const controller = new AbortController();
  const outer = init.signal;
  const stop = () => controller.abort(outer?.reason);
  if (outer?.aborted) stop(); else outer?.addEventListener('abort', stop, {once: true});
  const timer = setTimeout(() => controller.abort(new DOMException('The board took too long to answer.', 'TimeoutError')),
    init.timeout ?? TIMEOUT);
  try {
    const response = await fetch(path, {...init, signal: controller.signal, cache: 'no-store', credentials: 'same-origin'});
    const text = await response.text();
    let data: unknown = null;
    try { data = text ? JSON.parse(text) : null; } catch { /* reported by the status, or as an empty answer */ }
    if (!response.ok) {
      const reason = data && typeof data === 'object' && 'error' in data ? String((data as {error: unknown}).error) : '';
      throw new HttpError(response.status, reason || `The board answered ${response.status}.`);
    }
    if (data === null || typeof data !== 'object') throw new HttpError(502, 'The board sent an empty answer.');
    return data as T;
  } catch (error) {
    // A timeout surfaces as the controller's reason; an outside abort keeps its AbortError.
    if (controller.signal.aborted && controller.signal.reason instanceof DOMException) throw controller.signal.reason;
    throw error;
  } finally {
    clearTimeout(timer);
    outer?.removeEventListener('abort', stop);
  }
}

function query(params: Record<string, string | number | boolean | undefined>): string {
  const q = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === '' || value === false || value === 0) continue;
    q.set(key, value === true ? '1' : String(value));
  }
  const text = q.toString();
  return text ? `?${text}` : '';
}

function post<T>(path: string, body: unknown, signal?: AbortSignal, timeout = 15_000): Promise<T> {
  return request<T>(path, {
    method: 'POST', body: JSON.stringify(body), signal, timeout,
    headers: {'Content-Type': 'application/json', 'X-Board-CSRF': csrf},
  });
}

export interface StateQuery {
  dm?: string; agent?: string; q?: string; topic?: string; before?: number; log?: number; limit?: number;
}

export const api = {
  state: (params: StateQuery, signal?: AbortSignal) => request<State>(`/api/state${query({...params})}`, {signal}),
  threads: (params: {limit: number; starred?: boolean}, signal?: AbortSignal) =>
    request<Threads>(`/api/threads${query(params)}`, {signal}),
  activity: (params: {limit: number; kind?: string; unread?: boolean}, signal?: AbortSignal) =>
    request<Activity>(`/api/activity${query(params)}`, {signal}),
  thread: (id: number, signal?: AbortSignal) => request<Thread>(`/api/thread${query({id})}`, {signal}),
  document: (id: string) => request<Document>(`/api/document/${encodeURIComponent(id)}`),
  pushKey: () => request<PushKey>('/api/push/key'),

  send: (body: SendRequest, signal?: AbortSignal) => post<Sent>('/api/send', body, signal),
  read: (body: {id?: number; through?: number; all?: boolean; follow?: boolean}) => post<Read>('/api/read', body),
  seen: (ids: number[]) => post<Seen>('/api/seen', {ids}),
  star: (id: number, starred: boolean) => post<Starred>('/api/star', {id, starred}),
  dismissTask: (id: number) => post<Dismissed>('/api/task/dismiss', {id}),
  remove: (agent: string) => post<Removed>('/api/remove', {agent}),
  preview: (body: string) => post<Preview>('/api/preview', {body}),
  pushSubscribe: (subscription: PushSubscriptionJSON) => post<unknown>('/api/push/subscribe', {subscription}),
  pushUnsubscribe: (endpoint: string) => post<unknown>('/api/push/unsubscribe', {endpoint}),
  pushTest: () => post<Delivered>('/api/push/test', {}),
};

/** One file upload with progress (XHR, since fetch has no upload progress in Safari). */
export function upload(file: Blob, name: string, mime: string, size: [number, number] | null,
                       progress: (percent: number) => void): {done: Promise<Upload>; abort: () => void} {
  const xhr = new XMLHttpRequest();
  const done = new Promise<Upload>((resolve, reject) => {
    xhr.open('POST', '/api/upload');
    xhr.setRequestHeader('Content-Type', mime);
    xhr.setRequestHeader('X-Board-CSRF', csrf);
    xhr.setRequestHeader('X-File-Name', encodeURIComponent(name));
    if (size?.[0] && size[1]) {
      xhr.setRequestHeader('X-Media-Width', String(size[0]));
      xhr.setRequestHeader('X-Media-Height', String(size[1]));
    }
    xhr.upload.onprogress = (event) => { if (event.lengthComputable) progress(Math.round(event.loaded / event.total * 100)); };
    xhr.onload = () => {
      let data: {id?: string; error?: string} = {};
      try { data = JSON.parse(xhr.responseText); } catch { /* reported below */ }
      if (xhr.status === 200 && data.id) resolve(data as Upload);
      else reject(new HttpError(xhr.status, data.error || `${name} could not be uploaded. Tap it to retry.`));
    };
    xhr.onerror = () => reject(new HttpError(0, `${name} could not be uploaded. Tap it to retry.`));
    xhr.onabort = () => reject(new DOMException('cancelled', 'AbortError'));
    xhr.send(file);
  });
  return {done, abort: () => xhr.abort()};
}
