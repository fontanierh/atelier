"""Build-time artifact publication; merge retention reads only completed metadata."""
from contextlib import contextmanager
import fcntl
import os
import stat
import time
from pathlib import Path

from . import paths
from .atomic_files import atomic_json
from .checkpoint_store import (CheckpointError, Store, context, identity,
                               read_json, roots, safe_destination, validate)
from .build_hashes import digest_file, signature


def folder(out):
    path = safe_destination(Path(out).resolve(), '.state/retention')
    if path.is_symlink() or path.exists() and not path.is_dir():
        raise CheckpointError('Retention metadata root must be a real directory')
    return path


@contextmanager
def writer(out):
    directory = folder(out)
    directory.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(directory / 'writer.lock', os.O_CREAT | os.O_RDWR | getattr(os, 'O_NOFOLLOW', 0), 0o600)
    with os.fdopen(descriptor, 'a+b') as lock:
        if not stat.S_ISREG(os.fstat(lock.fileno()).st_mode):
            raise CheckpointError('Retention lock must be regular')
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise CheckpointError('Producer is building or retaining artifacts; retry at its stopped boundary') from None
        yield


def _workspace(ctx, store):
    """Publish workspace deltas during the build, reusing previously verified signatures."""
    from . import checkpoint_actions as actions
    from .checkpoint_store import tracked_paths
    allowed = roots(ctx)
    workspace_id = identity([ctx.game, str(paths.REPO.resolve()), str(ctx.out)])
    pointer = safe_destination(store.directory, 'workspaces/' + workspace_id + '.json')
    previous = {}
    if pointer.is_file():
        saved = read_json(pointer)
        previous = saved['workspace']
        validate(previous, ctx.game)
        if saved.get('key') != identity(previous) or previous.get('checkout') != identity(str(paths.REPO.resolve())):
            raise CheckpointError('Published workspace identity differs')
    old_files, old_checks = previous.get('files', {}), previous.get('local_observations', {})
    old_blobs = previous.get('blob_observations', {})
    index = getattr(ctx, 'build_hash_index', None)
    hashed = index.digest if index is not None else digest_file  # Reuse digests the build computed.
    source_files = tracked_paths()
    files, checks, blobs = {}, {}, {}
    copied, reused, spoken = 0, 0, time.monotonic()
    known, known_checks = {}, {}
    for value in getattr(ctx, 'retention_artifacts', {}).values():
        known.update(value['files'])
        known_checks.update(value['observations'])
    for label, (root, _) in allowed.items():
        if root.is_symlink():
            raise CheckpointError('Linked workspace root')
        checks[label] = list(signature(root.lstat())) if root.exists() else None
        if not root.exists():
            continue
        from .native_protocol import excluded
        for base, directories, leaves in os.walk(root, followlinks=False):
            base = Path(base)
            directories[:] = sorted(d for d in directories if not excluded((base / d).relative_to(root)))
            names = sorted([*leaves, *directories])
            for name in names:
                path = base / name
                if path in source_files or excluded(path.relative_to(root)):
                    continue
                info = path.lstat()
                member = label + '/' + path.relative_to(root).as_posix()
                observed = list(signature(info)); checks[member] = observed
                if known_checks.get(str(path)) == observed and member in known:
                    entry = known[member]
                    reused += 1
                elif old_checks.get(member) == observed and member in old_files:
                    entry = old_files[member]
                    reused += 1
                    if entry['kind'] == 'file' and old_blobs.get(entry['sha256']) != list(signature(store.blob(entry['sha256']).lstat())):
                        raise CheckpointError('Published CAS blob metadata changed')
                else:
                    entry = dict(mode=stat.S_IMODE(info.st_mode), mtime_ns=info.st_mtime_ns)
                    if stat.S_ISREG(info.st_mode):
                        digest = hashed(path)
                        store.put(path, digest)
                        copied += 1
                        entry.update(kind='file', size=info.st_size, sha256=digest)
                    elif stat.S_ISDIR(info.st_mode):
                        entry.update(kind='directory')
                    elif stat.S_ISLNK(info.st_mode):
                        target = path.resolve(strict=True)
                        choices = [(n, p) for n, (p, _) in allowed.items() if target.is_relative_to(p)]
                        if choices:
                            n, parent = max(choices, key=lambda item: len(item[1].parts))
                            entry.update(kind='link', target='member:' + n + '/' + target.relative_to(parent).as_posix())
                        elif getattr(ctx, 'unreal_root', None) and target.is_relative_to(ctx.unreal_root):
                            entry.update(kind='link', target='engine:' + target.relative_to(ctx.unreal_root).as_posix())
                        else:
                            raise CheckpointError('Workspace link escapes owned outputs and engine')
                    else:
                        raise CheckpointError('Special workspace output')
                files[member] = entry
                if time.monotonic() - spoken >= 25:
                    print(f'Build artifact publication: {len(files)} members, {copied} changed files copied, {reused} reused', flush=True)
                    spoken = time.monotonic()
                if entry['kind'] == 'file':
                    blob = store.blob(entry['sha256'])
                    if blob.is_symlink() or not blob.is_file() or blob.stat().st_size != entry['size']:
                        raise CheckpointError('Published CAS blob is missing')
                    blobs[entry['sha256']] = list(signature(blob.lstat()))
    observations = {}
    for member, expected in checks.items():
        label, _, tail = member.partition('/')
        path = allowed[label][0] / tail if tail else allowed[label][0]
        observations[str(path)] = expected
    actions.check_observations(observations)
    value = dict(schema=1, game=ctx.game, context=context(ctx),
                 checkout=identity(str(paths.REPO.resolve())), files=files, stamps={}, steps=[],
                 workspace_only=True, local_observations=checks, blob_observations=blobs)
    validate(value, ctx.game)
    # One current staging reference per producer, not hundreds of full checkpoint versions.
    # It is a CAS root while the build runs; completed manifests keep the same blobs afterward.
    atomic_json(pointer, dict(key=identity(value), workspace=value))
    return value


