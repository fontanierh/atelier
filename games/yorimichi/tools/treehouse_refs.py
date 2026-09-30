#!/usr/bin/env python3
"""Tree house references on Sunburst: one master overview that fixes the look of all ten places, then one
reference per view, each given the whole context so they agree with each other.

    uv run python games/yorimichi/tools/treehouse_refs.py [--only master] [--dry-run]

Context every image gets: the plan map and side view, the approved concepts (assets/treehouse/concepts), the game's
own style stills, and, for the views, the master overview and the in-game blockout capture of that view. Writes
<slug>.jpg (the committed copy), .prompt.txt and .provenance.json into games/yorimichi/assets/treehouse/refs/; the
full-size PNG goes to build/yorimichi/treehouse/originals/refs/ and a contact sheet to build/yorimichi/review/treehouse/.
Existing JPEGs are skipped (rename one to <slug>.rejected-N.jpg, kept out of git, to repaint it). Model
gpt-image-2.5-sunburst, quality high, 1536x1024, through /v1/images/edits. The key comes from OPENAI_API_KEY (or the
ignored .env).

Context that is not in git, made again by the world scripts and the game: the plan views of the layout in
build/yorimichi/review/treehouse/plan/ (world/regions/treehouse/plan_views.py), and in build/yorimichi/treehouse/,
scout/ (game stills of the hillside, the canopy and the lake cabin) and captures/blockout-r01/<view>.jpg or .png (the
blockout capture of each view). The cameras and place positions of those captures are committed beside the
references (cameras.json, places.json).
The master is painted and checked first (--only master); the views then come in waves, each one seeing the finished
references of its neighbours.
"""
import sys as _sys; from pathlib import Path as _Path; _sys.path.insert(0, str(_Path(__file__).resolve().parents[1] / 'world')); import yori  # noqa: E402
_sys.path.insert(0, str(_Path(__file__).resolve().parent))
import argparse, json, sys, time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

from treehouse_art import (CAPTURES, CONCEPTS as C, MODEL, PLAN, QUALITY, REFS as OUT, SCOUT as S, SHEETS, keep, redact,
                           rel, sha, sheet as contact_sheet, sunburst)

SIZE = '1536x1024'

CONTEXT = {
    'plan': (PLAN/'plan-map.png', 'the PLAN, seen from above with north up: where every place stands, its '
             'deck shape, which side its hut is on, and every rope bridge. It is the ground truth for the layout. '
             'Its labels, numbers and legend are for you only'),
    'section': (PLAN/'plan-section.png', 'the SIDE VIEW along the main path from the trail (left, north) '
                'down the slope to the lookout (right, south), true scale: the ground falls away so the far '
                'decks stand high above the forest floor'),
    'overview': (C/'overview-day.jpg', 'approved concept art of the whole tree house from the air'),
    'reveal': (C/'reveal-day.jpg', 'approved concept art: the view from the first porch'),
    'lookout': (C/'lookout-day.jpg', 'approved concept art: the crow\'s nest over the canopy, with the sea and '
                'the island'),
    'room': (C/'room-day.jpg', 'approved concept art: inside the Heart room'),
    'glimpse': (C/'glimpse-day.jpg', 'approved concept art: the little hut glimpsed from the trail'),
    'aerial': (S/'r01/A3-aerial.png', 'a real screenshot of the game: this exact hillside forest from the air'),
    'forest': (S/'player/P1-upper-slope-down.png', 'a real screenshot of the game: the forest on this hillside, '
               'with the player child for scale'),
    'canopy': (S/'r02/A10-canopy-low-end.png', 'a real screenshot of the game: the view from just above the '
               'canopy at the lower end, the sea and the rocky island with its temple'),
    'cabin': (S/'r01/S1-lake-cabin.png', 'a real screenshot of the game: the lake cabin, whose materials and '
              'level of detail the tree house must match'),
}

STYLE = (
    'Reference art for a new place in Yorimichi, a stylised low-poly Japanese autumn exploration game. The real '
    'screenshots show the art direction to match exactly: simple low-poly shapes, flat colours, soft painterly '
    'shading; vermilion and orange maples, golden ginkgo, deep teal-green cedars and pines, tall straight dark '
    'plum-brown trunks, a dark green forest floor with red leaves; aged warm timber, dark blue-grey tiles. The '
    'player is a small child in a yellow t-shirt over white long sleeves and khaki cargo trousers. Everything must '
    'look buildable from simple meshes in a game: not photoreal, not an ornate illustration.'
)

