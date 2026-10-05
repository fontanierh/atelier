"""Kawara: Japanese clay-tile roofs at the scale the art direction paints them (assets/hidamari/houses/*/concept.jpg).

A slope is a field of round tile rolls running from the eave up to the ridge, each roll a half-octagon on the dark
channel tiles with its own shade, a lip at each course, ending at the eave in a round end tile; hips and ridges are
stacked noshi courses under a round cap with an onigawara block at each end; the eaves show rafter tails over a fascia
and carry a copper half-round gutter. Every function works in the caller's frame (Mesh.at); slopes are described by an affine map
S(u, t) -> (x, y, z), u across the slope in metres and t from the eave (0) to the top (1).
"""
import math
from village import build as v

PITCH = .3                     # roll spacing across the slope
ROLL = .068                    # roll radius
KEYS = {'channel': 'kw_roof_channel', 'roll': 'kw_roof_tile', 'edge': 'kw_roof_ridge', 'rafter': 'hs_trim_wood',
        'fascia': 'hs_trim_wood', 'soffit': 'wood_dark', 'gutter': 'kw_copper_metal'}


def palette():
    # weathered blue-grey clay, lighter than the village's near-black 'roof' as the concepts paint it
    v.PALETTE.update({'kw_roof_tile': (.085, .095, .12), 'kw_roof_channel': (.045, .05, .064),
                      'kw_roof_ridge': (.065, .072, .092), 'kw_copper_metal': (.36, .17, .075)})


def _sub(a, b): return (a[0]-b[0], a[1]-b[1], a[2]-b[2])
def _add(a, b, s=1.): return (a[0]+b[0]*s, a[1]+b[1]*s, a[2]+b[2]*s)
def _cross(a, b): return (a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0])
def _unit(a):
    n = math.sqrt(sum(c*c for c in a)) or 1.
    return (a[0]/n, a[1]/n, a[2]/n)


def face(m, pts, key, toward):
    """A polygon wound so its normal points along toward."""
    n = _cross(_sub(pts[1], pts[0]), _sub(pts[2], pts[0]))
    m.poly(pts if sum(a*b for a, b in zip(n, toward)) >= 0 else pts[::-1], key)


def slope(m, S, u0, u1, tmax=lambda u: 1., steps=6, keys=KEYS):
    """The tiles of one slope S over u0..u1, each roll stopping at tmax(u) (a hip or a verge); returns the normal."""
    across = _unit(_sub(S(1., 0.), S(0., 0.))); up = _unit(_sub(S(0., 1.), S(0., 0.)))
    n = _unit(_cross(across, up))
    if n[2] < 0: n = (-n[0], -n[1], -n[2])
    # the channel tiles: one surface under the rolls, in rows so a hip can trim it
    cols = max(1, math.ceil((u1-u0)/PITCH))
    us = [u0+(u1-u0)*k/cols for k in range(cols+1)]
    for a, b in zip(us, us[1:]):
        ta, tb = min(1., tmax(a)), min(1., tmax(b))
        if max(ta, tb) <= 0: continue
        ta, tb = max(ta, 0.), max(tb, 0.)
        face(m, [S(a, 0), S(b, 0), S(b, tb), S(a, ta)], keys['channel'], n)
    # the rolls
    for k in range(cols):
        u = u0+(k+.5)*(u1-u0)/cols; tm = min(1., tmax(u)-.02)
        if tm <= .03: continue
        key = v.color_variant(keys['roll'], .06)
        ts = [tm*j/steps for j in range(steps+1)]
        angles = [0, math.pi/3, 2*math.pi/3, math.pi]
        def p(t, a): return _add(_add(S(u+ROLL*math.cos(a), t), n, ROLL*.9*math.sin(a)+.008), up, 0)
        for t0, t1 in zip(ts, ts[1:]):
            for a0, a1 in zip(angles, angles[1:]):
                am = (a0+a1)/2
                face(m, [p(t0, a0), p(t0, a1), p(t1, a1), p(t1, a0)], key,
                     _add(_add((0, 0, 0), n, math.sin(am)), across, math.cos(am)))
        # each tile's lower end, a little proud of the roll above it: a half-octagon lip facing the eave on every
        # course, and at the eave the round end tile, a full octagon
        def lip(t, r, full=False):
            c = _add(S(u, t), n, .008); arc = [k*math.pi/4 for k in range(8 if full else 5)]
            face(m, [_add(_add(c, across, r*math.cos(a)), n, r*.9*math.sin(a)) for a in arc], key, (-up[0], -up[1], -up[2]))
        lip(0, ROLL*1.4, full=True)
        for j in range(1, steps):lip(ts[j], ROLL*1.22)
    return n


