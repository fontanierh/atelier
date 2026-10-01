# Camera, see-through and the noren

The island is crowded and the tree house rooms are tight, so the chase camera keeps ending up behind something:
leaves, trunks, posts, rails, props, a hut's wall. The camera works the way Breath of the Wild's does. Solid things
push it in. Thin things between it and Cairo fade out whole and come back. Nothing is cut open: there is no hole round
him, no room cutaway and no silhouette (a hole mode remains as a fallback switch).

## Build

```sh
uv run atelier build yorimichi unreal.compile unreal.treehouse unreal.see_through data.stage
```

- `unreal.compile`: the camera arm, the see-through component and the groups' fade modes.
- `unreal.treehouse`: builds `M_TreeHouse` with the whole fades and the cloth, and imports `TH_Frame` and
  `TH_Dressing` with their piece bake (it runs `world.treehouse` first when that is out of date).
- `unreal.see_through`: patches the leaves, the grass, the trunks, the guardrail, the poles, lanterns and torii, and
  Cairo, and creates or completes the collection. It reruns after `unreal.world` or `unreal.cairo`, which rebuild
  those materials.
- `data.stage`: copies the runtime data.

## What the player sees

- **Solid things stop the camera.** These are the terrain and cliffs, rocks, houses, the road's guardrail (part of the
  terrain), and the tree house's floors, decks, walls, roofs and trunks. When one comes between, the camera moves in
  front of it at once. When it clears, the camera eases back out over about a second. Swung into a wall, the camera
  slides in along it.
- **Squeezed, the camera rises.** When the arm is pulled in shorter than 1.6 m, the camera rises over Cairo and looks
  down at him instead of going into his head. It rises by up to 50 cm, reached at 64 cm. It does not rise when
  looking up from below, and never goes through a ceiling.
- **Never under the floor.** On the tree house, the camera stays at least 40 cm above the floor he stands on.
- **Thin things fade whole.** These are trees (trunk and crown together), bushes, poles, street lamps, stone lanterns,
  the torii, the tree house's props, and its rails, posts, ropes, lanterns, floats and noren. They do not stop the
  camera. When one hides Cairo, or comes close to the lens, the whole thing dithers out, and it comes back once it has
  passed. Which things fade depends on size and distance:
  - A thing at most 1.5 m in radius (posts, poles, bushes, lanterns, props, thin trunks) fades when it comes within
    30 cm of one of three sight lines and stands in front of him. The sight lines run from the camera to his head,
    chest and knees, and they widen toward him by 30 cm, his body.
  - A big thing (a tree's crown, the torii) counts only by a core 40 cm in radius along its axis, its trunk or post,
    and only near the camera: fully within 2.5 m, not at all beyond 3.5 m. Further off, a big thing may hide him for
    a moment, as a tree does in Breath of the Wild; a whole crown vanishing next to him would be the bigger jolt.
  - Anything thin whose surface comes within 60 cm of the camera fades whole, fully at 30 cm, before the lens clips
    it.
- **Near the lens.** Everything, solid or thin, also dithers out right at the lens:
  - solid things from 15 cm, gone at 5 cm (the camera keeps at least 14 cm off them anyway);
  - thin things from 40 cm, gone at 10 cm;
  - leaves from 80 cm;
  - grass from 1 m, gone at 25 cm.

  Cairo and his bokken dither out from 60 cm and are gone at 22 cm.
- **Fades, not pops.** The sight lines start from the camera's position, followed at 10/s. A thing swept across the
  view therefore fades over about a quarter of a second, not in the frames it takes to cross. The 30 cm band makes
  the fade gradual both ways. The dither changes every frame, and temporal anti-aliasing turns it into a soft fade.
  Shadows stay: a faded tree still casts its shadow.
- **Rooms.** The tree house rooms keep their colour grade. Nothing in them is cut away.
- **Noren move.** Each strip of a door curtain moves away from him as a whole. It swings ahead of him as he comes,
  aside as he passes and behind as he leaves. Once he has gone, the cloth he walked through is dragged his way,
  swings back past rest and settles within a second. A light wind moves them the rest of the time. The noren have no
  collision, so they never block him.

## How it works

### The camera arm

The camera arm is `UJapanCameraArm` (`unreal/Source/Yorimichi/JapanCameraArm.cpp`), a spring arm. The engine places
the camera where it wants it to be, with its lag, rotation and socket offset, but without its own probe. The arm then
works in four steps:

1. **Sweep.** It sweeps a 20 cm sphere (`ProbeRadius`) from the arm's origin, 35 cm over Cairo's centre, to that
   camera. The first hit is the hard limit. 20 cm keeps the near plane's corners (about 13 cm off at a 70° field of
   view) out of the wall. If his head is already within 20 cm of something (a low beam), it sweeps a 4 cm sphere and
   stops 16 cm short of that hit. The engine's `ProbeSize` is not used.
