# Modern incremental cook experiment

`atelier build GAME unreal.cook --cook-mode modern-incremental` is an explicit UE 5.8 experiment.
Default package flags, command representation and fingerprints remain unchanged. This implementation has
no measured speedup or native parity acceptance yet; production defaults remain unchanged.

The candidate forwards only `-cookincremental -Cook.DependencyTracking=1` through UAT's
`AdditionalCookerOptions`. The full control forwards `-fullcook -Cook.DependencyTracking=1`.
It never passes UAT `-iterate` (which also changes deployment), reduces `-cookall`, changes staging/package
scope, skips target compilation, increases the existing three UBT workers, or restores native cooked bytes.
The existing guarded compile lifecycle owns UAT and its descendants.

Mode is part of package command identity and survives recipe reloads, including cook-source certification.
Only package commands change; source generation/import commands do not. With an experimental mode,
`--force` repeats package steps only, keeping current prerequisites current. It requires a short
`--cook-reason`; this measurement label is retained outside the fingerprint. Ordinary `--force` keeps its
existing behavior. Plans use the same force rule. `--touch` cannot certify an experimental cook.

## First controlled sandbox run

Use one owned checkout after source review and an agreed native turn. Keep that checkout for all samples.
Normal sandbox builds do not select the explicit cook experiment. Do not run these commands while another
owner holds the machine, and do not clone or delete Saved/Zen state to manufacture a warm result.

```sh
# Read-only: inspect editor compile, level/import and cook prerequisites.
uv run atelier build sandbox unreal.cook --cook-mode modern-full --plan --explain

# First full control: builds missing editor/game targets and the level, then cooks all discovered content.
uv run atelier build sandbox unreal.cook --cook-mode modern-full --force --cook-reason 'initial full baseline'

# Prime the modern state; an initial settings-wide invalidation is a legitimate full result.
uv run atelier build sandbox unreal.cook --cook-mode modern-incremental --force --cook-reason 'incremental prime'

# Two unchanged same-checkout observations; current import/compile prerequisites are not forced.
uv run atelier build sandbox unreal.cook --cook-mode modern-incremental --force --cook-reason 'unchanged control 1'
uv run atelier build sandbox unreal.cook --cook-mode modern-incremental --force --cook-reason 'unchanged control 2'
uv run atelier build sandbox unreal.cook --timings
```

First-run prerequisites are the normal `unreal.compile` editor target and `unreal.level` generation/import;
UAT also builds the game target. A first game-target compile is not cooker runtime. Retain its action count and
actual phase times separately. UAT's existing command limit is four hours; editor/import prerequisites retain
their normal existing guards and limits. No first-run duration has been measured for this experiment.

The observer consumes at most 256 KiB per poll, bounds total logs to 128 MiB and line size to 16 KiB, and
verifies the observed byte stream once at completion. It runs after ordinary guard health checks. Positive
modern dependency tracking (which requires the actual Zen writer in the inspected UE 5.8 source) and one
completed cook are mandatory. Legacy fallback, disabled tracking, unsupported mode decisions, malformed,
repeated, changed or truncated observations refuse before the following cook-certification command/stamp.
A legitimate global/artifact-settings full invalidation is reported as **full**, without a reuse claim.
Missing counters remain unknown; zero skips is recorded as zero. Native parity is never inferred from skips.

Evidence is under `build/sandbox/logs/unreal.cook.guard/`: `stdout.log`, normal guard receipts and
`cook-observation.json`. It includes requested/effective mode, invalidation category, cooked/skipped counts,
cooker-session time and UAT build/cook/stage/package/archive/total durations when uniquely observed.
Stage already includes pak/IoStore subprocesses; nested times must not be added again. Admission and child
lifetime remain separate launcher diagnostics. Existing Yorimichi cook certification is retained; the
experimental mode enters its source fingerprint too.

The sandbox publishes `build/sandbox/package/cook.json` only after the current observation, unchanged source
and complete archived app inventory agree. Actual executable and IoStore containers are required. Each result
is also retained in `build/sandbox/cook-experiments/`, with `native_parity: false`. The next run replaces its
archive; preserve completed baseline/candidate apps as independent evidence copies before comparison. Such
copies are for validation only and never seed project Content, Saved, Intermediate or Zen state.

## Native acceptance matrix — all still unrun

Record the checkout/revision, dirty patch, engine/SDK identity, run reason, raw logs and retained receipt for
each row. After a changed case, compare its incremental result with a fresh **full cook of the same changed
inputs**. Keep the previous receipt/app for inspection before the next run.

| Case | Required evidence |
| --- | --- |
| Initial full control | Actual modern dependencies, explicit full decision, complete archive/load |
| Two unchanged controls | Actual incremental decision; cooked/skipped counts; repeated phase times |
| Local asset edit | Changed asset invalidates; unaffected assets remain semantically equal |
| Referenced config edit | Effective config changes appear in cooked/runtime behavior |
| Serialization/header edit | UBT rebuild and affected cooked assets invalidate; no legacy ignore-exe behavior |
| External/pre-save generator input | Generated cooked bytes/settings update; hidden dependency misses block acceptance |
| Package rename/deletion | Old package absent from registry/container; references/load resolve correctly |
| Missing/corrupt previous state | Full regeneration or safe refusal, never stale successful reuse |
| Clean versus incremental parity | Registry/package/container semantics and native packaged map/asset loading agree |

Archive byte hashes retain evidence but do not prove semantic parity when native metadata is nondeterministic.
Load both packaged apps under normal owned guards; compare the sandbox map, expected actors/assets and the
changed configuration/serialization cases. No default enablement follows until this matrix and repeated
end-to-end timings demonstrate correctness and a real improvement. Compiler caching and runtime-root
reduction remain separate work; neither is silently enabled here.
