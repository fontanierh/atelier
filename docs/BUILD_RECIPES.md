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
The build also rechecks owned products after all selected steps, catching later importers that resave another
owner's package. Consumers verify fresh read-product bytes before certification. Completion and failure paths
also discard earlier consumer stamps when a later writer changes those inputs, including consumers with legacy
outputs. Reference edges remain independent of referenced content bytes.
Use `Product(name, required_paths, optional_paths=(...))` for format sidecars that may be absent:
their absence, appearance, removal or byte change is part of the product identity. Required roots still must exist.
Optional roots have the same exclusive ownership rules and are not eligible for the portable source cache or Python audit.
Change receipts retain their ordered root roles separately: an optional root appearing is an added member, its
removal is a retired member, and an absent root contributes no retained member count. Older receipts without the
optional-root roles remain unknown when they cannot be compared safely.

## Defer legacy input membership

A legacy action may defer an expensive directory selection until that action is selected and reaches
its fingerprint decision, after its prerequisites have finished:

```python
from atelier.build import DeferredInputs, Step

Step('runtime.identity', commands,
     inputs=[source / 'identity.py'],
     deferred_inputs=[DeferredInputs('content', identity.content_files, (content,),
                                     support=(source / 'identity.py',))])
```

`settings` is a tuple of positional collector arguments (nested tuples, paths, strings, integers,
booleans and `None`). `support` must include the collector's implementation and all its helpers.
Collectors are trusted recipe functions: they only observe membership and return an ordered list or
tuple of paths. They must declare all selection settings and code; this API does not discover hidden
reads, environment dependencies or hostile code. It does not import or launch tools itself.

Unselected collectors do not run. Fingerprints include explicit criteria, support bytes, ordered
member paths and their normal legacy byte feeds, including an empty selection. After executing an
opted-in action, a fresh selection and fingerprint must still match before a stamp is written.
Plans and worktree reuse use the same observation API; reuse filters copied generated members from
both the source-only byte inputs and membership list. No observation is cached on a recipe Step or
across invocations. Existing actions without this opt-in retain their fingerprint algorithm.

This first API supports legacy actions only: named products, reads/references, optional inputs,
spatial queries, audit, caches, pool roots, explicit toolchains and batches cannot use it. Supporting
named actions later requires preserving complete source/output ownership checks without enumerating
unselected members. Deferred selection does not grant native cache eligibility or audit certification.

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

## Reuse a tool process without merging actions

Opt in only scripts that reset their own transient state and can safely follow another script in the same process:

```python
from atelier.build import Batch, Blender, Product, Step

Step('library.oak', [Blender(script, ('oak',), threads=3, factory_startup=True)],
     inputs=[script, oak_spec], products=[Product('oak.mesh', (out / 'oak',))],
     heavy=True, toolchain=True, batch=Batch('tree exports', max_seconds=240))
```

Consecutive, ready misses with the same batch policy, command type, startup environment, module closure and tool
settings can share one guarded process. Arguments and script paths remain per action. `runtime_env=('ASSET_ID',)`
allows explicitly named environment values to vary between scripts; process-start settings such as `PYTHONHASHSEED`
cannot vary. Actions must override the same set of runtime keys; an added or omitted override starts a separate
process, so it cannot inherit the preceding action's value. Never rely on `runpy` to clear imported module globals,
Blender data or Unreal editor state. The recipe
must reset its own state, and native equivalence checks must cover cold and warm execution in different orders.

The host validates each action's marker, inputs and complete output inventory, saves its individual stamp, and
acknowledges it before the next action starts. A crash on action four preserves valid results from actions one to
three. The host checks completed results again after exit. No-op and already-current actions never enter the batch.
Cache-enabled actions currently execute individually, retaining their normal restore-before-execute behavior.
Per-action `seconds` and command timings in a batch measure action execution only. `--timings` labels that scope,
including in copied producer receipts. Shared tool startup/shutdown and host validation/acknowledgement time are
excluded; the builder does not allocate those costs to individual actions. Per-action phase and output-change
receipts remain historical diagnostics and do not change product identity or admission.
New individual command receipts identify their command-invocation scope. Historical commands without a recorded
scope remain labelled unknown; they are not assumed to include shared process startup or shutdown.

