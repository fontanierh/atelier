"""One Brinecove constructor or shared geometry primitive; no sibling generation."""
from brinecove import landmarks as LM
from brinecove import layout as L
from brinecove.geom import Builder
from brinecove.kit import barrel
from brinecove.kit import bollard
from brinecove.kit import crate
from brinecove.kit import lantern_post
from brinecove.kit import palm
from brinecove.procedural.geometry_policy import FLAT_PAVING
from brinecove.procedural.paving import paving
from brinecove.procedural.random_state import RNG
from brinecove.procedural.rowboat import rowboat
import math


def harbor():
    b = Builder('02_harbor')

    def run(half, y, z, sy, sz, mat):
        """A quay-long course from -half to half, broken where the shipyard slip cuts through the wall."""
        n0, n1 = LM.SLIP_NOTCH
        for x0, x1 in ((-half, n0), (n1, half)):
            b.box(((x0 + x1) / 2, y, z), (x1 - x0, sy, sz), mat)

    # Quay wall and its coping, seated on the wall top (it used to sit buried in the wall with its back edge proud).
    run(390, L.QUAY_Y, 0.35, 4.2, 9.4, 'stone')
    run(392, L.QUAY_Y + 1.15, 5.15, 1.9, 0.2, 'stone_light')
    # The seaward face needs a scale and rhythm of its own: a wet base,
    # horizontal courses and recessed arch-headed doors between the buttresses.
    # Everything on the face stays below the wall's top (0.35 + 9.4 / 2 = 5.05 m).
    run(390, L.QUAY_Y - 2.18, 0.75, 0.35, 1.5, 'stone_dark')
    for zz, mat in ((2.7, 'stone_light'), (3.95, 'stone')):
        run(390, L.QUAY_Y - 2.18, zz, 0.35, 0.28, mat)
    for x in range(-342, 343, 76):
        if abs(x) < 22:
            continue
        b.box((x, L.QUAY_Y - 2.28, 2.55), (8.2, 0.35, 4.5), 'stone_dark')
        b.box((x, L.QUAY_Y - 2.38, 4.6), (9.4, 0.45, 0.75), 'stone_light')
        b.box((x, L.QUAY_Y - 2.38, 2.25), (9.8, 0.45, 0.45), 'stone_light')
        b.box((x, L.QUAY_Y - 2.46, 2.25), (6.0, 0.28, 3.35), 'wood_dark')
        for dx in (-2.0, 0.0, 2.0):
            b.box((x + dx, L.QUAY_Y - 2.62, 2.25), (0.16, 0.12, 3.3), 'metal')
        # An iron mooring peg out of the face (its axis must have length).
        b.cylinder((x - 6.4, L.QUAY_Y - 2.2, 3.9), (x - 6.4, L.QUAY_Y - 2.75, 3.9), 0.18, 'metal', 8)
        # A stone arch header over the door instead of a square lintel.
        for k in range(7):
            a = math.pi * (k + 0.5) / 7
            b.box((x + math.cos(a) * 3.0, L.QUAY_Y - 2.58, 3.4 + math.sin(a) * 0.9),
                  (0.95, 0.36, 1.15), 'stone_light' if k % 2 else 'stone')
    for x in range(-390, 391, 38):
        b.box((x, L.QUAY_Y - 2.5, 0.4), (5.2, 2.4, 9.0), 'stone_light')
        b.cylinder((x, L.QUAY_Y - 3.9, 1.0), (x, L.QUAY_Y - 3.9, 1.0), 0.65, 'metal', 10)
    for x in range(-360, 361, 90):
        if x + 6 > LM.SLIP_NOTCH[0] and x - 6 < LM.SLIP_NOTCH[1]:
            continue
        b.box((x, L.QUAY_Y - 0.2, 5.2), (12, 1.2, 0.6), 'stone_dark')
    # The three piers, with piles down into the water.
    for name, px, y0, y1, width in L.PIERS:
        length = y0 - y1
        b.box((px, (y0 + y1) / 2, 4.9), (width, length, 0.7), 'wood_light')
        for yy in [y0 - 1.5 - i * 8 for i in range(int(length / 8) + 1)]:
            for side in (-1, 1):
                bx = px + side * (width / 2 - 1.0)
                b.cylinder((bx, yy, -4.5), (bx, yy, 5.0), 0.55, 'wood_dark', 7)
                b.beam((bx, yy, 0.5), (px, yy, 3.9), 0.25, 'wood_dark')
        for i in range(int(length / 9)):
            yy = y0 - 4 - i * 9
            b.box((px, yy, 5.28), (width - 0.4, 0.18, 0.08), 'wood_dark')
        # T-head on the main and east piers.
        if name in ('central', 'east'):
            tw = 40 if name == 'central' else 26
            b.box((px, y1 + 2, 4.9), (tw, 14, 0.7), 'wood_light')
            for xx in (-tw / 2 + 2, tw / 2 - 2):
                b.cylinder((px + xx, y1 - 3, -4.5), (px + xx, y1 - 3, 5.0), 0.6, 'wood_dark', 7)
        for i in range(max(2, int(length / 42))):
            yy = y0 - 14 - i * 42
            for side in (-1, 1):
                if i % 2:
                    bollard(b, px + side * (width / 2 - 1.2), yy, 5.3)
        lantern_post(b, px - width / 2 + 1.4, y1 + 3, 5.3, 3.0)
        lantern_post(b, px + width / 2 - 1.4, y0 - 16, 5.3, 3.0)
    # Quay promenade paving and steps into the water.
    # The promenade runs right up to the quay wall's back (y 62.1): a 2.9 m strip of bare ground between them
    # z-fought with the paving and showed as grass under the kerb (playtest notes 3 and 4). The wall's coping is the
    # seaward edge now.
    paving(b, -390.0, 390.0, 65.0, 107.0, z=4.745, tile=7.0, thick=0.25, kerbs=(False, False), seed=7)
    n0, n1 = LM.SLIP_NOTCH
    for x0, x1 in ((-390.0, n0), (n1, 390.0)):
        paving(b, x0, x1, L.QUAY_Y + 2.1, 65.0, z=4.745, tile=7.0, thick=0.25, kerbs=(False, False), seed=8)
        # Ground under the quay wall itself stays below the paving too: build.split clamps vertex by vertex, so a
        # ground triangle with one corner under the wall stood up past the paving edge as a grass wedge (note 3).
        FLAT_PAVING.append((x0, x1, L.QUAY_Y - 2.1, L.QUAY_Y + 2.1, 4.745 - 0.25))
    for x in (-130, 135):
        for i in range(6):
            b.box((x, L.QUAY_Y - 1.0 - i * 0.8, 4.3 - i * 0.7), (9.0, 0.9, 0.3), 'stone')
    # Palms in stone planters line the working quay, as in the harbor refs.
    for px, py in ((-330, 72), (-280, 96), (-180, 72), (-110, 96), (110, 96), (180, 72),
                   (280, 96), (330, 72), (-200, 96), (200, 96), (-300, 72), (300, 72)):
        pz = L.ground(px, py)
        b.cylinder((px, py, pz + 0.05), (px, py, pz + 1.0), 1.25, 'stone_light', 9, radius_b=0.95)
        b.cylinder((px, py, pz + 0.95), (px, py, pz + 1.08), 1.12, 'clay', 9)
        palm(b, px, py, pz + 1.05, RNG.uniform(0, 360), RNG.uniform(0.62, 0.82), RNG)
    # Fish market shed by the east pier.
    # Posts every 8 m carry eave plates and tie beams; the roof is a solid slab seated on the plates. Its single-sided
    # roof used to vanish from the street, leaving only two 36 m fascia beams floating overhead (playtest note 14).
    shed_x, shed_y = 305, 86
    for xx in range(-16, 17, 8):
        for yy in (-7, 7):
            b.beam((shed_x + xx, shed_y + yy, 5.0), (shed_x + xx, shed_y + yy, 11.0), 0.34, 'wood_dark')
            b.beam((shed_x + xx, shed_y + yy, 9.9), (shed_x + xx + (1.0 if xx < 16 else -1.0), shed_y + yy, 10.9),
                   0.16, 'wood_dark')
        b.beam((shed_x + xx, shed_y - 7, 10.8), (shed_x + xx, shed_y + 7, 10.8), 0.28, 'wood_dark')
    for yy in (-7, 7):
        b.beam((shed_x - 17, shed_y + yy, 10.85), (shed_x + 17, shed_y + yy, 10.85), 0.3, 'wood_dark')
    b.gable_roof((shed_x, shed_y, 11.0), 32, 14, 11.0, 3.0, 'roof_terra', 0, ridge='x', overhang=1.0)
    b.box((shed_x, shed_y - 2.0, 5.7), (30, 2.0, 1.2), 'wood_light')
    for i in range(6):
        b.box((shed_x - 12 + i * 4.8, shed_y - 2.3, 6.5), (2.2, 1.0, 0.5), 'sail_stripe' if i % 2 else 'cream')
    # Cargo cranes: a timber A-frame, jib, rope and a hanging crate.
    for cx, cy, ang in ((-334, 84, -22), (412, 128, 16)):
        b.beam((cx - 4, cy, 4.7), (cx, cy, 18.0), 0.5, 'wood_dark')
        b.beam((cx + 4, cy, 4.7), (cx, cy, 18.0), 0.5, 'wood_dark')
        b.beam((cx, cy, 15.0), (cx + math.cos(math.radians(ang)) * 16, cy + math.sin(math.radians(ang)) * 16, 17.5), 0.35, 'wood')
        b.rope((cx, cy, 17.0), (cx + math.cos(math.radians(ang)) * 14, cy + math.sin(math.radians(ang)) * 14, 9.5), 0.0, 0.06)
        crate(b, cx + math.cos(math.radians(ang)) * 14, cy + math.sin(math.radians(ang)) * 14, 7.8, 1.4)
    # Shipyard: the half-built hull on its cradle, the slip running into the sea, scaffold, crane and shed.
    LM.shipyard(b)
    for i in range(8):
        crate(b, 400 + RNG.uniform(-3, 3), 112 + i * 4.8, 4.7, RNG.uniform(0.8, 1.4), RNG.uniform(0, 90))
    for i in range(2):
        b.cylinder((408, 95 + i * 5, 4.7), (408, 95 + i * 5, 4.9), 2.4, 'wood_light', 10)
    # Cargo clusters along the working piers.
    for name, px, y0, y1, width in L.PIERS:
        for t, off in ((0.22, -4.2), (0.52, 3.4), (0.78, -2.6)):
            py = y0 + (y1 - y0) * t
            crate(b, px + off, py, 5.3, 0.9, RNG.uniform(0, 90))
            barrel(b, px + off + 1.5, py + 0.9, 5.3, 0.85)
            if t > 0.5:
                b.ring((px + off - 1.2, py - 1.0, 5.32), 0.55, 0.07, 'rope', sides=10)
    # Small boats give the open water scale and life.
    for x, y, yaw in ((-225, -40, -22), (-150, -90, -14), (-30, -150, 8), (100, -70, 35),
                      (180, -160, -8), (300, -60, 18), (-380, -40, -22), (420, -120, 12)):
        if L.is_water(x, y):
            rowboat(b, x, y, 0.0, yaw, 1.0)
    return b
