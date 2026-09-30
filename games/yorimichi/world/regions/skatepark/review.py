"""Review renders for the skate pier and the board (EEVEE). Called by build.py --review."""
import math
import sys
from pathlib import Path

import bpy
import numpy as np
from mathutils import Vector

import layout as L


def _mat(name, color, emit=0.0, alpha=1.0, vertex=False):
    m = bpy.data.materials.new(name); m.use_nodes = True
    b = m.node_tree.nodes.get('Principled BSDF')
    if vertex:
        vc = m.node_tree.nodes.new('ShaderNodeVertexColor'); vc.layer_name = 'Color'
        m.node_tree.links.new(vc.outputs['Color'], b.inputs['Base Color'])
    else:
        b.inputs['Base Color'].default_value = (*color, 1)
    b.inputs['Roughness'].default_value = .9
    if emit:
        b.inputs['Emission Color'].default_value = (*color, 1); b.inputs['Emission Strength'].default_value = emit
    if alpha < 1:
        b.inputs['Alpha'].default_value = alpha
        try: m.surface_render_method = 'BLENDED'
        except Exception: pass
    return m


def _mesh(name, verts, faces, colors=None, material=None):
    me = bpy.data.meshes.new(name); me.from_pydata(verts, [], faces); me.update()
    if colors is not None:
        a = me.color_attributes.new('Color', 'FLOAT_COLOR', 'POINT')
        for i, c in enumerate(colors): a.data[i].color = (*c, 1)
    if material: me.materials.append(material)
    for p in me.polygons: p.use_smooth = True
    ob = bpy.data.objects.new(name, me); bpy.context.scene.collection.objects.link(ob)
    return ob


def context_terrain(world, h, vmat):
    ox, oy, oz = L.ORIGIN
    xs = np.arange(-240, -10, 2.0); ys = np.arange(-270, -40, 2.0)
    n = len(h); step = 600 / (n - 1)
    V = []; C = []
    for y in ys:
        for x in xs:
            i = int(round((x + 300) / step)); j = int(round((y + 300) / step))
            z = float(h[j, i]) if 0 <= i < n and 0 <= j < n else -20.0
            V.append((x - ox, y - oy, z - oz))
            if z < -0.3: c = (0.16, 0.15, 0.11)
            elif z < 1.6: c = (0.36, 0.30, 0.19)
            else:
                t = min(1, (z - 1.6) / 1.0); c = tuple(np.array((0.36, 0.30, 0.19)) * (1 - t) + np.array((0.075, 0.12, 0.035)) * t)
            C.append(c)
    W = len(xs); F = []
    for r in range(len(ys) - 1):
        for c in range(W - 1):
            a = r * W + c; F.append((a, a + 1, a + W + 1, a + W))
    _mesh('ReviewTerrain', V, F, C, vmat)
    road = np.array(world['road']); m = (road[:, 0] > -260) & (road[:, 0] < 0); R = road[m]
    T = np.gradient(R[:, :2], axis=0); T /= np.linalg.norm(T, axis=1)[:, None]; N = np.column_stack([-T[:, 1], T[:, 0]])
    V = []; F = []
    for i in range(len(R)):
        for s in (-1, 1):
            V.append((R[i, 0] + N[i, 0] * 2.6 * s - ox, R[i, 1] + N[i, 1] * 2.6 * s - oy, R[i, 2] + 0.06 - oz))
    for i in range(len(R) - 1):
        a = 2 * i; F.append((a, a + 2, a + 3, a + 1))
    _mesh('ReviewRoad', V, F, None, _mat('road', (0.10, 0.10, 0.105)))
    for lot in world['houses']['lots']:                  # the houses on the main road, as their roof footprints
        (x, y), z, yaw = lot['centre'], lot['level'], lot['yaw']
        if abs(x - ox) < 150 and abs(y - oy) < 150:
            a = math.radians(yaw); c, s = math.cos(a), math.sin(a)
            fx0, fx1, fy0, fy1 = lot['house_roof']
            corners = [(fx0, fy0), (fx1, fy0), (fx1, fy1), (fx0, fy1)]
            base = [(x + u * c - v * s - ox, y + u * s + v * c - oy) for u, v in corners]
            V = [(bx, by, z - oz) for bx, by in base] + [(bx, by, z - oz + 4.5) for bx, by in base]
            F = [(0, 1, 2, 3), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)]
            _mesh('ReviewHouse', V, F, None, _mat('house', (0.30, 0.22, 0.12)))
    sea = _mesh('ReviewSea', [(-400, -400, -oz), (400, -400, -oz), (400, 400, -oz), (-400, 400, -oz)], [(0, 1, 2, 3)], None,
                _mat('sea', (0.03, 0.10, 0.12), alpha=0.72))
    return sea


