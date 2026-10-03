"""Author Sunset Pier's Sunburst surfaces, then finish repeatable game texture maps.

    uv run python games/yorimichi/tools/pier_textures.py paint
    uv run python games/yorimichi/tools/pier_textures.py finish

Paid images are recorded by atelier.ai.ledger and never resubmitted. Chosen compact
sources and provenance live in assets/skatepark/textures; full PNGs and finished
albedo, roughness and normal maps live in build/yorimichi/skatepark/textures.
"""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
from PIL import Image

from treehouse_art import MODEL, QUALITY, compact, sunburst
from atelier.ai.ledger import run_once
from atelier.paths import build_dir

GAME = Path(__file__).resolve().parents[1]
ART = GAME / 'assets/skatepark/textures'
OUT = build_dir('yorimichi') / 'skatepark/textures'
SURFACES = {
    'concrete': ('warm pale grey skate plaza concrete, finely burnished with tiny exposed aggregate, subtle '
                 'trowel arcs and understated scuffs from skateboard wheels, excellent nuanced material detail '
                 'without large cracks or dirt blotches', 3.0, .82, .16),
    'ceramic': ('small glazed Japanese ceramic mosaic tiles in muted sea-glass sage and pale jade, regular '
                'square grid with narrow cream grout, each tile subtly varied and hand glazed, restrained '
                'crazing and gentle salt weathering, no broken tiles', 1.2, .48, .30),
    'steel': ('polished stainless steel worn by skateboard trucks, fine lengthwise brushing and scratches, '
              'very subtle warm patina at the edges, clean silver steel without rust holes', 1.0, .28, .11),
    'wood': ('beautiful weathered Japanese cedar timber, long straight grain, fine pores and small knots, '
             'warm honey brown with softly bleached salt-air fibres, grain runs vertically', 2.0, .76, .24),
}
BASE = ('A production-quality seamless tileable game material albedo texture, completely flat orthographic '
        'view of the surface, edge to edge with identical scale everywhere. Painterly realism for a beautiful '
        'stylised Japanese coastal adventure game: tactile, finely observed materials with soft hand-painted '
        'microdetail. Uniform diffuse lighting, no cast shadows, no specular highlights, no perspective, no '
        'objects, no text, no border. Seamless in both directions. The surface is ')
MURAL = ('Paint a spectacular panoramic skateboard plaza mural: a curling Japanese indigo ocean wave with '
         'a vermilion koi jumping through it, a golden setting sun and windblown maple leaves. Original '
         'woodblock-inspired contemporary skate art, powerful sweeping composition, bone cream, indigo, '
         'vermilion and ochre, intricate ink strokes and subtly distressed silkscreen texture. Flat artwork '
         'edge to edge, no frame, no perspective, no lighting, no lettering, no logos. This will be printed '
         'on the wall behind a street skating line in a warm Japanese seaside game.')


def paint():
    ART.mkdir(parents=True, exist_ok=True); OUT.mkdir(parents=True, exist_ok=True)
    for name in (*SURFACES, 'mural'):
        ledger = ART / f'{name}.json'
        if ledger.exists():
            print(name, 'record exists; not resubmitting', flush=True); continue
        prompt = MURAL if name == 'mural' else BASE + SURFACES[name][0]
        size = '1536x1024' if name == 'mural' else '1024x1024'
        def generate():
            png, usage = sunburst(prompt, size)
            (OUT / f'{name}-original.png').write_bytes(png)
            record = compact(png, ART / f'{name}.jpg', 'textures' if name != 'mural' else 'concepts')
            return {'usage': usage, 'png_sha256': hashlib.sha256(png).hexdigest(), 'output': record}
        run_once(ledger, {'model': MODEL, 'quality': QUALITY, 'size': size, 'prompt': prompt,
                         'purpose': 'Sunset Pier material' if name != 'mural' else 'Sunset Pier wave wall'}, generate)
        print(name, 'saved', flush=True)


def linear(a):
    return np.where(a <= .04045, a / 12.92, ((a + .055) / 1.055) ** 2.4)


def srgb(a):
    return np.where(a <= .0031308, a * 12.92, 1.055 * np.maximum(a, 0) ** (1 / 2.4) - .055)


def seamless(a):
    """Periodic-plus-smooth decomposition removes the boundary discontinuity."""
    h, w = a.shape[:2]; v = np.zeros_like(a)
    v[0] = a[-1] - a[0]; v[-1] = -v[0]
    v[:, 0] += a[:, -1] - a[:, 0]; v[:, -1] -= a[:, -1] - a[:, 0]
    yy, xx = np.meshgrid(np.arange(h), np.arange(w), indexing='ij')
    d = 2 * np.cos(2 * np.pi * xx / w) + 2 * np.cos(2 * np.pi * yy / h) - 4
    d[0, 0] = 1
    f = np.fft.fft2(v, axes=(0, 1)) / d[..., None]; f[0, 0] = 0
    return a - np.fft.ifft2(f, axes=(0, 1)).real


def save(path, a):
    Image.fromarray(np.uint8(np.clip(a, 0, 1) * 255 + .5)).save(path)


def finish():
    OUT.mkdir(parents=True, exist_ok=True)
    specs = {**SURFACES, 'basalt': ('', 2., .88, .22)}
    manifest = {}
    for name, (_, repeat, rough, strength) in specs.items():
        source = GAME / 'assets/megapark/restyle/stone_cut.jpg' if name == 'basalt' else ART / f'{name}.jpg'
        if not source.exists(): raise FileNotFoundError(source)
        a = linear(np.asarray(Image.open(source).convert('RGB').resize((1024, 1024)), float) / 255)
        a = seamless(a)
        # Vertex colours supply the final palette and AO; detail maps have mean .5 linear.
        a = np.clip(a / np.maximum(a.mean((0, 1)), .01) * .5, .03, .95)
        save(OUT / f'{name}-albedo.png', srgb(a))
        height = a.mean(2)
        dx = (np.roll(height, -1, 1) - np.roll(height, 1, 1)) * strength
        dy = (np.roll(height, -1, 0) - np.roll(height, 1, 0)) * strength
        normal = np.stack([-dx, dy, np.ones_like(dx)], 2)
        normal /= np.linalg.norm(normal, axis=2, keepdims=True)
        save(OUT / f'{name}-normal.png', normal * .5 + .5)
        save(OUT / f'{name}-roughness.png', np.clip(rough + (height - .5) * .24, .16, .98))
        manifest[name] = {'repeat_m': repeat, 'metallic': 1. if name == 'steel' else 0.,
                          'source': source.relative_to(GAME).as_posix(),
                          'maps': {role: f'{name}-{role}.png' for role in ('albedo', 'normal', 'roughness')}}
    mural = ART / 'mural.jpg'
    if not mural.exists(): raise FileNotFoundError(mural)
    Image.open(mural).save(OUT / 'mural-albedo.png')
    manifest['mural'] = {'repeat_m': 1., 'metallic': 0., 'maps': {'albedo': 'mural-albedo.png'}}
    for entry in manifest.values():
        entry['sha256'] = {role: hashlib.sha256((OUT / file).read_bytes()).hexdigest() for role, file in entry['maps'].items()}
    (OUT / 'textures.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print('PIER TEXTURES COMPLETE', ', '.join(manifest), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument('mode', choices=('paint', 'finish'))
    args = parser.parse_args(); paint() if args.mode == 'paint' else finish()
