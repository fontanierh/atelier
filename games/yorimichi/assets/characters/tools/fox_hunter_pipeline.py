#!/usr/bin/env python3
"""Fox-masked hunter: the first enemy through the full Tripo workflow, one reviewed stage at a time.

    set -a; source .env; set +a
    uv run python games/yorimichi/assets/characters/tools/fox_hunter_pipeline.py front   # 3 front T-pose candidates
    uv run python games/yorimichi/assets/characters/tools/fox_hunter_pipeline.py views   # back/left/right from approved front
    ... later stages: tripo, cleanup, rig, animate (added as each earlier stage is approved)

Asset root: output/imagegen/yorimichi-fox-hunter-2026-09-13/. Each stage writes its own revision folder
with prompts, provenance (input/output hashes) and an approval.json that stays "pending" until the user
decides in chat. Images for Tripo are produced by gpt-image-2.5-sunburst at quality=high, 1024 x 1024.
"""
import sys as _sys; from pathlib import Path as _Path; _sys.path.insert(0, str(_Path(__file__).resolve().parents[3] / 'world')); import yori  # noqa: E402
import sys as _sys; from pathlib import Path as _Path; _sys.path.insert(0, str(_Path(__file__).resolve().parent))  # Blender's --python does not add the script's folder
from _archive import ROOT, TOOLS  # noqa: E402  (ROOT: the prototype archive holding the revision history)
import argparse, hashlib, json, sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import spirit_concepts as sc  # noqa: E402  (gpt_edit, prep, sha, key)

# ROOT (the archive) comes from _archive
ASSET = ROOT / 'output/imagegen/yorimichi-fox-hunter-2026-09-13'
SHEET = ROOT / 'output/imagegen/yorimichi-spirits-2026-09-13/r03/fox_hunter.png'
ROSTER = ROOT / 'output/imagegen/yorimichi-spirits-2026-09-13/r03/roster.png'
PLAYER = ROOT / 'output/imagegen/yorimichi-yellow-boy-2026-09-12/outfit-r04/final-captures/01-standing-three-quarter.png'

IDENTITY = (
    "Input images: the approved model sheet of the fox-masked hunter, an enemy in our low-poly game Yorimichi, "
    "the roster showing its size next to the player character, and the player character render. The sheet is the "
    "sole authority for its design. Preserve exactly: a thin hunched-shouldered humanoid body slightly taller than "
    "the player, long thin arms, long clawed hands with four fingers and a thumb, a smooth white fox mask with "
    "pointed ears and a dark vertical slit for eyes covering the whole face, a dark hood behind the mask, a rust-red "
    "scarf, a thick twisted rope collar with two flat cream paper tags hanging from it, a ragged layered cloak of "
    "dark grey-green and rust cloth in solid pointed pieces over a dark tunic, bandaged shins, wooden sandals on two "
    "blocks. Painted flat-shaded low-poly game look, matte, no outlines, no photoreal texture, no fine fibres. "
    "Menacing, no smile, no visible eyes. "
)
COMPOSITION = (
    "Composition and light: ONE full-body FRONT view only, a true frontal orthographic-style view, no rotation, no "
    "perspective, camera level with the chest. Whole figure centred on a square canvas with clear margin around "
    "fingertips, ears and sandals. Plain light-grey background, soft even diffuse light, minimal shadow, no ground "
    "plane, no cast shadow. No props, no held weapon, no floating parts, no text, labels, borders, insets or palette "
    "swatches. This is a reconstruction reference for 3D, not an action pose."
)

