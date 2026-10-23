"""Disposable protocol v1 worker for the C5b/C7 lifecycle tests. It stages nothing and runs no tools.

Usage: disposable_worker.py SCENARIO --request-fd N --response-fd M (the launcher appends the two
flags). It marks both protocol descriptors non-inheritable, then starts exactly one descendant that
lives until this worker's pipe to it closes, so a guard sees a two-process tree. Scenarios after
`started`: normal (completed), fail (failed/job), crash (exit 3), crash_once (exit 3 unless the
CRASH_MARKER file exists, which it creates), hang (wait until stopped or the pipe closes),
deaf (sends hello, then never reads again until stopped).
WORKER_FD_REPORT, when set, names a JSON file recording the descriptors this process holds;
JOB_LOG, when set, names a file that gets one JSON line {job_id, job_dir} for every run received.
Only the standard library and the Python protocol module, loaded by path, are used.
"""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import time

_path = Path(__file__).resolve().parents[3] / 'studio/atelier/build_v2/protocol.py'
_spec = importlib.util.spec_from_file_location('build_v2_protocol', _path)
protocol = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(protocol)

VERSION = os.environ.get('WORKER_VERSION', 'disposable-1')


def open_descriptors():
    """Descriptor number -> (device, inode) for every descriptor above stderr."""
    folder = '/dev/fd' if sys.platform == 'darwin' else '/proc/self/fd'
    found = {}
    for name in os.listdir(folder):
        fd = int(name)
        if fd < 3:
            continue
        try:
            value = os.fstat(fd)
        except OSError:
            continue  # the listing's own directory descriptor, already closed
        found[fd] = [value.st_dev, value.st_ino]
    return found


def main(argv):
    scenario = argv[0]
    request_fd = int(argv[argv.index('--request-fd') + 1])
    response_fd = int(argv[argv.index('--response-fd') + 1])
    report = os.environ.get('WORKER_FD_REPORT')
    if report:
        Path(report).write_text(json.dumps({'request_fd': request_fd, 'response_fd': response_fd,
                                            'open': open_descriptors()}))
    # The protocol pipe belongs to this worker only, never to its descendants.
    os.set_inheritable(request_fd, False)
    os.set_inheritable(response_fd, False)
    descendant = subprocess.Popen([sys.executable, '-c', 'import sys; sys.stdin.buffer.read()'],
                                  stdin=subprocess.PIPE)
    print(f'disposable worker {os.getpid()} descendant {descendant.pid}: {scenario}', flush=True)
    requests = os.fdopen(request_fd, 'rb', buffering=0)
    responses = os.fdopen(response_fd, 'wb', buffering=0)

    def send(message):
        protocol.write_frame(responses, protocol.RESPONSE, message)

    def receive():
        payload = protocol.read_payload(requests)
        return None if payload is None else protocol.decode_payload(protocol.REQUEST, payload)

    def end(code):
        descendant.stdin.close()
        descendant.wait()
        sys.exit(code)

    send({'type': 'hello', 'worker_version': VERSION})
    if scenario == 'deaf':
        while True:
            time.sleep(.05)  # never reads its request pipe; only a stop ends this worker
    while True:
        request = receive()
        if request is None:
            return end(0)
        if request['type'] == 'shutdown':
            send({'type': 'stopped'})
            return end(0)
        if request['type'] != 'run':
            continue
        job = request['job']
        send({'type': 'started', 'job_id': job['job_id']})
        if os.environ.get('JOB_LOG'):
            with open(os.environ['JOB_LOG'], 'a') as log:
                log.write(json.dumps({'job_id': job['job_id'], 'job_dir': job['job_dir']}) + '\n')
        marker = os.environ.get('CRASH_MARKER')
        if scenario == 'crash' or (scenario == 'crash_once' and marker and not Path(marker).exists()):
            if marker:
                Path(marker).write_text('crashed once\n')
            os._exit(3)  # the descendant sees its pipe close and exits too
        if scenario == 'hang':
            while receive() is not None:
                pass  # a cancel is not honoured; only a stop ends this worker
            return end(0)
        if scenario == 'fail':
            send({'type': 'failed', 'job_id': job['job_id'],
                  'failure': {'kind': 'job', 'message': 'scripted job failure'}})
            continue
        send({'type': 'completed', 'job_id': job['job_id'],
              'outputs': {'files': [item['path'] for item in job['outputs'] if item['required']]}})


if __name__ == '__main__':
    main(sys.argv[1:])
