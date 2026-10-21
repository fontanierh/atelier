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

Tasks with complete output declarations have individually reusable entries. Tasks with representative outputs
continue through compatible workspace incremental state; their files and source fingerprints are retained,
but that state is not promoted into a produced task/tool certificate. Normal output/input checks still apply.
This includes existing non-factory Blender steps, whose ambient startup does not support portable action proof.
Add complete declarations and an explicit factory tool environment when migrating those tasks to individual reuse.

For existing native state, compiled engine BuildId and SDK must be compatible. The receiving observed environment
is recorded locally; a later tool change invalidates compatibility-only stamps. Unknown or expensive misses still
stop before native work. Reuse never manufactures producer provenance or treats any Intermediate file as proof.
A changed C++ target still goes through UBT; this is not a cross-worktree compiler object cache.

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

Reasons are recorded locally. They do not weaken admission, guards, worker caps or deadlines. `--touch` cannot
certify checkpoint builds. `--force` additionally requires one exact task and forces only that task, preserving
current prerequisites. Never clear caches, delete stamps or force a whole dependency closure to fix a miss.

## Releases retain work

`atelier release publish` captures existing verified producer outputs and uploads a private checkpoint before
publishing the public playtest. It does not rebuild or cook the game. Normal successful tasks retain their local results; whole-workspace capture runs at release publication. Private release packs are content-addressed, checksum-verified, deduplicated and bounded to 128 MiB.
The completion index is uploaded last; partial drafts are never used as donors. Rerun the same publish command
to resume interrupted uploads without clobbering completed assets.

Keep the completed producer at its final source revision, with its build outputs, stamps, Content, Binaries,
Intermediate and Saved/Cooked, until checkpoint upload, verification and a receiving restore are accepted.
A running producer and its enclosing caller must stop before any transfer or source/client update. Preserve
shared engine, fetched inputs and DDC. Never link mutable generated folders between checkouts.

Retain published private checkpoint releases and their packs: newer indexes can directly reference older packs.
There is deliberately no automatic checkpoint GC. `atelier cache gc` manages the separate portable source store.
Do not delete a referenced private release to save space.

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
