"""Belmonte train coach shells (Blender, headless): `atelier build yorimichi world.belmonte_train`.

Builds the locomotive and the tender (their own sections below) and the coaches from train/layout.py: the shared envelope (side walls with real window and door openings, end
walls, floor deck, roof, ceiling, underframe, two bogies, buffers, couplers, gangways, steps), each coach's own
partitions, sliding and hinged doors, lining panels, window frames and glazing, plus furniture reservations, seat
markers, mounts and simple walkable collision. Furniture is separate Tripo Studio assets placed from placements.json;
the coaches and vans also get their luggage racks, bulbs, curtains and (second class) menu board on their mounts
(fittings.py).

Outputs in build/yorimichi/belmonte-train/: per coach a clean .blend, SM_BT_<Coach>_LOD0/1/2.glb (glTF, metres,
Blender's standard Y-up export), SM_BT_<Coach>_Collision.glb, <coach>-blockout.glb (reservations and markers) and
<coach>-placements.json; textures/; manifest.json with sizes, checksums, triangle counts and the checks.
Object origins: the coach at its centre on the top of the rail; bogies at their pivot; wheelsets at their axle;
doors at their hinge (hinged) or at the bottom centre of the closed leaf (sliding).
"""
import sys as _sys; from pathlib import Path as _Path; _sys.path.insert(0, str(_Path(__file__).resolve().parents[1])); import yori  # noqa: E402,F401
import hashlib
import json
import math

import bmesh
import bpy
import numpy as np
from mathutils import Vector

from train import collision as CO
from train import fittings as FT
from train import furniture as FU
from train import layout as L
from train import parts as PT
from train import textures as T

OUT = yori.OUT / 'belmonte-train'
TEX = OUT / 'textures'

# name: (base colour, metallic, roughness, texture, uv metres per tile, alpha)
MATERIALS = {
    'livery-blue': (T.LIVERY_BLUE, 0., .32, None, 1., 1.),
    'livery-ivory': ((1, 1, 1), 0., .38, 'T_BT_Ivory', (2., 1.), 1.),
    'livery-panel': ((1, 1, 1), 0., .32, 'T_BT_BluePanel', 0., 1.),       # one lined panel per face span (panel_uv)
    'roof': ((1, 1, 1), 0., .55, 'T_BT_Roof', 3.15, 1.),
    'end-dark': ((.018, .019, .022), 0., .5, None, 1., 1.),
    'brass': ((.80, .56, .24), 1., .28, None, 1., 1.),
    'walnut': ((1, 1, 1), 0., .42, 'T_BT_Walnut', .9, 1.),
    'panel-tall': ((1, 1, 1), 0., .35, 'T_BT_PanelTall', 0., 1.),
    'panel-wide': ((1, 1, 1), 0., .35, 'T_BT_PanelWide', 0., 1.),
    'carpet-burgundy': ((1, 1, 1), 0., .9, 'T_BT_CarpetBurgundy', 1.2, 1.),
    'carpet-emerald': ((1, 1, 1), 0., .9, 'T_BT_CarpetEmerald', 1.2, 1.),
    'tile': ((1, 1, 1), 0., .35, 'T_BT_Tiles', 1.2, 1.),
    'parquet': ((1, 1, 1), 0., .45, 'T_BT_Walnut', .45, 1.),
    'ceiling': ((.80, .71, .54), 0., .6, None, 1., 1.),
    'service': ((.62, .62, .60), .2, .4, None, 1., 1.),
    'undercarriage': ((1, 1, 1), .3, .6, 'T_BT_Underframe', 1.2, 1.),
    'steel': ((.30, .30, .31), 1., .45, None, 1., 1.),
    'zinc': ((.66, .67, .68), .85, .38, None, 1., 1.),            # the galley's and pantry's worktops
    'rubber': ((.012, .012, .013), 0., .8, None, 1., 1.),
    'glass': ((.92, .95, .96), 0., .04, None, 1., .12),
    'glass-frosted': ((.88, .90, .90), 0., .5, None, 1., .80),
    'glass-dark': ((.05, .07, .09), 0., .1, None, 1., 1.),
    'window-interior': ((1, 1, 1), 0., .25, None, 1., 1.),       # the LOD2 windows' interior atlas (parts.py)
    'shadow-proxy': ((.5, .5, .5), 0., 1., None, 1., 1.),
    'lamp-red': ((.85, .04, .02), 0., .2, None, 1., 1.),
    'coal': ((.008, .008, .009), .1, .75, None, 1., 1.),
    'iron-black': ((.014, .014, .015), .55, .42, None, 1., 1.),
    'loco-black': ((.011, .011, .012), 0., .26, None, 1., 1.),      # the engine and tender: black, brass and red lining
    'lining-red': ((.42, .025, .02), 0., .35, None, 1., 1.),
    'smokebox-door': ((1, 1, 1) if T.has('smokebox-door.jpg') else (.014, .014, .015), .4, .45, 'T_BT_SmokeboxDoor' if T.has('smokebox-door.jpg') else None, 0., 1.),
    'fire': ((1., .35, .05), 0., .9, None, 1., 1.),
    'lamp-white': ((1., .93, .78), 0., .2, None, 1., 1.),
    'crest': ((1, 1, 1), .8, .3, 'T_BT_Crest', 0., 1.),
    'livery-blue-worn': ((1, 1, 1), 0., .55, 'T_BT_BlueWorn', 2.0, 1.),
    'livery-ivory-worn': ((1, 1, 1), 0., .58, 'T_BT_IvoryWorn', (2., 1.), 1.),
    'livery-panel-worn': ((1, 1, 1), 0., .55, 'T_BT_BluePanelWorn', 0., 1.),
    'roof-worn': ((1, 1, 1), .2, .8, 'T_BT_RoofWorn', 3.15, 1.),
    'end-dark-worn': ((1, 1, 1), .2, .8, 'T_BT_DarkWorn', 2.0, 1.),
    'brass-dull': ((.36, .30, .17), .6, .65, None, 1., 1.),
    'paint-peel': ((1, 1, 1), 0., .85, 'T_BT_PaintPeel', (3.6, 1.2), 1.),
    'lino': ((1, 1, 1), 0., .75, 'T_BT_Lino', 2.4, 1.),
    'tiles-grimy': ((1, 1, 1), 0., .5, 'T_BT_TilesGrimy', (1.1, 1.0), 1.),
    'decal-two': ((1, 1, 1), 0., .6, 'T_BT_Two', 0., 1.),
    'glass-grimy': ((.70, .68, .55), 0., .3, None, 1., .35),
    'ceiling-dingy': ((.50, .43, .31), 0., .85, None, 1., 1.),
    'cord': ((.24, .19, .12), 0., .9, None, 1., 1.),                  # coach fittings (fittings.py)
    'cord-burgundy': ((.20, .025, .03), 0., .7, None, 1., 1.),
    'cord-emerald': ((.010, .060, .022), 0., .7, None, 1., 1.),
    'velvet-burgundy': ((.26, .03, .04), 0., .85, None, 1., 1.),
    'velvet-emerald': ((.008, .075, .025), 0., .85, None, 1., 1.),
    'curtain-canvas': ((.30, .27, .19), 0., .95, None, 1., 1.),       # the vans' faded blinds
    'enamel-white': ((.78, .76, .70), 0., .35, None, 1., 1.),
    'enamel-grimy': ((.55, .50, .40), 0., .55, None, 1., 1.),
    'enamel-soot': ((.09, .08, .07), 0., .8, None, 1., 1.),
    'enamel-cream': ((.66, .58, .42), 0., .55, None, 1., 1.),
    'curtain-fabric': ((1, 1, 1) if T.has('curtain-fabric.jpg') else (.34, .24, .09), 0., .95,     # faded mustard until the swatch
                       'T_BT_CurtainFabric' if T.has('curtain-fabric.jpg') else None, 0., 1.),
    'menu-board': ((1, 1, 1) if T.has('menu-board.jpg') else (.02, .02, .02), 0., .7, 'T_BT_MenuBoard' if T.has('menu-board.jpg') else None, 0., 1.),
    'reservation': ((.85, .28, .04), 0., .8, None, 1., .60),
    'reservation-service': ((.08, .25, .75), 0., .8, None, 1., .50),
    'gauge': ((.9, .1, .3), 0., .8, None, 1., 1.),
}
MAT = {}


def make_textures():
    TEX.mkdir(parents=True, exist_ok=True)
    images = {}
    for name, fn in T.ALL.items():
        px = fn()
        h, w, _ = px.shape
        img = bpy.data.images.new(name, w, h, alpha=True)
        img.pixels.foreach_set(px.astype(np.float32).ravel())
        ext, fmt = ('jpg', 'JPEG') if name in T.JPEG else ('png', 'PNG')
        img.filepath_raw = str(TEX / f'{name}.{ext}'); img.file_format = fmt
        if fmt == 'JPEG':
            bpy.context.scene.render.image_settings.quality = 90
        img.save()
        images[name] = img
    return images


def make_materials(images):
    for name, (color, metal, rough, tex, _, alpha) in MATERIALS.items():
        m = bpy.data.materials.new(f'M_BT_{"".join(p.title() for p in name.split("-"))}')
        nodes = m.node_tree.nodes
        bsdf = nodes['Principled BSDF']
        bsdf.inputs['Base Color'].default_value = (*color, 1)
        bsdf.inputs['Metallic'].default_value = metal
        bsdf.inputs['Roughness'].default_value = rough
        if name in ('fire', 'lamp-white'):
            bsdf.inputs['Emission Color'].default_value = (*color, 1)
            bsdf.inputs['Emission Strength'].default_value = 4. if name == 'fire' else 2.
        if name.startswith('livery') or name == 'loco-black':
            bsdf.inputs['Coat Weight'].default_value = .6 if not name.endswith('-worn') else .2
        if tex:
            node = nodes.new('ShaderNodeTexImage'); node.image = images[tex]
            m.node_tree.links.new(node.outputs['Color'], bsdf.inputs['Base Color'])
            if name in ('crest', 'decal-two'):
                m.node_tree.links.new(node.outputs['Alpha'], bsdf.inputs['Alpha'])
                m.surface_render_method = 'DITHERED'
        if alpha < 1:
            bsdf.inputs['Alpha'].default_value = alpha
            m.surface_render_method = 'BLENDED'
            m.use_backface_culling = False
        m.diffuse_color = (*color, alpha) if not tex else (.3, .15, .07, 1)
        MAT[name] = m


# --- mesh building ------------------------------------------------------------------------------------------------
class M:
    """Polygons with a material and optional UVs; every polygon has its own vertices until weld()."""

    def __init__(self):
        self.faces = []        # (points, material, uv or None)

    def poly(self, pts, mat, uv=None, normal=None):
        pts = [tuple(map(float, p)) for p in pts]
        if normal is not None:
            n = _newell(pts)
            if n.dot(Vector(normal)) < 0:
                pts = pts[::-1]
                uv = uv[::-1] if uv else None
        self.faces.append((pts, mat, uv))

    def box(self, x0, x1, y0, y1, z0, z1, mat, front=None, front_mat=None):
        """A closed box. front = (axis, sign): that face gets UVs 0..1 (as seen from outside) and front_mat."""
        x0, x1 = sorted((x0, x1)); y0, y1 = sorted((y0, y1)); z0, z1 = sorted((z0, z1))
        P = lambda i, j, k: ((x0, x1)[i], (y0, y1)[j], (z0, z1)[k])
        quads = {('x', -1): [P(0, 1, 0), P(0, 0, 0), P(0, 0, 1), P(0, 1, 1)], ('x', 1): [P(1, 0, 0), P(1, 1, 0), P(1, 1, 1), P(1, 0, 1)],
                 ('y', -1): [P(0, 0, 0), P(1, 0, 0), P(1, 0, 1), P(0, 0, 1)], ('y', 1): [P(1, 1, 0), P(0, 1, 0), P(0, 1, 1), P(1, 1, 1)],
                 ('z', -1): [P(0, 1, 0), P(1, 1, 0), P(1, 0, 0), P(0, 0, 0)], ('z', 1): [P(0, 0, 1), P(1, 0, 1), P(1, 1, 1), P(0, 1, 1)]}
        for key, q in quads.items():
            if front == key:
                self.faces.append((q, front_mat or mat, [(0, 0), (1, 0), (1, 1), (0, 1)]))
            else:
                self.faces.append((q, mat, None if front is None else [(0, 0), (.01, 0), (.01, .01), (0, .01)]))

    def prism(self, pts2, axis, a0, a1, mat, cap_mat=None):
        """Extrude a convex polygon given in the plane of the two other axes ((y, z) for axis x, (x, z) for y)."""
        def P(u, v, a):
            return (a, u, v) if axis == 'x' else (u, a, v) if axis == 'y' else (u, v, a)
        n = len(pts2)
        self.faces.append(([P(u, v, a0) for u, v in pts2], cap_mat or mat, None))
        self.faces.append(([P(u, v, a1) for u, v in pts2[::-1]], cap_mat or mat, None))
        for i in range(n):
            (u0, v0), (u1, v1) = pts2[i], pts2[(i + 1) % n]
            self.faces.append(([P(u0, v0, a0), P(u1, v1, a0), P(u1, v1, a1), P(u0, v0, a1)], mat, None))

    def ring(self, outer, inner, plane, d0, d1, mat):
        """A closed frame between two loops of the same length, in the plane normal to `plane` ('x', 'y' or 'z'), from d0 to d1."""
        def P(u, v, d):
            return (u, d, v) if plane == 'y' else (u, v, d) if plane == 'z' else (d, u, v)
        n = len(outer)
        for i in range(n):
            j = (i + 1) % n
            for d in (d0, d1):
                self.faces.append(([P(*outer[i], d), P(*outer[j], d), P(*inner[j], d), P(*inner[i], d)], mat, None))
            self.faces.append(([P(*outer[i], d0), P(*outer[j], d0), P(*outer[j], d1), P(*outer[i], d1)], mat, None))
            self.faces.append(([P(*inner[i], d0), P(*inner[j], d0), P(*inner[j], d1), P(*inner[i], d1)], mat, None))

    def cylinder(self, c, axis, r, a0, a1, mat, seg=16):
        pts = [(c[0] + r * math.cos(2 * math.pi * k / seg), c[1] + r * math.sin(2 * math.pi * k / seg)) for k in range(seg)]
        self.prism(pts, axis, a0, a1, mat)

    def obj(self, name, coll, origin=(0, 0, 0), parent=None, closed=True, lods=(0, 1), smooth_angle=35):
        me = bpy.data.meshes.new(name)
        mats = []
        for _, m, _ in self.faces:
            if m not in mats:
                mats.append(m)
        for m in mats:
            me.materials.append(MAT[m])
        ox, oy, oz = origin
        bm = bmesh.new()
        uvl = bm.loops.layers.uv.new('UVMap')
        for pts, m, uv in self.faces:
            vs = [bm.verts.new((x - ox, y - oy, z - oz)) for x, y, z in pts]
            try:
                f = bm.faces.new(vs)
            except ValueError:
                continue
            f.material_index = mats.index(m)
            if uv is None:
                n = _newell(pts)
                ax = max(range(3), key=lambda i: abs(n[i]))
                su, sv = _uv_scale(m)
                for loop, p in zip(f.loops, pts):
                    u, v = [p[i] for i in range(3) if i != ax]
                    loop[uvl].uv = (u / su, v / sv)
            else:
                for loop, q in zip(f.loops, uv):
                    loop[uvl].uv = q
        bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-5)
        if closed:
            bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
        bm.to_mesh(me); bm.free()
        finish_mesh(me, smooth_angle)
        o = bpy.data.objects.new(name, me)
        o.location = origin
        coll.objects.link(o)
        if parent:
            o.parent = parent
        o['lods'] = list(lods)
        return o


def _uv_scale(name):
    """Metres per texture tile along U and V (a material gives one number, or a pair for a non-square swatch)."""
    s = MATERIALS[name][4] or 1.
    return s if isinstance(s, tuple) else (s, s)


def _newell(pts):
    n = Vector((0, 0, 0))
    for a, b in zip(pts, pts[1:] + pts[:1]):
        n += Vector(((a[1] - b[1]) * (a[2] + b[2]), (a[2] - b[2]) * (a[0] + b[0]), (a[0] - b[0]) * (a[1] + b[1])))
    return n.normalized() if n.length else Vector((0, 0, 1))


def finish_mesh(me, angle=35):
    for p in me.polygons:
        p.use_smooth = True
    me.set_sharp_from_angle(angle=math.radians(angle))
    me.validate()


def rrect(cx, cz, w, h, r, seg=4):
    """A rounded rectangle, counter-clockwise in (u, v)."""
    r = min(r, w / 2, h / 2)
    out = []
    for (qx, qz, a0) in ((cx + w / 2 - r, cz - h / 2 + r, -90), (cx + w / 2 - r, cz + h / 2 - r, 0),
                         (cx - w / 2 + r, cz + h / 2 - r, 90), (cx - w / 2 + r, cz - h / 2 + r, 180)):
        for k in range(seg + 1):
            a = math.radians(a0 + 90 * k / seg)
            out.append((qx + r * math.cos(a), qz + r * math.sin(a)))
    return out


def ellipse(cx, cz, w, h, seg=24):
    return [(cx + w / 2 * math.cos(2 * math.pi * k / seg), cz + h / 2 * math.sin(2 * math.pi * k / seg)) for k in range(seg)]


def boolean(obj, cutters):
    """Subtract the cutter meshes from obj (exact solver) and apply it."""
    coll = bpy.data.collections.new(f'cut_{obj.name}')
    bpy.context.scene.collection.children.link(coll)
    objs = []
    for i, m in enumerate(cutters):
        objs.append(m.obj(f'cut_{obj.name}_{i}', coll, lods=()))
    mod = obj.modifiers.new('cut', 'BOOLEAN')
    mod.operation = 'DIFFERENCE'; mod.operand_type = 'COLLECTION'; mod.collection = coll; mod.solver = 'EXACT'
    dg = bpy.context.evaluated_depsgraph_get()
    me = bpy.data.meshes.new_from_object(obj.evaluated_get(dg))
    old = obj.data
    obj.modifiers.clear(); obj.data = me; me.name = old.name
    bpy.data.meshes.remove(old)
    for o in objs:
        bpy.data.meshes.remove(o.data)
    bpy.data.collections.remove(coll)
    return obj


def reproject(obj, classify):
    """Reassign every face's material with classify(normal, centre) -> name and redo box-projected UVs."""
    me = obj.data
    names = [m.name for m in me.materials]
    bm = bmesh.new(); bm.from_mesh(me)
    uvl = bm.loops.layers.uv.verify()
    wm = obj.matrix_world
    for f in bm.faces:
        n = (wm.to_3x3() @ f.normal).normalized(); c = wm @ f.calc_center_median()
        name = classify(n, c)
        mname = MAT[name].name
        if mname not in names:
            me.materials.append(MAT[name]); names.append(mname)
        f.material_index = names.index(mname)
        ax = max(range(3), key=lambda i: abs(n[i]))
        su, sv = _uv_scale(name)
        for loop in f.loops:
            p = wm @ loop.vert.co
            u, v = [p[i] for i in range(3) if i != ax]
            loop[uvl].uv = (u / su, v / sv)
    bm.to_mesh(me); bm.free()
    finish_mesh(me)


def group(name, coll, parent=None):
    e = bpy.data.objects.new(name, None)
    e.empty_display_size = .3
    coll.objects.link(e)
    if parent:
        e.parent = parent
    e['lods'] = [0, 1, 2]
    return e


