"""Selected house geometry; no regional export orchestration."""
from mathutils import Vector
import numpy as np
from houses.geometry_mesh import newell, variant

def tiled(m, pts, up, body='tile', roll='tile_roll', spacing=.34, r=.055, under=.16):
    """One tiled roof face: the convex polygon `pts`, round-tile rolls running up the slope (`up`: horizontal, toward
    the ridge) and its underside `under` metres below."""
    P = [np.array(p, float) for p in pts]
    n = np.array(newell([Vector(p) for p in pts])); n /= np.linalg.norm(n)
    if n[2] < 0: n = -n
    m.poly(pts, body, out=n)
    m.poly([(p[0], p[1], p[2] - under) for p in pts], 'soffit', out=-n)
    v = np.array([up[0], up[1], 0.], float); v -= n * v.dot(n); v /= np.linalg.norm(v)
    u = np.cross(v, n); o = P[0]
    S = [float((p - o).dot(u)) for p in P]; T = [float((p - o).dot(v)) for p in P]
    for s in np.arange(min(S) + spacing / 2, max(S) - spacing / 4, spacing):
        ts = []
        for a in range(len(P)):
            b = (a + 1) % len(P)
            if (S[a] - s) * (S[b] - s) < 0: ts.append(T[a] + (T[b] - T[a]) * (s - S[a]) / (S[b] - S[a]))
        if len(ts) < 2 or max(ts) - min(ts) < .25: continue
        t0, t1 = min(ts), max(ts) - .03
        a0 = o + u * s + v * t0; a1 = o + u * s + v * t1
        L0, L1, R0, R1, C0, C1 = a0 - u * r, a1 - u * r, a0 + u * r, a1 + u * r, a0 + n * r * 1.2, a1 + n * r * 1.2
        c = variant(roll, .05)
        m.poly([L0, L1, C1, C0], c, out=n - u); m.poly([C0, C1, R1, R0], c, out=n + u); m.poly([L0, C0, R0], c, out=-v)


def ridge(m, a, b, w=.34, h=.36, color='tile_edge'):
    m.beam((a[0], a[1], a[2] + h / 2 - .08), (b[0], b[1], b[2] + h / 2 - .08), w, h, color)


def onigawara(m, x, y, z, yaw):
    """The ridge-end tile, a plate across the ridge's end."""
    with m.at((x, y, z), yaw):
        m.box((0, 0, .20), (.18, .46, .55), 'tile_edge', .05)
        m.box((0, 0, .52), (.14, .56, .14), 'tile_edge', .03)


def eave_ends(m, a, b, z, out, pitch, under=.16, spacing=.46, color='timber_light'):
    """Rafters under an eave edge from a to b (xy), their ends toward `out`, just under the roof's underside."""
    a, b = np.array(a, float), np.array(b, float); L = np.linalg.norm(b - a); d = (b - a) / L; o = np.array(out, float)
    z0 = z - under - .055; n = int(L / spacing)
    for k in range(1, n):
        p = a + d * k * L / n
        m.beam((p[0] - o[0] * .9, p[1] - o[1] * .9, z0 + .9 * pitch), (p[0] - o[0] * .1, p[1] - o[1] * .1, z0 + .1 * pitch), .075, .09, color)


def fascia(m, a, b, z, h=.18, color='timber'):
    m.beam((a[0], a[1], z - h / 2 + .02), (b[0], b[1], z - h / 2 + .02), .09, h, color)


