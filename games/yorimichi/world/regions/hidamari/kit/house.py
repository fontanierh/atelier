"""Back-lane family houses, HD_House_00 to 03: two storeys on a 10 x 9 m plot behind a low front boundary, after the
concepts in assets/hidamari/houses/<n>/concept.jpg (tools/hidamari_houses.py).

The house body stands at the back of the plot; the front plot holds the path, plants and a bicycle. Boards below and
plaster (or ribbed metal) above, a tiled gable roof (turned gable-on to the lane on variant 2), a tiled pent roof over
the ground-floor front, aluminium sliding windows with a few lit shoji, an entrance porch with a lattice door, an
air-conditioner unit and a gas meter on a side wall and downpipes at the corners. Variant 0 has a balcony with a futon
and a block wall; 1 a persimmon tree and a hedge; 2 a steel side stair, washing under the eaves, a gravel parking pad
and a board fence; 3 ribbed metal upstairs, a balcony of washing and a block wall with openings.
"""
import math, random
from village import build as v
from hidamari.kit import apartment

ASSETS = {'HD_House_00': 0, 'HD_House_01': 1, 'HD_House_02': 2, 'HD_House_03': 3}
WIDTH, DEPTH = 10., 9.            # the plot (the brief's footprint)
W, D = 8.2, 6.4                   # the house body
Y0 = 1.05                         # the body's centre, at the back of the plot (front wall at Y0 - D/2 = -2.15)
F = 2.75                          # storey height
EAVE = 2*F+.15
FRONT = Y0-D/2
BOUNDARY = -DEPTH/2+.2            # the front boundary line
GATE = (-2.15, -.65)              # the gate gap along x, in front of the porch
TONES = {0: ('hs_cream_plaster', 'hs_board'), 1: ('hs_grey_plaster', 'hs_char_board'),
         2: ('hs_ochre_plaster', 'hs_board'), 3: ('hs_white_plaster', 'hs_metal_blue')}


def palette():
    v.PALETTE.update({
        'hs_cream_plaster': (.50, .43, .31), 'hs_grey_plaster': (.40, .39, .36), 'hs_ochre_plaster': (.50, .35, .17),
        'hs_white_plaster': (.53, .51, .47), 'hs_board': (.13, .08, .045), 'hs_char_board': (.065, .058, .052),
        'hs_metal_blue': (.17, .21, .26), 'hs_trim_wood': (.15, .095, .05), 'hs_alu_metal': (.34, .34, .33),
        'hs_glass': (.045, .055, .065), 'hs_base_concrete': (.27, .26, .24), 'hs_block_concrete': (.30, .29, .265),
        'hs_wall_roof_cap': (.085, .09, .10), 'hs_path_stone': (.24, .22, .19), 'hs_gravel': (.22, .20, .17),
        'hs_shrub_moss': (.05, .085, .03), 'hs_fence_board': (.17, .115, .07), 'hs_steel_metal': (.10, .10, .10),
        'hs_ac_metal': (.45, .45, .43), 'hs_futon_cloth': (.55, .50, .42), 'hs_cloth_a': (.50, .52, .55),
        'hs_cloth_b': (.15, .22, .40), 'hs_cloth_c': (.45, .14, .10), 'hs_fruit': (.75, .30, .04),
        'hs_leaf': (.24, .13, .035), 'hs_leaf_b': (.15, .12, .035), 'hs_bark': (.07, .045, .03), 'hs_door_wood': (.20, .13, .07)})


