"""Procedural timber textures for the gondola pieces (numpy only; deterministic, no paid generation).

Each texture tiles over 1 m x 1 m (the meshes carry UVs in metres, with u along the grain of each part). Planked
textures run planks along u with dark seams between rows and staggered butt joints; grain textures have the same
figure without seams, for posts, frames and boards that are separate pieces in the mesh. A roughness map
(matte, with slight variation along the grain) goes with each.
"""
import math

import numpy as np

SIZE = 1024
# name -> (plank width in metres or None, base sRGB, late-wood sRGB, seed)
SPECS = {
    'wood_panel': (0.10, (226, 174, 108), (184, 128, 70), 11),
    'wood_grain': (None, (224, 170, 104), (182, 124, 68), 23),
    'wood_grain_light': (None, (236, 190, 128), (198, 146, 88), 37),
    'wood_grain_dark': (None, (104, 68, 44), (66, 42, 28), 41),
    'deck_planks': (0.125, (212, 160, 102), (162, 112, 66), 53),
    'shingle': (0.18, (204, 146, 86), (150, 98, 54), 67),
}


def periodic_noise(n, rng, terms=6, lo=1, hi=9):
    """A smooth 1D function, periodic over n samples."""
    x = np.arange(n) / n; f = np.zeros(n)
    for _ in range(terms):
        k = rng.integers(lo, hi); f += rng.normal() / k * np.sin(2 * math.pi * (k * x + rng.random()))
    return f / (np.abs(f).max() + 1e-9)


def wood(name):
    plank, base, dark, seed = SPECS[name]
    rng = np.random.default_rng(seed); n = SIZE
    u = np.arange(n)[None, :].repeat(n, 0) / n; v = np.arange(n)[:, None].repeat(n, 1) / n
    rows = max(1, round(1 / plank)) if plank else 6
    pw = 1.0 / rows; r = np.minimum((v / pw).astype(int), rows - 1); vl = v - r * pw
    # Grain: fine lines along u, wandering with low-frequency noise in u; ring spacing varies per plank.
    wander = np.stack([periodic_noise(n, rng) for _ in range(rows)])          # rows x n
    wander2 = np.stack([periodic_noise(n, rng, 8, 6, 30) for _ in range(rows)])
    freq = rng.uniform(70, 110, rows); phase = rng.random(rows)
    t = vl * freq[r] + 1.6 * wander[r, (u * n).astype(int)] + 0.25 * wander2[r, (u * n).astype(int)] + phase[r]
    ring = 0.5 + 0.5 * np.sin(2 * math.pi * t)
    ring = ring ** 3                                                            # thin late-wood lines
    speck = rng.normal(0, 1, (n, n)) * 0.04
    tint = rng.uniform(-0.07, 0.07, rows)
    a = np.clip(0.45 * ring + 0.12 * (0.5 + 0.5 * wander2[r, (u * n).astype(int)]) + speck, 0, 1)
    b = np.array(base, float) / 255; d = np.array(dark, float) / 255
    col = b[None, None, :] * (1 - a[..., None]) + d[None, None, :] * a[..., None]
    col *= (1 + tint[r])[..., None]
    rough = 0.74 + 0.10 * (a - 0.3)
    if plank:
        px = 1.0 / n
        joints_per_row = 0 if name == 'wood_panel' else 2       # wall panels are full-length boards
        seam = (vl < 2.5 * px) | (vl > pw - 1.0 * px)
        # Staggered butt joints: two per row at random positions.
        joints = np.zeros((n, n), bool)
        for k in range(rows):
            for j in rng.random(joints_per_row):
                c = int(j * n); m = (r == k)
                cols = np.zeros(n, bool); cols[c:c + 3] = True
                joints |= m & cols[None, :]
        line = seam | joints
        col[line] = col[line] * 0.45
        rough[line] = 0.9
        # A soft bevel shade next to each seam.
        near = (vl < 6 * px) & ~seam
        col[near] *= 0.9
    return np.clip(col, 0, 1), np.clip(rough, 0, 1)


def generate(out_dir):
    """Write every texture as PNG via Blender's image API (this runs inside Blender)."""
    import bpy
    out_dir.mkdir(parents=True, exist_ok=True); files = {}
    for name in SPECS:
        col, rough = wood(name)
        for kind, arr in (('color', col), ('rough', rough)):
            rgba = np.ones((SIZE, SIZE, 4), np.float32)
            if arr.ndim == 2:
                rgba[..., 0] = rgba[..., 1] = rgba[..., 2] = arr
            else:
                rgba[..., :3] = arr
            img = bpy.data.images.new(f'{name}_{kind}', SIZE, SIZE, alpha=False)
            img.colorspace_settings.name = 'sRGB' if kind == 'color' else 'Non-Color'
            img.pixels.foreach_set(rgba[::-1].ravel())       # Blender images start at the bottom row
            path = out_dir / f'GD_{name}_{kind}.png'
            img.filepath_raw = str(path); img.file_format = 'PNG'; img.save()
            files[(name, kind)] = path
            bpy.data.images.remove(img)
    return files
