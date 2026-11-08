"""The vehicles' shells cut for the engine (Blender; build.py calls it once a vehicle is built).

Besides the combined SM_BT_<V>_LOD0/1/2.glb, each vehicle gets:

- SM_BT_<V>_Exterior_LOD0/1/2.glb: everything seen from outside. Static geometry is joined into one node (one
  primitive, so one draw, per material); the parts that move stay separate named nodes (door leaves with their trim
  and glazing joined in, bogies, wheelsets, rods, the cab controls), with the SOCKET_ empties.
- SM_BT_<V>_Interior_LOD0/1.glb: everything inside the inner envelope (lining, partitions, ceiling, floor, fittings,
  inside doors, the lookout, the engine's cab). A mesh that is both is cut face by face: a side wall's walnut inner
  face goes inside, its livery outside. No LOD2: the interior is culled with the furniture.
- SM_BT_<V>_ShadowProxy.glb: a closed hull of a few hundred triangles that casts the vehicle's shadows, so the
  detailed parts need not.
- SM_BT_<V>_WindowCards.glb and the LOD2 windows: each clear window as a one-sided card facing out, UVs into
  T_BT_<V>Interior.png, a 2D interior-mapping atlas of ATLAS_TILES views rendered from a window plane looking in
  (horizontal field of view WINDOW_FOV, room depth recorded per tile). The cards are drawn only beyond the interior's
  cull distance, where the real interior is gone.
"""
import hashlib
import json
import math
from pathlib import Path

import bmesh
import bpy
import numpy as np
from mathutils import Matrix, Vector

from train import budgets as BU
from train import layout as L

MOVABLE = ('Door_', 'Bogie_', 'Rod_', 'Control_', 'Wheelset')   # nodes the game animates: kept separate
ATLAS_TILES, TILE_PX = 4, 512
WINDOW_FOV = 90.                    # degrees, horizontal, of the atlas views
INTERIOR_CULL_M = BU.CULL_DISTANCE_M
OUTSIDE_ONLY = ('M_BT_Roof', 'M_BT_Livery', 'M_BT_LocoBlack', 'M_BT_Undercarriage')   # never inside, wherever they lie


# --- which side of the shell a face is on ---------------------------------------------------------------------
def is_interior(body, p):
    """True when the world point p (a face's centre) lies inside the vehicle's inner envelope."""
    x, y, z = p
    F, e = L.FLOOR_Z, .005
    if body.kind == 'tender':
        return False
    if body.kind == 'locomotive':
        return L.CAB[0] - e <= x <= L.CAB[1] + e and abs(y) <= L.CAB_IN + e and F - .05 <= z <= L.CAB_TOP - e
    well = L.lookout_well(body)
    if well and well[0] - e <= x <= well[1] + e and abs(y) <= well[2] + e and L.CEIL_SPRING - .2 <= z <= L.lookout_top(body)[0] + e:
        return True
    return body.in_a - e <= x <= body.in_b + e and abs(y) <= L.IN + e and F - .05 <= z <= L.CEIL_APEX + .06


# --- joining meshes -----------------------------------------------------------------------------------------------
def _append(bm, obj, matrix, mats):
    """Add obj's mesh to bm under `matrix`, its materials indexed into the shared list `mats`."""
    me = obj.data.copy()
    me.transform(matrix)
    if matrix.determinant() < 0:
        me.flip_normals()
    remap = []
    for s in obj.material_slots:
        if s.material not in mats:
            mats.append(s.material)
        remap.append(mats.index(s.material))
    for p in me.polygons:
        p.material_index = remap[p.material_index] if remap else 0
    bm.from_mesh(me)
    bpy.data.meshes.remove(me)


def _mesh(name, bm, mats, keep=None):
    """A mesh of the faces of bm that `keep` accepts (all by default), with only the materials they use."""
    b = bm.copy()
    b.faces.index_update()
    if keep:
        bmesh.ops.delete(b, geom=[f for f in b.faces if not keep(f)], context='FACES')
    used = sorted({f.material_index for f in b.faces})
    for f in b.faces:
        f.material_index = used.index(f.material_index)
    me = bpy.data.meshes.new(name)
    b.to_mesh(me); b.free()
    for i in used:
        me.materials.append(mats[i])
    return me


