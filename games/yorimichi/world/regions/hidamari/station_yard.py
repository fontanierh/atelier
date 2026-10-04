"""The railway behind Hidamari station, and the station square's flanks.

The station kit (kit/station.py) has its platform and canopy along the back of the building (world y 295-300, top
25 cm above the station floor). Behind it the line's single track lies in a shallow cutting on its own terrain pad
(PAD, level with the track bed, grassed slopes up to the hillside): a buffer stop closes the west end, and at the
east end the track runs into a small timber engine shed whose masonry end wall hides the step up to the x=1240 lane.
A two-car local railcar waits at the platform. In front, two shop lots close the square's flanks
(layout.shop_sites), a roofed bicycle shelter stands west of it and a kiosk by the station's east end.
Builders: HD_StationYard (world space: track, cutting floor, buffer, shed, shelter, kiosk), HD_Railcar (local, at
the platform).
"""
import math

STATION = (1185., 290.)
TRACK_Y = 301.45                  # the platform edge is y 299.95; the car body is 2.85 m wide
X0, X1 = 1134., 1231.4            # the cutting floor; the lane's road corridor begins at x 1231.6
Y0, Y1 = 299.9, 305.2
RAIL = -.67                       # rail top below the station floor (platform top +.25, 92 cm above the rail)
BED = RAIL-.72                    # the cutting floor
BUFFER_X = 1136.5
SHED = (1213., 1231.9)            # x extent; its end wall (x 1231.1-1232.1) stands over the terrain step
CARS = 2; CAR = 20.; GAP = .3     # the railcar: cars and their length
SHOPS = [('HD_Shop_05', 1143., 249.), ('HD_Shop_11', 1219.5, 249.)]   # north side of the y=230 street, facing it
SHELTER = (1146.2, 1150.0, 265.4, 276.2)   # x0, x1, y0, y1: over the bicycles at x 1148
KIOSK = (1221., 288.)             # faces west, towards the station's east end
# The pad's front is its north side (yaw 180): the review's approach probe lands on the cutting's foot there.
PAD = dict(asset='HD_StationYard', x=(X0+X1)/2, y=(Y0+Y1)/2, yaw=180, half_width=(X1-X0)/2, front=-(Y1-Y0)/2,
           back=(Y1-Y0)/2, fade_x=4., fade_y=4., group='public')
PALETTE = {'sy_ballast_gravel': (.20, .19, .17), 'sy_floor_gravel': (.24, .22, .19),
           'sy_sleeper_concrete': (.30, .29, .27), 'sy_rail_steel': (.09, .07, .06), 'sy_rail_head_steel': (.30, .30, .31),
           'sy_platform_concrete': (.33, .31, .28), 'sy_buffer_concrete': (.32, .31, .29),
           'sy_buffer_red_stripe': (.55, .06, .03), 'sy_buffer_white_stripe': (.75, .73, .68),
           'sy_shed_board': (.13, .085, .05), 'sy_shed_timber': (.20, .13, .07), 'sy_shed_roof_tin': (.10, .11, .12),
           'sy_shed_end_concrete': (.29, .28, .26), 'sy_shadow': (.012, .010, .009), 'sy_lamp_glow': (1., .75, .4),
           'sy_shelter_steel': (.20, .24, .22), 'sy_shelter_roof_tin': (.32, .36, .34),
           'sy_kiosk_green': (.07, .20, .13), 'sy_kiosk_cream_plaster': (.62, .56, .43), 'sy_kiosk_shutter': (.35, .36, .36),
           'sy_kiosk_display': (.55, .30, .12), 'sy_kiosk_sign': (.70, .66, .55),
           'sy_mag_red_cloth': (.55, .10, .06), 'sy_mag_blue_cloth': (.10, .20, .45), 'sy_mag_yellow_cloth': (.65, .50, .10),
           'rc_body_buff': (.60, .52, .36), 'rc_band_crimson': (.42, .05, .04), 'rc_top_grey': (.17, .17, .18),
           'rc_window_glass': (.04, .05, .06), 'rc_under_iron': (.035, .035, .035), 'rc_bogie_iron': (.05, .045, .04),
           'rc_head_lamp': (1.2, 1.1, .8), 'rc_tail_lamp': (.8, .05, .02), 'rc_door_steel': (.52, .45, .31),
           'rc_rubber_gangway': (.05, .05, .05), 'rc_dest_sign': (.80, .78, .70)}


