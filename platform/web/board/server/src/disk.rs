//! The render floor's Disk section: free space on the home folder's volume, read on every request (one statfs), and
//! what takes the space, measured by a slow background scan.
//!
//! The breakdown measures a fixed list of places by allocated size (st_blocks × 512 from readdir + lstat, never
//! following a symlink, staying on the place's own volume, a hard-linked file counted once, what cannot be read left
//! out):
//! - every entry directly in `~/dev` (checkouts and worktrees) and in `~/.cache/atelier`, then the rest of `~/.cache`;
//! - `~/Library/Caches`, then the rest of `~/Library` without the folders macOS guards for privacy (`PRIVATE`);
//! - `/Users/Shared/Epic Games` (the installed engine) and the user's temporary folder (`$TMPDIR`'s parent).
//!
//! The largest places are shown, then `Other`: the volume's used space less what they add up to. An APFS clone is
//! counted in full in every place that holds one, so the places can add up to more than the used space; Other is then
//! left out rather than shown negative.
//!
//! A full scan is expensive: on a machine with many checkouts it takes tens of minutes, and opening a guarded folder
//! can block for seconds while macOS checks it. So the scan runs on one thread in the background band (lowest CPU
//! priority and throttled disk reads), never while any render lane's lock is held, the fitting lane included (it
//! pauses and resumes, checking between directory entries), and the next one starts only `REFRESH_SECONDS` after the
//! last one finished. Each place keeps its own measurement, so a scan in progress shows the places it has already
//! measured, and the one it is measuring.
use std::collections::{HashMap, HashSet};
use std::ffi::CString;
use std::fs::{self, Metadata};
use std::os::unix::ffi::OsStrExt;
use std::os::unix::fs::MetadataExt;
use std::path::{Path, PathBuf};
use std::sync::{LazyLock, Mutex};
use std::time::{Duration, Instant};

use crate::api::{Disk, DiskItem};
use crate::db;

/// A scan starts at most this long (seconds) after the previous one finished.
pub const REFRESH_SECONDS: f64 = 300.0;
/// The largest places shown before the rest folds into Other.
pub const SHOWN: usize = 12;
/// How often a scan checks the render locks, and how long it sleeps before checking again while one is held.
const LOCK_CHECK: Duration = Duration::from_secs(2);
const PAUSE: Duration = Duration::from_secs(15);
/// Folders in `~/Library` that macOS guards for privacy: a scan never opens them (they count under Other).
pub const PRIVATE: &[&str] = &[
    "Accounts", "Application Support/AddressBook", "Application Support/CallHistoryDB",
    "Application Support/CallHistoryTransactions", "Application Support/Knowledge", "Application Support/MobileSync",
    "Application Support/com.apple.TCC", "Biome", "Calendars", "CloudStorage", "Containers", "Cookies",
    "Daemon Containers", "Group Containers", "HomeKit", "IdentityServices", "Mail", "Messages", "Metadata",
    "Mobile Documents", "PersonalizationPortrait", "Reminders", "Safari", "Sharing", "Suggestions", "Trial",
];

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

fn allocated(metadata: &Metadata) -> u64 {
    metadata.blocks() * 512
}

