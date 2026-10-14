"""Crater Park's tunnels kept open (pure numpy, native frame: metres, y up).

The foundation blocks under the riding pieces were made solid up to the top of the pieces over them, so the one
round tunnel was filled: its bore held the block's solid, and the rider met its flat end. inside_tubes finds the
faces in a bore (of the pieces tunnels finds), which build.py leaves out of the render and the collision.
"""
import math

import numpy as np

from craterpark import grind

TUBE = 2.               # metres from a tunnel's floor to its roof at least
TUBE_REACH = 12.        # metres to a tunnel's wall at most, every way
TUBE_SIDES = 2          # horizontal lines through a point in a tunnel meeting its wall both ways (its ends are open)
TUBE_RAYS = 5           # of eight horizontal directions from a point near a tunnel's open end, meeting its wall
PROBE = 2.              # metres between the points that find which pieces close round a bore (tunnels)
LARGE = 1.              # metres across: a face this large is tested at SAMPLES points, not its centre alone
# Barycentric points spread over a face, out towards its corners.
SAMPLES = np.array([[.6, .2, .2], [.2, .6, .2], [.2, .2, .6], [.8, .1, .1], [.1, .8, .1], [.1, .1, .8],
                    [.45, .45, .1], [.45, .1, .45], [.1, .45, .45], [.95, .025, .025], [.025, .95, .025], [.025, .025, .95]])
PAIRS = 2_000_000       # ray-face pairs per batch at most


def ray_distances(origins, direction, triangles, reach):
    """The distance from each of the `origins` (k, 3) along `direction` (3,) to the nearest of the `triangles` (m, 3, 3),
    inf where none lies within `reach`."""
    out = np.full(len(origins), np.inf)
    if not len(triangles):
        return out
    e1 = triangles[:, 1] - triangles[:, 0]; e2 = triangles[:, 2] - triangles[:, 0]
    p = np.cross(direction, e2); det = (e1 * p).sum(1)
    ok = np.abs(det) > 1e-12; inv = 1 / np.where(ok, det, 1.)
    step = max(1, PAIRS // max(len(triangles), 1))
    for i in range(0, len(origins), step):
        s = origins[i:i + step, None] - triangles[None, :, 0]
        u = (s * p).sum(-1) * inv; q = np.cross(s, e1); v = (q * direction).sum(-1) * inv; t = (e2 * q).sum(-1) * inv
        hit = ok & (u >= 0) & (v >= 0) & (u + v <= 1) & (t > 1e-3) & (t < reach)
        out[i:i + step] = np.where(hit, t, np.inf).min(1)
    return out


def in_bore(points, pieces):
    """Mask of the `points` (k, 3) in the space a riding piece closes round, a tunnel's bore: one of the `pieces`
    [(m, 3, 3)] lies over and under the point (TUBE apart) and round it, within TUBE_REACH: along TUBE_SIDES of four
    horizontal lines through it on both sides, or, near an open end, along TUBE_RAYS of eight horizontal directions;
    and open along at least one of them (the inside of a closed block is no bore)."""
    mask = np.zeros(len(points), bool)
    up, down = np.array([0., 1., 0.]), np.array([0., -1., 0.])
    flat = [np.array([math.cos(a), 0., math.sin(a)]) for a in np.radians(np.arange(0, 360, 45))]
    for piece in pieces:
        t = piece.astype('f8'); lo, hi = t.min((0, 1)), t.max((0, 1))
        near = np.flatnonzero(((points > lo) & (points < hi)).all(1) & ~mask)
        if not len(near):
            continue
        y = points[near, 1]; between = grind.heights(t)               # cheap first: a face over and under at all
        near = near[between(points[near], y + 1e-3, y + TUBE_REACH) & between(points[near], y - TUBE_REACH, y - 1e-3)]
        if not len(near):
            continue
        c = points[near]
        over = ray_distances(c, up, t, TUBE_REACH); under = ray_distances(c, down, t, TUBE_REACH)
        maybe = np.isfinite(over) & np.isfinite(under) & (over + under > TUBE)
        if not maybe.any():
            continue
        c = c[maybe]
        hits = np.stack([np.isfinite(ray_distances(c, d, t, TUBE_REACH)) for d in flat], 1)
        # Open along some way (a tunnel's ends), not the inside of a closed block.
        closed = (((hits[:, :4] & hits[:, 4:]).sum(1) >= TUBE_SIDES) | (hits.sum(1) >= TUBE_RAYS)) & ~hits.all(1)
        mask[near[np.flatnonzero(maybe)[closed]]] = True
    return mask


def cell_keys(points, size):
    c = np.floor(points / size).astype('i8') + (1 << 20)
    return (c[:, 0] << 42) | (c[:, 1] << 21) | c[:, 2]


def tunnels(pieces, step=PROBE):
    """The `pieces` [(m, 3, 3)] that close round a bore somewhere, each with the points of a `step`-metre grid over it
    that lie in its bore (in_bore): [(piece, points)]."""
    found = []
    for piece in pieces:
        lo, hi = piece.min((0, 1)), piece.max((0, 1))
        axes = [np.arange(lo[k] + step / 2, hi[k], step) for k in range(3)]
        grid = np.stack(np.meshgrid(*axes, indexing='ij'), -1).reshape(-1, 3)
        inside = grid[in_bore(grid, [piece])] if len(grid) else grid
        if len(inside):
            found.append((piece, inside))
    return found


def inside_tubes(triangles, bores):
    """Mask of the `triangles` (n, 3, 3) reaching into a tunnel's bore (in_bore), `bores` as tunnels gives them: the
    centre, or for a face over LARGE across, any of SAMPLES points spread over it. Only the points within a grid step
    or so of the bore's own grid points are tested. The foundation blocks were made solid up to the top of the pieces
    over them: they filled the tunnel, and the rider met its solid end; long faces inside the block crossed it too."""
    mask = np.zeros(len(triangles), bool)
    for piece, inside in bores:
        lo, hi = piece.min((0, 1)), piece.max((0, 1))
        near = np.flatnonzero(((triangles.max(1) > lo) & (triangles.min(1) < hi)).all(1))
        if not len(near):
            continue
        t = triangles[near].astype('f8')
        large = np.flatnonzero(np.linalg.norm(t.max(1) - t.min(1), axis=1) > LARGE)
        points = np.concatenate([t.mean(1), np.einsum('sk,nkd->nsd', SAMPLES, t[large]).reshape(-1, 3)])
        owner = np.concatenate([np.arange(len(t)), np.repeat(large, len(SAMPLES))])
        offsets = np.stack(np.meshgrid(*[[-PROBE, 0., PROBE]] * 3, indexing='ij'), -1).reshape(-1, 3)
        around = np.unique(cell_keys((inside[:, None] + offsets).reshape(-1, 3), PROBE))
        close = np.isin(cell_keys(points, PROBE), around)
        hit = np.zeros(len(points), bool); hit[close] = in_bore(points[close], [piece])
        mask[near[owner[hit]]] = True
    return mask
