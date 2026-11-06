"""Pluggable views of the shared Git and Git LFS remotes.

The service verifies, it never trusts a report: a claim becomes active only after an LFS verifier shows the
reported lock (path, owner, ID) on the remote and a Git verifier shows the base is current. Any doubt raises
``Unavailable``, which callers treat as a refusal (fail closed), never as success.

Clients lock and unlock with their own credentials through a locker (``git lfs lock --json`` normally).
"""
import json
import os
import subprocess
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass

LFS_MEDIA = 'application/vnd.git-lfs+json'


class Unavailable(Exception):
    """The remote could not be asked or gave an answer that cannot be trusted."""


@dataclass(frozen=True)
class Lock:
    id: str
    path: str
    owner: str


@dataclass(frozen=True)
class LockResult:
    """One lock attempt. ``created`` means this call made the lock (proven ours); ``exists`` means the
    path was already locked (by anyone, including this account); ``failed`` means certainly no lock was made;
    ``unknown`` means the call may or may not have created a lock."""
    outcome: str
    lock: Lock | None = None
    detail: str = ''


def _lock(data):
    try:
        return Lock(str(data['id']), str(data['path']), str((data.get('owner') or {}).get('name') or ''))
    except (KeyError, TypeError, AttributeError) as error:
        raise Unavailable(f'malformed LFS lock record: {data!r}') from error


# ---------------------------------------------------------------------------- LFS: HTTP locking API

class LfsHttp:
    """The Git LFS locking API over HTTP (docs/api/locking.md in git-lfs). Serves as both verifier and locker."""

    def __init__(self, url, headers=None, timeout=20):
        self.url, self.headers, self.timeout = url.rstrip('/'), dict(headers or {}), timeout

    def _call(self, method, path, body=None, query=None):
        url = self.url + path + ('?' + urllib.parse.urlencode(query) if query else '')
        data = json.dumps(body).encode() if body is not None else None
        request = urllib.request.Request(url, data=data, method=method,
                                         headers={'Accept': LFS_MEDIA, 'Content-Type': LFS_MEDIA, **self.headers})
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                return response.status, json.loads(response.read() or b'{}')
        except urllib.error.HTTPError as error:
            try:
                payload = json.loads(error.read() or b'{}')
            except ValueError:
                payload = {}
            return error.code, payload
        except (OSError, ValueError) as error:
            raise Unavailable(f'LFS locking API {method} {path}: {error}') from error

    def locks(self, path=None, lock_id=None):
        found, cursor = [], None
        for _ in range(1000):
            query = {k: v for k, v in (('path', path), ('id', lock_id), ('cursor', cursor), ('limit', 100)) if v}
            status, payload = self._call('GET', '/locks', query=query)
            if status != 200 or not isinstance(payload.get('locks'), list):
                raise Unavailable(f'LFS lock listing returned {status}: {payload.get("message", "")}')
            found += [_lock(item) for item in payload['locks']]
            cursor = payload.get('next_cursor')
            if not cursor:
                return found
        raise Unavailable('LFS lock listing did not terminate')

    def lock(self, path, ref=None):
        try:
            status, payload = self._call('POST', '/locks', {'path': path, **({'ref': {'name': ref}} if ref else {})})
        except Unavailable as error:
            return LockResult('unknown', detail=str(error))
        if status == 201 and isinstance(payload.get('lock'), dict):
            return LockResult('created', _lock(payload['lock']))
        if status == 409:
            existing = payload.get('lock')
            return LockResult('exists', _lock(existing) if isinstance(existing, dict) else None, payload.get('message', ''))
        if status in (400, 401, 403, 404, 422):
            return LockResult('failed', detail=f'{status}: {payload.get("message", "")}')
        return LockResult('unknown', detail=f'{status}: {payload.get("message", "")}')

    def unlock(self, lock_id, ref=None):
        status, payload = self._call('POST', f'/locks/{urllib.parse.quote(lock_id, safe="")}/unlock',
                                     {'force': False, **({'ref': {'name': ref}} if ref else {})})
        if status == 404:
            return False
        if status != 200:
            raise Unavailable(f'LFS unlock {lock_id} returned {status}: {payload.get("message", "")}')
        return True


# ---------------------------------------------------------------------------- LFS: git-lfs command line

