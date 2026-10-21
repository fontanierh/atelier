# Build caches and independent reuse

Keep a complete playable canonical checkout warm. Feature worktrees keep independent generated
files; all share the installed engine and its local derived-data cache. Never share mutable Unreal
`Content`, `Binaries`, `Intermediate` or PCH trees. Cache hits must describe actual successful output,
not hide missing inputs or failed builds.

## Automatic product cache

Named-product actions with `cache=True` publish verified portable outputs during `atelier build` and restore matching
actions automatically across revisions and worktrees. [The recipe guide](BUILD_RECIPES.md) covers eligibility and the
sandbox example. This store lives under `ATELIER_CACHE/products/v1` (by default the machine-local Atelier cache).
It uses content-addressed blobs and complete inventories. Restores are independent APFS clones or copies, never
links; a checkout stays usable if its cache entry is deleted. Builds do not upload artifacts automatically. Remote reads are
disabled unless explicitly configured as described below.

```sh
uv run atelier cache status
uv run atelier cache gc --max-gib 10 --max-age-days 30 --dry-run
uv run atelier cache gc --max-gib 10 --max-age-days 30
uv run atelier cache pin <action-key>
uv run atelier cache unpin <action-key>
uv run atelier cache forget <action-key>
```

Status reports unique blob bytes, action keys, last publication/restore time, pins, invalid manifests and conflicts.
These are logical content bytes, **not physical APFS space or a promise of reclaimed disk space**. GC drops old and
least recently restored/published unpinned actions, then unreferenced blobs. Pins can keep usage above the requested
limit; the result reports remaining bytes. GC is explicit; include it in disk maintenance before enabling large
products. It refuses concurrent transfers rather than deleting blobs in use. Ordinary publication/restoration may
run together in different checkouts. This cache mutex protects files and grants no native execution capacity.

A conflicting action key remains disabled until investigated. `forget` discards its entry and conflict record;
it does not choose either result as valid. Fix nondeterminism or missing inputs before publishing again. Deleting
an entry does not change successful local stamps; use a deliberate `--force` on that action to generate new evidence.
Corrupt action manifests must be explicitly forgotten before GC can safely determine blob reachability.

## Local portable snapshots

A local snapshot selects current portable products and their complete dependency closure. It records
`needs`, `after`, product reads and references, including reference-only cycles and leaf products nobody reads.
Spatial reads use the recipe's complete frozen query matches, including empty results. Selection never runs
actions or contacts a server. Every selected action must already have a current successful stamp, complete
outputs and a matching, non-conflicting cache entry whose blob bytes pass verification. Native packages,
non-cache owners, batching, custom verification callbacks, touched stamps and interrupted restores are refused.

```sh
uv run atelier build sandbox world.placements spatial.tile.west
uv run atelier cache snapshot-create sandbox world.placements spatial.tile.west --grants grants.json
uv run atelier cache status
uv run atelier cache snapshot-show <snapshot-key>
uv run atelier cache snapshot-restore <snapshot-key> sandbox
uv run atelier cache snapshot-unpin <snapshot-key>
uv run atelier cache snapshot-pin <snapshot-key>
uv run atelier cache snapshot-remove <snapshot-key>
```

The grants file uses the same per-action/product format as the publisher policy. Include **every product** of
every selected owner, including closure-only owners; a missing grant is an error. For the `world.placements`
selection, for example:

```json
{
  "schema": 1,
  "actions": {
    "sandbox/world.block": {
      "block.shape": {"permission": "public", "grant": "approved-source-v1"},
      "block.bounds": {"permission": "public", "grant": "approved-source-v1"}
    },
    "sandbox/world.placements": {
      "world.placements": {"permission": "public", "grant": "approved-source-v1"}
    }
  }
}
```

