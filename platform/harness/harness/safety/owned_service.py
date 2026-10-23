"""Invocation-private gated children; never adopt an already running service.

The capability is inherited only by an explicitly enabled guarded compound driver.
It is lifecycle authority within that invocation, not a sandbox against a malicious driver.
"""
import array
import json
import os
import select
import socket
import stat
import sys
import threading
import time
import uuid

from . import process_tree

ENV_FD = 'ATELIER_PRIVATE_SERVICE_FD'
ENV_TOKEN = 'ATELIER_PRIVATE_SERVICE_TOKEN'
TIMEOUT = 1.
GATE_TIMEOUT = 12.
REGISTRATION_TIMEOUT = 4.
MAX_MESSAGE = 4096
MAX_SERVICES = 16
_CLIENT_LOCK = threading.Lock()


class ChannelClosed(RuntimeError):
    pass


def channel():
    left, right = socket.socketpair()
    for endpoint in (left, right):
        endpoint.settimeout(TIMEOUT)
    return left, right


def remaining(deadline):
    duration = deadline - time.monotonic()
    if duration <= 0:
        raise TimeoutError('private service deadline expired')
    return duration


def frame_deadline(endpoint, deadline):
    duration = endpoint.gettimeout()
    bound = time.monotonic() + (TIMEOUT if duration is None else duration)
    return bound if deadline is None else min(bound, deadline)


def send(endpoint, value, descriptor=None, *, deadline=None):
    raw = json.dumps(value, separators=(',', ':')).encode()
    if len(raw) > MAX_MESSAGE:
        raise RuntimeError('private service message too large')
    packet = len(raw).to_bytes(4, 'big') + raw
    ancillary = [] if descriptor is None else [(socket.SOL_SOCKET, socket.SCM_RIGHTS, array.array('i', [descriptor]))]
    previous = endpoint.gettimeout()
    stop = frame_deadline(endpoint, deadline)
    try:
        endpoint.settimeout(remaining(stop))
        if endpoint.sendmsg([packet], ancillary) != len(packet):
            raise RuntimeError('partial private service message')
    finally:
        endpoint.settimeout(previous)


def receive(endpoint, *, descriptor=False, deadline=None):
    """@cc [owner:fontanierh,label:safety] complete-frame-deadline
    All header/body fragments and ancillary validation MUST share one absolute monotonic deadline,
    capped by the caller's remaining handshake budget. Partial progress MUST NOT renew it.
    Every received descriptor MUST be validated or closed on failure, including later fragments.
    """
    descriptors = []
    previous = endpoint.gettimeout()
    stop = frame_deadline(endpoint, deadline)

    def read(count):
        endpoint.settimeout(remaining(stop))
        chunk, ancillary, flags, _ = endpoint.recvmsg(
            count, socket.CMSG_SPACE(array.array('i').itemsize * 4), getattr(socket, 'MSG_CMSG_CLOEXEC', 0))
        unexpected = False
        for level, kind, data in ancillary:
            if level == socket.SOL_SOCKET and kind == socket.SCM_RIGHTS:
                values = array.array('i')
                values.frombytes(data[:len(data) - len(data) % values.itemsize])
                descriptors.extend(values)
                for fd in values:
                    os.set_inheritable(fd, False)
                if len(data) % values.itemsize:
                    unexpected = True
            else:
                unexpected = True
        if unexpected:
            raise RuntimeError('unexpected private service ancillary data')
        if flags & (socket.MSG_TRUNC | socket.MSG_CTRUNC):
            raise RuntimeError('truncated private service message')
        if len(descriptors) > int(descriptor):
            raise RuntimeError('invalid private service message/descriptor')
        if not chunk:
            raise ChannelClosed('lost private service channel')
        return chunk

    try:
        raw = read(4)
        while len(raw) < 4:
            raw += read(4-len(raw))
        size = int.from_bytes(raw, 'big')
        if not 0 < size <= MAX_MESSAGE:
            raise RuntimeError('invalid private service message size')
        raw = b''
        while len(raw) < size:
            raw += read(size-len(raw))
        def unique(pairs):
            value = {}
            for key, item in pairs:
                if key in value:
                    raise RuntimeError('duplicate private service message field')
                value[key] = item
            return value
        value = json.loads(raw, object_pairs_hook=unique)
        remaining(stop)
        if not isinstance(value, dict) or len(descriptors) != int(descriptor):
            raise RuntimeError('invalid private service message/descriptor')
        if descriptor:
            fd = descriptors.pop()
            try:
                if not stat.S_ISSOCK(os.fstat(fd).st_mode):
                    raise RuntimeError('private service gate descriptor is not a socket')
                with socket.socket(fileno=os.dup(fd)) as checked:
                    if checked.family != socket.AF_UNIX or checked.type != socket.SOCK_STREAM:
                        raise RuntimeError('private service gate requires a Unix stream socket')
                os.set_inheritable(fd, False)
                return value, fd
            except BaseException:
                os.close(fd)
                raise
        return value
    finally:
        endpoint.settimeout(previous)
        for fd in descriptors:
            os.close(fd)


