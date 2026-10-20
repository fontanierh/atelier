# Horse racing

Races run in the world on the rules of the `HorseRacing` game plugin
(`games/yorimichi/unreal/Plugins/HorseRacing`, module `AtelierHorseRacing`): a continuous clock with one race day
every two real hours and up to six races a day, computer stables, jockeys and Grand Prix days. Yorimichi shows the
races at two racecourses, the same for every player. Four TVs in Belmonte show the races live. There are no bets, stables or menus yet: later work adds betting and player
stables.

## The service

`ARacingService` (`RacingService.h/.cpp`) is one replicated actor, spawned by the host (offline: the game itself) once
the world is in place; clients receive it. It follows `ABelmonteTrainService`: one network-state struct with a serial,
and positions computed on every machine from the replicated clock, never replicated per frame.

- **The world.** The host owns the rules' `FHRWorldState`. It loads `Saved/racing/world.json` (or `-racingsave=PATH`)
  or creates a world from `-racingseed=` (default `yorimichi-racing-1`) and anchors its clock to Unix time, so the
  racing world keeps going between sessions and a host that was away catches up (at most one race day per frame, so
  hours of catch-up never hitch, and at most `HRRules::MaxCatchUpDays`, one real week: a host away longer resumes as if
  the world had paused then). It saves after a race or a day changes the world (at most every 15 s) and when the game
  ends, atomically: a flushed temporary file renamed over the old one, so a crash leaves the old world or the new one.
- **Admission and failures.** A save is admitted by `HRSave::FromJson` before it replaces anything (schema and rules
  versions, required fields, unique ids, references, ranges and collection sizes). A file that is not an admissible
  world is kept aside (`world.json.unreadable-<time>`) and a new world is created; if it cannot be moved aside, or the
  file cannot be read at all, it is left exactly as it is, no world opens and racing stays off (an error in the log,
  `GetPersistenceError()`). A failed save keeps the accepted world in memory and dirty, logs the error, and the next save
  tries again.
- **Players.** V1 registers the host's own player only (`HRRules::AddPlayer`), with an id saved beside the world
  (`Saved/racing/player-id.txt`); its name is their character's. **Remote guests get no player record, wallet or stable**:
  there is no persistent guest identity yet (an online id may be missing and a session id changes every session), so
  nothing persistent may be owned by one. Guests watch from the replicated snapshot, which carries no player, coins,
  tickets or ownership; every rules call that changes the world (and `racing.Next`, `racing.TimeScale`, `racing.Save`)
  runs on the host only. Betting, stables and wallets for guests wait for a persistent guest identity.
- **The snapshot.** `FRacingNetState` carries the clock anchor (the rules' world second at a server time, and the dev
  time scale), the race day and its event, the race in focus, the last podium and the six best stables. The race in
  focus is the one running or just run (for the rules' 180 s after its start), else the next one today. Each runner
  has its horse, stable, jockey, silks colour, win odds, look (breed, coat, scale) and, once run, its place and the
  four stage splits. A five-runner snapshot weighs about 0.8 kB on the wire (`FRacingNetState::PayloadBytes`; `Yorimichi.Racing.Snapshot` holds it under 2 kB). The host
  rebuilds it every second and publishes a new serial only when its content changes or the clock needs re-anchoring.

## Motion

The rules decide a race when it starts (`HRRules::ResolveRace`): each horse's cumulative time at the end of its four
stages (15, 35, 25 and 25 % of the distance). `RacingMotion::Distance` (`RacingMotion.h`) turns those splits into
distance over time with a monotone cubic through the stage ends, from a standing start, so every machine draws the same
race and each horse crosses the line at its official time in its official place. Before the off the field walks the last
120 m to the start from 180 s to 125 s before it, then stands lined up there (the TVs' build-up, from 120 s, never
shows it walking); after the post each horse eases down to a trot until the race leaves the focus. Each runner keeps its draw lane (the entries' order) across the track. A two-run Grand Prix race shows the run
that counts.

## Venues

| Venue | Course | Lanes |
| --- | --- | --- |
| Hidamari hippodrome | `FHippodromeCourse` (554.2 m oval, counter-clockwise, post at x = 600) | from 5 m inside to 5 m outside the centre line |
| Belmonte racecourse | turf (1799.8 m) or sand (1703.7 m) polyline, `FRacingPolylineCourse` | lane 1 on the line, then 1.9 m steps inwards, to 10 m in |

**Rule:** Grand Prix days (days 3, 6, 9 and 12 of a season) are at Belmonte. The eight ordinary days alternate,
counting from the season's first: Hidamari, Belmonte, Hidamari... A race on sand (the rules' surface 2) at Belmonte
uses its sand track; every other Belmonte race uses the turf.

The Belmonte tracks come from Haras Valley's venue data (`tracks`: closed centrelines every 2 m in Belmonte's plan
metres). `tools/belmonte_courses.py SOURCE` writes the committed, simplified copy `world/racing/belmonte_courses.json`
(lengths are kept exactly; the finish post is `finish_s` = 240 m from the first point), which `data.stage` stages as
`Content/Data/racing/belmonte_courses.json`. At runtime the points are placed round the Belmonte region's origin (the
`ABelmonteRegion` actor's location, `layout.ORIGIN`), as the region places its zones: a point (x, y, z) lands at
`ORIGIN + (x, y, z)` metres. The finish line is at plan (-155, 607.3), the post 3.6 m outside it.

