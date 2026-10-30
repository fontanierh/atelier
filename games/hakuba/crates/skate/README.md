# Skating

`SkatePlugin` connects the fixed-step skating simulation to the player, world collision, character pose and camera.
The public `Session` API also runs deterministic raw-controller ticks without the plugin. `Controls` contains the
raw pad packet. `Pose` publishes the solved rider hierarchy, board bodies, velocity, physical state, authoritative
IK contacts and camera. `set_control_feel` changes stick dead zone/reach at the native converter, once per sample.
LB plus DPadDown places the native marker; holding LB plus DPadUp returns. `TRANSFER` is separate from LB.
Keyboard markers use M plus Down/Up. The HUD shows native placement/return eligibility and hold progress.
P or LB plus DPadLeft opens saved places. Arrow/DPad left/right selects; N/F5 or Y saves here; F2/X renames;
Delete/DPadDown twice deletes. Hold Enter/A to return through the same native marker path, after destination
collision is ready. Keyboard text names a place; on a controller left/right chooses a character, Y appends,
X erases and A saves. Escape/B closes. The bar consumes riding actions while it owns input.
`Settings.skate_places` keeps the current marker, named frames and selection in the normal desktop/browser
settings document. A stow, remount or reload restores the exact simulation basis, board mode and foot-forward
state without changing the rider; only a validated native held return may travel.

`CollisionRail` preserves each authored grind line's ID, points and closed topology on initial load and collision replacement.
`Session::telemetry` publishes retained scorer announcements and trick-start stance, rider-root spin and intentional
pump observations, with the displayed trick line. These observers neither change scoring nor move the bodies.

## Source

The recovered calculations and session were imported from the Rust reconstruction published by
`chasmlol/2010-rust-rewrite-mashup`, commit `7842b9e70e9aac22ed176b655dd63302618ee023` (`skate/`),
whose recorded engine origin is `SK8-ENGINE/skate-3-rust-engine`, commit `cb79689`. The import preserves
the latest recovered Rust session revision `1536531c6e03c72d3c232614141500419059ca2e`, including explicit
transfer input and vert departure assistance. Source is Apache-2.0; see `LICENSE-APACHE`.
This is a reconstruction, not a claim of verified original-console numerical parity. Simulation data has its own
provenance and rights in its asset folder; the source license does not license that data.

## Known source gaps

The motion factory reports 71 unsupported condition instances across six condition names. They cover skitching,
moving-object animation adjustment and two drop-in gates; they are also unsupported in the source reconstruction.
They remain explicit errors, not invented constant predicates. The air-secondary physical state (202) also lacks
an established state implementation and dispatch owner. Neither gap is evidence of a working gameplay path.
Ordinary riding, tricks, carry and local recovery have separate regression tests; those tests do not establish
support for every authored graph branch.

## Code

- `src/core/`: engine-independent arithmetic, board/rider solver, animation calculations, graphs, input, camera
  and scoring. Its subfolders group their corresponding calculations and unit tests.
- `src/data/`: validated simulation records and readers. `collections/package.rs` reads reflected settings;
  `animation_frames/package.rs` samples selected keys directly from compact component tracks in one shared archive.
- `src/resources.rs`, `src/resources/`: prepare the exported package once and share settings, motion and graphs through
  `PreparedResources`. Sessions reuse this handle; mounting does not decode the package again.
- `src/physics/`: complete session ownership and schedule, board and physical rider, contacts, air/ground/grind,
  animation feedback and transitions. `bridge.rs` is the public in-process session boundary.
- `src/graph_host/`: concrete action and motion graph operations. `graph_runtime.rs` compiles the graph bindings.
- `src/camera/`: camera graph, subjects, shot data and world queries.
- `src/input/`: pad mapping and gesture recognition. The game supplies raw input; no socket or subprocess runs.
- `src/session_marker/`: saved simulation marker state and placement validation.
- `src/places.rs`, `src/places_tests.rs`: named places, focused keyboard/controller bar, progress HUD and host input tests.
- `src/animation_pose/`, `src/skater_animation/`: evaluated full-body pose and retained animation state.
- The remaining root modules provide shared animation transforms, scoring, tuning, collision/grind adapters,
  crash diagnostics and host-world collision records.
The host supplies raw controller packets; the crate does not poll platform devices or load original-format files.

The runtime reads only the committed exported `.skatepack`, not archive-era assets or the local filesystem.
Its 60 Hz simulation clock is advanced by the host, independently of rendered frames. Current project-format
settings, graph, rig, metadata, gesture and clip words are retained, including separate animation-bank identity.
The 120 Hz flick history uses real timestamped stick observations when available. Ordinary frame-only
controller events fall back to one packet with double weight; the host never invents midpoint device samples.
