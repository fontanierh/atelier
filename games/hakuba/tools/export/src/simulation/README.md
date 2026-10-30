# Simulation exporter

`mod.rs` loads an asset's JSON source tree, checks its supplied integrity descriptor and writes one indexed archive.
`motion.rs` writes the rig, compact animation clips and both metadata banks.
`runtime.rs` writes reflected settings, graph arenas, camera, gestures and physical skeletons.
The shared byte archive and bounds-checked reader live in `schemas/skate`.
No conversion tool or original bank archive is needed to export.
