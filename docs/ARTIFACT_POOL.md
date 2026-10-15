# Independent artifact pooling

Keep a complete playable canonical checkout warm. Feature worktrees keep independent generated
files; all share the installed engine and its local derived-data cache. Never share mutable Unreal
`Content`, `Binaries`, `Intermediate` or PCH trees. Cache hits must describe actual successful output,
not hide missing inputs or failed builds.

## Automatic product cache

Named-product actions with `cache=True` publish verified portable outputs during `atelier build` and restore matching
actions automatically across revisions and worktrees. [The recipe guide](BUILD_RECIPES.md) covers eligibility and the
sandbox example. This store lives under `ATELIER_CACHE/products/v1` (by default the machine-local Atelier cache).
It uses content-addressed blobs and complete inventories. Restores are independent APFS clones or copies, never
links; a checkout stays usable if its cache entry is deleted. Nothing is uploaded. Remote reads are
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
currently no authentication header or presigned-URL support; an endpoint must be reachable without these, for
example on a private network with a publicly trusted TLS certificate. It never prints URLs, response bodies or
foreign network exceptions. No archive extraction, automatic upload, GitHub release adapter or production signer
is provided by this transport. A repository being public does not grant redistribution rights for its assets.

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

## Portable output pool

`atelier pool` is the older explicit pool for independently generated Python outputs. The recipe
must declare exclusively owned `pool_roots`, no dependencies, and only Python commands. Yorimichi
currently opts in the Hidamari and tree-house texture finishing steps. All other
steps refuse pooling. Pool entries stay in the machine-local ignored cache; licensed/private output
must never be added to Git or uploaded to a public artifact store.

After a successful build records the new pool context, publish it at a render release:

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
A failed/interrupted restore removes its stamp before replacing files and cannot certify completion.

Publish/restore take the normal render mutex for actual file transfer; they fail promptly when busy.
Read the machine ledger/telemetry and coordinate these useful short turns. `status` only reads cache
availability; restoration also verifies every file. Legacy and `--touch` stamps cannot publish: a real
successful build must have recorded the matching pool key. A miss leaves ordinary incremental build
as the fallback. This first pool is explicit, rather than silently changing every build's behavior.

## Full game and feature integration

| Artifact | Current safe workflow |
| --- | --- |
| Complete generated game plus compiled module | `atelier reuse` from a clean complete checkout at exactly the same revision and engine; then incremental build |
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
