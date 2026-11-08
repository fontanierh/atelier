"""Lay out the furniture LOD review frames side by side, labelled (plain Python with Pillow).

Reads build/yorimichi/belmonte-train/review-perf/frames/ (review_lods.py) and writes review-perf/<asset>.png (the fitted
mesh, LOD0 and LOD1, then the fitted mesh and LOD0 close up) and review-perf/<coach>-<view>.png (fitted above, LOD0 below).
"""
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import yori  # noqa: E402,F401

from train import budgets as B  # noqa: E402
from train import bake_manifest as BM  # noqa: E402

OUT = yori.OUT / 'belmonte-train'
REVIEW = OUT / 'review-perf'
FRAMES = REVIEW / 'frames'


def font(px):
    for name in ('/System/Library/Fonts/Helvetica.ttc', '/System/Library/Fonts/Supplemental/Arial.ttf'):
        try:
            return ImageFont.truetype(name, px)
        except OSError:
            pass
    return ImageFont.load_default()


def label(img, text, px=30):
    d = ImageDraw.Draw(img)
    d.rectangle((0, 0, img.width, px + 18), fill=(255, 255, 255))
    d.text((14, 8), text, fill=(20, 20, 20), font=font(px))
    return img


def row(images):
    h = max(i.height for i in images)
    out = Image.new('RGB', (sum(i.width for i in images), h), 'white')
    x = 0
    for i in images:
        out.paste(i, (x, 0)); x += i.width
    return out


def column(images):
    w = max(i.width for i in images)
    out = Image.new('RGB', (w, sum(i.height for i in images)), 'white')
    y = 0
    for i in images:
        out.paste(i, (0, y)); y += i.height
    return out


def asset_sheet(asset, lods):
    src = lods['source_triangles']
    levels = {r['level']: r for r in lods['levels']}
    tex = 'x'.join(map(str, lods['textures']['base']))
    names = [('before', f'fitted Tripo: {lods["source_triangles"]:,} tris, 2048 maps'),
             ('lod0', f'LOD0: {levels[0]["triangles"]:,} tris, {tex} baked'),
             ('lod1', f'LOD1: {levels[1]["triangles"]:,} tris' if 1 in levels else None)]
    top = [label(Image.open(FRAMES / f'{asset}-{k}.png').convert('RGB'), t) for k, t in names if t and (FRAMES / f'{asset}-{k}.png').exists()]
    close = [label(Image.open(FRAMES / f'{asset}-{k}-close.png').convert('RGB'), f'{t.split(":")[0]} close') for k, t in names[:2]
             if (FRAMES / f'{asset}-{k}-close.png').exists()]
    sheet = column([row(top), row(close)]) if close else row(top)
    sheet.save(REVIEW / f'{asset}.png')
    print(f'{asset}: {src} -> {[levels[k]["triangles"] for k in sorted(levels)]}', flush=True)


def coach_sheets():
    for before in sorted(FRAMES.glob('*-before.png')):
        stem = before.name[:-len('-before.png')]
        if stem in B.FURNITURE:
            continue
        after = FRAMES / f'{stem}-lod0.png'
        if not after.exists():
            continue
        sheet = column([label(Image.open(before).convert('RGB'), f'{stem}: fitted Tripo furniture'),
                        label(Image.open(after).convert('RGB'), f'{stem}: LOD0 furniture')])
        sheet.save(REVIEW / f'{stem}.png')
        print(f'{stem}: sheet', flush=True)


def main():
    summary = BM.read(OUT / 'furniture')
    REVIEW.mkdir(parents=True, exist_ok=True)
    for a in B.FURNITURE:
        if (FRAMES / f'{a}-lod0.png').exists():
            asset_sheet(a, summary[a])
    coach_sheets()
    print('BELMONTE TRAIN FURNITURE REVIEW SHEETS COMPLETE', flush=True)


if __name__ == '__main__':
    main()
