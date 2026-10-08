//! The board's API contract: every request and response the server speaks. `atelier-board-server --schema` prints it
//! as JSON Schema (committed as platform/web/board/api/board-api.schema.json), and the web app's TypeScript types and a
//! native client's Swift types are generated from that file, so all of them describe the same shapes.
use std::collections::BTreeMap;

use schemars::JsonSchema;
use serde::Serialize;
use serde_json::Value;

/// A stored message, exactly as the mailbox holds it.
#[derive(Serialize, JsonSchema, Clone, Debug, PartialEq)]
pub struct Row {
    pub id: i64,
    /// Seconds since the Unix epoch.
    pub created: f64,
    pub sender: String,
    /// An agent's name, or `*` for the whole board.
    pub recipient: String,
    pub topic: String,
    pub body: String,
    pub reply_to: Option<i64>,
    /// `web-broadcast:{uuid}:{agent}`, `web-broadcast:{uuid}~m:{agent}` (a mention group) or
    /// `web-direct:{uuid}:{agent}` for the addressed copies of one web send; other keys are the sender's own.
    pub dedup: Option<String>,
    /// 1 when its sender asked for a phone notification to the operator.
    pub notify: i64,
}

/// A file named in a message's attachment trailer.
#[derive(Serialize, JsonSchema, Clone, Debug)]
#[serde(untagged)]
pub enum Attachment {
    Present(File),
    /// The file was removed from this machine, or never belonged to the board.
    Missing { missing: bool, name: String },
}

#[derive(Serialize, JsonSchema, Clone, Debug)]
pub struct File {
    pub id: String,
    pub name: String,
    pub mime: String,
    pub size: u64,
    /// Where the board serves it (with byte ranges, for video).
    pub url: String,
    /// A photo's or video's pixel size, when the uploader knew it.
    pub width: Option<u32>,
    pub height: Option<u32>,
    /// Markdown or text small enough to open in the board's reader (`/api/document/{id}`).
    pub readable: bool,
}

/// A message as the board shows it.
#[derive(Serialize, JsonSchema, Clone, Debug)]
pub struct Message {
    #[serde(flatten)]
    pub row: Row,
    /// Everyone the message reached: `["*"]` for the whole board, every addressed copy's recipient for a web send.
    pub audience: Vec<String>,
    /// The body without its attachment trailer, rendered as safe HTML.
    pub body_html: String,
    pub attachments: Vec<Attachment>,
    /// Its recipient replied with an acknowledgement.
    pub acknowledged: bool,
}

#[derive(Serialize, JsonSchema, Clone, Debug)]
pub struct Agent {
    pub agent: String,
    /// The newest message delivered to the agent.
    pub cursor: i64,
    pub pid: Option<i64>,
    pub heartbeat: Option<f64>,
    /// The folder name of the agent's checkout.
    pub checkout: Option<String>,
    pub stop: i64,
    /// Its listener runs as a launchd service.
    pub supervised: bool,
    /// Its one-line status; `idle` when it has none.
    pub task: Option<String>,
    pub task_at: Option<f64>,
    /// Whether the agent's own session is `busy` or `idle`, since `session_since`.
    pub session: Option<String>,
    pub session_since: Option<f64>,
    /// A listener is armed and sent a heartbeat in the last 90 seconds.
    pub listening: bool,
    /// Messages addressed to it that it has not received yet.
    pub pending: i64,
    /// Its listener's last delivery failed.
    pub delivery_error: bool,
    /// The newest message it sent the board's sender (0 for none): marks unread direct messages.
    pub last_to_me: i64,
    /// It has render work in flight (named on the render board, or holding a render lock).
    pub engaged: bool,
}

#[derive(Serialize, JsonSchema, Clone, Debug)]
pub struct LastReply {
    pub sender: String,
    pub body: String,
    pub created: f64,
}

/// An agent blocked on the operator.
#[derive(Serialize, JsonSchema, Clone, Debug)]
pub struct OperatorTask {
    pub id: i64,
    pub created: f64,
    pub agent: String,
    /// The ask's message, the root of the task's thread.
    pub message: i64,
    pub closed: Option<f64>,
    pub closed_by: Option<String>,
    pub note: Option<String>,
    pub edited: Option<f64>,
    /// The ask (its newest wording once edited).
    pub body: String,
    pub body_html: String,
    pub asked: f64,
    pub replies: i64,
    pub last_reply: Option<LastReply>,
}

/// A live render lock holder.
#[derive(Serialize, JsonSchema, Clone, Debug)]
pub struct Holder {
    pub purpose: Value,
    pub kind: Value,
    /// The folder name of the checkout running the job.
    pub checkout: String,
    pub time: Value,
}

#[derive(Serialize, JsonSchema, Clone, Debug, Default)]
pub struct Holders {
    #[serde(skip_serializing_if = "Option::is_none")]
    pub big: Option<Holder>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub small: Option<Holder>,
}

/// A remote agent session the watchdog reports on.
#[derive(Serialize, JsonSchema, Clone, Debug)]
pub struct Session {
    pub name: Value,
    pub url: String,
    pub health: Value,
    pub connection: Value,
    pub fresh: bool,
}

