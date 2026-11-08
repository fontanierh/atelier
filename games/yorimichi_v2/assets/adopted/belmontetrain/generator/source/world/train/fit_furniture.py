"""Fit a furniture export to the train's dimension contract under the Atelier render/memory guard.

    uv run python games/yorimichi/world/train/fit_furniture.py ASSET_ID SOURCE.fbx|.glb [--column Z0 Z1]
        [--yaw DEG] [--scale-by width|height] [--side-panels Y0 Y1 Z0 Z1] [--back-panel X0 X1 Z0 Z1]
        [--erase X0 X1 Z0 Z1 SHIFT] [--as OUTPUT_ID] [--table-top] [--side-wood] [--shallow-gaps]
        [--metal HUE0 HUE1 SAT VAL [--metal-skip X0 X1 Y0 Y1 Z0 Z1]] [--cut-box X0 X1 Y0 Y1 Z0 Z1]
        [--drop-along AX AY AZ BX BY BZ R] [--drop-islands X0 X1 Y0 Y1 Z0 Z1] [--porridge Z R] [--hang]
    uv run python games/yorimichi/world/train/fit_furniture.py --metal-only OUTPUT_ID [HUE0 HUE1 SAT VAL]

Imports the mesh, puts its origin at the contract's pivot (floor footprint centre, table lamp base, sconce wall
mount), scales it uniformly so its width matches the contract, then, with --column, lengthens only the part between
heights Z0 and Z1 (fractions of the scaled height) to reach the contract height: a pedestal or legs grow, the top
and the base keep their shape. It never stretches the whole object along one axis. Depth must then match within
the tolerance, or the script stops and reports it.

Writes build/yorimichi/belmonte-train/furniture/<asset>.glb and <asset>.json (dimensions before and after,
scale, column stretch, triangles, checksum) and a check render <asset>.png against a wireframe of the target box.

--hang first stands a long hanging tool upright (long axis vertical, heavy end down, thin side along Y, its bowl
opening towards -Y), for the pivot hook_top (the origin at the top of its hook). --yaw turns the model about +Z first, when Tripo faced it another way (the contract wants the front towards -Y).
--scale-by height fits the height instead of the width (then width and depth follow the model, and the report
says so). --side-panels closes see-through gaps in the sides of a seat: a thin panel just inside each side, from
Y0 to Y1 (fractions of the depth, front to back) and Z0 to Z1 (fractions of the height), textured with the
model's own material at the side's wood. --back-panel does the same for the back (X0 to X1: fractions of the width).
--erase paints over a mark in the texture (carved initials, say): the front-facing area X0..X1, Z0..Z1 (metres, fitted
frame) is covered with the texture of the same area moved SHIFT metres along X. --as writes the result under another
id (a variant of the asset with the same contract dimensions). --table-top builds a real wooden table (top, apron, head
block and brackets) under a draped tablecloth, whose underside Tripo leaves as a flat sheet. --side-wood repaints the
upholstery colour that bleeds onto a sofa's wooden side panels with the surrounding wood. --metal turns the brass and
gilt Tripo paints as yellow into real metal (a metallic-roughness map from the colour map; see metalize); --metal-only
does it to an asset already fitted. --cut-box deletes the faces in a box (metres, fitted frame, after the column
stretch): Tripo parts replaced by modelled ones. --drop-along deletes the loose parts lying wholly within R of the
segment A-B and --drop-islands those wholly inside a box (the canteen pot's ladle, its lumpy porridge top); after any of
the three the footprint is re-centred. --porridge Z R adds a separate porridge surface, a lumpy disc of radius R at
height Z over the pot's base, its own mesh and material for the game to animate.
"""
import sys as _sys; from pathlib import Path as _Path; _sys.path.insert(0, str(_Path(__file__).resolve().parents[1])); import yori  # noqa: E402,F401
import hashlib
import json
import math
import os
import sys
import time

try:
    import bpy
    from mathutils import Vector
except ImportError:
    bpy = None
    Vector = None

from train import layout as L

OUT = yori.OUT / 'belmonte-train' / 'furniture'
TOLERANCE = .02          # metres, on width/depth/height after fitting


def bounds(objs):
    """From the vertices themselves (bound_box lags behind direct vertex edits)."""
    pts = [o.matrix_world @ v.co for o in objs for v in o.data.vertices]
    lo = Vector([min(p[i] for p in pts) for i in range(3)]); hi = Vector([max(p[i] for p in pts) for i in range(3)])
    return lo, hi


