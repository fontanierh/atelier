# Foliage implementation and real-game testing handoff

Branch: `codex/foliage-system`

Draft PR: <https://github.com/fontanierh/atelier/pull/493>

Implementation revision before this document: `2067080fe31ef43f5e354e6451e3e86f36bbd002`.

The implementation is pushed for testing on another machine. **The 10× performance target is not established. Full production preparation, real-game visual review and performance approval remain unfinished. Do not merge or release based on the isolated measurements below.**

## What is implemented

- One build-time foliage owner discovers vegetation across all regional namespaces, including vegetation embedded in mixed meshes. It generates bounded visual LODs, separate shadow meshes and conservative distant forest patches, verifies saved geometry and dependencies, and publishes a complete runtime registry.
- `UYorimichiFoliageSubsystem` owns both rendering modes. Original components retain placement and collision; optimized children handle rendering. Runtime audits reject missing registrations. Missing/stale products fail normal build or gameplay readiness.
- **Foliage optimization** is a persistent graphics setting, enabled by default. Disabling it warns and restores original rendering without a restart; cancellation and failed preference saves must preserve the prior state. The existing `tree_optimization` city-tree preference remains separate.
- `games/yorimichi/CONTRACTS` requires **all current and future vegetation** to use this system. Procedural authors/importers certify per-face roles; material/name semantics discover other sources. Explicit authored-prop budgets and exact collision-owner references are bounded policies, not general exemptions.
- The shared native builder preserves authored LODs through save/unload/rebuild/reload. Its tests cover registry rejection, toggle restoration, coverage, import roles and persisted mesh products.
- An explicit Entry-map diagnostic registration helper exists in the editor import module. It registers Python-created HISM components for rendering and builds their instance trees synchronously. It does not publish a registry or establish production readiness.

Architecture and authoring details: [FOLIAGE_SYSTEM.md](FOLIAGE_SYSTEM.md). Source library/build details: [FOLIAGE_BUILDS.md](FOLIAGE_BUILDS.md).

## What has actually been validated

- Five native automation tests passed at implementation revision `b451c797`: `Yorimichi.Foliage.AuthoredLODs`, `ImportRoles`, `PatchCoverage`, `Registry`, and `Toggle`. This includes the persisted-asset regression, not only transient meshes. They have **not** all been rerun on the final handoff head.
- An independent native probe rebuilt the formerly failing BarrelPlanter without preloading its destination; all four saved LODs retained 598 triangles, and the source package digest stayed unchanged.
- The later classification change passed 67 focused Python tests across `test_foliage_classification.py` and `test_foliage_system.py`. Additional focused tests were run during development for authoring roles, packages/cache repair, material bindings and performance-sample validation.
- Hosted `Studio Python / macOS` passed on exact earlier head `b451c797`: <https://github.com/fontanierh/atelier/actions/runs/39537770579>. **This is not a claim that final-head CI passed.** Inspect PR checks on the head being tested.
- The final diagnostic helper compiled successfully in 17.18 seconds and received independent static approval. Lint checked 9,679 files with zero problems; contract syntax/owners checked 1,626 source files successfully before the handoff documentation change. These checks do not prove visual quality or performance.

## First rendered measurement: limited scope

An isolated native scene used **1,460 actual Brinecove tree placements across 20 species**, identical transforms, camera and lighting, and prepared visual/shadow products. It ran forward rendering at **2560×1440, 100% render scale**, fullscreen, uncapped, with dynamic resolution and VSync disabled. Both modes were warmed; measurements used real frame callbacks and RHI GPU timestamps in Off/On/On/Off order, eight seconds per pass.

| Mode | Mean GPU time, pass 1 / pass 2 | Mean frame time, pass 1 / pass 2 |
| --- | --- | --- |
| Original meshes | 8.31 / 8.86 ms | 8.87 / 9.31 ms |
| Prepared visual + shadow meshes | 7.11 / 7.07 ms | 7.58 / 7.54 ms |

Averaged across pairs: **8.59 → 7.09 ms GPU (1.21×)** and **110 → 132 FPS (1.20×)**. This is a modest improvement, not 10×. The original passes differ by about 7%; use the raw per-pass values when assessing stability.

**This was not the normal game or the complete runtime system.** It excluded terrain/gameplay, retained near-source rendering and distant patch aggregation. It compared original HISMs with prepared visual/shadow HISMs. The proxy-only aerial capture visibly loses leaf detail and looks too coarse; it is not visual-quality approval. The normal subsystem's distance transitions still need inspection.

An earlier windowed comparison stayed near 60 FPS and is unsuitable for estimating gains: UE 5.8 Metal enables display synchronization in windowed mode even with `r.VSync=0`. Fullscreen removed that limit. An earlier diagnostic ground plane hid lower trees; it was lowered below every root before the fullscreen measurements. Blank/unregistered-scene samples were rejected.

Raw isolated samples, reports and original/proxy captures remain in the originating checkout's ignored `build/yorimichi/foliage_immediate/`. They are not committed source artifacts. The temporary isolated driver is not the repeatable production test; use the committed scenario below on the real game.

## Build state and first steps on the receiving machine

The last complete original-source import pass included the main world, regional imports, all 341 Brinecove meshes, Belmonte's nine planted authored props, materials, characters and city-tree preparation. **The shared derivative owner was stopped partway through its 2,619-candidate scan for the immediate test. No current complete production registry/readiness was certified.** Native module changes also have broad import invalidation, so let the normal graph decide what must rerun on the final revision.

