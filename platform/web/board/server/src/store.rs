//! The board's writes and conversation reads, as board_store.py has them: web sends (one addressed copy per agent,
//! retry-safe), threads and audiences, operator tasks, and removing an agent.
use std::collections::{BTreeSet, HashMap};
use std::sync::LazyLock;

use regex::Regex;
use rusqlite::{Connection, params};
use serde_json::Value;

use crate::api::{LastReply, OperatorTask, Row};
use crate::db::{self, Error, Result, bad};
use crate::{files, markdown};

pub const TOPICS: &[&str] = &["info", "request", "handoff", "blocked", "release", "evidence", "ack", "alert"];
pub const TASK_EDIT: &str = "task-edit:";

static AGENT: LazyLock<Regex> = LazyLock::new(|| Regex::new(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,79}$").unwrap());

pub fn agent_name(value: &str) -> Result<&str> {
    if AGENT.is_match(value) {
        Ok(value)
    } else {
        bad("agent names need 1–80 letters, digits, dots, underscores or hyphens")
    }
}

/// `web-broadcast:{uuid}:` for an addressed copy of a web broadcast.
pub fn prefix(dedup: &str) -> &str {
    &dedup[..dedup.rfind(':').map_or(0, |at| at + 1)]
}

/// Escape LIKE's wildcards, so a prefix matches only itself.
fn like(prefix: &str) -> String {
    prefix.replace('\\', "\\\\").replace('%', "\\%").replace('_', "\\_") + "%"
}

/// Every message whose dedup key starts with prefix, oldest first.
pub fn copies(db: &Connection, prefix: &str) -> Result<Vec<Row>> {
    db::messages(
        db,
        &format!("SELECT {} FROM messages WHERE dedup LIKE ? ESCAPE '\\' ORDER BY id", db::MESSAGE),
        [like(prefix)],
    )
}

/// Everyone each message reached: `["*"]` for the whole board, every addressed copy's recipient for a web broadcast
/// (each agent holds one copy, so the copy alone looks direct), or the one recipient.
pub fn audiences(db: &Connection, rows: &[Row]) -> Result<Vec<Vec<String>>> {
    let mut groups: HashMap<String, Vec<String>> = HashMap::new();
    let mut out = Vec::with_capacity(rows.len());
    for row in rows {
        match row.dedup.as_deref().filter(|dedup| dedup.starts_with("web-broadcast:")) {
            Some(dedup) => {
                let key = prefix(dedup).to_owned();
                if !groups.contains_key(&key) {
                    let mut statement = db.prepare_cached(
                        "SELECT recipient FROM messages WHERE dedup LIKE ? ESCAPE '\\' ORDER BY recipient",
                    )?;
                    let names = statement.query_map([like(&key)], |r| r.get(0))?.collect::<rusqlite::Result<_>>()?;
                    groups.insert(key.clone(), names);
                }
                out.push(groups[&key].clone());
            }
            None => out.push(vec![row.recipient.clone()]),
        }
    }
    Ok(out)
}

pub fn message(db: &Connection, id: i64) -> Result<Option<Row>> {
    let rows = db::messages(db, &format!("SELECT {} FROM messages WHERE id=?", db::MESSAGE), [id])?;
    Ok(rows.into_iter().next())
}

/// The conversation holding message_id: its root (every copy of a web send) and all replies below it, oldest first.
pub fn thread_rows(db: &Connection, message_id: i64) -> Result<(Vec<Row>, Vec<Row>)> {
    let Some(mut row) = message(db, message_id)? else {
        return Err(Error::Missing(format!("message {message_id} is not on the board")));
    };
    let mut seen = std::collections::HashSet::from([row.id]);
    while let Some(parent) = row.reply_to {
        if seen.len() >= 200 {
            break;
        }
        match message(db, parent)? {
            Some(found) if !seen.contains(&found.id) => {
                seen.insert(found.id);
                row = found;
            }
            _ => break,
        }
    }
    let dedup = row.dedup.clone().unwrap_or_default();
    let roots = if dedup.starts_with("web-broadcast:") || dedup.starts_with("web-direct:") {
        copies(db, prefix(&dedup))?
    } else {
        vec![row]
    };
    let ids: Vec<i64> = roots.iter().map(|r| r.id).collect();
    let sql = format!(
        "WITH RECURSIVE t(id) AS (SELECT id FROM messages WHERE reply_to IN ({}) \
         UNION SELECT m.id FROM messages m JOIN t ON m.reply_to=t.id) \
         SELECT {} FROM messages WHERE id IN t ORDER BY id LIMIT 500",
        db::marks(ids.len()),
        db::MESSAGE
    );
    let replies = db::messages(db, &sql, rusqlite::params_from_iter(ids))?;
    Ok((roots, replies))
}

/// The operator's open tasks, oldest first, each with its question and its thread's newest reply.
pub fn tasks(db: &Connection) -> Result<Vec<OperatorTask>> {
    let mut statement = db.prepare_cached(
        "SELECT t.id, t.created, t.agent, t.message, t.closed, t.closed_by, t.note, t.edited, \
         coalesce(t.body, m.body) AS body, m.created AS asked FROM operator_tasks t JOIN messages m ON m.id=t.message \
         WHERE t.closed IS NULL ORDER BY t.id LIMIT 200",
    )?;
    let rows = statement.query_map([], |r| {
        Ok(OperatorTask {
            id: r.get("id")?,
            created: r.get("created")?,
            agent: r.get("agent")?,
            message: r.get("message")?,
            closed: r.get("closed")?,
            closed_by: r.get("closed_by")?,
            note: r.get("note")?,
            edited: r.get("edited")?,
            body: r.get("body")?,
            body_html: String::new(),
            asked: r.get("asked")?,
            replies: 0,
            last_reply: None,
        })
    })?;
    let mut tasks = rows.collect::<rusqlite::Result<Vec<_>>>()?;
    let mut replies = db.prepare_cached(
        "WITH RECURSIVE r(id) AS (SELECT id FROM messages WHERE reply_to=? \
         UNION SELECT m.id FROM messages m JOIN r ON m.reply_to=r.id) \
         SELECT sender, body, created FROM messages WHERE id IN r AND coalesce(dedup, '') NOT LIKE ? ORDER BY id",
    )?;
    for task in &mut tasks {
        // An edit's note is the ask itself, already on the card, so it is not a reply.
        let found: Vec<LastReply> = replies
            .query_map(params![task.message, format!("{TASK_EDIT}%")], |r| {
                Ok(LastReply { sender: r.get(0)?, body: r.get(1)?, created: r.get(2)? })
            })?
            .collect::<rusqlite::Result<_>>()?;
        task.replies = found.len() as i64;
        task.last_reply = found.into_iter().last();
        task.body_html = markdown::cached(files::split_attachments(&task.body).0);
    }
    Ok(tasks)
}

/// Python's truthiness, for the few places the old server tested a JSON value that way.
pub fn truthy(value: &Value) -> bool {
    match value {
        Value::Null => false,
        Value::Bool(b) => *b,
        Value::Number(n) => n.as_f64() != Some(0.0),
        Value::String(s) => !s.is_empty(),
        Value::Array(a) => !a.is_empty(),
        Value::Object(o) => !o.is_empty(),
    }
}

/// An integer and not a boolean, as the old server's isinstance checks had it.
pub fn integer(value: &Value) -> Option<i64> {
    match value {
        Value::Number(n) => n.as_i64(),
        _ => None,
    }
}

enum To {
    Everyone,
    One(String),
    Group(Vec<String>),
}

/// Atomically address every non-stopped subscriber (addressed-only listeners included), one agent, or the agents a
/// message @mentions (one addressed copy each, shown as one message). A retry of the same request returns the
/// original copies; the same request id with different content is refused.
pub fn send_web(sender: &str, body: &Value, request_id: &Value, topic: &Value, recipient: &Value, reply_to: &Value)
    -> Result<Vec<Row>> {
    agent_name(sender)?;
    let mut to = match recipient {
        Value::Array(names) => {
            if !(1..=50).contains(&names.len()) || !names.iter().all(Value::is_string) {
                return bad("choose up to 50 registered recipients");
            }
            let mut group = BTreeSet::new();
            for name in names {
                group.insert(agent_name(name.as_str().unwrap())?.to_owned());
            }
            let group: Vec<String> = group.into_iter().collect();
            if group.len() == 1 { To::One(group[0].clone()) } else { To::Group(group) }
        }
        Value::String(name) if name == "*" => To::Everyone,
        Value::String(name) => To::One(name.clone()),
        _ => return bad("choose a registered recipient"),
    };
    if let To::One(name) = &to {
        agent_name(name)?;
    }
    let body = match body {
        Value::String(text) if !text.trim().is_empty() && text.chars().count() <= 8000 => text,
        _ => return bad("use a known topic and a nonempty message of at most 8000 characters"),
    };
    let topic = match topic.as_str() {
        Some(topic) if TOPICS.contains(&topic) => topic,
        _ => return bad("use a known topic and a nonempty message of at most 8000 characters"),
    };
    let reply_to = match reply_to {
        Value::Null => None,
        value => match integer(value) {
            Some(id) if id >= 1 => Some(id),
            _ => return bad("reply_to must be a message id"),
        },
    };
    let Some(key) = request_id.as_str().and_then(|id| uuid::Uuid::parse_str(id).ok()) else {
        return bad("broadcast request_id must be a UUID");
    };
    let key = key.hyphenated().to_string();
    // A mention group is stored as a broadcast to just those agents; `~m` lets the feed say who, not "everyone".
    let mut prefix =
        if matches!(to, To::Group(_)) { format!("web-broadcast:{key}~m:") } else { format!("web-broadcast:{key}:") };
    let direct = format!("web-direct:{key}:");
    let mut db = db::write()?;
    let tx = db::immediate(&mut db)?;
    let existing = db::messages(
        &tx,
        &format!(
            "SELECT {} FROM messages WHERE dedup LIKE ? ESCAPE '\\' OR dedup LIKE ? ESCAPE '\\' ORDER BY id",
            db::MESSAGE
        ),
        [like(&format!("web-broadcast:{key}")), like(&direct)],
    )?;
    if !existing.is_empty() {
        let first = existing[0].dedup.clone().unwrap_or_default();
        let mut names: Vec<&str> = existing.iter().map(|r| r.recipient.as_str()).collect();
        names.sort();
        let different = existing.iter().any(|r| r.sender != sender || r.body != *body || r.topic != topic
                || r.reply_to != reply_to)
            || match &to {
                To::Everyone => !first.starts_with(&prefix),
                To::Group(group) => !first.starts_with(&prefix) || names != *group,
                To::One(name) => existing.len() != 1 || first != format!("{direct}{name}"),
            };
        if different {
            return bad("this broadcast request_id already belongs to a different message");
        }
        return Ok(existing);
    }
    let registered: Vec<String> = {
        let mut statement = tx.prepare("SELECT agent FROM subscribers WHERE stop=0 AND agent!=? ORDER BY agent")?;
        statement.query_map([sender], |r| r.get(0))?.collect::<rusqlite::Result<_>>()?
    };
    let agents = match &mut to {
        To::Group(group) => {
            let missing: Vec<&str> =
                group.iter().filter(|name| !registered.contains(name)).map(String::as_str).collect();
            if !missing.is_empty() {
                return bad(format!("Not registered or retired: {}.", missing.join(", ")));
            }
            std::mem::take(group)
        }
        To::One(name) => {
            if !registered.contains(name) {
                return bad("This agent is not registered or has been retired.");
            }
            prefix = direct;
            vec![name.clone()]
        }
        To::Everyone => registered,
    };
    if agents.is_empty() {
        return bad("No agents are currently registered for broadcasts.");
    }
    if let Some(id) = reply_to {
        if message(&tx, id)?.is_none() {
            return bad("The message you are replying to no longer exists.");
        }
    }
    let created = db::now();
    for agent in &agents {
        // A bad name in the subscriber table rolls the whole send back.
        agent_name(agent)?;
        tx.execute(
            "INSERT INTO messages (created, sender, recipient, topic, body, reply_to, dedup) VALUES (?, ?, ?, ?, ?, ?, ?)",
            params![created, sender, agent, topic, body, reply_to, format!("{prefix}{agent}")],
        )?;
    }
    let rows = copies(&tx, &prefix)?;
    tx.commit()?;
    Ok(rows)
}

/// Dismiss an open operator task inside the caller's transaction: by the operator from the web board, or because its
/// agent was removed. The thread records it. False if it was already closed.
fn close_task_in(db: &Connection, task: i64, by: &str, note: &str, removed: bool) -> Result<bool> {
    let row = db.query_row("SELECT agent, closed, message FROM operator_tasks WHERE id=?", [task], |r| {
        Ok((r.get::<_, String>(0)?, r.get::<_, Option<f64>>(1)?, r.get::<_, i64>(2)?))
    });
    let (agent, closed, message) = match row {
        Ok(row) => row,
        Err(rusqlite::Error::QueryReturnedNoRows) => {
            return Err(Error::Missing(format!("operator task {task} does not exist")));
        }
        Err(error) => return Err(error.into()),
    };
    if closed.is_some() {
        return Ok(false);
    }
    let now = db::now();
    db.execute(
        "UPDATE operator_tasks SET closed=?, closed_by=?, note=? WHERE id=?",
        params![now, by, (!note.is_empty()).then_some(note), task],
    )?;
    let (sender, recipient, text) = if removed {
        ("board-watch", "operator".to_owned(), "Dismissed this operator task: its agent left the board.")
    } else {
        (by, agent, "Dismissed this operator task.")
    };
    let text = if note.is_empty() { text.to_owned() } else { format!("{text} {note}") };
    db.execute(
        "INSERT INTO messages (created, sender, recipient, topic, body, reply_to) VALUES (?, ?, ?, 'info', ?, ?)",
        params![now, sender, recipient, text, message],
    )?;
    Ok(true)
}

/// The operator dismisses a task from the Tasks page.
pub fn dismiss_task(task: i64, by: &str, note: &Value) -> Result<bool> {
    agent_name(by)?;
    let note = match note {
        Value::String(text) => text.split_whitespace().collect::<Vec<_>>().join(" "),
        value if !truthy(value) => String::new(),
        _ => return bad("the dismissal note must be text"),
    };
    if note.chars().count() > 300 {
        return bad("keep the dismissal note to at most 300 characters");
    }
    let mut db = db::write()?;
    let tx = db::immediate(&mut db)?;
    let closed = close_task_in(&tx, task, by, &note, false)?;
    tx.commit()?;
    Ok(closed)
}

/// Take an evicted agent off the board. Its listener is retired (a supervised one through launchd), so nothing more
/// queues for it, and it leaves every list. History stays, and subscribing again brings the agent back.
pub fn remove(agent: &str) -> Result<()> {
    agent_name(agent)?;
    let supervised: Option<String> = {
        let db = db::write()?;
        match db.query_row("SELECT supervised FROM subscribers WHERE agent=?", [agent], |r| r.get(0)) {
            Ok(value) => value,
            Err(rusqlite::Error::QueryReturnedNoRows) => {
                return Err(Error::Missing(format!("{agent} is not registered on the board")));
            }
            Err(error) => return Err(error.into()),
        }
    };
    if supervised.as_deref().is_some_and(|label| !label.is_empty()) {
        retire(agent)?;
    }
    let mut db = db::write()?;
    let tx = db::immediate(&mut db)?;
    tx.execute("UPDATE subscribers SET stop=1, removed=1 WHERE agent=?", [agent])?;
    // Nobody is left to unblock: its tasks leave the operator's list, in the same transaction.
    let open: Vec<i64> = {
        let mut statement = tx.prepare("SELECT id FROM operator_tasks WHERE agent=? AND closed IS NULL")?;
        statement.query_map([agent], |r| r.get(0))?.collect::<rusqlite::Result<_>>()?
    };
    for task in open {
        close_task_in(&tx, task, agent, "", true)?;
    }
    tx.commit()?;
    Ok(())
}

/// Retire a supervised listener as `atelier board retire` does: stop its launchd job so it cannot come back.
fn retire(agent: &str) -> Result<()> {
    let label = format!("com.atelier.board.{agent}");
    // Tests point this at a stand-in; the board never runs anything else.
    let launchctl = std::env::var("ATELIER_BOARD_LAUNCHCTL").unwrap_or_else(|_| "launchctl".into());
    let target = format!("gui/{}/{label}", unsafe { libc::getuid() });
    let run = |argv: &[&str]| {
        std::process::Command::new(&launchctl)
            .args(argv)
            .stdin(std::process::Stdio::null())
            .output()
            .map(|output| output.status.success())
    };
    if !run(&["bootout", &target])? && run(&["print", &target])? {
        return bad("Listener service could not be retired");
    }
    let plist = db::home().join("Library/LaunchAgents").join(format!("{label}.plist"));
    match std::fs::remove_file(plist) {
        Err(error) if error.kind() != std::io::ErrorKind::NotFound => return Err(error.into()),
        _ => {}
    }
    let db = db::write()?;
    db.execute("UPDATE subscribers SET supervised=NULL,stop=1,pid=NULL WHERE agent=?", [agent])?;
    Ok(())
}
