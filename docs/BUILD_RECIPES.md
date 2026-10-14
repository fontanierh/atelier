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
Cached Blender commands must use `factory_startup=True`. Keep installed tools fixed during one build invocation;
the next invocation rediscovers their identities. A static import check rejects undeclared local helpers, including
package initializers and relative imports. Use `atelier.build_inputs.local_imports(script, roots)` when declaring
their closure. Dynamic imports, runtime data reads and relevant settings still need explicit inputs; this is not a
filesystem sandbox or a complete runtime read auditor. Scripts must not depend on undeclared environment values.

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
