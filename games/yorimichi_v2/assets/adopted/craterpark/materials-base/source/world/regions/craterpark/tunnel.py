"""Crater Park's tunnels kept open (pure numpy, native frame: metres, y up).

The foundation blocks under the riding pieces were made solid up to the top of the pieces over them, so the one
round tunnel was filled: its bore held the block's solid, and the rider met its flat end. carve cuts the faces
reaching into a bore (of the pieces tunnels finds) out of the render and the collision.
"""
import hashlib
import math

import numpy as np

from craterpark import grind

TUBE = 2.               # metres from a tunnel's floor to its roof at least
TUBE_REACH = 12.        # metres to a tunnel's wall at most, every way
TUBE_SIDES = 2          # horizontal lines through a point in a tunnel meeting its wall both ways (its ends are open)
TUBE_RAYS = 5           # of eight horizontal directions from a point near a tunnel's open end, meeting its wall
PROBE = 2.              # metres between the points that find which pieces close round a bore (tunnels)
COVERED = 3             # of eight horizontal directions from a bore's axis meeting a wall, for its prism to go on
EXTEND = 40.            # metres a bore's prism is carried on along its axis at most, past its grid (bore_prism)
VOXEL = .5              # metres between the nodes of the grid that says which points lie in a bore (bore_grid)
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


_GRIDS = {}


def bore_grid(piece, inside, cell=VOXEL):
    """in_bore over the grid of nodes `cell` apart round the points `inside` a bore, PROBE wider: (origin, cell, mask
    (a, b, c), its summed volume). Kept for the next mesh: a build carves each of its meshes in turn."""
    key = hashlib.sha1(piece.tobytes() + inside.tobytes() + repr(cell).encode()).hexdigest()
    if key not in _GRIDS:
        lo = inside.min(0) - PROBE
        n = np.floor((inside.max(0) + PROBE - lo) / cell).astype('i8') + 1
        nodes = lo + np.stack(np.meshgrid(*map(np.arange, n), indexing='ij'), -1).reshape(-1, 3) * cell
        mask = in_bore(nodes, [piece]).reshape(tuple(n))
        total = np.zeros(tuple(n + 1), 'i8'); total[1:, 1:, 1:] = mask.cumsum(0).cumsum(1).cumsum(2)
        _GRIDS[key] = (lo, cell, mask, total)
    return _GRIDS[key]


def hull(points):
    """The convex hull of the 2-D `points` (k, 2), counter-clockwise (monotone chain)."""
    p = np.unique(np.round(points, 6), axis=0)
    if len(p) < 3:
        return p
    cross = lambda o, a, b: (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])
    lower, upper = [], []
    for q in p:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], q) <= 0:
            lower.pop()
        lower.append(q)
    for q in p[::-1]:
        while len(upper) >= 2 and cross(upper[-2], upper[-1], q) <= 0:
            upper.pop()
        upper.append(q)
    return np.asarray(lower[:-1] + upper[:-1])


def bore_prism(grid, around=None, step=VOXEL, reach=EXTEND):
    """A straight bore as a convex prism: the hull of its grid's nodes across its axis (horizontal, their main
    direction), extruded between its ends, each face half a node out; with `around` (m, 3, 3), each end carried on
    along the axis to the mouth, while those faces together still lie over and under the hull's middle with COVERED of
    eight horizontal directions walled, where one piece alone does not close round it (a tunnel's roof one piece, a
    wall another; its walls open near the mouth). (normals (m, 3), offsets (m,)): a point x lies in it
    when normals @ x <= offsets for every face."""
    lo, cell, mask, _ = grid
    p = lo + np.argwhere(mask) * cell
    centre = p[:, [0, 2]].mean(0)
    axis = np.linalg.svd(p[:, [0, 2]] - centre, full_matrices=False)[2][0]
    side = np.array([-axis[1], axis[0]])
    along = (p[:, [0, 2]] - centre) @ axis
    outline = hull(np.stack([(p[:, [0, 2]] - centre) @ side, p[:, 1]], 1))
    a3 = np.array([axis[0], 0., axis[1]]); s3 = np.array([side[0], 0., side[1]]); c3 = np.array([centre[0], 0., centre[1]])
    ends = [along.max() + cell / 2, -along.min() + cell / 2]
    if around is not None:
        middle = c3 + outline[:, 0].mean() * s3 + np.array([0., outline[:, 1].mean(), 0.])
        up, down = np.array([0., 1., 0.]), np.array([0., -1., 0.])
        flat = [np.array([math.cos(a), 0., math.sin(a)]) for a in np.radians(np.arange(0, 360, 45))]
        for k, sign in enumerate((1., -1.)):
            start = ends[k]
            while ends[k] < start + reach:
                point = (middle + sign * (ends[k] + step) * a3)[None]
                near = around[((around.max(1) > point - TUBE_REACH) & (around.min(1) < point + TUBE_REACH)).all(1)]
                if not len(near):
                    break
                over, under = ray_distances(point, up, near, TUBE_REACH)[0], ray_distances(point, down, near, TUBE_REACH)[0]
                walls = sum(np.isfinite(ray_distances(point, d, near, TUBE_REACH)[0]) for d in flat)
                if not (np.isfinite(over) and np.isfinite(under) and walls >= COVERED):   # its roof ends: the mouth
                    break
                ends[k] += step
    normals = [a3, -a3]; offsets = [ends[0] + a3 @ c3, ends[1] - a3 @ c3]
    for k in range(len(outline)):
        (u0, y0), (u1, y1) = outline[k], outline[(k + 1) % len(outline)]
        n2 = np.array([y1 - y0, -(u1 - u0)]); n2 /= max(np.linalg.norm(n2), 1e-12)      # outward (counter-clockwise)
        normal = n2[0] * s3 + n2[1] * np.array([0., 1., 0.])
        normals.append(normal); offsets.append(n2 @ np.array([u0, y0]) + cell / 2 + n2[0] * (s3 @ c3))
    return np.asarray(normals), np.asarray(offsets)


