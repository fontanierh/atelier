//! The render floor's Disk section: free space on the home folder's volume, read on every request (one statfs), and
//! what takes the space, measured by a background scan at most once every five minutes.
//!
//! The breakdown walks a fixed list of places, each counted by allocated size (st_blocks × 512, never following a
//! symlink, staying on the place's own volume, a hard-linked file counted once):
//! - every entry directly in the home folder, except `dev`, `.cache` and `Library` (broken down below) and Desktop,
//!   Documents and Downloads, which macOS asks permission for and the scan never opens;
//! - every entry directly in `~/dev` (checkouts and worktrees) and in `~/.cache/atelier`, then the rest of `~/.cache`;
//! - `~/Library/Caches`, then the rest of `~/Library`, without the other apps' containers, iCloud Drive and cloud
//!   storage folders (which macOS also asks permission for);
//! - `/Users/Shared/Epic Games` (the installed engine) and the user's temporary folder (`$TMPDIR`'s parent).
//!
//! The largest places are shown, then `Other`: the volume's used space less what they add up to. An APFS clone is
//! counted in full in every place that holds one, so the places can add up to more than the used space; Other is then
//! left out rather than shown negative.
use std::collections::HashSet;
use std::ffi::CString;
use std::fs::{self, Metadata};
use std::os::unix::ffi::OsStrExt;
use std::os::unix::fs::MetadataExt;
use std::path::{Path, PathBuf};
use std::sync::{LazyLock, Mutex};
use std::time::Instant;

use crate::api::{Disk, DiskItem};
use crate::db;

/// The breakdown is measured at most this often (seconds between the end of one scan and the start of the next).
pub const REFRESH_SECONDS: f64 = 300.0;
/// The largest places shown before the rest folds into Other.
pub const SHOWN: usize = 12;

/// Free and total bytes on the volume holding `path`, as the user can use them.
pub fn volume(path: &Path) -> Option<(u64, u64)> {
    let path = CString::new(path.as_os_str().as_bytes()).ok()?;
    let mut found: libc::statfs = unsafe { std::mem::zeroed() };
    if unsafe { libc::statfs(path.as_ptr(), &mut found) } != 0 {
        return None;
    }
    let block = found.f_bsize as u64;
    Some((found.f_bavail * block, found.f_blocks * block))
}

/// A file's allocated bytes.
fn allocated(metadata: &Metadata) -> u64 {
    metadata.blocks() * 512
}

/// The allocated bytes under `root`: never following symlinks, never leaving its volume, never entering `skip`, and
/// counting a hard-linked file only the first time `seen` meets it. What cannot be read is left out.
pub fn measure(root: &Path, skip: &HashSet<PathBuf>, seen: &mut HashSet<(u64, u64)>) -> u64 {
    let Ok(metadata) = fs::symlink_metadata(root) else { return 0 };
    let device = metadata.dev();
    let mut total = 0;
    let mut pending = vec![(root.to_path_buf(), metadata)];
    while let Some((path, metadata)) = pending.pop() {
        // A directory's link count is not a hard link count on APFS.
        if !metadata.is_dir() && metadata.nlink() > 1 && !seen.insert((metadata.dev(), metadata.ino())) {
            continue;
        }
        total += allocated(&metadata);
        if !metadata.is_dir() {
            continue;
        }
        let Ok(entries) = fs::read_dir(&path) else { continue };
        for entry in entries.flatten() {
            // A directory entry's metadata is lstat's: a symlink is itself, never what it points to.
            let Ok(child) = entry.metadata() else { continue };
            let child_path = entry.path();
            if child.dev() != device || (child.is_dir() && skip.contains(&child_path)) {
                continue;
            }
            pending.push((child_path, child));
        }
    }
    total
}

/// One place the breakdown measures.
#[derive(Clone, Debug, PartialEq)]
pub struct Place {
    pub label: String,
    pub path: PathBuf,
}

