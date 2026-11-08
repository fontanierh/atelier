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
WALL_LOW, WALL_HIGH = .9, 5.   # metres a riding deck stands over the floor, for a transition at its wall's foot
RADIUS = (2.5, 3.5) # metres: a transition's radius, the wall's height within these
RAISED = .005       # metres: a floor node raised less is left as it is
LIP = .5            # metres round a bank's edge node within which it meets the piece's highest point (its lip)
RAISED_RIM = .25    # metres a hole's rim stands over the floor round it, for it to be a planter (a flat bed)
BED = .45           # metres a planter's bed lies under its cap
TRANSITION = 1.75   # metres a channel or pocket takes to reach its depth; wider, it has a flat bottom
WIDE = 2.           # metres across a deck at least, for a transition at its wall's foot
CLEAR_NARROW, EASE = .3, 1.5  # metres a transition keeps off a narrower piece, and over which it eases down
LIFTED = .02        # metres off the floor's level: a triangle with a corner this far is the curves' concrete
SKIRT_STEEPEST = .7 # a triangle's normal y at least (45 degrees), for the skirt: a paved slope is, a wall is not
FEET_METRES = 4.    # metres per texture tile the skirt's UVs are made at (build.py rescales them to its floor's)
BRIDGE = 2.          # metres: a strip across a slot this wide at most is a bridge the channel rises under
TAPER = 4.          # metres either side of a bridge over which a channel's depth eases to nothing
STEEPEST = .55      # a channel's depth at most this share of its half width (a narrow part is shallower)
REACH = 4.          # metres: the distances to a slot's edge are measured up to this far
OUTLINE = 3         # sweeps that smooth an added piece's outline (grid_mesh): its grid staircase made a row of slats
OVERLAP = 2         # nodes a piece reaches under the floor round it, so no crack opens at the edge
RELAX = 600         # sweeps of the smoothing that carries the floor's height across a slot
COARSE = 16         # nodes across at least, for relax to start from a grid half as fine
GUESS = 2000        # fixed nodes at most that start the smoothing (relax)
UV_METRES = 9.      # metres per texture tile (the snake runs' concrete)
SNAKE_MATERIAL = 'material_010'     # seamless concrete ('concrete'): 'concrete_edge' drew a dark band every tile

# The regions whose open slots and holes are filled (snake_channels): a box (x0, z0, x1, z1), the height of its floor,
# how far under it a hole's top lies at least, the channel's depth (metres; 0 fills a slot flush), whether its deck
# walls get transitions at their foot, and the floor's material (on the flat skirt round the curves).
SNAKES = {'east_bowls': ((1384., 958., 1468., 1140.), 0., OPEN, 0., True, 'material_004'),   # one curve floor to wall
          'plaza_pockets': ((1186., 1002., 1262., 1158.), 6., 3., CHANNEL, False, 'material_003')}  # the flagstones
# The banks: a box (x0, z0, x1, z1) over the open ground between the pieces they join, the joins (bank) or None, and
# the landing shape (bank) or None.
# The kickers: a box over the floor in front of a low wall, the side the wall is on, and whether it is a spine (kicker).
KICKERS = {'plaza_parapet': ((1184.5, 1009.5, 1189.5, 1014.5), 'x-', False)}   # the hip's foot, onto the terrace
KICK = .3           # metres over the floor: a kicker's wall top, at least
BANKS = {'tower_plaza_hip': ((1155., 1003., 1187., 1025.), None, 2.5),   # a hip: off the channel's coping at 35 deg
         # The banked curve ends in a quarter (-14.6 m) 2.5 m short of the peanut bowl's rim (-14.1 m): a deck across
         # makes a spine, over into the bowl, where the curve stopped dead.
         'curve_to_peanut': ((1232.5, 952., 1239., 967.), [((1230., 950., 1242., 969.), -15.5, -13.5)], None),
         # From the south-west bowl's rim deck (11 m) down to the banked curve's outer lip (9.5 m), beside the
         # tunnel strip: the line's way back towards the drop-in.
         'bowl_rim_to_curve': ((1139., 903., 1149.5, 969.), [((1136., 897., 1151., 906.), 10., 12.),
                                                            ((1139., 955., 1151., 972.), 7., 10.5)], None)}
# The snake runs: a centreline [(x, z) or (x, y, z)], the floor's width, the walls' height, their radius, and whether
# it is laid on the path under it (snake_run).
SNAKE_RUNS = {
    # The narrow path from the banked curve's foot to the blue pool, a wide run to pump along, over its coping.
    'curve_to_blue_pool': ([(1211., 955.5), (1217., 950.), (1229.7, 939.7), (1248., 924.2), (1257.6, 917.9),
                            (1264.9, 914.4), (1268., -22.1, 913.4), (1277., -22., 911.)], 6., 2.5, 3.5, True),
    # The blue pool's north coping (-22 m) to the 12 m half-pipe's floor (-22 m), through the hump between them (cut).
    'blue_pool_to_half_pipe': ([(1316., -22., 923.), (1318., -22., 936.), (1322., -22., 950.)], 6., 2.5, 3.5, False),
    # The valley's floor (-24.2 m), where the rider stopped, south through the city's dirt to its paved central street
    # (-22.4 m): a pump track, rollers a metre high every 8 m between transition walls.
    'valley_pump_track': ([(1322., -24.2 + k % 2, 1134. - 4 * k) for k in range(15)]
                          + [(1322., -23.4, 1072.), (1322., -22.4, 1066.), (1322., -22.4, 1056.)], 7., 2.5, 3.5, False)}
