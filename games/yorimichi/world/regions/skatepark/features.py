"""Skate pier geometry in park-local metres (see layout.py). No bpy: MeshData only.

Riding surfaces are the collision (complex as simple), so every ramp surface is one clean
shared-vertex patch, ramps start exactly on floor grid lines and the floor has holes under
solid features (no coplanar overlap, no lips)."""
import math
import numpy as np
import layout as L
from geom import MeshData, PAL

XS, YS = L.grid_lines()


def P(axis, u, w, z):
    return (u, w, z) if axis == 'x' else (w, u, z)


def wl(lines, a, b, extra=()):
    v = sorted(set([round(x, 6) for x in L.lines_between(lines, a, b)] + [round(a, 6), round(b, 6)] + [round(e, 6) for e in extra]))
    out = [v[0]]
    for x in v[1:]:
        if x - out[-1] > 1e-4: out.append(x)
    return out


def ramp(m, prof, axis, wlines, color, want, tag='paint', color_fn=None):
    rows = [[P(axis, u, w, z) for w in wlines] for u, z in prof]
    return m.grid(rows, color, tag, True, want, color_fn)


def side_fan(m, axis, w, pts_uz, anchor_uz, color, want, tag='wall'):
    m.fan_polygon([P(axis, u, w, z) for u, z in pts_uz], P(axis, anchor_uz[0], w, anchor_uz[1]), color, tag, want)


def wall(m, axis, u, w0, w1, z0, z1, color, want, tag='wall', wlines=None, zsteps=None):
    """Vertical wall at constant `axis` coordinate u (axis 'x': wall in the y-z plane)."""
    ws = wlines if wlines is not None else [w0, w1]
    n = zsteps or max(1, int(math.ceil((z1 - z0) / 0.6)))
    zs = [z0 + (z1 - z0) * k / n for k in range(n + 1)]
    rows = [[P(axis, u, w, z) for w in ws] for z in zs]
    m.grid(rows, color, tag, False, want)


def flat(m, x0, x1, y0, y1, z, color, tag='concrete', want=(0, 0, 1), xl=None, yl=None, color_fn=None):
    xs = xl if xl is not None else wl(XS, x0, x1)
    ys = yl if yl is not None else wl(YS, y0, y1)
    rows = [[(x, y, z) for y in ys] for x in xs]
    return m.grid(rows, color, tag, False, want, color_fn)


def railing(m, pts, height, color='railing', post_every=2.0, post=0.06, top_r=0.028, mid_r=0.02, base_z=None):
    """Posts and two round rails along a straight run a->b (x, y, z-base)."""
    a = np.array(pts[0], float); b = np.array(pts[1], float)
    L_ = np.linalg.norm(b[:2] - a[:2]); n = max(1, int(math.ceil(L_ / post_every)))
    for k in range(n + 1):
        p = a + (b - a) * k / n
        m.box((p[0] - post / 2, p[1] - post / 2, p[2] - 0.03), (p[0] + post / 2, p[1] + post / 2, p[2] + height - top_r), color, 'railing')
    m.tube([a + (0, 0, height - top_r), b + (0, 0, height - top_r)], top_r, color, 'railing', sides=8)
    m.tube([a + (0, 0, height * .5), b + (0, 0, height * .5)], mid_r, color, 'railing', sides=6)


def steel_side_band(m, axis, w, u0, u1, z_top, out_sign, zlen=L.STEEL_BAND, proud=0.002):
    """Vertical flange of the steel angle on a side face, 2 mm proud."""
    ww = w + out_sign * proud
    want = (0, out_sign, 0) if axis == 'x' else (out_sign, 0, 0)
    m.poly([P(axis, u0, ww, z_top - zlen), P(axis, u1, ww, z_top - zlen), P(axis, u1, ww, z_top), P(axis, u0, ww, z_top)], 'steel', 'steel', want=want)


def steel_side_band_sloped(m, axis, w, top_uz, out_sign, zlen=L.STEEL_BAND, proud=0.002):
    ww = w + out_sign * proud
    want = (0, out_sign, 0) if axis == 'x' else (out_sign, 0, 0)
    for (u0, z0), (u1, z1) in zip(top_uz[:-1], top_uz[1:]):
        m.poly([P(axis, u0, ww, z0 - zlen), P(axis, u1, ww, z1 - zlen), P(axis, u1, ww, z1), P(axis, u0, ww, z0)], 'steel', 'steel', want=want)


