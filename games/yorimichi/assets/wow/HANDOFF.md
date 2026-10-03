# Handoff: standalone vanilla WoW extraction for a native game

You are taking over **implementation and extraction**, not another general research pass. Work on this machine until you have a coherent, inspectable offline content pack and a clear account of unresolved inputs or conversion defects.

## User intent and non-negotiable scope

We want to incorporate WoW places, characters, animations, items and selected mechanics **natively into our own game**, Yorimichi, later. Our own multiplayer server will eventually own gameplay. At this stage:

- **No Unreal Engine, Yorimichi checkout, game launch, WoW login or running game server is required.** This machine has Blender. Install the small additional extraction/build tools you need.
- The task is **pure extraction/conversion/data preparation**. Do not build a replacement WoW client, a VMangos server, a Bevy renderer or an Unreal importer.
- The first player profile is a **level 60 mage**, but the formats and selection must support other classes, levels, races and appearances later. Avoid a mage-specific skeleton or hardcoded one-spell extractor.
- World scope is **Booty Bay**, selected **Stranglethorn farming pockets**, relevant friendly NPCs and mobs, and eventually a bounded dungeon wing. Booty Bay/Bloodsail is the first coherent pack. A small adapted **Zul’Gurub wing** is the thematic dungeon candidate; Deadmines is the pirate alternative. Original raid/group/level/lockout rules do not constrain our eventual native gameplay.
- The user does not currently have a vanilla client. **This machine is where a matching client will be downloaded/provided.** Establish that input early. Read archives; you do not need to run the original executable.
- Preserve provenance and distinguish extracted facts, approximations, authored adaptations and missing server content. Do not present client metadata as a complete combat simulation.

## What accompanies this prompt

The archive has this `HANDOFF.md` and a `tools/` directory containing Python scripts, a configurable TOML profile, a small Rust extractor and its Cargo lockfile. It contains **no retail assets, client binaries, private Discord captures, credentials or compiled platform-specific tools**.

Tools were started in another checkout. They are a useful implementation baseline, **not a verified retail extraction solution**. The following were exercised locally: decoder compilation before the final creature-skin dependency addition; synthetic M2 mesh/skeleton/clip conversion; animated GLB writing; units/bind-pose checks; malformed-data rejection and manifest checks. The local Python suite passed **13 tests**. The final Rust change could not be rebuilt immediately because another Atelier render job held the compile lock. **Rebuild the bundled source here first.** Standalone execution does not use Atelier or its render lock.

No real WoW archive, model, animation, Booty Bay tile or mage spell catalogue has been extracted/visually verified yet. The original-machine doctor reports missing client data. Do not inherit an assumption that real assets were tested.

The scripts use only the Python standard library. Python **3.11+** is needed for TOML. Use a recent Rust/Cargo toolchain; **Rust 1.94.1** was the original compiler. Cargo fetches selected benilla reader/schema dependencies pinned below, not its game app. Blender is for import, assembly, animation inspection and optional further export. On Windows use the corresponding Python executable and Cargo `.exe` output.

## Start here

Unpack into a dedicated working directory. Keep input client data and generated output in separate directories. From `tools/`:

```sh
python3 pipeline.py plan --output ../private-output
python3 pipeline.py build --output ../private-output
python3 selftest.py --binary ../private-output/tools/debug/yorimichi-wow-extract
python3 pipeline.py doctor --data /path/to/client/Data --output ../private-output
python3 pipeline.py extract --data /path/to/client/Data --output ../private-output
python3 pipeline.py verify --output ../private-output
```

For Windows the self-test binary has `.exe`. `WOW_DATA` can replace `--data`. A client root containing `Data/` is also accepted. Use `--profile /path/to/profile.toml` for a changed scope. `python3 pipeline.py test` runs the Rust tests. `extract` requires a fresh pack output; use a different output directory for a new revision rather than mixing assets. Job logs are in `private-output/jobs/<job>/stdout.log`.

The standalone default output is beside the tools directory. Inside the original Atelier repository, output is restricted to ignored `build/` and jobs use Atelier’s guards; that branch of the script is irrelevant on this machine.

