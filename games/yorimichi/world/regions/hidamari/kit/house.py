"""Back-lane family houses, HD_House_00 to 03: two storeys on a 10 x 9 m plot behind a low front boundary, after the
concepts in assets/hidamari/houses/<n>/concept.jpg (tools/hidamari_houses.py).

The house body stands at the back of the plot; the front plot holds the path, plants and a bicycle. Board cladding
with battens below; above, plaster framed by exposed posts, rails and a head beam (ribbed metal on variant 3). A
kawara roof (kit/kawara.py) of round tile rolls with an onigawara-capped ridge, deep eaves on rafter tails and copper
gutters with downpipes: gable on 0 and 3, hipped on 1, gable-on to the lane on 2. A tiled pent roof runs across the
ground-floor front, broken by a gabled entrance porch on two posts over a lattice door. Windows have wooden frames
and aluminium sashes with shoji glowing or curtains behind, hoods over the upper ones, a louvred shutter or a lattice
grille below. An air-conditioner unit and a gas meter on a side wall. Variant 0 has a balcony with a futon and a
block wall; 1 a hedge (its garden tree is a foliage instance, house_gardens.py); 2 a steel side stair, washing under the eaves, a gravel parking pad and
a board fence; 3 ribbed metal upstairs, a balcony of washing and a block wall with openings.
"""
import math, random
from village import build as v
from hidamari.kit import apartment, kawara

ASSETS = {'HD_House_00': 0, 'HD_House_01': 1, 'HD_House_02': 2, 'HD_House_03': 3}
WIDTH, DEPTH = 10., 9.            # the plot (the brief's footprint)
W, D = 8.2, 6.4                   # the house body
Y0 = 1.05                         # the body's centre, at the back of the plot (front wall at Y0 - D/2 = -2.15)
F = 2.75                          # storey height
EAVE = 2*F+.15                    # the top of the walls
FRONT = Y0-D/2
BOUNDARY = -DEPTH/2+.2            # the front boundary line
GATE = (-2.15, -.65)              # the gate gap along x, in front of the porch
PORCH = -1.4                      # the entrance's centre along x
OVER = .75                        # the main roof's overhang
TONES = {0: ('hs_cream_plaster', 'hs_board'), 1: ('hs_grey_plaster', 'hs_char_board'),
         2: ('hs_ochre_plaster', 'hs_board'), 3: ('hs_white_plaster', 'hs_metal_blue')}


def palette():
    v.PALETTE.update({
        'hs_cream_plaster': (.56, .47, .33), 'hs_grey_plaster': (.50, .45, .37), 'hs_ochre_plaster': (.56, .40, .20),
        'hs_white_plaster': (.60, .55, .46), 'hs_board': (.15, .09, .05), 'hs_char_board': (.075, .062, .052),
        'hs_metal_blue': (.17, .21, .26), 'hs_trim_wood': (.17, .10, .05), 'hs_alu_metal': (.34, .34, .33),
        'hs_glass': (.045, .055, .065), 'hs_base_concrete': (.27, .26, .24), 'hs_block_concrete': (.37, .34, .285),
        'hs_block_joint': (.20, .19, .17), 'hs_wall_roof_cap': (.25, .24, .22), 'hs_path_stone': (.27, .25, .21),
        'hs_gravel': (.24, .22, .18), 'hs_shrub_moss': (.05, .085, .03), 'hs_fence_board': (.19, .125, .07),
        'hs_steel_metal': (.10, .10, .10), 'hs_ac_metal': (.52, .51, .48), 'hs_futon_cloth': (.62, .58, .50),
        'hs_cloth_a': (.55, .56, .58), 'hs_cloth_b': (.15, .24, .45), 'hs_cloth_c': (.50, .30, .26),
        'hs_curtain_cloth': (.55, .50, .42), 'hs_curtain_b_cloth': (.42, .44, .40),
        'hs_door_wood': (.22, .14, .07), 'hs_soil': (.11, .075, .045), 'hs_louvre_wood': (.20, .12, .06)})
    kawara.palette()


