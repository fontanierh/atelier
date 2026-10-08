//! The board's sender's inbox, as in Slack: Threads (every conversation with replies they are part of, unread first,
//! then newest reply first) and Activity (everything that involves them, newest first: @mentions, replies in their
//! threads, direct messages, and acknowledgements grouped like reactions). Ported from board_inbox.py.
//!
//! Read state lives on the board, in the `reads` table, so every device agrees. A thread is read up to the newest of:
//! its own mark, the reader's "mark all read", the baseline the table was created with (history from before read state
//! starts read), and the reader's own newest message in it (replying means you read what came before).
use std::collections::{HashMap, HashSet};
use std::sync::LazyLock;

use regex::Regex;
use rusqlite::{Connection, OptionalExtension, params};

use crate::api::{Activity, ActivityCounts, ActivityItem, Card, InboxSummary, ReplyAudience, ThreadItem, Threads};
use crate::db::{self, Result, bad};
use crate::{files, markdown, store};

static MENTION: LazyLock<Regex> = LazyLock::new(|| Regex::new(r"(?:^|[^\w@.-])@([A-Za-z0-9][\w.-]*)").unwrap());
static SYSTEM: LazyLock<Regex> = LazyLock::new(|| Regex::new(r"(^|-)watch$").unwrap());
static MARKUP: LazyLock<Regex> = LazyLock::new(|| Regex::new(r"[*_`#>]+").unwrap());
static SPACE: LazyLock<Regex> = LazyLock::new(|| Regex::new(r"\s+").unwrap());
const SNIPPET: usize = 160;
pub const KINDS: &[&str] = &["mention", "reply", "dm", "ack"];

/// Automatic notices (render-watch and the like): the feed folds them away and they never make anything unread.
pub fn is_system(sender: &str) -> bool {
    SYSTEM.is_match(sender)
}

pub fn mentions(body: &str, reader: &str) -> bool {
    let reader = reader.to_lowercase();
    MENTION.captures_iter(body).any(|found| found[1].trim_end_matches(['.', '-']).to_lowercase() == reader)
}

/// One line of plain text for a list.
pub fn snippet(text: &str, has_files: bool) -> String {
    let flat = SPACE.replace_all(&MARKUP.replace_all(text, ""), " ").trim().to_owned();
    if flat.is_empty() {
        return if has_files { "Attachment".into() } else { String::new() };
    }
    if flat.chars().count() > SNIPPET { flat.chars().take(SNIPPET).collect::<String>() + "…" } else { flat }
}

/// A message as the inbox shows it: rendered body, attachments and a one-line snippet.
pub fn card(row: &crate::api::Row) -> Card {
    let (text, attachments) = files::split_attachments(&row.body);
    Card {
        id: row.id,
        created: row.created,
        sender: row.sender.clone(),
        recipient: row.recipient.clone(),
        topic: row.topic.clone(),
        reply_to: row.reply_to,
        dedup: row.dedup.clone(),
        body: row.body.clone(),
        body_html: markdown::cached(text),
        snippet: snippet(text, !attachments.is_empty()),
        attachments,
        acknowledged: false,
        audience: None,
        unread: None,
    }
}

/// The message index: everything about a message except its body.
#[derive(Clone, Debug)]
struct Head {
    id: i64,
    created: f64,
    sender: String,
    recipient: String,
    topic: String,
    reply_to: Option<i64>,
    dedup: Option<String>,
}

/// Every addressed copy of one web send is one message.
pub fn group_key(id: i64, dedup: Option<&str>) -> String {
    match dedup {
        Some(dedup) if dedup.starts_with("web-broadcast:") || dedup.starts_with("web-direct:") => {
            dedup[..dedup.rfind(':').unwrap()].to_owned()
        }
        _ => format!("m{id}"),
    }
}

fn key_of(row: &Head) -> String {
    group_key(row.id, row.dedup.as_deref())
}

struct Conversation {
    key: String,
    roots: Vec<usize>,
    messages: Vec<usize>,
    first_involved: Option<i64>,
    read: i64,
    unfollowed: Option<i64>,
    following: bool,
    starred: bool,
    newest: usize,
}