FRONT = {
    'A': dict(label='T-pose, full cloak',
              trade='Closest to the sheet. Best pose for auto-rigging. Cloak pieces along the arms may web at the armpit.',
              prompt=IDENTITY + (
                  "Pose: a symmetrical T-pose. Both arms extend straight out horizontally at shoulder height, palms "
                  "facing the camera, clawed fingers slightly spread. Legs straight with a small gap, feet forward. The "
                  "cloak's layered pieces hang from the shoulders and along the outstretched arms like sleeves, and hang "
                  "down the torso; keep clear open space between each arm and the torso, with no cloth bridging the "
                  "armpit. ") + COMPOSITION),
    'B': dict(label='A-pose, full cloak',
              trade='Arms at 45 degrees so the cloak drapes naturally with no webbing. Rig still works; Tripo suggests A-pose when hanging shapes matter.',
              prompt=IDENTITY + (
                  "Pose: a symmetrical A-pose. Both arms extend straight out and down at about 45 degrees from the "
                  "shoulders, palms facing the camera, clawed fingers slightly spread, hands well clear of the hips. "
                  "Legs straight with a small gap, feet forward. The cloak hangs from the shoulders in layered solid "
                  "pieces over the upper arms and torso, without touching the hands. ") + COMPOSITION),
    'C': dict(label='T-pose, short cape',
              trade='Cheapest to build and animate: the cloak becomes a short shoulder cape, the tunic carries the ragged hem. Loses some silhouette.',
              prompt=IDENTITY + (
                  "Pose: a symmetrical T-pose. Both arms extend straight out horizontally at shoulder height, palms "
                  "facing the camera, clawed fingers slightly spread. Legs straight with a small gap, feet forward. "
                  "Simplify the costume for a low polygon budget: the layered cloak is reduced to a short pointed "
                  "shoulder cape that ends above the elbows and does not reach the arms, and the ragged pointed hem "
                  "belongs to the tunic itself, ending above the knees. Arms are bare thin dark sleeves with bandaged "
                  "forearms. Keep the mask, hood, scarf, rope collar and tags unchanged. ") + COMPOSITION),
}


def approval_stub(stage, rev, candidates):
    return dict(asset='fox-hunter', stage=stage, revision=rev, candidates=candidates, status='pending',
                decision=None, user_message=None, recorded_at=None)


def stage_front(rev='r01'):
    out = ASSET / f'front-{rev}'
    out.mkdir(parents=True, exist_ok=True)
    sc.OUT = out
    sc.SIZE = '1024x1024'
    stills = [SHEET, ROSTER, PLAYER]

    def one(k):
        c = FRONT[k]
        (out / f'{k}.prompt.txt').write_text(c['prompt'] + '\n')
        started = datetime.now(timezone.utc).isoformat()
        try:
            blobs, secs = sc.gpt_edit(c['prompt'], stills, 1)
            err = None
        except Exception as e:  # noqa: BLE001
            blobs, secs, err = [], None, str(e)
        p = out / f'{k}.png'
        if blobs:
            p.write_bytes(blobs[0])
        prov = dict(asset='fox-hunter', stage='front', revision=rev, candidate=k, label=c['label'],
                    requested_model=sc.MODEL, quality=sc.QUALITY, size=sc.SIZE, endpoint='/v1/images/edits',
                    execution='games/yorimichi/assets/characters/tools/fox_hunter_pipeline.py front',
                    prompt_file=f'{k}.prompt.txt', prompt_sha256=hashlib.sha256(c['prompt'].encode()).hexdigest(),
                    reference_files={str(s.relative_to(ROOT)): sc.sha(s) for s in stills},
                    started_at=started, finished_at=datetime.now(timezone.utc).isoformat(), elapsed_seconds=secs,
                    output=p.name if blobs else None, output_sha256=sc.sha(p) if blobs else None, error=err,
                    approval='pending')
        (out / f'{k}.provenance.json').write_text(json.dumps(prov, indent=2) + '\n')
        return k, err, secs

    with ThreadPoolExecutor(3) as ex:
        for k, err, secs in ex.map(one, list(FRONT)):
            print(f'{k}: {"ERROR " + err if err else "ok"} ({secs}s)')
    ap = out / 'approval.json'
    if not ap.exists():
        ap.write_text(json.dumps(approval_stub('front', rev, {k: FRONT[k]['label'] for k in FRONT}), indent=2) + '\n')


