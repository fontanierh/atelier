//! The render floor as the board shows it: the render board's human-maintained scheduling sections, the live render
//! lock holders (validated like atelier.safety.render_lock.read_holder), and who has render work in flight.
use std::collections::{BTreeMap, HashSet};
use std::path::{Path, PathBuf};
use std::sync::LazyLock;

use regex::Regex;
use serde_json::Value;

use crate::api::{Holder, Holders};
use crate::db;

static TELEMETRY: LazyLock<Regex> =
    LazyLock::new(|| Regex::new(r"(?s)<!-- atelier-coordinator:start -->.*?<!-- atelier-coordinator:end -->").unwrap());
static HEADING: LazyLock<Regex> = LazyLock::new(|| Regex::new(r"^## (Holding|Waiting|Handoffs|Log)").unwrap());
static ENTRY: LazyLock<Regex> = LazyLock::new(|| Regex::new(r"^\s*[-*]\s").unwrap());
/// A Holding or Waiting line starts with its timestamp and then the agent it belongs to.
static SCHEDULED: LazyLock<Regex> = LazyLock::new(|| {
    Regex::new(r"(?m)^\s*-\s+\d{4}-\d\d-\d\d[ T]\d\d:\d\d(?::\d\d)?(?:\s+[A-Z]{2,5})?\s+([A-Za-z0-9][\w.-]*)").unwrap()
});

/// Where each line starting `## ` begins.
fn heading_starts(text: &str) -> Vec<usize> {
    let mut starts = Vec::new();
    let mut at = 0;
    for line in text.split_inclusive('\n') {
        if line.starts_with("## ") {
            starts.push(at);
        }
        at += line.len();
    }
    starts
}

/// The Holding, Waiting, Handoffs and Log sections: each runs from its heading to the next `## ` heading.
pub fn sections(text: &str) -> BTreeMap<String, String> {
    let text = TELEMETRY.replace_all(text, "");
    let starts = heading_starts(&text);
    let mut out = BTreeMap::new();
    for &start in &starts {
        let Some(found) = HEADING.find(&text[start..]) else { continue };
        let name = &found.as_str()[3..];
        // The heading's name is followed only by whitespace up to the line's end; the section starts after the last
        // line break in that whitespace.
        let after = start + found.end();
        let space = text[after..].len() - text[after..].trim_start().len();
        let Some(newline) = text[after..after + space].rfind('\n') else { continue };
        let body_start = after + newline + 1;
        let end = starts.iter().copied().find(|&next| next >= body_start).unwrap_or(text.len());
        out.insert(name.to_owned(), text[body_start..end].trim().to_owned());
    }
    out
}

/// The newest `count` entries of the render board's Log (newest last, as written) and how many there are.
pub fn recent_log(text: &str, count: usize) -> (String, i64) {
    let mut entries: Vec<String> = Vec::new();
    for line in text.lines() {
        if line.trim().is_empty() {
            continue;
        }
        if ENTRY.is_match(line) || entries.is_empty() {
            entries.push(line.to_owned());
        } else {
            let last = entries.last_mut().unwrap();
            last.push('\n');
            last.push_str(line);
        }
    }
    let total = entries.len();
    (entries[total.saturating_sub(count)..].join("\n"), total as i64)
}

/// When a process started, as the kernel records it (rusage_info_v2's ri_proc_start_abstime), or None if it is gone.
pub fn process_start(pid: i64) -> Option<u64> {
    let pid = i32::try_from(pid).ok()?;
    // rusage_info_v2: a 16-byte UUID, then 18 counters; the start time is the ninth.
    let mut buffer = [0u64; 2 + 18 + 8];
    let result = unsafe { proc_pid_rusage(pid, 2, buffer.as_mut_ptr().cast()) };
    (result == 0).then_some(buffer[2 + 8])
}

unsafe extern "C" {
    fn proc_pid_rusage(pid: i32, flavor: i32, buffer: *mut libc::c_void) -> i32;
}

/// The lock files: $ATELIER_RENDER_LOCK (else ~/.cache/atelier/render.lock) and render.small.lock beside it.
fn lock_paths() -> (PathBuf, PathBuf) {
    let big = std::env::var_os("ATELIER_RENDER_LOCK")
        .filter(|value| !value.is_empty())
        .map(PathBuf::from)
        .unwrap_or_else(|| db::home().join(".cache/atelier/render.lock"));
    let stem = big.file_stem().map(|s| s.to_string_lossy().into_owned()).unwrap_or_default();
    let suffix = big.extension().map(|s| format!(".{}", s.to_string_lossy())).unwrap_or_default();
    let small = big.with_file_name(format!("{stem}.small{suffix}"));
    (big, small)
}