/// Every thread on the board seen from `reader`, built from one pass over the message index.
struct Inbox<'a> {
    db: &'a Connection,
    reader: &'a str,
    rows: Vec<Head>,
    index: HashMap<i64, usize>,
    mentioned: HashSet<i64>,
    threads: Vec<Conversation>,
    thread_of: Vec<usize>,
}

impl<'a> Inbox<'a> {
    fn new(db: &'a Connection, reader: &'a str) -> Result<Self> {
        let mut statement =
            db.prepare("SELECT id, created, sender, recipient, topic, reply_to, dedup FROM messages ORDER BY id")?;
        let rows: Vec<Head> = statement
            .query_map([], |r| {
                Ok(Head {
                    id: r.get(0)?,
                    created: r.get(1)?,
                    sender: r.get(2)?,
                    recipient: r.get(3)?,
                    topic: r.get(4)?,
                    reply_to: r.get(5)?,
                    dedup: r.get(6)?,
                })
            })?
            .collect::<rusqlite::Result<_>>()?;
        let mut mentioned = HashSet::new();
        {
            let mut candidates =
                db.prepare("SELECT id, body FROM messages WHERE sender!=? AND instr(lower(body), ?)>0")?;
            let found = candidates.query_map(params![reader, format!("@{}", reader.to_lowercase())], |r| {
                Ok((r.get::<_, i64>(0)?, r.get::<_, String>(1)?))
            })?;
            for item in found {
                let (id, body) = item?;
                if mentions(&body, reader) {
                    mentioned.insert(id);
                }
            }
        }
        let index: HashMap<i64, usize> = rows.iter().enumerate().map(|(i, row)| (row.id, i)).collect();
        let mut threads: Vec<Conversation> = Vec::new();
        let mut by_key: HashMap<String, usize> = HashMap::new();
        let mut root_of: HashMap<i64, i64> = HashMap::new();
        let mut thread_of = Vec::with_capacity(rows.len());
        for (i, row) in rows.iter().enumerate() {
            let root = match row.reply_to {
                Some(parent) if index.contains_key(&parent) => *root_of.get(&parent).unwrap_or(&row.id),
                _ => row.id,
            };
            root_of.insert(row.id, root);
            let key = key_of(&rows[index[&root]]);
            let slot = *by_key.entry(key.clone()).or_insert_with(|| {
                threads.push(Conversation {
                    key,
                    roots: Vec::new(),
                    messages: Vec::new(),
                    first_involved: None,
                    read: 0,
                    unfollowed: None,
                    following: false,
                    starred: false,
                    newest: i,
                });
                threads.len() - 1
            });
            if root == row.id { threads[slot].roots.push(i) } else { threads[slot].messages.push(i) }
            thread_of.push(slot);
        }
        let mut inbox = Inbox { db, reader, rows, index, mentioned, threads, thread_of };
        inbox.read_state()?;
        Ok(inbox)
    }

    fn has_table(&self, name: &str) -> Result<bool> {
        let found = self.db.query_row("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", [name], |_| Ok(()));
        Ok(found.optional()?.is_some())
    }