FEET_EDIT = (
    "Input image: the approved FRONT reference of the fox-masked hunter, an enemy in our low-poly game Yorimichi, in "
    "a T-pose. Produce the same image with ONE change and nothing else changed: replace the raised two-block wooden "
    "platform sandals with flat footwear that has no platform, no blocks and no visible base: simple dark flat "
    "sandals with a thin sole, strapped over bandaged feet, toes forward, standing directly on nothing. Keep the "
    "bandaged shins. Keep every other pixel of identity, pose, proportions, mask, hood, scarf, rope collar, tags, "
    "cape, tunic, arms, hands, palette, lighting, framing, scale and the plain light-grey background identical. Keep "
    "the feet at the same floor height so the figure does not move. No ground plane, no shadow, no labels."
)


def stage_front_edit(rev='r02', src_rev='r01', src_choice='C'):
    out = ASSET / f'front-{rev}'
    out.mkdir(parents=True, exist_ok=True)
    sc.OUT = out
    sc.SIZE = '1024x1024'
    src = ASSET / f'front-{src_rev}' / f'{src_choice}.png'
    (out / 'C.prompt.txt').write_text(FEET_EDIT + '\n')
    started = datetime.now(timezone.utc).isoformat()
    blobs, secs = sc.gpt_edit(FEET_EDIT, [src], 1)
    p = out / 'C.png'
    p.write_bytes(blobs[0])
    prov = dict(asset='fox-hunter', stage='front', revision=rev, candidate='C', label='T-pose, short cape, flat sandals',
                parent=str(src.relative_to(ROOT)), parent_sha256=sc.sha(src), reason='user: remove the stand (platform sandals)',
                requested_model=sc.MODEL, quality=sc.QUALITY, size=sc.SIZE, endpoint='/v1/images/edits',
                execution='games/yorimichi/assets/characters/tools/fox_hunter_pipeline.py front --rev r02 --edit',
                prompt_file='C.prompt.txt', prompt_sha256=hashlib.sha256(FEET_EDIT.encode()).hexdigest(),
                reference_files={str(src.relative_to(ROOT)): sc.sha(src)},
                started_at=started, finished_at=datetime.now(timezone.utc).isoformat(), elapsed_seconds=secs,
                output='C.png', output_sha256=sc.sha(p), error=None, approval='pending')
    (out / 'C.provenance.json').write_text(json.dumps(prov, indent=2) + '\n')
    ap = out / 'approval.json'
    if not ap.exists():
        ap.write_text(json.dumps(approval_stub('front', rev, {'C': prov['label']}), indent=2) + '\n')
    print(f'front {rev}: ok ({secs}s)')


VIEW_COMMON = (
    "Input image: the approved FRONT reference of the fox-masked hunter, an enemy in our low-poly game Yorimichi, in "
    "a T-pose. It is the sole authority for identity, proportions, costume, palette and materials. Preserve exactly: "
    "the white fox mask with pointed ears, the dark hood, rust-red scarf, twisted rope collar with two cream paper "
    "tags at the front, short pointed shoulder cape in grey-green and rust, dark tunic with a ragged pointed hem above "
    "the knees, thin dark sleeves with bandaged forearms, long clawed five-digit hands, dark cropped trousers, "
    "bandaged shins, simple flat dark sandals with thin soles and no platform. Keep the same T-pose with arms straight out horizontally, the same "
    "image scale, head height and floor baseline as the front view. Painted flat-shaded low-poly game look, matte. "
)
VIEW_TAIL = (
    "Orthographic-style projection, no perspective, camera level with the chest. Plain light-grey background, soft "
    "even diffuse light, no ground plane, no cast shadow. Fit the complete silhouette on the square canvas with clear "
    "margin. Include only this one view: no labels, border, props, insets, text or extra figures."
)
VIEWS = {
    'back': "Create the full-body BACK reference view. The character faces away from the camera: back of the hood "
            "and mask ears, back of the shoulder cape hanging over the shoulder blades, the rope collar seen from "
            "behind, the back of the tunic and its ragged hem, backs of the arms with palms away from camera, heels "
            "and the thin flat soles. ",
    'left': "Create the full-body LEFT reference view: the character's own anatomical left side, a true profile in "
            "which the mask's nose points to the image-left. The near (left) arm points straight toward the camera "
            "and is strongly foreshortened, showing the clawed hand end-on; the far arm is hidden behind it. Show "
            "the depth of the hood, cape, torso, hem, trousers and sandals in profile. ",
    'right': "Create the full-body RIGHT reference view: the character's own anatomical right side, a true profile in "
             "which the mask's nose points to the image-right. The near (right) arm points straight toward the "
             "camera and is strongly foreshortened, showing the clawed hand end-on; the far arm is hidden behind it. "
             "Show the depth of the hood, cape, torso, hem, trousers and sandals in profile. ",
}


