#!/usr/bin/env python3
"""Hidamari street props: a Sunburst concept of each object alone, in the style of the city's art-direction
redesigns, then a Tripo image-to-model. Two stages, so the concepts are checked before any credits are spent.

    uv run python games/yorimichi/tools/hidamari_props.py concept [--only kei_truck,postbox] [--dry-run]
    uv run python games/yorimichi/tools/hidamari_props.py model [--only ...] [--dry-run] [--approval "..."]
    uv run python games/yorimichi/tools/hidamari_props.py sheet

Each prop lives in games/yorimichi/assets/hidamari/props/<slug>/: concept.jpg with concept.json (the ledger record
of the paid call, atelier.ai.ledger.run_once: a slug with a record is never painted again; rename the record to
concept.rejected-N.json and the picture likewise to repaint), then job.json (the Tripo settings, task id and credits)
and <slug>.glb, the model with its texture made a 1024 JPEG. The model stage is tools/treehouse_props.py's: Tripo P2
image-to-model with a detailed texture, a task submitted once and resumed by id, an uncertain POST never repeated
(atelier.ai.tripo_asset). The full-size concepts and the Tripo work folders stay in build/yorimichi/hidamari/.
world/regions/hidamari/props.py (Blender) fits each GLB to SIZE for the game.
"""
import sys as _sys; from pathlib import Path as _Path; _sys.path.insert(0, str(_Path(__file__).resolve().parents[1] / 'world')); import yori  # noqa: E402
_sys.path.insert(0, str(_Path(__file__).resolve().parent))
import argparse, time
from concurrent.futures import ThreadPoolExecutor

from treehouse_art import MODEL, QUALITY, compact, rel, sha, sheet as contact_sheet, sunburst

OUT = yori.ASSETS / 'hidamari' / 'props'
WORK = yori.OUT / 'hidamari'
ORIGINALS, TRIPO = WORK / 'concepts', WORK / 'tripo'
CONCEPTS = yori.ASSETS / 'hidamari' / 'concepts'
STYLE_REFS = [CONCEPTS / 'street_ew140.jpg', CONCEPTS / 'station.jpg']
SIZE = '1024x1024'

STYLE = ('Paint ONE object alone for 3D reconstruction: shown whole, in a three-quarter front view from slightly above, '
         'centred with a clear margin all round, on a plain flat light-grey background, soft even light, no cast '
         'shadow, no floor, no text, letters or logos anywhere, nothing else in the picture. Images 1 and 2 show the '
         'art direction of the game it is for, Yorimichi, a stylised Japanese autumn town: paint the object in that '
         'same warm hand-painted style, chunky readable shapes, gently rounded edges, matte colours with soft '
         'variation and light weathering, believable real-world proportions, no photographic noise, no glossy '
         'highlights. Every part must be solid and connected; nothing floating. The object: ')