# ----------------------------------------------------------------------------- features
def big_quarter(m):
    q = L.BIG_QP; prof, toe, _ = L.big_qp_profile(); ys = wl(YS, q['y0'], q['y1'])
    ramp(m, prof, 'x', ys, 'teal', want=(-1, 0, 1))
    lip, h, back = q['lip_x'], q['height'], q['deck_x']
    flat(m, lip, back, q['y0'], q['y1'], h, 'concrete', xl=[lip, lip + .5, lip + 1.0, lip + 1.5, back], yl=ys)
    wall(m, 'x', back, q['y0'], q['y1'], -0.05, h, 'concrete', (1, 0, 0), wlines=ys)
    for y, s in ((q['y0'], -1), (q['y1'], 1)):
        side_fan(m, 'x', y, prof + [(back, h)], (back, -0.05), 'concrete', (0, s, 0))
    cx, cz = L.big_coping()
    m.tube([(cx, q['y0'], cz), (cx, q['y1'], cz)], L.COPING_R, 'coping', 'coping', sides=10)
    rx = back - 0.1
    railing(m, [(rx, q['y0'] + .05, h), (rx, q['y1'] - .05, h)], q['rail_h'], post_every=3.0)


def mini_quarter(m):
    q = MINI = L.MINI_QP; prof, toe, _ = L.mini_qp_profile(); ys = wl(YS, q['y0'], q['y1'])
    ramp(m, prof, 'x', ys, 'salmon', want=(1, 0, 1))
    lip, h, back = q['lip_x'], q['height'], q['deck_x']
    flat(m, back, lip, q['y0'], q['y1'], h, 'concrete', xl=[back, back + .5, back + 1.0, back + 1.5, lip], yl=ys)
    wall(m, 'x', back, q['y0'], q['y1'], -0.05, h, 'concrete', (-1, 0, 0), wlines=ys)
    for y, s in ((q['y0'], -1), (q['y1'], 1)):
        side_fan(m, 'x', y, prof + [(back, h)], (back, -0.05), 'concrete', (0, s, 0))
    cx, cz = L.mini_coping()
    m.tube([(cx, q['y0'], cz), (cx, q['y1'], cz)], L.COPING_R, 'coping', 'coping', sides=10)
    rx = back + 0.1
    railing(m, [(rx, q['y0'] + .05, h), (rx, q['y1'] - .05, h)], q['rail_h'], post_every=2.5)


def kicker(m):
    k = L.KICKER; prof, r, ang = L.kicker_profile()
    # a 6 cm steel lip plate at the top of the curve
    t_band = 0.06 / r; a_end = math.radians(ang)
    band = (k['toe_x'] + r * math.sin(a_end - t_band), r * (1 - math.cos(a_end - t_band)))
    prof = [p for p in prof if p[0] < band[0] - 1e-4] + [band, prof[-1]]
    ys = wl(YS, k['y0'], k['y1'])
    n = len(prof) - 1
    ramp(m, prof, 'x', ys, 'salmon', want=(-1, 0, 2), color_fn=lambda i, j: 'steel' if i == n - 1 else 'salmon')
    wall(m, 'x', k['lip_x'], k['y0'], k['y1'], -0.05, k['height'], 'concrete', (1, 0, 0), wlines=ys, zsteps=1)
    for y, s in ((k['y0'], -1), (k['y1'], 1)):
        side_fan(m, 'x', y, prof, (k['lip_x'], -0.05), 'concrete', (0, s, 0))


def funbox(m):
    f = L.FUNBOX; prof, (t0, t1) = L.funbox_profile()
    ys = wl(YS, f['y0'], f['y1'], extra=(f['y0'] + L.STEEL_BAND, f['y1'] - L.STEEL_BAND))
    on_top = [i for i in range(len(prof) - 1) if prof[i][0] >= t0 - 1e-6 and prof[i + 1][0] <= t1 + 1e-6]
    last = len(ys) - 2
    def col(i, j):
        if i in on_top and j in (0, last): return 'steel'
        if i in on_top: return 'concrete_light'
        return 'mustard'
    ids = ramp(m, prof, 'x', ys, 'mustard', want=(0, 0, 1), color_fn=col)
    # the flat top reads as concrete, not paint
    xm = (t0 + t1) / 2
    for y, s in ((f['y0'], -1), (f['y1'], 1)):
        side_fan(m, 'x', y, prof, (xm, -0.05), 'concrete', (0, s, 0))
        steel_side_band(m, 'x', y, t0, t1, f['height'], s)


