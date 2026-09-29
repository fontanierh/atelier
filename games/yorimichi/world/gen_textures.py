import sys as _sys; from pathlib import Path as _Path; _sys.path.insert(0, str(_Path(__file__).resolve().parent)); import yori  # noqa: E402,F401
#!/usr/bin/env python3
"""Painterly textures for the Japan demo (PIL + numpy) -> build/yorimichi/textures/T_*.png|jpg

Every texture is a set of flat, soft-edged brush stamps: nothing photographic.
  T_leaf_broad.png   1024  2x2 atlas of broadleaf canopy clusters (RGBA)
  T_leaf_cedar.png   1024  2x2 atlas of dense dark cedar foliage (RGBA)
  T_leaf_pine.png    1024  2x2 atlas of pine needle fans (RGBA)
  T_leaf_ochre.png   1024  2x2 atlas of yellow/ochre bush clusters (RGBA)
  T_grass.png        1024  2x2 paint palette for curved grass blades (RGBA)
  T_bark.jpg         512   dark trunk with vertical strokes
  T_road.jpg         256x1024  asphalt strip, white edge lines, dashed centre (V along the road)
  T_ground.jpg       1024  painterly meadow ground
  T_sky.png          2048x1024 equirect painted sky with cumulus
  T_water.jpg        512   sea
  T_concrete.jpg     256   pole concrete
"""
import os, math
import numpy as np
from PIL import Image, ImageDraw, ImageFilter

OUT = str(yori.TEXTURES)
os.makedirs(OUT, exist_ok=True)


def rng_for(seed):
    return np.random.default_rng(seed)


def noise(n, scale, octaves=4, seed=0, m=None):
    """Tileable value-noise fBm in [0,1] (n x n or n x m)."""
    r = np.random.default_rng(seed)
    w = m or n
    out = np.zeros((n, w), np.float32)
    amp, tot = 1.0, 0.0
    for o in range(octaves):
        cells = max(2, int(scale * (2 ** o)))
        g = r.random((cells, max(2, int(cells * w / n)))).astype(np.float32)
        big = np.asarray(Image.fromarray((g * 255).astype(np.uint8)).resize((w, n), Image.BICUBIC), np.float32) / 255.0
        out += big * amp; tot += amp; amp *= 0.5
    return out / tot


def save(name, im, q=90):
    p = os.path.join(OUT, name)
    if name.endswith(".png"):
        im.save(p, optimize=True)
    else:
        im.convert("RGB").save(p, quality=q)
    print(name, im.size, f"{os.path.getsize(p) / 1024:.0f} KB")


def col(c, k=1.0, j=0.0, r=None):
    """(r,g,b) in 0..1 -> 8-bit tuple with brightness k and optional random jitter j"""
    if r is not None and j:
        k *= 1.0 + (r.random() * 2 - 1) * j
    return tuple(int(max(0, min(255, v * k * 255))) for v in c)


def ellipse_poly(cx, cy, rx, ry, ang, n=18):
    ca, sa = math.cos(ang), math.sin(ang)
    pts = []
    for i in range(n):
        t = 2 * math.pi * i / n
        x, y = rx * math.cos(t), ry * math.sin(t)
        pts.append((cx + x * ca - y * sa, cy + x * sa + y * ca))
    return pts