def irimoya(m, xe, yf, yb, ze, p, a, g):
    """Hip-and-gable roof: eaves round the rectangle +-xe by yf..yb at ze, pitch p. The hips run `a` in to where the
    gable (tsuma) stands; the upper gable roof overhangs it by g."""
    yc = (yf + yb) / 2; zr = ze + (yc - yf) * p; xr = xe - a; zm = ze + a * p
    xg = xr + g; zg = ze + (a - g) * p
    front = [(-xe, yf, ze), (xe, yf, ze), (xg, yf + a - g, zg), (xg, yc, zr), (-xg, yc, zr), (-xg, yf + a - g, zg)]
    back = [(x, yb + yf - y, z) for x, y, z in front]
    tiled(m, front, (0, 1)); tiled(m, back, (0, -1))
    for s in (-1, 1):
        tiled(m, [(s * xe, yf, ze), (s * xe, yb, ze), (s * xr, yb - a, zm), (s * xr, yf + a, zm)], (-s, 0))
        # the gable: plaster in a timber frame, set back under the upper roof, a gegyo board under the ridge end
        m.poly([(s * xr, yf + a, zm), (s * xr, yb - a, zm), (s * xr, yc, zr - .05)], 'plaster', out=(s, 0, 0))
        m.beam((s * (xr + .03), yf + a, zm + .06), (s * (xr + .03), yb - a, zm + .06), .12, .16, 'timber')
        m.beam((s * (xr + .03), yf + a + .8, zm + .45), (s * (xr + .03), yb - a - .8, zm + .45), .09, .10, 'timber')
        m.beam((s * (xr + .03), yc, zm), (s * (xr + .03), yc, zr - .1), .10, .10, 'timber')
        m.box((s * (xg + .02), yc, zr - .45), (.08, .34, .55), 'timber_light', .03)
        for yy, sy in ((yf, 1), (yb, -1)):
            m.beam((s * (xg + .02), yy + sy * (a - g), zg - .05), (s * (xg + .02), yc, zr - .05), .08, .26, 'timber')   # verge board
            ridge(m, (s * xe, yy, ze), (s * xg, yy + sy * (a - g), zg), .22, .22)                                    # hip
            m.beam((s * xe, yy, ze + .08), (s * (xe + .22), yy - sy * .22, ze + .34), .18, .18, 'tile_edge')      # its turned-up end
        onigawara(m, s * (xg + .05), yc, zr, 0)
        fascia(m, (s * xe, yf), (s * xe, yb), ze)
    ridge(m, (-xg, yc, zr), (xg, yc, zr), .36, .40)
    m.beam((-xg + .4, yc, zr + .30), (xg - .4, yc, zr + .30), .22, .14, 'tile_roll')
    for yy in (yf, yb): fascia(m, (-xe, yy), (xe, yy), ze)


def gable_y(m, xc, half, y0, y1, ze, p, g=.25):
    """A small gabled porch roof, its ridge along y from the house (y0) out to its front (y1 < y0)."""
    zr = ze + half * p
    for s in (-1, 1):
        tiled(m, [(xc + s * half, y1 - g, ze), (xc + s * half, y0, ze), (xc, y0, zr), (xc, y1 - g, zr)], (-s, 0), spacing=.30)
        m.beam((xc + s * half, y1 - g - .02, ze - .02), (xc, y1 - g - .02, zr - .02), .08, .24, 'timber')   # verge board
        fascia(m, (xc + s * half, y0), (xc + s * half, y1 - g), ze)
    m.poly([(xc - half + .25, y1, ze + .08), (xc + half - .25, y1, ze + .08), (xc, y1, zr - .15)], 'plaster', out=(0, -1, 0))
    m.beam((xc - half + .2, y1 + .02, ze + .05), (xc + half - .2, y1 + .02, ze + .05), .14, .16, 'timber')
    ridge(m, (xc, y0 - .3, zr), (xc, y1 - g, zr), .26, .30)
    onigawara(m, xc, y1 - g - .03, zr, 90)
    m.poly([(xc - half, y0, ze - .16), (xc + half, y0, ze - .16), (xc + half, y1 - g, ze - .16), (xc - half, y1 - g, ze - .16)],
           'soffit', out=(0, 0, -1))


