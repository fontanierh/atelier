#!/usr/bin/env python3
"""Concept paintings for the roadside houses on the main road, on Sunburst, steered by playtest screenshots.

    uv run python games/yorimichi/tools/house_concepts.py [--only street,variants] [--again street] [--dry-run]

Model gpt-image-2.5-sunburst, quality high, 1536x1024, through /v1/images/edits with the context images. Writes
<slug>.jpg (the committed copy), <slug>.prompt.txt and <slug>.provenance.json into games/yorimichi/assets/houses/concepts/;
the full-size PNG goes to build/yorimichi/houses/originals/. The context images are two playtest screenshots of the old
house, kept in build/yorimichi/houses/refs/ (not in git): playtest-road-house.webp (the house seen from the road) and
playtest-bank-house.webp (the house beside the uphill bank).

Every call is recorded before it is made and again when it returns: the provenance file is written with status
"submitted" first. A concept whose provenance exists without its JPEG (a call that failed or never came back) is not
asked for again unless --again names it, so a paid call is never repeated blindly. Existing JPEGs are skipped.
The key comes from OPENAI_API_KEY (or the ignored .env) and is never printed.
"""
import sys as _sys; from pathlib import Path as _Path; _sys.path.insert(0, str(_Path(__file__).resolve().parents[1] / 'world')); import yori  # noqa: E402
_sys.path.insert(0, str(_Path(__file__).resolve().parent))
import argparse, json, sys, time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

from treehouse_art import MODEL, QUALITY, compact, redact, rel, sha, sunburst

OUT = yori.ASSETS / 'houses' / 'concepts'
ORIGINALS = yori.OUT / 'houses' / 'originals'
REFS = yori.OUT / 'houses' / 'refs'
SIZE = '1536x1024'

STILLS = {
    'road': (REFS / 'playtest-road-house.webp', 'a screenshot of the game on its coastal country road, with the OLD roadside '
             'house that this painting replaces'),
    'bank': (REFS / 'playtest-bank-house.webp', 'another screenshot of the game: the same old house beside the grassy uphill '
             'bank of the road'),
}

STYLE = (
    'Concept art for Yorimichi, a stylised low-poly Japanese autumn exploration game. The numbered images are real '
    'screenshots of the game: match their art direction exactly: simple low-poly shapes, flat colours and soft painterly '
    'shading; the same autumn trees (vermilion and orange maples, golden ginkgo, deep teal-green pines and cedars), the '
    'same long grass and small flowering bushes, the same grey asphalt road with white edge lines, white guardrail and '
    'concrete utility poles, the same soft warm late-afternoon light. The player is a small child in a yellow t-shirt '
    'over white long sleeves and khaki cargo trousers: use him for scale. Do NOT copy the old house in the screenshots '
    '(a plain white box on a bare white slab, its side wall turned to the road): it is being redesigned. It must look '
    'like a polished, achievable game scene built from simple meshes: not photoreal, and not an elaborate illustration '
    'that could not be modelled.'
)

HOUSE = (
    'THE HOUSE: a lived-in rural Japanese house (minka) of a coastal hill village, on the sea side of the road, where '
    'the ground falls away behind it. It FACES THE ROAD: its long front with the entrance turns to the road, the way '
    'a family would really build beside a road. It stands set back about 6 m on a level terrace lot. Along the road '
    'edge: a low dry-stone kerb with a clipped evergreen hedge (ikegaki) on it, about waist height for an adult, '
    'broken by an entrance opening between two square timber gate posts. From the opening, large flat stepping '
    'stones cross a raked pale gravel yard to the genkan: a small entrance porch with its own little gabled tile roof '
    'projecting from the facade, a latticed wooden sliding door, a flat stone step in front. Beside the porch a raised '
    'wooden engawa veranda runs along the front under deep eaves, with sliding shoji and glass doors behind it. Posts '
    'stand on rounded foundation stones; a dark timber frame over cream plaster walls with a dark wooden wainscot along '
    'the bottom; a hip-and-gable (irimoya) roof of dark blue-grey kawara tiles with a heavy ridge, upturned end tiles '
    'and rafter ends under the eaves. Where the lot is higher than the falling ground at its side and back, it is held '
    'by a battered retaining wall of rounded grey stones (ishigaki), not a concrete slab. A small front garden beside '
    'the yard: a clipped pine (niwaki) by the gate, a small red maple, a stone lantern, two or three rocks with '
    'moss, potted plants by the door. The planting keeps clear of the walls. Everything tidy and grounded.'
)