def leaf_cluster(cell, r, palette, stamps=140, size=(22, 46), blob_r=0.36, dark_bottom=True, needle=False, layer=None):
    """Paint one cluster into an RGBA layer of size cell x cell."""
    layer = layer or Image.new("RGBA", (cell, cell), (0, 0, 0, 0))
    dr = ImageDraw.Draw(layer)
    c = cell / 2
    # silhouette: union of a few discs
    discs = [(c, c, blob_r * cell)]
    for _ in range(4):
        a = r.random() * 2 * math.pi
        d = r.random() * 0.22 * cell
        discs.append((c + math.cos(a) * d, c + math.sin(a) * d, (0.2 + r.random() * 0.16) * cell))
    def inside(x, y):
        return any((x - dx) ** 2 + (y - dy) ** 2 < dr_ ** 2 for dx, dy, dr_ in discs)
    pts = []
    tries = 0
    while len(pts) < stamps and tries < stamps * 30:
        tries += 1
        x, y = r.random() * cell, r.random() * cell
        if inside(x, y):
            pts.append((x, y))
    pts.sort(key=lambda p: -p[1])           # paint bottom first so top leaves overlap
    base, light, dark = palette
    for (x, y) in pts:
        h = (c - y) / (blob_r * cell)       # -1 bottom .. 1 top
        if needle:
            ang = r.random() * math.pi
            rx, ry = r.uniform(size[1] * 0.7, size[1]), r.uniform(size[0] * 0.35, size[0] * 0.6)
        else:
            ang = r.uniform(-0.9, 0.9) + (math.pi / 2 if r.random() < 0.3 else 0)
            rx, ry = r.uniform(size[0], size[1]), r.uniform(size[0] * 0.5, size[0] * 0.9)
        t = 0.5 + 0.5 * h                   # 0 bottom .. 1 top
        cc = tuple(dark[i] * (1 - t) + base[i] * t for i in range(3))
        k = 1.0 + (r.random() * 2 - 1) * 0.08
        dr.polygon(ellipse_poly(x, y, rx, ry, ang), fill=col(cc, k) + (255,))
        if r.random() < 0.22 + 0.33 * t:     # lit tip toward the upper left (sparser: the mass reads flatter)
            lx, ly = x - rx * 0.28, y - ry * 0.35
            dr.polygon(ellipse_poly(lx, ly, rx * 0.55, ry * 0.5, ang), fill=col(light, k) + (255,))
    return layer


