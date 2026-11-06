# __Title__

A game on Atelier on the Bevy engine, started with `atelier new __game__ --engine bevy`: a lit, spinning cube on a
ground. It is a Rust program (`src/main.rs`) built by cargo.

```sh
atelier doctor __game__     # cargo and the workspace
atelier build __game__      # cargo build --release, under the build's admission and memory guard
atelier play __game__       # runs target/release/__game__
```

Add steps to `build.py` for your own generators (`Python`, `Blender`, more `Cargo` commands) and play profiles to
`game.toml`. `atelier live` and `atelier stream` are Unreal features: a Bevy game has neither.
