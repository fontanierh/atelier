# South-west detour

A lane leaves the coastal road, runs down through a small fishing village (two fisher houses, a boat shed, a dock,
boats and drying racks) and ends at the cove with the coconut stand and its beach. Offshore, the island holds a
temple on its crown, reached by [sailboat](../../../assets/vehicles/sailboat/README.md) and a stair from its cove.

## Build

```sh
uv run atelier build yorimichi world.southwest unreal.southwest data.stage
```

- `world.layout` calls `southwest.layout.integrate` from `gen_world.py`, after the village and the mini-mega. It
  grades the village terrace and the shore lane, places the houses and props, and places the island
  (`ISLAND`: origin (-150, -530), yaw 15 degrees) with its trees, boulders, torii and temple. The island sits 50 m
  farther offshore after Sunset Pier's enlargement, leaving about 65 m of water at its nearest headland.
- `world.southwest` ([`build.py`](build.py), Blender) builds the props (`stand.py`, `fishing.py`, `temple.py`, on the
  village kit and the shared helpers in `mesh.py`), the island mesh, its boulders and the leaning pines.
- `unreal.southwest` (`unreal/Scripts/import_southwest.py`) imports them and builds the sea plane's `M_Sea`.
- The sailboat is its own asset: `world.sailboat` and `unreal.world` build and import it, and
  `uv run atelier qa yorimichi sailboat SESSION` checks it.

## The island

[`island.py`](island.py) authors the island (`SW_Island`) as a heightfield in island-local metres, and its
placements:

- **Shape.** A broad, low wooded crown (about 99 m) with a lower west top and an east hump, and headlands and points
  on every side, so the outline is uneven from any bearing. Four sea stacks, 14-19 m high, stand off the headlands.
- **Cliffs.** Dark rock cliffs run around the coast, mostly 8-31 m high, up to 38 m under the headlands, and lowest
  at the cove. Their height changes with the bearing and the tall ones break into a ledge. Above them the slope is
  capped at a steep but wooded grade, so bare rock stays at the rim and on a few knobs.
- **Cove and stair.** The pale sand cove on the north side is the sailboat landing. A valley climbs from it, and the
  stair zig-zags up the north face, through five torii, to the temple terrace on the crown's north spur (82 m). The
  stair's cut banks are moss and wood, not bare rock.
- **Forest.** The wood grows in masses (`forest()`): black pines along the cliff tops and headlands, a tall cedar
  grove on the crown behind the temple, and maple and ginkgo drifts in the hollows and on the lower slopes, with a
  few glades. The hearts of the drifts use the tree house's big autumn crowns (`Tree_Canopy_*`).
- **Leaning pines.** `Tree_PineLean_A`/`B` lean out over the cliff edges on the headlands and top every sea stack.
- **Boulders.** Boulders sit at the foot of the cliffs, on the steep lower faces and on the knobs.

### Collision near the stair

The game treats every `Tree*` instance the same way: within 450 m of the world centre on both axes, a tree gets
query collision down to its crown's lowest leaves, and the camera ignores it; beyond 450 m on either axis it has no
collision and no shadow. Most of the stair (world y -377 to -461) is inside that line, and a crown hanging over a
walk is an invisible wall, so `scatter()` keeps every island tree clear of the stair:

- `stair_blocked()` tests the trunk and crown of each tree against every stretch of the stair within reach, using
  each species' size (`TREE_DIMS`), the walk's half-width with the player's radius (2.7 m) and head height.
- The cove's sand and the temple terrace have their own tree-free rings.
- Leaning pines keep 12 m off the stair. They are named `Tree_PineLean_*` so that, like the other trees, they never
  stop the camera.
- Boulders are `SW_*` props and block the camera, so each keeps its own width off the stair.

No trunk, crown or boulder stands in the stair's walk, on the cove's sand or on the terrace.

### Concepts

[`tools/island_concepts.py`](../../../tools/island_concepts.py) paints three concept views of the island with GPT
Image 2.5 Sunburst (quality high), steered by in-game stills and Blender previews of `island.py` from the same
cameras. The images, prompts and provenance are in
[`assets/southwest/concepts/`](../../../assets/southwest/concepts/): `far.jpg` (from the mainland hilltop), `boat.jpg`
(from the dinghy at the cove) and `aerial.jpg`. Each provenance file is written with status `submitted` before its
paid call, and a view that has one is never sent again.

The shape follows the concepts where a heightfield can: the low, broad crown, taller rock headlands and stacks, the
cove between two headlands, and more ginkgo gold in the drifts. The painted world map's island is repainted to match
([WORLD_MAP.md](../../../docs/WORLD_MAP.md#local-repaints)).

## The sea

`unreal/Scripts/sea_look.py` holds the open-sea look shared by the sea plane's `M_Sea` (`import_southwest.py`) and
the Hidamari harbour's `M_HarborWater` (`harbor_material.py`): the waves, the colour and the haze as HLSL for Custom
nodes, and the values they use.

The sea's colour is emissive, not left to the engine's lighting. From eye height nearly all the sea is seen at
grazing angles, where water's Fresnel reflectance runs to 1, and a lit sea mirrors the sky light's capture of the dome
into one flat sheet with no horizon. The dome is unlit and the exposure is fixed, so an emissive colour given in the
dome's own units shows exactly as chosen, next to the sky:

- a deep blue-teal body, lighter teal over the first 5 m behind the surface;
- a reflection of the painted dome, by water's Fresnel term on the wave normals, scaled down so the body shows.
  Facets turned toward the viewer mirror the bluer sky higher up, so the waves read;
- where the view grazes the far, flat sea the reflection strengthens (`GRAZE`), and a haze comes in with distance
  (`HAZE_CM`, a tenth at 1 km, a third at 4 km) toward the dome's horizon colour times `FAR`. The sea gets lighter
  toward the horizon but stays a little darker than the sky, so the horizon is a soft line;
- white surf where the water meets the cliffs, stacks, beaches, piles and hulls, from the scene depth behind the
  translucent surface: a band 1.6 m deep near the camera that widens to about a pixel and a half far away, and none
  beyond 2.5 to 4 km;
- a few white flecks on the short wave crests, in slow, kilometre-wide gusts.

The waves are nine crossing trains in world space, spread about the world's wind, 21 m down to 1.1 m long, at
deep-water speeds. Each train fades before its phase changes too fast across a pixel, so the far sea goes flat
rather than noisy.

The engine lights the surface only for the sun's glints: black base colour, roughness .15, specular .02. Below a
specular of .25 the engine scales its grazing reflection by 50 x F0 (here .08), so the captured sky cannot wash out
the authored colour.

On its outline the harbour water is exactly this sea: the same waves, emissive colour, base colour, roughness and
specular. It is opaque, so it has no surf or shallows there. Its own lit water takes over within 200 m of the
outline, and only the haze applies over it. `refresh_water_materials.py` rebuilds both materials, and the forest
lake's, without reimporting any mesh.

The sea plane (`world/build_terrain.py`) reaches 24 km from the centre, past the 20 km sky dome, so the dome's lower
half never shows below the horizon.
