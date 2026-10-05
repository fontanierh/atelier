# Skateboarding

Cairo can ride a skateboard anywhere there is ground, with skate.-style controls: Flick-It tricks on the right stick
or the mouse, manuals, grinds, powerslides, pumping, airs and bails. The riding runs in the platform's
[Skate plugin](../../../platform/engine/Plugins/Activities/Skate/README.md), which simulates the board and a physical
rider, then fits the solved pose onto Cairo and the board meshes. This page covers what the game adds: the controls
as the player sees them, the tuning, the board, the skate pier, the sounds and the checks. The plugin's
[runtime reference](../../../platform/engine/Plugins/Activities/Skate/RUNTIME.md) covers the native data and its
verification.

```sh
uv run atelier build yorimichi skate.runtime unreal.compile   # verify the tracked native data, compile
uv run atelier play yorimichi
uv run atelier qa yorimichi skate                              # with the game running
```

## Getting on and off

**Triangle / Y** (keyboard **B**) gets on or off the board; the on-foot controls line shows it whenever the board is
available. Getting on works while standing, walking or running on the ground (crouching stands up first), but not
in a menu, as a zeppelin passenger or with the sailboat out. It sheathes the sword. Running onto the board keeps the
position, the direction of travel and the speed. Getting off works while the board is on the ground (not in the air,
on a rail or in a bail) and keeps a jog's worth of speed.

Yorimichi rides on the plugin's Ride backend (`Backend=Ride` in DefaultGame.ini): the native session rides the board
under Cairo's own physical body, which takes over in bails and plays the moves on and off the board. The plugin's
[RIDE.md](../../../platform/engine/Plugins/Activities/Skate/RIDE.md) says what runs in the native session and what in
Unreal, how much is ported and the known bugs. The Native backend is only the reference the QA compares against:
`skate.Backend Native` on the console switches to it from the next mount; the game does not offer it to players.

Getting on and off is one continuous move. Running, walking or standing,
the rider drops the board and steps on at speed. Stepping off, the rider runs out with the board in hand, and the
board dissolves after 6 s or as soon as the hands are needed. **D-pad Right** (keyboard **G**) brings a board to the
hand on foot, or puts the held one away. Jumping with the board in hand plays a jump and a landing with it. The skate
button in the air throws the board under the feet (a caveman: run, jump, then press it). In a ride's air it steps off
the board from the grab held and comes down on foot holding it; with no grab held the feet kick the board away and it
flies on by itself. A slow, upright bail runs out on foot, the board rolling on. Pressing the skate button during a
fall gets up on foot where the body lies, and the board stays lying; the skate button next to a board lying on its
wheels steps onto it (see the Skate plugin's `RIDE.md`, "Transitions").

Riding into the sea puts Cairo back on the board at the last dry spot.

## Controls

| Action | Controller | Keyboard and mouse |
| --- | --- | --- |
| Push | Cross / A (Square / X pushes mongo) | W |
| Brake | Circle / B | S |
| Steer, spin | Left stick | A / D |
| Powerslide | Left stick down-left / down-right | Hold C (A picks the left side) |
| Ollie | Right stick down, then up | Hold Space, release |
| Tricks | Right stick gestures | Hold the left mouse button and flick |
| Manual, nose manual | Right stick partly down / up | Hold the left mouse button, move part-way |
| Pump on the ground, grab in the air | L2 / R2 (LT / RT) | Q / E |
| Transfer over the coping | Left stick forward | Hold Shift |
| Look | (follows the board) | Mouse, without the left button |

The flicks: down-up ollie, down-up-left kickflip, down-up-right heelflip, down-left or down-right shove-its, a sweep
around for 360s, and starting from up for nollies. With the mouse, pull back then forward for an ollie, forward-left
for a kickflip, forward-right for a heelflip, and back then sideways for a shove-it. The mouse flick scales with the
game's mouse sensitivity. Goofy stance mirrors the gestures.

A grab never sends Cairo over the coping; only the transfer input does.

### Trick line and HUD

While riding, the controls line at the bottom lists the riding controls and shows the board's status (rolling,
pushing, manual, grinding, airborne, bail...) and speed in km/h. The trick line shows the current trick in large
text, centred at 84% of the screen height, and fades out about 1.5 s after the trick, grind or manual ends. Trick
names are the session's trick IDs without their prefixes, in title case: `ID_TRICK_GRIND_FS_50_50` reads "FS 50-50".
The score sits at the top right once it is above zero. The film HUD (`UYorimichiLive::FilmHud`) keeps only the trick
line.

