#!/usr/bin/env python3
"""T-pose reference views of the chosen rival concept, "came-back", for Tripo's multiview model generation.

    uv run python games/yorimichi/tools/came_back_tpose.py front     # the front T-pose, from the concept sheet
    uv run python games/yorimichi/tools/came_back_tpose.py views     # back, left and right, from the front

Same stages as the sword trainer's (assets/characters/tools/sword_trainer_pipeline.py): one figure in, one figure
out. The front is painted from single-figure crops of the approved sheet (concepts/came-back.jpg: the front view and
the face close-up, cut from the full-size original into build/.../came-back-tpose/refs/); the other three views are
painted from the front alone. The rope and bell weapon of the sheet is left out. Model gpt-image-2.5-sunburst,
quality high, 1024x1024, /v1/images/edits, each call through atelier.ai.ledger.

Committed: <view>.jpg, <view>.prompt.txt and <view>.provenance.json in
games/yorimichi/assets/characters/concepts/came-back-tpose/. The full-size PNGs, the ones to upload to Tripo, are in
build/yorimichi/characters/concepts/came-back-tpose/. A view with a provenance file is never sent again.
"""
import sys as _sys; from pathlib import Path as _Path; _sys.path.insert(0, str(_Path(__file__).resolve().parents[1] / 'world')); import yori  # noqa: E402
_sys.path.insert(0, str(_Path(__file__).resolve().parent))
import argparse, sys, time
from concurrent.futures import ThreadPoolExecutor

from treehouse_art import MODEL, QUALITY, compact, redact, rel, sha, sunburst

OUT = yori.ASSETS / 'characters' / 'concepts' / 'came-back-tpose'
WORK = yori.OUT / 'characters' / 'concepts' / 'came-back-tpose'
SIZE = '1024x1024'

FRONT_REFS = [WORK / 'refs' / 'sheet-front.png', WORK / 'refs' / 'sheet-face.png']

DESIGN = (
    'a lean young man of about eighteen in a soft, smooth stylised 3D game finish (matte painted colour, chunky simple '
    'shapes, no outlines). Near-black hair in big sculpted spiky clumps with one upward tuft on top, a long side-swept '
    'fringe covering his right eye, and one thin white streak in the fringe. Simple face: warm peach skin, dark '
    'half-lidded pill eyes without whites (a flat heavy lid line across the top), a barely indicated nose, a faint '
    'calm almost-smile. A long open charcoal coat reaching the knees with a tall stiff stand-up collar edged in a '
    'slightly lighter grey; straight sleeves to the wrists; the coat hem and the sleeve ends fade to a pale icy blue '
    'like creeping frost. Under it a black high-neck fitted top, a dark belt with a small silver buckle, loose slate-'
    'grey trousers gathered into black wrapped leg wraps from mid-shin, and black split-toe boots. Hands bare, five '
    'fingers. '
)

POSE = (
    'Pose: a symmetrical T-pose. Both arms straight out horizontally at shoulder height, palms facing down, fingers '
    'together and straight, thumbs relaxed. Legs straight with a small gap, feet forward, flat on the floor. The coat '
    'hangs straight down from the shoulders and stays open at the front, its skirt clear of the legs; the sleeves '
    'follow the arms and are snug enough not to hang into a wing; no cloth bridges the armpits or the legs. '
)

FRONT = (
    'Input images: crops of our approved concept sheet for a playable hero of the stylised 3D game Yorimichi. Image 1 '
    'is his front view, image 2 his face close-up. They are the authority for his identity, proportions, costume, '
    'palette and finish. Redraw him exactly as designed: ' + DESIGN +
    'REMOVE the coiled rope and the bell weight over his shoulder entirely: he carries nothing and nothing is worn '
    'over the shoulder, the coat underneath is plain charcoal there. ' + POSE +
    'Composition and light: ONE full-body FRONT view only, a true frontal orthographic-style view, no rotation, no '
    'perspective, camera level with the chest. Whole figure centred on the square canvas with clear margin around '
    'the fingertips, hair and feet. Plain light-grey background, soft even diffuse light, minimal shadow, no ground '
    'plane, no cast shadow. No props, no weapon, nothing held or worn on the back. No text, labels, borders, insets '
    'or colour swatches. Draw exactly ONE figure, seen from the front only: never a second view, a turnaround or a '
    'close-up beside it. This is a reconstruction reference for 3D, not an action pose.'
)

