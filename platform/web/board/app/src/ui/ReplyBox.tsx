// A reply box in Threads, Activity and Tasks. Its draft and request id are its own state, so the board's refreshes
// never touch what is being typed, and a retry after a failure sends the same message rather than a second one.
import {useLayoutEffect, useRef, useState} from 'react';
import {api, message} from '../api/client';
import type {ReplyAudience, State} from '../api/schema';
import {describe, mentionedIn, uuid, type Target} from '../lib/format';
import {isTouch} from '../lib/media';
import {liveAgents} from '../store/board';
import {Slot} from './bits';

/** Who an inbox reply goes to: the agents in the conversation still on the board, else everyone, plus anyone the
 *  reply mentions. */
export function replyTarget(audience: ReplyAudience, text: string, state: State | null): Target {
  const live = new Set(liveAgents(state).map((a) => a.agent)), me = state?.sender ?? 'operator';
  const extra = mentionedIn(text, live);
  if (audience === '*') return extra.length ? (extra.length === 1 ? extra[0]! : extra) : '*';
  const target = [audience].flat().filter((name) => live.has(name) && name !== me);
  for (const name of extra) if (!target.includes(name)) target.push(name);
  return target.length === 0 ? '*' : target.length === 1 ? target[0]! : target;
}

/** Sends a reply in a thread; resolves with who it went to. */
export async function sendReply(text: string, key: string, recipient: Target, replyTo: number): Promise<Target> {
  await api.send({body: text, topic: 'info', recipient, request_id: key, reply_to: replyTo});
  return recipient;
}

export function ReplyBox({label, placeholder, className = 'task-reply inbox-reply', autoFocus = false, onSend}: {
  label: string; placeholder: string; className?: string; autoFocus?: boolean;
  onSend: (text: string, key: string) => Promise<Target>;
}) {
  const [text, setText] = useState(''), [sending, setSending] = useState(false);
  const [status, setStatus] = useState<{text: string; error: boolean}>({text: '', error: false});
  const key = useRef<string | null>(null), box = useRef<HTMLTextAreaElement>(null);
  useLayoutEffect(() => {
    const t = box.current;
    if (t) { t.style.height = 'auto'; t.style.height = `${t.scrollHeight}px`; }
  }, [text]);
  useLayoutEffect(() => { if (autoFocus) box.current?.focus(); }, [autoFocus]);
  async function submit(): Promise<void> {
    const body = text.trim();
    if (!body || sending) return;
    key.current ??= uuid();
    setSending(true); setStatus({text: 'Sending…', error: false});
    try {
      const target = await onSend(body, key.current);
      setText(''); key.current = null;
      setStatus({text: `Sent to ${describe(target)}.`, error: false});
    } catch (error) {
      setStatus({text: message(error), error: true});
    } finally {
      setSending(false);
    }
  }
  return <>
    <form className={className} onSubmit={(event) => { event.preventDefault(); submit(); }}>
      <textarea ref={box} rows={1} maxLength={8000} aria-label={label} placeholder={placeholder} value={text}
        onChange={(event) => { key.current = null; setText(event.target.value); }}
        onKeyDown={(event) => {
          if (event.key === 'Enter' && !event.shiftKey && !isTouch() && !event.nativeEvent.isComposing) { event.preventDefault(); submit(); }
        }} />
      <button className="send-button" type="submit" disabled={!text.trim() || sending} aria-label="Send reply"><Slot name="send" /></button>
    </form>
    <p className={`task-status${status.error ? ' error' : ''}`} role="status">{status.text}</p>
  </>;
}
