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
not discover arbitrary reads. Every declared source of a named-product action must exist before it runs or accepts
a cache hit; plans report missing inputs. Native commands still need `heavy=True` and the existing guards.

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
consume its own output. Declare every required file and sidecar, or a wholly owned directory. Inventories include
every member, empty directory and file hash. Missing, altered, unexpected or linked output invalidates the product.
Symlinked ancestors such as a system temporary directory are supported; product roots and members cannot be links.
Input changes during generation prevent certification, and the final stamp is replaced atomically after validation.
The build also rechecks owned products after all selected steps, catching later importers that resave another
owner's package. Use `Product(name, required_paths, optional_paths=(...))` for format sidecars that may be absent:
their absence, appearance, removal or byte change is part of the product identity. Required roots still must exist.
Optional roots have the same exclusive ownership rules and are not eligible for the portable source cache.

## Inspect a build without running it

```sh
uv run atelier build sandbox --list
uv run atelier build sandbox --plan --explain
uv run atelier build sandbox --json
```

`--plan` and `--dry-run` are aliases. `--explain` and `--json` also imply planning. They do not create build folders,
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
cannot vary. Never rely on `runpy` to clear imported module globals, Blender data or Unreal editor state. The recipe
must reset its own state, and native equivalence checks must cover cold and warm execution in different orders.

The host validates each action's marker, inputs and complete output inventory, saves its individual stamp, and
acknowledges it before the next action starts. A crash on action four preserves valid results from actions one to
three. The host checks completed results again after exit. No-op and already-current actions never enter the batch.
Cache-enabled actions currently execute individually, retaining their normal restore-before-execute behavior.

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

## Migration boundary

Named actions use a persistent file-hash index in `build/<game>/.state/`. It checks file identity, size and nanosecond
mtime/ctime before reusing a hash; directory membership is always rediscovered. Missing or corrupt indexes fall back
to reading files. `--verify` bypasses hash hints. Publication and restoration always verify full output bytes.
Source directories retain the legacy exclusions for bytecode, build-tool caches and Markdown; an explicitly named
file is always included. Named source inputs cannot contain symlinks: declare the real source instead.

Add `cache=True` only to a deterministic, portable Python/Blender action with complete product ownership under
`ctx.out`. Successful actions publish automatically to the local content store; a compatible action in another
checkout restores independent copies before running a generator. A change of unrelated Git revision does not
invalidate the key. The sandbox's `world.block` and `world.placements` are executable examples; run
`atelier build sandbox world` without any native tools.

The key includes command arguments, declared sources, consumed product digests, the managed Python environment or
Blender application, dependency lock and build adapters. Python path/interpreter overrides refuse portable caching.
Cached Blender commands must use `factory_startup=True`. `BLENDER` must resolve to the executable inside the macOS
app bundle. For the standard install, set `BLENDER=/Applications/Blender.app/Contents/MacOS/Blender`; the fingerprint
includes its bundled Python and exporters. A shell wrapper alone cannot identify those resources.
Keep installed tools fixed during one build invocation; the next invocation rediscovers their identities.
A static import check rejects undeclared local helpers, including
package initializers and relative imports. Use `atelier.build_inputs.local_imports(script, roots)` when declaring
their closure. A recipe with many scripts can share an `ImportScanner()` and call `scanner.local_imports(script, roots)`
within that recipe evaluation; create a new scanner on every evaluation so added or removed helpers are discovered.
`toolchain=True` includes the same
installed tool identity for a named action without enabling storage or restoration. Dynamic imports, runtime data
reads and relevant settings still need explicit inputs; this is not a
filesystem sandbox or a complete runtime read auditor. Scripts must not depend on undeclared environment values.

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
