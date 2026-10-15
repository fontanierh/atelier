# Build recipes and named products

`games/<game>/build.py` returns `Step` declarations. Existing recipes keep their fingerprints and behavior.
New recipes can name independently consumed products so a producer change does not invalidate every consumer.

```python
from atelier.build import Product, Python, Step

def steps(ctx):
    sources, out = ctx.game_dir / 'world', ctx.out
    return [
        Step('library.bench', [Python(sources / 'bench.py')],
             inputs=[sources / 'bench.py', sources / 'bench.json'],
             products=[Product('bench.mesh', (out / 'bench.glb',)),
                       Product('bench.bounds', (out / 'bench-bounds.json',))]),
        Step('world.placements', [Python(sources / 'placements.py')],
             inputs=[sources / 'placements.py', sources / 'placements.json'],
             references=['bench.mesh'],
             products=[Product('world.placements', (out / 'placements.json',))]),
        Step('world.clearance', [Python(sources / 'clearance.py')],
             inputs=[sources / 'clearance.py'], reads=['bench.bounds', 'world.placements'],
             products=[Product('world.clearance', (out / 'clearance.json',))]),
    ]
```

The scripts write their declared paths. Command scripts are automatically included for named-product actions.
They must also declare imported helpers, data, settings and tool inputs that
affect their output. `Call` function bodies must also be covered by explicit source inputs. Declaration alone does
not discover arbitrary reads. Every required source of a named-product action must exist before it runs or accepts
a cache hit; plans report missing required inputs. Explicit optional files use the declaration below.
Native commands still need `heavy=True` and the existing guards.

| Relationship | Execution and invalidation |
| --- | --- |
| `reads=['bench.bounds']` | Build its producer first; hash this product's contents into the consumer key |
| `references=['bench.mesh']` | Include its producer in the selected closure; do not derive data from its contents |
| `after=['compile']` | Run the prerequisite first without hashing its result |
| `needs=['legacy.step']` | Preserve the existing dependency on the whole step result |

If the bench generator changes but produces the same bounds, clearance stays current. Moving the bench reruns
placement and its actual consumers. Reference cycles are permitted; read/order cycles are rejected. A reference
must not conceal a read of bounds, collision, material state or any other derived data.

Each output has exactly one owner. Product roots cannot overlap, including case-insensitive aliases; a step cannot
consume its own output. A product also cannot overlap another step's legacy `outputs` or `pool_roots`, because
restoration and audited generation replace entire owned roots. Declare every required file and sidecar, or a wholly owned directory. Inventories include
every member, empty directory and file hash. Missing, altered, unexpected or linked output invalidates the product.
Symlinked ancestors such as a system temporary directory are supported; product roots and members cannot be links.
Input changes during generation prevent certification, and the final stamp is replaced atomically after validation.

## Track an optional source file

A step with named products can declare `optional_inputs=[source / 'override.json']`. The exact path contributes
either an absent identity or a complete regular-file content identity to its key. Appearance, edits, removal and
changing between required and optional declarations all invalidate the action. An unrelated sibling file does not.
Normal `inputs`, command scripts and audit support files remain required. Plans explain optional-file transitions.

Use this for an explicitly named source whose absence has defined behavior, such as the sandbox block override.
Do not declare a broad directory merely to support `Path.exists()` on one file. A declaration grants an audited
action reads and ordinary metadata checks on that exact path; it grants no directory listing, descendant/sibling
read or source write. Optional paths cannot overlap the action's outputs or duplicate a required input.

Directories, symlinks (including dangling ones), special files and access/I/O errors are refused. Only a missing
path is absence. Existing cache and post-generation fingerprint checks also cover optional files; a change while
building prevents certification. This tracks existence and file contents, not portable timestamp, permission or
inode dependencies. Declare imported helpers normally, and include optional source files in source control when
they are part of the intended game. Local dirty-source caching does not make a private file available to others.

## Inspect a build without running it

