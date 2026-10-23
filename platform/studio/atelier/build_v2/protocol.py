"""Python framing and validation for build-v2 worker protocol version 1.

`platform/build-v2/src/protocol.rs` is authoritative. A frame is a four-byte unsigned big-endian payload
length followed by a UTF-8 JSON envelope `{"version":1,"message":{...}}` of at most 8 MiB. Messages are
plain dicts in the Rust shapes. The frames travel on a dedicated pipe; stdout and stderr stay logs.
Message ordering belongs to the controller session (`platform/build-v2/src/worker_session.rs`).

Decoding is at least as strict as the Rust reader. Python additionally refuses duplicate keys anywhere and
integers outside the 64-bit range, which Rust would keep only lossily. Encoding validates first and writes
the Rust byte form: compact JSON, fields in declaration order, params keys sorted, non-ASCII unescaped.
Floats use Rust's shortest round-trip text and its layout (`1e-7`, `0.00001`, `1e+16`, `100.0`).

Only the standard library is used, so a worker interpreter can load this file by path.
"""
from __future__ import annotations

from decimal import Decimal
import json
import math
import struct

PROTOCOL_VERSION = 1
MAX_FRAME_BYTES = 8 * 1024 * 1024
REQUEST = 'request'
RESPONSE = 'response'
FAILURE_KINDS = ('job', 'dependency', 'protocol', 'crash', 'cancelled', 'timeout', 'guard_stop')

# serde_json refuses the 128th nested array or object of a document.
_MAX_DEPTH = 127
_INT_MIN, _INT_MAX = -(1 << 63), (1 << 64) - 1
_JOB_FIELDS = ('job_id', 'unit', 'op', 'job_dir', 'script', 'code', 'inputs', 'params', 'outputs')


class ProtocolError(Exception):
    """A frame or message that protocol version 1 refuses."""


class InvalidMessage(ProtocolError):
    """Bad length, payload, envelope or message: Rust's `InvalidData`."""


class TruncatedFrame(ProtocolError):
    """The stream ended inside a frame: Rust's `UnexpectedEof`."""


def _fail(where, problem):
    raise InvalidMessage(f'{where}: {problem}')


def _fields(value, where, required, optional=()):
    if not isinstance(value, dict):
        _fail(where, 'expected an object')
    for name in value:
        if name not in required and name not in optional:
            _fail(where, f'unknown field {name!r}')
    for name in required:
        if name not in value:
            _fail(where, f'missing field {name!r}')
    return value


def _tag(value, where, allowed, key='type'):
    if not isinstance(value, dict):
        _fail(where, 'expected an object')
    tag = value.get(key)
    if not isinstance(tag, str) or tag not in allowed:
        _fail(where, f'unknown or missing {key} {tag!r}')
    return tag


def _str(value, where):
    if not isinstance(value, str):
        _fail(where, 'expected a string')
    try:
        value.encode('utf-8')
    except UnicodeEncodeError:
        _fail(where, 'unpaired surrogate')
    return value


def _list(value, where):
    if not isinstance(value, list):
        _fail(where, 'expected an array')
    return value


def _value(value, where):
    """Normalize one arbitrary JSON parameter value the way serde_json::Value holds it."""
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, int):
        if not _INT_MIN <= value <= _INT_MAX:
            _fail(where, 'integer outside the 64-bit range')
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            _fail(where, 'non-finite number')
        return value
    if isinstance(value, str):
        return _str(value, where)
    if isinstance(value, list):
        return [_value(item, where) for item in value]
    if isinstance(value, dict):
        keys = sorted(_str(key, where) for key in value)
        return {key: _value(value[key], where) for key in keys}
    _fail(where, f'unsupported value {type(value).__name__}')


def _job(job):
    _fields(job, 'job', _JOB_FIELDS)
    op = _fields(job['op'], 'job.op', ('kind', 'version'))
    params = job['params']
    if not isinstance(params, dict):
        _fail('job.params', 'expected an object')
    return {
        'job_id': _str(job['job_id'], 'job.job_id'),
        'unit': _str(job['unit'], 'job.unit'),
        'op': {'kind': _str(op['kind'], 'job.op.kind'), 'version': _str(op['version'], 'job.op.version')},
        'job_dir': _str(job['job_dir'], 'job.job_dir'),
        'script': _str(job['script'], 'job.script'),
        'code': [_str(path, 'job.code') for path in _list(job['code'], 'job.code')],
        'inputs': [_input(item) for item in _list(job['inputs'], 'job.inputs')],
        'params': _value(params, 'job.params'),
        'outputs': [_output(item) for item in _list(job['outputs'], 'job.outputs')],
    }


