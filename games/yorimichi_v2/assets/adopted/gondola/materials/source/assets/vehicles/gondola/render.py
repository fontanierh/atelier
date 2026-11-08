"""Review renders of the gondola pieces from cameras fitted to the concepts (cameras.json), plus plain elevations.

blender --background --factory-startup --threads 3 --python-exit-code 1 -P games/yorimichi/assets/vehicles/gondola/render.py
Reads the per-piece .blend files that build.py wrote in build/yorimichi/gondola/ and writes PNGs to
build/yorimichi/gondola/review/. $GONDOLA_VIEWS limits a run to some views (comma separated). compare.py then puts
each matched view next to its concept.

Review-only props (never exported): the haul ropes, a cabin hanging at a station berth or on a tower's rope, a ground
block and a painted-sky world. Glass renders see-through here; the exported material is just named GD_Glass.
"""
import sys as _sys; from pathlib import Path as _Path; _sys.path.insert(0, str(_Path(__file__).resolve().parents[3] / 'world')); import yori  # noqa: E402,F401
_sys.path.insert(0, str(_Path(__file__).resolve().parent))
import json  # noqa: E402
import math  # noqa: E402
import os  # noqa: E402

import bpy  # noqa: E402
from mathutils import Matrix, Vector  # noqa: E402

import params as P  # noqa: E402
import rope as R  # noqa: E402
from cabin import GRIP  # noqa: E402

OUT = yori.OUT / 'gondola'
REVIEW = OUT / 'review'
HERE = _Path(__file__).resolve().parent
CAMS = json.loads((HERE / 'cameras.json').read_text())
PRM = P.load(); DRV = P.derived(PRM)


def srgb(c):
    return tuple(((v / 255) / 12.92) if v / 255 <= 0.04045 else (((v / 255) + 0.055) / 1.055) ** 2.4 for v in c)


def material(name, rgb, rough=0.8, metal=0.0, alpha=1.0):
    m = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    try:
        m.use_nodes = True
    except Exception:
        pass
    b = m.node_tree.nodes.get('Principled BSDF')
    b.inputs['Base Color'].default_value = (*srgb(rgb), 1); b.inputs['Roughness'].default_value = rough
    b.inputs['Metallic'].default_value = metal; b.inputs['Alpha'].default_value = alpha
    if alpha < 1:
        m.surface_render_method = 'DITHERED'
    return m


def reset():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    for engine in ('BLENDER_EEVEE', 'BLENDER_EEVEE_NEXT'):
        try:
            scene.render.engine = engine
            break
        except TypeError:
            continue
    scene.render.film_transparent = False
    scene.render.image_settings.file_format = 'PNG'
    scene.render.image_settings.color_mode = 'RGB'
    scene.view_settings.view_transform = 'Standard'
    try:
        scene.eevee.taa_render_samples = 40
    except AttributeError:
        pass
    try:
        scene.eevee.use_shadows = True
    except AttributeError:
        pass
    return scene


def append(blend, names=None):
    path = str(OUT / blend)
    with bpy.data.libraries.load(path, link=False) as (src, dst):
        dst.objects = [n for n in src.objects if (names is None or n in names) and not n.startswith('UCX_') and not n.endswith('_Collision')]
    objs = []
    for o in dst.objects:
        if o is not None:
            bpy.context.scene.collection.objects.link(o); objs.append(o)
    glass = bpy.data.materials.get('GD_Glass')
    if glass:
        b = glass.node_tree.nodes.get('Principled BSDF'); b.inputs['Alpha'].default_value = 0.12; b.inputs['Roughness'].default_value = 0.05
        try:
            glass.surface_render_method = 'BLENDED'
        except (TypeError, AttributeError):
            glass.surface_render_method = 'DITHERED'
        try:
            glass.use_transparent_shadow = True
        except AttributeError:
            pass
    return objs


