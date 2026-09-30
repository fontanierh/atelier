#!/usr/bin/env python3
"""Concept paintings for the south-west island on Sunburst, steered by stills of the game.

    uv run python games/yorimichi/tools/island_concepts.py [--only far] [--dry-run]

Three views of one redesigned island: `far` repaints the island and the sea in a player's still from a hilltop in the
square, then `boat` (from the dinghy off the landing cove) and `aerial` (the whole footprint) are painted with `far`
as their reference, so the three show the same island. Writes <slug>.jpg (the committed copy), <slug>.prompt.txt and
<slug>.provenance.json into games/yorimichi/assets/southwest/concepts/; the full-size PNG goes to
build/yorimichi/southwest/originals/concepts/. Model gpt-image-2.5-sunburst, quality high, 1536x1024, through
/v1/images/edits.

Every paid call is recorded before it is sent: the provenance file is written with status `submitted` first and
completed (or marked failed) afterwards. A view that has a provenance file is never sent again, whatever its status;
rename its files to <slug>.rejected-N.* to paint it again. The stills (not in git) are looked for in
build/yorimichi/southwest/stills/: hilltop-island.png (a player's screenshot of the island from a hilltop in the square)
and crow-sea.png (the tree house crow's nest capture looking at the sea and the island). The key comes from
OPENAI_API_KEY (or the ignored .env).
"""
import sys as _sys; from pathlib import Path as _Path; _sys.path.insert(0, str(_Path(__file__).resolve().parents[1] / 'world')); import yori  # noqa: E402
_sys.path.insert(0, str(_Path(__file__).resolve().parent))
import argparse, json, sys, time
from datetime import datetime, timezone

from treehouse_art import MODEL, QUALITY, compact, redact, rel, sha, sunburst

OUT = yori.ASSETS / 'southwest' / 'concepts'
ORIGINALS = yori.OUT / 'southwest' / 'originals' / 'concepts'
STILLS = yori.OUT / 'southwest' / 'stills'
SIZE = '1536x1024'

REFS = {
    'hilltop': (STILLS / 'hilltop-island.png', 'a real screenshot of the game from a hilltop on the mainland, looking '
                'south over the autumn forest at the island as it is now (an ugly steep flat-topped lump) and the sea'),
    'crow': (STILLS / 'crow-sea.png', 'another real screenshot of the game, from a lookout on the west hillside of the '
             'mainland, looking at the same island and sea'),
    'far': (OUT / 'far.jpg', 'the approved concept of the redesigned island seen from the mainland hilltop: keep this '
            'exact island design (its silhouette, cliffs, headlands, cove, forest colours, torii and temple)'),
}

STYLE = (
    'Concept art for Yorimichi, a stylised low-poly Japanese autumn exploration game. The numbered images are given '
    'for reference: match the game\'s art direction exactly. Simple low-poly shapes with flat colours and soft '
    'painterly shading; the same autumn trees (vermilion and orange maples, golden ginkgo, deep teal-green cedars and '
    'pines with dark trunks), the same soft blue sky and gentle afternoon light. It must look like a polished, '
    'achievable game scene built from simple meshes: not photoreal, and not an elaborate illustration that could not '
    'be modelled.'
)

ISLAND = (
    'THE ISLAND: a small wooded island about 300 m across and 130 m high, half a kilometre offshore, reached by a '
    'small sailing dinghy. On its north face (the side toward the viewer and the mainland beach) a stone stairway '
    'zigzags up from a small pale sand cove, through five vermilion torii gates with stone lanterns, to a modest '
    'temple on a small stone terrace near the top: one hall with a wide sweeping dark indigo hip roof, vermilion '
    'columns and cream plaster. Redesign the island as a believable, beautiful Japanese island, like Chikubu-shima or '
    'the small islands of the Seto Inland Sea: a varied, asymmetric silhouette with one higher rounded wooded '
    'shoulder, a lower saddle, and two lower rocky headlands reaching into the sea on either side of the cove. Steep '
    'grey-brown rock cliffs broken by ledges and mossy shelves along the shore, fallen boulders and one or two small '
    'sea stacks at their feet, a soft line of white surf. Gnarled Japanese black pines lean out over the rocks on the '
    'headlands and cliff tops. The forest is mixed and patchy, never a uniform carpet: dark green pine and cedar '
    'masses, drifts of red and orange maples and golden ginkgo in the hollows and on the upper slopes, a few open '
    'grassy glades. The temple roof and a vermilion torii read clearly as landmarks. No flat top, no mesa, no '
    'straight vertical walls.'
)

SEA = (
    'THE SEA: calm, deep blue-teal near the shores, lighter with distance, fading smoothly into a pale hazy horizon '
    'that melts into the sky. No hard bands, no straight edges, patches or seams anywhere on the water.'
)

