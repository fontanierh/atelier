//! A6 live raw-source fencing for units that are still tentative at dispatch.
//!
//! Capture (@see python_sources::capture_sources) owns the bytes and stat hints that feed
//! keys::prepare; staging never rereads live files. This module re-observes the live names a
//! tentative unit consumed, before its first key-specific lookup or ticket, so an edit before the
//! fence re-prepares only the affected units and an edit after it belongs to the next build.
//! Comparison uses bytes and entry kind, never a FileVersion hint alone, and absence is a missing
//! snapshot entry rather than an entry variant.
use crate::keys::{PreparedUnit, SourceVersions};
use crate::python_sources::{CapturedSources, capture_sources};
use crate::source_hashes::FileVersion;
use crate::validate::{SnapshotEntry, SourceSnapshot};
use std::collections::BTreeSet;
use std::path::PathBuf;

/// Re-prepare attempts allowed per unit per build before it fails as source-unstable.
pub const MAX_REPREPARES: u32 = 3;

/// The captured observation of exactly the names one unit's key consumed, bound to the anchored
/// capture root. Construct through the capture constructor; no ambient-directory fallback exists.
#[derive(Clone, Debug)]
pub struct SourceFence {
    capture_root: PathBuf,
    scope: BTreeSet<String>,
    snapshot: SourceSnapshot,
    versions: SourceVersions,
}

/// A unit and the capture it was keyed from, until its dispatch mints miss work.
#[derive(Clone, Debug)]
pub struct TentativeSources {
    keyed: PreparedUnit,
    fence: SourceFence,
}

/// Outcome of one pre-dispatch revalidation.
#[derive(Clone, Debug, PartialEq, Eq)]
pub enum Fence {
    Unchanged,
    Changed { names: BTreeSet<String> },
}

impl SourceFence {
    /// @cc [owner:fontanierh,label:correctness] build-v2-live-source-fence
    /// A6 MUST revalidate live bytes and entry kinds for every name a tentative unit consumed -
    /// data inputs, its declared code closure and the three Python worker files - before its first
    /// key-specific lookup or ticket, using the same anchored root as the capture. A FileVersion
    /// alone MUST NOT prove equality; a version-only touch MUST NOT re-key, and a missing snapshot
    /// entry is absence. A real change MUST re-prepare the affected unit with a fresh
    /// SourceHashCache, new work and, for worker sources, a reconstructed frozen worker bundle and
    /// identity; old work MUST NOT be retagged. At most three re-prepares per unit per build are
    /// allowed before a deterministic source-unstable failure. See src/source_fence.rs.
    pub fn capture(
        capture_root: PathBuf,
        scope: BTreeSet<String>,
        captured: CapturedSources,
    ) -> Self {
        Self {
            capture_root,
            scope,
            snapshot: captured.snapshot,
            versions: captured.versions,
        }
    }

    pub fn capture_root(&self) -> &std::path::Path {
        &self.capture_root
    }

    pub fn scope(&self) -> &BTreeSet<String> {
        &self.scope
    }

    /// Re-observe the same names through the anchored provider and compare.
    pub fn revalidate(&self) -> Result<Fence, String> {
        let live = capture_sources(&self.capture_root, self.scope.iter().map(String::as_str))?;
        Ok(self.compare(&live))
    }

    /// Pure comparison against an already captured observation; used by revalidate and tests.
    pub fn compare(&self, live: &CapturedSources) -> Fence {
        let mut names = self.scope.clone();
        names.extend(self.snapshot.keys().cloned());
        names.extend(self.versions.keys().cloned());
        names.extend(live.snapshot.keys().cloned());
        names.extend(live.versions.keys().cloned());
        let changed: BTreeSet<String> = names
            .into_iter()
            .filter(|name| differs(self, live, name))
            .collect();
        if changed.is_empty() {
            Fence::Unchanged
        } else {
            Fence::Changed { names: changed }
        }
    }
}

impl TentativeSources {
    pub fn new(keyed: PreparedUnit, fence: SourceFence) -> Self {
        Self { keyed, fence }
    }

    pub fn keyed(&self) -> &PreparedUnit {
        &self.keyed
    }

    pub fn fence(&self) -> &SourceFence {
        &self.fence
    }

    /// Run before the first key-specific lookup (Backend.lookup / ResultStore) and before any
    /// miss ticket is minted.
    pub fn revalidate(&self) -> Result<Fence, String> {
        self.fence.revalidate()
    }
}

/// One build-scoped budget for pre-dispatch re-prepares of a single unit.
#[derive(Debug, Default)]
pub struct ReprepareBudget {
    used: u32,
}

