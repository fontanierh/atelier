"""One-shot, closed two-process launch-barrier experiment. Never native admission."""
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import time

from .capacity_probe_child import command, expect, process_start, reap, receive, send
from .capacity_service import Observation, ShadowService, identity


class Probe:
    """@cc [owner:fontanierh,label:safety] closed-probe-barrier
    Only the fixed launcher and fixed worker MUST be launched. Useful work MUST follow pinned
    registration, synthetic readiness and a current-epoch heartbeat. Only exact owned wait facts
    MUST establish exit; missing receipts MUST retain uncertainty and shadow charges. Synthetic
    capacity/guard facts and this closed roster MUST NOT establish native eligibility.
    """
    def __init__(self, database):
        self.database = Path(database)
        self.service = ShadowService(self.database, observe=self.observe)
        self.sequence = 0
        self.epoch = 1
        self.bound = dict(epoch=self.epoch, nonce=secrets.token_hex(32))
        self.child = self.channel = self.ready = self.token = None
        self.launcher_waited = self.worker_waited = self.gate_opened = False
        self.useful_byte = None

    def call(self, action, **fields):
        self.sequence += 1
        return self.service.apply(dict(id=f'probe-{self.sequence}', action=action,
                                       epoch=self.epoch, **fields), now=int(time.monotonic()))

    def observe(self, now):
        processes, edges = {}, ()
        if self.ready is not None:
            for role, waited in (('launcher', self.launcher_waited), ('worker', self.worker_waited)):
                pin = self.ready[role]
                state = 'unknown'
                if waited:
                    state = 'dead'
                else:
                    try:
                        if (role != 'launcher' or self.child.poll() is None) and process_start(pin[0]) == pin[1]:
                            state = 'alive'
                    except (OSError, ValueError):
                        pass
                processes[identity(pin)] = state
            if all(value == 'alive' for value in processes.values()):
                edges = ((identity(self.ready['launcher']), identity(self.ready['worker'])),)
        # Completeness covers only the fixed program's known roster, never the host or arbitrary forks.
        return Observation(now, healthy=bool(processes) and 'unknown' not in processes.values(),
                           complete=self.ready is not None, available_mib=100, disk_available_mib=100,
                           processes=processes, edges=edges, measured_mib={'probe': 1},
                           allocated_temp_mib={'probe': 0})

    def start(self):
        # This command owns a fresh experiment, never an existing service or another holder's database.
        process_start(os.getpid())  # Unsupported/unavailable identity APIs refuse before any child launch.
        for suffix in ('', '-journal', '-wal', '-shm'):
            if os.path.lexists(str(self.database) + suffix):
                raise ValueError('Closed probes require a fresh shadow database')
        self.call('init', total=dict(memory_mib=10, cpu_millis=10), reserve={})
        parent, child_end = socket.socketpair()
        self.channel = parent
        try:
            self.child = subprocess.Popen(command('launcher', child_end.fileno()),
                                          pass_fds=(child_end.fileno(),), stdin=subprocess.DEVNULL,
                                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        finally:
            child_end.close()
        send(parent, self.bound)
        ready = receive(parent)
        expect(ready, dict(kind='ready', launcher=ready['launcher'], worker=ready['worker'], **self.bound))
        if ready['launcher'] != [self.child.pid, process_start(self.child.pid)]:
            raise ValueError('Probe launcher readiness mismatch')
        identity(ready['worker'])
        if ready['worker'][0] == self.child.pid or process_start(ready['worker'][0]) != ready['worker'][1]:
            raise ValueError('Probe worker identity mismatch')
        self.ready = ready
        self.call('submit', request_id='probe', owner='closed-probe', checkout='fixed-program',
                  resources=dict(memory_mib=1, cpu_millis=1), locks=['closed-probe'], launcher=ready['launcher'])
        decisions = self.call('schedule')['decisions']
        if len(decisions) != 1 or decisions[0]['result'] != 'reserved':
            raise ValueError('Probe reservation refused')
        self.token = decisions[0]['token']
        if self.call('register', request_id='probe', token=self.token, child=ready['worker'])['result'] != 'registered':
            raise ValueError('Probe registration refused')

    def open_gate(self):
        if self.call('running', request_id='probe', token=self.token, guard_ready=True)['result'] != 'running':
            raise ValueError('Synthetic probe readiness refused')
        if self.call('heartbeat', request_id='probe', token=self.token)['result'] != 'running':
            raise ValueError('Probe heartbeat refused')
        send(self.channel, dict(kind='go', launcher=self.ready['launcher'], worker=self.ready['worker'], **self.bound))
        self.gate_opened = True

    def accept_wait(self, receipt):
        if self.ready is None:
            raise ValueError('Probe readiness missing')
        expected = dict(kind='waited', launcher=self.ready['launcher'], worker=self.ready['worker'],
                        returncode=receipt.get('returncode'), useful_byte=receipt.get('useful_byte'), **self.bound)
        expect(receipt, expected)
        if type(receipt.get('returncode')) is not int or type(receipt.get('useful_byte')) is not bool:
            raise ValueError('Probe wait receipt mismatch')
        self.worker_waited = True
        self.useful_byte = receipt['useful_byte']
        return receipt['returncode']

    def close(self):
        """Cleanup cannot turn absent worker evidence into a dead observation."""
        worker_code = None
        launcher_code = None
        try:
            if self.channel is not None:
                try:
                    self.channel.shutdown(socket.SHUT_WR)
                    worker_code = self.accept_wait(receive(self.channel))
                except (OSError, ValueError, TimeoutError):
                    pass
            if self.child is not None:
                try:
                    launcher_code = reap(self.child)
                    self.launcher_waited = True
                except (OSError, subprocess.SubprocessError):
                    pass
        finally:
            if self.channel is not None:
                self.channel.close()
        released = 'not-reserved'
        if self.token is not None:
            try:
                released = self.call('release', request_id='probe', token=self.token)['result']
            except ValueError:
                released = 'fenced'
        return worker_code, launcher_code, released


def run(database):
    probe = Probe(database)
    error = None
    try:
        probe.start()
        probe.open_gate()
    except (OSError, ValueError, KeyError, TypeError):
        error = 'Probe readiness or gate refused'
    finally:
        worker_code, launcher_code, released = probe.close()
    passed = (error is None and probe.gate_opened and probe.useful_byte is True and
              worker_code == launcher_code == 0 and released == 'released')
    if not passed and error is None:
        error = 'Probe completion or release unproven'
    return dict(mode='shadow', admission=False, native_eligible=False, synthetic_resources=True,
                synthetic_guard_ready=True, roster='fixed-launcher-and-worker',
                identity_source='os-process-start', gate_opened=probe.gate_opened,
                useful_byte=probe.useful_byte, worker_waited=probe.worker_waited,
                launcher_waited=probe.launcher_waited, release=released,
                passed=passed, error=error)


def main(database, *, echo=print):
    result = run(database)
    echo(json.dumps(result, sort_keys=True))
    return 0 if result['passed'] else 1
