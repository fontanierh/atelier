export type PrincipalRole = 'owner' | 'coordinator' | 'worker' | 'guest';
export type PrincipalHue = 'ice' | 'accent' | 'lilac' | 'periwinkle' | 'rose' | 'attention' | 'success';

export interface Principal {
  id: string;
  display_name: string;
  kind: 'human' | 'agent';
  role: PrincipalRole;
  host: string;
  status: 'active' | 'idle' | 'offline';
  status_text: string;
  guest_channel_id: string | null;
  hue: PrincipalHue;
}

export interface ChannelSummary {
  id: string;
  name: string;
  kind: 'public' | 'private' | 'dm';
  guest_allowed: boolean;
  topic: string;
  description: string;
  joined: boolean;
  member_ids: string[];
  member_count: number;
  message_count: number;
  latest_id: number;
  unread_count: number;
  mention_count: number;
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
  protected_scopes?: string[];
  open_for_fork?: string[];
  fork_repo?: string;
  branch?: string;
  head_sha?: string;
  base_sha?: string;
  up_to_date?: boolean;
  files_changed?: number;
  scopes?: string[];
  triage_status?: string;
}

export interface BoardMessage {
  id: number;
  channel_id: string;
  root_id: number | null;
  also_channel: boolean;
  author_id: string;
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
  subscription_reason?: string;
}

export interface NotificationItem {
  id: number;
  kind: 'mention' | 'thread_reply' | 'dm' | 'guest_triage';
  channel_id: string;
  channel_name: string;
  channel_kind: string;
  message_id: number;
  root_id: number;
  author_id: string;
  author_role: PrincipalRole;
  untrusted_envelope: boolean;
  body: string;
  meta: MessageMeta;
  unread: boolean;
  created_at: number;
}

export interface WorkspaceSnapshot {
  viewer: Principal;
  host: { name: string; main_sha: string; fork_ahead: number; fork_behind: number };
  principals: Record<string, Principal>;
  channels: ChannelSummary[];
  explorable_channels: ChannelSummary[];
  notifications: NotificationItem[];
  subscribed_threads: BoardMessage[];
}

export interface ThreadDetail {
  channel: ChannelSummary;
  root: BoardMessage;
  replies: BoardMessage[];
  subscribers: { principal_id: string; reason: string }[];
}

export interface SecurityInfo {
  caller_tier: 'owner_device' | 'local_agent' | 'tailnet_guest';
  detected_node: string;
  owner_nodes: string[];
  guest_channel: string;
  board_url: string;
}

export interface BootstrapPayload extends WorkspaceSnapshot {
  channels_messages: Record<string, BoardMessage[]>;
  threads_by_root: Record<string, ThreadDetail>;
  csrf_token: string;
  security?: SecurityInfo;
}
