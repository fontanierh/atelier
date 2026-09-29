"""Grip solver for either hand of the Cairo on a sword prop (extracted from warm_sword_hold.py rounds 1-14).

Hand rest frames (mixamorig): +Y along the fingers, +Z across the hand from index to pinky; the palm normal is +X on the
right hand and -X on the left. All solver logic is written in "palm-positive" coordinates: x is multiplied by
`palm_sign` so both hands read like the right one. Finger bones curl about local +X toward the palm on both hands.
The sword prop is built tip +Z, cutting edge -X, pivot at the grip centre; in the hand frame the tip goes to -Z (index
side) and the edge to +Y (along the fingers).
"""
import sys as _sys; from pathlib import Path as _Path; _sys.path.insert(0, str(_Path(__file__).resolve().parents[3] / 'world')); import yori  # noqa: E402
import sys as _sys; from pathlib import Path as _Path; _sys.path.insert(0, str(_Path(__file__).resolve().parent))  # Blender's --python does not add the script's folder
from _archive import ROOT, TOOLS  # noqa: E402  (ROOT: the prototype archive holding the revision history)
import math
import bpy
from mathutils import Vector, Matrix, Quaternion

FINGERS = ['Index', 'Middle', 'Ring', 'Pinky']
SOCKET_ROT = Matrix(((0, -1, 0), (-1, 0, 0), (0, 0, -1)))     # columns: sword x, y, z in the hand frame (same for both hands)