HOUSE = (
    'THE TREE HOUSE: a children\'s secret base (himitsu kichi) built by the island\'s kids over many summers from '
    'weathered planks, crates, rope, old sailcloth and glass fishing floats. Cosy and a little ethereal: paper '
    'lanterns strung along the rails, warm round windows, cloth noren in doorways, glass wind chimes, patched '
    'mossy bark-shingle roofs with a few blue-grey tiles. Ten places on ten trees, each deck an octagon of planks '
    'round its trunk with a simple rail, joined by twelve sagging rope bridges with plank floors and rope '
    'handrails, exactly as on the plan:\n'
    '1 Little hut: the only part seen from the trail; one small gable-roofed hut built round the trunk of a maple, '
    'only 3 m up, a door on the trail side reached by stepping stones and a few plank steps, a porch on the far '
    'side.\n'
    '2 Map room: a small gable-roofed hut on a golden ginkgo; maps, books and treasures.\n'
    '3 Heart room: the biggest room, an eight-sided room with a cone-shaped shingle roof built round a very thick, '
    'ancient camphor trunk with a shimenawa rope, a balcony all round, round windows; 11 m up.\n'
    '4 Kitchen: a small hut on a maple with a little clay chimney pipe and drying persimmons.\n'
    '5 Sleeping nest: a small hut on a ginkgo, quilts airing over its rail, a hammock.\n'
    '6 Boat room: an old wooden rowboat, painted faded blue, turned upside down on posts as the roof of an open '
    'room on a maple deck.\n'
    '7 Slide tree: a wooden spiral slide wrapping about one turn round a broadleaf trunk down to the forest floor.\n'
    '8 Pulley deck: a wooden crane arm with a pulley and a basket on a rope.\n'
    '9 Chime tree: a small round landing with no hut, hung with glass wind chimes, where three bridges meet.\n'
    '10 Lookout: a tall bare trunk with stairs spiralling up it to a crow\'s nest well above the canopy, with a '
    'patched sail awning, a telescope, a bell and a small flag.\n'
    'Only the Heart room\'s camphor is really big; the other nine are ordinary old trees among the forest. The '
    'ground falls about 20 m from the trail to the lookout, so the little hut is near the ground and the far '
    'places are 13 to 16 m up, while every deck is at about the same height.\n'
    'ONE BUILDING KIT everywhere, identical in every picture: the same weathered grey-brown planks, the same square '
    'dark posts and timber handrails, the same rope bridges (plank floor, two rope handrails, rope suspenders), '
    'the same mossy bark-shingle roofs with a few blue-grey tiles, the same round windows with a cross frame, the '
    'same warm cream paper windows and paper lanterns.'
)

AVOID = ('No text, letters, numbers, labels, arrows or diagram marks anywhere in the picture; no borders or '
         'collage panels; no photorealism, no neon, no creatures, no other people.')

DAY = ('LIGHT: the game\'s soft late-afternoon daylight, warm sunbeams slanting through the leaves, drifting '
       'maple leaves.')

MASTER = (
    'VIEW: a high three-quarter aerial view of the whole tree house, from above the forest in the SOUTH, looking '
    'NORTH up the hillside. Read the plan with this camera: the plan\'s left (west) is the picture\'s left, the '
    'plan\'s bottom (south) is nearest to the viewer, and the trail runs across the top of the picture, far away '
    'in its cutting. So the Lookout\'s crow\'s nest is in the near left, the Chime tree and the Slide tree near '
    'the middle, the Pulley deck and Sleeping nest on the left, the Boat room and Kitchen on the right, the Heart '
    'room in the centre, the Map room behind it on the left, and the Little hut small, far away and almost hidden '
    'just below the trail. The canopy is thinned just enough that every place and every bridge on the plan can be '
    'seen and counted: ten places, twelve bridges, nothing extra. This picture becomes the reference sheet for '
    'every place, so each place must be clear and distinct.'
)

# Two masters were painted from this same prompt and the second was chosen as the look guide; only it is kept. It
# was painted before the ONE BUILDING KIT paragraph joined HOUSE, so its prompt.txt lacks that paragraph.
JOBS = {
    'master': (['plan', 'section', 'overview', 'reveal', 'lookout', 'aerial', 'cabin'], MASTER),
}

# ------------------------------------------------------------------ one reference per view, over the blockout
CONTEXT['master'] = (OUT/'master.jpg', 'the MASTER overview, the look guide for the whole tree '
                     'house: take the style of each place from it (hut shapes, roofs, materials, props, lanterns), '
                     'but NOT positions, which come from the blockout capture')