2. **Floor.** On the tree house, the hard limit keeps the camera `FloorClearance` (40 cm) over the floor he stands
   on. This applies when his movement base is tagged `JapanSeeThrough`, and through a jump or fall from it. It fades
   in and out over 0.4 s.
3. **Length.** A critically damped spring (Unity's SmoothDamp) takes the arm's length to the hard limit. It takes
   0.06 s going in (`PullInTime`) and 0.3 s going out (`EaseOutTime`), so it settles in about a second. The length
   never goes more than 6 cm past the hard limit, so the camera stays at least 14 cm off anything solid. A gap in
   the arm's updates, such as a camera cut or the zeppelin's free camera, starts it afresh.
4. **Squeeze.** Below `SqueezeLength` (1.6 m), once pulled in by 50 cm or more, the camera rises by up to
   `LiftHeight` (50 cm). The rise eases at 5/s, and an upward sweep keeps it under any ceiling. The camera then
   re-aims at the point it was looking at.

Only what blocks the camera channel stops the arm. `AJapanWorld` makes every thin group ignore it.

### Fade modes

`JapanSeeThrough::FadeMode` (`SeeThrough.cpp`) gives each world.json group a fade mode. `AJapanWorld` writes it into
the group's custom primitive data 0, which the materials read as the scalar parameter `FadeMode`. The Mega Park's
trees (`ASuperUltraMegaPark`) use the same modes; the far backdrop is always solid, so it skips the fade's vertex
work.

| Mode | Groups | Camera | Fade |
| --- | --- | --- | --- |
| 0, solid | everything else: the terrain (with the guardrail), rocks, houses, `TH_Structure`, `TH_Trunks` | stops it | lens only, 5 to 15 cm |
| 1, instances | `Tree*`, `HD_NorthTree*`, `HD_ArcadeTree`, `HD_PlazaTree*`, `Bush*`, `Pole`, `Pole_Lamp`, `Lantern`, `Torii`, `TH_P_*` (the tree house props) | passes | each instance whole, from its own position and mesh bounds |
| 2, pieces | `TH_Frame`, `TH_Dressing` with the piece bake (5 UV channels or more) | passes | each piece whole, from the bake in UV channels 1 to 4 |
| 3, near only | `Grass*`, `Litter`, `Lake_Plants`; `TH_Frame`, `TH_Dressing` without the bake | passes | lens only, 10 to 40 cm |

### The collection

`USeeThroughComponent` (`SeeThrough.cpp`) sits on the player's character. Every frame it writes the material
parameter collection `/Game/SeeThrough/MPC_SeeThrough`:

| Parameter | Value |
| --- | --- |
| `Focus` | Cairo's capsule centre (cm) and its half height |
| `Eye` | the camera position, followed at 10/s; a jump of more than 3 m is taken at once |
| `Fade` | the whole fades' strength (0..1), his body's clearance (30 cm), the lens range (60 cm), the big things' reach (250 cm) |
| `Cut` | the hole's radius and front margin (cm), the lens fade's strength (0..1), the hole's strength (0 unless in hole mode) |
| `Room`, `RoomSize`, `RoomShape` | hole mode only: the tree house room he is in, for the room cutaway |
| `Trail0`..`Trail3` | where he was every 0.3 s and how long ago: the path the noren swing from |

The collection lives outside `/Game/Japan`, so the world import (which clears that folder) never leaves the Cairo
materials pointing at a missing asset. With no game running, as in the editor, the defaults leave everything whole.

### The materials

Each patched material (`unreal/Scripts/see_through.py`) becomes masked. Its vertex shader works out one number for
the whole instance or piece: how much it hides Cairo or crowds the lens (`WHOLE`). It computes the piece's axis as a
segment with a radius, from the instance's bounds (mode 1) or from the bake (mode 2). It then measures the segment's
closest approach to the camera and to the three sight lines. Every vertex of a piece gets the same number, and a
vertex interpolator hands it to the pixels, so the piece fades evenly, with no edge. The pixel shader multiplies it
with the lens fade (`KEEP`) and dithers against interleaved gradient noise that shifts every frame. Shadow passes
keep every pixel. Modes 0 and 3 skip the vertex work.

| Material | Fades |
| --- | --- |
| `M_TreeHouse`: the structure, frame, dressing and the props | by the group's mode (the props 1, the frame and dressing 2 once baked), and the noren cloth |
| `MI_TH_trunk`: the trunks through the rooms | the lens fade (the trunks are solid), with `RoomCut` 0 for hole mode |
| `M_Foliage` (leaves, bushes, flowers, litter) | mode 1; the lens fade reaches 80 cm |
| `M_Grass` (the grass tufts) | the lens fade only, reaching 1 m |
| `M_Painted` through its instances, switched to masked (`PAINTED` in see_through.py): `MI_Bark` (trunks), `MI_Paint` (the guardrail), `MI_Concrete`, `MI_Metal`, `MI_Wood` (poles), `MI_Stone` (stone lanterns), `MI_Vermilion`, `MI_Tile` (the torii) | by the group's mode |
| `M_Cairo_*`, `M_Bokken_*` | dither out near the camera |

The vector parameter `CutScale` scales the lens fade's distances (z) per material or instance (`SCALES` in
see_through.py); its x and y scale the hole. Every patch is idempotent, and a material carrying the hole-only patch
(tag `Japan see-through`) is upgraded in place, keeping whatever fed its mask before, such as the leaves' distance
fade.

