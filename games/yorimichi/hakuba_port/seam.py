"""Where Sunset Pier's path in from the coast meets the coast road's edge.

The source builds the path's end up to 9 mm short of the road's edge, a slit at the path's west corner. The road owns
that edge, so the path meets it: `meet` moves each path vertex within `REACH` of the road's edge, in plan, and within
`RISE` of its height there onto the edge's nearest point, and splits the path's edges along it at the road's own
vertices, so the path's end follows the road's edge exactly. `pier_path.py` (the walking surface) and `convert.py`
(the path's props) both run it on the same source mesh, so the two still share every vertex. `ROAD` and `edge` need
no Blender; `meet` runs inside it.
"""
import json
from pathlib import Path

import numpy as np

ROAD = (Path(__file__).resolve().parents[2] / 'hakuba' / 'assets' / 'world' / 'src' / 'regions' / 'momiji-coast'
        / 'road-source.json')
# How far, in plan, a path vertex may stand off the road's edge to meet it, and how far above or under it, in metres.
REACH, RISE = 0.02, 0.05
# Splits land strictly inside an edge, this far from its ends as a fraction of its length.
INSIDE = 1e-4


def edge(near, margin=1.0):
    """The road's outer edge as (n, 2, 3) map segments: its triangles' edges that only one triangle has, those within
    `margin` of the (west, south, east, north) rectangle `near`."""
    triangles = np.array([t['xyz'] for t in json.loads(ROAD.read_text())['triangles']], float)
    key = np.round(triangles, 4)
    count = {}
    for t in key:
        for a, b in ((0, 1), (1, 2), (2, 0)):
            pair = tuple(sorted((tuple(t[a]), tuple(t[b]))))
            count[pair] = count.get(pair, 0) + 1
    segments = np.array([pair for pair, n in count.items() if n == 1], float)
    west, south, east, north = near
    lo, hi = segments[..., :2].min(1), segments[..., :2].max(1)
    inside = ((hi[:, 0] >= west - margin) & (lo[:, 0] <= east + margin)
              & (hi[:, 1] >= south - margin) & (lo[:, 1] <= north + margin))
    return segments[inside]


def nearest(points, segments):
    """Each point's nearest point on `segments` in plan, with the segment's height there, and its plan distance."""
    a, b = segments[None, :, 0], segments[None, :, 1]
    d = b - a
    t = np.clip(((points[:, None, :2] - a[..., :2]) * d[..., :2]).sum(-1)
                / np.maximum((d[..., :2] ** 2).sum(-1), 1e-18), 0.0, 1.0)
    q = a + t[..., None] * d
    apart = np.linalg.norm(q[..., :2] - points[:, None, :2], axis=-1)
    best = apart.argmin(1)
    rows = np.arange(len(points))
    return q[rows, best], apart[rows, best]


def meet(o, segments):
    """Move the vertices of the Blender object `o` (its frame the segments' frame) that stand within `REACH` and
    `RISE` of the road's edge onto it, and split its edges between two such vertices at the edge's own vertices.
    Returns how many vertices moved and how many were added."""
    import bmesh
    from mathutils import Vector
    if not len(segments):
        return 0, 0
    mesh = bmesh.new()
    mesh.from_mesh(o.data)
    verts = list(mesh.verts)
    points = np.array([v.co[:] for v in verts], float)
    q, apart = nearest(points, segments)
    moved = (apart <= REACH) & (np.abs(points[:, 2] - q[:, 2]) <= RISE)
    for k in np.flatnonzero(moved):
        verts[k].co = Vector(q[k])
    on = {verts[k] for k in np.flatnonzero(moved)}
    corners = np.unique(segments.reshape(-1, 3), axis=0)
    added = 0
    for corner in corners:
        for e in [e for e in mesh.edges if e.verts[0] in on and e.verts[1] in on]:
            a, b = np.array(e.verts[0].co[:]), np.array(e.verts[1].co[:])
            d = b - a
            length = float((d[:2] ** 2).sum())
            if length < 1e-12:
                continue
            t = float(((corner[:2] - a[:2]) * d[:2]).sum() / length)
            off = np.linalg.norm(a[:2] + t * d[:2] - corner[:2])
            if INSIDE < t < 1 - INSIDE and off <= REACH:
                _, vert = bmesh.utils.edge_split(e, e.verts[0], t)
                vert.co = Vector(corner)
                on.add(vert)
                added += 1
    mesh.to_mesh(o.data)
    mesh.free()
    return int(moved.sum()), added
