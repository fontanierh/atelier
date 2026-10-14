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

The scripts write their declared paths. They must declare imported helpers, data, settings and tool inputs that
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

Named products currently verify their full contents on every check. A persistent file-hash index is still planned
before large Unreal package inventories migrate; this phase does not claim the final no-op timing target.
`atelier reuse` and the portable pool reject recipes that try to certify named products through their older protocols.
Existing recipes remain supported. Automatic product caching, transactional Unreal restoration, import ownership,
registry refresh, relocation and remote storage are described in [the architecture](INCREMENTAL_BUILDS.md) and are
not enabled by these declarations. Keep native imports conservative until their clean/incremental equivalence checks
pass, following [world build practices](WORLD_BUILD_PRACTICES.md).
