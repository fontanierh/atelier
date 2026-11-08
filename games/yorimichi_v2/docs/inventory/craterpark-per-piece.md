# Crater Park per piece

Prototype and plan for regrouping Crater Park's render meshes and collision by park piece
(`tools/migrate/craterpark_per_piece.py`). Gap 1 of the Crater Park units audit: today 22 of 26 collision pieces
and 177 of 1123 render meshes mix several pieces, so no piece can be edited without claiming its neighbours.

## What the regrouped outputs are

The input is the donor generator's own geometry (`editor_generate.py` on `tools/craterpark_editor/shipped.json`,
rev 114), which reproduces today's 1123 render and 26 collision names exactly. Every face carries a feature name
(`p9`, `p9_supports`, `editor_coping_004`, `crater_floor`). The prototype assigns each face to an owner:

- a piece, with its `_supports`, `_tower` and `_shrine` features;
- a coping rail goes to the piece it rides (`coping_rides` in `assets/adopted/craterpark/craterpark_ownership.json`);
- `crater_floor` faces go to 16 area blocks of 4 x 4 tiles (256 m), as in `units.json`.

Then it writes, per owner (to `build/craterpark-per-piece/`, not committed):

- `render_<role>_<material>[_k].npz`: the owner's faces of one role and material, in z-order, at most 30000
  triangles each (today's `MAX_RENDER`; the atomic budget is 32768). Arrays: `V N UV AO F material tag`.
- `collision_<k>.npz`: the owner's collision triangles, z-ordered, at most 32768 per file (today's `_PieceNNN`).
- `summary.json`: the counts below and the exactness proof.

**Exactness.** The multiset of render triangles (positions rounded to 10 um, material, tag) and of collision
triangles is hashed before and after: both are identical (1,100,476 render and 757,537 collision triangles). No
collision triangle is unmatched to a render face. Only the grouping changes, so appearance and contact are unchanged
(normals, UVs, AO ride along per face).

## Counts

| | Today | Per piece |
|---|---:|---:|
| Render meshes (draw calls, one material each) | 1123 | 318 |
| Collision pieces | 26 | 81 |
| Render triangles | 1,100,476 | 1,100,476 |
| Collision triangles | 757,537 | 757,537 |
| Mixed render meshes | 177 | 0 |
| Mixed collision pieces | 22 | 0 |
| Owners | none | 57 pieces + 16 floor blocks |

The 81 collision pieces are 57 (one per piece) + 16 (one per floor block) + 8 extra for the pieces over 32768
triangles (p5 has 6 pieces, p9 3, p10 2).

Per owner:

