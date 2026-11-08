# The tree house

A children's secret base hidden on the west hillside below the Woodland air-station trail. From the trail you see one
small hut in a maple; through it, twelve rope bridges join ten places in the canopy: the Map room, the big Heart room
beside an old camphor, the Kitchen, the Sleeping nest, the Boat room under an upturned rowboat, a spiral slide down to
the forest floor, a pulley deck, a ring of wind chimes, and a lookout whose crow's nest stands over the crowns and
looks out to the sea.

The places, bridges, trees, props and design rules are in
[docs/TREEHOUSE_PLAN.md](../../../docs/TREEHOUSE_PLAN.md). The paintings, textures and Tripo models are in
[assets/treehouse](../../../assets/treehouse/README.md).

## Build and check

```sh
uv run atelier build yorimichi unreal.treehouse data.stage
uv run atelier qa yorimichi treehouse LABEL               # the 22 reference views beside their paintings
uv run atelier qa yorimichi treehouse_tour film LABEL     # the tour, rendered in the game (plan, film, cut)
uv run atelier qa yorimichi treehouse_tour cut LABEL      # ... cut into build/yorimichi/treehouse/tour/LABEL.mp4
uv run atelier qa yorimichi treehouse_walk plan           # a player's route through every place
uv run atelier qa yorimichi treehouse_walk film TAKE      # Cairo walks it in the game (--rehearse: no frames)
uv run atelier qa yorimichi treehouse_walk cut TAKE       # ... with its footsteps: walk/TAKE/treehouse-walk.mp4
```

`treehouse_walk film` drives the game through `treehouse_walk_live.py` over the live bridge.

## Files

| File | What it does |
| --- | --- |
| `layout.py` | The single source of truth: places, bridges, stairs, slide, crow's nest, anchor trunks, the canopy trees round the house and the existing trees that must go. `gen_world.py` calls `integrate()` after every other region except the house lots' dressing and the Mega Park trail; it writes `world['treehouse']` and `build/yorimichi/treehouse/layout.json`. |
| `trees.py` | Blender (`world.treehouse_trees`): the four tall canopy trees (maple, crimson, amber, ginkgo) and their recoloured leaf atlases, made like the rest of the forest. |
| `props.py` | Blender (`world.treehouse_props`): the 13 Tripo props, turned, reduced, sized and given a calibrated colour gain. |
| `build.py` | Blender (`world.treehouse`): TH_Structure (walkable, stops the camera), TH_Frame (rails, posts, hand ropes, braces: collision, but the camera passes), TH_Trunks, TH_Dressing (lanterns, thin ropes, cloth, window panes: no collision), the prop placements, and `runtime.json` (props, the lantern lights, room boxes and their colour grade). |
| `tmesh.py` | The mesh builder `build.py` uses: material slots, UVs, vertex colours, the see-through piece bake. |
| `plan_views.py` | The plan map and section drawings, in `build/yorimichi/review/treehouse/plan/`. |
| `preview.py` | Quick Workbench views of the built blend. |
| `zfight.py` | Blender: finds faces of the built tree house and its placed props that lie in the same plane, face the same way and overlap, which flicker in the game. It exits 1 while any remain. |
| `screen.py` | Sight lines from every walk to the lookout, and the grove of tall trees that hides it from the lake trail. `python games/yorimichi/world/regions/treehouse/screen.py [--eye 1.6]` prints where it still shows. |

The Unreal side is `unreal/Scripts/import_treehouse.py` (meshes, the tree house materials, textures, props, canopy
trees) and the tree house block in `AJapanWorld`, which merges `runtime.json` at load: props as instanced meshes,
point lights, and the warmer grade while the camera is inside a room.

## Things to know

- A new static mesh's first FBX import can crash the editor commandlet (the "nearly zero tangents" warning opens the
  message log). The import seeds every new mesh from an existing one and reimports over it.
- A seeded copy keeps the template's import data and far models. The canopy trees drop to one source model, and when
  the first reimport skips the unit conversion (a tree 100 times too small) they are imported a second time; the
  import checks every crown top against `trees.json`.
- The world import (`unreal.world`) clears /Game/Japan, so every region import, the tree house and the sounds rerun
  after it.
- Every material on the instanced props needs "used with instanced static meshes", or it renders as the grid.
- The palette is sRGB and decoded in the material, like the rest of the world's vertex colours.
- The camera see-through ([docs/CAMERA.md](../../../docs/CAMERA.md)) makes `M_TreeHouse` masked: what hides Cairo
  dithers away, and his room's near walls and roof open. While it is on, the chase camera's probe passes the whole
  tree house. The rooms it opens are the room-grade `rooms` in runtime.json; a round room also needs `half_height`.
- Noren are a band and six strips, and the material finds a vertex's strip from its u in sixths, so keep six. Vertex
  alpha is how freely a vertex hangs (0 down the band, 1 at the hem): the material parts the strips round Cairo and
  swings them by it. Other geometry in `M_TreeHouse` keeps alpha 0 and does not move.
- Each window has a pane: an extra material slot of TH_Dressing drawn additive, a soft glow in the opening. Do not add
  sunbeam shafts or floor pools: they flicker on the floors and hide the rooms from the camera.
- The sizes the player walks through are in `layout.py`: the side huts 7 x 6 m inside (`HUT`), doors 1.3 x 2.5 m
  (`DOOR`), walls 3 m to the plate (`WALL`), bridges and stairs 1.4 m wide, no stair rise over 18 cm (`RISE`) and no
  bridge end steeper than 1 in 4. A bridge leaves its deck no more than 40 degrees off square (`SQUARE`; else it
  lands on the edge facing the other end), and its end posts stand splayed `BRIDGE_SPLAY` past the handrails, off
  the way on. In a room the furniture stands against the walls and a 1.4 m lane runs from door to door; no post
  stands free in a room (the hammocks hang from wall pegs), and nothing stands in a lane, a doorway or a bridge
  mouth.
- Nothing may lie in the plane of another face that faces the same way (a rug on a floor, a rail end in a post, two
  wall boards at a corner): the depth test flips between them and they flicker. Lift or shorten one, and run
  `zfight.py` on the build before committing.
- The forest the tree house adds round itself keeps 7.5 m off the air-station trail and clear of the station
  (`zeppelin.layout.clear`). A cedar's crown is solid down to head height, so one on the trail is an invisible wall
  across it.
- The canopy trees stand with their crown tops about a metre under to 3.5 m over the nearest deck and keep 2.5 m of
  headroom over every deck and roof; the lookout's crow's nest (89 m) stands over them, with the crowns on its
  sight lines to every bridge cleared.
- The lookout must not show over the forest from the lake trail. `screen.py` checks sight lines from eye and camera
  height (1.6 and 2.6 m, the middle and both edges of the walk) to points up the tower, through the terrain, the
  rooms and every tree crown, and adds a few tall cedars and amber canopy trees where they hide the most. They keep
  7.5 m off every walk and the road, 22 m from every place, clear of the lake, the cabin and the station, and may
  take the spot of a short maple, ginkgo or broadleaf. `world['treehouse']` records them (`forest_screen`,
  `forest_screen_replaced`, `screen` with the seen metres before and after). The air-station trail's last stretch
  before the entry sees the tower down the porch reveal on purpose, and the crow's nest still looks over the grove
  to the bridges and the sea.
