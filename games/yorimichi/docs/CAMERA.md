# Camera see-through and the noren

The island is crowded and the tree house rooms are small, so the chase camera keeps ending up behind something:
leaves, trunks, posts, rails, props, a hut's roof. Rather than pull the camera in front of every obstacle (in a small
room that puts it inside Cairo's head), the game keeps the camera where it is and lets what hides him go.

## What the player sees

- **A hole round Cairo.** Whatever stands between the camera and Cairo dithers away in a soft round hole around his
  body: leaves, bushes, grass, trunks, the road's guardrail, poles, the torii, and all of the tree house. The hole
  starts 35 cm in front of him, so nothing touching him is cut. On the guardrail it starts 9 cm in front of him, so
  the rail is gone even when he walks along it. The floor under his feet and everything behind him stay. The houses
  and the rest of the village kit are not cut (see Limits).
- **Rooms open on the camera's side.** Inside a tree house room, the walls between the camera and him and the
  ceiling and roof over his head open while the camera is outside or above the room. The far walls stay. A change
  of room closes the old one before it opens the new one.
- **A camera that stays back.** The camera's probe passes the whole tree house and the see-through deals with it,
  so the arm stays long. The ground and the rest of the world still stop the camera. When something does stop it,
  the arm pulls in at once and eases back out once the way is clear, with no snapping. On the tree house, the
  camera stays at least 40 cm above the floor he stands on.
- **Near the camera.** Anything closer than 40 cm to the camera fades out and is gone at 10 cm, so you never see
  half-clipped planks. Grass fades from 1 m and is gone at 25 cm, so a tuft by the lens never fills the screen.
  Cairo and his bokken dither out from 60 cm away and are gone at 22 cm.
- **Fades, not pops.** The cut fades in over a third of a second and a room opens over a quarter. The dither
  changes every frame and temporal anti-aliasing turns it into a soft fade.
- **Noren move.** Each strip of a door curtain moves away from him as a whole. It swings ahead of him as he comes,
  aside as he passes and behind as he leaves. Once he has gone, the cloth he walked through is dragged his way,
  swings back past rest and settles within a second. A light wind moves them the rest of the time. The noren
  have no collision, so they never block him.

## How it works

`USeeThroughComponent` (`unreal/Source/Yorimichi/SeeThrough.cpp`) sits on the player's character. Every frame it
writes the material parameter collection `/Game/SeeThrough/MPC_SeeThrough`:

| Parameter | Value |
| --- | --- |
| `Focus` | Cairo's capsule centre (cm) and its half height |
| `Cut` | the hole's radius (cm), how far in front of him it starts (35 cm), the near-camera fade (0/1), strength (0..1) |
| `Room`, `RoomSize`, `RoomShape` | the tree house room he is in: centre and yaw, half size and how open it is, round or box |
| `Trail0`..`Trail3` | where he was every 0.3 s and how long ago: the path the noren swing from |

The collection lives outside `/Game/Japan`, so the world import (which clears that folder) never leaves the Cairo
materials pointing at a missing asset. With no game running (in the editor), the defaults put the cut far away
with no strength, so nothing is cut.

Each material that reads it (`unreal/Scripts/see_through.py`) becomes masked and gets one extra calculation per
pixel. It finds the closest point between the ray from the camera through that pixel and Cairo's body axis, from
his feet to his head. If the ray passes within the radius, and the pixel is in front of him and above his feet, the
pixel is dropped. The dither compares that result with interleaved gradient noise that shifts every frame. Shadow
passes keep every pixel, so a cut-away roof still casts its shadow.

| Material | Cut |
| --- | --- |
| `M_TreeHouse`: the structure, the dressing and the 13 props | the hole and the room walls and roof |
| `MI_TH_trunk`: the camphor's trunk through the rooms | the hole only (`RoomCut` 0), so it is never cut at ceiling height |
| `M_Foliage` (leaves, bushes, flowers, litter) | the hole |
| `M_Grass` (the grass tufts, already masked for their distance fade) | the hole; the near-camera fade reaches 1 m |
| `M_Painted` through `MI_Bark` (tree trunks), `MI_Paint` (the road's guardrail, part of the terrain mesh), `MI_Metal` and `MI_Wood` (poles), `MI_Vermilion` and `MI_Tile` (the torii); `MI_RoofTile`, `MI_Plaster`, `MI_Lattice` have no mesh today | the hole; these instances are switched to masked (`PAINTED` in see_through.py), the ground, road, water, rock, stone and far forest stay opaque. On `MI_Paint` the hole starts 9 cm in front of him |
| `M_Cairo_*`, `M_Bokken_*` | dither out near the camera |

`M_Grass` and `M_Painted` carry the scaled cut. Its vector parameter `CutScale` multiplies the hole's radius (x),
how far in front of him it starts (y) and the near-camera fade distances (z), per material or instance (`SCALES`
in see_through.py: `M_Grass` (1, 1, 2.5, 1), `MI_Paint` (1, 0.25, 1, 1)). It also leaves early, keeping the pixel,
wherever no cut can reach: every ray the hole takes passes closer to his centre than his half height plus the
hole's radius, so a pixel beyond that sphere, or outside the cone it makes from the camera, costs a few
instructions instead of the whole cut. In a chase view over grass that is more than 99% of the pixels. The tree house and the leaves keep the
first version, without the early exit.

The rooms are the room-grade boxes and round rooms from `treehouse/runtime.json`. A round room gives its height
as `half_height`. Cairo must be 10 cm inside a room to enter it and 25 cm outside to leave it, so the walls do not
flicker at a doorway.

The camera arm is `UJapanCameraArm` (`JapanCameraArm.cpp`), a spring arm. Its probe hits the tree house's collision
as before. When the see-through is on, it sweeps again, ignoring the tree house's instance groups (tagged
`JapanSeeThrough`), and only the terrain and the rest of the world count. The tree house keeps its collision, so
Cairo still walks on it and other traces still see it.

