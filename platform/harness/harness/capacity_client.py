"""Bounded guard-facing capacity RPC. A failed broker never grants a local fallback."""
from dataclasses import asdict
import errno
import math
import os
from pathlib import Path
import socket
import stat
import subprocess
import time

from atelier.harness import capacity_protocol as wire
from atelier.harness.capacity import Resources

CapacityError = wire.CapacityError


class CapacityQueued(CapacityError):
    """A positive broker response says this uncharged request is waiting."""


class CapacityOfferLost(CapacityError):
    """A fenced broker response positively denies GO for this pending gate child."""
    def __init__(self, session, reason='selection-changed'):
        self.reason = reason
        super().__init__('Capacity selection changed before GO; launch gate closed without execution')
        self.session = session
        self.child = session.child
        self.cleanup = None


class CapacityTransportError(CapacityError):
    """A transient transport failure; whether the broker acted is unknown."""


def wait_for_offer(admission, *, seconds=None):
    """@cc [owner:fontanierh,label:safety] uncharged-capacity-wait
    Only a positive queued response MAY retry admission, retaining this controller's request and nonce.
    Waiting MUST hold no capacity, launch gate, child or legacy lock. The queue loop MUST NOT catch
    transport, policy, fencing or other failures; session RPC reconciliation is separate and bounded.
    A queued job MUST stay queued until admitted, printing progress: lack of capacity is never a
    failure. A deadline applies only when the caller opts into one (seconds), and cancellation MUST
    unwind through the guard's normal queued-session close.
    """
    if seconds is not None and (type(seconds) not in (int, float) or not math.isfinite(seconds) or not seconds > 0):
        raise ValueError('Capacity queue wait must be None (until admitted) or a positive number of seconds')
    started = time.monotonic()
    spoken = None
    while True:
        try:
            return admission.offer()
        except CapacityQueued as queued:
            now = time.monotonic()
            if seconds is not None and now - started >= seconds:
                raise CapacityError('Capacity queue wait deadline reached; no resources held. '
                                    'Rerunning the same job retains its ready age.') from None
            if spoken is None or now - spoken >= 25:
                limit = '' if seconds is None else f'/{seconds:.0f}'
                print(f'Waiting for capacity: {now-started:.0f}{limit}s; '
                      f'broker queue active, no resources or child held; {queued}', flush=True)
                spoken = now
            time.sleep(1. if seconds is None else min(1., seconds - (now - started)))


def _endpoint(path):
    path = Path(path)
    if not path.is_absolute():
        raise CapacityError('Capacity socket path must be absolute')
    for part in (path, *path.parents):
        if part.is_symlink() and str(part) not in ('/tmp', '/var', '/etc'):
            raise CapacityError('Capacity socket ancestors cannot be links')
    directory, info = path.parent.stat(), path.lstat()
    if (directory.st_uid != os.getuid() or directory.st_mode & 0o077 or not stat.S_ISSOCK(info.st_mode)
            or info.st_uid != os.getuid() or info.st_mode & 0o077):
        raise CapacityError('Capacity socket must be private and owned')
    return path


def _rpc(path, message, timeout, *, descriptor=False):
    """@cc [owner:fontanierh,label:safety] bounded-rpc-diagnostics
    Transport diagnostics MUST expose only bounded operation/phase/type/errno/timing metadata,
    never request contents or raw transport errors. Diagnostics MUST NOT retry or extend deadlines.
    """
    if type(timeout) not in (int, float) or not .05 <= timeout <= 5:
        raise CapacityError('Capacity RPC deadline must be between .05 and 5 seconds')
    fd = None
    started = time.monotonic()
    phase = 'endpoint'
    try:
        deadline = started + timeout
        endpoint = _endpoint(path)
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as channel:
            if time.monotonic() >= deadline:
                raise CapacityError('Capacity RPC deadline exceeded')
            channel.settimeout(deadline - time.monotonic())
            phase = 'connect'
            channel.connect(str(endpoint))
            phase = 'send'
            wire.send(channel, {'namespace': wire.NAMESPACE, **message}, deadline=deadline)
            phase = 'receive'
            response, fd = wire.receive(channel, descriptor=descriptor, deadline=deadline)
        phase = 'response'
        if response.get('namespace') != wire.NAMESPACE:
            raise CapacityError('Capacity broker refused this operation')
        if response.get('ok') is not True:
            raise CapacityError(wire.text(response.get('error', 'Capacity broker refused this operation')))
        return response, fd
    except wire.CapacityError:
        if fd is not None:
            os.close(fd)
        raise
    except (OSError, ValueError, TypeError) as error:
        if fd is not None:
            os.close(fd)
        metadata = (f'action={wire.action_name(message)}, phase={phase}, error={type(error).__name__}, '
                    f'errno={error.errno if isinstance(error, OSError) else None}, '
                    f'elapsed={time.monotonic() - started:.3f}s, timeout={timeout:.3f}s')
        transient = (phase in ('connect', 'send', 'receive') and isinstance(error, OSError)
                     and (isinstance(error, TimeoutError) or error.errno in (
                         errno.EINTR, errno.EAGAIN, errno.ECONNRESET, errno.ECONNREFUSED,
                         errno.EPIPE, errno.ETIMEDOUT)))
        error_class = CapacityTransportError if transient else CapacityError
        raise error_class('Capacity broker unavailable or operation refused; no fallback admission ('
                          + metadata + ')') from None