/// The allocated bytes under `root`: never following symlinks, never leaving its volume, never entering `skip`, and
/// counting a hard-linked file only the first time `seen` meets it. What cannot be read is left out. `tick` hears the
/// running total after every entry it lists, so a long listing can pause too (it may pause the walk).
pub fn measure(root: &Path, skip: &HashSet<PathBuf>, seen: &mut HashSet<(u64, u64)>, tick: &mut dyn FnMut(u64)) -> u64 {
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
        if let Ok(entries) = fs::read_dir(&path) {
            for entry in entries.flatten() {
                // Every entry, skipped or not, gives a render the chance to pause the walk.
                tick(total);
                // A directory entry's metadata is lstat's: a symlink is itself, never what it points to.
                let Ok(child) = entry.metadata() else { continue };
                let child_path = entry.path();
                if child.dev() != device || (child.is_dir() && skip.contains(&child_path)) {
                    continue;
                }
                pending.push((child_path, child));
            }
        }
        tick(total);
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
    /// The machine's places, from the home folder, the shared engine folder and the temporary folder. `pause` runs
    /// before each folder it lists, after each entry and before each place's lstat, so setup can wait for a render too.
    pub fn new(home: &Path, engine: &Path, temp: Option<&Path>, pause: &mut dyn FnMut()) -> Plan {
        let (dev, cache, library) = (home.join("dev"), home.join(".cache"), home.join("Library"));
        let atelier = cache.join("atelier");
        let mut skip: HashSet<PathBuf> = PRIVATE.iter().map(|name| library.join(name)).collect();
        skip.insert(atelier.clone());
        let mut places = Vec::new();
        for parent in [&dev, &atelier] {
            pause();
            // A symlinked folder is never listed: it could lead into a folder macOS guards.
            if !fs::symlink_metadata(parent).is_ok_and(|found| found.is_dir()) {
                continue;
            }
            let Ok(entries) = fs::read_dir(parent) else { continue };
            let mut found: Vec<Place> = entries
                .flatten()
                .map(|entry| {
                    pause();
                    Place { label: entry.file_name().to_string_lossy().into_owned(), path: entry.path() }
                })
                .collect();
            found.sort_by(|a, b| a.label.cmp(&b.label));
            places.extend(found);
        }
        places.push(Place { label: ".cache (rest)".into(), path: cache });
        places.push(Place { label: "Library caches".into(), path: library.join("Caches") });
        places.push(Place { label: "Library (rest)".into(), path: library });
        places.push(Place { label: "Unreal Engine (Epic Games)".into(), path: engine.to_path_buf() });
        if let Some(temp) = temp.filter(|temp| !temp.starts_with(home)) {
            places.push(Place { label: "Temporary files".into(), path: temp.to_path_buf() });
        }
        // Every place is measured once: a walk never enters another place.
        skip.extend(places.iter().map(|place| place.path.clone()));
        places.retain(|place| {
            pause();
            fs::symlink_metadata(&place.path).is_ok()
        });
        Plan { places, skip }
    }
}

/// How a place's path is shown: relative to the home folder (`~/…`) when it is inside it.
pub fn shown_path(path: &Path, home: &Path) -> String {
    match path.strip_prefix(home) {
        Ok(rest) if rest.as_os_str().is_empty() => "~".into(),
        Ok(rest) => format!("~/{}", rest.display()),
        Err(_) => path.display().to_string(),
    }
}

/// A place's last measurement.
#[derive(Clone, Debug, PartialEq)]
struct Measured {
    label: String,
    bytes: u64,
    at: f64,
}

#[derive(Debug, Default)]
struct Status {
    /// Each place's own last measurement, kept across scans.
    measured: HashMap<PathBuf, Measured>,
    /// The place being measured now, and the bytes counted so far.
    current: Option<(Place, u64)>,
    scanning: bool,
    paused: bool,
    /// When the last scan ended (finished or failed), and the last complete scan's end and duration.
    ended: Option<f64>,
    complete: Option<(f64, f64)>,
}

/// One place as the Disk section shows it: label, path, bytes, its own measurement time, and whether it is being
/// measured now.
pub type Shown = (String, PathBuf, u64, Option<f64>, bool);

/// What the Disk section shows from the cache.
#[derive(Clone, Debug, PartialEq)]
pub struct View {
    pub measured_at: Option<f64>,
    pub scan_seconds: Option<f64>,
    pub scanning: bool,
    pub paused: bool,
    pub places: Vec<Shown>,
}

/// The places' measurements and the single scan that may be refreshing them.
#[derive(Debug)]
pub struct Cache {
    status: Mutex<Status>,
    interval: f64,
}

impl Cache {
    pub fn new(interval: f64) -> Cache {
        Cache { status: Mutex::new(Status::default()), interval }
    }

