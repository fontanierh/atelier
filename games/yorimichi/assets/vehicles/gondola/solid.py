"""Closed-solid mesh core and geometry audits for the gondola pieces (Blender only: bpy and mathutils).

The Mesh core is world/solid_mesh.py, shared with the passenger ferry and its terminals. This module keeps the
gondola palette, timber grain, moving-contact tags and kit-specific audits; it defines no closed primitive copies.

Audits (all fail the build when violated):
- closed(): every edge of every part is shared by exactly two faces; parts wound inward are flipped (reported);
  degenerate faces are counted.
- coplanar_overlaps(): faces of different parts lying in the same plane, facing the same way and overlapping
  (they would z-fight).
- seats(): every registered fitting base is ray-cast onto the bearing parts: no gap over 1 cm, no penetration beyond
  the fitting's declared embedding.
- clearance(): a moving body (the cabin and hanger) placed along its path must not touch the static geometry.
"""
import math
from contextlib import contextmanager

import bpy
from mathutils import Matrix, Vector

# ------------------------------------------------------------------ materials: name -> (sRGB, roughness, metallic)
TIMBER, PLANK, TIMBER_DARK, PLASTER, TILE = 'GD_Timber', 'GD_TimberPlank', 'GD_TimberDark', 'GD_Plaster', 'GD_RoofTile'
SHINGLE, STEEL, IRON, GASKET, GLASS = 'GD_Shingle', 'GD_Steel', 'GD_DarkIron', 'GD_Gasket', 'GD_Glass'
BOLT, CONCRETE, STONE, BASALT, PAVING = 'GD_Bolt', 'GD_Concrete', 'GD_Stone', 'GD_Basalt', 'GD_Paving'
ROPE, BRASS, LAMP, SIGN, POT, SOIL = 'GD_Rope', 'GD_Brass', 'GD_LampGlow', 'GD_SignBoard', 'GD_Terracotta', 'GD_Soil'
DECK, RUBBER, PAINT = 'GD_DeckTimber', 'GD_Rubber', 'GD_SafetyPaint'
PANEL = 'GD_TimberPanel'
MATERIALS = {
    TIMBER: ((222, 168, 102), .55, 0.), PLANK: ((232, 184, 120), .6, 0.), TIMBER_DARK: ((96, 62, 40), .6, 0.),
    PLASTER: ((238, 230, 214), .8, 0.), TILE: ((70, 74, 88), .5, 0.), SHINGLE: ((196, 140, 82), .7, 0.),
    STEEL: ((172, 168, 160), .45, .5), IRON: ((64, 64, 68), .5, .4), GASKET: ((46, 46, 50), .6, 0.),
    GLASS: ((150, 176, 192), .08, 0.), BOLT: ((196, 194, 188), .35, .7), CONCRETE: ((178, 172, 162), .85, 0.),
    STONE: ((132, 128, 122), .85, 0.), BASALT: ((86, 82, 80), .85, 0.), PAVING: ((206, 194, 170), .85, 0.),
    ROPE: ((74, 74, 76), .6, .3), BRASS: ((206, 164, 78), .35, .55), LAMP: ((255, 214, 150), .4, 0.),
    SIGN: ((232, 228, 216), .7, 0.), POT: ((156, 100, 62), .7, 0.), SOIL: ((70, 52, 38), .9, 0.),
    DECK: ((204, 152, 96), .65, 0.), RUBBER: ((40, 40, 42), .8, 0.), PAINT: ((222, 178, 60), .6, 0.),
    PANEL: ((226, 174, 108), .75, 0.),
}
# Materials with a procedural timber texture (textures.py); their UVs are in metres with u along the grain.
TEXTURED = {TIMBER: 'wood_grain', PANEL: 'wood_panel', PLANK: 'wood_grain_light', TIMBER_DARK: 'wood_grain_dark',
            DECK: 'deck_planks', SHINGLE: 'shingle'}


# ------------------------------------------------------------------ shared geometry, kit metadata
import solid_mesh as _shared

signed_area = _shared.signed_area
is_convex = _shared.is_convex
ear_clip = _shared.ear_clip
offset_loop = _shared.offset_loop
resample = _shared.resample
circle = _shared.circle
rect = _shared.rect


