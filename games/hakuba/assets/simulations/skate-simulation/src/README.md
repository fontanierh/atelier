# Simulation source data

`motion/rig.json` defines the rig, its parent/mirror indices and bank-specific reference poses.
`motion/metadata/bank-0.json` and `bank-1.json` keep source identities, offsets, timing, attributes and blend/selection trees.
`motion/clips/<bank>/<name>.json` keeps every bone's weight and ten component tracks. A constant track is one number; other tracks have one number per frame.
`runtime/` holds settings and their reflected field types, three graph trees, camera shots/shakes, gesture patterns and physical skeletons.
`package-manifest.json` names every encoded payload with its size and SHA-256. `bundle.json` pins that manifest, format versions, source identity and aggregate counts.

`cargo export assets/simulations/skate-simulation` reads only these sources and writes the indexed `.skatepack` beside this folder.
The Rust encoder rounds JSON decimal numbers through f64 to f32, preserves negative zero and accepts exact lowercase `0x` float words where the source uses them.
The export must match every payload checksum and all counts in the descriptor. Update the source manifest deliberately if changing a payload.

## Provenance and distribution

These sources were migrated unchanged from the repository's current readable simulation data at revision `aaa1fdd28251c30c8c89cdfc6d2ec5c371e46991`.
The source chain identifies EA Skate 3 animation, settings, graph, camera, gesture and skeleton data. Bank metadata retains the original bank names, byte counts and SHA-256 identities.
The historical data notice described its inclusion for the owner's personal use. Reformatting the data and supplying integrity hashes do not grant a new data license.
Recovered Rust code licensing does not license this data. Confirm the intended distribution scope with the owner before publishing this asset in a public/browser release.
