"""The claim authority's durable state and its only writer.

Every mutation runs in one ``BEGIN IMMEDIATE`` transaction behind a process lock and appends its event in the
same transaction, so the event history is complete and a polling cursor (``events(after)``) never misses state.
Remote reads (Git heads, LFS locks) happen outside the lock; the decision is then re-checked inside it.
"""
import contextlib
import fcntl
import json
import sqlite3
import threading
import time
from pathlib import Path

from . import scopes
from .remote import Unavailable

LIST_ALL_LOCKS_ABOVE = 20   # larger checks use one paginated listing, not a remote request for each path

HOLDING = ('pending', 'active', 'releasing', 'uncertain')
TASK_STATES = ('open', 'in_progress', 'review', 'merged', 'cancelled')
SCHEMA = """
CREATE TABLE IF NOT EXISTS principals (name TEXT PRIMARY KEY, kind TEXT NOT NULL, git_account TEXT, created REAL NOT NULL);
CREATE TABLE IF NOT EXISTS machines (id TEXT PRIMARY KEY, created REAL NOT NULL);
CREATE TABLE IF NOT EXISTS workspaces (id TEXT PRIMARY KEY, principal TEXT NOT NULL, machine TEXT NOT NULL,
  last_seen REAL, created REAL NOT NULL);
CREATE TABLE IF NOT EXISTS tasks (id TEXT PRIMARY KEY, title TEXT NOT NULL, status TEXT NOT NULL, owner TEXT NOT NULL,
  workspace TEXT NOT NULL, target_branch TEXT NOT NULL, branch TEXT, base_revision TEXT, depends_on TEXT NOT NULL,
  reads TEXT NOT NULL, merged_revision TEXT, created REAL NOT NULL, updated REAL NOT NULL);
CREATE TABLE IF NOT EXISTS claims (id INTEGER PRIMARY KEY AUTOINCREMENT, task TEXT NOT NULL, principal TEXT NOT NULL,
  workspace TEXT NOT NULL, state TEXT NOT NULL, ending TEXT, base_revision TEXT NOT NULL, target_head TEXT NOT NULL,
  created REAL NOT NULL, updated REAL NOT NULL);
CREATE TABLE IF NOT EXISTS items (claim INTEGER NOT NULL, kind TEXT NOT NULL, value TEXT NOT NULL,
  lfs INTEGER NOT NULL DEFAULT 0, PRIMARY KEY (claim, kind, value));
CREATE TABLE IF NOT EXISTS locks (claim INTEGER NOT NULL, path TEXT NOT NULL, state TEXT NOT NULL, lock_id TEXT,
  owner TEXT, prior TEXT, detail TEXT, updated REAL NOT NULL, rev INTEGER NOT NULL DEFAULT 0, PRIMARY KEY (claim, path));
CREATE TABLE IF NOT EXISTS events (seq INTEGER PRIMARY KEY AUTOINCREMENT, at REAL NOT NULL, kind TEXT NOT NULL,
  actor TEXT NOT NULL, task TEXT, claim INTEGER, data TEXT NOT NULL);
"""
# Every change to a lock row bumps its revision, so a decision made from a remote read taken outside the lock is
# applied only if the row is still the one that was read (compare-and-set in the writing transaction).
REVISION = """
CREATE TRIGGER IF NOT EXISTS locks_revision AFTER UPDATE ON locks WHEN NEW.rev = OLD.rev
BEGIN UPDATE locks SET rev = OLD.rev + 1 WHERE claim = NEW.claim AND path = NEW.path; END;
"""
# Lock rows: needed -> requested (intent) -> created (reported) -> verified (remote confirmed).
# requested/unknown -> uncertain; created/verified -> releasing -> released; exists/failed -> refused.
# uncertain -> abandoned when no lock appeared within the settle interval (or a coordinator says foreign -> refused);
# an abandoned attempt's late lock is still recognised and released when it is proven the attempt's.
OWNED = ('created', 'verified')
# Attempts whose request may have made (or may still make) a lock nobody has recorded.
UNRESOLVED = ('requested', 'uncertain', 'abandoned')
RETRYABLE = ('needed', 'refused') + UNRESOLVED


class ClaimError(Exception):
    def __init__(self, status, code, message, **extra):
        super().__init__(message)
        self.status, self.code, self.message, self.extra = status, code, message, extra

    def payload(self):
        return {'error': self.code, 'message': self.message, **self.extra}


def refuse(code, message, status=409, **extra):
    raise ClaimError(status, code, message, **extra)


def _text(value, name, required=True):
    if value is None and not required:
        return None
    if not isinstance(value, str) or not value.strip() or len(value) > 500:
        refuse('invalid', f'{name} must be a non-empty string', 400)
    return value.strip()


def _list(value, name):
    if value is None:
        return []
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        refuse('invalid', f'{name} must be a list of strings', 400)
    return value


