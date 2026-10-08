// Small pure helpers the views share: names, colours, times and text.
import type {Agent, Attachment, File as BoardFile, Message} from '../api/schema';

export const TOPICS: Record<string, string> = {
  info: 'Info', request: 'Request', handoff: 'Handoff', blocked: 'Blocked', release: 'Release', evidence: 'Evidence',
  ack: 'Ack', alert: 'Alert',
};
export const VIEWS = ['messages', 'threads', 'activity', 'tasks', 'agents', 'render'] as const;
export type View = (typeof VIEWS)[number];
export const isView = (value: unknown): value is View => VIEWS.includes(value as View);

export function hue(name: string): number {
  let h = 0;
  for (const c of name) h = (h * 31 + c.charCodeAt(0)) % 360;
  return h;
}
export function initials(name: string): string {
  return name.replace(/[^a-z0-9]/gi, ' ').trim().split(/\s+/).slice(0, 2).map((w) => w[0]).join('').toUpperCase() || '?';
}
export const clock = (t: number) => new Date(t * 1000).toLocaleTimeString([], {hour: '2-digit', minute: '2-digit'});
export const isoTime = (t: number) => new Date(t * 1000).toISOString();
export const longTime = (t: number) => new Date(t * 1000).toLocaleString();
export function dayLabel(t: number): string {
  const date = new Date(t * 1000);
  if (date.toDateString() === new Date().toDateString()) return 'Today';
  if (date.toDateString() === new Date(Date.now() - 864e5).toDateString()) return 'Yesterday';
  return date.toLocaleDateString([], {weekday: 'short', month: 'short', day: 'numeric'});
}
/** How long ago, by the board's clock when there is one. */
export function since(t: number, now: number = Date.now() / 1000): string {
  const s = Math.max(0, now - t);
  return s < 60 ? 'just now' : s < 3600 ? `${Math.floor(s / 60)} min ago` : s < 86400 ? `${Math.floor(s / 3600)} h ago`
    : `${Math.floor(s / 86400)} d ago`;
}
export function sizeText(size: number): string {
  return size < 1024 ? `${size} bytes` : size < 1048576 ? `${(size / 1024).toFixed(0)} KB`
    : size < 1073741824 ? `${(size / 1048576).toFixed(1)} MB` : `${(size / 1073741824).toFixed(1)} GB`;
}
export type Kind = 'image' | 'video' | 'audio' | 'file';
export const kindOf = (mime: string): Kind =>
  /^image\//.test(mime) ? 'image' : /^video\//.test(mime) ? 'video' : /^audio\//.test(mime) ? 'audio' : 'file';
export const isFile = (a: Attachment): a is BoardFile => !('missing' in a);

