# Sunset Pier

A 112 × 88 m concrete skate park on piers over the sea, reached by a downhill path from the road to its north
entrance. Warm stone, sage transitions, rust tile, red rails and timber seating follow five
[Sunburst concepts](../../../assets/skatepark/concepts/prompts.json), whose images and per-image provenance sit beside
that file. Riding it is described in [Skateboarding](../../../docs/SKATE.md).

![Sunburst overview](../../../assets/skatepark/concepts/flow-overview.jpg)

## Build

```sh
uv run atelier build yorimichi world.skatepark unreal.skatepark
python3 games/yorimichi/tools/check_skatepark_runtime.py   # offline, needs the native QA executable
uv run atelier qa yorimichi skatepark                      # with the game running
```

`world.skatepark` runs `build.py` in Blender under the render lock and memory guard. It writes the FBX files, the
blend scene, `collision.json` and `build-report.json` to `build/yorimichi/skatepark/`, and the tracked `park.json`
here. To render the review images into `build/yorimichi/skatepark/review/`, run it by hand with `-- --review`
(command in the `build.py` docstring) under `atelier.safety`. `unreal.skatepark` imports the meshes into
`/Game/SkatePark` and the board into `/Game/SkatePark/Board` with the vertex-colour material `M_Village`; `data.stage`
copies `park.json` into `unreal/Content/Data/skatepark/`.

| File | Role |
| --- | --- |
| `layout.py` | Dimensions, ramp profiles, the floor grid, rail contact lines and the terrain-following path |
| `features.py` | The riding geometry, pier, piles, path, furniture, planting and floor paint |
| `geom.py` | Mesh building, vertex AO and colour, FBX export |
| `board.py` | The deck, truck and wheel ([board contract](../../../docs/SKATE.md#board-contract)) |
| `build.py` | Builds everything and checks it |
| `review.py` | Review renders: overview, sea overview, street, bowl, mini-ramp, arrival, rail plan and the board |
| `park.json` | The tracked contract read by `ASkatePark`: placement, meshes, spawn, clearance and rails |

`build.py` fails if a rail contact point is more than 1 cm off the modelled surface, if the path's centre or edges
exceed a 10% grade, if the path dips below the terrain or crosses a house lot, or if promenade furniture stands on a
rideable bank instead of the pier flat. The path is built 5 cm above the upper terrain envelope.

Blocking park meshes (pier, piles, features, path, furniture) use their render triangles as collision; planting and
the floor paint, 25 mm above the deck, are visual only.

## Layout

Coordinates are park-local metres: east +X, north +Y, up +Z, with the origin on the deck at world `(-110, -212, 1.8)`.
Unreal converts world metres `(x, y, z)` to centimetres `(100x, -100y, 100z)`.

| Area | Features |
| --- | --- |
| North street | The arrival plaza at the entrance (x = 6). Two 8 m manual pads, 22 and 38 cm high, along y = 27.5 with an 8 m gap. Steel edges take manuals, slides and grinds. |
| West street terraces | A four-stair terrace (0.72 m, y = 6 to 17) and a seven-stair terrace (1.26 m, y = 21 to 36), each with a 14 m approach deck, two handrails with flat lead-ins and run-outs, two steel-edged hubbas and a long bank facing the park. The stairs descend east into open flat; a smooth rise joins the two levels, with west and side banks for continuous lines. |
| Technical street | A 10 m ledge, 32 cm high, at y = 12 to 15. Three 8 m flat bars: 38 cm round red at y = 20, 30 cm square sage at y = 20, 45 cm round red at y = 29, each in its own lane. |
| Centre wave | An 85 cm hip at x = -21 to 1, y = -8 to 5: rounded banks meet a 6 m top, and the sides taper to flat for diagonal transfers. |
| East return | A 16 m wide quarter at x = 46, y = 18 to 34: 2 m radius, 15 cm of vert, coping and a 3 m deck, with a south access bank to the flat. |
| Horseshoe mini | Two 10 m opposing walls with lips at x = -36 and -10 (y = -23 to -13), 2.5 m radius plus 15 cm of vert, 21 m between the toes, joined by a 180° southern return with a skateable outer shoulder. The north side opens toward the wave; a bank reaches the west deck. |
| Bowl | A rounded rectangle centred at `(29, -10)`: floor 20 × 16 m, coping 26 × 22 m, 3 m transition plus 20 cm of vert (3.2 m deep). A 1.5 m deck meets a 7 m wide bank on every outer face. The floor stays at pier level, above the sea. |
| Promenade | A terracotta floor ribbon, rounded planters, edge benches, grasses, lamps and a timber pergola over the sea, all outside the skating lines. |

The broad banks carry speed through lines: roll down facing the open flat, then link into the street or the
transitions. A vertical coping lip is a drop-in and trick edge, not a mellow bank.

## Transitions

The quarters and the bowl reach 90° and end in a short vertical extension, so they turn horizontal travel upward
before the wheels leave the lip; with the game's `VertAssist`, straight airs come back down into the transition.
The steel coping is a continuous rounded shoulder: no tube overlaps the riding surface or catches the front truck.
Low speeds stall at the lip: use the banks, push on the flat and [pump](../../../docs/SKATE.md#pumping). The curved
bowl corners carry continuous carves.

## In the game

`ASkatePark` registers the coping, handrails, hubbas, ledges, curbs and bars with the Skate plugin, and its
`SkatePark` tag keeps the collision snapshot centred on the pier, so riding between its corners never rebuilds it.
Drifting leaves stay off the pier and stop simulating while the player is on it. A post-process volume over the
pier turns off Lumen global illumination, which leaves coarse patches on the large thin decks; vertex AO, the
skylight and direct shadows light it instead.
