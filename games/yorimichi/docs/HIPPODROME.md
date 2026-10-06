# Hidamari Hippodrome

A racecourse on the terraced slope north of Hidamari, reached by a lane that climbs from the end of the city's
eastern street (x = 560). Hudson, the race master, stands by the grandstand. Talk to him (E, or D-pad Down) to race
five BOTW riders round the oval. The riding is a rhythm game: the cup's song plays and its notes slide along a
four-row rail under the horse, and every note met on the beat lifts the horse's stride.

The structures follow the Sunburst concept sheet (`assets/hippodrome/concepts/`): a timber grandstand with a red
tin roof, a white rail, a green starting gate, a judges' tower, a red-and-white finish post, a tote board and a
stable. They were modelled from that sheet with Tripo (`tools/hippodrome_props.py`).

## Playing

| | Keyboard | Pad (Xbox labels) |
| --- | --- | --- |
| Notes, lanes 1 to 4 (green, red, blue, yellow) | D F J K | A B X Y |
| Steer | Left / Right | Left stick or D-pad |
| Spur | Space | RB |
| Retire | Hold Esc 1 s | Hold Menu 1 s |

The HUD keeps the race clear. Nothing sits over the track ahead or the field:

- **Sky:** the cup, lap, clock and distance, the riders just ahead of and behind you with the gaps, and a small map of the oval.
- **Under the horse:** the note rail. Four thin rows run across the bottom of the screen, the notes slide left into the hit rings, and the stride bar and the spurs sit beneath them.
- **Results:** the full field waits for the results card, which stands alone.

The rail shows face-button names for the connected pad (PlayStation shapes, Nintendo letters), and the controls line
fades once the race is under way. The chase camera stays close behind your horse. When a rider runs close behind in
the camera's lane, the camera cranes up and looks down over it. Every horse stays in view.

- **Judgement:** Perfect within ±50 ms of the beat, Great ±100 ms, Good ±150 ms. Anything later is a miss. A long
  note must be held to its end ("Held!"); letting go early drops it. A press with no note costs a little stride but
  never the combo.
- **Stride:** a running average of the last dozen or so notes (Perfect 1, Great .8, Good .5, Miss 0). The horse's
  speed is the cup's base speed plus its range times the stride, so a clean rhythm is worth about 3.5 m/s over a
  ragged one.
- **Spurs:** every 16 notes in a row earns a horseshoe (up to four). A spur adds 3 m/s for 2.6 s. Save them for the
  home straight, or spend one before a fourth would be wasted.
- **Racing line:** the turns are all to the left, and the rail is the short way round: one metre outwards on a turn
  costs 2% of the distance. A horse right ahead in your path holds you to its pace ("Boxed in"). Steer out round
  it.
- **The field:** the other riders meet the same notes at their own skill (Urbosa is the strongest), a little
  sharper when they trail and looser when they lead, and spur late. They hold the rail, swing out to pass and
  never cut across a horse alongside. Horses keep 2 m between them side by side (about a metre between flanks).

| Cup | Distance | Song | Field skill | Speeds (m/s) |
| --- | --- | --- | --- | --- |
| Maiden Plate | 1.5 laps (831 m) | 132 BPM, single notes | .45 to .70 | 8.2 + 3.4 |
| Hidamari Stakes | 1.5 laps | 148 BPM, first chords | .60 to .82 | 9.0 + 3.6 |
| Hidamari Cup | 2.5 laps (1385 m) | 164 BPM | .72 to .92 | 10.2 + 3.8 |

The horses are Biscuit (pinto), Kuro (black), Momo (roan), Fuji (lilac), Kinako (dun) and Shiro (white); they are
the same speed, so the choice is looks. Epona joins once you have won any cup. Best places and times per cup are
kept in `Saved/hippodrome.json`.

A race runs in phases: the parade (fanfare over the gate), the song's four-beat count-in, the off (the gate opens on
the song's downbeat), the finish, then the results. If the race outlasts the song, the music loops its last eight
bars and the chart repeats their notes.

`hippodrome.LatencyMs` (console variable) shifts presses back to meet the music on a system with audio output lag.

## Layout

`world/regions/hippodrome/layout.py` holds the plan. All values are in Blender metres; the docstring there is
authoritative.

- **Oval:** centre (600, 525). The straights are 120 m and the turns are half circles of 50 m centre-line radius,
  so a lap is 554.2 m on a 14 m track. The race runs counter-clockwise: east along the home straight in front of
  the grandstand (south), west along the back straight.
- **Platform:** the course is flat, on one platform (48.26 m) just above the highest ground under it, with a skirt
  down to the terraces. JapanWorld clears trees and grass inside the `clearance` polygons.
- **Starting gate:** mid back straight, at s = 277.1 m (half a lap from the finish post), so every cup is a whole
  number of laps plus a half. It is taken off the track five seconds after the off, when the field is away, and stands
  ready again after the race.
- **Hudson:** stands at (-38, -64) from the centre. Races and the map stop put the player at (-36.5, -66.5), facing him.

`world.hippodrome` writes `build/yorimichi/hippodrome/region/` (`hippodrome.json` and the GLBs), and
`unreal.hippodrome` imports them to `/Game/Hippodrome` and `Content/Data/hippodrome/hippodrome.json`.
`AHippodrome` places the meshes and spawns Hudson and the race manager. The world map gains a `hippodrome` stop
at the return spot (`UJapanMap`, read from the same file).

