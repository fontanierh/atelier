# Remaining exceptions to "one object, one owner"

Measured on branch `jim5/yv2-prep-exceptions` (code-only checkout, LFS pointers; nothing here needs the binaries). Every
count comes from the commands at the end, which read the records with `tools/content/records.py`. The older figures in
`sources.md` and `ownership-audit.md` describe `origin/main` before the unit splits landed and are superseded for counts.

Rule used: an object is independent when it has its own record and claim scope, its own packages, and either a source or
recipe that re-makes it or a saved editor package that is its own source. All 1,505 `adopted/*` records and all 2,470
`object/*` placements are `editor-saved` (`verified.json` present), so they can be edited; the gaps below are about
sharing, restriction, missing sources and area patches that hold many things.

## Already in progress (not counted)

experiments/citysurfaces, belmontetrain, japan vehicle (bike, sailboat, treehouse, zeppelin), treehouse, southwest, lake,
hidamari, skatepark, megapark, swordcamp, fx, racing, skateruntime, citytrees, villageatomic.

## Exception groups

| # | Group (records or glob) | Records | Packages | Why it is not independently editable | Next action, by whom | Proof it is fixed |
|---|---|---:|---:|---|---|---|
| G6 | Area-patch actors with no placement record: `world/regions/*/patches.json` entries whose package no `object/*` record owns and whose key is not scatter. Ground/terrain/edges 1,245 (29 keys), buildings 574 (43 keys, e.g. `HD_Shop_*`, `HD_House_*`), props/other 451 (66 keys, e.g. `HD_P_*`, `Pole_Lamp`, `HD_Lamp`) | 2,270 actors (0 records) | 2,270 | Each patch actor is a World Partition actor that bundles several instances; the thing has no record, so it cannot be claimed alone. Scatter (6,988 actors, 42 keys) stays area by design | Planner: extend `objects.toml` promotion (`patch-objects.md` rule: one instance, one patch, a thing) for the 574 building and 451 prop actors, and a cell-split rule for multi-patch buildings (`HD_Shop_*` has 9 to 44 patches each). Ground stays area: owner decision to accept it as an area scope. Then Unreal save per region | Re-run script, lines `G6 unowned building` and `G6 unowned prop/other` fall to 0 and `G6 owned by a placement record` rises by the same amount |
| G1 | Restricted, pinned, no editable route: `adopted/skateride/*` 692, `adopted/craterpark/*` 68, `adopted/japan/audio/*` 7, `adopted/audio/*` 4, characters and mounts 29 (`modori`, `nox`, `paul`, `cairo`, `swordtrainer`, `wanderer`, `foxhunter`, `skatemotion`, `cairoadventure`, and the `*bike`, `*horse` records) | 800 | 5,976 | Packages are git-ignored under `restricted.toml`; the original (mocap clips, Sonniss masters, rights not recorded, D05 group 1 and 2) is not in the repository, so no source or recipe can be listed and edits need the private store | Owner decision (D05): clear or keep each root. A cleared root leaves `restricted.toml`, then the planner pins sources. Crater Park is the owner's own park: ask for the licence statement first (68 records, 1,112 packages). Until then they stay pinned and are edited only through `fetch.py` | `V2_RESTRICTED_SOURCE=DIR uv run python games/yorimichi_v2/tools/restricted/fetch.py fetch` passes, and the script's `G1 restricted TOTAL` falls as roots leave the list |
| G4a | Brine Cove fused tile meshes (`prop/brinecove/{ships-4-*,ships-5-*,harbor*,props*,market*,town-*}`): one mesh holds several useful objects (Nightjar plus sloop; shipyard, cranes and crates; cannons, anchor and props; 19 market stalls; town houses) | 234 | 234 | One package shared by several objects; faces are bucketed by 256 m tile, so one house or stall cannot be claimed alone (`brinecove-objects.md`) | Planner: change the generator so each object has its own Builder and mesh (Nightjar, sloop, shipyard, cannons x2, anchor, 19 stalls, per-building town houses), keep `modules.props` RNG draw order. Then Unreal save of the new placements | Script line `G4 brinecove fused tile meshes` falls; `uv run python games/yorimichi_v2/tools/content/check.py` stays OK |
| G4b | Brine Cove hero models: `adopted/brinecove/hero-galleon-hull` (3 hulls in 4 cell meshes), `hero-harbor-capstan` (2 capstans), `hero-pirate-queen-statue` (4 cells) | 3 | 41 | Each record bundles all instances, so one hull or one capstan is not alone. Statue is alone but spread over cells | Planner: one hero group per transform; allow `groups = [...]` per object in `objects.toml` | Script line `G4 brinecove hero models` shows one record per object |
| G4c | In-scope `adopted/japan/assets/*` records that hold several objects: `house` (A/B/C), `houselot` (5), `pole` (Pole, Pole_Lamp), `bush` (6), `grass` (2), `rock` (3), `bird`, `mega-park-pieces`, 8 `tree-*` families | 16 | 52 | One record per group key (`groups.toml` rule for `/Game/Japan/Assets`), several useful objects in one claim | Planner: change the rule so `key` captures the whole name for these prefixes (as proposed for ZP in `transport-objects.md`), 52 single-package records. Overlaps G3 (same records) | Script line `  of which one record, several objects` goes to 0 |
| G3 | Open, editor-saved but no `[[sources]]` or recipe, generator present in the donor: `adopted/japan/assets/*` non-vehicle 54 (16 of them are G4c), `adopted/japan/materials/*` 7, `adopted/brinecove/plant-*` 9, `adopted/hippodrome/*` 3, `adopted/japan/textures/{plaza-harbor,sky-water}` 2, `adopted/belmonte/shared-{metal-glass,water}` 2, `adopted/seethrough` 1 | 78 | 208 | Editable now (saved package is the source) but cannot be re-made: no source file or recipe is pinned. The plants, textures and materials are parametric with no image. Seethrough is a material parameter collection (editor-owned candidate) | Planner: pin generator closures as `[[sources]]` (donor scripts named in `sources.md`). Hippodrome: GLBs from the Belmonte hippodrome. Seethrough: owner confirms editor-owned. Parametric materials list the generator only | Script line `G3 TOTAL` falls to 0 |
| G2 | Generator missing in the donor: `adopted/adventure/reference` (121 clips), `adopted/adventure/loose_files` (2), `adopted/japan/animation` | 3 | 124 | The clip libraries and the animation origin are not committed or recorded, so there is nothing to pin | Owner decision: locate the source and its licence; if it cannot be found, mark restricted or editor-owned and add the root to `restricted.toml` | Script line `G2 generator missing` goes to 0 |
| G5 | Editor-owned maps: `map/slice` and `map/test-minimal` | 2 | 6 | The maps are `editor-saved` but one map package set is shared by all regions (`maps = ["/Game/V2/Maps/Slice"]`); a region claim covers its actors, not the map | Planner: confirm the map claim scope is separate from region actors; Unreal save only for map-level edits | `uv run python games/yorimichi_v2/tools/content/save_validate.py map/slice` reports no change |

