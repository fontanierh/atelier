#!/usr/bin/env python3
"""Ship the owner's Crater Park editor design to the game: freeze it, pin its compiler, build.

    uv run python games/yorimichi/tools/ship_craterpark_editor.py [--lines L1,L2] [--build]

1. Freeze. The live editor folder (park.json, data/ and pieces.js) is copied to ship/rev<N> beside it, where N is
   park.json's rev. A frozen revision is never overwritten: if ship/rev<N> exists with other bytes, edit once more in
   the editor (the rev goes up) and ship again.
2. Pin. If the editor's pieces.js changed, it is vendored as editor/pieces.cjs and its hash pinned in editor/pin.json,
   then the bridge validates and meshes the frozen park. A park the game cannot read fails here, not in Unreal.
3. Build. With --build, runs `nice -n 10 atelier build yorimichi` under the render lock and memory guard with
   ATELIER_CRATERPARK_EDITOR_PARK and ATELIER_CRATERPARK_EDITOR_LINES set; otherwise prints that command.
   Only the chosen lines are built, plus the bowls they land in and the decks they start from.

The editor's own code (index.html, app.js, server.py, cpe_client.py, vendor/) is refreshed in tools/craterpark_editor
from the live folder, and the frozen design is kept as tools/craterpark_editor/designs/craterpark-rev<N>.json.
Commit those with the re-pinned pieces.cjs and pin.json, so main carries the editor and the design the release used.
"""
import argparse
import hashlib
import json
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
V2 = ROOT / 'games/yorimichi/world/regions/craterpark/v2'
VENDORED = V2 / 'editor'
APP = ROOT / 'games/yorimichi/tools/craterpark_editor'      # the editor's reviewed copy (pieces.js links to pieces.cjs)
APP_CODE = ['index.html', 'app.js', 'server.py', 'cpe_client.py', 'vendor']
EDITOR = Path.home() / '.cache/atelier/handoff/craterpark/editor'   # served on the tailnet at /parkeditor/

sys.path.insert(0, str(V2.parents[1]))
sys.path.insert(0, str(V2.parents[2]))


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def tree(directory):
    """{relative path: sha256} of every file under directory."""
    return {str(p.relative_to(directory)): sha(p) for p in sorted(Path(directory).rglob('*')) if p.is_file()}


def freeze(editor):
    rev = json.loads((editor / 'park.json').read_text())['rev']
    target = editor.parent / 'ship' / f'rev{rev}'
    staging = Path(tempfile.mkdtemp(prefix=f'rev{rev}-', dir=editor.parent))
    shutil.copy2(editor / 'park.json', staging / 'park.json')
    shutil.copy2(editor / 'pieces.js', staging / 'pieces.js')
    shutil.copytree(editor / 'data', staging / 'data')
    if target.exists():
        same = tree(target) == tree(staging)
        shutil.rmtree(staging)
        if not same:
            raise SystemExit(f'{target} already holds a different rev {rev}; save once more in the editor and ship again')
        print(f'rev {rev} already frozen at {target}')
    else:
        target.parent.mkdir(exist_ok=True)
        staging.rename(target)
        print(f'froze rev {rev} at {target}')
    return target


def pin(frozen):
    pin_path = VENDORED / 'pin.json'
    pinned = json.loads(pin_path.read_text())
    current = sha(frozen / 'pieces.js')
    if current != pinned['pieces_sha256']:
        shutil.copy2(frozen / 'pieces.js', VENDORED / 'pieces.cjs')
        pinned['pieces_sha256'] = current
        pin_path.write_text(json.dumps(pinned, indent=2) + '\n')
        print(f'pinned the editor compiler {current[:16]} (commit editor/pieces.cjs and editor/pin.json)')
    from craterpark.v2.editor import frontend
    with tempfile.TemporaryDirectory() as tmp:
        snapshot = frontend.snapshot(frozen / 'park.json', Path(tmp) / 'snapshot')
        scene = frontend.compile_snapshot(snapshot, Path(tmp) / 'mesh', timeout=600)
    print(f'bridge meshed {len(scene.pieces)} pieces')


def sync_app(editor, frozen):
    """Refresh the repository copy of the editor's code and keep the shipped design beside it."""
    changed = []
    for name in APP_CODE:
        source, target = editor / name, APP / name
        if source.is_dir():
            if not target.exists() or tree(source) != tree(target):
                shutil.rmtree(target, ignore_errors=True)
                shutil.copytree(source, target)
                changed.append(name)
        elif not target.exists() or sha(source) != sha(target):
            shutil.copy2(source, target)
            changed.append(name)
    rev = frozen.name.removeprefix('rev')
    design = APP / 'designs' / f'craterpark-rev{rev}.json'
    if not design.exists():
        design.parent.mkdir(exist_ok=True)
        shutil.copy2(frozen / 'park.json', design)
        changed.append(str(design.relative_to(APP)))
    if changed:
        print(f'refreshed tools/craterpark_editor: {", ".join(changed)} (commit them)')


def main():
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--editor', type=Path, default=EDITOR, help='the live editor folder')
    parser.add_argument('--lines', default='L1', help='comma-separated line ids to build (L1 is orange)')
    parser.add_argument('--build', action='store_true', help='run the guarded game build')
    args = parser.parse_args()
    frozen = freeze(args.editor.expanduser())
    pin(frozen)
    sync_app(args.editor.expanduser(), frozen)
    env = {'ATELIER_CRATERPARK_EDITOR_PARK': str(frozen / 'park.json'), 'ATELIER_CRATERPARK_EDITOR_LINES': args.lines}
    command = ['nice', '-n', '10', 'uv', 'run', 'atelier', 'build', 'yorimichi']
    shown = ' '.join(f'{k}={shlex.quote(v)}' for k, v in env.items()) + ' ' + shlex.join(command)
    if not args.build:
        print(f'build with:\n  {shown}')
        return
    print(f'$ {shown}', flush=True)
    raise SystemExit(subprocess.call(command, cwd=ROOT, env={**os.environ, **env}))


if __name__ == '__main__':
    main()
