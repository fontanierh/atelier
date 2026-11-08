#!/usr/bin/env python3
"""Hidamari city surfaces on Sunburst: tileable ground, wall, wood, roof and metal textures for the city material
(M_HDCity, unreal/Scripts/city_material.py), and the game-ready detail maps.

    uv run python games/yorimichi/tools/hidamari_textures.py concepts
    uv run python games/yorimichi/tools/hidamari_textures.py paint [--only grass,earth] [--dry-run]
    uv run python games/yorimichi/tools/hidamari_textures.py finish

concepts: copies the art-direction redesigns the plan was greenlit on (build/yorimichi/scout/redesigns, made by the
scout's redesign script) into assets/hidamari/concepts/ as compact JPEGs with their ledger records.

paint: gpt-image-2.5-sunburst, quality high, 1024x1024, once per recorded prompt (atelier.ai.ledger.run_once): each
surface is a /v1/images/edits call with the street redesign (concepts/street_ew140.jpg) as the style reference. The
compact copy goes to assets/hidamari/textures/<slug>.jpg with <slug>.json, the ledger record (written before the paid
call; a slug with a record is never sent again: rename the record to <slug>.rejected-N.json to repaint it). The full
PNG stays in build/yorimichi/hidamari/textures/originals/. The key comes from OPENAI_API_KEY (or the ignored .env).

finish: offline from the committed JPEGs (any Python with NumPy and Pillow). Writes build/yorimichi/hidamari/
textures/<slug>.png and textures.json. Each surface is made seamless and turned into a neutral detail map, its linear
colour divided by its own mean and stored at half (tools/treehouse_textures.py), so the city material multiplies the
build's vertex colour by 2 x texture and the calibrated palette keeps its colour. The world build gives every face a
texture slot (world/regions/hidamari/surfaces.py) and UVs in metres; TILE below is metres per texture repeat.
"""
import sys as _sys; from pathlib import Path as _Path; _sys.path.insert(0, str(_Path(__file__).resolve().parents[1] / 'world')); import yori  # noqa: E402
_sys.path.insert(0, str(_Path(__file__).resolve().parent))
import argparse, json, time
from concurrent.futures import ThreadPoolExecutor

from treehouse_art import MODEL, QUALITY, compact, rel, sha, sunburst
from treehouse_textures import lin, seamless, srgb

ART = yori.ASSETS / 'hidamari'
CONCEPTS, RAW = ART / 'concepts', ART / 'textures'
WORK = yori.OUT / 'hidamari' / 'textures'
REDESIGNS = yori.OUT / 'scout' / 'redesigns'
STYLE = CONCEPTS / 'street_ew140.jpg'
SIZE = '1024x1024'

SURFACE = ('Image 1 is the art direction of Yorimichi, a stylised Japanese autumn town game: soft hand-painted '
           'materials, warm afternoon light, gentle detail. Paint one seamless tileable texture for that game, seen '
           'perfectly flat and straight-on, filling the whole square edge to edge: no object outline, no background, '
           'no perspective, no vignette, no shadows or lighting gradient, even brightness everywhere, no text. '
           'Hand-painted in the style of Image 1: soft painterly strokes that still read clearly as the real '
           'material, medium-scale detail that holds up when repeated many times across a town, matte, colours '
           'kept close to one mid tone. The surface: ')

