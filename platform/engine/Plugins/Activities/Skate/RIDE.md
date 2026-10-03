# Ride

Ride is the Unreal-native skating backend (`skate.Backend Ride`, `USkateSettings::Backend`). Its sources are in
`Source/AtelierSkate/Private/Ride/`.

## Board

The board is rigid and steps at 60 Hz (`RideSession.cpp`; the numbers are in `RideTuning.h`). Each frame shows it
between its last two steps at the frame's own time, from the ride's first frame (the step clock starts a step full).

- **Ground.** A tick moves in steps of at most `GroundStep` (15 cm). Each step probes the ground under both axles with
  a wheel-sized sphere, from `StepUp` (6 cm) above to `StickGap` plus a share of the step below, and the deck takes
  the line between the two contacts. Ground that falls away further is a take-off. A ride that starts inside the floor
  (a hand-off a little low) finds the floor's top from up to `StartRecover` (40 cm) above and starts on it, rather
  than in the air under it.
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
  `GrindLockSpeed` (4 m/s), rather than jumping there: the native board touches the line before it locks, and its step
  at a lock is at most its speed's plus 0.7 cm. At a line's end the grind carries on, at its speed, into a line whose
  end meets it within `GrindJoin` (10 cm) and turns less than `GrindCorner` (45 degrees). At a sharper corner, within
  a line or between two, the board flies off the way it was going. A grind slower than `GrindStall` (15 cm/s) after
  half a second steps off the line: a hop of `GrindStallHop` (1.1 m/s up, 4 cm) to a ledge's open side, a coping's
  deck, or else the side the rider leans to unless something stands there, just wide enough that the board comes down
  beside the line rather than on it. The air sweep starts inside the line, so it passes through it until the board is
  clear.
