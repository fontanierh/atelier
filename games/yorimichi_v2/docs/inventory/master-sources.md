# Generator-built master materials: recovery design

Status: proposal and inventory. Nothing is imported, claimed or pushed. The machine-readable inventory is
[master-sources.json](master-sources.json); the held list is [small-families-masters.txt](small-families-masters.txt).
Donor paths are relative to the donor root `games/yorimichi/`. Pins are sha256 of the committed blob at the V2 source
baseline `7eec0f98dd` (docs/DECISIONS.md D01), not of the donor working tree, which is dirty.

A generator-built master stays `authority = "generated"` until its generator, settings and inputs are recoverable in
V2 (plan section 4, "generated art needs its generator, settings and inputs"; section 5, ownership cases). A parameter
read alone does not close one. This document proposes how to make them recoverable. It does not convert any master to
editor-owned; section 6 lists the conversions that are a decision for the owner.

## 1. What the inventory covers

27 masters: the 19 in `small-families-masters.txt`, the three Mega Park retail parents named in the brief
(`M_RetailOpaque`, `M_RetailMasked`, `M_RetailTranslucent`), `M_HDCity`, the hidamari family's master
(`adopted/japan/hidamari/generator`), and the four plaza masters `M_Arcade`, `M_ArcadePaving`, `M_Harbor` and `M_HarborWater`
(section 2a). Each row of the JSON gives the donor generator file, the exact line range that
builds the graph (asserted against the baseline bytes when the inventory was generated), every input with its V2
owner record, and every helper with its sha256.

The four plaza masters were left out of the first pass and are added in this one. They are generator-built too and
owned by `adopted/japan/materials/base-materials`. Decision 4 (section 7) records that they belong in the same recovery.

## 2. Per-master table

Fit: **direct** = the builder can be carried by a material-master recipe as it is, once its generator is pinned and its
texture inputs are recorded; **needs helper** = the builder calls a donor helper that V2 must port (pure code, no
Unreal change); **not recoverable** = none of the 23 is. Every texture input below has an owner record, and the test
`test_every_texture_input_is_an_output_of_the_owner_record_it_names` checks that the record outputs the package.

