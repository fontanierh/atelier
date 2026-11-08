#!/usr/bin/env python3
"""Paint the alpha leaf-card atlases used by the Brinecove trees and palms.

    uv run python games/yorimichi/world/regions/brinecove/references/leaf_atlas.py

Four 512-square canopies (mid, light, deep, warm) share one leaf silhouette
vocabulary; a separate atlas carries long palm fronds.  Every card in the
scene samples one 256-square cell, so the same atlas serves the whole town.
"""
import math
import random
from pathlib import Path

from PIL import Image, ImageDraw

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
import yori  # noqa: E402,F401
from brinecove.paths import TEXTURES as OUT  # noqa: E402
SIZE = 512
CELL = SIZE // 2

# Base leaf colour, vein colour, and the spread of shades around the base.
PALETTES = {
    'leaf_mid': ((76, 104, 48), (52, 74, 34), 26),
    'leaf_light': ((108, 138, 63), (74, 100, 44), 30),
    'leaf_deep': ((52, 72, 34), (34, 50, 23), 20),
    'leaf_warm': ((150, 112, 48), (104, 74, 34), 34),
    # Sunlit crown tops and the orange and gold accents of the Sunburst canopy.
    'leaf_sun': ((138, 160, 70), (96, 118, 48), 28),
    'leaf_rust': ((176, 98, 44), (120, 62, 30), 30),
    'leaf_gold': ((186, 146, 58), (128, 96, 36), 30),
}


def shade(color, amount):
    return tuple(max(0, min(255, int(c + amount))) for c in color)


def leaf_polygon(cx, cy, length, width, angle):
    points = []
    steps = 12
    for i in range(steps + 1):
        t = i / steps
        x = (t - 0.5) * length
        y = math.sin(math.pi * t) ** 0.72 * width * 0.5
        points.append((x, y))
    for i in range(steps, -1, -1):
        t = i / steps
        x = (t - 0.5) * length
        y = -math.sin(math.pi * t) ** 0.72 * width * 0.5
        points.append((x, y))
    ca, sa = math.cos(angle), math.sin(angle)
    return [(cx + x * ca - y * sa, cy + x * sa + y * ca) for x, y in points]


def paint_canopy(draw, ox, oy, base, vein, spread, rng):
    # Back leaves first and darker, front leaves last and lit from the upper left, so one card already reads as
    # a rounded clump instead of a flat decal.
    leaves = []
    for _ in range(30):
        angle = rng.uniform(0, math.tau)
        distance = rng.uniform(4, 96) ** 0.92 * 1.2
        leaves.append((angle, distance))
    leaves.sort(key=lambda leaf: -math.sin(leaf[0]) * leaf[1])
    for index, (angle, distance) in enumerate(leaves):
        light = (index / len(leaves) - 0.5) * spread * 1.4
        cx = ox + 128 + math.cos(angle) * distance
        cy = oy + 128 + math.sin(angle) * distance * 0.86
        length = rng.uniform(72, 138)
        width = length * rng.uniform(0.34, 0.52)
        tone = rng.randint(-spread, spread) // 2 + light
        colour = shade(base, tone)
        rotation = angle + rng.uniform(-1.2, 1.2)
        polygon = leaf_polygon(cx, cy, length, width, rotation)
        draw.polygon(polygon, fill=colour + (255,))
        # A darker midrib and two side veins keep the cards readable at distance.
        ca, sa = math.cos(rotation), math.sin(rotation)
        x0, y0 = cx - ca * length * 0.44, cy - sa * length * 0.44
        x1, y1 = cx + ca * length * 0.44, cy + sa * length * 0.44
        draw.line((x0, y0, x1, y1), fill=vein + (210,), width=2)
        for side in (-1, 1):
            vx = cx + math.cos(rotation + side * 0.7) * length * 0.25
            vy = cy + math.sin(rotation + side * 0.7) * length * 0.25
            draw.line((cx, cy, vx, vy), fill=vein + (160,), width=1)


def leaf_atlas(name, base, vein, spread):
    rng = random.Random(sum(map(ord, name)))
    image = Image.new('RGBA', (SIZE, SIZE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    for cell in range(4):
        ox, oy = (cell % 2) * CELL, (cell // 2) * CELL
        paint_canopy(draw, ox, oy, base, vein, spread, rng)
    image.save(OUT / f'{name}.png')
    print(name, image.size)


def palm_frond():
    """One coconut frond per cell: rachis up the middle (base at the bottom), long leaflets sweeping to the tip.

    The cards are bent strips whose v runs from the trunk to the tip, so each cell is painted as a single frond
    that fills the width, not a cone of leaves.
    """
    rng = random.Random(9157)
    image = Image.new('RGBA', (SIZE, SIZE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    for cell in range(4):
        ox, oy = (cell % 2) * CELL, (cell // 2) * CELL
        cx = ox + CELL / 2
        base_y = oy + CELL - 4
        tip_y = oy + 6
        base = ((92, 124, 52), (104, 132, 56), (82, 112, 46), (112, 128, 58))[cell]
        leaflets = []
        for i in range(34):
            t = 0.04 + 0.94 * i / 33
            for side in (-1, 1):
                leaflets.append((t, side))
        # Underside leaflets first, so the upper row overlaps them.
        leaflets.sort(key=lambda leaf: (leaf[1], leaf[0]))
        for t, side in leaflets:
            y = base_y + (tip_y - base_y) * t
            reach = (math.sin(math.pi * min(1.0, t * 1.15)) ** 0.6) * (CELL * 0.47) + 6
            reach *= rng.uniform(0.88, 1.04)
            # Leaflets angle forward toward the tip and droop a little at their ends.
            angle = -math.pi / 2 + side * (1.05 - 0.35 * t) + rng.uniform(-0.06, 0.06)
            tip = (cx + math.cos(angle) * reach, y + math.sin(angle) * reach * 0.62 + 10 * (1 - t))
            mid = ((cx + tip[0]) / 2 + side * 2, (y + tip[1]) / 2 + 3)
            width = 7.5 * (1.0 - 0.55 * t) + 2
            tone = rng.randint(-18, 18) + int(18 * (side > 0)) - int(10 * t)
            colour = shade(base, tone) + (255,)
            normal = (-(tip[1] - y), tip[0] - cx)
            length = math.hypot(*normal) or 1.0
            nx, ny = normal[0] / length * width * 0.5, normal[1] / length * width * 0.5
            draw.polygon([(cx, y), (mid[0] + nx, mid[1] + ny), tip, (mid[0] - nx, mid[1] - ny)], fill=colour)
            draw.line((cx, y, mid[0], mid[1]), fill=shade(base, -30) + (170,), width=1)
        for k in range(24):
            t0, t1 = k / 24, (k + 1) / 24
            draw.line((cx, base_y + (tip_y - base_y) * t0, cx, base_y + (tip_y - base_y) * t1),
                      fill=(78, 92, 42, 255), width=max(1, int(5 * (1 - t0)) + 1))
    image.save(OUT / 'palm_frond.png')
    print('palm_frond', image.size)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    for name, (base, vein, spread) in PALETTES.items():
        leaf_atlas(name, base, vein, spread)
    palm_frond()


if __name__ == '__main__':
    main()

