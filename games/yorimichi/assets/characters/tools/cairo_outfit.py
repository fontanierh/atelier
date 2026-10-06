"""One command for a new Cairo outfit: an outfit spec in; a skinned, captured and clipping-checked outfit out.

    ~/.cache/yorimichi/imagegen-venv/bin/python games/yorimichi/assets/characters/tools/cairo_outfit.py \\
        games/yorimichi/assets/characters/cairo/outfits/<slug>.toml [--dir body-swap-<slug>] [--status] [--spend] \\
        [--approve "who looked at what"] [--concept IMAGE] [--redo STAGE,...] [--until STAGE] [--source BLEND]

Run it from the Atelier checkout with YORIMICHI_ARCHIVE pointing at the prototype archive. API keys come from the
environment or from the ignored `.env` of this checkout or of the archive (never printed).

Every stage writes files into the revision folder (`output/imagegen/yorimichi-yellow-boy-2026-09-12/<dir>`, default
`body-swap-<slug>`). A stage is skipped when its files are there and newer than the stage before it, so rerunning the
same command continues where it stopped; `--redo` forces stages, and everything after them follows. Blender output
goes to `<dir>/logs/<stage>.log`, and `<dir>/outfit-run.json` records every stage run (time, seconds, result).

Stages (cost):
  references  the mannequin, no head or hands, four orthographic renders (Blender, free)
  concept     the approved concept sheet redrawn in the outfit (Sunburst, about $0.07); --concept IMAGE uses a picked design
  views       the mannequin dressed in the outfit, front/back/left/right (Sunburst, about $0.28)
  key         the same four views with the bare mannequin painted green (Sunburst, about $0.24)
  approve     stops here: look at the concept, views and keys, then rerun with --approve "..." to record it
  tripo       the clothed body from the four views (Tripo P2 multiview, 120 credits, 2 to 4 minutes)
  fit         the Tripo body aligned on the base body (Blender)
  assemble    head, hands, kept skin, weights, sleeves, skirts (Blender)
  capture     52 renders, 9 poses (Blender, about 3 minutes)
  check       clipping measure over 14 library clips (Blender, about 10 seconds)
  sheet       review.jpg: the captures to look at first, with the numbers
  export      GLB with every clip (only with --until export)

Paid stages run only with --spend; without it the driver stops before the first one that is not done yet and says
what it costs. The approval gate cannot be skipped: Tripo refuses views whose hashes are not in references/approval.json.
"""
import argparse, hashlib, json, os, shutil, subprocess, sys, time, tomllib
from datetime import datetime, timezone
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
REPO = TOOLS.parents[4]
sys.path.insert(0, str(TOOLS)); sys.path.insert(0, str(REPO / 'platform/studio'))
from _archive import ROOT  # noqa: E402
from atelier import env  # noqa: E402

CHAR = ROOT / 'output/imagegen/yorimichi-yellow-boy-2026-09-12'
BLENDER = os.environ.get('BLENDER', '/Applications/Blender.app/Contents/MacOS/Blender')
VIEWS = ('front', 'back', 'left', 'right')
STAGES = ('references', 'concept', 'views', 'key', 'approve', 'tripo', 'fit', 'assemble', 'capture', 'check', 'sheet', 'export')
PAID = {'concept': 'Sunburst, 1 image, about $0.07', 'views': 'Sunburst, 4 images, about $0.28',
        'key': 'Sunburst, 4 images, about $0.24', 'tripo': 'Tripo, 120 credits'}
FIRST_LOOK = ['standing--front-left', 'standing--back-right', 'standing--neck', 'standing--wrist-left',
              'sprint27--back', 'crouch--back', 'sit--front', 'doublejump--back']


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def outputs(stage, d, stem):
    return {'references': [d / f'references/naked-{v}.png' for v in VIEWS] + [d / 'references/envelope.json'],
            'concept': [d / 'concept.png'],
            'views': [d / f'references/{v}.png' for v in VIEWS],
            'key': [d / f'key/key-{v}.png' for v in VIEWS],
            'approve': [d / 'references/approval.json'],
            'tripo': [d / 'raw/output_model_url.fbx'],
            'fit': [d / 'fit/align.json'],
            'assemble': [d / f'assembled/{stem}.blend', d / 'assembled/assembly.json'],
            'capture': [d / 'captures/index.json'],
            'check': [d / 'qa/check.json'],
            'sheet': [d / 'review.jpg'],
            'export': [d / f'assembled/{stem}.glb']}[stage]