impl ReprepareBudget {
    pub fn new() -> Self {
        Self::default()
    }

    /// Consume one attempt; false means the unit must fail as source-unstable.
    pub fn try_consume(&mut self) -> bool {
        if self.used >= MAX_REPREPARES {
            return false;
        }
        self.used += 1;
        true
    }

    pub fn used(&self) -> u32 {
        self.used
    }
}

/// Stable unit-failure text naming every changed source.
pub fn source_unstable(names: &BTreeSet<String>) -> String {
    let names: Vec<&str> = names.iter().map(String::as_str).collect();
    format!("source-unstable: {}", names.join(", "))
}

fn differs(fence: &SourceFence, live: &CapturedSources, name: &str) -> bool {
    match (fence.snapshot.get(name), live.snapshot.get(name)) {
        (None, None) => false,
        (Some(SnapshotEntry::File(before)), Some(SnapshotEntry::File(after))) => {
            // Bytes are identity; a version-only change with equal bytes does not re-key.
            before != after
        }
        (Some(SnapshotEntry::Directory), Some(SnapshotEntry::Directory)) => false,
        (Some(SnapshotEntry::Symlink), Some(SnapshotEntry::Symlink)) => false,
        (Some(SnapshotEntry::Unreadable), Some(SnapshotEntry::Unreadable)) => false,
        _ => true,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn captured(files: &[(&str, &[u8])]) -> CapturedSources {
        let mut captured = CapturedSources::default();
        for (name, bytes) in files {
            captured
                .snapshot
                .insert((*name).into(), SnapshotEntry::File(bytes.to_vec()));
            captured.versions.insert(
                (*name).into(),
                FileVersion {
                    device: 1,
                    inode: 2,
                    size: bytes.len() as u64,
                    mtime_ns: 10,
                    ctime_ns: 10,
                },
            );
        }
        captured
    }

    fn scope(names: &[&str]) -> BTreeSet<String> {
        names.iter().map(|name| (*name).into()).collect()
    }

    fn names(values: &[&str]) -> BTreeSet<String> {
        scope(values)
    }

    fn fence(scope: BTreeSet<String>, captured: CapturedSources) -> SourceFence {
        SourceFence::capture(PathBuf::from("/not-read-by-compare"), scope, captured)
    }

    #[test]
    fn unchanged_bytes_do_not_rekey_even_when_the_version_moved() {
        let fence = fence(scope(&["a"]), captured(&[("a", b"same")]));
        let mut live = captured(&[("a", b"same")]);
        live.versions.get_mut("a").unwrap().mtime_ns = 99;
        assert_eq!(fence.compare(&live), Fence::Unchanged);
    }

    #[test]
    fn same_size_rewrite_is_changed_because_bytes_differ() {
        let fence = fence(scope(&["a"]), captured(&[("a", b"aaaa")]));
        let live = captured(&[("a", b"bbbb")]);
        assert_eq!(
            fence.compare(&live),
            Fence::Changed {
                names: names(&["a"])
            }
        );
    }

    #[test]
    fn an_absent_name_that_appears_is_changed() {
        let fence = fence(scope(&["new"]), captured(&[]));
        let live = captured(&[("new", b"x")]);
        assert_eq!(
            fence.compare(&live),
            Fence::Changed {
                names: names(&["new"])
            }
        );
    }

    #[test]
    fn every_non_file_entry_kind_fences() {
        for entry in [
            SnapshotEntry::Directory,
            SnapshotEntry::Symlink,
            SnapshotEntry::Unreadable,
        ] {
            let mut before = CapturedSources::default();
            before.snapshot.insert("a".into(), entry);
            let fence = fence(scope(&["a"]), before);
            let live = captured(&[("a", b"file")]);
            assert_eq!(
                fence.compare(&live),
                Fence::Changed {
                    names: names(&["a"])
                }
            );
        }
    }

    #[test]
    fn a_new_name_outside_the_old_scope_is_changed() {
        let fence = fence(scope(&["a"]), captured(&[("a", b"a")]));
        let live = captured(&[("a", b"a"), ("b", b"b")]);
        assert_eq!(
            fence.compare(&live),
            Fence::Changed {
                names: names(&["b"])
            }
        );
    }

    #[test]
    fn the_reprepare_budget_fails_on_the_fourth_change() {
        let mut budget = ReprepareBudget::new();
        assert!(budget.try_consume());
        assert!(budget.try_consume());
        assert!(budget.try_consume());
        assert!(!budget.try_consume());
        assert_eq!(budget.used(), MAX_REPREPARES);
        assert_eq!(
            source_unstable(&names(&["a", "b"])),
            "source-unstable: a, b"
        );
    }
}
