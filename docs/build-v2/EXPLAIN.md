# Build v2 summaries and reasons

**Retired experiment.** This page describes `platform/build-v2`, not Yorimichi V2. Its tests are disabled,
and the roadmap items below are historical, not current development requirements. Use the
[active game guide](../../games/yorimichi_v2/README.md) for normal authoring, builds and tests.

The unused library's `explain` module records why work was reused or requested. It does not change
normal build output or provide a new command. Wiring `why`, cache reports and normal CLI summaries
belongs to I2/I1.

Create one `Recorder` per scheduler invocation, wrap the existing backend and executor, then read the
observations after `scheduler::run` returns:

```rust,ignore
let recorder = Recorder::default();
let report = scheduler::run(request, &mut recorder.backend(&mut backend),
    &mut recorder.executor(&mut executor), control, hashes)?;
let summary = recorder.summarize(&report, &previous_ingredients,
    Some(&backend.io().launches_by_unit))?;
```

This pattern borrows the same backend, tickets and executor. It adds no cache lookup, source read,
payload hash, tree discovery, staging or restoration. The recorder holds no `PreparedUnit`, file
descriptors, leases, pins or payload bytes. Its compact fingerprints hash only the original prepared
ingredient metadata with A3's canonical encoding; they are diagnostic data, not another cache key.

Each unit reports its diagnostic scheduling label, prepared key, lookup decision, final outcome,
submission and completion counts, cache publication, confirmed restore/install/receipt effects and
unsatisfied explicit final demands. Labels do not enter ingredient comparisons. A consumer hit needs
only ancestor identities: an identity observation is neither an executed unit nor a restored hit.
Pruned/unselected units are absent; they are not counted as successes.
A backend's rejected hit claim remains visible in `lookup`, but does not increase accepted hit counts.

| Observation | Meaning |
|---|---|
| `current` | The backend certified Current; no successful restore or receipt write was reported. |
| `identity_only` | Metadata resolved an internal prerequisite; no byte availability is asserted. |
| `stored_hit` | The typed cached-hit decision. Reuse counts require scheduler acceptance; restoration also requires confirmed installation effects. |
| `executed` | A completion was published or retained locally and final settlement succeeded. |
| `cached` / `not_cached` | The backend reported successful cache publication or validated local completion without cache success. Explicit Stored may remain unsatisfied. |
| `attempted_unknown` | Publication returned an error or mismatched checked key; this does not prove nothing reached the store. |
| missing/corrupt/unsupported reason | The original typed lookup fact. A missing record or blob does not prove eviction. |
| source unavailable/changed/invalid | Conditional staging refused before dispatch. Original miss evidence is retained separately. |

Submission is not a launch. `launched_attempts` counts worker identities reported by the existing
guard's `ChildStarted` event, once per lifecycle attempt including retries; it does not count
successful Runs. Generic executors without such evidence return `null`. Missing reports, uncertain
cleanup or admission without a pinned child also leave the relevant unit and aggregate unknown,
rather than claiming zero. A confirmed failed submission with no child can prove zero. No-op builds
have no submitted work and can prove zero from an empty complete evidence map.

Completion, cache success, installation and final failure are separate facts. A later independent
failure retains earlier success counts. A successful publication followed by settlement failure
remains a cached publication and a failed unit; `effects_complete = false` warns that only confirmed
returned effects are counted. `executor_fatal` reports the scheduler's fatal executor boundary,
without inferring that a child launched or cleanup was uncertain. The summary rejects
inconsistent prepared keys, duplicate terminal events, foreign launch labels and mismatched effects.
It does not reinterpret free-form backend errors or copy them into serialized output.

This is a summary of `scheduler::run`, not a certificate of overall build success. Concrete
`finish()` root/release calls run outside these traits: callers must retain their separate outcome,
sample actual I/O after finish, and never erase valid per-unit work because finalization failed.
`effects_complete` concerns observed scheduler settlement, not arbitrary finalization or all I/O.

For ingredient reasons, retain `recorder.ingredients()` and supply that compact baseline on a later
invocation. A missing baseline yields `ingredient_changes: null`, not an invented change. An unchanged
baseline yields an empty list. A caller renaming a scheduling label must explicitly match the old
observation by its stable logical owner; the recorder never guesses this relation. The comparison
reports only changed categories and declared code paths/slot names: versions, op, entrypoint, code,
worker, validator, parameters, selected content, references, staged paths, input shapes and output
contracts. It exposes no values. Changed producer input keys alone do not explain a consumer rebuild
when its selected output content is unchanged. Installed tools, checkout/branch/commit/dirty state
and source provenance are not ingredients and cannot manufacture a cause.

Linux T0 tests reuse the actual scheduler and its existing deterministic backend/executor fixture to
check first/no-op/mixed runs, restoration, output cutoff, typed missing-object refusal, local output
feeding downstream and partial success. These fixture counters are not native launch evidence.
Existing real sandbox/APFS backend fixtures also compare these summaries against actual Python I/O
counters. Those changed macOS assertions are **MAC1 pending**, not development-CI passes. Actual
guarded production custody, dynamic scheduling, A6 edit fencing, native workers and CLI cutover remain
separate acceptance work.
