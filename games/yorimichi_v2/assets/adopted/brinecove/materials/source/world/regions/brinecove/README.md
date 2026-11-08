# Brinecove

A pirate port in the western reach of Yorimichi: a horseshoe cove cut into a jungle headland, with a stone quay,
three timber piers, moored galleons and a shipyard, a market square on the water, a town climbing two cliff terraces,
a watchtower on the crest, a lighthouse on the west headland and a two-tier waterfall in the east cliff. Booty Bay is
the broad reference for the vertical, ramshackle port; the painting language, palette and low-poly construction are
Yorimichi's. `DESIGN.md` records the plan, dimensions, district names and art-direction rules.

## Where it sits

The cove is the eighth atlas region, **Brinecove Reach**, on the south coast west of Momiji Coast, where nothing
else stood. World metres follow `docs/WORLD_MAP.md`: world = local + `region.ORIGIN` (-1500, -120, 0), with no
rotation. The cove opens south onto open sea; the quay line (local y 60) sits on the old coastline.

| Brinecove (local) | World |
| --- | --- |
| Region ground, `region.OUTER` | x -2526.3..-707.4, y -1044.2..572.6 (FarHills knots 10..37, 32..56) |
| Layout ground, `region.INNER` | x -2400..-800, y -900..480 |
| Market square (0, 160) | (-1500, 40) |
| Lighthouse (-618, -38) | (-2118, -158) |
| Waterfall gorge (459..700, 30) | (-1041..-800, -90) |
| Map stop `brinecove_quay` | (-1500, -45) |

## How it joins the world

- **Far hills.** `farhills_surface.owns_fine_ground` hides the FarHills cells inside `region.OUTER_WORLD` when the
  city is built, exactly as it does for Hidamari. The rectangle lies on the 96-knot axis, so the hole is the
  rectangle itself.
- **Ground** (`ground.py`). The layout's ground on a 4 m grid inside `INNER`, eased across the collar into the
  far hills' rim heights, and closed by a zipper strip onto the FarHills final product's own hole vertices
  (`region.rim_from_mesh`): the two meshes share every vertex on their seam, with no T-junction on the far-hills
  side. `tests/test_brinecove_ground.py` checks the seam and the hidden footprint.
- **Trees and boulders.** `ABelmonteRegion::Clear` removes the island's trees, bushes and grass inside
  `clearance_m`, and the coastal dressing's `SW_Boulder` rocks along the old shore (`clear_prefixes`).
- **Map.** `world/map/build_map.py` samples `plan.heights` and draws `plan.draw` (streets, piers, roofs, ships, the
  river); the atlas painting `world/map/atlas/brinecove.png` is painted from that plan.

## Build

`world.brinecove` (`build.py`, Blender) writes `build/yorimichi/brinecove`: the ground and nine modules split into
256 m tiles, each tile split again into a solid part (complex collision) and a soft part (foliage cards, water,
spray: no collision), the processed hero models once each with their placements, and the flora prototypes once
each with their instances. `runtime.json` uses the Belmonte runtime schema, so `ABelmonteRegion::Spawn` places it
(tag `brinecove`). `unreal.brinecove` (`unreal/Scripts/import_brinecove.py`) imports it into `/Game/Brinecove` with
three parents sharing the island haze: opaque, two-sided masked (leaves, fronds, foam lace and the scrolling
waterfall curtain) and translucent spray. Foliage prototypes get generated LODs.

The ground is one blended `terrain` material: the shader picks sand, meadow, forest floor and rock per pixel from
height, slope and noise, on smoothed vertex normals (the collar's zipper fans take the eased ground's analytic
normal, so they do not band). Cells under paving are clamped below it, seabed never paints above the sea, and the
sea cliff and notch flanks around the falls are rock only, so no meadow facet shows through the cliff rock. The
waterfall curtain is placed against the built ground (`falls.mesh_height`: the 4 m grid with its jittered cliff
corners), not the analytic cliff, which it would otherwise cut through. Groundcover grows in single-family clumps on
a jittered grid; open slopes seen from the beach get clumps of larger ferns and broadleaf around low shrubs, culled
at 90 m instead of 50 m. Retaining walls that stand proud of the hillside get boulders and shrubs along their feet.

The sources are committed under `assets/brinecove`: palette-tinted Sunburst surface maps (`textures/`), the
procedural water atlas, the processed TRELLIS and Tripo hero models with provenance (`models/`), and the hero prop
reference paintings (`references/props/`).

## Review scene

`review_build.py` builds the same modules into one Blender scene, Eevee review renders and a three.js viewer in
`build/yorimichi/brinecove-review`. The game never reads it. Run it under the normal guard:

```sh
uv run python -m atelier.safety.guarded --report build/yorimichi/brinecove-review/guard --purpose "Brinecove review" \
  --timeout 3600 -- /usr/local/bin/blender -b --factory-startup --threads 3 \
  --python games/yorimichi/world/regions/brinecove/review_build.py -- --stage all
```

`review_sheets.py` pairs each render with its Sunburst concept. `references/` holds the paid-call scripts, each
recording through `atelier.ai.ledger`. `generate.py` paints the concepts. `bridge.py` edits a render toward its
concept as a middle-ground target. Both the waterfall and cliff rework follow the `07-waterfall-bridge` and
`13-cliff-face` targets. `textures.py` paints and tints the surface set; `redesign.py` paints the 2026-10-19 playtest-note concepts and the
surfaces that replaced their defects (the natural weathered rock, the softened sand). `props.py` paints hero prop references,
and `galleon_tripo.py` paints the galleon reference views. `water_atlas.py` and `leaf_atlas.py` draw the water and
leaf atlases procedurally. `process_assets.py` and `galleon_hull.py` reduce the neural models into
`assets/brinecove/models`.