def platform(m):
    p = L.PLATFORM; b = L.PLATFORM_BANK; s = L.STAIRS; hb = L.HUBBA; h = p['height']
    xs = wl(XS, p['x0'], p['x1'], extra=(hb['x0'],)); ys = wl(YS, p['y0'], p['y1'], extra=(hb['y0'], hb['y1'], s['y0'], s['y1']))
    flat(m, p['x0'], p['x1'], p['y0'], p['y1'], h, 'concrete', xl=xs, yl=ys)
    # walls: west, south, the part of the north wall beside the bank, the east wall around the stairs
    wall(m, 'x', p['x0'], p['y0'], p['y1'], -0.05, h, 'concrete', (-1, 0, 0), wlines=ys)
    wall(m, 'y', p['y0'], p['x0'], p['x1'], -0.05, h, 'concrete', (0, -1, 0), wlines=xs)
    wall(m, 'y', p['y1'], b['x1'], p['x1'], -0.05, h, 'concrete', (0, 1, 0), wlines=wl(xs, b['x1'], p['x1']))
    top_riser = h - s['rise']
    wall(m, 'x', p['x1'], p['y0'], hb['y0'], -0.05, h, 'concrete', (1, 0, 0), wlines=wl(ys, p['y0'], hb['y0']))
    wall(m, 'x', p['x1'], s['y0'], s['y1'], top_riser, h, 'concrete', (1, 0, 0), wlines=wl(ys, s['y0'], s['y1']), zsteps=1)
    wall(m, 'x', p['x1'], s['y1'], p['y1'], -0.05, h, 'concrete', (1, 0, 0), wlines=wl(ys, s['y1'], p['y1']))
    # the long bank up to the platform (rises southward)
    prof = L.platform_bank_profile(); bx = wl(XS, b['x0'], b['x1'])
    ramp(m, prof, 'y', bx, 'teal', want=(0, 1, 3))
    for x, sgn in ((b['x0'], -1), (b['x1'], 1)):
        side_fan(m, 'y', x, prof, (p['y1'], -0.05), 'concrete', (sgn, 0, 0))
    # own railing on the sea and west sides
    rail_h = L.RAILING_H
    railing(m, [(p['x0'] + .1, p['y0'] + .1, h), (p['x1'] - .1, p['y0'] + .1, h)], rail_h)
    railing(m, [(p['x0'] + .1, p['y0'] + .1, h), (p['x0'] + .1, p['y1'] - .1, h)], rail_h)