def build(name, variant, lettering):
    palette(); apartment.palette(0)
    r = random.Random(4100+variant)
    m = v.Mesh(name)
    upper, lower = TONES[variant]
    # body: a concrete footing, boards below, plaster or metal above, a projecting band between the storeys
    m.box((0, Y0, -.05), (W+.12, D+.12, .7), 'hs_base_concrete')
    m.box((0, Y0, .3+F/2), (W, D, F), lower)
    m.box((0, Y0, .3+F+(EAVE-F-.3)/2), (W, D, EAVE-F-.3), upper)
    m.box((0, Y0, F+.36), (W+.18, D+.18, .2), 'hs_trim_wood')
    m.box((0, Y0, EAVE-.12), (W+.1, D+.1, .24), 'hs_trim_wood')          # the head beam under the eaves
    walls = (((0, FRONT), 0, W), ((W/2, Y0), 90, D), ((-W/2, Y0), -90, D), ((0, Y0+D/2), 180, W))
    for (x, y), yaw, w in walls:
        with m.at((x, y, 0), yaw):boards(m, w, 0, .3, F+.26)
    m.collider((0, Y0, EAVE/2), (W, D, EAVE+.4))
    if variant == 3:
        for k in range(1, 28):                       # the ribbed metal upstairs
            x = -W/2+k*W/28
            for y in (FRONT-.03, Y0+D/2+.03):m.box((x, y, F+.3+(EAVE-F-.3)/2), (.05, .05, EAVE-F-.4), 'hs_metal_blue')
    elif variant == 2:
        with m.at((0, FRONT, 0)):boards(m, W, 0, F+.46, EAVE-.24)
    for x in (-W/2, W/2):                            # corner posts, full height
        for y in (FRONT, Y0+D/2):m.box((x, y, EAVE/2+.15), (.2, .2, EAVE-.2), 'hs_trim_wood')
    roof(m, variant, upper)
    # the pent roof across the front, broken by the entrance porch
    for x0, x1 in ((-W/2-.25, PORCH-1.05), (PORCH+1.05, W/2+.25)):
        kawara.pent(m, x0, x1, FRONT, F+.5, .95)
    porch(m, PORCH)
    # front windows
    window(m, 1.9, FRONT, 1.55, 2.0, 1.25, 'shoji' if variant % 2 == 0 else 'curtain')
    if variant in (1, 3):
        grille(m, 1.9, FRONT, 1.55, 2.0, 1.25)
    else:
        shutter(m, .3, FRONT, 1.55, 1.25)
    if variant in (0, 3):
        balcony(m, variant)
        window(m, -2.2, FRONT, F+1.65, 1.4, 1.1, 'shoji', hood=True)
        posts = [-3.35, -1.05, 3.3]
    else:
        window(m, -1.6, FRONT, F+1.65, 1.6, 1.1, 'shoji', hood=True)
        window(m, 2.0, FRONT, F+1.65, 1.5, 1.1, 'curtain' if variant != 1 else 'shoji', hood=True)
        posts = [-3.0, .25, 3.15]
    if variant != 3:
        with m.at((0, FRONT, 0)):framing(m, W, posts, posts_skip=variant == 2)
    # sides and back: windows, the services on the east side
    for side in (-1, 1):
        with m.at((side*W/2, Y0, 0), 90*side):
            for x, z, kind in ((-1.4, 1.5, 'glass'), (1.5, 1.5, 'shoji' if side > 0 else 'curtain'),
                               (-1.2, F+1.65, 'curtain'), (1.6, F+1.65, 'glass')):
                if variant == 2 and side < 0 and (z < F or x > 0): continue   # behind the stair, and its side door
                window(m, x, 0, z, 1.1, .95, kind, hood=z > F)
            if variant != 3:framing(m, D, [.2])
    with m.at((W/2, Y0, 0), 90):
        ac_unit(m, .6, 0, .2); gas_meter(m, -2.2, 0, 1.0)
    with m.at((0, Y0+D/2, 0), 180):
        for x, z in ((-2.3, 1.5), (1.0, 1.5), (-1.8, F+1.65), (2.0, F+1.65)):
            window(m, x, 0, z, 1.3, 1.0, 'curtain' if x > 0 else 'glass', hood=z > F)
        if variant != 3:framing(m, W, [.2])
    # the front plot: stepping stones, boundary, plants, a bicycle
    for k in range(4):
        y = BOUNDARY+.4+k*(FRONT-1.5-BOUNDARY-.2)/3
        m.box((PORCH+r.uniform(-.12, .12), y, -.02), (.85+r.uniform(-.1, .1), .55, .1), 'hs_path_stone', .04)
    boundary(m, variant, r)
    for k, (x, y) in enumerate(((-3.0, FRONT-.5), (-.1, FRONT-.45), (3.3, FRONT-.6), (-4.3, BOUNDARY+.7), (.4, BOUNDARY+.55))):
        if variant == 2 and x > 0: continue          # the parking pad
        v.pot(m, x, y, 0, r.uniform(.9, 1.3), 'clay', plant=True, form=('jar', 'bowl')[k % 2])
    if variant in (0, 2):
        apartment.bicycle(m, -3.6, FRONT-1.15, 0, 90, 'ap_bike_g' if variant == 0 else 'ap_bike_o', seed=variant)
    if variant == 2:
        side_stair(m)
        washing(m, -W/2+.6, W/2-.6, Y0+D/2+.45, EAVE-.3, r)
        m.box((3.0, -2.9, -.03), (3.4, 2.6, .08), 'hs_gravel')
    return m


