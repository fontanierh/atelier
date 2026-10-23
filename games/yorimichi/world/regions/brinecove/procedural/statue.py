"""One Brinecove constructor or shared geometry primitive; no sibling generation."""
from brinecove import layout as L


def statue(b):
    x, y, _ = L.STATUE
    z = 8.0
    start = len(b.verts)
    # Plinth and figure, all in one stone material so the silhouette reads from the harbor.
    b.box((x, y, z + 2.2), (11, 11, 4.4), 'stone')
    b.box((x, y, z + 4.5), (13, 13, 0.5), 'stone_light')
    base = z + 4.8
    # Boots, legs and coat.
    for side in (-1, 1):
        b.box((x + side * 1.2, y, base + 2.0), (2.0, 3.2, 4.0), 'stone')
    b.box((x, y, base + 6.8), (5.6, 3.6, 6.8), 'stone_light')
    b.sphere((x, y, base + 8.2), 1.8, 'stone', (1.8, 0.9, 2.0), subdiv=1)
    # Torso, shoulders and head.
    b.box((x, y, base + 11.4), (5.2, 3.0, 3.4), 'stone')
    b.box((x, y, base + 13.0), (7.2, 3.3, 1.3), 'stone')
    b.sphere((x, y, base + 14.4), 1.45, 'stone_light', (0.95, 0.9, 1.1), subdiv=1)
    # Tricorn hat: brim and three raised points.
    b.cylinder((x, y, base + 15.2), (x, y, base + 15.55), 2.4, 'stone_dark', 3)
    b.sphere((x, y, base + 15.9), 1.15, 'stone_dark', (1.1, 1.1, 0.55), subdiv=0)
    # Cape billowing behind.
    for i in range(3):
        b.quad((x - 2.8 + i * 2.8, y + 1.6, base + 12.8),
               (x - 2.8 + i * 2.8, y + 2.1, base + 12.8),
               (x - 4.2 + i * 3.2, y + 5.6 + i * 0.8, base + 5.5),
               (x - 5.2 + i * 3.2, y + 5.2 + i * 0.8, base + 5.5), 'stone_dark')
    # Right arm raised with a cutlass; left hand on the hip.
    b.beam((x + 2.8, y, base + 12.9), (x + 5.8, y - 0.2, base + 15.8), 0.55, 'stone')
    b.beam((x + 5.8, y - 0.2, base + 15.8), (x + 6.6, y - 0.4, base + 18.7), 0.35, 'stone_light')
    b.beam((x + 6.2, y - 0.3, base + 18.0), (x + 10.2, y - 1.8, base + 22.0), 0.18, 'metal')
    b.beam((x + 9.2, y - 1.5, base + 20.5), (x + 10.8, y - 2.1, base + 22.4), 0.25, 'metal')
    b.beam((x - 2.8, y, base + 12.9), (x - 4.5, y - 1.2, base + 9.3), 0.55, 'stone')
    b.beam((x - 4.5, y - 1.2, base + 9.3), (x - 1.4, y - 1.7, base + 7.8), 0.35, 'stone')
    # A lantern held low on the seaward side.
    b.box((x - 5.0, y - 2.3, base + 8.4), (0.9, 0.9, 1.2), 'lantern')
    # The queen is a harbor landmark: make her a little larger than life.
    scale = 1.5
    for i in range(start, len(b.verts)):
        vx, vy, vz = b.verts[i]
        b.verts[i] = (x + (vx - x) * scale, y + (vy - y) * scale, z + (vz - z) * scale)