def world(scene, top, horizon, bottom, fill=(178, 200, 230), strength=0.65, split=0.5):
    w = bpy.data.worlds.new('Review'); scene.world = w
    try:
        w.use_nodes = True
    except Exception:
        pass
    nodes, links = w.node_tree.nodes, w.node_tree.links
    bg = nodes.get('Background'); bg.inputs['Color'].default_value = (*srgb(fill), 1); bg.inputs['Strength'].default_value = strength
    sky = nodes.new('ShaderNodeBackground'); sky.inputs['Strength'].default_value = 1.0
    coord = nodes.new('ShaderNodeTexCoord'); sep = nodes.new('ShaderNodeSeparateXYZ'); ramp = nodes.new('ShaderNodeValToRGB')
    ramp.color_ramp.elements[0].position = 0.0; ramp.color_ramp.elements[0].color = (*srgb(bottom), 1)
    ramp.color_ramp.elements[1].position = 1.0; ramp.color_ramp.elements[1].color = (*srgb(top), 1)
    e = ramp.color_ramp.elements.new(split); e.color = (*srgb(horizon), 1)
    links.new(coord.outputs['Window'], sep.inputs[0]); links.new(sep.outputs['Y'], ramp.inputs['Fac'])
    links.new(ramp.outputs['Color'], sky.inputs['Color'])
    path = nodes.new('ShaderNodeLightPath'); mix = nodes.new('ShaderNodeMixShader')
    links.new(path.outputs['Is Camera Ray'], mix.inputs['Fac'])
    links.new(bg.outputs['Background'], mix.inputs[1]); links.new(sky.outputs['Background'], mix.inputs[2])
    links.new(mix.outputs['Shader'], nodes.get('World Output').inputs['Surface'])


def sun(scene, elev, azim, energy=4.2, color=(255, 228, 190)):
    s = bpy.data.lights.new('Sun', 'SUN'); s.energy = energy; s.color = srgb(color); s.angle = math.radians(5)
    ob = bpy.data.objects.new('Sun', s); scene.collection.objects.link(ob)
    ob.rotation_euler = (math.radians(90 - elev), 0, math.radians(azim + 90))
    return ob


def tube_obj(name, pts, r, mat, n=10):
    me = bpy.data.meshes.new(name); verts = []; faces = []
    P_ = [Vector(p) for p in pts]
    for i, c in enumerate(P_):
        t = (P_[min(i + 1, len(P_) - 1)] - P_[max(i - 1, 0)]).normalized()
        a = t.orthogonal().normalized(); b = t.cross(a)
        for k in range(n):
            ang = 2 * math.pi * k / n; verts.append(tuple(c + r * (math.cos(ang) * a + math.sin(ang) * b)))
    for i in range(len(P_) - 1):
        for k in range(n):
            j = (k + 1) % n; faces.append((i * n + k, i * n + j, (i + 1) * n + j, (i + 1) * n + k))
    faces.append(tuple(reversed(range(n)))); faces.append(tuple((len(P_) - 1) * n + k for k in range(n)))
    me.from_pydata(verts, [], faces); me.materials.append(mat)
    for poly in me.polygons:
        poly.use_smooth = True
    ob = bpy.data.objects.new(name, me); bpy.context.scene.collection.objects.link(ob)
    return ob


def rope_mat():
    return material('ReviewRope', (58, 60, 64), 0.36, 0.85)


def strand_rope(name, path, start=0.0, end=None, sides=7):
    """The haul rope as six helical strands round a core (rope.strand_rings), from the same RopePath as the grip."""
    mat = rope_mat(); strands, core = R.strand_rings(path, start, end)
    obs = [tube_obj(f'{name}Strand{k}', pts, rs * 1.04, mat, n=sides) for k, (rs, pts) in enumerate(strands)]
    end = path.length if end is None else end
    n = max(2, int((end - start) / 0.25))
    obs.append(tube_obj(f'{name}Core', [path.rope_point(start + (end - start) * k / n) for k in range(n + 1)], core, mat, n=8))
    return obs


def door_open(objs):
    """Slide the two door leaves to their open pose (offsets recorded by the build)."""
    info = json.loads((OUT / 'piece_cabin.json').read_text())['door_frame']['leaves']['open_offsets']
    for o in objs:
        if o.name in info:
            o.location = Vector(info[o.name])


def look(name, pos, target, lens, size, roll=0.0):
    data = bpy.data.cameras.new(name); data.lens = lens; data.sensor_width = 36.0; data.clip_start = 0.02; data.clip_end = 3000
    ob = bpy.data.objects.new(name, data); bpy.context.scene.collection.objects.link(ob)
    ob.location = pos; d = Vector(target) - Vector(pos)
    ob.rotation_euler = d.to_track_quat('-Z', 'Y').to_euler()
    scene = bpy.context.scene; scene.render.resolution_x, scene.render.resolution_y = size; scene.render.resolution_percentage = 100
    return ob