    fn read_state(&mut self) -> Result<()> {
        let has_reads = self.has_table("reads")?;
        let mut stars = HashSet::new();
        if self.has_table("stars")? {
            let mut statement = self.db.prepare("SELECT thread FROM stars WHERE reader=?")?;
            for key in statement.query_map([self.reader], |r| r.get::<_, String>(0))? {
                stars.insert(key?);
            }
        }
        let mut marks: HashMap<(String, String), (i64, Option<i64>)> = HashMap::new();
        if has_reads {
            let mut statement =
                self.db.prepare("SELECT reader, thread, last_read, unfollowed FROM reads WHERE reader IN (?, '*')")?;
            let found = statement.query_map([self.reader], |r| {
                Ok(((r.get::<_, String>(0)?, r.get::<_, String>(1)?), (r.get::<_, i64>(2)?, r.get(3)?)))
            })?;
            for item in found {
                let (key, value) = item?;
                marks.insert(key, value);
            }
        }
        let mark = |who: &str, key: &str| marks.get(&(who.to_owned(), key.to_owned())).copied();
        // Without the table (an older store) nothing is unread yet.
        let baseline =
            if has_reads { mark("*", "*").map_or(0, |m| m.0) } else { self.rows.last().map_or(0, |row| row.id) };
        let everything = baseline.max(mark(self.reader, "*").map_or(0, |m| m.0));
        for t in 0..self.threads.len() {
            let thread = &self.threads[t];
            let every: Vec<usize> = thread.roots.iter().chain(&thread.messages).copied().collect();
            let own = every.iter().filter(|&&i| self.rows[i].sender == self.reader).map(|&i| self.rows[i].id).max();
            let involved = every.iter().filter(|&&i| self.involves(i)).map(|&i| self.rows[i].id).min();
            let own_mark = mark(self.reader, &thread.key);
            let read = everything.max(own_mark.map_or(0, |m| m.0)).max(own.unwrap_or(0));
            let mut unfollowed = own_mark.and_then(|m| m.1).filter(|&since| since != 0);
            // Unfollowing hides a thread until someone @mentions you in it again.
            if let Some(since) = unfollowed {
                if thread.messages.iter().any(|&i| self.rows[i].id > since && self.mentioned.contains(&self.rows[i].id))
                {
                    unfollowed = None;
                }
            }
            let newest = *every.last().unwrap();
            let thread = &mut self.threads[t];
            thread.starred = stars.contains(&thread.key);
            thread.first_involved = involved;
            thread.read = read;
            thread.unfollowed = unfollowed;
            thread.following = involved.is_some() && unfollowed.is_none();
            thread.newest = newest;
        }
        Ok(())
    }

    fn involves(&self, i: usize) -> bool {
        let row = &self.rows[i];
        row.sender == self.reader || row.recipient == self.reader || self.mentioned.contains(&row.id)
    }

    fn from_others(&self, i: usize) -> bool {
        self.rows[i].sender != self.reader && !is_system(&self.rows[i].sender)
    }

    fn unread(&self, i: usize) -> bool {
        self.from_others(i) && self.rows[i].id > self.threads[self.thread_of[i]].read
    }

    /// Unread, and more than an acknowledgement: acks are like reactions and never make a thread unread.
    fn new_in_thread(&self, i: usize) -> bool {
        self.rows[i].topic != "ack" && self.unread(i)
    }

    /// The thread's replies as messages: a web reply's addressed copies are one.
    fn replies(&self, thread: &Conversation) -> Vec<Vec<usize>> {
        let mut groups: Vec<Vec<usize>> = Vec::new();
        let mut slots: HashMap<String, usize> = HashMap::new();
        for &i in &thread.messages {
            let key = key_of(&self.rows[i]);
            match slots.get(&key) {
                Some(&slot) => groups[slot].push(i),
                None => {
                    slots.insert(key, groups.len());
                    groups.push(vec![i]);
                }
            }
        }
        groups
    }

    /// Threads with replies that the reader started, joined, was addressed or @mentioned in, and still follows.
    fn open_threads(&self) -> Vec<usize> {
        (0..self.threads.len()).filter(|&t| !self.threads[t].messages.is_empty() && self.threads[t].following).collect()
    }

    /// Who a reply from the reader goes to, before the web board drops retired agents: `*` for a thread the reader
    /// opened to the whole board, else the agent who started it (or those the reader's opening addressed) and
    /// everyone who joined in.
    fn audience(&self, thread: &Conversation) -> ReplyAudience {
        let first = &self.rows[thread.roots[0]];
        let dedup = first.dedup.as_deref().unwrap_or("");
        if first.sender == self.reader
            && !dedup.contains("~m:")
            && (first.recipient == "*" || dedup.starts_with("web-broadcast:"))
        {
            return ReplyAudience::Everyone("*".into());
        }
        let mut names: Vec<&str> = if first.sender == self.reader {
            thread.roots.iter().map(|&i| self.rows[i].recipient.as_str()).collect()
        } else {
            vec![first.sender.as_str()]
        };
        for &i in &thread.messages {
            let row = &self.rows[i];
            names.push(if row.sender == self.reader { &row.recipient } else { &row.sender });
        }
        let mut seen = HashSet::new();
        ReplyAudience::Agents(
            names
                .into_iter()
                .filter(|name| seen.insert(*name) && *name != "*" && *name != self.reader && !is_system(name))
                .map(str::to_owned)
                .collect(),
        )
    }

