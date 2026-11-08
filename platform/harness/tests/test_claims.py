"""Claim service: atomic grants, LFS binding, stale bases, failures, restart and the fail-closed check.

Runs the real HTTP service over a real SQLite file, real Git repositories and an in-process Git LFS lock
server that implements the locking API. No engine or render resources are used.
"""
import os
import shutil
import subprocess
import sys
import threading
from pathlib import Path

import pytest

from atelier.harness.claims import cli as claims_cli
from atelier.harness.claims.client import (AcquireFailed, Change, Client, Refused, Unreachable, acquire, check,
                                           evaluate, release_locks, staged_changes)
from atelier.harness.claims.remote import GitCli, GitLfsCli, LfsHttp, Unavailable
from atelier.harness.claims.scopes import overlaps, scope
from atelier.harness.claims.service import Service
from atelier.harness.claims.store import Store
from claims_fake_lfs import FakeLfs, basic

TOKEN = 'test-token-0123456789abcdef'
BENCH = 'Content/Props/Bench01.uasset'
SEA = 'Content/Shared/M_Sea.uasset'
HARBOUR = 'Content/__ExternalActors__/North/Harbour/'


def git(repo, *argv):
    env = {**os.environ, 'GIT_AUTHOR_NAME': 't', 'GIT_AUTHOR_EMAIL': 't@example.invalid', 'GIT_COMMITTER_NAME': 't',
           'GIT_COMMITTER_EMAIL': 't@example.invalid', 'GIT_TERMINAL_PROMPT': '0'}
    return subprocess.run(['git', '-C', str(repo), *argv], capture_output=True, text=True, check=True, env=env,
                          timeout=30).stdout.strip()


class Clock:
    def __init__(self):
        self.now = 1_000_000.0

    def __call__(self):
        return self.now


class World:
    def __init__(self, tmp):
        self.tmp = tmp
        self.origin = tmp / 'origin.git'
        subprocess.run(['git', 'init', '-q', '--bare', '-b', 'main', str(self.origin)], check=True)
        self.seed = tmp / 'seed'
        subprocess.run(['git', 'clone', '-q', str(self.origin), str(self.seed)], check=True, capture_output=True)
        git(self.seed, 'checkout', '-q', '-b', 'main')
        (self.seed / '.gitattributes').write_text('*.uasset lockable\n*.umap lockable\n')
        for rel in (BENCH, SEA, 'Content/__ExternalActors__/North/Harbour/A1.uasset', 'Source/Skate.cpp'):
            self.write(rel, 'v1')
        self.base = self.commit('seed')
        self.service_repo = tmp / 'service-clone'
        subprocess.run(['git', 'clone', '-q', str(self.origin), str(self.service_repo)], check=True, capture_output=True)
        self.lfs = FakeLfs()
        self.clock = Clock()
        self.db = tmp / 'claims.sqlite'
        self.start()

    def write(self, rel, text):
        path = self.seed / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)

    def commit(self, message, branch='main'):
        git(self.seed, 'add', '-A')
        git(self.seed, 'commit', '-q', '-m', message)
        git(self.seed, 'push', '-q', 'origin', f'HEAD:{branch}')
        return git(self.seed, 'rev-parse', 'HEAD')

    def start(self, reconcile=True):
        self.store = Store(self.db, GitCli(self.service_repo), LfsHttp(self.lfs.url, {'Authorization': basic('service')}),
                           coordinators=['lead'], heartbeat_timeout=60, clock=self.clock)
        self.service = Service(self.store, TOKEN, '127.0.0.1', getattr(self, 'port', 0))
        self.port = self.service.address[1]  # restarts keep the address clients already know
        self.service.start()
        if reconcile:
            self.client('lead').call('POST', '/principals', {'name': 'lead', 'kind': 'human', 'git_account': 'lead'})
            self.client('lead').call('POST', '/reconcile')

    def stop(self):
        self.service.close()
        self.store.close()

    def client(self, actor):
        return Client(self.service.url, TOKEN, actor, timeout=10)

    def agent(self, name, account, machine='m-1'):
        c = self.client(name)
        c.call('POST', '/principals', {'name': name, 'kind': 'agent', 'git_account': account})
        c.call('POST', '/machines', {'id': machine})
        c.call('POST', '/workspaces', {'id': name + '-ws', 'principal': name, 'machine': machine})
        c.locker = LfsHttp(self.lfs.url, {'Authorization': basic(account)})
        return c

    def task(self, c, task, base=None, **extra):
        return c.call('POST', '/tasks', {'id': task, 'title': task, 'workspace': c.actor + '-ws',
                                         'base_revision': base or self.base, **extra})

    def request(self, c, task, **items):
        return c.call('POST', '/claims', {'task': task, 'workspace': c.actor + '-ws', **items})


@pytest.fixture
def world(tmp_path):
    w = World(tmp_path)
    yield w
    w.stop()
    w.lfs.close()


def refused(code, fn, *args, **kwargs):
    with pytest.raises(Refused) as error:
        fn(*args, **kwargs)
    assert error.value.code == code, error.value.payload
    return error.value.payload


def coverage(c, task):
    return c.call('GET', f'/tasks/{task}/coverage')


def test_scope_overlap_rules():
    assert overlaps(('scope', 'region/north'), ('scope', 'region/north/harbour'))
    assert not overlaps(('scope', 'region/north/harbour'), ('scope', 'region/north/market'))
    assert not overlaps(('scope', 'region/north'), ('scope', 'shared/material/M_Sea'))
    assert scope('boundary/south+north') == 'boundary/north+south'
    assert overlaps(('prefix', 'A/B/'), ('path', 'a/b/New.uasset'))
    assert not overlaps(('prefix', 'A/B/'), ('path', 'A/Bc.uasset'))
    assert not overlaps(('scope', 'asset/x'), ('path', 'asset/x'))


def test_authentication_is_required(world):
    for token in ('', 'wrong-token-0123456789'):
        bad = Client(world.service.url, token, 'lead')
        assert refused('unauthorized', bad.call, 'GET', '/status')['message']
    assert world.client('lead').call('GET', '/status')['service'] == 'ready'


@pytest.mark.parametrize('accounts', [('alice', 'bob'), ('team', 'team')], ids=['different-accounts', 'same-account'])
def test_c07_concurrent_requests_yield_exactly_one_active_grant(world, accounts):
    agents = [world.agent(f'agent-{i}', accounts[i % 2]) for i in range(6)]
    for c in agents:
        world.task(c, 'task-' + c.actor)
    barrier, results = threading.Barrier(len(agents)), {}

    def contend(c):
        barrier.wait()
        try:
            results[c.actor] = world.request(c, 'task-' + c.actor, scopes=['asset/prop/bench-01'], lock_paths=[BENCH])
        except Refused as error:
            results[c.actor] = error

    threads = [threading.Thread(target=contend, args=(c,)) for c in agents]
    for t in threads:
        t.start()
    for t in threads:
        t.join(20)
    winners = [name for name, r in results.items() if isinstance(r, dict)]
    assert len(winners) == 1 and len(results) == len(agents)
    assert all(r.code == 'overlap' for r in results.values() if not isinstance(r, dict))
    winner = next(c for c in agents if c.actor == winners[0])
    view = acquire(winner, results[winner.actor]['id'], winner.locker)
    assert view['state'] == 'active' and view['locks'][0]['state'] == 'verified'
    loser = next(c for c in agents if c.actor != winner.actor and c.locker.headers == winner.locker.headers) \
        if accounts[0] == accounts[1] else next(c for c in agents if c.actor != winner.actor)
    # The loser holds no claim, so its check refuses the protected file even when the LFS lock is its account's.
    problems = evaluate([Change('M', BENCH)], {BENCH: 'lockable'}, coverage(loser, 'task-' + loser.actor))
    assert problems and 'not declared' in problems[0]
    assert evaluate([Change('M', BENCH)], {BENCH: 'lockable'}, coverage(winner, 'task-' + winner.actor), 'publish') == []
    assert len(world.lfs.at(BENCH)) == 1