| Owner | Name | Render meshes | Render tris | Collision pieces | Collision tris |
|---|---|---:|---:|---:|---:|
| p10 | w1 · 1 | 3 | 39,706 | 2 | 39,706 |
| p11 | w1 · 2 | 2 | 2,220 | 1 | 2,220 |
| p12 | w1 · 3 | 3 | 668 | 1 | 668 |
| p13 | w1 · 4 | 3 | 2,852 | 1 | 2,852 |
| p14 | w1 · 5 | 2 | 1,650 | 1 | 1,650 |
| p183 | Orange tower (ladder from the tower deck) | 10 | 66,774 | 1 | 3,890 |
| p184 | U-turn infill | 2 | 560 | 1 | 560 |
| p185 | c2 run-out | 3 | 8,864 | 1 | 8,864 |
| p186 | T spine run-in | 3 | 4,604 | 1 | 4,604 |
| p187 | T mouth run-out | 3 | 1,582 | 1 | 1,582 |
| p188 | T U-turn infill | 2 | 320 | 1 | 320 |
| p189 | in · kick | 2 | 344 | 1 | 344 |
| p190 | in · late kick (+4 m) | 2 | 560 | 1 | 560 |
| p30 | w1b · 16 | 4 | 19,728 | 1 | 12,536 |
| p300 | Vert drop takeoff ledge | 2 | 10 | 1 | 10 |
| p302 | Vert drop run-out | 4 | 1,072 | 1 | 1,072 |
| p303 | Vert drop into the void | 5 | 12,214 | 1 | 2,382 |
| p305 | Vert launch, no assist | 4 | 4,204 | 1 | 4,204 |
| p306 | Reverse catch | 4 | 7,984 | 1 | 7,984 |
| p307 | Vert drop: bend right | 4 | 2,934 | 1 | 2,934 |
| p308 | Vert drop: U-turn bowl | 5 | 21,745 | 1 | 12,653 |
| p309 | Kicker run-up | 5 | 11,894 | 1 | 3,138 |
| p31 | Gap 30 m · g2 | 4 | 31,776 | 1 | 23,288 |
| p310 | Mega air kicker | 4 | 4,222 | 1 | 4,222 |
| p311 | Mega air landing | 3 | 31,194 | 1 | 15,938 |
| p312 | into the orange last section | 2 | 2,738 | 1 | 2,738 |
| p32 | w2 · 1 | 3 | 9,880 | 1 | 9,880 |
| p320 | Step-down 18 m · sd | 3 | 13,692 | 1 | 13,692 |
| p321 | sd out · 1 | 3 | 9,232 | 1 | 9,232 |
| p322 | sd out · 2 | 3 | 8,768 | 1 | 8,768 |
| p33 | w2 · 2 | 3 | 1,574 | 1 | 1,574 |
| p34 | Gap 25 m · g3 | 4 | 25,364 | 1 | 21,432 |
| p35 | w3 · 1 | 3 | 4,534 | 1 | 4,534 |
| p36 | w3 · 2 | 4 | 10,944 | 1 | 7,012 |
| p37 | Gap 30 m · g4 | 4 | 29,482 | 1 | 20,754 |
| p38 | w4 | 3 | 7,398 | 1 | 7,398 |
| p39 | Gap 15 m · g5 | 4 | 10,598 | 1 | 7,794 |
| p40 | w5 · 1 | 2 | 756 | 1 | 756 |
| p41 | w5 · 2 | 4 | 8,900 | 1 | 6,096 |
| p42 | Gap 25 m · g6 | 3 | 28,934 | 1 | 28,934 |
| p43 | Turn t1 | 3 | 29,310 | 1 | 29,310 |
| p44 | a1 | 2 | 1,336 | 1 | 1,336 |
| p45 | Flow bowl | 8 | 24,020 | 1 | 8,184 |
| p46 | vert approach | 3 | 5,704 | 1 | 5,704 |
| p47 | Half bowl U-turn | 6 | 5,518 | 1 | 5,518 |
| p48 | vert mouth | 2 | 972 | 1 | 972 |
| p49 | c2 | 3 | 2,522 | 1 | 2,522 |
| p5 | Crater Bowl (Prado) | 15 | 181,786 | 6 | 169,546 |
| p50 | T approach | 3 | 784 | 1 | 784 |
| p51 | T half bowl U-turn | 8 | 21,430 | 1 | 5,594 |
| p52 | T mouth | 2 | 810 | 1 | 810 |
| p53 | s | 3 | 5,070 | 1 | 5,070 |
| p54 | final | 3 | 3,658 | 1 | 3,658 |
| p55 | Gap 25 m · fgap | 4 | 18,932 | 1 | 10,060 |
| p56 | in | 3 | 4,758 | 1 | 4,758 |
| p8 | Roll-in rollin | 6 | 33,588 | 1 | 19,916 |
| p9 | Mega 55 m · mega | 5 | 96,888 | 3 | 76,160 |
| 16 crater-floor blocks | volcano ground in the crater | 103 | 210,915 | 16 | 98,860 |

## Draw-call and size impact

- **Draw calls fall by 3.5 times** (1123 to 318 render meshes): the 64 m tile cut multiplied meshes; a piece needs
  only its materials (typically 1 to 5 per piece). Collision components rise from 26 to 81, but they are invisible
  static meshes with no draw cost; their cost is the 55 more components in the skating snapshot.
- **Culling gets coarser.** Mean mesh extent grows from 45 m (max 161 m) to 114 m (max 270 m): a long ramp is
  drawn whole once any part is in view. With 4x fewer meshes this is a net gain on the CPU side, but a loss of
  fine occlusion. The crater floor stays in 256 m blocks.