### The piece bake

`TH_Frame` and `TH_Dressing` are merged meshes, so their instance bounds cover the whole house. To fade a rail or a
lantern whole, the tree house build (`treehouse/tmesh.py`) writes each vertex's piece into four more UV layers, after
`UVMap`. The values are in Blender metres and axes:

| Layer | u | v |
| --- | --- | --- |
| `Piece1` | centre x − vertex x | centre y − vertex y |
| `Piece2` | centre z − vertex z | the piece's radius round its axis |
| `Piece3` | half axis x | half axis y |
| `Piece4` | half axis z | 1 (0: the vertex belongs to no piece and never fades) |

The FBX import flips every v, and `PIECE` in see_through.py undoes it. The import keeps both meshes' UVs at full
precision, so every vertex of a piece finds the same centre. A mesh with fewer than 5 UV channels is not read this
way: the game gives it mode 3 and logs `SEE-THROUGH TH_Frame: fades at the lens only, no piece bake`.

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
  segment counts by its length and its age, so a new sample or a dropped old one never makes the cloth jump. A jump
  of more than 2 m in a frame (a map travel, a respawn) starts the trail afresh.
- **The swing.** Each vertex then moves on a circle as long as it hangs below the band. Pushed aside, it rises, and
  however hard it is pushed it never leaves the strip's length. The material's maximum world position offset is
  60 cm, which grows the instances' culling bounds to match.