const TRAILER = /(^|\n\n)Attachments \(files on this machine\):[\s\S]*$/;
export const snippetless = (text: string) => text.replace(TRAILER, '');
export function snippet(text: string): string {
  return text.replace(/\n\nAttachments \(files on this machine\):[\s\S]*$/, '')
    .replace(/^Attachments \(files on this machine\):[\s\S]*$/, 'Attachment').replace(/[*_`#>]+/g, '')
    .replace(/\s+/g, ' ').trim().slice(0, 140);
}
/** A long message starts folded to about nine lines. */
export function isLong(body: string): boolean {
  const text = snippetless(body);
  return text.length > 500 || text.split('\n').length > 8;
}
/** Automatic notices (render-watch and the like). */
export const isSystem = (m: {sender: string}) => /(^|-)watch$/.test(m.sender);

export const statusOf = (a: Agent | undefined) => (!a ? '' : a.delivery_error ? 'error' : a.listening ? 'live' : 'idle');
export const agentStatus = (a: Agent) =>
  a.stop ? 'Retired' : a.delivery_error ? 'Delivery retrying' : a.listening ? 'Listening' : 'Offline';
export const idleLine = (a: Agent | undefined) => /^(idle)?$/i.test((a?.task || '').trim());
export const QUIET = 600;

/** One message's place in the feed: every addressed copy of one web send, or a loop of the same direct post. */
export interface Group {
  key: string;
  broadcast: boolean;
  mentions: boolean;
  merged?: boolean;
  messages: Message[];
  first: Message;
}

export function groupsFrom(messages: Iterable<Message>): Group[] {
  const groups = new Map<string, Omit<Group, 'first'>>();
  const loops = new Map<string, {key: string; created: number; recipients: Set<string>}>();
  for (const m of [...messages].sort((a, b) => a.id - b.id)) {
    const broadcast = (m.dedup || '').match(/^web-broadcast:([a-f0-9-]+(~m)?):/);
    let key = broadcast ? broadcast[1]! : String(m.id);
    let merged = false;
    // The same text sent to several agents one by one (a loop of direct posts) reads as one message to them all.
    if (!broadcast && m.recipient !== '*' && !isSystem(m)) {
      const same = `${m.sender}\u0000${m.topic}\u0000${m.reply_to || ''}\u0000${m.body}`;
      const open = loops.get(same);
      if (open && m.created - open.created < 15 && !open.recipients.has(m.recipient)) {
        key = open.key; merged = true; open.recipients.add(m.recipient);
      } else loops.set(same, {key, created: m.created, recipients: new Set([m.recipient])});
    }
    let group = groups.get(key);
    if (!group) groups.set(key, group = {key, broadcast: Boolean(broadcast), mentions: Boolean(broadcast?.[2]), messages: []});
    group.messages.push(m);
    if (merged) { group.broadcast = true; group.merged = true; }
  }
  return [...groups.values()]
    .map((g) => ({...g, messages: g.messages.sort((a, b) => a.id - b.id), first: g.messages[0]!}))
    .sort((a, b) => a.first.id - b.first.id);
}

/** A reply whose original is on the page folds under its thread's root, Slack style: root key → its reply groups. */
export function threadIndex(groups: Group[]): {replies: Map<string, Group[]>; threaded: Set<string>} {
  const groupOf = new Map<number, Group>();
  for (const g of groups) for (const m of g.messages) groupOf.set(m.id, g);
  const rootOf = (g: Group) => {
    let current = g;
    const seen = new Set<string>();
    while (current.first.reply_to && groupOf.has(current.first.reply_to) && !seen.has(current.key)) {
      seen.add(current.key); current = groupOf.get(current.first.reply_to)!;
    }
    return current;
  };
  const replies = new Map<string, Group[]>(), threaded = new Set<string>();
  for (const g of groups) {
    if (!g.first.reply_to || !groupOf.has(g.first.reply_to) || isSystem(g.first)) continue;
    const root = rootOf(g);
    if (root === g) continue;
    if (!replies.has(root.key)) replies.set(root.key, []);
    replies.get(root.key)!.push(g);
    threaded.add(g.key);
  }
  return {replies, threaded};
}

/** Consecutive messages from the same sender to the same place within five minutes share one header. */
export function continues(previous: Group | null, group: Group): boolean {
  if (!previous) return false;
  const a = previous.first, m = group.first;
  return a.sender === m.sender && a.recipient === m.recipient && a.topic === m.topic && m.created - a.created < 300
    && !group.broadcast && !previous.broadcast;
}

/** Ledger lines: one bullet per entry, wrapped lines folded into it. */
export function entries(text: string | undefined): string[] {
  const items: string[] = [];
  for (const line of (text || '').split('\n')) {
    if (!line.trim()) continue;
    const item = line.match(/^\s*[-*]\s+(.*)$/);
    if (item || !items.length) items.push(item ? item[1]! : line.trim());
    else items[items.length - 1] += ' ' + line.trim();
  }
  return items;
}

export const MENTION = /(^|[^\w@.-])@([A-Za-z0-9][\w.-]*)/g;
export const trimMention = (name: string) => name.replace(/[.-]+$/, '');
export function mentionedIn(text: string, names: Set<string>): string[] {
  const found: string[] = [];
  for (const m of text.matchAll(MENTION)) {
    const name = trimMention(m[2]!);
    if (names.has(name) && !found.includes(name)) found.push(name);
  }
  return found;
}
export type Target = string | string[];
export const describe = (t: Target) => (t === '*' ? 'everyone' : Array.isArray(t) ? t.join(', ') : t);
/** A reply box's hint names one person and counts the rest, so it fits on a phone's single line. */
export const replyHint = (t: Target) =>
  `Reply to ${Array.isArray(t) && t.length > 1 ? `${t[0]} +${t.length - 1}` : describe(t)}…`;
export function uuid(): string {
  return crypto.randomUUID?.() ?? `${Date.now().toString(16)}-${Math.random().toString(16).slice(2)}`;
}
