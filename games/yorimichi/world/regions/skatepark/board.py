"""Modern trick skateboard for the native skate system (docs/SKATE.md board contract).

Metres, Blender axes. Unreal imports Blender (x, y, z) as (x, -y, z), so the deck's toe
side (+Y in Unreal) is -Y here. Three meshes, each with its own origin:
  SM_SkateDeck  origin at the centre of the deck top, nose +X, up +Z
  SM_SkateTruck origin at the kingpin pivot on the deck underside (placed at (+-0.18, 0, -0.012));
                modelled as the front truck (kingpin toward -X, the board centre); the back
                truck is the same mesh turned 180 degrees about Z
  SM_SkateWheel origin at the wheel centre, axle along Y, symmetric
"""
import math
import numpy as np
from geom import MeshData

LENGTH, WIDTH = 0.80, 0.205
KICK_START, KICK_RISE, KICK_ANGLE = 0.27, 0.045, 22.0
CONCAVE, THICK = 0.009, 0.012
TRUCK_X, TRUCK_Z = 0.18, -0.012
AXLE_Z = -0.0635
WHEEL_Y, WHEEL_R, WHEEL_W = 0.093, 0.0265, 0.032
ROUND = WIDTH / 2                 # popsicle ends: semicircles
FLAT_END = LENGTH / 2 - ROUND     # 0.2975

GRIP = (0.021, 0.021, 0.023)
PLY_LIGHT, PLY_DARK = (0.44, 0.30, 0.15), (0.26, 0.16, 0.075)
BOTTOM = (0.46, 0.40, 0.30)
SUN = (0.50, 0.055, 0.035)
WAVE = (0.035, 0.070, 0.140)
HANGER = (0.30, 0.30, 0.31)
BASEPLATE = (0.035, 0.035, 0.037)
BUSHING = (0.42, 0.22, 0.05)
AXLE = (0.16, 0.16, 0.165)
URETHANE = (0.50, 0.44, 0.31)
BEARING = (0.035, 0.035, 0.04)


def _kick_bend_radius():
    t = math.radians(KICK_ANGLE); run = LENGTH / 2 - KICK_START
    return (run * math.tan(t) - KICK_RISE) / (math.sin(t) * math.tan(t) - (1 - math.cos(t)))


R_KICK = _kick_bend_radius()


def kick(xa):
    """Height and slope angle of the deck top centreline at |x| = xa."""
    t = math.radians(KICK_ANGLE)
    if xa <= KICK_START: return 0.0, 0.0
    xb = KICK_START + R_KICK * math.sin(t)
    if xa <= xb:
        a = math.asin((xa - KICK_START) / R_KICK)
        return R_KICK * (1 - math.cos(a)), a
    return R_KICK * (1 - math.cos(t)) + (xa - xb) * math.tan(t), t


def half_width(xa):
    if xa <= FLAT_END: return ROUND
    return ROUND * math.sqrt(max(0.0, 1 - ((xa - FLAT_END) / ROUND) ** 2))


def x_samples():
    side = [0.0, 0.045, 0.09, 0.135, 0.18, 0.225, 0.27, 0.2825, FLAT_END]
    side += [FLAT_END + ROUND * math.sin(math.radians(a)) for a in np.linspace(11.25, 90, 8)]
    return [-x for x in side[:0:-1]] + side


def top(x, y):
    xa = abs(x); zk, _ = kick(xa)
    fade = 1 - 0.5 * min(1.0, max(0.0, (xa - KICK_START) / (LENGTH / 2 - KICK_START)))
    return zk + CONCAVE * (y / ROUND) ** 2 * fade


def bottom(x, y):
    zk, a = kick(abs(x)); s = 1 if x >= 0 else -1
    return (x + s * THICK * math.sin(a), y, top(x, y) - THICK * math.cos(a))


