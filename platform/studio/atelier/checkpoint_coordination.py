"""Cross-machine exclusion for private checkpoint publication, downloads and pack retirement."""
from contextlib import contextmanager
import os
import re
import time
import threading
import uuid

from . import paths, release
from .atomic_files import atomic_json
from .checkpoint_store import CheckpointError, identity, read_json

WAIT_SECONDS = 600


def claim_path(remote):
    return paths.cache_dir('checkpoints', 'writers') / (identity([remote.repository, remote.game]) + '.json')


def reference(remote):
    return 'heads/atelier-cache-' + remote.game + '-writer'


def observe(remote):
    # State reads must not reuse a proxy's earlier response to this mutable ref.
    return remote.github.read('git/ref/' + reference(remote) + '?refresh=' + uuid.uuid4().hex, missing=True)


def make_claim(remote, target):
    metadata = remote.require_private()
    base = remote.github.read('git/ref/heads/' + metadata['default_branch'])['object']['sha']
    tree = remote.github.read('git/commits/' + base)['tree']['sha']
    nonce = uuid.uuid4().hex
    commit = remote.github.api('git/commits', method='POST', data=dict(tree=tree, parents=[base],
        message='Atelier private cache writer ' + remote.game + ' ' + nonce))
    value = dict(schema=1, game=remote.game, repository=remote.repository, commit=commit['sha'], nonce=nonce, state='prepared')
    atomic_json(target, value)
    return value


@contextmanager
def owned(remote):
    """@cc [owner:fontanierh,label:safety] cross-machine-checkpoint-exclusion
    Every private checkpoint publisher, downloader and destructive collector MUST hold the
    same atomically created Git ref. Ownership MUST NOT expire or be stolen. A crashed held
    claim MUST require explicit worker/transport cleanup proof before reuse. Release intent MUST
    persist before its single DELETE; an ambiguous release MUST remain observation-only.
    """
    target = claim_path(remote)
    value = read_json(target) if target.exists() else None
    if value is not None and (type(value) is not dict or value.get('schema') != 1
            or value.get('repository') != remote.repository or value.get('game') != remote.game
            or not re.fullmatch('[0-9a-f]{40}', value.get('commit', ''))):
        raise CheckpointError('Invalid durable cache writer claim')
    started = spoken = time.monotonic()
    if value is not None and value.get('state') == 'held':
        raise CheckpointError('Previous private writer needs explicit worker and transport cleanup proof')
    held = False
    while not held:
        if remote.github.stop.is_set() or time.monotonic() - started >= WAIT_SECONDS:
            raise CheckpointError('Timed out waiting for the private cache writer; no resources held')
        if time.monotonic() - spoken >= 25:
            remote.echo(f'private cache: waiting for writer ownership; {time.monotonic() - started:.0f}s elapsed')
            spoken = time.monotonic()
        current = observe(remote)
        observed = current.get('object', {}).get('sha') if current else None
        if value is not None and value.get('state') == 'releasing':
            if observed == value['commit']:
                raise CheckpointError('Private writer release is uncertain; preserve its claim and use writer-recover after cleanup proof')
            value = None  # Earlier DELETE is observed complete; never reuse its nonce/commit.
        if value is not None and observed == value['commit']:
            held = True
            break
        if observed is None:
            if value is None or value.get('state') == 'released':
                value = make_claim(remote, target)
            try:
                remote.github.api('git/refs', method='POST', data=dict(ref='refs/' + reference(remote), sha=value['commit']))
            except release.TransportError as error:
                if error.code not in (None, 422, 500, 502, 503, 504):
                    raise
                remote.github.stop.wait(1)
            continue  # Observe the exact accepted commit, including ambiguous create responses.
        if remote.github.stop.is_set() or time.monotonic() - started >= WAIT_SECONDS:
            raise CheckpointError('Timed out waiting for the private cache writer; no resources held')
        remote.github.stop.wait(2)
    value['state'] = 'held'; value['pid'] = os.getpid(); atomic_json(target, value)
    try:
        yield
    finally:
        # All owned requests/uploads have returned or joined before this boundary.
        # Cleanup must still run after the operation's cancellation/deadline event.
        operation_stop = remote.github.stop
        remote.github.stop = threading.Event()
        try:
            if getattr(remote, '_checkpoint_mutation_uncertain', False):
                raise CheckpointError('Private asset deletion remains unresolved; writer claim retained')
            current = observe(remote)
            if not current or current.get('object', {}).get('sha') != value['commit']:
                raise CheckpointError('Private cache writer ownership changed; no foreign claim removed')
            value['state'] = 'releasing'; atomic_json(target, value)
            remote.github.api('git/refs/' + reference(remote), method='DELETE')
            value['state'] = 'released'; atomic_json(target, value)
        except (OSError, ValueError, RuntimeError, release.PublishError):
            remote.echo('Private cache claim retained after uncertain cleanup; recover from its owning machine')
        finally:
            remote.github.stop = operation_stop


def recover(remote, commit, evidence):
    """Explicit same-machine recovery, after all former worker/transports stopped."""
    from .checkpoint_packs import local_writer
    remote.require_private()
    proof = read_json(evidence)
    if (type(proof) is not dict or proof.get('schema') != 1 or proof.get('commit') != commit
            or proof.get('worker_cleanup_complete') is not True or proof.get('transport_release_resolved') is not True):
        raise CheckpointError('Writer recovery requires explicit worker and transport cleanup evidence')
    with local_writer(remote):
        target = claim_path(remote); value = read_json(target)
        if value.get('commit') != commit or value.get('repository') != remote.repository or value.get('game') != remote.game:
            raise CheckpointError('Recovery differs from this machine durable claim')
        current = observe(remote)
        if current and current.get('object', {}).get('sha') != commit:
            raise CheckpointError('Another machine owns the private writer; not removed')
        if current:
            value['state'] = 'releasing'; atomic_json(target, value)
            remote.github.api('git/refs/' + reference(remote), method='DELETE')
        value['state'] = 'released'; atomic_json(target, value)
    return dict(recovered=True)
