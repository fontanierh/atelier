"""One Brinecove constructor or shared geometry primitive; no sibling generation."""
from brinecove.kit import local
from brinecove.procedural.hero_presence import HAS_FIGUREHEAD
from brinecove.procedural.hero_presence import HAS_HULL
from brinecove.procedural.hero_presence import HAS_WHEEL
from brinecove.procedural.hero_presence import HULL
from brinecove.procedural.random_state import TAU
import math


def ship(b, x, y, z, yaw, scale=1.0, sails=True, unfinished=False, canvas='sail_dark'):
    """A three-masted galleon with a lofted hull, gun deck and layered rigging.

    Local +Y is the bow.  The hull stations carry width, keel and gunwale
    height; four shell bands give the tumblehome and wale that the blockout
    lacked.
    """
    def T(lx, ly, lz):
        return local(x, y, yaw, lx * scale, ly * scale) + (z + lz * scale,)

    def box(lx, ly, lz, sx, sy, sz, mat, rot=0.0):
        b.box(T(lx, ly, lz), (sx * scale, sy * scale, sz * scale), mat, yaw + rot)

    stations = [
        (-32.0, 2.2, 3.6, 7.4), (-29.0, 4.4, 2.5, 8.1), (-25.0, 6.2, 1.7, 8.7),
        (-18.0, 7.4, 1.0, 9.0), (-8.0, 8.0, 0.6, 9.1), (2.0, 8.0, 0.5, 9.1),
        (12.0, 7.4, 0.9, 8.9), (20.0, 6.0, 1.7, 8.5), (26.0, 4.0, 2.9, 7.8),
        (30.0, 1.2, 4.6, 6.8),
    ]
    if not (HAS_HULL and not unfinished):
        # Hull shell in four horizontal bands.  The upper bands pull inward for
        # tumblehome; the wale is a darker band with a proud rubbing strake.
        bands = ((0.24, 0.72, 0.0, 2.5, 'wood_dark'), (0.72, 1.0, 2.5, 4.7, 'hull'),
                 (1.0, 0.94, 4.7, 6.6, 'hull'), (0.94, 0.82, 6.6, 8.6, 'wood_light'))
        for i in range(len(stations) - 1):
            y0, w0, k0, g0 = stations[i]
            y1, w1, k1, g1 = stations[i + 1]
            for side in (-1, 1):
                for fa, fb, za, zb, mat in bands:
                    zz0 = k0 + (g0 - k0) * za / 8.6 if za else k0
                    zz1 = k1 + (g1 - k1) * za / 8.6 if za else k1
                    a = T(side * w0 * fa, y0, zz0)
                    bb = T(side * w1 * fa, y1, zz1)
                    c = T(side * w1 * fb, y1, k1 + (g1 - k1) * zb / 8.6)
                    d = T(side * w0 * fb, y0, k0 + (g0 - k0) * zb / 8.6)
                    b.quad(a, bb, c, d, mat)
                # Proud wale and a row of iron nail heads.
                b.beam(T(side * w0 * 1.01, y0, 4.8), T(side * w1 * 1.01, y1, 4.8), 0.20, 'wood_dark')
                b.beam(T(side * w0 * 0.96, y0, 6.55), T(side * w1 * 0.96, y1, 6.55), 0.10, 'metal')
                # Gun ports and cannon muzzles on the lower gun deck.
                for yy in (y0 + 2.0, y0 + 7.0):
                    if yy < y1:
                        px, py = local(x, y, yaw, side * (w0 + 0.1) * scale, yy * scale)
                        slot = py + 0.0
                        b.box((px, slot, z + 5.7 * scale), (0.35 * scale, 1.4 * scale, 0.9 * scale), 'glass', yaw)
                        b.cylinder((px, slot, z + 5.7 * scale),
                                   T(side * (w0 + 1.5), yy, 5.7), 0.20 * scale, 'metal', 7)
        # Deck planking, keel and deck beams.
        for i in range(len(stations) - 1):
            y0, w0, _, _ = stations[i]
            y1, w1, _, _ = stations[i + 1]
            b.quad(T(-w0 * 0.94, y0, 4.7), T(w0 * 0.94, y0, 4.7),
                   T(w1 * 0.94, y1, 4.7), T(-w1 * 0.94, y1, 4.7), 'deck_planks')
            b.beam(T(-w0 * 0.92, y0, 4.55), T(w0 * 0.92, y0, 4.55), 0.16, 'wood_dark')
        b.beam(T(0, -32, 1.1), T(0, 30, 1.1), 0.7, 'wood_dark')
        # Transom, stern galleries and the raised cabin.
        b.quad(T(-2.3, -32.1, 4.4), T(2.3, -32.1, 4.4), T(2.7, -32.1, 8.7), T(-2.7, -32.1, 8.7), 'wood')
        for side in (-1, 1):
            b.box(T(side * 2.5, -32.4, 9.3), (0.32, 0.32, 0.52), 'lantern')
            b.beam(T(side * 2.5, -32.4, 9.56), T(side * 2.5, -32.4, 9.9), 0.03, 'metal')
        box(0, -24.0, 7.0, 11.0, 12.0, 3.2, 'wood')
        box(0, -24.0, 9.0, 12.0, 13.0, 0.35, 'wood_dark')
        for side in (-1, 1):
            for yy in (-29.0, -26.0, -23.0, -20.0, -17.0):
                box(side * 5.1, yy, 7.8, 0.18, 1.15, 1.25, 'glass_warm')
                box(side * 5.2, yy, 6.65, 0.22, 1.4, 0.16, 'gold')
            # Stern gallery rail and brackets.
            b.beam(T(side * 5.4, -30.0, 9.25), T(side * 5.4, -15.0, 9.25), 0.12, 'wood_dark')
            for yy in (-29, -25, -21, -17):
                b.beam(T(side * 5.4, yy, 8.9), T(side * 5.4, yy, 10.1), 0.10, 'wood')
        # Forecastle deck and its rail.
        box(0, 22.0, 6.65, 10.0, 9.0, 3.2, 'wood')
        box(0, 22.0, 8.15, 10.2, 9.2, 0.25, 'wood_dark')
        for side in (-1, 1):
            for yy in (18, 21, 24, 27):
                b.beam(T(side * 4.8, yy, 8.2), T(side * 4.8, yy, 9.25), 0.10, 'wood')
            b.beam(T(side * 4.8, 18.0, 9.2), T(side * 4.8, 27.0, 9.2), 0.13, 'wood_dark')
        # Bowsprit, stem and a carved figurehead block (a TRELLIS figurehead is
        # loaded over this when the asset is present).
        b.beam(T(0, 29, 7.6), T(0, 44, 12.4), 0.38, 'wood_dark')
        b.beam(T(0, 29, 7.6), T(0, 39, 9.6), 0.18, 'metal')
        if not HAS_FIGUREHEAD:
            b.sphere(T(0, 43.2, 11.8), 1.05, 'gold', (0.75, 1.4, 0.8), subdiv=0)
            b.sphere(T(0, 45.0, 12.6), 0.55, 'gold', (0.7, 1.1, 0.7), subdiv=0)
        # Deck furniture: hatch, capstan, ship's boat and a wheel.
        box(0, 6.0, 5.0, 6.0, 5.0, 0.35, 'wood_dark')
        box(0, 6.0, 5.2, 5.2, 4.2, 0.25, 'wood_light')
        b.cylinder(T(0, 12, 4.8), T(0, 12, 6.4), 0.85, 'wood', 10, radius_b=0.65)
        b.beam(T(-2.2, 12, 5.9), T(2.2, 12, 5.9), 0.16, 'wood_dark')
        b.beam(T(0, 9.8, 5.9), T(0, 14.2, 5.9), 0.16, 'wood_dark')
        box(0, -10.0, 5.15, 4.8, 7.2, 0.6, 'wood_light')
        if not HAS_WHEEL:
            b.ring(T(0, -16.5, 6.3), 1.05, 0.10, 'wood', axis='x', sides=12)
            for i in range(8):
                a = i * TAU / 8
                b.beam(T(0, -16.5, 6.3), T(math.cos(a) * 1.1, -16.5, 6.3 + math.sin(a) * 1.1), 0.06, 'wood')
        # Fenders and a pair of anchors stowed at the bow.
        for yy in (-18, -2, 14):
            b.cylinder(T(8.1, yy, 5.4), T(8.1, yy, 8.2), 0.34, 'rope', 7)
        for side in (-1, 1):
            b.ring(T(side * 3.4, 26.0, 5.8), 0.8, 0.12, 'metal', axis='x', sides=10)
    if unfinished:
        # Exposed ribs and staging make the shipyard hull read as work in progress.
        for y0, w0, k0, g0 in stations:
            for side in (-1, 1):
                b.beam(T(side * w0 * 0.35, y0, k0), T(side * w0, y0, g0), 0.22, 'wood_dark')
        for yy in (-24, -16, -8, 0, 8, 16, 24):
            for side in (-1, 1):
                b.beam(T(side * 8.6, yy, 0), T(side * 8.6, yy, 9.6), 0.16, 'wood_light')
        b.beam(T(-10, 24, 8.6), T(10, 24, 8.6), 0.18, 'wood_dark')
        return
    # Masts, tops, yards, layered sails and standing rigging.  On the Tripo hull the rig stands on its waist deck
    # (keel a draft below the sea, as hero_assets seats it) and on its mast stumps, a little taller for the bigger hull.
    deck, masts = 4.7, [(-15.0, 21.0, 0.62), (3.0, 30.0, 1.0), (18.0, 24.0, 0.74)]
    if HULL:
        deck = HULL['deck_z'] - 0.24 * HULL['top_z'] - 0.3
        masts = [(my, mh * 1.12, strength) for my, (_, mh, strength) in zip(HULL['masts'], masts)]
    rise = deck - 4.7
    if HULL:
        # Bowsprit for the forestays.
        b.cylinder(T(0, 26.0, deck + 1.5), T(0, 44.0, 12.4 + rise), 0.42, 'wood_dark', 8, radius_b=0.2)
    for my, mh, strength in masts:
        b.cylinder(T(0, my, deck), T(0, my, deck + mh), 0.50 * strength, 'wood_dark', 8,
                   radius_b=0.24 * strength)
        # Mast top and crosstrees.
        b.cylinder(T(0, my, deck + mh * 0.58), T(0, my, deck + mh * 0.61), 1.7 * strength,
                   'wood', 10, radius_b=1.4 * strength)
        b.beam(T(-2.4 * strength, my, deck + mh * 0.605), T(2.4 * strength, my, deck + mh * 0.605),
               0.16, 'wood_dark')
        if my == masts[1][0]:
            # Crow's nest on the mainmast.
            b.cylinder(T(0, my, deck + mh * 0.86), T(0, my, deck + mh * 0.89), 1.55, 'wood', 10)
            for i in range(10):
                a = i * TAU / 10
                b.beam(T(math.cos(a) * 1.5, my + math.sin(a) * 1.5, deck + mh * 0.89),
                       T(math.cos(a) * 1.5, my + math.sin(a) * 1.5, deck + mh * 0.89 + 0.8), 0.07, 'wood_dark')
        for frac, width in ((0.34, 11.5), (0.55, 9.8), (0.76, 7.2)):
            zz = deck + mh * frac
            yard_w = width * strength
            b.beam(T(-yard_w, my, zz), T(yard_w, my, zz), 0.24, 'wood')
            b.beam(T(-yard_w * 0.96, my + 0.12, zz), T(-yard_w * 0.96, my + 0.12, zz - 0.4), 0.08, 'wood_dark')
            b.beam(T(yard_w * 0.96, my + 0.12, zz), T(yard_w * 0.96, my + 0.12, zz - 0.4), 0.08, 'wood_dark')
            if sails and frac > 0.3:
                # One square sail per yard, bellied forward by the wind and narrowing a little at the foot.
                cols, rows = 6, 4
                grid = []
                for r in range(rows + 1):
                    v = r / rows
                    row = []
                    for c in range(cols + 1):
                        u = c / cols
                        half = yard_w * (0.97 - 0.08 * v)
                        belly = 2.2 * math.sin(math.pi * u) * math.sin(math.pi * (0.15 + 0.8 * v)) * strength
                        row.append(T(-half + 2 * half * u, my + 0.25 + belly + 1.0 * v, zz - 0.15 - 4.7 * v))
                    grid.append(row)
                for r in range(rows):
                    for c in range(cols):
                        b.quad(grid[r][c], grid[r][c + 1], grid[r + 1][c + 1], grid[r + 1][c], canvas)
                # Bolt-rope along the foot.
                for c in range(cols):
                    b.beam(grid[rows][c], grid[rows][c + 1], 0.06, 'rope')
                # Reef points across the sail foot.
                for j in range(6):
                    xx = -yard_w + 2 * yard_w * (j + 0.5) / 6
                    b.beam(T(xx, my + 1.0, zz - 3.4), T(xx, my + 1.25, zz - 4.5), 0.025, 'wood_dark')
        # Standing rigging to the bowsprit, stern and channels.
        top = deck + mh * 0.82
        b.rope(T(0, my, top), T(0, 44, 12.4 + rise), 0.0, 0.035)
        b.rope(T(0, my, top), T(0, -30, 8.5 + rise), 0.0, 0.035)
        for side in (-1, 1):
            b.rope(T(0, my, top), T(side * 8.6, my - 10.0, 7.0 + rise), 0.15, 0.03)
            b.rope(T(0, my, top), T(side * 8.6, my + 8.0, 7.0 + rise), 0.15, 0.03)
            # Shrouds and ratlines.
            for k in range(5):
                x0 = side * (3.0 + k * 1.25)
                b.rope(T(x0, my - 2.0, top - 0.5), T(x0, my - 4.8, 8.6 + rise), 0.0, 0.025)
                for r in range(6):
                    t = r / 6
                    z0 = top - 0.5 + (8.6 + rise - (top - 0.5)) * t
                    yy = my - 2.0 - 2.8 * t
                    b.beam(T(x0 - 0.6, yy, z0), T(x0 + 0.6, yy, z0), 0.018, 'rope')
    # A long pennant and a black stern flag with a pale skull, its staff above the stern castle.
    stern = HULL['top_z'] * 0.76 - 0.3 - 9.4 if HULL else 0.0
    for my, mh, _ in masts:
        b.cylinder(T(0, my, deck + mh), T(0, my, deck + mh + 1.4), 0.07, 'metal', 5)
        b.quad(T(0, my, deck + mh + 1.3), T(4.6, my, deck + mh + 0.7),
               T(4.6, my, deck + mh + 0.25), T(0, my, deck + mh + 0.55),
               'flag_black' if my == masts[1][0] else 'flag_red')
    b.cylinder(T(0, -30, 9.4 + stern), T(0, -30, 20.5 + stern), 0.13, 'metal', 6)
    b.quad(T(0, -30, 20.2 + stern), T(5.8, -30, 19.0 + stern), T(5.8, -30, 15.1 + stern), T(0, -30, 15.7 + stern), 'flag_black')
    b.sphere(T(2.7, -30.06, 17.6 + stern), 0.72, 'cream', (1.0, 0.06, 1.1), subdiv=0)