def palette():
    from village import build as v
    v.PALETTE.update(PALETTE)


def floor_z():
    from hidamari import layout
    return float(layout.street_height(STATION[0], STATION[1]-11.5))   # HD_Station's pad (layout.terrain_pads)


def place(put, inst, height, buildings):
    """The railcar, the yard's lot record, and no stray scatter in the cutting, the new lots or the shelter."""
    z = floor_z()
    put('HD_Railcar', STATION[0], TRACK_Y, z+RAIL)
    buildings.append({'asset': 'HD_StationYard', 'position': [PAD['x'], PAD['y'], z+BED], 'yaw': 180,
                      'width': X1-X0, 'depth': Y1-Y0, 'terrain_pad': True})
    boxes = [(X0-2, X1+1, Y0-2, Y1+2), (SHELTER[0]-.5, SHELTER[1]+.5, SHELTER[2]-.5, SHELTER[3]+.5),
             (KIOSK[0]-2.2, KIOSK[0]+2.2, KIOSK[1]-2.6, KIOSK[1]+2.6)]
    boxes += [(x-13.5, x+13.5, y-11.6, y+11.6) for _, x, y in SHOPS]
    for name, items in inst.items():
        if name.startswith(('HD_Shop_', 'HD_Railcar', 'HD_P_')) or not items: continue
        inst[name] = [p for p in items if not any(a < p[0] < b and c < p[1] < d for a, b, c, d in boxes)]


def _shed(m, z):
    """A dark-stained board engine shed over the track's east end, its doors folded open towards the station."""
    x0, x1 = SHED; ys, yn = Y0-.45, Y1+.25; cy = (ys+yn)/2; w = yn-ys
    eave, ridge, base = z+RAIL+4.4, z+RAIL+5.5, z+BED-.25
    # masonry end wall, gable and all, over the terrain step
    m.box((1231.6, cy, (base+eave)/2), (1.0, w+.5, eave-base), 'sy_shed_end_concrete'); m.collider((1231.6, cy, (base+eave)/2), (1.0, w+.5, eave-base))
    m.poly([(1231.1, ys-.25, eave), (1231.1, yn+.25, eave), (1231.1, cy, ridge)], 'sy_shed_end_concrete')
    m.poly([(1232.1, yn+.25, eave), (1232.1, ys-.25, eave), (1232.1, cy, ridge)], 'sy_shed_end_concrete')
    m.box((1231.05, cy, (z+BED+eave)/2), (.04, w-.6, eave-z-BED), 'sy_shadow')
    for y in (ys+.125, yn-.125):                                   # board side walls, dark inside
        m.box(((x0+1231.1)/2, y, (base+eave)/2), (1231.1-x0, .25, eave-base), 'sy_shed_board')
        m.collider(((x0+1231.1)/2, y, (base+eave)/2), (1231.1-x0, .25, eave-base))
        inner = y+(.14 if y < cy else -.14)
        m.box(((x0+1231.1)/2, inner, (z+BED+eave)/2), (1231.1-x0-.1, .03, eave-z-BED), 'sy_shadow')
        for x in range(int(x0)+1, 1231, 3):                        # posts proud of the boards
            m.box((x, y+(-.16 if y < cy else .16), (base+eave)/2), (.16, .08, eave-base), 'sy_shed_timber')
    m.box(((x0+1231.1)/2, cy, eave-.05), (1231.1-x0, w-.5, .04), 'sy_shadow')   # the dark under-roof
    for side in (-1, 1):                                           # corrugated tin roof, eaves out .5 m
        y_e = cy+side*(w/2+.5); pts = [(x0-.6, cy, ridge+.02), (1232.4, cy, ridge+.02), (1232.4, y_e, eave-.3), (x0-.6, y_e, eave-.3)]
        m.poly(pts if side > 0 else [pts[1], pts[0], pts[3], pts[2]], 'sy_shed_roof_tin')
        m.poly([pts[0], pts[3], pts[2], pts[1]] if side > 0 else [pts[0], pts[1], pts[2], pts[3]], 'sy_shadow')
        for k in range(int((1232.4-x0)/.8)):                      # corrugation ribs
            x = x0-.4+k*.8; m.beam((x, cy, ridge+.05), (x, y_e, eave-.27), .05, .03, 'sy_shed_roof_tin')
    m.beam((x0-.6, cy, ridge+.08), (1232.4, cy, ridge+.08), .22, .12, 'sy_shed_roof_tin')
    # the open west end: gable boards above the doorway, posts, and the two door leaves folded back
    door = z+RAIL+4.0
    m.poly([(x0, yn, door), (x0, ys, door), (x0, ys, eave), (x0, yn, eave)], 'sy_shed_board')
    m.poly([(x0, yn, eave), (x0, ys, eave), (x0, cy, ridge)], 'sy_shed_board')
    m.poly([(x0+.05, ys, door), (x0+.05, yn, door), (x0+.05, yn, eave), (x0+.05, ys, eave)], 'sy_shadow')
    for y in (ys+.2, yn-.2):
        m.box((x0, y, (base+door)/2), (.3, .3, door-base), 'sy_shed_timber'); m.collider((x0, y, (base+door)/2), (.3, .3, door-base))
        out = -1 if y < cy else 1
        m.box((x0-1.4, y+out*.35, (z+BED+door)/2+.1), (2.6, .1, door-z-BED-.3), 'sy_shed_board')
        for zz in (z+BED+.6, door-.6):
            m.beam((x0-2.6, y+out*.42, zz), (x0-.2, y+out*.42, zz), .12, .06, 'sy_shed_timber')
    m.beam((x0, ys, door), (x0, yn, door), .3, .3, 'sy_shed_timber')
    m.box((x0-.25, cy, door+.55), (.25, .3, .2), 'sy_lamp_glow')


