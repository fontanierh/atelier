"""Thresholds and pass/fail decisions for the gondola audits (plain Python: no bpy, no mathutils).

Every number the README and NOTES quote for a gate is a named constant here (walk.py holds the walk rules), and
tests/test_gondola_geometry.py asserts the documented numbers equal them. build.py, stations.py and walk.py measure;
the decisions below say whether a measurement passes, so the same rule runs in the build and in the fast tests.

Rope contacts fall in two categories:
- intentional contact: the parts that carry the rope (each grip jaw half, each tower sheave, the bullwheel groove).
  Each part on its own passes when the rope axis is the rope radius from it, within CONTACT_TOL, at every pose: seated,
  neither pressed into the part nor lifted off it. The distance is signed (a ray-parity test says whether the rope
  axis is inside the part), so an axis buried a radius deep inside a part reads -radius and fails. The clamp body over
  the jaws sits beside the rope by design: it is exempt from the clearance rule but must not cut into the rope.
- clearance to unrelated hardware: everything else (the cabin, the hanger, the grip outside the jaws, the towers'
  and stations' structure). It passes when nothing comes nearer the rope axis than the rope radius + ROPE_CLEARANCE.
"""
import math

import numpy as np

ROPE_CLEARANCE = 0.05          # m: unrelated hardware keeps this gap to the rope surface
CONTACT_TOL = 0.002            # m: an intentional contact (jaw, sheave, bullwheel groove) sits on the rope radius within this
FLOOR_TILT_TOL_DEG = 0.01      # the cabin floor stays level (it hangs plumb): largest tilt from level allowed
BUDGET = {'cabin': 15000, 'tower': 8000, 'station': 60000}   # triangles per piece (a tower: per height)
STATION_LOOP_MARGIN = 0.10     # m: the cabin body (bounding prism) to station structure, at every loop position
TOWER_BODY_MARGIN = 0.30       # m: passing cabin body to tower hardware
SEATED_TAGS = ('jaw', 'sheave', 'bullwheel groove')        # each such part carries the rope: gated per part
NO_INTRUSION_TAGS = ('clamp',)                             # beside the rope by design: may not cut into it
EXPECTED_PARTS = {'jaw': 2, 'sheave': 4, 'bullwheel groove': 1}   # parts on one rope: jaw halves, sheaves per train

CONTACT_TAGS = {'jaw': 'rope seated in the jaw groove', 'clamp': 'rope seated in the jaw groove',
                'sheave': 'rope on the sheave grooves', 'bullwheel groove': 'rope in the bullwheel groove'}
INTENTIONAL = 'intentional contact'
UNRELATED = 'clearance to unrelated hardware'


def category(tag):
    """The contact category of a part, from its tag."""
    return INTENTIONAL if tag in CONTACT_TAGS else UNRELATED


def required_clearance(rope_radius):
    """The least distance from the rope axis that unrelated hardware may come."""
    return rope_radius + ROPE_CLEARANCE


def clearance_ok(distance, rope_radius):
    """Unrelated hardware: passes at rope radius + ROPE_CLEARANCE or more. None means nothing within the search reach."""
    return distance is None or distance >= required_clearance(rope_radius) - 1e-9


def contact_ok(distance, rope_radius):
    """Intentional contact: the rope axis is the rope radius from the part, within CONTACT_TOL. None (the rope never
    came near the part) fails: a jaw, sheave or groove that does not carry the rope is a fault."""
    return distance is not None and abs(distance - rope_radius) <= CONTACT_TOL + 1e-9


def no_intrusion_ok(distance, rope_radius):
    """The clamp body beside the jaws: it may touch the rope surface but not cut into it."""
    return distance is None or distance >= rope_radius - CONTACT_TOL - 1e-9


