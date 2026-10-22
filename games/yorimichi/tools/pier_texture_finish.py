"""Deterministic offline pier texture finishing; no paid authoring client dependency."""
import hashlib
import json
from pathlib import Path

import numpy as np
from PIL import Image
from atelier.paths import build_dir

GAME = Path(__file__).resolve().parents[1]
ART = GAME / 'assets/skatepark/textures'
OUT = build_dir('yorimichi') / 'skatepark/textures'
SURFACES = {
    'concrete': (3.0, 0.82, 0.16),
    'ceramic': (1.2, 0.48, 0.30),
    'steel': (1.0, 0.28, 0.11),
    'wood': (2.0, 0.76, 0.24),
}


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
    """@cc [owner:fontanierh,label:correctness] offline-pier-material-finishing
    Normal finishing MUST consume committed chosen images and deterministic surface settings without
    importing paid authoring clients or submitting paid requests. Its complete helper/source closure
    and every generated texture MUST enter the ordinary portable product identity.
    """
    OUT.mkdir(parents=True, exist_ok=True)
    specs = {**SURFACES, 'basalt': (2., .88, .22)}
    manifest = {}
    for name, (repeat, rough, strength) in specs.items():
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
    finish()