These example grant identifiers must be replaced by an actual approval applicable to the products.
Private grants permit local selection and restoration. `snapshot-create --public` additionally requires a
public grant for every product; it is a **selection check, not publication or an attestation**. The manifest
always says `authority: local-unsigned`. A local manifest must never be accepted as a trusted remote bundle.
Multi-action signed starter-pack export remains a separate integration with the existing pinned publisher,
producer and redistribution verification rules; these commands neither sign nor upload anything.

The immutable manifest lives at `products/v1/snapshots/<snapshot-key>.json`; its key covers canonical contents,
all action keys, inventories, edges and grants. It contains no checkout paths or timestamps. Limits are
256 actions, 256 MiB logical product bytes and a 2 MiB manifest; each action also obeys the signed-bundle
inventory/path bounds. Snapshot enumeration is limited to 512 identities and 1536 directory entries.

Creation pins the snapshot. Pinned snapshots retain **every member action and blob**, independently of action
pins and GC quotas. Status reports snapshot roots and each action's `snapshot_retained` flag. GC verifies
pinned members before deleting anything and fails closed on malformed manifests, dangling pins, missing or
conflicting retained actions, and missing/corrupt retained bytes. `forget` cannot remove a snapshot-rooted action.
Unpinning is explicit and makes members eligible for ordinary GC; the valid unsigned manifest remains as
historical metadata. After eviction, use `snapshot-show --metadata-only` to inspect it; repinning and restoration
require complete verified members again. Removal is explicit and requires unpinning first. For a damaged root,
unpin/remove the snapshot explicitly or repair its members before retrying GC; GC never guesses a missing root.

Restore requires the receiving recipe, source/tool identities, selected closure and exact action keys to agree.
Stop that checkout's game/editor and any other build or restore writer before installation. Concurrent mutation
of one checkout is unsupported; independent file copies are not a live-game update protocol.
It holds the store mutex throughout verification and installation, preventing GC races. Every selected stamp
is removed and journalled before replacement; existing portable staging verifies independent copies, then a
fresh graph/input/output check certifies the restored actions. It executes no fallback generators. An interrupted
restore leaves a snapshot-wide `.portable-snapshot-in-progress.json` barrier in both the checkout's default
build root and the selected output root. Build, play, package and direct native launches refuse that mixed snapshot,
including when another output root is selected. Repeat the same `snapshot-restore` key in the original checkout,
output root and cache to resume its recorded nonce and scope. A different key/scope or conflicting nonce is refused;
normal builds cannot clear this barrier. Successful resume removes it last, after every selected action is certified.
This installs portable sources only; ordinary native reuse is handled by build checkpoints.

## Native build checkpoints

Ordinary builds and releases use [build checkpoints](BUILD_CHECKPOINTS.md). The removed exact-commit
whole-build transfer is not a setup step. Individual task hits require complete output inventories;
lookup uses inputs and tools across source revisions. This page documents separate portable source formats.

## Import a signed offline bundle

```sh
uv run atelier cache import-bundle /path/to/bundle --trust publishers.json --dry-run
uv run atelier cache import-bundle /path/to/bundle --trust publishers.json
uv run atelier build <game> <step>
```

The importer verifies a supplied bundle, then publishes its portable source products into the existing local
store. An ordinary build can restore an exact action-key match through its existing staging, complete-inventory
verification and independent-copy protocol. Importing never writes checkout outputs or success stamps.
`--dry-run` verifies the same signature, policy, inventories and bytes without changing the store.

Obtain publisher public keys through a trusted channel. The explicit trust file contains only public keys:

```json
{"schema":1,"publishers":{"<sha256-of-raw-public-key>":"<base64-raw-32-byte-Ed25519-public-key>"}}
```

