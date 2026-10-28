"""Bounded production broker messages and affirmative, pinned kernel exit evidence.

The retained roster is not a claim that process discovery covers an arbitrary native tree.
No function in this module signals a process or treats a failed lookup as proof of exit.
"""
import array
from dataclasses import dataclass
import json
import math
import os
from pathlib import Path
import select
import socket
import stat
import struct
import subprocess
import sys
import time
import uuid

from atelier.harness.capacity import Resources

NAMESPACE = 'atelier.capacity-broker.v1'
MAX_FRAME = 65536
MAX_ROSTER = 512
MAX_RETAINED = 8192  # Cumulative identities, independent of live-report and RPC batch limits.
RESOURCE_FIELDS = frozenset(Resources.__dataclass_fields__)
_ACTION_NAMES = frozenset(('status', 'reconcile', 'abandon-interrupted', 'abandon-completed', 'abandon-unwitnessed', 'owned', 'offer', 'gate', 'start', 'check', 'replace', 'close'))


def action_name(message):
    """Diagnostic label only: never echo an unknown action or request contents."""
    value = message.get('action') if type(message) is dict else None
    return value if type(value) is str and value in _ACTION_NAMES else 'invalid'


class CapacityError(RuntimeError):
    """A broker refusal; admission never falls back to a local grant."""


def fields(value, required, optional=()):
    if type(value) is not dict or not set(required) <= value.keys() or value.keys() - set(required) - set(optional):
        raise CapacityError('Invalid capacity protocol fields')
    return value


def integer(value, *, minimum=0, maximum=2**63-1):
    if type(value) is not int or not minimum <= value <= maximum:
        raise CapacityError('Invalid capacity integer')
    return value


def identity(value):
    if type(value) not in (list, tuple) or len(value) != 2:
        raise CapacityError('A pinned process identity is required')
    return (integer(value[0], minimum=1), integer(value[1], minimum=1))


def resources(value):
    fields(value, RESOURCE_FIELDS)
    try:
        return Resources(**{key: integer(item) for key, item in value.items()})
    except ValueError:
        raise CapacityError('Invalid capacity resource vector') from None


def text(value, *, maximum=256):
    if type(value) is not str or not value or len(value) > maximum or any(ord(c) < 32 for c in value):
        raise CapacityError('Invalid capacity name')
    return value


def encode(value):
    data = json.dumps(value, separators=(',', ':'), allow_nan=False).encode() + b'\n'
    if len(data) > MAX_FRAME:
        raise CapacityError('Capacity message exceeds its limit')
    return data


def decode(data):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise CapacityError('Duplicate capacity protocol field')
            result[key] = value
        return result
    try:
        if len(data) > MAX_FRAME:
            raise CapacityError('Capacity message exceeds its limit')
        value = json.loads(data, object_pairs_hook=unique,
                           parse_constant=lambda _: (_ for _ in ()).throw(CapacityError('Nonfinite protocol number')))
        pending = [(value, 0)]
        while pending:
            item, depth = pending.pop()
            if depth > 12:
                raise CapacityError('Capacity message exceeds its depth limit')
            if type(item) is dict:
                pending.extend((v, depth + 1) for v in item.values())
            elif type(item) is list:
                pending.extend((v, depth + 1) for v in item)
        return fields(value, (), value.keys())
    except (ValueError, TypeError, RecursionError, AttributeError):
        raise CapacityError('Invalid capacity message') from None


def receive(channel, *, descriptor=False, deadline=None):
    """One bounded newline frame; any received descriptors are closed unless exactly expected."""
    data, received = bytearray(), []
    deadline = deadline if deadline is not None else time.monotonic() + (channel.gettimeout() or 2.)
    try:
        while b'\n' not in data:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise CapacityError('Capacity receive deadline exceeded')
            channel.settimeout(remaining)
            chunk, ancillary, flags, _ = channel.recvmsg(MAX_FRAME + 1 - len(data), socket.CMSG_SPACE(4 * 4))
            for level, kind, raw in ancillary:
                if level == socket.SOL_SOCKET and kind == socket.SCM_RIGHTS:
                    values = array.array('i')
                    values.frombytes(raw[:len(raw) - len(raw) % values.itemsize])
                    received.extend(values)
            if flags & (socket.MSG_TRUNC | socket.MSG_CTRUNC) or not chunk or len(data) + len(chunk) > MAX_FRAME:
                raise CapacityError('Incomplete or oversized capacity message')
            data.extend(chunk)
        if data.count(b'\n') != 1 or not data.endswith(b'\n'):
            raise CapacityError('Unexpected capacity message or descriptor')
        value = decode(bytes(data[:-1]))
        expected = int(descriptor and value.get('ok') is not False)
        if len(received) != expected:
            raise CapacityError('Unexpected capacity message or descriptor')
        fd = received.pop() if expected else None
        if fd is not None:
            os.set_inheritable(fd, False)
        return value, fd
    finally:
        for fd in received:
            os.close(fd)


