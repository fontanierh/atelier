"""Generic native-import candidates from immutable workspaces; never receiving success proof.

The native owner must verify source/import policy and recertify its outputs. These copies are
execution hints in ignored staging, never source or live Content replacements.
"""
from dataclasses import dataclass
import os
from pathlib import Path
import re
import stat
import tempfile
import time

from . import build_products
from .build_cache import atomic_json, copy_file
from .checkpoint_store import (CheckpointError, HEX, Store, context, identity, read_json,
                               relative, safe_destination, validate)


@dataclass(frozen=True)
class CandidateScope:
    files: tuple = ()
    directories: tuple = ()
    donor_task: str | None = None


def task_name(value):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9_][A-Za-z0-9_.-]*', value) or '..' in value:
        raise CheckpointError('Invalid candidate task name')
    return value


def root(ctx):
    return safe_destination(ctx.out, '.state/import-candidates')


def original(store, key):
    if not HEX.fullmatch(key):
        raise CheckpointError('Invalid candidate checkpoint key')
    try:
        return store.load(key)
    except FileNotFoundError:
        value = read_json(store.directory / 'candidate-sources' / (key + '.json'))
        validate(value, store.game)
        if identity(value) != key:
            raise CheckpointError('Candidate source manifest identity differs')
        return value


def inventory(ctx, key, task):
    """Original immutable member inventory and historical compatibility evidence, without copies."""
    task_name(task)
    saved = original(Store(ctx.game), key)
    stamp = {**saved['stamps'], **saved.get('incremental_stamps', {})}.get(task)
    revision = saved.get('source_revision', '')
    if (saved['context'] != context(ctx) or not stamp or stamp.get('touched')
            or not re.fullmatch(r'[0-9a-f]{40}', revision)):
        raise CheckpointError('Candidate needs compatible engine/platform, clean source revision and historical task proof')
    return dict(schema=1, checkpoint=key, donor_task=task, donor_fingerprint=stamp['fingerprint'],
                source_revision=revision, context=saved['context'], provenance='compatibility-only', files=saved['files'])


def checked_file(directory, member, entry):
    relative(member)
    if entry.get('path') != 'files/' + member or not HEX.fullmatch(entry.get('sha256', '')):
        raise CheckpointError('Invalid staged candidate member')
    path = safe_destination(directory, entry['path'])
    if (path.is_symlink() or not path.is_file() or path.stat().st_size != entry['size']
            or stat.S_IMODE(path.stat().st_mode) != entry['mode']
            or build_products.file_digest(path) != entry['sha256']):
        raise CheckpointError('Staged candidate bytes changed')
    return path


class Bundle(dict):
    """Loaded once per importer; each member access verifies only that member's actual bytes."""
    def __init__(self, value, directory):
        super().__init__(value)
        self.directory = directory

    def member_path(self, member):
        entry = self['files'].get(member)
        return checked_file(self.directory, member, entry) if entry is not None else None


def completion(ctx, value, directory, *, verify_files=True):
    if (value.get('schema') != 1 or value.get('provenance') != 'compatibility-only'
            or value.get('context') != context(ctx) or not HEX.fullmatch(value.get('checkpoint', ''))
            or not HEX.fullmatch(value.get('donor_fingerprint', ''))
            or not re.fullmatch(r'[0-9a-f]{40}', value.get('source_revision', ''))
            or not isinstance(value.get('files'), dict) or not value['files']):
        raise CheckpointError('Invalid or incompatible candidate completion')
    task_name(value['donor_task'])
    proof = inventory(ctx, value['checkpoint'], value['donor_task'])
    if any(value.get(k) != proof[k] for k in ('source_revision', 'context', 'donor_fingerprint')):
        raise CheckpointError('Candidate completion differs from immutable donor evidence')
    for member, entry in value['files'].items():
        original_entry = proof['files'].get(member)
        if original_entry is None or original_entry['kind'] != 'file' or any(
                entry.get(k) != original_entry[k] for k in ('sha256', 'size', 'mode')):
            raise CheckpointError('Candidate completion contains unproved donor members')
    bundle = Bundle(value, directory)
    if verify_files:
        for member in value['files']:
            bundle.member_path(member)
    return bundle


