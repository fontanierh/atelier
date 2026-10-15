"""Bounded guard-facing capacity RPC. A failed broker never grants a local fallback."""
from dataclasses import asdict
import os
from pathlib import Path
import socket
import stat
import subprocess
import time

from . import capacity_protocol as wire
from .capacity import Resources

CapacityError = wire.CapacityError


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
    if type(timeout) not in (int, float) or not .05 <= timeout <= 5:
        raise CapacityError('Capacity RPC deadline must be between .05 and 5 seconds')
    fd = None
    try:
        deadline = time.monotonic() + timeout
        endpoint = _endpoint(path)
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as channel:
            if time.monotonic() >= deadline:
                raise CapacityError('Capacity RPC deadline exceeded')
            channel.settimeout(deadline - time.monotonic())
            channel.connect(str(endpoint))
            wire.send(channel, {'namespace': wire.NAMESPACE, **message}, deadline=deadline)
            response, fd = wire.receive(channel, descriptor=descriptor, deadline=deadline)
        if response.get('namespace') != wire.NAMESPACE:
            raise CapacityError('Capacity broker refused this operation')
        if response.get('ok') is not True:
            raise CapacityError(wire.text(response.get('error', 'Capacity broker refused this operation')))
        return response, fd
    except wire.CapacityError:
        if fd is not None:
            os.close(fd)
        raise
    except (OSError, ValueError, TypeError):
        if fd is not None:
            os.close(fd)
        raise CapacityError('Capacity broker unavailable or operation refused; no fallback admission') from None


def status(socket_path, *, timeout=2.):
    return _rpc(socket_path, {'action': 'status'}, timeout)[0]


def reconcile(socket_path, *, timeout=2.):
    """Release only retained rosters whose affirmative kernel exits are already recorded."""
    return _rpc(socket_path, {'action': 'reconcile'}, timeout)[0]


class AdmissionSession:
    """@cc [owner:fontanierh,label:safety] guard-facing-broker-admission
    Offers MUST be uncharged. Only the server's committed gate MAY release useful work; the
    client MUST never own a writer or fall back on broker failure. Close MUST obtain affirmative
    exit evidence for every retained identity or raise while the durable reservation stays held.
    A Popen witness proves the direct child's exit only, never an undiscovered process tree.
    """
    def __init__(self, socket_path, request, *, timeout=2., cutover=None):
        self.socket_path, self.request, self.timeout = Path(socket_path), dict(request), timeout
        self.cutover = cutover
        self.mode = 'capacity' if cutover is not None else 'legacy-bridge'
        self.activation_id = None
        if cutover is not None:
            from . import capacity_compat
            proof = capacity_compat.verify(cutover)
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

    def _fence(self):
        return {'activation_id': self.activation_id} if self.mode == 'capacity' else {}

    def _response(self, response, fd):
        if self.mode == 'capacity' and (response.get('mode') != self.mode
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
        return self._response(*_rpc(self.socket_path, {'action': action, 'id': self.request['id'],
                                      'nonce': self.nonce, 'epoch': self.epoch, 'boot_id': self.boot,
                                      **self._fence(), **fields}, self.timeout, descriptor=descriptor))

    def offer(self):
        response, _ = self._response(*_rpc(self.socket_path, {'action': 'offer', 'request': self.request,
                                            **self._fence(), **({'nonce': self.nonce} if self.nonce else {})}, self.timeout))
        self.nonce, self.epoch = response['nonce'], response['epoch']
        self.boot = response['boot_id']
        if response.get('selected') is not True:
            raise CapacityError('Capacity request remains queued without holding resources')
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
        if response.get('state') not in ('running', 'draining') or response.get('admission') is not True:
            raise CapacityError('Capacity launch was not durably admitted')
        return response

    def check(self, *, descendants=()):
        response, _ = self._call('check', descendants=[list(wire.identity(pin)) for pin in descendants])
        if response.get('state') not in ('running', 'draining') or response.get('admission') is not True:
            raise CapacityError('Capacity grant is no longer healthy')
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
            response, _ = self._call('close', descendants=[list(wire.identity(pin)) for pin in descendants], witness=witness)
        finally:
            self.closed = True
        if response.get('released') is not True:
            raise CapacityError('Capacity exit remains uncertain; reservation and named locks retained')
        return response
