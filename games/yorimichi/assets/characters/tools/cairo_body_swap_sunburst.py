#!/usr/bin/env python3
"""Dress the naked T-pose views of the Cairo with the chosen outfit study, one Sunburst edit per view.

    set +x; set -a; source ./.env; set +a
    uv run python games/yorimichi/assets/characters/tools/cairo_body_swap_sunburst.py [--only front,back] [--concept path]

Image 1 per view is the real Blender render of the base body in its bind pose (`references/naked-<view>.png`);
image 2 is the user's chosen outfit study. Only the clothing may change. Outputs are square 1024 PNGs named by
Tripo view slot, next to the naked renders. Provider replies stay in the ignored api-private/ folder.
"""
import sys as _sys; from pathlib import Path as _Path; _sys.path.insert(0, str(_Path(__file__).resolve().parents[3] / 'world')); import yori  # noqa: E402
from _archive import ROOT, TOOLS  # noqa: E402  (ROOT: the prototype archive holding the revision history)
import argparse, hashlib, json, sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
import cairo_back_concepts as wb
# ROOT (the archive) comes from _archive
CHAR = ROOT / 'output/imagegen/yorimichi-yellow-boy-2026-09-12'
OUT = CHAR / 'body-swap-r01/references'
wb.OUT = OUT; wb.SIZE = '1024x1024'
CONCEPT = CHAR / 'back-concepts-r04/boxy-tee-cargo-nohat-1.png'

COMMON = (
    "Use case: clothing transfer onto a 3D character turnaround, one image. "
    "Input image 1 is a real Blender render of our game character's base body in a wide horizontal T-pose, seen "
    "from the {view}: a boy with an oversized head, dark chocolate spiky hair with a small upward tuft, warm peach "
    "skin, wearing a plain grey fitting suit and barefoot. Input image 2 is the APPROVED OUTFIT DESIGN on the same "
    "character standing relaxed. "
    "Task: redraw image 1 with the character wearing the outfit from image 2, and change NOTHING else. Keep the "
    "exact T-pose with both arms straight out horizontally, the exact body proportions, the exact head, hair, "
    "face, hands and finger poses, the exact camera (orthographic, {view}), the exact scale, framing and position "
    "in the frame, and the same plain light-gray background and soft even light. The grey fitting suit is the "
    "body surface: the clothes are worn over it and it must not show anywhere except where skin would show. "
    "Outfit, exactly as in image 2: a huge boxy mustard-yellow short-sleeve tee that hangs to mid-thigh, its wide "
    "short sleeves reaching past the elbow, worn over a white long-sleeve layer whose sleeves end at the wrists; "
    "extra-wide olive-drab cargo work trousers with one big flap pocket on the outside of each thigh, the legs "
    "stacking in soft folds over chunky skate shoes with a cream upper, black toe and side panels and a cream "
    "sole; the bare feet become those shoes. Every garment is a flat solid colour: no printed graphics, logos, "
    "text, stripes or patterns, no visible fabric texture. Softly sculpted matte 3D game-character finish, no "
    "shine, no dramatic shadows. In the T-pose the sleeves hang under the outstretched arms and the tee hangs "
    "straight; the trousers stay wide and straight. No text, labels, border or watermark. "
)
VIEWS = {
    'front': "View: TRUE FRONT view, camera directly in front, matching image 1 exactly. The face, the tee's round "
             "neckline with the white layer's collar just visible, the cargo pockets on both outer thighs and the "
             "shoe fronts are visible.",
    'back': "View: TRUE BACK view, camera directly behind, matching image 1 exactly. The back of the hair, the "
            "plain back of the tee, the back of the trousers and the shoe heels are visible; no face.",
    'left': "View: TRUE LEFT side view, camera at the character's left, matching image 1 exactly: the left arm "
            "points at the camera so the left hand is seen end-on in front of the body, the left cargo pocket "
            "faces the camera on the outer thigh, and the shoes are seen from the side.",
    'right': "View: TRUE RIGHT side view, camera at the character's right, matching image 1 exactly: the right "
             "arm points at the camera so the right hand is seen end-on in front of the body, the right cargo "
             "pocket faces the camera on the outer thigh, and the shoes are seen from the side.",
}


def run(view):
    prompt = COMMON.format(view=view) + VIEWS[view]
    stills = [OUT / f'naked-{view}.png', CONCEPT]
    (OUT / f'{view}.prompt.txt').write_text(prompt + '\n')
    started = datetime.now(timezone.utc).isoformat()
    blobs, raw, secs = wb.gpt_edit(prompt, stills, 1)
    (OUT / f'{view}.png').write_bytes(blobs[0])
    prov = dict(stage='body-swap-multiview-reference' + ('-headless' if 'headless' in str(OUT) else ''), view=view, requested_model=wb.MODEL, quality=wb.QUALITY,
                size=wb.SIZE, endpoint='/v1/images/edits', execution='games/yorimichi/assets/characters/tools/cairo_body_swap_sunburst.py',
                prompt_file=f'{view}.prompt.txt', prompt_sha256=hashlib.sha256(prompt.encode()).hexdigest(),
                reference_files={str(s.relative_to(ROOT)): wb.sha(s) for s in stills},
                started_at=started, finished_at=datetime.now(timezone.utc).isoformat(), elapsed_seconds=secs,
                output_sha256=wb.sha(OUT / f'{view}.png'), approval='pending')
    (OUT / f'{view}.provenance.json').write_text(json.dumps(prov, indent=2) + '\n')
    return view, secs


if __name__ == '__main__':
    ap = argparse.ArgumentParser(); ap.add_argument('--only', default=''); ap.add_argument('--concept', default='')
    ap.add_argument('--headless', default='', help='directory (under the character folder) holding mannequin references; dress them without head or hands')
    a = ap.parse_args()
    if a.concept:
        CONCEPT = Path(a.concept)
    if a.headless:
        OUT = CHAR / a.headless / 'references'; wb.OUT = OUT
        COMMON = COMMON.replace(
            "a boy with an oversized head, dark chocolate spiky hair with a small upward tuft, warm peach skin, wearing a plain grey fitting suit and barefoot.",
            "a plain grey display MANNEQUIN of a boy's body WITHOUT A HEAD and WITHOUT HANDS: the neck ends in a flat stump at collar height, the arms end in flat stumps at the wrists, the feet are bare.").replace(
            "Keep the exact T-pose with both arms straight out horizontally, the exact body proportions, the exact head, hair, face, hands and finger poses,",
            "Keep the exact T-pose with both arms straight out horizontally and the exact body proportions. Do NOT add a head, hair, face, neck or hands: the collar of the tee stays EMPTY (we see into the neck opening, the grey stump or nothing), and each white sleeve ends OPEN at the wrist with NOTHING coming out of it,").replace(
            "worn over a white long-sleeve layer whose sleeves end at the wrists;",
            "worn over a white long-sleeve layer whose sleeves end at the wrists as open cuffs with no hand inside;")
        VIEWS = {k: v.replace("The face, ", "No head and no hands anywhere. ").replace("The back of the hair, ", "No head and no hands anywhere. ").replace("so the left hand is seen end-on in front of the body", "so the open sleeve end is seen end-on in front of the body with no hand").replace("so the right hand is seen end-on in front of the body", "so the open sleeve end is seen end-on in front of the body with no hand") for k, v in VIEWS.items()}
    views = [v for v in a.only.split(',') if v] or list(VIEWS)
    wb.key()
    with ThreadPoolExecutor(max_workers=len(views)) as ex:
        for view, secs in ex.map(run, views):
            print(view, f'{secs}s')
