"""Review contact sheets for the skate rider clips (cairo_skate_clips.py), with a board proxy of the SKATE.md dimensions.

    blender -b --threads 4 --python-exit-code 1 --python games/yorimichi/assets/characters/tools/cairo_skate_review.py -- \
        [--blend output/.../game-r17/WarmOriginal-Game-r17.blend] [--clips SkateStance,SkateOllieGoofy] [--columns 8] \
        [--out output/.../skate-r01/review] [--size 300]

Each clip gets one sheet: three rows of views (from behind the board = the game camera, from the toe side in front of
the rider, from above the toe side) and `--columns` evenly spaced frames. The board proxy sits at its rest place, or
where the game will move it (SkateOllie/SkateNollie pitch about the wheels, manual tilts, the flip); while the board
moves, the feet in contact follow it with a two-bone leg solve, as the game's IK will do. The rows are labelled with
the time. Sheets are assembled with Pillow in the imagegen venv (Blender's python has none).
"""
import sys as _sys; from pathlib import Path as _Path; _sys.path.insert(0, str(_Path(__file__).resolve().parents[3] / 'world')); import yori  # noqa: E402
import sys as _sys; from pathlib import Path as _Path; _sys.path.insert(0, str(_Path(__file__).resolve().parent))  # Blender's --python does not add the script's folder
from _archive import ROOT, TOOLS  # noqa: E402  (ROOT: the prototype archive holding the revision history)
import argparse, json, math, subprocess, sys
from pathlib import Path
try:
    import bpy
    import numpy as np
    from mathutils import Matrix, Vector
    sys.path.insert(0, str(Path(__file__).parent))
    import cairo_skate_clips as W
    from cairo_outfit_correctives import set_clip
    from cairo_rig import Rig, BODY, HAND_PROPS, bn
except ImportError:                      # the Pillow sheet step runs outside Blender
    bpy = None

# ROOT (the archive) comes from _archive
VENV = Path(sys.executable)
VIEWS = {'behind': (0., -1., .30), 'toe side': (1., 0., .10), 'above': (.75, -.55, .85)}
EXTRA_VIEWS = {'front': (1., .35, .25), 'nose': (0., 1., .30), 'heel': (-1., 0., .15), 'low': (.8, -.6, -.05)}


def board_mesh(name, s):
    """Deck (grid over the outline, concave and kicks, 1.2 cm thick), trucks and wheels, in stance-frame cm."""
    B = W.Board
    verts, faces, mats = [], [], []

    def add(vs, fs, m):
        o = len(verts); verts.extend(vs); faces.extend([tuple(o + i for i in f) for f in fs]); mats.extend([m] * len(fs))
    na, nt = 81, 21
    A = np.linspace(-B.LENGTH / 2, B.LENGTH / 2, na)
    top, bot = [], []
    for a in A:
        e = B.edge(a); T = np.linspace(-e, e, nt) if e > 1e-3 else np.zeros(nt)
        for t in T:
            z = float(B.top(a, t)); top.append((t, a, z)); bot.append((t, a, z - B.THICK))
    grid = [(i * nt + j, i * nt + j + 1, (i + 1) * nt + j + 1, (i + 1) * nt + j) for i in range(na - 1) for j in range(nt - 1)]
    add(top, grid, 0)
    add(bot, [tuple(reversed(f)) for f in grid], 1)
    o_top, o_bot = 0, len(top)
    ring = [i * nt for i in range(na)] + [(na - 1) * nt + j for j in range(1, nt)] + [i * nt + nt - 1 for i in range(na - 2, -1, -1)] + [j for j in range(nt - 2, 0, -1)]
    side = [(ring[k], ring[(k + 1) % len(ring)], o_bot + ring[(k + 1) % len(ring)], o_bot + ring[k]) for k in range(len(ring))]
    faces.extend(side); mats.extend([1] * len(side))
    # trucks: baseplate + hanger boxes, wheels as 16-gon cylinders
    for sgn in (1, -1):
        a0 = sgn * B.KINGPIN
        add(*box((0, a0, B.TOP - B.THICK - .8), (7, 5, 1.6)), 2)
        add(*box((0, a0, B.TOP + B.AXLE_Z + .6), (15, 2.4, 2.2)), 2)
        for ws in (1, -1):
            add(*cylinder((ws * B.WHEEL_Y, a0, B.TOP + B.AXLE_Z), B.WHEEL_R, B.WHEEL_W), 3)
    me = bpy.data.meshes.new(name)
    me.from_pydata(verts, [], faces); me.update()
    for i, p in enumerate(me.polygons): p.material_index = mats[i]
    for label, color in [('grip', (.05, .05, .055, 1)), ('wood', (.55, .38, .22, 1)), ('truck', (.55, .56, .58, 1)), ('wheel', (.85, .80, .66, 1))]:
        m = bpy.data.materials.get('Skate proxy · ' + label) or bpy.data.materials.new('Skate proxy · ' + label)
        m.diffuse_color = color; m.use_nodes = True
        bsdf = m.node_tree.nodes.get('Principled BSDF')
        if bsdf: bsdf.inputs['Base Color'].default_value = color; bsdf.inputs['Roughness'].default_value = .8
        me.materials.append(m)
    return me


