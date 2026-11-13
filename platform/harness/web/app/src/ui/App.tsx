import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import type {
  BoardMessage,
  BootstrapPayload,
  ChannelSummary,
  NotificationItem,
  Principal,
  Reaction,
  ThreadDetail,
} from '../types';
import { DitherBeam, type BeamPreset } from './DitherBeam';

const QUICK_EMOJIS = ['👍', '🔥', '✅', '❤️', '👀', '🚀', '🎉', '😂'];

function formatClock(unixSeconds: number): string {
  const d = new Date(unixSeconds * 1000);
  const hh = d.getUTCHours();
  const mm = String(d.getUTCMinutes()).padStart(2, '0');
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
  const match = text.match(/(?:^|\s)@([a-z0-9._/-]*)$/i);
  return match ? (match[1] ?? '').toLowerCase() : null;
}

function completeMention(text: string, handle: string): string {
  return text.replace(/(^|\s)@[a-z0-9._/-]*$/i, `$1@${handle} `);
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
  const label = (principal?.display_name || id).replace(/^henry\//, '');
  const initials = label
    .split(/[\s/-]+/)
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

function renderSlackMarkdown(text: string, viewerId: string): React.ReactNode {
  const clean = text.replace(/^📢\s*/, '');
  const lines = clean.split('\n');
  return lines.map((line, lineIdx) => {
    const tokens = line.split(/(`[^`]+`|\*\*[^*]+\*\*|@[a-z0-9._/-]+|#[a-z0-9-]+)/gi);
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
            const isMe = tok.slice(1).toLowerCase() === viewerId.toLowerCase();
            return <span key={i} className={`sl-mention ${isMe ? 'is-me' : ''}`}>{tok}</span>;
          }
          if (tok.startsWith('#') && tok.length > 2) {
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
          <strong>@{p.id}</strong>
          <span>{p.display_name}</span>
        </button>
      ))}
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
  approvedBranches: Record<string, boolean>;
  onApproveFork: (branch: string, rootId: number) => void;
  onInspectDiff: (branch: string) => void;
  onToggleReaction: (messageId: number, emoji: string) => void;
  onOpenActionSheet: (msg: BoardMessage) => void;
  onOpenThread?: (rootId: number) => void;
  inThread?: boolean;
  isOptimistic?: boolean;
}> = ({
  msg,
  principals,
  viewer,
  approvedBranches,
  onApproveFork,
  onInspectDiff,
  onToggleReaction,
  onOpenActionSheet,
  onOpenThread,
  inThread = false,
  isOptimistic = false,
}) => {
  const author = principals[msg.author_id];
  const isGuestMsg = msg.author_role === 'guest';
  const isAgent = author?.kind === 'agent';
  const [pickerOpen, setPickerOpen] = useState(false);
  const [pressing, setPressing] = useState(false);

  const pressTimer = useRef<number | null>(null);
  const startCoord = useRef<{ x: number; y: number } | null>(null);

  const onTouchStart = (e: React.TouchEvent) => {
    const t = e.touches[0];
    if (!t) return;
    startCoord.current = { x: t.clientX, y: t.clientY };
    pressTimer.current = window.setTimeout(() => {
      pressTimer.current = null;
      setPressing(false);
      if (typeof navigator !== 'undefined' && 'vibrate' in navigator) {
        try { navigator.vibrate(14); } catch {}
      }
      onOpenActionSheet(msg);
    }, 320);
    setPressing(true);
  };

  const onTouchMove = (e: React.TouchEvent) => {
    if (!startCoord.current) return;
    const t = e.touches[0];
    if (!t) return;
    if (Math.hypot(t.clientX - startCoord.current.x, t.clientY - startCoord.current.y) > 8) {
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

  return (
    <div
      className={`sl-msg ${isGuestMsg && viewer.role !== 'guest' ? 'sl-msg-guest' : ''} ${
        pressing ? 'is-pressing' : ''
      } ${isOptimistic ? 'msg-enter' : ''}`}
      onTouchStart={onTouchStart}
      onTouchMove={onTouchMove}
      onTouchEnd={clearPress}
      onTouchCancel={clearPress}
      onContextMenu={(e) => {
        if (window.innerWidth < 860) {
          e.preventDefault();
          onOpenActionSheet(msg);
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

        <div className="sl-msg-body">{renderSlackMarkdown(msg.body, viewer.id)}</div>

        <SlackUnfurl
          msg={msg}
          viewerRole={viewer.role}
          approvedBranches={approvedBranches}
          onApproveFork={onApproveFork}
          onInspectDiff={onInspectDiff}
        />

        {(msg.reactions.length > 0 || pickerOpen || (!inThread && msg.reply_count > 0 && onOpenThread)) && (
          <div className="sl-msg-below">
            {(msg.reactions.length > 0 || pickerOpen) && (
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
                  onClick={(e) => {
                    e.stopPropagation();
                    setPickerOpen((v) => !v);
                  }}
                >
                  ☺+
                </button>
              </div>
            )}

            {pickerOpen && (
              <div className="sl-inline-picker" onClick={(e) => e.stopPropagation()}>
                {QUICK_EMOJIS.map((em) => (
                  <button
                    key={em}
                    type="button"
                    onClick={() => {
                      onToggleReaction(msg.id, em);
                      setPickerOpen(false);
                    }}
                  >
                    {em}
                  </button>
                ))}
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

      {/* Desktop Hover Pill — CSS strictly scopes hover to (hover: hover) and (pointer: fine)! */}
      <div className="sl-hover-bar">
        <button
          type="button"
          title="React"
          onClick={(e) => {
            e.stopPropagation();
            setPickerOpen((v) => !v);
          }}
        >
          ☺
        </button>
        {!inThread && onOpenThread && (
          <button
            type="button"
            title="Reply in thread"
            onClick={(e) => {
              e.stopPropagation();
              onOpenThread(msg.id);
            }}
          >
            <IcoThreads />
          </button>
        )}
      </div>
    </div>
  );
};

export const App: React.FC = () => {
  const initialParams = useMemo(() => new URLSearchParams(window.location.search), []);
  const [viewerId, setViewerId] = useState<string>(initialParams.get('viewer') || 'jim');

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
    initialParams.get('channel') || (initialParams.get('viewer') === 'henry' ? 'fork-sync' : 'world-build')
  );
  const [openThreadId, setOpenThreadId] = useState<number | null>(() => {
    const t = initialParams.get('thread');
    return t ? Number(t) : null;
  });

  // Persistent 3-Layer Mobile Stack: depth 0 ('tab'), depth 1 ('channel' | 'threads-list' | 'all-channels'), depth 2 ('thread')
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

  // Interactive 120fps Touch Swipe-Back State
  const [swipeDx, setSwipeDx] = useState<number>(0);
  const [isSwiping, setIsSwiping] = useState<boolean>(false);
  const swipeRef = useRef<{ startX: number; startY: number; startTime: number; active: boolean } | null>(null);

  const [collapsedSections, setCollapsedSections] = useState<Record<string, boolean>>({});
  const [activityFilter, setActivityFilter] = useState<'all' | 'dms' | 'mentions' | 'threads'>('all');
  const [dmFilter, setDmFilter] = useState<'all' | 'agents' | 'unreads'>('all');

  const [showNewChannelModal, setShowNewChannelModal] = useState<boolean>(
    initialParams.get('modal') === 'new-channel'
  );
  const [showAccessModal, setShowAccessModal] = useState<boolean>(
    initialParams.get('modal') === 'access'
  );
  const [showSearchModal, setShowSearchModal] = useState<boolean>(false);
  const [searchQuery, setSearchQuery] = useState<string>('');

  const [actionSheetMsg, setActionSheetMsg] = useState<BoardMessage | null>(null);
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
  const [newChTopic, setNewChTopic] = useState<string>('Tuscan stone shaders & station signage');

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

  /* Global Cmd+K / Escape Keyboard Shortcuts */
  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        setShowSearchModal((v) => !v);
      } else if (e.key === 'Escape') {
        setShowSearchModal(false);
        setActionSheetMsg(null);
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

  const refreshBootstrap = useCallback(async (vId: string) => {
    const res = await fetch(`/api/bootstrap?viewer=${encodeURIComponent(vId)}`);
    if (!res.ok) return;
    const data: BootstrapPayload = await res.json();
    setBoot(data);
    if (data.viewer.role === 'guest' && data.viewer.guest_channel_id) {
      setActiveChannelId(data.viewer.guest_channel_id);
    }
  }, []);

  /* Real-Time SSE Stream (/api/events) — opened after initial load so Safari's URL spinner finishes instantly */
  useEffect(() => {
    refreshBootstrap(viewerId);
    let es: EventSource | null = null;
    const timer = window.setTimeout(() => {
      es = new EventSource(`/api/events?viewer=${encodeURIComponent(viewerId)}`);
      es.addEventListener('sync', () => {
        refreshBootstrap(viewerId);
      });
    }, 300);
    return () => {
      clearTimeout(timer);
      es?.close();
    };
  }, [viewerId, refreshBootstrap]);

  /* 0ms Optimistic Reaction Toggle */
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

      await fetch(`/api/messages/${messageId}/react?viewer=${encodeURIComponent(actorId)}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-Atelier-CSRF': boot?.csrf_token || '' },
        body: JSON.stringify({ viewer_id: actorId, emoji }),
      });
    },
    [boot]
  );

  const switchViewer = (nextViewer: string) => {
    setViewerId(nextViewer);
    if (nextViewer === 'henry' || nextViewer.startsWith('guest:')) {
      setRailTab('home');
      setCenterMode('channel');
      setActiveChannelId('fork-sync');
      setOpenThreadId(null);
      setMobileTab('home');
      setStackDepth(0);
    }
  };

  /* 0ms Channel Open + Optimistic Unread Clear */
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
      fetch(`/api/channels/${encodeURIComponent(cid)}/read?viewer=${encodeURIComponent(viewerId)}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-Atelier-CSRF': boot?.csrf_token || '' },
        body: '{}',
      }).catch(() => {});
    },
    [viewerId]
  );

  /* 0ms Single-Tap Thread Open */
  const openThread = useCallback((rootId: number) => {
    setOpenThreadId(rootId);
    setStackDepth(2);
  }, []);

  /* Interactive iOS Touch Edge-Swipe Back Handlers */
  const handleStackTouchStart = (e: React.TouchEvent) => {
    if (stackDepth === 0) return;
    const t = e.touches[0];
    if (!t) return;
    // Allow left-edge swipe (< 44px) or broad horizontal swipe
    if (t.clientX <= 44) {
      swipeRef.current = { startX: t.clientX, startY: t.clientY, startTime: performance.now(), active: false };
    } else {
      swipeRef.current = null;
    }
  };

  const handleStackTouchMove = (e: React.TouchEvent) => {
    const s = swipeRef.current;
    if (!s || stackDepth === 0) return;
    const t = e.touches[0];
    if (!t) return;
    const dx = t.clientX - s.startX;
    const dy = t.clientY - s.startY;
    if (!s.active) {
      if (Math.abs(dy) > Math.abs(dx)) {
        swipeRef.current = null;
        return;
      }
      if (dx > 8) {
        s.active = true;
        setIsSwiping(true);
      }
    }
    if (s.active) {
      setSwipeDx(Math.max(0, dx));
    }
  };

  const handleStackTouchEnd = () => {
    const s = swipeRef.current;
    swipeRef.current = null;
    if (!s || !s.active) {
      setIsSwiping(false);
      setSwipeDx(0);
      return;
    }
    const elapsed = Math.max(1, performance.now() - s.startTime);
    const velocity = swipeDx / elapsed;
    const w = window.innerWidth || 393;
    if (swipeDx > w * 0.3 || velocity > 0.5) {
      setStackDepth((d) => (d === 2 ? 1 : 0));
      if (stackDepth === 2) setOpenThreadId(null);
    }
    setIsSwiping(false);
    setSwipeDx(0);
  };

  const handleApproveFork = async (branch: string, rootId: number) => {
    setApprovedBranches((prev) => ({ ...prev, [branch]: true }));
    await fetch(`/api/messages?viewer=${encodeURIComponent(viewerId)}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-Atelier-CSRF': boot?.csrf_token || '' },
      body: JSON.stringify({
        author_id: 'jim',
        channel_id: 'fork-sync',
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

    await fetch(`/api/messages?viewer=${encodeURIComponent(viewerId)}`, {
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

    await fetch(`/api/messages?viewer=${encodeURIComponent(viewerId)}`, {
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
    const res = await fetch(`/api/channels?viewer=${encodeURIComponent(viewerId)}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-Atelier-CSRF': boot?.csrf_token || '' },
      body: JSON.stringify({ creator_id: boot.viewer.id, name: newChName, kind: newChKind, topic: newChTopic }),
    });
    if (res.ok) {
      const data = await res.json();
      setShowNewChannelModal(false);
      await refreshBootstrap(viewerId);
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

  const filteredNotifications = notifications.filter((n) => {
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

  // Instant Fuzzy Search Results (Cmd+K / Search Orb)
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

  /* Shared Instant Quick Switcher / Search Modal (Cmd+K on Desktop, Search Orb on Mobile) */
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

  const mobileActionSheet = actionSheetMsg && (
    <div className="ios-sheet-backdrop" onClick={() => setActionSheetMsg(null)}>
      <div className="ios-action-sheet" onClick={(e) => e.stopPropagation()}>
        <div className="ios-sheet-grabber" />
        <div className="ios-sheet-emojis">
          {QUICK_EMOJIS.map((em) => (
            <button
              key={em}
              type="button"
              onClick={() => {
                handleToggleReaction(actionSheetMsg.id, em);
                setActionSheetMsg(null);
              }}
            >
              {em}
            </button>
          ))}
        </div>
        <button
          type="button"
          className="ios-sheet-row"
          onClick={() => {
            const targetId = actionSheetMsg.root_id || actionSheetMsg.id;
            setActionSheetMsg(null);
            openThread(targetId);
          }}
        >
          <IcoThreads />
          <span>Reply in thread</span>
        </button>
        <button
          type="button"
          className="ios-sheet-row"
          onClick={() => {
            navigator.clipboard?.writeText(actionSheetMsg.body).catch(() => {});
            setActionSheetMsg(null);
          }}
        >
          <span>📋</span>
          <span>Copy message text</span>
        </button>
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
            <div className="sec-tier-title">2. Your Devices ({(security?.owner_nodes || []).join(', ')}) → Owner</div>
            <p>
              Authenticated via <code>tailscale whois</code>. Full owner access on Mac & iPhone. Current session:{' '}
              <code>{security?.detected_node || 'local'}</code>.
            </p>
          </div>

          <div className="sec-tier amber">
            <div className="sec-tier-title">3. Brother & His Agents on Tailnet → Auto Single-Channel Guest</div>
            <p>
              Share your tailnet node with your brother in Tailscale. Any connection from his laptop is automatically
              locked to <strong>#fork-sync</strong> (no DMs, no internal channels, cannot wake your worker agents).
            </p>
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
        <p className="sl-modal-sub">henry/atelier · 91c4e02d rebased on a3b145ff2b · 0 C++ files touched</p>
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

    // GPU UINavigationController Parallax Math across persistent layers 0, 1, and 2!
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

        {/* ========== LAYER 0: PERSISTENT ROOT TABS (Home · DMs · Activity — Preserves Scroll!) ========== */}
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
              <button
                type="button"
                className="ios-profile-capsule"
                onClick={() => switchViewer(isGuest ? 'jim' : 'henry')}
              >
                <span className="ios-role-label">{isGuest ? 'Guest' : 'Jim'}</span>
                <Avatar principal={viewer} id={viewer.id} size="xs" showDot />
              </button>
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
                  <button type="button" className="ios-tile" onClick={() => openChannel('fork-sync')}>
                    <span className="ios-tile-ico has-dot"><IcoBranch /></span>
                    <strong>Fork Sync</strong>
                    <span>1 ready</span>
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
                  Single-channel guest · Scoped strictly to <strong>#fork-sync</strong>
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
                            ? 'henry/train-agent marked feat/belmonte-platform-benches ready in #fork-sync…'
                            : p.status_text}
                        </div>
                      </div>
                    </button>
                  );
                })}
              </div>

              <button type="button" className="ios-plus-fab" onClick={() => openChannel('dm-jim-front-man')}>+</button>
            </div>
          )}

          {mobileTab === 'activity' && (
            <div className="slm-scroll with-dock">
              <div className="ios-chip-row four">
                {(['all', 'dms', 'mentions', 'threads'] as const).map((f) => (
                  <button key={f} type="button" className={activityFilter === f ? 'active' : ''} onClick={() => setActivityFilter(f)}>
                    {f === 'all' ? 'All' : f === 'dms' ? 'DMs' : f === 'mentions' ? 'Mentions' : 'Threads'}
                  </button>
                ))}
              </div>

              <div className="ios-act-list">
                {filteredNotifications.map((n: NotificationItem) => (
                  <button
                    key={n.id}
                    type="button"
                    className="ios-act-item"
                    onClick={() => {
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
                        <strong>{principals[n.author_id]?.display_name || n.author_id}</strong>
                        {principals[n.author_id]?.kind === 'agent' && !n.untrusted_envelope && (
                          <span className="sl-app-tag">AGENT</span>
                        )}
                        {n.untrusted_envelope && <span className="sl-app-tag tag-guest">GUEST</span>}
                        <span className="ios-act-right">
                          <time>{formatRelative(n.created_at)}</time>
                          <span className="ios-reply-pill">💬 2</span>
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

          {/* Sliding Liquid-Glass Bottom Pill Dock + Circular Search Orb */}
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

        {/* ========== LAYER 1: CHANNEL / THREADS-LIST / ALL-CHANNELS (GPU Slide-Over!) ========== */}
        <div
          className={`nav-layer layer-1 ${stackDepth === 2 ? 'underneath' : ''} ${stackDepth === 0 ? 'offscreen' : ''}`}
          style={{ transform: layer1Transform }}
        >
          <DitherBeam preset="floor" />
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
                  : `${activeChannelMeta?.member_count || 2} members`}
              </div>
            </div>
          </header>

          {layer1Mode === 'channel' ? (
            <>
              <div className="slm-feed ios-padded-top" ref={feedRef}>
                <div className="sl-date-divider"><span>Today</span></div>
                {channelMessages.map((msg) => (
                  <SlackMessageRow
                    key={msg.id}
                    msg={msg}
                    principals={principals}
                    viewer={viewer}
                    approvedBranches={approvedBranches}
                    onApproveFork={handleApproveFork}
                    onInspectDiff={setDiffModalBranch}
                    onToggleReaction={handleToggleReaction}
                    onOpenActionSheet={setActionSheetMsg}
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
                        approvedBranches={approvedBranches}
                        onApproveFork={handleApproveFork}
                        onInspectDiff={setDiffModalBranch}
                        onToggleReaction={handleToggleReaction}
                        onOpenActionSheet={setActionSheetMsg}
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

        {/* ========== LAYER 2: THREAD VIEW (GPU Slide-Over on 1 Single Tap!) ========== */}
        <div
          className={`nav-layer layer-2 ${stackDepth < 2 ? 'offscreen' : ''}`}
          style={{ transform: layer2Transform }}
        >
          <DitherBeam preset="floor" />
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
                  approvedBranches={approvedBranches}
                  onApproveFork={handleApproveFork}
                  onInspectDiff={setDiffModalBranch}
                  onToggleReaction={handleToggleReaction}
                  onOpenActionSheet={setActionSheetMsg}
                  inThread
                />
                <div className="ios-new-divider">
                  <span>{threadDetail.replies.length} REPLIES</span>
                </div>
                {threadDetail.replies.map((rep) => (
                  <SlackMessageRow
                    key={rep.id}
                    msg={rep}
                    principals={principals}
                    viewer={viewer}
                    approvedBranches={approvedBranches}
                    onApproveFork={handleApproveFork}
                    onInspectDiff={setDiffModalBranch}
                    onToggleReaction={handleToggleReaction}
                    onOpenActionSheet={setActionSheetMsg}
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
                    placeholder="Add a reply"
                  />
                  <button type="submit" className="ios-cap-send" aria-label="Reply">
                    <IcoSend />
                  </button>
                </form>
              </div>
            </>
          )}
        </div>

        {mobileActionSheet}
        {searchModal}
        {accessModal}
        {diffModal}
      </div>
    );

    if (simulateMobileOnDesktop && !nativeMobile) {
      return (
        <div className="sl-sim-stage">
          <div className="sl-sim-bar">
            <span>Mobile Preview (393 × 852) · Swipe from left edge · Long-press messages</span>
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

      <header className="sl-topbar">
        <div className="sl-topbar-left" />
        <button type="button" className="sl-search-pill" onClick={() => setShowSearchModal(true)}>
          <IcoSearch />
          <span>Search Atelier</span>
          <kbd className="sl-kbd">⌘K</kbd>
        </button>
        <div className="sl-topbar-right">
          {!isGuest && (
            <button type="button" className="sl-top-chip" onClick={() => setShowAccessModal(true)}>
              Tailnet & Onboarding
            </button>
          )}
          <button type="button" className="sl-top-chip" onClick={() => setSimulateMobileOnDesktop(true)}>
            Mobile view
          </button>
          <button type="button" className="sl-top-chip" onClick={() => switchViewer(isGuest ? 'jim' : 'henry')}>
            Viewing as: {isGuest ? 'Henry (Guest)' : 'Jim'}
          </button>
        </div>
      </header>

      <div className={`sl-body ${openThreadId !== null ? 'has-thread' : ''}`}>
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
                {(['all', 'mentions', 'threads'] as const).map((f) => (
                  <button key={f} type="button" className={activityFilter === f ? 'active' : ''} onClick={() => setActivityFilter(f)}>
                    {f === 'all' ? 'All' : f === 'mentions' ? '@Mentions' : 'Threads'}
                  </button>
                ))}
              </div>
              {filteredNotifications.map((n) => (
                <button
                  key={n.id}
                  type="button"
                  className={`sl-sb-act-item ${n.unread ? 'unread' : ''}`}
                  onClick={() => {
                    setActiveChannelId(n.channel_id);
                    setCenterMode('channel');
                    openThread(n.root_id);
                  }}
                >
                  <div className="sl-sb-act-meta">
                    <span>#{n.channel_name}</span>
                    <span>{formatClock(n.created_at)}</span>
                  </div>
                  <div className="sl-sb-act-who">
                    <strong>{principals[n.author_id]?.display_name || n.author_id}</strong>
                  </div>
                  <div className="sl-sb-act-preview">{n.body.slice(0, 72)}</div>
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
                  Single-channel guest on <strong>#fork-sync</strong>
                </div>
              )}
            </div>
          )}
        </aside>

        <main className="sl-main">
          {centerMode === 'channel' && (
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
                  External single-channel guests are in <strong>#fork-sync</strong>
                  {!isGuest && ' · Guest messages are treated strictly as data and never wake worker agents'}
                </div>
              )}

              <div className="sl-feed" ref={feedRef}>
                <div className="sl-date-divider"><span>Today</span></div>
                {channelMessages.map((msg) => (
                  <SlackMessageRow
                    key={msg.id}
                    msg={msg}
                    principals={principals}
                    viewer={viewer}
                    approvedBranches={approvedBranches}
                    onApproveFork={handleApproveFork}
                    onInspectDiff={setDiffModalBranch}
                    onToggleReaction={handleToggleReaction}
                    onOpenActionSheet={setActionSheetMsg}
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
                      approvedBranches={approvedBranches}
                      onApproveFork={handleApproveFork}
                      onInspectDiff={setDiffModalBranch}
                      onToggleReaction={handleToggleReaction}
                      onOpenActionSheet={setActionSheetMsg}
                      inThread
                    />
                    {(th.recent_replies || []).map((rep) => (
                      <SlackMessageRow
                        key={rep.id}
                        msg={rep}
                        principals={principals}
                        viewer={viewer}
                        approvedBranches={approvedBranches}
                        onApproveFork={handleApproveFork}
                        onInspectDiff={setDiffModalBranch}
                        onToggleReaction={handleToggleReaction}
                        onOpenActionSheet={setActionSheetMsg}
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
                  approvedBranches={approvedBranches}
                  onApproveFork={handleApproveFork}
                  onInspectDiff={setDiffModalBranch}
                  onToggleReaction={handleToggleReaction}
                  onOpenActionSheet={setActionSheetMsg}
                  inThread
                />
                <div className="ios-new-divider"><span>{threadDetail.replies.length} REPLIES</span></div>
                {threadDetail.replies.map((rep) => (
                  <SlackMessageRow
                    key={rep.id}
                    msg={rep}
                    principals={principals}
                    viewer={viewer}
                    approvedBranches={approvedBranches}
                    onApproveFork={handleApproveFork}
                    onInspectDiff={setDiffModalBranch}
                    onToggleReaction={handleToggleReaction}
                    onOpenActionSheet={setActionSheetMsg}
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
