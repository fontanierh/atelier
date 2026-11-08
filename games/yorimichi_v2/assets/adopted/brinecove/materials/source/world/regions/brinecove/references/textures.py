#!/usr/bin/env python3
"""Paint and finish the Brinecove tileable surface set with gpt-image-2.5-sunburst.

    uv run python games/yorimichi/world/regions/brinecove/references/textures.py paint
    uv run python games/yorimichi/world/regions/brinecove/references/textures.py finish

Every paid call is recorded before submission by atelier.ai.ledger.  The raw
1024 px PNGs stay in build/yorimichi/brinecove-review/textures/originals; the
committed copies are seamless 768 px JPEGs tinted to the Brinecove palette in
the proposal's textures/ directory.
"""
import argparse
import hashlib
import json
import math
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
import yori  # noqa: E402,F401

from brinecove import layout as L  # noqa: E402
from brinecove import surfaces as S  # noqa: E402
from brinecove.paths import REPO, REVIEW, TEXTURES  # noqa: E402

MODEL = 'gpt-image-2.5-sunburst'
QUALITY = 'high'
SIZE = '1024x1024'
OUT = REVIEW / 'textures' / 'originals'

STYLE = (
    'A seamless tileable material texture for a stylised hand-painted pirate-port game, seen perfectly '
    'flat and straight-on filling the whole square edge to edge. Match the warm storybook painting of the '
    'Brinecove Sunburst references: ochre, rust, cream, sage, weathered teal and turquoise. Soft painterly '
    'strokes, readable medium detail, matte, even diffuse lighting, no directional shadow, no vignette, '
    'no perspective, no border, no object outline, no text or labels. The surface: '
)


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


def paint_one(slug, n=1):
    from atelier.ai import images, ledger
    base = S.SURFACES[slug]
    prompt = STYLE + base['prompt'] + '.'
    target = OUT / f'{slug}.png'
    record = OUT / f'{slug}.provenance.json'
    prompt_file = OUT / f'{slug}.prompt.txt'
    OUT.mkdir(parents=True, exist_ok=True)
    prompt_file.write_text(prompt + '\n')
    if record.exists():
        data = json.loads(record.read_text())
        if data.get('status') == 'done' and target.exists():
            return slug, str(target), None
        return slug, None, 'already recorded; set the record aside to pay again'

    def call():
        blobs, body, seconds = images.sunburst(prompt, SIZE, [], n, model=MODEL, quality=QUALITY, key=key())
        paths = []
        for i, blob in enumerate(blobs):
            path = target if n == 1 else OUT / f'{slug}-{i + 1}.png'
            path.write_bytes(blob)
            paths.append(path)
        return dict(elapsed_seconds=seconds, outputs={p.name: sha(p) for p in paths}, usage=body.get('usage'))

    prov, error = ledger.try_once(record, dict(
        stage='brinecove-texture', surface=slug, requested_model=MODEL, quality=QUALITY, size=SIZE,
        endpoint='/v1/images/generations', execution='games/yorimichi/world/regions/brinecove/references/textures.py',
        prompt_file=prompt_file.name, prompt_sha256=hashlib.sha256(prompt.encode()).hexdigest()), call)
    return slug, str(target) if prov else None, error


