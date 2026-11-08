#!/usr/bin/env python3
"""Contact sheets that put each Brinecove render beside its Sunburst concept."""
import json
import sys
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import yori  # noqa: E402,F401
from brinecove.paths import REVIEW as OUT  # noqa: E402
REFS = OUT / 'references'
RENDERS = OUT / 'renders'
PAIRS = [
    ('01-aerial-hero', '01-aerial-hero'),
    ('02-harbor-approach', '02-harbor-approach'),
    ('03-market-square', '03-market-square'),
    ('04-upper-terrace', '04-upper-terrace'),
    ('05-lighthouse-headland', '05-lighthouse-headland'),
    ('06-shipyard', '06-shipyard'),
    ('07-waterfall-bridge', '07-waterfall-bridge'),
    ('08-night-harbor', '08-night-harbor'),
    ('09-rum-row', '09-rum-row'),
    ('10-cliff-shacks', '11-cliff-shacks'),
    ('13-map', '10-topdown'),
]


def label(draw, text, xy, fill=(238, 228, 205)):
    draw.text(xy, text, fill=fill)


def sheet(name, items):
    if not items:
        return None
    w = 960
    images = []
    for concept, render in items:
        a = Image.open(REFS / f'{concept}.png').convert('RGB')
        b = Image.open(RENDERS / f'{render}.png').convert('RGB')
        a = a.resize((w, round(a.height * w / a.width)), Image.LANCZOS)
        b = b.resize((w, round(b.height * w / b.width)), Image.LANCZOS)
        images.append((concept, render, a, b))
    pad = 18
    height = sum(a.height + b.height + 58 for _, _, a, b in images) + pad
    canvas = Image.new('RGB', (w + pad * 2, height), (19, 43, 49))
    draw = ImageDraw.Draw(canvas)
    y = pad
    for concept, render, a, b in images:
        label(draw, f'SUNBURST  {concept}', (pad, y))
        y += 20
        canvas.paste(a, (pad, y)); y += a.height + 5
        label(draw, f'BLENDER  {render}', (pad, y))
        y += 20
        canvas.paste(b, (pad, y)); y += b.height + 15
    dest = RENDERS / name
    canvas.save(dest, quality=90)
    print(dest)


def main():
    RENDERS.mkdir(parents=True, exist_ok=True)
    made = [p for p in PAIRS if (REFS / f'{p[0]}.png').exists() and (RENDERS / f'{p[1]}.png').exists()]
    for i in range(0, len(made), 3):
        sheet(f'compare-{i // 3 + 1}.jpg', made[i:i + 3])
    # A compact visual index of every render.
    files = sorted(p for p in RENDERS.glob('*.png') if p.name[:2].isdigit() and p.name[2] == '-')
    if files:
        thumbs = []
        for p in files:
            im = Image.open(p).convert('RGB')
            im = im.resize((560, round(im.height * 560 / im.width)), Image.LANCZOS)
            thumbs.append((p, im))
        cols = 2
        pad = 12
        cell_h = max(im.height for _, im in thumbs) + 32
        rows = (len(thumbs) + cols - 1) // cols
        canvas = Image.new('RGB', (cols * 560 + (cols + 1) * pad, rows * cell_h + (rows + 1) * pad), (19, 43, 49))
        draw = ImageDraw.Draw(canvas)
        for i, (p, im) in enumerate(thumbs):
            x = pad + (i % cols) * (560 + pad); y = pad + (i // cols) * cell_h
            label(draw, p.stem, (x, y))
            canvas.paste(im, (x, y + 20))
        canvas.save(RENDERS / 'contact-sheet.jpg', quality=90)
        print(RENDERS / 'contact-sheet.jpg')
    (OUT / 'review.json').write_text(json.dumps(dict(pairs=made), indent=2) + chr(10))


if __name__ == '__main__':
    main()
