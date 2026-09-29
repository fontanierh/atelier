"""Skate pier layout: every dimension the meshes, park.json and the checks share.

Pure numpy (no bpy). Park-local metres: origin at the platform centre on the deck
top, x east, y north, z up (the Blender world axes, yaw 0). World = ORIGIN + local.
"""
import sys as _sys; from pathlib import Path as _Path; _sys.path.insert(0, str(_Path(__file__).resolve().parents[2])); import yori  # noqa: E402,F401
import json
import math
from pathlib import Path
import numpy as np

JAPAN = yori.REGIONS

ORIGIN = (-110.0, -195.0, 1.80)          # Blender world metres, deck top
HALF_X, HALF_Y = 40.0, 27.0              # deck x in [-40, 40], y in [-27, 27]
RAIL_INSET = 0.15                         # perimeter railing line inside the deck edge
RAILING_H = 1.10
SLAB = 0.50                               # deck slab thickness under the floor
ENTRANCE_X = 6.0                          # path arrives on the north edge at this local x
PATH_HALF = 2.0                           # 4 m path

# ----------------------------------------------------------------------------- features
BIG_QP = dict(lip_x=35.0, y0=-6.0, y1=6.0, height=1.80, vert=0.15, r0=2.20, deck_x=37.0, rail_h=1.0)
MINI_QP = dict(lip_x=-35.0, y0=-5.0, y1=5.0, height=1.00, radius=1.50, deck_x=-37.0, rail_h=1.0)
COPING_R = 0.025                          # 5 cm round steel coping
COPING_OUT = 0.010                        # pipe stands 1 cm proud of the face
COPING_UP = 0.005                         # and 5 mm above the deck
KICKER = dict(toe_x=-11.5, lip_x=-9.5, y0=0.1, y1=1.7, height=0.5)
FUNBOX = dict(x0=-8.5, x1=2.5, top0=-6.0, top1=0.0, y0=-1.75, y1=1.75, height=0.6, r_bottom=2.0, r_top=1.2)
PLATFORM = dict(x0=-30.0, x1=-18.0, y0=-26.85, y1=-18.85, height=1.2)
PLATFORM_BANK = dict(x0=-30.0, x1=-22.0, corner_y=-12.35, radius=5.0)   # rises south to y1 of the platform
STAIRS = dict(x_top=-18.0, y0=-25.0, y1=-20.0, risers=6, rise=0.20, tread=0.35)
HANDRAIL = dict(y=-22.5, x0=-19.5, x1=-15.9, above=0.85, r=0.025)
HUBBA = dict(y0=-25.8, y1=-25.0, x0=-19.0, above=0.35, x1=-15.9)
BARS = [dict(id='flatbar_high', x0=10.0, x1=16.0, y=-4.5, top=0.35, color='red'),
        dict(id='flatbar_low', x0=10.5, x1=15.5, y=4.5, top=0.25, color='yellow')]
BAR_R = 0.025
MANUAL_PAD = dict(x0=16.0, x1=20.0, y0=11.75, y1=14.25, height=0.18)
BENCHES = [(-25.0, -20.0), (-14.0, -9.0), (20.0, 25.0)]
BENCH = dict(y0=22.25, y1=22.75, height=0.45)
SOUTH_BANK = dict(x0=4.0, x1=24.0, top_y=-25.85, height=1.5, angle=35.0, radius=2.0)
DECAL_Z = 0.004                           # painted floor motif (separate, non-blocking mesh)
FLOOR_SUN = dict(x=-25.0, y=12.0, r=3.2)
FLOOR_WAVES = [(-19.6, -12.6, 10.6), (-19.2, -12.2, 12.0), (-18.8, -11.8, 13.4)]   # x0, x1, y
LAMPS = [(-38.5, 25.5), (0.0, 25.5), (38.5, 25.5), (-38.5, -25.5), (0.0, -25.5), (38.5, -25.5)]
STEEL_BAND = 0.05                         # width of the flush steel angle on ledge corners
JOINT_W = 0.04                            # sawn expansion joints in the deck, painted dark (flush)
JOINTS_X = [float(x) for x in np.arange(-35.0, 35.1, 5.0)]
JOINTS_Y = [float(y) for y in np.arange(-25.0, 25.1, 5.0)]