def rounded_rect(w, h, r, k=3, c=(0.0, 0.0)):
    return _shared.rounded_rect(w, h, min(r, w / 2 - 1e-4, h / 2 - 1e-4), k=k, c=c)


def _origin():
    import os
    import sys
    f = sys._getframe(1)
    while f is not None and os.path.basename(f.f_code.co_filename) in ('solid.py', 'solid_mesh.py'):
        f = f.f_back
    return f'{os.path.basename(f.f_code.co_filename)}:{f.f_lineno}' if f is not None else '?'


class Mesh(_shared.Mesh):
    """The shared solid builder with this kit's appearance and moving-contact metadata."""
    def __init__(self, name):
        super().__init__(name, default_mat=TIMBER)
        self.tag = None; self.grain = None; self.fgrain = []

    @contextmanager
    def tagged(self, tag):
        old = self.tag; self.tag = tag
        try:
            yield
        finally:
            self.tag = old

    @contextmanager
    def grained(self, direction):
        """Faces built inside carry this grain direction (local frame) for their UVs."""
        old = self.grain; self.grain = direction
        try:
            yield
        finally:
            self.grain = old

    def mirrored(self, axis='y', on=True):
        return super().mirrored(on=on, axis=axis)

    def part(self, verts, faces, mats):
        first = len(self.faces)
        result = super().part(verts, faces, mats)
        self.parts[-1] = (*self.parts[-1], self.tag)
        self.origins[-1] = _origin()
        grain = None if self.grain is None else tuple((self.xf.to_3x3() @ Vector(self.grain)).normalized())
        self.fgrain.extend([grain] * (len(self.faces) - first))
        return result

    def prism(self, outline, z0, z1, side, top=None, bottom=None, bevel=0.0, **options):
        return super().prism(outline, z0, z1, side, top=top, bottom=bottom, bevel=bevel,
                             triangulate_caps=True, **options)

    def beam(self, a, b, w, d, mat, up=None, bevel=0.0):
        axis = Vector(b) - Vector(a)
        reference = up if up is not None else ((0, 0, 1) if abs(axis.normalized().z) < .9 else (1, 0, 0))
        with self.grained((0, 0, 1)):
            return super().beam(a, b, w, d, mat, up=reference, bevel=bevel)

    def tube(self, path, r, mat, n=6, phase=0.0, sx=1.0, sy=1.0):
        return super().tube(path, r, mat, n=n, phase=phase, sx=sx, sy=sy)


# ------------------------------------------------------------------ audits
closed = _shared.closed
coplanar_overlaps = _shared.coplanar_overlaps


def bvh_of(meshes, tags=None, exclude_tags=(), origins=None):
    """A BVH of the meshes' parts (filtered by tag); `origins`, a list, receives each face's part origin and tag."""
    from mathutils.bvhtree import BVHTree
    verts, faces = [], []
    for m in meshes:
        for pi, (start, end, tag) in enumerate(m.parts):
            if (tags is not None and tag not in tags) or tag in exclude_tags:
                continue
            if origins is not None:
                origins += [f'{m.origins[pi] if pi < len(m.origins) else "?"} ({tag})'] * (end - start)
            vmap = {}
            for f in m.faces[start:end]:
                nf = []
                for v in f:
                    if v not in vmap:
                        vmap[v] = len(verts); verts.append(m.verts[v])
                    nf.append(vmap[v])
                faces.append(nf)
    return BVHTree.FromPolygons(verts, faces, epsilon=0.0) if faces else None