## Horses, riders and animation

The horses, the riders and Hudson come from the local BOTW asset library, like the BOTW roster. See
[`assets/characters/horses/README.md`](../assets/characters/horses/README.md). `characters.horses` bakes them to
GLBs and `unreal.horses` imports them. The game finds them through `Content/Data/horses/roster.json`.

`AHippodromeFigure` plays the clips directly on skeletal meshes (no AnimBP):

- **Riders:** each rider sits on the horse's `Saddle_Root` bone and plays its own half of the horse's clip.
  `Horse_Move_Gear_<n>` matches the horse's `Move_Gear_<n>` frame for frame.
- **Gaits:** chosen from the ground speed (walk below 3 m/s, trot below 5.4, canter below 7.4, run below 9.6, then
  sprint). Each clip plays at the rate that matches its measured stride to that speed, so the hooves don't slide.
  A gait change keeps the stride's phase.
- **Turns:** at a run or a sprint the horses play the `Curve_L` clips and lean in.
- **Spur:** the rider's spur kick is a one-off that rejoins the stride when it ends.
- **The winner:** rears once it has pulled up.
- **The player:** races as Cairo (`RiderCairo`): `characters.cairo_rider` retargets the riders' clips onto him with
  his BOTW move set's retarget (`assets/characters/horses/cairo_rider.py`). Playing as Link (`-rider=Link`), you race
  as Link. A rider mesh that faces another axis than the horse's is turned to face ahead on the saddle.

## Riding about the world

`UHorseRideComponent` puts the player on horseback anywhere on firm ground:

- **H** brings round the horse you last raced (`Saved/hippodrome.json`, else Momo) and mounts it. At a walk, **H**
  steps off on the horse's near side and leaves it standing; **H** within 15 m mounts it again, and further away a
  fresh horse comes.
- **W** trots, **Shift** gallops, **Alt** walks and **S** reins in. Left alone, the horse eases to a stop.
  **A / D** turn: on the spot at a standstill, tightly at a walk and widely at a gallop.
- **Space** spurs for a 1.8 s burst at full speed. There are three spurs, and one comes back every 4 s.
- **Q** rears at a standstill.
- The horse is an `AHippodromeFigure` (horse and rider) standing on the hidden character's capsule. The capsule keeps
  its walking physics: floors, slopes, steps and walls. The figure tilts with the ground between fore and hind legs.
  It stops short of walls, and it plays the race's gaits, curve clips and hooves.
- The camera rises and stands back, and swings in behind the horse once it moves.
- Deep water puts you off; the horse waits at the bank.
- No gamepad button mounts yet: on a controller, ride with the stick, the sprint button and the jump button (spur).

## Sound

`audio.hippodrome` (`assets/audio/hippodrome/make.py`) synthesises the three songs, their charts (`charts.json`:
notes in song seconds, lanes 0 to 3, holds) and the cues: fanfare, gate, crowd loop and cheers, hooves, hit ticks,
miss, spur, finish bell, win and lose. `unreal.hippodrome_audio` imports them to `/Game/Audio/Hippodrome`.
`tests/test_hippodrome_charts.py` checks the charts against the songs' beats.

## Live verbs and film

```sh
uv run atelier live py "unreal.YorimichiLive.race_visit()"            # stand by Hudson
uv run atelier live py "unreal.YorimichiLive.race_start(1, 'HorseRoan', 0.9)"   # cup, horse, autoplay accuracy (0 = you play)
uv run atelier live py "unreal.YorimichiLive.race_state()"            # phase, clock, every runner as JSON
uv run atelier live py "unreal.YorimichiLive.race_end()"
uv run atelier live py "unreal.YorimichiLive.race_menu()"             # toggle Hudson's menu
uv run atelier live py "unreal.YorimichiLive.press('horse')"          # mount or step off (free riding)
uv run atelier live py "unreal.YorimichiLive.horse_state()"           # mounted, horse, gait, speed, spurs, figure
```

The race film runs a guarded 1080p60 game on a fixed clock with autoplay, writes the frames, camera, sounds and the
music's start, loop jumps and fade, and quits at the results:

```sh
games/yorimichi/tools/film_race.sh stakes 1 HorseRoan 0.93     # take, cup, horse, autoplay accuracy
uv run python games/yorimichi/tools/mix_race_film.py build/yorimichi/racefilm/stakes
```

`mix_race_film.py` lays the stereo song down as the game played it and places every other cue by its distance and
bearing from the camera. It writes `race.mp4` and `race-720p.mp4`.

The encode takes no render lock, but it is CPU-heavy. It runs at nice 10, with two threads each for decoding,
filtering and encoding. It prints its progress every ten seconds and ends an encode that stalls for five minutes.
Even so, list it under Waiting on the render board and run it only when no graded game is loading or running.

## Known limits

- **Starting gate:** the stall doors are modelled half open, and the number plates read 1, 2, 3, blank, 4, blank,
  7, 8.
- **Stable and judges' tower:** the stable's walls came out as plaster rather than timber, and the judges' tower
  has panels between its legs.
- **Map sheet:** the painted map does not draw the oval yet; the travel stop is added at runtime.
- **Audio seam:** the music loop's jump is not sample-exact.
