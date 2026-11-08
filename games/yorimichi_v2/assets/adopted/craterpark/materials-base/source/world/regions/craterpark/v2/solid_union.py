"""Join designed closed solids without retaining their covered interior faces.

The riding layout and matching interface heights are designed before a union.
This operation closes intersecting receiver/bowl bodies; it does not make an
incorrect crossing or discontinuous riding route acceptable. Run the geometry
and native route gates on its result.

Uses Manifold's float64 mesh and original-face relations, as documented in
https://github.com/elalish/manifold/blob/master/bindings/python/manifold3d.cpp
"""
import numpy as np

from . import dsl, solids


def canonicalize(mesh, tolerance=solids.WELD):
    """Unify numerical split positions and remove only collapsed triangles.

    UVs and normals remain split at their original chart/crease boundaries.
    The same geometric precision is used by the normal topology gate.
    """
    keys, first, inverse = np.unique(np.round(mesh.V / tolerance).astype('i8'), axis=0,
                                     return_index=True, return_inverse=True)
    positions = np.zeros((len(first), 3))
    np.add.at(positions, inverse, mesh.V)
    weight = np.bincount(inverse)
    positions /= weight[:, None]
    # Rounding alone misses two near-identical positions on opposite sides
    # of a cell boundary. Search the 13 forward neighbours as well; one
    # representative per occupied cell keeps this bounded for attribute seams.
    lookup = {tuple(k): i for i, k in enumerate(keys)}
    offsets = [(x, y, z) for x in (-1, 0, 1) for y in (-1, 0, 1) for z in (-1, 0, 1)
               if (x, y, z) > (0, 0, 0)]
    parent = np.arange(len(keys))

    def root(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return int(i)

    for i, (x, y, z) in enumerate(keys):
        for dx, dy, dz in offsets:
            j = lookup.get((x + dx, y + dy, z + dz))
            if j is not None and np.linalg.norm(positions[i] - positions[j]) <= tolerance:
                parent[root(j)] = root(i)
    parent = np.asarray([root(i) for i in range(len(parent))])
    total = np.zeros_like(positions)
    np.add.at(total, parent, positions * weight[:, None])
    count = np.bincount(parent, weights=weight, minlength=len(parent))
    used = count > 0
    total[used] /= count[used, None]
    new = total[parent[inverse]]
    if np.linalg.norm(new - mesh.V, axis=1).max(initial=0.) > 2 * tolerance:
        raise ValueError('solid union: numerical seam cluster exceeds topology precision')
    mesh.V = new
    F = parent[inverse[mesh.F]]
    keep = (F[:, 0] != F[:, 1]) & (F[:, 1] != F[:, 2]) & (F[:, 2] != F[:, 0])
    return mesh.subset(keep)


def union(meshes):
    """@cc [owner:fontanierh,label:correctness] labelled-closed-solid-union
    Inputs and output MUST be closed outward manifolds. Face materials, roles,
    tags and feature ownership MUST come from exact original-face relations,
    never from interpolated categorical vertex properties. Normals, UVs and AO
    MUST retain their original vertex charts. A failed solid MUST raise.
    """
    import manifold3d as M

    meshes = tuple(meshes)
    if not meshes:
        raise ValueError('solid union requires at least one closed mesh')
    names = tuple(dict.fromkeys(n for m in meshes for n in m.features))
    features = {n: i for i, n in enumerate(names)}
    inputs, source = [], {}
    for mesh in meshes:
        solids.check_closed(mesh)
        # Keep attribute seams as separate property vertices, with explicit
        # geometric merges so that they still form a closed solid.
        key = np.round(mesh.V / solids.WELD).astype('i8')
        _, first, inverse = np.unique(key, axis=0, return_index=True, return_inverse=True)
        to = first[inverse]
        frm = np.flatnonzero(to != np.arange(len(to)))
        props = np.ascontiguousarray(np.c_[mesh.V, mesh.N, mesh.UV, mesh.AO])
        original = M.Manifold.reserve_ids(1)
        raw = M.Mesh64(props, np.ascontiguousarray(mesh.F, dtype=np.uint64),
                       merge_from_vert=frm.astype(np.uint64), merge_to_vert=to[frm].astype(np.uint64),
                       run_index=np.array([0, len(mesh.F) * 3], dtype=np.uint64),
                       run_original_id=np.array([original], dtype=np.uint32),
                       face_id=np.arange(len(mesh.F), dtype=np.uint64))
        item = M.Manifold(raw)
        if item.status() != M.Error.NoError:
            raise ValueError(f'solid union: rejected input {item.status()}')
        source[original] = mesh
        inputs.append(item)
    result = M.Manifold.batch_boolean(inputs, M.OpType.Add)
    if result.status() != M.Error.NoError or result.is_empty():
        raise ValueError(f'solid union: failed result {result.status()}')
    raw = result.to_mesh64()
    props = np.asarray(raw.vert_properties)
    F = np.asarray(raw.tri_verts, dtype=np.int64)
    if props.shape[1] != 9:
        raise ValueError('solid union lost a vertex attribute chart')
    N = props[:, 3:6].copy()
    length = np.linalg.norm(N, axis=1)
    if (length < 1e-12).any():
        raise ValueError('solid union produced an undefined shading normal')
    N /= length[:, None]
    mat, role, feature, tag = (np.empty(len(F), np.int32) for _ in range(4))
    face = np.asarray(raw.face_id, np.int64)
    runs = np.asarray(raw.run_index, np.int64) // 3
    for i, original in enumerate(raw.run_original_id):
        mesh = source[int(original)]
        sl = slice(runs[i], runs[i + 1])
        ids = face[sl]
        mat[sl], role[sl], tag[sl] = mesh.material[ids], mesh.role[ids], mesh.tag[ids]
        feature[sl] = np.asarray([features[n] for n in mesh.features])[mesh.feature[ids]]
    out = dsl.Mesh(props[:, :3].copy(), F, N, props[:, 6:8], props[:, 8],
                   mat, role, feature, names, {}, tag)
    out = canonicalize(out)
    solids.check_closed(out)
    return out
