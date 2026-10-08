//! The board's read-only views: the feed snapshot, a whole thread, and the inbox's Threads and Activity. Reads never
//! advance subscriber cursors or acquire render locks.
use std::collections::{BTreeMap, HashMap, HashSet};
use std::path::Path;
use std::sync::LazyLock;

use regex::Regex;
use rusqlite::{Connection, params_from_iter};
use serde_json::Value;

use crate::api::{Agent, Message, Resources, Row, Session, State, Thread};
use crate::db::{self, Result, bad};
use crate::{files, floor, inbox, markdown, store};

static SESSION_URL: LazyLock<Regex> = LazyLock::new(|| Regex::new(r"^https://claude\.ai/code/session_[A-Za-z0-9]+$").unwrap());

/// A query string's parameters as Python's parse_qs reads them: the first value of each, blank values left out.
pub struct Query(HashMap<String, String>);

impl Query {
    pub fn parse(query: Option<&str>) -> Query {
        let mut values = HashMap::new();
        for (key, value) in url::form_urlencoded::parse(query.unwrap_or("").as_bytes()) {
            if !value.is_empty() {
                values.entry(key.into_owned()).or_insert_with(|| value.into_owned());
            }
        }
        Query(values)
    }

    pub fn text(&self, name: &str) -> &str {
        self.0.get(name).map_or("", String::as_str)
    }

    pub fn number(&self, name: &str, default: i64) -> Result<i64> {
        match self.0.get(name) {
            None => Ok(default),
            Some(text) => text.trim().parse().or_else(|_| bad(format!("{name} must be a whole number"))),
        }
    }

    /// A number in 1..=high, with this default.
    pub fn bounded(&self, name: &str, default: i64, high: i64) -> Result<usize> {
        let value = self.number(name, default)?;
        if !(1..=high).contains(&value) {
            return bad(format!("{name} must be between 1 and {high}"));
        }
        Ok(value as usize)
    }
}

fn ack_ids(db: &Connection, within: Option<&[i64]>) -> Result<HashSet<i64>> {
    let base = "SELECT reply.reply_to FROM messages reply JOIN messages original ON original.id=reply.reply_to \
                WHERE reply.topic='ack' AND reply.sender=original.recipient";
    let mut found = HashSet::new();
    match within {
        None => {
            let mut statement = db.prepare_cached(base)?;
            for id in statement.query_map([], |r| r.get(0))? {
                found.insert(id?);
            }
        }
        Some(ids) => {
            for chunk in ids.chunks(500) {
                let sql = format!("{base} AND reply.reply_to IN ({})", db::marks(chunk.len()));
                let mut statement = db.prepare(&sql)?;
                for id in statement.query_map(params_from_iter(chunk), |r| r.get(0))? {
                    found.insert(id?);
                }
            }
        }
    }
    Ok(found)
}

/// Messages as the board shows them: rendered, with attachments, audience and acknowledgement.
fn decorate(db: &Connection, rows: Vec<Row>, acks: &HashSet<i64>) -> Result<Vec<Message>> {
    let audiences = store::audiences(db, &rows)?;
    Ok(rows
        .into_iter()
        .zip(audiences)
        .map(|(row, audience)| {
            let (text, attachments) = files::split_attachments(&row.body);
            Message {
                body_html: markdown::cached(text),
                attachments,
                acknowledged: acks.contains(&row.id),
                audience,
                row,
            }
        })
        .collect())
}

