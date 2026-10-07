# Skate

The Atelier Skate plugin (module `AtelierSkate`) puts an Unreal character on a skateboard. One C++
`atelier::skate::GameplaySession` runs in process and simulates the deck, trucks, wheels and physical rider together:
contacts and constraints, steering and pushes, Flick-It gestures, manuals and powerslides, grinds, pumping, airs,
landings and bails, with the recovered animation graphs, trick scoring and skating camera. The game supplies nearby
static collision, rails, controls, its character, the board meshes, sounds and the HUD; the adapter in
`Source/AtelierSkate/Private/SkateRuntime.cpp` connects the two, and `SkateRetarget.cpp` retargets the solved rider
onto the game's character. Under the Ride backend the character's body is an active ragdoll that takes over in bails
and plays the transitions on and off the board ([RIDE.md](RIDE.md)). [RUNTIME.md](RUNTIME.md) lists the session's
systems, the data bundle and how both are verified.

## Adding it to a game

1. Enable `Skate` in the `.uproject`, with `platform/engine/Plugins` in its `AdditionalPluginDirectories`. The plugin
   depends on AtelierCore and AtelierFX.
2. Track the native data bundle in the game's `unreal/Content/Data/SkateNative` and stage it as loose files. The
   loader reads it with standard file reads, so a pak alone is not enough:

   ```ini
   [/Script/UnrealEd.ProjectPackagingSettings]
   +DirectoriesToAlwaysStageAsNonUFS=(Path="Data")
   ```

3. Make the player an `ACharacter` that implements `ISkateRider`, give it a `USkateComponent` and call
   `Initialize(Character)`. Bind a button to `Toggle()`.
4. In the character movement component's `PhysCustom`, call `PhysSkate(Dt)` for custom mode
   `USkateComponent::MovementMode` (2), and leave the actor's rotation alone while `IsRiding()` (true during a bail).
5. In the animation instance, use `GetRetailPose()` while riding: local transforms for every bone of the host
   skeleton.
6. Optionally drive the camera from `GetRetailCamera(Transform, FOV)`. The FOV is vertical; convert it to Unreal's
   horizontal FOV with the viewport aspect.
7. Register grindable lines with `USkateRailSubsystem::Add`: rails, ledge and box edges, coping and curbs, as their top
   contact line in centimetres.
8. Set the board meshes, sounds and tuning in `DefaultGame.ini` (below).

| `ISkateRider` | Meaning |
| --- | --- |
| `PrepareToSkate()` | Getting on: put away what the hands hold, stop any action in progress |
| `IsSkateInputBlocked()` | A menu has the controls: the board gets no input and the mouse stick recentres |
| `IsSkateMouseFree()` | The mouse is released to the desktop: the board gets no input |
| `GetSkateMouseSensitivity()` | The player's mouse sensitivity (default 0.4); scales the mouse flick |
| `GetSkateBone(Contract)` | The rider's bone for a humanoid contract name, `NAME_None` when it has none (default: the name itself); the retargeter finds every bone through it |
| `GetSkateBoardScale()` | The visible board's size (default 1): it grows about the wheels' contact and the pose rises onto its deck; the physics keep the standard board |
| `CanCarrySkateBoard()` | Ride only: the hands are free to carry the board on foot (default true); false puts a carried board away and refuses the board button |

`Toggle()` mounts only on the ground and not crouched. The board starts at the player's feet, aligned with their
travel above 30 cm/s, and keeps their velocity. Stepping off works only on the ground (not in the air, on a rail or
in a bail) and leaves the player facing the board's travel at up to 420 cm/s. `StowImmediately()`, `SetGoofy()`,
`PlaceAt()` and `Launch()` serve the game and QA; `SetScriptedInput()` replaces the player's controls.

## Backends

`USkateSettings::Backend` picks the backend, and the console variable `skate.Backend` (`Native` or `Ride`) overrides it
from the next mount on. Both ride the same `GameplaySession` and serve the same `ISkateRider`, controls, board meshes,
sounds and HUD getters.

- **Ride**: the backend games ship, described in [RIDE.md](RIDE.md). The session rides the board under the
  character's own body: an active ragdoll that Physics Control drives toward the retargeted pose
  (`skate.RidePhysical 0` shows the pose alone), Chaos bails and get-ups, and transitions on and off the board played
  from the native clips. The game imports the clips as Unreal assets under `/Game/SkateRide` (`SK_SkateRider`,
  `MDT_SkateRider` and the clips in `Clips/B0` and `Clips/B1`) with its own build step. `skate.RideTune` overrides the
  transitions' tuning live (`Name=Value` words, names as in `RideTuning.h`).