| Master | Record | Generator file:lines (builder) | Inputs (V2 owner) | Fit |
|---|---|---|---|---|
| `/Game/Hippodrome/Materials/M_HD_Structure` | `adopted/hippodrome/materials` | `unreal/Scripts/import_hippodrome.py`:59-78 (structure_material) | WhiteSquareTexture (engine) | direct |
| `/Game/Hippodrome/Materials/M_HD_Grass` | `adopted/hippodrome/materials` | `unreal/Scripts/import_hippodrome.py`:36-55 (surface) | T_Grass (texture/hippodrome/grass); the donor texture helper only | direct |
| `/Game/Hippodrome/Materials/M_HD_Dirt` | `adopted/hippodrome/materials` | `unreal/Scripts/import_hippodrome.py`:36-55 (surface) | T_Dirt (texture/hippodrome/dirt); the donor texture helper only | direct |
| `/Game/Hippodrome/Materials/M_HD_Stone` | `adopted/hippodrome/materials` | `unreal/Scripts/import_hippodrome.py`:36-55 (surface) | none (constants) | direct |
| `/Game/Hippodrome/Materials/M_HD_Rail` | `adopted/hippodrome/materials` | `unreal/Scripts/import_hippodrome.py`:36-55 (surface) | none (constants) | direct |
| `/Game/SkatePark/Materials/M_Pier_basalt` | `adopted/skatepark/materials` | `unreal/Scripts/import_skatepark.py`:132-174 (materials, per-key loop body) | T_Pier_basalt_albedo, _normal, _roughness (texture/skatepark/pier-basalt-*) | direct |
| `/Game/SkatePark/Materials/M_Pier_ceramic` | `adopted/skatepark/materials` | `unreal/Scripts/import_skatepark.py`:132-174 | T_Pier_ceramic_albedo, _normal, _roughness (texture/skatepark/pier-ceramic-*) | direct |
| `/Game/SkatePark/Materials/M_Pier_concrete` | `adopted/skatepark/materials` | `unreal/Scripts/import_skatepark.py`:132-174 | T_Pier_concrete_albedo, _normal, _roughness (texture/skatepark/pier-concrete-*) | direct |
| `/Game/SkatePark/Materials/M_Pier_mural` | `adopted/skatepark/materials` | `unreal/Scripts/import_skatepark.py`:132-174 | T_Pier_mural_albedo (texture/skatepark/pier-mural-albedo) | direct |
| `/Game/SkatePark/Materials/M_Pier_painted` | `adopted/skatepark/materials` | `unreal/Scripts/import_skatepark.py`:132-174 (metallic 0, line 134) | T_Pier_painted_albedo, _normal, _roughness (texture/skatepark/pier-painted-*) | direct |
| `/Game/SkatePark/Materials/M_Pier_steel` | `adopted/skatepark/materials` | `unreal/Scripts/import_skatepark.py`:132-174 | T_Pier_steel_albedo, _normal, _roughness (texture/skatepark/pier-steel-*) | direct |
| `/Game/SkatePark/Materials/M_Pier_wood` | `adopted/skatepark/materials` | `unreal/Scripts/import_skatepark.py`:132-174 | T_Pier_wood_albedo, _normal, _roughness (texture/skatepark/pier-wood-*) | direct |
| `/Game/SkatePark/Board/M_BoardDissolve` | `adopted/skatepark/board` | `unreal/Scripts/board_dissolve_material.py`:1-95 (module body) | none (constants and Dissolve scalar) | direct |
| `/Game/SwordCamp/Materials/M_SwordCamp` | `adopted/swordcamp/materials` | `unreal/Scripts/import_swordcamp.py`:46-113 (build_material) | T_SwordCampAtlas (texture/swordcamp/atlas); helper atmosphere.py | needs helper |
| `/Game/SwordCamp/Materials/M_RoninBody` | `adopted/swordcamp/materials` | `unreal/Scripts/import_swordcamp.py`:116-171 (build_ronin_body_material) | T_SwordCampAtlas (texture/swordcamp/atlas) | direct |
| `/Game/Racing/M_RacingTv` | `adopted/racing` | `unreal/Scripts/racing_tv_material.py`:1-57 (module body) | Black (engine); Picture is a runtime render target | direct |
| `/Game/FX/M_FX_Additive` | `adopted/fx` | `unreal/Scripts/import_combat_fx.py`:52-70 (sprite_material) | T_FX_Glow (texture/fx/glow) | direct |
| `/Game/FX/M_FX_Dust` | `adopted/fx` | `unreal/Scripts/import_combat_fx.py`:52-70 (sprite_material) | T_FX_Dust (texture/fx/dust) | direct |
| `/Game/FX/M_FX_Trail` | `adopted/fx` | `unreal/Scripts/import_combat_fx.py`:87-96 (module body) | T_FX_Trail (texture/fx/trail) | direct |
| `/Game/MegaPark/Materials/M_RetailOpaque` | `adopted/megapark/base-materials` | `unreal/Scripts/import_megapark.py`:68-163 (material, alpha 0) | T_DefaultWhite, T_DefaultLinear, T_DefaultBlack, T_DefaultNormal (adopted/megapark/shared-textures-common) | direct |
| `/Game/MegaPark/Materials/M_RetailMasked` | `adopted/megapark/base-materials` | `unreal/Scripts/import_megapark.py`:68-163 (material, alpha 1) | as above | direct |
| `/Game/MegaPark/Materials/M_RetailTranslucent` | `adopted/megapark/base-materials` | `unreal/Scripts/import_megapark.py`:68-163 (material, alpha 2) | as above | direct |
| `/Game/Japan/Hidamari/Materials/M_HDCity` | `adopted/japan/hidamari/generator` | `unreal/Scripts/city_material.py`:42-95 (parent) | T_HD_plaster (adopted/japan/hidamari/surface-plaster); helper atmosphere.py | needs helper |
| `/Game/Japan/Materials/M_Arcade` | `adopted/japan/materials/base-materials` | `unreal/Scripts/arcade_material.py`:24-63 (material, paving=False) | T_Arcade_timber (texture/japan/arcade-timber); roughness .87, specular .12 | direct |
| `/Game/Japan/Materials/M_ArcadePaving` | `adopted/japan/materials/base-materials` | `unreal/Scripts/arcade_material.py`:24-63 (material, paving=True; colour override 44-45) | T_Arcade_paving (texture/japan/arcade-paving); roughness .87, specular .12 | direct |
| `/Game/Japan/Materials/M_Harbor` | `adopted/japan/materials/base-materials` | `unreal/Scripts/harbor_material.py`:39-176 (material, water=False; branch 143-173) | T_Harbor_paving (texture/japan/harbor-paving), T_Harbor_timber (texture/japan/harbor-timber); roughness .83/.19, specular .35, fill .025 | direct |
| `/Game/Japan/Materials/M_HarborWater` | `adopted/japan/materials/base-materials` | `unreal/Scripts/harbor_material.py`:39-176 (material, water=True; branch 62-142) | sea_look (WAVES, LOOK, HAZE, constants), coast_water.HARBOR_RECT, EDGE 200 m, FAR_FADE (300, 900) m, opacity 1, metallic 0 | needs helper |