def close_gaps(obj, f, faces=('-x', '+x'), n=56, shallow=False):
    """Close see-through gaps in the given faces of a seat ('-x', '+x' sides, '+y' back). Rays cast at the face on an
    n x n grid over the region f (fractions of the face's horizontal extent and of the height) find its wood depth
    (the most common shallow hit) and its holes: rays that cross the whole seat or hit nothing, and that have wood
    above and below in the same column (open air above an arm is not a gap). Each hole cell gets a small two-sided
    patch just behind the wood, textured with the model's walnut from a sound part of the same face. shallow: on the
    sides too, anything well behind the wood is a hole (a notch under a sofa's arm showing the velvet inside)."""
    import bmesh
    from collections import Counter
    from mathutils.bvhtree import BVHTree
    me = obj.data
    lo, hi = bounds([obj])
    bm = bmesh.new(); bm.from_mesh(me)
    uv = bm.loops.layers.uv.verify()
    bm.faces.ensure_lookup_table()
    tree = BVHTree.FromBMesh(bm)
    h = hi.z - lo.z
    report = []
    for spec in faces:
        s, ax = (1 if spec[0] == '+' else -1), 'xyz'.index(spec[1])
        other = 1 - ax                                    # the horizontal axis along the face
        span0, span1 = lo[other], hi[other]
        thick = hi[ax] - lo[ax]
        outer = hi[ax] if s > 0 else lo[ax]
        dirv = Vector((0, 0, 0)); dirv[ax] = -s
        def point(u, z, off):
            p = Vector((0, 0, z)); p[other] = u; p[ax] = outer + s * off
            return p
        du, dz = (f[1] - f[0]) * (span1 - span0) / n, (f[3] - f[2]) * h / n
        cells = {}
        for i in range(n):
            for j in range(n):
                u, z = span0 + f[0] * (span1 - span0) + (i + .5) * du, lo.z + f[2] * h + (j + .5) * dz
                loc, _, _, dist = tree.ray_cast(point(u, z, .5), dirv)
                cells[(i, j)] = dist - .5 if loc is not None else 1e9
        shallow = [round(v, 3) for v in cells.values() if v < .08]
        if not shallow:
            continue
        wood = Counter(shallow).most_common(1)[0][0]
        solid = {}
        for (i, j), v in cells.items():
            if v < .08:
                solid.setdefault(i, []).append(j)
        # through a side, open air above an arm is legitimate, so a hole must cross the whole seat; nothing should
        # show through the back, so there anything well behind the back's wood is a hole
        deep = .8 * thick if ax == 0 and not shallow else wood + .05
        holes = [(i, j) for (i, j), v in cells.items() if v > deep and i in solid and min(solid[i]) < j < max(solid[i])]
        # grow each hole by a cell: the patches sit behind the wood, so the overlap closes the slivers at their edges
        holes = sorted({(i + di, j + dj) for i, j in holes for di in (-1, 0, 1) for dj in (-1, 0, 1) if (i + di, j + dj) in cells})
        # walnut UV, taken inside a plain field: the middle of the lower side panel, or the middle of the lower back
        ref = (lo.y + .30 * (hi.y - lo.y)) if ax == 0 else (lo.x + hi.x) / 2
        _, _, index, _ = tree.ray_cast(point(ref, lo.z + .28 * h, .5), dirv)
        bm.faces.ensure_lookup_table()
        face = bm.faces[index] if index is not None else bm.faces[0]
        cu = sum((l[uv].uv for l in face.loops), Vector((0, 0))) / len(face.loops)
        for i, j in holes:
            u0, z0 = span0 + f[0] * (span1 - span0) + i * du - .002, lo.z + f[2] * h + j * dz - .002
            quad = [point(u0, z0, -(wood + .008)), point(u0 + du + .004, z0, -(wood + .008)),
                    point(u0 + du + .004, z0 + dz + .004, -(wood + .008)), point(u0, z0 + dz + .004, -(wood + .008))]
            for vs in (quad, quad[::-1]):                 # both faces
                nf = bm.faces.new([bm.verts.new(v) for v in vs])
                nf.material_index = face.material_index
                for k, l in enumerate(nf.loops):
                    l[uv].uv = cu + Vector(((k in (1, 2)) * .003, (k in (2, 3)) * .003))
        report.append((spec, wood, len(holes)))
    bm.to_mesh(me); bm.free(); me.update()
    print('CLOSED GAPS', report, flush=True)


def table_top(obj):
    """Put a real wooden table under a draped cloth: Tripo closes the cloth with a flat cap, so from below a table reads
    as a sheet on a stick. Adds, just under the cap, a walnut top, an apron round it and a head block joining the
    pedestal, textured with the model's own wood (sampled on the pedestal)."""
    import bmesh
    from mathutils.bvhtree import BVHTree
    me = obj.data
    lo, hi = bounds([obj])
    h = hi.z - lo.z
    caps = [(p.center.z, p.area) for p in me.polygons if p.normal.z < -.9 and p.center.z > lo.z + .6 * h]
    bins = {}
    for z, a in caps:                                    # the flat cap: the 1 cm band holding the most down-facing area
        bins[round(z, 2)] = bins.get(round(z, 2), 0.) + a
    zc = max(bins, key=bins.get) if bins else hi.z - .04
    band = [v.co for v in me.vertices if zc - .005 < v.co.z < zc + .03]
    x0, x1 = min(p.x for p in band) + .03, max(p.x for p in band) - .03
    y0, y1 = min(p.y for p in band) + .03, max(p.y for p in band) - .03
    bm = bmesh.new(); bm.from_mesh(me); bm.faces.ensure_lookup_table()
    uv = bm.loops.layers.uv.verify()
    tree = BVHTree.FromBMesh(bm)
    zp = lo.z + .45 * (zc - lo.z)                        # the pedestal column, under the cloth's hem
    _, _, index, _ = tree.ray_cast(Vector(((lo.x + hi.x) / 2, lo.y - 1, zp)), Vector((0, 1, 0)))
    face = bm.faces[index] if index is not None else bm.faces[0]
    cu = sum((l[uv].uv for l in face.loops), Vector((0, 0))) / len(face.loops)

    def box(a0, a1, b0, b1, c0, c1):
        vs = [bm.verts.new((x, y, z)) for x in (a0, a1) for y in (b0, b1) for z in (c0, c1)]
        for q in ((0, 1, 3, 2), (4, 6, 7, 5), (0, 4, 5, 1), (2, 3, 7, 6), (0, 2, 6, 4), (1, 5, 7, 3)):
            nf = bm.faces.new([vs[i] for i in q])
            nf.material_index = face.material_index
            for k, l in enumerate(nf.loops):
                l[uv].uv = cu + Vector(((k in (1, 2)) * .004, (k in (2, 3)) * .004))
    top = zc - .006
    box(x0, x1, y0, y1, top - .035, top)                                   # the walnut top
    a = .05
    for ya, yb in ((y0 + a, y0 + a + .025), (y1 - a - .025, y1 - a)):      # the apron
        box(x0 + a, x1 - a, ya, yb, top - .035 - .09, top - .035)
    for xa, xb in ((x0 + a, x0 + a + .025), (x1 - a - .025, x1 - a)):
        box(xa, xb, y0 + a, y1 - a, top - .035 - .09, top - .035)
    cx, cy = (lo.x + hi.x) / 2, (lo.y + hi.y) / 2
    box(cx - .09, cx + .09, cy - .09, cy + .09, top - .035 - .14, top - .035)   # head block on the pedestal
    for sx, sy in ((1, 0), (-1, 0), (0, 1), (0, -1)):                     # four brackets out to the apron
        bx0, bx1 = sorted((cx + sx * .09, cx + sx * (x1 - x0) / 2 * .8)) if sx else (cx - .02, cx + .02)
        by0, by1 = sorted((cy + sy * .09, cy + sy * (y1 - y0) / 2 * .8)) if sy else (cy - .02, cy + .02)
        box(bx0, bx1, by0, by1, top - .035 - .06, top - .035)
    bm.to_mesh(me); bm.free(); me.update()
    print(f'TABLE TOP under the cloth at {zc:.3f} m: {x1 - x0:.2f} x {y1 - y0:.2f} m', flush=True)