def ridge(m, a, b, key=KEYS['edge'], courses=3, oni=True):
    """A stacked ridge from a to b: noshi courses narrowing upwards, a round cap and an onigawara block at each end."""
    z = 0.
    for k in range(courses):
        w = .36-.05*k
        m.beam(_add(a, (0, 0, z+.035)), _add(b, (0, 0, z+.035)), w, .07, v.color_variant(key, .03)); z += .075
    m.beam(_add(a, (0, 0, z+.07)), _add(b, (0, 0, z+.07)), .2, .14, key)
    if not oni: return
    d = _unit(_sub(b, a)); along = abs(d[0]) >= .5
    for p, s in ((a, -1), (b, 1)):                 # onigawara: a plate across the ridge end, a little taller
        c = _add(p, d, s*.06)
        m.box((c[0], c[1], c[2]+.22), (.14, .46, .42) if along else (.46, .14, .42), key, .03)
        m.box((c[0], c[1], c[2]+.46), (.18, .3, .08) if along else (.3, .18, .08), key, .02)


def hip(m, a, b, key=KEYS['edge']):
    """A hip roll from the eave corner a up to the ridge end b."""
    m.beam(a, b, .3, .12, v.color_variant(key, .03))
    m.beam(_add(a, (0, 0, .09)), _add(b, (0, 0, .09)), .2, .12, key)


def eave(m, a, b, out, z_wall, wall_y, keys=KEYS, rafters=True, gutter=True):
    """Under an eave edge from a to b (the slope's t=0 line), out the horizontal unit vector away from the wall:
    a fascia board, rafter tails back to the wall line at height z_wall, and a copper half-round gutter."""
    out = (out[0], out[1], 0.)
    m.beam(_add(a, (0, 0, -.1)), _add(b, (0, 0, -.1)), .06, .2, keys['fascia'])
    L = math.dist(a[:2], b[:2]); d = _unit(_sub(b, a))
    if rafters:
        n = int(L/.46)
        for k in range(1, n):
            p = _add(a, d, k*L/n)
            back = (p[0]-out[0]*wall_y, p[1]-out[1]*wall_y, z_wall)
            m.beam(_add(p, (0, 0, -.12)), back, .07, .09, keys['rafter'])
    if gutter:
        g = _add(_add(a, out, .1), (0, 0, -.16)); h = _add(_add(b, out, .1), (0, 0, -.16))
        m.beam(g, h, .14, .1, keys['gutter'])


def downpipe(m, top, wall, z0=.15, key=KEYS['gutter']):
    """From a gutter point top, an elbow to the wall point wall (x, y) and straight down it to z0."""
    elbow = (wall[0], wall[1], top[2]-.45)
    m.beam(top, (top[0], top[1], top[2]-.2), .07, .07, key)
    m.beam((top[0], top[1], top[2]-.2), elbow, .07, .07, key)
    m.beam(elbow, (wall[0], wall[1], z0), .075, .075, key)
    for z in (z0+.9, (z0+elbow[2])/2, elbow[2]-.3):
        m.box((wall[0], wall[1], z), (.11, .11, .04), key)