# --- the shared envelope ------------------------------------------------------------------------------------------
def side_walls(c, coll, parent):
    out = []
    for side, sy in (('l', 1), ('r', -1)):
        m = M()
        y0, y1 = sorted((sy * L.IN, sy * L.HALF))
        m.box(B.x_a, B.x_b, y0, y1, L.SKIRT_Z, L.BELT_Z, 'livery-blue')
        m.box(B.x_a, B.x_b, y0, y1, L.BELT_Z, L.CANT_Z, 'livery-ivory')
        o = m.obj(f'Shell_Side_{side.upper()}', coll, parent=parent)
        cutters = []
        for w in c.windows:
            if w.side != sy:
                continue
            cut = M(); cut.prism(rrect(w.x, (w.sill + w.head) / 2, w.width, w.head - w.sill, L.WIN_RADIUS), 'y', y0 - .05, y1 + .05, 'glass')
            cutters.append(cut)
        for name, s, x0, x1, z0, z1 in L.exterior_openings(c):
            if s == sy:
                cut = M(); cut.box(x0, x1, y0 - .05, y1 + .05, z0, z1, 'glass'); cutters.append(cut)
        boolean(o, cutters)

        def classify(n, ctr, sy=sy):
            if n.y * sy > .7 and abs(ctr.y) > L.HALF - 1e-3:
                return 'livery-blue' if ctr.z < L.BELT_Z else 'livery-ivory'
            if n.y * sy < -.7:
                return 'walnut'
            return 'walnut' if abs(ctr.y) < L.HALF - .01 or ctr.z > L.SILL - .01 else ('livery-blue' if ctr.z < L.BELT_Z else 'livery-ivory')
        reproject(o, classify)
        panel_uv(o, livery_panels(c, sy), sy)
        out.append(o)
    return out


def livery_panels(c, sy):
    """The lined panels of the blue lower body on side sy, (x0, x1) each: the spans between the exterior doors and the crest, split
    into panels of about 2 m (the swatch's proportions over the 0.85 m band)."""
    doors = sorted([(x0 - .18, x1 + .18) for _, s, x0, x1, *_ in L.exterior_openings(c) if s == sy]
                   + [(B.crest_x - .42, B.crest_x + .42)])          # the crest sits on plain blue between two panels
    out = []
    for a, b in _free(B.x_a + .12, B.x_b - .12, doors, .8):
        n = max(1, round((b - a) / 2.))
        out += [(a + (b - a) * k / n, a + (b - a) * (k + 1) / n) for k in range(n)]
    return out


def panel_uv(o, panels, sy):
    """Cut the outer blue faces at the panel edges and map the lined-panel swatch once on each panel, skirt to belt;
    blue between the panels (round the doors) stays the plain livery colour."""
    me = o.data
    bm = bmesh.new(); bm.from_mesh(me)
    for x in sorted({x for p in panels for x in p}):
        bmesh.ops.bisect_plane(bm, geom=bm.verts[:] + bm.edges[:] + bm.faces[:], plane_co=(x, 0, 0), plane_no=(1, 0, 0))
    names = [m.name for m in me.materials]
    if MAT['livery-panel'].name not in names:
        me.materials.append(MAT['livery-panel']); names.append(MAT['livery-panel'].name)
    blue, panel = names.index(MAT['livery-blue'].name), names.index(MAT['livery-panel'].name)
    uvl = bm.loops.layers.uv.verify()
    wm = o.matrix_world
    for f in bm.faces:
        if f.material_index != blue or (wm.to_3x3() @ f.normal).y * sy < .7:
            continue
        cx = (wm @ f.calc_center_median()).x
        p = next(((a, b) for a, b in panels if a - 1e-4 <= cx <= b + 1e-4), None)
        if p is None:
            continue
        f.material_index = panel
        for loop in f.loops:
            q = wm @ loop.vert.co
            u = (q.x - p[0]) / (p[1] - p[0])
            loop[uvl].uv = (u if sy > 0 else 1 - u, (q.z - L.SKIRT_Z) / (L.BELT_Z - L.SKIRT_Z))
    bm.to_mesh(me); bm.free()
    finish_mesh(me)


def end_walls(c, coll, parent):
    """Each end wall rises to the roof; it carries the gangway opening, or the door onto the balcony."""
    for end, sx in (('A', -1), ('B', 1)):
        pts = [(-L.IN, L.SKIRT_Z), (L.IN, L.SKIRT_Z)]
        for k in range(17):
            y = L.IN - 2 * L.IN * k / 16
            pts.append((y, L.roof_z(y, L.ROOF_SKIN) + .002))
        m = M(); a0, a1 = sorted((B.inner(sx), B.face(sx)))
        m.prism(pts, 'x', a0, a1, 'walnut')
        o = m.obj(f'Shell_End_{end}', coll, parent=parent)
        w = c.wall(f'end-{end.lower()}')
        cutters = []
        for op in w.openings:
            cut = M(); cut.box(a0 - .05, a1 + .05, op.a0, op.a1, op.z0, op.z1, 'glass'); cutters.append(cut)
        boolean(o, cutters)
        outside = 'end-dark' if B.end(sx) == 'gangway' else 'livery-ivory'
        reproject(o, lambda n, ctr, sx=sx, outside=outside: (outside if ctr.z > L.BELT_Z or outside == 'end-dark' else 'livery-blue') if n.x * sx > .7 else 'walnut')
    # corner posts close the ends of the side walls up to the roof
    m = M()
    for sx in (-1, 1):
        for sy in (-1, 1):
            x0, x1 = sorted((B.face(sx) - sx * .07, B.face(sx) + sx * .012))
            y0, y1 = sorted((sy * (L.IN - .002), sy * (L.HALF + .012)))
            m.box(x0, x1, y0, y1, L.SKIRT_Z - .02, L.CANT_Z + .14, 'end-dark')
    m.obj('Shell_CornerPosts', coll, parent=parent)


def roof(coll, parent, lod=0):
    seg = 32 if lod == 0 else 12
    outer = [(-L.HALF + 2 * L.HALF * k / seg) for k in range(seg + 1)]
    # the roof overhangs each end wall a little, and runs on over a balcony as its canopy
    xa = (B.x_a - .05) if B.end_a == 'gangway' else B.headstock(-1) - .04
    xb = (B.x_b + .05) if B.end_b == 'gangway' else B.headstock(1) + .04
    m = M()
    ys_o = [(y, L.roof_z(y)) for y in outer]
    ys_i = [(y * (L.HALF - L.ROOF_SKIN) / L.HALF, L.roof_z(y * (L.HALF - L.ROOF_SKIN) / L.HALF, L.ROOF_SKIN)) for y in outer]
    for k in range(seg):
        (ya, za), (yb, zb) = ys_o[k], ys_o[k + 1]
        m.poly([(xa, ya, za), (xa, yb, zb), (xb, yb, zb), (xb, ya, za)], 'roof')
        (ya, za), (yb, zb) = ys_i[k], ys_i[k + 1]
        m.poly([(xb, ya, za), (xb, yb, zb), (xa, yb, zb), (xa, ya, za)], 'roof')
        for x in (xa, xb):
            m.poly([(x, *ys_o[k]), (x, *ys_o[k + 1]), (x, *ys_i[k + 1]), (x, *ys_i[k])], 'roof')
    for k in (0, seg):
        m.poly([(xa, *ys_o[k]), (xb, *ys_o[k]), (xb, *ys_i[k]), (xa, *ys_i[k])], 'roof')
    skin = m.obj('Roof_Skin' if lod == 0 else 'LOD2_Roof', coll, parent=parent, lods=(0, 1) if lod == 0 else (2,))
    if lod:
        return skin
    well = _lookout_well()
    if well:                                          # the lookout opens through the roof
        cut = M(); cut.box(well[0] - .02, well[1] + .02, -well[2] - .02, well[2] + .02, L.CEIL_SPRING, L.ROOF_TOP + .30, 'roof')   # edges hidden in its walls
        boolean(skin, [cut])
    m = M()
    for sy in (-1, 1):            # cornice and the brass line under it
        y0, y1 = sorted((sy * (L.HALF - .01), sy * (L.HALF + .028)))
        m.box(xa + .03, xb - .03, y0, y1, L.CANT_Z - .07, L.CANT_Z + .01, 'roof')
        y0, y1 = sorted((sy * (L.HALF - .01), sy * (L.HALF + .016)))
        m.box(B.x_a, B.x_b, y0, y1, L.CANT_Z - .105, L.CANT_Z - .085, 'brass')
    span = B.x_b - B.x_a
    vents = max(2, round(span / 2.6))
    cup = B.cupola or (1e9, 1e9)
    for k in range(vents):        # torpedo ventilators on the centre line, none on a lookout
        x = B.x_a + 1.2 + (span - 2.4) * k / (vents - 1)
        if cup[0] - .3 < x < cup[1] + .3:
            continue
        m.cylinder((x, 0), 'z', .085, L.roof_z(0) - .02, L.VENT_TOP - .07, 'roof', 12)
        m.cylinder((x, 0), 'z', .13, L.VENT_TOP - .07, L.VENT_TOP - .02, 'brass', 12)
        m.cylinder((x, 0), 'z', .07, L.VENT_TOP - .02, L.VENT_TOP, 'brass', 12)
    battens = max(2, round((xb - xa) / 1.85))
    for k in range(battens + 1):  # roof seams: raised battens following the roof curve
        x = xa + .3 + (xb - xa - .6) * k / battens
        for j in range(seg):
            (ya, za), (yb, zb) = ys_o[j], ys_o[j + 1]
            if abs(ya) > L.HALF - .05 or abs(yb) > L.HALF - .05:
                continue
            if B.cupola and B.cupola[0] - .07 < x < B.cupola[1] + .07 and min(abs(ya), abs(yb)) < L.CUPOLA_HW + .07:
                continue
            m.poly([(x - .012, ya, za + .010), (x + .012, ya, za + .010), (x + .012, yb, zb + .010), (x - .012, yb, zb + .010)], 'roof', normal=(0, 0, 1))
            for e, sgn in ((x - .012, -1), (x + .012, 1)):
                m.poly([(e, ya, za - .002), (e, yb, zb - .002), (e, yb, zb + .010), (e, ya, za + .010)], 'roof', normal=(sgn, 0, 0))
    m.obj('Roof_Details', coll, parent=parent, lods=(0,), closed=False)
    if B.cupola:
        cupola(coll, parent)
    return skin


def cupola(coll, parent):
    """The guard's lookout: a raised glazed cab on the roof with its own curved top, part of the removable roof."""
    x0, x1 = B.cupola
    hw = L.CUPOLA_HW
    z0, z1 = L.roof_z(hw) - .05, L.ROOF_TOP + L.LOOKOUT_RISE
    m = M()
    m.box(x0, x1, -hw, hw, z0, z1, 'livery-ivory')
    o = m.obj('Roof_Cupola', coll, parent=parent)
    w = L.CUPOLA_WALL
    hollow = M(); hollow.box(x0 + w, x1 - w, -hw + w, hw - w, z0 - .30, z1 - w, 'ceiling')   # open below, into the well
    cutters = [hollow]
    for sy in (-1, 1):
        for k in range(3):
            xc = x0 + (x1 - x0) * (k + .5) / 3
            cut = M(); cut.prism(rrect(xc, z1 - .30, (x1 - x0) / 3 - .20, .34, .05), 'y', -hw - .05, hw + .05, 'glass'); cutters.append(cut)
    for xe in (x0, x1):
        cut = M(); cut.prism(rrect(0, z1 - .30, 1.30, .34, .05), 'x', xe - .05, xe + .05, 'glass'); cutters.append(cut)
    boolean(o, cutters)
    inside = lambda ctr: abs(ctr.y) < hw - .03 and x0 + .03 < ctr.x < x1 - .03 and ctr.z < z1 - .03
    reproject(o, lambda n, ctr: ('ceiling' if n.z < -.5 else 'walnut') if inside(ctr) and n.z < .5 else 'livery-ivory')
    m = M()
    seg = 16
    for k in range(seg):          # a small curved top, echoing the main roof
        ya, yb = -hw - .06 + (2 * hw + .12) * k / seg, -hw - .06 + (2 * hw + .12) * (k + 1) / seg
        za = z1 + .16 * (1 - (ya / (hw + .06)) ** 2) ** .5
        zb = z1 + .16 * (1 - (yb / (hw + .06)) ** 2) ** .5
        m.poly([(x0 - .06, ya, za), (x0 - .06, yb, zb), (x1 + .06, yb, zb), (x1 + .06, ya, za)], 'roof', normal=(0, 0, 1))
        m.poly([(x0 - .06, ya, za - .03), (x1 + .06, ya, za - .03), (x1 + .06, yb, zb - .03), (x0 - .06, yb, zb - .03)], 'roof', normal=(0, 0, -1))
    m.obj('Roof_CupolaTop', coll, parent=parent, closed=False)
    m = M(); g = M()
    for sy in (-1, 1):
        for k in range(3):
            xc = x0 + (x1 - x0) * (k + .5) / 3
            pts = rrect(xc, z1 - .30, (x1 - x0) / 3 - .20, .34, .05)
            g.poly([(u, sy * (hw - .02), v) for u, v in pts], 'glass', normal=(0, sy, 0))
            m.ring(rrect(xc, z1 - .30, (x1 - x0) / 3 - .12, .42, .09), rrect(xc, z1 - .30, (x1 - x0) / 3 - .22, .32, .04), 'y', sy * hw, sy * (hw + .012), 'brass')
    for xe, sx in ((x0, -1), (x1, 1)):
        pts = rrect(0, z1 - .30, 1.30, .34, .05)
        g.poly([(xe - sx * .02, u, v) for u, v in pts], 'glass', normal=(sx, 0, 0))
    m.box(x0 - .02, x1 + .02, -hw - .02, hw + .02, z1 - .02, z1 + .01, 'brass')
    m.obj('Roof_CupolaTrim', coll, parent=parent, lods=(0,))
    g.obj('Glazing_Cupola', coll, parent=parent, closed=False)


def _lookout_well():
    return L.lookout_well(B)


def lookout(c, coll, parent):
    """The guard's way up into the lookout: two walnut steps with brass nosings on the 'cupola-steps' box, a brass
    ladder from the top tread, and the lookout seat against the lookout's rear wall, with a grab rail."""
    b = next(r for r in c.reservations if r.name == 'cupola-steps')
    F, lx = L.FLOOR_Z, L.LOOKOUT_LADDER_X
    sx0, sx1, sy0, sy1, top = L.LOOKOUT_SEAT
    m = M()
    for x0, x1, z in ((lx + .03, b.x1, F + .30), (b.x0, lx + .03, F + .60)):     # the lower tread in front, the upper behind
        m.box(x0, x1, b.y0, b.y1, F, z, 'walnut')
        m.box(x1 - .03, x1, b.y0, b.y1, z - .02, z + .005, 'brass')
    for y in (b.y0 + .07, b.y1 - .07):               # ladder stiles, on past the seat as handholds
        m.box(lx - .015, lx + .015, y - .015, y + .015, F + .60, F + top + .55, 'brass')
    for k in range(6):
        z = F + .90 + k * .30
        m.cylinder((lx, z), 'y', .012, b.y0 + .07, b.y1 - .07, 'brass', 8)
    m.box(sx0, sx1, sy0, sy1, F + top - .06, F + top, 'walnut')                 # seat board on its bearers
    for y in (sy0 + .04, sy1 - .04):
        m.box(sx0, sx1, y - .025, y + .025, F + top - .16, F + top - .06, 'walnut')
    m.box(sx0, sx0 + .05, sy0, sy1, F + top, F + top + .40, 'walnut')            # backrest on the rear wall
    m.cylinder((sx0 + .10, F + top + .35), 'y', .014, sy1, sy1 + .45, 'brass', 8)  # grab rail along the wall
    m.obj('Interior_Lookout', coll, parent=parent)


def ceiling(c, coll, parent):
    seg = 24
    ys = [-L.IN + 2 * L.IN * k / seg for k in range(seg + 1)]
    well = _lookout_well()
    if well:                                          # the strips meet the well's sides exactly
        ys = sorted(set(ys) | {-well[2], well[2]})
    m = M()
    xa, xb = B.in_a, B.in_b
    for ya, yb in zip(ys, ys[1:]):
        za, zb = L.ceiling_z(ya), L.ceiling_z(yb)
        spans = [(xa, well[0]), (well[1], xb)] if well and abs((ya + yb) / 2) < well[2] else [(xa, xb)]
        for x0, x1 in spans:
            m.poly([(x0, ya, za), (x1, ya, za), (x1, yb, zb), (x0, yb, zb)], 'ceiling', normal=(0, 0, -1))
            m.poly([(x0, ya, za + .03), (x0, yb, zb + .03), (x1, yb, zb + .03), (x1, ya, za + .03)], 'ceiling', normal=(0, 0, 1))
    if well:                                          # the well's walnut lining, from the ceiling up into the lookout
        x0, x1, hw, top = well
        for y, sgn in ((-hw, 1), (hw, -1)):
            z = L.ceiling_z(y)
            m.poly([(x0, y, z), (x1, y, z), (x1, y, top), (x0, y, top)], 'walnut', normal=(0, sgn, 0))
        for x, sgn in ((x0, 1), (x1, -1)):
            for ya, yb in zip(ys, ys[1:]):
                if abs((ya + yb) / 2) < hw:
                    m.poly([(x, ya, L.ceiling_z(ya)), (x, yb, L.ceiling_z(yb)), (x, yb, top), (x, ya, top)], 'walnut', normal=(sgn, 0, 0))
    m.obj('Ceiling', coll, parent=parent, closed=False)
    # brass ribs at the window piers (and partitions in first class)
    side = sorted((w for w in c.windows if w.side > 0), key=lambda w: w.x)
    xs = sorted({round((a.x + b.x) / 2, 3) for a, b in zip(side, side[1:])})
    m = M()
    for x in xs:                  # a smooth brass band following the ceiling: underside and two edges
        for k in range(seg):
            ya, yb = ys[k], ys[k + 1]
            za, zb = L.ceiling_z(ya) - .016, L.ceiling_z(yb) - .016
            m.poly([(x - .025, ya, za), (x + .025, ya, za), (x + .025, yb, zb), (x - .025, yb, zb)], 'brass', normal=(0, 0, -1))
            for e, sgn in ((x - .025, -1), (x + .025, 1)):
                m.poly([(e, ya, za), (e, yb, zb), (e, yb, zb + .017), (e, ya, za + .017)], 'brass', normal=(sgn, 0, 0))
    # cove line at the springing
    for sy in (-1, 1):
        y0, y1 = sorted((sy * (L.IN - .035), sy * L.IN))
        m.box(B.in_a, B.in_b, y0, y1, L.CEIL_SPRING - .05, L.CEIL_SPRING + .005, 'brass')
    m.obj('Ceiling_Ribs', coll, parent=parent, lods=(0,), closed=False)


