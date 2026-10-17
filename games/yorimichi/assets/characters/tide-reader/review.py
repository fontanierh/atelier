#!/usr/bin/env python3
"""Lay the six orthographic Kiyo renders out as a labelled review sheet."""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
REVIEW = HERE.parents[4] / 'build' / 'yorimichi' / 'tide-reader' / 'review'


def main():
    views = [(name, REVIEW / f'{name}.png') for name in ('front', 'profile', 'back', 'three_quarter')]
    faces = [('face', REVIEW / 'face.png'), ('hat', REVIEW / 'hat.png')]
    tile_w, tile_h, label_h = 540, 710, 44
    sheet = Image.new('RGB', (tile_w * 4, tile_h + label_h + 420), (218, 217, 214))
    draw = ImageDraw.Draw(sheet)
    font = ImageFont.load_default(size=24)
    for index, (name, path) in enumerate(views):
        image = Image.open(path).convert('RGB')
        image.thumbnail((tile_w, tile_h), Image.Resampling.LANCZOS)
        x = index * tile_w + (tile_w - image.width) // 2
        y = (tile_h - image.height) // 2
        sheet.paste(image, (x, y))
        draw.text((index * tile_w + 18, tile_h + 8), name.replace('_', ' ').upper(), fill=(48, 48, 50), font=font)
    y = tile_h + label_h
    for index, (name, path) in enumerate(faces):
        image = Image.open(path).convert('RGB')
        image.thumbnail((tile_w * 2, 380), Image.Resampling.LANCZOS)
        x = index * tile_w * 2 + (tile_w * 2 - image.width) // 2
        sheet.paste(image, (x, y))
        draw.text((index * tile_w * 2 + 18, y + 386), name.upper(), fill=(48, 48, 50), font=font)
    target = REVIEW / 'contact-sheet.jpg'
    sheet.save(target, quality=92, subsampling=0)
    print(target)


if __name__ == '__main__':
    main()
