#!/usr/bin/env python3
"""Suzu, the bell-ringer of Hidamari: Sunburst reference images for the procedural model.

    uv run python games/yorimichi/assets/characters/tools/bell_ringer_concepts.py               # paint the missing stages
    uv run python games/yorimichi/assets/characters/tools/bell_ringer_concepts.py --dry-run     # print the prompts
    uv run python games/yorimichi/assets/characters/tools/bell_ringer_concepts.py --only sheet

Stage `sheet` paints the design sheet the mesh is built from; stage `views` paints four single-figure turnaround
images for close measurement. Inputs are Cairo's renders, made here with sword_trainer_refs.py (the style authority),
and the villager's sheet, for the sheet layout only. Each paid call goes through atelier.ai.ledger: an image that has a
provenance file is never sent again, whatever its status; rename its files to `<name>.rejected-N.*` to paint it again.

Written under games/yorimichi/assets/characters/bell-ringer/references/: the compact JPEG, its prompt and provenance.
Full-size PNGs stay in build/yorimichi/characters/bell-ringer/references/originals/.
"""
import sys as _sys
from pathlib import Path as _Path

_sys.path.insert(0, str(_Path(__file__).resolve().parents[3] / 'world'))  # noqa: E402
import yori  # noqa: E402
_sys.path.insert(0, str(_Path(__file__).resolve().parents[3] / 'tools'))  # noqa: E402
import argparse  # noqa: E402
import hashlib  # noqa: E402
import sys  # noqa: E402
import time  # noqa: E402
from pathlib import Path  # noqa: E402

from atelier.ai import images as client  # noqa: E402
from atelier.ai.ledger import redact, run_once  # noqa: E402
from treehouse_art import sha  # noqa: E402

CWD = Path(__file__).resolve().parents[5]
CHARACTER = yori.ASSETS / 'characters' / 'bell-ringer'
OUT = CHARACTER / 'references'
STYLE_REFS = yori.OUT / 'characters' / 'bell-ringer' / 'style-refs'
ORIGINALS = yori.OUT / 'characters' / 'bell-ringer' / 'references' / 'originals'
SIZE = '1536x1024'
MODEL, QUALITY = client.MODEL, client.QUALITY


def relative(path):
    try:
        return str(Path(path).resolve().relative_to(CWD))
    except ValueError:
        return str(path)


STYLE = (
    'Production character model sheet for Yorimichi, a stylised 3D Japanese action-exploration game in Unreal. '
    'Images 1 and 2 are renders of Cairo, the approved player character (front T-pose and three-quarter): they are '
    'the PRIMARY reference for finish, face and material language. Match exactly his softly sculpted matte 3D '
    'game-character finish, chunky simplified forms, broad clumped hair shapes, warm peach skin, a simple face with '
    'dark vertical pill eyes without whites or irises, a barely indicated nose and a small mouth, a plain light-grey '
    'studio background and soft even light. Image 3 is the villager\'s model sheet: use it ONLY for the sheet layout '
    '(four labelled views on top, close-ups and colour chips below), not for its flat faceted look.'
)

CHARACTER = (
    'THE CHARACTER: a new non-player villager, not Cairo and not a child. SUZU, the bell-ringer of the seaside town '
    'of Hidamari: an elderly woman of about seventy, short and round (about 1.46 m, a little over four heads tall), '
    'with a soft pear-shaped body, short legs, gently rounded shoulders and a slight forward settle of the head and '
    'neck, as if she has spent fifty years looking up at a bell. Her face is warm, calm and unbothered, with soft '
    'round cheeks, a small closed contented smile, a tiny nose and deep smile lines beside the mouth; her dark pill '
    'eyes are slightly downturned and half-lidded, with soft grey eyebrows above them. Silver-white hair, thick and '
    'soft, is parted in the middle, smoothed back and gathered into one low round bun at the nape, bound with a dark '
    'cord and pinned with a small dark wooden comb; two short soft locks fall before the ears and a few fine strands '
    'escape at the temples. Age shows in the shapes, not in texture: no wrinkle maps, no pore detail, no stray hairs.'
)