def pending(endpoint):
    return bool(select.select([endpoint], [], [], 0)[0])


def identity(value):
    if (type(value) is not list or len(value) != 2
            or any(type(x) is not int or x <= 0 for x in value)):
        raise RuntimeError('invalid private service identity')
    return tuple(value)


def token(value):
    if type(value) is not str or len(value) != 32:
        raise RuntimeError('invalid private service correlation token')
    try:
        if uuid.UUID(value).hex != value:
            raise ValueError()
    except ValueError:
        raise RuntimeError('invalid private service correlation token') from None
    return value


def validate_request(value, invocation):
    if set(value) != {'identity', 'token', 'invocation'} or value['invocation'] != invocation:
        raise RuntimeError('invalid private service request binding')
    token(value['token'])
    return identity(value['identity'])


def unsupported(shared, parents, services):
    found = []
    for key in shared:
        ancestor, seen = parents.get(key), set()
        while ancestor is not None and ancestor not in seen:
            if services.includes(ancestor):
                found.append(key)
                break
            seen.add(ancestor)
            ancestor = parents.get(ancestor)
    return sorted(found)


class Controller:
    """@cc [owner:fontanierh,label:safety] registration-single-budget
    One registration MUST retain its original monotonic budget across descriptor adoption/release,
    actual-child readiness, independent acknowledgment and final ownership checks. No GO may follow
    expiration; each blocking frame MUST also keep its shorter health-loop budget.
    """
    def __init__(self):
        self.host, self.driver = channel()
        self.host.settimeout(.25)
        self.invocation = uuid.uuid4().hex
        self.seen = set()

    def close(self):
        self.host.close()
        self.driver.close()

    def poll(self, tree, aggregate, stack, duration, limit_gib):
        if not pending(self.host):
            return
        stop = time.monotonic() + REGISTRATION_TIMEOUT
        try:
            request, descriptor = receive(self.host, descriptor=True, deadline=stop)
        except ChannelClosed:
            # EOF can race a normal driver exit after the host's poll. A live
            # driver closing its capability remains a failed invocation.
            if tree is not None:
                try:
                    sample = process_tree.usage(tree.root[0])
                except ProcessLookupError:
                    return
                if sample.started != tree.root[1] or sample.exited:
                    return
            raise
        with socket.socket(fileno=descriptor) as gate:
            gate.settimeout(.25)
            key = validate_request(request, self.invocation)
            if request['token'] in self.seen or len(self.seen) >= MAX_SERVICES:
                raise RuntimeError('duplicate or excessive private service registration')
            self.seen.add(request['token'])
            if receive(gate, deadline=stop) != dict(gated=list(key), token=request['token']):
                raise RuntimeError('private service gate identity mismatch')
            # Keep the sender's socket open until its transferred descriptor is
            # installed here. In-flight Unix socket rights on macOS do not keep
            # the peer usable after the sender closes its last descriptor.
            send(self.host, dict(**request, adopted=True), deadline=stop)
            if receive(self.host, deadline=stop) != dict(**request, released=True):
                raise RuntimeError('private service gate transfer was not completed')
            tree.register_service(key)
            from .guard import attach, wait_ready
            report = tree.folder / f'memory-health-owned-service-{key[0]}.json'
            monitor = stack.enter_context(attach(key[0], report, duration=duration,
                                                 limit_gib=limit_gib, expected_start=key[1]))
            if monitor is None:
                raise RuntimeError('private service has no actual-child guard')
            tree.guarded[key] = ('owned-service', monitor)
            tree.service_reports[key] = report
            wait_ready(monitor, key[0], key[1], report, int(limit_gib * 1024**3), timeout=remaining(stop))
            aggregate.register_service(key, request['token'], deadline=stop)
            tree.check()
            tree.services.validate(key)
            remaining(stop)
            send(gate, dict(go=list(key), token=request['token']), deadline=stop)
            send(self.host, dict(**request, ready=True), deadline=stop)


