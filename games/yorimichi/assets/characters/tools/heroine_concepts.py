#!/usr/bin/env python3
"""Eight concept directions for a new female character, painted in Cairo's style by gpt-image-2.5-sunburst.

    YORIMICHI_ARCHIVE=... uv run python games/yorimichi/assets/characters/tools/heroine_concepts.py [--only A,B] [--rev r01]
    YORIMICHI_ARCHIVE=... uv run python games/yorimichi/assets/characters/tools/heroine_concepts.py sheet [--rev r01]

Asset root: <archive>/output/imagegen/yorimichi-heroine-2026-10-06/concepts-<rev>/ (YORIMICHI_ARCHIVE, see _archive.py).
The only reference is Cairo's three-quarter render, the authority for the art style. Each image goes through
atelier.ai.ledger at quality=high, 1024 x 1024, with its prompt and provenance beside it. `sheet` lays the eight out
with their labels for review; one is picked before the turnaround stage (sword_trainer_pipeline.py shows the next steps).
"""
import sys as _sys; from pathlib import Path as _Path; _sys.path.insert(0, str(_Path(__file__).resolve().parent))  # noqa: E702
from _archive import ROOT  # noqa: E402
import argparse, hashlib, sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import spirit_concepts as sc  # noqa: E402  (gpt_edit, sha, key)

REPO = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(REPO / 'platform/studio'))
from atelier import env  # noqa: E402
from atelier.ai import ledger  # noqa: E402

ASSET = ROOT / 'output/imagegen/yorimichi-heroine-2026-10-06'
REFS = [ROOT / 'output/imagegen/yorimichi-sword-trainer-2026-10-05/refs/cairo_three_quarter.png']

STYLE = (
    "Input image: a render of Cairo, the boy who is the player character of our stylised 3D game Yorimichi, a warm "
    "Japanese exploration game of forest hamlets, a fishing harbour, a small city, skate spots and mountain roads. The "
    "image is the authority for the art style only; do not draw Cairo. Style: soft smooth stylised 3D, matte painted "
    "colour, simple rounded shapes, a large simple face with two plain dark oval eyes without visible whites, small nose "
    "and mouth, hands with five fingers, clothes as a few clean solid shapes with little fine detail. Design a NEW "
    "character in exactly that style: a girl about Cairo's age and height (around 148 cm), a peer who could play beside "
    "him. "
)
COMPOSITION = (
    "Composition: ONE full-body figure in a relaxed, characterful standing pose, three-quarter view like the input "
    "image, the whole figure from hair to shoes centred on a square canvas with clear margin. Plain mid-grey studio "
    "background, soft even light, a faint contact shadow only. Readable silhouette and a palette of at most four main "
    "colours. No text, labels, logos, borders, insets or extra figures."
)
CONCEPTS = {
    'A': ('Skater', "Concept: a street skater. An oversized faded teal hoodie over a cream long-sleeve shirt, wide "
          "charcoal cargo shorts to below the knee, mismatched tall socks, chunky grey skate shoes, a black knee pad on "
          "one knee and a scuffed plaster on the other. Short choppy dark-brown hair under a backwards ochre cap. One "
          "hand holds a skateboard upright at her side, its deck painted with a simple maple leaf."),
    'B': ('Courier', "Concept: a bicycle courier who knows every road. A fitted rust-orange windbreaker with a cream "
          "stripe across the chest, black cycling shorts over dark leggings, short white socks, light trainers. A big "
          "cream messenger bag across the body with a rolled map in the side pocket, a small cycling cap with the brim "
          "up. Long black hair in a single thick braid over one shoulder. Confident grin, one hand on the bag strap."),
    'C': ('Lantern warden', "Concept: a young spirit warden from the island shrine. A short white haori with wide "
          "vermilion trim over a fitted dark-indigo shirt, a vermilion pleated skirt-like hakama cut above the knee, "
          "dark leggings, tabi socks and wooden-soled sandals. A paper lantern hanging from a short bamboo staff held "
          "over one shoulder, a few paper charm tags on her belt. Black hair to the jaw with straight bangs and a red "
          "cord tied at the back. Calm, watchful expression."),
    'D': ('Harbour diver', "Concept: a free diver from the fishing village. A sleeveless navy wetsuit top with a "
          "sea-green panel at the side, loose rolled-up sand-coloured canvas trousers, bare ankles and sturdy rubber "
          "sandals. Round diving goggles pushed up on her forehead, a rope net bag with two glass fishing floats on "
          "her hip, a small knife sheath strapped to the calf. Sun-browned skin, short wavy hair bleached at the tips. "
          "Cheerful, salt-weathered look."),
    'E': ('Mountain rider', "Concept: a horse rider from the mountain pastures. A fitted moss-green riding jacket with "
          "a high collar and brass buttons, a cream scarf, tan riding trousers, tall dark-brown boots, leather gloves "
          "tucked into the belt. A coiled rope on her hip and a small saddlebag-style pouch. Dark hair in a low "
          "ponytail under a flat-brimmed felt hat with a feather. Steady, outdoorsy, determined."),
    'F': ('Airship mechanic', "Concept: a mechanic from the zeppelin dock. Mustard-yellow work overalls with the top "
          "half tied around the waist by the sleeves, a fitted black tank top, a wide tool belt with a wrench and a "
          "screwdriver as solid simple shapes, heavy brown work boots, rolled cuffs. Big round flight goggles around "
          "her neck, an oil smudge on one cheek, messy auburn bun held with a pencil. Proud, practical stance."),
    'G': ('Mapmaker', "Concept: an explorer who draws the game's maps. A short ochre field jacket with many pockets "
          "over a pale-blue shirt, a knee-length dark-green skirt over brown leggings, walking boots, a wide-brimmed "
          "straw hat with a red band. A leather satchel stuffed with rolled maps, a sketchbook held open in one hand "
          "and a pencil behind her ear, round glasses. Shoulder-length black hair. Curious, bookish, lively."),
    'H': ('Kendo apprentice', "Concept: the sword teacher's young apprentice from Momiji Hamlet. A cream practice gi "
          "jacket with the sleeves tied back, a deep maple-red hakama, dark shin wraps, flat straw sandals. A wooden "
          "practice sword resting on one shoulder, a folded maple-orange headband tied around the forehead with long "
          "tails. Black hair in a high short ponytail. Bold, competitive smile, a rival as much as a friend."),
}