    fn lock(&self) -> std::sync::MutexGuard<'_, Status> {
        self.status.lock().unwrap_or_else(|poisoned| poisoned.into_inner())
    }

    /// What to show, and whether this one call must start a scan (then it owns it and must call `end`): when none has
    /// ended yet or the last ended at least the interval ago, none is running, and no render lock is held.
    pub fn check(&self, now: f64, render_busy: bool) -> (View, bool) {
        let mut status = self.lock();
        let due = status.ended.is_none_or(|ended| now - ended >= self.interval);
        let start = due && !status.scanning && !render_busy;
        if start {
            status.scanning = true;
        }
        let current = status.current.as_ref().map(|(place, _)| &place.path);
        let mut places: Vec<Shown> = status
            .measured
            .iter()
            .filter(|(path, _)| current != Some(*path))
            .map(|(path, m)| (m.label.clone(), path.clone(), m.bytes, Some(m.at), false))
            .collect();
        if let Some((place, so_far)) = &status.current {
            // A place measured before shows its last size until the new count passes it.
            let (bytes, at) = status.measured.get(&place.path).map_or((*so_far, None), |m| (m.bytes.max(*so_far), Some(m.at)));
            places.push((place.label.clone(), place.path.clone(), bytes, at, true));
        }
        let view = View {
            measured_at: status.complete.map(|(at, _)| at),
            scan_seconds: status.complete.map(|(_, seconds)| seconds),
            scanning: status.scanning,
            paused: status.paused,
            places,
        };
        (view, start)
    }

    fn measuring(&self, place: &Place, so_far: u64, paused: bool) {
        let mut status = self.lock();
        status.current = Some((place.clone(), so_far));
        status.paused = paused;
    }

    fn measured(&self, place: &Place, bytes: u64, now: f64) {
        let mut status = self.lock();
        status.measured.insert(place.path.clone(), Measured { label: place.label.clone(), bytes, at: now });
        status.current = None;
    }

    /// A scan ended at `now`. A complete one (with its plan's places and duration) forgets places no longer planned.
    pub fn end(&self, complete: Option<(&[Place], f64)>, now: f64) {
        let mut status = self.lock();
        status.scanning = false;
        status.paused = false;
        status.current = None;
        status.ended = Some(now);
        if let Some((places, seconds)) = complete {
            let planned: HashSet<&PathBuf> = places.iter().map(|place| &place.path).collect();
            status.measured.retain(|path, _| planned.contains(path));
            status.complete = Some((now, seconds));
        }
    }
}

/// Measures every place in turn, recording each as it finishes. While `render_busy` says a render lock is held (asked
/// at most every `check_every`), the walk stays paused, calling `wait` between checks. Returns the seconds it took.
pub fn scan(plan: &Plan, cache: &Cache, now: &dyn Fn() -> f64, render_busy: &dyn Fn() -> bool, wait: &dyn Fn(),
            check_every: Duration) -> f64 {
    let started = Instant::now();
    let mut seen = HashSet::new();
    let mut checked: Option<Instant> = None;
    for place in &plan.places {
        cache.measuring(place, 0, false);
        let mut tick = |so_far: u64| {
            if checked.is_some_and(|at| at.elapsed() < check_every) {
                return;
            }
            cache.measuring(place, so_far, false);
            while render_busy() {
                cache.measuring(place, so_far, true);
                wait();
            }
            cache.measuring(place, so_far, false);
            checked = Some(Instant::now());
        };
        tick(0);
        let bytes = measure(&place.path, &plan.skip, &mut seen, &mut tick);
        cache.measured(place, bytes, now());
    }
    started.elapsed().as_secs_f64()
}

/// The largest `SHOWN` places, biggest first (the one being measured always shown), then Other: `used` less what the
/// shown places add up to, only once a complete scan exists and only when positive.
pub fn fold(view: &View, used: Option<u64>, home: &Path) -> Vec<DiskItem> {
    let mut places = view.places.clone();
    places.retain(|(_, _, bytes, _, measuring)| *bytes > 0 || *measuring);
    places.sort_by(|a, b| b.2.cmp(&a.2).then_with(|| a.0.cmp(&b.0)));
    let mut shown: Vec<Shown> = places.iter().take(SHOWN).cloned().collect();
    if let Some(measuring) = places.iter().skip(SHOWN).find(|place| place.4) {
        shown.push(measuring.clone());
    }
    let sum: u64 = shown.iter().map(|place| place.2).sum();
    let mut items: Vec<DiskItem> = shown
        .into_iter()
        .map(|(label, path, bytes, measured_at, measuring)| DiskItem {
            label,
            path: Some(shown_path(&path, home)),
            bytes,
            measured_at,
            measuring,
        })
        .collect();
    let other = used.filter(|_| view.measured_at.is_some()).map(|used| used.saturating_sub(sum)).filter(|other| *other > 0);
    if let Some(other) = other {
        items.push(DiskItem { label: "Other".into(), path: None, bytes: other, measured_at: None, measuring: false });
    }
    items
}

