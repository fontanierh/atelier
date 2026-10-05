"""The temple hillside between the y=230 and y=335 streets: what turns two halls on a lawn into a precinct.

A stone-flagged approach climbs from the street to each temple's forecourt (civic_gardens.temple_ground) between pairs
of stone lanterns; a low mossy stone wall with a tile cap runs along the street with openings for the approaches and
the shrine; a three-storey pagoda stands west of the main hall, a small graveyard of grey stones on its own level
terrace east of it, and bamboo groves and maple clumps fill the back of the hill. The old rows of street lamps across
the lawn go. Builders: HD_Pagoda, HD_Bamboo, HD_Graves (local, placed on PADS), HD_Precinct (world space: paths and
wall, following the ground).
"""
import math, random

WALL_Y = 241.2            # the precinct wall's line, just off the y=230 street's paving (y 238)
WALL_X = (578., 826.)
APPROACHES = [(690., 266.)]                   # (x of the gap in the wall, y where the forecourt starts)
PAGODA = (641., 304.)
GRAVES = (739., 271., 34., 16.)               # centre x, y, width, depth
BAMBOO = [(616., 318., 7), (588., 312., 6), (662., 322., 6), (722., 318., 7), (758., 322., 5), (816., 312., 4)]
MAPLES = [(652., 288.), (628., 286.), (716., 290.), (762., 292.), (735., 258.), (747., 287.), (660., 262.), (622., 262.)]
GATES = [(600., 3.2), (690., 3.2), (820., 2.4)]                        # (x, half-width) openings in the wall
PADS = [dict(asset='HD_Pagoda', x=PAGODA[0], y=PAGODA[1], yaw=0, half_width=5., front=-5., back=5., fade_x=3., fade_y=3.,
             group='public'),
        dict(asset='HD_Graves', x=GRAVES[0], y=GRAVES[1], yaw=0, half_width=GRAVES[2]/2, front=-GRAVES[3]/2,
             back=GRAVES[3]/2, fade_x=3., fade_y=3., group='public')]
PALETTE = {'tp_flag_stone': (.25, .235, .205), 'tp_wall_stone': (.23, .22, .19), 'tp_wall_moss': (.075, .10, .04),
           'tp_wall_roof_cap': (.075, .08, .09), 'tp_grave_stone': (.33, .33, .31), 'tp_grave_stone_dark': (.25, .25, .24),
           'tp_grave_base_concrete': (.29, .28, .26), 'tp_gravel': (.26, .245, .21), 'tp_vermilion_timber': (.42, .085, .035),
           'tp_white_plaster': (.55, .52, .46), 'tp_bronze_metal': (.16, .12, .06), 'bamboo_cane': (.20, .25, .07),
           'bamboo_cane_old': (.24, .23, .10), 'bamboo_leaf': (.065, .12, .03), 'bamboo_leaf_light': (.10, .16, .04)}


def palette():
    from village import build as v
    v.PALETTE.update(PALETTE)


def place(put, inst, height, buildings):
    """Clear the lamp rows off the hill, then add the lantern-lined approaches, the pagoda, graves, bamboo and maples."""
    inst['HD_Lamp'] = [p for p in inst.get('HD_Lamp', []) if not (630 < p[0] < 810 and abs(p[1]-255) < 1.5)]
    for name in ('HD_Lamp', 'HD_Bench', 'HD_Planter'):
        inst[name] = [p for p in inst.get(name, []) if not (GRAVES[0]-GRAVES[2]/2-2 < p[0] < GRAVES[0]+GRAVES[2]/2+2 and
                                                           GRAVES[1]-GRAVES[3]/2-2 < p[1] < GRAVES[1]+GRAVES[3]/2+2)]
    x, y1 = APPROACHES[0]
    for y in range(int(WALL_Y)+4, int(y1)-1, 6):
        for side in (-1, 1):put('HD_P_stone_lantern', x+side*2.9, y)
    for name, (x, y), w, d in (('HD_Pagoda', PAGODA, 8.2, 8.2), ('HD_Graves', GRAVES[:2], GRAVES[2], GRAVES[3])):
        z = float(height(x, y)); put(name, x, y, z)
        buildings.append({'asset': name, 'position': [x, y, z], 'yaw': 0, 'width': w, 'depth': d, 'terrain_pad': True})
    for k, (bx, by, n) in enumerate(BAMBOO):
        r = random.Random(500+k)
        for i in range(n):
            a = r.uniform(0, math.tau); d = r.uniform(0, 4.5)
            put('HD_Bamboo', bx+math.cos(a)*d, by+math.sin(a)*d*.7, yaw=r.uniform(0, 360), scale=r.uniform(.85, 1.15))
    for k, (mx, my) in enumerate(MAPLES):
        r = random.Random(600+k)
        for i in range(3):
            put('Tree_Maple_A', mx+r.uniform(-3, 3), my+r.uniform(-2.5, 2.5), yaw=r.uniform(0, 360), scale=r.uniform(.9, 1.2))