def classify(tag, distance, rope_radius):
    """One measurement (part tag, signed distance from the rope axis) as a report row with its category and verdict."""
    cat = category(tag)
    if cat == UNRELATED:
        ok = clearance_ok(distance, rope_radius)
    elif tag in NO_INTRUSION_TAGS:
        ok = no_intrusion_ok(distance, rope_radius)
    else:
        ok = contact_ok(distance, rope_radius)
    row = {'tag': tag, 'category': cat, 'min_distance_from_rope_axis_m': distance, 'rope_radius_m': rope_radius, 'ok': ok}
    if cat == INTENTIONAL:
        row['contact'] = CONTACT_TAGS[tag]
        row['gap_m'] = None if distance is None else round(distance - rope_radius, 4)
    else:
        row['required_m'] = round(required_clearance(rope_radius), 3)
    return row


def _rows(M):
    return [[float(M[i][j]) for j in range(3)] for i in range(3)]


def floor_tilt_deg(C):
    """The angle between the cabin frame's up axis and world up (C: a 3x3 or 4x4 matrix, rows, or a mathutils
    Matrix). Zero when the cabin hangs plumb."""
    return math.degrees(math.acos(max(-1.0, min(1.0, _rows(C)[2][2]))))


def grip_pitch_deg(G):
    """The grip's pitch: the angle of its x axis (along the rope) above level."""
    return math.degrees(math.asin(max(-1.0, min(1.0, _rows(G)[2][0]))))


def hanging_ok(C):
    return floor_tilt_deg(C) <= FLOOR_TILT_TOL_DEG


def grip_clearances(grip, rope_radius):
    """Distances from the rope axis (the grip frame's x axis) to the grip parts that must stay off the rope, from the
    grip's dimensions alone: the running wheels (a tyre disc of wheel_radius in a plane wheel_y outboard, width
    wheel_width, centre wheel_z above the axis) and the pivot point. Each passes at rope radius + ROPE_CLEARANCE."""
    wy, wz, wr, ww = abs(grip['wheel_y']), grip['wheel_z'], grip['wheel_radius'], grip['wheel_width']
    inner_face = wy - ww / 2                                # the tyre's face nearest the rope, across the rope
    below = max(0.0, abs(wz) - wr)                          # how far the tyre disc stays above or below the axis height
    wheel = math.hypot(inner_face, below)                   # the nearest tyre point to the axis
    px, py, pz = grip['pivot']
    pivot = math.hypot(py, pz)
    need = required_clearance(rope_radius)
    return {'wheel_m': round(wheel, 4), 'pivot_point_m': round(pivot, 4), 'required_m': round(need, 3),
            'ok': wheel >= need and pivot >= need}


def point_clearance(points, path, near=None, window=1.5):
    """The least distance from the rope axis to a set of points (pure geometry, rope.RopePath.nearest). Used by the
    tests to check the decision rules on hand-built fixtures."""
    best = None
    for q in points:
        d, s = path.nearest(q, near=near, window=window)
        best = d if best is None else min(best, d)
    return best


def proxy_failures(proxies):
    """Collision proxies are exported as UCX convex hulls: each must be a convex plan polygon (Unreal would silently
    wrap a concave one) with its top above its bottom at every corner."""
    bad = []
    for pr in proxies:
        pts = [tuple(q) for q in pr['poly']]; n = len(pts)
        cross = [(pts[(i + 1) % n][0] - pts[i][0]) * (pts[(i + 2) % n][1] - pts[(i + 1) % n][1])
                 - (pts[(i + 1) % n][1] - pts[i][1]) * (pts[(i + 2) % n][0] - pts[(i + 1) % n][0]) for i in range(n)]
        if n < 3 or not (all(c >= -1e-9 for c in cross) or all(c <= 1e-9 for c in cross)):
            bad.append(f'collision proxy {pr["name"]} is not convex')
        elif any(b <= a for a, b in zip(pr['z0'], pr['z1'])):
            bad.append(f'collision proxy {pr["name"]} has its top at or below its bottom')
    if not proxies:
        bad.append('no collision proxies: the piece would export without UCX hulls')
    return bad


# ------------------------------------------------------------------ signed distance to a closed part (numpy only)
RAYS = np.array([[0.5257311, 0.3090170, 0.7926544], [-0.6123724, 0.7071068, -0.3535534], [0.2672612, -0.8017837, -0.5345225]])