Generated Content, Binaries, stamps and caches are ignored and are not transported by the Git push. Use the receiving machine's normal engine setup and guarded build workflow. Do not copy partial registry files, manufacture stamps, bypass readiness or use stale products to get a game running.

From a clean checkout of the branch, after that checkout's native callers have stopped:

```sh
git fetch origin
git switch codex/foliage-system
uv sync
uv run atelier fetch yorimichi
uv run atelier build yorimichi data.network --plan --explain
uv run atelier build yorimichi data.network
```

On a shared machine, register/verify the board listener and use the normal owner, admission and memory guards described in `AGENTS.md`. Preserve caches. Use verified `atelier reuse` only when its source/engine checks pass; independent copies only. No forced rebuild is needed by default.

Inspect the normal `unreal.foliage_system` report and completion marker before play:

- `build/yorimichi/foliage_system/report.json`
- `games/yorimichi/unreal/Content/Data/foliage_system/registry.json`
- `build/yorimichi/logs/unreal.foliage_system.guard/`

The owner must finish, verify its saved counts/digests and publish `FOLIAGE SYSTEM COMPLETE`. Partial output directories are not success. The receiving-machine follow-up batches material bindings into one editor property update per variant, preserving slot metadata and the appended canopy materials. Source material wrappers are prepared once for both variants. Focused tests cover binding order, metadata preservation and refusing incompatible layouts; native preparation and its timings still need validation. Do not weaken output verification to speed preparation.

On macOS, verify `xcrun -sdk macosx metal --version` before rendered testing. The originating machine initially lacked the Metal compiler; installing Apple's `MetalToolchain` component resolved startup. A successful NullRHI test does not check this prerequisite.

## Run the actual slow-view comparison

Use an owned loopback port; the example assumes **8841 is free and belongs to this session**. Run from the same clean checkout whose native code/content were built. Keep the renderer, render scale, city-tree setting and all other quality settings identical between modes. Honor saved renderer/tree preferences; record them rather than silently changing them. Use the same receiving machine for both modes.

```sh
uv run atelier play yorimichi --profile fullscreen -- -liveport=8841
```

Wait for normal gameplay readiness, then in another terminal:

```sh
uv run python games/yorimichi/scenarios/foliage_performance.py --port 8841 --take aerial_scout --aerial-scout --seconds 5 --settle 3
uv run python games/yorimichi/scenarios/foliage_performance.py --port 8841 --take slow_aerial_abba --camera-file build/yorimichi/foliage_performance/aerial_scout/slow_views.json --seconds 10 --settle 8
```

The scout chooses dense neighborhoods from actual tree placements in Momiji, Hidamari, Belmonte and Brinecove, trying down-facing and oblique cameras at three heights. **Inspect its captures:** reject cameras inside terrain/crowns or without enough visible trees, and adjust/replay explicit camera files as needed. Rank original GPU cost and frame p95; report poor results as well as good ones. The scout itself only records baselines.

The paired driver checks compiled identity, readiness, saved/effective settings and real-time clocks; captures the scene; records GPU/frame means and tails; warms both modes; and restores settings/camera afterward. Results go to `build/yorimichi/foliage_performance/`. Ensure no display/frame cap masks gains. Use longer intervals when slow views yield too few frames; do not discard them because they are slow. Record actual resolution and internal scale, hardware, renderer, revision and pass order. Inspect GPU event breakdowns to distinguish shadows, base/depth passes and other costs.

### Momiji Lake to Hidamari

Two repeatable cameras follow the Woodland–Hidamari cruise corridor at approximately
the authored 155 m height, looking back toward Momiji Lake:

```sh
uv run python games/yorimichi/scenarios/foliage_performance.py --port 8841 --take zeppelin_lake_abba --views zeppelin_lake_early zeppelin_lake_crossing --seconds 10 --settle 8
```

These are fixed scenery cameras. For the actual ride, the existing native
`-benchmarkview=zeppelin` diagnostic boards at Woodland and looks back over the
lake during the flight to Hidamari. Its CSV records player/camera position and
real-time frame/GPU timings. Run repeated original/optimized flights with the same
settings and duration, and verify the recorded route before calling them a moving
comparison. Keep screenshots outside the measured interval; use the fixed cameras
above for exact image matching.

## Remaining acceptance checks

1. Complete normal production preparation and verify every current foliage source, package and runtime registration. Exercise final-head functional/native tests and hosted CI.
2. Inspect original/optimized ground, canopy, village/city, treehouse and dense aerial views, including a moving pass. Check silhouette, color, leaf detail, clearings, shadow continuity, distance/LOD transitions and camera occlusion behavior.
3. Use the actual settings menu: cancel the disable warning; confirm disable and observe original rendering; re-enable; restart and verify persistence. Check legacy city-tree preference combinations, collision and gameplay in both foliage modes. The console toggle is temporary and does not test persistence.
4. Measure the slow real-game aerial views using paired real-time frame/GPU evidence. **No order-of-magnitude or visual-equivalence claim is supported yet.** If results remain modest or images degrade, change the representation/policy and remeasure before calling this finished.
5. Keep the PR draft until these checks pass. Request the required paid review with `r? cc` when ready, obtain independent board approval, verify final-head CI/lint/contracts, and follow the repository merge rules. No merge/release was performed for this handoff.