class Registrations:
    """@cc [owner:fontanierh,label:safety] exact-owned-service-registration
    A private-service exception MUST bind a live exact direct child of the pinned driver
    before exec, never a shared-named process or a previously excluded identity. Reuse
    MUST NOT inherit the exception. Unregistered shared services remain excluded.
    """
    def __init__(self, api, root):
        self.api, self.root = api, root
        self._roots = set()

    def includes(self, key):
        return key in self._roots

    def register(self, key, shared):
        if (key in self._roots or key in shared or len(self._roots) >= MAX_SERVICES
                or self.api.name(key[0]) in {'zenserver', 'UnrealTraceServer'}):
            raise RuntimeError('private service is not a fresh gated owned child')
        self.validate(key)
        self._roots.add(key)

    def validate(self, key):
        if (self.api.started(self.root[0]) != self.root[1] or self.api.started(key[0]) != key[1]
                or self.api.usage(self.root[0]).exited or self.api.usage(key[0]).exited
                or key not in self.api.owned_children(*self.root)):
            raise RuntimeError('private service is not a fresh gated owned child')

    def evidence(self):
        return [list(key) for key in sorted(self._roots)]


def spawn(command, *, kind='job', cwd=None, stdout=None, stderr=None):
    """Spawn a direct service child, gated until both independent trackers acknowledge it.

    No detach, arbitrary PID registration, shell, environment override or descriptor inheritance
    option is exposed. Isolated Python startup prevents cwd/PYTHONPATH from replacing the gate.
    The caller must keep the service foreground and own its ordinary successful shutdown.
    Failed registration never releases exec; controller/aggregate cleanup remains authoritative.
    """
    from .process import spawn as launch
    from .guard import reap
    descriptor = os.environ.get(ENV_FD)
    if descriptor is None:
        raise RuntimeError('private services require an enabled guarded compound driver')
    os.set_inheritable(int(descriptor), False)
    argv = list(command)
    if not argv or isinstance(command, (str, bytes)):
        raise ValueError('private service requires a nonempty argv')
    with _CLIENT_LOCK, socket.socket(fileno=os.dup(int(descriptor))) as client:
        client.settimeout(GATE_TIMEOUT)
        stop = time.monotonic() + GATE_TIMEOUT
        host, gate = channel()
        child = None
        try:
            environment = dict(os.environ)
            environment.pop(ENV_FD, None)
            environment.pop(ENV_TOKEN, None)
            correlation = uuid.uuid4().hex
            child = launch([sys.executable, '-I', '-m', __name__, str(gate.fileno()), correlation, *argv], kind=kind,
                           cwd=cwd, env=environment, stdout=stdout, stderr=stderr,
                           stdin=-3, pass_fds=(gate.fileno(),))
            gate.close()
            key = [child.pid, process_tree.started(child.pid)]
            identity(key)
            invocation = token(os.environ.get(ENV_TOKEN))
            sent = dict(identity=key, token=correlation, invocation=invocation)
            send(client, sent, host.fileno(), deadline=stop)
            if receive(client, deadline=stop) != dict(**sent, adopted=True):
                raise RuntimeError('private service gate descriptor was not adopted')
            host.close()  # only the controller can now release the service gate
            send(client, dict(**sent, released=True), deadline=stop)
            answer = receive(client, deadline=stop)
            if answer != dict(**sent, ready=True):
                raise RuntimeError('private service registration was not acknowledged')
            return child
        except BaseException:
            if child is not None:
                reap(child, grace=0.)
            raise
        finally:
            host.close()
            gate.close()


def main():
    endpoint = socket.socket(fileno=int(sys.argv[1]))
    os.set_inheritable(endpoint.fileno(), False)
    endpoint.settimeout(GATE_TIMEOUT)
    stop = time.monotonic() + GATE_TIMEOUT
    key = [os.getpid(), process_tree.started(os.getpid())]
    correlation = token(sys.argv[2])
    try:
        print('private service gate awaiting guard registration', flush=True)
        send(endpoint, dict(gated=key, token=correlation), deadline=stop)
        if receive(endpoint, deadline=stop) != dict(go=key, token=correlation):
            return 1
    finally:
        endpoint.close()
    os.execvpe(sys.argv[3], sys.argv[3:], os.environ)


if __name__ == '__main__':
    raise SystemExit(main())