/// The feed page and everything around it, as `GET /api/state` returns it.
pub fn snapshot(query: &Query, remote_status: Option<&Path>, sender: &str, csrf: &str) -> Result<State> {
    let before = query.number("before", 0)?;
    let limit = query.number("limit", 150)?;
    let log = query.number("log", 30)?;
    if before < 0 || !(1..=300).contains(&limit) || !(1..=5000).contains(&log) {
        return bad("invalid history page");
    }
    let mut conditions: Vec<&str> = Vec::new();
    let mut parameters: Vec<Value> = Vec::new();
    if before != 0 {
        conditions.push("id<?");
        parameters.push(before.into());
    }
    let topic = query.text("topic");
    if !topic.is_empty() {
        if !store::TOPICS.contains(&topic) {
            return bad("unknown topic");
        }
        conditions.push("topic=?");
        parameters.push(topic.into());
    }
    let (agent, direct) = (query.text("agent"), query.text("dm"));
    if !direct.is_empty() {
        // A direct conversation: only messages between this agent and the board's sender, never broadcast copies.
        store::agent_name(direct)?;
        conditions.push(
            "((sender=? AND recipient=?) OR (sender=? AND recipient=?)) \
             AND (dedup IS NULL OR dedup NOT LIKE 'web-broadcast:%')",
        );
        parameters.extend([direct, sender, sender, direct].map(Value::from));
    } else if !agent.is_empty() {
        store::agent_name(agent)?;
        conditions.push("(sender=? OR recipient=? OR recipient='*')");
        parameters.extend([agent, agent].map(Value::from));
    }
    let search = query.text("q").trim();
    if search.chars().count() > 200 {
        return bad("search is too long");
    }
    if !search.is_empty() {
        conditions.push(
            "(body LIKE ? ESCAPE '\\' OR sender LIKE ? ESCAPE '\\' OR recipient LIKE ? ESCAPE '\\')",
        );
        let pattern = format!("%{}%", search.replace('\\', "\\\\").replace('%', "\\%").replace('_', "\\_"));
        parameters.extend([pattern.clone(), pattern.clone(), pattern].map(Value::from));
    }
    let filter = if conditions.is_empty() { String::new() } else { format!(" WHERE {}", conditions.join(" AND ")) };
    parameters.push((limit + 1).into());
    let now = db::now();
    let db = db::read()?;
    let rows = db::messages(
        &db,
        &format!("SELECT {} FROM messages{filter} ORDER BY id DESC LIMIT ?", db::MESSAGE),
        params_from_iter(parameters.iter().map(sql_value)),
    )?;
    let has_more = rows.len() as i64 > limit;
    let page = &rows[..rows.len().min(limit as usize)];
    let mut agents = Vec::new();
    {
        let mut statement = db.prepare_cached(
            "SELECT agent, cursor, pid, heartbeat, checkout, stop, supervised, error, task, task_at, session, \
             session_since FROM subscribers WHERE removed=0 ORDER BY agent",
        )?;
        let mut pending = db.prepare_cached("SELECT count(*) FROM messages WHERE recipient=? AND id>? AND sender!=?")?;
        let mut last = db.prepare_cached("SELECT max(id) FROM messages WHERE sender=? AND recipient=?")?;
        let found = statement.query_map([], |r| {
            Ok((
                r.get::<_, String>("agent")?,
                r.get::<_, i64>("cursor")?,
                r.get::<_, Option<i64>>("pid")?,
                r.get::<_, Option<f64>>("heartbeat")?,
                r.get::<_, Option<String>>("checkout")?,
                r.get::<_, i64>("stop")?,
                r.get::<_, Option<String>>("supervised")?,
                r.get::<_, Option<String>>("error")?,
                r.get::<_, Option<String>>("task")?,
                r.get::<_, Option<f64>>("task_at")?,
                r.get::<_, Option<String>>("session")?,
                r.get::<_, Option<f64>>("session_since")?,
            ))
        })?;
        for item in found {
            let (name, cursor, pid, heartbeat, checkout, stop, supervised, error, task, task_at, session, since) = item?;
            let age = now - heartbeat.unwrap_or(0.0);
            agents.push(Agent {
                listening: pid.is_some_and(|pid| pid != 0) && stop == 0 && (0.0..90.0).contains(&age),
                pending: pending.query_row(rusqlite::params![name, cursor, name], |r| r.get(0))?,
                last_to_me: last.query_row([&name, sender], |r| r.get::<_, Option<i64>>(0))?.unwrap_or(0),
                checkout: checkout.filter(|c| !c.is_empty()).map(|c| floor::folder_name(&c)),
                supervised: supervised.is_some_and(|s| !s.is_empty()),
                // Transport errors are generated diagnostics, never shown in full.
                delivery_error: error.is_some_and(|e| !e.is_empty()),
                engaged: false,
                unread: 0,
                agent: name,
                cursor,
                pid,
                heartbeat,
                stop,
                task,
                task_at,
                session,
                session_since: since,
            });
        }
    }
    let total: i64 = db.query_row("SELECT count(*) FROM messages", [], |r| r.get(0))?;
    // The operator's open tasks: what agents are blocked on, oldest first, answered from the Tasks page.
    let tasks = store::tasks(&db)?;
    // Fetch complete fanouts even when a history or filter boundary cuts through one.
    let mut copies: BTreeMap<i64, Row> = page.iter().map(|row| (row.id, row.clone())).collect();
    let prefixes: HashSet<&str> = page
        .iter()
        .filter_map(|row| row.dedup.as_deref())
        .filter(|dedup| dedup.starts_with("web-broadcast:"))
        .map(store::prefix)
        .collect();
    for prefix in prefixes {
        for row in store::copies(&db, prefix)? {
            copies.insert(row.id, row);
        }
    }
    let acks = ack_ids(&db, None)?;
    let (summary, direct) = inbox::summary(&db, sender)?;
    let mut schedule = floor::sections(&floor::board_text());
    let holders = floor::holders();
    let telemetry = files::read_json(&db::root().join("render-supervisor/latest.json")).unwrap_or(Value::Null);
    let mut sessions = Vec::new();
    if let Some(path) = remote_status {
        let remote = files::read_json(path).unwrap_or(Value::Null);
        if let Some(Value::Object(items)) = remote.get("sessions") {
            for (label, item) in items {
                let url = item.get("url").and_then(Value::as_str).unwrap_or("");
                if !SESSION_URL.is_match(url) {
                    continue;
                }
                let checked = item.get("checked_at").and_then(Value::as_f64).unwrap_or(0.0);
                sessions.push(Session {
                    name: item.get("name").cloned().unwrap_or_else(|| label.clone().into()),
                    url: url.to_owned(),
                    health: item.get("health").cloned().unwrap_or(Value::Null),
                    connection: item.get("connection").cloned().unwrap_or(Value::Null),
                    fresh: (0.0..120.0).contains(&(now - checked)),
                });
            }
        }
    }
    let engaged = floor::engaged(
        &schedule,
        &holders,
        agents.iter().map(|a| (a.agent.as_str(), a.checkout.as_deref())).collect::<Vec<_>>(),
    );
    for agent in &mut agents {
        agent.engaged = engaged.contains(&agent.agent);
        agent.unread = direct.get(&agent.agent).copied().unwrap_or(0);
    }
    let (log_text, log_total) = floor::recent_log(schedule.get("Log").map_or("", String::as_str), log as usize);
    schedule.insert("Log".into(), log_text);
    let messages = decorate(&db, copies.into_values().rev().collect(), &acks)?;
    let reported = telemetry.get("time").and_then(Value::as_f64).unwrap_or(0.0);
    Ok(State {
        time: now,
        messages,
        has_more,
        agents,
        total,
        tasks,
        schedule,
        log_total,
        inbox: summary,
        holders,
        sessions,
        resources: Resources {
            fresh: (0.0..120.0).contains(&(now - reported)),
            cpu: telemetry.get("cpu_busy_percent").and_then(Value::as_f64),
            available_gib: telemetry.get("memory").and_then(|m| m.get("available_gib")).and_then(Value::as_f64),
        },
        csrf: csrf.to_owned(),
        sender: sender.to_owned(),
    })
}

fn sql_value(value: &Value) -> rusqlite::types::Value {
    match value {
        Value::Number(n) => rusqlite::types::Value::Integer(n.as_i64().unwrap_or(0)),
        Value::String(s) => rusqlite::types::Value::Text(s.clone()),
        _ => rusqlite::types::Value::Null,
    }
}

/// A whole conversation: the root (every copy of a web send) and all replies beneath it, oldest first.
pub fn thread(id: i64, reader: &str) -> Result<Thread> {
    let db = db::read()?;
    let (roots, replies) = store::thread_rows(&db, id)?;
    let ids: Vec<i64> = roots.iter().chain(&replies).map(|row| row.id).collect();
    let acks = ack_ids(&db, Some(&ids))?;
    let key = inbox::group_key(roots[0].id, roots[0].dedup.as_deref());
    let starred = inbox::is_starred(&db, reader, &key)?;
    Ok(Thread { root: decorate(&db, roots, &acks)?, replies: decorate(&db, replies, &acks)?, key, starred })
}
