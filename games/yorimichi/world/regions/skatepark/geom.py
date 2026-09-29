"""Small mesh builder for the skate pier and board: shared-vertex patches (smooth ramps),
flat polygons, tubes; per-corner base colours with a surface tag; later a shading pass
(noise, paint wear, baked ambient occlusion) and export through bpy."""
import math
import numpy as np

# Linear albedo. The game's exposure turns pale colours white: stay near 0.05-0.35.
PAL = {
    'concrete': (0.300, 0.288, 0.258), 'concrete_light': (0.330, 0.318, 0.285), 'concrete_dark': (0.215, 0.205, 0.182),
    'underside': (0.125, 0.118, 0.103), 'skirt': (0.205, 0.195, 0.172), 'joint': (0.150, 0.142, 0.124),
    'teal': (0.105, 0.235, 0.225), 'salmon': (0.440, 0.175, 0.120), 'mustard': (0.400, 0.285, 0.075),
    'dusty_blue': (0.120, 0.175, 0.270),
    'steel': (0.070, 0.071, 0.068), 'coping': (0.115, 0.116, 0.112),
    'red': (0.420, 0.045, 0.032), 'yellow': (0.500, 0.350, 0.040), 'railing': (0.125, 0.190, 0.190),
    'pole': (0.055, 0.070, 0.062), 'lamp': (0.92, 0.58, 0.22), 'lamp_cap': (0.045, 0.050, 0.048),
    'pile': (0.170, 0.162, 0.145), 'pile_wet': (0.070, 0.074, 0.060), 'algae': (0.055, 0.085, 0.045),
}
CONCRETE_TAGS = {'concrete', 'deck', 'path', 'skirt', 'wall', 'pile', 'underside'}


def newell(pts):
    p = np.asarray(pts, float); q = np.roll(p, -1, axis=0)
    n = np.array([np.sum((p[:, 1] - q[:, 1]) * (p[:, 2] + q[:, 2])),
                  np.sum((p[:, 2] - q[:, 2]) * (p[:, 0] + q[:, 0])),
                  np.sum((p[:, 0] - q[:, 0]) * (p[:, 1] + q[:, 1]))])
    return n


