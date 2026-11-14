export type PrincipalRole = 'owner' | 'worker' | 'guest';
export type PrincipalKind = 'human' | 'agent';

export interface Principal {
  id: string;
  display_name: string;
  kind: PrincipalKind;
  role: PrincipalRole;
  title: string;
  tailnet_node: string;
  stable_node_id?: string;
  tailscale_user_id?: string;
  tailscale_login?: string;
  hue: string;
  guest_channel_id: string | null;
  status: string;
  status_text: string;
  dm_browser_notify?: boolean;
}

export interface ChannelSummary {
  id: string;
  name: string;
  raw_name: string;
  kind: 'public' | 'private' | 'dm';
  topic: string;
  description: string;
  guest_allowed: boolean;
  joined: boolean;
  starred: boolean;
  unread_count: number;
  mention_count: number;
  member_ids: string[];
  member_count: number;
}

export interface Reaction {
  emoji: string;
  count: number;
  users: string[];
}

export interface MessageMeta {
  card_type?: 'build_receipt' | 'upstream_guideline' | 'fork_submission';
  title?: string;
  badges?: string[];
  artifact?: string;
  main_sha?: string;
  open_for_fork?: string[];
  protected_scopes?: string[];
  fork_repo?: string;
  branch?: string;
  head_sha?: string;
  base_sha?: string;
  up_to_date?: boolean;
  files_changed?: number;
  scopes?: string[];
}

export interface BoardMessage {
  id: number;
  channel_id: string;
  root_id: number | null;
  also_channel: boolean;
  author_id: string;
  author_display_name?: string;
  author_role: PrincipalRole;
  untrusted_guest: boolean;
  envelope_warning: string | null;
  body: string;
  meta: MessageMeta;
  reactions: Reaction[];
  created_at: number;
  reply_count: number;
  last_reply_at: number | null;
  reply_authors: string[];
  subscribed_ids: string[];
  viewer_subscribed: boolean;
  recent_replies?: BoardMessage[];
}

export interface NotificationItem {
  id: number;
  kind: 'mention' | 'dm' | 'thread_reply' | 'guest_triage';
  channel_id: string;
  channel_name: string;
  channel_kind: string;
  message_id: number;
  root_id: number;
  author_id: string;
  author_role: PrincipalRole;
  body: string;
  untrusted_envelope: boolean;
  envelope_banner: string | null;
  created_at: number;
  unread: boolean;
}

export interface ScopeClaim {
  scope: string;
  owner_id: string;
  channel_id: string;
  branch: string;
  note: string;
  claimed_at: number;
}

export interface ThreadDetail {
  channel: { id: string; name: string; kind: string; guest_allowed?: boolean };
  root: BoardMessage;
  replies: BoardMessage[];
  subscribers: { principal_id: string; reason: string }[];
}

export interface SecurityContext {
  tier: 'local_agent' | 'owner_device' | 'tailnet_guest';
  detected_node: string;
  stable_node_id?: string;
  tailscale_login?: string;
  owner_login?: string;
  owner_id?: string;
  owner_nodes: string[];
  guest_jailed: boolean;
}

export interface BootstrapPayload {
  viewer: Principal;
  principals: Record<string, Principal>;
  channels: ChannelSummary[];
  explorable_channels: ChannelSummary[];
  channels_messages: Record<string, BoardMessage[]>;
  threads_by_root: Record<string, ThreadDetail>;
  notifications: NotificationItem[];
  subscribed_threads: BoardMessage[];
  scope_claims: ScopeClaim[];
  default_guest_channel_id?: string | null;
  security?: SecurityContext;
  csrf_token?: string;
}

export interface SyncEventPayload {
  ts: number;
  kind?: string;
  channel_id?: string;
  channel_kind?: 'public' | 'private' | 'dm';
  message?: {
    id: number;
    root_id: number | null;
    author_id: string;
    author_display_name?: string;
    body: string;
    created_at: number;
  };
}
