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
      rig/                  the rig, and the `animation` and `character` kinds made on it
        mod.rs              the rig and the `Skeleton` trait
        pose.rs             poses: each rig bone's world rotation and position
        pose_edit.rs        turning bones, moving the body and bending legs, shared by the retarget and animations
        retarget.rs         moving a clip from one skeleton onto another
        animation.rs        the `animation` kind
        animations.rs       every animation, and the `Animation` trait each implements
        character.rs        the `character` kind
        characters.rs       every character, and the `Character` trait each implements
      texture/
        mod.rs              the `texture` kind
      world/                the `world` kind
        mod.rs              the settings, and cutting the world into tiles
        regions.rs          every region, and the `Region` trait: what a region adds to the world
        checksums.rs        what each tile is made from, so an export rebuilds only the tiles that changed
        ground.rs           the ground's heights, read from its pages
        overlay.rs          flat shapes laid over the ground, such as roads
        ribbon.rs           strips of even width along a curve, for regions to lay as overlays
        surface.rs          finding what lies under a point of a mesh, and cutting shapes along its triangles
```

## The rig

Every animation is made once on the rig, a 52-bone humanoid skeleton (`RIG` in `rig/mod.rs`): the pelvis, spine,
neck and head, and per side the clavicle, arm, hand with five three-bone digits, leg, foot and toe. Its rest pose
is a T-pose facing +Z with the character's left at +X, the pelvis one hip height above the ground, and every rest
rotation the identity. Clips on the rig store each bone's world turn, and the pelvis's position in hip heights, so
they fit any skeleton of any size.

A skeleton implements `Skeleton`, naming its node for each rig bone. The spine's middle and the fingers are
optional; a skeleton without them gets them from its neighbours.

## Characters

A character's file, `src/<name>.rs` in its asset folder, implements `Character`: its name and which of its bones
plays each rig bone (`Skeleton`). `characters.rs` lists it in `CHARACTERS`. Its changes to the animations are numbers in its
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

| Setting  | Meaning                                           |
|----------|---------------------------------------------------|
| `source` | the file holding the clip, relative to the folder |
| `clip`   | the clip's name in that file                      |

**`character`** exports a character's model: scaled to its height, textures resized, morph targets removed, and
every animation fitted to it with the character's changes. Its rig bones are renamed to the rig's names.

| Setting        | Meaning                                     |
|----------------|---------------------------------------------|
| `source`       | the model, relative to the asset folder     |
| `height_m`     | how tall the character stands in the game   |
| `texture_size` | the largest side of any texture, in pixels  |
| `animations`   | its changes to each animation, by name      |

**`texture`** writes an image as `<folder name>.ktx2`, with every mipmap level so it draws smoothly near and far.
Each level averages the one above it in linear light, each colour weighted by its opacity, and is stored as 8-bit
sRGB, compressed with zstd. In an image with clear parts, such as leaves, every level keeps at least the share of
pixels opaque enough to show, so leaves stay as full far away as near. Its sides must be powers of two.

| Setting  | Meaning                                       |
|----------|-----------------------------------------------|
| `source` | the image, PNG or JPEG, relative to the folder |

**`world`** builds the ground from the height pages in `src/ground/`, lays over it what each region adds, and cuts
them into square tiles under `tiles/`. Each region's `src/regions/<region>/layout.rs` implements `Region`, and
`world/regions.rs` lists it. Each tile is written in full detail and in middle detail, for seeing from afar. The
ground and each overlay show a texture asset, named by its folder: a tile points at the texture's `.ktx2` and never
holds it, and the export fails if no such texture asset exists. An
overlay lies a few centimetres above the ground triangles under it; the export fails if it comes closer anywhere. `<folder name>.glb` holds a node per tile, at its centre, and the spawn.

| Setting             | Meaning                                                               |
|---------------------|-----------------------------------------------------------------------|
| `ground`            | the folder of the ground's height pages, relative to the asset folder |
| `south_west_m`      | the world's south-west corner on the map, where pages and tiles start |
| `ground_step_m`     | the distance between neighbouring heights                             |
| `page_steps`        | how many heights apart page edges are                                 |
| `tile_steps`        | how many heights apart tile edges are                                 |
| `tiles`             | the first and last tile exported, each as `[column, row]`             |
| `ground_texture`    | the texture the ground shows, by its folder under `assets/textures/`  |
| `ground_texture_m`  | how far apart the ground's texture repeats                            |
| `spawn_m`           | where the player starts, on the map                                   |
| `spawn_bearing_deg` | which way the player faces there, as a compass bearing east of north  |

## Inputs checksum

`inputs_sha256` in `asset.toml` covers the asset's settings, every file in its `src/`, its kind's code, and the
exports it reads (a character reads every animation, through each one's checksum and `.glb`). Changing any of them
marks the export out of date until it is exported again. A character exports only after the animations it reads
are current, and `cargo export` on several folders exports each after those it reads.

A kind's code is its folder under `src/` (`rig/`, `texture/` or `world/`) and the shared code: `main.rs`, `glb.rs`,
`Cargo.toml`, the lock file and the toolchain. Each kind uses only its own folder and the shared code, so editing
the world's code never marks a character out of date, and editing the rig never marks the world. Docs and
`CONTRACTS` files are not inputs. `cargo test -p hakuba_export` checks that no kind uses another's code.

The world also keeps one checksum per tile, in `tiles/checksums.toml`. It covers the code that writes tiles
(`world/` but the regions list, `glb.rs`, and the locked crate versions), the settings tiles use, the heights in and
around the tile, and the overlay triangles that reach into it, with the names of the textures they show. An export
rewrites only the tiles whose checksum changed, so moving a road rebuilds the tiles it crosses and nothing else.
A tile names its textures rather than holding them, so repainting a texture rebuilds no tile.