def _attached(o):
    """A door's trim or glazing: joined into the leaf it hangs from."""
    return o.parent is not None and o.parent.name.startswith(MOVABLE) and (o.name.endswith('_Trim') or o.name.startswith('Glazing_'))


def _movable(o):
    return o.name.startswith(MOVABLE) and not _attached(o)


def split(body, objs, coll):
    """(The originals carry a trailing '~' while their copies take their names.) New objects in `coll` for one level of detail: {'exterior': [...], 'interior': [...]}, the static parts of
    `objs` joined per side, the movable ones copied whole (their attachments joined in) on the side their centre is."""
    bpy.context.view_layer.update()
    out = {'exterior': [], 'interior': []}
    meshes = [o for o in objs if o.type == 'MESH']
    static = [o for o in meshes if not _movable(o) and not _attached(o)]
    bm, mats = bmesh.new(), []
    for o in static:
        _append(bm, o, o.matrix_world, mats)
    bm.faces.index_update()
    outside = {i for i, m in enumerate(mats) if m and m.name.startswith(OUTSIDE_ONLY)}
    inside = {f.index: f.material_index not in outside and is_interior(body, f.calc_center_median()) for f in bm.faces}
    for side, want in (('exterior', False), ('interior', True)):
        me = _mesh(f'{side.title()}_Static', bm, mats, lambda f: inside[f.index] == want)
        if len(me.polygons):
            o = bpy.data.objects.new(f'{side.title()}_Static', me); coll.objects.link(o); out[side].append(o)
        else:
            bpy.data.meshes.remove(me)
    bm.free()
    copies = {}
    for m in [o for o in meshes if _movable(o)]:
        bm, mats = bmesh.new(), []
        _append(bm, m, Matrix.Identity(4), mats)
        for ch in meshes:
            if _attached(ch) and ch.parent == m:
                _append(bm, ch, m.matrix_world.inverted() @ ch.matrix_world, mats)
        me = _mesh(m.name, bm, mats); bm.free()
        o = bpy.data.objects.new(m.name.rstrip('~'), me); coll.objects.link(o)
        o.matrix_world = m.matrix_world.copy()
        copies[m] = o
        corners = [m.matrix_world @ Vector(c) for c in m.bound_box]
        out['interior' if is_interior(body, sum(corners, Vector()) / 8) else 'exterior'].append(o)
    for m, o in copies.items():                     # wheelsets stay children of their bogie
        if m.parent in copies:
            world = o.matrix_world.copy()
            o.parent = copies[m.parent]; o.matrix_world = world
    for e in [o for o in objs if o.type == 'EMPTY' and o.name.startswith('SOCKET_')]:
        c = e.copy(); c.name = e.name.rstrip('~'); coll.objects.link(c); c.parent = None; c.matrix_world = e.matrix_world.copy()
        out['interior' if e.name.startswith('SOCKET_Light') else 'exterior'].append(c)
    return out


def triangles(objs):
    return sum(sum(len(p.vertices) - 2 for p in o.data.polygons) for o in objs if o.type == 'MESH')


def sections(objs):
    """Draw calls: one per material of each mesh node (an engine that merges the nodes needs fewer)."""
    return sum(len({p.material_index for p in o.data.polygons}) for o in objs if o.type == 'MESH')


