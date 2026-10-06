# Sunset Pier

A 170 × 132 m waterfront skate plaza: long street lines, a terraced stair court, a banked market plaza, a deep bowl,
a horseshoe mini and a separate mellow return. Its north entrance meets the existing coastal path; the enlarged
pier extends farther over the sea. Park-local metres are east +X, north +Y, up +Z, origin `(-110, -234, 1.8)`.

## Build and materials

```sh
uv run atelier build yorimichi world.skatepark unreal.skatepark
uv run atelier qa yorimichi skatepark
```

`world.skatepark_textures` finishes existing painted sources offline. It never makes a paid call. To author the
sources explicitly, `uv run python games/yorimichi/tools/pier_textures.py paint` records each GPT Image 2.5 Sunburst
`quality=high` submission with `atelier.ai.ledger`. An existing record is never submitted again.

The source images and exact prompts are in `assets/skatepark/textures/`: burnished concrete, sea-glass ceramic,
truck-worn steel, cedar and the original koi/wave wall. Cut stone comes from the Mega Park restyle. Finishing makes
periodic albedo detail, roughness and subtle normal maps in `build/yorimichi/skatepark/textures/`. Vertex colours
supply the final palette and baked AO; the detail albedo has a mean of .5 linear. Blender and Unreal both multiply
it by twice the linear vertex colour. Metal, glazed tile, timber and concrete have distinct material responses.

`world.skatepark` builds the FBXs, Blender scene, exported riding collision, build report and tracked `park.json`.
`unreal.skatepark` imports the meshes, maps and named material slots into `/Game/SkatePark`. The board retains its
existing mesh contract. `data.stage` copies `park.json` to runtime data. Generated exports, captures and reports
remain in the ignored build folder.

## Riding areas

| Area | Features and approach |
| --- | --- |
| North rail promenade | Three separate 18–20 m bars at y = 43: 36 cm round vermilion, 30 cm square sage, and 42 cm round. Wide approaches and exits serve both directions. |
| Manual promenade | Two 14 m pads at y = 53–56, 22 and 30 cm high, with a 9 m link. The entrance opens onto the broad promenade behind them. |
| Street court | 22 m approach decks for four and seven stairs. Gentler stair runs, handrails with 4 m lead-ins and 3 m exits, steel-edged hubbas and access/return banks. A smooth rise connects the two terraces. |
| Market plaza | A 20 m approach deck, low three stairs, rails and hubbas, with front and back banks. Nearby a 21 m, 16 cm curb and a 22 m crescent rail offer low street practice. |
| Central street | A 20 m low ledge, a 20 m higher stone ledge, a 14 m skate bench and a curved steel-edged wave ledge. A low kicker/landing connects the approach lanes. |
| Central wave | A 65 cm table with wide tapered shoulders for diagonal transfers and low-speed flow. |
| Sunset line | A low 14 m manual pad, a broad 75 cm hip, a bump-to-20 m bar and a wide mellow return. The southern pavilion and planted seats face this line. |
| Transitions | The horseshoe mini, deep rounded bowl, east return and a separate 1.6 m mellow quarter. Access banks reach the decks. |
| Promenade | Cedar seats and pavilion, rounded stone gardens, island maples and coastal pines, ornamental grasses, lamps and an original wave mural. Dressing stays outside riding approaches. |

## Geometry and runtime checks

The riding surfaces use their render triangles for collision. Rail contact lines come from the same dimensions as
visible geometry. The build checks every contact point against the meshes (within 1 cm), tangent changes on ramp
profiles, floor/toe joins, the terrain-following path, furniture clearance and FBX bounds after reimport.

The entrance remains in the original world position despite the larger deck. `ASkatePark` derives its bounds,
meshes, clearance and registered grind paths from `park.json`. Floor paint and planting have no collision. The
pier look volume uses direct shadows, skylight and baked vertex AO, avoiding Lumen's unstable patches on thin decks.

## Film a bounded batch

Start the desktop game, then capture one of the rehearsed route groups:

```sh
uv run atelier play yorimichi --profile desktop-1440
uv run python games/yorimichi/tools/pier_film.py --take street-01 --batch street
```

Use a fresh take name every time. `--batch detail` covers the long flatbar and low manual pad;
`--batch transition` covers bowl, return and mini airs. The detail routes use one push and early ollies to give
the rider a controlled approach. `--rehearse` records telemetry without images.
The tool checks checkout ownership before touching the live bridge, validates the take,
and quits the game to release the render slot. `--keep-game` instead returns the controls. Evidence includes every
input and state; bails, silent walking transitions, repeated captured poses and missing frames reject a take.
The capture deadline defaults to 300 seconds, including final image saving. The mixer preserves
16:9 proportions, combines recorded board audio with an original procedural beat, and exports 1080p and 720p MP4s.

## Sources

- `layout.py`: dimensions, profiles, routes, contact lines and the coastal path.
- `features.py`: skating surfaces, street features, pier and promenade.
- `board.py`: the trick board's deck, truck and wheel meshes (`SM_SkateDeck`, `SM_SkateTruck`, `SM_SkateWheel`).
- `geom.py`: shared-vertex geometry, material routing, colour/AO and FBX export.
- `build.py`: geometry build, checks and gameplay contract.
- `review.py`: textured overview, street, rail-lane, sunset, bowl and mini renders.
- `tools/pier_textures.py`: paid source authoring and offline material finishing.
- `tools/pier_film.py`: bounded capture, validation and game handoff.
- `unreal/Scripts/import_skatepark.py`: material graph, import and collision checks.
