# Modori

The rival: a lean, dark-haired young man of about eighteen, calm and nonchalant, a long fringe over one eye. He walked
into the forest sinkhole with a search party and came out alone six weeks later, well fed, calm and wrong; the coast
calls the ones who came back from the openings *modori* (戻り, "returned"), and he never gave another name. See the
[concept and its T-pose references](../concepts/README.md#the-chosen-take-modori-in-t-pose) and the
[lore](../../../docs/LORE.md).

He is playable in the game, with his own body, long coat and finger rig. The build exports his committed source,
imports the mesh and Chaos Cloth skirt into Unreal, and retargets the merged move set onto him. He carries the
merged set's sword and paraglider; the native skating runtime retargets its rider pose onto his body too.

## The source: `Modori-Rig-r01.blend`

Everything is packed into the blend (textures included); [`source-manifest.json`](source-manifest.json) has its
SHA-256 and the counts below.

| Object | What it is |
| --- | --- |
| `Modori-Rig` | Tripo Studio's rig: a Mixamo skeleton, 65 bones with full fingers (`mixamorig:Hips` ... `mixamorig:RightHandThumb4`) |
| `Modori-Body` | Tripo Studio's body (Smart Mesh and Smart UV), 5,172 vertices, skinned to the rig. One material, matte (specular 0, roughness 1), its normal map disconnected; base colour `basecolor-redo.png`, 4096 px |
| `Modori-Coat` | Tripo's long coat, a separate mesh of 5,404 vertices fitted onto the body and skinned to the same rig, with a `cloth_pin` vertex group; base colour 4096 px |

- **Scale and axes:** 1 m tall in the source, Z up, facing -Y. `export_unreal.py` scales him to 1.75 m (`height_cm`),
  places the soles at the floor and turns him to face +X. He is about 5 heads tall to Cairo's 4.
- **Texture:** the *redo* variant of [`modori_texture.py`](../tools/modori_texture.py), chosen by the user on
  7 October 2026: each head triangle is labelled skin, hair or collar, and the skin and hair are painted fresh with soft
  shading from the geometry; the eyes, brows and mouth are drawn from its `FACE` table. Below the neck it is Tripo's
  own paint (clothes, hands, boots).
- **Coat:** fitted by [`modori_coat.py`](../tools/modori_coat.py): cuffs on the wrist bones, pushed 4 mm clear of
  the body, the body's bone weights with the skirt blending to the hips. `cloth_pin` is 1 on the torso and sleeves,
  falling to 0 just below the hips (0.44 to 0.52 m at 1 m scale). The blend keeps a Blender cloth modifier and a
  130-frame test take (`Modori-RigAction`: rest, arms down, a few steps, a quick turn) as a look check only; the
  baked frames are not kept, so the cloth simulates again when the take plays.

## Build and play

From the repository root:

```sh
nice -n 10 uv run atelier build yorimichi
nice -n 10 uv run atelier play yorimichi -- -rider=Modori
```

The normal build includes him. `unreal.modori_adventure` selects his mesh and merged-motion imports with their
dependencies when only those assets need rebuilding after an existing full build.

- `characters.modori` runs [`export_unreal.py`](export_unreal.py), checks the source hash, renames the bones to the
  humanoid contract and writes his body, coat, textures and cloth mask into `build/yorimichi/modori/`.
- `unreal.modori` runs `unreal/Scripts/import_modori.py`, creating `SK_Modori`, materials, coat cloth and colliders,
  and `DA_ModoriBase`. The base supplies the mesh and measurements to the merged importer.
- `characters.modori_adventure` runs `adventure/retarget.py --character modori`, using Cairo's donor clips and the
  committed motion reference. `unreal.modori_adventure` imports those clips into `/Game/Modori/Adventure` and writes
  `DA_Modori` and his move record. [`adventure.toml`](adventure.toml) records his equipment fit.
- `characters.modori_grips` exports his posed hand grips for the sword and paraglider.

`AModoriCharacter` is registered as a playable character and always uses his merged move set. His coat skirt is
simulated by Chaos Cloth, with the upper coat pinned and the free skirt colliding with capsules on his body.
The cloth resets after teleports and board mounts. His story weapon, the rope and bell-metal weight, is still a
concept; the playable character uses the merged set's sword.

## Known limits

- In the hidden crevice behind the ears the texels are large (about 1 mm, from Tripo's UV), so the skin/hair edge there
  is soft at 60 mm close-ups. Two material slots (hair and skin) would make it exact.
- The matte material reads the hair a little darker than Tripo's sheen did.

## Authoring a new source revision

Game rebuilds use the committed blend and its packed textures. The original Tripo Studio downloads below are
inputs to the authoring tools, rather than the game build. They stay in the author's ignored
`build/yorimichi/characters/modori/` (`tripo-body-r01/` with its `rigged/modori-rigged.fbx`, `tripo-coat-r01/`).
To author a replacement from those files, under the guard
(`uv run python -m atelier.safety.guarded --small 3 ...`):

```sh
T=games/yorimichi/assets/characters/tools; M=build/yorimichi/characters/modori; B=$M/tripo-body-r01
blender -b --python-exit-code 1 --python $T/modori_texture.py -- --input "$B/anime+character+3d+model.fbx" --output $B/texture-r01 --stage raster
uv run python $T/modori_texture.py --input "$B/anime+character+3d+model.fbx" --output $B/texture-r01 --stage paint --variant redo
blender -b --python-exit-code 1 --python $T/modori_coat.py -- --body $B/rigged/modori-rigged.fbx \
    --texture $B/texture-r01/basecolor-redo.png --coat "$M/tripo-coat-r01/long+coat+3d+model.fbx" --output $M/fit-r02 --stage fit
blender -b --python-exit-code 1 --python $T/modori_coat.py -- ... --stage sim   # writes Modori-Rig.blend
```

`Modori-Rig.blend` (no machine paths, unlike `Modori-Coat.blend` beside it) is copied here as the next
`Modori-Rig-rNN.blend`, with its manifest updated.