class HandGrip:
    def __init__(self, arm, hands, side, sword, R, build, skin=.002, palm_sink=.008, palm_gap_max=.002, thumb_space=.03):
        self.arm, self.hands, self.side, self.sword, self.R, self.build = arm, hands, side, sword, R, build
        self.SKIN, self.PALM_SINK, self.PALM_GAP_MAX, self.THUMB_SPACE = skin, palm_sink, palm_gap_max, thumb_space
        self.sign = 1.0 if side == 'Right' else -1.0
        self.HAND = f'mixamorig:{side}Hand'; self.pb = arm.pose.bones[self.HAND]
        self.rest = arm.data.bones[self.HAND].matrix_local
        M = (arm.matrix_world @ self.rest).inverted()
        self.all_pts = [self._pp(M @ (hands.matrix_world @ v.co)) for v in hands.data.vertices]
        thumb_gi = {hands.vertex_groups[f'mixamorig:{side}HandThumb{i}'].index for i in (1, 2, 3)}
        self.is_thumb = [any(g.group in thumb_gi and g.weight > .2 for g in v.groups) for v in hands.data.vertices]
        self.kn = {f: self._pp(M @ (arm.matrix_world @ arm.data.bones[f'mixamorig:{side}Hand{f}1'].head_local)) for f in FINGERS}
        self.knuckle_y = sum(self.kn[f].y for f in FINGERS) / 4; self.axis_z = sum(self.kn[f].z for f in FINGERS) / 4
        edge_pts = [q for q, t in zip(self.all_pts, self.is_thumb) if .06 < q.y < .13 and abs(q.x) < .03 and not t]
        self.index_edge = min(q.z for q in edge_pts)
        self.pinky_edge = max(q.z for q, t in zip(self.all_pts, self.is_thumb) if .02 < q.y < .13 and abs(q.x) < .03 and not t)
        self.PALM_IDX = [i for i, q in enumerate(self.all_pts) if .02 < q.y < .13 and abs(q.z - self.axis_z) < .06 and q.x > -.01 and not self.is_thumb[i]]
        self.FV = {f: self.finger_verts(f) for f in FINGERS + ['Thumb']}
        self.DV = {f: self.distal_verts(f) for f in FINGERS}
        self.report = {}

    # --- frames -------------------------------------------------------------------------------------------------
    def _pp(self, v):                                          # hand frame -> palm-positive frame
        return Vector((v.x * self.sign, v.y, v.z))

    def pp_to_hand(self, v):
        return Vector((v.x * self.sign, v.y, v.z))

    def finger_bones(self, f):
        return [f'mixamorig:{self.side}Hand{f}{i}' for i in (1, 2, 3)]

    def finger_verts(self, f):
        gs = {self.hands.vertex_groups[n].index for n in self.finger_bones(f)}
        return [v.index for v in self.hands.data.vertices if any(g.group in gs and g.weight > .3 for g in v.groups)]

    def distal_verts(self, f):
        gi3 = self.hands.vertex_groups[self.finger_bones(f)[2]].index
        return [v.index for v in self.hands.data.vertices if any(g.group == gi3 and g.weight > .4 for g in v.groups)]

    def evaluated_coords(self, idx):
        dg = bpy.context.evaluated_depsgraph_get(); ev = self.hands.evaluated_get(dg); me = ev.to_mesh()
        out = [ev.matrix_world @ me.vertices[i].co for i in idx]; ev.to_mesh_clear(); return out

    def grip_axis(self):
        m = self.sword.matrix_world; return m @ Vector((0, 0, 0)), (m.to_3x3() @ Vector((0, 0, 1))).normalized()

    @staticmethod
    def dist_to_axis(p, o, d):
        v = p - o; return (v - d * v.dot(d)).length

    # --- socket: where the sword sits relative to this hand ---------------------------------------------------------
    def guard_z(self):
        return self.index_edge - .004 - self.THUMB_SPACE

    def palm_surface_x(self, ay):
        o = [q for q in self.all_pts if abs(q.y - ay) < self.R and abs(q.z - self.axis_z) < .03 and q.x > 0]
        return max(q.x for q in o)

    def socket_matrix(self, ax, ay, guard_z=None):
        """Sword local -> hand local (bone-space, origin at the bone head) for a grip axis through (ax, ay) with the guard at guard_z."""
        gz = self.guard_z() if guard_z is None else guard_z
        pivot = self.pp_to_hand(Vector((ax, ay, gz + self.build['guard_z'])))
        return Matrix.Translation(pivot) @ SOCKET_ROT.to_4x4(), pivot

    def place_sword(self, ax, ay, guard_z=None):
        """Bone-parent the sword to this hand (used for the primary hand)."""
        local, pivot = self.socket_matrix(ax, ay, guard_z)
        sw = self.sword; sw.parent = self.arm; sw.parent_type = 'BONE'; sw.parent_bone = self.HAND; sw.matrix_parent_inverse = Matrix.Identity(4)
        sw.matrix_basis = Matrix.Translation(Vector((0, -self.pb.length, 0))) @ local
        bpy.context.view_layer.update(); self.pivot = pivot; return pivot

    def hand_matrix_for_sword(self, ax, ay, guard_z=None):
        """World matrix this hand must have so that the sword (already placed in the world) sits in its grip."""
        local, pivot = self.socket_matrix(ax, ay, guard_z)
        return self.sword.matrix_world @ local.inverted(), pivot

    # --- solving ----------------------------------------------------------------------------------------------------
    def set_angles(self, names, angles, sweep=0.0):
        for n, a in zip(names, angles):
            b = self.arm.pose.bones[n]; b.rotation_mode = 'QUATERNION'
            q = Quaternion((1, 0, 0), math.radians(a))
            if n.endswith('1') and sweep:
                q = Quaternion((0, 0, 1), math.radians(sweep)) @ q
            b.rotation_quaternion = q
        bpy.context.view_layer.update()

    def straighten(self, names):
        for n in names:
            self.arm.pose.bones[n].rotation_mode = 'QUATERNION'; self.arm.pose.bones[n].rotation_quaternion = Quaternion()
        bpy.context.view_layer.update()

    def measure(self, idx):
        o, d = self.grip_axis(); ds = [self.dist_to_axis(p, o, d) for p in self.evaluated_coords(idx)]
        return min(ds), sum(1 for x in ds if x < self.R + .003)

    def palm_sink(self):
        o, d = self.grip_axis(); return self.R - min(self.dist_to_axis(p, o, d) for p in self.evaluated_coords(self.PALM_IDX))

    def wrap(self, names, idx, sweep=0.0, start=(0, 0, 0), step=2.0, limits=(100, 110, 100)):
        ang = list(start); self.set_angles(names, ang, sweep); moved = True
        while moved:
            moved = False
            for j in range(3):
                if ang[j] + step > limits[j]:
                    continue
                ang[j] += step; self.set_angles(names, ang, sweep); dmin, _ = self.measure(idx)
                if dmin < self.R - self.SKIN:
                    ang[j] -= step; self.set_angles(names, ang, sweep)
                else:
                    moved = True
        dmin, ncont = self.measure(idx); return ang, dmin, ncont

    def solve_axis(self, place):
        """Search the grip axis position (palm-positive ax, ay) for the largest index+middle wrap; `place(ax, ay)` puts
        the sword there (either by parenting it to this hand or by moving this hand to the sword)."""
        R = self.R; trials = []
        for ay in [self.knuckle_y + dy for dy in (-.008, -.004, 0, .004, .008, .012, .016, .020)]:
            for sink_target in (0.0, .003, .006):
                for f in FINGERS:
                    self.straighten(self.finger_bones(f))
                ax = self.palm_surface_x(ay) + R - sink_target; place(ax, ay); sink = self.palm_sink()
                if not (-self.PALM_GAP_MAX <= sink <= self.PALM_SINK):
                    trials.append((0, round(ax, 4), round(ay, 4), round(sink * 1000, 1))); continue
                total = 0
                for f in ('Index', 'Middle'):
                    ang, dmin, ncont = self.wrap(self.finger_bones(f), self.FV[f], step=3.0); total += sum(ang)
                trials.append((total, round(ax, 4), round(ay, 4), round(sink * 1000, 1)))
        trials.sort(reverse=True)
        if trials[0][0] == 0:
            trials.sort(key=lambda t: abs(t[3]))
        total, ax, ay, sink = trials[0]
        for f in FINGERS:
            self.straighten(self.finger_bones(f))
        place(ax, ay); self.ax, self.ay = ax, ay
        self.report.update(axis_search=trials[:6], palm_sink_mm=sink, axis=[ax, ay]); return ax, ay

    def solve_fingers(self):
        fr = {}
        for f in FINGERS:
            ang, dmin, ncont = self.wrap(self.finger_bones(f), self.FV[f])
            fr[f] = {'curl': ang, 'min_gap_mm': round((dmin - self.R) * 1000, 2), 'verts_touching': ncont}
        self.report['fingers'] = fr

        def set_spread(f, deg):
            b = self.arm.pose.bones[self.finger_bones(f)[0]]; c = fr[f]['curl']
            b.rotation_quaternion = Quaternion((0, 0, 1), math.radians(deg)) @ Quaternion((1, 0, 0), math.radians(c[0]))
            bpy.context.view_layer.update()

        def gap(f, g):
            a = self.evaluated_coords(self.DV[f]); b = self.evaluated_coords(self.FV[g]); return min((x - y).length for x in a for y in b[::2])

        for f, g in (('Index', 'Middle'), ('Ring', 'Middle'), ('Pinky', 'Ring')):
            best = (gap(f, g), 0); dmin0, _ = self.measure(self.FV[f]); floor = min(self.R - self.SKIN, dmin0) - .001
            for sign in (1, -1):
                for d in range(2, 31, 2):
                    set_spread(f, sign * d); gp = gap(f, g); dmin, _ = self.measure(self.FV[f])
                    if dmin < floor or gp < .0003:
                        break
                    if gp < best[0]:
                        best = (gp, sign * d)
                    if gp < .0015:
                        break
                if best[1] * sign > 0:
                    break
            set_spread(f, best[1]); fr[f]['spread'] = best[1]; fr[f]['gap_to_neighbour_mm'] = round(best[0] * 1000, 1)

    def solve_thumb(self):
        tb = self.finger_bones('Thumb'); best = None
        Mh = self.arm.matrix_world @ self.pb.matrix
        target = Vector((self.ax + self.R + .002, self.ay - .004, self.index_edge - .012))
        index_pts = self.evaluated_coords(self.FV['Index'])

        def thumb_to_index():
            tp = self.evaluated_coords(self.FV['Thumb']); return min((a - b).length for a in tp for b in index_pts[::3])

        for sweep in range(-130, 91, 10):
            for c1 in range(0, 61, 10):
                for c2 in range(10, 61, 10):
                    self.set_angles(tb, (c1, c2, c2 * .5), sweep); dmin, ncont = self.measure(self.FV['Thumb'])
                    if dmin < self.R - self.SKIN:
                        continue
                    tip = self._pp(Mh.inverted() @ (self.arm.matrix_world @ self.arm.pose.bones[tb[2]].tail))
                    score = (tip - target).length + (0.01 if ncont == 0 else 0)
                    if best is None or score < best[0]:
                        ti = thumb_to_index()
                        if ti < .002:
                            continue
                        best = (score, sweep, [c1, c2, c2 * .5], dmin, ncont, ti)
        if best is None:                                       # nothing clears the grip and the index finger: relax the squish, then give up gracefully
            for sweep in range(-130, 91, 10):
                for c1 in range(0, 61, 10):
                    for c2 in range(10, 61, 10):
                        self.set_angles(tb, (c1, c2, c2 * .5), sweep); dmin, ncont = self.measure(self.FV['Thumb'])
                        if dmin < self.R - 2 * self.SKIN:
                            continue
                        tip = self._pp(Mh.inverted() @ (self.arm.matrix_world @ self.arm.pose.bones[tb[2]].tail))
                        score = (tip - target).length + (0.01 if ncont == 0 else 0)
                        if best is None or score < best[0]:
                            ti = thumb_to_index()
                            if ti < .001:
                                continue
                            best = (score, sweep, [c1, c2, c2 * .5], dmin, ncont, ti)
        if best is None:
            self.set_angles(tb, (10, 10, 5), -20); dmin, ncont = self.measure(self.FV['Thumb'])
            self.report['thumb'] = {'unsolved': True, 'min_gap_mm': round((dmin - self.R) * 1000, 2)}; return
        score, sweep, ang, dmin, ncont, ti = best
        self.set_angles(tb, ang, sweep)
        self.report['thumb'] = {'sweep': sweep, 'curl': ang, 'min_gap_mm': round((dmin - self.R) * 1000, 2), 'verts_touching': ncont,
                                'tip_to_target_mm': round(score * 1000, 1), 'thumb_to_index_mm': round(ti * 1000, 1)}

    def worst_sink(self):
        o, d = self.grip_axis(); allev = self.evaluated_coords(list(range(len(self.hands.data.vertices))))
        near = [self.dist_to_axis(p, o, d) for p, q in zip(allev, self.all_pts) if abs(q.z - self.axis_z) < .06 and q.y > .0]
        return round((self.R - min(near)) * 1000, 2)

    def bones_touched(self):
        return [self.HAND] + sum((self.finger_bones(f) for f in FINGERS + ['Thumb']), [])