def _session_rpc(path, message, timeout, *, descriptor=False):
    """@cc [owner:fontanierh,label:safety] bounded-fenced-rpc-replay
    Only offer, owned, check and close MAY replay once after a typed transient transport failure.
    The identical request MUST be resent under the existing per-call deadline and normal response
    fencing; no response may be assumed. Gate, start and replace MUST NOT replay. Protocol, policy,
    ownership and fencing refusals MUST propagate without retry, fallback or local release authority.
    """
    try:
        return _rpc(path, message, timeout, descriptor=descriptor)
    except CapacityTransportError:
        if descriptor or message.get('action') not in ('offer', 'owned', 'check', 'close'):
            raise
        print(f'Capacity transport interrupted: reconciling {wire.action_name(message)} once; '
              'same request, normal fencing and guards', flush=True)
        return _rpc(path, message, timeout, descriptor=descriptor)


def status(socket_path, *, timeout=2.):
    return _rpc(socket_path, {'action': 'status'}, timeout)[0]


def reconcile(socket_path, *, timeout=2., request_id=None, preserved_terminal=None):
    """Apply release policy, optionally attesting a preserved terminal receipt for one request."""
    if (request_id is None) != (preserved_terminal is None):
        raise CapacityError('Preserved terminal evidence requires both request ID and archive path')
    message = {'action': 'reconcile'}
    if request_id is not None:
        message['preserved_terminal'] = dict(request_id=wire.text(request_id),
                                            path=str(Path(preserved_terminal).absolute()))
    return _rpc(socket_path, message, timeout)[0]


def abandon_interrupted(socket_path, evidence, *, timeout=5.):
    """Operator-directed administration only; never called by automatic guarded cleanup."""
    return _rpc(socket_path, {'action': 'abandon-interrupted', 'interrupted_compile': evidence}, timeout)[0]


def abandon_completed(socket_path, evidence, *, timeout=5.):
    """Explicit reviewed administration; never automatic cleanup or output certification."""
    return _rpc(socket_path, {'action': 'abandon-completed', 'completed_job': evidence}, timeout)[0]


def abandon_unwitnessed(socket_path, evidence, *, timeout=5.):
    """Explicit administrator acknowledgement of lost root-exit history; never automatic."""
    return _rpc(socket_path, {'action': 'abandon-unwitnessed', 'unwitnessed_compile': evidence}, timeout)[0]


