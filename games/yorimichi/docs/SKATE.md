# Skateboarding (flick-it, game-r17)

> Moved from the prototype repository on 29 September 2026. Paths are translated to this repository where the file moved; paths still starting with `japan/` or `output/imagegen/` refer to the prototype archive (authoring tools, earlier revisions, review images). See [docs/MIGRATION.md](../../../docs/MIGRATION.md).

Skateboarding comes back for the player (Warm Original) with controls modelled on EA's *skate.* series: the left stick
steers and spins, the right stick does every trick (**Flick-It**), the triggers grab. This page is the design and the
contract between the three parts: the native skate system (C++), the rider clips (Blender, game-r17) and the skate pier
with its board (Blender + Unreal import).

Status (28 Sep 2026): playable end to end and not yet reviewed by the user. The ride, Flick-It with fourteen tricks and
their nollie and fakie versions, spins, grabs, manuals, grinds and slides on rails, ledges and coping, powerslides, vert,
bails, sounds, the rider clips (game-r17) and the skate pier all work in the game; `games/yorimichi/scenarios/skate.py` passes 22/22
against the running game. A filmed run is in `build/yorimichi/skatefilm/<take>/showreel.mp4` (see Checks).
`-skatedebug` logs every change of mode with its reason and the wheel probes.

Not done: touch controls for the phone stream (it still knows only the old cruiser), switch stance (fakie is
supported), tweaked grabs and lip tricks. The painted world map does not show
the pier; its travel pin does.

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

Pull the stick back to crouch (the load). The pop comes when the stick is flicked into the upper half. How hard the flick
is (the stick's speed, or the mouse swipe's) sets most of the pop height and how long the load was held (up to 0.3 s)
the rest: 28 cm for a gentle flick up to 1.2 m for a hard one (mouse swipes measured 57, 80 and 104 cm for gentle,
medium and hard). A hard flick clears a handrail with room.
A flick has to reach the rim within 0.25 s of leaving the load; a side flick (shove-it) has to rest at the side for
50 ms or be let go there. U and D are 60 degrees wide, so a straight flick is an ollie and a diagonal has to be meant.
While loaded, the left stick still steers (three quarters of the usual turn) and winds up a spin for the pop.

| Motion | Trick |
| --- | --- |
| D, then U | Ollie |
| D, then UL | Kickflip |
| D, then UR | Heelflip |
| D, then L | Backside pop shove-it |
| D, then R | Frontside pop shove-it |
| R, D, then U (sweep into the load from the right) | 360 backside shove-it |
| L, D, then U | 360 frontside shove-it |
| DR, then UL | Varial kickflip |
| DL, then UR | Varial heelflip |
| D, DL, then U | Hardflip |
| D, DR, then U | Inward heelflip |
| R, D, then UL | 360 flip (tre flip) |
| L, D, then UR | Laser flip |
| D, then UL, UL again before landing | Double kickflip (a second flick in the air adds a rotation) |
| U, then D / DL / DR / L / R … | Nollie, nollie kickflip, nollie heelflip, nollie shove-its … (the same table turned upside down) |

Flip and shove rotations are the board's; the rider's body only spins with the left stick. Tricks can be done off
any pop: from flat, a manual, a grind (flick to pop out) or the lip of a ramp.

**Manuals.** Tilt the right stick part-way down (manual) or up (nose manual), 30–75% of its travel, and hold it. A
balance needle drifts slowly; keep it centred with small stick movements (balanced is a little past half-way). Held at
half-way without correcting, a manual lasts about 5 s; a tenth of the travel off, about 2 s. Too far and the tail (or
nose) touches and you ride out of it. Flick to pop out of a manual.
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

`USkateComponent` owns the ride; `UJapanCharacterMovement` gets a custom movement mode (Skate) that calls it.

- **Board frame.** The actor is the board: its origin is the board's ground point under the deck centre, its axes are
  the board's (X nose, Y toe side for regular, Z up). The capsule turns with the board on ramps. The mesh and the board
  hang off this frame; the board's procedural pitch, roll and flips turn about points of the board.
