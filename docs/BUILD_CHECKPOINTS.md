# Build checkpoints

Use the normal commands. There is no separate fast-build command and no Git-revision equality requirement:

```sh
uv sync
uv run atelier fetch yorimichi
ATELIER_AGENT=OWNER nice -n 10 uv run atelier build yorimichi
```

Set the private GitHub repository once on each machine:

```sh
uv run atelier cache configure --repository OWNER/REPOSITORY
```

Authenticate `gh` with access to that private repository first. The address is stored in a mode-0600 file
under the machine cache, outside the checkout. Never put it in game.toml, documentation or a PR.
This command verifies privacy and does not invite collaborators. Each developer can configure their own repository.

## What is reused

A task result is identified by its actual declared inputs, consumed products, command, installed tools,
engine and complete output declarations. The Git commit is provenance, not a lookup condition. Normal builds
look for matching task results locally and in every published private checkpoint, including in warm worktrees,
before batching or launching native work. Source edits remain untouched. Restored files are independent copies.
An unchanged task can be reused after unrelated changes or after reverting to older inputs.

A result needs a complete output inventory. Named products provide this; `checkpoint_outputs` can declare
additional complete, disjoint generated roots. Compiled editor targets also check their target receipt and required
module/plugin binaries. Producer tool keys and complete inventory identities are retained in success stamps. Missing or corrupted outputs
invalidate a previous stamp. Existing bytes cannot be adopted under a newly selected toolchain. Conflicting bytes for one input
key disable that entry rather than choosing one result silently.