class AdmissionSession:
    """@cc [owner:fontanierh,label:safety] guard-facing-broker-admission
    Offers MUST be uncharged. Only the server's committed gate MAY release useful work; the
    client MUST never own a writer or fall back on broker failure. Close MUST obtain affirmative
    release evidence under the broker's exact or exclusive terminal-tree policy, or raise while
    the durable reservation stays held.
    A Popen witness proves the direct child's exit only, never an undiscovered process tree.
    """
    def __init__(self, socket_path, request, *, timeout=2., cutover=None, guard_limit_gib=None, mode=None, seal_policy_sha256=None):
        if guard_limit_gib is not None and (type(guard_limit_gib) not in (int, float)
                or not math.isfinite(guard_limit_gib) or guard_limit_gib <= 0):
            raise CapacityError('Configured guard ceiling must be positive and finite')
        self._guard_limit_gib = guard_limit_gib
        self.socket_path, self.request, self.timeout = Path(socket_path), dict(request), timeout
        self.cutover = cutover
        self.mode = mode or ('capacity' if cutover is not None else 'legacy-bridge')
        self.seal_policy_sha256 = seal_policy_sha256
        if self.mode not in ('legacy-bridge', 'capacity', 'sealed-maintenance') or ((cutover is None) != (self.mode == 'legacy-bridge')):
            raise CapacityError('Invalid capacity session mode')
        self.activation_id = None
        if cutover is not None:
            from atelier.harness import capacity_compat
            proof = (capacity_compat.verify_maintenance(cutover, policy_sha256=seal_policy_sha256)
                     if self.mode == 'sealed-maintenance' else capacity_compat.verify(cutover))
            if str(self.socket_path) != proof['socket']:
                raise CapacityError('Capacity client endpoint differs from the compatibility barrier')
            self.activation_id = proof['activation_id']
        if isinstance(self.request.get('resources'), Resources):
            self.request['resources'] = asdict(self.request['resources'])
        if 'locks' in self.request:
            self.request['locks'] = list(self.request['locks'])
        self.nonce = self.epoch = self.boot = None
        self.child = None
        self.closed = False
        self._acknowledged = set()
        self._requeue_fence = None

    def requeue_after(self, previous):
        """@cc [owner:fontanierh,label:safety] fenced-requeue-configuration
        A renewed automatic launch MUST retain the exact request, endpoint, guard ceiling and
        compatibility binding. Its first offer MUST carry and verify the previous epoch/boot;
        a restart or changed configuration MUST refuse rather than rebind or grant work.
        The guard caller MUST first establish no-GO, owned cleanup and uncharged close.
        """
        fields = ('socket_path', 'request', 'timeout', 'cutover', 'mode', 'seal_policy_sha256',
                  'activation_id', '_guard_limit_gib')
        if (not previous.closed or previous.nonce is None or self.nonce is not None
                or any(getattr(self, field) != getattr(previous, field) for field in fields)):
            raise CapacityError('Capacity requeue configuration changed')
        self._requeue_fence = (previous.epoch, previous.boot)

    @property
    def guard_limit_gib(self):
        """Selected automatic guard envelope; injected sessions never override the caller's limit."""
        return self._guard_limit_gib

    def _fence(self):
        return {'activation_id': self.activation_id} if self.mode in ('capacity', 'sealed-maintenance') else {}

    def _response(self, response, fd):
        if self.mode in ('capacity', 'sealed-maintenance') and (response.get('mode') != self.mode
                or response.get('activation_id') != self.activation_id):
            if fd is not None:
                os.close(fd)
            raise CapacityError('Capacity broker mode or compatibility epoch changed')
        return response, fd

    def _call(self, action, *, descriptor=False, **fields):
        if self.closed:
            raise CapacityError('Capacity session is closed')
        if self.nonce is None:
            raise CapacityError('Capacity offer has not been obtained')
        return self._response(*_session_rpc(self.socket_path, {'action': action, 'id': self.request['id'],
                                      'nonce': self.nonce, 'epoch': self.epoch, 'boot_id': self.boot,
                                      **self._fence(), **fields}, self.timeout, descriptor=descriptor))

    def offer(self):
        if self.closed:
            raise CapacityError('Capacity session is closed')
        response, _ = self._response(*_session_rpc(self.socket_path, {'action': 'offer', 'request': self.request,
                                            **self._fence(), **({'nonce': self.nonce} if self.nonce else {}),
                                            **(dict(epoch=self._requeue_fence[0], boot_id=self._requeue_fence[1])
                                               if self._requeue_fence else {})}, self.timeout))
        if self._requeue_fence is not None and (response.get('epoch'), response.get('boot_id')) != self._requeue_fence:
            raise CapacityError('Capacity requeue response was fenced by restart')
        if self.nonce is not None and (response.get('nonce'), response.get('epoch'), response.get('boot_id')) != (
                self.nonce, self.epoch, self.boot):
            raise CapacityError('Capacity offer was fenced by a session or broker change')
        if response['nonce'] != self.nonce:
            self._acknowledged.clear()
            self.child = None
        self.nonce, self.epoch = response['nonce'], response['epoch']
        self.boot = response['boot_id']
        if response.get('selected') is not True:
            if response.get('selected') is False and response.get('state') == 'queued':
                reason = 'Capacity request remains queued without holding resources'
                if 'wait_reason' in response:
                    try:
                        reason += '; ' + wire.text(response['wait_reason'], maximum=1024)
                    except CapacityError:
                        pass  # Optional display text cannot invalidate a positively fenced queued response.
                raise CapacityQueued(reason)
            raise CapacityError('Capacity offer response is not a selected or queued request')
        return response

    def owned(self, candidates):
        response, _ = self._call('owned', candidates=[list(wire.identity(pin)) for pin in candidates])
        if response.get('epoch') != self.epoch or response.get('boot_id') != self.boot:
            raise CapacityError('Capacity ownership response was fenced')
        values = response.get('owned')
        if type(values) is not list or len(values) > wire.MAX_ROSTER:
            raise CapacityError('Capacity ownership response is incomplete')
        result = {wire.identity(pin) for pin in values}
        if not result <= {wire.identity(pin) for pin in candidates}:
            raise CapacityError('Capacity ownership response includes an unrequested identity')
        return result

    def gate(self):
        response, fd = self._call('gate', descriptor=True)
        if response.get('state') != 'gated':
            if fd is not None:
                os.close(fd)
            raise CapacityError('Capacity launch gate was refused')
        return fd

    def start(self, *, child_pid, child_start, process_guard, tree_guard, limit_bytes):
        self.child = wire.identity((child_pid, child_start))
        response, _ = self._call('start', child=list(self.child), process_guard=process_guard,
                                 tree_guard=tree_guard, limit_bytes=limit_bytes)
        if response.get('no_go') is True:
            if (response.get('state') != 'queued' or response.get('admission') is not False
                    or response.get('reason') not in ('selection-changed', 'pressure-wait') or response.get('nonce') != self.nonce
                    or response.get('epoch') != self.epoch or response.get('boot_id') != self.boot
                    or wire.identity(response.get('child')) != self.child):
                raise CapacityError('Capacity no-GO response is incomplete or fenced')
            raise CapacityOfferLost(self, response['reason'])
        self._healthy(response)
        self._acknowledged.add(self.child)
        return response

    def _pending(self, descendants):
        # Discovery order keeps observed parents before their children, even across PID wrap.
        pins = list(dict.fromkeys(wire.identity(pin) for pin in descendants))
        if len(self._acknowledged | set(pins)) > wire.MAX_RETAINED:
            raise CapacityError('Retained process roster exceeds its limit')
        return [pin for pin in pins if pin not in self._acknowledged]

    def _healthy(self, response):
        if response.get('epoch') != self.epoch or response.get('boot_id') != self.boot:
            raise CapacityError('Capacity process acknowledgement was fenced')
        if response.get('state') not in ('running', 'draining') or response.get('admission') is not True:
            state = response.get('state') if response.get('state') in ('uncertain', 'released', 'waiting', 'queued') else 'invalid'
            raise CapacityError('Capacity grant is no longer healthy (' + state + ')')

    def check(self, *, descendants=()):
        """@cc [owner:fontanierh,label:safety] acknowledged-process-deltas
        Every observed identity MUST be registered in discovery order. Only a healthy fenced
        acknowledgement MAY suppress retransmission; failed batches MUST remain pending.
        A fenced completion observation MUST NOT acknowledge a batch or authorize more work.
        """
        pending = self._pending(descendants)
        for index in range(0, max(1, len(pending)), wire.MAX_ROSTER):
            batch = pending[index:index + wire.MAX_ROSTER]
            response, _ = self._call('check', descendants=[list(pin) for pin in batch])
            if response.get('terminal') is True or response.get('finish_required') is True:
                if (response.get('epoch') != self.epoch or response.get('boot_id') != self.boot
                        or (response.get('terminal') is True and response.get('finish_required') is True)
                        or response.get('admission') is not False or self.child is None
                        or wire.identity(response.get('child')) != self.child
                        or response.get('state') != ('released' if response.get('terminal') is True else 'uncertain')):
                    raise CapacityError('Capacity completion observation is invalid or fenced')
                return response  # No healthy acknowledgement, process-delta ACK or permission to keep running.
            self._healthy(response)
            self._acknowledged.update(batch)
        return response

    def replace(self, resources, locks):
        vector = asdict(resources) if isinstance(resources, Resources) else resources
        response, _ = self._call('replace', resources=vector, locks=list(locks))
        if response.get('admission') is not True:
            raise CapacityError('Capacity replacement was refused; old grant remains held')
        return response

    def close(self, *, child=None, child_start=None, descendants=()):
        if self.closed:
            return
        if self.nonce is None:
            self.closed = True
            return
        witness = None
        if child is not None and (child_start is not None or self.child is not None):
            if not isinstance(child, subprocess.Popen) or child_start is None:
                raise CapacityError('Close requires the actual owned Popen and start identity')
            pin = wire.identity((child.pid, child_start))
            if self.child is not None and pin != self.child:
                raise CapacityError('Close child differs from the admitted child')
            try:
                code = child.wait(timeout=0)
            except subprocess.TimeoutExpired:
                code = None
            if code is not None:
                witness = {'kind': 'direct-parent-wait', 'parent': [os.getpid(), wire.process_start(os.getpid())],
                           'child': list(pin), 'returncode': code}
        try:
            pending = self._pending(descendants)
            if len(pending) > wire.MAX_ROSTER:
                raise CapacityError('Atomic capacity close exceeds its process batch limit; reservation retained')
            response, _ = self._call('close', descendants=[list(pin) for pin in pending], witness=witness)
        finally:
            self.closed = True
        if response.get('released') is not True:
            raise CapacityError('Capacity exit remains uncertain; reservation and named locks retained')
        return response