def nosing_z(x):
    """Stair nosing line (platform edge to the last nosing), local metres."""
    s = STAIRS
    return PLATFORM['height'] - (x - s['x_top']) * s['rise'] / s['tread']


def world(p):
    return [ORIGIN[0] + p[0], ORIGIN[1] + p[1], ORIGIN[2] + (p[2] if len(p) > 2 else 0.0)]


# ----------------------------------------------------------------------------- profiles
def big_qp_profile(step_deg=2.5):
    """(x, z) from the toe to the lip: radius runs 2.2 m at the floor down to 1.34 m where it
    reaches vertical at 1.65 m, then 0.15 m of true vertical. Exact ends."""
    q = BIG_QP
    a = q['r0']; tall = q['height'] - q['vert']
    b = tall - a                                       # r(phi) = a + b*phi: height a+b, run a+b(pi/2-1)
    run = a + b * (math.pi / 2 - 1)
    toe = q['lip_x'] - run
    n = int(math.ceil(90 / step_deg))
    pts = []
    for k in range(n + 1):
        t = (math.pi / 2) * k / n
        x = a * math.sin(t) + b * (t * math.sin(t) + math.cos(t) - 1)
        z = a * (1 - math.cos(t)) + b * (math.sin(t) - t * math.cos(t))
        pts.append((toe + x, z))
    pts[-1] = (q['lip_x'], tall)
    pts.append((q['lip_x'], q['height']))
    return pts, toe, (a, a + b * math.pi / 2)


def mini_qp_profile(step_deg=2.5):
    q = MINI_QP; r = q['radius']; h = q['height']
    top = math.acos(1 - h / r); run = r * math.sin(top)
    toe = q['lip_x'] + run
    n = int(math.ceil(math.degrees(top) / step_deg))
    pts = [(toe - r * math.sin(top * k / n), r * (1 - math.cos(top * k / n))) for k in range(n + 1)]
    pts[-1] = (q['lip_x'], h)
    return pts, toe, math.degrees(top)


def kicker_profile(step_deg=2.0):
    k = KICKER; run = k['lip_x'] - k['toe_x']; h = k['height']
    ang = 2 * math.atan2(h, run); r = run / math.sin(ang)
    n = int(math.ceil(math.degrees(ang) / step_deg))
    pts = [(k['toe_x'] + r * math.sin(ang * i / n), r * (1 - math.cos(ang * i / n))) for i in range(n + 1)]
    pts[-1] = (k['lip_x'], h)
    return pts, r, math.degrees(ang)


def fillet_polyline(corners, radii, step_deg=2.5):
    """2D polyline (u, z) with circular fillets at interior corners; exact tangent points."""
    c = [np.array(p, float) for p in corners]
    out = [c[0]]
    for i in range(1, len(c) - 1):
        a, b, d = c[i - 1], c[i], c[i + 1]
        u = (b - a) / np.linalg.norm(b - a); v = (d - b) / np.linalg.norm(d - b)
        ang = math.acos(float(np.clip(u @ v, -1, 1)))
        r = radii[i - 1]
        if ang < 1e-6 or r <= 0:
            out.append(b); continue
        t = r * math.tan(ang / 2)
        p1 = b - u * t; p2 = b + v * t
        cross = u[0] * v[1] - u[1] * v[0]
        n = np.array([-u[1], u[0]]) * (1 if cross > 0 else -1)
        centre = p1 + n * r
        a1 = math.atan2(*(p1 - centre)[::-1]); a2 = math.atan2(*(p2 - centre)[::-1])
        d_ang = a2 - a1
        while d_ang > math.pi: d_ang -= 2 * math.pi
        while d_ang < -math.pi: d_ang += 2 * math.pi
        m = max(1, int(math.ceil(abs(math.degrees(d_ang)) / step_deg)))
        for k in range(m + 1):
            t_ = a1 + d_ang * k / m
            out.append(centre + r * np.array([math.cos(t_), math.sin(t_)]))
    out.append(c[-1])
    clean = [out[0]]
    for p in out[1:]:
        if np.linalg.norm(p - clean[-1]) > 1e-6: clean.append(p)
    return [tuple(map(float, p)) for p in clean]


