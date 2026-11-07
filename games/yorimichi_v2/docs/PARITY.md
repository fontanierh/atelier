# Yorimichi V2 visual parity (plan P3.6)

Both games are captured the same way, as a runtime viewport screenshot through each game's live bridge
(`tools/parity/capture_runtime.py`). The donor's scenery exists only at run time, so an editor capture is no
baseline. `tools/parity/compare.py` checks both receipts and scores each pose. A receipt must name the revision its
game was proven to launch from: the live session's launch commit for V2; for the donor, which has no session record,
HEAD of the checkout whose project the process on its live port runs, unmoved since that process started.

**What this comparison proves.** It compares lighting, terrain and the scenery the slice has already migrated (W00
environment, W01 start, W04 pier approach). It does not prove the whole view matches the original. Two of the four
cameras stand outside the migrated regions, and their missing landmarks are listed below. A whole-image score passes
with those landmarks absent, so it closes none of them.

## Slice result (2026-11-07)

Donor 7eec0f98dd (forward, through its desktop launcher). That checkout is dirty: 31 local edits to its export and
import scripts and its hippodrome and skate park sources, made for the one-time donor export. None touch C++, config
or packages. V2 main aea8c3c860 (clean), with the C01 edits merged. 4 poses at 2560x1440, both receipts carrying their
proven launch revision; gate `--min-ssim 0.75 --max-mad 0.04`: pass.

| Pose | Camera (cm) | In migrated regions | SSIM | MAD |
|---|---|---|---|---|
| coast_start | -23600, 16000 | no: south of W01 (y > 12800), west of W04 | 0.910 | 0.031 |
| start_road | -24830, 10000 | W01 | 0.790 | 0.038 |
| pier_path_top | -15421, 8680 | W01 | 0.878 | 0.018 |
| pier_arrival | -200, 36200 | no: north of W04 (y > 25600) | 0.868 | 0.031 |

The earlier pass (V2 b563d5d3f1, dirty) predates the receipts' launch proof, and `compare.py` now refuses it.

### Missing landmarks and where they belong

| Seen from | Missing in V2 | Belongs to | Status |
|---|---|---|---|
| coast_start | the food stall, the paper-lantern post and the sign beside the coast path | the coast south of W01, not yet a region | open: about 60 m south of the spawn (-25526, 9951, on the W01 road), off the start route, which runs east along the road to the pier path |
| coast_start | the cliff forest on the headland across the bay | the headland, not yet a region | open (backdrop) |
| pier_arrival | the forested hillside above the beach, behind the pier | the slope north of W04, not yet a region | **open**: it frames the pier arrival, the route's end |
| pier_arrival | the town on the far shore (top left) | the town regions | open (backdrop) |
| all | falling leaves | the leaf effect (P4) | open, P4 |
| start_road | the donor's view shows its fox (the donor's pawn is not hidden) | capture difference, not scenery | none |

Foliage and grass sway in the wind, which keeps SSIM lower on foliage than MAD suggests.

### Defects the first comparison found (fixed)

The first comparison scored SSIM 0.77–0.86 and MAD 0.065–0.105. It found three V2 defects:

- The coast at `coast_start` was sea. Island cells outside the migrated regions were skipped, so they now belong to
  the environment region (277 terrain and far-hill pieces).
- A migration rerun placed every World Partition actor that was not loaded again. Duplicates appeared and a scene
  patch overwrote a placement edit. The migration now loads every actor before matching stable IDs, and a rerun
  creates nothing.
- Surfaces were 10–34% brighter and bluer, from the sky light only. Measured with the sky light off, the two games
  matched within 2%; with the sun off, V2 was 20–52% brighter. The original's desktop launcher set the forward sky
  light and distance-field settings, which are now the game's own (DECISIONS D09).

## Route on the same build

`tools/test/route.py` ran twice on the aea8c3c860 game, after the captures. The second run passed: 15.5 m walked at
≥3.5 m/s, a skate top speed of 8.5 m/s with 0.0 cm deck variation, and the lowest sampled fps 59.9 over 20 sampled
frames. The first run failed at a lowest sampled 3.1 fps, as on the earlier build. The capture had already visited
`start_road`, so this is not only first use of that place. The packaged slice (below) answers the open question:
its first arrival does not stall.

