"""Private bounded legacy-authority transport; no reconnect, retry or local permission policy."""
import json
import math
import os
import select
import stat
import struct
import time

MAX_FRAME_BYTES = 256 * 1024
MAX_RECORD_BYTES = 4 * 1024 * 1024
MAX_DEPTH = 24
MAX_VALUES = 32768
CLOCK_ID = 'posix-clock-monotonic-v1'
HOST_SELECTION_NS = 48 * 60 * 60 * 1_000_000_000
HOST_STARTUP_NS = 60 * 1_000_000_000
HOST_CLEANUP_NS = 600 * 1_000_000_000


class AuthorityLost(RuntimeError):
    """The original exchange is uncertain; no further work may be authorized on it."""


class AuthorityRefused(RuntimeError):
    """The original host explicitly refused this request; never a fallback permission."""


def authority_now_ns():
    """Exact Rust clock_gettime(CLOCK_MONOTONIC) domain, including on Darwin.

    Python time.monotonic/ns uses a different Darwin numeric epoch. There is no fallback
    or conversion from that clock, boot identity, wall time or received timestamps.
    """
    try:
        return time.clock_gettime_ns(time.CLOCK_MONOTONIC)
    except (AttributeError, OSError):
        raise AuthorityLost('shared authority clock is unavailable') from None


def host_budgets(*, enclosing_deadline_ns=None):
    """@cc [owner:fontanierh,label:safety] bounded-legacy-authority-lifetime
    The ordinary managed host MUST use one POSIX-clock absolute deadline with a 48-hour
    operational ceiling, 60-second startup allowance and 600-second cleanup reserve. An
    actually supplied same-domain enclosing deadline MUST shorten this bound; startup and
    cleanup MUST fit before launch. This MUST NOT alter native guard/resource ceilings,
    claim measured cold-build fit, reuse the M1 watch deadline, or reset epoch transitions.
    Exhaustion MUST preserve the fence/verified work for ordinary continuation, not force
    cleanup or claim completion. See test_build_v2_legacy_client.py.
    """
    now = authority_now_ns()
    deadline = now + HOST_SELECTION_NS
    if enclosing_deadline_ns is not None:
        if type(enclosing_deadline_ns) is not int or not 0 < enclosing_deadline_ns <= 2**63 - 1:
            raise AuthorityLost('invalid enclosing authority deadline')
        deadline = min(deadline, enclosing_deadline_ns)
    if deadline - now <= HOST_STARTUP_NS + HOST_CLEANUP_NS or deadline > 2**63 - 1:
        raise AuthorityLost('authority lifetime cannot cover startup and cleanup')
    return {'clock_domain': CLOCK_ID, 'deadline_ns': deadline,
            'startup_budget_ns': HOST_STARTUP_NS, 'cleanup_budget_ns': HOST_CLEANUP_NS}


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise AuthorityLost('duplicate authority record field')
        result[key] = value
    return result


def _bounded(value, budget=None, depth=0):
    budget = [MAX_VALUES, MAX_FRAME_BYTES] if budget is None else budget
    budget[0] -= 1
    if budget[0] < 0 or depth > MAX_DEPTH:
        raise AuthorityLost('authority record exceeds structural bounds')
    if type(value) is dict:
        if any(type(key) is not str for key in value):
            raise AuthorityLost('authority record needs string fields')
        for key in value:
            _bounded(key, budget, depth + 1)
        for child in value.values():
            _bounded(child, budget, depth + 1)
    elif type(value) in (list, tuple):
        for child in value:
            _bounded(child, budget, depth + 1)
    elif type(value) is float:
        if not math.isfinite(value):
            raise AuthorityLost('nonfinite authority value')
    elif type(value) is str:
        if len(value) > MAX_FRAME_BYTES:
            raise AuthorityLost('authority text exceeds frame bound')
        try:
            budget[1] -= len(value.encode('utf-8'))
        except UnicodeError:
            raise AuthorityLost('authority text is not valid UTF8') from None
        if budget[1] < 0:
            raise AuthorityLost('authority text exceeds frame bound')
    elif type(value) is int and not -(2**63) <= value <= 2**64 - 1:
        raise AuthorityLost('authority integer exceeds wire bound')
    elif value is not None and type(value) not in (str, int, bool):
        raise AuthorityLost('unsupported authority value')


