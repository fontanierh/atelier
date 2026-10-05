#!/usr/bin/env python3
"""The sword trainer of Momiji Hamlet through the Tripo workflow, one reviewed stage at a time (the fox hunter's).

    uv run python games/yorimichi/assets/characters/tools/sword_trainer_pipeline.py front          # 3 front T-pose candidates
    uv run python games/yorimichi/assets/characters/tools/sword_trainer_pipeline.py views --choice B   # back/left/right
    uv run python games/yorimichi/assets/characters/tools/sword_trainer_pipeline.py approve --note "who looked at what"
    uv run python games/yorimichi/assets/characters/tools/sword_trainer_pipeline.py tripo           # P2 multiview mesh
    uv run python games/yorimichi/assets/characters/tools/sword_trainer_pipeline.py rig --source CLEANUP.glb

Asset root: <archive>/output/imagegen/yorimichi-sword-trainer-2026-10-05/ (YORIMICHI_ARCHIVE, see _archive.py). The
references are Cairo's renders (sword_trainer_refs.py, into refs/). Images come from gpt-image-2.5-sunburst at
quality=high, 1024 x 1024, each through atelier.ai.ledger with its prompt and provenance beside it; Tripo calls go
through atelier.ai.tripo_asset, which refuses inputs whose hashes are not in the approval.
"""
import sys as _sys; from pathlib import Path as _Path; _sys.path.insert(0, str(_Path(__file__).resolve().parent))  # noqa: E702
from _archive import ROOT  # noqa: E402
import argparse, hashlib, json, subprocess, sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

import spirit_concepts as sc  # noqa: E402  (gpt_edit, sha, key)

REPO = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(REPO / 'platform/studio'))
from atelier import env  # noqa: E402
from atelier.ai import ledger  # noqa: E402

ASSET = ROOT / 'output/imagegen/yorimichi-sword-trainer-2026-10-05'
REFS = [ASSET / 'refs/cairo_front_tpose.png']   # one figure in, one figure out (a pair of views came back as a pair)

IDENTITY = (
    "Input image: a render of Cairo, the player character of our stylised 3D game Yorimichi (a boy, 148 cm). It is "
    "the authority for the art style only: soft smooth stylised 3D, matte painted colour, simple shapes, a large simple "
    "face with two plain dark oval eyes, small nose and mouth, hands with five fingers. Design a NEW character in "
    "exactly that style: Kaede, the sword teacher of Momiji Hamlet, a forest village of maples. A mature woman in her "
    "late forties, about 168 cm, clearly taller and broader than Cairo, with an athletic, upright build and adult "
    "proportions (a smaller head relative to the body than Cairo's). Calm, kind, confident face with Cairo's eye style, "
    "faint smile lines, grey streaks at the temples and a small scar across one eyebrow. "
)
COSTUME = {
    'A': "Costume: a short rust-red haori jacket that ends at the hips, its sleeves tied back so they fit snugly to the "
         "forearms; a cream undershirt at the collar; a wide dark-indigo cloth belt; fitted dark-indigo trousers "
         "gathered into cream leg wraps from knee to ankle; dark tabi socks and flat straw sandals with thin soles. "
         "Black hair tied in a short high ponytail that ends above the shoulders; a maple-orange headband. ",
    'B': "Costume: a fitted dark-green training jacket crossed at the chest like a gi, ending at the hips, with short "
         "sleeves over snug cream forearm wraps; a maple-red sash belt; fitted charcoal trousers tucked into cream leg "
         "wraps from knee to ankle; flat dark sandals with thin soles. Black hair in a neat low bun at the nape with "
         "a few strands loose at the temples; a small maple-leaf pin in the bun. ",
    'C': "Costume: a sleeveless padded travelling vest in muted ochre over a long-sleeved fitted indigo shirt; a "
         "rust-red cloth belt; one light leather pauldron on the left shoulder; fitted grey-brown trousers tucked into "
         "short soft boots with thin flat soles. Dark-brown hair cut to the jaw, tucked behind one ear; a thin red cord "
         "headband. ",
}
POSE = (
    "Pose: a symmetrical T-pose. Both arms straight out horizontally at shoulder height, palms facing down, fingers "
    "together and straight, thumbs relaxed. Legs straight with a small gap, feet forward, flat on the floor. Every "
    "garment fits close to the body: nothing hangs below the hips except the trousers, no loose sleeves, no cloth "
    "bridging the armpits or between the legs, no long hair. "
)
COMPOSITION = (
    "Composition and light: ONE full-body FRONT view only, a true frontal orthographic-style view, no rotation, no "
    "perspective, camera level with the chest. Whole figure centred on a square canvas with clear margin around the "
    "fingertips, hair and feet. Plain light-grey background, soft even diffuse light, minimal shadow, no ground plane, "
    "no cast shadow. No props: no sword, no scabbard, no shield, nothing held or worn on the back. No text, labels, "
    "borders, insets or palette swatches. Draw exactly ONE figure, seen from the front only: never a second view, a "
    "turnaround or a three-quarter view beside it. This is a reconstruction reference for 3D, not an action pose."
)
LABELS = {'A': 'rust haori, ponytail, headband', 'B': 'green gi jacket, low bun', 'C': 'ochre vest, bob, pauldron'}