def triangles(verts, faces):
    """A closed part's faces as an (n, 3, 3) array of triangles (polygons fanned)."""
    tris = [(verts[f[0]], verts[f[k]], verts[f[k + 1]]) for f in faces for k in range(1, len(f) - 1)]
    return np.asarray(tris, dtype=float).reshape(-1, 3, 3)


def _seg_dist(p, a, b):
    ab = b - a; t = np.clip(np.einsum('ij,ij->i', p - a, ab) / np.maximum(np.einsum('ij,ij->i', ab, ab), 1e-30), 0.0, 1.0)
    return np.linalg.norm(p - (a + ab * t[:, None]), axis=1)


def point_distance(p, tris):
    """Unsigned distance from point p to the nearest of the triangles."""
    p = np.asarray(p, dtype=float); a, b, c = tris[:, 0], tris[:, 1], tris[:, 2]
    n = np.cross(b - a, c - a); nn = np.linalg.norm(n, axis=1); ok = nn > 1e-15
    nh = n / np.where(ok, nn, 1.0)[:, None]
    h = np.einsum('ij,ij->i', p - a, nh); q = p - h[:, None] * nh
    inside = ok.copy()
    for u, v in ((a, b), (b, c), (c, a)):
        inside &= np.einsum('ij,ij->i', np.cross(v - u, q - u), nh) >= -1e-12
    P = np.broadcast_to(p, a.shape)
    edge = np.minimum(np.minimum(_seg_dist(P, a, b), _seg_dist(P, b, c)), _seg_dist(P, c, a))
    return float(np.min(np.where(inside, np.abs(h), edge)))


def _crossings(p, tris, d):
    a, b, c = tris[:, 0], tris[:, 1], tris[:, 2]
    e1, e2 = b - a, c - a; h = np.cross(d, e2); det = np.einsum('ij,ij->i', e1, h)
    good = np.abs(det) > 1e-14; inv = 1.0 / np.where(good, det, 1.0)
    s = p - a; u = np.einsum('ij,ij->i', s, h) * inv; q = np.cross(s, e1)
    v = np.einsum('j,ij->i', d, q) * inv; t = np.einsum('ij,ij->i', e2, q) * inv
    return int(np.count_nonzero(good & (u >= 0) & (v >= 0) & (u + v <= 1) & (t > 1e-12)))


def inside(p, tris):
    """Ray parity against a closed part: odd crossings mean inside; three skew rays vote, so a ray grazing an edge
    cannot flip the answer."""
    p = np.asarray(p, dtype=float)
    return sum(_crossings(p, tris, d) % 2 for d in RAYS) >= 2


def signed_distance(p, tris):
    """Distance from p to the part's surface, negative when p is inside the part."""
    d = point_distance(p, tris)
    return -d if inside(p, tris) else d


def part_minimum(tris, points, rope_radius, near=0.3):
    """The least signed distance from the rope axis samples to one part, or None when no sample comes within
    `near` of the part's box (the part is not on this rope). Parity runs only where the sign can change a verdict
    (unsigned distance below the rope radius plus 10 mm): elsewhere the unsigned distance already decides."""
    lo, hi = tris.reshape(-1, 3).min(axis=0) - near, tris.reshape(-1, 3).max(axis=0) + near
    best = None
    for p in points:
        if np.any(np.asarray(p) < lo) or np.any(np.asarray(p) > hi):
            continue
        d = point_distance(p, tris)
        if d < rope_radius + 0.01 and inside(p, tris):
            d = -d
        best = d if best is None else min(best, d)
    return best