def funbox_profile():
    """(x, z) along the box from the west toe to the east toe (fillets included)."""
    f = FUNBOX; h = f['height']
    corners = [(f['x0'] - 1.0, 0), (f['x0'], 0), (f['top0'], h), (f['top1'], h), (f['x1'], 0), (f['x1'] + 1.0, 0)]
    pts = fillet_polyline(corners, [f['r_bottom'], f['r_top'], f['r_top'], f['r_bottom']])[1:-1]
    ang = math.atan2(h, f['top0'] - f['x0'])
    top_flat = (f['top0'] + f['r_top'] * math.tan(ang / 2), f['top1'] - f['r_top'] * math.tan(ang / 2))
    return pts, top_flat


def platform_bank_profile():
    """(y, z) from the north toe up (southward) to the platform edge, where the top fillet ends
    exactly at the platform's height (no lip)."""
    b = PLATFORM_BANK; p = PLATFORM; h = p['height']; r = b['radius']
    run = b['corner_y'] - p['y1']                        # corner-to-corner run before the shift
    ang = math.atan2(h, run); t = r * math.tan(ang / 2)
    top_c = p['y1'] + t; bot_c = top_c + run
    corners = [(bot_c + 1.0, 0), (bot_c, 0), (top_c, h), (p['y1'] - 1.0, h)]
    pts = fillet_polyline(corners, [r, r])[1:-1]
    assert abs(pts[-1][0] - p['y1']) < 1e-9 and abs(pts[-1][1] - h) < 1e-9
    return pts


def south_bank_profile():
    """(y, z) from the toe (north) up to the steel top edge at top_y; a point 5 cm below the
    top edge (along the face) bounds the steel band."""
    b = SOUTH_BANK; h = b['height']; ang = math.radians(b['angle'])
    corner = b['top_y'] + h / math.tan(ang)
    pts = fillet_polyline([(corner + 1.0, 0), (corner, 0), (b['top_y'], h)], [b['radius']])[1:]
    band = (b['top_y'] + STEEL_BAND * math.cos(ang), h - STEEL_BAND * math.sin(ang))
    return pts[:-1] + [band, pts[-1]]


def handrail_top():
    """Top contact line of the stair handrail (x, z)."""
    h = HANDRAIL; s = STAIRS
    top = PLATFORM['height'] + h['above']
    return [(h['x0'], top), (s['x_top'], top), (h['x1'], nosing_z(h['x1']) + h['above'])]


def hubba_top():
    h = HUBBA; s = STAIRS
    top = PLATFORM['height'] + h['above']
    return [(h['x0'], top), (s['x_top'], top), (h['x1'], nosing_z(h['x1']) + h['above'])]