def stairs(m):
    s = L.STAIRS; h = L.PLATFORM['height']
    ys = wl(YS, s['y0'], s['y1'])
    for k in range(1, s['risers']):
        xa = s['x_top'] + s['tread'] * (k - 1); xb = xa + s['tread']; z = h - s['rise'] * k
        nose = 0.06
        flat(m, xa, xb, s['y0'], s['y1'], z, 'concrete', xl=[xa, xb - nose, xb], yl=ys,
             color_fn=lambda i, j: 'concrete_dark' if i == 1 else 'concrete')
        wall(m, 'x', xb, s['y0'], s['y1'], z - s['rise'], z, 'concrete', (1, 0, 0), wlines=ys, zsteps=1)
        # open north side of the flight
        m.poly([(xa, s['y1'], -0.05), (xb, s['y1'], -0.05), (xb, s['y1'], z), (xa, s['y1'], z)], 'concrete', 'wall', want=(0, 1, 0))
    # handrail down the middle: axis offset below the top contact line, three round posts
    hr = L.HANDRAIL; axis = L.offset_polyline(L.handrail_top(), hr['r'])
    m.tube([(x, hr['y'], z) for x, z in axis], hr['r'], 'red', 'rail', sides=10)
    def axis_z(x):
        a = np.array(axis); return float(np.interp(x, a[:, 0], a[:, 1]))
    def ground(x):
        if x <= s['x_top']: return h
        k = int((x - s['x_top']) // s['tread']) + 1
        return h - s['rise'] * k if k < s['risers'] else 0.0
    for x in (hr['x0'] + 0.2, s['x_top'] + s['tread'] * 2.5, hr['x1'] - 0.15):
        m.tube([(x, hr['y'], ground(x) - 0.03), (x, hr['y'], axis_z(x) - hr['r'] * .5)], 0.024, 'red', 'rail', sides=8, caps=False)


def hubba(m):
    hb = L.HUBBA; s = L.STAIRS; h = L.PLATFORM['height']
    top = L.hubba_top()                                  # (x, z) flat on the platform, then down the stairs
    y0, y1 = hb['y0'], hb['y1']; b = L.STEEL_BAND
    ys = [y0, y0 + b, (y0 + y1) / 2, y1 - b, y1]
    xs = sorted(set([top[0][0], top[1][0], top[2][0]] + [x for x in XS if top[0][0] < x < top[2][0]]))
    zt = lambda x: float(np.interp(x, [p[0] for p in top], [p[1] for p in top]))
    rows = [[(x, y, zt(x)) for y in ys] for x in xs]
    m.grid(rows, 'concrete_light', 'concrete', False, (0, 0, 1), color_fn=lambda i, j: 'steel' if j in (0, 3) else 'concrete_light')
    # sides: the block sits on the platform (x < x_top) and on the floor beyond
    for y, sgn in ((y0, -1), (y1, 1)):
        pts = [(x, zt(x)) for x in xs]
        side = [(x, y, z) for x, z in pts]
        # platform part: rectangle over z in [h, top]
        m.poly([(top[0][0], y, h), (s['x_top'], y, h), (s['x_top'], y, top[1][1]), (top[0][0], y, top[0][1])], 'concrete_light', 'wall', want=(0, sgn, 0))
        # floor part: fan from the bottom corner under the stair top
        m.fan_polygon([(x, y, zt(x)) for x in xs if x >= s['x_top'] - 1e-9] + [(top[2][0], y, -0.05)], (s['x_top'], y, -0.05), 'concrete_light', 'wall', (0, sgn, 0))
        steel_side_band_sloped(m, 'x', y, [(x, zt(x)) for x in xs], sgn)
    m.poly([(top[0][0], y0, h), (top[0][0], y1, h), (top[0][0], y1, top[0][1]), (top[0][0], y0, top[0][1])], 'concrete_light', 'wall', want=(-1, 0, 0))
    m.poly([(top[2][0], y0, -0.05), (top[2][0], y1, -0.05), (top[2][0], y1, top[2][1]), (top[2][0], y0, top[2][1])], 'concrete_light', 'wall', want=(1, 0, 0))


def ledge_box(m, x0, x1, y0, y1, h, top_color='concrete_light', side_color='concrete_light', steel_x=False, steel_y=True):
    b = L.STEEL_BAND
    xs = wl(XS, x0, x1, extra=((x0 + b, x1 - b) if steel_x else ()))
    ys = wl(YS, y0, y1, extra=((y0 + b, y1 - b) if steel_y else ()))
    lx, ly = len(xs) - 2, len(ys) - 2
    def col(i, j):
        if steel_y and j in (0, ly): return 'steel'
        if steel_x and i in (0, lx): return 'steel'
        return top_color
    flat(m, x0, x1, y0, y1, h, top_color, 'concrete', xl=xs, yl=ys, color_fn=col)
    wall(m, 'y', y0, x0, x1, -0.05, h, side_color, (0, -1, 0), wlines=xs, zsteps=1)
    wall(m, 'y', y1, x0, x1, -0.05, h, side_color, (0, 1, 0), wlines=xs, zsteps=1)
    wall(m, 'x', x0, y0, y1, -0.05, h, side_color, (-1, 0, 0), wlines=ys, zsteps=1)
    wall(m, 'x', x1, y0, y1, -0.05, h, side_color, (1, 0, 0), wlines=ys, zsteps=1)
    if steel_y:
        steel_side_band(m, 'x', y0, x0, x1, h, -1); steel_side_band(m, 'x', y1, x0, x1, h, 1)
    if steel_x:
        steel_side_band(m, 'y', x0, y0, y1, h, -1); steel_side_band(m, 'y', x1, y0, y1, h, 1)


def manual_pad(m):
    p = L.MANUAL_PAD
    ledge_box(m, p['x0'], p['x1'], p['y0'], p['y1'], p['height'], top_color='dusty_blue', side_color='concrete', steel_x=True, steel_y=True)


def benches(m):
    b = L.BENCH
    for x0, x1 in L.BENCHES:
        ledge_box(m, x0, x1, b['y0'], b['y1'], b['height'])


def flat_bars(m):
    for bar in L.BARS:
        cz = bar['top'] - L.BAR_R
        m.tube([(bar['x0'], bar['y'], cz), (bar['x1'], bar['y'], cz)], L.BAR_R, bar['color'], 'rail', sides=10)
        for x in (bar['x0'] + 0.25, (bar['x0'] + bar['x1']) / 2, bar['x1'] - 0.25):
            m.box((x - .025, bar['y'] - .025, -0.03), (x + .025, bar['y'] + .025, cz), bar['color'], 'rail')


def south_bank(m):
    b = L.SOUTH_BANK; prof = L.south_bank_profile(); xs = wl(XS, b['x0'], b['x1'])
    back = -L.HALF_Y + L.RAIL_INSET; h = b['height']; n = len(prof) - 1
    ramp(m, prof, 'y', xs, 'dusty_blue', want=(0, 1, 1), color_fn=lambda i, j: 'steel' if i == n - 1 else 'dusty_blue')
    rows = [[(x, y, h) for x in xs] for y in (b['top_y'], b['top_y'] - L.STEEL_BAND, b['top_y'] - .5, back)]
    m.grid(rows, 'concrete', 'concrete', False, (0, 0, 1), color_fn=lambda i, j: 'steel' if i == 0 else 'concrete')
    wall(m, 'y', back, b['x0'], b['x1'], -0.05, h, 'concrete', (0, -1, 0), wlines=xs)
    for x, s in ((b['x0'], -1), (b['x1'], 1)):
        side_fan(m, 'y', x, prof + [(back, h)], (back, -0.05), 'concrete', (s, 0, 0))
    railing(m, [(b['x0'] + .1, back + .1, h), (b['x1'] - .1, back + .1, h)], L.RAILING_H)


PAINTS = {PAL[k] for k in ('teal', 'salmon', 'mustard', 'dusty_blue')}
STEELS = {PAL['steel'], PAL['coping']}
CONCRETES = {PAL[k] for k in ('concrete', 'concrete_light', 'concrete_dark')}


def retag(m):
    """Surface tags follow the base colour: steel stays steel, paint wears, concrete varies."""
    for fi, cols in enumerate(m.colors):
        c = tuple(cols[0])
        if c in STEELS: m.tags[fi] = 'steel' if m.tags[fi] != 'coping' else 'coping'
        elif c in PAINTS: m.tags[fi] = 'paint'
        elif c in CONCRETES and m.tags[fi] in ('paint',): m.tags[fi] = 'concrete'


def park_features():
    m = MeshData('SM_SkateParkFeatures')
    for fn in (big_quarter, mini_quarter, kicker, funbox, platform, stairs, hubba, manual_pad, benches, flat_bars, south_bank):
        fn(m)
    retag(m)
    return m


def decals():
    """Faded floor paint: the Yorimichi sun and three wave strokes (4 mm above the deck, no collision)."""
    m = MeshData('SM_SkateParkDecals'); z = L.DECAL_Z
    sun = L.FLOOR_SUN; n = 48
    red = (0.42, 0.075, 0.048); ink = (0.055, 0.10, 0.18)
    radii = list(np.linspace(sun['r'] / 6, sun['r'], 6))
    rings = [[(sun['x'] + r * math.cos(t), sun['y'] + r * math.sin(t), z) for t in 2 * math.pi * np.arange(n) / n] for r in radii]
    c = m.vert((sun['x'], sun['y'], z)); ids = [[m.vert(p) for p in ring] for ring in rings]
    for k in range(n):
        m.face([c, ids[0][k], ids[0][(k + 1) % n]], red, 'decal', want=(0, 0, 1))
        for a in range(len(radii) - 1):
            m.face([ids[a][k], ids[a + 1][k], ids[a + 1][(k + 1) % n], ids[a][(k + 1) % n]], red, 'decal', want=(0, 0, 1))
    for x0, x1, y0 in L.FLOOR_WAVES:
        xs = np.linspace(x0, x1, 57); w = 0.16
        cy = y0 + 0.32 * np.sin(2 * math.pi * (xs - x0) / 2.35)
        dy = np.gradient(cy, xs); nrm = np.column_stack([-dy, np.ones_like(dy)]); nrm /= np.linalg.norm(nrm, axis=1)[:, None]
        left = [m.vert((x - nx * w, y - ny * w, z)) for x, y, (nx, ny) in zip(xs, cy, nrm)]
        right = [m.vert((x + nx * w, y + ny * w, z)) for x, y, (nx, ny) in zip(xs, cy, nrm)]
        for k in range(len(xs) - 1):
            m.face([left[k], left[k + 1], right[k + 1], right[k]], ink, 'decal', want=(0, 0, 1))
    return m


# ----------------------------------------------------------------------------- pier
def pier():
    m = MeshData('SM_SkatePier')
    holes = list(L.footprints().values())
    V = {}
    def vid(i, j):
        if (i, j) not in V: V[(i, j)] = m.vert((XS[i], YS[j], 0.0))
        return V[(i, j)]
    for i in range(len(XS) - 1):
        cx = (XS[i] + XS[i + 1]) / 2
        for j in range(len(YS) - 1):
            cy = (YS[j] + YS[j + 1]) / 2
            if any(x0 < cx < x1 and y0 < cy < y1 for x0, x1, y0, y1 in holes): continue
            joint = any(abs(cx - j) < L.JOINT_W / 2 for j in L.JOINTS_X) or any(abs(cy - j) < L.JOINT_W / 2 for j in L.JOINTS_Y)
            m.face([vid(i, j), vid(i + 1, j), vid(i + 1, j + 1), vid(i, j + 1)], 'joint' if joint else 'concrete', 'deck', False, want=(0, 0, 1))
    # edge fascia (downstand beam) and the slab underside
    hx, hy = L.HALF_X, L.HALF_Y; fz = -0.70; bw = 0.30
    for axis, u, lines, want in (('y', -hy, XS, (0, -1, 0)), ('y', hy, XS, (0, 1, 0)), ('x', -hx, YS, (-1, 0, 0)), ('x', hx, YS, (1, 0, 0))):
        wall(m, axis, u, lines[0], lines[-1], fz, 0.0, 'concrete_dark', want, tag='wall', wlines=list(lines), zsteps=1)
    for axis, u, a, b_, want in (('y', -hy + bw, -hx + bw, hx - bw, (0, 1, 0)), ('y', hy - bw, -hx + bw, hx - bw, (0, -1, 0)),
                                 ('x', -hx + bw, -hy + bw, hy - bw, (1, 0, 0)), ('x', hx - bw, -hy + bw, hy - bw, (-1, 0, 0))):
        wall(m, axis, u, a, b_, fz, -L.SLAB, 'underside', want, tag='underside', zsteps=1)
    for x0, x1, y0, y1 in ((-hx, hx, -hy, -hy + bw), (-hx, hx, hy - bw, hy), (-hx, -hx + bw, -hy + bw, hy - bw), (hx - bw, hx, -hy + bw, hy - bw)):
        m.poly([(x0, y0, fz), (x0, y1, fz), (x1, y1, fz), (x1, y0, fz)], 'underside', 'underside', want=(0, 0, -1))
    ux = np.linspace(-hx + bw, hx - bw, 21); uy = np.linspace(-hy + bw, hy - bw, 13)
    m.grid([[(x, y, -L.SLAB) for y in uy] for x in ux], 'underside', 'underside', False, (0, 0, -1))
    # perimeter railing (blocks, not grindable) with the entrance gap; the platform and the
    # south bank carry their own railings where they meet the edge
    e = hx - L.RAIL_INSET; f = hy - L.RAIL_INSET; gap = (L.ENTRANCE_X - 2.5, L.ENTRANCE_X + 2.5)
    p = L.PLATFORM; sb = L.SOUTH_BANK
    runs = [((-e, f), (gap[0], f)), ((gap[1], f), (e, f)), ((e, f), (e, -f)), ((-e, f), (-e, -f)),
            ((-e, -f), (p['x0'], -f)), ((p['x1'], -f), (sb['x0'], -f)), ((sb['x1'], -f), (e, -f))]
    for a, b_ in runs:
        railing(m, [(a[0], a[1], 0.0), (b_[0], b_[1], 0.0)], L.RAILING_H)
    for x, y in L.LAMPS:
        lamp(m, x, y)
    return m


def lamp(m, x, y):
    m.box((x - .16, y - .16, -0.02), (x + .16, y + .16, 0.28), 'concrete_dark', 'concrete')
    m.lathe((x, y, 0.28), [(0, 0.075), (4.25, 0.06), (4.25, 0.0)], 'pole', 'pole', sides=8)
    m.box((x - .19, y - .19, 4.22), (x + .19, y + .19, 4.28), 'lamp_cap', 'pole', bottom=True)
    m.box((x - .16, y - .16, 4.28), (x + .16, y + .16, 4.72), 'lamp', 'lamp')
    m.lathe((x, y, 4.72), [(0, 0.0), (0, 0.26), (0.18, 0.05), (0.18, 0.0)], 'lamp_cap', 'pole', sides=4)


def pilings(h_world):
    import sys
    sys.path.insert(0, str(L.JAPAN))
    from village.layout import sample
    m = MeshData('SM_SkatePierPilings')
    ox, oy, oz = L.ORIGIN
    xs = np.linspace(-36, 36, 10); ys = np.linspace(-24, 24, 7)
    cap_top, cap_bot = -L.SLAB, -1.0
    for y in ys:
        m.box((-L.HALF_X + .3, y - .3, cap_bot), (L.HALF_X - .3, y + .3, cap_top), 'underside', 'pile', bottom=True)
        for x in xs:
            bed = float(sample(h_world, ox + x, oy + y)) - oz
            prof = [(bed - 0.6 - cap_bot, 0.30), (cap_top - 0.02 - cap_bot, 0.30), (cap_top - 0.02 - cap_bot, 0.0)]
            base = len(m.faces)
            m.lathe((x, y, cap_bot), [(bed - 0.6 - cap_bot, 0.0)] + prof, 'pile', 'pile', sides=10)
            # wet / algae bands by world height
            for fi in range(base, len(m.faces)):
                cols = []
                for vi in m.faces[fi]:
                    wz = m.verts[vi][2] + oz
                    c = np.array(PAL['pile'])
                    if wz < 0.9: c = c * 0.5 + np.array(PAL['algae']) * 0.5 if wz > -0.4 else np.array(PAL['pile_wet'])
                    cols.append(tuple(c))
                m.colors[fi] = cols
    return m


# ----------------------------------------------------------------------------- path
def path_railing(m, run, height=1.1, every=2.0):
    """Railing following a polyline of base points (x, y, z on the path surface)."""
    run = np.array(run, float)
    d = np.r_[0, np.cumsum(np.linalg.norm(np.diff(run[:, :2], axis=0), axis=1))]
    n = max(1, int(math.ceil(d[-1] / every)))
    for t in np.linspace(0, d[-1], n + 1):
        p = np.array([np.interp(t, d, run[:, i]) for i in range(3)])
        m.box((p[0] - .03, p[1] - .03, p[2] - .03), (p[0] + .03, p[1] + .03, p[2] + height - .028), 'railing', 'railing')
    keep = [0] + [i for i in range(1, len(run) - 1) if int(d[i] // 1.0) != int(d[i - 1] // 1.0)] + [len(run) - 1]
    m.tube([run[i] + (0, 0, height - .028) for i in keep], 0.028, 'railing', 'railing', sides=8)
    m.tube([run[i] + (0, 0, height * .5) for i in keep], 0.02, 'railing', 'railing', sides=6)


def path(pl, h_world):
    """Path in park-local metres: level cross-sections, dark joints every 3 m, edge bands and a
    skirt down past the ground on both sides so it never floats or sinks out of sight."""
    import sys
    sys.path.insert(0, str(L.JAPAN))
    from village.layout import upper_surface
    m = MeshData('SM_SkatePath')
    ox, oy, oz = L.ORIGIN
    Pw, s, n, z = pl['P'], pl['s'], pl['n'], pl['z']
    # sample positions: the profile samples plus 5 cm joint strips every 3 m
    joints = [j for j in np.arange(3.0, s[-1] - 1.0, 3.0)]
    ss = np.unique(np.r_[s, joints, np.array(joints) + 0.05])
    Px = np.interp(ss, s, Pw[:, 0]); Py = np.interp(ss, s, Pw[:, 1]); Z = np.interp(ss, s, z)
    nx = np.interp(ss, s, n[:, 0]); ny = np.interp(ss, s, n[:, 1]); nn = np.hypot(nx, ny); nx /= nn; ny /= nn
    road = np.array(pl['road'])
    def road_z(x, y):
        d = np.hypot(road[:, 0] - x, road[:, 1] - y); i = int(np.argmin(d))
        a, b = (i - 1, i) if i > 0 and (i == len(road) - 1 or d[i - 1] < d[i + 1]) else (i, i + 1)
        A, B = road[a], road[b]; t = np.clip(((x - A[0]) * (B[0] - A[0]) + (y - A[1]) * (B[1] - A[1])) / ((B[0] - A[0]) ** 2 + (B[1] - A[1]) ** 2), 0, 1)
        return float(A[2] + (B[2] - A[2]) * t + 0.06)
    rows = []
    for k in range(len(ss)):
        row = []
        for o in L.PATH_OFFSETS:
            x = Px[k] + nx[k] * o; y = Py[k] + ny[k] * o
            zz = road_z(x, y) if k == 0 else Z[k]
            row.append((x - ox, y - oy, zz - oz))
        rows.append(row)
    jset = set(np.searchsorted(ss, joints))
    edge = {0, len(L.PATH_OFFSETS) - 2}
    def col(i, j):
        if i in jset: return 'joint'
        return 'concrete_dark' if j in edge else 'concrete'
    m.grid(rows, 'concrete', 'path', True, (0, 0, 1), color_fn=col)
    # skirts
    for side, j in ((-1, 0), (1, len(L.PATH_OFFSETS) - 1)):
        top = [rows[k][j] for k in range(len(ss))]
        bot = []
        for (x, y, zz) in top:
            g = float(upper_surface(h_world, x + ox, y + oy)) - oz
            # the terrain may be a little lower between samples: reach well past it
            lowest = min(g, *(float(upper_surface(h_world, x + ox + dx, y + oy + dy)) - oz for dx, dy in ((.7, 0), (-.7, 0), (0, .7), (0, -.7))))
            bot.append((x, y, min(zz - 0.25, lowest - 0.45)))
        ids_t = [m.vert(p) for p in top]; ids_b = [m.vert(p) for p in bot]
        for k in range(len(ss) - 1):
            want = (nx[k] * side, ny[k] * side, 0)
            zt = (top[k][2] + top[k + 1][2]) / 2; zb = (bot[k][2] + bot[k + 1][2]) / 2
            c_top = PAL['skirt']; c_bot = tuple(c * 0.55 for c in PAL['skirt'])
            m.face([ids_b[k], ids_b[k + 1], ids_t[k + 1], ids_t[k]], [c_bot, c_bot, c_top, c_top], 'skirt', False, want=want)
        # guard railing wherever this side stands more than 1.2 m above the ground
        high = np.array([t[2] - g for t, g in zip(top, [float(upper_surface(h_world, x + ox, y + oy)) - oz for x, y, _ in top])]) > 1.2
        k = 0
        while k < len(ss):
            if not high[k]: k += 1; continue
            e = k
            while e + 1 < len(ss) and high[e + 1]: e += 1
            a, b = max(0, k - 4), min(len(ss) - 1, e + 4)
            if ss[b] - ss[a] > 4.0:
                inset = 0.15
                run = [(top[q][0] - nx[q] * side * inset, top[q][1] - ny[q] * side * inset, top[q][2]) for q in range(a, b + 1)]
                path_railing(m, run)
            k = e + 1
    # start cap (under the road edge) and end cap (inside the pier edge beam)
    for k, sgn in ((0, -1), (len(ss) - 1, 1)):
        a = rows[k][0]; b = rows[k][-1]
        ga = min(a[2] - 0.6, float(upper_surface(h_world, a[0] + ox, a[1] + oy)) - oz - 0.45)
        gb = min(b[2] - 0.6, float(upper_surface(h_world, b[0] + ox, b[1] + oy)) - oz - 0.45)
        t = (Px[k] - Px[k - sgn] if k else Px[1] - Px[0], Py[k] - Py[k - sgn] if k else Py[1] - Py[0])
        m.poly([a, b, (b[0], b[1], gb), (a[0], a[1], ga)], 'skirt', 'skirt', want=(t[0] * sgn, t[1] * sgn, 0))
    return m, ss, rows