```sh
uv run atelier build sandbox --list
uv run atelier build sandbox --plan --explain
uv run atelier build sandbox --json
uv run atelier build sandbox world --timings --json
uv run atelier build sandbox world --changes --json
uv run atelier build sandbox --ddc --json
```

`--plan` and `--dry-run` are aliases. `--explain` and `--json` also imply planning unless `--timings`, `--changes` or
`--ddc` selects historical observations. These reports do not create build folders,
write stamps, run commands or take render capacity. Recipes and verification callbacks must themselves be read-only
during inspection. Changed input names are available after a new successful build stores input detail; older stamps
get a general reason. A consumer of a dirty product is `check-after-build` when its outcome is still unknown.

Builds store per-command durations alongside total step time. Step/prefix selection remains supported; a prefix
matching only explicit steps reports an unknown selection rather than silently doing nothing. `--touch` cannot
certify named products.

## Compare certified outputs

`atelier build <game> [step ...] --changes` reports differences between the last two certified named-product
inventories for each selected step. `--json` exposes the complete member lists. This is historical inspection:
it reads stamps without hashing bytes, verifying current files, running commands or contacting the cache.

Reports list added, changed and retired members, and count unchanged members. Members include files, sidecars,
empty directories and the declared roots themselves. A rename appears as retirement plus addition; replacing a
file with a directory is a change at that path. Removing a product declaration retires it from the certified set;
this report neither deletes its files nor claims they were removed from disk.

These are **content differences between certified outputs**, not a trace of filesystem writes. Rebuilding identical
bytes produces no changes. Restoring damaged/missing files can also produce no content delta when the last certified
inventory already described those bytes. Execution and restoration are labelled separately. Copied stamps retain
the donor's historical change receipt; they do not describe installation into the receiving checkout.

The builder compares inventories it already computed, with no extra source or output byte reads. Successful stamps
store portable ordered root labels and diagnostic changes outside products and cache manifests. Missing/old/malformed
baselines, external roots and moved/reordered root declarations are **unknown** rather than falsely unchanged.
No-op builds leave history alone. Failed builds have no successful receipt; an interrupted restore is not reported
as a certified change. As with `--timings`, combine `--changes` only with step selection and optional `--json`.

## Measure work inside a command

`atelier build <game> [step ...] --timings` reads the last successful step and command receipts. Add `--json` for
machine-readable output. It loads the recipe and selects its dependency closure, but does not hash inputs, verify
outputs, contact the store, launch tools or acquire capacity. Recipes must remain read-only when declaring steps.
These are historical measurements, not a statement that the outputs are current. A no-op build leaves the previous
receipt intact. Failed commands retain their raw log; they have no successful stamp for this view to display.

Execution and cache-restore durations are separate. A restore with the same key preserves an existing local
producer receipt, including across repeated restores. A fresh checkout restore, or a restore after a different
key, has no producer timing unless it already carries that receipt. It is reported as **not recorded**, never zero.
Explicit worktree reuse and the legacy pool copy producer stamps; their restore duration is unknown. Touched,
old stamps without command details and interrupted restores also remain clearly labelled.

To time a generator or importer, emit one flushed stdout line per phase boundary. The version 1 protocol is the
literal prefix `ATELIER_PHASE ` followed by a JSON object:

```python
import json
import time

print('ATELIER_PHASE ' + json.dumps({
    'event': 'begin', 'id': 'mesh-export', 'name': 'export meshes', 'at': time.monotonic(),
}), flush=True)
export_meshes()
print('ATELIER_PHASE ' + json.dumps({
    'event': 'end', 'id': 'mesh-export', 'at': time.monotonic(), 'ok': True,
}), flush=True)
```

Use one monotonic clock and emitter per command. IDs are unique within the command; IDs and names are printable
strings of at most 128 characters. A nested begin adds `parent` equal to the current open phase's ID; end records
close the most recently opened phase. Nested durations include child time and must not be summed. Independent
concurrent emitters are not supported. `ok: false` describes a measured phase failure; the command's exit code and
normal success marker still decide whether the build succeeds.