# ----------------------------------------------------------------------------- footprints
def footprints():
    """Axis-aligned floor areas covered by solid features (the floor has holes there)."""
    _, big_toe, _ = big_qp_profile(); _, mini_toe, _ = mini_qp_profile()
    fb, _ = funbox_profile(); pb = platform_bank_profile(); sb = south_bank_profile()
    q, m, k, f, p, b, s, hb, mp, bn, sbk = BIG_QP, MINI_QP, KICKER, FUNBOX, PLATFORM, PLATFORM_BANK, STAIRS, HUBBA, MANUAL_PAD, BENCH, SOUTH_BANK
    out = {
        'big_qp': (big_toe, q['deck_x'], q['y0'], q['y1']),
        'mini_qp': (m['deck_x'], mini_toe, m['y0'], m['y1']),
        'kicker': (k['toe_x'], k['lip_x'], k['y0'], k['y1']),
        'funbox': (fb[0][0], fb[-1][0], f['y0'], f['y1']),
        'platform': (p['x0'], p['x1'], p['y0'], p['y1']),
        'platform_bank': (b['x0'], b['x1'], p['y1'], pb[0][0]),
        'stairs': (s['x_top'], s['x_top'] + (s['risers'] - 1) * s['tread'], s['y0'], s['y1']),
        'hubba': (s['x_top'], hb['x1'], hb['y0'], hb['y1']),
        'manual_pad': (mp['x0'], mp['x1'], mp['y0'], mp['y1']),
        'south_bank': (sbk['x0'], sbk['x1'], -HALF_Y + RAIL_INSET, sb[0][0]),
    }
    for i, (x0, x1) in enumerate(BENCHES):
        out[f'bench_{i + 1}'] = (x0, x1, bn['y0'], bn['y1'])
    return out


def grid_lines(spacing=0.625):
    """Floor grid lines: every footprint edge, the path's end ring, the deck joints (exact, 'hard'
    lines), filled with a uniform grid that yields to them. Ramps sample their width on these
    same lines so ramp toes and the floor share vertices (no T-cracks, no lips)."""
    hx, hy = set(), set()
    for x0, x1, y0, y1 in footprints().values():
        hx |= {round(x0, 6), round(x1, 6)}; hy |= {round(y0, 6), round(y1, 6)}
    hx |= {round(ENTRANCE_X + o, 6) for o in PATH_OFFSETS}
    hx |= {-HALF_X, HALF_X, round(-HALF_X + RAIL_INSET, 6), round(HALF_X - RAIL_INSET, 6)}
    hy |= {-HALF_Y, HALF_Y, round(-HALF_Y + RAIL_INSET, 6), round(HALF_Y - RAIL_INSET, 6)}
    hy |= {round(FUNBOX['y0'] + STEEL_BAND, 6), round(FUNBOX['y1'] - STEEL_BAND, 6)}
    for j in JOINTS_X: hx |= {round(j - JOINT_W / 2, 6), round(j + JOINT_W / 2, 6)}
    for j in JOINTS_Y: hy |= {round(j - JOINT_W / 2, 6), round(j + JOINT_W / 2, 6)}
    def fill(hard, half):
        hard = sorted(hard)
        assert min(np.diff(hard)) > 0.009, ('grid lines too close', min(np.diff(hard)))
        uni = np.linspace(-half, half, int(round(2 * half / spacing)) + 1)
        h = np.array(hard)
        keep = [u for u in uni if np.min(np.abs(h - u)) > 0.12]
        return np.array(sorted(set(hard) | set(round(float(u), 6) for u in keep)))
    return fill(hx, HALF_X), fill(hy, HALF_Y)


def lines_between(lines, a, b):
    return [float(v) for v in lines if a - 1e-6 <= v <= b + 1e-6]


# ----------------------------------------------------------------------------- path
PATH_OFFSETS = [-2.0, -1.85, -0.95, 0.0, 0.95, 1.85, 2.0]
PATH_GRADE = 0.090             # centreline limit on straights (edges checked <= 10%)
PATH_EDGE_GRADE = 0.097        # inner-edge limit on curves
PATH_CLEAR = 0.05              # surface above the upper terrain envelope