# The ramps: a centreline [(x, z)], where along it the ramp starts (metres), its profile (y, degrees, parts; profile),
# its width and its walls' height (ramp). A gap is a kicker and a landing on one line.
GAP_LINE = [(1144., 931.4), (1380., 902.6)]
PLAZA_LINE = [(1237.6, 1037.1), (1337.6, 967.1)]  # the terrace (7.5 m) south-east, past its planters, into the half-pipe     # the rim deck (11 m) east, over the dumbbell's disk, into the blue pool
RAMPS = {
    # The blue pool gap: a 50 m bridge off the south-west bowl's rim deck, a crest (radius 50 m) down to 32 degrees, a
    # kicker to a 15-degree lip at -2.5 m; a table, a 32-degree landing over the snake run's end (5 m up) and a run-out
    # into the pool's floor (-24.9 m). The game's rider (offline simulation): 16-18 m/s at the lip from 7-13 m/s on
    # the bridge, a 35 m, 2.2 s air from 10 m/s, clean at every speed (slower ones land on the table), 23-25 m/s in.
    'pool_gap_kicker': (GAP_LINE, 0., (11.1, -1., [('line', 50.), ('arc', 50., -32.), ('line', 2.), ('arc', 30., 0.),
                                                   ('arc', 20., 15.)]), 7., 0.),
    'pool_gap_landing': (GAP_LINE, 100.2, (-2.99, 0., [('line', 6.), ('arc', 18., -32.), ('line', 22.2), ('arc', 35., 0.)]),
                         10., 0.),
    # The pool's far side at that speed: its 3 m wall is vertical at the top (from 22 m/s the rider bailed there), so a
    # bank over it from the run-out's foot: a 12 m transition to 28 degrees, clear of the old coping, up 22.5 m to the
    # south-east run's deck (-2.4 m), the crater floor's way out; down it, the run drops into the pool.
    'pool_east_bank': (GAP_LINE, 157.5, (-24.9, 0., [('arc', 12., 28.), ('line', 30.8), ('arc', 40., 0.), ('line', 12.5)]),
                       12., 0.),
    # The plaza's gap south-east over the hillside and the city's west street (29 m down): a 4.5 m step-up off the
    # terrace (it bleeds the speed the hip gives: past 21 m/s at the lip the rider overshot the landing and bailed), a
    # 15-degree lip at the terrace's edge, a 10 m table and a 45-degree landing easing out (radius 70 m) over the paved
    # street onto the 12 m half-pipe's floor. The game's rider: clean from 14 to 26 m/s on the terrace; 24 m/s flies
    # 48 m in 2.8 s.
    'plaza_gap_kicker': (PLAZA_LINE, 0., (7.5, 0., [('arc', 20., 25.), ('line', 6.), ('arc', 20., 0.), ('line', 3.),
                                                     ('arc', 15., 15.)]), 8., 0.),
    'plaza_gap_landing': (PLAZA_LINE, 31.3, (14.06, 0., [('line', 10.), ('arc', 25., -45.), ('line', 8.24), ('arc', 70., 0.)]),
                          10., 0.),
    # The 12 m half-pipe's east wall carried up 11 m to the black bowls' pocket (-0.9 m): a roll-in (crest radius 14 m,
    # 38 degrees, the old wall's angle where they meet). From a standstill the rider reaches the floor at 16.5 m/s; up
    # it, a pump out of the crater floor to the black bowls and the tunnel.
    'half_pipe_roll_in': ([(1378., 953.), (1340., 953.)], 0., (-0.9, 0., [('line', 4.), ('arc', 14., -38.), ('line', 11.4)]),
                          8., 0.),
    # The 12 m half-pipe's west deck (-10.1 m) over its stepped neck to the peanut bowl's tail (-14.5 m): a 25-degree
    # landing for an air out over the west coping, one smooth bank where the steps were.
    'half_pipe_to_peanut': ([(1283., 959.), (1250., 959.)], 0., (-10.1, 0., [('line', 1.5), ('arc', 8., -25.), ('line', 5.8),
                                                                          ('arc', 10., 0.)]), 6., 0.)}
# The streets: a box over the open ground, the heights (low, high) of the pieces it is paved flush with, and its material.
STREETS = {'central_street': ((1306., 968., 1348., 1055.), (-22.7, -22.), 'material_012')}  # the walkways, herringbone
CLEAR = .05         # metres a street lies over the hillside at least (nearer, the two would flicker)
OVER = .3           # metres: where the hillside comes up through a street more than this, the street stops at it


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
    rows, cols = h.shape
    if min(rows, cols) >= COARSE and free.sum() > COARSE ** 2 and fixed.any():
        # Started from the same membrane on a grid half as fine (each square of four nodes one node: fixed if any of
        # them is, at their mean): the sweeps here then only add the detail, however long the span (a 60 m bank
        # converged over 240 nodes only from this start).
        r2, c2 = (rows + 1) // 2, (cols + 1) // 2
        blocks = lambda a, fill: np.pad(a, ((0, 2 * r2 - rows), (0, 2 * c2 - cols)), constant_values=fill).reshape(r2, 2, c2, 2)
        f2 = blocks(fixed, False); n = f2.sum((1, 3))
        coarse_fixed = n > 0
        coarse = relax(blocks(np.where(fixed, height, 0.), 0.).sum((1, 3)) / np.maximum(n, 1), coarse_fixed,
                       blocks(free, False).any((1, 3)) & ~coarse_fixed, sweeps)
        h = np.where(free, np.repeat(np.repeat(coarse, 2, 0), 2, 1)[:rows, :cols], h)
    else:
        # Started from the fixed heights spread by inverse distance: the sweeps then only smooth it.
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


def grid_mesh(x0, z0, cell, height, nodes, smooth=OUTLINE):
    """The height field over the squares whose four corner `nodes` are set: (vertices (k, 3), faces (n, 3)), each
    square split along the diagonal across which its corners' heights differ least. Its outline, a staircase of the
    grid's squares, is smoothed `smooth` times (smooth_outline): a wall closing it stands straight, not in slats."""
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
    faces = np.concatenate([first, second])
    moved = smooth_outline(vertices, faces, smooth)
    # an outline vertex moved across keeps to the surface: its height read off the field where it now stands (moved
    # level, it stood proud of a slope or sank into it by the slope times its move, a row of teeth along the edge)
    shift_ = np.linalg.norm((moved - vertices)[:, [0, 2]], axis=1) > 1e-9
    if shift_.any():
        moved[shift_, 1] = field_height(height, nodes, x0, z0, cell, moved[shift_][:, [0, 2]], vertices[shift_, 1])
    return moved, faces


def field_height(height, nodes, x0, z0, cell, q, fallback):
    """The height field's value at the points q (k, 2) (x, z): bilinear over its square where all four corners are set,
    else `fallback` (a vertex moved out past the set squares keeps its height)."""
    i = (q[:, 0] - x0) / cell; j = (q[:, 1] - z0) / cell
    i0 = np.clip(np.floor(i).astype('i8'), 0, nodes.shape[1] - 2); j0 = np.clip(np.floor(j).astype('i8'), 0, nodes.shape[0] - 2)
    fi, fj = np.clip(i - i0, 0, 1), np.clip(j - j0, 0, 1)
    h00, h10 = height[j0, i0], height[j0, i0 + 1]; h01, h11 = height[j0 + 1, i0], height[j0 + 1, i0 + 1]
    n00, n10, n01, n11 = nodes[j0, i0], nodes[j0, i0 + 1], nodes[j0 + 1, i0], nodes[j0 + 1, i0 + 1]
    out = np.asarray(fallback, 'f8').copy()
    full = n00 & n10 & n01 & n11
    out[full] = ((1 - fi) * (1 - fj) * h00 + fi * (1 - fj) * h10 + (1 - fi) * fj * h01 + fi * fj * h11)[full]
    return out


def smooth_outline(vertices, faces, sweeps=OUTLINE):
    """`vertices` with the outline of the mesh `faces` smoothed across (x, z) `sweeps` times: each vertex on one run of
    free edges (two neighbours along it) moves half way to their middle. Its height stays."""
    if not sweeps or not len(faces):
        return vertices
    edges = np.concatenate([faces[:, [0, 1]], faces[:, [1, 2]], faces[:, [2, 0]]])
    key = np.sort(edges, 1)
    _, inverse, count = np.unique(key, axis=0, return_inverse=True, return_counts=True)
    free = key[count[inverse.ravel()] == 1]
    ends = np.concatenate([free[:, 0], free[:, 1]]); other = np.concatenate([free[:, 1], free[:, 0]])
    order = np.argsort(ends, kind='stable'); ends, other = ends[order], other[order]
    vertex, first, degree = np.unique(ends, return_index=True, return_counts=True)
    run = degree == 2                                   # a pinch (more neighbours) or an end stays put
    vertex, first = vertex[run], first[run]
    one, two = other[first], other[first + 1]
    v = vertices.astype('f8').copy()
    for _ in range(sweeps):
        middle = (v[one][:, [0, 2]] + v[two][:, [0, 2]]) / 2
        v[vertex[:, None], [0, 2]] = (v[vertex][:, [0, 2]] + middle) / 2
    return v.astype(vertices.dtype)


