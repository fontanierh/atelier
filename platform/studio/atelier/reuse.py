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
from . import build_snapshot
from .safety.render_lock import render_lock

# Send our inspector to the receiving checkout's interpreter; its imports resolve there.
INSPECT = Path(__file__).with_name('reuse_inspect.py').read_text()


def git(repo, *args):
    return subprocess.check_output(['git', '-C', str(repo), *args], text=True).strip()


def inspect(repo, game):
    env = dict(os.environ)
    env.pop('ATELIER_BUILD_ROOT', None)
    script = 'import sys\nsys.path.insert(0, ' + repr(str(repo / 'platform/studio')) + ')\nGAME=' + repr(game) + '\n' + INSPECT
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
    return [(s['name'], s.get('verified_fingerprint', s['fingerprint'])) for s in snapshot['steps']]


def _products(snapshot):
    """Include leaves: their bytes need not appear in any consumer's fingerprint."""
    return [(s['name'], s.get('products', {})) for s in snapshot['steps']]


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
    """@cc [owner:fontanierh,label:correctness] verified-snapshot-reuse
    Named products MUST match the donor stamps and the independently copied target byte for byte.
    A journal MUST block build/play/package until all checks and stamp installation complete.
    Registry caches MUST NOT be carried over or left stale in the receiving checkout.
    """
    source, target = Path(source).resolve(), Path(target or paths.REPO).resolve()
    if source == target:
        raise ValueError('Use a separate fresh worktree as the target')
    if '/' in game or game in ('.', '..'):
        raise ValueError('Invalid game ID')
    revision = git(source, 'rev-parse', 'HEAD')
    if revision != git(target, 'rev-parse', 'HEAD'):
        raise ValueError('Source and target must have exactly the same source revision before reusing artifacts')
    for repo in (source, target):
        build_snapshot.require_complete(repo / 'build' / game, game=game, repo=repo)
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
        invalid = [s['name'] for s in before['steps'] if not s['outputs_ok'] or s['stamp'].get('fingerprint') != s['fingerprint']
                   or s.get('made') and s['stamp'].get('result') != s['made']
                   or 'products' in s and s['stamp'].get('products', {}) != s['products']]
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
        from .reuse_inspect import excluded
        copies = [item for item in (source / 'build' / game).iterdir() if not excluded(item.name)]
        copies += [game_root / 'Content', game_root / 'Binaries']
        copies += [b for b in (source / 'platform/engine/Plugins').rglob('Binaries') if b.is_dir() and 'Intermediate' not in b.parts]
        if found := occupied(target, [item.relative_to(source) for item in copies]):
            raise ValueError('Target already has its own files where artifacts would be copied; use a fresh worktree: '
                             + ', '.join(found[:5]) + (f' and {len(found) - 5} more' if len(found) > 5 else ''))
        # A fresh editor/cooker discovers copied packages from disk. Refuse a target with local
        # discovery caches rather than transplanting the donor's Intermediate/Saved registry.
        target_project = target / game_root.relative_to(source)
        if any((target_project / name).exists() for name in ('Intermediate', 'Saved')):
            raise ValueError('Target has Unreal Intermediate/Saved state; use a fresh worktree for registry discovery')
        out = target / 'build' / game
        out.mkdir(parents=True, exist_ok=True)
        journal = out / build_snapshot.JOURNAL
        with journal.open('x') as handle:
            json.dump({'schema': 1, 'revision': revision, 'source': str(source),
                       'copies': [item.relative_to(source).as_posix() for item in copies]}, handle)
            handle.flush()
            os.fsync(handle.fileno())
        for item in copies:
            copy_tree(item, target / item.relative_to(source), source, target, clone)
        after = inspect(target, game)
        donor_after = inspect(source, game)
        if _inputs(before) != _inputs(after) or _inputs(before) != _inputs(donor_after):
            raise ValueError('Inputs changed during copying; target stamps have not been created')
        if _products(before) != _products(after) or _products(before) != _products(donor_after):
            raise ValueError('Products changed during copying; target stamps have not been created')
        for repo in (source, target):
            if git(repo, 'rev-parse', 'HEAD') != revision or git(repo, 'status', '--porcelain', '--untracked-files=no'):
                raise ValueError('Source revision changed during copying; target stamps have not been created')
        if not all(s['outputs_ok'] for s in after['steps']):
            raise ValueError('Required outputs are missing; target stamps have not been created')
        stamps = target / 'build' / game / 'stamps'
        stamps.mkdir(parents=True, exist_ok=True)
        target_steps = {step['name']: step for step in after['steps']}
        for step in before['steps']:
            stamp = dict(step['stamp'], fingerprint=target_steps[step['name']]['fingerprint'], reused_from=str(source))
            (stamps / (step['name'] + '.json')).write_text(json.dumps(stamp) + '\n')
            peak = source / 'build' / game / 'logs' / (step['name'] + '.guard') / 'step-peak.json'
            if peak.exists():
                copy_tree(peak, target / 'build' / game / 'logs' / (step['name'] + '.guard') / 'step-peak.json', source, target, clone)
        completion = out / build_snapshot.COMPLETE
        temporary = completion.with_suffix('.tmp')
        temporary.write_text(json.dumps({'schema': 1, 'revision': revision, 'steps': _inputs(after)}) + '\n')
        temporary.replace(completion)
        journal.unlink()
    print(f'Reused {len(before["steps"])} verified steps in {target}; run uv sync there, then atelier build/play.')
    return 0