def encode_record(record):
    if type(record) is not dict:
        raise AuthorityLost('authority envelope must be an object')
    _bounded(record)
    raw = json.dumps(record, ensure_ascii=False, allow_nan=False,
                     separators=(',', ':')).encode('utf-8')
    if not raw or len(raw) > MAX_FRAME_BYTES:
        raise AuthorityLost('authority frame exceeds size bound')
    return len(raw).to_bytes(4, 'big') + raw


def decode_record(raw):
    if type(raw) is not bytes or not raw or len(raw) > MAX_FRAME_BYTES:
        raise AuthorityLost('invalid authority frame size')
    def nonfinite(_):
        raise AuthorityLost('nonfinite authority value')
    try:
        record = json.loads(raw, object_pairs_hook=_unique, parse_constant=nonfinite)
    except (ValueError, UnicodeError, RecursionError) as error:
        raise AuthorityLost('invalid authority JSON') from error
    if type(record) is not dict:
        raise AuthorityLost('authority envelope must be an object')
    _bounded(record)
    return record


class LegacyChannel:
    """@cc [owner:fontanierh,label:correctness;safety] legacy-authority-channel-fail-closed
    Each exchange MUST use the original private framed pipes and an absolute deadline.
    EOF, timeout, malformed/truncated data, uncertain send or reply MUST latch the channel
    failed; no reconnect or automatic retry may grant more work. JSON/framing produces
    observations only, never an epoch or task capability. Callers MUST verify exact closed
    protocol shape and correlation before consuming a reply. See test_build_v2_legacy_client.py.
    """
    def __init__(self, command_fd, reply_fd, *, deadline_ns, clock_domain=CLOCK_ID):
        if (type(command_fd) is not int or type(reply_fd) is not int
                or command_fd < 3 or reply_fd < 3 or command_fd == reply_fd
                or clock_domain != CLOCK_ID or type(deadline_ns) is not int
                or not authority_now_ns() < deadline_ns <= 2**63 - 1):
            raise AuthorityLost('invalid authority pipe or deadline')
        for descriptor in (command_fd, reply_fd):
            if not stat.S_ISFIFO(os.fstat(descriptor).st_mode) or os.get_inheritable(descriptor):
                raise AuthorityLost('authority endpoint must be a private CLOEXEC pipe')
            os.set_blocking(descriptor, False)
        self.command_fd = command_fd
        self.reply_fd = reply_fd
        self.deadline_ns = deadline_ns
        self.failed = False
        self.pending = False
        self.closed = False

    def _wait(self, descriptor, *, writing):
        while True:
            remaining = (self.deadline_ns - authority_now_ns()) / 1e9
            if remaining <= 0:
                raise AuthorityLost('authority deadline expired')
            try:
                ready = select.select([] if writing else [descriptor],
                                      [descriptor] if writing else [], [], min(remaining, .05))
            except InterruptedError:
                continue
            if ready[1 if writing else 0]:
                return
            # Resample the shared absolute clock even after suspension or a quiet pipe.

    def _write(self, raw):
        offset = 0
        while offset < len(raw):
            self._wait(self.command_fd, writing=True)
            try:
                count = os.write(self.command_fd, raw[offset:])
            except (InterruptedError, BlockingIOError):
                continue
            if count <= 0:
                raise AuthorityLost('authority pipe write made no progress')
            offset += count

    def _read(self, count):
        raw = bytearray()
        while len(raw) < count:
            self._wait(self.reply_fd, writing=False)
            try:
                chunk = os.read(self.reply_fd, count - len(raw))
            except (InterruptedError, BlockingIOError):
                continue
            if not chunk:
                raise AuthorityLost('authority pipe closed during exchange')
            raw.extend(chunk)
        return bytes(raw)

    def receive(self):
        if self.failed or self.closed:
            raise AuthorityLost('authority channel is no longer usable')
        try:
            size = struct.unpack('!I', self._read(4))[0]
            if not 0 < size <= MAX_FRAME_BYTES:
                raise AuthorityLost('invalid authority frame size')
            return decode_record(self._read(size))
        except (AuthorityLost, OSError, ValueError) as error:
            self.failed = True
            if isinstance(error, AuthorityLost):
                raise
            raise AuthorityLost('authority exchange could not be completed') from error

    def exchange(self, request, *, verify):
        if self.failed or self.closed or self.pending:
            raise AuthorityLost('authority channel cannot start another request')
        self.pending = True
        try:
            self._write(encode_record(request))
            reply = self.receive()
            # Fixed versioned client owns this verifier; a raw reply never grants permission.
            result = verify(reply)
            self.pending = False
            return result
        except OSError as error:
            self.failed = True
            self.pending = False
            raise AuthorityLost('authority exchange could not be completed') from error
        except BaseException:
            self.failed = True
            self.pending = False
            raise

    def close(self):
        if not self.closed:
            self.closed = True
            for descriptor in (self.command_fd, self.reply_fd):
                try:
                    os.close(descriptor)
                except OSError:
                    pass  # Best-effort local close is never child cleanup evidence.