LOOK = {
    'entry': 'the Little hut (a small weathered plank hut with a gable roof of bark shingles, built round a maple trunk)',
    'library': 'the Map room (a small plank hut with a gable roof and a round window, on a golden ginkgo)',
    'heart': 'the Heart room (the big eight-sided room with a cone roof of mossy shingles round the thick camphor trunk)',
    'kitchen': 'the Kitchen (a small hut with a clay chimney pipe and strings of drying persimmons, on a maple)',
    'sleep': 'the Sleeping nest (a small hut with patchwork quilts airing over its rail, on a ginkgo)',
    'boat': 'the Boat room (a faded blue rowboat turned upside down on posts as a roof)',
    'slide': 'the Slide tree (a deck with a wooden spiral slide winding down its trunk)',
    'pulley': 'the Pulley deck (a crane arm with a basket on a rope)',
    'chimes': 'the Chime tree (a small round landing under a hoop of glass wind chimes)',
    'lookout': 'the Lookout (stairs spiralling up a tall trunk inside a four-legged timber tower to the crow\'s nest)',
}
CHILD = ' Add the player child for scale, walking ahead on the bridge, seen from behind, small in the lower third.'
DECK = (' Dress its deck: planks with moss in the corners, rails with paper lanterns and glass floats, a few crates, '
        'potted plants and a rolled rope; keep the deck, rail and bridge shapes of the blockout.')
