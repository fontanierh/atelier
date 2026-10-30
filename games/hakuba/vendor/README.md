# Patched dependencies

`bevy_pbr/` is the Bevy 0.20.0 PBR crate with project-local opt-in forward color-and-motion output. Cargo selects it with
`[patch.crates-io]`; the rest of Bevy remains pinned to the registry versions in the lockfile. No Cargo cache edits
or external checkout paths are required. `bevy_pbr/PROVENANCE.json` records the source release, archive checksum,
upstream commit and original file hashes. The original MIT and Apache-2.0 licenses are retained.

The patch is opt-in by view. It supplies previous positions, motion outputs and the matching view bindings;
`crates/rendering/` owns comparison, publication to TAA, and camera geometry-prepass elision. `compare` keeps the
original displayed TAA, while `publish` and `single` explicitly test main-pass temporal inputs. The ordinary
renderer stays unchanged. `PERFORMANCE.md` records measured gains and the remaining temporal-quality and frame-rate
acceptance limits; successful motion transfer is not by itself proof of equivalent temporal edges.

`bevy_pbr/src/` is the upstream rendering library, including shader modules and feature-gated rendering paths.
Keep upstream files together so its declared features and shader imports remain complete. Changes belong in this
copy, not the registry. Compare updates against the recorded upstream release and review local changes before
upgrading Bevy; the patch is not an independently versioned rendering engine.