COSTUME = (
    'COSTUME: a padded deep-indigo work haori with wide sleeves and a cream lining that turns back at the cuffs and '
    'the collar, worn closed over a dark narrow under-collar; a broad muted-vermilion obi wrapped high under the '
    'chest, its knot to the back; a plain deeper-indigo apron panel hanging from the obi to mid-shin in front; wide '
    'charcoal indigo trousers gathered at the ankle; white tabi socks and dark wooden geta sandals with two dark '
    'thongs. Over her left shoulder she carries a thick twisted straw bell-rope, coiled twice across her chest and '
    'knotted at her right hip, its loose end tucked through the obi. A small dull-gold bell-metal hand bell hangs from '
    'a short dark cord at her left hip. A folded cream cloth is tucked into the obi at her right. '
    'Palette: deep indigo 39465C, darker indigo 2C3648, warm cream E8DECA, muted vermilion A4543A, straw C3A06B, '
    'dull bell-metal gold C9A45E, dark wood 5F4634, silver-white hair CFCAC2, warm peach skin E6B183, ink 2B2A2E. '
    'One accent only: the vermilion obi.'
)

LAYOUT = (
    'Composition: landscape model sheet. Top row: equally sized full-body FRONT, exact RIGHT PROFILE, BACK and '
    'THREE-QUARTER views of the SAME design in a relaxed A-pose, feet slightly apart, both hands visible and empty, '
    'labelled FRONT, RIGHT PROFILE, BACK, THREE-QUARTER. Bottom row: a larger face close-up in front and in '
    'three-quarter (the half-lidded eyes, smile and bun clearly readable), a close-up of the hand bell and rope knot, '
    'a close-up of the bun with its comb, and 6 flat colour chips. Consistent height and proportions in every view. '
    'Clean modelable shapes for a game mesh rigged with a standard humanoid skeleton: no tiny straps, laces, '
    'embroidery, fine fringe or texture noise; no cloth hanging below the knees except the trousers.'
)

AVOID = (
    'No text other than the short view labels, no logos, no HUD, no border around the whole sheet, no other '
    'characters, no Cairo, no yellow pullover, no spirits or creatures, no blood, no realistic skin or cloth shading, '
    'no cropped or floor-length kimono, no umbrella, no cat, no staff.'
)

SHEET_PROMPT = '\n\n'.join([STYLE, CHARACTER, COSTUME, LAYOUT, AVOID])

VIEWS = {
    'front': 'Create the full-body FRONT reference view of Suzu, the elderly bell-ringer, standing straight in a '
             'relaxed A-pose: arms away from the body at about thirty degrees, palms facing the body, fingers relaxed, '
             'feet slightly apart and forward. Show the face, the cream-lined haori collar and cuffs, the vermilion '
             'obi, the indigo apron panel, the straw rope across her chest, and the bell at her left hip. ',
    'back': 'Create the full-body BACK reference view of Suzu. She faces away from the camera: the low round bun and '
            'its dark wooden comb, the back of the haori and its wide sleeves, the obi knot at the back, the apron '
            'panel below it, the rope crossing her back, grey trousers and the heels of her geta. ',
    'left': 'Create the full-body LEFT PROFILE view of Suzu: her own anatomical left side, a true profile in which the '
            'nose points to the image-left. Show the depth of the bun at the back of her head, the forward settle of '
            'her neck, the padded haori, the obi, the apron panel, the rope over her shoulder, the bell at her hip, '
            'the profile of the trousers and the geta. Both arms hang beside the body in profile; the near arm is '
            'visible in full. ',
    'right': 'Create the full-body RIGHT PROFILE view of Suzu: her own anatomical right side, a true profile in which '
             'the nose points to the image-right. Show the same depth as the left profile, the knot of the straw rope '
             'at her right hip, the folded cloth at the obi, the profile of the bun and geta. Both arms hang beside '
             'the body in profile; the near arm is visible in full. ',
}

VIEW_INPUT = (
    'Input image: the approved design sheet of Suzu, the elderly bell-ringer of our stylised 3D game Yorimichi. The '
    'FRONT figure on its top-left is the sole authority for identity, proportions, costume, palette and materials; '
    'the other views and close-ups confirm them. Redraw that character exactly, at the same image scale and with the '
    'same floor baseline, as ONE full-body view, on a plain light-grey studio background with soft even light, no '
    'ground shadow: '
)