def test_same_account_lock_does_not_grant_ownership(world):
    a, b = world.agent('a', 'team'), world.agent('b', 'team')
    world.task(a, 'ta'), world.task(b, 'tb')
    claim = world.request(a, 'ta', lock_paths=[BENCH])
    acquire(a, claim['id'], a.locker)
    lock_id = world.lfs.at(BENCH)[0]['id']
    # b can reach the same LFS account's lock, but cannot reserve, report or verify it as its own.
    refused('overlap', world.request, b, 'tb', lock_paths=[BENCH])
    refused('not_holder', b.call, 'POST', f'/claims/{claim["id"]}/lock-result',
            {'path': BENCH, 'outcome': 'created', 'lock_id': lock_id})
    refused('not_holder', b.call, 'POST', f'/claims/{claim["id"]}/abort', {'reason': 'steal'})


def test_c08_region_claim_blocks_second_writer_before_filenames_exist(world):
    a, b = world.agent('a', 'alice'), world.agent('b', 'bob')
    world.task(a, 'ta'), world.task(b, 'tb')
    region = world.request(a, 'ta', scopes=['region/north/harbour'], prefixes=[HARBOUR])
    assert acquire(a, region['id'], a.locker)['state'] == 'active'
    new_actor = HARBOUR + 'NewActorNotYetNamed.uasset'
    refused('overlap', world.request, b, 'tb', lock_paths=[new_actor])
    refused('overlap', world.request, b, 'tb', scopes=['region/north'])
    refused('overlap', world.request, b, 'tb', prefixes=['Content/__ExternalActors__/North/'])
    # A sibling region coexists; a region claim does not own the shared material used there.
    assert world.request(b, 'tb', scopes=['region/north/market'], prefixes=['Content/__ExternalActors__/North/Market/'])
    shared = world.request(b, 'tb', scopes=['shared/material/M_Sea'], lock_paths=[SEA])
    assert acquire(b, shared['id'], b.locker)['state'] == 'active'


def test_c09_stale_base_is_refused_until_updated(world):
    a, b = world.agent('a', 'alice'), world.agent('b', 'bob')
    old = world.base
    world.task(a, 'ta')
    claim = world.request(a, 'ta', lock_paths=[BENCH])
    acquire(a, claim['id'], a.locker)
    world.write(BENCH, 'v2 by a')
    merged = world.commit('a edits bench')
    world.client('a').call('POST', '/tasks/ta/merged', {'revision': merged})
    view = release_locks(a, a.call('GET', f'/claims/{claim["id"]}'), a.locker)
    assert view['state'] == 'released' and world.lfs.at(BENCH) == []
    # b starts from the old revision: the lock is free but the base is stale.
    world.task(b, 'tb', base=old)
    payload = refused('stale_base', world.request, b, 'tb', lock_paths=[BENCH])
    assert payload['changed'] == [BENCH]
    b.call('POST', '/tasks/tb/update', {'base_revision': merged})
    assert world.request(b, 'tb', lock_paths=[BENCH])['state'] == 'pending'
    # A changed read dependency also refuses an old base.
    world.task(b, 'tc', base=old, reads=['Content/Props/'])
    refused('stale_base', world.request, b, 'tc', paths=['Source/Skate.cpp'])
    world.task(b, 'td', base='0' * 40)
    refused('stale_base', world.request, b, 'td', paths=['Source/Other.cpp'])


def test_c10_unreachable_service_grants_nothing_and_text_still_passes(world, tmp_path):
    a = world.agent('a', 'alice')
    world.task(a, 'ta')
    claim = world.request(a, 'ta', lock_paths=[BENCH])
    world.stop()
    with pytest.raises(Unreachable):
        acquire(a, claim['id'], a.locker)
    assert world.lfs.at(BENCH) == []  # no lock attempt without a recorded intent
    repo = world.seed
    assert check(a, repo, 'ta', [Change('M', 'Source/Skate.cpp')]) == []
    problems = check(a, repo, 'ta', [Change('M', BENCH)])
    assert problems and 'cannot be verified' in problems[0]
    world.start()


def test_c10_partial_failure_releases_only_proven_own_locks(world):
    a = world.agent('a', 'team')
    bootstrap = world.lfs.add(SEA, 'team')  # pre-existing lock of the same account (another writer's)
    world.task(a, 'ta')
    claim = world.request(a, 'ta', lock_paths=[BENCH, SEA])
    with pytest.raises(AcquireFailed) as failure:
        acquire(a, claim['id'], a.locker)
    view = failure.value.claim
    assert view['state'] == 'failed'
    assert world.lfs.at(BENCH) == []  # created by this attempt: released
    assert [l['id'] for l in world.lfs.at(SEA)] == [bootstrap]  # pre-existing: untouched despite the same account
    assert world.request(a, 'ta', lock_paths=[BENCH])['state'] == 'pending'  # the failed claim reserves nothing


def test_c10_lost_reply_stays_uncertain_and_reserved_until_reconciled(world):
    a, b = world.agent('a', 'alice'), world.agent('b', 'bob')
    world.task(a, 'ta'), world.task(b, 'tb')
    world.lfs.drop_after_create.add(SEA)
    claim = world.request(a, 'ta', lock_paths=[BENCH, SEA])
    with pytest.raises(AcquireFailed) as failure:
        acquire(a, claim['id'], a.locker)
    view = failure.value.claim
    assert view['state'] == 'uncertain'
    assert {l['path']: l['state'] for l in view['locks']} == {BENCH: 'released', SEA: 'uncertain'}
    assert world.lfs.at(BENCH) == [] and len(world.lfs.at(SEA)) == 1
    refused('overlap', world.request, b, 'tb', lock_paths=[SEA])
    result = world.client('lead').call('POST', '/reconcile')
    assert result['changes'] == [{'claim': claim['id'], 'path': SEA, 'from': 'uncertain', 'to': 'releasing',
                                  'lock_id': world.lfs.at(SEA)[0]['id']}]
    view = release_locks(a, a.call('GET', f'/claims/{claim["id"]}'), a.locker)
    assert view['state'] == 'failed' and world.lfs.at(SEA) == []
    assert world.request(b, 'tb', lock_paths=[SEA])['state'] == 'pending'


def test_c10_lfs_unavailable_during_activation_leaves_claim_pending(world):
    a = world.agent('a', 'alice')
    world.task(a, 'ta')
    claim = world.request(a, 'ta', lock_paths=[BENCH])
    a.call('POST', f'/claims/{claim["id"]}/lock-intent', {'path': BENCH})
    made = a.locker.lock(BENCH)
    a.call('POST', f'/claims/{claim["id"]}/lock-result', {'path': BENCH, 'outcome': 'created', 'lock_id': made.lock.id,
                                                          'owner': made.lock.owner})
    world.lfs.down = True
    refused('lfs_unavailable', a.call, 'POST', f'/claims/{claim["id"]}/activate')
    assert a.call('GET', f'/claims/{claim["id"]}')['state'] == 'pending'
    world.lfs.down = False
    assert a.call('POST', f'/claims/{claim["id"]}/activate')['state'] == 'active'