VIEW_TAIL = (
    "Keep the same T-pose with the arms straight out horizontally, the same image scale, head height and floor baseline "
    "as the front view. Orthographic-style projection, no perspective, camera level with the chest. Plain light-grey "
    "background, soft even diffuse light, no ground plane, no cast shadow. Fit the complete silhouette on the square "
    "canvas with clear margin. Include only this one view: no labels, border, props, insets, text or extra figures."
)
VIEWS = {
    'back': "Create the full-body BACK reference view. The character faces away from the camera: the back of the head "
            "and hair, the back of the jacket, belt and trousers, backs of the arms with palms down, the heels. ",
    'left': "Create the full-body LEFT reference view: the character's own anatomical left side, a true profile in which "
            "the nose points to the image-left. The near (left) arm points straight toward the camera and is strongly "
            "foreshortened, showing the hand end-on; the far arm is hidden behind it. Show the depth of the head, hair, "
            "torso, jacket, belt, trousers and feet in profile. ",
    'right': "Create the full-body RIGHT reference view: the character's own anatomical right side, a true profile in "
             "which the nose points to the image-right. The near (right) arm points straight toward the camera and is "
             "strongly foreshortened, showing the hand end-on; the far arm is hidden behind it. Show the depth of the "
             "head, hair, torso, jacket, belt, trousers and feet in profile. ",
}


# The chosen front as it was drawn (the views describe the picture, not the prompt it came from).
DRAWN = {
    'A': "the dark hair gathered in a full bun on top with grey streaks at the temples and two loose strands framing "
         "the face, the small scar through the right eyebrow, a short open rust-red haori ending at the hips with "
         "elbow-length sleeves tied with dark cords above the elbows, a cream crossed undershirt over a dark inner "
         "collar, a dark-brown cloth sash knotted at the front with two short tails, loose dark-brown trousers gathered "
         "below the knees, dark shin wraps crossed with tan cord, dark flat shoes with cream soles, bare forearms and "
         "hands. ",
}


def view_common(choice):
    return ("Input image: the approved FRONT reference of Kaede, the sword teacher in our stylised 3D game Yorimichi, "
            "in a T-pose. It is the sole authority for identity, proportions, costume, palette and materials. "
            "Preserve exactly: " + DRAWN[choice] + "Soft smooth stylised 3D, matte. ")


def generate(stage, name, prompt, images, out):
    """One Sunburst edit through the ledger: the image, its prompt and its provenance in `out`."""
    out.mkdir(parents=True, exist_ok=True)
    sc.OUT = out
    sc.SIZE = '1024x1024'
    (out / f'{name}.prompt.txt').write_text(prompt + '\n')
    meta = dict(asset='sword-trainer', stage=stage, candidate=name, provider='openai', requested_model=sc.MODEL,
                quality=sc.QUALITY, size=sc.SIZE, endpoint='/v1/images/edits',
                execution=f'games/yorimichi/assets/characters/tools/sword_trainer_pipeline.py {stage}',
                prompt_file=f'{name}.prompt.txt', prompt_sha256=hashlib.sha256(prompt.encode()).hexdigest(),
                reference_files={str(p.relative_to(ROOT)): sc.sha(p) for p in images})
    target = out / f'{name}.png'

    def call():
        blobs, secs = sc.gpt_edit(prompt, images, 1)
        target.write_bytes(blobs[0])
        return dict(elapsed_seconds=secs, output=target.name, output_sha256=sc.sha(target), approval='pending')
    record = ledger.run_once(out / f'{name}.provenance.json', meta, call)
    return name, record['elapsed_seconds']


