# Atelier Skate

Skateboarding with controls modelled on EA's *skate.* series: the left stick steers and spins, the right stick (or the
mouse with the left button held) does every trick (**Flick-It**), the triggers grab. Manuals, grinds and slides on
rails, ledges and coping, powerslides, vert, bails, a trick line with a score, and the board's rolling and trick sounds.
Experimental. A game documents its own side (rider clips, parks, checks) in its docs.

| Piece | What |
|---|---|
| `USkateComponent` | the ride: board frame, ground, air, grinds, bails, input, clip choice, sounds, score |
| `ISkateRider` | what the component needs from the character (clips by role, mount hook, input gates, contacts file) |
| `SkateNative.h` / `SkateNativeTuning.h` | ported controllers, retail point curves and 78 Flick-It patterns |
| `FSkateFlick` (`SkateFlick.h`) | input/trick types and crouch/manual input conditioning |
| `USkateRailSubsystem` (`SkateRails.h`) | every grindable line in the world |
| `USkateSettings` | board meshes, sound folder, fall sounds, rolling resistance by material name |

## What a game provides

- **A rider.** An `ACharacter` implementing `ISkateRider`, which creates a `USkateComponent` and calls
  `Initialize(this)` in `BeginPlay`. Clips are found by role (`platform/conventions/clip-roles.toml`: `SkateStance`,
  `SkateOllie`, ... and their `<Role>Goofy` copies, plus `Idle` and `Roll` for fallbacks and bails). Missing skate
  clips fall back to the stance, so the ride can be tested before every clip is authored.
- **A movement mode.** Its movement component's `PhysCustom` calls `PhysSkate(Dt)` when
  `CustomMovementMode == USkateComponent::MovementMode`.
- **An anim graph** that plays `GetSequence()` at `GetClipTime()` (restart on `GetSerial()` changes, blend
  `GetBlendTime()`), blends `GetCrouch()` and `GetLean()`, and carries the limbs with the deck through
  `FSkateRiderNode` (AtelierAnimation) using `GetDeckCarryWorld()` and `GetLimbContact()`.
- **Rails.** `GetWorld()->GetSubsystem<USkateRailSubsystem>()->Add(...)` for every grindable line it builds. Actors
  tagged `SkatePark` roll as smooth park concrete.
- **Settings** in DefaultGame.ini under `[/Script/AtelierSkate.SkateSettings]`: `DeckMesh`, `TruckMesh`, `WheelMesh`
  (the board contract: deck top 9.05 cm above the ground, X toward the nose, wheels at +-18 cm, 2.65 cm radius),
  `SoundFolder` (loops `roll_01`, `grind_01`, `slide_01`, `skid_01`, `scrape_01`; one-shot banks `pop`, `land`,
  `catch`, `push`, `flick`, `clatter` as `<cue>_01..08`), `FallSounds`, `Surfaces`.

Scripted input (`SetScriptedInput`), `PlaceAt`, `Launch`, `GetStatus` and `GetDebug` exist for QA scenarios and the live
bridge; `-skatedebug` logs every change of mode with its reason and the wheel probes.

## Controls

| Action | Controller (skate.) | Keyboard + mouse (skate. on PC) |
| --- | --- | --- |
| Get on / off the board | D-pad down (on or off); Y (Triangle) steps off | B |
| Push (tap = one push, hold = keep pushing) | A (Cross); X (Square) pushes mongo | W |
| Foot brake | B (Circle) | S |
| Steer / carve | left stick left-right | A / D |
| Powerslide (at speed) | left stick down (or B above 16 km/h) | C (or S above 16 km/h) |
| Kickturn (stopped) | left stick left-right | A / D |
| Revert (right after a landing) | left stick down | C |
| Tricks (Flick-It) | right stick | hold left mouse button and move the mouse |
| Spin | hold left stick left/right as you pop, keep holding in the air | A / D |
| Left hand grab / right hand grab | LT / RT (L2 / R2) | Q / E |
| Manual / nose manual | right stick part-way down / part-way up, hold | hold left mouse, mouse part-way down / up |
| Grind or slide | land on a rail, ledge or coping; right stick picks the grind | same, with the mouse |
| Ollie with keys only | — | Space: hold to crouch, release to pop |

The camera sits lower and closer than on foot and swings in behind the line of travel. The right stick is Flick-It
while riding, so only the mouse (without the button) looks around; the camera returns two seconds after the last look.