# slug: (surface description, metres per texture repeat)
SURFACES = {
    'grass': ('a short lawn of soft green grass seen from straight above, small tufts and clover leaves, slightly '
              'darker and lighter patches, a few tiny fallen yellow and red autumn leaves', 2.4),
    'earth': ('packed dry earth seen from straight above, fine gravel and a few small pebbles pressed into it, '
              'worn smooth in places, warm brown-grey', 2.6),
    'flagstone': ('large irregular flat stone paving flags seen from straight above, worn smooth, narrow joints '
                  'with a little moss in them, warm grey-beige stone', 3.2),
    'sidewalk': ('a town pavement of small rectangular concrete paving blocks laid in a running bond, seen from '
                 'straight above, narrow joints, light even weathering and faint stains', 2.2),
    'asphalt': ('an old fine-grained asphalt road surface seen from straight above, small aggregate stones, faint '
                'darker patches and a few hairline cracks, no road markings', 3.5),
    'moss': ('thick soft cushion moss seen from straight above, deep green with yellow-green highlights and tiny '
             'dark gaps', 1.6),
    'gravel': ('pale grey temple gravel seen from straight above, raked into fine parallel lines running exactly '
               'left to right', 1.8),
    'stone': ('weathered grey granite, speckled grain, small pits and a few pale lichen spots, no block edges or '
              'joints', 1.6),
    'plaster': ('a warm lime plaster wall, soft trowel marks, fine sand grain and faint rain stains, no edges', 2.2),
    'timber': ('smooth planed cedar timber, straight fine grain running exactly up and down, softly weathered, no '
               'edges or seams', 1.3),
    'siding': ('a wall of weathered wooden boards laid horizontally, wide boards with soft dark lines between them, '
               'grain running exactly left to right, slightly silvered', 1.8),
    'roof': ('fired clay roof tile glaze seen close up, soft grey-blue mottling, fine speckles and faint pale '
             'lichen, no tile edges or rows', 1.4),
    'metal': ('weathered painted sheet metal, soft scratches, faint rust spots and gentle streaks', 1.4),
    'brick': ('an old brick wall in running bond, soft mortar joints, some bricks a little darker or lighter', 1.3),
    'concrete': ('weathered smooth concrete, faint formwork stains, tiny air pores and soft grime', 2.2),
    'paint': ('a softly weathered painted wooden surface, an even coat of pale paint with faint brush strokes and a '
              'few tiny chips', 1.5),
    'drystone': ('a dry-laid Japanese terrace retaining wall (ishigaki) seen straight-on: rounded river stones of mixed '
                 'sizes fitted closely together with small dark gaps and no mortar, warm grey, beige and ochre stones, '
                 'a little moss in the gaps', 2.0),
    'rice': ('a paddy of ripe standing rice seen from a little above: dense golden heads of grain bowing over in soft '
             'rows running exactly left to right, warm yellow-gold with ochre and pale green-gold, darker gaps between '
             'the rows', 1.6),
    'blockwall': ('the rough split face of a concrete garden block, coarse sandy grain with small pits, soft mottling '
                  'and faint rain streaks, warm beige-grey, no joints or block edges', 1.2),
}

# Share of each surface's colour variation kept in its detail map (the rest is brightness only): the map multiplies
# whatever palette colour a face has, and a full-strength hue shift (grey mortar over a red mean turns cyan) shows
# wherever the face's colour differs from the painting's.
CHROMA = {'grass': .5, 'moss': .3, 'brick': .45, 'flagstone': .6, 'earth': .6, 'rice': .6, 'drystone': .55}


def concepts():
    """The greenlit redesigns as compact committed concepts, with their ledger records."""
    CONCEPTS.mkdir(parents=True, exist_ok=True); n = 0
    for record in sorted(REDESIGNS.glob('*.json')):
        png = record.with_suffix('.png'); info = json.loads(record.read_text())
        if info.get('status') != 'done' or not png.exists(): print('skipped', record.stem, info.get('status')); continue
        out = compact(png, CONCEPTS / f'{record.stem}.jpg', 'concepts')
        info['compact_copy'] = out
        (CONCEPTS / f'{record.stem}.json').write_text(json.dumps(info, indent=2) + '\n'); n += 1
    print(n, 'concepts ->', rel(CONCEPTS))


