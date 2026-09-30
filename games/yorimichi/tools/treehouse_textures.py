#!/usr/bin/env python3
"""Tree house textures on Sunburst: tileable surfaces (wood, bark, shingles, plaster, cloth, paper...) and one-off
pictures (noren, maps, quilts, rugs, the flag...), then the game-ready copies.

    uv run python games/yorimichi/tools/treehouse_textures.py paint [--only bark,moss] [--dry-run]
    uv run python games/yorimichi/tools/treehouse_textures.py finish

paint: gpt-image-2.5-sunburst, quality high, 1024x1024 (surfaces through /v1/images/generations, pictures through
/v1/images/edits with the place reference that shows them). Each lands in games/yorimichi/assets/treehouse/textures/
as <slug>.jpg (the committed copy, JPEG quality 92) with <slug>.prompt.txt and <slug>.provenance.json; the full-size
PNG goes to build/yorimichi/treehouse/originals/textures/. Existing JPEGs are skipped: rename one to
<slug>.rejected-N.jpg (kept out of git) to repaint it. The key comes from OPENAI_API_KEY (or the ignored .env).

finish: works offline from the committed JPEGs (any Python with numpy and Pillow) and writes
build/yorimichi/treehouse/textures/<slug>.png and textures.json. A surface is made seamless (a half-tile offset copy
blended in at the borders, keeping contrast) and turned into a neutral detail map: its linear colour divided by its
own mean, stored at half, so M_TreeHouse multiplies the build's vertex colour by (2 x texture) and the game's
calibrated palette stays as it was. A picture keeps its colours; textures.json gives the gain that brings its mean to
the palette's brightness. The rope texture is drawn here rather than painted.
"""
import sys as _sys; from pathlib import Path as _Path; _sys.path.insert(0, str(_Path(__file__).resolve().parents[1] / 'world')); import yori  # noqa: E402
_sys.path.insert(0, str(_Path(__file__).resolve().parent))
import argparse, json, time
from concurrent.futures import ThreadPoolExecutor

from treehouse_art import MODEL, QUALITY, REFS, SHEETS, TEXTURES as RAW, keep, now, redact, rel, sha, sunburst

GAME = yori.OUT/'treehouse'/'textures'
SIZE = '1024x1024'

SURFACE = ("A seamless tileable texture for a stylised game, seen perfectly flat and straight-on, filling the whole square "
           "edge to edge: no object outline, no background, no perspective, no vignette, no shadows or lighting "
           "gradient, even brightness everywhere, no text. Hand-painted like the background art of a warm Japanese "
           "animated film: soft painterly strokes that still read as the real material, medium detail that holds up "
           "when repeated, matte. The surface: ")
PICTURE = ("Paint a flat straight-on image, filling the whole square edge to edge, to be printed on an object in a "
           "stylised game: no background, no perspective, no shadows, no frame unless asked, no lettering or text of any "
           "kind. Match the colours and hand-made look it has in the reference painting (Image 1), in the same warm "
           "painterly style. The image: ")