def gable(m, w, d, eave_z, rise, overhang=.75, keys=KEYS, oni=True, gutters=True, courses=3):
    """A tiled gable roof over a w x d body centred on the origin, ridge along x: two sagging slopes of rolls, verge
    rolls and bargeboards, a stacked ridge with onigawara, rafter tails, fascias and gutters. Returns the eave height
    of the gutter line and the ridge height."""
    palette()
    W_, D_ = w+2*overhang, d+2*overhang
    top = eave_z+rise
    for sy in (-1, 1):
        def S(u, t, sy=sy): return (u, sy*D_/2*(1-t), eave_z+rise*t)
        slope(m, S, -W_/2, W_/2)
        # verge: a roll of tiles along each gable edge over a deep bargeboard
        for sx in (-1, 1):
            a, b = S(sx*W_/2, 0), S(sx*W_/2, 1)
            m.beam(_add(a, (0, 0, .07)), _add(b, (0, 0, .07)), .2, .16, keys['edge'])
            m.beam(_add(a, (sx*.02, 0, -.12)), _add(b, (sx*.02, 0, -.12)), .09, .3, keys['fascia'])
        # soffit under the overhang, then the eave's rafters, fascia and gutter
        face(m, [(-W_/2, sy*D_/2, eave_z-.03), (W_/2, sy*D_/2, eave_z-.03), (W_/2, sy*d/2, eave_z+rise*overhang/(D_/2)-.03),
                 (-W_/2, sy*d/2, eave_z+rise*overhang/(D_/2)-.03)], keys['soffit'], (0, 0, -1))
        eave(m, S(-W_/2+.05, 0), S(W_/2-.05, 0), (0, sy), eave_z+rise*overhang/(D_/2)-.1, overhang, keys, gutter=gutters)
    # under the ridge, the gable walls' triangles are the caller's; a ridge on top
    ridge(m, (-W_/2-.05, 0, top+.02), (W_/2+.05, 0, top+.02), keys['edge'], courses, oni=oni)
    return eave_z, top


def hipped(m, w, d, eave_z, rise, overhang=.75, keys=KEYS, gutters=True):
    """A tiled hipped roof over a w x d body centred on the origin (w >= d): two long slopes and two hipped ends of
    rolls trimmed at the hips, hip rolls, a short stacked ridge, rafter tails, fascias and gutters all round."""
    palette()
    W_, D_ = w+2*overhang, d+2*overhang
    rh = (W_-D_)/2; top = eave_z+rise
    for sy in (-1, 1):                    # the long slopes: u along x, cut where |u| passes the hip line
        def S(u, t, sy=sy): return (u, sy*D_/2*(1-t), eave_z+rise*t)
        slope(m, S, -W_/2, W_/2, lambda u: (W_/2-abs(u))/(W_/2-rh) if W_/2 > rh else 1.)
    for sx in (-1, 1):                    # the hipped ends: u along y
        def S(u, t, sx=sx): return (sx*(W_/2-(W_/2-rh)*t), u, eave_z+rise*t)
        slope(m, S, -D_/2, D_/2, lambda u: 1-abs(u)/(D_/2))
    for sx in (-1, 1):
        for sy in (-1, 1):hip(m, (sx*W_/2, sy*D_/2, eave_z+.04), (sx*rh, 0, top+.04))
    ridge(m, (-rh, 0, top+.02), (rh, 0, top+.02), keys['edge'], oni=True)
    zw = eave_z+rise*overhang/(D_/2)-.1
    m.box((0, 0, zw), (w+.1, d+.1, .1), keys['soffit'])
    m.poly([(-W_/2, D_/2, eave_z-.03), (W_/2, D_/2, eave_z-.03), (W_/2, -D_/2, eave_z-.03), (-W_/2, -D_/2, eave_z-.03)], keys['soffit'])
    for (p, q), out in ((((-W_/2+.3, -D_/2), (W_/2-.3, -D_/2)), (0, -1)), (((-W_/2+.3, D_/2), (W_/2-.3, D_/2)), (0, 1)),
                        (((W_/2, -D_/2+.3), (W_/2, D_/2-.3)), (1, 0)), (((-W_/2, -D_/2+.3), (-W_/2, D_/2-.3)), (-1, 0))):
        eave(m, (*p, eave_z), (*q, eave_z), out, zw, overhang, keys, gutter=gutters)
    return eave_z, top


def pent(m, x0, x1, y, z, depth, drop=.38, keys=KEYS, gutter=True):
    """A tiled pent roof (hisashi) along a wall at y facing -y, from height z at the wall falling drop over depth:
    rolls, a ridge flashing against the wall, rafters, fascia and gutter."""
    palette()
    def S(u, t): return (u, y-depth*(1-t), z-drop*(1-t))
    slope(m, S, x0, x1, steps=3)
    m.beam((x0, y-.06, z+.06), (x1, y-.06, z+.06), .14, .12, keys['edge'])
    face(m, [(x0, y-depth, z-drop-.03), (x1, y-depth, z-drop-.03), (x1, y, z-.05), (x0, y, z-.05)], keys['soffit'], (0, 0, -1))
    eave(m, S(x0+.05, 0), S(x1-.05, 0), (0, -1), z-.12, depth, keys, gutter=gutter)
