"""Tall autumn canopy trees round the tree house (Blender headless).

    atelier build yorimichi world.treehouse_trees

The houses stand 3 to 16 m up the hillside, above the tops of the island's maples and ginkgos, so from a deck the eye
met sky and sea where the paintings have a wall of red and gold crowns. These trees hold their crowns at deck height.
They are made like the rest of the forest (build_assets.py): card canopies with normals from the crown centre, the
same atlases and material slots, so they shade and sway alike. They have a taller trunk and a crown of clumped
lobes. Two recoloured maple atlases (crimson, amber) widen the palette toward the paintings.
Writes build/yorimichi/treehouse/trees/<name>.fbx, T_leaf_crimson.png, T_leaf_amber.png and trees.json (dimensions for
layout.py and the Unreal import).
"""
import sys as _sys; from pathlib import Path as _Path; _sys.path.insert(0, str(_Path(__file__).resolve().parents[2])); import yori  # noqa: E402,F401
import json, math, random, sys
from pathlib import Path
import bpy
import numpy as np
from mathutils import Vector

import build_assets as A

OUT = yori.OUT/'treehouse'/'trees'
# name: seed, leaf material, height, spread, side lobes, leaf cards
SPECS = {
    'Tree_Canopy_Maple':   (51, 'LeafMaple', 17., 9.0, 5, 1250),
    'Tree_Canopy_Crimson': (52, 'LeafCrimson', 16., 8.6, 5, 1200),
    'Tree_Canopy_Amber':   (53, 'LeafAmber', 18., 8.4, 4, 1200),
    'Tree_Canopy_Ginkgo':  (54, 'LeafGinkgo', 19., 6.6, 4, 1100),
}
# Every tree exports its leaves under the maple slot. The first import of a new mesh crashes Unreal's commandlet, so the
# import copies the island's Tree_Maple_A (slots Bark, LeafMaple) and reimports over it, then gives the leaf slot the
# tree's own material instance.
SLOT = {'LeafMaple': 'LeafMaple', 'LeafCrimson': 'LeafMaple', 'LeafAmber': 'LeafMaple', 'LeafGinkgo': 'LeafMaple'}
# New atlases: hue (degrees) of the maple atlas mapped to a*h+b, saturation and value scaled.
RECOLOUR = {'crimson': (.35, -8., 1.06, .9), 'amber': (.45, 28., 1.0, 1.06)}


def hsv(rgb):
    mx = rgb.max(1); mn = rgb.min(1); d = mx-mn; h = np.zeros(len(rgb))
    r, g, b = rgb.T; m = d > 1e-6
    i = m & (mx == r); h[i] = ((g-b)[i]/d[i]) % 6
    i = m & (mx == g) & (mx != r); h[i] = (b-r)[i]/d[i]+2
    i = m & (mx == b) & (mx != r) & (mx != g); h[i] = (r-g)[i]/d[i]+4
    return h*60., np.where(mx > 0, d/np.maximum(mx, 1e-6), 0), mx


def rgb(h, s, v):
    h = (h % 360)/60.; c = v*s; x = c*(1-abs(h % 2-1)); z = np.zeros_like(h); k = np.floor(h).astype(int) % 6
    out = np.stack([np.choose(k, [c, x, z, z, x, c]), np.choose(k, [x, c, c, x, z, z]), np.choose(k, [z, z, x, c, c, x])], 1)
    return out+(v-c)[:, None]


def recolour():
    src = bpy.data.images.load(str(yori.TEXTURES/'T_leaf_maple.png')); w, h = src.size
    px = np.array(src.pixels[:], np.float32).reshape(-1, 4)
    for name, (a, b, sm, vm) in RECOLOUR.items():
        H, S, V = hsv(px[:, :3].astype(np.float64))
        H = np.where(H > 180, H-360, H)             # reds just below 0 stay reds
        out = px.copy(); out[:, :3] = np.clip(rgb(a*H+b, np.clip(S*sm, 0, 1), np.clip(V*vm, 0, 1)), 0, 1)
        img = bpy.data.images.new(f'T_leaf_{name}', w, h, alpha=True)
        img.pixels[:] = out.ravel().tolist()
        path = OUT/f'T_leaf_{name}.png'; img.filepath_raw = str(path); img.file_format = 'PNG'; img.save()


def canopy_tree(name, seed, leaf, H, spread, lobes, cards):
    """A straight trunk forking at 55% of the height into a crown of one top lobe and a ring of side lobes."""
    rng = random.Random(seed); M = A.Mesh(name); bark = A.MATS['Bark']; leafm = A.MATS[SLOT[leaf]]
    lean = Vector((rng.uniform(-.5, .5), rng.uniform(-.5, .5), 0))
    mid = lean*.35+Vector((0, 0, H*.3)); fork = lean+Vector((0, 0, H*.55))
    M.tube((0, 0, -.3), mid, .46, .34, bark, n=10, uvscale=(1, .35))
    M.tube(mid, fork, .34, .24, bark, n=10, uvscale=(1, .35))
    centres = [(fork+Vector((0, 0, H*.25)), (spread*.3, spread*.3, H*.15))]
    a0 = rng.uniform(0, 2*math.pi)
    for i in range(lobes):
        a = a0+2*math.pi*i/lobes+rng.uniform(-.35, .35); r = spread*rng.uniform(.19, .25)
        c = lean+Vector((math.cos(a)*r, math.sin(a)*r, H*rng.uniform(.64, .74)))
        centres.append((c, (spread*rng.uniform(.24, .28), spread*rng.uniform(.24, .28), H*rng.uniform(.12, .15))))
    for c, _ in centres:
        end = fork+(c-fork)*.8
        M.tube(fork-Vector((0, 0, .4)), end, .17, .05, bark, n=6, uvscale=(1, .5))
        side = fork+(c-fork)*.45; off = Vector((rng.uniform(-1, 1), rng.uniform(-1, 1), .6)).normalized()*1.4
        M.tube(side, side+off, .07, .02, bark, n=5)
    vol = [r[0]*r[1]*r[2] for _, r in centres]; total = sum(vol)
    nc = lean+Vector((0, 0, H*.62))
    for (c, r), v in zip(centres, vol):
        A.leaf_canopy(M, c, r, int(cards*v/total), .8, leafm, rng, normal_center=nc, vertical_bias=.35)
    ob = M.build()
    leaf_i = ob.data.materials.find(SLOT[leaf])
    pts = np.array([ob.data.vertices[v].co[:] for p in ob.data.polygons if p.material_index == leaf_i for v in p.vertices])
    dims = dict(trunk_top=round(fork.z, 2), crown_lo=round(float(np.percentile(pts[:, 2], 3)), 2),
                crown_hi=round(float(pts[:, 2].max()), 2),
                radius=round(float(np.percentile(np.hypot(pts[:, 0]-lean.x, pts[:, 1]-lean.y), 92)), 2),
                leaf=leaf, slot=SLOT[leaf], triangles=sum(len(p.vertices)-2 for p in ob.data.polygons))
    return ob, dims


def main():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    OUT.mkdir(parents=True, exist_ok=True)
    A.materials(); recolour(); A.OUTDIR = str(OUT)
    info = {}
    for name, (seed, leaf, H, spread, lobes, cards) in SPECS.items():
        ob, info[name] = canopy_tree(name, seed, leaf, H, spread, lobes, cards)
        A.export(ob, name)
    (OUT/'trees.json').write_text(json.dumps(info, indent=1)+'\n')
    print('TREES COMPLETE', json.dumps(info))


main()
