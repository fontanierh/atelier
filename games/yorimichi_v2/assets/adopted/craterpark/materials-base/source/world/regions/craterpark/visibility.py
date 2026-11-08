"""Which of Crater Park's faces can be seen from the open space (Blender: a BVH of every face; native frame, y up).

A face is drawn only if it can be seen. From sample points on it (about one per SPACING square, MIN to MAX of them,
2 mm off its front, and off its back too where its material is double-sided) RAYS cosine-weighted rays go out: the
face is seen if one escapes the park, or if the free run of one, up to what blocks it, passes through the open space
reachable from outside (clean.reachable). That keeps every face seen through a tunnel, under a span or in a pocket,
and leaves out the foundation prisms' shared walls, their bottoms, the hillside under the pieces and the coping's
buried underside: about four in five of the faces r4 drew.
"""
import numpy as np

SPACING = .5        # metres between a face's sample points, about
MIN, MAX = 4, 16    # sample points per face
RAYS = 8            # rays per sample point
FAR = 3000.         # metres: a ray this long escapes
LIFT = .002         # metres a sample point stands off its face


def bvh(triangles):
    """A BVH over the faces (n,3,3), through a throwaway mesh (bounded memory)."""
    import bpy
    from mathutils.bvhtree import BVHTree
    n = len(triangles)
    me = bpy.data.meshes.new('visibility')
    me.vertices.add(3 * n); me.vertices.foreach_set('co', triangles.reshape(-1).astype('f4'))
    me.loops.add(3 * n); me.loops.foreach_set('vertex_index', np.arange(3 * n, dtype='i4'))
    me.polygons.add(n); me.polygons.foreach_set('loop_start', np.arange(0, 3 * n, 3, dtype='i4'))
    me.polygons.foreach_set('loop_total', np.full(n, 3, 'i4'))
    me.update(calc_edges=False)
    ob = bpy.data.objects.new('visibility', me); bpy.context.collection.objects.link(ob)
    tree = BVHTree.FromObject(ob, bpy.context.evaluated_depsgraph_get())
    bpy.data.objects.remove(ob); bpy.data.meshes.remove(me)
    return tree


def seen_faces(tree, triangles, two_sided, reach, test=None, seed=1):
    """Mask of the faces (n,3,3) seen from the reachable open space (reach: grid, origin, voxel). `two_sided`: a bool
    per face, or one for all; `test`: the faces to test (the others are returned as seen). Per face and side, the
    centroid's rays go first; the rest of its samples' rays go out in one batch, their runs marched through the
    reach grid at once."""
    grid, org, h = reach
    shape = np.array(grid.shape)
    rng = np.random.default_rng(seed)
    ray = tree.ray_cast
    steps = np.arange(.5, 400) * (h / 2)
    t = triangles.astype('f8')
    nn = np.cross(t[:, 1] - t[:, 0], t[:, 2] - t[:, 0]); area = np.linalg.norm(nn, axis=1) / 2
    nn /= np.maximum(np.linalg.norm(nn, axis=1, keepdims=True), 1e-300)
    ns = np.clip(np.ceil(area / SPACING ** 2), MIN, MAX).astype(int)
    two = np.broadcast_to(np.asarray(two_sided, bool), (len(t),))
    seen = np.ones(len(t), bool)
    idx = np.arange(len(t)) if test is None else np.flatnonzero(test)
    seen[idx] = False

    def out(O, D):
        """True if a ray (origins O (r,3), directions D (r,3)) escapes, or its free run passes reachable space."""
        ts = np.empty(len(O))
        for i, (o, d) in enumerate(zip(O.tolist(), D.tolist())):
            hit = ray(o, d, FAR)
            if hit[0] is None:
                return True
            ts[i] = hit[3]
        m = steps[None, :] < (ts[:, None] - h / 4)
        k = int(m.sum(1).max())
        if not k:
            return False
        p = O[:, None, :] + D[:, None, :] * steps[None, :k, None]
        c = np.floor((p[m[:, :k]] - org) / h).astype(int)
        c = c[((c >= 0) & (c < shape)).all(1)]
        return bool(len(c)) and bool(grid[c[:, 0], c[:, 1], c[:, 2]].any())

    i_r = (np.arange(RAYS) + .5) / RAYS
    for f in idx.tolist():
        s = ns[f]
        r1 = np.sqrt((np.arange(s) + rng.random(s)) / s); r2 = rng.random(s)
        r1[0], r2[0] = np.sqrt(2 / 3), .5                                   # the centroid first
        b = np.stack([1 - r1, r1 * (1 - r2), r1 * r2], 1) * .98 + .02 / 3
        pts = b @ t[f]
        for sgn in ((1., -1.) if two[f] else (1.,)):
            n = sgn * nn[f]
            side = np.array([1., 0, 0]) if abs(n[0]) < .9 else np.array([0, 0, 1.])
            tu = np.cross(n, side); tu /= np.linalg.norm(tu); tv = np.cross(n, tu)
            # cosine-weighted directions, a fresh rotation per sample
            r = np.sqrt((i_r[None, :] + rng.random((s, 1)) / RAYS) % 1.)
            phi = 2 * np.pi * ((np.arange(RAYS)[None, :] * .618034 + rng.random((s, 1))) % 1)
            D = (r * np.cos(phi))[..., None] * tu + (r * np.sin(phi))[..., None] * tv + np.sqrt(1 - r * r)[..., None] * n
            O = np.repeat((pts + LIFT * n)[:, None, :], RAYS, 1)
            if out(O[0], D[0]) or (s > 1 and out(O[1:].reshape(-1, 3), D[1:].reshape(-1, 3))):
                seen[f] = True
                break
    return seen
