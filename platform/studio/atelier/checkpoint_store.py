"""Immutable build checkpoints. Source files and live engine/Zen directories are never copied.

This is a native workspace snapshot protocol, separate from the portable product cache.
Checkout-local compiler state is retained as a seed only at its original path; no PCH relocation
or compiler-action-cache claim is made. Certificates are recomputed by the receiving recipe.
"""
from contextlib import contextmanager
import fcntl
import json
import os
from pathlib import Path
import shutil
import stat
import tempfile
import time

from . import build_products, paths
from .build_cache import atomic_json, copy_file
from .native_protocol import (SCHEMA, MAX_MANIFEST, MAX_FILES, MAX_BYTES, HEX, IGNORED, CheckpointError,
                              canonical, identity, read_json, relative, context, excluded, safe_destination, validate)
from .build_hashes import HashIndex, signature

JOURNAL = '.checkpoint-in-progress.json'


def roots(ctx):
    """The allowlist is derived locally, never from a downloaded manifest."""
    result = {'generated': (ctx.out, False)}
    if getattr(ctx, 'uproject', None):
        project = ctx.uproject.parent
        result.update(content=(project / 'Content', False), binaries=(project / 'Binaries', False),
                      intermediate=(project / 'Intermediate', True), cooked=(project / 'Saved/Cooked', False),
                      zen=(ctx.out / '.state/checkpoint-zen', False))
        for base in (paths.ENGINE_PLUGINS, project / 'Plugins'):
            for descriptor in sorted(base.rglob('*.uplugin')) if base.exists() else ():
                plugin = descriptor.parent
                if any(p in ('Intermediate', 'Binaries') for p in plugin.relative_to(base).parts):
                    continue
                name = identity(str(plugin.relative_to(paths.REPO)))[:24]
                result['plugin-' + name + '-binaries'] = (plugin / 'Binaries', False)
                result['plugin-' + name + '-intermediate'] = (plugin / 'Intermediate', True)
    return result


def members(root):
    if root.is_symlink():
        raise CheckpointError('Checkpoint roots must not be symlinks')
    if not root.exists():
        return
    for base, directories, files in os.walk(root, followlinks=False):
        base = Path(base)
        directories[:] = sorted(d for d in directories if not excluded((base / d).relative_to(root)))
        for name in sorted([*files, *(d for d in directories if (base / d).is_symlink())]):
            path = base / name
            if not excluded(path.relative_to(root)):
                yield path


class Store:
    def __init__(self, game, directory=None):
        self.game = game
        self.directory = Path(directory) if directory else paths.cache_dir('checkpoints', 'v1', game)
        self.blobs = self.directory / 'blobs'
        self.manifests = self.directory / 'manifests'
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(self.directory, 0o700)

    @contextmanager
    def locked(self):
        with (self.directory / 'store.lock').open('a+b') as handle:
            fcntl.flock(handle, fcntl.LOCK_EX)
            yield

    def blob(self, digest):
        if not isinstance(digest, str) or not HEX.fullmatch(digest):
            raise CheckpointError('Invalid checkpoint content digest')
        return self.blobs / digest

    def put(self, path, digest):
        destination = self.blob(digest)
        if destination.is_symlink():
            raise CheckpointError('Linked checkpoint blob')
        if destination.exists():
            if build_products.file_digest(destination) != digest:
                raise CheckpointError('Existing checkpoint blob is corrupt; no results were restored')
            return
        self.blobs.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=self.directory) as temporary:
            copied = Path(temporary) / 'blob'
            copy_file(path, copied)
            if build_products.file_digest(copied) != digest:
                raise CheckpointError('Checkpoint output changed while being copied')
            os.chmod(copied, 0o600)
            copied.replace(destination)

    def save(self, manifest):
        validate(manifest, self.game)
        key = identity(manifest)
        self.manifests.mkdir(parents=True, exist_ok=True)
        atomic_json(self.manifests / (key + '.json'), manifest)
        return key

    def load(self, key):
        if not HEX.fullmatch(key):
            raise CheckpointError('Invalid checkpoint identity')
        manifest = read_json(self.manifests / (key + '.json'))
        validate(manifest, self.game)
        if identity(manifest) != key:
            raise CheckpointError('Checkpoint manifest digest differs')
        return manifest

    def latest(self):
        candidates = sorted(self.manifests.glob('*.json'), key=lambda p: p.stat().st_mtime_ns, reverse=True)
        return [(p.stem, self.load(p.stem)) for p in candidates]