A batch uses BIG and the normal 10 GiB actual-child guard. Before each further action, its memory predictor reserves
headroom using the next action's measured batch growth and the current session's growth. Without batch history it
falls back to the standalone peak or conservative unknown headroom. Session reports stay separate from standalone
action peaks. Missing fresh telemetry ends the batch.
The wall budget is at most 240 seconds, including startup, and is checked **between actions**; one long action can
exceed it. This is a cooperative boundary, not a deadline that interrupts an import or a replacement for the guard.

Budget exhaustion saves completed results, exits **75 (yielded)**, and prints `BATCH YIELDED` with counts and a resume
command. It does not reacquire capacity automatically. `atelier build ... && atelier play ...` intentionally stops
there. Remaining actions stay `run` in `--plan`; rerun the printed command without `--force` after checking Waiting
and handing off to other ready work. Retain the original first-ready time in the render board's Waiting entry.

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
New portable restore receipts distinguish a local-store hit from a product fetched over HTTPS during that build.
The latter still passes through the normal verified local store before installation. A later local restore is
labelled local even if the bytes originally arrived remotely. Older stamps without this attribution say
**not recorded**; inspection never contacts a server to infer provenance.

Guarded commands can also retain a fresh launcher timing receipt. Admission and guard setup measure from entry
to the launch gate acknowledgement; child lifetime measures actual spawn to observed process exit and includes
any time behind that gate. These intervals overlap and must not be added. Command execution stays **not recorded**
unless the launcher observes its start separately. Useful phase durations still come from the instrumented script.
Missing, stale or malformed diagnostics never change build success, product identities or cache eligibility.

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

Add `audit=True` to a step with exactly one `Python` command and named products under `ctx.out`. Python actions
work with or without `cache=True`. Guarded `Blender` and `UnrealScript` commands have offline-tested Python access
audit adapters with `heavy=True` and `cache=False`; Blender requires `factory_startup=True`. Native products may live in owned
generated subpaths under `ctx.out`, or the project's `Content` for Unreal. Optional product roots, linked output
paths and legacy pool/cutoff protocols are refused. The sandbox's two portable generators opt in. Atelier installs a Python audit hook before
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
drops the stamp. The executing child removes old product paths before installing its observer and running the
recipe; heavy actions reach that child only after normal guarded admission. Refused admission preserves the old
products. Cleanup rechecks root and ancestor links and removes entries through held parent descriptors. It unlinks
file leaves, preserving any other hard-link names;
old bytes, metadata and leftover files cannot become inputs to the recipe. A failed action leaves no
certified outputs, and a retry starts empty again. Reading back new writes is allowed. Atomic output replacement
works by writing in the action's private temporary directory and then using `os.replace`. Use an owned directory
product when a generator needs temporary siblings.

Atelier gives the action private `HOME`, temporary/cache directories and a bytecode prefix. Ambient source bytecode
is not used, and the action does not write bytecode. Declared inputs, arguments, the audit adapters and managed tool
context enter its fingerprint. Installed Python libraries remain part of that tool context and must stay fixed.
Audited actions inherit the ordinary launcher; `heavy=True` still takes its normal lock and memory guard.

A caught access violation remains a failure. Missing, malformed or unsuccessful completion records prevent stamps
and cache publication, including an `os._exit(0)` that bypasses normal cleanup. Reports travel through a separate
inherited pipe, not a recipe-owned output. A fresh nonce, ordered start/accesses/complete records and pipe closure
are required. The hook stays armed after completion: trailing Python access fails certification, even if it repeats
a formerly allowed read and its exception is caught. Cache hits verify the audited action key and complete output inventory;
they do not rerun the generator merely to produce another trace. The stamp records restoration separately.

