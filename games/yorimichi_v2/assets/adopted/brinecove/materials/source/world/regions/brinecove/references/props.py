#!/usr/bin/env python3
"""Paint isolated Brinecove hero props for the local TRELLIS.2 workflow.

    uv run python games/yorimichi/world/regions/brinecove/references/props.py

Each reference is one complete object on a pure black background so the
documented local matte (border-connected near-black) can remove it cleanly.
Every paid call is recorded by atelier.ai.ledger before submission.
"""
import argparse
import hashlib
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
import yori  # noqa: E402,F401
from brinecove.paths import REFERENCES, REPO  # noqa: E402

OUT = REFERENCES / 'props'

MODEL = 'gpt-image-2.5-sunburst'
QUALITY = 'high'
SIZE = '1024x1024'

STYLE = (
    'A single game asset concept painting for Brinecove, a warm hand-painted pirate port in the style of a '
    'storybook watercolour: ochre, rust, cream, weathered teal and dark timber. One object only, centred and '
    'complete with its whole silhouette inside the frame, three-quarter view, isolated on a pure black '
    'background. Soft even studio light with a faint warm rim, no cast shadow, no ground plane, no other '
    'objects, no text, no labels, no border. Weathered, lived-in materials with readable chunky shapes. The '
    'object: '
)

PROPS = {
    'pirate-queen-statue': (
        'a weathered pale limestone statue of a pirate queen in a tricorn hat and long coat, one arm raised '
        'holding a cutlass, the other hand on her hip, standing on a small rough stone plinth, full figure'),
    'galleon-figurehead': (
        'a carved wooden galleon figurehead of a sea siren with long flowing hair and outstretched arms, '
        'faded cream and dark red paint, complete carved object'),
    'harbor-cannon': (
        'a heavy black iron cannon on a dark oak carriage with four wooden wheels and iron bands, side '
        'three-quarter view, complete object'),
    'ship-anchor': (
        'a massive rusty iron ship anchor with a curved stock and a thick coiled hemp rope around its shank, '
        'complete object'),
    'harbor-capstan': (
        'a stout weathered wooden capstan with eight radiating handspikes and three iron bands, complete object'),
    'ships-wheel': (
        'a weathered wooden ship\'s wheel with eight turned spokes, a brass hub and iron rim bands, complete object'),
}


def key():
    from atelier.env import load
    load()
    import os
    value = os.environ.get('OPENAI_API_KEY')
    if not value:
        raise SystemExit('OPENAI_API_KEY is not set')
    return value


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def paint_one(slug):
    from atelier.ai import images, ledger
    prompt = STYLE + PROPS[slug] + '.'
    OUT.mkdir(parents=True, exist_ok=True)
    target = OUT / f'{slug}.png'
    record = OUT / f'{slug}.provenance.json'
    prompt_file = OUT / f'{slug}.prompt.txt'
    prompt_file.write_text(prompt + '\n')
    if record.exists():
        data = json.loads(record.read_text())
        if data.get('status') == 'done' and target.exists():
            return slug, str(target), None
        return slug, None, 'already recorded; set the record aside to pay again'

    def call():
        blobs, body, seconds = images.sunburst(prompt, SIZE, [], 1, model=MODEL, quality=QUALITY, key=key())
        target.write_bytes(blobs[0])
        return dict(elapsed_seconds=seconds, output=target.name, output_sha256=sha(target), usage=body.get('usage'))

    prov, error = ledger.try_once(record, dict(
        stage='brinecove-trellis-reference', prop=slug, requested_model=MODEL, quality=QUALITY, size=SIZE,
        endpoint='/v1/images/generations', execution='games/yorimichi/world/regions/brinecove/references/props.py',
        prompt_file=prompt_file.name, prompt_sha256=hashlib.sha256(prompt.encode()).hexdigest()), call)
    return slug, str(target) if prov else None, error


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--only', default='')
    ap.add_argument('--jobs', type=int, default=3)
    args = ap.parse_args()
    key()
    slugs = [s for s in args.only.split(',') if s] or list(PROPS)
    with ThreadPoolExecutor(max_workers=max(1, args.jobs)) as pool:
        for slug, path, error in pool.map(paint_one, slugs):
            suffix = f' ({error})' if error else ''
            print(f'{slug}: {path or "not painted"}{suffix}', flush=True)


if __name__ == '__main__':
    main()