def build(name, variant, lettering):
    palette(); apartment.palette(0)
    r = random.Random(4100+variant)
    m = v.Mesh(name)
    upper, lower = TONES[variant]
    # body: a concrete footing, boards below, plaster or metal above, a trim band between
    m.box((0, Y0, -.05), (W+.12, D+.12, .7), 'hs_base_concrete')
    m.box((0, Y0, .3+F/2), (W, D, F), lower)
    m.box((0, Y0, .3+F+(EAVE-F-.3)/2), (W, D, EAVE-F-.3), upper)
    m.box((0, Y0, F+.32), (W+.1, D+.1, .16), 'hs_trim_wood')
    for (x, y), yaw, w in (((0, FRONT), 0, W), ((W/2, Y0), 90, D), ((-W/2, Y0), -90, D), ((0, Y0+D/2), 180, W)):
        with m.at((x, y, 0), yaw):boards(m, w, 0, .3, F+.24)
    if variant == 2:
        with m.at((0, FRONT, 0)):boards(m, W, 0, F+.4, EAVE-.1)
    m.collider((0, Y0, EAVE/2), (W, D, EAVE+.4))
    if variant != 3:
        for x in (-W/2, W/2):
            for y in (FRONT, Y0+D/2):m.box((x, y, EAVE/2), (.16, .16, EAVE-.1), 'hs_trim_wood')
    else:
        for k in range(1, 28):                       # the ribbed metal upstairs
            x = -W/2+k*W/28
            for y in (FRONT-.03, Y0+D/2+.03):m.box((x, y, F+.3+(EAVE-F-.3)/2), (.05, .05, EAVE-F-.4), 'hs_metal_blue')
    roof(m, variant)
    pent(m, -W/2-.2, W/2+.2, FRONT, F+.15, .95)
    # front: the porch and door at x = -1.4, windows beside and above
    porch(m, -1.4)
    window(m, 1.9, FRONT, 1.55, 2.0, 1.25, lit=variant % 2 == 0)
    if variant in (0, 3):
        balcony(m, variant)
    else:
        window(m, -1.6, FRONT, F+1.6, 1.6, 1.1, lit=True)
    window(m, 2.0, FRONT, F+1.6, 1.5, 1.1, lit=variant == 1)
    # sides and back: windows, the services on the east side, downpipes
    for side in (-1, 1):
        with m.at((side*W/2, Y0, 0), 90*side):
            for x, z, lit in ((-1.4, 1.5, False), (1.5, 1.5, side > 0), (-1.2, F+1.6, side < 0), (1.6, F+1.6, False)):
                if variant == 2 and side < 0 and (z < F or x > 0): continue   # behind the stair, and its side door
                window(m, x, 0, z, 1.1, .95, lit=lit)
    with m.at((W/2, Y0, 0), 90):
        ac_unit(m, .6, 0, .2); gas_meter(m, -2.2, 0, 1.0)
    with m.at((0, Y0+D/2, 0), 180):
        for x, z in ((-2.3, 1.5), (1.0, 1.5), (-1.8, F+1.6), (2.0, F+1.6)):window(m, x, 0, z, 1.3, 1.0, lit=False)
    for x in (-W/2+.12, W/2-.12):
        m.box((x, FRONT-.12, EAVE/2), (.09, .09, EAVE), 'hs_alu_metal')
    # the front plot: path, boundary, plants, a bicycle
    for k in range(4):
        y = BOUNDARY+.4+k*(FRONT-BOUNDARY-.5)/3.5
        m.box((-1.4+r.uniform(-.1, .1), y, -.02), (.9, .6, .08), 'hs_path_stone')
    boundary(m, variant, r)
    for k, (x, y) in enumerate(((-2.6, FRONT-.5), (-.3, FRONT-.4), (3.3, FRONT-.6), (-4.3, BOUNDARY+.7))):
        if variant == 2 and x > 0: continue          # the parking pad
        v.pot(m, x, y, 0, r.uniform(.9, 1.3), 'clay', plant=True, form=('jar', 'bowl')[k % 2])
    if variant in (0, 2):
        apartment.bicycle(m, -3.4, FRONT-1.0, 0, 90, 'ap_bike_g' if variant == 0 else 'ap_bike_o', seed=variant)
    if variant == 1:
        persimmon(m, 3.2, -3.4, r)
    if variant == 2:
        side_stair(m)
        washing(m, -W/2+.6, W/2-.6, Y0+D/2+.45, EAVE-.1, r)
        m.box((3.0, -2.9, -.03), (3.4, 2.6, .08), 'hs_gravel')
    return m


def window(m, x, y, z, w, h, lit=False):
    """An aluminium sliding window at (x, y) on a wall facing -y, centre height z."""
    m.box((x, y-.04, z), (w+.12, .08, h+.12), 'hs_alu_metal')
    m.box((x, y-.085, z), (w, .02, h), 'paper' if lit else 'hs_glass')
    m.box((x, y-.11, z), (.05, .04, h), 'hs_alu_metal')
    m.box((x, y-.14, z-h/2-.06), (w+.2, .2, .06), 'hs_alu_metal')