def pent(m, inner, outer, zi, zo):
    """A pent roof (hisashi) round a storey: from the rectangle `inner` (x0, x1, y0, y1) at zi down to `outer` at zo."""
    (a0, a1, b0, b1), (c0, c1, d0, d1) = inner, outer
    for pts, up in (([(c0, d0, zo), (c1, d0, zo), (a1, b0, zi), (a0, b0, zi)], (0, 1)),
                    ([(c1, d1, zo), (c0, d1, zo), (a0, b1, zi), (a1, b1, zi)], (0, -1)),
                    ([(c1, d0, zo), (c1, d1, zo), (a1, b1, zi), (a1, b0, zi)], (-1, 0)),
                    ([(c0, d1, zo), (c0, d0, zo), (a0, b0, zi), (a0, b1, zi)], (1, 0))):
        tiled(m, pts, up, under=.14)
    corners = [(c0, d0), (c1, d0), (c1, d1), (c0, d1)]; inner_c = [(a0, b0), (a1, b0), (a1, b1), (a0, b1)]
    for (x, y), (xi, yi) in zip(corners, inner_c): ridge(m, (x, y, zo), (xi, yi, zi), .18, .18)
    for (x0, y0), (x1, y1) in zip(corners, corners[1:] + corners[:1]): fascia(m, (x0, y0), (x1, y1), zo, .15)


def post(m, x, y, z0, z1, s=.15, stone=True, color='timber'):
    m.box((x, y, (z0 + z1) / 2), (s, s, z1 - z0), color)
    if stone:
        m.lathe((x, y, z0 - .02), [(0, s * 1.35), (.10, s * 1.4), (.17, s * 1.05), (.19, 0)], variant('stone_light', .08), 8)


def glass_door(m, x, w, z0, h):
    m.bar((x, -.05, z0 + h / 2), (w, .04, h), 'glass')
    for xx in (x - w / 2 + .03, x + w / 2 - .03): m.bar((xx, -.08, z0 + h / 2), (.06, .05, h), 'timber_light')
    for zz, hh in ((z0 + .16, .32), (z0 + h * .62, .04), (z0 + h - .03, .06)):
        m.bar((x, -.085, zz), (w - .06, .05, hh), 'timber_light' if hh > .1 else 'timber')


def shoji(m, x, w, z0, h, cols=3, rows=5):
    m.bar((x, -.04, z0 + h / 2), (w, .03, h), 'shoji')
    for xx in (x - w / 2 + .025, x + w / 2 - .025): m.bar((xx, -.07, z0 + h / 2), (.05, .04, h), 'timber_light')
    for k in range(1, cols): m.bar((x - w / 2 + w * k / cols, -.065, z0 + h / 2), (.022, .03, h - .05), 'timber_light')
    for k in range(1, rows): m.bar((x, -.065, z0 + h * k / rows), (w - .04, .03, .022), 'timber_light')
    m.bar((x, -.07, z0 + .12), (w - .04, .04, .24), 'timber_light')


def lattice_door(m, x, w, z0, h, pitch=.085):
    m.bar((x, -.04, z0 + h / 2), (w, .03, h), 'board')
    for xx in (x - w / 2 + .03, x + w / 2 - .03): m.bar((xx, -.08, z0 + h / 2), (.06, .05, h), 'timber_light')
    for zz in (z0 + .05, z0 + h * .45, z0 + h - .04): m.bar((x, -.08, zz), (w - .06, .05, .07), 'timber_light')
    n = int(w / pitch)
    for k in range(1, n): m.bar((x - w / 2 + k * w / n, -.07, z0 + h / 2), (.025, .03, h - .1), 'timber_light')


def koshi_window(m, x, z, w, h):
    """A paper window behind a timber lattice (koshi)."""
    m.bar((x, -.02, z), (w, .03, h), 'shoji')
    for dz in (-1, 1): m.bar((x, -.05, z + dz * (h / 2 + .035)), (w + .14, .06, .07), 'timber')
    for dx in (-1, 1): m.bar((x + dx * (w / 2 + .035), -.05, z), (.07, .06, h), 'timber')
    n = max(2, int(w / .11))
    for k in range(1, n): m.bar((x - w / 2 + k * w / n, -.06, z), (.03, .04, h), 'timber')
    m.bar((x, -.09, z - h / 2 - .09), (w + .24, .08, .05), 'timber')


def amado(m, x, w, z0, h):
    """A wooden storm shutter."""
    m.bar((x, -.06, z0 + h / 2), (w - .01, .05, h), variant('board', .12))
    for k in (1, 2): m.bar((x, -.09, z0 + h * k / 3), (w - .05, .03, .035), 'timber')


