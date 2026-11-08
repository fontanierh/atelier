"""Detail textures for the Belmonte train, drawn with numpy (no image model, no paid call): walnut grain, two
marquetry panels with an olive sprig in gold inlay, burgundy and emerald carpets, the vestibule tiles and the
sun-and-olive crest; the exterior livery and the worn walls and floors come from ChatGPT swatches prepared by prepare_livery.py (`source`), which
the worn second class weathers. Each function returns float RGBA rows, bottom row first (Blender's image order), values 0..1.
Tileable textures wrap seamlessly; panels are mapped 0..1 on each panel face.
"""
import math
from pathlib import Path

import numpy as np

SOURCES = Path(__file__).resolve().parents[2] / 'assets' / 'vehicles' / 'belmonte-train' / 'textures'
JPEG = {'T_BT_SmokeboxDoor', 'T_BT_MenuBoard', 'T_BT_CurtainFabric', 'T_BT_BluePanel', 'T_BT_BluePanelWorn', 'T_BT_Ivory', 'T_BT_IvoryWorn', 'T_BT_Roof', 'T_BT_RoofWorn', 'T_BT_Underframe', 'T_BT_PaintPeel', 'T_BT_Lino', 'T_BT_TilesGrimy'}

WALNUT_DARK = np.array([.115, .042, .016])
WALNUT_MID = np.array([.235, .095, .036])
WALNUT_LIGHT = np.array([.36, .165, .07])
INLAY = np.array([.80, .56, .25])          # pale olive wood / satinwood inlay
GOLD = np.array([.86, .62, .26])


def _noise(h, w, cells, seed, octaves=4):
    """Tileable value noise in 0..1."""
    rng = np.random.default_rng(seed)
    out = np.zeros((h, w))
    amp, total = 1., 0.
    for o in range(octaves):
        cy, cx = cells[0] * 2 ** o, cells[1] * 2 ** o
        g = rng.random((cy, cx))
        y = np.linspace(0, cy, h, endpoint=False); x = np.linspace(0, cx, w, endpoint=False)
        y0 = np.floor(y).astype(int); x0 = np.floor(x).astype(int)
        fy = (y - y0)[:, None]; fx = (x - x0)[None, :]
        fy = fy * fy * (3 - 2 * fy); fx = fx * fx * (3 - 2 * fx)
        a = g[y0 % cy][:, x0 % cx]; b = g[y0 % cy][:, (x0 + 1) % cx]
        c = g[(y0 + 1) % cy][:, x0 % cx]; d = g[(y0 + 1) % cy][:, (x0 + 1) % cx]
        out += amp * ((a * (1 - fx) + b * fx) * (1 - fy) + (c * (1 - fx) + d * fx) * fy)
        total += amp; amp *= .5
    return out / total


def _rgba(rgb, alpha=None):
    h, w, _ = rgb.shape
    a = np.ones((h, w, 1)) if alpha is None else alpha[..., None]
    return np.concatenate([np.clip(rgb, 0, 1), a], axis=2)


def walnut(size=1024, seed=3, figure=1.):
    """Tileable straight-grained walnut: wavy stripes along U with darker pores."""
    n = _noise(size, size, (4, 2), seed)
    fine = _noise(size, size, (64, 8), seed + 1, 2)
    v = np.linspace(0, 1, size, endpoint=False)[:, None]
    stripes = .5 + .5 * np.sin(2 * math.pi * (v * 22 + n * 3.2 * figure))
    t = np.clip(.15 + .6 * stripes + .25 * (fine - .5), 0, 1)[..., None]
    rgb = WALNUT_DARK * (1 - t) + WALNUT_MID * t
    rgb = rgb * (.92 + .16 * _noise(size, size, (2, 2), seed + 2, 2))[..., None]
    return _rgba(rgb)


def _stroke(img, mask, color):
    img[mask] = color


def _leaf_mask(X, Y, cx, cy, length, width, angle):
    ca, sa = math.cos(angle), math.sin(angle)
    u = (X - cx) * ca + (Y - cy) * sa
    w = -(X - cx) * sa + (Y - cy) * ca
    # a pointed leaf: ellipse narrowed towards its tip
    t = np.clip(u / length, 0, 1)
    half = width * np.sin(math.pi * t) ** .8
    return (u >= 0) & (u <= length) & (np.abs(w) <= half)