def seamless(a, band=.18):
    import numpy as np
    h, w = a.shape[:2]
    rolled = np.roll(a, (h // 2, w // 2), (0, 1))
    y = np.minimum(np.arange(h) + .5, h - np.arange(h) - .5) / h
    x = np.minimum(np.arange(w) + .5, w - np.arange(w) - .5) / w
    smooth = lambda t: np.clip(t / band, 0, 1) ** 2 * (3 - 2 * np.clip(t / band, 0, 1))
    k = np.minimum(smooth(y)[:, None], smooth(x)[None, :])[..., None]
    mean = a.reshape(-1, a.shape[2]).mean(0)
    dev = (a - mean) * k + (rolled - mean) * (1 - k)
    return np.clip(mean + dev / np.sqrt(k ** 2 + (1 - k) ** 2), 0, 1)


def hex_rgb(value):
    import numpy as np
    return np.array([int(value[i:i + 2], 16) / 255.0 for i in (1, 3, 5)])


def colorize(detail, hex_color, contrast=1.0, lift=0.0, keep_chroma=0.0):
    """Keep the painted detail, replace its mean colour with the palette colour."""
    import numpy as np
    lum = detail[..., 0] * .2126 + detail[..., 1] * .7152 + detail[..., 2] * .0722
    mean = max(1e-4, float(lum.mean()))
    factor = np.clip((lum / mean) ** contrast, .35, 2.1)
    target = hex_rgb(hex_color)
    out = target[None, None, :] * factor[..., None] + lift
    if keep_chroma:
        # The painted sources carry mossy teal, ochre and cream patches.  A
        # flat mean replacement threw that variety away and left every wall
        # the same grey-green.  Keep a share of the source chroma around its
        # own mean while the body of the surface takes the palette colour.
        source_mean = detail.mean(axis=(0, 1))
        out = out + (detail - source_mean[None, None, :]) * keep_chroma
    return np.clip(out, 0, 1)


def finish():
    from PIL import Image
    import numpy as np
    TEXTURES.mkdir(parents=True, exist_ok=True)
    raw = {}
    for slug in S.SURFACES:
        source = OUT / f'{slug}.png'
        if not source.exists():
            print(f'missing source {source}', flush=True)
            continue
        image = Image.open(source).convert('RGB')
        if image.width != image.height:
            side = min(image.width, image.height)
            image = image.crop(((image.width - side) // 2, (image.height - side) // 2,
                                (image.width + side) // 2, (image.height + side) // 2))
        image = image.resize((512, 512), Image.LANCZOS)
        raw[slug] = seamless(np.asarray(image).astype(np.float32) / 255.0)
    records = {}
    for material, (slug, scale) in S.MATERIAL_SURFACE.items():
        if slug not in raw:
            continue
        detail = raw[slug]
        if slug == 'water':
            arr = detail
            if material != 'water':
                arr = colorize(detail, L.COLORS.get(material, L.COLORS['sea']), .8, .02)
        else:
            target = L.COLORS.get(material)
            if not target:
                continue
            # Plaster at full contrast read as stained, blotchy walls; the paintings' walls are clean washes.
            contrast = 1.15 if slug in ('foliage', 'roof', 'stone') else (0.7 if slug == 'plaster' else 1.0)
            lift = .025 if slug in ('plaster', 'canvas') else .0
            chroma = {'plaster': .28, 'roof': .48, 'stone': .40, 'cliff': .40, 'sea_rock': .55, 'cliff_block': .6, 'moss_rock': .55,
                      'wood': .30, 'canvas': .26, 'foliage': .40, 'sand': .28}.get(slug, .0)
            arr = colorize(detail, target, contrast, lift, chroma)
        path = TEXTURES / f'{material}.jpg'
        Image.fromarray((np.clip(arr, 0, 1) * 255).astype(np.uint8)).save(path, 'JPEG', quality=92, subsampling=0)
        records[material] = dict(file=path.name, surface=slug, scale=scale, sha256=sha(path))
    manifest = dict(model=MODEL, quality=QUALITY, surface_sha256={k: sha(OUT / f'{k}.png') if (OUT / f'{k}.png').exists() else None
                                                                   for k in S.SURFACES}, materials=records)
    (TEXTURES / 'textures.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print(f'textures: {len(records)} material maps in {TEXTURES}', flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('stage', choices=('paint', 'finish', 'all'), nargs='?', default='all')
    ap.add_argument('--only', default='')
    ap.add_argument('--jobs', type=int, default=3)
    args = ap.parse_args()
    if args.stage in ('paint', 'all'):
        key()
        slugs = [s for s in args.only.split(',') if s] or list(S.SURFACES)
        with ThreadPoolExecutor(max_workers=max(1, args.jobs)) as pool:
            for slug, path, error in pool.map(paint_one, slugs):
                suffix = f' ({error})' if error else ''
                print(f'{slug}: {path or "not painted"}{suffix}', flush=True)
    if args.stage in ('finish', 'all'):
        finish()


if __name__ == '__main__':
    main()
