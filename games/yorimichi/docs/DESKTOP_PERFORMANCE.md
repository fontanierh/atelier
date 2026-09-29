# Desktop performance and lighting — September 14

> Moved from the prototype repository on 29 September 2026. Paths are translated to this repository where the file moved; paths still starting with `japan/` or `output/imagegen/` refer to the prototype archive (authoring tools, earlier revisions, review images). See [docs/MIGRATION.md](../../../docs/MIGRATION.md).

The target is the native desktop game at 1440 pixels high and stable 60 FPS. Phone streaming is off. A future phone preview should mirror desktop play; it is not the performance acceptance target.

## Correct the lighting without expensive screen probes

The hard patches on the inverted character come from the irradiance-field interpolation offset. `r.Lumen.IrradianceFieldGather.ProbeOcclusionBias` had been raised from the engine default 0.8 to 2.0 to address building-foundation shading. Restoring **0.8** removes the abrupt patches in matched game-r10 flip captures, while retaining medium GI's cheaper gather method 0. Neither the mesh, animation, skin roughness nor hair is changed. No screen-probe override is restored.

The local UE 5.8 shader `LumenIrradianceFieldInterpolation.ush` offsets its sample by a combination of the surface normal and view direction, proportional to the cell size and this bias. The first clipmap spans 100 m with a 64-cell grid. The excessive offset can sample substantially different lighting across a bent or inverted body. The diagnosis is supported by a single-variable reproduction, not merely by that source explanation.

*(image in the prototype archive: desktop-performance-2026-09-14/flip-probe-offset.jpg)*

Full 138-frame sequences: `build/yorimichi/cairo/desktop-bias20/` and `desktop-bias08/`. The focused flip shortcut intentionally skips sprint, so its final waist-curve assertion reports false; these are visual diagnostics, not a full gameplay pass. Both use the same game-r10 source and 1600×900 capture settings. Frame 99 reproduces the hard bands with 2.0 and smooth shading with 0.8; later rotated/recovery frames were also inspected.

Three arcade A/B pairs retain the roof, shopfronts and foundation shading in the inspected images. Late medians are 36.45 vs 36.42 ms: this adjustment is not claimed as a performance saving. Earlier phases drift, so their apparent 3 ms gains are not attributed to the bias. The comparison is in `build/yorimichi/perf60/desktop-opt-bias-arcade/` and its [compact timing record](desktop-performance-2026-09-14/desktop-opt-bias-arcade.json).

A separate complete opening gallery from simulation time 0 through 12 seconds passes all checks: walk/run/sprint speeds, ground dash, double jump, the waist corrective (0.9) and bounded hair flex (0.943536). This uses the actual default config with no bias override: `build/yorimichi/cairo/desktop-lighting-gallery/`.

## Measure the actual desktop presentation

The offscreen spawn captures on this machine measured 29–35 ms at 2228×1440. A fox animation preview was running in Claude; closing its pane improved a subsequent run but did not explain the entire difference. CPU process scans alone do not establish that the GPU is free: they miss browser and application previews. No unrelated Claude task or command-line job was stopped.

The benchmark now supports `--desktop-fullscreen`. It uses the same separate scene target, fixed native render height, display aspect and full HUD as `run.sh desktop-1440`, and still rejects a PNG dimension mismatch. A first attempt omitted the viewport initialization command and captured 2056×1329; that run is rejected, not counted as 1440p evidence.

The verified visible baseline, uncapped and with dynamic resolution disabled, is **2228×1440** (2232×1440 padded scene allocation): **17.23 ms median / 19.97 ms p95 / 20.60 ms p99**, about 58 FPS median. Only 11% of frames meet 16.67 ms. This establishes the user's desktop shortfall, without conflating it with slower offscreen execution. It does not establish a precise OS scheduling cause for the difference. [Baseline record](desktop-performance-2026-09-14/desktop-opt-visible-native.json).

```sh
python3 games/yorimichi/tools/benchmark.py UNIQUE_NAME --desktop-fullscreen \
  --view spawn --width 2228 --height 1440 --seconds 25 \
  --settings 'desktop=1;performance=1;render_scale=100' \
  --commands 'r.DynamicRes.OperationMode 0,r.ScreenPercentage 100,r.RHISetGPUCaptureOptions 0' \
  --launch-arg=-noshaderworker
```

