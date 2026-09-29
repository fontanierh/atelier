"""Procedural sprite textures for the sword-fight effects (AJapanCombatFX, UJapanSwordTrail).

    python games/yorimichi/assets/fx/gen_textures.py      # writes build/yorimichi/combat_fx/T_FX_*.png

Greyscale masks (the materials read the red channel and take colour from per-instance data or vertex colour):
- T_FX_Glow: a soft round glow with a hot core (flashes, embers, the charge glow).
- T_FX_Spark: an elongated streak; the sprite's X axis is stretched along the spark's velocity.
- T_FX_Ring: a thin soft ring for shock waves.
- T_FX_Dust: a noisy soft puff.
- T_FX_Trail: the slash ribbon, U along its length (age), V across (hand side to tip): broken brush streaks that
  are brightest just inside the tip edge, for the painterly look of the rest of the game.
Deterministic (fixed seeds).
"""
from pathlib import Path
import numpy as np
from PIL import Image

import sys as _sys; _sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'world')); import yori  # noqa: E402
OUT = yori.OUT / 'combat_fx'


def save(name, a):
    a = np.clip(a, 0, 1)
    Image.fromarray((a * 255 + .5).astype(np.uint8)).convert('RGB').save(OUT / f'{name}.png')


def grid(w, h=None):
    h = h or w
    y, x = np.mgrid[0:h, 0:w]
    return (x + .5) / w * 2 - 1, (y + .5) / h * 2 - 1


def value_noise(shape, cells, seed):
    rng = np.random.default_rng(seed)
    h, w = shape
    g = rng.random((cells[1] + 1, cells[0] + 1))
    y, x = np.mgrid[0:h, 0:w]
    fx = x / w * cells[0]; fy = y / h * cells[1]
    ix, iy = fx.astype(int), fy.astype(int); tx, ty = fx - ix, fy - iy
    tx = tx * tx * (3 - 2 * tx); ty = ty * ty * (3 - 2 * ty)
    a = g[iy, ix]; b = g[iy, ix + 1]; c = g[iy + 1, ix]; d = g[iy + 1, ix + 1]
    return (a * (1 - tx) + b * tx) * (1 - ty) + (c * (1 - tx) + d * tx) * ty


def fbm(shape, base, seed, octaves=4):
    out = np.zeros(shape); amp = 1.; total = 0.
    for o in range(octaves):
        out += amp * value_noise(shape, (base[0] * 2 ** o, base[1] * 2 ** o), seed + o); total += amp; amp *= .5
    return out / total


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    x, y = grid(128); r = np.hypot(x, y)
    edge = np.clip((1 - r) / .15, 0, 1)                      # every sprite reaches zero before the quad's edge
    save('T_FX_Glow', (np.exp(-(r / .42) ** 2 * 2.2) * .8 + np.exp(-(r / .12) ** 2) * .6) * edge)
    save('T_FX_Spark', np.exp(-(y / .16) ** 2 * 2) * np.exp(-(x / .62) ** 2 * 1.4) * (1 + .6 * np.exp(-(x / .2) ** 2)) / 1.6 * edge)
    save('T_FX_Ring', (np.exp(-((r - .74) / .07) ** 2) + .12 * np.exp(-((r - .6) / .2) ** 2)) * edge)
    n = fbm((128, 128), (4, 4), 7)
    save('T_FX_Dust', np.clip(np.exp(-(r / .55) ** 2 * 1.8) * (.45 + .9 * n) - .05, 0, 1) * edge)
    # Trail: 256 along the length (U), 64 across (V: 0 hand side, 1 tip).
    w, h = 256, 64
    u = (np.arange(w) + .5) / w; v = (np.arange(h) + .5) / h
    U, V = np.meshgrid(u, v)
    across = np.clip(V / .82, 0, 1) ** 1.6 * np.clip((1 - V) / .1, 0, 1) ** .7          # brightest just inside the tip edge
    rng = np.random.default_rng(3)
    lines = np.zeros((h,))
    for _ in range(26):
        c = rng.random(); wdt = rng.uniform(.01, .045); lines += rng.uniform(.35, 1.) * np.exp(-((v - c) / wdt) ** 2)
    lines = .55 + .45 * lines / lines.max()
    breakup = fbm((h, w), (10, 3), 11, 3)
    broken = np.clip(.35 + 1.1 * breakup - .6 * U * (1 - lines[:, None]), 0, 1)
    head = np.clip(U / .04, 0, 1)                                                          # soft start at the blade
    save('T_FX_Trail', across * lines[:, None] * broken * head)
    print('COMBAT FX TEXTURES', sorted(p.name for p in OUT.glob('T_FX_*.png')))


if __name__ == '__main__':
    main()