def test_c10_c11_service_lost_after_locking_then_restart_and_reconcile(world):
    a, b = world.agent('a', 'alice'), world.agent('b', 'bob')
    world.task(a, 'ta'), world.task(b, 'tb')
    claim = world.request(a, 'ta', lock_paths=[BENCH])

    class Crashing(LfsHttp):
        def lock(self, path, ref=None):
            result = super().lock(path, ref)
            world.stop()  # the service dies after the lock exists but before the result is reported
            return result

    with pytest.raises(AcquireFailed, match='stays reserved'):
        acquire(a, claim['id'], Crashing(world.lfs.url, {'Authorization': basic('alice')}))
    assert len(world.lfs.at(BENCH)) == 1
    world.start(reconcile=False)
    assert a.call('GET', '/status')['service'] == 'reconciling'
    refused('reconciling', world.request, b, 'tb', lock_paths=['Content/Other.uasset'])
    assert evaluate([Change('M', BENCH)], {BENCH: 'lockable'}, coverage(a, 'ta'))[0].startswith('claims service is reconciling')
    world.client('lead').call('POST', '/reconcile')
    assert {l['path']: l['state'] for l in a.call('GET', f'/claims/{claim["id"]}')['locks']} == {BENCH: 'created'}
    assert acquire(a, claim['id'], a.locker)['state'] == 'active'
    refused('overlap', world.request, b, 'tb', lock_paths=[BENCH])


def test_retry_after_client_crash_resumes_its_own_unreported_lock(world):
    a = world.agent('a', 'team')
    world.task(a, 'ta')
    claim = world.request(a, 'ta', lock_paths=[BENCH])
    a.call('POST', f'/claims/{claim["id"]}/lock-intent', {'path': BENCH})
    made = a.locker.lock(BENCH)  # the client crashes before reporting
    view = acquire(a, claim['id'], a.locker)
    assert view['state'] == 'active' and view['locks'][0]['lock_id'] == made.lock.id
    assert len(world.lfs.at(BENCH)) == 1


def test_c11_claims_survive_restart_heartbeat_expiry_and_need_explicit_recovery(world):
    a, b = world.agent('a', 'team'), world.agent('b', 'bob')
    a2 = world.agent('a2', 'team')
    world.task(a, 'ta'), world.task(b, 'tb')
    claim = world.request(a, 'ta', lock_paths=[BENCH])
    acquire(a, claim['id'], a.locker)
    a.call('POST', '/workspaces/a-ws/heartbeat')
    world.stop()
    world.start(reconcile=False)
    refused('reconciling', world.request, b, 'tb', paths=['Source/Skate.cpp'])
    world.client('lead').call('POST', '/reconcile')
    assert a.call('GET', f'/claims/{claim["id"]}')['state'] == 'active'
    world.clock.now += 3600  # the owner crashed: its heartbeat expires
    assert a.call('GET', '/workspaces/a-ws')['reachable'] is False
    assert a.call('GET', f'/claims/{claim["id"]}')['state'] == 'active'
    refused('overlap', world.request, b, 'tb', lock_paths=[BENCH])
    body = {'action': 'transfer', 'reason': 'a crashed', 'to_workspace': 'a2-ws'}
    refused('not_coordinator', b.call, 'POST', f'/claims/{claim["id"]}/recover',
            {**body, 'old_writer_stopped': True, 'preserved': 'branch a/wip'})
    refused('invalid', world.client('lead').call, 'POST', f'/claims/{claim["id"]}/recover', body)
    moved = world.client('lead').call('POST', f'/claims/{claim["id"]}/recover',
                                      {**body, 'old_writer_stopped': True, 'preserved': 'branch a/wip'})
    assert (moved['principal'], moved['workspace'], moved['state']) == ('a2', 'a2-ws', 'active')
    # The previous holder's checks stop passing: the task's claim now authorizes only its new principal (C04).
    [stale] = check(a, world.seed, 'ta', [Change('M', BENCH)], stage='publish')
    assert stale == f'{BENCH}: claim {claim["id"]} is held by a2, not a'
    assert check(a2, world.seed, 'ta', [Change('M', BENCH)], stage='publish') == []
    events = a.call('GET', '/events?after=0&limit=1000')['events']
    recovery = [e for e in events if e['kind'] == 'claim.recovered'][-1]
    assert recovery['actor'] == 'lead' and recovery['data']['reason'] == 'a crashed'
    assert recovery['data']['preserved'] == 'branch a/wip'
    refused('account_mismatch', world.client('lead').call, 'POST', f'/claims/{claim["id"]}/recover',
            {**body, 'to_workspace': 'b-ws', 'old_writer_stopped': True, 'preserved': 'x'})


def test_reconcile_demotes_a_claim_whose_verified_lock_vanished(world):
    a = world.agent('a', 'alice')
    world.task(a, 'ta')
    claim = world.request(a, 'ta', lock_paths=[BENCH])
    acquire(a, claim['id'], a.locker)
    world.lfs.locks.clear()  # for example an administrator force-unlocked it
    world.client('lead').call('POST', '/reconcile')
    view = a.call('GET', f'/claims/{claim["id"]}')
    assert view['state'] == 'pending' and view['locks'][0]['state'] == 'needed'
    assert acquire(a, claim['id'], a.locker)['state'] == 'active'


def test_c14_check_refuses_undeclared_shared_paths_renames_and_deletions(world):
    a = world.agent('a', 'alice')
    world.task(a, 'ta')
    region = world.request(a, 'ta', scopes=['region/north/harbour'], prefixes=[HARBOUR])
    acquire(a, region['id'], a.locker)
    repo, actor = world.seed, HARBOUR + 'A1.uasset'
    ok = [Change('M', actor), Change('A', HARBOUR + 'New.uasset'), Change('M', 'Source/Skate.cpp')]
    assert check(a, repo, 'ta', ok) == []
    for change in ([Change('M', SEA)], [Change('D', BENCH)], [Change('R', 'Content/Props/Moved.uasset', actor)],
                   [Change('R', actor, BENCH)]):
        problems = check(a, repo, 'ta', change)
        assert problems and 'not declared' in problems[0], change
    assert check(a, repo, None, [Change('M', SEA)])[0].endswith('no task is set')
    assert check(a, repo, 'ta', [Change('M', 'Docs/Note.md')], patterns=['Docs/*']) != []
    # Publication needs exact paths and verified locks, not only the prefix.
    problems = check(a, repo, 'ta', [Change('A', HARBOUR + 'New.uasset')], stage='publish')
    assert 'covered only by a prefix' in problems[0]
    a.call('POST', f'/claims/{region["id"]}/extend', {'lock_paths': [HARBOUR + 'New.uasset']})
    assert acquire(a, region['id'], a.locker)['state'] == 'active'
    assert check(a, repo, 'ta', [Change('A', HARBOUR + 'New.uasset')], stage='publish') == []


def test_staged_changes_include_deletions_and_renames(world):
    repo = world.seed
    git(repo, 'mv', BENCH, 'Content/Props/Bench02.uasset')
    git(repo, 'rm', '-q', SEA)
    changes = staged_changes(repo)
    assert Change('R', 'Content/Props/Bench02.uasset', BENCH) in changes and Change('D', SEA) in changes


def test_c17_pushed_but_unmerged_keeps_the_claim(world):
    a, b = world.agent('a', 'alice'), world.agent('b', 'bob')
    world.task(a, 'ta', branch='a/bench'), world.task(b, 'tb')
    claim = world.request(a, 'ta', lock_paths=[BENCH])
    acquire(a, claim['id'], a.locker)
    world.write(BENCH, 'v2 on a branch')
    pushed = world.commit('bench edit', branch='a/bench')
    git(world.seed, 'reset', '-q', '--hard', world.base)
    a.call('POST', '/tasks/ta/push', {'revision': pushed, 'ok': True})
    a.call('POST', '/tasks/ta/update', {'status': 'review'})
    assert a.call('GET', f'/claims/{claim["id"]}')['state'] == 'active'
    refused('overlap', world.request, b, 'tb', lock_paths=[BENCH])
    refused('not_merged', a.call, 'POST', '/tasks/ta/merged', {'revision': pushed})
    assert a.call('GET', f'/claims/{claim["id"]}')['state'] == 'active' and len(world.lfs.at(BENCH)) == 1
    git(world.seed, 'merge', '-q', '--ff-only', pushed)
    git(world.seed, 'push', '-q', 'origin', 'HEAD:main')
    view = a.call('POST', '/tasks/ta/merged', {'revision': pushed})
    assert view['status'] == 'merged'
    release_locks(a, view['claims'][0], a.locker)
    assert world.lfs.at(BENCH) == []
    b.call('POST', '/tasks/tb/update', {'base_revision': pushed})
    assert world.request(b, 'tb', lock_paths=[BENCH])['state'] == 'pending'


