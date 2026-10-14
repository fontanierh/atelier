"""Crater Park's added riding pieces, shaped on the park's own surfaces (pure numpy, native frame: metres, y up).

Nothing that is ridden is moved, cut or covered: every piece fills space where there was no riding surface, and meets
the riding surfaces round it flush. The pieces are height fields over a CELL grid of the park seen from above:
- snake channels: the slots in the east bowls' floor fell 20 to 30 m to the hillside. Each now holds a concrete
  channel CHANNEL deep at its middle, its sides rising as a sine curve to meet the floor at both edges level with it;
- banks: a smooth surface spanning the hillside between two riding pieces, flush with both (a hip from the tower's
  channel down to the plaza terrace);
- caps and walls (solidify): a sheet's free edge ending in the air, a knife edge, gets a level cap and a wall under it.
"""
import numpy as np

CELL = .25          # metres between the height field's nodes
OPEN = 8.           # metres: a node whose highest surface lies this far under the region's floor is open (a slot)
RING = .55          # share of an open patch's rim that must be riding floor, for the patch to be filled
CHANNEL = 1.5       # metres: a snake channel's depth at its middle
BRIDGE = 2.          # metres: a strip across a slot this wide at most is a bridge the channel rises under
TAPER = 4.          # metres either side of a bridge over which a channel's depth eases to nothing
STEEPEST = .55      # a channel's depth at most this share of its half width (a narrow part is shallower)
REACH = 4.          # metres: the distances to a slot's edge are measured up to this far
OVERLAP = 2         # nodes a piece reaches under the floor round it, so no crack opens at the edge
RELAX = 600         # sweeps of the smoothing that carries the floor's height across a slot
GUESS = 2000        # fixed nodes at most that start the smoothing (relax)
UV_METRES = 9.      # metres per texture tile (the snake runs' concrete)
SNAKE_MATERIAL = 'material_006'     # the snake runs' concrete

# The regions whose open slots and holes are filled (snake_channels): a box (x0, z0, x1, z1), the height of its floor,
# how far under it a hole's top lies at least, and the channel's depth (metres).
SNAKES = {'east_bowls': ((1384., 958., 1468., 1140.), 0., OPEN, CHANNEL),
          'plaza_pockets': ((1186., 1002., 1262., 1158.), 6., 3., CHANNEL)}
# The banks: a box (x0, z0, x1, z1) over the open ground between the pieces they join.
BANKS = {'tower_plaza_hip': (1155., 1003., 1187., 1025.)}


def unit_normals(t):
    n = np.cross(t[:, 1] - t[:, 0], t[:, 2] - t[:, 0])
    return n / np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-12)