def _fields(value, expected):
    if type(value) is not dict or set(value) != set(expected):
        raise AuthorityLost('authority record has unexpected fields')


def _integer(value, maximum=65536):
    if type(value) is not int or not 0 <= value <= maximum:
        raise AuthorityLost('authority record has invalid counter')


def _digest(value):
    if value is not None and (type(value) is not str or len(value) != 64
                              or any(c not in '0123456789abcdef' for c in value)):
        raise AuthorityLost('authority record has invalid digest')


def _identity(value):
    _fields(value, ('pid', 'boot', 'started'))
    _integer(value['pid'], 2**31 - 1)
    if (value['pid'] == 0 or type(value['boot']) is not str or not value['boot']
            or len(value['boot']) > 128 or type(value['started']) is not str
            or not value['started'].isascii() or not value['started'].isdecimal()
            or len(value['started']) > 20 or int(value['started']) == 0):
        raise AuthorityLost('authority process identity is invalid')


def scheduler_request(game, wanted, *, verify=False, max_heavy_commands=None, fail_fast=False, rebuild_reason=None):
    """Original ordinary selection/options, never an alternate target or scheduling policy.

    The existing build entry performs its option checks first and explicitly refuses options
    not implemented by the reviewed issuer before invoking this transport. Empty wanted is
    the actual default selection, not a synthetic task. The host binds these exact bytes.
    """
    record = {'version': 2, 'game': game, 'wanted': list(wanted),
              'options': {'verify': verify, 'max_heavy_commands': max_heavy_commands,
                          'fail_fast': fail_fast}}
    if rebuild_reason is not None:
        record['options']['rebuild_reason'] = [rebuild_reason] if isinstance(rebuild_reason, str) else list(rebuild_reason)
    return validate_scheduler_request(record)


def validate_scheduler_request(record):
    _fields(record, ('version', 'game', 'wanted', 'options'))
    if (type(record['version']) is not int or record['version'] != 2
            or type(record['game']) is not str or not record['game']
            or len(record['game']) > 128
            or any(c not in 'abcdefghijklmnopqrstuvwxyz0123456789_-' for c in record['game'])
            or type(record['wanted']) is not list or len(record['wanted']) > 64
            or any(type(name) is not str or not name or len(name) > 256 or '\0' in name
                   for name in record['wanted'])):
        raise AuthorityLost('unsupported original scheduler selection')
    options = record['options']
    expected = ('verify', 'max_heavy_commands', 'fail_fast')
    if type(options) is dict and 'rebuild_reason' in options:
        expected += ('rebuild_reason',)
    _fields(options, expected)
    reasons = options.get('rebuild_reason', [])
    if (type(reasons) is not list or len(reasons) > 64
            or any(type(value) is not str or not value or len(value) > 1024
                   or any(ord(c) < 32 for c in value) for value in reasons)):
        raise AuthorityLost('unsupported original rebuild reason record')
    if type(options['verify']) is not bool or type(options['fail_fast']) is not bool:
        raise AuthorityLost('unsupported original scheduler options')
    maximum = options['max_heavy_commands']
    if maximum is not None and (type(maximum) is not int or not 1 <= maximum <= 2**31 - 1):
        raise AuthorityLost('unsupported original scheduler work budget')
    return {'version': 2, 'game': record['game'], 'wanted': list(record['wanted']),
            'options': dict(options)}


