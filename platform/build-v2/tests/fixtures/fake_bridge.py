"""Stand-in for the guarded bridge in hosted T0 tests. It admits nothing and guards nothing.

It accepts the real bridge's arguments and descriptors, records what it inherited, and reports
scripted guard observations as JSON lines on the events descriptor. The real bridge
(`atelier.build_v2.guarded_worker`) calls `guarded.run`; this fixture only spawns the worker
directly so the Rust adapter and lifecycle can be exercised on any host. Stdlib only.

Usage: fake_bridge.py SCENARIO --report DIR ... -- (the real bridge flags). Scenarios:
normal, queue_forever (never admitted; holds until stopped), guard_stop (the "guard" kills the
worker), foreign_exit (reports another identity's exit), unconfirmed (cleanup not confirmed),
spec_closed (closes its spec descriptor unread, so the launcher's spec write fails after the spawn;
it then waits to be stopped and reports nothing), samples (normal, plus a tree sample of only the
worker every 50 ms), busy_samples (samples that also list an unclassified process), early_exit
(reports the worker's exit as soon as it starts, before any reply is read: the order in which the
controller can see a real exit report and the worker's last replies). With custody descriptors it
also reports a stand-in custody monitor identity (itself) after child_started and writes
cleanup.json before finished, as the real bridge does; no_monitor reports none, monitor_changed
reports a second, different one. stop_after_start waits from child_started until the launcher's
SIGTERM has been delivered (a handshake on the signal wakeup pipe, never a delay), so the stop
always lands right after child_started. The stop handler only records the signal: it takes no
lock, since it runs on the main thread wherever that thread was interrupted.
It records its PID in bridge.pid and bounds itself: once the controller is gone, if its main thread
has not finished within 2 s, it kills and reaps its own worker (within 2 s) and exits, so the
launcher reaps it and no bridge outlives its test.
"""
import argparse
import json
import os
import select
from pathlib import Path
import signal
import subprocess
import sys
import threading
import time
import uuid

stopped = []
spawned = []  # the worker, once started
done = []  # set when the main thread has reported finished


