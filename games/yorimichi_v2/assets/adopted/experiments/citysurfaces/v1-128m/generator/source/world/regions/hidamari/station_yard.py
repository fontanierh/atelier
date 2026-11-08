"""The railway behind Hidamari station, and the station square's flanks.

The clock-tower station keeps its existing platform and canopy. The platform is extended by the Belmonte train
service at the same height, with standard-gauge track from train/track.py and a cutting open to the east. The old
static railcar, narrow-gauge track and blocking engine shed are gone. HD_StationYard supplies the cutting floor,
bicycle shelter and kiosk; the east lane ends on each side of the railway. Two shop lots flank the station square.
"""

from hidamari.station_yard_placement import (
    BED, KIOSK, LANE_BREAK, PAD, RAIL, SHELTER, SHOPS, STATION, X0, X1, Y0, Y1, floor_z, place,
)

TRACK_Y = 301.8                   # 1.85 m from the existing platform edge at y=299.95
SERVICE_CENTRE = (1208., TRACK_Y)
# The pad's front is its north side (yaw 180): the review's approach probe lands on the cutting's foot there.
PALETTE = {'sy_floor_gravel': (.24, .22, .19), 'sy_buffer_concrete': (.32, .31, .29),
           'sy_shadow': (.012, .010, .009), 'sy_lamp_glow': (1., .75, .4),
           'sy_shelter_steel': (.20, .24, .22), 'sy_shelter_roof_tin': (.32, .36, .34),
           'sy_kiosk_green': (.07, .20, .13), 'sy_kiosk_cream_plaster': (.62, .56, .43),
           'sy_kiosk_display': (.55, .30, .12), 'sy_kiosk_sign': (.70, .66, .55),
           'sy_mag_red_cloth': (.55, .10, .06), 'sy_mag_blue_cloth': (.10, .20, .45),
           'sy_mag_yellow_cloth': (.65, .50, .10)}


def palette():
    from village import mesh as v
    v.PALETTE.update(PALETTE)


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
    palette(); z = floor_z(); bed = z+BED
    for x in range(int(X0), int(X1)):                             # the cutting's gravel floor
        x1 = min(x+1., X1)
        m.poly([(x, Y0, bed+.015), (x1, Y0, bed+.015), (x1, Y1, bed+.015), (x, Y1, bed+.015)], 'sy_floor_gravel')
    _shelter(m, height)
    _kiosk(m, height)
    lane, south, north = LANE_BREAK
    for y in (south, north):
        g = float(height(lane, y))
        m.box((lane, y, g+.8), (6.0, .12, .18), 'sy_shelter_steel')
        m.collider((lane, y, g+.5), (6.0, .2, 1.))
        for dx in (-2.8, 2.8):
            m.box((lane+dx, y, g+.4), (.12, .12, .8), 'sy_shelter_steel')
    return m
