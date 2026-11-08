"""Ambient occlusion: r4's bake (build.ambient_occlusion), unchanged in its rays, reach and smoothing, on a v2 Mesh.

The drawn faces fill a voxel grid (AO_VOXEL); from each vertex AO_RAYS cosine-weighted rays (a fixed spiral:
deterministic builds) march out to AO_REACH at AO_STEPS geometric distances, and a ray first blocked at distance d
occludes by 1 - d / reach. Two passes of neighbour averaging (.5 own + .5 neighbours' mean) take out the grid's step
noise; the result is clipped to 0..1 (1 open). It stays sRGB-encoded in the vertex colour downstream.

Bit-identical to build.ambient_occlusion (test_craterpark_v2_ao): the same grid fill (a barycentric grid per face,
its longest edge over voxel/2 steps), rays and smoothing. The fill goes in batches of `budget` points and the rays in
CHUNK vertices: memory is bounded by points, never by faces.

On a v2 Mesh (bake_mesh): rays leave along the mesh's own (analytic) normals; vertices are split at creases and UV
seams, so the smoothing runs over NODES, one per (position, normal): a UV seam's twins (one normal) smooth as one and
get one value, while a crease's sides (two normals) keep their own.
"""
import math

import numpy as np

AO_VOXEL = .5       # metres
AO_REACH = 12.      # metres
AO_RAYS = 16
AO_STEPS = 10
SMOOTH = 2          # neighbour-averaging passes
CHUNK = 20000       # vertices per ray batch: bounds the memory
WELD = 1e-6         # metres: positions this close are one node
NORMAL_KEY = 1e-4   # normals equal to this are one node (seam twins), else a crease's sides


def directions(rays=AO_RAYS):
    """Cosine-weighted directions over the hemisphere about +z, a fixed spiral."""
    i = np.arange(rays) + .5
    r = np.sqrt(i / rays); phi = i * math.pi * (3 - math.sqrt(5))
    return np.stack([r * np.cos(phi), r * np.sin(phi), np.sqrt(1 - r * r)], -1)


def area_normals(V, F):
    """Area-weighted vertex normals (r4's), +y where a vertex has no face."""
    n = np.zeros((len(V), 3))
    if len(F):
        t = V[F]; face = np.cross(t[:, 1] - t[:, 0], t[:, 2] - t[:, 0])
        for i in range(3):
            np.add.at(n, F[:, i], face)
    length = np.linalg.norm(n, axis=1, keepdims=True)
    return np.where(length > 1e-12, n / np.maximum(length, 1e-12), [0., 1., 0.])