VIEWS = {
    'street': (['road', 'bank'],
        'VIEW: player-height view from the road, the child standing on the asphalt in the foreground on the right, '
        'looking across the road at the gate. The house is seen three-quarter from the front, fully in view with its '
        'roof, a stone retaining wall visible at the lot\'s downhill side, tall trees behind and a glimpse of the sea '
        'beyond. The road runs across the lower part of the picture; the guardrail stops at the lot\'s frontage.'),
    'variants': (['road', 'bank'],
        'VIEW: a model sheet of three variants of the roadside house for the same game, each in a three-quarter front '
        'view from slightly above, standing on a small square of its own level lot (gravel yard, stepping stones, a bit '
        'of hedge and ishigaki at the lot edge), side by side on a plain warm light-grey background, all at the same '
        'scale, no text. LEFT: the tiled hip-and-gable house described above. MIDDLE: an older thatched farmhouse '
        '(kayabuki): a steep, thick hipped thatch roof with a ridge capped in dark tiles and short crossed ridge logs, '
        'dark weathered timber walls with a few plaster panels, a wide engawa with wooden storm shutters (amado) half '
        'open, a wide wooden sliding door into the earth-floored doma, a lean-to side roof over a woodpile. RIGHT: a '
        'two-storey tiled house, the upper floor smaller, a lower pent roof (hisashi) wrapping the ground floor, a small '
        'wooden balcony railing upstairs, a gabled upper roof, sliding glass doors, the genkan under a small tiled '
        'canopy. All three: foundation stones under the posts, dark blue-grey tiles, warm aged timber, cream plaster, '
        'chunky readable low-poly shapes, no fine clutter.'),
    'uphill': (['bank', 'road'],
        'VIEW: the same kind of house on the UPHILL side of the road instead: player-height view from the road, the '
        'child on the asphalt in the foreground. The level lot sits a little above the road, cut into the grassy '
        'hillside: a low stone wall along the road verge with the hedge on it, two or three wide stone steps up through '
        'the gate, the stepping stones continue to the genkan; beside and behind the house the hillside rises as a '
        'grassy bank held at its foot by a low stone wall, with the forest above. The house faces the road, '
        'three-quarter front view, roof in view.'),
}

AVOID = 'No photorealism, no concrete slab or plinth, no text, labels, borders or collage panels, no other people.'


def concepts():
    for view, (refs, text) in VIEWS.items():
        numbered = ' '.join(f'Image {i + 1} is {STILLS[r][1]}.' for i, r in enumerate(refs))
        yield view, refs, '\n\n'.join([STYLE + ' ' + numbered, HOUSE, text, AVOID])


def now():
    return datetime.now(timezone.utc).isoformat()


def run(slug, refs, prompt):
    (OUT/f'{slug}.prompt.txt').write_text(prompt + '\n')
    prov = dict(stage='house-concept', concept=slug, requested_model=MODEL, quality=QUALITY, size=SIZE,
                endpoint='/v1/images/edits', execution='games/yorimichi/tools/house_concepts.py',
                prompt_file=f'{slug}.prompt.txt', prompt_sha256=sha(prompt.encode()),
                reference_files={rel(STILLS[r][0]): sha(STILLS[r][0].read_bytes()) for r in refs},
                status='submitted', started_at=now())
    path = OUT/f'{slug}.provenance.json'
    path.write_text(json.dumps(prov, indent=2) + '\n')          # recorded before the paid call
    t = time.time()
    try:
        png, usage = sunburst(prompt, SIZE, [STILLS[r][0] for r in refs])
        ORIGINALS.mkdir(parents=True, exist_ok=True); (ORIGINALS/f'{slug}.png').write_bytes(png)
        prov.update(status='done', usage=usage, outputs={f'{slug}.png': sha(png)},
                    compact_copy=compact(png, OUT/f'{slug}.jpg', 'concepts'), error=None)
    except Exception as e:  # noqa: BLE001 - recorded in provenance, never retried here
        prov.update(status='failed', error=redact(e)[:600])
    prov.update(finished_at=now(), elapsed_seconds=round(time.time()-t, 1))
    path.write_text(json.dumps(prov, indent=2) + '\n')          # and again when it returns
    return slug, prov.get('error'), prov['elapsed_seconds']


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--only', default='')
    ap.add_argument('--again', default='', help='concepts to ask for again although a call was already recorded')
    ap.add_argument('--dry-run', action='store_true', help='print the prompts and stop')
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    wanted = [c for c in concepts() if not args.only or c[0] in args.only.split(',')]
    again = set(filter(None, args.again.split(',')))
    todo, blocked = [], []
    for c in wanted:
        if (OUT/f'{c[0]}.jpg').exists(): continue
        (blocked if (OUT/f'{c[0]}.provenance.json').exists() and c[0] not in again else todo).append(c)
    if args.dry_run:
        for slug, refs, prompt in wanted:
            print(f'--- {slug} {refs}\n{prompt}\n')
        return
    if blocked:
        print('already called (see their provenance), pass --again to repeat:', ', '.join(c[0] for c in blocked))
    missing = sorted({rel(STILLS[r][0]) for _, refs, _ in todo for r in refs if not STILLS[r][0].exists()})
    if missing:
        sys.exit(f'missing context images: {missing}')
    if todo:
        from atelier.env import require
        require('OPENAI_API_KEY')
    print(f'{len(todo)} to generate')
    with ThreadPoolExecutor(3) as pool:
        for slug, error, secs in pool.map(lambda c: run(*c), todo):
            print(f'{slug}: {"FAILED " + error if error else "ok"} ({secs} s)', flush=True)


if __name__ == '__main__':
    main()