AVOID = ('No photorealism, no text, labels, borders or collage panels, no extra buildings, villages or boats besides '
         'those described, no other people.')

VIEWS = {
    'far': (['hilltop', 'crow'],
        'VIEW: exactly the camera and framing of Image 1: the child standing on the grassy hilltop in the foreground '
        'and the autumn trees around him stay as they are. Replace only the island and the sea behind them with the '
        'redesigned island and a sea that fades into the horizon haze. The island sits in the same place and at the '
        'same size in the frame.'),
    'boat': (['far', 'hilltop'],
        'VIEW: from the sailing dinghy about 120 m off the island\'s north shore, the child in a yellow t-shirt at the '
        'tiller small in the lower left foreground with the cream sail. Looking at the landing cove: a small pale sand '
        'beach between the two rocky headlands, a few flat stone landing steps, the first torii at the foot of the '
        'stair, the stairway zigzagging up the wooded face past more torii and lanterns, and the temple roof at the '
        'top. Pines lean over the rocks of the headlands on both sides.'),
    'aerial': (['far', 'crow'],
        'VIEW: a high three-quarter aerial view from the north-east, about 400 m away, showing the whole island and '
        'its outline on the sea: the cove and beach on the north side, the two headlands, the higher shoulder and the '
        'saddle, the zigzag of the stair with its torii, the temple terrace near the top. A clear, readable layout '
        'that could be built as a terrain heightfield.'),
}
ORDER = ('far', 'boat', 'aerial')     # boat and aerial take far as their reference


def prompt_of(view):
    refs, text = VIEWS[view]
    numbered = ' '.join(f'Image {i + 1} is {REFS[r][1]}.' for i, r in enumerate(refs))
    return '\n\n'.join([STYLE + ' ' + numbered, ISLAND, SEA, text, AVOID])


def now():
    return datetime.now(timezone.utc).isoformat()


def run(view):
    refs, _ = VIEWS[view]
    prompt = prompt_of(view)
    (OUT / f'{view}.prompt.txt').write_text(prompt + '\n')
    paths = [REFS[r][0] for r in refs]
    record = dict(stage='southwest-island-concept', concept=view, status='submitted', requested_model=MODEL,
                  quality=QUALITY, size=SIZE, endpoint='/v1/images/edits',
                  execution='games/yorimichi/tools/island_concepts.py', prompt_file=f'{view}.prompt.txt',
                  prompt_sha256=sha(prompt.encode()), reference_files={rel(p): sha(p.read_bytes()) for p in paths},
                  started_at=now())
    ledger = OUT / f'{view}.provenance.json'
    ledger.write_text(json.dumps(record, indent=2) + '\n')          # recorded before the paid call
    t = time.time()
    try:
        png, usage = sunburst(prompt, SIZE, paths)
        ORIGINALS.mkdir(parents=True, exist_ok=True); (ORIGINALS / f'{view}.png').write_bytes(png)
        record.update(status='done', usage=usage, outputs={f'{view}.png': sha(png)},
                      compact_copy=compact(png, OUT / f'{view}.jpg', 'concepts'), error=None)
    except Exception as e:  # noqa: BLE001 - recorded, never retried
        record.update(status='failed', error=redact(e)[:600])
    record.update(finished_at=now(), elapsed_seconds=round(time.time() - t, 1),
                  hashes='of the files as the API saw and returned them; the full-size original is kept outside the '
                         'repository')
    ledger.write_text(json.dumps(record, indent=2) + '\n')
    return record


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--only', default='', help='comma-separated views (far, boat, aerial)')
    ap.add_argument('--dry-run', action='store_true', help='print the prompts and stop')
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    wanted = [v for v in ORDER if not args.only or v in args.only.split(',')]
    if args.dry_run:
        for v in wanted:
            print(f'--- {v} {VIEWS[v][0]}{" (recorded, skipped)" if (OUT / f"{v}.provenance.json").exists() else ""}'
                  f'\n{prompt_of(v)}\n')
        return
    todo = [v for v in wanted if not (OUT / f'{v}.provenance.json').exists()]
    from atelier.env import require
    if todo:
        require('OPENAI_API_KEY')   # loads the ignored .env; stops with a clear message, never prints the value
    for v in todo:
        missing = [rel(REFS[r][0]) for r in VIEWS[v][0] if not REFS[r][0].exists()]
        if missing:
            sys.exit(f'{v}: missing references {missing}')
        record = run(v)
        print(f'{v}: {record["status"]}{" " + record["error"] if record.get("error") else ""} '
              f'({record["elapsed_seconds"]} s)', flush=True)
        if record['status'] != 'done':
            sys.exit('stopped: a failed call is not retried')


if __name__ == '__main__':
    main()