def record(ctx, step, stamp, *, store=None):
    """@cc [owner:fontanierh,label:correctness;performance] completed-step-retention-evidence
    Record only successful owning stamps after guarded finalization and ordinary action CAS
    publication. Preserve original action/tool/inventory proof. Compiler intermediates MUST be
    copied at compile completion and remain original-path seeds, never portable action proof.
    """
    from . import checkpoint_actions as actions
    from .build import UnrealCompile, UnrealPackage
    if getattr(ctx, 'checkpoint_settings', None) is None:
        return
    store = store or Store(ctx.game)
    key = stamp.get('checkpoint_key')
    directory = folder(ctx.out) / 'tasks'
    directory.mkdir(parents=True, exist_ok=True)
    target = safe_destination(directory, step.name + '.json')
    old = read_json(target) if target.exists() else {}
    observations = ctx.__dict__.get('retention_observations', {}).get(step.name, {})
    if old.get('stamp') != stamp and any(isinstance(c, UnrealPackage) for c in step.commands):
        project = getattr(ctx, 'uproject', None)
        if project and any((project.parent / 'Saved/Cooked').glob('*/ue.projectstore')):
            # Zen is mutable service state: export it under ordinary guarded ownership
            # at cook completion, never during the later merge retention.
            from .build_checkpoints import _guard
            _guard(ctx, 'export-zen')
    with store.locked():
        # A package-owned result kept local claims no inventory: it binds to no published entry.
        local = not stamp.get('checkpoint_inventory') and actions.packaged(ctx, step)
        value = actions.load(store, key) if key is not None and not local else None
        # A stamp that claims a certificate must have it published; a keyless (local-only) stamp is legacy state.
        if key is not None and not local and actions.key(ctx, step, stamp['fingerprint']) is not None and value is None:
            raise CheckpointError('Completed task lacks its published artifact certificate')
        if value is not None:
            if value['task'] != step.name or value['fingerprint'] != stamp['fingerprint'] or value['stamp'].get('checkpoint_inventory') != stamp.get('checkpoint_inventory'):
                raise CheckpointError('Completed task artifact binding differs')
            if not observations:
                raise CheckpointError('Completed task lacks verified file metadata')
            actions.check_observations(observations)
            ctx.__dict__.setdefault('retention_artifacts', {})[step.name] = dict(files=value['files'], observations=observations)
        # Legacy tasks still publish their complete generated workspace as compatible
        # state. They never acquire a complete portable action certificate from this scan.
        if old.get('stamp') != stamp and (value is None or any(isinstance(c, UnrealCompile) for c in step.commands)):
            _workspace(ctx, store)
        atomic_json(target, dict(schema=1, game=ctx.game, task=step.name, stamp=stamp,
                                 action=value['key'] if value else None,
                                 context=getattr(ctx, 'checkpoint_tool_context', None) or context(ctx), observations=observations))


