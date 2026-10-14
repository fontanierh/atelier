"""Mesh primitives, materials and FBX export shared by independent asset generators."""
import os
import math
import bpy
import numpy as np
from mathutils import Vector, Matrix, Euler
import yori

TEX = str(yori.TEXTURES)
OUTDIR = str(yori.OUT / 'assets')
MATS = {}
LEAF_CROPS = {}


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


def materials(names=None):
    """Load only the palette this asset reads; leaf cropping consumes the image's alpha pixels."""
    from material_specs import MATERIALS
    for name in MATERIALS if names is None else names:
        mat(name, **MATERIALS[name])


class Mesh:
    """Accumulates verts/faces/uvs/materials/custom normals for one exported object."""
    def __init__(self, name):
        self.name = name; self.v = []; self.f = []; self.fm = []; self.uv = []; self.mats = []; self.nrm = {}
        self.smooth = []; self.col = []

    def mi(self, m):
        if m not in self.mats: self.mats.append(m)
        return self.mats.index(m)

    def begin_canopy(self,count):
        """LOD subclasses allocate cards independently in every crown lobe."""

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

    def card(self, center, size, yaw, tilt, m, cell, normal, roll=0.0, col=1.0, col_bottom=None, crop=(0.0, 0.0, 1.0, 1.0)):
        """vertical-ish quad centred at `center`, width/height size, rotated yaw about Z then tilted (pitch); crop
        (left, bottom, right, top, as fractions of the card and its atlas cell) keeps part of it at the same texel size"""
        w, h = size; s0, t0, s1, t1 = crop
        R = Euler((math.radians(tilt), math.radians(roll), yaw), "XYZ").to_matrix()
        corners = ((s0, t0), (s1, t0), (s1, t1), (s0, t1))
        pts = [Vector(center) + R @ Vector(((s - 0.5) * w, 0, (t - 0.5) * h)) for s, t in corners]
        u0, v0 = (cell % 2) * 0.5, 0.5 - (cell // 2) * 0.5
        uvs = [(u0 + 0.5 * s, v0 + 0.5 * t) for s, t in corners]
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


def leaf_crop(m, cell):
    """The part of a leaf atlas cell any mip can draw: (left, bottom, right, top) as fractions of the cell. Each mip
    is a simple average with its alpha scaled to keep the full texture's coverage at the 0.4 clip (setup_project's
    leaf import); a texel past the clip there reaches one texel further by bilinear filtering. Mips down to 8 texels
    a cell count, so a card trimmed to this box clips the same pixels as the whole card."""
    if m.name not in LEAF_CROPS:
        nodes = [n for n in m.node_tree.nodes if n.type == "TEX_IMAGE" and n.image] if m.use_nodes else []
        crops = [(0.0, 0.0, 1.0, 1.0)] * 4
        if nodes:
            image = nodes[0].image; W, H = image.size
            pixels = np.empty(W * H * 4, np.float32); image.pixels.foreach_get(pixels)
            mips = [pixels.reshape(H, W, 4)[..., 3].astype(np.float64)]      # rows bottom-up, as UV v
            while mips[-1].shape[0] > 16:
                a = mips[-1]; mips.append(a.reshape(a.shape[0] // 2, 2, a.shape[1] // 2, 2).mean((1, 3)))
            covered = (mips[0] >= 0.4).mean(); scales = [1.0]
            for a in mips[1:]:
                low, high = 0.01, 100.0
                for _ in range(40):
                    k = (low * high) ** 0.5
                    if (a * k >= 0.4).mean() < covered: low = k
                    else: high = k
                scales.append(high)
            crops = []
            for c in range(4):
                lo, hi = np.ones(2), np.zeros(2)
                for a, k in zip(mips, scales):
                    n = a.shape[0] // 2; row = (1 - c // 2) * n
                    ys, xs = np.nonzero(a[row:row + n, (c % 2) * n:(c % 2 + 1) * n] * k >= 0.4)
                    if not len(xs): continue
                    lo = np.minimum(lo, (np.array([xs.min(), ys.min()]) - 0.5) / n)
                    hi = np.maximum(hi, (np.array([xs.max(), ys.max()]) + 1.5) / n)
                lo, hi = np.clip(lo, 0, 1), np.clip(hi, 0, 1)
                crops.append((float(lo[0]), float(lo[1]), float(hi[0]), float(hi[1])) if (hi > lo).all() else (0.0, 0.0, 1.0, 1.0))
        LEAF_CROPS[m.name] = crops
    return LEAF_CROPS[m.name][cell]


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
        # The card keeps only the part of its cell the leaves can cover: the depth and shadow passes skip the
        # clipped-away margin, and every pixel that shows is the one the whole card drew.
        cell = rng.randrange(4); crop = leaf_crop(m, cell); s0, t0, s1, t1 = crop
        corners = []
        for (ux, uz) in ((s0, t0), (s1, t0), (s1, t1), (s0, t1)):
            q = pos + R @ Vector(((ux - 0.5) * w, 0, (uz - 0.5) * w))
            nrm = (q - nc); nrm.z += vertical_bias * max(rx, rz); corners.append(nrm.normalized())
        shell = 0.22 + 0.78 * min(1.0, p.length)          # interior leaves get darkened by the material
        mesh.card(pos, (w, w), yaw, tilt, m, cell, corners, roll=roll, col=(1.0, shell), crop=crop)


def export(ob, name, *, portable=False):
    from contextlib import nullcontext
    from atelier.blender.fbx import stable_export
    os.makedirs(OUTDIR, exist_ok=True)
    bpy.ops.object.select_all(action="DESELECT"); ob.select_set(True); bpy.context.view_layer.objects.active = ob
    hull=None
    if 'trunk_collision' in ob:
        values=ob['trunk_collision'];radius=values[0];a=Vector(values[1:4]);b=Vector(values[4:7])
        bpy.ops.mesh.primitive_cube_add(size=1,location=(a+b)*.5)
        hull=bpy.context.object;hull.name='UCX_'+name+'_00';hull.scale=(radius*2,radius*2,(b-a).length+.2)
        hull.rotation_euler=(b-a).to_track_quat('Z','Y').to_euler()
        bpy.ops.object.transform_apply(location=False,rotation=True,scale=True)
        ob.select_set(True);bpy.context.view_layer.objects.active=ob
    path = os.path.join(OUTDIR, f"{name}.fbx")
    # Geometry already consumed texture alpha. Native import assigns materials by slot name;
    # the FBX needs neither texture files nor the exporting checkout's image paths.
    images = []
    if portable:
        for material in ob.data.materials:
            for node in material.node_tree.nodes:
                if node.type == 'TEX_IMAGE' and node.image:
                    images.append((node, node.image))
                    node.image = None
    try:
        with stable_export() if portable else nullcontext():
            bpy.ops.export_scene.fbx(
                filepath=path, use_selection=True, apply_unit_scale=True, apply_scale_options="FBX_SCALE_ALL",
                axis_forward="-Y", axis_up="Z", object_types={"MESH"}, mesh_smooth_type="FACE", bake_anim=False,
                path_mode="STRIP" if portable else "COPY", embed_textures=False, use_tspace=False, colors_type="SRGB")
    finally:
        for node, image in images:
            node.image = image
        if hull:
            bpy.data.objects.remove(hull, do_unlink=True)
    print(f"exported {name}: {len(ob.data.polygons)} faces")
