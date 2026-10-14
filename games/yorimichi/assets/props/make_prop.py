#!/usr/bin/env python3
"""Make a prop for the running game from a sentence: a Sunburst concept, then a Tripo model, as a GLB the live bridge
can place (atelier live, the live bridge). Two stages so the concept can be looked at before paying for a model.

    uv run python games/yorimichi/assets/props/make_prop.py concept stone_lantern "a moss-covered stone lantern (ishidoro)"
    uv run python games/yorimichi/assets/props/make_prop.py model stone_lantern [--faces 6000]
    uv run python games/yorimichi/assets/props/make_prop.py make stone_lantern "..."          # both, no stop

Everything lands in games/yorimichi/assets/props/<slug>/: concept.png, prompt.txt, provenance.json, job.json, raw/
(the Tripo outputs) and <slug>.glb, the file to place. Credentials come from the environment or the ignored .env:
OPENAI_API_KEY (Sunburst, gpt-image-2.5-sunburst, quality high, per AGENTS.md) and TRIPO_API_KEY. A Tripo task is
submitted once and resumed by id; an uncertain POST is never repeated (tripo_asset.py).
"""
import sys as _sys; from pathlib import Path as _Path; _sys.path.insert(0, str(_Path(__file__).resolve().parents[2] / 'world')); import yori  # noqa: E402
ROOT = yori.REPO
_sys.path.insert(0, str(yori.ASSETS / 'characters' / 'tools'))
import argparse, datetime, hashlib, json, os, shutil, sys
from pathlib import Path

OUT = yori.ASSETS / 'props'
MODEL = 'gpt-image-2.5-sunburst'
STYLE = ("A single isolated object for 3D reconstruction, shown whole in a three-quarter front view from slightly above, "
         "centred with a clear margin, on a plain flat light-grey background, soft even studio light, no cast shadow, no "
         "ground plane, no text, no other objects. Style: a stylised prop for a painterly Japanese countryside game — "
         "chunky readable shapes, gently rounded edges, hand-painted matte colours with soft colour variation, no "
         "photographic texture noise, no glossy highlights. The object: ")


def env():
    dotenv = ROOT / '.env'
    if dotenv.exists():
        for line in dotenv.read_text().splitlines():
            if '=' in line and not line.lstrip().startswith('#'):
                k, v = line.split('=', 1); os.environ.setdefault(k.strip().removeprefix('export ').strip(), v.strip().strip('"').strip("'"))


def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def concept(slug, description):
    """@cc [owner:fontanierh,label:correctness] prop-concept-paid-once
    A concept request MUST use the paid-call ledger. Existing output or provenance MUST prevent
    resubmission; an uncertain provider result MUST be reconciled before another paid attempt.
    """
    from atelier.ai import images
    folder = OUT / slug; folder.mkdir(parents=True, exist_ok=True)
    prompt = STYLE + description.strip()
    image = folder / 'concept.png'
    if image.exists():
        raise SystemExit('Concept already exists; archive the reviewed revision before paying for a replacement.')
    images.paint(image, prompt, '1024x1024', record=folder / 'provenance.json', model=MODEL, quality='high',
                 metadata={'slug': slug, 'description': description, 'prompt': prompt, 'created_at': now()})
    (folder / 'prompt.txt').write_text(prompt + '\n')
    print(image)


def model(slug, faces):
    from atelier.ai.tripo_asset import call, credential, write_json, read_json, private_folder, fetch
    import httpx
    folder = OUT / slug; image = folder / 'concept.png'
    if not image.exists(): raise SystemExit(f'no concept for {slug}: run the concept stage first')
    private = private_folder(folder)
    with httpx.Client(headers={'Authorization': 'Bearer ' + credential()}, timeout=httpx.Timeout(180, connect=20)) as client:
        job_path = folder / 'job.json'
        if not job_path.exists() or read_json(job_path).get('input_sha256') != sha(image):
            if (private / 'submission-started.json').exists() and not job_path.exists():
                raise SystemExit('An earlier Tripo POST may have succeeded; reconcile api-private/ before submitting again.')
            write_json(folder / 'balance-before.json', {'checked_at': now(), **call(client, 'GET', '/account/balance')['data']})
            with image.open('rb') as f: token = call(client, 'POST', '/files', files={'file': (image.name, f, 'image/png')})['data']['file_token']
            settings = {'model': 'P2-20260801', 'quad': False, 'face_limit': faces, 'texture': True, 'pbr': False, 'texture_quality': 'detailed',
                        'export_uv': True, 'model_seed': 9242026, 'texture_seed': 9242026, 'texture_alignment': 'original_image'}
            payload = {'input': token, **settings}
            write_json(private / 'submission-started.json', {'started_at': now(), 'request': payload}, private=True)
            response = call(client, 'POST', '/generation/image-to-model', json=payload)
            write_json(private / 'submission-response.json', response, private=True)
            write_json(job_path, {'stage': 'live_prop', 'slug': slug, 'endpoint': '/generation/image-to-model', 'settings': settings,
                                  'input': 'concept.png', 'input_sha256': sha(image), 'submitted_at': now(), 'task_id': response['data']['task_id'],
                                  'status': 'submitted', 'user_approval': 'live_workshop'})
            (private / 'submission-started.json').unlink()
            print('Submitted Tripo task', response['data']['task_id'], flush=True)
        fetch(client, folder, True)
        write_json(folder / 'balance-after.json', {'checked_at': now(), **call(client, 'GET', '/account/balance')['data']})
    downloads = read_json(folder / 'downloads.json')
    glbs = [d for d in downloads if d['file'].endswith('.glb')]
    if not glbs: raise SystemExit('Tripo returned no GLB: ' + json.dumps(downloads))
    best = next((d for d in glbs if 'pbr' not in d['output_field']), glbs[0])
    target = folder / f'{slug}.glb'; shutil.copyfile(folder / best['file'], target)
    ignore = folder / '.gitignore'   # the raw GLB is a byte copy of <slug>.glb (downloads.json keeps its hash)
    lines = ignore.read_text().splitlines() if ignore.exists() else []
    if 'raw/*.glb' not in lines: ignore.write_text('\n'.join([*lines, 'raw/', 'raw/*.glb']).strip() + '\n')
    print(target.relative_to(ROOT))


def main():
    env()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('stage', choices=['concept', 'model', 'make']); ap.add_argument('slug'); ap.add_argument('description', nargs='?')
    ap.add_argument('--faces', type=int, default=6000)
    a = ap.parse_args()
    if a.stage in ('concept', 'make'):
        if not a.description: raise SystemExit('a description is needed')
        concept(a.slug, a.description)
    if a.stage in ('model', 'make'): model(a.slug, a.faces)


if __name__ == '__main__':
    main()
