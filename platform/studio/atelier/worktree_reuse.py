"""Certified task results from other checkouts and retained checkpoints, found by fingerprint.

A machine-wide index maps (game, task, fingerprint) to sibling Git worktrees whose stamp records
it; it is refreshed from stamp mtimes. Donor trees are only read: outputs are APFS clones, never
links, and a result counts only when the receiving build certifies the cloned outputs itself.
"""
import os
from pathlib import Path
import sqlite3
import subprocess
import time

from . import paths
from .native_protocol import CheckpointError, read_json, safe_destination


def database():
    return paths.cache_dir('reuse') / 'stamps.sqlite3'


def trees():
    """Sibling worktrees of this repository, excluding the receiver."""
    try:
        listing = subprocess.run(['git', '-C', str(paths.REPO), 'worktree', 'list', '--porcelain'], check=True,
                                 stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, timeout=10).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    here = paths.REPO.resolve()
    found = [Path(line[9:]) for line in listing.splitlines() if line.startswith('worktree ')]
    return [tree for tree in found if tree.is_dir() and tree.resolve() != here]


class Index:
    """@cc [owner:fontanierh,label:correctness] worktree-reuse-index
    The index is only a hint. A sibling result MUST be re-read from its stamp and MUST count
    only after the receiver certifies its own cloned outputs for its own fingerprint. Donor
    trees MUST NOT be modified, linked to or relocated from path-bound compiler state.
    """
    def __init__(self, game):
        self.game = game
        self.connection = None
        self.refreshed = False

    def open(self):
        if self.connection is None:
            path = database()
            path.parent.mkdir(parents=True, exist_ok=True)
            self.connection = sqlite3.connect(path, timeout=5)
            self.connection.execute('CREATE TABLE IF NOT EXISTS stamps (tree TEXT, game TEXT, task TEXT, '
                                    'mtime_ns INTEGER, size INTEGER, fingerprint TEXT, '
                                    'PRIMARY KEY (tree, game, task)) WITHOUT ROWID')
        return self.connection

    def refresh(self, echo=print):
        if self.refreshed:
            return
        self.refreshed = True
        started = time.monotonic()
        db = self.open()
        sources = trees()
        known = {(t, n): (m, s) for t, n, m, s in db.execute(
            'SELECT tree, task, mtime_ns, size FROM stamps WHERE game=?', (self.game,))}
        seen, changed = set(), 0
        for tree in sources:
            folder = tree / 'build' / self.game / 'stamps'
            try:
                entries = list(os.scandir(folder))
            except OSError:
                continue
            for entry in entries:
                if not entry.name.endswith('.json') or not entry.is_file(follow_symlinks=False):
                    continue
                task = entry.name[:-5]
                info = entry.stat(follow_symlinks=False)
                seen.add((str(tree), task))
                if known.get((str(tree), task)) == (info.st_mtime_ns, info.st_size):
                    continue
                try:
                    value = read_json(Path(entry.path))
                    fingerprint = value.get('fingerprint') if isinstance(value, dict) and not value.get('touched') else None
                except (OSError, ValueError, CheckpointError):
                    fingerprint = None
                db.execute('INSERT OR REPLACE INTO stamps VALUES (?, ?, ?, ?, ?, ?)',
                           (str(tree), self.game, task, info.st_mtime_ns, info.st_size, fingerprint))
                changed += 1
        stale = [key for key in known if key not in seen]
        db.executemany('DELETE FROM stamps WHERE tree=? AND game=? AND task=?', [(t, self.game, n) for t, n in stale])
        db.commit()
        echo(f'worktree reuse index: {len(sources)} worktrees, {changed} stamps updated, '
             f'{time.monotonic() - started:.1f} s')

    def lookup(self, task, fingerprint):
        db = self.open()
        return [Path(t) for (t,) in db.execute('SELECT tree FROM stamps WHERE game=? AND task=? AND fingerprint=?',
                                                (self.game, task, fingerprint))]

    def checkpoints(self, ctx, steps_names=None):
        """(task, fingerprint) -> compatible checkpoint keys, newest first, from cached summaries."""
        if not hasattr(self, 'catalogue'):
            from .checkpoint_store import Store, context, identity
            self.store = Store(self.game)
            expected, self.catalogue = identity(context(ctx)), {}
            for key, summary in self.store.summaries():
                if summary['context'] == expected and not summary['workspace_only']:
                    for task, fingerprint in summary['stamps'].items():
                        self.catalogue.setdefault((task, fingerprint), []).append(key)
        return self.catalogue

    def close(self):
        if self.connection is not None:
            self.connection.close()
            self.connection = None