def atlas(name, palettes, seed, **kw):
    cell = 512
    im = Image.new("RGBA", (cell * 2, cell * 2), (0, 0, 0, 0))
    r = rng_for(seed)
    for i in range(4):
        pal = palettes[i % len(palettes)]
        layer = leaf_cluster(cell, r, pal, **kw)
        layer = layer.filter(ImageFilter.GaussianBlur(1.1))
        # crisp-ish alpha after the blur (painted edge, not fuzzy)
        a = np.asarray(layer.getchannel("A")).astype(np.float32) / 255
        a = np.clip((a - 0.35) * 3.0, 0, 1)
        rgb = np.asarray(layer.convert("RGB")).astype(np.uint8)
        layer = Image.fromarray(np.dstack([rgb, (a * 255).astype(np.uint8)]), "RGBA")
        im.paste(layer, ((i % 2) * cell, (i // 2) * cell))
    # bleed colour under the alpha so mip-mapped edges do not go dark
    arr = np.asarray(im).astype(np.float32)
    rgb, a = arr[..., :3], arr[..., 3:4] / 255
    blurred = np.asarray(Image.fromarray(np.dstack([rgb.astype(np.uint8), (a[..., 0] * 255).astype(np.uint8)]).astype(np.uint8), "RGBA").filter(ImageFilter.GaussianBlur(6))).astype(np.float32)
    ba = np.maximum(blurred[..., 3:4], 1.0)
    fill = blurred[..., :3] * 255 / ba
    rgb = np.where(a > 0.02, rgb, fill)
    save(name, Image.fromarray(np.dstack([np.clip(rgb, 0, 255).astype(np.uint8), (a[..., 0] * 255).astype(np.uint8)]), "RGBA"))


def leaves():
    broad = [((0.38, 0.48, 0.22), (0.60, 0.66, 0.32), (0.18, 0.28, 0.12)),
             ((0.35, 0.46, 0.20), (0.56, 0.62, 0.30), (0.16, 0.26, 0.11)),
             ((0.44, 0.50, 0.23), (0.66, 0.68, 0.36), (0.20, 0.29, 0.13))]
    atlas("T_leaf_broad.png", broad, 11, stamps=260, size=(30, 62), blob_r=0.38)
    cedar = [((0.26, 0.40, 0.22), (0.42, 0.54, 0.28), (0.12, 0.22, 0.12)),
             ((0.28, 0.42, 0.23), (0.44, 0.56, 0.29), (0.13, 0.23, 0.13))]
    atlas("T_leaf_cedar.png", cedar, 12, stamps=520, size=(14, 34), blob_r=0.40)
    pine = [((0.19, 0.34, 0.21), (0.34, 0.48, 0.27), (0.08, 0.17, 0.10))]
    atlas("T_leaf_pine.png", pine, 13, stamps=520, size=(6, 64), blob_r=0.44, needle=True)
    ochre = [((0.70, 0.60, 0.28), (0.84, 0.76, 0.44), (0.46, 0.38, 0.16)),
             ((0.66, 0.56, 0.26), (0.80, 0.72, 0.42), (0.44, 0.36, 0.15))]
    atlas("T_leaf_ochre.png", ochre, 14, stamps=240, size=(26, 54), blob_r=0.38)


def leaf_shape(kind, cx, cy, R, ang, r):
    """polygon for one leaf: maple star, ginkgo fan or pointed oval"""
    pts = []
    if kind == "maple":
        for i in range(14):
            t = 2 * math.pi * i / 14
            rr = R * (1.0 if i % 2 == 0 else 0.5) * (1 + 0.08 * math.sin(3 * t))
            pts.append((rr * math.cos(t), rr * math.sin(t)))
    elif kind == "ginkgo":
        for i in range(9):
            t = math.radians(-65 + 130 * i / 8)
            rr = R * (1 + 0.06 * math.sin(i * 2.1)) * (0.85 if i == 4 else 1.0)
            pts.append((rr * math.sin(t), -rr * math.cos(t)))
        pts.append((0, R * 0.25))
    else:
        for i in range(12):
            t = 2 * math.pi * i / 12
            pts.append((R * 0.42 * math.cos(t) * (1 - 0.25 * abs(math.sin(t))), R * math.sin(t)))
    ca, sa = math.cos(ang), math.sin(ang)
    return [(cx + x * ca - y * sa, cy + x * sa + y * ca) for (x, y) in pts]


def small_leaf_atlas(name, kind, palette, seed, per_cell=(3, 6), size=(110, 175)):
    """2x2 atlas of small leaf clusters (RGBA), for the many-small-cards canopies"""
    cell = 512; r = rng_for(seed)
    im = Image.new("RGBA", (cell * 2, cell * 2), (0, 0, 0, 0))
    for c in range(4):
        layer = Image.new("RGBA", (cell, cell), (0, 0, 0, 0)); d = ImageDraw.Draw(layer)
        n = r.integers(per_cell[0], per_cell[1] + 1)
        for i in range(n):
            R = r.uniform(*size); x = r.uniform(cell * 0.25, cell * 0.75); y = r.uniform(cell * 0.25, cell * 0.75)
            ang = r.uniform(0, 2 * math.pi); base = palette[r.integers(len(palette))]
            k = 1 + (r.random() * 2 - 1) * 0.12
            d.polygon(leaf_shape(kind, x, y, R * 1.08, ang, r), fill=col(base, k * 0.84) + (255,))     # dark edge: leaves read against each other
            d.polygon(leaf_shape(kind, x, y, R, ang, r), fill=col(base, k) + (255,))
            d.polygon(leaf_shape(kind, x - R * 0.12, y - R * 0.12, R * 0.55, ang, r), fill=col(base, k * 1.08) + (255,))
        layer = layer.filter(ImageFilter.GaussianBlur(0.8))
        im.paste(layer, ((c % 2) * cell, (c // 2) * cell))
    arr = np.asarray(im).astype(np.float32); a = arr[..., 3:4] / 255
    blurred = np.asarray(im.filter(ImageFilter.GaussianBlur(6))).astype(np.float32)
    fill = blurred[..., :3] * 255 / np.maximum(blurred[..., 3:4], 1.0)
    rgb = np.where(a > 0.02, arr[..., :3], fill)
    save(name, Image.fromarray(np.dstack([np.clip(rgb, 0, 255).astype(np.uint8), (a[..., 0] * 255).astype(np.uint8)]), "RGBA"))


def autumn_lo():
    maple = [((0.82, 0.26, 0.10), (0.96, 0.52, 0.18), (0.50, 0.10, 0.06)), ((0.88, 0.40, 0.12), (0.98, 0.64, 0.22), (0.56, 0.18, 0.07)), ((0.80, 0.34, 0.10), (0.94, 0.56, 0.20), (0.48, 0.14, 0.06))]
    atlas("T_leaf_maple_lo.png", maple, 71, stamps=300, size=(28, 58), blob_r=0.40)
    ginkgo = [((0.90, 0.76, 0.22), (0.98, 0.90, 0.45), (0.62, 0.48, 0.12))]
    atlas("T_leaf_ginkgo_lo.png", ginkgo, 72, stamps=300, size=(26, 54), blob_r=0.40)
    broad = [((0.50, 0.58, 0.24), (0.76, 0.74, 0.36), (0.26, 0.34, 0.14)), ((0.62, 0.56, 0.22), (0.86, 0.78, 0.36), (0.32, 0.30, 0.12))]
    atlas("T_leaf_broad_lo.png", broad, 73, stamps=300, size=(28, 58), blob_r=0.40)


def autumn_leaves():
    autumn_lo()
    small_leaf_atlas("T_leaf_maple.png", "maple", [(0.82, 0.26, 0.12), (0.88, 0.45, 0.12), (0.72, 0.16, 0.10), (0.92, 0.60, 0.16), (0.86, 0.34, 0.10)], 41, per_cell=(7, 12), size=(70, 120))
    small_leaf_atlas("T_leaf_ginkgo.png", "ginkgo", [(0.90, 0.78, 0.30), (0.84, 0.70, 0.24), (0.94, 0.86, 0.44), (0.78, 0.64, 0.22)], 42, per_cell=(7, 12), size=(65, 105))
    small_leaf_atlas("T_leaf_ochre_small.png", "oval", [(0.72, 0.60, 0.26), (0.80, 0.70, 0.34), (0.62, 0.50, 0.20), (0.86, 0.76, 0.40), (0.70, 0.56, 0.22)], 46, per_cell=(9, 14), size=(60, 100))
    small_leaf_atlas("T_leaf_small.png", "oval", [(0.50, 0.56, 0.22), (0.64, 0.62, 0.24), (0.74, 0.60, 0.20), (0.42, 0.50, 0.20), (0.82, 0.56, 0.18)], 43, per_cell=(9, 14), size=(60, 100))
    # litter: leaves lying on the ground, one 512 card
    r = rng_for(44); cell = 512
    layer = Image.new("RGBA", (cell, cell), (0, 0, 0, 0)); d = ImageDraw.Draw(layer)
    pal = [(0.70, 0.30, 0.12), (0.78, 0.48, 0.14), (0.60, 0.22, 0.10), (0.82, 0.62, 0.18), (0.55, 0.40, 0.14)]
    for i in range(26):
        R = r.uniform(28, 48); x = r.uniform(70, cell - 70); y = r.uniform(70, cell - 70); base = pal[r.integers(len(pal))]
        k = 1 + (r.random() * 2 - 1) * 0.15; ang = r.uniform(0, 2 * math.pi)
        d.polygon(leaf_shape("maple" if r.random() < 0.7 else "ginkgo", x, y, R, ang, r), fill=col(base, k) + (255,))
    save("T_litter.png", layer.filter(ImageFilter.GaussianBlur(0.7)))
    # soft cloud shadows for the sun's light function
    m = noise(512, 2, 3, 45)
    v = np.clip((m - 0.45) * 3.0, 0, 1)
    save("T_cloudmask.png", Image.fromarray((v * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(6)).convert("RGB"))


def flower_atlas():
    """green small leaves with pink/white/red blossoms: roadside azalea-like bushes"""
    cell = 512; r = rng_for(51)
    im = Image.new("RGBA", (cell * 2, cell * 2), (0, 0, 0, 0))
    leaf_pal = [(0.36, 0.50, 0.22), (0.44, 0.56, 0.24), (0.30, 0.44, 0.20)]
    flower_pals = [[(0.92, 0.45, 0.60), (0.98, 0.70, 0.78)], [(0.96, 0.94, 0.90), (0.90, 0.86, 0.70)], [(0.85, 0.22, 0.28), (0.95, 0.45, 0.40)], [(0.98, 0.80, 0.30), (0.95, 0.65, 0.20)]]
    for c in range(4):
        layer = Image.new("RGBA", (cell, cell), (0, 0, 0, 0)); d = ImageDraw.Draw(layer)
        for i in range(6):
            R = r.uniform(80, 130); x = r.uniform(cell * 0.25, cell * 0.75); y = r.uniform(cell * 0.25, cell * 0.75)
            base = leaf_pal[r.integers(3)]; k = 1 + (r.random() * 2 - 1) * 0.12; ang = r.uniform(0, 2 * math.pi)
            d.polygon(leaf_shape("oval", x, y, R * 1.06, ang, r), fill=col(base, k * 0.7) + (255,))
            d.polygon(leaf_shape("oval", x, y, R, ang, r), fill=col(base, k) + (255,))
        fp = flower_pals[c]
        for i in range(5):
            x = r.uniform(cell * 0.28, cell * 0.72); y = r.uniform(cell * 0.28, cell * 0.72); R = r.uniform(34, 52)
            for pI in range(5):
                a = 2 * math.pi * pI / 5 + r.uniform(-0.2, 0.2)
                d.polygon(ellipse_poly(x + math.cos(a) * R * 0.55, y + math.sin(a) * R * 0.55, R * 0.5, R * 0.36, a), fill=col(fp[0], 1 + (r.random() - 0.5) * 0.1) + (255,))
            d.ellipse([x - R * 0.22, y - R * 0.22, x + R * 0.22, y + R * 0.22], fill=col(fp[1]) + (255,))
        layer = layer.filter(ImageFilter.GaussianBlur(0.8))
        im.paste(layer, ((c % 2) * cell, (c // 2) * cell))
    arr = np.asarray(im).astype(np.float32); a = arr[..., 3:4] / 255
    blurred = np.asarray(im.filter(ImageFilter.GaussianBlur(6))).astype(np.float32)
    fill = blurred[..., :3] * 255 / np.maximum(blurred[..., 3:4], 1.0)
    rgb = np.where(a > 0.02, arr[..., :3], fill)
    save("T_flower.png", Image.fromarray(np.dstack([np.clip(rgb, 0, 255).astype(np.uint8), (a[..., 0] * 255).astype(np.uint8)]), "RGBA"))


def rooftile(n=512):
    """grey kawara tile rows: the tile is 1 m wide, 4 rows high"""
    im = Image.new("RGB", (n, n), col((0.16, 0.18, 0.22))); d = ImageDraw.Draw(im)
    rows, cols = 4, 6
    for j in range(rows):
        y0 = j * n // rows
        for i in range(cols):
            x0 = i * n // cols + (n // cols // 2 if j % 2 else 0)
            d.rectangle([x0 - n, y0, x0 + n // cols - 4 - n, y0 + n // rows - 6], fill=col((0.27, 0.29, 0.33)))
            d.rectangle([x0, y0, x0 + n // cols - 4, y0 + n // rows - 6], fill=col((0.27, 0.29, 0.33)))
            d.rectangle([x0, y0, x0 + n // cols - 4, y0 + 8], fill=col((0.40, 0.42, 0.46)))
            d.rectangle([x0, y0 + n // rows - 16, x0 + n // cols - 4, y0 + n // rows - 6], fill=col((0.12, 0.13, 0.16)))
    im = im.filter(ImageFilter.GaussianBlur(1.0))
    save("T_rooftile.jpg", im)


def farforest(n=1024):
    """speckled autumn forest for the distant hills ring (one texel = one tree at 6 m)"""
    r = rng_for(61); base = noise(n, 4, 3, 62)
    g = np.array([0.34, 0.34, 0.16]); pal = [(0.30, 0.38, 0.18), (0.44, 0.44, 0.18), (0.66, 0.46, 0.14), (0.74, 0.30, 0.12), (0.82, 0.60, 0.16), (0.24, 0.32, 0.16), (0.80, 0.40, 0.14), (0.72, 0.52, 0.16)]
    rgb = np.broadcast_to(g, (n, n, 3)).copy() * (0.8 + 0.4 * base[..., None])
    im = Image.fromarray(np.clip(rgb * 255, 0, 255).astype(np.uint8)); d = ImageDraw.Draw(im)
    for _ in range(6000):
        x = r.uniform(0, n); y = r.uniform(0, n); rr = r.uniform(8, 16); c = pal[r.integers(len(pal))]
        k = 1 + (r.random() - 0.5) * 0.3
        d.ellipse([x - rr, y - rr, x + rr, y + rr], fill=col(c, k))
        d.ellipse([x - rr * 0.5, y - rr * 0.8, x + rr * 0.5, y], fill=col(c, k * 1.25))
    save("T_farforest.jpg", im.filter(ImageFilter.GaussianBlur(0.8)))


def grass():
    """Quiet paint for curved mesh blades; silhouette comes from real geometry.

    Four opaque atlas cells share a meadow palette. Broad root-to-tip gradients
    and a soft folded face give form without isolated sparkling highlights.
    """
    cell = 512
    im = Image.new("RGBA", (cell * 2, cell * 2))
    palette = [(0.29, 0.40, 0.17), (0.35, 0.45, 0.20),
               (0.43, 0.45, 0.22), (0.49, 0.49, 0.26)]
    yy, xx = np.mgrid[0:cell, 0:cell] / (cell - 1)
    fold = 1 + .045 * np.tanh((xx - .5) * 5)
    light = (.88 + .12 * (1 - yy)) * fold
    for i, colour in enumerate(palette):
        rgb = np.clip(np.array(colour)[None, None, :] * light[:, :, None] * 255, 0, 255)
        rgba = np.dstack([rgb.astype(np.uint8), np.full((cell, cell), 255, np.uint8)])
        im.paste(Image.fromarray(rgba), ((i % 2) * cell, (i // 2) * cell))
    save("T_grass.png", im)


def bark(n=512):
    r = rng_for(31)
    im = Image.new("RGB", (n, n), col((0.20, 0.15, 0.12)))
    dr = ImageDraw.Draw(im)
    for _ in range(260):
        x = r.uniform(0, n); w = r.uniform(4, 14); h = r.uniform(40, 220); y = r.uniform(-h, n)
        c = (0.24, 0.18, 0.14) if r.random() < 0.5 else (0.16, 0.12, 0.10)
        dr.polygon([(x, y), (x + w, y + 4), (x + w * 0.7, y + h), (x - 2, y + h - 3)], fill=col(c, 1 + (r.random() - 0.5) * 0.2))
    im = im.filter(ImageFilter.GaussianBlur(0.7))
    # make it tile horizontally by blending the edge
    a = np.asarray(im).astype(np.float32)
    a = (a + np.roll(a, n // 2, axis=1)) / 2
    save("T_bark.jpg", Image.fromarray(a.astype(np.uint8)))


def road(w=256, h=1024):
    base = noise(h, 6, 3, 41, m=w); fine = noise(h, 40, 2, 42, m=w)
    xs = np.linspace(0, 1, w)[None, :]
    lanes = 0.04 * (np.exp(-((xs - 0.3) / 0.08) ** 2) + np.exp(-((xs - 0.7) / 0.08) ** 2))      # lighter worn wheel tracks
    v = 0.33 + 0.06 * (base - 0.5) + 0.03 * (fine - 0.5) + lanes - 0.05 * np.exp(-((np.abs(xs - 0.5) - 0.5) / 0.05) ** 2)
    rgb = np.stack([v * 1.0, v * 1.0, v * 1.03], -1)
    im = Image.fromarray(np.clip(rgb * 255, 0, 255).astype(np.uint8))
    dr = ImageDraw.Draw(im)
    line = col((0.72, 0.72, 0.68))
    m = int(w * 0.06); lw = int(w * 0.03)
    dr.rectangle([m, 0, m + lw, h], fill=line)
    dr.rectangle([w - m - lw, 0, w - m, h], fill=line)
    # dashed centre: 3 m dash / 5 m gap on an 8 m tile
    dr.rectangle([w // 2 - lw // 2, 0, w // 2 + lw // 2, int(h * 3 / 8)], fill=line)
    im = im.filter(ImageFilter.GaussianBlur(0.6))
    save("T_road.jpg", im)


def ground(n=1024):
    base = noise(n, 3, 4, 51)
    patch = noise(n, 5, 2, 52)
    g = np.array([0.40, 0.44, 0.20]); y = np.array([0.60, 0.52, 0.22]); d = np.array([0.30, 0.34, 0.16])
    t = np.clip((patch - 0.5) * 3, -1, 1)[..., None]
    rgb = g + np.where(t > 0, y - g, g - d) * np.abs(t) * 0.6 + (base[..., None] - 0.5) * 0.08
    save("T_ground.jpg", Image.fromarray(np.clip(rgb * 255, 0, 255).astype(np.uint8)))


def sky(w=4096, h=2048):
    """Equirect painted sky (row 0 = zenith, row h/2 = horizon). Each cumulus is a union of discs with one flat
    base, eroded by noise for a soft ragged edge, and shaded by the distance below its own top silhouette:
    bright warm tops, blue-grey undersides."""
    r = rng_for(61)
    yy = np.linspace(0, 1, h)[:, None]
    elev = np.clip((0.5 - yy) * 2, 0, 1)
    zen = np.array([0.14, 0.32, 0.66]); hor = np.array([0.34, 0.52, 0.76]); low = np.array([0.34, 0.48, 0.70])   # dark base: the dome is lit 1.35x so cloud tops go past white
    t = elev ** 0.6
    rgb = hor * (1 - t) + zen * t
    rgb = np.where(yy > 0.5, low, rgb)
    sky = np.broadcast_to(rgb[:, None, :], (h, w, 3)).astype(np.float32).copy()
    ero = 0.65 * noise(1024, 20, 4, 63) + 0.35 * noise(1024, 60, 2, 64)
    ero = np.asarray(Image.fromarray((ero * 255).astype(np.uint8)).resize((w, h), Image.BILINEAR), np.float32) / 255
    lit = np.array([1.0, 0.99, 0.97]); mid = np.array([0.84, 0.87, 0.92]); shade = np.array([0.52, 0.57, 0.68])
    clouds = []
    for _ in range(14):
        e = r.uniform(0.08, 0.45)
        cy = h * (0.5 - e * 0.5)
        W = r.uniform(30, 85) * (1 + 0.9 * e)          # the lobes extend the silhouette to ~2.2 W
        clouds.append((r.uniform(0, w), cy, W, W * r.uniform(0.42, 0.62)))
    clouds.sort(key=lambda c: -c[1])
    for (cx, cy, W, Hc) in clouds:
        x0, x1 = int(cx - W * 1.1), int(cx + W * 1.1); y0, y1 = int(cy - Hc * 1.9), int(cy + Hc * 0.35)
        if y0 < 0 or y1 >= h: continue
        cw, ch = x1 - x0, y1 - y0
        mask = Image.new("L", (cw, ch), 0); d = ImageDraw.Draw(mask)
        n = int(r.uniform(5, 9)); big = []
        for i in range(n):
            u = (i + 0.5) / n * 2 - 1 + r.uniform(-0.1, 0.1)
            rad = Hc * r.uniform(0.55, 1.0) * (1 - 0.55 * u * u)
            px, py = cx + u * W / 2 - x0, cy - rad * 0.5 - y0
            d.ellipse([px - rad, py - rad, px + rad, py + rad], fill=255); big.append((px, py, rad))
        # cauliflower lobes along the top of every big disc
        for (px, py, rad) in big:
            for k in range(int(rad / 9) + 4):
                ang = r.uniform(0, math.pi * 2)
                rr = rad * r.uniform(0.16, 0.34)
                qx, qy = px + math.cos(ang) * (rad - rr * 0.4), py + math.sin(ang) * (rad - rr * 0.4)
                d.ellipse([qx - rr, qy - rr, qx + rr, qy + rr], fill=255)
        m = np.asarray(mask).astype(np.float32) / 255
        base_row = int(cy + Hc * 0.10 - y0); fade = np.clip((np.arange(ch) - base_row) / max(Hc * 0.25, 1), 0, 1)[:, None]
        m = m * (1 - fade)
        cols = (np.arange(cw) + x0) % w
        sub = ero[y0:y1][:, cols]
        m = np.asarray(Image.fromarray((m * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(4)), np.float32) / 255
        m = np.clip((m - 0.30 - 0.8 * (sub - 0.5)) * 3.2, 0, 1)
        m = np.asarray(Image.fromarray((m * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(1.0)), np.float32) / 255
        # shading: bump-lit lobes (sun upper-left) on top of a depth gradient below the top silhouette
        top = np.argmax(m > 0.3, axis=0).astype(np.float32); has = (m > 0.3).any(axis=0)
        depth = (np.arange(ch)[:, None] - top[None, :]) / max(Hc, 1.0)
        depth = np.where(has[None, :], depth, 0.0)
        g = np.clip(depth / 1.0, 0, 1) ** 0.9
        base = lit[None, None, :] * (1 - g[..., None]) + shade[None, None, :] * g[..., None]
        mb = np.asarray(Image.fromarray((m * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(9)), np.float32) / 255
        sh = np.zeros_like(mb); sh[12:, 8:] = mb[:-12, :-8]                       # mask sampled up-left of each pixel
        bump = np.clip((mb - sh) * 4.0, -1, 1)                                   # + where the surface faces the sun (up-left), - on the far side
        colr = base + bump[..., None] * np.where(bump[..., None] > 0, (lit - base) * 0.9, (base - shade * 0.92) * 0.9)
        colr = np.clip(colr, 0, 1)
        region = sky[y0:y1][:, cols]
        sky[y0:y1][:, cols] = region * (1 - m[..., None]) + colr * m[..., None]
    save("T_sky.png", Image.fromarray(np.clip(sky * 255, 0, 255).astype(np.uint8)))


def water(n=512):
    r = rng_for(71)
    im = Image.new("RGB", (n, n), col((0.30, 0.44, 0.58)))
    dr = ImageDraw.Draw(im)
    for _ in range(160):
        x = r.uniform(0, n); y = r.uniform(0, n); L = r.uniform(20, 90); th = r.uniform(2, 5)
        c = (0.36, 0.50, 0.63) if r.random() < 0.7 else (0.28, 0.41, 0.55)
        for dx in (0, n, -n):
            dr.polygon(ellipse_poly(x + dx, y, L, th, 0), fill=col(c))
    save("T_water.jpg", im.filter(ImageFilter.GaussianBlur(1.2)))


def white():
    save("T_white.png", Image.new("RGB", (8, 8), (255, 255, 255)))


def concrete(n=256):
    b = noise(n, 4, 3, 81)
    v = 0.62 + 0.06 * (b - 0.5)
    rgb = np.stack([v, v * 0.99, v * 0.96], -1)
    save("T_concrete.jpg", Image.fromarray(np.clip(rgb * 255, 0, 255).astype(np.uint8)))


if __name__ == "__main__":
    leaves(); autumn_leaves(); flower_atlas(); rooftile(); farforest(); grass(); bark(); road(); ground(); sky(); water(); concrete(); white()
