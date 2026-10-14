"""Crater Park's grind lines, found in its own riding surfaces (pure numpy, native frame: metres, y up).

The source park has no grind paths, and the skate runtime grinds only the lines a park registers (park.json `rails`).
A lip is the edge of a level deck where the deck stops: past it the ground falls away (a ramp's coping, a ledge, a box,
a bowl's rim), and nothing hangs over it. These are the edges the runtime's grind probes accept (PlayerGrindSurface):
the deck within a few centimetres on one side, nothing at deck height on the other, nothing just above. Nothing is added
to the park: the lines run along edges that are already there.
"""
import numpy as np

LEVEL = .9          # a deck face's normal y at least (about 25 degrees)
NEAR = .09          # metres either side of a lip the runtime probes (PlayerGrindSurface): the deck on one side only
SNAP = .04          # metres up or down from the lip a probe still counts as meeting the deck
CLEAR = .4          # metres above the lip and its probes that must be empty (no ceiling, no wall leaning over)
OUT = .3            # metres past the lip where the drop is measured
DROP = (.15, 6.)    # metres the ground past a lip lies under it: a curb or more, and not the block's outer cliff
TREAD = (.15, .3, .7, .9, 1.1)  # metres past a lip: a stair's tread (the first two), then its next step
RISER = .3          # metres: a step down this high or less, onto a level tread, is a stair's
TURN = 35.          # degrees: a sharper corner ends a line
SHORTEST = 1.5      # metres: shorter lines are left out
STEP = .5           # metres between a line's points
CELL = 2.           # metres: the height index's grid


def unit_normals(t):
    n = np.cross(t[:, 1] - t[:, 0], t[:, 2] - t[:, 0])
    return n / np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-12)


