"""One-way recovery for interrupted pre-checkpoint transfers; no build reuse entry point.

Only removal of the journaled partial generated copy remains. No commit matching, donor
inspection, artifact installation or stamp manufacturing is supported by this module.
"""
from contextlib import contextmanager
import fcntl
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import time
import uuid
from . import paths, build_snapshot

TRANSACTION_WAIT_SECONDS = 30.


def _launch(game, target):
    """Remove recorded partial outputs under ordinary owned-child admission."""
    action = 'abandon'
    from atelier.harness.safety import guarded
    identifier = uuid.uuid4().hex
    folder = target / 'build' / game / 'logs' / (f'reuse-{action}-{identifier}.guard')
    command = [sys.executable, '-m', 'atelier.legacy_transfer', action, game, str(target)]
    command += ['--invocation', identifier]
    print(f'{action} {game}: guarded artifact transfer; log {folder / "stdout.log"}', flush=True)
    code = guarded.run(command, folder, kind='job', aggregate_tree=True, timeout=1800,
                       progress=30, purpose=f'{action} verified {game} artifacts', invocation_id=identifier)
    return code


@contextmanager
def _transaction(game, target):
    """Serialize final publication with abandonment, without holding it during admission waits."""
    folder = target / 'build' / game / 'logs'
    folder.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(folder / '.reuse-transaction.lock', os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600)
    with os.fdopen(descriptor, 'r+b') as lock:
        info = os.fstat(lock.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_nlink != 1:
            raise ValueError('Reuse transaction mutex must be an owned regular single-link file')
        deadline = time.monotonic() + TRANSACTION_WAIT_SECONDS
        spoken = time.monotonic()
        while True:
            try:
                fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise RuntimeError('Receiving checkout is still finalizing or abandoning reuse; no files changed') from None
                if time.monotonic() - spoken >= 5:
                    print('Waiting for the receiving checkout reuse transaction to finish', flush=True)
                    spoken = time.monotonic()
                time.sleep(.05)
        yield


def _abandon(game, target=None):
    target = Path(target or paths.REPO).resolve()
    if '/' in game or game in ('.', '..'):
        raise ValueError('Invalid game ID')
    with _transaction(game, target):
        return _remove_partial(game, target)


def _remove_partial(game, target):
    """Remove only the recorded generated copy, preserving tracked sources and diagnostic logs."""
    target = Path(target or paths.REPO).resolve()
    if '/' in game or game in ('.', '..'):
        raise ValueError('Invalid game ID')
    out = target / 'build' / game
    journal = out / build_snapshot.JOURNAL
    if not journal.exists():
        raise SystemExit('No interrupted reuse to abandon')
    record = json.loads(journal.read_text())
    if record.get('schema') != 1 or not isinstance(record.get('copies'), list):
        raise SystemExit('Unrecognised reuse journal; preserve it and use a fresh worktree')
    roots = []
    excluded = lambda name: name in {'logs', 'stamps', 'remote-proof', '.state'} or name.startswith('.restore-') or name.endswith('.tmp')
    for relative in record['copies']:
        path = Path(relative)
        parts = path.parts
        in_build = parts[:2] == ('build', game) and len(parts) >= 3 and not excluded(parts[2])
        in_game = parts in (('games', game, 'unreal', 'Content'), ('games', game, 'unreal', 'Binaries'))
        in_plugin = ((parts[:3] == ('platform', 'engine', 'Plugins') and len(parts) >= 5)
                     or (parts[:4] == ('games', game, 'unreal', 'Plugins') and len(parts) >= 6)) and parts[-1] == 'Binaries'
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
    print('Partial generated copy removed; tracked sources and logs preserved. Run atelier build normally.')
    return 0


def abandon(game):
    if not game or '/' in game or game in ('.', '..'):
        raise ValueError('Invalid game ID')
    return _launch(game, paths.REPO.resolve())


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('operation', choices=['abandon'])
    parser.add_argument('game')
    parser.add_argument('target', type=Path)
    parser.add_argument('--invocation', required=True)
    args = parser.parse_args()
    raise SystemExit(_abandon(args.game, args.target))
