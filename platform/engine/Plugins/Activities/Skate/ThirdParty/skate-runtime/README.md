# Recovered skating runtime

Vendored from `skate/` in [chasmlol/2010-rust-rewrite-mashup](https://github.com/chasmlol/2010-rust-rewrite-mashup/tree/7842b9e70e9aac22ed176b655dd63302618ee023/skate),
commit `7842b9e70e9aac22ed176b655dd63302618ee023`. That workspace identifies its engine origin as
`SK8-ENGINE/skate-3-rust-engine` commit `cb79689`. The source license is [Apache-2.0](../skate-core-LICENSE).
IW4L copyright 2026 vladtrc; mashup and skating integration by chasmlol; recovered engine by SK8-ENGINE.

The four crates and workspace manifest retain the upstream source layout, including its tests and diagnostic
comments. Build through `atelier-host/Cargo.toml` with Rust 1.95 or newer. Its committed Cargo.lock pins external
dependencies; write Cargo outputs to the repository's ignored build directory, not this source tree.

Atelier changes to the imported crates:

- `skate-host/src/physics/bridge.rs`: expose the reference pose, difficulty/equipment/stance configuration, score
  snapshot, current manual balance and a diagnostic whole-assembly launch. Physics, animation graphs and frame scheduling remain in Session.
- `skate-host/src/scoring_runtime.rs`: read-only current trick accessor.

`atelier-host` is the new headless pipe adapter. It loads collision triangles and rail lines from a local JSON
snapshot, runs Session at its native period, and publishes solved board/rider matrices and the native camera.
Commands and poses use newline-delimited JSON on stdin/stdout; upstream diagnostics go to stderr. It opens no
network listener. EOF and quit terminate the process. The Unreal owner retains it between rides and closes it
when the world ends. Only one step packet is outstanding, bounding controller latency and pipe memory.

Animation banks, state graphs and the full settings database are installed locally by the game's importer.
They are generated data in ignored Content, not vendored source. Selected numeric tuning and gesture points
for the standalone C++ fallback are committed separately in `SkateNativeTuning.h`.
