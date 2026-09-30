# The tree house

A children's secret base hidden on the west hillside below the Woodland air-station trail. From the trail you see one
small hut in a maple; through it, twelve rope bridges join ten places in the canopy: the Map room, the big Heart room
round an old camphor, the Kitchen, the Sleeping nest, the Boat room under an upturned rowboat, a spiral slide down to
the forest floor, a pulley deck, a ring of wind chimes, and a lookout whose crow's nest stands over the crowns and
looks out to the sea.

The plan (places, bridges, heights, trees, how it was made) is [docs/TREEHOUSE_PLAN.md](../../../docs/TREEHOUSE_PLAN.md);
every part and how it is made is [docs/TREEHOUSE_ITEMS.md](../../../docs/TREEHOUSE_ITEMS.md). The paintings, textures
and Tripo models are in [assets/treehouse](../../../assets/treehouse/README.md).

## Files

| File | What it does |
| --- | --- |
| `layout.py` | The single source of truth: places, bridges, stairs, slide, crow's nest, anchor trunks, the canopy trees round the house and the existing trees that must go. `gen_world.py` calls `integrate()` last, after every other region, and it writes `world['treehouse']` and `build/yorimichi/treehouse/layout.json`. |
| `trees.py` | Blender: the four tall canopy trees (maple, crimson, amber, ginkgo) and their recoloured leaf atlases, made like the rest of the forest. |
| `props.py` | Blender: the 13 Tripo props, reduced, sized and given a calibrated colour gain. |
| `build.py` | Blender: TH_Structure (walkable, with collision), TH_Trunks, TH_Dressing (rooms, kit, window panes), the prop placements, and `runtime.json` (props, 69 lantern lights, room boxes and their colour grade). |
| `tmesh.py` | The mesh builder `build.py` uses: material slots, UVs, vertex colours. |
| `plan_views.py` | The plan map and section drawings. |
| `preview.py` | Quick Workbench previews of the built blend. |
| `zfight.py` | Blender: finds faces of the built tree house and its placed props that lie in the same plane, face the same way and overlap, which flicker in the game. It exits 1 while any remain. |
| `screen.py` | Sight lines from every walk to the lookout, and the grove of tall trees that hides it from the lake trail. `python games/yorimichi/world/regions/treehouse/screen.py [--eye 1.6]` prints where it still shows. |

The Unreal side is `unreal/Scripts/import_treehouse.py` (meshes, the tree house materials, textures, props, canopy
trees) and the tree house block in `AJapanWorld`, which merges `runtime.json` at load: props as instanced meshes,
point lights, and the warmer grade while the camera is inside a room.

## Build and look

```sh
atelier build yorimichi unreal.treehouse data.stage
python games/yorimichi/scenarios/treehouse.py LABEL              # the 22 reference views beside their paintings
python games/yorimichi/scenarios/treehouse_tour.py film LABEL    # the tour, rendered in the game
python games/yorimichi/scenarios/treehouse_tour.py cut LABEL     # ... cut into build/yorimichi/treehouse/tour/LABEL.mp4
python games/yorimichi/scenarios/treehouse_walk.py plan          # a player's route through every place
python games/yorimichi/scenarios/treehouse_walk.py film TAKE     # Cairo walks it in the game (--rehearse: no frames)
python games/yorimichi/scenarios/treehouse_walk.py cut TAKE      # ... with its footsteps: walk/TAKE/treehouse-walk.mp4
```

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
- Each window has a pane: an extra material slot of TH_Dressing drawn additive, a soft glow in the opening. There are
  no sunbeam shafts or floor pools: they flickered on the floors and hid the rooms from the camera.
- Nothing may lie in the plane of another face that faces the same way (a rug on a floor, a rail end in a post, two
  wall boards at a corner): the depth test flips between them and they flicker. Lift or shorten one, and run
  `zfight.py` on the build before committing.
- The forest the tree house adds round itself keeps 7.5 m off the air-station trail and clear of the station, as the
  zeppelin region cleared them (`zeppelin.layout.clear`). A cedar's crown is solid down to head height, so one on the
  trail is an invisible wall across it.
- The canopy trees stand with their crown tops about a metre under to 3.5 m over the nearest deck and keep 2.5 m of
  headroom over every deck and roof; the lookout's crow's nest (89 m) stands over them, with the crowns on its
  sight lines to every bridge cleared.
- The lookout should not show over the forest from the lake trail. `screen.py` checks sight lines from eye and camera
  height (1.6 and 2.6 m, the middle and both edges of the walk) to points up the tower, through the terrain, the
  rooms and every tree crown, and adds a few tall cedars and amber canopy trees where they hide the most. They keep
  7.5 m off every walk and the road, 22 m from every place, clear of the lake, the cabin and the station, and may
  take the spot of a short maple, ginkgo or broadleaf. `world['treehouse']` records them (`forest_screen`,
  `forest_screen_replaced`, `screen` with the seen metres before and after). The air-station trail's last stretch
  before the entry still sees the tower down the porch reveal on purpose, and the crow's nest still looks over the
  grove to the bridges and the sea.
