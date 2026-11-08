# Ownership audit of the adopted records

Counts are from the adopted records on this branch (11,345 packages). "Source coverage" is what the records pin in
`[[sources]]` today: **own** (the unit's model, images or scripts), **generator** (only a reference to a unit that holds
the generator), or **none**. Kind: **unit** is a real editing boundary, **batch** is a sorted or mixed grouping that should
be split. Rows marked done have a units map from the audit tasks A1 to A3.

## Done (units maps with sources)

| Family | Records | Packages | Kind | Sources | Note |
|---|---:|---:|---|---|---|
| brinecove | 202 | 699 | unit | own + generator | feature tiles, hero models, ships |
| belmonte | 216 | 616 | unit | own + generator | 78 saved objects |
| craterpark | 81 | 1265 | unit | own + generator | park pieces |
| megapark | map only | n/a | unit | own + generator | `megapark/units.json` |
| gondola, ferry, belmontetrack | 4, 3, 2 | 96, 66, 146 | batch (landing) | none | being split by their own tasks |
| **horses** (this audit) | 108 | 637 | unit | own + generator | breed, saddle, reins, coat units |
| **japan/hidamari** (this audit) | 57 | 124 | unit | own + generator | 32 props, 20 surfaces, 4 trees |
| **japan/treehouse** (this audit) | 51 | 109 | unit | own + generator | 13 props, surfaces, cell pieces |
| **belmontetrain** (round 2) | 24 | 659 | unit | own (16 furniture) + generator (7 coaches) | 7 rolling-stock models with their doors, 16 furniture models, `generator` |
| **japan/materials** (round 2) | 16 | 78 | unit | generator only | `base-materials` (27 parents and the generator) plus 15 surface-family and tree-impostor units |
| **japan/textures** (round 2) | 14 | 54 | unit | own for 10 units, generator for the rest | per tree species (8), `leaf-atlases`, `bark`, `ground`, `rock`, `plaza-harbor`, `sky-water` |
| **japan/foliagelods** (round 2) | 22 | 116 | unit | own (generator settings) | 10 tree families, 8 forest or Tuscan species, 4 bush and grass families |
| **japan/audio** (round 2) | 8 | 533 | unit | generator only (restricted) | 7 footstep banks plus `generator` (bank, fetch, slice, licence) |

## Still to split

| Family | Records | Packages | Kind | Sources | Proposed split |
|---|---:|---:|---|---|---|
| skateride/clips | 68 | 3324 | batch by clip prefix, 200-package chunks (`r_01`, `g_02`) | none | One unit per animation clip set (e.g. `5050-bf-bsgrab`) from a `[[group]]` key per clip stem. **Rule change needed**: `/Game/SkateRide/Clips/B0` and `/B1` already have `[[group]]` rules (`^([0-9A-Z]+)_`), so no units map can sit there. Replace the key with the clip stem (strip the `_CYC/_IN/_OUT/_N_0` direction tokens) and keep 200-package chunks off. Sources: not located in the donor (the clip libraries are not committed); confirm whether they are restricted, which keeps the pinned route, before listing any. |
| experiments/citysurfaces | 89 | 1049 | batch (`*_cell_*` group rule, `_01..04` chunks) | none | `HD_NorthMountains_01..04`, `HD_Terrain` etc. are generated 128 m terrain cells. One unit per surface layer and area (`north-mountains-x-y`). **Rule change needed**: folder `/Game/Experiments/CitySurfaces/v1_128m` has a `[[group]]` rule. Generator: `city_surface_tiles.py`, `city_terrain_surface.py` and the island layout (same closure as Belmonte north). |
| experiments/islandterrain | 8 | 288 | batch (`FarHills_01..02`, terrain chunks) | none | Per-cell units with the terrain generator as source. **Rule change** as above for `/Game/Experiments/IslandTerrain/v1_atomic`. |
| experiments/citytrees, villageatomic | 2 | 55 | unit | none | Per tree variant; generator `build_foliage_lods.py` and the city tree LOD scripts. |
| japan/assets | 58 | 131 | unit | none | Already split by `[[group]]` into bike, sailboat, treehouse, zeppelin and mega pieces; sources need per-model GLB/FBX and generator references. Rule `/Game/Japan/Assets` stays. |
| japan/southwest, lake, animation | 1 each | 31, 5, 1 | unit | none | Fine as units; add sources. |
| adventure, cairoadventure | 2, 1 | 123, 113 | batch (`reference`, `loose_files`) | none | One unit for the shared adventure skeleton and one per clip family. |
| modori, paul, nox, swordtrainer, cairo | 3, 3, 3, 3, 2 | 131, 130, 130, 129, 21 | mixed (character: `adventure` 121 clips + `loose_files` + `textures`) | none | Per character: mesh and rig unit, clip-set units (sword, locomotion, pose), textures. Sources: character GLB/FBX in `assets/characters`. |
| modoribike, noxbike, paulbike, cairobike; *horse | 4; 4 | 10 each; 13 each | unit | none | Fine as units: add the clip sources. |
| audio/skate, transport, combat, bike, driving | 5 | 200 | batch (one record per bank) | none | Per cue family; sources from `assets/audio`. |
| skatepark | 4 | 47 | mixed (`loose_files` 17, textures, materials, board) | none | Per feature (pier, decals, board) with generator `skatepark` region scripts. |
| hippodrome | 4 | 31 | mixed (`loose_files`) | none | Per model (finish post...) from the Belmonte hippodrome GLBs. |
| swordcamp, wanderer, skatemotion, foxhunter, fx | 3, 2, 2, 2, 2 | 17, 29, 27, 21, 12 | small mixed | none | Small; split `loose_files` by model. |
| seethrough, racing, skateruntime | 1 each | 1 each | unit | none | Single packages; nothing to split. |