def deck_and_underframe(c, coll, parent):
    m = M()
    ha, hb = B.headstock(-1), B.headstock(1)
    m.box(B.in_a, B.in_b, -L.IN, L.IN, L.FLOOR_Z - L.DECK, L.FLOOR_Z - .006, 'undercarriage')
    m.box(ha, hb, -L.IN, L.IN, L.SKIRT_Z - .02, L.FLOOR_Z - L.DECK, 'undercarriage')
    for sy in (-1, 1):            # solebars
        y0, y1 = sorted((sy * (L.HALF - .45), sy * (L.HALF - .28)))
        m.box(ha + .1, hb - .1, y0, y1, .80, L.SKIRT_Z - .02, 'undercarriage')
    for sx in (-1, 1):            # headstocks
        x0, x1 = sorted((B.headstock(sx) - sx * .05, B.headstock(sx) + sx * .07))
        m.box(x0, x1, -L.HALF + .15, L.HALF - .15, .86, 1.24, 'end-dark')
    # equipment between the bogies: battery boxes, water tanks, brake cylinders, truss rods
    lo, hi = B.bogies[0] + B.wheelbase / 2 + .75, B.bogies[1] - B.wheelbase / 2 - .75
    f = lambda t: lo + (hi - lo) * t
    for t0, t1, y0, y1, z0, z1 in ((.0, .15, .25, 1.15, .45, .80), (.85, 1., -1.15, -.25, .45, .80), (.32, .68, -1.10, -.35, .40, .80),
                                   (.36, .45, .45, 1.15, .52, .80), (.56, .66, .45, 1.15, .55, .80)):
        m.box(f(t0), f(t1), y0, y1, z0, z1, 'undercarriage')
    if hi - lo > 6:
        for t in (.33, .67):
            m.cylinder((.65, .62), 'x', .22, f(t) - 1.0, f(t) + 1.0, 'undercarriage', 16)
    for sy in (-1, 1):
        for t0, t1 in ((0., .42), (.58, 1.)):
            m.box(f(t0), f(t1), sy * .55 - .02, sy * .55 + .02, .42, .46, 'steel')
    m.obj('Shell_Underframe', coll, parent=parent)
    # brass lining on the livery
    m = M()
    for sy in (-1, 1):
        o = lambda d: sorted((sy * (L.HALF - .002), sy * (L.HALF + d)))
        y0, y1 = o(.006)
        # the belt; the lined panels and rivet strips of the blue lower body are in the livery-panel swatch (panel_uv)
        m.box(B.x_a + .08, B.x_b - .08, y0, y1, L.BELT_Z - .009, L.BELT_Z + .009, 'brass')
        for z in (L.CANT_Z - .16,):
            m.box(B.x_a + .08, B.x_b - .08, y0, y1, z - .006, z + .006, 'brass')
    m.obj('Shell_Lining', coll, parent=parent, lods=(0,))
    # the crest, a decal on each side of the blue band
    m = M()
    zc = (L.SKIRT_Z + .16 + L.BELT_Z - .10) / 2
    for sy in (-1, 1):
        y = sy * (L.HALF + .004)
        w = h = .56
        xs = (B.crest_x - w / 2, B.crest_x + w / 2)
        pts = [(xs[0], y, zc - h / 2), (xs[1], y, zc - h / 2), (xs[1], y, zc + h / 2), (xs[0], y, zc + h / 2)]
        uv = [(0, 0), (1, 0), (1, 1), (0, 1)]
        if sy < 0:
            pts = [(xs[1] + xs[0] - p[0], p[1], p[2]) for p in pts]
        m.poly(pts, 'crest', uv=uv, normal=(0, sy, 0))
    m.obj('Shell_Crest', coll, parent=parent, closed=False)


def ends_hardware(c, coll, parent):
    m = M()
    for sx in (-1, 1):
        hs, bf = B.headstock(sx), B.buffer(sx)
        for sy in (-1, 1):            # buffers
            x0, x1 = sorted((hs + sx * .06, bf - sx * .06))
            m.cylinder((sy * L.BUFFER_Y, L.BUFFER_Z), 'x', .10, x0, x1, 'undercarriage', 16)
            x0, x1 = sorted((bf - sx * .06, bf))
            m.cylinder((sy * L.BUFFER_Y, L.BUFFER_Z), 'x', .20, x0, x1, 'steel', 20)
        x0, x1 = sorted((hs + sx * .06, bf - sx * .02))     # draw hook and screw link
        m.box(x0, x1, -.06, .06, L.BUFFER_Z - .07, L.BUFFER_Z + .05, 'undercarriage')
        m.box(bf - sx * .04 - .03, bf - sx * .04 + .03, -.12, .12, L.BUFFER_Z - .20, L.BUFFER_Z - .05, 'steel')
        for sy in (-1, 1):            # brake hoses
            m.box(hs + sx * .10 - .02, hs + sx * .10 + .02, sy * .35 - .02, sy * .35 + .02, .80, 1.15, 'rubber')
    m.obj('Shell_Buffers', coll, parent=parent)
    # gangways: a bellows frame around the end door, its face at the buffer line, and a footplate
    m = M()
    w_out, h_out = L.GANGWAY_W + .36, L.GANGWAY_H + .26
    z0 = L.FLOOR_Z - .06
    for sx in (-1, 1):
        if B.end(sx) != 'gangway':
            continue
        fx, bf = B.face(sx), B.buffer(sx)
        pitch = (abs(bf - fx) - .01) / 5
        for k in range(5):
            a0, a1 = sorted((fx + sx * (.002 + k * pitch), fx + sx * (.002 + (k + 1) * pitch - (.012 if k < 4 else 0))))
            g = .02 if k % 2 else 0
            yo, yi = w_out / 2 - g, L.GANGWAY_W / 2 + .04
            m.box(a0, a1, -yo, -yi, z0 + g, z0 + h_out - g, 'rubber')
            m.box(a0, a1, yi, yo, z0 + g, z0 + h_out - g, 'rubber')
            m.box(a0, a1, -yi, yi, z0 + L.GANGWAY_H + .08, z0 + h_out - g, 'rubber')
        a0, a1 = sorted((fx, bf - sx * .005))
        m.box(a0, a1, -L.GANGWAY_W / 2 - .02, L.GANGWAY_W / 2 + .02, L.FLOOR_Z - .03, L.FLOOR_Z - .005, 'steel')
    if m.faces:
        m.obj('Shell_Gangways', coll, parent=parent)
    # exterior door steps and brass grab handles
    m = M()
    for name, sy, x0, x1, *_ in L.exterior_openings(c):
        steps(m, sy, x0, x1)
        y = sy * L.HALF
        for x in (x0 - .07, x1 + .07):
            m.cylinder((x, sy * (L.HALF + .065)), 'z', .016, L.FLOOR_Z + .15, L.FLOOR_Z + 1.75, 'brass', 8)
            for z in (L.FLOOR_Z + .15, L.FLOOR_Z + 1.75):
                m.box(x - .012, x + .012, min(sy * L.HALF, sy * (L.HALF + .07)), max(sy * L.HALF, sy * (L.HALF + .07)), z - .012, z + .012, 'brass')
    m.obj('Shell_Steps', coll, parent=parent, lods=(0,))


def steps(m, sy, x0, x1, inset=0.):
    """Two hanging steps under a door or a balcony gate on side sy, from x0 to x1."""
    y = sy * (L.HALF - inset)
    for tx0, tx1, ya, yb, z in L.step_treads(sy, x0, x1, inset):
        m.box(tx0, tx1, ya, yb, z - .03, z, 'steel')
        m.box(tx0, tx1, ya, yb, z - .004, z + .002, 'brass')
    for x in (x0 + .01, x1 - .01):
        m.box(x - .015, x + .015, min(y, y + sy * .08), max(y, y + sy * .08), .63, L.SKIRT_Z, 'undercarriage')


def balcony(c, coll, parent):
    """An open platform beyond the end wall: plank floor, brass railing with a gate gap and steps on each side,
    canopy posts holding the roof, and the red tail lamp."""
    for s in (-1, 1):
        if B.end(s) != 'balcony':
            continue
        edge, face = B.headstock(s), B.face(s)
        m = M(); trim = M()
        x0, x1 = sorted((edge, face))
        m.box(x0, x1, -L.HALF + .12, L.HALF - .12, L.FLOOR_Z - L.DECK, L.FLOOR_Z, 'parquet')
        for x0b, x1b, y0, y1 in L.railings(B):
            for z in (L.FLOOR_Z + .48, L.FLOOR_Z + 1.02):
                trim.box(x0b, x1b, y0, y1, z - .018, z + .018, 'brass')
            for x in (x0b, x1b) if x1b - x0b > .1 else ((x0b + x1b) / 2,):
                for y in ((y0 + y1) / 2,) if y1 - y0 < .1 else (y0 + .03, (y0 + y1) / 2, y1 - .03):
                    trim.cylinder((x, y), 'z', .022, L.FLOOR_Z, L.FLOOR_Z + 1.04, 'brass', 8)
        # balusters along the outer edge
        for k in range(15):
            y = -L.IN + .1 + (2 * L.IN - .2) * k / 14
            trim.cylinder((edge - s * .025, y), 'z', .012, L.FLOOR_Z, L.FLOOR_Z + 1.02, 'brass', 6)
        for sy in (-1, 1):            # canopy posts at the outer corners, up to the roof
            trim.cylinder((edge - s * .03, sy * (L.HALF - .10)), 'z', .035, L.FLOOR_Z, L.roof_z(L.HALF - .10, L.ROOF_SKIN), 'brass', 10)
            steps(m, sy, *L.balcony_gate(B, s))
        lamp = next((mt for mt in c.mounts if mt.kind == 'tail-lamp'), None)
        if lamp:
            trim.box(lamp.x - .09, lamp.x + .09, lamp.y - .09, lamp.y + .09, lamp.z - .12, lamp.z + .12, 'end-dark')
            red = M(); red.cylinder((lamp.y, lamp.z), 'x', .07, lamp.x + s * .09, lamp.x + s * .11, 'lamp-red', 16)
            red.obj('Shell_TailLamp', coll, parent=parent)
        m.obj('Shell_Balcony', coll, parent=parent)
        trim.obj('Shell_BalconyRailing', coll, parent=parent)


def bogies(coll, parent, lod=0):
    """Identical two-axle bogies sharing one frame mesh and one wheelset mesh (linked data)."""
    if lod == 2:
        m = M()
        for bx in B.bogies:
            m.box(bx - B.wheelbase / 2 - .30, bx + B.wheelbase / 2 + .30, -1.08, 1.08, .20, .85, 'undercarriage')
        return [m.obj('LOD2_Bogies', coll, parent=parent, lods=(2,))]
    m = M()
    hl = B.wheelbase / 2 + .30
    for sy in (-1, 1):
        y0, y1 = sorted((sy * .96, sy * 1.06))
        m.box(-hl, hl, y0, y1, .36, .62, 'undercarriage')            # side frame
        m.box(-.55, .55, y0, y1, .62, .80, 'undercarriage')
        for x in (-B.wheelbase / 2, B.wheelbase / 2):
            m.box(x - .16, x + .16, y0 - .02, y1 + .02, .30, .64, 'undercarriage')   # axlebox guides
            m.cylinder((x, L.WHEEL_R), 'y', .085, *sorted((sy * 1.06, sy * 1.10)), 'brass', 12)   # brass axle caps
        for x in (-.75, -.45, .45, .75):                                   # bolster springs
            m.cylinder((x, sy * 1.01), 'z', .07, .62, .82, 'steel', 10)
    m.box(-.30, .30, -1.0, 1.0, .58, .80, 'undercarriage')                 # bolster
    for x in (-B.wheelbase / 2 - .25, B.wheelbase / 2 + .25):             # brake beams
        m.box(x - .04, x + .04, -.95, .95, .42, .50, 'undercarriage')
    out = []
    w = M()
    for sy in (-1, 1):
        y0, y1 = sorted((sy * (L.GAUGE / 2 - .02), sy * (L.GAUGE / 2 + .11)))
        w.cylinder((0, 0), 'y', L.WHEEL_R, y0, y1, 'steel', 24)
        f0, f1 = sorted((sy * (L.GAUGE / 2 - .02), sy * (L.GAUGE / 2 + .005)))
        w.cylinder((0, 0), 'y', L.WHEEL_R + .03, f0, f1, 'steel', 24)
        w.cylinder((0, 0), 'y', .15, *sorted((sy * (L.GAUGE / 2 + .11), sy * .98)), 'undercarriage', 12)
    w.cylinder((0, 0), 'y', .075, -.98, .98, 'undercarriage', 12)
    frame_me = wheel_me = None
    for end, bx in zip('ABCD', B.bogies):
        if frame_me is None:
            b = m.obj(f'Bogie_{end}', coll, parent=parent); frame_me = b.data
        else:
            b = _linked(f'Bogie_{end}', frame_me, coll, (0, 0, 0), parent)
        b.location = (bx, 0, 0)
        out.append(b)
        for k, ax in enumerate((-B.wheelbase / 2, B.wheelbase / 2)):
            name = f'Bogie_{end}_Wheelset_{k + 1}'
            if wheel_me is None:
                ws = w.obj(name, coll); wheel_me = ws.data
            else:
                ws = _linked(name, wheel_me, coll, (0, 0, 0), None)
            ws.parent = b
            ws.location = (ax, 0, L.WHEEL_R)
    return out


def _linked(name, me, coll, loc, parent):
    o = bpy.data.objects.new(name, me)
    o.location = loc
    coll.objects.link(o)
    if parent:
        o.parent = parent
    o['lods'] = [0, 1]
    return o


# --- each coach's interior ----------------------------------------------------------------------------------------
def floors(c, coll, parent):
    m = M()
    for r in c.rooms:
        m.poly([(r.x0, r.y0, L.FLOOR_Z), (r.x1, r.y0, L.FLOOR_Z), (r.x1, r.y1, L.FLOOR_Z), (r.x0, r.y1, L.FLOOR_Z)], r.floor, normal=(0, 0, 1))
    m.obj('Interior_Floor', coll, parent=parent, closed=False)


def partitions(c, coll, parent):
    objs = []
    m = M()
    for w in c.walls:
        if w.name.startswith('end-'):
            continue
        if w.axis == 'x':
            top = L.ceiling_z(min(abs(w.c0), abs(w.c1))) + .02
            m.box(w.a0, w.a1, w.c0, w.c1, L.FLOOR_Z - .006, top, 'walnut')
        else:
            pts = [(w.a0, L.FLOOR_Z - .006), (w.a1, L.FLOOR_Z - .006)]
            for k in range(13):
                y = w.a1 - (w.a1 - w.a0) * k / 12
                pts.append((y, L.ceiling_z(y) + .02))
            m.prism(pts, 'x', w.c0, w.c1, 'walnut')
    o = m.obj('Interior_Partitions', coll, parent=parent)
    cutters = []
    for w in c.walls:
        if w.name.startswith('end-'):
            continue
        for op in w.openings:
            cut = M()
            if w.axis == 'x':
                cut.box(op.a0, op.a1, w.c0 - .05, w.c1 + .05, op.z0 - .05, op.z1, 'glass')
            else:
                cut.box(w.c0 - .05, w.c1 + .05, op.a0, op.a1, op.z0 - .05, op.z1, 'glass')
            cutters.append(cut)
    boolean(o, cutters)
    reproject(o, lambda n, ctr: 'walnut')
    objs.append(o)
    return objs


PANELLED = {'cabin', 'corridor', 'salon', 'lobby', 'bar', 'saloon', 'guard'}

# a worn coach keeps the same geometry; its finishes are swapped for tired ones after the build
WORN = {'livery-blue': 'livery-blue-worn', 'livery-ivory': 'livery-ivory-worn', 'livery-panel': 'livery-panel-worn', 'roof': 'roof-worn', 'end-dark': 'end-dark-worn',
        'brass': 'brass-dull', 'panel-tall': 'paint-peel', 'panel-wide': 'paint-peel', 'walnut': 'paint-peel',
        'crest': 'decal-two', 'glass': 'glass-grimy', 'ceiling': 'ceiling-dingy'}


def wear_out(objs):
    bpy.context.view_layer.update()         # world matrices of the freshly placed doors, for _reproject_worn
    for o in objs:
        if o.type != 'MESH':
            continue
        for slot in o.material_slots:
            for k, v in WORN.items():
                if slot.material is MAT[k]:
                    slot.material = MAT[v]
                    break
        _reproject_worn(o)


def _reproject_worn(o):
    """The peeling matchboard replaces marquetry mapped once per panel and walnut at its own scale: map it again in
    metres, boards upright, so it keeps one board width on every wall, pier and panel."""
    peel = [i for i, s in enumerate(o.material_slots) if s.material is MAT['paint-peel']]
    if not peel:
        return
    bm = bmesh.new(); bm.from_mesh(o.data)
    uvl = bm.loops.layers.uv.verify()
    wm = o.matrix_world
    su, sv = _uv_scale('paint-peel')
    for f in bm.faces:
        if f.material_index not in peel:
            continue
        n = wm.to_3x3() @ f.normal
        ax = max(range(3), key=lambda i: abs(n[i]))
        for loop in f.loops:
            p = wm @ loop.vert.co
            u, v = [p[i] for i in range(3) if i != ax]
            loop[uvl].uv = (u / su, v / sv)
    bm.to_mesh(o.data); bm.free()


def _free(a0, a1, blocked, min_len=.12):
    out, a = [], a0
    for b0, b1 in sorted(blocked):
        if b1 <= a or b0 >= a1:
            continue
        if b0 - a >= min_len:
            out.append((a, b0))
        a = max(a, b1)
    if a1 - a >= min_len:
        out.append((a, a1))
    return out


def _panels(m, axis, face, sign, intervals, z0, z1, target, kind):
    """Raised marquetry panels on a wall face. axis: the face runs along x ('x') or y ('y'); face: its coordinate
    across; sign: the side the panel stands proud on."""
    gap = .035
    for a, b in intervals:
        n = max(1, round((b - a) / target))
        w = (b - a - gap * (n + 1)) / n
        for k in range(n):
            p0 = a + gap + k * (w + gap); p1 = p0 + w
            if w < .08:
                continue
            tall = (z1 - z0) / w >= 1.0
            mat = kind if kind != 'auto' else ('panel-tall' if tall else 'panel-wide')
            c0, c1 = sorted((face, face + sign * .014))
            if axis == 'x':
                m.box(p0, p1, c0, c1, z0, z1, 'walnut', front=('y', sign), front_mat=mat)
            else:
                m.box(c0, c1, p0, p1, z0, z1, 'walnut', front=('x', sign), front_mat=mat)


