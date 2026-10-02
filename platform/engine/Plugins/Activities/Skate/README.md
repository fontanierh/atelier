# Skate

The Atelier Skate plugin (module `AtelierSkate`) puts an Unreal character on a skateboard. One C++
`atelier::skate::GameplaySession` runs in process and simulates the deck, trucks, wheels and physical rider together:
contacts and constraints, steering and pushes, Flick-It gestures, manuals and powerslides, grinds, pumping, airs,
landings and bails, with the recovered animation graphs, trick scoring and skating camera. The game supplies nearby
static collision, rails, controls, its character, the board meshes, sounds and the HUD; the adapter in
`Source/AtelierSkate/Private/SkateRuntime.cpp` connects the two and retargets the solved rider onto the game's
character. Board and rider physics stay in this native solver; they do not use Chaos.
[RUNTIME.md](RUNTIME.md) lists the systems, formats and checks;
[UNREAL_INTEGRATION.md](UNREAL_INTEGRATION.md) covers the asset, animation and collision tooling.

## Adding it to a game

1. Enable `Skate` in the `.uproject`, with `platform/engine/Plugins` in its `AdditionalPluginDirectories`. The plugin
   depends on AtelierCore and AtelierFX.
2. Track native source records outside Content, in `games/<game>/assets/skate/native`. Use the editor module's
   `SkateRuntimeAssetLibrary` to build a lossless `USkateRuntimeAsset` and `SkateCollisionBuilderLibrary` to bake
   the world's static meshes into a `USkateCollisionAsset` catalog. Create a `USkateProfile` with those references,
   tuning and board/audio references. Generated UAssets belong in ignored Content; gameplay loads them exclusively.
   Include the assets and their dependencies in the cook, for example with an Asset Manager rule and:

   ```ini
   [/Script/UnrealEd.ProjectPackagingSettings]
   +DirectoriesToAlwaysCook=(Path="/Game/SkateNative")
   ```

3. Make the player an `ACharacter` that implements `ISkateRider`, give it a `USkateComponent` and call
   `Initialize(Character)`. Bind a button to `Toggle()`.
4. In the character movement component's `PhysCustom`, call `PhysSkate(Dt)` for custom mode
   `USkateComponent::MovementMode` (2), and leave the actor's rotation alone while `IsRiding()` (true during a bail).
5. Put `FAnimNode_SkatePose` above the base local-space pose in the AnimGraph, at Weight 1. Its `PreUpdate` copies
   `GetRetailPose()` on the game thread; animation workers consume the snapshot. Native graph hosts must include
   the node in `GetCustomNodes()` so Unreal registers its `PreUpdate`. The editor wrapper works in Animation Blueprints.
6. Optionally drive the camera from `GetRetailCamera(Transform, FOV)`. The FOV is vertical; convert it to Unreal's
   horizontal FOV with the viewport aspect.
7. Register grindable lines with `USkateRailSubsystem::Add`: rails, ledge and box edges, coping and curbs, as their top
   contact line in centimetres.
8. Select the profile through `USkateSettings::DefaultProfile`, or set the component's `Profile` before `Initialize`.
   Use `SetProfile` to validate and switch content while off the board.

| `ISkateRider` | Meaning |
| --- | --- |
| `PrepareToSkate()` | Getting on: put away what the hands hold, stop any action in progress |
| `IsSkateInputBlocked()` | A menu has the controls: the board gets no input and the mouse stick recentres |
| `IsSkateMouseFree()` | The mouse is released to the desktop: the board gets no input |
| `GetSkateMouseSensitivity()` | The player's mouse sensitivity (default 0.4); scales the mouse flick |
| `GetSkateBone(Contract)` | The rider's bone for a humanoid contract name, `NAME_None` when it has none (default: the name itself); the retargeter finds every bone through it |
| `GetSkateBoardScale()` | The visible board's size (default 1): it grows about the wheels' contact and the pose rises onto its deck; the physics keep the standard board |

`Toggle()` mounts only on the ground and not crouched. The board starts at the player's feet, aligned with their
travel above 30 cm/s, and keeps their velocity. Stepping off works only on the ground (not in the air, on a rail or
in a bail) and leaves the player facing the board's travel at up to 420 cm/s. `StowImmediately()`, `SetGoofy()`,
`PlaceAt()` and `Launch()` serve the game and QA; `SetScriptedInput()` replaces the player's controls.

## Profile and settings

`USkateSettings` selects one asset in the game's `DefaultGame.ini`:

```ini
[/Script/AtelierSkate.SkateSettings]
DefaultProfile=/Game/SkateNative/DA_Profile.DA_Profile
```

