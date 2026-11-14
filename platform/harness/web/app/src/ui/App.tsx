import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import type {
  BoardMessage,
  BootstrapPayload,
  ChannelSummary,
  NotificationItem,
  Principal,
  Reaction,
  SyncEventPayload,
  ThreadDetail,
} from '../types';
import { DitherBeam, type BeamPreset } from './DitherBeam';

const HERO_EMOJIS = ['👍', '❤️', '🔥', '✅', '👀', '🚀'];

const EMOJI_CATALOG: { emoji: string; keywords: string }[] = [
  { emoji: '👍', keywords: 'thumbs up yes approve like ok' },
  { emoji: '❤️', keywords: 'heart love red' },
  { emoji: '🔥', keywords: 'fire hot lit ship' },
  { emoji: '✅', keywords: 'check done green pass verified' },
  { emoji: '👀', keywords: 'eyes looking review' },
  { emoji: '🚀', keywords: 'rocket launch deploy ship fast' },
  { emoji: '🎉', keywords: 'tada party celebrate congrats' },
  { emoji: '😂', keywords: 'joy laugh lol funny' },
  { emoji: '🙌', keywords: 'hands raise praise nice' },
  { emoji: '💯', keywords: '100 hundred perfect' },
  { emoji: '⚡', keywords: 'zap bolt fast perf' },
  { emoji: '👏', keywords: 'clap bravo great' },
  { emoji: '🤝', keywords: 'handshake deal sync merge' },
  { emoji: '🎯', keywords: 'bullseye target exact' },
  { emoji: '🛠️', keywords: 'tools build fix wrench' },
  { emoji: '🐛', keywords: 'bug issue' },
  { emoji: '✨', keywords: 'sparkles polish clean magic' },
  { emoji: '🧠', keywords: 'brain smart idea' },
  { emoji: '🫡', keywords: 'salute ack on it' },
  { emoji: '📌', keywords: 'pin note keep' },
  { emoji: '💡', keywords: 'bulb idea tip' },
  { emoji: '🐎', keywords: 'horse race gallop' },
  { emoji: '🚂', keywords: 'train express rail' },
  { emoji: '🛹', keywords: 'skateboard trick' },
];

function formatClock(unixSeconds: number): string {
  const d = new Date(unixSeconds * 1000);
  const hh = d.getHours();
  const mm = String(d.getMinutes()).padStart(2, '0');
  const ampm = hh >= 12 ? 'PM' : 'AM';
  const h12 = hh % 12 || 12;
  return `${h12}:${mm} ${ampm}`;
}

function formatRelative(unixSeconds: number): string {
  const nowRef = Math.max(Date.now() / 1000, 1794332100);
  const mins = Math.max(1, Math.round((nowRef - unixSeconds) / 60));
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.round(mins / 60);
  if (hrs < 48) return `${hrs}h ago`;
  return `${Math.round(hrs / 24)}d ago`;
}

function toggleReactionsArray(reactions: Reaction[], emoji: string, userId: string): Reaction[] {
  const next = reactions.map((r) => ({ ...r, users: [...(r.users || [])] }));
  const hit = next.find((r) => r.emoji === emoji);
  if (hit) {
    const idx = hit.users.indexOf(userId);
    if (idx >= 0) hit.users.splice(idx, 1);
    else hit.users.push(userId);
    hit.count = hit.users.length;
    return next.filter((r) => r.count > 0);
  }
  return [...next, { emoji, count: 1, users: [userId] }];
}

function detectMentionQuery(text: string): string | null {
  const match = text.match(/(?:^|\s)@([a-z0-9.:_/-]*)$/i);
  return match ? (match[1] ?? '').toLowerCase() : null;
}

function completeMention(text: string, handle: string): string {
  return text.replace(/(^|\s)@[a-z0-9.:_/-]*$/i, `$1@${handle} `);
}

/* Crisp Slack Icons */
const IcoHome: React.FC<{ filled?: boolean }> = ({ filled }) => (
  <svg width="20" height="20" viewBox="0 0 20 20" fill={filled ? 'currentColor' : 'none'}>
    <path d="M3.2 8.4L10 3L16.8 8.4V16.2C16.8 16.75 16.35 17.2 15.8 17.2H12.2V12.2H7.8V17.2H4.2C3.65 17.2 3.2 16.75 3.2 16.2V8.4Z" stroke="currentColor" strokeWidth="1.55" strokeLinejoin="round" />
  </svg>
);

const IcoDMs: React.FC<{ filled?: boolean }> = ({ filled }) => (
  <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
    <path d="M3 5.2C3 4.2 3.8 3.4 4.8 3.4H12.6C13.6 3.4 14.4 4.2 14.4 5.2V10.2C14.4 11.2 13.6 12 12.6 12H7.4L3.8 14.8V12C3.3 11.8 3 11.1 3 10.2V5.2Z" fill={filled ? 'currentColor' : 'none'} stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round" />
    <path d="M14.6 7.4H15.4C16.3 7.4 17 8.1 17 9V13.4C17 14.3 16.3 15 15.4 15H14.8V17L12.3 15H9.6" stroke="currentColor" strokeWidth="1.45" strokeLinecap="round" strokeLinejoin="round" />
  </svg>
);

const IcoBell: React.FC<{ filled?: boolean }> = ({ filled }) => (
  <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
    <path d="M5.4 8.5C5.4 5.95 7.45 3.9 10 3.9C12.55 3.9 14.6 5.95 14.6 8.5V12.1L16.2 14.1H3.8L5.4 12.1V8.5Z" fill={filled ? 'currentColor' : 'none'} stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round" />
    <path d="M8.3 14.6C8.6 15.6 9.2 16.2 10 16.2C10.8 16.2 11.4 15.6 11.7 14.6" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
  </svg>
);

const IcoThreads: React.FC = () => (
  <svg width="16" height="16" viewBox="0 0 18 18" fill="none">
    <path d="M2.8 4.2C2.8 3.4 3.4 2.8 4.2 2.8H13.8C14.6 2.8 15.2 3.4 15.2 4.2V10.8C15.2 11.6 14.6 12.2 13.8 12.2H7.2L3.8 15V12.2C3.25 12.2 2.8 11.75 2.8 11.2V4.2Z" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round" />
  </svg>
);

const IcoSmilePlus: React.FC = () => (
  <svg width="15" height="15" viewBox="0 0 18 18" fill="none">
    <path d="M14.8 9.4C14.6 12.5 12 15 8.8 15C5.5 15 2.8 12.3 2.8 9C2.8 5.7 5.5 3 8.8 3C9.5 3 10.2 3.1 10.8 3.3" stroke="currentColor" strokeWidth="1.45" strokeLinecap="round" />
    <circle cx="6.7" cy="7.8" r="0.9" fill="currentColor" />
    <circle cx="10.9" cy="7.8" r="0.9" fill="currentColor" />
    <path d="M6.4 10.6C7 11.5 7.8 12 8.8 12C9.8 12 10.6 11.5 11.2 10.6" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" />
    <path d="M14.4 2.6V6.6M12.4 4.6H16.4" stroke="currentColor" strokeWidth="1.45" strokeLinecap="round" />
  </svg>
);

const IcoCopy: React.FC = () => (
  <svg width="16" height="16" viewBox="0 0 18 18" fill="none">
    <rect x="6.2" y="6.2" width="8.6" height="8.6" rx="2" stroke="currentColor" strokeWidth="1.45" />
    <path d="M11.8 6.2V4.4C11.8 3.6 11.2 3 10.4 3H4.4C3.6 3 3 3.6 3 4.4V10.4C3 11.2 3.6 11.8 4.4 11.8H6.2" stroke="currentColor" strokeWidth="1.45" />
  </svg>
);

const IcoCatchUp: React.FC = () => (
  <svg width="16" height="16" viewBox="0 0 18 18" fill="none">
    <rect x="3" y="4" width="10" height="10" rx="2.2" stroke="currentColor" strokeWidth="1.5" />
    <path d="M6.2 2.5H13.5C14.6 2.5 15.5 3.4 15.5 4.5V11.8" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" />
  </svg>
);

const IcoBranch: React.FC = () => (
  <svg width="16" height="16" viewBox="0 0 18 18" fill="none">
    <circle cx="5.5" cy="4.5" r="2" stroke="currentColor" strokeWidth="1.5" />
    <circle cx="5.5" cy="13.5" r="2" stroke="currentColor" strokeWidth="1.5" />
    <circle cx="13" cy="6.5" r="2" stroke="currentColor" strokeWidth="1.5" />
    <path d="M5.5 6.5V11.5M13 8.5C13 10.5 11 11 5.5 11" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
  </svg>
);

const IcoAgents: React.FC = () => (
  <svg width="16" height="16" viewBox="0 0 18 18" fill="none">
    <circle cx="9" cy="9" r="6.2" stroke="currentColor" strokeWidth="1.5" />
    <path d="M6.4 9.2L8.2 11L11.8 7.2" stroke="currentColor" strokeWidth="1.55" strokeLinecap="round" strokeLinejoin="round" />
  </svg>
);

const IcoSearch: React.FC = () => (
  <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
    <circle cx="7.8" cy="7.8" r="5.1" stroke="currentColor" strokeWidth="1.65" />
    <path d="M11.7 11.7L15.4 15.4" stroke="currentColor" strokeWidth="1.65" strokeLinecap="round" />
  </svg>
);

const IcoShield: React.FC = () => (
  <svg width="14" height="14" viewBox="0 0 16 16" fill="none">
    <path d="M8 1.8L13.2 3.8V7.8C13.2 11.1 10.9 13.4 8 14.4C5.1 13.4 2.8 11.1 2.8 7.8V3.8L8 1.8Z" stroke="currentColor" strokeWidth="1.45" strokeLinejoin="round" />
  </svg>
);

const IcoSend: React.FC = () => (
  <svg width="15" height="15" viewBox="0 0 16 16" fill="none">
    <path d="M2.2 13.4L14.2 8L2.2 2.6L3.9 7.2L9.6 8L3.9 8.8L2.2 13.4Z" fill="currentColor" />
  </svg>
);

const IcoLock: React.FC = () => (
  <svg width="13" height="13" viewBox="0 0 16 16" fill="none">
    <rect x="3.2" y="7.2" width="9.6" height="6.8" rx="1.6" stroke="currentColor" strokeWidth="1.45" />
    <path d="M5.2 7.2V5.1C5.2 3.55 6.45 2.3 8 2.3C9.55 2.3 10.8 3.55 10.8 5.1V7.2" stroke="currentColor" strokeWidth="1.45" />
  </svg>
);