def wall_feet(ride, is_floor, is_ride, slot, cell=CELL):
    """How far each floor node rises in a transition at the foot of the nearest riding deck WALL_LOW to WALL_HIGH over
    it (none where a slot lies nearer): a circle's arc of radius R (the wall's height within RADIUS), rising from the
    floor to the deck's edge, or to R where the wall is taller. Returns (rise, wall height) per node."""
    best = np.full(ride.shape, np.inf); height = np.zeros(ride.shape)
    n = int(np.ceil(RADIUS[1] / cell))
    deck = np.where(is_ride, ride, -np.inf); base = np.where(np.isfinite(ride), ride, np.inf)
    for dj in range(-n, n + 1):
        for di in range(-n, n + 1):
            r = np.hypot(dj, di) * cell
            if r == 0 or r > RADIUS[1]:
                continue
            h = shift(deck, dj, di, -np.inf) - base
            wall = is_floor & (h >= WALL_LOW) & (h <= WALL_HIGH) & (r < best)
            best = np.where(wall, r, best); height = np.where(wall, h, height)
    to_slot = distance_out(~slot, RADIUS[1] + cell, cell) if slot.any() else np.full(ride.shape, np.inf)
    best = np.where(best < np.where(to_slot > 0, to_slot, np.inf), best, np.inf)
    d = np.maximum(best - cell / 2, 0.)
    radius = np.clip(height, *RADIUS); top = np.minimum(height, radius)
    reach = np.sqrt(np.maximum(radius ** 2 - (radius - top) ** 2, 0.))
    rise = np.where(np.isfinite(best) & (d < reach), radius - np.sqrt(np.maximum(radius ** 2 - (reach - d) ** 2, 0.)), 0.)
    return rise, height


def snake_channels(riding, solid, box, floor, open_=OPEN, channel=CHANNEL, feet=False, cell=CELL):
    """The snake channels in the open slots of `box` (x0, z0, x1, z1), whose floor lies near `floor`, a slot's top
    `open_` under it at least, `channel` deep (0: filled flush, part of the floor); with `feet`, the transitions at the
    foot of its deck walls (wall_feet).
    Returns {'channels': (vertices, faces, uvs), 'floor': ...} (the curves, the flat skirt round them; either may be
    missing), or None. A small hole makes a
    pocket. `riding` and `solid` are the park's riding and other faces (m, 3, 3)."""
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
    slot = np.zeros_like(deep); beds = np.zeros_like(deep)
    for k in np.unique(label[label >= 0]):
        patch = label == k
        if patch[0].any() or patch[-1].any() or patch[:, 0].any() or patch[:, -1].any():
            continue                                            # it runs out of the box: not a slot in the floor
        rim = grow(patch, 1) & ~patch
        if is_floor[rim].mean() >= RING:
            slot |= patch
            # A planter: its rim (a brick cap) stands RAISED_RIM over the floor round it. It gets a flat bed BED under
            # its cap, not a pocket curving up to the cap inside the box.
            ring = grow(patch, 6) & ~grow(patch, 3) & is_floor
            if ring.any() and np.median(ride[rim & is_floor]) - np.median(ride[ring]) > RAISED_RIM:
                beds |= patch
    # A bridge across a slot (a strip at floor height, not the floor, BRIDGE wide at most) stays: the channel rises under it, a roller
    # TAPER long either side, and meets it flush.
    closed = shrink(grow(slot, int(BRIDGE / 2 / cell) + 1), int(BRIDGE / 2 / cell) + 1) | slot
    bridge = closed & ~slot & ~is_floor & np.isfinite(every) & (np.abs(every - floor) < open_ / 2)
    slot |= bridge
    if channel <= 0:
        # Filled: a slot carries the floor's level across (relaxed from the floor round it) and is floor from then on,
        # so a deck wall's transition starts on the floor and runs over the slot in one curve: no gutter at its foot.
        across = relax(np.where(bridge, every, np.where(is_floor, ride, 0.)),
                       (grow(slot, 1) & ~slot & is_floor) | bridge, slot & ~bridge)
        ride = np.where(slot & ~bridge, across, np.where(bridge, every, ride)); is_floor = is_floor | (slot & ~bridge)
    # Only a deck WIDE across has a transition at its foot. A rail, a ledge or a free-standing wall stub keeps its
    # faces as they are: no transition starts at it, and one passing by eases down to the floor CLEAR_NARROW from it.
    high = is_ride & (ride > floor + WALL_LOW - .05)
    k = int(round(WIDE / 2 / cell))
    narrow = high & ~grow(~grow(~high, k, True), k, True)          # opened by a square: a deck's corners stay
    rise = wall_feet(ride, is_floor, is_ride & ~narrow, slot & (channel > 0), cell)[0] if feet else np.zeros(ride.shape)
    if narrow.any():
        gap = distance_out(~narrow, CLEAR_NARROW + EASE, cell)
        rise = rise * np.sin(np.pi / 2 * np.clip((gap - CLEAR_NARROW) / EASE, 0., 1.)) ** 2
    rise = np.where(is_floor, rise, 0.)
    raised = rise > RAISED
    if not slot.any() and not raised.any():
        return None
    ground = np.where(is_floor, ride + rise, ride)
    fixed = (grow(slot, 1) & ~slot & is_floor) | bridge
    level = np.where(bridge, every, np.where(is_floor, ground, 0.))
    rim = relax(level, fixed, slot & ~bridge)
    d = distance_out(slot, REACH, cell)
    half = np.maximum(max_near(d, REACH * .75, cell, slot), d)
    ramp = np.minimum(half, TRANSITION)                          # down a transition, then a flat bottom
    depth = np.minimum(max(channel, 0.), STEEPEST * ramp)
    if bridge.any():
        to_bridge = distance_out(~bridge, TAPER, cell)
        depth = depth * np.sin(np.pi / 2 * np.clip(to_bridge / TAPER, 0., 1.)) ** 2
    u = np.clip(d / np.maximum(ramp, 1e-6), 0., 1.)
    height = np.where(slot & (channel > 0), rim - depth * np.sin(np.pi / 2 * u) ** 2, ground)
    height = np.where(beds, rim - BED, height)
    # The nodes round each piece, under the floor, carry the floor's own height: its edge meets the floor flush.
    # One mesh over both, then split by its shape, not by the grid's cells (whose outline is a staircase): a triangle
    # with a corner off the floor's level by LIFTED, a channel's dip or a transition's rise, is the channels' concrete;
    # the rest, flat at the floor's level, is the floor's own material ('floor'), so the concrete ends along a smooth
    # contour (the bowls' dark floor, the plaza's flagstones: SNAKES names it).
    near = slot | raised
    for _ in range(OVERLAP):
        near = grow(near, 1, True) & (slot | is_floor)
    vertices, faces = grid_mesh(x0, z0, cell, height, near)
    flat = np.flatnonzero(near.ravel())
    ours = (slot | raised).ravel()[flat][faces].any(1)              # the rest lie on the floor or a deck: left out
    level = ride if channel <= 0 else np.where(slot, relax(np.where(bridge, every, np.where(is_floor, ride, 0.)),
                                                             fixed, slot & ~bridge), ride)
    with np.errstate(invalid='ignore'):                             # no floor at all off the pieces: inf - inf
        off = np.abs(height - level)
    lifted = np.isfinite(off) & (np.where(np.isfinite(off), off, 0.) > LIFTED)
    steep = unit_normals(vertices[faces].astype('f8'))[:, 1] < SKIRT_STEEPEST    # a floor node to a deck's top
    curved = lifted.ravel()[flat][faces].any(1) | steep
    made = {}
    for name, part, metres in (('channels', ours & curved, UV_METRES), ('floor', ours & ~curved, FEET_METRES)):
        if part.any():
            made[name] = (vertices.astype('f4'), faces[part], (vertices[:, [0, 2]] / metres).astype('f4'))
    return made or None




