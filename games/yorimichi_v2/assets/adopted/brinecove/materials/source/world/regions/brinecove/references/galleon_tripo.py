#!/usr/bin/env python3
"""A Tripo hero hull for the Brinecove galleons: Sunburst multiview set, review approval, one P2 generation.

    uv run python games/yorimichi/world/regions/brinecove/references/galleon_tripo.py paint
    uv run python games/yorimichi/world/regions/brinecove/references/galleon_tripo.py approve --note "..."
    uv run python -m atelier.ai.tripo_asset generate --faces 25000 \\
        --references build/yorimichi/brinecove-review/tripo/galleon/views-r1 \\
        --output build/yorimichi/brinecove-review/tripo/galleon/model-r2

The hull is the part of a galleon procedural lofting cannot carve: the stern castle, galleries, gunports, carved
rails and gilding. Masts, yards, sails and rigging stay procedural (modules.ship), so the views show the hull with
short mast stumps only; thin rigging would only become noise in a reconstructed mesh. Every paid call is recorded by
atelier.ai.ledger before submission; the images stay in the ignored build tree.
"""
import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
import yori  # noqa: E402,F401
from brinecove.paths import REPO, REVIEW  # noqa: E402

OUT = REVIEW / 'tripo/galleon/views-r1'
MODEL = 'gpt-image-2.5-sunburst'
SIZE = '1024x1024'

SHIP = (
    'A single stylised pirate galleon HULL for a hand-painted 3D game, as a clean product turnaround reference for '
    '3D reconstruction. Chunky, slightly toy-like proportions: a deep curved hull of dark weathered oak planks, a '
    'tall stepped stern castle with a two-tier gallery of warm-lit leaded windows and a carved gilded taffrail, a '
    'raised forecastle, a row of eight square gunports with dark red lids and black cannon muzzles on each side, '
    'gilded rails and wales, ochre and teal painted bands along the upper hull, a beakhead with a bowsprit stub and '
    'a carved mermaid figurehead. Three SHORT mast stumps only, cut off just above the deck: NO sails, NO yards, '
    'NO rigging, NO ropes, NO flags. Matte, evenly lit from the front, soft ambient light, no cast shadow, no water, '
    'no waves, no ground. Plain pure white background, the whole hull centred with margin on every side. '
)
FIRST = 'View: exact LEFT side profile (port side), bow pointing to the left of the image, orthographic, keel level.'
VIEWS = {
    'front': 'View: exact FRONT, bow-on, looking straight at the figurehead and beakhead, orthographic, keel level.',
    'back': 'View: exact BACK, looking straight at the stern castle galleries and taffrail, orthographic, keel level.',
    'right': 'View: exact RIGHT side profile (starboard side), bow pointing to the right of the image, orthographic, '
             'keel level, the mirror counterpart of the input left view.',
}
SAME = ('Input image: the approved LEFT view of this exact galleon hull. It is the sole authority for shape, '
        'proportions, colours, carvings, window and gunport counts. Show the same hull from another side; change '
        'nothing else. ')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def paint_one(name, prompt, refs):
    from atelier.ai import images, ledger
    OUT.mkdir(parents=True, exist_ok=True)
    target = OUT / f'{name}.png'
    prompt_file = OUT / f'{name}.prompt.txt'
    prompt_file.write_text(prompt + '\n')
    record = OUT / f'{name}.provenance.json'
    if record.exists() and json.loads(record.read_text()).get('status') == 'done' and target.exists():
        return target

    def call():
        blobs, body, seconds = images.sunburst(prompt, SIZE, [str(p) for p in refs], 1, model=MODEL, quality='high')
        target.write_bytes(blobs[0])
        return dict(elapsed_seconds=seconds, outputs={target.name: sha(target)}, usage=body.get('usage'))

    prov, error = ledger.try_once(record, dict(
        stage='brinecove-galleon-views', view=name, requested_model=MODEL, quality='high', size=SIZE,
        endpoint='/v1/images/edits' if refs else '/v1/images/generations',
        execution='games/yorimichi/world/regions/brinecove/references/galleon_tripo.py paint',
        prompt_file=prompt_file.name, prompt_sha256=hashlib.sha256(prompt.encode()).hexdigest(),
        reference_files={p.name: sha(p) for p in refs}), call)
    if not prov:
        raise SystemExit(f'{name}: {error}')
    return target


def paint():
    from concurrent.futures import ThreadPoolExecutor
    left = paint_one('left', SHIP + FIRST, [])
    print('left', left, flush=True)
    with ThreadPoolExecutor(3) as pool:
        for path in pool.map(lambda kv: paint_one(kv[0], SAME + SHIP + kv[1], [left]), VIEWS.items()):
            print(path.stem, path, flush=True)
    sheet()


def sheet():
    from PIL import Image
    tiles = [Image.open(OUT / f'{v}.png').convert('RGB').resize((512, 512)) for v in ('front', 'left', 'back', 'right')]
    out = Image.new('RGB', (2048, 512), 'white')
    for i, tile in enumerate(tiles):
        out.paste(tile, (i * 512, 0))
    out.save(OUT / 'contact-sheet.jpg', quality=88)
    print('sheet', OUT / 'contact-sheet.jpg')


def approve(note):
    images = {f'{v}.png': sha(OUT / f'{v}.png') for v in ('front', 'left', 'back', 'right')}
    (OUT / 'approval.json').write_text(json.dumps(dict(
        event='multiview_set_approved_for_tripo_generation', images=images, note=note,
        recorded_at=datetime.now(timezone.utc).isoformat()), indent=2) + '\n')
    print('approved', OUT / 'approval.json')


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest='command', required=True)
    sub.add_parser('paint')
    sub.add_parser('sheet')
    a = sub.add_parser('approve')
    a.add_argument('--note', required=True)
    args = ap.parse_args()
    if args.command == 'paint':
        paint()
    elif args.command == 'sheet':
        sheet()
    else:
        approve(args.note)
