//! Pure cleanup policy over catalog facts, never filesystem or deletion authority.
//!
//! A future adapter must validate complete record metadata and acquire facts under the shared
//! store mutex, apply roots::may_reclaim, and reuse one deadline from acquisition through apply.
//! This module neither probes liveness nor reads, hashes, repairs, or removes any store file.
use crate::store::ObjectDigest;
use std::collections::{BTreeMap, BTreeSet};
use std::fmt;
use std::time::Instant;

pub const RECENT_GUARD_SECONDS: u64 = 24 * 60 * 60;

/// A durable use/grace bucket's upper bound, never payload mtime or production provenance.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Age {
    Unknown,
    UpperBound(u64),
}

#[derive(Clone, Debug)]
pub struct ResultFacts {
    pub key: String,
    pub upstream: BTreeSet<String>,
    /// Complete fixed, group and auxiliary membership, deduplicated by digest with checked sizes.
    pub objects: BTreeMap<String, u64>,
    pub age: Age,
}

#[derive(Clone, Debug)]
pub struct ObjectFacts {
    pub digest: String,
    pub size: u64,
    pub age: Age,
}

/// Caller-supplied metadata facts, not a complete/validated filesystem snapshot capability.
#[derive(Clone, Debug, Default)]
pub struct CatalogFacts {
    pub results: Vec<ResultFacts>,
    pub objects: Vec<ObjectFacts>,
}

/// Lease sets include every retained lease, as decided only by roots::may_reclaim upstream.
#[derive(Clone, Debug, Default)]
pub struct ProtectedFacts {
    pub roots: BTreeSet<String>,
    pub leased_results: BTreeSet<String>,
    pub leased_objects: BTreeSet<String>,
}

#[derive(Clone, Copy, Debug)]
pub struct PlanOptions {
    pub now_unix_seconds: u64,
    pub target_payload_bytes: u64,
    pub max_deletions: usize,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq, PartialOrd, Ord)]
pub enum RetainReason {
    Root,
    Lease,
    Recent,
    UnknownAge,
    FutureObservation,
    RequiredByRetainedConsumer,
    CyclicLineage,
    ReferencedByRemainingResult,
    UnresolvedLeaseLineage,
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub enum PolicyError {
    Deadline,
    InvalidDigest(String),
    DuplicateResult(String),
    DuplicateObject(String),
    MissingRoot(String),
    MissingProducer { consumer: String, producer: String },
    InconsistentSize(String),
    ByteCountOverflow,
}
impl fmt::Display for PolicyError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(formatter, "cleanup policy: {self:?}")
    }
}
impl std::error::Error for PolicyError {}

/// Diagnostic proposals only. No apply/delete API accepts this value as authority.
#[derive(Clone, Debug)]
pub struct CleanupPlan {
    pub logical_payload_bytes_before: u64,
    pub logical_payload_bytes_after: u64,
    pub target_payload_bytes: u64,
    /// A pure plan cannot measure physical APFS allocation or space actually freed.
    pub physical_bytes_freed: Option<u64>,
    pub result_deletions: Vec<String>,
    pub object_deletions: Vec<String>,
    pub remaining_results: BTreeSet<String>,
    pub remaining_objects: BTreeSet<String>,
    pub protected_results: BTreeMap<String, BTreeSet<RetainReason>>,
    pub protected_objects: BTreeMap<String, BTreeSet<RetainReason>>,
    pub missing_objects: BTreeSet<String>,
    /// Unpublished lease keys are normal, but unresolved lineage conservatively fences this plan.
    pub unresolved_lease_keys: BTreeSet<String>,
}
impl CleanupPlan {
    pub fn target_reached(&self) -> bool {
        self.logical_payload_bytes_after <= self.target_payload_bytes
    }
    fn actions(&self) -> usize {
        self.result_deletions.len() + self.object_deletions.len()
    }
    fn remove_object(&mut self, object: &ObjectFacts, options: PlanOptions) {
        if !self.target_reached()
            && self.actions() < options.max_deletions
            && !self.protected_objects.contains_key(&object.digest)
            && self.remaining_objects.remove(&object.digest)
        {
            self.logical_payload_bytes_after -= object.size;
            self.object_deletions.push(object.digest.clone());
        }
    }
}

fn valid(value: &str) -> Result<(), PolicyError> {
    ObjectDigest::from_hex(value)
        .map(|_| ())
        .map_err(|_| PolicyError::InvalidDigest(value.into()))
}
fn age_reason(age: Age, now: u64) -> Option<RetainReason> {
    match age {
        Age::Unknown => Some(RetainReason::UnknownAge),
        Age::UpperBound(upper) if upper > now => Some(RetainReason::FutureObservation),
        Age::UpperBound(upper) if now - upper < RECENT_GUARD_SECONDS => Some(RetainReason::Recent),
        Age::UpperBound(_) => None,
    }
}
fn order(age: Age) -> u64 {
    match age {
        Age::UpperBound(upper) => upper,
        Age::Unknown => u64::MAX,
    }
}
fn protect(map: &mut BTreeMap<String, BTreeSet<RetainReason>>, key: &str, reason: RetainReason) {
    map.entry(key.into()).or_default().insert(reason);
}