def seats(meshes, registry):
    """Ray-cast each registered fitting base down onto the parts it rests on (named by tag). Each base is probed at
    its point and 15 mm round it, so a seam between floor boards does not read as a gap."""
    cache = {}; rows = []
    for label, x, y, z, embed, probe, on in registry:
        key = tuple(sorted(on))
        if key not in cache:
            cache[key] = bvh_of(meshes, tags=set(key))
        bvh = cache[key]; hz = None
        for dx, dy in ((0, 0), (0.015, 0), (-0.015, 0), (0, 0.015), (0, -0.015)):
            hit = bvh.ray_cast(Vector((x + dx, y + dy, z + probe)), Vector((0, 0, -1)), probe + 3.0) if bvh else (None,)
            if hit[0] is not None:
                hz = hit[0].z if hz is None else max(hz, hit[0].z)
        if hz is None:
            rows.append({'label': label, 'at': [x, y, z], 'on': list(key), 'status': 'no bearing surface under base'}); continue
        gap = z - hz; ok = -(embed + 0.005) <= gap <= 0.01
        rows.append({'label': label, 'at': [round(x, 3), round(y, 3), round(z, 3)], 'on': list(key), 'surface_z': round(hz, 4), 'gap_m': round(gap, 4),
                     'embed_allowed_m': embed, 'status': 'ok' if ok else ('floating' if gap > 0.01 else 'sunk')})
    return rows


def transformed(m, M, name=None):
    """A copy of mesh m moved by matrix M (parts and tags kept)."""
    c = Mesh(name or m.name); c.verts = [tuple(M @ Vector(v)) for v in m.verts]; c.faces = list(m.faces)
    c.mats = list(m.mats); c.parts = list(m.parts)
    R3 = M.to_3x3(); c.fgrain = [None if g is None else tuple((R3 @ Vector(g)).normalized()) for g in m.fgrain]
    return c


class Pose:
    """A placement whose meshes take different matrices: the named grip meshes take G (on the rope), every other mesh
    takes C (hanging plumb from the grip's pivot)."""
    def __init__(self, G, C, grip_names):
        self.G, self.C, self.grip_names = G, C, tuple(grip_names)

    def of(self, name):
        return self.G if name in self.grip_names else self.C


def matrix_for(M, name):
    return M.of(name) if isinstance(M, Pose) else M


def rope_clearance(meshes, path, poses, exclude_tags=('jaw', 'clamp'), reach=3.0, step=0.02, near=0.6, only_tags=None):
    """Minimum distance from the rope centreline (a rope.RopePath) to the placed meshes, over poses [(label, pose, s)]
    (s = the grip's arc length on the path, or None to take the nearest). For each pose the rope is sampled every `step` within +-reach of the grip
    and the samples are taken into each mesh's own frame (rigid, so distances hold): nearest-surface distance per
    sample, and a ray along each sample segment, which counts any crossing of a surface as distance 0. Parts tagged
    exclude_tags (the jaws and the clamp body that close on the rope) are left out. Returns the overall minimum with
    where it occurs, and the minimum per pose."""
    from mathutils.bvhtree import BVHTree
    trees = []
    for m in meshes:
        verts, faces, origin = [], [], []
        for pi, (start, end, tag) in enumerate(m.parts):
            if tag in exclude_tags or (only_tags is not None and tag not in only_tags):
                continue
            vmap = {}
            for f in m.faces[start:end]:
                nf = []
                for v in f:
                    if v not in vmap:
                        vmap[v] = len(verts); verts.append(m.verts[v])
                    nf.append(vmap[v])
                faces.append(nf); origin.append(m.origins[pi] if pi < len(m.origins) else '?')
        if faces:
            trees.append((m.name, BVHTree.FromPolygons(verts, faces, epsilon=0.0), origin))
    best = {'distance_m': 1e9}; per_pose = []; per_mesh = {}
    for label, pose, s0 in poses:
        if s0 is None:                    # the grip's place on this path (its frame origin is on the grip line)
            G = pose.G if isinstance(pose, Pose) else pose
            s0 = path.nearest(tuple(G.translation))[1]
        n = max(2, int(2 * reach / step)); ss = [min(path.length, max(0.0, s0 - reach + 2 * reach * k / n)) for k in range(n + 1)]
        world = [Vector(path.rope_point(s_)) for s_ in ss]
        pose_min = 1e9
        for name, tree, origin in trees:
            Minv = matrix_for(pose, name).inverted(); loc = [Minv @ w for w in world]
            for k, q in enumerate(loc):
                hit = tree.find_nearest(q, 3.0)
                if hit[0] is not None:
                    d = hit[3]
                    if d < pose_min:
                        pose_min = d
                    if d < per_mesh.get(name, (1e9,))[0]:
                        per_mesh[name] = (d, label, origin[hit[2]])
                    if d < best['distance_m']:
                        best = {'distance_m': d, 'at': label, 'mesh': name, 'part': origin[hit[2]], 'rope_point': [round(c, 3) for c in world[k]]}
                if k:
                    seg = q - loc[k - 1]; L = seg.length
                    if L > 1e-9:
                        hit = tree.ray_cast(loc[k - 1], seg / L, L)
                        if hit[0] is not None:
                            pose_min = 0.0; per_mesh[name] = (0.0, label, origin[hit[2]])
                            if best['distance_m'] > 0.0:
                                best = {'distance_m': 0.0, 'at': label, 'mesh': name, 'part': origin[hit[2]], 'rope_point': [round(c, 3) for c in world[k]],
                                        'crossing': True}
        per_pose.append((label, round(pose_min, 4)))
    if best['distance_m'] >= 1e9:
        best['distance_m'] = None
        return best, per_pose
    best['distance_m'] = round(best['distance_m'], 4)
    best['per_mesh'] = {k: {'distance_m': round(v[0], 4), 'at': v[1], 'part': v[2]} for k, v in sorted(per_mesh.items())}
    return best, per_pose