SUBJECT = {
    'entry-glimpse': (['glimpse', 'forest'], 'VIEW: from the trail, the child standing on the path in the lower '
        'middle. Below the right bank, the small Little hut sits in its maple 3 m above the slope, half hidden in '
        'the leaves, one warm window, plank steps down to stepping stones and a low rope handrail with one small '
        'paper lantern at the gap in the bank. It must look SMALL, modest and alone: nothing else of the tree house '
        'shows. Around and behind the hut there is only ordinary forest, exactly as in the capture: no other huts, '
        'no bridges, no tower, no slide, no chimes.'),
    'entry-inside': (['room', 'cabin'], 'VIEW: inside the Little hut, a tiny cosy room (3 x 2.6 m) built round the '
        'living maple trunk that rises through its middle and out through the roof. Doors on two sides, a round '
        'window and a paper window; pegs with a straw hat and a small backpack, a low shelf with jars of acorns and '
        'shells, a rolled rug, a hanging lantern, a noren curtain in the far doorway glowing with the brighter '
        'forest beyond, inviting you through.'),
    'entry-reveal': (['reveal', 'forest'], 'VIEW: the REVEAL, from the Little hut\'s porch looking down the '
        'hillside: the child stands at the rail in the lower middle, seen from behind. The whole hidden tree house '
        'opens out below and ahead: rope bridges, the Map room close by, the Heart room\'s cone roof in the middle, '
        'more huts and decks stepping away across the trees, the Lookout tower far away above the canopy. The '
        'porch itself: a patched sail awning overhead, a bench made from a crate, lanterns on the rail. A sense of '
        'wonder: far bigger than the small hut suggested.'),
    'library-approach': (['overview', 'reveal'], 'VIEW: on the first rope bridge, arriving at the Map room.'+DECK+CHILD),
    'library-inside': (['room', 'cabin'], 'VIEW: inside the Map room (a 2.4 x 2.0 m hut): a big hand-drawn map of '
        'the island pinned on the wall (drawings only, no readable writing), a low desk made from a crate with a '
        'compass, a magnifying glass and rolled charts, shelves of books, jars, shells and a paper kite, a small '
        'globe, a floor cushion; the round window shows the forest, the doorway has a noren curtain.'),
    'heart-approach': (['overview', 'room'], 'VIEW: on the long rope bridge from the Map room, arriving at the '
        'Heart room: its eight walls with round windows and a paper window, the balcony all round, the cone roof '
        'of mossy shingles, the huge camphor trunk rising through the roof into its crown, the shimenawa rope '
        'visible through the door.'+DECK+CHILD),
    'heart-inside': (['room', 'cabin'], 'VIEW: inside the Heart room: the living camphor trunk (2.3 m wide) with its '
        'shimenawa rope and paper shide stands in the middle of the eight-sided room; the ceiling is the underside '
        'of the cone roof with eight rafters; the big open round window frames the view down the slope to the '
        'Chime tree and the Lookout tower; cushions and patchwork quilts, a low table with a kettle on a charcoal '
        'brazier, shelves of treasures, a hammock slung from the trunk to a wall post, paper lanterns, a wind '
        'chime in the window, the child sitting on a cushion.'),
    'kitchen-approach': (['overview', 'cabin'], 'VIEW: from the Heart room\'s balcony onto the short bridge to the '
        'Kitchen hut: a clay chimney pipe with a thread of smoke, persimmons drying on strings under the eaves, a '
        'water barrel by the door.'+DECK+CHILD),
    'kitchen-inside': (['room', 'cabin'], 'VIEW: inside the Kitchen (a 2.4 x 2.0 m hut): a small clay stove '
        '(kamado) with a kettle and a pot, its chimney pipe going up through the roof, shelves of bowls, cups and '
        'jars, a water barrel with a ladle, persimmons and herbs hanging from the rafters, a small table with two '
        'stools made from logs.'),
    'sleep-approach': (['overview', 'reveal'], 'VIEW: on the rope bridge from the Map room to the Sleeping nest: '
        'quilts airing over its rail, a hammock slung under its eaves.'+DECK+CHILD),
    'sleep-inside': (['room', 'cabin'], 'VIEW: inside the Sleeping nest (a 2.4 x 2.0 m hut): two futons with '
        'patchwork quilts and fat pillows on the floor, a hammock across the hut, a small hanging lantern, a shelf '
        'with a picture book and a toy boat, a noren in the doorway.'),
    'boat-approach': (['overview', 'cabin'], 'VIEW: on the rope bridge from the Kitchen to the Boat room: the old '
        'rowboat, painted faded blue with a pale stripe, rests upside down on four posts as the roof of an open '
        'room beside the trunk.'+DECK+CHILD),
    'boat-inside': (['room', 'cabin'], 'VIEW: under the upturned rowboat of the Boat room: its wooden ribs and '
        'planks form the ceiling, two oars and a fishing net hung inside, glass fishing floats, a low bench of '
        'crates with cushions, a rolled sail, a lantern hanging from the keel; the forest beyond on both open sides.'),
    'slide-approach': (['overview', 'reveal'], 'VIEW: on the rope bridge from the Boat room to the Slide tree: the '
        'wooden spiral slide starts from a little gate on the deck and winds down round the trunk, about one turn, '
        'to the forest floor far below.'+DECK+CHILD),
    'slide-foot': (['forest', 'overview'], 'VIEW: from the forest floor at the slide\'s end, looking back up: the '
        'wooden spiral slide winds down round the trunk from the deck 15 m above and runs out onto a soft landing '
        'of straw and fallen leaves; the tree house decks and bridges high above, half hidden in the canopy.'),
    'pulley-approach': (['overview', 'reveal'], 'VIEW: on the rope bridge from the Heart room to the Pulley deck: '
        'the crane arm reaches out from the trunk, a pulley wheel at its tip, a woven basket hanging on its rope '
        'just past the rail, the rope running down to the ground.'+DECK+CHILD),
    'chimes-approach': (['overview', 'reveal'], 'VIEW: on the long rope bridge from the Heart room to the Chime '
        'tree: a small round landing where three bridges meet, under a wooden hoop hung with a dozen glass wind '
        'chimes (fuurin) with paper tails.'+DECK+CHILD),
    'lookout-approach': (['lookout', 'overview'], 'VIEW: on the rope bridge from the Chime tree to the Lookout: the '
        'four-legged timber tower round the tall trunk, stairs spiralling up inside it to the crow\'s nest above '
        'the canopy, with a patched sail awning, a bell and a small flag.'+DECK+CHILD),
    'crow-sea': (['lookout', 'canopy'], 'VIEW: from the crow\'s nest, above the canopy, looking south to the sea: '
        'the child leans on the rail; a brass telescope on a tripod, a bell, the patched sail awning overhead; the '
        'autumn canopy below, then the sea and the rocky island with its temple, as in the canopy screenshot. '
        'The rest of the tree house is behind the camera, out of view: below and ahead there is only untouched '
        'forest canopy, exactly as in the capture, with no huts, bridges, decks or other towers.'),
    'crow-back': (['overview', 'lookout'], 'VIEW: from the crow\'s nest looking back north up the hillside over '
        'the whole tree house: every roof, deck and bridge seen from above through gaps in the canopy, the Heart '
        'room\'s cone roof in the middle, the trail far away at the top.'),
    'overview-south': (['overview', 'aerial'], 'VIEW: the whole finished tree house from the air, from the south, '
        'through and under the canopy.'),
    'overview-east': (['overview', 'aerial'], 'VIEW: the whole finished tree house from the air, from the east, '
        'through and under the canopy.'),
}


