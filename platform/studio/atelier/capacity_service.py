"""Durable offline capacity lifecycle experiments. Nothing here authorizes native work.

The explicit database and supplied observations belong to a simulation, not the machine's
render state. No live process adapter, daemon, launcher integration or default state path exists.
"""
from dataclasses import asdict, dataclass, field
import hashlib
import json
import os
from pathlib import Path
import secrets
import sqlite3
import stat

from .capacity import Request, Resources, conflicts

ACTIVE = frozenset(('reserved', 'registered', 'running', 'uncertain'))
MAX_AGE = 30
APPLICATION_ID = 0x41545348
TABLES = {
    'state': 'CREATE TABLE state (id INTEGER PRIMARY KEY CHECK(id=1), body TEXT NOT NULL)',
    'operations': 'CREATE TABLE operations (id TEXT PRIMARY KEY, body TEXT NOT NULL, result TEXT NOT NULL)',
}
ARGUMENTS = {
    'init': {'total', 'reserve'}, 'status': set(), 'restart': set(), 'reconcile': set(),
    'submit': {'request_id', 'owner', 'checkout', 'resources', 'locks', 'seconds', 'performance', 'launcher', 'ready'},
    'ready': {'request_id', 'launcher'}, 'cancel': {'request_id'}, 'schedule': set(),
    'register': {'request_id', 'token', 'child'}, 'running': {'request_id', 'token', 'guard_ready'},
    'heartbeat': {'request_id', 'token'}, 'release': {'request_id', 'token'},
    'replace': {'request_id', 'token', 'resources', 'locks', 'performance'},
}


def number(value):
    if type(value) is not int or not 0 <= value < 2**63:
        raise ValueError('Expected a nonnegative integer below 2**63')
    return value


def name(value):
    if not isinstance(value, str) or not 0 < len(value) <= 256:
        raise ValueError('Expected a nonempty name of at most 256 characters')
    return value


def identity(value):
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        raise ValueError('A process identity needs pid and start')
    pid, start = map(number, value)
    if pid <= 1 or start == 0:
        raise ValueError('A process identity needs positive pid and start')
    return f'{pid}:{start}'


@dataclass(frozen=True)
class Observation:
    """Supplied simulation facts; absence never means a process exited."""
    at: int
    healthy: bool = False
    complete: bool = False
    available_mib: int = 0
    disk_available_mib: int = 0
    processes: dict = field(default_factory=dict)  # "pid:start": alive/dead/unknown
    edges: tuple = ()                            # pinned parent/child identity strings
    measured_mib: dict = field(default_factory=dict)
    allocated_temp_mib: dict = field(default_factory=dict)

    def __post_init__(self):
        for value in (self.at, self.available_mib, self.disk_available_mib):
            number(value)
        if type(self.healthy) is not bool or type(self.complete) is not bool:
            raise ValueError('Observation flags must be boolean')
        for key, state in self.processes.items():
            identity([int(v) for v in key.split(':')])
            if state not in ('alive', 'dead', 'unknown'):
                raise ValueError('Invalid process observation')
        for parent, child in self.edges:
            if parent not in self.processes or child not in self.processes:
                raise ValueError('Ownership edges need observed pinned identities')
        for amounts in (self.measured_mib, self.allocated_temp_mib):
            for key, value in amounts.items():
                name(key)
                number(value)


def encode(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)


def request(record):
    return Request(record['request_id'], Resources(**record['resources']), tuple(record['locks']),
                   record['ready_at'] or 0, record['seconds'], record['bypasses'], record['performance'])