All content and tuning live in `USkateProfile`:

| Key | Default | Meaning |
| --- | --- | --- |
| `RuntimeData` | none | Required cooked `USkateRuntimeAsset`; exact native bytes and checksums |
| `CollisionDataCatalog` | empty | Cooked `USkateCollisionAsset` catalogs for the world's static collision |
| `CollisionScanPeriodSeconds` | 0.25 | Scene-change scan interval, 0.05 to 5 seconds |
| `Difficulty` | `normal` | Recovered controller preset: `easy`, `normal` or `hardcore` |
| `bGoofy` | false | Initial stance |
| `TruckTightness` | 0.5 | 0 loose to 1 tight; feeds the recovered steering scalar |
| `PopHeightScale` | 1 | 0.5 to 2; scales the recovered jump-height presets |
| `AirSpinScale` | 1 | 0.5 to 3; scales the air-spin target and the spin response curves |
| `PushSpeedScale` | 1 | 0.5 to 2; scales the animation-timed push speed target |
| `PushPowerScale` | 1 | 0.5 to 3; scales the planted-foot push propulsion |
| `VertAssist` | 0 | 0 to 1; how far short of vertical a quarter pipe still sends a straight air back into it (1 reaches lips of about 50°) |
| `DeckMesh`, `TruckMesh`, `WheelMesh` | none | Board parts (see the board contract); skating is unavailable without all three |
| `SoundFolder` | none | Content folder of the board sounds |
| `FallSounds` | none | Body-hitting-the-ground sounds for a bail (the `fall` cue) |

The scales apply to the stock values each time the session is configured, so they never compound. Structural
validation collects independent profile errors; missing content or an out-of-range scale prevents the board from starting.

`SoundFolder` holds the loops `roll_01`, `grind_01`, `slide_01`, `skid_01` (powerslide) and `scrape_01` (foot brake),
and one-shot variants `<cue>_01` to `<cue>_08` for `pop`, `land`, `catch`, `push`, `flick` and `clatter`. The loops
follow the board with volume and pitch set by mode and speed; a one-shot never repeats the previous variant. Sounds
attenuate over a 500 cm inner radius and 4500 cm falloff.

## Controls

| Action | Controller | Keyboard and mouse |
| --- | --- | --- |
| Get on / off | The game's button | The game's key |
| Push | A (X pushes mongo) | W or Up |
| Brake | B | S or Down |
| Steer, spin | Left stick | A / D or Left / Right |
| Powerslide | Left stick down-left / down-right | Hold C; A chooses the left side |
| Load, ollie | Right stick down, then up | Hold Space, release to pop |
| Flick-It tricks | Right stick gestures | Hold the left mouse button and flick |
| Manual, nose manual | Right stick partly down / up | Hold the left mouse button and move slowly |
| Pump (ground), grab (air) | Left / right trigger | Q / E |
| Transfer over the coping | Left stick forward | Hold Shift |

Kickflips flick down then up-left, heelflips down then up-right; goofy mirrors the gestures. Holding the left-trigger
grab, B makes it a Christ air and A a one-foot; holding the right stick to one side changes the grab, and the right
trigger with the stick held left is a tuck knee. A grab never requests a transfer: the transfer has its own input. LB,
RB and both stick clicks pass through to the recovered pad; clicking both sticks with both triggers held is the
deliberate bail. The adapter undoes the project's 0.25 per-axis stick dead zone, because Flick-It and the manual
balance read real stick positions. A fast mouse flick points the stick in its direction and springs back after 0.1 s;
slow movement moves it gradually.

## Board contract

The board meshes are separate static meshes, in centimetres:

| Mesh | Origin | Axes |
| --- | --- | --- |
| Deck | Centre of the deck top | +X nose, +Z up |
| Truck | Kingpin pivot on the deck underside, modelled as the front truck | +X nose, +Z up; the back truck is the same mesh turned 180° |
| Wheel | Wheel centre | Axle along Y |

The deck top rides 9.05 cm above the ground. The adapter places each part on its solved bone (`SKATEBOARD_ROOT`,
`TRUCK_FRONT`, `TRUCK_BACK` and the four wheel bones), fits the truck mesh to the solved axle and scales the wheels
from a 2.65 cm host radius to the session's 3.1 cm. Board parts render with custom depth stencil 2.

## How a ride runs

The session runs on its own thread, `AtelierSkateNative` (32 MiB stack), which owns every mutable simulation object.
The game thread sends it typed commands (activate, configure, step, world, launch, suspend) and reads back the root,
bones, velocity, state, trick, score, manual balance and camera. Each activation carries a generation number so that
output from a previous ride never moves a new one.