def rope_contact_parts(meshes, path, poses, tags, reach=0.4, step=0.01):
    """Per part, the signed minimum distance from the rope axis (checks.part_minimum: negative inside the part) at
    each pose [(label, pose, s)]: one row per part tagged `tags`, so each jaw half, each sheave and the bullwheel
    groove is gated on its own (checks.part_verdicts). The rope is sampled every `step` within +-reach of s (the whole
    path when reach is None) and taken into each mesh's own frame."""
    import checks
    parts = []; count = {}
    for m in meshes:
        for pi, (start, end, tag) in enumerate(m.parts):
            if tag in tags:
                k = count[tag] = count.get(tag, 0) + 1
                parts.append((m.name, tag, f'{tag} {k} ({m.origins[pi] if pi < len(m.origins) else "?"})',
                              checks.triangles(m.verts, m.faces[start:end])))
    rows = [{'mesh': n, 'tag': t, 'part': o, 'per_pose': []} for n, t, o, _ in parts]
    for label, pose, s0 in poses:
        if reach is None:
            ss = [path.length * k / max(1, int(path.length / step)) for k in range(int(path.length / step) + 1)]
        else:
            if s0 is None:
                G = pose.G if isinstance(pose, Pose) else pose
                s0 = path.nearest(tuple(G.translation))[1]
            n = max(2, int(2 * reach / step)); ss = [min(path.length, max(0.0, s0 - reach + 2 * reach * k / n)) for k in range(n + 1)]
        world = [Vector(path.rope_point(s_)) for s_ in ss]
        for row, (name, tag, origin, tris) in zip(rows, parts):
            Minv = matrix_for(pose, name).inverted()
            d = checks.part_minimum(tris, [tuple(Minv @ w) for w in world], path.r)
            row['per_pose'].append(None if d is None else round(d, 5))
    return rows


def clearance(static, movers, placements, exclude_tags=(), mover_exclude=()):
    """Place the mover meshes at each placement (a matrix or a Pose); count triangle contacts with the static meshes
    (static parts tagged exclude_tags and mover parts tagged mover_exclude are left out)."""
    so = []; sb = bvh_of(static, exclude_tags=exclude_tags, origins=so); hits = []
    for label, M in placements:
        mb = bvh_of([transformed(m, matrix_for(M, m.name)) for m in movers], exclude_tags=mover_exclude)
        pairs = sb.overlap(mb) if (sb and mb) else []
        if pairs:
            hits.append({'at': label, 'contacts': len(pairs), 'station_parts': sorted({so[i] for i, _ in pairs})[:4]})
    return hits


