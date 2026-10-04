# Ride

Ride is the skating backend (`skate.Backend Ride`, `USkateSettings::Backend`). A ride is Native's
`atelier::skate::GameplaySession` (the recovered C++ in `Source/AtelierSkate/Private/Native/`, described in
[RUNTIME.md](RUNTIME.md)) running on its own thread under Ride's Unreal body. Native simulates the board, reads the
controls, recognises the tricks, scores them, decides landings and bails, poses the rider and frames the camera. Unreal
hosts the ride in CharacterMovement, retargets Native's pose onto the game's character, makes that character an active
ragdoll with Chaos and Physics Control, takes over the body in a bail, gets it up, and plays the transitions on and off
the board from Native's clips. Ride's sources are in `Source/AtelierSkate/Private/Ride/`; the glue between Native and
Unreal is `Source/AtelierSkate/Private/SkateRuntime.cpp` and `SkateComponent.cpp`.

Native's own backend (`skate.Backend Native`: the session's pose with no physical body, no transitions and no Chaos
bails) is kept only as the reference that QA and replays compare the ride against. Games do not offer it to players.

Ride had its own board solver, an Unreal re-implementation of part of Native's riding. It was removed; commit
`479a895` is the last one that has it. [What a full port to Unreal would need](#what-a-full-port-to-unreal-would-need)
says what it covered.

## What runs where

"Native" is the session's code, which Unreal neither reads into nor changes during a step. "Unreal" is Ride, the glue
and the engine. Native's file names are its families in `Private/Native/` (see [RUNTIME.md](RUNTIME.md#systems)).

| Part | Runs in | What and where |
|---|---|---|
| Ride host | Unreal | CharacterMovement's custom mode (`MOVE_Custom`, `USkateComponent::MovementMode`). `PhysSkate` calls `StepRetailRuntime` (`SkateRuntime.cpp`), which steps the session, sets the actor on Native's root (plus the body's lift onto the deck) and the movement velocity to Native's, without a physics teleport. |
| Board physics | Native | The deck, two trucks and four wheels as rigid bodies with joints and drives, solved with the rider's bodies (`Board*`, `RigidBody`, `ConstraintSolver`, `Truck*`, `Deck*`, `Drive*`). Unreal only shows them: `PlaceBoardParts` puts the board meshes on the solved bones. |
| Collision world | Native, from Unreal meshes | Native's own world (`GameplayWorld`, `WorldGeometry`, `WorldContactProducer`), built from a snapshot of Unreal's static meshes that block `Pawn`: `CollectWorld` lists them on the game thread, `FillWorld` and `BuildGameplayWorld` make the triangles and the BVH off it. Budget 500,000 triangles: a 100 m cube, shrunk to 60, 35 or 20 m. The next snapshot is gathered when the rider leaves the inner 60% and installed between steps. See [The world](#the-world). |
| Rails and grinds | Native | Grind selection, balance and forces (`Grind*`, `PlayerGrind*`, `Slide*`) on polylines made from the `USkateRailSubsystem` rails within the snapshot. A game registers its rails; their kind, side and radius are not used. |
| Input mapping | Unreal, then Native | `USkateComponent::ReadInput` and `ReadHostPad` sample the controls into an Xbox-style packet (`SkatePad.h`); Native maps it to intents (`ControllerInputRuntime`, `PlayerControls`, `InputIntentions`). |
| Flick recognizer | Native | Flick-It gestures and the action graph (`Gestures`, `GestureInputPublication`, `GraphGestureOperations`, `ActionGraphFrame`). |
| Tricks, score, trick line | Native, labels in the glue | Native names and scores tricks and combos (`Scoring*`). The glue renames for display: `TrickLabel` (`Kickflip`, `Nollie`, `50-50`, `Pop Shove-it`), the `Fakie` or `Switch` prefix from the trick's start stance, `NameNativeSpin` (an air spin from the root's yaw, at least 150 degrees, shown as `Trick / FS 360`), a successful pump as `Pump` (U121), and `RideGrab` (the grab held, for an air dismount). |
| Manuals | Native | `Manual`; the balance is published for the HUD. |
| Pumping | Native | `Pumping`, `GroundPumpingRuntime`. The session counts successful pumps and their gain; one that adds at least `skate.PumpTrick` (0.5 m/s) shows in the trick line. |
| Airs, spins, grabs | Native | Take-off trajectories, spins, flips and grabs (`Air*`, `KnownAir*`, `BodySpin`, `BodyFlip`). |
| Landing and bail decisions | Native | Landing prediction and quality (`LandingDeck*`, `LandingOnDeck*`, `LandingQuality`) and the wipeout rules (`Wipeout*`). The glue reads a state name containing `Wipeout` as a bail. |
| Bail kind | Unreal | `ClassifyBail` (`RidePhysicalRider.cpp`): a run-out on foot when tilted under `RunOutTilt` (35 degrees), with the feet 20 cm below the hips, slower than `RunOutSpeed` (450 cm/s) across, `RunOutImpact` (300 cm/s) down and `RunOutSpin` (200 degrees/s); otherwise a ragdoll fall. |
| Bail ragdoll | Unreal | The rider's own Chaos bodies (`URidePhysicalRider`), limp under Physics Control's `Bail` profile, inside a joint envelope taken from Native's bail limits (`BailJoints`). |
| Board during a bail | Native, then Chaos | The session goes on with its wipeout and a Chaos box is placed on Native's board every frame; it is released to Chaos with Native's motion. See [Bails](#bails). |
| Get-up | Unreal | The body's snapshot blends into a get-up clip (`BlendFromSnapshot`); `GetUpFromNativeBail` (`RideComponent.cpp`) starts the next ride on a fresh session where the body lies. |
| Mount, dismount, carry, run-out, kick-out, caveman, step-on | Unreal | `RideTransition.*`: Native's clips played by Ride's clip player (`FRideClipPlayer`, `RideClipPlayer.h`) and retargeted like a ride. See [Transitions](#transitions). |
| Native's on-foot states | Native, handed to Unreal | When Native's rider leaves the board on foot by itself (`BipedGround` for 0.2 s outside a bail or get-up), `TakeNativeOnFoot` (`RideComponent.cpp`) suspends the session, puts the character on its feet with the rider's velocity and lets the board roll on from Native's deck (U120). |
| Riding pose | Native, then Unreal | Native's motion graph and animation (`MotionGraph*`, `RidingAnimation*`, `Skeleton*`, `Footplant*`, `FootIk*`) give the pose; `RetargetRetailPose` (`SkateRuntime.cpp`) fits it onto the character; `FAnimNode_SkateRider` shows it with inertialization. See [Rider pose](#rider-pose). |
| Active ragdoll | Unreal | `URidePhysicalRider` and `URidePhysicsControl`: the character's bodies follow the retargeted pose. See [Physical rider](#physical-rider). |
| Camera | Native while riding | Native's camera (`Camera*`, `GrindCamera`), returned by `GetRetailCamera`. In a Chaos bail it returns nothing and the game's own camera follows. The game converts the vertical FOV and blends its own camera in and out. |
| Audio | Unreal | `USkateComponent::UpdateAudio` loops roll, grind, slide, skid and scrape by mode and speed; one-shots play on Native's changes of mode (`pop` on take-off, `land`, `clatter` on a bail). The push, flick, catch and fall sounds are loaded but not played (H62). |
| HUD | Unreal, from Native's data | `GetStatus`, `GetComboLine`, `GetComboAlpha`, `GetScore`, `GetSpeed`, `GetCameraYaw` read the published state, trick line, score, stance and velocity. |
| Threading and lockstep | Native thread, Unreal commands | `FNativeSkateWorker` (thread `AtelierSkateNative`, 32 MiB stack) owns the session; the game thread sends typed commands and reads the published pose. See [Threading and lockstep](#threading-and-lockstep). |
| Fresh and spare sessions | Glue | Every ride starts on a new session made ahead. See [Fresh sessions](#fresh-sessions). |
| World centring | Glue | `SnapshotCentre`: the 10 m cell or a park's origin. See [The world](#the-world). |

## How much is ported to Unreal

Measured with `wc -l` on this tree, headers included:

| Code | Files | Lines | What it is |
|---|---|---|---|
| `Private/Native/` | 767 (410 `.cpp`, 357 `.h`) | about 59,000 (43,039 + 15,982) | All of the riding, as recovered |
| `Private/Ride/` with the solver (`479a895`) | 23 | 11,492 | The body, bails, get-up, transitions and the solver |
| of which the solver's own files (`RideSession.*`, `RideFlick.*`, `RideManual.*`, `RideNative.cpp`, `RideSpeedModel.*`) | 9 | 3,555 | Removed; about 4,000 with its parts of `RideTuning.*`, `RideComponent.cpp` and `RideAnimator.*` (inferred) |
| The glue (`SkateRuntime.cpp`, `SkateComponent.*`, `SkatePad.h`, `AnimNode_SkateRider.*`, `AnimNode_RideInertialization.*`, `SkateRails.*`, `SkateSettings.*`, `SkateInput.h`, `SkateRider.h`) | 15 | about 3,700 | Hosting, snapshot, threading, retarget, audio, HUD |

"Ported" here means Unreal code does the job and Native's version of it does not run. By that measure the ride's
**body** is ported: the active ragdoll, the bail ragdoll, the get-up, the transitions on and off the board, the
retarget, the inertialization and the audio are Unreal's. Its **riding** is not: every decision that makes it skating
(board dynamics, contacts, grinds, flicks, manuals, pumping, airs, landings, bail rules, scoring, the riding pose's
choice of clips, the camera) is Native's code running inside Unreal's process. Unreal feeds it controls, collision and
rails and reads back a pose.

## What a full port to Unreal would need

A full port replaces each Native system with Unreal code and the session with Unreal objects. The table gives, per
subsystem, the Native code involved (measured: `wc -l` over the family's files; families overlap a little, so the rows
do not add up), what the removed solver had at `479a895` and how faithful it was (measured where a test or the gap
audit says so), and what a port needs (inferred).

| Subsystem | Native code | The removed solver | A port needs |
|---|---|---|---|
| Board dynamics | `Board*`, `RigidBody`, `ConstraintSolver`, `Contact*`, `Joint*`, `Drive*`, `Truck*`, `Deck*`, `AssemblyContacts`, `AggregateMass`, `SpeedWobble`: 73 files, about 4,900 lines | One rigid board on the game thread at 60 Hz against Unreal sweeps, not Native's seven bodies: ground follow with a 15 cm step, a crest window and a launch factor; a speed model (`RideSpeedModel`: a gain, a 7 m/s² gravity limit, a 25 m/s² load-free limit); the push (`PushDvStart` 0.6 against Native's 0.5). Not bit-equal; its paths differed from Native's by place. | Either Native's seven-body assembly on a custom integrator (comparable tick for tick with the reference) or Chaos bodies and constraints (comparable only by outcome). The truck drives and wheel contacts decide the feel. |
| Collision | `Geometry*`, `WorldGeometry`, `WorldContact*`, `WorldPrimitive*`, `CollisionBody`, `GameplayWorld`: 23 files, about 2,400 lines | Unreal sweeps (a box and wheel-sized shapes) against the scene. | Contacts from Unreal queries instead of a snapshot, with physical materials mapped (the snapshot has one). Removes the snapshot, its budget and its rebuilds. |
| Grinds | `Grind*`, `PlayerGrind*`, `AirTrajectoryGrind*`: 52 files, about 3,500 lines | Grind capture within 30 cm, from up to 40 cm above, at up to 65 degrees across; 50-50, 5-0 and slides; lip airs on coping. Partial in the gap audit. | Rail selection, balance and forces on Unreal splines; `USkateRailSubsystem` would carry kind, side and radius. |
| Input and flick recognizer | `Controller*`, `Input*`, `Intents`, `PlayerControls`, `PlayerInput*`, `Gesture*`, `GraphGesture*`: 26 files, about 3,400 lines | The Flick-It chain as a translation (`RideFlick`: `ControllerInputRuntime::Sample`, `PlayerControls::Update`, `PublishGestures`, `SelectGestureTrick`). Measured bit for bit with Native over a recorded 1,573-tick replay (`Tests/Native/ride_input_replay_probe.cpp`: the packet equal on 1,461 rolling ticks, the owners bit for bit, six tricks). Gaps: no action graph, so the pop was timed by hand; the physical capabilities and state were fed 0. | The action graph, or an Unreal state machine standing in for it, driven by the recognizer's gestures; the recognizer itself ports as a translation. |
| Manuals | `Manual*`: 2 files, 174 lines | `RideManual`: `CalculateManual`'s balance PID. Measured: the manual ended one tick before Native's balance cleared. | A translation; small. |
| Pumping | `*Pump*`: 4 files, 213 lines | `UpdateGroundPumping`, with the crouch height and a pump angle of 0. | A translation; it reads the rider's crouch from the riding pose. |
| Airs, spins, landing | `Air*`, `KnownAir*`, `Landing*`, `BodySpin`, `BodyFlip`: 63 files, about 4,300 lines | Spins (`BodySpin`), flips through the clips, bad-landing limits, a landing predictor. Measured: `BailImpact` 13.5 against Native's 11.2; `BailGrindImpact` 8. | Trajectory selection, air control, landing prediction and quality; tied to the board bodies and the motion graph. |
| Bail decisions | `Wipeout*`: 32 files, about 1,500 lines | Curb bails at 7.1 m/s (impact 60), wall bails at 8 m/s, bad landings, a danger zone. | The wipeout requests and prediction; the ragdoll part is already Unreal's. |
| Riding pose | `ActionGraph*`, `Graph*`, `CompiledGraph`, `MotionGraph*`: 52 files, about 5,800 lines; `Animation*`, `SkaterAnimation`, `RidingAnimation*`, `GroundAnimation*`, `BoardAnimation`, `MotionAnimation*`, `Footplant*`, `FootIk*`, `Skeleton*`, `PhysicsSkeleton`, `PhysicsAnimation*`: 135 files, about 10,400 lines | A C++ anim graph (`USkateRideAnimInstance`: four explicit-time sequence evaluators, a multi-way blend, a mirror, inertialization) choosing clips from the solver's state, with the fakie channel, the switch turn and the air legs. Missing: Native's physical feedback (crouch and tilt) and the spin overlays (U111). | The motion graph as an AnimGraph or C++ state machine with its blend trees, the procedural layers (feedback, spin channels, foot IK, footplants) and the physical skeleton's targets. The largest part. |
| Scoring | `Scoring*`: 15 files, about 1,500 lines | Trick names and a simple combo. | A translation of the catalogue, combos and timers. |
| Camera | `Camera*`, `GrindCamera`: 26 files, about 5,500 lines | One follow shot. | Native's shots per state (air, grind, bail), tracking and effects as Unreal camera modes (G7). |
| Off the board, handplants, climbing | `Biped*`, `Offboard*`: 83 files, about 4,400 lines; `Climbing*`, `Handplant*`: 21 files, about 1,600 lines | None; Ride's transitions play the off-board clips. | Only what a game wants beyond the transitions (G10, G18). |
| Session, settings, respawn | `Gameplay*`, `PlayerState*`, `Settings`, `StockSettingsReader`, `Respawn*`, `Revert*`, `Teleport*`, `SessionMarker*`, `NativeMath`, `NetworkProxies`: 48 files, about 4,200 lines | The solver's own session (`FRideSession`). | The riding state machine as Unreal objects; the data readers stay. |

The gap audit of the solver against Native counted 183 features: 49 present, 50 partial, 66 missing, 8 unverified and
10 not applicable (measured by reading both codes). To recover the solver, take `Source/AtelierSkate/Private/Ride/` and
`Tests/Native/ride_input_replay_probe.cpp` from `479a895`, with `skate.RideSolver` in `SkateRuntime.cpp` and the
solver's branches in `RideComponent.cpp` (`StepRide`, `AfterRideFrame`).

Suggested order (inferred): board dynamics and collision together, since every other system reads their contacts;
then input with the action graph, so tricks start from the recognizer rather than hand timing; then the ground moves
(push, steering, pumping, manuals, powerslides); airs and landing; grinds; bail decisions; scoring; the riding pose;
the camera last, since it only reads. After each step, replay the same recorded pad on the Native backend and on the
port: bit for bit where the port is a translation, by outcome (tricks, landings, bails, places within a tolerance)
where it runs on Chaos.

## Native's session under Ride's body

### Fresh sessions

Every ride starts on a new session, made ahead on no world (`CreateBlank`, about 40 ms on its own thread; two are kept
spare), which takes over the collision of the one before (`AdoptWorld`). The same controls from the same place ride
the same way whatever was ridden before. The swap at a mount takes 0.7–1.8 ms. A trick shown at the end of one ride is
hidden on the next until it changes.

### The world

The collision snapshot is centred on the 10 m cell the rider is in, or on the origin of an actor tagged `SkatePark`
when the cell is within 60 m of it (`SnapshotCentre`), so a place always gets the same triangles in the same order.
Complex-as-simple meshes give their collision triangles; others their boxes, spheres, capsules and convex hulls.
Instanced meshes count; the rider's own components do not. The snapshot is rebuilt off the game thread when the ride
nears its edge or, on foot, when the rider changes cell; in lockstep (QA, replays) a mount on another place's world
gathers its own at once. Over open water, where there is nothing to snapshot, the old one stays and the rebuild is
retried 20 m further on. Moving objects, skeletal and procedural meshes and streamed-out terrain are not in it.

### Threading and lockstep

The session runs on `AtelierSkateNative` (32 MiB stack), which owns every mutable simulation object, in the standalone
runtime's floating-point environment (the defaults, denormals flushed to zero; `FScopedNativeFloatEnvironment`
restores the caller's afterwards). The game thread sends `Activate`, `Configure`, `Step`, `World`, `Launch` and
`Suspend` commands and reads back the root, bones, velocity, state, trick, stance, score, pumps, manual balance and
camera; one step is in flight at a time. Each step carries the frame time and the session runs whole 60 Hz ticks.
Each activation carries a generation number, so a previous ride's output never moves a new one.

`skate.Lockstep` (-1, the default: on under a fixed time step or frame rate; 1 always; 0 never) makes each frame wait
up to 2 s for the last step, so the same controls ride the same way. A mount waits for the session's first pose.

### Bails

A Native wipeout hands the rider to the Chaos body (`AfterNativeRideFrame`, `OfferBail`): a run-out plays on foot, a
fall goes limp, and the actor follows the body's ground (`GetBodyGround`). The session goes on with its wipeout,
controls neutral. The loose board (a 3.5 kg Chaos box) is placed on Native's
`SKATEBOARD_ROOT` each frame, trucks and wheels included: it rolls on and catches on edges as on the Native backend
(within 1 cm of it at 1 s in the reference bails). It goes to Chaos with Native's motion when the state no longer
contains `Wipeout` (Native's recovery teleports its rider), when it would jump further than its speed takes it
(50 cm plus twice its speed times the time since the last frame), when the session fails, or at the get-up.

When the body has settled, or went unstable, `GetUpFromNativeBail` gets up where it lies and starts the next ride on a
fresh session there. A board lying on its wheels within 60 cm (`GetUpBoardReach`) is stepped onto; any other dissolves
out where it lies and a board dissolves in under the feet.

### Failures

A session error never stows the board under a moving rider (`skate.FailNative 1` forces one): the body bails with the
momentum shown and `RelaunchNativeRide` loads a fresh session off the game thread while it falls. Two failures in a
row (a failure during the get-up) stow the board (H23).

### Modes and display

The glue reads Native's state name: a `Wipeout` state is a bail, a `Grind` state a grind, an `Air` state the air,
anything else the ground. `SlideGround` loops the powerslide sound; `GrindBoardslide`, `GrindTipslide`,
`GrindDarkslide` and `GrindLipslide` the slide. Rolling fakie and riding switch come from the session's published
stance (`riding_switch`, `fakie`).

## Rider pose

`RetargetRetailPose` (`SkateRuntime.cpp`) fits Native's skeleton onto the character through the bone contract
(`ISkateRider::GetSkateBone`): it scales the pose by the hip-to-foot height ratio, keeps the character's bind bone
lengths, solves both legs with two-bone IK to Native's feet, traces the feet to the ground (`skate.FootGround`,
0.5 cm), keeps the arms clear of the body outside bails (`ClearArms`, `skate.ArmClear`, 2 cm), and in a grab hooks the
hand under the board's nearest edge (`skate.Grip`). The result is `GetRetailPose()`, which `FAnimNode_SkateRider` in
the character's graph shows; a switch between the character's own animation and the ride's pose blends through
`FAnimNode_RideInertialization` (`Public/AnimNode_RideInertialization.h`).

- **Inertialization.** A change of pose carries on from the last frames with their velocity and settles onto the new
  one on a quintic curve per bone (Bollo, "Inertialization", GDC 2018). The engine's `FAnimNode_Inertialization` and
  `FAnimNode_DeadBlending` report to Animation Insights through Anim Blueprint node data, which a graph built in C++
  does not have (an editor build asserts in `GetNodeIndex`). Our node takes requests through
  `IInertializationRequester` graph messages, with blend profiles as per-bone time factors. With `MaxSpeed` set, a
  request between poses far apart lasts at least 1.875 times the largest component-space gap over `MaxSpeed`, at most
  `MaxDuration` (0.25 s). It keeps its stored poses across a recache of the same bones, which the physical rider's
  physics asset swap causes.
- **State line** (`USkateComponent::GetRetailState`, `atelier live state`): it gives the backend, the tick, the
  controls sent (`pad=`), the collision snapshot (`world=`, its cell and triangles), the step's cost, the spin, the
  wheels, the bail, the pumps (`pump=` count and last gain) and the arm clearance (`arm_swing=`, `arm_need=`), then the
  physical rider's and the transitions' fields.

## Physical rider

While riding, the rider is an active ragdoll (`skate.RidePhysical 1`, the default): the bodies of its physics asset
simulate in the world's Chaos scene, Physics Control drives them toward the retargeted pose, and the board holds the
feet. The bail lets the same bodies go limp, and the get-up blends from a snapshot of the fallen body into the get-up
clip. `skate.RidePhysical 0` shows the pose alone, with a ragdoll only for bails.

### What the reference rider does

These come from Native's traces, comparing its published pose with its animation pose. They are tuning targets and QA
tolerances; the implementation is ordinary Unreal code, not a port.

| Situation | Published pose versus animation |
|---|---|
| Rolling, carving, powerslide, manual, grind | upper body within 0.5 cm (p95); feet held on the deck, 6–8 cm from the animated feet |
| Ollie and drop landings | the hips stay within 1–4 cm; the compression is in the clips |
| Knocks that do not bail (wall at 5 m/s) | the hips move up to 6 cm |
| Bail | continuous, with no jump: 8 cm at 0.125 s, 8–26 cm at 0.25 s, 14–37 cm at 0.5 s, 64–127 cm at 1 s |
| Bail travel (the pelvis) | the entry speed times 1.0–1.4 s, at any speed; a bail into a wall stops at it |

The rider is therefore stiff while riding: what you see is the animation, a body that carries its momentum through
knocks and landings, and feet that stay on the board.

### Unreal mapping

- **Code.** `URidePhysicalRider` (`RidePhysicalRider.h`) is owned by `USkateComponent` as `PhysicalRider`. The ride
  drives it each frame from `AfterNativeRideFrame` (`RideComponent.cpp`), after the step and before the mesh animates.
  With no ride step (transition clips on foot, a get-up that outlives the ride) it ticks itself in the `OnFoot`
  profile.
- **Bodies.** The mesh's own physics asset when it has six or more bodies (`RideConstraintProfile` riding,
  `BailConstraintProfile` in a bail); otherwise an asset built from the bone contract: 16 bodies, each fitted to the
  skin it carries (the convex hull of its vertices in 256 directions, `bFitBodiesToSkin`), with human joint ranges and
  a kinematic root body. While riding, a limit the animation passes widens to it; a bail puts each joint back. Joint
  ranges in degrees:

  | Joint | Flexion / extension | Abduction / adduction | Twist |
  |---|---|---|---|
  | Lower back | 40 / 20 | 20 / 20 | 15 |
  | Upper back | 40 / 15 | 20 / 20 | 25 |
  | Neck | 50 / 55 | 40 / 40 | 60 |
  | Shoulder | a 110 cone round the arm out and a little forward | | 60 |
  | Elbow | 145 / 5 | 8 / 8 | 40 |
  | Wrist | a 70 cone | | 45 |
  | Hip | 120 / 25 | 45 / 30 | 40 |
  | Knee | 140 / 5 | 8 / 8 | 15 |
  | Ankle | 50 down / 20 up | 15 / 15 | 25 |

  In a bail the bodies meet each other, except a joint's two bodies and two that overlap in the bind pose; two that
  overlap in the bail's first pose meet again once 1 cm apart. `skate.RideSelfCollision 0` lets them pass.
- **Bail envelope.** In a bail each joint closes, at `skate.RideBailTightenRate` (120 degrees/s), onto Native's bail
  limits (`BailJoints`, from Native's physical skeleton and `WipeoutRagdoll`: a cone of the skeleton's swing times the
  bail multiplier times 0.5, at least 0.01; the twist times 0.6), with hard limits. `skate.RideBailTighten`,
  `skate.RideBailProjection` (0.8) and `skate.RideBailDriveFade` tune it.
- **Controller.** `URidePhysicsControl` (a `UPhysicsControlComponent`) makes parent-space controls on every joint
  (`Joints_Spine`, `Joints_Arms`, `Joints_Legs`), anchors on every body relative to the kinematic root body
  (`Anchor_Pelvis`, `Anchor_Feet`, `Anchor_Hands` the strong ones) and a body modifier per body. Targets come from the
  mesh's animated pose; an update with no component-space pose is skipped. The ride moves the actor with
  `ETeleportType::None`.
- **Phases.** Profiles `Riding`, `Air`, `Landing`, `Grind`, `Manual`, `Bail`, `GetUp` and `OnFoot`, built from
  `URidePhysicalSettings` (Project Settings › Plugins › Skate Physical Rider; `skate.RidePhysicalReload` rebuilds
  them). Strengths: pelvis anchor 16 Hz (damping ratio 0.5), feet 12 Hz, joints 10 Hz, an 8 Hz anchor on every body,
  gravity 0 while riding. `Bail` lets go of every anchor, turns gravity on and leaves the joints a 3 Hz tone.
- **World.** Query-only surfaces within `WorldRadius` (12 m) of the body become physical while it simulates, following
  it every 6 m; instanced meshes with more than 64 instances are left alone. The rider wants Chaos substepping at
  `MaxSubstepDeltaTime` 1/120 with up to 4 substeps.
- **Bail.** `StartBail` lets the bodies go with their momentum and applies the `Bail` profile at once
  (`skate.RideBailApplyNow`; at Physics Control's next update instead, the anchors braked a 6 m/s bail to 1.6 m/s in a
  frame). The bodies slide with `BailFriction` 0.06 and, with the pelvis within 50 cm of the ground, `BailDrag` 1.5/s
  ramped in from 0.7 to 1.1 s, so a slide's length grows with its speed as the reference's does. A body that gains
  speed or height it was never given, or falls through a floor, is unstable and ends the bail. `skate.RideBailTrace N`
  logs the bail's first N frames.
- **Get-up.** When the body has settled (still for 0.4 s, after at least 1.6 s), its pose snapshot blends into the
  clip over `GetUpBlend`, lifted so that no bone or body goes lower than the lower of its two ends. The bodies stay
  simulating until Physics Control's pelvis and head are within 10 cm of the snapshot (at most five frames).
- **Debugging.** The Chaos Visual Debugger records the bodies, controls and contacts. The state line ends with the
  phase, the physics weight, the pelvis, feet and worst body's distance from the animation, the bail's `lie` and
  `drag`, the get-up blend, the last bail's kind and the skipped updates. `skate.RideJointCheck`,
  `skate.RideSkinCheck 1` (the skin's depth under the ground and `hand_gap`) and `skate.RidePhysicalDump` add
  measurements.

### Measured

A rider with the built asset (17 bodies) on scripted runs; distances to Physics Control's copy of the animation, p95.
Rolling at 0–10 m/s: pelvis 0.3–0.6 cm, feet 0.4–0.7 cm. Hard carve at 8 m/s: 3.3 and 3.2 cm. Grind: 4.8 and 4.7 cm.
Quarter pipe: 7.7 and 5.7 cm. 3 m drop: 4.8 and 2.9 cm. A bail on flat at 6 m/s travels 0.90 times the entry speed in
the first second and comes to rest at 1.24–1.26 times (the reference: 0.97–0.98 and 1.04–1.16). In bails the worst
joint stays within 1.5–8.4 degrees of its range and two bodies meet at most 2.9 cm deep. Skin under the ground with
the fitted hulls: at most about 1 cm sliding and lying, 0.7–2.6 cm for the feet getting up. Frame cost with the
physical rider on and off is within the noise (p99 17.11 against 17.17 ms riding a park road). These were measured
on the removed solver's board; the body code is the same under Native's board.

### Why the component and not RigidBodyWithControl

`FAnimNode_RigidBodyWithControl` simulates bodies on the animation thread in a private scene that sees the world only
through copied shapes. The bail would then either tumble in that scene, with no contact with the loose board or moving
props, or hand its state over to world bodies, a discontinuity exactly where the reference has none. The component
drives the mesh's own bodies in the world scene, so riding, bail and get-up are one continuous simulation against real
contacts. Its cost is game-thread updates for about 32 controls.

## Transitions

Getting on and off the board (`RideTransition.*`, `USkateComponent`) keeps one continuous character; the actor is
never moved to a new place. The capsule changes size about its centre, the mesh keeps its world place across each
switch and eases back onto the capsule over `MeshSettle`, the pose switches by inertialization
(`FAnimNode_SkateRider`, on a `RequestPoseBlend`), and the speed carries over both ways. The Native backend switches
at once.

Off the board, Native's clips play through Ride's clip player (`FRideClipPlayer`, `Private/Ride/RideClipPlayer.h`).
The clip's `TRAJECTORY` is put on the capsule's floor and the pose is retargeted like a ride's
(`PublishOffBoardPose`). On the ground a clip moves the capsule along its root motion through an override root motion
source (`SkateDrive`); in the air CharacterMovement keeps the fall. `IsRiding()` is true while a clip plays. Every
hand-off to a ride starts the session on the floor under the deck, never inside it: one wheel-sized sweep under the
board settles the start onto the floor (`SettleRideStart`, `RideComponent.cpp`).

| State (`foot=`) | What plays | Board (`board=`) |
|---|---|---|
| `off` | the character's own animation | `away` (dissolved), or `world` (lying) |
| `carry` | `BR_STAND_0_CYC`, `BR_WALK_FWD_CYC`, `BR_RUN_FWD_CYC`, `BR_SPRINT_FWD_CYC`, blended by speed | `hand` |
| `mount` | `BR_STAND_0_INTO_MOUNT`, or `BR_{WALK,RUN,SPRINT}_FWD_{0,25,50,75}_INTO_MOUNT` by speed and stride | `hand`, then `ride` |
| `dismount` | `BR_DISMOUNT_{HI,LO}_INTO_STAND_0`, `BR_DISMOUNT_{HI,LO}_INTO_RUN_FWD` or `BR_DISMOUNT_FAST_{HI,LO}_INTO_RUN_FWD`, then the carry | `hand` |
| `air` | a jump with the board (`JBR_*`); an air dismount from a grab (`BR_DISMOUNT_{FS,BS,STALE,DBL,MUTE}_INTO_BR_AIR`); a kick-out (`BR_KICKOUT_{HI,LO}_INTO_NB_AIR`) | `hand`; kicked, `world` |
| `land` | `BR_LAND_{SML,BIG}_{DN,FWD,UP}_*` | `hand` |
| `airmount` | `BR_{LF,RF}_AIR_INTO_MOUNT_BSGRAB` (a caveman) | `hand`, then `ride` |
| `runout` | `RUNOUT_{FWD,BWD,FF,BF}_{HI,LO}_{S,M,B}<n>_TO_RUN_FWD` | `world` (rolling on) |
| `recover` | `W_RECOVERY_ON{BACK*,FRONT,LEFT,RIGHT*}_N_0_N` (a get-up on foot where the body lies) | `world` (lying) |

- **Mount.** The skate button on the ground; the gait by speed (standing under 80 cm/s, a walk under 350, a run under
  620, a sprint above), the variant by the quarter of the stride. At the clip's end the ride starts on the clip's deck
  at the clip's speed.
- **Dismount.** The skate button on the ground: `FAST` above 600 cm/s, `RUN_FWD` above 150 cm/s or with the stick
  held, `STAND_0` otherwise; `LO` crouched, read from Native's hips over the deck (below 60 cm; riding is 80-90 cm, a
  crouch 30-50), as for the run-out and the kick-out. Rolling fakie the rider steps off facing the other way. Speed left over
  runs on as momentum that fades (`MomentumDecay`, `MomentumBrake`).
- **Air dismount and kick-out.** The skate button in the air: with a grab held (`RideGrab`: Indy `FS`, Melon `BS`,
  Christ air `STALE`, tuck knee `DBL`, a one-foot `MUTE`) the rider steps off holding the board; without one the feet
  kick the board away and it flies on as a projectile, settling flat.
- **Caveman.** The skate button in a jump: the board goes under the feet; the ride starts airborne when the ground is
  more than 70 cm below.
- **Carry.** The board stays in hand for `BoardHoldTime` (6 s), then dissolves. It goes at once when the hands are
  needed (`ISkateRider::CanCarrySkateBoard` false) or when the character uses a move the carry has no clip for, such as
  a sprint, a double jump or a dash (U122).
- **Board button** (`RecallBoard`, `recall_board()` in Python): a board to the hand, the held one away, or a lying one
  replaced.
- **Run-out.** A `RunOut` bail is taken on foot: the clip by the board's way under the rider, the crouch and the bail's
  energy; the board rolls on.
- **Bail.** The skate button during a fall gets up on foot where the body lies, with the `W_RECOVERY_*` clip whose
  first frame is most like the fallen body; the board stays lying and dissolves after `BoardLyingTime` out of
  `BoardReach`.
- **Step on.** The skate button next to a board lying on its wheels (within 130 cm, slower than a run) plays the stand
  mount onto it.
- **Placement.** `PlaceAt()` gets on at once, without a clip.

Tunables (`skate.RideTune Name=Value`, names as in `RideTuning.h`): `MountBlend`, `DismountBlend`, `ClipBlend`,
`CarryBlend`, `RecoverBlend`, `MeshSettle`, `BoardDissolveTime`, `BoardHoldTime`, `BoardLyingTime`, `BoardReach`,
`MomentumDecay`, `MomentumBrake`. The dissolve uses `USkateSettings::BoardDissolveMaterial`. The state line's
transition fields are `board=`, `shown=`, `vis=`, `hip=`, `deck=`, `vel=`, `offset=`, `turn=`, `momentum=`, `foot=`,
`clip=`, `t=`, `lift=`, `phase=`, `hold=`, `hand=`, `air=`, `loose=` and `deckup=`. `skate.RideTrace N` logs every
frame from the frame before each switch to N frames after it; `FAnimNode_SkateRider` and
`FAnimNode_RideInertialization` log their switches, requests, recaches and resets.

## Testing

- **Reference.** `skate.Backend Native` rides the same session with no body, transitions or Chaos bails. QA rows and
  replays run on both backends and compare the board's path, the state names, the tricks and the outcomes. Two runs of
  the same replay on the ride match to the bit on the board; the body after a Chaos bail does not (H61).
- **The game's QA scenarios** drive the ride through the live bridge: riding rows on both backends, the transitions,
  and a replay of a recorded session (the pad, packet by packet, in lockstep).
- **Native's own tests** (`Tests/Native/`, [RUNTIME.md](RUNTIME.md#verification)) check the session bit for bit
  against the recovered implementation.
- **Console variables.** `skate.Backend` (`Ride` or `Native`, from the next mount), `skate.FailNative 1` (the session fails, to test recovery), `skate.RidePhysical` (0: no
  active ragdoll), `skate.Lockstep` (-1, 0 or 1), `skate.PumpTrick` (the m/s one pump must add to show as `Pump`, 0.5), `skate.RideTrace N`, `skate.RideBailTrace N`,
  `skate.RideJointCheck`, `skate.RideSkinCheck 1`, `skate.RidePhysicalDump`, `skate.RideTune`.

## Known gaps and bugs

Open or partly open, for the ride as it is. "Where" is where to start looking. "Fixed, to playtest" means the code is
in but no one has ridden it yet.

| ID | Symptom | Known cause | Where |
|---|---|---|---|
| H11 | Frame pacing p99 17.1 ms (limit 17) and a worst frame of 38.5 ms in the transitions run | Not the snapshot gather, which is off the game thread; unknown | Frame traces around mounts; `CollectWorld`; the transitions |
| H23 | Native maths on the game thread runs outside the floating-point scope; two session failures in a row (one during the get-up) stow the board | The scope covers the worker's calls only | `FScopedNativeFloatEnvironment` callers in `SkateRuntime.cpp`; `RelaunchNativeRide` |
| H26 | Hands inside the thighs at rest: the main rider -7.8 / -4.3 cm, a second rider -5.2 cm | Native's idle pose on our riders' proportions; `ClearArms` runs on Native's pose, but whether it covers this case is unchecked | `RetargetRetailPose`, `ClearArms`, the `arm_need=` field |
| H29 | The board inside geometry: 19.3 cm into a wall in a run-out carrying the board; one frame 104 cm past a floor at a corner | The run-out case is the transition's carried board, not Native's; the floor case is unexplained | The run-out in `RideTransition.cpp`; the snapshot near thin meshes |
| H30 | A 360 hardflip onto a rail lands into a 5-0 5 cm from the rail's line, then bails | Unknown: Native's own outcome or the rail's polyline | Rail registration, `Grind*` |
| H35 | A foot joint goes 1.8–3.5 degrees past its range in the joint check | Unknown | `skate.RideJointCheck`, `BailJoints` |
| H37 | A quarter pipe's straight air is not repeatable (an occasional 70-degree yaw on the face, a bail at the landing) | Possibly fixed by fresh sessions; to measure again | The same launch repeated on both backends |
| H43 | A grind's exit at the end of a long ledge drifts outward; the board yaws 15–20 degrees on the lock | Unknown: Native's grind exit or the rail's end | The rail's polyline and end, `Grind*` |
| H44 | Filmed boardslides over-rotate | The film script predicts the spin with the removed solver's model; Native turns 98–120 degrees for a 70–88 degree target | The film script's spin model |
| H60 | Replays on the ride started two rest steps later than on the Native backend | The replay harness counted the ride's frames from the body's mount; fixed in the harness (it starts at the session's own settle), to confirm | The game's replay scenario |
| H61 | Two identical replays match on the board, but the body after a bail differs by up to 13.7 cm | The Chaos ragdoll is not repeatable across runs (inferred) | `StartBail`, the Chaos settings |
| H62 | No push foot-scrape, flick, catch or fall sounds while riding; only `pop`, `land` and `clatter` play, on changes of mode | The cues came from the removed solver's cue list; a fix needs a push-contact signal (and flick and catch events) from Native | `USkateComponent::PlayCue`, `AfterNativeRideFrame`, Native's `Push` and `PUSH_CONTACT` |
| H63 | The "Rolling fakie" and "Rolling switch" status read the removed solver's idle state, not Native's stance | Fixed: `GetStatus` reads the stance shown (`ShownSwitch`, `ShownFakie`, from Native's `riding_switch` and `fakie`), to playtest | `USkateComponent::GetStatus` |
| U119 | Hard to lock into a grind, and a grind loses much speed | Investigating: grinds are Native's own, so a difference would come from what the session is given (rails, collision, input) | The same rail on both backends |
| U120 | After losing the board, getting back on could move the character 4–12 m at once | The actor followed Native's root while Native's rider walked away from the board; fixed by handing Native's on-foot states to the character (`TakeNativeOnFoot`), to playtest | `RideComponent.cpp` |
| U121 | A successful pump did not show in the trick line | Native scores no pump; fixed (the session counts pumps, `skate.PumpTrick`), to playtest. QA: the timed bowl pumps show `Pump` and `Pump x2` (0.6 m/s a rise); the mistimed row's rises that gain speed show too (0.5-0.67 m/s each), although that row ends slower than coasting, so the count is per rise, not per line | The trick line in `SkateRuntime.cpp`, `pump=` |
| U122 | On foot after a get-up, sprint, double jump and dash stayed off while the board was carried | The carry blocked them; fixed (using one puts the board away), to playtest. A rider with a BotW move set (Link) puts the board away the same way before its dodge or dash; untested, as this checkout had no move-set import | `RideTransition.cpp`, the game's character |
| H65 | `caveman_run` and `caveman_sprint` fail one run in three: a one-frame move or speed spike (8 cm, 340 cm/s) at the air mount's landing | Native's wheels touching a frame before its state lands, or a double step on a long frame; the rows pass on reruns | `skate_transitions` `caveman_*`, the landing frame in `continuity` |
| U5, U13 | Turning, the rider bends too much for the board's tilt | The retarget of Native's lean onto our proportions (inferred) | `RetargetRetailPose` |
| U19 | Hopping off with the board in hand, the tail clips the ground | The carry clip's board on our character | `RideTransition.cpp` |
| U58 | Ragdoll fallbacks: an invalid physics asset silently rides animation-only; large errors reset to the animation | Recovery by reset instead of failure | `URidePhysicalRider` |
| U73 | The foot-on-deck check fails at a placement frame and entering a push (3–4 cm a frame) | Unknown | The physical rider's foot anchors |
| U111 | The transitions' clip player has none of Native's spin overlays or physical feedback | It plays clips only | `RideClipPlayer.h` |
| K2 | The landing legs reach 75 cm above the deck before an ollie lands; Native's 81 | The retarget's scale or the body | `RetargetRetailPose` |
| K6 | Frame time p99 up to 26 ms in dense scenes; one 68 ms frame | Unknown, with the physical rider on | Frame traces |
| K7 | The camera does not turn from an exactly opposite heading; one-frame pull-ins | The game's camera blend | The game's camera, `GetCameraYaw` |
| K8 | One 281 ms frame switching to a second character | Asset loading | The game's character switch |
| K9 | Physics follow-up: a stability sweep, the get-up's foot margin, a second rider's legs and accessories at its feet | Open | `URidePhysicalRider` |
| G6 | No wipeout control (the left stick in a bail) and no active falls (flail, brace) | Not built on the Chaos bail | `StartBail`, the `Bail` profile |
| G18 | No skitching, moving objects, board throw, jump-out or fakie dismount clips | Not built | `RideTransition.cpp` |
| G20 | No sounds per surface or grind material, no ragdoll impacts, no tail scrape | One surface material; not built | `UpdateAudio` |
| G22 | The camera jumps 30 cm or more on some mounts; a kicked-out board stays in the world | Pending | The transitions, the game's camera |
| G29 | The air dismount clips for a Christ air and a tuck knee look wrong (inferred) | Unchecked | `RideTransition.cpp` |
| G30 | On the Native backend Y, D-pad, Start and Back never reach the session; the keyboard has no X | The reference's input wiring | `ReadHostPad` |
| U108 | Native backend rows are one frame behind their pad | It polls the previous step before sending the frame's input | `PollIdleRetail`, the QA timing |
| U118 | A QA row bails only after other rows ran in the same game | State leaking between rows | The QA reset |
| U28, G23, K10 | QA: identical tricks in a row merge in the count; rows missing (more grabs and grinds, pump gain, flick and pop latency); the grind setup and the wheel-contact count | The harness | The game's QA scenarios |

### Native's own behaviour

Native does these on the Native backend too; they are not bugs of the ride.

| ID | Behaviour |
|---|---|
| H18 | A quarter pipe 180 names no spin |
| H20 | Pumping gains from 1.19 times, not 1.2 |
| H21 | Some grind rows lock a different grind than the row expects |
| H22 | Vert airs differ from the rows' expectations |
| H24 | Hand-timed pops reach 1,900–2,250 cm/s |
| H27 | A goofy toe sits 28 cm over the deck |
| H28 | The pre-landing pose is 7 cm higher than expected |
| H31 | Pool landings come down on the deck |
| H32 | Coping catches end lip airs |
| H33 | Wheel contact counts differ from the rows' |
| H38 | Wheel spin rates differ from the rows' |
| H39 | The fakie pose does not look along the travel |
| H49 | 50-50s on a low ledge slip |
| H58 | A coping grind instead of an air |
| H59 | A lip air airs again |
| H66 | Rolling, a foot leaves the deck on 2-3 % of frames (`pose_feet`; the Native backend's pose rides: 19 of 208), and in the bowl pump a wheel sits up to 1.6 cm under or 4.3 cm over the ground (`wheels_contact`) |
