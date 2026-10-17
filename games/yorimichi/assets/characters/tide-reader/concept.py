#!/usr/bin/env python3
"""Paint Kiyo's production reference sheets with gpt-image-2.5-sunburst.

    uv run python games/yorimichi/assets/characters/tide-reader/concept.py sheet
    uv run python games/yorimichi/assets/characters/tide-reader/concept.py details poses

The first sheet is a four-view production turnaround. Later sheets edit that
approved design into construction details and an in-world attitude study. Every
paid call is recorded by atelier.ai.ledger before submission and is never
retried automatically. Full-size PNGs live under build/yorimichi; the compact
committed copies, prompts and provenance sit beside this script.
"""
import argparse
import hashlib
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[4]
sys.path.insert(0, str(REPO / 'games' / 'yorimichi' / 'tools'))
sys.path.insert(0, str(REPO / 'games' / 'yorimichi' / 'world'))
import yori  # noqa: E402
from treehouse_art import compact, rel, sha, sunburst  # noqa: E402

from atelier.ai.ledger import run_once  # noqa: E402
from atelier.env import require  # noqa: E402

REFS = HERE / 'references'
ORIGINALS = yori.OUT / 'characters' / 'tide-reader' / 'references' / 'originals'
STYLE = HERE.parent / 'wanderer' / 'references' / 'design-sheet.png'
MODEL, QUALITY, SIZE = 'gpt-image-2.5-sunburst', 'high', '1536x1024'

STYLE_PROMPT = (
    'The attached image is the approved Villager model sheet for Yorimichi, a stylised low-poly Japanese '
    'action-exploration game. Use it only as the authority for art direction, proportion language and model-sheet '
    'layout: soft matte flat-shaded polygon faces, a large angular head with a simple face, two dark vertical pill '
    'eyes with no whites or irises, barely indicated nose and mouth, broad clean garment planes, chunky readable '
    'silhouettes, warm restrained colours, a plain warm-grey studio background and soft even light. Do not draw or '
    'copy the Villager himself.'
)

KIYO = (
    'Design one definitive NPC, not alternate options: Kiyo, the tide-reader of Hidamari. A weathered coastal '
    'fisherwoman and amateur astronomer, about seventy years old, short and broad with a slightly forward-hunched '
    'carriage, about 4.4 heads tall. Warm sun-browned skin, a broad angular face, a strong jaw and rounded nose, '
    'dark vertical pill eyes under heavy lids with short crow\'s-feet creases, relaxed level brows, a small calm '
    'closed mouth, two short smile creases, and simple faceted shell earrings. Silver-grey hair in a low bun at '
    'the nape with a few broad angular side locks and a short swept fringe, never thin strands. '
    'She wears a very wide low-poly indigo straw weather hat on her head, built from twelve broad faceted panels, '
    'its brim scalloped by a few large notches and tied under the chin with a thin rust cord. A deep-indigo layered '
    'fisherman\'s coat reaches mid-thigh: a short broad shoulder cape sits over a wrapped long coat with an '
    'asymmetric front crossing, wide sleeves pushed up to the forearm, and a cream inner collar. A muted rust sash '
    'wraps the waist twice and holds a small flat wooden tide-board with four simple shell counters. Dark blue-grey '
    'cropped trousers, cream shin wraps, and broad flat straw sandals. A weathered leather satchel hangs at her left '
    'hip, with one rolled chart and a short bamboo case. '
    'Her tide staff is a dark polished bamboo rod with eight broad carved tide notches, a dull-gold bell-metal cap, '
    'and one small shell tied beneath the cap. The same dull-gold metal appears on the tide-board pins. '
    'Everything is made from a small number of broad, modelable planes and solid props: no embroidery, lace, tiny '
    'laces, woven wicker microgeometry, individual hair strands, texture noise, lettering or complex jewellery.'
)

SHEET_PROMPT = '\n\n'.join([
    STYLE_PROMPT,
    KIYO,
    'Composition: a large landscape production turnaround sheet on the same plain warm-grey background. Top row: '
    'equally sized full-body FRONT, exact RIGHT PROFILE, BACK and THREE-QUARTER views of the SAME design in a '
    'relaxed A-pose, both hands visible, hat on the head, staff standing upright beside her outside the body '
    'silhouette. Keep scale, proportions and costume identical in every view. Bottom row: a large face close-up '
    'front and true profile, a hat/hair close-up from front and back, a close-up of the crossed collar and rust '
    'sash, a close-up of one hand and the shell charms, a close-up of the shin wraps and straw sandals, a clear '
    'front-and-profile construction drawing of the tide staff, and seven flat colour chips. Label exactly the four '
    'main views FRONT, RIGHT PROFILE, BACK and THREE-QUARTER. No other text, logos, HUD, borders or extra figures. '
    'Modelable flat-shaded geometry with crisp silhouettes and no painterly brushwork. This sheet will be modelled '
    'directly, so anatomical and costume consistency are essential.',
])

