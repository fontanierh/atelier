# Recovered Skate runtime

The skating implementation uses the recovered Skate 3 routines in
[2010-rust-rewrite-mashup/skate](https://github.com/chasmlol/2010-rust-rewrite-mashup/tree/7842b9e70e9aac22ed176b655dd63302618ee023/skate).
The reference commit is `7842b9e70e9aac22ed176b655dd63302618ee023`; its skate engine originated in
[SK8-ENGINE/skate-3-rust-engine](https://github.com/SK8-ENGINE/skate-3-rust-engine).
The recovered Rust Session is the only skating implementation. It does not claim original-console numerical parity.

## Complete session

`ThirdParty/skate-runtime` vendors the four original crates. Its headless `atelier-host` wraps the mashup's existing
`skate_host::bridge::Session`. The session owns the seven-body deck/truck/wheel assembly, physical rider skeleton,
constraints, contact solver, collision BVH, steering/push/pump/manual forces, trajectory and grind selection,
Flick-It recognizers, gameplay states, landing quality, bails, scoring, stock animation graphs/banks, procedural
pose adjustments, and the stock camera. These systems run together at the session's native fixed period. They are
not reimplemented as independent Unreal approximations.

`SkateRuntime.cpp` supplies Unreal terrain and controls, consumes the solved transforms, and retargets the
36-bone animation output onto the host character's bind pose. Bone lengths and skin scale stay authored;
leg IK fits the source foot targets without stretching the neck, torso or shoes. The game anim proxy evaluates that local pose
directly while the session is active. The deck, both trucks and four wheels
follow the native bones. Native camera position, orientation and FOV are available to the game camera, with its
normal mouse-look override. Keyboard/mouse controls remain available, including Space as a straight ollie.

The retained child process loads banks once per world. Pipes carry controller packets and poses, with one step
outstanding to prevent an accumulating input backlog. It runs without a network listener. Stowing suspends input;
remounting resets the native session; EndPlay closes it. A failed worker logs the reason and returns to walking.
Missing/corrupt executable or data reports an error and leaves the rider walking.

The game commits all 19 required data files in `assets/skate/runtime.zip` (8.8 MB compressed), with SHA-256
checksums and conversion provenance. `skate.runtime`, a dependency of the normal Unreal compile step, builds
Rust 1.97.1 and stages the executable plus verified data automatically. No disc or upstream checkout is needed.
The optional importer documents the original conversion. Build outputs stay in ignored Content/build folders.

The host game's `PopHeightScale=1.15` scales the original launch-height presets. `AirSpinScale=2.2` scales the
PhysicsAir/KnownAir speed target and BodySpin proportional/acceleration curves; derivative history and
constraint solving remain recovered code. Reconfiguration uses the stock values, so scales never compound.
Running mounts transfer the full planar velocity to board and skeleton. Activation generations prevent stale
poses or camera frames from a previous ride from being applied. C sends the native rear-diagonal slide gesture;
skid audio uses the angle between board heading and travel.

### Adapter boundaries

- Collision is a 100 m snapshot of nearby registered, pawn-blocking static mesh LOD0 triangles and registered rail
  polylines. It refreshes after travelling 60 m. This uses render triangles, not authored Chaos simple collision.
  Moving objects, skeletal obstacles, procedural meshes, collision material IDs and streamed-out terrain need
  additional adapters. CPU mesh buffers must be retained for packaged builds; editor builds are the validated path.
- The native session currently receives one default collision material. Named grass/sand drag is
  not yet mapped to native surface IDs. Rails use the source host's line-to-grind provider, not original disc collision metadata.
- Retargeting fits source reference-bone directions, scales the root/foot targets to the host's leg height, and
  preserves local bone lengths and skin scale. Two-bone leg IK keeps those targets within the avatar's reach;
  sole-height and deck/truck/wheel pivot offsets fit the host meshes. Unmapped fingers retain their bind pose.
  The physical skeleton keeps the source proportions; this retargeter changes the rendered avatar. Different
  proportions still require visual contact review, particularly grabs, low overhead obstacles and extreme poses.
- Unreal keeps walking, mounting, world streaming, audio assets and the HUD. Native score/trick/state drive the
  existing HUD, and mode transitions trigger the host sounds; original audio and UI are not reproduced.
- A first mount decodes the banks asynchronously (about 7–8 seconds measured locally). The process stays resident
  for subsequent rides. Static collision export currently runs on the game thread and can cause a mount/refresh hitch.

`tools/check_skate_runtime.py` tests both stances through 480 native ticks each: support, push, ollie, landing,
changing finite poses, teleport reset, deliberate bail/recovery and a sub-tick pipe acknowledgement. Additional
checks compare stock/tuned pop, both spin directions and powerslides in both stances, and running mounts.
The in-game runtime scenario validates push/flip/landing, steering direction, manual entry/exit, rails, vert,
bail/recovery, preserved bone lengths and head direction, keyboard-driven foot motion, stow/remount and goofy
push/ollie, flat-ground rotation, powerslide input and running mounts.

The unmodified vendored core's full test suite currently reports 604 passes and one failure on Mac ARM64:
`physics::board_world::broadphase_tests::predictive_contacts_and_retention_match_full_scan_for_every_primitive`.
The compared source and test are byte-identical to the pinned upstream. Its linear scan produces extra contacts
on distant triangles that the indexed scan rejects. This upstream discrepancy remains recorded rather than
changing the recovered contact kernel to force agreement.