def box(c, size):
    x, y, z = c; sx, sy, sz = (v / 2 for v in size)
    v = [(x + i * sx, y + j * sy, z + k * sz) for i in (-1, 1) for j in (-1, 1) for k in (-1, 1)]
    f = [(0, 1, 3, 2), (4, 6, 7, 5), (0, 4, 5, 1), (2, 3, 7, 6), (0, 2, 6, 4), (1, 5, 7, 3)]
    return v, f


def cylinder_along(c, r, length, axis, n=20):
    x, y, z = c; v = []
    for end in (-1, 1):
        for i in range(n):
            ang = 2 * math.pi * i / n; u, w = r * math.cos(ang), r * math.sin(ang)
            v.append((x + end * length / 2, y + u, z + w) if axis == 't' else (x + u, y + end * length / 2, z + w))
    f = [(i, (i + 1) % n, n + (i + 1) % n, n + i) for i in range(n)]
    return v, f


def cylinder(c, r, w, n=16):
    x, y, z = c; v = []
    for side in (-1, 1):
        for i in range(n):
            ang = 2 * math.pi * i / n
            v.append((x + side * w / 2, y + r * math.cos(ang), z + r * math.sin(ang)))
    f = [(i, (i + 1) % n, n + (i + 1) % n, n + i) for i in range(n)] + [tuple(range(n - 1, -1, -1)), tuple(range(n, 2 * n))]
    return v, f


