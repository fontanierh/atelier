# Footsteps

The player's footsteps: 531 one-shots across seven surfaces, triggered from the character's own foot bones and picked
by the material under the foot. `UJapanFootstepComponent` (`unreal/Source/Yorimichi/JapanFootsteps.h/.cpp`) does the
detection and playback; the sounds and where they come from are in
[assets/audio/footsteps](../assets/audio/footsteps/README.md).

## Building

```bash
atelier fetch yorimichi                  # the Sonniss masters
atelier build yorimichi unreal.sounds    # slice and import footsteps, combat and skate audio
```

`unreal.sounds` runs `audio.footsteps` (slicing into `build/yorimichi/audio/footsteps/`) and
`unreal/Scripts/import_footsteps.py`, which builds:

| Asset | What it is |
| --- | --- |
| `/Game/Japan/Audio/Footsteps/<surface>/` | the sound waves |
| `/Game/Japan/Audio/A_Footstep` | shared attenuation: full volume within 3.5 m, then a natural falloff to −60 dB over 26 m; no occlusion |
| `/Game/Japan/Audio/DA_Footsteps` | the `UJapanFootstepSet` library (surface banks, material table, attenuation) the component loads at `BeginPlay` |

Then `atelier play yorimichi` and walk.

## Detecting a footfall

There are no anim notifies: the animation graph is native C++ (`FWandererAnimProxy`) with no Blueprint to hang them
on, and the clips are re-exported from Blender, which would drop them. The component instead watches the height of
`foot_L` and `foot_R` above the capsule floor every frame. A foot that has swung clear and comes back down has planted.
This works for every clip, blend and play rate (walk, jog, run, sprint, roll recovery) without authored markers.

The thresholds sit on the character definition's `RestAnkleHeights` (11.2 cm by default; Cairo's come from its
export), because rigs differ by several centimetres:

| | |
| --- | --- |
| Swing clear (re-arm) | rest ankle + 5.8 cm |
| Plant (fire) | rest ankle + 2.3 cm, descending, at least 0.1 s after that foot's last plant |
| Gate | walking on the ground (not skating or sailing) at 40 cm/s or more |

Below 40 cm/s the feet shuffle in place and every crossing would be a phantom step. Crouch-walking (50 cm/s) clears the
gate.

Each footfall costs one line trace (under the foot, 95 cm down from 45 cm above the capsule base), not one per frame. A landing plays
its own heavier step from `AWandererCharacter::Landed`: the fall speed (200 to 1100 cm/s) sets its weight (0.55 to
1.4) and its pitch is lowered to 0.82–0.9. Landings on the skateboard or the sailboat are skipped.

## Choosing the surface

The painterly pass gives every Blender material slot its own material instance, so the material under the foot names
the surface. The trace asks for the face index, reads the material at that triangle, strips the `MI_` or `M_` prefix
and looks the name up:

| Material | Surface |
| --- | --- |
| Ground, Hills, Grass, Moss, FarForest, Flower | `grass` |
| Road, Lane, Sand, Dirt | `dirt_gravel` |
| Stone, Rock, Concrete, Tile, Plaster, Paint, Metal, RoofTile | `stone` |
| Wood, Lattice, Bark, Vermilion | `wood` |
| Water, Mud | `mud_water` |
| Tatami | `barefoot` |
| Litter, LeafBroad, LeafCedar, LeafPine, LeafOchre, LeafMaple, LeafGinkgo, LeafSmall | `leaves` |
| Tree house: TH_wood_plank, TH_wood_timber, TH_wood_pale, TH_bark, TH_hull, TH_shingle, TH_rope | `wood` |
| Tree house: TH_stone, TH_tile, TH_plaster | `stone` |
| Tree house: TH_moss | `grass` |
| Tree house: TH_straw | `leaves` |
| Tree house: TH_rug, TH_rug_blue, TH_cushion, TH_quilt | `barefoot` |

Anything unmapped plays `grass`. One override: around the forest lake the ground is still the terrain material but the
floor is leaf litter, so a default hit between 1.24 and 2.0 lake radii from the centre plays `leaves`.
`world/regions/forest_lake/layout.py` clears every tree inside r = 1.24, which is where the canopy starts.

The table lives in `import_footsteps.py` and is baked into the data asset: adding a surface is a table edit and a
re-import, not a code change.

## Variation

Each surface draws from a shuffled bag without replacement, so the whole pool plays before any one-shot repeats. Volume
and pitch rise with speed between 60 and 320 cm/s (volume 0.32 to 1, pitch 0.96 to 1.06), then get a small random
spread (volume × 0.88–1, pitch × 0.94–1.06): a walk is quiet and slightly flat, a sprint full and bright.

## Console

| Variable | Does |
| --- | --- |
| `japan.FootstepVolume` | volume multiplier (default 1); 0 silences footsteps |
| `japan.FootstepDebug 1` | logs every footfall with its surface and the material it read, and whether the table had an entry |

`japan.FootstepDebug 1` is the first thing to try when a surface sounds wrong.

## Known gaps

- `stone` is 9 one-shots from one source, the pool most likely to sound repetitive.
- `barefoot` is hardwood recordings, not tatami, and no material in the world is named Tatami.
- Water is a footstep, not a splash: wading through the shallows plays the mud pool, with no depth-aware variant.
- No scuffs and no crouch-specific pool: crouch-walking draws the same pool at walk volume.