Counts: **24 direct, 3 needs helper, 0 not recoverable.**

### 2a. The four plaza masters

Pins: `arcade_material.py` sha256 `21ca3cbc06b18defbc95f7d5ae9a4c580027126bdcd90214d09d0eed016d10ab` (63 lines);
`harbor_material.py` sha256 `7681f25484a4d5589b0fbc366203391039a6747ccc07ca8ec90dcc801acc59ad` (176 lines);
`world/coast_water.py` sha256 `a7f9b6f40ae171526aa86999b17f4f3a48ebe35cce6dff4c305baa644c5d9381` (6 lines, `HARBOR_RECT` at line 6).
The call sites are `import_hidamari.py:26-32` and, for `M_HarborWater`, `refresh_water_materials.py:22`.

- The arcade and paving masters are one function, `material(paving)`. The `texture()` import at lines 7-21 becomes the
  texture records; the graph is lines 24-63. Paving changes only the colour code (line 45).
- The harbor is one function, `material(water)`. The non-water branch is lines 143-173 and the water branch is lines 62-142;
  lines 39-43 and 174-176 are shared. The module-level imports `sea_look` and `coast_water` (lines 9-10, 16) belong to the
  water branch. The builder for `M_Harbor` must not import them.
- The texture owners already exist and are source-backed: `texture/japan/arcade-paving` and `texture/japan/harbor-paving` pin
  `paving.png` (sha256 `0cf002e5…`, the same bytes in both records), and `texture/japan/arcade-timber` and
  `texture/japan/harbor-timber` pin `timber.png` (sha256 `d71b181a…`). The donor files are
  `world/regions/hidamari/textures/paving.png` and `timber.png` at the baseline.

Counts after this pass: **24 direct, 3 needs helper, 0 not recoverable.**

Notes on the fits:

- The Hippodrome and Mega Park builders call donor helpers only to import their textures (`import_megapark.py:43-65`,
  reached through `runpy` at `import_hippodrome.py:30`) or as module-level code (the donor scripts run their whole import on
  load). V2 imports the textures through texture records, so the recipe needs the builder function, not the importer.
- Three masters are module bodies with no function: `board_dissolve_material.py`, `racing_tv_material.py` and
  `M_FX_Trail` in `import_combat_fx.py`. Their builder is the body wrapped in one function; this is a mechanical move,
  and the read-back proves it. The hippodrome, skatepark, swordcamp and Mega Park graphs already sit in functions.
- The pier loop (`import_skatepark.py:136-173`) becomes a per-key builder. The metallic value is an argument (steel 1,
  the rest 0, `painted` 0 by `import_skatepark.py:134`). Its maps come from `tools/pier_texture_finish.py`, the writer of
  `textures.json`, and the V2 texture records hold the bytes.
- The haze helper (`atmosphere.py`, 62 lines) imports `sea_look.py`. A port needs only what it reads: `num` and `f3`
  (`sea_look.py:38-46`), `HAZE_CM = 900000.0` (line 67), `FAR = 0.74` (line 68) and `FAR_COLOUR`, which derives from
  `HORIZON = (0.126, 0.311, 0.720)` (line 50). The rest of `sea_look.py` (sea materials) is not needed.
- `material_assets.py` is not called by any held master generator (checked); it builds instances. It stays out of
  this design.

## 3. The recipe: `material-master`, version 1

A master is one record of kind `material-master`. Its generator is committed beside the record as sha-pinned `.py`
sources; the recipe names the builder function and its arguments and never restates the graph.