def send(channel, value, fd=None, *, deadline=None):
    data = encode(value)
    deadline = deadline if deadline is not None else time.monotonic() + (channel.gettimeout() or 2.)
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise CapacityError('Capacity send deadline exceeded')
    channel.settimeout(remaining)
    ancillary = [(socket.SOL_SOCKET, socket.SCM_RIGHTS, array.array('i', [fd]))] if fd is not None else []
    sent = channel.sendmsg([data], ancillary)
    while sent < len(data):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise CapacityError('Capacity send deadline exceeded')
        channel.settimeout(remaining)
        amount = channel.send(data[sent:])
        if not amount:
            raise CapacityError('Capacity peer stopped receiving')
        sent += amount


def process_start(pid):
    integer(pid, minimum=1)
    if sys.platform == 'darwin':
        from atelier.harness.safety.memory_guard import usage
        return integer(int(usage(pid).started), minimum=1)
    if sys.platform.startswith('linux'):
        raw = Path(f'/proc/{pid}/stat').read_bytes()
        if len(raw) > 4096:
            raise CapacityError('Oversized process identity')
        return integer(int(raw[raw.rindex(b')') + 2:].split()[19]), minimum=1)
    raise CapacityError('Pinned process identities are unsupported on this platform')


def direct_child(parent, child):
    """A positive parent edge, never a process-table completeness observation."""
    parent, child = identity(parent), identity(child)
    try:
        if not live(parent) or not live(child):
            return False
        if sys.platform == 'darwin':
            from atelier.harness.safety.memory_guard import owned_children
            return child in owned_children(*parent)
        raw = Path(f'/proc/{child[0]}/stat').read_bytes()
        ppid = int(raw[raw.rindex(b')') + 2:].split()[1])
        return ppid == parent[0] and process_start(parent[0]) == parent[1] and process_start(child[0]) == child[1]
    except (OSError, ValueError, CapacityError):
        return False


def peer(channel):
    if sys.platform == 'darwin':
        import ctypes
        libc = ctypes.CDLL(None, use_errno=True)
        uid, gid = ctypes.c_uint(), ctypes.c_uint()
        if libc.getpeereid(channel.fileno(), ctypes.byref(uid), ctypes.byref(gid)) != 0:
            raise CapacityError('Cannot authenticate capacity peer')
        uid = uid.value
        pid = struct.unpack('i', channel.getsockopt(0, 2, 4))[0]  # LOCAL_PEERPID
    else:
        pid, uid, _ = struct.unpack('3i', channel.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))
    if uid != os.getuid():
        raise CapacityError('Capacity peer belongs to another user')
    return (pid, process_start(pid))


def live(pin):
    """A matching birth identity alone does not exclude a positively exited zombie."""
    pin = identity(pin)
    try:
        if sys.platform == 'darwin':
            from atelier.harness.safety.memory_guard import usage
            sample = usage(pin[0])
            return sample.started == pin[1] and not sample.exited
        raw = Path(f'/proc/{pin[0]}/stat').read_bytes()
        values = raw[raw.rindex(b')') + 2:].split()
        return int(values[19]) == pin[1] and values[0] not in (b'Z', b'X')
    except (OSError, ValueError):
        return False


def parent_pin(pin):
    """Read one positive edge while the child's exact identity stays stable."""
    pin = identity(pin)
    try:
        if not live(pin):
            return None
        if sys.platform == 'darwin':
            import ctypes
            from atelier.harness.safety.memory_guard import LIB
            LIB.proc_pidinfo.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_uint64, ctypes.c_void_p, ctypes.c_int]
            buffer = ctypes.create_string_buffer(1024)
            # proc_bsdinfo's first five uint32 fields end with pbi_ppid (SDK proc_info.h).
            size = LIB.proc_pidinfo(pin[0], 3, 0, buffer, len(buffer))
            if size < 20:
                return None
            ppid = struct.unpack_from('5I', buffer.raw)[4]
        else:
            raw = Path(f'/proc/{pin[0]}/stat').read_bytes()
            ppid = int(raw[raw.rindex(b')') + 2:].split()[1])
        parent = (ppid, process_start(ppid))
        return parent if live(pin) and live(parent) else None
    except (OSError, ValueError, CapacityError):
        return None


