// Small pieces every view uses: an agent's orb, a slot icon, formatted text and attachments.
import {memo, useLayoutEffect, useRef, type ReactNode} from 'react';
import type {Agent, Attachment} from '../api/schema';
import {isFree} from '../lib/agents';
import {hue, initials, isFile, kindOf, MENTION, sizeText, statusOf, trimMention} from '../lib/format';
import {board} from '../store/board';
import {openPhoto, openReader} from '../store/overlay';
import {useStore} from '../store/store';
import {Icon, type IconName} from './Icon';

/** An icon in its own slot, as the page's fixed controls have it. */
export const Slot = ({name}: {name: IconName}) => <span data-icon={name}><Icon name={name} /></span>;

export function Orb({name, agent, children}: {name: string; agent?: Agent | undefined; children?: ReactNode}) {
  const free = useStore(board, (b) => (agent ? isFree(agent, b.state, b.dismissed) : false));
  if (name === '*' || !name) return <span className="orb everyone"><Icon name="agents" />{children}</span>;
  return (
    <span className="orb" style={{'--hue': hue(name)} as React.CSSProperties}>
      {initials(name).slice(0, 1)}
      {agent && !agent.stop && (
        <span className={`badge ${statusOf(agent)}${free ? ' free' : ''}`}
          style={{'--delay': `${(hue(name) % 9) * .29}s`} as React.CSSProperties} />
      )}
      {children}
    </span>
  );
}

/** @name of an agent on the board becomes a tappable mention (the container handles the tap). */
function linkMentions(container: HTMLElement, names: Set<string>): void {
  if (!names.size) return;
  const walker = document.createTreeWalker(container, NodeFilter.SHOW_TEXT, {acceptNode: (n) =>
    n.parentElement?.closest('code, pre, a, button') ? NodeFilter.FILTER_REJECT
      : n.nodeValue?.includes('@') ? NodeFilter.FILTER_ACCEPT : NodeFilter.FILTER_SKIP});
  const texts: Text[] = [];
  while (walker.nextNode()) texts.push(walker.currentNode as Text);
  for (const text of texts) {
    const value = text.nodeValue || '', parts: Node[] = [];
    let last = 0;
    for (const m of value.matchAll(MENTION)) {
      const name = trimMention(m[2]!);
      if (!names.has(name)) continue;
      const at = m.index! + m[1]!.length;
      parts.push(document.createTextNode(value.slice(last, at)));
      const b = document.createElement('button');
      b.className = 'mention'; b.type = 'button'; b.textContent = '@' + name; b.dataset.agent = name;
      parts.push(b);
      last = at + 1 + name.length;
    }
    if (parts.length) { parts.push(document.createTextNode(value.slice(last))); text.replaceWith(...parts); }
  }
}

const agentNames = (agents: Agent[] | undefined) => (agents || []).map((a) => a.agent).join('\u0000');

/** Server-rendered Markdown (the server's renderer allows no raw HTML). Set once per change, so the playful layer's
 *  word streaming and anything else that decorates it is left alone between changes. */
export const Markdown = memo(function Markdown({html, raw, className = '', onMention}:
  {html: string | null | undefined; raw?: string; className?: string; onMention?: (name: string) => void}) {
  const ref = useRef<HTMLDivElement>(null);
  const names = useStore(board, (b) => agentNames(b.state?.agents));
  useLayoutEffect(() => {
    const box = ref.current;
    if (!box) return;
    if (typeof html !== 'string') { box.textContent = raw ?? ''; return; }
    const template = document.createElement('template');
    template.innerHTML = html;
    box.replaceChildren(template.content);
    box.querySelectorAll('table').forEach((table) => {
      const wrap = document.createElement('div');
      wrap.className = 'table-scroll'; table.replaceWith(wrap); wrap.append(table);
    });
    linkMentions(box, new Set(names ? names.split('\u0000') : []));
  }, [html, raw, names]);
  return (
    <div ref={ref} className={`${className} markdown`.trim()} onClick={(event) => {
      const mention = (event.target as Element).closest<HTMLElement>('button.mention');
      if (mention?.dataset.agent && onMention) { event.stopPropagation(); onMention(mention.dataset.agent); }
    }} />
  );
});

export const Attachments = memo(function Attachments({files}: {files: Attachment[]}) {
  const images = files.filter((f) => isFile(f) && kindOf(f.mime) === 'image').length;
  return (
    <div className="attachments">
      {files.map((f, i) => {
        if (!isFile(f)) return <p key={`missing:${i}`} className="att-missing">{f.name} is no longer available</p>;
        const kind = kindOf(f.mime);
        const ratio = f.width && f.height ? {'--ratio': `${f.width} / ${f.height}`} as React.CSSProperties : undefined;
        if (kind === 'image') {
          return (
            <button key={f.id} type="button" className={`att-image${images === 1 ? ' single' : ''}`} style={ratio}
              onClick={() => openPhoto(f)}>
              <img src={f.url} alt={f.name} loading="lazy" width={f.width ?? undefined} height={f.height ?? undefined} />
            </button>
          );
        }
        if (kind === 'video') return <video key={f.id} className="att-video" style={ratio} src={f.url} controls playsInline preload="metadata" />;
        if (kind === 'audio') return <audio key={f.id} className="att-audio" src={f.url} controls preload="none" />;
        return (
          <a key={f.id} className="att-file" href={f.url} target="_blank" rel="noopener noreferrer" onClick={(event) => {
            if (!f.readable || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
            event.preventDefault(); openReader(f);
          }}>
            <Icon name="file" />
            <span><b>{f.name}</b><small>{`${sizeText(f.size)} · ${(f.name.split('.').pop() || 'file').toUpperCase()}`}</small></span>
          </a>
        );
      })}
    </div>
  );
});

/** Ledger text is plain; only `code` spans are styled. */
export function Inline({text}: {text: string}) {
  return <span>{text.split('`').map((part, i) => (i % 2 ? <code key={i}>{part}</code> : part))}</span>;
}