    fn bodies(&self, ids: impl IntoIterator<Item = i64>) -> Result<HashMap<i64, Card>> {
        let ids: Vec<i64> = ids.into_iter().collect::<HashSet<_>>().into_iter().collect();
        let mut out = HashMap::new();
        for chunk in ids.chunks(500) {
            let sql = format!("SELECT {} FROM messages WHERE id IN ({})", db::MESSAGE, db::marks(chunk.len()));
            for row in db::messages(self.db, &sql, rusqlite::params_from_iter(chunk))? {
                out.insert(row.id, card(&row));
            }
        }
        Ok(out)
    }

    fn id(&self, i: usize) -> i64 {
        self.rows[i].id
    }
}

fn unique<'a>(names: impl IntoIterator<Item = &'a str>) -> Vec<String> {
    let mut seen = HashSet::new();
    names.into_iter().filter(|name| seen.insert(*name)).map(str::to_owned).collect()
}

/// The Threads view: unread threads first, then the rest, each by newest reply, as Slack orders them. `starred` lists
/// only the reader's starred threads, replies or not, followed or not.
pub fn threads(db: &Connection, reader: &str, limit: usize, starred: bool) -> Result<Threads> {
    const LATEST: usize = 3;
    let inbox = Inbox::new(db, reader)?;
    let chosen: Vec<usize> = if starred {
        (0..inbox.threads.len()).filter(|&t| inbox.threads[t].starred).collect()
    } else {
        inbox.open_threads()
    };
    let mut listed: Vec<(usize, Vec<i64>)> = chosen
        .into_iter()
        .map(|t| {
            let thread = &inbox.threads[t];
            let unread = thread
                .messages
                .iter()
                .chain(&thread.roots)
                .filter(|&&i| inbox.new_in_thread(i))
                .map(|&i| inbox.id(i))
                .collect();
            (t, unread)
        })
        .collect();
    listed.sort_by_key(|(t, unread)| (unread.is_empty(), -inbox.id(inbox.threads[*t].newest)));
    let page = &listed[..limit.min(listed.len())];
    let mut shown = Vec::new();
    for (t, _) in page {
        let thread = &inbox.threads[*t];
        shown.push(inbox.id(thread.roots[0]));
        let groups = inbox.replies(thread);
        shown.extend(groups[groups.len().saturating_sub(LATEST)..].iter().map(|g| inbox.id(g[0])));
    }
    let bodies = inbox.bodies(shown)?;
    let mut items = Vec::new();
    for (t, unread_ids) in page {
        let thread = &inbox.threads[*t];
        let groups = inbox.replies(thread);
        let root = &inbox.rows[thread.roots[0]];
        let unread_groups: HashSet<String> = thread
            .messages
            .iter()
            .filter(|&&i| unread_ids.contains(&inbox.id(i)))
            .map(|&i| key_of(&inbox.rows[i]))
            .collect();
        let latest = groups[groups.len().saturating_sub(LATEST)..]
            .iter()
            .map(|group| {
                let mut audience: Vec<String> = group.iter().map(|&i| inbox.rows[i].recipient.clone()).collect();
                audience.sort();
                audience.dedup();
                Card {
                    audience: Some(audience),
                    unread: Some(unread_groups.contains(&key_of(&inbox.rows[group[0]]))),
                    ..bodies[&inbox.id(group[0])].clone()
                }
            })
            .collect();
        let newest = &inbox.rows[thread.newest];
        items.push(ThreadItem {
            id: root.id,
            key: thread.key.clone(),
            root: Card {
                audience: Some(thread.roots.iter().map(|&i| inbox.rows[i].recipient.clone()).collect()),
                unread: Some(unread_ids.contains(&root.id)),
                ..bodies[&root.id].clone()
            },
            latest,
            replies: groups.len() as i64,
            unread: unread_groups.len() as i64,
            participants: unique(
                thread.roots[..1].iter().chain(&thread.messages).map(|&i| inbox.rows[i].sender.as_str()),
            ),
            reply_audience: inbox.audience(thread),
            last_activity: newest.created,
            newest: newest.id,
            starred: thread.starred,
        });
    }
    Ok(Threads {
        threads: items,
        total: listed.len() as i64,
        unread: listed.iter().filter(|(_, unread)| !unread.is_empty()).count() as i64,
        starred: inbox.threads.iter().filter(|thread| thread.starred).count() as i64,
    })
}