**The mouse as the right stick** (skate. on PC): hold the left button, and a quick movement points the stick the way
the hand moved (a swipe at 45 degrees is a diagonal flick, not a trip round the stick's edge); a slow movement moves
the stick gradually, which is how a manual is held part-way. A tenth of a second after a flick the stick springs back
to the centre, as a thumbstick does (the load's pull does not), so a manual pulled after a kickflip starts from the
middle, not from the corner the flick left it in. Letting go of the button centres the stick. The scale follows the
mouse sensitivity setting (about 1.5 cm of travel is a full stick at the default).

**The pad's right stick is read in its real positions.** The project's 0.25 dead zone on each axis (DefaultInput.ini)
made half-way read as a third and bent the diagonals; skating undoes it and keeps a small round dead zone (0.15)
instead, so the numbers on this page are where the thumb actually is.

## Flick-It

Directions are the right stick as seen by the player: **D** pulled toward you, **U** pushed away, **L/R** left/right,
diagonals **DL, DR, UL, UR**. Everything below is **regular stance**; goofy mirrors left and right. Riding fakie
prefixes the name ("Fakie Kickflip"), and a nollie pops from the nose.

The recognizer uses the original `skater.pat` points and tolerance circles: 78 path variants producing 30 named
ollie/nollie-family tricks. It scores matching paths by their length, distance error and elapsed samples, and computes
strength from sample timing. Holding the loaded point does not age the gesture. All recognition runs at 60 Hz.
The exact primary paths are exposed in `live.FLICKS`; the committed definitions are in `SkateNativeTuning.h`.

| Motion (approximate; regular stance) | Trick |
| --- | --- |
| D, then U | Ollie |
| D, then UR | Kickflip |
| D, then UL | Heelflip |
| D, DR, then UR | Backside pop shove-it |
| D, DL, then UL | Frontside pop shove-it |
| L, D, then UR | Varial kickflip / 360 flip, depending on the starting point and scoop |
| R, D, then UL | Varial heelflip / laser flip |
| R, D, then UR | Hardflip / 360 hardflip |
| L, D, then UL | Inward heelflip / 360 inward heelflip |
| U, then D | Nollie; other nose-loaded paths have their own authored variants |

Pop height uses the retail speed/strength curves and subtracts the rider's current COM height before calculating the
launch impulse. It also responds to ramp inclination. The host game supplies the COM estimate and its own animation.
See [NATIVE_PORT.md](NATIVE_PORT.md) for exactly which computations are ported and which remain UE adapters.

Flip and shove rotations are the board's; the rider's body only spins with the left stick. Tricks can be done off
any pop: from flat, a manual, a grind (flick to pop out) or the lip of a ramp.

**Manuals.** Tilt the right stick part-way down (manual) or up (nose manual), 30–75% of its travel, and hold it. A
pitch controller follows that stick position with the retail proportional, integral, derivative and procedural-noise
settings. The needle reflects deck pitch. Excess tilt scrapes and ends the manual; neutral releases it. Flick to pop
out of a manual. A stationary half-stick no longer loses balance due to an unrelated random timer.
Hold the manual on the way down and the trick lands straight into it: the board tips onto its back wheels (front
wheels for a nose manual) in the air and touches down in the manual, with no flat landing first. The tilt eases in and
out (into a manual, and setting the nose down after one) rather than snapping.

**Grabs.** In the air, hold LT (left hand) or RT (right hand). The right stick picks the spot as the grab starts:

| Hand | Stick neutral | Stick up | Stick down |
| --- | --- | --- | --- |
| Back hand (RT regular) | Indy | Stalefish | Tail grab |
| Front hand (LT regular) | Melon | Nose grab | Method |
| Both | Double grab (Indy + Melon) | | |

Let go before touchdown: landing on a grab still held after 0.2 s bails; one let go on the landing frame just lets go.

**Grinds and slides.** Land on a rail, a ledge or coping with the trucks near it. The board's angle to the rail and the
right stick at the moment of contact pick the trick:

| Board angle to the rail | Stick neutral | Stick down | Stick up | Stick down-left / down-right | Stick up-left / up-right |
| --- | --- | --- | --- | --- | --- |
| near parallel (< 35°) | 50-50 | 5-0 | Nosegrind | Smith / Feeble | Crooked / Overcrook |
| across (> 35°) | Boardslide (lipslide if the tail crossed first) | Tailslide | Noseslide | | |

Toe side toward the rail is frontside (FS), heel side backside (BS); landing on it backwards is a fakie grind. The
turn that puts the board across the rail belongs to the slide and is not named as a spin. Left stick balances (a
needle as for manuals). Flick to pop off (any trick: "kickflip out"); the end of the rail rolls you off. Losing balance
drops you off the side, not a bail. The capture: descending, a truck or the deck middle within 24 cm of the rail in
plan and 8 cm below to 22 cm above it, moving along it at 1 m/s or more.

**Spins.** Hold the left stick left or right before the pop to wind up and keep holding in the air (up to 420°/s,
reached in about a third of a second: a 360 needs a good pop). The spin is named
by the total turn at landing (180, 360, 540), frontside or backside by its direction. Landing backwards is fine: you
ride away fakie.

**Bails.** Landing sideways (board more than 60° off the direction of travel and not fakie; from 25° to 60° off it
rolls away but the wheels scrub round to the line and lose up to 30% of the speed), landing before the flip
is caught, landing on a grab still held, a drop over 17 m/s, tripping on a step at speed, or hitting a wall hard. The
board tumbles on and rolls away; at speed he tumbles through his dive-roll, slower he sits down hard (the knock-down
clips), and then he is back on the board where he stopped.

**Scoring.** Every trick, grind and manual adds to the combo line; the combo ends a third of a second after a plain
landing (a manual or grind keeps it going) and scores its points times the number of tricks.

## Physics (native)

`USkateComponent` owns the ride; the game's movement component gives it a custom movement mode
(`USkateComponent::MovementMode`) whose `PhysCustom` calls `PhysSkate`.

- **Board frame.** The actor is the board: its origin is the board's ground point under the deck centre, its axes are
  the board's (X nose, Y toe side for regular, Z up). The capsule turns with the board on ramps. The mesh and the board
  hang off this frame; the board's procedural pitch, roll and flips turn about points of the board.
- **Ground.** Four wheel traces along -Z of the board frame find the surface; the board takes the average of the
  surfaces' own normals under the wheels (a plane through the hit points tips on every seam) at the hits' height.
  Gravity along the surface, rolling resistance by the material under the board (`USkateSettings::Surfaces`: for example roads,
  concrete, wood and the park 1x, rough lanes 4x, sand and dirt 12x, grass 20x, mud 25x), air drag, lateral grip (the wheels roll only along the
  heading). The native steering/truck curves turn the heading; finite lateral grip redirects momentum, with a lateral acceleration cap in the UE adapter. A wheel meeting a
  rise over 3.5 cm that is not a ramp coming up ahead is a step: a bump, or a trip at speed.
- **Transitions and edges.** Concave (the leading wheels' surfaces tip back against the travel): the board always
  follows, up to vertical; carving leans the deck a few degrees over its trucks. Convex: it leaves the ground when the leading wheels' ground falls away (over 1 cm) faster
  than gravity can bend the path (v^2 x curvature > g x cos + 3.5 m/s^2); with no ground at all under the wheels (a lip,
  the coping, a kicker) it simply flies.
- **Air.** Ballistic at the retail 9.8 m/s^2, spins integrate a yaw rate about the board's up. The board turns toward the normal
  of the landing surface found by sweeping the flight path; off a wall (a vert air) it stays square to the wall and
  touches back down on it, riding away fakie unless it spun.
- **Landing.** Checks the angle between board heading and velocity (fakie allowed), the flip/shove state, grabs and the
  surface normal. A good landing keeps the speed along the new surface.
- **Grinds.** Rails are whatever the game adds to `USkateRailSubsystem` (a park's rails, ledges and coping, road guardrails). While
  falling, a truck within 22 cm horizontally and 0–35 cm above a rail captures the board; it then moves along the rail
  (grinds lose speed slowly, slides faster), with a balance needle.
- **Pushing** uses the retail held-time/strength curves and speed-target force limits only while the foot is planted.
  Pushing stops at 8.5 m/s (30.6 km/h); downhill travel can exceed that, with a UE safety ceiling of 28 m/s.
  The existing Cairo push clip supplies contact and swing timing. Fakie uses the opposite stance's pushing clip.
- **Pumping** uses the change in rider COM height and ground-normal angular speed. Crouch into a transition and
  extend through it (release the right stick toward neutral). Flat-ground crouching cannot generate speed.
- **Landings** retain the board heading and tangent velocity. Retail landing quality classifies sideways speed and
  remaining spin; the UE grip adapter then recovers alignment over time.
- **Timing** is a fixed 60 Hz accumulator for input recognition and gameplay, with 120 Hz collision substeps. Animation and audio are
  presented each render frame. At most 0.1 s is simulated after a hitch; teleport/mount resets controller history.
- **Rider.** The mesh stands by its Root bone on the board's ground point, turned so the nose is on the rider's left
  (regular) or right (goofy). The anim graph plays the state's clip at the component's time, blends the load crouch
  and the carve lean over it, then carries every limb the clip has on the board through the board's motion
  (`FSkateRiderNode`, two-bone IK), so feet stay on a pitching or leaning deck. A flip's roll and shove are left out of
  that motion: the feet are off the board for them, and carrying the feet round with the board twisted the legs. The
  flip clip is timed by the board rather than the clock: the ollie's snap for 0.04 s, the feet leave the board in the
  next 0.06 s before it turns, stay up while it turns (however long the trick) and catch it as it finishes; a second
  flick in the air turns the board on from where it is and lifts the feet again.

