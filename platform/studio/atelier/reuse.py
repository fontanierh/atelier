"""Seed a fresh worktree with verified independent build artifacts, leaving mutable Unreal intermediates behind.

The source and target must be clean at the same revision, with matching inputs and installed engine. Before copying,
each step's source fingerprint must match: its inputs outside the folders being copied (a step may also hash generated
Content, such as a multiplayer identity, which a fresh checkout cannot have yet). Tracked files in those folders are
covered by the clean same-revision checks, and the target must have no untracked or ignored files there, so nothing of
its own is overwritten. After copying, every full fingerprint must match. APFS clones copy on write; ordinary copies are
used elsewhere. Only successful, current source stamps are carried over.
"""
import ctypes
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

from . import paths
from .safety.render_lock import render_lock

INSPECT = '''import json
from pathlib import Path
from dataclasses import replace
from atelier.build import Context,load_recipe,order,fingerprint
try: from atelier.build import result as published
except ImportError: published=lambda step,value,stamp: value   # a donor from before cutoff steps
from atelier import manifest
ctx=Context(GAME)
# A step's source fingerprint leaves out its inputs inside the copied folders; kept here, not in atelier.build, so a
# donor checkout of an older revision can be inspected too.
artifacts=[p.resolve() for p in [ctx.out]+([ctx.uproject.parent/'Content'] if ctx.uproject else [])]
def own(step): return replace(step,inputs=[i for i in step.inputs if not any(Path(i).resolve().is_relative_to(a) for a in artifacts)])
done={}; sources={}; result=[]
for step in order(load_recipe(GAME).steps(ctx),[]):
 value=fingerprint(step,done)
 source=fingerprint(own(step),sources); sources[step.name]=source
 path=ctx.stamps/(step.name+'.json')
 stamp=json.loads(path.read_text()) if path.exists() else {}
 done[step.name]=published(step,value,stamp)
 result.append(dict(name=step.name,fingerprint=value,source=source,stamp=stamp,outputs_ok=all(Path(p).exists() for p in step.outputs)))
print(json.dumps(dict(steps=result,engine=str(ctx.unreal_root.resolve()),project=ctx.uproject.stem,
 editor_target=manifest.game(GAME)['editor_target'],
 build_version=json.loads((ctx.unreal_root/'Engine/Build/Build.version').read_text()))))
'''


def git(repo, *args):
    return subprocess.check_output(['git', '-C', str(repo), *args], text=True).strip()


def inspect(repo, game):
    env = dict(os.environ, PYTHONPATH=str(repo / 'platform/studio'))
    env.pop('ATELIER_BUILD_ROOT', None)
    script = 'GAME=' + repr(game) + '\n' + INSPECT
    return json.loads(subprocess.check_output([sys.executable, '-c', script], cwd=repo, env=env, text=True))


def copy_tree(source, target, source_repo, target_repo, clone):
    if not source.exists() and not source.is_symlink():
        return
    if source.is_dir() and not source.is_symlink():
        target.mkdir(parents=True, exist_ok=True)
        for item in source.iterdir():
            copy_tree(item, target / item.name, source_repo, target_repo, clone)
        shutil.copystat(source, target)
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() or target.is_symlink():
        target.unlink()
    if source.is_symlink():
        link = os.readlink(source)
        if link.startswith(str(source_repo) + '/'):
            link = str(target_repo) + link[len(str(source_repo)):]
        target.symlink_to(link)
    elif clone is not None and clone(os.fsencode(source), os.fsencode(target), 0) == 0:
        shutil.copystat(source, target)
    else:
        shutil.copy2(source, target)


def _inputs(snapshot):
    return [(s['name'], s['fingerprint']) for s in snapshot['steps']]


def differing_sources(source, target):
    """Steps whose source fingerprints differ between two snapshots, or that only one of them has."""
    theirs = {s['name']: s['source'] for s in target['steps']}
    names = [s['name'] for s in source['steps'] if theirs.pop(s['name'], None) != s['source']]
    return names + sorted(theirs)


def occupied(repo, folders):
    """Untracked or ignored files under the given repo-relative folders, which copying would overwrite unchecked."""
    if not folders:
        return []
    out = subprocess.check_output(['git', '-C', str(repo), 'status', '--porcelain', '--ignored', '--untracked-files=all',
                                   '--', *map(str, folders)], text=True)
    return [line[3:] for line in out.splitlines() if line[:2] in ('??', '!!')]