class MeshData:
    def __init__(self, name):
        self.name = name
        self.verts = []; self.faces = []; self.colors = []; self.smooth = []; self.tags = []

    # --- primitives -------------------------------------------------------------------
    def vert(self, p):
        self.verts.append(tuple(float(c) for c in p)); return len(self.verts) - 1

    def face(self, idx, color, tag='concrete', smooth=False, want=None):
        """Face from vertex indices. `want` (a direction) flips the winding to face it."""
        idx = [a for k, a in enumerate(idx) if a != idx[k - 1]] if len(idx) > 1 else list(idx)
        if len(set(idx)) < 3 or len(set(idx)) != len(idx): return
        pts = [self.verts[i] for i in idx]
        n = newell(pts)
        if np.linalg.norm(n) < 1e-12: return
        if want is not None and float(n @ np.asarray(want, float)) < 0: idx.reverse()
        if isinstance(color, str): color = PAL[color]
        cols = [tuple(c) for c in color] if isinstance(color[0], (tuple, list, np.ndarray)) else [tuple(color)] * len(idx)
        if want is not None and float(n @ np.asarray(want, float)) < 0 and len(cols) == len(idx): cols = cols[::-1]
        self.faces.append(tuple(idx)); self.colors.append(cols); self.smooth.append(smooth); self.tags.append(tag)

    def poly(self, pts, color, tag='concrete', want=None):
        clean = []
        for p in pts:
            if not clean or np.linalg.norm(np.subtract(p, clean[-1])) > 1e-7: clean.append(p)
        if len(clean) > 2 and np.linalg.norm(np.subtract(clean[0], clean[-1])) < 1e-7: clean.pop()
        if len(clean) < 3: return
        self.face([self.vert(p) for p in clean], color, tag, False, want)

    def grid(self, rows, color, tag='concrete', smooth=True, want=None, color_fn=None):
        """rows[i][j] -> xyz; quads between neighbours share vertices. color_fn(i, j) -> colour
        for the quad (i, j) overrides `color`."""
        ids = [[self.vert(p) for p in row] for row in rows]
        flip = None
        for i in range(len(rows) - 1):
            for j in range(len(rows[i]) - 1):
                q = [ids[i][j], ids[i + 1][j], ids[i + 1][j + 1], ids[i][j + 1]]
                pts = [self.verts[k] for k in q]
                if want is not None and flip is None:
                    n = newell(pts)
                    if np.linalg.norm(n) > 1e-12: flip = float(n @ np.asarray(want, float)) < 0
                if flip: q = q[::-1]
                c = color_fn(i, j) if color_fn else color
                self.face(q, c, tag, smooth)
        return ids

    def box(self, lo, hi, color, tag='concrete', bottom=False, faces='all'):
        x0, y0, z0 = lo; x1, y1, z1 = hi
        P = {k: (x1 if 'X' in k else x0, y1 if 'Y' in k else y0, z1 if 'Z' in k else z0)
             for k in ['', 'X', 'Y', 'XY', 'Z', 'XZ', 'YZ', 'XYZ']}
        sides = {'top': (['Z', 'XZ', 'XYZ', 'YZ'], (0, 0, 1)), 'bottom': (['', 'Y', 'XY', 'X'], (0, 0, -1)),
                 '-x': (['', 'Z', 'YZ', 'Y'], (-1, 0, 0)), '+x': (['X', 'XY', 'XYZ', 'XZ'], (1, 0, 0)),
                 '-y': (['', 'X', 'XZ', 'Z'], (0, -1, 0)), '+y': (['Y', 'YZ', 'XYZ', 'XY'], (0, 1, 0))}
        for key, (ks, n) in sides.items():
            if key == 'bottom' and not bottom: continue
            if faces != 'all' and key not in faces: continue
            self.poly([P[k] for k in ks], color, tag, want=n)

    def tube(self, path, r, color, tag='steel', sides=10, caps=True, top_vertex=True, smooth=True):
        """Round tube along a polyline, mitred joints; one ring vertex exactly on top."""
        path = [np.asarray(p, float) for p in path]
        rings = []
        for k, p in enumerate(path):
            if k == 0: d = path[1] - path[0]
            elif k == len(path) - 1: d = path[-1] - path[-2]
            else:
                a = (path[k] - path[k - 1]); b = (path[k + 1] - path[k])
                d = a / np.linalg.norm(a) + b / np.linalg.norm(b)
            d = d / np.linalg.norm(d)
            up = np.array([0, 0, 1.0])
            if abs(d @ up) > .95: up = np.array([1.0, 0, 0])
            u = up - d * (up @ d); u /= np.linalg.norm(u)      # 'top' direction
            v = np.cross(d, u)
            # mitre: scale the ring in the bend plane so the tube keeps its radius
            scale = 1.0
            if 0 < k < len(path) - 1:
                a = (path[k] - path[k - 1]); a /= np.linalg.norm(a)
                scale = 1.0 / max(.2, float(a @ d))
            ring = []
            for i in range(sides):
                t = math.pi / 2 + 2 * math.pi * i / sides if top_vertex else 2 * math.pi * (i + .5) / sides
                off = u * math.sin(t) + v * math.cos(t)
                # stretch the component in the bend plane (along the direction of change)
                if scale != 1.0:
                    a = (path[k] - path[k - 1]); a /= np.linalg.norm(a)
                    bend = a - d * (a @ d)
                    if np.linalg.norm(bend) > 1e-9:
                        bend /= np.linalg.norm(bend); off = off + bend * (off @ bend) * (scale - 1)
                ring.append(p + off * r)
            rings.append(ring)
        ids = [[self.vert(q) for q in ring] for ring in rings]
        for k in range(len(rings) - 1):
            for i in range(sides):
                j = (i + 1) % sides
                q = [ids[k][i], ids[k + 1][i], ids[k + 1][j], ids[k][j]]
                c = (np.mean([self.verts[x] for x in q], axis=0))
                ctr = (path[k] + path[k + 1]) / 2
                self.face(q, color, tag, smooth, want=c - ctr)
        if caps:
            for k, sgn in ((0, -1), (-1, 1)):
                d = path[-1] - path[-2] if k == -1 else path[1] - path[0]
                self.poly(rings[k], color, tag, want=d * sgn)
        return rings

    def lathe(self, centre, profile, color, tag='concrete', sides=10, axis='z', smooth=True):
        """Surface of revolution; profile = [(along, radius), ...] traversed with the solid on
        its right, so the outward normal of a segment is axis*(-d_radius) + radial*d_along."""
        c0 = np.array(centre, float); ax = {'x': 0, 'y': 1, 'z': 2}[axis]
        e = np.zeros(3); e[ax] = 1.0
        b1 = np.zeros(3); b1[(ax + 1) % 3] = 1.0
        b2 = np.cross(e, b1)
        ids = []
        for along, rad in profile:
            if rad <= 1e-12:
                ids.append([self.vert(c0 + e * along)] * sides); continue
            ids.append([self.vert(c0 + e * along + (b1 * math.cos(t) + b2 * math.sin(t)) * rad)
                        for t in 2 * math.pi * (np.arange(sides) + .5) / sides])
        for k in range(len(profile) - 1):
            da = profile[k + 1][0] - profile[k][0]; dr = profile[k + 1][1] - profile[k][1]
            for i in range(sides):
                j = (i + 1) % sides
                t = 2 * math.pi * (i + 1) / sides
                radial = b1 * math.cos(t) + b2 * math.sin(t)
                want = e * (-dr) + radial * da
                self.face([ids[k][i], ids[k + 1][i], ids[k + 1][j], ids[k][j]], color, tag, smooth, want=want)
        return ids

    def fan_polygon(self, pts, anchor, color, tag, want):
        """Star-shaped polygon (every point visible from `anchor`) as a triangle fan."""
        a = self.vert(anchor)
        ids = [self.vert(p) for p in pts]
        for i in range(len(ids) - 1):
            self.face([a, ids[i], ids[i + 1]], color, tag, False, want)

    def merge(self, other):
        base = len(self.verts)
        self.verts += other.verts
        self.faces += [tuple(i + base for i in f) for f in other.faces]
        self.colors += other.colors; self.smooth += other.smooth; self.tags += other.tags

    def translate(self, d):
        self.verts = [tuple(v[i] + d[i] for i in range(3)) for v in self.verts]

    @property
    def triangles(self):
        return sum(len(f) - 2 for f in self.faces)

    # --- normals ----------------------------------------------------------------------
    def corner_normals(self):
        V = np.array(self.verts)
        fn = []
        for f in self.faces:
            n = newell(V[list(f)]); fn.append(n)
        fn = np.array(fn)
        vn = np.zeros_like(V)
        for f, n, sm in zip(self.faces, fn, self.smooth):
            if sm:
                for i in f: vn[i] += n
        out = []
        for f, n, sm in zip(self.faces, fn, self.smooth):
            unit = n / (np.linalg.norm(n) + 1e-12)
            out.append([(vn[i] / (np.linalg.norm(vn[i]) + 1e-12)) if sm else unit for i in f])
        return out


