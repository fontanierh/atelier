// The composer: who it goes to, the draft, its attachments and @mentions. Typing @ suggests agents, and a message
// that mentions agents goes to exactly them (plus the agent whose conversation you're in). The operator's messages
// are always requests: agents treat them as actionable, so there is no type to pick.
import {useEffect, useLayoutEffect, useMemo, useRef, useState} from 'react';
import type {Agent} from '../api/schema';
import {feed} from '../lib/feed';
import {agentStatus, describe, kindOf, replyHint, sizeText} from '../lib/format';
import {isTouch} from '../lib/media';
import {changedFilters} from '../nav';
import {board, liveAgents, load} from '../store/board';
import {addFiles, composer, recipients, removeUpload, send, setBody, setRecipient, startUpload, type Tile} from '../store/composer';
import {useStore} from '../store/store';
import {loadThread, thread} from '../store/thread';
import {filterKey, ui} from '../store/ui';
import {Orb, Slot} from './bits';
import {Icon} from './Icon';
import {replyContext, threadFeed} from './ThreadView';

const box = () => document.getElementById('message') as HTMLTextAreaElement | null;

/** The @word being typed at the caret, if any. */
function mentionQuery(text: HTMLTextAreaElement | null): {start: number; text: string} | null {
  if (!text || document.activeElement !== text || text.selectionStart !== text.selectionEnd) return null;
  const before = text.value.slice(0, text.selectionStart), m = before.match(/(^|[^\w@.-])@([\w.-]*)$/);
  return m ? {start: before.length - m[2]!.length - 1, text: m[2]!.toLowerCase()} : null;
}

function TileView({tile}: {tile: Tile}) {
  const kind = kindOf(tile.mime);
  return (
    <div className={`tile ${kind}${tile.status === 'error' ? ' error' : ''}`}
      title={`${tile.name} · ${sizeText(tile.size)}`} style={{'--p': tile.progress} as React.CSSProperties}>
      {kind === 'image' ? <img src={tile.preview} alt={tile.name} />
        : kind === 'video' ? <><video src={`${tile.preview}#t=0.1`} muted playsInline preload="metadata" /><span className="tile-kind">▶ Video</span></>
          : <><Icon name="file" /><span className="tile-name">{tile.name}</span></>}
      <div className="tile-progress" hidden={tile.status === 'done'}>
        <button type="button" className="tile-retry" hidden={tile.status !== 'error'} onClick={() => startUpload(tile.key)}>Retry</button>
      </div>
      <button type="button" className="tile-remove" aria-label={`Remove ${tile.name}`} onClick={() => removeUpload(tile.key)}>
        <Icon name="close" />
      </button>
    </div>
  );
}