def ground_block(name, z, size, rgb, cx=0.0, cy=0.0, depth=2.0):
    me = bpy.data.meshes.new(name); s = size; d = depth
    v = [(cx - s, cy - s, z - d), (cx + s, cy - s, z - d), (cx + s, cy + s, z - d), (cx - s, cy + s, z - d),
         (cx - s, cy - s, z), (cx + s, cy - s, z), (cx + s, cy + s, z), (cx - s, cy + s, z)]
    me.from_pydata(v, [], [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)])
    me.materials.append(material(name + 'Mat', rgb, 0.95))
    ob = bpy.data.objects.new(name, me); bpy.context.scene.collection.objects.link(ob)
    return ob


def camera_from(name, key=None, scale=1.0):
    c = CAMS[key or name]; w, h = c['size']
    data = bpy.data.cameras.new(name); ob = bpy.data.objects.new(name, data); bpy.context.scene.collection.objects.link(ob)
    yaw, pitch, roll = c['yaw'], c['pitch'], c['roll']
    d = Vector((math.cos(pitch) * math.cos(yaw), math.cos(pitch) * math.sin(yaw), -math.sin(pitch)))
    right = d.cross(Vector((0, 0, 1))).normalized(); up = right.cross(d)
    r2 = math.cos(roll) * right + math.sin(roll) * up; u2 = -math.sin(roll) * right + math.cos(roll) * up
    ob.matrix_world = Matrix.Translation(c['pos']) @ Matrix((r2, u2, -d)).transposed().to_4x4()
    data.sensor_fit = 'HORIZONTAL'; data.sensor_width = 36.0; data.lens = c['focal_px'] * 36.0 / w
    off = c.get('principal_offset_px', [0, 0]); big = max(w, h)
    data.shift_x = -off[0] / big; data.shift_y = off[1] / big
    data.clip_start = 0.02; data.clip_end = 3000
    scene = bpy.context.scene
    scene.render.resolution_x, scene.render.resolution_y = int(w * scale), int(h * scale); scene.render.resolution_percentage = 100
    return ob


def ortho(name, loc, rot, scale, size):
    data = bpy.data.cameras.new(name); data.type = 'ORTHO'; data.ortho_scale = scale; data.clip_end = 3000
    ob = bpy.data.objects.new(name, data); bpy.context.scene.collection.objects.link(ob)
    ob.location = loc; ob.rotation_euler = tuple(math.radians(a) for a in rot)
    scene = bpy.context.scene; scene.render.resolution_x, scene.render.resolution_y = size; scene.render.resolution_percentage = 100
    return ob


SHOTS = {w.strip() for w in os.environ.get('GONDOLA_SHOTS', '').split(',') if w.strip()}   # empty: every shot


def shoot(scene, cam, name):
    if SHOTS and name not in SHOTS:
        return
    scene.camera = cam; scene.render.filepath = str(REVIEW / f'{name}.png')
    bpy.ops.render.render(write_still=True); print('rendered', name, flush=True)


