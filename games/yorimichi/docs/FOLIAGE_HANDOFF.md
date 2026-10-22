# Foliage validation handoff

The implementation is tracked in [PR493](https://github.com/fontanierh/atelier/pull/493).
Use its current source review, CI and native evidence; earlier isolated proxy measurements do not
establish a full-game speedup or approve the current representation.

## Current behavior

The normal build classifies dense and embedded vegetation, verifies saved source/material geometry,
and publishes prepared resident assets. Complete small `FoliageAuthored_` props under 12,288 triangles
remain ordinary props. Prepared leaves retain source texture/opacity/wind/interaction wrappers and
complete authored LOD chains, including far impostors and their actual screen thresholds. A source
without lower authored levels uses native leaf-only reduction. Rigid scenery is retained once;
prepared trees use simple trunk shapes and bushes stay passable.

The foliage preference is selected before loading scenery. Optimized mode opens prepared assets only.
Mode switches release inactive meshes before loading the selected replacement. Native readiness and
runtime audits reject incomplete registration. Source geometry, packages, placements and authored
trunk collision enablement remain unchanged. See [FOLIAGE_SYSTEM.md](FOLIAGE_SYSTEM.md) for authoring
roles, source discovery, collision and memory ownership.

## Build and native checks

Verify the persistent board listener and machine capacity ledger, then use the ordinary workflow from
a stopped checkout. Preserve generated Content, Binaries, successful stamps and caches.

```sh
uv sync
uv run atelier build yorimichi --plan --explain
uv run atelier build yorimichi
```

A deliberate geometry change may require an explicit `--rebuild-reason` explaining why regeneration is
necessary. A cache miss runs the owning task; never copy stamps or weaken current validation.

Both `unreal.foliage_system` and `unreal.foliage_residency` must finish before launch. Check their
reports under `build/yorimichi/`, published registries under `unreal/Content/Data/`, and actual current
native guard receipts. An earlier receipt or a partial output directory is not completion evidence.
The residency owner runs its own native fixtures before production sources, including complete
five-level chains, authored screens, far shape/UV preservation and exact empty distant levels.
`Yorimichi.Foliage` automation additionally covers registry, collision, bindings and toggling.

Preparation lives in the independent editor module `YorimichiFoliagePreparation`; raw imports retain
role certification in `YorimichiImport`. Each consumer binds its actual compiled module records.
Historical partial-unit hints require exact reviewed source/module/context proof and current native
source/package/geometry/material/settings validation before receiving success.

## Matched game comparison

Launch the normal fullscreen game using saved renderer/tree preferences and an owned loopback port.
Use a supported memory ceiling covering the measured session and retain both child and aggregate
receipts. Do not treat a raised ceiling as a memory improvement.

```sh
uv run atelier play yorimichi --profile fullscreen -- -liveport=8841
uv run python games/yorimichi/scenarios/foliage_performance.py --port 8841 --take matched_lake --views zeppelin_lake_early canopy --seconds 10 --settle 8
```

The comparison requires clean source, matching compiled code, actual gameplay readiness, a real
viewport, fixed resolution/settings and real-time clocks. It waits for each deferred switch and zero
inactive mesh residency, then records Off/On/On/Off frame/GPU samples. Screenshots and GPU breakdowns
stay outside measured intervals. PNG completion and the final preference restore must finish before
quitting. Quit test games promptly and retain normal guard cleanup evidence.

Inspect each camera before using it as evidence. The existing `forest_under` camera may lie inside a
leaf at some source revisions; that does not establish ordinary ground-level visual quality. Compare
valid village/ground, canopy and dense aerial views, plus a moving route where practical. Preserve
silhouette, leaf detail, clearings, shadows, interaction and collision. Record poor results and pass
drift as well as improvements; a display cap can hide frame-rate gains, so retain GPU times.

The optional `--aerial-scout` samples dense neighborhoods from actual placements. Its baseline ranking
is not a speedup measurement. Its `slow_views.json` can be replayed with `--camera-file` for exact
comparisons. The separate native zeppelin benchmark records the real flight route; validate the route
telemetry before calling it traversal evidence.

## Merge conditions

Keep the PR draft while native preparation, matched appearance or performance acceptance is incomplete.
Run focused tests for changed behavior, lint and contract checks. Require independent source approval,
the requested paid advisory review and green `Studio Python / macOS` on the exact final PR head.
Use `atelier merge PR --source CHECKOUT` to retain the completed source products. A failed or
memory-infeasible check must be identified honestly rather than labelled PASS.