# ------------------------------------------------------------------ Blender objects and export
def make_materials(textures=None):
    """Principled materials; the timber ones sample their procedural texture through the UV map (metres)."""
    mats = {}
    for name, (rgb, rough, metal) in MATERIALS.items():
        lin = tuple(((c / 255) / 12.92) if c / 255 <= 0.04045 else (((c / 255) + 0.055) / 1.055) ** 2.4 for c in rgb)
        mat = bpy.data.materials.get(name) or bpy.data.materials.new(name)
        try:
            mat.use_nodes = True
        except Exception:
            pass
        nt = mat.node_tree; bsdf = nt.nodes.get('Principled BSDF')
        bsdf.inputs['Base Color'].default_value = (*lin, 1)
        bsdf.inputs['Roughness'].default_value = rough
        bsdf.inputs['Metallic'].default_value = metal
        if name == LAMP:
            bsdf.inputs['Emission Color'].default_value = (*lin, 1); bsdf.inputs['Emission Strength'].default_value = 1.2
        tex = TEXTURED.get(name)
        if textures and tex and (tex, 'color') in textures:
            uv = nt.nodes.new('ShaderNodeTexCoord')
            ci = nt.nodes.new('ShaderNodeTexImage'); ci.image = bpy.data.images.load(str(textures[(tex, 'color')]), check_existing=True)
            ri = nt.nodes.new('ShaderNodeTexImage'); ri.image = bpy.data.images.load(str(textures[(tex, 'rough')]), check_existing=True)
            ri.image.colorspace_settings.name = 'Non-Color'
            for node in (ci, ri):
                nt.links.new(uv.outputs['UV'], node.inputs['Vector'])
            nt.links.new(ci.outputs['Color'], bsdf.inputs['Base Color']); nt.links.new(ri.outputs['Color'], bsdf.inputs['Roughness'])
        mat.diffuse_color = (*lin, 1)
        mats[name] = mat
    return mats


def to_object(m, mats, sharp_degrees=38, collection=None):
    """A Blender mesh object. UVs are in metres: u runs along the part's grain (or, by default, horizontally on
    upright faces and along x on level faces) and v across it, so timber textures tile at true scale."""
    names = sorted(set(m.mats), key=list(MATERIALS).index)
    data = bpy.data.meshes.new(m.name)
    data.from_pydata(m.verts, [], [list(f) for f in m.faces]); data.update()
    for n in names:
        data.materials.append(mats[n])
    index = {n: i for i, n in enumerate(names)}
    data.polygons.foreach_set('material_index', [index[n] for n in m.mats])
    data.polygons.foreach_set('use_smooth', [True] * len(data.polygons))
    data.set_sharp_from_angle(angle=math.radians(sharp_degrees))
    uv = data.uv_layers.new(name='UVMap'); Z = Vector((0, 0, 1))
    for face in data.polygons:
        n = Vector(face.normal); g = m.fgrain[face.index] if face.index < len(m.fgrain) else None
        U = None
        if g is not None:
            gv = Vector(g); U = gv - n * gv.dot(n)
            U = U.normalized() if U.length > 0.2 else None
        if U is None:
            if abs(n.z) > 0.7:
                U = Vector((1, 0, 0)) - n * n.x; U = U.normalized() if U.length > 1e-6 else Vector((0, 1, 0))
            else:
                U = Z.cross(n).normalized()
        V = n.cross(U)
        for li in face.loop_indices:
            co = data.vertices[data.loops[li].vertex_index].co
            uv.data[li].uv = (co.dot(U), co.dot(V))
    data.update()
    obj = bpy.data.objects.new(m.name, data); (collection or bpy.context.collection).objects.link(obj)
    return obj, names


def export_fbx(objs, path, smooth='EDGE'):
    bpy.ops.object.select_all(action='DESELECT')
    for o in objs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]
    bpy.ops.export_scene.fbx(filepath=str(path), use_selection=True, apply_unit_scale=True, apply_scale_options='FBX_SCALE_ALL',
                             axis_forward='-Y', axis_up='Z', object_types={'MESH'}, mesh_smooth_type=smooth, bake_anim=False,
                             use_custom_props=False)


# ------------------------------------------------------------------ collision proxies (convex prisms)
def proxy(name, poly, z0, z1):
    """A convex collision prism: plan polygon with bottom/top heights (constants or per-corner callables)."""
    pts = [tuple(p) for p in poly]
    if signed_area(pts) < 0:
        pts = pts[::-1]
    f0 = z0 if callable(z0) else (lambda x, y, c=z0: c)
    f1 = z1 if callable(z1) else (lambda x, y, c=z1: c)
    return {'name': name, 'poly': [[round(x, 4), round(y, 4)] for x, y in pts],
            'z0': [round(f0(x, y), 4) for x, y in pts], 'z1': [round(f1(x, y), 4) for x, y in pts]}