/// What a scan measures, and what it never enters.
#[derive(Debug, Default)]
pub struct Plan {
    pub places: Vec<Place>,
    pub skip: HashSet<PathBuf>,
}

impl Plan {
    /// The machine's places, from the home folder, the shared engine folder and the temporary folder.
    pub fn new(home: &Path, engine: &Path, temp: Option<&Path>) -> Plan {
        let (dev, cache, library) = (home.join("dev"), home.join(".cache"), home.join("Library"));
        let atelier = cache.join("atelier");
        let library_caches = library.join("Caches");
        let mut skip: HashSet<PathBuf> = [&dev, &cache, &library, &atelier, &library_caches].map(|p| p.to_path_buf()).into();
        // macOS asks the person before a process opens these; the scan never does.
        skip.extend(["Desktop", "Documents", "Downloads"].map(|name| home.join(name)));
        skip.extend(["Containers", "Group Containers", "Mobile Documents", "CloudStorage"].map(|name| library.join(name)));
        let mut places = Vec::new();
        for parent in [home, dev.as_path(), atelier.as_path()] {
            let Ok(entries) = fs::read_dir(parent) else { continue };
            for entry in entries.flatten() {
                let path = entry.path();
                if !skip.contains(&path) {
                    places.push(Place { label: entry.file_name().to_string_lossy().into_owned(), path });
                }
            }
        }
        places.push(Place { label: ".cache (rest)".into(), path: cache });
        places.push(Place { label: "Library caches".into(), path: library_caches });
        places.push(Place { label: "Library (rest)".into(), path: library });
        places.push(Place { label: "Unreal Engine (Epic Games)".into(), path: engine.to_path_buf() });
        if let Some(temp) = temp.filter(|temp| !temp.starts_with(home)) {
            places.push(Place { label: "Temporary files".into(), path: temp.to_path_buf() });
        }
        // Every place is measured once: a walk never enters another place.
        skip.extend(places.iter().map(|place| place.path.clone()));
        places.retain(|place| fs::symlink_metadata(&place.path).is_ok());
        Plan { places, skip }
    }
}

/// One measured breakdown.
#[derive(Clone, Debug, PartialEq)]
pub struct Breakdown {
    /// When the scan finished, in Unix seconds.
    pub measured_at: f64,
    pub seconds: f64,
    pub items: Vec<DiskItem>,
}

/// How a place's path is shown: relative to the home folder (`~/…`) when it is inside it.
pub fn shown_path(path: &Path, home: &Path) -> String {
    match path.strip_prefix(home) {
        Ok(rest) if rest.as_os_str().is_empty() => "~".into(),
        Ok(rest) => format!("~/{}", rest.display()),
        Err(_) => path.display().to_string(),
    }
}

/// The largest `SHOWN` places, biggest first, then Other: `used` less what they add up to, left out when that is not
/// positive (clones counted in several places can add up to more than the used space).
pub fn fold(mut measured: Vec<(Place, u64)>, used: Option<u64>, home: &Path) -> Vec<DiskItem> {
    measured.retain(|(_, bytes)| *bytes > 0);
    measured.sort_by(|a, b| b.1.cmp(&a.1).then_with(|| a.0.label.cmp(&b.0.label)));
    measured.truncate(SHOWN);
    let sum: u64 = measured.iter().map(|(_, bytes)| bytes).sum();
    let mut items: Vec<DiskItem> = measured
        .into_iter()
        .map(|(place, bytes)| DiskItem { label: place.label, path: Some(shown_path(&place.path, home)), bytes })
        .collect();
    if let Some(other) = used.map(|used| used.saturating_sub(sum)).filter(|other| *other > 0) {
        items.push(DiskItem { label: "Other".into(), path: None, bytes: other });
    }
    items
}