# ------------------------------------------------------------------ views
def view_cabin():
    scene = reset(); append('cabin.blend')
    world(scene, (70, 140, 222), (176, 206, 238), (214, 150, 62), split=0.55)
    sun(scene, 46, 200)
    rr = PRM['rope_radius']; G = DRV['grip_to_floor']
    line = R.straight((-30, 0, 0), (30, 0, 0), rr, step=0.5)
    rope = strand_rope('Rope', line, 10.0, 50.0)
    shoot(scene, camera_from('cabin_exterior'), 'cabin_exterior')
    # Interior: daylight through the windows (sun) and a soft, low fill under the ceiling.
    a = bpy.data.lights.new('Fill', 'AREA'); a.energy = 14; a.size = 1.6; a.color = srgb((255, 236, 210))
    ob = bpy.data.objects.new('Fill', a); scene.collection.objects.link(ob); ob.location = (0.3, 0, -G + 2.0)
    shoot(scene, camera_from('cabin_interior'), 'cabin_interior')
    bpy.data.objects.remove(ob)
    shoot(scene, ortho('CabSide', (0, -20, -2.0), (90, 0, 0), 6.2, (900, 900)), 'cabin_side')
    shoot(scene, ortho('CabEnd', (20, 0, -2.0), (90, 0, 90), 6.2, (900, 900)), 'cabin_end')
    shoot(scene, ortho('CabTop', (0, 0, 20), (0, 0, 0), 3.4, (700, 700)), 'cabin_top')
    # Grip on the rope: side (door side), front along the rope (rope cut just ahead of the jaws), 3/4 from above.
    shoot(scene, look('GripSide', (0.15, -1.9, 0.18), (0.0, 0.0, -0.05), 50, (1000, 800)), 'cabin_grip_side')
    shoot(scene, look('GripAbove', (1.05, -0.95, 0.85), (0.0, -0.08, 0.0), 50, (1000, 800)), 'cabin_grip_above')
    for o in rope:
        bpy.data.objects.remove(o)
    cut = strand_rope('RopeCut', line, 10.0, 30.35)
    shoot(scene, look('GripFront', (2.4, -0.25, 0.25), (0.0, -0.12, -0.02), 120, (900, 900)), 'cabin_grip_front')
    shoot(scene, ortho('GripFrontOrtho', (3.0, -0.12, -0.02), (90, 0, 90), 0.85, (900, 900)), 'cabin_grip_section')
    for o in cut:
        bpy.data.objects.remove(o)
    # Riding distance: the cabin as seen from a cabin on the other track, ~35 m away, on a sagging span.
    span = R.RopePath([(x * 0.5, 0.0, 0.0025 * (x * 0.5) ** 2) for x in range(-160, 161)], rr)
    strand_rope('Span', span)
    cam = look('Riding', (-24.0, -25.0, -1.0), (0.0, 0.0, -2.2), 50, (1280, 800))
    shoot(scene, cam, 'cabin_riding_distance')
    for o in [o for o in scene.objects if o.name.startswith('Span')]:
        bpy.data.objects.remove(o)
    # Steepest span (75 % grade, as the crater-floor line): the grip pitches with the rope, the cabin hangs plumb with its floor level.
    cab = [o for o in scene.objects if o.name.startswith('GD_Cabin')]
    hide(cab)
    steep = R.straight((-30.0, 0.0, -22.5), (30.0, 0.0, 22.5), rr, step=0.25)
    srope = strand_rope('Steep', steep, steep.length / 2 - 8, steep.length / 2 + 8)
    placed = place_cabin(cab, steep.grip_frame(steep.length / 2, (0, -1, 0)), 'steep')
    Cm = Matrix(R.hang_frame([list(r) for r in steep.grip_frame(steep.length / 2, (0, -1, 0))], GRIP['pivot']))
    pv = Cm @ Vector(GRIP['pivot'])
    guides = [rod('GuideLevel', (pv.x - 1.6, -1.3, -G - 0.004), (pv.x + 1.6, -1.3, -G - 0.004), 0.012, (220, 40, 40)),
              rod('GuidePlumb', (pv.x, -1.3, pv.z + 0.25), (pv.x, -1.3, -G - 0.1), 0.012, (220, 40, 40))]
    shoot(scene, ortho('SteepSide', (pv.x, -20, -1.55), (90, 0, 0), 6.4, (1000, 1000)), 'cabin_steep_side')
    for o in guides:
        bpy.data.objects.remove(o)
    shoot(scene, look('SteepJunction', (pv.x + 0.95, pv.y - 1.25, pv.z + 0.15), (pv.x, pv.y + 0.1, pv.z + 0.1), 45, (1000, 900)),
          'cabin_steep_junction')
    for o in placed + srope:
        bpy.data.objects.remove(o)
    for o in cab:
        o.hide_render = False
    grip_diagrams(scene, rr)
    # Doors open: the boarding aisle from the platform, at eye height.
    door_open(scene.objects)
    a = bpy.data.lights.new('Fill2', 'AREA'); a.energy = 14; a.size = 1.6
    ob = bpy.data.objects.new('Fill2', a); scene.collection.objects.link(ob); ob.location = (0.3, 0, -G + 2.0)
    shoot(scene, look('DoorOpen', (0.0, -3.4, -G + 1.6), (0.0, 0.2, -G + 0.75), 28, (1000, 900)), 'cabin_door_open')
    shoot(scene, ortho('DoorOpenTop', (0, 0, -G + 1.9), (0, 0, 0), 3.6, (800, 800)), 'cabin_door_open_plan')