The bundle cannot nominate its own trust root. Do not add an unknown key merely because a download includes it.
The directory contains `manifest.json` and flat `blobs/<sha256>` regular files; archives are not extracted.
The manifest has exactly `payload` and a base64 Ed25519 `signature`. Signed bytes are
`b'atelier-artifact-bundle-v1\0'` (schema `1`) or `b'atelier-artifact-bundle-v2\0'` (schema `2`), followed
by canonical sorted, compact ASCII JSON of the payload. Both use namespace `atelier.portable-source.v1`, the publisher key ID, the unchanged
local action `entry`, `root_names`, a `producer` attestation and a `redistribution` grant for every product.
`root_names` maps each product to the ordered original basename of each root. These signed labels permit path
policy checks that the local inventory's numeric root indexes alone cannot provide. They remain publisher assertions;
the normal build restore also validates the receiving recipe's actual destination paths.

V1 producer fields remain exactly `source_commit`, `clean`, `pushed`, `guarded` and `tool_context`; the three
flags must be true. V2 instead requires exactly `source_commit`, `clean`, `pushed`, `execution`, `tool_context`
and `audit_sha256`. Its two flags must be true, and `execution` must be `audited-python-v1`. The audit digest
identifies the producer's run-bound audit receipt. V2 makes no native memory-guard assertion. Mixed producer
variants and signatures under the other version's domain are refused. CAS entries and action keys are unchanged.
Each redistribution record explicitly names `permission` (`private` or `public`) and a bounded `grant` identifier.
Missing permission refuses import; a private grant permits private local ingestion and never authorizes upload.
A verified signature authenticates the pinned publisher's assertions. It does not independently prove the build
was clean, pushed or guarded, that a licence is valid, or that arbitrary file contents contain no secrets.
Trusted publishers remain responsible for those facts.

Reads and reconstruction are bounded: manifests at most 2 MiB, trust files 64 KiB, 256 products, 32 roots per
product, 4,096 inventory records and 256 MiB of logical file content per bundle. Links, special files, unsafe paths,
declared native package paths and known credential/authentication/ledger paths are refused. Every blob is rehashed, and every
complete product inventory is reconstructed before publication. Same-key conflicts retain the existing refusal
policy. A failed publication may leave unreachable blobs; ordinary GC can remove them.

The JSON receipt identifies the accepted action, publisher, assertions and permissions; retain it when auditing
imports. Removing a public key from the trust file does not revoke bytes already accepted into the local store.
Use the receipt's action key with `atelier cache forget` when revoking an import. This receiver does not upload
or discover keys. The HTTPS transport below uses the same validation and store publication protocol.

## Fetch signed products over HTTPS

```sh
uv run atelier cache fetch-bundle https://cache.example.test/products/ <action-key> --trust publishers.json --dry-run
uv run atelier cache fetch-bundle https://cache.example.test/products/ <action-key> --trust publishers.json
```

An HTTPS object-store endpoint serves two fixed paths under its configured prefix:

```text
actions/<action-key>/manifest.json
blobs/<sha256>
```

The manifest format, trust file, inventory policies and quotas are the same as the offline bundle. The requested
action key, signature and all policy/size declarations must pass before any blob request. Blob URLs come only
from the configured prefix and validated digests. All downloaded bytes are rehashed, then the ordinary bundle
importer rechecks trust and complete inventories before publishing to the local store. It writes no checkout
outputs or stamps. Normal builds perform restoration and certify their inputs independently.

To enable lookup automatically after a local product-cache miss, set both variables in the build environment:

```sh
export ATELIER_ARTIFACT_URL=https://cache.example.test/products/
export ATELIER_ARTIFACT_TRUST=/path/to/publishers.json
uv run atelier build <game>
```

Only `cache=True` actions use remote lookup. Current outputs and local cache hits avoid it; plans, `--force`
and `--touch` never contact it. Without both settings, no remote lookup is enabled. An incomplete or invalid
configuration reports an unavailable cache and continues locally. Missing actions run normally. A transport,
signature, policy or import failure disables later remote lookups for that build and leaves local execution
as the fallback. A remote hit enters the ordinary local restore path, including input rechecks and stamp handling.