VIEW_HEAD = (
    'Input image: the approved FRONT T-pose reference of a playable hero of our stylised 3D game Yorimichi. It is the '
    'sole authority for identity, proportions, costume, palette and materials. Preserve exactly: ' + DESIGN
)
VIEW_TAIL = (
    'Keep the same T-pose with the arms straight out horizontally, the same image scale, head height and floor '
    'baseline as the front view. Orthographic-style projection, no perspective, camera level with the chest. Plain '
    'light-grey background, soft even diffuse light, no ground plane, no cast shadow. Fit the complete silhouette on '
    'the square canvas with clear margin. Include only this one view: no labels, border, props, insets, text or '
    'extra figures.'
)
VIEWS = {
    'back': 'Create the full-body BACK reference view. He faces away from the camera: the back of the spiky hair, the '
            'back of the tall collar, the plain charcoal back of the long coat with its icy-blue hem, the backs of '
            'the arms with palms down, the trousers, leg wraps and heels. ',
    'left': 'Create the full-body LEFT reference view: his own anatomical left side, a true profile in which the nose '
            'points to the image-left. The near (left) arm points straight toward the camera and is strongly '
            'foreshortened, showing the hand end-on; the far arm is hidden behind it. Show the depth of the head, '
            'hair, collar, coat, trousers and boots in profile. ',
    'right': 'Create the full-body RIGHT reference view: his own anatomical right side, a true profile in which the '
             'nose points to the image-right. The near (right) arm points straight toward the camera and is strongly '
             'foreshortened, showing the hand end-on; the far arm is hidden behind it. Show the depth of the head, '
             'hair (the white-streaked fringe over the right eye), collar, coat, trousers and boots in profile. ',
}


def paint(view, prompt, refs):
    from atelier.ai.ledger import run_once
    OUT.mkdir(parents=True, exist_ok=True); WORK.mkdir(parents=True, exist_ok=True)
    (OUT / f'{view}.prompt.txt').write_text(prompt + '\n')
    metadata = dict(stage='came-back-tpose', view=view, requested_model=MODEL, quality=QUALITY, size=SIZE,
                    endpoint='/v1/images/edits', execution='games/yorimichi/tools/came_back_tpose.py',
                    prompt_file=f'{view}.prompt.txt', prompt_sha256=sha(prompt.encode()),
                    reference_files={rel(p): sha(p.read_bytes()) for p in refs},
                    hashes='of the files as the API saw and returned them; the full-size PNG stays in build/')

    def call():
        t = time.time()
        png, usage = sunburst(prompt, SIZE, refs)
        (WORK / f'{view}.png').write_bytes(png)
        return dict(usage=usage, outputs={f'{view}.png': sha(png)},
                    compact_copy=compact(png, OUT / f'{view}.jpg', 'refs'), elapsed_seconds=round(time.time() - t, 1))

    return run_once(OUT / f'{view}.provenance.json', metadata, call)


def run(jobs):
    jobs = [(v, p, r) for v, p, r in jobs if not (OUT / f'{v}.provenance.json').exists()]
    missing = sorted({rel(x) for _, _, r in jobs for x in r if not x.exists()})
    if missing:
        sys.exit(f'missing references {missing}')
    if not jobs:
        print('nothing to paint: every view is recorded'); return
    from atelier.env import require
    require('OPENAI_API_KEY')   # loads the ignored .env; stops with a clear message, never prints the value
    print(f'painting {", ".join(v for v, _, _ in jobs)}', flush=True)
    failed = []

    def one(job):
        view, prompt, refs = job
        try:
            print(f'{view}: done ({paint(view, prompt, refs)["elapsed_seconds"]} s)', flush=True)
        except Exception as e:  # noqa: BLE001 - recorded by the ledger, never retried
            failed.append(view); print(f'{view}: failed: {redact(e)[:300]}', flush=True)

    with ThreadPoolExecutor(len(jobs)) as pool:
        futures = [pool.submit(one, j) for j in jobs]
        start = time.time()
        while not all(f.done() for f in futures):
            time.sleep(10)
            if not all(f.done() for f in futures):
                print(f'{round(time.time() - start)} s: waiting on Sunburst', flush=True)
    if failed:
        sys.exit(f'stopped: {", ".join(failed)} failed and are not retried')


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('stage', choices=['front', 'views'])
    ap.add_argument('--dry-run', action='store_true', help='print the prompts and stop')
    args = ap.parse_args()
    if args.stage == 'front':
        jobs = [('front', FRONT, FRONT_REFS)]
    else:
        jobs = [(v, VIEW_HEAD + text + VIEW_TAIL, [WORK / 'front.png']) for v, text in VIEWS.items()]
    if args.dry_run:
        for v, p, r in jobs:
            print(f'--- {v} {[rel(x) for x in r]}\n{p}\n')
        return
    run(jobs)


if __name__ == '__main__':
    main()
