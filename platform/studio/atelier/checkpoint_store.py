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

    def latest(self):
        candidates = sorted(self.manifests.glob('*.json'), key=lambda p: p.stat().st_mtime_ns, reverse=True)
        return [(p.stem, self.load(p.stem)) for p in candidates]

    def summaries(self):
        """Newest first; a small cached summary per immutable manifest, so scans avoid large JSON."""
        index = self.directory / 'index'
        result = []
        for path in sorted(self.manifests.glob('*.json'), key=lambda p: p.stat().st_mtime_ns, reverse=True):
            cached = index / path.name
            try:
                summary = read_json(cached) if cached.is_file() else None
                if not isinstance(summary, dict) or summary.get('schema') != 2:
                    summary = summarize(self.load(path.stem))
                    index.mkdir(parents=True, exist_ok=True)
                    atomic_json(cached, summary)
            except (OSError, ValueError, KeyError, TypeError, CheckpointError):
                continue
            result.append((path.stem, summary))
        return result

SMALL_UNIT = 256


def unit_name(member):
    """Hydration unit of a member: its root, or one task's native import receipts."""
    parts = member.split('/', 3)
    if parts[0] == 'generated' and len(parts) > 3 and parts[1] == 'native-imports':
        return 'generated/native-imports/' + parts[2] + '/'
    return parts[0] + '/'


def summarize(saved):
    units, listings = {}, {}
    for member, entry in saved['files'].items():
        label = member.partition('/')[0] + '/'
        units[label] = units.get(label, 0) + 1
        unit = unit_name(member)
        if unit != label:
            units[unit] = units.get(unit, 0) + 1
    for member, entry in saved['files'].items():
        unit = member.partition('/')[0] + '/'
        if units[unit] <= SMALL_UNIT:
            listings.setdefault(unit, {})[member[len(unit):]] = [entry['kind'], entry.get('size'), entry.get('mode'), entry.get('mtime_ns')]
    stamps = {**saved['stamps'], **saved.get('incremental_stamps', {})}
    return dict(schema=2, context=identity(saved['context']), checkout=saved['checkout'],
                steps=sorted(saved.get('steps', ())), workspace_only=bool(saved.get('workspace_only')),
                units=units, listings=listings, stamps={n: s.get('fingerprint') for n, s in stamps.items()})


RESTORED_HASHES = '.state/file-hashes.sqlite3'  # The build's own hash index.


def certificates(ctx, steps, *, include_incremental=False, hashes=None):
    from .build import fingerprint, order, outputs_present, result
    from .build_plan import read_stamp
    from .checkpoint_actions import compile_present, certified, local_incremental
    done, records, tools = {}, {}, {}  # One tool enumeration per pass, as in the build loop.
    with HashIndex(hashes) as index, hashing(ctx, index.digest):
        for step in order(steps, [s.name for s in steps]):
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


def cold(ctx):
    """Whole-workspace hydration never merges with a receiver's existing generated work."""
    for label, (root, _) in roots(ctx).items():
        if any(members(root)):
            return False
    return True


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


def declared_member(name, outputs):
    while name:
        if name in outputs:
            return True
        name = name.rpartition('/')[0]
    return False


def _place(store, selected, echo, verified=frozenset()):
    """Clone digest-named blobs in parallel; links and directories follow sequentially."""
    def place(item):
        destination, entry = item
        if destination.exists() or destination.is_symlink():
            if destination.is_symlink() or not destination.is_file():
                raise CheckpointError('Receiver output changed during checkpoint restoration; preserving it')
            if destination not in verified and not unchanged(destination, entry):
                if build_products.file_digest(destination) != entry['sha256']:
                    raise CheckpointError('Receiver output changed during checkpoint restoration; preserving it')
            return
        staged = destination.parent / ('.checkpoint-' + os.urandom(8).hex())
        try:
            copy_file(store.blob(entry['sha256']), staged)
            os.chmod(staged, entry['mode'])
            os.utime(staged, ns=(entry['mtime_ns'], entry['mtime_ns']))
            staged.replace(destination)
        finally:
            staged.unlink(missing_ok=True)
    started = spoken = time.monotonic()
    files = [item for item in selected.values() if item[1]['kind'] == 'file']
    for parent in sorted({d.parent for d, _ in selected.values()}):
        parent.mkdir(parents=True, exist_ok=True)
    # APFS clones are metadata operations; a few threads hide per-file syscall latency.
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(8) as pool:
        for count, _ in enumerate(pool.map(place, files), 1):
            if time.monotonic() - spoken >= 25:
                echo(f'checkpoint restore: {count}/{len(files)} files cloned')
                spoken = time.monotonic()
    for destination, entry in selected.values():
        if entry['kind'] == 'directory':
            if destination.is_symlink() or destination.exists() and not destination.is_dir():
                raise CheckpointError('Receiver directory destination is occupied')
            destination.mkdir(exist_ok=True)
        elif entry['kind'] == 'link':
            link = os.path.relpath(entry['resolved'], destination.parent)
            if destination.is_symlink():
                if os.readlink(destination) != link:
                    raise CheckpointError('Receiver link changed during checkpoint restoration')
            elif destination.exists():
                raise CheckpointError('Receiver link destination is occupied')
            else:
                destination.symlink_to(link)
    for destination, entry in files:
        if not unchanged(destination, entry) and destination not in verified:
            raise CheckpointError('Restored checkpoint bytes differ; launch barrier retained')
    echo(f'checkpoint restore: {len(files)} files cloned in {time.monotonic() - started:.1f} s')
    return files


