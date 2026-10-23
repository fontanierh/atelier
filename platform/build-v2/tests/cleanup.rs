use atelier_build_v2::cleanup::*;
use std::collections::{BTreeMap, BTreeSet};
use std::time::{Duration, Instant};

const NOW: u64 = 10 * RECENT_GUARD_SECONDS;
fn key(value: u64) -> String {
    format!("{value:064x}")
}
fn object(value: u64, size: u64, age: Age) -> ObjectFacts {
    ObjectFacts {
        digest: key(value),
        size,
        age,
    }
}
fn result(value: u64, upstream: &[u64], objects: &[(u64, u64)], age: Age) -> ResultFacts {
    ResultFacts {
        key: key(value),
        upstream: upstream.iter().map(|value| key(*value)).collect(),
        objects: objects
            .iter()
            .map(|(digest, size)| (key(*digest), *size))
            .collect(),
        age,
    }
}
fn plan(
    facts: &CatalogFacts,
    protected: &ProtectedFacts,
    target: u64,
    limit: usize,
) -> CleanupPlan {
    plan_catalog(
        facts,
        protected,
        PlanOptions {
            now_unix_seconds: NOW,
            target_payload_bytes: target,
            max_deletions: limit,
        },
        Instant::now() + Duration::from_secs(1),
    )
    .unwrap()
}

#[test]
fn retained_consumers_keep_transitive_producers_and_shared_auxiliary_objects() {
    let old = Age::UpperBound(0);
    let facts = CatalogFacts {
        results: vec![
            result(1, &[2], &[(11, 10)], old),
            result(2, &[3], &[(12, 20)], old),
            result(3, &[], &[(13, 30)], old),
            result(4, &[], &[(11, 10), (14, 40)], old),
        ],
        objects: vec![
            object(11, 10, old),
            object(12, 20, old),
            object(13, 30, old),
            object(14, 40, old),
        ],
    };
    let protected = ProtectedFacts {
        roots: BTreeSet::from([key(1)]),
        ..Default::default()
    };
    let report = plan(&facts, &protected, 0, 100);
    assert_eq!(report.result_deletions, vec![key(4)]);
    assert_eq!(report.object_deletions, vec![key(14)]);
    assert_eq!(report.logical_payload_bytes_before, 100);
    assert_eq!(report.logical_payload_bytes_after, 60);
    assert_eq!(
        report.remaining_results,
        BTreeSet::from([key(1), key(2), key(3)])
    );
    assert!(report.protected_results[&key(3)].contains(&RetainReason::RequiredByRetainedConsumer));
    assert!(!report.target_reached());
    assert_eq!(report.physical_bytes_freed, None);
}

#[test]
fn oldest_eligible_result_never_precedes_its_still_kept_consumer() {
    let old = Age::UpperBound(0);
    let facts = CatalogFacts {
        results: vec![
            result(1, &[], &[(11, 10)], old),
            result(2, &[1], &[(12, 20)], Age::UpperBound(100)),
            result(3, &[], &[(13, 30)], Age::UpperBound(50)),
        ],
        objects: vec![
            object(11, 10, old),
            object(12, 20, old),
            object(13, 30, old),
        ],
    };
    let report = plan(&facts, &ProtectedFacts::default(), 0, 100);
    assert_eq!(report.result_deletions, vec![key(3), key(2), key(1)]);
    assert_eq!(report.object_deletions, vec![key(13), key(12), key(11)]);
    assert!(report.target_reached());
    let bounded = plan(&facts, &ProtectedFacts::default(), 0, 1);
    assert_eq!(bounded.result_deletions, vec![key(3)]);
    assert!(bounded.object_deletions.is_empty());
    assert_eq!(bounded.logical_payload_bytes_after, 60);
}