def deck():
    m = MeshData('SM_SkateDeck')
    xs = x_samples(); tip = (0, len(xs) - 1)
    V_TOP = np.linspace(-1, 1, 7); V_BOT = np.linspace(-1, 1, 5)
    rng = np.random.default_rng(11)

    def rows(vs, fn):
        out = []
        for i, x in enumerate(xs):
            w = half_width(abs(x))
            if i in tip:
                p = fn(x, 0.0); vid = m.vert(p); out.append([vid] * len(vs))
            else:
                out.append([m.vert(fn(x, v * w)) for v in vs])
        return out

    T = rows(V_TOP, lambda x, y: (x, y, top(x, y)))
    B = rows(V_BOT, bottom)
    for i in range(len(xs) - 1):
        for j in range(len(V_TOP) - 1):
            k = rng.uniform(.94, 1.06)
            g = tuple(c * k for c in GRIP)
            m.face([T[i][j], T[i + 1][j], T[i + 1][j + 1], T[i][j + 1]], g, 'grip', False, want=(0, 0, 1))
        for j in range(len(V_BOT) - 1):
            m.face([B[i][j], B[i][j + 1], B[i + 1][j + 1], B[i + 1][j]], BOTTOM, 'board', False, want=(0, 0, -1))
    # laminated edge: five plies between the top and bottom perimeters
    plies = [PLY_LIGHT, PLY_DARK, PLY_LIGHT, PLY_DARK, PLY_LIGHT]
    for side, jt, jb in ((1, len(V_TOP) - 1, len(V_BOT) - 1), (-1, 0, 0)):
        ring = []
        for i in range(len(xs)):
            a = np.array(m.verts[T[i][jt]]); b = np.array(m.verts[B[i][jb]])
            ring.append([a + (b - a) * k / len(plies) for k in range(len(plies) + 1)])
        ids = [[m.vert(p) for p in r] for r in ring]
        for i in range(len(xs) - 1):
            x0, x1 = xs[i], xs[i + 1]
            for k, c in enumerate(plies):
                mid = np.mean([ring[i][k], ring[i + 1][k + 1]], axis=0)
                out = np.array([mid[0] * (1 if abs(mid[0]) > FLAT_END else 0), side * 1.0, 0.0])
                m.face([ids[i][k], ids[i + 1][k], ids[i + 1][k + 1], ids[i][k + 1]], c, 'board', False, want=out)
    # painted bottom graphic, 2 mm proud of the underside: red sun disc toward the nose, wave strokes by the tail
    off = 0.002
    def under(x, y):
        p = bottom(x, y); return (p[0], p[1], p[2] - off)
    cx, r = 0.078, 0.058
    ring = [under(cx + r * math.cos(t), r * math.sin(t)) for t in np.linspace(0, 2 * math.pi, 21)[:-1]]
    inner = [under(cx + r * .5 * math.cos(t), r * .5 * math.sin(t)) for t in np.linspace(0, 2 * math.pi, 21)[:-1]]
    c0 = m.vert(under(cx, 0)); ri = [m.vert(p) for p in inner]; ro = [m.vert(p) for p in ring]
    for k in range(20):
        m.face([c0, ri[k], ri[(k + 1) % 20]], SUN, 'board', want=(0, 0, -1))
        m.face([ri[k], ro[k], ro[(k + 1) % 20], ri[(k + 1) % 20]], SUN, 'board', want=(0, 0, -1))
    for x0, amp, width in ((-0.048, 0.009, 0.010), (-0.090, 0.009, 0.010), (-0.128, 0.006, 0.007)):
        ys = np.linspace(-0.082, 0.082, 33)
        centre = [(x0 + amp * math.sin(2 * math.pi * y / 0.072), y) for y in ys]
        left = [m.vert(under(x - width / 2, y)) for x, y in centre]
        right = [m.vert(under(x + width / 2, y)) for x, y in centre]
        for k in range(len(ys) - 1):
            m.face([left[k], left[k + 1], right[k + 1], right[k]], WAVE, 'board', want=(0, 0, -1))
    return m