def roof(m, variant, wall):
    """The main roof with its walls' gable triangles and their framing; downpipes from the front gutters."""
    if variant == 1:
        rise = 2.1; ez = EAVE-rise*OVER/(D/2+OVER)+.03
        with m.at((0, Y0, 0)):kawara.hipped(m, W, D, ez, rise, OVER)
        pipes = [((sx*(W/2+OVER-.35), FRONT-OVER-.1, ez-.16), (sx*(W/2-.3), FRONT-.08)) for sx in (-1, 1)]
    else:
        rise = 1.9 if variant != 3 else 1.55
        long_, short = (D, W) if variant == 2 else (W, D)
        ez = EAVE-rise*OVER/(short/2+OVER)+.03
        with m.at((0, Y0, 0), 90 if variant == 2 else 0):
            kawara.gable(m, long_, short, ez, rise, OVER)
            for sx in (-1, 1):                       # gable triangles, a tie beam, king post and a louvred vent
                x = sx*(long_/2)
                tri = [(x, -short/2, EAVE-.02), (x, 0, ez+rise-.06), (x, short/2, EAVE-.02)]
                kawara.face(m, tri, wall, (sx, 0, 0))
                m.box((x+sx*.05, 0, EAVE+.05), (.12, short+.1, .2), 'hs_trim_wood')
                m.box((x+sx*.05, 0, (EAVE+ez+rise)/2), (.12, .16, ez+rise-EAVE), 'hs_trim_wood')
                for s in (-1, 1):
                    m.beam((x+sx*.05, s*short*.3, EAVE+.1), (x+sx*.05, s*.1, ez+rise*.75), .1, .12, 'hs_trim_wood')
                vz = EAVE+.3+(ez+rise-EAVE)*.25
                m.box((x+sx*.07, -.75, vz), (.08, .55, .5), 'hs_trim_wood')
                for k in range(5):m.box((x+sx*.12, -.75, vz-.2+k*.1), (.04, .48, .035), 'hs_louvre_wood')
        if variant == 2:   # eaves along the sides: pipes down the side walls near the front
            pipes = [((sx*(W/2+OVER+.1), FRONT+.35, ez-.16), (sx*(W/2+.08), FRONT+.35)) for sx in (-1, 1)]
        else:
            pipes = [((sx*(W/2+OVER-.35), FRONT-OVER-.1, ez-.16), (sx*(W/2-.3), FRONT-.08)) for sx in (-1, 1)]
    for top, wall_pt in pipes:kawara.downpipe(m, top, wall_pt)