Not computed here, from `transport-objects.md`: the Hidamari train platform and buffer have no mesh at all (runtime `Block()` boxes),
and the arrival boards are live text. They need an owner decision on whether they are objects, then a model; no record exists.
`object/harbour/temples` (8), `clock-hall` (4) and `station/station-building` (4) are single objects that span several actor
packages; they are one record each by design and are not exceptions.

## Totals

**Remaining: 1,120 records without independent ownership or source (G1 800, G2 3, G3 78 of which 16 also in G4c, G4a 234, G4b 3, G5 2) plus 2,270 area-patch actors with no record (G6); 6,988 scatter actors stay area by design.**
Distinct record count is 1,120 because G3 and G4c share 16 records and that overlap is counted once. G1 is 5,976 of the 9,069 packages once called source-less in `sources.md`.

## Commands

Run from the repository root, in the worktree. Read-only. The script below needs only the standard library and
`games/yorimichi_v2/tools/content/records.py`.

```
python3 exceptions_count.py games/yorimichi_v2        # script below, saved anywhere outside the repo
uv run python games/yorimichi_v2/tools/content/check.py --allow-restricted-absent   # reads the whole content tree; needs LFS binaries for hashes
```

```python
import sys, json, re, collections
from pathlib import Path
GAME = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(GAME / 'tools/content'))
import records
A, regions = records.discover(GAME)
R = records.load_restricted(GAME)
def fam(a):
    p = a.id.split('/'); return '/'.join(p[1:3]) if p[1] in ('japan', 'experiments') else p[1]
def srcless(a): return not a.sources and not a.recipe
def pk(rs): return sum(len(a.outputs) for a in rs)
def show(name, rs): print(f'{name:48} records={len(rs):5} packages={pk(rs):5}')
adopted = [a for a in A if a.id.startswith('adopted/')]
restr = [a for a in adopted if srcless(a) and any(R.covers_package(o.package) for o in a.outputs)]
print('all records', len(A), 'adopted', len(adopted), 'adopted source-less', sum(map(srcless, adopted)))
# G1 restricted
chars = {'modori','nox','paul','cairo','swordtrainer','wanderer','foxhunter','skatemotion','cairoadventure'}
def isbm(f): return f.endswith(('bike','horse'))
g = collections.defaultdict(list)
for a in restr:
    f = fam(a)
    k = 'skateride' if f=='skateride' else 'craterpark' if f=='craterpark' else f if f in ('japan/audio','audio') else 'characters-mounts'
    g[k].append(a)
for k, rs in g.items(): show('G1 restricted ' + k, rs)
show('G1 restricted TOTAL', restr)
# G2 generator missing
g2 = [a for a in adopted if srcless(a) and fam(a) in ('adventure', 'japan/animation')]
show('G2 generator missing', g2)
# G3 open source-less, generator present, in scope
rest_ids = {a.id for a in restr}
done = ('experiments/citysurfaces','belmontetrain','japan/treehouse','japan/southwest','japan/lake','japan/hidamari','skatepark','megapark','swordcamp','fx','racing','skateruntime','experiments/citytrees','experiments/villageatomic')
vehicle = re.compile(r'^adopted/japan/assets/(bike|sailboat|treehouse|zeppelin)$')
g3 = [a for a in adopted if srcless(a) and a.id not in rest_ids and fam(a) not in done and fam(a) not in ('adventure','japan/animation') and not vehicle.match(a.id)]
for f in sorted({fam(a) for a in g3}): show('G3 ' + f, [a for a in g3 if fam(a)==f])
show('G3 TOTAL', g3)
# G4 shared package: multi-package model records referenced by placements (japan/assets, non vehicle) and hero records
ja = [a for a in adopted if fam(a)=='japan/assets' and not vehicle.match(a.id)]
show('japan/assets in scope (non-vehicle)', ja)
show('  of which one record, several objects', [a for a in ja if len(a.outputs)>1])
show('  of which one package', [a for a in ja if len(a.outputs)==1])
heroes = [a for a in adopted if a.id.startswith('adopted/brinecove/hero-')]
show('G4 brinecove hero models', heroes)
tiles = [a for a in A if a.id.startswith('prop/brinecove/') and re.match(r'prop/brinecove/(ships-4-|ships-5-|harbor|props|market|town-)', a.id)]
show('G4 brinecove fused tile meshes', tiles)
# G5 maps
show('G5 maps', [a for a in A if a.kind=='map'])
# G6 area patches
placed = {o.package for a in A if a.kind=='placement' for o in a.outputs}
scatter = re.compile(r'^(Tree_|Bush_|Grass|Litter|Rock_|Pole$|Plant|Flower|Fern|Reed|Palm|Shrub)')
ground = re.compile(r'(Terrain|Mountains|NorthRock|Streets|Square|Harbor$|Park$|Edges|Ground|Island|Water|Shore|Trail|Wires|Gardens|Details|Threshold|Planting|Roads?$|Sea|Beach|Cliff|Hill)')
build = re.compile(r'(Shop|House|Cottage|Storehouse|TeaHouse|Workshop|Temple|Cabin|Frame|Structure|Dressing|Boat|Dock|Stairs|Hall|Tower|Station|Arcade|Villa|Shed|Rack|Stand)')
c = collections.Counter(); keys = collections.defaultdict(set)
for r in regions:
    pf = r.folder / 'patches.json'
    if not pf.exists(): continue
    for p in json.loads(pf.read_text())['patches'].values():
        pkg = '/Game/' + p['package'].split('unreal/Content/')[1].rsplit('.', 1)[0]
        c['patch actors'] += 1
        if pkg in placed: c['owned by a placement record'] += 1; continue
        k = p['key']
        cls = 'scatter (area by design)' if scatter.match(k) else 'ground/terrain/edges' if ground.search(k) else 'building' if build.search(k) else 'prop/other'
        c['unowned ' + cls] += 1; keys[cls].add(k)
for k, v in sorted(c.items()): print(f'G6 {k:40} {v}')
for k in keys: print('G6 distinct keys', k, len(keys[k]))
print('G6 placement records', sum(a.kind=='placement' for a in A), 'objects.toml entries', sum(len(__import__("tomllib").loads((r.folder/'objects.toml').read_text()).get('objects',[])) for r in regions if (r.folder/'objects.toml').exists()))
```
