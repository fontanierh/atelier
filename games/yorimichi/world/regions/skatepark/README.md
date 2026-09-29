# Skate pier and trick skateboard

A concrete street plaza with transitions on a pier over the sea, south of the spawn road,
reached by a skateable concrete path, plus the modern trick board the native skate system
rides (docs/SKATE.md has the controls, physics and contracts). Everything is generated here:
geometry, faded paint, baked ambient occlusion in vertex colours, `park.json` and the checks.

## Files

| File | What it is |
| --- | --- |
| `layout.py` | every dimension (pure numpy): site, feature profiles, grid lines, the path route and profile, rails |
| `features.py` | park geometry (pier, features, pilings, path, floor paint) as `geom.MeshData` |
| `board.py` | deck, truck and wheel |
| `geom.py` | mesh builder, painterly shading, AO bake (ray cast), FBX export |
| `build.py` | builds all, runs the checks, exports, writes `park.json` and the report |
| `review.py` | EEVEE review renders (`build.py -- --review`) |
| `park.json` | the gameplay contract read by `ASkatePark` (committed) |

Outputs (disposable, `japan/out/skatepark/`): `assets/*.fbx` (park), `board/*.fbx`,
`SkatePark.blend`, `build-report.json` (all checks and numbers), `review/*.png`,
`import-report.json` (written by the Unreal import).

## Rebuild

```sh
blender -b --threads 6 --python-exit-code 1 --python japan/skatepark/build.py            # ~10 s
blender -b --threads 6 --python-exit-code 1 --python japan/skatepark/build.py -- --review # + renders
japan/run.sh skatepark     # build, compile the module, import (Unreal closed)
```

`Scripts/import_skatepark.py` imports the park meshes to `/Game/SkatePark/` and the board
to `/Game/SkatePark/Board/` with `/Game/Japan/Materials/M_Village` (loaded, not rebuilt),
complex-as-simple collision on blocking park meshes, none on the paint and the board. It
refuses stale exports (hashes in the build report) and checks units and axes on every mesh.
The terrain and `world.json` are not touched: the game removes trees, bushes, grass and
litter inside `park.json`'s clearance polygons.

## Frames

Park-local metres, Blender axes (x east, y north, z up), origin on the deck top at the
platform centre, world origin `(-110, -195, 1.80)`, yaw 0. Unreal: world metres
`(x, y, z)` land at `(100x, -100y, 100z)` cm, the same route as the mega and the village
(FBX forward -Y, up Z, legacy importer). Spawn one actor at the origin for every park mesh.
`yaw_deg` values are counter-clockwise from +x (Unreal yaw = -yaw_deg).

## Site

- Pier deck x in [-150, -70], y in [-222, -168] world, top at z = 1.80 (80 x 54 m). The
  beach under the north edge is 0.1-1.0 m, the sea bed falls to -12 m by the south edge.
  70 piles (0.6 m) on an 8 m grid into the sea bed, pile caps, 0.7 m edge beam, perimeter
  railing 1.1 m (posts every 2 m, blocks, not grindable), six lamp posts, 5 m deck joints.
- Path: 111 m, 4 m wide, from the road's south edge at (-155.0, -83.6, 9.31) through the
  guardrail gap on the west side of the house, down to the pier's north edge at
  (-104, -168, 1.80). Straights and arcs (radii 20, 10, 20, 25 m), grade <= 9 % on the
  centre line and <= 9.7 % on both edges, at least 5 cm above the upper envelope of both
  terrain triangulations everywhere, level first metre off the road and level last 4 m
  onto the deck. Its end ring shares the deck's edge vertices (no lip). Skirts run 0.45 m
  below the ground on both sides; it stands on a retaining wall up to ~1.5 m where it
  leaves the house's level pad, and ~1 m on the pier abutment.

## Features (park-local metres)

| Feature | Where | Dimensions |
| --- | --- | --- |
| Big quarter pipe | coping x = 35, y -6..6, faces west | 1.8 m: transition radius 2.2 m at the floor tightening to 1.34 m, vertical at 1.65 m, 0.15 m of vert; 5 cm round coping 1 cm proud; 2 m deck with guard rail |
| Mini quarter pipe | coping x = -35, y -5..5, faces east | 1.0 m, radius 1.5 m (70.5 deg at the lip), coping, 2 m deck, guard rail |
| Kicker | x -11.5..-9.5, y 0.1..1.7 | 0.5 m over 2 m (radius 4.25 m, 28 deg lip), steel lip, 1 m before the funbox |
| Funbox | x -8.74..2.74, y -1.75..1.75 | 0.6 m, 2.5 m banks (13.5 deg, filleted), 5.7 m flat top, steel ledges both sides |
| Upper deck | x -30..-18, y -26.85..-18.85 | 1.2 m platform, 7.4 m bank (10.5 deg) from the north, own railing on the sea sides |
| Stairs | x -18..-16.25, y -25..-20, down east | 6 risers of 0.20 m, treads 0.35 m; red 5 cm handrail at y -22.5, 0.85 m over the nosings |
| Hubba | y -25.8..-25.0 | 0.35 m over the nosing line, 1 m flat on the platform, steel edges |
| Flat bars | y -4.5 x 10..16 (red), y 4.5 x 10.5..15.5 (yellow) | 0.35 m x 6 m and 0.25 m x 5 m, 5 cm round |
| Manual pad | x 16..20, y 11.75..14.25 | 0.18 m, steel edged all round |
| Benches | y 22.25..22.75, x -25..-20, -14..-9, 20..25 | 0.45 m, steel on both long edges |
| South bank | x 4..24, top edge y -25.85 | 1.5 m, 35 deg with a 2 m concave toe, steel top edge (listed as coping) |
| Floor paint | sun disc at (-25, 12), three wave strokes | separate non-blocking mesh 4 mm above the deck |

Lines: the entrance (x = 6) runs straight south to the south bank; the mini quarter feeds
the kicker, funbox and the flat bars into the big quarter; the path entrance line to the
upper-deck bank, across the platform and down the stairs, hubba or rail, out east along the
south bank. Every ramp starts tangent to the floor on a floor grid line (shared vertices),
transitions step at most 2.5 deg per segment, and complex collision is the render mesh.

## park.json

`origin`, `yaw_deg`, `deck`, `meshes` (name, asset, blocks), `board` (asset paths and
offsets), `rails` (id, kind rail|ledge|coping|curb, points along the top contact line in
park-local metres, `radius` for round rails and coping, `side` for ledges, curbs and coping),
`spawns.park` (park-local) and `spawns.path_top` (world), `clearance` (world polygons: the
pier + 4 m and the path corridor +-5 m), `surfaces`, `features` (footprints). The build
checks every rail point against the modelled surface (worst 0.01 mm).

## Board

Deck 80 x 20.5 cm popsicle, kicks rising 4.5 cm over the last 13 cm (9.6 cm bend then
22 deg), 0.9 cm concave, 1.2 cm thick, 5-ply maple edge, black grip, off-white bottom with
a red sun and indigo waves. Trucks: kingpin pivot at (+-18, 0, -1.2), axle 5.15 cm below
(-6.35 on the deck), silver hanger, dark baseplate, amber bushings; the mesh is the front
truck (kingpin toward -X), the back truck is it turned 180 deg. Wheels: 2.65 cm radius,
3.2 cm wide, cream. About 2.7k triangles assembled. Unreal axes: nose +X, toe side +Y
(Blender -Y). With the contract's axle height and wheel radius the wheels touch at
-9.00 cm, 0.5 mm above the -9.05 ground stated in docs/SKATE.md.
