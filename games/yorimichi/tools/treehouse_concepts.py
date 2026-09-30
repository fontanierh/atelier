#!/usr/bin/env python3
"""Tree house concepts on Sunburst, steered by stills of the game.

    uv run python games/yorimichi/tools/treehouse_concepts.py [--only glimpse-dusk,room-day] [--dry-run]

Each concept is one view (glimpse, reveal, lookout, overview, room) in one light (day, dusk). Writes <slug>.jpg (the
committed copy), <slug>.prompt.txt and <slug>.provenance.json into games/yorimichi/assets/treehouse/concepts/; the
full-size PNG goes to build/yorimichi/treehouse/originals/concepts/ and a contact sheet to
build/yorimichi/review/treehouse/. Existing JPEGs are skipped, so a rerun only fills the gaps (rename one to
<slug>.rejected-N.jpg, kept out of git, to repaint it). Model gpt-image-2.5-sunburst, quality high, 1536x1024, through
/v1/images/edits with the game stills, which are looked for in build/yorimichi/treehouse/scout/ (player/, r01/, r02/:
captures of the west hillside, the lake cabin and the hamlet). The key comes from OPENAI_API_KEY (or the ignored .env).
"""
import sys as _sys; from pathlib import Path as _Path; _sys.path.insert(0, str(_Path(__file__).resolve().parents[1] / 'world')); import yori  # noqa: E402
_sys.path.insert(0, str(_Path(__file__).resolve().parent))
import argparse, json, sys, time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

from treehouse_art import CONCEPTS as OUT, MODEL, QUALITY, SCOUT, SHEETS, keep, redact, rel, sha, sheet as contact_sheet, sunburst

SIZE = '1536x1024'

STILLS = {
    'trail': (SCOUT/'player/P5-air-station-trail.png', 'the actual air-station trail where the entrance goes: a dirt path in a sunken cutting with grassy banks'),
    'forest': (SCOUT/'player/P1-upper-slope-down.png', 'the actual forest on the hillside where the tree house stands, with the player child for scale'),
    'slope': (SCOUT/'r02/A6-mid-slope-across.png', 'the actual hillside under the canopy, sloping down to the left'),
    'canopy': (SCOUT/'r02/A10-canopy-low-end.png', 'the actual view from just above the treetops at this spot: the autumn canopy, then the sea and the rocky island with its temple'),
    'aerial': (SCOUT/'r01/A3-aerial.png', 'the actual hillside forest seen from the air'),
    'cabin': (SCOUT/'r01/S1-lake-cabin.png', 'an existing building in the game, the lake cabin: use its materials and level of detail'),
    'hamlet': (SCOUT/'r01/S2-hamlet.png', 'the existing village buildings and garden props: use their materials and level of detail'),
}

STYLE = (
    'Concept art for a new hidden place in Yorimichi, a stylised low-poly Japanese autumn exploration game. The '
    'numbered images are real screenshots of the game: match their art direction exactly. Simple low-poly shapes '
    'with flat colours and soft painterly shading; the same autumn forest (vermilion and orange maples, golden '
    'ginkgo, deep teal-green cedars and pines, tall straight dark plum-brown trunks, a dark green forest floor with '
    'scattered red leaves); the same building materials (aged warm timber, cream plaster, dark blue-grey tiles). '
    'The player is a small child in a yellow t-shirt over white long sleeves and khaki cargo trousers, and '
    'everything is sized for him. It must look like a polished, achievable game scene built from simple meshes: '
    'not photoreal, and not an elaborate illustration that could not be modelled.'
)

PLACE = (
    'THE PLACE: a secret tree house hidden on a forested hillside, a children\'s "himitsu kichi" (secret base) '
    'built by the island\'s kids over many summers from planks, crates, rope, old sailcloth awnings and glass '
    'fishing floats used as lamps. Cosy and a little ethereal: warm paper lanterns strung along the rails, warm '
    'round windows, cloth noren curtains in doorways, glass wind chimes (fuurin) hanging everywhere, patched mossy '
    'roofs of bark shingles with a few blue-grey tiles. From outside it looks like ONE small hut in one old tree, '
    'half hidden in the leaves. Once you climb in, walkways and rope bridges reach across dozens of trees down the '
    'slope: little houses on many trees, stairs wrapped around trunks, platforms at several heights, a slide '
    'spiralling round a trunk, a zip line, a pulley basket, a crow\'s nest with a telescope, a small bell to ring. '
    'At its heart stands one ancient, thick camphor tree with a shimenawa rope round its trunk, holding the biggest '
    'room. A few old, thick trees anchor it among the ordinary forest; no single giant tree dwarfs the forest.'
)

AVOID = ('No photorealism, no elven white stone, no neon, no creatures or spirits, no other people, no text, '
         'labels, borders or collage panels.')

LIGHT = {
    'day': 'LIGHT: the game\'s soft late-afternoon daylight, warm sunbeams slanting through the leaves (komorebi), '
           'drifting maple leaves, calm and gentle.',
    'dusk': 'LIGHT: dusk at blue hour. The forest turns deep blue-teal, every lantern, window and glass float glows '
            'warm orange, fireflies drift between the trunks and a thin mist lies low under the canopy; still the '
            'same simple game shading.',
}