export function Composer() {
  const c = useStore(composer, (x) => x), state = useStore(board, (b) => b.state);
  const open = useStore(thread, (t) => t.open);
  const [focused, setFocused] = useState(false), [caret, setCaret] = useState(0), [index, setIndex] = useState(0);
  const text = useRef<HTMLTextAreaElement>(null), file = useRef<HTMLInputElement>(null);
  const keyboard = useRef<{top: number; stick: boolean; moved: boolean; sent: boolean} | null>(null);

  const live = liveAgents(state), count = live.length;
  const reply = replyContext(open, state);
  const target = state ? recipients(c.body, c.recipient, reply.audience) : '*';
  const ready = c.uploads.filter((u) => u.status === 'done').length, busy = c.uploads.some((u) => u.status !== 'done');
  const mentioning = Array.isArray(target) || target !== c.recipient;
  const disabled = c.sending || busy || !state || !count || !(c.body.trim() || ready)
    || (target !== '*' && ![target].flat().every((name) => state.agents.some((a) => a.agent === name && !a.stop)));

  // @mentions at the caret.
  const choices = useMemo(() => {
    const q = mentionQuery(text.current);
    if (!q) return [] as Agent[];
    const starts = (a: Agent) => Number(a.agent.toLowerCase().startsWith(q.text));
    return live.filter((a) => a.agent.toLowerCase().includes(q.text))
      .sort((a, b) => starts(b) - starts(a) || Number(b.listening) - Number(a.listening) || a.agent.localeCompare(b.agent)).slice(0, 6);
  }, [caret, c.body, focused, state]);
  const names = choices.map((a) => a.agent).join();
  useEffect(() => setIndex(0), [names]);
  const pick = (name: string) => {
    const t = text.current, q = mentionQuery(t);
    if (!t || !q) return;
    t.setRangeText(`@${name} `, q.start, t.selectionStart, 'end');
    setBody(t.value); setCaret(t.selectionStart);
  };

  // The box grows with the draft.
  useLayoutEffect(() => {
    const t = text.current;
    if (!t) return;
    t.style.height = 'auto'; t.style.height = `${t.scrollHeight}px`;
  }, [c.body]);

  const options = live.map((a) => [a.agent, a.agent + (!a.listening ? ' · offline' : a.delivery_error ? ' · retrying' : '')] as const);
  const retired = c.recipient !== '*' && !live.some((a) => a.agent === c.recipient);
  const chosenLabel = c.recipient === '*' ? `Everyone (${count})` : c.recipient;

  async function submit(): Promise<void> {
    if (disabled) return;
    const current = thread.get().open, context = replyContext(current, board.get().state);
    const to = recipients(composer.get().body, composer.get().recipient, context.audience);
    const sent = await send(to, current ? context.replyTo : null);
    if (!sent) return;
    if (keyboard.current) keyboard.current.sent = true;   // after sending, the conversation follows your new message
    if (isTouch()) text.current?.blur();   // on a phone the keyboard closes once the message is away
    if (current) { threadFeed.stick = true; loadThread(true); load(); return; }
    const u = ui.get(), before = filterKey(u);
    let agent = u.agent;
    if (agent && !Array.isArray(sent) && agent !== sent) agent = sent === '*' ? '' : sent;
    ui.set({agent, search: '', topic: ''});
    feed.stick = true;
    if (filterKey(ui.get()) !== before) changedFilters(); else load();
  }

  const className = `composer glass${c.body ? ' has-text' : ''}${c.body || c.uploads.length || focused || open ? ' expanded' : ''}${c.sending ? ' sending' : ''}`;
  const blur = useRef(0), out = useRef(0);
  useEffect(() => () => { clearTimeout(blur.current); clearTimeout(out.current); }, []);

  return <>
    <div className="mention-menu glass" id="mentionMenu" role="listbox" aria-label="Mention an agent" hidden={!choices.length}>
      {choices.map((a, i) => (
        <button key={a.agent} type="button" className="mention-option" id={`mention-${i}`} role="option" aria-selected={i === index}
          // Choosing keeps focus (and the phone keyboard) in the composer.
          onPointerDown={(event) => event.preventDefault()} onClick={() => pick(a.agent)}>
          <Orb name={a.agent} agent={a} />
          <span className="mention-text"><span className="mention-name">{a.agent}</span><span className="mention-task">{a.task || agentStatus(a)}</span></span>
        </button>
      ))}
    </div>
    <form id="broadcastForm" className={className} autoComplete="off"
      onSubmit={(event) => { event.preventDefault(); submit(); }}
      onFocus={() => { clearTimeout(out.current); setFocused(true); }}
      onBlur={() => { out.current = window.setTimeout(() => setFocused(false), 180); }}>
      <p id="composerStatus" className={`composer-status${c.statusError ? ' error' : ''}`} role="status" aria-live="polite">{c.status}</p>
      <div className="composer-options">
        <label className={`select-pill recipient-pill${mentioning ? ' mentioning' : ''}`}>
          <span className="pill-label">To</span>
          {/* Mentions decide who a message goes to; the To pill says so. */}
          <span className="pill-value" aria-hidden="true">{mentioning ? (Array.isArray(target) ? `${target.length} people` : target) : chosenLabel}</span>
          <select id="recipient" aria-label="Send to" value={c.recipient} onChange={(event) => setRecipient(event.target.value)}>
            <option value="*">{`Everyone (${count})`}</option>
            {options.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
            {retired && <option value={c.recipient} disabled>{`${c.recipient} · retired`}</option>}
          </select>
          <Slot name="chevron" />
        </label>
        <input type="hidden" id="broadcastTopic" value="request" />
        <span id="characterCount" className="character-count">{c.body.length > 6000 ? `${c.body.length.toLocaleString()} / 8,000` : ''}</span>
      </div>
      <div className="tray" id="tray" hidden={!c.uploads.length}>{c.uploads.map((tile) => <TileView key={tile.key} tile={tile} />)}</div>
      <div className="composer-row">
        <button type="button" className="attach-button" id="attachButton" aria-label="Add photos, videos or files" onClick={() => file.current?.click()}>
          <Slot name="plus" />
        </button>
        <input type="file" id="fileInput" ref={file} multiple hidden onChange={(event) => {
          if (event.target.files) addFiles([...event.target.files]);
          event.target.value = '';
        }} />
        <textarea ref={text} id="message" name="message" maxLength={8000} rows={1} aria-label="Send a message" enterKeyHint="enter" required
          placeholder={open ? replyHint(target) : target === '*' ? 'Message everyone, or @someone…' : `Message ${describe(target)}…`}
          aria-activedescendant={choices.length ? `mention-${index}` : undefined}
          value={c.body}
          onChange={(event) => { setBody(event.target.value); setCaret(event.target.selectionStart); }}
          onClick={(event) => setCaret(event.currentTarget.selectionStart)}
          onKeyUp={(event) => { if (!['ArrowDown', 'ArrowUp', 'Enter', 'Tab', 'Escape'].includes(event.key)) setCaret(event.currentTarget.selectionStart); }}
          onPaste={(event) => {
            const files = [...(event.clipboardData?.files || [])];
            if (files.length) { event.preventDefault(); addFiles(files); }
          }}
          onKeyDown={(event) => {
            const native = event.nativeEvent;
            if (choices.length && !native.isComposing) {
              const step = ({ArrowDown: 1, ArrowUp: -1} as Record<string, number>)[event.key];
              if (step) { event.preventDefault(); setIndex((i) => (i + step + choices.length) % choices.length); return; }
              if (event.key === 'Enter' || event.key === 'Tab') { event.preventDefault(); pick(choices[index]?.agent ?? choices[0]!.agent); return; }
              if (event.key === 'Escape') { event.preventDefault(); event.stopPropagation(); setCaret(-1); event.currentTarget.blur(); return; }
            }
            if (event.key !== 'Enter' || native.isComposing) return;
            const go = event.metaKey || event.ctrlKey || (!isTouch() && !event.shiftKey && !event.altKey);
            if (go && !disabled) { event.preventDefault(); event.currentTarget.form?.requestSubmit(); }
          }}
          // The keyboard: what you were reading before it opened is where you are once it closes. While it is up the
          // feed is shorter and gets clamped at its end, which used to flip the board into following the latest
          // message, so closing the keyboard jumped there. Unless you scrolled or sent meanwhile, it is put back.
          onFocus={() => {
            clearTimeout(blur.current);
            const f = document.getElementById('feed');
            if (isTouch()) {
              document.getElementById('app')!.classList.add('typing');
              if (!keyboard.current && f) keyboard.current = {top: f.scrollTop, stick: feed.stick, moved: false, sent: false};
            }
            if (feed.stick) setTimeout(() => feed.scrollToLatest(), 250);
            setCaret(text.current?.selectionStart ?? 0);
          }}
          onBlur={() => {
            blur.current = window.setTimeout(() => document.getElementById('app')!.classList.remove('typing'), 120);
            setTimeout(() => { if (document.activeElement !== text.current) setCaret(-1); }, 150);
            const saved = keyboard.current;
            keyboard.current = null;
            if (!saved || saved.moved || saved.sent) return;
            // Twice: once the keyboard has mostly gone, and again after its animation and the viewport have settled.
            for (const ms of [350, 750]) setTimeout(() => {
              if (document.activeElement === box()) return;
              feed.settle(250); feed.stick = saved.stick;
              if (saved.stick) feed.scrollToLatest();
              else { const f = document.getElementById('feed'); if (f) f.scrollTop = saved.top; }
            }, ms);
          }} />
        <button id="sendButton" className="send-button" type="submit" disabled={disabled}
          aria-label={busy ? 'Waiting for uploads' : target === '*' ? `Send to all ${count} agents` : `Send to ${describe(target)}`}
          // Keep the keyboard up when tapping send, so the button doesn't move under the finger.
          onPointerDown={(event) => { if (document.activeElement === text.current) event.preventDefault(); }}>
          <Slot name="send" />
        </button>
      </div>
    </form>
    <ScrollWatch keyboard={keyboard} />
  </>;
}

/** Scrolling the feed while the keyboard is up means the reader moved on: closing it then leaves them there. */
function ScrollWatch({keyboard}: {keyboard: React.RefObject<{moved: boolean} | null>}) {
  useEffect(() => {
    const f = document.getElementById('feed');
    const moved = () => { if (keyboard.current) keyboard.current.moved = true; };
    f?.addEventListener('touchmove', moved, {passive: true});
    return () => f?.removeEventListener('touchmove', moved);
  }, [keyboard]);
  return null;
}