The parser accepts Unreal log prefixes. Only for `UnrealScript`, adjacent identical JSON records are treated as
echoes; any intervening ordinary output ends that allowance. Traces are limited to 1,000 records, 8,192 characters
per payload and 32 nested phases. At the first malformed, duplicate, out-of-order or oversized record, parsing
stops and the trace is marked incomplete. Earlier completed intervals remain; open intervals have no duration.
Bad timing data never substitutes for output verification or fails an otherwise successful build.

Timings live in logs and stamps, outside product payloads and store entries. Scripts need no shared timing import;
the sandbox block generator demonstrates direct emission. Adding a shared helper later would make that helper
an ordinary declared code dependency. This build-engine update itself changes the tool identity of portable
actions once; it does not weaken cache keys to avoid that initial rebuild. Native phase measurements still require
the normal guarded execution and admission. Command time outside measured phases includes waiting and launch/
shutdown overhead; do not label it all as editor startup.

## Inspect derived-data-cache observations

`atelier build <game> [step ...] --ddc [--json]` reads retained logs for selected Unreal script/package steps and
their dependencies. It starts no tools and does not read DDC directories, contact Zen, inspect artifacts, hash
inputs, write stamps or acquire capacity. Other commands such as Python generators and native compilation have
no DDC report. Combine `--ddc` only with step selection and optional `--json`.

The report recognizes explicit cache-node availability and disabled states, plus Unreal's `DDC Summary Stats`
fields for get/put counts, reported hit fractions and local/shared/Zen/cloud presence. An import log can describe
its cache configuration without recording any hit counts. Missing, malformed or conflicting values are **unknown**,
not zero. Contradictory count totals are unusable. Repeated summaries remain separate; local and ZenLocal counters
can overlap and must not be summed. Configuration that changes within a log is labelled **mixed**.

These are **historical, unverified log observations**. A retained log can describe a failed attempt, an older
revision or a reused donor; it does not prove the current configuration, a successful build, or sharing with
another checkout. `LogZenStore` cook-storage messages and isolated shader-cache misses do not establish DDC totals.
DDC reuse does not eliminate package imports, loading or saving.

For each step, the reader prefers `logs/<step>.guard/stdout.log`, covering the last guarded command, and falls
back to `logs/<step>.log` only when guard stdout is absent. It never counts both as separate executions. Reads are
capped at 4 MiB per file and 32 MiB per invocation, with 100,000 lines, 8,192 characters per line and 16 summaries
per file. Limits and logs changed during reading are labelled **partial**. Cut records are discarded; unsupported
formats remain unknown. Missing logs after reuse are normal. Symlinks and special files are not read.

Reports contain only allowlisted node/state labels and typed numerical fields. Paths, URLs, namespaces, command
lines and unknown raw log messages are omitted; the report identifies its source by a build-relative label.
The sandbox uses the same inspection path and reports unknown values until native logs exist. Parser fixtures
exercise the supported log formats without requiring a native build.

## Audit a Python generator's accesses

Add `audit=True` to a step with exactly one `Python` command and named products under `ctx.out`. It works with
or without `cache=True`. The sandbox's two portable generators opt in. Atelier installs a Python audit hook before
running the script and writes `logs/<step>.audit.json` separately from its products. No extra command is required.

The audit checks file reads against declared source inputs and `reads` products. A `references` edge grants no
read access. Directory listings require a declared directory with a complete inventory; listing the parent of
several declared files is insufficient. Audited source directories include every member, including Markdown and
bytecode, so adding a file cannot evade the key. Finder-created `.DS_Store` files and ambient `__pycache__` contents
also change these directory keys; prefer small source directories or explicit files. CPython's import finder may
search startup paths and declared module parents while loading modules; the bytes it opens still require declared
inputs or tool runtime. Resolver-only queries such as `importlib.util.find_spec` and direct `FileFinder` queries
are refused, including after a finder has cached its directory listing. Native extension filenames reported by
Python's import event also require declared inputs or tool runtime. Namespace packages require a fully inventoried
directory or tool runtime.

