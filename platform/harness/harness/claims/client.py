"""Client side: the HTTP client, the lock acquisition sequence and the fail-closed change-set check."""
import fnmatch
import json
import subprocess
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
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


LOCK_WORKERS = 8   # paths locked at once: each path is three remote round trips, and paths are independent
UNKNOWN_RETRY_S = (2.0, 5.0)   # an unanswered lock request is asked again: a dropped reply rarely means a lock


def _workers(locker, workers, count):
    return max(1, min(workers if getattr(locker, 'concurrent', False) else 1, count))


def acquire(client, claim_id, locker, ref=None, workers=LOCK_WORKERS):
    """Lock every needed LFS path of a pending (or extended active) claim with this client's own credentials,
    then have the service verify and activate it. On failure abort the attempt: the service lists only the
    locks this attempt proved it created, and this client unlocks exactly those.

    Paths are locked `workers` at a time when the locker is safe to run concurrently (`locker.concurrent`), else
    one at a time, so no request waits behind another after its intent is recorded. Each path still records its
    intent right before its lock request and its result after it. After the first failure or error, no new path starts; the requests already started finish
    and report before the attempt is aborted or the error is raised."""
    view = client.call('GET', f'/claims/{claim_id}')
    paths = [lock['path'] for lock in view['locks']
             if lock['state'] in ('needed', 'refused', 'requested', 'uncertain', 'abandoned')]
    stop = threading.Event()

    def lock_one(path):
        if stop.is_set():
            return None
        try:
            try:
                intent = client.call('POST', f'/claims/{claim_id}/lock-intent', {'path': path})  # Unreachable: nothing locked
            except Refused as error:
                if error.code != 'unsettled':
                    raise
                # An earlier attempt's request may still land: keep the reservation, do not abort.
                raise AcquireFailed(f'{error}; claim {claim_id} stays reserved', view) from None
            if intent.get('resumed'):
                return None  # an earlier interrupted attempt made this lock; the service recorded it
            result = locker.lock(path, ref=ref)
            for wait in UNKNOWN_RETRY_S:
                if result.outcome != 'unknown':
                    break
                # Asking again settles a dropped reply now, not after the settle interval: a new lock (201) proves
                # the first request made none, and if that one lands later the remote refuses it as a duplicate.
                # Any other answer (the path is already locked, perhaps by the first request) stays unknown.
                time.sleep(wait)
                again = locker.lock(path, ref=ref)
                if again.outcome != 'unknown':
                    result = again if again.outcome == 'created' else result
                    break
            body = {'path': path, 'outcome': result.outcome, 'detail': result.detail}
            if result.outcome == 'created':
                body.update(lock_id=result.lock.id, owner=result.lock.owner)
            try:
                client.call('POST', f'/claims/{claim_id}/lock-result', body)
            except Unreachable as error:
                raise AcquireFailed(f'{error}; {path} is {result.outcome} and stays reserved until the service '
                                    'reconciles (do not unlock or edit it)') from None
        except BaseException:
            stop.set()
            raise
        if result.outcome != 'created':
            stop.set()
            return f'{path}: {result.outcome} {result.detail}'.strip()
        return None

    failure, error = None, None
    with ThreadPoolExecutor(max_workers=_workers(locker, workers, len(paths))) as pool:
        for future in [pool.submit(lock_one, path) for path in paths]:   # in path order: the first problem wins
            try:
                outcome = future.result()
            except BaseException as raised:   # noqa: BLE001 - re-raised once every started request reported
                error = error or raised
                continue
            failure = failure or outcome
    if error is not None:
        raise error
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


def release_locks(client, view, locker, ref=None, workers=LOCK_WORKERS):
    """Unlock the claim's locks the service marked releasing (proven ours), reporting each one, `workers` at a
    time. A lock the LFS server cannot unlock now stays releasing (retry with `atelier claims unlock`)."""
    releasing = [lock for lock in view['locks'] if lock['state'] == 'releasing' and lock['lock_id']]

    def release(lock):
        try:
            locker.unlock(lock['lock_id'], ref=ref)
        except Unavailable:
            return False
        client.call('POST', f'/claims/{view["id"]}/unlocked', {'path': lock['path']})
        return True

    if not releasing:
        return view
    with ThreadPoolExecutor(max_workers=_workers(locker, workers, len(releasing))) as pool:
        list(pool.map(release, releasing))   # re-raises the first error once every started unlock reported
    return client.call('GET', f'/claims/{view["id"]}')


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


def evaluate(changes, guarded, coverage, stage='commit', actor=None):
    """Return problems: every changed protected path (both sides of a rename, deletions included) must be
    covered by an ACTIVE claim of the task that the service re-verified live for this check (its LFS locks on
    the remote and its base against the target branch). Publication additionally requires exact paths, with
    verified LFS locks for lockable files; new files under a region prefix must be added to the claim first. Only
    claims held by `actor`, the principal checking, count: a task's claim transferred to another principal no longer
    authorizes its previous holder."""
    touched = sorted({p for change in changes for p in change.paths() if p in guarded})
    if not touched:
        return []
    if coverage is None:
        return [f'{path}: protected and no task is set' for path in touched]
    if coverage.get('service') != 'ready':
        return [f'claims service is {coverage.get("service")}; protected writes wait for reconciliation']
    # Only a live verification counts: a coverage answer without one (stored state alone) authorizes nothing.
    active = [c for c in coverage['claims'] if c['state'] == 'active' and c.get('verified') is True
              and (actor is None or c.get('principal') == actor)]
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
            foreign = [c for c in unverified if actor is not None and c.get('principal') != actor]
            if foreign:
                why = f'claim {foreign[0]["id"]} is held by {foreign[0].get("principal")}, not {actor}'
            elif unverified:
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
        return evaluate(changes, guarded, None, stage, client.actor)
    try:
        coverage = client.call('GET', f'/tasks/{task}/coverage')
    except Unreachable as error:
        return [f'{error}: protected changes cannot be verified']
    except Refused as error:
        return [f'claims service refused the check: {error}']
    return evaluate(changes, guarded, coverage, stage, client.actor)