def _fillet_route(pts, radii, spacing=0.5):
    pts = [np.array(p, float) for p in pts]
    segs = []; cur = pts[0]
    for k in range(1, len(pts) - 1):
        a, b, c = pts[k - 1], pts[k], pts[k + 1]
        u = (b - a) / np.linalg.norm(b - a); v = (c - b) / np.linalg.norm(c - b)
        ang = math.acos(float(np.clip(u @ v, -1, 1))); r = radii[k - 1]
        t = r * math.tan(ang / 2)
        assert t < np.linalg.norm(b - cur) + 1e-6 and t < np.linalg.norm(c - b), ('fillet too large', k)
        p1 = b - u * t; p2 = b + v * t
        segs.append(('L', cur, p1, math.inf))
        cross = u[0] * v[1] - u[1] * v[0]
        n = np.array([-u[1], u[0]]) * (1 if cross > 0 else -1)
        segs.append(('A', p1 + n * r, r, p1, p2, cross > 0))
        cur = p2
    segs.append(('L', cur, pts[-1], math.inf))
    P = []; R = []
    for sg in segs:
        if sg[0] == 'L':
            a, b = sg[1], sg[2]; L = np.linalg.norm(b - a)
            if L < 1e-6: continue
            n = max(1, int(math.ceil(L / spacing)))
            for i in range(n): P.append(a + (b - a) * i / n); R.append(math.inf)
        else:
            _, c, r, p1, p2, ccw = sg
            a1 = math.atan2(*(p1 - c)[::-1]); a2 = math.atan2(*(p2 - c)[::-1]); d = a2 - a1
            if ccw and d < 0: d += 2 * math.pi
            if not ccw and d > 0: d -= 2 * math.pi
            n = max(1, int(math.ceil(abs(d) * r / spacing)))
            for i in range(n):
                t = a1 + d * i / n; P.append(c + r * np.array([math.cos(t), math.sin(t)])); R.append(r)
    P.append(pts[-1]); R.append(math.inf)
    return np.array(P), np.array(R)


def _lipschitz(z, s, g):
    z = z.copy()
    for i in range(1, len(z)): z[i] = max(z[i], z[i - 1] - g[i] * (s[i] - s[i - 1]))
    for i in range(len(z) - 2, -1, -1): z[i] = max(z[i], z[i + 1] - g[i] * (s[i + 1] - s[i]))
    return z


def _gauss(z, s, sigma):
    ds = float(np.mean(np.diff(s))); k = int(3 * sigma / ds)
    x = np.arange(-k, k + 1) * ds; w = np.exp(-.5 * (x / sigma) ** 2); w /= w.sum()
    zp = np.r_[np.full(k, z[0]), z, np.full(k, z[-1])]
    return np.convolve(zp, w, mode='valid')


def load_world():
    return json.loads((yori.OUT / 'world.json').read_text()), np.load(yori.OUT / 'heightmap.npy')