def lining(c, coll, parent):
    """Marquetry panels, dado rail and skirting on the walls of the passenger rooms; brass window frames."""
    m = M(); trim = M()
    rooms = [r for r in c.rooms if r.kind in PANELLED]
    ext = L.exterior_openings(c)
    for sy in (-1, 1):
        face = sy * L.IN
        blocked_doors = [(x0 - .03, x1 + .03) for _, s, x0, x1, *_ in ext if s == sy]
        blocked_walls = [(w.c0 - .005, w.c1 + .005) for w in c.walls if w.axis == 'y' and (w.a1 >= L.IN - 1e-6 if sy > 0 else w.a0 <= -L.IN + 1e-6)]
        for r in rooms:
            if not (r.y1 >= L.IN - 1e-6 if sy > 0 else r.y0 <= -L.IN + 1e-6):
                continue
            base = blocked_doors + blocked_walls
            here = [w for w in c.windows if w.side == sy and r.x0 < w.x < r.x1 and w.kind == 'clear']
            sill = min((w.sill for w in here), default=L.SILL); head = max((w.head for w in here), default=L.HEAD)
            wins = [(w.x - w.width / 2 - .075, w.x + w.width / 2 + .075) for w in c.windows if w.side == sy]
            dado = _free(r.x0, r.x1, base)
            _panels(m, 'x', face, -sy, dado, L.FLOOR_Z + .12, sill - .07, .80, 'panel-wide')
            _panels(m, 'x', face, -sy, _free(r.x0, r.x1, base + wins), sill - .01, head + .01, .85, 'auto')
            if L.CEIL_SPRING - .07 - (head + .08) > .08:
                _panels(m, 'x', face, -sy, _free(r.x0, r.x1, base), head + .08, L.CEIL_SPRING - .07, 1.2, 'walnut')
            for a, b in dado:
                c0, c1 = sorted((face, face - sy * .03))
                trim.box(a, b, c0, c1, sill - .055, sill - .025, 'brass')
                c0, c1 = sorted((face, face - sy * .02))
                trim.box(a, b, c0, c1, L.FLOOR_Z, L.FLOOR_Z + .10, 'walnut')
    # partitions: both faces where they face a panelled room
    for w in c.walls:
        if w.name.startswith('end-'):
            continue
        for side in (-1, 1):
            face = w.c1 if side > 0 else w.c0
            probe = face + side * .1
            pt = (w.a0 + w.a1) / 2
            room = None
            for r in rooms:
                x, y = (pt, probe) if w.axis == 'x' else (probe, pt)
                for frac in (.1, .5, .9):
                    a = w.a0 + (w.a1 - w.a0) * frac
                    x, y = (a, probe) if w.axis == 'x' else (probe, a)
                    if r.x0 <= x <= r.x1 and r.y0 <= y <= r.y1:
                        room = r
            if room is None:
                continue
            lo, hi = (max(w.a0, room.x0), min(w.a1, room.x1)) if w.axis == 'x' else (max(w.a0, room.y0), min(w.a1, room.y1))
            blocked = [(o.a0 - .07, o.a1 + .07) for o in w.openings]
            for o2 in c.walls:            # walls meeting this face
                if o2.axis != w.axis and o2.a0 - 1e-3 <= face <= o2.a1 + 1e-3 or o2.axis != w.axis and abs(face - (o2.a0 if side > 0 else o2.a1)) < 1e-3:
                    blocked.append((o2.c0 - .005, o2.c1 + .005))
            top = min(L.ceiling_z(face) if w.axis == 'x' else L.CEIL_SPRING, L.CEIL_SPRING) - .07
            free = _free(lo, hi, blocked)
            _panels(m, w.axis, face, side, free, L.FLOOR_Z + .12, L.FLOOR_Z + .78, .80, 'panel-wide')
            _panels(m, w.axis, face, side, free, L.FLOOR_Z + .86, L.FLOOR_Z + 1.95, .80, 'auto')
            if top - (L.FLOOR_Z + 2.03) > .08:
                _panels(m, w.axis, face, side, free, L.FLOOR_Z + 2.03, top, 1.2, 'walnut')
            for a, b in free:
                c0, c1 = sorted((face, face + side * .03))
                if w.axis == 'x':
                    trim.box(a, b, c0, c1, L.FLOOR_Z + .80, L.FLOOR_Z + .83, 'brass')
                else:
                    trim.box(c0, c1, a, b, L.FLOOR_Z + .80, L.FLOOR_Z + .83, 'brass')
    m.obj('Interior_Lining', coll, parent=parent, lods=(0,))
    # architraves and thresholds round every interior doorway
    for w in c.walls:
        if w.name.startswith('end-'):
            continue
        for o in w.openings:
            glazed = any(d.opening == o.name and d.glazed for d in c.doors)
            mat = 'brass' if glazed else 'walnut'
            for side in (-1, 1):
                face = w.c1 if side > 0 else w.c0
                c0, c1 = sorted((face, face + side * .018))
                for a0, a1, z0, z1 in ((o.a0 - .06, o.a0, o.z0, o.z1 + .06), (o.a1, o.a1 + .06, o.z0, o.z1 + .06), (o.a0 - .06, o.a1 + .06, o.z1, o.z1 + .06)):
                    if w.axis == 'x':
                        trim.box(a0, a1, c0, c1, z0, z1, mat)
                    else:
                        trim.box(c0, c1, a0, a1, z0, z1, mat)
            if o.z0 - L.FLOOR_Z > .1:          # a hatch: a sill board instead of a threshold
                z = o.z0
                if w.axis == 'x':
                    trim.box(o.a0 - .03, o.a1 + .03, w.c0 - .08, w.c1 + .08, z - .03, z, 'walnut')
                else:
                    trim.box(w.c0 - .08, w.c1 + .08, o.a0 - .03, o.a1 + .03, z - .03, z, 'walnut')
            elif w.axis == 'x':
                trim.box(o.a0, o.a1, w.c0 - .02, w.c1 + .02, L.FLOOR_Z - .006, L.FLOOR_Z + .004, 'brass')
            else:
                trim.box(w.c0 - .02, w.c1 + .02, o.a0, o.a1, L.FLOOR_Z - .006, L.FLOOR_Z + .004, 'brass')
    trim.obj('Interior_Trim', coll, parent=parent, lods=(0,))


def window_frames(c, coll, parent, glass_coll, glass_parent):
    ext = M(); inner = M(); glass = M()
    for w in c.windows:
        zc, h = (w.sill + w.head) / 2, w.head - w.sill
        opening = rrect(w.x, zc, w.width, h, L.WIN_RADIUS)
        out = rrect(w.x, zc, w.width + .11, h + .11, L.WIN_RADIUS + .055)
        lip = rrect(w.x, zc, w.width - .03, h - .03, L.WIN_RADIUS - .015)
        sy = w.side
        inner.ring(rrect(w.x, zc, w.width + .13, h + .13, L.WIN_RADIUS + .065), lip, 'y', sy * (L.IN + .002), sy * (L.IN - .03), 'brass')
        if w.kind == 'bay':               # a projecting lookout: its own glazed box outside the opening
            lookout_bay(w, coll, parent, glass)
            continue
        ext.ring(out, lip, 'y', sy * (L.HALF - .002), sy * (L.HALF + .014), 'brass')
        y = sy * (L.IN + L.WALL * .55)
        glass.poly([(u, y, v) for u, v in opening], 'glass' if w.kind == 'clear' else 'glass-frosted', normal=(0, sy, 0))
    ext.obj('Shell_WindowFrames', coll, parent=parent)
    inner.obj('Interior_WindowFrames', coll, parent=parent, lods=(0,))
    o = glass.obj('Glazing_Windows', glass_coll, parent=glass_parent, closed=False, lods=(0, 1))
    return o


def lookout_bay(w, coll, parent, glass, depth=.24):
    """The guard's projecting lookout (a ducket): a glazed box standing out from the side wall over an opening."""
    sy = w.side
    x0, x1 = w.x - w.width / 2 - .10, w.x + w.width / 2 + .10
    z0, z1 = w.sill - .16, w.head + .16
    ya, yb = sorted((sy * (L.HALF - .01), sy * (L.HALF + depth)))
    m = M()
    m.box(x0, x1, ya, yb, z0, z1, 'livery-ivory')
    o = m.obj(f'Shell_Lookout_{w.name}', coll, parent=parent)
    yi0, yi1 = sorted((sy * (L.HALF - .05), sy * (L.HALF + depth - .04)))
    hole = M(); hole.box(x0 + .04, x1 - .04, yi0, yi1, z0 + .05, z1 - .05, 'glass')           # hollow it out
    front = M(); front.prism(rrect(w.x, (w.sill + w.head) / 2, w.width - .04, w.head - w.sill, .06), 'y', yb - sy * .08 if sy > 0 else ya - .02,
                             yb + .02 if sy > 0 else ya + .08, 'glass')
    sides = []
    for xe in (x0, x1):
        sd = M(); sd.prism(rrect((ya + yb) / 2 + sy * .02, (w.sill + w.head) / 2, depth - .10, w.head - w.sill - .10, .04), 'x', xe - .06, xe + .06, 'glass')
        sides.append(sd)
    boolean(o, [hole, front] + sides)
    reproject(o, lambda n, ctr: 'livery-ivory' if abs(ctr.y) > L.HALF + .02 or abs(n.y) < .5 else 'walnut')
    yf = sy * (L.HALF + depth - .02)
    glass.poly([(u, yf, v) for u, v in rrect(w.x, (w.sill + w.head) / 2, w.width - .04, w.head - w.sill, .06)], 'glass', normal=(0, sy, 0))
    for xe, sx in ((x0 + .01, -1), (x1 - .01, 1)):
        pts = rrect((ya + yb) / 2 + sy * .02, (w.sill + w.head) / 2, depth - .10, w.head - w.sill - .10, .04)
        glass.poly([(xe, u, v) for u, v in pts], 'glass', normal=(sx, 0, 0))
    cap = M()                             # a small sloped roof and a brass rim
    cap.box(x0 - .03, x1 + .03, min(ya, yb) - .0, max(ya, yb) + .03 * (1 if sy > 0 else 0) + (.03 if sy < 0 else 0), z1, z1 + .04, 'roof')
    cap.box(x0, x1, ya, yb, z1 - .02, z1, 'brass')
    cap.obj(f'Shell_LookoutRoof_{w.name}', coll, parent=parent)


def cargo_door(c, d, coll, parent, glass_coll):
    """A pair of luggage-door leaves on the outer face of the side, sliding apart along it (open_offset_m per leaf)."""
    name, sy, x0, x1, z0, z1 = next(e for e in L.exterior_openings(c) if e[0] == d.name.replace('cargo-door', 'cargo'))
    yc = sy * (L.HALF + .025)
    hw = d.width
    for k, (sign, xc) in enumerate(((-1, x0 + hw / 2 - .02), (1, x1 - hw / 2 + .02))):
        m = M(); g = M()
        m.box(-hw / 2, hw / 2, -.022, .022, 0, L.BELT_Z - z0, 'livery-blue')
        m.box(-hw / 2, hw / 2, -.022, .022, L.BELT_Z - z0, z1 - z0 + .04, 'livery-ivory')
        leaf = m.obj(f'Door_{d.name}_{k + 1}', coll, parent=parent)
        win = M(); win.prism(rrect(0, 1.45, .34, .44, .05), 'y', -.08, .08, 'glass')
        boolean(leaf, [win])
        belt = L.BELT_Z - z0
        reproject(leaf, lambda n, ctr: ('livery-blue' if ctr.z < belt else 'livery-ivory') if abs(n.y) > .7 else 'walnut')
        t = M()
        t.ring(rrect(0, 1.45, .42, .52, .09), rrect(0, 1.45, .33, .43, .045), 'y', sy * .02, sy * .034, 'brass')
        for xb in (-hw / 2 + .04, hw / 2 - .04):
            t.box(xb - .006, xb + .006, *sorted((sy * .022, sy * .028)), .12, z1 - z0 - .08, 'brass')
        hx = sign * -(hw / 2 - .10)
        t.box(hx - .014, hx + .014, *sorted((sy * .022, sy * .052)), .90, 1.20, 'brass')
        t.box(-hw / 2 - .02, hw / 2 + .02, *sorted((sy * .022, sy * .06)), z1 - z0 + .04, z1 - z0 + .09, 'end-dark')   # running rail
        tr = t.obj(f'Door_{d.name}_{k + 1}_Trim', coll); tr.parent = leaf
        g.poly([(u, 0, v) for u, v in rrect(0, 1.45, .34, .44, .05)], 'glass', normal=(0, sy, 0))
        go = g.obj(f'Glazing_Door_{d.name}_{k + 1}', glass_coll, closed=False); go.parent = leaf
        leaf.location = (xc, yc, z0)
        DOOR_RECORDS.append(dict(name=leaf.name, door=d.name, kind='sliding', pivot=[xc, yc, z0], open_offset_m=[sign * (hw - .05), 0, 0],
                                 opening=[x0, x1, z0, z1], wall=f'side-{"l" if sy > 0 else "r"}'))


# --- doors --------------------------------------------------------------------------------------------------------
DOOR_RECORDS = []


def _door_leaf(name, width, height, thick, glazed, coll, parent, glass_coll, glass_parent, origin, axis, panel_mat='walnut'):
    """A leaf built about its own origin (bottom centre), long side along `axis` ('x' or 'y')."""
    m = M(); g = M()
    def B(a0, a1, t0, t1, z0, z1, mat, front=None, front_mat=None):
        if axis == 'x':
            m.box(a0, a1, t0, t1, z0, z1, mat, front, front_mat)
        else:
            m.box(t0, t1, a0, a1, z0, z1, mat, front, front_mat)
    hw, ht = width / 2, thick / 2
    if glazed:
        stile, rail, mid = .085, .09, .92
        B(-hw, -hw + stile, -ht, ht, 0, height, 'walnut'); B(hw - stile, hw, -ht, ht, 0, height, 'walnut')
        B(-hw + stile, hw - stile, -ht, ht, height - rail, height, 'walnut')
        for s in (-1, 1):
            t0, t1 = sorted((s * ht, s * (ht - .004)))
            B(-hw + stile, hw - stile, -ht, ht, 0, mid, 'walnut', front=('y' if axis == 'x' else 'x', s), front_mat='panel-tall')
        B(-hw + stile, hw - stile, -ht, ht, mid, mid + .05, 'brass')
        for s in (-1, 1):                 # brass glazing beads
            t0, t1 = sorted((s * ht, s * (ht + .008)))
            for a0, a1, z0, z1 in ((-hw + stile, -hw + stile + .02, mid, height - rail), (hw - stile - .02, hw - stile, mid, height - rail),
                                   (-hw + stile, hw - stile, height - rail - .02, height - rail), (-hw + stile, hw - stile, mid + .05, mid + .07)):
                B(a0, a1, t0, t1, z0, z1, 'brass')
        pts = [(-hw + stile, mid + .05), (hw - stile, mid + .05), (hw - stile, height - rail), (-hw + stile, height - rail)]
        if axis == 'x':
            g.poly([(u, 0, v) for u, v in pts], 'glass', normal=(0, 1, 0))
        else:
            g.poly([(0, u, v) for u, v in pts], 'glass', normal=(1, 0, 0))
    else:
        B(-hw, hw, -ht, ht, 0, height, 'walnut', front=('y' if axis == 'x' else 'x', 1), front_mat=panel_mat)
    for s in (-1, 1):                     # handles
        t0, t1 = sorted((s * ht, s * (ht + .03)))
        a = hw - .09
        B(a - .012, a + .012, t0, t1, 1.0, 1.22, 'brass')
    leaf = m.obj(f'Door_{name}', coll, origin=(0, 0, 0), parent=parent)
    leaf.location = origin
    leaf.parent = parent
    if g.faces:
        go = g.obj(f'Glazing_Door_{name}', glass_coll, closed=False)
        go.parent = leaf
    return leaf


def doors(c, coll, parent, glass_coll, glass_parent):
    DOOR_RECORDS.clear()
    walls = {w.name: w for w in c.walls}
    for d in c.doors:
        if d.kind == 'hinged' and d.name.startswith('exterior'):
            _exterior_door(c, d, coll, parent, glass_coll)
            continue
        if d.kind == 'cargo':
            cargo_door(c, d, coll, parent, glass_coll)
            continue
        w = walls[d.wall]
        o = next(o for o in w.openings if o.name == d.opening)
        thick = .035
        height = o.z1 - o.z0 + .03
        face = w.c1 if d.face > 0 else w.c0
        t = face + d.face * (.006 + thick / 2)
        if d.kind == 'sliding':
            a = (o.a0 + o.a1) / 2
            origin = (a, t, o.z0) if w.axis == 'x' else (t, a, o.z0)
            leaf = _door_leaf(d.name, d.width, height, thick, d.glazed, coll, parent, glass_coll, None, origin, w.axis)
            dirv = [d.slide * (o.a1 - o.a0), 0, 0] if w.axis == 'x' else [0, d.slide * (o.a1 - o.a0), 0]
            DOOR_RECORDS.append(dict(name=leaf.name, door=d.name, kind='sliding', pivot=list(origin), open_offset_m=dirv, opening=[o.a0, o.a1, o.z0, o.z1], wall=w.name))
        else:                               # hinged: two leaves (double) or one, hinged at the `slide` end
            leaves = ((o.a0, 1, -90), (o.a1, -1, 90)) if d.kind == 'double' else (((o.a0, 1, -90),) if d.slide < 0 else ((o.a1, -1, 90),))
            for k, (hinge, direction, swing) in enumerate(leaves):
                lw = (o.a1 - o.a0) / len(leaves)
                a = hinge + direction * lw / 2
                t = w.c1 if d.face > 0 else w.c0
                origin = (t + d.face * thick / 2, a, o.z0)
                leaf = _door_leaf(f'{d.name}_{k + 1}' if len(leaves) > 1 else d.name, lw - .005, o.z1 - o.z0, thick, d.glazed, coll, parent, glass_coll, None, origin, 'y')
                # move the origin to the hinge, keeping the leaf where it is
                shift = Vector((0, hinge - a, 0))
                leaf.data.transform(__import__('mathutils').Matrix.Translation(-shift))
                for ch in leaf.children:
                    ch.location -= shift
                leaf.location = Vector(origin) + shift
                DOOR_RECORDS.append(dict(name=leaf.name, door=d.name, kind='hinged', pivot=list(leaf.location), swing_deg=swing * d.face, opening=[o.a0, o.a1, o.z0, o.z1], wall=w.name))
    gates(c, coll, parent)


def gates(c, coll, parent):
    """A brass gate in the railing gap over each balcony's steps: hung on the post at its end-wall side, swinging in
    over the balcony (collision.doors() gives it its Interact points and box)."""
    F = L.FLOOR_Z
    for s, end in ((-1, 'a'), (1, 'b')):
        if B.end(s) != 'balcony':
            continue
        gx0, gx1 = L.balcony_gate(B, s)
        hinge = CO.gate_hinge(B, s)
        dx = 1 if hinge == gx0 else -1
        n = gx1 - gx0 - .06                       # clear of both posts
        for side, sy in (('l', 1), ('r', -1)):
            m = M()
            u0, u1 = sorted((dx * .03, dx * (.03 + n)))
            for z in (.48, 1.02):
                m.box(u0, u1, -.016, .016, z - .016, z + .016, 'brass')
            for u in (u0 + .014, u1 - .014):
                m.cylinder((u, 0), 'z', .018, .05, 1.04, 'brass', 8)
            for k in range(1, 5):
                m.cylinder((u0 + (u1 - u0) * k / 5, 0), 'z', .010, .06, 1.02, 'brass', 6)
            leaf = m.obj(f'Door_gate-{end}{side}', coll, parent=parent)
            pivot = (hinge, sy * (L.IN - .025), F)
            leaf.location = pivot
            DOOR_RECORDS.append(dict(name=leaf.name, door=f'gate-{end}{side}', kind='hinged', pivot=list(pivot), swing_deg=-90 * sy * dx,
                                     opening=[gx0, gx1, F, F + 1.05], wall='railing'))


def _exterior_door(c, d, coll, parent, glass_coll):
    name, sy, x0, x1, z0, z1 = next(e for e in L.exterior_openings(c) if e[0] == d.name.replace('exterior-door', 'exterior'))
    sx = -1 if x0 < 0 else 1
    hinge_x = x0 if sx < 0 else x1          # hinged on the end-wall side, opening inward
    yc = sy * (L.IN + L.WALL / 2)
    w = x1 - x0 + .01
    te, ti = sy * .026, -sy * .026          # exterior and interior faces of the leaf
    m = M(); g = M()
    # built relative to the hinge: the leaf runs from the hinge towards the coach centre (-sx)
    a0, a1 = sorted((0, -sx * w))
    m.box(a0, a1, -.026, .026, 0, L.BELT_Z - z0, 'livery-blue')
    m.box(a0, a1, -.026, .026, L.BELT_Z - z0, z1 - z0 + .01, 'livery-ivory')
    leaf = m.obj(f'Door_{d.name}', coll, parent=parent)
    oval_c = (-sx * w / 2, 1.42)
    cut = M(); cut.prism(ellipse(*oval_c, .30, .56, 24), 'y', -.08, .08, 'glass')
    boolean(leaf, [cut])
    belt = L.BELT_Z - z0
    reproject(leaf, lambda n, ctr: ('livery-blue' if ctr.z < belt else 'livery-ivory') if n.y * sy > .7
              else 'walnut' if n.y * sy < -.7 else ('livery-blue' if ctr.z < belt else 'livery-ivory'))
    trim = M()
    trim.ring(ellipse(*oval_c, .38, .64, 24), ellipse(*oval_c, .285, .545, 24), 'y', te - sy * .002, te + sy * .012, 'brass')
    trim.ring(ellipse(*oval_c, .36, .62, 24), ellipse(*oval_c, .285, .545, 24), 'y', ti + sy * .002, ti - sy * .012, 'brass')
    for t in (te, ti):                      # handles on both faces
        ta, tb = sorted((t, t + (t / abs(t)) * .03))
        trim.box(-sx * (w - .10) - .014, -sx * (w - .10) + .014, ta, tb, .95, 1.15, 'brass')
    ta, tb = sorted((te, te + sy * .004))
    for z in (.30, belt - .10):             # lining on the blue lower panel
        trim.box(min(0, -sx * w) + .05, max(0, -sx * w) - .05, ta, tb, z, z + .008, 'brass')
    tr = trim.obj(f'Door_{d.name}_Trim', coll)
    tr.parent = leaf
    g.poly([(u, 0, v) for u, v in ellipse(*oval_c, .30, .56, 24)], 'glass', normal=(0, sy, 0))
    go = g.obj(f'Glazing_Door_{d.name}', glass_coll, closed=False)
    go.parent = leaf
    leaf.location = (hinge_x, yc, z0)
    swing = 90 * sy * sx
    DOOR_RECORDS.append(dict(name=leaf.name, door=d.name, kind='hinged', pivot=[hinge_x, yc, z0], swing_deg=swing, opening=[x0, x1, z0, z1],
                             wall=f'side-{"l" if sy > 0 else "r"}'))