class Review:
    def __init__(self, blend):
        bpy.ops.wm.open_mainfile(filepath=str(blend))
        self.scene = bpy.context.scene; self.arm = next(o for o in self.scene.objects if o.type == 'ARMATURE')
        outfit = bpy.data.objects[W.OUTFIT]
        set_clip(self.arm, bpy.data.actions['Standing · outfit review']); self.scene.frame_set(1)
        dg = bpy.context.evaluated_depsgraph_get(); ev = outfit.evaluated_get(dg)
        self.rig = Rig(self.arm, self.scene, outfit, min((ev.matrix_world @ v.co).z for v in ev.data.vertices))
        self.skater = W.Skater(self.rig, outfit, self.arm)
        self.boards = {}
        for o in self.scene.objects:
            if o.name.startswith('Review floor') or o.name.startswith('Bokken'): o.hide_render = True
        s = self.scene
        engines = [e.identifier for e in bpy.types.RenderSettings.bl_rna.properties['engine'].enum_items]
        s.render.engine = 'BLENDER_EEVEE_NEXT' if 'BLENDER_EEVEE_NEXT' in engines else 'BLENDER_EEVEE'
        s.eevee.taa_render_samples = 8; s.view_settings.view_transform = 'Standard'
        s.render.image_settings.file_format = 'PNG'; s.render.resolution_percentage = 100
        floor_z = (self.arm.matrix_world @ self.skater.origin).z
        bpy.ops.mesh.primitive_plane_add(size=40, location=(0, 0, floor_z - .0005)); fl = bpy.context.object; fl.name = 'Skate review floor'
        m = bpy.data.materials.new('Skate review floor'); m.diffuse_color = (.42, .42, .43, 1); m.use_nodes = True
        m.node_tree.nodes['Principled BSDF'].inputs['Base Color'].default_value = (.42, .42, .43, 1); fl.data.materials.append(m)
        cam = s.camera; cam.data.type = 'ORTHO'; cam.data.ortho_scale = 1.3; cam.data.clip_start = .01; cam.data.clip_end = 50
        self.cam = cam
        self.world = s.world
        if self.world and self.world.use_nodes:
            bg = self.world.node_tree.nodes.get('Background')
            if bg: bg.inputs['Color'].default_value = (.62, .64, .67, 1); bg.inputs['Strength'].default_value = .8

    def rail(self, st, kind):
        """A round rail proxy: along the board under the trucks (grinds) or across it under the deck (slides)."""
        name = f'Skate rail · {kind} · {st.name}'
        ob = bpy.data.objects.get(name)
        if ob is None:
            B = W.Board
            if kind == 'grind':
                v, f = cylinder_along((0, 0, B.TOP + B.AXLE_Z - 3.9), 2.5, 150., 'a')
            else:
                v, f = cylinder_along((0, 0, B.TOP - B.THICK - 2.5), 2.5, 150., 't')
            me = bpy.data.meshes.new(name); me.from_pydata(v, [], f); me.update()
            m = bpy.data.materials.get('Skate proxy · truck'); me.materials.append(m)
            ob = bpy.data.objects.new(name, me); self.scene.collection.objects.link(ob); ob.parent = self.arm
            ob.matrix_parent_inverse = Matrix.Identity(4); ob.matrix_basis = self.stance_to_arm(st)
        return ob

    def board(self, st):
        if st.name not in self.boards:
            ob = bpy.data.objects.new('Skate proxy · ' + st.name, board_mesh('Skate proxy · ' + st.name, st.s))
            self.scene.collection.objects.link(ob); ob.parent = self.arm
            self.boards[st.name] = ob
        for k, o in self.boards.items(): o.hide_render = k != st.name
        return self.boards[st.name]

    def stance_to_arm(self, st):
        return Matrix.Translation(self.skater.origin) @ Matrix.Diagonal((1 / W.UNIT, st.s / W.UNIT, 1 / W.UNIT, 1))

    def pose_frame(self, clip, st, action, f):
        """Evaluate the clip at frame f; if the board moves, move the contact feet with it (game IK preview)."""
        t = (f - 1) / W.FPS
        set_clip(self.arm, action); self.scene.frame_set(f)
        pb = self.arm.pose.bones
        bm = clip.board(t)
        S2A = self.stance_to_arm(st)
        Bm = W.board_matrix(**bm)
        ob = self.board(st); ob.matrix_parent_inverse = Matrix.Identity(4); ob.matrix_basis = S2A @ Bm
        moved = any(abs(bm[k]) > 1e-3 for k in ('pitch', 'roll', 'lift'))
        if not moved: return
        P = clip.params(t)
        M = {n: pb[bn(n)].matrix.copy() for n in BODY}
        props = {side: {p: float(pb[bn(side + 'Hand')][p]) for p in HAND_PROPS} for side in ('Left', 'Right')}
        self.arm.animation_data.action = None
        rig = self.rig; rig.M = dict(M)
        T = S2A @ Bm @ S2A.inverted()
        sk = self.skater
        for role in 'FB':
            side = st.side[role]
            pts = sk.shoe[side].points(M)
            gap = float((pts[:, 2] - sk.surface(pts, st, None)).min()) * W.UNIT
            if gap > .6 or P[role + 'g'] > .5: continue
            foot = T @ M[side + 'Foot']
            knee = M[side + 'Leg'].translation; hip = M[side + 'UpLeg'].translation; ank = M[side + 'Foot'].translation
            pole = (knee - (hip + ank) / 2).normalized()
            for n in ('Leg', 'Foot', 'ToeBase'): rig.M.pop(side + n, None)
            rig.two_bone(side + 'UpLeg', side + 'Leg', foot.translation, pole, extension=.999)
            rig.set_rot(side + 'Foot', foot.to_quaternion())
            rig.M[side + 'ToeBase'] = T @ M[side + 'ToeBase']
            rig.M[side + 'ToeBase'].translation = rig.inherited(side + 'ToeBase').translation
        rig.apply()
        for side, d in props.items():
            for p, v in d.items(): pb[bn(side + 'Hand')][p] = v
        bpy.context.view_layer.update()

    def aim(self, view, st, target=None):
        d = Vector({**VIEWS, **EXTRA_VIEWS}[view]); d = Vector((d.x, st.s * d.y, d.z)).normalized()
        target = self.arm.matrix_world @ (target if target is not None else self.skater.origin + Vector((0, 0, .40)))
        self.cam.location = target + d * 4
        self.cam.rotation_euler = (-d).to_track_quat('-Z', 'Y').to_euler()

    def render_clip(self, role_name, columns, size, work):
        goofy = role_name.endswith('Goofy'); role = role_name[:-5] if goofy else role_name
        clip = W.CLIPS[role]; st = W.Stance(goofy)
        action = bpy.data.actions[role_name + W.SUFFIX]
        n = clip.frames
        frames = sorted({int(round(1 + i * (n - 1) / (columns - 1))) for i in range(columns)}) if columns > 1 else [1]
        self.scene.render.resolution_x = self.scene.render.resolution_y = size
        for o in self.scene.objects:
            if o.name.startswith('Skate rail'): o.hide_render = True
        if role.startswith('SkateGrind'): self.rail(st, 'grind').hide_render = False
        if role == 'SkateSlide': self.rail(st, 'slide').hide_render = False
        tiles = []
        for f in frames:
            self.pose_frame(clip, st, action, f)
            row = []
            for view in VIEWS:
                self.aim(view, st)
                path = work / f'{role_name}-{view.replace(" ", "")}-{f:03d}.png'
                self.scene.render.filepath = str(path); bpy.ops.render.render(write_still=True)
                row.append(str(path))
            tiles.append({'frame': f, 't': round((f - 1) / W.FPS, 3), 'views': row})
        self.arm.animation_data.action = None
        return tiles