def abandon(game, target=None):
    """Remove only the recorded generated copy, preserving tracked sources and diagnostic logs."""
    target = Path(target or paths.REPO).resolve()
    if '/' in game or game in ('.', '..'):
        raise ValueError('Invalid game ID')
    out = target / 'build' / game
    journal = out / build_snapshot.JOURNAL
    with render_lock('abandon interrupted ' + game + ' reuse'):
        if not journal.exists():
            raise SystemExit('No interrupted reuse to abandon')
        record = json.loads(journal.read_text())
        if record.get('schema') != 1 or not isinstance(record.get('copies'), list):
            raise SystemExit('Unrecognised reuse journal; preserve it and use a fresh worktree')
        roots = []
        from .reuse_inspect import excluded
        for relative in record['copies']:
            path = Path(relative)
            parts = path.parts
            in_build = parts[:2] == ('build', game) and len(parts) >= 3 and not excluded(parts[2])
            in_game = parts in (('games', game, 'unreal', 'Content'), ('games', game, 'unreal', 'Binaries'))
            in_plugin = parts[:3] == ('platform', 'engine', 'Plugins') and len(parts) >= 5 and parts[-1] == 'Binaries'
            if path.is_absolute() or '..' in parts or not (in_build or in_game or in_plugin):
                raise SystemExit('Unsafe path in reuse journal; no files removed')
            absolute = target / path
            roots.append(absolute)
        roots += [out / 'stamps', out / build_snapshot.COMPLETE]
        for absolute in [*roots, journal]:
            if any(p.is_symlink() for p in absolute.parents if p != target and p.is_relative_to(target)):
                raise SystemExit('Linked ancestor of a copied path; no files removed')
        tracked = set(subprocess.check_output(['git', '-C', str(target), 'ls-files', '-z']).decode().split('\0'))

        def remove(path):
            if path.relative_to(target).as_posix() in tracked:
                return
            if path.is_symlink() or path.is_file():
                path.unlink()
            elif path.is_dir():
                for child in path.iterdir():
                    remove(child)
                if not any(path.iterdir()):
                    path.rmdir()

        for root in roots:
            remove(root)
        journal.unlink()
    print('Partial generated copy removed; tracked sources and logs preserved. Reuse again or build normally.')
    return 0