If the baseline build/test fails, fix it before running a large extraction. Keep fixes in the portable sources, pin dependencies and record the resulting versions. Do not silently drop an unsupported dependency and still mark the pack complete.

## Source acquisition and exact revisions

The required art/table source for this decoder is **English WoW 1.12.1, build 5875**. Establish the version and patch chain rather than trusting a download filename. Modern Classic Era, Wrath, Cataclysm and customized client builds are not interchangeable with the inspected vanilla schemas.

Use a client source the user can obtain/use. If no suitable source is available, request the missing source/location succinctly, continue independent code/data work, and clearly mark real asset extraction blocked. Do not invent assets or relabel a different client build as 5875. Preserve the original install; extraction writes elsewhere. Client executable execution, private-server accounts and patcher installation are unnecessary for archive reading.

Record archive names, sizes and SHA-256 hashes; version/language evidence; patch order; converter revision and effective profile. The baseline preserves input hashes, but its manifest deliberately sets `source_build_verified=false`. Add an explicit verification record after you establish the actual build. Hashes are provenance, not proof of a build by themselves.

Primary source references:

- **benilla**: https://github.com/samwhosung/benilla/tree/b396bbf69a0486b6d29829ec191145f63c363eea — MIT OR Apache-2.0. Reader/schema/animation reference. Its README says the user supplies their own install. It does not bundle retail art.
- **wow.export**: https://github.com/Kruithne/wow.export/tree/c2fd7bde36a712be78a5da896c995b84fbfa2545 — inspected legacy export code has MIT notices. Optional accelerator/independent check for static terrain/WMO/M2 export. Do not assume modern glTF marketing means animated legacy glTF support: the inspected legacy model dispatcher offered OBJ/STL/raw.
- **World of Skatecraft**: https://github.com/Kimmo3223/world-of-skatecraft/tree/da6e99bc15abdebdf199c7315c821b41a00ee691 — selected files show semantic rig mapping, local-origin collision workers and rail detection. Optional later reference; its `export.rs` converts a Skate GLB, not WoW M2. Rail/export files retain Apache-2.0 provenance.
- **VMangos**: https://github.com/vmangos/core/tree/0e3ff01e76d4758e8a7c3108b2717cc785ed56fa — optional behavioral/content reference only. No runtime dependency. Server code is GPL-2.0; do not silently transplant it into our game implementation. A separately sourced world database can be parsed offline if useful; record its revision/licence and keep source data separate.

Keep retail-derived data private. Public tool code and extracted proprietary assets must not be mixed into one repository/package. Preserve applicable code notices. No paid AI generation is needed.

## Current implementation and its limits

`profile.toml` initially selects class ID 8, spell family 3, level 60, human male/female body models, jungle creature directory patterns, item components/texture directories, and Booty Bay. Race/sex are profile fields; the starter does **not** yet build a fully dressed, composited player appearance from them.

The Rust extractor:

- Opens the vanilla MPQ patch chain using benilla, so later patches override earlier files.
- Uses archive listfiles plus explicit seeds and parsed dependencies. **Listfiles are incomplete**, especially for base textures. “Not listed” is not proof a file cannot be read by name.
- Recursively extracts ADT/WMO/M2/BLP dependencies; records hashes, winning archive, dependencies, failures and unsupported-table warnings.
- Exports M2 geometry, weights, hierarchy/pivots, skin sections, materials, attachments, animation fallback tables, per-sequence tracks/events and independent global-sequence bone channels to neutral JSON.
- Exports terrain chunks/holes/layers/placements and WMO roots/groups/doodads/materials/portal data to neutral JSON; decodes BLP textures to PNG; retains raw files.
- Exports registered DBC schemas to CSV and retains unregistered tables losslessly as raw DBC. The typed CSV dumper does **not** cover every table.
- Joins spell family and triggered spell closure with range/cast-time/duration and visual metadata. The creature dependency pass adds display-skin texture references that M2 files do not hardcode.