def in_frame(shot, places):
    """Places inside the capture's horizontal field of view, left to right, with rough distance."""
    import math
    cx, cy, cz = shot['camera_position']; tx, ty, _ = shot['camera_target']
    f = math.atan2(ty-cy, tx-cx); half = math.radians(shot['fov'])/2; seen = []
    for name, (x, y) in places.items():
        a = math.atan2(y-cy, x-cx)-f; a = (a+math.pi) % (2*math.pi)-math.pi; d = math.hypot(x-cx, y-cy)
        if abs(a) < half*1.05 and d > 1.5:
            side = 'left' if a > half/3 else 'right' if a < -half/3 else 'middle'
            seen.append((-a, name, side, 'near' if d < 12 else 'mid-distance' if d < 30 else 'far'))
    return [f'{LOOK[n]} ({side}, {dist})' for _, n, side, dist in sorted(seen)]


# Views are painted in waves so each one sees the finished references of its neighbours: the south aerial fixes
# every place first, then the three wide views that show many places, then each approach, then the insides.
DEPS = {
    'overview-east': ['overview-south'], 'crow-back': ['overview-south'], 'entry-reveal': ['overview-south'],
    'library-approach': ['entry-reveal', 'overview-south'], 'sleep-approach': ['entry-reveal', 'overview-south'],
    'heart-approach': ['entry-reveal', 'crow-back'], 'kitchen-approach': ['crow-back', 'overview-east'],
    'boat-approach': ['crow-back', 'overview-east'], 'slide-approach': ['crow-back', 'overview-east'],
    'pulley-approach': ['crow-back', 'overview-south'], 'chimes-approach': ['crow-back', 'entry-reveal'],
    'lookout-approach': ['entry-reveal', 'overview-south'],
    'crow-sea': ['lookout-approach'], 'slide-foot': ['slide-approach', 'crow-back'],
    'entry-inside': ['entry-glimpse', 'entry-reveal'], 'library-inside': ['library-approach'],
    'heart-inside': ['heart-approach', 'entry-reveal'], 'kitchen-inside': ['kitchen-approach'],
    'sleep-inside': ['sleep-approach'], 'boat-inside': ['boat-approach'],
}


# Views that must show one place alone: any picture of the whole house in their context leaks into them (the first
# glimpse showed the city from the trail), so they get only the capture, their concept and the style stills.
# crow-sea likewise painted the whole city between the nest and the sea, though the city is behind that camera.
ALONE = {'entry-glimpse', 'crow-sea'}


def finished():
    """Context entries for the references already painted."""
    for sid in SUBJECT:
        CONTEXT['ref:'+sid] = (OUT/f'{sid}.jpg', f'the FINISHED reference already painted for another view of '
                               f'this same tree house ({sid.replace("-", " ")}): every place, material, colour, '
                               f'lantern, rail, roof and prop that appears in both pictures must look identical')


def capture(sid):
    """The blockout capture of a view: the JPEG copy, else the PNG."""
    jpg = CAPTURES/f'{sid}.jpg'
    return jpg if jpg.exists() else CAPTURES/f'{sid}.png'


def place_jobs():
    spec = OUT/'cameras.json'
    if not spec.exists():
        return {}
    shots = {s['id']: s for s in json.loads(spec.read_text())['shots']}
    places = json.loads((OUT/'places.json').read_text())
    jobs = {}
    for sid, (extra, text) in SUBJECT.items():
        if sid not in shots: continue
        key = 'cap:'+sid
        CONTEXT[key] = (capture(sid), 'the BLOCKOUT CAPTURE, a real in-game still of this exact view with '
                        'the tree house as plain untextured shapes: keep its camera, framing and horizon, and the '
                        'position, height and size of every deck, bridge, hut, trunk and stair, and the forest '
                        'around; replace the plain shapes with the finished, detailed look')
        seen = in_frame(shots[sid], places)
        where = (' Places in this view, left to right: '+'; '.join(seen)+'. Some may be hidden by leaves.') if seen and not sid.endswith('-inside') else ''
        refs = ([key] if sid in ALONE else [key, 'master', 'plan'])+extra+['ref:'+d for d in DEPS.get(sid, [])]+['cabin']
        jobs[sid] = (list(dict.fromkeys(refs)), text+where)
    return jobs