def truck():
    """Front truck, origin at the baseplate top centre; axle 5.15 cm below."""
    m = MeshData('SM_SkateTruck')
    az = AXLE_Z - TRUCK_Z                  # -0.0515
    m.box((-0.032, -0.027, -0.006), (0.032, 0.027, 0.0), BASEPLATE, 'board', bottom=True)
    # baseplate boss: kingpin seat (toward -X) and the pivot cup (toward +X)
    m.poly([(-0.024, -0.012, -0.006), (0.022, -0.012, -0.006), (0.022, 0.012, -0.006), (-0.024, 0.012, -0.006)], BASEPLATE, 'board', want=(0, 0, 1))
    for (x0, z0), (x1, z1) in [((-0.024, -0.006), (-0.004, -0.022)), ((0.006, -0.006), (0.026, -0.026))]:
        m.box((x0, -0.012, z1), (x1, 0.012, z0), BASEPLATE, 'board', bottom=True)
    # hanger: a tapered body from the pivot down to the axle housing
    hz0, hz1 = -0.024, az
    top4 = [(-0.017, -0.021, hz0), (0.013, -0.021, hz0), (0.013, 0.021, hz0), (-0.017, 0.021, hz0)]
    bot4 = [(-0.010, -0.066, hz1), (0.010, -0.066, hz1), (0.010, 0.066, hz1), (-0.010, 0.066, hz1)]
    m.poly(top4, HANGER, 'board', want=(0, 0, 1))
    for k in range(4):
        a, b = top4[k], top4[(k + 1) % 4]; c, d = bot4[(k + 1) % 4], bot4[k]
        out = np.mean([a, b, c, d], axis=0); out[2] = 0
        m.poly([a, b, c, d], HANGER, 'board', want=out)
    # pivot arm into the cup
    m.box((0.010, -0.005, -0.032), (0.026, 0.005, -0.022), HANGER, 'board', bottom=True)
    # axle housing and axle
    m.lathe((0, 0, az), [(-0.072, 0.0), (-0.072, 0.0092), (0.072, 0.0092), (0.072, 0.0)], HANGER, 'board', sides=10, axis='y')
    m.lathe((0, 0, az), [(-0.113, 0.0), (-0.113, 0.0042), (0.113, 0.0042), (0.113, 0.0)], AXLE, 'board', sides=6, axis='y')
    for s in (-1, 1):
        y0 = s * 0.1105
        m.lathe((0, y0, az), [(-0.003, 0.0), (-0.003, 0.0065), (0.003, 0.0065), (0.003, 0.0)], AXLE, 'board', sides=6, axis='y')
    # kingpin with its bushing stack, leaning toward the board centre
    d = np.array([-math.sin(math.radians(38)), 0, -math.cos(math.radians(38))])
    p0 = np.array([-0.013, 0.0, -0.012])
    def seg(a, b, r, col, sides):
        u = np.array([0, 1.0, 0]); v = np.cross(d, u)
        rings = []
        for t in (a, b):
            c = p0 + d * t
            rings.append([c + (u * math.cos(q) + v * math.sin(q)) * r for q in np.linspace(0, 2 * math.pi, sides + 1)[:-1]])
        ids = [[m.vert(p) for p in rg] for rg in rings]
        for k in range(sides):
            j = (k + 1) % sides
            out = (rings[0][k] + rings[1][j]) / 2 - (p0 + d * (a + b) / 2)
            m.face([ids[0][k], ids[1][k], ids[1][j], ids[0][j]], col, 'board', True, want=out)
        m.poly(rings[0], col, 'board', want=-d); m.poly(rings[1], col, 'board', want=d)
    seg(0.000, 0.012, 0.0125, BUSHING, 10)
    seg(0.016, 0.026, 0.0115, BUSHING, 10)
    seg(0.0, 0.036, 0.0042, AXLE, 6)
    seg(0.030, 0.036, 0.0075, AXLE, 6)
    return m


def wheel():
    m = MeshData('SM_SkateWheel')
    h = WHEEL_W / 2; r = WHEEL_R
    prof = [(-0.012, 0.0), (-0.012, 0.0112), (-h, 0.0112), (-h, 0.0215), (-0.011, r), (0.011, r), (h, 0.0215), (h, 0.0112), (0.012, 0.0112), (0.012, 0.0)]
    m.lathe((0, 0, 0), prof[1:-1], URETHANE, 'board', sides=12, axis='y')
    # bearings: dark discs in the recesses (replace the first/last lathe band colour)
    for y, want in ((-0.012, (0, -1, 0)), (0.012, (0, 1, 0))):
        m.poly([(0.0112 * math.cos(t), y, 0.0112 * math.sin(t)) for t in 2 * math.pi * (np.arange(12) + .5) / 12], BEARING, 'board', want=want)
    # recess walls read darker
    for fi, f in enumerate(m.faces):
        pts = np.array([m.verts[i] for i in f])
        if np.all(np.abs(np.hypot(pts[:, 0], pts[:, 2]) - 0.0112) < 1e-4) and np.all(np.abs(pts[:, 1]) >= 0.0119):
            m.colors[fi] = [tuple(c * .55 for c in URETHANE)] * len(f)
    return m


def contract():
    """Numbers the checks compare with the built meshes (metres, Blender axes)."""
    return dict(length=LENGTH, width=WIDTH, kick_rise=KICK_RISE, kick_length=LENGTH / 2 - KICK_START, concave=CONCAVE,
                thickness=THICK, truck_x=TRUCK_X, truck_z=TRUCK_Z, axle_z=AXLE_Z, wheel_y=WHEEL_Y, wheel_r=WHEEL_R,
                ground_z=AXLE_Z - WHEEL_R)
