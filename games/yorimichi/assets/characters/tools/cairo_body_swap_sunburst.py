#!/usr/bin/env python3
"""Dress the naked T-pose views of the Cairo with the chosen outfit study, one Sunburst edit per view.

    set +x; set -a; source ./.env; set +a
    uv run python games/yorimichi/assets/characters/tools/cairo_body_swap_sunburst.py [--only front,back] [--concept path]
    ... --headless DIR --outfit games/yorimichi/assets/characters/cairo/outfits/hoodie.toml [--make-concept]

With --outfit the garment text comes from an outfit spec instead of the skate outfit written below; --make-concept
first redraws the approved concept sheet in that outfit (DIR/concept.png), which then serves as image 2. --key
(after the views exist) repaints each dressed view with the visible mannequin body in flat green: DIR/key/key-<view>.png,
the body mask the assembly step projects onto the Tripo model.

Image 1 per view is the real Blender render of the base body in its bind pose (`references/naked-<view>.png`);
image 2 is the user's chosen outfit study. Only the clothing may change. Outputs are square 1024 PNGs named by
Tripo view slot, next to the naked renders. Provider replies stay in the ignored api-private/ folder.
"""
import sys as _sys; from pathlib import Path as _Path; _sys.path.insert(0, str(_Path(__file__).resolve().parents[3] / 'world')); import yori  # noqa: E402
import sys as _sys; from pathlib import Path as _Path; _sys.path.insert(0, str(_Path(__file__).resolve().parent))  # Blender's --python does not add the script's folder
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


def private_reply(name, raw):
    """The provider reply without the image (token usage for the cost record), in the ignored api-private folder."""
    priv = OUT / 'api-private'; priv.mkdir(parents=True, exist_ok=True, mode=0o700); (priv / '.gitignore').write_text('*\n')
    p = priv / f'{name}.response.json'; p.write_text(json.dumps(raw, indent=1)); p.chmod(0o600)


# Generic headless prompt for an outfit spec: the r02 headless prompt with the skate garments taken out
SPEC_COMMON = (
    "Use case: clothing transfer onto a 3D character turnaround, one image. "
    "Input image 1 is a real Blender render of our game character's base body in a wide horizontal T-pose, seen "
    "from the {view}: a plain grey display MANNEQUIN of a boy's body WITHOUT A HEAD and WITHOUT HANDS: the neck ends "
    "in a flat stump at collar height, the arms end in flat stumps at the wrists, the feet are bare. Input image 2 is "
    "the APPROVED OUTFIT DESIGN on the same character standing relaxed. "
    "Task: redraw image 1 with the character wearing the outfit from image 2, and change NOTHING else. Keep the "
    "exact T-pose with both arms straight out horizontally and the exact body proportions. Do NOT add a head, hair, "
    "face, neck or hands: the neck opening stays EMPTY (we see into it, the grey stump or nothing), and each arm ends "
    "at the wrist with NOTHING coming out of it, the exact camera (orthographic, {view}), the exact scale, framing "
    "and position in the frame, and the same plain light-gray background and soft even light. The grey fitting suit "
    "is the body surface: the clothes are worn over it and {skin} "
    "Outfit, exactly as in image 2: {outfit} Every garment is a flat solid colour: no printed graphics, logos, text, "
    "stripes or patterns, no visible fabric texture. Softly sculpted matte 3D game-character finish, no shine, no "
    "dramatic shadows. {pose} No text, labels, border or watermark. "
)
SPEC_VIEWS = {
    'front': "View: TRUE FRONT view, camera directly in front, matching image 1 exactly. No head and no hands anywhere. ",
    'back': "View: TRUE BACK view, camera directly behind, matching image 1 exactly. No head and no hands anywhere; no face. ",
    'left': "View: TRUE LEFT side view, camera at the character's left, matching image 1 exactly: ",
    'right': "View: TRUE RIGHT side view, camera at the character's right, matching image 1 exactly: ",
}
CONCEPT_PROMPT = (
    "Use case: outfit redesign on an approved 3D character turnaround, one image. Input image 1 shows our game "
    "character from the back and from the front, standing relaxed. Redraw image 1 with exactly the same character: "
    "the same head, hair, face, skin, hands, body proportions, the same two poses, the same camera, framing, scale, "
    "light and plain grey studio background. Change ONLY his clothes, to this outfit: {concept}. Every garment is a "
    "flat solid colour: no printed graphics, logos, text, stripes or patterns, no visible fabric texture. Softly "
    "sculpted matte 3D game-character finish in the same style as image 1. The clothes sit on his body the way real "
    "clothes of that cut would; nothing floats. No text, labels, border or watermark."
)
# The body key: the dressed view repainted with every visible bit of mannequin (neck stump, chest inside the neckline,
# wrist stumps, bare arms and legs) in flat green, everything else unchanged. Assembly projects it onto the Tripo model
# to know which faces are body. The outfit text and the bare mannequin (image 2) are what stop Sunburst from keying
# white under-layers: without them it turned the skate outfit's white sleeves green.
KEY_PROMPT = (
    "Use case: recolour one image into a body mask. Input image 1 shows an outfit worn by a display mannequin that has "
    "no head and no hands, in a T-pose, on a light grey background. Input image 2 is the same mannequin with no "
    "clothes, from the same camera: its plain grey surface is the BODY. The outfit in image 1 is: {outfit}\n"
    "Redraw image 1 keeping everything exactly where it is: the same outline, the same clothes with the same colours "
    "and folds, the same camera, framing, scale and background. Change ONE thing: every part of the mannequin BODY "
    "that is still visible in image 1, not covered by the outfit, becomes flat pure green (#00FF00) with no shading. "
    "That is the bare grey mannequin surface and any bare skin: the neck stump and whatever chest or throat shows "
    "inside the neck opening, the flat wrist stumps at the arm ends, and bare arms, knees or shins where the outfit "
    "leaves them bare. Every garment of the outfit listed above stays exactly as it is, even where it is white, grey, "
    "beige, tan or skin-coloured: collars and their linings, undershirts and under-layers, the insides of sleeves, "
    "socks, shoes, sandals, belts, buttons and toggles. No green anywhere else. No text, labels, border or watermark."
)