`ATELIER_ARTIFACT_TIMEOUT` sets a shared lookup allowance per build (default 30 seconds; maximum 300).
Transfer and verification time consume it; local generation between lookups does not. The explicit command's
`--timeout` sets its transfer deadline. An owned network process enforces that deadline even during stalled DNS
resolution or slow trickle responses, and is reaped on every exit. Cleanup and parent-side inventory verification
can extend the command beyond the network deadline. Waiting progress is emitted at least every 10 seconds;
explicit commands put progress on stderr and the JSON receipt on stdout. No cache lock is held during networking.

The transport requires verified HTTPS, refuses redirects and compressed responses, and ignores implicit proxy,
netrc and certificate-path environment settings. URLs cannot contain credentials, queries or fragments. There is
currently no receiver authentication header or presigned-URL support; an endpoint must be readable without these, for
example on a private network with a publicly trusted TLS certificate. It never prints URLs, response bodies or
foreign network exceptions. Archive extraction, automatic upload and a GitHub release adapter remain unimplemented.
The trusted local exporter below supplies signed bundles; a public repository does not grant asset redistribution rights.

## Export from a trusted Python producer

```sh
uv run atelier cache export-bundle sandbox world.block /path/to/new-bundle --profile /path/to/publisher.json
```

This command always executes a fresh build; it cannot sign an arbitrary old stamp or accept `clean`, `pushed`
or audit-success flags. The first producer supports one independent `cache=True`, `audit=True`, non-heavy
Python action with named products. Dependency/reference/query edges, custom verifiers, Blender and Unreal are
refused. Export writes a new local directory, with the manifest committed last, and never overwrites an existing
destination. Its receipt says `uploaded: false`. Private grants permit local export/ingestion, not upload.

The operator creates a regular owner-only profile outside the checkout, using absolute paths for the checkout
and raw 32-byte Ed25519 signing-key file. The key must also be owner-only, have one link, and be outside the
checkout, build outputs and cache. Provision the key through the operator's trusted secret-handling workflow;
never commit it. A profile has exactly these fields:

```json
{"schema":1,"repository":"/path/to/checkout","remote":"https://example.invalid/project.git","ref":"refs/heads/main","actions":["sandbox/world.block"],"grants":"artifact-grants.json","signing_key":"/path/to/protected/signing.key"}
```

The remote is an explicit credential-free HTTPS URL or absolute local bare-repository path, not a mutable
checkout remote alias. Git credentials, if needed, remain in the host's trusted Git configuration. The producer
checks the freshly advertised approved branch before and after execution: a cached remote-tracking ref is not
pushed evidence. Each Git call has a 15-second deadline and bounded output. Network unavailability refuses export.

The repository maintainer must commit an approved grants file before publication. Every product needs its own
explicit `permission` and grant identifier; the repository being public does not grant redistribution rights:

```json
{"schema":1,"actions":{"sandbox/world.block":{"block.shape":{"permission":"private","grant":"approved-policy-reference"},"block.bounds":{"permission":"private","grant":"approved-policy-reference"}}}}
```

The command requires a clean checkout and checks every consumed source against ordinary committed Git blobs,
including scripts, audit support, optional-file presence, the recipe, lockfile and grants. Ignored local inputs
and Git `assume-unchanged` flags cannot bypass those byte checks. Source traversal is bounded to 4,096 records
and 256 MiB; bundles retain the import limits above. It recomputes the action key/tool context and complete
output inventories, requires a fresh run-bound successful audit receipt, and repeats source/ref/output checks
before reading the private key. Blobs are copied and rehashed in private staging. Failed validation produces no bundle.

The host, approved recipe and signer implementation are trusted. The Python input audit is a diagnostic, not a
security sandbox: environment reads, metadata-derived behavior and arbitrary native I/O remain outside its
guarantee. Owner-only files and loading the key after execution do not isolate it from malicious code under the
same user account. This command does not provide hostile-source signing, a native memory guard or online publishing.

## Upload an approved public bundle

```sh
uv run atelier cache upload-bundle /path/to/export --trust /path/to/publishers.json --profile /path/to/upload.json --dry-run
uv run atelier cache upload-bundle /path/to/export --trust /path/to/publishers.json --profile /path/to/upload.json
```

