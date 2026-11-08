#!/usr/bin/env python3
"""Crater Park tower-top shrine: a Sunburst reference sheet of each object alone, in the look of the approved
tower-top concept (C, "shrine balcony"), then a Tripo image-to-model. Two stages, so the sheets are checked before
any credits are spent; the same steps as tools/hidamari_props.py.

    uv run python games/yorimichi/tools/craterpark_shrine_props.py concept [--only torii,lantern] [--dry-run]
    uv run python games/yorimichi/tools/craterpark_shrine_props.py model [--only ...] [--dry-run] [--approval "..."]
    uv run python games/yorimichi/tools/craterpark_shrine_props.py sheet

Each object lives in games/yorimichi/assets/craterpark/shrine/<slug>/: concept.jpg with concept.json (the ledger
record of the paid call, atelier.ai.ledger.run_once: a slug with a record is never painted again; rename the record
to concept.rejected-N.json and the picture likewise to repaint), then job.json (the Tripo settings, task id and
credits) and <slug>.glb, the model with its texture made a 1024 JPEG (tools/treehouse_props.py's model stage: Tripo
P2 image-to-model with a detailed texture, submitted once and resumed by id, an uncertain POST never repeated). The
full-size sheets and the Tripo work folders (raw downloads, api-private) stay in build/yorimichi/craterpark/shrine/.
world/regions/craterpark/v2/shrine.py fits each GLB to its size and editor_supports places them on the balcony off the
start tower's back edge; tools/craterpark_textures.py finish writes their textures out for the Unreal import.
"""
import sys as _sys; from pathlib import Path as _Path; _sys.path.insert(0, str(_Path(__file__).resolve().parents[1] / 'world')); import yori  # noqa: E402
_sys.path.insert(0, str(_Path(__file__).resolve().parent))
import argparse, time
from concurrent.futures import ThreadPoolExecutor

from treehouse_art import MODEL, QUALITY, compact, rel, sha, sheet as contact_sheet, sunburst

OUT = yori.ASSETS / 'craterpark' / 'shrine'
WORK = yori.OUT / 'craterpark' / 'shrine'
ORIGINALS, TRIPO = WORK / 'concepts', WORK / 'tripo'
STYLE_REFS = [yori.ASSETS / 'craterpark' / 'concepts' / 'editor' / 'tower-top-shrine-balcony.jpg']
SIZE = '1024x1024'

STYLE = ('Paint ONE object alone for 3D reconstruction: shown whole, in a three-quarter front view from slightly above, '
         'centred with a clear margin all round, on a plain flat light-grey background, soft even light, no cast '
         'shadow, no floor, no ground, no landscape, no text, letters or logos anywhere, nothing else in the picture. '
         'Image 1 is the approved art direction: the top of a skate start tower with a small shrine behind it. Paint '
         'the object exactly in the look of the shrine pieces in image 1: the same warm hand-painted style, '
         'vermilion lacquer with light wear, dark weathered timber, pale grey weathered granite, dark grey roof '
         'tiles, matte colours with soft variation, chunky readable shapes, believable real-world proportions, no '
         'photographic noise, no glossy highlights. Every part must be solid and connected; nothing floating. '
         'The object: ')

# slug: the object (its size in the game is world/regions/craterpark/v2/shrine.py MODELS)
PROPS = {
    'bell_pavilion': ('a small Japanese shrine bell pavilion (shoro) standing on its own square raised balcony: a square '
                      'plank deck of warm timber with a vermilion-lacquered wooden railing with dark-capped posts round '
                      'all four sides; the deck sits on a short solid base of dark weathered timber beams with a '
                      'flat bottom; in the middle of the deck four vermilion posts on small stone bases carry a curved '
                      'dark-grey tiled hip-and-gable roof with gently upturned eaves and a ridge with small end tiles, '
                      'and under the roof hangs a large dark bronze temple bell from a cross beam, with a short wooden '
                      'striker log on ropes beside it; the roof is about as wide as the deck'),
    'stone_lantern': ('a tall Japanese granite stone lantern (kasuga-doro): a hexagonal stepped base, a slim round '
                      'column, a lamp box with open square windows and a warm glow inside, a wide curved hexagonal roof '
                      'with curled corners and an onion-shaped jewel finial on top, pale weathered grey stone with '
                      'small patches of moss'),
    'torii': ('a slim vermilion-lacquered Japanese Shinto torii gate of the myojin style: two round vermilion posts '
              'standing on short square grey granite footings, a straight tie beam (nuki) through the posts below '
              'the top and a dark-capped upper lintel (kasagi) that curves gently up at both ends, a small dark '
              'plaque between the two beams left blank; a thick twisted straw shimenawa rope hangs in a shallow sag '
              'between the two posts under the tie beam, with four white zigzag paper shide streamers hanging from it; '
              'the gate is about twice as tall as it is wide'),
    'nobori': ('a single tall Japanese nobori shrine banner on its own pole: a thin dark lacquered wooden pole standing '
               'in a small square grey stone base, a long narrow vertical cloth banner in vermilion red hanging from '
               'a short crossbar at the top of the pole and tied to the pole down one side, a simple white circle '
               'crest of three swirling commas (mitsudomoe) near its top, a thin white border, the cloth hanging '
               'almost straight with a gentle ripple; the banner is about four times as tall as it is wide'),
}