JOBS.update(place_jobs())


def prompt_for(refs, view):
    numbered = ' '.join(f'Image {i+1} is {CONTEXT[r][1]}.' for i, r in enumerate(refs))
    return '\n\n'.join([STYLE, numbered, HOUSE, view, DAY, AVOID])


def run(slug, refs, prompt):
    (OUT/f'{slug}.prompt.txt').write_text(prompt + '\n')
    started = datetime.now(timezone.utc).isoformat(); t = time.time(); error = usage = record = None; outputs = {}
    try:
        png, usage = sunburst(prompt, SIZE, [CONTEXT[r][0] for r in refs])
        digest, record = keep(png, 'refs', slug, OUT/f'{slug}.jpg'); outputs[f'{slug}.png'] = digest
    except Exception as e:  # noqa: BLE001 - recorded in provenance, the batch goes on
        error = redact(e)[:600]
    prov = dict(stage='treehouse-reference', reference=slug, requested_model=MODEL, quality=QUALITY, size=SIZE,
                endpoint='/v1/images/edits', execution='games/yorimichi/tools/treehouse_refs.py',
                prompt_file=f'{slug}.prompt.txt', prompt_sha256=sha(prompt.encode()),
                reference_files={rel(CONTEXT[r][0]): sha(CONTEXT[r][0].read_bytes()) for r in refs},
                started_at=started, finished_at=datetime.now(timezone.utc).isoformat(),
                elapsed_seconds=round(time.time()-t, 1), usage=usage, outputs=outputs, error=error, compact_copy=record)
    (OUT/f'{slug}.provenance.json').write_text(json.dumps(prov, indent=2) + '\n')
    return slug, error, prov['elapsed_seconds'], usage


def sheet():
    return contact_sheet([(OUT/f'{s}.jpg', s) for s in JOBS], SHEETS/'refs-sheet.jpg', 768, 512, 2)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--only', default='')
    ap.add_argument('--dry-run', action='store_true', help='print the waves and prompts (also of existing references) and stop')
    ap.add_argument('--concurrency', type=int, default=6)
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True); finished()
    wanted = [(s, refs, prompt_for(refs, view)) for s, (refs, view) in JOBS.items()
              if not args.only or s in args.only.split(',')]
    todo = [j for j in wanted if not (OUT/f'{j[0]}.jpg').exists()]
    coming = {s for s, _, _ in todo}
    missing = sorted({rel(CONTEXT[r][0]) for _, refs, _ in todo for r in refs
                      if not CONTEXT[r][0].exists() and not (r[:4] == 'ref:' and r[4:] in coming)})
    waves, left = [], list(todo)
    while left:
        done = {s for w in waves for s, _, _ in w}
        wave = [j for j in left if all(r[4:] in done or r[4:] not in coming for r in j[1] if r[:4] == 'ref:')]
        if not wave:
            sys.exit(f'circular dependencies: {[j[0] for j in left]}')
        waves.append(wave); left = [j for j in left if j not in wave]
    if args.dry_run:
        for slug, refs, prompt in wanted:
            if (slug, refs, prompt) not in todo:
                print(f'--- {slug} (exists, skipped) {refs}\n{prompt}\n')
        for i, wave in enumerate(waves):
            for slug, refs, prompt in wave:
                print(f'--- wave {i+1} {slug} {refs}\n{prompt}\n')
        if missing: print(f'missing context images: {missing}')
        return
    if missing:
        hint = ' (paint and check the master first: --only master)' if rel(OUT/'master.jpg') in missing else ''
        sys.exit(f'missing context images: {missing}{hint}')
    if todo:
        from atelier.env import require
        require('OPENAI_API_KEY')   # loads the ignored .env; stops with a clear message, never prints the value
    print(f'{len(todo)} to generate in {len(waves)} waves, {len(wanted)-len(todo)} already there', flush=True)
    for i, wave in enumerate(waves):
        with ThreadPoolExecutor(args.concurrency) as pool:
            for slug, error, secs, usage in pool.map(lambda j: run(*j), wave):
                print(f'wave {i+1} {slug}: {"FAILED " + error if error else "ok"} ({secs} s) '
                      f'{usage and usage.get("total_tokens")}', flush=True)
        failed = [s for s, _, _ in wave if not (OUT/f'{s}.jpg').exists()]
        if failed:
            sys.exit(f'stopping after wave {i+1}; failed: {failed}')
    sheet()


if __name__ == '__main__':
    main()