def fill(T, lo, shape, voxel=AO_VOXEL, budget=1_000_000):
    """The voxel grid (bool, origin lo) of the faces T (m,3,3), as r4 fills it: each face sampled on a barycentric grid
    of k + 1 steps along both edges from corner 0, k its longest edge over voxel/2 (at most 400), grouped by k; batched
    by about `budget` points (r4 split by face count only: the grid is the same, the memory bounded)."""
    grid = np.zeros(shape, bool)
    T = np.asarray(T, 'f8')
    edge = np.linalg.norm(T - np.roll(T, 1, 1), axis=2).max(1)
    steps = np.clip(np.ceil(edge / (voxel / 2)), 1, 400).astype(int)
    for k in np.unique(steps):
        g = np.linspace(0, 1, k + 1); a, b = np.meshgrid(g, g); m = a + b <= 1 + 1e-9; a, b = a[m], b[m]
        faces = np.flatnonzero(steps == k)
        per = max(1, budget // len(a))
        for i in range(0, len(faces), per):
            t = T[faces[i:i + per]]
            p = t[:, None, 0] + a[None, :, None] * (t[:, None, 1] - t[:, None, 0]) + b[None, :, None] * (t[:, None, 2] - t[:, None, 0])
            c = np.floor((p.reshape(-1, 3) - lo) / voxel).astype(int)
            c = c[((c >= 0) & (c < shape)).all(1)]
            grid[c[:, 0], c[:, 1], c[:, 2]] = True
    return grid


def grid_for(V, T, voxel=AO_VOXEL, reach=AO_REACH):
    """r4's grid bounds: the vertices and `reach` round them, but not the block's buried sides far below."""
    verts = np.asarray(V, 'f8')
    lo = verts.min(0) - reach - voxel; hi = verts.max(0) + reach + voxel
    lo[1] = max(lo[1], np.percentile(verts[:, 1], 1) - reach)
    shape = tuple(np.ceil((hi - lo) / voxel).astype(int))
    return fill(T, lo, shape, voxel), lo


def rays(V, N, grid, lo, voxel=AO_VOXEL, reach=AO_REACH, n_rays=AO_RAYS, steps=AO_STEPS):
    """Raw (unsmoothed) occlusion of the vertices V along their unit normals N."""
    V = np.asarray(V, 'f8'); N = np.asarray(N, 'f8')
    shape = np.array(grid.shape)
    local = directions(n_rays)
    distances = np.geomspace(1.5 * voxel, reach, steps)
    side = np.where(np.abs(N[:, :1]) < .9, [[1., 0., 0.]], [[0., 0., 1.]])
    tu = np.cross(N, side); tu /= np.linalg.norm(tu, axis=1, keepdims=True); tv = np.cross(N, tu)
    ao = np.ones(len(V))
    for s in range(0, len(V), CHUNK):
        d = (local[None, :, :1] * tu[s:s + CHUNK, None] + local[None, :, 1:2] * tv[s:s + CHUNK, None]
             + local[None, :, 2:] * N[s:s + CHUNK, None])
        origin = V[s:s + CHUNK, None, None] + 1.2 * voxel * N[s:s + CHUNK, None, None]
        p = origin + d[:, :, None] * distances[None, None, :, None]
        c = np.floor((p - lo) / voxel).astype(int)
        inside = ((c >= 0) & (c < shape)).all(-1)
        c = np.where(inside[..., None], c, 0)
        blocked = grid[c[..., 0], c[..., 1], c[..., 2]] & inside
        first = np.where(blocked.any(-1), distances[blocked.argmax(-1)], reach)
        ao[s:s + CHUNK] = 1 - (1 - first / reach).mean(1)
    return ao


def smooth(ao, F, node=None, passes=SMOOTH):
    """r4's neighbour averaging over the faces' edges, `passes` times: ao = .5 ao + .5 mean(neighbours). With `node`
    (n,) (vertices of one node smooth as one: bake_mesh), the graph is the nodes' and every vertex gets its node's."""
    F = np.asarray(F, 'i8')
    if node is None:
        node = np.arange(len(ao))
    k = int(node.max()) + 1 if len(node) else 0
    # a node's value: its vertices' mean (seam twins agree to rounding: one ray set each, the same normal)
    val = np.bincount(node, ao, minlength=k) / np.maximum(np.bincount(node, minlength=k), 1)
    E = node[np.concatenate([F[:, [0, 1]], F[:, [1, 2]], F[:, [2, 0]]])]   # per face, as r4 (an inner edge twice)
    E = E[E[:, 0] != E[:, 1]]                                                # a face's edge between twins: none
    for _ in range(passes):
        total = np.zeros(k); count = np.zeros(k)
        np.add.at(total, E[:, 0], val[E[:, 1]]); np.add.at(count, E[:, 0], 1)
        np.add.at(total, E[:, 1], val[E[:, 0]]); np.add.at(count, E[:, 1], 1)
        val = np.where(count > 0, .5 * val + .5 * total / np.maximum(count, 1), val)
    return np.clip(val[node], 0, 1)


def bake(V, F, N=None, node=None, occluders=None):
    """Per-vertex occlusion of the mesh (V, F): rays along N (default r4's area-weighted normals), the grid filled by
    `occluders` (k,3,3) (default the mesh's own faces), smoothed over `node` (default every vertex its own)."""
    V = np.asarray(V, 'f8'); F = np.asarray(F, 'i8').reshape(-1, 3)
    if not len(V):
        return np.ones(0)
    N = area_normals(V, F) if N is None else np.asarray(N, 'f8')
    grid, lo = grid_for(V, V[F] if occluders is None else occluders)
    raw = rays(V, N, grid, lo)
    del grid
    return smooth(raw, F, node)


def nodes(V, N):
    """One node per (position, normal): UV-seam twins share one, a crease's sides do not."""
    key = np.c_[np.round(np.asarray(V, 'f8') / WELD), np.round(np.asarray(N, 'f8') / NORMAL_KEY)].astype('i8')
    return np.unique(key, axis=0, return_inverse=True)[1].ravel()


def bake_mesh(mesh, drawn=None):
    """Bake mesh.AO in place (returns the mesh): every face occludes (a solid's buried base too); the rays leave along
    mesh.N; the smoothing runs over nodes(). `drawn` (role names): only their vertices are baked, the rest stay 1."""
    from . import dsl
    occluders = mesh.triangles()
    ao = np.ones(len(mesh.V))
    face = np.ones(len(mesh.F), bool) if drawn is None else np.isin(mesh.role, [dsl.ROLE[r] for r in drawn])
    used = np.unique(mesh.F[face])
    if len(used):
        remap = np.full(len(mesh.V), -1, 'i8'); remap[used] = np.arange(len(used))
        V, N, F = mesh.V[used], mesh.N[used], remap[mesh.F[face]]
        ao[used] = bake(V, F, N, nodes(V, N), occluders)
    mesh.AO = ao
    return mesh