def certificates(ctx, steps, *, include_incremental=False):
    from .build import fingerprint, order, outputs_present, result
    from .build_plan import read_stamp
    from .checkpoint_actions import compile_present, certified, local_incremental
    done, records = {}, {}
    with HashIndex() as index:
        for step in order(steps, [s.name for s in steps]):
            stamp = read_stamp(ctx.stamps / (step.name + '.json'))
            try:
                current = fingerprint(step, done, index=index, tool_cache={})
                products = build_products.records(step, hasher=index.digest)
                good = (stamp.get('fingerprint') == current and not stamp.get('touched')
                        and outputs_present(step) and compile_present(ctx, step) and (certified(ctx, step, current, stamp) or (include_incremental and local_incremental(ctx, step, current, stamp))) and (not step.products or stamp.get('products') == products)
                        and all(need in records for need in step.needs))
            except (OSError, ValueError, SyntaxError):
                good = False
            if good:
                records[step.name] = stamp
                done[step.name] = result(step, current, stamp)
                build_products.feed_results(done, products)
    return records



def historical_candidates(ctx, steps):
    """Unmodified old task evidence; never a current fingerprint or success certificate."""
    result = {}
    for step in steps:
        try:
            stamp = read_json(safe_destination(ctx.stamps, step.name + '.json'))
            if (isinstance(stamp, dict) and not stamp.get('touched')
                    and isinstance(stamp.get('fingerprint'), str) and HEX.fullmatch(stamp['fingerprint'])
                    and isinstance(stamp.get('input_state'), dict)
                    and isinstance(stamp['input_state'].get('inputs'), dict)):
                result[step.name] = stamp
        except (OSError, ValueError, TypeError, CheckpointError):
            pass
    return result


def capture(ctx, steps, store, *, echo=print, allow_seed=False, candidate_only=False, scratch=None):
    """@cc [owner:fontanierh,label:correctness] immutable-checkpoint-capture
    Historical candidate evidence MUST retain original task input identities and remain
    separate from current certificates. It MUST be checked again after the copy.
    Saved certificates MUST retain their produced tool key and output inventory proof, matching
    the producer's current declared inputs and complete named
    outputs. Touched/failed/stale certificates MUST NOT publish. Source and output changes during
    capture MUST refuse publication. HEAD equality with a future receiver MUST NOT be required.
    Candidate-only capture MUST write hash scratch outside the producer and publish only a
    compatibility catalogue, never a full workspace donor or produced action certificate.
    """
    history = historical_candidates(ctx, steps)
    before = certificates(ctx, steps, include_incremental=True)
    if candidate_only and (scratch is None or Path(scratch).resolve().is_relative_to(paths.REPO.resolve())):
        raise CheckpointError('Candidate-only capture requires scratch outside the producer')
    if not before and not allow_seed:
        raise CheckpointError('No current successful build results to checkpoint')
    from . import checkpoint_actions
    from .build import order, result
    checkpoint_actions.validate_ownership(ctx, steps)
    done = {}
    for step in order(steps, [s.name for s in steps]):
        if step.name in before:
            record = before[step.name]
            if not candidate_only and checkpoint_actions.certified(ctx, step, record['fingerprint'], record):
                checkpoint_actions.publish(ctx, step, record['fingerprint'], record, store=store, done=done)
            done[step.name] = result(step, record['fingerprint'], record)
            build_products.feed_results(done, record.get('products', {}))
    actions = {}
    for action_path in sorted((store.directory / 'actions').glob('*.json')):
        if not action_path.with_suffix('.conflict').exists():
            actions[action_path.stem] = checkpoint_actions.load(store, action_path.stem)
    allowed, files, observations = roots(ctx), {}, []
    if candidate_only:
        allowed = {name: value for name, value in allowed.items() if name in ('generated', 'content')}
    source_paths = tracked_paths()
    with store.locked(), HashIndex(scratch if scratch is not None else ctx.out / '.state/checkpoint-hashes.sqlite3') as hashes:
        started = spoken = time.monotonic()
        for label, (root, _) in allowed.items():
            for path in members(root):
                if path in source_paths:
                    continue
                info = path.lstat()
                member = label + '/' + path.relative_to(root).as_posix()
                entry = dict(mode=stat.S_IMODE(info.st_mode), mtime_ns=info.st_mtime_ns)
                if stat.S_ISLNK(info.st_mode):
                    target = path.resolve(strict=True)
                    choices = [(name, base) for name, (base, _) in allowed.items() if target.is_relative_to(base)]
                    if choices:
                        name, base = max(choices, key=lambda item: len(item[1].parts))
                        entry.update(kind='link', target='member:' + name + '/' + target.relative_to(base).as_posix())
                    elif getattr(ctx, 'unreal_root', None) and target.is_relative_to(ctx.unreal_root):
                        entry.update(kind='link', target='engine:' + target.relative_to(ctx.unreal_root).as_posix())
                    else:
                        raise CheckpointError('Checkpoint link escapes generated outputs and installed engine')
                elif stat.S_ISREG(info.st_mode):
                    digest = hashes.digest(path)
                    store.put(path, digest)
                    entry.update(kind='file', size=info.st_size, sha256=digest)
                else:
                    raise CheckpointError('Special checkpoint output')
                files[member] = entry
                observations.append((path, signature(info)))
                if time.monotonic() - spoken >= 25:
                    echo(f'checkpoint: {len(files)} files saved, {time.monotonic() - started:.0f}s elapsed')
                    spoken = time.monotonic()
        names = {label + '/' + p.relative_to(root).as_posix()
                 for label, (root, _) in allowed.items() for p in members(root) if p not in source_paths}
        if (names != set(files) or any(signature(p.lstat()) != info for p, info in observations)
                or certificates(ctx, steps, include_incremental=True) != before
                or (historical_candidates(ctx, steps) != history)):
            raise CheckpointError('Build changed during checkpoint capture; nothing published')
        current_proof = {s.name: before[s.name] for s in steps if not candidate_only and s.name in before
                         and checkpoint_actions.certified(ctx, s, before[s.name]['fingerprint'], before[s.name])}
        incremental = {name: value for name, value in before.items() if name not in current_proof}
        manifest = dict(schema=SCHEMA, game=ctx.game, context=context(ctx),
                        checkout=identity(str(paths.REPO.resolve())), files=files, stamps=current_proof, incremental_stamps=incremental,
                        historical_stamps={name: stamp for name, stamp in history.items() if name not in before},
                        steps=sorted(s.name for s in steps), actions=actions)
        if candidate_only:
            manifest['candidate_only'] = True
            manifest['actions'] = {}
            key = identity(manifest)
            atomic_json(store.directory / 'candidate-sources' / (key + '.json'), manifest)
        else:
            key = store.save(manifest)
    echo(f'checkpoint saved: {key[:12]}, {len(files)} files, {len(before)} certified tasks')
    return key


