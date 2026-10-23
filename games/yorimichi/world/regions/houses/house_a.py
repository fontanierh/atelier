"""Selected house geometry; no regional export orchestration."""
from houses.layout import HOUSES
from houses.construction import bays, body_walls, eave_ends, engawa, gable_y, glass_door, irimoya, koshi_window, lattice_door, mid, post, pots, step_stone

def house_a(m):
    """Tiled single-storey house: irimoya roof, engawa with glass doors, gabled entrance porch."""
    w, d, fl, top = 10.0, 6.8, .55, 3.30
    door = HOUSES['A']['door_x']; ze, p = 2.78, .45
    m.box((0, 0, (fl + top) / 2), (w, d, top - fl), 'plaster')
    m.collider((0, 0, 2.2), (w, d, 4.4))
    front = [-5.0, -3.375, -1.75, -.125, 1.5, 5.0]

    def dress(side, L, posts):
        if side == 'front':
            for x0, x1 in zip(front[:4], front[1:5]):
                bw = (x1 - x0) / 2
                for k in range(2): glass_door(m, x0 + bw * (k + .5), bw - .02, fl, 1.78)
                m.bar(((x0 + x1) / 2, -.03, 2.6), (x1 - x0 - .16, .04, .36), 'shoji')          # transom
            koshi_window(m, 4.45, 1.75, .6, .9)
            return
        m.bar((0, -.01, (fl + 1.25) / 2), (L - .02, .04, 1.25 - fl), 'board')                  # wainscot
        for k in ((0, 2) if side == 'back' else (1, 3)): koshi_window(m, mid(posts, k), 1.8, 1.1 if side == 'back' else .9, .8)
    body_walls(m, w, d, fl, top, 2.35, lambda side, L: front if side == 'front' else bays(L, 4), dress)
    # engawa along the glass doors, the eave posts along its edge, a shoe stone, the shutter box at its end
    ye = engawa(m, -5.0, 1.45, -3.4, .92)
    for x in (-4.95, -1.75, 1.45): post(m, x, ye - .02, .0, 2.62, .14)
    m.box((-1.75, ye - .02, 2.56), (6.9, .16, .2), 'timber')
    step_stone(m, -2.6, ye - .27, .25, .9, .45)
    m.box((-4.72, -3.62, 1.4), (.5, .38, 1.7), 'board')
    # genkan: an open porch with plaster side walls, a stone floor, lattice sliding doors and its own gable
    py = -5.0
    m.box((door, -4.2, .07), (2.3, 1.7, .14), 'stone')
    for x in (door - 1.02, door + 1.02): post(m, x, py + .08, .14, 2.44, .15)
    m.box((door, py + .08, 2.36), (2.35, .16, .18), 'timber')
    for s in (-1, 1):
        m.box((door + s * 1.1, -4.2, 1.35), (.12, 1.6, 2.2), 'plaster')
        m.box((door + s * 1.1, -4.2, .6), (.14, 1.62, .9), 'board')
    with m.at((door, -3.4, 0)):
        for k in (-1, 1): lattice_door(m, k * .48, .96, .14, 2.05)
        m.bar((0, -.03, 2.3), (2.0, .04, .3), 'shoji')
    gable_y(m, door, 1.4, -3.3, py, 2.62, .55)
    step_stone(m, door, -5.25, .12, 1.3, .5)
    pots(m, door + 1.45, -5.0)
    m.collider((door, -4.2, 1.3), (2.3, 1.6, 2.6))
    # roof
    irimoya(m, 6.25, -4.75, 4.15, ze, p, 2.4, .45)
    eave_ends(m, (-6.0, -4.75), (door - 1.5, -4.75), ze, (0, -1), p)
    eave_ends(m, (-6.0, 4.15), (6.0, 4.15), ze, (0, 1), p)