# slug: (surface description, metres per tile)
SURFACES = {
    'wood_plank': ('warm honey-brown weathered wood grain of one wide sawn board, long grain lines running exactly '
                   'left to right, a few small dark knots, soft silvering in the grain, no board edges or seams', 1.2),
    'wood_timber': ('dark brown rough hand-hewn timber, strong grain lines running exactly left to right, adze marks '
                    'and fine cracks along the grain, no edges or seams', 1.2),
    'wood_pale': ('pale smooth sanded cedar wood, soft straight grain running exactly left to right, gentle '
                  'honey-cream tones, no edges or seams', 1.2),
    'bark': ('the bark of an ancient camphor tree, deep rough furrows and plates running exactly up and down, '
             'grey-brown with warm brown in the cracks and a few small patches of green moss and lichen', 1.6),
    'shingle': ('weathered split cedar-shake wood, coarse fibrous grain running exactly up and down, grey-brown with '
                'silvered tips and small flecks of green moss', 1.0),
    'moss': ('thick soft cushion moss, deep green with yellow-green highlights and tiny dark gaps', 1.0),
    'stone': ('a flat weathered grey-green granite stepping stone surface, small pits, speckled grain and pale lichen '
              'spots', 1.2),
    'plaster': ('warm cream clay plaster wall, soft trowel marks, fine chopped straw fibres showing in the clay', 1.5),
    'canvas': ('cream cotton sailcloth, a clearly visible even weave, soft weathered stains and faint creases', 1.0),
    'indigo': ('hand-dyed indigo cotton cloth, uneven deep blue dye with lighter streaks, a fine visible weave', .8),
    'paper': ('warm white washi paper, long soft fibres and small flecks of bark pressed into the sheet', .6),
    'tile': ('old blue-grey glazed clay roof tile surface, speckled glaze with soft wear and faint rings', 1.0),
    'hull': ('old wooden boat planks painted faded sea blue, the paint worn and flaking to show brown wood grain, '
             'grain running exactly left to right, no plank edges', 1.5),
    'straw': ('tightly bundled golden rice straw, long stalks running exactly left to right, some darker stalks', .8),
    'iron': ('dark cast iron, fine sand-cast pitting with soft rust-brown patches', .8),
}
COLOURED = {'hull': (.34, .46, .52)}   # surfaces kept in colour, with the palette colour their mean should match
# slug: (reference view, description, gain target = the palette colour its mean should match)
PICTURES = {
    'noren_indigo': ('library-inside', 'an indigo noren door curtain seen flat: one deep indigo cotton cloth with a '
                     'single large white maple leaf in the centre, a narrow darker band along the top, the cloth '
                     'filling the square', (.16, .20, .36)),
    'noren_cream': ('entry-reveal', 'a cream cotton noren door curtain seen flat, filling the square: plain warm '
                    'cream cloth with a small indigo maple leaf near the bottom and a thin indigo band along the top',
                    (.58, .50, .37)),
    'map': ('library-inside', 'a hand-drawn treasure-style island map on old parchment: one green wooded island with '
            'hills, a small temple on a rocky islet, a tiny tree house drawn in the forest, a dotted path, soft blue '
            'sea with painted waves, a compass rose; no words or letters anywhere', (.62, .52, .36)),
    'quilt': ('sleep-inside', 'a patchwork quilt seen from straight above, 4 by 4 large squares: indigo cotton with '
              'small white stitched stars, cream, persimmon orange, faded red with one white maple leaf; soft puffy '
              'stitching lines; no stripes and nothing like a national flag', (.50, .36, .28)),
    'rug': ('heart-inside', 'a woven rag rug seen from straight above: cream field with indigo and faded red blocks, '
            'little white crosses and a patterned border all round, the rug filling the square', (.50, .42, .34)),
    'rug_blue': ('boat-inside', 'a woven cotton rug seen from straight above: soft blue and cream stripes across its '
                 'width with a thin red line near each end, filling the square', (.30, .33, .38)),
    'flag': ('crow-back', 'a cloth flag seen flat and filling the square: deep indigo cotton with a single large white '
             'maple leaf in the middle', (.16, .20, .36)),
    'kite': ('heart-inside', 'a Japanese paper kite seen flat, filling the square: diamond shape split into quarters '
             'of red, white and indigo, a thin bamboo cross behind it, painted on washi paper', (.55, .40, .34)),
    'books': ('library-inside', 'a row of about twelve old cloth-bound book spines standing side by side, filling '
              'the square, muted blue, red, green, ochre and brown, small gold bands, no titles or letters', (.40, .26, .16)),
    'pictures': ('library-inside', 'four children\'s drawings in a 2 by 2 grid on cream paper, filling the square: a '
                 'little sailing boat on waves, the tree house in autumn trees, a red fox, the rocky island with its '
                 'temple; crayon and watercolour; no words', (.60, .52, .40)),
    'cushion': ('heart-inside', 'the top of a square indigo floor cushion seen from above, filling the square: deep '
                'indigo cotton with small white stitched stars and a thin cream piping edge', (.16, .20, .36)),
}