def rails_overlay(data):
    col = bpy.data.collections.new('RailsOverlay'); bpy.context.scene.collection.children.link(col)
    mat = _mat('rail_overlay', (1.0, 0.05, 0.6), emit=4.0)
    for r in data['rails']:
        cu = bpy.data.curves.new(r['id'], 'CURVE'); cu.dimensions = '3D'; cu.bevel_depth = 0.07
        sp = cu.splines.new('POLY'); sp.points.add(len(r['points']) - 1)
        for i, p in enumerate(r['points']): sp.points[i].co = (p[0], p[1], p[2] + 0.02, 1)
        cu.materials.append(mat)
        ob = bpy.data.objects.new(r['id'], cu); col.objects.link(ob)
    sp = data['spawns']['park']; p = Vector(sp['pos']); a = math.radians(sp['yaw_deg'])
    cu = bpy.data.curves.new('spawn', 'CURVE'); cu.dimensions = '3D'; cu.bevel_depth = 0.12
    s = cu.splines.new('POLY'); s.points.add(1)
    s.points[0].co = (p.x, p.y, 0.1, 1); s.points[1].co = (p.x + 4 * math.cos(a), p.y + 4 * math.sin(a), 0.1, 1)
    cu.materials.append(_mat('spawn', (0.1, 0.9, 1.0), emit=4.0))
    col.objects.link(bpy.data.objects.new('spawn', cu))
    return col


def clearance_overlay(data):
    col = bpy.data.collections.new('ClearanceOverlay'); bpy.context.scene.collection.children.link(col)
    mat = _mat('clear_overlay', (1.0, 0.85, 0.1), emit=3.0)
    ox, oy, oz = L.ORIGIN
    for k, poly in enumerate(data['clearance']):
        cu = bpy.data.curves.new(f'clear{k}', 'CURVE'); cu.dimensions = '3D'; cu.bevel_depth = 0.15
        s = cu.splines.new('POLY'); s.points.add(len(poly)); s.use_cyclic_u = True
        for i, (x, y) in enumerate(poly + [poly[0]]): s.points[i].co = (x - ox, y - oy, 12.0, 1)
        cu.materials.append(mat); col.objects.link(bpy.data.objects.new(f'clear{k}', cu))
    return col


def camera(name, loc, target, lens=35, ortho=None):
    cd = bpy.data.cameras.new(name); cd.lens = lens; cd.clip_start = 0.02; cd.clip_end = 2000
    if ortho: cd.type = 'ORTHO'; cd.ortho_scale = ortho
    ob = bpy.data.objects.new(name, cd); bpy.context.scene.collection.objects.link(ob)
    ob.location = loc; ob.rotation_euler = (Vector(target) - Vector(loc)).to_track_quat('-Z', 'Y').to_euler()
    return ob


def setup_scene(res=(1600, 1000)):
    sc = bpy.context.scene
    sc.render.engine = 'BLENDER_EEVEE'
    sc.render.resolution_x, sc.render.resolution_y = res; sc.render.resolution_percentage = 100
    sc.render.image_settings.file_format = 'PNG'
    try: sc.view_settings.view_transform = 'AgX'
    except Exception: pass
    if sc.world is None: sc.world = bpy.data.worlds.new('ReviewSky')
    sc.world.use_nodes = True
    bg = sc.world.node_tree.nodes.get('Background'); bg.inputs['Color'].default_value = (0.42, 0.55, 0.72, 1); bg.inputs['Strength'].default_value = 0.55
    try: sc.view_settings.look = 'AgX - Medium High Contrast'
    except Exception: pass
    sc.view_settings.exposure = -0.3
    sun = bpy.data.lights.new('ReviewSun', 'SUN'); sun.energy = 5.5; sun.angle = math.radians(3); sun.color = (1.0, 0.93, 0.82)
    so = bpy.data.objects.new('ReviewSun', sun); sc.collection.objects.link(so)
    so.rotation_euler = (math.radians(50), 0, math.radians(-35))
    try:
        sc.eevee.use_shadows = True
    except Exception: pass
    return sc


def render(sc, cam, path, res=None):
    sc.camera = cam
    if res: sc.render.resolution_x, sc.render.resolution_y = res
    sc.render.filepath = str(path); bpy.ops.render.render(write_still=True)
    print('REVIEW', path, flush=True)


