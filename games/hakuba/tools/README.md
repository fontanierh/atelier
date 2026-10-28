# Tools

The asset exporter (`../assets/README.md` describes an asset folder). Run it from `games/hakuba`:

```sh
cargo export assets/characters/nox     # export one asset folder
cargo export assets                    # export every asset folder, each after the assets it reads
cargo export --check assets            # list the exports whose inputs changed
```

`cargo export` is an alias in `../.cargo/config.toml` for running the `export` crate.

## What lives here and what lives in an asset

- **The exporter** holds how every asset of a kind is made: the methods, shared by all of them. It holds no asset's
  own numbers or shapes.
- **An asset** holds what that asset is: its source files and code in `src/`, such as a region's roads, and its
  own numbers in `asset.toml`, such as a character's stance.
- **The export** (`<asset>.glb` and what sits beside it) is written by the exporter and never edited by hand.

The exporter names assets in one place per kind, a list that compiles in each asset's `.rs` file:
`rig/animations.rs`, `rig/characters.rs` and `world/regions.rs`. If a second asset would need the same code, it belongs in
the exporter; if only this asset has it, it belongs in the asset.

```text
tools/
  export/
    Cargo.toml              the crate and its dependencies
    src/
      main.rs               the `export` command: reads asset.toml, runs its kind's exporter, records its inputs
      glb.rs                reading, editing and writing .glb files, shared by every kind
      shapes.rs             closed tubes, boxes and cards that meshes are built from, shared by every kind
      random.rs             repeatable random numbers, shared by every kind
      rig/                  the rig, and the `animation` and `character` kinds made on it
        mod.rs              the rig and the `Skeleton` trait
        pose.rs             poses: each rig bone's world rotation and position
        pose_edit.rs        turning bones, moving the body and bending legs, shared by the retarget and animations
        retarget.rs         moving a clip from one skeleton onto another
        animation.rs        the `animation` kind
        animations.rs       every animation, and the `Animation` trait each implements
        character.rs        the `character` kind
        characters.rs       every character, and the `Character` trait each implements
        equipment.rs        the `equipment` kind
      texture/
        mod.rs              the `texture` kind
      sound/
        mod.rs              the `sound` kind
      model/                still models: the `plant` and `prop` kinds
        mod.rs              writing a model's versions and anchors
        plant.rs            the `plant` kind
        prop.rs             the `prop` kind
      world/                the `world` kind
        mod.rs              the settings, and cutting the world into tiles
        regions.rs          every region, and the `Region` trait: what a region adds to the world
        checksums.rs        what each tile is made from, so an export rebuilds only the tiles that changed
        ground.rs           the ground's heights, read from its pages
        levelling.rs        strips of ground a region levels along a course, with shoulders easing back to the ground
        overlay.rs          flat shapes laid over the ground, such as roads
        curve.rs            a smooth curve through a course's points, sampled every metre
        ribbon.rs           strips of even width along a curve, for regions to lay as overlays
        scenery.rs          the models, cables and rails regions stand on the ground, shared out between tiles
        surface.rs          finding what lies under a point of a mesh, and cutting shapes along its triangles
```

## The rig

Every animation is made once on the rig, a 52-bone humanoid skeleton (`RIG` in `rig/mod.rs`): the pelvis, spine,
neck and head, and per side the clavicle, arm, hand with five three-bone digits, leg, foot and toe. Its rest pose
is a T-pose facing +Z with the character's left at +X, the pelvis one hip height above the ground, and every rest
rotation the identity. Clips on the rig store each bone's world turn, and the pelvis's position in hip heights, so
they fit any skeleton of any size.

A skeleton implements `Skeleton`, naming its node for each rig bone. The spine's middle and the fingers are
optional; a skeleton without them gets them from its neighbours. `Bones::library()` is the skeleton of the motion
library every animation's clip comes from; `Bones::mixamo()` is Mixamo's.

A hand's palm has a frame (`pose::palm`): its y axis from the wrist toward the knuckles, its z axis from the index
finger toward the little finger. The retarget turns each hand so its palm faces as the source's does, so something
held in the palm's frame sits in every character's hand as it did in the library's.

## Characters