#[test]
fn recent_unknown_and_future_observations_never_expire_early() {
    let cutoff = NOW - RECENT_GUARD_SECONDS;
    let facts = CatalogFacts {
        results: vec![],
        objects: vec![
            object(1, 1, Age::UpperBound(cutoff)),
            object(2, 2, Age::UpperBound(cutoff + 1)),
            object(3, 3, Age::Unknown),
            object(4, 4, Age::UpperBound(NOW + 1)),
        ],
    };
    let report = plan(&facts, &ProtectedFacts::default(), 0, 100);
    assert_eq!(report.object_deletions, vec![key(1)]);
    assert_eq!(
        report.protected_objects[&key(2)],
        BTreeSet::from([RetainReason::Recent])
    );
    assert_eq!(
        report.protected_objects[&key(3)],
        BTreeSet::from([RetainReason::UnknownAge])
    );
    assert_eq!(
        report.protected_objects[&key(4)],
        BTreeSet::from([RetainReason::FutureObservation])
    );
    assert_eq!(report.logical_payload_bytes_after, 9);
    // A recent consumer also protects an old producer through complete lineage.
    let facts = CatalogFacts {
        results: vec![
            result(1, &[2], &[], Age::UpperBound(cutoff + 1)),
            result(2, &[], &[(5, 5)], Age::UpperBound(0)),
        ],
        objects: vec![object(5, 5, Age::UpperBound(0))],
    };
    assert!(
        plan(&facts, &ProtectedFacts::default(), 0, 100)
            .result_deletions
            .is_empty()
    );
}

#[test]
fn lease_facts_are_protection_not_liveness_or_cleanup_decisions() {
    let old = Age::UpperBound(0);
    let facts = CatalogFacts {
        results: vec![result(1, &[], &[(11, 10)], old)],
        objects: vec![object(11, 10, old), object(12, 20, old)],
    };
    let protected = ProtectedFacts {
        leased_results: BTreeSet::from([key(1)]),
        leased_objects: BTreeSet::from([key(12)]),
        ..Default::default()
    };
    let report = plan(&facts, &protected, 0, 100);
    assert!(report.result_deletions.is_empty() && report.object_deletions.is_empty());
    assert!(report.protected_results[&key(1)].contains(&RetainReason::Lease));
    // A pre-publication lease key is valid but cannot be guessed to have no producers.
    let unresolved = ProtectedFacts {
        leased_results: BTreeSet::from([key(99)]),
        ..Default::default()
    };
    let report = plan(&facts, &unresolved, 0, 100);
    assert_eq!(report.unresolved_lease_keys, BTreeSet::from([key(99)]));
    assert!(report.result_deletions.is_empty() && report.object_deletions.is_empty());
    assert!(report.protected_objects[&key(12)].contains(&RetainReason::UnresolvedLeaseLineage));
}

#[test]
fn every_record_reference_is_validated_before_any_proposal() {
    let old = Age::UpperBound(0);
    let facts = CatalogFacts {
        results: vec![result(1, &[99], &[], old)],
        objects: vec![object(11, 10, old)],
    };
    let options = PlanOptions {
        now_unix_seconds: NOW,
        target_payload_bytes: 0,
        max_deletions: 100,
    };
    assert!(matches!(
        plan_catalog(
            &facts,
            &ProtectedFacts::default(),
            options,
            Instant::now() + Duration::from_secs(1)
        ),
        Err(PolicyError::MissingProducer { .. })
    ));
    let facts = CatalogFacts {
        results: vec![result(1, &[], &[(11, 9)], old)],
        objects: vec![object(11, 10, old)],
    };
    assert!(matches!(
        plan_catalog(
            &facts,
            &ProtectedFacts::default(),
            options,
            Instant::now() + Duration::from_secs(1)
        ),
        Err(PolicyError::InconsistentSize(_))
    ));
    let protected = ProtectedFacts {
        roots: BTreeSet::from([key(99)]),
        ..Default::default()
    };
    assert!(matches!(
        plan_catalog(
            &CatalogFacts::default(),
            &protected,
            options,
            Instant::now() + Duration::from_secs(1)
        ),
        Err(PolicyError::MissingRoot(_))
    ));
}

