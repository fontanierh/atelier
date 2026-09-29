"""Clipping check of an assembled body swap: poses the character through the library clips and measures, per frame,
how much of the outfit passes through itself (a coat skirt through the trousers, a hem through a thigh) and how much
of the kept skin (head, hands and forearms, and whatever body the outfit leaves bare) passes through the outfit.

    BODY_SWAP_DIR=... BODY_SWAP_STEM=... blender -b --python-exit-code 1 --python games/yorimichi/assets/characters/tools/cairo_body_swap_check.py

A crossing counts when it goes deeper than 2 mm. Only the outer cloth surface is tested (the 2 mm solidify shell doubles every vertex; the first half is the outer
surface). Intersections already present in the bind pose (pockets, folds Tripo modelled as touching) are subtracted,
so the numbers are what the rig adds. Area is the area of the triangles involved, in cm² at the character's 1 m scale.
Each clip's worst frame also says where: skin by kept body region, cloth by where the triangle sits on the body in
the bind pose (above the waist, the hips down to the crotch, below the crotch).
Writes <swap>/qa/check.json and prints one line per clip.
"""
import sys as _sys; from pathlib import Path as _Path; _sys.path.insert(0, str(_Path(__file__).resolve().parents[3] / 'world')); import yori  # noqa: E402
import sys as _sys; from pathlib import Path as _Path; _sys.path.insert(0, str(_Path(__file__).resolve().parent))  # Blender's --python does not add the script's folder
from _archive import ROOT, TOOLS  # noqa: E402  (ROOT: the prototype archive holding the revision history)
import json, os
import bpy
import numpy as np
from mathutils.bvhtree import BVHTree
from cairo_outfit_correctives import set_clip

SWAP_DIR = os.environ.get('BODY_SWAP_DIR', 'body-swap-r01')
SWAP_STEM = os.environ.get('BODY_SWAP_STEM', 'WarmOriginal-BodySwap-r01')
SWAP = ROOT / 'output/imagegen/yorimichi-yellow-boy-2026-09-12' / SWAP_DIR
CLIPS = ['Walk', 'Sprint · dressed', 'CrouchIdle', 'CrouchWalk', 'SitDown', 'SitIdle', 'Roll', 'Climb', 'Wave',
         'DoubleJump', 'DashGround', 'HardLand', 'Glide', 'Interact']
FRAMES = 8
DEPTH = .002   # 2 mm at the character's 1 m scale: shallower crossings are hidden by the shading
bpy.ops.wm.open_mainfile(filepath=str(SWAP / f'assembled/{SWAP_STEM}.blend'))
s = bpy.context.scene
arm = next(o for o in s.objects if o.type == 'ARMATURE')
outfit = next(o for o in s.objects if o.get('body_region') == 'outfit_body')
kept = [o for o in s.objects if o.type == 'MESH' and o.get('body_region') and o is not outfit and not o.hide_render]   # every visible piece of Cairo's own body


