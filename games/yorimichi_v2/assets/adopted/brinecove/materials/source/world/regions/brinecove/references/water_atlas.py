#!/usr/bin/env python3
"""Paint the falling-water and mist textures for the Brinecove waterfall.

    uv run python games/yorimichi/world/regions/brinecove/references/water_atlas.py

waterfall.png tiles vertically: a bright foam curtain with cool streak shadows. mist.png is one feathered spray
billow for the large cards at the plunge pools; spray.png is foam lace lying on the water. Both are drawn procedurally; no paid call is involved.
"""
import math
import random
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
import yori  # noqa: E402,F401
from brinecove.paths import TEXTURES as OUT  # noqa: E402


def waterfall():
    """White water: an almost opaque foam curtain with pale blue-grey streak shadows, tiling top to bottom.

    The bridge painting's fall is bright churning white with cooler streaks; a translucent body with clipped holes
    read as a pixelated glass slab. The curtain's ragged edges come from the geometry's loose strands.
    """
    rng = random.Random(4471)
    w, h = 256, 512
    image = Image.new('RGBA', (w, h), (236, 244, 246, 236))
    draw = ImageDraw.Draw(image)
    # Cool shadow channels first, then bright foam streaks over them.
    for _ in range(70):
        x = rng.uniform(0, w)
        length = rng.uniform(120, 420)
        y0 = rng.uniform(0, h)
        width = rng.uniform(3, 12)
        tone = rng.randint(150, 200)
        colour = (tone - 18, tone + 14, tone + 30, rng.randint(205, 235))
        for dy in (0, -h, h):
            draw.line((x, y0 + dy, x + rng.uniform(-4, 4), y0 + length + dy), fill=colour, width=int(width))
    for _ in range(240):
        x = rng.uniform(0, w)
        length = rng.uniform(40, 260)
        y0 = rng.uniform(0, h)
        width = rng.uniform(2, 8)
        tone = rng.randint(232, 255)
        colour = (tone, tone, min(255, tone + 2), 255)
        for dy in (0, -h, h):
            draw.line((x, y0 + dy, x + rng.uniform(-3, 3), y0 + length + dy), fill=colour, width=int(width))
    # Wrap the columns too, so neighbouring tiles join without a seam.
    image = image.filter(ImageFilter.GaussianBlur(1.6))
    image.save(OUT / 'waterfall.png')
    print('waterfall', (w, h))


def mist():
    """Spray cloud: one broad soft billow per card, brightest low in the middle, with a torn, feathered edge.

    Small sharp puffs on crossed cards read as cotton balls; large overlapping feathered cards read as spray.
    """
    rng = random.Random(8819)
    size = 256
    alpha = Image.new('L', (size, size), 0)
    draw = ImageDraw.Draw(alpha)
    for _ in range(160):
        a = rng.uniform(0, math.tau)
        d = rng.uniform(0, 1) ** 0.8 * 96
        cx, cy = size / 2 + math.cos(a) * d, size * 0.58 + math.sin(a) * d * 0.55
        r = rng.uniform(10, 34) * (1.15 - d / 120)
        draw.ellipse((cx - r, cy - r * 0.8, cx + r, cy + r * 0.8), fill=rng.randint(10, 26))
    alpha = alpha.filter(ImageFilter.GaussianBlur(9))
    # Fade every edge to nothing, so no card silhouette survives.
    fade = Image.new('L', (size, size), 0)
    fd = ImageDraw.Draw(fade)
    for k in range(40):
        fd.ellipse((k * 1.6, k * 2.2, size - k * 1.6, size - k * 1.4), fill=int(255 * k / 39))
    fade = fade.filter(ImageFilter.GaussianBlur(12))
    body = np.asarray(alpha, 'float32')
    body = (body / max(1.0, body.max())) ** 0.8 * 190.0 * np.asarray(fade, 'float32') / 255.0
    alpha = Image.fromarray(body.astype('uint8'))
    tone = Image.new('RGB', (size, size), (246, 250, 251))
    Image.merge('RGBA', (*tone.split(), alpha)).save(OUT / 'mist.png')
    print('mist', (size, size))


def spray():
    """Ragged white foam lace for patches lying on the water; clipped, so it keeps crisp edges."""
    rng = random.Random(3307)
    size = 256
    lace = Image.new('L', (size, size), 0)
    draw = ImageDraw.Draw(lace)
    # Dense enough to read as a white wash from the sea at clip 0.45: a sparse lace vanished at distance.
    for _ in range(700):
        a = rng.uniform(0, math.tau)
        d = rng.uniform(0, 1) ** 0.8 * 118
        cx, cy = size / 2 + math.cos(a) * d, size / 2 + math.sin(a) * d * 0.55
        r = rng.uniform(5, 17) * (1.25 - d / 150)
        draw.ellipse((cx - r * 1.4, cy - r * 0.8, cx + r * 1.4, cy + r * 0.8), fill=rng.randint(200, 255))
    # Dark holes keep it lace rather than a solid white tile.
    for _ in range(160):
        cx, cy, r = rng.uniform(0, size), rng.uniform(0, size), rng.uniform(2, 6)
        draw.ellipse((cx - r * 1.5, cy - r, cx + r * 1.5, cy + r), fill=0)
    lace = lace.filter(ImageFilter.GaussianBlur(1.6))
    tone = Image.new('RGB', (size, size), (240, 246, 244))
    image = Image.merge('RGBA', (*tone.split(), lace))
    image.save(OUT / 'spray.png')
    print('spray', (size, size))


if __name__ == '__main__':
    OUT.mkdir(parents=True, exist_ok=True)
    waterfall()
    mist()
    spray()