Python postprocessing joins selected creature appearances, retains item-display records, selects class talent metadata and level-eligible spell candidates, inventories required effect/aura types, writes portable M2 GLBs and world-geometry OBJs, and verifies output hashes/dependency closure.

Known limitations to address:

1. No real archive test yet; field/layout assumptions and dependency closure must be checked with actual input. Baseline parsers target 5875; skill-line abilities expect 15 fields, talent tabs 15, talents 21 and Spell.dbc 173.
2. The GLB writer supports ordinary bone inheritance and step/linear clip channels. It explicitly rejects billboard/special-parent rigs and independent global-sequence bones. Those models still have neutral channels and raw assets. Extend/bake deliberately; do not erase the channels just to obtain a GLB.
3. GLBs use **preview materials** and export authored geoset sections. They do not yet select clothing/hair/geosets, compose skin/equipment atlases, reproduce alpha/material passes, particles/ribbons or animated UVs. A grey overlapping-geoset humanoid is not the final mage.
4. OBJ outputs are geometry views. Materials, placements and appearance/collision semantics are in neutral JSON/raw files; no complete assembled/textured Booty Bay `.blend` has been made.
5. Terrain liquid geometry remains in raw ADT with counts in neutral output; extend it for an assembled scene. Verify WMO group doodad membership/interior/exterior lighting and any raw-only fields before faithful assembly.
6. Client spell records are **not learned spells**. Baseline highest-level-per-name candidates are not validated rank chains. Talent/quest/racial/item restrictions and acquisition remain unresolved.
7. Named NPC templates/spawns/AI/loot, complete item stats/prices/drop tables and quest rules are not supplied by display DBCs. The baseline labels these missing instead of inventing them.
8. No native effect execution, combat simulation or future server protocol exists here. This task should produce clean mechanics specifications/data and references, without turning extraction into a server project.

Treat these as a punch list, not a reason to discard useful readers and start from zero.

## Required work, in order

### 1. Validate the source and extract a small proof

Identify the full input/patch chain. Run the synthetic smoke test. Then decode one humanoid model, one jungle creature, one item model and the Booty Bay WMO. Check that real skeleton/track counts, textures and dependencies are plausible. Fail visibly on truncated data, schema mismatch or unresolved references. Only widen selection after this works.

### 2. Character and animation pack

Begin with a mage-capable human body; keep the converter generic. Include additional mage races/sexes if practical after the first model is verified, but do not block the first correct pack on all appearances.

Preserve every authored animation sequence and variation for selected rigs, not just six locomotion clips. Give each clip its source model, animation semantic ID/name from `AnimationData.dbc`, source sequence, duration, loop mode, authored move speed, blend time, variation/replay metadata and events. Keep source IDs; do not replace them with guessed names.

Prioritize inspection of idle, walk/run/backward, jump/fall/land, swim, attack/hit/death, spell-ready/casting/launch/channel and relevant emotes. Bone hierarchy, model-space pivots, weights, interpolation, attachments, globals and material/effect channels matter. Preserve untranslated raw tracks as well as portable exports.

Produce usable GLB/Blender actions. Validate several sampled timestamps against benilla’s decoded pose semantics; bind pose and hierarchy alone are insufficient. Extend the exporter for special parent/billboard/global behavior where selected rigs need it, with documented baking or retained-runtime-channel policy. Do not bake camera-facing effects against an arbitrary camera and call the result faithful.

Compose at least one selected mage appearance in Blender: correct skin/hair/face/geosets and a simple robe/staff/wand loadout once item source records are available. Keep equipment separate/attached using real attachment metadata. Do not retarget onto Cairo or another Yorimichi rig; that game data is not on this machine. Export the original skeleton and semantic key-bone map.

### 3. Mage abilities and mechanics data

Extract the full class-relevant spell/rank/talent metadata and retain triggered/support spells. Resolve real acquisition/rank links wherever an appropriate source exists. Separate trained, talent, racial, quest, item-triggered and NPC-only entries. Retain downrank choices. Do not grant every family spell just because `spell_level <= 60`.

