#!/usr/bin/env python3
"""Concept paintings for the south-west island on Sunburst, steered by stills of the game.

    uv run python games/yorimichi/tools/island_concepts.py [--only far] [--dry-run]

Three views of one redesigned island: `far` repaints the island and the sea in a player's still from a hilltop in the
square, then `boat` (from the dinghy off the landing cove) and `aerial` (the whole footprint) are painted with `far`
as their reference, so the three show the same island. Each view also gets the Blender preview of the island as
island.py builds it from about the same camera, as a layout guide (where the cove, stair, headlands and stacks are),
so the painting stays buildable. Writes <slug>.jpg (the committed copy), <slug>.prompt.txt and <slug>.provenance.json
into games/yorimichi/assets/southwest/concepts/; the full-size PNG goes to
build/yorimichi/southwest/originals/concepts/. Model gpt-image-2.5-sunburst, quality high, 1536x1024, through
/v1/images/edits.

The provenance file is the paid call's record in atelier.ai.ledger: it is written with status `submitted` before the
call is sent and completed (or marked uncertain) afterwards. A view that has a provenance file is never sent again,
whatever its status; rename its files to <slug>.rejected-N.* to paint it again.

The stills are not in git; they are looked for in build/yorimichi/southwest/stills/:
- hilltop-island.png: a player's screenshot of the island from a hilltop in the square (letterbox bars cropped);
- game-look.png: a player's screenshot of the hamlet path, for the game's look;
- layout-far.png, layout-boat.png, layout-aerial.png: the Blender previews of island.py (a small EEVEE render of the
  terrain with its placed trees, boulders, torii and temple) from the far hilltop, the boat and the air.
The key comes from OPENAI_API_KEY (or the ignored .env).
"""
import sys as _sys; from pathlib import Path as _Path; _sys.path.insert(0, str(_Path(__file__).resolve().parents[1] / 'world')); import yori  # noqa: E402
_sys.path.insert(0, str(_Path(__file__).resolve().parent))
import argparse, sys, time

from treehouse_art import MODEL, QUALITY, compact, rel, sha, sunburst

OUT = yori.ASSETS / 'southwest' / 'concepts'
ORIGINALS = yori.OUT / 'southwest' / 'originals' / 'concepts'
STILLS = yori.OUT / 'southwest' / 'stills'
SIZE = '1536x1024'

LAYOUT = ('a plain 3D layout render of the planned island from about this direction (untextured flat colours, grey '
          'lighting): use it only for where things are (the sand cove and the stair on the north face, the headlands, '
          'the sea stacks, the temple terrace below the wooded crown) and make everything else more beautiful')
REFS = {
    'hilltop': (STILLS / 'hilltop-island.png', 'a real screenshot of the game from a hilltop on the mainland, looking '
                'south over the autumn forest at the island as it is now (an ugly steep flat-topped lump) and the sea '
                '(with ugly hard pale bands toward the horizon)'),
    'look': (STILLS / 'game-look.png', 'another real screenshot of the game, on a hamlet path, for the game\'s '
             'look: its trees, grass, light and colours'),
    'layout_far': (STILLS / 'layout-far.png', LAYOUT),
    'layout_boat': (STILLS / 'layout-boat.png', LAYOUT),
    'layout_aerial': (STILLS / 'layout-aerial.png', LAYOUT),
    'far': (OUT / 'far.jpg', 'the approved concept of the redesigned island seen from the mainland hilltop: keep this '
            'exact island design (its silhouette, cliffs, headlands, cove, forest colours, torii and temple)'),
}

STYLE = (
    'Concept art for Yorimichi, a stylised low-poly Japanese autumn exploration game. The numbered images are given '
    'for reference: match the game\'s art direction exactly. Simple low-poly shapes with flat colours and soft '
    'painterly shading; the same autumn trees (vermilion and orange maples, golden ginkgo, deep teal-green cedars and '
    'pines with dark trunks), the same soft blue sky and gentle afternoon light. It must look like a polished, '
    'achievable game scene built from simple meshes: not photoreal, and not an elaborate illustration that could not '
    'be modelled.'
)

ISLAND = (
    'THE ISLAND: a small wooded island about 340 m across and 125 m high, half a kilometre offshore, reached by a '
    'small sailing dinghy. On its north face (the side toward the mainland beach) a grey stone stairway zigzags up '
    'from a small pale sand cove, through five vermilion torii gates with stone lanterns, to a modest temple on a '
    'small stone terrace on a spur below the top: one hall with a wide sweeping dark indigo hip roof, vermilion '
    'columns and cream plaster. Behind and above the temple rises the island\'s highest point, a rounded crown dark '
    'with tall cedars; a lower wooded top on the west end and a lower hump on the east end, with saddles between, so '
    'the silhouette is a long, uneven, gently rising ridge, not a cone or a single peak. Rocky headlands reach into '
    'the sea on both sides of the cove and at the ends, and four small sea stacks stand off them, each crowned by a '
    'pine. Redesign it as a believable, beautiful Japanese island, like Chikubu-shima or the small islands of the '
    'Seto Inland Sea: dark grey-brown rock cliffs broken by ledges and mossy shelves along the whole shore (low at the '
    'cove, tall under the headlands), fallen boulders at their feet, a soft line of white surf. Gnarled Japanese '
    'black pines lean out over the rocks on the headlands and cliff tops. The forest is mixed and patchy, never a '
    'uniform carpet and never speckled confetti: large dark green pine and cedar masses, broad drifts of red and '
    'orange maples and golden ginkgo in the hollows and on the lower slopes, a few open grassy glades. The temple '
    'roof and a vermilion torii read clearly as landmarks. No flat top, no mesa, no straight vertical walls.'
)