Writes, removals and renames must stay within owned products or private scratch space. After a cache miss, Atelier
drops the stamp and removes the action's old product paths before launching it. It unlinks file leaves, preserving
any other hard-link names; old bytes, metadata and leftover files cannot become inputs. A failed action leaves no
certified outputs, and a retry starts empty again. Reading back new writes is allowed. Atomic output replacement
works by writing in the action's private temporary directory and then using `os.replace`. Use an owned directory
product when a generator needs temporary siblings.

Atelier gives the action private `HOME`, temporary/cache directories and a bytecode prefix. Ambient source bytecode
is not used, and the action does not write bytecode. Declared inputs, arguments, the audit adapters and managed tool
context enter its fingerprint. Installed Python libraries remain part of that tool context and must stay fixed.
Audited actions inherit the ordinary launcher; `heavy=True` still takes its normal lock and memory guard.

A caught access violation remains a failure. Missing, malformed or unsuccessful completion records prevent stamps
and cache publication, including an `os._exit(0)` that bypasses normal cleanup. Reports travel through a separate
inherited pipe, not a recipe-owned output. Cache hits verify the audited action key and complete output inventory;
they do not rerun the generator merely to produce another trace. The stamp records restoration separately.

This is a diagnostic for trusted recipes, **not a security sandbox or a proof of complete input closure**. It observes
Python `open`, directory and mutation events, and validates paths passed through `os.stat`, `os.lstat` and `os.access`
without changing their return values. Metadata values (timestamps, permissions and inode numbers), environment
reads, direct native I/O and unobserved low-level APIs are outside its guarantee. Recipes must not derive portable
output from those values. Observed subprocess, network, ctypes, mmap, sqlite3 and opaque descriptor operations,
and unhandled `os.*` events, are refused;
an uninstrumented child must not silently supply a supposedly audited result. Blender and Unreal bootstraps are not
enabled by this option. Their imports still need their own dependency and native equivalence proofs.
Libraries that use a refused mechanism during initialization also cannot pass, even if they catch its exception;
the installed NumPy uses `ctypes` this way. Such recipes must keep `audit=False` until a specific adapter proves the
required native behavior. Do not add a blanket exemption for the library.

## Migration boundary

Named actions use a persistent file-hash index in `build/<game>/.state/`. It checks file identity, size and nanosecond
mtime/ctime before reusing a hash; directory membership is always rediscovered. Missing or corrupt indexes fall back
to reading files. `--verify` bypasses hash hints. Publication and restoration always verify full output bytes.
Unaudited source directories retain the legacy exclusions for bytecode, build-tool caches and Markdown; an explicitly
named file is always included. Audited directories use complete inventories. Named source inputs cannot contain
symlinks: declare the real source instead.

Add `cache=True` only to a deterministic, portable Python/Blender action with complete product ownership under
`ctx.out`. Successful actions publish automatically to the local content store; a compatible action in another
checkout restores independent copies before running a generator. A change of unrelated Git revision does not
invalidate the key. The sandbox's `world.block` and `world.placements` are executable examples; run
`atelier build sandbox world` without any native tools.

The key includes command arguments, declared sources, consumed product digests, the managed Python environment or
Blender application, dependency lock and build adapters. Python path/interpreter overrides refuse portable caching.
Cached Blender commands must use `factory_startup=True`. Keep installed tools fixed during one build invocation;
the next invocation rediscovers their identities. A static import check rejects undeclared local helpers, including
package initializers and relative imports. Use `atelier.build_inputs.local_imports(script, roots)` when declaring
their closure. Dynamic imports, runtime data reads and relevant settings still need explicit inputs. The optional
Python access audit catches many missing declarations during execution; it does not replace the closure contract.
Scripts must not depend on undeclared environment values.

