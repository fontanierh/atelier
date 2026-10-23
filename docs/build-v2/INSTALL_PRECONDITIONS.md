# Install precondition and fault evidence

`RestorePlan::commit_with` is nonblocking. It acquires exclusive content custody before creating
the install journal. A live shared reader can therefore return `InstallError::Lock(Busy)` before
any transaction starts. The old checkout stays readable and no journal is created. This is a
precondition refusal, not evidence that a failed transaction lost its barrier.

Once `JournalCreated` has run, an injected failure must leave its durable journal. Shared reader
admission then returns `RecoveryRequired` until exclusive recovery succeeds. Dropping the temporary
writer guard does not clear that journal barrier. The existing BSD `flock` locks are associated with
their open file description, not POSIX `fcntl` per-process record locks; guards never issue
`LOCK_UN`, and closing an unrelated descriptor does not release a live guard.

The portable regression uses a valid required-file cache fixture: known bytes under their SHA-256
name and a matching read-only result record, following the existing result-store test setup. The
real strict B2 lookup issues the private install plan and lease. No publication, payload snapshot or
APFS clone is fabricated. With the prior empty index state and a foreign neighbor preserved, it holds
a real shared reader, proves the exact pre-journal `Busy` error and then releases that reader and
injects the exact `JournalCreated` failure, before cloning starts. It checks the hook, durable journal,
reader refusal, unchanged index and lease, preserved object/record/neighbor bytes and real recovery.

The first fixture proposal with all optional files absent was invalid: A2 requires at least one
required file per item. Hosted validation rejected it before install logic. That failed run is not
custody evidence, and neither the validator nor the production code is relaxed to accommodate it.

The APFS `CloneCreated` test now requires its fault hook, exact injected I/O error and journal to
exist before asserting reader exclusion. An arbitrary earlier error cannot stand in for this cut.
The original whole-binary-only report did not capture the error or whether the hook ran. Its cause
remains unclassified; missing historical evidence cannot be recovered by a later test. A precondition
refusal explains the source-level sequence but is not a proven diagnosis of that run. There is no
new evidence of product custody loss and no product locking change.

Linux proves the precondition and metadata-journal boundaries. The actual post-clone cut is still
macOS/APFS coverage deferred to MAC1; it is not reproduced by a local Mac run or relabelled portable
coverage. This diagnostic PR can complete with portable proof; installer functional/cut acceptance
and activation remain pending the revised actual APFS cut at MAC1. That future test will establish
the intended cut behavior and capture the exact error, hook and journal for any new failure; it
cannot retroactively classify the old run. No earlier local Mac gate, retry loop, sleep or whole-suite
serialization is added.
