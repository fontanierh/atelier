"""Selected house geometry; no regional export orchestration."""
import math
import numpy as np
from houses.layout import HOUSES
from houses.geometry_mesh import R, variant
from houses.construction import amado, bays, body_walls, engawa, koshi_window, mid, post, pots, shoji, step_stone, tiled
from houses.construction import _band

def house_b(m):
    """Thatched farmhouse: steep hipped thatch, engawa with storm shutters and shoji, wide earth-floored entrance,
    woodpile lean-to."""
    w, d, fl, top = 11.0, 7.4, .50, 2.55
    door = HOUSES['B']['door_x']
    m.box((0, 0, (fl + top) / 2), (w, d, top - fl), 'plaster')
    m.box((0, 0, top + .6), (w - .2, d - .2, 1.2), 'soffit')                  # the loft, up under the thatch
    m.collider((0, 0, 2.0), (w, d, 4.0))

    def dress(side, L, posts):
        if side == 'front':
            bay = L / 6
            for k in range(4):                                                  # the engawa: shutters, then shoji
                for j in range(2): (amado if k < 2 else shoji)(m, posts[k] + bay / 4 + j * bay / 2, bay / 2 - .02, fl, 1.55)
                m.bar((mid(posts, k), -.03, 2.3), (bay - .16, .04, .3), 'plaster_shade')
            with m.at((door, 0, 0)):                                           # the doma door: wide planks
                m.bar((0, -.05, 1.0), (1.9, .05, 2.0), 'timber')
                for k in range(6): m.bar((-.8 + k * .32, -.08, 1.0), (.03, .03, 1.95), 'board')
                m.bar((0, -.09, 1.95), (2.1, .06, .12), 'timber_light')
            m.bar((door, -.02, .08), (2.3, .06, .16), 'stone')
            koshi_window(m, mid(posts, 5), 1.55, 1.0, .7)
            return
        for k in range(len(posts) - 1):
            m.bar((mid(posts, k), -.012, (fl + top) / 2 - .1), (posts[k + 1] - posts[k] - .18, .03, top - fl - .3), variant('board', .12))
        if side == 'left': koshi_window(m, mid(posts, 1), 1.7, 1.0, .7)
        if side == 'back': koshi_window(m, mid(posts, 4), 1.7, 1.2, .7)
    body_walls(m, w, d, fl, top, 2.1, lambda side, L: bays(L, 6 if L > 10 else 4), dress)
    ye = engawa(m, -5.5, 1.75, -3.7, .92)
    step_stone(m, -2.0, ye - .27, .25, .9, .45)
    m.box((-5.22, -3.95, 1.3), (.5, .4, 1.6), 'board')
    step_stone(m, door, -4.05, .12, 1.5, .6)
    pots(m, door - 1.6, -4.05)
    # thatch: a steep hip, thick at the eave, a tiled ridge cap with crossed ridge logs
    xe, yf, yb, ze, p, t = 6.9, -5.2, 5.2, 2.65, .85, .5
    yc = (yf + yb) / 2; zr = ze + (yc - yf) * p; xr = xe - (yc - yf)
    for pts, out in (([(-xe, yf, ze), (xe, yf, ze), (xr, yc, zr), (-xr, yc, zr)], (0, -1, 1)),
                     ([(xe, yb, ze), (-xe, yb, ze), (-xr, yc, zr), (xr, yc, zr)], (0, 1, 1)),
                     ([(xe, yf, ze), (xe, yb, ze), (xr, yc, zr)], (1, 0, 1)),
                     ([(-xe, yb, ze), (-xe, yf, ze), (-xr, yc, zr)], (-1, 0, 1))):
        m.poly(pts, 'thatch', out=out)
        m.poly([(x, y, z - t) for x, y, z in pts], 'soffit', out=(-out[0], -out[1], -1))
        # a darker, older band toward the ridge and a lighter trimmed band along the eave, standing proud
        for z0, z1, key in ((ze + (zr - ze) * .62, zr + 1, 'thatch_dark'), (ze - 1, ze + (zr - ze) * .16, 'thatch_light')):
            m.poly([(x + out[0] * .02, y + out[1] * .02, z + .02) for x, y, z in _band(pts, z0, z1)], variant(key, .04), out=out)
    ring = [(-xe, yf), (xe, yf), (xe, yb), (-xe, yb)]
    for (x0, y0), (x1, y1) in zip(ring, ring[1:] + ring[:1]):                 # the thick cut edge, in two layers
        nx, ny = (y1 - y0), -(x1 - x0); ln = math.hypot(nx, ny); nx, ny = nx / ln, ny / ln
        if nx * (x0 + x1) + ny * (y0 + y1) < 0: nx, ny = -nx, -ny
        m.poly([(x0, y0, ze), (x1, y1, ze), (x1, y1, ze - t * .55), (x0, y0, ze - t * .55)], 'thatch_cut', out=(nx, ny, 0))
        m.poly([(x0 - nx * .06, y0 - ny * .06, ze - t * .55), (x1 - nx * .06, y1 - ny * .06, ze - t * .55),
                (x1 - nx * .06, y1 - ny * .06, ze - t), (x0 - nx * .06, y0 - ny * .06, ze - t)], 'thatch_dark', out=(nx, ny, 0))
    m.box((0, yc, zr + .12), (2 * xr + 1.2, .9, .40), 'tile_edge', .05)
    m.box((0, yc, zr + .38), (2 * xr + .9, .42, .20), 'tile_roll', .04)
    for x in np.linspace(-xr + .1, xr - .1, 4):
        for s in (-1, 1): m.beam((float(x), -s * .75, zr - .15), (float(x), s * .55, zr + .75), .10, .10, 'log')
    for s in (-1, 1): m.beam((s * (xr + .5), yc, zr + .2), (s * (xr + .9), yc, zr + .55), .16, .16, 'log')
    # lean-to over the woodpile on the +x side, under the thatch's eave
    lx0, lx1 = w / 2, 7.6
    for y in (-2.3, 2.3): post(m, lx1 - .1, y, 0, 1.72, .13)
    m.box((lx1 - .1, 0, 1.68), (.14, 4.9, .14), 'timber')
    tiled(m, [(lx0, -2.8, 2.0), (lx0, 2.8, 2.0), (lx1 + .3, 2.8, 1.70), (lx1 + .3, -2.8, 1.70)], (-1, 0),
          body='board', roll='timber_light', spacing=.42, r=.04, under=.08)
    for row in range(3):
        for k in range(8 - row):
            y = -1.75 + k * .47 + row * .235; z = .18 + row * .31
            m.log((lx0 + .1, y, z), (lx0 + 1.75 + R.uniform(-.08, .08), y, z), .16, variant('log', .15), variant('log_end', .1))
    m.collider(((lx0 + lx1) / 2, 0, 1.0), (lx1 - lx0, 4.8, 2.0))