#[derive(Serialize, JsonSchema, Clone, Debug)]
pub struct Resources {
    /// The machine's resource report is under two minutes old.
    pub fresh: bool,
    pub cpu: Option<f64>,
    pub available_gib: Option<f64>,
}

/// The Threads and Activity tabs' unread badges.
#[derive(Serialize, JsonSchema, Clone, Debug)]
pub struct InboxSummary {
    pub threads: i64,
    pub activity: i64,
}

/// `GET /api/state`: the feed page, the agents, the render board and everything the header shows.
#[derive(Serialize, JsonSchema, Clone, Debug)]
pub struct State {
    pub time: f64,
    /// Newest first. Every copy of a web send on the page is included, even past the page's limit.
    pub messages: Vec<Message>,
    pub has_more: bool,
    pub agents: Vec<Agent>,
    pub total: i64,
    /// The operator's open tasks, oldest first.
    pub tasks: Vec<OperatorTask>,
    /// The render board's Holding, Waiting, Handoffs and Log sections (Log cut to the newest `log` entries).
    pub schedule: BTreeMap<String, String>,
    pub log_total: i64,
    pub inbox: InboxSummary,
    pub holders: Holders,
    pub sessions: Vec<Session>,
    pub resources: Resources,
    /// Send it back as `X-Board-CSRF` on every POST.
    pub csrf: String,
    /// The name the board posts as.
    pub sender: String,
}

/// Who a reply goes to: `*` for the whole board, or these agents.
#[derive(Serialize, JsonSchema, Clone, Debug, PartialEq)]
#[serde(untagged)]
pub enum ReplyAudience {
    Everyone(String),
    Agents(Vec<String>),
}

/// A message as the inbox shows it.
#[derive(Serialize, JsonSchema, Clone, Debug)]
pub struct Card {
    pub id: i64,
    pub created: f64,
    pub sender: String,
    pub recipient: String,
    pub topic: String,
    pub reply_to: Option<i64>,
    pub dedup: Option<String>,
    pub body: String,
    pub body_html: String,
    pub attachments: Vec<Attachment>,
    pub acknowledged: bool,
    /// One line of plain text, at most 160 characters and an ellipsis.
    pub snippet: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub audience: Option<Vec<String>>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub unread: Option<bool>,
}

#[derive(Serialize, JsonSchema, Clone, Debug)]
pub struct ThreadItem {
    /// The root message's id.
    pub id: i64,
    /// The thread's read-state key.
    pub key: String,
    pub root: Card,
    /// The newest replies, oldest first.
    pub latest: Vec<Card>,
    pub replies: i64,
    /// Unread replies.
    pub unread: i64,
    pub participants: Vec<String>,
    pub reply_audience: ReplyAudience,
    pub last_activity: f64,
    pub newest: i64,
}

/// `GET /api/threads`: the conversations the reader is part of, unread first, then by newest reply.
#[derive(Serialize, JsonSchema, Clone, Debug)]
pub struct Threads {
    pub threads: Vec<ThreadItem>,
    pub total: i64,
    pub unread: i64,
}

#[derive(Serialize, JsonSchema, Clone, Debug)]
pub struct ActivityItem {
    /// `mention`, `reply`, `dm` or `ack`.
    pub kind: String,
    pub id: i64,
    pub created: f64,
    pub unread: i64,
    pub count: i64,
    /// The thread's root message id.
    pub thread: i64,
    pub replies: i64,
    pub message: Option<Card>,
    pub senders: Vec<String>,
    pub reply_audience: ReplyAudience,
    /// The thread's root, when it is not the message itself.
    pub root: Option<Card>,
    /// For an acknowledgement, the reader's message it acknowledges.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub target: Option<Option<Card>>,
}

#[derive(Serialize, JsonSchema, Clone, Debug, Default)]
pub struct ActivityCounts {
    pub all: i64,
    pub mention: i64,
    pub reply: i64,
    pub dm: i64,
    pub ack: i64,
}

/// `GET /api/activity`: what involves the reader, newest first.
#[derive(Serialize, JsonSchema, Clone, Debug)]
pub struct Activity {
    pub items: Vec<ActivityItem>,
    pub total: i64,
    pub unread: ActivityCounts,
}

/// `GET /api/thread?id=`: a whole conversation, oldest first.
#[derive(Serialize, JsonSchema, Clone, Debug)]
pub struct Thread {
    /// The root: every addressed copy of a web send.
    pub root: Vec<Message>,
    pub replies: Vec<Message>,
}

/// `GET /api/document/{id}`: a Markdown or text attachment, rendered for the reader.
#[derive(Serialize, JsonSchema, Clone, Debug)]
pub struct Document {
    pub name: String,
    pub url: String,
    pub size: u64,
    pub html: String,
}

