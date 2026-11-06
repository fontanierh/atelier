"""Client side: the HTTP client, the lock acquisition sequence and the fail-closed change-set check."""
import fnmatch
import json
import subprocess
import urllib.error
import urllib.request
from dataclasses import dataclass

from . import scopes
from .remote import Unavailable


class Unreachable(Exception):
    """The claims service did not answer. Protected writes and publication must stop."""


class Refused(Exception):
    def __init__(self, status, payload):
        super().__init__(f'{payload.get("error", status)}: {payload.get("message", "")}')
        self.status, self.payload, self.code = status, payload, payload.get('error')


class Client:
    def __init__(self, url, token, actor, timeout=30):
        self.url, self.token, self.actor, self.timeout = url.rstrip('/'), token, actor, timeout

    def call(self, method, path, body=None):
        data = None
        if method == 'POST':
            data = json.dumps({'actor': self.actor, **(body or {})}).encode()
        request = urllib.request.Request(self.url + path, data=data, method=method, headers={
            'Authorization': 'Bearer ' + self.token, 'Content-Type': 'application/json'})
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                return json.loads(response.read())
        except urllib.error.HTTPError as error:
            try:
                payload = json.loads(error.read() or b'{}')
            except ValueError:
                payload = {}
            raise Refused(error.code, payload) from None
        except (OSError, ValueError) as error:
            raise Unreachable(f'claims service at {self.url}: {error}') from None


class AcquireFailed(Exception):
    def __init__(self, message, claim=None):
        super().__init__(message)
        self.claim = claim


def acquire(client, claim_id, locker, ref=None):
    """Lock every needed LFS path of a pending (or extended active) claim with this client's own credentials,
    then have the service verify and activate it. On failure abort the attempt: the service lists only the
    locks this attempt proved it created, and this client unlocks exactly those."""
    view = client.call('GET', f'/claims/{claim_id}')
    failure = None
    for lock in view['locks']:
        if lock['state'] not in ('needed', 'refused', 'requested', 'uncertain', 'abandoned'):
            continue
        path = lock['path']
        try:
            intent = client.call('POST', f'/claims/{claim_id}/lock-intent', {'path': path})  # Unreachable: nothing locked
        except Refused as error:
            if error.code != 'unsettled':
                raise
            # An earlier attempt's request may still land: keep the reservation, do not abort.
            raise AcquireFailed(f'{error}; claim {claim_id} stays reserved', view) from None
        if intent.get('resumed'):
            continue  # an earlier interrupted attempt made this lock; the service recorded it
        result = locker.lock(path, ref=ref)
        body = {'path': path, 'outcome': result.outcome, 'detail': result.detail}
        if result.outcome == 'created':
            body.update(lock_id=result.lock.id, owner=result.lock.owner)
        try:
            client.call('POST', f'/claims/{claim_id}/lock-result', body)
        except Unreachable as error:
            raise AcquireFailed(f'{error}; {path} is {result.outcome} and stays reserved until the service '
                                'reconciles (do not unlock or edit it)') from None
        if result.outcome != 'created':
            failure = f'{path}: {result.outcome} {result.detail}'.strip()
            break
    if failure is None:
        try:
            return client.call('POST', f'/claims/{claim_id}/activate')
        except Refused as error:
            if view['state'] != 'pending' or error.code in ('reconciling', 'lfs_unavailable', 'git_unavailable'):
                raise AcquireFailed(str(error), view) from None
            failure = str(error)
    aborted = client.call('POST', f'/claims/{claim_id}/abort', {'reason': failure})
    released = release_locks(client, aborted, locker, ref=ref)
    raise AcquireFailed(f'claim {claim_id} not granted: {failure}', released)


def release_locks(client, view, locker, ref=None):
    """Unlock the claim's locks the service marked releasing (proven ours), reporting each one."""
    for lock in view['locks']:
        if lock['state'] == 'releasing' and lock['lock_id']:
            try:
                locker.unlock(lock['lock_id'], ref=ref)
            except Unavailable:
                continue  # stays releasing; retry with `atelier claims unlock`
            view = client.call('POST', f'/claims/{view["id"]}/unlocked', {'path': lock['path']})
    return view


# ---------------------------------------------------------------------------- change-set check

@dataclass(frozen=True)
class Change:
    status: str  # A, M, D, R, C, T ...
    path: str
    old: str | None = None

    def paths(self):
        return [p for p in (self.old, self.path) if p]