def test_c18_failed_push_leaves_ownership_intact(world):
    a, b = world.agent('a', 'alice'), world.agent('b', 'bob')
    world.task(a, 'ta'), world.task(b, 'tb')
    claim = world.request(a, 'ta', lock_paths=[BENCH])
    acquire(a, claim['id'], a.locker)
    a.call('POST', '/tasks/ta/push', {'revision': 'f' * 40, 'ok': False, 'detail': 'LFS upload failed'})
    assert a.call('GET', f'/claims/{claim["id"]}')['state'] == 'active' and len(world.lfs.at(BENCH)) == 1
    refused('overlap', world.request, b, 'tb', lock_paths=[BENCH])
    kinds = [e['kind'] for e in a.call('GET', '/events?after=0&limit=1000')['events']]
    assert 'task.push_failed' in kinds and 'claim.released' not in kinds
    # Retry: re-verify the claim against the remote before publishing again.
    assert a.call('POST', f'/claims/{claim["id"]}/activate')['state'] == 'active'


def test_cancel_records_disposition_and_releases_only_own_locks(world):
    a = world.agent('a', 'alice')
    world.task(a, 'ta')
    claim = world.request(a, 'ta', lock_paths=[BENCH])
    acquire(a, claim['id'], a.locker)
    refused('invalid', a.call, 'POST', f'/claims/{claim["id"]}/cancel', {})
    view = a.call('POST', f'/claims/{claim["id"]}/cancel', {'disposition': 'preserved', 'note': 'branch kept'})
    assert view['state'] == 'releasing'
    assert release_locks(a, view, a.locker)['state'] == 'released' and world.lfs.at(BENCH) == []


def test_event_cursor_is_durable_and_resumable(world):
    a = world.agent('a', 'alice')
    first = a.call('GET', '/events?after=0&limit=1000')
    world.task(a, 'ta')
    later = a.call('GET', f'/events?after={first["cursor"]}')
    assert [e['kind'] for e in later['events']] == ['task.created'] and later['cursor'] > first['cursor']
    world.stop()
    world.start(reconcile=False)
    again = a.call('GET', f'/events?after={first["cursor"]}')
    assert again['events'][0] == later['events'][0]


def test_only_one_service_opens_the_database(world):
    with pytest.raises(RuntimeError, match='already owns'):
        Store(world.db, None, None)


def test_check_command_fails_closed_and_passes_text_without_service(world, monkeypatch, capsys):
    monkeypatch.chdir(world.seed)
    monkeypatch.setenv('ATELIER_CLAIMS_TOKEN', TOKEN)
    args = claims_cli_args('--url', 'http://127.0.0.1:9', '--actor', 'a', 'check', '--task', 'ta',
                           '--paths', 'Source/Skate.cpp')
    assert claims_cli.main(args) == 0
    args = claims_cli_args('--url', 'http://127.0.0.1:9', '--actor', 'a', 'check', '--task', 'ta', '--paths', BENCH)
    assert claims_cli.main(args) == 1
    assert 'cannot be verified' in capsys.readouterr().err


def claims_cli_args(*argv):
    from atelier.cli import make_parser
    return make_parser().parse_args(['claims', *argv])


@pytest.mark.parametrize('command, seconds', [(['reconcile'], 300), (['reconcile', '--timeout', '900'], 900),
                                              (['status'], 30)])
def test_reconcile_timeout_reaches_the_transport_without_changing_other_commands(monkeypatch, command, seconds):
    import io
    from atelier.harness.claims import client as claims_client

    seen = []

    def respond(request, timeout):
        seen.append((request.full_url, timeout))
        return io.BytesIO(b'{"state": "ready"}')

    monkeypatch.setenv('ATELIER_CLAIMS_TOKEN', TOKEN)
    monkeypatch.setattr(claims_client.urllib.request, 'urlopen', respond)
    args = claims_cli_args('--url', 'http://127.0.0.1:8840', '--actor', 'lead', *command)
    assert claims_cli.main(args) == 0
    assert seen == [(args.url + '/' + command[0], seconds)]


@pytest.mark.parametrize('command, seconds', [(['status'], 300.0), (['reconcile', '--timeout', '900'], 900)])
def test_claims_timeout_env_raises_the_default_wait(monkeypatch, command, seconds):
    import io
    from atelier.harness.claims import client as claims_client

    seen = []
    monkeypatch.setenv('ATELIER_CLAIMS_TOKEN', TOKEN)
    monkeypatch.setenv('ATELIER_CLAIMS_TIMEOUT', '300')
    monkeypatch.setattr(claims_client.urllib.request, 'urlopen',
                        lambda request, timeout: seen.append(timeout) or io.BytesIO(b'{"state": "ready"}'))
    assert claims_cli.main(claims_cli_args('--url', 'http://127.0.0.1:8840', '--actor', 'lead', *command)) == 0
    assert seen == [seconds]


def test_a_bad_claims_timeout_env_is_refused(monkeypatch):
    monkeypatch.setenv('ATELIER_CLAIMS_TOKEN', TOKEN)
    monkeypatch.setenv('ATELIER_CLAIMS_TIMEOUT', 'soon')
    with pytest.raises(SystemExit, match='ATELIER_CLAIMS_TIMEOUT'):
        claims_cli.main(claims_cli_args('--url', 'http://127.0.0.1:8840', '--actor', 'lead', 'status'))


@pytest.mark.parametrize('seconds', ['0', '-1', 'nan', 'inf'])
def test_reconcile_timeout_must_be_finite_and_positive(seconds):
    with pytest.raises(SystemExit):
        claims_cli_args('reconcile', '--timeout', seconds)


@pytest.mark.skipif(shutil.which('git-lfs') is None, reason='git-lfs is not installed')
def test_cli_acquire_uses_git_lfs_with_its_own_credentials(world, monkeypatch, capsys):
    a = world.agent('a', 'alice')
    world.task(a, 'ta')
    work = world.tmp / 'work-a'
    subprocess.run(['git', 'clone', '-q', str(world.origin), str(work)], check=True, capture_output=True)
    git(work, 'config', 'lfs.url', world.lfs.url + '/info/lfs')
    git(work, 'config', 'http.extraHeader', 'Authorization: ' + basic('alice'))
    monkeypatch.setenv('ATELIER_CLAIMS_TOKEN', TOKEN)
    common = ['--url', world.service.url, '--actor', 'a', '--repo', str(work)]
    assert claims_cli.main(claims_cli_args(*common, 'request', '--task', 'ta', '--workspace', 'a-ws',
                                           '--lock-path', BENCH, '--acquire')) == 0
    assert world.lfs.at(BENCH)[0]['owner']['name'] == 'alice'
    assert claims_cli.main(claims_cli_args(*common, 'check', '--task', 'ta', '--paths', BENCH, '--stage', 'publish')) == 0
    claim = a.call('GET', '/tasks/ta')['claims'][0]['id']
    assert claims_cli.main(claims_cli_args(*common, 'cancel', str(claim), '--disposition', 'discarded')) == 0
    assert world.lfs.at(BENCH) == []
    assert GitLfsCli(work).locks() == []


