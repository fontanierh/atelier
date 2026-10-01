"""Mega Park restyle textures: the park's rock, earth and signs in the island's style (docs/MEGAPARK.md, "Restyle").

    uv run python games/yorimichi/tools/megapark_textures.py paint [--only rock,grass] [--dry-run]
    python games/yorimichi/tools/megapark_textures.py finish

paint: gpt-image-2.5-sunburst, quality high, once per recorded prompt (atelier.ai.ledger). A surface is an edit of the
original texture (Image 1, which keeps its layout and scale on the park's UVs) in the style of the restyle concept
(Image 2). A picture is a new painting in that style for the signs. The compact copy and provenance go to
assets/megapark/restyle/<slug>.jpg|json; the full PNG stays in build/yorimichi/megapark/restyle.

finish: offline, any Python with NumPy and Pillow. Writes build/yorimichi/megapark/textures/<id>.png for every
original texture the restyle changes, and textures.json ({textures: {id: {png, sha256, how}}, lightmaps: {id: level}}),
which import_megapark.py reads in place of the originals. Painted surfaces are made seamless and brought to the island
palette's mean colour; recoloured textures keep their layout and alpha exactly; the signs get the paintings, fitted to
the original's shape and alpha. The skating geometry and its UVs are never touched. It also writes the Black instance of Noto Sans JP that the park
build extrudes the hilltop 寄り道 from (world/regions/megapark/sign.py).
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'world'))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'world' / 'regions'))
import yori  # noqa: E402
from megapark import sign as letters  # noqa: E402

GAME = Path(__file__).resolve().parents[1]
SOURCE = GAME / 'assets' / 'megapark'
PAINTED = SOURCE / 'restyle'
WORK = yori.OUT / 'megapark' / 'restyle'
OUT = yori.OUT / 'megapark' / 'textures'
CONCEPT = SOURCE / 'concepts' / 'restyle-west.jpg'
STYLE_CROP = (700, 330, 1536, 800)      # the concept's rocks, moss, grass and trees
SIZE = '1024x1024'

SURFACE = ('Image 1 is a tileable texture from a skate park in a stylised game. Image 2 shows the art direction of the '
           'game: soft painterly shapes, flat matte colour, cool lavender-grey volcanic rock with moss, autumn leaves. '
           'Repaint Image 1 as a seamless tileable texture in that style, keeping the layout, scale and direction of '
           'its features (strata, cracks, pebbles, blades) so it fits the same 3D surfaces. Seen perfectly flat and '
           'straight-on, filling the square edge to edge: no perspective, no object outline, no shadows or lighting '
           'gradient, even brightness everywhere, no text. Hand-painted like the background art of a Japanese '
           'animated film, soft strokes that still read as the real material, medium detail that holds up when '
           'repeated. The surface: ')
PICTURE = ('Image 1 shows the art direction of a stylised game set on a Japanese volcanic island in autumn: soft '
           'painterly shapes, flat matte colour, warm light. Paint a flat straight-on image in that style, filling the '
           'whole frame edge to edge, to be printed on a sign in a skate park: no frame, no perspective, no shadows, '
           'no lettering or text of any kind. The image: ')

# slug: (original texture, description, the island palette's mean sRGB colour it is brought to)
SURFACES = {
    'rock': ('0x2c70170a001d0133', 'rugged layered volcanic andesite rock like Mount Myogi, horizontal strata and '
             'blocky fractures, cool lavender-grey with darker slate in the cracks, soft green moss and a few '
             'yellow-green lichen patches on the ledges', (118, 114, 126)),
    'rock_smooth': ('0x2c70170a001d0135', 'smooth weathered volcanic rock, rounded water-worn faces with fine '
                    'cracks, cool grey with a faint lavender tint and thin streaks of green moss', (128, 125, 132)),
    'stone_cut': ('0x2c70170a001d014f', 'split grey andesite stone with fine cracks and chisel marks, pale '
                  'blue-grey with slight warm specks and a little moss in the deepest cracks', (142, 140, 140)),
    'earth': ('0x2c70170a001d00aa', 'dark forest earth and fine grey volcanic gravel, scattered small pebbles, a '
              'few fallen maple and ginkgo leaves in rust, orange and gold, small moss patches', (92, 86, 80)),
    'grass': ('0x2c70170a00040094', 'short soft green grass seen from above with a few fallen autumn leaves in '
              'rust, orange and gold, slightly uneven, like the island hillsides', (82, 102, 62)),
}
# slug: (size, description)
PICTURES = {
    'poster_volcano': ('1536x1024', 'a travel poster of the island: a snow-capped volcano above hills of autumn '
                       'forest in rust, orange and gold, a winding road and a small skate park carved into grey '
                       'rocks in the foreground, clear blue sky with one soft cloud'),
    'poster_festival': ('1536x1024', 'an autumn night festival by a small harbour: rows of glowing red and cream paper '
                        'lanterns, a few fireworks over the dark blue bay, wooden stalls under the lanterns'),
    'poster_noodles': ('1536x1024', 'a noodle stall poster: a steaming bowl of ramen with a soft egg, green onion '
                       'and a maple leaf on the rim, indigo noren curtain behind, warm cream background'),
    'waves': ('1024x1024', 'hand-dyed deep indigo cotton cloth covered edge to edge with a regular pattern of white '
              'overlapping wave arcs (seigaiha), the pattern repeating seamlessly on all four sides'),
    'emblem': ('1024x1024', 'one round emblem in the style of a Japanese family crest, the circle touching the '
               'edges of the square: a single maple leaf above three stylised curling waves inside a thin ring, bold '
               'flat shapes in warm cream on a deep indigo disc, slightly worn like hand-painted stencil; plain '
               'white outside the circle'),
}
# original texture -> recipe, for textures kept in shape but brought into the island's colours.
INDIGO = {'hue': 228, 'sat': .72, 'val': .82}
RECOLOUR = {
    # blue paint and teal: faded indigo, like the island's dyed cloth
    **{t: ('hue', {**INDIGO, 'from': (150, 260)}) for t in (
        '0x2c70170a001d0163', '0x2c70170a001d0151', '0x2c70170a001d0162', '0x2c70170a001d01be', '0x2c70170a002f1113',
        '0x2c70170a002f110b', '0x2c70170a002f0543', '0x2c70170a002f0d0a', '0x2c70170a002f1116', '0x2c70170a001d01b2')},
    # the skater banners' green and blue grounds, around their white silhouettes
    **{t: ('hue', {**INDIGO, 'from': (60, 260)}) for t in ('0x2c70170a001d01b3', '0x2c70170a001d01b4', '0x2c70170a001d01b5')},
    # red concrete: torii vermilion
    **{t: ('hue', {'hue': 10, 'sat': 1.05, 'val': .95, 'from': (330, 40)}) for t in (
        '0x2c70170a001d011f', '0x2c70170a001d0120')},
    # beige and pink stone: neutral warm grey
    **{t: ('grade', {'mean': (150, 147, 142), 'keep': .25}) for t in (
        '0x2c70170a001d015a', '0x2c70170a0004000a')},
    # dry grass and dirt decals on the rock: moss green and dark earth, alpha untouched
    '0x2c70170a001d00b0': ('grade', {'mean': (88, 100, 64), 'keep': .2}),
    '0x2c70170a002f0b10': ('grade', {'mean': (86, 102, 62), 'keep': .2}),
    '0x2c70170a001d0128': ('grade', {'mean': (86, 102, 62), 'keep': .2}),
    '0x2c70170a001d0137': ('grade', {'mean': (84, 80, 78), 'keep': .2}),
    # the white light towers: dark weathered iron
    '0x2c70170a001d016a': ('grade', {'mean': (70, 64, 60), 'keep': .1}),
}
# original texture -> how a painting replaces it
SIGNS = {
    '0x2c70170a001d0183': ('poster_volcano', 'fit'),        # the beer billboard
    '0x2c70170a001d0178': ('poster_festival', 'fit'),       # the bar ad
    '0x2c70170a001d0179': ('poster_noodles', 'fit'),        # the student-union ad
    '0x2c70170a001d01bc': ('waves', 'fit'),                 # the championship banner
    '0x2c70170a001d016c': ('emblem', 'banner'),             # the blue shark signs
    '0x2c70170a001d01bb': ('emblem', 'disc'),               # the shark logo boards
    '0x2c70170a001d0167': ('emblem', 'disc'),               # the shark painted on the decks
    '0x2c70170a001d01db': ('emblem', 'disc'),               # the MEGARAMP logo
    '0x2c70170a001d01c8': ('emblem', 'shack'),              # the SHARK SHACK banner, in its own outline
    '0x2c70170a001d016d': ('waves', 'band'),                # the LANDSHARKS MEGAPARK wall letters, as wave cloths
}
BAND = .745         # 016d: the park's two lettering quads use its bottom band; the campus names above are not kept


def sha(data):
    return hashlib.sha256(data).hexdigest()


def original(tid):
    record = json.loads((SOURCE / 'map.json').read_text())['textures'][tid]
    return SOURCE / record['png']


def style_reference():
    """The concept crop every painting is styled on, written to build (its hash goes into each provenance)."""
    from PIL import Image
    path = WORK / 'style.png'
    if not path.exists():
        WORK.mkdir(parents=True, exist_ok=True)
        Image.open(CONCEPT).convert('RGB').crop(STYLE_CROP).save(path)
    return path


def job(slug):
    """(prompt, size, reference images) of one painting."""
    if slug in SURFACES:
        tid, text, _ = SURFACES[slug]
        return SURFACE + text + '.', SIZE, [original(tid), style_reference()]
    size, text = PICTURES[slug]
    return PICTURE + text + '.', size, [style_reference()]


def paint(only, dry):
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from atelier.ai.ledger import run_once
    from treehouse_art import MODEL, QUALITY, compact, rel, sunburst
    for slug in [s for s in list(SURFACES) + list(PICTURES) if not only or s in only]:
        prompt, size, refs = job(slug)
        provenance = PAINTED / f'{slug}.json'
        if dry:
            print(f'--- {slug} {size} {[p.name for p in refs]}{" (recorded)" if provenance.exists() else ""}\n{prompt}\n')
            continue
        if provenance.exists():
            print(slug, 'already recorded; not resubmitting', flush=True)
            continue

        def generate(prompt=prompt, size=size, refs=refs, slug=slug):
            png, usage = sunburst(prompt, size, images=refs)
            WORK.mkdir(parents=True, exist_ok=True)
            (WORK / f'{slug}.png').write_bytes(png)
            return {'usage': usage, 'png_sha256': sha(png), 'output': compact(png, PAINTED / f'{slug}.jpg', 'textures')}
        PAINTED.mkdir(parents=True, exist_ok=True)
        run_once(provenance, {'model': MODEL, 'quality': QUALITY, 'size': size, 'prompt': prompt,
                              'references': {rel(p): sha(p.read_bytes()) for p in refs},
                              'purpose': 'Mega Park restyle texture'}, generate)
        print(slug, 'saved', flush=True)


# ---- finish -------------------------------------------------------------------------------------------------------

def lin(a):
    import numpy as np
    return np.where(a <= .04045, a / 12.92, ((a + .055) / 1.055) ** 2.4)


def srgb(a):
    import numpy as np
    a = np.clip(a, 0, 1)
    return np.where(a <= .0031308, a * 12.92, 1.055 * a ** (1 / 2.4) - .055)


def seamless(a, band=.22):
    """A half-tile offset copy blended in at the borders, where it wraps without a seam; deviations are rescaled so
    the blend keeps the texture's contrast (as tools/treehouse_textures.py)."""
    import numpy as np
    h, w = a.shape[:2]
    r = np.roll(a, (h // 2, w // 2), (0, 1))
    y = np.minimum(np.arange(h) + .5, h - np.arange(h) - .5) / h; x = np.minimum(np.arange(w) + .5, w - np.arange(w) - .5) / w
    s = lambda t: np.clip(t / band, 0, 1) ** 2 * (3 - 2 * np.clip(t / band, 0, 1))
    k = np.minimum(s(y)[:, None], s(x)[None, :])[..., None]
    mean = a.reshape(-1, a.shape[2]).mean(0)
    return mean + ((a - mean) * k + (r - mean) * (1 - k)) / np.sqrt(k ** 2 + (1 - k) ** 2)


def load(path, size=None):
    """RGBA float array in 0..1 (sRGB)."""
    import numpy as np
    from PIL import Image
    im = Image.open(path).convert('RGBA')
    if size and im.size != size: im = im.resize(size, Image.LANCZOS)
    return np.asarray(im, float) / 255


def to_mean(rgb, target):
    """Per-channel linear gain so the mean colour is `target` (sRGB 0-255)."""
    import numpy as np
    a = lin(rgb); want = lin(np.asarray(target, float) / 255)
    return srgb(a * want / np.maximum(a.reshape(-1, 3).mean(0), 1e-4))


def hsv(rgb):
    import numpy as np
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    mx = rgb.max(-1); mn = rgb.min(-1); d = mx - mn
    h = np.zeros_like(mx)
    m = d > 1e-6
    rr = (mx == r) & m; gg = (mx == g) & m & ~rr; bb = m & ~rr & ~gg
    h[rr] = ((g - b)[rr] / d[rr]) % 6; h[gg] = (b - r)[gg] / d[gg] + 2; h[bb] = (r - g)[bb] / d[bb] + 4
    return h * 60, np.where(mx > 1e-6, d / np.maximum(mx, 1e-6), 0), mx


def rgb_from_hsv(h, s, v):
    import numpy as np
    c = v * s; hp = (h % 360) / 60; x = c * (1 - np.abs(hp % 2 - 1)); z = np.zeros_like(h)
    i = np.floor(hp).astype(int) % 6
    table = [(c, x, z), (x, c, z), (z, c, x), (z, x, c), (x, z, c), (c, z, x)]
    out = np.zeros(h.shape + (3,))
    for k, (a, b, cc) in enumerate(table):
        sel = i == k
        out[sel] = np.stack([a[sel], b[sel], cc[sel]], -1)
    return out + (v - c)[..., None]


def recolour(a, how, params):
    import numpy as np
    rgb = a[..., :3]
    if how == 'hue':
        h, s, v = hsv(rgb)
        lo, hi = params['from']
        inside = ((h >= lo) & (h <= hi)) if lo <= hi else ((h >= lo) | (h <= hi))
        # Weighted by saturation, so white scratches and grey grime stay as they are.
        w = inside * np.clip(s * 2.5, 0, 1)
        new = rgb_from_hsv(np.full_like(h, params['hue']), np.clip(s * params['sat'], 0, 1), np.clip(v * params['val'], 0, 1))
        rgb = rgb * (1 - w[..., None]) + new * w[..., None]
    else:
        l = lin(rgb) @ [.2126, .7152, .0722]
        want = lin(np.asarray(params['mean'], float) / 255)
        weight = a[..., 3] if a[..., 3].min() < .99 else np.ones_like(l)
        mean_l = (l * weight).sum() / max(weight.sum(), 1e-6)
        graded = srgb(l[..., None] / max(mean_l, 1e-4) * want)
        rgb = graded * (1 - params['keep']) + rgb * params['keep']
    return np.concatenate([rgb, a[..., 3:]], -1)


def disc(n, feather=2.):
    import numpy as np
    y, x = np.mgrid[:n, :n] + .5
    r = np.hypot(x - n / 2, y - n / 2)
    return np.clip((n / 2 - 1 - r) / feather + .5, 0, 1)


def sign(tid, slug, how):
    """A sign texture: the painting fitted to the original's size, shape and alpha."""
    import numpy as np
    from PIL import Image
    base = load(original(tid)); h, w = base.shape[:2]
    art = Image.open(PAINTED / f'{slug}.jpg').convert('RGB')
    if how == 'fit':             # cover the original's aspect, centred
        scale = max(w / art.width, h / art.height)
        im = art.resize((round(art.width * scale), round(art.height * scale)), Image.LANCZOS)
        x0 = (im.width - w) // 2; y0 = (im.height - h) // 2
        rgb = np.asarray(im.crop((x0, y0, x0 + w, y0 + h)), float) / 255
        return np.concatenate([rgb, base[..., 3:]], -1)
    n = max(w, h)
    waves = np.asarray(Image.open(PAINTED / 'waves.jpg').convert('RGB').resize((n, n), Image.LANCZOS), float)[:h, :w] / 255
    if how == 'band':            # an opaque wave cloth over the band, and nothing of the old lettering anywhere
        alpha = np.zeros((h, w, 1)); alpha[int(h * BAND):] = 1
        return np.concatenate([waves, alpha], -1)
    if how == 'disc':            # a round decal or board: the emblem inside its circle, nothing outside
        rgb = np.asarray(art.resize((n, n), Image.LANCZOS), float)[:h, :w] / 255
        return np.concatenate([rgb, disc(n)[:h, :w, None]], -1)
    if how == 'banner':          # a hanging banner: indigo waves with the emblem near the top
        rgb = waves.copy()
        n = int(min(w, h) * .8); e = np.asarray(art.resize((n, n), Image.LANCZOS), float) / 255
        y0 = int(h * .12); x0 = (w - n) // 2; m = disc(n)[..., None]
        rgb[y0:y0 + n, x0:x0 + n] = rgb[y0:y0 + n, x0:x0 + n] * (1 - m) + e * m
        return np.concatenate([rgb, np.ones((h, w, 1))], -1)
    # 'shack': the banner's own outline, indigo waves along the band and the emblem in its middle disc
    rgb = waves.copy()
    n = min(w, h); e = np.asarray(art.resize((n, n), Image.LANCZOS), float) / 255
    x0 = (w - n) // 2; m = disc(n)[..., None]
    rgb[:, x0:x0 + n] = rgb[:, x0:x0 + n] * (1 - m) + e * m
    return np.concatenate([rgb, base[..., 3:]], -1)


def finish():
    import numpy as np
    from PIL import Image
    OUT.mkdir(parents=True, exist_ok=True)
    info = {}

    def save(tid, a, how):
        path = OUT / f'{tid[2:]}.png'
        mode = 'RGBA' if a.shape[2] == 4 else 'RGB'
        Image.fromarray((np.clip(a, 0, 1) * 255 + .5).astype(np.uint8), mode).save(path)
        info[tid] = {'png': path.name, 'sha256': sha(path.read_bytes()), 'how': how}

    for slug, (tid, _, mean) in SURFACES.items():
        src = PAINTED / f'{slug}.jpg'
        if not src.exists():
            print('not painted yet:', slug); continue
        a = load(src)[..., :3]
        save(tid, to_mean(srgb(seamless(lin(a))), mean), f'painted {slug}')
    for tid, (how, params) in RECOLOUR.items():
        save(tid, recolour(load(original(tid)), how, params), f'recoloured ({how})')
    for tid, (slug, how) in SIGNS.items():
        needs = [slug] + (['waves'] if how != 'fit' else [])
        missing = [n for n in needs if not (PAINTED / f'{n}.jpg').exists()]
        if missing:
            print('not painted yet:', missing, 'for', tid); continue
        save(tid, sign(tid, slug, how), f'sign {slug} ({how})')
    letters.font(yori.OUT / 'megapark' / letters.BLACK)
    report = {'textures': info, 'lightmaps': lightmap_levels()}
    (OUT / 'textures.json').write_text(json.dumps(report, indent=1, sort_keys=True) + '\n')
    print('MEGAPARK TEXTURES', len(info), 'restyled,', len(report['lightmaps']), 'lightmap levels', flush=True)


def lightmap_levels():
    """{lightmap id: sunlit level}: the 95th percentile luminance of the decoded irradiance (4*L*L) over the lit texels.
    The park material divides by it, so a lightmap's sunlit texels leave the island's lighting alone and only its
    shadowed corners darken (import_megapark.py, material)."""
    import numpy as np
    from PIL import Image
    records = json.loads((SOURCE / 'map.json').read_text())
    ids = sorted({p['retail_texture_ids']['lightmap'] for m in records['models'] for p in m['meshes']
                  if 'lightmap' in p.get('retail_texture_ids', {})})
    levels = {}
    for tid in ids:
        if tid not in records['textures']:
            continue
        a = np.asarray(Image.open(SOURCE / records['textures'][tid]['png']).convert('RGB'), 'f4') / 255
        lum = (4 * a * a) @ np.array([.2126, .7152, .0722], 'f4')
        lit = lum[lum > .02]
        if lit.size > 64:
            # A page that is nearly all shade keeps its shade: never normalise below 1.
            levels[tid] = round(max(float(np.percentile(lit, 95)), 1.), 3)
    return levels


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('command', choices=('paint', 'finish'))
    parser.add_argument('--only', default='')
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    if args.command == 'paint':
        paint({s for s in args.only.split(',') if s}, args.dry_run)
    else:
        finish()


if __name__ == '__main__':
    main()
