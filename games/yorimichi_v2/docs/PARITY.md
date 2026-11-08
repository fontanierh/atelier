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
`start_road`, so this is not only first use of that place. It stays open: the packaged slice (below) has measured a
walk from spawn, not this walk and skate route.

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

What this shows, and no more. On every warm launch the packaged game has long frames at frame 1 (141–143 ms),
frame 114 (84–86 ms) and frame 442 (442–447 ms); the first launch had 435 ms at frame 1. Its warmed 20 s walk from
spawn holds 60 fps. The first launch's walk
was not validly recorded (see the note). The editor route's first run (lowest sampled 3.1 fps, "Route on the same
build") covered a different path, the walk and skate from `start_road` and the pier. So whether that route stalls
in the package is not yet measured. Measuring it needs the same route in the package with real-time stepping and a
frame trace from boot. The game's benchmark has no view for the pier ride, and the package has no live bridge to
drive one, so that takes a route view and a new cook.

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

## Whole-island pose set (P5, 2026-11-08)

`tools/parity/island_poses.json` holds 54 viewpoints, at least two for every world row W01–W20 and three for W00 (the
sea and coast views). `tools/parity/make_island_poses.py` writes it from committed data: unreal/Content/Data (world.json,
city.json, the per-feature JSON), `world/regions/*/region.toml` bounds and `heightmap.bin`. Every pose's `source` names
its target's file. Rerun the generator rather than editing the file; `tests/test_island_poses.py` fails when they differ.
Pose names are `<wrow>_<what>`. Cameras stand outside and above the landmark, at least 10 m above the ground the
heightfield or nearest committed scenery gives. Walls and canopies between camera and target are not checked.

Capture a subset with `--only` (fnmatch globs, comma separated or repeated; every glob must match). The receipt then
names only the subset, and compare.py needs the same `--only`:

    uv run python games/yorimichi_v2/tools/parity/capture_runtime.py --source donor-runtime \
        --checkout DONOR_CHECKOUT --port 8830 --poses games/yorimichi_v2/tools/parity/island_poses.json \
        --only 'w07_*' --out build/yorimichi_v2/parity/island-donor
    uv run python games/yorimichi_v2/tools/parity/capture_runtime.py --session ID --source v2 \
        --poses games/yorimichi_v2/tools/parity/island_poses.json --only 'w07_*' \
        --out build/yorimichi_v2/parity/island-v2
    uv run python games/yorimichi_v2/tools/parity/compare.py build/yorimichi_v2/parity/island-donor \
        build/yorimichi_v2/parity/island-v2 --out build/yorimichi_v2/parity/island-report --min-ssim 0.75 \
        --poses games/yorimichi_v2/tools/parity/island_poses.json --only 'w07_*'

Omit `--only` for all 54.

### First whole-island run (2026-11-08)

Donor `7eec0f98dd` (desktop profile) and V2 `1d9ac65d77` (`jim5/yv2-statics-run`, clean), 2560x1440, all 54 poses,
`compare.py --min-ssim 0.75`. Both games ran under the normal play guard; whole-island V2 needs `--memory-gib 22`
(it peaks near 20 GiB while far tiles stream in; 10 and 16 GiB stop it during startup).

| Settle per pose | Pass | Below 0.75 |
|---|---:|---|
| 8 s (the old default) | 47 / 54 | w07 harbour pier, w07 station yard, w20 Hidamari platform, w20 corridor viaduct, w17 Hidamari ferry pier, w02 teahouse, w13 Ronin camp |
| 30 s (the 7, plus w05 far northeast as a control) | 51 / 54 | w17 Hidamari ferry pier 0.71, w13 Ronin camp 0.70, w02 teahouse 0.59 |

- At 8 s V2 was still streaming Hidamari's city cells and the corridor forest in (flat sea plane where the town stands,
  bare slopes); at 30 s the same views score 0.78 to 0.96. The capture default is now 30 s.
- The three still below 0.75 show the same scenery by eye. The teahouse and camp cameras stood inside the canopy, so
  leaf motion dominated the score; they now stand 30 and 35 m above their targets (make_island_poses.py), and both
  pass from there (teahouse 0.81, Ronin camp 0.76; donor and V2 recaptured at 30 s). The ferry pier differs only by
  the ferry, docked in the V2 frame and away in the donor's: a moving service, not scenery.

Result: 53 of 54 poses at SSIM >= 0.75; the one below is the ferry's schedule position.

**Unfinished views.** Eight first-run V2 shots still showed "Preparing Static Meshes (N)" (w05 far east, w09 Brine Cove
ferry, w11 Mega Park overview, w12 volcano west flank, w13 Ronin camp, w18 gondola Belmonte station, w19 zeppelin
Hidamari), several of them passing on score. A score is no proof that a view finished, so V2 captures now also wait,
after the settle, until `YorimichiLive.PendingAssetCompiles()` is 0, refuse a pose still compiling 300 s later, and
record each pose's extra wait in the receipt (`compile_waits_s`; the donor has no such verb). Those eight, recaptured on
both games with the revised poses at 30 s: no message in any V2 shot, no extra wait needed, six pass at 0.85 to 0.98.
The teahouse and Ronin camp views scored 0.72 and 0.73 in this run, against 0.81 and 0.76 in the previous one: the
hamlet, its houses, paths and trees match, and the near canopy's leaves move between frames. Treat those two as
foliage-limited views around the threshold, not as content differences.