def test_repository_hooks_skip_without_task_and_fail_closed_with_one(world):
    """The committed hooks: no task set means no claims check; with a task, protected staged files need the
    service while text passes. Runs the real shell hooks in a checkout that mounts this platform tree."""
    from atelier import paths
    repo = world.seed
    (repo / 'platform').mkdir()
    for part in ('studio', 'harness'):
        (repo / 'platform' / part).symlink_to(paths.PLATFORM / part)
    (repo / '.git' / 'info' / 'exclude').write_text('platform/\n')
    hook = paths.PLATFORM / 'harness' / 'harness' / 'claims' / 'hooks' / 'pre-commit'
    env = {**os.environ, 'ATELIER_PYTHON': sys.executable,
           'ATELIER_CLAIMS_URL': 'http://127.0.0.1:9', 'ATELIER_CLAIMS_TOKEN': TOKEN, 'ATELIER_CLAIMS_ACTOR': 'a'}

    def run():
        return subprocess.run([str(hook)], cwd=repo, env=env, capture_output=True, text=True, timeout=30)

    world.write(BENCH, 'edited')
    git(repo, 'add', BENCH)
    assert run().returncode == 0  # no task: the hook does nothing
    (Path(git(repo, 'rev-parse', '--absolute-git-dir')) / 'atelier-claims-task').write_text('ta\n')
    result = run()
    assert result.returncode == 1 and 'cannot be verified' in result.stderr
    git(repo, 'reset', '-q', BENCH)
    world.write('Source/Skate.cpp', 'text edit')
    git(repo, 'add', 'Source/Skate.cpp')
    assert run().returncode == 0


class Unanswered(LfsHttp):
    """A lock request whose reply never came and which made no lock (yet): the outcome is unknown."""

    def lock(self, path, ref=None):
        from atelier.harness.claims.remote import LockResult
        return LockResult('unknown', detail='timed out')


def test_protected_checks_reverify_locks_and_base_live(world):
    a = world.agent('a', 'alice')
    world.task(a, 'ta')
    claim = world.request(a, 'ta', lock_paths=[BENCH])
    acquire(a, claim['id'], a.locker)
    repo = world.seed
    for stage in ('commit', 'publish'):
        assert check(a, repo, 'ta', [Change('M', BENCH)], stage=stage) == []
    # LFS unreachable after activation: the stored coverage is not enough.
    world.lfs.down = True
    for stage in ('commit', 'publish'):
        problems = check(a, repo, 'ta', [Change('M', BENCH)], stage=stage)
        assert problems and 'lfs_unavailable' in problems[0], problems
    world.lfs.down = False
    # Git remote unreachable.
    moved = world.origin.with_name('origin-away.git')
    world.origin.rename(moved)
    try:
        for stage in ('commit', 'publish'):
            problems = check(a, repo, 'ta', [Change('M', BENCH)], stage=stage)
            assert problems and 'git_unavailable' in problems[0], problems
    finally:
        moved.rename(world.origin)
    assert check(a, repo, 'ta', [Change('M', BENCH)]) == []
    # The lock vanished from the remote (no reconcile ran): the claim no longer authorizes the write.
    world.lfs.locks.clear()
    problems = check(a, repo, 'ta', [Change('M', BENCH)])
    assert problems and 'live verification' in problems[0], problems
    assert check(a, repo, 'ta', [Change('M', 'Source/Skate.cpp')]) == []  # unprotected text still passes


def test_changed_paths_of_a_large_claim_are_listed_in_bounded_diffs(world, monkeypatch):
    from atelier.harness.claims import remote
    base = git(world.seed, 'rev-parse', 'HEAD')
    for name in 'abcde':
        world.write(f'Content/{name}.txt', name)
    head = world.commit('five files')
    items = [('path', f'Content/{name}.txt') for name in 'abcdef'] + [('prefix', 'Other/')]
    cli = GitCli(world.service_repo)
    cli.head('main')
    whole = cli.changed(base, head, items)
    monkeypatch.setattr(remote, 'DIFF_SPECS', 2)
    assert cli.changed(base, head, items) == whole == [f'Content/{name}.txt' for name in 'abcde']


def test_unseen_uncertain_lock_keeps_its_reservation_until_settled(world):
    a, b = world.agent('a', 'alice'), world.agent('b', 'bob')
    world.task(a, 'ta'), world.task(b, 'tb')
    claim = world.request(a, 'ta', lock_paths=[SEA])
    with pytest.raises(AcquireFailed):
        acquire(a, claim['id'], Unanswered(world.lfs.url, {'Authorization': basic('alice')}))
    assert a.call('GET', f'/claims/{claim["id"]}')['state'] == 'uncertain'
    # No lock is listed yet, but the timed-out request may still create it: stay uncertain and reserved.
    world.client('lead').call('POST', '/reconcile')
    view = a.call('GET', f'/claims/{claim["id"]}')
    assert view['state'] == 'uncertain' and view['locks'][0]['state'] == 'uncertain'
    refused('overlap', world.request, b, 'tb', lock_paths=[SEA])
    # The late lock lands: reconcile proves it is the attempt's and releases it.
    late = world.lfs.add(SEA, 'alice')
    result = world.client('lead').call('POST', '/reconcile')
    assert [c['to'] for c in result['changes']] == ['releasing']
    view = release_locks(a, a.call('GET', f'/claims/{claim["id"]}'), a.locker)
    assert view['state'] == 'failed' and world.lfs.at(SEA) == [] and late
    assert world.request(b, 'tb', lock_paths=[SEA])['state'] == 'pending'


def test_unseen_uncertain_lock_settles_only_after_the_settle_interval(world):
    a, b = world.agent('a', 'alice'), world.agent('b', 'bob')
    world.task(a, 'ta'), world.task(b, 'tb')
    claim = world.request(a, 'ta', lock_paths=[SEA])
    with pytest.raises(AcquireFailed):
        acquire(a, claim['id'], Unanswered(world.lfs.url, {'Authorization': basic('alice')}))
    world.clock.now += world.store.uncertain_settle - 1
    world.client('lead').call('POST', '/reconcile')
    assert a.call('GET', f'/claims/{claim["id"]}')['state'] == 'uncertain'
    world.clock.now += 2
    world.client('lead').call('POST', '/reconcile')
    view = a.call('GET', f'/claims/{claim["id"]}')
    assert view['state'] == 'failed' and view['locks'][0]['state'] == 'abandoned'
    other = world.request(b, 'tb', lock_paths=[SEA])
    # Against every bound, A's request lands after B reserved the path. Reconcile proves the lock is A's (A's
    # account, absent from A's snapshot, no other attempt by that account) and has A unlock it, while A stays
    # ended and B alone holds the path.
    world.lfs.add(SEA, 'alice')
    world.client('lead').call('POST', '/reconcile')
    view = a.call('GET', f'/claims/{claim["id"]}')
    assert view['state'] == 'failed' and view['locks'][0]['state'] == 'releasing'
    assert holding(world, SEA) == [other['id']]
    release_locks(a, view, a.locker)
    assert world.lfs.at(SEA) == []
    assert acquire(b, other['id'], b.locker)['state'] == 'active'


def test_adoption_never_takes_a_lock_from_the_intent_snapshot(world):
    a = world.agent('a', 'team')
    lead = world.client('lead')
    bootstrap = world.lfs.add(SEA, 'team')  # another writer's lock under the same account
    world.task(a, 'ta')
    claim = world.request(a, 'ta', lock_paths=[SEA])
    assert a.call('POST', f'/claims/{claim["id"]}/lock-intent', {'path': SEA})['prior'] == [bootstrap]
    a.call('POST', f'/claims/{claim["id"]}/lock-result', {'path': SEA, 'outcome': 'unknown'})
    a.call('POST', f'/claims/{claim["id"]}/abort', {'reason': 'lock outcome unknown'})
    body = {'action': 'resolve', 'path': SEA, 'decision': 'adopt', 'lock_id': bootstrap, 'reason': 'looks like ours'}
    refused('pre_existing', lead.call, 'POST', f'/claims/{claim["id"]}/recover', body)
    view = release_locks(a, a.call('GET', f'/claims/{claim["id"]}'), a.locker)
    assert view['locks'][0]['state'] == 'uncertain'
    assert [l['id'] for l in world.lfs.at(SEA)] == [bootstrap]
    # The explicit bootstrap handover still works: a live claim that never attempted the path adopts it.
    world.task(a, 'tb')
    handover = world.request(a, 'tb', lock_paths=[BENCH])
    held = world.lfs.add(BENCH, 'team')
    lead.call('POST', f'/claims/{handover["id"]}/recover', {**body, 'path': BENCH, 'lock_id': held})
    assert acquire(a, handover['id'], a.locker)['state'] == 'active'


