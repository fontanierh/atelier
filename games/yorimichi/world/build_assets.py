"""Painterly Japan-countryside props (Blender headless) -> build/yorimichi/assets/<Name>.fbx (+ check render)

    blender -b --python japan/build_assets.py -- [--render]

Metres, Z up; the FBX exporter converts to Unreal centimetres. Every canopy is a handful of
alpha cards whose custom normals point away from the canopy centre so it shades as one soft
mass. Grass card normals point straight up so tufts shade like the ground under them.
Material slot names are what the Unreal setup script keys on: LeafBroad, LeafCedar, LeafPine,
LeafOchre, Grass, Bark, Concrete, Paint, Stone, Vermilion, Plaster, Tile, Wood, Feather,
FeatherDark, Sky, Metal.
"""
import sys as _sys; from pathlib import Path as _Path; _sys.path.insert(0, str(_Path(__file__).resolve().parent)); import yori  # noqa: E402,F401
import sys, os, math, random, argparse
import bpy, bmesh
import numpy as np
from mathutils import Vector, Matrix, Euler

TEX = str(yori.TEXTURES)
OUTDIR = str(yori.OUT / "assets")
os.makedirs(OUTDIR, exist_ok=True)
MATS = {}


def parse():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    ap = argparse.ArgumentParser()
    ap.add_argument("--render", action="store_true")
    ap.add_argument("--only", default="")
    return ap.parse_args(argv)


def mat(name, color=(0.5, 0.5, 0.5), texture=None, alpha=False):
    if name in MATS:
        return MATS[name]
    m = bpy.data.materials.new(name); m.use_nodes = True
    nt = m.node_tree; b = nt.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (*color, 1); b.inputs["Roughness"].default_value = 1.0
    b.inputs["Specular IOR Level"].default_value = 0.0
    if texture:
        t = nt.nodes.new("ShaderNodeTexImage"); t.image = bpy.data.images.load(os.path.join(TEX, texture)); t.location = (-400, 200)
        nt.links.new(t.outputs["Color"], b.inputs["Base Color"])
        if alpha:
            nt.links.new(t.outputs["Alpha"], b.inputs["Alpha"])
            m.surface_render_method = "DITHERED"
            m.use_backface_culling = False
    MATS[name] = m
    return m


def materials():
    mat("LeafBroad", texture="T_leaf_broad.png", alpha=True)
    mat("LeafCedar", texture="T_leaf_cedar.png", alpha=True)
    mat("LeafPine", texture="T_leaf_pine.png", alpha=True)
    mat("LeafOchre", texture="T_leaf_ochre.png", alpha=True)
    mat("LeafMaple", texture="T_leaf_maple.png", alpha=True)
    mat("LeafGinkgo", texture="T_leaf_ginkgo.png", alpha=True)
    mat("LeafSmall", texture="T_leaf_small.png", alpha=True)
    mat("Litter", texture="T_litter.png", alpha=True)
    mat("Flower", texture="T_flower.png", alpha=True)
    mat("LeafOchreSmall", texture="T_leaf_ochre_small.png", alpha=True)
    mat("LeafMapleLo", texture="T_leaf_maple_lo.png", alpha=True); mat("LeafGinkgoLo", texture="T_leaf_ginkgo_lo.png", alpha=True); mat("LeafBroadLo", texture="T_leaf_broad_lo.png", alpha=True)
    mat("RoofTile", (0.32, 0.34, 0.38), texture="T_rooftile.jpg"); mat("FarForest", (0.35, 0.45, 0.22), texture="T_farforest.jpg")
    mat("Rock", (0.48, 0.45, 0.40)); mat("Lattice", (0.16, 0.12, 0.09)); mat("Moss", (0.36, 0.44, 0.20))
    mat("Grass", texture="T_grass.png", alpha=True)
    mat("Bark", (0.20, 0.15, 0.12), texture="T_bark.jpg")
    mat("Concrete", (0.62, 0.61, 0.59), texture="T_concrete.jpg")
    mat("Paint", (0.90, 0.90, 0.88))
    mat("Stone", (0.55, 0.55, 0.52))
    mat("Vermilion", (0.78, 0.18, 0.10))
    mat("Plaster", (0.86, 0.83, 0.76))
    mat("Tile", (0.25, 0.27, 0.30))
    mat("Wood", (0.30, 0.20, 0.13))
    mat("Feather", (0.95, 0.95, 0.93))
    mat("FeatherDark", (0.15, 0.15, 0.17))
    mat("Metal", (0.35, 0.35, 0.37))
    mat("Sky", texture="T_sky.png")