def descriptors():
    folder = '/dev/fd' if sys.platform == 'darwin' else '/proc/self/fd'
    found = {}
    for name in os.listdir(folder):
        fd = int(name)
        if fd < 3:
            continue
        try:
            value = os.fstat(fd)
        except OSError:
            continue
        found[fd] = [value.st_dev, value.st_ino]
    return found


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('scenario')
    parser.add_argument('--report', type=Path, required=True)
    parser.add_argument('--purpose', required=True)
    parser.add_argument('--memory-gib', type=int, required=True)
    parser.add_argument('--timeout', type=float, required=True)
    parser.add_argument('--queue-wait', type=float)
    for name in ('events', 'liveness', 'spec', 'request', 'response'):
        parser.add_argument(f'--{name}-fd', type=int, required=True)
    parser.add_argument('--custody-fd', type=int, action='append', default=[])
    args = parser.parse_args()
    (args.report / 'inherited.json').write_text(json.dumps({
        'open': descriptors(), 'cwd': os.getcwd(), 'custody': args.custody_fd,
        'events': args.events_fd, 'liveness': args.liveness_fd, 'spec': args.spec_fd,
        'request': args.request_fd, 'response': args.response_fd}))
    for fd in (args.events_fd, args.liveness_fd, args.spec_fd, *args.custody_fd):
        os.set_inheritable(fd, False)
    if args.scenario == 'stop_after_start':
        (args.report / 'bridge.pid').write_text(f'{os.getpid()}\n')
    if args.scenario == 'spec_closed':
        os.close(args.spec_fd)
        while True:
            time.sleep(.02)  # until the launcher's SIGTERM; no receipt is ever written
    with os.fdopen(args.spec_fd, 'rb') as stream:
        spec = json.loads(stream.read())
    events = os.fdopen(args.events_fd, 'w', buffering=1)

    def emit(event, **fields):
        try:
            events.write(json.dumps({'event': event, **fields}) + '\n')
        except BrokenPipeError:
            pass  # the controller is gone; keep cleaning up

    def stop(number, frame):
        stopped.append(number)  # no lock: this may interrupt the main thread anywhere
    wake_r, wake_w = os.pipe()
    os.set_blocking(wake_w, False)
    signal.set_wakeup_fd(wake_w)  # one byte per delivered signal, written before the handler runs
    signal.signal(signal.SIGTERM, stop)

    def stop_delivered(timeout):
        # A stop delivered after the check still wakes select through its pipe byte; `stopped`,
        # not the byte, is the evidence, so draining the pipe can never lose a stop.
        if not stopped and select.select([wake_r], [], [], timeout)[0]:
            os.read(wake_r, 512)
        return bool(stopped)

    def watch_liveness():
        while os.read(args.liveness_fd, 1):
            pass
        (args.report / 'liveness-eof').write_text('controller gone\n')
        os.kill(os.getpid(), signal.SIGTERM)
        if args.scenario == 'stop_after_start':
            deadline = time.monotonic() + 2
            while not done and time.monotonic() < deadline:
                time.sleep(.02)
            if not done:  # the main thread is stuck: end our own worker and exit
                for child in spawned:
                    child.kill()
                    try:
                        child.wait(timeout=2)
                    except subprocess.TimeoutExpired:
                        pass
                (args.report / 'bridge-abandoned').write_text('main thread did not finish\n')
                os._exit(70)
    threading.Thread(target=watch_liveness, daemon=True).start()

    emit('queued')
    if args.scenario == 'queue_forever':
        while not stop_delivered(0.02):
            pass
        emit('finished', cleanup='confirmed', reason=None)
        return 0
    emit('admitted')
    command = [spec['program'], *spec['args'], '--request-fd', str(args.request_fd),
               '--response-fd', str(args.response_fd)]
    with (args.report / 'stdout.log').open('w') as log:
        child = subprocess.Popen(command, env=spec['env'], pass_fds=(args.request_fd, args.response_fd),
                                 stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT)
    spawned.append(child)
    os.close(args.request_fd)
    os.close(args.response_fd)
    identity = dict(pid=child.pid, started=f'fake-{child.pid}-{time.monotonic_ns()}', boot='fake-boot')
    emit('child_started', **identity)
    invocation = uuid.uuid4().hex
    monitor = [os.getpid(), 10**9 + os.getpid()]
    if args.custody_fd and args.scenario != 'no_monitor':
        emit('monitor', pid=monitor[0], started=str(monitor[1]), boot='fake-boot', invocation=invocation)
        if args.scenario == 'monitor_changed':
            emit('monitor', pid=monitor[0], started=str(monitor[1] + 1), boot='fake-boot', invocation=invocation)
    if args.scenario == 'stop_after_start':
        # Until the stop is delivered (its wakeup byte) or the worker exits.
        while child.poll() is None and not stop_delivered(0.02):
            pass
    if args.scenario == 'early_exit':
        emit('child_exited', returncode=0, stopped_by=None, **identity)
    stopped_by = None
    if args.scenario == 'guard_stop':
        child.kill()
        stopped_by = 'guard'
    while child.poll() is None:
        if args.scenario in ('samples', 'busy_samples'):
            processes = [[child.pid, identity['started']]]
            if args.scenario == 'busy_samples':
                processes.append([child.pid + 1, 'unclassified'])
            emit('tree_sample', time=time.time(), processes=processes)
        if stop_delivered(0.05 if args.scenario.endswith('samples') else 0.02):
            child.kill()
            stopped_by = stopped_by or 'cancel'
            break
    code = child.wait()
    if args.scenario == 'foreign_exit':
        identity['pid'] += 100000
    if args.scenario != 'early_exit':
        emit('child_exited', returncode=code if stopped_by is None else None, stopped_by=stopped_by, **identity)
    confirmed = args.scenario != 'unconfirmed'
    if args.custody_fd:
        record = dict(schema=1, invocation=invocation, boot='fake-boot', child=[child.pid, 1],
                      monitor=None if args.scenario == 'no_monitor' else monitor, confirmed=confirmed,
                      reason=None if confirmed else 'scripted uncertain cleanup')
        (args.report / 'cleanup.json.tmp').write_text(json.dumps(record))
        os.replace(args.report / 'cleanup.json.tmp', args.report / 'cleanup.json')
    if confirmed:
        emit('finished', cleanup='confirmed', reason=None)
    else:
        emit('finished', cleanup='unconfirmed', reason='scripted uncertain cleanup')
    done.append(True)
    return 0


if __name__ == '__main__':
    sys.exit(main())