def _ribbon(m, a, b, width, z_at, key, lift, step=2.):
    """A flat strip from a to b, width wide, following the ground (z_at) in step-metre pieces."""
    dx, dy = b[0]-a[0], b[1]-a[1]; length = math.hypot(dx, dy); ux, uy = dx/length, dy/length; nx, ny = -uy, ux
    n = max(1, math.ceil(length/step))
    for k in range(n):
        t0, t1 = k/n, (k+1)/n
        p0 = (a[0]+dx*t0, a[1]+dy*t0); p1 = (a[0]+dx*t1, a[1]+dy*t1)
        q = [(p0[0]-nx*width/2, p0[1]-ny*width/2), (p1[0]-nx*width/2, p1[1]-ny*width/2),
             (p1[0]+nx*width/2, p1[1]+ny*width/2), (p0[0]+nx*width/2, p0[1]+ny*width/2)]
        m.poly([(x, y, float(z_at(x, y))+lift) for x, y in q], key)


def precinct(m, height):
    """World-space paths and the precinct wall, following the ground."""
    palette()
    r = random.Random(77)
    # The main approach: big flags between the lanterns, a gravel margin either side.
    x, y1 = APPROACHES[0]
    y = WALL_Y-1.
    while y < y1:
        h = r.uniform(.8, 1.3)
        for k, w in enumerate((1.25, 1.25)):
            cx = x+(k-.5)*1.3
            _ribbon(m, (cx, y+.04), (cx, y+h-.04), w-.06, height, 'tp_flag_stone', .05, step=h)
        y += h
    for side in (-1, 1):_ribbon(m, (x+side*2.0, WALL_Y-1.), (x+side*2.0, y1), 1.4, height, 'tp_gravel', .035)
    # The east temple's approach comes up from the street corner at an angle, a gravel path with stepping stones.
    a = math.radians(25.); fx, fy = 790+14*math.sin(a), 305-14*math.cos(a)
    run = (fy-WALL_Y+1.)/math.cos(a)                   # back down the temple's axis to the wall's gate (x ~ 820)
    sx, sy = fx+math.sin(a)*run, fy-math.cos(a)*run
    _ribbon(m, (sx, sy), (fx, fy-2), 2.6, height, 'tp_gravel', .04)
    n = int(math.hypot(sx-fx, sy-fy)/1.1)
    for k in range(1, n):
        t = k/n; px, py = sx+(fx-sx)*t, sy+(fy-2-sy)*t
        _ribbon(m, (px-math.sin(a)*.35, py+math.cos(a)*.35), (px+math.sin(a)*.35, py-math.cos(a)*.35), .9, height,
                'tp_flag_stone', .06, step=.7)
    # The wall along the street, with openings.
    x = WALL_X[0]
    while x < WALL_X[1]:
        gate = next(((gx, gw) for gx, gw in GATES if gx-gw <= x+2 and x < gx+gw), None)
        if gate:x = gate[0]+gate[1];continue
        x1 = min(x+2., WALL_X[1], *[gx-gw for gx, gw in GATES if gx-gw > x])
        za, zb = float(height(x, WALL_Y)), float(height(x1, WALL_Y))
        _wall(m, x, x1, WALL_Y, za, zb, r)
        x = x1
    for gx, gw in GATES:
        for side in (-1, 1):
            px = gx+side*(gw+.25); z = float(height(px, WALL_Y))
            m.box((px, WALL_Y, z+.45), (.5, .55, 1.6), 'tp_wall_stone')
            m.box((px, WALL_Y, z+1.3), (.62, .66, .12), 'tp_wall_roof_cap')
            m.collider((px, WALL_Y, z+.45), (.5, .55, 1.6))
    return m