def uv_mask(me, w, h, keep):
    """The texels (h x w booleans) covered by the UV triangles of the faces for which keep(polygon) is true."""
    import numpy as np
    uvl = me.uv_layers.active.data
    mask = np.zeros((h, w), bool)
    for p in me.polygons:
        if not keep(p):
            continue
        uvs = [uvl[i].uv for i in p.loop_indices]
        for k in range(1, len(uvs) - 1):
            tri = np.array([[uvs[0].x * w, uvs[0].y * h], [uvs[k].x * w, uvs[k].y * h], [uvs[k + 1].x * w, uvs[k + 1].y * h]])
            x0, y0 = np.floor(tri.min(0)).astype(int); x1, y1 = np.ceil(tri.max(0)).astype(int)
            x0, y0, x1, y1 = max(x0, 0), max(y0, 0), min(x1, w - 1), min(y1, h - 1)
            if x1 < x0 or y1 < y0:
                continue
            X, Y = np.meshgrid(np.arange(x0, x1 + 1) + .5, np.arange(y0, y1 + 1) + .5)
            (ax, ay), (bx, by), (cx, cy) = tri
            d = (by - cy) * (ax - cx) + (cx - bx) * (ay - cy)
            if abs(d) < 1e-9:
                continue
            l1 = ((by - cy) * (X - cx) + (cx - bx) * (Y - cy)) / d
            l2 = ((cy - ay) * (X - cx) + (ax - cx) * (Y - cy)) / d
            mask[y0:y1 + 1, x0:x1 + 1] |= (l1 >= -.02) & (l2 >= -.02) & (1 - l1 - l2 >= -.02)
    return mask


def hang(obj):
    """Turn a long tool that hangs from a hook (the canteen ladle) upright: its long axis vertical with the heavy end
    (the bowl) down and the hook end up, its thinnest side along Y (flat against the wall), the bowl's opening
    towards -Y (the contract's front, away from the wall)."""
    import numpy as np
    from mathutils import Matrix
    from mathutils.bvhtree import BVHTree
    pts = lambda: np.array([v.co[:] for v in obj.data.vertices])
    P = pts(); c = P.mean(0)
    a = np.linalg.eigh(np.cov((P - c).T))[1][:, 2]
    t = (P - c) @ a; span = t.max() - t.min()
    spread = lambda sel: np.linalg.norm((P[sel] - c) - np.outer((P[sel] - c) @ a, a), axis=1).max()
    if spread(t > t.max() - span / 4) > spread(t < t.min() + span / 4):
        a = -a                                        # a now runs from the bowl to the hook
    obj.data.transform(Vector(a).rotation_difference(Vector((0, 0, 1))).to_matrix().to_4x4())
    P = pts(); Q = P[:, :2] - P[:, :2].mean(0)
    thin = np.linalg.eigh(np.cov(Q.T))[1][:, 0]
    obj.data.transform(Matrix.Rotation(math.pi / 2 - math.atan2(thin[1], thin[0]), 4, 'Z'))
    P = pts(); zl = P[:, 2].min(); bowl = P[P[:, 2] < zl + .3 * (P[:, 2].max() - zl)]
    centre = Vector(((bowl[:, 0].min() + bowl[:, 0].max()) / 2, (bowl[:, 1].min() + bowl[:, 1].max()) / 2, (bowl[:, 2].min() + bowl[:, 2].max()) / 2))
    tree = BVHTree.FromPolygons([v.co[:] for v in obj.data.vertices], [p.vertices[:] for p in obj.data.polygons])
    if tree.ray_cast(centre, Vector((0, -1, 0)))[0] is not None and tree.ray_cast(centre, Vector((0, 1, 0)))[0] is None:
        obj.data.transform(Matrix.Rotation(math.pi, 4, 'Z'))   # the opening faced +Y
    obj.data.update()
    print('HANG long axis vertical, bowl down, opening towards -Y', flush=True)


def recentre(obj):
    """Put the footprint's centre back on the origin after parts were removed; returns the shift."""
    lo, hi = bounds([obj])
    shift = Vector(((lo.x + hi.x) / 2, (lo.y + hi.y) / 2, 0))
    for v in obj.data.vertices:
        v.co -= shift
    obj.data.update()
    return shift


def cut_box(obj, box):
    """Delete the faces whose centre lies in box (x0, x1, y0, y1, z0, z1, metres, fitted frame): parts of a Tripo model
    to be replaced by modelled ones (the canteen counter's crooked tray rails)."""
    import bmesh
    x0, x1, y0, y1, z0, z1 = box
    me = obj.data
    bm = bmesh.new(); bm.from_mesh(me)
    gone = [f for f in bm.faces if x0 <= f.calc_center_median().x <= x1 and y0 <= f.calc_center_median().y <= y1
            and z0 <= f.calc_center_median().z <= z1]
    bmesh.ops.delete(bm, geom=gone, context='FACES')
    loose = [v for v in bm.verts if not v.link_faces]
    bmesh.ops.delete(bm, geom=loose, context='VERTS')
    bm.to_mesh(me); bm.free(); me.update()
    print(f'CUT {len(gone)} faces in {box}', flush=True)