### Pumping

Pull a trigger to crouch and let it go to stand up: L2 / R2 any part of the way (the deeper of the two counts), or
Q / E fully. Standing up while the board rides through a curve gains speed: crouch across the flat or high on the
descent and let go through the curve at the bottom; crouch again for the next wall. Timing matters: holding a trigger
is not a boost, and holding it through the curve gains less than coasting, which pumps a little by itself (the
transitions crouch Cairo). Any pull grabs in the air, so release the triggers before leaving the lip unless you want
a grab, and keep off the right stick, which pops. A grab held into the landing rides away; a Christ air or a one-foot
air held into it, or let go too late, is a bail.

### Camera

The follow camera comes 20 cm lower and 22% closer while riding, and its field of view widens by up to 9° between
18 and 45 km/h. Without mouse look it turns to follow the board and eases into the skating camera over about 0.6 s.
Looking with the mouse takes the view back for two seconds. The right stick never looks while riding: it is the
trick stick.

## Tuning

`unreal/Config/DefaultGame.ini`, section `[/Script/AtelierSkate.SkateSettings]` (the plugin README lists every key):

| Key | Value | Effect |
| --- | --- | --- |
| `PopHeightScale` | 1.15 | Higher ollies than stock |
| `AirSpinScale` | 1.6 | Faster air spins |
| `PushSpeedScale` | 1.15 | Higher push speed target |
| `PushPowerScale` | 1.45 | Stronger pushes |
| `VertAssist` | 1 | Straight airs on quarters short of vertical (down to about 50°) come back into the ramp |
| `DeckMesh`, `TruckMesh`, `WheelMesh` | `/Game/SkatePark/Board/SM_Skate{Deck,Truck,Wheel}` | The pier's board |
| `SoundFolder` | `/Game/Audio/Skate` | Board loops and one-shots |
| `FallSounds` | `/Game/Audio/Combat/body_fall_01`, `_02` | Body falls for bails |

`Difficulty` and `TruckTightness` are not set, so the plugin defaults apply: `normal` and 0.5.
`tools/check_skate_runtime.py` assumes `AirSpinScale` 1.6; change both together.

## Skate feel menu

Settings (Esc, or Menu / Options / Plus on a pad) → **Skate feel** opens a page with every value that changes how the board rides.
It starts with the **skating mode**:

- **Easy**, **Normal** and **Hardcore** are the game's own difficulties, as made. The custom values are greyed out and
  ignored, but kept.
- **Custom** tunes every value on a base difficulty. Switching to Custom from a preset with nothing tuned yet starts on
  that preset's difficulty, so Custom begins exactly where you were.

The custom values are grouped as Custom base (base difficulty, trucks), Flick-It, Air, Rails, Pushing and rolling,
Turning, Balance and Bails. **Controls and camera** (stick dead zone and full tilt, mouse flick strength, skate camera
distance and field of view) apply in every mode. Hover a row for what it does. Changes apply at once, even mid-ride,
and are saved in `settings.txt` as `skate_*` keys (`skate_mode` 0 Easy, 1 Normal, 2 Hardcore, 3 Custom). The phone's
settings show the same values under "Skate mode", "Skate feel · Custom" and "Skate controls & camera". **Reset custom
values to stock** and **Reset controls and camera** return those values to their defaults.

Custom values multiply the base difficulty's own, so pick the base first. Each starts at the game's own value: 1.00 for
most, and this game's pop 1.15, spin 1.6, push speed 1.15, push strength 1.45 and vert assist 1 (`DefaultGame.ini`). The plugin README's
"Feel" table says what each one scales. Some useful starting points:

| To get | Try |
| --- | --- |
| Flick tricks that land more easily | Flick tolerance 1.3, Flick time window 1.5, Flick speed for full pop 0.8 |
| Floatier airs | Gravity 0.8 (heights stay; air time is about 12% longer) |
| Grinds that catch from farther | Rail magnetism 1.5 to 2 |
| Endless lines | Rolling resistance 0.5, Grind friction 0.5, Pumping 1.5 |
| Fewer bails | Landing forgiveness 1.5, Impact toughness 1.5 |

## Board contract