def stage_views(rev='r01', front_rev='r01', front_choice='C'):
    out = ASSET / f'views-{rev}'
    out.mkdir(parents=True, exist_ok=True)
    sc.OUT = out
    sc.SIZE = '1024x1024'
    src = ASSET / f'front-{front_rev}' / f'{front_choice}.png'
    front = out / 'front.png'
    front.write_bytes(src.read_bytes())
    (out / 'front.provenance.json').write_text(json.dumps(dict(
        asset='fox-hunter', stage='views', revision=rev, view='front', kind='exact copy of approved front',
        source=str(src.relative_to(ROOT)), source_sha256=sc.sha(src), output='front.png', output_sha256=sc.sha(front)),
        indent=2) + '\n')

    def one(v):
        prompt = VIEW_COMMON + VIEWS[v] + VIEW_TAIL
        (out / f'{v}.prompt.txt').write_text(prompt + '\n')
        started = datetime.now(timezone.utc).isoformat()
        try:
            blobs, secs = sc.gpt_edit(prompt, [front], 1)
            err = None
        except Exception as e:  # noqa: BLE001
            blobs, secs, err = [], None, str(e)
        p = out / f'{v}.png'
        if blobs:
            p.write_bytes(blobs[0])
        prov = dict(asset='fox-hunter', stage='views', revision=rev, view=v, requested_model=sc.MODEL,
                    quality=sc.QUALITY, size=sc.SIZE, endpoint='/v1/images/edits',
                    execution='games/yorimichi/assets/characters/tools/fox_hunter_pipeline.py views',
                    prompt_file=f'{v}.prompt.txt', prompt_sha256=hashlib.sha256(prompt.encode()).hexdigest(),
                    reference_files={str(front.relative_to(ROOT)): sc.sha(front)},
                    started_at=started, finished_at=datetime.now(timezone.utc).isoformat(), elapsed_seconds=secs,
                    output=p.name if blobs else None, output_sha256=sc.sha(p) if blobs else None, error=err,
                    approval='pending')
        (out / f'{v}.provenance.json').write_text(json.dumps(prov, indent=2) + '\n')
        return v, err, secs

    with ThreadPoolExecutor(3) as ex:
        for v, err, secs in ex.map(one, list(VIEWS)):
            print(f'{v}: {"ERROR " + err if err else "ok"} ({secs}s)')
    ap = out / 'approval.json'
    if not ap.exists():
        ap.write_text(json.dumps(approval_stub('views', rev, {v: f'{v} view' for v in ['front'] + list(VIEWS)}), indent=2) + '\n')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('stage', choices=['front', 'views'])
    ap.add_argument('--rev', default='r01')
    ap.add_argument('--front-rev', default='r01')
    ap.add_argument('--front-choice', default='C')
    ap.add_argument('--edit', action='store_true', help='front: edit the previous approved front (feet fix) instead of new candidates')
    a = ap.parse_args()
    sc.key()
    if a.stage == 'front' and a.edit:
        stage_front_edit(a.rev, a.front_rev, a.front_choice)
    elif a.stage == 'front':
        stage_front(a.rev)
    elif a.stage == 'views':
        stage_views(a.rev, a.front_rev, a.front_choice)


if __name__ == '__main__':
    main()