### The noren

`treehouse/build.py` cuts every noren into a band under the rod and six strips with slits between them (one slit in
the middle, where Cairo walks through). Each strip is two columns by six rows, drawn on both sides. The vertex
colour's alpha says how freely a vertex hangs: 0 down to the bottom of the band, rising to 1 at the hem. The tree
house material's world position offset (`CLOTH` in `see_through.py`) moves only vertices with alpha:

- **The strip it belongs to.** The material finds each vertex's strip from its u coordinate, in sixths. It finds the
  strip's middle from the vertex tangent (the direction u runs), assuming a curtain about 85 cm wide. The whole
  strip moves 30 cm away from Cairo's axis when he is at it, less as he gets further, and not at all from 50 cm
  away. The push leans to the side: a strip goes mostly aside unless he is nearly in line with its middle, so it
  does not whip round him from front to back as he walks straight through.
- **The trail.** Near any point of the last 1.2 s of his path, the cloth swings along the way he was going,
  starting at his speed. It is a damped oscillation that settles by the time that point is 0.9 s old. Each trail
  segment counts by its length and its age, so a new sample or a dropped old one never makes the cloth jump.
- **The swing.** Each vertex then moves on a circle as long as it hangs below the band. Pushed aside, it rises, and
  however hard it is pushed it never leaves the strip's length. The material's maximum world position offset is
  60 cm, which grows the instances' culling bounds to match.

The cloth moves whether or not the see-through is on. It only needs the component running.

## Switches

| Console variable | Default | |
| --- | --- | --- |
| `japan.SeeThrough` | 1 | 0 turns off the hole, the rooms and the near fades (over a third of a second), and the camera probe stops at the tree house again |
| `japan.SeeThroughRadius` | 55 | the hole's radius round Cairo, in cm (10 to 300) |

At start the log says `SEE-THROUGH active: radius 55 cm, N tree house rooms, N tree house groups, tree house cut
yes, switch japan.SeeThrough 1`. If the collection is missing, it says `SEE-THROUGH off: ... missing`. When the
probe changes, it says `SEE-THROUGH camera probe passes the tree house`. The fixed review and trailer views have
no cut.

## Build

```sh
atelier build yorimichi unreal.compile world.treehouse unreal.treehouse unreal.see_through data.stage
```

- `unreal.compile`: the component, the camera arm and the tree house groups.
- `world.treehouse` (Blender): the noren strips, their alpha, and the round room's `half_height`.
- `unreal.treehouse`: rebuilds `M_TreeHouse` with the cut and the cloth, and makes `MI_TH_trunk`.
- `unreal.see_through`: patches the leaves, the grass, the trunks, the guardrail, the poles and torii, and Cairo. It
  reruns after `unreal.world` or `unreal.cairo`, which rebuild those materials. On a project patched before the
  scaled cut it takes `M_Painted`'s earlier cut off and puts the scaled one on.
- `data.stage`: copies the new runtime.json.

The camera probe passes the tree house only while `M_TreeHouse` is masked, that is, while it has the cut. An old
tree house import keeps the old camera.

## What to check in game

- Walk the forest and the villages with trees, bushes, poles and the torii between you and the camera. Cairo should
  show through a soft round hole, with no hard edges and no shimmer once you stop moving. The ground under him
  should stay.
- Walk the main road along the guardrail with the camera swung out over the drop. The rail should be gone in
  front of him, even with him right against it. Grind the rail: the rail under his feet should stay.
- Push the camera into tall grass by the road. No blade should fill the screen, and the grass further off and the
  grass round his feet should stay.
- In each tree house room, the round Heart room included, swing the camera round Cairo. The near wall and the
  roof should open, and the far wall and the floor should stay. Walk from room to room and across the bridges:
  the opening should follow without jumping, and nothing outside should be cut away.
- Swing the camera low and high on the bridges and decks. It should stay out of Cairo's head, and should not
  dive under the floor.
- Run against a cliff or a big wall. The camera should still stop there, pull in, and ease back out once clear.
- Push the camera into Cairo. He should fade out smoothly, and the bokken with him.
- Walk and run through every noren, straight, at an angle and slowly. The strips should part round his head
  without passing through it, and swing back and settle after. Stand under one, and check the band under the rod
  stays still.
- `japan.SeeThrough 0` and `1`, and `japan.SeeThroughRadius 100`.
- Performance: every leaf is now masked with one extra calculation per pixel. Compare frame times in a dense
  forest view (`japan.SeeThrough 0` does not remove that cost, only the hole).

## Limits

- The hole is a round shape. A long wall or roof between the camera and Cairo shows a round window, not the whole
  wall gone.
- The houses on the main road, the village, the lake, the skate pier, part of the city and the other kit-built
  places share one opaque material, `M_Village`, and are not cut. Masking it would take early depth rejection away
  from everything built with it. A cheaper way would be a masked copy of it given to the houses and huts alone.
- A strip he walks into the exact middle of (within 4 cm) cannot part: there it would have to drape over him. When
  he runs past a strip's middle at an angle, that strip flicks across quickly.
- The see-through has no memory of what it cut. A thin rail passing across the hole's edge dithers in and out.
- Scene captures (none today) would also see the cut: the parameters are global to the world.