This is a diagnostic for trusted recipes, **not a security sandbox or a proof of complete input closure**. It observes
Python `open`, directory and mutation events, and validates paths passed through `os.stat`, `os.lstat` and `os.access`
without changing their return values. Metadata values (timestamps, permissions and inode numbers), environment
reads, direct native I/O and unobserved low-level APIs are outside its guarantee. Recipes must not derive portable
output from those values. Observed subprocess, network, ctypes, mmap, sqlite3 and opaque descriptor operations,
and unhandled `os.*` events, are refused;
an uninstrumented child must not silently supply a supposedly audited result. Blender/Unreal bootstraps observe
action-time Python work only; host startup, native callbacks and native imports still need explicit declarations
and native equivalence proofs. Offline fake-host tests validate this protocol without launching Blender or Unreal;
they do not certify real-host behavior or native package portability. Tool runtime exemptions come only from
recognized Python library directories within a fingerprinted host installation, never arbitrary `sys.path` entries.
Native bootstrap helpers execute their fingerprinted source directly. Ambient runtime `__pycache__` bytes receive
no runtime exemption, and action imports use a private bytecode prefix even if the host ignored startup flags.
Before execution, the bootstrap refuses preloaded project/helper modules outside the fingerprinted installation,
including declared sources: their loaded values may predate those source bytes or come from stale bytecode.
Package and namespace search locations must also stay inside the tool. Installed module origins and preloaded
bytecode must belong to the complete tool identity or fresh private bytecode directory; native Blender's audit
identity therefore includes installed `__pycache__` bytes. Originless modules require builtin/frozen loader
provenance or an explicit known host API name (`unreal` or the supported Blender API modules). Host API mutable
native state remains outside Python input observation. CPython's synthetic `typing.io`/`typing.re` namespaces require
their exact binding to the fingerprinted `typing` module. Preload rejection produces an incomplete report and no stamp.
The source-verified UE adapter is version-gated to UE 5.8. It completely fingerprints the bundled
`Engine/Binaries/ThirdParty/Python3/Mac` runtime and the exact
`Engine/Plugins/Experimental/PythonScriptPlugin/Content/Python` wrapper directory, including bytecode. That wrapper
directory also grants tool reads during the action. The identity includes the editor, `Build.version`, both
`libUnrealEditor-PythonScriptPlugin.dylib` and `libUnrealEditor-PythonScriptPluginPreload.dylib`, and their
`UnrealEditor.modules` descriptor. The shipped source creates exactly `_unreal_core`, `_unreal_slate`,
`_unreal_engine` and `_unreal_editor` at startup; those originless bindings join `unreal` as explicit native APIs.
UE's source-proven originless `__main__` placeholder is allowed only without file/spec origins; the recipe runs
in a fresh `runpy` main module, so startup globals in that placeholder do not become recipe globals.
Native startup search paths are retained, but grant no additional read permission. Other plugin/project roots,
preloaded project helpers and unknown dynamic native modules remain refused. The wrapper registry also generates
module names from loaded engine/game modules; those require explicit provenance before approval, not a prefix
wildcard. Fake hosts exercise the actual wrapper layout and known binding names. Actual UE execution and complete
native dependency/equivalence acceptance remain unvalidated and separate from this offline adapter.
Unreal keeps its descriptor isolation and native library checks before/after the observed script. These framework
checks run outside recipe observation; recipe ctypes calls remain refused.

