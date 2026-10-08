//! The shared SQLite mailbox (`agent-board.sqlite3` in the board's cache folder), which the agents' `atelier board`
//! command writes too. Its schema is board_store.database()'s; both sides create what is missing, never more.
use std::path::PathBuf;
use std::sync::OnceLock;
use std::time::{Duration, SystemTime, UNIX_EPOCH};

use rusqlite::{Connection, OpenFlags, Transaction, TransactionBehavior};

use crate::api::Row;

/// What went wrong, and how the HTTP layer reports it.
#[derive(Debug)]
pub enum Error {
    /// The request is wrong: 400 with this sentence.
    Bad(String),
    /// What it names is not on the board.
    Missing(String),
    /// The database is busy or broken: 503.
    Db(rusqlite::Error),
    /// A file could not be read or written: 503.
    Io(std::io::Error),
}

impl From<rusqlite::Error> for Error {
    fn from(error: rusqlite::Error) -> Self {
        Error::Db(error)
    }
}

impl From<std::io::Error> for Error {
    fn from(error: std::io::Error) -> Self {
        Error::Io(error)
    }
}

pub type Result<T> = std::result::Result<T, Error>;

pub fn bad<T>(message: impl Into<String>) -> Result<T> {
    Err(Error::Bad(message.into()))
}

static ROOT: OnceLock<PathBuf> = OnceLock::new();

/// The board's folder: $ATELIER_CACHE, else ~/.cache/atelier, as atelier.paths.cache_dir() has it.
pub fn root() -> &'static PathBuf {
    ROOT.get_or_init(|| {
        let path = std::env::var_os("ATELIER_CACHE")
            .filter(|value| !value.is_empty())
            .map(PathBuf::from)
            .unwrap_or_else(|| home().join(".cache/atelier"));
        let _ = std::fs::create_dir_all(&path);
        path
    })
}

pub fn home() -> PathBuf {
    std::env::var_os("HOME").map(PathBuf::from).unwrap_or_else(|| PathBuf::from("/"))
}

pub fn path() -> PathBuf {
    root().join("agent-board.sqlite3")
}

pub fn now() -> f64 {
    SystemTime::now().duration_since(UNIX_EPOCH).map(|d| d.as_secs_f64()).unwrap_or(0.0)
}

/// A read-only connection: reads never take a write lock or change anything.
pub fn read() -> Result<Connection> {
    let db = Connection::open_with_flags(path(), OpenFlags::SQLITE_OPEN_READ_ONLY | OpenFlags::SQLITE_OPEN_NO_MUTEX)?;
    db.busy_timeout(Duration::from_secs(5))?;
    Ok(db)
}

pub fn write() -> Result<Connection> {
    let db = Connection::open_with_flags(
        path(),
        OpenFlags::SQLITE_OPEN_READ_WRITE | OpenFlags::SQLITE_OPEN_CREATE | OpenFlags::SQLITE_OPEN_NO_MUTEX,
    )?;
    db.busy_timeout(Duration::from_secs(10))?;
    db.execute_batch("PRAGMA foreign_keys=ON")?;
    Ok(db)
}

/// A write transaction that holds the write lock from its start, so a check and the write it guards are atomic.
pub fn immediate(db: &mut Connection) -> Result<Transaction<'_>> {
    Ok(db.transaction_with_behavior(TransactionBehavior::Immediate)?)
}

fn columns(db: &Connection, table: &str) -> Result<Vec<String>> {
    let mut statement = db.prepare(&format!("PRAGMA table_info({table})"))?;
    let names = statement.query_map([], |row| row.get::<_, String>("name"))?;
    Ok(names.collect::<rusqlite::Result<_>>()?)
}

fn add_column(db: &Connection, table: &str, column: &str, kind: &str) -> Result<()> {
    if columns(db, table)?.iter().any(|name| name == column) {
        return Ok(());
    }
    if let Err(error) = db.execute_batch(&format!("ALTER TABLE {table} ADD COLUMN {column} {kind}")) {
        // Another process may have added it first.
        if !columns(db, table)?.iter().any(|name| name == column) {
            return Err(error.into());
        }
    }
    Ok(())
}

/// The mailbox's tables, as board_store.database() creates them.
pub fn ensure_schema() -> Result<()> {
    let db = write()?;
    db.query_row("PRAGMA journal_mode=WAL", [], |_| Ok(()))?;
    db.execute_batch(
        "CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT, created REAL NOT NULL,
            sender TEXT NOT NULL, recipient TEXT NOT NULL, topic TEXT NOT NULL,
            body TEXT NOT NULL, reply_to INTEGER REFERENCES messages(id),
            dedup TEXT UNIQUE
        );
        CREATE INDEX IF NOT EXISTS messages_reply_to ON messages(reply_to);
        CREATE TABLE IF NOT EXISTS observations (name TEXT PRIMARY KEY, value TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS operator_tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT, created REAL NOT NULL, agent TEXT NOT NULL,
            message INTEGER NOT NULL REFERENCES messages(id), closed REAL, closed_by TEXT, note TEXT
        );
        CREATE TABLE IF NOT EXISTS subscribers (
            agent TEXT PRIMARY KEY, cursor INTEGER NOT NULL DEFAULT 0,
            pid INTEGER, heartbeat REAL, checkout TEXT, stop INTEGER NOT NULL DEFAULT 0,
            error TEXT
        );
        CREATE TABLE IF NOT EXISTS reads (
            reader TEXT NOT NULL, thread TEXT NOT NULL, last_read INTEGER NOT NULL DEFAULT 0, unfollowed INTEGER,
            PRIMARY KEY (reader, thread)
        );
        CREATE TABLE IF NOT EXISTS stars (
            reader TEXT NOT NULL, thread TEXT NOT NULL, created REAL NOT NULL, PRIMARY KEY (reader, thread)
        );
        INSERT OR IGNORE INTO reads (reader, thread, last_read) SELECT '*', '*', coalesce(max(id), 0) FROM messages;",
    )?;
    for (column, kind) in [
        ("supervised", "TEXT"),
        ("task", "TEXT"),
        ("removed", "INTEGER NOT NULL DEFAULT 0"),
        ("task_at", "REAL"),
        ("session", "TEXT"),
        ("session_since", "REAL"),
    ] {
        add_column(&db, "subscribers", column, kind)?;
    }
    add_column(&db, "messages", "notify", "INTEGER NOT NULL DEFAULT 0")?;
    add_column(&db, "operator_tasks", "body", "TEXT")?;
    add_column(&db, "operator_tasks", "edited", "REAL")?;
    Ok(())
}

/// A `SELECT * FROM messages` row.
pub fn message(row: &rusqlite::Row) -> rusqlite::Result<Row> {
    Ok(Row {
        id: row.get("id")?,
        created: row.get("created")?,
        sender: row.get("sender")?,
        recipient: row.get("recipient")?,
        topic: row.get("topic")?,
        body: row.get("body")?,
        reply_to: row.get("reply_to")?,
        dedup: row.get("dedup")?,
        notify: row.get("notify")?,
    })
}

pub const MESSAGE: &str = "id, created, sender, recipient, topic, body, reply_to, dedup, notify";

pub fn messages(db: &Connection, sql: &str, parameters: impl rusqlite::Params) -> Result<Vec<Row>> {
    let mut statement = db.prepare_cached(sql)?;
    let rows = statement.query_map(parameters, message)?;
    Ok(rows.collect::<rusqlite::Result<_>>()?)
}

/// `?, ?, ?` for n parameters.
pub fn marks(n: usize) -> String {
    vec!["?"; n].join(",")
}