def boot_id():
    """An OS boot UUID is independent of daemon epoch and cannot survive a reboot."""
    try:
        if sys.platform == 'darwin':
            raw = subprocess.check_output(['/usr/sbin/sysctl', '-n', 'kern.bootsessionuuid'], timeout=.5).decode().strip()
        else:
            raw = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
        return str(uuid.UUID(raw))
    except (OSError, ValueError, subprocess.SubprocessError):
        raise CapacityError('Authoritative OS boot identity unavailable') from None


class ExitWatch:
    """@cc [owner:fontanierh,label:safety] pinned-kernel-exit-witness
    An exit event MUST come from a kernel watch bound while both start-identity checks matched.
    Missing processes, failed registration and PID reuse MUST remain unknown, never exited.
    A positive event MUST remain cached after promptly closing its kernel descriptor.
    This watch proves only the retained identity's exit, not undiscovered descendants' exit.
    """
    def __init__(self, pin, *, started=process_start):
        self.pin, self.handle, self.exited = identity(pin), None, False
        try:
            if started(self.pin[0]) != self.pin[1]:
                return
            if sys.platform == 'darwin':
                self.handle = select.kqueue()
                event = select.kevent(self.pin[0], filter=select.KQ_FILTER_PROC,
                                     flags=select.KQ_EV_ADD | select.KQ_EV_ONESHOT, fflags=select.KQ_NOTE_EXIT)
                self.handle.control([event], 0, 0)
            elif hasattr(os, 'pidfd_open'):
                self.handle = os.pidfd_open(self.pin[0], 0)
            if self.handle is not None and started(self.pin[0]) != self.pin[1]:
                self.close()
        except (OSError, ValueError, CapacityError):
            self.close()

    def poll(self):
        if self.handle is not None and not self.exited:
            if sys.platform == 'darwin':
                self.exited = any(event.ident == self.pin[0] and event.fflags & select.KQ_NOTE_EXIT
                                  and not event.flags & select.KQ_EV_ERROR
                                  for event in self.handle.control(None, 1, 0))
            else:
                self.exited = bool(select.select([self.handle], [], [], 0)[0])
            if self.exited:
                self.close()  # The cached positive event remains; departed helpers need no kernel descriptor.
        return self.exited

    def close(self):
        if self.handle is not None:
            self.handle.close() if sys.platform == 'darwin' else os.close(self.handle)
            self.handle = None


class _ReplacedReport(CapacityError):
    """An opened report was unlinked by its publisher's atomic replacement."""


def private_file(path, *, limit, private=True):
    return _read_file(path, limit=limit, private=private)


def _read_file(path, *, limit, private, guard_report=False):
    path = Path(path)
    for ancestor in (path, *path.parents):
        if ancestor.is_symlink() and str(ancestor) not in ('/tmp', '/var', '/etc'):
            raise CapacityError('Capacity paths cannot contain symlinks')
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        info = os.fstat(fd)
        mask = 0o077 if private else 0o022
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
                or info.st_mode & mask or info.st_size > limit):
            raise CapacityError('Capacity file must be bounded, owned and regular')
        def replaced(sample):
            if not guard_report or sample.st_nlink != 0:
                return False
            current = path.lstat()
            return (current.st_dev, current.st_ino) != (sample.st_dev, sample.st_ino)
        if info.st_nlink != 1:
            if replaced(info):
                raise _ReplacedReport('Capacity guard report replaced while reading')
            raise CapacityError('Capacity file must be bounded, owned and regular')
        data = os.read(fd, limit + 1)
        after = os.fstat(fd)
        if len(data) != info.st_size or (info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns) != (
                after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns):
            if replaced(after):
                raise _ReplacedReport('Capacity guard report replaced while reading')
            raise CapacityError('Capacity file changed while reading')
        return data
    finally:
        os.close(fd)