/// Measures every place in the plan, and Other against the volume's used space at the end.
pub fn scan(plan: &Plan, home: &Path, now: impl Fn() -> f64) -> Breakdown {
    let started = Instant::now();
    let mut seen = HashSet::new();
    let measured = plan.places.iter().map(|place| (place.clone(), measure(&place.path, &plan.skip, &mut seen))).collect();
    let used = volume(home).map(|(free, total)| total.saturating_sub(free));
    Breakdown { items: fold(measured, used, home), seconds: started.elapsed().as_secs_f64(), measured_at: now() }
}

#[derive(Debug, Default)]
struct Status {
    last: Option<Breakdown>,
    scanning: bool,
    /// When the last scan ended, finished or failed.
    ended: Option<f64>,
}

/// The last breakdown and the single scan that may be refreshing it.
#[derive(Debug)]
pub struct Cache {
    status: Mutex<Status>,
    interval: f64,
}

impl Cache {
    pub fn new(interval: f64) -> Cache {
        Cache { status: Mutex::new(Status::default()), interval }
    }

    /// The last breakdown and whether a scan is running. When there is none yet, or the last scan ended at least the
    /// interval ago, and none is running, this one call is told to start it (`true`) and must then call `end`.
    pub fn check(&self, now: f64) -> (Option<Breakdown>, bool, bool) {
        let mut status = self.status.lock().unwrap_or_else(|poisoned| poisoned.into_inner());
        let due = status.ended.is_none_or(|ended| now - ended >= self.interval);
        let start = due && !status.scanning;
        if start {
            status.scanning = true;
        }
        (status.last.clone(), status.scanning, start)
    }

    /// A scan ended at `now`, with its breakdown unless it failed (the last one is then kept).
    pub fn end(&self, result: Option<Breakdown>, now: f64) {
        let mut status = self.status.lock().unwrap_or_else(|poisoned| poisoned.into_inner());
        status.scanning = false;
        status.ended = Some(now);
        if result.is_some() {
            status.last = result;
        }
    }
}

static CACHE: LazyLock<Cache> = LazyLock::new(|| Cache::new(REFRESH_SECONDS));

/// Ends the scan even if it panics, so a failed scan waits out the interval rather than block the next one forever.
struct Ending(Option<Breakdown>);

impl Drop for Ending {
    fn drop(&mut self) {
        CACHE.end(self.0.take(), db::now());
    }
}

/// `ATELIER_BOARD_DISK_SCAN=0` turns the breakdown off (tests, whose servers come and go in seconds).
fn enabled() -> bool {
    std::env::var("ATELIER_BOARD_DISK_SCAN").map_or(true, |value| value != "0")
}

/// The scanning thread runs in the background band: low CPU priority and throttled disk reads.
fn lower_priority() {
    unsafe {
        libc::setpriority(libc::PRIO_DARWIN_THREAD, 0, libc::PRIO_DARWIN_BG);
    }
}