def job(slug):
    if slug in SURFACES: return SURFACE+SURFACES[slug][0]+'.', []
    view, text, _ = PICTURES[slug]
    return PICTURE+text+'.', [REFS/f'{view}.jpg']


def paint(slug, dry):
    prompt, refs = job(slug); image = RAW/f'{slug}.jpg'
    if dry: print(f'--- {slug} {[r.name for r in refs]}{" (exists, skipped)" if image.exists() else ""}\n{prompt}\n'); return slug, None
    if image.exists(): return slug, None
    t = time.time(); started = now(); error = usage = digest = record = None
    try:
        png, usage = sunburst(prompt, SIZE, refs)
        digest, record = keep(png, 'textures', slug, image)
    except Exception as e:  # noqa: BLE001 - recorded, the batch goes on
        error = redact(e)[:600]
    (RAW/f'{slug}.prompt.txt').write_text(prompt+'\n')
    (RAW/f'{slug}.provenance.json').write_text(json.dumps(dict(
        stage='treehouse-texture', slug=slug, requested_model=MODEL, quality=QUALITY, size=SIZE,
        endpoint='/v1/images/edits' if refs else '/v1/images/generations', execution='games/yorimichi/tools/treehouse_textures.py',
        prompt_sha256=sha(prompt.encode()), reference_files={rel(r): sha(r.read_bytes()) for r in refs},
        started_at=started, finished_at=now(), elapsed_seconds=round(time.time()-t, 1), usage=usage,
        output_sha256=digest, error=error, compact_copy=record), indent=2)+'\n')
    print(slug, error or f'ok {time.time()-t:.0f}s', flush=True)
    return slug, error


def lin(a):
    import numpy as np
    return np.where(a <= .04045, a/12.92, ((a+.055)/1.055)**2.4)


def srgb(a):
    import numpy as np
    a = np.clip(a, 0, 1)
    return np.where(a <= .0031308, a*12.92, 1.055*a**(1/2.4)-.055)