def part_verdicts(rows, rope_radius, expected=None, seated=True):
    """Per-part rope contact gate. rows: [{'tag', 'part', 'per_pose': [signed minimum or None per pose]}]. Each seated
    part must be seated at every pose; the clamp must not intrude; and a rope must meet exactly the expected number
    of each seated part (a sheave lifted clear of the rope reads as missing, not as passing). seated=False (the
    station's attach zone, where the rope ramps down away from the opening jaws) asks only that no part cuts into the
    rope. Returns the failures."""
    bad = []; met = {}
    for r in rows:
        vals = [v for v in r['per_pose'] if v is not None]
        if not vals:
            continue
        met[r['tag']] = met.get(r['tag'], 0) + 1
        rule = no_intrusion_ok if (r['tag'] in NO_INTRUSION_TAGS or not seated) else contact_ok
        off = [v for v in vals if not rule(v, rope_radius)]
        if off:
            worst = max(off, key=lambda v: abs(v - rope_radius))
            bad.append(f'{r["tag"]} {r["part"]}: rope axis {worst:+.4f} m from it (radius {rope_radius}, '
                       f'{"inside the part" if worst < 0 else "off the seat"}) at {len(off)} of {len(vals)} poses')
    for tag, n in (expected or {}).items():
        if met.get(tag, 0) != n:
            bad.append(f'{met.get(tag, 0)} {tag} parts meet the rope, expected {n}')
    return bad


def loop_margin_ok(distance):
    """The cabin to the station structure at a loop position: at least STATION_LOOP_MARGIN."""
    return distance is not None and distance >= STATION_LOOP_MARGIN - 1e-9


FLOOR_SAMPLE = 0.25            # m: grid step for the floor-support check
FLOOR_TOL = 0.05               # m: a sample this near a hull's plan edge counts as supported
FLOOR_Z_TOL = 0.01             # m: a hull supports a slab only where its top is this near the slab's height (the seat rule)


def _inside_convex(pt, poly, tol):
    """pt within tol of the convex plan polygon poly (either winding)."""
    x, y = pt; sides = []
    for (ax, ay), (bx, by) in zip(poly, poly[1:] + poly[:1]):
        L = math.hypot(bx - ax, by - ay) or 1.0
        sides.append(((bx - ax) * (y - ay) - (by - ay) * (x - ax)) / L)
    return all(d >= -tol for d in sides) or all(d <= tol for d in sides)


def _inside(pt, poly):
    x, y = pt; c = False
    for (ax, ay), (bx, by) in zip(poly, poly[1:] + poly[:1]):
        if (ay > y) != (by > y) and x < ax + (y - ay) * (bx - ax) / (by - ay):
            c = not c
    return c


def _top_plane(pr):
    """The plane through a hull's top corners (z1), as (a, b, c) with z = a x + b y + c."""
    A = np.array([[x, y, 1.0] for x, y in pr['poly']]); return np.linalg.lstsq(A, np.array(pr['z1'], float), rcond=None)[0]


def floor_support_failures(slabs, proxies, step=FLOOR_SAMPLE, tol=FLOOR_TOL, z_tol=FLOOR_Z_TOL):
    """Every walkable slab must stand on collision: each grid sample inside a slab's plan lies within tol of some
    collision hull's plan whose top there is within z_tol of the slab's walking height (a roof over the slab or a hull
    elsewhere below it is not its floor). slabs: [(name, polygon[, z])], z a height or z(x, y), default 0;
    proxies: [{'poly', 'z1'}]. Returns the failures, one per slab."""
    hulls = [([tuple(p) for p in pr['poly']], _top_plane(pr)) for pr in proxies]
    bad = []
    for slab in slabs:
        name, poly = slab[0], [tuple(p) for p in slab[1]]
        z = slab[2] if len(slab) > 2 else 0.0
        zf = z if callable(z) else (lambda x, y, c=z: c)
        xs, ys = [p[0] for p in poly], [p[1] for p in poly]
        miss = []
        for x in np.arange(min(xs) + step / 2, max(xs), step):
            for y in np.arange(min(ys) + step / 2, max(ys), step):
                if not _inside((x, y), poly):
                    continue
                want = zf(x, y)
                if not any(_inside_convex((x, y), h, tol) and abs(a * x + b * y + c - want) <= z_tol + 1e-9 for h, (a, b, c) in hulls):
                    miss.append((round(float(x), 2), round(float(y), 2)))
        if miss:
            bad.append(f'{name}: {len(miss)} walkable samples with no collision floor at the slab height, e.g. {miss[:3]}')
    return bad


def budget_failures(piece, count):
    limit = BUDGET[piece]
    return [f'{count} triangles over budget {limit}'] if count > limit else []