def guard_report(path):
    """@cc [owner:fontanierh,label:safety] bounded-guard-report-replacement
    Only an unlinked opened report with a different current path identity MAY be retried,
    at most three fresh reads. Every read MUST retain ownership, mode, type and size checks;
    callers MUST still validate freshness, monitor identity and the decoded receipt.
    Private token and configuration reads MUST NOT retry replacement races.
    """
    for attempt in range(3):
        try:
            return _read_file(path, limit=MAX_FRAME, private=False, guard_report=True)
        except _ReplacedReport:
            if attempt == 2:
                raise CapacityError('Capacity guard report repeatedly replaced while reading') from None


@dataclass(frozen=True)
class GuardFacts:
    roster: tuple
    footprint_bytes: int


def validate_guards(guards, child, owner, limit_bytes, reserved_mib, *, started=process_start,
                    child_of=direct_child, alive=live):
    integer(limit_bytes, minimum=1)
    if limit_bytes > reserved_mib * 1024**2:
        raise CapacityError('Guard ceiling exceeds the reserved memory envelope')
    roster, footprint = [], 0
    for kind in ('process_guard', 'tree_guard'):
        item = fields(guards[kind], ('pid', 'start', 'report'))
        monitor = identity((item['pid'], item['start']))
        if started(monitor[0]) != monitor[1] or not alive(monitor) or not child_of(owner, monitor):
            raise CapacityError('Capacity guard identity is not live and owned')
        record = decode(guard_report(text(item['report'], maximum=4096)))
        observed = record.get('observed_monotonic') if kind == 'tree_guard' else record.get('time')
        now = time.monotonic() if kind == 'tree_guard' else time.time()
        if (type(observed) not in (int, float) or not math.isfinite(observed) or not 0 <= now - observed <= 3
                or record.get('state') != 'running' or record.get('limit_bytes') != limit_bytes):
            raise CapacityError('Capacity guard receipt is stale or mismatched')
        keys = ('owner', 'owner_started') if kind == 'tree_guard' else ('pid', 'process_start')
        if identity([record.get(key) for key in keys]) != child:
            raise CapacityError('Capacity guard receipt belongs to another child')
        if kind == 'tree_guard':
            values = record.get('processes')
            if type(values) is not list or len(values) > MAX_ROSTER:
                raise CapacityError('Invalid retained guard roster')
            for value in values:
                if type(value) is not dict or 'pid' not in value or 'started' not in value:
                    raise CapacityError('Invalid retained guard process identity')
                roster.append(identity([value['pid'], value['started']]))
            footprint = integer(record.get('footprint_bytes'))
        if started(monitor[0]) != monitor[1] or not alive(monitor):
            raise CapacityError('Capacity guard identity changed during validation')
    return GuardFacts(tuple(roster), footprint)



def require_independent_guards(guards, owner, *, started=process_start, group=None):
    """@cc [owner:fontanierh,label:safety] independent-controller-loss-supervision
    Before full-mode GO, both guards MUST own process groups separate from the controller,
    retain their exact birth identities, and the aggregate receipt MUST bind this controller.
    Old clients lacking this protection MUST refuse before useful execution.
    """
    group = group or os.getpgid
    owner = identity(owner)
    for kind in ('process_guard', 'tree_guard'):
        item = fields(guards[kind], ('pid','start','report'))
        pin = identity((item['pid'],item['start']))
        if (started(pin[0]) != pin[1] or group(pin[0]) != pin[0] or group(owner[0]) == group(pin[0])
                or started(pin[0]) != pin[1]):
            raise CapacityError('Capacity guards require independent supervision; update the launching checkout')
    receipt = decode(guard_report(guards['tree_guard']['report']))
    if receipt.get('controller') != list(owner):
        raise CapacityError('Capacity aggregate guard requires controller-loss supervision; update the launching checkout')

def pressure(_disk_pool):
    """Fresh memory availability is separate from ownership. Disk is not an admission input."""
    memory = None
    try:
        if sys.platform == 'darwin':
            from atelier.harness.safety.render_lock import parse_vm_stat
            result = subprocess.run(['/usr/bin/vm_stat'], capture_output=True, text=True, timeout=.5)
            memory = parse_vm_stat(result.stdout) if result.returncode == 0 else None
        else:
            for line in Path('/proc/meminfo').read_text().splitlines():
                if line.startswith('MemAvailable:'):
                    memory = int(line.split()[1]) * 1024
    except (OSError, ValueError, subprocess.SubprocessError):
        return None
    return {'observed_monotonic': time.monotonic(),
            'available_memory_mib': memory // 1024**2} if memory is not None else None
