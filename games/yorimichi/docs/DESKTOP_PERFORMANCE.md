# Desktop performance

The desktop target is the game at its native 1440-pixel height, 100% render scale, at a steady 60 fps. The default
`play` profile uses the measured desktop tuning on the reference machine (an M3 Pro): forward rendering, city surfaces
split into visibility tiles and optimized city-tree LODs. `fullscreen` uses the same tuning in fullscreen;
`desktop` and `desktop-1440` remain aliases. Saved quality and art preferences are preserved. This page covers the
desktop profiles, the settings that matter, how to measure with
`tools/benchmark.py`, the scripted routes it drives, and the reference measurements.

## Desktop play profiles

```sh
atelier build yorimichi                                   # includes unreal.desktop: city tiles and tree LODs
atelier play yorimichi                                    # default native 1440 window
atelier play yorimichi --profile fullscreen               # same defaults fullscreen
atelier play yorimichi --profile desktop-1440             # fullscreen
atelier play yorimichi --profile desktop                  # in a window
atelier play yorimichi --profile desktop --set 'show_fps=0'
```

All four profiles run `tools/desktop_preview.py --shared-settings` (`play` and `desktop` add `--windowed`); `--set` is passed on as
`--settings`. The launcher starts the editor binary with `-game` at `-resx=2560 -resy=1440`, under the render lock and
the 10 GiB memory guard, and chooses the renderer per process with Unreal's `-ini:` override, so `DefaultEngine.ini` is
never rewritten. `--memory-gib N` reaches the launcher too; the normal 10 to 14 GiB range remains enforced.

Forward lighting and tree optimization are the defaults, including when `Saved/settings.txt` has no corresponding
keys. The graphics menu saves `renderer=0` (forward) or `renderer=1` (Lumen), and `tree_optimization=1` or `0`.
Enabling Lumen requires confirmation of its higher GPU and memory use and a restart; disabling tree optimization
requires confirmation that it can lower the frame rate. The launcher passes `-renderrestart` and a fresh
`-renderrestartrequest=<run>/renderer-restart.txt` path. After a confirmed renderer change the game saves the preference,
writes `renderer=0` or `renderer=1` to that file and quits normally. The launcher releases the old render lock,
verifies the request matches a changed saved choice, consumes it and starts a new guarded
process with it. Direct editor launches save the choice for the next launch instead of promising an automatic restart.
On restart the saved menu renderer wins over an earlier `--set renderer=...` or `--baseline` comparison override.
Tree changes apply in the current game; subsequent launches honor the saved choice.

| Flag | Effect |
|---|---|
| `--windowed` | a window instead of fullscreen |
| `--shared-settings` | use and save the game's own `unreal/Saved/settings.txt` (camera, controls, quality, art, renderer and trees); `desktop=1` is session-only. Performance mode and 100% render scale are defaults when absent, rather than overwriting saved choices. Without it, the session gets a copy of that file and a fixed look (painterly 0.35, exposure 0.9, sun 48°/15°, FPS shown) |
| `--settings 'key=value;...'` | extra preference overrides for this session |
| `--baseline` | explicitly use deferred Lumen and the full sky light for comparison; the launcher prints its resource warning |
| `--memory-gib N` | guard ceiling for this run, 10 to 14 GiB |
| `--dry-run` | print the launch command |

`YORIMICHI_EXTRA_ARGS` and CLI arguments after `--` append Unreal arguments. Each run writes `build/yorimichi/logs/desktop-<YYYYmmdd-HHMMSS>/`:
`game.log`, `stdout.log`, the guard's `memory-health.json`, `ready.png` (the game buffer a few seconds after startup)
and, without `--shared-settings`, the session's `settings.txt`. Renderer restarts have separate `restart-N` log
directories but keep the same preference file. When the game exits, the launcher checks the log and
prints `verified: {...}` or `not verified: ...` (exit code 1):

- the viewport is 1440 high, 1600 to 3840 wide, in the requested window mode;
- the log reports the selected renderer (`r.ForwardShading = "1"` for forward, `"0"` for Lumen);
- `CITY TILES` reports exactly the source and tile counts in the completed staged
  `Content/Data/city_surface_tiles/v1_128m/manifest.json`, rather than a historical fixed count;
