# Ski

Physics-based freestyle skiing in two layers. A native simulation (`Source/AtelierSki/Private/Native`) rides the skis
on the snow. The character's own body rides on top of it as an active ragdoll that follows the skiing pose and goes
limp in a crash. The simulation is a C++ port of the browser lab in
[`platform/web/ski-lab`](../../../../web/ski-lab/README.md). Its checks run the same scripted run through both and
require them to agree.

## Model

**The simulation.** The skier is one rigid body (the pelvis) with legs of variable length. The skis meet the snow at
contact points along their length (`Settings::contactPoints`). Each point pushes out of the snow on a spring and damper.
It grips across the ski by its edge angle, and glides along it. An edged ski bends into its sidecut, and its contact
line turns. That turn is the carve.

The player steers by leaning. A balance controller moves the body along the felt force of the turn that the stick
asks for. The legs crouch, extend and pop, and they absorb landings. In the air the body keeps its angular momentum,
and tucking spins it faster. A crash happens when the body touches the snow, or when the skier tips more than 78°
from the snow while standing on it. The simulation steps at 600 Hz.

The simulation reports takeoff, landing, trick, bail and crash events. Trick names come from the yaw, flips and grabs
in the air (for example `Switch 540 Mute` or `Backflip`). A trick scores once its landing has held for 0.7 s.

**The snow** (`SkiTerrain`). The simulation's frame is the world's in metres, with y flipped to the left. Inside a
terrain park (`ASkiPark`) the snow is the park's exact surface. Anywhere else it comes from a line trace on the Pawn
channel against the world's collision.

**The body** (`SkiPhysicalBody`). The pose comes first:

- `USkiComponent` computes the skiing pose from the simulation, and `FAnimNode_SkiRider` applies it.
- The pelvis goes where the simulation carries it, scaled to the character's leg length.
- The trunk bends with the crouch and tuck.
- Two-bone IK puts the ankles on the skis, and the feet turn with the skis' edge.
- The arms reach forward for balance and go wide in the air. A grab takes a hand to its ski: Mute takes the left hand
  to the left ski's front, and Safety takes the right hand to the right ski.

With `bPhysicalRider` set, the mesh's physics bodies then simulate under Physics Control:

- The pelvis body follows the pose kinematically.
- Every joint is driven toward the pose (`JointStrength`).
- The feet and hands are held from the pelvis (`FeetStrength`, `HandStrength`). The body therefore keeps up at any
  speed, and only its limbs swing and lag.
- While skiing, the bodies are query-only and pass through the snow.

**Crashes.** In a crash the pelvis lets go. Gravity and collision come on, and the joints drop to `CrashTone`. The body
tumbles with the skier's momentum, and the skis stay on its feet. After `CrashTime` the skier is back up on the snow
where the body lies, standing still.

A mesh with fewer than six physics bodies, or `ski.Physical 0`, shows the pose alone. In that case the simulation's own
tumble is the crash.

## Controls

| | Keyboard | Gamepad |
| --- | --- | --- |
| Skis on/off | the game's binding | the game's binding |
| Steer (lean into the turn) | A / D | left stick X |
| Lean forward / back | W / S | left stick Y |
| Crouch; release to pop | Space | A (bottom face) |
| Wind up a spin | J / L | right stick X |
| Mute grab / Safety grab | Q / E | left / right trigger |
| Brake (hockey stop) | Left Shift | B (right face) |

Above walking speed the view turns toward the direction of travel (`CameraFollow`).

Console commands, for play and QA:

- `ski.Park [speed]` puts the skis on at the top of the first terrain park, at a speed in m/s.
- `ski.Input steer lean crouch spin grab brake` replaces the controls until `ski.Input off`.
- `ski.Describe` logs the skier's state.
- `ski.Off` takes the skis off at once.

## Park

`ASkiPark` builds the native park (`SkiParkShape`) as a procedural snow mesh with collision:

- The park runs 410 m down the fall line, with a start, a run-in and three jumps (small, medium and large).
- Each jump is shaped for its speed window.

The actor's location is the park's origin, and its yaw is the fall line. Pitch and roll are ignored. `GetStartLocation`
and `GetStartYaw` give the top of the run.

Place the park on ground carved to its base (`Park::Base`), so that the run-out meets the slope.

## Settings

Project Settings > Plugins > Ski (`[/Script/AtelierSki.SkiSettings]` in `DefaultGame.ini`):

- **Assists:** `BalanceAssist`, `AirAssist`, `SpinAssist`.
- **Look:**
  - `SkiMesh`: one ski, 1 m long. Without a mesh the skis are boxes.
  - `SkiMaterial`.
  - `SnowMaterial`: without it the snow is plain white.
  - `StanceWidth`.
- **Body:** `bPhysicalRider`, `JointStrength`, `FeetStrength`, `HandStrength`, `CrashTone`, `CrashTime`.
- **Camera:** `CameraFollow`.

The console variable `ski.Physical` (1 on, 0 off, -1 the setting) overrides `bPhysicalRider` from the next start.

## Adding it to a game

1. Enable `Ski` in the `.uproject`, and add `AtelierSki` to the game module's dependencies.
2. Have the character implement `ISkiRider`:
   - `PrepareToSki` puts away what the hands hold.
   - `IsSkiInputBlocked` reports when a menu has the controls.
   - `GetSkiBone` maps the humanoid contract's bone names (`platform/conventions/rigs/humanoid.toml`) to the mesh's
     bones.
3. Create a `USkiComponent` and call `Initialize(this)`. Bind a key to `Toggle`.
4. In the movement component's `PhysCustom`, call `PhysSki` for `USkiComponent::MovementMode` (custom mode 6). Skip
   the rotation update while skiing: the component sets the actor's rotation itself.
5. In a native anim instance, link `FAnimNode_SkiRider` above the character's graph and add `GetNodes()` to
   `GetCustomNodes()`.

Skiing is single-player. A networked game should refuse to start it online.

## Checks

`platform/studio/tests/test_ski_native.py` compiles the native simulation with clang and runs two checks:

- `Tests/ski_sim_test.cpp`: carving, popping, landing, crashing and the park's shape.
- A scripted run, compared with the same run through the browser lab (`Tests/trace_sim.mjs`, which needs Node).