def framing(m, w, posts, posts_skip=False):
    """Exposed timber on an upper-storey wall at y = 0 facing -y, w wide: posts at the given x, a sill rail under the
    windows and a rail over them (the corner posts and head beam are the body's)."""
    for z in (F+.95, F+2.32):
        m.box((0, -.03, z), (w, .06, .1), 'hs_trim_wood')
    if posts_skip: return
    for x in posts:
        m.box((x, -.035, F+.46+(EAVE-F-.7)/2), (.14, .07, EAVE-F-.7), 'hs_trim_wood')


def window(m, x, y, z, w, h, kind='glass', hood=False):
    """A window on a wall at y facing -y, centre height z: a wooden frame, an aluminium two-pane sash with a mullion,
    shoji glowing behind it, a half-drawn curtain or dark glass; a sill, and a small metal hood when asked."""
    m.box((x, y-.04, z), (w+.24, .08, h+.24), 'hs_trim_wood')
    m.box((x, y-.075, z), (w+.06, .04, h+.06), 'hs_alu_metal')
    if kind == 'shoji':
        m.box((x, y-.09, z), (w, .02, h), 'paper')
        for k in range(1, 4):m.box((x-w/2+k*w/4, y-.1, z), (.025, .015, h), 'hs_trim_wood')
        for k in range(1, 3):m.box((x, y-.1, z-h/2+k*h/3), (w, .015, .025), 'hs_trim_wood')
    else:
        m.box((x, y-.09, z), (w, .02, h), 'hs_glass')
        if kind == 'curtain':
            s = 1 if (x*7) % 2 > 1 else -1
            m.box((x+s*w*.27, y-.1, z+.02), (w*.42, .015, h*.94), 'hs_curtain_cloth' if s > 0 else 'hs_curtain_b_cloth')
    m.box((x, y-.13, z), (.06, .04, h), 'hs_alu_metal')
    m.box((x, y-.13, z), (w, .03, .03), 'hs_alu_metal')
    m.box((x, y-.13, z-h/2-.1), (w+.32, .26, .07), 'hs_trim_wood')
    if hood:
        top = z+h/2+.3
        m.box((x, y-.23, top), (w+.5, .46, .08), 'hs_trim_wood')
        m.poly([(x-w/2-.27, y-.48, top+.05), (x+w/2+.27, y-.48, top+.05), (x+w/2+.27, y, top+.2), (x-w/2-.27, y, top+.2)], 'kw_roof_tile')
        for s in (-1, 1):m.beam((x+s*(w/2+.15), y, top-.3), (x+s*(w/2+.15), y-.4, top-.03), .06, .06, 'hs_trim_wood')


def shutter(m, x, y, z, h):
    """A louvred storm-shutter box beside a window on a wall at y facing -y."""
    m.box((x, y-.09, z), (.9, .16, h+.2), 'hs_louvre_wood')
    for k in range(int(h/.11)):m.box((x, y-.18, z-h/2+.06+k*.11), (.8, .03, .045), 'hs_trim_wood')


def grille(m, x, y, z, w, h):
    """A koshi lattice in front of a window on a wall at y facing -y."""
    for k in range(int(w/.09)+1):m.box((x-w/2+k*w/int(w/.09), y-.2, z), (.035, .05, h+.1), 'hs_trim_wood')
    for zz in (z-h/2-.04, z+h/2+.04):m.box((x, y-.2, zz), (w+.1, .07, .07), 'hs_trim_wood')