struct Entry {
    kind: &'static str,
    rows: Vec<usize>,
    unread: i64,
    thread: usize,
    target: Option<i64>,
}

/// What involves the reader, oldest first: an @mention, a direct message, a reply addressed to them, the other
/// replies in a thread they were in by then (one entry per thread, as Slack folds a thread's new replies), and the
/// acknowledgements of their own message (one entry per message, like reactions).
fn activity_entries(inbox: &Inbox) -> Vec<Entry> {
    let mut entries: Vec<Entry> = Vec::new();
    let mut slots: HashMap<String, usize> = HashMap::new();
    for i in 0..inbox.rows.len() {
        if !inbox.from_others(i) {
            continue;
        }
        let row = &inbox.rows[i];
        let t = inbox.thread_of[i];
        let thread = &inbox.threads[t];
        let in_thread = row.reply_to.is_some()
            && thread.first_involved.is_some_and(|first| first < row.id)
            && thread.unfollowed.is_none();
        let target = row.reply_to.and_then(|parent| inbox.index.get(&parent)).map(|&j| &inbox.rows[j]);
        let (kind, key) = if inbox.mentioned.contains(&row.id) {
            ("mention", format!("i{}", row.id))
        } else if let (true, Some(target)) = (row.topic == "ack", target) {
            if target.sender != inbox.reader {
                continue;
            }
            ("ack", format!("a{}", key_of(target)))
        } else if row.recipient == inbox.reader {
            (if row.reply_to.is_some() { "reply" } else { "dm" }, format!("i{}", row.id))
        } else if in_thread {
            ("reply", format!("t{}", thread.key))
        } else {
            continue;
        };
        let slot = *slots.entry(key).or_insert_with(|| {
            entries.push(Entry { kind, rows: Vec::new(), unread: 0, thread: t, target: None });
            entries.len() - 1
        });
        let entry = &mut entries[slot];
        entry.rows.push(i);
        entry.unread += inbox.unread(i) as i64;
        if kind == "ack" {
            entry.target = target.map(|target| target.id);
        }
    }
    entries
}