def test_resolution_never_revives_an_ended_claim_whose_path_another_claim_holds(world):
    a, b = world.agent('a', 'alice'), world.agent('b', 'bob')
    lead = world.client('lead')
    world.task(a, 'ta'), world.task(b, 'tb')
    claim = world.request(a, 'ta', lock_paths=[SEA])
    a.call('POST', f'/claims/{claim["id"]}/lock-intent', {'path': SEA})
    a.call('POST', f'/claims/{claim["id"]}/lock-result', {'path': SEA, 'outcome': 'unknown'})
    a.call('POST', f'/claims/{claim["id"]}/abort', {'reason': 'lock outcome unknown'})
    lead.call('POST', f'/claims/{claim["id"]}/recover', {'action': 'resolve', 'path': SEA, 'decision': 'foreign',
                                                          'reason': 'request confirmed dead'})
    assert a.call('GET', f'/claims/{claim["id"]}')['state'] == 'failed'
    other = world.request(b, 'tb', lock_paths=[SEA])
    late = world.lfs.add(SEA, 'alice')  # A's request lands after all
    body = {'action': 'resolve', 'path': SEA, 'decision': 'adopt', 'lock_id': late, 'reason': 'late lock'}
    refused('lock_state', lead.call, 'POST', f'/claims/{claim["id"]}/recover', body)  # refused: no lock was made
    # Same story, but the attempt was left unresolved (uncertain), so the late lock is provably A's.
    world.lfs.locks.clear()
    b.call('POST', f'/claims/{other["id"]}/cancel', {'disposition': 'discarded'})
    claim = world.request(a, 'ta', lock_paths=[SEA])
    a.call('POST', f'/claims/{claim["id"]}/lock-intent', {'path': SEA})
    a.call('POST', f'/claims/{claim["id"]}/lock-result', {'path': SEA, 'outcome': 'unknown'})
    a.call('POST', f'/claims/{claim["id"]}/abort', {'reason': 'lock outcome unknown'})
    world.clock.now += world.store.uncertain_settle + 1
    lead.call('POST', '/reconcile')
    assert a.call('GET', f'/claims/{claim["id"]}')['state'] == 'failed'
    other = world.request(b, 'tb', lock_paths=[SEA])
    late = world.lfs.add(SEA, 'alice')
    view = lead.call('POST', f'/claims/{claim["id"]}/recover', {**body, 'lock_id': late})
    assert view['state'] == 'failed' and view['locks'][0]['state'] == 'releasing'
    assert holding(world, SEA) == [other['id']]
    release_locks(a, view, a.locker)
    assert world.lfs.at(SEA) == [] and acquire(b, other['id'], b.locker)['state'] == 'active'


def test_late_lock_is_not_proven_when_another_attempt_by_the_same_account_could_own_it(world):
    a, b = world.agent('a', 'team'), world.agent('b', 'team')
    lead = world.client('lead')
    world.task(a, 'ta'), world.task(b, 'tb')
    claim = world.request(a, 'ta', lock_paths=[SEA])
    with pytest.raises(AcquireFailed):
        acquire(a, claim['id'], Unanswered(world.lfs.url, {'Authorization': basic('team')}))
    world.clock.now += world.store.uncertain_settle + 1
    lead.call('POST', '/reconcile')
    other = world.request(b, 'tb', lock_paths=[SEA])
    b.call('POST', f'/claims/{other["id"]}/lock-intent', {'path': SEA})
    late = world.lfs.add(SEA, 'team')  # A's late lock, or B's own: the account cannot tell
    body = {'action': 'resolve', 'path': SEA, 'decision': 'adopt', 'lock_id': late, 'reason': 'late lock'}
    refused('ambiguous', lead.call, 'POST', f'/claims/{claim["id"]}/recover', body)
    lead.call('POST', '/reconcile')
    assert a.call('GET', f'/claims/{claim["id"]}')['locks'][0]['state'] == 'abandoned'
    assert b.call('GET', f'/claims/{other["id"]}')['locks'][0]['state'] == 'requested'
    assert [l['id'] for l in world.lfs.at(SEA)] == [late]


def holding(world, path):
    """IDs of claims in a holding state with an item overlapping the path (the one-active-writer invariant)."""
    from atelier.harness.claims.store import HOLDING
    with world.store.lock:
        rows = world.store.db.execute('SELECT c.id, i.kind, i.value FROM claims c JOIN items i ON i.claim=c.id '
                                      f'WHERE c.state IN ({",".join("?" * len(HOLDING))})', HOLDING).fetchall()
    return sorted({r['id'] for r in rows if overlaps(('path', path), (r['kind'], r['value']))})


class Failing(LfsHttp):
    """A lock request that certainly made no lock (for example a 403)."""

    def lock(self, path, ref=None):
        from atelier.harness.claims.remote import LockResult
        return LockResult('failed', detail='403: denied')


def test_retry_never_discards_an_earlier_unsettled_attempt(world):
    a, b = world.agent('a', 'alice'), world.agent('b', 'bob')
    world.task(a, 'ta'), world.task(b, 'tb')
    claim = world.request(a, 'ta', lock_paths=[SEA])
    # The first attempt recorded its intent and the client was interrupted: its lock request may still land.
    a.call('POST', f'/claims/{claim["id"]}/lock-intent', {'path': SEA})
    # A retry whose own request certainly fails must not abort the claim and free the path.
    with pytest.raises(AcquireFailed, match='unsettled'):
        acquire(a, claim['id'], Failing(world.lfs.url, {'Authorization': basic('alice')}))
    view = a.call('GET', f'/claims/{claim["id"]}')
    assert view['state'] == 'pending' and view['locks'][0]['state'] == 'requested'
    refused('overlap', world.request, b, 'tb', lock_paths=[SEA])
    # Same for an attempt reported unknown on a claim that was not aborted.
    other = world.request(a, 'ta', lock_paths=[BENCH])
    a.call('POST', f'/claims/{other["id"]}/lock-intent', {'path': BENCH})
    a.call('POST', f'/claims/{other["id"]}/lock-result', {'path': BENCH, 'outcome': 'unknown'})
    refused('unsettled', a.call, 'POST', f'/claims/{other["id"]}/lock-intent', {'path': BENCH})
    # Once the settle interval passed with no lock on the remote, the retry proceeds.
    world.clock.now += world.store.uncertain_settle + 1
    assert acquire(a, claim['id'], a.locker)['state'] == 'active'
    assert acquire(a, other['id'], a.locker)['state'] == 'active'


class Interleaved:
    """An LFS verifier that runs ``during`` right after its first listing returns, before the caller applies it."""

    def __init__(self, inner, during):
        self.inner, self.during = inner, during

    def locks(self, path=None, lock_id=None):
        found = self.inner.locks(path=path, lock_id=lock_id)
        during, self.during = self.during, None
        if during:
            during()
        return found


