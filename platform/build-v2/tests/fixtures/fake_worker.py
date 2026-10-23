"""Scripted protocol v1 worker for the C1a pipe tests. It stages nothing and launches no tools.

Outside the deliberate fault scenarios it follows the worker rule: `started` for every `run`, then
exactly one terminal response; a cancel received while idle is ignored.

Usage: fake_worker.py SCENARIO REQUEST_FD RESPONSE_FD. Frames use only the two inherited pipe
descriptors; stdout and stderr carry log lines, as for a real worker. Only the standard library and
the Python protocol module (loaded by path, without the atelier package) are used.
"""
import importlib.util
import os
from pathlib import Path
import struct
import sys

_path = Path(__file__).resolve().parents[3] / 'studio/atelier/build_v2/protocol.py'
_spec = importlib.util.spec_from_file_location('build_v2_protocol', _path)
protocol = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(protocol)

VERSION = 'fake-worker-1'


def main(scenario, request_fd, response_fd):
    requests = os.fdopen(request_fd, 'rb', buffering=0)
    responses = os.fdopen(response_fd, 'wb', buffering=0)

    def send(message):
        protocol.write_frame(responses, protocol.RESPONSE, message)

    def send_raw(data):
        responses.write(data)
        responses.flush()

    def receive():
        payload = protocol.read_payload(requests)
        if payload is None:
            return None, None
        return protocol.decode_payload(protocol.REQUEST, payload), payload

    def drain():
        while receive()[0] is not None:
            pass

    if scenario == 'unknown_field_hello':
        payload = b'{"version":1,"message":{"type":"hello","worker_version":"fake-worker-1","pid":1}}'
        send_raw(struct.pack('>I', len(payload)) + payload)
        return drain()
    if scenario == 'oversize_hello':
        return send_raw(struct.pack('>I', protocol.MAX_FRAME_BYTES + 1))
    send({'type': 'hello', 'worker_version': 'fake-worker-0' if scenario == 'wrong_version' else VERSION})
    print(f'fake worker ready: {scenario}', flush=True)
    while True:
        request, payload = receive()
        if request is None:
            return
        if request['type'] == 'shutdown':
            send({'type': 'stopped'})
            return
        if request['type'] != 'run':
            # A cancel that raced the job's terminal response gets no reply.
            continue
        job = request['job']
        job_id = job['job_id']
        if scenario == 'truncated_body':
            return send_raw(struct.pack('>I', 100) + b'{"version":1')
        if scenario == 'terminal_before_started':
            send({'type': 'completed', 'job_id': job_id, 'outputs': {'files': []}})
            return drain()
        send({'type': 'started', 'job_id': f'{job_id}-other' if scenario == 'wrong_job_id' else job_id})
        print(f'job {job_id} started', flush=True)
        print(f'job {job_id} log on stderr', file=sys.stderr, flush=True)
        if scenario == 'exit_mid_job':
            os._exit(3)
        if scenario == 'wrong_job_id':
            return drain()
        if protocol.encode_payload(protocol.REQUEST, request) != payload:
            send({'type': 'failed', 'job_id': job_id,
                  'failure': {'kind': 'protocol', 'message': 'Python re-encoding differs from the received bytes'}})
            continue
        if job['params'].get('fixture') == 'await_cancel':
            follow, _ = receive()
            if follow == {'type': 'cancel', 'job_id': job_id}:
                send({'type': 'failed', 'job_id': job_id, 'failure': {'kind': 'cancelled', 'message': 'cancelled'}})
            else:
                send({'type': 'failed', 'job_id': job_id, 'failure': {'kind': 'protocol', 'message': f'got {follow}'}})
            continue
        completed = {'type': 'completed', 'job_id': job_id,
                     'outputs': {'files': [item['path'] for item in job['outputs'] if item['required']]}}
        send(completed)
        if scenario == 'duplicate_terminal':
            send(completed)
            return drain()


if __name__ == '__main__':
    main(sys.argv[1], int(sys.argv[2]), int(sys.argv[3]))
