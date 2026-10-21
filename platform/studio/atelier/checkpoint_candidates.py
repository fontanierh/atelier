"""Generic native-import candidates from immutable workspaces; never receiving success proof.

The native owner must verify source/import policy and recertify its outputs. These copies are
execution hints in ignored staging, never source or live Content replacements.
"""
from dataclasses import dataclass
import os
from pathlib import Path
import re
import tempfile
import time

from . import build_products
from .native_candidates import (task_name, root, original, inventory, checked_file, Bundle, completion, load, member_path)
from .build_cache import atomic_json, copy_file
from .checkpoint_store import (CheckpointError, HEX, Store, context, identity, read_json,
                               relative, safe_destination, validate)


@dataclass(frozen=True)
class CandidateScope:
    files: tuple = ()
    directories: tuple = ()
    donor_task: str | None = None


def save_prior(ctx, task, nonce, stamp):
    """Non-success historical evidence; the caller still invalidates its actual build stamp."""
    if not stamp:
        return None
    task_name(task)
    if not re.fullmatch('[0-9a-f]{24}', nonce) or not isinstance(stamp, dict):
        raise CheckpointError('Invalid prior native evidence owner or invocation')
    path = safe_destination(ctx.out, '.state/mesh-import-prior/' + task + '/' + nonce + '.json')
    if os.path.lexists(path):
        raise CheckpointError('Prior native invocation evidence already exists')
    atomic_json(path, dict(schema=1, task=task, nonce=nonce, stamp=stamp,
                           observed_context=getattr(ctx, 'checkpoint_observed_context', None)))
    return path


def stage_worker(ctx, request_id):
    if not re.fullmatch(r'[0-9a-f]{24}', request_id):
        raise CheckpointError('Invalid candidate staging request')
    request = read_json(safe_destination(ctx.out, '.state/candidate-requests/' + request_id + '.json'))
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
    request_path = safe_destination(ctx.out, '.state/candidate-requests/' + request_id + '.json')
    atomic_json(request_path, request)
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


def local_keys(store):
    """Defer manifest validation to each attempt so one corrupt donor cannot hide older work."""
    candidates = []
    for path in [*store.manifests.glob('*.json'), *(store.directory / 'candidate-sources').glob('*.json')]:
        try:
            candidates.append((path.stat().st_mtime_ns, path.stem))
        except OSError:
            continue
    return list(dict.fromkeys(key for _, key in sorted(candidates, reverse=True)))


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
    for key in local_keys(store):
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
            with remote.transaction(), tempfile.TemporaryDirectory(dir=store.directory) as temporary:
                for item in remote.candidates():
                    try:
                        data = remote.descriptor(item, Path(temporary))
                        key, saved = data['key'], data['checkpoint']
                        # Metadata-only catalogues never become full workspace donors.
                        atomic_json(store.directory / 'candidate-sources' / (key + '.json'), saved)
                        proof = inventory(ctx, key, donor_task)
                        selected = select(ctx, scope, proof['files'])
                        if not selected:
                            continue
                        subset = dict(saved, files={n: saved['files'][n] for n in selected}, stamps={}, incremental_stamps={}, actions={})
                        needed = {e['sha256'] for e in subset['files'].values()}
                        transfer = dict(data, checkpoint=subset, key=identity(subset), blobs={n: data['blobs'][n] for n in needed})
                        remote.fetch(item, transfer, store, save=False)
                        return attempt(key)
                    except (OSError, ValueError, KeyError, TypeError, RuntimeError) as error:
                        echo(step.name + ': remote donor miss (' + str(error) + ')')
        except (OSError, ValueError, KeyError, TypeError, RuntimeError) as error:
            echo(step.name + ': remote candidate miss (' + str(error) + ')')
    echo(step.name + ': no compatible native candidates; normal import remains required')
    return None