def coping_top(riding, gx, gz, edge, fixed, reach=LIP, rise=1., highest=np.inf):
    """The lip's true top at the `fixed` nodes: the highest corner of the `riding` faces within `reach` of the node, up
    to `rise` over its `edge` height and `highest` at most (a quarter pipe's coping lies between the grid's nodes, up
    to 0.6 m over them)."""
    out = edge.copy()
    j, i = np.nonzero(fixed)
    if not len(j):
        return out
    p = np.stack([gx[j, i], gz[j, i]], 1)
    corners = riding.reshape(-1, 3)
    near = ((corners[:, [0, 2]] > p.min(0) - reach) & (corners[:, [0, 2]] < p.max(0) + reach)).all(1) & (corners[:, 1] <= highest)
    c = corners[near]
    for k in range(0, len(p), 512):
        q = p[k:k + 512]; e = edge[j[k:k + 512], i[k:k + 512]]
        close = ((c[None, :, [0, 2]] - q[:, None]) ** 2).sum(-1) <= reach ** 2
        y = np.where(close & (c[None, :, 1] <= e[:, None] + rise), c[None, :, 1], -np.inf).max(1) if len(c) else e
        out[j[k:k + 512], i[k:k + 512]] = np.maximum(e, y)
    return out


def bank(riding, solid, box, joins=None, shape=None, cell=CELL):
    """A bank spanning the open ground of `box` (x0, z0, x1, z1) between the riding surfaces round it: where no
    riding face is the top, a smooth surface carries their edges' heights across (relax) and meets them flush. With
    `joins` [((x0, z0, x1, z1), low, high)], only the riding surfaces in those boxes, between those heights, are met;
    the bank passes the others by. With `shape` (an exponent over 1), it is a landing transition: from its high edge it
    falls steeply (shape times the mean slope) and eases out flat onto its low edge, a hip's far side. It lies CLEAR over
    the ground at least. Its free sides hang (solidify closes them). (vertices, faces, uvs) or None."""
    x0, z0, x1, z1 = box
    xs = np.arange(x0, x1 + cell / 2, cell); zs = np.arange(z0, z1 + cell / 2, cell)
    gx, gz = np.meshgrid(xs, zs)
    points = np.stack([gx.ravel(), np.zeros(gx.size), gz.ravel()], 1)
    ride = top_heights(riding, points).reshape(gx.shape)
    every = np.maximum(ride, top_heights(solid, points).reshape(gx.shape))
    is_ride = np.isfinite(ride) & (ride >= every - .01)
    open_ = ~is_ride
    meet = is_ride.copy()
    if joins is not None:
        meet[:] = False
        for (a0, b0, a1, b1), low, high in joins:
            meet |= is_ride & (gx >= a0) & (gx <= a1) & (gz >= b0) & (gz <= b1) & (ride >= low) & (ride <= high)
    fixed = grow(open_, 1) & meet
    if not open_.any() or not fixed.any():
        return None
    # The bank meets a piece at its lip, the highest of it within LIP: the grid node next to a quarter pipe's top lies
    # on its steep face, under the lip (the hip from the tower met the channel's wall 0.6 m low, a step and a coping
    # across the face).
    edge = np.where(fixed, max_near(np.where(meet, ride, -np.inf), LIP, cell, meet), ride)
    # Joined only to some heights, the lip is too: a higher piece beside a walkway is no lip of it.
    highest = max(high for _, _, high in joins) if joins is not None else np.inf
    edge = np.where(fixed, coping_top(riding, gx, gz, edge, fixed, highest=highest), edge)
    height = np.where(open_, relax(np.where(meet, edge, 0.), fixed, open_), np.where(fixed, edge, ride))
    if shape:
        # The share of the way from the high edge to the low (a membrane, 0 to 1), the heights each edge carries across,
        # and between them the drop (1 - share) ** shape: steep off the lip, flat at the foot.
        high = fixed & (edge > (edge[fixed].min() + edge[fixed].max()) / 2); low = fixed & ~high
        if high.any() and low.any():
            share = relax(np.where(low, 1., 0.), fixed, open_)
            top = relax(np.where(high, edge, 0.), high, open_ | low); foot = relax(np.where(low, edge, 0.), low, open_ | high)
            height = np.where(open_, foot + (top - foot) * (1 - np.clip(share, 0., 1.)) ** shape, height)
            with np.errstate(invalid='ignore'):             # no ground: -inf
                lift = every + CLEAR - height
            height = np.where(open_ & np.isfinite(lift) & (lift > 0) & (lift <= OVER * 3), every + CLEAR, height)
    near = open_.copy()
    for _ in range(OVERLAP):
        near = grow(near, 1, True) & (open_ | meet)
    vertices, faces = grid_mesh(x0, z0, cell, height, near)
    return vertices.astype('f4'), faces, (vertices[:, [0, 2]] / UV_METRES).astype('f4')


def street(riding, solid, box, level, cell=CELL):
    """A street paved over the open ground of `box` (x0, z0, x1, z1): a bank met only by the riding pieces whose height
    lies within `level` (low, high), so it passes the others by (a deck's wall over it stays a wall, a ledge a ledge).
    It lies CLEAR over the hillside at least; where the hillside rises through it more than OVER, it stops there.
    (vertices, faces, uvs) or None."""
    made = bank(riding, solid, box, [(box, *level)], cell)
    if made is None:
        return None
    v = made[0].astype('f8')
    with np.errstate(invalid='ignore'):                             # no ground under a vertex: -inf
        up = top_heights(solid, v) + CLEAR - v[:, 1]
    up = np.where(np.isfinite(up), up, -np.inf)
    v[:, 1] += np.where((up > 0) & (up <= OVER + CLEAR), up, 0.)
    faces = made[1][~(up > OVER + CLEAR)[made[1]].any(1)]
    if not len(faces):
        return None
    used = np.unique(faces); index = np.full(len(v), -1, 'i8'); index[used] = np.arange(len(used))
    return v[used].astype('f4'), index[faces], made[2][used]


def monotone(x, y, at):
    """The curve through the points (x, y) at `at`, smooth (its slope continuous) and never past its neighbours' heights
    (a monotone cubic, Fritsch-Carlson): a landing ramp's profile with no bump or dip between its given heights."""
    x, y = np.asarray(x, 'f8'), np.asarray(y, 'f8')
    if len(x) < 3:
        return np.interp(at, x, y)
    h = np.diff(x); d = np.diff(y) / h
    m = np.zeros(len(x)); m[0], m[-1] = d[0], d[-1]
    same = d[:-1] * d[1:] > 0
    w1, w2 = 2 * h[1:] + h[:-1], h[1:] + 2 * h[:-1]
    m[1:-1] = np.where(same, (w1 + w2) / np.where(same, w1 / np.where(same, d[:-1], 1) + w2 / np.where(same, d[1:], 1), 1), 0.)
    k = np.clip(np.searchsorted(x, at) - 1, 0, len(x) - 2)
    u = np.clip((at - x[k]) / h[k], 0., 1.)
    h00, h10, h01, h11 = 2 * u ** 3 - 3 * u ** 2 + 1, u ** 3 - 2 * u ** 2 + u, -2 * u ** 3 + 3 * u ** 2, u ** 3 - u ** 2
    return h00 * y[k] + h10 * h[k] * m[k] + h01 * y[k + 1] + h11 * h[k] * m[k + 1]


