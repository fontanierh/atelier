#!/usr/bin/env python3
"""Tree house props: a Sunburst concept of each object alone, painted from the place reference it appears in, then a
Tripo image-to-model. Two stages, so the concepts can be checked before any credits are spent.

    uv run python games/yorimichi/tools/treehouse_props.py concept [--only kamado,globe] [--dry-run]
    uv run python games/yorimichi/tools/treehouse_props.py model [--only ...] [--dry-run] [--approval "..."]
    uv run python games/yorimichi/tools/treehouse_props.py sheet

Each prop lives in games/yorimichi/assets/treehouse/props/<slug>/: concept.jpg with prompt.txt and provenance.json,
then job.json (the Tripo settings, task id and credits) and <slug>.glb, the model with its texture made a 1024 JPEG.
concept: gpt-image-2.5-sunburst, quality high, 1024x1024, through /v1/images/edits with the place references as
context; it always paints a new concept and sets the old one aside as concept.rejected-N.jpg (kept out of git).
model: Tripo P2 image-to-model with a detailed texture, skipped when the committed job was made from the current
concept. A task is submitted once and resumed by id; an uncertain POST is never repeated (atelier.ai.tripo_asset). The
Tripo work folder, raw downloads and private API responses stay in build/yorimichi/treehouse/tripo/<slug>/.
Keys come from OPENAI_API_KEY and TRIPO_API_KEY (or the ignored .env). world/regions/treehouse/props.py (Blender)
reads PROPS and OUT from here and fits each GLB to its size for the game, so nothing heavy is imported at load time.
"""
import sys as _sys; from pathlib import Path as _Path; _sys.path.insert(0, str(_Path(__file__).resolve().parents[1] / 'world')); import yori  # noqa: E402
_sys.path.insert(0, str(_Path(__file__).resolve().parent))
import argparse, json, time
from concurrent.futures import ThreadPoolExecutor

from treehouse_art import (MODEL, QUALITY, ORIGINALS, REFS, SHEETS, TRIPO, compact_glb, keep, ledger_error, now, redact,
                           rel, set_aside, sha, sheet as contact_sheet, sunburst)

OUT = yori.ASSETS/'treehouse'/'props'
SIZE = '1024x1024'

STYLE = ("Paint ONE object alone for 3D reconstruction: shown whole, in a three-quarter front view from slightly above, "
         "centred with a clear margin all round, on a plain flat light-grey background, soft even light, no cast shadow, "
         "no floor, no text, nothing else in the picture. Keep the exact look of the object in the reference painting: "
         "the same colours, materials, proportions and hand-made character, in the same warm painterly style of a "
         "Japanese countryside adventure game: chunky readable shapes, gently rounded edges, matte hand-painted colours "
         "with soft variation, clear wood grain and weave where they belong, no photographic noise, no glossy highlights. "
         "Every part must be solid and connected; nothing floating. ")

# slug: (reference views, where it is in them, the object, size in metres for the game (longest side or height))
PROPS = {
    'kamado': (['kitchen-inside'], 'right of centre, under the black chimney pipe',
               'a small rounded clay-and-stone kamado cooking stove, grey-brown plastered body with a glowing arched fire '
               'opening at the front, a black cast-iron kettle and a black iron pot with a wooden lid sitting on top, '
               'a few split logs stacked against its base', 1.05),
    'stump_kettle': (['heart-inside'], 'the low tree-stump table in the middle of the room, before the trunk',
                     'a short thick tree-stump side table with rough bark on the sides and a pale ring-cut top, a black '
                     'cast-iron tetsubin teapot and a small blue-glazed cup on top', .55),
    'telescope': (['crow-sea'], 'bottom left, beside the child at the rail',
                  'a brass telescope on a wooden tripod with three splayed legs, the tube tilted up towards the sea, a '
                  'dark leather grip band and a small brass eyepiece', 1.45),
    'backpack': (['entry-inside', 'library-inside'], 'the green bag leaning by the wall and the crates',
                 'a child\'s olive-green canvas adventurer backpack with a rolled blanket strapped on top, two front '
                 'pockets with leather straps and brass buckles, standing upright', .55),
    'bell': (['crow-sea', 'heart-inside'], 'the brass bell hanging at the top of the picture',
             'a brass ship\'s bell hanging from a short curved wooden bracket, with a braided rope pull hanging from '
             'its clapper', .75),
    'globe': (['library-inside'], 'on the shelf at the left, in front of the map',
              'a small desk globe on a turned wooden stand with a brass half-meridian ring, the globe painted with '
              'soft blue seas and green-and-sand islands', .45),
    'basket': (['pulley-approach'], 'hanging from the pulley crane at the top left',
               'a round woven wicker basket with a flat base and a thick rim, four short ropes rising from the rim and '
               'tied together to a single iron ring above it', .85),
    'barrel': (['kitchen-inside'], 'bottom right, the wooden tub in the foreground',
               'a wooden water barrel of vertical staves held by two dark bamboo hoops, a round plank lid half open, '
               'and a long-handled wooden ladle resting across it', .8),
    'futon': (['sleep-inside'], 'the patchwork bed on the floor at the bottom of the picture',
              'a thick Japanese futon on the floor with a puffy patchwork quilt of large squares: indigo cotton with small '
              'white hemp-leaf and star stitching, cream, persimmon orange, faded red with one white maple leaf; no stripes '
              'and nothing like a national flag; a plump cream buckwheat pillow at the head', 2.0),
    'log_table': (['kitchen-inside'], 'the round log table in the middle, with the stools',
                  'a low round table cut from a thick tree trunk with rough bark on the sides and a pale ring-cut top, '
                  'on it a blue-and-white teapot, a mug, a wooden bowl of orange persimmons and a small jar of '
                  'wild flowers', .95),
    'bookshelf': (['library-inside', 'heart-inside'], 'the tall shelves full of books, jars and shells',
                  'a tall narrow rustic wooden bookshelf with four shelves filled with old books in muted blue, red, '
                  'green and brown, glass jars of acorns and shells, a spiral sea shell and a small potted plant on top', 1.9),
    'crate_desk': (['library-inside'], 'the desk under the window, made from plank on crates',
                   'a child\'s rustic writing desk made of a thick plank laid across two wooden crates, on top an open '
                   'hand-drawn island map, a brass compass, a magnifying glass, a small glowing oil lamp and two '
                   'rolled charts', 1.4),
    'planter': (['kitchen-approach', 'chimes-approach'], 'the wooden crates with flowers on the decks',
                'a weathered wooden crate planter full of soil with small autumn flowers in orange, yellow and white '
                'and green herbs spilling over the edge', .7),
}


