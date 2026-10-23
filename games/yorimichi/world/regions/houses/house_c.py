"""Selected house geometry; no regional export orchestration."""
import numpy as np
from houses.layout import HOUSES
from houses.construction import _band, bays, body_walls, eave_ends, fascia, gable_y, glass_door, koshi_window, lattice_door, mid, onigawara, pent, pots, ridge, step_stone, tiled, wall, wall_frame



def house_c(m):
    """Two storeys: a pent roof round the ground floor, a gabled upper roof, a balcony, the genkan under a small gable."""
    w, d, fl, top = 9.2, 7.2, .45, 3.10
    uw, ud, uz, utop = 7.8, 5.8, 3.40, 6.0
    door = HOUSES['C']['door_x']
    m.box((0, 0, (fl + top) / 2), (w, d, top - fl), 'plaster')
    m.box((0, 0, (uz - .2 + utop) / 2), (uw, ud, utop - uz + .2), 'plaster')
    m.collider((0, 0, 1.8), (w, d, 3.6)); m.collider((0, 0, 4.7), (uw, ud, 2.6))
    front = [-4.6, -2.3, 0, 1.45, 3.35, 4.6]

    def dress(side, L, posts):
        if side == 'front':
            for x0, x1 in zip(front[:2], front[1:3]):
                bw = (x1 - x0) / 2
                for k in range(2): glass_door(m, x0 + bw * (k + .5), bw - .02, fl, 1.8)
            with m.at((door, 0, 0)):
                for k in (-1, 1): lattice_door(m, k * .43, .86, .12, 2.0)
            m.bar((door, -.02, .06), (1.9, .06, .12), 'stone')
            koshi_window(m, mid(front, 2), 1.8, .8, .8)
            koshi_window(m, mid(front, 4), 1.8, .6, .8)
            return
        m.bar((0, -.01, (fl + 1.2) / 2), (L - .02, .04, 1.2 - fl), 'board')
        for k in (0, 2): koshi_window(m, mid(posts, k), 1.8, 1.0, .8)
    body_walls(m, w, d, fl, top, 2.3, lambda side, L: front if side == 'front' else bays(L, 4), dress)
    # the upper storey: glass doors onto the balcony, windows round the rest
    for side in ('front', 'back', 'left', 'right'):
        L = uw if side in ('front', 'back') else ud
        posts = bays(L, 3)
        with wall(m, side, uw, ud):
            wall_frame(m, L, uz, utop, posts, 5.45)
            if side == 'front':
                for j in (-1, 1): glass_door(m, j * L / 12, L / 6 - .02, uz + .18, 1.8)
                for k in (0, 2): koshi_window(m, mid(posts, k), 4.6, 1.3, .9)
            elif side == 'back':
                for k in (0, 2): koshi_window(m, mid(posts, k), 4.7, 1.2, .8)
            else:
                koshi_window(m, mid(posts, 1), 4.7, 1.0, .8)
    pent(m, (-uw / 2, uw / 2, -ud / 2, ud / 2), (-5.6, 5.6, -4.6, 4.6), uz + .08, 2.82)
    # balcony over the pent roof, in front of the middle bay's glass doors
    by0, by1, bz, bx = -ud / 2, -ud / 2 - .95, uz + .18, 1.9
    m.box((0, (by0 + by1) / 2, bz - .04), (2 * bx, .95, .08), 'timber_light')
    for x in np.linspace(-bx + .05, bx - .05, 4):
        m.box((float(x), by1 + .04, bz + .45), (.08, .08, .9), 'timber')
        m.beam((float(x), by1 + .04, bz - .06), (float(x), by0 - .02, bz - .4), .07, .07, 'timber')
    for s in (-1, 1): m.box((s * (bx - .05), (by0 + by1) / 2, bz + .9), (.08, .95, .07), 'timber_light')
    m.box((0, by1 + .04, bz + .9), (2 * bx, .12, .07), 'timber_light')
    m.box((0, by1 + .04, bz + .12), (2 * bx, .07, .06), 'timber')
    for x in np.linspace(-bx + .15, bx - .15, 19): m.box((float(x), by1 + .04, bz + .5), (.035, .035, .7), 'timber_light')
    # the upper gable roof, its ridge along x
    xe, ye, ze, p = uw / 2 + .65, ud / 2 + .95, 5.62, .52
    zr = ze + ye * p
    for s in (-1, 1):
        tiled(m, [(-xe, s * ye, ze), (xe, s * ye, ze), (xe, 0, zr), (-xe, 0, zr)], (0, -s))
        fascia(m, (-xe, s * ye), (xe, s * ye), ze)
        eave_ends(m, (-xe + .3, s * ye), (xe - .3, s * ye), ze, (0, s), p)
        gz0 = zr - .16
        m.poly([(s * uw / 2, -ud / 2, utop - .02), (s * uw / 2, ud / 2, utop - .02), (s * uw / 2, 0, gz0)], 'plaster', out=(s, 0, 0))
        with m.at((s * uw / 2, 0, 0), 90 * s):
            m.bar((0, -.03, utop + .08), (ud, .06, .12), 'timber')
            m.bar((0, -.03, utop + .75), (ud * .5, .06, .10), 'timber')
            m.bar((0, -.03, (utop + gz0) / 2), (.12, .06, gz0 - utop), 'timber')
        for sy in (-1, 1): m.beam((s * (xe + .02), sy * ye, ze - .05), (s * (xe + .02), 0, zr - .05), .08, .26, 'timber')
        onigawara(m, s * (xe + .05), 0, zr, 0)
    ridge(m, (-xe, 0, zr), (xe, 0, zr), .34, .38)
    # the genkan's gable on the pent roof, its steps and pots
    gable_y(m, door, 1.0, -3.4, -4.6, 2.62, .6, .2)
    step_stone(m, door, -4.0, .12, 1.4, .6)
    step_stone(m, door, -4.75, .06, 1.0, .5)
    pots(m, door - 1.5, -4.0)
