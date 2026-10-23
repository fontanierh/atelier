"""Python protocol v1 framing matches the Rust reader and writer, without native tools or a Rust build."""
import io
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import threading

import pytest

from atelier.build_v2 import protocol
from atelier.build_v2.protocol import InvalidMessage, ProtocolError, TruncatedFrame

_crate = Path(__file__).resolve().parents[3] / 'platform/build-v2'
_vectors = json.loads((_crate / 'tests/vectors/protocol_v1.json').read_text(encoding='utf-8'))['vectors']
_errors = {'invalid': InvalidMessage, 'truncated': TruncatedFrame}


def vector_bytes(vector, field='chunks'):
    return b''.join(bytes.fromhex(chunk['hex']) if 'hex' in chunk else chunk['text'].encode('utf-8')
                    for chunk in vector[field])


class Trickle(io.RawIOBase):
    """Returns at most one byte per read, like a slow pipe."""

    def __init__(self, data):
        self.data, self.offset = data, 0

    def readable(self):
        return True

    def read(self, size=-1):
        chunk = self.data[self.offset:self.offset + 1]
        self.offset += len(chunk)
        return chunk


@pytest.mark.parametrize('vector', _vectors, ids=[vector['name'] for vector in _vectors])
def test_shared_vectors_decode_and_encode_like_rust(vector):
    data = vector_bytes(vector)
    opaque = vector.get('opaque_messages', 0)
    assert not opaque or vector['canonical']
    for stream in (io.BytesIO(data), Trickle(data)):
        decoded = [protocol.read_frame(stream, vector['kind']) for _ in range(len(vector['messages']) + opaque)]
        assert decoded[:len(vector['messages'])] == vector['messages']
        if vector['error'] is None:
            assert protocol.read_frame(stream, vector['kind']) is None
        else:
            with pytest.raises(_errors[vector['error']]):
                protocol.read_frame(stream, vector['kind'])
    encoded = b''.join(protocol.encode_frame(vector['kind'], message) for message in decoded)
    if vector['canonical']:
        assert encoded == data
    if 'reencoded' in vector:
        assert encoded == vector_bytes(vector, 'reencoded')


def test_every_partial_frame_is_truncated_and_only_eof_between_frames_is_clean():
    frame = protocol.encode_frame(protocol.REQUEST, {'type': 'shutdown'})
    assert protocol.read_frame(io.BytesIO(b''), protocol.REQUEST) is None
    for end in range(1, len(frame)):
        with pytest.raises(TruncatedFrame):
            protocol.read_frame(io.BytesIO(frame[:end]), protocol.REQUEST)


def test_oversize_length_fails_before_reading_the_body():
    class HeaderOnly:
        def __init__(self, header):
            self.header = header

        def read(self, size):
            if not self.header:
                raise AssertionError('the body must not be read')
            chunk, self.header = self.header[:size], self.header[size:]
            return chunk

    for length in (0, protocol.MAX_FRAME_BYTES + 1, 0xFFFFFFFF):
        with pytest.raises(InvalidMessage):
            protocol.read_frame(HeaderOnly(struct.pack('>I', length)), protocol.REQUEST)


def test_maximum_frame_is_accepted_and_one_byte_more_writes_nothing():
    def completed(name):
        return {'type': 'completed', 'job_id': 'j', 'outputs': {'files': [name]}}
    padding = protocol.MAX_FRAME_BYTES - len(protocol.encode_payload(protocol.RESPONSE, completed('')))
    largest = completed('x' * padding)
    frame = protocol.encode_frame(protocol.RESPONSE, largest)
    assert len(frame) == 4 + protocol.MAX_FRAME_BYTES
    assert protocol.read_frame(io.BytesIO(frame), protocol.RESPONSE) == largest
    out = io.BytesIO()
    with pytest.raises(InvalidMessage):
        protocol.write_frame(out, protocol.RESPONSE, completed('x' * (padding + 1)))
    assert out.getvalue() == b''


@pytest.mark.parametrize('message', [
    {'type': 'shutdown', 'typo': 1},
    {'type': 'cancel', 'job_id': 1},
    {'type': 'pause'},
    {'type': 'cancel', 'job_id': '\ud800'},
    {'type': 'run', 'job': {'job_id': 'j'}},
])
def test_encoder_refuses_invalid_messages_without_writing(message):
    out = io.BytesIO()
    with pytest.raises(InvalidMessage):
        protocol.write_frame(out, protocol.REQUEST, message)
    assert out.getvalue() == b''