Portable output must be byte-deterministic, contain no checkout-specific paths and run without its donor checkout.
An interrupted restore leaves no successful stamp; the next build discards that action's abandoned staging and
verifies every installed output again. Missing/corrupt blobs fall back to generation. Two different outputs for the
same action key disable that key's reuse. [Cache maintenance](ARTIFACT_POOL.md#automatic-product-cache) covers
accounting, pins, LRU pruning and discarding conflicts. Plans remain read-only and never fetch or restore a hit.

`atelier reuse` and the portable pool reject recipes that try to certify named products through their older protocols.
Existing recipes remain supported. Unreal packages, native binaries, Content and Intermediate directories are
ineligible for this cache. Transactional Unreal restoration, import ownership, registry refresh, relocation and remote
storage remain described in [the architecture](INCREMENTAL_BUILDS.md). Keep native imports conservative until their clean/incremental equivalence checks
pass, following [world build practices](WORLD_BUILD_PRACTICES.md).

## Spatial product reads

Use recipe-declared boxes when an action depends on nearby products. `Product(collection=..., bounds=...)` names
a collection and a conservative bounding box. `BBoxQuery(name, collection, bounds)` selects its intersecting
products. Bounds are `(min_x, min_y, min_z, max_x, max_y, max_z)`, finite numbers in a shared coordinate frame and
unit. Flat boxes and touching boundaries are included. Names are stable product IDs, independent of discovery order.

```python
from atelier.build import BBoxQuery, Product, Python, Step
from atelier.build_inputs import local_imports

source = Step('world.rock', [Python(rock_script, (rock_source, rock_output))],
              inputs=[rock_source], audit=True, cache=True,
              products=[Product('rock.geometry', (rock_output,),
                                collection='geometry.cm', bounds=(10, 0, 0, 30, 20, 40))])
tile = Step('world.tile', [Python(tile_script, (tile_output,))],
            inputs=local_imports(tile_script), audit=True, cache=True,
            queries=[BBoxQuery('nearby', 'geometry.cm', (0, -50, -50, 100, 50, 50))],
            products=[Product('tile.geometry', (tile_output,))])
```

The tile script reads frozen matches:

```python
from atelier.build_context import query

for product in query('nearby'):
    # product.name, product.bounds and product.paths are immutable records.
    geometry = product.paths[0].read_bytes()
```

Resolution happens before target selection, ordering and cache lookup, against all current recipe declarations.
Matching producers become prerequisites and their selected product identities enter the consumer's key. The key
also includes query criteria and the full sorted result set, even when empty. Unmatched products and unconsumed
sibling outputs do not enter it. `--plan --json` exposes resolved matches; `--explain` names changed queries.

Queries currently require an audited Python action with named products. Only declared matches grant file access;
the action does not receive the global catalogue. Include its static imports through `local_imports`, and avoid
declaring a broad catalogue input on the consumer, which would deliberately invalidate it for every catalogue edit.
The [sandbox example](../games/sandbox/README.md#spatial-dependencies-without-unreal) exercises this without native tools.

Read catalogue metadata freshly inside `steps(ctx)`, for example from per-source JSON files. Atelier re-evaluates
the recipe before accepting a query consumer and before/after restoration or execution. Changed bindings, owner
paths, consumed bytes or refreshed consumer fingerprints refuse certification and require rerunning to replan.
The executor does not silently add producers to an already running plan. Fresh resolution does not reload arbitrary
Python globals or cached imported modules; keep catalogues out of such state. Products must not change concurrently
with their consumers. Endpoint checks cannot prove that a file was unchanged at every instant.

Bounds are author declarations, not a geometric proof. Include each operation's full influence volume and verify
that product bounds contain the generated geometry. Runtime-discovered boxes, generated spatial catalogues,
nearest-neighbour queries and native import/query adapters are not implemented. Use broader explicit reads until
those contracts exist. Native Unreal products remain ineligible for portable caching.