- `CITY TREE LODS tag=v4 enabled=0|1 forced=0 groups=3` matches the selected tree preference, and forward launches
  report `FORWARD FILL nominal_lux=3.000 lights=1`. A missing marker
  means the imports are missing: `atelier build yorimichi unreal.desktop`.

This is a local build run from the editor binary, not a cooked package.

Agent-launched processes use `atelier.safety.process` on macOS: application scheduling policies, at least
nice 10, without imposing a thread QoS clamp. This prevents inherited background scheduling from distorting imports
and game measurements. Native review and benchmark launchers use the same helper. The command still owns the
actual child PID, render admission, memory ceiling and cleanup; worker counts and caches stay unchanged.
For unexpectedly slow runs, inspect `ps -o pid,ni,pri -p PID` using the actual child from `memory-health.json`.
An inherited background band can limit CPU throughput even with abundant free RAM and no swap. Correct the
launch context before comparing performance or raising resource limits; compare equivalent cached inputs.

## Settings that matter

Set by the launcher (`desktop_preview.py`):

| Setting | Value | Why |
|---|---|---|
| `r.ForwardShading` (`-ini:` override) | True by default | forward lighting; saved Lumen selects False at process startup |
| `r.GenerateMeshDistanceFields`, `r.MeshCardRepresentation` (`-ForceDPCVars`) | 0 for forward only | avoids generating unused distance fields and cards during first editor play; Lumen retains their generation |
| `-desktopnative1440`, `DesktopPreviewViewportClient` | | a separate scene target fixed at 1440 high and the window's aspect, independent of macOS's scaled window drawable |
| `r.SkylightIntensityMultiplier` | 0.33 | forward has no Lumen bounce; the full sky light washes out the ambient and the water |
| `japan.ForwardHarborFill` | 3 (lux) | a warm, shadowless spot light standing in for the harbor's second directional fill, which forward cannot render |
| `japan.CitySurfaceTiles` | `v1_128m 1` | the city surfaces split into 128 m visibility tiles, with every polygon and attribute kept; count follows the current manifest |
| `tree_optimization` (native preference) | 1 by default | city-tree LOD1/2 that keep every leaf and simplify only the leaf outlines; the menu can restore original trees |
| `r.DynamicRes.OperationMode`, render scale | 0, 100% by default | native resolution without dynamic resolution; saved render scale remains in effect |
| `t.MaxFPS`, `r.VSync` | 60, 1 | the 60 fps cap |
| `r.Shadow.CSMCaching` | 0 | caching saved −0.18 / +0.11 / −0.14 ms in three fullscreen spawn pairs, with no consistent tail gain: not worth its shadow differences |
| `r.RHISetGPUCaptureOptions` | 0 | Metal's per-frame GPU-capture labels otherwise accumulate in a development build |

It also sets `r.Shadow.CSMSlopeScaleDepthBias 3` and runs `japan.PreviewInfo`, which logs the viewport for the check above.

Set by the game's preferences with `desktop=1` and `performance=1` (`JapanPreferences.cpp`):

| Setting | Value | Why |
|---|---|---|
| `foliage.LODDistanceScale` | 0.75 | 0.6 saves only about 0.3 ms on the city approach and visibly simplifies building detail |
| `sg.GlobalIlluminationQuality` | 1 | medium GI (the irradiance field) in the deferred path |
| `r.Shadow.CSM.MaxCascades`, `r.Shadow.MaxCSMResolution`, `r.Shadow.DistanceScale`, `r.DistanceFieldShadowing` | 2, 1024, 0.5, 0 | performance-mode shadows |
| `r.SceneColorFormat` | 2 (R11G11B10) | HDR at half the bandwidth: about 1 ms in the forest and harbor at native 1440 |
| `r.TemporalAA.Quality` | 3 | about 0.3 ms, character edges kept in sprint and double-jump frames |
| `r.InstanceCulling.OcclusionCull` | 1 | culls instances the depth buffer hides (both profiles) |
| `japan.HarborFillAuto` | 1 | no cascades for the harbor's second directional light when every receiver is beyond cascade range |