def stage_front(rev):
    out = ASSET / f'front-{rev}'
    jobs = [(k, IDENTITY + COSTUME[k] + POSE + COMPOSITION) for k in COSTUME]
    with ThreadPoolExecutor(3) as ex:
        for name, secs in ex.map(lambda j: generate('front', j[0], j[1], REFS, out), jobs):
            print(f'{name}: ok ({secs}s)', flush=True)


def stage_views(rev, front_rev, choice):
    out = ASSET / f'views-{rev}'
    out.mkdir(parents=True, exist_ok=True)
    src = ASSET / f'front-{front_rev}' / f'{choice}.png'
    front = out / 'front.png'
    front.write_bytes(src.read_bytes())
    (out / 'front.provenance.json').write_text(json.dumps(dict(
        asset='sword-trainer', stage='views', view='front', kind='exact copy of the chosen front',
        source=str(src.relative_to(ROOT)), source_sha256=sc.sha(src), choice=choice, label=LABELS[choice]), indent=2) + '\n')
    jobs = [(v, view_common(choice) + VIEWS[v] + VIEW_TAIL) for v in VIEWS]
    with ThreadPoolExecutor(3) as ex:
        for name, secs in ex.map(lambda j: generate('views', j[0], j[1], [front], out), jobs):
            print(f'{name}: ok ({secs}s)', flush=True)


def stage_approve(rev, note):
    out = ASSET / f'views-{rev}'
    images = {f'{v}.png': sc.sha(out / f'{v}.png') for v in ('front', 'left', 'back', 'right')}
    (out / 'approval.json').write_text(json.dumps(dict(
        event='multiview_set_approved_for_tripo_generation', images=images, note=note,
        recorded_at=datetime.now(timezone.utc).isoformat()), indent=2) + '\n')
    print('approved', out / 'approval.json')


def tripo(*args):
    """atelier.ai.tripo_asset, recorded in the ledger (it resumes a saved task and never resubmits an uncertain one)."""
    return subprocess.run([sys.executable, '-m', 'atelier.ai.tripo_asset', *map(str, args)], cwd=REPO / 'platform/studio', check=True)


def stage_tripo(rev, views_rev, faces):
    out = ASSET / f'tripo-{rev}'
    out.mkdir(parents=True, exist_ok=True)
    references = ASSET / f'views-{views_rev}'
    meta = dict(asset='sword-trainer', stage='tripo', provider='tripo', endpoint='/generation/multiview-to-model',
                references=str(references.relative_to(ROOT)), faces=faces)
    marker = out / 'ledger.json'
    if marker.exists():   # a recorded submission: resume it (tripo_asset fetches the saved task)
        tripo('fetch', '--output', out, '--watch')
        return
    ledger.run_once(marker, meta, lambda: (tripo('generate', '--references', references, '--output', out, '--faces', faces), {})[1])


def stage_rig(rev, source):
    out = ASSET / f'tripo-rig-{rev}'
    out.mkdir(parents=True, exist_ok=True)
    marker = out / 'ledger.json'
    meta = dict(asset='sword-trainer', stage='rig', provider='tripo', endpoint='/animations/rig', source=str(source),
                source_sha256=sc.sha(source))
    if marker.exists():
        tripo('rig', '--source', source, '--output', out)
        return
    ledger.run_once(marker, meta, lambda: (tripo('rig', '--source', source, '--output', out), {})[1])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('stage', choices=['front', 'views', 'approve', 'tripo', 'rig'])
    ap.add_argument('--rev', default='r01')
    ap.add_argument('--front-rev', default='r01')
    ap.add_argument('--views-rev', default='r01')
    ap.add_argument('--choice', default='A')
    ap.add_argument('--note', default='')
    ap.add_argument('--faces', type=int, default=12000)
    ap.add_argument('--source', type=Path)
    a = ap.parse_args()
    env.load()
    if a.stage == 'front':
        sc.key(); stage_front(a.rev)
    elif a.stage == 'views':
        sc.key(); stage_views(a.rev, a.front_rev, a.choice)
    elif a.stage == 'approve':
        stage_approve(a.rev, a.note)
    elif a.stage == 'tripo':
        stage_tripo(a.rev, a.views_rev, a.faces)
    else:
        stage_rig(a.rev, a.source)


if __name__ == '__main__':
    main()