def donor_root(ctx, tree, label):
    from .checkpoint_store import roots
    root, path_bound = roots(ctx)[label]
    if path_bound:
        return None  # Compiler intermediates never relocate between checkouts.
    if label == 'generated':
        return tree / 'build' / ctx.game
    try:
        return tree / root.relative_to(paths.REPO)
    except ValueError:
        return None


def pairs(ctx, step, tree):
    """(receiver, donor) output roots, or None when any declared output cannot be sourced."""
    from .checkpoint_actions import declared, label
    result = []
    for path in declared(ctx, step):
        name = label(ctx, Path(path))
        root_label, _, tail = name.partition('/')
        base = donor_root(ctx, tree, root_label)
        if base is None:
            return None
        donor = base / tail if tail else base
        if donor.is_symlink() or not donor.exists():
            return None
        result.append((str(path), str(donor)))
    return result or None


def restore(ctx, step, fingerprint, index, *, echo=print):
    """Clone a sibling worktree's certified outputs for this exact fingerprint; returns (tree, stamp)."""
    from .checkpoint_actions import certified, compile_present
    from .build import outputs_present
    from .build_cache import atomic_json
    index.refresh(echo)
    for tree in index.lookup(step.name, fingerprint):
        try:
            stamp = read_json(tree / 'build' / ctx.game / 'stamps' / (step.name + '.json'))
            if not isinstance(stamp, dict) or stamp.get('fingerprint') != fingerprint or stamp.get('touched'):
                continue
            selected = pairs(ctx, step, tree)
            if selected is None:
                continue
            started = time.monotonic()
            request = ctx.out / '.state/clone-requests' / (step.name + '.json')
            atomic_json(request, dict(task=step.name, tree=str(tree), pairs=selected))
            from .build_checkpoints import _guard
            _guard(ctx, 'clone-step', step.name)
            if outputs_present(step) and compile_present(ctx, step) and certified(ctx, step, fingerprint, stamp):
                echo(f'{step.name}: restored from worktree {tree.name} ({len(selected)} outputs, '
                     f'{time.monotonic() - started:.1f} s)')
                return tree, stamp
            echo(f'{step.name}: worktree {tree.name} outputs did not certify; building normally')
        except (OSError, ValueError, KeyError, TypeError, CheckpointError) as error:
            echo(f'{step.name}: worktree {tree.name} reuse skipped ({error})')
    return None


def restore_checkpoint(ctx, step, fingerprint, index, *, echo=print):
    """Clone one task's outputs from any retained checkpoint certifying this exact fingerprint."""
    from .checkpoint_actions import certified, compile_present, declared, label
    from .build import outputs_present
    from .build_cache import atomic_json
    for key in index.checkpoints(ctx).get((step.name, fingerprint), []):
        try:
            started = time.monotonic()
            prefixes = [label(ctx, Path(p)) for p in declared(ctx, step)]
            request = ctx.out / '.state/clone-requests' / (step.name + '.json')
            atomic_json(request, dict(task=step.name, checkpoint=key, outputs=prefixes))
            from .build_checkpoints import _guard
            _guard(ctx, 'clone-step', step.name)
            saved = index.store.load(key)
            stamp = {**saved['stamps'], **saved.get('incremental_stamps', {})}.get(step.name)
            if (stamp and stamp.get('fingerprint') == fingerprint and outputs_present(step)
                    and compile_present(ctx, step) and certified(ctx, step, fingerprint, stamp)):
                echo(f'{step.name}: restored from checkpoint {key[:12]} ({time.monotonic() - started:.1f} s)')
                return key, stamp
            echo(f'{step.name}: checkpoint {key[:12]} outputs did not certify; building normally')
        except (OSError, ValueError, KeyError, TypeError, CheckpointError) as error:
            echo(f'{step.name}: checkpoint {key[:12]} reuse skipped ({error})')
    return None


def swap(destination, staged):
    aside = destination.parent / ('.checkpoint-old-' + os.urandom(8).hex())
    if os.path.lexists(destination):
        destination.rename(aside)
    staged.rename(destination)
    if os.path.lexists(aside):
        if aside.is_dir() and not aside.is_symlink():
            import shutil
            shutil.rmtree(aside)
        else:
            aside.unlink()