static CACHE: LazyLock<Cache> = LazyLock::new(|| Cache::new(REFRESH_SECONDS));

/// Ends the scan even if it panics, so a failed scan waits out the interval rather than block the next one forever.
struct Ending(Option<(Vec<Place>, f64)>);

impl Drop for Ending {
    fn drop(&mut self) {
        let complete = self.0.take();
        CACHE.end(complete.as_ref().map(|(places, seconds)| (places.as_slice(), *seconds)), db::now());
    }
}

/// `ATELIER_BOARD_DISK_SCAN=0` turns the breakdown off (tests, whose servers come and go in seconds).
fn enabled() -> bool {
    std::env::var("ATELIER_BOARD_DISK_SCAN").map_or(true, |value| value != "0")
}

/// The scanning thread joins the background band: the lowest CPU priority, and disk reads throttled behind everyone
/// else's.
fn lower_priority() {
    unsafe {
        libc::setpriority(libc::PRIO_DARWIN_THREAD, 0, libc::PRIO_DARWIN_BG);
    }
}

/// The installed engine's folder: `ATELIER_BOARD_DISK_ENGINE` (for previews on a sample tree), else Epic's.
fn engine() -> PathBuf {
    std::env::var_os("ATELIER_BOARD_DISK_ENGINE")
        .filter(|value| !value.is_empty())
        .map_or_else(|| PathBuf::from("/Users/Shared/Epic Games"), PathBuf::from)
}

fn render_busy() -> bool {
    crate::floor::any_lane_held()
}

