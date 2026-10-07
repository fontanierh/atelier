# Modori

The rival: a lean, dark-haired young man of about eighteen, calm and nonchalant, a long fringe over one eye. He walked
into the forest sinkhole with a search party and came out alone six weeks later, well fed, calm and wrong; the coast
calls the ones who came back from the openings *modori* (戻り, "returned"), and he never gave another name. See the
[concept and its T-pose references](../concepts/README.md#the-chosen-take-modori-in-t-pose) and the
[lore](../../../docs/LORE.md).

He is modelled, textured and dressed, **not in the game yet**: there is no export or Unreal import for him so far.

## The source: `Modori-Rig-r01.blend`

Everything is packed into the blend (textures included); [`source-manifest.json`](source-manifest.json) has its
SHA-256 and the counts below.

| Object | What it is |
| --- | --- |
| `Modori-Rig` | Tripo Studio's rig: a Mixamo skeleton, 65 bones with full fingers (`mixamorig:Hips` ... `mixamorig:RightHandThumb4`) |
| `Modori-Body` | Tripo Studio's body (Smart Mesh and Smart UV), 5,172 vertices, skinned to the rig. One material, matte (specular 0, roughness 1), its normal map disconnected; base colour `basecolor-redo.png`, 4096 px |
| `Modori-Coat` | Tripo's long coat, a separate mesh of 5,404 vertices fitted onto the body and skinned to the same rig, with a `cloth_pin` vertex group; base colour 4096 px |

- **Scale and axes:** 1 m tall as Tripo exports him, Z up, facing -Y. He is meant to be 1.75 m (`height_cm`), about
  5 heads tall to Cairo's 4: scale on export, as Kaede's `export_unreal.py` does.
- **Texture:** the *redo* variant of [`modori_texture.py`](../tools/modori_texture.py), chosen by the user on
  7 October 2026: each head triangle is labelled skin, hair or collar, and the skin and hair are painted fresh with soft
  shading from the geometry; the eyes, brows and mouth are drawn from its `FACE` table. Below the neck it is Tripo's
  own paint (clothes, hands, boots).
- **Coat:** fitted by [`modori_coat.py`](../tools/modori_coat.py): cuffs on the wrist bones, pushed 4 mm clear of
  the body, the body's bone weights with the skirt blending to the hips. `cloth_pin` is 1 on the torso and sleeves,
  falling to 0 just below the hips (0.44 to 0.52 m at 1 m scale). The blend keeps a Blender cloth modifier and a
  130-frame test take (`Modori-RigAction`: rest, arms down, a few steps, a quick turn) as a look check only.

## Putting him in the game

The steps Kaede took ([`sword-trainer/`](../sword-trainer), [Tripo characters](../../../docs/TRIPO_CHARACTERS.md)),
are the model:

1. **Export** (`export_unreal.py` here, a build step in `games/yorimichi/build.py`): scale to 1.75 m with the soles on
   the floor, rename the Mixamo bones to the humanoid contract (`atelier.character.names.mixamo_aliases`,
   [`platform/conventions/rigs/humanoid.toml`](../../../../../platform/conventions/rigs/humanoid.toml)), drop the
   Blender cloth modifier and the test action, and write the skinned mesh (body and coat) and textures to FBX.
2. **Coat in Unreal:** Chaos Cloth on the coat's skirt, its max-distance mask painted from `cloth_pin` (0 pinned,
   free where the pin is 0), the body as the collider; or skirt bones if cloth costs too much.
3. **Moves:** retarget the merged move set onto him as for Kaede (`cairo/botw.py --character modori`, which loads
   this folder's `export_unreal.py` for its `prepare`, `SOURCE` and `OUT`). His own weapon
   (a knotted rope with a bell-metal weight, left off the T-pose) and its clips come later.
4. **Import** (`unreal/Scripts/import_<...>.py`), then play him: as the player in Cairo's place first, to check the
   skinning, the face and the coat in motion.

## Known limits

- In the hidden crevice behind the ears the texels are large (about 1 mm, from Tripo's UV), so the skin/hair edge there
  is soft at 60 mm close-ups. Two material slots (hair and skin) would make it exact.
- The matte material reads the hair a little darker than Tripo's sheen did.

## Rebuilding the source

The Tripo Studio downloads are not in Git; they stay in `build/yorimichi/characters/modori/` on the machine that made
them (`tripo-body-r01/` with its `rigged/modori-rigged.fbx`, `tripo-coat-r01/`). From there, under the guard
(`uv run python -m atelier.safety.guarded --small 3 ...`):

```sh
T=games/yorimichi/assets/characters/tools; M=build/yorimichi/characters/modori; B=$M/tripo-body-r01
blender -b --python-exit-code 1 --python $T/modori_texture.py -- --input "$B/anime+character+3d+model.fbx" --output $B/texture-r01 --stage raster
uv run python $T/modori_texture.py --input "$B/anime+character+3d+model.fbx" --output $B/texture-r01 --stage paint --variant redo
blender -b --python-exit-code 1 --python $T/modori_coat.py -- --body $B/rigged/modori-rigged.fbx \
    --texture $B/texture-r01/basecolor-redo.png --coat "$M/tripo-coat-r01/long+coat+3d+model.fbx" --output $M/fit-r02 --stage fit
blender -b --python-exit-code 1 --python $T/modori_coat.py -- ... --stage sim   # writes Modori-Coat.blend
```

`Modori-Coat.blend` is copied here as the next `Modori-Rig-rNN.blend`, with its manifest updated.
