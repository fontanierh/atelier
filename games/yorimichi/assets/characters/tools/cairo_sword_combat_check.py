"""Validate the saved combat clips of game-r13 independently of the build solver.

    blender -b --threads 4 --python-exit-code 1 --python games/yorimichi/assets/characters/tools/cairo_sword_combat_check.py

Per clip, evaluated skinned meshes are sampled at 240 Hz (60 Hz for the static holds/draw) and tested
with BVH overlap: blade and whole sword against the head (skin + hair), blade against the outfit (torso,
legs, shoes) and against the free hand/forearm skin, and both fists against the head. It also reports
the support-hand grip error against the rigid socket, per-frame world rotation steps of the arm chain,
the lowest garment vertex against the floor, loop seams, and that every library action in game-r13 has
exactly the game-r12 curves. Sampled checks are not continuous collision proofs.
"""
import sys as _sys; from pathlib import Path as _Path; _sys.path.insert(0, str(_Path(__file__).resolve().parents[3] / 'world')); import yori  # noqa: E402
import sys as _sys; from pathlib import Path as _Path; _sys.path.insert(0, str(_Path(__file__).resolve().parent))  # Blender's --python does not add the script's folder
from _archive import ROOT, TOOLS  # noqa: E402  (ROOT: the prototype archive holding the revision history)
import hashlib, json, math, sys
from pathlib import Path
import bpy, numpy as np
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree
sys.path.insert(0, str(Path(__file__).parent))
from cairo_outfit_correctives import set_clip
from cairo_sword_combat_build import Builder, P
# ROOT (the archive) comes from _archive
ASSET = ROOT / 'output/imagegen/yorimichi-yellow-boy-2026-09-12'
SRC = ASSET / 'game-r13/WarmOriginal-Game-r13.blend'; PARENT = ASSET / 'game-r12/WarmOriginal-Game-r12.blend'
OUT = ASSET / 'combat-r01'
FLOOR = -.5011
SOCKET = Matrix.Translation((-.0167, .0724, -.068)) @ Matrix(((0, -1, 0), (-1, 0, 0), (0, 0, -1))).to_4x4()
ARM_CHAIN = [P + s + p for s in ['Right', 'Left'] for p in ['Arm', 'ForeArm', 'Hand']]


def signatures(path):
    bpy.ops.wm.open_mainfile(filepath=str(path))
    return {a.name: Builder.signature(a) for a in bpy.data.actions}


def evaluated(obj, dg):
    ev = obj.evaluated_get(dg); m = ev.to_mesh()
    verts = [ev.matrix_world @ v.co for v in m.vertices]; faces = [list(p.vertices) for p in m.polygons]; ev.to_mesh_clear()
    return verts, faces


