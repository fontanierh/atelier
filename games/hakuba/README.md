# Hakuba

Hakuba is Yorimichi rebuilt on [Bevy](https://bevyengine.org), a Rust engine where the whole game is code.
Yorimichi stays in `games/yorimichi` as the legacy Unreal version until everything has moved here; then it is
removed.

## Why Bevy

With Unreal, every test of a change means importing, cooking and packaging assets again, and switching to
another checkout means doing it all over. With many agents and people working on different branches and
machines at once, that loop became too slow. Bevy loads glTF files directly and the game is ordinary Rust, so
a checkout only needs a Rust compile to run.

Hakuba runs as a Mac desktop app and in the browser, so anyone can open a link and join.

## How we work

- Every change is reviewed by hand. Only clean architecture and tidy file layout get committed.
- Hakuba does not use the `atelier` command, its build steps or its admission setup yet. It is plain `cargo`.
  Once the setup works well, Atelier itself moves to it and drops Unreal.
- Nothing Hakuba-specific goes in `platform/` for now. Code moves there only when a second game, or Atelier
  itself, needs it.

## Plan

1. An empty game with an empty map.
2. The playable characters and their move sets: double jump, backflip, side dashes, sword fighting and the
   paraglider. First Nox as he is (this step), then the shared humanoid rig, then the animations.
3. The world: terrain, trees, cities, everything else, kept fast and optimized.
4. Skateboarding and multiplayer. Browser players join too, so networking uses web transports (WebSocket or
   WebTransport).
5. Atelier adopts this setup and drops the Unreal one.

## Run

Run commands from this folder; `rust-toolchain.toml` picks the Rust version and the browser target. The first
build compiles Bevy and takes a few minutes; later builds only compile Hakuba.

Models and images are stored in Git LFS. Install it once per machine before cloning, or the checkout holds small
pointer files instead of the real assets: `brew install git-lfs`, then `git lfs install`. In a clone made
without it, run `git lfs pull`.

```sh
trunk serve                  # browser, at http://127.0.0.1:8080 (install once: cargo install --locked trunk)
cargo run                    # desktop
```

Test in the browser by default: what runs there almost always runs on desktop too, while the reverse is not
true. The browser build loads `index.html`, which holds the canvas the game draws into. `Trunk.toml` copies
`assets/` into the web build without the `src/` folders and `asset.toml` records.

## Layout

```text
games/hakuba/
  Cargo.toml                Rust workspace and the game program
  rust-toolchain.toml       Rust version and the browser (wasm) target
  index.html                the page the browser build runs in
  Trunk.toml                what the browser build copies next to the game
  src/main.rs               builds the app and adds the plugins, nothing else
  crates/                   game code: one crate per feature, each one Bevy plugin
    world/                  the map
    characters/             the playable characters
    (later) player/ moves/ combat/ skate/ net/
  tools/                    Python shared by every exporter
    hakuba_tools/           export runner and glTF helpers; (later) Blender runner, mesh, texture and rig helpers
  assets/                   everything the game loads, plus how each piece is made
```

### Assets

Every asset is one folder, named in kebab case. Its main file has the folder's name. The top of the folder is
what the game loads; `src/` is how it is made and is never loaded or shipped.

```text
<asset-name>/
  asset.toml                what it is, its outputs, how its sources were made, checksum of the inputs at last export
  <asset-name>.glb          what the game loads
  src/
    export.py               the script that writes the .glb (generated assets)
    params.toml             the numbers the script reads
    <asset-name>.blend      a hand-made source (hand-made assets)
```

The whole tree:

```text
assets/
  characters/
    <character>/            mesh bound to the humanoid rig, plus clips only this character uses
      character.toml        per-character tweaks: hips height, limits, correction layers, clip overrides
      moves.toml            move tuning (jump height, dash speed); Bevy reloads it while the game runs
  animations/
    humanoid/               the shared rig and every clip on it, retargeted onto it once
      rig.glb  locomotion.glb  traversal.glb  glider.glb  sword.glb
      src/clips/            one source per clip
  world/
    common/                 usable in any region
      trees/<tree>/  rocks/<rock>/  props/<prop>/  materials/<material>/
    regions/
      <region>/
        region.toml         bounds, spawn points, the common assets it uses
        terrain/            chunk-<x>-<z>.glb, made by src/export.py from src/heightmap.png
        layout/             placements.json (where every tree, rock and house stands), made by src/place.py
        buildings/<building>/  props/<prop>/  audio/
  audio/
    music/  footsteps/  combat/
  ui/
    fonts/  icons/
```

Rules:

- An asset's script, sources and output live in the same folder, so they move, change and get deleted together.
- An asset starts in its region. When a second region needs it, its folder moves to `world/common/`.
- A region uses only its own folder and `world/common/`, never another region's.
- There is no donor character. Every clip is authored or retargeted once onto the humanoid rig, and every
  character is bound to that rig, keeping its own proportions. Clips rotate bones; only the hips also move, scaled
  to each character's height. Extra bones such as hair hang under the rig's bones.
- Optimization (mesh simplification, LODs, compressed textures) happens during export, so `assets/` always holds
  the final files.
- Binaries (`.glb`, `.blend`, `.ktx2`, `.png`) are stored in Git LFS (`.gitattributes`). The repository's
  pre-push hook uploads them.
- Concept images, reference videos, old revisions and captures stay out of git, in the archive. `asset.toml`
  records what a source was made from.

### Exporting

Exports are not part of the build. Exported files are committed next to their sources, unlike the repository's
general rule that generated files go in `build/`. This is on purpose: every checkout runs the game straight
away, without exporting anything. The Python is something you run before committing:

1. Change an asset's script, parameters or source, for example
   `assets/world/common/trees/pine-a/src/params.toml`.
2. Export that folder: `uv run --project tools export assets/world/common/trees/pine-a`. The runner reads
   `asset.toml`, runs `src/export.py`, checks that it wrote every listed output and records the checksum of
   `src/` and `tools/` in `asset.toml`. Scripts that need Blender will run it headless.
3. Commit the sources and the `.glb` together.

`uv run --project tools export --check assets` compares each recorded checksum with the current inputs and lists
out-of-date exports.

## Conventions

Bevy uses metres with Y up and -Z forward. Sources stay in metres with Z up, as in
[the units guide](../../platform/conventions/units.md); the glTF export converts them to Y up, and nothing else
flips axes.