The cloth moves whether or not the see-through is on. It only needs the component running.

### Hole mode, the fallback

`japan.SeeThroughHole 1` switches to:

- a soft round hole round Cairo, cut per pixel, instead of the whole fades;
- the near walls and roof of the tree house room he is in, opened on the camera's side;
- the camera probe passing the tree house (`AJapanWorld::SetSeeThroughProbe`).

The rooms are the room-grade boxes and round rooms from `treehouse/runtime.json`. The switch blends over a quarter
of a second.

## Switches

| Console variable | Default | |
| --- | --- | --- |
| `japan.SeeThrough` | 1 | 0 turns every fade off, over a third of a second. The arm still stops at solid things, and thin things still let it through |
| `japan.SeeThroughHole` | 0 | 1: the hole and room cutaway instead of the whole fades, and the camera probe passes the tree house |
| `japan.SeeThroughRadius` | 55 | the hole's radius round Cairo, in cm (10 to 300), in hole mode |

At start the log says `SEE-THROUGH active: whole fades like Breath of the Wild (japan.SeeThroughHole 0), N tree
house rooms, N tree house groups, tree house material ready, switch japan.SeeThrough 1`. A change of mode logs
`SEE-THROUGH now ...`. At load, the world logs `SEE-THROUGH TH_Dressing: fades piece by piece (5 uv channels)`, or
`fades at the lens only, no piece bake`. If the collection is missing, it says `SEE-THROUGH off: ... missing`. The
fixed review and trailer views have no fades.

## What to check in game

- Swing the camera behind trees, bushes, poles, stone lanterns and the torii. Each should fade out whole and come
  back over about a quarter of a second, with no hole and no pop. A big tree 4 m or more from the camera may hide
  him for a moment.
- Run along walls, cliffs and houses, and through the tree house rooms and doorways. The camera should slide in,
  never through a wall, and ease back out without jitter. In a tight corner it should rise a little and look down
  at him rather than go into his head.
- Swing the camera low and high on the bridges and decks. It should never go under the floor.
- Walk the main road along the guardrail with the camera swung out over the drop. The camera should stay on the
  road side or ride over the rail, with no hole.
- Push the camera into tall grass and into a bush. No blade or leaf should fill the screen.
- Push the camera into Cairo. He should fade out smoothly, and the bokken with him.
- In the tree house rooms the colour grade should still change, and no wall or roof should open.
- Walk and run through every noren, straight, at an angle and slowly. The strips should part round his head
  without passing through it, and swing back and settle after. Stand under one, and check the band under the rod
  stays still.
- `japan.SeeThroughHole 1` and back to 0, and `japan.SeeThrough 0` and 1.
- Performance: compare frame times in a dense forest view with `japan.SeeThrough` 1 and 0. The vertex shader does a
  little more work on thin things.

## Limits

- The houses on the main road, the village, the lake, the skate pier, part of the city and the other kit-built
  places share one opaque material, `M_Village`. It does not fade, so their groups are solid. Their thin parts, such
  as fences and signs, push the camera in like walls.
- A solid thing that comes between the middle of the arm and Cairo (a house corner as he walks past) moves the camera
  in within a frame or two. The camera never waits behind it.
- The fade is spatial, and has no timer. A thing that stops at the edge of the 30 cm band stays half faded.
- A piece fades as one straight segment, so a long, bent piece (a rope along a whole bridge) must be split: the build
  cuts the bridges' hand ropes every 1.2 m and the lookout's spiral rope at every other tread. Split any new long run
  the same way.
- A strip he walks into the exact middle of (within 4 cm) cannot part: there it would have to drape over him. When
  he runs past a strip's middle at an angle, that strip flicks across quickly.
- Scene captures (none today) would also see the fades: the parameters are global to the world.