const Avatar: React.FC<{
  principal?: Principal;
  id: string;
  size?: 'xl' | 'lg' | 'md' | 'sm' | 'xs';
  showDot?: boolean;
  cornerBadge?: '@' | 'thread';
}> = ({ principal, id, size = 'md', showDot = false, cornerBadge }) => {
  const isActive = principal?.status === 'active';
  const hue = principal?.hue || 'ice';
  const label = (principal?.display_name || id).replace(/^guest:/, '');
  const initials = label
    .split(/[\s/:-]+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((s) => s[0]?.toUpperCase() || '')
    .join('');

  return (
    <span className={`sl-av sl-av-${size} av-hue-${hue}`}>
      <span>{initials || '?'}</span>
      {showDot && <i className={`sl-presence ${isActive ? 'online' : 'away'}`} />}
      {cornerBadge && <i className="sl-corner-sub">{cornerBadge === '@' ? '@' : '💬'}</i>}
    </span>
  );
};

function renderSlackMarkdown(
  text: string,
  viewerId: string,
  onClickChannel?: (channelSlug: string) => void,
  onClickMention?: (handle: string) => void
): React.ReactNode {
  const clean = text.replace(/^📢\s*/, '');
  const lines = clean.split('\n');
  return lines.map((line, lineIdx) => {
    const tokens = line.split(/(`[^`]+`|\*\*[^*]+\*\*|@[a-z0-9.:_/-]+|#[a-z0-9-]+)/gi);
    return (
      <React.Fragment key={lineIdx}>
        {lineIdx > 0 && <br />}
        {tokens.map((tok, i) => {
          if (!tok) return null;
          if (tok.startsWith('`') && tok.endsWith('`') && tok.length > 2) {
            return <code key={i} className="sl-code">{tok.slice(1, -1)}</code>;
          }
          if (tok.startsWith('**') && tok.endsWith('**') && tok.length > 4) {
            return <strong key={i}>{tok.slice(2, -2)}</strong>;
          }
          if (tok.startsWith('@') && tok.length > 1) {
            const handle = tok.slice(1);
            const isMe = handle.toLowerCase() === viewerId.toLowerCase();
            if (onClickMention) {
              return (
                <button
                  key={i}
                  type="button"
                  className={`sl-mention ${isMe ? 'is-me' : ''}`}
                  onClick={(e) => {
                    e.preventDefault();
                    e.stopPropagation();
                    onClickMention(handle);
                  }}
                >
                  {tok}
                </button>
              );
            }
            return <span key={i} className={`sl-mention ${isMe ? 'is-me' : ''}`}>{tok}</span>;
          }
          if (tok.startsWith('#') && tok.length > 2) {
            const slug = tok.slice(1).toLowerCase();
            if (onClickChannel) {
              return (
                <button
                  key={i}
                  type="button"
                  className="sl-ch-ref"
                  onClick={(e) => {
                    e.preventDefault();
                    e.stopPropagation();
                    onClickChannel(slug);
                  }}
                >
                  {tok}
                </button>
              );
            }
            return <span key={i} className="sl-ch-ref">{tok}</span>;
          }
          return <React.Fragment key={i}>{tok}</React.Fragment>;
        })}
      </React.Fragment>
    );
  });
}

const MentionAutocomplete: React.FC<{
  query: string | null;
  principals: Record<string, Principal>;
  onSelect: (id: string) => void;
}> = ({ query, principals, onSelect }) => {
  if (query === null) return null;
  const matches = Object.values(principals)
    .filter(
      (p) =>
        p.id.toLowerCase().includes(query) ||
        p.display_name.toLowerCase().includes(query)
    )
    .slice(0, 6);
  if (!matches.length) return null;

  return (
    <div className="mention-popover">
      {matches.map((p) => (
        <button
          key={p.id}
          type="button"
          className="mention-opt"
          onMouseDown={(e) => {
            e.preventDefault();
            onSelect(p.id);
          }}
          onClick={() => onSelect(p.id)}
        >
          <Avatar principal={p} id={p.id} size="xs" showDot />
          <strong>@{p.display_name}</strong>
          <span>{p.status_text}</span>
        </button>
      ))}
    </div>
  );
};

/* Native Slack Bottom Sheet (Used for BOTH ☺+ Reaction Picker AND Long-Press Message Actions — NEVER shifts layout!) */
const NativeBottomSheet: React.FC<{
  msg: BoardMessage | null;
  mode: 'reactions' | 'actions';
  viewerId: string;
  principals: Record<string, Principal>;
  onSwitchMode: (mode: 'reactions' | 'actions') => void;
  onSelectEmoji: (emoji: string) => void;
  onReplyThread: (rootId: number) => void;
  onCopyText: (text: string) => void;
  onClose: () => void;
}> = ({
  msg,
  mode,
  viewerId,
  principals,
  onSwitchMode,
  onSelectEmoji,
  onReplyThread,
  onCopyText,
  onClose,
}) => {
  const [emojiSearch, setEmojiSearch] = useState('');
  const [dragY, setDragY] = useState(0);
  const [dragging, setDragging] = useState(false);
  const startYRef = useRef<number | null>(null);
  const openedAtRef = useRef<number>(performance.now());

  useEffect(() => {
    if (msg) {
      openedAtRef.current = performance.now();
      setEmojiSearch('');
      setDragY(0);
      setDragging(false);
    }
  }, [msg, mode]);

  if (!msg) return null;

  const existingMine = new Set(
    msg.reactions.filter((r) => (r.users || []).includes(viewerId)).map((r) => r.emoji)
  );
  const author = principals[msg.author_id];
  const eq = emojiSearch.trim().toLowerCase();
  const filteredEmojis = EMOJI_CATALOG.filter(
    (item) => !eq || item.keywords.includes(eq) || item.emoji.includes(eq)
  );

  const onSheetTouchStart = (e: React.TouchEvent) => {
    const t = e.touches[0];
    if (!t) return;
    startYRef.current = t.clientY;
    setDragging(false);
  };

  const onSheetTouchMove = (e: React.TouchEvent) => {
    if (startYRef.current === null) return;
    const t = e.touches[0];
    if (!t) return;
    const dy = t.clientY - startYRef.current;
    if (dy > 4) {
      setDragging(true);
      setDragY(dy);
    }
  };

  const onSheetTouchEnd = () => {
    startYRef.current = null;
    if (dragY > 90) {
      onClose();
    } else {
      setDragging(false);
      setDragY(0);
    }
  };

  return (
    <div
      className="ios-sheet-backdrop"
      onClick={() => {
        // Ignore ghost click from long-press finger release!
        if (performance.now() - openedAtRef.current < 220) return;
        onClose();
      }}
    >
      <div
        className={`ios-action-sheet ${dragging ? 'is-dragging' : ''}`}
        style={dragY > 0 ? { transform: `translate3d(0, ${dragY.toFixed(1)}px, 0)` } : undefined}
        onClick={(e) => e.stopPropagation()}
        onTouchStart={onSheetTouchStart}
        onTouchMove={onSheetTouchMove}
        onTouchEnd={onSheetTouchEnd}
      >
        <div className="ios-sheet-grabber" />

        {/* Subtle message context header */}
        <div className="ios-sheet-context">
          <Avatar principal={author} id={msg.author_id} size="xs" />
          <strong>{author?.display_name || msg.author_id}</strong>
          <span className="ios-sheet-snippet">{msg.body}</span>
        </div>

        {/* Hero 1-Tap Quick Reactions Strip (just like Slack iOS!) */}
        <div className="ios-hero-emoji-bar">
          {HERO_EMOJIS.map((em) => (
            <button
              key={em}
              type="button"
              className={`ios-hero-emoji ${existingMine.has(em) ? 'is-mine' : ''}`}
              onClick={() => {
                onSelectEmoji(em);
                onClose();
              }}
            >
              {em}
            </button>
          ))}
          {mode === 'actions' && (
            <button
              type="button"
              className="ios-hero-emoji more-btn"
              aria-label="More reactions"
              onClick={() => onSwitchMode('reactions')}
            >
              <IcoSmilePlus />
            </button>
          )}
        </div>

        {mode === 'reactions' ? (
          <>
            <div className="ios-emoji-search">
              <IcoSearch />
              <input
                type="text"
                value={emojiSearch}
                onChange={(e) => setEmojiSearch(e.target.value)}
                placeholder="Find an emoji…"
              />
            </div>
            <div className="ios-emoji-grid">
              {filteredEmojis.map((item) => (
                <button
                  key={item.emoji}
                  type="button"
                  className={`ios-grid-emoji ${existingMine.has(item.emoji) ? 'is-mine' : ''}`}
                  onClick={() => {
                    onSelectEmoji(item.emoji);
                    onClose();
                  }}
                >
                  {item.emoji}
                </button>
              ))}
            </div>
          </>
        ) : (
          <div className="ios-action-group">
            <button
              type="button"
              className="ios-sheet-row"
              onClick={() => {
                const rootId = msg.root_id || msg.id;
                onClose();
                onReplyThread(rootId);
              }}
            >
              <IcoThreads />
              <span>Reply in thread</span>
            </button>
            <button
              type="button"
              className="ios-sheet-row"
              onClick={() => {
                onCopyText(msg.body);
                onClose();
              }}
            >
              <IcoCopy />
              <span>Copy text</span>
            </button>
          </div>
        )}
      </div>
    </div>
  );
};

const SlackUnfurl: React.FC<{
  msg: BoardMessage;
  viewerRole: Principal['role'];
  approvedBranches: Record<string, boolean>;
  onApproveFork: (branch: string, rootId: number) => void;
  onInspectDiff: (branch: string) => void;
}> = ({ msg, viewerRole, approvedBranches, onApproveFork, onInspectDiff }) => {
  const m = msg.meta;
  if (!m || !m.card_type) return null;

  if (m.card_type === 'build_receipt') {
    return (
      <div className="sl-unfurl bar-blue">
        <div className="sl-unfurl-source">GitHub · fontanierh/atelier</div>
        <div className="sl-unfurl-title">{m.title}</div>
        <div className="sl-unfurl-text">{(m.badges || []).join('  ·  ')}</div>
        {m.artifact && <div className="sl-unfurl-foot"><code>{m.artifact}</code></div>}
      </div>
    );
  }

  if (m.card_type === 'upstream_guideline') {
    return (
      <div className="sl-unfurl bar-slate">
        <div className="sl-unfurl-source">Upstream main · <code>{m.main_sha}</code></div>
        <div className="sl-unfurl-text">
          <strong>Open for fork:</strong> <code>{(m.open_for_fork || []).join(', ')}</code>
          <br />
          <strong>Read-only on main:</strong> <code>{(m.protected_scopes || []).join(', ')}</code>
        </div>
      </div>
    );
  }

  if (m.card_type === 'fork_submission') {
    const branchKey = m.branch || String(msg.id);
    const isApproved = Boolean(approvedBranches[branchKey]);
    return (
      <div className="sl-unfurl bar-amber">
        <div className="sl-unfurl-source">
          {m.fork_repo} · branch <code>{m.branch}</code>
        </div>
        <div className="sl-unfurl-title">
          HEAD <code>{m.head_sha}</code> ({m.up_to_date ? `rebased on ${m.base_sha}` : 'needs rebase'} · {m.files_changed} files changed)
        </div>
        <div className="sl-unfurl-text">Touched: {(m.scopes || []).join(', ')}</div>
        {viewerRole === 'owner' && (
          <div className="sl-unfurl-actions" onClick={(e) => e.stopPropagation()}>
            <button
              type="button"
              className={isApproved ? 'sl-btn' : 'sl-btn sl-btn-primary'}
              disabled={isApproved}
              onClick={() => onApproveFork(branchKey, msg.root_id || msg.id)}
            >
              {isApproved ? 'Approved ✓' : 'Approve & Merge'}
            </button>
            <button type="button" className="sl-btn" onClick={() => onInspectDiff(branchKey)}>
              View 6 files
            </button>
          </div>
        )}
      </div>
    );
  }

  return null;
};

const SlackMessageRow: React.FC<{
  msg: BoardMessage;
  principals: Record<string, Principal>;
  viewer: Principal;
  isMobileMode: boolean;
  approvedBranches: Record<string, boolean>;
  onApproveFork: (branch: string, rootId: number) => void;
  onInspectDiff: (branch: string) => void;
  onToggleReaction: (messageId: number, emoji: string) => void;
  onOpenSheet: (msg: BoardMessage, mode: 'reactions' | 'actions') => void;
  onSelectChannel?: (slug: string) => void;
  onSelectMention?: (handle: string) => void;
  onOpenThread?: (rootId: number) => void;
  inThread?: boolean;
  isActiveThread?: boolean;
  isOptimistic?: boolean;
}> = ({
  msg,
  principals,
  viewer,
  isMobileMode,
  approvedBranches,
  onApproveFork,
  onInspectDiff,
  onToggleReaction,
  onOpenSheet,
  onSelectChannel,
  onSelectMention,
  onOpenThread,
  inThread = false,
  isActiveThread = false,
  isOptimistic = false,
}) => {
  const author = principals[msg.author_id];
  const isGuestMsg = msg.author_role === 'guest';
  const isAgent = author?.kind === 'agent';
  // Desktop-only floating popover (positioned absolute so it NEVER pushes content down!)
  const [desktopPopover, setDesktopPopover] = useState(false);
  const [pressing, setPressing] = useState(false);

  const pressTimer = useRef<number | null>(null);
  const startCoord = useRef<{ x: number; y: number } | null>(null);
  const suppressClickUntil = useRef<number>(0);

  const openReactionPicker = (e: React.MouseEvent) => {
    e.stopPropagation();
    if (isMobileMode) {
      onOpenSheet(msg, 'reactions');
    } else {
      setDesktopPopover((v) => !v);
    }
  };

  const onTouchStart = (e: React.TouchEvent) => {
    const t = e.touches[0];
    if (!t) return;
    startCoord.current = { x: t.clientX, y: t.clientY };
    pressTimer.current = window.setTimeout(() => {
      pressTimer.current = null;
      setPressing(false);
      suppressClickUntil.current = performance.now() + 550;
      if (typeof navigator !== 'undefined' && 'vibrate' in navigator) {
        try { navigator.vibrate(14); } catch {}
      }
      onOpenSheet(msg, 'actions');
    }, 340);
    setPressing(true);
  };

  const onTouchMove = (e: React.TouchEvent) => {
    if (!startCoord.current) return;
    const t = e.touches[0];
    if (!t) return;
    if (Math.hypot(t.clientX - startCoord.current.x, t.clientY - startCoord.current.y) > 9) {
      if (pressTimer.current) {
        clearTimeout(pressTimer.current);
        pressTimer.current = null;
      }
      setPressing(false);
    }
  };

  const clearPress = () => {
    if (pressTimer.current) {
      clearTimeout(pressTimer.current);
      pressTimer.current = null;
    }
    setPressing(false);
  };

  const handleRowClick = () => {
    if (performance.now() < suppressClickUntil.current) return;
    if (typeof window !== 'undefined' && (window.getSelection()?.toString() || '').length > 0) {
      return;
    }
    if (desktopPopover) {
      setDesktopPopover(false);
      return;
    }
    if (!inThread && onOpenThread) {
      onOpenThread(msg.id);
    }
  };

  return (
    <div
      className={`sl-msg ${!inThread && onOpenThread ? 'is-tappable' : ''} ${
        isActiveThread ? 'is-active-thread' : ''
      } ${
        isGuestMsg && viewer.role !== 'guest' ? 'sl-msg-guest' : ''
      } ${pressing ? 'is-pressing' : ''} ${isOptimistic ? 'msg-enter' : ''}`}
      onClick={handleRowClick}
      onTouchStart={onTouchStart}
      onTouchMove={onTouchMove}
      onTouchEnd={clearPress}
      onTouchCancel={clearPress}
      onContextMenu={(e) => {
        if (isMobileMode) {
          e.preventDefault();
          suppressClickUntil.current = performance.now() + 550;
          onOpenSheet(msg, 'actions');
        }
      }}
    >
      <Avatar principal={author} id={msg.author_id} size="md" />
      <div className="sl-msg-col">
        <div className="sl-msg-head">
          <span className="sl-msg-sender">{author?.display_name || msg.author_id}</span>
          {isAgent && !isGuestMsg && <span className="sl-app-tag">AGENT</span>}
          {isGuestMsg && <span className="sl-app-tag tag-guest">GUEST</span>}
          <span className="sl-msg-time">{formatClock(msg.created_at)}</span>
        </div>

        <div className="sl-msg-body">
          {renderSlackMarkdown(msg.body, viewer.id, onSelectChannel, onSelectMention)}
        </div>

        <SlackUnfurl
          msg={msg}
          viewerRole={viewer.role}
          approvedBranches={approvedBranches}
          onApproveFork={onApproveFork}
          onInspectDiff={onInspectDiff}
        />

        {(msg.reactions.length > 0 || (!inThread && msg.reply_count > 0 && onOpenThread)) && (
          <div className="sl-msg-below">
            {msg.reactions.length > 0 && (
              <div className="sl-reactions">
                {msg.reactions.map((r) => {
                  const mine = (r.users || []).includes(viewer.id);
                  return (
                    <button
                      key={`${r.emoji}-${r.count}-${mine ? 1 : 0}`}
                      type="button"
                      className={`sl-rx ${mine ? 'is-mine' : ''}`}
                      onClick={(e) => {
                        e.stopPropagation();
                        onToggleReaction(msg.id, r.emoji);
                      }}
                    >
                      <span className="rx-em">{r.emoji}</span>
                      <span className="rx-cnt">{r.count}</span>
                    </button>
                  );
                })}
                <button
                  type="button"
                  className="sl-rx sl-rx-add"
                  aria-label="Add reaction"
                  onClick={openReactionPicker}
                >
                  <IcoSmilePlus />
                </button>
              </div>
            )}

            {!inThread && msg.reply_count > 0 && onOpenThread && (
              <button
                type="button"
                className="sl-thread-summary"
                onClick={(e) => {
                  e.stopPropagation();
                  onOpenThread(msg.id);
                }}
              >
                <span className="sl-thread-avs">
                  {msg.reply_authors.slice(0, 3).map((aid) => (
                    <Avatar key={aid} principal={principals[aid]} id={aid} size="xs" />
                  ))}
                </span>
                <span className="sl-thread-replies">
                  {msg.reply_count} {msg.reply_count === 1 ? 'reply' : 'replies'}
                </span>
                {msg.last_reply_at && (
                  <span className="sl-thread-last">Last reply {formatRelative(msg.last_reply_at)}</span>
                )}
                <span className="sl-thread-chev">›</span>
              </button>
            )}
          </div>
        )}
      </div>

      {/* Desktop Floating Popover (position: absolute — NEVER shifts or pushes message rows!) */}
      {desktopPopover && !isMobileMode && (
        <div className="sl-floating-emoji-popover" onClick={(e) => e.stopPropagation()}>
          {EMOJI_CATALOG.slice(0, 8).map((item) => (
            <button
              key={item.emoji}
              type="button"
              onClick={() => {
                onToggleReaction(msg.id, item.emoji);
                setDesktopPopover(false);
              }}
            >
              {item.emoji}
            </button>
          ))}
        </div>
      )}

      {/* Desktop Hover Pill */}
      <div className="sl-hover-bar" onClick={(e) => e.stopPropagation()}>
        <button type="button" title="Add reaction" onClick={openReactionPicker}>
          <IcoSmilePlus />
        </button>
        {!inThread && onOpenThread && (
          <button type="button" title="Open thread" onClick={() => onOpenThread(msg.id)}>
            <IcoThreads />
          </button>
        )}
      </div>
    </div>
  );
};

export const App: React.FC = () => {
  const initialParams = useMemo(() => new URLSearchParams(window.location.search), []);
  const [viewerQuery, setViewerQuery] = useState<string>(initialParams.get('viewer') || '');

  const [railTab, setRailTab] = useState<'home' | 'dms' | 'activity'>(() => {
    const v = initialParams.get('view');
    if (v === 'activity') return 'activity';
    if (v === 'dms') return 'dms';
    return 'home';
  });
  const [centerMode, setCenterMode] = useState<'channel' | 'threads' | 'all-channels'>(() => {
    const v = initialParams.get('view');
    if (v === 'browse') return 'all-channels';
    if (v === 'threads') return 'threads';
    return 'channel';
  });

  const [activeChannelId, setActiveChannelId] = useState<string>(
    initialParams.get('channel') || 'world-build'
  );
  const [openThreadId, setOpenThreadId] = useState<number | null>(() => {
    const t = initialParams.get('thread');
    return t ? Number(t) : null;
  });

  const [mobileTab, setMobileTab] = useState<'home' | 'dms' | 'activity'>(() => {
    const mt = initialParams.get('mobileTab');
    if (mt === 'dms') return 'dms';
    if (mt === 'activity') return 'activity';
    return 'home';
  });
  const [layer1Mode, setLayer1Mode] = useState<'channel' | 'threads-list' | 'all-channels'>('channel');
  const [stackDepth, setStackDepth] = useState<0 | 1 | 2>(() => {
    const mt = initialParams.get('mobileTab');
    if (mt === 'thread') return 2;
    if (mt === 'channel') return 1;
    return 0;
  });

  // Interactive Full-Screen Horizontal Right-Swipe Back State
  const [swipeDx, setSwipeDx] = useState<number>(0);
  const [isSwiping, setIsSwiping] = useState<boolean>(false);
  const swipeRef = useRef<{ startX: number; startY: number; startTime: number; mode: 'undecided' | 'swipe' | 'scroll' } | null>(null);

  const [sidebarWidth, setSidebarWidth] = useState<number>(() => {
    try {
      const v = Number(localStorage.getItem('atelier.sidebar_width'));
      return Number.isFinite(v) && v >= 180 && v <= 460 ? v : 244;
    } catch {
      return 244;
    }
  });
  const [threadWidth, setThreadWidth] = useState<number>(() => {
    try {
      const v = Number(localStorage.getItem('atelier.thread_width'));
      return Number.isFinite(v) && v >= 300 && v <= 720 ? v : 392;
    } catch {
      return 392;
    }
  });
  const [resizingPane, setResizingPane] = useState<'sidebar' | 'thread' | null>(null);
  const resizeDragRef = useRef<{ pane: 'sidebar' | 'thread'; startX: number; startW: number } | null>(null);

  const beginPaneResize = (pane: 'sidebar' | 'thread', e: React.MouseEvent<HTMLDivElement>) => {
    e.preventDefault();
    e.stopPropagation();
    const startX = e.clientX;
    const startW = pane === 'sidebar' ? sidebarWidth : threadWidth;
    resizeDragRef.current = { pane, startX, startW };
    setResizingPane(pane);

    let latestW = startW;
    const onMove = (ev: MouseEvent) => {
      const vw = window.innerWidth || 1440;
      if (pane === 'sidebar') {
        const maxSb = Math.max(240, Math.min(460, vw - (openThreadId !== null ? threadWidth : 0) - 420));
        latestW = Math.round(Math.max(180, Math.min(maxSb, startW + (ev.clientX - startX))));
        setSidebarWidth(latestW);
      } else {
        const maxTh = Math.max(320, Math.min(720, vw - sidebarWidth - 420));
        latestW = Math.round(Math.max(300, Math.min(maxTh, startW - (ev.clientX - startX))));
        setThreadWidth(latestW);
      }
    };
    const onUp = () => {
      window.removeEventListener('mousemove', onMove);
      window.removeEventListener('mouseup', onUp);
      resizeDragRef.current = null;
      setResizingPane(null);
      try {
        localStorage.setItem(
          pane === 'sidebar' ? 'atelier.sidebar_width' : 'atelier.thread_width',
          String(latestW)
        );
      } catch {}
    };
    window.addEventListener('mousemove', onMove);
    window.addEventListener('mouseup', onUp);
  };

  const [collapsedSections, setCollapsedSections] = useState<Record<string, boolean>>({});
  const [activityFilter, setActivityFilter] = useState<'all' | 'unreads' | 'dms' | 'mentions' | 'threads'>('all');
  const [dmFilter, setDmFilter] = useState<'all' | 'agents' | 'unreads'>('all');

  const [showNewChannelModal, setShowNewChannelModal] = useState<boolean>(
    initialParams.get('modal') === 'new-channel'
  );
  const [showAccessModal, setShowAccessModal] = useState<boolean>(
    initialParams.get('modal') === 'access'
  );
  const [showSearchModal, setShowSearchModal] = useState<boolean>(false);
  const [searchQuery, setSearchQuery] = useState<string>('');

  const [sheetState, setSheetState] = useState<{ msg: BoardMessage; mode: 'reactions' | 'actions' } | null>(null);
  const [toastText, setToastText] = useState<string | null>(null);
  const [diffModalBranch, setDiffModalBranch] = useState<string | null>(null);
  const [approvedBranches, setApprovedBranches] = useState<Record<string, boolean>>({});
  const [copiedOnboarding, setCopiedOnboarding] = useState<boolean>(false);

  const [nativeMobile, setNativeMobile] = useState<boolean>(() => window.innerWidth < 860);
  const [simulateMobileOnDesktop, setSimulateMobileOnDesktop] = useState<boolean>(
    initialParams.get('device') === 'mobile'
  );
  const [keyboardOpen, setKeyboardOpen] = useState<boolean>(false);
  const feedRef = useRef<HTMLDivElement | null>(null);
  const threadFeedRef = useRef<HTMLDivElement | null>(null);

  const [boot, setBoot] = useState<BootstrapPayload | null>(null);

  const [draftBody, setDraftBody] = useState<string>('');
  const [threadDraft, setThreadDraft] = useState<string>('');
  const [alsoSendChannel, setAlsoSendChannel] = useState<boolean>(false);

  const [newChName, setNewChName] = useState<string>('belmonte-art');
  const [newChKind, setNewChKind] = useState<'public' | 'private'>('public');
  const [newChGuestAllowed, setNewChGuestAllowed] = useState<boolean>(false);
  const [newChTopic, setNewChTopic] = useState<string>('Tuscan stone shaders & station signage');

  const showToast = useCallback((text: string) => {
    setToastText(text);
    window.setTimeout(() => setToastText(null), 2000);
  }, []);

  const [dmNotifyEnabled, setDmNotifyEnabled] = useState<boolean>(() => {
    try {
      return (
        typeof window !== 'undefined' &&
        localStorage.getItem('atelier.dm_browser_notify') === '1' &&
        typeof Notification !== 'undefined' &&
        Notification.permission === 'granted'
      );
    } catch {
      return false;
    }
  });
  const dmNotifyRef = useRef<boolean>(dmNotifyEnabled);
  const viewerRef = useRef<Principal | null>(null);
  const csrfRef = useRef<string>('');
  const maxSeenMsgIdRef = useRef<number>(0);
  const swRegRef = useRef<ServiceWorkerRegistration | null>(null);

  useEffect(() => {
    dmNotifyRef.current = dmNotifyEnabled;
  }, [dmNotifyEnabled]);

  useEffect(() => {
    if (typeof navigator === 'undefined' || !('serviceWorker' in navigator)) return;
    navigator.serviceWorker
      .register('/sw.js')
      .then((reg) => {
        swRegRef.current = reg;
      })
      .catch(() => {});
    const onSwMessage = (ev: MessageEvent) => {
      const d = ev.data;
      if (d && d.type === 'atelier-open-dm' && d.channelId) {
        setActiveChannelId(d.channelId);
        setRailTab('dms');
        setCenterMode('channel');
        setLayer1Mode('channel');
        if (d.rootId) {
          setOpenThreadId(Number(d.rootId));
          setStackDepth(2);
        } else {
          setOpenThreadId(null);
          setStackDepth(1);
        }
      }
    };
    navigator.serviceWorker.addEventListener('message', onSwMessage);
    return () => navigator.serviceWorker.removeEventListener('message', onSwMessage);
  }, []);

  const fireNativeDmNotification = useCallback(
    (ev: SyncEventPayload) => {
      if (!dmNotifyRef.current) return;
      if (typeof Notification === 'undefined' || Notification.permission !== 'granted') return;
      const curViewer = viewerRef.current;
      if (!curViewer || curViewer.kind !== 'human' || curViewer.role === 'guest') return;
      if (ev.kind !== 'message.created' || ev.channel_kind !== 'dm' || !ev.message || !ev.channel_id) return;
      if (ev.message.author_id === curViewer.id) return;
      if (ev.message.id <= maxSeenMsgIdRef.current) return;
      maxSeenMsgIdRef.current = ev.message.id;

      const sender = ev.message.author_display_name || ev.message.author_id;
      const title = `Direct message from ${sender}`;
      const body = ev.message.body.length > 180 ? `${ev.message.body.slice(0, 177)}…` : ev.message.body;
      const targetChannel = ev.channel_id;
      const targetRoot = ev.message.root_id;
      const url = `/?channel=${encodeURIComponent(targetChannel)}${targetRoot ? `&thread=${targetRoot}` : ''}`;
      const tag = `atelier-dm-${targetChannel}-${ev.message.id}`;

      if (swRegRef.current && typeof swRegRef.current.showNotification === 'function') {
        swRegRef.current
          .showNotification(title, {
            body,
            tag,
            icon: '/apple-touch-icon.png',
            data: { url, channelId: targetChannel, rootId: targetRoot },
          })
          .catch(() => {
            const n = new Notification(title, { body, tag, icon: '/apple-touch-icon.png' });
            n.onclick = () => {
              window.focus();
              setActiveChannelId(targetChannel);
              setCenterMode('channel');
              setStackDepth(1);
              n.close();
            };
          });
      } else {
        const n = new Notification(title, { body, tag, icon: '/apple-touch-icon.png' });
        n.onclick = () => {
          window.focus();
          setActiveChannelId(targetChannel);
          setCenterMode('channel');
          setStackDepth(1);
          n.close();
        };
      }
    },
    []
  );

  const toggleDmBrowserNotifications = useCallback(async () => {
    if (typeof Notification === 'undefined') {
      showToast('Browser notifications are not supported here');
      return;
    }
    if (dmNotifyEnabled) {
      setDmNotifyEnabled(false);
      try { localStorage.setItem('atelier.dm_browser_notify', '0'); } catch {}
      fetch('/api/preferences/notifications', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-Atelier-CSRF': csrfRef.current },
        body: JSON.stringify({ dm_browser_notify: false }),
      }).catch(() => {});
      showToast('DM browser notifications paused');
      return;
    }
    let perm = Notification.permission;
    if (perm === 'default') {
      perm = await Notification.requestPermission();
    }
    if (perm !== 'granted') {
      showToast('Notifications blocked in browser settings');
      return;
    }
    setDmNotifyEnabled(true);
    try { localStorage.setItem('atelier.dm_browser_notify', '1'); } catch {}
    await fetch('/api/preferences/notifications', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-Atelier-CSRF': csrfRef.current },
      body: JSON.stringify({ dm_browser_notify: true }),
    }).catch(() => {});
    showToast('Native DM notifications enabled');
  }, [dmNotifyEnabled, showToast]);

  /* Fix #31690: Exact iOS Safari visualViewport lock */
  useEffect(() => {
    let baselineHeight = window.innerHeight;
    const syncViewport = () => {
      setNativeMobile(window.innerWidth < 860);
      const vv = window.visualViewport;
      if (vv) {
        if (vv.height > baselineHeight) baselineHeight = vv.height;
        const h = Math.round(vv.height);
        const top = Math.round(vv.offsetTop);
        document.documentElement.style.setProperty('--vvh', `${h}px`);
        document.documentElement.style.setProperty('--vvt', `${top}px`);
        setKeyboardOpen(baselineHeight - h > 110);
        if (window.scrollY !== 0 || window.scrollX !== 0) window.scrollTo(0, 0);
      } else {
        document.documentElement.style.setProperty('--vvh', `${window.innerHeight}px`);
        document.documentElement.style.setProperty('--vvt', '0px');
      }
    };

    syncViewport();
    window.addEventListener('resize', syncViewport);
    window.visualViewport?.addEventListener('resize', syncViewport);
    window.visualViewport?.addEventListener('scroll', syncViewport);
    return () => {
      window.removeEventListener('resize', syncViewport);
      window.visualViewport?.removeEventListener('resize', syncViewport);
      window.visualViewport?.removeEventListener('scroll', syncViewport);
    };
  }, []);

  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        setShowSearchModal((v) => !v);
      } else if (e.key === 'Escape') {
        setShowSearchModal(false);
        setSheetState(null);
        setShowAccessModal(false);
        setShowNewChannelModal(false);
        setDiffModalBranch(null);
      }
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, []);

  const onInputFocus = (isThread = false) => {
    setTimeout(() => {
      if (window.visualViewport) {
        document.documentElement.style.setProperty('--vvh', `${Math.round(window.visualViewport.height)}px`);
        document.documentElement.style.setProperty('--vvt', `${Math.round(window.visualViewport.offsetTop)}px`);
      }
      if (window.scrollY !== 0) window.scrollTo(0, 0);
      const target = isThread ? threadFeedRef.current : feedRef.current;
      if (target) target.scrollTop = target.scrollHeight;
    }, 50);
  };

  const querySuffix = viewerQuery ? `?viewer=${encodeURIComponent(viewerQuery)}` : '';

  const refreshBootstrap = useCallback(async (qSuffix: string) => {
    const res = await fetch(`/api/bootstrap${qSuffix}`);
    if (!res.ok) return;
    const data: BootstrapPayload = await res.json();
    viewerRef.current = data.viewer;
    csrfRef.current = data.csrf_token || '';
    for (const msgs of Object.values(data.channels_messages)) {
      for (const m of msgs) {
        if (m.id > maxSeenMsgIdRef.current) maxSeenMsgIdRef.current = m.id;
      }
    }
    setBoot(data);
    if (data.viewer.role === 'guest' && data.viewer.guest_channel_id) {
      setActiveChannelId(data.viewer.guest_channel_id);
    }
  }, []);

  useEffect(() => {
    refreshBootstrap(querySuffix);
    let es: EventSource | null = null;
    const timer = window.setTimeout(() => {
      es = new EventSource(`/api/events${querySuffix}`);
      es.addEventListener('sync', (rawEv: Event) => {
        try {
          const parsed: SyncEventPayload = JSON.parse((rawEv as MessageEvent).data || '{}');
          fireNativeDmNotification(parsed);
          if ((parsed.kind === 'message.created' || parsed.kind === 'reaction.toggled') && parsed.message && parsed.channel_id) {
            const incoming = parsed.message;
            const cid = parsed.channel_id;
            setBoot((prev) => {
              if (!prev) return prev;
              const curList = prev.channels_messages[cid] || [];
              let nextList = curList;
              if (parsed.kind === 'reaction.toggled') {
                nextList = curList.map((m) => (m.id === incoming.id ? incoming : m));
              } else if (incoming.root_id === null || incoming.also_channel) {
                // Replace matching optimistic message or append if new
                const withoutOpt = curList.filter(
                  (m) => !(m.id < 0 && m.author_id === incoming.author_id && m.body === incoming.body)
                );
                nextList = withoutOpt.some((m) => m.id === incoming.id)
                  ? withoutOpt.map((m) => (m.id === incoming.id ? incoming : m))
                  : [...withoutOpt, incoming];
              } else {
                // Thread reply: use authoritative parent_root from SQLite so optimistic + SSE never double-counts!
                nextList = curList.map((m) => {
                  if (m.id !== incoming.root_id) return m;
                  if (parsed.parent_root) return parsed.parent_root;
                  return {
                    ...m,
                    last_reply_at: incoming.created_at,
                    reply_authors: m.reply_authors.includes(incoming.author_id)
                      ? m.reply_authors
                      : [...m.reply_authors, incoming.author_id],
                  };
                });
              }
              const nextThreads = { ...prev.threads_by_root };
              const ridKey = String(incoming.root_id || incoming.id);
              if (nextThreads[ridKey]) {
                const td = nextThreads[ridKey]!;
                if (incoming.id === td.root.id) {
                  nextThreads[ridKey] = { ...td, root: incoming };
                } else if (parsed.kind === 'reaction.toggled') {
                  nextThreads[ridKey] = {
                    ...td,
                    replies: td.replies.map((r) => (r.id === incoming.id ? incoming : r)),
                  };
                } else if (incoming.root_id === td.root.id) {
                  const cleanReps = td.replies.filter(
                    (r) => !(r.id < 0 && r.author_id === incoming.author_id && r.body === incoming.body)
                  );
                  const mergedReps = cleanReps.some((r) => r.id === incoming.id)
                    ? cleanReps.map((r) => (r.id === incoming.id ? incoming : r))
                    : [...cleanReps, incoming];
                  nextThreads[ridKey] = {
                    ...td,
                    root: parsed.parent_root || { ...td.root, reply_count: mergedReps.length },
                    replies: mergedReps,
                  };
                }
              }
              return {
                ...prev,
                channels_messages: { ...prev.channels_messages, [cid]: nextList },
                threads_by_root: nextThreads,
              };
            });
            return;
          }
        } catch {}
        refreshBootstrap(querySuffix);
      });
    }, 250);
    return () => {
      clearTimeout(timer);
      es?.close();
    };
  }, [querySuffix, refreshBootstrap, fireNativeDmNotification]);

  const handleToggleReaction = useCallback(
    async (messageId: number, emoji: string) => {
      if (!boot) return;
      const actorId = boot.viewer.id;

      setBoot((prev) => {
        if (!prev) return prev;
        const patchMsg = (m: BoardMessage): BoardMessage =>
          m.id === messageId ? { ...m, reactions: toggleReactionsArray(m.reactions, emoji, actorId) } : m;

        const nextChMsgs: Record<string, BoardMessage[]> = {};
        for (const [cid, list] of Object.entries(prev.channels_messages)) {
          nextChMsgs[cid] = list.map(patchMsg);
        }
        const nextThreads: Record<string, ThreadDetail> = {};
        for (const [rid, td] of Object.entries(prev.threads_by_root)) {
          nextThreads[rid] = {
            ...td,
            root: patchMsg(td.root),
            replies: td.replies.map(patchMsg),
          };
        }
        return {
          ...prev,
          channels_messages: nextChMsgs,
          threads_by_root: nextThreads,
          subscribed_threads: prev.subscribed_threads.map(patchMsg),
        };
      });

      await fetch(`/api/messages/${messageId}/react${querySuffix}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-Atelier-CSRF': boot?.csrf_token || '' },
        body: JSON.stringify({ viewer_id: actorId, emoji }),
      });
    },
    [boot]
  );

  const toggleGuestPreview = () => {
    const gch = boot?.default_guest_channel_id;
    if (!gch && viewerQuery !== 'guest_preview') {
      setShowAccessModal(true);
      showToast('Select an external guest channel first to preview guest mode');
      return;
    }
    const next = viewerQuery === 'guest_preview' ? '' : 'guest_preview';
    setViewerQuery(next);
    if (next === 'guest_preview' && gch) {
      setRailTab('home');
      setCenterMode('channel');
      setActiveChannelId(gch);
      setOpenThreadId(null);
      setMobileTab('home');
      setStackDepth(0);
    }
  };

  const openChannel = useCallback(
    (cid: string) => {
      setActiveChannelId(cid);
      setRailTab('home');
      setCenterMode('channel');
      setOpenThreadId(null);
      setLayer1Mode('channel');
      setStackDepth(1);
      setBoot((prev) => {
        if (!prev) return prev;
        return {
          ...prev,
          channels: prev.channels.map((c) =>
            c.id === cid ? { ...c, unread_count: 0, mention_count: 0 } : c
          ),
        };
      });
      requestAnimationFrame(() => {
        if (feedRef.current) feedRef.current.scrollTop = feedRef.current.scrollHeight;
      });
      fetch(`/api/channels/${encodeURIComponent(cid)}/read${querySuffix}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-Atelier-CSRF': boot?.csrf_token || '' },
        body: '{}',
      }).catch(() => {});
    },
    [querySuffix, boot?.csrf_token]
  );

  const openThread = useCallback((rootId: number) => {
    setOpenThreadId(rootId);
    setStackDepth(2);
    requestAnimationFrame(() => {
      if (threadFeedRef.current) threadFeedRef.current.scrollTop = 0;
    });
  }, []);

  const handleSelectChannelLink = useCallback(
    (slug: string) => {
      if (!boot) return;
      const clean = slug.replace(/^#/, '').toLowerCase();
      const exists =
        boot.channels.find((c) => c.id === clean || c.raw_name.toLowerCase() === clean) ||
        boot.explorable_channels.find((c) => c.id === clean || c.raw_name.toLowerCase() === clean);
      if (exists) {
        openChannel(exists.id);
      } else {
        showToast(`#${clean} is not accessible`);
      }
    },
    [boot, openChannel, showToast]
  );

  const handleSelectMentionLink = useCallback(
    async (rawHandle: string) => {
      if (!boot || boot.viewer.role === 'guest') return;
      const clean = rawHandle.replace(/^@/, '').toLowerCase();
      const target = Object.values(boot.principals).find(
        (p) => p.id.toLowerCase() === clean || p.display_name.toLowerCase() === clean
      );
      if (!target) {
        showToast(`@${rawHandle} is not in this workspace`);
        return;
      }
      if (target.id === boot.viewer.id) return;
      if (target.role === 'guest') {
        if (target.guest_channel_id) openChannel(target.guest_channel_id);
        return;
      }
      const existingDm = boot.channels.find(
        (c) => c.kind === 'dm' && c.member_ids.includes(target.id) && c.member_ids.includes(boot.viewer.id)
      );
      if (existingDm) {
        openChannel(existingDm.id);
      }
    },
    [boot, openChannel, showToast]
  );

  const markNotificationRead = useCallback(
    (notifId: number) => {
      setBoot((prev) =>
        prev
          ? {
              ...prev,
              notifications: prev.notifications.map((n) =>
                n.id === notifId ? { ...n, unread: false } : n
              ),
            }
          : prev
      );
      fetch(`/api/notifications/${notifId}/read${querySuffix}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-Atelier-CSRF': boot?.csrf_token || '' },
        body: '{}',
      }).catch(() => {});
    },
    [querySuffix, boot?.csrf_token]
  );

  const markAllNotificationsRead = useCallback(() => {
    setBoot((prev) =>
      prev
        ? {
            ...prev,
            notifications: prev.notifications.map((n) => ({ ...n, unread: false })),
          }
        : prev
    );
    fetch(`/api/notifications/read-all${querySuffix}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-Atelier-CSRF': boot?.csrf_token || '' },
      body: '{}',
    }).catch(() => {});
    showToast('Marked all notifications as read');
  }, [querySuffix, boot?.csrf_token, showToast]);

  const loadEarlierMessages = useCallback(async () => {
    if (!boot) return;
    const list = boot.channels_messages[activeChannelId] || [];
    const oldest = list.find((m) => m.id > 0);
    if (!oldest) return;
    const res = await fetch(
      `/api/channels/${encodeURIComponent(activeChannelId)}/messages?before=${oldest.id}&limit=100${
        querySuffix ? `&${querySuffix.slice(1)}` : ''
      }`
    );
    if (!res.ok) return;
    const data = await res.json();
    const older: BoardMessage[] = data.messages || [];
    setBoot((prev) => {
      if (!prev) return prev;
      const existing = prev.channels_messages[activeChannelId] || [];
      const seen = new Set(existing.map((m) => m.id));
      const merged = [...older.filter((m) => !seen.has(m.id)), ...existing];
      return {
        ...prev,
        channels: prev.channels.map((c) =>
          c.id === activeChannelId ? { ...c, has_more: older.length >= 100 } : c
        ),
        channels_messages: { ...prev.channels_messages, [activeChannelId]: merged },
      };
    });
  }, [boot, activeChannelId, querySuffix]);

  const configureGuestChannel = useCallback(
    async (nextChannelId: string) => {
      if (!boot) return;
      const res = await fetch(`/api/settings/guest-channel${querySuffix}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-Atelier-CSRF': boot.csrf_token || '' },
        body: JSON.stringify({ channel_id: nextChannelId || null }),
      });
      if (res.ok) {
        await refreshBootstrap(querySuffix);
        showToast(nextChannelId ? `External guests scoped to #${nextChannelId}` : 'External guest access disabled');
      }
    },
    [boot, querySuffix, refreshBootstrap, showToast]
  );

  const handleOpenSheet = useCallback((msg: BoardMessage, mode: 'reactions' | 'actions') => {
    setSheetState({ msg, mode });
  }, []);

  /* Full-Screen Native Horizontal Right-Swipe Back Gesture (works anywhere on screen when swiping horizontally!) */
  const handleStackTouchStart = (e: React.TouchEvent) => {
    if (stackDepth === 0 || sheetState) return;
    const t = e.touches[0];
    if (!t) return;
    swipeRef.current = { startX: t.clientX, startY: t.clientY, startTime: performance.now(), mode: 'undecided' };
  };

  const handleStackTouchMove = (e: React.TouchEvent) => {
    const s = swipeRef.current;
    if (!s || stackDepth === 0 || sheetState) return;
    const t = e.touches[0];
    if (!t) return;
    const dx = t.clientX - s.startX;
    const dy = t.clientY - s.startY;
    if (s.mode === 'undecided') {
      if (Math.abs(dy) > 10 && Math.abs(dy) >= Math.abs(dx) * 0.75) {
        s.mode = 'scroll';
        return;
      }
      if (dx > 14 && dx > Math.abs(dy) * 1.5) {
        s.mode = 'swipe';
        setIsSwiping(true);
      }
    }
    if (s.mode === 'swipe') {
      setSwipeDx(Math.max(0, dx));
    }
  };

  const handleStackTouchEnd = () => {
    const s = swipeRef.current;
    swipeRef.current = null;
    if (!s || s.mode !== 'swipe') {
      setIsSwiping(false);
      setSwipeDx(0);
      return;
    }
    const elapsed = Math.max(1, performance.now() - s.startTime);
    const velocity = swipeDx / elapsed;
    const w = window.innerWidth || 393;
    if (swipeDx > w * 0.28 || velocity > 0.45) {
      if (stackDepth === 2) {
        setStackDepth(1);
        setOpenThreadId(null);
      } else {
        setStackDepth(0);
      }
    }
    setIsSwiping(false);
    setSwipeDx(0);
  };

  const handleApproveFork = async (branch: string, rootId: number) => {
    setApprovedBranches((prev) => ({ ...prev, [branch]: true }));
    showToast(`Approved ${branch}`);
    await fetch(`/api/messages${querySuffix}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-Atelier-CSRF': boot?.csrf_token || '' },
      body: JSON.stringify({
        author_id: boot?.viewer.id,
        channel_id: boot?.default_guest_channel_id || activeChannelId,
        root_id: rootId,
        body: `@front-man Approved \`${branch}\` — run checks and merge into \`main\`.`,
      }),
    });
  };

  const submitChannelMessage = async (e: React.FormEvent) => {
    e.preventDefault();
    const text = draftBody.trim();
    if (!text || !boot) return;
    setDraftBody('');

    const nowSec = Date.now() / 1000;
    const tempId = -Math.floor(Math.random() * 1e9);
    const optimistic: BoardMessage = {
      id: tempId,
      channel_id: activeChannelId,
      root_id: null,
      also_channel: false,
      author_id: boot.viewer.id,
      author_role: boot.viewer.role,
      untrusted_guest: boot.viewer.role === 'guest',
      envelope_warning: null,
      body: text,
      meta: {},
      reactions: [],
      created_at: nowSec,
      reply_count: 0,
      last_reply_at: null,
      reply_authors: [],
      subscribed_ids: [boot.viewer.id],
      viewer_subscribed: true,
    };

    setBoot((prev) => {
      if (!prev) return prev;
      const cur = prev.channels_messages[activeChannelId] || [];
      return {
        ...prev,
        channels_messages: { ...prev.channels_messages, [activeChannelId]: [...cur, optimistic] },
      };
    });

    requestAnimationFrame(() => {
      if (feedRef.current) feedRef.current.scrollTop = feedRef.current.scrollHeight;
    });

    await fetch(`/api/messages${querySuffix}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-Atelier-CSRF': boot?.csrf_token || '' },
      body: JSON.stringify({ author_id: boot.viewer.id, channel_id: activeChannelId, body: text }),
    });
  };

  const submitThreadReply = async (e: React.FormEvent) => {
    e.preventDefault();
    const text = threadDraft.trim();
    if (!text || openThreadId === null || !boot) return;
    setThreadDraft('');

    const nowSec = Date.now() / 1000;
    const tempId = -Math.floor(Math.random() * 1e9);
    const existingTd = boot.threads_by_root[String(openThreadId)];
    const chId = existingTd?.channel.id || activeChannelId;

    const optimisticReply: BoardMessage = {
      id: tempId,
      channel_id: chId,
      root_id: openThreadId,
      also_channel: alsoSendChannel,
      author_id: boot.viewer.id,
      author_role: boot.viewer.role,
      untrusted_guest: boot.viewer.role === 'guest',
      envelope_warning: null,
      body: text,
      meta: {},
      reactions: [],
      created_at: nowSec,
      reply_count: 0,
      last_reply_at: null,
      reply_authors: [],
      subscribed_ids: [],
      viewer_subscribed: true,
    };

    setBoot((prev) => {
      if (!prev) return prev;
      const curTd = prev.threads_by_root[String(openThreadId)];
      const rootMsg = curTd?.root || (prev.channels_messages[chId] || []).find((m) => m.id === openThreadId);
      if (!rootMsg) return prev;
      const updatedRoot: BoardMessage = {
        ...rootMsg,
        reply_count: rootMsg.reply_count + 1,
        last_reply_at: nowSec,
        reply_authors: rootMsg.reply_authors.includes(boot.viewer.id)
          ? rootMsg.reply_authors
          : [...rootMsg.reply_authors, boot.viewer.id],
      };
      const chObj = curTd?.channel || prev.channels.find((c) => c.id === chId) || prev.channels[0]!;
      return {
        ...prev,
        channels_messages: {
          ...prev.channels_messages,
          [chId]: (prev.channels_messages[chId] || []).map((m) => (m.id === openThreadId ? updatedRoot : m)),
        },
        threads_by_root: {
          ...prev.threads_by_root,
          [String(openThreadId)]: {
            channel: chObj,
            root: updatedRoot,
            replies: [...(curTd?.replies || []), optimisticReply],
            subscribers: curTd?.subscribers || [{ principal_id: boot.viewer.id, reason: 'replied' }],
          },
        },
      };
    });

    requestAnimationFrame(() => {
      if (threadFeedRef.current) threadFeedRef.current.scrollTop = threadFeedRef.current.scrollHeight;
    });

    await fetch(`/api/messages${querySuffix}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-Atelier-CSRF': boot?.csrf_token || '' },
      body: JSON.stringify({
        author_id: boot.viewer.id,
        channel_id: chId,
        root_id: openThreadId,
        also_channel: alsoSendChannel,
        body: text,
      }),
    });
  };

  const submitNewChannel = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newChName.trim() || !boot) return;
    const res = await fetch(`/api/channels${querySuffix}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-Atelier-CSRF': boot?.csrf_token || '' },
      body: JSON.stringify({ creator_id: boot.viewer.id, name: newChName, kind: newChKind, topic: newChTopic, guest_allowed: newChGuestAllowed }),
    });
    if (res.ok) {
      const data = await res.json();
      setShowNewChannelModal(false);
      await refreshBootstrap(querySuffix);
      openChannel(data.channel.id);
    }
  };

  const threadDetail: ThreadDetail | null = useMemo(() => {
    if (!boot || openThreadId === null) return null;
    const hit = boot.threads_by_root[String(openThreadId)];
    if (hit) return hit;
    for (const [cid, list] of Object.entries(boot.channels_messages)) {
      const found = list.find((m) => m.id === openThreadId);
      if (found) {
        const ch =
          boot.channels.find((c) => c.id === cid) ||
          boot.explorable_channels.find((c) => c.id === cid) ||
          boot.channels[0]!;
        return {
          channel: ch,
          root: found,
          replies: [],
          subscribers: [{ principal_id: found.author_id, reason: 'starter' }],
        };
      }
    }
    return null;
  }, [openThreadId, boot]);

  const activeSheetMsg: BoardMessage | null = useMemo(() => {
    if (!sheetState || !boot) return null;
    const targetId = sheetState.msg.id;
    for (const list of Object.values(boot.channels_messages)) {
      const hit = list.find((m) => m.id === targetId);
      if (hit) return hit;
    }
    for (const td of Object.values(boot.threads_by_root)) {
      if (td.root.id === targetId) return td.root;
      const rhit = td.replies.find((m) => m.id === targetId);
      if (rhit) return rhit;
    }
    return sheetState.msg;
  }, [sheetState, boot]);

  if (!boot) return <div className="sl-boot" />;

  const { viewer, principals, channels, explorable_channels, notifications, subscribed_threads, security } = boot;
  const activeChannelMeta: ChannelSummary | undefined =
    channels.find((c) => c.id === activeChannelId) ||
    explorable_channels.find((c) => c.id === activeChannelId);
  const channelMessages: BoardMessage[] = boot.channels_messages[activeChannelId] || [];

  const isGuest = viewer.role === 'guest';
  const sidebarChannels = channels.filter((c) => c.kind === 'public' || c.kind === 'private');
  const mentionChannels = sidebarChannels.filter((c) => c.mention_count > 0);
  const regularChannels = sidebarChannels.filter((c) => c.mention_count === 0);
  const dmChannels = channels.filter((c) => c.kind === 'dm');
  const unreadActivity = notifications.filter((n) => n.unread).length;
  const activeAgentsCount = Object.values(principals).filter(
    (p) => p.kind === 'agent' && p.role !== 'guest' && p.status === 'active'
  ).length;

  const guestBridgeChannelId = boot.default_guest_channel_id || null;

  const filteredNotifications = notifications.filter((n) => {
    if (activityFilter === 'unreads') return n.unread;
    if (activityFilter === 'dms') return n.kind === 'dm';
    if (activityFilter === 'mentions') return n.kind === 'mention' || n.kind === 'guest_triage';
    if (activityFilter === 'threads') return n.kind === 'thread_reply';
    return true;
  });

  const internalPeers = Object.values(principals).filter((p) => p.role !== 'guest' && p.id !== viewer.id);
  const filteredPeers = internalPeers.filter((p) => {
    if (dmFilter === 'agents') return p.kind === 'agent';
    if (dmFilter === 'unreads') {
      const dm = dmChannels.find((d) => d.member_ids.includes(p.id));
      return Boolean(dm && dm.unread_count > 0);
    }
    return true;
  });

  const qNorm = searchQuery.trim().toLowerCase();
  const searchChannels = explorable_channels.filter(
    (c) => !qNorm || c.name.toLowerCase().includes(qNorm) || c.topic.toLowerCase().includes(qNorm)
  );
  const searchMessages: BoardMessage[] = [];
  if (qNorm.length >= 2) {
    for (const list of Object.values(boot.channels_messages)) {
      for (const m of list) {
        if (m.body.toLowerCase().includes(qNorm)) searchMessages.push(m);
      }
    }
  }

  const isMobileMode = nativeMobile || simulateMobileOnDesktop;
  const beamPreset: BeamPreset = isMobileMode
    ? stackDepth === 0
      ? 'floor-mirrored'
      : 'floor'
    : centerMode === 'all-channels'
    ? 'sweep'
    : 'edge';

  const onboardingCommand = `uv run atelier board connect ${window.location.origin}`;



  const toastBanner = toastText && <div className="ios-toast">{toastText}</div>;

  const searchModal = showSearchModal && (
    <div className="sl-modal-veil" onClick={() => setShowSearchModal(false)}>
      <div className="sl-modal search-palette" onClick={(e) => e.stopPropagation()}>
        <div className="palette-input-row">
          <IcoSearch />
          <input
            type="text"
            autoFocus
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Jump to channel, agent, or message…"
          />
          <button type="button" className="palette-esc" onClick={() => setShowSearchModal(false)}>
            ESC
          </button>
        </div>
        <div className="palette-results">
          <div className="palette-sec">Channels</div>
          {searchChannels.slice(0, 6).map((ch) => (
            <button
              key={ch.id}
              type="button"
              className="palette-item"
              onClick={() => {
                setShowSearchModal(false);
                setSearchQuery('');
                openChannel(ch.id);
              }}
            >
              <span className="palette-hash">#</span>
              <strong>{ch.name}</strong>
              <span className="palette-sub">{ch.topic}</span>
            </button>
          ))}
          {!isGuest && (
            <>
              <div className="palette-sec">Agents & Direct Messages</div>
              {internalPeers
                .filter((p) => !qNorm || p.display_name.toLowerCase().includes(qNorm))
                .map((p) => {
                  const dm = dmChannels.find((d) => d.member_ids.includes(p.id));
                  return (
                    <button
                      key={p.id}
                      type="button"
                      className="palette-item"
                      onClick={() => {
                        setShowSearchModal(false);
                        setSearchQuery('');
                        if (dm) openChannel(dm.id);
                      }}
                    >
                      <Avatar principal={p} id={p.id} size="xs" showDot />
                      <strong>{p.display_name}</strong>
                      <span className="palette-sub">{p.status_text}</span>
                    </button>
                  );
                })}
            </>
          )}
          {searchMessages.length > 0 && (
            <>
              <div className="palette-sec">Messages</div>
              {searchMessages.slice(0, 5).map((m) => (
                <button
                  key={m.id}
                  type="button"
                  className="palette-item"
                  onClick={() => {
                    setShowSearchModal(false);
                    setSearchQuery('');
                    openChannel(m.channel_id);
                    openThread(m.root_id || m.id);
                  }}
                >
                  <span className="palette-hash">#{m.channel_id}</span>
                  <span className="palette-sub">{m.body.slice(0, 70)}</span>
                </button>
              ))}
            </>
          )}
        </div>
      </div>
    </div>
  );

  const accessModal = showAccessModal && (
    <div className="sl-modal-veil" onClick={() => setShowAccessModal(false)}>
      <div className="sl-modal wide" onClick={(e) => e.stopPropagation()}>
        <div className="sl-modal-head">
          <h3>Tailnet Security & Brother Onboarding</h3>
          <button type="button" className="sl-close" onClick={() => setShowAccessModal(false)}>×</button>
        </div>

        <div className="sec-tier-list">
          <div className="sec-tier">
            <div className="sec-tier-title">1. Agents on Your MacBook → Auto Full Workspace Member</div>
            <p>
              Local processes read <code>~/.cache/atelier/board/local.secret</code> (<code>chmod 0600</code> owner-only)
              and join all public channels automatically with zero setup.
            </p>
          </div>

          <div className="sec-tier">
            <div className="sec-tier-title">2. Tailscale Account ({security?.owner_login || viewer.display_name}) → Owner</div>
            <p>
              Human identity comes directly from Tailscale (<code>Tailscale-User-Login</code> + <code>tailscale whois</code>{' '}
              <code>UserProfile</code>). Active session: <strong>{viewer.display_name}</strong> on{' '}
              <code>{security?.detected_node || 'local'}</code>.
            </p>
          </div>

          <div className="sec-tier amber">
            <div className="sec-tier-title">3. External Tailscale Collaborators → Optional Single-Channel Guest</div>
            <p>
              External Tailscale accounts have <strong>no access by default</strong>. If you designate one guest bridge
              channel below, external collaborators and their agents are automatically jailed strictly to that single
              channel (no DMs, no internal channels, cannot wake worker agents).
            </p>
            {viewer.role === 'owner' && (
              <div className="sec-guest-select-row">
                <label htmlFor="guest-ch-select">External guest channel:</label>
                <select
                  id="guest-ch-select"
                  value={guestBridgeChannelId || ''}
                  onChange={(e) => configureGuestChannel(e.target.value)}
                >
                  <option value="">Disabled (Deny external Tailscale accounts)</option>
                  {sidebarChannels
                    .filter((c) => c.kind === 'public')
                    .map((c) => (
                      <option key={c.id} value={c.id}>
                        #{c.name}
                      </option>
                    ))}
                </select>
              </div>
            )}
            <div className="sec-copy-box">
              <code>{onboardingCommand}</code>
              <button
                type="button"
                className="sl-btn sl-btn-primary"
                onClick={() => {
                  navigator.clipboard?.writeText(onboardingCommand).catch(() => {});
                  setCopiedOnboarding(true);
                  setTimeout(() => setCopiedOnboarding(false), 1800);
                }}
              >
                {copiedOnboarding ? 'Copied ✓' : 'Copy'}
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );

  const diffModal = diffModalBranch && (
    <div className="sl-modal-veil" onClick={() => setDiffModalBranch(null)}>
      <div className="sl-modal wide" onClick={(e) => e.stopPropagation()}>
        <div className="sl-modal-head">
          <h3>{diffModalBranch}</h3>
          <button type="button" className="sl-close" onClick={() => setDiffModalBranch(null)}>×</button>
        </div>
        <p className="sl-modal-sub">fork/atelier · 91c4e02d rebased on a3b145ff2b · 0 C++ files touched</p>
        <div className="sl-diff-list">
          <div><span>M</span><code>content/data/belmonte_train/platforms.json</code><em>+42 −6</em></div>
          <div><span>M</span><code>content/data/belmonte_train/service.json</code><em>+8 −2</em></div>
          <div><span>A</span><code>content/assets/adopted/belmonte/SM_PlatformBench_A.toml</code><em>+31 −0</em></div>
          <div><span>A</span><code>content/assets/adopted/belmonte/SM_StationClock.toml</code><em>+29 −0</em></div>
        </div>
        <div className="sl-modal-foot">
          <button type="button" className="sl-btn sl-btn-primary" onClick={() => setDiffModalBranch(null)}>Close</button>
        </div>
      </div>
    </div>
  );

  // ==================== NATIVE-GRADE SLACK iOS 26 MOBILE UI ====================
  if (isMobileMode) {
    const activeDockIdx = isGuest
      ? mobileTab === 'home' ? 0 : 1
      : mobileTab === 'home' ? 0 : mobileTab === 'dms' ? 1 : 2;

    const wPx = window.innerWidth || 393;
    const swipeRatio = isSwiping ? Math.min(1, swipeDx / wPx) : 0;

    const layer0Transform =
      stackDepth === 0
        ? 'translate3d(0px, 0, 0)'
        : stackDepth === 1 && isSwiping
        ? `translate3d(${(-28 * (1 - swipeRatio)).toFixed(2)}%, 0, 0)`
        : 'translate3d(-28%, 0, 0)';

    const layer1Transform =
      stackDepth === 0
        ? 'translate3d(100%, 0, 0)'
        : stackDepth === 1
        ? isSwiping
          ? `translate3d(${swipeDx.toFixed(1)}px, 0, 0)`
          : 'translate3d(0px, 0, 0)'
        : isSwiping
        ? `translate3d(${(-28 * (1 - swipeRatio)).toFixed(2)}%, 0, 0)`
        : 'translate3d(-28%, 0, 0)';

    const layer2Transform =
      stackDepth < 2
        ? 'translate3d(100%, 0, 0)'
        : isSwiping
        ? `translate3d(${swipeDx.toFixed(1)}px, 0, 0)`
        : 'translate3d(0px, 0, 0)';

    const phoneApp = (
      <div
        className={`slm-app ${simulateMobileOnDesktop && !nativeMobile ? 'is-framed' : ''} ${
          keyboardOpen ? 'kb-open' : ''
        } ${isSwiping ? 'swiping' : ''}`}
        onTouchStart={handleStackTouchStart}
        onTouchMove={handleStackTouchMove}
        onTouchEnd={handleStackTouchEnd}
        onTouchCancel={handleStackTouchEnd}
      >
        <DitherBeam preset={beamPreset} />
        {toastBanner}

        {/* ========== LAYER 0: PERSISTENT ROOT TABS ========== */}
        <div
          className={`nav-layer layer-0 ${stackDepth > 0 ? 'underneath' : ''}`}
          style={{ transform: layer0Transform }}
        >
          <header className="ios-top-header">
            <div className="ios-ws-title-row">
              {mobileTab === 'home' && <span className="ios-ws-badge">A</span>}
              <h1 className="ios-big-title">
                {mobileTab === 'home' ? 'Atelier' : mobileTab === 'dms' ? 'DMs' : 'Activity'}
              </h1>
            </div>

            <div className="ios-header-pills">
              {!isGuest && viewer.kind === 'human' && (
                <button
                  type="button"
                  className={`ios-shield-btn ${dmNotifyEnabled ? 'notify-on' : ''}`}
                  aria-label={dmNotifyEnabled ? 'DM notifications on' : 'Enable DM browser notifications'}
                  title={dmNotifyEnabled ? 'DM browser notifications ON' : 'Opt in to native DM browser notifications'}
                  onClick={toggleDmBrowserNotifications}
                >
                  <IcoBell filled={dmNotifyEnabled} />
                </button>
              )}
              {!isGuest && (
                <button
                  type="button"
                  className="ios-shield-btn"
                  aria-label="Tailnet Security"
                  onClick={() => setShowAccessModal(true)}
                >
                  <IcoShield />
                </button>
              )}
              {(viewer.role === 'owner' || viewerQuery === 'guest_preview') ? (
                <button type="button" className="ios-profile-capsule" onClick={toggleGuestPreview}>
                  <span className="ios-role-label">{isGuest ? 'Guest Preview' : viewer.display_name.split(' ')[0]}</span>
                  <Avatar principal={viewer} id={viewer.id} size="xs" showDot />
                </button>
              ) : (
                <div className="ios-profile-capsule">
                  <span className="ios-role-label">{viewer.display_name}</span>
                  <Avatar principal={viewer} id={viewer.id} size="xs" showDot />
                </div>
              )}
            </div>
          </header>

          {mobileTab === 'home' && (
            <div className="slm-scroll with-dock">
              {!isGuest && (
                <div className="ios-summary-tiles">
                  <button type="button" className="ios-tile" onClick={() => setMobileTab('activity')}>
                    <span className="ios-tile-ico has-dot"><IcoCatchUp /></span>
                    <strong>Catch Up</strong>
                    <span>{unreadActivity} new</span>
                  </button>
                  <button
                    type="button"
                    className="ios-tile"
                    onClick={() => {
                      setLayer1Mode('threads-list');
                      setStackDepth(1);
                    }}
                  >
                    <span className="ios-tile-ico"><IcoThreads /></span>
                    <strong>Threads</strong>
                    <span>{subscribed_threads.length} active</span>
                  </button>
                  <button
                    type="button"
                    className="ios-tile"
                    onClick={() => {
                      if (guestBridgeChannelId) {
                        openChannel(guestBridgeChannelId);
                      } else {
                        setLayer1Mode('all-channels');
                        setStackDepth(1);
                      }
                    }}
                  >
                    <span className="ios-tile-ico"><IcoBranch /></span>
                    <strong>{guestBridgeChannelId ? `#${guestBridgeChannelId}` : 'Channels'}</strong>
                    <span>{guestBridgeChannelId ? 'Guest bridge' : `${explorable_channels.length} public`}</span>
                  </button>
                  <button type="button" className="ios-tile" onClick={() => setMobileTab('dms')}>
                    <span className="ios-tile-ico"><IcoAgents /></span>
                    <strong>Agents</strong>
                    <span>{activeAgentsCount} active</span>
                  </button>
                </div>
              )}

              {isGuest && (
                <div className="slm-guest-banner">
                  Single-channel guest · Scoped strictly to <strong>#{viewer.guest_channel_id}</strong>
                </div>
              )}

              {mentionChannels.length > 0 && (
                <div className="ios-section">
                  <button
                    type="button"
                    className="ios-sec-header"
                    onClick={() => setCollapsedSections((p) => ({ ...p, mentions: !p.mentions }))}
                  >
                    <span className="ios-at-sym">@</span>
                    <span className="ios-sec-title">Mentions ›</span>
                    <span className={`ios-chev ${collapsedSections.mentions ? 'collapsed' : ''}`}>⌃</span>
                  </button>
                  {!collapsedSections.mentions &&
                    mentionChannels.map((ch) => (
                      <button key={ch.id} type="button" className="ios-ch-row bold" onClick={() => openChannel(ch.id)}>
                        <span className="ios-hash">{ch.kind === 'private' ? <IcoLock /> : '#'}</span>
                        <span className="ios-ch-label">{ch.name}</span>
                        <span className="ios-count-badge">{ch.mention_count}</span>
                      </button>
                    ))}
                </div>
              )}

              <div className="ios-section">
                <div className="ios-sec-header">
                  <span
                    className="ios-sec-title"
                    onClick={() => setCollapsedSections((p) => ({ ...p, channels: !p.channels }))}
                  >
                    {isGuest ? 'Shared channel ›' : 'Channels ›'}
                  </span>
                  {!isGuest && (
                    <span className="ios-sec-actions">
                      <b onClick={() => setShowNewChannelModal(true)}>+</b>
                      <span
                        className={`ios-chev ${collapsedSections.channels ? 'collapsed' : ''}`}
                        onClick={() => setCollapsedSections((p) => ({ ...p, channels: !p.channels }))}
                      >
                        ⌃
                      </span>
                    </span>
                  )}
                </div>
                {!collapsedSections.channels &&
                  (isGuest ? sidebarChannels : regularChannels).map((ch) => (
                    <button
                      key={ch.id}
                      type="button"
                      className={`ios-ch-row ${ch.unread_count > 0 ? 'bold' : ''}`}
                      onClick={() => openChannel(ch.id)}
                    >
                      <span className="ios-hash">{ch.kind === 'private' ? <IcoLock /> : '#'}</span>
                      <span className="ios-ch-label">{ch.name}</span>
                      {ch.unread_count > 0 && <span className="ios-unread-dot" />}
                    </button>
                  ))}
                {!isGuest &&
                  !collapsedSections.channels &&
                  internalPeers.slice(0, 2).map((p) => {
                    const dm = dmChannels.find((d) => d.member_ids.includes(p.id));
                    return (
                      <button key={p.id} type="button" className="ios-ch-row bold" onClick={() => dm && openChannel(dm.id)}>
                        <Avatar principal={p} id={p.id} size="xs" />
                        <span className="ios-ch-label">{p.display_name}</span>
                        {p.kind === 'agent' && <span className="sl-app-tag">AGENT</span>}
                        {dm && dm.unread_count > 0 && <span className="ios-count-badge">{dm.unread_count}</span>}
                      </button>
                    );
                  })}
              </div>

              {!isGuest && (
                <button
                  type="button"
                  className="ios-plus-fab"
                  aria-label="New channel"
                  onClick={() => setShowNewChannelModal(true)}
                >
                  +
                </button>
              )}
            </div>
          )}

          {mobileTab === 'dms' && !isGuest && (
            <div className="slm-scroll with-dock">
              <div className="ios-dm-strip">
                {Object.values(principals)
                  .filter((p) => p.role !== 'guest')
                  .map((p) => {
                    const dm = dmChannels.find((d) => d.member_ids.includes(p.id) && p.id !== viewer.id);
                    return (
                      <button key={p.id} type="button" className="ios-dm-avatar-col" onClick={() => dm && openChannel(dm.id)}>
                        <Avatar principal={p} id={p.id} size="xl" showDot />
                        <span className="ios-dm-short">{p.display_name}</span>
                      </button>
                    );
                  })}
              </div>

              <div className="ios-chip-row">
                <button type="button" className={dmFilter === 'all' ? 'active' : ''} onClick={() => setDmFilter('all')}>All</button>
                <button type="button" className={dmFilter === 'agents' ? 'active' : ''} onClick={() => setDmFilter('agents')}>Agents</button>
                <button type="button" className={dmFilter === 'unreads' ? 'active' : ''} onClick={() => setDmFilter('unreads')}>Unreads</button>
              </div>

              <div className="ios-dm-list">
                {filteredPeers.map((p) => {
                  const dm = dmChannels.find((d) => d.member_ids.includes(p.id));
                  return (
                    <button key={p.id} type="button" className="ios-dm-item" onClick={() => dm && openChannel(dm.id)}>
                      <Avatar principal={p} id={p.id} size="lg" showDot />
                      <div className="ios-dm-body">
                        <div className="ios-dm-top">
                          <strong>{p.display_name}</strong>
                          {p.kind === 'agent' && <span className="sl-app-tag">AGENT</span>}
                          <time>{dm && dm.unread_count > 0 ? '5:31 PM' : 'Today'}</time>
                        </div>
                        <div className="ios-dm-preview">
                          {p.id === 'front-man'
                            ? p.status_text
                            : p.status_text}
                        </div>
                      </div>
                    </button>
                  );
                })}
              </div>

              <button type="button" className="ios-plus-fab" onClick={() => dmChannels[0] && openChannel(dmChannels[0].id)}>+</button>
            </div>
          )}

          {mobileTab === 'activity' && (
            <div className="slm-scroll with-dock">
              <div className="ios-act-toolbar">
                <div className="ios-chip-row">
                  {(['all', 'unreads', 'mentions', 'threads'] as const).map((f) => (
                    <button key={f} type="button" className={activityFilter === f ? 'active' : ''} onClick={() => setActivityFilter(f)}>
                      {f === 'all'
                        ? 'All'
                        : f === 'unreads'
                        ? `Unreads (${unreadActivity})`
                        : f === 'mentions'
                        ? 'Mentions'
                        : 'Threads'}
                    </button>
                  ))}
                </div>
                {unreadActivity > 0 && (
                  <button type="button" className="sl-mark-read-btn" onClick={markAllNotificationsRead}>
                    Mark all read
                  </button>
                )}
              </div>

              <div className="ios-act-list">
                {filteredNotifications.map((n: NotificationItem) => (
                  <button
                    key={n.id}
                    type="button"
                    className={`ios-act-item ${n.unread ? 'is-unread' : 'is-read'}`}
                    onClick={() => {
                      if (n.unread) markNotificationRead(n.id);
                      setActiveChannelId(n.channel_id);
                      setLayer1Mode('channel');
                      openThread(n.root_id);
                    }}
                  >
                    <Avatar
                      principal={principals[n.author_id]}
                      id={n.author_id}
                      size="lg"
                      cornerBadge={n.kind === 'mention' ? '@' : 'thread'}
                    />
                    <div className="ios-act-main">
                      <div className="ios-act-line1">
                        {n.unread && <span className="sl-unread-dot" aria-label="Unread" />}
                        <strong>{principals[n.author_id]?.display_name || n.author_id}</strong>
                        {n.unread && <span className="sl-new-pill">NEW</span>}
                        {principals[n.author_id]?.kind === 'agent' && !n.untrusted_envelope && (
                          <span className="sl-app-tag">AGENT</span>
                        )}
                        {n.untrusted_envelope && <span className="sl-app-tag tag-guest">GUEST</span>}
                        <span className="ios-act-right">
                          <time>{formatRelative(n.created_at)}</time>
                        </span>
                      </div>
                      <div className="ios-act-sub">
                        {n.kind === 'mention'
                          ? `Mention in #${n.channel_name}`
                          : n.kind === 'dm'
                          ? 'Direct message'
                          : `Thread in #${n.channel_name}`}
                      </div>
                      <div className="ios-act-snippet">{renderSlackMarkdown(n.body, viewer.id)}</div>
                    </div>
                  </button>
                ))}
              </div>
            </div>
          )}

          <div className="ios-bottom-scrim" aria-hidden="true" />
          <div className="ios-dock-row">
            <nav
              className={`ios-pill-dock ${isGuest ? 'cols-2' : 'cols-3'}`}
              style={{ '--tab-idx': activeDockIdx } as React.CSSProperties}
            >
              <span className="ios-dock-glider" aria-hidden="true" />
              <button
                type="button"
                className={mobileTab === 'home' ? 'active' : ''}
                onClick={() => setMobileTab('home')}
              >
                <span className="ios-tab-ico">
                  <IcoHome filled={mobileTab === 'home'} />
                  {mentionChannels.length > 0 && <i className="ios-red-dot" />}
                </span>
                <span>Home</span>
              </button>

              {!isGuest && (
                <button
                  type="button"
                  className={mobileTab === 'dms' ? 'active' : ''}
                  onClick={() => setMobileTab('dms')}
                >
                  <span className="ios-tab-ico">
                    <IcoDMs filled={mobileTab === 'dms'} />
                  </span>
                  <span>DMs</span>
                </button>
              )}

              <button
                type="button"
                className={mobileTab === 'activity' ? 'active' : ''}
                onClick={() => setMobileTab('activity')}
              >
                <span className="ios-tab-ico">
                  <IcoBell filled={mobileTab === 'activity'} />
                  {unreadActivity > 0 && <i className="ios-red-dot" />}
                </span>
                <span>Activity</span>
              </button>
            </nav>

            <button
              type="button"
              className="ios-search-orb"
              aria-label="Search"
              onClick={() => setShowSearchModal(true)}
            >
              <IcoSearch />
            </button>
          </div>
        </div>

        {/* ========== LAYER 1: CHANNEL / THREADS-LIST / ALL-CHANNELS ========== */}
        <div
          className={`nav-layer layer-1 ${stackDepth === 2 ? 'underneath' : ''} ${stackDepth === 0 ? 'offscreen' : ''}`}
          style={{ transform: layer1Transform }}
        >
          <DitherBeam preset="floor" />
          <div className="ios-top-scrim" aria-hidden="true" />

          <header className="ios-floating-header">
            <button type="button" className="ios-back-orb" aria-label="Back" onClick={() => setStackDepth(0)}>
              ‹
            </button>

            <div className="ios-title-pill">
              <div className="ios-pill-main">
                {layer1Mode === 'threads-list'
                  ? 'Threads'
                  : layer1Mode === 'all-channels'
                  ? 'All channels'
                  : `${activeChannelMeta?.kind === 'private' ? '🔒 ' : activeChannelMeta?.kind === 'dm' ? '' : '#'}${
                      activeChannelMeta?.name || activeChannelId
                    }`}
              </div>
              <div className="ios-pill-sub">
                {layer1Mode === 'threads-list'
                  ? `${subscribed_threads.length} subscribed threads`
                  : layer1Mode === 'all-channels'
                  ? `${explorable_channels.length} public channels`
                  : activeChannelMeta?.guest_allowed
                  ? 'External guest bridge · data only'
                  : `${activeChannelMeta?.member_count || 2} members · Tap any message to thread`}
              </div>
            </div>
          </header>

          {layer1Mode === 'channel' ? (
            <>
              <div className="slm-feed ios-padded-top" ref={feedRef}>
                {activeChannelMeta?.has_more && (
                  <div className="sl-date-divider">
                    <button type="button" className="sl-btn" onClick={loadEarlierMessages}>
                      Load earlier messages
                    </button>
                  </div>
                )}
                <div className="sl-date-divider"><span>Today</span></div>
                {channelMessages.map((msg) => (
                  <SlackMessageRow
                    key={msg.id}
                    msg={msg}
                    principals={principals}
                    viewer={viewer}
                    isMobileMode={isMobileMode}
                    approvedBranches={approvedBranches}
                    onApproveFork={handleApproveFork}
                    onInspectDiff={setDiffModalBranch}
                    onToggleReaction={handleToggleReaction}
                    onOpenSheet={handleOpenSheet}
                    onSelectChannel={handleSelectChannelLink}
                    onSelectMention={handleSelectMentionLink}
                    onOpenThread={openThread}
                    isOptimistic={msg.id < 0}
                  />
                ))}
              </div>

              <div className="composer-rel-wrap">
                <MentionAutocomplete
                  query={detectMentionQuery(draftBody)}
                  principals={principals}
                  onSelect={(id) => setDraftBody((prev) => completeMention(prev, id))}
                />
                <form className={`ios-reply-capsule ${keyboardOpen ? 'kb-flush' : ''}`} onSubmit={submitChannelMessage}>
                  <button type="button" className="ios-cap-plus">+</button>
                  <input
                    type="text"
                    value={draftBody}
                    onFocus={() => onInputFocus(false)}
                    onChange={(e) => setDraftBody(e.target.value)}
                    placeholder={`Message #${activeChannelMeta?.name || activeChannelId}`}
                  />
                  <button type="submit" className="ios-cap-send" aria-label="Send">
                    <IcoSend />
                  </button>
                </form>
              </div>
            </>
          ) : (
            <div className="slm-scroll ios-padded-top">
              {layer1Mode === 'threads-list'
                ? subscribed_threads.map((th) => (
                    <div
                      key={th.id}
                      className="sl-thread-card"
                      onClick={() => {
                        setActiveChannelId(th.channel_id);
                        openThread(th.id);
                      }}
                    >
                      <div className="sl-thread-card-ch">#{th.channel_id}</div>
                      <SlackMessageRow
                        msg={th}
                        principals={principals}
                        viewer={viewer}
                        isMobileMode={isMobileMode}
                        approvedBranches={approvedBranches}
                        onApproveFork={handleApproveFork}
                        onInspectDiff={setDiffModalBranch}
                        onToggleReaction={handleToggleReaction}
                        onOpenSheet={handleOpenSheet}
                        inThread
                      />
                    </div>
                  ))
                : explorable_channels.map((ch) => (
                    <button key={ch.id} type="button" className="slm-browse-row" onClick={() => openChannel(ch.id)}>
                      <div className="slm-browse-name">#{ch.name}</div>
                      <div className="slm-browse-sub">{ch.member_count} members · {ch.topic}</div>
                    </button>
                  ))}
            </div>
          )}
        </div>

        {/* ========== LAYER 2: THREAD VIEW ========== */}
        <div
          className={`nav-layer layer-2 ${stackDepth < 2 ? 'offscreen' : ''}`}
          style={{ transform: layer2Transform }}
        >
          <DitherBeam preset="floor" />
          <div className="ios-top-scrim" aria-hidden="true" />

          {threadDetail && (
            <>
              <header className="ios-floating-header">
                <button
                  type="button"
                  className="ios-back-orb"
                  aria-label="Back to channel"
                  onClick={() => {
                    setStackDepth(1);
                    setOpenThreadId(null);
                  }}
                >
                  ‹
                </button>
                <div className="ios-title-pill">
                  <div className="ios-pill-main">Thread</div>
                  <div className="ios-pill-sub">
                    #{threadDetail.channel.name} · {threadDetail.subscribers.length} following
                  </div>
                </div>
              </header>

              <div className="slm-feed ios-padded-top" ref={threadFeedRef}>
                <SlackMessageRow
                  msg={threadDetail.root}
                  principals={principals}
                  viewer={viewer}
                  isMobileMode={isMobileMode}
                  approvedBranches={approvedBranches}
                  onApproveFork={handleApproveFork}
                  onInspectDiff={setDiffModalBranch}
                  onToggleReaction={handleToggleReaction}
                  onOpenSheet={handleOpenSheet}
                  inThread
                />
                <div className="ios-new-divider">
                  <span>
                    {threadDetail.replies.length === 0
                      ? 'START THREAD'
                      : `${threadDetail.replies.length} ${threadDetail.replies.length === 1 ? 'REPLY' : 'REPLIES'}`}
                  </span>
                </div>
                {threadDetail.replies.map((rep) => (
                  <SlackMessageRow
                    key={rep.id}
                    msg={rep}
                    principals={principals}
                    viewer={viewer}
                    isMobileMode={isMobileMode}
                    approvedBranches={approvedBranches}
                    onApproveFork={handleApproveFork}
                    onInspectDiff={setDiffModalBranch}
                    onToggleReaction={handleToggleReaction}
                    onOpenSheet={handleOpenSheet}
                    inThread
                    isOptimistic={rep.id < 0}
                  />
                ))}
              </div>

              <div className="composer-rel-wrap">
                <MentionAutocomplete
                  query={detectMentionQuery(threadDraft)}
                  principals={principals}
                  onSelect={(id) => setThreadDraft((prev) => completeMention(prev, id))}
                />
                <form className={`ios-reply-capsule ${keyboardOpen ? 'kb-flush' : ''}`} onSubmit={submitThreadReply}>
                  <button type="button" className="ios-cap-plus">+</button>
                  <input
                    type="text"
                    value={threadDraft}
                    onFocus={() => onInputFocus(true)}
                    onChange={(e) => setThreadDraft(e.target.value)}
                    placeholder="Add a reply…"
                  />
                  <button type="submit" className="ios-cap-send" aria-label="Reply">
                    <IcoSend />
                  </button>
                </form>
              </div>
            </>
          )}
        </div>

        <NativeBottomSheet
          msg={activeSheetMsg}
          mode={sheetState?.mode || 'actions'}
          viewerId={viewer.id}
          principals={principals}
          onSwitchMode={(m) => setSheetState((prev) => (prev ? { ...prev, mode: m } : null))}
          onSelectEmoji={(em) => activeSheetMsg && handleToggleReaction(activeSheetMsg.id, em)}
          onReplyThread={(rid) => openThread(rid)}
          onCopyText={(txt) => {
            navigator.clipboard?.writeText(txt).catch(() => {});
            showToast('Copied to clipboard');
          }}
          onClose={() => setSheetState(null)}
        />

        {searchModal}
        {accessModal}
        {diffModal}
      </div>
    );

    if (simulateMobileOnDesktop && !nativeMobile) {
      return (
        <div className="sl-sim-stage">
          <div className="sl-sim-bar">
            <span>Mobile Preview (393 × 852) · Tap any message for Thread · ☺+ or Long-press for Sheet</span>
            <button type="button" className="sl-btn" onClick={() => setSimulateMobileOnDesktop(false)}>
              Back to Desktop
            </button>
          </div>
          {phoneApp}
        </div>
      );
    }
    return phoneApp;
  }

  // ==================== SLACK DESKTOP LAYOUT (>= 860px) ====================
  return (
    <div className="sl-desktop">
      <DitherBeam preset={beamPreset} />
      {toastBanner}

      <header className="sl-topbar">
        <div className="sl-topbar-left" />
        <button type="button" className="sl-search-pill" onClick={() => setShowSearchModal(true)}>
          <IcoSearch />
          <span>Search Atelier</span>
          <kbd className="sl-kbd">⌘K</kbd>
        </button>
        <div className="sl-topbar-right">
          {!isGuest && viewer.kind === 'human' && (
            <button
              type="button"
              className={`sl-top-chip ${dmNotifyEnabled ? 'chip-notify-on' : ''}`}
              onClick={toggleDmBrowserNotifications}
            >
              {dmNotifyEnabled ? '🔔 DM Alerts: On' : '🔕 Notify on DMs'}
            </button>
          )}
          {!isGuest && (
            <button type="button" className="sl-top-chip" onClick={() => setShowAccessModal(true)}>
              Tailnet & Onboarding
            </button>
          )}
          <button type="button" className="sl-top-chip" onClick={() => setSimulateMobileOnDesktop(true)}>
            Mobile view
          </button>
          {(viewer.role === 'owner' || viewerQuery === 'guest_preview') ? (
            <button type="button" className="sl-top-chip" onClick={toggleGuestPreview}>
              {isGuest ? `Previewing: Guest (#${viewer.guest_channel_id})` : `${viewer.display_name}`}
            </button>
          ) : (
            <span className="sl-top-chip">{viewer.display_name} (Guest)</span>
          )}
        </div>
      </header>

      <div
        className={`sl-body ${openThreadId !== null ? 'has-thread' : ''} ${resizingPane ? 'is-resizing' : ''}`}
        style={{ '--sb-w': `${sidebarWidth}px`, '--th-w': `${threadWidth}px` } as React.CSSProperties}
      >
        <nav className="sl-rail">
          <div className="sl-ws-tile">A</div>

          <button
            type="button"
            className={`sl-rail-btn ${railTab === 'home' ? 'active' : ''}`}
            onClick={() => { setRailTab('home'); setCenterMode('channel'); }}
          >
            <span className="sl-rail-ico"><IcoHome filled={railTab === 'home'} /></span>
            <span>Home</span>
          </button>

          {!isGuest && (
            <button
              type="button"
              className={`sl-rail-btn ${railTab === 'dms' ? 'active' : ''}`}
              onClick={() => setRailTab('dms')}
            >
              <span className="sl-rail-ico"><IcoDMs filled={railTab === 'dms'} /></span>
              <span>DMs</span>
            </button>
          )}

          <button
            type="button"
            className={`sl-rail-btn ${railTab === 'activity' ? 'active' : ''}`}
            onClick={() => setRailTab('activity')}
          >
            <span className="sl-rail-ico">
              <IcoBell filled={railTab === 'activity'} />
              {unreadActivity > 0 && <i className="sl-rail-badge">{unreadActivity}</i>}
            </span>
            <span>Activity</span>
          </button>

          <div className="sl-rail-spacer" />
          <Avatar principal={viewer} id={viewer.id} size="md" showDot />
        </nav>

        <aside className="sl-sidebar">
          <div className="sl-sb-header">
            <button type="button" className="sl-ws-menu-btn" onClick={() => !isGuest && setShowAccessModal(true)}>
              Atelier ⌄
            </button>
            {!isGuest && (
              <button type="button" className="sl-compose-btn" title="New channel" onClick={() => setShowNewChannelModal(true)}>
                +
              </button>
            )}
          </div>

          {railTab === 'activity' ? (
            <div className="sl-sb-scroll">
              <div className="sl-act-filters">
                {(['all', 'unreads', 'mentions', 'threads'] as const).map((f) => (
                  <button key={f} type="button" className={activityFilter === f ? 'active' : ''} onClick={() => setActivityFilter(f)}>
                    {f === 'all'
                      ? 'All'
                      : f === 'unreads'
                      ? `Unreads (${unreadActivity})`
                      : f === 'mentions'
                      ? '@Mentions'
                      : 'Threads'}
                  </button>
                ))}
              </div>
              {unreadActivity > 0 && (
                <button type="button" className="sl-mark-read-btn sidebar" onClick={markAllNotificationsRead}>
                  Mark all {unreadActivity} read
                </button>
              )}
              {filteredNotifications.map((n) => (
                <button
                  key={n.id}
                  type="button"
                  className={`sl-sb-act-item ${n.unread ? 'unread' : 'is-read'} ${openThreadId === n.root_id ? 'selected' : ''}`}
                  onClick={() => {
                    if (n.unread) markNotificationRead(n.id);
                    setActiveChannelId(n.channel_id);
                    openThread(n.root_id);
                  }}
                >
                  <div className="sl-sb-act-meta">
                    <span className="sl-sb-act-ch">
                      {n.unread && <i className="sl-unread-dot" />}
                      {n.channel_kind === 'dm' ? 'Direct message' : `#${n.channel_name}`}
                    </span>
                    <span>{formatClock(n.created_at)}</span>
                  </div>
                  <div className="sl-sb-act-who">
                    <strong>{principals[n.author_id]?.display_name || n.author_id}</strong>
                    {n.unread && <span className="sl-new-pill">NEW</span>}
                  </div>
                  <div className="sl-sb-act-preview">{n.body.slice(0, 80)}</div>
                </button>
              ))}
            </div>
          ) : railTab === 'dms' && !isGuest ? (
            <div className="sl-sb-scroll">
              <div className="sl-sb-group-label">Direct messages</div>
              {internalPeers.map((p) => {
                const dm = dmChannels.find((d) => d.member_ids.includes(p.id));
                return (
                  <button
                    key={p.id}
                    type="button"
                    className={`sl-sb-item ${dm && activeChannelId === dm.id ? 'selected' : ''}`}
                    onClick={() => dm && openChannel(dm.id)}
                  >
                    <Avatar principal={p} id={p.id} size="xs" showDot />
                    <span className="sl-sb-label">{p.display_name}</span>
                    {dm && dm.unread_count > 0 && <span className="sl-sb-badge">{dm.unread_count}</span>}
                  </button>
                );
              })}
            </div>
          ) : (
            <div className="sl-sb-scroll">
              <div className="sl-sb-nav">
                <button
                  type="button"
                  className={`sl-sb-item ${centerMode === 'threads' ? 'selected' : ''}`}
                  onClick={() => setCenterMode('threads')}
                >
                  <span className="sl-sb-sym"><IcoThreads /></span>
                  <span className="sl-sb-label">Threads</span>
                </button>
                {!isGuest && (
                  <button
                    type="button"
                    className={`sl-sb-item ${centerMode === 'all-channels' ? 'selected' : ''}`}
                    onClick={() => setCenterMode('all-channels')}
                  >
                    <span className="sl-sb-sym">#</span>
                    <span className="sl-sb-label">All channels</span>
                  </button>
                )}
              </div>

              <div className="sl-sb-group">
                <button
                  type="button"
                  className="sl-sb-group-btn"
                  onClick={() => setCollapsedSections((p) => ({ ...p, sbCh: !p.sbCh }))}
                >
                  <span>{collapsedSections.sbCh ? '▸' : '▾'} Channels</span>
                </button>
                {!collapsedSections.sbCh &&
                  sidebarChannels.map((ch) => (
                    <button
                      key={ch.id}
                      type="button"
                      className={`sl-sb-item ${centerMode === 'channel' && activeChannelId === ch.id ? 'selected' : ''} ${
                        ch.unread_count > 0 || ch.mention_count > 0 ? 'unread' : ''
                      }`}
                      onClick={() => openChannel(ch.id)}
                    >
                      <span className="sl-sb-sym">{ch.kind === 'private' ? <IcoLock /> : '#'}</span>
                      <span className="sl-sb-label">{ch.name}</span>
                      {ch.mention_count > 0 && <span className="sl-sb-badge">{ch.mention_count}</span>}
                    </button>
                  ))}
                {!isGuest && !collapsedSections.sbCh && (
                  <button type="button" className="sl-sb-item muted" onClick={() => setShowNewChannelModal(true)}>
                    <span className="sl-sb-sym">+</span>
                    <span className="sl-sb-label">Add channels</span>
                  </button>
                )}
              </div>

              {!isGuest && (
                <div className="sl-sb-group">
                  <button
                    type="button"
                    className="sl-sb-group-btn"
                    onClick={() => setCollapsedSections((p) => ({ ...p, sbDm: !p.sbDm }))}
                  >
                    <span>{collapsedSections.sbDm ? '▸' : '▾'} Direct messages</span>
                  </button>
                  {!collapsedSections.sbDm &&
                    Object.values(principals)
                      .filter((p) => p.role !== 'guest')
                      .map((p) => {
                        const dm = dmChannels.find((d) => d.member_ids.includes(p.id) && p.id !== viewer.id);
                        const sel = dm && centerMode === 'channel' && activeChannelId === dm.id;
                        return (
                          <button
                            key={p.id}
                            type="button"
                            className={`sl-sb-item ${sel ? 'selected' : ''} ${dm && dm.unread_count > 0 ? 'unread' : ''}`}
                            onClick={() => dm && openChannel(dm.id)}
                          >
                            <Avatar principal={p} id={p.id} size="xs" showDot />
                            <span className="sl-sb-label">
                              {p.display_name}
                              {p.id === viewer.id ? ' (you)' : ''}
                            </span>
                            {dm && dm.unread_count > 0 && <span className="sl-sb-badge">{dm.unread_count}</span>}
                          </button>
                        );
                      })}
                </div>
              )}

              {isGuest && (
                <div className="sl-sb-guest-footer">
                  Single-channel guest on <strong>#{viewer.guest_channel_id}</strong>
                </div>
              )}
            </div>
          )}
          <div
            role="separator"
            aria-orientation="vertical"
            aria-label="Resize sidebar"
            title="Drag to resize · Double-click to reset"
            className={`sl-resize-handle is-sidebar ${resizingPane === 'sidebar' ? 'is-active' : ''}`}
            onMouseDown={(e) => beginPaneResize('sidebar', e)}
            onDoubleClick={() => {
              setSidebarWidth(244);
              try { localStorage.setItem('atelier.sidebar_width', '244'); } catch {}
            }}
          />
        </aside>

        <main className="sl-main">
          {railTab === 'activity' ? (
            <>
              <header className="sl-pane-header">
                <div className="sl-pane-title-wrap">
                  <h1 className="sl-pane-h1">Activity</h1>
                  <span className="sl-pane-topic">
                    {unreadActivity > 0 ? `${unreadActivity} unread notification${unreadActivity === 1 ? '' : 's'}` : 'All caught up'}
                  </span>
                </div>
                <div className="sl-act-header-actions">
                  <div className="sl-act-filters">
                    {(['all', 'unreads', 'mentions', 'threads', 'dms'] as const).map((f) => (
                      <button
                        key={f}
                        type="button"
                        className={activityFilter === f ? 'active' : ''}
                        onClick={() => setActivityFilter(f)}
                      >
                        {f === 'all'
                          ? 'All'
                          : f === 'unreads'
                          ? `Unreads (${unreadActivity})`
                          : f === 'mentions'
                          ? '@Mentions'
                          : f === 'threads'
                          ? 'Threads'
                          : 'DMs'}
                      </button>
                    ))}
                  </div>
                  {unreadActivity > 0 && (
                    <button type="button" className="sl-btn" onClick={markAllNotificationsRead}>
                      Mark all read
                    </button>
                  )}
                </div>
              </header>

              <div className="sl-feed padded">
                <div className="sl-act-feed-list">
                  {filteredNotifications.length === 0 && (
                    <div className="sl-empty-state">No notifications in this view.</div>
                  )}
                  {filteredNotifications.map((n) => (
                    <div
                      key={n.id}
                      className={`sl-act-card ${n.unread ? 'is-unread' : 'is-read'} ${
                        openThreadId === n.root_id ? 'is-active-thread' : ''
                      }`}
                      onClick={() => {
                        if (n.unread) markNotificationRead(n.id);
                        setActiveChannelId(n.channel_id);
                        openThread(n.root_id);
                      }}
                    >
                      <div className="sl-act-card-top">
                        <span className="sl-act-card-context">
                          {n.unread && <i className="sl-unread-dot" />}
                          {n.kind === 'mention'
                            ? `Mentioned you in #${n.channel_name}`
                            : n.kind === 'dm'
                            ? 'Direct message'
                            : n.kind === 'guest_triage'
                            ? `External guest submission in #${n.channel_name}`
                            : `Replied to thread in #${n.channel_name}`}
                        </span>
                        <span className="sl-act-card-meta">
                          {n.unread && <span className="sl-new-pill">UNREAD</span>}
                          <time>{formatClock(n.created_at)}</time>
                        </span>
                      </div>
                      <div className="sl-act-card-body">
                        <Avatar principal={principals[n.author_id]} id={n.author_id} size="md" />
                        <div className="sl-act-card-col">
                          <div className="sl-msg-head">
                            <span className="sl-msg-sender">{principals[n.author_id]?.display_name || n.author_id}</span>
                            {principals[n.author_id]?.kind === 'agent' && !n.untrusted_envelope && (
                              <span className="sl-app-tag">AGENT</span>
                            )}
                            {n.untrusted_envelope && <span className="sl-app-tag tag-guest">GUEST</span>}
                          </div>
                          <div className="sl-msg-body">{renderSlackMarkdown(n.body, viewer.id)}</div>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </>
          ) : centerMode === 'channel' && (
            <>
              <header className="sl-pane-header">
                <div className="sl-pane-title-wrap">
                  <h1 className="sl-pane-h1">
                    {activeChannelMeta?.kind === 'private' ? <IcoLock /> : activeChannelMeta?.kind === 'dm' ? '' : '#'}
                    <span>{activeChannelMeta?.name || activeChannelId}</span>
                  </h1>
                  <span className="sl-pane-topic">{activeChannelMeta?.topic}</span>
                </div>
                <div className="sl-pane-members">
                  <span className="sl-av-stack">
                    {(activeChannelMeta?.member_ids || []).slice(0, 4).map((mid) => (
                      <Avatar key={mid} principal={principals[mid]} id={mid} size="xs" />
                    ))}
                  </span>
                  <span>{activeChannelMeta?.member_count || 0}</span>
                </div>
              </header>

              {activeChannelMeta?.guest_allowed && (
                <div className="sl-ext-bar">
                  External Tailscale single-channel guests are enabled in <strong>#{activeChannelMeta.name}</strong>
                  {!isGuest && ' · Guest messages are treated strictly as data and never wake worker agents'}
                </div>
              )}

              <div className="sl-feed" ref={feedRef}>
                {activeChannelMeta?.has_more && (
                  <div className="sl-date-divider">
                    <button type="button" className="sl-btn" onClick={loadEarlierMessages}>
                      Load earlier messages
                    </button>
                  </div>
                )}
                <div className="sl-date-divider"><span>Today</span></div>
                {channelMessages.map((msg) => (
                  <SlackMessageRow
                    key={msg.id}
                    msg={msg}
                    principals={principals}
                    viewer={viewer}
                    isMobileMode={isMobileMode}
                    approvedBranches={approvedBranches}
                    onApproveFork={handleApproveFork}
                    onInspectDiff={setDiffModalBranch}
                    onToggleReaction={handleToggleReaction}
                    onOpenSheet={handleOpenSheet}
                    onSelectChannel={handleSelectChannelLink}
                    onSelectMention={handleSelectMentionLink}
                    onOpenThread={openThread}
                    isActiveThread={openThreadId === msg.id}
                    isOptimistic={msg.id < 0}
                  />
                ))}
              </div>

              <div className="composer-rel-wrap">
                <MentionAutocomplete
                  query={detectMentionQuery(draftBody)}
                  principals={principals}
                  onSelect={(id) => setDraftBody((prev) => completeMention(prev, id))}
                />
                <form className="sl-composer-box" onSubmit={submitChannelMessage}>
                  <input
                    type="text"
                    value={draftBody}
                    onChange={(e) => setDraftBody(e.target.value)}
                    placeholder={`Message ${
                      activeChannelMeta?.kind === 'dm' ? '' : '#'
                    }${activeChannelMeta?.name || activeChannelId}`}
                  />
                  <div className="sl-composer-bar">
                    <div className="sl-composer-tools">
                      <button type="button" title="Attach">+</button>
                      <span className="sl-tool-div" />
                      <button type="button" title="Mention" onClick={() => setDraftBody((b) => `${b}@`)}>@</button>
                      <button type="button" title="Code">{'</>'}</button>
                    </div>
                    <button type="submit" className="sl-send-btn" aria-label="Send">
                      <IcoSend />
                    </button>
                  </div>
                </form>
              </div>
            </>
          )}

          {centerMode === 'threads' && (
            <>
              <header className="sl-pane-header">
                <h1 className="sl-pane-h1">Threads</h1>
              </header>
              <div className="sl-feed padded">
                {subscribed_threads.map((th) => (
                  <div key={th.id} className="sl-threads-page-card">
                    <div className="sl-threads-page-head" onClick={() => openChannel(th.channel_id)}>
                      <strong>#{th.channel_id}</strong>
                      <span>· You and {Math.max(0, th.subscribed_ids.length - 1)} others notified on replies</span>
                    </div>
                    <SlackMessageRow
                      msg={th}
                      principals={principals}
                      viewer={viewer}
                      isMobileMode={isMobileMode}
                      approvedBranches={approvedBranches}
                      onApproveFork={handleApproveFork}
                      onInspectDiff={setDiffModalBranch}
                      onToggleReaction={handleToggleReaction}
                      onOpenSheet={handleOpenSheet}
                      inThread
                    />
                    {(th.recent_replies || []).map((rep) => (
                      <SlackMessageRow
                        key={rep.id}
                        msg={rep}
                        principals={principals}
                        viewer={viewer}
                        isMobileMode={isMobileMode}
                        approvedBranches={approvedBranches}
                        onApproveFork={handleApproveFork}
                        onInspectDiff={setDiffModalBranch}
                        onToggleReaction={handleToggleReaction}
                        onOpenSheet={handleOpenSheet}
                        inThread
                      />
                    ))}
                  </div>
                ))}
              </div>
            </>
          )}

          {centerMode === 'all-channels' && !isGuest && (
            <>
              <header className="sl-pane-header">
                <h1 className="sl-pane-h1">All channels</h1>
                <button type="button" className="sl-btn sl-btn-primary" onClick={() => setShowNewChannelModal(true)}>
                  Create channel
                </button>
              </header>
              <div className="sl-feed padded">
                <div className="sl-channel-browser">
                  {explorable_channels.map((ch) => (
                    <div key={ch.id} className="sl-browser-row" onClick={() => openChannel(ch.id)}>
                      <div>
                        <div className="sl-browser-title">#{ch.name}</div>
                        <div className="sl-browser-meta">
                          {ch.joined ? '✓ Joined · ' : ''}
                          {ch.member_count} members · {ch.description || ch.topic}
                        </div>
                      </div>
                      <button type="button" className="sl-btn">{ch.joined ? 'View' : 'Join'}</button>
                    </div>
                  ))}
                </div>
              </div>
            </>
          )}
        </main>

        <aside className={`sl-thread-pane ${openThreadId !== null && threadDetail ? 'is-open' : ''}`}>
          {openThreadId !== null && threadDetail && (
            <div
              role="separator"
              aria-orientation="vertical"
              aria-label="Resize thread panel"
              title="Drag to resize · Double-click to reset"
              className={`sl-resize-handle is-thread ${resizingPane === 'thread' ? 'is-active' : ''}`}
              onMouseDown={(e) => beginPaneResize('thread', e)}
              onDoubleClick={() => {
                setThreadWidth(392);
                try { localStorage.setItem('atelier.thread_width', '392'); } catch {}
              }}
            />
          )}
          {threadDetail && (
            <>
              <header className="sl-pane-header">
                <div className="sl-pane-title-wrap">
                  <h2 className="sl-pane-h1">Thread</h2>
                  <span className="sl-pane-topic">#{threadDetail.channel.name}</span>
                </div>
                <button type="button" className="sl-close" onClick={() => setOpenThreadId(null)}>×</button>
              </header>

              <div className="sl-feed" ref={threadFeedRef}>
                <SlackMessageRow
                  msg={threadDetail.root}
                  principals={principals}
                  viewer={viewer}
                  isMobileMode={isMobileMode}
                  approvedBranches={approvedBranches}
                  onApproveFork={handleApproveFork}
                  onInspectDiff={setDiffModalBranch}
                  onToggleReaction={handleToggleReaction}
                  onOpenSheet={handleOpenSheet}
                  inThread
                />
                <div className="ios-new-divider">
                  <span>
                    {threadDetail.replies.length === 0
                      ? 'START THREAD'
                      : `${threadDetail.replies.length} ${threadDetail.replies.length === 1 ? 'REPLY' : 'REPLIES'}`}
                  </span>
                </div>
                {threadDetail.replies.map((rep) => (
                  <SlackMessageRow
                    key={rep.id}
                    msg={rep}
                    principals={principals}
                    viewer={viewer}
                    isMobileMode={isMobileMode}
                    approvedBranches={approvedBranches}
                    onApproveFork={handleApproveFork}
                    onInspectDiff={setDiffModalBranch}
                    onToggleReaction={handleToggleReaction}
                    onOpenSheet={handleOpenSheet}
                    inThread
                    isOptimistic={rep.id < 0}
                  />
                ))}
              </div>

              <div className="composer-rel-wrap">
                <MentionAutocomplete
                  query={detectMentionQuery(threadDraft)}
                  principals={principals}
                  onSelect={(id) => setThreadDraft((prev) => completeMention(prev, id))}
                />
                <form className="sl-composer-box in-thread" onSubmit={submitThreadReply}>
                  <input
                    type="text"
                    value={threadDraft}
                    onChange={(e) => setThreadDraft(e.target.value)}
                    placeholder="Add a reply…"
                  />
                  <div className="sl-composer-bar">
                    <label className="sl-also-send">
                      <input
                        type="checkbox"
                        checked={alsoSendChannel}
                        onChange={(e) => setAlsoSendChannel(e.target.checked)}
                      />
                      <span>Also send to #{threadDetail.channel.name}</span>
                    </label>
                    <button type="submit" className="sl-send-btn" aria-label="Reply">
                      <IcoSend />
                    </button>
                  </div>
                </form>
              </div>
            </>
          )}
        </aside>
      </div>

      {showNewChannelModal && !isGuest && (
        <div className="sl-modal-veil" onClick={() => setShowNewChannelModal(false)}>
          <form className="sl-modal" onClick={(e) => e.stopPropagation()} onSubmit={submitNewChannel}>
            <div className="sl-modal-head">
              <h3>Create a channel</h3>
              <button type="button" className="sl-close" onClick={() => setShowNewChannelModal(false)}>×</button>
            </div>
            <div className="sl-vis-row">
              <button type="button" className={newChKind === 'public' ? 'active' : ''} onClick={() => setNewChKind('public')}>
                # Public
              </button>
              <button type="button" className={newChKind === 'private' ? 'active' : ''} onClick={() => setNewChKind('private')}>
                🔒 Private
              </button>
            </div>
            <input type="text" value={newChName} onChange={(e) => setNewChName(e.target.value)} placeholder="e.g. belmonte-art" />
            <input type="text" value={newChTopic} onChange={(e) => setNewChTopic(e.target.value)} placeholder="Description (optional)" />
            {viewer.role === 'owner' && newChKind === 'public' && (
              <label className="sl-also-send">
                <input
                  type="checkbox"
                  checked={newChGuestAllowed}
                  onChange={(e) => setNewChGuestAllowed(e.target.checked)}
                />
                <span>Allow external Tailscale Single-Channel Guests in this channel</span>
              </label>
            )}
            <div className="sl-modal-foot">
              <button type="button" className="sl-btn" onClick={() => setShowNewChannelModal(false)}>Cancel</button>
              <button type="submit" className="sl-btn sl-btn-primary">Create</button>
            </div>
          </form>
        </div>
      )}

      {searchModal}
      {accessModal}
      {diffModal}
    </div>
  );
};
