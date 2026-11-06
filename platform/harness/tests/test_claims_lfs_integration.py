"""Opt-in: the claim sequence against a real Git remote and its real Git LFS lock API.

Set ``ATELIER_CLAIMS_LFS_REMOTE`` to a scratch repository URL whose LFS server supports locking and for which
this machine's Git credentials can push and lock (for example a private test repository). The test locks and
unlocks one unique path under ``atelier-claims-test/`` and leaves no lock behind. Optionally set
``ATELIER_CLAIMS_LFS_BRANCH`` (default ``main``).
"""
import os
import subprocess
import uuid

import pytest

from atelier.harness.claims.client import Change, Client, acquire, evaluate, release_locks
from atelier.harness.claims.remote import GitCli, GitLfsCli
from atelier.harness.claims.service import Service
from atelier.harness.claims.store import Store

REMOTE = os.environ.get('ATELIER_CLAIMS_LFS_REMOTE')
pytestmark = pytest.mark.skipif(not REMOTE, reason='set ATELIER_CLAIMS_LFS_REMOTE to run against a real LFS remote')
TOKEN = 'integration-token-0123456789'


def test_real_lfs_lock_is_verified_bound_and_released(tmp_path):
    branch = os.environ.get('ATELIER_CLAIMS_LFS_BRANCH', 'main')
    work = tmp_path / 'work'
    subprocess.run(['git', 'clone', '-q', '--depth', '50', '--branch', branch, REMOTE, str(work)], check=True,
                   timeout=300, env={**os.environ, 'GIT_LFS_SKIP_SMUDGE': '1', 'GIT_TERMINAL_PROMPT': '0'})
    lfs = GitLfsCli(work)
    path = f'atelier-claims-test/{uuid.uuid4().hex}.bin'
    store = Store(tmp_path / 'claims.sqlite', GitCli(work), lfs, coordinators=['lead'])
    service = Service(store, TOKEN, '127.0.0.1', 0)
    service.start()
    try:
        account = None
        probe = lfs.lock(path)
        assert probe.outcome == 'created', probe.detail
        account = probe.lock.owner
        assert lfs.unlock(probe.lock.id)
        assert not [l for l in lfs.locks(path=path)]
        c = Client(service.url, TOKEN, 'agent')
        c.call('POST', '/principals', {'name': 'lead', 'kind': 'human'})
        c.call('POST', '/principals', {'name': 'agent', 'kind': 'agent', 'git_account': account})
        c.call('POST', '/machines', {'id': 'integration'})
        c.call('POST', '/workspaces', {'id': 'ws', 'principal': 'agent', 'machine': 'integration'})
        Client(service.url, TOKEN, 'lead').call('POST', '/reconcile')
        head = subprocess.run(['git', '-C', str(work), 'rev-parse', 'HEAD'], capture_output=True, text=True,
                              check=True).stdout.strip()
        c.call('POST', '/tasks', {'id': 't', 'title': 'integration', 'workspace': 'ws', 'target_branch': branch,
                                  'base_revision': head})
        claim = c.call('POST', '/claims', {'task': 't', 'workspace': 'ws', 'lock_paths': [path]})
        view = acquire(c, claim['id'], lfs)
        assert view['state'] == 'active'
        remote = [l for l in lfs.locks(path=path)]
        assert len(remote) == 1 and remote[0].id == view['locks'][0]['lock_id'] and remote[0].owner == account
        assert evaluate([Change('A', path)], {path: 'lockable'}, c.call('GET', '/tasks/t/coverage'), 'publish') == []
        view = c.call('POST', f'/claims/{claim["id"]}/cancel', {'disposition': 'discarded'})
        assert release_locks(c, view, lfs)['state'] == 'released'
        assert not lfs.locks(path=path)
    finally:
        for lock in lfs.locks(path=path):
            lfs.unlock(lock.id)
        service.close()
        store.close()