def prompt_for(slug):
    views, where, what, _ = PROPS[slug]
    ctx = ' '.join(f'Image {i+1} is a finished painting of the tree house; the object is {where}.' if i == 0 else
                   f'Image {i+1} is another painting where the same kind of object appears.' for i in range(len(views)))
    return f'{STYLE}\n\n{ctx}\n\nThe object: {what}.'


def concept(slug, dry):
    folder = OUT/slug
    views = PROPS[slug][0]; refs = [REFS/f'{v}.jpg' for v in views]; prompt = prompt_for(slug)
    if dry:
        print(f'--- {slug}: {[r.name for r in refs]}\n{prompt}\n'); return slug, None
    missing = [rel(r) for r in refs if not r.exists()]
    if missing: return slug, f'missing references {missing}'
    folder.mkdir(parents=True, exist_ok=True)
    from atelier.ai.ledger import run_once
    image = folder/'concept.jpg'; ledger = folder/'provenance.json'
    if image.exists():   # painting a prop again: its earlier concept and record are set aside, not overwritten
        set_aside(image)
        if (ORIGINALS/'props'/slug/'concept.png').exists(): set_aside(ORIGINALS/'props'/slug/'concept.png')
        if ledger.exists(): set_aside(ledger)
    (folder/'prompt.txt').write_text(prompt+'\n')
    t = time.time(); error = None

    def generate():
        png, usage = sunburst(prompt, SIZE, refs)
        digest, record = keep(png, 'props', f'{slug}/concept', image)
        return dict(elapsed_seconds=round(time.time()-t, 1), usage=usage, concept_sha256=digest, compact_copy=record)
    try:   # the record is written before the paid call; a failed or uncertain one is never sent again by itself
        run_once(ledger, dict(
            stage='treehouse-prop-concept', slug=slug, requested_model=MODEL, quality=QUALITY, size=SIZE,
            endpoint='/v1/images/edits', execution='games/yorimichi/tools/treehouse_props.py', prompt_sha256=sha(prompt.encode()),
            reference_files={rel(r): sha(r.read_bytes()) for r in refs}), generate)
    except Exception as e:  # noqa: BLE001 - the ledger keeps it; the batch goes on
        error = ledger_error(ledger, e)
    print(slug, error or f'ok {time.time()-t:.0f}s', flush=True)
    return slug, error


def made_from(job):
    """The concept a job was made from (older jobs recorded only the uploaded file, which was that concept)."""
    return job.get('concept_sha256') or job.get('input_sha256')