def _wall(m, x0, x1, y, za, zb, r):
    h = 1.05
    pts = lambda yy, lo, hi: [(x0, yy, za+lo), (x1, yy, zb+lo), (x1, yy, zb+hi), (x0, yy, za+hi)]
    for yy, rev in ((y-.3, False), (y+.3, True)):
        q = pts(yy, -.4, h); m.poly(q[::-1] if rev else q, 'tp_wall_stone')
    m.poly([(x0, y-.3, za+h), (x1, y-.3, zb+h), (x1, y+.3, zb+h), (x0, y+.3, za+h)], 'tp_wall_moss')
    m.poly([(x0, y-.38, za+h+.02), (x1, y-.38, zb+h+.02), (x1, y+.38, zb+h+.12), (x0, y+.38, za+h+.12)][::1], 'tp_wall_roof_cap')
    if r.random() < .5:   # a few dark stone courses
        m.poly([(x0, y-.31, za+.25), (x1, y-.31, zb+.25), (x1, y-.31, zb+.32), (x0, y-.31, za+.32)], 'tp_wall_moss')
    m.collider(((x0+x1)/2, y, (za+zb)/2+.3), (x1-x0, .6, h+.6))


def pagoda():
    """A three-storey pagoda, 6 m square at the base, about 21 m to the tip of the spire."""
    from village import build as v
    palette()
    m = v.Mesh('HD_Pagoda')
    m.box((0, 0, -.1), (7.4, 7.4, .9), 'tp_wall_stone'); m.box((0, 0, .45), (8.2, 8.2, .2), 'tp_flag_stone')
    m.collider((0, 0, 4.5), (6., 6., 9.))
    for k in range(3, 0, -1):m.box((0, -4.1-k*.32, .35-k*.13), (2.2, .32, .13*k*2), 'tp_wall_stone')   # steps
    z = .55
    for storey in range(3):
        s = 6.0-storey*.85; hgt = 3.0-storey*.25
        m.box((0, 0, z+hgt/2), (s, s, hgt), 'tp_white_plaster')
        for px in (-1, 1):
            for py in (-1, 1):m.box((px*(s/2-.05), py*(s/2-.05), z+hgt/2), (.28, .28, hgt), 'tp_vermilion_timber')
            for side in (-1, 1):m.box((px*(s/6), side*(s/2+.02), z+hgt/2), (.22, .1, hgt), 'tp_vermilion_timber')
        for side in (-1, 1):
            m.box((0, side*(s/2+.03), z+hgt/2-.2), (s/3-.25, .06, hgt-.8), 'tp_vermilion_timber')   # doors
            m.box((side*(s/2+.03), 0, z+hgt/2-.2), (.06, s/3-.25, hgt-.8), 'tp_vermilion_timber')
        m.box((0, 0, z+hgt-.15), (s+.3, s+.3, .3), 'tp_vermilion_timber')   # bracket band
        if storey == 0:
            m.box((0, 0, z+.25), (s+1.6, s+1.6, .12), 'tp_vermilion_timber')   # veranda
            for px in (-1, 1):
                for py in (-1, 1):m.box((px*(s/2+.7), py*(s/2+.7), z+.6), (.08, .08, .7), 'tp_vermilion_timber')
        z += hgt
        _pyramid(m, s+3.4-storey*.25, z, .9)
        z += .55
    m.box((0, 0, z+.1), (1.4, 1.4, .5), 'roof')
    for k in range(9):m.lathe((0, 0, z+.5+k*.55), [(0, .26), (.12, .3), (.24, .2)], 'tp_bronze_metal', n=8)
    m.lathe((0, 0, z+.5), [(0, .09), (5.6, .06)], 'tp_bronze_metal', n=6)
    m.lathe((0, 0, z+5.8), [(0, .2), (.3, .26), (.6, 0)], 'tp_bronze_metal', n=8)
    return m


def _pyramid(m, w, z, rise):
    """A wide square roof from eave height z with upturned corners: tile slopes, a thick eave, hip rolls, a soffit."""
    t = w/2; top = .9
    def ring8(f, lift):
        c = [(-1, -1), (1, -1), (1, 1), (-1, 1)]; out = []
        for i in range(4):
            (ax, ay), (bx, by) = c[i], c[(i+1) % 4]
            out.append((ax*t*f, ay*t*f, lift)); out.append(((ax+bx)/2*t*f, (ay+by)/2*t*f, 0.))
        return out
    levels = [(1., 0., .3), (.82, rise*.3, .1), (.55, rise*.72, 0.), (top/t, rise, 0.)]
    for (f0, z0, l0), (f1, z1, l1) in zip(levels, levels[1:]):
        a, b = ring8(f0, l0), ring8(f1, l1)
        for i in range(8):
            j = (i+1) % 8
            m.poly([(a[i][0], a[i][1], z+z0+a[i][2]), (a[j][0], a[j][1], z+z0+a[j][2]),
                    (b[j][0], b[j][1], z+z1+b[j][2]), (b[i][0], b[i][1], z+z1+b[i][2])], 'roof')
    a = ring8(1., .3)
    m.poly([(p[0]*.97, p[1]*.97, z-.3+p[2]) for p in a[::-1]], 'tp_vermilion_timber')
    for i in range(8):
        j = (i+1) % 8
        p, q = a[i], a[j]
        m.beam((p[0], p[1], z+p[2]-.1), (q[0], q[1], z+q[2]-.1), .2, .38, 'roof_edge')
        m.beam((p[0]*.97, p[1]*.97, z+p[2]-.42), (q[0]*.97, q[1]*.97, z+q[2]-.42), .3, .25, 'tp_vermilion_timber')
    for i in range(0, 8, 2):
        p = a[i]; m.beam((p[0]*1.02, p[1]*1.02, z+p[2]+.1), (p[0]*top/t, p[1]*top/t, z+rise+.05), .22, .22, 'roof_edge')