- **Lip airs.** As in the native runtime (`AirTrajectoryLaunch.cpp`, `AirTrajectoryScoring.cpp`), a take-off from a
  face steeper than `VertSteepness` (50 degrees at `VertAssist` 1, 75 at 0), climbing at least `VertClimb` (0.66 of
  its speed up, against the speed into the face), comes back into the face it left. The face is the steepest climbed
  in the last 8 steps (0.13 s), so a board that leaves from the coping's rounded edge still counts as leaving the
  wall. The velocity over the coping is lost; the climb is turned to `VertLean` (3 degrees) from vertical, into the
  ramp, at its own speed, and the speed along the coping is kept. The reference's board leaves vert at 0.29 to 0.37
  m/s into the ramp for 5.3 to 5.9 m/s up (native gets there with a 1.15 degree lean and its landing aim). The flight
  then takes the velocity or one of six around it (native's cone: 10 degrees across the heading, 40 along it, at 2 to
  4 m/s), whichever lands back on the steepest part of the same face, not within 0.25 s nor within 0.15 s of the apex,
  with the least change. It falls under `VertGravity` (10 m/s², the reference's board on vert airs; flat airs keep
  `AirGravity`). With the stick released, the board turns to the nearer of forward and fakie on the landing's line by
  touch-down (native's rate: the angle left over the time left, times 1.2), so a straight air and a 360 land fakie and
  a 180 forward. A flick early in a lip air pops straight up. Holding transfer carries the rider over the coping
  instead. Any landing keeps the speed along the face it lands on; coming down a face between 46 and 65 degrees that
  speed grows by up to 15%, as much as the travel runs downhill (native's `LandingSpeedScalarVsGroundNormalY`), so an
  air that comes back in low on the transition keeps its speed.
- **Pushing.** A push from slower than `PushFromRest` (0.3 m/s) goes nose-first, and the board stands on the planted
  foot through the wind-up, so it neither creeps back down a slope nor leaves tail-first.
- **Pumping.** Extending through a concave transition gains speed, v × exp(curvature × extension), up to
  `PumpExtension` (26 cm) of travel between crouched and extended; the rider crouches on flats, crests and straight
  faces. Holding push pumps on any face steeper than 37 degrees. Coasting there pumps by itself, `AutoPump` (0.7) as
  much and less with speed (native's unintentional pump and its `PumpVsVel`: all of it to 7 m/s, 96% at 8.8, 57% at
  10.7, 16% at 12.2, none from 14.2), so a rider going back and forth in a bowl keeps up speed, toward native's 12.3
  m/s.
- **Powerslides.** Above `SlideMinSpeed` (1.2 m/s) the deck turns `SlideAngle` across the travel and scrubs speed.
  The powerslide key holds one, turned to the stick's side. On a pad the left stick's rear diagonal does, as the native
  runtime's slide intents read it (`InputIntentions.cpp`): pushing the stick out past 0.9 into the 52 degrees either
  side of straight back starts a slide on that side, and it lasts while the stick stays out past 0.9, anywhere from
  the other side's sideways line to 115 degrees round its own. Straight back, or a stick already held there, does not
  start one.

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
  at 1000 cm/s, a little under the trick clips' own fastest limbs (1100 to 1300 cm/s). The node keeps its stored poses
  and a blend in progress across a recache of the same bones: swapping a physics asset in or out (the physical rider
  does, at its start and end) re-requires the mesh's bones, and dropping the poses there would turn the next request
  into a cut.
- **Stance.** The clips are authored goofy. A regular rider plays them mirrored (`bMirror = !bGoofy`), and a stance
  change inertializes over 0.2 s. `MDT_SkateRider` mirrors across Unreal's Y axis and lists every bone the native rig
  mirrors, the centre bones onto themselves: Unreal leaves a bone without a row unmirrored.
- **Fakie.** Riding fakie the head and chest turn toward the travel, as native's fakie channel does
  (`FAKIE_HEAD_CHANNEL_CYC`, `FAKIE_CHANNEL_CYC`, `FAKIE_MANUAL_CHANNEL_CYC` layered over the main clips on the neck,
  head and upper spine). The channel blends in and out over 0.3 s; its three clips blend by a torso value: 1 in a
  manual, 0 in a powerslide (the head only), 0.5 otherwise, moving at 0.6 a second (set at once when fakie starts).
  Native's angles from the travel (head, chest; offline through its channel blend): forward 3°, 46°; fakie without the
  channel 177°, 134°; fakie 72°, 126°; a fakie manual 22°, 100°.
- **Air legs.** As native's air legs do (its `B_AIR_CYC` trees), the air pose blends by a hips-to-board distance, each
  clip carrying its own: it stays at its floor (0.5, native metres) until the rider prepares to land, (1 − 0.6) / 2 s
  before the touch-down onto level ground (less onto a steeper face, never onto a wall), then grows at 2 a second, so
  the legs are still reaching for the board when it lands. The low pose reaches toward the extended one as the fall
  goes on (0.16 to 0.45 over the first 0.3 s after the top of the flight).
- **Placement.** The riding clips' `TRAJECTORY` is the deck's pivot at rest, 8.9 cm above the ground, which is the
  session's root. The animator puts the clips' root space on the session's deck (`Lock` 0), or moves the pose so that
  the clip's board lies exactly on the deck (`Lock` 1, for clips whose board is elsewhere, as in the transitions). On
  the ground the whole pose then moves along the ground's normal (`lift`, cm), so the feet stay on the deck: rolling
  (the ground, a manual, a powerslide, a push, a brake, the load and a landing) until the lowest wheel touches the
  ground, whatever height the clip gives the deck, unless a nose or tail would then sink; on a board the clip tilts
  off its wheels (a pop's tail, a 5-0) only by what would sink. The move eases back to none at 150 cm/s in the air.
- **Board.** The clip's `SKATEBOARD_ROOT` is the board: flips, shove-its, the pop's tilt and the carve's lean come
  from the clips, and the session's deck adds only a powerslide's yaw. The trucks and wheels are placed from the deck
  with the wheels' spin. On its wheels the deck rolls over the trucks as on a real board: each truck rolls against the
  deck, about the deck's length, so that its axle lies level with the ground (up to 30 degrees; a deck rolled further
  lifts the inside wheel), and both wheels of an axle touch the ground through a carve; off the ground the trucks
  come back straight under the deck at 240 degrees/s. Without the rig in the build, the board rides alone with a
  procedural flip.

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
| Air | `IA_IDLE_N_N_0_CYC` blended toward `IA_IDLE_LO_N_0_CYC` and `IA_EXTEND_LO_N_0_CYC` by the legs' reach (below); after a flip trick with its own air cycles, `T_<TRICK>_H_CYC` toward `T_<TRICK>_L_CYC` the same way |
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
- **The rider's own body.** The clips' arms hang beside an adult's hips, and on a rider with wider hips and thighs
  the hands sink into them. After the retarget each arm swings about its shoulder, its bend kept, just far enough that
  its hand and the hand's half of its forearm clear the rider's own pelvis, spine, chest and thigh bodies (its physics
  asset's, fitted to the skin) by `skate.ArmClear` (1 cm), at most 25 degrees. A grab solves after it, so it still
  reaches the board. A clip's pushing or braking foot steps on the source's ground plane, which on another rider's
  proportions can be under the real ground: a foot whose sole goes under the ground below it (by up to 15 cm) lifts to
  `skate.FootGround` (0.5 cm) above it, the leg solved to it. Neither runs in a bail. Below 0 turns either off.
- **Pose health.** The Ride state line (`USkateComponent::GetRetailState`, `atelier live state`) has `clip=` (the
  clip with the most weight), `ct=` (its time, s), `lock=`, `lift=` (cm), `step=` (the fastest body bone in the
  root's space, cm/s), `stepbone=` (that bone), `dt=` (the frame time it is measured over, ms),
  `feet=` (the toes' heights over the deck, cm), `feetoff=` (feet outside the deck's 42 × 14 cm outline, or more than
  16 cm above or 4 cm below it), `nan=` and `anim=` (the animator's time this frame, ms), `hipboard=` (the hips over
  the board, cm), `headyaw=` and `chestyaw=` (their facing from the travel, degrees), `fakiech=` and `torso=` (the fakie
  channel's weight and torso value) and `feetalong=` (each toe along the travel from the deck's pivot, cm). The game's
  QA reads it.
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
| Bail travel (the pelvis) | the entry speed times 1.0–1.4 s, at any speed: on flat at 4.6 m/s 0.97× at 1 s and 1.04× at rest (1.5 s); at 5.6–12.2 m/s 0.96–1.00× and 1.16–1.40×, at rest 1.7–2.4 s after the bail (10.6 m/s: 0.97× and 1.26×); thrown off in the air at 4.8 m/s across (rising 8.7 m/s) 1.04× and 1.36× the speed across. A bail into a wall stops at it, about 1 m on |

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
  the asset has one) in a bail. Otherwise the rider uses an asset built from the bone contract: 16 bodies, one set
  of joint limits wide enough for every riding pose, and no collision between the rider's own bodies. While riding, a
  limit that the animation passes widens to it (`WidenLimits`); in a bail the limits hold.
  - Each built body is fitted to the skin it carries (`bFitBodiesToSkin`, on by default): the convex hull of the
    mesh's vertices whose strongest weight is on its bone, or on a bone under it without a body (the fingers go to
    the hand, the hair to the head), at the mass of the contract's capsule. A stylised rider is far from the slim
    1.7 m figure the capsules are sized for: with them his face sank 17–30 cm into the floor in a bail and his hands
    and feet 13 cm. A body with too little skin keeps its capsule. Off, the contract's capsules.
  - The built asset is kept for the session, one per mesh and fit, so a switch back to a rider does not fit it again.
  - A root bone with a scale (an FBX armature carries its unit scale there) needs a body on the root. The skeletal
    mesh's physics blend takes that body as the frame of the simulated bodies under it. Without one, the blend divides
    by the root's scale twice, and the pelvis lands at the root. The built asset adds a kinematic root body that
    touches nothing. A rider's own asset on such a skeleton needs the same body.
  - The built shapes are sized in the bone's units, lengths as well as radii. On a root scaled 148 times, one unit
    is 1.48 m.
- **Controller.** A `URidePhysicsControl` (a `UPhysicsControlComponent`) sits on the rider. It creates its controls
  and body modifiers from a `UPhysicsControlAsset`, using limbs found through the bone contract:
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
  Under a heavy load the mesh can reach Physics Control's update with no component-space pose for a frame. Physics
  Control then aims every control at the identity, and the anchors pull the whole body onto the board: the hips
  dropped 48 cm in one frame. `URidePhysicsControl` skips such an update, and the drives keep last frame's targets.
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
  same bodies go with the momentum they have. They go limp at once: on the bail's first frame the `Bail` profile lets
  go of every anchor, turns gravity on and leaves the joints a 3 Hz tone toward the clip, inside their authored limits.
  `StartBail` applies the profile then and there (`UpdateControls`). Physics Control otherwise applies a profile in
  its next update, which comes after that frame's physics when the session throws the rider off: the riding anchors
  then braked the bodies toward the stopped root, from 5.9 m/s to 1.6 m/s in a frame, and a 6 m/s bail slid 2 m
  instead of 7.5 m. `skate.RideBailApplyNow 0` brings the late profile back, and `skate.RideBailTrace N` logs the
  bail's first N frames (pelvis, mean body and root velocities, and when the controls updated).
  The anchors hold the bodies in the frame of the kinematic root body, and in a bail the ride stops the root on the
  bail's frame, then carries it to the ground under the body a frame late (on a quarter, from the board on the wall to
  whatever lies below the hips). Held to that frame even for a moment, the body is braked to a stop on flat or flung
  off a wall. The bodies fall with `BailFriction` (0.06, the lower of it and the ground's, as a physical material
  override; the default material's is 0.7). While the pelvis is down within 50 cm of the ground, they also drag with
  `BailDrag` (1.5 per second of linear damping, on top of the physics asset's), coming in smoothly from `BailDragFrom`
  (0.7 s after the bail) to `BailDragFull` (1.1 s). The drag takes speed in proportion to the speed, so a slide's length
  grows with its entry speed, as the reference's does. Friction alone makes it grow with the square. Held off for most
  of a second, the drag lets the body keep its speed as the reference's does, then stops it within about another
  second. A body still in the air falls and flies freely.
  The board becomes a 3.5 kg Chaos box thrown with the board's velocity and spin, and the board's meshes follow it.
  - The bail's distance from the animation is measured with the pose carried as far as the ground under the pelvis has
    gone since the bail began, as the reference's root follows its body. The ride's root gets there some frames late
    (it follows the body's ground through the session's interpolated step), and Physics Control's copy of the pose a
    frame later still.
  - A body that gains speed or height it was never given, or falls through a floor, is unstable. The ride then drops
    the ragdoll, and the session slides the rider to a stop instead.
- **Get-up.** This is the standard technique. When the body has settled (still for 0.4 s, after at least 1.6 s), it
  takes a pose snapshot and blends the pose from the snapshot into the clip over `GetUpBlend` (`BlendFromSnapshot`).
  The rider gets up where the body lies and never returns to where the bail started.
  - Blended joint by joint, the rotations swing a limb through the floor on its way from lying to standing: a foot
    went 15–23 cm under it half way up. The blend lifts the root by the deepest shortfall, so no bone goes lower than
    the lower of its two ends, where it lay and where the clip puts it.
  - The blend measures the snapshot from the mesh's transform for this frame (`ShownTransform`: its relative
    transform on its parent's). Inside CharacterMovement's move the actor's children keep last frame's transform
    until the move ends: getting up after a bail on a quarter pipe, the hips stepped 42 cm in one frame. The loose
    board starts from the board's transform the same way.
  - The bodies stay simulating and seen until the animation shows the snapshot, then go kinematic and unseen. The
    mesh shows a pose the ride sets a frame later, and Physics Control's copy of it (the kinematic bodies' targets)
    a frame after that. Switching at once showed the clip's pose for one frame (the hips 61 cm off) and moved the
    bodies there the next. The switch waits until Physics Control's pelvis and head are within 10 cm of the snapshot,
    at most five frames.
  - **Onto the board.** The ride blends the pose seam (`USkateComponent::GetRetailPose`). The active ragdoll returns
    at the end. The board never travels by itself (`GetUpFromBody`, `AfterRideFrame`):
    - A board lying on its wheels within `GetUpBoardReach` (60 cm, about a step) of where he gets up is stepped
      onto: its meshes ease from the loose board under the feet over the get-up, at most about 3 cm a tick.
    - Any other board dissolves out where it lies (`ShowBoard`, the transitions' dissolve, over
      `BoardDissolveTime`), and a board then dissolves in under his feet while he rises. The board used to fly or
      glide to his feet over the get-up blend, up to 20 m/s. The bail checks in `skate_ride` measure this: while the
      board shows, it moves under 8 cm in a tick from the last fallen frame to half a second after he is up.
  - **On foot** (`WantsGetUpOnFoot`). The transition code plays the recovery off the board (`BeginGetUpOnFoot`). It
    may take the loose board (`TakeLooseBoard`), which then stays a physical body it owns.
- **Debugging.** The bodies, controls and contacts are ordinary world physics, so the Chaos Visual Debugger records
  them. `p.PhysicsControl.*` and the component's `bShowDebugVisualization` also apply. The Ride state line
  (`USkateComponent::GetRetailState`, `atelier live state`) ends with the phase, whether the bodies simulate, the
  physics weight, the distance of the pelvis, feet and worst body from the animation (cm), the pelvis body's world
  position and, in a bail, its height above the ground under it (`lie`) and the slide's drag in effect (`drag`, per
  second), the get-up blend, the last bail's kind, the body count, which physics asset is in use, and how many of
  Physics Control's updates were skipped for want of a pose (`skipped`, each also logged). A game's QA checks read it.
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
  - `skate.RideSkinCheck 1` adds the skin's depth under the ground to the state line (`MeasureSkinDepth`): a sample
    of the mesh's vertices, skinned on the CPU as the mesh shows them and traced against the ground's complex
    collision, the deepest overall and by group of bodies (torso, head, upper arms, forearms, hands, legs, feet). It
    also adds how far each hand's skin stays from the torso's and thighs' bodies (`hand_gap`, below 0 inside one;
    `MeasureHandGap`).

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