def model(slug, faces, approval, dry, out=None, tripo=None, originals=None, stage='treehouse_prop', record='provenance.json'):
    """out, tripo, originals: the committed props, Tripo work and full-size concept folders (default the tree
    house's), record: the concept's provenance file; tools/hidamari_props.py models the city's props with the same steps."""
    folder = (out or OUT)/slug; work = (tripo or TRIPO)/slug
    if not (folder/'concept.jpg').exists() or not (folder/record).exists(): return slug, 'no concept'
    wanted = json.loads((folder/record).read_text()).get('concept_sha256')
    if not wanted: return slug, f'the concept has no hash in {record}'
    done = folder/'job.json'
    if done.exists() and (folder/f'{slug}.glb').exists() and made_from(json.loads(done.read_text())) == wanted:
        print(slug, 'already modelled from this concept', flush=True); return slug, None
    original = (originals or ORIGINALS/'props')/slug/'concept.png'   # the full-size painting when this machine made it
    image = original if original.exists() and sha(original.read_bytes()) == wanted else folder/'concept.jpg'
    if dry:
        print(f'--- {slug}: would submit {rel(image)} to Tripo P2 image-to-model, {faces} faces', flush=True)
        return slug, None
    from atelier.ai.tripo_asset import call, credential, write_json, read_json, private_folder, fetch
    import httpx
    private = private_folder(work)
    try:
        with httpx.Client(headers={'Authorization': 'Bearer '+credential()}, timeout=httpx.Timeout(180, connect=20)) as client:
            job_path = work/'job.json'
            if not job_path.exists() or made_from(read_json(job_path)) != wanted:
                if (private/'submission-started.json').exists() and not job_path.exists():
                    return slug, f'an earlier Tripo POST may have succeeded; reconcile {rel(private)} first'
                kind = 'image/png' if image.suffix == '.png' else 'image/jpeg'
                with image.open('rb') as f:
                    token = call(client, 'POST', '/files', files={'file': (image.name, f, kind)})['data']['file_token']
                settings = {'model': 'P2-20260801', 'quad': False, 'face_limit': faces, 'texture': True, 'pbr': False,
                            'texture_quality': 'detailed', 'export_uv': True, 'model_seed': 9292026, 'texture_seed': 9292026,
                            'texture_alignment': 'original_image'}
                payload = {'input': token, **settings}
                write_json(private/'submission-started.json', {'started_at': now(), 'request': payload}, private=True)
                response = call(client, 'POST', '/generation/image-to-model', json=payload)
                write_json(private/'submission-response.json', response, private=True)
                if job_path.exists(): job_path.rename(work/f'job.{int(time.time())}.json')
                write_json(job_path, {'stage': stage, 'slug': slug, 'endpoint': '/generation/image-to-model',
                                      'settings': settings, 'input': image.name, 'input_sha256': sha(image.read_bytes()),
                                      'concept_sha256': wanted, 'submitted_at': now(),
                                      'task_id': response['data']['task_id'], 'status': 'submitted',
                                      'user_approval': approval})
                (private/'submission-started.json').unlink()
                print(slug, 'submitted', response['data']['task_id'], flush=True)
            fetch(client, work, True)
    except (Exception, SystemExit) as e:  # noqa: BLE001 - a missing key stops only this prop, with its message
        return slug, redact(e)[:400]
    downloads = read_json(work/'downloads.json')
    glbs = [d for d in downloads if d['file'].endswith('.glb')]
    if not glbs: return slug, 'no GLB'
    best = next((d for d in glbs if 'pbr' not in d['output_field']), glbs[0])
    (folder/f'{slug}.glb').write_bytes(compact_glb((work/best['file']).read_bytes()))
    write_json(done, read_json(work/'job.json'))   # the public record: settings, task id, status, credits
    print(slug, 'model', rel(folder/f'{slug}.glb'), flush=True)
    return slug, None


def sheet():
    return contact_sheet([(OUT/s/'concept.jpg', s) for s in PROPS], SHEETS/'props-sheet.jpg', 384, 384, 5)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('stage', choices=['concept', 'model', 'sheet'])
    ap.add_argument('--only', default=''); ap.add_argument('--dry-run', action='store_true')
    ap.add_argument('--faces', type=int, default=9000); ap.add_argument('--concurrency', type=int, default=5)
    ap.add_argument('--approval', default='pending', help='who approved spending the credits, kept in job.json')
    a = ap.parse_args()
    slugs = [s for s in PROPS if not a.only or s in a.only.split(',')]
    if a.stage == 'sheet': return sheet()
    if a.stage == 'concept' and not a.dry_run:
        from atelier.env import require
        require('OPENAI_API_KEY')   # loads the ignored .env; stops with a clear message, never prints the value
    job = (lambda s: concept(s, a.dry_run)) if a.stage == 'concept' else (lambda s: model(s, a.faces, a.approval, a.dry_run))
    with ThreadPoolExecutor(1 if a.dry_run else a.concurrency) as ex:
        results = list(ex.map(job, slugs))
    bad = [(s, e) for s, e in results if e]
    for s, e in bad: print('FAILED', s, e)
    if a.stage == 'concept' and not a.dry_run: sheet()
    raise SystemExit(1 if bad else 0)


if __name__ == '__main__':
    main()