def closeups(a):
    """Zoomed stills: --closeup Clip:frame:view[:scale], ... centred on the board."""
    blend = ROOT / a.blend; out = ROOT / a.out; out.mkdir(parents=True, exist_ok=True)
    r = Review(blend); r.scene.render.resolution_x = r.scene.render.resolution_y = a.size
    for item in a.closeup.split(','):
        parts = item.split(':'); name, f, view = parts[0], int(parts[1]), parts[2]
        scale = float(parts[3]) if len(parts) > 3 else .7
        goofy = name.endswith('Goofy'); role = name[:-5] if goofy else name
        clip = W.CLIPS[role]; st = W.Stance(goofy)
        r.pose_frame(clip, st, bpy.data.actions[name + W.SUFFIX], f)
        r.cam.data.ortho_scale = scale
        r.aim(view, st, r.skater.origin + Vector((0, 0, .17)))
        r.scene.render.filepath = str(out / f'{name}-f{f:03d}-{view}.png'); bpy.ops.render.render(write_still=True)
        print('CLOSEUP', r.scene.render.filepath, flush=True)


def main(a):
    if a.closeup: return closeups(a)
    blend = ROOT / a.blend
    out = ROOT / a.out; out.mkdir(parents=True, exist_ok=True)
    work = out / '.frames'; work.mkdir(exist_ok=True)
    r = Review(blend)
    names = a.clips.split(',') if a.clips else [x.name[:-len(W.SUFFIX)] for x in bpy.data.actions if x.name.endswith(W.SUFFIX)]
    jobs = []
    for name in names:
        tiles = r.render_clip(name, a.columns, a.size, work)
        jobs.append({'name': name, 'tiles': tiles, 'views': list(VIEWS), 'out': str(out / f'{name}.jpg')})
        print('RENDERED', name, flush=True)
    spec = work / 'sheets.json'; spec.write_text(json.dumps(jobs))
    subprocess.run([str(VENV), str(Path(__file__)), 'sheet', str(spec)], check=True)


def sheets(spec):
    from PIL import Image, ImageDraw, ImageFont
    jobs = json.loads(Path(spec).read_text())
    try: font = ImageFont.truetype('/System/Library/Fonts/Helvetica.ttc', 18); big = ImageFont.truetype('/System/Library/Fonts/Helvetica.ttc', 24)
    except Exception: font = big = ImageFont.load_default()
    for job in jobs:
        tiles = job['tiles']; first = Image.open(tiles[0]['views'][0]); w, h = first.size
        pad, head, left = 4, 34, 90
        sheet = Image.new('RGB', (left + len(tiles) * (w + pad), head + 22 + len(job['views']) * (h + pad)), (38, 38, 40))
        d = ImageDraw.Draw(sheet)
        d.text((8, 6), job['name'], fill=(240, 240, 240), font=big)
        for i, tile in enumerate(tiles):
            x = left + i * (w + pad)
            d.text((x + 4, head), f"{tile['t']:.3f} s  (f{tile['frame']})", fill=(220, 220, 220), font=font)
            for j, path in enumerate(tile['views']):
                sheet.paste(Image.open(path).convert('RGB'), (x, head + 22 + j * (h + pad)))
        for j, view in enumerate(job['views']):
            d.text((6, head + 22 + j * (h + pad) + h // 2 - 10), view, fill=(220, 220, 220), font=font)
        sheet.save(job['out'], quality=88)
        print('SHEET', job['out'])


if __name__ == '__main__':
    if len(sys.argv) > 2 and sys.argv[1] == 'sheet':
        sheets(sys.argv[2])
    else:
        argv = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
        ap = argparse.ArgumentParser()
        ap.add_argument('--blend', default='output/imagegen/yorimichi-yellow-boy-2026-09-12/game-r17/WarmOriginal-Game-r17.blend')
        ap.add_argument('--clips'); ap.add_argument('--columns', type=int, default=8); ap.add_argument('--size', type=int, default=300)
        ap.add_argument('--out', default='output/imagegen/yorimichi-yellow-boy-2026-09-12/skate-r01/review')
        ap.add_argument('--closeup', help='Clip:frame:view[:ortho scale],... zoomed stills instead of sheets')
        main(ap.parse_args(argv))