- Landing (ride QA): the worst body 12–16 cm off, the pelvis back under 3 cm within 7–9 frames.
- Bail on flat at 6 m/s: 7, 22, 41–54 and 55–73 cm from the clip at 0.125, 0.25, 0.5 and 1 s, against 0–8, 8–26,
  14–37 and 64–127 cm. The bail starts with the body moving at the board's speed (10 cm a frame at 6 m/s) and no jump.
  The pelvis travels 5.3–5.4 m in the first second and comes to rest 7.4–7.5 m on after 2.6 s (0.90× and 1.24–1.26×
  the entry speed times 1 s, against the reference's 0.97–0.98× and 1.04–1.16× at 4.6–5.6 m/s), lying 7 cm (the second
  rider 14 cm) over the ground within the second.
- Bail on flat at 10.9 m/s: 10.0–10.1 m in the first second, at rest 14.5 m on after 3.0 s (0.92–0.93× and
  1.33–1.34×, against the reference's 0.97× and 1.26–1.30× at 10.6–11.5 m/s), lying 7 cm over the ground within the
  second.
- How the slide was tuned, as the entry speed times 1 s travelled at 1 s and at rest, at 6 and 10.9 m/s. Friction alone
  (`BailFriction` 0.25, no drag): 0.78×/1.12× and 0.86×/1.91× (after 4.2 s): the length grows with the square of the
  speed. A drag from the moment the body is down (friction 0.1, drag 0.55): 0.75×/1.09× and 0.78–0.81×/1.30–1.33×
  (2.8 s and 3.6 s); other constant drags only traded the rest against the first second (0.1 with 0.5 1.14× and 1.38×
  at rest, 0.6 1.05× and 1.24×; 0.15 with 0.5 0.98× and 1.23×; 0.06 with 0.55 1.27× and 1.44×, creeping on for
  3.3–4.2 s). The reference's body keeps the entry speed for about 0.7 s, then stops within about a second, at any
  speed; a drag that waits as long comes closer. Ramped in over 0.6–1.0 s, friction 0.1 with drag 1.0: 0.87×/1.21×;
  0.08 with 1.0: 0.88×/1.28× and 0.91×/1.42×; over 0.7–1.1 s, 0.06 with 1.5 (taken): 0.90×/1.24–1.26× and
  0.92–0.93×/1.33–1.34×. The first second cannot reach the reference's: the body's landing keeps about 80% of its speed
  at any friction or drag.
- Bail landing an Indy on a quarter pipe at 9.2 m/s (the grab held into the landing, which comes down on the wall):
  limp from the first frame, the body slides down the wall; 0.45–0.52× the whole speed at 1 s and 0.62–0.73× at rest
  (the reference thrown off in the air, 0.50× and 0.65×). The hips move at most 6.5 cm in a frame beyond what the
  pelvis's own speed covers. Before, the anchors held the body for the bail's first 0.15 s in the frame of a root that
  jumped from the wall to the floor; it was flung at 45 m/s, the bail was handed to the animated slide, and the rider
  stood with the arms out until the get-up.
- The bail's profile applied at the bail, against Physics Control's next update: the pelvis kept 5.9 m/s on the next
  frame instead of 1.6 m/s, and the 6 and 10.9 m/s bails travelled 0.91× and 0.93× the entry speed in the first
  second instead of 0.27× and 0.21×. A 0.9 m drop at 8 m/s with a grab held into the landing slides 9.9 m (3.9 m
  before; the reference 8–11 m). At 40 frames a second the pelvis keeps its speed through the bail's first frames.
- Skin under the ground (`skate.RideSkinCheck`), the worst of the bails above for regular, goofy and a second rider on
  another skeleton, the contract's capsules then the fitted hulls. Sliding: hands 11.6–13.1 then 0.3–0.7 cm, head
  16.6–30 then 0.3–1.0 cm, feet 8.2–13.2 then 0.4–2.3 cm, torso 5.5–14.3 then 0.1–0.8 cm, legs 6.2–7.1 then
  0.4–2.3 cm. Lying, every group up to 20 cm then at most 0.7 cm (the second rider's legs 2.3 cm). Getting up, the feet
  18.9–23.2 cm then 0.7–2.6 cm with the blend's lift. A park's road and pool bails at 9–12 m/s: the head 17–27 cm then
  at most 1.1 cm. Riding, the pushing foot goes 5.4–6.3 cm under the ground in the push clips, with either set of
  bodies; nothing else does.
- Standing still on the board, one hand's skin sits 7–8 cm inside the thigh's hull and the other 3–4 cm
  (`hand_gap`), the same with the physical rider on or off: the idle clip's pose on that rider, not the bodies.
- Get-up: across the hand-over the hips move under 0.5 cm a frame, and the rider rises within 6 cm of where the hips
  lay. The hand-over took five frames in every get-up measured.
- Cost, riding a park road with `skate.RidePhysical` 0 then 1 with no other heavy job running: game-thread frame p50
  16.66 then 16.69 ms, p99 17.17 then 17.11 ms. On busier machines, p50 16.69 then 16.63 ms and 17.5 then 16.7 ms,
  p99 21.04 then 19.83 ms and 23.0 then 17.2 ms. With the fitted hulls, p50 16.63 then 16.67 ms, p99 18.11 then
  17.92 ms. The difference is within the noise.
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
- the mesh keeps its world place and rotation across each switch (the actor turning to a clip's way included), then
  eases back onto the capsule over `MeshSettle`: the inertialization works in the mesh's frame, so a mesh that moved or
  turned with the actor would show as a jump of the whole body;
- the pose switches by inertialization (`FAnimNode_SkateRider` in the character's graph, on a `RequestPoseBlend`);
- the speed carries over both ways.

The native backend still switches at once.

Off the board, the native clips play through the session's animator (`FRideSession::StepOffBoard`). Their
`TRAJECTORY` is put on the capsule's floor, facing the way the clip goes, and the pose is retargeted like a ride's
(`PublishOffBoardPose`). There, the visible deck is where the clip's `SKATEBOARD_ROOT` is:
- on the ground, it grows about its contact like a ridden board;
- held, it is scaled with the body, between the two by its height above the trajectory.

On the ground, a clip moves the capsule along its root motion through an override root motion source (`SkateDrive`,
its Z left to CharacterMovement). The source follows the clip's travel averaged over 0.2 s (the native trajectories
step unevenly frame to frame). Its speed goes from the character's at the start to the board's (or the run's) at the
end along a smooth step, or the clip's own travel is scaled to start at the character's speed. A mount also moves the
capsule on to where the clip leaves the board, so the ride starts with the capsule over the deck. The retargeted deck
sits a little off the clip's own (the bodies differ): that drift is taken off where the trajectory ends, so the deck
the rider stands on ends over the capsule, and a step onto a lying board puts the retargeted deck, not the clip's, on
the lying one. A get-up, held in the world, pulls the capsule after its trajectory instead. A step onto a lying board,
also held in the world, moves the capsule from where it stood, at rest, onto its trajectory by the clip's end: each
frame at the speed that puts it where the eased path is at the next frame's clip time. In the air no clip moves the
capsule: CharacterMovement keeps the fall (the drive holds its flat velocity, gravity its height, so the landing's move,
which comes before the component sees the landing, does not brake a character that has no stick yet), the clip's own arc
is left out, and its trajectory follows the capsule's floor. A clip that follows another starts from the trajectory the
last one left and eases onto the capsule's floor. `IsRiding()` is true while a clip plays: the game's own actions and
turning wait for it.

| State (`foot=`) | What plays | Board (`board=`) |
|---|---|---|
| `off` | the character's own animation | `away` (dissolved), or `world` (lying) |
| `carry` | the board-carry locomotion: `BR_STAND_0_CYC`, `BR_WALK_FWD_CYC`, `BR_RUN_FWD_CYC` and `BR_SPRINT_FWD_CYC`, blended by speed between their own speeds (about 170, 540 and 910 cm/s) | `hand` |
| `mount` | `BR_STAND_0_INTO_MOUNT`, or `BR_{WALK,RUN,SPRINT}_FWD_{0,25,50,75}_INTO_MOUNT`; onto a lying board, `BR_STAND_0_INTO_MOUNT` from its touchdown | `hand`, then `ride` |
| `dismount` | `BR_DISMOUNT_{HI,LO}_INTO_STAND_0`, `BR_DISMOUNT_{HI,LO}_INTO_RUN_FWD` or `BR_DISMOUNT_FAST_{HI,LO}_INTO_RUN_FWD`, then the carry | `hand` |
| `air` | a jump with the board, `JBR_STAND_0_TO_SML_FWD_0` or `JBR_RUN_FWD_{0,25,50,75}_TO_SML_FWD_{25,75}`; a step off the board in the air from a grab, `BR_DISMOUNT_{FS,BS,STALE,DBL,MUTE}_INTO_BR_AIR`, then `JBR_AIRDISMOUNT_TO_BIG_DN_0`; or a kick-out, `BR_KICKOUT_{HI,LO}_INTO_NB_AIR`, then `JNB_KICKOUT_TO_SML_FWD_75` | `hand`; kicked, `world` |
| `land` | `BR_LAND_{SML,BIG}_{DN,FWD,UP}_0_INTO_STAND` or `BR_LAND_{SML,BIG}_{DN,FWD,UP}_{25,75}_INTO_RUN_FWD` (`BIG_DN` has only `0`), then the carry | `hand` |
| `airmount` | `BR_LF_AIR_INTO_MOUNT_BSGRAB` or `BR_RF_AIR_INTO_MOUNT_BSGRAB` (a caveman) | `hand`, then `ride` |
| `runout` | `RUNOUT_{FWD,BWD,FF,BF}_{HI,LO}_{S,M,B}<n>_TO_RUN_FWD` (a bail run out on foot) | `world` (rolling on) |
| `recover` | `W_RECOVERY_ON{BACK*,FRONT,LEFT,RIGHT*}_N_0_N` (a get-up on foot where the body lies) | `world` (lying) |

- **Mount.** The game's skate button, on the ground. The gait is chosen by speed (under 80 cm/s standing, then walk
  under 350 and run under 620, sprint above: just under the character's own sprint, 637 cm/s, which it reaches). The
  variant is the quarter of the stride the character is at: the carry's phase, or the phase read from the feet (`L - R`
  along the facing goes as `-sin 2πφ`, φ 0 with the left foot down; a mirrored clip is half a cycle on). A faster run
  plays the clip up to 1.3 times faster. The clip's travel is scaled to start and end at the character's speed. The
  board is the one in hand; without one, a board dissolves into the hand over the clip's first frames, and a board lying
  elsewhere goes. At the clip's end the ride starts on the clip's deck, at the clip's speed: the ride's own clips take
  over with a cut on the pose mesh, hidden by the character's blend (`ClipBlend`). Every hand-off to the ride starts it
  on the floor under the deck, never inside it: a wheel-sized sweep down the deck's normal from 30 cm above (or, under
  something close overhead, from a step above) lifts a deck the clip brought into the floor onto it (a ride started
  inside a pier's planks found no ground and fell through them).
- **Dismount.** The skate button, on the ground. The clip is chosen like this:
  - `FAST` above 600 cm/s;
  - `RUN_FWD` above 150 cm/s or with the stick held;
  - `STAND_0` otherwise.

  It is `LO` when crouched. Rolling fakie, the rider steps off facing the other way, in the other stance's clip. The
  clip starts with its board exactly on the deck the rider leaves; that offset eases away over the first 0.35 s.
  The carry follows on at the clip's last stride (its `CADENCEENDPERCENT` curve when it has one, else the phase read
  from the clip's feet). CharacterMovement moves before the character's own tick gives it the stick, so its first move
  off a clip would have none and brake the speed away: the drive carries the clip's speed over that move, and the stick
  the character's tick then gives the next move shares it out. The character keeps what the stick lets it run at
  (CharacterMovement's analog speed); the rest goes on as momentum that fades, at `MomentumDecay` with the stick along
  the way and `MomentumBrake` without, so with the stick let go the whole speed runs out. The momentum is an additive
  root motion source, the character's own velocity recorded as CharacterMovement's velocity before it, so the walk's
  own speed does not dip as the source starts. A step off at once (a bail's get-up on foot) shares its speed out the
  same way. After 40% of a clip that ends
  standing, the stick runs off into the carry; any landing or step-off also gives way to the stick turned more than 60
  degrees from its way.
- **Air dismount.** The skate button in a ride's air with a grab held. The clip is the grab: Indy `FS`, Melon `BS`,
  Christ air `STALE`, tuck knee `DBL`, a one-foot `MUTE`. It starts with its board on the deck the rider leaves, the
  feet come off it and the board goes to the hand; the offset from the capsule's floor eases away before the landing.
  With more than 0.25 s of fall left the fall clip follows, timed to the ground below.
- **Kick-out.** The skate button in a ride's air without a grab: the feet push the board away (`BR_KICKOUT_HI`, or `LO`
  crouched). The board leaves the clip with the clip's own velocity and spin (its motion as shown, measured over 50 ms
  at least, so a very short frame does not throw it), at least 250 cm/s away from the rider, and flies on by itself: a
  small sphere moved by a `UProjectileMovementComponent` (it bounces off what it hits and slides to a stop on the
  ground), the deck over it turning with the spin. It settles flat over 0.2 s, wheels down or, when it came down closer
  to that, upside down. The rider lands on foot without it. Rising, or with more than 0.1 s of the fall ahead, the
  rider falls on with the board's velocity rather than standing on a floor below (that dropped the rise and ended the
  clip at once).
- **Jump.** A jump while carrying plays the jump with the board from the stride's quarter (from a stand under
  150 cm/s), timed to the fall (0.6 to 1.4 times). A step off a ledge keeps the character's own pose, the board on
  the hand bone nearest to it.
- **Landing.** The landing clip is `BIG` after 0.9 s in the air or falling faster than 700 cm/s; `DN` 60 cm or more
  below the take-off, `UP` 30 cm above; `RUN_FWD` above 150 cm/s, at the jump's stride (25 or 75), otherwise `STAND`.
  Its travel is scaled to keep the landing speed.
- **Caveman.** The skate button in the air (a jump, with or without the board in hand, or after an air dismount): the
  board goes under the feet, the foot ahead first. The clip is timed to the fall (0.8 to 1.5 times). From the
  character's own pose its pelvis starts at the character's. Once the board touches the feet, the deck stays over the
  capsule, where the ride starts (the clip's board moving on moves the trajectory back). At its end the ride starts
  airborne when the ground is more than 70 cm below; closer, the feet stay on the board until the landing. Landing
  before the board is under the feet lands on foot holding it.
- **Carry.** The board stays in hand for `BoardHoldTime` (6 s), then dissolves in the hand while the character's own
  pose blends back (`CarryBlend`). It also goes as soon as the hands are needed (`ISkateRider::CanCarrySkateBoard`
  false: for example a sword drawn, a boat steered, swimming or an interaction). The walk, run and sprint cycles share
  one phase, which advances by the distance covered over the blended stride, so the feet keep to the ground. There is
  no back socket: a board is either in the hand, under the rider, lying, or gone. A board leaving a hand of the
  character's own pose for a clip's eases there over `ClipBlend`.
- **Board button** (`USkateComponent::RecallBoard`, the game's button, on foot; a `UFUNCTION`, so scripts can press it,
  `recall_board()` in Python):
  - with no board, one dissolves into the hand;
  - holding one, it is put away;
  - with one lying in the world, that one dissolves and a fresh one comes to the hand.
- **Run-out.** A slow, upright bail (the physical rider's `OnBailStart`, kind `RunOut`: see "Physical rider") is
  taken on foot: no ragdoll, the rider runs out of it. The clip is chosen by the way the board was going under the
  rider (on along its nose `FWD`, back along its tail `BWD`, across toward the toes `FF` or the heels `BF`), `HI` or
  `LO` by the crouch, and small, medium or big by the bail's energy (the largest of its speed over `RunOutSpeed`, its
  fall over `RunOutImpact` and its spin over `RunOutSpin`), one of the variants at random. The clip's board starts on
  the deck the rider bailed from and rolls with the clip; the body starts where it was, at the bail's speed, and
  follows the clip's turns. At the clip's end the board rolls on by itself like a kicked one.
- **Bail.** Otherwise the body falls (the physical rider). The skate button during the bail means "get up on foot":
  the rider gets up where the body lies with the `W_RECOVERY_*` clip whose first frame lies most like the fallen body
  (the head, hands, feet and the way the front faces, about the hips). The clip's pelvis is put on the body's and its
  first frame held until the physical rider hands its bodies to the animation (a frame or two, at most 0.3 s); the
  pose then rises out of the fallen body's (`BlendFromSnapshot`) over `RecoverBlend`. The board stays lying where it
  came to rest (`world`), a body of its own. A lying board dissolves after `BoardLyingTime` out of reach
  (`BoardReach`).
- **Step on.** The skate button next to a board lying on its wheels (within 130 cm, slower than a run): the stand mount
  plays from the moment its foot touches the deck, its board on the lying one (nose to nose or turned end to end,
  whichever puts the clip's body nearer the character's), and the capsule eases from rest onto the clip's path, over the
  deck by the clip's end. A mount while a board lies elsewhere, upside down or still moving removes it and uses a fresh
  board in the hand, and logs why the lying one was not stepped on (`SKATE ride no step on`).
- **Placement.** `PlaceAt()` gets on at once, without a clip (a scripted cut).

The tunables are in `skate.RideTune`: `MountBlend`, `DismountBlend`, `ClipBlend`, `CarryBlend`, `RecoverBlend`,
`MeshSettle`, `BoardDissolveTime`, `BoardHoldTime`, `BoardLyingTime`, `BoardReach`, `MomentumDecay` and
`MomentumBrake`. The dissolve is a masked material (`USkateSettings::BoardDissolveMaterial`), loaded once with the
clips; without it the board shows whole until it is gone.

The transition fields on the state line (`atelier live state`) are:
- `board=`, `shown=` and `vis=`;
- `hip=`, `deck=`, `vel=`, `offset=` (the mesh's offset from its on-foot place), `turn=` (its turn from its on-foot
  rotation, degrees) and `momentum=`;
- `foot=`, `clip=`, `t=`, `lift=` (the body standing on the deck, 0 to 1), `phase=`, `hold=`, `hand=` and `air=`
  (seconds in the air);
- `loose=` (a board on its own: `flying`, `settling`, `body` for the physical rider's box, or `-`) and `deckup=` (its
  deck's up, 1 wheels down, -1 upside down).

A game's transitions QA scenario checks them. `skate.RideTrace N` logs a line a frame from the frame before each switch
(a pose blend, the mode, the clip) to N frames after it: the actor, the mesh, and the pelvis and facing published and
shown, and the speed: the velocity, the acceleration, the character's own velocity before the momentum, the momentum,
the drive, the stick given to the next move and the speed the character may run at. `FAnimNode_SkateRider` adds a line
for each switch and blend request, and `FAnimNode_RideInertialization` one for each recache and each request it cannot
start (no previous pose): a cut. The inertialization also logs each reset that drops a blend or its stored poses, with
the reason (a teleport, new bones, a skipped update), and each blending frame: the pelvis's offset, where the source
and the blend put the pelvis in component space, and the root's source and blended transforms.