/// The Activity view, newest first, and its unread counts. Acknowledgements show as read or unread but never count
/// toward the badge, which only real messages raise.
pub fn activity(db: &Connection, reader: &str, kind: &str, unread_only: bool, limit: usize) -> Result<Activity> {
    if !kind.is_empty() && !KINDS.contains(&kind) {
        return bad("unknown activity kind");
    }
    let inbox = Inbox::new(db, reader)?;
    let mut entries = activity_entries(&inbox);
    let mut counts = ActivityCounts::default();
    for entry in &entries {
        if entry.unread > 0 {
            match entry.kind {
                "mention" => counts.mention += 1,
                "reply" => counts.reply += 1,
                "dm" => counts.dm += 1,
                _ => counts.ack += 1,
            }
            counts.all += (entry.kind != "ack") as i64;
        }
    }
    let newest = |entry: &Entry| inbox.id(*entry.rows.last().unwrap());
    entries.sort_by_key(|entry| -newest(entry));
    entries.retain(|entry| (kind.is_empty() || entry.kind == kind) && (entry.unread > 0 || !unread_only));
    let total = entries.len() as i64;
    entries.truncate(limit);
    let mut wanted = Vec::new();
    for entry in &entries {
        wanted.push(newest(entry));
        wanted.push(inbox.id(inbox.threads[entry.thread].roots[0]));
        wanted.extend(entry.target);
    }
    let bodies = inbox.bodies(wanted)?;
    let mut items = Vec::new();
    for entry in &entries {
        let thread = &inbox.threads[entry.thread];
        let last = &inbox.rows[*entry.rows.last().unwrap()];
        let root = inbox.id(thread.roots[0]);
        // A thread's folded replies say how many are new and from whom; once read, the entry is its newest reply.
        let rows: Vec<usize> = if entry.kind == "reply" {
            let unread: Vec<usize> = entry.rows.iter().copied().filter(|&i| inbox.unread(i)).collect();
            if unread.is_empty() { vec![*entry.rows.last().unwrap()] } else { unread }
        } else {
            entry.rows.clone()
        };
        items.push(ActivityItem {
            kind: entry.kind.into(),
            id: last.id,
            created: last.created,
            unread: entry.unread,
            count: rows.len() as i64,
            thread: root,
            replies: inbox.replies(thread).len() as i64,
            message: bodies.get(&last.id).cloned(),
            senders: unique(rows.iter().map(|&i| inbox.rows[i].sender.as_str())),
            reply_audience: inbox.audience(thread),
            root: if root == last.id { None } else { bodies.get(&root).cloned() },
            target: (entry.kind == "ack").then(|| entry.target.and_then(|id| bodies.get(&id).cloned())),
        });
    }
    Ok(Activity { items, total, unread: counts })
}

/// The badges: threads with unread replies, and unread activity (acknowledgements aside); and, by agent, how many of
/// its direct messages to the reader are unread.
pub fn summary(db: &Connection, reader: &str) -> Result<(InboxSummary, HashMap<String, i64>)> {
    let inbox = Inbox::new(db, reader)?;
    let threads = inbox
        .open_threads()
        .into_iter()
        .filter(|&t| {
            let thread = &inbox.threads[t];
            thread.roots.iter().chain(&thread.messages).any(|&i| inbox.new_in_thread(i))
        })
        .count() as i64;
    let activity =
        activity_entries(&inbox).iter().filter(|entry| entry.kind != "ack" && entry.unread > 0).count() as i64;
    let mut direct: HashMap<String, i64> = HashMap::new();
    for i in 0..inbox.rows.len() {
        if inbox.rows[i].recipient == reader && inbox.rows[i].topic != "ack" && inbox.unread(i) {
            *direct.entry(inbox.rows[i].sender.clone()).or_default() += 1;
        }
    }
    Ok((InboxSummary { threads, activity }, direct))
}

/// Each message's thread key, for every message on the board (as Inbox::new finds a thread's root).
fn thread_keys(db: &Connection) -> Result<HashMap<i64, String>> {
    let mut statement = db.prepare("SELECT id, reply_to, dedup FROM messages ORDER BY id")?;
    let rows = statement.query_map([], |r| Ok((r.get::<_, i64>(0)?, r.get::<_, Option<i64>>(1)?, r.get(2)?)))?;
    let mut keys: HashMap<i64, String> = HashMap::new();
    for row in rows {
        let (id, reply_to, dedup): (i64, Option<i64>, Option<String>) = row?;
        let key = match reply_to.and_then(|parent| keys.get(&parent)) {
            Some(key) => key.clone(),
            None => group_key(id, dedup.as_deref()),
        };
        keys.insert(id, key);
    }
    Ok(keys)
}