The width must match the current display aspect. Keep one heavy render job under the existing render lock and 10 GiB memory guard. The game is visible during this test and exits automatically. Screenshot/settling frames are excluded from timing. Native fullscreen timing is required before claiming desktop improvements; fixed-step animation captures remain visual evidence only.

## Rejected optimization

With the corrected probe offset, three fullscreen spawn shadow-cache pairs save **−0.18 / +0.11 / −0.14 ms**, with no consistent tail improvement. `r.Shadow.CSMCaching` stays off. There is no reason to accept its additional shadow-behavior differences for these results. [Comparison record](desktop-performance-2026-09-14/desktop-opt-shadow-cache.json).

## Optimized desktop renderer

Normal desktop launches now use the prepared forward renderer with sky intensity 0.33, the forward-compatible harbor fill at nominal 3 lux, 85 full-detail city visibility tiles and correctly scaled v4 city-tree LODs. It renders at 100% of the actual 1440-high scene, with dynamic resolution disabled. Character meshes, materials, hair motion, outfit correctives and animations are unchanged. Original grass and painterly strength are retained. The source/experiment receipt verifies all 413 files before starting; this is not an unvalidated swap of generated packages.

The renderer avoids the old irradiance-field character bands entirely. The 0.8 bias fix above remains useful for the deferred comparison path. Forward still differs in ambient bounce, covered shade and water contacts because it lacks Lumen bounce and screen-space reflections. Sky intensity 0.33 corrects the washed-out ambient/water; the harbor spot restores the warm fill that forward's single directional light cannot provide. It does not reproduce the old second directional light's shadows. See the September 12 [renderer study](performance-1440/FORWARD-DESKTOP-PREVIEW.md) for provenance and limitations.

All following tests use **visible fullscreen 2228×1440**, 100% scale, dynamic resolution off, uncapped, on this M3 Pro. There is no fixed timestep. These are measured runs, not sums of savings from separate studies:

| Scene / route | Median | p95 | p99 | Frames ≤16.67 ms |
|---|---:|---:|---:|---:|
| Original desktop, spawn | 17.23 ms | 19.97 ms | 20.60 ms | 11.00% |
| Optimized desktop, spawn | 11.53 ms | 13.93 ms | 14.83 ms | 99.77% |
| Forest village, 45 s running | 10.77 ms | 13.20 ms | 14.32 ms | 99.98% |
| City centre/plaza, 45 s running | 12.47 ms | 15.20 ms | 15.80 ms | 99.77% |
| Wide city approach, 45 s running | 12.27 ms | 16.41 ms | 18.75 ms | 96.97% |

Each moving run covers **182.7 m** with 100% moving time and zero stalls or recoveries. The village loops six times; the plaza reverses twice. The approach advances from waypoint 0 to 123 of 559 and does not reach the town centre in 45 seconds; the separate plaza run supplies that coverage. Compact records are in [desktop-performance-2026-09-14](desktop-performance-2026-09-14/). Raw CSV, command, settings, exact output dimensions and memory telemetry remain in the correspondingly named `build/yorimichi/perf60/desktop-opt-*` folders.

The baseline and candidate spawn runs are separate launches, so their difference is not presented as a paired causal measurement immune to machine drift. The actual candidate routes establish useful headroom, but **not a universal locked 60 FPS**: the approach's first wide views still contain occasional 19–23 ms frames. Its game thread remains about 1.8–1.9 ms, while distant geometry makes the base pass and depth prepass more expensive. Do not attribute this residual to the character's dense sprint bake or reduce animation fidelity to address it.

### Capped desktop presentation

A final run uses the normal desktop cap/VSync settings on the same city-approach route: `--capped` plus `r.VSync 1`, native 2228×1440, 100% scale, DRS off, no fixed timestep. Across 45 seconds and 182.7 m it measures **59.995 FPS average**, **16.6671 ms median / 16.6806 ms p95 / 16.6975 ms p99**, with a maximum measured frame of **16.7217 ms**. Every measured frame is within 17.2 ms. Movement validation passes with zero stalls or recoveries. [Capped record](desktop-performance-2026-09-14/desktop-opt-city-capped.json).

This establishes stable engine frame pacing for that visible desktop run. It is not a hardware display scanout measurement or a guarantee for every route, weather setting, background workload or a 2560×1440 external display. The tiny fluctuations around 16.6667 ms make the strict “≤1000/60” percentage unsuitable as a dropped-frame metric for a capped test. Keep the uncapped route results above as the separate headroom measurement.

