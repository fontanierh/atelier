"""One Brinecove constructor or shared geometry primitive; no sibling generation."""
from brinecove import landmarks as LM
from brinecove import layout as L
from brinecove.geom import Builder
from brinecove.kit import barrel
from brinecove.kit import crate
from brinecove.kit import lantern_post
from brinecove.kit import palm
from brinecove.procedural.random_state import RNG
from brinecove.procedural.rowboat import rowboat


def props():
    b = Builder('08_props')
    # Quay and street furniture.
    for x in range(-360, 361, 44):
        if abs(x) < 16:
            continue
        lantern_post(b, x, 103, 4.7, 3.4)
    for x in (-320, -270, -210, 150, 205, 270, 320):
        for y in (146, 184):
            barrel(b, x + RNG.uniform(-1.5, 1.5), y + RNG.uniform(-1, 1), 4.7, RNG.uniform(0.8, 1.1))
        crate(b, x + RNG.uniform(-2, 2), 176 + RNG.uniform(-1, 1), 4.7, RNG.uniform(0.7, 1.2), RNG.uniform(0, 90))
    for x in range(-300, 321, 40):
        lantern_post(b, x, 326, L.UPPER_Z, 3.4)
    for x in (-250, -190, 70, 130, 190, 250):
        barrel(b, x, 370, L.UPPER_Z, 0.9)
        crate(b, x + 3, 366, L.UPPER_Z, 0.8, 12)
    # Pier clutter and fenders.
    for _, px, y0, y1, width in L.PIERS:
        for yy in (y0 - 24, y1 + 18):
            barrel(b, px + width * 0.25, yy, 5.25, 0.9)
            crate(b, px - width * 0.25, yy - 3, 5.25, 1.0, 20)
    # Buoys, rowboats and fish baskets in the water.
    for x, y, z, yaw, scale in [(-155, -205, 0.0, 20, 1.0), (145, -228, 0.0, -14, 0.9),
                                 (-270, -145, 0.0, 65, 0.8), (270, -182, 0.0, -70, 0.9)]:
        rowboat(b, x, y, 0.0, yaw, scale)
    for x, y in [(-200, -160), (190, -190), (-90, -210)]:
        b.sphere((x, y, 0.45), 0.7, 'flag_red', (1.0, 1.0, 1.0), subdiv=1)
        b.cylinder((x, y, 0.2), (x, y, 1.6), 0.12, 'metal', 6)
    # Fish baskets and nets near the market shed.
    for i in range(7):
        bx = 290 + i * 4.2
        b.cylinder((bx, 78, 4.8), (bx, 78, 5.35), 1.0, 'wood_light', 9)
        b.sphere((bx, 78, 5.4), 0.5, 'sail', (1.3, 0.6, 0.5), subdiv=0)
    for i in range(3):
        b.ring((330 + i * 3, 70, 4.9), 1.6, 0.08, 'rope', sides=12)
    # Cargo clusters, rope coils and net racks along the working quay.
    for cx, cy in ((-250, 94), (-170, 94), (120, 94), (270, 94), (-60, 84), (60, 84)):
        for i in range(2):
            crate(b, cx + i * 1.25, cy, 4.75, RNG.uniform(0.9, 1.3), RNG.uniform(-8, 8))
            barrel(b, cx - 1.8 - i * 1.1, cy + 1.4, 4.75, RNG.uniform(0.7, 1.0))
        b.ring((cx, cy + 3.0, 4.82), 0.85, 0.07, 'rope', sides=12)
    for x, y in ((274, 70), (286, 70)):
        for side in (-1, 1):
            b.beam((x, y + side * 3.2, 4.8), (x, y + side * 3.2, 9.2), 0.16, 'wood_dark')
        for i in range(6):
            yy = y - 3.0 + i * 1.2
            b.rope((x - 0.2, yy, 8.8), (x + 0.2, yy, 5.4), 0.35, 0.035)
            b.panel((x - 1.4, yy - 0.5, 8.7), (x + 1.4, yy - 0.5, 8.7),
                    (x + 1.6, yy + 0.5, 5.6), (x - 1.6, yy + 0.5, 5.6), 'rope', thick=0.04)
    # Two big cannon on the quay aimed at the harbor mouth, at the old hero model's landmark size (the TRELLIS hero
    # cannon imported as broken triangles).
    for x, y, yaw in ((-206, 88.0, 18), (210, 88.0, -14)):
        LM.cannon(b, x, y, max(L.ground(x, y), LM.QUAY_TOP), yaw, 2.5)
    # The quay anchor is procedural too (the TRELLIS one imported with scrambled triangles: playtest note 13).
    LM.anchor(b, -292, 90, max(L.ground(-292, 90), LM.QUAY_TOP), 28)
    # Gulls over the harbor mouth.
    for i in range(18):
        gx = RNG.uniform(-320, 320)
        gy = RNG.uniform(-300, 40)
        gz = RNG.uniform(20, 58)
        b.sphere((gx, gy, gz), 0.22, 'sail', (1.0, 0.6, 0.5), subdiv=0)
        b.quad((gx - 1.1, gy, gz), (gx, gy, gz + 0.35), (gx + 1.1, gy, gz), (gx, gy, gz - 0.1), 'sail')
    # Potted palms on the upper terrace and by tavern doors.
    for x, y in [(-300, 300), (-170, 300), (120, 300), (280, 300), (-40, 236), (45, 236)]:
        b.cylinder((x, y, L.ground(x, y) + 0.3), (x, y, L.ground(x, y) + 1.2), 1.0, 'clay' if 'clay' in L.COLORS else 'coral', 8, radius_b=0.8)
        palm(b, x, y, L.ground(x, y) + 1.1, 0, 0.38, RNG)
    return b