def _shelter(m, height):
    """A steel bicycle shelter with a sloping corrugated roof, cantilevered from posts along its back."""
    x0, x1, y0, y1 = SHELTER
    zs = [float(height(x0+.2, y)) for y in (y0, y1)]
    top = max(zs)+2.45
    for k in range(5):
        y = y0+.3+k*(y1-y0-.6)/4; g = float(height(x0+.3, y))
        m.box((x0+.3, y, (g+top)/2), (.12, .12, top-g+.1), 'sy_shelter_steel'); m.collider((x0+.3, y, (g+top)/2), (.14, .14, top-g))
        m.beam((x0+.3, y, top-.6), (x1-.2, y, top-.12), .08, .1, 'sy_shelter_steel')
        m.beam((x0+.3, y, top-.05), (x1-.2, y, top-.32), .08, .12, 'sy_shelter_steel')
        rg = float(height(x1-.5, y)); m.beam((x1-.6, y-.6, rg+.32), (x1-.6, y+.6, rg+.32), .04, .04, 'sy_shelter_steel')
    m.poly([(x0, y0, top), (x0, y1, top), (x1, y1, top-.3), (x1, y0, top-.3)], 'sy_shelter_roof_tin')
    m.poly([(x0, y1, top-.04), (x0, y0, top-.04), (x1, y0, top-.34), (x1, y1, top-.34)], 'sy_shelter_roof_tin')
    m.beam((x1, y0, top-.37), (x1, y1, top-.37), .06, .1, 'sy_shelter_steel')


