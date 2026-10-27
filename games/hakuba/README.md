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

Run commands from this folder. The first build compiles Bevy and takes a few minutes; after that, builds only
compile Hakuba.

```sh
trunk serve                  # browser, at http://127.0.0.1:8080
cargo run                    # desktop
```

The game opens on a menu: **World** enters the world, **Character viewer** shows each character and plays its clips.
Escape goes back to the menu.

The browser needs WebGPU: a recent Chrome, Edge or other Chromium browser, or Safari 26.

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
    player/                 the character the player controls in the world
    rendering/              shared rendering commands and 3D shadow views
    viewer/                 the character viewer
    audio/                  the sounds: footsteps, the moves, the paraglider's wind and the countryside
  index.html                the page the browser build runs in, with the canvas the game draws into
  Trunk.toml                what the browser build copies next to the game
  assets/                   everything the game loads, each next to its sources (assets/README.md)
  tools/export/             the asset exporter, run with `cargo export` (tools/README.md)
  .gitattributes            which files Git LFS stores
  .gitignore                the build folders
  CONTRACTS                 the rules every change keeps (crates/, assets/ and tools/export/ have their own)
```

## Conventions

Bevy and glTF use metres with Y up. A character's front faces +Z, the glTF convention. The world's map uses x east, y
north and z up; the export turns it into the game's frame as (x, z, -y), so north is -Z.
