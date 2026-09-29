# Migration from the prototype repository

Yorimichi was built from 4 to 28 September 2026 in a private prototype repository (`japan/` inside a larger
experiments repo). This file tracks the move into Atelier. The prototype stays as a read-only archive.

## Definition of done

1. Everything live in the prototype is here, in the Atelier layout: code, sources, build scripts, tests, docs.
2. No secrets, personal data or third-party files that can't be redistributed.
3. A fresh clone builds and plays Yorimichi with `atelier fetch`, `atelier build` and `atelier play`, and the
   generated world, characters and sounds match the prototype's.
4. The scenario tests (skate, combat) pass against the fresh build.

## Stages

**Stage 1: move and bootstrap.** Move every live piece into the new layout with the game behaving exactly as before:
same C++ (renamed module), same generators, same import scripts, with every path going through `atelier.paths` and
the game reading its runtime data from `Content/Data/` instead of the prototype's loose `japan/out/` files.

**Stage 2: platform plugins.** Pull the engine code into platform plugins behind the activity interface, one plugin
per commit, each verified with scenario tests: FX and audio, animation nodes, live bridge and scenarios, streaming and
touch controls, the player shell and on-foot activity, skate, sail and ride, combat.

## Status

| Piece | Prototype | Here | State |
|---|---|---|---|
| Skeleton, conventions | — | `README.md`, `ARCHITECTURE.md`, `platform/conventions/` | done |