def load(ctx, task):
    """@cc [owner:fontanierh,label:correctness] compatibility-candidates-are-not-success
    A candidate pointer MUST stay within ignored receiving staging. Load MUST verify engine/
    platform context and staged file integrity. It MUST NOT publish a receiving stamp or claim
    current importer compatibility. A failed check MUST yield a normal cache miss. Reuse of
    native assets requires the native owner's current source/policy/material/collision proof.
    """
    try:
        pointer = read_json(root(ctx) / (task_name(task) + '.json'))
        if pointer.get('schema') != 1:
            return None
        manifest = safe_destination(root(ctx), pointer['manifest'])
        bundle = completion(ctx, read_json(manifest), manifest.parent)
        if bundle.get('receiver_task') != task:
            return None
        return bundle
    except (OSError, ValueError, KeyError, TypeError, CheckpointError):
        return None


def member_path(ctx, task, member, *, bundle=None):
    """Pass the Bundle from load() to avoid rehashing the bundle on each member access."""
    try:
        bundle = bundle if bundle is not None else load(ctx, task)
        return bundle.member_path(member) if bundle is not None else None
    except (OSError, ValueError, KeyError, TypeError, CheckpointError):
        return None


def stage_worker(ctx, request_id):
    if not re.fullmatch(r'[0-9a-f]{24}', request_id):
        raise CheckpointError('Invalid candidate staging request')
    request = read_json(ctx.out / '.state/candidate-requests' / (request_id + '.json'))
    proof = inventory(ctx, request['checkpoint'], request['donor_task'])
    task_name(request['receiver_task'])
    files = {}
    folder = root(ctx) / request['checkpoint'] / request['receiver_task'] / request_id
    store = Store(ctx.game)
    spoken = time.monotonic()
    for count, member in enumerate(request['members'], 1):
        entry = proof['files'].get(member)
        if entry is None or entry['kind'] != 'file':
            raise CheckpointError('Candidates must select explicit regular checkpoint files')
        target = safe_destination(folder, 'files/' + member)
        if os.path.lexists(target):
            raise CheckpointError('Candidate staging destination already exists')
        target.parent.mkdir(parents=True, exist_ok=True)
        blob = store.blob(entry['sha256'])
        if blob.is_symlink() or build_products.file_digest(blob) != entry['sha256']:
            raise CheckpointError('Candidate source blob is missing or corrupt')
        copy_file(blob, target)
        os.chmod(target, entry['mode'])
        files[member] = dict(path='files/' + member, sha256=entry['sha256'], size=entry['size'], mode=entry['mode'])
        checked_file(folder, member, files[member])
        if time.monotonic() - spoken >= 25:
            print(f'candidate staging: {count}/{len(request["members"])} verified files copied; no native import requested', flush=True)
            spoken = time.monotonic()
    value = {**proof, 'receiver_task': request['receiver_task'], 'files': files}
    completion(ctx, value, folder)
    return dict(request=request_id, folder=folder.relative_to(root(ctx)).as_posix(), value=value)


