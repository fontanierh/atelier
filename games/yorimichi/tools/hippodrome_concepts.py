"""Sunburst concepts for the Hidamari hippodrome: the reference the race track, its buildings and the race HUD are
modelled from.

paint: gpt-image-2.5-sunburst, quality high, 1536x1024, one image per concept through atelier.ai.ledger (an existing
provenance file means the call was made: it is never sent again). Context images are the site plan
(build/yorimichi/hippodrome/inputs/site_plan_A.jpg, drawn from the generated terrain and city data) and the approved
Hidamari art-direction concepts. The committed compact copies and their provenance go to assets/hippodrome/concepts/,
the full PNGs to build/yorimichi/hippodrome/originals/.

    uv run python games/yorimichi/tools/hippodrome_concepts.py [slug ...]
"""
import sys as _sys; from pathlib import Path as _Path; _sys.path.insert(0, str(_Path(__file__).resolve().parent)); import treehouse_art as art  # noqa: E401,E402
import json, sys, time
from concurrent.futures import ThreadPoolExecutor
from atelier.ai import ledger
from atelier.env import load
import yori

OUT = yori.ASSETS / 'hippodrome' / 'concepts'
WORK = yori.OUT / 'hippodrome'
STYLE = yori.ASSETS / 'hidamari' / 'concepts'
SIZE = '1536x1024'
BASE = ('Concept art for Yorimichi, a stylised Japanese autumn exploration game made in Unreal: a polished commercial '
        'stylised look (Ghibli-inspired and painterly like Breath of the Wild), hand-crafted, cosy and lived-in, '
        'warm afternoon sunlight, red and orange maples, yellow ginkgo and deep green cedars, a snowcapped volcanic '
        'summit to the north. It must read as a believable real-time game frame built from meshes, textures and '
        'foliage, not a loose illustration. No text, no logos, no watermark unless asked for. ')
CONCEPTS = {
    'aerial': dict(
        refs=[WORK / 'inputs' / 'site_plan_A.jpg', STYLE / 'canopy_north_aerial.jpg', STYLE / 'temple_hillside.jpg'],
        prompt='Image 1 is the true-scale site plan, north up: the oval marked A is the new hippodrome, a 234 x 114 m '
               'stadium-shaped oval with a 14 m wide dirt racing track, a grass infield and the grandstand (red bar) on '
               'its south side, on a flat forest shelf 90 m north of the city of Hidamari (blue roofs and streets at the '
               'bottom). Images 2 and 3 set the art direction. Paint a high three-quarter aerial view from the '
               'south-east, looking north-west past the grandstand and along the home straight, the snowcapped summit '
               'behind. Design it as a small, charming countryside racecourse in rural Japan (Hidamari Keibajo): a '
               'raked dirt track ringed by white timber running rails, a lush infield with a small pond, a few maples '
               'and a judges\' tower; a long wooden grandstand with a dark tiled hip roof, timber posts and stepped '
               'seating facing the finish post; a white finish post with a red disc; an eight-stall starting gate '
               'parked on the back straight; a long low stable block with paddock and saddling ring behind the '
               'grandstand; paper lanterns and red banners; a lane leading south into the city. The autumn forest '
               'wraps tightly around the clearing.'),
    'grandstand': dict(
        refs=[STYLE / 'temple_hillside.jpg', STYLE / 'sunlit_park.jpg'],
        prompt='Images 1 and 2 set the art direction. Eye-level view from the front row of the wooden grandstand of '
               'the Hidamari hippodrome as a race thunders past the finish post: six horses at full gallop on the dirt '
               'track, each ridden by a young adventurer-style rider in a coloured tunic and scarf (no jockey silks, '
               'no helmets with logos), kicking up dust, white running rails in the foreground, the grass infield '
               'with its pond and judges\' tower beyond, the autumn forest ringing the course and the snowcapped '
               'summit behind. Horses are stylised, sturdy and expressive: bay, chestnut, dapple grey, black, white, '
               'pinto. Spectators in yukata and autumn coats cheer, paper lanterns hang from the grandstand eaves.'),
    'kit': dict(
        refs=[STYLE / 'station.jpg'],
        prompt='Image 1 sets the materials and art direction. A clean modelling reference sheet on a plain warm-grey '
               'background, every object isolated, evenly lit and seen in a three-quarter view, no overlaps, for '
               'building game assets: (1) the long wooden grandstand with dark tiled hip roof, timber posts, stepped '
               'bench seating and a central judges\' balcony; (2) an eight-stall green metal starting gate with '
               'numbered doors on rubber wheels; (3) a white finish post with a red disc and a small elevated '
               'timber judges\' box; (4) three straight and one curved section of white timber running rail; '
               '(5) a tote and results board in painted timber with a small clock (numbers only, no words); '
               '(6) a low timber stable block with stall doors and hay; (7) a round saddling-ring fence; '
               '(8) a furlong marker post, a red race banner on a pole and a hanging paper lantern.'),
    'hud': dict(
        refs=[STYLE / 'arrival_road.jpg'],
        prompt='Image 1 sets the art direction for the world. In-game screenshot mock-up of the horse race gameplay, a '
               'rhythm game played at full gallop: third-person chase camera behind and above a young rider on a bay '
               'horse galloping along the dirt track of the Hidamari hippodrome, rival riders on chestnut, grey and '
               'black horses close alongside, white rails, the grandstand and autumn forest beyond, motion and dust. '
               'The rhythm interface sits in the lower centre: a four-lane note highway drawn in perspective, like a '
               'guitar game, with round gem notes in four colours (green, red, blue, yellow, matching the four face '
               'buttons) scrolling toward a hit line of four rings; one note bursting in a gold "PERFECT" flash; a '
               'combo counter "x24" and a stamina/whip gauge shaped like a horseshoe. A clean race HUD: "2nd / 6" '
               'position, "Lap 2/3", a small minimap of the oval with coloured dots, and a timer. Stylish, readable, '
               'warm paper-and-lacquer UI styling.'),
}


def paint(slug):
    spec = CONCEPTS[slug]
    record = OUT / f'{slug}.json'
    if record.exists():
        return slug, 'kept (already painted)'
    prompt = BASE + spec['prompt']
    meta = dict(model=art.MODEL, quality=art.QUALITY, size=SIZE, endpoint='/v1/images/edits', prompt=prompt,
                references={art.rel(p): art.sha(p.read_bytes()) for p in spec['refs']},
                purpose='Hidamari hippodrome and horse race concept', execution='games/yorimichi/tools/hippodrome_concepts.py')

    def call():
        t = time.time()
        png, usage = art.sunburst(prompt, SIZE, spec['refs'])
        original = WORK / 'originals' / f'{slug}.png'; original.parent.mkdir(parents=True, exist_ok=True)
        original.write_bytes(png)
        return dict(usage=usage, png_sha256=art.sha(png), seconds=round(time.time() - t, 1),
                    compact_copy=art.compact(png, OUT / f'{slug}.jpg', 'concepts'))
    try:
        ledger.run_once(record, meta, call)
    except Exception as error:  # noqa: BLE001
        return slug, 'failed: ' + art.redact(error)
    return slug, 'painted'


def main():
    load()
    slugs = sys.argv[1:] or list(CONCEPTS)
    OUT.mkdir(parents=True, exist_ok=True)
    with ThreadPoolExecutor(len(slugs)) as pool:
        for slug, status in pool.map(paint, slugs):
            print(slug, status, flush=True)


if __name__ == '__main__':
    main()