/// @cc [owner:fontanierh,label:safety] gentle-disk-scan
/// A board request MUST NOT wait for the disk breakdown. At most one scan MAY run at a time, in the background
/// band, and the next MUST NOT start within REFRESH_SECONDS of the previous one finishing. A scan MUST NOT start or
/// continue while any render lane's lock is held (big, small or fitting), and MUST NOT open the folders macOS guards
/// for privacy.
///
/// The Disk section as the render floor shows it, given whether a render lock is held now.
pub fn report(render_held: bool) -> Disk {
    let home = db::home();
    let volume = volume(&home);
    let (view, start) = if enabled() {
        CACHE.check(db::now(), render_held)
    } else {
        (View { measured_at: None, scan_seconds: None, scanning: false, paused: false, places: vec![] }, false)
    };
    if start {
        let scan_home = home.clone();
        let spawned = std::thread::Builder::new().name("disk-scan".into()).spawn(move || {
            let mut ending = Ending(None);
            lower_priority();
            let temp = std::env::temp_dir();
            let plan = Plan::new(&scan_home, &engine(), temp.parent(), &mut || {
                while render_busy() {
                    std::thread::sleep(PAUSE);
                }
            });
            let seconds = scan(&plan, &CACHE, &db::now, &render_busy, &|| std::thread::sleep(PAUSE), LOCK_CHECK);
            ending.0 = Some((plan.places, seconds));
        });
        if spawned.is_err() {
            CACHE.end(None, db::now());
        }
    }
    let used = volume.map(|(free, total)| total.saturating_sub(free));
    Disk {
        free_bytes: volume.map(|(free, _)| free),
        total_bytes: volume.map(|(_, total)| total),
        measured_at: view.measured_at,
        scan_seconds: view.scan_seconds,
        scanning: view.scanning,
        paused: view.paused,
        items: fold(&view, used, &home),
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::cell::Cell;
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

    fn size(path: &Path, skip: &HashSet<PathBuf>) -> u64 {
        measure(path, skip, &mut HashSet::new(), &mut |_| {})
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
        let total = size(&tree, &HashSet::new());
        fs::set_permissions(tree.join("locked"), fs::Permissions::from_mode(0o755)).unwrap();
        assert!(file > 0 && big > 0 && hidden > 0);
        // Folders and symlinks take a few blocks at most; the file once, never the big one or the locked one.
        assert!(total >= file && total < file + (64 << 10), "{total} for a {file}-byte file");
        // A hard link already met in another place is not counted again; an unknown path counts nothing.
        let mut seen = HashSet::new();
        let first = measure(&tree.join("a"), &HashSet::new(), &mut seen, &mut |_| {});
        assert!(measure(&tree.join("b"), &HashSet::new(), &mut seen, &mut |_| {}) < file && first >= file);
        assert_eq!(size(&temp.0.join("missing"), &HashSet::new()), 0);
    }

    #[test]
    fn plan_measures_each_place_once_and_never_opens_private_folders() {
        let temp = Temp::new("plan");
        let (home, engine) = (temp.0.join("home"), temp.0.join("Epic Games"));
        for path in ["dev/one/x", "dev/two/x", ".cache/atelier/products/x", ".cache/uv/x", "Library/Caches/app/x",
                     "Library/Preferences/x", "Library/Containers/other/x", "Library/Mail/x", "Documents/x", ".Trash/x"] {
            write(&home.join(path), 4096);
        }
        write(&engine.join("UE/x"), 4096);
        let mut pauses = 0;
        let plan = Plan::new(&home, &engine, Some(&temp.0.join("not-there")), &mut || pauses += 1);
        // Before listing ~/dev and ~/.cache/atelier, after each of their three entries, and before checking each of the
        // eight places exists.
        assert_eq!(pauses, 2 + 3 + 8);
        let shown: Vec<String> = plan.places.iter().map(|p| shown_path(&p.path, &home)).collect();
        let mut expected: Vec<String> =
            ["~/dev/one", "~/dev/two", "~/.cache/atelier/products", "~/.cache", "~/Library/Caches", "~/Library"]
                .map(String::from)
                .into();
        expected.push(engine.display().to_string());
        assert_eq!(shown, expected);
        // The rest of Library leaves out its caches and private folders; .cache leaves out atelier's folders.
        let library = size(&home.join("Library"), &plan.skip);
        assert!((4096..2 * 4096).contains(&library), "{library}");
        assert!((4096..2 * 4096).contains(&size(&home.join(".cache"), &plan.skip)));
    }

    #[test]
    fn folds_small_places_into_other_and_never_shows_it_negative() {
        let home = PathBuf::from("/home/me");
        let mut places: Vec<Shown> =
            (0..15u64).map(|i| (format!("p{i}"), home.join(format!("dev/p{i}")), (i + 1) * 100, Some(5.0), false)).collect();
        places.push(("empty".into(), home.join("e"), 0, Some(5.0), false));
        let mut view = View { measured_at: Some(9.0), scan_seconds: Some(4.0), scanning: false, paused: false, places };
        let items = fold(&view, Some(20_000), &home);
        assert_eq!(items.len(), SHOWN + 1);
        assert_eq!((items[0].label.as_str(), items[0].path.as_deref(), items[0].bytes), ("p14", Some("~/dev/p14"), 1500));
        let shown: u64 = items[..SHOWN].iter().map(|i| i.bytes).sum();
        let other = DiskItem { label: "Other".into(), path: None, bytes: 20_000 - shown, measured_at: None, measuring: false };
        assert_eq!(items[SHOWN], other);
        // Clones can make the places add up to more than is used: Other is then left out.
        assert!(fold(&view, Some(1000), &home).iter().all(|i| i.label != "Other"));
        // The place being measured is shown even when small; before a complete scan there is no Other.
        view.places.push(("new".into(), home.join("dev/new"), 0, None, true));
        view.measured_at = None;
        let items = fold(&view, Some(20_000), &home);
        assert!(items.last().unwrap().measuring && items.iter().all(|i| i.label != "Other"));
        assert_eq!(shown_path(Path::new("/Users/Shared/Epic Games"), &home), "/Users/Shared/Epic Games");
    }

    #[test]
    fn rescans_only_after_the_interval_from_the_last_finish_and_one_at_a_time() {
        let cache = Cache::new(300.0);
        // A held render lock keeps the first scan from starting.
        assert!(!cache.check(1000.0, true).1);
        // The first look starts the one scan; looks while it runs neither wait nor start another.
        assert!(cache.check(1000.0, false).1);
        let (view, start) = cache.check(5000.0, false);
        assert!(view.scanning && !start);
        cache.end(Some((&[], 4000.0)), 5010.0);
        let (view, start) = cache.check(5309.0, false);
        assert_eq!((view.measured_at, view.scan_seconds, view.scanning, start), (Some(5010.0), Some(4000.0), false, false));
        // Due again 300 s after the finish, but not while a render lock is held.
        assert!(!cache.check(5310.0, true).1);
        assert!(cache.check(5310.0, false).1);
        assert!(!cache.check(5311.0, false).1);
        // A failed scan keeps the last complete one and also waits out the interval.
        cache.end(None, 5400.0);
        let (view, start) = cache.check(5500.0, false);
        assert_eq!((view.measured_at, start), (Some(5010.0), false));
        assert!(cache.check(5700.0, false).1);
    }

    #[test]
    fn single_flight_under_concurrent_looks() {
        let cache = std::sync::Arc::new(Cache::new(300.0));
        let starts: usize = (0..16)
            .map(|_| {
                let cache = cache.clone();
                std::thread::spawn(move || cache.check(10.0, false).1 as usize)
            })
            .collect::<Vec<_>>()
            .into_iter()
            .map(|handle| handle.join().unwrap())
            .sum();
        assert_eq!(starts, 1);
    }

    #[test]
    fn a_scan_shows_each_place_as_measured_and_pauses_while_a_render_runs() {
        let temp = Temp::new("scan");
        let (one, two) = (temp.0.join("one"), temp.0.join("two"));
        let first = write(&one.join("a/x.bin"), 64 << 10);
        let second = write(&two.join("b/y.bin"), 128 << 10);
        let plan = Plan {
            places: vec![Place { label: "one".into(), path: one }, Place { label: "two".into(), path: two }],
            skip: HashSet::new(),
        };
        let cache = Cache::new(300.0);
        assert!(cache.check(0.0, false).1);
        // The render lock is held for the first three checks, which come while measuring "one".
        let (checks, waits, clock) = (Cell::new(0), Cell::new(0), Cell::new(100.0));
        let busy = || {
            checks.set(checks.get() + 1);
            checks.get() <= 3
        };
        let wait = || {
            waits.set(waits.get() + 1);
            let (view, _) = cache.check(0.0, false);
            let measuring: Vec<&str> = view.places.iter().filter(|p| p.4).map(|p| p.0.as_str()).collect();
            assert!(view.paused && view.scanning && measuring == ["one"]);
        };
        let now = || {
            clock.set(clock.get() + 1.0);
            clock.get()
        };
        scan(&plan, &cache, &now, &busy, &wait, Duration::ZERO);
        assert_eq!(waits.get(), 3);
        let (view, _) = cache.check(0.0, false);
        let mut places = view.places.clone();
        places.sort_by(|a, b| a.0.cmp(&b.0));
        // Each place has its own measurement time; none is still measuring, and nothing is paused.
        let summary: Vec<(&str, Option<f64>, bool)> = places.iter().map(|p| (p.0.as_str(), p.3, p.4)).collect();
        assert_eq!(summary, [("one", Some(101.0), false), ("two", Some(102.0), false)]);
        assert!(places[0].2 >= first && places[1].2 >= second && !view.paused);
    }

    #[test]
    fn a_symlinked_dev_folder_is_never_listed() {
        let temp = Temp::new("linked");
        let (home, engine) = (temp.0.join("home"), temp.0.join("Epic Games"));
        write(&home.join("Documents/private/x"), 4096);
        std::os::unix::fs::symlink(home.join("Documents"), home.join("dev")).unwrap();
        let plan = Plan::new(&home, &engine, None, &mut || {});
        assert!(plan.places.iter().all(|place| !place.path.starts_with(home.join("dev"))), "{:?}", plan.places);
    }

    #[test]
    fn a_long_listing_can_pause_between_entries() {
        let temp = Temp::new("listing");
        for i in 0..50 {
            write(&temp.0.join(format!("f{i}")), 1);
        }
        let mut ticks = 0;
        measure(&temp.0, &HashSet::new(), &mut HashSet::new(), &mut |_| ticks += 1);
        assert!(ticks > 50, "{ticks}");
    }

    #[test]
    fn volumes_report_free_and_total_space() {
        let (free, total) = volume(&std::env::temp_dir()).unwrap();
        assert!(total > 0 && free <= total);
    }
}