def grip_diagrams(scene, rr):
    """End view and section through the grip on a level rope, labelled: rope, jaws, clamp, pivot pin, hanger, the
    running wheels' axles and, for reference, a piece of station rail under the wheels (stations only)."""
    g = GRIP; wy, wz, wr, ww = g['wheel_y'], g['wheel_z'], g['wheel_radius'], g['wheel_width']
    line = R.straight((-30, 0, 0), (30, 0, 0), rr, step=0.5)
    rope = strand_rope('EndRope', line, 10.0, 30.32)                      # cut just past the near wheel
    rail = block('RefRail', (-0.7, 0.7, wy - ww / 2 - 0.01, wy + ww / 2 + 0.01, wz - wr - 0.115, wz - wr), (226, 140, 40))
    px, py, pz = g['pivot']
    for tag, clip in (('end', None), ('section', 3.0)):
        cam = ortho(f'Grip_{tag}', (3.0, -0.08, -0.1), (90, 0, 90), 1.3, (1100, 1100))
        if clip:
            cam.data.clip_start = clip                                     # cut at x = 0, through the jaws
        X = 0.6 if not clip else -0.01
        T = 0.026; L = -0.71; Rt = 0.17
        right = [('haul rope, 90 mm', (X, 0.03, 0.03), (X, Rt, 0.33)),
                 ('jaws closed on the rope', (X, 0.06, 0.07), (X, Rt, 0.25)),
                 ('clamp body', (X, 0.03, 0.16), (X, Rt, 0.42)),
                 ('side plate', (X, 0.115, -0.05), (X, Rt, -0.12))]
        left = [('pivot pin\n(cabin hangs plumb)', (X, py - 0.06, pz), (X, L, -0.27)),
                ('hanger post', (X, py, -0.45), (X, L, -0.5)),
                ('wheel axle', (X, -0.2, wz), (X, L, 0.1)),
                ('running wheel\n(station rail only)', (X, wy, wz + wr - 0.03), (X, L, 0.4)),
                ('station rail\n(stations only)', (X, wy - 0.02, wz - wr - 0.06), (X, L, -0.08))]
        made = []
        for k, (text, anc, at) in enumerate(right):
            made += label(f'R{tag}{k}', text, anc, at, T, cam, align='LEFT')
        for k, (text, anc, at) in enumerate(left):
            w = max(len(t) for t in text.split('\n')) * T * 0.52
            made += label(f'Lf{tag}{k}', text, anc, at, T, cam, align='LEFT', leader_end=(at[0], at[1] + w + 0.01, at[2]))
        shoot(scene, cam, f'cabin_grip_{tag}_view')
        for o in made:
            bpy.data.objects.remove(o)
    for o in rope + [rail]:
        bpy.data.objects.remove(o)


def disc(name, c, r, z0, z1, rgb, n=40):
    me = bpy.data.meshes.new(name); v = []
    for z in (z0, z1):
        v += [(c[0] + r * math.cos(2 * math.pi * k / n), c[1] + r * math.sin(2 * math.pi * k / n), z) for k in range(n)]
    f = [tuple(range(n))[::-1], tuple(range(n, 2 * n))] + [(k, (k + 1) % n, n + (k + 1) % n, n + k) for k in range(n)]
    me.from_pydata(v, [], f); me.materials.append(material(name + 'Mat', rgb, 0.95))
    ob = bpy.data.objects.new(name, me); bpy.context.scene.collection.objects.link(ob)
    return ob


def place_cabin(objs, M, tag):
    """Copies of the cabin objects placed for a grip frame M (rope.grip_frame): the grip follows the rope, the
    hanger, body and doors hang plumb from the pivot pin (rope.hang_frame)."""
    rows = [list(r) for r in (M if not isinstance(M, Matrix) else [M[i] for i in range(4)])]
    G = Matrix(rows); C = Matrix(R.hang_frame(rows, GRIP['pivot'])); out = []
    for o in objs:
        c = o.copy(); c.name = f'{o.name}_{tag}'; c.hide_render = False; bpy.context.scene.collection.objects.link(c)
        c.matrix_world = (G if o.name.startswith('GD_CabinGrip') else C) @ o.matrix_world; out.append(c)
    return out