def finish(ctx, steps):
    """Finalize build-time workspace deltas and completed task records before retention."""
    if getattr(ctx, 'checkpoint_settings', None) is None:
        return
    from . import checkpoint_actions as actions
    store = Store(ctx.game)
    records, entries, observations, incremental, inventories = {}, {}, {}, {}, {}
    tool = context(ctx)
    with store.locked():
        workspace = _workspace(ctx, store)
        for step in steps:
            target = safe_destination(folder(ctx.out), 'tasks/' + step.name + '.json')
            stamp_path = ctx.stamps / (step.name + '.json')
            if not target.is_file() or not stamp_path.is_file():
                continue
            record = read_json(target)
            stamp = read_json(stamp_path)
            if record.get('stamp') != stamp or record.get('context') != tool or stamp.get('touched'):
                continue
            if record.get('game') != ctx.game or record.get('task') != step.name:
                raise CheckpointError('Retention task binding differs')
            try:
                actions.check_observations(record.get('observations', {}))
            except (OSError, CheckpointError):
                continue
            key = record.get('action')
            if key is not None:
                value = actions.load(store, key)
                if value is None or value['task'] != step.name or value['fingerprint'] != stamp['fingerprint'] or key != stamp.get('checkpoint_key') or value['stamp'].get('checkpoint_inventory') != stamp.get('checkpoint_inventory'):
                    raise CheckpointError('Published task artifact certificate is missing')
                entries[key] = value
            from .build import Call
            if actions.verifiable(ctx, step):
                pass
            elif actions.inventory_verified(ctx, step, stamp):
                inventories[step.name] = stamp['output_inventory']
            else:
                continue  # Its stamp and owned files stay local; a receiver rebuilds them.
            if key is None and not (all(isinstance(c, Call) for c in step.commands) and not step.outputs):
                incremental[step.name] = stamp
            else:
                records[step.name] = stamp
        allowed = roots(ctx)
        for member, expected in workspace['local_observations'].items():
            label, _, tail = member.partition('/')
            root = allowed[label][0]
            observations[str(root / tail if tail else root)] = expected
        if not records and not incremental:
            (folder(ctx.out) / 'ready.json').unlink(missing_ok=True)
            return
        files = actions.publishable(workspace['files'], actions.ownership(ctx, steps, inventories))
        digests = {e['sha256'] for e in files.values() if e['kind'] == 'file'}
        manifest = dict(workspace, workspace_only=False, stamps=records, incremental_stamps=incremental,
                        steps=sorted({*records, *incremental}), actions=entries, files=files,
                        blob_observations={d: v for d, v in workspace['blob_observations'].items() if d in digests})
        key = store.save(manifest)
        atomic_json(folder(ctx.out) / 'ready.json', dict(schema=1, game=ctx.game,
                    checkout=manifest['checkout'], key=key,
                    stamps=_stamp_identities(ctx.out), observations=observations))


def _stamp_identities(out):
    result = {}
    for path in safe_destination(out, 'stamps').glob('*.json'):
        if path.is_symlink() or not path.is_file():
            raise CheckpointError('Nonregular producer stamp')
        stamp = read_json(path)
        if not stamp.get('touched'):
            result[path.stem] = identity(stamp)
    return result


def retain(source, out, game):
    """@cc [owner:fontanierh,label:correctness;performance] manifest-only-merge-retention
    Merge retention MUST read only build-published metadata under stopped-producer exclusion.
    It MUST NOT hash/copy generated files, re-certify task outputs, walk the workspace, export
    Zen, or launch a capture worker. Missing/stale evidence MUST refuse promptly and direct the
    caller to the normal incremental build, never silently perform a full capture or forge proof.
    """
    from .build_snapshot import require_complete
    with writer(out):
        require_complete(out, game=game)
        path = folder(out) / 'ready.json'
        if not path.is_file():
            raise CheckpointError('No build-published retention manifest; run the normal incremental build once, then retry retention')
        ready = read_json(path)
        if ready.get('schema') != 1 or ready.get('game') != game or ready.get('checkout') != identity(str(source.resolve())):
            raise CheckpointError('Retention manifest belongs to another producer')
        observed = _stamp_identities(out)
        if observed != ready.get('stamps'):
            raise CheckpointError('Build-published retention evidence is incomplete or stale; run the normal incremental build once')
        from .checkpoint_actions import check_observations
        parents = set()
        for name in ready.get('observations', {}):
            p = Path(name)
            if not (p.is_relative_to(source) or p.is_relative_to(out)):
                raise CheckpointError('Retention observation escapes its producer')
            parents.update(p.parents)
        if any(p.is_symlink() for p in parents):
            raise CheckpointError('Retention output has a linked ancestor')
        check_observations(ready.get('observations', {}))
        store = Store(game)
        manifest = store.load(ready['key'])
        certified = {n: identity(s) for n, s in {**manifest['stamps'], **manifest.get('incremental_stamps', {})}.items()}
        if manifest['checkout'] != ready['checkout'] or any(observed.get(n) != value for n, value in certified.items()):
            raise CheckpointError('Retention certificate differs from its published manifest')
        for digest, expected in manifest.get('blob_observations', {}).items():
            blob = store.blob(digest)
            if blob.is_symlink() or not blob.is_file() or list(signature(blob.lstat())) != expected:
                raise CheckpointError('Published CAS blob metadata changed')
        # CAS bytes are already certified and referenced by this immutable manifest.
        # Restoration still verifies all blob bytes and current receiving inputs.
        check_observations(ready.get('observations', {}))
        return ready['key']