DETAIL_PROMPT = '\n\n'.join([
    'The attached image is the approved Kiyo turnaround sheet. Preserve the exact same character, colours, '
    'proportions, low-poly language and plain warm-grey studio light. Paint a construction-detail sheet, not a '
    'redesign: six large, equally spaced panels at game-model clarity.',
    'Panel 1: the indigo weather hat alone, three-quarter view and underside, showing twelve broad panels, the '
    'rust chin cord and the small brass attachment points. Panel 2: the silver-grey low bun and angular side '
    'locks from behind and profile, under the hat brim. Panel 3: the tide staff head, front and side, showing the '
    'eight broad carved notches, dull-gold bell-metal cap and single hanging shell. Panel 4: the wooden tide-board '
    'with four shell counters, a rope loop and dull-gold pins. Panel 5: the layered coat front, showing the cream '
    'inner collar, asymmetric crossing, wide cuff and rust sash at larger scale. Panel 6: straw sandals, cream '
    'shin wraps and the broad flat sole. Minimal labels only. No extra characters, no new costume parts, no '
    'photoreal material rendering.',
])

POSE_PROMPT = '\n\n'.join([
    'The attached image is the approved Kiyo turnaround sheet. Preserve the exact same character, outfit, props, '
    'low-poly geometry and matte palette. Paint one cinematic in-world attitude study on a plain warm-grey '
    'background: Kiyo stands on the Hidamari seawall at late afternoon, leaning her weight on the tide staff with '
    'one hand, the other holding the tide-board up to read it. She looks out to sea with a patient, knowing '
    'expression rather than a smile. Her wide indigo weather hat and short shoulder cape break the sea wind. '
    'Three-quarter full-body view, feet planted, clear silhouette, no other characters, no text, no HUD, no '
    'dramatic lighting. Keep her face and costume identical to the sheet and keep every prop a simple solid '
    'low-poly shape.',
])

SHEETS = {
    'sheet': dict(prompt=SHEET_PROMPT, references=[STYLE]),
    'details': dict(prompt=DETAIL_PROMPT, references=[REFS / 'sheet.jpg']),
    'poses': dict(prompt=POSE_PROMPT, references=[REFS / 'sheet.jpg']),
}


def keep_original(png, name):
    """Keep the API's full-size PNG outside git and a compact sheet in references/."""
    target = ORIGINALS / f'{name}.png'
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(png)
    return sha(png), compact(png, REFS / f'{name}.jpg', 'concepts')


def generate(name, spec):
    prompt = spec['prompt']
    refs = spec['references']
    missing = [rel(path) for path in refs if not path.exists()]
    if missing:
        raise SystemExit(f'missing references for {name}: {missing}')
    prompt_file = REFS / f'{name}.prompt.txt'
    provenance = REFS / f'{name}.provenance.json'
    REFS.mkdir(parents=True, exist_ok=True)
    prompt_file.write_text(prompt + '\n')
    metadata = dict(
        asset='tide-reader', stage='reference', sheet=name, provider='openai',
        requested_model=MODEL, quality=QUALITY, size=SIZE, endpoint='/v1/images/edits',
        execution='games/yorimichi/assets/characters/tide-reader/concept.py',
        prompt_file=f'{name}.prompt.txt', prompt_sha256=sha(prompt.encode()),
        reference_files={rel(path): sha(path.read_bytes()) for path in refs},
        hashes='of the files as the API saw and returned them; the full-size original is kept outside the repository',
    )

    def paint():
        png, usage = sunburst(prompt, SIZE, refs)
        compact_record = keep_original(png, name)
        return dict(usage=usage, outputs={f'{name}.png': compact_record[0]}, compact_copy=compact_record[1])

    record = run_once(provenance, metadata, paint)
    print(f'{name}: {record["status"]} ({record.get("elapsed_seconds", "?")} s)', flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('sheets', nargs='+', choices=[*SHEETS, 'all'])
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    wanted = list(SHEETS) if 'all' in args.sheets else args.sheets
    for name in wanted:
        spec = SHEETS[name]
        if args.dry_run:
            print(f'--- {name}\n{spec["prompt"]}\n')
            continue
        if (REFS / f'{name}.provenance.json').exists():
            print(f'{name}: already recorded; left untouched', flush=True)
            continue
        require('OPENAI_API_KEY')
        generate(name, spec)


if __name__ == '__main__':
    main()