def checkpoint_clone(ctx, request):
    """Rebuild each declared output root from digest-named blobs, then swap it into place."""
    from .build_cache import copy_file
    from .checkpoint_store import Store, roots, safe_destination as safe
    store = Store(ctx.game)
    manifest = store.load(request['checkpoint'])
    allowed = roots(ctx)
    same_path = manifest['checkout'] == __import__('atelier.checkpoint_store', fromlist=['identity']).identity(
        str(paths.REPO.resolve()))
    for prefix in request['outputs']:
        label, _, tail = prefix.partition('/')
        if label not in allowed or allowed[label][1] and not same_path:
            raise CheckpointError('Checkpoint output root is not locally owned')
        root = allowed[label][0]
        destination = safe(root, tail) if tail else root
        members = {m: e for m, e in manifest['files'].items() if m == prefix or m.startswith(prefix + '/')}
        if not members:
            raise CheckpointError('Checkpoint holds no outputs for ' + prefix)
        destination.parent.mkdir(parents=True, exist_ok=True)
        staged = destination.parent / ('.checkpoint-' + os.urandom(8).hex())
        for member, entry in members.items():
            path = staged if member == prefix else safe(staged, member[len(prefix) + 1:])
            if entry['kind'] == 'directory':
                path.mkdir(parents=True, exist_ok=True)
                continue
            path.parent.mkdir(parents=True, exist_ok=True)
            if entry['kind'] == 'link':
                if entry['target'].startswith('member:'):
                    target_label, _, target_name = entry['target'][7:].partition('/')
                    target = safe(allowed[target_label][0], target_name)
                else:
                    target = ctx.unreal_root / entry['target'][7:]
                path.symlink_to(os.path.relpath(target, (destination / path.relative_to(staged)).parent
                                                if member != prefix else destination.parent))
                continue
            blob = store.blob(entry['sha256'])
            if not blob.is_file() or blob.stat().st_size != entry['size']:
                raise CheckpointError('Checkpoint blob is missing or corrupt')
            copy_file(blob, path)
            os.chmod(path, entry['mode'])
            os.utime(path, ns=(entry['mtime_ns'], entry['mtime_ns']))
        swap(destination, staged)
    return len(request['outputs'])


def clone_worker(ctx, task):
    """Guarded child: replace each receiver output root with an independent clone of the donor's."""
    from .build_cache import clone_function, copy_file
    from .checkpoint_store import roots, tracked_paths
    request = read_json(ctx.out / '.state/clone-requests' / (task + '.json'))
    if request.get('task') != task:
        raise CheckpointError('Clone request names another task')
    if 'checkpoint' in request:
        return checkpoint_clone(ctx, request)
    tree = Path(request['tree'])
    if request.get('task') != task or tree.resolve() not in {t.resolve() for t in trees()}:
        raise CheckpointError('Clone request names an unknown worktree')
    allowed = roots(ctx)
    source = tracked_paths()
    for receiver, donor in request['pairs']:
        receiver, donor = Path(receiver), Path(donor)
        choices = [(label, root) for label, (root, bound) in allowed.items()
                   if not bound and (receiver == root or root in receiver.parents)]
        if not choices or receiver in source:
            raise CheckpointError('Clone destination is not a generated output')
        label, root = max(choices, key=lambda item: len(item[1].parts))
        base = donor_root(ctx, tree, label)
        tail = receiver.relative_to(root)
        if base is None or donor != base / tail or donor.is_symlink():
            raise CheckpointError('Clone source does not mirror the receiver output')
        destination = safe_destination(root, tail.as_posix()) if tail.parts else receiver
        destination.parent.mkdir(parents=True, exist_ok=True)
        staged = destination.parent / ('.checkpoint-' + os.urandom(8).hex())
        if clone_function()(os.fsencode(donor), os.fsencode(staged), 1) != 0:  # CLONE_NOFOLLOW
            if donor.is_dir():
                import shutil
                shutil.copytree(donor, staged, symlinks=True, copy_function=lambda a, b: copy_file(Path(a), Path(b)))
            else:
                copy_file(donor, staged)
        for base_dir, directories, files in os.walk(staged):
            for name in (*directories, *files):
                path = Path(base_dir) / name
                if path.is_symlink():
                    target = (path.parent / os.readlink(path)).resolve()
                    if not any(target == r or r in target.parents for r, _ in allowed.values()) and not (
                            getattr(ctx, 'unreal_root', None) and ctx.unreal_root in target.parents):
                        import shutil
                        shutil.rmtree(staged, ignore_errors=True)
                        raise CheckpointError('Cloned output links outside the receiver')
        swap(destination, staged)
    return len(request['pairs'])
