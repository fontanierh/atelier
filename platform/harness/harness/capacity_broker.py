"""Production Unix capacity broker. Native activation and supervision are separate policy.

One serialized actor owns the SQLite transaction and every launch-gate writer. Restart fences
all old sessions and retains their allocations. Release uses exact retained exits or the scoped
exclusive monitored-tree cleanup policy; neither establishes universal process-tree discovery.
"""
from dataclasses import asdict
import array
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

from atelier.harness.capacity import Request, Resources, conflicts
from atelier.harness import capacity_protocol as wire
from atelier.harness import capacity_process_history as history

APPLICATION_ID = 0x41434231
SCHEMA = 'CREATE TABLE state (id INTEGER PRIMARY KEY CHECK(id=1), value TEXT NOT NULL)'
MAX_DATABASE = 32 * 1024 * 1024
HELD = {'running', 'draining', 'uncertain'}
MIN_CALIBRATED_MEMORY_MIB = 476  # 499,122,176 bytes, below the operator's decimal 500 MB maximum.


class PressureWait(wire.CapacityError):
    """An ordinary complete-memory deficit; never a failed guard or stale observation."""


class CapacityBroker:
    """@cc [owner:fontanierh,label:safety] production-serialized-capacity-gate
    Queued offers MUST charge no resources. Final complete-vector and lock accounting MUST commit
    before this broker's sole gate writer releases a child, in one serialized actor turn. Restart,
    lost health and missing exit evidence MUST retain grants. No process MAY be signalled here.
    Explicit operator-directed administrative abandonment MAY separately use current kernel
    quiescence for an interrupted exclusive compile, or a completed nonexclusive job with its
    original bound normal empty terminal, exact monitor/report fences and strictly absent
    controller/guards/retained identities. Both MUST require no other charge and two complete
    same-user censuses under the administrative policy. Neither MAY certify outputs or run
    through ordinary close/reconcile. Exact exit evidence covers the retained roster only. Bridge and performance-exclusive grants
    MAY instead use a positively exited root plus its bound aggregate guard's terminal empty-tree
    cleanup receipt; that witnesses the monitored owned tree, not every descendant's kernel exit.
    The adapter MUST retain exclusive legacy exclusion in bridge
    mode, verified sealed shared compatibility mutexes in full mode, or read-only exclusive
    ownership of every sealed legacy lane in explicit maintenance mode. Maintenance or an explicit
    calibrated full configuration MAY reduce the host memory reserve, with a 4096 MiB floor
    for maintenance or 476 MiB for explicitly calibrated full mode, and the sealed reserve as
    its ceiling. Explicit calibrated full mode MAY also reduce CPU reserve down to zero, but a
    changed CPU reserve MUST NOT expose more managed CPU than the actual logical host count.
    Ordinary full configuration MUST keep the exact sealed
    reserve; every other sealed configuration value MUST remain exact. Legacy temp_mib fields
    remain readable but MUST NOT constrain admission. Actual memory reservations, guard ceilings
    and complete remaining-memory-growth pressure checks MUST NOT shrink.
    """
    def __init__(self, state_directory, *, total, reserve=Resources(), disk_pool=None,
                 observe=None, lease_seconds=10., rpc_timeout=2., started=wire.process_start,
                 watch=wire.ExitWatch, guards=wire.validate_guards, child_of=wire.direct_child,
                 parent=wire.parent_pin, boot=wire.boot_id, alive=wire.live, mode='legacy-bridge',
                 cutover=None, policy_sha256=None, foreign=None, calibrated_memory_reserve=False):
        if mode not in ('legacy-bridge', 'capacity', 'sealed-maintenance'):
            raise wire.CapacityError('Unsupported production capacity mode')
        if (type(calibrated_memory_reserve) is not bool
                or (calibrated_memory_reserve and mode != 'capacity')):
            raise wire.CapacityError('Memory reserve calibration requires explicit full capacity')
        self.mode, self.cutover, self.policy_sha256 = mode, cutover, policy_sha256
        self.activation_id, self.compatible = None, True
        if mode in ('capacity', 'sealed-maintenance'):
            from atelier.harness import capacity_compat
            if (not isinstance(policy_sha256, str) or len(policy_sha256) != 64
                    or Path(cutover or '') != capacity_compat.DEFAULT_RECORD):
                raise wire.CapacityError('Full capacity requires the sealed machine policy')
            proof = (capacity_compat.verify_maintenance(cutover, policy_sha256=policy_sha256)
                     if mode == 'sealed-maintenance' else capacity_compat.verify(cutover, policy_sha256=policy_sha256))
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
        reserve_matches = True
        if mode in ('capacity', 'sealed-maintenance'):
            selected_reserve = asdict(self.reserve)
            reserve_matches = selected_reserve == proof['reserve']
            if calibrated_memory_reserve or (mode == 'sealed-maintenance' and not reserve_matches):
                floor = MIN_CALIBRATED_MEMORY_MIB if calibrated_memory_reserve else 4096
                expected = {**selected_reserve, 'memory_mib': proof['reserve']['memory_mib']}
                cpu_matches = True
                if calibrated_memory_reserve:
                    expected['cpu_millis'] = proof['reserve']['cpu_millis']
                    cpu_matches = (0 <= self.reserve.cpu_millis <= proof['reserve']['cpu_millis'] and
                        (self.reserve.cpu_millis == proof['reserve']['cpu_millis'] or
                         self.total.cpu_millis - self.reserve.cpu_millis <= (os.cpu_count() or 0) * 1000))
                reserve_matches = (floor <= self.reserve.memory_mib <= proof['reserve']['memory_mib']
                    and cpu_matches and expected == proof['reserve'])
        if mode in ('capacity', 'sealed-maintenance') and (proof['socket'] != str(self.socket_path)
                or proof['disk_pool'] != str(self.disk_pool)
                or proof['total'] != asdict(self.total) or not reserve_matches):
            raise wire.CapacityError('Broker resources or endpoint differ from the sealed policy')
        if len(os.fsencode(self.socket_path)) >= (104 if sys.platform == 'darwin' else 108):
            raise wire.CapacityError('Capacity Unix socket path is too long')
        self.database_path = self.directory / 'admission.sqlite'
        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._gates, self._watches = {}, {}
        self._queue_status = self._advisory_budget = None
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
                            exited = {tuple(pin) for pin in record.get('exited', [])}
                            for pin in record.get('roster', []):
                                if tuple(pin) not in exited:
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
        data = history.encode_state(self.directory, state)
        self.connection.execute('UPDATE state SET value=? WHERE id=1', (data,))
        self.connection.commit()
        released = {r.get('nonce') for r in state['records'].values() if r['state'] == 'released'}
        for nonce in released & self._gates.keys():
            self._gate_close(nonce)
        for key in [key for key in self._watches if key[0] in released]:
            self._watches.pop(key).close()

    def _clock(self):
        now = time.monotonic()
        if now < self._last_clock:
            raise wire.CapacityError('Capacity clock regressed')
        self._last_clock = now
        return now

    def _batch(self, message):
        pins = message.get('descendants', [])
        if type(pins) is not list or len(pins) > wire.MAX_ROSTER:
            raise wire.CapacityError('Capacity process batch exceeds its limit')
        return pins

    def _watch(self, record, pins, *, edges=(), exits=()):
        """Retain pins; resolve ancestry from positive edges; record the aggregate monitor's exits.

        ``edges``/``exits`` come only from a bound aggregate receipt. Every retained pin keeps the exact
        parent first known for it. A monitor edge fills only a parent the broker could not read itself.
        A receipt naming a pin twice, or a parent other than the one already known, is refused whole:
        none of its evidence applies. A monitor exit applies only to an already retained, non-root pin.
        Ancestry still needs a positive chain to the verified root.
        """
        pins = [wire.identity(pin) for pin in pins]
        roster = {tuple(pin) for pin in record.get('roster', [])}
        verified = {tuple(pin) for pin in record.get('verified_roster', [])}
        if len(roster | set(pins)) > wire.MAX_RETAINED:
            raise wire.CapacityError('Retained process roster exceeds its limit')
        # Records from before re-resolvable ancestry keep their sticky unknown.
        legacy_unknown = record.get('ancestry_unknown') is True and 'unresolved' not in record
        pending = {tuple(pin): tuple(parent) if parent is not None else None
                   for pin, parent in record.get('unresolved', [])}
        parents = {tuple(pin): tuple(parent) for pin, parent in record.get('parents', [])}
        for value in pins:
            pin = wire.identity(value)
            if pin == tuple(record['principal']):
                raise wire.CapacityError('The controller is not a workload descendant')
            if pin not in roster:
                roster.add(pin)
                self._watches[(record['nonce'], pin)] = self.watch_factory(pin)
                parent = self.parent(pin)
                pending[pin] = parent
                if parent is not None:
                    parents[pin] = tuple(parent)
        root = tuple(record['child']) if 'child' in record else None
        if root in roster:
            verified.add(root)  # start() separately validated its direct-parent edge.
            pending.pop(root, None)
            parents.setdefault(root, tuple(record['principal']))
        evidence = [*edges, *exits]
        named = [pin for pin, _ in edges], [pin for pin, _ in exits]
        conflict = (any(len(set(group)) != len(group) for group in named)
                    or any(pin in parents and parents[pin] != parent for pin, parent in evidence)
                    or any(dict(edges).get(pin, parent) != parent for pin, parent in exits))
        if conflict:
            request = record.get('request', {})
            print('capacity aggregate evidence refused: ' + json.dumps(dict(
                owner=request.get('owner'), purpose=request.get('purpose'), pid=(root or [None])[0],
                reason='duplicate or conflicting parent')), file=sys.stderr, flush=True)
            edges = exits = ()
        exited = {tuple(pin) for pin in record.get('exited', [])}
        for pin, parent in [*edges, *exits]:
            if pin in pending and pending[pin] is None:  # never a verified pin whose parent was not retained
                parents[pin] = pending[pin] = parent
        for pin, parent in exits:
            # A verified pin without a retained parent (an older record) cannot be checked; it stays unknown.
            if pin in roster and pin != root and parents.get(pin) == parent and pin not in exited:
                record.setdefault('exited', []).append(list(pin))
                exited.add(pin)
        while pending:
            found = [pin for pin, parent in pending.items() if parent in verified]
            if not found:
                break
            for pin in found:
                verified.add(pin)
                del pending[pin]
        record['roster'] = [list(pin) for pin in sorted(roster)]
        record['verified_roster'] = [list(pin) for pin in sorted(verified)]
        record['parents'] = [[list(pin), list(parent)] for pin, parent in sorted(parents.items()) if pin in roster]
        record['unresolved'] = [[list(pin), list(parent) if parent is not None else None]
                                for pin, parent in sorted(pending.items())]
        record['ancestry_unknown'] = legacy_unknown or bool(pending)

    def _terminal_guard_evidence(self, record):
        """The bound aggregate receipt's final exits, for helpers that left after the last live check.

        Exits are immutable facts about exact identities, so this needs the receipt's owner and ceiling,
        not freshness. Unreadable, foreign or malformed receipts add nothing.
        """
        try:
            item = wire.fields(record.get('guards', {}).get('tree_guard'), ('pid', 'start', 'report'))
            wire.identity((item['pid'], item['start']))
            receipt = wire.decode(wire.guard_report(wire.text(item['report'], maximum=4096)),
                                  limit=wire.GUARD_REPORT_LIMIT)
            if (wire.identity((receipt.get('owner'), receipt.get('owner_started'))) != tuple(record['child'])
                    or receipt.get('limit_bytes') != record['limit_bytes']):
                return
            processes = receipt.get('processes') or []
            if type(processes) is not list or any(type(v) is not dict or 'pid' not in v or 'started' not in v
                                                  for v in processes):
                return
            edges, exits = wire.guard_evidence(receipt)
        except (OSError, ValueError, KeyError, TypeError, wire.CapacityError):
            return
        self._watch(record, [], edges=edges, exits=exits)

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
            record['guard_completion_candidate'] = isinstance(error, wire.CapacityError) and str(error) in {
                'Capacity guard identity is not live and owned',
                'Capacity guard identity changed during validation',
                'Capacity guard receipt is stale or mismatched'}
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
                     'Invalid aggregate exit evidence',
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
        if self.mode in ('capacity', 'sealed-maintenance'):
            try:
                proof = self._compatibility_proof()
                self.compatible = proof['activation_id'] == self.activation_id
                if not self.compatible:
                    self._report_compatibility_failure(
                        state, wire.CapacityError('Capacity activation changed'), phase='refresh')
            except (OSError, ValueError, wire.CapacityError) as error:
                self.compatible = False
                self._report_compatibility_failure(state, error, phase='refresh')
        for record in state['records'].values():
            if record['state'] == 'released':
                continue  # Historical proof is immutable, not a live polling roster.
            if not self.compatible:
                changed |= record.pop('guard_completion_candidate', None) is not None
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
            exited = {tuple(pin) for pin in record.get('exited', [])}
            for pin in record.get('roster', []):
                if tuple(pin) in exited:
                    continue
                watch = self._watches.get((record['nonce'], tuple(pin)))
                if watch is not None and watch.poll():
                    record.setdefault('exited', []).append(pin)
                    exited.add(tuple(pin))
                    changed = True
            if record['state'] == 'running' and tuple(record['child']) in exited:
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
        exited = {tuple(pin) for pin in record.get('exited', [])}
        if (not record.get('ancestry_unknown') and all(tuple(pin) in exited for pin in record['roster'])):
            witness = {'kind': 'retained-kernel-exits'}
        else:
            witness = self._terminal_tree_exit(record)
            if witness is None:
                return False
        record.update(state='released', release_witness=witness)
        return True

    def _terminal_tree_exit(self, record, *, preserved=None):
        """@cc [owner:fontanierh,label:safety] exclusive-terminal-tree-release
        Only bridge or sealed-mode performance-exclusive grants MAY use this policy. The root MUST
        have affirmative exit evidence and its previously bound aggregate report MUST match
        identity, ceiling and invocation time, with completed cleanup. A normal child exit
        MUST satisfy the normal terminal sample checks. A memory/duration/controller-loss stop MUST have
        explicitly empty, zero post-drain cleanup and MUST NOT certify successful completion.
        A controller-loss receipt MUST bind the original controller and require that identity no longer live.
        A normal exit's processes/footprint MUST be empty/zero, or an older pre-cleanup sample whose
        entire reported tail has retained positive exits and an exact footprint sum.
        Any verifiably live retained identity MUST refuse release. This
        witnesses monitored-owned-tree cleanup, never individual historical kernel exits.
        """
        if (self.mode != 'legacy-bridge'
                and not (self.mode in ('capacity', 'sealed-maintenance') and record.get('request', {}).get('performance') is True)):
            return None
        if record.get('child') not in record.get('exited', []):
            return None
        return self._tree_end_observation(record, preserved=preserved, allow_stopped=True)

    def _stopped_terminal_sample(self, record, receipt):
        """Guard stops retain the offending sample separately from the observed cleanup."""
        if receipt.get('state') == 'controller_exited' and (
                receipt.get('controller') != record.get('principal') or self.alive(tuple(record['principal']))):
            return False
        if (receipt.get('cleanup_processes') != []
                or type(receipt.get('cleanup_footprint_bytes')) is not int
                or receipt['cleanup_footprint_bytes'] != 0):
            return False
        samples, footprint, peak = receipt.get('processes'), receipt.get('footprint_bytes'), receipt.get('peak_bytes')
        if (type(samples) is not list or len(samples) > wire.MAX_ROSTER
                or type(footprint) is not int or footprint < 0
                or type(peak) is not int or peak < footprint
                or (receipt['state'] == 'memory_limit') != (footprint > record['limit_bytes'])):
            return False
        seen, total = set(), 0
        for sample in samples:
            if type(sample) is not dict:
                return False
            pin = wire.identity((sample.get('pid'), sample.get('started')))
            amount = sample.get('footprint_bytes')
            if pin in seen or type(amount) is not int or amount < 0:
                return False
            seen.add(pin)
            total += amount
        return total == footprint

    def _settled_terminal_sample(self, record, receipt, exited):
        """Older monitors published the pre-drain sample beside successful post-drain cleanup.

        Never infer those remaining exits from missing PIDs, names or elapsed time: every
        reported tail must have its exact retained affirmative exit witness already recorded.
        """
        samples, footprint = receipt.get('processes'), receipt.get('footprint_bytes')
        if (type(samples) is not list or len(samples) > wire.MAX_ROSTER or type(footprint) is not int
                or not 0 <= footprint <= record['limit_bytes']):
            return False
        retained = {tuple(pin) for pin in record['roster']}
        seen, total = set(), 0
        for sample in samples:
            if type(sample) is not dict:
                return False
            pin = wire.identity((sample.get('pid'), sample.get('started')))
            amount = sample.get('footprint_bytes')
            if (pin == tuple(record['child']) or pin in seen or pin not in retained or pin not in exited
                    or self.alive(pin) or type(amount) is not int or amount < 0):
                return False
            seen.add(pin)
            total += amount
        return total == footprint

    def _tree_end_observation(self, record, *, preserved=None, pending=False, allow_stopped=False):
        """A pending observation hints to wait; it is never an exit witness or release authority."""
        try:
            item = wire.fields(record.get('guards', {}).get('tree_guard'), ('pid', 'start', 'report'))
            wire.identity((item['pid'], item['start']))  # Bound at start; terminal monitor may now have exited.
            report = wire.text(item['report'], maximum=4096)
            receipt = (wire.decode(wire.private_file(report, limit=wire.GUARD_REPORT_LIMIT, private=False),
                                   limit=wire.GUARD_REPORT_LIMIT)
                       if preserved is None else preserved)
            observed, ready = receipt.get('time'), record.get('first_ready')
            exited = {tuple(pin) for pin in record.get('exited', [])}
            stopped = receipt.get('state') in ('memory_limit', 'test_duration', 'controller_exited')
            sample_valid = (self._stopped_terminal_sample(record, receipt) if stopped and allow_stopped and not pending
                            else receipt.get('state') == 'child_exited'
                            and self._settled_terminal_sample(record, receipt, exited))
            if (type(observed) not in (int, float) or not math.isfinite(observed)
                    or type(ready) not in (int, float) or not math.isfinite(ready)
                    or not 0 < ready <= observed <= time.time()
                    or wire.identity((receipt.get('owner'), receipt.get('owner_started'))) != tuple(record['child'])
                    or type(receipt.get('limit_bytes')) is not int or receipt['limit_bytes'] != record['limit_bytes']
                    or receipt.get('cleanup_complete') is not True
                    or receipt.get('termination_reason') is not None
                    or not sample_valid
                    or (pending and (time.time() - observed > 3
                                     or type(receipt.get('observed_monotonic')) not in (int, float)
                                     or not 0 <= self._clock() - receipt['observed_monotonic'] <= 3))
                    or any(self.alive(wire.identity(pin)) for pin in record['roster']
                           if tuple(pin) not in exited and (not pending or pin != record['child']))):
                return None
        except (OSError, ValueError, KeyError, TypeError, wire.CapacityError):
            return None
        return {'kind': 'guarded-tree-stop' if stopped else 'guarded-tree-observation' if pending else 'guarded-tree-exit',
                'coverage': 'monitored-owned-tree', 'observed_at': observed}

    def _check_completion(self, record, *, reconcile=False):
        witness = record.get('release_witness', {})
        if (record['state'] == 'released' and record.get('child')
                and witness.get('kind') in ('retained-kernel-exits', 'guarded-tree-exit')):
            return dict(state='released', admission=False, terminal=True, child=record['child'])
        if (record['state'] == 'uncertain' and record.get('guard_completion_candidate') is True
                and self.compatible and self._clock() - record['heartbeat'] <= self.lease_seconds):
            observation = self._tree_end_observation(record, pending=True)
            if observation is None and reconcile and not record.get('completion_reconciled'):
                # Process and aggregate monitors publish independently. Keep the charge and all
                # ownership barriers while reconciling this one shutdown window, below RPC timeout.
                record['completion_reconciled'] = True
                deadline = time.monotonic() + .5
                while time.monotonic() < deadline:
                    if self._root_exited(record):
                        record['state'] = 'draining'  # Positive root event; still charged, no new GO.
                        return None
                    observation = self._tree_end_observation(record, pending=True)
                    if observation is not None:
                        break
                    time.sleep(.01)
            if observation is not None:
                return dict(state='uncertain', admission=False, finish_required=True, child=record['child'])
        return None

    def _heartbeat(self, state, record, batch, now):
        # A validated new observation must survive a refused heartbeat, rather than disappear
        # when the caller is told its grant is unhealthy. No refused resource vector is copied.
        if record['state'] in HELD:
            self._watch(record, batch)
        elif record['state'] == 'released':
            retained = {tuple(pin) for pin in record.get('roster', [])}
            retained.update(tuple(pin) for pin in record.get('terminal_observed', []))
            if any(tuple(pin) not in retained for pin in batch):
                raise wire.CapacityError('Terminal capacity check includes unretained process identities')
        for refresh in (False, True):
            if refresh:
                self._refresh(state, now)
            completion = self._check_completion(record, reconcile=True)
            if completion is not None:
                if completion.get('terminal') is True:
                    record['terminal_observed'] = [list(pin) for pin in batch]
                return dict(completion, epoch=state['epoch'])
            if record['state'] not in ('running', 'draining'):
                return dict(state=record['state'], admission=False, epoch=state['epoch'])
        if record['child'] in record.get('exited', []):
            record['state'] = 'draining'
        else:
            facts = self._guard_health(record)
            if facts is not None:
                self._watch(record, facts.roster, edges=facts.edges, exits=facts.exits)
                record.update(measured_memory_mib=facts.footprint_bytes // 1024**2, measured_at=time.time())
            completion = self._check_completion(record, reconcile=True)
            if completion is not None:
                if completion.get('terminal') is True:
                    record['terminal_observed'] = [list(pin) for pin in batch]
                return dict(completion, epoch=state['epoch'])
            if record['state'] not in ('running', 'draining'):
                return dict(state=record['state'], admission=False, epoch=state['epoch'])
        record['heartbeat'] = now
        return dict(state=record['state'], epoch=state['epoch'], admission=True)


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
        if self.mode in ('capacity', 'sealed-maintenance'):
            checkout = wire.text(value.get('checkout'), maximum=4096)
            if not Path(checkout).is_absolute() or 'checkout:' + checkout not in locks:
                raise wire.CapacityError('Full capacity requires its declared checkout named lock')
            if not vector.cpu_millis:
                raise wire.CapacityError('Full capacity requires a nonzero CPU reservation')
            if self.mode == 'sealed-maintenance' and (not performance or vector.cpu_millis != self.total.cpu_millis - self.reserve.cpu_millis):
                raise wire.CapacityError('Maintenance requires exclusive admission and the complete managed CPU budget')
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

    def _start_refusal(self, reason):
        print('capacity start refused: ' + json.dumps(dict(reason=reason, observed_at=time.time())),
              file=sys.stderr, flush=True)

    def _lost_offer(self, state, record, principal, message, *, reason='selection-changed'):
        """@cc [owner:fontanierh,label:safety] unexecuted-selection-loss
        A typed selection-change or pressure-wait denial MUST require a queued, fenced session, a still-pending
        broker-owned gate and a verified direct child. It MUST close that gate without writing GO,
        changing the request age or charging resources. Other refusal reasons MUST stay errors.
        """
        invalid = ('not-queued' if record['state'] != 'queued' else
                  'gate-unavailable' if record['nonce'] not in self._gates else
                  'compatibility' if not self.compatible else
                  'recovery' if any(r['state'] == 'uncertain' for r in state['records'].values()) else None)
        if invalid is not None:
            self._start_refusal(invalid)
            raise wire.CapacityError('Capacity offer is no longer selected')
        child = wire.identity(message['child'])
        if not self.child_of(principal, child):
            self._start_refusal('child-identity')
            raise wire.CapacityError('Launcher is not the pinned direct child')
        self._start_refusal(reason)
        self._gate_close(record['nonce'])  # EOF may end this owned gate child; no GO was written.
        return dict(state='queued', admission=False, no_go=True, reason=reason,
                    nonce=record['nonce'], epoch=state['epoch'], child=list(child))

    def _selection(self, state, *, pressure=False, advisory=False):
        """@cc [owner:fontanierh,label:safety] pressure-aware-uncharged-offer
        Offers MUST stay uncharged and retain ready age, sequence and bypass protection while
        complete memory is unavailable. Pressure-aware ranking MUST use one fresh observation
        and full validated remaining peer growth. After two bypasses or 900 seconds of original
        ready age, the oldest protected feasible request MUST drain before younger work,
        including performance-exclusive requests. Named-lock-blocked requests MUST retain their
        age/protection but MUST NOT impose an unrelated broker-wide drain.
        Missing advisory observations MUST keep offers queued without mutating holder health;
        final start observations MUST still fail closed on unavailable enforcement.
        This eligibility observation MUST NOT replace the final guarded GO pressure proof.
        """
        if not self.compatible or any(r['state'] == 'uncertain' for r in state['records'].values()):
            return None  # Accounting alone cannot replace a lost enforcement/ownership boundary.
        holders = [self._model(r) for r in state['records'].values() if r['state'] in HELD]
        queued = sorted((r for r in state['records'].values() if r['state'] == 'queued'), key=lambda r: r['sequence'])
        feasible = [r for r in queued if not conflicts(self._model(r), [], self.total, self.reserve)]
        held_locks = {lock for holder in holders for lock in holder.locks}
        protected = next((r for r in feasible if not held_locks.intersection(r['request']['locks'])
                          and (r.get('bypasses', 0) >= 2 or time.time() - r['first_ready'] >= 900.)), None)
        ranked = sorted(feasible, key=lambda r: (r is not protected if protected else False,
                                                r['request']['seconds'] > 300, r['sequence']))
        if not ranked:
            return None
        budget = None
        for record in ranked:
            if not conflicts(self._model(record), holders, self.total, self.reserve):
                if pressure:
                    if budget is None:
                        budget = self._pressure_budget(state, advisory=advisory)
                        if budget is None:
                            return None
                    memory, growth = budget
                    required = record['request']['resources']['memory_mib'] + self.reserve.memory_mib + growth
                    if memory < required:
                        if record is protected:
                            break
                        continue
                return record
            if record is protected:
                break
        return None

    def _pressure_budget(self, state, candidate=None, *, advisory=False):
        observation = self.observe()
        now = self._clock()
        if (type(observation) is not dict or type(observation.get('observed_monotonic')) not in (float, int)
                or not math.isfinite(observation['observed_monotonic'])
                or not 0 <= now - observation['observed_monotonic'] <= 2):
            if advisory:
                return None
            raise wire.CapacityError('Fresh capacity pressure observation unavailable')
        memory = wire.integer(observation.get('available_memory_mib'))
        growth_memory = 0
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
                    if advisory:
                        return None
                    record['state'] = 'draining' if self._root_exited(record) else 'uncertain'
                    raise wire.CapacityError('Existing holder enforcement is unavailable; reservation retained') from None
            growth_memory += max(0, vector.memory_mib - measured)
        if advisory:
            self._advisory_budget = dict(memory=memory, growth=growth_memory,
                                         observed=observation['observed_monotonic'])
        return memory, growth_memory

    def _pressure(self, state, candidate):
        memory, growth = self._pressure_budget(state, candidate)
        required = candidate['request']['resources']['memory_mib'] + self.reserve.memory_mib + growth
        if memory < required:
            raise PressureWait('Capacity pressure refuses the complete reservation')

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
                      or not {tuple(pin) for pin in record['roster']} <=
                             {tuple(pin) for pin in record.get('exited', [])}):
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

    def _report_compatibility_failure(self, state, error, *, phase):
        """@cc [owner:fontanierh,label:safety] compatibility-failure-evidence
        Compatibility failures MUST attempt to record a redacted reason, wall/monotonic time and activation,
        epoch and affected request identities without changing refusal, charges or recovery rules.
        Request identity lists MUST be bounded, with the total affected count retained.
        """
        try:
            from atelier.harness.capacity_compat_diagnostics import failure_reason
            affected = sorted(key for key, record in state['records'].items() if record['state'] in HELD)
            print('capacity compatibility failure: ' + json.dumps(dict(
                phase=phase, reason=failure_reason(error), error_type=type(error).__name__,
                errno=error.errno if isinstance(error, OSError) else None,
                observed_at=time.time(), observed_monotonic=self._clock(), epoch=state.get('epoch'),
                activation_id=self.activation_id, boot_id=self.boot,
                affected_request_ids=affected[:32], affected_request_count=len(affected))),
                file=sys.stderr, flush=True)
        except Exception:
            pass  # Diagnostic/import/serialization failures cannot affect enforcement.

    def _compatibility_proof(self):
        from atelier.harness import capacity_compat
        verifier = capacity_compat.verify_maintenance if self.mode == 'sealed-maintenance' else capacity_compat.verify
        return verifier(self.cutover, policy_sha256=self.policy_sha256)

    def _validate_compatibility(self, state):
        if self.mode not in ('capacity', 'sealed-maintenance'):
            return
        try:
            proof = self._compatibility_proof()
            if proof['activation_id'] != self.activation_id:
                raise wire.CapacityError('Capacity activation changed')
        except (OSError, ValueError, wire.CapacityError) as error:
            self.compatible = False
            retained = [record for record in state['records'].values() if record['state'] in HELD]
            for record in retained:
                record['state'] = 'uncertain'
            self._report_compatibility_failure(state, error, phase='admission')
            raise wire.CapacityError('Full-capacity compatibility changed before admission; charges retained') from None

    def _gate_close(self, nonce):
        fd = self._gates.pop(nonce, None)
        if fd is not None:
            os.close(fd)

    def _dispose(self, nonce):
        self._gate_close(nonce)
        for key in [key for key in self._watches if key[0] == nonce]:
            self._watches.pop(key).close()

    def _queue_context(self, state):
        return json.dumps(dict(mode=self.mode, boot=self.boot, total=asdict(self.total), reserve=asdict(self.reserve),
                               records=[dict(id=key, state=r['state'], request=r['request'],
                                nonce=r.get('nonce'), child=r.get('child'), principal=r.get('principal'),
                                limit=r.get('limit_bytes'), sequence=r['sequence'],
                                first_ready=r['first_ready'], bypasses=r['bypasses'])
                           for key, r in sorted(state['records'].items())
                           if r['state'] in HELD or r['state'] == 'queued']), sort_keys=True)

    def _fresh_queue_status(self, state):
        snapshot = self._queue_status
        age = self._clock() - snapshot['budget']['observed'] if snapshot and snapshot['budget'] else -1
        if (snapshot is not None and snapshot['epoch'] == state['epoch'] and 0 <= age <= 2
                and snapshot['context'] == self._queue_context(state)):
            return snapshot, age
        return None, None

    def _queue_pressure_reason(self, record, snapshot, age):
        request = record['request']['resources']['memory_mib']
        required = request + self.reserve.memory_mib + snapshot['budget']['growth']
        available = snapshot['budget']['memory']
        prefix = ('waiting for memory' if available < required else
                  'advisory offer eligible; guarded start still required' if snapshot['selected'] == record['request']['id'] else
                  'waiting behind queue priority')
        return (f'{prefix}: {available} MiB available, {required} MiB required '
                f'({request} request + {self.reserve.memory_mib} host reserve + '
                f'{snapshot["budget"]["growth"]} remaining peer growth); '
                f'deficit {max(0, required - available)} MiB; sample age {age:.1f}s')

    def _status(self, state):
        """@cc [owner:fontanierh,label:correctness] cached-pressure-status-is-advisory
        Queue pressure arithmetic and selected identity MUST come only from a successful advisory
        pressure observation, including evaluations with no selected offer, no older than two seconds,
        with unchanged queued/held context and epoch.
        Stale or changed context MUST be reported as unknown, never selected or available.
        Pressure claims MUST carry an expiry bounded by that observation; display consumers MUST
        invalidate expired claims locally without waiting for their next broker poll.
        Status MUST NOT sample memory, validate guards or mutate holder health for this display.
        Displayed eligibility MUST NOT certify a guarded start or change admission/fairness.
        """
        records = list(state['records'].values())
        charged = [r for r in records if r['state'] in HELD]
        used = Resources()
        for record in charged:
            used += wire.resources(record['request']['resources'])
        result = dict(epoch=state['epoch'], boot_id=self.boot, mode=self.mode, cutover=self.mode == 'capacity',
                      observed_at=time.time(), observed_monotonic=time.monotonic(),
                      recovering=not self.compatible or any(r['state'] == 'uncertain' for r in records),
                      total=asdict(self.total.admission()), reserve=asdict(self.reserve.admission()),
                      charged_resources=asdict(used.admission()),
                      charged_count=len(charged), waiting_count=sum(r['state'] == 'queued' for r in records),
                      total_records=len(records), records=[], truncated=False)
        if self.mode in ('capacity', 'sealed-maintenance'):
            result['compatibility_healthy'] = self.compatible
        snapshot, age = self._fresh_queue_status(state)
        for record in sorted(records, key=lambda r: (r['state'] not in HELD, r['state'] != 'queued',
                                                     -r['sequence'] if r['state'] == 'released' else r['sequence'])):
            request = record['request']
            blockers = conflicts(self._model(record), [self._model(r) for r in charged], self.total, self.reserve)
            reason = ('uncertain ownership or enforcement; reservation retained' if record['state'] == 'uncertain' else
                      'capacity recovery blocks new grants' if result['recovering'] and record['state'] == 'queued' else
                      ('; '.join(blockers) if blockers else
                       self._queue_pressure_reason(record, snapshot, age) if snapshot else
                       'waiting for a fresh pressure eligibility observation; no resources held') if record['state'] == 'queued' else
                      'not currently ready; retry required' if record['state'] == 'waiting' else '')
            item = dict(id=request['id'], owner=request.get('owner'), checkout=request.get('checkout'),
                        purpose=request.get('purpose'), phase=request.get('phase'),
                        state=record['state'], charged=record['state'] in HELD, resources=request['resources'],
                        locks=request['locks'], first_ready=record['first_ready'], sequence=record['sequence'],
                        bypasses=record['bypasses'], retained=history.count(record, 'roster'),
                        witnessed=history.count(record, 'exited'), wait_reason=reason,
                        pressure_expires_at=(result['observed_at'] + 2 - age
                                             if record['state'] == 'queued' and snapshot and not blockers
                                             and not result['recovering'] else None),
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
        known = set()
        for record in state['records'].values():
            if record['state'] in HELD:
                exited = {tuple(pin) for pin in record.get('exited', [])}
                known.update(tuple(pin) for pin in record.get('verified_roster', []) if tuple(pin) not in exited)
        return [list(pin) for pin in pins if pin in known and self.started(pin[0]) == pin[1] and self.alive(pin)]

    def _foreign_check(self, state):
        from atelier.harness.safety.render_lock import native_candidates
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
                            'activation_id', 'candidates', 'preserved_terminal', 'interrupted_compile', 'completed_job'))
                if message['namespace'] != wire.NAMESPACE:
                    raise wire.CapacityError('Production broker namespace required')
                action = message['action']
                if 'interrupted_compile' in message and action != 'abandon-interrupted':
                    raise wire.CapacityError('Interrupted compile evidence requires explicit administrative action')
                if 'completed_job' in message and action != 'abandon-completed':
                    raise wire.CapacityError('Completed job evidence requires explicit administrative action')
                if 'preserved_terminal' in message and action != 'reconcile':
                    raise wire.CapacityError('Preserved terminal evidence is allowed only for reconciliation')
                if self.mode in ('capacity', 'sealed-maintenance') and action not in ('status', 'reconcile', 'close', 'abandon-interrupted', 'abandon-completed'):
                    if not self.compatible or message.get('activation_id') != self.activation_id:
                        if action == 'start':
                            self._start_refusal('compatibility-fence')
                        raise wire.CapacityError('Full-capacity compatibility proof is unavailable or mismatched')
                if action in ('abandon-interrupted', 'abandon-completed'):
                    completed = action == 'abandon-completed'
                    from atelier.harness import capacity_abandon
                    evidence = wire.fields(message.get('completed_job' if completed else 'interrupted_compile', {}),
                        ('id', 'nonce', 'epoch', 'boot_id', 'operator_reference', 'administrator', 'services')
                        + (('guards', 'report_sha256') if completed else ()))
                    print(json.dumps({'event': 'capacity administrative abandon attempt',
                                      'epoch': state['epoch'], 'peer_pid': principal[0]}), file=sys.stderr, flush=True)
                    if self.mode != 'capacity' or not self.compatible:
                        raise wire.CapacityError('Administrative recovery requires healthy full-capacity compatibility')
                    record = state['records'].get(evidence.get('id'))
                    if record is None:
                        raise wire.CapacityError('Interrupted compile request does not exist')
                    if any(other is not record and other['state'] in HELD for other in state['records'].values()):
                        raise wire.CapacityError('Another charged job prevents interrupted compile recovery')
                    witness = capacity_abandon.recover(record, evidence, principal=principal, boot=self.boot,
                                                       epoch=state['epoch'], completed=completed)
                    record.update(state='released', release_witness=witness)
                    result = {'released': True, 'state': 'released', 'witness': witness}
                elif action in ('status', 'reconcile'):
                    if action == 'reconcile':
                        if 'preserved_terminal' in message:
                            refreshed |= self._preserved_terminal(state, message['preserved_terminal'])
                        for retained in state['records'].values():
                            refreshed |= self._settle_exited(retained)
                    result = self._status(state)
                elif action == 'owned':
                    if (self.mode not in ('capacity', 'sealed-maintenance') or message.get('boot_id') != self.boot
                            or message.get('epoch') != state['epoch']):
                        raise wire.CapacityError('Capacity ownership observation was fenced')
                    result = dict(owned=self._owned(state, message.get('candidates')), epoch=state['epoch'])
                elif action == 'offer':
                    if ('epoch' in message or 'boot_id' in message) and (
                            message.get('epoch') != state['epoch'] or message.get('boot_id') != self.boot):
                        raise wire.CapacityError('Capacity requeue was fenced by restart')
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
                        record.pop('guard_completion_candidate', None)
                        record.pop('completion_reconciled', None)
                        record.pop('terminal_observed', None)
                        record.update(nonce=secrets.token_hex(32), principal=list(principal), roster=[], exited=[],
                                      verified_roster=[], ancestry_unknown=False)
                        record.pop('process_history', None)
                    record.update(request=request, state='queued', epoch=state['epoch'], heartbeat=now)
                    self._advisory_budget = None
                    selected_record = self._selection(state, pressure=True, advisory=True)
                    selected = selected_record is record
                    self._queue_status = dict(epoch=state['epoch'], context=self._queue_context(state),
                                              budget=self._advisory_budget,
                                              selected=selected_record['request']['id'] if selected_record else None)
                    snapshot, age = self._fresh_queue_status(state)
                    blockers = conflicts(self._model(record),
                                         [self._model(r) for r in state['records'].values() if r['state'] in HELD],
                                         self.total, self.reserve)
                    reason = ('capacity recovery blocks new grants' if not self.compatible or
                              any(r['state'] == 'uncertain' for r in state['records'].values()) else
                              '; '.join(blockers) if blockers else
                              self._queue_pressure_reason(record, snapshot, age) if snapshot else
                              'waiting for a fresh pressure eligibility observation; no resources held')
                    result = {'selected': selected, 'state': 'offered' if selected else 'queued',
                              'nonce': record['nonce'], 'epoch': state['epoch'], 'first_ready': record['first_ready'],
                              'wait_reason': reason}
                else:
                    record = state['records'].get(message.get('id'))
                    if (record is None or tuple(record['principal']) != principal or message.get('nonce') != record['nonce']):
                        if action == 'start':
                            self._start_refusal('session-identity')
                        raise wire.CapacityError('Capacity session identity mismatch')
                    wire.integer(message.get('epoch'), minimum=1)
                    old_close = action == 'close' and message['epoch'] == record['epoch']
                    if message.get('boot_id') != self.boot or (not old_close and
                            (message['epoch'] != state['epoch'] or record['epoch'] != state['epoch'])):
                        if action == 'start':
                            self._start_refusal('restart-fence')
                        raise wire.CapacityError('Capacity session was fenced by restart')
                    if self.started(principal[0]) != principal[1] or not self.alive(principal):
                        raise wire.CapacityError('Capacity controller identity is no longer live')
                    if action in ('check', 'close'):
                        batch = self._batch(message)
                    if action == 'gate':
                        if record['state'] != 'queued' or record['nonce'] in self._gates:
                            raise wire.CapacityError('Capacity gate is unavailable')
                        fd, writer = os.pipe()
                        os.set_inheritable(fd, False)
                        self._gates[record['nonce']] = writer
                        result = {'state': 'gated', 'epoch': state['epoch']}
                    elif action == 'start':
                        if record['state'] != 'queued' or self._selection(state, pressure=True) is not record or record['nonce'] not in self._gates:
                            result = self._lost_offer(state, record, principal, message, reason=
                                'pressure-wait' if self._selection(state) is record else 'selection-changed')
                        else:
                            child = wire.identity(message['child'])
                            if not self.child_of(principal, child):
                                raise wire.CapacityError('Launcher is not the pinned direct child')
                            guards = {name: message[name] for name in ('process_guard', 'tree_guard')}
                            facts = self.guards(guards, child, principal, message['limit_bytes'],
                                                 record['request']['resources']['memory_mib'])
                            if self.mode in ('capacity', 'sealed-maintenance'):
                                if self.guards is wire.validate_guards:
                                    wire.require_independent_guards(guards, principal)
                                self._foreign_check(state)
                            try:
                                self._pressure(state, record)
                            except PressureWait:
                                result = self._lost_offer(state, record, principal, message, reason='pressure-wait')
                            else:
                                self._validate_compatibility(state)
                                self._validate_holders(state, record)
                                # Revalidate after all compatibility, process-scan and pressure I/O.
                                facts = self.guards(guards, child, principal, message['limit_bytes'],
                                                    record['request']['resources']['memory_mib'])
                                if self.mode in ('capacity', 'sealed-maintenance') and self.guards is wire.validate_guards:
                                    wire.require_independent_guards(guards, principal)
                                if self.started(child[0]) != child[1] or self.started(principal[0]) != principal[1]:
                                    raise wire.CapacityError('Launcher/controller changed before admission')
                                record['child'] = list(child)
                                self._watch(record, [child, *facts.roster], edges=facts.edges, exits=facts.exits)
                                record.update(state='running', child=list(child), guards=guards,
                                              limit_bytes=message['limit_bytes'], heartbeat=self._clock(),
                                              measured_memory_mib=facts.footprint_bytes // 1024**2, measured_at=time.time())
                                for earlier in state['records'].values():
                                    if earlier['state'] == 'queued' and earlier['sequence'] < record['sequence']:
                                        earlier['bypasses'] += 1
                                go = record['nonce']
                                result = {'state': 'running', 'epoch': state['epoch'], 'admission': True}
                    elif action == 'check':
                        result = self._heartbeat(state, record, batch, now)
                    elif action == 'close':
                        self._gate_close(record['nonce'])
                        if record['state'] not in HELD:
                            self._dispose(record['nonce'])
                            record['state'] = 'waiting'
                            record.pop('terminal_observed', None)
                            result = {'state': 'waiting', 'released': True}
                        else:
                            self._watch(record, batch)
                            witness = message.get('witness')
                            if witness is not None:
                                wire.fields(witness, ('kind', 'parent', 'child', 'returncode'))
                                if (witness['kind'] != 'direct-parent-wait' or wire.identity(witness['parent']) != principal
                                        or wire.identity(witness['child']) != tuple(record['child'])
                                        or type(witness['returncode']) is not int):
                                    raise wire.CapacityError('Invalid direct-parent exit witness')
                                # This authenticated adapter reports its actual Popen wait status.
                                record.setdefault('exited', []).append(record['child']) if record['child'] not in record.get('exited', []) else None
                            self._terminal_guard_evidence(record)
                            self._refresh(state, now)
                            if record['state'] != 'released':
                                record['state'] = 'uncertain'
                                self._settle_exited(record)
                            complete = record['state'] == 'released'
                            if complete:
                                record.pop('terminal_observed', None)
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
                if action in ('status', 'reconcile', 'owned') and not refreshed:
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
                        **({'activation_id': self.activation_id} if self.mode in ('capacity', 'sealed-maintenance') else {}), **result}, fd
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
        """@cc [owner:fontanierh,label:safety] bounded-capacity-actor-io
        Request mutations and gate writes MUST remain serialized on this actor. A slow reader
        MUST NOT block other clients: replies MUST use nonblocking selector writes, with at most
        MAX_FRAME reply bytes per client, at most 32 clients and the original accept-time RPC deadline.
        A returned descriptor MUST be transferred at most once and closed locally on transfer,
        disconnect, expiry or shutdown. Reply failure MUST NOT release a grant or authorize work.
        Diagnostics MUST contain only operation, phase, duration, observation time, exception type and errno;
        diagnostics failures MUST NOT change accounting or the operation result.
        """
        selector = selectors.DefaultSelector()
        selector.register(self.listener, selectors.EVENT_READ)
        clients = {}

        def report(peer, error=None):
            try:
                now = time.monotonic()
                elapsed = now - peer['started']
                if error is None and elapsed < .25:
                    return
                timings = {**peer['timings'], peer['phase'] + '_seconds': round(now - peer['phase_started'], 3)}
                metadata = dict(action=peer['action'], phase=peer['phase'],
                                elapsed_seconds=round(elapsed, 3), observed_at=time.time(), **timings)
                if error is not None:
                    metadata.update(error_type=type(error).__name__,
                                    errno=error.errno if isinstance(error, OSError) else None)
                label = 'capacity operation refused: ' if error is not None else 'capacity slow operation: '
                print(label + json.dumps(metadata), file=sys.stderr, flush=True)
            except Exception:
                pass  # Diagnostic output cannot change grant accounting or operation results.

        def advance(peer, phase):
            now = time.monotonic()
            peer['timings'][peer['phase'] + '_seconds'] = round(now - peer['phase_started'], 3)
            peer.update(phase=phase, phase_started=now)

        def close_peer(channel):
            peer = clients.pop(channel)
            if peer['fd'] is not None:
                os.close(peer['fd'])
                peer['fd'] = None
            try:
                selector.unregister(channel)
            except (KeyError, ValueError, OSError):
                pass
            channel.close()

        def queue_reply(channel, peer, result, fd=None):
            peer['fd'] = fd
            advance(peer, 'send')
            peer['reply'] = wire.encode(result)
            selector.modify(channel, selectors.EVENT_WRITE)

        try:
            while not self._stop.is_set():
                for key, _ in selector.select(.1):
                    channel = key.fileobj
                    if channel is self.listener:
                        try:
                            channel, _ = self.listener.accept()
                        except (BlockingIOError, InterruptedError):
                            continue
                        channel.setblocking(False)
                        if len(clients) >= 32:
                            channel.close()
                            continue
                        try:
                            principal = wire.peer(channel)
                        except (OSError, ValueError, wire.CapacityError):
                            channel.close()
                            continue
                        now = time.monotonic()
                        clients[channel] = dict(buffer=bytearray(), deadline=now + self.rpc_timeout,
                            principal=principal, started=now, phase_started=now, timings={},
                            action='invalid', phase='receive', reply=None, sent=0, fd=None, refused=False)
                        selector.register(channel, selectors.EVENT_READ)
                        continue
                    peer = clients[channel]
                    if time.monotonic() >= peer['deadline']:
                        report(peer, TimeoutError())
                        close_peer(channel)
                        continue
                    try:
                        if peer['reply'] is not None:
                            remaining = memoryview(peer['reply'])[peer['sent']:]
                            if peer['fd'] is not None:
                                ancillary = [(socket.SOL_SOCKET, socket.SCM_RIGHTS, array.array('i', [peer['fd']]))]
                                try:
                                    sent = channel.sendmsg([remaining], ancillary)
                                except (BlockingIOError, InterruptedError):
                                    continue
                            else:
                                try:
                                    sent = channel.send(remaining)
                                except (BlockingIOError, InterruptedError):
                                    continue
                            if sent <= 0:
                                raise ConnectionError('Capacity peer stopped receiving')
                            if peer['fd'] is not None:
                                descriptor, peer['fd'] = peer['fd'], None
                                os.close(descriptor)
                            peer['sent'] += sent
                            if peer['sent'] == len(peer['reply']):
                                if not peer['refused']:
                                    report(peer)
                                close_peer(channel)
                            continue
                        buffer = peer['buffer']
                        try:
                            data = channel.recv(wire.MAX_FRAME + 1 - len(buffer))
                        except (BlockingIOError, InterruptedError):
                            continue
                        if not data:
                            raise wire.CapacityError('Capacity peer closed its request')
                        buffer.extend(data)
                        if len(buffer) > wire.MAX_FRAME:
                            raise wire.CapacityError('Capacity message exceeds its limit')
                        if b'\n' not in buffer:
                            continue
                        if not buffer.endswith(b'\n') or buffer.count(b'\n') != 1:
                            raise wire.CapacityError('One capacity operation per connection is required')
                        message = wire.decode(bytes(buffer[:-1]))
                        peer['action'] = wire.action_name(message)
                        advance(peer, 'handle')
                        result, fd = self.handle(message, peer['principal'])
                        queue_reply(channel, peer, {'ok': True, **result}, fd)
                    except (OSError, ValueError, KeyError, TypeError, sqlite3.Error, wire.CapacityError) as error:
                        report(peer, error)
                        if peer['reply'] is not None or peer['phase'] == 'send':
                            close_peer(channel)
                            continue
                        peer['refused'] = True
                        try:
                            queue_reply(channel, peer, {'ok': False, 'namespace': wire.NAMESPACE,
                                'error': str(error) if isinstance(error, wire.CapacityError)
                                else 'Capacity broker refused this operation'})
                        except (OSError, ValueError, TypeError, wire.CapacityError):
                            close_peer(channel)
                for channel, peer in list(clients.items()):
                    if time.monotonic() >= peer['deadline']:
                        report(peer, TimeoutError())
                        close_peer(channel)
                began = time.monotonic()
                with self._lock:
                    state = self._load()
                    if self._refresh(state, self._clock()):
                        self._save(state)
                    else:
                        self.connection.rollback()
                report(dict(started=began, phase_started=began, phase='refresh',
                            action='maintenance', timings={}))
        finally:
            for channel in list(clients):
                close_peer(channel)
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
    wire.fields(config, ('schema', 'state_directory', 'total', 'reserve', 'disk_pool', 'mode'), ('cutover', 'seal_policy_sha256'))
    bridge = type(config['schema']) is int and config['schema'] == 1 and config['mode'] == 'legacy-bridge' and 'cutover' not in config and 'seal_policy_sha256' not in config
    full = type(config['schema']) is int and config['schema'] == 2 and config['mode'] == 'capacity' and 'cutover' in config and 'seal_policy_sha256' not in config
    maintenance = (type(config['schema']) is int and config['schema'] == 3 and config['mode'] == 'sealed-maintenance'
                   and 'cutover' in config and isinstance(config.get('seal_policy_sha256'), str)
                   and len(config['seal_policy_sha256']) == 64
                   and all(c in '0123456789abcdef' for c in config['seal_policy_sha256']))
    calibrated = (type(config['schema']) is int and config['schema'] == 4 and config['mode'] == 'capacity'
                  and 'cutover' in config and isinstance(config.get('seal_policy_sha256'), str)
                  and len(config['seal_policy_sha256']) == 64
                  and all(c in '0123456789abcdef' for c in config['seal_policy_sha256']))
    if not (bridge or full or maintenance or calibrated):
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
    if full or maintenance or calibrated:
        from atelier.harness import capacity_compat
        if Path(config['cutover']) != capacity_compat.DEFAULT_RECORD:
            raise wire.CapacityError('Full capacity must use the machine default compatibility record')
        settings.update(mode=config['mode'], cutover=Path(config['cutover']),
                        policy_sha256=config['seal_policy_sha256'] if maintenance or calibrated else hashlib.sha256(raw).hexdigest())
    if calibrated:
        settings['calibrated_memory_reserve'] = True
    return settings


def main(configpath):
    expected = os.environ.get('ATELIER_CAPACITY_SERVICE_CONFIG_SHA256')
    settings = load_config(configpath, expected_sha256=expected)
    if expected is None and (settings.get('mode') == 'sealed-maintenance'
                             or settings.get('calibrated_memory_reserve')):
        raise wire.CapacityError('Calibrated policy requires a supervised configuration digest')
    broker = CapacityBroker(**settings)
    try:
        broker.serve_forever()
    finally:
        broker.close()
    return 0