class Mesh:
    """Accumulates verts/faces/uvs/materials/custom normals for one exported object."""
    def __init__(self, name):
        self.name = name; self.v = []; self.f = []; self.fm = []; self.uv = []; self.mats = []; self.nrm = {}
        self.smooth = []; self.col = []

    def mi(self, m):
        if m not in self.mats: self.mats.append(m)
        return self.mats.index(m)

    def quad(self, pts, m, uvs=None, normal=None, smooth=False, col=None):
        i0 = len(self.v); self.v += [Vector(p) for p in pts]
        self.f.append([i0 + k for k in range(len(pts))]); self.fm.append(self.mi(m)); self.smooth.append(smooth)
        self.uv.append(uvs or [(0, 0)] * len(pts))
        self.col.append([(c if isinstance(c, tuple) else (c, 1.0)) for c in col] if col is not None else [(0.0, 1.0)] * len(pts))
        if normal is not None:
            for k in range(len(pts)):
                self.nrm[i0 + k] = Vector(normal[k] if isinstance(normal, list) else normal)

    def tube(self, p0, p1, r0, r1, m, n=8, uvscale=(1, 1), cap=False, twist=0.0):
        """tapered tube from p0 to p1 with radii r0/r1; smooth-shaded, UVs wrap around"""
        p0, p1 = Vector(p0), Vector(p1); d = (p1 - p0); L = d.length; dn = d.normalized()
        up = Vector((0, 0, 1)) if abs(dn.z) < 0.99 else Vector((1, 0, 0))
        x = up.cross(dn).normalized(); y = dn.cross(x)
        ring0, ring1 = [], []
        for i in range(n):
            a = 2 * math.pi * i / n + twist
            ring0.append(p0 + (x * math.cos(a) + y * math.sin(a)) * r0)
            ring1.append(p1 + (x * math.cos(a) + y * math.sin(a)) * r1)
        for i in range(n):
            j = (i + 1) % n
            u0, u1 = i / n * uvscale[0], (i + 1) / n * uvscale[0]
            self.quad([ring0[i], ring0[j], ring1[j], ring1[i]], m, [(u0, 0), (u1, 0), (u1, L * uvscale[1]), (u0, L * uvscale[1])], smooth=True)
        if cap:
            self.quad(list(reversed(ring0)), m, smooth=False); self.quad(ring1, m, smooth=False)

    def box(self, c, s, m, rot=None):
        cx, cy, cz = c; sx, sy, sz = s
        R = rot or Matrix.Identity(3)
        def P(x, y, z): return Vector(c) + R @ Vector((x * sx / 2, y * sy / 2, z * sz / 2))
        v = [P(-1, -1, -1), P(1, -1, -1), P(1, 1, -1), P(-1, 1, -1), P(-1, -1, 1), P(1, -1, 1), P(1, 1, 1), P(-1, 1, 1)]
        for f in [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)]:
            self.quad([v[i] for i in f], m, [(0, 0), (1, 0), (1, 1), (0, 1)])

    def card(self, center, size, yaw, tilt, m, cell, normal, roll=0.0, col=1.0, col_bottom=None):
        """vertical-ish quad centred at `center`, width/height size, rotated yaw about Z then tilted (pitch)"""
        w, h = size
        R = Euler((math.radians(tilt), math.radians(roll), yaw), "XYZ").to_matrix()
        pts = [Vector(center) + R @ Vector((-w / 2, 0, -h / 2)), Vector(center) + R @ Vector((w / 2, 0, -h / 2)),
               Vector(center) + R @ Vector((w / 2, 0, h / 2)), Vector(center) + R @ Vector((-w / 2, 0, h / 2))]
        u0, v0 = (cell % 2) * 0.5, 0.5 - (cell // 2) * 0.5
        uvs = [(u0, v0), (u0 + 0.5, v0), (u0 + 0.5, v0 + 0.5), (u0, v0 + 0.5)]
        cb = col if col_bottom is None else col_bottom
        self.quad(pts, m, uvs, normal=normal, col=[cb, cb, col, col])

    def rock(self, center, size, m, rng, moss=None):
        """low-poly boulder: jittered icosphere-ish ring stack, flat shaded"""
        cx, cy, cz = center; sx, sy, sz = size
        rings = []
        for j in range(4):
            t = (j + 0.5) / 4; z = cz + (t - 0.15) * sz; rr = math.sin(math.pi * min(1.0, t * 1.1)) * 0.5 + 0.2
            ring = [Vector((cx + math.cos(a) * sx * rr * rng.uniform(0.8, 1.2), cy + math.sin(a) * sy * rr * rng.uniform(0.8, 1.2), z + rng.uniform(-0.05, 0.05) * sz)) for a in [2 * math.pi * i / 7 for i in range(7)]]
            rings.append(ring)
        for j in range(3):
            for i in range(7):
                a, b = rings[j][i], rings[j][(i + 1) % 7]; c, d = rings[j + 1][(i + 1) % 7], rings[j + 1][i]
                self.quad([a, b, c, d], (moss if (moss and j == 2) else m))
        top = Vector((cx, cy, cz + sz * 0.9))
        for i in range(7):
            self.quad([rings[3][i], rings[3][(i + 1) % 7], top], moss or m)

    def build(self):
        me = bpy.data.meshes.new(self.name)
        me.from_pydata([tuple(p) for p in self.v], [], self.f); me.update()
        for m in self.mats: me.materials.append(m)
        uv = me.uv_layers.new(name="UVMap").data
        ca = me.color_attributes.new(name="Col", type="BYTE_COLOR", domain="CORNER")
        for pi, p in enumerate(me.polygons):
            p.material_index = self.fm[pi]; p.use_smooth = self.smooth[pi]
            for k, li in enumerate(p.loop_indices):
                uv[li].uv = self.uv[pi][k]
                w, g = self.col[pi][k]; ca.data[li].color = (w, g, w, 1.0)
        me.color_attributes.active_color = ca; me.color_attributes.render_color_index = 0
        ob = bpy.data.objects.new(self.name, me); bpy.context.scene.collection.objects.link(ob)
        if self.nrm:
            # custom normals: cards use the canopy direction, everything else keeps its own
            me.calc_normals_split() if hasattr(me, "calc_normals_split") else None
            loops = []
            for p in me.polygons:
                for li in p.loop_indices:
                    vi = me.loops[li].vertex_index
                    loops.append(tuple(self.nrm[vi].normalized()) if vi in self.nrm else tuple(p.normal if not p.use_smooth else me.vertices[vi].normal))
            me.normals_split_custom_set(loops)
        return ob


# ------------------------------------------------------------------ vegetation
def canopy(mesh, center, radii, n_clusters, card_size, m, rng, normal_center=None, tilt_range=(-25, 25), vertical_bias=0.0):
    cx, cy, cz = center; rx, ry, rz = radii
    nc = Vector(normal_center or center)
    for i in range(n_clusters):
        # cluster points: uniform in the ellipsoid, slightly favouring the shell
        while True:
            p = Vector((rng.uniform(-1, 1), rng.uniform(-1, 1), rng.uniform(-1, 1)))
            if p.length <= 1.0: break
        p = p * 0.85 + p.normalized() * 0.15 * p.length
        pos = Vector((cx + p.x * rx, cy + p.y * ry, cz + p.z * rz))
        w = card_size * rng.uniform(0.85, 1.15)
        for k in range(2):
            yaw = rng.uniform(0, math.pi) + k * math.pi / 2
            tilt = rng.uniform(*tilt_range)
            cell = rng.randrange(4)
            # normal: away from the canopy centre, blended toward straight up
            corners = []
            R = Euler((math.radians(tilt), 0, yaw), "XYZ").to_matrix()
            for (ux, uz) in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
                q = pos + R @ Vector((ux * w / 2, 0, uz * w / 2))
                nrm = (q - nc); nrm.z += vertical_bias * max(rx, rz)
                corners.append(nrm.normalized())
            mesh.card(pos, (w, w), yaw, tilt, m, cell, corners, col=(0.6, 0.55 + 0.45 * min(1.0, p.length)))


def leaf_canopy(mesh, center, radii, n, size, m, rng, normal_center=None, vertical_bias=0.3, shell=0.35):
    """many small leaf cards filling an ellipsoid, denser on the shell; normals from the canopy centre"""
    cx, cy, cz = center; rx, ry, rz = radii; nc = Vector(normal_center or center)
    for i in range(n):
        while True:
            p = Vector((rng.uniform(-1, 1), rng.uniform(-1, 1), rng.uniform(-1, 1)))
            if p.length <= 1.0: break
        if p.length < 0.5 and rng.random() < shell: p = p.normalized() * rng.uniform(0.6, 1.0)
        pos = Vector((cx + p.x * rx, cy + p.y * ry, cz + p.z * rz))
        w = size * rng.uniform(0.8, 1.2)
        yaw = rng.uniform(0, 2 * math.pi); tilt = rng.uniform(-70, 70); roll = rng.uniform(-40, 40)
        R = Euler((math.radians(tilt), math.radians(roll), yaw), "XYZ").to_matrix()
        corners = []
        for (ux, uz) in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
            q = pos + R @ Vector((ux * w / 2, 0, uz * w / 2))
            nrm = (q - nc); nrm.z += vertical_bias * max(rx, rz); corners.append(nrm.normalized())
        shell = 0.22 + 0.78 * min(1.0, p.length)          # interior leaves get darkened by the material
        mesh.card(pos, (w, w), yaw, tilt, m, rng.randrange(4), corners, roll=roll, col=(1.0, shell))


def tree_maple(name, seed, height=6.5, spread=6.0):
    """momiji: short trunk, wide layered canopy of small red leaves"""
    rng = random.Random(seed); M = Mesh(name); bark = MATS["Bark"]; leaf = MATS["LeafMaple"]
    top = Vector((rng.uniform(-0.2, 0.2), rng.uniform(-0.2, 0.2), height * 0.42))
    M.tube((0, 0, -0.2), top, 0.22, 0.13, bark, n=8, uvscale=(1, 0.5))
    for i in range(5):
        a = 2 * math.pi * i / 5 + rng.uniform(-0.3, 0.3)
        end = top + Vector((math.cos(a) * spread * 0.42, math.sin(a) * spread * 0.42, height * 0.35))
        M.tube(top - Vector((0, 0, 0.2)), end, 0.10, 0.03, bark, n=6, uvscale=(1, 0.5))
        mid = top + (end - top) * 0.55
        M.tube(mid, mid + Vector((math.cos(a + 0.9) * 1.2, math.sin(a + 0.9) * 1.2, 0.6)), 0.05, 0.02, bark, n=5)
    leaf_canopy(M, (0, 0, height * 0.74), (spread * 0.5, spread * 0.5, height * 0.28), 420, 0.70, leaf, rng, normal_center=(0, 0, height * 0.5), vertical_bias=0.4)
    return M.build()


def tree_ginkgo(name, seed, height=9.0):
    rng = random.Random(seed); M = Mesh(name); bark = MATS["Bark"]; leaf = MATS["LeafGinkgo"]
    top = Vector((0, 0, height * 0.55))
    M.tube((0, 0, -0.2), Vector((0, 0, height * 0.9)), 0.24, 0.06, bark, n=8, uvscale=(1, 0.5))
    for i in range(6):
        a = 2 * math.pi * i / 6 + rng.uniform(-0.3, 0.3); z = height * rng.uniform(0.35, 0.75)
        M.tube(Vector((0, 0, z)), Vector((math.cos(a) * 1.4, math.sin(a) * 1.4, z + 1.2)), 0.07, 0.02, bark, n=5)
    leaf_canopy(M, (0, 0, height * 0.66), (2.1, 2.1, height * 0.34), 380, 0.72, leaf, rng, normal_center=(0, 0, height * 0.45), vertical_bias=0.3)
    return M.build()


def tree_lo(name, seed, kind, height, spread):
    """distant version: a few dozen big painted-cluster cards (used beyond 90 m from the road)"""
    rng = random.Random(seed); M = Mesh(name); bark = MATS["Bark"]
    leaf = MATS[{"maple": "LeafMapleLo", "ginkgo": "LeafGinkgoLo", "broad": "LeafBroadLo"}[kind]]
    M.tube((0, 0, -0.2), (0, 0, height * 0.55), 0.22, 0.10, bark, n=6, uvscale=(1, 0.5))
    # a few dozen mid-size cards of the soft painted-cluster atlases: smooth crowns from a distance
    leaf_canopy(M, (0, 0, height * 0.72), (spread * 0.5, spread * 0.5, height * 0.28), 40, 1.2, leaf, rng, normal_center=(0, 0, height * 0.45), vertical_bias=0.3)
    return M.build()


def bush_flower(name, seed, r=1.1):
    rng = random.Random(seed); M = Mesh(name)
    leaf_canopy(M, (0, 0, r * 0.7), (r, r, r * 0.7), 120, 0.55, MATS["Flower"], rng, normal_center=(0, 0, r * 0.25), vertical_bias=0.35)
    return M.build()


def rock(name, seed, size):
    rng = random.Random(seed); M = Mesh(name)
    M.rock((0, 0, 0), size, MATS["Rock"], rng, moss=MATS["Moss"])
    return M.build()


def tree_broad(name, seed, height=8.0, spread=4.2):
    rng = random.Random(seed); M = Mesh(name)
    bark = MATS["Bark"]; leaf = MATS["LeafBroad"]
    top = Vector((rng.uniform(-0.3, 0.3), rng.uniform(-0.3, 0.3), height * 0.55))
    M.tube((0, 0, -0.2), top, 0.28, 0.16, bark, n=8, uvscale=(1, 0.5))
    for i in range(4):
        a = 2 * math.pi * i / 4 + rng.uniform(-0.4, 0.4)
        end = top + Vector((math.cos(a) * spread * 0.4, math.sin(a) * spread * 0.4, height * 0.28))
        M.tube(top - Vector((0, 0, 0.3)), end, 0.14, 0.05, bark, n=6, uvscale=(1, 0.5))
    leaf_canopy(M, (0, 0, height * 0.72), (spread * 0.55, spread * 0.55, height * 0.32), 440, 0.75, MATS["LeafSmall"], rng,
                normal_center=(0, 0, height * 0.55), vertical_bias=0.35)
    return M.build()


def tree_pine(name, seed, height=14.0):
    """akamatsu: tall bare trunk with a slight lean, a few horizontal branches, feathery needle pads on each"""
    rng = random.Random(seed); M = Mesh(name)
    bark = MATS["Bark"]; leaf = MATS["LeafPine"]
    lean = Vector((rng.uniform(-0.9, 0.9), rng.uniform(-0.9, 0.9), 0))
    pts = [Vector((0, 0, -0.2)), Vector((0, 0, height * 0.5)) + lean * 0.4, Vector((0, 0, height)) + lean]
    M.tube(pts[0], pts[1], 0.26, 0.17, bark, n=8, uvscale=(1, 0.4)); M.tube(pts[1], pts[2], 0.17, 0.05, bark, n=8, uvscale=(1, 0.4))
    tiers = 6
    for i in range(tiers):
        t = i / (tiers - 1)
        z = height * (0.5 + 0.48 * t); r = 2.6 * (1 - t) ** 0.8 + 0.6
        c = Vector((0, 0, z)) + lean * (z / height)
        a0 = rng.uniform(0, math.pi)
        for k in range(2 if i < tiers - 1 else 1):
            a = a0 + k * 2.6 + rng.uniform(-0.4, 0.4)
            end = c + Vector((math.cos(a) * r * 0.85, math.sin(a) * r * 0.85, 0.15))
            M.tube(c, end, 0.07, 0.02, bark, n=5)
            # a feathery pad at the branch tip: several small horizontal cards
            for j in range(16):
                q = end + Vector((rng.uniform(-0.5, 0.5) * r, rng.uniform(-0.5, 0.5) * r, rng.uniform(-0.25, 0.45)))
                w = r * rng.uniform(0.3, 0.5)
                yaw = rng.uniform(0, math.pi); tilt = rng.uniform(38, 82)
                Rm = Euler((math.radians(tilt), 0, yaw), "XYZ").to_matrix()
                corners = []
                for (ux, uz) in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
                    qq = q + Rm @ Vector((ux * w / 2, 0, uz * w / 2)); nrm = qq - (c - Vector((0, 0, r * 0.9))); corners.append(nrm.normalized())
                M.card(q, (w, w), yaw, tilt, leaf, rng.randrange(4), corners, col=(0.6, 0.6 + 0.4 * rng.random()))
        # a few vertical cards so the pad is not paper-thin from the side
        canopy(M, tuple(c), (r * 0.5, r * 0.5, height * 0.035), 2, r * 0.8, leaf, rng, normal_center=(c.x, c.y, c.z - r), tilt_range=(-15, 15), vertical_bias=0.4)
    return M.build()


def tree_cedar(name, seed, height=16.0):
    rng = random.Random(seed); M = Mesh(name)
    bark = MATS["Bark"]; leaf = MATS["LeafCedar"]
    M.tube((0, 0, -0.2), (0, 0, height * 0.95), 0.32, 0.05, bark, n=8, uvscale=(1, 0.4))
    levels = 8
    for i in range(levels):
        t = i / (levels - 1)
        z = height * (0.22 + 0.76 * t)
        r = 2.6 * (1 - t) + 0.45
        canopy(M, (0, 0, z), (r * 0.75, r * 0.75, height * 0.07), 10 if i < levels - 1 else 3, r * 1.5, leaf, rng,
               normal_center=(0, 0, z - r * 0.9), tilt_range=(-25, 25), vertical_bias=0.35)
    return M.build()


def bush(name, seed, m_name, r=1.4):
    """small-leaf bush mass (green or ochre), dark inside like the trees"""
    rng = random.Random(seed); M = Mesh(name)
    leaf = MATS[{"LeafBroad": "LeafSmall", "LeafOchre": "LeafOchreSmall"}.get(m_name, m_name)]
    leaf_canopy(M, (0, 0, r * 0.65), (r, r, r * 0.7), int(110 * r), 0.48, leaf, rng, normal_center=(0, 0, r * 0.2), vertical_bias=0.35)
    return M.build()


def grass_tuft(name, seed, lod=0):
    """Eight curved ribbons: 40 triangles, no intersecting rectangular cards."""
    rng = random.Random(seed); M = Mesh(name)
    # Most of each clump is green, with a few muted straw blades.
    for k in range(8):
        angle = k * math.tau / 8 + rng.uniform(-.4, .4)
        direction = Vector((math.cos(angle), math.sin(angle), 0))
        sideways = Vector((-math.sin(angle), math.cos(angle), 0))
        root = direction * rng.uniform(.06, .20) + Vector((0, 0, -.025))
        height, width, curl = rng.uniform(.32, .53), rng.uniform(.055, .095), rng.uniform(.14, .27)
        cell = rng.choices(range(4), weights=[4, 4, 1, 1])[0]
        u0, v0 = cell % 2 * .5, .5 - cell // 2 * .5
        levels = []
        for t in ((0., .48, .82), (0., .58), (0.,))[lod]:
            centre = root + direction * curl * t * t + Vector((0, 0, height * t))
            half = sideways * width * (1 - t ** 1.7) * .5
            levels.append((centre - half, centre + half, t))
        def uv(u, t): return (u0 + .5 * (.02 + .96 * u), v0 + .5 * (.02 + .96 * t))
        for (a, b, t), (d, c, q) in zip(levels, levels[1:]):
            M.quad([a, b, c, d], MATS['Grass'], [uv(0,t), uv(1,t), uv(1,q), uv(0,q)],
                   normal=(0,0,1), col=[(t*t, .6+.4*t)]*2 + [(q*q, .6+.4*q)]*2)
        a, b, t = levels[-1]
        tip = root + direction * curl + Vector((0, 0, height))
        M.quad([a, b, tip], MATS['Grass'], [uv(0,t),uv(1,t),uv(.5,1)],
               normal=(0,0,1), col=[(t*t,.6+.4*t)]*2+[(1.,1.)])
    return M.build()


# ------------------------------------------------------------------ roadside
def pole(name, lamp=False):
    M = Mesh(name); c = MATS["Concrete"]; k = MATS["Metal"]
    M.tube((0, 0, -0.5), (0, 0, 11.0), 0.17, 0.11, c, n=10, uvscale=(1, 0.3), cap=True)
    for z, w in ((10.3, 2.4), (9.4, 2.0)):
        M.box((0, 0, z), (0.12, w, 0.12), MATS["Wood"])
        M.box((0, 0, z + 0.08), (0.16, w + 0.1, 0.05), k)
        for sgn in (-1, 1):                                                       # diagonal braces under the crossarm
            M.tube((0, sgn * w * 0.4, z - 0.06), (0, 0, z - 0.7), 0.025, 0.025, k, n=4)
        for y in (-w / 2 + 0.15, 0.0 if z > 10 else None, w / 2 - 0.15):
            if y is None: continue
            M.tube((0, y, z + 0.06), (0, y, z + 0.28), 0.05, 0.04, MATS["Paint"], n=6, cap=True)
    if lamp:
        M.tube((0, 0, 7.4), (0, 1.5, 7.9), 0.04, 0.035, k, n=6)
        M.box((0, 1.5, 7.9), (0.26, 0.6, 0.16), k)
    return M.build()


def guardrail(name, length=2.0):
    """one 2 m section of white W-beam guardrail with its post at the origin; rail runs along +X"""
    M = Mesh(name); p = MATS["Paint"]
    M.tube((0, 0, -0.3), (0, 0, 0.72), 0.05, 0.05, p, n=6, cap=True)
    prof = [(0.0, 0.85), (0.06, 0.80), (0.0, 0.72), (0.06, 0.64), (0.0, 0.58)]     # (y, z) W profile
    x0, x1 = -length / 2, length / 2
    for (y0, z0), (y1, z1) in zip(prof[:-1], prof[1:]):
        M.quad([(x0, y0, z0), (x1, y0, z0), (x1, y1, z1), (x0, y1, z1)], p, smooth=True)
        M.quad([(x0, y1, z1), (x1, y1, z1), (x1, y0, z0), (x0, y0, z0)], p, smooth=True)
    return M.build()


def lantern(name):
    M = Mesh(name); s = MATS["Stone"]
    # A buried stone footing supports every corner on the island's sloping path.
    # Keep the pedestal top at .24 m and the lantern body at its existing height.
    M.box((0, 0, -0.08), (0.7, 0.7, 0.64), s); M.box((0, 0, 0.30), (0.45, 0.45, 0.12), s)
    M.tube((0, 0, 0.36), (0, 0, 0.95), 0.10, 0.09, s, n=8, cap=True)
    M.box((0, 0, 1.02), (0.44, 0.44, 0.10), s); M.box((0, 0, 1.24), (0.34, 0.34, 0.34), s)
    M.box((0, 0, 1.48), (0.62, 0.62, 0.12), s); M.tube((0, 0, 1.54), (0, 0, 1.72), 0.22, 0.05, s, n=4, cap=True)
    return M.build()


def torii(name):
    M = Mesh(name); v = MATS["Vermilion"]; k = MATS["Tile"]
    for y in (-1.6, 1.6):
        M.tube((0, y, -0.3), (0, y, 4.6), 0.17, 0.14, v, n=10, cap=True)
    M.box((0, 0, 4.75), (0.30, 4.6, 0.30), v)            # kasagi
    M.box((0, 0, 5.02), (0.36, 4.9, 0.20), k)            # dark top
    M.box((0, 0, 3.55), (0.22, 4.0, 0.24), v)            # nuki
    M.box((0, 0, 4.15), (0.22, 0.34, 0.6), v)            # gakuzuka
    return M.build()


def leaf_mesh(name):
    """one small leaf card for the wind-blown leaf system (origin at the centre, lying in the XY plane)"""
    M = Mesh(name); rng = random.Random(77)
    M.card((0, 0, 0), (0.24, 0.28), 0, 90, MATS["LeafMaple"], 1, [(0, 0, 1)] * 4, col=0.0)
    return M.build()


def litter(name):
    M = Mesh(name)
    M.quad([(-0.5, -0.5, 0.02), (0.5, -0.5, 0.02), (0.5, 0.5, 0.02), (-0.5, 0.5, 0.02)], MATS["Litter"], [(0, 0), (1, 0), (1, 1), (0, 1)], normal=[(0, 0, 1)] * 4)
    return M.build()


def sky_dome(name):
    bm = bmesh.new(); bmesh.ops.create_uvsphere(bm, u_segments=48, v_segments=24, radius=1.0)
    for f in bm.faces: f.normal_flip()
    me = bpy.data.meshes.new(name); bm.to_mesh(me); bm.free()
    ob = bpy.data.objects.new(name, me); bpy.context.scene.collection.objects.link(ob)
    me.materials.append(MATS["Sky"])
    uv = me.uv_layers.new(name="UVMap").data
    for p in me.polygons:
        p.use_smooth = True
        us = []
        for li in p.loop_indices:
            co = me.vertices[me.loops[li].vertex_index].co
            u = 0.5 + math.atan2(co.y, co.x) / (2 * math.pi)
            v = 0.5 + math.asin(max(-1, min(1, co.z))) / math.pi
            us.append([u, v])
        # fix the seam wrap
        if max(x[0] for x in us) - min(x[0] for x in us) > 0.5:
            for x in us:
                if x[0] < 0.5: x[0] += 1.0
        for k, li in enumerate(p.loop_indices):
            uv[li].uv = us[k]
    return ob


def bird_parts():
    """body (with head/tail) and two wings as separate objects; wing origins at the shoulders"""
    f = MATS["Feather"]; fd = MATS["FeatherDark"]
    B = Mesh("BirdBody")
    B.tube((-0.28, 0, 0), (0.22, 0, 0.02), 0.06, 0.09, f, n=8, cap=True)
    B.tube((0.22, 0, 0.02), (0.36, 0, 0.06), 0.09, 0.05, f, n=8, cap=True)
    B.tube((0.36, 0, 0.06), (0.44, 0, 0.09), 0.05, 0.045, f, n=8, cap=True)
    B.tube((0.44, 0, 0.09), (0.54, 0, 0.08), 0.045, 0.005, MATS["Vermilion"], n=6, cap=True)   # beak
    B.quad([(-0.28, -0.06, 0.0), (-0.28, 0.06, 0.0), (-0.50, 0.12, 0.02), (-0.50, -0.12, 0.02)], f)
    B.quad([(-0.50, -0.12, 0.02), (-0.50, 0.12, 0.02), (-0.28, 0.06, 0.0), (-0.28, -0.06, 0.0)], f)
    body = B.build()
    wings = []
    for s, nm in ((1, "BirdWingL"), (-1, "BirdWingR")):
        W = Mesh(nm)
        pts = [(0.12, 0, 0), (-0.14, 0, 0), (-0.20, s * 0.42, 0.0), (0.10, s * 0.42, 0.0)]
        W.quad(pts if s > 0 else list(reversed(pts)), f); W.quad(list(reversed(pts)) if s > 0 else pts, f)
        tip = [(0.10, s * 0.42, 0.0), (-0.20, s * 0.42, 0.0), (-0.30, s * 0.80, 0.02), (0.02, s * 0.80, 0.02)]
        W.quad(tip if s > 0 else list(reversed(tip)), fd); W.quad(list(reversed(tip)) if s > 0 else tip, fd)
        wings.append(W.build())
    return [body] + wings


# ------------------------------------------------------------------ export + check
def export(ob, name):
    bpy.ops.object.select_all(action="DESELECT"); ob.select_set(True); bpy.context.view_layer.objects.active = ob
    path = os.path.join(OUTDIR, f"{name}.fbx")
    bpy.ops.export_scene.fbx(filepath=path, use_selection=True, apply_unit_scale=True, apply_scale_options="FBX_SCALE_ALL",
                             axis_forward="-Y", axis_up="Z", object_types={"MESH"}, mesh_smooth_type="FACE", bake_anim=False,
                             path_mode="COPY", embed_textures=False, use_tspace=False, colors_type="SRGB")
    print(f"exported {name}: {len(ob.data.polygons)} faces")


def main():
    a = parse()
    bpy.ops.wm.read_factory_settings(use_empty=True)
    materials()
    builders = {
        "Tree_Broad_A": lambda: tree_broad("Tree_Broad_A", 1, 8.5, 4.6), "Tree_Broad_B": lambda: tree_broad("Tree_Broad_B", 2, 7.0, 3.8),
        "Tree_Broad_C": lambda: tree_broad("Tree_Broad_C", 3, 10.0, 5.4),
        "Tree_Maple_A": lambda: tree_maple("Tree_Maple_A", 21, 6.5, 6.0), "Tree_Maple_B": lambda: tree_maple("Tree_Maple_B", 22, 5.2, 4.6),
        "Tree_Ginkgo": lambda: tree_ginkgo("Tree_Ginkgo", 23, 9.0), "Leaf": lambda: leaf_mesh("Leaf"), "Litter": lambda: litter("Litter"),
        "Tree_Maple_lo": lambda: tree_lo("Tree_Maple_lo", 31, "maple", 6.5, 6.0), "Tree_Ginkgo_lo": lambda: tree_lo("Tree_Ginkgo_lo", 32, "ginkgo", 9.0, 4.2),
        "Tree_Broad_lo": lambda: tree_lo("Tree_Broad_lo", 33, "broad", 8.5, 5.0),
        "Bush_Flower_A": lambda: bush_flower("Bush_Flower_A", 34, 1.2), "Bush_Flower_B": lambda: bush_flower("Bush_Flower_B", 35, 0.9),
        "Rock_A": lambda: rock("Rock_A", 36, (1.8, 1.4, 1.0)), "Rock_B": lambda: rock("Rock_B", 37, (1.1, 0.9, 0.7)), "Rock_C": lambda: rock("Rock_C", 38, (2.6, 2.0, 1.3)),
        "Tree_Pine_A": lambda: tree_pine("Tree_Pine_A", 4, 13.0), "Tree_Pine_B": lambda: tree_pine("Tree_Pine_B", 5, 11.0),
        "Tree_Cedar_A": lambda: tree_cedar("Tree_Cedar_A", 6, 16.0), "Tree_Cedar_B": lambda: tree_cedar("Tree_Cedar_B", 7, 13.0),
        "Bush_Green_A": lambda: bush("Bush_Green_A", 8, "LeafBroad", 1.4), "Bush_Green_B": lambda: bush("Bush_Green_B", 9, "LeafBroad", 1.0),
        "Bush_Ochre_A": lambda: bush("Bush_Ochre_A", 10, "LeafOchre", 1.5), "Bush_Ochre_B": lambda: bush("Bush_Ochre_B", 11, "LeafOchre", 1.1),
        "Grass_A": lambda: grass_tuft("Grass_A", 12), "Grass_B": lambda: grass_tuft("Grass_B", 13),
        "Pole": lambda: pole("Pole"), "Pole_Lamp": lambda: pole("Pole_Lamp", lamp=True),
        "Guardrail": lambda: guardrail("Guardrail"), "Lantern": lambda: lantern("Lantern"), "Torii": lambda: torii("Torii"),
        "SkyDome": lambda: sky_dome("SkyDome"),
    }
    built = {}
    for name, fn in builders.items():
        if a.only and name not in a.only.split(","): continue
        ob = fn(); built[name] = ob; export(ob, name)
    for ob in bird_parts():
        built[ob.name] = ob; export(ob, ob.name)
    if a.render:
        # one tile per asset (EEVEE, alpha-hashed foliage), composited into renders/japan/assets.jpg
        sc = bpy.context.scene; sc.render.engine = "BLENDER_EEVEE"; sc.render.resolution_x, sc.render.resolution_y = 420, 520
        w = bpy.data.worlds.new("W"); sc.world = w; w.use_nodes = True
        w.node_tree.nodes["Background"].inputs[0].default_value = (0.62, 0.72, 0.85, 1); w.node_tree.nodes["Background"].inputs[1].default_value = 1.2
        sun = bpy.data.lights.new("Sun", "SUN"); sun.energy = 3.0; sun.angle = math.radians(6); so = bpy.data.objects.new("Sun", sun); sc.collection.objects.link(so)
        so.rotation_euler = (math.radians(50), 0, math.radians(-30))
        cam = bpy.data.cameras.new("Cam"); co = bpy.data.objects.new("Cam", cam); sc.collection.objects.link(co); sc.camera = co
        cam.lens = 45; sc.view_settings.view_transform = "Standard"
        tiles = []
        tmpdir = str(yori.REVIEW / "tiles"); os.makedirs(tmpdir, exist_ok=True)
        for name, ob in built.items():
            if name == "SkyDome": continue
            for o in built.values(): o.hide_render = (o is not ob)
            d = max(ob.dimensions.x, ob.dimensions.y, ob.dimensions.z)
            c = Vector((0, 0, ob.dimensions.z * 0.5 + (ob.bound_box[0][2])))
            dist = d * 1.9 + 0.5
            co.location = c + Vector((-0.55, -1.0, 0.45)).normalized() * dist
            co.rotation_euler = (c - Vector(co.location)).to_track_quat("-Z", "Y").to_euler()
            sc.render.filepath = os.path.join(tmpdir, f"{name}.png"); bpy.ops.render.render(write_still=True)
            tiles.append((name, sc.render.filepath))
        print("tiles", tmpdir)


if __name__ == "__main__":
    main()