### Keep meaningful route validation

The legacy `road_walk` benchmark enabled `bJog`. Cairo maps that retired gait to Walk, only about 92 cm/s. The road recovery heuristic requires 150 cm of progress within 1.2 seconds, so two initial tests repeatedly recovered and never traversed the route. Those `desktop-opt-forward-city-walk` and `desktop-opt-forward-village-walk` runs are invalid performance evidence. The harness now selects the new character's actual Run (rate-scaled Sprint), around 406 cm/s. Recovery thresholds and normal game controls are unchanged. All three runs in the table pass the original movement checks.

### Rejected detail reduction

At the slow city-approach camera, changing `foliage.LODDistanceScale` from 0.75 to 0.6 saves only 0.370 / 0.299 / 0.290 ms across three alternating pairs. It visibly simplifies some building detail. Keep 0.75: the small gain does not justify that difference. No further foliage-distance reduction is installed. [A/B record](desktop-performance-2026-09-14/desktop-opt-distant-lods.json).

### Scene lighting checks

Current native fullscreen static checks are 8.32 / 8.67 / 9.27 ms at the harbor, 12.03 / 14.84 / 15.15 ms at the lake, and 11.32 / 14.05 / 14.38 ms in the arcade (median / p95 / p99). The inspected harbor retains warm paving/boats and blue water; the lake is no longer pale white; the covered arcade retains legible warm wood, roof detail and ground shadows. Those images establish these views only, not equivalence to deferred everywhere. Their on-image FPS labels are cold startup values from the pre-measurement screenshot and are not the measured rates.

*(image in the prototype archive: desktop-performance-2026-09-14/forward-lighting-views.jpg)*

The current character also passes a complete opening gallery from time 0 through 12 seconds under forward: walk/run/sprint, ground dash, double jump, waist corrective 0.9 and bounded hair flex 0.943536. Sprint and inverted flip images were inspected for bands and clipping. Source: `build/yorimichi/cairo/desktop-forward-lighting-gallery/`, with the [result](desktop-performance-2026-09-14/forward-lighting-gallery-result.json) preserved here. These 1600×900 fixed-step images validate appearance and animation, not performance. No character re-export was performed.

## Desktop launch and reproducibility

```sh
# Normal game: fullscreen, native 1440-high, full HUD, saved player preferences.
atelier play yorimichi --profile desktop-1440

# Windowed counterpart.
atelier play yorimichi --profile desktop

# Previous deferred renderer for comparison/fallback.
atelier play yorimichi --profile desktop-1440-baseline
```

The forward override is per process; neither normal launch nor comparison rewrites `DefaultEngine.ini`. Normal desktop play uses `JapanProto/Saved/settings.txt`, preserving the player's camera, controls and art preferences, and saves menu edits there. Only the session defaults for desktop/performance/native 100% are selected by the launcher. Optional second-argument `key=value;...` overrides remain supported. Direct `python3 games/yorimichi/tools/desktop_preview.py` comparison launches still seed an isolated preference file; use `--shared-settings` for normal-play behavior.

READY requires the correct renderer, all three asset/fill operations, separate scene target, actual 1440-high viewport, a matching nonempty capture and the requested preference path. Runs keep `manifest.json`, `ready.json`, `ready.png`, `game.log` and memory telemetry under `build/yorimichi/desktop-preview/<timestamp>/`. The shared render lock and independent 10 GiB guard remain active. Phone streaming remains off.

This is the **prepared local desktop build**, not a cooked distributable. A clean checkout must generate the original assets and prepare/validate the tile and city-tree packages according to [city tiles](performance-1440/CITY-SURFACE-TILES.md) and [tree LODs](performance-1440/CITY-TREE-LOD-STUDY.md). The launcher refuses missing or modified receipt files; do not regenerate a receipt merely to silence the guard. Shipping packaging, all-weather/all-location acceptance and a universal 60-FPS guarantee remain outside the evidence established here.

Validation: native C++ Development Editor build succeeds with two compile actions; 6 desktop-launcher tests, 11 benchmark tests and 5 performance-pipeline tests pass. Shell syntax and diff whitespace checks pass. The settings menu now describes Quality as increasing shadow detail instead of promising lighting features unavailable in forward.