A character's file, `src/<name>.rs` in its asset folder, implements `Character`: its name and which of its bones
plays each rig bone (`Skeleton`). Every character gets every animation, so the whole move set works for any
character whose skeleton maps to the rig. `characters.rs` lists it in `CHARACTERS`. Its changes to the animations are numbers in its
`asset.toml`, one table per animation, such as `[animations.idle]`. Each animation's file defines what its table may
hold; a character leaves out the animations and fields it does not change. A table for no animation, or an unknown
field, fails the export.

## Kinds

`asset.toml` is read into the `Asset` enum in `main.rs`: `kind` picks the variant, and the other keys are that
kind's settings. A missing, misspelled or unknown setting fails the export. Each kind is one module with a
`Settings` struct and an `export` function that writes the folder's export.

**`animation`** retargets a clip onto the rig and writes the rig playing it, named after the folder. Its
`src/<name>.rs` implements `Animation`: its name, the skeleton its clip is on, what a character may change in it
and how those changes apply. `animations.rs` lists it in `ANIMATIONS`. The folder's name picks it there.

The clip loses its root motion, the travel of its skeleton's top node: the game moves the character, so a run stays
in place and a jump stays on the ground. A node `clip` beside the skeleton keeps how fast the root travelled over the
ground, in hip heights a second (`{"speed": ...}`), for the character export.

| Setting  | Meaning                                                                  |
|----------|--------------------------------------------------------------------------|
| `source` | the file holding the clip, relative to the folder                        |
| `clip`   | the clip's name in that file                                             |
| `rate`   | how fast it plays, as a share of its source's speed (1 if left out)      |
| `frames` | the first and last source frames it plays (all of them if left out)      |

**`character`** exports a character's model: scaled to its height, textures resized, morph targets removed, and
every animation fitted to it with the character's changes. Its rig bones are renamed to the rig's names. Where a
fitted stride is longer than the character's legs reach, the body lowers just enough. Beside the model, for the game:

- `grip_r`, an empty node under the right hand: its palm's frame at the wrist, moved and turned by `hold`. The game
  puts what the character holds there, such as the paraglider.
- `clips`, an empty node whose extras give how fast each clip carries the character over the ground, in metres a
  second: the clip's speed on the rig times the character's hip height (`{"speeds": {"run": 5.1, ...}}`). Clips that
  stay in place are left out.

| Setting        | Meaning                                                                         |
|----------------|---------------------------------------------------------------------------------|
| `source`       | the model, relative to the asset folder                                         |
| `height_m`     | how tall the character stands in the game                                       |
| `texture_size` | the largest side of any texture, in pixels                                      |
| `animations`   | its changes to each animation, by name                                          |
| `hold`         | where its right hand holds things: `offset_cm` and `turn_deg` from its palm's axes |

**`equipment`** writes something a character holds, such as the paraglider, as `<folder name>.glb`, playing its one
clip under the folder's name. It comes from the motion library with the skeleton that held it there, and is drawn at
its source's size, the size that skeleton held it at. Its export is placed in that skeleton's body frame between its
fists, each the middle of its wrist and its middle finger's three bones, so a character holds it between its own fists
as the library's skeleton did. A node `holder` gives, in its extras, in the export's frame, left then right: how high
the skeleton's hips stand; its two handles, each the stretch of tube a fist closes round from its back end to its
front end, with the tube's radius; and the skeleton's two palm frames as it held them (`pose::palm`), each its origin
at the wrist and its rotation. A character puts each of its hands exactly there, turned so its own palm frame is that
one, and closes its fingers round the handle. The export fails if a joint of the holder's fingers lies more than 2 cm
off its handle's surface: then it did not hold that handle.

| Setting            | Meaning                                                                    |
|--------------------|----------------------------------------------------------------------------|
| `source`           | the equipment, with its clip, relative to the folder                       |
| `clip`             | the clip's name in that file                                               |
| `holder`           | the skeleton that held it, at rest, relative to the folder                 |
| `pose`             | the holder's clip whose first frame holds it                               |
| `held_at`          | the holder's bone its root sits at                                         |
| `handle_left_m`    | the left handle's stretch, back end then front end, in the source's frame  |
| `handle_right_m`   | the right handle's                                                         |
| `handle_radius_m`  | the handles' tube's radius in the source                                   |