CUT = .3            # metres the hillside lies under a snake run laid through it (cut_ground)
SNAKE_LIP = .6      # metres of flat deck along a snake run's lip, behind its coping
SNAKE_STEP = .5     # metres between the points its centreline is resampled at
SNAKE_EASE = 2.     # metres over which its floor's height is smoothed along it
SKIRT_DEGREES = 30. # a ramp's flank sloping down to the ground beside it (run_mesh)
SKIRT_DEPTH = 4.    # metres it goes down at most


def snake_run(riding, path, width, wall, radius, laid=True, cell=CELL):
    """A snake run along the centreline `path` [(x, z) or (x, y, z)]: a floor `width` wide, at the height of the riding
    face under the centreline (a path it is laid over stays flush), or the point's own y, carried smoothly along it
    between; a circle's arc of `radius` either side rising `wall` over the floor, so a rider carves and pumps from wall
    to wall; then SNAKE_LIP of flat deck. Not `laid` (over a gap: a landing ramp), its floor takes only the points' own
    heights, through a smooth curve that never overshoots them (no wall: a ramp). Its outer sides hang (solidify closes
    them). (vertices, faces, uvs) or None."""
    p = np.asarray([(q[0], np.nan, q[1]) if len(q) == 2 else q for q in path], 'f8')
    # The centreline resampled every SNAKE_STEP, its floor's height sampled and carried across the gaps, then eased.
    seg = np.linalg.norm(np.diff(p[:, [0, 2]], axis=0), axis=1); s = np.concatenate([[0.], np.cumsum(seg)])
    t = np.arange(0., s[-1] + 1e-6, SNAKE_STEP)
    line = np.stack([np.interp(t, s, p[:, 0]), np.zeros(len(t)), np.interp(t, s, p[:, 2])], 1)
    given = np.interp(t, s[np.isfinite(p[:, 1])], p[np.isfinite(p[:, 1]), 1]) if np.isfinite(p[:, 1]).any() else None
    if not laid:
        y = monotone(s[np.isfinite(p[:, 1])], p[np.isfinite(p[:, 1]), 1], t)
    else:
        y = top_heights(riding, line)
    near_given = np.zeros(len(t), bool)
    if given is not None and laid:
        for k in np.flatnonzero(np.isfinite(p[:, 1])):
            near_given |= np.abs(t - s[k]) < SNAKE_STEP
        y = np.where(near_given | ~np.isfinite(y), np.where(near_given, given, y), y)
    ok = np.isfinite(y)
    if ok.sum() < 2:
        return None
    y = np.interp(t, t[ok], y[ok])
    if laid:
        k = max(1, int(SNAKE_EASE / SNAKE_STEP / 2))
        y = np.convolve(np.pad(y, k, mode='edge'), np.ones(2 * k + 1) / (2 * k + 1), mode='valid')
    return run_mesh(line, y, width, wall, radius, cell)


def run_field(line, y, q):
    """A run's centreline field at the points q (m, 2) (x, z): the distance to the centreline `line` (k, 3), the floor's
    height there (the nearest segment's `y`, interpolated) and whether the point lies past either end of it."""
    a, b = line[:-1][:, [0, 2]], line[1:][:, [0, 2]]
    best = np.full(len(q), np.inf); floor_y = np.zeros(len(q)); beyond = np.zeros(len(q), bool)
    for i in range(0, len(a), 64):
        aa, bb = a[i:i + 64], b[i:i + 64]; d = bb - aa
        free = ((q[:, None] - aa) * d).sum(-1) / np.maximum((d * d).sum(-1), 1e-12); u = np.clip(free, 0., 1.)
        dist = np.linalg.norm(q[:, None] - (aa + u[..., None] * d), axis=-1)
        j = dist.argmin(1); m = dist[np.arange(len(q)), j]; f = free[np.arange(len(q)), j]
        better = m < best
        best = np.where(better, m, best)
        floor_y = np.where(better, y[i + j] + u[np.arange(len(q)), j] * (y[i + j + 1] - y[i + j]), floor_y)
        out = ((i + j == 0) & (f < -1e-9)) | ((i + j == len(a) - 1) & (f > 1 + 1e-9))
        beyond = np.where(better, out, beyond)
    return best, floor_y, beyond


RIBBON_EASE = 4.    # metres either side over which the ribbon's cross-sections turn with the centreline
CHORD = .001        # metres: a transition's arc off its chords at most


def _offsets(width, reach, radius, edge, cell):
    """The lateral offsets of one side of a run's cross-section (from 0 out to `edge`): the floor every `cell`, its
    edge (the transition's foot, a crease), the arc in chords within CHORD, its top (a crease), the lip deck to `edge`."""
    w2 = width / 2
    floor = np.linspace(0., w2, max(1, int(np.ceil(w2 / cell))) + 1)
    if reach > 1e-9:
        ang = np.arcsin(min(reach / radius, 1.))
        n = max(1, int(np.ceil(ang / (2 * np.arccos(1 - CHORD / radius)))), int(np.ceil(reach / cell)))
        arc = w2 + radius * np.sin(np.linspace(0., ang, n + 1))[1:]
    else:
        arc = np.zeros(0)
    top = w2 + reach
    lip = np.linspace(top, edge, max(1, int(np.ceil((edge - top) / cell))) + 1)[1:] if edge > top + 1e-9 else np.zeros(0)
    return np.concatenate([floor, arc, lip])