def stage(ctx, key, donor_task, members, *, receiver_task=None):
    """@cc [owner:fontanierh,label:correctness] candidate-completion-after-guard
    Staging MUST use independent copies of explicitly selected immutable regular members,
    refuse linked destinations, and publish its pointer only after successful guard cleanup
    and a second integrity check. It MUST NOT replace live Content, source or success stamps.
    Historical source revision MUST come from clean capture evidence, never receiving HEAD.
    """
    receiver_task = task_name(receiver_task or donor_task)
    proof = inventory(ctx, key, donor_task)
    members = sorted(set(members))
    if not members or any(m not in proof['files'] or proof['files'][m]['kind'] != 'file' for m in members):
        raise CheckpointError('Candidate selection must contain existing regular checkpoint members')
    request_id = os.urandom(12).hex()
    request = dict(checkpoint=key, donor_task=donor_task, receiver_task=receiver_task, members=members)
    atomic_json(ctx.out / '.state/candidate-requests' / (request_id + '.json'), request)
    from .build_checkpoints import _guard
    result = _guard(ctx, 'stage-candidates', request_id)
    if result.get('folder') != '/'.join((key, receiver_task, request_id)):
        raise CheckpointError('Candidate guard returned a foreign staging folder')
    folder = safe_destination(root(ctx), result['folder'])
    value = result['value']
    if (result.get('request') != request_id or value.get('checkpoint') != key
            or value.get('receiver_task') != receiver_task or value.get('donor_task') != donor_task
            or value.get('donor_fingerprint') != proof['donor_fingerprint'] or set(value['files']) != set(members)):
        raise CheckpointError('Candidate guard completion differs from its request')
    for member in members:
        if any(value['files'][member][k] != proof['files'][member][k] for k in ('sha256', 'size', 'mode')):
            raise CheckpointError('Candidate completion contains foreign bytes')
    completion(ctx, value, folder)
    target = folder / 'manifest.json'
    atomic_json(target, value)
    atomic_json(root(ctx) / (receiver_task + '.json'), dict(schema=1, manifest=target.relative_to(root(ctx)).as_posix()))
    return target


def select(ctx, scope, files):
    from .checkpoint_actions import label
    required = [label(ctx, p) for p in scope.files]
    prefixes = [label(ctx, p).rstrip('/') + '/' for p in scope.directories]
    if any(name not in files or files[name]['kind'] != 'file' for name in required):
        return []
    return sorted(set(required) | {n for n, e in files.items() if e['kind'] == 'file' and any(n.startswith(p) for p in prefixes)})


def prepare(ctx, step, *, echo=print):
    """Automatically discover compatible candidates before a normal native miss, including batches."""
    scope = getattr(step, 'candidate_scope', None)
    if scope is None:
        return None
    if not isinstance(scope, CandidateScope) or not (scope.files or scope.directories):
        raise CheckpointError('Native candidates require a typed, nonempty scope')
    prepared = ctx.__dict__.setdefault('prepared_candidate_tasks', set())
    if step.name in prepared:
        return None
    prepared.add(step.name)
    donor_task = scope.donor_task or step.name
    store = Store(ctx.game)
    def attempt(key):
        proof = inventory(ctx, key, donor_task)
        selected = select(ctx, scope, proof['files'])
        if not selected:
            return None
        return stage(ctx, key, donor_task, selected, receiver_task=step.name)
    for key, _ in store.latest():
        try:
            result = attempt(key)
            if result:
                echo(step.name + ': staged compatible local candidates; native validation still required')
                return result
        except (OSError, ValueError, KeyError, TypeError, CheckpointError) as error:
            echo(step.name + ': candidate miss (' + str(error) + ')')
    from .build_checkpoints import configured
    settings = configured(ctx)
    if settings and settings.get('repository'):
        from .checkpoint_github import Remote
        remote = Remote(settings['repository'], ctx.game, echo=echo)
        try:
            with tempfile.TemporaryDirectory(dir=store.directory) as temporary:
                for item in remote.candidates():
                    data = remote.descriptor(item, Path(temporary))
                    key, saved = data['key'], data['checkpoint']
                    # Metadata-only catalogues never become full workspace donors.
                    atomic_json(store.directory / 'candidate-sources' / (key + '.json'), saved)
                    try:
                        proof = inventory(ctx, key, donor_task)
                    except CheckpointError:
                        continue
                    selected = select(ctx, scope, proof['files'])
                    if not selected:
                        continue
                    subset = dict(saved, files={n: saved['files'][n] for n in selected}, stamps={}, incremental_stamps={}, actions={})
                    needed = {e['sha256'] for e in subset['files'].values()}
                    transfer = dict(data, checkpoint=subset, key=identity(subset), blobs={n: data['blobs'][n] for n in needed})
                    remote.fetch(item, transfer, store, save=False)
                    return attempt(key)
        except (OSError, ValueError, KeyError, TypeError, RuntimeError) as error:
            echo(step.name + ': remote candidate miss (' + str(error) + ')')
    echo(step.name + ': no compatible native candidates; normal import remains required')
    return None
