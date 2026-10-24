# Dormant legacy operational epoch

`platform/build-v2/src/legacy_epoch.rs` implements a private control-state machine. It is not
connected to the legacy caller, a repair command, Python startup, checkpoint writer custody,
or native launch. Production qualification returns `Unsupported`: there is no production
plan/evidence issuer. A separately reviewed finite adapter must establish source/plan,
closed write ownership, replay/restore qualification, real cleanup and finalization before
it can issue the private capabilities. Raw JSON, public report fields and booleans cannot.

The record is `build/build-v2/install/legacy-epoch.json`, version 1, bounded to 256 KiB,
64 tasks, 16 roots and 256 attempts. It binds checkout device/inode, project, roots,
source-plan and ownership digests, optional checked order fulfillment, exact tasks,
pending/settled membership and attempt intents. These are operational bindings; they are
not task keys, content identities, installed-platform fingerprints or result authority.
Records reject duplicate/unknown fields, positional records, aliases, invalid paths,
inconsistent task membership and unsupported versions. The decoder is never a qualifier.
Qualification requires at least one fresh source witness; an empty witness set cannot validate
even a fixture plan. This unit adds Rust admission fences only. Python/v1 reader and producer
admission integration remains an activation gate.

Begin holds real same-checkout build and exclusive content guards and publishes all pending
tasks without replacing an existing name, with file and parent fsync. Every transition checks
the exact prior record/inode and live source observations, persists a candidate, then updates
memory. Attempt intents precede work. Settlement requires private freshly validated evidence;
old pre-epoch stamps cannot settle an interrupted task. Repair requires the exact unchanged
plan/root/source and positive cleanup evidence for every recorded attempt. It returns explicit
closed-replay or verified-restore demands for pending tasks, and revalidation demands for
settled independent tasks. Revalidation can durably put failed tasks back in pending before
mutation while preserving valid independent results. No force, time expiry, deletion shortcut,
scope retagging or automatic adoption is provided.

Finish requires no pending work, matching fresh settlements, source/output observations,
cleanup and separately qualified finalization. It persists verified-complete, rechecks fresh
observations, then removes only the exact owned marker and fsyncs the parent. A crash before
removal remains fenced even if the record says verified-complete; fresh verification is still
required to resume. Drop does not clear the barrier. This describes process-interruption
fencing, not arbitrary legacy rollback or power-loss durability of native output writers.

Shared reader admission checks marker presence after taking SH. Any entry, including a link,
directory or malformed record, fences. Default install/recovery/completion preflight and EX
admission also refuse it. Absence creates no epoch and preserves the existing v2-only path.
The private already-EX receipt observation requires the exact active/repair permit and actual
guards, retains the separate B3 install-journal blocker, and reuses `current_locked`. It does
not reacquire SH or authorize a v2 install inside a legacy epoch.

The private fresh-exec custody pair requires actual matching build and EX guards and duplicates
both SAME open file descriptions with atomic CLOEXEC. It never changes inheritable flags,
adopts FDs, unlocks or launches. Existing public build-guard duplication stays monitor-only.
The future bootstrap, checkpoint writer's third SAME-OFD handle, child/external-reader coverage
and source-update rules are separate integration obligations.
The guards retain their original directory anchor across `CheckoutLocks` clones. Pair issuance
checks that anchor and both current named lock inodes against the original held descriptors;
same-path root or lock replacement cannot supply new authority.
The pair's file fields are private and it exposes no raw-FD/pass-fd conversion. A future
bootstrap/custodian consumer requires separate review; ordinary worker dispatch cannot extract it.

Hosted portable scenarios exercise real control files, fsync transitions, record replacement,
source/output drift, drop/resume cuts and actual flock description custody. The test-only
issuer validates a concrete fixed-file copy fixture and synthetic positive cleanup metadata;
it does not qualify arbitrary `Step`, `Call`, native writes, replans or a production plan.
No native process or compiler runs in these tests. Actual platform/parent-death child custody,
ordinary repair CLI, full mixed/default support and activation remain pending.
