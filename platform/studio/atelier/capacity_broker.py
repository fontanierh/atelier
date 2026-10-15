"""Production Unix capacity broker. Native activation and supervision are separate policy.

One serialized actor owns the SQLite transaction and every launch-gate writer. Restart fences
all old sessions and retains their allocations. Release uses exact retained exits or the scoped
exclusive monitored-tree cleanup policy; neither establishes universal process-tree discovery.
"""
from dataclasses import asdict
import fcntl
import hashlib
import hmac
import json
import math
import os
from pathlib import Path
import secrets
import selectors
import socket
import sqlite3
import stat
import sys
import threading
import time

from .capacity import Request, Resources, conflicts
from . import capacity_protocol as wire

APPLICATION_ID = 0x41434231
SCHEMA = 'CREATE TABLE state (id INTEGER PRIMARY KEY CHECK(id=1), value TEXT NOT NULL)'
MAX_DATABASE = 32 * 1024 * 1024
HELD = {'running', 'draining', 'uncertain'}


class CapacityBroker:
    """@cc [owner:fontanierh,label:safety] production-serialized-capacity-gate
    Queued offers MUST charge no resources. Final complete-vector and lock accounting MUST commit
    before this broker's sole gate writer releases a child, in one serialized actor turn. Restart,
    lost health and missing exit evidence MUST retain grants. No process MAY be signalled here.
    Exact exit evidence covers the retained roster only. Bridge and performance-exclusive grants
    MAY instead use a positively exited root plus its bound aggregate guard's terminal empty-tree
    cleanup receipt; that witnesses the monitored owned tree, not every descendant's kernel exit.
    The adapter MUST retain exclusive legacy exclusion in bridge
    mode, or verified sealed shared compatibility mutexes in full mode.
    """
    def __init__(self, state_directory, *, total, reserve=Resources(), disk_pool=None,
                 observe=None, lease_seconds=10., rpc_timeout=2., started=wire.process_start,
                 watch=wire.ExitWatch, guards=wire.validate_guards, child_of=wire.direct_child,
                 parent=wire.parent_pin, boot=wire.boot_id, alive=wire.live, mode='legacy-bridge',
                 cutover=None, policy_sha256=None, foreign=None):
        if mode not in ('legacy-bridge', 'capacity'):
            raise wire.CapacityError('Unsupported production capacity mode')
        self.mode, self.cutover, self.policy_sha256 = mode, cutover, policy_sha256
        self.activation_id, self.compatible = None, True
        if mode == 'capacity':
            from . import capacity_compat
            if (not isinstance(policy_sha256, str) or len(policy_sha256) != 64
                    or Path(cutover or '') != capacity_compat.DEFAULT_RECORD):
                raise wire.CapacityError('Full capacity requires the sealed machine policy')
            proof = capacity_compat.verify(cutover, policy_sha256=policy_sha256)
            self.activation_id = proof['activation_id']
        self.foreign = foreign
        self.directory = Path(state_directory)
        if not self.directory.is_absolute() or not 1 <= lease_seconds <= 300 or not .1 <= rpc_timeout <= 5:
            raise wire.CapacityError('Invalid broker directory or deadline')
        self.total = total if isinstance(total, Resources) else wire.resources(total)
        self.reserve = reserve if isinstance(reserve, Resources) else wire.resources(reserve)
        if self.reserve.excess(self.total):
            raise wire.CapacityError('Host reserve exceeds capacity')
        self.disk_pool = Path(disk_pool or self.directory)
        if not self.disk_pool.is_absolute() or not self.disk_pool.is_dir():
            raise wire.CapacityError('Capacity disk pool must be an existing absolute directory')
        self.observe = observe or (lambda: wire.pressure(self.disk_pool))
        self.lease_seconds, self.rpc_timeout = lease_seconds, rpc_timeout
        self.started, self.watch_factory, self.guards, self.child_of = started, watch, guards, child_of
        self.parent, self.boot = parent, boot()
        self.alive = alive
        self.socket_path = self.directory / 'broker.sock'
        if mode == 'capacity' and (proof['socket'] != str(self.socket_path)
                or proof['disk_pool'] != str(self.disk_pool)
                or proof['total'] != asdict(self.total) or proof['reserve'] != asdict(self.reserve)):
            raise wire.CapacityError('Broker resources or endpoint differ from the sealed policy')
        if len(os.fsencode(self.socket_path)) >= (104 if sys.platform == 'darwin' else 108):
            raise wire.CapacityError('Capacity Unix socket path is too long')
        self.database_path = self.directory / 'admission.sqlite'
        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._gates, self._watches = {}, {}
        self._last_clock = time.monotonic()
        self.listener = self.connection = self.lock_fd = None
        try:
            self._directory()
            self._singleton()
            self.connection = self._database()
            with self._lock:
                state = self._load()
                previous_boot = state['boot_id']
                state['epoch'] += 1
                state['boot_id'] = self.boot
                for record in state['records'].values():
                    if record['state'] in HELD:
                        if previous_boot != self.boot:
                            record.update(state='released', release_witness={'kind': 'os-boot-change',
                                          'from': previous_boot, 'to': self.boot})
                        else:
                            record['state'] = 'uncertain'
                            for pin in record.get('roster', []):
                                if pin not in record.get('exited', []):
                                    self._watches[(record['nonce'], tuple(pin))] = self.watch_factory(pin)
                    elif record['state'] != 'released':
                        record['state'] = 'waiting'
                self._save(state)
            if self.socket_path.exists() or self.socket_path.is_symlink():
                info = self.socket_path.lstat()
                if not stat.S_ISSOCK(info.st_mode) or info.st_uid != os.getuid():
                    raise wire.CapacityError('Refusing unrelated capacity socket path')
                self.socket_path.unlink()  # Only after exclusive singleton ownership.
            self.listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            self.listener.bind(str(self.socket_path))
            self.socket_path.chmod(0o600)
            self.listener.listen(16)
            self.listener.setblocking(False)
        except BaseException:
            self.close()
            raise

    def _directory(self):
        for part in (self.directory, *self.directory.parents):
            if part.is_symlink() and str(part) not in ('/tmp', '/var', '/etc'):
                raise wire.CapacityError('Broker directory ancestors cannot be symlinks')
        self.directory.mkdir(mode=0o700, exist_ok=True)
        info = self.directory.stat()
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
            raise wire.CapacityError('Broker directory must be private and owned')

    def _singleton(self):
        path = self.directory / 'broker.lock'
        try:
            fd = os.open(path, os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
            os.write(fd, (wire.NAMESPACE + '\n').encode())
            os.fsync(fd)
        except FileExistsError:
            wire.private_file(path, limit=128)
            fd = os.open(path, os.O_RDWR | os.O_NOFOLLOW)
        self.lock_fd = fd
        if os.pread(fd, 128, 0) != (wire.NAMESPACE + '\n').encode():
            raise wire.CapacityError('Unrelated broker singleton file')
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise wire.CapacityError('A capacity broker already owns this directory') from None

    def _database(self):
        path = self.database_path
        for sibling in (path, *(Path(str(path) + suffix) for suffix in ('-journal', '-wal', '-shm'))):
            if sibling.exists() or sibling.is_symlink():
                wire.private_file(sibling, limit=MAX_DATABASE)
        try:
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        except FileExistsError:
            created = False
        else:
            os.close(fd)
            created = True
        if not created:
            probe = sqlite3.connect(path.resolve().as_uri() + '?mode=ro&immutable=1', uri=True)
            try:
                if (probe.execute('PRAGMA application_id').fetchone()[0] != APPLICATION_ID
                        or probe.execute('PRAGMA user_version').fetchone()[0] != 1
                        or dict(probe.execute("SELECT name,sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'")) != {'state': SCHEMA}):
                    raise wire.CapacityError('Not a production capacity database')
            finally:
                probe.close()
        connection = sqlite3.connect(path, isolation_level=None, check_same_thread=False, timeout=.2)
        connection.execute('PRAGMA synchronous=FULL')
        connection.execute('PRAGMA journal_mode=DELETE')
        if created:
            connection.execute('BEGIN IMMEDIATE')
            connection.execute(f'PRAGMA application_id={APPLICATION_ID}')
            connection.execute('PRAGMA user_version=1')
            connection.execute(SCHEMA)
            connection.execute('INSERT INTO state VALUES (1,?)',
                               (json.dumps({'namespace': wire.NAMESPACE, 'boot_id': self.boot,
                                            'epoch': 0, 'sequence': 0, 'records': {}}),))
            connection.commit()
        return connection

    def _load(self):
        self.connection.execute('BEGIN IMMEDIATE')
        row = self.connection.execute('SELECT value FROM state WHERE id=1').fetchone()
        value = json.loads(row[0])
        if value.get('namespace') != wire.NAMESPACE:
            self.connection.rollback()
            raise wire.CapacityError('Capacity database namespace mismatch')
        return value

    def _save(self, state):
        data = json.dumps(state, separators=(',', ':'), allow_nan=False)
        if len(data) > 4 * 1024 * 1024:
            raise wire.CapacityError('Capacity state exceeds its limit')
        self.connection.execute('UPDATE state SET value=? WHERE id=1', (data,))
        self.connection.commit()
        for record in state['records'].values():
            if record['state'] == 'released':
                self._dispose(record.get('nonce'))

    def _clock(self):
        now = time.monotonic()
        if now < self._last_clock:
            raise wire.CapacityError('Capacity clock regressed')
        self._last_clock = now
        return now

    def _watch(self, record, pins):
        roster = {tuple(pin) for pin in record.get('roster', [])}
        verified = {tuple(pin) for pin in record.get('verified_roster', [])}
        pending = {}
        for value in pins:
            pin = wire.identity(value)
            if pin == tuple(record['principal']):
                raise wire.CapacityError('The controller is not a workload descendant')
            if pin not in roster:
                if len(roster) >= wire.MAX_ROSTER:
                    raise wire.CapacityError('Retained process roster exceeds its limit')
                roster.add(pin)
                self._watches[(record['nonce'], pin)] = self.watch_factory(pin)
                pending[pin] = self.parent(pin)
        root = tuple(record['child']) if 'child' in record else None
        if root in roster:
            verified.add(root)  # start() separately validated its direct-parent edge.
            pending.pop(root, None)
        while pending:
            found = [pin for pin, parent in pending.items() if parent in verified]
            if not found:
                record['ancestry_unknown'] = True
                break
            for pin in found:
                verified.add(pin)
                del pending[pin]
        record['roster'] = [list(pin) for pin in sorted(roster)]
        record['verified_roster'] = [list(pin) for pin in sorted(verified)]

    def _root_exited(self, record):
        pin = record.get('child')
        if pin in record.get('exited', []):
            return True
        watch = self._watches.get((record['nonce'], tuple(pin))) if pin else None
        if watch is not None and watch.poll():
            record.setdefault('exited', []).append(pin)
            return True
        return False

    def _guard_health(self, record):
        try:
            return self.guards(record['guards'], tuple(record['child']), tuple(record['principal']),
                               record['limit_bytes'], record['request']['resources']['memory_mib'])
        except (OSError, ValueError, wire.CapacityError) as error:
            # A normal child exit can occur between the first watch poll and receipt validation.
            # Only an already bound positive kernel witness resolves that race.
            record['state'] = 'draining' if self._root_exited(record) else 'uncertain'
            known = {'Capacity guard identity is not live and owned',
                     'Capacity guard identity changed during validation',
                     'Capacity guard receipt is stale or mismatched',
                     'Capacity guard receipt belongs to another child',
                     'Capacity guard report repeatedly replaced while reading',
                     'Capacity file changed while reading',
                     'Capacity file must be bounded, owned and regular',
                     'Capacity paths cannot contain symlinks',
                     'Guard ceiling exceeds the reserved memory envelope',
                     'Invalid retained guard roster', 'Invalid retained guard process identity',
                     'Invalid capacity message', 'Invalid capacity protocol fields',
                     'Invalid capacity integer', 'A pinned process identity is required'}
            reason = str(error) if isinstance(error, wire.CapacityError) and str(error) in known else type(error).__name__
            request = record['request']
            print('capacity guard health failure: ' + json.dumps(dict(
                owner=request.get('owner'), purpose=request.get('purpose'), pid=record['child'][0],
                reason=reason, state=record['state'])), file=sys.stderr, flush=True)
            return None

    def _refresh(self, state, now):
        changed = False
        if self.mode == 'capacity':
            from . import capacity_compat
            try:
                proof = capacity_compat.verify(self.cutover, policy_sha256=self.policy_sha256)
                self.compatible = proof['activation_id'] == self.activation_id
            except (OSError, ValueError, wire.CapacityError):
                self.compatible = False
        for record in state['records'].values():
            if not self.compatible and record['state'] in HELD and record['state'] != 'uncertain':
                record['state'] = 'uncertain'
                changed = True
            if record['state'] == 'queued' and now - record['heartbeat'] > self.lease_seconds:
                record['state'] = 'waiting'
                self._gate_close(record['nonce'])
                changed = True
            if record['state'] in ('running', 'draining') and now - record['heartbeat'] > self.lease_seconds:
                record['state'] = 'uncertain'
                changed = True
            for pin in record.get('roster', []):
                watch = self._watches.get((record['nonce'], tuple(pin)))
                if watch is not None and watch.poll() and pin not in record.setdefault('exited', []):
                    record['exited'].append(pin)
                    changed = True
            if record['state'] == 'running' and record.get('child') in record.get('exited', []):
                record['state'] = 'draining'
                changed = True
            if record['state'] in ('running', 'draining'):
                try:
                    owner = tuple(record['principal'])
                    if self.started(owner[0]) != owner[1] or not self.alive(owner):
                        raise wire.CapacityError('Controller identity lost')
                    if record['state'] == 'running':
                        before = record['state']
                        self._guard_health(record)
                        changed |= record['state'] != before
                except (OSError, ValueError, wire.CapacityError):
                    record['state'] = 'uncertain'
                    changed = True
            changed |= self._settle_exited(record)
        return changed

    def _settle_exited(self, record):
        """@cc [owner:fontanierh,label:safety] witnessed-capacity-recovery
        An uncertain reservation MUST release after complete known-ancestry retained exits, or
        the explicitly scoped terminal-tree witness below. Missing PIDs and expired heartbeats
        alone MUST NOT release capacity. Neither release path MAY certify build outputs.
        """
        if record['state'] != 'uncertain' or not record.get('roster'):
            return False
        if (not record.get('ancestry_unknown')
                and all(pin in record.get('exited', []) for pin in record['roster'])):
            witness = {'kind': 'retained-kernel-exits'}
        else:
            witness = self._terminal_tree_exit(record)
            if witness is None:
                return False
        record.update(state='released', release_witness=witness)
        return True

    def _terminal_tree_exit(self, record, *, preserved=None):
        """@cc [owner:fontanierh,label:safety] exclusive-terminal-tree-release
        Only bridge or full performance-exclusive grants MAY use this policy. The root MUST
        have affirmative exit evidence and its previously bound aggregate report MUST match
        identity, ceiling and invocation time, with child_exited, completed cleanup and zero
        processes/footprint. Any verifiably live retained identity MUST refuse release. This
        witnesses monitored-owned-tree cleanup, never individual historical kernel exits.
        """
        if (self.mode != 'legacy-bridge'
                and not (self.mode == 'capacity' and record.get('request', {}).get('performance') is True)):
            return None
        if record.get('child') not in record.get('exited', []):
            return None
        try:
            item = wire.fields(record.get('guards', {}).get('tree_guard'), ('pid', 'start', 'report'))
            wire.identity((item['pid'], item['start']))  # Bound at start; terminal monitor may now have exited.
            report = wire.text(item['report'], maximum=4096)
            receipt = (wire.decode(wire.private_file(report, limit=wire.MAX_FRAME, private=False))
                       if preserved is None else preserved)
            observed, ready = receipt.get('time'), record.get('first_ready')
            if (type(observed) not in (int, float) or not math.isfinite(observed)
                    or type(ready) not in (int, float) or not math.isfinite(ready)
                    or not 0 < ready <= observed <= time.time()
                    or wire.identity((receipt.get('owner'), receipt.get('owner_started'))) != tuple(record['child'])
                    or type(receipt.get('limit_bytes')) is not int or receipt['limit_bytes'] != record['limit_bytes']
                    or receipt.get('state') != 'child_exited' or receipt.get('cleanup_complete') is not True
                    or receipt.get('termination_reason') is not None or receipt.get('processes') != []
                    or type(receipt.get('footprint_bytes')) is not int or receipt['footprint_bytes'] != 0
                    or any(self.alive(wire.identity(pin)) for pin in record['roster'])):
                return None
        except (OSError, ValueError, KeyError, TypeError, wire.CapacityError):
            return None
        return {'kind': 'guarded-tree-exit', 'coverage': 'monitored-owned-tree', 'observed_at': observed}

    def _preserved_terminal(self, state, evidence):
        """@cc [owner:fontanierh,label:safety] attested-preserved-terminal-recovery
        This explicit same-UID administration request MAY supply an archived original receipt
        after its bound shared report path was reused. It MUST retain every terminal-tree
        policy check and bind the evidence digest and original report metadata durably. It
        attests operator preservation, not cryptographic monitor provenance or per-pin exits.
        """
        wire.fields(evidence, ('request_id', 'path'))
        record = state['records'].get(wire.text(evidence['request_id']))
        if record is None:
            raise wire.CapacityError('Preserved terminal request does not exist')
        if record['state'] == 'released':
            return False
        if record['state'] != 'uncertain':
            raise wire.CapacityError('Preserved terminal evidence requires an uncertain reservation')
        path = Path(wire.text(evidence['path'], maximum=4096))
        if not path.is_absolute():
            raise wire.CapacityError('Preserved terminal archive path must be absolute')
        raw = wire.private_file(path, limit=wire.MAX_FRAME, private=False)
        witness = self._terminal_tree_exit(record, preserved=wire.decode(raw))
        if witness is None:
            raise wire.CapacityError('Preserved terminal evidence does not satisfy the scoped release policy')
        bound = record['guards']['tree_guard']
        witness.update(provenance='operator-preserved', evidence_sha256=hashlib.sha256(raw).hexdigest(),
                       bound_report_sha256=hashlib.sha256(bound['report'].encode()).hexdigest(),
                       bound_monitor=[bound['pid'], bound['start']])
        record.update(state='released', release_witness=witness)
        return True

    def _request(self, value):
        wire.fields(value, ('id', 'resources'), ('locks', 'seconds', 'performance', 'checkout', 'owner', 'purpose', 'phase', 'workers'))
        wire.text(value['id'])
        vector = wire.resources(value['resources'])
        locks = value.get('locks', [])
        if type(locks) is not list or len(locks) > 32 or len(set(locks)) != len(locks):
            raise wire.CapacityError('Invalid capacity named locks')
        locks = [wire.text(item, maximum=1024) for item in locks]
        seconds = wire.integer(value.get('seconds', 300), maximum=86400)
        performance = value.get('performance', False)
        if type(performance) is not bool:
            raise wire.CapacityError('Invalid performance-window request')
        if self.mode == 'capacity':
            checkout = wire.text(value.get('checkout'), maximum=4096)
            if not Path(checkout).is_absolute() or 'checkout:' + checkout not in locks:
                raise wire.CapacityError('Full capacity requires its declared checkout named lock')
            if not vector.cpu_millis:
                raise wire.CapacityError('Full capacity requires a nonzero CPU reservation')
            workers = value.get('workers')
            if workers is not None:
                wire.integer(workers, minimum=1, maximum=1024)
                if vector.cpu_millis < workers * 1000:
                    raise wire.CapacityError('Capacity CPU reservation does not cover declared unchanged workers')
            if (workers is None or value.get('phase') in ('game', 'compile')) and not performance:
                raise wire.CapacityError('Games, compiles and unbounded compound profiles require exclusive capacity')
            if workers is None and vector.cpu_millis < self.total.cpu_millis - self.reserve.cpu_millis:
                raise wire.CapacityError('Unknown profiles must reserve the complete managed CPU budget')
            if value.get('phase') == 'compile' and vector.cpu_millis < 3000:
                raise wire.CapacityError('Compile profiles must cover the existing three workers')
        for key in ('owner', 'checkout', 'purpose', 'phase'):
            if key in value:
                wire.text(value[key], maximum=4096 if key == 'checkout' else 512)
        return {**value, 'resources': asdict(vector), 'locks': locks, 'seconds': seconds, 'performance': performance}

    def _model(self, record):
        request = record['request']
        return Request(request['id'], wire.resources(request['resources']), tuple(request['locks']),
                       record['sequence'], request['seconds'], record.get('bypasses', 0), request['performance'])

    def _selection(self, state):
        if not self.compatible or any(r['state'] == 'uncertain' for r in state['records'].values()):
            return None  # Accounting alone cannot replace a lost enforcement/ownership boundary.
        holders = [self._model(r) for r in state['records'].values() if r['state'] in HELD]
        queued = sorted((r for r in state['records'].values() if r['state'] == 'queued'), key=lambda r: r['sequence'])
        feasible = [r for r in queued if not conflicts(self._model(r), [], self.total, self.reserve)]
        protected = next((r for r in feasible if r.get('bypasses', 0) >= 2), None)
        ranked = sorted(feasible, key=lambda r: (r is not protected if protected else False,
                                                r['request']['seconds'] > 300, r['sequence']))
        if not ranked:
            return None
        for record in ranked:
            if not conflicts(self._model(record), holders, self.total, self.reserve):
                return record
            if record is protected:
                break
        return None

    def _pressure(self, state, candidate):
        observation = self.observe()
        now = self._clock()
        if (type(observation) is not dict or type(observation.get('observed_monotonic')) not in (float, int)
                or not math.isfinite(observation['observed_monotonic'])
                or not 0 <= now - observation['observed_monotonic'] <= 2):
            raise wire.CapacityError('Fresh capacity pressure observation unavailable')
        memory = wire.integer(observation.get('available_memory_mib'))
        disk = wire.integer(observation.get('available_temp_mib'))
        required = wire.resources(candidate['request']['resources']) + self.reserve
        growth_memory, growth_temp = 0, 0
        for record in state['records'].values():
            if record is candidate or record['state'] not in HELD:
                continue
            vector = wire.resources(record['request']['resources'])
            measured = 0
            if record['state'] == 'running':
                try:
                    facts = self.guards(record['guards'], tuple(record['child']), tuple(record['principal']),
                                        record['limit_bytes'], vector.memory_mib)
                    measured = facts.footprint_bytes // 1024**2
                except (OSError, ValueError, KeyError, wire.CapacityError):
                    record['state'] = 'draining' if self._root_exited(record) else 'uncertain'
                    raise wire.CapacityError('Existing holder enforcement is unavailable; reservation retained') from None
            growth_memory += max(0, vector.memory_mib - measured)
            growth_temp += vector.temp_mib
        if memory < required.memory_mib + growth_memory or disk < required.temp_mib + growth_temp:
            raise wire.CapacityError('Capacity pressure refuses the complete reservation')

    def _validate_holders(self, state, candidate):
        """@cc [owner:fontanierh,label:safety] final-charged-peer-enforcement
        Before another GO, charged peer controller/guard health MUST be revalidated after slow
        observations. Positively observed loss MUST survive candidate rollback as a nonce-bound
        retained state transition, without committing any refused candidate vector or lock change.
        """
        failed = []
        for record in state['records'].values():
            if record is candidate or record['state'] not in HELD:
                continue
            try:
                if record['state'] == 'uncertain':
                    raise wire.CapacityError('Existing holder is uncertain')
                if record['state'] == 'running':
                    self.guards(record['guards'], tuple(record['child']), tuple(record['principal']),
                                record['limit_bytes'], record['request']['resources']['memory_mib'])
                elif (not record.get('roster') or record.get('ancestry_unknown')
                      or any(pin not in record.get('exited', []) for pin in record['roster'])):
                    raise wire.CapacityError('Draining holder lacks complete retained exit evidence')
                owner = tuple(record['principal'])
                if self.started(owner[0]) != owner[1] or not self.alive(owner):
                    raise wire.CapacityError('Existing holder controller identity lost')
                if self._clock() - record['heartbeat'] > self.lease_seconds:
                    raise wire.CapacityError('Existing holder lease expired during admission')
            except (OSError, ValueError, KeyError, wire.CapacityError):
                record['state'] = 'uncertain'
                failed.append(record)
        if failed:
            raise wire.CapacityError('Existing holder lost ownership or enforcement; reservation retained')

    def _validate_compatibility(self, state):
        if self.mode != 'capacity':
            return
        from . import capacity_compat
        try:
            proof = capacity_compat.verify(self.cutover, policy_sha256=self.policy_sha256)
            if proof['activation_id'] != self.activation_id:
                raise wire.CapacityError('Capacity activation changed')
        except (OSError, ValueError, wire.CapacityError):
            self.compatible = False
            retained = [record for record in state['records'].values() if record['state'] in HELD]
            for record in retained:
                record['state'] = 'uncertain'
            raise wire.CapacityError('Full-capacity compatibility changed before admission; charges retained') from None

    def _gate_close(self, nonce):
        fd = self._gates.pop(nonce, None)
        if fd is not None:
            os.close(fd)

    def _dispose(self, nonce):
        self._gate_close(nonce)
        for key in [key for key in self._watches if key[0] == nonce]:
            self._watches.pop(key).close()

    def _status(self, state):
        records = list(state['records'].values())
        charged = [r for r in records if r['state'] in HELD]
        used = Resources()
        for record in charged:
            used += wire.resources(record['request']['resources'])
        result = dict(epoch=state['epoch'], boot_id=self.boot, mode=self.mode, cutover=self.mode == 'capacity',
                      observed_at=time.time(), observed_monotonic=time.monotonic(),
                      recovering=not self.compatible or any(r['state'] == 'uncertain' for r in records),
                      total=asdict(self.total), reserve=asdict(self.reserve), charged_resources=asdict(used),
                      charged_count=len(charged), waiting_count=sum(r['state'] in ('queued', 'waiting') for r in records),
                      total_records=len(records), records=[], truncated=False)
        if self.mode == 'capacity':
            result['compatibility_healthy'] = self.compatible
        selected = self._selection(state)
        for record in sorted(records, key=lambda r: (r['state'] not in HELD, r['state'] != 'queued', r['sequence'])):
            request = record['request']
            blockers = conflicts(self._model(record), [self._model(r) for r in charged], self.total, self.reserve)
            reason = ('uncertain ownership or enforcement; reservation retained' if record['state'] == 'uncertain' else
                      'capacity recovery blocks new grants' if result['recovering'] and record['state'] == 'queued' else
                      ('selected advisory offer; sealed compatibility locks and guarded commit still required'
                       if self.mode == 'capacity' else 'selected advisory offer; legacy exclusion and guarded commit still required') if record is selected else
                      ('; '.join(blockers) or 'older ready request selected') if record['state'] == 'queued' else
                      'not currently ready; retry required' if record['state'] == 'waiting' else '')
            item = dict(id=request['id'], owner=request.get('owner'), checkout=request.get('checkout'),
                        purpose=request.get('purpose'), phase=request.get('phase'),
                        state=record['state'], charged=record['state'] in HELD, resources=request['resources'],
                        locks=request['locks'], first_ready=record['first_ready'], sequence=record['sequence'],
                        bypasses=record['bypasses'], retained=len(record.get('roster', [])),
                        witnessed=len(record.get('exited', [])), wait_reason=reason,
                        measured_memory_mib=record.get('measured_memory_mib'),
                        measured_at=record.get('measured_at'), ancestry_unknown=record.get('ancestry_unknown', False))
            result['records'].append(item)
            if len(json.dumps(result).encode()) > wire.MAX_FRAME - 1024 or len(result['records']) > 32:
                result['records'].pop()
                result['truncated'] = True
                break
        result['returned_records'] = len(result['records'])
        return result

    def _owned(self, state, candidates):
        """@cc [owner:fontanierh,label:safety] exact-capacity-scan-exclusions
        Foreign-scan exclusions MUST match complete PID/start identities in positively verified,
        still charged rosters. No descendant expansion, truncated roster or uncertain grant MAY
        establish ownership. Unknown observations MUST refuse admission, never imply absence.
        """
        if (not self.compatible or any(r['state'] == 'uncertain' for r in state['records'].values())
                or type(candidates) is not list or len(candidates) > wire.MAX_ROSTER):
            raise wire.CapacityError('Capacity ownership observation is unavailable or incomplete')
        pins = [wire.identity(pin) for pin in candidates]
        known = {tuple(pin) for record in state['records'].values() if record['state'] in HELD
                 for pin in record.get('verified_roster', []) if pin not in record.get('exited', [])}
        return [list(pin) for pin in pins if pin in known and self.started(pin[0]) == pin[1] and self.alive(pin)]

    def _foreign_check(self, state):
        from .safety.render_lock import native_candidates
        candidates = self.foreign() if self.foreign is not None else native_candidates()
        owned = {tuple(pin) for pin in self._owned(state, candidates)}
        if any(tuple(pin) not in owned for pin in candidates):
            raise wire.CapacityError('Unregistered native processes refuse full-capacity admission')

    def handle(self, message, principal):
        """Serialized actor: refused accounting rolls back, observed enforcement loss remains charged."""
        with self._lock:
            state = self._load()
            fd, go = None, None
            try:
                now = self._clock()
                refreshed = self._refresh(state, now)
                wire.fields(message, ('namespace', 'action'), ('request', 'id', 'nonce', 'epoch', 'boot_id', 'child',
                            'process_guard', 'tree_guard', 'limit_bytes', 'descendants', 'witness', 'resources', 'locks',
                            'activation_id', 'candidates', 'preserved_terminal'))
                if message['namespace'] != wire.NAMESPACE:
                    raise wire.CapacityError('Production broker namespace required')
                action = message['action']
                if 'preserved_terminal' in message and action != 'reconcile':
                    raise wire.CapacityError('Preserved terminal evidence is allowed only for reconciliation')
                if self.mode == 'capacity' and action not in ('status', 'reconcile', 'close'):
                    if not self.compatible or message.get('activation_id') != self.activation_id:
                        raise wire.CapacityError('Full-capacity compatibility proof is unavailable or mismatched')
                if action in ('status', 'reconcile'):
                    if action == 'reconcile':
                        if 'preserved_terminal' in message:
                            refreshed |= self._preserved_terminal(state, message['preserved_terminal'])
                        for retained in state['records'].values():
                            refreshed |= self._settle_exited(retained)
                    result = self._status(state)
                elif action == 'owned':
                    if (self.mode != 'capacity' or message.get('boot_id') != self.boot
                            or message.get('epoch') != state['epoch']):
                        raise wire.CapacityError('Capacity ownership observation was fenced')
                    result = dict(owned=self._owned(state, message.get('candidates')), epoch=state['epoch'])
                elif action == 'offer':
                    request = self._request(message['request'])
                    record = state['records'].get(request['id'])
                    if any(r['state'] in HELD and tuple(r['principal']) == principal for r in state['records'].values()):
                        raise wire.CapacityError('Cannot queue while holding capacity')
                    if record is None:
                        if len(state['records']) >= 512:
                            for key in list(state['records']):
                                if state['records'][key]['state'] == 'released':
                                    self._dispose(state['records'][key]['nonce'])
                                    del state['records'][key]
                            if len(state['records']) >= 512:
                                raise wire.CapacityError('Capacity queue is full')
                        state['sequence'] += 1
                        record = dict(request=request, sequence=state['sequence'], first_ready=time.time(), bypasses=0)
                        state['records'][request['id']] = record
                    elif record['state'] in HELD:
                        raise wire.CapacityError('Capacity request identity conflicts with retained state')
                    changed_request = ({k: v for k, v in record['request'].items() if k not in ('owner', 'purpose')} !=
                                       {k: v for k, v in request.items() if k not in ('owner', 'purpose')})
                    if record.get('state') == 'released' or changed_request:
                        state['sequence'] += 1
                        record.update(sequence=state['sequence'], first_ready=time.time(), bypasses=0)
                    if (record.get('state') != 'queued' or tuple(record.get('principal', ())) != principal
                            or message.get('nonce') != record.get('nonce') or changed_request):
                        self._dispose(record.get('nonce'))
                        record.update(nonce=secrets.token_hex(32), principal=list(principal), roster=[], exited=[],
                                      verified_roster=[], ancestry_unknown=False)
                    record.update(request=request, state='queued', epoch=state['epoch'], heartbeat=now)
                    selected = self._selection(state) is record
                    result = {'selected': selected, 'state': 'offered' if selected else 'queued',
                              'nonce': record['nonce'], 'epoch': state['epoch'], 'first_ready': record['first_ready']}
                else:
                    record = state['records'].get(message.get('id'))
                    if (record is None or tuple(record['principal']) != principal or message.get('nonce') != record['nonce']):
                        raise wire.CapacityError('Capacity session identity mismatch')
                    wire.integer(message.get('epoch'), minimum=1)
                    old_close = action == 'close' and message['epoch'] == record['epoch']
                    if message.get('boot_id') != self.boot or (not old_close and
                            (message['epoch'] != state['epoch'] or record['epoch'] != state['epoch'])):
                        raise wire.CapacityError('Capacity session was fenced by restart')
                    if self.started(principal[0]) != principal[1] or not self.alive(principal):
                        raise wire.CapacityError('Capacity controller identity is no longer live')
                    if action == 'gate':
                        if record['state'] != 'queued' or record['nonce'] in self._gates:
                            raise wire.CapacityError('Capacity gate is unavailable')
                        fd, writer = os.pipe()
                        os.set_inheritable(fd, False)
                        self._gates[record['nonce']] = writer
                        result = {'state': 'gated', 'epoch': state['epoch']}
                    elif action == 'start':
                        if record['state'] != 'queued' or self._selection(state) is not record or record['nonce'] not in self._gates:
                            raise wire.CapacityError('Capacity offer is no longer selected')
                        child = wire.identity(message['child'])
                        if not self.child_of(principal, child):
                            raise wire.CapacityError('Launcher is not the pinned direct child')
                        guards = {name: message[name] for name in ('process_guard', 'tree_guard')}
                        facts = self.guards(guards, child, principal, message['limit_bytes'],
                                             record['request']['resources']['memory_mib'])
                        if self.mode == 'capacity':
                            self._foreign_check(state)
                        self._pressure(state, record)
                        self._validate_compatibility(state)
                        self._validate_holders(state, record)
                        # Revalidate after all compatibility, process-scan and pressure I/O.
                        facts = self.guards(guards, child, principal, message['limit_bytes'],
                                            record['request']['resources']['memory_mib'])
                        if self.started(child[0]) != child[1] or self.started(principal[0]) != principal[1]:
                            raise wire.CapacityError('Launcher/controller changed before admission')
                        record['child'] = list(child)
                        self._watch(record, [child, *facts.roster])
                        record.update(state='running', child=list(child), guards=guards,
                                      limit_bytes=message['limit_bytes'], heartbeat=self._clock(),
                                      measured_memory_mib=facts.footprint_bytes // 1024**2, measured_at=time.time())
                        for earlier in state['records'].values():
                            if (earlier['state'] == 'queued' and earlier['sequence'] < record['sequence']
                                    and earlier['request']['seconds'] > 300 and request_seconds(record) <= 300):
                                earlier['bypasses'] += 1
                        go = record['nonce']
                        result = {'state': 'running', 'epoch': state['epoch'], 'admission': True}
                    elif action == 'check':
                        if record['state'] not in ('running', 'draining'):
                            raise wire.CapacityError('Capacity grant is uncertain or inactive')
                        self._watch(record, message.get('descendants', []))
                        self._refresh(state, now)
                        if record['state'] not in ('running', 'draining'):
                            raise wire.CapacityError('Capacity grant is uncertain or inactive')
                        if record['child'] in record.get('exited', []):
                            record['state'] = 'draining'
                        else:
                            facts = self._guard_health(record)
                            if facts is not None:
                                self._watch(record, facts.roster)
                                record.update(measured_memory_mib=facts.footprint_bytes // 1024**2, measured_at=time.time())
                        record['heartbeat'] = now
                        result = {'state': record['state'], 'epoch': state['epoch'], 'admission': True}
                    elif action == 'close':
                        self._gate_close(record['nonce'])
                        if record['state'] not in HELD:
                            self._dispose(record['nonce'])
                            record['state'] = 'waiting'
                            result = {'state': 'waiting', 'released': True}
                        else:
                            self._watch(record, message.get('descendants', []))
                            witness = message.get('witness')
                            if witness is not None:
                                wire.fields(witness, ('kind', 'parent', 'child', 'returncode'))
                                if (witness['kind'] != 'direct-parent-wait' or wire.identity(witness['parent']) != principal
                                        or wire.identity(witness['child']) != tuple(record['child'])
                                        or type(witness['returncode']) is not int):
                                    raise wire.CapacityError('Invalid direct-parent exit witness')
                                # This authenticated adapter reports its actual Popen wait status.
                                record.setdefault('exited', []).append(record['child']) if record['child'] not in record.get('exited', []) else None
                            self._refresh(state, now)
                            if record['state'] != 'released':
                                record['state'] = 'uncertain'
                                self._settle_exited(record)
                            complete = record['state'] == 'released'
                            if not complete:
                                print('capacity close retained: ' + json.dumps(dict(
                                    owner=record['request'].get('owner'), purpose=record['request'].get('purpose'),
                                    pid=record['child'][0], roster=len(record.get('roster', [])),
                                    exited=len(record.get('exited', [])), ancestry_unknown=record.get('ancestry_unknown', False),
                                    reason='Retained exits incomplete and no eligible terminal cleanup witness')),
                                    file=sys.stderr, flush=True)
                            result = {'state': record['state'], 'released': complete,
                                      'coverage': record.get('release_witness', {}).get('coverage', 'retained-roster-only')}
                    elif action == 'replace':
                        if record['state'] != 'running':
                            raise wire.CapacityError('Only a live grant can change phase')
                        replacement = {**record['request'], 'resources': message['resources'], 'locks': message['locks']}
                        old = record['request']
                        record['request'] = self._request(replacement)
                        others = [self._model(r) for r in state['records'].values() if r is not record and r['state'] in HELD]
                        if (conflicts(self._model(record), others, self.total, self.reserve)
                                or record['limit_bytes'] > record['request']['resources']['memory_mib'] * 1024**2):
                            record['request'] = old
                            raise wire.CapacityError('Atomic phase replacement refused; old grant retained')
                        self._pressure(state, record)
                        self._validate_compatibility(state)
                        self._validate_holders(state, record)
                        result = {'state': 'running', 'admission': True}
                    else:
                        raise wire.CapacityError('Unknown capacity action')
                if action in ('status', 'reconcile') and not refreshed:
                    self.connection.rollback()
                else:
                    self._save(state)
                if go is not None:
                    try:
                        os.write(self._gates[go], b'1')
                    except OSError:
                        failed = self._load()
                        failed['records'][record['request']['id']]['state'] = 'uncertain'
                        self._save(failed)
                        raise wire.CapacityError('Launch gate failed; reservation retained') from None
                    finally:
                        self._gate_close(go)
                return {'namespace': wire.NAMESPACE, 'boot_id': self.boot, 'mode': self.mode,
                        **({'activation_id': self.activation_id} if self.mode == 'capacity' else {}), **result}, fd
            except BaseException:
                self.connection.rollback()
                if message.get('action') == 'start':
                    self._gate_close(message.get('nonce'))
                if fd is not None:
                    os.close(fd)
                # Refresh can observe loss before request validation or candidate selection. Retain
                # those observations on every refusal, not only failures at the final GO checks.
                losses = [(item['request']['id'], item['nonce'], item['state'])
                          for item in state['records'].values() if item['state'] in ('uncertain', 'draining')]
                if losses:
                    retained = self._load()
                    for identity, nonce, lost_state in losses:
                        other = retained['records'].get(identity)
                        if other is not None and other['nonce'] == nonce and other['state'] in HELD:
                            # Never copy a refused vector/lock/roster or turn uncertainty into draining.
                            if other['state'] != 'uncertain':
                                other['state'] = lost_state
                    self._save(retained)
                raise

    def serve_forever(self):
        """Bounded concurrent partial frames; all requests execute on this one actor thread."""
        selector = selectors.DefaultSelector()
        selector.register(self.listener, selectors.EVENT_READ)
        clients = {}
        try:
            while not self._stop.is_set():
                for key, _ in selector.select(.1):
                    channel = key.fileobj
                    if channel is self.listener:
                        channel, _ = self.listener.accept()
                        channel.setblocking(False)
                        if len(clients) >= 32:
                            channel.close()
                            continue
                        try:
                            principal = wire.peer(channel)
                        except (OSError, ValueError, wire.CapacityError):
                            channel.close()
                            continue
                        clients[channel] = [bytearray(), time.monotonic() + self.rpc_timeout, principal]
                        selector.register(channel, selectors.EVENT_READ)
                        continue
                    buffer, deadline, principal = clients[channel]
                    try:
                        data = channel.recv(wire.MAX_FRAME + 1 - len(buffer))
                        if not data:
                            raise wire.CapacityError('Capacity peer closed its request')
                        buffer.extend(data)
                        if len(buffer) > wire.MAX_FRAME:
                            raise wire.CapacityError('Capacity message exceeds its limit')
                        if b'\n' not in buffer:
                            continue
                        if not buffer.endswith(b'\n') or buffer.count(b'\n') != 1:
                            raise wire.CapacityError('One capacity operation per connection is required')
                        result, fd = self.handle(wire.decode(bytes(buffer[:-1])), principal)
                        try:
                            channel.settimeout(self.rpc_timeout)
                            wire.send(channel, {'ok': True, **result}, fd)
                        finally:
                            if fd is not None:
                                os.close(fd)
                    except (OSError, ValueError, KeyError, TypeError, sqlite3.Error, wire.CapacityError) as error:
                        try:
                            channel.settimeout(.1)
                            wire.send(channel, {'ok': False, 'namespace': wire.NAMESPACE,
                                                'error': str(error) if isinstance(error, wire.CapacityError)
                                                else 'Capacity broker refused this operation'})
                        except OSError:
                            pass
                    selector.unregister(channel)
                    clients.pop(channel, None)
                    channel.close()
                for channel, (_, deadline, _) in list(clients.items()):
                    if time.monotonic() >= deadline:
                        selector.unregister(channel)
                        clients.pop(channel)
                        channel.close()
                with self._lock:
                    state = self._load()
                    if self._refresh(state, self._clock()):
                        self._save(state)
                    else:
                        self.connection.rollback()
        finally:
            for channel in clients:
                channel.close()
            selector.close()

    def close(self):
        self._stop.set()
        with self._lock:
            for nonce in list(self._gates):
                self._gate_close(nonce)
            for watch in self._watches.values():
                watch.close()
            self._watches.clear()
            if self.listener is not None:
                self.listener.close()
                self.listener = None
            if self.connection is not None:
                self.connection.close()
                self.connection = None
            if self.lock_fd is not None:
                os.close(self.lock_fd)
                self.lock_fd = None


def request_seconds(record):
    return record['request']['seconds']


def load_config(configpath, *, expected_sha256=None):
    path = Path(configpath)
    if not path.is_absolute():
        raise wire.CapacityError('Capacity broker configuration must be absolute')
    raw = wire.private_file(path, limit=wire.MAX_FRAME)
    if expected_sha256 is not None:
        if (len(expected_sha256) != 64 or any(c not in '0123456789abcdef' for c in expected_sha256)
                or not hmac.compare_digest(hashlib.sha256(raw).hexdigest(), expected_sha256)):
            raise wire.CapacityError('Capacity policy changed; drain and reinstall the reviewed configuration')
    config = wire.decode(raw)
    wire.fields(config, ('schema', 'state_directory', 'total', 'reserve', 'disk_pool', 'mode'), ('cutover',))
    bridge = type(config['schema']) is int and config['schema'] == 1 and config['mode'] == 'legacy-bridge' and 'cutover' not in config
    full = type(config['schema']) is int and config['schema'] == 2 and config['mode'] == 'capacity' and 'cutover' in config
    if not (bridge or full):
        raise wire.CapacityError('Unsupported capacity broker configuration')
    state, disk = Path(config['state_directory']), Path(config['disk_pool'])
    if (not state.is_absolute() or not disk.is_absolute() or not disk.is_dir()
            or len(os.fsencode(state / 'broker.sock')) >= (104 if sys.platform == 'darwin' else 108)):
        raise wire.CapacityError('Capacity state/disk paths must be absolute and the Unix socket path short')
    for part in (state, *state.parents):
        if part.is_symlink() and str(part) not in ('/tmp', '/var', '/etc'):
            raise wire.CapacityError('Capacity state path cannot contain symlinks')
    if state.exists() and (not state.is_dir() or state.stat().st_uid != os.getuid() or state.stat().st_mode & 0o077):
        raise wire.CapacityError('Capacity state directory must be private and owned')
    total, reserve = wire.resources(config['total']), wire.resources(config['reserve'])
    if reserve.excess(total):
        raise wire.CapacityError('Capacity reserve exceeds total')
    settings = dict(state_directory=state, total=total, reserve=reserve, disk_pool=disk)
    if full:
        from . import capacity_compat
        if Path(config['cutover']) != capacity_compat.DEFAULT_RECORD:
            raise wire.CapacityError('Full capacity must use the machine default compatibility record')
        settings.update(mode='capacity', cutover=Path(config['cutover']), policy_sha256=hashlib.sha256(raw).hexdigest())
    return settings


def main(configpath):
    broker = CapacityBroker(**load_config(configpath, expected_sha256=os.environ.get('ATELIER_CAPACITY_SERVICE_CONFIG_SHA256')))
    try:
        broker.serve_forever()
    finally:
        broker.close()
    return 0
