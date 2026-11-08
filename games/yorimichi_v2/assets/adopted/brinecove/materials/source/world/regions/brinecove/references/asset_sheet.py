#!/usr/bin/env python3
"""Contact sheet of each TRELLIS reference beside its processed Blender views."""
from pathlib import Path

from PIL import Image, ImageDraw

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
import yori  # noqa: E402,F401
from brinecove.paths import REFERENCES, REVIEW as BUILD  # noqa: E402
REVIEWS = BUILD / 'asset-reviews'
REFS = REFERENCES / 'props'
SLUGS = ['pirate-queen-statue', 'galleon-figurehead', 'harbor-cannon', 'ship-anchor',
         'harbor-capstan', 'ships-wheel']


def main():
    rows = []
    for slug in SLUGS:
        images = []
        ref = REFS / f'{slug}.png'
        if ref.exists():
            images.append(('reference', ref))
        for view in ('front', 'three-quarter', 'side'):
            path = REVIEWS / f'{slug}-{view}.png'
            if path.exists():
                images.append((view, path))
        if images:
            rows.append((slug, images))
    if not rows:
        print('no asset reviews')
        return
    w = 360
    pad = 14
    canvas_w = pad + 4 * (w + pad)
    canvas_h = pad
    for _, images in rows:
        canvas_h += w + 50
    canvas = Image.new('RGB', (canvas_w, canvas_h), (22, 40, 44))
    draw = ImageDraw.Draw(canvas)
    y = pad
    for slug, images in rows:
        draw.text((pad, y + 4), slug, fill=(238, 226, 198))
        y += 28
        for i, (label, path) in enumerate(images):
            image = Image.open(path).convert('RGB').resize((w, w), Image.LANCZOS)
            x = pad + i * (w + pad)
            canvas.paste(image, (x, y))
            draw.text((x + 4, y + w + 4), label, fill=(200, 205, 190))
        y += w + 42
    out = REVIEWS / 'contact-sheet.jpg'
    canvas.save(out, quality=90)
    print(out)


if __name__ == '__main__':
    main()