def records(stage, d):
    """The ledger records of a Sunburst stage (atelier.ai.ledger: the tool never sends a recorded call again by itself)."""
    return {'concept': [d / 'concept.provenance.json'], 'views': [d / f'references/{v}.provenance.json' for v in VIEWS],
            'key': [d / f'key/key-{v}.provenance.json' for v in VIEWS]}.get(stage, [])


def set_aside(stage, d):
    """--spend on a Sunburst stage that runs again pays for it again: its earlier records are kept as
    <name>.rejected-N.provenance.json, so the stage can write new ones."""
    for record in records(stage, d):
        if record.exists():
            name, n = record.name.removesuffix('.provenance.json'), 1
            while record.with_name(f'{name}.rejected-{n}.provenance.json').exists():
                n += 1
            record.rename(record.with_name(f'{name}.rejected-{n}.provenance.json'))


def approved(d):
    p = d / 'references/approval.json'
    if not p.exists():
        return False
    images = json.loads(p.read_text()).get('images', {})
    return all(images.get(f'{v}.png') == sha(d / f'references/{v}.png') for v in VIEWS if (d / f'references/{v}.png').exists())


def done(stage, d, stem):
    files = outputs(stage, d, stem)
    if stage == 'concept' and all(f.exists() for f in outputs('views', d, stem)):
        return True   # the views exist already (drawn from another design): the concept only serves to draw them
    if not all(f.exists() for f in files):
        return False
    if stage == 'approve':
        return approved(d)
    if stage == 'tripo':   # Tripo output is never redone by timestamps: it costs credits and job.json is its ledger
        return True
    before = [s for s in STAGES[:STAGES.index(stage)] if s not in ('approve', 'export')]
    prev = [f for f in outputs(before[-1], d, stem) if f.exists()] if before else []
    return not prev or min(f.stat().st_mtime for f in files) >= max(f.stat().st_mtime for f in prev)


def unshare(stage, d, stem):
    """A revision folder may link its inputs from another one (new rules rerun on the same Tripo model). A stage that
    runs here first drops its linked outputs, so it writes files of its own instead of through the links into the
    other revision."""
    own = {'fit': 'fit', 'assemble': 'assembled', 'capture': 'captures', 'check': 'qa'}.get(stage)
    for f in outputs(stage, d, stem) + (list((d / own).glob('*')) if own else []):
        if f.is_symlink():
            f.unlink()


def run(cmd, log, environ):
    log.parent.mkdir(exist_ok=True)
    with open(log, 'w') as fh:
        return subprocess.run(cmd, cwd=REPO, env=environ, stdout=fh, stderr=subprocess.STDOUT).returncode


def blender(script, log, environ, *args):
    return run([BLENDER, '-b', '--python-exit-code', '1', '--python', str(TOOLS / script), *(['--', *args] if args else [])], log, environ)


