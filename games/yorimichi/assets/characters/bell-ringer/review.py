#!/usr/bin/env python3
"""Lay Suzu's review renders beside the design sheet, view for view, at one height.

    uv run python games/yorimichi/assets/characters/bell-ringer/review.py [--study NAME] [--out FILE]

Reads the sheet from references/sheet.jpg and the orthographic renders from build/yorimichi/bell-ringer/review/
(or build/yorimichi/bell-ringer/studies/<NAME>/review/) and writes a single comparison PNG (default
build/yorimichi/review/bell-ringer/compare.png). The sheet's own crop boxes are fixed, so a new render is compared
with the same pixels every time.
"""
import argparse
from pathlib import Path

from PIL import Image

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[4]
SHEET = HERE / 'references' / 'sheet.jpg'
# The four views on the sheet's top row and the face close-up on its second row, in source pixels.
CROPS = {
    'front': (40, 40, 400, 600),
    'side': (430, 40, 760, 600),
    'back': (790, 40, 1130, 600),
    'three_quarter': (1170, 40, 1530, 600),
    'face': (30, 610, 320, 900),
}


def fitted(image, height):
    return image.resize((round(image.width*height/image.height), height), Image.LANCZOS)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--study', help='read studies/<NAME>/review instead of the production review folder')
    parser.add_argument('--out', default=str(REPO/'build'/'yorimichi'/'review'/'bell-ringer'/'compare.png'))
    parser.add_argument('--height', type=int, default=820, help='height of every column in pixels')
    args = parser.parse_args()
    review = REPO/'build'/'yorimichi'/'bell-ringer'
    review = review/'studies'/args.study/'review' if args.study else review/'review'
    sheet = Image.open(SHEET).convert('RGB')
    columns = []
    for view in ('front', 'side', 'back', 'three_quarter', 'face'):
        model = review/f'{view}.png'
        if not model.exists():
            print(f'skip {view}: no {model}')
            continue
        columns += [fitted(sheet.crop(CROPS[view]), args.height), fitted(Image.open(model).convert('RGB'), args.height)]
    if not columns:
        raise SystemExit(f'no renders in {review}')
    canvas = Image.new('RGB', (sum(c.width for c in columns), args.height), (150, 150, 152))
    x = 0
    for column in columns:
        canvas.paste(column, (x, 0))
        x += column.width
    target = Path(args.out)
    target.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(target, quality=92)
    print(target)


if __name__ == '__main__':
    main()