def run_key(view, outfit):
    key_dir = OUT.parent / 'key'; key_dir.mkdir(exist_ok=True)
    prompt = KEY_PROMPT.format(outfit=outfit)
    stills = [OUT / f'{view}.png', OUT / f'naked-{view}.png']
    (key_dir / f'key-{view}.prompt.txt').write_text(prompt + '\n')
    started = datetime.now(timezone.utc).isoformat()
    blobs, raw, secs = wb.gpt_edit(prompt, stills, 1)
    out = key_dir / f'key-{view}.png'; out.write_bytes(blobs[0])
    private_reply(f'key-{view}', raw)
    prov = dict(stage='body-swap-body-key', view=view, requested_model=wb.MODEL, quality=wb.QUALITY, size=wb.SIZE,
                endpoint='/v1/images/edits', execution='games/yorimichi/assets/characters/tools/cairo_body_swap_sunburst.py --key',
                prompt_file=f'key-{view}.prompt.txt', prompt_sha256=hashlib.sha256(prompt.encode()).hexdigest(),
                reference_files={str(s.relative_to(ROOT)): wb.sha(s) for s in stills}, started_at=started,
                finished_at=datetime.now(timezone.utc).isoformat(), elapsed_seconds=secs, output_sha256=wb.sha(out))
    (key_dir / f'key-{view}.provenance.json').write_text(json.dumps(prov, indent=2) + '\n')
    return view, secs


def make_concept(spec):
    prompt = CONCEPT_PROMPT.format(concept=spec['concept'])
    (OUT.parent / 'concept.prompt.txt').write_text(prompt + '\n')
    size = wb.SIZE; wb.SIZE = '1536x1024'
    started = datetime.now(timezone.utc).isoformat()
    blobs, raw, secs = wb.gpt_edit(prompt, [CONCEPT], 1)
    wb.SIZE = size
    out = OUT.parent / 'concept.png'; out.write_bytes(blobs[0]); private_reply('concept', raw)
    prov = dict(stage='body-swap-outfit-concept', outfit=spec['name'], requested_model=wb.MODEL, quality=wb.QUALITY,
                size='1536x1024', endpoint='/v1/images/edits', execution='games/yorimichi/assets/characters/tools/cairo_body_swap_sunburst.py --make-concept',
                prompt_file='concept.prompt.txt', prompt_sha256=hashlib.sha256(prompt.encode()).hexdigest(),
                reference_files={str(CONCEPT.relative_to(ROOT)): wb.sha(CONCEPT)}, started_at=started,
                finished_at=datetime.now(timezone.utc).isoformat(), elapsed_seconds=secs, output_sha256=wb.sha(out),
                approval='pending')
    (OUT.parent / 'concept.provenance.json').write_text(json.dumps(prov, indent=2) + '\n')
    print('concept', f'{secs}s')
    return out


def run(view):
    prompt = COMMON.format(view=view) + VIEWS[view]
    stills = [OUT / f'naked-{view}.png', CONCEPT]
    (OUT / f'{view}.prompt.txt').write_text(prompt + '\n')
    started = datetime.now(timezone.utc).isoformat()
    blobs, raw, secs = wb.gpt_edit(prompt, stills, 1)
    (OUT / f'{view}.png').write_bytes(blobs[0])
    private_reply(view, raw)
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
    ap.add_argument('--outfit', default='', help='outfit spec (TOML: name, concept, outfit, pose, front/back/left/right, optional skin)')
    ap.add_argument('--make-concept', action='store_true', help='redraw the concept sheet in the spec outfit first (DIR/concept.png)')
    ap.add_argument('--headless', default='', help='directory (under the character folder) holding mannequin references; dress them without head or hands')
    ap.add_argument('--key', action='store_true', help='paint the visible mannequin body green in the dressed views (DIR/key/key-<view>.png); needs --outfit')
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
    if a.outfit:
        import tomllib
        if not a.headless:
            sys.exit('--outfit needs --headless DIR (the spec prompt is written for the mannequin views)')
        spec = tomllib.loads(Path(a.outfit).read_text())
        if a.key:
            views = [v for v in a.only.split(',') if v] or list(SPEC_VIEWS)
            wb.key()
            with ThreadPoolExecutor(max_workers=len(views)) as ex:
                for view, secs in ex.map(lambda v: run_key(v, spec['outfit']), views):
                    print('key', view, f'{secs}s')
            sys.exit(0)
        COMMON = SPEC_COMMON.replace('{skin}', spec.get('skin', 'it must not show anywhere except where skin would show.')).replace(
            '{outfit}', spec['outfit']).replace('{pose}', spec['pose'])
        VIEWS = {v: SPEC_VIEWS[v] + spec[v] for v in SPEC_VIEWS}
        wb.key()
        if a.make_concept:
            CONCEPT = make_concept(spec)
            if not a.only:
                sys.exit(0)
        elif not a.concept:
            CONCEPT = OUT.parent / 'concept.png'
    views = [v for v in a.only.split(',') if v] or list(VIEWS)
    wb.key()
    with ThreadPoolExecutor(max_workers=len(views)) as ex:
        for view, secs in ex.map(run, views):
            print(view, f'{secs}s')