VIEWS = {
    'glimpse': (['trail', 'forest', 'cabin'],
        'VIEW: player-height view along the trail of Image 1, the child standing on the path. In the LEFT bank '
        'there is a narrow gap that is easy to miss: a few rough stepping stones, a rope handrail and one small '
        'paper lantern lead down into the trees. Beyond the gap, partly hidden by leaves, one small weathered hut '
        'sits in the fork of an old tree about 4 m up, with a rope ladder hanging down and one warm window. It must '
        'look SMALL and modest: a single hut, none of the rest of the tree house visible.'),
    'reveal': (['forest', 'slope', 'cabin'],
        'VIEW: the child has just climbed through the trapdoor onto the first platform and looks out down the '
        'hillside, seen from just behind him. The hidden tree city unfolds below and ahead: dozens of trees linked '
        'by plank walkways and sagging rope bridges, little houses and platforms stepping down the slope at several '
        'heights, the ground falling away so the far walkways are high above the forest floor, lanterns strung '
        'everywhere, the heart camphor tree with its big room in the middle distance. A sense of wonder: it is far '
        'bigger than the small hut suggested.'),
    'lookout': (['canopy', 'forest', 'cabin'],
        'VIEW: from the crow\'s nest at the top of the tree house, just above the canopy: a small railed platform '
        'with a telescope, a bell, a patched sailcloth awning and wind chimes, the child leaning on the rail. Below '
        'and around, roofs, bridges and little flags of the tree house poke through the canopy; beyond, the same '
        'sea and island as Image 1.'),
    'overview': (['aerial', 'cabin', 'forest'],
        'VIEW: three-quarter aerial view from the south-east, as if from the airship, of the whole hillside: the '
        'tree house spread across the slope, through and under the canopy (the canopy thinned enough to read the '
        'layout); along the top edge, the dirt trail in its cutting with the small entrance hut; walkways and '
        'houses stepping down the slope to the lookout at the lower end. A clear, readable layout that could be '
        'built.'),
    'room': (['cabin', 'hamlet', 'forest'],
        'VIEW: inside the big room in the heart tree. The living camphor trunk rises through the middle of a low, '
        'warm wooden room; a round window looks out onto the autumn canopy and another little house across a rope '
        'bridge; a reading loft with a ladder, cushions and patchwork quilts, a hammock, a small kettle on a '
        'charcoal brazier, shelves of treasures (shells, a kite, jars, a hand-drawn map pinned up with no readable '
        'writing), paper lanterns and a wind chime at the window, the child sitting on a cushion.'),
}


def concepts():
    for view, (refs, text) in VIEWS.items():
        for light in LIGHT:
            numbered = ' '.join(f'Image {i + 1} is {STILLS[r][1]}.' for i, r in enumerate(refs))
            prompt = '\n\n'.join([STYLE + ' ' + numbered, PLACE, text, LIGHT[light], AVOID])
            yield f'{view}-{light}', refs, prompt


def run(slug, refs, prompt):
    (OUT/f'{slug}.prompt.txt').write_text(prompt + '\n')
    started = datetime.now(timezone.utc).isoformat(); t = time.time(); error = usage = record = None; outputs = {}
    try:
        png, usage = sunburst(prompt, SIZE, [STILLS[r][0] for r in refs])
        digest, record = keep(png, 'concepts', slug, OUT/f'{slug}.jpg'); outputs[f'{slug}.png'] = digest
    except Exception as e:  # noqa: BLE001 - recorded in provenance, the batch goes on
        error = redact(e)[:600]
    prov = dict(stage='treehouse-concept', concept=slug, requested_model=MODEL, quality=QUALITY, size=SIZE,
                endpoint='/v1/images/edits', execution='games/yorimichi/tools/treehouse_concepts.py',
                prompt_file=f'{slug}.prompt.txt', prompt_sha256=sha(prompt.encode()),
                reference_files={rel(STILLS[r][0]): sha(STILLS[r][0].read_bytes()) for r in refs},
                started_at=started, finished_at=datetime.now(timezone.utc).isoformat(),
                elapsed_seconds=round(time.time()-t, 1), usage=usage, outputs=outputs, error=error, compact_copy=record)
    (OUT/f'{slug}.provenance.json').write_text(json.dumps(prov, indent=2) + '\n')
    return slug, error, prov['elapsed_seconds']


def sheet():
    return contact_sheet([(OUT/f'{v}-{l}.jpg', f'{v}-{l}') for v in VIEWS for l in LIGHT], SHEETS/'concepts-sheet.jpg', 768, 512, 2)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--only', default='')
    ap.add_argument('--dry-run', action='store_true', help='print the prompts (also of existing concepts) and stop')
    ap.add_argument('--concurrency', type=int, default=5)
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    wanted = [c for c in concepts() if not args.only or c[0] in args.only.split(',')]
    todo = [c for c in wanted if not (OUT/f'{c[0]}.jpg').exists()]
    missing = sorted({rel(STILLS[r][0]) for _, refs, _ in todo for r in refs if not STILLS[r][0].exists()})
    if args.dry_run:
        for slug, refs, prompt in wanted:
            print(f'--- {slug} {refs}{"" if (slug, refs, prompt) in todo else " (exists, skipped)"}\n{prompt}\n')
        if missing: print(f'missing stills: {missing}')
        return
    if missing:
        sys.exit(f'missing stills: {missing}')
    if todo:
        from atelier.env import require
        require('OPENAI_API_KEY')   # loads the ignored .env; stops with a clear message, never prints the value
    print(f'{len(todo)} to generate, {len(wanted)-len(todo)} already there')
    with ThreadPoolExecutor(args.concurrency) as pool:
        for slug, error, secs in pool.map(lambda c: run(*c), todo):
            print(f'{slug}: {"FAILED " + error if error else "ok"} ({secs} s)', flush=True)
    sheet()


if __name__ == '__main__':
    main()