def porch(m, x):
    """A recessed entrance with a sliding lattice door, a lamp and a small roof."""
    m.box((x, FRONT-.06, .3+1.1), (1.7, .1, 2.2), 'hs_trim_wood')
    m.box((x, FRONT-.12, .3+1.05), (1.4, .04, 2.0), 'hs_door_wood')
    for k in range(9):m.box((x-.6+k*.15, FRONT-.15, .3+1.05), (.035, .03, 1.95), 'hs_trim_wood')
    for z in (.9, 1.6, 2.2):m.box((x, FRONT-.15, z), (1.4, .03, .035), 'hs_trim_wood')
    m.box((x, FRONT-.5, .12), (1.8, 1.0, .25), 'hs_path_stone')
    m.box((x+1.05, FRONT-.1, 2.35), (.16, .12, .22), 'paper')


def pent(m, x0, x1, y, z, depth):
    """A tiled pent roof along the front wall at y, from height z falling .35 m over its depth."""
    z1 = z-.35
    m.poly([(x0, y-depth, z1), (x1, y-depth, z1), (x1, y, z), (x0, y, z)], 'roof')
    m.poly([(x0, y, z-.08), (x1, y, z-.08), (x1, y-depth, z1-.08), (x0, y-depth, z1-.08)], 'hs_trim_wood')
    for k in range(int((x1-x0)/.3)):
        xx = x0+.15+k*.3
        m.beam((xx, y, z+.03), (xx, y-depth, z1+.03), .07, .06, 'roof')
    m.beam((x0, y-depth, z1-.02), (x1, y-depth, z1-.02), .1, .14, 'hs_trim_wood')


def roof(m, variant):
    upper = TONES[variant][0]
    rise = 1.9 if variant != 3 else 1.5
    if variant == 1:
        hipped(m, W+1.5, D+1.5, EAVE, 2.1)
    elif variant == 2:
        with m.at((0, Y0, 0), 90):gable(m, D, W, EAVE, rise, upper)
    else:
        with m.at((0, Y0, 0)):gable(m, W, D, EAVE, rise, upper)


def gable(m, w, d, eave, rise, wall):
    """A tiled gable roof, ridge along x, in the hipped roof's light tile courses: slopes sagging a little to the eaves,
    verge boards, a ridge roll and closed gable triangles in the upper wall's finish. Overhangs .75 m."""
    W_, D_ = w+1.5, d+1.5
    def z(t): return eave+.05+rise*(t**1.15)          # t: 0 at the eave line, 1 at the ridge
    rows = 7
    for sy in (-1, 1):
        for row in range(rows):
            t0, t1 = row/rows, (row+1)/rows
            y0, y1 = sy*D_/2*(1-t0), sy*D_/2*(1-t1)
            key = v.color_variant('roof', .045)
            q = [(-W_/2, y0, z(t0)), (W_/2, y0, z(t0)), (W_/2, y1, z(t1)), (-W_/2, y1, z(t1))]
            m.poly(q if sy < 0 else q[::-1], key)
            m.beam((-W_/2, y0, z(t0)+.04), (W_/2, y0, z(t0)+.04), .05, .05, key)
        m.poly([(-W_/2, sy*D_/2, eave), (W_/2, sy*D_/2, eave), (W_/2, 0, eave), (-W_/2, 0, eave)][::(1 if sy > 0 else -1)], 'wood_dark')
        for sx in (-1, 1):                               # verge boards
            for row in range(rows):
                t0, t1 = row/rows, (row+1)/rows
                m.beam((sx*W_/2, sy*D_/2*(1-t0), z(t0)), (sx*W_/2, sy*D_/2*(1-t1), z(t1)), .16, .2, 'roof_edge')
        m.beam((-W_/2, sy*D_/2, eave+.02), (W_/2, sy*D_/2, eave+.02), .12, .16, 'hs_trim_wood')
    for sx in (-1, 1):                                   # the gable triangles, just inside the wall line
        x = sx*(w/2-.02)
        tri = [(x, -d/2, eave-.02), (x, 0, z(1)-.1), (x, d/2, eave-.02)]
        m.poly(tri if sx > 0 else tri[::-1], wall)
        m.box((sx*(w/2+.06), 0, eave+rise/2), (.14, .16, rise), 'hs_trim_wood')
    m.beam((-W_/2-.1, 0, z(1)+.08), (W_/2+.1, 0, z(1)+.08), .28, .24, 'roof_edge')
    for sx in (-1, 1):m.box((sx*(W_/2+.05), 0, z(1)+.2), (.25, .3, .36), 'roof_edge')