DOOR_RULES = dict(interact='D-pad down (Interact) opens or closes the one door whose handle point is nearest; never all '
                  'together', opens={'station': 'only while the train is stopped at a station (exterior doors, balcony gates)',
                                     'any': 'at any time (gangway and inside doors)'},
                  staff='the cab doors open for the crew only; passengers get the "locked" prompt',
                  locked='a locked door keeps its gangway-lock box shut and the Interact prompt reads "locked" for passengers',
                  collision='opening a door removes its collision object (COL_<mesh>_<part>); closing it puts it back')


def door_interactions(c, mesh_name):
    """collision.doors() with the leaves that build made for each door (its hinge pivot and swing, or its slide
    offset) and the name of its switchable collision object."""
    out = []
    for d in CO.doors(c):
        key = d['door'] or d['id']
        leaves = [{k: r[k] for k in ('name', 'kind', 'pivot', 'swing_deg', 'open_offset_m') if k in r} for r in DOOR_RECORDS if r['door'] == key]
        out.append(dict(d, box=[round(v, 4) for v in d['box']], leaves=leaves, collision=f'COL_{mesh_name}_{d["part"]}'))
    return out


# --- reservations, markers, collision -----------------------------------------------------------------------------
def fittings(c, coll, parent):
    """The fittings on the coach's mounts (fittings.py): one object per kind, plus an empty where each bulb's runtime
    light goes. Every mount that is not a gameplay anchor must get its geometry."""
    parts = FT.fittings(c)
    if c.name in FT.COACHES:
        made = {p.name for p in parts}
        bare = sorted({mt.kind for mt in c.mounts if mt.kind not in FT.ANCHORS | FT.BUILT and not made & set(FT.KINDS.get(mt.kind, ()))})
        if bare:
            raise SystemExit(f'{c.name}: mounts without fittings: {bare}')
    for p in parts:
        m = M(); m.faces = list(p.faces)
        m.obj(p.name, coll, parent=parent, closed=p.closed, lods=p.lods, smooth_angle=p.smooth)
        for name, loc in p.sockets:
            so = bpy.data.objects.new(name, None); so.empty_display_type = 'SPHERE'; so.empty_display_size = .05
            so.location = loc; so['lods'] = [0, 1]; so['light'] = 'bulb'
            coll.objects.link(so); so.parent = parent
    return parts


def reservations(c, coll, parent):
    spec = {a['id']: a for a in L.contract()['assets']}
    for p in c.placements:
        a = spec[p.asset]; d = a['dimensions_m']
        w, dep, h = d['width'], d['depth'], d['height']
        m = M()
        if a['pivot'] == 'wall_mount_center':
            m.box(-w / 2, w / 2, -dep, 0, -h / 2, h / 2, 'reservation')
        else:
            m.box(-w / 2, w / 2, -dep / 2, dep / 2, 0, h, 'reservation')
        m.box(-.02, .02, -dep / 2 - .06 if a['pivot'] != 'wall_mount_center' else -dep - .06, -dep / 2 if a['pivot'] != 'wall_mount_center' else -dep, 0 if a['pivot'] != 'wall_mount_center' else -.02, .04, 'gauge')
        o = m.obj(f'FURN_{p.id}', coll, lods=())
        o.location = (p.x, p.y, p.z); o.rotation_euler = (0, 0, math.radians(p.yaw)); o.parent = parent
        o['asset'] = p.asset; o['room'] = p.room; o['yaw_deg'] = p.yaw
    for b in c.reservations:
        m = M(); m.box(b.x0, b.x1, b.y0, b.y1, b.z0, b.z1, 'reservation-service')
        o = m.obj(f'RES_{b.name}', coll, parent=parent, lods=())
        o['kind'] = b.kind; o['note'] = b.note
    for s in c.seats:
        e = bpy.data.objects.new(f'SEAT_{s.id}', None); e.empty_display_type = 'SINGLE_ARROW'; e.empty_display_size = .25
        e.location = (s.x, s.y, s.z); e.rotation_euler = (math.radians(90), 0, math.radians(s.yaw + 180))
        e['furniture'] = s.furniture; e['yaw_deg'] = s.yaw; e['lods'] = []
        coll.objects.link(e); e.parent = parent
    for mt in c.mounts:
        e = bpy.data.objects.new(f'MOUNT_{mt.id}', None); e.empty_display_type = 'PLAIN_AXES'; e.empty_display_size = .12
        e.location = (mt.x, mt.y, mt.z); e.rotation_euler = (0, 0, math.radians(mt.yaw))
        e['kind'] = mt.kind; e['length_m'] = mt.length; e['lods'] = []
        coll.objects.link(e); e.parent = parent


def collision(c, coll, parent, mesh_name):
    out = []
    for name, n, g, b in CO.named_boxes(c, mesh_name):
        m = M(); m.box(*b, 'reservation-service')
        o = m.obj(name, coll, parent=parent, lods=())
        o['part'] = n; o['group'] = g; o.display_type = 'WIRE'
        out.append(o)
    return out


def window_cards(c, m, y_out):
    """Each window as a card facing out at y_out from the side: the clear ones on the interior atlas (parts.py), the
    frosted ones dark."""
    _, tiles = PT.window_tiles(c)
    for w in c.windows:
        y = w.side * y_out
        pts = [(w.x - w.width / 2, y, w.sill), (w.x + w.width / 2, y, w.sill), (w.x + w.width / 2, y, w.head), (w.x - w.width / 2, y, w.head)]
        if w.name in tiles:
            m.poly(pts, 'window-interior', uv=PT.window_uv(w, tiles[w.name]), normal=(0, w.side, 0))
        else:
            m.poly(pts, 'glass-dark', normal=(0, w.side, 0))


def lod2_hull(c, coll, parent):
    m = M()
    m.box(B.x_a, B.x_b, -L.HALF, L.HALF, L.SKIRT_Z, L.BELT_Z, 'livery-blue')
    m.box(B.x_a, B.x_b, -L.HALF, L.HALF, L.BELT_Z, L.CANT_Z, 'livery-ivory')
    window_cards(c, m, L.HALF + .003)
    for name, sy, x0, x1, z0, z1 in L.exterior_openings(c):
        y = sy * (L.HALF + .002)
        m.poly([(x0, y, z0), (x1, y, z0), (x1, y, z1), (x0, y, z1)], 'livery-blue', normal=(0, sy, 0))
    for sx in (-1, 1):
        x0, x1 = sorted((B.headstock(sx), B.buffer(sx)))
        m.box(x0, x1, -L.GANGWAY_W / 2 - .18, L.GANGWAY_W / 2 + .18, L.FLOOR_Z - .06, L.FLOOR_Z + L.GANGWAY_H + .2, 'rubber')
        for sy in (-1, 1):
            m.box(x0, x1, sy * L.BUFFER_Y - .15, sy * L.BUFFER_Y + .15, L.BUFFER_Z - .15, L.BUFFER_Z + .15, 'undercarriage')
    m.box(-7, 7, -1.2, 1.2, .45, L.SKIRT_Z, 'undercarriage')
    m.obj('LOD2_Hull', coll, parent=parent, lods=(2,), closed=False)


# --- export -------------------------------------------------------------------------------------------------------
def tris(objs):
    n = 0
    dg = bpy.context.evaluated_depsgraph_get()
    for o in objs:
        if o.type == 'MESH':
            n += sum(len(p.vertices) - 2 for p in o.data.polygons)
    return n


def export_glb(path, objs):
    bpy.ops.object.select_all(action='DESELECT')
    for o in objs:
        o.hide_set(False); o.select_set(True)
    bpy.ops.export_scene.gltf(filepath=str(path), export_format='GLB', use_selection=True, export_yup=True, export_apply=True,
                              export_extras=True, export_materials='EXPORT', export_image_format='AUTO', export_cameras=False,
                              export_lights=False, export_animations=False)
    bpy.ops.object.select_all(action='DESELECT')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def mesh_checks(objs):
    """Closed meshes (manifold, outward) and no degenerate faces in the architectural parts."""
    report = {}
    for o in objs:
        if o.type != 'MESH' or o.name.startswith(('Glazing', 'Interior_Floor', 'Ceiling', 'Shell_Crest', 'LOD2_Hull', 'Roof_Details', 'Roof_CupolaTop', 'Tender_Coal', 'Loco_SmokeboxDoor', 'Cab_BackheadFace', 'Cab_FireGlow', 'Fittings_')):
            continue
        bm = bmesh.new(); bm.from_mesh(o.data)
        boundary = sum(1 for e in bm.edges if e.is_boundary)
        nonman = sum(1 for e in bm.edges if not e.is_manifold and not e.is_boundary)
        degenerate = sum(1 for f in bm.faces if f.calc_area() < 1e-9)
        vol = bm.calc_volume(signed=True)
        bm.free()
        report[o.name] = dict(boundary_edges=boundary, non_manifold_edges=nonman, degenerate_faces=degenerate, signed_volume_m3=round(vol, 4))
    return report


# --- the tender ---------------------------------------------------------------------------------------------------
def _tank_section(hw, z0, z1, r, seg=6):
    """The tank's cross-section in (y, z): square at the bottom, rounded along the top edges."""
    pts = [(-hw, z0), (hw, z0)]
    for cy, a0 in ((hw - r, 0), (-hw + r, 90)):
        for k in range(seg + 1):
            a = math.radians(a0 + 90 * k / seg)
            pts.append((cy + r * math.cos(a), z1 - r + r * math.sin(a)))
    return pts


def tender_body(c, coll, parent, glass_coll):
    """Tank with the shovelling hole, coping plates and coal heap, footplate, lockers, frames, axles and ends."""
    hw, (ta, tb), (z0, z1) = L.TENDER_HALF, L.TENDER_TANK, L.TENDER_TANK_Z
    hs = L.TENDER_HEADSTOCK
    hy, hb, ht = L.COAL_HOLE
    # the riveted tank, its front face (the coal plate) cut by the coal hole into a dark pocket
    m = M(); m.prism(_tank_section(hw, z0, z1, .28), 'x', ta, tb, 'loco-black')
    tank = m.obj('Tender_Tank', coll, parent=parent)
    cut = M(); cut.box(tb - .62, tb + .10, -hy, hy, hb, ht, 'end-dark')
    boolean(tank, [cut])
    pocket = lambda ctr: ctr.x > tb - .63 and abs(ctr.y) < hy + .005 and hb - .005 < ctr.z < ht + .005 and ctr.x < tb - .002
    reproject(tank, lambda n, ctr: 'end-dark' if pocket(ctr) else 'roof' if n.z > .9 and ctr.z > z1 - .01 else 'loco-black')
    # coal seen through the hole, sloping back up into the tank
    m = M()
    m.poly([(tb - .02, -hy, hb + .02), (tb - .02, hy, hb + .02), (tb - .60, hy, ht - .02), (tb - .60, -hy, ht - .02)], 'coal', normal=(1, 0, 1))
    # the coal heap on top, inside the coping plates
    (ca, cb), cz = L.TENDER_COAL, L.TENDER_COPING_Z
    nx, ny = 24, 16
    def heap(x, y):
        t = max(0., 1 - ((x - (ca + cb) / 2 - .10) / ((cb - ca) / 2 + .25)) ** 2) * max(0., 1 - (y / (hw + .15)) ** 2)
        lumps = .045 * math.sin(17 * x + 3 * y) * math.cos(13 * y - 5 * x) + .03 * math.sin(29 * x * y + 7 * y)
        return cz - .17 + .40 * t + lumps
    xs = [ca + (cb - ca) * i / nx for i in range(nx + 1)]
    ys = [-(hw - .05) + 2 * (hw - .05) * j / ny for j in range(ny + 1)]
    for i in range(nx):
        for j in range(ny):
            q = [(xs[i], ys[j]), (xs[i + 1], ys[j]), (xs[i + 1], ys[j + 1]), (xs[i], ys[j + 1])]
            m.poly([(x, y, heap(x, y)) for x, y in q], 'coal', normal=(0, 0, 1))
    m.obj('Tender_Coal', coll, parent=parent, closed=False, smooth_angle=60)
    # coping plates round the coal space, with a brass capping
    m = M(); trim = M()
    for sy in (-1, 1):
        y0, y1 = sorted((sy * (hw - .05), sy * hw))
        m.box(ca - .06, tb, y0, y1, z1 - .25, cz, 'loco-black')
        trim.box(ca - .06, tb, y0 - .006, y1 + .006, cz, cz + .02, 'brass')
    for x0, zb in ((ca - .06, z1 - .05), (tb - .06, z1 - .25)):     # end boards, clear of the side plates
        m.box(x0, x0 + .06, -hw + .052, hw - .052, zb, cz, 'loco-black')
    for x in (ca - .06, tb - .06):
        trim.box(x - .006, x + .066, -hw, hw, cz, cz + .02, 'brass')
    m.obj('Tender_Coping', coll, parent=parent)
    # footplate, fall plate and lockers
    m = M()
    lx0, lx1, ly, lz = L.TENDER_LOCKER
    m.box(tb, hs, -hw + .10, hw - .10, z0 + .05, L.FLOOR_Z, 'parquet')
    m.box(hs, L.TENDER_FALL_PLATE, -.95, .95, L.FLOOR_Z - .018, L.FLOOR_Z, 'steel')
    for sy in (-1, 1):
        y0, y1 = sorted((sy * ly, sy * hw))
        m.box(lx0, lx1, y0, y1, L.FLOOR_Z, lz, 'loco-black')
        trim.box(lx0, lx1 + .02, y0 - .01, y1 + .01, lz, lz + .03, 'brass')
    m.obj('Tender_Footplate', coll, parent=parent)
    # locker doors (hinged at the outer side, opening towards the cab) and the coal-hole shutter (slides up)
    for side, sy in (('l', 1), ('r', -1)):
        w = hw - ly - .08
        d = M()
        a0, a1 = sorted((0, -sy * w))
        d.box(0, .03, a0, a1, 0, lz - L.FLOOR_Z - .14, 'loco-black')
        for z in (.10, lz - L.FLOOR_Z - .24):
            d.box(.03, .034, a0 + .05, a1 - .05, z, z + .008, 'brass')
        d.box(.03, .06, -sy * (w - .07) - .012, -sy * (w - .07) + .012, .50, .70, 'brass')
        leaf = d.obj(f'Door_tender-locker-{side}', coll, parent=parent)
        hinge = (lx1, sy * (hw - .04), L.FLOOR_Z + .07)
        leaf.location = hinge
        DOOR_RECORDS.append(dict(name=leaf.name, door=f'tender-locker-{side}', kind='hinged', pivot=list(hinge), swing_deg=90 * sy,
                                 opening=[sy * ly, sy * (hw - .04), L.FLOOR_Z + .07, lz - .07], wall=f'locker-{side}'))
    d = M()
    d.box(-.01, .01, -hy - .05, hy + .05, 0, ht - hb + .08, 'end-dark')
    d.box(.01, .04, -.10, .10, .06, .10, 'brass')
    shutter = d.obj('Door_coal-hole', coll, parent=parent)
    shutter.location = (tb + .012, 0, hb - .04)
    DOOR_RECORDS.append(dict(name=shutter.name, door='coal-hole', kind='sliding', pivot=list(shutter.location),
                             open_offset_m=[0, 0, ht - hb + .02], opening=[-hy, hy, hb, ht], wall='coal-plate'))
    # the coal hole's ironwork: a steel shovelling plate at its sill, channel guides the shutter slides up in (as far
    # as its stop bar), and the lamp irons on the tank's rear face (a plate, an arm and the tongue a lamp drops onto)
    f = M()
    lift = ht - hb + .02
    f.box(tb - .25, tb + .05, -hy - .02, hy + .02, hb - .015, hb, 'steel')
    for sy in (-1, 1):
        f.box(tb, tb + .034, sy * (hy + .055), sy * (hy + .085), hb - .06, ht + .04 + lift, 'iron-black')   # cheek, beside the shutter
        f.box(tb + .024, tb + .034, sy * (hy + .03), sy * (hy + .055), hb - .06, ht + .04 + lift, 'iron-black')   # lip, over its edge
    f.box(tb, tb + .034, -hy - .10, hy + .10, ht + .04 + lift, ht + .08 + lift, 'iron-black')     # stop bar
    for mt in (mo for mo in c.mounts if mo.kind == 'lamp-bracket'):
        x, y, z = mt.x, mt.y, mt.z
        f.box(ta - .008, ta, y - .035, y + .035, z - .07, z + .03, 'iron-black')
        f.box(x - .006, ta - .008, y - .022, y + .022, z - .07, z - .058, 'iron-black')
        f.box(x - .006, x + .006, y - .022, y + .022, z - .07, z + .07, 'iron-black')
    f.obj('Tender_Ironwork', coll, parent=parent)
    # brass handrails at the footplate's open sides, hanging steps below them
    for sy in (-1, 1):
        for x in (lx1 + .04, hs - .05):
            trim.cylinder((x, sy * (hw - .08)), 'z', .018, L.FLOOR_Z, L.FLOOR_Z + 1.20, 'brass', 8)
        trim.box(lx1 + .04, hs - .05, sy * (hw - .08) - .016, sy * (hw - .08) + .016, L.FLOOR_Z + .94, L.FLOOR_Z + .97, 'brass')
        y = sy * hw
        for zz, depth in ((.96, .20), (.66, .30)):
            ya, yb = sorted((y - sy * .25, y + sy * (depth - .25)))
            trim.box(lx1 + .20, hs - .15, ya, yb, zz - .03, zz, 'steel')
        for x in (lx1 + .19, hs - .14):
            trim.box(x - .015, x + .015, min(y - sy * .25, y), max(y - sy * .25, y), .63, z0 + .05, 'undercarriage')
    # tank top: two water fillers, vents and handrails; rear ladder
    for x in (-3.10, -1.40):
        trim.cylinder((x, 0), 'z', .28, z1 - .05, z1 + .12, 'end-dark', 20)
        trim.cylinder((x, 0), 'z', .30, z1 + .12, z1 + .16, 'brass', 20)
        trim.cylinder((x, 0), 'z', .06, z1 + .16, z1 + .22, 'brass', 10)
    for sy in (-1, 1):
        trim.cylinder((-2.30, sy * .85), 'z', .05, z1 - .05, z1 + .35, 'end-dark', 10)
        trim.cylinder((-2.30, sy * .85), 'z', .07, z1 + .35, z1 + .40, 'brass', 10)
        y = sy * (hw - .22)
        for x in (-3.80, -2.60, -1.40, -.20):
            trim.cylinder((x, y), 'z', .015, z1 - .10, z1 + .24, 'brass', 8)
        trim.box(-3.80, -.20, y - .016, y + .016, z1 + .22, z1 + .25, 'brass')
    for y in L.TENDER_LADDER:
        trim.box(ta - .05, ta - .02, y - .02, y + .02, z0, z1 - .05, 'brass')
    for k in range(7):
        z = z0 + .25 + k * .30
        trim.box(ta - .05, ta - .03, *L.TENDER_LADDER, z - .012, z + .012, 'brass')
    # brass lining and the crest on the tank sides
    for sy in (-1, 1):
        y0, y1 = sorted((sy * (hw - .002), sy * (hw + .006)))
        for z in (z0 + .10, z1 - .32):
            trim.box(ta + .08, tb - .08, y0, y1, z - .009, z + .009, 'brass')
        for z in (z0 + .30, z1 - .52):
            trim.box(ta + .30, tb - .30, y0, y1, z - .005, z + .005, 'brass')
        for x in (ta + .30, tb - .30):
            trim.box(x - .005, x + .005, y0, y1, z0 + .30, z1 - .52, 'brass')
        for z in (z0 + .37, z1 - .59):              # red lining inside the brass
            trim.box(ta + .37, tb - .37, y0, y1, z - .005, z + .005, 'lining-red')
        for x in (ta + .37, tb - .37):
            trim.box(x - .005, x + .005, y0, y1, z0 + .37, z1 - .59, 'lining-red')
    trim.obj('Tender_Trim', coll, parent=parent, lods=(0,))
    m = M()
    zc = (z0 + .30 + z1 - .52) / 2
    for sy in (-1, 1):
        y = sy * (hw + .008)
        w = h = .80
        xs2 = (B.crest_x - w / 2, B.crest_x + w / 2)
        pts = [(xs2[0], y, zc - h / 2), (xs2[1], y, zc - h / 2), (xs2[1], y, zc + h / 2), (xs2[0], y, zc + h / 2)]
        if sy < 0:
            pts = [(xs2[1] + xs2[0] - p[0], p[1], p[2]) for p in pts]
        m.poly(pts, 'crest', uv=[(0, 0), (1, 0), (1, 1), (0, 1)], normal=(0, sy, 0))
    m.obj('Shell_Crest', coll, parent=parent, closed=False)
    # outside frames, axleboxes with brass caps, leaf springs, brake gear, headstocks
    m = M()
    for sy in (-1, 1):
        y0, y1 = sorted((sy * 1.18, sy * 1.30))
        m.box(-hs, hs, y0, y1, .58, z0, 'undercarriage')
        for x in L.TENDER_AXLES:
            m.box(x - .17, x + .17, *sorted((sy * 1.30, sy * 1.40)), .30, .74, 'undercarriage')
            m.cylinder((x, L.TENDER_WHEEL_R), 'y', .09, *sorted((sy * 1.40, sy * 1.45)), 'brass', 14)
            for k, (hl, zz) in enumerate(((.60, .78), (.48, .82), (.36, .86), (.24, .90))):
                m.box(x - hl, x + hl, *sorted((sy * 1.20, sy * 1.36)), zz - .04, zz, 'steel')
            for xx in (x - .62, x + .62):
                m.box(xx - .025, xx + .025, *sorted((sy * 1.24, sy * 1.32)), .70, z0, 'undercarriage')
    for x0, x1 in zip(L.TENDER_AXLES, L.TENDER_AXLES[1:]):
        mid = (x0 + x1) / 2
        m.box(mid - .05, mid + .05, -1.18, 1.18, .40, .50, 'undercarriage')
        m.cylinder((.55, .70), 'x', .07, x0 + .55, x1 - .55, 'undercarriage', 10)
    for sx in (-1, 1):
        x0, x1 = sorted((sx * hs - sx * .06, sx * hs + sx * .06))
        m.box(x0, x1, -hw + .05, hw - .05, .86, z0 + .05, 'end-dark')
    m.obj('Tender_Frames', coll, parent=parent)
    # buffers: full-size at the rear (the baggage van), smaller under the fall plate at the front; hooks, hoses
    m = M()
    for sx, head_r in ((-1, .20), (1, .15)):
        bf = B.buffer(sx)
        for sy in (-1, 1):
            x0, x1 = sorted((sx * hs + sx * .06, bf - sx * .06))
            m.cylinder((sy * L.BUFFER_Y, L.BUFFER_Z), 'x', .10, x0, x1, 'undercarriage', 16)
            x0, x1 = sorted((bf - sx * .06, bf))
            m.cylinder((sy * L.BUFFER_Y, L.BUFFER_Z), 'x', head_r, x0, x1, 'steel', 20)
        x0, x1 = sorted((sx * hs + sx * .06, bf - sx * .02))
        m.box(x0, x1, -.06, .06, L.BUFFER_Z - .07, L.BUFFER_Z + .05, 'undercarriage')
        for sy in (-1, 1):
            m.box(sx * hs + sx * .10 - .02, sx * hs + sx * .10 + .02, sy * .35 - .02, sy * .35 + .02, .80, 1.10 if sx > 0 else 1.15, 'rubber')
    m.box(B.buffer(-1) + .04 - .03, B.buffer(-1) + .04 + .03, -.12, .12, L.BUFFER_Z - .20, L.BUFFER_Z - .05, 'steel')
    m.obj('Shell_Buffers', coll, parent=parent)
    # three wheelsets sharing one mesh, origins at their axles
    w = M()
    r = L.TENDER_WHEEL_R
    for sy in (-1, 1):
        y0, y1 = sorted((sy * (L.GAUGE / 2 - .02), sy * (L.GAUGE / 2 + .11)))
        w.cylinder((0, 0), 'y', r, y0, y1, 'steel', 28)
        f0, f1 = sorted((sy * (L.GAUGE / 2 - .02), sy * (L.GAUGE / 2 + .005)))
        w.cylinder((0, 0), 'y', r + .03, f0, f1, 'steel', 28)
        w.cylinder((0, 0), 'y', .16, *sorted((sy * (L.GAUGE / 2 + .11), sy * (L.GAUGE / 2 + .15))), 'brass', 14)
    w.cylinder((0, 0), 'y', .08, -1.30, 1.30, 'undercarriage', 12)
    wheel_me = None
    for k, x in enumerate(L.TENDER_AXLES):
        if wheel_me is None:
            ws = w.obj(f'Wheelset_{k + 1}', coll, parent=parent); wheel_me = ws.data
        else:
            ws = _linked(f'Wheelset_{k + 1}', wheel_me, coll, (0, 0, 0), parent)
        ws.location = (x, 0, r)


