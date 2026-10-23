"""One Brinecove constructor or shared geometry primitive; no sibling generation."""
from brinecove import landmarks as LM
from brinecove import layout as L
from brinecove.kit import bush
from brinecove.kit import door
from brinecove.kit import lantern_post
from brinecove.kit import palm
from brinecove.kit import window
from brinecove.procedural.random_state import RNG
from brinecove.procedural.random_state import TAU
from brinecove.procedural.rock_cluster import rock_cluster
import math


def lighthouse(b):
    x, y, _ = L.LIGHTHOUSE
    z = L.ground(x, y) + 0.4
    # Broad rock plinth, then a tall tapered tower with three broad red bands.
    b.cylinder((x, y, z - 1.5), (x, y, z + 2.0), 7.2, 'stone', 14, radius_b=5.4)
    b.cylinder((x, y, z + 1.9), (x, y, z + 2.35), 6.8, 'stone_light', 14)
    z0 = z + 2.2
    bands = 11
    for i in range(bands):
        r0 = 4.35 - i * 0.13
        r1 = 4.35 - (i + 1) * 0.13
        mat = 'flag_red' if i in (1, 2, 6, 7, 10) else 'cream'
        b.cylinder((x, y, z0 + i * 2.55), (x, y, z0 + (i + 1) * 2.55), r0, mat, 14, radius_b=r1)
    # Gallery and railing.
    zz = z0 + bands * 2.55
    b.cylinder((x, y, zz), (x, y, zz + 0.55), 3.1, 'stone_dark', 14, radius_b=3.0)
    for i in range(14):
        a = i * TAU / 14
        px, py = x + math.cos(a) * 3.3, y + math.sin(a) * 3.3
        b.beam((px, py, zz + 0.5), (px, py, zz + 2.25), 0.10, 'metal')
    b.ring((x, y, zz + 2.15), 3.3, 0.10, 'metal', sides=16)
    b.ring((x, y, zz + 1.1), 3.3, 0.06, 'metal', sides=16)
    # Lantern room, glazing bars, dome and lightning rod.
    b.cylinder((x, y, zz + 0.55), (x, y, zz + 3.6), 2.35, 'glass_warm', 12)
    for i in range(8):
        a = i * TAU / 8
        px, py = x + math.cos(a) * 2.34, y + math.sin(a) * 2.34
        b.beam((px, py, zz + 0.6), (px, py, zz + 3.55), 0.08, 'metal')
    b.cylinder((x, y, zz + 3.55), (x, y, zz + 4.1), 2.75, 'metal', 12, radius_b=2.35)
    b.cylinder((x, y, zz + 4.05), (x, y, zz + 5.25), 2.55, 'roof_teal', 12, radius_b=0.15)
    b.cylinder((x, y, zz + 5.2), (x, y, zz + 6.1), 0.10, 'metal', 6)
    b.sphere((x, y, zz + 6.2), 0.35, 'gold', subdiv=0)
    # Door, small windows and the keeper's cottage at the foot.
    b.box((x, y - 4.35, z + 4.1), (1.9, 0.5, 3.6), 'wood_dark')
    for f in (0.35, 0.62):
        b.box((x - 4.2, y, z + 2.2 + f * 20), (0.25, 1.1, 1.4), 'glass_warm', 90)
    kx, ky = x + 24, y + 12
    kz = L.ground(kx, ky) + 0.2
    b.box((kx, ky, kz + 2.2), (17, 12, 4.4), 'cream')
    b.gable_roof((kx, ky, kz + 4.4), 17, 12, kz + 4.4, 3.8, 'roof_terra', 0, ridge='x')
    window(b, kx, ky, 0, -4.4, -6.05, kz + 1.5, 1.25, 1.55, True, True)
    window(b, kx, ky, 0, 4.2, -6.05, kz + 1.5, 1.25, 1.55, True, True)
    door(b, kx, ky, 0, 0, -6.05, kz, 1.5, 2.3)
    b.box((kx + 5.5, ky + 2.5, kz + 6.4), (1.1, 1.1, 3.4), 'stone')
    b.box((kx + 5.5, ky + 2.5, kz + 8.2), (1.4, 1.4, 0.3), 'stone_dark')
    lantern_post(b, kx - 10, ky - 8, kz, 3.2)
    # A low signal wall and a pair of cannon on the seaward edge, run out through gaps in it.
    for i in range(10):
        px = x - 18 + i * 4.2
        if i in (3, 6):
            b.box((px, y - 15.0, z + 0.3), (4.2, 1.2, 0.6), 'stone')
            LM.cannon(b, px, y - 12.6, L.ground(px, y - 12.6), 0.0, 1.8)
            continue
        b.box((px, y - 15.0, z + 1.0), (4.2, 1.2, 2.0), 'stone')
    # A lived-in headland: a stone path links cottage and tower, a rope fence
    # follows the cliff edge, and garden beds and palms break up the lawn.
    for i in range(22):
        t = i / 21
        px = x + 24 * t
        py = y + 12 * t
        pz = L.ground(px, py) + 0.10
        b.box((px, py, pz), (2.3, 2.3, 0.18),
              'stone_light' if i % 4 else 'sand', 0)
    for i in range(13):
        px = x - 30 + i * 5.0
        py = y - 27.0
        pz = L.ground(px, py)
        b.beam((px, py, pz), (px, py, pz + 2.3), 0.16, 'wood_dark')
        if i < 12:
            qx = px + 5.0
            qz = L.ground(qx, py)
            b.beam((px, py, pz + 1.8), (qx, py, qz + 1.8), 0.07, 'rope')
            b.beam((px, py, pz + 0.9), (qx, py, qz + 0.9), 0.05, 'rope')
    for side, off in ((-1, -18), (1, 18)):
        gx, gy = x + off, y + 2
        gz = L.ground(gx, gy)
        b.box((gx, gy, gz + 0.35), (7.5, 3.2, 0.7), 'stone')
        for i in range(4):
            bush(b, gx - 2.6 + i * 1.8, gy, gz + 0.7, 0.0, 0.55, RNG)
    for i in range(16):
        rx = x - 38 + RNG.uniform(0, 76)
        ry = y - 34 + RNG.uniform(-5, 2)
        rock_cluster(b, rx, ry, L.height(rx, ry) - 0.8, RNG.uniform(1.4, 3.2), 2)
    for px, py, scale in ((-30, -8, 1.0), (34, 16, 0.82), (18, -20, 0.7)):
        palm(b, x + px, y + py, L.ground(x + px, y + py), RNG.uniform(0, 360), scale, RNG)
    b.box((x + 31, y + 19, L.ground(x + 31, y + 19) + 1.1), (4.0, 3.0, 2.2), 'wood')
    b.gable_roof((x + 31, y + 19, L.ground(x + 31, y + 19) + 2.1), 4.0, 3.0,
                 L.ground(x + 31, y + 19) + 2.1, 1.4, 'roof_terra', 0, ridge='x', overhang=0.5)