```toml
schema = 1
id = "master/hippodrome/grass"
kind = "material-master"
authority = "generated"
owner = "shared/hippodrome/grass"
input_dependencies = ["texture/hippodrome/grass"]

[[sources]]
path = "src/hippodrome_masters.py"        # the builder module, extracted from the donor script (section 4)
sha256 = "<64 lower-case hex>"

[recipe]
importer = "material-master"
version = 1

[recipe.settings]
builder = "surface"                       # a lower-case function in the pinned source
reads = ["/Game/Hippodrome/Textures/T_Grass"]   # each read must be an output of an input dependency
arguments = { key = "HD_Grass", roughness = 0.95, two_sided = false }

[[outputs]]
package = "/Game/Hippodrome/Materials/M_HD_Grass"
```

What the validator enforces (`tools/content/records.py`, `material_master_settings`, `material_master_reads`,
`material_input_problems`):

- `importer` is `material-master` and `version` is 1; `[recipe.settings]` has only `builder`, `reads`, `arguments`.
- `authority` is `generated`. A material-master with `editor` or `split` authority is refused: no master is converted
  by omission.
- `[[sources]]` holds at least one `.py` file, each pinned by sha256. A texture or any other file is refused.
- `builder` is a lower-case identifier; `reads` is a list of distinct `/Game` packages; `arguments` holds plain scalars
  and strings (no lists or tables).
- Each output is a `/Game` package named `M_<name>`.
- Every package in `reads` is an output of one of the record's `input_dependencies`; a read that no input owns is
  reported, as for material instances.

The schema enum (`schemas/asset.schema.json`) and `KINDS` both list `material-master`, and
`test_published_schemas_match_the_validator` still holds.

## 4. The generator, committed and pinned

Two facts shape this:

1. The donor scripts run their work at import (`import_hippodrome.py`, `board_dissolve_material.py`,
   `racing_tv_material.py`, `import_combat_fx.py`), so a builder cannot be imported from them without running the
   editor import. The builder must live in its own module.
2. There is a precedent for committing donor generator source inside a V2 record: `adopted/megapark/base-materials/source/`
   holds a byte-identical copy of `import_megapark.py` (sha256 `ac0c1df0…`, the donor pin in the JSON).

So each master family gets one builder module, `src/<family>_masters.py`, extracted from the donor script with the
graph code unchanged and the import work left behind. The record pins the extracted module by its own sha256, and
records the donor sha256 and line range in its provenance, so both the donor origin and the V2 bytes are checkable.
The extraction is itself a change, which is why the read-back in section 5 is the proof, not the extraction alone.

Per family:

- Hippodrome: `src/hippodrome_masters.py` with `structure_material` and `surface` (donor lines 36-78).
- Skatepark: `src/skatepark_masters.py` with `pier_material(key, metallic)` (lines 136-173) and `board_dissolve` (the module body).
- Swordcamp: `src/swordcamp_masters.py` with `build_material` and `build_ronin_body_material`, and the haze helper
  `src/atmosphere.py` with its sea_look constants (section 2).
- Racing: `src/racing_tv_masters.py` with `racing_tv`.
- FX: `src/fx_masters.py` with `sprite_material` and `trail`.
- Mega Park: already committed as `adopted/megapark/base-materials/source/unreal/Scripts/import_megapark.py`; the
  `material` builder is in that file, so its three masters need no new source, only the recipe.
- Hidamari: `src/hidamari_masters.py` with `parent` (city_material.py lines 42-95) and the haze helper.
- Plaza: `src/plaza_masters.py` with `material(paving)` (arcade_material.py lines 24-63) and `material(water)`
  (harbor_material.py lines 39-176, with the module-level sea imports moved into the water branch only). The water
  branch also needs `sea_look` and `coast_water.HARBOR_RECT`; section 9 lists them.

The recipe's `reads` and `input_dependencies` are the texture records already in V2, so nothing new is imported to
make a master recoverable.

## 5. The importer and the read-back

`material-master` runs inside the V2 editor. Its phases:

1. Plan (no editor): read the record, check each `[[sources]]` sha256, check every `reads` package is an output of an
   input dependency. Any mismatch stops the plan.
2. Editor rebuild: import the pinned builder module from the record's `src/` folder (never from elsewhere), require that
   each read asset loads, and call `builder(**arguments)` with the loaded textures. The rebuild writes to a scratch
   package under `build/yorimichi_v2/` by default, never to the saved master.