def wall_frame(m, w, z0, z1, posts, kamoi=None):
    """Posts, sill, top beam and door head on a wall face."""
    for x in posts: m.bar((x, -.02, (z0 + z1) / 2), (.16, .06, z1 - z0), 'timber')
    m.bar((0, -.03, z0 + .06), (w + .04, .07, .14), 'timber')
    m.bar((0, -.03, z1 - .08), (w + .04, .08, .18), 'timber')
    if kamoi: m.bar((0, -.035, kamoi), (w + .02, .08, .12), 'timber')


def skirt(m, w, z1, posts):
    """Under the raised floor: a dark recessed skirt between posts on foundation stones."""
    m.bar((0, .03, z1 / 2), (w, .04, z1), 'skirt')
    for x in posts: post(m, x, -.02, .0, z1, .16, True)


def wall(m, side, w, d):
    """The wall frame of one side of a w x d body: front (-y), back (+y), left (-x), right (+x)."""
    return {'front': m.at((0, -d / 2, 0), 0), 'back': m.at((0, d / 2, 0), 180),
            'left': m.at((-w / 2, 0, 0), -90), 'right': m.at((w / 2, 0, 0), 90)}[side]


def bays(L, n):
    return [-L / 2 + k * L / n for k in range(n + 1)]


def mid(posts, k):
    return (posts[k] + posts[k + 1]) / 2


def body_walls(m, w, d, fl, top, kamoi, posts_of, dress):
    """Skirt, frame and whatever `dress(side, L, posts)` adds, on each of the four walls."""
    for side in ('front', 'back', 'left', 'right'):
        L = w if side in ('front', 'back') else d
        posts = posts_of(side, L)
        with wall(m, side, w, d):
            skirt(m, L, fl, [p for p in posts if abs(p) < L / 2 - .01] + [-L / 2 + .08, L / 2 - .08])
            wall_frame(m, L, fl, top, posts, kamoi)
            dress(side, L, posts)


def pots(m, x, y):
    for dx, sc, key in ((0, .9, 'clay'), (.45, .7, 'bluepot')):
        with m.at((x + dx, y, 0)):
            m.lathe((0, 0, 0), [(a * sc, b * sc) for a, b in [(0, 0), (.02, .16), (.25, .22), (.40, .19), (.40, 0)]], key, 8)
            m.lathe((0, 0, .40 * sc), [(0, .17 * sc), (.12 * sc, .24 * sc), (.30 * sc, .12 * sc), (.34 * sc, 0)], variant('leaf', .2), 7)


def step_stone(m, x, y, z, w, d):
    """A flat stone step, its top at z."""
    m.box((x, y, z / 2 - .02), (w, d, z + .04), variant('stone_light', .08), .05)
    m.collider((x, y, z / 2), (w, d, max(z, .05)))


def engawa(m, x0, x1, y_wall, depth, top=.5):
    """The veranda along the front: boards, an edge beam on short posts, its collision box. Returns its edge."""
    boards = int(round(depth / .23))
    for k in range(boards):
        m.box(((x0 + x1) / 2, y_wall - (k + .5) * depth / boards, top - .03), (x1 - x0, depth / boards - .01, .06), variant('timber_light', .07))
    ye = y_wall - depth
    m.box(((x0 + x1) / 2, ye + .06, top - .1), (x1 - x0, .12, .12), 'timber')
    for x in np.linspace(x0 + .1, x1 - .1, 5): post(m, float(x), ye + .06, 0, top - .16, .11)
    m.collider(((x0 + x1) / 2, y_wall - depth / 2, top / 2), (x1 - x0, depth, top))
    return ye



def _band(pts, z0, z1):
    """The part of a planar polygon between heights z0 and z1."""
    def clip(poly, level, above):
        out = []
        for a, b in zip(poly, poly[1:] + poly[:1]):
            ina = a[2] >= level if above else a[2] <= level
            inb = b[2] >= level if above else b[2] <= level
            if ina: out.append(a)
            if ina != inb:
                s = (level - a[2]) / (b[2] - a[2]); out.append(tuple(a[i] + (b[i] - a[i]) * s for i in range(3)))
        return out
    return clip(clip(list(pts), z0, True), z1, False)
