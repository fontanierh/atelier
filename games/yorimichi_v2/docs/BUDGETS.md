# Yorimichi V2 measured slice budgets

These are historical measurements of the November 7 slice, not current whole-game timings or a gate on the
full port. Reuse this evidence; run a new focused measurement only for a material changed behavior or unresolved
performance issue. Current production/package progress is in [INVENTORY.md](INVENTORY.md) and
[PACKAGE.md](PACKAGE.md).

Measured on 2026-11-07 on the reference Mac (Apple M1 Max) in the compiled asset workspace, with
`tools/test/budgets.py`. Each operation had one declared warm-up, then five timed runs. The resource-queue wait
was recorded apart from the time and was 0 s in every run. The writing runs were done under real claims (region
`w01-start` for the actor, `prop/lantern` for the mesh), then reset; no V2 lock was left. Every receipt
(`build/yorimichi_v2/budgets/OPERATION.json`) names its checkout revision: 8bc1d22051, and 4295fa7aae for the mesh.
Neither differs from main in C++, configuration or content.

| Operation | Target | Median | Slowest | What one run is |
|---|---|---|---|---|
| No-change content check | ≤ 10 s median | 3.5 s | 3.5 s | `check.py` on a warm local index (run separately, 6 runs) |
| One actor placement | ≤ 30 s median, ≤ 60 s slowest | 17.1 s | 17.3 s | `editor.run` with `move_actor.py`: open the slice, move the w01-start ginkgo 1 cm (alternately +x and -x), save only its package |
| Small prop mesh update | ≤ 3 min median, ≤ 6 min slowest | 23.9 s | 24.1 s | the lantern's FBX switched between its two shapes, then the claimed targeted import. Every run imported; none was skipped as unchanged |
| Small C++ implementation edit | ≤ 3 min median, ≤ 6 min slowest | 35.0 s | 40.1 s | a numbered comment appended to `YorimichiLive.cpp`, `unreal.compile`, then the slice played until Cairo walks on the ground. UnrealBuildTool's log shows `Compile [Apple] YorimichiLive.cpp` in every run |
| Warm slice opening | ≤ 90 s median | 23.0 s | 23.3 s | `atelier play yorimichi_v2 --profile slice` from launch until the live bridge answers and Cairo walks on the ground; then a quit through the bridge |

All five pass. The warm-ups were slower (placement 47.8 s, C++ 39.3 s, opening 24.9 s). After the six alternating
moves, the actor's package was byte-identical to main. After the C++ series, `YorimichiLive.cpp` was restored and
the workspace was clean.

These targets are for warm, everyday work in a compiled workspace. The cold costs are separate. The editor compile
of a new workspace took 17–32 minutes (COLLABORATION_TESTS "C01 and C04 native run"). The slice cook took 1062 s
and needs `--cook-memory-gib 20` (PARITY "Packaged slice").

## What the first attempts got wrong

- **The placement claim lacked the actor's companion locks.** The editor step refused every run in 3 s, before
  Unreal started, because `.uexp/.ubulk/.uptnl` were not locked. With them locked, every run passed.
- **The play runner read the game's output wrongly.** A non-blocking read raised on the text pipe, so no session was
  found and no quit was sent. The 120 s cleanup boundary stopped the series as designed, and the game was quit
  through its bridge by hand. The runner now reads the output on a thread and takes the session from the
  live-session records.
- **The compile proof looked in the wrong place.** UnrealBuildTool's per-file actions go to the compile step's log,
  not to the build's output. So five real compiles were first counted as failures, not as passes. The proof now
  reads `build/yorimichi_v2/logs/unreal.compile.log`. It counts a compile only when this run's build ran the step
  (not `up to date`) and wrote that log after the run began; each run keeps its own copy. The review found that an
  older log under an `up to date` build would otherwise pass. In the six C++ runs above the build ran the step each
  time (six `unreal.compile done in` lines). Only the last run's log was kept, and it holds the rebuilt file.

## Recording a current performance run

Use the existing guarded play/capture tools and the run already needed for the changed behavior. This does not
require repeating the historical five-run slice campaign for routine changes.

- Keep each attempt in a new output directory or under a unique tag. A retry must preserve prior captures,
  stdout and receipts, including failed attempts. Write a failure summary after cleanup as well as a success summary.
- Record the source revision, renderer and saved preferences, requested resolution, actual viewport/capture size,
  memory ceiling and guard paths. A logical Retina window size is not proof of the render-target size.
- Separate capacity queue time from admitted startup and playable-world readiness. A live-session registry entry
  can exist while waiting for admission; it does not prove that Unreal started or the world became playable.
  A readiness timeout spent in that queue is not a measured game startup failure.
- Preserve both `memory-health.json` and `memory-health-tree.json` when the guard emits them. The first describes
  the primary process; the aggregate tree can exceed its limit even when the primary peak is below that limit.
  Report the guard's termination reason and cleanup result, not just one peak number.
- A memory-limit termination before gameplay readiness is an incomplete attempt, not an accepted performance
  result. A source change intended to reduce memory is not a measured reduction until a comparable run completes.

The existing `tools/test/budgets.py` separates observed queue wait from its operation timing. Custom capture
callers need the same distinction and must preserve the existing admission, deadlines and owned-process cleanup.