def rod(name, a, b, w, rgb):
    """A thin square bar from a to b (review guides: plumb and level lines)."""
    me = bpy.data.meshes.new(name); A, B = Vector(a), Vector(b); d = (B - A).normalized()
    u = d.orthogonal().normalized() * w / 2; v = d.cross(u).normalized() * w / 2
    vs = [tuple(P + su * u + sv * v) for P in (A, B) for su, sv in ((-1, -1), (1, -1), (1, 1), (-1, 1))]
    fs = [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)]
    me.from_pydata(vs, [], fs); me.materials.append(material(name + 'Mat', rgb, 0.6))
    ob = bpy.data.objects.new(name, me); bpy.context.scene.collection.objects.link(ob)
    return ob


GUIDE = (205, 30, 30)


def label(name, text, anchor, at, size, cam, align='LEFT', rgb=GUIDE, leader_end=None):
    """A review label facing the camera, with a thin leader line from the anchor point to the text (or leader_end)."""
    cu = bpy.data.curves.new(name, 'FONT'); cu.body = text; cu.size = size; cu.align_x = align; cu.align_y = 'CENTER'
    ob = bpy.data.objects.new(name, cu); bpy.context.scene.collection.objects.link(ob)
    ob.location = at; ob.rotation_euler = cam.rotation_euler
    cu.materials.append(material(name + 'Mat', rgb, 0.6))
    return [ob, rod(name + 'Leader', anchor, leader_end or at, size * 0.09, rgb)]


def block(name, box, rgb):
    """An axis-aligned review block (x0, x1, y0, y1, z0, z1)."""
    x0, x1, y0, y1, z0, z1 = box; me = bpy.data.meshes.new(name)
    me.from_pydata([(x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0), (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)], [],
                   [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)])
    me.materials.append(material(name + 'Mat', rgb, 0.6))
    ob = bpy.data.objects.new(name, me); bpy.context.scene.collection.objects.link(ob)
    return ob


def hide(objs):
    for o in objs:
        o.hide_render = True


def flat_world(scene, rgb=(221, 216, 207)):
    world(scene, rgb, rgb, rgb, fill=(206, 212, 222), strength=0.75)


def view_towers():
    scene = reset(); append('towers.blend')
    cab = append('cabin.blend'); hide(cab)
    H = PRM['review_tower_height']; rr = PRM['rope_radius']; g = PRM['gauge']
    flat_world(scene); sun(scene, 48, 215, energy=4.0)
    ropes = []
    for y in (-g / 2, g / 2):
        path = R.over_tower(H, y, rr, span=60.0, step=0.25)
        ropes.append(path); strand_rope(f'Rope{y:+.0f}', path, path.length / 2 - 22, path.length / 2 + 22)
    soil = disc('Soil', (0, 0), 5.0, -1.05, 0.0, (150, 140, 120))
    for name in ('tower_front', 'tower_side', 'tower_head', 'tower_base', 'tower_anchor'):
        shoot(scene, camera_from(name), name)
    hide([soil])
    # Scenes: a cabin on the rope beside the tower, rocky ground and sky.
    world(scene, (70, 140, 222), (186, 210, 236), (150, 130, 100), split=0.55)
    ground_block('Ground', -0.25, 120, (128, 118, 104))
    for x, side in ((9.0, 0), (-15.0, 1)):
        path = ropes[side]; s_ = path.length / 2 + x
        place_cabin(cab, path.grip_frame(s_, (0, -1 if side == 0 else 1, 0)), f'c{x}')
    shoot(scene, camera_from('tower_scene'), 'tower_scene')
    shoot(scene, camera_from('tower_vista'), 'tower_vista')
    # Grip passing over the sheave train (on the rope frame at the tower centre).
    place_cabin(cab, ropes[0].grip_frame(ropes[0].length / 2 + 0.3, (0, -1, 0)), 'pass')
    shoot(scene, look('TowerPass', (1.9, -5.6, H + 0.6), (0.3, -3.0, H - 0.2), 35, (1000, 800)), 'tower_cabin_pass')


