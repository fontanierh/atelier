# Ride reference

[`reference.json`](reference.json) records how the native skating session behaves (the C++ runtime in the Skate
plugin's `Source/AtelierSkate/Private/Native`, entry `GameplaySession`). A replacement ride system is checked against it.
The file holds 321 scripted scenarios, each played through a complete session on simple collision worlds with the game's
skate tuning, plus per-frame dumps of 13 key clips and a summary of the measured numbers.

Native space is metres with x left, y up and z forward. A tick is 1/60 s and heading 0 rides toward +z. The rider is
regular unless a scenario uses the goofy tuning.

## Contents

| Key | Content |
| --- | --- |
| `conventions` | Units and axes, pad layout and stick conditioning, the `game` and `stock` tunings, column names, rotation conventions, wipeout reason codes, the Flick-It gesture tables |
| `mechanics` | One entry per scenario (see below) |
| `clips` | 13 clips sampled frame by frame and composed onto the rig pose (before the runtime's stance mirror): board pivot, board rotation, hips and feet, the clip's trajectory track |
| `summary` | The headline numbers gathered across scenarios: standing pose, push, coast, brake and powerslide, steering, ollie, air tricks, grabs, grinds, bails, ground tricks, landings, air gravity |

Each `mechanics` entry contains:

- **The setup:** `group`, `note`, `world`, `spawn`, `heading`, `velocity` and `tuning`.
- **The recipe:** `recipe.events` lists `[start_tick, end_tick, {field: value}]` on a neutral pad. The fields are
  `buttons`, `lt`, `rt`, `lx`, `ly`, `rx` and `ry`, with raw sticks of ±32767.
- **What happened:**
  - `states`, `motion_graph` and `action_graph` are `[name, start, end]` runs.
  - `tricks` lists the published trick names.
  - `grind` and `bail` are the grind families and the wipeout reasons.
  - `clips` holds the clip segments. Each row has the clip, layer, ticks, peak weight, rate, clip times, wraps and a
    weight curve.
- **`numbers`:** the measurements for that group. Examples are take-off, pop height, air time, gravity, deck and body
  rotation, board-spin ticks, feet-to-board distances, grind entry offset and speed loss, manual balance, and bail tick
  and speeds.

A launched rider reacts to the launch for ticks 2 to 50, so analysis starts at tick 50 (`analysed_from`) unless the
inputs start earlier.

The scenarios use these worlds:

- flat ground;
- a halfpipe with 3.4 m vert walls and coping;
- a quarter pipe;
- a 0.5 m rail along z at x = 0;
- a 0.45 m ledge;
- a 0.5 m kicker;
- a 2 m wall;
- 1 m, 3 m and 6 m drops.

The full per-tick traces (about 130 MB) are written to `build/yorimichi/skate-ride/oracle/traces/` and are not
tracked. Each trace has:

- the deck pose and velocities, with contacts and wheels;
- the player and graph states, the trick, score and manual balance;
- the active clips with their weights, times and rates;
- 13 key bones, in both the published pose and the animation pose;
- grinds, wipeouts, board possession and the camera.

## Measured numbers (game tuning)

| Mechanic | Value |
| --- | --- |
| Standing | Hips 0.89 m over the board root (0.975 m over the ground), board root 0.087 m |
| Push (A held) | 9.78 m/s top speed, 90 % in 1.65 s. Mongo (X): same top speed in 2.6 s. Stock tuning: 8.5 m/s |
| Coasting on flat | No measurable slowdown (under 0.01 m/s²) |
| Brake (B) | 3.14 m/s² |
| Powerslide (held) | 2.0 m/s² at 4 m/s, 4.6 m/s² at 8 m/s; the deck turns 250–276° |
| Steering, full stick | 68°/s at 2 m/s, 76–81°/s at 5 m/s, 98–109°/s at 9 m/s. Three-quarter stick: 45, 47 and 58°/s. Half stick: about 5–8°/s above 2 m/s. A quarter stick is in the dead zone |
| Kick turn (full stick for 1 s) | 156–174° standing, 110° at 3 m/s |
| Ollie | 1.31 m deck rise, 0.867 s air, 5.4 m/s take-off, at any speed. Loading 4 ticks gives 0.64 m, 40 ticks 1.37 m. Stock tuning: 1.04 m |
| Gravity in the air | About 15 m/s² mid-air (stock 17.7), not 9.81 |
| Kickflip | Roll −357°, caught about 0.42 s after the pop. Heelflip +358°. 360 flip: roll −367° with the shove-it at −336° |
| Body spin, flat (left stick held into the ollie) | Starts only if the stick is still held at take-off. Releasing 2 ticks after take-off gives 150°, 8 ticks 170°, 18 ticks 225–230°, 33 ticks 290° |
| Body spin, vert at 10 m/s (stick from 6 ticks before the lip) | Released 4–10 ticks after the lip: 160°. 18 ticks: 340–394°. 30 ticks: 500°. 40 ticks: 555–573° |
| Landing | Every spin rides away, even 45–70° off the line of travel: the wheels keep only the speed along the board, and the rider rolls on forward or fakie. In the air the board turns toward the nearer of forward and fakie (90° became 127° over a 1.5 m fall). With the board 44–112° off the body the landing clip is `L_SKETCH_*`; clean spins use `L_NICE_*`; otherwise `L_HCOM_*` / `L_LCOM_*` with LIMP / HIMP by impact. No landing-angle bail (reason 5) was seen |
| Transfer (pad bit 0x0800 in a vert air) | Carries the rider over the coping onto the deck (body pitched 85°) and locks the board into a lipslide on the coping |
| Manual | Engages 13 ticks after the input; deck pitch −11° (−16° deep, +8° nose); slows 4.6 → 3.6 m/s over 3 s |
| Grind entry | Grinds from 0.47 m right to 0.64 m left of the rail at take-off; approach angles up to 60° hold |
| Grind speed loss | 0.97 m/s² on a rail, 1.40 m/s² on a ledge, 2.48 m/s² with stock tuning |
| Bails | A wall at 8 m/s or more (deck in-plane acceleration). A landing faster than about 13.5 m/s vertically. Landing across a rail locks into a boardslide; at 3 m/s it ends in a slide wipeout. Body flips on flat ground and on vert. Christ air and superman on a flat-ground ollie. Clicking both sticks while holding both triggers |

## How the native session does it

- **Flips are animation-driven.** The clips rotate the board and the physical deck follows. Over a kickflip the
  animation pose's board turns −357° about its long axis and the published deck turns −357.5°.
- **Kickflip order:**
  1. `R_ANTIC_OLLIE_N_0_INTO` (the load);
  2. `KICKFLIP_IN_HIGH_G`, then `KICKFLIP_IN_HIGH_A` (rate 1.03), which carries the first half turn;
  3. `T_KICKFLIP_HI_4FLIPS_0_OUT1` (rate 0.95), which finishes the turn;
  4. the air idle `IA_IDLE_N_N_0_CYC` with crouch and extend blends, fading in over about 10 ticks;
  5. `L_HCOM_*IMP_3`, the landing chosen by impact;
  6. `R_IDLE_HCOM_000`.

  Neighbouring clips cross-fade over 2 to 12 ticks. The motion graph follows the same order: AnticTail, TakeOff,
  LeftGround, Out1, InAirStatic, Land.
- **The rider is posed relative to the board pivot.** In every clip the board root stays at the clip origin. The clip
  rotates the board about that pivot and places the hips and feet around it. Standing, the ankles are 0.11–0.13 m
  above the board root: the front one 0.07 m from it along the board and the back one 0.35 m from it, over the tail
  (the trucks are 0.26 m either side). The clips are deltas added onto `RIG_TPOSE`, and for a regular rider
  `BOARD_BACKWARDS` turns the board round. The runtime then mirrors the pose for the stance, so the live regular
  rider is the dumped pose reflected front to back with left and right swapped.
- **The root in the air:** the published root stays on the physical deck to within 0.03 m. The deck flies a ballistic
  arc under stronger gravity. The board stays under the feet because the clip's board rotation returns to level
  before the landing clip, not because anything moves the root toward the board.
- **Grind entry:** in the air, the deck is pulled sideways over the rail. On the first grinding tick the deck sits
  within 0.02 m of the rail line, so contact itself does not snap it. The grind family follows the deck's angle to the
  rail and the stick:
  - near 0° with no stick: 50-50;
  - right stick down: 5-0; right stick up: nosegrind;
  - 25–35° (or the right stick held left): crooked or willy;
  - board across the rail: boardslide or lipslide;
  - left stick right: bluntslide.
- **Bail triggers:** each wipeout publishes reason codes, which `conventions.bail_reasons` lists. The common ones are:
  - 2: deck acceleration in the board plane (walls, bad catches);
  - 4: upside down while flipping;
  - 6: landing impact speed;
  - 10: slide wipeout.

## Recording it again

The recorder is in the Skate plugin's tests: `Tests/build_ride_oracle.py`, `Tests/Native/ride_oracle_recorder.cpp`,
`Tests/ride_oracle.py`, and the scenarios and analysis beside them. It needs only the native data bundle; it does not
use Unreal. Build it, then record, under the render lock and memory guard:

```sh
uv run python -m atelier.safety.guarded --report build/yorimichi/skate-ride/oracle/guard-compile --kind compile \
  --purpose "skate ride oracle: build the recorder" -- \
  python3 platform/engine/Plugins/Activities/Skate/Tests/build_ride_oracle.py --out build/yorimichi/skate-ride/oracle
uv run python -m atelier.safety.guarded --report build/yorimichi/skate-ride/oracle/guard-run --kind job \
  --purpose "skate ride oracle: record" -- \
  python3 platform/engine/Plugins/Activities/Skate/Tests/ride_oracle.py \
  --recorder build/yorimichi/skate-ride/oracle/ride-oracle-recorder \
  --package games/yorimichi/unreal/Content/Data/SkateNative \
  --traces build/yorimichi/skate-ride/oracle/traces \
  --reference games/yorimichi/assets/skate/ride/reference.json --jobs 4
```

- The first build compiles the whole runtime, which takes a few minutes. After that only changed files are rebuilt.
- Recording all scenarios takes about 25 s.
- `--only 'flip/*,grind/*'` records only the matching scenarios.
- `--analyse-only` rebuilds `reference.json` from the existing traces without recording.

The scenario names, worlds and input recipes are in `ride_oracle_scenarios.py`, and the measurements in
`ride_oracle_analysis.py`.