def main(game, source, target=None):
    source, target = Path(source).resolve(), Path(target or paths.REPO).resolve()
    if source == target:
        raise ValueError('Use a separate fresh worktree as the target')
    if '/' in game or game in ('.', '..'):
        raise ValueError('Invalid game ID')
    revision = git(source, 'rev-parse', 'HEAD')
    if revision != git(target, 'rev-parse', 'HEAD'):
        raise ValueError('Source and target must have exactly the same source revision before reusing artifacts')
    for repo in (source, target):
        if git(repo, 'status', '--porcelain', '--untracked-files=no'):
            raise ValueError(f'Tracked files must be clean before reusing artifacts: {repo}')
    if os.environ.get('ATELIER_BUILD_ROOT'):
        raise ValueError('Use the default per-worktree build folders when reusing artifacts')
    if any((target / 'build' / game / 'stamps').glob('*.json')):
        raise ValueError('Target already has build stamps; use its incremental build instead')
    clone = None
    if sys.platform == 'darwin':
        clone = ctypes.CDLL('/usr/lib/libSystem.B.dylib', use_errno=True).clonefile
        clone.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_int]
        clone.restype = ctypes.c_int
    with render_lock('reuse verified ' + game + ' artifacts'):
        before = inspect(source, game)
        invalid = [s['name'] for s in before['steps'] if not s['outputs_ok'] or s['stamp'].get('fingerprint') != s['fingerprint']]
        game_root = source / 'games' / game / 'unreal'
        module = game_root / 'Binaries/Mac' / ('libUnrealEditor-' + before['project'] + '.dylib')
        if invalid or not module.is_file():
            raise ValueError('Source build is not complete/current: ' + ', '.join(invalid or ['compiled module missing']))
        receipt = json.loads((module.parent / (before['editor_target'] + '.target')).read_text())
        for field in ('MajorVersion', 'MinorVersion', 'PatchVersion', 'Changelist', 'CompatibleChangelist', 'BranchName'):
            if receipt['Version'].get(field) != before['build_version'].get(field):
                raise ValueError('The compiled game uses a different engine version')
        engine_modules = Path(before['engine']) / 'Engine/Binaries/Mac/UnrealEditor.modules'
        game_modules = module.parent / 'UnrealEditor.modules'
        if json.loads(engine_modules.read_text())['BuildId'] != json.loads(game_modules.read_text())['BuildId']:
            raise ValueError('Compiled game and installed engine build IDs differ')
        dest_before = inspect(target, game)
        if before['build_version'] != dest_before['build_version'] or before['engine'] != dest_before['engine']:
            raise ValueError('Source and target must use the same installed engine')
        if differ := differing_sources(before, dest_before):
            raise ValueError('Source inputs differ, including untracked inputs; artifacts cannot be reused: ' + ', '.join(differ))
        copies = [item for item in (source / 'build' / game).iterdir() if item.name not in ('logs', 'stamps', 'remote-proof')]
        copies += [game_root / 'Content', game_root / 'Binaries']
        copies += [b for b in (source / 'platform/engine/Plugins').rglob('Binaries') if b.is_dir() and 'Intermediate' not in b.parts]
        if found := occupied(target, [item.relative_to(source) for item in copies]):
            raise ValueError('Target already has its own files where artifacts would be copied; use a fresh worktree: '
                             + ', '.join(found[:5]) + (f' and {len(found) - 5} more' if len(found) > 5 else ''))
        for item in copies:
            copy_tree(item, target / item.relative_to(source), source, target, clone)
        after = inspect(target, game)
        if _inputs(before) != _inputs(after) or _inputs(before) != _inputs(inspect(source, game)):
            raise ValueError('Inputs changed during copying; target stamps have not been created')
        for repo in (source, target):
            if git(repo, 'rev-parse', 'HEAD') != revision or git(repo, 'status', '--porcelain', '--untracked-files=no'):
                raise ValueError('Source revision changed during copying; target stamps have not been created')
        if not all(s['outputs_ok'] for s in after['steps']):
            raise ValueError('Required outputs are missing; target stamps have not been created')
        stamps = target / 'build' / game / 'stamps'
        stamps.mkdir(parents=True, exist_ok=True)
        for step in before['steps']:
            stamp = dict(step['stamp'], fingerprint=step['fingerprint'], reused_from=str(source))
            (stamps / (step['name'] + '.json')).write_text(json.dumps(stamp) + '\n')
            peak = source / 'build' / game / 'logs' / (step['name'] + '.guard') / 'step-peak.json'
            if peak.exists():
                copy_tree(peak, target / 'build' / game / 'logs' / (step['name'] + '.guard') / 'step-peak.json', source, target, clone)
    print(f'Reused {len(before["steps"])} verified steps in {target}; run uv sync there, then atelier build/play.')
    return 0