def cold(ctx):
    """Whole-workspace hydration never merges with a receiver's existing generated work."""
    for label, (root, _) in roots(ctx).items():
        if any(members(root)):
            return False
    return True


def restore(ctx, steps, store, key, *, echo=print):
    """@cc [owner:fontanierh,label:correctness] checkpoint-restoration-certificates
    Restoration MUST preserve source files, use independent verified copies and stay within
    locally allowed generated roots. Only certificates matching the receiving recipe's actual
    inputs MAY survive. A durable launch barrier MUST precede mutation and survive any failure.
    Existing generated work MUST NOT be overwritten. Compiler intermediates MUST NOT relocate.
    """
    from .build_snapshot import require_complete
    manifest = store.load(key)
    if manifest['context'] != context(ctx):
        raise CheckpointError('Checkpoint engine/platform identity differs')
    allowed = roots(ctx)
    saved_stamps = {**manifest['stamps'], **manifest.get('incremental_stamps', {})}
    if not set(manifest.get('steps', ())) <= {s.name for s in steps}:
        raise CheckpointError('Checkpoint task ownership changed; a new baseline is required')
    journal = ctx.out / JOURNAL
    resume = dict(schema=SCHEMA, key=key, game=ctx.game)
    existing = read_json(journal) if journal.exists() else None
    if existing is not None and existing != resume:
        raise CheckpointError('A different checkpoint restoration is incomplete')
    require_complete(ctx.out, game=ctx.game, checkpoint_resume=resume if existing else None)
    if existing is None and not cold(ctx):
        raise CheckpointError('Checkpoint restoration preserves existing generated work; receiver is not empty')
    selected = {}
    source_paths = tracked_paths()
    same_path = manifest['checkout'] == identity(str(paths.REPO.resolve()))
    for member, entry in manifest['files'].items():
        label, _, name = member.partition('/')
        if label not in allowed:
            raise CheckpointError('Checkpoint root is not owned by this project')
        root, path_bound = allowed[label]
        if path_bound and not same_path:
            continue
        destination = safe_destination(root, name)
        if destination in source_paths:
            raise CheckpointError('Checkpoint cannot replace tracked source')
        if entry['kind'] == 'file':
            blob = store.blob(entry['sha256'])
            if (blob.is_symlink() or blob.stat().st_size != entry['size']
                    or build_products.file_digest(blob) != entry['sha256']):
                raise CheckpointError('Checkpoint blob is missing or corrupt')
        selected[member] = (destination, entry)
    # Verify link targets before changing anything; never create a link into a skipped root.
    for destination, entry in selected.values():
        if entry['kind'] == 'link' and entry['target'].startswith('member:'):
            if (entry['target'][7:] not in selected
                    and not any(m.startswith(entry['target'][7:] + '/') for m in selected)):
                raise CheckpointError('Checkpoint link target is unavailable')
    ctx.stamps.mkdir(parents=True, exist_ok=True)
    atomic_json(journal, resume)
    for name in saved_stamps:
        (ctx.stamps / (name + '.json')).unlink(missing_ok=True)
    spoken = time.monotonic()
    for count, (destination, entry) in enumerate(selected.values(), 1):
        destination.parent.mkdir(parents=True, exist_ok=True)
        if entry['kind'] == 'file':
            if destination.exists() or destination.is_symlink():
                if (destination.is_symlink() or not destination.is_file()
                        or build_products.file_digest(destination) != entry['sha256']):
                    raise CheckpointError('Receiver output changed during checkpoint restoration; preserving it')
            else:
                with tempfile.TemporaryDirectory(prefix='.checkpoint-', dir=destination.parent) as temporary:
                    staged = Path(temporary) / 'file'
                    copy_file(store.blob(entry['sha256']), staged)
                    if build_products.file_digest(staged) != entry['sha256']:
                        raise CheckpointError('Staged checkpoint bytes differ')
                    os.chmod(staged, entry['mode'])
                    os.utime(staged, ns=(entry['mtime_ns'], entry['mtime_ns']))
                    staged.replace(destination)
        elif entry['kind'] == 'directory':
            if destination.is_symlink() or destination.exists() and not destination.is_dir():
                raise CheckpointError('Receiver directory destination is occupied')
            destination.mkdir(exist_ok=True)
        else:
            if entry['target'].startswith('member:'):
                label, _, name = entry['target'][7:].partition('/')
                target = safe_destination(allowed[label][0], name)
            else:
                target = ctx.unreal_root / entry['target'][7:]
            link = os.path.relpath(target, destination.parent)
            if destination.is_symlink():
                if os.readlink(destination) != link:
                    raise CheckpointError('Receiver link changed during checkpoint restoration')
            elif destination.exists():
                raise CheckpointError('Receiver link destination is occupied')
            else:
                destination.symlink_to(link)
        if time.monotonic() - spoken >= 25:
            echo(f'checkpoint restore: {count}/{len(selected)} files copied')
            spoken = time.monotonic()
    for destination, entry in selected.values():
        if entry['kind'] == 'file' and build_products.file_digest(destination) != entry['sha256']:
            raise CheckpointError('Restored checkpoint bytes differ; launch barrier retained')
    # Imported source paths remain provenance. Runtime packages retain their logical /Game paths.
    # The installed engine discovers its registry normally; producer registry caches are not copied.
    for name, stamp in saved_stamps.items():
        atomic_json(ctx.stamps / (name + '.json'), stamp)
    from .build_checkpoints import incremental_environment
    incremental_environment(ctx)
    current = certificates(ctx, steps, include_incremental=True)
    for name in saved_stamps:
        path = ctx.stamps / (name + '.json')
        if name not in current:
            path.unlink(missing_ok=True)
    from .build_checkpoints import estimate
    atomic_json(ctx.out / '.state/checkpoint.json', dict(key=key, restored=sorted(current),
                estimates={name: estimate(stamp) for name, stamp in saved_stamps.items()}))
    # Publication of current certificates happens only after the outer guard closes in the caller.
    for name in current:
        (ctx.stamps / (name + '.json')).unlink(missing_ok=True)
    return current


def tracked_paths():
    """Tracked source can never be acquired by a generated-output transaction."""
    import subprocess
    if not (paths.REPO / '.git').exists():
        return set()
    result = subprocess.run(['git', '-C', str(paths.REPO), 'ls-files', '-z'], check=True,
                            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=15)
    return {paths.REPO / os.fsdecode(name) for name in result.stdout.split(b'\0') if name}