def main():
    parent = signatures(PARENT)
    current = signatures(SRC)
    library_unchanged = all(current.get(k) == v for k, v in parent.items())
    scene = bpy.context.scene; arm = next(o for o in scene.objects if o.type == 'ARMATURE'); W = arm.matrix_world
    manifest = json.loads((SRC.parent / 'source-manifest.json').read_text()); roles = [r for r in manifest['roles'] if r.get('sword')]
    sword = bpy.data.objects['Bokken-stage1-r01']; head = bpy.data.objects['Body · head']; outfit = bpy.data.objects['Body · outfit (Tripo skate r01)']; skin = bpy.data.objects['Body · hands_forearms']
    sv = [v.co.copy() for v in sword.data.vertices]; sfaces = [list(p.vertices) for p in sword.data.polygons]
    blade_faces = [p for p in sfaces if min(sv[i].z for i in p) > .11]
    hand_groups = {side: [v.index for v in skin.data.vertices if any(skin.vertex_groups[g.group].name == P + side + 'Hand' and g.weight > .5 for g in v.groups)] for side in ['Left', 'Right']}
    report = {'library_actions_unchanged_from_game_r12': library_unchanged, 'floor': FLOOR, 'clips': {}}
    for role in roles:
        action = bpy.data.actions[role['clip']]; set_clip(arm, action); n = role['frames']
        rate = 240 if role['kind'] in ('one-shot', 'reference') and 'Draw' not in role['role'] and 'Sheath' not in role['role'] else 60
        step = 60 / rate; samples = int(round((n - 1) / step)) + 1
        hits = {'blade_head': [], 'sword_head': [], 'blade_outfit': [], 'blade_skin': [], 'fist_head': []}
        grip = [0, 0]; low = [10, 0]; steps = {b: [0, 0] for b in ARM_CHAIN}; previous = {}; head_min = [10, 0]
        first = None
        for i in range(samples):
            f = 1 + i * step; scene.frame_set(int(math.floor(f)), subframe=f % 1); dg = bpy.context.evaluated_depsgraph_get()
            hv, hf = evaluated(head, dg); ov, of = evaluated(outfit, dg); kv, kf = evaluated(skin, dg)
            head_tree = BVHTree.FromPolygons(hv, hf); outfit_tree = BVHTree.FromPolygons(ov, of)
            swv = [sword.matrix_world @ v for v in sv]
            blade = BVHTree.FromPolygons(swv, blade_faces); whole = BVHTree.FromPolygons(swv, sfaces)
            if head_tree.overlap(blade): hits['blade_head'].append(f)
            if head_tree.overlap(whole): hits['sword_head'].append(f)
            if outfit_tree.overlap(blade): hits['blade_outfit'].append(f)
            # free skin (hands/forearms) against the blade only: the grip contact itself is intended
            skin_tree = BVHTree.FromPolygons(kv, kf)
            if skin_tree.overlap(blade): hits['blade_skin'].append(f)
            for side, idx in hand_groups.items():
                if any(head_tree.find_nearest(kv[j])[-1] < .004 for j in idx[::4]): hits['fist_head'].append([f, side]); break
            d = min(head_tree.find_nearest(swv[j])[-1] for j in sorted({k for p in blade_faces for k in p})[::3])
            if d < head_min[0]: head_min = [d, f]
            goal = (sword.matrix_world @ SOCKET.inverted()).translation
            e = (W @ arm.pose.bones[P + 'LeftHand'].head - goal).length
            if e > grip[0]: grip = [e, f]
            z = min(v.z for v in ov)
            if z < low[0]: low = [z, f]
            if abs(f - round(f)) < 1e-6:
                for b in ARM_CHAIN:
                    q = (W @ arm.pose.bones[b].matrix).to_quaternion()
                    if b in previous:
                        deg = math.degrees(q.rotation_difference(previous[b]).angle); deg = min(deg, 360 - deg)
                        if deg > steps[b][0]: steps[b] = [deg, f]
                    previous[b] = q.copy()
                pose = {pb.name: (W @ pb.matrix).copy() for pb in arm.pose.bones}
                if first is None: first = pose
                last = pose
        seam = None
        if role['loop']:
            seam = max((first[k].translation - last[k].translation).length for k in first)
        report['clips'][role['role']] = {'clip': role['clip'], 'frames': n, 'sample_rate_hz': rate, 'samples': samples,
            'overlap_samples': {k: v[:40] for k, v in hits.items()}, 'overlap_counts': {k: len(v) for k, v in hits.items()},
            'blade_to_head_min_m_and_sample': head_min, 'support_grip_max_error_m_and_sample': grip, 'lowest_outfit_vertex_z_and_sample': low,
            'floor_penetration_m': max(0., FLOOR - low[0]), 'max_keyframe_world_rotation_step_degrees': steps, 'loop_seam_max_joint_distance_m': seam}
        c = report['clips'][role['role']]
        print('CHECK', role['role'], 'overlaps', c['overlap_counts'], f"grip {grip[0] * 1000:.1f}mm@{grip[1]}", f"low {low[0]:.4f}", 'seam', seam, flush=True)
    (OUT).mkdir(exist_ok=True)
    (OUT / 'combat-validation.json').write_text(json.dumps(report, indent=1) + '\n')
    print('COMBAT_CHECK library_unchanged', library_unchanged, flush=True)


if __name__ == '__main__': main()