def _sprig(img, X, Y, x0, y0, x1, y1, scale, leaves=7):
    """An olive sprig from (x0, y0) to (x1, y1) (pixels): a slender stem with paired leaves, inlaid."""
    length = math.hypot(x1 - x0, y1 - y0)
    ang = math.atan2(y1 - y0, x1 - x0)
    stem = np.zeros(X.shape, bool)
    for k in range(200):
        t = k / 199
        bend = math.sin(t * math.pi) * .05 * length
        px = x0 + (x1 - x0) * t - math.sin(ang) * bend
        py = y0 + (y1 - y0) * t + math.cos(ang) * bend
        stem |= (X - px) ** 2 + (Y - py) ** 2 <= (scale * (3.2 - 1.6 * t)) ** 2
    mask = stem.copy()
    for k in range(leaves):
        t = .12 + .80 * k / (leaves - 1)
        bend = math.sin(t * math.pi) * .05 * length
        px = x0 + (x1 - x0) * t - math.sin(ang) * bend
        py = y0 + (y1 - y0) * t + math.cos(ang) * bend
        size = scale * (38 - 16 * t)
        for side in (-1, 1):
            mask |= _leaf_mask(X, Y, px, py, size, size * .30, ang + side * .70)
    mask |= _leaf_mask(X, Y, x1 - math.cos(ang) * scale * 2, y1 - math.sin(ang) * scale * 2, scale * 24, scale * 6.5, ang)
    # olives: two small ovals near the base
    for side in (-1, 1):
        t = .38
        px = x0 + (x1 - x0) * t + side * math.sin(ang) * scale * 20
        py = y0 + (y1 - y0) * t - side * math.cos(ang) * scale * 20
        mask |= ((X - px) / (scale * 6.0)) ** 2 + ((Y - py) / (scale * 8.0)) ** 2 <= 1
    edge = mask & ~(np.roll(mask, 2, 0) & np.roll(mask, -2, 0) & np.roll(mask, 2, 1) & np.roll(mask, -2, 1))
    shade = (.86 + .14 * np.sin(X * .05 + Y * .03))[..., None]
    img[mask] = (INLAY * shade)[mask]
    img[edge] = WALNUT_DARK * .8


def _border(img, X, Y, w, h, inset, line, color):
    m = ((np.abs(X - inset) < line) | (np.abs(X - (w - inset)) < line)) & (Y > inset - line) & (Y < h - inset + line)
    m |= ((np.abs(Y - inset) < line) | (np.abs(Y - (h - inset)) < line)) & (X > inset - line) & (X < w - inset + line)
    img[m] = color


def panel(w=512, h=1024, seed=11, horizontal=False):
    """A marquetry panel: burr walnut field, darker cross-banded edge, double gold line and a central olive sprig."""
    rng_n = _noise(h, w, (3, 3), seed, 5)
    burr = .5 + .5 * np.sin(rng_n * 40)
    t = (.25 + .5 * burr)[..., None]
    img = WALNUT_MID * (1 - t) + WALNUT_LIGHT * t
    Y, X = np.mgrid[0:h, 0:w].astype(float)
    band = min(w, h) * .07
    edge = (X < band) | (X > w - band) | (Y < band) | (Y > h - band)
    img[edge] = (WALNUT_DARK * 1.3 * (.9 + .2 * rng_n[..., None]))[edge]
    _border(img, X, Y, w, h, band * 1.25, 2.2, GOLD)
    _border(img, X, Y, w, h, band * 1.6, 1.2, GOLD * .85)
    s = min(w, h) / 512 * 1.6
    if horizontal:
        _sprig(img, X, Y, w * .22, h * .5, w * .78, h * .5, s * .9, leaves=8)
    else:
        _sprig(img, X, Y, w * .5, h * .18, w * .5, h * .84, s, leaves=8)
    return _rgba(img)


def carpet(size=1024, field=(.30, .035, .04), motif=GOLD * .85, seed=5):
    """Tileable carpet: a diamond trellis of fine gold lines with a four-petal flower in each lozenge."""
    Y, X = np.mgrid[0:size, 0:size].astype(float) / size
    n = _noise(size, size, (16, 16), seed, 3)
    img = np.array(field)[None, None, :] * (.85 + .3 * n[..., None])
    u, v = (X * 4) % 1, (Y * 4) % 1
    d = np.abs(u - .5) + np.abs(v - .5)
    trellis = np.abs(d - .5) < .018
    img[trellis] = motif
    r = np.hypot(u - .5, v - .5); a = np.arctan2(v - .5, u - .5)
    petals = r < .11 * (.55 + .45 * np.abs(np.cos(2 * a)))
    img[petals] = motif * 1.05
    img[r < .03] = np.array(field) * .6
    corner = np.hypot(np.minimum(u, 1 - u), np.minimum(v, 1 - v)) < .045
    img[corner] = motif * .9
    return _rgba(img)