This explicit command accepts an already exported, pinned-signer V2 audited-Python bundle. Every product must
carry an explicit `public` redistribution grant. A `private` grant permits local export/ingestion only, even
when the upload endpoint is private. A signature authenticates these permissions and producer assertions;
Atelier does not independently establish redistribution rights. No build signs or uploads automatically.

The operator supplies an absolute owner-only profile outside Git checkouts and the bundle:

```json
{"schema":1,"endpoint":"https://cache.example.test/products/","token_file":"/path/to/protected/upload.token"}
```

The token file contains only a bearer token, optionally followed by one newline. It must also be absolute,
owner-only, single-link and outside checkouts/the bundle. Final-component symlinks and special files are refused.
Use a write credential scoped to the configured object prefix. Its value is read only after signature, grants,
every blob and complete reconstructed product inventories have passed the shared importer verification.
The upload consumes independent staging copies, so later changes to the original export cannot change its bytes.
A dry run verifies the bundle and profile without opening the token file or contacting the network.

The endpoint must honor atomic `If-None-Match: *` PUT semantics and expose the receiver's fixed object paths:
`blobs/<sha256>` and `actions/<action-key>/manifest.json`. Blobs are conditionally written and read back with exact
size/hash checks before the action manifest is conditionally written last. The manifest is then read back and
verified against the pinned publisher allowlist. An existing trusted public V2 manifest for the same complete
entry remains unchanged, including its original provenance. A different entry, corrupt blob, invalid signature
or private grant refuses publication; Atelier never deletes a conflicting remote object. Interrupted attempts
may leave unreferenced blobs. The server's conditional-write behavior is an operator deployment requirement,
not something a client can establish against a dishonest server.

TLS verification stays enabled, redirects are refused, and ambient proxy/netrc/certificate-path configuration
is ignored. Only the explicit upload client sends the bearer credential to the configured origin. Receivers
still need unauthenticated GET access; private read authentication and presigned URLs remain separate work.
URLs, credentials, response bodies and foreign network exceptions are omitted from progress and receipts.

The existing bundle quotas apply (256 MiB logical products and 2 MiB manifest). Verification uses at most two
logical copies in temporary staging; transfer payloads are bounded to twice the bundle/manifest byte quotas,
including readback. A separate owned worker enforces the total verification/network deadline, 30 seconds by
default and at most 300 with `--timeout`, including blocked DNS shutdown. It is reaped before scratch removal;
bounded cleanup can extend wall time beyond that deadline. This command changes no checkout outputs, stamps
or local store. Tests exercise fake HTTPS transport and a shipped sandbox export/upload/fetch/restore path;
no deployment, real upload, credential provisioning or native-product publication is claimed.

## Portable output pool

`atelier pool` is the older explicit pool for independently generated Python outputs. The recipe
must declare exclusively owned `pool_roots`, no dependencies, and only Python commands. Yorimichi
currently opts in the Hidamari and tree-house texture finishing steps. All other
steps refuse pooling. Pool entries stay in the machine-local ignored cache; licensed/private output
must never be added to Git or uploaded to a public artifact store.

After a successful build records the new pool context, publish it:

```sh
uv run atelier pool publish yorimichi world.hidamari_textures
```

In another feature checkout, sync its locked Python environment, check the pool, then restore:

```sh
uv sync
uv run atelier pool status yorimichi world.hidamari_textures
uv run atelier pool restore yorimichi world.hidamari_textures
uv run atelier build yorimichi world.hidamari_textures
```