def clip_out(corners, normals, offsets):
    """The parts of the triangle `corners` (3, 3) outside the convex prism (normals, offsets), as barycentric triangles
    (m, 3, 3) on it: the polygon left inside every face so far is cut by the next, and what lies past it kept."""
    keep = []
    polygon = [(corners[i], np.eye(3)[i]) for i in range(3)]
    for n, d in zip(normals, offsets):
        inside, outside = [], []
        for k in range(len(polygon)):
            (p0, b0), (p1, b1) = polygon[k], polygon[(k + 1) % len(polygon)]
            d0, d1 = n @ p0 - d, n @ p1 - d
            (inside if d0 <= 0 else outside).append((p0, b0))
            if (d0 < 0 < d1) or (d1 < 0 < d0):
                t = d0 / (d0 - d1); q = (p0 + t * (p1 - p0), b0 + t * (b1 - b0))
                inside.append(q); outside.append(q)
        if len(outside) >= 3:
            keep += [(outside[0][1], outside[i][1], outside[i + 1][1]) for i in range(1, len(outside) - 1)]
        polygon = inside
        if len(polygon) < 3:
            break
    return np.asarray(keep).reshape(-1, 3, 3)


def bore_prisms(bores):
    """Each of the `bores` (tunnels) as a convex prism (bore_prism), from the grid of its piece round it, the bores'
    pieces together carrying it on to its mouths; (None, None) where its grid holds no node."""
    around = np.concatenate([piece for piece, _ in bores]).astype('f8') if bores else None
    out = []
    for piece, inside in bores:
        lo, hi = inside.min(0) - PROBE - TUBE_REACH, inside.max(0) + PROBE + TUBE_REACH
        grid = bore_grid(piece[((piece.max(1) > lo) & (piece.min(1) < hi)).all(1)], inside)
        out.append(bore_prism(grid, around) if grid[2].any() else (None, None))
    return out


def carve(triangles, bores):
    """The `triangles` (n, 3, 3) cut out of the tunnels' bores, `bores` as tunnels gives them: each bore taken as a
    convex prism (bore_prism), a face wholly inside it is left out, and a face crossing its side is clipped exactly,
    its parts outside kept, so a block's wall keeps its solid round the portal and a long face crossing the bore keeps
    its ends. Returns (cut, parent, corners): the mask of the faces cut, and for each kept part its face's index and its
    corners' barycentric coordinates on that face (m, 3, 3)."""
    cut = np.zeros(len(triangles), bool); parents, corners = [], []
    done = 0
    for normals, offsets in bore_prisms(bores):
        if normals is None:
            continue
        near = np.flatnonzero(~cut)
        side = np.einsum('mk,fck->fcm', normals, triangles[near].astype('f8')) - offsets   # (faces, corners, prism faces)
        apart = (side >= 0).all(1).any(1)                                 # all corners past one face: clear of it
        near, side, apart = near[~apart], side[~apart], apart[~apart]
        t = triangles[near].astype('f8')
        whole = (side <= 0).all((1, 2))                                   # all corners inside every face
        cut[near[whole]] = True
        for f in np.flatnonzero(~apart & ~whole):
            parts = clip_out(t[f], normals, offsets)
            # a barycentric triangle's share of its face is its cross product's sum over three: all of it, only touching
            share = np.abs(np.cross(parts[:, 1] - parts[:, 0], parts[:, 2] - parts[:, 0]).sum(1)).sum() / 3 if len(parts) else 0.
            if share > 1 - 1e-9:
                continue
            cut[near[f]] = True
            if len(parts):
                parents.append(np.full(len(parts), near[f])); corners.append(parts)
        # The parts an earlier bore left, cut by this one too (two bores meet at a tunnel's bend or its mouth).
        if done:
            parent, corner = np.concatenate(parents[:done]), np.concatenate(corners[:done])
            p = np.einsum('mij,mjd->mid', corner, triangles[parent].astype('f8'))
            side = np.einsum('mk,fck->fcm', normals, p) - offsets
            gone = (side <= 0).all((1, 2)); touching = ~(side >= 0).all(1).any(1) & ~gone
            keep_p, keep_c = [parent[~gone & ~touching]], [corner[~gone & ~touching]]
            for f in np.flatnonzero(touching):
                sub = clip_out(p[f], normals, offsets)
                share = np.abs(np.cross(sub[:, 1] - sub[:, 0], sub[:, 2] - sub[:, 0]).sum(1)).sum() / 3 if len(sub) else 0.
                if share > 1 - 1e-9:
                    sub = np.eye(3)[None]
                keep_p.append(np.full(len(sub), parent[f])); keep_c.append(np.einsum('mij,jk->mik', sub, corner[f]))
            parents[:done], corners[:done] = [np.concatenate(keep_p)], [np.concatenate(keep_c).reshape(-1, 3, 3)]
        done = len(parents)
    if not parents:
        return cut, np.zeros(0, 'i8'), np.zeros((0, 3, 3))
    return cut, np.concatenate(parents), np.concatenate(corners)