@pytest.mark.parametrize('bulk', [False, True])
def test_reconcile_discards_a_listing_that_a_fresh_attempt_made_stale(world, monkeypatch, bulk):
    monkeypatch.setattr('atelier.harness.claims.store.LIST_ALL_LOCKS_ABOVE', 0 if bulk else 20)
    a, b = world.agent('a', 'alice'), world.agent('b', 'bob')
    world.task(a, 'ta'), world.task(b, 'tb')
    claim = world.request(a, 'ta', lock_paths=[SEA])
    a.call('POST', f'/claims/{claim["id"]}/lock-intent', {'path': SEA})
    a.call('POST', f'/claims/{claim["id"]}/lock-result', {'path': SEA, 'outcome': 'unknown'})
    world.clock.now += world.store.uncertain_settle + 1  # the first attempt is old enough to settle

    def retry():  # a permitted retry starts, its request times out, and the claim is aborted
        a.call('POST', f'/claims/{claim["id"]}/lock-intent', {'path': SEA})
        a.call('POST', f'/claims/{claim["id"]}/lock-result', {'path': SEA, 'outcome': 'unknown'})
        a.call('POST', f'/claims/{claim["id"]}/abort', {'reason': 'lock outcome unknown'})

    world.store.lfs = Interleaved(world.store.lfs, retry)
    result = world.store.reconcile('lead')  # listed before the retry, applied after it
    assert result['changes'] == []
    view = a.call('GET', f'/claims/{claim["id"]}')
    assert view['state'] == 'uncertain' and view['locks'][0]['state'] == 'uncertain'
    refused('overlap', world.request, b, 'tb', lock_paths=[SEA])  # the fresh request may still land


def test_resolution_and_unlock_discard_stale_listings(world):
    a = world.agent('a', 'alice')
    lead = world.client('lead')
    world.task(a, 'ta')
    claim = world.request(a, 'ta', lock_paths=[SEA])
    a.call('POST', f'/claims/{claim["id"]}/lock-intent', {'path': SEA})
    a.call('POST', f'/claims/{claim["id"]}/lock-result', {'path': SEA, 'outcome': 'unknown'})
    late = world.lfs.add(SEA, 'alice')
    world.clock.now += world.store.uncertain_settle + 1

    def retry():  # the attempt is replaced (resumed onto the late lock) while the coordinator's read is in flight
        a.call('POST', f'/claims/{claim["id"]}/lock-intent', {'path': SEA})

    world.store.lfs = Interleaved(world.store.lfs, retry)
    body = {'action': 'resolve', 'path': SEA, 'decision': 'adopt', 'lock_id': late, 'reason': 'late lock'}
    refused('lock_state', lead.call, 'POST', f'/claims/{claim["id"]}/recover', body)
    assert a.call('GET', f'/claims/{claim["id"]}')['locks'][0]['state'] == 'created'


class TrackingLocker:
    """Wraps a locker and records how many lock requests were in flight at once."""

    def __init__(self, inner, concurrent=True):
        self.inner, self.concurrent, self.now, self.peak, self.guard = inner, concurrent, 0, 0, threading.Lock()

    def lock(self, path, ref=None):
        with self.guard:
            self.now += 1
            self.peak = max(self.peak, self.now)
        try:
            threading.Event().wait(0.02)   # a remote round trip
            return self.inner.lock(path, ref=ref)
        finally:
            with self.guard:
                self.now -= 1

    def __getattr__(self, name):
        return getattr(self.inner, name)


def test_reconcile_uses_all_pages_and_keeps_unrelated_locks(world, monkeypatch):
    a = world.agent('a', 'alice')
    world.task(a, 'ta')
    paths = [f'{HARBOUR}Actor{i:02}.uasset' for i in range(30)]
    # Put other owners' locks on the early pages: reconciliation must finish the listing, not infer absence.
    unrelated = [world.lfs.add(f'Other/Actor{i}.uasset', 'bob') for i in range(205)]
    claim = world.request(a, 'ta', lock_paths=paths)
    view = acquire(a, claim['id'], a.locker)
    a.locker.unlock(view['locks'][0]['lock_id'])
    requested, real = [], world.store.lfs._call

    def listing(method, path, body=None, query=None):
        requested.append(query)
        return real(method, path, body, query)

    monkeypatch.setattr(world.store.lfs, '_call', listing)
    result = world.store.reconcile('lead')
    assert result['checked'] == 30
    assert len(result['changes']) == 1 and result['changes'][0]['to'] == 'lost'
    assert [q.get('cursor') for q in requested] == [None, '100', '200']
    assert all('path' not in q for q in requested)   # three pages, not thirty path queries
    assert all(lock_id in world.lfs.locks for lock_id in unrelated)
    current = a.call('GET', f'/claims/{claim["id"]}')
    assert current['state'] == 'pending'
    assert sum(l['state'] == 'verified' for l in current['locks']) == 29


def test_failed_bulk_reconcile_preserves_state_and_can_be_retried(world, monkeypatch):
    a = world.agent('a', 'alice')
    world.task(a, 'ta')
    paths = [f'{HARBOUR}Actor{i:02}.uasset' for i in range(30)]
    claim = world.request(a, 'ta', lock_paths=paths)
    acquire(a, claim['id'], a.locker)
    for i in range(100):
        world.lfs.add(f'Other/Actor{i}.uasset', 'bob')
    world.stop()
    world.start(reconcile=False)
    before = a.call('GET', f'/claims/{claim["id"]}')
    real = world.store.lfs._call

    def fail_later_page(method, path, body=None, query=None):
        if query and query.get('cursor'):
            raise Unavailable('temporary failure after the first page')
        return real(method, path, body, query)

    monkeypatch.setattr(world.store.lfs, '_call', fail_later_page)
    refused('lfs_unavailable', world.client('lead').call, 'POST', '/reconcile')
    assert not world.store.ready
    assert a.call('GET', f'/claims/{claim["id"]}') == before
    monkeypatch.setattr(world.store.lfs, '_call', real)
    assert world.client('lead').call('POST', '/reconcile')['state'] == 'ready'
    assert a.call('GET', f'/claims/{claim["id"]}') == before


def test_many_locks_are_acquired_concurrently_and_verified_against_one_listing(world):
    a = world.agent('a', 'alice')
    world.task(a, 'ta')
    paths = [f'{HARBOUR}Actor{i:02}.uasset' for i in range(30)]
    claim = world.request(a, 'ta', lock_paths=paths)
    listed, real = [], world.store.lfs.locks
    world.store.lfs.locks = lambda path=None, lock_id=None: listed.append(path) or real(path=path, lock_id=lock_id)
    locker = TrackingLocker(a.locker)
    view = acquire(a, claim['id'], locker)
    assert view['state'] == 'active' and {l['state'] for l in view['locks']} == {'verified'}
    assert all(len(world.lfs.at(p)) == 1 for p in paths)
    assert 1 < locker.peak <= 8                      # concurrent, bounded by LOCK_WORKERS
    assert sorted(p for p in listed if p) == sorted(paths)   # one intent snapshot per path
    assert listed.count(None) == 1                    # activation: one listing for all 30 locks


def test_a_failure_among_concurrent_locks_releases_only_this_attempt_s_locks(world):
    a = world.agent('a', 'team')
    paths = [f'{HARBOUR}Actor{i:02}.uasset' for i in range(30)]
    other = world.lfs.add(paths[13], 'team')   # another writer's lock of the same account, mid-list
    world.task(a, 'ta')
    claim = world.request(a, 'ta', lock_paths=paths)
    with pytest.raises(AcquireFailed) as failure:
        acquire(a, claim['id'], TrackingLocker(a.locker))
    assert failure.value.claim['state'] == 'failed'
    assert all(world.lfs.at(p) == [] for p in paths if p != paths[13])   # every lock this attempt made: released
    assert [l['id'] for l in world.lfs.at(paths[13])] == [other]          # the pre-existing one: untouched


def test_a_locker_not_safe_to_run_concurrently_locks_one_path_at_a_time(world):
    # A request queued after its intent was recorded could create its lock after reconciliation released the path.
    a = world.agent('a', 'alice')
    world.task(a, 'ta')
    paths = [f'{HARBOUR}Actor{i:02}.uasset' for i in range(10)]
    claim = world.request(a, 'ta', lock_paths=paths)
    locker = TrackingLocker(a.locker, concurrent=False)
    assert acquire(a, claim['id'], locker)['state'] == 'active'
    assert locker.peak == 1