# --- the shadow proxy ---------------------------------------------------------------------------------------------
class Hull:
    """Closed convex pieces for the shadow proxy."""

    def __init__(self):
        self.bm = bmesh.new()

    def prism(self, prof, axis, a0, a1):
        """A convex polygon `prof` (in the plane across `axis`) extruded from a0 to a1, capped."""
        def P(u, v, a):
            return (a, u, v) if axis == 'x' else (u, a, v) if axis == 'y' else (u, v, a)
        lo = [self.bm.verts.new(P(u, v, a0)) for u, v in prof]
        hi = [self.bm.verts.new(P(u, v, a1)) for u, v in prof]
        n = len(prof)
        for i in range(n):
            j = (i + 1) % n
            self.bm.faces.new((lo[i], lo[j], hi[j], hi[i]))
        self.bm.faces.new(lo[::-1]); self.bm.faces.new(hi)

    def box(self, x0, x1, y0, y1, z0, z1):
        self.prism([(y0, z0), (y1, z0), (y1, z1), (y0, z1)], 'x', x0, x1)

    def cylinder(self, cy, cz, r, x0, x1, seg=10):
        self.prism([(cy + r * math.cos(2 * math.pi * k / seg), cz + r * math.sin(2 * math.pi * k / seg)) for k in range(seg)], 'x', x0, x1)

    def obj(self, name, coll, mat):
        bmesh.ops.recalc_face_normals(self.bm, faces=self.bm.faces)
        bmesh.ops.triangulate(self.bm, faces=self.bm.faces)
        me = bpy.data.meshes.new(name); self.bm.to_mesh(me); self.bm.free()
        me.materials.append(mat)
        o = bpy.data.objects.new(name, me); coll.objects.link(o)
        return o


def shadow_proxy(c, coll, mat):
    """The vehicle's silhouette as a few closed pieces: body and roof, underframe and bogies; the engine's boiler,
    smokebox, cab and running gear; the tender's tank and frames."""
    b, h = c.body, Hull()
    if b.kind == 'locomotive':
        (b0, b1, br, bz), (s0, s1, sr) = L.BOILER, L.SMOKEBOX
        h.cylinder(0., bz, br, b0, b1); h.cylinder(0., bz, sr, s0, s1)
        h.box(L.CAB[0], L.CAB[1], -L.LOCO_HALF, L.LOCO_HALF, L.FLOOR_Z, L.CAB_TOP)
        h.prism([(-L.LOCO_HALF, L.CAB_TOP), (L.LOCO_HALF, L.CAB_TOP), (0., L.CAB_ROOF)], 'x', L.CAB[0] - .25, L.CAB[1])
        h.box(-5.0, L.LOCO_BEAM + .14, -L.LOCO_HALF, L.LOCO_HALF, .20, L.RUNNING_BOARD_Z)
    elif b.kind == 'tender':
        (ta, tb), (z0, _) = L.TENDER_TANK, L.TENDER_TANK_Z
        h.box(ta, tb, -L.TENDER_HALF, L.TENDER_HALF, z0, L.TENDER_COPING_Z)
        h.box(-L.TENDER_HEADSTOCK, L.TENDER_HEADSTOCK, -1.45, 1.45, .30, z0)
    else:
        h.box(b.x_a, b.x_b, -L.HALF, L.HALF, L.SKIRT_Z, L.CANT_Z)
        xa = b.x_a if b.end_a == 'gangway' else b.headstock(-1)
        xb = b.x_b if b.end_b == 'gangway' else b.headstock(1)
        ys = [-L.HALF + 2 * L.HALF * k / 6 for k in range(7)]
        h.prism([(y, L.roof_z(y)) for y in ys], 'x', xa, xb)        # closed by the chord along the cant rail
        h.box(b.headstock(-1), b.headstock(1), -L.HALF + .30, L.HALF - .30, .45, L.SKIRT_Z)
        for bx in b.bogies:
            h.box(bx - b.wheelbase / 2 - .30, bx + b.wheelbase / 2 + .30, -1.08, 1.08, .20, .85)
        if b.cupola:
            x0, x1 = b.cupola
            h.box(x0, x1, -L.CUPOLA_HW, L.CUPOLA_HW, L.roof_z(L.CUPOLA_HW) - .05, L.lookout_top(b)[1])
    return h.obj('ShadowProxy', coll, mat)


