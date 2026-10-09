# Controller controls

The game plays with a keyboard and mouse or with a gamepad, through one set of Enhanced Input actions
(`AWandererCharacter::BuildInput`, `WandererCharacter.cpp`). The HUD shows hints for whichever is in use: controller
hints, lettered for the connected pad, while a gamepad is attached, and keyboard hints otherwise. Skating has its own
controls: see [SKATE.md](SKATE.md). So does skiing: see the
[Ski plugin](../../../platform/engine/Plugins/Activities/Ski/README.md#controls).

## Bindings

| Action | Keyboard and mouse | Xbox | PlayStation | Nintendo |
|---|---|---|---|---|
| Move | WASD or arrows | Left stick | Left stick | Left stick |
| Look | Mouse | Right stick | Right stick | Right stick |
| Sprint (hold) | Left Shift | Left stick click | L3 | Left stick click |
| Walk (hold) | Left Alt or J | | | |
| Jump / double jump / paraglider | Space | A | Cross | B |
| Swim dash | F | X | Square | Y |
| Dodge (side hop, backflip) | Left Ctrl | B | Circle | A |
| Crouch | C | Right stick click | R3 | Right stick click |
| Get on / step off the skateboard | B | Y (tap) | Triangle (tap) | X (tap) |
| Bike out and on / off and parked (stopped) | V | Y (hold 0.4 s) | Triangle (hold) | X (hold) |
| Skis on / off (offline; standing on the ground, off when not crashed or in the air) | N | LB | L1 | L |
| Skateboard to the hand / put it away (Ride backend) | G | D-pad Right | D-pad Right | D-pad Right |
| Interact, board the zeppelin | E | D-pad Down | D-pad Down | D-pad Down |
| Sailboat / step ashore | K | D-pad Up | D-pad Up | D-pad Up |
| Attack (hold to charge) | Left click | RT | R2 | ZR |
| Guard and lock on (hold); with Jump, parry | Right click | LT | L2 | ZL |
| Draw / sheathe the sword | R | D-pad Left | D-pad Left | D-pad Left |
| Flight speed aboard, choose the stop before boarding | [ / ] | LB / RB | L1 / R1 | L / R |
| Map | M | View | Touchpad click | Minus |
| Settings | Esc | Menu | Options | Plus |
| Wave | Q | | | |
| Release the mouse | Tab | | | |
| Screenshot | F12 | | | |

Getting on the board while running carries the running speed onto it. Riding, the right stick (or the mouse with the
left button held) is Flick-It, not the camera. Skiing, the right stick winds up spins and the camera follows the
direction of travel; `ski.Park` in the console puts the skis on at the top of the terrain park on the volcano. On the sailboat the left stick steers and raises or lowers the sail.
On the bike (see [BIKE.md](BIKE.md)) the left stick pedals, brakes and steers, a press of Sprint (the left stick) pedals hard until pressed again or he stops pedalling, Jump hops, Crouch
is a skid stop, Attack rings the bell and Wave waves.

The player plays the merged move set (Cairo and Modori; see [the move set](../assets/characters/adventure/README.md)).
Jump in the air is the double jump; pressed again, it opens the paraglider. Roll is the dodge (a side hop with the
stick left or right, otherwise a backflip). Parry held draws the sword, guards with it and locks on; Jump while
guarding parries. Dash is the swim dash. Every playable character uses its merged move set.

The map takes the controller while it is open: left stick or D-pad to choose a pin, the bottom face button to travel
there, the right face button to close, LB / RB (L1 / R1, L / R) to zoom and the right stick to pan when zoomed in. The
map and settings buttons pass through to the game, which closes the map; every other gamepad button is swallowed.

Right-stick look: UE 5.8's `FSceneViewport` negates `Gamepad_RightY` before player input, and the project disables
legacy input scales, so `StickLook` applies `-Delta.Y` to the pitch. Right stick up looks up; mouse look keeps its own
sign.

## Controller hints

Every 0.25 s the HUD reads `FSlateApplication::IsGamepadAttached` and the engine's connected-device registry, so a pad
attached before startup or unplugged later switches the hints without a button press. Device names pick the lettering:
PS4, PS5, DualShock or DualSense for PlayStation; Xbox or XInput for Xbox; Nintendo or Switch for Nintendo. An unknown
pad gets physical positions ("Bottom button", "Right button", ...) rather than guessed letters. On macOS, Unreal
names PS4, PS5 and Xbox pads through Apple's GameController backend, and its PlayStation `Special Left` is the touchpad
click.

The hints follow the situation: sailboat steering and sail, zeppelin boarding and flight speed with the interaction
button, the sword's attack, parry and draw while it is installed, the move set's double jump and paraglider, dodge,
the sword guard and swim dash,
and the skate controls while riding. With a controller the mouse-release tip is hidden; stamina rings and the FPS
counter stay. The two hint rows measure their text and shrink to fit the viewport.

## Debugging

- `japan.ControllerHUD` forces the hint lettering for visual checks: `-1` automatic (default), `0` keyboard, `1` Xbox,
  `2` PlayStation, `3` Nintendo, `4` generic. It changes labels only (no input, no fake connection) and is not saved.
  Style changes log `CONTROLS HUD style=<n> automatic=<0|1>`.
- `-controllertrace` on the Unreal command line logs `CONTROLLER TRACE` lines for gamepad keys and Esc at each step:
  Slate key-down (editor binary), viewport press and release, and every button action's start and completion with the
  ready, menu and movement-lock state. It only observes. Follow a press through all three before blaming the bindings:
  an action can rightly refuse a press during a locked action, such as a jump pressed before a roll finishes.
