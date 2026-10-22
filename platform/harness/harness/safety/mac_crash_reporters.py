"""Read-only kernel evidence for late Unreal crash reporters on macOS.

No process is signalled here. The aggregate guard may adopt only a completely
proved process and then use its existing pinned-tree termination lifecycle.
"""
import ctypes
import errno
import hmac
import os
from pathlib import PurePosixPath
import re
import struct

from .launch_ownership import ENVIRONMENT_KEY, LINEAGE_KEY, marker_tokens

MAX_ARGUMENT_BYTES = 2 * 1024**2
MAX_PROCESSES = 65536
CRASH_DIRECTORY = re.compile(r'(?:CrashReport|EnsureReport)-UE-.+-pid-([1-9][0-9]*)-([0-9a-fA-F]{32})')


def arguments_and_marker(data, nonce):
    """Return argv and True/False/unknown ownership, never raw environment.

    XNU can redact a restricted executable's environment. Absence, malformed
    values and duplicates are unknown; only a complete different marker is foreign.
    """
    if not isinstance(data, bytes) or not 5 <= len(data) <= MAX_ARGUMENT_BYTES:
        raise ValueError('Invalid process argument bounds')
    argc = struct.unpack_from('=i', data)[0]
    if not 1 <= argc <= 4096:
        raise ValueError('Invalid process argument count')
    end = data.find(b'\0', 4)
    if end <= 4:
        raise ValueError('Missing kernel executable prefix')
    offset = end + 1
    while offset < len(data) and data[offset] == 0:
        offset += 1
    argv = []
    for _ in range(argc):
        end = data.find(b'\0', offset)
        if end < offset:
            raise ValueError('Truncated process arguments')
        argv.append(os.fsdecode(data[offset:end]))
        offset = end + 1
    fields = {key.encode() + b'=': [] for key in (ENVIRONMENT_KEY, LINEAGE_KEY)}
    for item in data[offset:].split(b'\0'):
        for prefix, found in fields.items():
            if item.startswith(prefix):
                found.append(item[len(prefix):])
    marker = None
    if all(len(found) == 1 for found in fields.values()):
        try:
            current, lineage = (found[0].decode('ascii') for found in fields.values())
            values = marker_tokens(current, lineage)
            marker = any(hmac.compare_digest(value, nonce) for value in values)
        except (UnicodeDecodeError, ValueError):
            pass
    return tuple(argv), marker


def reporter_for_native(executable):
    """Derive the two installed editor CRC layouts from a kernel UnrealEditor path.

    WITH_EDITOR selects CrashReportClientEditor even for UnrealEditor-Cmd.
    GenerateApplicationPath supports the app executable and its flat fallback;
    actual kernel executable identity must match one of these exact siblings.
    """
    if not isinstance(executable, str):
        return None
    path = PurePosixPath(executable)
    if not path.is_absolute() or '..' in path.parts or str(path) != executable:
        return None
    for name in ('UnrealEditor', 'UnrealEditor-Cmd'):
        if tuple(path.parts[-4:]) == (name + '.app', 'Contents', 'MacOS', name):
            directory = path.parents[3]
            break
        if path.name == name:
            directory = path.parent
            break
    else:
        return None
    if tuple(directory.parts[-3:]) != ('Engine', 'Binaries', 'Mac'):
        return None
    return frozenset(str(directory / suffix) for suffix in (
        'CrashReportClientEditor.app/Contents/MacOS/CrashReportClientEditor',
        'CrashReportClientEditor'))


def crash_parent(argv):
    """The installed UE puts its exact native PID/run UUID in the first argument."""
    if len(argv) < 2 or argv[0] != 'CrashReportClient':
        return None
    directory = PurePosixPath(argv[1])
    if not directory.is_absolute() or '..' in directory.parts:
        return None
    match = CRASH_DIRECTORY.fullmatch(directory.name)
    return int(match[1]) if match else None