def render_all(outdir, park, board_objs, data, world, h, pl):
    outdir = Path(outdir); outdir.mkdir(parents=True, exist_ok=True)
    sc = setup_scene()
    vmat = _mat('review_vc', (1, 1, 1), vertex=True)
    for ob in park.values():
        ob.data.materials.clear(); ob.data.materials.append(vmat)
    for ob in board_objs.values(): ob.hide_render = True
    context_terrain(world, h, vmat)
    ox, oy, oz = L.ORIGIN
    rails = rails_overlay(data); rails.hide_render = True
    clear = clearance_overlay(data); clear.hide_render = True
    # path frames in local coordinates
    P = pl['P'] - np.array([ox, oy]); Z = pl['z'] - oz; s = pl['s']
    def at(dist):
        k = int(np.searchsorted(s, dist)); return Vector((P[k, 0], P[k, 1], Z[k]))
    shots = {
        'overview': ((-92, 98, 78), (0, 0, 0), 35),
        'overview_sea': ((82, -104, 66), (0, 0, 0), 35),
        'street': ((-6, 5, 7), (-30, 24, 1), 28),
        'bowl': ((6, -35, 15), (29, -10, 1), 30),
        'mini': ((-4, -41, 7), (-24, -28, .4), 30),
        'arrival': (tuple(at(s[-1] - 10) + Vector((0, 0, 1.7))), (6, 8, .7), 30),
    }
    for name, (loc, tgt, lens) in shots.items():
        render(sc, camera('cam_' + name, loc, tgt, lens), outdir / f'{name}.png', (1600, 1000))
    rails.hide_render = False
    render(sc, camera('cam_plan', (0, 0, 120), (0, 0, 0), ortho=120), outdir / 'plan_rails.png', (2000, 1400))
    rails.hide_render = True


def board_review(outdir, objs):
    """Assembled board per the contract, rendered top, bottom, side and three-quarter."""
    sc = bpy.data.scenes.new('BoardStudio')
    sc.render.engine = 'BLENDER_EEVEE'; sc.render.image_settings.file_format = 'PNG'
    try: sc.view_settings.view_transform = 'AgX'
    except Exception: pass
    sc.world = bpy.data.worlds.new('Studio'); sc.world.use_nodes = True
    bg = sc.world.node_tree.nodes.get('Background'); bg.inputs['Color'].default_value = (0.55, 0.57, 0.6, 1); bg.inputs['Strength'].default_value = 1.0
    vmat = bpy.data.materials.get('review_vc')
    def place(name, loc, rotz=0.0):
        src = objs[name]; ob = bpy.data.objects.new(name + '_placed', src.data); sc.collection.objects.link(ob)
        ob.location = loc; ob.rotation_euler = (0, 0, rotz); ob.hide_render = False
        src.data.materials.clear(); src.data.materials.append(vmat)
        return ob
    place('SM_SkateDeck', (0, 0, 0))
    for tx, rz in ((0.18, 0.0), (-0.18, math.pi)):
        place('SM_SkateTruck', (tx, 0, -0.012), rz)
        for wy in (-0.093, 0.093):
            place('SM_SkateWheel', (tx, wy, -0.0635))
    me = bpy.data.meshes.new('floor'); me.from_pydata([(-2, -2, -0.0905), (2, -2, -0.0905), (2, 2, -0.0905), (-2, 2, -0.0905)], [], [(0, 1, 2, 3)])
    fl = bpy.data.objects.new('floor', me); sc.collection.objects.link(fl); me.materials.append(_mat('floor', (0.22, 0.22, 0.23)))
    for nm, rot, e in (('key', (math.radians(35), 0, math.radians(30)), 3.5), ('fill', (math.radians(140), 0, math.radians(-120)), 1.5)):
        ld = bpy.data.lights.new(nm, 'SUN'); ld.energy = e; lo = bpy.data.objects.new(nm, ld); sc.collection.objects.link(lo); lo.rotation_euler = rot
    views = {'board_top': ((0, 0, 2.0), (0, 0, 0), 0.95), 'board_bottom': ((0, 0, -2.0), (0, 0, 0), 0.95),
             'board_side': ((0, -2.0, -0.03), (0, 0, -0.03), 0.95), 'board_three_quarter': ((0.75, -0.65, 0.42), (0, 0, -0.03), None)}
    for name, (loc, tgt, ortho) in views.items():
        fl.hide_render = name == 'board_bottom'
        cd = bpy.data.cameras.new(name); cd.clip_start = 0.01
        if ortho: cd.type = 'ORTHO'; cd.ortho_scale = ortho
        else: cd.lens = 50
        ob = bpy.data.objects.new(name, cd); sc.collection.objects.link(ob); ob.location = loc
        up = 'Y' if name not in ('board_top', 'board_bottom') else 'X'
        ob.rotation_euler = (Vector(tgt) - Vector(loc)).to_track_quat('-Z', 'Y').to_euler()
        if name in ('board_top', 'board_bottom'):
            ob.rotation_euler = (0, 0, 0) if name == 'board_top' else (math.pi, 0, 0)
        sc.camera = ob; sc.render.resolution_x, sc.render.resolution_y = (1400, 500) if ortho else (1200, 800)
        sc.render.filepath = str(Path(outdir) / f'{name}.png'); bpy.ops.render.render(write_still=True, scene=sc.name)
        print('REVIEW', name, flush=True)
