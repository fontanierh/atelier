# Footsteps in the game

> Moved from the prototype repository on 29 September 2026. Paths are translated to this repository where the file moved; paths still starting with `japan/` or `output/imagegen/` refer to the prototype archive (authoring tools, earlier revisions, review images). See [docs/MIGRATION.md](../../../docs/MIGRATION.md).

The first sound in Yorimichi. 531 one-shots across 7 surfaces, picked and played from the
character's own foot bones. Build it with:

```bash
atelier build yorimichi unreal.sounds
```

That slices the Sonniss masters, compiles the module, and imports the library. Then
`atelier play yorimichi` and walk.

## How it decides a foot has landed

There are no anim notifies. The animation graph is native C++ (`FWandererAnimProxy`) with no
Blueprint to hang notifies on, and the clips are re-exported from Blender on every character
pass, which would drop them anyway.

Instead `UJapanFootstepComponent` watches the height of `foot_L` and `foot_R` above the capsule
floor. A foot that has swung clear and then comes back down below the threshold has planted.
This works for every clip, every blend and every play rate — walk, jog, run, sprint, the roll
recovery — without a single authored marker.

The two thresholds ride on the character's own `RestAnkleHeights`, because the rigs differ:
Warm Original rests at 11.2 cm, the older Wanderer at about 14.7.

| | |
| --- | --- |
| swing clear (re-arm) | rest ankle + 5.8 cm |
| plant (fire) | rest ankle + 2.3 cm, descending |
| gate | on the ground, not riding, faster than 40 cm/s |

Those numbers were picked by replaying the detector over the recorded foot telemetry in
`out/cape_boy/gameplay/telemetry.csv` — it gives 133 footfalls/min at a walk, 180 at a jog and
200 at a run, alternating feet, with nothing firing while idle.

Cost is one line trace per footfall — about two a second — not one per frame. A landing fires
its own heavier step from `AWandererCharacter::Landed`, scaled by the drop.

## How it decides what you're standing on

The painterly pass gives every Blender material slot its own material instance, so the material
under the foot already names the surface. The trace asks for a face index, reads the material
at that triangle, strips the `MI_` prefix and looks the name up:

| Material | Surface |
| --- | --- |
| Ground, Hills, Grass, Moss, FarForest, Flower | `grass` |
| Road, Lane, Sand, Dirt | `dirt_gravel` |
| Stone, Rock, Concrete, Tile, Plaster, Paint, Metal, RoofTile | `stone` |
| Wood, Lattice, Bark, Vermilion | `wood` |
| Water, Mud | `mud_water` |
| Litter, Leaf* | `leaves` |
| Tatami | `barefoot` |

Anything unmapped falls back to `grass`. One override on top: around the forest lake the ground
is still the terrain material but the floor is leaf litter, so a hit between 1.24 and 2.0 lake
radii from the centre plays `leaves` instead. Those bounds are not guesses — `forest_lake/
layout.py` clears every tree inside r=1.24, which is exactly where the canopy starts.

The table lives in `Scripts/import_footsteps.py` and is baked into the data asset, so adding a
surface is a table edit and a re-import, not a code change.

## Variation

Every play draws from a shuffled bag per surface — without replacement, so the same one-shot
never comes round twice in a row and the whole pool is heard before any repeat. On top of that,
volume and pitch both scale with how fast the foot arrived and then get a small random spread:
a walk whispers at about a third of the volume and slightly flat, a sprint is full and bright.

## What the pieces are

| | |
| --- | --- |
| `Source/JapanProto/JapanFootsteps.h/.cpp` | the component, the data asset class, the detection |
| `Scripts/import_footsteps.py` | imports the WAVs, builds `A_Footstep` and `DA_Footsteps` |
| `/Game/Japan/Audio/DA_Footsteps` | the library the component loads at BeginPlay |
| `/Game/Japan/Audio/A_Footstep` | shared attenuation — natural falloff, silent by 26 m |
| `audio/footsteps/` | the sliced sources, and the README on where they came from |

## Console

```
japan.FootstepVolume 0     silence them
japan.FootstepDebug 1      log every footfall with its surface and the material it read
```

`japan.FootstepDebug 1` is the first thing to reach for if a surface sounds wrong: it prints the
material name it found and whether the table had an entry for it.

## Known gaps

- **`stone` is 9 one-shots** from one source. It is the pool most likely to sound repetitive.
- **`barefoot` is hardwood**, not tatami, and nothing maps to it yet — no interiors have a
  Tatami material.
- **Water is a footstep, not a splash.** Wading through the shallows plays the mud pool; it has
  no depth-aware variant.
- **No scuffs, no landings-into-run, no crouch-specific pool.** Crouch-walking (50 cm/s) does
  clear the 40 cm/s gate, so sneaking is audible — but it draws the same pool at walk volume
  rather than anything quieter or softer-edged.
- Nothing else in the game makes a sound yet. See [SOUND_RESEARCH.md](SOUND_RESEARCH.md) for
  what generates the rest.