# ------------------------------------------------------------------------------- shading
def _lattice(seed, n=97):
    rng = np.random.default_rng(seed)
    return rng.uniform(-1, 1, (n, n))


_LAT = {k: _lattice(k) for k in range(1, 9)}


def vnoise(x, y, scale, seed):
    """Smooth value noise in [-1, 1], deterministic, periodic at 97*scale metres."""
    L = _LAT[seed]; n = L.shape[0]
    fx = np.asarray(x, float) / scale; fy = np.asarray(y, float) / scale
    ix = np.floor(fx).astype(int); iy = np.floor(fy).astype(int)
    tx = fx - ix; ty = fy - iy
    tx = tx * tx * (3 - 2 * tx); ty = ty * ty * (3 - 2 * ty)
    a = L[iy % n, ix % n]; b = L[iy % n, (ix + 1) % n]; c = L[(iy + 1) % n, ix % n]; d = L[(iy + 1) % n, (ix + 1) % n]
    return (a * (1 - tx) + b * tx) * (1 - ty) + (c * (1 - tx) + d * tx) * ty


def ao_directions(k=16):
    """Cosine-weighted hemisphere directions around +Z (deterministic)."""
    out = []
    golden = math.pi * (3 - math.sqrt(5))
    for i in range(k):
        u = (i + .5) / k
        r = math.sqrt(u); t = golden * i
        out.append((r * math.cos(t), r * math.sin(t), math.sqrt(max(0.0, 1 - u))))
    return np.array(out)


def bake_ao(meshes, occluders, max_dist=1.4, rays=16, skip_tags=()):
    """Ambient occlusion per face corner by ray casting against `occluders` (MeshData list).
    Returns {mesh.name: [[occ per corner] per face]}. Needs Blender's mathutils."""
    from mathutils.bvhtree import BVHTree
    from mathutils import Vector
    verts = []; polys = []
    for m in occluders:
        b = len(verts); verts += m.verts; polys += [tuple(i + b for i in f) for f in m.faces]
    tree = BVHTree.FromPolygons(verts, polys, all_triangles=False, epsilon=0.0)
    D = ao_directions(rays)
    cache = {}; out = {}
    for m in meshes:
        normals = m.corner_normals(); res = []
        for f, ns, tag in zip(m.faces, normals, m.tags):
            row = []
            for i, n in zip(f, ns):
                if tag in skip_tags: row.append(0.0); continue
                p = m.verts[i]
                key = (round(p[0], 3), round(p[1], 3), round(p[2], 3), round(float(n[0]), 2), round(float(n[1]), 2), round(float(n[2]), 2))
                if key not in cache:
                    nz = np.asarray(n, float)
                    t = np.array([1.0, 0, 0]) if abs(nz[0]) < .9 else np.array([0, 1.0, 0])
                    u = np.cross(nz, t); u /= np.linalg.norm(u); v = np.cross(nz, u)
                    o = Vector(p) + Vector(nz * 0.012)
                    occ = 0.0
                    for d in D:
                        w = u * d[0] + v * d[1] + nz * d[2]
                        hit = tree.ray_cast(o, Vector(w), max_dist)
                        if hit[0] is not None:
                            occ += (1 - hit[3] / max_dist) ** 0.6
                    cache[key] = occ / len(D)
                row.append(cache[key])
            res.append(row)
        out[m.name] = res
    return out