def path_layout(world, h):
    """Centreline, frames and a smooth grade-limited profile that never dips under the terrain."""
    import sys
    sys.path.insert(0, str(JAPAN))
    from village.layout import upper_surface
    road = np.array(world['road'])
    i = int(np.argmin(np.abs(road[:, 0] + 155.3)))
    tan = road[i + 1, :2] - road[i - 1, :2]; tan /= np.linalg.norm(tan)
    south = np.array([tan[1], -tan[0]])
    start = road[i, :2] + south * world['road_width'] / 2
    end = np.array([ORIGIN[0] + ENTRANCE_X, ORIGIN[1] + HALF_Y])
    route = [start, start + south * 5.0, (-154.6, -101.5), (-121.0, -106.5), (end[0], -146.0), (end[0], end[1] + 8.0), end]
    radii = [20.0, 10.0, 20.0, 25.0]
    P, R = _fillet_route(route[:-1], radii)
    # straight run-in to the deck edge
    tail = np.array([P[-1] + (end - P[-1]) * k / 16 for k in range(1, 17)])
    P = np.vstack([P, tail]); R = np.r_[R, np.full(len(tail), math.inf)]
    s = np.r_[0, np.cumsum(np.linalg.norm(np.diff(P, axis=0), axis=1))]
    t = np.gradient(P, s, axis=0); t /= np.linalg.norm(t, axis=1)[:, None]
    t[0] = south; t[-8:] = (0, -1)
    n = np.column_stack([-t[:, 1], t[:, 0]])
    # terrain envelope over the whole footprint (dense across and along)
    offs = np.linspace(-PATH_HALF - .15, PATH_HALF + .15, 44)
    fine = np.linspace(0, s[-1], int(s[-1] / .1) + 1)
    Px = np.interp(fine, s, P[:, 0]); Py = np.interp(fine, s, P[:, 1])
    nx = np.interp(fine, s, n[:, 0]); ny = np.interp(fine, s, n[:, 1])
    Tf = np.max([upper_surface(h, Px + nx * o, Py + ny * o) for o in offs], axis=0) + PATH_CLEAR
    T = np.array([Tf[max(0, int((a - .3) / .1)):int((a + .3) / .1) + 1].max() for a in s])
    z0 = float(road[i, 2] + 0.06); z1 = ORIGIN[2]
    g = np.where(np.isfinite(R), PATH_EDGE_GRADE * (1 - (PATH_HALF + .05) / np.maximum(R, 3)), PATH_GRADE)
    g = np.minimum(g, PATH_GRADE)
    # the smoothing below mixes grades over about +-6 m: hold the curve limit that far out
    g = np.array([g[(s > a - 6.5) & (s < a + 6.5)].min() for a in s])
    lo = T.copy()
    lo[s < 1.0] = np.maximum(lo[s < 1.0], z0)                 # level run-off the road
    lo[s > s[-1] - 4.0] = np.maximum(lo[s > s[-1] - 4.0], z1)  # level run-in to the deck
    E = _lipschitz(lo, s, g)
    assert E[0] <= z0 + 1e-6 and E[-1] <= z1 + 1e-6, ('path infeasible', E[0], z0, E[-1], z1)
    fixed = (s < 1.0) | (s > s[-1] - 4.0)
    target = np.where(s < 1.0, z0, np.where(s > s[-1] - 4.0, z1, E))
    z = target.copy()
    for _ in range(6):
        z = np.maximum(_gauss(z, s, 2.0), E)
        z[fixed] = target[fixed]
    z = np.maximum(z, E)
    return dict(P=P, s=s, t=t, n=n, z=z, R=R, T=T - PATH_CLEAR, E=E, z0=z0, start=start, road_index=i,
                road_tangent=tan, end=end, road=road, route=[list(map(float, p)) for p in route], radii=radii)


def path_ring(pl, k):
    """World-space ring of the path surface at sample k (x, y, z for each PATH_OFFSET)."""
    return [(pl['P'][k, 0] + pl['n'][k, 0] * o, pl['P'][k, 1] + pl['n'][k, 1] * o, pl['z'][k]) for o in PATH_OFFSETS]


# ----------------------------------------------------------------------------- coping, rails
def big_coping():
    """Coping pipe centre (x, z): 1 cm proud of the vertical face, 5 mm above the deck."""
    q = BIG_QP
    return (q['lip_x'] - COPING_OUT + COPING_R, q['height'] + COPING_UP - COPING_R)


def mini_coping():
    q = MINI_QP; r = q['radius']; h = q['height']
    top = math.acos(1 - h / r)
    n = (math.sin(top), math.cos(top))                  # face normal toward the riding side
    cz = h + COPING_UP - COPING_R
    cx = q['lip_x'] + ((COPING_OUT - COPING_R) - (cz - h) * n[1]) / n[0]
    return (cx, cz)


def offset_polyline(top, r):
    """Axis of a round rail whose top contact line is `top` [(x, z)...] (perpendicular offset)."""
    top = [np.array(p, float) for p in top]
    lines = []
    for a, b in zip(top[:-1], top[1:]):
        d = (b - a) / np.linalg.norm(b - a); u = np.array([-d[1], d[0]])
        if u[1] < 0: u = -u
        lines.append((a - u * r, d))
    out = [lines[0][0]]
    for (p1, d1), (p2, d2) in zip(lines[:-1], lines[1:]):
        # intersect p1 + t d1 = p2 + s d2
        A = np.array([[d1[0], -d2[0]], [d1[1], -d2[1]]]); t = np.linalg.solve(A, p2 - p1)[0]
        out.append(p1 + d1 * t)
    last_p, last_d = lines[-1]
    out.append(top[-1] - np.array([-last_d[1], last_d[0]]) * r * (1 if last_d[0] >= 0 else -1))
    return [tuple(map(float, p)) for p in out]


