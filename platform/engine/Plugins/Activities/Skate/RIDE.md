# Ride

Ride is the Unreal-native skating backend (`skate.Backend Ride`, `USkateSettings::Backend`). Its sources are in
`Source/AtelierSkate/Private/Ride/`.

## Board

The board is rigid and steps at 60 Hz (`RideSession.cpp`; the numbers are in `RideTuning.h`).

- **Ground.** A tick moves in steps of at most `GroundStep` (15 cm). Each step probes the ground under both axles with
  a wheel-sized sphere, from `StepUp` (6 cm) above to `StickGap` plus a share of the step below, and the deck takes
  the line between the two contacts. Ground that falls away further is a take-off.
- **Crests.** The curvature along the travel is the turn of the ground's normal over at least `CrestWindow` (50 cm) of
  travel, so a transition built of flat facets reads as the curve it approximates. A convex crest launches the board
  when following it would take more than `LaunchFactor` (1.5) g once the rider's legs have absorbed a drop of
  `CrestReach` (6 cm) over that window. A crest rounder than about 2 m radius never launches; a sharp 25 degree lip
  does from about 5.8 m/s.
- **Curbs and walls.** The board stops at a face too steep to roll onto (its normal more than 60 degrees from the
  deck's). As in the native runtime (`Wipeout_GroundXZAcceleration`, `Wipeout_GroundYAcceleration`), the closing
  velocity along the face's normal throws the rider beyond `CurbBail` (7.1 m/s) across the deck or `CurbImpact`
  (60 m/s) along its normal. A concave transition turns with the board, so its closing velocity stays small at any
  speed and it never throws the rider. A wheel that starts inside the ground looks again from higher: a face rising
  against the travel (a tight transition, a bank's foot) is followed, a raised step level with the deck is not. A
  wall at deck height throws the rider beyond `WallBailSpeed` (8 m/s) into it; slower, the board glances off it,
  turned along it.
- **Grinds.** A line locks on when the board comes down within `GrindCapture` (30 cm) of it in plan and at most
  `GrindAbove` (40 cm) over it, crossing it at no more than `GrindCross` (65 degrees; the native runtime locks up to
  about 61), and keeps the speed along it. The board then closes onto the line at its approach speed, at least
  `GrindLockSpeed` (4 m/s), rather than jumping there: the native board touches the line before it locks, and its
  step at a lock is at most its speed's plus 0.7 cm. At a line's end the grind carries on, at its speed, into a line
  whose end meets it within `GrindJoin` (10 cm) and turns less than `GrindCorner` (45 degrees). At a sharper corner,
  within a line or between two, the board flies off the way it was going.

## Rider

The rider's pose is the native clips played by an Unreal animation graph. The session's state machine
(`RideSession.cpp`) picks the clips and their times each frame; `FRideAnimator` (`RideAnimator.*`) turns that choice
into the graph's inputs, runs the graph and places the pose on the board.

- **Graph.** `USkateRideAnimInstance` (`RideAnimInstance.*`) is a C++ anim instance whose proxy owns its nodes, like
  the game's own anim instances: four `FAnimNode_SequenceEvaluator_Standalone` (explicit time: the session's clock
  drives every clip), then `FAnimNode_MultiWayBlend` (normalised weights), `FAnimNode_Mirror_Standalone`
  (`MDT_SkateRider`) and `FAnimNode_RideInertialization` at the root. It runs on a hidden `SK_SkateRider` mesh (the
  native rig) that the animator adds to the rider at the mount. The mesh never moves, so the graph only sees the
  clips' own root space; it stays at LOD 1, and the animator ticks and evaluates it after each session step
  (`TickAnimation`, `RefreshBoneTransforms`), so the pose and the physics are always in step. The clips' curves
  (`PUSH_CONTACT` and the rest) are read back from the instance.
- **Inertialization.** A change of clip cross-fades by inertialization: the pose carries on from the last frames with
  their velocity and settles onto the new clip on a quintic curve per bone (Bollo, "Inertialization", GDC 2018).
  `FAnimNode_RideInertialization` (`Public/AnimNode_RideInertialization.h`) does it. The engine's
  `FAnimNode_Inertialization` and `FAnimNode_DeadBlending` report to Animation Insights outside shipping builds
  through Anim Blueprint node data, which a graph built in C++ does not have: an editor-build game asserts in
  `GetNodeIndex`. Our node takes requests the standard way, through `IInertializationRequester` graph messages (the
  mirror node's stance change, blend nodes) with blend profiles as per-bone time factors, so any C++ graph can use it;
  the transitions' `FAnimNode_SkateRider` does. With `MaxSpeed` set, a request between poses far apart lasts longer
  than asked: at least 1.875 times the largest component-space gap over `MaxSpeed` (the quintic's fastest point), at
  most `MaxDuration` (0.25 s); `SpeedRoot` limits the bones counted. The rider's mesh caps the body (`HIPS` and below)
  at 1000 cm/s, a little under the trick clips' own fastest limbs (1100 to 1300 cm/s).
- **Stance.** The clips are authored goofy. A regular rider plays them mirrored (`bMirror = !bGoofy`), and a stance
  change inertializes over 0.2 s. `MDT_SkateRider` mirrors across Unreal's Y axis and lists every bone the native rig
  mirrors, the centre bones onto themselves: Unreal leaves a bone without a row unmirrored.
- **Placement.** The riding clips' `TRAJECTORY` is the deck's pivot at rest, 8.9 cm above the ground, which is the
  session's root. The animator puts the clips' root space on the session's deck (`Lock` 0), or moves the pose so that
  the clip's board lies exactly on the deck (`Lock` 1, for clips whose board is elsewhere, as in the transitions). On
  the ground, a board that the clip tilts (a pop's tail, a manual, a 5-0) keeps its lowest wheel or tip on the ground:
  the pose rises by what would sink (`lift`), and the rise decays at 150 cm/s once the board is in the air.
- **Board.** The clip's `SKATEBOARD_ROOT` is the board: flips, shove-its and the pop's tilt come from the clips, and
  the session's deck adds only a powerslide's yaw. The trucks and wheels are placed from the deck with the truck's
  lean and the wheels' spin. Without the rig in the build, the board rides alone with a procedural flip.

| Session motion | Clips |
|---|---|
| Rolling | `R_IDLE_HCOM_000`, `R_IDLE_HCOM_P100` or `_N100` (leaning toe or heel side), `R_IDLE_LCOM_000` (crouched), blended by lean and crouch |
| Push | `R_PUSHLSP_HSTR_N_0_INTO` for the first push of a run (from 0.231 s), then per push the kick (`R_PUSH*_HSTR_N_0_CYC1`) and the recovery (`_CYC2`), slow (`LSP`) blended toward fast (`HSP`) by speed and stretched over the session's push phases; `R_PUSH_H_N_OUT_FRONT` after |
| Brake | `R_BRAKE_N_N_0_INTO`, `_CYC`, `_OUT`; stopped, `R_STAND_FROMLSBRAKE_N_0_TR`, then `R_STAND_IDLE2_N_0_CYC` and `_OUT` |
| Powerslide | `R_SLIDE_FS_LSP_*` (toes leading) or `R_SLIDE_BS_LSP_*`: into, cycle, out |
| Manual | `M_IDLE_N_0_CYC`; nose manual `M_NOSEIDLE_N_0_INTO`, `_CYC`, `_OUT` |
| Loading a flick | `R_ANTIC_OLLIE_N_0_INTO` or `R_ANTIC_NOLLIE_N_0_INTO`, held at its end |
| Pop | the trick's ground clip (`<TRICK>_HIGH_G`), scaled to the pop delay |
| Flip in the air | the trick's air clip (`<TRICK>_HIGH_A`) straight on from the pop, then its follow-through (`T_<TRICK>_*`) |
| Air | `IA_IDLE_N_N_0_CYC`; within 0.217 s of the landing, `IA_IDLE_LO_N_0_CYC` with `IA_EXTEND_LO_N_0_CYC` |
| Grab | once the board is caught: `GR_*_INTO`, the hold (`GR_GRAB_N_FS_0_CYC`, `GR_MELON_N_BS_0_CYC`, `GR_DSMNT_CHRIST_BS_0_CYC`, `1FT_AIR_GRAB_N_BSL_0_CYC`, `GR_TKNEE_N_FS_0_CYC`), `GR_*_OUT` when let go |
| Landing | `L_HCOM_LIMP_3` blended toward `L_HCOM_HIMP_3` by the impact (250 to 750 cm/s), `L_LCOM_3` after a grab, `L_SKETCH_FS_HCOM_LIMP` by how sketchy, over 1 s |
| Grind | `G_5050_*`, `G_50_*`, `G_NGRIND_*`, `G_CROOKS_*`, `G_BSLIDE_*`, `G_LIPSLIDE_*`, frontside or backside, cycling |
| Bail | the last pose, held; the physical rider takes over |

- **Timing from the clips.** The pop delay is the length of the trick's ground clip. The catch is where the clip's
  board stops turning: the first key after which it stays within 25° of its final attitude (a half turn about its up
  axis counts as none), read over the air clip and the first 0.4 s of its follow-through. The push's lead-in, kick and
  recovery last as long as the push clips, blended by speed. The session's trick timing (the flick window, the catch,
  the scoring) uses these, so the clip's board and the physics agree.
- **Cross-fades.** Most switches blend over 0.05 to 0.18 s; the landing back to rolling takes 0.25 s and a get-up
  0.4 s. The pop's ground clip and the trick's air clip follow on with a cut, as they were cut to. A quick flick pops
  from the anticipation's first frames, 50 to 65 cm (head, hands) from every pop clip's first pose: the pop's 0.05 s
  would sweep the head across that at up to 1900 cm/s, so the speed cap stretches it to about 0.1 s (a full
  anticipation, 7 to 12 cm away, keeps 0.05 s). A blend whose clip shares move by more than 0.2 in a 60 Hz tick (the
  lean when a wall hit stops the turn; steering moves it at most 0.11 a tick) inertializes like a clip change. A clip
  that ends with the board turned end for end (a hardflip or an inward heelflip caught backwards) hands the board to
  the next clip at once (a blend profile with the board at time factor 0) while the body blends: the board looks the
  same either way round, and a blend would spin it back in the air.
- **For the physical rider.** The pose is the motor target (below), so it has to be continuous. `FRideBodyPose`
  carries what the controller needs besides it: the motion and its time, the landing's impact and age, the grind and
  manual state and the bail's start.
- **Pose health.** The Ride state line (`USkateComponent::GetRetailState`, `atelier live state`) has `clip=` (the
  clip with the most weight), `ct=` (its time, s), `lock=`, `lift=` (cm), `step=` (the fastest body bone in the
  root's space, cm/s), `stepbone=` (that bone), `dt=` (the frame time it is measured over, ms),
  `feet=` (the toes' heights over the deck, cm), `feetoff=` (feet outside the deck's 42 × 14 cm outline, or more than
  16 cm above or 4 cm below it), `nan=` and `anim=` (the animator's time this frame, ms). The game's QA reads it.
- **Cost.** Riding two large skatepark levels on an M-series Mac with no other heavy job running (load average about
  4), with `skate.RidePhysical` 0 then 1. The frame stays at 60 fps: p50 16.66 to 16.67 ms both ways, p99 17.07 to
  17.29 ms then 17.08 to 17.30 ms. The animator (graph update, evaluation and placement) takes 0.058 to 0.060 ms then
  0.059 to 0.063 ms p50 per frame, and 0.104 to 0.107 ms then 0.112 to 0.133 ms p99. The session's step takes 0.024
  to 0.034 ms then 0.026 to 0.037 ms mean per 60 Hz tick, and at most 0.068 ms then 0.072 ms. With other heavy jobs
  running, the animator measured 0.08 to 0.10 ms p50 and 0.11 to 0.19 ms p99.
- **Checks.** The game's `skate_ride` scenario rides pushes, steering, flip tricks, grabs, spins, a grind and manuals, a
  roll-in over a crest and down a long face, and a grind into a sharp corner, and reads the state line every frame: no
  NaN (0 of 6741 frames), no planted foot off the deck (0 of 3709 frames regular, 0 of 372 goofy), no pop between clips
  (`step=`; the fastest body bone 1447 cm/s, a sketchy landing's switch), and the standing rider against the native
  reference's stand (`reference.json`, `stand/idle`, bones in the deck's frame): 1.35 cm mean, the worst bone a hand at
  2.8 cm. Retargeted onto a character with other proportions, the rider keeps the toes 4.5 to 4.7 cm over the deck.

## Physical rider

While riding, the rider is an active ragdoll (`skate.RidePhysical 1`, the default): the bodies of its physics asset
simulate in the world's Chaos scene, Physics Control drives them toward the animated pose, and the board holds the feet.
The bail lets the same bodies go limp, and the get-up blends from a snapshot of the fallen body into the get-up clip.
`skate.RidePhysical 0` turns the rider back into pure animation, with a ragdoll only for bails.

### What the reference rider does

These numbers come from the oracle traces (`build/<game>/skate-ride/oracle/traces`), comparing the published pose
with the animation pose. They are tuning targets and QA tolerances. The implementation is ordinary Unreal code; it
is not a port of the native code.

| Situation | Published pose versus animation |
|---|---|
| Rolling, carving, powerslide, manual, grind | upper body within 0.5 cm (p95); feet held on the deck, 6–8 cm from the animated feet |
| Ollie and drop landings | the hips stay within 1–4 cm. The compression is in the clips: the hips drop 47–54 cm below standing, lowest at 0.10–0.23 s, 90 % recovered after 0.73–1.08 s |
| Knocks that do not bail (wall at 5 m/s) | the hips move up to 6 cm |
| The last 0.5 s before an impact bail | the hips move 10–14 cm |
| Bail | continuous, with no jump: 8 cm at 0.125 s, 8–26 cm at 0.25 s, 14–37 cm at 0.5 s, 64–127 cm at 1 s |

The rider is therefore stiff while riding: what you see is the animation, a body that carries its momentum through
knocks and landings, and feet that stay on the board. The body becomes visible as physics when something hits it, and
it goes fully limp only in a bail.

### Unreal mapping

- **Code.** `URidePhysicalRider` (`RidePhysicalRider.h`) is owned by `USkateComponent` as `PhysicalRider`. The ride
  drives it each frame from `AfterRideFrame` (`RideComponent.cpp`), after the step and before the mesh animates. With
  no ride step (mount and dismount clips on foot, a get-up that outlives the ride) it ticks itself in the `OnFoot`
  profile.
- **Bodies.** The rider uses the mesh's own Physics Asset when it has six or more bodies. Its constraint profile
  `RideConstraintProfile` (default: the asset's own) applies while riding, and `BailConstraintProfile` (`Ragdoll`, when
  the asset has one) in a bail. Otherwise the rider uses an asset built from the bone contract: 16 capsules, one set
  of joint limits wide enough for every riding pose, and no collision between the rider's own bodies. While riding, a
  limit that the animation passes widens to it (`WidenLimits`); in a bail the limits hold.
  - A root bone with a scale (an FBX armature carries its unit scale there) needs a body on the root. The skeletal
    mesh's physics blend takes that body as the frame of the simulated bodies under it. Without one, the blend divides
    by the root's scale twice, and the pelvis lands at the root. The built asset adds a kinematic root body that
    touches nothing. A rider's own asset on such a skeleton needs the same body.
  - The built shapes are sized in the bone's units, lengths as well as radii. On a root scaled 148 times, one unit
    is 1.48 m.
- **Controller.** A `UPhysicsControlComponent` sits on the rider. It creates its controls and body modifiers from a
  `UPhysicsControlAsset`, using limbs found through the bone contract:
  - parent-space controls on every joint, aimed at the animated pose, in the sets `Joints_Spine`, `Joints_Arms` and
    `Joints_Legs`;
  - world-space controls ("anchors") on every body, with the sets `Anchor_Pelvis`, `Anchor_Feet` and `Anchor_Hands`
    as the strong ones. They are made relative to the kinematic root body, which the actor carries with the board
    (`CreateControlsAndBodyModifiersFromPhysicsControlAsset` with the mesh and its root bone as the world component).
    An anchor in the world would trail a target moving with the board by about a frame, 12 cm at 10 m/s. The pelvis
    anchor replaces the root-to-pelvis joint control, which is removed. A skeleton without a root body anchors in the
    world;
  - a body modifier on every body: kinematic and unseen (physics weight 0) until the mount, simulated after it.

  Targets come from the mesh's animated component-space pose (`bUseSkeletalAnimation`). The mesh stays attached to
  the capsule
  (`ComponentTransformIsKinematic`), and the ride moves the actor without teleporting physics (`ETeleportType::None`).
- **Phases.** Each phase is a named profile in the control asset: `Riding`, `Air`, `Landing` (held for `LandingTime`
  after a touchdown), `Grind`, `Manual`, `Bail`, `GetUp`, `OnFoot`. `InvokeControlProfile` switches between them as
  the session's mode changes. The mount and dismount fade the body modifiers' physics weight over `MountBlend` and
  `DismountBlend`. The default profiles are built from `URidePhysicalSettings` (Project Settings › Plugins › Skate
  Physical Rider); `skate.RidePhysicalReload` rebuilds them live. Point `ControlAsset` there at an authored asset to
  replace them in the editor.
- **Strengths.** A strength works like a frequency: an acceleration drive with velocity feed-forward lags by a/(2πf)².
  The defaults were tuned live against the measurements below (`set RidePhysicalSettings Riding (Pelvis=16)` and
  `skate.RidePhysicalReload` in the console).
  - Pelvis anchor, 16 Hz, anchor damping ratio 0.5. In a quarter pipe the anchors trail the turning board by a lag
    that halves with each doubling of the frequency or halving of the damping: 27 cm p95 at 8 Hz and ratio 1, 7 cm
    now.
  - Feet, 12 Hz. On the board the feet do not collide with the world, since the deck carries them.
  - Joints, 10 Hz.
  - Every body also has an 8 Hz anchor. This stops sag from building up down the chain.
  - Gravity 0: Physics Control's gravity compensation (the body modifiers' gravity multiplier). With gravity the
    drives hold the pelvis 1.9 cm under the animation at every speed; without it, 0.2 cm. The `Bail` profile falls
    with gravity 1, from the bail's first frame.
- **World.** Query-only surfaces within `WorldRadius` (12 m) of the body are made physical while it simulates, so
  knocks, hand contacts and the bail are real Chaos contacts. They follow the body every 6 m and go back to query-only
  beyond twice the radius. Instanced meshes with more than 64 instances are left alone. Chaos substepping comes from
  the project's physics settings; the rider wants `MaxSubstepDeltaTime` 1/120 with up to 4 substeps.
- **Bail.** On the bail's first frame `OfferBail` classifies it (`ClassifyBail`). An upright, slow bail with the feet
  below the hips, no big drop and no fast spin is `RunOut`; everything else is `Fall`. The transition code may take
  the bail through `OnBailStart`: the body stays active and plays a run-out on foot. Otherwise `StartBail` lets the
  same bodies go with the momentum they have. The joints drop to the `Bail` tone (3 Hz) at once, and the anchors fade
  out over `BailRelease` (0.15 s, a multiplier on the world-space set). The bail starts with no jump. The board
  becomes a 3.5 kg Chaos box thrown with the board's velocity and spin, and the board's meshes follow it.
  - A body that gains speed or height it was never given, or falls through a floor, is unstable. The ride then drops
    the ragdoll, and the session slides the rider to a stop instead.
- **Get-up.** This is the standard technique. When the body has settled (still for 0.4 s, after at least 1.6 s), it
  takes a pose snapshot and blends the pose from the snapshot into the clip over `GetUpBlend` (`BlendFromSnapshot`).
  The rider gets up where the body lies and never returns to where the bail started.
  - The bodies stay simulating and seen until the animation shows the snapshot, then go kinematic and unseen. The
    mesh shows a pose the ride sets a frame later, and Physics Control's copy of it (the kinematic bodies' targets)
    a frame after that. Switching at once showed the clip's pose for one frame (the hips 61 cm off) and moved the
    bodies there the next. The switch waits until Physics Control's pelvis and head are within 10 cm of the snapshot,
    at most five frames.
  - **Onto the board.** The ride blends the pose seam (`USkateComponent::GetRetailPose`) and moves the board's meshes
    from the loose board back under the feet. The active ragdoll returns at the end.
  - **On foot** (`WantsGetUpOnFoot`). The transition code plays the recovery off the board (`BeginGetUpOnFoot`). It
    may take the loose board (`TakeLooseBoard`), which then stays a physical body it owns.
- **Debugging.** The bodies, controls and contacts are ordinary world physics, so the Chaos Visual Debugger records
  them. `p.PhysicsControl.*` and the component's `bShowDebugVisualization` also apply. The Ride state line
  (`USkateComponent::GetRetailState`, `atelier live state`) ends with the phase, whether the bodies simulate, the
  physics weight, the distance of the pelvis, feet and worst body from the animation (cm), the pelvis body's world
  position, the get-up blend, the last bail's kind, the body count, and which physics asset is in use. A game's QA
  checks read it.
  - A rider placed further than 1 m in one frame (a scripted placement) has its bodies carried along by the skeletal
    mesh's own teleport (`UpdateKinematicBonesToAnim` with `TeleportPhysics`), at the rider's velocity. Physics
    Control's reset to cached targets would give each body the jump divided by the frame time. The component's
    `TeleportDistanceThreshold` is the same 1 m. A change of speed above 2 m/s in one frame during the next three
    frames (a scripted launch) is given to the bodies too. The mount starts the bodies the same way.
  - A riding body more than 3 m from the animation (carried off by something it could not resolve) is reset onto
    Physics Control's copy of the animation. Frames in which Physics Control has no copy (before its first update)
    are not measured.
  - `skate.RidePhysicalDump` logs every body: its scale, its body, bone and target positions, its bounds, and the
    physical components it overlaps.
  - Each profile's `bBodyTouchesWorld` turns the bodies' world collision on or off for that phase (the feet have
    their own `bFeetTouchWorld`).

### Measured

A rider with the built asset (17 bodies) and the profiles above, on scripted runs. Distances are from each body to
Physics Control's copy of the animation, p95.

| Run | Pelvis | Feet | Reference |
|---|---|---|---|
| Rolling at 0, 2, 4, 6, 8, 10 m/s | 0.3–0.6 cm | 0.4–0.7 cm | upper body 0.5 cm |
| Hard carve at 8 m/s | 3.3 cm | 3.2 cm | |
| Pushing and carving | 2.0 cm | 3.5 cm | |
| 50-50 grind | 4.8 cm | 4.7 cm | |
| Quarter pipe | 7.7 cm | 5.7 cm | |
| 3 m drop | 4.8 cm | 2.9 cm | hips 1–4 cm |
| Kickflip | 6.0 cm | 4.1 cm | |
| Ride QA, regular and goofy | 2.1–2.2 cm | 3.4–3.5 cm | |
| Ride QA, a second rider on another skeleton | 2.5 cm | 3.8 cm | |

- Landing (ride QA): the worst body 14–16 cm off, the pelvis back under 3 cm within 7–9 frames.
- Bail: 1–3, 14, 38–45 and 60–73 cm at 0.125, 0.25, 0.5 and 1 s, against 0–8, 8–26, 14–37 and 64–127 cm. The bail
  starts with the body moving at the board's speed (10 cm a frame at 6 m/s) and no jump.
- Get-up: across the hand-over the hips move under 0.5 cm a frame, and the rider rises within 6 cm of where the hips
  lay. The hand-over took five frames in every get-up measured.
- Cost, riding a park road with `skate.RidePhysical` 0 then 1 with no other heavy job running: game-thread frame p50
  16.66 then 16.69 ms, p99 17.17 then 17.11 ms. On busier machines, p50 16.69 then 16.63 ms and 17.5 then 16.7 ms,
  p99 21.04 then 19.83 ms and 23.0 then 17.2 ms. The difference is within the noise.
- No run went unstable. Every frame simulated, and nothing was reset. Wherever the hips move far in one frame, the
  board moved as far, over a long frame.
- The first frame after a scripted placement and launch leaves the pelvis 6–13 cm behind (37 cm when placed 3 m up).
  At a grind lock the board moves at most 2.3 cm a frame more than its speed carries it (the native board, 0.7 cm).
- The copy of the animation the bodies follow is a frame older than the pose the mesh shows. While riding, the
  rider shows its pose about a frame late, in the board's frame.

### Why the component and not RigidBodyWithControl

`FAnimNode_RigidBodyWithControl` simulates the bodies on the animation thread in a private immediate-mode scene. That
scene sees the world only through shapes it copies near the character. The bail would then need one of two things,
and both are worse:
- keep tumbling inside that private scene, which has no contact with the loose board or with props that move;
- hand its state over to world bodies, which is a discontinuity at exactly the moment the reference shows none.

The component drives the mesh's own bodies in the world scene. Ramps, rails, walls, the loose board and props are all
real contacts. The riding body and the bail ragdoll are one set of bodies, so riding, bail and get-up form one
continuous simulation, and they all show up in the Chaos Visual Debugger. The cost is game-thread control updates for
about 32 controls, which is small next to the frame. The anim-node approach would win for many characters or for
lower levels of detail, and the ride has neither.

## Transitions

Getting on and off the board with the Ride backend (`RideTransition.*`, `USkateComponent`) keeps one continuous
character. The actor is never moved to a new place:
- the capsule changes size about its centre and settles onto the floor under it;
- the mesh keeps its world place across each switch, then eases back onto the capsule over `MeshSettle`;
- the pose switches by inertialization (`FAnimNode_SkateRider` in the character's graph, on a `RequestPoseBlend`);
- the speed carries over both ways.

The native backend still switches at once.

Off the board, the native clips play through the session's animator (`FRideSession::StepOffBoard`). Their
`TRAJECTORY` is put on the capsule's floor, facing the way the clip goes, and the pose is retargeted like a ride's
(`PublishOffBoardPose`). There, the visible deck is where the clip's `SKATEBOARD_ROOT` is:
- on the ground, it grows about its contact like a ridden board;
- held, it is scaled with the body, between the two by its height above the trajectory.

On the ground, a clip moves the capsule along its root motion through an override root motion source (`SkateDrive`,
its Z left to CharacterMovement). The source's speed is scaled from the character's speed at the start to the board's
(or the run's) at the end. In the air no clip moves the capsule: CharacterMovement keeps the fall, the clip's own arc is
left out, and its trajectory follows the capsule's floor. A clip that follows another starts from the trajectory the
last one left and eases onto the capsule's floor. `IsRiding()` is true while a clip plays: the game's own actions and
turning wait for it.

| State (`foot=`) | What plays | Board (`board=`) |
|---|---|---|
| `off` | the character's own animation | `away` (dissolved), or `world` (lying) |
| `carry` | the board-carry locomotion: `BR_STAND_0_CYC`, `BR_WALK_FWD_CYC`, `BR_RUN_FWD_CYC` and `BR_SPRINT_FWD_CYC`, blended by speed between their own speeds (about 170, 540 and 910 cm/s) | `hand` |
| `mount` | `BR_STAND_0_INTO_MOUNT`, or `BR_{WALK,RUN,SPRINT}_FWD_{0,25,50,75}_INTO_MOUNT` | `hand`, then `ride` |
| `dismount` | `BR_DISMOUNT_{HI,LO}_INTO_STAND_0`, `BR_DISMOUNT_{HI,LO}_INTO_RUN_FWD` or `BR_DISMOUNT_FAST_{HI,LO}_INTO_RUN_FWD`, then the carry | `hand` |
| `air` | a jump with the board, `JBR_STAND_0_TO_SML_FWD_0` or `JBR_RUN_FWD_{0,25,50,75}_TO_SML_FWD_{25,75}`; or a step off the board in the air, `BR_DISMOUNT_{FS,BS,STALE,DBL,MUTE}_INTO_BR_AIR`, then `JBR_AIRDISMOUNT_TO_BIG_DN_0` | `hand` |
| `land` | `BR_LAND_{SML,BIG}_{DN,FWD,UP}_0_INTO_STAND` or `BR_LAND_{SML,BIG}_{DN,FWD,UP}_{25,75}_INTO_RUN_FWD` (`BIG_DN` has only `0`), then the carry | `hand` |
| `airmount` | `BR_LF_AIR_INTO_MOUNT_BSGRAB` or `BR_RF_AIR_INTO_MOUNT_BSGRAB` (a caveman) | `hand`, then `ride` |

- **Mount.** The game's skate button, on the ground. The gait is chosen by speed (under 80 cm/s standing, then walk
  under 350 and run under 720, sprint above). The variant is the quarter of the stride the character is at: the
  carry's phase, or the phase read from the feet (`L - R` along the facing goes as `-sin 2πφ`, φ 0 with the left foot
  down; a mirrored clip is half a cycle on). A faster run plays the clip up to 1.3 times faster. The clip's travel is
  scaled to start and end at the character's speed. The board is the one in hand; without one, a board dissolves into
  the hand over the clip's first frames, and a board lying elsewhere goes. At the clip's end the ride starts on the
  clip's deck, at the clip's speed: the ride's own clips take over with a cut on the pose mesh, hidden by the
  character's blend (`ClipBlend`).
- **Dismount.** The skate button, on the ground. The clip is chosen like this:
  - `FAST` above 600 cm/s;
  - `RUN_FWD` above 150 cm/s or with the stick held;
  - `STAND_0` otherwise.

  It is `LO` when crouched. Rolling fakie, the rider steps off facing the other way, in the other stance's clip. The
  clip starts with its board exactly on the deck the rider leaves; that offset eases away over the first 0.35 s.
  The carry follows on at the clip's last stride (its `CADENCEENDPERCENT` curve when it has one, else the phase read
  from the clip's feet). Speed above the character's own goes on as momentum that fades (`MomentumDecay`,
  `MomentumBrake`). After 40% of a clip that ends standing, the stick runs off into the carry; any landing or step-off
  also gives way to the stick turned more than 60 degrees from its way.
- **Air dismount.** The skate button in a ride's air. The clip is the grab held: Indy `FS`, Melon `BS`, Christ air
  `STALE`, tuck knee `DBL`, otherwise `MUTE`. It starts with its board on the deck the rider leaves, the feet come off
  it and the board goes to the hand; the offset from the capsule's floor eases away before the landing. With more than
  0.25 s of fall left the fall clip follows, timed to the ground below.
- **Jump.** A jump while carrying plays the jump with the board from the stride's quarter (from a stand under
  150 cm/s), timed to the fall (0.6 to 1.4 times). A step off a ledge keeps the character's own pose, the board on
  the hand bone nearest to it.
- **Landing.** The landing clip is `BIG` after 0.9 s in the air or falling faster than 700 cm/s; `DN` 60 cm or more
  below the take-off, `UP` 30 cm above; `RUN_FWD` above 150 cm/s, at the jump's stride (25 or 75), otherwise `STAND`.
  Its travel is scaled to keep the landing speed.
- **Caveman.** The skate button in the air (a jump, with or without the board in hand, or after an air dismount): the
  board goes under the feet, the foot ahead first. The clip is timed to the fall (0.8 to 1.5 times). From the
  character's own pose its pelvis starts at the character's. At its end the ride starts airborne when the ground is
  more than 70 cm below; closer, the feet stay on the board until the landing. Landing before the board is under the
  feet lands on foot holding it.
- **Carry.** The board stays in hand for `BoardHoldTime` (6 s), then dissolves in the hand while the character's own
  pose blends back (`CarryBlend`). It also goes as soon as the hands are needed (`ISkateRider::CanCarrySkateBoard`
  false: for example a sword drawn, a boat steered, swimming or an interaction). The walk, run and sprint cycles share
  one phase, which advances by the distance covered over the blended stride, so the feet keep to the ground. There is
  no back socket: a board is either in the hand, under the rider, lying, or gone. A board leaving a hand of the
  character's own pose for a clip's eases there over `ClipBlend`.
- **Board button** (`USkateComponent::RecallBoard`, the game's button, on foot):
  - with no board, one dissolves into the hand;
  - holding one, it is put away;
  - with one lying in the world, that one dissolves and a fresh one comes to the hand.
- **Bail.** The skate button during a bail means "get up on foot": the rider gets up where the body lies, then steps
  off at once with the character's own pose blending in. The board stays lying where it came to rest (`world`), a
  body of its own. A lying board dissolves after `BoardLyingTime` out of reach (`BoardReach`). A mount while a board
  lies in the world removes it and uses a fresh board in the hand.
- **Placement.** `PlaceAt()` gets on at once, without a clip (a scripted cut).

The tunables are in `skate.RideTune`: `MountBlend`, `DismountBlend`, `ClipBlend`, `CarryBlend`, `MeshSettle`,
`BoardDissolveTime`, `BoardHoldTime`, `BoardLyingTime`, `BoardReach`, `MomentumDecay` and `MomentumBrake`.

The transition fields on the state line (`atelier live state`) are:
- `board=`, `shown=` and `vis=`;
- `hip=`, `deck=`, `vel=`, `offset=` (the mesh's offset from its on-foot place) and `momentum=`;
- `foot=`, `clip=`, `t=`, `lift=` (the body standing on the deck, 0 to 1), `phase=`, `hold=`, `hand=` and `air=`
  (seconds in the air).

A game's transitions QA scenario checks them.
