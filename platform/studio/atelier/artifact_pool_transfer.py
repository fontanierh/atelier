"""Guarded pool transfers; the parent certifies restoration only after cleanup and capacity close."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import uuid

from . import artifact_pool as pool, artifact_pool_state as state, build_snapshot, paths


def journal_digest(record):
    return hashlib.sha256(json.dumps(record, sort_keys=True).encode()).hexdigest() if record else 'none'


def preflight(action, game, name):
    if action not in ('publish', 'restore', 'abandon') or not state.valid_name(game) or not state.valid_name(name):
        raise ValueError('Invalid pool operation, game or step')
    out = paths.build_root() / game
    cache = paths.cache_dir('artifact-pool', 'v1', create=False)
    marker = out / state.JOURNAL
    record = state.validate(state.read(marker), game=game, step=name, out=out, pool=cache) if os.path.lexists(marker) else None
    build_snapshot.require_complete(out, game=game, pool_resume=record)
    if action == 'abandon':
        if record is None:
            raise ValueError('No incomplete pool transfer to abandon')
        return out, cache, record, None
    ctx, step, current = pool.select(game, name)
    identity = pool.key(ctx, step, current)
    owned = [str(p) for p in pool.roots(ctx, step)]
    if record and (record['action'], record['key'], record['fingerprint'], record['roots']) != (action, identity, current, owned):
        raise ValueError('Pool transfer scope changed; abandon its original partial transfer before starting another')
    return out, cache, record, (ctx, step, current, identity, owned)


def _remove_stage(cache, invocation):
    folder = state.stage(cache, invocation)
    if os.path.lexists(folder):
        if folder.is_symlink() or not folder.is_dir():
            raise ValueError('Pending pool entry must be a regular directory')
        shutil.rmtree(folder)


def _abandon(out, cache, record):
    """Discard only the journal's generated transfer scope; never cache entries or unrelated builds."""
    owned = state.owned_roots(record['roots'])
    destinations = [state.destination(out, root) for root in owned]
    if record['action'] == 'restore':
        stamps = out / 'stamps'
        (stamps / (record['step'] + '.json')).unlink(missing_ok=True)
        if stamps.is_dir():
            state.sync(stamps)
        for destination in destinations:
            if destination.is_dir():
                shutil.rmtree(destination)
            elif destination.exists():
                destination.unlink()
    _remove_stage(cache, record['invocation'])
    (out / state.JOURNAL).unlink()
    state.sync(out)


def execute(action, game, name, *, invocation, expected_key, expected_journal):
    """@cc [owner:fontanierh,label:correctness] guarded-pool-transaction
    A queued transfer MUST revalidate its original source key and journal after admission. Copies
    MUST remain independently owned and fully inventoried. A restore MUST remove its old stamp
    before replacement and leave only staged metadata. Its journal MUST block normal use until
    the parent observes successful guarded execution, cleanup and capacity close. Failed or
    interrupted transfers MUST retain recoverable scope, never a successful restored stamp.
    """
    if (not state.token(invocation) or not state.valid_name(game) or not state.valid_name(name)
            or action not in ('publish', 'restore', 'abandon')):
        raise ValueError('Invalid pool invocation or scope')
    out = paths.build_root() / game
    with state.transaction(out):
        out, cache, previous, selected = preflight(action, game, name)
        if journal_digest(previous) != expected_journal:
            raise ValueError('Pool journal changed while awaiting admission')
        if action == 'abandon':
            _abandon(out, cache, previous)
            print('Discarded the incomplete pool transfer; ordinary incremental build is available.', flush=True)
            return 0
        ctx, step, current, identity, owned = selected
        if identity != expected_key:
            raise ValueError('Pool source context changed while awaiting admission')
        record = dict(schema=1, action=action, game=game, step=name, out=str(out.resolve()), pool=str(cache.resolve()),
                      key=identity, fingerprint=current, roots=owned, invocation=invocation)
        state.validate(record, game=game, step=name, out=out, pool=cache)
        for root in state.owned_roots(owned):
            state.destination(out, root)
        def begin():
            if previous:
                _remove_stage(cache, previous['invocation'])
            state.write(out / state.JOURNAL, record)
        print(f'{action} {name}: verifying and independently copying portable files', flush=True)
        staged = pool.transfer(action, ctx, step, current, cache,
                               staging=state.stage(cache, invocation), begin=begin)
        _, _, _, fresh = preflight(action, game, name)
        if fresh[3] != identity:
            raise ValueError('Source context changed during pool transfer')
        state.write(completion(out, invocation), dict(schema=1, invocation=invocation, action=action, **staged))
        print('Pool file verification complete; parent must certify after guarded cleanup.', flush=True)
    return 0


def completion(out, invocation):
    if not state.token(invocation):
        raise ValueError('Invalid pool invocation')
    return Path(out) / 'logs' / f'pool-transfer-{invocation}.guard' / 'completed.json'


def finalize(action, game, name, invocation):
    """Called only after guarded.run returns 0, including its cleanup and affirmative close."""
    out = paths.build_root() / game
    with state.transaction(out):
        out, cache, record, selected = preflight(action, game, name)
        if record is None or record['invocation'] != invocation or record['action'] != action:
            raise ValueError('Pool completion is no longer this guarded transfer')
        result = state.read(completion(out, invocation))
        if (type(result) is not dict or set(result) != {'schema','invocation','action','key','files','stamp','existing'}
                or type(result['schema']) is not int or result['schema'] != 1 or result['invocation'] != invocation
                or result['action'] != action or result['key'] != record['key'] or type(result['existing']) is not bool
                or type(result['files']) is not dict or not result['files'] or type(result['stamp']) is not dict
                or result['stamp'].get('pool_key') != record['key']
                or result['stamp'].get('fingerprint') != record['fingerprint'] or result['stamp'].get('touched')):
            raise ValueError('Pool completion metadata differs; journal retained')
        if action == 'restore':
            if result['stamp'].get('pooled_from') != record['key']:
                raise ValueError('Pool restore stamp is not bound to this entry')
            state.write(selected[0].stamps / (name + '.json'), result['stamp'])
        else:
            staging = state.stage(cache, invocation)
            if staging.is_symlink() or not staging.is_dir():
                raise ValueError('Pending pool entry must be a regular directory')
            manifest = state.read(staging / 'manifest.json')
            if manifest != dict(key=result['key'], files=result['files'], stamp=result['stamp']):
                raise ValueError('Staged pool manifest differs; journal retained')
            if not result['existing']:
                staging.rename(cache / record['key'])  # A concurrent nonempty entry refuses replacement.
                state.sync(cache)
            else:
                _remove_stage(cache, invocation)
        (out / state.JOURNAL).unlink()
        state.sync(out)
    print(f'{action} {name}: {result["key"]}; independent copies and full file hashes verified', flush=True)


def launch(action, game, name):
    from atelier.harness.safety import guarded
    out, _, record, selected = preflight(action, game, name)
    invocation = uuid.uuid4().hex
    folder = completion(out, invocation).parent
    command = [sys.executable, '-m', 'atelier.artifact_pool_worker', action, game, name, '--invocation', invocation,
               '--expected-key', selected[3] if selected else 'abandon', '--expected-journal', journal_digest(record)]
    print(f'{action} {name}: guarded pool transfer; log {folder / "stdout.log"}', flush=True)
    code = guarded.run(command, folder, kind='job', aggregate_tree=True, timeout=1800, progress=30,
                       purpose=f'portable pool {action} {name}', invocation_id=invocation)
    if code == 0 and action != 'abandon':
        finalize(action, game, name, invocation)
    return code