/// @cc [owner:fontanierh,label:correctness] cleanup-policy-is-not-deletion-authority
/// Planning MUST validate every supplied record reference before proposing any blob removal,
/// retain roots/leases/recent/unknown data and all producer ancestors, and never remove a producer
/// while a remaining consumer references it. One absolute deadline MUST cover validation and
/// planning without reset; timeout MUST return no plan. This pure result MUST NOT authorize disk
/// deletion, certify filesystem enumeration, claim physical space freed or bypass roots::may_reclaim.
pub fn plan_catalog(
    facts: &CatalogFacts,
    protected: &ProtectedFacts,
    options: PlanOptions,
    deadline: Instant,
) -> Result<CleanupPlan, PolicyError> {
    plan_with_clock(facts, protected, options, deadline, Instant::now)
}

fn plan_with_clock(
    facts: &CatalogFacts,
    protected: &ProtectedFacts,
    options: PlanOptions,
    deadline: Instant,
    mut clock: impl FnMut() -> Instant,
) -> Result<CleanupPlan, PolicyError> {
    let mut check = || {
        if clock() >= deadline {
            Err(PolicyError::Deadline)
        } else {
            Ok(())
        }
    };
    check()?;
    let mut objects = BTreeMap::new();
    let mut bytes = 0u64;
    for object in &facts.objects {
        check()?;
        valid(&object.digest)?;
        if objects.insert(object.digest.clone(), object).is_some() {
            return Err(PolicyError::DuplicateObject(object.digest.clone()));
        }
        bytes = bytes
            .checked_add(object.size)
            .ok_or(PolicyError::ByteCountOverflow)?;
    }
    let mut records = BTreeMap::new();
    let mut sizes = BTreeMap::new();
    let mut missing_objects = BTreeSet::new();
    for record in &facts.results {
        check()?;
        valid(&record.key)?;
        if records.insert(record.key.clone(), record).is_some() {
            return Err(PolicyError::DuplicateResult(record.key.clone()));
        }
        for (digest, size) in &record.objects {
            check()?;
            valid(digest)?;
            if sizes
                .insert(digest.clone(), *size)
                .is_some_and(|prior| prior != *size)
                || objects
                    .get(digest)
                    .is_some_and(|object| object.size != *size)
            {
                return Err(PolicyError::InconsistentSize(digest.clone()));
            }
            if !objects.contains_key(digest) {
                missing_objects.insert(digest.clone());
            }
        }
    }
    let mut incoming: BTreeMap<_, usize> = records.keys().map(|key| (key.clone(), 0)).collect();
    let mut references: BTreeMap<String, usize> = BTreeMap::new();
    for record in records.values() {
        check()?;
        for upstream in &record.upstream {
            check()?;
            valid(upstream)?;
            let count = incoming
                .get_mut(upstream)
                .ok_or_else(|| PolicyError::MissingProducer {
                    consumer: record.key.clone(),
                    producer: upstream.clone(),
                })?;
            *count += 1;
        }
        for digest in record.objects.keys() {
            check()?;
            *references.entry(digest.clone()).or_default() += 1;
        }
    }
    let mut plan = CleanupPlan {
        logical_payload_bytes_before: bytes,
        logical_payload_bytes_after: bytes,
        target_payload_bytes: options.target_payload_bytes,
        physical_bytes_freed: None,
        result_deletions: vec![],
        object_deletions: vec![],
        remaining_results: records.keys().cloned().collect(),
        remaining_objects: objects.keys().cloned().collect(),
        protected_results: BTreeMap::new(),
        protected_objects: BTreeMap::new(),
        missing_objects,
        unresolved_lease_keys: BTreeSet::new(),
    };
    for key in &protected.roots {
        check()?;
        valid(key)?;
        if !records.contains_key(key) {
            return Err(PolicyError::MissingRoot(key.clone()));
        }
        protect(&mut plan.protected_results, key, RetainReason::Root);
    }
    for key in &protected.leased_results {
        check()?;
        valid(key)?;
        if records.contains_key(key) {
            protect(&mut plan.protected_results, key, RetainReason::Lease);
        } else {
            plan.unresolved_lease_keys.insert(key.clone());
        }
    }
    for digest in &protected.leased_objects {
        check()?;
        valid(digest)?;
        protect(&mut plan.protected_objects, digest, RetainReason::Lease);
    }
    for record in records.values() {
        check()?;
        if let Some(reason) = age_reason(record.age, options.now_unix_seconds) {
            protect(&mut plan.protected_results, &record.key, reason);
        }
    }
    for object in objects.values() {
        check()?;
        if let Some(reason) = age_reason(object.age, options.now_unix_seconds) {
            protect(&mut plan.protected_objects, &object.digest, reason);
        }
    }
    // Kahn's remaining set includes cycles and their producer closure; retain it conservatively.
    let mut counts = incoming.clone();
    let mut ready: BTreeSet<_> = counts
        .iter()
        .filter(|(_, count)| **count == 0)
        .map(|(key, _)| key.clone())
        .collect();
    let mut acyclic = BTreeSet::new();
    while let Some(key) = ready.pop_first() {
        check()?;
        acyclic.insert(key.clone());
        for upstream in &records[&key].upstream {
            check()?;
            let count = counts.get_mut(upstream).unwrap();
            *count -= 1;
            if *count == 0 {
                ready.insert(upstream.clone());
            }
        }
    }
    for key in records.keys() {
        check()?;
        if !acyclic.contains(key) {
            protect(
                &mut plan.protected_results,
                key,
                RetainReason::CyclicLineage,
            );
        }
    }
    let mut pending: Vec<_> = plan.protected_results.keys().cloned().collect();
    let mut visited = BTreeSet::new();
    while let Some(key) = pending.pop() {
        check()?;
        if !visited.insert(key.clone()) {
            continue;
        }
        for upstream in &records[&key].upstream {
            check()?;
            protect(
                &mut plan.protected_results,
                upstream,
                RetainReason::RequiredByRetainedConsumer,
            );
            pending.push(upstream.clone());
        }
    }
    if !plan.unresolved_lease_keys.is_empty() {
        for key in records.keys() {
            check()?;
            protect(
                &mut plan.protected_results,
                key,
                RetainReason::UnresolvedLeaseLineage,
            );
        }
        for key in objects.keys() {
            check()?;
            protect(
                &mut plan.protected_objects,
                key,
                RetainReason::UnresolvedLeaseLineage,
            );
        }
    } else {
        // Existing orphan blobs can satisfy the budget without losing useful result metadata.
        let mut orphans = BTreeSet::new();
        for object in objects.values() {
            check()?;
            if references.get(&object.digest).copied().unwrap_or_default() == 0 {
                orphans.insert((order(object.age), object.digest.clone()));
            }
        }
        for (_, digest) in orphans {
            check()?;
            plan.remove_object(objects[&digest], options);
        }
        let mut eligible = BTreeSet::new();
        for (key, count) in &incoming {
            check()?;
            if *count == 0 && !plan.protected_results.contains_key(key) {
                eligible.insert((order(records[key].age), key.clone()));
            }
        }
        while !plan.target_reached() && plan.actions() < options.max_deletions {
            check()?;
            let Some((_, key)) = eligible.pop_first() else {
                break;
            };
            plan.remaining_results.remove(&key);
            plan.result_deletions.push(key.clone());
            for upstream in &records[&key].upstream {
                check()?;
                let count = incoming.get_mut(upstream).unwrap();
                *count -= 1;
                if *count == 0 && !plan.protected_results.contains_key(upstream) {
                    eligible.insert((order(records[upstream].age), upstream.clone()));
                }
            }
            let mut orphaned = BTreeSet::new();
            for digest in records[&key].objects.keys() {
                check()?;
                let count = references.get_mut(digest).unwrap();
                *count -= 1;
                if *count == 0
                    && let Some(object) = objects.get(digest)
                {
                    orphaned.insert((order(object.age), digest.clone()));
                }
            }
            for (_, digest) in orphaned {
                check()?;
                plan.remove_object(objects[&digest], options);
            }
        }
    }
    for (digest, count) in references {
        check()?;
        if count > 0 && plan.remaining_objects.contains(&digest) {
            protect(
                &mut plan.protected_objects,
                &digest,
                RetainReason::ReferencedByRemainingResult,
            );
        }
    }
    check()?;
    Ok(plan)
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::time::Duration;

    #[test]
    fn deadline_covers_validation_and_planning_without_returning_partial_authority() {
        let facts = CatalogFacts {
            objects: (0..100)
                .map(|value| ObjectFacts {
                    digest: format!("{value:064x}"),
                    size: 1,
                    age: Age::UpperBound(0),
                })
                .collect(),
            ..Default::default()
        };
        let start = Instant::now();
        let mut ticks = 0;
        let result = plan_with_clock(
            &facts,
            &ProtectedFacts::default(),
            PlanOptions {
                now_unix_seconds: RECENT_GUARD_SECONDS,
                target_payload_bytes: 0,
                max_deletions: 100,
            },
            start + Duration::from_nanos(5),
            || {
                ticks += 1;
                start + Duration::from_nanos(ticks)
            },
        );
        assert!(matches!(result, Err(PolicyError::Deadline)));
    }
}
