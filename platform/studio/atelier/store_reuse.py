"""Certified task results from the shared local checkpoint store, found by fingerprint.

Only immutable, content-addressed store entries are sources; no other checkout is read.
A result counts only when the receiving build certifies the restored outputs itself.
"""
import os
from pathlib import Path
import time

from . import paths
from .native_protocol import CheckpointError, read_json, safe_destination


class Catalogue:
    """@cc [owner:fontanierh,label:correctness] store-reuse-catalogue
    The catalogue is only a hint built from cached immutable manifest summaries. A result
    MUST count only after the receiver certifies its restored outputs for its own fingerprint.
    """
    def __init__(self, game):
        self.game = game

    def checkpoints(self, ctx):
        """(task, fingerprint) -> compatible checkpoint keys, newest first."""
        if not hasattr(self, 'catalogue'):
            from .checkpoint_store import Store, context, identity
            self.store = Store(self.game)
            expected, self.catalogue = identity(context(ctx)), {}
            for key, summary in self.store.summaries():
                if summary['context'] == expected and not summary['workspace_only']:
                    for task, fingerprint in summary['stamps'].items():
                        self.catalogue.setdefault((task, fingerprint), []).append(key)
        return self.catalogue


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
    from .checkpoint_store import identity
    same_path = manifest['checkout'] == identity(str(paths.REPO.resolve()))
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
    """Guarded child: rebuild one task's declared outputs from a store checkpoint."""
    request = read_json(ctx.out / '.state/clone-requests' / (task + '.json'))
    if request.get('task') != task or 'checkpoint' not in request:
        raise CheckpointError('Clone request names another task or source')
    return checkpoint_clone(ctx, request)