`world/regions/skatepark/board.py` builds the board as three meshes, in Blender metres; the importer turns Blender
(x, y, z) into Unreal (x, -y, z) centimetres:

| Mesh | Origin | Shape |
| --- | --- | --- |
| `SM_SkateDeck` | Centre of the deck top; nose +X, up +Z | 80 × 20.5 cm, 22° kicks |
| `SM_SkateTruck` | Kingpin pivot on the deck underside; modelled as the front truck | Trucks sit at x = ±18 cm, 1.2 cm under the deck top; the back truck is turned 180° about Z |
| `SM_SkateWheel` | Wheel centre; axle along Y | 2.65 cm radius, 3.2 cm wide, at y = ±9.3 cm, 6.35 cm under the deck top |

The plugin places the deck top 9.05 cm above the ground and fits the trucks and wheels to the solved axle and wheel
bones (see the [plugin's board contract](../../../platform/engine/Plugins/Activities/Skate/README.md#board-contract)).
`unreal.skatepark` imports the three parts into `/Game/SkatePark/Board` without collision.

## Skate pier

Sunset Pier is a 170 × 132 m textured waterfront skate plaza below the road: long rail and manual promenades,
street terraces with stairs and hubbas, a banked market plaza, curved ledges and rails, a central wave, a sunset hip
line, a horseshoe mini-ramp, deep bowl and two return quarters. Concrete, glazed tile, stone, steel and cedar use
Sunburst material detail with distinct roughness and normal maps. The
[park guide](../world/regions/skatepark/README.md) gives its layout and build. `ASkatePark` loads its meshes and
spawn from `Content/Data/skatepark/park.json`, registers its rails, ledges, coping and curbs with the plugin, and is
tagged `SkatePark` for the skating collision snapshot. Drifting leaves are
hidden and not simulated on the pier, and a post-process volume over it turns off Lumen global illumination, whose
cache leaves patches on the large thin decks.

## Sounds

`audio.skate` (`assets/audio/skate/make.py`) builds the board sounds into `build/yorimichi/audio/skate/`, 48 kHz mono:

- loops `roll`, `grind`, `slide`, `skid` and `scrape`, synthesised as shaped noise so they loop without a seam;
- three variants each of `pop`, `land`, `catch`, `push`, `flick` and `clatter`, built from two wooden stick hits in the
  Sonniss combat masters (`atelier fetch yorimichi`) with synthetic thumps and clicks.

`unreal.sounds` imports them into `/Game/Audio/Skate` (`Scripts/import_skate_audio.py`), with the loops set to loop.
In the game the roll loop follows speed on the ground, grind or slide plays on a rail, skid in a powerslide and
scrape while braking; `pop` plays on take-off, `land` on landing and `clatter` on a bail.

## QA

With the game running (`atelier play yorimichi`):

| Scenario | What it checks | Report in `build/yorimichi/` |
| --- | --- | --- |
| `skate`, `skate_runtime` | 19 checks: push, flip and landing; steering; manual; rail; vert; deliberate bail and recovery; skin clearance during the bail (at least 0.45 cm); retargeted bone lengths, head direction and camera; keyboard pushing; stow and remount; goofy push and ollie; flat 360s both ways; keyboard powerslides both ways; running mount; Triangle mount and stow; coasting pose stability | `skateqa/runtime.json` |
| `skate_transitions` | With `skate.Backend Ride`, getting on and off: mounts from a stand, a walk, a run, a sprint and the carry; dismounts to a stand, a run and a fast run; the carry put away; the board button; a fall got up from on foot and back onto the board; a lying board dissolving; jumps with the board in hand; cavemans; an air dismount from a grab and a kick-out; a slow bail run out; a step onto a lying board; Link; the capsule (a BotW rider's fitted one keeps its size through three board toggles and a jump, a crouched Cairo stands up for the board). Every frame: the character, its hips, its velocity and the camera move no more than the speed explains; frame p99 under 17 ms | `skateqa/transitions.json`, each check's frames in `skateqa/transitions-rows/` |
| `ride_e2e` | On the default game (Ride is the default backend): a playtest dry run on the pad from the island's start to Sunset Pier, every input a pad key or stick: the first mounts (stand, run, sprint) and dismounts, the road (carve, brake, a push from a stop, an ollie, a kickflip), Flick-It tricks, a manual, a grab, a grind, pad and C powerslides, a quarter air, the hold-time dissolve and the recall, the sword, an interaction and the sailboat taking the board, a slam at speed, air and kick-out dismounts, a caveman, a bail off a grind, Link, and the Native backend and back. Every frame: frame time, camera and hip jumps, the board's places and pops, the sounds; flick directions follow the saved stance; `--post` after quitting adds the memory peak and the whole log | `skateqa/ride_e2e.json`, `.md`, frames and screenshots in `skateqa/ride_e2e/` |
| `skate_ride` | The ride (`skate.Backend Ride`) on the pier park and Mega Park: the first frame, pushing, steering, braking, the ollie, every Flick-It trick (also flicked on the player's pad, `--only pad`), grabs, spins, grinds, manuals, lip airs and vert (`--only vert`), pumping (`--only pump`), wheel contact, frame pacing, and the physical rider (how closely it holds the pose, bails that go limp at once and travel as far as the reference's, skin above the ground, joints within their ranges, its frame cost); `--only native` runs some rows on the Native backend beside it | `skateqa/ride.json`, `skateqa/ride-pose.json` |
| `ride_session.py` (through `atelier live py`, not `qa`) | Records a session from the player's pad, then replays it packet by packet on either backend at a fixed 60 Hz in lockstep; the replay reports the board's error against the recording (see the script) | `ride-record/<take>/`, a replay in `replay-<backend>/` |
| `skatepark` | Roll-ins on the bowl, mini, east and mellow returns, market, seven-stair and four-stair banks; the stair handrail; an air up and back in the bowl (apex above 3.5 m, landing back on the wall) | `skateqa/park.json` |
| `skate_performance` | Real-time frame pacing through six activities (push and flip, bowl air, mini air, quarter air, street to mini, bail): at least 58.5 fps, p95 under 20 ms, p99 under 33.34 ms, no frame over 50 ms, no native pose repeated three frames running | `skateqa/performance.json` |
| `pier_part`, `pier_part_check` | Self-stopping control-driven rehearsals and films; complete telemetry and bail checks | `skatefilm/<take>/` |
| `pier_part_mix` | Assembles approved takes, original procedural soundtrack and board audio | `skatefilm/<part>/` |
| `skate_showreel` | A filmed line of shots at the pier, at a fixed 60 fps step; run through the live bridge (see the script) | `skatefilm/<take>/` |
| `skate_mix_showreel` | Mixes a showreel take's sounds and encodes 1080p and 720p MP4s | `skatefilm/<take>/` |
| `megapark_ride_film` | A filmed Mega Park line on the Ride backend (20 shots: carves, flips, manuals, grinds, powerslide, the drop-in, quarter airs, three ragdoll bails with the get-up and a board recall, a final line; optional caveman and grab-dismount shots), per-shot parts with slow-motion replays, the rider about 40% of the frame's height; run through the live bridge (see the script) | `megapark/ride-film/<take>/` |
| `megapark_ride_film_mix` | Cuts the kept parts and their replays into one film and mixes it through `skate_mix_showreel` (`--audio` reads another build's sounds; `--trim shot:first-last` leaves out frames where a camera lost the rider; `--replays a,b` picks the slow-motion replays) | `megapark/ride-film/<take>/` |

`skate` runs `skate_runtime` and always gives the controls back. `skate_live_skate.py` is the in-game helper module
the others load (`live.park.place`, `live.park.launch`, `live.scenario`). The live module also has `live.skate()`,
`skate_input()`, `skate_release()`, `skate_state()`, `skate_place()`, `skate_park()`, `skate_script()` and the
gesture paths in `FLICKS`.

Offline, without Unreal, after building the native QA executable (see the plugin's
[runtime reference](../../../platform/engine/Plugins/Activities/Skate/RUNTIME.md#reference-build)):

```sh
python3 games/yorimichi/tools/verify_skate_native.py      # the tracked bundle against its manifest
python3 games/yorimichi/tools/check_skate_runtime.py      # flat ground, both stances -> build/yorimichi/skate-native/check
python3 games/yorimichi/tools/check_skatepark_runtime.py  # the pier's exported collision -> build/yorimichi/skatepark/physics
```

`check_skatepark_runtime.py` needs `world.skatepark` built. It rides the bowl, the mini-ramp, the return quarter, a
bowl roll-in, an ollie over the bowl coping and the seven-stair handrail, and requires a pumped 8.5 m/s bowl run to
peak at least 0.5 m higher and come back at least 0.4 m/s faster than coasting.
