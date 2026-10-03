# Ride

Ride is the Unreal-native skating backend (`skate.Backend Ride`, `USkateSettings::Backend`). Its sources are in
`Source/AtelierSkate/Private/Ride/`.

## Physical rider

While riding, the rider is an active ragdoll: the bodies of its physics asset simulate in the world's Chaos scene,
Physics Control drives them toward the animated pose, and the board holds the feet. The bail lets the same bodies go
limp, and the get-up blends from a snapshot of the fallen body into the get-up clip. `skate.RidePhysical 0` turns the
rider back into pure animation, with a ragdoll only for bails.

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
- **Controller.** A `UPhysicsControlComponent` sits on the rider. It creates its controls and body modifiers from a
  `UPhysicsControlAsset`, using limbs found through the bone contract:
  - parent-space controls on every joint, aimed at the animated pose, in the sets `Joints_Spine`, `Joints_Arms` and
    `Joints_Legs`;
  - world-space controls on every body, with the sets `Anchor_Pelvis`, `Anchor_Feet` and `Anchor_Hands` as the strong
    ones;
  - a body modifier on every body: kinematic and unseen (physics weight 0) until the mount, simulated after it.

  Targets come from the mesh's animated component-space pose: `bUseSkeletalAnimation`, with target velocities from
  the pose's motion, so a body tracks at 10 m/s with no lag. The mesh stays attached to the capsule
  (`ComponentTransformIsKinematic`), and the ride moves the actor without teleporting physics (`ETeleportType::None`).
- **Phases.** Each phase is a named profile in the control asset: `Riding`, `Air`, `Landing` (held for `LandingTime`
  after a touchdown), `Grind`, `Manual`, `Bail`, `GetUp`, `OnFoot`. `InvokeControlProfile` switches between them as
  the session's mode changes. The mount and dismount fade the body modifiers' physics weight over `MountBlend` and
  `DismountBlend`. The default profiles are built from `URidePhysicalSettings` (Project Settings › Plugins › Skate
  Physical Rider); `skate.RidePhysicalReload` rebuilds them live. Point `ControlAsset` there at an authored asset to
  replace them in the editor.
- **Strengths.** A strength works like a frequency: an acceleration drive with velocity feed-forward lags by a/(2πf)².
  - Pelvis anchor, 8 Hz: lags 0.6 cm in a 16 m/s² carve and adds about 5 cm at a 7 m/s landing, which matches the
    reference.
  - Feet, 12 Hz: stay within 0.3 cm of the deck. On the board the feet do not collide with the world, since the deck
    carries them.
  - Joints, 10 Hz.
  - Every body also has a weak 2 Hz world anchor. This stops sag from building up down the chain.
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
  takes a pose snapshot, sets the bodies kinematic and unseen, and blends the pose from the snapshot into the clip
  over `GetUpBlend` (`BlendFromSnapshot`). The rider gets up where the body lies and never returns to where the bail
  started.
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
  - A rider placed further than 1 m in one frame (a scripted placement) has its bodies reset to the animation.

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