- **Native**: the session's pose on the character with no physical body, no transitions and no Chaos bails. It is
  the reference that QA and replays compare the Ride backend against, not a backend for players.

## Settings

`USkateSettings`, section `[/Script/AtelierSkate.SkateSettings]` of the game's `DefaultGame.ini`:

| Key | Default | Meaning |
| --- | --- | --- |
| `Backend` | `Ride` | `Ride` (the ride) or `Native` (the reference; see Backends); `skate.Backend` overrides it on the next mount |
| `Difficulty` | `normal` | Recovered controller preset: `easy`, `normal` or `hardcore` |
| `TruckTightness` | 0.5 | 0 loose to 1 tight; feeds the recovered steering scalar |
| `PopHeightScale` | 1 | 0.5 to 2; scales the recovered jump-height presets |
| `AirSpinScale` | 1 | 0.5 to 3; scales the air-spin target and the spin response curves |
| `PushSpeedScale` | 1 | 0.5 to 2; scales the animation-timed push speed target |
| `PushPowerScale` | 1 | 0.5 to 3; scales the planted-foot push propulsion |
| `VertAssist` | 0 | 0 to 1; how far short of vertical a quarter pipe still sends a straight air back into it (1 reaches lips of about 50°) |
| `bTightFlicks` | false | Also read a hardflip or inward heelflip flicked close to straight down then up (newer skate games' motion), beside the authored wide arc: the main gesture set gains a narrower copy of each (`GestureInputPublication::Tune`). Off is stock |
| `DeckMesh`, `TruckMesh`, `WheelMesh` | none | Board parts (see the board contract); skating is unavailable without all three |
| `BoardDissolveMaterial` | none | Ride only: a masked material with a scalar `Dissolve` (0 whole, 1 gone) that fades the board in and out; without one the board shows and hides |
| `SoundFolder` | none | Content folder of the board sounds |
| `FallSounds` | none | Body-hitting-the-ground sounds for a bail (the `fall` cue) |
| `SurfaceMeshes`, `SurfaceMaterials` | empty | What the ground rides like, by static mesh or material name (see Surfaces) |
| `DefaultSurface` | `Concrete` | The surface of a triangle nothing names |

The scales apply to the stock values each time the session is configured, so they never compound. A scale outside
its range is an error and the board does not start.

### Surfaces

Every colliding triangle in the snapshot carries an `ESkateSurface`, and the board rides it with the recovered
surface profile Skate 3 gives that kind of ground. The four wheels vote, so a board half on the grass rides half
slow. The surface's own sounds also play (see Feel).

| Surface | Profile | Rides |
| --- | --- | --- |
| `Concrete`, `Wood`, `Metal` | smooth | Full speed. Wood and metal only sound different |
| `Asphalt`, `Stone` | rough | Nearly full speed, with a rumble |
| `Dirt` | slow | Coasting stops within about 10 m; pushing still gets going |
| `Grass`, `Sand` | very slow | Barely rolls; pushing reaches a walking pace |

The first match wins:

1. An actor or component tag `SkateSurface.<Surface>` (`SkateSurface.Wood`).
2. The static mesh's name in `SurfaceMeshes`.
3. The triangle's material, read per mesh section, in `SurfaceMaterials`.
4. `DefaultSurface`.

Names drop a leading `SM_`, `MI_` or `M_`, so `MI_Road` is `Road`. Use a mesh name when several kinds of ground share
one material. The ini form is `SurfaceMaterials=(("Grass",Grass),("Road",Asphalt))`. `skate.SurfaceDebug 1` logs
each mesh section's surface the next time the snapshot is built. `GetSurface()` returns the surface under the
wheels, and `GetRetailState` reports it as `surface=<name>:<wheels>`.

## Feel

`FSkateFeel` (`Public/SkateFeel.h`) is everything that changes how the board rides, for a game's settings menu.
`USkateComponent::SetFeel` applies it at once, mid-ride too, and to every later ride. `FSkateFeel::Defaults()` starts
from the settings above and the stock feel. A game's settings menu shows it, and saves it with the rest of its settings.
Multipliers scale the active difficulty's authored values, so 1 is the game as made. A switch at -1 keeps the
difficulty's own choice. Values outside their ranges are refused with the reason (`FSkateFeel::Validate`), and the
feel then stays as it was.

The session side is `FeelTuning` (`Private/Native/FeelTuning.h`), applied by `GameplayRuntime::Feel`. It works on
copies of the authored settings captured when the session is created, so values never compound and the defaults are
bit-exact with stock.

| Field | Range | What it scales |
| --- | --- | --- |
| `Difficulty`, `TruckTightness`, `Pop`, `Spin`, `PushSpeed`, `PushPower`, `VertAssist` | as above | The settings above |
| `TightFlicks` | 0, 1 | `bTightFlicks` |
| `FlickRadius` | 0.5 to 2 | Each Flick-It pattern's match radius: how far a flick may stray from a trick's shape |
| `FlickWindow` | 0.5 to 3 | The samples a flick may take (the stick's authored miss limit) |
| `FlickPace` | 0.5 to 2 | The flick speeds that map to low and full pop (lower needs a gentler flick) |
| `StickDeadZone`, `StickReach` | 0.25 to 0.6, 0.6 to 1 | Stick travel ignored, and travel that counts as full: remapped onto the pad's live 0.25 to 0.95 (`SkatePad.h`) |
| `MouseFlick` | 0.25 to 4 | The mouse trick stick's travel, beside the game's mouse sensitivity |
| `Gravity` | 0.5 to 1.5 | World gravity, for the rider, the board and every predicted arc. Jump heights stay, air time changes |
| `Boneless`, `Hippy` | 0.5 to 3 | Boneless and hippy-jump heights |
| `RailMagnetism` | 0.25 to 3 | The grind lock distance, how far and how sharply a jump may be bent onto a rail, and the crossing and drop speeds still admitted |
| `GrindPop` | 0.5 to 2 | The ollie out of a grind |
| `GrindFriction` | 0 to 3 | Grind and slide friction |
| `Braking` | 0.25 to 3 | Foot-brake force |
| `Steering`, `Carve`, `Grip` | 0.5 to 2 | Steering scalar, heading turn strength, wheel friction |
| `Powerslide` | 0.25 to 3 | A powerslide's slowing force |
| `RollingFriction` | 0 to 3 | Surface, coasting and manual rolling friction: how fast speed above the board's cruising speed bleeds off (it holds its cruising speed on the flat either way) |
| `HillSpeed` | 0 to 2 | The speed model's downhill pull |
| `Pump` | 0 to 3 | Pumping acceleration |
| `Wobble`, `WobbleOnset` | 0 to 3, 0.5 to 3 | Speed-wobble amplitude, and the speed it starts at |
| `ManualDrift` | 0 to 3 | Manual balance noise |
| `Landing` | 0.5 to 3 | The landing angles and speeds forgiven before a bail |
| `Impact` | 0.5 to 3 | The ground and air accelerations ridden through before a bail |
| `GetUpDelay` | 0.25 to 2 | Ride: the time the body lies before getting up |
| `AutoPush` | -1, 0, 1 | Auto push |
| `AssistedAir` | -1, 0, 1 | Easy body spins and perfect body flips |
| `CameraDistance` | 0.6 to 1.6 | The skate camera's distance from the rider |
| `CameraFOV` | -20 to 20 | Degrees added to the skate camera's field of view |

`SoundFolder` holds the loops `roll_01`, `grind_01`, `slide_01`, `skid_01` (powerslide) and `scrape_01` (foot brake),
and one-shot variants `<cue>_01` to `<cue>_08` for `pop`, `land`, `catch`, `push`, `flick` and `clatter`. The loops
follow the board with volume and pitch set by mode and speed; a one-shot never repeats the previous variant. Each
surface after `Concrete` can have its own roll loop `roll_<surface>_01` (`roll_wood_01`) and its own `pop_<surface>`
and `land_<surface>` variants. The board plays whichever the ground under it has, and otherwise falls back to `roll`,
`pop` or `land`. The roll crossfades as the board crosses from one surface to another. Sounds
attenuate over a 500 cm inner radius and 4500 cm falloff.

## Controls

| Action | Controller | Keyboard and mouse |
| --- | --- | --- |
| Get on / off | The game's button | The game's key |
| Board to the hand / put it away (Ride, on foot) | The game's button (`RecallBoard()`) | The game's key |
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

- **Loading.** Two seconds after play begins the component preloads the data and nearby collision, so the first mount
  is immediate. The session stays loaded between rides: getting off suspends its input, `EndPlay` releases it.
- **Collision.** The adapter snapshots registered, collision-enabled static meshes that block `Pawn` within a 100 m
  cube around the rider, shrinking it to 60, 35 or 20 m when it exceeds 500,000 triangles. Complex-as-simple meshes
  give their collision triangles: their collision LOD's render triangles, or, in a cooked build that keeps no CPU copy
  of those, the cooked Chaos triangles Unreal itself collides with (`skate.CookedSurface 1` reads those in the editor
  too, which checks their contents but not the cooked build's choice of them; the packaged `japan.SkateGroundCheck`
  does). Other meshes give their boxes, spheres, capsules and convex hulls. Instanced meshes
  count; the rider's own components do not. Registered rails within the cube go with it. When the rider leaves the
  inner 60%, the game thread gathers the next snapshot, a background task builds it and the session installs it
  between steps. Within 60 m of an actor tagged `SkatePark` the snapshot stays centred on that actor, so riding
  around a park never rebuilds it. Over open water, where there is nothing to snapshot, the old one stays and the
  rebuild is retried 20 m further on. Game meshes are not authored skate collision, so an edge within 12 mm of the
  wheels' bottoms (a gap between planks, a seam, trim) is ridden over: the wheel steps up onto it, and the trucks, the
  deck and the rider's feet pass its face. A taller edge, such as a 3 cm curb, still stops the board. A ramp is not an
  edge: a wheel steps up only where it touches an edge or corner, and the trucks and deck pass only faces no higher
  than 12 mm over the wheels in the world, so a transition met tilted, or a pitched landing in it, holds the board.
- **Input.** Each frame the component samples the controls into an Xbox-style packet and steps the session with the
  frame time; the session runs whole 60 Hz ticks.
- **Lockstep.** By default the game thread sends the next step only once the last one's pose is back, so a slow step
  runs later and merges two frames' time. Under a fixed time step or frame rate (`skate.Lockstep` -1, the default), or
  with `skate.Lockstep 1`, each frame waits up to 2 s for the last step and a collision rebuild installs on the frame
  after it starts, so the same controls ride the same way: the game's `scenarios/ride_session.py` replays a recorded session to
  the bit. The state string then shows the controls sent (`pad=`) and the collision snapshots sent (`world=`).
- **Retargeting.** The solved skeleton is mapped onto the host's `root`, `pelvis`, `spine`, `spine_mid`, `chest`,
  `neck`, `head`, clavicles, arms, hands, thighs, shins, feet and toes (`_L` / `_R`). The pose is scaled by the
  hip-to-foot height ratio, keeps the host's bind bone lengths and scale, and fits the feet to the solved targets with
  two-bone leg IK; unmapped bones keep their bind pose. In a grab, where the solved hand reaches its deck, the host's
  hand holds the nearest edge of the board (knuckles outside the rail, fingers hooked under, thumb on the grip tape)
  and the arm is solved to it. The grip is sized in the host's finger widths (its knuckle spacing), uses whichever
  fingers the rig has, and is tunable live through `skate.Grip`. During a bail, skinned LOD0 vertices are sampled
  in 12 cm cells and traced down, and the whole pose is lifted to keep at least 0.5 cm above the ground, so a
  differently proportioned character stays out of the floor. This needs CPU-accessible skin data on the rider's mesh.
- **Modes.** The session's state name sets the component mode: `Wipeout` states are a bail, `Grind` states a grind,
  `Air` states the air, anything else the ground. The HUD getters (`GetComboLine`, `GetComboAlpha`, `GetScore`,
  `GetStatus`, `GetSpeed`, `GetCameraYaw`) read from it.
- **Errors.** Missing or corrupt data, or a session error, logs `SKATE: <message>`, shows it on screen and stows the
  board; the player keeps walking. Under the Ride backend a session error during a ride bails the body instead and
  loads a fresh session (see [RIDE.md](RIDE.md#failures)).

## Data and limits

The session reads the game's tracked `unreal/Content/Data/SkateNative` bundle: settings, graphs, gesture sets,
physical skeletons, the animation rig, clips, metadata banks and camera shots, listed with their sizes and SHA-256 in
`package-manifest.json`. The game's `skate.runtime` build step checks every file against that manifest before Unreal
compiles. [RUNTIME.md](RUNTIME.md#data-bundle) describes the formats and the
[verification](RUNTIME.md#verification), and lists the [limits](RUNTIME.md#limits): collision is a static snapshot
whose triangles carry the [surface](#surfaces) they were classified as, and editor builds are the checked path.