def paint(slug, dry):
    from atelier.ai.ledger import run_once
    prompt = SURFACE + SURFACES[slug][0] + '.'; record = RAW / f'{slug}.json'
    if dry:
        print(f'--- {slug}{" (recorded)" if record.exists() else ""}\n{prompt}\n'); return slug, None
    if record.exists(): return slug, None
    t = time.time()

    def generate():
        png, usage = sunburst(prompt, SIZE, images=[STYLE])
        (WORK / 'originals').mkdir(parents=True, exist_ok=True); (WORK / 'originals' / f'{slug}.png').write_bytes(png)
        return {'usage': usage, 'png_sha256': sha(png), 'seconds': round(time.time() - t, 1),
                'compact_copy': compact(png, RAW / f'{slug}.jpg', 'textures')}
    try:
        run_once(record, {'model': MODEL, 'quality': QUALITY, 'size': SIZE, 'endpoint': '/v1/images/edits',
                          'prompt': prompt, 'references': {rel(STYLE): sha(STYLE.read_bytes())},
                          'execution': 'games/yorimichi/tools/hidamari_textures.py',
                          'purpose': 'Hidamari city surface texture'}, generate)
    except Exception as e:  # noqa: BLE001 - the ledger keeps it as submission_uncertain; never retried here
        print(slug, 'FAILED', type(e).__name__, flush=True); return slug, type(e).__name__
    print(slug, f'ok {time.time() - t:.0f}s', flush=True)
    return slug, None


def finish():
    import numpy as np
    from PIL import Image
    WORK.mkdir(parents=True, exist_ok=True); info = {}
    for slug, (_, tile) in SURFACES.items():
        src = RAW / f'{slug}.jpg'
        if not src.exists(): print('missing', slug); continue
        a = seamless(lin(np.asarray(Image.open(src).convert('RGB').resize((1024, 1024), Image.LANCZOS), float) / 255))
        ratio = a / a.reshape(-1, 3).mean(0)
        luma = (ratio @ [.2126, .7152, .0722])[..., None]
        detail = (luma + (ratio - luma) * CHROMA.get(slug, .5)) * .5
        Image.fromarray((srgb(detail) * 255 + .5).astype(np.uint8)).save(WORK / f'{slug}.png')
        info[slug] = dict(tile_m=tile, source=rel(src), sha256=sha(src.read_bytes()))
    (WORK / 'textures.json').write_text(json.dumps(info, indent=1) + '\n')
    sheet = Image.new('RGB', (8 * 192, -(-len(info) // 8) * 192))
    for i, slug in enumerate(info):
        sheet.paste(Image.open(WORK / f'{slug}.png').convert('RGB').resize((192, 192)), ((i % 8) * 192, (i // 8) * 192))
    (yori.REVIEW / 'hidamari').mkdir(parents=True, exist_ok=True); sheet.save(yori.REVIEW / 'hidamari' / 'textures-sheet.jpg', quality=85)
    print(len(info), 'textures ->', rel(WORK))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('stage', choices=['concepts', 'paint', 'finish'])
    ap.add_argument('--only', default=''); ap.add_argument('--dry-run', action='store_true')
    ap.add_argument('--concurrency', type=int, default=6)
    a = ap.parse_args()
    if a.stage == 'concepts': return concepts()
    if a.stage == 'finish': return finish()
    assert STYLE.exists(), 'run the concepts stage first'
    RAW.mkdir(parents=True, exist_ok=True)
    slugs = [s for s in SURFACES if not a.only or s in a.only.split(',')]
    if not a.dry_run:
        from atelier.env import require
        require('OPENAI_API_KEY')   # loads the ignored .env; never prints the value
    with ThreadPoolExecutor(1 if a.dry_run else a.concurrency) as ex:
        bad = [(s, e) for s, e in ex.map(lambda s: paint(s, a.dry_run), slugs) if e]
    for s, e in bad: print('FAILED', s, e)
    raise SystemExit(1 if bad else 0)


if __name__ == '__main__':
    main()
