//! Board attachments: files saved on this machine and named in a message by a plain trailer of absolute paths, which
//! agents reading the board with `atelier board read` open directly (board_files.py writes the same trailer).
use std::path::PathBuf;
use std::sync::LazyLock;

use percent_encoding::{AsciiSet, NON_ALPHANUMERIC, percent_decode_str, utf8_percent_encode};
use rand::RngCore;
use regex::Regex;
use serde_json::{Value, json};

use crate::api::{Attachment, File};
use crate::db::{self, Error, Result, bad};

pub const ATTACHMENT_LIMIT: u64 = 512 * 1024 * 1024;
pub const TRAILER: &str = "Attachments (files on this machine):";
/// Only these types display inline; everything else downloads, so an uploaded page or SVG can never run here.
pub const INLINE_TYPES: &[&str] = &[
    "image/png", "image/jpeg", "image/gif", "image/webp", "image/heic", "image/heif", "image/avif", "video/mp4",
    "video/quicktime", "video/webm", "audio/mpeg", "audio/mp4", "audio/aac", "audio/x-m4a", "audio/wav",
    "application/pdf",
];
/// Markdown and text attachments up to this size open in the board's reader; larger ones download.
const READABLE_LIMIT: u64 = 512 * 1024;
pub const MARKDOWN_SUFFIXES: &[&str] = &[".md", ".markdown"];
const TEXT_SUFFIXES: &[&str] = &[".md", ".markdown", ".txt", ".log"];

static ID: LazyLock<Regex> = LazyLock::new(|| Regex::new(r"^[0-9a-f]{24}$").unwrap());
static IN_TRAILER: LazyLock<Regex> = LazyLock::new(|| Regex::new(r"/board-attachments/([0-9a-f]{24})/[^/]+$").unwrap());
static UNSAFE_NAME: LazyLock<Regex> = LazyLock::new(|| Regex::new(r"[^\w.\- ()]+").unwrap());
static MIME: LazyLock<Regex> = LazyLock::new(|| Regex::new(r"^[\w.+-]+/[\w.+-]+$").unwrap());

/// What Python's urllib.parse.quote leaves alone: letters, digits, `_.-~` and `/`.
const QUOTE: &AsciiSet = &NON_ALPHANUMERIC.remove(b'_').remove(b'.').remove(b'-').remove(b'~').remove(b'/');

pub fn quote(text: &str) -> String {
    utf8_percent_encode(text, QUOTE).to_string()
}

pub fn folder() -> PathBuf {
    db::root().join("board-attachments")
}

/// A stored attachment.
#[derive(Clone, Debug)]
pub struct Item {
    pub id: String,
    pub name: String,
    pub mime: String,
    pub size: u64,
    pub path: PathBuf,
    pub width: Option<u32>,
    pub height: Option<u32>,
}

impl Item {
    pub fn url(&self) -> String {
        format!("/api/attachment/{}/{}", self.id, quote(&self.name))
    }

    pub fn readable(&self) -> bool {
        let name = self.name.to_lowercase();
        self.size <= READABLE_LIMIT && TEXT_SUFFIXES.iter().any(|suffix| name.ends_with(suffix))
    }

    pub fn inline(&self) -> bool {
        INLINE_TYPES.contains(&self.mime.as_str())
    }
}

pub fn read_json(path: &std::path::Path) -> Option<Value> {
    serde_json::from_slice(&std::fs::read(path).ok()?).ok()
}

fn dimension_value(value: &Value) -> Option<u32> {
    value.as_u64().and_then(|n| u32::try_from(n).ok())
}

pub fn attachment(id: &str) -> Option<Item> {
    if !ID.is_match(id) {
        return None;
    }
    let meta = read_json(&folder().join(id).join(".meta.json"))?;
    let name = meta.get("name")?.as_str()?.to_owned();
    let path = folder().join(id).join(&name);
    if name.is_empty() || name.contains('/') || !path.is_file() {
        return None;
    }
    Some(Item {
        id: id.to_owned(),
        mime: meta.get("mime")?.as_str()?.to_owned(),
        size: meta.get("size")?.as_u64()?,
        width: meta.get("width").and_then(dimension_value),
        height: meta.get("height").and_then(dimension_value),
        name,
        path,
    })
}

/// A safe file name from what the uploader sent: its last path part, without characters that mean anything.
pub fn file_name(name: &str) -> String {
    let name = percent_decode_str(name).decode_utf8_lossy().replace('\\', "/");
    let last = name.rsplit('/').next().unwrap_or("");
    let cleaned = UNSAFE_NAME.replace_all(last, "_");
    let trimmed: String = cleaned.trim_matches([' ', '.']).chars().take(120).collect();
    if trimmed.is_empty() { "file".into() } else { trimmed }
}

pub fn size_text(size: u64) -> String {
    if size < 1024 {
        return format!("{size} bytes");
    }
    let mut value = size as f64 / 1024.0;
    for unit in ["KB", "MB"] {
        if value < 1024.0 {
            return format!("{value:.1} {unit}");
        }
        value /= 1024.0;
    }
    format!("{value:.1} GB")
}

fn dimension(value: Option<&str>) -> Option<u32> {
    let number: i64 = value?.trim().parse().ok()?;
    (1..=100_000).contains(&number).then_some(number as u32)
}

/// Where an upload is being written; dropping it unfinished removes the folder.
pub struct Upload {
    pub id: String,
    pub name: String,
    pub mime: String,
    pub length: u64,
    folder: PathBuf,
    pub file: Option<std::fs::File>,
    done: bool,
}

