"""Put the ferry review renders next to concept C (concept left, render right).

uv run python games/yorimichi/assets/vehicles/ferry/compare.py [CONCEPT.jpg]
Reads build/yorimichi/ferry/review/ferry_{three_quarter,side,top}.png and writes compare_*.png beside them, a
50% overlay of the matched three-quarter view and rigging close-ups (closeup_*.png, concept crop vs render crop at
the same framing of the matched camera).
"""
import sys
from pathlib import Path

from PIL import Image, ImageDraw

REPO = Path(__file__).resolve().parents[5]
REVIEW = REPO / 'build' / 'yorimichi' / 'ferry' / 'review'
BACKGROUND = (238, 238, 233)
# Close-up framings (left, top, right, bottom) in the concept's 1536 x 1024 pixels.
CLOSEUPS = {'rigging_foremast_bow': (840, 30, 1500, 560), 'rigging_aftmast_funnel': (150, 110, 760, 430),
            'lifeboats': (220, 290, 800, 470), 'bow_anchor': (1180, 520, 1500, 760), 'funnel_ventilators': (420, 120, 800, 380)}
# Side-view close-up of the companionway at the canopy end / aft deckhouse (side render pixels), shown against the
# iteration 9 side render for before/after.
STAIR_SIDE = (250, 190, 660, 460)
BEFORE = REPO / 'build' / 'yorimichi' / 'ferry' / 'iterations' / 'iter9' / 'ferry_side.png'


def flatten(path):
    im = Image.open(path).convert('RGBA')
    bg = Image.new('RGBA', im.size, BACKGROUND + (255,))
    return Image.alpha_composite(bg, im).convert('RGB')


def pair(left, right, label_left, label_right):
    h = max(left.height, right.height)
    left = left.resize((round(left.width * h / left.height), h), Image.LANCZOS)
    right = right.resize((round(right.width * h / right.height), h), Image.LANCZOS)
    out = Image.new('RGB', (left.width + right.width + 12, h + 28), (255, 255, 255))
    out.paste(left, (0, 28)); out.paste(right, (left.width + 12, 28))
    d = ImageDraw.Draw(out)
    d.text((8, 8), label_left, fill=(40, 40, 40)); d.text((left.width + 20, 8), label_right, fill=(40, 40, 40))
    return out


def main():
    concept_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path.home() / '.cache/atelier/handoff/jim5/transport-concepts/ferry_oldschool_c.jpg'
    concept = Image.open(concept_path).convert('RGB')
    for view in ('three_quarter', 'side', 'top'):
        render = flatten(REVIEW / f'ferry_{view}.png')
        pair(concept, render, 'concept C', f'Blender model: {view.replace("_", " ")}').save(REVIEW / f'compare_{view}.png')
        if view == 'three_quarter':
            Image.blend(concept, render.resize(concept.size), 0.5).save(REVIEW / 'overlay_three_quarter.png')
            matched = render.resize(concept.size)
            for name, box in CLOSEUPS.items():
                pair(concept.crop(box), matched.crop(box), 'concept C', 'Blender model').resize(
                    (2 * (box[2] - box[0]) * 2 + 24, (box[3] - box[1]) * 2 + 56), Image.LANCZOS).save(REVIEW / f'closeup_{name}.png')
    if BEFORE.exists():
        after = flatten(REVIEW / 'ferry_side.png').crop(STAIR_SIDE); before = flatten(BEFORE).crop(STAIR_SIDE)
        pair(before, after, 'iteration 9 (side)', 'now (side)').resize((before.width * 4 + 24, before.height * 2 + 56), Image.LANCZOS).save(REVIEW / 'closeup_stair_side.png')
    print('wrote', *sorted(p.name for p in REVIEW.glob('compare_*.png')), *sorted(p.name for p in REVIEW.glob('closeup_*.png')))


if __name__ == '__main__':
    main()