In `unreal/Config/DefaultEngine.ini`, for the deferred path: `r.Lumen.IrradianceFieldGather.ProbeOcclusionBias=0.8`,
the engine's default. A larger offset puts opposite sides of the inverted character into different probe cells and
bands the lighting during flips; 0.8 costs nothing measurable (arcade medians 36.45 against 36.42 ms).

## Measuring with benchmark.py

`tools/benchmark.py` runs one real-time capture of the game and writes `build/yorimichi/perf60/<name>/` (the name must be
new): `manifest.json` (command, commit, settings, engine config, binary and asset hashes), `game.log`, `stdout.log`,
`memory-health.json`, `view.png`, `frames.csv`, `route.json` and `results.json` (median, p95, p99, median and average
fps, the share of frames within 16.67 ms, and GPU stat medians). The game settles for 8 s, takes `view.png`, then
records `--seconds` (10 to 1800, default 25).

It refuses to start while another Unreal, shader-compile or Blender process runs (`--wait-renderer S` waits up to S
seconds), takes the render lock and the 10 GiB memory guard, and fails a run that another render job overlapped.

```sh
# The desktop profile, visible fullscreen at native 1440 (width = 1440 x the display's aspect, rounded to even).
uv run python games/yorimichi/tools/benchmark.py desktop-spawn-01 --desktop-fullscreen \
  --view spawn --width 2228 --height 1440 --seconds 25 \
  --settings 'desktop=1;performance=1;render_scale=100' \
  --ini '[/Script/Engine.RendererSettings]:r.ForwardShading=True' \
  --commands 'r.DynamicRes.OperationMode 0,r.ScreenPercentage 100,r.RHISetGPUCaptureOptions 0,r.Shadow.CSMCaching 0,r.Shadow.CSMSlopeScaleDepthBias 3,r.SkylightIntensityMultiplier .33,japan.CitySurfaceTiles v1_128m 1,japan.CityTreeLODs v4 1,japan.ForwardHarborFill 3' \
  --launch-arg=-noshaderworker

# Running along a scripted route, offscreen at 1920x1080.
uv run python games/yorimichi/tools/benchmark.py village-walk-01 --view road_walk --route village --seconds 45 --hide-hud
```

| Option | Meaning |
|---|---|
| `--view` | static cameras: `spawn` (default), `portrait`, `forest`, `coast`, `village`, `north_overview`, `park`, `station`, `lake`, `harbor`, `arcade`, `plaza`, `city`, `custom` (with `--camera X Y Z PITCH YAW FOV`, player hidden); moving: `traverse` (walk, jog, run and a jump), `road_walk` (runs a scripted route) |
| `--route` | with `road_walk`: `village` (default), `village_loop`, `mega`, `hidamari`, `arcade`, `plaza`, `harbor`, `harbor_pier`, `north`; `--road-index N` starts at route sample N |
| `--desktop-fullscreen` | the visible fullscreen game with the desktop viewport client; needs `--height 1440` and a `--width` matching the display's aspect. Without it the capture renders offscreen at `--width` × `--height` (default 1920×1080) |
| `--capped` | `t.MaxFPS 60` instead of uncapped; VSync stays off unless `--commands` adds `r.VSync 1` |
| `--settings`, `--commands`, `--ini`, `--launch-arg` | preferences (`-set=`), console commands at startup, `-ini:Engine:` overrides, extra Unreal arguments |
| `--compare-before`, `--compare-after` | a paired ABABAB test on a static view: six phases of `--seconds`, each after 8 s of settling; settling and screenshots are excluded from timing; `results.json` gets the three paired savings |
| `--hide-hud` | a clean `view.png`; timings are unchanged |
| `--boot` | the 900-frame boot capture instead of a scene view |

Rules for numbers:

- Desktop claims need `--desktop-fullscreen`. Offscreen captures run slower on the reference machine (29 to 35 ms
  against 17 ms visible, deferred spawn at 2228×1440), and fixed-step captures (`capture.py`, the QA scenarios) are
  visual evidence only.
- A moving view fails unless the character moved for at least 90% of the window, never stalled over 2 s, travelled at
  least 10 m, and needed at most one stall recovery per 30 s (`route.json` has the distance, stalls and waypoints).
- Uncapped runs measure headroom; `--capped` with `r.VSync 1` measures frame pacing. The share of frames within
  16.67 ms is meaningless for a capped run, whose frames hover around 16.667 ms.
- Separate launches drift: compare settings with `--compare-before/--compare-after`, or alternate several runs.

## The benchmark and trailer routes

A scripted character follows an authored path: `road_walk` in `benchmark.py`, and trailer shots (`capture.py`, shot
files with `road_index`, `follow_road` and skate shots). `-reviewroute=<name>` picks the path
(`AWandererCharacter::GetRoadSteering`, `JapanSkateReview.cpp`); `benchmark.py --route` and a shot's `route` field
pass it.

| `-reviewroute` | Path | Read from |
|---|---|---|
| none or unknown | the island road | `world.json` `road` |
| `village`, `village_loop` | the village's first and second paths | `world.json` `village.paths` |
| `mega` | the woodland trail to the mini-mega | `world.json` `mega.trail` |
| `hidamari` | the city arrival and the central street | `hidamari/city.json` `review_route` |
| `arcade`, `plaza`, `plaza_steps` | the shopping arcade, the clock square, the square's steps | `arcade_route`, `plaza_route`, `plaza_steps` |
| `harbor`, `harbor_pier` | the fishing harbor quay, the pier | `harbor_route`, `harbor_pier_route` |
| `park`, `north` | the city park, the northern foothills trail | `park_route`, `north_trail` |

The character steers six samples ahead and patrols: it turns around eight samples short of either end, so a long run
keeps moving. If it has not moved 1.5 m in 1.2 s, it is turned around and put back on the route eight samples behind,
logged as `ROUTE RECOVERY` and counted (harness runs only, never a player session). `road_walk` runs at the default
run gait.

## Reference measurements

Measured on the M3 Pro, visible fullscreen at 2228×1440, 100% scale, dynamic resolution off, uncapped, no fixed
timestep. Moving runs cover 182.7 m in 45 s with no stalls or recoveries.

| Scene | Median | p95 | p99 | Frames ≤ 16.67 ms |
|---|---:|---:|---:|---:|
| Deferred Lumen, spawn | 17.23 ms | 19.97 ms | 20.60 ms | 11.00% |
| Desktop profile, spawn | 11.53 ms | 13.93 ms | 14.83 ms | 99.77% |
| Desktop profile, village, running | 10.77 ms | 13.20 ms | 14.32 ms | 99.98% |
| Desktop profile, city centre and plaza, running | 12.47 ms | 15.20 ms | 15.80 ms | 99.77% |
| Desktop profile, wide city approach, running | 12.27 ms | 16.41 ms | 18.75 ms | 96.97% |
| Desktop profile, harbor, static | 8.32 ms | 8.67 ms | 9.27 ms | |
| Desktop profile, lake, static | 12.03 ms | 14.84 ms | 15.15 ms | |
| Desktop profile, arcade, static | 11.32 ms | 14.05 ms | 14.38 ms | |

Capped (`--capped`, `r.VSync 1`) on the wide city approach: 59.995 fps average, 16.667 ms median, 16.681 ms p95,
16.698 ms p99, slowest frame 16.72 ms.

## Limits

- Forward shading has no Lumen bounce or screen-space reflections, so ambient bounce, covered shade and water contacts
  differ from the deferred look. The harbor fill has no shadows.
- Uncapped, the wide city approach still has occasional 19 to 23 ms frames in its first wide views: distant geometry
  makes the base pass and depth prepass expensive, while the game thread stays at 1.8 to 1.9 ms. Do not lower the
  character's animation fidelity for it.
- These numbers hold for the measured views and routes on the reference machine, not for every route, weather,
  background load or external display.