def hipped(m, w, d, eave, rise):
    """A tiled hipped roof over the body: four slopes in tile courses, hip and ridge rolls, a closed soffit."""
    rh = (w-d)/2                                         # the ridge's half-length along x
    with m.at((0, Y0, 0)):
        m.poly([(-w/2, d/2, eave), (w/2, d/2, eave), (w/2, -d/2, eave), (-w/2, -d/2, eave)], 'wood_dark')
        rows = 7
        for row in range(rows):
            t0, t1 = row/rows, (row+1)/rows
            z0, z1 = eave+rise*t0+.05, eave+rise*t1+.05
            key = v.color_variant('roof', .045)
            def at(t, sx, sy): return (sx*(w/2-(w/2-rh)*t), sy*(d/2)*(1-t))
            for sy in (-1, 1):       # the long slopes
                a, b = at(t0, -1, sy), at(t0, 1, sy); c, e = at(t1, 1, sy), at(t1, -1, sy)
                q = [(a[0], a[1], z0), (b[0], b[1], z0), (c[0], c[1], z1), (e[0], e[1], z1)]
                m.poly(q if sy < 0 else q[::-1], key)
                m.beam((a[0], a[1], z0+.04), (b[0], b[1], z0+.04), .05, .05, key)
            for sx in (-1, 1):       # the hipped ends
                a, b = at(t0, sx, -1), at(t0, sx, 1); c, e = at(t1, sx, 1), at(t1, sx, -1)
                q = [(a[0], a[1], z0), (b[0], b[1], z0), (c[0], c[1], z1), (e[0], e[1], z1)]
                m.poly(q if sx > 0 else q[::-1], key)
                m.beam((a[0], a[1], z0+.04), (b[0], b[1], z0+.04), .05, .05, key)
        top = eave+rise+.05
        for sx in (-1, 1):
            for sy in (-1, 1):m.beam((sx*w/2, sy*d/2, eave+.05), (sx*rh, 0, top), .2, .16, 'roof_edge')
        m.beam((-rh, 0, top), (rh, 0, top), .26, .22, 'roof_edge')
        m.box((0, 0, eave-.06), (w, d, .12), 'hs_trim_wood')


def boards(m, w, y, z0, z1):
    """Vertical battens over the board cladding of a wall at y facing -y."""
    for k in range(1, int(w/.5)):
        m.box((-w/2+k*w/int(w/.5), y-.025, (z0+z1)/2), (.06, .05, z1-z0), 'hs_trim_wood')


def balcony(m, variant):
    """A narrow upper-floor balcony across the front with a sliding door, a rail and a laundry pole."""
    z = F+.3
    m.box((0, FRONT-.5, z), (5.2, 1.0, .14), 'hs_trim_wood' if variant == 0 else 'hs_alu_metal')
    for k in range(11):m.box((-2.5+k*.5, FRONT-.98, z+.5), (.05, .05, .9), 'hs_trim_wood' if variant == 0 else 'hs_alu_metal')
    m.box((0, FRONT-.98, z+.95), (5.2, .07, .07), 'hs_trim_wood' if variant == 0 else 'hs_alu_metal')
    window(m, -.9, FRONT, z+1.15, 2.0, 1.9, lit=False)
    m.box((0, FRONT-.8, z+1.9), (4.8, .04, .04), 'hs_alu_metal')
    if variant == 0:
        m.box((-1.2, FRONT-1.02, z+.6), (1.9, .08, 1.1), 'hs_futon_cloth')
    else:
        for k, x in enumerate((-2., -1.3, -.6, .1, .8, 1.5)):
            m.box((x, FRONT-.8, z+1.55), (.55, .03, .65), ('hs_cloth_a', 'hs_cloth_b', 'hs_cloth_c')[k % 3])