# slug: (the object, its size in metres for the game: longest side, or height for upright things)
PROPS = {
    'vending_machine': ('a Japanese drink vending machine, a tall white-and-red metal cabinet with two rows of small '
                        'coloured drink bottles behind a clear front panel, round buttons under each, a coin slot and '
                        'a dark pick-up opening at the bottom; no writing', 1.85),
    'kei_truck': ('a small white Japanese kei pickup truck, a boxy flat-nosed cab and a low open cargo bed with fold-'
                  'down sides, a few wooden crates of persimmons in the bed, small black wheels', 3.4),
    'scooter': ('a small cream-and-red Japanese step-through moped with a front basket and a rear rack, round '
                'headlight, black seat, standing on its side stand', 1.8),
    'bicycle': ('a Japanese town bicycle (mamachari) in muted mint green with a black wire front basket, a chain '
                'guard, mudguards and a rear rack, standing on its kickstand', 1.75),
    'postbox': ('a classic round red Japanese post box on a short pedestal, a domed top, a dark letter slot under '
                'the rim and a small white plate on the front; no writing', 1.45),
    'phone_booth': ('a small Japanese public telephone booth, a narrow box with a pale green roof and frame and '
                    'glass sides, a green payphone on a small shelf inside', 2.3),
    'bus_stop': ('a small rural Japanese bus stop shelter of weathered wood with a corrugated metal roof, a long '
                 'wooden bench inside and a round sign on a pole beside it with no writing', 3.2),
    'stone_lantern': ('a tall Japanese granite stone lantern (ishi-doro): a round base, a slim column, a lamp box with '
                      'a square window, a wide curved roof and a jewel finial, patches of moss', 2.0),
    'komainu': ('a weathered granite komainu guardian lion-dog sitting on a square stone plinth, curly mane, open '
                'mouth, one front paw resting on a ball, moss in the crevices', 1.1),
    'jizo': ('a small round-headed stone jizo statue with a gentle face, wearing a faded red cloth bib and a red '
             'knitted cap, standing on a low stone base with a little offering cup', .8),
    'water_basin': ('a shrine purification basin: a rectangular carved granite trough full of still water, a bamboo '
                    'spout feeding it, three long-handled wooden ladles resting across it, under a small wooden '
                    'roof on four posts', 2.2),
    'sake_barrels': ('a stack of six straw-wrapped sake barrels (komodaru) on a low wooden stand, three, two and one, '
                     'tied with ropes, their round wooden lids facing front, the straw wrapping painted with simple '
                     'red and indigo bands and no writing', 1.6),
    'produce_stand': ('a small wooden street-side vegetable and fruit stall: a sloping table of shallow baskets with '
                      'persimmons, mandarins, daikon, pumpkins and cabbages, a small fabric awning on two poles', 2.0),
    'garbage_station': ('a Japanese neighbourhood garbage collection point: a low folding green metal mesh cage with '
                        'a lid, a few tied white and blue bags inside and a folded blue net on top', 1.6),
    'potted_plants': ('a crowded cluster of potted plants as seen outside Japanese houses: a small wooden step stand '
                      'with clay and blue-glazed pots of a little pine bonsai, ferns, red geraniums, a morning glory '
                      'on a bamboo frame and an aloe, with a watering can', 1.2),
    # The second set (the houses' sides and the shop streets, after the concepts' clutter)
    'ac_unit': ('an outdoor air-conditioner unit of a Japanese house, a pale beige-grey metal box with a round fan '
                'grille on the front, on a low metal stand, with a short insulated pipe and a grey cable running up '
                'from its side', .85),
    'propane_tanks': ('two tall grey propane gas cylinders standing side by side on a small concrete pad beside a '
                      'house, each with a domed top, a valve under a round collar and a short chain around them both', 1.3),
    'curve_mirror': ('a Japanese road curve mirror: a round convex traffic mirror in an orange frame with a small hood, '
                     'on a tall slim orange metal pole with a concrete foot', 3.0),
    'hokora': ('a small roadside Shinto shrine (hokora): a little wooden shrine house with a gabled copper-green roof '
               'and closed lattice doors, on a stacked stone plinth, a tiny red torii in front and a small offering '
               'of a cup and fruit', 1.5),
    'tanuki': ('a glazed Shigaraki ceramic tanuki statue as stood outside Japanese shops and inns: a round-bellied '
               'standing raccoon dog in a straw hat, holding a sake flask in one hand and a ledger in the other, '
               'warm brown glaze; no writing', 1.0),
    'fire_buckets': ('a Japanese street fire-bucket stand: a small red metal rack holding a pyramid of six round red '
                     'buckets, with a red metal water box beneath; no writing', 1.1),
    'drink_crates': ('a stack of plastic drink crates outside a Japanese liquor shop: yellow and red crates, the top '
                     'ones holding brown glass bottles, beside two empty crates on the ground; no writing', 1.2),
    'planter_box': ('a long low wooden planter box outside a Japanese shop, full of orange and yellow potted '
                    'chrysanthemums and a few green leafy plants', 1.6),
    'laundry_stand': ('a Japanese garden laundry drying stand: two metal stands holding a long pole, a few towels, '
                      'a shirt and a folded futon hanging over it, and wooden clothes pegs', 2.4),
    'street_bench': ('a weathered wooden street bench with a slatted seat and back on dark metal legs, as outside a '
                     'Japanese sweet shop, a red cloth runner and a small round cushion on the seat', 1.8),
    'bonsai_shelf': ('a two-tier wooden display shelf of bonsai trees in shallow glazed pots, a little pine, a maple '
                     'in red autumn leaf and a juniper, with small stones', 1.5),
    'yatai': ('a Japanese wooden street food cart (yatai) parked closed for the day: a wheeled wooden counter '
              'with a small sloping roof, a rolled-up indigo cloth curtain, a few stools stacked by it and red paper '
              'lanterns hanging unlit; no writing', 2.6),
    # The third set (the station and the parking pads, after the station and house concepts)
    'kei_car': ('a small white Japanese kei car, a tall boxy two-box hatchback with round headlights, black bumpers '
                'and small wheels, parked; no writing and a blank number plate', 3.4),
    'taxi': ('a Japanese town taxi, a boxy dark-green and cream four-door saloon with a small roof lamp, chrome '
             'bumpers and white seat covers inside; no writing and a blank number plate', 4.6),
    'town_bus': ('a small Japanese local route bus in cream and green, rounded corners, a big front windscreen, a '
                 'folding front door and a destination board left blank; no writing anywhere', 9.0),
    'bicycle_shelter': ('a Japanese bicycle parking shelter: a long low corrugated metal roof on slim green posts '
                        'over a metal rack, five town bicycles parked in it side by side', 5.5),
    'lantern_sign': ('a Japanese shop front standing sign: a tall red paper lantern (chochin) hung on a small wooden '
                     'stand on a low base, beside a blank wooden menu board; no writing', 1.8),
}


def prompt_for(slug):
    return STYLE + PROPS[slug][0] + '.'


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
                          'execution': 'games/yorimichi/tools/hidamari_props.py',
                          'purpose': 'Hidamari street prop concept for Tripo'}, generate)
    except Exception as e:  # noqa: BLE001 - kept by the ledger as submission_uncertain; never retried here
        print(slug, 'FAILED', type(e).__name__, flush=True); return slug, type(e).__name__
    print(slug, f'ok {time.time() - t:.0f}s', flush=True)
    return slug, None


def model(slug, faces, approval, dry):
    import treehouse_props
    return treehouse_props.model(slug, faces, approval, dry, out=OUT, tripo=TRIPO, originals=ORIGINALS,
                                 stage='hidamari_prop', record='concept.json')


def sheet():
    return contact_sheet([(OUT / s / 'concept.jpg', s) for s in PROPS], yori.REVIEW / 'hidamari' / 'props-sheet.jpg',
                         384, 384, 5)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('stage', choices=['concept', 'model', 'sheet'])
    ap.add_argument('--only', default=''); ap.add_argument('--dry-run', action='store_true')
    ap.add_argument('--faces', type=int, default=12000); ap.add_argument('--concurrency', type=int, default=5)
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