def view_station(key):
    scene = reset(); append(f'station{key}.blend')
    cab = append('cabin.blend'); hide(cab)
    info = json.loads((OUT / f'piece_station_{key}.json').read_text())
    Zr = info['rope_height']; rr = PRM['rope_radius']; xm = info['station_mouth_x']
    world(scene, (70, 140, 222), (186, 210, 236), (150, 130, 100), split=0.55)
    sun(scene, 44, 205, energy=4.0)
    ground = {'valley': (-0.3, (112, 128, 76)), 'rim': (-3.5, (104, 96, 88)), 'crater': (-1.2, (92, 84, 78))}[key]
    ground_block('Ground', ground[0], 160, ground[1])
    for b in info['berths']:
        s = b['side']; M = Matrix.Translation(b['cabin_grip']) @ Matrix.Rotation(math.radians(b['cabin_yaw_deg']), 4, 'Z')
        place_cabin(cab, M, f'berth{s}')
    slope = {'valley': 0.32, 'rim': -0.18, 'crater': 0.75}[key]
    for y in (-1, 1):
        a = (xm + 0.6, y * PRM['gauge'] / 2, Zr); b_ = (xm + 0.6 + 70, y * PRM['gauge'] / 2, Zr + 70 * slope)
        strand_rope(f'Line{y}', R.straight(a, b_, rr, step=0.5))
    for k, xo in enumerate((16.0, 34.0)):
        y = -PRM['gauge'] / 2 if k == 0 else PRM['gauge'] / 2
        line = R.straight((xm + 0.6, y, Zr), (xm + 70.6, y, Zr + 70 * slope), rr)
        place_cabin(cab, line.grip_frame(xo, (0, -1 if y < 0 else 1, 0)), f'line{k}')
    shoot(scene, camera_from(f'{key}_view'), f'{key}_view')
    span = {'valley': 46, 'rim': 52, 'crater': 40}[key]
    shoot(scene, ortho(f'{key}Top', (-2, -4, 60), (0, 0, 0), span, (1100, 1100)), f'{key}_top')
    shoot(scene, look(f'{key}Over', (30, -34, 26), (-2, -2, 1.5), 28, (1400, 900)), f'{key}_overview')
    pos, tgt = BERTH_CAM.get(key, ((xm - 3.0, -7.4, 1.7), (3.4, -3.0, 1.4)))
    sight_clear(key, pos, tgt)
    shoot(scene, look(f'{key}Berth', pos, tgt, 24, (1200, 850)), f'{key}_berth')
    # Close-ups: the bullwheel bay from the deck at eye height, and a roof eave with its post, brackets and tails.
    for tag, (pos, tgt, lens) in CLOSE[key].items():
        shoot(scene, look(f'{key}_{tag}', pos, tgt, lens, (1400, 1000)), f'{key}_{tag}')
    if key == 'valley':
        mouth_views(scene, cab, Zr, info['rope_height_in_station'], rr, xm)


# Berth views: from the plaza or deck, outside every post, at eye height. sight_clear() refuses a camera that stands
# in or within 0.3 m of a collision proxy, or whose first 3 m of sight line passes through one (valley: the cross-gable
# post at x 4.4 stood in front of the default camera).
BERTH_CAM = {'valley': ((2.0, -8.6, 1.7), (3.4, -3.0, 1.4))}


def sight_clear(key, pos, tgt, margin=0.3, reach=3.0):
    L = json.loads((OUT / f'layout_{key}.json').read_text())
    d = [t - p for p, t in zip(pos, tgt)]; n = math.sqrt(sum(c * c for c in d)); d = [c / n for c in d]
    for k in range(int(reach / 0.1) + 1):
        q = [p + c * 0.1 * k for p, c in zip(pos, d)]
        for pr in L['obstacles']:
            xs = [v[0] for v in pr['poly']]; ys = [v[1] for v in pr['poly']]
            if (min(xs) - margin <= q[0] <= max(xs) + margin and min(ys) - margin <= q[1] <= max(ys) + margin
                    and min(pr['z0']) - margin <= q[2] <= max(pr['z1']) + margin):
                raise SystemExit(f'{key} berth camera: sight line {0.1 * k:.1f} m out is in or near proxy {pr["name"]}')