def drop_islands(obj, inside, label):
    """Delete every loose part of the mesh whose vertices all satisfy inside(co): a Tripo part fused into the model
    only by sitting in it (the pot's ladle, its lumpy porridge top). Returns the number of parts removed."""
    import bmesh
    me = obj.data
    bm = bmesh.new(); bm.from_mesh(me); bm.verts.ensure_lookup_table()
    seen, gone, parts = set(), [], 0
    for v in bm.verts:
        if v.index in seen:
            continue
        comp, stack = [], [v]; seen.add(v.index)
        while stack:
            a = stack.pop(); comp.append(a)
            for e in a.link_edges:
                b = e.other_vert(a)
                if b.index not in seen:
                    seen.add(b.index); stack.append(b)
        if all(inside(a.co) for a in comp):
            gone += comp; parts += 1
    bmesh.ops.delete(bm, geom=gone, context='VERTS')
    bm.to_mesh(me); bm.free(); me.update()
    print(f'DROP {label}: {parts} loose parts, {len(gone)} vertices', flush=True)
    return parts


def near_segment(a, b, r):
    a, b = Vector(a), Vector(b)
    def inside(co):
        t = max(0., min(1., (co - a).dot(b - a) / (b - a).length_squared))
        return (co - (a + (b - a) * t)).length <= r
    return inside


def in_box(x0, x1, y0, y1, z0, z1):
    return lambda co: x0 <= co.x <= x1 and y0 <= co.y <= y1 and z0 <= co.z <= z1


def porridge_surface(obj, z, r, seg=32, rings=6):
    """A separate porridge top for the pot: a gently lumpy disc of radius r at height z, centred on the pot's base,
    its own mesh (<name>_PorridgeSurface) and material (M_BT_Porridge) so the game can make it bubble."""
    import bmesh
    base = [v.co for v in obj.data.vertices if v.co.z < .02]
    cx, cy = sum(c.x for c in base) / len(base), sum(c.y for c in base) / len(base)
    me = bpy.data.meshes.new(f'{obj.name}_PorridgeSurface')
    bm = bmesh.new()
    centre = bm.verts.new((cx, cy, z + .004))
    loops = []
    for i in range(1, rings + 1):
        rr = r * i / rings
        loops.append([bm.verts.new((cx + rr * math.cos(2 * math.pi * k / seg), cy + rr * math.sin(2 * math.pi * k / seg),
                                    z + .004 * math.sin(3 * k * 2 * math.pi / seg + 7 * rr) * math.cos(11 * rr) * (1 - (i / rings) ** 4)))
                      for k in range(seg)])
    for k in range(seg):
        bm.faces.new((centre, loops[0][k], loops[0][(k + 1) % seg]))
    for a, b in zip(loops, loops[1:]):
        for k in range(seg):
            bm.faces.new((a[k], b[k], b[(k + 1) % seg], a[(k + 1) % seg]))
    uv = bm.loops.layers.uv.new('UVMap')
    for f in bm.faces:
        for lp in f.loops:
            lp[uv].uv = ((lp.vert.co.x - cx) / (2 * r) + .5, (lp.vert.co.y - cy) / (2 * r) + .5)
    bm.normal_update()
    bm.to_mesh(me); bm.free()
    for p in me.polygons:
        p.use_smooth = True
    mat = bpy.data.materials.new('M_BT_Porridge')
    bsdf = mat.node_tree.nodes['Principled BSDF']
    bsdf.inputs['Base Color'].default_value = (.36, .23, .11, 1); bsdf.inputs['Roughness'].default_value = .45
    me.materials.append(mat)
    o = bpy.data.objects.new(me.name, me); bpy.context.scene.collection.objects.link(o)
    print(f'PORRIDGE disc r {r} at z {z}, centre ({cx:.4f}, {cy:.4f}), {len(me.polygons)} faces', flush=True)
    return o


def side_wood(obj, out_id):
    """Repaint upholstery colour that bleeds onto the wooden side panels of a sofa: on the faces of the two outer sides
    (normal along X, at the extreme X), texels that read as the fabric (green over red) are filled from the surrounding
    wood by diffusion, with a little of the wood's grain noise."""
    import numpy as np
    me = obj.data
    lo, hi = bounds([obj])
    img = None
    for m in me.materials:
        for n in (m.node_tree.nodes if m and m.node_tree else []):
            if n.type == 'TEX_IMAGE' and n.image and n.image.colorspace_settings.name == 'sRGB' and n.outputs['Color'].links:
                img = n.image
    if img is None:
        print('SIDE WOOD: no base colour texture', flush=True); return
    w, h = img.size
    px = np.empty(w * h * 4, np.float32); img.pixels.foreach_get(px); px = px.reshape(h, w, 4)
    mask = uv_mask(me, w, h, lambda p: abs(p.normal.x) >= .85 and min(abs(p.center.x - lo.x), abs(p.center.x - hi.x)) <= .06)
    r, g, b = px[..., 0], px[..., 1], px[..., 2]
    bad = mask & (g > r * 1.02) & (g > b * .9)
    good = mask & ~bad
    fill = px[..., :3].copy()
    known = good.copy()
    todo = bad.copy()
    for _ in range(400):                         # diffuse the wood into the green, ring by ring
        if not todo.any():
            break
        acc = np.zeros_like(fill); cnt = np.zeros((h, w))
        for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (-1, -1), (1, -1), (-1, 1)):
            k = np.roll(np.roll(known, dy, 0), dx, 1)
            acc += np.roll(np.roll(fill, dy, 0), dx, 1) * k[..., None]; cnt += k
        new = todo & (cnt > 0)
        fill[new] = acc[new] / cnt[new][:, None]
        known |= new; todo &= ~new
    rng = np.random.default_rng(7)
    fill[bad] *= (.92 + .16 * rng.random(bad.sum()))[:, None]
    px[..., :3][bad] = fill[bad]
    img.pixels.foreach_set(px.ravel())
    path = OUT / f'{out_id}-basecolor.jpg'
    OUT.mkdir(parents=True, exist_ok=True)
    img.filepath_raw = str(path); img.file_format = 'JPEG'; img.save()
    fresh = bpy.data.images.load(str(path), check_existing=False); fresh.pack()
    for m in me.materials:
        for n in (m.node_tree.nodes if m and m.node_tree else []):
            if n.type == 'TEX_IMAGE' and n.image == img:
                n.image = fresh
    print(f'SIDE WOOD: {int(bad.sum())} fabric texels repainted on the side panels ({int(mask.sum())} panel texels)', flush=True)