def _kiosk(m, height):
    """A small green and cream station kiosk with its counter, magazine racks and a sign board (no lettering)."""
    x, y = KIOSK; g = min(float(height(x+sx, y+sy)) for sx in (-1.2, 1.2) for sy in (-1.7, 1.7))
    with m.at((x, y, g), -90):                                     # front (-Y local) faces west
        m.box((0, 0, .1), (3.6, 2.6, .2), 'sy_buffer_concrete'); m.collider((0, 0, 1.3), (3.4, 2.4, 2.6))
        m.box((0, .25, 1.35), (3.4, 1.9, 2.3), 'sy_kiosk_cream_plaster')
        m.box((0, -.82, .6), (3.4, .36, .8), 'sy_kiosk_green')    # counter front
        m.box((0, -.86, 1.03), (3.5, .5, .06), 'sy_kiosk_green')
        m.box((0, -.68, 1.62), (2.6, .05, 1.1), 'sy_shadow')      # the open hatch
        for k in range(5):m.box((-1.0+k*.5, -.95, 1.12), (.42, .3, .09), ('sy_mag_red_cloth', 'sy_mag_blue_cloth', 'sy_mag_yellow_cloth')[k % 3])
        for sx in (-1.45, 1.45):
            for r in range(3):m.box((sx, -.8, .5+r*.42), (.42, .2, .3), ('sy_mag_blue_cloth', 'sy_mag_yellow_cloth', 'sy_mag_red_cloth')[(r+int(sx > 0)) % 3])
        m.box((0, 0, 2.62), (4.0, 3.2, .16), 'sy_kiosk_green')     # roof slab
        m.box((0, -1.62, 2.38), (4.0, .5, .32), 'sy_kiosk_green')  # fascia
        m.box((0, -1.88, 2.4), (2.6, .04, .26), 'sy_kiosk_sign')
        m.box((0, -1.3, 2.25), (3.6, .1, .06), 'sy_lamp_glow')
        m.box((2.15, .2, .55), (.5, .6, 1.1), 'sy_kiosk_display'); m.box((2.15, .2, 1.12), (.56, .66, .05), 'sy_kiosk_green')


def yard(m, height):
    """HD_StationYard, in world space."""
    palette(); z = floor_z(); rail = z+RAIL; bed = z+BED
    for x in range(int(X0), int(X1)):                             # the cutting's gravel floor
        x1 = min(x+1., X1)
        m.poly([(x, Y0, bed+.015), (x1, Y0, bed+.015), (x1, Y1, bed+.015), (x, Y1, bed+.015)], 'sy_floor_gravel')
    tx0 = BUFFER_X-.6; tx1 = 1231.1
    for x in range(int(tx0), int(tx1)):                           # ballast shoulder, in metre pieces
        a, b = max(x, tx0), min(x+1., tx1)
        top, foot = rail-.27, bed+.01
        for side in (-1, 1):
            p = [(a, TRACK_Y+side*1.45, top), (b, TRACK_Y+side*1.45, top), (b, TRACK_Y+side*2.05, foot), (a, TRACK_Y+side*2.05, foot)]
            m.poly(p if side > 0 else [p[1], p[0], p[3], p[2]], 'sy_ballast_gravel')
        m.poly([(a, TRACK_Y-1.45, top), (b, TRACK_Y-1.45, top), (b, TRACK_Y+1.45, top), (a, TRACK_Y+1.45, top)], 'sy_ballast_gravel')
    x = tx0+.3
    while x < tx1-.2:                                              # concrete sleepers
        m.box((x, TRACK_Y, rail-.24), (.24, 2.0, .16), 'sy_sleeper_concrete'); x += .62
    for side in (-1, 1):                                           # rails, in 8 m lengths
        y = TRACK_Y+side*.5335; x = tx0
        while x < tx1:
            b = min(x+8., tx1)
            m.box(((x+b)/2, y, rail-.15), (b-x-.01, .13, .03), 'sy_rail_steel')
            m.box(((x+b)/2, y, rail-.08), (b-x-.01, .03, .13), 'sy_rail_steel')
            m.box(((x+b)/2, y, rail-.015), (b-x-.01, .07, .03), 'sy_rail_head_steel'); x = b
    # the platform's track-side face, under the kit platform's edge
    m.box((STATION[0], 299.84, (bed-.1+z+.22)/2), (46.8, .22, z+.22-bed+.1), 'sy_platform_concrete')
    m.collider((STATION[0], 299.84, (bed+z+.22)/2), (46.8, .22, z+.22-bed))
    # the buffer stop: a concrete block with a striped board facing the line
    m.box((BUFFER_X-.7, TRACK_Y, rail+.25), (1.2, 3.0, 1.4), 'sy_buffer_concrete', .05)
    m.collider((BUFFER_X-.7, TRACK_Y, rail+.25), (1.2, 3.0, 1.4))
    for k in range(6):
        m.box((BUFFER_X-.08, TRACK_Y-1.25+k*.5, rail+.75), (.06, .5, .45), 'sy_buffer_red_stripe' if k % 2 == 0 else 'sy_buffer_white_stripe')
    m.box((BUFFER_X-.2, TRACK_Y, rail+1.15), (.12, .3, .3), 'sy_lamp_glow')
    _shed(m, z)
    _shelter(m, height)
    _kiosk(m, height)
    return m


