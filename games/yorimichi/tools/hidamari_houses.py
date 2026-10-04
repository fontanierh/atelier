#!/usr/bin/env python3
"""Hidamari back-lane houses: a Sunburst concept of each house variant alone, in the style of the city's art-direction
redesigns, to model it from in the building kit (world/regions/hidamari/kit/house.py).

    uv run python games/yorimichi/tools/hidamari_houses.py concept [--only 0,2] [--dry-run]
    uv run python games/yorimichi/tools/hidamari_houses.py sheet

Each variant lives in games/yorimichi/assets/hidamari/houses/<n>/: concept.jpg with concept.json, the ledger record
of the paid call (atelier.ai.ledger.run_once: a variant with a record is never painted again; rename the record to
concept.rejected-N.json and the picture likewise to repaint). The full-size paintings stay in
build/yorimichi/hidamari/houses/.
"""
import sys as _sys; from pathlib import Path as _Path; _sys.path.insert(0, str(_Path(__file__).resolve().parents[1] / 'world')); import yori  # noqa: E402
_sys.path.insert(0, str(_Path(__file__).resolve().parent))
import argparse, time
from concurrent.futures import ThreadPoolExecutor

from treehouse_art import MODEL, QUALITY, compact, rel, sha, sheet as contact_sheet, sunburst

OUT = yori.ASSETS / 'hidamari' / 'houses'
ORIGINALS = yori.OUT / 'hidamari' / 'houses'
CONCEPTS = yori.ASSETS / 'hidamari' / 'concepts'
STYLE_REFS = [CONCEPTS / 'cross_street_ns730.jpg', CONCEPTS / 'street_ew140.jpg']
SIZE = '1536x1024'

STYLE = ('Paint ONE ordinary two-storey Japanese family house alone, as a reference for modelling it: the whole house '
         'and its small front plot, in a three-quarter front view from standing eye height a little to the left, '
         'centred with a clear margin all round, on a plain flat light-grey background, soft even afternoon light, no '
         'other buildings, no street, no people, no text, letters or logos anywhere. Images 1 and 2 show the art '
         'direction of the game it is for, Yorimichi, a stylised Japanese autumn harbour town: paint it in that same '
         'warm hand-painted style, simple chunky readable shapes that could be built from boxes and slabs, believable '
         'proportions for a 10 m wide by 9 m deep plot, matte colours with soft variation and light weathering, no '
         'glossy highlights. Common to every variant: dark grey kawara tile roof, a small tiled pent roof over the '
         'ground-floor front, aluminium-framed sliding windows (a few with lit shoji behind), a small entrance porch '
         'with a sliding lattice door, an air-conditioner unit and a gas meter on the side wall, downpipes, potted '
         'plants by the door and a low front boundary with a gap for the gate. This variant: ')

VARIANTS = [
    'a gabled house, cream plaster upper floor over weathered dark-brown cedar boards below, a narrow wooden balcony '
    'on the upper floor with a laundry pole and a hanging futon, a grey concrete-block front wall with a tile cap, a '
    'bicycle by the door',
    'a hipped-roof house, pale grey plaster over charcoal-stained boards, a bay of tall sliding windows on the ground '
    'floor, a small persimmon tree in the front plot heavy with orange fruit, a clipped hedge front boundary',
    'a gabled house turned side-on, its gable to the lane, ochre plaster over brown boards, an exterior steel stair to '
    'a side door, washing on a line under the eaves, a weathered wooden board fence front boundary, a small kei-car '
    'parking space of gravel',
    'a boxy later house clad in blue-grey corrugated metal on the upper floor and white plaster below, a flat-roofed '
    'porch, a balcony with a laundry pole and colourful washing, potted plants on a step stand, a low concrete-block '
    'wall with a few decorative openings',
]


def prompt_for(n):
    return STYLE + VARIANTS[n] + '.'


def concept(n, dry):
    from atelier.ai.ledger import run_once
    folder = OUT / str(n); record = folder / 'concept.json'; prompt = prompt_for(n)
    if dry:
        print(f'--- house {n}{" (recorded)" if record.exists() else ""}\n{prompt}\n'); return n, None
    if record.exists(): return n, None
    folder.mkdir(parents=True, exist_ok=True); t = time.time()

    def generate():
        png, usage = sunburst(prompt, SIZE, images=STYLE_REFS)
        (ORIGINALS / str(n)).mkdir(parents=True, exist_ok=True); (ORIGINALS / str(n) / 'concept.png').write_bytes(png)
        return {'usage': usage, 'concept_sha256': sha(png), 'seconds': round(time.time() - t, 1),
                'compact_copy': compact(png, folder / 'concept.jpg', 'concepts')}
    try:
        run_once(record, {'model': MODEL, 'quality': QUALITY, 'size': SIZE, 'endpoint': '/v1/images/edits',
                          'prompt': prompt, 'references': {rel(p): sha(p.read_bytes()) for p in STYLE_REFS},
                          'execution': 'games/yorimichi/tools/hidamari_houses.py',
                          'purpose': 'Hidamari back-lane house concept for the building kit'}, generate)
    except Exception as e:  # noqa: BLE001 - kept by the ledger as submission_uncertain; never retried here
        print('house', n, 'FAILED', type(e).__name__, flush=True); return n, type(e).__name__
    print('house', n, f'ok {time.time() - t:.0f}s', flush=True)
    return n, None


def sheet():
    return contact_sheet([(OUT / str(n) / 'concept.jpg', f'house {n}') for n in range(len(VARIANTS))],
                         yori.REVIEW / 'hidamari' / 'houses-sheet.jpg', 576, 384, 2)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('stage', choices=['concept', 'sheet'])
    ap.add_argument('--only', default=''); ap.add_argument('--dry-run', action='store_true')
    a = ap.parse_args()
    if a.stage == 'sheet': return sheet()
    ns = [n for n in range(len(VARIANTS)) if not a.only or str(n) in a.only.split(',')]
    if not a.dry_run:
        from atelier.env import require
        require('OPENAI_API_KEY')   # loads the ignored .env; never prints the value
    with ThreadPoolExecutor(1 if a.dry_run else 4) as ex:
        results = list(ex.map(lambda n: concept(n, a.dry_run), ns))
    bad = [(n, e) for n, e in results if e]
    for n, e in bad: print('FAILED house', n, e)
    if not a.dry_run: sheet()
    raise SystemExit(1 if bad else 0)


if __name__ == '__main__':
    main()