Build a machine-readable mage profile with known/eligible spell sets, unresolved acquisition flags, talents, resources/stat dependencies and equipment requirements. A concrete initial talent/loadout choice can be proposed, but must be explicitly identified as our chosen profile. Level 60 alone does not determine racial stats, gear, talents, max mana or spell power.

For each selected ability include IDs/rank/source, name/description/icon, school, cast/channel timing, resource cost/scaling, individual/category/global cooldown, min/max range, radius/targets, projectile speed, interrupts, effect slots/coefficients/base points/dice, aura duration/ticks/stacks, proc/trigger references, reagents, restrictions and visual/animation/sound links. Preserve source values and units; interpret base-point encoding explicitly rather than assuming stored base points are the final damage number.

Use recognizable mage abilities as a coverage checklist, then verify names/IDs/ranks from input: Fireball, Frostbolt, Arcane Missiles/Explosion, Fire Blast, Scorch, Flamestrike, Blizzard, Cone of Cold, Frost Nova, Polymorph, Blink, Counterspell, Evocation, armour/intellect/shield buffs, conjured food/water/mana items, dispel/curse removal, Slow Fall, teleports/portals, and talent-dependent abilities such as Pyroblast/Ice Block/Ice Barrier where the selected build provides them. This checklist is not a hardcoded grant list.

Write a mechanics dossier that distinguishes:

- Extracted client policies we can adapt: targeting, reach/range, casting lifecycle, cooldown feedback, animation selection and presentation.
- Extracted metadata: costs, effect/aura identifiers, flags, parameters and references.
- Mechanics needing our implementation: effect execution, damage/healing/resistance/crit, crowd control, threat/aggro, AI, proc rules, inventory/rewards and persistence.

Benilla source paths worth inspecting: `crates/benilla-formats/src/spells/`, `crates/benilla-app/src/spell/validator.rs`, `spell/cooldowns.rs`, `ui_cast.rs`, `creature_anim/select.rs`, `crates/benilla-world/src/rig_anim/` and `crates/benilla-formats/src/models/`. Some client validators permit missing data because an original server decides outcomes; document that and do not inherit permissive behavior in a future authority.

### 4. NPCs, mobs and items

Deliver selected jungle creature models/animations and appearance variants, goblin-friendly NPC appearances and pirate/humanoid presentation assets relevant to Booty Bay/Bloodsail. Join `CreatureDisplayInfo`, `CreatureDisplayInfoExtra`, `CreatureModelData`, character appearance and equipment data where possible. Record display IDs separately from creature entry/template IDs.

Extract item models, replaceable textures, body texture components, icons, geosets, attachments and visual references. Start with mage cloth/robe/head/shoulder components, staves/wands and selected farming loot/consumables. **ItemDisplayInfo is appearance data, not a complete item catalogue.** Keep item entry IDs separate from display IDs.

For named NPC stats, spawns, patrols, loot, vendors, quests and item gameplay values, use a separately identified compatible reference dataset if available. You may parse an openly available database dump offline; do not install/run VMangos or copy its server engine into the extractor. Pin the dataset, preserve patch/build selection and record schema transformations. If unavailable, emit explicit gaps and appearance-only records. Do not fabricate original spawn inventories or prices.

### 5. Booty Bay and selected surrounding terrain

Known root path:

`World\\wmo\\Azeroth\\Buildings\\Stranglethorn_BootyBay\\BootyBay.wmo`

Booty Bay is area 35 under Stranglethorn zone 33, on Azeroth/map 0 in inspected client fixtures. These are source metadata, not future engine/network identities.

The starter selects a 3×3 ADT window around raw world `(-14314.3, 466.2)`. This comes from a traversal fixture, **not a surveyed complete boundary or recommended spawn**. Determine the actual town/coast footprint from WDT/ADT placements and WMO bounds. Follow dependencies beyond tile edges; deduplicate placements by source unique ID. Add sufficient visual margin. Do not cut buildings by pivot position or confuse tile-local, world and WMO-local coordinates.

