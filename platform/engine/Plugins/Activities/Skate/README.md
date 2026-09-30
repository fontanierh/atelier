# Skate

The recovered Skate 3 Rust Session is the skating engine. It owns the board/rider solver, animation graphs,
Flick-It, riding states, tricks, scoring and camera. Unreal supplies terrain, player controls, the Cairo mesh,
board meshes, audio and HUD. There is one simulation and animation path.

## Controls

| Action | Controller | Keyboard / mouse |
|---|---|---|
| Mount / step off | Triangle / Y (host action) | B |
| Push / mongo | A / X | W |
| Brake | B | S |
| Steer / spin | Left stick | A / D |
| Powerslide | Left stick down-left / down-right | Hold C; A / D chooses the side |
| Load / ollie | Right stick down, then up | Hold Space, release to pop |
| Flick-It | Right stick gesture | Hold left mouse button and flick |
| Manual / nose manual | Right stick partly down / up | Hold the mouse gesture part-way |
| Pump (ground) / grab (air) | Left / right trigger | Q / E |
| Look | Host camera controls | Mouse when not flicking |

Regular kickflips flick down then up-left; heelflips finish up-right. Goofy mirrors the gestures. The original
seven gesture files and both animation banks are included in the game's runtime bundle. Grind selection,
manuals, reverts, landing assists, bails and recovery use the recovered graphs and physical state machines.

## Game integration

- An `ACharacter` implements `ISkateRider`: prepare for mounting, menu/input gating and mouse sensitivity.
- Its movement component calls `PhysSkate` for custom movement mode 2 and leaves actor rotation to skating
  while `IsRiding()`, including a bail.
- Its animation proxy evaluates `GetRetailPose()` directly as local bone transforms. The retargeter preserves
  the host bind lengths, head facing and shoe scale, then fits the foot contacts with two-bone IK.
- Its camera may use `GetRetailCamera()`. The returned FOV is vertical; convert to horizontal for Unreal.
- `USkateSettings` supplies the deck/truck/wheel meshes, board sound folder, fall sounds, difficulty and tuning.
- Register rail polylines with `USkateRailSubsystem`. Static mesh triangles within 100 m supply collision.

The board contract is +X nose, +Z up, deck top 9.05 cm above the ground. The native adapter fits the individual
truck and wheel pivots and drives them with solved source bones. The runtime uses metres and a left/up/forward
frame; the bridge converts positions, rotations and collision winding to Unreal centimetres.

`Difficulty` accepts `easy`, `normal` or `hardcore`; `TruckTightness` ranges from 0 to 1. `PopHeightScale` scales
stock launch-height presets and `AirSpinScale` scales spin targets and manual spin acceleration/velocity curves.
`PushPowerScale` and `PushSpeedScale` adjust native push propulsion and speed limits. All default to 1 in the
plugin; the host game selects its own tuning. The recovered constraints and animation timing remain active.

Mounting starts at the player's feet, aligns with running velocity and transfers that velocity to the whole
physical assembly. Each activation identifies its poses so an old response cannot move a newly mounted rider.
The retained worker loads banks once per world; stowing suspends it and world shutdown terminates it.
Missing/corrupt runtime files report an error and leave the player walking.

See [NATIVE_PORT.md](NATIVE_PORT.md) for provenance and remaining adapter boundaries.

Grounded triggers compress the rider for the recovered pumping controller; releasing extends. In the air they
grab. The retargeter uses skinned contact samples during bails to keep a differently proportioned visual rider
above the supporting scene. Rider LODs should retain CPU vertex data for these contact samples.