def run_mesh(line, y, width, wall, radius, cell=CELL, ground=None):
    """The mesh of a run along `line` (k, 3) whose floor lies at `y` (k,) under it: a floor `width` wide, a circle's arc
    of `radius` either side rising `wall` over it, then SNAKE_LIP of flat deck; its ends open, cut square across it.
    With `ground` (m, 3, 3), its sides slope down at SKIRT_DEGREES to the ground under them where it lies within
    SKIRT_DEPTH (lower, they hang that far: solidify walls the rest): a ramp's flank meeting the street it lands on is
    a hip to ride over, not a wall across it. (vertices, faces, uvs) or None.

    Swept, not gridded: a cross-section every `cell` along the centreline (its normal eased over RIBBON_EASE, square to
    the end segments at the ends), each vertex moved onto the exact distance from the centreline its offset stands for,
    so the floor's edges, the arcs' tops, the lip and the outline are straight or curved lines along the run, never a
    grid's staircase; heights from the same field as before (run_field)."""
    radius = max(radius, wall); reach = np.sqrt(max(radius ** 2 - (radius - wall) ** 2, 0.))
    edge = width / 2 + reach + SNAKE_LIP
    skirt = SKIRT_DEPTH / np.tan(np.radians(SKIRT_DEGREES)) if ground is not None else 0.
    # stations every `cell` along the centreline (its segments are straight: y between stations is linear)
    seg = np.linalg.norm(np.diff(line[:, [0, 2]], axis=0), axis=1); s = np.concatenate([[0.], np.cumsum(seg)])
    if s[-1] < 1e-6:
        return None
    t = np.unique(np.concatenate([np.linspace(0., s[-1], max(2, int(np.ceil(s[-1] / cell))) + 1), s]))
    t = t[np.r_[True, np.diff(t) > 1e-6]]
    cx, cz = np.interp(t, s, line[:, 0]), np.interp(t, s, line[:, 2])
    # cross-section directions: the tangent eased over RIBBON_EASE (narrowing to none at the ends)
    tang = np.stack([np.gradient(cx, t), np.gradient(cz, t)], 1)
    tang[0] = line[1, [0, 2]] - line[0, [0, 2]]; tang[-1] = line[-1, [0, 2]] - line[-2, [0, 2]]
    tang /= np.maximum(np.linalg.norm(tang, axis=1, keepdims=True), 1e-12)
    ease = np.minimum(RIBBON_EASE, np.minimum(t, t[-1] - t))
    sm = np.empty_like(tang)
    for i in range(len(t)):
        w = np.abs(t - t[i]) <= ease[i] + 1e-9
        v = tang[w].sum(0); sm[i] = v / max(np.linalg.norm(v), 1e-12)
    nrm = np.stack([-sm[:, 1], sm[:, 0]], 1)                         # left of the direction of travel
    side = _offsets(width, reach, radius, edge, cell)
    cols = np.concatenate([-side[::-1], side[1:]])                   # the core section, left to right
    # the skirt's extra offsets (trimmed per section where it meets the ground)
    extra = np.arange(cell, skirt + cell / 2, cell)[:, None] * [1.] if skirt > 0 else np.zeros((0, 1))
    extra = extra.ravel()
    def place(off):
        """Points at signed offsets off (n, m) from each station, moved onto the exact centreline distance |off|."""
        p = np.stack([cx[:, None] + off * nrm[:, None, 0], cz[:, None] + off * nrm[:, None, 1]], -1)
        target = np.abs(off)
        for _ in range(4):
            d, _, _ = run_field(line, y, p.reshape(-1, 2)); d = d.reshape(off.shape)
            p = p + ((target - d) * np.sign(off))[..., None] * nrm[:, None, :]
        return p
    def field_y(p):
        d, fy, beyond = run_field(line, y, p.reshape(-1, 2))
        e = np.clip(d - width / 2, 0., reach)
        return (fy + radius - np.sqrt(np.maximum(radius ** 2 - e ** 2, 0.))).reshape(p.shape[:-1]), d.reshape(p.shape[:-1])
    core = place(np.broadcast_to(cols, (len(t), len(cols))).copy())
    core_y, _ = field_y(core)
    V = [np.stack([core[..., 0], core_y, core[..., 1]], -1).reshape(-1, 3)]
    nst, nc = len(t), len(cols)
    idx = np.arange(nst * nc).reshape(nst, nc)
    rows = [list(r) for r in idx.tolist()]                           # each section's vertex ids, left to right
    base = nst * nc
    if skirt > 0 and len(extra):
        drop = extra * np.tan(np.radians(SKIRT_DEGREES))
        for sgn in (-1., 1.):
            off = sgn * (edge + extra)
            p = place(np.broadcast_to(off, (nst, len(extra))).copy())
            py, _ = field_y(p); py = py - drop
            under = top_heights(ground, np.stack([p[..., 0].ravel(), (py + OVER).ravel(), p[..., 1].ravel()], 1)).reshape(py.shape)
            margin = py - (under - CUT)                              # >= 0: the slope still over the ground
            edge_y = V[0].reshape(nst, nc, 3)[:, 0 if sgn < 0 else -1]
            for i in range(nst):
                ok = margin[i] >= 0
                k = int(np.argmin(ok)) if not ok.all() else len(ok)  # the run of samples before the first under
                pts = [np.array([p[i, j, 0], py[i, j], p[i, j, 1]]) for j in range(k)]
                if k < len(ok):
                    # where the slope meets the ground: between the last sample over it and the first under
                    m0 = margin[i, k - 1] if k else (edge_y[i, 1] - (top_heights(ground, edge_y[i:i + 1])[0] - CUT))
                    m1 = margin[i, k]
                    if m0 > 0 and np.isfinite(m1) and np.isfinite(m0):
                        f = m0 / (m0 - m1)
                        a0 = pts[-1] if k else edge_y[i]
                        a1 = np.array([p[i, k, 0], py[i, k], p[i, k, 1]])
                        pts.append(a0 + f * (a1 - a0))
                ids = list(range(base, base + len(pts))); base += len(pts)
                if pts:
                    V.append(np.array(pts))
                rows[i] = (ids[::-1] + rows[i]) if sgn < 0 else (rows[i] + ids)
    vertices = np.concatenate(V)
    # strips between neighbouring sections: the core column by column; a skirt's longer side fanned to the shorter end
    faces = []
    for i in range(nst - 1):
        r0, r1 = rows[i], rows[i + 1]
        # split each row into (left skirt, core, right skirt); the core is idx[i]
        c0, c1 = idx[i].tolist(), idx[i + 1].tolist()
        l0 = r0[:r0.index(c0[0])][::-1]; l1 = r1[:r1.index(c1[0])][::-1]
        g0 = r0[r0.index(c0[-1]) + 1:]; g1 = r1[r1.index(c1[-1]) + 1:]
        def strip(a, b):
            """Quads between two parallel polylines a and b (same direction), the longer one's tail fanned."""
            out = []
            m = min(len(a), len(b))
            for j in range(m - 1):
                out.append((a[j], b[j], a[j + 1], b[j + 1]))
            if len(a) > m:
                out += [('tri', a[j], a[j + 1], b[m - 1]) for j in range(m - 1, len(a) - 1)]
            elif len(b) > m:
                out += [('tri', a[m - 1], b[j], b[j + 1]) for j in range(m - 1, len(b) - 1)]
            return out
        quads = strip(c0, c1) + strip([c0[0]] + l0, [c1[0]] + l1) + strip([c0[-1]] + g0, [c1[-1]] + g1)
        for q in quads:
            if q[0] == 'tri':
                faces.append(q[1:])
                continue
            a0, b0, a1, b1 = q
            # the shorter diagonal
            if np.linalg.norm(vertices[a0] - vertices[b1]) <= np.linalg.norm(vertices[b0] - vertices[a1]):
                faces += [(a0, b0, b1), (a0, b1, a1)]
            else:
                faces += [(a0, b0, a1), (b0, b1, a1)]
    faces = np.array(faces, 'i8').reshape(-1, 3)
    tri = vertices[faces]
    n = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
    faces = faces[np.linalg.norm(n, axis=1) > 1e-10]; n = n[np.linalg.norm(n, axis=1) > 1e-10]
    down = n[:, 1] < 0
    if 0 < down.sum() < len(faces) / 2:                                # the sections all run one way: a face turned
        raise ValueError(f'run_mesh: {int(down.sum())} faces folded over (the centreline bends tighter than the run is wide)')
    faces[down] = faces[down][:, [0, 2, 1]]                           # wound to face up (native y up)
    if not len(faces):
        return None
    return vertices.astype('f4'), faces, (vertices[:, [0, 2]] / UV_METRES).astype('f4')