def _git(repo, *argv, stdin=None):
    result = subprocess.run(['git', '-C', str(repo), *argv], capture_output=True, input=stdin, timeout=60)
    if result.returncode != 0:
        raise RuntimeError(f'git {argv[0]} failed: {result.stderr.decode(errors="replace").strip()}')
    return result.stdout.decode()


def _name_status(text):
    fields, changes, i = text.split('\0'), [], 0
    while i < len(fields) and fields[i]:
        status = fields[i]
        if status[0] in 'RC':
            changes.append(Change(status[0], fields[i + 2], fields[i + 1]))
            i += 3
        else:
            changes.append(Change(status[0], fields[i + 1]))
            i += 2
    return changes


def staged_changes(repo):
    return _name_status(_git(repo, 'diff', '--cached', '--name-status', '-z', '--find-renames'))


def range_changes(repo, spec):
    return _name_status(_git(repo, 'diff', '--name-status', '-z', '--find-renames', spec))


def protected(repo, paths, patterns=(), cached=False):
    """Map each protected path to why: 'lockable' (Git LFS lockable attribute) or 'pattern'."""
    found = {}
    if paths:
        argv = ['check-attr', '-z', '--stdin'] + (['--cached'] if cached else []) + ['lockable']
        out = _git(repo, *argv, stdin='\0'.join(paths).encode() + b'\0').split('\0')
        for i in range(0, len(out) - 2, 3):
            if out[i + 2] not in ('unspecified', 'unset', ''):
                found[out[i]] = 'lockable'
    for path in paths:
        if path not in found and any(fnmatch.fnmatchcase(path, pattern) for pattern in patterns):
            found[path] = 'pattern'
    return found


def evaluate(changes, guarded, coverage, stage='commit'):
    """Return problems: every changed protected path (both sides of a rename, deletions included) must be
    covered by an ACTIVE claim of the task that the service re-verified live for this check (its LFS locks on
    the remote and its base against the target branch). Publication additionally requires exact paths, with
    verified LFS locks for lockable files; new files under a region prefix must be added to the claim first."""
    touched = sorted({p for change in changes for p in change.paths() if p in guarded})
    if not touched:
        return []
    if coverage is None:
        return [f'{path}: protected and no task is set' for path in touched]
    if coverage.get('service') != 'ready':
        return [f'claims service is {coverage.get("service")}; protected writes wait for reconciliation']
    # Only a live verification counts: a coverage answer without one (stored state alone) authorizes nothing.
    active = [c for c in coverage['claims'] if c['state'] == 'active' and c.get('verified') is True]
    items = [(i['kind'], i['value']) for c in active for i in c['items'] if i['kind'] != 'scope']
    exact = {i['value'].casefold(): i['lfs'] for c in active for i in c['items'] if i['kind'] == 'path'}
    locked = {l['path'].casefold() for c in active for l in c['locks'] if l['state'] == 'verified'}
    problems = []
    for path in touched:
        key = path.casefold()
        if not scopes.covers(items, path):
            held = [c['id'] for c in coverage['claims'] if scopes.covers(
                [(i['kind'], i['value']) for i in c['items']], path)]
            unverified = [c for c in coverage['claims'] if c['id'] in held and c['state'] == 'active']
            if unverified:
                why = (f'claim {unverified[0]["id"]} failed live verification against the remote: '
                       f'{json.dumps(unverified[0].get("problems", "not verified"), sort_keys=True)[:300]}')
            else:
                why = f'claim {held[0]} is not active yet' if held else 'not declared by any active claim of this task'
            problems.append(f'{path}: {why}')
        elif stage == 'publish' and key not in exact:
            problems.append(f'{path}: covered only by a prefix; add the exact path (and its LFS lock) before publishing')
        elif stage == 'publish' and guarded[path] == 'lockable' and not (exact[key] and key in locked):
            problems.append(f'{path}: lockable file without a verified LFS lock in this claim')
    return problems


def check(client, repo, task, changes, patterns=(), stage='commit', cached=False):
    """Fail-closed check. Unprotected changes pass without contacting the service; protected ones need it, and
    the service re-verifies the task's active claims against the LFS and Git remotes for every check (it refuses
    when either cannot be asked)."""
    names = sorted({p for change in changes for p in change.paths()})
    guarded = protected(repo, names, patterns, cached=cached)
    if not any(p in guarded for p in names):
        return []
    if not task:
        return evaluate(changes, guarded, None, stage)
    try:
        coverage = client.call('GET', f'/tasks/{task}/coverage')
    except Unreachable as error:
        return [f'{error}: protected changes cannot be verified']
    except Refused as error:
        return [f'claims service refused the check: {error}']
    return evaluate(changes, guarded, coverage, stage)
