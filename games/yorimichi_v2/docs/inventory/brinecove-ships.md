# Brine Cove ships: Nightjar, sloop and per-instance hero hulls

Tool: `tools/migrate/brinecove_ships.py` (tests `tests/test_brinecove_ships.py`). Pure Python, no Blender or Unreal.
It reuses `brinecove_split.py` / `brinecove_split_apply.py` (two minimal shared changes: an optional `assigner` argument on
`split.compute` and `apply.build`, default unchanged).

## Boundary: the generator, not a radius

`procedural/ships.py` builds one `ship()` per `layout.SHIPS` entry. The tool runs the donor's own `ship()` for each entry and
gives every exported tile triangle to the ship whose generator vertices coincide with all three corners (same material, same
ground position within 2 mm). Proof built in: part triangles must equal the generator's count (Nightjar 7,600, sloop 9,328),
no triangle may be owned by two ships, and the three ship tiles' remainder must be empty. The result equals batch 1's
numbers and bounds (Nightjar 172 + 7,428; sloop 6,540 + 2,788), now proven from the generator.

The donor ships with `galleon-hull.glb` present (`HAS_HULL`), so `ship()` skips its procedural hull, deck, cabins, gun ports and
cannons: the tile geometry is **rig only** (bowsprit, masts, tops, crow's nest, yards, standing rigging and ratlines, pennants,
stern flag and skull; sails on the sloop only). Hull, deck and guns are the hero hull model.

## Objects

| Object | Rig part (record, package) | Hull | Notes |
|---|---|---|---|
| `object/brinecove/galleon-nightjar` | `prop/brinecove/galleon-nightjar`, `SM_BC_GalleonNightjar`, 7,600 tris, 7 materials, collision complex | its 4 hull cell groups (1 transform each) of `adopted/brinecove/hero-galleon-hull` | rig and hull move as one object |
| `object/brinecove/sloop-east` | `prop/brinecove/sloop-east`, `SM_BC_SloopEast`, 9,328 tris, 8 materials, collision complex | its 4 hull cell groups | same |
| `object/brinecove/galleon-adventure-hull` | none | the Adventure's 4 hull cell groups | the Adventure's rig stays `object/brinecove/galleon-adventure` (unchanged) |

Settings (`slot_materials` by name, `collision = "complex"`, `full_precision_uvs`, one LOD) are copied from the tile records;
runtime flags (shadow, cull 1,200 m / 600 m for hulls, collision) from the tile and hull groups. Hull cell triangles
(unchanged, shared meshes): 11,549 / 11,323 / 11,560 / 11,533.

## Hull groups

Each hero hull cell group holds all three transforms (layout order: Adventure, Nightjar, sloop). `apply` leaves each cell group
in place with the first (Adventure) transform and appends the other 8 as single-transform groups of the same mesh, so no
earlier group changes position (plant group keys are positional, `towns.group_keys`: `mesh#index` for repeated names). Keys are
computed from the final runtime file at apply time and written to `objects.toml`; `check` re-derives them. The old
`object/brinecove/hero-galleon-hull` entry leaves `objects.toml` at apply (its plain keys no longer exist); its record and actor
retire later.

## Retires (after the import, `objects.py` and a passing `check`)

- Tile records `prop/brinecove/ships-4-2`, `ships-4-3`, `ships-5-3`, their packages and runtime groups.
- Placements `object/brinecove/ships-nightjar-sloop` and `object/brinecove/hero-galleon-hull` (records, actor packages,
  `objects.toml` and `objects.saved.json` entries).
- `adopted/brinecove/hero-galleon-hull` stays: it is the shared mesh unit the three hull instances use.

## Controller sequence

```
DONOR=~/dev/atelier-yv2-donor/build/yorimichi           # generator found at DONOR/../../games/yorimichi/world/regions (or --generator DIR)
CMD="uv run python games/yorimichi_v2/tools/migrate/brinecove_ships.py"
git lfs pull --include="games/yorimichi_v2/unreal/Content/Data/brinecove/runtime.json"
$CMD plan  --donor $DONOR
$CMD paths --donor $DONOR --json            # claim exactly 'apply' first, then 'objects_step', later 'retire'
$CMD apply --donor $DONOR --claim TASK
uv run python games/yorimichi_v2/tools/import/run.py prop/brinecove/galleon-nightjar prop/brinecove/sloop-east --claim TASK
uv run python games/yorimichi_v2/tools/migrate/objects.py region/w09-brinecove --environment region/w00-island --claim TASK \
  --only object/brinecove/galleon-nightjar,object/brinecove/sloop-east,object/brinecove/galleon-adventure-hull
$CMD check --donor $DONOR
uv run python games/yorimichi_v2/tools/test/saved_objects.py --zone brinecove_harbor      # each ship and hull drawn once
$CMD retire --donor $DONOR --claim TASK     # refuses unless check passes; then rerun towns.py (below)
uv run python games/yorimichi_v2/tools/migrate/towns.py
uv run python games/yorimichi_v2/tools/content/check.py
```

Retiring the three tile groups (positions 239 to 243) shifts every later group index by 3, so the positional plant keys in the
generated `objects.toml` tail change; rerun `towns.py` after `retire`. The tool recomputes the hull keys itself in `retire`.