def hermite(s, y, slope, at):
    """The curve through the heights `y` at the distances `s` along a line, rising at the `slope`s there (rise per
    metre), a cubic between each two: a ramp's profile with its lip and its landing at exactly their angles."""
    s, y, m = (np.asarray(v, 'f8') for v in (s, y, slope))
    k = np.clip(np.searchsorted(s, at) - 1, 0, len(s) - 2); h = s[k + 1] - s[k]
    u = np.clip((at - s[k]) / h, 0., 1.)
    h00, h10, h01, h11 = 2 * u ** 3 - 3 * u ** 2 + 1, u ** 3 - 2 * u ** 2 + u, -2 * u ** 3 + 3 * u ** 2, u ** 3 - u ** 2
    return h00 * y[k] + h10 * h * m[k] + h01 * y[k + 1] + h11 * h * m[k + 1]


def profile(y, degrees, parts, step=1.):
    """A ramp's profile from its start at height `y` rising at `degrees`, through `parts`: ('line', metres) straight on,
    or ('arc', radius, degrees) curving to that angle on a circle (a crest down a roll-in, a kicker's transition up to
    its lip, a landing's knuckle and its run-out): its knots [(s, y, degrees)] every `step` metres at most, for ramp."""
    s, a = 0., float(degrees); knots = [(s, float(y), a)]
    for part in parts:
        if part[0] == 'line':
            n = max(1, int(np.ceil(part[1] / step)))
            for _ in range(n):
                s += part[1] / n; y += part[1] / n * np.tan(np.radians(a)); knots.append((s, y, a))
        else:
            radius, to = part[1], float(part[2])
            n = max(1, int(np.ceil(radius * np.radians(abs(to - a)) / step)))
            for k in range(1, n + 1):
                b = a + (to - a) * k / n; prev = knots[-1][2]
                # along the circle from angle prev to b: dx = R |sin b - sin prev|, dy = R |cos prev - cos b| signed
                dx = radius * abs(np.sin(np.radians(b)) - np.sin(np.radians(prev)))
                dy = radius * (np.cos(np.radians(prev)) - np.cos(np.radians(b))) * (1 if b > prev else -1)
                s += dx; y += dy; knots.append((s, y, b))
            a = to
    return knots


def ramp(path, start, knots, width, wall=0., radius=RADIUS[1], cell=CELL, ground=None):
    """A ramp along the centreline `path` [(x, z)] from `start` metres along it, its floor's height along it from the
    `knots` [(s, y, degrees)] (profile; s from the ramp's start, a cubic between, so each knot's angle holds there: a
    kicker's lip, a landing's slope), `width` wide, with walls as a snake run's (run_mesh; `wall` 0: a plain sheet). A
    gap is a kicker and a landing, each a ramp on one path. (vertices, faces, uvs) or None."""
    p = np.asarray(path, 'f8'); k = np.asarray(knots, 'f8')
    seg = np.linalg.norm(np.diff(p, axis=0), axis=1); s = np.concatenate([[0.], np.cumsum(seg)])
    t = np.arange(0., k[-1, 0] + 1e-6, SNAKE_STEP)
    if t[-1] < k[-1, 0] - 1e-6:
        t = np.append(t, k[-1, 0])
    line = np.stack([np.interp(start + t, s, p[:, 0]), np.zeros(len(t)), np.interp(start + t, s, p[:, 1])], 1)
    return run_mesh(line, hermite(k[:, 0], k[:, 1], np.tan(np.radians(k[:, 2])), t), width, wall, radius, cell, ground)


def cut_ground(positions, pieces, depth=CUT):
    """The hillside's vertices `positions` (k, 3) lowered to `depth` under the added `pieces` (m, 3, 3) over them, where
    the hillside stood higher: a snake run laid through a hump lies in a cut, the hill meeting its lips, not through
    its floor. Returns the new positions and how many moved."""
    top = top_heights(pieces.astype('f8'), positions.astype('f8'))
    with np.errstate(invalid='ignore'):                             # none over: -inf
        low = np.isfinite(top) & (positions[:, 1] > top - depth)
    out = positions.copy(); out[low, 1] = (top[low] - depth).astype(out.dtype)
    return out, int(low.sum())


def kicker(riding, box, toward='x-', spine=False, cell=CELL):
    """A kicker in `box` (x0, z0, x1, z1) up to a low wall's top on its `toward` side ('x-', 'x+', 'z-' or 'z+'): along
    each grid line toward the wall, from the floor at the box's far side, a circle's arc of radius RADIUS[0] (the wall's
    height if more) rising to the wall's top edge (the first node KICK higher than the floor) and meeting it flush. Its
    two sides are closed down to the floor. With `spine`, the arc spans the whole box from its far side (its radius set by
    the run and the height: a spine's steep side), and it carries the wall's top on, flush, across any gap up to the
    rim beyond it. (vertices, faces, uvs) or None."""
    x0, z0, x1, z1 = box
    xs = np.arange(x0, x1 + cell / 2, cell); zs = np.arange(z0, z1 + cell / 2, cell)
    gx, gz = np.meshgrid(xs, zs)
    ride = top_heights(riding, np.stack([gx.ravel(), np.zeros(gx.size), gz.ravel()], 1)).reshape(gx.shape)
    turn = lambda a: (a if toward[0] == 'x' else a.T)[:, ::-1 if toward[1] == '+' else 1]
    unturn = lambda a: (a[:, ::-1 if toward[1] == '+' else 1]).T if toward[0] == 'z' else a[:, ::-1 if toward[1] == '+' else 1]
    r = turn(ride); height = np.full(r.shape, np.nan)
    for k, row in enumerate(r):
        low = row[-1]
        up = np.flatnonzero(np.isfinite(row) & (row > low + KICK))
        if not np.isfinite(low) or not len(up):
            continue
        top = up.max(); h = row[top] - low
        radius = max(RADIUS[0], h); reach = np.sqrt(radius ** 2 - (radius - h) ** 2)
        if spine:
            run = (len(row) - 1 - top - .5) * cell
            radius = max((run ** 2 + h ** 2) / (2 * h), h); reach = min(run, radius)
            rim = np.flatnonzero(np.isfinite(row[:top]) & (row[:top] >= row[top] - .05))
            fill = np.arange((rim.max() + 1) if len(rim) else 0, top)
            height[k, fill] = row[top]
        s = (np.arange(len(row)) - top - .5) * cell                     # metres from the wall's face
        arc = low + radius - np.sqrt(np.maximum(radius ** 2 - (reach - np.clip(s, 0., reach)) ** 2, 0.))
        span = (np.arange(len(row)) >= top) & (s <= reach + cell)
        height[k, span] = np.where(np.arange(len(row))[span] == top, row[top], arc[span])
    height = unturn(height)
    nodes = np.isfinite(height)
    if nodes.sum() < 4:
        return None
    vertices, faces = grid_mesh(x0, z0, cell, np.where(nodes, height, 0.), nodes, 0)   # its sides follow the grid
    floor_y = np.nanmin(height)
    # The two sides, from the profile down to the floor, both ways round (they are seen from either side).
    sides_v, sides_f = [], []
    edge_rows = [0, nodes.shape[0] - 1] if toward[0] == 'x' else [0, nodes.shape[1] - 1]
    for e in edge_rows:
        line = (np.flatnonzero(nodes[e]) if toward[0] == 'x' else np.flatnonzero(nodes[:, e]))
        for i in line[:-1]:
            if toward[0] == 'x':
                (xa, za, ya), (xb, zb, yb) = (xs[i], zs[e], height[e, i]), (xs[i + 1], zs[e], height[e, i + 1])
            else:
                (xa, za, ya), (xb, zb, yb) = (xs[e], zs[i], height[i, e]), (xs[e], zs[i + 1], height[i + 1, e])
            base = len(vertices) + len(sides_v)
            sides_v += [(xa, ya, za), (xb, yb, zb), (xb, floor_y, zb), (xa, floor_y, za)]
            sides_f += [(base, base + 1, base + 2), (base, base + 2, base + 3), (base, base + 2, base + 1), (base, base + 3, base + 2)]
    if sides_v:
        vertices = np.concatenate([vertices, np.asarray(sides_v)]); faces = np.concatenate([faces, np.asarray(sides_f, 'i8')])
    uv = np.where(np.arange(len(vertices))[:, None] < nodes.sum(), vertices[:, [0, 2]],
                  np.stack([vertices[:, 0] + vertices[:, 2], vertices[:, 1]], 1)) / UV_METRES
    return vertices.astype('f4'), faces, uv.astype('f4')