def porch(m, x):
    """The entrance: a lattice sliding door in a frame, a gabled kawara porch roof on two posts, a lamp, a nameplate
    and a post box, a stone step."""
    m.box((x, FRONT-.06, .3+1.15), (1.85, .1, 2.3), 'hs_trim_wood')
    m.box((x, FRONT-.12, .3+1.1), (1.55, .04, 2.1), 'hs_door_wood')
    for k in range(11):m.box((x-.7+k*.14, FRONT-.15, .3+1.1), (.035, .03, 2.05), 'hs_trim_wood')
    for z in (.95, 1.65, 2.3):m.box((x, FRONT-.15, z), (1.55, .03, .035), 'hs_trim_wood')
    m.box((x, FRONT-.12, .3+2.32), (.04, .03, .05), 'hs_trim_wood')
    m.box((x, FRONT-.7, .14), (1.9, 1.2, .28), 'hs_path_stone', .03)
    depth = 1.45
    with m.at((x, FRONT-depth/2+.15, 0), -90):     # ridge along -y, out from the wall
        ez, top = kawara.gable(m, depth, 1.9, F+.15, .62, .3, oni=False, gutters=False, courses=1)
        tri = [(depth/2+.02, -.95, ez+.06), (depth/2+.02, 0, top-.04), (depth/2+.02, .95, ez+.06)]
        kawara.face(m, tri, 'hs_trim_wood', (1, 0, 0))
        m.box((depth/2+.06, 0, ez+.04), (.12, 2.2, .18), 'hs_trim_wood')
    for s in (-1, 1):
        m.box((x+s*.92, FRONT-depth+.1, (F+.15)/2), (.14, .14, F+.15), 'hs_trim_wood')
        m.box((x+s*.92, FRONT-depth+.1, .08), (.26, .26, .16), 'hs_base_concrete')
    m.box((x+1.12, FRONT-.12, 2.35), (.18, .14, .26), 'paper')
    m.box((x+1.12, FRONT-.12, 2.52), (.24, .18, .05), 'hs_steel_metal')
    m.box((x-1.15, FRONT-.08, 1.6), (.1, .03, .32), 'hs_trim_wood')
    m.box((x+1.25, FRONT-.14, 1.15), (.32, .14, .42), 'hs_steel_metal')


def balcony(m, variant, cx=1.5, w=4.8):
    """A narrow upper-floor balcony across the east of the front, clear of the porch roof: timber floor on brackets,
    a spindle rail, a sliding door, a laundry pole; a futon over the rail (0) or a line of washing (3)."""
    z = F+.55
    wood = variant == 0
    rail = 'hs_trim_wood' if wood else 'hs_alu_metal'
    x0, x1 = cx-w/2, cx+w/2
    m.box((cx, FRONT-.55, z), (w, 1.1, .12), rail)
    for x in (x0+.2, cx, x1-.2):m.beam((x, FRONT-.05, z-.6), (x, FRONT-1.0, z-.06), .1, .1, rail)
    n = int(w/(.2 if wood else .4))
    for k in range(n+1):
        m.box((x0+.05+k*(w-.1)/n, FRONT-1.06, z+.48), (.045 if wood else .03, .045 if wood else .03, .84), rail)
    m.box((cx, FRONT-1.06, z+.93), (w, .1 if wood else .05, .08), rail)
    m.box((cx, FRONT-1.06, z+.1), (w, .07, .06), rail)
    for x in (x0, x1):m.box((x, FRONT-.55, z+.48), (.08, 1.1, .08), rail)
    window(m, cx-.5, FRONT, z+1.1, 2.0, 1.9, 'curtain')
    for x in (x0+.15, x1-.15):m.box((x, FRONT-.75, z+1.45), (.04, .04, 1.0), 'hs_alu_metal')
    m.box((cx, FRONT-.75, z+1.9), (w-.2, .04, .04), 'hs_alu_metal')
    if wood:
        fx = cx-.6
        m.box((fx, FRONT-1.1, z+.98), (1.9, .16, .12), 'hs_futon_cloth', .04)
        m.box((fx, FRONT-1.2, z+.6), (1.9, .07, .76), 'hs_futon_cloth')
        m.box((fx, FRONT-.98, z+.6), (1.9, .07, .76), 'hs_futon_cloth')
    else:
        for k in range(7):
            x = x0+.5+k*(w-1.)/6
            m.box((x, FRONT-.75, z+1.55), (.5+.1*(k % 2), .03, .6+.1*(k % 3)), ('hs_cloth_a', 'hs_cloth_b', 'hs_cloth_c')[k % 3])


