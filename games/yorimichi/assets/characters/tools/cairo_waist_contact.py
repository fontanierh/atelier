"""Exact outer shirt/shorts intersections near the waistband."""
import sys as _sys; from pathlib import Path as _Path; _sys.path.insert(0, str(_Path(__file__).resolve().parents[3] / 'world')); import yori  # noqa: E402
import sys as _sys; from pathlib import Path as _Path; _sys.path.insert(0, str(_Path(__file__).resolve().parent))  # Blender's --python does not add the script's folder
from _archive import ROOT, TOOLS  # noqa: E402  (ROOT: the prototype archive holding the revision history)
import bpy
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree
from cairo_outfit_arm_clearance import _crossings


class WaistContactProbe:
    def __init__(self, shirt, shorts):
        self.objects = (shirt, shorts)
        self.faces = []
        for obj in self.objects:
            points = np.array([v.co[:] for v in obj.data.vertices])
            yellow = obj.data.attributes.get('yellow_layer')
            faces = []
            for p in obj.data.polygons:
                ids = list(p.vertices)
                center = points[ids].mean(axis=0)
                if obj == shirt:
                    if not all(yellow.data[i].value > .5 for i in ids):
                        continue
                    if center[2] > .04 or abs(center[1]) > .145:
                        continue
                elif max(points[ids, 2]) < -.13:
                    continue
                if p.normal.dot(Vector((center[0]-.023, center[1], 0))) > 0:
                    faces.append(ids)
            self.faces.append(faces)

    def check(self, details=False):
        bpy.context.view_layer.update()
        dg = bpy.context.evaluated_depsgraph_get()
        points = [[obj.matrix_world @ v.co for v in obj.evaluated_get(dg).data.vertices]
                  for obj in self.objects]
        trees = [BVHTree.FromPolygons(v, f) for v, f in zip(points, self.faces)]
        hits = []
        for a, b in trees[0].overlap(trees[1]):
            if _crossings([points[0][i] for i in self.faces[0][a]],
                          [points[1][i] for i in self.faces[1][b]]):
                hits.append((a, b))
        result = {'shirt_faces':len({a for a,b in hits}), 'shorts_faces':len({b for a,b in hits})}
        if details:
            result['vertices'] = [sorted({i for h in hits for i in self.faces[n][h[n]]}) for n in range(2)]
        return result