def tender_lod2(c, coll, parent):
    hw, (ta, tb), (z0, z1) = L.TENDER_HALF, L.TENDER_TANK, L.TENDER_TANK_Z
    m = M()
    m.box(ta, tb, -hw, hw, z0, z1, 'livery-blue')
    m.box(L.TENDER_COAL[0], tb, -hw, hw, z1, L.TENDER_COPING_Z, 'coal')
    m.box(tb, L.TENDER_HEADSTOCK, -hw, hw, z0, L.FLOOR_Z, 'parquet')
    m.box(-L.TENDER_HEADSTOCK, L.TENDER_HEADSTOCK, -1.30, 1.30, .05, z0, 'undercarriage')
    for sx in (-1, 1):
        x0, x1 = sorted((sx * L.TENDER_HEADSTOCK, B.buffer(sx)))
        for sy in (-1, 1):
            m.box(x0, x1, sy * L.BUFFER_Y - .15, sy * L.BUFFER_Y + .15, L.BUFFER_Z - .15, L.BUFFER_Z + .15, 'undercarriage')
    m.obj('LOD2_Hull', coll, parent=parent, lods=(2,))


# --- the locomotive -----------------------------------------------------------------------------------------------
def _circle(cx, cz, r, seg=24, a0=0.):
    return [(cx + r * math.cos(a0 + 2 * math.pi * k / seg), cz + r * math.sin(a0 + 2 * math.pi * k / seg)) for k in range(seg)]


def _spoked_wheel(m, r, y0, y1, spokes, crank_angle=None, seg=32):
    """One wheel in the plane of the y axis, centred on the axle at the origin: steel tyre with its flange, black rim,
    spokes, hub with a brass cap and, on coupled wheels, a crank boss and the counterweight opposite it."""
    sy = 1 if y1 > 0 else -1
    m.ring(_circle(0, 0, r, seg), _circle(0, 0, r - .07, seg), 'y', y0, y1, 'steel')
    f0, f1 = sorted((y0 - sy * .0, y0 + sy * .025))
    m.ring(_circle(0, 0, r + .03, seg), _circle(0, 0, r - .02, seg), 'y', f0, f1, 'steel')
    m.ring(_circle(0, 0, r - .07, seg), _circle(0, 0, r - .12, seg), 'y', y0 + sy * .02, y1 - sy * .02, 'end-dark')
    hub = .11 + r * .12
    for k in range(spokes):
        a = 2 * math.pi * k / spokes
        ca, sa = math.cos(a), math.sin(a)
        w0, w1 = .028 + r * .012, .018 + r * .008
        pts = [(hub * ca + w0 * sa, hub * sa - w0 * ca), ((r - .10) * ca + w1 * sa, (r - .10) * sa - w1 * ca),
               ((r - .10) * ca - w1 * sa, (r - .10) * sa + w1 * ca), (hub * ca - w0 * sa, hub * sa + w0 * ca)]
        m.prism(pts, 'y', *sorted((y0 + sy * .03, y1 - sy * .03)), 'end-dark')
    m.prism(_circle(0, 0, hub, 16), 'y', *sorted((y0 + sy * .01, y1 + sy * .02)), 'end-dark')
    m.prism(_circle(0, 0, hub * .55, 12), 'y', *sorted((y1 + sy * .02, y1 + sy * .045)), 'brass')
    if crank_angle is not None:
        ca, sa = math.cos(crank_angle), math.sin(crank_angle)
        m.prism(_circle(L.CRANK * ca, L.CRANK * sa, .10, 12), 'y', *sorted((y0 + sy * .02, y1 + sy * .05)), 'end-dark')
        arc = [((r - .12) * math.cos(crank_angle + math.pi + d), (r - .12) * math.sin(crank_angle + math.pi + d)) for d in np.linspace(-.75, .75, 9)]
        m.prism(arc, 'y', *sorted((y0 + sy * .025, y1 - sy * .015)), 'end-dark')


def _wheelset(name, r, spokes, coll, parent, x, crank_angle=None):
    """A wheelset object, its origin on the axle so it can spin about +Y."""
    w = M()
    for sy in (-1, 1):
        y0, y1 = sy * (L.GAUGE / 2 - .02), sy * (L.GAUGE / 2 + .11)
        _spoked_wheel(w, r, y0, y1, spokes, crank_angle if crank_angle is None else crank_angle + (0 if sy > 0 else math.pi / 2))
    w.cylinder((0, 0), 'y', .09, -L.GAUGE / 2, L.GAUGE / 2, 'undercarriage', 12)
    o = w.obj(name, coll, parent=parent)
    o.location = (x, 0, r)
    return o


