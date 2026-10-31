# Hakuba

Hakuba is a 3D game built on [Bevy](https://bevyengine.org), a Rust engine where the whole game is code. Bevy
loads the committed glTF files directly, so a checkout runs after a Rust compile. Hakuba runs as a Mac desktop app
and in the browser.

## How we work

- Every change is reviewed by hand.
- Every folder and file says what it is for, here, in its own README or in a header comment. Nothing is committed
  that the game or its exports do not use.
- Hakuba is all Rust and builds with plain `cargo` and `trunk`.
- Hakuba's code and assets stay in `games/hakuba`.

## Run

Install once per machine: [Rust](https://rustup.rs), [trunk](https://trunkrs.dev) (`cargo install --locked trunk`)
and Git LFS (`brew install git-lfs`, then `git lfs install`). Without Git LFS a clone holds small pointer files
instead of the models; `git lfs pull` fetches them afterwards.

Run commands from this folder. The first build compiles Bevy and takes a few minutes; later builds reuse unchanged
compiled dependencies.

```sh
trunk serve --release        # browser play, at http://127.0.0.1:8080
trunk serve                  # faster-to-build browser development
cargo run --release          # desktop play
cargo run                    # faster-to-build desktop development
```

The game opens on a menu: **World** enters the world, **Character viewer** shows each character and plays its clips.
Escape goes back to the menu.

The browser needs WebGPU and standard WebAssembly SIMD: a recent Chrome, Edge or other Chromium browser, or Safari 26.
Browser builds enable 128-bit SIMD for vector math; they do not enable relaxed SIMD or fast-math operations.

### Skateboard controls

Press **V** to get on or off the board. Off the board, the native rider carries it and can get back on; **F** requests
stowing and returns to walking after 0.2 seconds of stable ground. **W** pushes, **S** brakes, and **A/D** steer. Hold **Space** to crouch,
then release to pop. Drag with the left mouse button, or use the arrow keys, to move the trick stick. **Q/E** are
left/right grab triggers; off the board they drop or throw the carried board. **R** requests a transfer,
**B** bails, and **Enter** asks the native recovery state to get up. While riding, **Shift/C** move the left stick forward/back for drift and handplant input; **T** is the right
shoulder button. Off the board, **WASD** moves, **Shift** sprints and **Space** jumps. Hold **M + Down** to place a
marker, or **M + Up** to return after the native hold delay. A controller uses its two sticks and triggers directly;
Select gets on or off, and left shoulder plus left stick forward requests a transfer. Left shoulder plus D-pad
Down/Up places/returns to a marker. The on-screen readout shows the actual simulation state, speed, trick and score.
Skating waits for the world's full collision around the rider. Stowing the board needs the keyboard's F: a
controller has no stow binding yet. Some authored skating branches are unsupported; `crates/skate/README.md` lists them.

The simulation and board assets are exported with the rest of the game. See `crates/skate/README.md` and
`assets/simulations/skate-simulation/src/README.md` for the runtime and data provenance.

Test in the browser first: what works there almost always works on desktop, but not always the other way round.

## Layout

```text
games/hakuba/
  README.md                 this file
  PERFORMANCE.md            the frame-rate target, how to measure it and what costs what
  Cargo.toml                the Rust workspace, its shared dependencies and the game program
  .cargo/config.toml        the `cargo export` alias
  Cargo.lock                the exact dependency versions
  rust-toolchain.toml       the Rust version and the browser (wasm) target
  src/main.rs               the game program, what runs when the game opens: builds the app and adds the plugins
  crates/                   the game code, one crate per feature, each one Bevy plugin with its own README.md
    screens/                what every screen shares: which screen is showing, buttons and text
    menu/                   the menu the game opens on
    world/                  the world
    characters/             the playable characters: their models and clips
    glider/                 the paraglider, and how a character holds it
    player/                 walking, running, jumping and movement ownership
    skate/                  fixed-step board and rider simulation, input, solved pose and skating camera
    rendering/              shared rendering commands and 3D shadow views
    viewer/                 the character viewer
    audio/                  the sounds: footsteps, the moves, the paraglider's wind and the countryside
  schemas/                  data formats shared by the exporter and game, without Bevy dependencies
  index.html                the page the browser build runs in, with the canvas the game draws into
  Trunk.toml                export checks and what the browser build copies next to the game
  assets/                   everything the game loads, each next to its sources (assets/README.md)
  tools/export/             the asset exporter, run with `cargo export` (tools/README.md)
  .gitattributes            which files Git LFS stores
  .gitignore                the build folders
  CONTRACTS                 the rules every change keeps (crates/, assets/ and tools/export/ have their own)
```

## Conventions

Bevy and glTF use metres with Y up. A character's front faces +Z, the glTF convention. The world's map uses x east, y
north and z up; the export turns it into the game's frame as (x, z, -y), so north is -Z.