def heights(triangles, cell=CELL):
    """A query over the faces `triangles` (m, 3, 3) not seen edge-on from above: between(points, low, high) is the mask
    of the points (k, 3) with a face over or under them whose height there lies within [low, high] (k,); with top=True,
    the highest such height instead (-inf where there is none)."""
    s = triangles.astype('f8')
    s = s[np.abs(unit_normals(s)[:, 1]) > .05]
    lo = np.floor(s.min(1)[:, [0, 2]] / cell).astype('i8'); hi = np.floor(s.max(1)[:, [0, 2]] / cell).astype('i8')
    size = hi - lo + 1; count = size.prod(1)
    owner = np.repeat(np.arange(len(s)), count)
    local = np.arange(count.sum()) - np.repeat(np.cumsum(count) - count, count)
    cells = lo[owner] + np.stack([local % size[owner, 0], local // size[owner, 0]], -1)
    keys = (cells[:, 0] + (1 << 20)) << 21 | (cells[:, 1] + (1 << 20))
    order = np.argsort(keys, kind='stable'); keys, owner = keys[order], owner[order]

    def between(points, low, high, chunk=20000, top=False):
        if len(points) > chunk:
            return np.concatenate([between(points[i:i + chunk], low[i:i + chunk], high[i:i + chunk], top=top)
                                   for i in range(0, len(points), chunk)])
        c = np.floor(points[:, [0, 2]] / cell).astype('i8'); k = (c[:, 0] + (1 << 20)) << 21 | (c[:, 1] + (1 << 20))
        start = np.searchsorted(keys, k, 'left'); reps = np.searchsorted(keys, k, 'right') - start
        which = np.repeat(np.arange(len(points)), reps)
        cand = owner[np.repeat(start, reps) + np.arange(reps.sum()) - np.repeat(np.cumsum(reps) - reps, reps)]
        p = points[which]; v = s[cand]
        d = (v[:, 1, 2] - v[:, 2, 2]) * (v[:, 0, 0] - v[:, 2, 0]) + (v[:, 2, 0] - v[:, 1, 0]) * (v[:, 0, 2] - v[:, 2, 2])
        ok = np.abs(d) > 1e-12; d = np.where(ok, d, 1.)
        l1 = ((v[:, 1, 2] - v[:, 2, 2]) * (p[:, 0] - v[:, 2, 0]) + (v[:, 2, 0] - v[:, 1, 0]) * (p[:, 2] - v[:, 2, 2])) / d
        l2 = ((v[:, 2, 2] - v[:, 0, 2]) * (p[:, 0] - v[:, 2, 0]) + (v[:, 0, 0] - v[:, 2, 0]) * (p[:, 2] - v[:, 2, 2])) / d
        l3 = 1 - l1 - l2
        y = l1 * v[:, 0, 1] + l2 * v[:, 1, 1] + l3 * v[:, 2, 1]
        hit = ok & (l1 >= -1e-9) & (l2 >= -1e-9) & (l3 >= -1e-9) & (y >= low[which]) & (y <= high[which])
        if top:
            best = np.full(len(points), -np.inf); np.maximum.at(best, which[hit], y[hit])
            return best
        found = np.zeros(len(points), bool); found[which[hit]] = True
        return found
    return between


def lips(points, outward, riding, solid):
    """Mask of the points (k, 3) on a deck edge, `outward` (k, 3) horizontal unit vectors pointing off the deck, that are
    grindable lips: the deck NEAR inside, nothing at deck height NEAR outside, the park's riding surface past it DROP
    below (a path's edge over the hillside is no lip), not a stair's nosing, and nothing
    within CLEAR above the lip or its probes. `riding` and `solid` are heights() queries over the riding surfaces and
    over all the collision."""
    y = points[:, 1]
    inner = points - NEAR * outward; outer = points + NEAR * outward; past = points + OUT * outward
    ok = riding(inner, y - SNAP, y + SNAP)
    ok &= ~solid(outer, y - SNAP, y + SNAP)
    ok &= riding(past, y - DROP[1], y - DROP[0]) & ~solid(past, y - DROP[0], y + CLEAR)
    for q in (points, inner, outer):
        ok &= ~solid(q, y + SNAP, y + CLEAR)
    # A stair's nosing: the ground past it is a short level tread, then another step down. Its edges are no grind (an
    # ollie down the set would be pulled onto a step). A bank or a transition falls away smoothly; a ledge or a curb has
    # level ground past it.
    depth = np.minimum(np.stack([y - solid(points + d * outward, y - DROP[1], y - SNAP, top=True) for d in TREAD], 1), 1e3)
    flat = np.abs(depth[:, 1] - depth[:, 0]) < SNAP / 4
    ok &= ~(flat & (depth[:, 0] < RISER) & (depth[:, 2:].max(1) - depth[:, 1] > SNAP * 2))
    return ok


def deck_edges(riding_triangles):
    """Every edge of the level riding faces, with its horizontal unit vector pointing off the face: (a, b, outward)."""
    t = riding_triangles.astype('f8'); deck = t[unit_normals(t)[:, 1] > LEVEL]
    c = deck.mean(1)
    a = np.concatenate([deck[:, i] for i in range(3)]); b = np.concatenate([deck[:, (i + 1) % 3] for i in range(3)])
    centre = np.tile(c, (3, 1))
    e = (b - a) * [1, 0, 1]; length = np.linalg.norm(e, axis=1); keep = length > 1e-4
    a, b, e, centre, length = a[keep], b[keep], e[keep], centre[keep], length[keep]
    out = np.stack([e[:, 2], np.zeros(len(e)), -e[:, 0]], 1) / length[:, None]
    flip = ((centre - (a + b) / 2) * out).sum(1) > 0
    out[flip] *= -1
    return a, b, out


def chain(a, b, turn=TURN):
    """The segments (a, b) joined end to end into polylines (lists of points), broken at corners sharper than `turn`
    and wherever more than two segments meet."""
    key = lambda p: tuple(np.round(p * 1000).astype('i8'))      # welded at a millimetre
    ends = {}
    for i, (p, q) in enumerate(zip(a, b)):
        ends.setdefault(key(p), []).append((i, 0)); ends.setdefault(key(q), []).append((i, 1))
    used = np.zeros(len(a), bool); lines = []
    cos_turn = np.cos(np.radians(turn))

    def step(i, end):
        """From segment i leaving through its end `end` (0 = a, 1 = b): the next segment and its far end, if any."""
        here = (a, b)[end][i]; d0 = (b[i] - a[i]) if end == 1 else (a[i] - b[i])
        nxt = [(j, e) for j, e in ends[key(here)] if j != i and not used[j]]
        if len(ends[key(here)]) != 2 or not nxt:
            return None
        j, e = nxt[0]; far = 1 - e
        d1 = (b[j] - a[j]) if far == 1 else (a[j] - b[j])
        cos = (d0 * d1).sum() / max(np.linalg.norm(d0) * np.linalg.norm(d1), 1e-12)
        return (j, far) if cos >= cos_turn else None

    for i in range(len(a)):
        if used[i]:
            continue
        used[i] = True; line = [a[i], b[i]]
        k, end = i, 1
        while (n := step(k, end)) is not None:
            k, end = n; used[k] = True; line.append((a, b)[end][k])
        k, end = i, 0
        while (n := step(k, end)) is not None:
            k, end = n; used[k] = True; line.insert(0, (a, b)[end][k])
        lines.append(np.array(line))
    return lines


def resample(line, step=STEP):
    """The polyline's points every `step` metres or so along it, its ends kept."""
    d = np.concatenate([[0.], np.cumsum(np.linalg.norm(np.diff(line, axis=0), axis=1))])
    n = max(1, int(np.ceil(d[-1] / step)))
    s = np.linspace(0., d[-1], n + 1)
    return np.stack([np.interp(s, d, line[:, k]) for k in range(3)], 1)


def grind_lines(riding_triangles, solid_triangles):
    """Crater Park's grind lines: [(points (k, 3) native metres)], each a lip SHORTEST long or more, its points every
    STEP, every point a grindable lip (lips)."""
    riding = heights(riding_triangles); solid = heights(np.concatenate([riding_triangles, solid_triangles]))
    a, b, out = deck_edges(riding_triangles)
    # An edge is a lip when its middle and both quarter points are.
    ok = np.ones(len(a), bool)
    for f in (.25, .5, .75):
        ok &= lips(a + (b - a) * f, out, riding, solid)
    lines = []
    for line in chain(a[ok], b[ok]):
        if np.linalg.norm(np.diff(line, axis=0), axis=1).sum() < SHORTEST:
            continue
        pts = resample(line)
        # The resampled points again (a corner can cut across): split where one fails.
        seg = (pts[1:] - pts[:-1]) * [1, 0, 1]; seg /= np.maximum(np.linalg.norm(seg, axis=1, keepdims=True), 1e-12)
        o = np.stack([seg[:, 2], np.zeros(len(seg)), -seg[:, 0]], 1)
        o = np.concatenate([o, o[-1:]]); o[1:-1] = (o[1:-1] + o[:-2]); o /= np.maximum(np.linalg.norm(o, axis=1, keepdims=True), 1e-12)
        good = lips(pts, o, riding, solid) | lips(pts, -o, riding, solid)      # the deck's side is either
        run = []
        for p, g in zip(pts, good):
            if g:
                run.append(p)
            else:
                if len(run) > 1 and np.linalg.norm(np.diff(run, axis=0), axis=1).sum() >= SHORTEST:
                    lines.append(np.array(run))
                run = []
        if len(run) > 1 and np.linalg.norm(np.diff(run, axis=0), axis=1).sum() >= SHORTEST:
            lines.append(np.array(run))
    return lines