def world_tris(obj, outer_only=False):
    deps = bpy.context.evaluated_depsgraph_get()
    ev = obj.evaluated_get(deps); me = ev.to_mesh()
    co = np.empty(len(me.vertices) * 3); me.vertices.foreach_get('co', co)
    M = np.array(obj.matrix_world); co = co.reshape(-1, 3) @ M[:3, :3].T + M[:3, 3]
    me.calc_loop_triangles()
    tri = np.empty(len(me.loop_triangles) * 3, int); me.loop_triangles.foreach_get('vertices', tri); tri = tri.reshape(-1, 3)
    if outer_only:
        tri = tri[(tri < len(me.vertices) // 2).all(axis=1)]
    ev.to_mesh_clear()
    return co, tri


def areas(co, tri):
    a, b, c = co[tri[:, 0]], co[tri[:, 1]], co[tri[:, 2]]
    return np.linalg.norm(np.cross(b - a, c - a), axis=1) / 2 * 1e4   # cm²


def depth(ca, ta, cb, tb, pairs):
    """How far each crossing pair passes through: for crossing triangles each has corners on both sides of the other's
    plane; the lesser side is how far it sticks through. Touching layers that graze each other stay under a millimetre."""
    if not len(pairs):
        return np.zeros(0)
    A = ca[ta[pairs[:, 0]]]; B = cb[tb[pairs[:, 1]]]
    def through(X, Y):
        n = np.cross(Y[:, 1] - Y[:, 0], Y[:, 2] - Y[:, 0]); n /= np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-12)
        sd = np.einsum('kij,kj->ki', X - Y[:, :1], n)
        return np.minimum(sd.max(axis=1), -sd.min(axis=1)).clip(0)
    return np.minimum(through(A, B), through(B, A))


def measure():
    """Triangles (outfit, kept skin) that take part in a crossing deeper than DEPTH."""
    global KOWNER
    oc, ot = world_tris(outfit, outer_only=True)
    otree = BVHTree.FromPolygons(oc.tolist(), ot.tolist(), all_triangles=True)
    sp = np.array([(i, j) for i, j in otree.overlap(otree) if i < j and not set(ot[i]) & set(ot[j])], int).reshape(-1, 2)
    sp = sp[depth(oc, ot, oc, ot, sp) > DEPTH]
    kc, kt, kown = [], [], []; off = 0
    for k, o in enumerate(kept):
        c, t = world_tris(o); kc.append(c); kt.append(t + off); kown.append(np.full(len(t), k)); off += len(c)
    kc = np.concatenate(kc); kt = np.concatenate(kt); KOWNER = np.concatenate(kown)
    ktree = BVHTree.FromPolygons(kc.tolist(), kt.tolist(), all_triangles=True)
    kp = np.array(ktree.overlap(otree), int).reshape(-1, 2)
    kp = kp[depth(kc, kt, oc, ot, kp) > DEPTH]
    return set(sp.ravel().tolist()), set(kp[:, 0].tolist()), areas(oc, ot), areas(kc, kt)


KOWNER = np.zeros(0, int)   # kept object index per kept triangle, set by measure()


def where(new_self, new_kept, oa, ka):
    """cm² per kept region and per bind-pose band of the outfit."""
    skin = {}
    for i in new_kept:
        r = kept[KOWNER[i]].get('body_region'); skin[r] = skin.get(r, 0) + float(ka[i])
    cloth = {}
    for i in new_self:
        b = BAND[i]; cloth[b] = cloth.get(b, 0) + float(oa[i])
    return {'skin': {k: round(v, 1) for k, v in sorted(skin.items(), key=lambda kv: -kv[1])},
            'cloth': {k: round(v, 1) for k, v in sorted(cloth.items(), key=lambda kv: -kv[1])}}


arm.animation_data.action = None; arm.data.pose_position = 'REST'; bpy.context.view_layer.update()
rest_self, rest_kept, _, _ = measure()
_assembly = SWAP / 'assembled/assembly.json'
CROTCH = json.loads(_assembly.read_text()).get('components', {}).get('crotch_z', -.12) if _assembly.exists() else -.12
_rc, _rt = world_tris(outfit, outer_only=True); _z = _rc[_rt].mean(axis=1)[:, 2]
BAND = np.where(_z > 0, 'above waist', np.where(_z > CROTCH, 'hips to crotch', 'below crotch'))
arm.data.pose_position = 'POSE'
report = {'swap': SWAP_DIR, 'depth_m': DEPTH, 'rest_cloth_tris': len(rest_self), 'rest_skin_tris': len(rest_kept), 'clips': {}}
actions = {a.name.split(' · ')[0] if a.name.endswith('· library') else a.name: a for a in bpy.data.actions}
for name in CLIPS:
    act = actions.get(name)
    if act is None:
        continue
    set_clip(arm, act)
    lo, hi = act.frame_range
    rows = []
    for f in np.linspace(lo, hi, FRAMES):
        s.frame_set(int(round(f))); bpy.context.view_layer.update()
        sp, kp, oa, ka = measure()
        new_self = list(sp - rest_self); new_kept = list(kp - rest_kept)   # triangles not already crossing at rest
        rows.append({'frame': int(round(f)),
                     'cloth_through_cloth_cm2': round(float(oa[new_self].sum()), 2),
                     'skin_through_cloth_cm2': round(float(ka[new_kept].sum()), 2),
                     'where': where(new_self, new_kept, oa, ka)})
    worst = max(rows, key=lambda r: r['cloth_through_cloth_cm2'] + r['skin_through_cloth_cm2'])
    report['clips'][name] = {'frames': rows, 'worst_frame': worst['frame'], 'worst_where': worst['where'],
                             'cloth_max_cm2': max(r['cloth_through_cloth_cm2'] for r in rows),
                             'cloth_mean_cm2': round(float(np.mean([r['cloth_through_cloth_cm2'] for r in rows])), 2),
                             'skin_max_cm2': max(r['skin_through_cloth_cm2'] for r in rows),
                             'skin_mean_cm2': round(float(np.mean([r['skin_through_cloth_cm2'] for r in rows])), 2)}
    c = report['clips'][name]
    print(f'CHECK {name:18s} cloth max {c["cloth_max_cm2"]:7.1f} mean {c["cloth_mean_cm2"]:6.1f} | skin max {c["skin_max_cm2"]:6.1f} mean {c["skin_mean_cm2"]:5.1f} cm²')
clips = report['clips'].values()
report['summary'] = {'cloth_mean_cm2': round(float(np.mean([c['cloth_mean_cm2'] for c in clips])), 2),
                     'cloth_worst_cm2': max(c['cloth_max_cm2'] for c in clips),
                     'skin_mean_cm2': round(float(np.mean([c['skin_mean_cm2'] for c in clips])), 2),
                     'skin_worst_cm2': max(c['skin_max_cm2'] for c in clips)}
total = {'skin': {}, 'cloth': {}}   # summed over every frame of every clip: where the crossings mostly are
for c in clips:
    for r in c['frames']:
        for kind in total:
            for k, v in r['where'][kind].items():
                total[kind][k] = total[kind].get(k, 0) + v
report['summary_where'] = {kind: {k: round(v / sum(len(c['frames']) for c in clips), 1) for k, v in sorted(d.items(), key=lambda kv: -kv[1])}
                           for kind, d in total.items()}   # mean cm² per frame
(SWAP / 'qa').mkdir(exist_ok=True)
(SWAP / 'qa/check.json').write_text(json.dumps(report, indent=1) + '\n')
print('CHECK_SUMMARY', json.dumps(report['summary']))
print('CHECK_WHERE', json.dumps(report['summary_where']))