/// @cc [owner:fontanierh,label:safety] gentle-disk-scan
/// A board request MUST NOT wait for the disk breakdown. At most one scan MAY run at a time, a scan MUST NOT start
/// within REFRESH_SECONDS of the previous one ending, it runs at background priority, and it MUST NOT open the
/// folders macOS guards with a permission prompt (Desktop, Documents, Downloads, app containers, cloud storage).
///
/// The Disk section as the render floor shows it. It starts the background scan when the breakdown is due.
pub fn report() -> Disk {
    let home = db::home();
    let (free_bytes, total_bytes) = volume(&home).map_or((None, None), |(free, total)| (Some(free), Some(total)));
    let (last, scanning, start) = if enabled() { CACHE.check(db::now()) } else { (None, false, false) };
    if start {
        let spawned = std::thread::Builder::new().name("disk-scan".into()).spawn(move || {
            let mut ending = Ending(None);
            lower_priority();
            let temp = std::env::temp_dir();
            let plan = Plan::new(&home, Path::new("/Users/Shared/Epic Games"), temp.parent());
            ending.0 = Some(scan(&plan, &home, db::now));
        });
        if spawned.is_err() {
            CACHE.end(None, db::now());
        }
    }
    Disk {
        free_bytes,
        total_bytes,
        measured_at: last.as_ref().map(|b| b.measured_at),
        scan_seconds: last.as_ref().map(|b| b.seconds),
        scanning,
        items: last.map(|b| b.items).unwrap_or_default(),
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::os::unix::fs::PermissionsExt;

    /// A fresh folder for one test, removed when it ends.
    struct Temp(PathBuf);

    impl Temp {
        fn new(name: &str) -> Temp {
            let path = std::env::temp_dir().join(format!("board-disk-{name}-{}-{}", std::process::id(), db::now().to_bits()));
            fs::create_dir_all(&path).unwrap();
            Temp(path)
        }
    }

    impl Drop for Temp {
        fn drop(&mut self) {
            let _ = fs::remove_dir_all(&self.0);
        }
    }

    fn write(path: &Path, bytes: usize) -> u64 {
        fs::create_dir_all(path.parent().unwrap()).unwrap();
        fs::write(path, vec![7u8; bytes]).unwrap();
        allocated(&fs::symlink_metadata(path).unwrap())
    }

    #[test]
    fn counts_hard_links_once_and_never_follows_symlinks_or_unreadable_folders() {
        let temp = Temp::new("walk");
        let (tree, outside) = (temp.0.join("tree"), temp.0.join("outside"));
        let file = write(&tree.join("a/file.bin"), 64 << 10);
        fs::create_dir_all(tree.join("b")).unwrap();
        fs::hard_link(tree.join("a/file.bin"), tree.join("b/link.bin")).unwrap();
        let big = write(&outside.join("big.bin"), 1 << 20);
        std::os::unix::fs::symlink(&outside, tree.join("to-outside")).unwrap();
        std::os::unix::fs::symlink(outside.join("big.bin"), tree.join("big-link")).unwrap();
        let hidden = write(&tree.join("locked/secret.bin"), 256 << 10);
        fs::set_permissions(tree.join("locked"), fs::Permissions::from_mode(0o000)).unwrap();
        let total = measure(&tree, &HashSet::new(), &mut HashSet::new());
        fs::set_permissions(tree.join("locked"), fs::Permissions::from_mode(0o755)).unwrap();
        assert!(file > 0 && big > 0 && hidden > 0);
        // Folders and symlinks take a few blocks at most; the file once, never the big one or the locked one.
        assert!(total >= file && total < file + (64 << 10), "{total} for a {file}-byte file");
        // A hard link already met in another place is not counted again; an unknown path counts nothing.
        let mut seen = HashSet::new();
        let first = measure(&tree.join("a"), &HashSet::new(), &mut seen);
        assert!(measure(&tree.join("b"), &HashSet::new(), &mut seen) < file && first >= file);
        assert_eq!(measure(&temp.0.join("missing"), &HashSet::new(), &mut seen), 0);
    }

    #[test]
    fn plan_measures_each_place_once_and_never_opens_protected_folders() {
        let temp = Temp::new("plan");
        let (home, engine) = (temp.0.join("home"), temp.0.join("Epic Games"));
        for path in ["dev/one/x", "dev/two/x", ".cache/atelier/products/x", ".cache/uv/x", "Library/Caches/app/x",
                     "Library/Preferences/x", "Library/Containers/other/x", "Documents/x", "UnrealEngine/x"] {
            write(&home.join(path), 4096);
        }
        write(&engine.join("UE/x"), 4096);
        let plan = Plan::new(&home, &engine, Some(&temp.0.join("not-there")));
        let mut shown: Vec<String> = plan.places.iter().map(|p| shown_path(&p.path, &home)).collect();
        shown.sort();
        let expected = ["~/.cache", "~/.cache/atelier/products", "~/Library", "~/Library/Caches", "~/UnrealEngine",
                        "~/dev/one", "~/dev/two"];
        let mut expected: Vec<String> = expected.map(String::from).into();
        expected.push(engine.display().to_string());
        expected.sort();
        assert_eq!(shown, expected);
        let size = |path: &str| measure(&home.join(path), &plan.skip, &mut HashSet::new());
        // The rest of Library leaves out its caches and other apps' containers; .cache leaves out atelier's folders.
        assert!(size("Library") >= 4096 && size("Library") < 2 * 4096, "{}", size("Library"));
        assert!(size(".cache") >= 4096 && size(".cache") < 2 * 4096);
        assert!(!plan.places.iter().any(|p| p.path.starts_with(home.join("Documents"))));
    }

    #[test]
    fn folds_small_places_into_other_and_never_shows_it_negative() {
        let home = PathBuf::from("/home/me");
        let places: Vec<(Place, u64)> = (0..15u64)
            .map(|i| (Place { label: format!("p{i}"), path: home.join(format!("dev/p{i}")) }, (i + 1) * 100))
            .chain([(Place { label: "empty".into(), path: home.join("e") }, 0)])
            .collect();
        let items = fold(places.clone(), Some(20_000), &home);
        assert_eq!(items.len(), SHOWN + 1);
        assert_eq!((items[0].label.as_str(), items[0].path.as_deref(), items[0].bytes), ("p14", Some("~/dev/p14"), 1500));
        let shown: u64 = items[..SHOWN].iter().map(|i| i.bytes).sum();
        assert_eq!(items[SHOWN], DiskItem { label: "Other".into(), path: None, bytes: 20_000 - shown });
        // Clones can make the places add up to more than is used: Other is then left out.
        assert!(fold(places.clone(), Some(1000), &home).iter().all(|i| i.label != "Other"));
        assert!(fold(places, None, &home).iter().all(|i| i.label != "Other"));
        assert_eq!(shown_path(Path::new("/Users/Shared/Epic Games"), &home), "/Users/Shared/Epic Games");
    }

    #[test]
    fn rescans_at_most_once_per_interval_and_one_at_a_time() {
        let cache = Cache::new(300.0);
        let breakdown = |at: f64| Breakdown { measured_at: at, seconds: 1.0, items: vec![] };
        // The first look starts the one scan; looks while it runs neither wait nor start another.
        assert_eq!(cache.check(1000.0), (None, true, true));
        assert_eq!(cache.check(1001.0), (None, true, false));
        assert_eq!(cache.check(5000.0), (None, true, false));
        cache.end(Some(breakdown(5010.0)), 5010.0);
        // Within the interval of its end, the last breakdown is shown and nothing is rescanned.
        assert_eq!(cache.check(5010.0), (Some(breakdown(5010.0)), false, false));
        assert_eq!(cache.check(5309.0), (Some(breakdown(5010.0)), false, false));
        // Once it is due, exactly one look starts the next scan, and the old breakdown stays up meanwhile.
        assert_eq!(cache.check(5310.0), (Some(breakdown(5010.0)), true, true));
        assert_eq!(cache.check(5311.0), (Some(breakdown(5010.0)), true, false));
        // A failed scan keeps the last breakdown and also waits out the interval.
        cache.end(None, 5400.0);
        assert_eq!(cache.check(5500.0), (Some(breakdown(5010.0)), false, false));
        assert_eq!(cache.check(5700.0).2, true);
    }

    #[test]
    fn single_flight_under_concurrent_looks() {
        let cache = std::sync::Arc::new(Cache::new(300.0));
        let starts: usize = (0..16)
            .map(|_| {
                let cache = cache.clone();
                std::thread::spawn(move || cache.check(10.0).2 as usize)
            })
            .collect::<Vec<_>>()
            .into_iter()
            .map(|handle| handle.join().unwrap())
            .sum();
        assert_eq!(starts, 1);
    }

    #[test]
    fn volumes_report_free_and_total_space() {
        let (free, total) = volume(&std::env::temp_dir()).unwrap();
        assert!(total > 0 && free <= total);
    }
}