# Tripo face limits: the detailed pavilion gets the most, the slim banner the fewest (all seen from the deck up close)
FACES = {'bell_pavilion': 16000, 'torii': 10000, 'stone_lantern': 8000, 'nobori': 6000}


def prompt_for(slug):
    return STYLE + PROPS[slug] + '.'


def concept(slug, dry):
    from atelier.ai.ledger import run_once
    folder = OUT / slug; record = folder / 'concept.json'; prompt = prompt_for(slug)
    if dry:
        print(f'--- {slug}{" (recorded)" if record.exists() else ""}\n{prompt}\n'); return slug, None
    if record.exists(): return slug, None
    folder.mkdir(parents=True, exist_ok=True); t = time.time()

    def generate():
        png, usage = sunburst(prompt, SIZE, images=STYLE_REFS)
        (ORIGINALS / slug).mkdir(parents=True, exist_ok=True); (ORIGINALS / slug / 'concept.png').write_bytes(png)
        return {'usage': usage, 'concept_sha256': sha(png), 'seconds': round(time.time() - t, 1),
                'compact_copy': compact(png, folder / 'concept.jpg', 'props')}
    try:
        run_once(record, {'model': MODEL, 'quality': QUALITY, 'size': SIZE, 'endpoint': '/v1/images/edits',
                          'prompt': prompt, 'references': {rel(p): sha(p.read_bytes()) for p in STYLE_REFS},
                          'execution': 'games/yorimichi/tools/craterpark_shrine_props.py',
                          'purpose': 'Crater Park tower-top shrine reference sheet for Tripo'}, generate)
    except Exception as e:  # noqa: BLE001 - kept by the ledger as submission_uncertain; never retried here
        print(slug, 'FAILED', type(e).__name__, flush=True); return slug, type(e).__name__
    print(slug, f'ok {time.time() - t:.0f}s', flush=True)
    return slug, None


def model(slug, faces, approval, dry):
    import treehouse_props
    return treehouse_props.model(slug, faces or FACES[slug], approval, dry, out=OUT, tripo=TRIPO, originals=ORIGINALS,
                                 stage='craterpark_shrine', record='concept.json')


def sheet():
    return contact_sheet([(OUT / s / 'concept.jpg', s) for s in PROPS],
                         yori.REVIEW / 'craterpark' / 'shrine-sheet.jpg', 384, 384, 4)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('stage', choices=['concept', 'model', 'sheet'])
    ap.add_argument('--only', default=''); ap.add_argument('--dry-run', action='store_true')
    ap.add_argument('--faces', type=int, default=0, help='Tripo face limit (default FACES)'); ap.add_argument('--concurrency', type=int, default=4)
    ap.add_argument('--approval', default='pending', help='who approved spending the credits, kept in job.json')
    a = ap.parse_args()
    slugs = [s for s in PROPS if not a.only or s in a.only.split(',')]
    if a.stage == 'sheet': return sheet()
    if a.stage == 'concept' and not a.dry_run:
        from atelier.env import require
        require('OPENAI_API_KEY')   # loads the ignored .env; never prints the value
    job = (lambda s: concept(s, a.dry_run)) if a.stage == 'concept' else (lambda s: model(s, a.faces, a.approval, a.dry_run))
    with ThreadPoolExecutor(1 if a.dry_run else a.concurrency) as ex:
        results = list(ex.map(job, slugs))
    bad = [(s, e) for s, e in results if e]
    for s, e in bad: print('FAILED', s, e)
    if a.stage == 'concept' and not a.dry_run: sheet()
    raise SystemExit(1 if bad else 0)


if __name__ == '__main__':
    main()