**`texture`** writes an image as `<folder name>.ktx2`, with every mipmap level so it draws smoothly near and far.
Each level averages the one above it in linear light, each colour weighted by its opacity, and is stored as 8-bit
sRGB, compressed with zstd. In an image with clear parts, such as leaves, every level keeps at least the share of
pixels opaque enough to show, so leaves stay as full far away as near. Its sides must be powers of two.
When `alpha_shadow` is true, the exporter also writes `<folder name>.alpha.ktx2`; its single channel contains the
same alpha byte from each finished colour mip. Source foliage names this companion for its shadow-only mesh, and the
export check rejects missing or mismatched companions.

| Setting  | Meaning                                       |
|----------|-----------------------------------------------|
| `source` | the image, PNG or JPEG, relative to the folder |
| `alpha_shadow` | export an exact single-channel companion for source foliage shadows (default false) |

**`sound`** writes a sound's takes, WAV files at one sample rate and channel count, one after the other with 50 ms of
silence between, as `<folder name>.ogg` (Ogg Vorbis, which the browser and the desktop both decode), and where each
take starts and how long it lasts as `<folder name>.takes.json`, which also says whether the takes loop.

| Setting   | Meaning                                                          |
|-----------|------------------------------------------------------------------|
| `takes`   | each take, a WAV file relative to the folder                     |
| `looped`  | whether the game loops each take; then each must loop seamlessly |
| `quality` | the Vorbis quality, from -0.1 (smallest) to 1 (best)             |

**`plant`** builds a tree, a bush or a tuft of grass from its settings alone, in its own frame (x and y level, z up,
metres, its foot at the origin), and writes it as `<folder name>.glb`. A tree or bush is `wood`, a trunk of bark
with a branch to each clump of leaves, and `leaves`, cards cut out of a leaf image scattered through those clumps.
Grass is a `tuft` of curved blades coloured per vertex; it casts no shadow. Every model reaches below its foot, so
it stands on sloping ground with no gap; the export fails if it does not. A plant with `middle_cards` also writes a
lighter `middle` version for seeing from afar.

| Setting  | Meaning                                                                                           |
|----------|---------------------------------------------------------------------------------------------------|
| `seed`   | the seed of every random draw                                                                     |
| `wood`   | its bark's texture, its trunk's points and radii, and the radius of its branches                   |
| `leaves` | its leaves' texture and tint, how many cards in each version and how wide, and its clumps of leaves |
| `tuft`   | how many blades, their spread, height, width, curl and colours                                    |

**`prop`** builds a made object, such as a pole, from closed tubes, boxes and convex prisms of plain colours, in the same frame as
a plant, and writes it as `<folder name>.glb`. Its anchors are empty nodes `anchor 0`, `anchor 1` and so on, the
points other things fasten to, such as cables.

| Setting     | Meaning                                         |
|-------------|-------------------------------------------------|
| `materials` | each material's linear colour, by its name      |
| `tubes`     | each tube's ends, radii, sides and material     |
| `boxes`     | each box's centre, size and material            |
| `prisms`    | each closed prism: a strictly convex `profile` of `[x, z]` points in order, `y = [start, end]` with start less than end, and `material`, all coordinates in metres |
| `solid`     | optional; when true, the prop is solid to scenery raycasts (default false) |
| `anchors`   | the points other things fasten to               |

As an alternative to generated shapes, a prop may set `source` to an embedded GLB under its own `src/` folder.
It cannot combine `source` with materials, shapes or anchors. The GLB has one identity-frame scene root named
`full`, and may have a second root named `collision`. Both contain static, tightly packed indexed triangles with
finite float positions and optional normals, UVs and colours; textures, animation and external buffers are not
supported. The full mesh reaches below its foot. With `solid = true`, the full mesh supplies raycast collision unless
the source has a `collision` root; that root then supplies the collision without being rendered or casting a shadow.
Source extras on `full` are preserved except `solid`, which is set from the prop settings. A static `vertex_paint`
profile requires RGBA vertex colours with zero alpha
(the motion weight) and an opaque material; this alpha is not opacity.