def top_heights(triangles, points, cell=2., pairs=2_000_000):
    """The highest of the faces `triangles` (m, 3, 3) over or under each point (k, 3), -inf where there is none. Faces
    seen edge-on from above (walls) are left out. The points go in batches of at most `pairs` point-face candidates."""
    lo_p, hi_p = points[:, [0, 2]].min(0), points[:, [0, 2]].max(0)
    s = triangles[((triangles[:, :, [0, 2]].max(1) >= lo_p) & (triangles[:, :, [0, 2]].min(1) <= hi_p)).all(1)].astype('f8')
    s = s[np.abs(unit_normals(s)[:, 1]) > .05]
    best = np.full(len(points), -np.inf)
    if not len(s):
        return best
    lo = np.floor(s.min(1)[:, [0, 2]] / cell).astype('i8'); hi = np.floor(s.max(1)[:, [0, 2]] / cell).astype('i8')
    size = hi - lo + 1; count = size.prod(1)
    owner = np.repeat(np.arange(len(s)), count)
    local = np.arange(count.sum()) - np.repeat(np.cumsum(count) - count, count)
    cells = lo[owner] + np.stack([local % size[owner, 0], local // size[owner, 0]], -1)
    keys = (cells[:, 0] + (1 << 20)) << 21 | (cells[:, 1] + (1 << 20))
    order = np.argsort(keys, kind='stable'); keys, owner = keys[order], owner[order]
    c = np.floor(points[:, [0, 2]] / cell).astype('i8'); k = (c[:, 0] + (1 << 20)) << 21 | (c[:, 1] + (1 << 20))
    first = np.searchsorted(keys, k, 'left'); total = np.cumsum(np.searchsorted(keys, k, 'right') - first)
    cuts = np.unique(np.concatenate([[0], np.searchsorted(total, np.arange(pairs, total[-1], pairs)), [len(points)]]))
    for i0, i1 in zip(cuts[:-1], cuts[1:]):
        p = points[i0:i1]
        start = first[i0:i1]; reps = np.diff(total[i0:i1], prepend=total[i0 - 1] if i0 else 0)
        which = np.repeat(np.arange(len(p)), reps)
        cand = owner[np.repeat(start, reps) + np.arange(reps.sum()) - np.repeat(np.cumsum(reps) - reps, reps)]
        q = p[which]; v = s[cand]
        d = (v[:, 1, 2] - v[:, 2, 2]) * (v[:, 0, 0] - v[:, 2, 0]) + (v[:, 2, 0] - v[:, 1, 0]) * (v[:, 0, 2] - v[:, 2, 2])
        ok = np.abs(d) > 1e-12; d = np.where(ok, d, 1.)
        l1 = ((v[:, 1, 2] - v[:, 2, 2]) * (q[:, 0] - v[:, 2, 0]) + (v[:, 2, 0] - v[:, 1, 0]) * (q[:, 2] - v[:, 2, 2])) / d
        l2 = ((v[:, 2, 2] - v[:, 0, 2]) * (q[:, 0] - v[:, 2, 0]) + (v[:, 0, 0] - v[:, 2, 0]) * (q[:, 2] - v[:, 2, 2])) / d
        l3 = 1 - l1 - l2
        y = l1 * v[:, 0, 1] + l2 * v[:, 1, 1] + l3 * v[:, 2, 1]
        hit = ok & (l1 >= -1e-9) & (l2 >= -1e-9) & (l3 >= -1e-9)
        part = np.full(len(p), -np.inf); np.maximum.at(part, which[hit], y[hit])
        best[i0:i1] = part
    return best


def shift(a, dj, di, fill):
    """`a` (rows, cols) moved by (dj, di) nodes, `fill` where it moved in from outside."""
    out = np.full_like(a, fill)
    rows, cols = a.shape
    out[max(dj, 0):rows + min(dj, 0), max(di, 0):cols + min(di, 0)] = a[max(-dj, 0):rows + min(-dj, 0), max(-di, 0):cols + min(-di, 0)]
    return out


def grow(mask, steps, diagonal=False):
    """`mask` grown by `steps` nodes (4-connected, or 8 with `diagonal`)."""
    moves = ((1, 0), (-1, 0), (0, 1), (0, -1)) + (((1, 1), (1, -1), (-1, 1), (-1, -1)) if diagonal else ())
    for _ in range(steps):
        out = mask.copy()
        for dj, di in moves:
            out |= shift(mask, dj, di, False)
        mask = out
    return mask


def shrink(mask, steps):
    return ~grow(~mask, steps)


def components(mask):
    """Labels (rows, cols) of the 4-connected patches of `mask`, -1 outside it."""
    label = np.where(mask, np.arange(mask.size).reshape(mask.shape), -1)
    big = mask.size + 1
    while True:
        low = np.where(mask, label, big)
        for dj, di in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            low = np.minimum(low, np.where(mask, shift(np.where(mask, label, big), dj, di, big), big))
        # Pointer jumping: each node takes its label's label, so long serpentines settle in a few dozen sweeps.
        flat = low.ravel(); inside = mask.ravel()
        flat[inside] = flat[flat[inside]]
        new = np.where(mask, flat.reshape(mask.shape), -1)
        if np.array_equal(new, label):
            return label
        label = new


def distance_out(region, reach, cell):
    """Each node's distance (metres) to the nearest node outside `region`, up to `reach`."""
    best = np.where(region, reach, 0.)
    n = int(np.ceil(reach / cell))
    for dj in range(-n, n + 1):
        for di in range(-n, n + 1):
            r = np.hypot(dj, di) * cell
            if r == 0 or r >= reach:
                continue
            outside = ~shift(region, dj, di, True)
            best = np.where(region & outside, np.minimum(best, r), best)
    return best


def max_near(a, radius, cell, where):
    """The largest of `a` within `radius` metres of each node, over the nodes `where`."""
    best = np.where(where, a, -np.inf)
    n = int(np.ceil(radius / cell)); out = best.copy()
    for dj in range(-n, n + 1):
        for di in range(-n, n + 1):
            if np.hypot(dj, di) * cell <= radius:
                out = np.maximum(out, shift(best, dj, di, -np.inf))
    return out


def relax(height, fixed, free, sweeps=RELAX):
    """`height` carried smoothly across the `free` nodes from the `fixed` ones (a membrane: each free node the mean of
    its free or fixed neighbours)."""
    h = np.where(fixed | free, height, 0.).astype('f8')
    # Started from the fixed heights spread by inverse distance: the sweeps then only smooth it, even far from them.
    fj, fi = np.nonzero(fixed); keep = slice(None, None, max(1, len(fj) // GUESS))
    fj, fi, fh = fj[keep], fi[keep], height[fixed][keep]
    sj, si = np.nonzero(free)
    for k in range(0, len(sj), 4096):
        w = 1 / np.maximum((sj[k:k + 4096, None] - fj) ** 2 + (si[k:k + 4096, None] - fi) ** 2, 1e-9)
        h[sj[k:k + 4096], si[k:k + 4096]] = (w * fh).sum(1) / w.sum(1)
    use = fixed | free
    for _ in range(sweeps):
        total = np.zeros_like(h); count = np.zeros_like(h)
        for dj, di in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            m = shift(use, dj, di, False)
            total += np.where(m, shift(h, dj, di, 0.), 0.); count += m
        h = np.where(free & (count > 0), total / np.maximum(count, 1), h)
    return h


def grid_mesh(x0, z0, cell, height, nodes):
    """The height field over the squares whose four corner `nodes` are set: (vertices (k, 3), faces (n, 3)), each
    square split along the diagonal across which its corners' heights differ least."""
    rows, cols = nodes.shape
    index = np.full(nodes.shape, -1, 'i8'); index[nodes] = np.arange(nodes.sum())
    jj, ii = np.nonzero(nodes)
    vertices = np.stack([x0 + ii * cell, height[jj, ii], z0 + jj * cell], 1)
    a = index[:-1, :-1]; b = index[:-1, 1:]; c = index[1:, 1:]; d = index[1:, :-1]
    square = (a >= 0) & (b >= 0) & (c >= 0) & (d >= 0)
    a, b, c, d = a[square], b[square], c[square], d[square]
    h = vertices[:, 1]
    flip = np.abs(h[a] - h[c]) > np.abs(h[b] - h[d])
    # Wound to face up (native y up): a (x, z), b (x+1, z), c (x+1, z+1), d (x, z+1) are counter-clockwise seen from
    # below, so (a, c, b) faces up.
    first = np.where(flip[:, None], np.stack([a, d, b], 1), np.stack([a, c, b], 1))
    second = np.where(flip[:, None], np.stack([b, d, c], 1), np.stack([a, d, c], 1))
    return vertices, np.concatenate([first, second])


def snake_channels(riding, solid, box, floor, open_=OPEN, channel=CHANNEL, cell=CELL):
    """The snake channels in the open slots of `box` (x0, z0, x1, z1), whose floor lies near `floor`, a slot's top
    `open_` under it at least, `channel` deep: (vertices, faces, uvs), or None. A small hole makes a pocket. `riding` and
    `solid` are the park's riding and other faces (m, 3, 3)."""
    x0, z0, x1, z1 = box
    xs = np.arange(x0, x1 + cell / 2, cell); zs = np.arange(z0, z1 + cell / 2, cell)
    gx, gz = np.meshgrid(xs, zs)
    points = np.stack([gx.ravel(), np.zeros(gx.size), gz.ravel()], 1)
    ride = top_heights(riding, points).reshape(gx.shape)
    every = np.maximum(ride, top_heights(solid, points).reshape(gx.shape))
    is_floor = np.isfinite(ride) & (ride >= every - .01) & (np.abs(ride - floor) < OPEN / 2)
    is_ride = np.isfinite(ride) & (ride >= every - .01)
    deep = (every < floor - open_) & ~is_ride                   # a hole: no riding face is the top
    label = components(deep)
    slot = np.zeros_like(deep)
    for k in np.unique(label[label >= 0]):
        patch = label == k
        if patch[0].any() or patch[-1].any() or patch[:, 0].any() or patch[:, -1].any():
            continue                                            # it runs out of the box: not a slot in the floor
        rim = grow(patch, 1) & ~patch
        if is_floor[rim].mean() >= RING:
            slot |= patch
    if not slot.any():
        return None
    # A bridge across a slot (a strip at floor height, not the floor, BRIDGE wide at most) stays: the channel rises under it, a roller
    # TAPER long either side, and meets it flush.
    closed = shrink(grow(slot, int(BRIDGE / 2 / cell) + 1), int(BRIDGE / 2 / cell) + 1) | slot
    bridge = closed & ~slot & ~is_floor & np.isfinite(every) & (np.abs(every - floor) < open_ / 2)
    slot |= bridge
    fixed = (grow(slot, 1) & ~slot & is_floor) | bridge
    level = np.where(bridge, every, np.where(is_floor, ride, 0.))
    rim = relax(level, fixed, slot & ~bridge)
    d = distance_out(slot, REACH, cell)
    half = np.maximum(max_near(d, REACH * .75, cell, slot), d)
    depth = np.minimum(channel, STEEPEST * half)
    if bridge.any():
        to_bridge = distance_out(~bridge, TAPER, cell)
        depth = depth * np.sin(np.pi / 2 * np.clip(to_bridge / TAPER, 0., 1.)) ** 2
    u = np.clip(d / np.maximum(half, 1e-6), 0., 1.)
    height = np.where(slot, rim - depth * np.sin(np.pi / 2 * u) ** 2, ride)
    # The nodes round each slot, under the floor, carry the floor's own height: the channel's edge meets it flush.
    near = slot.copy()
    for _ in range(OVERLAP):
        near = grow(near, 1, True) & (slot | is_floor)
    vertices, faces = grid_mesh(x0, z0, cell, height, near)
    uvs = vertices[:, [0, 2]] / UV_METRES
    return vertices.astype('f4'), faces, uvs.astype('f4')




def bank(riding, solid, box, cell=CELL):
    """A bank spanning the open ground of `box` (x0, z0, x1, z1) between the riding surfaces round it: where no
    riding face is the top, a smooth surface carries their edges' heights across (relax) and meets them flush. Its
    sides along the box's edges hang free (solidify closes them). (vertices, faces, uvs) or None."""
    x0, z0, x1, z1 = box
    xs = np.arange(x0, x1 + cell / 2, cell); zs = np.arange(z0, z1 + cell / 2, cell)
    gx, gz = np.meshgrid(xs, zs)
    points = np.stack([gx.ravel(), np.zeros(gx.size), gz.ravel()], 1)
    ride = top_heights(riding, points).reshape(gx.shape)
    every = np.maximum(ride, top_heights(solid, points).reshape(gx.shape))
    is_ride = np.isfinite(ride) & (ride >= every - .01)
    open_ = ~is_ride
    fixed = grow(open_, 1) & is_ride
    if not open_.any() or not fixed.any():
        return None
    height = np.where(open_, relax(np.where(is_ride, ride, 0.), fixed, open_), ride)
    near = open_.copy()
    for _ in range(OVERLAP):
        near = grow(near, 1, True) & (open_ | is_ride)
    vertices, faces = grid_mesh(x0, z0, cell, height, near)
    return vertices.astype('f4'), faces, (vertices[:, [0, 2]] / UV_METRES).astype('f4')


def tile_metres(positions, uvs, triangles, default=UV_METRES):
    """Metres per texture tile on a piece: its edges' median length over their length in UV."""
    p = positions[triangles].astype('f8'); u = uvs[triangles].astype('f8')
    world = np.linalg.norm(p[:, 1] - p[:, 0], axis=1); texture = np.linalg.norm(u[:, 1] - u[:, 0], axis=1)
    use = (world > .2) & (texture > 1e-6)
    return float(np.median(world[use] / texture[use])) if use.sum() > 10 else default


THICK = .35         # metres: a sheet's free edge is capped this wide, so the piece reads as solid concrete
CLEAR_EDGE = .3     # metres up or down from a free edge where nothing continues past it (it ends in the air)
LOWEST = .15        # metres: a free edge this close over what lies under it rests on it (no wall to build)
FAR_DOWN = 30.      # metres a wall goes down at most, where nothing lies under it
BURY = .1           # metres a wall goes on under the ground it stands on
SHEET = .4          # metres either side of a sheet's face that are open air


def free_edges(triangles):
    """The edges of the faces `triangles` (n, 3, 3) that only one face uses (welded at a millimetre): (a, b, face)."""
    a = np.concatenate([triangles[:, i] for i in range(3)]); b = np.concatenate([triangles[:, (i + 1) % 3] for i in range(3)])
    face = np.tile(np.arange(len(triangles)), 3)
    _, ids = np.unique(np.round(np.concatenate([a, b]) * 1000).astype('i8'), axis=0, return_inverse=True)
    ids = ids.ravel(); ia, ib = ids[:len(a)], ids[len(a):]
    _, inverse, count = np.unique(np.stack([np.minimum(ia, ib), np.maximum(ia, ib)], 1), axis=0,
                                  return_inverse=True, return_counts=True)
    keep = (count[inverse.ravel()] == 1) & (ia != ib)
    return a[keep], b[keep], face[keep]


def local_centres(points, centres, radius):
    """The mean of the `centres` (m, 3) within about `radius` of each point (k, 3) (a cube of cells), nan where none."""
    cell = radius
    key = lambda c: (c[:, 0] + (1 << 20)) << 42 | (c[:, 1] + (1 << 20)) << 21 | (c[:, 2] + (1 << 20))
    cc = np.floor(centres / cell).astype('i8'); keys = key(cc); order = np.argsort(keys); keys = keys[order]
    sums = np.zeros((len(points), 3)); counts = np.zeros(len(points))
    pc = np.floor(points / cell).astype('i8')
    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            for dz in (-1, 0, 1):
                k = key(pc + [dx, dy, dz]); lo = np.searchsorted(keys, k, 'left'); hi = np.searchsorted(keys, k, 'right')
                reps = hi - lo; which = np.repeat(np.arange(len(points)), reps)
                idx = order[np.repeat(lo, reps) + np.arange(reps.sum()) - np.repeat(np.cumsum(reps) - reps, reps)]
                np.add.at(sums, which, centres[idx]); np.add.at(counts, which, 1)
    return np.where(counts[:, None] > 0, sums / np.maximum(counts, 1)[:, None], np.nan)


def solidify(piece, heights, around, metres=UV_METRES):
    """Caps and walls that close the free edges of the riding piece `piece` (n, 3, 3) where it ends in the air, a
    sheet with no thickness (a half-pipe's flank, the back of its wall): along each such edge a level cap THICK wide on
    the side away from the piece, then a wall from the cap's far edge down to whatever lies under it. `heights` is
    grind.heights over the whole park and `around` its faces (m, 3, 3); `metres` per texture tile. A sheet is open on
    both sides: from its face just inside the edge, nothing lies within SHEET either way (a trim on a wall's top, a
    pool's rim or a ramp on its block has the solid behind it). Returns (vertices (k, 3), faces (m, 3), uvs (k, 2)) or
    None: the caps' corners and the walls' are apart, so the edge between them stays sharp."""
    t = piece.astype('f8')
    a, b, face = free_edges(t)
    if not len(a):
        return None
    mid = (a + b) / 2
    local = local_centres(mid, t.mean(1), 1.5)
    out = (mid - local) * [1, 0, 1]
    along = (b - a) * [1, 0, 1]; flat = np.linalg.norm(along, axis=1)
    lengthwise = flat > .2 * np.linalg.norm(b - a, axis=1)
    u = along / np.maximum(flat, 1e-9)[:, None]
    out = np.where(lengthwise[:, None], out - (out * u).sum(1, keepdims=True) * u, out)
    size = np.linalg.norm(out, axis=1); ok = np.isfinite(size) & (size > .05)
    out = np.where(ok[:, None], out / np.maximum(size, 1e-9)[:, None], 0.)
    y = mid[:, 1]; probe = mid + .1 * out
    ends_in_air = ok & ~heights(probe, y - CLEAR_EDGE, y + CLEAR_EDGE)
    a, b, out, face, mid = a[ends_in_air], b[ends_in_air], out[ends_in_air], face[ends_in_air], mid[ends_in_air]
    if not len(a):
        return None
    lo, hi = t.min((0, 1)) - 1, t.max((0, 1)) + 1
    near = around[((around.max(1) > lo) & (around.min(1) < hi)).all(1)].astype('f8')
    inward = t[face].mean(1) - mid; inward /= np.maximum(np.linalg.norm(inward, axis=1, keepdims=True), 1e-9)
    start = mid + .1 * inward; normal = unit_normals(t[face])
    sheet = np.ones(len(a), bool)
    # In batches of neighbouring edges, each against the faces round the batch only.
    cells = np.floor(start / 2.).astype('i8'); order = np.lexsort((cells[:, 2], cells[:, 1], cells[:, 0]))
    for k in range(0, len(order), 64):
        batch = order[k:k + 64]
        b_lo, b_hi = start[batch].min(0) - SHEET, start[batch].max(0) + SHEET
        here = near[((near.max(1) > b_lo) & (near.min(1) < b_hi)).all(1)]
        for sign in (1., -1.):
            sheet[batch] &= ~np.isfinite(rays(start[batch], sign * normal[batch], here, SHEET))
    a, b, out = a[sheet], b[sheet], out[sheet]
    if not len(a):
        return None
    # One far point per corner, shared by the edges that meet there: the caps join without a crack.
    _, ids = np.unique(np.round(np.concatenate([a, b]) * 1000).astype('i8'), axis=0, return_inverse=True)
    ids = ids.ravel(); n = ids.max() + 1
    corner = np.zeros((n, 3)); corner[ids] = np.concatenate([a, b])
    push = np.zeros((n, 3)); np.add.at(push, ids, np.concatenate([out, out]))
    push /= np.maximum(np.linalg.norm(push, axis=1, keepdims=True), 1e-9)
    far = corner + THICK * push
    ground = heights(far, far[:, 1] - FAR_DOWN, far[:, 1] - CLEAR_EDGE, top=True)
    bottom = np.where(np.isfinite(ground), ground, far[:, 1] - FAR_DOWN) - BURY
    low = np.stack([far[:, 0], bottom, far[:, 2]], 1)
    # Vertices: the caps' (corner, far), then the walls' (far, low).
    vertices = np.concatenate([corner, far, far, low])
    ia, ib = ids[:len(a)], ids[len(a):]
    caps = np.concatenate([np.stack([ia, ib, n + ib], 1), np.stack([ia, n + ib, n + ia], 1)])
    walls = 2 * n + np.concatenate([np.stack([ia, ib, n + ib], 1), np.stack([ia, n + ib, n + ia], 1)])
    faces = np.concatenate([caps, walls]); kind = np.repeat([0, 1], [len(caps), len(walls)])
    # Caps face up, walls face out, away from the piece.
    tri = vertices[faces]; normal = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
    outward = np.tile(np.concatenate([out, out]), (2, 1))
    facing = np.where(kind == 0, normal[:, 1], (normal * outward).sum(1))
    faces[facing < 0] = faces[facing < 0][:, [0, 2, 1]]
    # Caps take the texture from above, walls along their face.
    p = np.concatenate([push, push])
    wall_u = vertices[2 * n:, 0] * p[:, 2] - vertices[2 * n:, 2] * p[:, 0]
    uvs = np.concatenate([vertices[:2 * n][:, [0, 2]], np.stack([wall_u, vertices[2 * n:, 1]], 1)]) / metres
    keep = np.linalg.norm(normal, axis=1) > 1e-8
    return vertices, faces[keep], uvs


COPING_RADIUS = .035    # metres: a steel coping tube's radius (7 cm across, as a skatepark's pipe coping)
COPING_PROUD = .012     # metres the tube's top stands over the deck
COPING_SIDES = 8
COPING_MATERIAL = 'coping_steel'    # import_craterpark.py makes it, a steel parent


def coping(lines, radius=COPING_RADIUS, proud=COPING_PROUD, sides=COPING_SIDES):
    """A steel coping tube along each grind line (native points (k, 3)), drawn only: its axis `radius - proud` under
    the line, so its top stands `proud` over the deck. (vertices, faces, uvs) or None; u runs along, v round."""
    vertices, faces, uvs = [], [], []
    count = 0
    angle = 2 * np.pi * np.arange(sides + 1) / sides                 # the seam's ring twice, for its UVs
    for line in lines:
        p = np.asarray(line, 'f8')
        if len(p) < 2:
            continue
        closed = len(p) > 3 and np.linalg.norm(p[0] - p[-1]) < .01
        tangent = np.gradient(p, axis=0)
        if closed:
            tangent[0] = tangent[-1] = p[1] - p[-2]
        tangent /= np.maximum(np.linalg.norm(tangent, axis=1, keepdims=True), 1e-9)
        side = np.cross(tangent, [0., 1., 0.])
        side /= np.maximum(np.linalg.norm(side, axis=1, keepdims=True), 1e-9)
        up = np.cross(side, tangent)
        centre = p - (radius - proud) * up
        ring = (centre[:, None] + radius * (np.cos(angle)[None, :, None] * side[:, None]
                                            + np.sin(angle)[None, :, None] * up[:, None]))       # (k, sides + 1, 3)
        k = len(p)
        along = np.concatenate([[0.], np.cumsum(np.linalg.norm(np.diff(p, axis=0), axis=1))])
        uv = np.stack(np.broadcast_arrays(along[:, None] / UV_METRES, (angle / (2 * np.pi))[None, :]), -1)
        i, j = np.meshgrid(np.arange(k - 1), np.arange(sides), indexing='ij')
        a = count + i * (sides + 1) + j; b = a + 1; c = a + sides + 1; d = c + 1
        # (a, c, b) faces out of the tube: along the line times round it is the ring's own direction.
        faces.append(np.concatenate([np.stack([a, c, b], -1).reshape(-1, 3), np.stack([b, c, d], -1).reshape(-1, 3)]))
        vertices.append(ring.reshape(-1, 3)); uvs.append(uv.reshape(-1, 2))
        count += k * (sides + 1)
    if not faces:
        return None
    return np.concatenate(vertices).astype('f4'), np.concatenate(faces), np.concatenate(uvs).astype('f4')


def rays(origins, directions, triangles, reach, pairs=2_000_000):
    """The distance from each of the `origins` (k, 3) along its unit `directions` (k, 3) to the nearest of the
    `triangles` (m, 3, 3), inf where none lies within `reach` (past a millimetre: not the face it starts on)."""
    out = np.full(len(origins), np.inf)
    if not len(triangles) or not len(origins):
        return out
    e1 = triangles[:, 1] - triangles[:, 0]; e2 = triangles[:, 2] - triangles[:, 0]
    step = max(1, pairs // len(triangles))
    for i in range(0, len(origins), step):
        o = origins[i:i + step, None]; d = directions[i:i + step, None]
        p = np.cross(d, e2[None]); det = (e1[None] * p).sum(-1)
        ok = np.abs(det) > 1e-12; inv = 1 / np.where(ok, det, 1.)
        s = o - triangles[None, :, 0]
        u = (s * p).sum(-1) * inv; q = np.cross(s, e1[None]); v = (q * d).sum(-1) * inv; t = (e2[None] * q).sum(-1) * inv
        hit = ok & (u >= 0) & (v >= 0) & (u + v <= 1) & (t > 1e-3) & (t < reach)
        out[i:i + step] = np.where(hit, t, np.inf).min(1)
    return out