def tile_metres(positions, uvs, triangles, default=UV_METRES):
    """Metres per texture tile on a piece: its edges' median length over their length in UV."""
    p = positions[triangles].astype('f8'); u = uvs[triangles].astype('f8')
    world = np.linalg.norm(p[:, 1] - p[:, 0], axis=1); texture = np.linalg.norm(u[:, 1] - u[:, 0], axis=1)
    use = (world > .2) & (texture > 1e-6)
    return float(np.median(world[use] / texture[use])) if use.sum() > 10 else default


THICK = .35         # metres: a sheet's free edge is capped this wide, so the piece reads as solid concrete
RUN = 2.            # metres of free edge in one run at least, for a cap and a wall
CLEAR_EDGE = .3     # metres up or down from a free edge where nothing continues past it (it ends in the air)
LOWEST = .15        # metres: a free edge this close over what lies under it rests on it (no wall to build)
FAR_DOWN = 30.      # metres a wall goes down at most, where nothing lies under it
BURY = .1           # metres a wall goes on under the ground it stands on
SHEET = .4          # metres either side of a sheet's face that are open air
HEADROOM = 3.       # metres over a riding face at least, for a ramp's wall over it to stop short as a span (solidify)
BEAM = .6           # metres deep: a span's fascia over a run it leaves open


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


def solidify(piece, heights, around, metres=UV_METRES, clear=None):
    """Caps and walls that close the free edges of the riding piece `piece` (n, 3, 3) where it ends in the air, a
    sheet with no thickness (a half-pipe's flank, the back of its wall): along each such edge a level cap THICK wide on
    the side away from the piece, then a wall from the cap's far edge down to whatever lies under it. `heights` is
    grind.heights over the whole park and `around` its faces (m, 3, 3); `metres` per texture tile. A sheet is open on
    both sides: from its face just inside the edge, nothing lies within SHEET either way (a trim on a wall's top, a
    pool's rim or a ramp on its block has the solid behind it). With `clear` (grind.heights over the riding faces), a
    wall over a riding face HEADROOM or more under it stops BEAM down, a span's fascia: a ramp flying over a run leaves
    it open. Returns (vertices (k, 3), faces (m, 3), uvs (k, 2)) or None: the caps' corners and the walls' are apart, so
    the edge between them stays sharp."""
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
    # Only a run of edges RUN long at least: a stray stretch a few decimetres long stood as a lone slat to the ground.
    _, ids = np.unique(np.round(np.concatenate([a, b]) * 1000).astype('i8'), axis=0, return_inverse=True)
    ia, ib = ids.ravel()[:len(a)], ids.ravel()[len(a):]
    label = np.arange(ids.max() + 1)
    while True:                                                     # each corner takes its run's lowest id
        low = np.minimum(label[ia], label[ib]); before = label.copy()
        np.minimum.at(label, ia, low); np.minimum.at(label, ib, low); label = label[label]
        if (label == before).all():
            break
    run = np.zeros(len(label)); np.add.at(run, label[ia], np.linalg.norm(b - a, axis=1))
    long_run = run[label[ia]] >= RUN
    a, b, out = a[long_run], b[long_run], out[long_run]
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
    if clear is not None:
        ride = clear(far, far[:, 1] - FAR_DOWN, far[:, 1] - HEADROOM, top=True)
        span = np.isfinite(ride) & (ride >= bottom + BURY - LOWEST)        # the ground it stands on is ridden
        bottom = np.where(span, far[:, 1] - BEAM, bottom)
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
    # Caps take the texture from above, walls along their face: u is the distance along the run of the wall's top (a
    # projection on the outward direction's normal jumped a tile each time the direction turned a degree, far from the
    # origin: streaks down the wall), v its height. Where a run closes on itself its first corner is doubled.
    u = np.full(n, np.nan)
    adj = [[] for _ in range(n)]
    for e, (x, z) in enumerate(zip(ia.tolist(), ib.tolist())):
        adj[x].append((z, e)); adj[z].append((x, e))
    flat_far = far[:, [0, 2]]
    deg = np.array([len(v) for v in adj])
    for s0 in sorted(range(n), key=lambda v: (deg[v] != 1, v)):
        if np.isfinite(u[s0]) or not deg[s0]:
            continue
        u[s0] = 0.; stack = [s0]
        while stack:
            cur = stack.pop()
            for nxt, e in adj[cur]:
                if np.isnan(u[nxt]):
                    u[nxt] = u[cur] + np.linalg.norm(flat_far[nxt] - flat_far[cur]); stack.append(nxt)
    u = np.nan_to_num(u)
    length = np.linalg.norm(flat_far[ib] - flat_far[ia], axis=1)
    seam = np.abs(np.abs(u[ib] - u[ia]) - length) > 1e-4                 # a run's closing edge (or a pinch)
    uv_wall = np.stack([np.concatenate([u, u]), vertices[2 * n:, 1]], 1)
    extra_v, extra_uv = [], []
    m, ne = len(vertices), len(ia)
    for k, e in enumerate(np.flatnonzero(seam).tolist()):
        lo_end, hi_end = (ia[e], ib[e]) if u[ia[e]] <= u[ib[e]] else (ib[e], ia[e])
        nu = u[hi_end] + length[e]                       # the lower end's copies carry on past the higher end's u
        extra_v += [vertices[2 * n + lo_end], vertices[3 * n + lo_end]]
        extra_uv += [[nu, vertices[2 * n + lo_end, 1]], [nu, vertices[3 * n + lo_end, 1]]]
        for f in (len(caps) + e, len(caps) + ne + e):    # the edge's two wall faces
            faces[f] = np.where(faces[f] == 2 * n + lo_end, m + 2 * k, np.where(faces[f] == 3 * n + lo_end, m + 2 * k + 1, faces[f]))
    if extra_v:
        vertices = np.concatenate([vertices, np.array(extra_v)])
    uvs = np.concatenate([vertices[:2 * n][:, [0, 2]], uv_wall] + ([np.array(extra_uv)] if extra_uv else [])) / metres
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