**`world`** builds the ground from the height pages in `src/ground/`, lays over it what each region adds, and cuts
them into square tiles under `tiles/`. Each region's `src/regions/<region>/layout.rs` implements `Region`, and
`world/regions.rs` lists it. Each tile is written in full detail and in middle detail, for seeing from afar. The
ground and each overlay show a texture asset, named by its folder: a tile points at the texture's `.ktx2` and never
holds it, and the export fails if no such texture asset exists. An
overlay lies a few centimetres above the ground triangles under it; the export fails if it comes closer anywhere, or
if in full detail it creases by more than 1.5° between two of its triangles. A region levels the ground under its
overlays with levelled strips (`world/levelling.rs`): along a course, the ground within a half width is level across
it and smooth along it, and a shoulder eases back to the ground without a crease. A strip can instead specify
endpoint heights and grades; the exporter interpolates these along its sampled course. Curves include both authored
endpoints, with a shorter final interval when needed. The strips change the heights once,
after the pages are read, so the tiles, overlays and scenery all stand on the levelled ground. A region can also
declare rectangular pads at a given height and slope, with shoulders easing back to the ground. A pad's planar margin
covers a coarse tile cell around its footprint, so the full and middle ground both draw the same plane. Pads apply
after strips and own the final ground at crossings; the export rejects overlapping pads. Regions
can declare corridors kept clear of scattered trees, bushes or grass. Scatter candidates use an origin-anchored grid
that includes boundary cells, so extending the exported area keeps candidates inside the old area unchanged. Scatter
producers check these shared clearances; explicit placements and their cable indices are unchanged.

A region also stands scenery on the ground: plant and prop models, each at a point with a turn and a scale, cables
between authored world endpoints, and rails along authored three-dimensional points. A tile names each model's `.glb` and each
texture's `.ktx2` and lists where its copies stand, seated on the ground that tile draws; it never holds them. A
placement may specify a signed origin offset from that ground or an explicit authored world height shared by both
detail versions; its model and intended embedment need an independent grounding check. The export fails if a model or
texture asset does not exist, if a model stands on an overlay, or if a cable comes closer than 2 m to the ground.
`<folder name>.glb` holds a node per tile, at its centre, and the spawn.

| Setting             | Meaning                                                               |
|---------------------|-----------------------------------------------------------------------|
| `ground`            | the folder of the ground's height pages, relative to the asset folder |
| `south_west_m`      | the world's south-west corner on the map, where pages and tiles start |
| `ground_step_m`     | the distance between neighbouring heights                             |
| `page_steps`        | how many heights apart page edges are                                 |
| `tile_steps`        | how many heights apart tile edges are                                 |
| `tiles`             | the first and last tile exported, each as `[column, row]`             |
| `extent_m`          | optional ground-grid-aligned map rectangle clipping boundary tiles    |
| `middle_uses_fine_ground` | whether middle tiles retain full-detail ground triangles       |
| `ground_texture`    | the texture the ground shows, by its folder under `assets/textures/`  |
| `ground_texture_m`  | how far apart the ground's texture repeats                            |
| `spawn_m`           | where the player starts, on the map                                   |
| `spawn_bearing_deg` | which way the player faces there, as a compass bearing east of north  |

## Inputs checksum

`inputs_sha256` in `asset.toml` covers the asset's settings, every file in its `src/`, its kind's code, and the
exports it reads (a character reads every animation through each one's checksum and `.glb`). Changing any of them
marks the export out of date until it is exported again. An
asset exports only after the assets it reads are current, and `cargo export` on several folders exports each after
those it reads.

A kind's code is its folder under `src/` (`rig/` for the animation, character and equipment kinds, `texture/`,
`sound/`, `model/` or `world/`) and the shared code: `main.rs`,
`glb.rs`, `shapes.rs`, `random.rs`, `Cargo.toml`, the lock file and the toolchain. Each kind uses only its own
folder and the shared code, so editing the world's code never marks a character out of date, and editing the rig
never marks the world. Docs and `CONTRACTS` files are not inputs. `cargo test -p hakuba_export` checks that no kind
uses another's code.

The world also keeps one checksum per tile, in `tiles/checksums.toml`. It covers the code that writes tiles
(`world/` but the regions list, the shared code but `main.rs`, and the locked crate versions), the settings tiles
use, the heights in and around the tile, and the overlay triangles that reach into it, with the names of the
textures they show, and its scenery: where each model stands in it, by the model's name, its pieces of rail, and the
cables starting in it, with their ends. An export rewrites only the tiles whose checksum changed, so moving a road
rebuilds the tiles it crosses and nothing else. A tile names its textures and models rather than holding them, so
repainting a texture or reshaping a tree rebuilds no tile.