- **Loading.** Two seconds after play begins the component starts preloading the profile's runtime data and nearby
  collision. The game thread copies resource bytes into immutable native ownership; the native thread verifies
  every checksum before decoding, without reading UObjects. Missing or corrupt assets have no file fallback.
  The session stays loaded between rides: getting off suspends its input, `EndPlay` releases it.
- **Collision.** The adapter snapshots registered, collision-enabled static meshes that block `Pawn` within a 100 m
  cube around the rider, shrinking it to 60, 35 or 20 m when it exceeds 500,000 triangles. Complex-as-simple meshes
  use baked local triangles; other meshes give their cooked boxes, spheres, capsules and convex hulls. Gathering
  does not read static render buffers. Instanced meshes count; the rider's own components do not. Registered rails
  within the cube go with it. Leaving the inner 60%, or detecting changed geometry, transforms, instances,
  materials or rails at the profile's scan interval, requests a new snapshot. The game thread gathers it, a
  background task builds it and the session installs it between steps. Within 60 m of an actor tagged `SkatePark`
  the snapshot stays centred on that actor; scene changes still refresh it. Over open water, where there is nothing
  to snapshot, the old one stays and the rebuild is retried 20 m further on. Stale or missing baked geometry is an error.
- **Materials.** Catalog mappings explicitly connect Physical Materials to packed native surface IDs and optional
  friction/restitution overrides. Unmapped surfaces keep the stock contact material and surface zero; Unreal's
  `SurfaceType` is not assumed to be a native ID.
- **Input.** Each frame the component samples the controls into an Xbox-style packet and steps the session with the
  frame time; the session runs whole 60 Hz ticks.
- **Retargeting.** The solved skeleton is mapped onto the host's `root`, `pelvis`, `spine`, `spine_mid`, `chest`,
  `neck`, `head`, clavicles, arms, hands, thighs, shins, feet and toes (`_L` / `_R`). The pose is scaled by the
  hip-to-foot height ratio, keeps the host's bind bone lengths and scale, and fits the feet to the solved targets with
  two-bone leg IK; unmapped bones keep their bind pose. In a grab, where the solved hand reaches its deck, the host's
  hand holds the nearest edge of the board (knuckles outside the rail, fingers hooked under, thumb on the grip tape)
  and the arm is solved to it. The grip is sized in the host's finger widths (its knuckle spacing), uses whichever
  fingers the rig has, and is tunable live through `skate.Grip`. During a bail, skinned LOD0 vertices are sampled
  in 12 cm cells and traced down, and the whole pose is lifted to keep at least 0.5 cm above the ground, so a
  differently proportioned character stays out of the floor. This needs CPU-accessible skin data on the rider's mesh.
- **Animation.** `FAnimNode_SkatePose` captures local transforms and generation identifiers in `PreUpdate`. At
  full weight it resets to reference pose and assigns by mesh bone index, matching the former direct proxy path
  while keeping base graph clocks. Inactive, invalid or zero-weight poses pass through; partial weight blends
  toward the same target. Node diagnostics expose the copied pose's hash and generation.
- **Modes.** The session's state name sets the component mode: `Wipeout` states are a bail, `Grind` states a grind,
  `Air` states the air, anything else the ground. The HUD getters (`GetComboLine`, `GetComboAlpha`, `GetScore`,
  `GetStatus`, `GetSpeed`, `GetCameraYaw`) read from it.
- **Events and diagnostics.** Blueprint mode, trick, landing and bail events follow publication of the solved frame.
  `GetRuntimeDiagnostics()` returns readiness, pending work, native tick, pose generation, data identity, collision
  counts/revision and errors. A listener can stow the board; subsequent events from that obsolete ride are skipped.
- **Errors.** Missing or corrupt data, or a session error, logs `SKATE: <message>`, shows it on screen, tears down
  the failed ride and publishes `OnRuntimeFailure`; the player keeps walking.

## Data and limits

The source bundle contains settings, graphs, gesture sets, physical skeletons, the animation rig, clips, metadata
banks and camera shots, listed with their sizes and SHA-256 in `package-manifest.json`. Source verification precedes
asset creation; the filesystem loader remains an offline QA entry point. Gameplay reads only the profile's assets.
[RUNTIME.md](RUNTIME.md#data-bundle) describes the formats and [checks](RUNTIME.md#verification), and lists the
[limits](RUNTIME.md#limits). The Unreal asset, animation, collision and cooked-game checks are described in
[UNREAL_INTEGRATION.md](UNREAL_INTEGRATION.md#validation-status).
