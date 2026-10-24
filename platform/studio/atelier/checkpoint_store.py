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
                              ManifestTooLarge, canonical, identity, read_json, relative, context, excluded,
                              safe_destination, validate)
from .build_hashes import HashIndex, signature

JOURNAL = '.checkpoint-in-progress.json'


def roots(ctx):
    """The allowlist is derived locally, never from a downloaded manifest."""
    result = {'generated': (ctx.out, False)}
    if getattr(ctx, 'uproject', None):
        project = ctx.uproject.parent
        result.update(content=(project / 'Content', False), binaries=(project / 'Binaries', False),
                      samples=(project / 'Samples', False),
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

    def put(self, path, digest, *, proved=None):
        """Store bytes under their digest. proved is the source's stat signature when digest came
        from the build's hash index for exactly that signature: an unchanged source across the
        APFS clone proves the blob without rereading it."""
        destination = self.blob(digest)
        if destination.is_symlink():
            raise CheckpointError('Linked checkpoint blob')
        if destination.exists():
            if (destination.stat().st_size != path.stat().st_size if proved is not None
                    else build_products.file_digest(destination) != digest):
                raise CheckpointError('Existing checkpoint blob is corrupt; no results were restored')
            return
        self.blobs.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=self.directory) as temporary:
            copied = Path(temporary) / 'blob'
            copy_file(path, copied)
            if proved is not None and signature(path.stat()) == proved and copied.stat().st_size == path.stat().st_size:
                pass
            elif build_products.file_digest(copied) != digest:
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


RESTORED_HASHES = '.state/file-hashes.sqlite3'  # The build's own hash index.


def certificates(ctx, steps, *, include_incremental=False, hashes=None):
    from .build import fingerprint, order, outputs_present, result
    from .build_plan import read_stamp
    from .checkpoint_actions import compile_present, certified, local_incremental
    done, records, tools = {}, {}, {}  # One tool enumeration per pass, as in the build loop.
    with HashIndex(hashes) as index, hashing(ctx, index.digest):
        for step in order(steps, [s.name for s in steps]):
            if getattr(step, 'controller', None) is not None:
                continue  # Controller identities never become legacy action certificates.
            stamp = read_stamp(ctx.stamps / (step.name + '.json'))
            try:
                current = fingerprint(step, done, index=index, tool_cache=tools)
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


@contextmanager
def hashing(ctx, digest):
    previous = getattr(ctx, 'checkpoint_hasher', None)
    ctx.checkpoint_hasher = digest
    try:
        yield
    finally:
        ctx.checkpoint_hasher = previous


def unchanged(path, entry):
    """Metadata proof for a clone this restoration made from a verified content-addressed blob."""
    try:
        info = path.lstat()
    except OSError:
        return False
    return (stat.S_ISREG(info.st_mode) and info.st_size == entry['size']
            and stat.S_IMODE(info.st_mode) == entry['mode'] and info.st_mtime_ns == entry['mtime_ns'])


def historical_candidates(ctx, steps):
    """Unmodified old task evidence; never a current fingerprint or success certificate."""
    result = {}
    for step in steps:
        if getattr(step, 'controller', None) is not None:
            continue
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
    from .build_v2.controller_claims import for_context
    controller_claims = for_context(ctx)
    actions = {}
    for action_path in sorted((store.directory / 'actions').glob('*.json')):
        if not action_path.with_suffix('.conflict').exists():
            action = checkpoint_actions.load(store, action_path.stem)
            if controller_claims.files and action is not None:
                try:
                    checkpoint_actions.reject_controller_overlap(ctx, [checkpoint_actions.destination(ctx, name)
                        for name in [*[root['path'] for root in action['roots']], *action['files']]])
                except CheckpointError:
                    continue  # Reject a complete historical action, never trim its certificate.
            actions[action_path.stem] = action
    allowed, files, observations = roots(ctx), {}, []
    if candidate_only:
        allowed = {name: value for name, value in allowed.items() if name in ('generated', 'content')}
    source_paths = tracked_paths()
    with store.locked(), HashIndex(scratch if scratch is not None else ctx.out / '.state/checkpoint-hashes.sqlite3') as hashes:
        started = spoken = time.monotonic()
        for label, (root, _) in allowed.items():
            for path in members(root):
                if path in source_paths or controller_claims.excludes(path):
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
                 for label, (root, _) in allowed.items() for p in members(root)
                 if p not in source_paths and not controller_claims.excludes(p)}
        if (names != set(files) or any(signature(p.lstat()) != info for p, info in observations)
                or certificates(ctx, steps, include_incremental=True) != before
                or (historical_candidates(ctx, steps) != history)):
            raise CheckpointError('Build changed during checkpoint capture; nothing published')
        current_proof = {s.name: before[s.name] for s in steps if not candidate_only and s.name in before
                         and checkpoint_actions.certified(ctx, s, before[s.name]['fingerprint'], before[s.name])}
        # A candidate-only catalogue is never a workspace donor; native validation decides its use.
        inventories = {s.name: before[s.name]['output_inventory'] for s in steps if s.name in before
                       and not checkpoint_actions.verifiable(ctx, s) and checkpoint_actions.inventory_verified(ctx, s, before[s.name])}
        unverified = set() if candidate_only else {s.name for s in steps if not checkpoint_actions.verifiable(ctx, s) and s.name not in inventories}
        incremental = {name: value for name, value in before.items() if name not in current_proof and name not in unverified}
        if not candidate_only:
            files = checkpoint_actions.publishable(files, checkpoint_actions.ownership(ctx, steps, inventories))
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


def declared(ctx, steps):
    """Generated paths some receiving step declares; other donor files are never hydrated."""
    base = str(ctx.out.absolute()) + '/'
    result = set()
    for step in steps:
        result.add('native-imports/' + step.name)  # Mesh reuse receipts, validated by their owner.
        for path in (*getattr(step, 'outputs', ()), *(q for product in getattr(step, 'products', ()) for q in product.paths)):
            text = str(Path(path).absolute())
            if text.startswith(base):
                result.add(text[len(base):])
    return result


def tracked_paths():
    """Tracked source can never be acquired by a generated-output transaction."""
    import subprocess
    if not (paths.REPO / '.git').exists():
        return set()
    result = subprocess.run(['git', '-C', str(paths.REPO), 'ls-files', '-z'], check=True,
                            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=15)
    return {paths.REPO / os.fsdecode(name) for name in result.stdout.split(b'\0') if name}