def railcar():
    """HD_Railcar: a two-car local diesel railcar, buff with a crimson band, origin at rail top between the cars."""
    from village import build as v
    palette(); m = v.Mesh('HD_Railcar')
    W2 = 1.425
    for c in range(CARS):
        cx = (c-(CARS-1)/2)*(CAR+GAP)
        end = -1 if c == 0 else 1                                   # the cab end
        m.box((cx, 0, 2.3), (CAR, 2*W2, 2.7), 'rc_body_buff'); m.collider((cx, 0, 2.3), (CAR, 2*W2, 2.7))
        m.box((cx, 0, 3.72), (CAR-.4, 2*W2-.2, .18), 'rc_top_grey')
        m.box((cx, 0, 3.86), (CAR-1.4, 2*W2-.7, .14), 'rc_top_grey')
        m.box((cx, 0, .85), (CAR-.3, 2*W2-.25, .3), 'rc_under_iron')
        for side in (-1, 1):
            y = side*(W2+.005)
            m.box((cx, y, 1.55), (CAR, .02, .32), 'rc_band_crimson')
            m.box((cx, y, 3.25), (CAR, .02, .08), 'rc_band_crimson')
            for k in range(8):                                     # windows between the doors
                wx = cx-6.3+k*1.8
                m.box((wx, y, 2.42), (1.25, .03, .85), 'rc_window_glass')
            for dx in (-8.6, 8.6):                                 # doors near the car ends
                m.box((cx+dx, y, 2.05), (1.1, .03, 2.1), 'rc_door_steel')
                m.box((cx+dx, y+side*.01, 2.55), (.7, .02, .7), 'rc_window_glass')
        for bx in (-6.9, 6.9):                                     # bogies: frame, wheels, springs
            m.box((cx+bx, 0, .55), (2.6, 2.0, .34), 'rc_bogie_iron')
            for wx in (-1.05, 1.05):
                for side in (-1, 1):m.box((cx+bx+wx, side*.62, .43), (.86, .1, .86), 'rc_under_iron')
        m.box((cx, 0, .9), (3.2, 1.6, .5), 'rc_under_iron')        # engine and tanks under the floor
        m.beam((cx+end*(-3.0), .9, 3.9), (cx+end*(-3.0), .9, 4.4), .18, .18, 'rc_under_iron')  # exhaust stack
        # the cab face: windows, destination box, lamps
        fx = cx+end*(CAR/2+.01)
        m.box((fx, 0, 2.6), (.03, 2*W2-.3, .95), 'rc_window_glass')
        m.box((fx, 0, 3.45), (.03, 1.1, .3), 'rc_dest_sign')
        for side in (-1, 1):
            m.box((fx, side*.95, 1.75), (.04, .3, .2), 'rc_head_lamp')
            m.box((fx, side*.95, 1.45), (.04, .2, .14), 'rc_tail_lamp')
        m.box((fx+end*.15, 0, .95), (.3, 2.2, .3), 'rc_under_iron')   # skirt
    m.box((0, 0, 2.2), (GAP+.2, 1.3, 2.2), 'rc_rubber_gangway')
    return m