def loco_body(c, coll, parent, glass_coll):
    F = L.FLOOR_Z
    hw, cin = L.LOCO_HALF, L.CAB_IN
    (ca, cb), ce = L.CAB, L.CAB_ENTRY
    bx = L.BACKHEAD_X
    (b0, b1, br, bz), (s0, s1, sr) = L.BOILER, L.SMOKEBOX
    rb = L.RUNNING_BOARD_Z
    trim = M()
    # --- boiler, firebox, smokebox, chimney, domes ---
    m = M()
    m.cylinder((0, bz), 'x', br, b0, b1, 'loco-black', 40)
    for k in range(7):                               # brass boiler bands
        x = b0 + .35 + k * (b1 - b0 - .55) / 6
        trim.cylinder((0, bz), 'x', br + .012, x - .025, x + .025, 'brass', 40)
        for dx in (-.075, .075):                     # red lines either side of each band
            trim.cylinder((0, bz), 'x', br + .006, x + dx - .006, x + dx + .006, 'lining-red', 40)
    m.box(b0, -1.90, -1.05, 1.05, rb - .05, bz, 'loco-black')                     # firebox sides under the barrel
    m.obj('Loco_Boiler', coll, parent=parent)
    m = M()
    m.cylinder((0, bz), 'x', sr, s0, s1, 'iron-black', 40)
    m.box(s0 + .10, s1 - .05, -sr + .10, sr - .10, rb - .05, bz - .3, 'iron-black')     # saddle
    m.obj('Loco_Smokebox', coll, parent=parent)
    m = M()
    # a tall stovepipe chimney, as on the classic engines: flared base on the smokebox, slender stack, flared lip
    m.prism(_circle(4.40, 0, .38, 24), 'z', bz + sr - .10, bz + sr - .01, 'iron-black')
    # hollow from the top for the smoke: a sooty floor 0.54 m down, the bore 0.44 m across
    m.prism(_circle(4.40, 0, .27, 24), 'z', bz + sr - .01, 4.12, 'iron-black')
    m.poly([(x, y, 4.121) for x, y in _circle(4.40, 0, .222, 24)], 'coal', normal=(0, 0, 1))
    m.ring(_circle(4.40, 0, .27, 24), _circle(4.40, 0, .22, 24), 'z', 4.12, 4.52, 'iron-black')
    m.ring(_circle(4.40, 0, .31, 24), _circle(4.40, 0, .22, 24), 'z', 4.52, 4.58, 'iron-black')
    trim.ring(_circle(4.40, 0, .34, 24), _circle(4.40, 0, .23, 24), 'z', 4.58, 4.66, 'brass')
    m.prism(_circle(1.20, 0, .36, 24), 'z', bz + br - .06, bz + br + .22, 'brass')     # steam dome
    m.prism(_circle(1.20, 0, .28, 24), 'z', bz + br + .22, bz + br + .30, 'brass')
    m.prism(_circle(-.80, 0, .26, 20), 'z', bz + br - .06, bz + br + .16, 'loco-black')   # sand dome
    trim.prism(_circle(-.80, 0, .20, 20), 'z', bz + br + .16, bz + br + .20, 'brass')
    for y in (-.14, .14):                             # safety valves and whistle
        trim.prism(_circle(-2.60, y, .07, 12), 'z', bz + br - .05, bz + br + .28, 'brass')
    trim.prism(_circle(-3.90, 0, .05, 12), 'z', bz + br - .05, bz + br + .30, 'brass')
    trim.prism(_circle(-3.90, 0, .08, 12), 'z', bz + br + .30, bz + br + .42, 'brass')
    m.obj('Loco_Domes', coll, parent=parent)
    # the smokebox door (a decal plate: assets textures/smokebox-door.jpg when it exists)
    d = M()
    pts = _circle(0, bz, sr - .10, 32)
    d.poly([(s1 + .006, y, z) for y, z in pts], 'smokebox-door', uv=[((y + sr - .10) / (2 * (sr - .10)), (z - bz + sr - .10) / (2 * (sr - .10))) for y, z in pts], normal=(1, 0, 0))
    d.obj('Loco_SmokeboxDoor', coll, parent=parent, closed=False)
    for sy in (-1, 1):                                # boiler handrails
        trim.cylinder((sy * (br + .07), bz + .25), 'x', .014, b0 + .1, s1 - .1, 'brass', 8)
    # --- running boards with their blue valance, front deck, buffer beam ---
    m = M()
    for sy in (-1, 1):
        y0, y1 = sorted((sy * 1.02, sy * hw))
        m.box(cb, 5.40, y0, y1, rb - .04, rb, 'iron-black')
        v0, v1 = sorted((sy * (hw - .03), sy * hw))
        m.box(cb, 5.40, v0, v1, rb - .26, rb, 'loco-black')
        trim.box(cb, 5.40, v0 - sy * .0, v1 + sy * .004, rb - .19, rb - .18, 'brass')
        trim.box(cb, 5.40, v0 - sy * .0, v1 + sy * .004, rb - .13, rb - .122, 'lining-red')
        # the drop to the front deck
        m.prism([(5.40, rb), (5.40, rb - .26), (5.95, 1.30), (5.95, 1.34)], 'y', y0, y1, 'loco-black')
    m.box(5.95, L.LOCO_BEAM, -hw, hw, 1.30, 1.34, 'iron-black')
    m.box(L.LOCO_BEAM, L.LOCO_BEAM + .14, -hw + .05, hw - .05, .85, 1.34, 'end-dark')
    trim.box(L.LOCO_BEAM + .14, L.LOCO_BEAM + .145, -hw + .15, hw - .15, 1.20, 1.22, 'brass')
    m.obj('Loco_RunningBoards', coll, parent=parent)
    # --- frames, cylinders, slide bars ---
    m = M()
    for sy in (-1, 1):
        y0, y1 = sorted((sy * .50, sy * .58))
        m.box(-5.0, L.LOCO_BEAM, y0, y1, .55, 1.45, 'undercarriage')
    x0, x1, cr, cz, cy = L.CYLINDER
    for sy in (-1, 1):
        m.cylinder((sy * cy, cz), 'x', cr, x0, x1, 'loco-black', 24)
        trim.cylinder((sy * cy, cz), 'x', cr + .012, x0 - .01, x0 + .03, 'brass', 24)
        trim.cylinder((sy * cy, cz), 'x', cr + .012, x1 - .03, x1 + .01, 'brass', 24)
        m.box(x0 - .02, x1 + .02, *sorted((sy * .58, sy * (cy - cr + .02))), cz - .12, cz + .12, 'undercarriage')
        for dz in (-.07, .07):                         # slide bars
            m.box(3.55, x0, *sorted((sy * (cy - .03), sy * (cy + .03))), cz + dz - .015, cz + dz + .015, 'steel')
    m.obj('Loco_Frames', coll, parent=parent)
    # --- wheels: leading bogie, three coupled axles, trailing axle; each its own object so it can spin ---
    for k, x in enumerate(L.LEADING):
        _wheelset(f'Wheelset_Leading_{k + 1}', L.LEADING_R, 10, coll, parent, x)
    for k, x in enumerate(L.DRIVERS):
        _wheelset(f'Wheelset_Driver_{k + 1}', L.DRIVER_R, 18, coll, parent, x, crank_angle=0.)
    for k, x in enumerate(L.TRAILING):
        _wheelset(f'Wheelset_Trailing_{k + 1}', L.TRAILING_R, 12, coll, parent, x)
    m = M()                                          # leading bogie frame and axleboxes
    for sy in (-1, 1):
        m.box(L.LEADING[1] - .55, L.LEADING[0] + .55, *sorted((sy * .92, sy * 1.00)), .25, .60, 'undercarriage')
    m.obj('Loco_LeadingBogie', coll, parent=parent)
    # coupling and connecting rods (right side crank at 0, left at 90 degrees), crosshead
    for sy, ang in ((1, 0.), (-1, math.pi / 2)):
        ca_, sa_ = math.cos(ang), math.sin(ang)
        side = 'L' if sy > 0 else 'R'
        yr0, yr1 = sorted((sy * (L.GAUGE / 2 + .17), sy * (L.GAUGE / 2 + .21)))
        rod = M()
        z = L.DRIVER_R + L.CRANK * sa_
        rod.box(L.DRIVERS[-1] + L.CRANK * ca_ - .08, L.DRIVERS[0] + L.CRANK * ca_ + .08, yr0, yr1, z - .05, z + .05, 'steel')
        rod.obj(f'Rod_Coupling_{side}', coll, parent=parent)
        # connecting rod from the crosshead to the middle driver's crank pin
        px, pz = L.DRIVERS[1] + L.CRANK * ca_, L.DRIVER_R + L.CRANK * sa_
        hx, hz = 3.70, cz
        dx, dz = hx - px, hz - pz
        n = math.hypot(dx, dz); ux, uz = -dz / n * .055, dx / n * .055
        yc0, yc1 = sorted((sy * (L.GAUGE / 2 + .22), sy * (L.GAUGE / 2 + .26)))
        con = M()
        con.prism([(px + ux, pz + uz), (px - ux, pz - uz), (hx - ux, hz - uz), (hx + ux, hz + uz)], 'y', yc0, yc1, 'steel')
        con.box(hx - .12, hx + .12, *sorted((sy * (cy - .05), sy * (cy + .05))), cz - .09, cz + .09, 'steel')
        con.box(hx - .03, hx + .03, *sorted((sy * (L.GAUGE / 2 + .22), sy * (cy - .05))), cz - .03, cz + .03, 'steel')
        con.obj(f'Rod_Connecting_{side}', coll, parent=parent)
        for x in L.DRIVERS:                            # crank pins
            trim.cylinder((x + L.CRANK * ca_, z), 'y', .045, *sorted((sy * (L.GAUGE / 2 + .11), sy * (L.GAUGE / 2 + .28))), 'brass', 10)
    # --- cab: floor, sides with windows, front plate with spectacle glasses, roof ---
    m = M()
    m.box(ca, cb, -cin, cin, F - .15, F, 'parquet')
    m.box(ca, cb, -hw, hw, F - .30, F - .15, 'undercarriage')
    m.obj('Cab_Floor', coll, parent=parent)
    for side, sy in (('L', 1), ('R', -1)):
        m = M()
        y0, y1 = sorted((sy * cin, sy * hw))
        m.box(ce, cb, y0, y1, F - .30, L.CAB_TOP, 'loco-black')
        m.box(ca, ce, y0, y1, F - .30, F + .05, 'loco-black')          # kick plate under the entrance
        o = m.obj(f'Cab_Side_{side}', coll, parent=parent)
        cut = M(); cut.prism(rrect(-5.45, F + 1.52, 1.00, .70, .08), 'y', y0 - .05, y1 + .05, 'glass')
        boolean(o, [cut])
        reproject(o, lambda n, ctr, sy=sy: 'loco-black' if n.y * sy > .7 and abs(ctr.y) > hw - 1e-3 else 'walnut' if n.y * sy < -.7 else 'loco-black')
        g = M(); g.poly([(x, sy * (cin + .03), z) for x, z in rrect(-5.45, F + 1.52, 1.00, .70, .08)], 'glass', normal=(0, sy, 0))
        g.obj(f'Glazing_Cab_{side}', glass_coll, closed=False)
        trim.ring(rrect(-5.45, F + 1.52, 1.10, .80, .10), rrect(-5.45, F + 1.52, 1.00, .70, .08), 'y', sy * hw, sy * (hw + .02), 'brass')
        for x in (ca + .04, ce - .04):              # grab rails at the entrance, steps below
            trim.cylinder((x, sy * (hw + .05)), 'z', .016, F - .10, F + 1.70, 'brass', 8)
        for zz, depth in ((F - .32, .22), (F - .62, .30)):
            ya, yb = sorted((sy * (hw - .22), sy * (hw - .22 + depth)))
            trim.box(ca + .08, ce - .08, ya, yb, zz - .03, zz, 'steel')
        trim.box(ca + .06, ca + .09, *sorted((sy * hw, sy * (hw - .02))), F - .65, F, 'undercarriage')
        trim.box(ce - .09, ce - .06, *sorted((sy * hw, sy * (hw - .02))), F - .65, F, 'undercarriage')
        ya, yb = sorted((sy * (hw - .002), sy * (hw + .006)))
        trim.box(ce, cb, ya, yb, F + .45 - .005, F + .45 + .005, 'brass')
        for z in (F + .54, F + 1.06):                 # red lined panel round the crest
            trim.box(ce + .12, cb - .12, ya, yb, z - .005, z + .005, 'lining-red')
        for x in (ce + .12, cb - .12):
            trim.box(x - .005, x + .005, ya, yb, F + .54, F + 1.06, 'lining-red')
    # side doors in the entrance cut-outs, under a header: hinged at their front edge, opening outwards
    for side, sy in (('L', 1), ('R', -1)):
        y0, y1 = sorted((sy * cin, sy * hw))
        hd = M(); hd.box(ca, ce, y0, y1, F + 1.95, L.CAB_TOP, 'loco-black')
        hd.obj(f'Cab_DoorHeader_{side}', coll, parent=parent)
        dwid, dz0, dz1 = ce - ca - .02, F + .05, F + 1.93
        d = M()
        d.box(-dwid, 0, -.02, .02, 0, dz1 - dz0, 'loco-black')
        win = (-dwid / 2, 1.30, dwid - .18, .42)          # (x centre from the hinge, z centre from the sill, w, h)
        for s in (-1, 1):
            ta, tb = sorted((s * .02, s * .026))
            d.box(-dwid + .05, -.05, ta, tb, .30, .305, 'lining-red')
            d.box(-dwid + .05, -.05, ta, tb, 1.02, 1.025, 'lining-red')
            d.box(-.10, -.08, ta - s * .0, tb + s * .03, .85, 1.05, 'brass')
        leaf = d.obj(f'Door_cab-{side.lower()}', coll, parent=parent)
        cut = M(); cut.prism(rrect(win[0], win[1], win[2], win[3], .05), 'y', -.1, .1, 'glass')
        boolean(leaf, [cut]); reproject(leaf, lambda n, ctr: 'walnut' if n.y * sy < -.7 else 'loco-black')
        g = M(); g.poly([(x, 0, z) for x, z in rrect(win[0], win[1], win[2], win[3], .05)], 'glass', normal=(0, sy, 0))
        go = g.obj(f'Glazing_Door_cab-{side.lower()}', glass_coll, closed=False); go.parent = leaf
        hinge = (ce - .01, sy * (hw - .02), dz0)
        leaf.location = hinge
        DOOR_RECORDS.append(dict(name=leaf.name, door=f'cab-{side.lower()}', kind='hinged', pivot=list(hinge), swing_deg=-95 * sy,
                                 opening=[ca, ce, dz0, dz1], wall=f'cab-side-{side.lower()}'))
    # back plate, facing the tender: a doorway in the middle, a small glass each side to look back along the train
    dw, dh = L.CAB_DOOR
    m = M()
    for sy in (-1, 1):
        m.box(ca, ca + L.CAB_WALL, *sorted((sy * dw, sy * hw)), F, L.CAB_TOP, 'loco-black')
    m.box(ca, ca + L.CAB_WALL, -dw, dw, F + dh, L.CAB_TOP, 'loco-black')
    o = m.obj('Cab_Back', coll, parent=parent)
    cuts = []
    for sy in (-1, 1):
        cut = M(); cut.prism(rrect(sy * 1.02, F + 1.62, .42, .52, .06), 'x', ca - .05, ca + .11, 'glass'); cuts.append(cut)
    boolean(o, cuts)
    reproject(o, lambda n, ctr: 'walnut' if n.x > .7 else 'loco-black')
    g = M()
    for sy in (-1, 1):
        g.poly([(ca + .03, y, z) for y, z in rrect(sy * 1.02, F + 1.62, .42, .52, .06)], 'glass', normal=(-1, 0, 0))
        trim.ring(rrect(sy * 1.02, F + 1.62, .50, .60, .08), rrect(sy * 1.02, F + 1.62, .42, .52, .06), 'x', ca - .015, ca, 'brass')
    g.obj('Glazing_Cab_Back', glass_coll, closed=False)
    for y in (-dw - .03, dw + .03):                 # brass grab rails at the doorway
        trim.box(ca - .05, ca - .02, y - .015, y + .015, F + .15, F + 1.80, 'brass')
    # the back plates' cab face: a lined panel under each glass, a steel angle round the doorway with a kick plate,
    # and a brass handle each side of it to swing in from the tender
    fx = ca + L.CAB_WALL
    for sy in (-1, 1):
        y0, y1 = sorted((sy * (dw + .10), sy * (hw - .10)))
        for z0, z1, pad in ((F + .15, F + 1.22, 0.), (F + .15 + .05, F + 1.22 - .05, .05)):
            mat, t = ('brass', .008) if not pad else ('lining-red', .005)
            ya, yb = y0 + pad, y1 - pad
            trim.box(fx, fx + t, ya, yb, z0, z0 + .012, mat); trim.box(fx, fx + t, ya, yb, z1 - .012, z1, mat)
            trim.box(fx, fx + t, ya, ya + .012, z0, z1, mat); trim.box(fx, fx + t, yb - .012, yb, z0, z1, mat)
        ya, yb = sorted((sy * dw, sy * (dw + .05)))
        trim.box(ca - .005, fx + .02, ya, yb, F, F + dh, 'steel')                                  # doorway angle
        hy = sy * (dw + .075)                      # between the doorway angle and the lined panel
        trim.cylinder((hy, F + 1.10), 'x', .012, fx, fx + .07, 'brass', 8)
        trim.cylinder((hy, F + 1.50), 'x', .012, fx, fx + .07, 'brass', 8)
        trim.box(fx + .055, fx + .075, hy - .012, hy + .012, F + 1.10, F + 1.50, 'brass')          # handle bar
    trim.box(ca - .005, fx + .02, -dw - .05, dw + .05, F + dh, F + dh + .05, 'steel')              # lintel angle
    trim.box(ca, fx + .004, -dw, dw, F, F + .012, 'steel')                                         # kick plate, flush
    # front plate round the firebox, two spectacle glasses
    m = M()
    for sy in (-1, 1):
        m.box(cb - .06, cb, *sorted((sy * L.FIREBOX_HW, sy * hw)), F, L.CAB_TOP, 'loco-black')
    m.box(cb - .06, cb, -L.FIREBOX_HW, L.FIREBOX_HW, L.FIREBOX_TOP, L.CAB_TOP, 'loco-black')
    o = m.obj('Cab_Front', coll, parent=parent)
    cuts = []
    for sy in (-1, 1):
        cut = M(); cut.prism(_circle(sy * 1.22, F + 1.72, .17, 20), 'x', cb - .1, cb + .05, 'glass'); cuts.append(cut)
    boolean(o, cuts)
    reproject(o, lambda n, ctr: 'walnut' if n.x < -.7 else 'loco-black')
    g = M()
    for sy in (-1, 1):
        g.poly([(cb - .03, y, z) for y, z in _circle(sy * 1.22, F + 1.72, .17, 20)], 'glass', normal=(1, 0, 0))
        trim.ring(_circle(sy * 1.22, F + 1.72, .22, 20), _circle(sy * 1.22, F + 1.72, .17, 20), 'x', cb - .075, cb - .06, 'brass')
    g.obj('Glazing_Cab_Front', glass_coll, closed=False)
    # roof: an elliptic shell over the cab, overhanging the back, cream underneath
    sec_o = [(y, L.CAB_TOP + (L.CAB_ROOF - L.CAB_TOP) * math.sqrt(max(0., 1 - (y / (hw + .05)) ** 2))) for y in np.linspace(hw + .05, -hw - .05, 17)]
    m = M()
    rx0, rx1, th = ca - .25, cb + .06, .05
    sec_i = [(y, z - th) for y, z in sec_o]
    for (ya, za), (yb, zb), (yc, zc), (yd, zd) in zip(sec_o, sec_o[1:], sec_i, sec_i[1:]):
        m.poly([(rx0, ya, za), (rx1, ya, za), (rx1, yb, zb), (rx0, yb, zb)], 'loco-black', normal=(0, 0, 1))      # smooth top
        m.poly([(rx0, yc, zc), (rx0, yd, zd), (rx1, yd, zd), (rx1, yc, zc)], 'ceiling', normal=(0, 0, -1))        # cream underside
        for x, s in ((rx0, -1), (rx1, 1)):                                                                       # end edges
            m.poly([(x, ya, za), (x, yb, zb), (x, yd, zd), (x, yc, zc)], 'loco-black', normal=(s, 0, 0))
    for (y, z), (yi, zi) in ((sec_o[0], sec_i[0]), (sec_o[-1], sec_i[-1])):                                     # eaves
        m.poly([(rx0, y, z), (rx1, y, z), (rx1, yi, zi), (rx0, yi, zi)], 'loco-black', normal=(0, 1 if y > 0 else -1, 0))
    m.obj('Cab_Roof', coll, parent=parent, smooth_angle=50)
    trim.box(ca - .27, ca - .23, -hw, hw, L.CAB_TOP - .02, L.CAB_TOP + .02, 'brass')
    # --- backhead: the firebox end in the cab, with the fire door, gauges and controls ---
    m = M()
    m.prism(_tank_section(L.FIREBOX_HW, F, L.FIREBOX_TOP, .45), 'x', bx, cb - .06, 'iron-black')
    o = m.obj('Cab_Backhead', coll, parent=parent)
    reproject(o, lambda n, ctr: 'iron-black')
    d = M()
    pts = _tank_section(L.FIREBOX_HW, F, L.FIREBOX_TOP, .45)
    d.poly([(bx - .004, y, z) for y, z in pts], 'undercarriage', normal=(-1, 0, 0))     # riveted plate behind the Tripo pipework
    d.obj('Cab_BackheadFace', coll, parent=parent, closed=False)
    mt = {mo.id: mo for mo in c.mounts}
    # the controls, each its own object with the origin at its pivot (the driving mode turns them)
    def control(name, mesh, mount, to=bx):
        if mount.x < bx - .05:                       # on a shaft from the backhead plate (or a valve), through the pipework
            mesh.cylinder((mount.y, mount.z), 'x', .018, mount.x, to, 'steel', 8)
        o = mesh.obj(f'Control_{name}', coll, parent=parent, origin=(mount.x, mount.y, mount.z))
        o['control'] = mount.id; o['lods'] = [0, 1]
        return o
    p = mt['regulator']
    k = M()
    k.prism(_circle(p.y, p.z, .05, 12), 'x', p.x - .05, p.x, 'brass')
    k.box(p.x - .06, p.x - .03, p.y, p.y + p.length, p.z - .02, p.z + .02, 'brass')
    k.prism(_circle(p.y + p.length, p.z, .03, 10), 'x', p.x - .14, p.x - .03, 'end-dark')
    control('Regulator', k, p)
    p = mt['reverser']
    trim.box(p.x - .10, p.x + .10, p.y - .10, p.y + .10, F, p.z - .05, 'brass')
    trim.box(p.x - .13, p.x + .13, p.y - .13, p.y + .13, F, F + .06, 'brass')
    k = M()
    for a in range(6):
        ang = math.pi * a / 3
        k.box(p.x + .14 * math.cos(ang) - .015, p.x + .14 * math.cos(ang) + .015, p.y + .14 * math.sin(ang) - .015, p.y + .14 * math.sin(ang) + .015, p.z - .015, p.z + .015, 'brass')
        k.box(min(p.x, p.x + .14 * math.cos(ang)) - .008, max(p.x, p.x + .14 * math.cos(ang)) + .008,
              min(p.y, p.y + .14 * math.sin(ang)) - .008, max(p.y, p.y + .14 * math.sin(ang)) + .008, p.z - .008, p.z + .008, 'brass')
    k.prism(_circle(p.x, p.y, .04, 10), 'z', p.z - .03, p.z + .03, 'brass')
    control('Reverser', k, p)
    p = mt['brake']
    trim.box(p.x - .08, p.x + .08, p.y - .03, p.y + .06, p.z - .10, p.z + .06, 'brass')
    k = M(); k.box(p.x - .01, p.x + p.length, p.y - .05, p.y - .02, p.z - .015, p.z + .015, 'brass')
    control('Brake', k, p)
    p = mt['whistle']
    k = M(); k.box(p.x - .03, p.x, p.y - .01, p.y + .01, p.z - p.length, p.z, 'brass'); k.prism(_circle(p.y, p.z - p.length, .02, 8), 'x', p.x - .05, p.x, 'end-dark')
    control('Whistle', k, p, to=L.WHISTLE_VALVE[0] - L.WHISTLE_VALVE[1])      # the pull rod runs to the whistle valve
    cab_pipework(coll, parent)
    p = mt['sander']
    k = M(); k.box(p.x - .03, p.x, p.y - .012, p.y + .012, p.z, p.z + p.length, 'brass')
    control('Sander', k, p)
    p = mt['injector-valve']
    k = M(); k.ring(_circle(p.y, p.z, .09, 14), _circle(p.y, p.z, .07, 14), 'x', p.x - .03, p.x, 'brass')
    control('Injector', k, p)
    # the fire door over the arch painted on the backhead: hinged on its right edge, opening towards the driver, the
    # fire glowing behind it
    p = mt['fire-door']
    hwd, hhd = p.length / 2, .34
    glow = M(); glow.poly([(bx - .006, y, z) for y, z in rrect(0, p.z, 2 * hwd - .04, 2 * hhd - .04, .08)], 'fire', normal=(-1, 0, 0))
    glow.obj('Cab_FireGlow', coll, parent=parent, closed=False)
    door = M()
    door.box(-.03, 0, 0, 2 * hwd, -hhd, hhd, 'iron-black')
    for dz in (-.20, -.07, .07, .20):
        door.box(-.034, -.03, .10, 2 * hwd - .10, dz - .009, dz + .009, 'brass')
    door.box(-.09, -.03, 2 * hwd - .10, 2 * hwd - .05, -.025, .025, 'brass')
    leaf = door.obj('Door_fire-door', coll, parent=parent)
    leaf.location = (bx - .012, -hwd, p.z)
    DOOR_RECORDS.append(dict(name=leaf.name, door='fire-door', kind='hinged', pivot=list(leaf.location), swing_deg=100,
                             opening=[-hwd, hwd, p.z - hhd, p.z + hhd], wall='backhead'))
    # flap seats, crest, cab lining
    for b in c.reservations:
        if b.kind == 'seat':
            trim.box(b.x0, b.x1, b.y0, b.y1, b.z1 - .05, b.z1, 'walnut')
            trim.box((b.x0 + b.x1) / 2 - .02, (b.x0 + b.x1) / 2 + .02, b.y0, b.y1, b.z0, b.z1 - .05, 'brass')
    trim.obj('Loco_Trim', coll, parent=parent, lods=(0,))
    m = M()
    for sy in (-1, 1):
        y = sy * (hw + .008)
        w = h = .44
        xs2 = (B.crest_x - w / 2, B.crest_x + w / 2)
        zc = F + .80
        pts = [(xs2[0], y, zc - h / 2), (xs2[1], y, zc - h / 2), (xs2[1], y, zc + h / 2), (xs2[0], y, zc + h / 2)]
        if sy < 0:
            pts = [(xs2[1] + xs2[0] - q[0], q[1], q[2]) for q in pts]
        m.poly(pts, 'crest', uv=[(0, 0), (1, 0), (1, 1), (0, 1)], normal=(0, sy, 0))
    m.obj('Shell_Crest', coll, parent=parent, closed=False)
    # buffers: small at the back (under the tender's fall plate), full-size at the front; hooks, head lamp
    m = M()
    for sx, head_r, hs in ((-1, .15, ca), (1, .20, L.LOCO_BEAM + .14)):
        bf = B.buffer(sx)
        for sy in (-1, 1):
            x0, x1 = sorted((hs, bf - sx * .06))
            m.cylinder((sy * L.BUFFER_Y, L.BUFFER_Z), 'x', .10, x0, x1, 'undercarriage', 16)
            x0, x1 = sorted((bf - sx * .06, bf))
            m.cylinder((sy * L.BUFFER_Y, L.BUFFER_Z), 'x', head_r, x0, x1, 'steel', 20)
        x0, x1 = sorted((hs, bf - sx * .02))
        m.box(x0, x1, -.06, .06, L.BUFFER_Z - .07, L.BUFFER_Z + .05, 'undercarriage')
    m.box(B.buffer(1) - .04 - .03, B.buffer(1) - .04 + .03, -.12, .12, L.BUFFER_Z - .20, L.BUFFER_Z - .05, 'steel')
    hl = mt['head-lamp']
    m.box(hl.x - .10, hl.x + .10, hl.y - .13, hl.y + .13, 1.34, hl.z + .16, 'end-dark')
    m.obj('Shell_Buffers', coll, parent=parent)
    lamp = M(); lamp.prism(_circle(hl.y, hl.z, .09, 16), 'x', hl.x + .10, hl.x + .12, 'lamp-white')
    lamp.obj('Shell_HeadLamp', coll, parent=parent)