Assemble an inspectable Blender scene with terrain, WMO groups, doodads, repeated M2 props, materials/textures and water. Preserve original placement values and an explicit local origin. Group exports into hub, coast/Bloodsail and later jungle pockets rather than exporting the entire continent blindly. Keep draw/material/geoset/interior metadata beside meshes for later native import.

Two precise source fixtures:

- Booty Bay entrance arch, WMO MODD doodad index 3, is referenced by interior group 22 and exterior group 42 in the inspected test. Its stored colour is black; applying it indiscriminately creates a black silhouette. Preserve ownership/exterior-lighting context. See benilla `crates/benilla-assets/src/wmo.rs`.
- The mover fixture at `(-14314.3, 466.2, 18.5)` describes a roughly 22-degree ramp with a 0.40-yard riser. Use it as a traversal-geometry reference, not an asserted player spawn. See `crates/benilla-app/src/player/mover.rs`.

Check boardwalks, stairs, doors, the entrance, cliffs/coast/water and terrain holes. Preserve collision flags/geometry as data, but do not build Unreal collision or VMangos navigation. Scene inspection in Blender is enough at this stage.

### 6. Optional bounded dungeon extension

Only after the town/character/mage-data loop is coherent, extract one bounded Zul’Gurub wing and selected creatures/objects. Retain original art but do not require original raid progression. Inspect WDT first: dungeons can use ADT terrain or a globally placed WMO. Applying ordinary ADT coordinate remapping to a global WMO can put it far away. Do not infer every instance is one building or require every boss before a wing is inspectable.

## Coordinate and animation contract

The neutral format preserves **raw WoW right-handed coordinates in yards**, world X north, Y west, Z up; model X forward, Y left, Z up. One physical yard is **0.9144 metres**. Benilla's Bevy mapping `(-y,z,-x)` is not our interchange contract.

The starter portable GLB uses **metres, glTF right-handed Y-up**, via `(x,z,-y) × 0.9144`. It rotates rather than mirrors. Scale vectors permute axes without distance scaling; quaternion basis conversion must match; bind transforms and inverse binds must remain consistent. Blender’s glTF importer handles the standard glTF-to-Blender boundary. Do not add a second yard conversion or arbitrary extra Y flip. Future Unreal conversion is out of scope.

Validate an asymmetric mesh, all basis vectors, a tilted placement, winding/normals, parent-child transforms, source bone pivots, bind skinning, an attachment and animation samples. Unit labels must appear in each serialized format or its versioned manifest.

## Deliverables and acceptance

Deliver private output and portable source separately:

1. `source-manifest.json`: client/build/language evidence, archive hashes/patch order, code/dataset revisions, profile and conversion conventions.
2. `pack/manifest.json` and verification: asset/dependency census, hash integrity, missing/unsupported records and completion scope.
3. Character/creature neutral data plus portable GLBs and a Blender animation inspection scene/contact sheet.
4. At least one textured mage appearance with real skeleton/actions and item attachments, or a precise blocked/unsupported report rather than a fake substitute.
5. Mage spell/rank/talent/mechanics catalogue with source values, acquisition distinctions and implementation gaps.
6. NPC/creature appearances and item appearances; separate gameplay records where a compatible source exists.
7. A bounded, assembled/textured Booty Bay Blender scene and exportable terrain/building/prop packs, plus screenshots of entrance/waterfront/interior paths.
8. Reproducible commands/scripts and a concise `EXTRACTION_REPORT.md`: what actually ran, counts/sizes/times, visual checks, deficiencies, fixes and exact next actions.

Acceptance requires real-input inspection and numerical checks, not only that a binary compiled or a JSON file exists. Report animations/models/appearances/spells/items/tile/group counts by category; do not inflate counts with duplicate placements or claim a playable mage/completed combat system. Keep unsupported visual/runtime features visible.

No proprietary assets should enter public git. If returning content to the original game team, package private outputs through an appropriate private transfer, with manifests. Return portable source fixes separately, without personal paths or credentials. The receiving game team will implement native systems and import into Unreal later.