def generate(name, prompt, out):
    """One Sunburst edit through the ledger: the image, its prompt and its provenance in `out`."""
    out.mkdir(parents=True, exist_ok=True)
    sc.OUT = out
    sc.SIZE = '1024x1024'
    (out / f'{name}.prompt.txt').write_text(prompt + '\n')
    meta = dict(asset='heroine', stage='concept', candidate=name, label=CONCEPTS[name][0], provider='openai',
                requested_model=sc.MODEL, quality=sc.QUALITY, size=sc.SIZE, endpoint='/v1/images/edits',
                execution='games/yorimichi/assets/characters/tools/heroine_concepts.py',
                prompt_file=f'{name}.prompt.txt', prompt_sha256=hashlib.sha256(prompt.encode()).hexdigest(),
                reference_files={str(p.relative_to(ROOT)): sc.sha(p) for p in REFS})
    target = out / f'{name}.png'

    def call():
        blobs, secs = sc.gpt_edit(prompt, REFS, 1)
        target.write_bytes(blobs[0])
        return dict(elapsed_seconds=secs, output=target.name, output_sha256=sc.sha(target), approval='pending')
    record = ledger.run_once(out / f'{name}.provenance.json', meta, call)
    return name, record['elapsed_seconds']


def concepts(rev, only):
    out = ASSET / f'concepts-{rev}'
    names = only or list(CONCEPTS)
    missing = [str(p) for p in REFS if not p.exists()]
    if missing:
        sys.exit(f'missing reference {missing}: set YORIMICHI_ARCHIVE')
    env.load()
    sc.key()
    print(f'painting {len(names)} concepts into {out}', flush=True)

    def one(name):
        try:
            return generate(name, STYLE + CONCEPTS[name][1] + ' ' + COMPOSITION, out)
        except Exception as error:   # the ledger keeps the uncertain record; never retried here
            return name, f'ERROR {type(error).__name__}: {error}'
    with ThreadPoolExecutor(4) as ex:
        for name, secs in ex.map(one, names):
            print(f'{name} ({CONCEPTS[name][0]}): {secs}', flush=True)


def sheet(rev, also=()):
    """The eight in one image; a candidate missing from `rev` is taken from the first of `also` that has it."""
    from PIL import Image, ImageDraw, ImageFont
    out = ASSET / f'concepts-{rev}'
    tile, label = 512, 44
    canvas = Image.new('RGB', (4*tile, 2*(tile+label)), (236, 233, 226))
    draw = ImageDraw.Draw(canvas)
    try:
        font = ImageFont.truetype('/System/Library/Fonts/Supplemental/Arial Bold.ttf', 26)
    except OSError:
        font = ImageFont.load_default()
    for i, (name, (title, _)) in enumerate(CONCEPTS.items()):
        x, y = (i % 4)*tile, (i // 4)*(tile+label)
        path = next((p for p in [out / f'{name}.png'] + [ASSET / f'concepts-{r}' / f'{name}.png' for r in also]
                     if p.exists()), out / f'{name}.png')
        if path.exists():
            canvas.paste(Image.open(path).convert('RGB').resize((tile, tile)), (x, y+label))
        draw.text((x+14, y+9), f'{name}  {title}', fill=(40, 36, 32), font=font)
    target = out / 'sheet.jpg'
    canvas.save(target, quality=90)
    print(target)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('stage', nargs='?', default='concepts', choices=['concepts', 'sheet'])
    ap.add_argument('--only', default='')
    ap.add_argument('--rev', default='r01')
    ap.add_argument('--also', default='', help='sheet: other revisions to take missing candidates from')
    a = ap.parse_args()
    if a.stage == 'sheet':
        sheet(a.rev, [r for r in a.also.split(',') if r])
    else:
        concepts(a.rev, [s for s in a.only.split(',') if s])


if __name__ == '__main__':
    main()
