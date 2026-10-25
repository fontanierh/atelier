# Tools

The asset exporter (`../assets/README.md` describes an asset folder). Run it from `games/hakuba`:

```sh
cargo export assets/characters/nox     # export one asset folder
cargo export --check assets            # list the exports whose inputs changed
```

`cargo export` is an alias in `../.cargo/config.toml` for running the `export` crate.

```text
tools/
  export/
    Cargo.toml              the crate and its dependencies
    src/
      main.rs               the `export` command: reads asset.toml, runs its kind's exporter, records its inputs
      rig.rs                the rig and the `Skeleton` trait
      pose.rs               poses: each rig bone's world rotation and position
      pose_edit.rs          turning bones, moving the body and bending legs, shared by the retarget and animations
      retarget.rs           moving a clip from one skeleton onto another
      animation.rs          the `animation` kind
      animations.rs         every animation, each from its asset folder
      character.rs          the `character` kind and the `Character` trait
      characters.rs         every character
      world.rs              the `world` kind
      glb.rs                reading, editing and writing .glb files
```

## The rig

Every animation is made once on the rig, a 52-bone humanoid skeleton (`RIG` in `rig.rs`): the pelvis, spine,
neck and head, and per side the clavicle, arm, hand with five three-bone digits, leg, foot and toe. Its rest pose
is a T-pose facing +Z with the character's left at +X, the pelvis one hip height above the ground, and every rest
rotation the identity. Clips on the rig store each bone's world turn, and the pelvis's position in hip heights, so
they fit any skeleton of any size.

A skeleton implements `Skeleton`, naming its node for each rig bone. The spine's middle and the fingers are
optional; a skeleton without them gets them from its neighbours.

## Characters

A character is a type that implements `Character`: `Skeleton`, plus one trait per animation (`Idle`, defined in
`assets/animations/idle/src/idle.rs`). Each animation trait's methods are the character's changes to that animation,
with defaults that change nothing. The character's file, `src/<name>.rs` in its asset folder, implements them, and
`characters.rs` includes it in the `Name` enum. If a character lacks one, the exporter fails to compile.

## Kinds

`asset.toml` is read into the `Asset` enum in `main.rs`: `kind` picks the variant, and the other keys are that
kind's settings. A missing, misspelled or unknown setting fails the export. Each kind is one module with a
`Settings` struct and an `export` function that writes the folder's `.glb`.

**`animation`** retargets a clip onto the rig and writes the rig playing it, named after the folder. Its
`src/<name>.rs` implements `Skeleton` for the clip's skeleton and defines the trait a character implements to
change the animation; `animations.rs` includes it in the `Name` enum.

| Setting     | Meaning                                         |
|-------------|-------------------------------------------------|
| `animation` | which animation this is                         |
| `source`    | the file holding the clip, relative to the folder |
| `clip`      | the clip's name in that file                    |

**`character`** exports a character's model: scaled to its height, textures resized, morph targets removed, and
every animation fitted to it with the character's changes. Its rig bones are renamed to the rig's names.

| Setting        | Meaning                                     |
|----------------|---------------------------------------------|
| `character`    | which character this is                     |
| `source`       | the model, relative to the asset folder     |
| `height_m`     | how tall the character stands in the game   |
| `texture_size` | the largest side of any texture, in pixels  |

**`world`** builds the ground from a heightmap and the road along the course in `src/layout.rs`, and cuts both
into square tiles under `tiles/`. Each tile is written in full detail and in middle detail, for seeing from afar.
The road lies a few centimetres above the ground triangles under it; the export fails if it comes closer anywhere.
`<folder name>.glb` holds a node per tile, at its centre, and the spawn.

| Setting             | Meaning                                                           |
|---------------------|-------------------------------------------------------------------|
| `heightmap`         | the ground's heights, relative to the folder                       |
| `heightmap_samples` | how many heights each row and column has                          |
| `heightmap_step_m`  | the distance between neighbouring heights                         |
| `tile_steps`        | how many heights apart tile edges are                             |
| `tiles`             | the first and last tile exported, each as `[column, row]`         |

## Inputs checksum

`inputs_sha256` in `asset.toml` covers the asset's settings, every file in its `src/`, every file in
`tools/export/`, and the exports it reads (a character reads every animation). Changing any of them marks the
export out of date until it is exported again. A character exports only after the animations it reads are current.
