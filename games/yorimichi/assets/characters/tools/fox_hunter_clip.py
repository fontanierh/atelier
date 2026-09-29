"""Self-intersection checks for the fox hunter on the deformed mesh (shared by the authoring script and
fox_hunter_clipcheck.py). Vertices are grouped by their strongest bone; each lower arm (forearm, hand, fingers)
is tested against the rest of the body and each whole arm against the other arm. Two measures per pair:
  pierced: edges of the source group that pass through a face of the target (catches thin cloth too),
  depth:   how far a source vertex sits inside the target surface by ray parity (closed parts only).
Plus the lateral position of each hand relative to the chest, to catch arms crossing the midline."""
import sys as _sys; from pathlib import Path as _Path; _sys.path.insert(0, str(_Path(__file__).resolve().parents[3] / 'world')); import yori  # noqa: E402
from _archive import ROOT, TOOLS  # noqa: E402  (ROOT: the prototype archive holding the revision history)
import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree

PAIRS = [('Llower', ('torso', 'Rleg', 'Lleg', 'Rupper', 'Rlower')), ('Rlower', ('torso', 'Rleg', 'Lleg', 'Lupper', 'Llower')),
         ('Llower+Lupper', ('Rlower', 'Rupper')), ('Rlower+Rupper', ('Llower', 'Lupper'))]
RAYS = [Vector((1, 0, 0)), Vector((0, 0, 1)), Vector((0.36, 0.48, 0.8)).normalized(), Vector((-0.6, 0.64, 0.48)).normalized()]

def group_of(name):
    n = name.replace('mixamorig:', '')
    side = 'L' if n.startswith('Left') else ('R' if n.startswith('Right') else '')
    if any(f in n for f in ('ForeArm', 'Hand', 'Thumb', 'Index', 'Middle', 'Ring', 'Pinky')): return side + 'lower'
    if n in ('LeftArm', 'RightArm'): return side + 'upper'
    if any(f in n for f in ('UpLeg', 'Leg', 'Foot', 'ToeBase')): return side + 'leg'
    return 'torso'

class Checker:
    def __init__(self, body, arm):
        self.body, self.arm = body, arm
        gi = {g.index: group_of(g.name) for g in body.vertex_groups}
        self.vgroup = []
        for v in body.data.vertices:
            best = max(v.groups, key=lambda g: g.weight, default=None)
            self.vgroup.append(gi[best.group] if best else 'torso')
        faces = [tuple(p.vertices) for p in body.data.polygons]
        fg = []
        for f in faces:
            gs = {self.vgroup[i] for i in f}
            fg.append(gs.pop() if len(gs) == 1 else None)
        self.src_idx, self.src_edges, self.tgt_faces = {}, {}, {}
        edges = [tuple(e.vertices) for e in body.data.edges]
        for src, tg in PAIRS:
            parts = src.split('+')
            self.src_idx[src] = [i for i, g in enumerate(self.vgroup) if g in parts]
            self.src_edges[src] = [e for e in edges if self.vgroup[e[0]] in parts and self.vgroup[e[1]] in parts]
            self.tgt_faces[tg] = [f for f, g in zip(faces, fg) if g in tg]

    def _inside(self, bvh, pt):
        votes = 0
        for d in RAYS:
            o = pt.copy(); hits = 0
            for _ in range(64):
                loc, nrm, idx, dist = bvh.ray_cast(o, d)
                if loc is None: break
                hits += 1; o = loc + d * 0.0005
            votes += hits % 2
        return votes >= 3

    def frame(self, dg, want_depth=True):
        ev = self.body.evaluated_get(dg); mw = ev.matrix_world
        co = [mw @ v.co for v in ev.data.vertices]
        out = {}
        for src, tg in PAIRS:
            tris = self.tgt_faces[tg]
            key = src + '>' + '+'.join(tg)
            if not tris: out[key] = dict(pierced=0, depth=0.0, inside=0); continue
            bvh = BVHTree.FromPolygons(co, tris, all_triangles=False)
            pierced = 0
            for e0, e1 in self.src_edges[src]:
                d = co[e1] - co[e0]; L = d.length
                if L < 1e-6: continue
                loc, nrm, idx, dist = bvh.ray_cast(co[e0], d / L, L)
                if loc is not None: pierced += 1
            depth, inside = 0.0, 0
            if want_depth and pierced:
                for i in self.src_idx[src]:
                    if self._inside(bvh, co[i]):
                        loc, nrm, idx, dist = bvh.find_nearest(co[i]); inside += 1; depth = max(depth, dist)
            out[key] = dict(pierced=pierced, depth=round(depth, 4), inside=inside)
        # hands against the chest midline, in the character's frame
        root = self.arm.pose.bones['Root']
        B = (self.arm.matrix_world.to_3x3() @ root.matrix.to_3x3() @ root.bone.matrix_local.to_3x3().inverted())
        rp = self.arm.matrix_world @ root.head
        def char(w): return B.inverted() @ (w - rp)
        chest = char(self.arm.matrix_world @ self.arm.pose.bones['mixamorig:Spine2'].head)
        lh = char(self.arm.matrix_world @ self.arm.pose.bones['mixamorig:LeftHand'].tail)
        rh = char(self.arm.matrix_world @ self.arm.pose.bones['mixamorig:RightHand'].tail)
        out['hands'] = dict(left_out=round(lh.y - chest.y, 3), right_out=round(chest.y - rh.y, 3))
        return out

def summarize(frames):
    """frames: list of (f, result). Per pair: worst pierce count and its frame, frames with any pierce, max depth."""
    keys = [k for k in frames[0][1] if k != 'hands']
    s = {}
    for k in keys:
        worst = max(frames, key=lambda fr: fr[1][k]['pierced'])
        s[k] = dict(max_pierced=worst[1][k]['pierced'], frame=worst[0], frames_pierced=sum(1 for fr in frames if fr[1][k]['pierced']),
                    max_depth=max(fr[1][k]['depth'] for fr in frames))
    s['hands'] = dict(left_min_out=min(fr[1]['hands']['left_out'] for fr in frames), right_min_out=min(fr[1]['hands']['right_out'] for fr in frames))
    return s

def line(name, s):
    parts = [f"{k.split('>')[0]}:{v['max_pierced']}@{v['frame']}/{v['frames_pierced']}f/{v['max_depth'] * 100:.1f}cm" for k, v in s.items() if k != 'hands']
    return f"{name:13s} " + '  '.join(parts) + f"  hands out L{s['hands']['left_min_out']:+.2f} R{s['hands']['right_min_out']:+.2f}"