def _input(item):
    _fields(item, 'job.inputs[]', ('name', 'path', 'identity'))
    identity = item['identity']
    state = _tag(identity, 'job.inputs[].identity', ('absent', 'digest'), key='state')
    if state == 'absent':
        _fields(identity, 'job.inputs[].identity', ('state',))
        normalized = {'state': 'absent'}
    else:
        _fields(identity, 'job.inputs[].identity', ('state', 'digest'))
        normalized = {'state': 'digest', 'digest': _str(identity['digest'], 'job.inputs[].identity.digest')}
    return {'name': _str(item['name'], 'job.inputs[].name'), 'path': _str(item['path'], 'job.inputs[].path'),
            'identity': normalized}


def _output(item):
    _fields(item, 'job.outputs[]', ('path',), ('install_path', 'required'))
    normalized = {'path': _str(item['path'], 'job.outputs[].path')}
    # serde: an Option field accepts null as absent; `required` defaults to true but is never null.
    if item.get('install_path') is not None:
        normalized['install_path'] = _str(item['install_path'], 'job.outputs[].install_path')
    required = item.get('required', True)
    if not isinstance(required, bool):
        _fail('job.outputs[].required', 'expected a boolean')
    normalized['required'] = required
    return normalized


def _request(message):
    kind = _tag(message, 'request', ('run', 'cancel', 'shutdown'))
    if kind == 'run':
        _fields(message, 'run', ('type', 'job'))
        return {'type': 'run', 'job': _job(message['job'])}
    if kind == 'cancel':
        _fields(message, 'cancel', ('type', 'job_id'))
        return {'type': 'cancel', 'job_id': _str(message['job_id'], 'cancel.job_id')}
    _fields(message, 'shutdown', ('type',))
    return {'type': 'shutdown'}


def _response(message):
    kind = _tag(message, 'response', ('hello', 'started', 'completed', 'failed', 'stopped'))
    if kind == 'hello':
        _fields(message, 'hello', ('type', 'worker_version'))
        return {'type': 'hello', 'worker_version': _str(message['worker_version'], 'hello.worker_version')}
    if kind == 'started':
        _fields(message, 'started', ('type', 'job_id'))
        return {'type': 'started', 'job_id': _str(message['job_id'], 'started.job_id')}
    if kind == 'completed':
        _fields(message, 'completed', ('type', 'job_id', 'outputs'))
        outputs = _fields(message['outputs'], 'completed.outputs', ('files',))
        files = [_str(path, 'completed.outputs.files') for path in _list(outputs['files'], 'completed.outputs.files')]
        return {'type': 'completed', 'job_id': _str(message['job_id'], 'completed.job_id'), 'outputs': {'files': files}}
    if kind == 'failed':
        _fields(message, 'failed', ('type', 'job_id', 'failure'))
        failure = _fields(message['failure'], 'failed.failure', ('kind', 'message'))
        if not isinstance(failure['kind'], str) or failure['kind'] not in FAILURE_KINDS:
            _fail('failed.failure.kind', f'unknown failure kind {failure["kind"]!r}')
        return {'type': 'failed', 'job_id': _str(message['job_id'], 'failed.job_id'),
                'failure': {'kind': failure['kind'], 'message': _str(failure['message'], 'failed.failure.message')}}
    _fields(message, 'stopped', ('type',))
    return {'type': 'stopped'}


def validate(kind, message):
    """@cc [owner:fontanierh,label:correctness] build-v2-python-message-parity
    Python MUST accept a request or response only in a shape Rust's protocol.rs also accepts,
    refusing unknown, missing, duplicate and wrongly typed fields (bool is not an integer) and
    unknown tags. It MUST return the normalized message Rust would decode, in Rust field order,
    so that re-encoding reproduces Rust's bytes. tests/vectors/protocol_v1.json is shared with Rust.
    """
    if kind == REQUEST:
        return _request(message)
    if kind == RESPONSE:
        return _response(message)
    raise ValueError(f'unknown message kind {kind!r}')


def _depth(value):
    deepest, pending = 0, [(value, 1)]
    while pending:
        item, level = pending.pop()
        if isinstance(item, (list, dict)):
            deepest = max(deepest, level)
            pending.extend((child, level + 1) for child in (item.values() if isinstance(item, dict) else item))
    return deepest


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            _fail('json', f'duplicate field {key!r}')
        result[key] = value
    return result


def _constant(name):
    _fail('json', f'non-finite number {name}')


def _float(text):
    value = float(text)
    if not math.isfinite(value):
        _fail('json', 'number out of range')
    return value


def _int(text):
    if text == '-0':
        return -0.0  # serde_json keeps the sign of `-0` by decoding it as a float
    value = int(text)
    if not _INT_MIN <= value <= _INT_MAX:
        _fail('json', 'integer outside the 64-bit range')
    return value