def sheet(d, stem, spec):
    from PIL import Image, ImageDraw, ImageFont
    tiles = [Image.open(d / 'concept.png').convert('RGB')] if (d / 'concept.png').exists() else []
    tiles += [Image.open(d / f'captures/{n}.png').convert('RGB') for n in FIRST_LOOK if (d / f'captures/{n}.png').exists()]
    h = 420; tiles = [t.resize((round(t.width * h / t.height), h)) for t in tiles]
    rows = [tiles[:5], tiles[5:]]
    W = max(sum(t.width for t in r) for r in rows if r)
    a = json.loads((d / 'assembled/assembly.json').read_text()); c = json.loads((d / 'qa/check.json').read_text())
    comp = a.get('components', {})
    lines = [f"{spec['name']}   ({d.relative_to(CHAR)})",
             f"garment faces {comp.get('garment_faces')}   skirt pieces {[t['faces'] for t in comp.get('skirt_test', []) if t['skirt']]}   "
             f"skirt vertices {a.get('skirt_vertices', 0)}",
             'kept skin ' + '   '.join(f"{k}: {v['faces']} faces ({v['bare_faces']} bare), deepest tuck {v['deepest_push_mm']} mm"
                                       for k, v in (a.get('kept_skin') or {}).items()),
             'clipping (cm2, minus bind pose): ' + '   '.join(f'{k} {v}' for k, v in c.get('summary', {}).items())]
    font = ImageFont.load_default(size=22)
    out = Image.new('RGB', (W, 2 * h + 34 * len(lines) + 20), (240, 240, 238)); dr = ImageDraw.Draw(out)
    for i, line in enumerate(lines):
        dr.text((12, 10 + 34 * i), line, fill=(20, 20, 20), font=font)
    y = 34 * len(lines) + 20
    for r in rows:
        x = 0
        for t in r:
            out.paste(t, (x, y)); x += t.width
        y += h
    out.save(d / 'review.jpg', quality=88)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('spec', type=Path, help='outfit spec, games/yorimichi/assets/characters/cairo/outfits/<slug>.toml')
    ap.add_argument('--dir', default='', help='revision folder under the character folder (default body-swap-<slug>)')
    ap.add_argument('--stem', default='', help='assembled file name (default Cairo-BodySwap-<slug>)')
    ap.add_argument('--source', default='', help='base character blend under the character folder (BODY_SWAP_SOURCE); '
                    'game-r10/WarmOriginal-Game-r10.blend for anything that goes to the game')
    ap.add_argument('--concept', type=Path, help='use this design image as concept.png instead of redrawing one')
    ap.add_argument('--spend', action='store_true', help='allow the paid stages (Sunburst, Tripo)')
    ap.add_argument('--approve', default='', help='record the review of the views and keys (who looked, what they checked)')
    ap.add_argument('--redo', default='', help='comma-separated stages to run again, with everything after them')
    ap.add_argument('--until', default='sheet', choices=STAGES, help='last stage to run (default sheet)')
    ap.add_argument('--status', action='store_true', help='print the state of every stage and exit')
    a = ap.parse_args()
    spec_path = a.spec.resolve(); spec = tomllib.loads(spec_path.read_text())
    slug = spec_path.stem
    rel = a.dir or f'body-swap-{slug}'; d = CHAR / rel; stem = a.stem or f'Cairo-BodySwap-{slug}'
    if not ROOT.exists():
        sys.exit('Set YORIMICHI_ARCHIVE to the prototype archive checkout.')
    d.mkdir(parents=True, exist_ok=True)
    gi = d / '.gitignore'
    if not gi.exists():
        gi.write_text('api-private/\n*.part\n*.blend1\n')
    env.load(); env.load(ROOT / '.env')
    environ = dict(os.environ, YORIMICHI_ARCHIVE=str(ROOT), PYTHONPATH=str(REPO / 'platform/studio'), BODY_SWAP_HEADLESS='1',
                   BODY_SWAP_DIR=rel, BODY_SWAP_STEM=stem)
    if a.source:
        environ['BODY_SWAP_SOURCE'] = a.source
    redo = {s for s in a.redo.split(',') if s}
    if redo - set(STAGES):
        sys.exit(f'unknown stage in --redo: {sorted(redo - set(STAGES))}')
    first_redo = min((STAGES.index(s) for s in redo), default=len(STAGES))
    last = STAGES.index(a.until)
    if a.status:
        for s in STAGES:
            print(f'{s:11s}', 'done' if done(s, d, stem) else '-', f'  ({PAID[s]})' if s in PAID else '')
        return
    ledger_path = d / 'outfit-run.json'
    ledger = json.loads(ledger_path.read_text()) if ledger_path.exists() else []
    py = sys.executable; sun = str(TOOLS / 'cairo_body_swap_sunburst.py'); ran = set()
    for i, s in enumerate(STAGES):
        if i > last:
            break
        if i < first_redo and done(s, d, stem):
            print(f'{s:11s} done')
            continue
        if s == 'approve':
            if not a.approve or ran & {'concept', 'views', 'key'}:   # nobody has seen images made in this run
                print('\napprove     STOP. Look at these before spending Tripo credits:')
                print(f'  {d / "concept.png"}')
                print('  ' + '  '.join(str(d / f'references/{v}.png') for v in VIEWS))
                print('  ' + '  '.join(str(d / f'key/key-{v}.png') for v in VIEWS))
                print('  The four views must agree (hem, collar, sleeves, shoes, colours); cuffs and the collar open, no head, no hands.')
                print('  The keys must be green exactly where the mannequin shows (neck stump, chest in the neckline, wrist stumps,')
                print('  bare arms or legs) and nowhere on cloth. Redo a bad view: --redo views --spend (or set aside its')
                print('  references/<view>.provenance.json and run the Sunburst tool with --only).')
                print('  Then rerun with --approve "<who reviewed, what they checked>".')
                return
            images = {f'{v}.png': sha(d / f'references/{v}.png') for v in VIEWS}
            (d / 'references/approval.json').write_text(json.dumps({
                'event': 'multiview_set_approved_for_tripo_generation', 'basis': a.approve, 'outfit_spec': spec_path.relative_to(REPO).as_posix(),
                'images': images, 'keys': {f'key-{v}.png': sha(d / f'key/key-{v}.png') for v in VIEWS},
                'view_convention': 'anatomical left/right; character faces +X, left +Y, up +Z',
                'approved_at': datetime.now(timezone.utc).isoformat()}, indent=2) + '\n')
            print(f'{s:11s} recorded')
            continue
        if s in PAID and not (s == 'concept' and a.concept):
            if not a.spend:
                print(f'\n{s:11s} STOP: costs {PAID[s]}. Rerun with --spend to pay for it.')
                return
            if s == 'tripo' and (d / 'job.json').exists():   # tripo_asset never pays twice for one folder
                if json.loads((d / 'job.json').read_text()).get('approved_inputs') != json.loads((d / 'references/approval.json').read_text())['images']:
                    sys.exit('The views changed after Tripo ran in this folder: start a new revision folder (--dir) for new views.')
                print(f'{s:11s} a Tripo job already exists ({d / "job.json"}); fetching it, not paying again')
            set_aside(s, d)
        print(f'{s:11s} running ...', flush=True)
        unshare(s, d, stem)
        t0 = time.time(); log = d / f'logs/{s}.log'
        if s == 'references':
            rc = blender('cairo_body_swap_references.py', log, environ, '--mannequin', rel)
        elif s == 'concept' and a.concept:
            shutil.copyfile(a.concept, d / 'concept.png'); rc = 0
        elif s == 'concept':
            rc = run([py, sun, '--headless', rel, '--outfit', str(spec_path), '--make-concept'], log, environ)
        elif s == 'views':
            rc = run([py, sun, '--headless', rel, '--outfit', str(spec_path)], log, environ)
        elif s == 'key':
            rc = run([py, sun, '--headless', rel, '--outfit', str(spec_path), '--key'], log, environ)
        elif s == 'tripo':
            rc = run([py, str(REPO / 'platform/studio/atelier/ai/tripo_asset.py'), 'generate', '--references', str(d / 'references'),
                      '--output', str(d), '--faces', '12000'], log, environ)
        elif s == 'sheet':
            sheet(d, stem, spec); rc = 0
        else:
            rc = blender(f'cairo_body_swap_{s}.py', log, environ)
        secs = round(time.time() - t0, 1)
        ledger.append({'stage': s, 'at': datetime.now(timezone.utc).isoformat(), 'seconds': secs, 'exit': rc})
        ledger_path.write_text(json.dumps(ledger, indent=1) + '\n')
        if rc != 0 or not all(f.exists() for f in outputs(s, d, stem)):
            tail = log.read_text().splitlines()[-15:] if log.exists() else []
            sys.exit(f'{s} failed (exit {rc}); log {log}\n' + '\n'.join(tail))
        ran.add(s); print(f'{s:11s} ok in {secs} s')
    print(f'\nDone up to {a.until}. Look at {d / "review.jpg"}, then the captures in {d / "captures"}.')


if __name__ == '__main__':
    main()
