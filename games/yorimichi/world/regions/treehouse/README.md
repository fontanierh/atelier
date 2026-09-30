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
| `build.py` | Blender: TH_Structure (walkable, with collision), TH_Trunks, TH_Dressing (rooms, kit, sunbeams), the prop placements, and `runtime.json` (props, 69 lantern lights, room boxes and their colour grade). |
| `tmesh.py` | The mesh builder `build.py` uses: material slots, UVs, vertex colours. |
| `plan_views.py` | The plan map and section drawings. |
| `preview.py` | Quick Workbench previews of the built blend. |

The Unreal side is `unreal/Scripts/import_treehouse.py` (meshes, the tree house materials, textures, props, canopy
trees) and the tree house block in `AJapanWorld`, which merges `runtime.json` at load: props as instanced meshes,
point lights, and the warmer grade while the camera is inside a room.

## Build and look

```sh
atelier build yorimichi unreal.treehouse data.stage
python games/yorimichi/scenarios/treehouse.py LABEL              # the 22 reference views beside their paintings
python games/yorimichi/scenarios/treehouse_tour.py film LABEL    # the tour, rendered in the game
python games/yorimichi/scenarios/treehouse_tour.py cut LABEL     # ... cut into build/yorimichi/treehouse/tour/LABEL.mp4
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
- Sunbeams are three extra material slots of TH_Dressing drawn additive: the shaft (fades where seen edge-on and
  toward its edges), the pool on the floor (the window's shape and its cross) and a soft glow in the opening.
- The canopy trees stand with their crown tops about a metre under to 3.5 m over the nearest deck and keep 2.5 m of
  headroom over every deck and roof; the lookout's crow's nest (89 m) stands over them, with the crowns on its
  sight lines to every bridge cleared.
