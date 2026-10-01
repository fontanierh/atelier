# Native Skate runtime

The skating implementation uses the recovered Skate 3 routines in
[2010-rust-rewrite-mashup/skate](https://github.com/chasmlol/2010-rust-rewrite-mashup/tree/7842b9e70e9aac22ed176b655dd63302618ee023/skate).
The reference commit is `7842b9e70e9aac22ed176b655dd63302618ee023`; its skate engine originated in
[SK8-ENGINE/skate-3-rust-engine](https://github.com/SK8-ENGINE/skate-3-rust-engine).
The native C++ runtime preserves that recovered implementation; it does not claim original-console numerical parity.
Reference source is restored from pinned Git history into ignored build output only for independent differential proofs.

## Complete session

`Native/GameplaySession.*` owns one `GameplayRuntime`, raw controller histories, markers, host elapsed time
and fixed-tick scheduling. The runtime owns the seven-body deck/truck/wheel assembly, physical rider skeleton,
constraints, contact solver, collision BVH, steering/push/pump/manual forces, trajectory and grind selection,
Flick-It recognizers, gameplay states, landing quality, bails, scoring, authored animation graphs/banks,
procedural pose adjustments and camera. These systems run together at the source fixed period.

`SkateRuntime.cpp` supplies Unreal terrain and controls, consumes the solved transforms, and retargets the
36-bone animation output onto the host character's bind pose. Bone lengths and skin scale stay authored;
leg IK fits the source foot targets without stretching the neck, torso or shoes. The game anim proxy evaluates that local pose
directly while the session is active. The deck, both trucks and four wheels
follow the native bones. Native camera position, orientation and FOV are available to the game camera, with its
normal mouse-look override. Keyboard/mouse controls remain available, including Space as a straight ollie.

The native adapter retains one in-process Session and loaded banks per world. Stowing suspends input,
remounting resets the same physical lifecycle, and shutdown releases the owner. Activation generations prevent
stale asynchronous world/pose responses from moving a newly mounted rider. Missing/corrupt native data logs
its diagnostic and leaves the player walking. No child executable, pipe protocol or alternate solver runs in game.

The project tracks the complete native bundle in `Data/SkateNative`: settings, skeletons, gesture sets,
graphs, animation samples/metadata and camera shots. The host descriptor pins its package manifest, native
formats, source identity, checksums and counts. `skate.runtime` validates this immutable bundle in place before
Unreal compilation. Missing/corrupt data is rejected without repair or source-format conversion. Standard
filesystem readers require loose NonUFS staging (`DirectoriesToAlwaysStageAsNonUFS`, the packaging UI's
Additional Non-Asset Directories to Copy); packaging the data solely inside a Pak is insufficient.

The accepted `46513a6` full-Session proof observes actual controls, solver, state, pose, score, camera, markers
and error prefixes. Latest-main `1536531` transfer/VertAssist behavior and the native Unreal adapter have their
own pending acceptance checks. See [CXX_PORT.md](CXX_PORT.md) for the current proof evidence and boundaries.
Original-source/ZIP extraction, Rust compilation and one-time conversion are test-only migration tools; the
normal build and offline native CLI builder do not depend on them.

The host game's `PopHeightScale=1.15` scales the original launch-height presets. `AirSpinScale=1.6` scales the
PhysicsAir/KnownAir speed target and BodySpin proportional/acceleration curves; derivative history and
constraint solving remain recovered code. `PushPowerScale=1.45` and `PushSpeedScale=1.15` scale the native
animation-timed propulsion and push speed limit. Reconfiguration uses the stock values, so scales never compound.
Running mounts transfer the full planar velocity to board and skeleton. Activation generations prevent stale
poses or camera frames from a previous ride from being applied. C sends the native rear-diagonal slide gesture;
skid audio uses the angle between board heading and travel.

Near-vertical departures canonicalize the contact normal to the wall plane before calling the native
trajectory selector. This removes the small floor-normal contribution that otherwise redirects a straight-up
air across the coping onto the deck. Banks, descending motion and explicit forward-transfer input retain their
original normals. `VertAssist` widens this band to lips short of vertical (down to about 50° at 1) and removes
the speed such a lip throws towards the deck. The independent latest-main departure-kernel and full Session/quarter-pipe checks are pending acceptance;
the original Rust unit tests remain historical reference evidence.

The transfer intent (the selector's directional input) comes from the host's transfer button, bit 0x0800 of the
step packet, instead of the right trigger (action 71), which still grabs. The bit is masked before the pad sample.

### Adapter boundaries

- Collision is a snapshot of nearby registered, pawn-blocking static meshes and registered rail polylines,
  up to 100 m around the rider and shrunk to 60, 35 or 20 m when the area exceeds the native builder's 500,000-triangle
  limit. Meshes whose collision is their surface (complex as simple) contribute their collision LOD triangles; the
  others contribute their authored simple shapes (boxes, capsules, spheres and convex hulls). Faces thinner than
  the native builder can normalize are dropped. The snapshot refreshes when the rider leaves its inner 60% region: the
  game thread gathers the triangles, a background task builds the native world, and the same Session installs
  the completed snapshot between steps. Inside a tagged skate park the snapshot stays anchored at the park
  origin, covering the entire pier without rebuilding collision between lines.
  Moving objects, skeletal obstacles, procedural meshes, collision material IDs and streamed-out terrain need
  additional adapters. The park importer retains CPU buffers; other world mesh importers still need the same treatment before
  packaged builds are supported. Editor builds are the validated path.
- The native session currently receives one default collision material. Named grass/sand drag is
  not yet mapped to native surface IDs. Rails use the source host's line-to-grind provider, not original disc collision metadata.
- Retargeting fits source reference-bone directions, scales the root/foot targets to the host's leg height, and
  preserves local bone lengths and skin scale. Two-bone leg IK keeps those targets within the avatar's reach;
  sole-height and deck/truck/wheel pivot offsets fit the host meshes. Unmapped fingers retain their bind pose.
  The physical skeleton keeps the source proportions; this retargeter changes the rendered avatar.
  During bails, the actual skinned surface supplies supporting-ground samples for a whole-pose visual lift,
  keeping the larger head and clothing out of the floor without changing the native bodies. Rider LODs retain
  CPU vertices for this pass. Different proportions still require visual review for grabs and low overhead obstacles.
- Unreal keeps walking, mounting, world streaming, audio assets and the HUD. Native score/trick/state drive the
  existing HUD, and mode transitions trigger the host sounds; original audio and UI are not reproduced.
- The native owner may preload banks and nearby collision before mounting and retain them across rides.
  Preload timing, engine presentation, packaged loose-data loading and performance require native integration
  validation; measurements of the removed worker are not native performance evidence.

`tools/check_skate_runtime.py` tests both stances through 480 native ticks each: support, push, ollie, landing,
changing finite poses, teleport reset, deliberate bail/recovery and a sub-tick acknowledgement in the offline native QA transport. Additional
checks compare stock/tuned pop and push, both spin directions and powerslides in both stances, and running mounts.
`check_skatepark_runtime.py` exercises the exported park collision: bowl and quarter re-entry, opposite mini-ramp
airs, an ollie through coping, a downhill roll-in, stair handrail grinds, and a timed pump/coast comparison.
The in-game runtime scenario validates push/flip/landing, steering direction, manual entry/exit, rails, vert,
bail/recovery, preserved bone lengths and head direction, keyboard-driven foot motion, stow/remount and goofy
push/ollie, flat-ground rotation, powerslide input and running mounts.

The pinned historical core's test suite reported 604 passes and one failure on Mac ARM64:
`physics::board_world::broadphase_tests::predictive_contacts_and_retention_match_full_scan_for_every_primitive`.
Historical source/test identities are recorded in the reference provenance; these are not native runtime tests. Its linear scan produces extra contacts
on distant triangles that the indexed scan rejects. This upstream discrepancy remains recorded rather than
changing the recovered contact kernel to force agreement.