def block_wall(m, x0, x1, y, h, openings=False):
    """A concrete block wall along y from x0 to x1, h high: blocks in a running bond with a cap course."""
    m.box(((x0+x1)/2, y, h/2), (x1-x0, .15, h), 'hs_block_concrete')
    rows = int(h/.2)
    for j in range(1, rows):
        m.box(((x0+x1)/2, y, j*.2), (x1-x0, .17, .012), 'hs_block_joint')
    for j in range(rows):
        off = .2 if j % 2 else 0.
        k = 1
        while x0+off+k*.4 < x1-.05:
            xx = x0+off+k*.4
            m.box((xx, y, j*.2+.1), (.012, .17, .19), 'hs_block_joint'); k += 1
    m.box(((x0+x1)/2, y, h+.04), (x1-x0+.04, .24, .08), 'hs_wall_roof_cap')
    if openings:
        for k in range(int((x1-x0)/1.6)):
            m.box((x0+.8+k*1.6, y, h-.4), (.42, .17, .2), 'hs_steel_metal')


def boundary(m, variant, r):
    """The front boundary along y = BOUNDARY, with the gate gap, pillars, and short returns along the sides."""
    runs = [(-WIDTH/2+.1, GATE[0]-.3), (GATE[1]+.3, WIDTH/2-.1)]
    for x0, x1 in runs:
        if variant in (0, 3):
            block_wall(m, x0, x1, BOUNDARY, 1.2, openings=variant == 3)
        elif variant == 1:
            m.box(((x0+x1)/2, BOUNDARY, .2), (x1-x0, .4, .4), 'hs_block_concrete')
            m.box(((x0+x1)/2, BOUNDARY, .42), (x1-x0+.04, .46, .06), 'hs_wall_roof_cap')
            m.box(((x0+x1)/2, BOUNDARY+.45, .2), (x1-x0, .5, .3), 'hs_soil')
        else:
            m.box(((x0+x1)/2, BOUNDARY, .2), (x1-x0, .2, .4), 'hs_block_concrete')
            for k in range(int((x1-x0)/.17)):
                m.box((x0+.09+k*.17, BOUNDARY, .95), (.15, .05, 1.1+.04*(k % 2)), 'hs_fence_board')
            m.box(((x0+x1)/2, BOUNDARY+.06, 1.3), (x1-x0, .05, .08), 'hs_trim_wood')
            m.box(((x0+x1)/2, BOUNDARY+.06, .65), (x1-x0, .05, .08), 'hs_trim_wood')
        m.collider(((x0+x1)/2, BOUNDARY, .5), (x1-x0, .4, 1.6))
    for x in (GATE[0]-.18, GATE[1]+.18, -WIDTH/2+.15, WIDTH/2-.15):   # pillars with caps
        m.box((x, BOUNDARY, .7), (.36, .36, 1.4), 'hs_block_concrete')
        m.box((x, BOUNDARY, 1.45), (.44, .44, .1), 'hs_wall_roof_cap', .02)
    if variant == 0:                               # a half-open timber gate leaf
        with m.at((GATE[0]+.05, BOUNDARY-.05, 0), -35):
            m.box((.38, 0, .65), (.76, .05, 1.1), 'hs_fence_board')
            for k in range(5):m.box((.08+k*.15, -.03, .65), (.04, .03, 1.1), 'hs_trim_wood')
    length = FRONT-BOUNDARY-.3                     # short returns up the plot's sides to the house
    for x in (-WIDTH/2+.1, WIDTH/2-.1):
        key = {1: 'hs_block_concrete', 2: 'hs_fence_board'}.get(variant, 'hs_block_concrete')
        m.box((x, BOUNDARY+length/2, .2 if variant == 1 else .6), (.3 if variant == 1 else .15, length, .4 if variant == 1 else 1.2), key)
        m.collider((x, BOUNDARY+length/2, .5), (.6, length, 1.6))