METAL_DEFAULT = (28., 58., .38, .42)     # hue range (degrees), minimum saturation and value of brass and gilt


def metalize(obj, out_id, hue0=28., hue1=58., sat=.38, val=.42, skip=None):
    """Tripo bakes everything into one colour map with metallic 0: its gilt and brass read as yellow paint. Find the
    brass in the colour map (warm hue, saturated, bright enough: dark wood shares the hue but not the value), and give
    the material a metallic-roughness map (metal 1 and roughness 0.28 there, 0 and 0.70 elsewhere, soft edges), with
    the brass brightened to a metal's reflectance. skip: a box (x0, x1, y0, y1, z0, z1, fractions of the bounds)
    whose faces stay non-metal whatever their colour (a lit, yellowish lampshade). Returns the share taken as metal."""
    import numpy as np
    me = obj.data
    done = []
    for m in me.materials:
        if not (m and m.node_tree):
            continue
        nt = m.node_tree
        bsdf = next((n for n in nt.nodes if n.type == 'BSDF_PRINCIPLED'), None)
        tex = next((n for n in nt.nodes if n.type == 'TEX_IMAGE' and n.image and n.image.colorspace_settings.name == 'sRGB'
                    and n.outputs['Color'].links), None)
        if bsdf is None or tex is None:
            continue
        img = tex.image
        w, h = img.size
        px = np.empty(w * h * 4, np.float32); img.pixels.foreach_get(px); px = px.reshape(h, w, 4)
        rgb = px[..., :3]
        mx, mn = rgb.max(-1), rgb.min(-1)
        s = np.where(mx > 1e-4, (mx - mn) / np.maximum(mx, 1e-4), 0)
        r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
        d = np.maximum(mx - mn, 1e-4)
        hue = np.where(mx == r, ((g - b) / d) % 6, np.where(mx == g, (b - r) / d + 2, (r - g) / d + 4)) * 60
        ramp = lambda x, a, b_: np.clip((x - a) / (b_ - a), 0, 1)
        mask = (ramp(hue, hue0 - 6, hue0) * (1 - ramp(hue, hue1, hue1 + 6)) * ramp(s, sat - .08, sat) * ramp(mx, val - .08, val))
        if skip:
            lo, hi = bounds([obj])
            f = lambda c, i: (c[i] - lo[i]) / max(hi[i] - lo[i], 1e-6)
            inside = lambda p: all(skip[2 * i] <= f(p.center, i) <= skip[2 * i + 1] for i in range(3))
            mask = mask * ~uv_mask(me, w, h, inside)
        # brass reflectance: lift the masked colour to a bright value, keeping its hue
        lift = np.clip(.80 / np.maximum(mx, 1e-3), 1, 2.2)[..., None]
        rgb[:] = rgb * (1 - mask[..., None]) + np.clip(rgb * lift, 0, 1) * mask[..., None]
        img.pixels.foreach_set(px.ravel())
        path = OUT / f'{out_id}-{len(done)}-basecolor.jpg'
        OUT.mkdir(parents=True, exist_ok=True)
        img.filepath_raw = str(path); img.file_format = 'JPEG'; img.save()
        fresh = bpy.data.images.load(str(path), check_existing=False); fresh.pack()
        tex.image = fresh
        # the metallic-roughness map, at most 2048 px, kept as a generated image with its pixels in memory and packed
        # (a file round trip left the exporter reading an empty image)
        k = max(1, w // 2048)
        m2 = mask[::k, ::k]
        mh, mw = m2.shape
        mr = np.ones((mh, mw, 4), np.float32)
        mr[..., 0] = 0.
        mr[..., 1] = .70 * (1 - m2) + .28 * m2              # glTF: roughness in G, metal in B (velvet, cloth, wood: matt)
        mr[..., 2] = m2
        mfresh = bpy.data.images.new(f'{out_id}-{len(done)}-metal-rough', mw, mh, alpha=False, float_buffer=False)
        mfresh.colorspace_settings.name = 'Non-Color'
        mfresh.pixels.foreach_set(mr.ravel())
        mfresh.pack()
        node = nt.nodes.new('ShaderNodeTexImage'); node.image = mfresh; node.interpolation = 'Linear'
        uvsrc = tex.inputs['Vector'].links[0].from_socket if tex.inputs['Vector'].links else None
        if uvsrc:
            nt.links.new(uvsrc, node.inputs['Vector'])
        sep = nt.nodes.new('ShaderNodeSeparateColor')
        nt.links.new(node.outputs['Color'], sep.inputs['Color'])
        for sock in ('Metallic', 'Roughness'):
            for l in list(bsdf.inputs[sock].links):
                nt.links.remove(l)
        nt.links.new(sep.outputs['Blue'], bsdf.inputs['Metallic'])
        nt.links.new(sep.outputs['Green'], bsdf.inputs['Roughness'])
        done.append(float(mask.mean()))
    print(f'METAL: {[round(v, 3) for v in done]} of the texture taken as brass', flush=True)
    return done


def erase_mark(obj, e, out_id, keep_front=False):
    """Cover a mark in the base-colour texture with a clean patch of the same surface, moved along X."""
    import numpy as np
    from mathutils.bvhtree import BVHTree
    import bmesh
    x0, x1, z0, z1, shift = e
    me = obj.data
    bm = bmesh.new(); bm.from_mesh(me); bm.faces.ensure_lookup_table()
    uvl = bm.loops.layers.uv.active
    tree = BVHTree.FromBMesh(bm)
    lo, hi = bounds([obj])

    def uv_at(x, z):
        loc, _, index, _ = tree.ray_cast(Vector((x, lo.y - 1, z)), Vector((0, 1, 0)))
        if loc is None:
            return None
        f = bm.faces[index]
        # barycentric UV inside the hit triangle (fan from the first corner)
        loops = f.loops
        from mathutils.geometry import intersect_point_tri, barycentric_transform
        a = loops[0]
        for b, c in zip(loops[1:], loops[2:]):
            if intersect_point_tri(loc, a.vert.co, b.vert.co, c.vert.co):
                p = barycentric_transform(loc, a.vert.co, b.vert.co, c.vert.co,
                                          a[uvl].uv.to_3d(), b[uvl].uv.to_3d(), c[uvl].uv.to_3d())
                return p.x, p.y
        return tuple(sum((l[uvl].uv for l in loops), Vector((0, 0))) / len(loops))

    img = None
    for m in me.materials:
        for n in (m.node_tree.nodes if m and m.node_tree else []):
            # the colour map (sRGB), whether it feeds Base Color directly or through a Mix node as Tripo's do
            if n.type == 'TEX_IMAGE' and n.image and n.image.colorspace_settings.name == 'sRGB' and n.outputs['Color'].links:
                img = n.image
    if img is None:
        print('ERASE: no base colour texture', flush=True); return
    w, h = img.size
    px = np.empty(w * h * 4, np.float32); img.pixels.foreach_get(px); px = px.reshape(h, w, 4)
    original = px.copy()
    done = 0
    for i in range(80):
        for j in range(30):
            x = x0 + (x1 - x0) * i / 79; z = z0 + (z1 - z0) * j / 29
            dst, src = uv_at(x, z), uv_at(x + shift, z)
            if dst is None or src is None:
                continue
            (du, dv), (su, sv) = dst, src
            di, dj = int((du % 1) * w), int((dv % 1) * h)
            si, sj = int((su % 1) * w), int((sv % 1) * h)
            r = 3
            px[max(0, dj - r):dj + r + 1, max(0, di - r):di + r + 1] = px[max(0, sj - r):sj + r + 1, max(0, si - r):si + r + 1][:min(dj + r + 1, h) - max(0, dj - r), :min(di + r + 1, w) - max(0, di - r)]
            done += 1
    img.pixels.foreach_set(px.ravel())
    path = OUT / f'{out_id}-basecolor.jpg'
    OUT.mkdir(parents=True, exist_ok=True)
    img.filepath_raw = str(path); img.file_format = 'JPEG'; img.save()
    # the exporter writes an embedded image's original bytes: load the edited file and use it instead
    fresh = bpy.data.images.load(str(path), check_existing=False)
    fresh.pack()
    if keep_front:
        img.pixels.foreach_set(original.ravel())      # the front keeps the mark
        # the original keeps the mark on the front; every face gets a reversed twin, textured with the clean copy,
        # and both sides become single-sided: the mark reads from the front only
        bm.free()
        src = me.materials[0]
        back = src.copy(); back.name = src.name + '_back'
        for n in back.node_tree.nodes:
            if n.type == 'TEX_IMAGE' and n.image == img:
                n.image = fresh
        me.materials.append(back)
        bm = bmesh.new(); bm.from_mesh(me)
        faces = list(bm.faces)
        dup = bmesh.ops.duplicate(bm, geom=faces)
        twins = [g for g in dup['geom'] if isinstance(g, bmesh.types.BMFace)]
        bmesh.ops.reverse_faces(bm, faces=twins)
        for f in twins:
            f.material_index = len(me.materials) - 1
        bm.to_mesh(me); bm.free(); me.update()
        for m in me.materials:
            m.use_backface_culling = True
            m['single_sided'] = True
        print('ERASE: mark kept on the front, clean back added', flush=True)
        return
    for m in me.materials:
        for n in (m.node_tree.nodes if m and m.node_tree else []):
            if n.type == 'TEX_IMAGE' and n.image == img:
                n.image = fresh
    bm.free()
    print(f'ERASE: {done} samples patched in {img.name} ({w}x{h})', flush=True)


def metal_only(args):
    """Add the brass metal to an asset already fitted (build/.../furniture/<asset>.glb), in place."""
    out_id = args[1]
    params = [float(v) for v in args[2:6]] if len(args) >= 6 and not args[2].startswith('--') else list(METAL_DEFAULT)
    skip = [float(v) for v in args[args.index('--metal-skip') + 1:args.index('--metal-skip') + 7]] if '--metal-skip' in args else None
    bpy.ops.wm.read_factory_settings(use_empty=True)
    glb = OUT / f'{out_id}.glb'
    bpy.ops.import_scene.gltf(filepath=str(glb))
    obj = next(o for o in bpy.context.scene.objects if o.type == 'MESH')
    for m in obj.data.materials:      # keep the fitted asset's sidedness through the round trip
        if m and m.use_backface_culling:
            m['single_sided'] = True
    share = metalize(obj, out_id, *params, skip=skip)
    bpy.ops.object.select_all(action='DESELECT'); obj.select_set(True)
    bpy.ops.export_scene.gltf(filepath=str(glb), export_format='GLB', use_selection=True, export_yup=True, export_apply=True,
                              export_image_format='AUTO', export_jpeg_quality=88)
    report_path = OUT / f'{out_id}.json'
    if report_path.exists():
        report = json.loads(report_path.read_text())
        report['metal'] = dict(hue=params[:2], min_saturation=params[2], min_value=params[3], skip=skip, share=share)
        report['glb'] = dict(file=glb.name, bytes=glb.stat().st_size, sha256=hashlib.sha256(glb.read_bytes()).hexdigest())
        report_path.write_text(json.dumps(report, indent=1))
    print('METAL ONLY', out_id, share, flush=True)


def main():
    args = sys.argv[sys.argv.index('--') + 1:]
    if args[0] == '--metal-only':
        return metal_only(args)
    asset, src = args[0], _Path(args[1])
    column = None
    if '--column' in args:
        i = args.index('--column'); column = float(args[i + 1]), float(args[i + 2])
    yaw = float(args[args.index('--yaw') + 1]) if '--yaw' in args else 0.
    scale_by = args[args.index('--scale-by') + 1] if '--scale-by' in args else 'width'
    panels = [float(v) for v in args[args.index('--side-panels') + 1:args.index('--side-panels') + 5]] if '--side-panels' in args else None
    back = [float(v) for v in args[args.index('--back-panel') + 1:args.index('--back-panel') + 5]] if '--back-panel' in args else None
    erase = [float(v) for v in args[args.index('--erase') + 1:args.index('--erase') + 6]] if '--erase' in args else None
    out_id = args[args.index('--as') + 1] if '--as' in args else asset
    keep_front = '--keep-front' in args      # with --erase: the mark stays on the front, a separate back is clean
    with_top = '--table-top' in args         # a draped table: build the wooden top, apron and head under the cloth
    wood_sides = '--side-wood' in args       # a sofa: repaint fabric colour bleeding onto its wooden side panels
    shallow = '--shallow-gaps' in args       # with --side-panels: holes need not cross the seat
    cut = [float(v) for v in args[args.index('--cut-box') + 1:args.index('--cut-box') + 7]] if '--cut-box' in args else None
    along = [float(v) for v in args[args.index('--drop-along') + 1:args.index('--drop-along') + 8]] if '--drop-along' in args else None
    island_box = [float(v) for v in args[args.index('--drop-islands') + 1:args.index('--drop-islands') + 7]] if '--drop-islands' in args else None
    porridge = [float(v) for v in args[args.index('--porridge') + 1:args.index('--porridge') + 3]] if '--porridge' in args else None
    metal = ([float(v) for v in args[args.index('--metal') + 1:args.index('--metal') + 5]] if '--metal' in args else None)
    metal_skip = ([float(v) for v in args[args.index('--metal-skip') + 1:args.index('--metal-skip') + 7]] if '--metal-skip' in args else None)
    spec = next(a for a in L.contract()['assets'] if a['id'] == asset)
    tw, td, th = (spec['dimensions_m'][k] for k in ('width', 'depth', 'height'))
    bpy.ops.wm.read_factory_settings(use_empty=True)
    if src.suffix.lower() == '.fbx':
        bpy.ops.import_scene.fbx(filepath=str(src))
    else:
        bpy.ops.import_scene.gltf(filepath=str(src))
    meshes = [o for o in bpy.context.scene.objects if o.type == 'MESH']
    # bake every transform into the mesh, then join into one object named after the asset
    for o in meshes:
        o.data = o.data.copy() if o.data.users > 1 else o.data
        o.data.transform(o.matrix_world); o.parent = None; o.matrix_world.identity()
    for o in list(bpy.context.scene.objects):
        if o.type != 'MESH':
            bpy.data.objects.remove(o)
    bpy.ops.object.select_all(action='DESELECT')
    for o in meshes:
        o.select_set(True)
    bpy.context.view_layer.objects.active = meshes[0]
    if len(meshes) > 1:
        bpy.ops.object.join()
    obj = bpy.context.view_layer.objects.active
    obj.name = obj.data.name = f'SM_BT_{"".join(p.title() for p in asset.split("-"))}'
    if '--hang' in args:
        hang(obj)
    if yaw:
        from mathutils import Matrix
        obj.data.transform(Matrix.Rotation(math.radians(yaw), 4, 'Z'))
    lo, hi = bounds([obj]); before = hi - lo
    swapped = before.y > before.x * 1.15 and tw > td * 1.15 and '--hang' not in args
    if swapped:                          # the width came out along Y: turn it a quarter so width runs along X
        from mathutils import Matrix
        obj.data.transform(Matrix.Rotation(math.radians(90), 4, 'Z'))
        lo, hi = bounds([obj])
    s = tw / (hi.x - lo.x) if scale_by == 'width' else th / (hi.z - lo.z)
    centre = Vector(((lo.x + hi.x) / 2, (lo.y + hi.y) / 2, lo.z))
    for v in obj.data.vertices:
        v.co = (v.co - centre) * s
    lo, hi = bounds([obj])
    stretch = 0.
    if column:
        h = hi.z - lo.z
        z0, z1 = column[0] * h, column[1] * h
        stretch = th - h
        for v in obj.data.vertices:
            if v.co.z >= z1:
                v.co.z += stretch
            elif v.co.z > z0:
                v.co.z += stretch * (v.co.z - z0) / (z1 - z0)
    if cut:
        cut_box(obj, cut)
    if along:
        drop_islands(obj, near_segment(along[0:3], along[3:6], along[6]), 'along a segment')
    if island_box:
        drop_islands(obj, in_box(*island_box), 'inside a box')
    if cut or along or island_box:
        shift = recentre(obj)
        print(f'footprint re-centred by {tuple(round(v, 4) for v in shift[:2])}', flush=True)
    extra = [porridge_surface(obj, *porridge)] if porridge else []
    if with_top:
        table_top(obj)
    if wood_sides:
        side_wood(obj, out_id)
    if panels:
        close_gaps(obj, panels, ('-x', '+x'), shallow=shallow)
    if back:
        close_gaps(obj, back, ('+y',))
    if erase:
        erase_mark(obj, erase, out_id, keep_front)
    if spec['pivot'] == 'wall_mount_center':
        lo, hi = bounds([obj])
        for v in obj.data.vertices:          # back of the sconce on y = 0, front towards -Y, centred in height
            v.co.y -= hi.y; v.co.z -= (lo.z + hi.z) / 2
    if spec['pivot'] == 'hook_top':              # hung from its top: the origin at the top of the hook end
        lo, hi = bounds([obj])
        top = [v.co for v in obj.data.vertices if v.co.z > hi.z - .02]
        hx, hy = sum(c.x for c in top) / len(top), sum(c.y for c in top) / len(top)
        for v in obj.data.vertices:
            v.co.x -= hx; v.co.y -= hy; v.co.z -= hi.z
    obj.data.update()
    lo, hi = bounds([obj]); after = hi - lo
    errors = {k: round(abs(a - t), 4) for k, a, t in (('width', after.x, tw), ('depth', after.y, td), ('height', after.z, th))}
    ok = all(e <= TOLERANCE for e in errors.values())
    if scale_by == 'height':   # the model's own proportions decide width and depth: record them for the contract
        ok = errors['height'] <= TOLERANCE
        tw, td = after.x, after.y
    OUT.mkdir(parents=True, exist_ok=True)
    # check render: the fitted mesh inside a wireframe of the target box
    tgt = bpy.data.objects.new('target', bpy.data.meshes.new('target'))
    z0 = {'wall_mount_center': -th / 2, 'hook_top': -th}.get(spec['pivot'], 0)
    y0, y1 = (-td / 2, td / 2) if spec['pivot'] != 'wall_mount_center' else (-td, 0)
    vs = [(x, y, z) for x in (-tw / 2, tw / 2) for y in (y0, y1) for z in (z0, z0 + th)]
    tgt.data.from_pydata(vs, [(0, 1), (2, 3), (4, 5), (6, 7), (0, 2), (1, 3), (4, 6), (5, 7), (0, 4), (1, 5), (2, 6), (3, 7)], [])
    bpy.context.scene.collection.objects.link(tgt)
    wire = tgt.modifiers.new('w', 'SKIN')
    for sv in tgt.data.skin_vertices[0].data:
        sv.radius = (.004, .004)
    mat = bpy.data.materials.new('target'); mat.node_tree.nodes['Principled BSDF'].inputs['Base Color'].default_value = (1, .2, .1, 1)
    tgt.data.materials.append(mat)
    sc = bpy.context.scene; sc.render.engine = 'BLENDER_EEVEE'; sc.render.resolution_x, sc.render.resolution_y = 1200, 800
    sc.view_settings.view_transform = 'Standard'
    w = bpy.data.worlds.new('w'); sc.world = w; w.node_tree.nodes['Background'].inputs[0].default_value = (1, 1, 1, 1)
    cam = bpy.data.objects.new('cam', bpy.data.cameras.new('cam')); sc.collection.objects.link(cam); sc.camera = cam
    size = max(tw, td, th)
    c = Vector((0, (y0 + y1) / 2, z0 + th / 2))
    cam.location = c + Vector((1.1, -1.6, .8)).normalized() * size * 2.6
    cam.rotation_euler = (c - cam.location).to_track_quat('-Z', 'Y').to_euler()
    sun = bpy.data.objects.new('sun', bpy.data.lights.new('sun', 'SUN')); sun.data.energy = 2.5; sun.rotation_euler = (.7, .2, .8)
    sc.collection.objects.link(sun)
    sc.render.filepath = str(OUT / f'{out_id}.png'); bpy.ops.render.render(write_still=True)
    bpy.data.objects.remove(tgt)
    metal_share = metalize(obj, out_id, *metal, skip=metal_skip) if metal else None
    for m in obj.data.materials:      # Tripo often leaves thin parts single-sided: show both faces
        if m and not m.get('single_sided'):
            m.use_backface_culling = False
    for m in obj.data.materials:      # web and game budget: no texture above 2048 px
        for n in (m.node_tree.nodes if m and m.node_tree else []):
            if n.type == 'TEX_IMAGE' and n.image and max(n.image.size) > 2048:
                n.image.scale(2048, 2048)
    bpy.ops.object.select_all(action='DESELECT'); obj.select_set(True)
    for o in extra:
        o.select_set(True)
    glb = OUT / f'{out_id}.glb'
    bpy.ops.export_scene.gltf(filepath=str(glb), export_format='GLB', use_selection=True, export_yup=True, export_apply=True,
                              export_image_format='JPEG', export_jpeg_quality=88)
    report = dict(asset=asset, source=src.name, source_sha256=hashlib.sha256(src.read_bytes()).hexdigest(),
                  target_m=dict(width=tw, depth=td, height=th), source_size=[round(v, 4) for v in before],
                  quarter_turn=swapped, uniform_scale=round(s, 5), column_fraction=column, column_stretch_m=round(stretch, 4),
                  fitted_m=dict(width=round(after.x, 4), depth=round(after.y, 4), height=round(after.z, 4)), errors_m=errors, ok=ok,
                  triangles=sum(len(p.vertices) - 2 for p in obj.data.polygons), pivot=spec['pivot'],
                  glb=dict(file=glb.name, bytes=glb.stat().st_size, sha256=hashlib.sha256(glb.read_bytes()).hexdigest()))
    report['output_id'] = out_id
    if metal:
        report['metal'] = dict(hue=metal[:2], min_saturation=metal[2], min_value=metal[3], skip=metal_skip, share=metal_share)
    (OUT / f'{out_id}.json').write_text(json.dumps(report, indent=1))
    print('FIT', json.dumps(report), flush=True)
    if not ok:
        raise SystemExit(f'{asset}: fitted size misses the contract by {errors}')


def _run_guarded():
    from atelier import engine
    from atelier.harness.safety import guarded
    report = yori.OUT / 'logs' / f'fit_furniture-{int(time.time() * 1000)}.guard'
    cmd = [
        str(engine.blender()), '-b', '-t', '3',
        '--python', str(_Path(__file__).resolve()), '--', *sys.argv[1:],
    ]
    raise SystemExit(guarded.run(
        cmd, report, timeout=600, purpose='fit belmonte train furniture',
        small_gib=3.0, kind='job',
        env={**os.environ, 'ATELIER_GUARDED_FIT_FURNITURE': '1'},
    ))


if __name__ == '__main__':
    if bpy is None:
        _run_guarded()
    if os.environ.get('ATELIER_GUARDED_FIT_FURNITURE') != '1' and not os.environ.get('ATELIER_MEMORY_GUARD'):
        raise SystemExit('Run fit_furniture.py via uv run python games/yorimichi/world/train/fit_furniture.py ... so it executes under atelier.harness.safety.guarded')
    main()