def _select(ctx, store, manifest, allowed, keep):
    """Verified destinations for members accepted by keep(member, label, name)."""
    selected = {}
    source_paths = tracked_paths()
    same_path = manifest['checkout'] == identity(str(paths.REPO.resolve()))
    for member, entry in manifest['files'].items():
        label, _, name = member.partition('/')
        if label not in allowed:
            raise CheckpointError('Checkpoint root is not owned by this project')
        root, path_bound = allowed[label]
        if path_bound and not same_path or not keep(member, label, name):
            continue
        destination = safe_destination(root, name)
        if destination in source_paths:
            raise CheckpointError('Checkpoint cannot replace tracked source')
        if entry['kind'] == 'file':
            blob = store.blob(entry['sha256'])
            # Blobs are named by digest and verified when written; restore checks identity, not bytes.
            if not blob.is_file() or blob.is_symlink() or blob.stat().st_size != entry['size']:
                raise CheckpointError('Checkpoint blob is missing or corrupt')
        if entry['kind'] == 'link':
            if entry['target'].startswith('member:'):
                target_label, _, target_name = entry['target'][7:].partition('/')
                entry = dict(entry, resolved=safe_destination(allowed[target_label][0], target_name))
            else:
                entry = dict(entry, resolved=ctx.unreal_root / entry['target'][7:])
        selected[member] = (destination, entry)
    return selected


def restore(ctx, steps, store, key, *, echo=print):
    """@cc [owner:fontanierh,label:correctness] checkpoint-restoration-certificates
    Restoration MUST preserve source files, use independent verified copies and stay within
    locally allowed generated roots. Saved certificates are only staged; the build MUST adopt
    one only when the receiving recipe's own fingerprint matches and its outputs certify. A durable launch barrier MUST precede mutation and survive any failure.
    Existing generated work MUST NOT be overwritten. Compiler intermediates MUST NOT relocate.
    Copies MUST be clones/copies of digest-named blobs verified when stored; restoration MAY prove
    them by blob size and copied size/mode/mtime instead of rereading bytes.
    """
    from .build_snapshot import require_complete
    manifest = store.load(key)
    if manifest['context'] != context(ctx):
        raise CheckpointError('Checkpoint engine/platform identity differs')
    allowed = roots(ctx)
    from .checkpoint_actions import ownership, trusted, unverified_member
    names, inventories = trusted(ctx, steps, manifest)
    saved_stamps = {n: v for n, v in {**manifest['stamps'], **manifest.get('incremental_stamps', {})}.items() if n in names}
    owners = ownership(ctx, steps, inventories)
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
    # Files owned by unverifiable receiving steps are never adopted, even from older manifests.
    selected = _select(ctx, store, manifest, allowed, lambda member, *_: not unverified_member(member, owners))
    selected = {m: (d, e) for m, (d, e) in selected.items()
                if not (e['kind'] == 'link' and e['target'].startswith('member:') and unverified_member(e['target'][7:], owners))}
    # Verify link targets before changing anything; never create a link into a skipped root.
    for destination, entry in selected.values():
        if entry['kind'] == 'link' and entry['target'].startswith('member:'):
            if (entry['target'][7:] not in selected
                    and not any(m.startswith(entry['target'][7:] + '/') for m in selected)):
                raise CheckpointError('Checkpoint link target is unavailable')
    ctx.stamps.mkdir(parents=True, exist_ok=True)
    atomic_json(journal, resume)
    files = _place(store, selected, echo)
    with HashIndex(ctx.out / RESTORED_HASHES) as hashes:
        for destination, entry in files:
            hashes.record(destination, entry['sha256'])
    # Imported source paths remain provenance. Runtime packages retain their logical /Game paths.
    # The installed engine discovers its registry normally; producer registry caches are not copied.
    # No certificate pass here: the caller stages the saved stamps and the build adopts each one
    # only when its own fingerprint matches and its restored outputs certify, as for hydration.
    from .build_checkpoints import estimate
    atomic_json(ctx.out / '.state/checkpoint.json', dict(key=key, restored=sorted(saved_stamps),
                estimates={name: estimate(stamp) for name, stamp in saved_stamps.items()}))
    return saved_stamps


