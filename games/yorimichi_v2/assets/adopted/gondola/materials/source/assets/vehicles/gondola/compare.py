"""Put the gondola review renders next to their concepts (concept left, render right) and overlay them.

uv run python games/yorimichi/assets/vehicles/gondola/compare.py CONCEPT_DIR
For each concept it assembles the matched panel renders (review/<view>.png, framed by cameras.json) into an image of
the concept's size, then writes review/compare_<concept>.png (side by side), review/overlay_<concept>.png (50% blend)
and review/edges_<concept>.png (the concept's strong edges drawn in magenta over the render). Close-ups crop both at
the same framing: review/closeup_<name>.png.
"""
import json
import os
import sys
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[4]
REVIEW = REPO / 'build' / 'yorimichi' / 'gondola' / 'review'
CAMS = json.loads((HERE / 'cameras.json').read_text())
FILL = {'gondola_tower_pylon.jpg': (221, 216, 207)}
# Close-ups: (concept file, box in concept pixels).
CLOSEUPS = {
    'cabin_grip': ('gondola_cabin.jpg', (240, 20, 500, 400)),
    'cabin_door_face': ('gondola_cabin.jpg', (100, 380, 360, 880)),
    'cabin_interior_benches': ('gondola_cabin.jpg', (860, 480, 1536, 920)),
    'tower_head': ('gondola_tower_pylon.jpg', (660, 60, 1170, 520)),
    'tower_base': ('gondola_tower_pylon.jpg', (0, 580, 470, 960)),
}


def label_pair(left, right, a, b):
    h = max(left.height, right.height)
    left = left.resize((round(left.width * h / left.height), h), Image.LANCZOS)
    right = right.resize((round(right.width * h / right.height), h), Image.LANCZOS)
    out = Image.new('RGB', (left.width + right.width + 12, h + 28), (255, 255, 255))
    out.paste(left, (0, 28)); out.paste(right, (left.width + 12, 28))
    d = ImageDraw.Draw(out); d.text((8, 8), a, fill=(40, 40, 40)); d.text((left.width + 20, 8), b, fill=(40, 40, 40))
    return out


def assemble(concept_name, size):
    views = {k: v for k, v in CAMS.items() if v['concept'] == concept_name and (REVIEW / f'{k}.png').exists()}
    if not views:
        return None, []
    canvas = Image.new('RGB', size, FILL.get(concept_name, (255, 255, 255)))
    for k, v in views.items():
        im = Image.open(REVIEW / f'{k}.png').convert('RGB')
        x0, y0, x1, y1 = v['box']
        canvas.paste(im.resize((x1 - x0, y1 - y0), Image.LANCZOS), (x0, y0))
    return canvas, sorted(views)


def edges(im):
    e = im.convert('L').filter(ImageFilter.FIND_EDGES).point(lambda v: 255 if v > 48 else 0)
    return e.filter(ImageFilter.MaxFilter(3))


def main():
    src = sys.argv[1] if len(sys.argv) > 1 else os.environ.get('GONDOLA_CONCEPTS')
    if not src:
        raise SystemExit('usage: compare.py CONCEPT_DIR (or set $GONDOLA_CONCEPTS): the folder with the gondola_*.jpg concepts')
    cdir = Path(src)
    made = []
    for concept_name in sorted({v['concept'] for v in CAMS.values()}):
        concept = Image.open(cdir / concept_name).convert('RGB')
        render, views = assemble(concept_name, concept.size)
        if render is None:
            continue
        stem = concept_name.rsplit('.', 1)[0].replace('gondola_', '')
        label_pair(concept, render, f'concept {concept_name}', 'Blender model, matched cameras: ' + ', '.join(views)).save(REVIEW / f'compare_{stem}.png')
        Image.blend(concept, render, 0.5).save(REVIEW / f'overlay_{stem}.png')
        mag = Image.new('RGB', concept.size, (255, 0, 200))
        Image.composite(mag, render, edges(concept)).save(REVIEW / f'edges_{stem}.png')
        made += [f'compare_{stem}.png', f'overlay_{stem}.png', f'edges_{stem}.png']
        for name, (cn, box) in CLOSEUPS.items():
            if cn != concept_name:
                continue
            crop_c, crop_r = concept.crop(box), render.crop(box)
            k = max(1, round(520 / crop_c.height))
            label_pair(crop_c.resize((crop_c.width * k, crop_c.height * k)), crop_r.resize((crop_r.width * k, crop_r.height * k)),
                       'concept', 'Blender model').save(REVIEW / f'closeup_{name}.png')
            made.append(f'closeup_{name}.png')
    _ = ImageChops
    print('wrote', *made)


if __name__ == '__main__':
    main()