def style_references():
    refs = [STYLE_REFS / 'cairo_front_tpose.png', STYLE_REFS / 'cairo_three_quarter.png',
            yori.ASSETS / 'characters' / 'wanderer' / 'references' / 'design-sheet.png']
    missing = [relative(p) for p in refs if not p.exists()]
    if missing:
        sys.exit(f'missing style references {missing}; render Cairo\'s with sword_trainer_refs.py:\n'
                 f'  blender -b --python-exit-code 1 --python games/yorimichi/assets/characters/tools/'
                 f'sword_trainer_refs.py -- {relative(STYLE_REFS)}')
    return refs


def paint(name, prompt, refs, stage, size=SIZE):
    """One ledgered Sunburst edit: the compact JPEG, its prompt and provenance under references/."""
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f'{name}.prompt.txt').write_text(prompt + '\n')
    metadata = dict(asset='bell-ringer', character='suzu', stage=stage, image=name, provider='openai',
                    requested_model=MODEL, quality=QUALITY, size=size, endpoint='/v1/images/edits',
                    execution='games/yorimichi/assets/characters/tools/bell_ringer_concepts.py',
                    prompt_file=f'{name}.prompt.txt', prompt_sha256=hashlib.sha256(prompt.encode()).hexdigest(),
                    reference_files={relative(p): sha(p.read_bytes()) for p in refs},
                    hashes='of the files as the API saw and returned them; the full-size original is kept outside '
                           'the repository')

    def call():
        started = time.time()
        blobs, response, seconds = client.sunburst(prompt, size, refs)
        png = blobs[0]
        ORIGINALS.mkdir(parents=True, exist_ok=True)
        (ORIGINALS / f'{name}.png').write_bytes(png)
        record = dict(output=name + '.png', output_sha256=sha(png), usage=response.get('usage'),
                      elapsed_seconds=round(time.time() - started, 1), api_seconds=seconds)
        width = 1600 if size.split('x')[0] == '1536' else int(size.split('x')[0])
        record['compact_copy'] = client.compact(png, OUT / f'{name}.jpg', width, 88)
        return record
    return run_once(OUT / f'{name}.provenance.json', metadata, call)


def prompt_sheet():
    return SHEET_PROMPT


def prompt_view(view):
    return VIEW_INPUT + VIEWS[view] + (
        'Keep the same design, palette and proportions as the approved sheet. Orthographic-style projection, no '
        'perspective, camera level with the chest. Include only this one figure and this one view: no labels, border, '
        'props, insets, text, extra views or extra figures.')


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--only', default='', help='comma-separated stages: sheet,front,back,left,right')
    parser.add_argument('--dry-run', action='store_true', help='print the prompts and stop')
    args = parser.parse_args()
    wanted = [s for s in ['sheet', *VIEWS] if not args.only or s in args.only.split(',')]
    prompts = {'sheet': prompt_sheet(), **{view: prompt_view(view) for view in VIEWS}}
    if args.dry_run:
        for stage in wanted:
            done = ' (recorded, skipped)' if (OUT / f'{stage}.provenance.json').exists() else ''
            print(f'--- {stage}{done}\n{prompts[stage]}\n')
        return
    if not (OUT / 'sheet.provenance.json').exists() and 'sheet' not in wanted:
        sys.exit('paint the design sheet first: the turnaround views are edits of it')
    if not (OUT / 'sheet.provenance.json').exists():
        from atelier.env import require
        require('OPENAI_API_KEY')
    for stage in wanted:
        if (OUT / f'{stage}.provenance.json').exists():
            print(f'{stage}: already recorded, skipped', flush=True)
            continue
        if stage == 'sheet':
            refs = style_references()
        else:
            refs = [OUT / 'sheet.jpg'] if (OUT / 'sheet.jpg').exists() else [OUT / 'sheet.png']
        print(f'{stage}: painting (references {[relative(p) for p in refs]})', flush=True)
        try:
            record = paint(stage, prompts[stage], refs, 'design-sheet' if stage == 'sheet' else 'turnaround')
            print(f'{stage}: done in {record["elapsed_seconds"]} s', flush=True)
        except Exception as error:  # noqa: BLE001 - the ledger records it; never retried blindly
            sys.exit(f'{stage}: failed: {redact(error)[:400]}')


if __name__ == '__main__':
    main()
