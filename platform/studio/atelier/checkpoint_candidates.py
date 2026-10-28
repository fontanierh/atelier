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
from .native_candidates import (task_name, root, original, inventory, checked_file, object_path,
                                Bundle, completion, load, member_path)
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
    if 'donors' in request:
        return stage_composed_worker(ctx, request_id, request)
    proof = inventory(ctx, request['checkpoint'], request['donor_task'])
    from .checkpoint_actions import destination, reject_controller_overlap
    reject_controller_overlap(ctx, [destination(ctx, member) for member in request['members']])
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


def stage_composed_worker(ctx, request_id, request):
    """Copy the union of immutable objects once, preserving separate original donor proofs."""
    task = task_name(request['receiver_task'])
    folder = safe_destination(root(ctx), 'composed/' + task + '/' + request_id)
    if os.path.lexists(folder):
        raise CheckpointError('Candidate staging destination already exists')
    store, values, copied, verified = Store(ctx.game), [], set(), set()
    spoken = time.monotonic()
    for selected in request['donors']:
        try:
            proof = inventory(ctx, selected['checkpoint'], selected['donor_task'])
            from .checkpoint_actions import destination, reject_controller_overlap
            reject_controller_overlap(ctx, [destination(ctx, member) for member in selected['members']])
            files = {}
            for member in selected['members']:
                entry = proof['files'].get(member)
                if entry is None or entry['kind'] != 'file':
                    raise CheckpointError('Candidates must select explicit regular checkpoint files')
                item = {k: entry[k] for k in ('sha256', 'size', 'mode')}
                item['path'] = object_path(item)
                target = safe_destination(folder, item['path'])
                if item['path'] not in copied:
                    if os.path.lexists(target):
                        raise CheckpointError('Candidate object destination already exists')
                    blob = store.blob(entry['sha256'])
                    if blob.is_symlink() or build_products.file_digest(blob) != entry['sha256']:
                        raise CheckpointError('Candidate source blob is missing or corrupt')
                    target.parent.mkdir(parents=True, exist_ok=True)
                    copy_file(blob, target)
                    os.chmod(target, entry['mode'])
                    copied.add(item['path'])
                checked_file(folder, member, item, shared=True, verified=verified)
                files[member] = item
                if time.monotonic() - spoken >= 25:
                    print(f'candidate staging: {len(copied)} unique objects, {len(values)} complete donors; no native import requested', flush=True)
                    spoken = time.monotonic()
            value = {**proof, 'schema': 2, 'receiver_task': task, 'files': files}
            completion(ctx, value, folder, verified=verified)
            values.append(value)
        except (OSError, ValueError, KeyError, TypeError, CheckpointError) as error:
            print('candidate donor miss: ' + str(error), flush=True)
    return dict(request=request_id, folder=folder.relative_to(root(ctx)).as_posix(), values=values,
                unique_objects=len(copied))


def stage_many(ctx, task, donors):
    """@cc [owner:fontanierh,label:correctness] bounded-candidate-composition
    One invocation MUST guard the complete composition. Copies and byte verification MUST be
    bounded by the union of selected (SHA256, mode) objects, not catalogue count times scope size.
    Each donor MUST retain its complete independent original proof. Shared copies MUST remain
    invocation-owned staging, never links or live Content, and every later member use MUST verify.
    """
    task_name(task)
    request_id = os.urandom(12).hex()
    selected = {value['checkpoint']: value for value in donors}
    request_path = safe_destination(ctx.out, '.state/candidate-requests/' + request_id + '.json')
    atomic_json(request_path, dict(receiver_task=task, donors=list(selected.values())))
    from .build_checkpoints import _guard
    result = _guard(ctx, 'stage-candidates', request_id)
    if result.get('request') != request_id or result.get('folder') != '/'.join(('composed', task, request_id)):
        raise CheckpointError('Candidate guard returned a foreign composition')
    folder = safe_destination(root(ctx), result['folder'])
    manifests, verified = [], set()
    for value in result['values']:
        try:
            choice = selected.get(value['checkpoint'])
            if (not choice or value['schema'] != 2 or value['receiver_task'] != task
                    or value['donor_task'] != choice['donor_task'] or set(value['files']) != set(choice['members'])):
                raise CheckpointError('Candidate guard composition differs from its request')
            completion(ctx, value, folder, verified=verified)
            manifest = folder / (value['checkpoint'] + '.json')
            atomic_json(manifest, value)
            manifests.append(manifest)
        except (OSError, ValueError, KeyError, TypeError, CheckpointError):
            continue
    return publish_bundles(ctx, task, manifests)


def stage(ctx, key, donor_task, members, *, receiver_task=None, publish=True):
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
    if publish:
        publish_bundles(ctx, receiver_task, [target])
    return target


def publish_bundles(ctx, task, manifests):
    """@cc [owner:fontanierh,label:correctness] independent-candidate-donors
    Every donor MUST retain its own original stamp, report and complete package inventory.
    A combined pointer MUST NOT merge files, fabricate a producer stamp, or install Content.
    Each selected donor MUST pass fresh context and staged-byte validation before publication.

    Publish independent donor manifests only after all their guarded copies complete.
    """
    task_name(task)
    members, verified = [], set()
    for manifest in manifests:
        try:
            member = Path(manifest).relative_to(root(ctx)).as_posix()
            target = safe_destination(root(ctx), member)
            value = completion(ctx, read_json(target), target.parent, verified=verified)
            if value.get('receiver_task') != task:
                raise CheckpointError('Candidate composition contains a foreign receiver')
            if member not in members:
                members.append(member)
        except (OSError, ValueError, KeyError, TypeError, CheckpointError):
            continue
    if not members:
        raise CheckpointError('Candidate composition has no unchanged valid donors')
    value = (dict(schema=1, manifest=members[0]) if len(members) == 1 else
             dict(schema=2, manifests=members))
    atomic_json(root(ctx) / (task + '.json'), value)
    return safe_destination(root(ctx), members[0])