## Horses

While a player is within about 600 m of the course of the race in focus (from 180 s before its start to 180 s after),
the service shows its field: up to six runners (the rules' `MaxRunners`). Each is three skeletal components moved by the
service: the roster's breed mesh (`Content/Data/horses/roster.json`) with its coat variant, the first tack set's saddle
in the stable's colour (the saddle cloth), and a jockey, the default character on his own horse clips (authored on the
reference breed and moved by the breed's seat offset; the hands and feet are not re-solved as `FHorseRiderNode` does
for the player). The gait follows the speed through the roster's Idle, Walk, Trot, Canter, Gallop and Sprint clips,
horse and jockey on one phase. The rules' breed gene picks the breed (Standard: Thoroughbred, Giant: Friesian, Bone:
Andalusian, Spirit: Arabian), the visual genome's coat colour the closest coat variant, and the size its individual
scale within 8 %.

**No stand-ins.** Every racing breed's mesh, six gait clips, first saddle and seat contacts, every coat texture and the
default character's six horseback clips are required. If one is missing the service logs an error and shows no field: a
runner is never riderless, in another breed or coat, or missing from its race (an entrant the world lacks is an error
too). The build checks the same list before the cook: `data.racing_assets` (`tools/racing_assets.py`) fails when an asset
is missing from the staged roster or Content, or lies outside a folder `DefaultGame.ini` always cooks (`/Game/Horses`
and the default rig's `/Game/<rig>Horse`, since the service loads them by path).

**Ground.** A shown runner traces the ground every 0.4 s through its course point. Only walkable ground counts
(`RacingGround::Pick`): a hit facing up (normal z at least 0.7), within 2.5 m above and 4 m below the point's authored
height, the nearest to it, so walls, rails and roofs above the track are ignored. Without one the runner is back on the
authored height, never on the last traced one; the traced offset follows the authored slope between traces.

Performance: no runner exists away from the venue, out of the race window or on a dedicated server; the service then
ticks four times a second. A shown runner evaluates its pose only when rendered.

## TVs

`ARacingBroadcast` (`RacingBroadcast.h/.cpp`) hangs four screens in Belmonte: two in the osteria's taproom on the piazza
(`osteria_front` on the door wall, `osteria_back` on the back wall) and two in the Salon des Paris (`salon_paris`,
`salon_bar`). Their places come from Haras Valley's `Data/tv_spots.json`: a pivot on the wall plane at the screen's
centre, facing its yaw, in Belmonte-local cm. Haras Valley's frame is the region's, so a screen hangs at the region
origin plus its pivot (the osteria's watch point is its map stop at plan (-30.4, 1.6) m). The screens are 1.4 times
Haras Valley's 70-inch one (2.17 m of picture); the Salon's bar screen is 1.3 times and 15 cm higher, to stay over the
mirror's frame. Each is a procedural frame and picture with no collision or shadow; the picture's material is
`/Game/Racing/M_RacingTv` (`unreal.belmonte`, `Scripts/racing_tv_material.py`): unlit, it decodes the picture's
display-encoded colours.

It is presentation only, on every machine that draws (never a dedicated server), from the service's replicated snapshot:
nothing of its own is replicated. The broadcast camera is a pure function of the race in focus, the shared clock and
the players' replicated pawns (`RacingTv::Direct`), so every player sees the same shot at the same moment. Until 15 s
before the off it cuts every 10 s between the whole course from above, the stand, the crowd (the one of three cameras
along the stand that frames the most players, `RacingTv::CrowdCamera`) and the field lined up at the start, head-on.
Then: side-on at the start for the off; trackside cameras every 120 m on the infield, the field galloping towards one
and past it; a view from above in the race's second and third stages; head-on past the post on the home straight
(from 400 m out); side-on at the line from 70 m out until the last runner is home; a wide shot of the field pulling up.
The stands are per venue (`RacingTv::VenueShots`). The lower third shows the event, the countdown, the distance left or
the arrival, and the first three behind their saddle cloths, in large type.

Between races (and away from a race's window, 120 s before its start to 180 s after) the screens show an idle card in
large type: the venue and distance, the event, the countdown, the three favourites with their odds and the last winner,
or the next meeting once the day's races are run.

**Performance.** One scene capture films for all four screens into a 480x270 film, 10 times a second (`racing.TvHz`),
and only while the local player is within 25 m of a screen, in front of it, during a race's window, and while a screen
near the player was drawn in the last 0.3 s (looking away pauses it). The film and the graphics are drawn into the
screens' 640x360 picture with a canvas, so the text stays sharp. It renders without Lumen (a post-process override),
dynamic shadows, reflections, ambient occlusion, volumetric or height fog, clouds, grass, translucency, motion blur,
bloom, particles, decals or temporal AA, with coarser LODs and nothing beyond 400 m except in the views from above,
with a little more contrast and colour. Otherwise nothing is captured: the card is redrawn once a second within 40 m of
a screen, and nothing at all further away. While the capture runs, the service shows the field wherever the race is
(`ARacingService::SetBroadcastAudience`): a Hidamari race is filmed from Belmonte, and the runners' poses are evaluated
though the main view does not draw them. The field is the same six runners the service shows near a venue: no proxies
to keep in step. Each camera's sightline is checked with a trace from its subject against the static world; a blocked
camera moves in front of the obstacle.

## HUD

Near a racecourse the HUD shows one line at the top: the next race and its countdown, "Course en cours" while the
field runs, the podium ("Arrivée : 1. … 2. … 3. …") for five minutes after a finish, or where today's races are run.

## Dev and live

```sh
racing.Next [lead s]        # jump to lead seconds (default 100) before the next start (host)
racing.TimeScale 10         # the racing clock ten times faster (host)
racing.Go hidamari|belmonte # stand by the post of a racecourse
racing.Save                 # write the world now
racing.Tv osteria_front     # stand at a TV's watch point (osteria_front, osteria_back, salon_paris, salon_bar)
racing.TvCapture 0          # keep the TVs' capture off (the idle card only), to measure it
```

Launch flags: `-racingnext`, `-racingseed=`, `-racingsave=`. The live bridge has `unreal.RacingLive.racing_state()`
(JSON: clock, race, each runner's distance, speed and position), `racing_next(lead)`, `racing_go(venue)` and
`racing_view_point(along, outwards)` (a point by the course and the yaw facing it), `racing_tv_state()` (JSON: the screens,
whether the capture is live, the shot, the nearest screen, frame and GPU times) and `racing_tv_go(spot)`.

## Tests

`Yorimichi.Racing.*`: `BelmonteCourse` (lap lengths, continuity of every lane, the finish point and the post),
`HippodromeCourse`, `Motion` (the same distances from the host's world and from a serialised snapshot, monotone, through
each split on time, places in finishing order, lined up before the off), `Snapshot` (size, the venue rule, the last
result after a race), `Save` (create, save and reload through the service on a temporary path), `SaveSafety` (an
invalid save kept aside; one that cannot be moved left untouched with no world opened; a failed save keeping the world
in memory, then succeeding), `Ground` (walls, rails, roofs and steep slopes ignored, the authored height after a miss), `TvPlacement` (the
screens round the region origin, the osteria's watch point on its map stop, each watch point in front of its screen) and
`TvDirector` (the shot list, the crowd camera, the same camera for the same clock, the leader in frame). `uv run pytest
games/yorimichi/tests/test_racing_courses.py -q` checks the committed course data, the simplification and the staging;
`test_racing_assets.py` the asset validation and its lists against the service's.