class ShadowService:
    """@cc [owner:fontanierh,label:safety] isolated-shadow-lifecycle
    This service MUST only mutate its explicitly supplied simulation database. Every response
    MUST say admission false. It MUST NOT import native safety modules, launch or signal work,
    or read/write the machine's live locks, scheduler state or telemetry.
    """
    def __init__(self, database, *, observe=None, before_commit=None):
        self.database = Path(database)
        self.observe = observe or (lambda now: Observation(now))
        self.before_commit = before_commit
        if not self.database.is_absolute():
            raise ValueError('The shadow database needs an explicit absolute path')

    def _connect(self):
        # A private directory excludes another user's SQLite sidecar/path substitution.
        # Permit only the operating system's conventional root aliases in ancestors.
        for part in [self.database.parent, *self.database.parent.parents]:
            info = part.lstat()
            if stat.S_ISLNK(info.st_mode) and str(part) not in ('/tmp', '/var', '/etc'):
                raise ValueError('Shadow database ancestors cannot be symlinks')
        parent = self.database.parent.resolve(strict=True)
        info = parent.stat()
        if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) & 0o077:
            raise ValueError('Shadow database directory must be owner-only')
        path = parent / self.database.name
        for sibling in [path, *(Path(str(path) + suffix) for suffix in ('-journal', '-wal', '-shm'))]:
            try:
                info = sibling.lstat()
            except FileNotFoundError:
                continue
            if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_uid != os.getuid() or
                    stat.S_IMODE(info.st_mode) & 0o077):
                raise ValueError('Shadow database and sidecars must be private owned single-link regular files')
        try:
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
        except FileExistsError:
            fd = None
        created = fd is not None
        if fd is not None:
            os.close(fd)
        before = path.lstat()
        if before.st_size > 64 * 1024 * 1024:
            raise ValueError('Shadow database exceeds the 64 MiB experiment limit')
        if not created:
            # Immutable inspection cannot replay a journal or create SQLite sidecars in
            # an unrelated database before its namespace/version/schema is validated.
            probe = sqlite3.connect(path.as_uri() + '?mode=ro&immutable=1', uri=True)
            try:
                if (probe.execute('PRAGMA application_id').fetchone()[0] != APPLICATION_ID or
                        probe.execute('PRAGMA user_version').fetchone()[0] != 1 or
                        dict(probe.execute("SELECT name,sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'")) != TABLES):
                    raise ValueError('Not a supported shadow capacity database')
            finally:
                probe.close()
        connection = sqlite3.connect(path.as_uri() + '?mode=rw', uri=True, timeout=5, isolation_level=None)
        try:
            after = path.lstat()
            if (before.st_dev, before.st_ino) != (after.st_dev, after.st_ino):
                raise ValueError('Shadow database changed while opening')
            if created:
                connection.execute('BEGIN IMMEDIATE')
                connection.execute(f'PRAGMA application_id={APPLICATION_ID}')
                connection.execute('PRAGMA user_version=1')
                for sql in TABLES.values():
                    connection.execute(sql)
                connection.commit()
            if (connection.execute('PRAGMA application_id').fetchone()[0] != APPLICATION_ID or
                    connection.execute('PRAGMA user_version').fetchone()[0] != 1):
                raise ValueError('Not a supported shadow capacity database')
            schema = dict(connection.execute("SELECT name,sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'"))
            if schema != TABLES:
                raise ValueError('Unknown shadow capacity database schema')
            connection.execute('PRAGMA synchronous=FULL')
            return connection
        except BaseException:
            connection.close()
            raise

    def apply(self, operation, *, now):
        """@cc [owner:fontanierh,label:correctness] atomic-shadow-transaction
        Every mutation, complete resource vector, named-lock claim, fairness update and retry
        receipt MUST commit in one serialized transaction or none. Refused replacements MUST
        preserve the previous allocation. A queued request MUST hold no allocation or lock.
        """
        number(now)
        action = name(operation['action'])
        if action not in ARGUMENTS or set(operation) - {'id', 'action', 'epoch'} - ARGUMENTS[action]:
            raise ValueError('Unknown shadow operation or fields')
        if 'epoch' in operation:
            number(operation['epoch'])
        operation_id = name(operation['id'])
        body = encode(operation)
        if len(body) > 65536:
            raise ValueError('Shadow operation is too large')
        connection = self._connect()
        try:
            connection.execute('BEGIN IMMEDIATE')
            previous = connection.execute('SELECT body, result FROM operations WHERE id=?', (operation_id,)).fetchone()
            if previous:
                if previous[0] != body:
                    raise ValueError('Operation id reused with different content')
                connection.commit()
                return json.loads(previous[1])
            row = connection.execute('SELECT body FROM state WHERE id=1').fetchone()
            state = json.loads(row[0]) if row else None
            if state is not None and (state.get('schema') != 1 or state.get('mode') != 'shadow'):
                raise ValueError('Unknown shadow capacity state version')
            if state is not None and now < state['last_now']:
                raise ValueError('Shadow service time cannot move backwards')
            result = self._apply(state, operation, now)
            state = result.pop('_state', state)
            state['last_now'] = now
            result.update(mode='shadow', admission=False, epoch=state['epoch'])
            self._validate(state)
            connection.execute('INSERT OR REPLACE INTO state VALUES (1, ?)', (encode(state),))
            connection.execute('INSERT INTO operations VALUES (?, ?, ?)', (operation_id, body, encode(result)))
            if self.before_commit:
                self.before_commit()
            connection.commit()
            return result
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _apply(self, state, op, now):
        action = op['action']
        if action == 'init':
            if state is not None:
                raise ValueError('Shadow database is already initialized')
            total, reserve = Resources(**op['total']), Resources(**op['reserve'])
            if reserve.excess(total):
                raise ValueError('Host reserve exceeds total capacity')
            state = dict(schema=1, mode='shadow', epoch=1, recovering=False, total=asdict(total), reserve=asdict(reserve),
                         sequence=0, requests={}, owner_turn={})
            return dict(result='initialized', _state=state)
        if state is None:
            raise ValueError('Initialize the shadow database first')
        if op.get('epoch') != state['epoch']:
            raise ValueError('Stale shadow service epoch')
        records = state['requests']
        holders = [r for r in records.values() if r['state'] in ACTIVE]
        if action == 'status':
            public = [{k: v for k, v in r.items() if k != 'token_hash'} for r in records.values()]
            return dict(result='status', recovering=state['recovering'], requests=public)
        if action == 'restart':
            state['epoch'] += 1
            state['recovering'] = True
            for holder in holders:
                holder['state'] = 'uncertain'
            return dict(result='recovery-required')
        observation = self.observe(now)
        if not isinstance(observation, Observation):
            raise ValueError('A typed simulation observation is required')
        fresh = 0 <= now - observation.at <= MAX_AGE
        if action == 'reconcile':
            if not fresh or not observation.complete:
                return dict(result='wait', reasons=['complete fresh ownership observations required'])
            for holder in holders:
                self._discover(holder, observation)
                if self._exited(holder, observation):
                    self._clear(holder)
            state['recovering'] = any(r['state'] in ACTIVE for r in records.values())
            # Surviving jobs stay charged and fenced. This first offline protocol recovers
            # by draining, rather than inventing a safe guard/launcher reattachment.
            return dict(result='wait' if state['recovering'] else 'reconciled')
        if action == 'submit':
            if 'ready' in op and type(op['ready']) is not bool:
                raise ValueError('ready must be boolean')
            rid = name(op['request_id'])
            if rid in records:
                raise ValueError('Request id already exists; retry with the same operation id')
            state['sequence'] += 1
            value = Request(rid, Resources(**op['resources']), tuple(op.get('locks', ())),
                            seconds=op.get('seconds', 300), performance=op.get('performance', False))
            records[rid] = dict(request_id=rid, owner=name(op['owner']), checkout=name(op['checkout']),
                                resources=asdict(value.resources), locks=list(value.locks), seconds=value.seconds,
                                performance=value.performance, bypasses=0, ready_at=None, ready_sequence=None,
                                state='blocked', launcher=identity(op['launcher']), identities=[], heartbeat=None)
            if op.get('ready', True) is not False:
                self._ready(state, records[rid], now)
            return dict(result='submitted')
        if action in ('ready', 'cancel'):
            record = records[op['request_id']]
            if record['state'] in ACTIVE:
                raise ValueError('A holder must release all resources and locks before queueing or cancellation')
            if action == 'cancel':
                if record['state'] == 'released':
                    raise ValueError('A released request is already terminal; ready it with a new launcher')
                record['state'] = 'cancelled'
            else:
                if record['state'] == 'released':
                    record['launcher'] = identity(op['launcher'])
                    record['identities'] = []
                self._ready(state, record, now)
            return dict(result=record['state'])
        if action == 'schedule':
            return self._schedule(state, holders, observation, now, fresh)
        record = records[op['request_id']]
        self._lease(record, op, state)
        self._discover(record, observation)
        if action == 'release':
            if not fresh or not self._exited(record, observation):
                record['state'] = 'uncertain'
                return dict(result='wait', reasons=['owned process tree exit is unproven'])
            self._clear(record)
            return dict(result='released')
        if (state['recovering'] or record['state'] == 'uncertain' or not fresh or
                not observation.healthy or not observation.complete or
                now - record['heartbeat'] > MAX_AGE or
                any(observation.processes.get(key) != 'alive'
                    for key in [record['launcher'], *record['identities']])):
            record['state'] = 'uncertain'
            return dict(result='wait', reasons=['recovery or fresh healthy observations required'])
        if action == 'register':
            if record['state'] != 'reserved':
                raise ValueError('Only a reserved shadow lease can register a child')
            child = identity(op['child'])
            if (observation.processes.get(record['launcher']) != 'alive' or
                    observation.processes.get(child) != 'alive' or
                    [record['launcher'], child] not in [list(edge) for edge in observation.edges]):
                raise ValueError('Child ownership needs a live pinned launcher/child edge')
            record['identities'] = sorted(set(record['identities']) | {child})
            record['state'] = 'registered'
        elif action == 'running':
            if record['state'] != 'registered' or op.get('guard_ready') is not True:
                raise ValueError('Running requires child registration and a supplied guard-ready receipt')
            record['state'] = 'running'
        elif action == 'heartbeat':
            if record['state'] not in ('reserved', 'registered', 'running'):
                raise ValueError('An uncertain lease cannot renew itself')
        elif action == 'replace':
            replacement = Request(record['request_id'], Resources(**op['resources']), tuple(op.get('locks', ())),
                                  performance=op.get('performance', record['performance']))
            others = [h for h in holders if h is not record]
            reasons = conflicts(replacement, [request(r) for r in others],
                                Resources(**state['total']), Resources(**state['reserve']))
            measured = observation.measured_mib.get(record['request_id'], 0 if record['state'] == 'reserved' else None)
            allocated = observation.allocated_temp_mib.get(record['request_id'], 0 if record['state'] == 'reserved' else None)
            if measured is None or allocated is None:
                reasons.append('replacement growth headroom is unknown')
            else:
                growth = Resources(memory_mib=max(0, replacement.resources.memory_mib - measured),
                                   temp_mib=max(0, replacement.resources.temp_mib - allocated))
                reasons += self._pressure(growth, others, observation, state)
                if allocated > replacement.resources.temp_mib:
                    reasons.append('replacement ceiling lacks observed disk headroom')
            if measured is None or measured > replacement.resources.memory_mib:
                reasons.append('replacement ceiling lacks observed memory headroom')
            if reasons:
                return dict(result='wait', reasons=reasons)
            record.update(resources=asdict(replacement.resources), locks=list(replacement.locks),
                          performance=replacement.performance)
        else:
            raise ValueError('Unknown shadow operation')
        record['heartbeat'] = now
        return dict(result=record['state'])

    @staticmethod
    def _ready(state, record, now):
        if record['ready_at'] is None:
            state['sequence'] += 1
            record['ready_at'], record['ready_sequence'] = now, state['sequence']
        record['state'] = 'queued'

    @staticmethod
    def _lease(record, op, state):
        token = op.get('token', '')
        if (record['state'] not in ACTIVE or record.get('lease_epoch') != state['epoch'] or
                not isinstance(token, str) or not token.startswith('shadow.') or
                not secrets.compare_digest(hashlib.sha256(token.encode()).hexdigest(), record.get('token_hash', ''))):
            raise ValueError('Invalid or fenced shadow lease')

    @staticmethod
    def _discover(record, observation):
        owned = set(record['identities'])
        roots = owned | {record['launcher']}
        # New edges must join two live pinned identities. Retained descendants survive
        # detached parents; a reused pid has a different identity and cannot join the tree.
        for _ in observation.edges:
            for parent, child in observation.edges:
                if parent in roots and observation.processes.get(parent) == observation.processes.get(child) == 'alive':
                    owned.add(child)
                    roots.add(child)
        record['identities'] = sorted(owned)

    @staticmethod
    def _exited(record, observation):
        """@cc [owner:fontanierh,label:safety] retain-uncertain-shadow-charges
        Missing samples, expired heartbeats, launcher exit and PID reuse MUST NOT establish
        whole-tree exit. Accounting and named locks MUST remain charged until a fresh complete
        observation explicitly reports the pinned launcher and every retained descendant dead.
        """
        return observation.complete and all(observation.processes.get(key) == 'dead'
                                            for key in [record['launcher'], *record['identities']])

    @staticmethod
    def _clear(record):
        record['state'] = 'released'
        record.pop('token_hash', None)
        record.pop('lease_epoch', None)

    @staticmethod
    def _pressure(resources, holders, observation, state):
        memory, disk = resources.memory_mib, resources.temp_mib
        for holder in holders:
            rid = holder['request_id']
            measured = observation.measured_mib.get(rid, 0 if holder['state'] == 'reserved' else None)
            allocated = observation.allocated_temp_mib.get(rid, 0 if holder['state'] == 'reserved' else None)
            if measured is None or allocated is None:
                return ['holder growth headroom is unknown']
            if measured > holder['resources']['memory_mib'] or allocated > holder['resources']['temp_mib']:
                return ['holder exceeded its reservation']
            memory += holder['resources']['memory_mib'] - measured
            disk += holder['resources']['temp_mib'] - allocated
        reasons = []
        if memory + state['reserve']['memory_mib'] > observation.available_mib:
            reasons.append('live memory growth headroom')
        if disk + state['reserve']['temp_mib'] > observation.disk_available_mib:
            reasons.append('live disk growth headroom')
        return reasons

    def _schedule(self, state, holders, observation, now, fresh):
        for holder in holders:
            self._discover(holder, observation)
            if (holder['heartbeat'] is None or now - holder['heartbeat'] > MAX_AGE or
                    any(observation.processes.get(key) != 'alive'
                        for key in [holder['launcher'], *holder['identities']])):
                holder['state'] = 'uncertain'
        if state['recovering'] or any(h['state'] == 'uncertain' for h in holders):
            return dict(result='wait', reasons=['ownership reconciliation required'])
        if not fresh or not observation.healthy or not observation.complete:
            return dict(result='wait', reasons=['fresh healthy complete observations required'])
        total, reserve = Resources(**state['total']), Resources(**state['reserve'])
        ready = sorted((r for r in state['requests'].values() if r['state'] == 'queued'),
                       key=lambda r: (r['ready_sequence'], r['request_id']))
        feasible, decisions = [], []
        for record in ready:
            exceeded = (reserve + request(record).resources).excess(total)
            if exceeded:
                decisions.append(dict(request_id=record['request_id'], result='cannot-fit', reasons=exceeded))
            else:
                feasible.append(record)
        protected = next((r for r in feasible if r['bypasses'] >= 2), None)
        ranked = sorted(feasible, key=lambda r: (r is not protected if protected else False,
                         r['seconds'] > 300, state['owner_turn'].get(r['owner'], -1), r['ready_sequence']))
        drain = False
        for record in ranked:
            candidate = request(record)
            reasons = conflicts(candidate, [request(h) for h in holders], total, reserve)
            reasons += self._pressure(candidate.resources, holders, observation, state)
            if any(h['owner'] == record['owner'] for h in holders):
                reasons.append('owner already has an active phase')
            if observation.processes.get(record['launcher']) != 'alive':
                reasons.append('pinned launcher is not observed alive')
            if drain:
                reasons.append('drain for oldest protected waiter')
            # Bypasses committed earlier in this same batch count immediately.
            barrier = next((r for r in feasible if r['state'] == 'queued' and r['bypasses'] >= 2), None)
            if barrier is not None and barrier is not record:
                reasons.append('drain for oldest protected waiter')
            if record is protected and reasons:
                drain = True
            if reasons:
                decisions.append(dict(request_id=candidate.id, result='wait', reasons=reasons))
                continue
            token = 'shadow.' + secrets.token_urlsafe(32)
            record.update(state='reserved', lease_epoch=state['epoch'], heartbeat=now,
                          token_hash=hashlib.sha256(token.encode()).hexdigest())
            holders.append(record)
            state['sequence'] += 1
            state['owner_turn'][record['owner']] = state['sequence']
            for older in feasible:
                if (older['state'] == 'queued' and older['seconds'] > 300 and
                        older['ready_sequence'] < record['ready_sequence'] and record['seconds'] <= 300):
                    older['bypasses'] += 1
            decisions.append(dict(request_id=candidate.id, result='reserved', token=token))
        return dict(result='scheduled', decisions=decisions)

    @staticmethod
    def _validate(state):
        holders = [r for r in state['requests'].values() if r['state'] in ACTIVE]
        locks = [lock for r in holders for lock in r['locks']]
        if len(locks) != len(set(locks)):
            raise ValueError('Conflicting shadow named locks')
        used = Resources(**state['reserve'])
        for holder in holders:
            used += Resources(**holder['resources'])
        if used.excess(Resources(**state['total'])):
            raise ValueError('Shadow allocations exceed the resource vector')
        if any(r['state'] not in ACTIVE and 'token_hash' in r for r in state['requests'].values()):
            raise ValueError('A queued request cannot retain a shadow lease')


def main(database, path, *, echo=print):
    """Apply a bounded operation fixture; supplied observations never claim live authority."""
    with Path(path).open('rb') as source:
        data = source.read(4 * 1024 * 1024 + 1)
    if len(data) > 4 * 1024 * 1024:
        raise ValueError('Shadow fixture exceeds 4 MiB')
    fixture = json.loads(data)
    if fixture.get('schema') != 1 or not isinstance(fixture.get('operations'), list) or len(fixture['operations']) > 1000:
        raise ValueError('Expected schema 1 and at most 1000 operations')
    results = []
    for item in fixture['operations']:
        observation = Observation(**item.get('observation', {'at': item['now']}))
        service = ShadowService(database, observe=lambda now, value=observation: value)
        results.append(service.apply(item['operation'], now=item['now']))
    echo(json.dumps(dict(mode='shadow', admission=False, results=results), indent=2))
    return 0