def boards(m, w, y, z0, z1):
    """Vertical battens over the board cladding of a wall at y facing -y."""
    for k in range(1, int(w/.45)):
        m.box((-w/2+k*w/int(w/.45), y-.025, (z0+z1)/2), (.06, .05, z1-z0), 'hs_trim_wood')


def ac_unit(m, x, y, z):
    """An outdoor air-conditioner unit on a bracket: a cabinet with a round fan grille."""
    m.box((x, y-.22, z+.3), (.82, .3, .62), 'hs_ac_metal', .03)
    m.box((x-.08, y-.38, z+.3), (.5, .02, .5), 'hs_steel_metal')
    for k in range(4):m.box((x-.08, y-.395, z+.08+k*.15), (.5, .015, .02), 'hs_ac_metal')
    m.beam((x+.32, y-.1, z+.45), (x+.32, y-.1, 1.6), .04, .04, 'hs_ac_metal')


def gas_meter(m, x, y, z):
    m.box((x, y-.1, z), (.35, .18, .45), 'hs_ac_metal'); m.beam((x, y-.1, z-.22), (x, y-.1, .2), .04, .04, 'hs_steel_metal')
    m.box((x+.5, y-.18, .55), (.36, .36, 1.1), 'hs_ac_metal', .1)


def side_stair(m):
    """A steel stair up the west wall to a side door on the upper floor."""
    x = -W/2-.5; y0, y1 = Y0+D/2-.3, Y0-D/2+1.4
    steps = 14
    for k in range(steps):
        t = k/steps; m.box((x, y0+(y1-y0)*t, .3+F*t), (.9, .26, .05), 'hs_steel_metal')
    for xx in (x-.45, x+.45):
        m.beam((xx, y0, .3), (xx, y1, .3+F), .05, .18, 'hs_steel_metal')
        m.beam((xx, y0, 1.2), (xx, y1, F+1.2), .04, .04, 'hs_steel_metal')
        for k in range(1, 7):
            t = k/7; m.box((xx, y0+(y1-y0)*t, .3+F*t+.45), (.025, .025, .9), 'hs_steel_metal')
    m.box((x, y1-.6, F+.3), (1.0, 1.2, .08), 'hs_steel_metal')
    for yy in (y1-1.15, y1-.05):m.box((x-.45, yy, F+.8), (.04, .04, 1.0), 'hs_steel_metal')
    m.collider((x, (y0+y1)/2-.3, F/2+.3), (1.0, abs(y1-y0)+1.2, F+.6))
    with m.at((-W/2, Y0, 0), -90):          # local x runs towards -y here: the door opens onto the landing
        m.box((Y0-(y1-.6), -.06, F+1.3), (.9, .08, 2.0), 'hs_door_wood')
        m.poly([(Y0-(y1-.6)-.7, -.7, F+2.55), (Y0-(y1-.6)+.7, -.7, F+2.55), (Y0-(y1-.6)+.7, 0, F+2.75), (Y0-(y1-.6)-.7, 0, F+2.75)], 'hs_alu_metal')


def washing(m, x0, x1, y, z, r):
    m.box(((x0+x1)/2, y, z), (x1-x0, .03, .03), 'hs_alu_metal')
    for k in range(8):
        x = x0+.4+k*(x1-x0-.8)/7
        m.box((x, y, z-.25), (.45, .03, .45), ('hs_cloth_a', 'hs_cloth_b', 'hs_cloth_c')[r.randrange(3)])