def select(ctx, scope, files):
    from .checkpoint_actions import label, reject_controller_overlap
    reject_controller_overlap(ctx, [*scope.files, *scope.directories])
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


def prepare(ctx, step, *, fingerprint=None, echo=print):
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
    signatures, selected_donors = set(), []
    def signature(proof, selected):
        return (proof['donor_fingerprint'], tuple((name, *(proof['files'][name][k]
                for k in ('sha256', 'size', 'mode'))) for name in selected))
    def attempt(key):
        proof = inventory(ctx, key, donor_task)
        selected = select(ctx, scope, proof['files'])
        if not selected:
            return None
        token = signature(proof, selected)
        if token in signatures:
            return None
        signatures.add(token)
        selected_donors.append(dict(checkpoint=key, donor_task=donor_task, members=selected))
        return key
    # Ranking hints are never admission proof. Re-read the selected immutable descriptor
    # in attempt()/stage(), even when another task has already ranked it in this build.
    from .native_candidates import original
    from .checkpoint_actions import label
    required = {label(ctx, path): Path(path) for path in scope.files}
    prefixes = [label(ctx, path).rstrip('/') + '/' for path in scope.directories]
    current_files = {}
    for member, path in required.items():
        try:
            if not path.is_symlink():
                current_files[member] = build_products.file_digest(path)
        except (OSError, ValueError):
            pass
    hints = ctx.__dict__.setdefault('candidate_catalogue_ranking_hints', {})
    ranked, current_context = [], context(ctx)
    spoken = time.monotonic()
    for age, key in enumerate(local_keys(store)):
        try:
            cache_key = (str(store.directory), key)
            if cache_key not in hints:
                saved = original(store, key)
                stamps = {**saved['stamps'], **saved.get('incremental_stamps', {}), **saved.get('historical_stamps', {})}
                hints[cache_key] = dict(context=saved['context'], revision=saved.get('source_revision', ''),
                    stamps={name: stamp['fingerprint'] for name, stamp in stamps.items() if not stamp.get('touched')},
                    files={name: entry['sha256'] for name, entry in saved['files'].items() if entry['kind'] == 'file'})
            if time.monotonic() - spoken >= 25:
                echo(step.name + ': ranking native donor metadata ' + str(age + 1) + ' catalogues inspected')
                spoken = time.monotonic()
            hint = hints[cache_key]
            if (hint['context'] != current_context or donor_task not in hint['stamps']
                    or not re.fullmatch('([0-9a-f]{40})?', hint['revision']) or not set(required) <= hint['files'].keys()):
                continue
            selected = set(required) | {name for name in hint['files'] if any(name.startswith(prefix) for prefix in prefixes)}
            if selected:
                exact = fingerprint is not None and hint['stamps'][donor_task] == fingerprint
                matching = sum(hint['files'].get(name) == digest for name, digest in current_files.items())
                primaries = sum(name.startswith('content/') and name.endswith('.uasset') for name in selected)
                ranked.append((-int(exact), -matching, -primaries, -len(selected), age, key))
        except (OSError, ValueError, KeyError, TypeError, CheckpointError) as error:
            echo(step.name + ': candidate miss (' + str(error) + ')')
    for *_, key in sorted(ranked):
        try:
            result = attempt(key)
            if result:
                echo(step.name + ': selected independent local donor; native validation still required')
        except (OSError, ValueError, KeyError, TypeError, CheckpointError) as error:
            echo(step.name + ': candidate miss (' + str(error) + ')')
    if selected_donors:
        try:
            return stage_many(ctx, step.name, selected_donors)
        except (OSError, ValueError, KeyError, TypeError, CheckpointError) as error:
            echo(step.name + ': candidate composition miss (' + str(error) + ')')
            selected_donors.clear()
            signatures.clear()
    from .build_checkpoints import configured, remote_repository
    settings = configured(ctx)
    if remote_repository(settings) is not None:
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
                        if signature(proof, selected) in signatures:
                            continue
                        subset = dict(saved, files={n: saved['files'][n] for n in selected}, stamps={}, incremental_stamps={}, actions={})
                        needed = {e['sha256'] for e in subset['files'].values()}
                        transfer = dict(data, checkpoint=subset, key=identity(subset), blobs={n: data['blobs'][n] for n in needed})
                        remote.fetch(item, transfer, store, save=False)
                        result = attempt(key)
                        if result:
                            echo(step.name + ': selected independent remote donor; native validation still required')
                    except (OSError, ValueError, KeyError, TypeError, RuntimeError) as error:
                        echo(step.name + ': remote donor miss (' + str(error) + ')')
        except (OSError, ValueError, KeyError, TypeError, RuntimeError) as error:
            echo(step.name + ': remote candidate miss (' + str(error) + ')')
    if selected_donors:
        try:
            return stage_many(ctx, step.name, selected_donors)
        except (OSError, ValueError, KeyError, TypeError, CheckpointError) as error:
            echo(step.name + ': candidate composition miss (' + str(error) + ')')
    echo(step.name + ': no compatible native candidates; normal import remains required')
    return None
