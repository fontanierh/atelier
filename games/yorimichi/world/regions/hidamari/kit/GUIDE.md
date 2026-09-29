# Building kit guide (read fully before modelling)

You are designing one building type for Hidamari, the big city of the Yorimichi game (Unreal 5.8, low-poly, flat-shaded
polygons with vertex colours). Each building is a Python module in `japan/hidamari/kit/<slug>.py` that builds a
`village.build.Mesh` with primitives. Blender runs it headless; the lab script imports it into Unreal and renders it in place.

## Commands (always this interpreter; run from the repo root)

```sh
PY=python3   # any Python 3.11+ with numpy and Pillow
$PY japan/tools/building_lab.py briefs                 # slugs, assets, titles
$PY japan/tools/building_lab.py build SLUG             # Blender -> Unreal import -> renders (2-4 min; queues on locks)
$PY japan/tools/building_lab.py capture SLUG           # renders only
$PY japan/tools/building_lab.py ref SLUG --n 2         # concept images (needs OPENAI_API_KEY_FILE)
$PY japan/tools/building_lab.py reconcile SLUG --ref docs/.../ref_1.jpg --render docs/.../render_v2_front.jpg
```
Outputs: `japan/docs/hidamari/kit/SLUG/` (`ref_N.jpg`, `render_vK_front.jpg`, `render_vK_street.jpg`, `reconciled_N.jpg`,
`provenance.json`). Build logs: `japan/out/logs/kit-build-<asset>.log`, `kit-import-<asset>.log`. A Python error in your
module shows up in the build log tail. Look at every render you produce (Read the PNG) before deciding what to change.

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

- Metres, Z up. The building's local origin is the centre of its lot at street level (z=0). **The front faces -Y**
  (the street). The lab renders a placement whose front is lit by the sun.
- Footprint: `width` x `depth` from the brief (about 22 x 16 m). Keep walls within |x| <= width/2 and |y| <= depth/2.
  Neighbouring lots repeat every 27 m along X, so anything wider than 25 m collides with the neighbour. The sidewalk
  in front is ~3.5 m: awnings, steps, benches and props may extend to y = -depth/2 - 2.5 (never further; a planter
  already stands near x = -9, y = -depth/2 - 1.5, keep that spot free of large props). Nothing beyond +depth/2+1 at the back.
- The ground is flat paving under the whole lot; start walls at z = -0.4 (sunk) so slopes never show a gap. Nothing may
  hang in the air. Nothing at z < -0.6.
- Corner lots expose the side walls and the back: dress all four sides (windows, a side door, downpipes, a pent roof,
  vents). A blank wall is a defect. Gables must be closed (soffit polygons) so sky never shows through the roof.
- Colliders: `m.collider(centre,size)` axis-aligned boxes (in the current `m.at` frame). Add one for every volume the
  player could walk into (walls, annexes, posts, big props, benches). Don't collide awnings, signs, eaves, lanterns.

## Primitives (all take a colour key or an (r,g,b) tuple)

- `m.box(centre,(w,d,h),key,bevel=0)`; `m.beam(a,b,width,depth,key)`; `m.poly([p0,p1,p2,p3],key)` (counter-clockwise seen
  from outside = front face; double a poly with reversed order if both sides are visible); `m.lathe(centre,[(z,r),...],key,n)`.
- `with m.at((x,y,z),yaw_degrees):` transforms everything inside (use it for the side walls: `with m.at((w/2,0,0),90)` puts
  local -Y on the +X side).
- Village helpers (front at y, facing -Y): `v.window(m,x,y,z,w,h,glow)`, `v.door(m,x,y,z,w,h)`, `v.awning(m,x,y,z,w,depth,key)`,
  `v.pot(m,x,y,z,scale,key,plant,form)`, `v.bench(m,x,y,z,w)`, `v.lantern(m,x,y,z,size)`, `v.roof(m,w,d,eave,rise,key)` (thick curved
  tiled gable, w along X), `v.shell(m,w,d,eave,timber)`, `v.foundation(m,w,d)`.
- Arcade helpers: `arcade.window(m,x,y,z,w,h,shopfront)`, `arcade.lantern(m,x,y,z,size)` (glowing paper lantern),
  `arcade.flowers(m,x,y,z,seed)`, `arcade.shelf(m,x,y,kind,seed)`, `arcade.book_icon(m,x,y,z,w)`.
- `lettering(m,'お茶',(x,y,z),size,color='cream')` extrudes text facing -Y (Japanese uses Noto Sans JP automatically).
  Rotate with `m.at` for other sides. Keep sign text short; authored Japanese, no English shop names.
- Read `japan/hidamari/build.py` (`shop`, `simple_roof`), `japan/hidamari/arcade.py` (`shop`) and `japan/hidamari/plaza.py`
  (`clock_hall`) for worked examples of the level of detail expected.

## Materials

Everything is one vertex-colour material (`M_Arcade`): colours near `paper` (.92,.58,.22) and `arc_paper` glow like
lanterns, `arc_shopglass` (.20,.095,.03) glows faintly (lit shop windows), `arc_canvas` glows softly, wood-like browns get
a subtle grain. Palette keys: plaster, plaster_light, cream, wood, wood_light, wood_dark, roof, roof_edge, stone,
stone_light, paper, window, rust, clay, metal, green, green_dark, leaf, blue, brick, soil, arc_plaster, arc_timber,
arc_trim, arc_roof, arc_cloth, arc_canvas, arc_glass, arc_paper, arc_stone, arc_leaf, arc_shopglass, arc_rose, arc_bloom,
arc_ivory, plus anything you add. Colours are linear; pure white (>.8) reads as blown-out, keep plaster around .5-.66.

## Quality bar

The reference concept sets the target. Aim for: a bold, specific silhouette (roof form, eaves, chimney, dormer, annex),
depth on the facade (recessed entrance, projecting bay, awnings, eaves 0.8-1.2 m deep, posts, sills), readable props
at street level (bench, crates, bicycle, lanterns, noren, pots, sign board), a lit ground floor, and four dressed sides.
Avoid: thin flat trims that shimmer, thousands of tiny parts, faces coincident with other faces (offset >= 0.01 m),
props in the road, colours brighter than the game's. Budget: under 60,000 triangles per building (the lab prints it).
