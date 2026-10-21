# Incremental builds

Run `atelier build GAME [TASK ...]`. It preserves current results, checks per-task caches before native work,
and stops unknown or expensive misses before they become an accidental full rebuild.

[Build checkpoints](BUILD_CHECKPOINTS.md) is the single operational guide for local and private GitHub reuse,
release retention, configuration and recovery. Lookup uses actual task inputs and tools, across source revisions.

Inspect decisions with `atelier build GAME --plan --explain`; use `--verify` when output corruption is suspected.
Keep stamps, generated Content, Binaries, Intermediate, the installed engine and DDC. Never routinely force,
touch stamps, clear caches or regenerate the world for a code-only edit. All native work retains normal guards.

[Build recipes](BUILD_RECIPES.md) explains complete inputs, named products, reference/read edges, spatial queries,
and bounded process reuse. Complete output ownership is required for individual task caching; representative
legacy outputs cannot prove it. The checkpoint guide documents current coverage and compiler/cook limits.
[World build practices](WORLD_BUILD_PRACTICES.md) explains how to narrow dependency and ownership boundaries.

[Portable artifact formats](ARTIFACT_POOL.md) documents optional source redistribution tools and formats.
They are not additional setup steps for ordinary builds or playtests.