class Store:
    def __init__(self, path, git, lfs, coordinators=(), heartbeat_timeout=300.0, uncertain_settle=3600.0,
                 clock=time.time):
        self.path = Path(path)
        self.git, self.lfs, self.clock = git, lfs, clock
        self.coordinators = frozenset(coordinators)
        self.heartbeat_timeout = heartbeat_timeout
        # How long a lock request whose outcome is unknown may still create its lock. It must exceed the
        # client's lock timeout plus any server-side delay; only after it may an unseen lock be settled.
        self.uncertain_settle = float(uncertain_settle)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # Only the service opens the database: a second service on the same file refuses to start.
        self._owner = open(str(self.path) + '.owner', 'a')
        try:
            fcntl.flock(self._owner, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self._owner.close()
            raise RuntimeError(f'another claims service already owns {self.path}')
        self.db = sqlite3.connect(self.path, isolation_level=None, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.execute('PRAGMA synchronous=FULL')
        self.db.executescript(SCHEMA)
        if 'rev' not in {r['name'] for r in self.db.execute('PRAGMA table_info(locks)')}:
            self.db.execute('ALTER TABLE locks ADD COLUMN rev INTEGER NOT NULL DEFAULT 0')
        self.db.executescript(REVISION)
        self.lock = threading.RLock()
        # A restarted service may have missed lock changes and lost in-flight replies: no grants until reconciled.
        self.ready = False
        with self.tx() as db:
            self._event(db, 'service.started', 'service', data={'state': 'reconciling'})

    def close(self):
        with self.lock:
            self.db.close()
            self._owner.close()

    @contextlib.contextmanager
    def tx(self):
        with self.lock:
            self.db.execute('BEGIN IMMEDIATE')
            try:
                yield self.db
            except BaseException:
                self.db.execute('ROLLBACK')
                raise
            self.db.execute('COMMIT')

    def _event(self, db, kind, actor, task=None, claim=None, data=None):
        db.execute('INSERT INTO events (at,kind,actor,task,claim,data) VALUES (?,?,?,?,?,?)',
                   (self.clock(), kind, actor, task, claim, json.dumps(data or {}, sort_keys=True)))

    # ------------------------------------------------------------------ identities

    def _principal(self, db, name):
        row = db.execute('SELECT * FROM principals WHERE name=?', (name,)).fetchone()
        if not row:
            refuse('unknown_principal', f'principal {name!r} is not registered', 404)
        return row

    def _coordinator(self, db, actor):
        self._principal(db, actor)
        if actor not in self.coordinators:
            refuse('not_coordinator', f'{actor!r} is not a configured coordinator', 403)

    def register_principal(self, name, kind, git_account=None):
        name, kind = _text(name, 'name'), _text(kind, 'kind')
        git_account = _text(git_account, 'git_account', required=False)
        if kind not in ('agent', 'human'):
            refuse('invalid', 'kind must be agent or human', 400)
        with self.tx() as db:
            row = db.execute('SELECT * FROM principals WHERE name=?', (name,)).fetchone()
            if row:
                if (row['kind'], row['git_account']) != (kind, git_account):
                    refuse('conflict', f'principal {name!r} is registered with different details')
                return dict(row)
            db.execute('INSERT INTO principals VALUES (?,?,?,?)', (name, kind, git_account, self.clock()))
            self._event(db, 'principal.registered', name, data={'kind': kind, 'git_account': git_account})
            return dict(self._principal(db, name))

    def register_machine(self, machine):
        machine = _text(machine, 'id')
        with self.tx() as db:
            if not db.execute('SELECT 1 FROM machines WHERE id=?', (machine,)).fetchone():
                db.execute('INSERT INTO machines VALUES (?,?)', (machine, self.clock()))
                self._event(db, 'machine.registered', 'service', data={'machine': machine})
            return {'id': machine}

    def register_workspace(self, workspace, principal, machine):
        workspace, principal, machine = _text(workspace, 'id'), _text(principal, 'principal'), _text(machine, 'machine')
        with self.tx() as db:
            self._principal(db, principal)
            if not db.execute('SELECT 1 FROM machines WHERE id=?', (machine,)).fetchone():
                refuse('unknown_machine', f'machine {machine!r} is not registered', 404)
            row = db.execute('SELECT * FROM workspaces WHERE id=?', (workspace,)).fetchone()
            if row:
                if (row['principal'], row['machine']) != (principal, machine):
                    refuse('conflict', f'workspace {workspace!r} belongs to another principal or machine')
            else:
                db.execute('INSERT INTO workspaces VALUES (?,?,?,?,?)', (workspace, principal, machine, self.clock(), self.clock()))
                self._event(db, 'workspace.registered', principal, data={'workspace': workspace, 'machine': machine})
            return self._workspace_view(db, workspace)

    def _workspace(self, db, workspace, actor=None):
        row = db.execute('SELECT * FROM workspaces WHERE id=?', (workspace,)).fetchone()
        if not row:
            refuse('unknown_workspace', f'workspace {workspace!r} is not registered', 404)
        if actor is not None and row['principal'] != actor:
            refuse('not_owner', f'workspace {workspace!r} belongs to {row["principal"]!r}', 403)
        return row

    def _workspace_view(self, db, workspace):
        row = dict(self._workspace(db, workspace))
        row['reachable'] = row['last_seen'] is not None and self.clock() - row['last_seen'] <= self.heartbeat_timeout
        return row

    def heartbeat(self, actor, workspace):
        """Liveness only. An expired heartbeat marks the owner unreachable; it never moves or releases a claim."""
        with self.tx() as db:
            self._workspace(db, workspace, actor)
            db.execute('UPDATE workspaces SET last_seen=? WHERE id=?', (self.clock(), workspace))
            return self._workspace_view(db, workspace)

    def workspace(self, workspace):
        with self.lock:
            return self._workspace_view(self.db, workspace)

    # ------------------------------------------------------------------ tasks

    def _task(self, db, task):
        row = db.execute('SELECT * FROM tasks WHERE id=?', (task,)).fetchone()
        if not row:
            refuse('unknown_task', f'task {task!r} is not registered', 404)
        return row

    def create_task(self, actor, task, title, workspace, target_branch='main', branch=None, base_revision=None,
                    depends_on=None, reads=None):
        task, title = _text(task, 'id'), _text(title, 'title')
        target_branch = _text(target_branch, 'target_branch')
        branch = _text(branch, 'branch', required=False)
        base_revision = _text(base_revision, 'base_revision', required=False)
        depends_on = _list(depends_on, 'depends_on')
        reads = [self._path_item(value) for value in _list(reads, 'reads')]
        with self.tx() as db:
            self._workspace(db, workspace, actor)
            if db.execute('SELECT 1 FROM tasks WHERE id=?', (task,)).fetchone():
                refuse('conflict', f'task {task!r} already exists')
            for dep in depends_on:
                self._task(db, dep)
            now = self.clock()
            db.execute('INSERT INTO tasks VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)',
                       (task, title, 'open', actor, workspace, target_branch, branch, base_revision,
                        json.dumps(depends_on), json.dumps(reads), None, now, now))
            self._event(db, 'task.created', actor, task, data={'title': title, 'target_branch': target_branch,
                                                                'branch': branch, 'base_revision': base_revision,
                                                                'depends_on': depends_on, 'reads': reads})
            return self._task_view(db, task)

    @staticmethod
    def _path_item(value):
        try:
            return ['prefix', scopes.prefix(value)] if value.endswith('/') else ['path', scopes.path(value)]
        except scopes.InvalidItem as error:
            refuse('invalid', str(error), 400)

    def _task_view(self, db, task):
        row = dict(self._task(db, task))
        row['depends_on'], row['reads'] = json.loads(row['depends_on']), json.loads(row['reads'])
        row['dependencies'] = {dep: self._task(db, dep)['status'] for dep in row['depends_on']}
        row['claims'] = [self._claim_view(db, r['id']) for r in
                         db.execute('SELECT id FROM claims WHERE task=? ORDER BY id', (task,))]
        return row

    def task(self, task):
        with self.lock:
            return self._task_view(self.db, task)

    def update_task(self, actor, task, status=None, branch=None, base_revision=None, note=None):
        with self.tx() as db:
            row = self._task(db, task)
            self._owner_or_coordinator(db, actor, row['owner'])
            if row['status'] in ('merged', 'cancelled'):
                refuse('closed', f'task {task!r} is {row["status"]}')
            if status is not None and status not in ('open', 'in_progress', 'review'):
                refuse('invalid', 'status may be set to open, in_progress or review; merge and cancel are recorded', 400)
            changes = {k: v for k, v in (('status', status), ('branch', branch), ('base_revision', base_revision)) if v}
            for key, value in changes.items():
                db.execute(f'UPDATE tasks SET {key}=?, updated=? WHERE id=?', (_text(value, key), self.clock(), task))
            self._event(db, 'task.updated', actor, task, data={**changes, 'note': note})
            return self._task_view(db, task)

    def record_push(self, actor, task, revision, ok, detail=None):
        """A pushed branch is evidence for review, never a release; a failed push changes no ownership."""
        with self.tx() as db:
            row = self._task(db, task)
            self._owner_or_coordinator(db, actor, row['owner'])
            self._event(db, 'task.pushed' if ok else 'task.push_failed', actor, task,
                        data={'revision': revision, 'branch': row['branch'], 'detail': detail})
            return self._task_view(db, task)

    def _owner_or_coordinator(self, db, actor, owner):
        self._principal(db, actor)
        if actor != owner and actor not in self.coordinators:
            refuse('not_owner', f'only {owner!r} or a coordinator may do this', 403)

    # ------------------------------------------------------------------ claims

    def _claim(self, db, claim):
        row = db.execute('SELECT * FROM claims WHERE id=?', (claim,)).fetchone()
        if not row:
            refuse('unknown_claim', f'claim {claim!r} does not exist', 404)
        return row

    def _items(self, db, claim):
        return [(r['kind'], r['value']) for r in db.execute('SELECT kind,value FROM items WHERE claim=?', (claim,))]

    def _claim_view(self, db, claim):
        row = dict(self._claim(db, claim))
        row['items'] = [dict(r) for r in db.execute('SELECT kind,value,lfs FROM items WHERE claim=? ORDER BY kind,value', (claim,))]
        row['locks'] = [{k: r[k] for k in ('path', 'state', 'lock_id', 'owner', 'detail')}
                        for r in db.execute('SELECT * FROM locks WHERE claim=? ORDER BY path', (claim,))]
        return row

    def claim(self, claim):
        with self.lock:
            return self._claim_view(self.db, claim)

    def _require_ready(self):
        if not self.ready:
            refuse('reconciling', 'the claims service has not reconciled its state with the remote since it started', 503)

    def _normalize(self, scopes_in, lock_paths, paths, prefixes):
        items = {}
        try:
            for kind, values in (('scope', scopes_in), ('prefix', prefixes), ('path', paths), ('path', lock_paths)):
                for value in _list(values, kind):
                    items[(kind, scopes.NORMALIZE[kind](value))] = 0
            for value in _list(lock_paths, 'lock_paths'):
                items[('path', scopes.path(value))] = 1
        except scopes.InvalidItem as error:
            refuse('invalid', str(error), 400)
        return items

    def _conflicts(self, db, items, own_claim=None):
        found = []
        rows = db.execute('SELECT i.kind,i.value,c.id,c.task,c.principal,c.state FROM items i JOIN claims c ON c.id=i.claim '
                          f'WHERE c.state IN ({",".join("?" * len(HOLDING))})', HOLDING).fetchall()
        for item in items:
            for row in rows:
                if row['id'] != own_claim and scopes.overlaps(item, (row['kind'], row['value'])):
                    found.append({'item': list(item), 'held': [row['kind'], row['value']], 'claim': row['id'],
                                  'task': row['task'], 'principal': row['principal'], 'state': row['state']})
        return found

    def _base_check(self, target_branch, base, items, head=None):
        """Remote read outside the lock: target head (or the one the caller just read) and every changed
        claimed/read path since base."""
        try:
            head = head or self.git.head(target_branch)
            if not self.git.is_ancestor(base, head):
                refuse('stale_base', f'base {base} is not part of {target_branch} at {head}; update the workspace',
                       head=head)
            changed = self.git.changed(base, head, items) if base != head else []
        except Unavailable as error:
            refuse('git_unavailable', f'cannot verify the base revision: {error}', 503)
        if changed:
            refuse('stale_base', f'{len(changed)} claimed or read paths changed on {target_branch} since {base}; '
                   'update or replay onto the latest version first', head=head, changed=sorted(changed)[:200])
        return head

    def request(self, actor, task, workspace, scopes=None, lock_paths=None, paths=None, prefixes=None,
                base_revision=None):
        """Atomically reserve scopes/paths for one task in the pending state, or refuse."""
        self._require_ready()
        items = self._normalize(scopes, lock_paths, paths, prefixes)
        if not items:
            refuse('invalid', 'a claim needs at least one scope, path or prefix', 400)
        with self.lock:
            row = self._task(self.db, task)
            if row['owner'] != actor:
                refuse('not_owner', f'task {task!r} belongs to {row["owner"]!r}', 403)
            if row['status'] in ('merged', 'cancelled'):
                refuse('closed', f'task {task!r} is {row["status"]}')
            self._workspace(self.db, workspace, actor)
            base = _text(base_revision or row['base_revision'], 'base_revision')
            reads = [tuple(r) for r in json.loads(row['reads'])]
            if any(lfs for lfs in items.values()) and not self._principal(self.db, actor)['git_account']:
                refuse('invalid', f'{actor!r} has no registered git_account to verify LFS lock ownership', 400)
        head = self._base_check(row['target_branch'], base, [i for i in items if i[0] != 'scope'] + reads)
        with self.tx() as db:
            self._require_ready()
            if self._task(db, task)['status'] in ('merged', 'cancelled'):
                refuse('closed', f'task {task!r} closed while the request was checked')
            conflicts = self._conflicts(db, items)
            if conflicts:
                self._event(db, 'claim.refused', actor, task, data={'conflicts': conflicts})
                refuse('overlap', 'the request overlaps a claim held by another task', conflicts=conflicts)
            now = self.clock()
            claim = db.execute('INSERT INTO claims (task,principal,workspace,state,base_revision,target_head,created,updated) '
                               'VALUES (?,?,?,?,?,?,?,?)', (task, actor, workspace, 'pending', base, head, now, now)).lastrowid
            self._add_items(db, claim, items)
            if row['status'] == 'open':
                db.execute("UPDATE tasks SET status='in_progress', updated=? WHERE id=?", (now, task))
            self._event(db, 'claim.reserved', actor, task, claim,
                        {'items': sorted(map(list, items)), 'base_revision': base, 'target_head': head})
            return self._claim_view(db, claim)

    def _add_items(self, db, claim, items):
        for (kind, value), lfs in items.items():
            db.execute('INSERT INTO items VALUES (?,?,?,?) ON CONFLICT(claim,kind,value) DO UPDATE SET lfs=max(lfs,excluded.lfs)',
                       (claim, kind, value, lfs))
            if lfs:
                db.execute('INSERT OR IGNORE INTO locks (claim,path,state,updated) VALUES (?,?,?,?)',
                           (claim, value, 'needed', self.clock()))

    def extend(self, actor, claim, lock_paths=None, paths=None):
        """Add exact paths (for example new actor files under a region prefix) to a held claim."""
        self._require_ready()
        items = self._normalize(None, lock_paths, paths, None)
        with self.lock:
            row = self._claim(self.db, claim)
            if row['principal'] != actor or row['state'] not in ('pending', 'active'):
                refuse('not_holder', f'claim {claim} is {row["state"]} and held by {row["principal"]!r}', 403)
            task = self._task(self.db, row['task'])
            new = {i: lfs for i, lfs in items.items() if i not in self._items(self.db, claim) or lfs}
        self._base_check(task['target_branch'], row['base_revision'], list(new))
        with self.tx() as db:
            if self._claim(db, claim)['state'] not in ('pending', 'active'):
                refuse('not_holder', f'claim {claim} is no longer held')
            conflicts = self._conflicts(db, new, own_claim=claim)
            if conflicts:
                self._event(db, 'claim.refused', actor, row['task'], claim, {'conflicts': conflicts})
                refuse('overlap', 'the extension overlaps a claim held by another task', conflicts=conflicts)
            self._add_items(db, claim, new)
            self._event(db, 'claim.extended', actor, row['task'], claim, {'items': sorted(map(list, new))})
            return self._claim_view(db, claim)

    def _lock_row(self, db, claim, path):
        row = db.execute('SELECT * FROM locks WHERE claim=? AND path=?', (claim, path)).fetchone()
        if not row:
            refuse('not_declared', f'{path!r} is not an LFS path of claim {claim}', 404)
        return row

    def lock_intent(self, actor, claim, path):
        """Record that the client is about to lock a path, with the remote's locks on it beforehand.
        That snapshot is what later proves whether an unreported lock was created by this attempt.
        Retrying an unresolved attempt first looks for the lock it may already have made: a lock absent from
        the earlier snapshot and owned by the claimant is that attempt's, and is recorded instead of re-locking.
        With no such lock, an unsettled (requested/uncertain) attempt is never replaced: its request may still
        land, so the retry is refused until a listing at least the settle interval after the attempt's last step
        shows none (or a coordinator resolves it). Replacing it earlier would let a failed retry free the path."""
        self._require_ready()
        with self.lock:
            row = self._claim(self.db, claim)
            if row['principal'] != actor or row['state'] not in ('pending', 'active'):
                refuse('not_holder', f'claim {claim} is {row["state"]} and held by {row["principal"]!r}', 403)
            before = self._lock_row(self.db, claim, path)
            if before['state'] not in RETRYABLE:
                refuse('lock_state', f'{path!r} is already {before["state"]} for claim {claim}')
            account = self._principal(self.db, actor)['git_account']
        listed_at = self.clock()  # the listing below is at least this recent
        try:
            remote = [l for l in self.lfs.locks(path=path) if l.path == path]
        except Unavailable as error:
            refuse('lfs_unavailable', f'cannot read LFS locks before locking: {error}', 503)
        earlier = set(json.loads(before['prior'] or '[]'))
        candidates = [l for l in remote if l.id not in earlier and l.owner == account] \
            if before['state'] in UNRESOLVED else []
        with self.tx() as db:
            current = self._lock_row(db, claim, path)
            if current['rev'] != before['rev']:
                refuse('lock_state', f'{path!r} changed while its intent was recorded; retry')
            resumed = [l for l in candidates if not self._others_could_own(db, claim, path, l)]
            if len(candidates) != len(resumed):
                refuse('ambiguous', f'a lock on {path!r} may belong to another attempt by the same account; '
                       'a coordinator must resolve it')
            if len(resumed) == 1:
                db.execute("UPDATE locks SET state='created', lock_id=?, owner=?, updated=? WHERE claim=? AND path=?",
                           (resumed[0].id, account, self.clock(), claim, path))
                self._event(db, 'lock.resumed', actor, row['task'], claim, {'path': path, 'lock_id': resumed[0].id})
                return {'path': path, 'resumed': resumed[0].id}
            if resumed:
                refuse('lock_state', f'{path!r} has several candidate locks; a coordinator must resolve it')
            if current['state'] in ('requested', 'uncertain') and listed_at - current['updated'] < self.uncertain_settle:
                wait = self.uncertain_settle - (listed_at - current['updated'])
                refuse('unsettled', f'the earlier lock request on {path!r} may still create its lock; retry in '
                       f'{wait:.0f} s or have a coordinator resolve it', retry_after=round(wait))
            prior = sorted(l.id for l in remote)
            db.execute("UPDATE locks SET state='requested', prior=?, lock_id=NULL, owner=NULL, detail=NULL, updated=? "
                       'WHERE claim=? AND path=?', (json.dumps(prior), self.clock(), claim, path))
            self._event(db, 'lock.intent', actor, row['task'], claim, {'path': path, 'prior': prior})
            return {'path': path, 'prior': prior}

    def lock_result(self, actor, claim, path, outcome, lock_id=None, owner=None, detail=None):
        if outcome not in ('created', 'exists', 'failed', 'unknown'):
            refuse('invalid', 'outcome must be created, exists, failed or unknown', 400)
        with self.tx() as db:
            row = self._claim(db, claim)
            if row['principal'] != actor:
                refuse('not_holder', f'claim {claim} is held by {row["principal"]!r}', 403)
            lock = self._lock_row(db, claim, path)
            if lock['state'] != 'requested':
                refuse('lock_state', f'{path!r} has no outstanding lock request (state {lock["state"]})')
            if outcome == 'created':
                lock_id = _text(lock_id, 'lock_id')
                if lock_id in json.loads(lock['prior'] or '[]'):
                    refuse('invalid', f'lock {lock_id} existed before this attempt; it is not a new lock', 400)
                state = 'created'
            else:
                state, lock_id = {'exists': 'refused', 'failed': 'refused', 'unknown': 'uncertain'}[outcome], None
            db.execute('UPDATE locks SET state=?, lock_id=?, owner=?, detail=?, updated=? WHERE claim=? AND path=?',
                       (state, lock_id, owner, detail, self.clock(), claim, path))
            self._event(db, 'lock.result', actor, row['task'], claim,
                        {'path': path, 'outcome': outcome, 'lock_id': lock_id, 'owner': owner, 'detail': detail})
            return self._claim_view(db, claim)

    def activate(self, actor, claim):
        """Verify every LFS lock (path, owner, ID) and the base, then mark the claim active. Also re-verifies an
        active claim (for example after an extension or before merge); any doubt leaves it unchanged."""
        self._require_ready()
        with self.lock:
            row = self._claim(self.db, claim)
            reverify = row['state'] == 'active' and actor in self.coordinators
            if row['principal'] != actor and not reverify or row['state'] not in ('pending', 'active'):
                refuse('not_holder', f'claim {claim} is {row["state"]} and held by {row["principal"]!r}', 403)
            account = self._principal(self.db, row['principal'])['git_account']
            locks = [dict(r) for r in self.db.execute('SELECT * FROM locks WHERE claim=?', (claim,))]
            task = self._task(self.db, row['task'])
            items = self._items(self.db, claim)
            reads = [tuple(r) for r in json.loads(task['reads'])]
        missing = [lock['path'] for lock in locks if lock['state'] not in OWNED]
        if missing:
            refuse('locks_missing', f'{len(missing)} LFS locks are not reported as created', paths=missing)
        problems = self._lock_problems(locks, account)
        if problems:
            with self.tx() as db:
                self._event(db, 'claim.verify_failed', actor, row['task'], claim, {'problems': problems})
            refuse('lock_unverified', 'LFS locks do not match the remote', problems=problems)
        head = self._base_check(task['target_branch'], row['base_revision'], [i for i in items if i[0] != 'scope'] + reads)
        with self.tx() as db:
            self._require_ready()
            current = self._claim(db, claim)
            if (current['state'], current['principal']) != (row['state'], row['principal']):
                refuse('not_holder', f'claim {claim} changed while it was verified')
            if any(self._lock_row(db, claim, l['path'])['rev'] != l['rev'] for l in locks):
                refuse('lock_state', f'a lock of claim {claim} changed while it was verified; retry')
            for lock in locks:
                db.execute("UPDATE locks SET state='verified', owner=?, updated=? WHERE claim=? AND path=? AND lock_id=?",
                           (account, self.clock(), claim, lock['path'], lock['lock_id']))
            if db.execute("SELECT COUNT(*) FROM locks WHERE claim=? AND state!='verified'", (claim,)).fetchone()[0]:
                refuse('locks_missing', f'claim {claim} gained an unverified lock while it was verified')
            db.execute("UPDATE claims SET state='active', target_head=?, updated=? WHERE id=?", (head, self.clock(), claim))
            self._event(db, 'claim.activated' if current['state'] == 'pending' else 'claim.verified', actor,
                        row['task'], claim, {'target_head': head, 'locks': {l['path']: l['lock_id'] for l in locks}})
            return self._claim_view(db, claim)

    def _lock_problems(self, locks, account, listed=None):
        """Remote read: each recorded lock must be on the remote with its path, ID and the claimant's account.
        `listed` is a full listing the caller read for this same check. Raises (fail closed) when the LFS server
        cannot be asked."""
        problems = []
        try:
            # Many locks: one listing of the remote's locks (paginated), not one request per lock. Either way each
            # recorded lock is read from the remote now.
            if listed is None and len(locks) > LIST_ALL_LOCKS_ABOVE:
                listed = self.lfs.locks()
            for lock in locks:
                found = listed if listed is not None else self.lfs.locks(path=lock['path']) if lock['lock_id'] else []
                remote = [l for l in found if l.id == lock['lock_id']] if lock['lock_id'] else []
                if len(remote) != 1 or remote[0].path != lock['path'] or remote[0].owner != account:
                    problems.append({'path': lock['path'], 'lock_id': lock['lock_id'],
                                     'remote': [vars(l) for l in remote], 'expected_owner': account})
        except Unavailable as error:
            refuse('lfs_unavailable', f'cannot verify LFS locks: {error}', 503)
        return problems

    def _others_could_own(self, db, claim, path, lock):
        """Whether another claim recorded this lock, or another unresolved attempt on the path by the same LFS
        account could have created it. Then the lock is not proven this claim's, whatever its account."""
        rows = db.execute('SELECT l.state, l.lock_id, l.prior, p.git_account FROM locks l JOIN claims c ON c.id=l.claim '
                          'JOIN principals p ON p.name=c.principal WHERE lower(l.path)=lower(?) AND l.claim!=?',
                          (path, claim))
        for r in rows:
            if r['lock_id'] == lock.id:
                return True
            if r['state'] in UNRESOLVED and r['prior'] is not None and r['git_account'] == lock.owner \
                    and lock.id not in json.loads(r['prior']):
                return True
        return False

    def _proven_own(self, db, claim, path, prior, account, lock):
        """A lock is this attempt's only when it is on the path, owned by the claimant's account, absent from the
        attempt's intent snapshot, and no other attempt could have made it."""
        return (lock.path == path and lock.owner == account and lock.id not in prior
                and not self._others_could_own(db, claim, path, lock))

    def _end(self, db, claim, ending):
        """Stop holding a claim's grant: proven-own locks become releasing, unknown ones uncertain."""
        db.execute("UPDATE locks SET state='releasing', updated=? WHERE claim=? AND state IN ('created','verified')",
                   (self.clock(), claim))
        db.execute("UPDATE locks SET state='uncertain', updated=? WHERE claim=? AND state='requested'", (self.clock(), claim))
        db.execute("UPDATE locks SET state='refused', updated=? WHERE claim=? AND state='needed'", (self.clock(), claim))
        db.execute('UPDATE claims SET ending=?, state=?, updated=? WHERE id=?', (ending, 'releasing', self.clock(), claim))
        self._settle(db, claim)

    def _settle(self, db, claim):
        row = self._claim(db, claim)
        if row['ending'] is None:
            return
        states = {r['state'] for r in db.execute('SELECT state FROM locks WHERE claim=?', (claim,))}
        state = ('uncertain' if states & {'uncertain', 'requested'} else 'releasing' if 'releasing' in states
                 else 'failed' if row['ending'] == 'aborted' else 'released')
        if state in HOLDING and row['state'] not in HOLDING and self._conflicts(db, self._items(db, claim), claim):
            # An ended claim whose items another claim now holds is never revived: one writer per path. A late
            # lock proven its own is still unlocked from its releasing row, without re-granting the path.
            return
        if state != row['state']:
            db.execute('UPDATE claims SET state=?, updated=? WHERE id=?', (state, self.clock(), claim))
            self._event(db, 'claim.' + state, 'service', row['task'], claim, {'ending': row['ending']})

    def abort(self, actor, claim, reason):
        """A failed acquisition: release only locks this attempt proved it created; keep uncertain ones reserved."""
        with self.tx() as db:
            row = self._claim(db, claim)
            if row['principal'] != actor or row['state'] != 'pending':
                refuse('not_holder', f'only the holder of a pending claim may abort it (claim {claim} is {row["state"]})', 403)
            self._event(db, 'claim.aborted', actor, row['task'], claim, {'reason': reason})
            self._end(db, claim, 'aborted')
            return self._claim_view(db, claim)

    def cancel(self, actor, claim, disposition, note=None):
        if disposition not in ('preserved', 'discarded'):
            refuse('invalid', 'disposition must say whether the changes were preserved or discarded', 400)
        with self.tx() as db:
            row = self._claim(db, claim)
            if row['principal'] != actor or row['state'] not in ('pending', 'active'):
                refuse('not_holder', f'only the holder may cancel claim {claim} ({row["state"]})', 403)
            self._event(db, 'claim.cancelled', actor, row['task'], claim, {'disposition': disposition, 'note': note})
            self._end(db, claim, 'cancelled:' + disposition)
            return self._claim_view(db, claim)

    def cancel_task(self, actor, task, disposition, note=None):
        with self.lock:
            row = self._task(self.db, task)
            if row['owner'] != actor:
                refuse('not_owner', f'task {task!r} belongs to {row["owner"]!r}', 403)
            held = [r['id'] for r in self.db.execute("SELECT id FROM claims WHERE task=? AND state IN ('pending','active')", (task,))]
            for claim in held:
                self.cancel(actor, claim, disposition, note)
            with self.tx() as db:
                db.execute("UPDATE tasks SET status='cancelled', updated=? WHERE id=?", (self.clock(), task))
                self._event(db, 'task.cancelled', actor, task, data={'disposition': disposition, 'note': note})
                return self._task_view(db, task)

    def record_merge(self, actor, task, revision):
        """Release a task's claims only after its merged revision is reachable from the target branch."""
        revision = _text(revision, 'revision')
        with self.lock:
            row = self._task(self.db, task)
            self._owner_or_coordinator(self.db, actor, row['owner'])
        try:
            head = self.git.head(row['target_branch'])
            reachable = self.git.is_ancestor(revision, head)
        except Unavailable as error:
            refuse('git_unavailable', f'cannot verify the merge: {error}', 503)
        if not reachable:
            refuse('not_merged', f'{revision} is not reachable from {row["target_branch"]} ({head}); the claim stays held',
                   head=head)
        with self.tx() as db:
            if self._task(db, task)['status'] == 'merged':
                return self._task_view(db, task)
            db.execute("UPDATE tasks SET status='merged', merged_revision=?, updated=? WHERE id=?", (revision, self.clock(), task))
            self._event(db, 'task.merged', actor, task, data={'revision': revision, 'target_head': head})
            for claim in [r['id'] for r in db.execute("SELECT id FROM claims WHERE task=? AND state IN ('pending','active')", (task,))]:
                self._end(db, claim, 'merged')
            return self._task_view(db, task)

    def unlocked(self, actor, claim, path):
        """Record a released lock after the remote shows it is gone."""
        with self.lock:
            row = self._claim(self.db, claim)
            if row['principal'] != actor and actor not in self.coordinators:
                refuse('not_holder', f'claim {claim} is held by {row["principal"]!r}', 403)
            lock = self._lock_row(self.db, claim, path)
            if lock['state'] != 'releasing':
                refuse('lock_state', f'{path!r} is {lock["state"]}, not releasing')
        try:
            still = [l for l in self.lfs.locks(path=path) if l.id == lock['lock_id']]
        except Unavailable as error:
            refuse('lfs_unavailable', f'cannot verify the unlock: {error}', 503)
        if still:
            refuse('still_locked', f'lock {lock["lock_id"]} on {path!r} is still on the remote')
        with self.tx() as db:
            if self._lock_row(db, claim, path)['rev'] != lock['rev']:
                refuse('lock_state', f'{path!r} changed while its unlock was verified; retry')
            db.execute("UPDATE locks SET state='released', updated=? WHERE claim=? AND path=? AND state='releasing'",
                       (self.clock(), claim, path))
            self._event(db, 'lock.released', actor, row['task'], claim, {'path': path, 'lock_id': lock['lock_id']})
            self._settle(db, claim)
            return self._claim_view(db, claim)

    # ------------------------------------------------------------------ recovery and reconciliation

    def recover(self, actor, claim, action, reason, old_writer_stopped=False, preserved=None, to_workspace=None,
                path=None, decision=None, lock_id=None):
        """Explicit coordinator operation: transfer or release a claim after the old writer stopped and its
        work was preserved, or resolve one uncertain/bootstrap lock. Records who and why."""
        reason = _text(reason, 'reason')
        if action in ('transfer', 'release') and (old_writer_stopped is not True or not preserved):
            refuse('invalid', 'recovery needs old_writer_stopped=true and where the old work was preserved', 400)
        if action == 'resolve':
            return self._resolve(actor, claim, path, decision, lock_id, reason)
        with self.tx() as db:
            self._coordinator(db, actor)
            row = self._claim(db, claim)
            if row['state'] not in HOLDING:
                refuse('not_holding', f'claim {claim} is {row["state"]}')
            data = {'action': action, 'reason': reason, 'preserved': preserved, 'from': row['principal'],
                    'from_workspace': row['workspace']}
            if action == 'transfer':
                target = self._workspace(db, _text(to_workspace, 'to_workspace'))
                old, new = (self._principal(db, p)['git_account'] for p in (row['principal'], target['principal']))
                owned = db.execute("SELECT COUNT(*) FROM locks WHERE claim=? AND state IN ('created','verified','releasing')",
                                   (claim,)).fetchone()[0]
                if owned and old != new:
                    refuse('account_mismatch', 'the new owner uses another LFS account; release and grant again instead')
                db.execute('UPDATE claims SET principal=?, workspace=?, updated=? WHERE id=?',
                           (target['principal'], target['id'], self.clock(), claim))
                db.execute('UPDATE tasks SET owner=?, workspace=?, updated=? WHERE id=?',
                           (target['principal'], target['id'], self.clock(), row['task']))
                data.update(to=target['principal'], to_workspace=target['id'])
                self._event(db, 'claim.recovered', actor, row['task'], claim, data)
            elif action == 'release':
                self._event(db, 'claim.recovered', actor, row['task'], claim, data)
                if row['ending'] is None:
                    self._end(db, claim, 'recovered')
            else:
                refuse('invalid', 'action must be transfer, release or resolve', 400)
            return self._claim_view(db, claim)

    def _resolve(self, actor, claim, path, decision, lock_id, reason):
        if decision not in ('adopt', 'foreign'):
            refuse('invalid', 'decision must be adopt (the lock belongs to this claim) or foreign', 400)
        with self.lock:
            self._coordinator(self.db, actor)
            row = self._claim(self.db, claim)
            lock = self._lock_row(self.db, claim, path)
            account = self._principal(self.db, row['principal'])['git_account']
        if lock['state'] not in RETRYABLE:
            refuse('lock_state', f'{path!r} is {lock["state"]}; only an unresolved lock can be resolved')
        prior = None if lock['prior'] is None else set(json.loads(lock['prior']))
        if decision == 'adopt':
            lock_id = _text(lock_id, 'lock_id')
            if prior is None and (row['state'] not in ('pending', 'active') or row['ending']):
                # Handing a pre-existing (bootstrap) lock over is only for a live claim that never attempted it.
                refuse('lock_state', f'claim {claim} is {row["state"]} and never attempted {path!r}; '
                       'only a live claim may take over a pre-existing lock')
            if prior is not None and lock['state'] == 'refused':
                refuse('lock_state', f'the attempt on {path!r} was refused or resolved foreign; it made no lock')
            if prior is not None and lock_id in prior:
                refuse('pre_existing', f'lock {lock_id} existed before the attempt on {path!r}; it is not this claim\'s')
            try:
                remote = [l for l in self.lfs.locks(path=path) if l.id == lock_id]
            except Unavailable as error:
                refuse('lfs_unavailable', f'cannot verify the adopted lock: {error}', 503)
            if len(remote) != 1 or remote[0].path != path or remote[0].owner != account:
                refuse('lock_unverified', f'lock {lock_id} on {path!r} is not held by {account!r} on the remote')
        with self.tx() as db:
            if self._lock_row(db, claim, path)['rev'] != lock['rev']:
                refuse('lock_state', f'{path!r} changed while it was resolved')
            if decision == 'adopt' and self._others_could_own(db, claim, path, remote[0]):
                refuse('ambiguous', f'lock {lock_id} may belong to another claim\'s attempt on {path!r}')
            ending = self._claim(db, claim)['ending']
            state = ('refused' if decision == 'foreign' else 'releasing' if ending else 'created')
            db.execute('UPDATE locks SET state=?, lock_id=?, owner=?, updated=? WHERE claim=? AND path=?',
                       (state, lock_id if decision == 'adopt' else None, account if decision == 'adopt' else None,
                        self.clock(), claim, path))
            self._event(db, 'lock.resolved', actor, row['task'], claim,
                        {'path': path, 'decision': decision, 'lock_id': lock_id, 'reason': reason})
            self._settle(db, claim)
            return self._claim_view(db, claim)

    def reconcile(self, actor):
        """Compare every recorded lock with the remote, resolve what the evidence proves, then allow grants.
        A lock whose ID was absent before the intent and now belongs to the claimant was created by that attempt;
        a lock that existed before the intent, or belongs to another account, is never ours.

        Large migrations use a complete paginated listing, indexed by path. No state is changed until that
        listing finishes; each row's revision still rejects evidence superseded by another attempt."""
        with self.lock:
            self._principal(self.db, actor)
            rows = [dict(r) for r in self.db.execute(
                'SELECT l.*, c.principal, c.ending, c.task FROM locks l JOIN claims c ON c.id=l.claim '
                "WHERE l.state IN ('requested','uncertain','abandoned','created','verified','releasing')")]
            accounts = {r['name']: r['git_account'] for r in self.db.execute('SELECT name, git_account FROM principals')}
        listed_at = self.clock()  # every listing below is at least this recent
        try:
            paths = {r['path'] for r in rows}
            if len(paths) > LIST_ALL_LOCKS_ABOVE:
                remote = {path: [] for path in paths}
                for lock in self.lfs.locks():
                    if lock.path in remote:
                        remote[lock.path].append(lock)
            else:
                remote = {path: self.lfs.locks(path=path) for path in paths}
        except Unavailable as error:
            refuse('lfs_unavailable', f'reconcile needs the LFS remote: {error}', 503)
        changes = []
        with self.tx() as db:
            for r in rows:
                if self._lock_row(db, r['claim'], r['path'])['rev'] != r['rev']:
                    continue  # changed since it was listed (for example a fresh attempt): the listing is stale
                here = [l for l in remote[r['path']] if l.path == r['path']]
                account = accounts.get(r['principal'])
                new = None
                if r['state'] in UNRESOLVED:
                    prior = set(json.loads(r['prior'] or '[]'))
                    candidates = [l for l in here if l.id not in prior and l.owner == account]
                    proven = [l for l in candidates if self._proven_own(db, r['claim'], r['path'], prior, account, l)]
                    if len(candidates) == 1 and len(proven) == 1:
                        new = ('releasing' if r['ending'] else 'created', proven[0].id)
                    elif candidates:
                        new = None  # several or ambiguous candidates: a coordinator resolves
                    elif r['state'] == 'uncertain' and listed_at - r['updated'] >= self.uncertain_settle:
                        # No lock appeared long after the request could still land: settle without a lock. A later
                        # lock proven this attempt's is still found and released from the abandoned row.
                        new = ('abandoned', None)
                    elif r['state'] == 'requested':
                        new = ('uncertain', None) if r['ending'] else None
                elif r['state'] in ('created', 'verified'):
                    if not any(l.id == r['lock_id'] for l in here):
                        new = ('lost', None)
                elif r['state'] == 'releasing' and not any(l.id == r['lock_id'] for l in here):
                    new = ('released', r['lock_id'])
                if new is None:
                    continue
                state, lock_id = new
                if state == 'lost':
                    # A verified lock vanished: the claim stays reserved but stops authorizing writes.
                    db.execute("UPDATE locks SET state='needed', lock_id=NULL, owner=NULL, detail=?, updated=? "
                               'WHERE claim=? AND path=?', (f'lock {r["lock_id"]} missing at reconcile', self.clock(),
                                                            r['claim'], r['path']))
                    db.execute("UPDATE claims SET state='pending', updated=? WHERE id=? AND state='active'",
                               (self.clock(), r['claim']))
                else:
                    db.execute('UPDATE locks SET state=?, lock_id=?, owner=?, updated=? WHERE claim=? AND path=?',
                               (state, lock_id, account if lock_id else None, self.clock(), r['claim'], r['path']))
                changes.append({'claim': r['claim'], 'path': r['path'], 'from': r['state'], 'to': state, 'lock_id': lock_id})
                self._settle(db, r['claim'])
            self.ready = True
            self._event(db, 'service.reconciled', actor, data={'changes': changes, 'checked': len(rows)})
            return {'state': 'ready', 'changes': changes, 'checked': len(rows)}

    # ------------------------------------------------------------------ reads

    def coverage(self, task):
        """What a protected check needs: the task's held claims with items and lock states, each active claim
        re-verified live (every LFS lock's path, ID and owner on the remote, and the base against the target
        branch). An unreachable LFS server or Git remote refuses the check (fail closed)."""
        with self.lock:
            view = self._task_view(self.db, task)
            ready = self.ready
            claims = [c for c in view['claims'] if c['state'] in HOLDING]
            accounts = {c['id']: self._principal(self.db, c['principal'])['git_account'] for c in claims}
            reads = [tuple(r) for r in view['reads']]
            revs = self._revisions(self.db, [c['id'] for c in claims])
        result = {'service': 'ready' if ready else 'reconciling', 'task': task, 'status': view['status'], 'claims': claims}
        if not ready:
            return result
        active = [c for c in claims if c['state'] == 'active']
        # One remote read per check, shared by its claims: a task of many claims costs one lock listing and one
        # target-branch fetch, not one of each per claim. Every lock and base is still read from the remotes now.
        listed, head = None, None
        if sum(len(c['locks']) for c in active) > LIST_ALL_LOCKS_ABOVE:
            try:
                listed = self.lfs.locks()
            except Unavailable as error:
                refuse('lfs_unavailable', f'cannot verify LFS locks: {error}', 503)
        if len(active) > 1:
            try:
                head = self.git.head(view['target_branch'])
            except Unavailable as error:
                refuse('git_unavailable', f'cannot verify the base revision: {error}', 503)
        for c in active:
            problems = self._lock_problems(c['locks'], accounts[c['id']], listed)
            items = [(i['kind'], i['value']) for i in c['items'] if i['kind'] != 'scope']
            try:
                self._base_check(view['target_branch'], c['base_revision'], items + reads, head)
            except ClaimError as error:
                if error.code != 'stale_base':
                    raise
                problems.append({'base': error.message})
            c['verified'], c['problems'] = not problems, problems
        with self.lock:  # a claim or lock that changed while it was verified is not verified
            changed = self._revisions(self.db, [c['id'] for c in claims]) != revs
        for c in claims:
            if changed and c.get('verified'):
                c['verified'], c['problems'] = False, [{'changed': 'the claim changed while it was verified; retry'}]
        return result

    @staticmethod
    def _revisions(db, claims):
        marks = ','.join('?' * len(claims))
        return ([tuple(r) for r in db.execute(f'SELECT id, state, updated FROM claims WHERE id IN ({marks}) ORDER BY id', claims)],
                [tuple(r) for r in db.execute(f'SELECT claim, path, rev FROM locks WHERE claim IN ({marks}) '
                                              'ORDER BY claim, path', claims)])

    def events(self, after=0, limit=500):
        limit = max(1, min(int(limit), 1000))
        with self.lock:
            rows = self.db.execute('SELECT * FROM events WHERE seq>? ORDER BY seq LIMIT ?', (int(after), limit)).fetchall()
            return {'events': [{**dict(r), 'data': json.loads(r['data'])} for r in rows],
                    'cursor': rows[-1]['seq'] if rows else int(after)}

    def status(self):
        with self.lock:
            counts = {r['state']: r['n'] for r in self.db.execute('SELECT state, COUNT(*) n FROM claims GROUP BY state')}
            last = self.db.execute('SELECT MAX(seq) FROM events').fetchone()[0] or 0
            return {'service': 'ready' if self.ready else 'reconciling', 'claims': counts, 'cursor': last}
