"""Add three-bone fingers to the fox hunter's Tripo body rig, fitted automatically from the mesh.

blender -b --python-exit-code 1 --python games/yorimichi/assets/characters/tools/add_fox_fingers.py -- [--no-reel]

Input: tripo-rig-r01/blender/FoxHunter-Rig-r01.blend (Tripo's 23 body bones plus the six body tests).
Output: tripo-rig-r02/ with the same body bones and weights untouched, 30 new finger bones (3 per digit),
hand controls (per-finger curl, thumb opposition, finger spread) driven onto the joints, a seventh test
segment (frames 360-419: fist, then spread), hand close-up stills, the reel, and the web preview.

Digit detection: hand vertices (Tripo hand weight > 0.5) are sliced by distance along the hand bone; the
smallest slice distance at which the sliced sub-mesh splits into exactly five connected pieces is the
finger base. Each piece's centreline (four centroids along its own axis) gives the joint centres. The
thumb is the digit whose base sits highest (palms face the camera in the T-pose, thumbs point up).
"""
import sys as _sys; from pathlib import Path as _Path; _sys.path.insert(0, str(_Path(__file__).resolve().parents[3] / 'world')); import yori  # noqa: E402
import sys as _sys; from pathlib import Path as _Path; _sys.path.insert(0, str(_Path(__file__).resolve().parent))  # Blender's --python does not add the script's folder
from _archive import ROOT, TOOLS  # noqa: E402  (ROOT: the prototype archive holding the revision history)
import argparse, base64, json, math, sys
from pathlib import Path
import bpy
from mathutils import Matrix, Vector, Quaternion

ap = argparse.ArgumentParser()
ap.add_argument('--no-reel', action='store_true')
ap.add_argument('--texture-size', type=int, default=2048)
a = ap.parse_args(sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else [])
ROOT = ROOT / 'output/imagegen/yorimichi-fox-hunter-2026-09-13'
SRC = ROOT / 'tripo-rig-r01/blender/FoxHunter-Rig-r01.blend'
OUT = ROOT / 'tripo-rig-r02'; REV = OUT / 'blender'; REV.mkdir(parents=True, exist_ok=True)
NAME = 'FoxHunter-Rig-r02'
FPS, SEG = 24, 60
bpy.ops.wm.open_mainfile(filepath=str(SRC))
scene = bpy.context.scene; scene.frame_set(0)
arm = next(o for o in scene.objects if o.type == 'ARMATURE')
body = next(o for o in scene.objects if o.type == 'MESH' and o.vertex_groups)
before_positions = [v.co.copy() for v in body.data.vertices]
before_weights = [[(g.group, g.weight) for g in v.groups] for v in body.data.vertices]
before_bones = {b.name: b.matrix_local.copy() for b in arm.data.bones}
neighbors = [set() for _ in body.data.vertices]
for e in body.data.edges:
    x, y = e.vertices; neighbors[x].add(y); neighbors[y].add(x)
# The GLB mesh is split at every hard edge and UV seam, so connectivity must be taken over welded positions.
key_of = [tuple(round(c, 5) for c in v.co) for v in body.data.vertices]
verts_of = {}
for i, k in enumerate(key_of): verts_of.setdefault(k, []).append(i)
wadj = {k: set() for k in verts_of}
for e in body.data.edges:
    ka, kb = key_of[e.vertices[0]], key_of[e.vertices[1]]
    if ka != kb: wadj[ka].add(kb); wadj[kb].add(ka)

FINGERS = ['Thumb', 'Index', 'Middle', 'Ring', 'Pinky']

def components(keys):
    seen, comps = set(), []
    for s in keys:
        if s in seen: continue
        stack, comp = [s], []
        seen.add(s)
        while stack:
            v = stack.pop(); comp.append(v)
            for n in wadj[v]:
                if n in keys and n not in seen:
                    seen.add(n); stack.append(n)
        comps.append(comp)
    return comps

def centroid_keys(keys):
    return sum((Vector(k) for k in keys), Vector()) / len(keys)