- **Ground.** Four wheel traces along -Z of the board frame find the surface; the board takes the average of the
  surfaces' own normals under the wheels (a plane through the hit points tips on every seam) at the hits' height.
  Gravity along the surface, rolling resistance by the material under the board (roads, concrete, wood and the park
  1x, rough lanes 4x, sand and dirt 12x, grass 20x, mud 25x), air drag, lateral grip (the wheels roll only along the
  heading). Steering turns the heading and the velocity together about the normal, less at speed. A wheel meeting a
  rise over 3.5 cm that is not a ramp coming up ahead is a step: a bump, or a trip at speed.
- **Transitions and edges.** Concave (the leading wheels' surfaces tip back against the travel): the board always
  follows, up to vertical; carving leans the deck a few degrees over its trucks. Convex: it leaves the ground when the leading wheels' ground falls away (over 1 cm) faster
  than gravity can bend the path (v^2 x curvature > g x cos + 3.5 m/s^2); with no ground at all under the wheels (a lip,
  the coping, a kicker) it simply flies.
- **Air.** Ballistic at 11 m/s^2, spins integrate a yaw rate about the board's up. The board turns toward the normal
  of the landing surface found by sweeping the flight path; off a wall (a vert air) it stays square to the wall and
  touches back down on it, riding away fakie unless it spun.
- **Landing.** Checks the angle between board heading and velocity (fakie allowed), the flip/shove state, grabs and the
  surface normal. A good landing keeps the speed along the new surface.
- **Grinds.** Rails come from the skate pier's `park.json` (rails, ledges, coping) and the road guardrails. While
  falling, a truck within 22 cm horizontally and 0–35 cm above a rail captures the board; it then moves along the rail
  (grinds lose speed slowly, slides faster), with a balance needle.
- **Pushing** adds speed only while the pushing foot is on the ground (plant to release in the push clip, stretched to the
  distance rolled so the foot stays planted), about the same for every stroke and fading to nothing at 1250 cm/s
  (45 km/h); hills can take you faster (hard limit 2200 cm/s). Held from a standstill: 240 cm/s after 1 s, 600 after
  3 s, 830 after 6 s. Held, it keeps pushing: after the stroke the foot swings straight back to its plant beside the
  front truck (the clip from its lift at 0.72 s, blended to its swing at 0.21 s) instead of returning to the tail, and
  the swing plays at 0.28 speed so there is a push about every 0.6 s, not a scramble. Rolling fakie, a push is a switch
  push: the other stance's clip (the other foot on the ground), so it drives the board the way it is rolling.
- **Rider.** The mesh stands by its Root bone on the board's ground point, turned so the nose is on the rider's left
  (regular) or right (goofy). The anim graph plays the state's clip at the component's time, blends the load crouch
  and the carve lean over it, then carries every limb the clip has on the board through the board's motion
  (`FSkateRiderNode`, two-bone IK), so feet stay on a pitching or leaning deck. A flip's roll and shove are left out of
  that motion: the feet are off the board for them, and carrying the feet round with the board twisted the legs. The
  flip clip is timed by the board rather than the clock: the ollie's snap for 0.04 s, the feet leave the board in the
  next 0.06 s before it turns, stay up while it turns (however long the trick) and catch it as it finishes; a second
  flick in the air turns the board on from where it is and lifts the feet again.

## Rider clips (Blender, game-r17)

Authored on the game-r16 revision with `games/yorimichi/assets/characters/tools/warm_rig.py`, saved as game-r17 with manifest roles, exported with
`export_warm_original_unreal.py -- --revision game-r17 --clips <list> --clips-only --report export-skate.json` and
installed by `Scripts/import_warm_skate.py` into `DA_WarmOriginal.SkateActions`.

**Frame.** The rig faces +X (Blender), left +Y, up +Z; the Root bone stays at the origin on the ground. The board lies
across the rider: its long axis along Y with the **nose toward +Y (regular: left foot forward)**, the toe edge toward
+X, **deck top at Z = 9.05 cm**, deck centre above the origin. In every clip the board is at this rest place; the game
moves it (pop, manual tilt, flips) and moves the feet with it.

**Board on screen.** A board 9 cm over the ground at speed left a speckled halo and a ghost copy of itself on the
ground: Lumen's short-range AO counted it as a wall down to the ground, and its temporal history lagged behind. Short-
range AO now ignores occluders floating more than 4% of the pixel's depth in front
(`r.Lumen.ScreenProbeGather.ShortRangeAO.HorizonSearch.ForegroundSampleRejectDistanceFraction=0.04`, engine default
0.3); the landscape changes by 2-4 grey levels inside foliage. A faint TAA trail of the deck remains at speed.
(Switching `r.Lumen.ScreenProbeGather.ShortRangeAO.Temporal` off at runtime crashes UE 5.8's renderer.)

**Board (cm, deck-local: origin at the centre of the deck top, +X nose, +Y toe side, +Z up).** Deck 80 × 20.5, kicks
rise over the last 13 cm to +4.5 cm at the tips (x = ±40), concave 0.9 cm, thickness 1.2. Truck kingpins at x = ±18
(the wheelbase is 36), axles at z = -6.35, wheel centres at y = ±9.3, wheel radius 2.65 (ground at z = -9.05). In the
Blender rider frame, deck-local (x, y, z) is (y, x, z + 9.05).

**Foot spots on the deck (deck-local).** Riding: front foot centre (+16, +1), back foot (-21, +1). Ollie load: back
foot's ball on the tail (-31, +1) on the kick, front foot just behind the front bolts (+8, +1). Nollie load: front
foot's ball on the nose (+31, +1), back foot (-8, +1). Front foot turned about 55° from the board axis toward the nose,
back foot about 80°, toes toward the toe edge (+Y deck-local). Soles on the grip, no penetration.

**Contacts.** For each clip the manifest lists, per foot and per hand, the intervals when it is on the board. The game
maps those limbs through the board's current transform (IK) and leaves the others to the clip.

**Clips** (60 fps; loops must close; goofy versions are the regular ones mirrored, suffix `Goofy`):

| Role | Length | What it is |
| --- | --- | --- |
| SkateStance | 2.0 s loop | riding stance: knees soft, weight centred, arms relaxed and a little away from the body, palms toward the body, head turned to the nose; slow breathing sway |
| SkateStanceFakie | 2.0 s loop | the same, looking back over the right shoulder toward the tail |
| SkatePush | 1.0 s loop | front foot turns to point along the board, body turns forward, back foot plants on the ground on the toe side beside the front truck (plant 0.30 s), strokes back 44 cm (release 0.62 s), lifts and returns to the tail; ends in the stance |
| SkateBrake | 0.4 s, then hold the last frame | back foot slides off the tail and drags its sole flat on the ground behind, weight on the front leg |
| SkateCrouch | 0.2 s hold | the ollie load: deep crouch, back foot on the tail, front foot behind the front bolts, arms a little forward |
| SkateNollieCrouch | 0.2 s hold | the nollie load, front foot on the nose |
| SkateOllie | 0.45 s | pop and rise, from SkateCrouch to the air tuck: back ankle snaps (board pitches nose-up about the rear wheels, 30° at 0.05 s, level again at 0.24 s), front foot drags up the grip to (+24, +1) by 0.20 s, knees pull up; ends in SkateAir |
| SkateNollie | 0.45 s | the same popped from the nose |
| SkateAir | 1.0 s loop | the air tuck: knees up (feet on the deck, pelvis about 18 cm lower than in the stance), arms out for balance, eyes ahead and down |
| SkateFlip | 0.45 s | the flick for flip tricks and shove-its, from SkateAir: both feet leave the deck by 0.08 s (front foot kicks forward and up, back foot up), about 15 cm above the grip at 0.2 s, come back down to catch at 0.38 s; ends in SkateAir |
| SkateLand | 0.35 s | touchdown from SkateAir: absorb (pelvis 15–20 cm down at 0.12 s), rise to the stance |
| SkateManual | 1.0 s loop | balancing on the back wheels: hips over the back foot, front leg straighter, arms out, small balancing wobble (the game tilts the board nose-up 11°) |
| SkateNoseManual | 1.0 s loop | the same over the front wheels |
| SkateGrind | 1.0 s loop | 50-50: crouched, arms out, looking down the line, balancing |
| SkateGrindTail | 1.0 s loop | 5-0 / smith / feeble: weight back |
| SkateGrindNose | 1.0 s loop | nosegrind / crooked: weight forward |
| SkateSlide | 1.0 s loop | boardslide / lipslide / nose- and tailslides: lower, wider arms, looking along the rail (toward +X) |
| SkateGrabIndy | 0.5 s (reach by 0.18 s, hold) | right hand grabs the toe edge between the feet |
| SkateGrabMelon | 0.5 s | left hand grabs the heel edge between the feet |
| SkateGrabNose | 0.5 s | left hand to the nose |
| SkateGrabTail | 0.5 s | right hand to the tail |
| SkateGrabMethod | 0.5 s | left hand on the heel edge, knees bent back so the board comes up behind |
| SkateGrabStalefish | 0.5 s | right hand behind the back leg to the heel edge |
| SkateGrabDouble | 0.5 s | right hand indy and left hand melon |
| SkatePowerslide | 0.6 s, hold the end | board turned across the travel (the game turns it), weight back toward the heel edge, knees bent, arms forward |
| SkateCarveToe | 0.5 s hold | leaning into a toe-side turn: knees and hips toward +X |
| SkateCarveHeel | 0.5 s hold | leaning into a heel-side turn: sitting back toward -X |

Bails reuse the dive-roll and the knock-down clips (Roll; SitDown, SitIdle, StandUp). What the rider clips actually do,
where they depart from this contract and their checks: `games/yorimichi/assets/characters/warm-original/README.md`.

## Skate pier (Blender + Unreal)

A concrete skate plaza on a pier off the beach south of the spawn road, reached by a concrete path that leaves the
road through the guardrail gap at x = -150 m and runs downhill to the pier; "Skate pier" is on the world map's travel
list. `games/yorimichi/world/regions/skatepark/` builds it, the board, and `park.json` (20 grindable lines, spawn points and the vegetation
clearance); `games/yorimichi/world/regions/skatepark/README.md` has the features and dimensions. The road guardrails are grindable too.

## Sounds

`games/yorimichi/assets/audio/skate/make.py` builds `games/yorimichi/assets/audio/skate/`: rolling, grind, slide, powerslide and foot-brake loops
synthesised as shaped noise (seamless), pops, landings, catches and bail clatter around two wooden stick hits from the
Sonniss masters, push scuffs and flip whirrs. The board carries the loops (volume and pitch follow the speed) and plays
the one-shots.

## Build

From the repository root, Unreal closed for the imports:

```sh
atelier build yorimichi unreal.world                                                        # pier, path, board: build + import
blender -b --python games/yorimichi/assets/characters/tools/warm_skate_clips.py -- --parent game-r16 --revision game-r17   # rider clips
blender -b --python games/yorimichi/assets/characters/warm-original/export_unreal.py -- --revision game-r17 --clips <Skate* roles> --clips-only --report export-skate.json
<python with numpy> games/yorimichi/assets/audio/skate/make.py                               # sounds
# then with UnrealEditor-Cmd -run=pythonscript: Scripts/import_warm_skate.py, Scripts/import_skate_audio.py
atelier build yorimichi unreal.compile
```

## Checks

- `python3 games/yorimichi/scenarios/skate.py [name] [--only case,...]` with the game running (`atelier play yorimichi`): 22 cases through
  the live bridge, scripted skate. controls and simulated keys and mouse; report in `build/yorimichi/skateqa/`.
- The showreel: `atelier live py "TAKE='take2'"`, then `atelier live py - <
  games/yorimichi/scenarios/skate_showreel.py`, wait for `build/yorimichi/skatefilm/<take>/done.json`, then
  `<python with numpy> games/yorimichi/scenarios/skate_mix_showreel.py build/yorimichi/skatefilm/<take>`: eight shots filmed at a fixed 60 fps
  step with their sound.
- Live verbs (`games/yorimichi/live/python/yorimichi_live.py`): `live.skate()`, `live.skate_park()`, `live.skate_input(...)`,
  `live.flick(name)`, `live.skate_script(steps)`, `live.skate_state()`, `live.L.skate_launch(v)`,
  `live.L.skate_goofy(b)`, `live.L.input_key(key, event, value)`, `live.L.hold_camera(s)`; `games/yorimichi/scenarios/skate_live_skate.py`
  adds park coordinates and recorded scenarios.