#[test]
fn cyclic_lineage_and_missing_payloads_are_honest_non_deletion_cases() {
    let old = Age::UpperBound(0);
    let facts = CatalogFacts {
        results: vec![
            result(1, &[2], &[(11, 10)], old),
            result(2, &[1, 3], &[(12, 20)], old),
            result(3, &[], &[(13, 30)], old),
            result(4, &[], &[(14, 40)], old),
        ],
        objects: vec![
            object(11, 10, old),
            object(13, 30, old),
            object(14, 40, old),
        ],
    };
    let report = plan(&facts, &ProtectedFacts::default(), 0, 100);
    assert_eq!(report.result_deletions, vec![key(4)]);
    assert_eq!(report.object_deletions, vec![key(14)]);
    assert_eq!(report.missing_objects, BTreeSet::from([key(12)]));
    assert!(report.protected_results[&key(3)].contains(&RetainReason::CyclicLineage));
    assert_eq!(report.logical_payload_bytes_after, 40);
}

#[test]
fn logical_dedup_budget_and_orphan_grace_do_not_claim_physical_reclaim() {
    let old = Age::UpperBound(0);
    let facts = CatalogFacts {
        results: vec![
            result(1, &[], &[(11, 10)], old),
            result(2, &[], &[(11, 10)], old),
        ],
        objects: vec![
            object(11, 10, old),
            object(12, 20, old),
            object(13, 30, Age::Unknown),
        ],
    };
    let report = plan(&facts, &ProtectedFacts::default(), 40, 100);
    assert_eq!(report.object_deletions, vec![key(12)]);
    assert!(report.result_deletions.is_empty());
    assert_eq!(report.logical_payload_bytes_before, 60);
    assert_eq!(report.logical_payload_bytes_after, 40);
    assert_eq!(report.physical_bytes_freed, None);
    let report = plan(&facts, &ProtectedFacts::default(), 0, 100);
    assert_eq!(report.result_deletions, vec![key(1), key(2)]);
    assert_eq!(report.object_deletions, vec![key(12), key(11)]);
    assert_eq!(report.remaining_objects, BTreeSet::from([key(13)]));
    assert_eq!(report.logical_payload_bytes_after, 30);
    assert!(!report.target_reached());
}

#[test]
fn malformed_duplicate_overflow_and_expired_catalogs_refuse() {
    let old = Age::UpperBound(0);
    let options = PlanOptions {
        now_unix_seconds: NOW,
        target_payload_bytes: 0,
        max_deletions: 100,
    };
    let run = |facts: &CatalogFacts| {
        plan_catalog(
            facts,
            &ProtectedFacts::default(),
            options,
            Instant::now() + Duration::from_secs(1),
        )
    };
    assert!(matches!(
        run(&CatalogFacts {
            objects: vec![object(1, 1, old), object(1, 1, old)],
            ..Default::default()
        }),
        Err(PolicyError::DuplicateObject(_))
    ));
    assert!(matches!(
        run(&CatalogFacts {
            results: vec![result(1, &[], &[], old), result(1, &[], &[], old)],
            ..Default::default()
        }),
        Err(PolicyError::DuplicateResult(_))
    ));
    assert!(matches!(
        run(&CatalogFacts {
            objects: vec![object(1, u64::MAX, old), object(2, 1, old)],
            ..Default::default()
        }),
        Err(PolicyError::ByteCountOverflow)
    ));
    let mut invalid = object(1, 1, old);
    invalid.digest = "../outside".into();
    assert!(matches!(
        run(&CatalogFacts {
            objects: vec![invalid],
            ..Default::default()
        }),
        Err(PolicyError::InvalidDigest(_))
    ));
    assert!(matches!(
        plan_catalog(
            &CatalogFacts::default(),
            &ProtectedFacts::default(),
            options,
            Instant::now()
        ),
        Err(PolicyError::Deadline)
    ));
    // An absent payload is not fabricated as present or counted as bytes.
    let report = run(&CatalogFacts {
        results: vec![ResultFacts {
            key: key(1),
            upstream: BTreeSet::new(),
            objects: BTreeMap::from([(key(11), 9)]),
            age: old,
        }],
        objects: vec![],
    })
    .unwrap();
    assert_eq!(report.logical_payload_bytes_before, 0);
    assert_eq!(report.missing_objects, BTreeSet::from([key(11)]));
}