## Round 2 notes

- **belmontetrain**: the carriages are generated; they have no model of their own, so each coach unit references
  `generator` (carriage scripts, source record, livery and detail images, line data). Furniture units pin their fitted GLB
  and fit report.
- **japan/audio**: restricted route (`restricted.toml` lists `/Game/Japan/Audio`). No audio is copied. The Sonniss masters
  are not in the repository; the bank records are the pinned copies. Open gap: the masters and the build `manifest.json`
  that maps each one-shot to its source file and offset.
- **japan/textures, materials, foliagelods**: open gaps are the images of `plaza-harbor` and `sky-water` textures and the
  surface-family materials (generated by `base-materials`' scripts, with no image of their own).
- **horses**: `/Game/Horses` is a restricted root (animation origin not recorded). The unit sources are the donor's
  committed GLBs; the controller should confirm that pinning those GLBs in public records is allowed before applying
  the horse map.

## Totals

- Packages with a units map and sources: Brine Cove 699, Belmonte 616, Crater Park 1265, Mega Park, Horses 637, Hidamari 124,
  Tree House 109.
- Largest remaining batches: skateride 3331, experiments 1392, japan audio 533, belmontetrain 659, belmontetrack 146.

## Exact rule changes (not applied; `groups.toml` is the controller's)

### SkateRide clips: one unit per complete move family

The packages are 2672 in B0 and 652 in B1, named `<CATEGORY>_<TRICK>_<VARIANT>...` (`INVERT_HANDPLANT_BS_...`,
`MVOBJ_PULL_45_...`). Replace both rules; the third token keeps every unit under the 200 cap (B0 largest 36, B1 largest 72
with two tokens) so no unit is chunked:

```
[[group]]
folder = "/Game/SkateRide/Clips/B0"
key = '^([0-9A-Z]+_[0-9A-Z]+_[0-9A-Z]+)(?:_|$)'

[[group]]
folder = "/Game/SkateRide/Clips/B1"
key = '^([0-9A-Z]+_[0-9A-Z]+)(?:_|$)'
```

B0 gives 644 families (names with fewer than three tokens become units of their own), B1 gives 47. The lock and
`restricted.toml` keep the route: every record stays under the restricted roots. **Open gap**: the original clip sources
(mocap library) are not in the donor; no source is listed until their location and licence are recorded.

### Experiments terrain: spatial areas

`HD_Terrain_cell_<x>_<y>`, `HD_NorthMountains_cell_<x>_<y>`, `FarHills_cell_<x>_<y>` are generated 128 m cells, so one
`_cell` key per layer produces the `_01..04` chunks. A regex cannot bucket numbers, so replace the two rules with
units maps (folder rule becomes `[[units]]`), each unit being `<layer>-<ax>-<ay>` with `ax = floor(x / 8)`,
`ay = floor(y / 8)` (a 1024 m area), `generator` holding the surface scripts:

```
[[units]]
folder = "/Game/Experiments/CitySurfaces/v1_128m"
map = "experiments/citysurfaces/units.json"

[[units]]
folder = "/Game/Experiments/IslandTerrain/v1_atomic"
map = "experiments/islandterrain/units.json"
```

The two maps are not written yet (the area writer is the next task); they would pin `city_surface_tiles.py`,
`city_terrain_surface.py` and the island layout closure as generator sources.

### Earlier proposals

One rule per folder holds, so these folders need their `[[group]]` rule replaced before a units map can sit there:

1. `/Game/SkateRide/Clips/B0` and `/B1`: replace the `^([0-9A-Z]+)_` key with a clip-stem key, or switch to `[[units]]`.
2. `/Game/Experiments/CitySurfaces/v1_128m` and `/Game/Experiments/IslandTerrain/v1_atomic`: replace `^(.*?)_cell` with a
   per-area key, or switch to `[[units]]` with a generator unit.
3. `/Game/Japan/Assets`: keep; add sources through the existing group names.

## Entries to add for this audit

```
[[units]]
folder = "/Game/Horses"
map = "horses/units.json"

[[units]]
folder = "/Game/Japan/Hidamari"
map = "japan/hidamari/units.json"

[[units]]
folder = "/Game/Japan/Treehouse"
map = "japan/treehouse/units.json"
```

## Open gaps in the three new maps

- Horses: none. Clips are read from the breed's `horse.glb`.
- Hidamari: `surface-flat` (parametric, no image); Caldera trees pin the raw generated model and job records only.
- Tree House: `surface-flat`, `-glass`, `-pane`, `-rope`, `-trunk` (no image of their own); the six cell piece units
  (dressing and structure cells) are generated, with sources in `generator` only.

## Sources under restricted roots

`restricted.toml` restricts the Unreal packages under `/Game/Horses` and `/Game/CraterPark` (animation origin, and a
license not recorded yet). Those packages stay git-ignored and pinned. The sources the Horses and Crater Park units
copy are only files the donor game already tracks in this repo (checked: every copied path is `git ls-files` under
`games/yorimichi/`), so copying them exposes nothing new. A restricted unit whose originals are not committed (audio
masters, SkateRide clip libraries) lists no sources and keeps the pinned route.