The key combines source/command fingerprint, declared output ownership, platform/architecture,
Python interpreter bytes/version, installed package versions, dependency lock and studio Python
support files. It deliberately excludes whole Git revision, so unrelated feature changes can hit.
All output files are inventoried and SHA-256 checked before publication and restoration. Entries
publish atomically; a repeated key with different bytes refuses to overwrite the first entry.
Restores are independent APFS clones where available, regular copies elsewhere. Symlinks refuse.
Publish/restore run an owned file worker through the normal guarded admission lifecycle. In full mode,
this unclassified file command currently requests the managed CPU pool with exclusion and a 10 GiB
aggregate/actual-child ceiling; it does not claim calibrated file-copy concurrency. Legacy mode retains
its ordinary big-slot guard. The worker waits normally for admission; no coordinator message or manual
lock is needed. No second render lock is taken. `status` only reads cache availability; restoration
also verifies every file.

Stop other writers in the receiving checkout before copying, as with whole-build reuse. Before any
replacement, a durable `.pool-transfer-in-progress.json` records the exact step, source/tool key, output
scope, cache and invocation. The worker rechecks the queued request's source and journal after admission.
Copies and full inventories complete under its guard. The parent publishes the immutable entry or restored
stamp only after the worker exits successfully and both guard cleanup and capacity close succeed.
Build, play, package and direct native launch refuse an incomplete journal, including through another output root.
The private file-publication mutex serializes finalization and recovery; it is not an execution grant and
is never taken while waiting for admission.

A failed/interrupted restore removes its old stamp before replacing files and cannot certify completion.
Repeat the exact original publish/restore command to retry, preserving its key, checkout, output root and cache.
The retry verifies the same scope and replaces only its own pending attempt. If the source/key changed or you
want to stop the transfer, use normal guarded cleanup:

```sh
uv run atelier pool abandon yorimichi world.hidamari_textures
```

Abandoning a restore removes only that journal's generated output roots and step stamp, leaving the immutable
cache entry, other steps and logs intact. Abandoning a publish removes only its pending cache copy; the original
outputs and producer stamp remain. Recovery refuses unsafe paths, symlink scopes, changed journal identity
or other incomplete installation barriers. Installation barrier names are protected. Reserved names and overlapping
roots are checked without case sensitivity; overlapping Unicode-normalization aliases are rejected for APFS.
Transaction JSON reads are bounded to 8 MiB and refuse links/special files.
Do not delete the journal or manufacture stamps by hand.
Legacy and `--touch` stamps cannot publish: a real
successful build must have recorded the matching pool key. A miss leaves ordinary incremental build
as the fallback. This first pool is explicit, rather than silently changing every build's behavior.

## Full game and feature integration

| Artifact | Current safe workflow |
| --- | --- |
| Complete generated game plus compiled module | normal `atelier build`, using compatible input-keyed checkpoints; see BUILD_CHECKPOINTS.md |
| Named portable products with `cache=True` | Automatic verified restoration during build; inspect/prune with `atelier cache` |
| Opted-in portable texture folders | Publish/restore matching pool key with full output hashes; independent copies |
| Other generated Blender/character/audio outputs | Keep them warm; extend recipe ownership and tool/dependency manifests before enabling cross-branch pooling |
| Unreal imported assets | Keep complete source/output proof; normal incremental import unless a targeted delta proves the full changed-content allowlist, collision/material contracts and unaffected asset hashes |
| C++ and PCH | Compile incrementally per worktree; no shared mutable Intermediate or cross-branch Binaries certification |
| Shaders/derived data | Reuse the engine's existing local per-user DDC; prewarm only the actual renderer/profile needed |

A geometry or texture pool does not certify an Unreal import, shader profile or compiled ABI. Main
must still rebuild/import each affected step and pass its validators after feature integration.
Region source changes can affect terrain, vegetation and map inputs as well as park assets;
copying a region alone is insufficient. Do not blanket-touch stamps or clear generated assets/DDC.

Next candidates are isolated Blender outputs with verified Blender/runtime context and full consumed
dependency output manifests. Region-owned Unreal imports and a cheap map assembly step would address
the large broad-world import cost. Those require ownership and collision/layout proofs before reuse.
A future shared DDC or compiler cache is separate from portable asset pooling and must retain local
fallback and real toolchain/header/flag keys; it never means sharing mutable intermediate directories.