def bamboo():
    """A clump of a dozen canes, 7-11 m, leaning a little outwards, with leaf sprays in their upper third."""
    from village import build as v
    palette()
    m = v.Mesh('HD_Bamboo'); r = random.Random(41)
    for k in range(12):
        a = r.uniform(0, math.tau); d = r.uniform(0, .9); x, y = math.cos(a)*d, math.sin(a)*d
        h = r.uniform(7., 11.); lean = r.uniform(.3, 1.); tx, ty = x+math.cos(a)*lean, y+math.sin(a)*lean
        cane = 'bamboo_cane' if k % 4 else 'bamboo_cane_old'
        m.beam((x, y, -.2), (tx, ty, h), .085, .085, cane)
        for j in range(1, int(h/1.4)):   # nodes
            t = j*1.4/h; m.box((x+(tx-x)*t, y+(ty-y)*t, -.2+(h+.2)*t), (.12, .12, .05), cane)
        for j in range(9):
            t = r.uniform(.55, .98); cx, cy, cz = x+(tx-x)*t, y+(ty-y)*t, -.2+(h+.2)*t
            b = r.uniform(0, math.tau); L = r.uniform(.7, 1.2)
            ex, ey = cx+math.cos(b)*L, cy+math.sin(b)*L; nx, ny = -math.sin(b)*.22, math.cos(b)*.22
            leaf = 'bamboo_leaf' if j % 2 else 'bamboo_leaf_light'
            q = [(cx, cy, cz), (cx+(ex-cx)*.5+nx, cy+(ey-cy)*.5+ny, cz-.25), (ex, ey, cz-.7), (cx+(ex-cx)*.5-nx, cy+(ey-cy)*.5-ny, cz-.25)]
            m.poly(q, leaf); m.poly(q[::-1], leaf)
    m.collider((0, 0, 1.5), (1.4, 1.4, 3.))
    return m


def graves():
    """A small temple graveyard on its terrace: rows of family stones on stepped bases, a few stupa boards, a path."""
    from village import build as v
    palette()
    m = v.Mesh('HD_Graves'); r = random.Random(23)
    w, d = GRAVES[2], GRAVES[3]
    m.box((0, 0, -.25), (w, d, .5), 'tp_gravel')
    m.box((0, 0, -.2), (1.8, d, .5), 'tp_flag_stone')         # the central path
    for row in range(4):
        y = -d/2+2.2+row*3.8
        for side in (-1, 1):
            for k in range(6):
                x = side*(2.2+k*2.45)
                if x*side > w/2-1.2:continue
                stone = 'tp_grave_stone' if r.random() < .65 else 'tp_grave_stone_dark'
                m.box((x, y, .05), (1.9, 1.9, .3), 'tp_grave_base_concrete')
                m.box((x, y+.2, .32), (1.1, 1.0, .25), 'tp_grave_base_concrete')
                hgt = r.uniform(.9, 1.3)
                m.box((x, y+.25, .45+hgt/2), (.55, .45, hgt), stone)
                m.box((x, y+.25, .47+hgt), (.6, .5, .06), stone)
                if r.random() < .5:      # flower holders and an incense stand
                    for f in (-1, 1):m.box((x+f*.42, y-.2, .5), (.12, .12, .2), stone)
                if r.random() < .3:      # wooden stupa boards behind
                    for b in range(r.randint(2, 4)):m.box((x-.3+b*.2, y+.85, .9+b*.05), (.1, .03, 1.5+b*.1), 'wood_light')
                m.collider((x, y, .5), (1.9, 1.9, 1.))
    # A low stone curb round the terrace.
    for side in (-1, 1):
        m.box((side*w/2, 0, .05), (.3, d, .6), 'tp_wall_stone'); m.box((0, side*d/2, .05), (w, .3, .6), 'tp_wall_stone')
    return m