- **Size.** The prototype npz files are unwelded (three vertices per triangle): 3.30 M vertices against today's
  1.54 M, 328 MB of npz against 146 MB of arrays. This is an artefact of the prototype, not of the regrouping; the
  importer welds equal vertices (as today's FBX path does), so the cooked size is the same as today to within the
  few vertices split at the new piece edges (a piece edge duplicates its boundary vertices once).
- **Collision grouping.** The skate simulation reads 64 stored triangles at a time in z-order. Each piece is
  still z-ordered inside itself, so locality is unchanged; only triangles of different pieces no longer share a
  group.

## Cannot be separated cleanly?

Every face has exactly one feature, so every piece separates at the triangle level with no unmatched triangle.
These caveats remain:

1. **Coping rails are assigned by a nearest-surface vote.** The generator names them `editor_coping_000..027`, not
   after a piece. Where a rail runs along a junction of two pieces the vote picks one (not audited rail by rail). It is
   deterministic, but an editor-side rail-to-piece id would remove the guess.
2. **Floor is not a piece.** The crater floor (210,915 triangles, 19% of render) is the volcano's ground cut by
   the park; it only exists as the 16 area blocks and is rebuilt when any piece cuts the ground.
3. **Render-only geometry.** p183 has 66,774 render triangles but 3,890 collision triangles (the shrine props and
   tower dressing); this is the same as today, not a defect.
4. **Rails** (`cp_lip_*` in `park.json`) are data, not meshes, and already separate.
5. **Large owners.** p5 (181,786 render triangles, 15 meshes, 6 collision pieces) and p9 (96,888) cannot be one mesh
   because of the 32768-triangle atomic budget; they stay several files of one record.
6. **Neighbouring pieces' triangles are not merged or changed, so the seam looks as today** (the exactness check
   covers this; overlap between pieces was not audited).

## What V2 needs to adopt this

Today: `Content/Data/craterpark/park.json` lists `render` and `collision` entries (`name`, `origin_cm`) under
`mesh_root` `/Game/CraterPark/Meshes`; `ASuperUltraMegaPark::Spawn` loads each mesh and attaches one static mesh
component at `origin_cm` under one actor placed by `location_cm` and `yaw_deg`. Rails, assist and boost zones,
spawns and trees are in the same file. It does not care how meshes are grouped, only what the lists name.

Needed changes, in order:

1. **Generator (donor side, then ported).** In `v2/split.py`, replace the 64 m tile key of `render_meshes` with the
   owner key (piece, or floor block) and `collision_sections` with the owner key; the face-to-owner map is
   `craterpark_per_piece.py` (needs the editor's rail-to-piece map in `generate.bundle`'s index). Names become
   `SM_CP_<owner>_<role>_<material>[_k]` and `UC_CP_<owner>_<k>`.
   `atomic_inputs.py` already writes one packet per name; its 32768 split and the `Piece` names stay.
2. **Importer.** `import_craterpark.py` and the V2 native importer need no change beyond the new names; the mesh
   name pattern `SM_CP_*`/`UC_CP_*` is kept, and each material stays one section.
3. **Records.** One generated record per owner, `adopted/craterpark/<owner>-<slug>` (today's unit names from
   `units.json`), each with: its meshes (the packages above), the material instances and textures only it uses,
   `references` to `materials-base`, and a recipe: the owner id, the `shipped.json` piece entry (type, name, line,
   params) pinned by hash, the generator revision (`pin.json` of the compiler), and the render/collision file hashes
   from `summary.json`. Sources: as in `units.json` (the generator unit holds the scripts and `shipped.json`).
   `craterpark_units.py` then maps every package by name instead of through the ledger, and
   `craterpark_ownership.json` is retired.
4. **Runtime.** Regenerate `Content/Data/craterpark/park.json` with the 318 render and 81 collision entries (name,
   `origin_cm` from `export.origin_of`). `ASuperUltraMegaPark::Spawn` and the CraterPark service
   (`CraterParkTower`, spawns, assist and boost zones, `w12-craterpark` region) are unchanged. For true
   independent edits, give each entry its owner id (`piece` field, ignored today) so a later runtime can stream or
   hide one piece, and keep the actor placement shared.
5. **Claims and cook.** The 16 floor blocks and 57 pieces become 73 claimable records; the shared materials and
   textures stay as in `units.json`. Moving one piece changes its own packages and the floor block it cuts; no
   other piece's packages change (z-order is within the piece).
6. **Validation before cut-over.** Run the prototype's exactness check on every geometry rebuild (it exits 1 on a
   triangle difference), compare the rider-contact snapshot against the current park on the lines L1, L2 and p5, and
   confirm the draw-call count (318).

## Reproduce

```
uv run python games/yorimichi/world/regions/craterpark/v2/editor_generate.py \
  --park games/yorimichi/tools/craterpark_editor/shipped.json --out build/craterpark/v2
uv run python games/yorimichi_v2/tools/migrate/craterpark_per_piece.py build/craterpark/v2/geometry.npz
```