An audited native action runs in a fresh process, including when it declares `Batch(...)`. Such declarations fall
back to ordinary per-action execution. Warm audited batching is unsupported: hooks cannot be removed and warm
modules/callbacks can retain earlier action state. The direct batch runner refuses audited candidates. A second
bootstrap invocation in the same host is a sticky failure. This option never enables native cache restoration or
publication.
The worker initializes managed stdlib `ctypes` before installing the observer, including CPython's own
`PyDLL(None)` handle. This lets NumPy import that existing runtime state. Action-time library loads and symbol
lookups remain refused, even when their exceptions are caught; NumPy gets no access exemption. Array operations
still have the native-I/O limits above. Other libraries that emit a refused event during initialization cannot
pass and must keep `audit=False` until a specific adapter supports their required behavior.

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
Cached Blender commands must use `factory_startup=True`. Blender discovery resolves app symlinks and simple
`#!/bin/sh` wrappers whose only command is `exec /absolute/app/Contents/MacOS/Blender "$@"` (quoted paths work too).
The fingerprint includes that app's bundled Python and exporters. Wrappers with extra flags, environment changes
or shell logic remain opaque: select the app executable with `BLENDER` and declare required flags in the recipe.
Keep installed tools fixed during one build invocation; the next invocation rediscovers their identities.
A static import check rejects undeclared local helpers, including
package initializers and relative imports. Use `atelier.build_inputs.local_imports(script, roots)` when declaring
their closure. A recipe with many scripts can share an `ImportScanner()` and call `scanner.local_imports(script, roots)`
within that recipe evaluation; create a new scanner on every evaluation so added or removed helpers are discovered.
`toolchain=True` includes the same installed tool identity for a named action without enabling storage or restoration.
Dynamic imports, runtime data reads and relevant settings still need explicit inputs. The optional Python access
audit catches many missing declarations during execution; it does not replace the closure contract. Scripts must
not depend on undeclared environment values.

Portable output must be byte-deterministic, contain no checkout-specific paths and run without its donor checkout.
An interrupted restore leaves no successful stamp; the next build discards that action's abandoned staging and
verifies every installed output again. Missing/corrupt blobs fall back to generation. Two different outputs for the
same action key disable that key's reuse. [Cache maintenance](ARTIFACT_POOL.md#automatic-product-cache) covers
accounting, pins, LRU pruning and discarding conflicts. Plans remain read-only and never fetch or restore a hit.

`atelier reuse` supports named products as part of a verified whole build at the same clean revision. It compares
producer source identities before copying and full fingerprints and inventories afterward, including unconsumed
leaves and optional sidecars. Its journal blocks build and launch after an interrupted copy; see
[snapshot recovery](ARTIFACT_POOL.md#verified-whole-build-reuse). The older explicit `atelier pool` still rejects named
products. Unreal packages, native binaries, Content and Intermediate directories remain ineligible for the automatic
portable source cache. Per-package cross-revision restoration, relocation and remote storage remain described in
[the architecture](INCREMENTAL_BUILDS.md). Keep native imports conservative until their clean/incremental equivalence
checks pass, following [world build practices](WORLD_BUILD_PRACTICES.md).

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

When a matching product declares `optional_paths`, the frozen result exposes that separate tuple too.
Required and optional root roles enter the selector identity; optional-root absence, presence and bytes enter
the consumed product identity. Audit read grants cover those exact owned roots, including missing optional
paths, without granting their parent directories or siblings. Products with optional output roots remain
ineligible for portable caching and Python auditing; this does not enable native package caching.

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

Each checkpoint resolves only the current action's queries, while revalidating ownership against the complete
fresh catalogue. Shared source paths are resolved once within that validation; path results are not retained
between checkpoints. Recipe loading, complete ownership checks and matched-product inventories still have a
cost. Profile large catalogues before migration; this API does not provide a persistent spatial index or watcher.

Bounds are author declarations, not a geometric proof. Include each operation's full influence volume and verify
that product bounds contain the generated geometry. Runtime-discovered boxes, generated spatial catalogues,
nearest-neighbour queries and native import/query adapters are not implemented. Use broader explicit reads until
those contracts exist. Native Unreal products remain ineligible for portable caching.