def seamless(a, band=.22):
    """Blend a half-tile offset copy in at the borders; the offset copy wraps without a seam there. Deviations are
    rescaled so the blend zone keeps the texture's contrast instead of greying out."""
    import numpy as np
    h, w = a.shape[:2]
    r = np.roll(a, (h//2, w//2), (0, 1))
    y = np.minimum(np.arange(h)+.5, h-np.arange(h)-.5)/h; x = np.minimum(np.arange(w)+.5, w-np.arange(w)-.5)/w
    s = lambda t: np.clip(t/band, 0, 1)**2*(3-2*np.clip(t/band, 0, 1))
    k = np.minimum(s(y)[:, None], s(x)[None, :])[..., None]
    mean = a.reshape(-1, a.shape[2]).mean(0)
    dev = (a-mean)*k+(r-mean)*(1-k)
    return mean+dev/np.sqrt(k**2+(1-k)**2)


def rope_texture(n=512):
    """Three twisted strands along u (left to right), round the rope along v, with fibre streaks."""
    import numpy as np
    rng = np.random.default_rng(7)
    u, v = np.meshgrid(np.arange(n)/n, np.arange(n)/n)
    phase = (u*6+v*3) % 1                                   # 6 twists per tile along, 3 strands around
    ridge = np.sin(np.pi*phase)**.6
    fy, fx = np.meshgrid(np.fft.fftfreq(n), np.fft.fftfreq(n), indexing='ij')
    blur = np.exp(-2*np.pi**2*((fy*1.2)**2+(fx*10)**2))               # wrap-around gaussian: fibres run along u
    streak = np.real(np.fft.ifft2(np.fft.fft2(rng.random((n, n)))*blur))
    shade = .55+.45*ridge+(streak-streak.mean())*2.2
    return np.clip(np.stack([shade]*3, -1)*[1, .93, .82], 0, None)


def finish():
    import numpy as np
    from PIL import Image
    GAME.mkdir(parents=True, exist_ok=True); info = {}
    for slug, (_, tile) in list(SURFACES.items())+[('rope', (None, .3))]:
        if slug == 'rope':
            a = rope_texture(); source = 'drawn in treehouse_textures.py'
        else:
            src = RAW/f'{slug}.jpg'
            if not src.exists(): print('missing', slug); continue
            a = lin(np.asarray(Image.open(src).convert('RGB').resize((1024, 1024), Image.LANCZOS), float)/255)
            a = seamless(a); source = rel(src)
        if slug in COLOURED:     # two-tone surfaces keep their colours; the gain sets the brightness
            Image.fromarray((srgb(a)*255+.5).astype(np.uint8)).save(GAME/f'{slug}.png')
            want = lin(np.array(COLOURED[slug], float))@[.2126, .7152, .0722]
            info[slug] = dict(kind='surface', tile_m=tile, gain=round(float(want/(a.reshape(-1, 3).mean(0)@[.2126, .7152, .0722])), 4), source=source)
            continue
        detail = a/a.reshape(-1, 3).mean(0)*.5
        Image.fromarray((srgb(detail)*255+.5).astype(np.uint8)).save(GAME/f'{slug}.png')
        info[slug] = dict(kind='surface', tile_m=tile, gain=2.0, source=source)
    for slug in ('flat', 'glass'):   # no texture: the vertex colour as it is (glass also glows a little)
        Image.new('RGB', (64, 64), (188, 188, 188)).save(GAME/f'{slug}.png')
        info[slug] = dict(kind='surface', tile_m=1., gain=round(1/float(lin(np.array(188/255))), 4), source='flat')
    for slug, (_, _, target) in PICTURES.items():
        src = RAW/f'{slug}.jpg'
        if not src.exists(): print('missing', slug); continue
        im = Image.open(src).convert('RGB').resize((1024, 1024), Image.LANCZOS); im.save(GAME/f'{slug}.png')
        mean = lin(np.asarray(im, float)/255).reshape(-1, 3).mean(0)
        want = lin(np.array(target, float))
        gain = float((want@[.2126, .7152, .0722])/(mean@[.2126, .7152, .0722]))
        info[slug] = dict(kind='picture', tile_m=1.0, gain=round(gain, 4), source=rel(src))
    (GAME/'textures.json').write_text(json.dumps(info, indent=1)+'\n')
    SHEETS.mkdir(parents=True, exist_ok=True)
    sheet = Image.new('RGB', (8*192, -(-len(info)//8)*192))
    for i, slug in enumerate(info):
        sheet.paste(Image.open(GAME/f'{slug}.png').convert('RGB').resize((192, 192)), ((i % 8)*192, (i//8)*192))
    sheet.save(SHEETS/'textures-sheet.jpg', quality=85)
    print(len(info), 'textures ->', rel(GAME))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('stage', choices=['paint', 'finish'])
    ap.add_argument('--only', default=''); ap.add_argument('--dry-run', action='store_true')
    ap.add_argument('--concurrency', type=int, default=8)
    a = ap.parse_args()
    if a.stage == 'finish': return finish()
    RAW.mkdir(parents=True, exist_ok=True)
    slugs = [s for s in list(SURFACES)+list(PICTURES) if not a.only or s in a.only.split(',')]
    if not a.dry_run and any(not (RAW/f'{s}.jpg').exists() for s in slugs):
        from atelier.env import require
        require('OPENAI_API_KEY')   # loads the ignored .env; stops with a clear message, never prints the value
    with ThreadPoolExecutor(1 if a.dry_run else a.concurrency) as ex:
        bad = [(s, e) for s, e in ex.map(lambda s: paint(s, a.dry_run), slugs) if e]
    for s, e in bad: print('FAILED', s, e)
    raise SystemExit(1 if bad else 0)


if __name__ == '__main__':
    main()