def boundary(m, variant, r):
    """The front boundary along y = BOUNDARY, with the gate gap, and short returns along the sides."""
    runs = [(-WIDTH/2+.1, GATE[0]), (GATE[1], WIDTH/2-.1)]
    for x0, x1 in runs:
        if variant in (0, 3):
            m.box(((x0+x1)/2, BOUNDARY, .45), (x1-x0, .15, 1.3), 'hs_block_concrete')
            m.box(((x0+x1)/2, BOUNDARY, 1.12), (x1-x0+.06, .25, .08), 'hs_wall_roof_cap')
            if variant == 3:
                for k in range(int((x1-x0)/1.6)):
                    m.box((x0+.8+k*1.6, BOUNDARY-.08, .75), (.4, .02, .2), 'hs_steel_metal')
        elif variant == 1:
            m.box(((x0+x1)/2, BOUNDARY, .1), (x1-x0, .4, .5), 'hs_block_concrete')
            m.box(((x0+x1)/2, BOUNDARY, .75), (x1-x0, .6, .8), 'hs_shrub_moss')
        else:
            m.box(((x0+x1)/2, BOUNDARY, .55), (x1-x0, .06, 1.4), 'hs_fence_board')
            for k in range(int((x1-x0)/1.8)+1):m.box((x0+k*1.8, BOUNDARY, .5), (.1, .1, 1.6), 'hs_trim_wood')
        m.collider(((x0+x1)/2, BOUNDARY, .5), (x1-x0, .4, 1.6))
    for x in (GATE[0]-.15, GATE[1]+.15):m.box((x, BOUNDARY, .55), (.3, .3, 1.5), 'hs_block_concrete')
    length = FRONT-BOUNDARY-.3                     # short returns up the plot's sides to the house
    for x in (-WIDTH/2+.1, WIDTH/2-.1):
        key = {1: 'hs_shrub_moss', 2: 'hs_fence_board'}.get(variant, 'hs_block_concrete')
        m.box((x, BOUNDARY+length/2, .45), (.6 if variant == 1 else .15, length, 1.3), key)
        m.collider((x, BOUNDARY+length/2, .5), (.6, length, 1.6))


def ac_unit(m, x, y, z):
    m.box((x, y-.2, z+.3), (.8, .3, .6), 'hs_ac_metal'); m.box((x, y-.36, z+.3), (.5, .02, .45), 'hs_steel_metal')


def gas_meter(m, x, y, z):
    m.box((x, y-.1, z), (.35, .18, .45), 'hs_ac_metal'); m.beam((x, y-.1, z-.22), (x, y-.1, .2), .04, .04, 'hs_steel_metal')


def persimmon(m, x, y, r):
    """A small persimmon tree: a forked trunk, a loose crown of leaf clumps in two tones, orange fruit."""
    m.lathe((x, y, -.2), [(0, .13), (1.6, .09), (2.1, .06)], 'hs_bark', n=7)
    for a in (.6, 2.6, 4.4):
        m.beam((x, y, 1.6), (x+math.cos(a)*.7, y+math.sin(a)*.45, 2.6), .07, .07, 'hs_bark')
    m.collider((x, y, 1.), (.4, .4, 2.4))
    for k in range(9):
        a = k*2.4+r.uniform(-.3, .3); d = r.uniform(.25, .75)
        cx = x+math.cos(a)*d; cy = y+math.sin(a)*d*.55-.15; cz = 2.3+r.uniform(0, 1.0); s = r.uniform(.35, .55)
        m.lathe((cx, cy, cz-s), [(0, 0), (.3*s, .8*s), (s, s), (1.6*s, .65*s), (1.9*s, 0)], ('hs_leaf', 'hs_leaf_b')[k % 2], n=7)
        for j in range(2):
            b = r.uniform(0, math.tau)
            m.box((cx+math.cos(b)*s*.95, cy+math.sin(b)*s*.95, cz+r.uniform(-.2, .2)), (.14, .14, .14), 'hs_fruit')


def side_stair(m):
    """A steel stair up the west wall to a side door on the upper floor."""
    x = -W/2-.5; y0, y1 = Y0+D/2-.3, Y0-D/2+1.4
    steps = 14
    for k in range(steps):
        t = k/steps; m.box((x, y0+(y1-y0)*t, .3+F*t), (.9, .26, .05), 'hs_steel_metal')
    for xx in (x-.45, x+.45):
        m.beam((xx, y0, .3), (xx, y1, .3+F), .05, .18, 'hs_steel_metal')
        m.beam((xx, y0, 1.2), (xx, y1, F+1.2), .04, .04, 'hs_steel_metal')
    m.box((x, y1-.6, F+.3), (1.0, 1.2, .08), 'hs_steel_metal')
    m.collider((x, (y0+y1)/2-.3, F/2+.3), (1.0, abs(y1-y0)+1.2, F+.6))
    with m.at((-W/2, Y0, 0), -90):          # local x runs towards -y here: the door opens onto the landing
        m.box((Y0-(y1-.6), -.06, F+1.3), (.9, .08, 2.0), 'hs_door_wood')


def washing(m, x0, x1, y, z, r):
    m.box(((x0+x1)/2, y, z), (x1-x0, .03, .03), 'hs_alu_metal')
    for k in range(8):
        x = x0+.4+k*(x1-x0-.8)/7
        m.box((x, y, z-.25), (.45, .03, .45), ('hs_cloth_a', 'hs_cloth_b', 'hs_cloth_c')[r.randrange(3)])