3. Read-back: run `unreal/Scripts/report_masters.py` (read-only, `V2_EDITOR_READ_ONLY=1`) on the scratch package and on the
   saved master. Compare blend mode, shading model, two-sided, domain, parameters with their defaults, texture names and
   the expression count. A difference fails the importer, and the saved master is never written.
4. An explicit rebuild (`--write`) saves the scratch result over the master only after the read-back agrees, and records
   the new sha256 of the sources in `verified.json`.

Limits of the read-back, stated plainly: `report_masters.py` reports the expression count and the textures, not the
wiring. Two graphs with equal counts and textures can differ in connections. `report_masters.py` has not been run natively
(the brief says so), so its output format is not yet proven. Before any master is claimed as recovered, extend the report
with a wiring digest (each expression's class, its properties and its input links, sorted) and run it on all 23 masters.
That extension is a separate change, not part of this preparation.

## 6. Changes this design needs (not written here)

`unreal/Scripts/import_asset.py` is not changed in this preparation. The change it needs, for review:

- Add a `material-master` handler beside the material-instance one: resolve the record's pinned builder module
  (hash-checked), load it with `importlib` from the record's `src/` folder, and call the builder with the arguments and
  the loaded reads.
- Add the scratch-package rebuild and the read-back comparison above, failing closed on any difference.
- Register `material-master` in the importer table that `tools/import/run.py` uses (`IMPORTERS`, version 1), as
  `test_the_runner_knows_the_material_instance_importer` does for instances.

`tools/import/run.py` and `build_batches.py` are not touched by this preparation.

## 7. Owner decisions

1. **Keep or convert the two constant-only masters.** `M_RacingTv` and `M_BoardDissolve` have no texture input and few
   parameters. Converting them to editor-owned would let the owner edit them directly, and nothing would be lost from the
   saved package. But the generator is then no longer the pinned source. Recommendation: keep them `generated` until
   the importer and read-back exist, then decide per master. Nothing here converts them.
2. **Commit generator sources into the adopted records.** Section 4 adds `src/` folders to the adopted records
   `adopted/hippodrome/materials`, `adopted/skatepark/materials`, `adopted/swordcamp/materials`, `adopted/fx`,
   `adopted/racing`, `adopted/skatepark/board`, `adopted/japan/hidamari/generator`. That changes their ownership units and
   their `verified.json`. Recommendation: approve, since the megapark precedent already does it.
3. **Engine defaults as reads.** `WhiteSquareTexture` (`M_HD_Structure`) and `Black` (`M_RacingTv`) are engine assets, not
   owned by any record. Recommendation: allow engine defaults in `reads` the way `ENGINE_PARENTS` allows engine parents.
4. **Scope of this pass.** Resolved in this pass: the four plaza masters (`M_Arcade`, `M_ArcadePaving`, `M_Harbor`,
   `M_HarborWater`) are inventoried (section 2a) and their inputs are in section 9. Their recovery stays a recipe until the
   importer exists, as for the others.
5. **Painted pier metallic.** The `painted` master uses the steel maps with metallic 0. Recommendation: state it as an
   argument (`metallic = 0.0`), not as a second builder.

## 8. What was not done

- No donor file was copied into V2 `src/` (the copies are the recovery step, not the inventory).
- The code changes are the validator (`tools/content/records.py`), the published kind enum
  (`schemas/asset.schema.json`) and the tests. No asset record, `import_asset.py`, `tools/import/run.py`,
  `build_batches.py` or guard and capacity code is changed.
- Nothing was imported, claimed, pushed, or run in Unreal or Blender.
- The donor was read only.

## 9. Input recovery for the 27 masters

Machine-readable form: `input_recovery` in [master-sources.json](master-sources.json) (10 entries, same ids as below).

Rule. An input is listed when it has no source-backed owner: an engine asset; a texture whose owner is an editor-owned
(adopted) record; or helper code whose bytes are pinned in V2 but are not yet a dependency of the master. Parameter constants
written in a pinned generator are not listed, because the generator carries them. Textures with a generated owner that pins
its own donor file are source-backed and are not listed. Nothing here writes a record.

| id | Input | Kind | Used by | Owner today | Donor original (sha256) | Importer | Status | Recovery needed |
|---|---|---|---|---|---|---|---|---|
| engine-white-square | `/Engine/EngineResources/WhiteSquareTexture` | engine | M_HD_Structure | engine | none | none | engine-default | engine reads allowlist (decision 3) |
| engine-black | `/Engine/EngineResources/Black` | engine | M_RacingTv | engine | none | none | engine-default | engine reads allowlist (decision 3) |
| texture-megapark-default-white | `/Game/MegaPark/Textures/T_DefaultWhite` | texture | M_RetailOpaque, M_RetailMasked, M_RetailTranslucent | adopted/megapark/shared-textures-common | `world/regions/megapark/build.py` `write_fallbacks` (lines 31-38), sha `819ce615…`; output white.png `7ac2abfc…` (68 bytes) | texture@1, srgb | recoverable-by-port | port the 8-line writer into a pinned src |
| texture-megapark-default-linear | `/Game/MegaPark/Textures/T_DefaultLinear` | texture | the same three | adopted/megapark/shared-textures-common | same donor function; white.png `7ac2abfc…` | texture@1, srgb off | recoverable-by-port | as above |
| texture-megapark-default-black | `/Game/MegaPark/Textures/T_DefaultBlack` | texture | the same three | adopted/megapark/shared-textures-common | same donor function; black.png `abc58d51…` (70 bytes) | texture@1, srgb off | recoverable-by-port | as above |
| texture-megapark-default-normal | `/Game/MegaPark/Textures/T_DefaultNormal` | texture | the same three | adopted/megapark/shared-textures-common | same donor function; normal.png `2d307115…` (70 bytes) | texture@1, srgb off, TC_NORMALMAP | recoverable-by-port | as above |
| texture-hidamari-plaster | `/Game/Japan/Hidamari/Textures/T_HD_plaster` | texture | M_HDCity | adopted/japan/hidamari/surface-plaster (editor) | `games/yorimichi/assets/hidamari/textures/plaster.jpg`, sha `e0204be3…`; the adopted record pins the same bytes | texture@1, srgb | recoverable-now | owner decision; the original is in hand |
| helper-sea-look | sea_look: WAVES, LOOK, HAZE and constants | helper | M_HarborWater, M_SwordCamp, M_HDCity | base-materials, line 84 | `unreal/Scripts/sea_look.py`, sha `ffae53cd…` | material-master@1 (pinned src) | wire-dependency | pin in the master src, or depend on base-materials |
| helper-atmosphere | atmosphere.py (haze) | helper | M_SwordCamp, M_HDCity | base-materials, line 16 | `unreal/Scripts/atmosphere.py`, sha `b59478df…` | material-master@1 | wire-dependency | pin with sea_look |
| helper-coast-water-harbor-rect | coast_water.HARBOR_RECT | helper | M_HarborWater | adopted/brinecove/materials, line 92 | `world/coast_water.py`, sha `a7f9b6f4…` | material-master@1 | wire-dependency | pin the 6-line file |

Counts: **10 inputs in total**, by kind: **engine 2, texture 5, helper 3**. By status: engine-default 2, recoverable-by-port 4,
recoverable-now 1, wire-dependency 3, not-recoverable 0.

Evidence for each recovery:

- The megapark defaults are 1x1 PNGs written by `write_fallbacks` (`world/regions/megapark/build.py:31-38`), which
  `import_megapark.py:183-186` imports. No file is committed, so they are not pinned by file. Running the donor function
  from the baseline blob, under `python -I`, reproduces the bytes: white 68 bytes `7ac2abfc…`, black 70 bytes `abc58d51…`,
  normal 70 bytes `2d307115…`. The owner record lists the four T_Default packages as outputs, but none of its `[[sources]]`
  is one of these PNGs.
- The plaster original is pinned (`plaster.jpg`, sha `e0204be3…`, the same bytes as the donor file). `tools/hidamari_textures.py`
  generates through an image API, so the pinned file is the only original, not a rerun. texture@1 fits it.
- The helper rows are bytes already pinned in V2 (`sea_look.py` and `atmosphere.py` in base-materials; `coast_water.py` in
  brinecove). The gap is wiring: no master names them yet. The donor file for each sha is the baseline blob.
- Engine defaults have no donor file and no importer. They need the reads allowlist from decision 3.

What is not recoverable: nothing in this pass. Each of the 10 has either a pinned original, a reproducible generator, or
pinned helper bytes.

What the importer pilot must decide (not decided here): the owner of T_HD_plaster, given that the adopted record already
outputs it; whether helper bytes are copied into each master's src or read through a dependency on base-materials or
brinecove; and whether the megapark defaults are re-homed to a generated texture record or stay in shared-textures-common.