Tasks with complete output declarations have individually reusable entries. A task without declared
outputs owns exactly the files its run wrote under the generated root and the project Content
(`package_ownership.py`), and publishes them as its entry. A non-factory Blender task's tool key
also covers everything its startup can read beyond the keyed app bundle: the bytes of the version's
user resource tree (preferences, startup file, add-ons, startup scripts, app templates, extensions;
Blender's derived extension cache excepted) and the `BLENDER_USER_*` and `BLENDER_SYSTEM_*`
variables with the trees they name. Its fingerprint is unchanged, so dependents are not re-keyed.

For existing native state, compiled engine BuildId and SDK must be compatible. The receiving observed environment
is recorded locally; a later tool change invalidates compatibility-only stamps. Unknown or expensive misses still
stop before native work. Reuse never manufactures producer provenance or treats any Intermediate file as proof.
A changed C++ target still goes through UBT; this is not a cross-worktree compiler object cache.

Native importers can also declare a `CandidateScope` on their normal build step. Before a
cache miss executes, including a batched leaf, the executor discovers compatible retained
checkpoints locally and in private history. It stages the declared reports and complete package
directories as independent copies in ignored `.state/import-candidates/`. Existing receiver
products and stamps remain intact; no manual donor selection is required. An engine/SDK mismatch,
missing clean donor revision, incomplete history or corrupted bytes makes the candidate unavailable.

These are compatibility candidates, not certified task results. The native importer loads one
validated bundle, verifies each selected member on access, and must prove its current source and
geometry policy match before reuse. The bundle carries `donor_stamp`, the original task evidence.
Its per-file input identities recover historical importer and support code from local Git objects
without executing it. The capture revision identifies the capture; it does not prove which importer
produced an older package. Missing original policy evidence is a normal import miss. It reruns current material, role, bounds and collision checks.
Changed or unproved assets import normally. Only the normal successful importer can publish a
current result. A whole-task miss can therefore reuse unchanged meshes without accepting stale
validation or overwriting unrelated completed receiver work. Importers must integrate this shared
protocol and declare their real artifact boundaries; arbitrary existing importers are not inferred.

Each finalized native summary records actual imported/local/candidate counts and `miss_reasons`.
These reasons identify the observed refusal, such as a dirty loaded package, mismatched saved receipt,
missing compatible history, changed candidate geometry, recorded source mismatch or rejected current
validation. They are observations, not proof that an import was avoidable. Read the exact invocation's
`native-imports/TASK/summary.json` and require `finalized_after_native_success`; pending packets and
staged file counts are not successful reuse. Reasons publish only after the normal successful host
boundary, including for unsupported mesh policies that imported normally without reusable receipts.

Existing local imports made before package inventories can follow a bounded incremental transition:
their recovered source/import policy and receiving environment must agree, their package files must
predate the old successful task without later modification/replacement, and Unreal must confirm the
stored source MD5 plus current import options and native validation. Known environment mismatches
are refused. When prior byte inventories exist they must match; a failed per-mesh receipt cannot
fall back to weaker evidence. This is compatibility-only continuity, not proof of canonical vertex
identity or a newly produced action result. It avoids reconstructing intact older local assets;
it does not authorize arbitrary existing packages or manual stamp adoption.

For an agreed read-only handoff from a clean, fully stopped older producer, use
`atelier cache retain-candidates GAME --source CHECKOUT`. It writes capture scratch/logs in the
controller and immutable files in the machine cache. It never writes producer `.state`, stamps,
products or Zen data. Only generated/Content members and historical evidence enter a candidate-only
catalogue; this is not a complete workspace seed or a new task certificate. Normal importer discovery
finds it automatically. Preserve the producer until the key is reported. This diagnostic capture is
not required for ordinary release retention. With the producer owner’s permission,
`atelier cache recover-history GAME --source CHECKOUT --checkpoint KEY --before-ns N --task TASK`
can recover explicitly selected small original stamp records. Both timestamps must precede the
known pre-capture boundary, the checkout must match the captured producer, and each read must
remain stable. It never reads live output bytes or writes the producer. Rewritten records miss.

All retention paths preserve stale tasks
separately in `historical_stamps`; these records never become successful action certificates or
receiving stamps. The read-only command accepts `--deadline-seconds` from 60 to 900 for bounded
maintenance handoffs, including queue time and cleanup.

A reviewed source-support extraction can preserve complete local products and restore an
existing portable cache result under its original tool identity. The executor reproduces the full
old fingerprint with unchanged installed tool bytes, source, commands and dependencies; keyed
state must also match its complete output inventory. Unknown changes miss. Preserved results
remain compatibility-only rather than acquiring a new producer certificate. Lookup and migration
happen before batching, so intact exports are not rerun merely because shared support code moved.

Embedded importers use `native_protocol.native_context(game)` rather than the build controller.
`native_protocol.runtime_files()` declares the complete small standard-library source closure.
Recipes include that closure and their actual game helpers, so unrelated release/build-controller
edits cannot invalidate native geometry. Unsupported source policies rebuild through the ordinary
importer and do not publish reusable receipts.

The host receipt update preserves proved warm batch results through a bounded equivalence
check. It reproduces the complete previous fingerprint with current inputs, worker, commands,
tools, dependencies and outputs, substituting only one reviewed predecessor host file. Complete
retained output evidence must still match. The migrated state remains compatibility-only and
keeps its downstream result token. Unknown history, changed data/commands or incomplete output
proof follows the normal miss path; migration never weakens a future execution-policy change.

Character body, bike and horse imports depend on normalized exported content. An exporter implementation change
that reproduces the same mesh, skinning, clips and textures leaves the import current. FBX timestamps and generated
IDs do not count as content changes. Importer implementation, native module, actual asset or engine changes still
invalidate the tasks that consume them. Existing imports keep their dependency result when the previous
declaration and retained outputs prove the migration changes only dependency metadata.

Fresh checkouts can receive the latest compatible complete workspace as an incremental seed. Receiving task
certificates are recomputed against current inputs. Intermediate is path-bound and is restored only at its
original checkout path; PCH and object files are never blindly relocated. Shared engine/DDC/Zen services stay in
place. Zen cooked data is exported/imported with UE snapshot operations, never by copying a live database.
The implementation currently targets the installed macOS UE 5.8 toolchain.

## Expensive misses stop

The game sets `[checkpoints] rebuild_budget_seconds = 600`. Unknown native costs or a cumulative estimate above
that budget stop before command preparation/admission. The error explains how to inspect the plan:

```sh
uv run atelier build yorimichi --plan --explain
```

Fix cache access or the invalid input declaration first. An unavoidable rebuild requires an explicit reason:

```sh
ATELIER_AGENT=OWNER nice -n 10 uv run atelier build yorimichi TASK --rebuild-reason "specific reason"
```

A bare reason covers only the tasks named on the command line and those with no result at launch. Any other
task the budget stops needs its own reason, `--rebuild-reason STEP="why"`, repeatable; the stop prints that form.
Each use is logged with its task and scope.

Reasons are recorded locally. They do not weaken admission, guards, worker caps or deadlines. `--touch` cannot
certify checkpoint builds. `--force` additionally requires one exact task and forces only that task, preserving
current prerequisites. Never clear caches, delete stamps or force a whole dependency closure to fix a miss.

## Merges

Merge PRs with `gh pr merge --squash --match-head-commit <tested head>`; builds publish their results to the local store as they run.

To retain an existing producer's artifacts explicitly, for example one built by an older controller:

```sh
uv run atelier cache retain GAME --source CHECKOUT
```

With no game arguments it retains every game with build stamps. Never run another build solely to fill the
cache, manufacture success stamps, or copy artifacts manually into another checkout.

## Releases retain work remotely

`atelier release publish` captures existing verified producer outputs locally, publishes the public playtest
and prints its link, then schedules private upload in a detached process. Private upload never blocks the
publish command or rolls back a successful public release. The worker reads the immutable store, without
accessing or holding the producer. It does not rebuild or cook the game. Normal successful tasks retain local
results; whole-workspace capture runs at release publication. Private release packs are content-addressed,
checksum-verified and deduplicated. New uploads use six workers and 100 MiB parts; verified older 128 MiB
packs are reused during interrupted-backup recovery when their original deterministic blob sequence matches. The temporary spool holds only the active upload window,
and verified parts are removed immediately. Logs report verified bytes and observed throughput. The completion
index uploads last; partial drafts are never donors. `atelier cache status` shows backup state. Pending and failed requests pin their manifests/blobs.
Rerun the same publish command to resume without recapture or clobbering completed assets. If capture itself
failed, preserve the producer and repair access before retrying. The [publishing guide](RELEASES.md) also covers
resuming an already captured interrupted backup without producer access.

Keep the completed producer at its final source revision, with its build outputs, stamps, Content, Binaries,
Intermediate and Saved/Cooked, until checkpoint upload, verification and a receiving restore are accepted.
A running producer and its enclosing caller must stop before any transfer or source/client update. Preserve
shared engine, fetched inputs and DDC. Never link mutable generated folders between checkouts.

After each successful private save, a complete immutable index consolidates every certified historical
input-keyed task result and all explicit live checkpoint pins. Only then are older checkpoint metadata
releases removed. Referenced packs remain in immutable storage releases, preserving their numeric asset
IDs; the index may reuse their bytes without another upload. Packs referenced by neither that index nor
a live pin are deleted, followed by empty storage releases. Logs report only remotely confirmed freed bytes.
Interrupted uploads receive seven-day retry pins. Their immutable draft indexes protect every
referenced pack, including packs reused from older saves. Cleanup defers while a live publication
has no complete reference inventory; its retry pin bounds that deferral. An explicit acceptance pin carries an expiry or a named
release condition; releasing it writes a remote tombstone so another machine's stale local file cannot
resurrect it. Missing or malformed pin evidence stops cleanup. Public playtests, other games and other
repositories are outside this cleanup.

Inspect pins and release a completed acceptance condition through the ordinary cache command:

```sh
uv run atelier cache checkpoint-pins GAME
uv run atelier cache checkpoint-unpin GAME PIN --reason "upload and receiving restore accepted"
```

Publication, remote download and collection share an atomic private Git writer reference across machines.
A remote reader may wait up to ten minutes while a backup owns this reference, then reports a retryable
failure; existing local cache hits do not wait. This conservative exclusion prevents deletion during reads.
Ownership never expires or gets stolen. A crashed writer requires evidence that its worker and all upload
transports stopped; `atelier cache writer-recover GAME --claim COMMIT --evidence FILE` verifies the exact
same-machine claim before removal. The evidence JSON must contain schema1, the exact commit, and true
`worker_cleanup_complete` and `transport_release_resolved` fields. Never assert these without checking.
Before enabling this collector, finish older private-upload workers that predate the shared protocol.

Local manifests, candidate bundles, pending/failed backup requests and their CAS bytes remain protected.
`atelier cache gc` currently manages only the separate portable source store; automatic workspace and local
checkpoint pruning are not implemented by this private-store collector.

## Recovery and validation

Interrupted restoration writes a durable launch barrier and removes success stamps before replacement. Build,
play and package refuse partial state. Rerun the normal build to finish the recorded restore; after guard exit,
receiving inputs and bytes are checked again before success publication. Preserve journals and logs on failure.
For a journaled partial transfer, `atelier cache abandon-transfer GAME` removes its journaled partial generated files while
preserving tracked source and logs; then use the normal build.

Configured games use UE dependency-tracked incremental cooking by default. This change was requested as a
source-first rollout without native builds/cooks. Python tests cover matching, transfer integrity and lifecycle
boundaries; no packaged parity or tenfold speedup is claimed. A cooker may legitimately invalidate its prior
state; the rebuild budget stops an expensive miss instead of silently authorizing it.

## Retention evidence

Normal builds publish artifacts and certificates as steps complete. Workspace-only outputs,
including original-path compiler state, are updated in the CAS during the build using verified
file signatures to reuse unchanged blobs. Completed cooks export their Zen snapshot through the
ordinary guarded worker before publication. The build finalizes its retention manifest before exit.
`atelier cache retain` then checks metadata/signatures and retains that existing manifest; it never
re-hashes outputs, walks generated trees, exports Zen or launches a capture.
Restoration still verifies the actual CAS bytes and the receiving recipe's inputs.

A producer built by an older controller needs one ordinary incremental build to publish this evidence.
Missing, changed or incomplete evidence refuses promptly instead of silently starting a costly scan.
Build and retain exclude each other on the producer; active builds are a prompt refusal, not a queue.
The current `workspaces/*.json` staging records in the private checkpoint store are CAS reference roots
and must be included in any coordinated retirement audit. Finished checkpoint manifests preserve their
references after build completion. Explicit release/backup workspace capture remains a separate operation.