HYDRATION_REQUEST = '.state/hydration-request.json'


def hydrate_files(ctx, store, key, *, echo=print):
    """@cc [owner:fontanierh,label:correctness] checkpoint-file-hydration
    Hydration of a non-cold receiver MAY only add generated files that are missing locally,
    within locally allowed roots and paths a receiving step declares; it MUST NOT overwrite or
    delete any existing file, link or directory, nor write certificates. A durable journal MUST
    precede mutation. Compiler intermediates MUST NOT relocate.
    """
    from .build_snapshot import require_complete
    journal = ctx.out / JOURNAL
    existing = read_json(journal) if journal.exists() else None
    request = existing if existing is not None else read_json(ctx.out / HYDRATION_REQUEST)
    if request.get('key') != key or not isinstance(request.get('units'), list):
        raise CheckpointError('Checkpoint hydration request differs')
    resume = dict(schema=SCHEMA, key=key, game=ctx.game, units=sorted(request['units']),
                  stamps=sorted(request.get('stamps', [])))
    if existing is not None:
        resume = existing  # Earlier formats resume with their own recorded scope.
    require_complete(ctx.out, game=ctx.game, checkpoint_resume=resume if existing else None)
    manifest = store.load(key)
    if manifest['context'] != context(ctx):
        raise CheckpointError('Checkpoint engine/platform identity differs')
    allowed = roots(ctx)
    units = [u for u in resume['units'] if u.partition('/')[0] in allowed and u.partition('/')[0] not in ('zen', 'cooked')]
    outputs = set(read_json(ctx.out / HYDRATION_REQUEST).get('outputs', ())) if (ctx.out / HYDRATION_REQUEST).is_file() else set()
    owners = read_json(ctx.out / HYDRATION_REQUEST).get('owners', {}) if (ctx.out / HYDRATION_REQUEST).is_file() else {}
    from .checkpoint_actions import unverified_member
    def keep(member, label, name):
        return (any(member.startswith(u) for u in units) and not unverified_member(member, owners)
                and (label != 'generated' or declared_member(name, outputs)))
    candidates = _select(ctx, store, manifest, allowed, keep)
    # Only absent destinations, under real local directories, are filled.
    parents, blocked = set(), set()
    for member, (destination, _) in candidates.items():
        root = allowed[member.partition('/')[0]][0]
        for parent in destination.parents:
            if parent == root or parent in parents:
                break
            parents.add(parent)
    blocked = {p for p in parents if p.is_symlink() or p.exists() and not p.is_dir()}
    selected = {m: (d, e) for m, (d, e) in candidates.items()
                if not os.path.lexists(d) and not (blocked and any(p in blocked for p in d.parents))
                and (e['kind'] != 'link' or os.path.lexists(e['resolved']) or e['target'][7:] in candidates)}
    if existing is None:
        atomic_json(journal, resume)
    files = _place(store, selected, echo)
    with HashIndex(ctx.out / RESTORED_HASHES) as hashes:
        for destination, entry in files:
            hashes.record(destination, entry['sha256'])
    return len(selected)


def tracked_paths():
    """Tracked source can never be acquired by a generated-output transaction."""
    import subprocess
    if not (paths.REPO / '.git').exists():
        return set()
    result = subprocess.run(['git', '-C', str(paths.REPO), 'ls-files', '-z'], check=True,
                            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=15)
    return {paths.REPO / os.fsdecode(name) for name in result.stdout.split(b'\0') if name}