def decode_payload(kind, payload):
    """Decode one frame payload (without its length header) into a normalized message."""
    if not 0 < len(payload) <= MAX_FRAME_BYTES:
        _fail('frame', 'invalid frame length')
    try:
        document = json.loads(bytes(payload).decode('utf-8'), object_pairs_hook=_pairs,
                              parse_constant=_constant, parse_float=_float, parse_int=_int)
    except ProtocolError:
        raise
    except (ValueError, RecursionError) as error:
        raise InvalidMessage(f'json: {error}') from None
    if _depth(document) > _MAX_DEPTH:
        _fail('json', 'recursion limit exceeded')
    _fields(document, 'envelope', ('version', 'message'))
    version = document['version']
    if isinstance(version, bool) or not isinstance(version, int):
        _fail('envelope.version', 'expected an unsigned integer')
    if version != PROTOCOL_VERSION:
        _fail('envelope.version', 'unsupported protocol version')
    return validate(kind, document['message'])


def _float_text(value):
    """serde_json's float text: the shortest round-trip digits (Python's repr), laid out as Rust does."""
    sign = '-' if math.copysign(1.0, value) < 0 else ''
    if value == 0:
        return sign + '0.0'
    _, digit_tuple, exponent = Decimal(repr(abs(value))).as_tuple()
    digits = ''.join(map(str, digit_tuple)).rstrip('0')
    exponent += len(digit_tuple) - len(digits)
    point = len(digits) + exponent - 1  # decimal exponent of the leading digit
    if -5 <= point <= 15:
        if len(digits) - 1 <= point:
            return sign + digits + '0' * (point + 1 - len(digits)) + '.0'
        if point >= 0:
            return sign + digits[:point + 1] + '.' + digits[point + 1:]
        return sign + '0.' + '0' * (-point - 1) + digits
    mantissa = digits[0] + ('.' + digits[1:] if len(digits) > 1 else '')
    return f'{sign}{mantissa}e{"+" if point >= 0 else "-"}{abs(point)}'


def _json(value):
    """Compact JSON in insertion order with Rust's string escapes and float text."""
    if isinstance(value, dict):
        return '{' + ','.join(f'{_json(key)}:{_json(item)}' for key, item in value.items()) + '}'
    if isinstance(value, list):
        return '[' + ','.join(_json(item) for item in value) + ']'
    if isinstance(value, float):
        return _float_text(value)
    return json.dumps(value, ensure_ascii=False)


def encode_payload(kind, message):
    """Validate a message and return its envelope bytes in Rust's form, without the length header."""
    envelope = {'version': PROTOCOL_VERSION, 'message': validate(kind, message)}
    if _depth(envelope) > _MAX_DEPTH:
        _fail('json', 'recursion limit exceeded')
    payload = _json(envelope).encode('utf-8')
    if len(payload) > MAX_FRAME_BYTES:
        _fail('frame', 'frame exceeds maximum length')
    return payload


def encode_frame(kind, message):
    payload = encode_payload(kind, message)
    return struct.pack('>I', len(payload)) + payload


def _read_exactly(stream, count, inside_frame):
    data = bytearray()
    while len(data) < count:
        chunk = stream.read(count - len(data))
        if chunk is None:
            raise ProtocolError('non-blocking protocol streams are not supported')
        if not chunk:
            if not data and not inside_frame:
                return None
            raise TruncatedFrame(f'stream ended after {len(data)} of {count} bytes')
        data += chunk
    return bytes(data)


def read_payload(stream):
    """@cc [owner:fontanierh,label:correctness] build-v2-python-framing
    Python framing MUST match protocol.rs: None only for EOF before a frame's first byte; EOF
    inside the header or body MUST raise TruncatedFrame; a zero or over-8-MiB length MUST raise
    InvalidMessage before any body byte is read. Short reads MUST be completed, not treated as
    frames. write_frame MUST refuse an invalid or oversized message before writing any byte.
    """
    header = _read_exactly(stream, 4, inside_frame=False)
    if header is None:
        return None
    (length,) = struct.unpack('>I', header)
    if length == 0 or length > MAX_FRAME_BYTES:
        _fail('frame', 'invalid frame length')
    return _read_exactly(stream, length, inside_frame=True)


def read_frame(stream, kind):
    """Read one frame from a blocking binary stream; None means a clean close between frames."""
    payload = read_payload(stream)
    return None if payload is None else decode_payload(kind, payload)


def write_frame(stream, kind, message):
    """Write one complete frame to a blocking binary stream, completing short writes, then flush."""
    view = memoryview(encode_frame(kind, message))
    while view:
        written = stream.write(view)
        if not written:
            raise ProtocolError('protocol stream accepted no bytes')
        view = view[written:]
    stream.flush()