# --- the windows' interior atlas ------------------------------------------------------------------------------
def window_tiles(c):
    """(probes, {window name: tile}): up to ATLAS_TILES clear windows spread along the vehicle, each rendered into one
    tile of the atlas, and every clear window's nearest probe."""
    ws = sorted((w for w in c.windows if w.kind == 'clear'), key=lambda w: (w.x, w.side))
    if not ws:
        return [], {}
    n = min(ATLAS_TILES, len(ws))
    probes = [ws[int((i + .5) * len(ws) / n)] for i in range(n)]
    return probes, {w.name: min(range(n), key=lambda i: abs(probes[i].x - w.x)) for w in ws}


def window_uv(w, tile):
    """UVs of a window quad [(x0, sill), (x1, sill), (x1, head), (x0, head)] into its atlas tile, as seen from outside
    (from +Y, +x runs to the viewer's left)."""
    u0, u1 = tile / ATLAS_TILES, (tile + 1) / ATLAS_TILES
    left, right = (u1, u0) if w.side > 0 else (u0, u1)
    return [(left, 0.), (right, 0.), (right, 1.), (left, 1.)]


def room_depth(c, w):
    """How far the room behind a window runs across the vehicle, from the window's wall."""
    y = w.side * (L.IN - .3)
    r = next((r for r in c.rooms if r.x0 <= w.x <= r.x1 and r.y0 <= y <= r.y1), None)
    return round((r.y1 - r.y0) if r else 2 * L.IN, 3)


ATLAS_SOURCES = ('build.py', 'parts.py', 'fittings.py', 'layout.py', 'textures.py')   # what shapes the rendered rooms


def atlas_key(c, furniture_dir):
    """A hash of everything an atlas shows: the code that builds and lights the rooms, the furniture contract, the
    vehicle's plan and the furniture GLBs it places."""
    h = hashlib.sha256()
    here = Path(__file__).resolve().parent
    for name in ATLAS_SOURCES:
        h.update((here / name).read_bytes())
    from train import textures as T
    for tex in sorted(T.SOURCES.glob('*.jpg')):
        h.update(tex.name.encode() + tex.read_bytes())
    h.update(L.CONTRACT.read_bytes())
    h.update(json.dumps(L.as_dict(c), sort_keys=True, default=str).encode())
    for asset in sorted({p.asset for p in c.placements}):
        f = furniture_dir / f'{asset}.glb'
        h.update(asset.encode() + (f.read_bytes() if f.exists() else b'-'))
    return h.hexdigest()


def atlas(c, path, furniture_dir, hide):
    """The vehicle's window atlas and its tile records: rendered (render_atlas) only when its inputs changed since
    the last build, which the sidecar <atlas>.json remembers; otherwise the atlas on disk is kept."""
    key, side = atlas_key(c, furniture_dir), path.with_suffix('.json')
    try:
        cached = json.loads(side.read_text())
        if cached['key'] == key and path.exists():
            return cached['tiles']
    except (OSError, ValueError, KeyError):
        pass
    tiles = render_atlas(c, path, furniture_dir, hide)
    if tiles:
        side.write_text(json.dumps(dict(key=key, tiles=tiles), indent=1))
    return tiles