def mouth_views(scene, cab, Zr, Zs, rr, xm):
    """At the station mouth: a cabin just inside (grip on the running rail, rope dropped below the jaws) and one
    just outside (wheels off the rail, jaws on the rope); a 3/4 side view and a section along the rope's plane."""
    Rb = PRM['gauge'] / 2; g = GRIP; x0 = xm + 0.6
    gl = R.station_loop(Rb, Zr, Zr, xm, rr)                                 # the grips' line (rail), as stations.py
    xin, xout = xm - 1.3, xm + 0.3
    placed = []
    for x, tag in ((xin, 'in'), (xout, 'out')):
        placed += place_cabin(cab, gl.grip_frame(x0 - x, (0, -1, 0)), f'mouth_{tag}')
    yw = -Rb + g['wheel_y']; zw = Zr + g['wheel_z']; zr = Zr + g['wheel_z'] - g['wheel_radius']
    cam = look('MouthSide', (xm - 0.5, -Rb - 3.6, Zr + 1.1), (xm - 0.5, -Rb, Zr - 0.05), 30, (1400, 900))
    Y = -Rb - 0.9; T = 0.06
    items = [('running wheels on the station rail', (xin - 0.36, yw, zr + 0.02), (xin - 1.9, Y, Zr + 0.75)),
             ('station rail ends at the mouth', (xm + 0.28, yw, zr - 0.05), (xm - 0.2, Y, Zr - 0.75)),
             (f'haul rope drops {Zr - Zs:.2f} m inside the mouth: grip detached', (xin + 0.6, -Rb, Zr - 0.14), (xin - 1.9, Y, Zr - 0.55)),
             ('outside: jaws on the rope, wheels free', (xout + 0.1, -Rb - 0.1, Zr + 0.12), (xout - 0.6, Y, Zr + 0.95))]
    made = []
    for k, (text, anc, at) in enumerate(items):
        made += label(f'M{k}', text, anc, at, T, cam)
    shoot(scene, cam, 'station_mouth_side')
    for o in made:
        bpy.data.objects.remove(o)
    loop = R.station_loop(Rb, Zr, Zs, xm, rr); z_in = loop.rope_point(loop.nearest((xin, -Rb, Zs))[1])[2]
    cam = ortho('MouthSection', (xm - 0.5, -Rb - 6.0, Zr - 0.15), (90, 0, 0), 3.4, (1400, 900))
    cam.data.clip_start = 6.0 - 0.006                                        # cut along the rope's vertical plane
    Y = -Rb - 0.005; T = 0.055
    items = [('rope seated in the jaw groove: attached', (xout, Y, Zr + 0.03), (xout - 1.2, Y, Zr + 0.75)),
             (f'rope {Zr - z_in:.2f} m below the jaws here, {Zr - Zs:.2f} m from 1.6 m in: detached\n(the jaws open here; modelled closed)',
              (xin, Y, Zr - 0.12), (xin - 0.9, Y, Zr - 0.75)),
             ('rope ramps up to the grip line at the mouth', (xm - 0.4, Y, Zr - 0.05), (xm - 0.6, Y, Zr - 1.05))]
    made = []
    for k, (text, anc, at) in enumerate(items):
        made += label(f'S{k}', text, anc, at, T, cam)
    shoot(scene, cam, 'station_mouth_section')
    for o in made + placed:
        bpy.data.objects.remove(o)


CLOSE = {
    'valley': {'bullwheel': ((-5.5, -5.8, 1.7), (0.5, 0.5, 4.6), 18), 'eave': ((-0.5, -11.5, 2.0), (-2.0, -7.3, 5.2), 24)},
    'rim': {'bullwheel': ((-3.0, -8.0, 1.7), (0.5, 0.0, 4.8), 18), 'eave': ((-10.6, -8.6, 1.7), (-12.8, -4.9, 4.4), 22)},
    'crater': {'bullwheel': ((4.0, -6.0, 1.7), (-1.0, 0.5, 4.4), 18), 'eave': ((5.2, -10.5, 1.0), (3.0, -7.2, 4.8), 22)},
}


VIEWS = {'cabin': view_cabin, 'towers': view_towers, 'valley': lambda: view_station('valley'),
         'rim': lambda: view_station('rim'), 'crater': lambda: view_station('crater')}


def main():
    REVIEW.mkdir(parents=True, exist_ok=True)
    wanted = [w.strip() for w in os.environ.get('GONDOLA_VIEWS', ','.join(VIEWS)).split(',') if w.strip()]
    for name in wanted:
        if name in VIEWS:
            VIEWS[name]()


if __name__ == '__main__':
    main()