def centreline(keys, base_hint_axis):
    """Four joint centres from base to tip along the digit's own axis."""
    pts_all = [Vector(k) for k in keys]
    proj = {k: Vector(k).dot(base_hint_axis) for k in keys}
    lo = sorted(keys, key=lambda k: proj[k]); n = max(4, len(keys) // 6)
    base_c = centroid_keys(lo[:n]); tip_c = centroid_keys(lo[-n:])
    axis = (tip_c - base_c).normalized()
    t = {k: (Vector(k) - base_c).dot(axis) for k in keys}
    tmin, tmax = min(t.values()), max(t.values())
    pts = []
    for q in range(4):
        a0, a1 = tmin + (tmax - tmin) * q / 4, tmin + (tmax - tmin) * (q + 1) / 4
        ids = [k for k in keys if a0 <= t[k] <= a1] or keys
        c = centroid_keys(ids); on = base_c + axis * ((c - base_c).dot(axis))
        pts.append(on + (c - on) * 0.5)
    pts[0] = pts[0] - axis * (tmax - tmin) * 0.12
    pts[3] = base_c + axis * (tmax + (tmax - tmin) * 0.02)
    return pts, tmax - tmin

def detect(side):
    hb = arm.data.bones[f'mixamorig:{side}Hand']
    gi = body.vertex_groups[hb.name].index
    hand_keys_ = {key_of[v.index] for v in body.data.vertices if any(g.group == gi and g.weight > 0.5 for g in v.groups)}
    d = (hb.tail_local - hb.head_local).normalized()
    up = Vector((0, 0, 1))
    s = {k: (Vector(k) - hb.head_local).dot(d) for k in hand_keys_}
    smax = max(s.values()); zmax = max(k[2] for k in hand_keys_)
    z_split = zmax - 0.35 * (zmax - hb.head_local.z)  # thumb material sits in the top third above the hand bone; fingers below
    # four fingers: lowest cut along the hand axis at which exactly four finger-height pieces remain
    finger_cut, finger_pieces = None, None
    for kk in range(59, 0, -1):
        cut = smax * kk / 60
        pieces = [c for c in components({k for k in hand_keys_ if s[k] > cut}) if len(c) >= 4]
        fingers = [c for c in pieces if centroid_keys(c).z < z_split]
        if len(fingers) == 4:
            finger_cut, finger_pieces = cut, fingers
        elif finger_pieces is not None and len(fingers) < 4:
            break
    if finger_pieces is None:
        raise RuntimeError(f'{side}: could not isolate four fingers')
    finger_keys = {k for c in finger_pieces for k in c}
    # thumb: lowest cut along up at which the topmost piece is still one narrow piece with no finger vertices
    thumb_piece, thumb_cut = None, None
    for kk in range(59, 0, -1):
        zc = hb.head_local.z + (zmax - hb.head_local.z) * kk / 60
        pieces = [c for c in components({k for k in hand_keys_ if k[2] > zc and k not in finger_keys}) if len(c) >= 4]
        if not pieces: continue
        top = max(pieces, key=len)
        extent = max(s[k] for k in top) - min(s[k] for k in top)
        if extent > 0.45 * smax or len(pieces) > 2:
            break
        thumb_piece, thumb_cut = top, zc
    if thumb_piece is None:
        raise RuntimeError(f'{side}: could not isolate the thumb')
    digits = {}
    fl = [(centroid_keys(c).z, c) for c in finger_pieces]
    fl.sort(key=lambda zc: -zc[0])  # index highest, pinky lowest (palms face the camera, thumb up)
    for name, (_, c) in zip(FINGERS[1:], fl):
        pts, length = centreline(c, d)
        digits[name] = dict(keys=c, points=pts, length=length)
    tp, tl = centreline(thumb_piece, (up * 0.7 + d * 0.5).normalized())
    digits['Thumb'] = dict(keys=thumb_piece, points=tp, length=tl)
    for dg in digits.values():
        dg['ids'] = [i for k in dg['keys'] for i in verts_of[k]]
    return hb, digits, dict(finger_cut=round(finger_cut, 4), thumb_cut=round(thumb_cut, 4))

detected = {side: detect(side) for side in ('Left', 'Right')}

# --- bones --------------------------------------------------------------------------------------------------
bpy.ops.object.select_all(action='DESELECT'); arm.select_set(True); bpy.context.view_layer.objects.active = arm
bpy.ops.object.mode_set(mode='EDIT')
chains = {}
for side, (hb, digits, _) in detected.items():
    for finger, dg in digits.items():
        pts, names = dg['points'], []
        for k in range(3):
            n = f'mixamorig:{side}Hand{finger}{k + 1}'
            eb = arm.data.edit_bones.new(n)
            eb.head, eb.tail = pts[k], pts[k + 1]
            eb.parent = arm.data.edit_bones[names[-1] if names else hb.name]
            eb.use_connect = k > 0
            eb.align_roll(Vector((1, 0, 0)))  # local Z toward the palm normal (+X): bending about local X curls into the palm
            names.append(n)
        chains[(side, finger)] = dict(points=pts, bones=names, ids=dg['ids'], length=dg['length'])
bpy.ops.object.mode_set(mode='OBJECT')
for n, m in before_bones.items():
    assert max(abs(arm.data.bones[n].matrix_local[i][j] - m[i][j]) for i in range(4) for j in range(4)) < 1e-6

# --- weights (only vertices of detected digits change; blend into the palm over the proximal joint) -----------
def smooth(v):
    t = max(0.0, min(1.0, v)); return t * t * (3 - 2 * t)

groups = {n: body.vertex_groups.new(name=n) for c in chains.values() for n in c['bones']}
changed = set(); per_chain = {}
for (side, finger), c in chains.items():
    pts, hand_name = c['points'], f'mixamorig:{side}Hand'
    lengths = [(b - a).length for a, b in zip(pts, pts[1:])]
    total = sum(lengths); band = 0.08 * total
    count = 0
    for i in c['ids']:
        p = body.data.vertices[i].co
        # arc length along the chain of the nearest point
        best = None; off = 0.0
        for k, (p0, p1, L) in enumerate(zip(pts, pts[1:], lengths)):
            t = (p - p0).dot(p1 - p0) / (L * L)
            near = p0 + (p1 - p0) * max(0.0, min(1.0, t))
            dist = (p - near).length
            arc = off + L * (t if k == 0 and t < 0 else max(0.0, min(1.0, t)))
            if best is None or dist < best[0]: best = (dist, arc)
            off += L
        arc = best[1]
        amount = smooth((arc + band) / (2 * band))
        one = smooth((arc - lengths[0] + 0.5 * band) / band)
        two = smooth((arc - lengths[0] - lengths[1] + 0.5 * band) / band)
        w = {c['bones'][0]: amount * (1 - one), c['bones'][1]: amount * one * (1 - two), c['bones'][2]: amount * one * two, hand_name: 1 - amount}
        for g in [g.group for g in body.data.vertices[i].groups]: body.vertex_groups[g].remove([i])
        for n, ww in w.items():
            if ww > 1e-7: body.vertex_groups[n].add([i], ww, 'REPLACE')
        changed.add(i); count += 1
    per_chain[side + finger] = count
for _ in range(2):  # relax over mesh neighbours so the finger base does not crease
    cur = [{g.group: g.weight for g in v.groups} for v in body.data.vertices]; upd = {}
    for i in changed:
        adj = neighbors[i]
        if not adj: continue
        comb = {g: w * 0.7 for g, w in cur[i].items()}
        for o in adj:
            for g, w in cur[o].items(): comb[g] = comb.get(g, 0) + 0.3 * w / len(adj)
        top = sorted(comb.items(), key=lambda kv: -kv[1])[:4]; tot = sum(w for _, w in top)
        upd[i] = [(g, w / tot) for g, w in top if w / tot > 1e-7]
    for i, ws in upd.items():
        for g in [g.group for g in body.data.vertices[i].groups]: body.vertex_groups[g].remove([i])
        for g, w in ws: body.vertex_groups[g].add([i], w, 'REPLACE')
assert all([(g.group, g.weight) for g in v.groups] == before_weights[v.index] for v in body.data.vertices if v.index not in changed)

# --- hand controls and drivers -------------------------------------------------------------------------------
props = [f.lower() + '_curl' for f in FINGERS] + ['thumb_opposition', 'finger_spread']
for side, sign in (('Left', 1), ('Right', -1)):
    hand = arm.pose.bones[f'mixamorig:{side}Hand']
    for p in props:
        hand[p] = 0.0
        hand.id_properties_ui(p).update(min=-1.0 if p == 'finger_spread' else 0.0, max=1.0, description=p.replace('_', ' ').capitalize())
    for finger in FINGERS:
        for k, n in enumerate(chains[(side, finger)]['bones']):
            pb = arm.pose.bones[n]; pb.rotation_mode = 'XYZ'
            fc = pb.driver_add('rotation_euler', 0); d = fc.driver; d.type = 'SCRIPTED'
            var = d.variables.new(); var.name = 'curl'; var.targets[0].id = arm
            var.targets[0].data_path = f'pose.bones["{hand.name}"]["{finger.lower()}_curl"]'
            angles = [30, 45, 55] if finger == 'Thumb' else [70, 85, 60]
            # both hands are rolled toward the palm normal (+X); measured: a positive angle about local X moves the knuckle toward +X on both sides
            d.expression = f'max(0,min(1,curl))*{math.radians(angles[k]):.5f}'
            if k == 0:
                fc = pb.driver_add('rotation_euler', 2); d = fc.driver; d.type = 'SCRIPTED'
                var = d.variables.new(); var.targets[0].id = arm
                if finger == 'Thumb':
                    var.name = 'opp'; var.targets[0].data_path = f'pose.bones["{hand.name}"]["thumb_opposition"]'
                    d.expression = f'{-sign}*max(0,min(1,opp))*1.1'  # swing the thumb across the palm toward the fingers
                else:
                    var.name = 'spread'; var.targets[0].data_path = f'pose.bones["{hand.name}"]["finger_spread"]'
                    d.expression = f'{sign}*spread*{ {"Index": .22, "Middle": .07, "Ring": -.07, "Pinky": -.22}[finger] }'

# --- seventh test: fist then spread, body at rest (frames 360-419) --------------------------------------------
hands = [arm.pose.bones[f'mixamorig:{s}Hand'] for s in ('Left', 'Right')]
def hand_keys(frame, values):
    for h in hands:
        for p in props:
            h[p] = values.get(p, 0.0); h.keyframe_insert(data_path=f'["{p}"]', frame=frame)
fist = {f.lower() + '_curl': 1.0 for f in FINGERS}; fist['thumb_curl'] = 0.6; fist['thumb_opposition'] = 0.8; fist['finger_spread'] = -0.3
spread = {'finger_spread': 1.0, 'thumb_opposition': 0.0}
hand_keys(0, {}); hand_keys(359, {}); hand_keys(360, {}); hand_keys(375, fist); hand_keys(390, {}); hand_keys(405, spread); hand_keys(419, {})
for n in before_bones:  # keep the body at rest through the hand segment
    pb = arm.pose.bones[n]
    for f in (360, 419):
        pb.rotation_quaternion = Quaternion(); pb.keyframe_insert('rotation_quaternion', frame=f)
scene.frame_end = 7 * SEG - 1
scene.frame_set(375); bpy.context.view_layer.update()
curl_check = {}
for side in ('Left', 'Right'):
    for finger in FINGERS:
        # first phalanx only: a full fist curls the tip past 180 degrees, so the tip is not a usable direction test
        pb = arm.pose.bones[chains[(side, finger)]['bones'][0]]
        dg = bpy.context.evaluated_depsgraph_get(); ea = arm.evaluated_get(dg); epb = ea.pose.bones[pb.name]
        tip_now = ea.matrix_world @ epb.tail; tip_rest = arm.matrix_world @ pb.bone.tail_local
        curl_check[side + finger] = [round(c, 4) for c in (tip_now - tip_rest)]
bad = [k for k, v in curl_check.items() if v[0] <= 0.003]
assert not bad, f'first knuckles not moving toward the palm (+X) at the fist: {bad} {curl_check}'
scene.frame_set(0); bpy.context.view_layer.update()
ev = body.evaluated_get(bpy.context.evaluated_depsgraph_get())
rest_err = max((ev.data.vertices[i].co - before_positions[i]).length for i in range(len(before_positions)))

# --- renders ------------------------------------------------------------------------------------------------
cam = scene.camera
body_cam = (cam.location.copy(), cam.rotation_euler.copy(), cam.data.lens)
scene.render.resolution_x = scene.render.resolution_y = 900
for side, sign in (('left', 1), ('right', -1)):
    c = chains[(side.capitalize(), 'Middle')]['points']
    target = (c[0] + c[3]) / 2
    cam.data.lens = 85
    cam.location = target + Vector((1.0, -sign * 0.35, 0.35)).normalized() * 0.55
    cam.rotation_euler = (target - cam.location).to_track_quat('-Z', 'Y').to_euler()
    for label, frame in (('open', 360), ('fist', 375), ('spread', 405)):
        scene.frame_set(frame); scene.render.filepath = str(REV / f'hand-{side}-{label}.png'); bpy.ops.render.render(write_still=True)
cam.location, cam.rotation_euler, cam.data.lens = body_cam
scene.frame_set(375); scene.render.filepath = str(REV / 'fingers.png'); bpy.ops.render.render(write_still=True)
if not a.no_reel:
    scene.render.filepath = str(REV / 'deformation-frames') + '/'
    bpy.ops.render.render(animation=True)

# --- exports -------------------------------------------------------------------------------------------------
bpy.ops.object.select_all(action='DESELECT'); arm.select_set(True); body.select_set(True); bpy.context.view_layer.objects.active = arm
bpy.ops.wm.save_as_mainfile(filepath=str(REV / f'{NAME}.blend'))
bpy.ops.export_scene.gltf(filepath=str(REV / f'{NAME}.glb'), export_format='GLB', use_selection=True, export_animations=True,
                          export_skins=True, export_force_sampling=True, export_yup=True)
for im in bpy.data.images:
    if im.size[0] > a.texture_size: im.scale(a.texture_size, a.texture_size)
prev = OUT / 'preview'; prev.mkdir(exist_ok=True); gltf = prev / f'{NAME}.gltf'
bpy.ops.export_scene.gltf(filepath=str(gltf), export_format='GLTF_SEPARATE', use_selection=True, export_image_format='JPEG',
                          export_jpeg_quality=85, export_texture_dir='tex', export_animations=True, export_skins=True,
                          export_force_sampling=True, export_yup=True)
doc = json.loads(gltf.read_text()); b = doc['buffers'][0]; blob = (gltf.parent / b['uri']).read_bytes(); (gltf.parent / b['uri']).unlink()
del b['uri']; b['byteLength'] = len(blob); gltf.write_text(json.dumps(doc))
(prev / f'{NAME}.buffer.js').write_text('window.GLTF_BUFFER_B64="' + base64.b64encode(blob).decode() + '";\n')

report = dict(source=str(SRC.relative_to(ROOT)), body_bones_retained=len(before_bones), added_finger_bones=len(chains) * 3,
              total_bones=len(arm.data.bones), detection={s: v[2] for s, v in detected.items()},
              chains={s + f: dict(bones=c['bones'], joints=[[round(x, 4) for x in p] for p in c['points']], vertices=per_chain[s + f], length=round(c['length'], 4)) for (s, f), c in chains.items()},
              hand_controls=props, reweighted_vertices=len(changed), rest_pose_max_vertex_error=rest_err,
              max_influences=max(len(v.groups) for v in body.data.vertices),
              unweighted_vertices=sum(sum(g.weight for g in v.groups) < 0.999 for v in body.data.vertices),
              tests_frames=7 * SEG, hand_test=dict(start=360, fist=375, spread=405), fist_tip_motion=curl_check, additional_tripo_credits=0, user_approval='pending')
(REV / 'review.json').write_text(json.dumps(report, indent=2) + '\n')
assert report['total_bones'] == 53 and report['max_influences'] <= 4 and report['unweighted_vertices'] == 0 and rest_err < 2e-5, report
print('FINGERS OK', json.dumps({k: v for k, v in report.items() if k != 'chains'}))
print('CHAINS', json.dumps({k: (v['vertices'], v['length']) for k, v in report['chains'].items()}))