def proxy_box(name, cx, cy, sx, sy, z0, z1, yaw=0.0):
    c, s_ = math.cos(math.radians(yaw)), math.sin(math.radians(yaw))
    poly = [(cx + c * u - s_ * v, cy + s_ * u + c * v) for u, v in ((-sx / 2, -sy / 2), (sx / 2, -sy / 2), (sx / 2, sy / 2), (-sx / 2, sy / 2))]
    return proxy(name, poly, z0, z1)


def proxy_strip(name, a, b, t, z0, z1):
    d = Vector((b[0] - a[0], b[1] - a[1])); n = Vector((-d.y, d.x)).normalized() * (t / 2)
    poly = [(a[0] - n.x, a[1] - n.y), (b[0] - n.x, b[1] - n.y), (b[0] + n.x, b[1] + n.y), (a[0] + n.x, a[1] + n.y)]
    return proxy(name, poly, z0, z1)


def proxy_transform(pr, M):
    """Move a proxy by a matrix that keeps z up (translation + yaw)."""
    pts = []; z0 = []; z1 = []
    for (x, y), a, b in zip(pr['poly'], pr['z0'], pr['z1']):
        p0 = M @ Vector((x, y, a)); p1 = M @ Vector((x, y, b)); pts.append((p0.x, p0.y)); z0.append(p0.z); z1.append(p1.z)
    if signed_area(pts) < 0:
        pts, z0, z1 = pts[::-1], z0[::-1], z1[::-1]
    return {'name': pr['name'], 'poly': [[round(x, 4), round(y, 4)] for x, y in pts], 'z0': [round(v, 4) for v in z0], 'z1': [round(v, 4) for v in z1]}


def proxy_mesh(proxies, name='proxies'):
    """The proxies as a Mesh (for clearance checks)."""
    m = Mesh(name)
    for pr in proxies:
        n = len(pr['poly'])
        verts = [(x, y, z) for (x, y), z in zip(pr['poly'], pr['z0'])] + [(x, y, z) for (x, y), z in zip(pr['poly'], pr['z1'])]
        faces = [list(reversed(range(n))), list(range(n, 2 * n))] + [[k, (k + 1) % n, n + (k + 1) % n, n + k] for k in range(n)]
        m.part(verts, faces, CONCRETE)
    return m


def export_collision(proxies, path, base):
    """One FBX: a tiny placeholder render mesh plus one UCX_ convex hull per proxy (Unreal custom collision)."""
    objs = []
    me = bpy.data.meshes.new(base); s_ = 0.05
    me.from_pydata([(x * s_, y * s_, z * s_) for x in (-1, 1) for y in (-1, 1) for z in (-1, 1)], [],
                   [[0, 1, 3, 2], [4, 6, 7, 5], [0, 4, 5, 1], [2, 3, 7, 6], [0, 2, 6, 4], [1, 5, 7, 3]])
    objs.append(bpy.data.objects.new(base, me))
    for i, pr in enumerate(proxies):
        n = len(pr['poly'])
        verts = [(x, y, z) for (x, y), z in zip(pr['poly'], pr['z0'])] + [(x, y, z) for (x, y), z in zip(pr['poly'], pr['z1'])]
        faces = [list(reversed(range(n))), list(range(n, 2 * n))] + [[k, (k + 1) % n, n + (k + 1) % n, n + k] for k in range(n)]
        cm = bpy.data.meshes.new(f'UCX_{base}_{i:03d}'); cm.from_pydata(verts, [], faces); cm.update()
        objs.append(bpy.data.objects.new(cm.name, cm))
    for o in objs:
        bpy.context.collection.objects.link(o)
    export_fbx(objs, path, smooth='FACE')
    for o in objs:
        data = o.data; bpy.data.objects.remove(o); bpy.data.meshes.remove(data)
    return len(proxies)