class LegacyClient:
    """@cc [owner:fontanierh,label:correctness;safety] legacy-authority-reply-correlation
    A versioned ACK MUST match the original host's nonce, persistent selection, sequence and
    requested operation's permission before client state advances. Pure Observe MUST preserve
    record/frame/count; malformed, refused, stale or ambiguous replies MUST permanently fail
    the original channel. Finish MUST be terminal. The fixed issuer MUST call operations only
    at reviewed boundaries; this transport MUST NOT qualify arbitrary Call semantics or turn
    raw FD/record metadata into a guard. See test_build_v2_legacy_client.py.
    """
    PERMISSIONS = {'observe': 'observed', 'prepare_selection': 'prepared', 'advance': 'frame',
                   'begin_attempt': 'mutation', 'settle': 'settled', 'requeue': 'requeued',
                   'guard_returned': 'guard_observed', 'supersede': 'superseded', 'finish': 'finished'}

    @classmethod
    def handshake(cls, channel, hello, *, expected_host, deadline_ns, work_deadline_ns):
        _identity(expected_host)
        if (type(deadline_ns) is not int or type(work_deadline_ns) is not int
                or not 0 < work_deadline_ns < deadline_ns
                or channel.deadline_ns != work_deadline_ns):
            raise AuthorityLost('authority channel has a different work cutoff')
        def ready(value):
            _fields(value, ('version', 'type', 'nonce', 'host', 'deadline_ns', 'work_deadline_ns', 'clock_domain', 'selection',
                            'record_digest', 'frame', 'transition_count'))
            _identity(value['host'])
            if (type(value['version']) is not int or value['version'] != 2
                    or value['type'] != 'ready' or value['nonce'] != hello['nonce']
                    or value['host'] != expected_host
                    or value['clock_domain'] != CLOCK_ID
                    or type(value['deadline_ns']) is not int
                    or value['deadline_ns'] != deadline_ns
                    or type(value['work_deadline_ns']) is not int
                    or value['work_deadline_ns'] != work_deadline_ns
                    or type(value['selection']) is not str or not 0 < len(value['selection']) <= 128):
                raise AuthorityLost('authority startup identity differs')
            _digest(value['record_digest'])
            _integer(value['transition_count'])
            if value['frame'] is not None:
                _integer(value['frame'])
            return value
        observation = channel.exchange(hello, verify=ready)
        result = cls()
        result.channel = channel
        result.nonce = hello['nonce']
        result.selection = observation['selection']
        result.record_digest = observation['record_digest']
        result.frame = observation['frame']
        result.transition_count = observation['transition_count']
        result.sequence = 1
        result.finished = False
        return result

    def request(self, operation):
        if (self.finished or type(operation) is not dict or type(operation.get('type')) is not str
                or operation['type'] not in self.PERMISSIONS):
            raise AuthorityLost('authority operation is unavailable')
        kind = operation['type']
        envelope = {'version': 2, 'nonce': self.nonce, 'selection': self.selection,
                    'sequence': self.sequence, 'frame': self.frame,
                    'previous_digest': self.record_digest, 'operation': operation}

        def checked(value):
            _fields(value, ('version', 'type', 'nonce', 'selection', 'sequence',
                            'record_digest', 'frame', 'transition_count', 'permission', 'record_page'))
            if (type(value['version']) is not int or value['version'] != 2
                    or value['nonce'] != self.nonce or value['selection'] != self.selection
                    or type(value['sequence']) is not int or value['sequence'] != self.sequence):
                raise AuthorityLost('authority reply correlation differs')
            _digest(value['record_digest'])
            _integer(value['transition_count'])
            if value['frame'] is not None:
                _integer(value['frame'])
            if value['type'] == 'refused' and value['permission'] == 'none':
                raise AuthorityRefused('original authority refused the operation')
            if (value['type'] != 'ack' or value['permission'] != self.PERMISSIONS[kind]
                    or value['transition_count'] < self.transition_count):
                raise AuthorityLost('authority reply cannot grant the requested operation')
            page = value['record_page']
            if kind != 'observe' and page is not None:
                raise AuthorityLost('unexpected authority record page')
            if kind == 'observe':
                if (value['record_digest'] != self.record_digest or value['frame'] != self.frame
                        or value['transition_count'] != self.transition_count):
                    raise AuthorityLost('pure observation changed authority state')
                offset = operation.get('record_offset')
                if offset is None:
                    if page is not None:
                        raise AuthorityLost('unexpected authority record page')
                else:
                    _fields(page, ('offset', 'next', 'total', 'hex'))
                    for field in ('offset', 'next', 'total'):
                        _integer(page[field], MAX_RECORD_BYTES)
                    if (page['offset'] != offset or not offset <= page['next'] <= page['total']
                            or (page['next'] == offset and offset < page['total'])
                            or page['next'] - offset > 16384 or type(page['hex']) is not str
                            or len(page['hex']) != 2 * (page['next'] - offset)
                            or any(c not in '0123456789abcdef' for c in page['hex'])):
                        raise AuthorityLost('authority record page differs')
            return value

        reply = self.channel.exchange(envelope, verify=checked)
        self.record_digest = reply['record_digest']
        self.frame = reply['frame']
        self.transition_count = reply['transition_count']
        self.sequence += 1
        self.finished = kind == 'finish'
        return reply
