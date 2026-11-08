"""One Brinecove constructor or shared geometry primitive; no sibling generation."""
from brinecove import layout as L
from brinecove import rocks
from brinecove.geom import Builder
from brinecove.kit import barrel
from brinecove.kit import crate
from brinecove.kit import fish_crate
from brinecove.kit import goods
from brinecove.kit import jungle_tree
from brinecove.kit import lantern_post
from brinecove.kit import local
from brinecove.kit import market_stall
from brinecove.kit import palm
from brinecove.kit import parasol
from brinecove.kit import pennants
from brinecove.kit import potted_plant
from brinecove.kit import sack
from brinecove.procedural.geometry_policy import MARKET_FLOOR
from brinecove.procedural.random_state import RNG
from brinecove.procedural.random_state import TAU
import math


def market():
    b = Builder('04_market')
    x0, x1, y0, y1 = MARKET_FLOOR
    b.box(((x0 + x1) / 2, (y0 + y1) / 2, 4.68), (x1 - x0, y1 - y0, 0.28), 'cobble')
    # A flagstone border and a grid of stone ribs divide the square into the paved bays of a piazza;
    # darker setts fill a few bays so the field never reads as one flat sheet.
    for cx, cy, sx, sy in ((0, 96.5, 196, 5), (0, 223.5, 196, 5), (-95.5, 160, 5, 132), (95.5, 160, 5, 132)):
        b.box((cx, cy, 4.83), (sx, sy, 0.06), 'stone_light')
    for gx in range(-84, 85, 12):
        b.box((gx, 160, 4.83), (0.7, 122, 0.06), 'stone_light')
    for gy in range(106, 215, 12):
        b.box((0, gy, 4.83), (186, 0.7, 0.06), 'stone_light')
    for gx in range(-84, 73, 12):
        for gy in range(106, 203, 12):
            if rocks.fbm(gx, gy, 30.0, 2, 17) > 0.62:
                b.box((gx + 6, gy + 6, 4.825), (11.3, 11.3, 0.05), 'cobble_dark')
    # Lantern posts at the square's front corners (their strings ran 184 m across the square: playtest note 14).
    for xx in (-92, 92):
        lantern_post(b, xx, 96, L.ground(xx, 96) + 0.1, 5.0)
    cloths = ('canvas', 'canvas_red', 'canvas_teal', 'canvas_gold', 'canvas_blue', 'canvas_green', 'canvas_red')
    for i, (x, y, w, d, cloth) in enumerate(L.MARKET_STALLS):
        # Loosen the grid: real market rows drift, turn and leave gaps.
        x += RNG.uniform(-2.5, 2.5)
        y += RNG.uniform(-2.0, 2.0)
        yaw = RNG.uniform(-16, 16)
        canvas = cloths[RNG.randrange(len(cloths))]
        market_stall(b, x, y, L.ground(x, y) + 0.1, w, d, canvas, yaw)
        barrel(b, x - w * 0.58, y + d * 0.25, L.ground(x, y) + 0.1, 0.72)
        crate(b, x + w * 0.55, y - d * 0.18, L.ground(x, y) + 0.1, 0.8, RNG.uniform(0, 90))
    # South-edge stalls frame the market camera and close the empty cobbles.
    for x, cloth in ((-76, 'canvas_red'), (58, 'canvas_teal')):
        y = 98
        market_stall(b, x, y, L.ground(x, y) + 0.1, 13, 8, cloth, -7 if x < 0 else 8)
    for x, y, cloth in ((-96, 108, 'canvas_red'), (96, 112, 'canvas_teal')):
        b.cylinder((x, y, L.ground(x, y) + 0.1), (x, y, L.ground(x, y) + 7.5), 0.12, 'wood_dark', 6)
        b.panel((x, y, L.ground(x, y) + 7.4), (x + 4.0, y, L.ground(x, y) + 6.8),
                (x + 4.0, y, L.ground(x, y) + 4.4), (x, y, L.ground(x, y) + 5.0), cloth, thick=0.04)
    for x, y in ((-70, 105), (-30, 105), (30, 105), (70, 105)):
        barrel(b, x, y, L.ground(x, y) + 0.1, 0.8)
        crate(b, x + 2.2, y + 1.2, L.ground(x, y) + 0.1, 0.8, 12)
    # Stone colonnades frame the square after the arcade concept (references/redesign/arcade.jpg): short groups of
    # square piers, each with its own lintel, a timber pergola on posts and a striped shade per bay. One 122 m
    # lintel and plank used to run the whole side into the terrace wall (playtest note 11).
    for side in (-1, 1):
        x = side * 96
        xi = x - side * 3.4
        for g, ys in enumerate(((108, 120, 132, 144), (158, 170, 182, 194), (206, 217))):
            gz = L.ground(x, (ys[0] + ys[-1]) / 2)
            top = gz + 4.9
            for y in ys:
                pz = L.ground(x, y)
                b.box((x, y, pz + 0.25), (1.15, 1.15, 0.5), 'stone')
                b.box((x, y, (pz + 0.5 + top - 0.6) / 2), (0.78, 0.78, top - 0.6 - pz - 0.5), 'stone_light')
                b.box((x, y, top - 0.45), (1.1, 1.1, 0.3), 'stone')
                b.beam((xi, y, L.ground(xi, y)), (xi, y, top - 0.25), 0.24, 'wood_dark')
                b.box((xi, y, L.ground(xi, y) + 0.12), (0.5, 0.5, 0.24), 'stone')
            b.box((x, (ys[0] + ys[-1]) / 2, top), (1.3, ys[-1] - ys[0] + 1.6, 0.6), 'stone_light')
            b.beam((xi, ys[0] - 0.7, top - 0.2), (xi, ys[-1] + 0.7, top - 0.2), 0.26, 'wood_dark')
            n = int((ys[-1] - ys[0]) / 1.5)
            for k in range(n + 1):
                y = ys[0] + (ys[-1] - ys[0]) * k / n
                b.beam((x + side * 0.9, y, top + 0.38), (xi - side * 0.6, y, top - 0.02), 0.14, 'wood_dark', 0.2)
            for k, (y0, y1) in enumerate(zip(ys, ys[1:])):
                b.panel((x + side * 0.4, y0 + 0.4, top + 0.5), (x + side * 0.4, y1 - 0.4, top + 0.5),
                        (xi - side * 0.3, y1 - 0.4, top + 0.12), (xi - side * 0.3, y0 + 0.4, top + 0.12),
                        ('canvas', 'canvas_teal', 'canvas_red')[(g + k) % 3], thick=0.05)
    # Lantern strings and a loose crowd make the open square read as a working
    # market rather than an empty plaza from the harbor camera.
    # Each string is a short local span between two posts, never one line across the whole square.
    for yy in (118, 168, 214):
        for x0, x1 in ((-89, -68), (-10, 10), (68, 89)):
            for xx in (x0, x1):
                lantern_post(b, xx, yy, L.ground(xx, yy) + 0.1, 5.5)
            za, zc = L.ground(x0, yy) + 5.6, L.ground(x1, yy) + 5.6
            b.rope((x0, yy, za), (x1, yy, zc), 0.6, 0.05)
            for k in range(1, 4):
                t = k / 4
                b.sphere((x0 + (x1 - x0) * t, yy, za + (zc - za) * t - 0.6 * math.sin(math.pi * t) - 0.3), 0.22,
                         'lantern', subdiv=1)
                b.beam((x0 + (x1 - x0) * t, yy, za + (zc - za) * t - 0.6 * math.sin(math.pi * t)),
                       (x0 + (x1 - x0) * t, yy, za + (zc - za) * t - 0.6 * math.sin(math.pi * t) - 0.1), 0.02, 'metal')
    # Handcarts, fish baskets and sack piles fill the lanes between stalls.
    for cx, cy, cyaw in ((-66, 150, 18), (66, 152, -24), (-52, 206, 8), (54, 204, -12)):
        cz = L.ground(cx, cy) + 0.1
        b.box((cx, cy, cz + 0.75), (4.2, 2.0, 0.35), 'wood_light', cyaw)
        for side in (-1, 1):
            wx, wy = local(cx, cy, cyaw, side * 1.45, 0.35)
            b.ring((wx, wy, cz + 0.45), 0.62, 0.16, 'wood_dark', axis='x', sides=10)
            b.cylinder((wx - 0.08, wy, cz + 0.45), (wx + 0.08, wy, cz + 0.45), 0.18, 'metal', 8)
        for k in range(3):
            crate(b, cx + RNG.uniform(-1.4, 1.4), cy + RNG.uniform(-0.7, 0.7), cz + 0.4,
                  RNG.uniform(0.45, 0.7), cyaw + RNG.uniform(-20, 20))
    for fx, fy in ((-78, 120), (76, 118), (-74, 224), (74, 222)):
        fz = L.ground(fx, fy) + 0.1
        b.cylinder((fx, fy, fz), (fx, fy, fz + 0.7), 0.7, 'wood', 10, radius_b=0.55)
        for k in range(5):
            b.sphere((fx + RNG.uniform(-0.5, 0.5), fy + RNG.uniform(-0.5, 0.5), fz + 0.75),
                     RNG.uniform(0.16, 0.26), 'sail', (1.3, 0.8, 0.7), subdiv=0)
    # Parasols, shade trees and paving rings break the square into rooms, as in the paintings' crowded markets.
    pair = (('canvas', 'canvas_red'), ('canvas', 'canvas_teal'), ('canvas_gold', 'canvas'), ('canvas_blue', 'canvas'),
            ('canvas_green', 'cream'), ('canvas_red', 'canvas_gold'))
    placed = 0
    for _ in range(400):
        if placed >= 34:
            break
        px, py = RNG.uniform(-86, 86), RNG.uniform(104, 222)
        if any(abs(px - sx) < sw / 2 + 3.2 and abs(py - sy) < sd / 2 + 3.2 for sx, sy, sw, sd, _ in L.MARKET_STALLS):
            continue
        if math.hypot(px - 0, py - 158) < 9 or math.hypot(px - 47, py - 137) < 6 or math.hypot(px + 44, py - 188) < 8:
            continue
        parasol(b, px, py, L.ground(px, py) + 0.1, RNG.uniform(2.2, 3.2), pair[RNG.randrange(len(pair))], RNG)
        placed += 1
    cz = L.ground(0, 158) + 0.1
    for r, mat in ((13.0, 'stone_light'), (12.4, 'cobble_dark'), (8.0, 'stone_light')):
        b.cylinder((0, 158, cz - 0.02), (0, 158, cz + 0.06), r, mat, 32)
    for k in range(8):
        a = TAU * k / 8
        b.box((math.cos(a) * 30, 158 + math.sin(a) * 30, cz + 0.04), (60, 0.5, 0.06), 'stone_light', math.degrees(a))
    for tx, ty in ((-60, 132), (60, 132), (-60, 196), (60, 196), (-24, 160), (24, 160)):
        tz = L.ground(tx, ty)
        b.cylinder((tx, ty, tz), (tx, ty, tz + 0.55), 2.3, 'stone_light', 12)
        b.cylinder((tx, ty, tz + 0.5), (tx, ty, tz + 0.6), 2.0, 'moss', 12)
        jungle_tree(b, tx, ty, tz + 0.5, RNG.uniform(0, 360), RNG.uniform(0.75, 0.95), RNG)
    # Potted palms soften the hard market edges and frame the two entrances.
    for px, py in ((-66, 102), (66, 102), (-66, 214), (66, 214), (0, 102), (0, 212)):
        pz = L.ground(px, py)
        b.cylinder((px, py, pz + 0.1), (px, py, pz + 1.2), 1.1, 'clay', 9, radius_b=0.8)
        palm(b, px, py, pz + 1.1, RNG.uniform(0, 360), 0.62, RNG)
    # Signal mast, crossyard, rigging, bunting and a crow's nest.
    mx, my, mz = 0, 158, 4.9
    b.cylinder((mx, my, mz), (mx, my, mz + 23), 0.32, 'wood_dark', 8, radius_b=0.18)
    b.beam((mx - 6, my, mz + 18), (mx + 6, my, mz + 18), 0.28, 'wood')
    b.beam((mx, my, mz + 22.4), (mx + 9, my - 4, mz + 15.5), 0.16, 'wood')
    b.ring((mx, my, mz + 18.5), 1.2, 0.10, 'wood', axis='z', sides=10)
    for i in range(5):
        xx = -4.5 + i * 2.25
        b.panel((mx + xx, my, mz + 19.5), (mx + xx + 1.0, my, mz + 19.5),
                (mx + xx + 1.0, my, mz + 18.1), (mx + xx, my, mz + 18.1),
                ('flag_red', 'cream', 'roof_teal')[i % 3], thick=0.04)
    b.rope((mx, my, mz + 17), (mx - 18, my + 6, 9.0), 0.7, 0.05)
    b.rope((mx, my, mz + 17), (mx + 18, my - 6, 9.0), 0.7, 0.05)
    for i in range(7):
        xx = -15 + i * 5
        yy = my + 6 - (abs(xx) / 18) * 12
        b.panel((mx + xx, yy, 9.0 - (abs(xx) / 18) * 0.8), (mx + xx + 2.0, yy - 0.8, 8.8),
                (mx + xx + 2.0, yy - 0.8, 7.8), (mx + xx, yy, 8.0), ('flag_red', 'cream')[i % 2], thick=0.04)
    # Well.
    wx, wy = 47, 137
    b.cylinder((wx, wy, 4.8), (wx, wy, 6.1), 2.2, 'stone', 12)
    b.cylinder((wx, wy, 6.0), (wx, wy, 6.15), 2.35, 'water_deep', 12)
    for sx in (-1.5, 1.5):
        b.beam((wx + sx, wy, 6.0), (wx + sx, wy, 8.9), 0.16, 'wood_dark')
    b.gable_roof((wx, wy, 8.8), 4.6, 4.0, 8.8, 1.4, 'roof_terra', 0, ridge='x', overhang=0.4)
    # Auction block with steps and a small canopy.
    ax, ay = -44, 188
    b.box((ax, ay, 5.25), (8, 5, 1.0), 'wood_light')
    b.box((ax - 3.5, ay, 4.9), (2.8, 5.2, 0.4), 'stone')
    for sx in (-3.4, 3.4):
        for sy in (-2.1, 2.1):
            b.beam((ax + sx, ay + sy, 5.7), (ax + sx, ay + sy, 9.4), 0.16, 'wood_dark')
    b.gable_roof((ax, ay, 9.3), 9, 6.2, 9.3, 1.8, 'roof_teal', 0, ridge='x', overhang=0.5)
    # Benches, ropes and market clutter.
    for i in range(8):
        x = -82 + i * 23
        y = 210 if i % 2 else 106
        b.box((x, y, 5.2), (5.4, 1.1, 0.25), 'wood_light')
        for sx in (-2.2, 2.2):
            b.beam((x + sx, y, 4.4), (x + sx, y, 5.2), 0.14, 'wood_dark')
    # Bunting over the stalls and a thicker layer of working clutter.
    for y, z in ((118, 10.2), (160, 10.4), (205, 10.0)):
        pennants(b, (-88, y, z), (88, y, z), 1.1, 15)
    for x, y, yaw in ((-70, 150, 12), (-24, 208, -8), (52, 148, 18), (70, 206, -14)):
        fish_crate(b, x, y, L.ground(x, y) + 0.1, yaw, 1.1)
    for x, y in ((-58, 176), (-6, 122), (44, 190), (78, 156)):
        sack(b, x, y, L.ground(x, y) + 0.1, 1.0)
    for x, y in ((-88, 128), (88, 128), (-88, 198), (88, 198)):
        potted_plant(b, x, y, L.ground(x, y) + 0.1, 0.8, RNG)
    # Break up the open foreground of the market camera with a working cluster.
    for x, y, yaw in ((-26, 128, 8), (24, 134, -12), (-42, 120, 0), (38, 120, 20)):
        fish_crate(b, x, y, L.ground(x, y) + 0.1, yaw, 1.05)
        sack(b, x + 1.5, y + 0.7, L.ground(x, y) + 0.1, 0.9)
    potted_plant(b, 0, 124, L.ground(0, 124) + 0.1, 0.9, RNG)
    # A low line of goods and bunting fills the market camera's foreground.
    for x, y, yaw in ((-16, 120, 6), (-6, 118, -10), (6, 121, 12), (16, 119, -4)):
        fish_crate(b, x, y, L.ground(x, y) + 0.1, yaw, 1.0)
        sack(b, x + 1.2, y + 0.9, L.ground(x, y) + 0.1, 0.85)
    pennants(b, (-88, 128, 9.2), (88, 128, 9.2), 0.8, 21)
    # Fill the open cobbles with lanes of smaller stalls, as in the market painting: a bazaar, not a parade ground.
    taken = [(x, y, w / 2 + 3.5, d / 2 + 3.5) for x, y, w, d, _ in L.MARKET_STALLS]
    taken += [(0, 158, 7, 7), (47, 137, 6, 6), (-44, 188, 7, 6), (0, 126, 30, 14), (-16, 134, 10, 7)]
    lane = 0
    for gy in range(112, 220, 15):
        lane += 1
        for gx in range(-84, 86, 13):
            x = gx + RNG.uniform(-2.0, 2.0) + (6.5 if lane % 2 else 0.0)
            y = gy + RNG.uniform(-1.5, 1.5)
            w, d = RNG.uniform(6.5, 9.0), RNG.uniform(4.5, 5.8)
            if abs(x) > 86 or any(abs(x - tx) < w / 2 + hw and abs(y - ty) < d / 2 + hd for tx, ty, hw, hd in taken):
                continue
            taken.append((x, y, w / 2 + 2.5, d / 2 + 2.5))
            yaw = RNG.uniform(-6, 6)
            z = L.ground(x, y) + 0.1
            market_stall(b, x, y, z, w, d, ('canvas', 'canvas_red', 'canvas_teal', 'canvas')[RNG.randrange(4)], yaw)
            for side in (-1, 1):
                gx2, gy2 = local(x, y, yaw, side * w * 0.3, -d * 0.62)
                goods(b, gx2, gy2, z, yaw, RNG)
    # A working stall just ahead of the market camera anchors the foreground.
    market_stall(b, -16, 134, L.ground(-16, 134) + 0.1, 12, 7, 'canvas_teal', 4)
    for x, y, yaw in ((-2, 131, 8), (6, 137, -12), (-28, 133, 16)):
        fish_crate(b, x, y, L.ground(x, y) + 0.1, yaw, 1.0)
        sack(b, x + 1.3, y + 0.8, L.ground(x, y) + 0.1, 0.85)
    return b