## Packaged slice (P3.5, 2026-11-07)

`atelier build yorimichi_v2 unreal.package` ran in the asset workspace at aea8c3c860, with a warm editor build and
the game target compiled cold. The first attempt was stopped by the guard's default 10 GiB ceiling at 3791 of 7330
cooked packages (cook editor 9.6 GB). The rerun with `--cook-memory-gib 20` passed: 1062 s, 7331 packages, a
2.1 GB archive, tree peak 10.35 GiB. So the slice cook needs more than the default ceiling; ordinary play does not.

The archive was copied to a folder outside every checkout and played from there under the guard (`kind=game`,
16 GiB). The game's own traverse (`-benchmarkview=traverse -benchmarkseconds=20`) starts at `player_start` on the
W01 road: 8 s standing, then 5 s walking, 5 s jogging and a jump. UE's CSV profiler recorded every frame from boot
(`-csvCaptureFrames`), so the first arrival is inside the record.

| Run | Launch to first frame | Frames over 50 ms after it | 20 s walk: median / p99 / max frame | Guard peak |
|---|---|---|---|---|
| First launch after extraction (see note) | 8.1 s | 435, 143, 89, 79, 447 ms | not recorded | 3.56 GiB |
| Warm 1 | 7.6 s | 141, 84, 442 ms | 16.67 / 17.5 / 44.4 ms (1 frame over 33 ms) | 3.75 GiB |
| Warm 2 | 7.7 s | 143, 86, 443 ms | 16.67 / 17.1 / 20.9 ms | 3.80 GiB |
| Warm 3 | 7.7 s | 142, 84, 447 ms | 16.67 / 17.0 / 21.7 ms | 3.80 GiB |

In each warm run Cairo walked 45 m from `player_start` (-25 526, 9 951) down the road. Frame times hold the 60 fps cap the
benchmark sets. The three long frames come at the same frame numbers each time: frame 1, frame 114 (about 2 s
after the first frame) and frame 442 (about 8 s after it, as the benchmark ends its warm-up and starts its own
capture). None falls in the walk.

So the packaged first arrival does not reproduce the editor route's first run (lowest sampled 3.1 fps, "Route on
the same build"). That stall is specific to the editor game; its cause there is not measured.

Note on the first launch: it was started with UE's own `-benchmark` switch by mistake, which fixes the time step and
exits after `-benchmarkseconds` of game time. Its load and first frames are valid; its walk is not, and the warm runs
dropped the switch. `-csvExitOnCompletion` did not end the warm runs once the capture was written: the guard stopped
warm 1 at its 600 s limit, and warms 2 and 3 were quit with SIGTERM after their CSV was written.

### What the package asked for and did not have

271 packages were requested by path and are not in the cooked game. None is committed V2 content:

| Requested | Count | Why it is absent |
|---|---|---|
| `/Game/Audio/Skate/*`, `/Game/Audio/Bike/*` numbered variants (`catch_04`–`08`, …) | 152 | the code probes variant numbers until one is missing; the donor never had these numbers either |
| `/Game/SkateRide/Clips/B0` and `B1` transition clips | 94 | looked up by name; the donor has none of these names |
| `/Game/CairoBike/*`, `/Game/CairoHorse/*`, `/Game/Horses/*` | 25 | bike and horse assets, not yet migrated (P4-E) |

The same two errors appear in the editor game: `HORSE roster … no coat or hair master` (P4-E) and `CITY TREE LODS
incomplete child swap 0/12`. The second comes from the city tree LOD experiment, which looks for runtime-spawned
city groups that the slice now holds as saved actors. It belongs to P5's runtime spawner removal.

Runtime data (`Content/Data`, for example `horses/roster.json`) is staged inside the app. The log names no path
inside a source checkout. The package also kept the template bundle identifier (`com.YourCompany.YorimichiV2`), like
the donor's, so its saved data lives in that sandbox container.