def test_many_locks_are_released_concurrently(world):
    a = world.agent('a', 'alice')
    world.task(a, 'ta')
    paths = [f'{HARBOUR}Actor{i:02}.uasset' for i in range(30)]
    claim = world.request(a, 'ta', lock_paths=paths)
    acquire(a, claim['id'], a.locker)
    view = a.call('POST', f'/claims/{claim["id"]}/cancel', {'disposition': 'discarded', 'note': 'test'})
    unlocks, real = [], a.locker.unlock
    peak = {'now': 0, 'max': 0}
    guard = threading.Lock()

    def unlock(lock_id, ref=None):
        with guard:
            peak['now'] += 1
            peak['max'] = max(peak['max'], peak['now'])
        try:
            threading.Event().wait(0.02)
            unlocks.append(lock_id)
            return real(lock_id, ref=ref)
        finally:
            with guard:
                peak['now'] -= 1
    a.locker.unlock = unlock
    a.locker.concurrent = True
    view = release_locks(a, view, a.locker)
    assert len(unlocks) == 30 and 1 < peak['max'] <= 8
    assert all(world.lfs.at(p) == [] for p in paths)
    assert {l['state'] for l in view['locks']} == {'released'}


def test_the_client_locker_reads_the_lfs_endpoint_and_git_credential():
    from atelier.harness.claims.remote import basic_auth, lfs_endpoint
    env = ('git-lfs/3.6.1\nEndpoint=https://github.com/o/r.git/info/lfs (auth=basic)\n'
           'Endpoint (fork)=https://github.com/f/r.git/info/lfs (auth=none)\nLocalWorkingDir=/w\n')
    assert lfs_endpoint(env) == 'https://github.com/o/r.git/info/lfs'
    assert lfs_endpoint(env, 'fork') == 'https://github.com/f/r.git/info/lfs'
    assert lfs_endpoint(env, 'other') is None
    assert basic_auth('protocol=https\nhost=github.com\nusername=u\npassword=p=q\n') == 'Basic dTpwPXE='
    assert basic_auth('protocol=https\nhost=github.com\n') is None


def test_the_git_lfs_command_locker_never_runs_two_lock_commands_at_once(tmp_path, monkeypatch):
    import time
    from concurrent.futures import ThreadPoolExecutor
    running, peak, guard = [0], [0], threading.Lock()

    def run(self, *argv):
        with guard:
            running[0] += 1
            peak[0] = max(peak[0], running[0])
        time.sleep(0.02)
        with guard:
            running[0] -= 1
        return subprocess.CompletedProcess(argv, 0, '', '')

    monkeypatch.setattr(GitLfsCli, '_run', run)
    cli = GitLfsCli(tmp_path)
    with ThreadPoolExecutor(8) as pool:
        list(pool.map(lambda i: cli.unlock(str(i)), range(16)))
    assert peak[0] == 1


def test_a_lock_request_that_never_left_is_retried_then_failed_not_unknown(monkeypatch):
    """A DNS failure or refused connection proves no lock was made: retry it, and never leave it uncertain."""
    import socket
    import urllib.error
    from atelier.harness.claims import remote
    calls = []

    def unresolved(self, method, path, body=None, query=None):
        calls.append(method)
        raise remote.Unavailable('no name') from urllib.error.URLError(socket.gaierror(8, 'nodename nor servname'))
    monkeypatch.setattr(remote.LfsHttp, '_call', unresolved)
    result = remote.LfsHttp('http://lfs.invalid').lock('a.uasset', backoff=0)
    assert result.outcome == 'failed' and result.detail.startswith('not sent') and calls == ['POST'] * 3

    answers = iter([urllib.error.URLError(ConnectionRefusedError()), None])

    def flaky(self, method, path, body=None, query=None):
        error = next(answers)
        if error:
            raise remote.Unavailable('refused') from error
        return 201, {'lock': {'id': '7', 'path': 'a.uasset', 'owner': {'name': 'alice'}}}
    monkeypatch.setattr(remote.LfsHttp, '_call', flaky)
    assert remote.LfsHttp('http://lfs.invalid').lock('a.uasset', backoff=0).outcome == 'created'

    def timed_out(self, method, path, body=None, query=None):
        raise remote.Unavailable('slow') from TimeoutError('timed out')
    monkeypatch.setattr(remote.LfsHttp, '_call', timed_out)
    assert remote.LfsHttp('http://lfs.invalid').lock('a.uasset', backoff=0).outcome == 'unknown'


class Counting:
    """Counts the remote reads a store makes through ``inner``."""

    def __init__(self, inner, counts, name):
        self.inner, self.counts, self.name = inner, counts, name

    def __getattr__(self, attr):
        method = getattr(self.inner, attr)

        def counted(*args, **kwargs):
            key = f'{self.name}.{attr}' + ('.all' if attr == 'locks' and not args and not kwargs else '')
            self.counts[key] = self.counts.get(key, 0) + 1
            return method(*args, **kwargs)
        return counted


def test_a_check_reads_the_remotes_once_for_all_claims_of_its_task(world, monkeypatch):
    """A task holding several claims is verified with one lock listing and one target-branch read per check, and
    every claim is still verified (a lock missing from the remote still fails its claim)."""
    monkeypatch.setattr('atelier.harness.claims.store.LIST_ALL_LOCKS_ABOVE', 0)
    a = world.agent('a', 'alice')
    world.task(a, 'ta')
    one = world.request(a, 'ta', scopes=['asset/prop/bench-01'], lock_paths=[BENCH])
    two = world.request(a, 'ta', scopes=['shared/material/M_Sea'], lock_paths=[SEA])
    for claim in (one, two):
        assert acquire(a, claim['id'], a.locker)['state'] == 'active'
    counts = {}
    monkeypatch.setattr(world.store, 'lfs', Counting(world.store.lfs, counts, 'lfs'))
    monkeypatch.setattr(world.store, 'git', Counting(world.store.git, counts, 'git'))
    view = coverage(a, 'ta')
    assert [c['verified'] for c in view['claims']] == [True, True]
    assert counts.get('lfs.locks.all') == 1 and counts.get('git.head') == 1, counts
    assert evaluate([Change('M', BENCH), Change('M', SEA)], {BENCH: 'lockable', SEA: 'lockable'}, view, 'publish') == []
    world.lfs.locks.pop(next(iter(world.lfs.locks)))   # one lock gone from the remote: its claim fails, not the other
    assert sorted(c['verified'] for c in coverage(a, 'ta')['claims']) == [False, True]


def test_a_check_reads_only_the_locks_of_its_own_paths(world, monkeypatch):
    """A claim of many locks is checked for one path with that path's lock alone (no full listing), and a lock missing
    from the remote fails exactly the checks that write through it."""
    a = world.agent('a', 'alice')
    world.task(a, 'ta')
    paths = [f'{HARBOUR}Actor{i:02}.uasset' for i in range(30)]
    claim = world.request(a, 'ta', lock_paths=paths)
    assert acquire(a, claim['id'], a.locker)['state'] == 'active'
    counts = {}
    monkeypatch.setattr(world.store, 'lfs', Counting(world.store.lfs, counts, 'lfs'))
    repo = world.seed
    assert check(a, repo, 'ta', [Change('M', paths[0])], stage='publish') == []
    assert 'lfs.locks.all' not in counts, counts                 # one per-path read, not the 30-lock listing
    gone = next(i for i, l in world.lfs.locks.items() if l['path'] == paths[5])
    world.lfs.locks.pop(gone)                                    # another path's lock disappears from the remote
    assert check(a, repo, 'ta', [Change('M', paths[0])], stage='publish') == []
    problems = check(a, repo, 'ta', [Change('M', paths[5])], stage='publish')
    assert problems and 'failed live verification' in problems[0], problems
    # The whole-task answer still reads every lock.
    assert [c['verified'] for c in coverage(a, 'ta')['claims']] == [False]