def test_short_writes_are_completed():
    class Dribble(io.RawIOBase):
        def __init__(self):
            self.data = bytearray()

        def writable(self):
            return True

        def write(self, buffer):
            self.data += bytes(buffer[:1])
            return 1

    out = Dribble()
    protocol.write_frame(out, protocol.REQUEST, {'type': 'cancel', 'job_id': 'job-1'})
    assert protocol.read_frame(io.BytesIO(bytes(out.data)), protocol.REQUEST) == {'type': 'cancel', 'job_id': 'job-1'}


def test_explicit_job_relative_paths_are_preserved_exactly():
    job = {'job_id': 'j', 'unit': 'u', 'op': {'kind': 'k', 'version': '1'}, 'job_dir': '/jobs/j',
           'script': 'code/Été.py', 'code': ['code/Été.py', 'code/éte.py'], 'inputs': [
               {'name': 'a', 'path': 'inputs/A.json', 'identity': {'state': 'absent'}}],
           'params': {}, 'outputs': [{'path': 'Out/x.glb', 'required': True}]}
    decoded = protocol.read_frame(io.BytesIO(protocol.encode_frame(protocol.REQUEST, {'type': 'run', 'job': job})),
                                  protocol.REQUEST)
    assert decoded == {'type': 'run', 'job': job}


def run_job(job_id, **params):
    return {'type': 'run', 'job': {
        'job_id': job_id, 'unit': 'fixture/piece', 'op': {'kind': 'fixture', 'version': '1'},
        'job_dir': f'/jobs/{job_id}', 'script': 'code/run.py', 'code': ['code/run.py'],
        'inputs': [{'name': 'shape', 'path': 'inputs/shape.json', 'identity': {'state': 'digest', 'digest': 'd1'}}],
        'params': params, 'outputs': [{'path': 'piece.glb', 'required': True},
                                      {'path': 'piece.log', 'required': False}]}}


def test_python_controller_and_worker_over_dedicated_pipes():
    request_read, request_write = os.pipe()
    response_read, response_write = os.pipe()
    worker = subprocess.Popen(
        [sys.executable, str(_crate / 'tests/fixtures/fake_worker.py'), 'normal', str(request_read), str(response_write)],
        pass_fds=(request_read, response_write), stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    os.close(request_read)
    os.close(response_write)
    watchdog = threading.Timer(10, worker.kill)
    watchdog.start()
    try:
        with os.fdopen(request_write, 'wb', buffering=0) as requests, \
                os.fdopen(response_read, 'rb', buffering=0) as responses:
            def exchange(message):
                protocol.write_frame(requests, protocol.REQUEST, message)
                return protocol.read_frame(responses, protocol.RESPONSE)

            assert protocol.read_frame(responses, protocol.RESPONSE) == {'type': 'hello', 'worker_version': 'fake-worker-1'}
            assert exchange(run_job('job-1', label='ünïcode')) == {'type': 'started', 'job_id': 'job-1'}
            assert protocol.read_frame(responses, protocol.RESPONSE) == {
                'type': 'completed', 'job_id': 'job-1', 'outputs': {'files': ['piece.glb']}}
            assert exchange(run_job('job-2', fixture='await_cancel')) == {'type': 'started', 'job_id': 'job-2'}
            assert exchange({'type': 'cancel', 'job_id': 'job-2'}) == {
                'type': 'failed', 'job_id': 'job-2', 'failure': {'kind': 'cancelled', 'message': 'cancelled'}}
            assert exchange({'type': 'shutdown'}) == {'type': 'stopped'}
            assert protocol.read_frame(responses, protocol.RESPONSE) is None
        stdout, stderr = worker.communicate(timeout=10)
    finally:
        watchdog.cancel()
        worker.kill()
        worker.wait()
    assert worker.returncode == 0
    assert b'job job-1 started' in stdout and b'job job-2 started' in stdout
    assert b'job job-1 log on stderr' in stderr


def test_non_blocking_streams_are_refused():
    class Empty(io.RawIOBase):
        def readable(self):
            return True

        def read(self, size=-1):
            return None

    with pytest.raises(ProtocolError):
        protocol.read_frame(Empty(), protocol.REQUEST)