/// The reader had these messages on screen: each one's thread is read up to the newest of them there. Marks only move
/// forward. Returns how many threads moved.
pub fn mark_seen(reader: &str, ids: &serde_json::Value) -> Result<i64> {
    store::agent_name(reader)?;
    let Some(list) = ids.as_array().filter(|list| list.len() <= 500) else {
        return bad("ids must be a list of at most 500 message ids");
    };
    let mut wanted = Vec::new();
    for value in list {
        match store::integer(value) {
            Some(id) => wanted.push(id),
            None => return bad("ids must be message ids"),
        }
    }
    let mut db = db::write()?;
    let tx = db::immediate(&mut db)?;
    let keys = thread_keys(&tx)?;
    let mut through: HashMap<&str, i64> = HashMap::new();
    for id in wanted {
        if let Some(key) = keys.get(&id) {
            let mark = through.entry(key.as_str()).or_default();
            *mark = (*mark).max(id);
        }
    }
    let mut moved = 0;
    for (key, mark) in through {
        moved += tx.execute(
            "INSERT INTO reads (reader, thread, last_read) VALUES (?, ?, ?) ON CONFLICT (reader, thread) \
             DO UPDATE SET last_read=excluded.last_read WHERE excluded.last_read > last_read",
            params![reader, key, mark],
        )? as i64;
    }
    tx.commit()?;
    Ok(moved)
}

/// Star or unstar the thread `id` is in. Returns the thread's key.
pub fn star(reader: &str, id: &serde_json::Value, starred: bool) -> Result<String> {
    store::agent_name(reader)?;
    let Some(id) = store::integer(id) else {
        return bad("Choose a message.");
    };
    let mut db = db::write()?;
    let tx = db::immediate(&mut db)?;
    let key = thread_keys(&tx)?.remove(&id).ok_or_else(|| db::Error::Missing(format!("message {id} is not on the board")))?;
    if starred {
        tx.execute("INSERT OR IGNORE INTO stars (reader, thread, created) VALUES (?, ?, ?)", params![reader, key, db::now()])?;
    } else {
        tx.execute("DELETE FROM stars WHERE reader=? AND thread=?", params![reader, key])?;
    }
    tx.commit()?;
    Ok(key)
}

/// Whether the reader starred the thread with this key.
pub fn is_starred(db: &Connection, reader: &str, key: &str) -> Result<bool> {
    let found = db.query_row("SELECT 1 FROM stars WHERE reader=? AND thread=?", params![reader, key], |_| Ok(()));
    Ok(found.optional()?.is_some())
}

/// Mark a conversation read up to `through` (the newest message the reader saw in it; its newest message when
/// omitted), mark everything read, or follow or unfollow a thread. Marks only move forward. Returns the thread's key.
pub fn mark_read(reader: &str, id: &serde_json::Value, through: &serde_json::Value, everything: bool,
                 follow: Option<bool>) -> Result<String> {
    store::agent_name(reader)?;
    let mut db = db::write()?;
    let tx = db::immediate(&mut db)?;
    let newest: i64 = tx.query_row("SELECT coalesce(max(id), 0) FROM messages", [], |r| r.get(0))?;
    let upsert = "INSERT INTO reads (reader, thread, last_read) VALUES (?, ?, ?) \
                  ON CONFLICT (reader, thread) DO UPDATE SET last_read=max(last_read, excluded.last_read)";
    if everything {
        tx.execute(upsert, params![reader, "*", newest])?;
        tx.commit()?;
        return Ok("*".into());
    }
    let Some(id) = store::integer(id) else {
        return bad("Choose a message.");
    };
    let through = match through {
        serde_json::Value::Null => None,
        value => match store::integer(value) {
            Some(n) => Some(n),
            None => return bad("through must be a message id"),
        },
    };
    let (roots, replies) = store::thread_rows(&tx, id)?;
    let key = group_key(roots[0].id, roots[0].dedup.as_deref());
    let last = roots.iter().chain(&replies).map(|row| row.id).max().unwrap();
    let mark = through.map_or(last, |through| through.min(last).max(0));
    tx.execute(upsert, params![reader, key, mark])?;
    if let Some(follow) = follow {
        // Unfollowing remembers where: only a later @mention brings the thread back.
        tx.execute(
            "UPDATE reads SET unfollowed=? WHERE reader=? AND thread=?",
            params![if follow { None } else { Some(last) }, reader, key],
        )?;
    }
    tx.commit()?;
    Ok(key)
}