/// `POST /api/upload` (the raw file as the body, `X-File-Name`, and optionally `X-Media-Width`/`X-Media-Height`).
#[derive(Serialize, JsonSchema, Clone, Debug)]
pub struct Upload {
    pub id: String,
    pub name: String,
    pub mime: String,
    pub size: u64,
    pub width: Option<u32>,
    pub height: Option<u32>,
}

/// `POST /api/send` and `/api/broadcast`.
#[derive(Serialize, JsonSchema, Clone, Debug)]
pub struct Sent {
    /// One addressed copy per recipient.
    pub messages: Vec<Row>,
    pub recipients: Vec<String>,
}

/// `POST /api/send`. `/api/broadcast` takes the same without `recipient` and reaches every listening agent.
#[derive(JsonSchema)]
#[allow(dead_code)]
pub struct SendRequest {
    pub body: String,
    /// A fresh UUID per message: a retry with the same one never sends twice.
    pub request_id: String,
    /// Defaults to `request`.
    pub topic: Option<String>,
    /// One agent, the agents a message @mentions, or `*`.
    pub recipient: Option<Recipient>,
    pub reply_to: Option<i64>,
    /// Upload ids, at most 10.
    pub attachments: Option<Vec<String>>,
}

#[derive(JsonSchema)]
#[serde(untagged)]
#[allow(dead_code)]
pub enum Recipient {
    One(String),
    Mentioned(Vec<String>),
}

/// `POST /api/preview`.
#[derive(JsonSchema)]
#[allow(dead_code)]
pub struct PreviewRequest {
    /// At most 8000 characters.
    pub body: String,
}

#[derive(Serialize, JsonSchema)]
pub struct Preview {
    pub html: String,
}

/// `POST /api/read`: mark a thread read (up to `through`, else its newest message), follow or unfollow it, or mark
/// everything read with `all`.
#[derive(JsonSchema)]
#[allow(dead_code)]
pub struct ReadRequest {
    pub id: Option<i64>,
    pub through: Option<i64>,
    pub all: Option<bool>,
    pub follow: Option<bool>,
}

#[derive(Serialize, JsonSchema)]
pub struct Read {
    /// The thread's key, or `*` for everything.
    pub read: String,
}

/// `POST /api/task/dismiss`.
#[derive(JsonSchema)]
#[allow(dead_code)]
pub struct DismissRequest {
    pub id: i64,
    pub note: Option<String>,
}

#[derive(Serialize, JsonSchema)]
pub struct Dismissed {
    pub dismissed: i64,
    /// It had been dismissed before.
    pub already: bool,
}

/// `POST /api/remove`.
#[derive(JsonSchema)]
#[allow(dead_code)]
pub struct RemoveRequest {
    pub agent: String,
}

#[derive(Serialize, JsonSchema)]
pub struct Removed {
    pub removed: String,
}

/// `POST /api/push/subscribe`: a browser's PushSubscription as JSON. `/api/push/unsubscribe` takes `{endpoint}`.
#[derive(JsonSchema)]
#[allow(dead_code)]
pub struct PushSubscribeRequest {
    pub subscription: PushSubscription,
}

#[derive(JsonSchema)]
#[allow(dead_code)]
pub struct PushSubscription {
    pub endpoint: String,
    pub keys: PushKeys,
}

#[derive(JsonSchema)]
#[allow(dead_code)]
pub struct PushKeys {
    pub p256dh: String,
    pub auth: String,
}

#[derive(JsonSchema)]
#[allow(dead_code)]
pub struct PushUnsubscribeRequest {
    pub endpoint: String,
}

#[derive(Serialize, JsonSchema)]
pub struct Subscribed {
    pub subscribed: bool,
}

#[derive(Serialize, JsonSchema)]
pub struct Delivered {
    /// Devices the sample notification reached.
    pub delivered: i64,
}

/// `GET /api/push/key`: the VAPID public key, for PushManager.subscribe.
#[derive(Serialize, JsonSchema)]
pub struct PushKey {
    pub key: String,
}

/// Every failure: a sentence to show the person.
#[derive(Serialize, JsonSchema)]
pub struct Problem {
    pub error: String,
}

#[derive(Serialize, JsonSchema)]
pub struct Ok {
    pub ok: bool,
}

/// Every shape in one document, so one schema file names them all.
#[derive(JsonSchema)]
#[allow(dead_code)]
pub struct Contract {
    state: State,
    threads: Threads,
    activity: Activity,
    thread: Thread,
    document: Document,
    upload: Upload,
    sent: Sent,
    send_request: SendRequest,
    preview_request: PreviewRequest,
    preview: Preview,
    read_request: ReadRequest,
    read: Read,
    dismiss_request: DismissRequest,
    dismissed: Dismissed,
    remove_request: RemoveRequest,
    removed: Removed,
    push_subscribe_request: PushSubscribeRequest,
    push_unsubscribe_request: PushUnsubscribeRequest,
    subscribed: Subscribed,
    delivered: Delivered,
    push_key: PushKey,
    problem: Problem,
    ok: Ok,
}

pub fn schema() -> String {
    let schema = schemars::schema_for!(Contract);
    serde_json::to_string_pretty(&schema).unwrap() + "\n"
}
