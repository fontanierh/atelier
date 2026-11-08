"""Split a compiled park into render tiles and collision sections (plan/pipeline.md 5.6, 9), bpy-free.

Render: one mesh per (render role, material, 64 m tile), at most MAX_RENDER triangles each (further split in
spatial order), named SM_CP_<role>_<material>_<tx>_<tz>[_<k>]. Base faces are never drawn.
Collision: the faces whose role has a collision role (dsl.COLLISION_ROLE), per collision role, in spatial order
(the skate simulation groups 64 stored triangles at a time), sections of at most SECTION triangles, named
UC_CP_<role>_<k>.
"""
import numpy as np

from . import dsl

TILE = 64.
MAX_RENDER = 30000
SECTION = 200000
LARGE = 8.        # metres across: a collision face this large is stored with the other large ones


def spatial_order(triangles, cell=1.):
    """The order of the `triangles` (n, 3, 3) along a Z-order curve of their centres over `cell`-metre cells, those over
    LARGE metres across last (craterpark/build.py spatial_order, without bpy)."""
    t = np.asarray(triangles, 'f8')
    if not len(t):
        return np.zeros(0, 'i8')
    centres = t.mean(1)
    large = np.linalg.norm(t.max(1) - t.min(1), axis=1) > LARGE
    q = np.floor((centres - centres.min(0)) / cell).astype('u8') & 0x1fffff
    code = np.zeros(len(q), 'u8')
    for bit in range(21):
        for axis in range(3):
            code |= ((q[:, axis] >> np.uint64(bit)) & np.uint64(1)) << np.uint64(3 * bit + axis)
    return np.lexsort((code, large))


GROUND_TILE = 128.  # the hillside's tiles: plain world-aligned ground, large triangles, so fewer, larger meshes


def render_meshes(mesh, tile=TILE, limit=MAX_RENDER, ground_tile=GROUND_TILE):
    """[(name, render role, Mesh)] for every drawn face of `mesh`, deterministic order (sorted by name)."""
    roles = np.asarray([dsl.RENDER_ROLE.get(r) for r in dsl.ROLES], object)[mesh.role]
    drawn = np.asarray([r is not None for r in roles], bool)
    if not drawn.any():
        return []
    c = mesh.triangles().mean(1)
    size = np.where(roles == dsl.RENDER_ROLE[dsl.GROUND], ground_tile, tile)
    tx = np.floor(c[:, 0] / size).astype('i8'); tz = np.floor(c[:, 2] / size).astype('i8')
    out = []
    keys = sorted({(roles[i], int(mesh.material[i]), int(tx[i]), int(tz[i])) for i in np.flatnonzero(drawn)})
    for role, material, x, z in keys:
        idx = np.flatnonzero(drawn & (roles == role) & (mesh.material == material) & (tx == x) & (tz == z))
        idx = idx[spatial_order(mesh.triangles()[idx])]
        base = f'SM_CP_{role}_{dsl.MATERIALS[material]}_{x}_{z}'.replace('-', 'm')
        chunks = [idx[k:k + limit] for k in range(0, len(idx), limit)]
        for k, part in enumerate(chunks):
            mask = np.zeros(len(mesh.F), bool); mask[part] = True
            sub = mesh.subset(mask)
            out.append((base if len(chunks) == 1 else f'{base}_{k}', role, sub))
    return sorted(out, key=lambda e: e[0])


def collision_sections(mesh, section=SECTION):
    """[(name, collision role, triangles (n, 3, 3))], each section spatially ordered."""
    roles = np.asarray([dsl.COLLISION_ROLE.get(r) for r in dsl.ROLES], object)[mesh.role]
    out = []
    for role in sorted({r for r in roles if r is not None}):
        t = mesh.triangles()[roles == role]
        t = t[spatial_order(t)]
        for k in range(0, len(t), section):
            out.append((f'UC_CP_{role}_{k // section}', role, t[k:k + section]))
    return out