def shade(m, ao=None, ao_strength=0.62, seed_offset=0):
    """Final colours: base colour, painterly variation by tag, paint wear, ambient occlusion."""
    V = np.array(m.verts); x, y, z = V[:, 0], V[:, 1], V[:, 2]
    big = vnoise(x + 3.1 * z, y - 2.3 * z, 7.0, 1 + seed_offset % 3)
    mid = vnoise(x - 1.7 * z, y + 1.3 * z, 2.2, 4)
    fine = vnoise(x + 5.3 * z, y + 4.1 * z, 0.7, 5)
    stain = np.maximum(0.0, vnoise(x, y, 4.5, 6) - 0.45) * 0.22
    hue = vnoise(x, y, 11.0, 7)
    wear = np.clip(0.14 + 0.22 * vnoise(x + z, y - z, 1.6, 8) + 0.10 * fine, 0.0, 0.55)
    chip = np.clip(vnoise(x + y + z, y - x, 0.9, 3) - 0.55, 0, 1) * 1.6
    conc = np.array(PAL['concrete']); steel = np.array(PAL['steel'])
    final = []
    for fi, (f, cols, tag) in enumerate(zip(m.faces, m.colors, m.tags)):
        row = []
        for ci, (i, c) in enumerate(zip(f, cols)):
            c = np.array(c, float)
            if tag in CONCRETE_TAGS:
                c = c * (1 + 0.075 * big[i] + 0.045 * mid[i] + 0.02 * fine[i]) * (1 - stain[i])
                c = c + np.array([0.006, 0.0, -0.006]) * hue[i]
            elif tag in ('paint', 'decal'):
                w = wear[i] * (0.4 if tag == 'decal' else 1.0)
                c = c * (1 + 0.05 * big[i] + 0.03 * mid[i])
                c = c * (1 - w) + conc * (1 + 0.05 * mid[i]) * w
            elif tag in ('steel', 'coping'):
                c = c * (1 + 0.14 * mid[i] + 0.08 * fine[i])
            elif tag in ('rail', 'railing', 'pole'):
                c = c * (1 + 0.05 * mid[i]) * (1 - chip[i]) + steel * chip[i]
            if ao is not None:
                c = c * (1 - ao_strength * ao[fi][ci])
            row.append(tuple(np.clip(c, 0, 1)))
        final.append(row)
    return final


# ------------------------------------------------------------------------------- export
def to_object(m, material, colors=None):
    import bpy
    data = bpy.data.meshes.new(m.name)
    data.from_pydata(m.verts, [], m.faces)
    data.update()
    data.materials.append(material)
    smooth = [bool(s) for s in m.smooth]
    data.polygons.foreach_set('use_smooth', smooth)
    uv = data.uv_layers.new(name='UVMap')
    for face in data.polygons:
        drop = max(range(3), key=lambda i: abs(face.normal[i])); axes = [i for i in range(3) if i != drop]
        for li in face.loop_indices:
            co = data.vertices[data.loops[li].vertex_index].co
            uv.data[li].uv = (co[axes[0]], co[axes[1]])
    col = data.color_attributes.new(name='Color', type='FLOAT_COLOR', domain='CORNER')
    colors = colors or m.colors
    k = 0
    for face, row in zip(data.polygons, colors):
        for li, c in zip(face.loop_indices, row):
            # alpha drives M_Village's wind offset: zero keeps everything still
            col.data[li].color = (c[0], c[1], c[2], 0.0)
    data.update()
    obj = bpy.data.objects.new(m.name, data)
    bpy.context.scene.collection.objects.link(obj)
    return obj


def export_fbx(obj, path):
    import bpy
    bpy.ops.object.select_all(action='DESELECT')
    obj.select_set(True); bpy.context.view_layer.objects.active = obj
    bpy.ops.export_scene.fbx(filepath=str(path), use_selection=True, apply_unit_scale=True, apply_scale_options='FBX_SCALE_ALL',
                             axis_forward='-Y', axis_up='Z', object_types={'MESH'}, mesh_smooth_type='FACE', bake_anim=False,
                             use_custom_props=False, colors_type='SRGB')