def tiles(size=512):
    """Vestibule floor: ivory and charcoal stone squares set on the diagonal."""
    Y, X = np.mgrid[0:size, 0:size].astype(float) / size
    n = _noise(size, size, (8, 8), 21, 3)[..., None]
    u, v = (X + Y) * 4, (X - Y) * 4
    check = (np.floor(u) + np.floor(v)) % 2 == 0
    ivory = np.array([.62, .58, .50]) * (.9 + .2 * n)
    dark = np.array([.07, .07, .075]) * (.8 + .4 * n)
    img = np.where(check[..., None], ivory, dark)
    grout = (np.abs(u - np.round(u)) < .02) | (np.abs(v - np.round(v)) < .02)
    img[grout] = (.30, .28, .25)
    return _rgba(img)


def crest(size=512):
    """The original crest: a sun disc with alternating rays above two olive branches, gold on transparent."""
    Y, X = np.mgrid[0:size, 0:size].astype(float)
    cx, cy = size / 2, size * .58
    r = np.hypot(X - cx, Y - cy); a = np.arctan2(Y - cy, X - cx)
    rays = (r < size * (.20 + .06 * (np.cos(a * 16) > 0))) & (np.abs(np.sin(a * 16)) < .55)
    disc = r < size * .12
    ring = np.abs(r - size * .135) < size * .008
    mask = rays | disc | ring
    img = np.zeros((size, size, 3)) + GOLD
    sh = (.85 + .15 * np.cos(a * 32))[..., None]
    img = img * sh
    branches = np.zeros_like(mask)
    tmp = np.zeros((size, size, 3))
    for side in (-1, 1):
        x0, y0 = cx + side * size * .05, size * .17
        x1, y1 = cx + side * size * .40, size * .52
        sub = np.zeros((size, size, 3))
        _sprig(sub, X, Y, x0, y0, x1, y1, size / 512 * .65, leaves=7)
        m = sub.sum(2) > 0
        branches |= m
    img[branches] = GOLD * .95
    alpha = (mask | branches).astype(float)
    img[disc] = GOLD * 1.08
    return _rgba(img, alpha)


# the luxury livery's linear colours (build.py MATERIALS reads them from here), the mean colours of the ChatGPT
# swatches in assets/vehicles/belmonte-train/textures: plain faces match the textured ones, and the worn second class
# starts from the very same paint, so it still belongs to the train
LIVERY_BLUE = (.0104, .0228, .054)
LIVERY_IVORY = (.743, .617, .438)
ROOF = (.041, .041, .040)


def has(name):
    """Whether an optional swatch (the locomotive's smokebox door, the canteen menu board, the curtain fabric) has been added yet."""
    return (SOURCES / name).exists()


def source(name, size=None):
    """A prepared swatch (prepare_livery.py) as float RGB rows, bottom row first. Needs Blender (bpy) to read it.
    size (w, h) resamples it first: Unreal only mips and streams power-of-two textures."""
    import bpy
    img = bpy.data.images.load(str(SOURCES / name))
    if size and tuple(img.size) != tuple(size):
        img.scale(*size)
    w, h = img.size
    px = np.array(img.pixels[:], dtype=np.float32).reshape(h, w, 4)[..., :3].astype(float)
    bpy.data.images.remove(img)
    return px


def srgb(c):
    """Linear colour to the sRGB values the PNG textures hold."""
    c = np.asarray(c, float)
    return np.where(c <= .0031308, 12.92 * c, 1.055 * np.power(c, 1 / 2.4) - .055)