/// Whoever last wrote the lock file, if that process is still the one it claims to be.
fn read_holder(path: &Path) -> Option<serde_json::Map<String, Value>> {
    let text = std::fs::read_to_string(path).ok()?;
    let record: Value = serde_json::from_str(if text.is_empty() { "{}" } else { &text }).ok()?;
    let Value::Object(record) = record else { return None };
    let pid = record.get("pid").and_then(Value::as_i64).filter(|pid| *pid > 1)?;
    if matches!(record.get("pid"), Some(Value::Bool(_))) {
        return None;
    }
    // A record without a start time (older code) is taken at its word, as render_lock does.
    match record.get("started") {
        None | Some(Value::Null) => {}
        Some(started) if started.as_u64().is_some_and(|started| process_start(pid) == Some(started)) => {}
        Some(_) => return None,
    }
    Some(record)
}

fn name_of(path: &str) -> String {
    Path::new(path).file_name().map(|name| name.to_string_lossy().into_owned()).unwrap_or_default()
}

/// The checkout folder name in a path, as Path(...).name gives it.
pub fn folder_name(path: &str) -> String {
    name_of(path)
}

pub fn holders() -> Holders {
    let (big, small) = lock_paths();
    let holder = |path: &Path| {
        let record = read_holder(path)?;
        let text = |key: &str| record.get(key).and_then(Value::as_str).filter(|s| !s.is_empty());
        Some(Holder {
            purpose: record.get("purpose").cloned().unwrap_or_else(|| "Render job".into()),
            kind: record.get("kind").cloned().unwrap_or_else(|| "job".into()),
            checkout: name_of(text("repo").or_else(|| text("checkout")).unwrap_or("")),
            time: record.get("time").cloned().unwrap_or(Value::Null),
        })
    };
    Holders { big: holder(&big), small: holder(&small) }
}

/// The render board's text, if there is one.
pub fn board_text() -> String {
    std::fs::read_to_string(db::root().join("render-board.md")).unwrap_or_default()
}

/// Agents with render work in flight, which waits on a background job with the session idle: those named on a
/// Holding or Waiting line of the render board, or holding a live render lock from their checkout.
pub fn engaged<'a>(sections: &BTreeMap<String, String>, holders: &Holders,
                   checkouts: impl IntoIterator<Item = (&'a str, Option<&'a str>)>) -> HashSet<String> {
    let mut named: HashSet<String> = HashSet::new();
    for part in ["Holding", "Waiting"] {
        if let Some(text) = sections.get(part) {
            named.extend(SCHEDULED.captures_iter(text).map(|found| found[1].to_owned()));
        }
    }
    let locked: HashSet<&str> =
        [&holders.big, &holders.small].into_iter().flatten().map(|h| h.checkout.as_str()).filter(|c| !c.is_empty()).collect();
    for (agent, checkout) in checkouts {
        if checkout.is_some_and(|checkout| !checkout.is_empty() && locked.contains(checkout)) {
            named.insert(agent.to_owned());
        }
    }
    named
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn sections_run_to_the_next_heading() {
        let found = sections("## Holding\nNone\n## Waiting\n- review\n## Notes\nx\n## Log\nheader\n- a\n");
        assert_eq!(found["Holding"], "None");
        assert_eq!(found["Waiting"], "- review");
        assert_eq!(found["Log"], "header\n- a");
        assert!(!found.contains_key("Notes"));
        assert_eq!(sections("## Holding\n## Waiting\n- w")["Holding"], "");
        assert!(sections("## Holding extra\nx").is_empty());
    }

    #[test]
    fn recent_log_keeps_whole_entries() {
        let log: Vec<String> = (0..100).map(|i| format!("- entry {i}\n  detail {i}")).collect();
        let text = format!("header line\n{}", log.join("\n"));
        let (recent, total) = recent_log(&text, 3);
        assert_eq!(recent, "- entry 97\n  detail 97\n- entry 98\n  detail 98\n- entry 99\n  detail 99");
        assert_eq!(total, 101);
    }

    #[test]
    fn own_process_has_a_start_time() {
        assert!(process_start(std::process::id() as i64).is_some());
        assert!(process_start(999_999_999).is_none());
    }
}