def cab_pipework(coll, parent):
    """The cab's pipe runs from layout.cab_pipes (the steam fountain, its feeds, the whistle valve and the injector pipes
    through the footplate), with brass unions, end caps, flanges, the fountain's saddles and the main steam valve."""
    F = L.FLOOR_Z
    m = M()
    axis = lambda a, b: next(i for i in range(3) if abs(a[i] - b[i]) > 1e-9)
    def tube(a, b, r, mat, seg):                     # an axis-aligned tube from a to b
        i = axis(a, b)
        m.cylinder([a[j] for j in range(3) if j != i], 'xyz'[i], r, min(a[i], b[i]), max(a[i], b[i]), mat, seg)
    def collar(p, i, sign, r, depth, mat, seg):      # a short ring on axis i at p, reaching `depth` back along the tube
        m.cylinder([p[j] for j in range(3) if j != i], 'xyz'[i], r, *sorted((p[i], p[i] - sign * depth)), mat, seg)
    for run in L.cab_pipes():
        pts, r, mat = run['pts'], run['r'], run['mat']
        seg = 12 if r > .03 else 8
        for a, b in zip(pts, pts[1:]):
            tube(a, b, r, mat, seg)
        for a, p, b in zip(pts, pts[1:], pts[2:]):  # elbows: a fitting a little fatter than the pipe at each bend
            i = axis(p, b)
            collar(p, i, -1 if b[i] > p[i] else 1, r * 1.3, r * 1.3, 'brass', seg)
            collar(p, axis(a, p), 1 if p[axis(a, p)] > a[axis(a, p)] else -1, r * 1.3, r * 1.3, 'brass', seg)
        for end, (p, q) in zip(run['ends'], ((pts[0], pts[1]), (pts[-1], pts[-2]))):
            i = axis(p, q)
            sign = 1 if p[i] > q[i] else -1           # outwards from the tube
            if end == 'union':
                collar(p, i, sign, r * 1.45, .035, 'brass', seg)
            elif end == 'cap':
                collar(p, i, sign, r * 1.15, .03, 'brass', seg)
            else:                                    # a bolted flange flat on the boiler's back end or the footplate
                collar(p, i, sign, r * 2.3, .012, 'iron-black', 12)
    fx, fz, fh, fr = L.FOUNTAIN
    for y in (-.35, .35):                            # saddles holding the fountain on the firebox top
        m.box(fx - .05, fx + .05, y - .03, y + .03, L.FIREBOX_TOP, F + fz, 'iron-black')
    for y in (-.36, -.12, .16):                      # small stop valves along the fountain's top, one per take-off
        m.cylinder((fx, y), 'z', .018, F + fz, F + fz + fr + .05, 'brass', 8)
        m.ring(_circle(fx, y, .045, 10), _circle(fx, y, .035, 10), 'z', F + fz + fr + .05, F + fz + fr + .06, 'brass')
    m.ring(_circle(0., F + 2.21, .09, 14), _circle(0., F + 2.21, .075, 14), 'x', fx - .07, fx - .055, 'brass')   # main steam valve wheel
    m.cylinder((0., F + 2.21), 'x', .015, fx - .07, fx, 'steel', 8)
    wx, wr = L.WHISTLE_VALVE
    wy = next(mo for mo in L.locomotive().mounts if mo.id == 'whistle').y
    m.cylinder((wx, wy), 'z', wr, L.FIREBOX_TOP, F + 2.12, 'brass', 10)                # the whistle valve
    m.obj('Cab_Pipework', coll, parent=parent, lods=(0,))     # inside the cab: LOD0 only, like the trim


def loco_lod2(c, coll, parent):
    F = L.FLOOR_Z
    (b0, b1, br, bz), (s0, s1, sr) = L.BOILER, L.SMOKEBOX
    m = M()
    m.box(b0, b1, -br, br, bz - br, bz + br, 'loco-black')
    m.box(s0, s1, -sr, sr, bz - sr, bz + sr, 'iron-black')
    m.box(4.12, 4.68, -.28, .28, bz + sr - .1, 4.66, 'iron-black')
    m.box(L.CAB[0], L.CAB[1], -L.LOCO_HALF, L.LOCO_HALF, F - .3, L.CAB_ROOF, 'loco-black')
    m.box(L.CAB[1], L.LOCO_BEAM, -L.LOCO_HALF, L.LOCO_HALF, 1.30, L.RUNNING_BOARD_Z, 'loco-black')
    m.box(-5.0, L.LOCO_BEAM, -1.0, 1.0, .05, 1.30, 'undercarriage')
    m.obj('LOD2_Hull', coll, parent=parent, lods=(2,))


B = L.Body()      # the body of the vehicle being built (build() sets it)


def runtime_placements(coach, mesh_name):
    placements = L.as_dict(coach)
    placements['doors_runtime'] = DOOR_RECORDS
    placements['doors'] = door_interactions(coach, mesh_name)
    placements['door_rules'] = DOOR_RULES
    placements['interior_volumes'] = L.interior_volumes(coach)
    placements['exterior_volumes'] = L.exterior_volumes(coach)
    placements['boarding'] = CO.boarding(coach)
    placements['envelope'] = L.envelope()
    placements['coupling'] = L.coupling(B)
    placements['collision_boxes'] = [dict(name=name, part=n, group=g, box=[round(v, 4) for v in b]) for name, n, g, b in CO.named_boxes(coach, mesh_name)]
    return placements


def build(coach, images, *, source_sink=None):
    global B
    B = coach.body
    bpy.ops.wm.read_factory_settings(use_empty=True)
    MAT.clear()
    for name, img in images.items():
        if name not in bpy.data.images:
            images[name] = bpy.data.images.load(str(TEX / f'{name}.{"jpg" if name in T.JPEG else "png"}'))
            images[name].name = name
    make_materials(images)
    scene = bpy.context.scene
    scene.unit_settings.system = 'METRIC'; scene.unit_settings.scale_length = 1.
    title = ''.join(p.title() for p in coach.name.split('-'))
    mesh_name = f'SM_BT_{title}'
    cols = {}
    for n in ('Shell', 'Roof', 'Glazing', 'Doors', 'Interior', 'LOD2', 'Reservations', 'Collision'):
        cols[n] = bpy.data.collections.new(f'{title}_{n}'); scene.collection.children.link(cols[n])
    root = group(f'BT_{title}', cols['Shell'])
    root['coach'] = coach.name; root['frame'] = L.as_dict(coach)['frame']
    g = {n: group(f'BT_{title}_{n}', cols[n], root) for n in ('Shell', 'Roof', 'Glazing', 'Doors', 'Interior')}
    if B.kind == 'tender':
        DOOR_RECORDS.clear()
        tender_body(coach, cols['Shell'], g['Shell'], cols['Glazing'])
    elif B.kind == 'locomotive':
        DOOR_RECORDS.clear()
        loco_body(coach, cols['Shell'], g['Shell'], cols['Glazing'])
        fittings(coach, cols['Interior'], g['Interior'])
    else:
        side_walls(coach, cols['Shell'], g['Shell'])
        end_walls(coach, cols['Shell'], g['Shell'])
        deck_and_underframe(coach, cols['Shell'], g['Shell'])
        ends_hardware(coach, cols['Shell'], g['Shell'])
        balcony(coach, cols['Shell'], g['Shell'])
        bogies(cols['Shell'], g['Shell'])
        roof(cols['Roof'], g['Roof'])
        ceiling(coach, cols['Roof'], g['Roof'])
        floors(coach, cols['Interior'], g['Interior'])
        partitions(coach, cols['Interior'], g['Interior'])
        lining(coach, cols['Interior'], g['Interior'])
        window_frames(coach, cols['Shell'], g['Shell'], cols['Glazing'], g['Glazing'])
        doors(coach, cols['Doors'], g['Doors'], cols['Glazing'], g['Glazing'])
        fittings(coach, cols['Interior'], g['Interior'])
        if B.cupola:
            lookout(coach, cols['Interior'], g['Interior'])
    for end, e in L.coupling(B)['ends'].items():   # attachment sockets, exported in every LOD
        for name, loc in [('Coupler', e['draw_hook'])] + ([('Gangway', e['gangway_face_centre'])] if 'gangway_face_centre' in e else []):
            so = bpy.data.objects.new(f'SOCKET_{name}_{end.upper()}', None); so.empty_display_type = 'ARROWS'; so.empty_display_size = .4
            so.location = loc; so.rotation_euler = (0, 0, 0 if end == 'b' else math.pi)
            so['lods'] = [0, 1, 2]; so['length_m'] = B.length
            cols['Shell'].objects.link(so); so.parent = root
    for mt in coach.mounts:                         # emitters (the chimney's smoke), exported in every LOD
        if mt.kind == 'emitter':
            so = bpy.data.objects.new(f'SOCKET_{"".join(p.title() for p in mt.id.split("-"))}', None)
            so.empty_display_type = 'SINGLE_ARROW'; so.empty_display_size = .5
            so.location = (mt.x, mt.y, mt.z); so['lods'] = [0, 1, 2]; so['mount'] = mt.id
            cols['Shell'].objects.link(so); so.parent = root
    lod2 = group(f'BT_{title}_LOD2', cols['LOD2']); lod2['lods'] = [2]
    if B.kind == 'tender':
        tender_lod2(coach, cols['LOD2'], lod2)
    elif B.kind == 'locomotive':
        loco_lod2(coach, cols['LOD2'], lod2)
    else:
        lod2_hull(coach, cols['LOD2'], lod2)
        roof(cols['LOD2'], lod2, lod=2)
        bogies(cols['LOD2'], lod2, lod=2)
    res_root = group(f'BT_{title}_Reservations', cols['Reservations']); res_root['lods'] = []
    reservations(coach, cols['Reservations'], res_root)
    col_root = group(f'BT_{title}_Collision', cols['Collision']); col_root['lods'] = []
    ucx = collision(coach, cols['Collision'], col_root, mesh_name)
    cols['LOD2'].hide_render = True; cols['Collision'].hide_render = True
    for o in cols['LOD2'].objects:
        o.hide_set(True)
    out = OUT / coach.name; out.mkdir(parents=True, exist_ok=True)
    atlas = TEX / f'T_BT_{title}Interior.png'           # the windows' interior views (re-rendered when their inputs change)
    window_tiles = PT.atlas(coach, atlas, OUT / 'furniture', [cols['LOD2'], cols['Reservations'], cols['Collision']])
    if window_tiles:
        MAT['window-interior'].name = f'M_BT_WindowInterior{title}'
        PT.window_material(MAT['window-interior'], atlas)
    if B.livery == 'worn':
        wear_out([o for o in scene.objects if o.users_collection and not o.users_collection[0].name.endswith(('_Reservations', '_Collision'))])
    every = list(scene.objects)
    lod_sets = {k: [o for o in every if k in list(o.get('lods', []))] for k in (0, 1, 2)}
    lod_sets[0] = [o for o in lod_sets[0] if o.name != lod2.name]
    lod_sets[1] = [o for o in lod_sets[1] if o.name != lod2.name]
    if source_sink is not None:
        info = dict(title=coach.title, mesh=mesh_name,
            triangles={f'LOD{k}': tris(lod_sets[k]) for k in (0, 1, 2)},
            objects={f'LOD{k}': sum(1 for o in lod_sets[k] if o.type == 'MESH') for k in (0, 1, 2)},
            materials=sorted({s.material.name for o in lod_sets[0] if o.type == 'MESH' for s in o.material_slots if s.material}),
            collision_boxes=len(ucx), placements=len(coach.placements), seats=len(coach.seats), mounts=len(coach.mounts),
            reservations=len(coach.reservations), doors=len(DOOR_RECORDS), mesh_checks=mesh_checks(lod_sets[0]),
            layout_checks=L.check(coach))
        if info['layout_checks']: raise ValueError('Selected carriage layout checks failed: ' + repr(info['layout_checks']))
        return source_sink(coach, mesh=mesh_name, lod_sets=lod_sets,
                           placements=runtime_placements(coach, mesh_name), info=info)
    files = {}
    for k in (0, 1, 2):
        p = out / f'{mesh_name}_LOD{k}.glb'; export_glb(p, lod_sets[k]); files[p.name] = p
    p = out / f'{mesh_name}_Collision.glb'; export_glb(p, [col_root] + ucx); files[p.name] = p
    blockout = [res_root] + [o for o in every if o.parent == res_root]
    p = out / f'{coach.name}-blockout.glb'; export_glb(p, blockout); files[p.name] = p
    placements = runtime_placements(coach, mesh_name)
    p = out / f'{coach.name}-placements.json'; p.write_text(json.dumps(placements, indent=1)); files[p.name] = p
    for o in cols['Reservations'].objects:
        o.hide_render = False
    for o in cols['LOD2'].objects:
        o.hide_set(True)
    p = out / f'{coach.name}.blend'
    bpy.ops.wm.save_as_mainfile(filepath=str(p), compress=True, relative_remap=True)
    files[p.name] = p
    parts = export_parts(coach, lod_sets, out, mesh_name, files, window_tiles)
    info = dict(
        title=coach.title, mesh=mesh_name,
        triangles={f'LOD{k}': tris(lod_sets[k]) for k in (0, 1, 2)},
        objects={f'LOD{k}': sum(1 for o in lod_sets[k] if o.type == 'MESH') for k in (0, 1, 2)},
        materials=sorted({s.material.name for o in lod_sets[0] if o.type == 'MESH' for s in o.material_slots if s.material}),
        collision_boxes=len(ucx), placements=len(coach.placements), seats=len(coach.seats), mounts=len(coach.mounts),
        reservations=len(coach.reservations), doors=len(DOOR_RECORDS),
        mesh_checks=mesh_checks(lod_sets[0]),
        layout_checks=L.check(coach),
        files={n: dict(bytes=f.stat().st_size, sha256=sha(f)) for n, f in files.items()},
        parts=parts,
    )
    return info


def export_parts(c, lod_sets, out, mesh_name, files, window_tiles):
    """The engine's cut of the vehicle (parts.py), beside the combined LODs, and its record for the manifest. Leaves
    the scene as it was."""
    coll = bpy.data.collections.new('Parts'); bpy.context.scene.collection.children.link(coll)
    p = out / f'{mesh_name}_Exterior_LOD2.glb'; export_glb(p, lod_sets[2]); files[p.name] = p     # the LOD2 is all outside
    lod2 = dict(file=p.name, triangles=tris(lod_sets[2]), sections=PT.sections(lod_sets[2]), nodes=sum(1 for o in lod_sets[2] if o.type == 'MESH'))
    renamed = []
    for o in set(lod_sets[0]) | set(lod_sets[1]):    # the copies take the originals' names in the GLBs
        renamed.append((o, o.name)); o.name = o.name + '~'
    record = dict(exterior={}, interior={}, render=dict(
        interior_cull_m=PT.INTERIOR_CULL_M, interior_cast_shadow=False, exterior_cast_shadow=False,
        shadow_proxy='casts the shadows only (hidden in game, shadow casting on)',
        window_cards=f'drawn only beyond {PT.INTERIOR_CULL_M:g} m, where the interior is culled; one-sided, facing out'))
    made = []
    for k in (0, 1):
        sides = PT.split(B, lod_sets[k], coll)
        for side, objs in sides.items():
            made += objs
            if not any(o.type == 'MESH' for o in objs):
                continue
            p = out / f'{mesh_name}_{side.title()}_LOD{k}.glb'; export_glb(p, objs); files[p.name] = p
            record[side][f'LOD{k}'] = dict(file=p.name, triangles=PT.triangles(objs), sections=PT.sections(objs),
                                           nodes=sum(1 for o in objs if o.type == 'MESH'))
        for o in made:
            o.name = o.name + '#'                     # out of the way of the next level's names
    for o, name in renamed:
        o.name = name
    record['exterior']['LOD2'] = lod2
    proxy = PT.shadow_proxy(c, coll, MAT['shadow-proxy']); made.append(proxy)
    proxy.name = 'ShadowProxy'
    p = out / f'{mesh_name}_ShadowProxy.glb'; export_glb(p, [proxy]); files[p.name] = p
    record['shadow_proxy'] = dict(file=p.name, triangles=PT.triangles([proxy]))
    if window_tiles:
        m = M(); window_cards(c, m, L.HALF + .004)
        cards = m.obj('WindowCards', coll, lods=()); made.append(cards)
        p = out / f'{mesh_name}_WindowCards.glb'; export_glb(p, [cards]); files[p.name] = p
        record['window_cards'] = dict(file=p.name, triangles=PT.triangles([cards]), atlas=f'T_BT_{"".join(t.title() for t in c.name.split("-"))}Interior.png',
                                      atlas_px=[PT.TILE_PX * PT.ATLAS_TILES, PT.TILE_PX], tiles=window_tiles, fov_deg=PT.WINDOW_FOV,
                                      uv='u across the atlas: tile = floor(u * tiles); v 0 at the sill')
    for o in made:
        data = o.data
        bpy.data.objects.remove(o)
        if data is not None and data.users == 0:
            bpy.data.meshes.remove(data) if isinstance(data, bpy.types.Mesh) else None
    bpy.data.collections.remove(coll)
    return record


def main():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    count = FU.stage(OUT / 'furniture')
    print(f'BELMONTE TRAIN: staged {count} verified furniture sources', flush=True)
    images = make_textures()
    paths = {n: TEX / f'{n}.{"jpg" if n in T.JPEG else "png"}' for n in images}
    manifest = dict(
        version=1, about='Belmonte train coach shells, generated by games/yorimichi/world/train/build.py from train/layout.py',
        units='metres in the .blend and placements; GLBs are standard glTF (Y-up) exported by Blender',
        frame=L.as_dict(L.restaurant())['frame'], envelope=L.envelope(), coupling=L.coupling(),
        human_gauges=dict(cairo=L.CAIRO, adult=L.HUMAN),
        budgets=dict(LOD0_triangles=60000, LOD1_triangles=20000, LOD2_triangles=1500, textures='7 maps, 512-1024 px, shared by both coaches'),
        textures={n: dict(bytes=p.stat().st_size, sha256=sha(p)) for n, p in paths.items()},
        coaches={},
    )
    for coach in L.vehicles():
        manifest['coaches'][coach.name] = build(coach, dict(images))
        print(f'BELMONTE TRAIN {coach.name}: {manifest["coaches"][coach.name]["triangles"]}', flush=True)
    (OUT / 'manifest.json').write_text(json.dumps(manifest, indent=1))
    bad = [(n, c['layout_checks']) for n, c in manifest['coaches'].items() if c['layout_checks']]
    if bad:
        raise SystemExit(f'layout checks failed: {bad}')
    print('BELMONTE TRAIN BUILD COMPLETE', flush=True)


if __name__ == '__main__':
    main()