class KernelProbe:
    """Bounded libproc/sysctl reads. Failed reads remain unknown, never positive ownership."""
    def __init__(self):
        from . import process_tree
        self.tree = process_tree
        self.lib = ctypes.CDLL('/usr/lib/libproc.dylib', use_errno=True)
        self.lib.proc_listpids.argtypes = [ctypes.c_uint32, ctypes.c_uint32, ctypes.c_void_p, ctypes.c_int]
        self.lib.proc_listpids.restype = ctypes.c_int
        self.lib.proc_pidpath.argtypes = [ctypes.c_int, ctypes.c_void_p, ctypes.c_uint32]
        self.lib.proc_pidpath.restype = ctypes.c_int
        self.system = ctypes.CDLL('/usr/lib/libSystem.B.dylib', use_errno=True)
        self.system.sysctl.argtypes = [ctypes.POINTER(ctypes.c_int), ctypes.c_uint, ctypes.c_void_p,
                                      ctypes.POINTER(ctypes.c_size_t), ctypes.c_void_p, ctypes.c_size_t]
        self.system.sysctl.restype = ctypes.c_int
        self.system.mach_absolute_time.argtypes = []
        self.system.mach_absolute_time.restype = ctypes.c_uint64

    def live_start(self, pid):
        try:
            value = self.tree.usage(pid)
            return None if value.exited else value.started
        except ProcessLookupError as error:
            if error.errno in (errno.ESRCH, errno.ENOENT):
                return None
            raise OSError('Cannot bind process start identity') from None

    def now(self):
        return self.system.mach_absolute_time()

    def pids(self):
        width = ctypes.sizeof(ctypes.c_int)
        # UE's reporter inherits the native launch UID. Other users' inaccessible
        # system daemons are not possible descendants and cannot obscure cleanup.
        kind, user = 4, os.geteuid()  # PROC_UID_ONLY (installed sys/proc_info.h)
        count = self.lib.proc_listpids(kind, user, None, 0)
        if not 0 < count <= MAX_PROCESSES * width:
            raise OSError('Cannot bound the process roster')
        buffer = (ctypes.c_int * min(MAX_PROCESSES, count // width + 128))()
        count = self.lib.proc_listpids(kind, user, buffer, ctypes.sizeof(buffer))
        if count <= 0 or count >= ctypes.sizeof(buffer) or count % width:
            raise OSError('Incomplete process roster')
        return tuple(pid for pid in buffer[:count // width] if pid > 0)

    def executable(self, pid):
        buffer = ctypes.create_string_buffer(4096)
        size = self.lib.proc_pidpath(pid, buffer, ctypes.sizeof(buffer))
        if not 0 < size < ctypes.sizeof(buffer):
            raise OSError('Cannot read process executable')
        return os.fsdecode(buffer.value)

    def name(self, pid):
        return self.tree.name(pid)

    def arguments(self, pid, nonce):
        mib = (ctypes.c_int * 3)(1, 49, pid)  # CTL_KERN, KERN_PROCARGS2
        size = ctypes.c_size_t()
        if self.system.sysctl(mib, 3, None, ctypes.byref(size), None, 0):
            raise OSError('Cannot size process arguments')
        if not 5 <= size.value <= MAX_ARGUMENT_BYTES:
            raise OSError('Invalid process argument size')
        buffer = ctypes.create_string_buffer(size.value)
        if self.system.sysctl(mib, 3, buffer, ctypes.byref(size), None, 0):
            raise OSError('Cannot read process arguments')
        return arguments_and_marker(buffer.raw[:size.value], nonce)


class Reporters:
    """@cc [owner:fontanierh,label:safety] late-crash-reporter-ownership
    Late reporter adoption MUST require the private launch marker in a strict current/
    ancestor context, the launch user's kernel process roster, an exact installed
    kernel executable, a previously pinned native PID/start and exact native crash
    argument, with repeated reporter start/executable checks. Names are discovery hints
    only. Unresolved possibly-owned reporters MUST NOT be signalled or certified empty.
    The independent aggregate monitor MUST reconcile before and during terminal drain,
    including controller loss; caller cleanup alone is insufficient. No crash privacy,
    evidence-generation or shared-service policy MAY be disabled.
    """
    def __init__(self, nonce, api=None):
        if not isinstance(nonce, str) or not re.fullmatch('[0-9a-f]{64}', nonce):
            raise ValueError('Invalid private launch marker')
        self.nonce = nonce
        self.api = KernelProbe() if api is None else api
        self.natives = {}
        self.exited_before = {}
        self.adopted = {}
        self.unresolved = {}
        self.unpinned = set()
        self.scan_failed = False

    def bind_root(self, pid, start):
        """The monitor must bind the actual gated root before acknowledging readiness."""
        if self.api.live_start(pid) != start:
            raise ValueError('Launch root identity is unavailable')
        _, marker = self.api.arguments(pid, self.nonce)
        if marker is not True or self.api.live_start(pid) != start:
            raise ValueError('Private launch context does not match the gated root')

    def observe(self, tree, candidates=None):
        """Remember kernel native paths while ancestry is positively established."""
        changed = False
        excluded = tree.excluded()
        candidates = set(tree.parents) if candidates is None else set(candidates)
        for key in candidates | self.natives.keys():
            if key in excluded or key in self.adopted:
                continue
            try:
                current = self.api.live_start(key[0])
                if current == key[1]:
                    name = self.api.name(key[0])
                    if key not in self.natives and (not name or name.startswith('UnrealEditor')):
                        executable = self.api.executable(key[0])
                        reporter = reporter_for_native(executable)
                        if reporter is not None and self.api.live_start(key[0]) == key[1]:
                            self.natives[key] = reporter
                elif key in self.natives and key not in self.exited_before:
                    # rusage start and mach_absolute_time share Mach absolute ticks.
                    # A reused native PID gives a tighter upper bound than this poll.
                    self.exited_before[key] = min(self.api.now(), current) if current is not None else self.api.now()
                    changed = True
            except OSError:
                # Discovery cannot infer a new native identity from an unreadable process.
                # Already pinned native context remains available to terminal reconciliation.
                continue
        return changed

    def _proof(self, pid, start):
        """Return one complete proof; raise on uncertainty only after a possible own match."""
        if self.api.live_start(pid) != start:
            return None
        executable = self.api.executable(pid)
        argv, marker = self.api.arguments(pid, self.nonce)
        if self.api.executable(pid) != executable or self.api.live_start(pid) != start:
            return None
        if marker is False:
            return None
        native_pid = crash_parent(argv)
        matches = [key for key, expected in self.natives.items()
                   if key[0] == native_pid and key[1] <= start
                   and start <= self.exited_before.get(key, self.api.now())
                   and executable in expected]
        if marker is None:
            raise ValueError('Reporter launch context is unavailable or ambiguous')
        if len(matches) != 1:
            raise ValueError('Launch marker matches but native context is unresolved')
        native = matches[0]
        return dict(native=native, executable=executable, arguments=argv)

    def reconcile(self, tree):
        """Adopt complete proofs, retaining uncertainty until a fresh successful scan clears it."""
        pending = {}
        unpinned = set()
        try:
            roster = self.api.pids()
        except OSError:
            self.scan_failed = True
            return
        self.scan_failed = False
        for pid in roster:
            # A name only narrows kernel probes; it never grants ownership or a signal.
            try:
                name = self.api.name(pid)
            except OSError:
                name = ''  # Fall back to kernel executable identity, never absence.
            if name and not name.startswith('CrashReport'):
                continue
            start = None
            try:
                start = self.api.live_start(pid)
                if start is None:
                    continue
                if not name:
                    # proc_name failure is not proof of absence. The kernel executable
                    # can still identify a reporter; unreadable live candidates stay unknown.
                    executable = PurePosixPath(self.api.executable(pid))
                    if executable.name not in {'CrashReportClient', 'CrashReportClientEditor'}:
                        continue
                proof = self._proof(pid, start)
                if proof is None:
                    continue
                key = (pid, start)
                if key not in tree.parents:
                    parent = proof['native']
                    tree.parents[key] = parent
                    tree.depth[key] = tree.depth[parent] + 1
                self.adopted[key] = proof
            except (OSError, ValueError):
                # A new reporter in this native lifetime may be owned but unobservable.
                # Keep it unknown; do not turn failed environment/path reads into admission.
                if start is None:
                    # A failed first identity read is different from a positive gone
                    # result. Preserve uncertainty without inventing a signalable pin.
                    unpinned.add(pid)
                elif start >= tree.root[1]:
                    try:
                        if self.api.live_start(pid) == start:
                            pending[(pid, start)] = 'reporter_probe_incomplete'
                    except OSError:
                        pending[(pid, start)] = 'reporter_probe_incomplete'
        self.unresolved = pending
        self.unpinned = unpinned

    def signal_allowed(self, key):
        if key not in self.adopted:
            return True
        try:
            if self.api.live_start(key[0]) != key[1]:
                return False
            if self._proof(*key) == self.adopted[key] and self.api.live_start(key[0]) == key[1]:
                return True
            self.unresolved[key] = 'reporter_signal_proof_changed'
            return False
        except (OSError, ValueError):
            self.unresolved[key] = 'reporter_signal_proof_incomplete'
            return False

    def empty(self):
        return not self.scan_failed and not self.unresolved and not self.unpinned

    def evidence(self):
        """Numeric/context evidence only; never emit the marker or raw argv/environment."""
        return dict(adopted=[dict(pid=key[0], started=key[1], native=list(proof['native']))
                             for key, proof in sorted(self.adopted.items())],
                    unresolved=[dict(pid=key[0], started=key[1], reason=reason)
                                for key, reason in sorted(self.unresolved.items())],
                    unresolved_pids=sorted(self.unpinned),
                    scan_failed=self.scan_failed)
