"""One Brinecove constructor or shared geometry primitive; no sibling generation."""
from brinecove import landmarks as LM
from brinecove import layout as L
from brinecove.geom import Builder
from brinecove.kit import bench
from brinecove.kit import building
from brinecove.kit import bush
from brinecove.kit import local
from brinecove.kit import palm
from brinecove.kit import pennants
from brinecove.kit import potted_plant
from brinecove.kit import vine
from brinecove.procedural.geometry_policy import TERRACE_CHEEKS
from brinecove.procedural.geometry_policy import TERRACE_STAIRS
from brinecove.procedural.pave_band import pave_band
from brinecove.procedural.paving import paving
from brinecove.procedural.random_state import RNG
from brinecove.procedural.split_lot import split_lot
from brinecove.procedural.terrace_stair import terrace_stair


def upper_town():
    b = Builder('05_town_upper')
    # Terrace surface and street.
    paving(b, -320.0, 320.0, 287.0, 393.0, z=L.UPPER_Z + 0.22, tile=7.0, thick=0.4, kerbs=(False, False), seed=5)
    paving(b, -320.0, 320.0, 279.0, 287.0, z=L.UPPER_Z + 0.22, tile=7.0, thick=0.4, kerbs=(False, False), seed=6)
    # The terrace's carriageway: a band of dark setts between two flagstone kerbs.
    b.box((0, 340, L.UPPER_Z + 0.16), (620, 22, 0.18), 'cobble_dark')
    for yy in (328.8, 351.2):
        b.box((0, yy, L.UPPER_Z + 0.3), (620, 0.6, 0.2), 'stone_light')
    for y0, y1 in ((354, 400), (424, 452)):
        pave_band(b, y0, y1, skip_market=False)
    # Balustrade along the harbor edge, broken for the three stairs.
    for x in range(-310, 311, 4):
        if abs(x) < 18 or 224 < abs(x) < 262:
            continue
        b.box((x, 283, L.UPPER_Z + 0.7), (3.2, 0.55, 1.4), 'stone')
        b.box((x, 283, L.UPPER_Z + 1.45), (3.5, 0.8, 0.28), 'stone_light')
    for x in (-309, -265, -221, -18, 18, 221, 265, 309):
        b.box((x, 283, L.UPPER_Z + 0.9), (2.2, 1.2, 1.8), 'stone_light')
        b.sphere((x, 283, L.UPPER_Z + 1.95), 0.55, 'stone_dark', (1.0, 1.0, 0.8), subdiv=0)
    # Retaining wall, buttresses, niches and a coping.
    wall_mid = (L.QUAY_Z + L.UPPER_Z) / 2
    wall_h = L.UPPER_Z - L.QUAY_Z
    for x0, x1 in ((-322, -252), (-224, -26), (26, 224), (262, 342)):
        b.box(((x0 + x1) / 2, 281, wall_mid), (x1 - x0, 3.0, wall_h), 'stone')
        b.box(((x0 + x1) / 2, 279.7, L.UPPER_Z + 0.15), (x1 - x0 + 2, 4.6, 0.5), 'stone_light')
        # Warm ashlar courses and hanging greenery give the tall retaining
        # wall a human scale instead of one long grey viaduct face.
        for zz in range(7, 29, 4):
            b.box(((x0 + x1) / 2, 279.42, zz), (x1 - x0, 0.36, 0.20), 'stone_light')
        for x in range(int(x0) + 10, int(x1), 32):
            b.box((x, 278.8, wall_mid - 0.5), (5.0, 2.8, wall_h - 1.0), 'stone_light')
            b.box((x, 278.4, wall_mid + 0.4), (2.4, 0.8, 4.2), 'stone_dark')
            b.box((x, 278.2, wall_mid + 2.5), (2.4, 0.7, 2.4), 'stone_dark')
    for i in range(30):
        vx = RNG.uniform(-316, 336)
        if abs(vx) < 32:
            continue
        vine(b, vx, 278.9, L.UPPER_Z - 0.2, RNG.uniform(3.4, 9.5), RNG)
    # Painted banners break up the long retaining wall.
    for i, bx in enumerate(range(-300, 301, 74)):
        mat = ('flag_red', 'cream', 'roof_teal', 'canvas_red')[i % 4]
        b.panel((bx - 3.0, 278.2, 21.5), (bx + 3.0, 278.2, 21.5),
                (bx + 2.4, 278.2, 12.5), (bx - 2.4, 278.2, 12.5), mat, thick=0.04)
        b.beam((bx - 3.2, 278.1, 21.6), (bx + 3.2, 278.1, 21.6), 0.12, 'wood_dark')
    # A planted string course halfway up breaks the 25 m wall into two tiers.
    for x0, x1 in ((-322, -252), (-224, -26), (26, 224), (262, 342)):
        b.box(((x0 + x1) / 2, 278.95, 17.5), (x1 - x0, 1.35, 0.55), 'stone_light')
        for x in range(int(x0) + 12, int(x1), 24):
            b.box((x, 278.70, 18.2), (2.8, 1.1, 0.85), 'stone')
            bush(b, x, 278.70, 18.55, 0.0, 0.62, RNG)
    # Grand stair from the quay to the terrace, its cheeks closing on the retaining wall's (12.6 m).
    terrace_stair(b, *TERRACE_STAIRS[0], cheek=TERRACE_CHEEKS[TERRACE_STAIRS[0][0]])
    # The retaining wall closes on the stair's cheeks: the gap beside the flights showed the raw cliff as flat beige
    # planes, a box trench in the note 7 view. Ashlar cheeks with courses, a coping and greenery match the wall.
    for side in (-1, 1):
        x0, x1 = sorted((side * 12.6, side * 26.0))
        b.box(((x0 + x1) / 2, 281, wall_mid), (x1 - x0, 3.0, wall_h), 'stone')
        b.box(((x0 + x1) / 2, 279.7, L.UPPER_Z + 0.15), (x1 - x0 + 1.0, 4.6, 0.5), 'stone_light')
        for zz in range(7, 29, 4):
            b.box(((x0 + x1) / 2, 279.42, zz), (x1 - x0, 0.36, 0.20), 'stone_light')
        b.box((side * 13.4, 279.2, wall_mid - 0.5), (1.6, 1.6, wall_h - 1.0), 'stone_light')
        for k in range(3):
            vine(b, side * (16.0 + k * 3.6), 279.0, L.UPPER_Z - 0.2, RNG.uniform(5.0, 12.0), RNG)
        bush(b, side * 19.0, 278.4, L.QUAY_Z, 0.0, 1.1, RNG)
    for x, width in TERRACE_STAIRS[1:]:
        terrace_stair(b, x, width, cheek=TERRACE_CHEEKS[x])
    # Upper buildings.
    for spec in L.DENSE_LOTS:
        if spec[2] >= 280:
            if spec[0].startswith(('slope-', 'ridge-')):
                b.box((spec[1], spec[2], spec[3] - 2.1), (spec[4] + 1.0, spec[5] + 1.0, 4.2),
                      'stone', spec[9])
            if spec[0].startswith('slope-') and sum(map(ord, spec[0])) % 3 == 0:
                lx, ly = local(spec[1], spec[2], spec[9], -spec[4] / 2 - 0.7, spec[5] * 0.22)
                for dz in (0.0, 1.0):
                    b.beam((lx + dz, ly, spec[3]), (lx + dz, ly, spec[3] + 5.2), 0.10, 'wood_dark')
                for r in range(6):
                    b.beam((lx, ly, spec[3] + 0.8 + r * 0.75), (lx + 1.0, ly, spec[3] + 0.8 + r * 0.75),
                           0.06, 'wood')
            if spec[8] == 'shack':
                spec = (*spec[:3], L.ground(spec[1], spec[2]) + 0.1, *spec[4:])
            for sub in split_lot(spec, RNG):
                building(b, sub, RNG)
    # The stilted hamlet perched on the upper slope. Long foundations and
    # posts keep every hut grounded on the uneven ridge.
    for spec in L.HILLSIDE_BUILDINGS:
        key, x, y, _, w, d, h, floors, style, yaw, roof = spec
        z = L.ground(x, y) + 0.4
        b.box((x, y, z - 3.8), (w + 4.0, d + 4.0, 7.6), 'stone', yaw)
        for side in (-1, 1):
            px, py = local(x, y, yaw, side * (w * 0.34), 0)
            b.cylinder((px, py, z - 8.0), (px, py, z - 1.0), 0.38, 'wood_dark', 6)
        building(b, (key, x, y, z, w, d, h, floors, style, yaw, roof), RNG)
    # A cistern and a laundry line on the terrace.
    cx, cy = -24, 360
    b.cylinder((cx, cy, L.UPPER_Z), (cx, cy, L.UPPER_Z + 2.6), 2.8, 'stone', 12)
    b.cylinder((cx, cy, L.UPPER_Z + 2.5), (cx, cy, L.UPPER_Z + 2.65), 3.0, 'stone_light', 12)
    for i in range(3):
        b.rope((cx - 7, cy + 4 + i * 0.4, L.UPPER_Z + 4.5), (cx - 1, cy + 4 + i * 0.4, L.UPPER_Z + 4.5), 0.3, 0.03)
        b.panel((cx - 6, cy + 4 + i * 0.4, L.UPPER_Z + 4.45), (cx - 4.3, cy + 4 + i * 0.4, L.UPPER_Z + 4.45),
                (cx - 4.3, cy + 4 + i * 0.4, L.UPPER_Z + 2.9), (cx - 6, cy + 4 + i * 0.4, L.UPPER_Z + 2.9),
                ('cream', 'flag_red', 'roof_teal')[i], thick=0.04)
    # Foreground pots and a laundry line frame the terrace view.
    for x, y in ((-14, 310), (14, 310), (-34, 306), (34, 306)):
        b.cylinder((x, y, L.UPPER_Z + 0.1), (x, y, L.UPPER_Z + 1.1), 0.9, 'clay', 8, radius_b=0.7)
        palm(b, x, y, L.UPPER_Z + 1.0, 0, 0.36, RNG)
    b.rope((-36, 314, L.UPPER_Z + 4.8), (36, 314, L.UPPER_Z + 4.8), 0.5, 0.04)
    for i in range(4):
        x = -24 + i * 16
        b.panel((x, 314, L.UPPER_Z + 4.7), (x + 6, 314, L.UPPER_Z + 4.7),
                (x + 6, 314, L.UPPER_Z + 2.7), (x, 314, L.UPPER_Z + 2.7),
                ('canvas', 'canvas_red', 'canvas_teal', 'canvas')[i], thick=0.04)
    # A switchback stair climbs from the terrace to the ridge hamlet's shelf.
    LM.hill_stair(b)
    # Bunting, pots and seating make the upper lane read as a street.
    for y in (306, 342, 378):
        pennants(b, (-240, y, L.UPPER_Z + 5.2), (240, y, L.UPPER_Z + 5.2), 1.2, 21)
    for x, y in ((-120, 300), (120, 300), (-200, 336), (200, 336), (-90, 374), (90, 374)):
        potted_plant(b, x, y, L.ground(x, y) + 0.05, 0.75, RNG)
    for x in (-180, -60, 60, 180):
        bench(b, x, 296, L.ground(x, 296) + 0.1, 180)
    return b
