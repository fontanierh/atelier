# Hidamari city

Eastern city extension at the approved 900 × 600 m footprint. Build from the existing generated forest world:

```sh
japan/run.sh hidamari
```

This generates `out/hidamari/city.json`, 55 modular FBX assets, collision surfaces and an import report, rebuilds the native module, and imports the city plus a terrain backdrop with space for the eastern extension. The original `world.json`, heightfield and far-hill source array remain unchanged. The runtime merges the optional city sidecar before creating instanced mesh groups. Full `assets` / `setup` rebuilds also include the city. Generated FBX and Unreal assets follow the repository's existing ignored-output convention; rebuild them after a fresh checkout.

Current content: 247 shop/residential placements, including 26 narrow arcade bays and six additional shop identities, clock hall and fountain square, station, two temples and local shrine, covered shopping arcade, two fish-market shelters, 12 fishing boats, lighthouse and breakwater, pond park with bridge and pavilions, playground, canal banks, street lamps, flower beds, benches, street trees and 35 cosmetic residents in independently proximity-gated groups. Shop signs combine names and pictorial marks. Interiors and functional fishing/commerce/train travel are not implemented.

Coordinates, scene references and the approved planning envelope: `../docs/hidamari/`.

Completed captures and measured results: [implementation review](review/README.md).

Review captures:

```sh
python3 japan/hidamari/review.py SESSION
```

Uses the existing trailer capture system and live Unreal scene; no image postprocessing. Optional trailer field `validate_hidamari: true` runs the live collision audit and writes `hidamari-physics.json`. `-reviewroute=hidamari` selects the actual city arrival and central street for the existing movement and benchmark helpers. Capture playback at fixed 60 Hz is not frame-rate evidence; use `benchmark.py` for real-time measurements.

## Integration and iteration

The eastern road endpoint is read from the actual generated road. Streets and their underlying terrain share one height profile, including level intersections. The original distant terrain is smoothly lowered around the city, and backdrop trees are replaced at the corresponding surface heights. The southwest branch can continue to own its separate layout; it must preserve the city sidecar merge and terrain hook when combining loaders.

The harbor has protected quay/pier edges. Falling into the harbor, canal or pond returns the player to their last grounded city position. Inland water is a separate collision-free mesh; banks and bridges retain collision. Boats are decorative and do not have collision. Existing running, skating, ollies and mini-mega code paths are retained.

For a targeted art iteration, set `HIDAMARI_ASSETS` to comma-separated mesh names for both the Blender builder and Unreal importer. Set `HIDAMARI_TERRAIN=1` on the importer when also replacing the base terrain FBX. A layout/height change may require rebuilding `HD_Terrain`, `HD_Streets` and any ground-anchored public spaces; always rerun the collision audit.

```sh
python3 japan/hidamari/review.py SESSION --shots square --audit
python3 japan/hidamari/review.py FUNCTIONAL_SESSION --shots '' --checks --wait 1200
python3 japan/benchmark.py CITY_PERF --view village_skate --route hidamari --road-index 258 --seconds 30 --hide-hud
python3 japan/tools/render_map.py --proposal japan/docs/hidamari/location.json --built-city japan/out/hidamari/city.json --out japan/docs/hidamari/current-map.png
```

Use a NumPy/Pillow-enabled Python for the generation and map tools. Do not overlap performance captures with Blender or another Unreal session. The benchmark rejects contaminated runs.

The live audit samples every street, sweeps a character capsule along three lateral tracks, checks the park bridge at half-metre intervals, and rejects collision on water. Functional captures assert that water recovery returns the player to shore, both bridges keep the player grounded, default running reaches travel speed, and a moving skateboard ollie takes off and lands. These tests exercise the real native scene and character movement; they are not offline geometry-only checks.

The first environment uses repeated facade modules and a broad street grid. The footprint includes water and public space, not 900 × 600 m of continuous buildings. Additional hero interiors, harbor work animations, shop interactions and fishing are separate future milestones.

Reference-led arcade pass, captures, materials and independent differences review: [arcade review](review/arcade/README.md).

Latest arcade: [polish, comparison and demo](review/arcade-polish/README.md).

Reference-led clock square rebuild, visual iterations and movement checks: [plaza review](review/plaza/README.md).

Reference-led harbor kit, before/after stills, independent differences and runtime checks: [harbor review](review/harbor/README.md).

Combined checkout checks: [integration review](review/integration/README.md). Final arcade, square and harbor film: [Hidamari demo](review/demo/README.md).