class GitLfsCli:
    """``git lfs locks/lock/unlock --json`` in a checkout, using that checkout's configured credentials."""

    def __init__(self, repo, remote=None, timeout=60):
        self.repo, self.remote, self.timeout = str(repo), remote, timeout

    def _run(self, *argv):
        command = ['git', '-C', self.repo, 'lfs', *argv, '--json'] + (['--remote', self.remote] if self.remote else [])
        env = {**os.environ, 'GIT_TERMINAL_PROMPT': '0'}
        return subprocess.run(command, capture_output=True, text=True, timeout=self.timeout, env=env)

    def locks(self, path=None, lock_id=None):
        try:
            result = self._run('locks', *(['--path', path] if path else []), *(['--id', lock_id] if lock_id else []))
        except (OSError, subprocess.TimeoutExpired) as error:
            raise Unavailable(f'git lfs locks: {error}') from error
        if result.returncode != 0:
            raise Unavailable(f'git lfs locks failed: {result.stderr.strip()[-500:]}')
        try:
            items = json.loads(result.stdout or '[]')
        except ValueError as error:
            raise Unavailable('git lfs locks printed non-JSON output') from error
        if not isinstance(items, list):
            raise Unavailable('git lfs locks printed an unexpected JSON value')
        return [_lock(item) for item in items]

    def lock(self, path, ref=None):
        try:
            result = self._run('lock', path)
        except subprocess.TimeoutExpired as error:
            return LockResult('unknown', detail=f'git lfs lock timed out: {error}')
        except OSError as error:
            return LockResult('failed', detail=f'git lfs lock could not start: {error}')
        if result.returncode == 0:
            try:
                made = json.loads(result.stdout)
                made = made[0] if isinstance(made, list) and len(made) == 1 else made
                lock = _lock(made)
            except (ValueError, Unavailable) as error:
                return LockResult('unknown', detail=f'unreadable git lfs lock output: {error}')
            if not lock.owner:
                # GitHub's `git lfs lock --json` prints [{id, path, locked_at}] without the owner: read it back.
                try:
                    listed = [l for l in self.locks(lock_id=lock.id) if l.id == lock.id]
                except Unavailable:
                    listed = []
                if listed:
                    lock = listed[0]
            return LockResult('created', lock)
        text = (result.stderr + result.stdout).strip()
        if 'already locked' in text.lower() or 'lock exists' in text.lower() or 'already created' in text.lower():
            return LockResult('exists', detail=text[-500:])
        # git-lfs does not separate "refused" from "connection dropped after the request was sent": unknown.
        return LockResult('unknown', detail=text[-500:])

    def unlock(self, lock_id, ref=None):
        try:
            result = self._run('unlock', '--id', lock_id)
        except (OSError, subprocess.TimeoutExpired) as error:
            raise Unavailable(f'git lfs unlock: {error}') from error
        if result.returncode != 0:
            raise Unavailable(f'git lfs unlock {lock_id} failed: {(result.stderr + result.stdout).strip()[-500:]}')
        return True


# ---------------------------------------------------------------------------- Git

class GitCli:
    """Target-branch checks in a service-host clone of the shared remote (``git ls-remote`` + ``fetch``)."""

    def __init__(self, repo, remote='origin', timeout=120):
        self.repo, self.remote, self.timeout = str(repo), remote, timeout

    def _git(self, *argv, check=True):
        try:
            result = subprocess.run(['git', '-C', self.repo, *argv], capture_output=True, text=True,
                                    timeout=self.timeout, env={**os.environ, 'GIT_TERMINAL_PROMPT': '0'})
        except (OSError, subprocess.TimeoutExpired) as error:
            raise Unavailable(f'git {argv[0]}: {error}') from error
        if check and result.returncode != 0:
            raise Unavailable(f'git {argv[0]} failed: {result.stderr.strip()[-500:]}')
        return result

    def head(self, branch):
        """The target branch's current remote head, fetched so later checks can read its history."""
        lines = self._git('ls-remote', '--heads', self.remote, 'refs/heads/' + branch).stdout.split('\n')
        heads = [line.split('\t')[0] for line in lines if line.endswith('\trefs/heads/' + branch)]
        if len(heads) != 1:
            raise Unavailable(f'target branch {branch!r} is not on {self.remote}')
        self._git('fetch', '--quiet', '--no-tags', self.remote, f'+refs/heads/{branch}:refs/claims/{branch}')
        if self._git('rev-parse', '--verify', '--quiet', f'refs/claims/{branch}').stdout.strip() != heads[0]:
            raise Unavailable(f'{branch} moved while it was fetched; retry')
        return heads[0]

    def known(self, revision):
        return self._git('cat-file', '-e', revision + '^{commit}', check=False).returncode == 0

    def is_ancestor(self, revision, head):
        if not self.known(revision):
            return False
        result = self._git('merge-base', '--is-ancestor', revision, head, check=False)
        if result.returncode not in (0, 1):
            raise Unavailable(f'git merge-base failed: {result.stderr.strip()[-500:]}')
        return result.returncode == 0

    def changed(self, base, head, items):
        """Repository paths changed between base and head under the given (kind, value) path/prefix items."""
        specs = [':(literal,icase)' + value.rstrip('/') for kind, value in items if kind in ('path', 'prefix')]
        if not specs:
            return []
        out = self._git('diff', '--no-renames', '--name-only', base, head, '--', *specs).stdout
        return [line for line in out.split('\n') if line]