def render_atlas(c, path, furniture_dir, hide):
    """Render the probes' views (the vehicle as built, its furniture imported for the shot and removed again) into
    the atlas at `path`; collections in `hide` stay out of the renders. Returns the tile records."""
    probes, _ = window_tiles(c)
    if not probes:
        return []
    sc = bpy.context.scene
    before = {k: set(getattr(bpy.data, k)) for k in ('objects', 'meshes', 'materials', 'images', 'lights', 'cameras', 'worlds')}
    templates = {}
    for p in c.placements:
        f = furniture_dir / f'{p.asset}.glb'
        if not f.exists():
            continue
        if p.asset not in templates:
            seen = set(bpy.data.objects)
            bpy.ops.import_scene.gltf(filepath=str(f))
            templates[p.asset] = [o for o in bpy.data.objects if o not in seen and o.parent is None]
            for o in templates[p.asset]:
                o.location = (1e4, 0, 0)
        for t in templates[p.asset]:
            o = t.copy(); sc.collection.objects.link(o)
            for ch in t.children:
                cc = ch.copy(); sc.collection.objects.link(cc); cc.parent = o
            o.location = (p.x, p.y, p.z); o.rotation_mode = 'XYZ'; o.rotation_euler = (0, 0, math.radians(p.yaw))
    for k in range(int(c.body.in_a), int(c.body.in_b) + 1, 3):
        ld = bpy.data.lights.new('atlas-light', 'POINT'); ld.energy = 90; ld.shadow_soft_size = .4
        lo = bpy.data.objects.new('atlas-light', ld); lo.location = (k + .5, 0, L.CEIL_SPRING - .25); sc.collection.objects.link(lo)
    world = bpy.data.worlds.new('atlas-world'); old_world = sc.world; sc.world = world
    world.node_tree.nodes['Background'].inputs[0].default_value = (.55, .62, .70, 1); world.node_tree.nodes['Background'].inputs[1].default_value = .8
    saved = (sc.render.engine, sc.render.resolution_x, sc.render.resolution_y, sc.render.filepath, sc.camera)
    hidden = [(col, col.hide_render) for col in hide]
    for col, _ in hidden:
        col.hide_render = True
    sc.render.engine = 'BLENDER_EEVEE'; sc.render.resolution_x = sc.render.resolution_y = TILE_PX
    sc.render.image_settings.file_format = 'PNG'
    try:
        sc.eevee.taa_render_samples = 16
    except AttributeError:
        pass
    atlas = np.zeros((TILE_PX, TILE_PX * ATLAS_TILES, 4), np.float32); atlas[..., 3] = 1
    tiles = []
    for i, w in enumerate(probes):
        cd = bpy.data.cameras.new('atlas'); cd.angle = math.radians(WINDOW_FOV); cd.clip_start = .03
        co = bpy.data.objects.new('atlas', cd); sc.collection.objects.link(co)
        co.location = (w.x, w.side * (L.IN - .02), (w.sill + w.head) / 2)
        co.rotation_euler = Vector((0, -w.side, 0)).to_track_quat('-Z', 'Y').to_euler()
        sc.camera = co
        tmp = path.with_name(f'{path.stem}-{i}.png'); sc.render.filepath = str(tmp)
        bpy.ops.render.render(write_still=True)
        img = bpy.data.images.load(str(tmp))
        px = np.array(img.pixels[:], np.float32).reshape(TILE_PX, TILE_PX, 4)
        atlas[:, i * TILE_PX:(i + 1) * TILE_PX] = px
        bpy.data.images.remove(img); tmp.unlink()
        tiles.append(dict(tile=i, window=w.name, side=w.side, x=w.x, depth_m=room_depth(c, w)))
    out = bpy.data.images.new(path.stem, TILE_PX * ATLAS_TILES, TILE_PX, alpha=False)
    out.pixels.foreach_set(atlas.ravel()); out.filepath_raw = str(path); out.file_format = 'PNG'; out.save()
    bpy.data.images.remove(out)
    sc.render.engine, sc.render.resolution_x, sc.render.resolution_y, sc.render.filepath, sc.camera = saved
    sc.world = old_world
    for col, was in hidden:
        col.hide_render = was
    for k, old in before.items():                   # leave the scene exactly as it was
        coll = getattr(bpy.data, k)
        for d in [d for d in coll if d not in old]:
            coll.remove(d)
    return tiles


def window_material(mat, path):
    """The atlas on the windows' material: a plain textured fallback until the engine's interior-mapping material."""
    img = bpy.data.images.load(str(path)); img.name = path.stem
    nodes = mat.node_tree.nodes
    node = nodes.new('ShaderNodeTexImage'); node.image = img
    mat.node_tree.links.new(node.outputs['Color'], nodes['Principled BSDF'].inputs['Base Color'])
    mat.use_backface_culling = True                 # one-sided: from inside the coach the cards are not there