SEA = (
    'THE SEA: calm, deep blue-teal near the shores, lighter with distance, fading smoothly into a pale hazy horizon '
    'that melts into the sky. No hard bands, no straight edges, patches or seams anywhere on the water.'
)

AVOID = ('No photorealism, no text, labels, borders, collage panels or game HUD, no extra buildings, villages or '
         'boats besides those described, no other people.')

VIEWS = {
    'far': (['hilltop', 'look', 'layout_far'],
        'VIEW: exactly the camera and framing of Image 1, without its on-screen text and HUD: the child standing on '
        'the grassy hilltop in the foreground and the autumn trees around him stay as they are. Replace only the '
        'island and the sea behind them with the redesigned island and a sea that fades into the horizon haze. The '
        'island sits in the same place in the frame and a little wider and lower than the old lump, with the cove and '
        'the crown where Image 3 has them.'),
    'boat': (['far', 'layout_boat', 'look'],
        'VIEW: from the sailing dinghy about 120 m off the island\'s north shore, the child in a yellow t-shirt at the '
        'tiller small in the lower left foreground with the cream sail. Looking at the landing cove: a small pale sand '
        'beach between two rocky headlands, the first torii at the foot of the stair, the stairway zigzagging up the '
        'wooded face past more torii and lanterns, and the temple roof above with the dark cedar crown behind it. '
        'Pines lean over the rocks of the headlands on both sides.'),
    'aerial': (['far', 'layout_aerial'],
        'VIEW: a high three-quarter aerial view from the north-east, about 400 m away, showing the whole island and '
        'its outline on the sea: the cove and beach on the north side, the headlands and sea stacks, the crown and '
        'the lower tops, the zigzag of the stair with its torii, the temple terrace on its spur. A clear, readable '
        'layout that could be built as a terrain heightfield.'),
}
ORDER = ('far', 'boat', 'aerial')     # boat and aerial take far as their reference


def prompt_of(view):
    refs, text = VIEWS[view]
    numbered = ' '.join(f'Image {i + 1} is {REFS[r][1]}.' for i, r in enumerate(refs))
    return '\n\n'.join([STYLE + ' ' + numbered, ISLAND, SEA, text, AVOID])


def run(view):
    """Paint one view; returns (elapsed seconds, None) when done, else (elapsed seconds, why)."""
    from atelier.ai.ledger import try_once
    refs, _ = VIEWS[view]
    prompt = prompt_of(view)
    (OUT / f'{view}.prompt.txt').write_text(prompt + '\n')
    paths = [REFS[r][0] for r in refs]
    t = time.time()

    def paint():
        png, usage = sunburst(prompt, SIZE, paths)
        ORIGINALS.mkdir(parents=True, exist_ok=True); (ORIGINALS / f'{view}.png').write_bytes(png)
        return dict(usage=usage, outputs={f'{view}.png': sha(png)}, compact_copy=compact(png, OUT / f'{view}.jpg', 'concepts'),
                    elapsed_seconds=round(time.time() - t, 1))
    # The record is written before the paid call; a failed or uncertain one is never sent again by itself.
    _, error = try_once(OUT / f'{view}.provenance.json', dict(
        stage='southwest-island-concept', concept=view, requested_model=MODEL, quality=QUALITY, size=SIZE,
        endpoint='/v1/images/edits', execution='games/yorimichi/tools/island_concepts.py', prompt_file=f'{view}.prompt.txt',
        prompt_sha256=sha(prompt.encode()), reference_files={rel(p): sha(p.read_bytes()) for p in paths},
        hashes='of the files as the API saw and returned them; the full-size original is kept outside the repository'),
        paint)
    return round(time.time() - t, 1), error


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--only', default='', help='comma-separated views (far, boat, aerial)')
    ap.add_argument('--dry-run', action='store_true', help='print the prompts and stop')
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    wanted = [v for v in ORDER if not args.only or v in args.only.split(',')]
    if args.dry_run:
        for v in wanted:
            print(f'--- {v} {VIEWS[v][0]}{" (recorded, skipped)" if (OUT / f"{v}.provenance.json").exists() else ""}'
                  f'\n{prompt_of(v)}\n')
        return
    todo = [v for v in wanted if not (OUT / f'{v}.provenance.json').exists()]
    from atelier.env import require
    if todo:
        require('OPENAI_API_KEY')   # loads the ignored .env; stops with a clear message, never prints the value
    for v in todo:
        missing = [rel(REFS[r][0]) for r in VIEWS[v][0] if not REFS[r][0].exists()]
        if missing:
            sys.exit(f'{v}: missing references {missing}')
        secs, error = run(v)
        print(f'{v}: {error or "done"} ({secs} s)', flush=True)
        if error:
            sys.exit('stopped: a failed call is not retried')


if __name__ == '__main__':
    main()