def _dense(poly, step):
    """Resample a polyline keeping its corners exactly."""
    poly = [np.array(p, float) for p in poly]
    out = [poly[0]]
    for a, b in zip(poly[:-1], poly[1:]):
        n = max(1, int(math.ceil(np.linalg.norm(b - a) / step)))
        out += [a + (b - a) * k / n for k in range(1, n + 1)]
    return [[round(float(c), 4) for c in p] for p in out]


def rails():
    out = []
    def add(id_, kind, pts, step, side=None, radius=None):
        r = {'id': id_, 'kind': kind, 'points': _dense(pts, step)}
        if radius is not None: r['radius'] = radius
        if side is not None: r['side'] = [round(float(side[0]), 4), round(float(side[1]), 4)]
        out.append(r)
    q = BIG_QP; cx, cz = big_coping()
    add('coping_big_quarter', 'coping', [(cx, q['y0'], cz + COPING_R), (cx, q['y1'], cz + COPING_R)], 0.5, (-1, 0), COPING_R)
    q = MINI_QP; cx, cz = mini_coping()
    add('coping_mini_quarter', 'coping', [(cx, q['y0'], cz + COPING_R), (cx, q['y1'], cz + COPING_R)], 0.5, (1, 0), COPING_R)
    b = SOUTH_BANK
    add('coping_south_bank', 'coping', [(b['x0'], b['top_y'], b['height']), (b['x1'], b['top_y'], b['height'])], 0.5, (0, 1))
    f = FUNBOX; _, (t0, t1) = funbox_profile()
    add('funbox_ledge_north', 'ledge', [(t0, f['y1'], f['height']), (t1, f['y1'], f['height'])], 0.5, (0, 1))
    add('funbox_ledge_south', 'ledge', [(t0, f['y0'], f['height']), (t1, f['y0'], f['height'])], 0.5, (0, -1))
    h = HUBBA; top = hubba_top()
    add('hubba_stairs_side', 'ledge', [(x, h['y1'], z) for x, z in top], 0.25, (0, 1))
    add('hubba_outer_side', 'ledge', [(x, h['y0'], z) for x, z in top], 0.25, (0, -1))
    hr = HANDRAIL
    add('stair_handrail', 'rail', [(x, hr['y'], z) for x, z in handrail_top()], 0.25, None, hr['r'])
    for bar in BARS:
        add(bar['id'], 'rail', [(bar['x0'], bar['y'], bar['top']), (bar['x1'], bar['y'], bar['top'])], 0.5, None, BAR_R)
    mp = MANUAL_PAD; z = mp['height']
    add('manual_pad_north', 'curb', [(mp['x0'], mp['y1'], z), (mp['x1'], mp['y1'], z)], 0.5, (0, 1))
    add('manual_pad_south', 'curb', [(mp['x0'], mp['y0'], z), (mp['x1'], mp['y0'], z)], 0.5, (0, -1))
    add('manual_pad_west', 'curb', [(mp['x0'], mp['y0'], z), (mp['x0'], mp['y1'], z)], 0.5, (-1, 0))
    add('manual_pad_east', 'curb', [(mp['x1'], mp['y0'], z), (mp['x1'], mp['y1'], z)], 0.5, (1, 0))
    bn = BENCH
    for i, (x0, x1) in enumerate(BENCHES):
        add(f'bench_{i + 1}_south', 'ledge', [(x0, bn['y0'], bn['height']), (x1, bn['y0'], bn['height'])], 0.5, (0, -1))
        add(f'bench_{i + 1}_north', 'ledge', [(x0, bn['y1'], bn['height']), (x1, bn['y1'], bn['height'])], 0.5, (0, 1))
    return out