def weather(img, seed=31, rust_amount=.05, streaks=True):
    """Tire an image of paint: slightly chalky faded patches, darker grime blotches and soot streaks of its own hue,
    a few rust chips. Tileable when the image is."""
    h, w, _ = img.shape
    n1 = _noise(h, w, (6, 6 * w // h), seed, 5)
    n2 = _noise(h, w, (14, 14 * w // h), seed + 1, 4)
    n3 = _noise(h, w, (3, 30 * w // h), seed + 2, 3)          # tall cells: streaks
    img = img * (.94 + .12 * n2[..., None])
    chalk = np.clip(img * 1.12 + .025, 0, 1)
    fade = (np.clip((n1 - .58) * 3, 0, 1) * .55)[..., None]
    img = img * (1 - fade) + chalk * fade
    grime = img * .50 + np.array((.030, .022, .012))
    dirt = (np.clip((.50 - n1) * 3, 0, 1) * .75)[..., None]
    img = img * (1 - dirt) + grime * dirt
    if streaks:
        st = (np.clip((n3 - .48) * 2.5, 0, 1) * .70)[..., None]
        img = img * (1 - st) + grime * .85 * st
    rust = np.array((.36, .17, .06))
    r = np.clip((n2 - (1 - rust_amount)) * 6, 0, 1)[..., None]
    img = img * (1 - r) + rust[None, None, :] * (.7 + .5 * n1[..., None]) * r
    return _rgba(img)


def worn(size=1024, paint=LIVERY_BLUE, seed=31, rust_amount=.05, streaks=True):
    """A flat coat of the livery, tired (see weather)."""
    return weather(np.zeros((size, size, 3)) + srgb(paint)[None, None, :], seed, rust_amount, streaks)


def numeral_two(size=512):
    """A crooked hand-painted 2 in faded cream, for the second-class sides."""
    Y, X = np.mgrid[0:size, 0:size].astype(float) / size
    cx, cy, r, t = .5, .66, .19, .07
    d = np.hypot(X - cx, Y - cy)
    ang = np.arctan2(Y - cy, X - cx)
    arc = (np.abs(d - r) < t / 2) & ((ang > -0.6) | (ang < -2.6))
    p0, p1 = np.array([cx + r * .82, cy - r * .55]), np.array([.30, .20])
    dv = p1 - p0
    tt = np.clip(((X - p0[0]) * dv[0] + (Y - p0[1]) * dv[1]) / (dv @ dv), 0, 1)
    diag = np.hypot(X - (p0[0] + tt * dv[0]), Y - (p0[1] + tt * dv[1])) < t / 2
    base = (Y > .16) & (Y < .16 + t) & (X > .28) & (X < .74)
    mask = arc | diag | base
    wear = _noise(size, size, (12, 12), 71, 3) > .3
    alpha = (mask & wear).astype(float)
    img = np.zeros((size, size, 3)) + np.array([.78, .70, .50])
    return _rgba(img, alpha)


ALL = {
    'T_BT_Walnut': lambda: walnut(),
    'T_BT_PanelTall': lambda: panel(512, 1024, 11),
    'T_BT_PanelWide': lambda: panel(1024, 512, 13, horizontal=True),
    'T_BT_CarpetBurgundy': lambda: carpet(1024, (.30, .035, .045), GOLD * .80, 5),
    'T_BT_CarpetEmerald': lambda: carpet(1024, (.035, .17, .12), GOLD * .80, 7),
    'T_BT_Tiles': lambda: tiles(),
    'T_BT_Crest': lambda: crest(),
    'T_BT_BlueWorn': lambda: worn(1024, LIVERY_BLUE, 31, rust_amount=.09),
    'T_BT_DarkWorn': lambda: worn(1024, (.018, .019, .022), 35, rust_amount=.16),
    'T_BT_BluePanel': lambda: _rgba(source('livery-blue-panel.jpg')),
    'T_BT_BluePanelWorn': lambda: weather(source('livery-blue-panel.jpg'), 31, rust_amount=.09),
    'T_BT_Ivory': lambda: _rgba(source('livery-ivory.jpg')),
    'T_BT_IvoryWorn': lambda: weather(source('livery-ivory.jpg'), 33, rust_amount=.08),
    'T_BT_Roof': lambda: _rgba(source('roof-canvas.jpg')),
    'T_BT_RoofWorn': lambda: weather(source('roof-canvas.jpg'), 35, rust_amount=.16),
    'T_BT_Underframe': lambda: _rgba(source('underframe.jpg')),
    'T_BT_PaintPeel': lambda: _rgba(source('wall-peel.jpg', (2048, 1024))),   # the 3072 px strip, power of two for Unreal
    'T_BT_Lino': lambda: _rgba(source('lino.jpg')),
    'T_BT_TilesGrimy': lambda: _rgba(source('canteen-tiles.jpg')),
    'T_BT_Two': lambda: numeral_two(),
}
for _name, _file in (('T_BT_SmokeboxDoor', 'smokebox-door.jpg'), ('T_BT_MenuBoard', 'menu-board.jpg'), ('T_BT_CurtainFabric', 'curtain-fabric.jpg')):
    if has(_file):          # optional swatches (smokebox door, canteen menu, curtain fabric): plain black until they are added
        ALL[_name] = lambda f=_file: _rgba(source(f))
