# Building kit

Each building type on Hidamari's ordinary blocks is a Python module in this folder, `<slug>.py`, that builds a
`village.build.Mesh` from primitives (low-poly, flat-shaded, vertex colours). `hidamari/build.py` lets these modules
replace the plain `shop(i)` boxes, so the city layout keeps its placements. [`briefs.json`](briefs.json) holds each
slug's brief: its assets, title, footprint and description.

## Commands

[`lab.py`](lab.py) builds, places and renders one building at a time:

```sh
LAB="uv run python games/yorimichi/world/regions/hidamari/kit/lab.py"
$LAB briefs                                   # slugs, assets, titles
$LAB build SLUG                               # Blender build -> Unreal import -> in-game renders
$LAB capture SLUG                             # renders only
$LAB ref SLUG --n 2                           # concept images from the brief and game stills (paid)
$LAB reconcile SLUG --ref REF --render RENDER # a reconciled target from a concept and a render (paid)
```

Everything lands in `build/yorimichi/kit/SLUG/`: `ref_N.jpg`, `render_vK_front.jpg`, `render_vK_street.jpg`,
`reconciled_N.jpg` and `provenance.json`. Build and import logs are `build/yorimichi/logs/kit-build-<asset>.log` and
`kit-import-<asset>.log`; a Python error in a module shows in the build log's tail. `ref` and `reconcile` call GPT Image
2.5 Sunburst and need `OPENAI_API_KEY`; in-game stills in `build/yorimichi/kit/style/` steer the concepts' style.
Look at every render before deciding what to change.

## Module contract

```python
"""One-line description."""
import math,random
from village import build as v          # Mesh, PALETTE, window, door, awning, pot, bench, lantern, roof, shell, foundation
from hidamari import arcade             # palette(), lantern(), flowers(), shelf(), window(), book_icon()
ASSETS={'HD_Shop_00':0,'HD_Shop_08':1}   # exactly the assets from briefs.json -> variant key
def build(name,variant,lettering):
    arcade.palette();v.PALETTE.update({'my_key':(r,g,b)})   # linear 0..1 colours; keep them in the game's muted range
    m=v.Mesh(name)
    ...
    return m
```

## Coordinates and footprint

- Metres, Z up. The local origin is the centre of the lot at street level (z = 0). **The front faces -Y** (the
  street). The lab renders a placement whose front is lit by the sun.
- Footprint: `width` x `depth` from the brief (about 22 x 16 m). Keep walls within |x| <= width/2 and |y| <= depth/2.
  Lots repeat every 27 m along X, so anything wider than 25 m collides with the neighbour. The sidewalk in front is
  about 3.5 m: awnings, steps, benches and props may reach y = -depth/2 - 2.5, never further. A planter stands near
  x = -9, y = -depth/2 - 1.5; keep that spot free of large props. Nothing beyond +depth/2 + 1 at the back.
- The ground is flat paving under the whole lot. Start walls at z = -0.4 so slopes never show a gap. Nothing hangs in
  the air, and nothing goes below z = -0.6.
- Corner lots expose the side walls and the back: dress all four sides (windows, a side door, downpipes, a pent roof,
  vents). A blank wall is a defect. Close the gables (soffit polygons) so sky never shows through the roof.
- Colliders: `m.collider(centre,size)` adds an axis-aligned box in the current `m.at` frame. Add one for every volume
  the player could walk into (walls, annexes, posts, big props, benches), none for awnings, signs, eaves or lanterns.

## Primitives

All take a colour key or an (r,g,b) tuple.

- `m.box(centre,(w,d,h),key,bevel=0)`; `m.beam(a,b,width,depth,key)`; `m.poly([p0,p1,p2,p3],key)` (counter-clockwise
  seen from outside is the front face; add the reversed poly if both sides show); `m.lathe(centre,[(z,r),...],key,n)`.
- `with m.at((x,y,z),yaw_degrees):` transforms everything inside; `with m.at((w/2,0,0),90)` puts local -Y on the +X
  side, for the side walls.
- Village helpers (front at y, facing -Y): `v.window(m,x,y,z,w,h,glow)`, `v.door(m,x,y,z,w,h)`,
  `v.awning(m,x,y,z,w,depth,key)`, `v.pot(m,x,y,z,scale,key,plant,form)`, `v.bench(m,x,y,z,w)`,
  `v.lantern(m,x,y,z,size)`, `v.roof(m,w,d,eave,rise,key)` (thick curved tiled gable, w along X),
  `v.shell(m,w,d,eave,timber)`, `v.foundation(m,w,d)`.
- Arcade helpers: `arcade.window(m,x,y,z,w,h,shopfront)`, `arcade.lantern(m,x,y,z,size)` (glowing paper lantern),
  `arcade.flowers(m,x,y,z,seed)`, `arcade.shelf(m,x,y,kind,seed)`, `arcade.book_icon(m,x,y,z,w)`.
- `lettering(m,'お茶',(x,y,z),size,color='cream')` extrudes text facing -Y (Japanese uses Noto Sans JP). Rotate it with
  `m.at` for other sides. Keep sign text short and in Japanese; no English shop names.
- Worked examples of the expected detail: `shop` and `simple_roof` in [`../build.py`](../build.py), `shop` in
  [`../arcade.py`](../arcade.py) and `clock_hall` in [`../plaza.py`](../plaza.py).

## Materials

Everything is one vertex-colour material, `M_Arcade`. Colours near `paper` (.92, .58, .22) and `arc_paper` glow like
lanterns, `arc_shopglass` (.20, .095, .03) glows faintly as lit shop windows, `arc_canvas` glows softly, and
wood-like browns get a subtle grain. Palette keys: plaster, plaster_light, cream, wood, wood_light, wood_dark, roof,
roof_edge, stone, stone_light, paper, window, rust, clay, metal, green, green_dark, leaf, blue, brick, soil,
arc_plaster, arc_timber, arc_trim, arc_roof, arc_cloth, arc_canvas, arc_glass, arc_paper, arc_stone, arc_leaf,
arc_shopglass, arc_rose, arc_bloom, arc_ivory, plus any you add. Colours are linear; pure white (> .8) reads as blown
out, so keep plaster around .5-.66.

## Quality bar

The brief's concept sets the target. Aim for a bold, specific silhouette (roof form, eaves, chimney, dormer, annex),
depth on the facade (recessed entrance, projecting bay, awnings, eaves 0.8-1.2 m deep, posts, sills), readable props
at street level (bench, crates, bicycle, lanterns, noren, pots, sign board), a lit ground floor and four dressed
sides. Avoid thin flat trims that shimmer, thousands of tiny parts, faces coincident with other faces (offset them by
at least 0.01 m), props in the road and colours brighter than the game's. Budget: under 60,000 triangles per
building; `build` prints the count and refuses a mesh over it.

## Limits

`lab.py` takes its own Blender and Unreal file locks, not the shared render lock and memory guard; do not run it
beside another heavy job.