impl Upload {
    /// Start one upload. Nothing is posted until a message refers to it.
    pub fn start(length: u64, name: &str, mime: &str) -> Result<Upload> {
        if !(1..=ATTACHMENT_LIMIT).contains(&length) {
            return bad(format!("Files can be up to {} MB.", ATTACHMENT_LIMIT / 1024 / 1024));
        }
        let mime = if MIME.is_match(mime) { mime.to_owned() } else { "application/octet-stream".into() };
        let mut bytes = [0u8; 12];
        rand::thread_rng().fill_bytes(&mut bytes);
        let id: String = bytes.iter().map(|b| format!("{b:02x}")).collect();
        let place = folder().join(&id);
        std::fs::create_dir_all(folder())?;
        std::fs::create_dir(&place)?;
        let file = std::fs::File::create(place.join(".partial"));
        let mut upload =
            Upload { id, name: file_name(name), mime, length, folder: place, file: None, done: false };
        upload.file = Some(file?);
        Ok(upload)
    }

    /// The whole file has arrived: keep it, with the pixel size a photo or video was said to have.
    pub fn finish(mut self, width: Option<&str>, height: Option<&str>) -> Result<crate::api::Upload> {
        drop(self.file.take());
        std::fs::rename(self.folder.join(".partial"), self.folder.join(&self.name))?;
        let (mut width, mut height) = (dimension(width), dimension(height));
        if width.is_none() || height.is_none() {
            (width, height) = (None, None);
        }
        let meta = json!({"name": self.name, "mime": self.mime, "size": self.length, "width": width, "height": height});
        std::fs::write(self.folder.join(".meta.json"), meta.to_string())?;
        self.done = true;
        Ok(crate::api::Upload {
            id: self.id.clone(),
            name: self.name.clone(),
            mime: self.mime.clone(),
            size: self.length,
            width,
            height,
        })
    }
}

impl Drop for Upload {
    fn drop(&mut self) {
        if !self.done {
            drop(self.file.take());
            let _ = std::fs::remove_dir_all(&self.folder);
        }
    }
}

/// The body with its attachments' trailer, from the upload ids a web send names.
pub fn with_attachments(body: &Value, ids: &Value) -> Result<Value> {
    let falsy = match ids {
        Value::Null => true,
        Value::Bool(b) => !b,
        Value::Number(n) => n.as_f64() == Some(0.0),
        Value::String(s) => s.is_empty(),
        Value::Array(a) => a.is_empty(),
        Value::Object(o) => o.is_empty(),
    };
    if falsy {
        return Ok(body.clone());
    }
    let Value::Array(ids) = ids else {
        return bad("Attach at most 10 different files to one message.");
    };
    let texts: std::collections::HashSet<String> =
        ids.iter().map(|id| id.as_str().map(str::to_owned).unwrap_or_else(|| id.to_string())).collect();
    if ids.len() > 10 || texts.len() != ids.len() {
        return bad("Attach at most 10 different files to one message.");
    }
    let mut lines = Vec::new();
    for id in ids {
        let Some(item) = id.as_str().and_then(attachment) else {
            return bad("An attachment is no longer available. Remove it and add it again.");
        };
        lines.push(format!("- {} ({}, {}): {}", item.name, item.mime, size_text(item.size), item.path.display()));
    }
    let Value::String(body) = body else {
        return bad("A message must be text.");
    };
    let lead = if body.trim().is_empty() { String::new() } else { body.trim_end().to_owned() + "\n\n" };
    Ok(Value::String(format!("{lead}{TRAILER}\n{}", lines.join("\n"))))
}

/// Where the trailer starts and its lines, when the body ends with one.
fn trailer(body: &str) -> Option<(usize, &str)> {
    // The trailer is the body's last part: its heading, at the start or after a blank line, then only "- " lines.
    let mut search = body.len();
    while let Some(at) = body[..search].rfind(TRAILER) {
        search = at;
        if !(at == 0 || body[..at].ends_with("\n\n")) {
            continue;
        }
        let rest = &body[at + TRAILER.len()..];
        let Some(lines) = rest.strip_prefix('\n') else { continue };
        if lines.is_empty() {
            continue;
        }
        let trimmed = lines.strip_suffix('\n').unwrap_or(lines);
        if trimmed.split('\n').all(|line| line.starts_with("- ")) && !trimmed.is_empty() {
            let start = if at == 0 { 0 } else { at - 2 };
            return Some((start, trimmed));
        }
    }
    None
}

/// The message text and the attachments its trailer names. Unknown or removed files are listed as missing.
pub fn split_attachments(body: &str) -> (&str, Vec<Attachment>) {
    let Some((start, lines)) = trailer(body) else {
        return (body, Vec::new());
    };
    let files = lines
        .split('\n')
        .map(|line| {
            let item = IN_TRAILER.captures(line).and_then(|found| attachment(&found[1]));
            match item {
                Some(item) => Attachment::Present(File {
                    url: item.url(),
                    readable: item.readable(),
                    id: item.id,
                    name: item.name,
                    mime: item.mime,
                    size: item.size,
                    width: item.width,
                    height: item.height,
                }),
                None => Attachment::Missing {
                    missing: true,
                    name: line[2..].split(" (").next().unwrap_or("").to_owned(),
                },
            }
        })
        .collect();
    (&body[..start], files)
}

impl From<Error> for std::io::Error {
    fn from(error: Error) -> Self {
        std::io::Error::other(format!("{error:?}"))
    }
}
