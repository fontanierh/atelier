"""Writes protocol_v1.json: `python3 generate_protocol_v1.py > protocol_v1.json`.

Payload text and expected messages are written by hand here; nothing comes from the code under test.
"""
import json
import struct
import sys

MAX = 8 * 1024 * 1024

def head(n):
    return {'hex': struct.pack('>I', n).hex()}

def frame(text):
    data = text.encode('utf-8')
    return [head(len(data)), {'text': text}]

def raw(data):
    return [head(len(data)), {'hex': data.hex()}]

vectors = []
def add(name, kind, chunks, messages=(), error=None, canonical=False, opaque=0):
    vector = {'name': name, 'kind': kind, 'chunks': chunks, 'messages': list(messages),
              'error': error, 'canonical': canonical}
    if opaque:
        vector['opaque_messages'] = opaque
    vectors.append(vector)

SHUTDOWN = '{"version":1,"message":{"type":"shutdown"}}'
CANCEL = '{"version":1,"message":{"type":"cancel","job_id":"job-1"}}'

label = 'café ☕ 𝄞 "q" \\ \n\t\x01\x7f'
label_json = 'café ☕ 𝄞 \\"q\\" \\\\ \\n\\t\\u0001\x7f'
RUN = ('{"version":1,"message":{"type":"run","job":{"job_id":"job-1","unit":"mesh/arch",'
       '"op":{"kind":"blender_export","version":"1"},"job_dir":"/jobs/job-1","script":"code/export.py",'
       '"code":["code/export.py","code/lib/shape.py"],'
       '"inputs":[{"name":"terrain","path":"inputs/terrain/heights.json","identity":{"state":"digest","digest":"sha256:ab"}},'
       '{"name":"overrides","path":"inputs/overrides.json","identity":{"state":"absent"}}],'
       '"params":{"angle":0.5,"big":18446744073709551615,"flags":[true,false,null],"label":"' + label_json + '",'
       '"min":-9223372036854775808,"nested":{"a":1,"b":[]}},'
       '"outputs":[{"path":"arch.glb","install_path":"out/arch.glb","required":true},{"path":"arch.log.json","required":false}]}}}')
RUN_JOB = {
    'job_id': 'job-1', 'unit': 'mesh/arch', 'op': {'kind': 'blender_export', 'version': '1'},
    'job_dir': '/jobs/job-1', 'script': 'code/export.py', 'code': ['code/export.py', 'code/lib/shape.py'],
    'inputs': [{'name': 'terrain', 'path': 'inputs/terrain/heights.json', 'identity': {'state': 'digest', 'digest': 'sha256:ab'}},
               {'name': 'overrides', 'path': 'inputs/overrides.json', 'identity': {'state': 'absent'}}],
    'params': {'angle': 0.5, 'big': 18446744073709551615, 'flags': [True, False, None], 'label': label,
               'min': -9223372036854775808, 'nested': {'a': 1, 'b': []}},
    'outputs': [{'path': 'arch.glb', 'install_path': 'out/arch.glb', 'required': True},
                {'path': 'arch.log.json', 'required': False}],
}
SMALL_JOB = ('{"job_id":"j","unit":"u","op":{"kind":"k","version":"1"},"job_dir":"/jobs/j","script":"s.py",'
             '"code":["s.py"],"inputs":[],"params":{},"outputs":[OUT]}')
def small_run(out='{"path":"o.json","required":true}', job=None):
    return '{"version":1,"message":{"type":"run","job":' + (job or SMALL_JOB).replace('OUT', out) + '}}'
def small_expected(outputs):
    return {'type': 'run', 'job': {'job_id': 'j', 'unit': 'u', 'op': {'kind': 'k', 'version': '1'}, 'job_dir': '/jobs/j',
            'script': 's.py', 'code': ['s.py'], 'inputs': [], 'params': {}, 'outputs': outputs}}

# Requests that decode.
add('empty_stream_is_clean_eof', 'request', [], canonical=True)
add('shutdown', 'request', frame(SHUTDOWN), [{'type': 'shutdown'}], canonical=True)
add('cancel_then_shutdown', 'request', frame(CANCEL) + frame(SHUTDOWN),
    [{'type': 'cancel', 'job_id': 'job-1'}, {'type': 'shutdown'}], canonical=True)
add('run_with_unicode_escapes_extreme_integers_and_both_identities', 'request', frame(RUN),
    [{'type': 'run', 'job': RUN_JOB}], canonical=True)
add('run_required_defaults_true_and_null_install_path_is_absent', 'request',
    frame(small_run('{"path":"o.json","install_path":null}')),
    [small_expected([{'path': 'o.json', 'required': True}])])
add('fields_in_any_order_with_whitespace', 'request',
    frame(' {"message" : {"job_id":"job-1", "type":"cancel"},\n"version":1} '),
    [{'type': 'cancel', 'job_id': 'job-1'}])
deep_ok = '[' * 123 + ']' * 123
deep_bad = '[' * 124 + ']' * 124
def deep_job(value):
    return SMALL_JOB.replace('"params":{}', '"params":{"d":' + value + '}')
# Rust's float text (serde_json via zmij): shortest digits, fixed layout for leading-digit exponents
# -5..=15, otherwise `e+N`/`e-N`. Written by hand here, not by the Python encoder.
FLOATS = ('1e-7,0.00001,0.00001234,1e-6,1e+16,1000000000000000.0,1.2345678901234568e+17,1.5e+300,5e-324,'
          '1.7976931348623157e+308,0.1,2.5,100.0,123.456,-2.5e-10,-0.0')
FLOAT_VALUES = [1e-7, 0.00001, 0.00001234, 1e-6, 1e16, 1e15, 1.2345678901234568e17, 1.5e300, 5e-324,
                1.7976931348623157e308, 0.1, 2.5, 100.0, 123.456, -2.5e-10, -0.0]
add('floats_use_rust_shortest_text', 'request',
    frame(small_run(job=SMALL_JOB.replace('"params":{}', '"params":{"f":[' + FLOATS + ']}'))),
    [{'type': 'run', 'job': {**small_expected([{'path': 'o.json', 'required': True}])['job'], 'params': {'f': FLOAT_VALUES}}}],
    canonical=True)
# Not canonical: serde_json decodes the integer token `-0` as the float -0.0 and writes `-0.0`.
add('negative_zero_integer_token_is_float', 'request',
    frame(small_run(job=SMALL_JOB.replace('"params":{}', '"params":{"x":-0}'))),
    [{'type': 'run', 'job': {**small_expected([{'path': 'o.json', 'required': True}])['job'], 'params': {'x': -0.0}}}])
vectors[-1]['reencoded'] = frame(small_run(job=SMALL_JOB.replace('"params":{}', '"params":{"x":-0.0}')))
# Too deep to embed as an expected value here; the canonical byte comparison checks its content.
add('nesting_depth_127_is_accepted', 'request', frame(small_run(job=deep_job(deep_ok))), canonical=True, opaque=1)

# Requests that fail as invalid data.
for name, text in [
    ('unsupported_version', '{"version":2,"message":{"type":"shutdown"}}'),
    ('version_as_string', '{"version":"1","message":{"type":"shutdown"}}'),
    ('version_as_boolean', '{"version":true,"message":{"type":"shutdown"}}'),
    ('version_as_float', '{"version":1.0,"message":{"type":"shutdown"}}'),
    ('missing_version', '{"message":{"type":"shutdown"}}'),
    ('duplicate_version', '{"version":1,"version":1,"message":{"type":"shutdown"}}'),
    ('unknown_envelope_field', '{"version":1,"message":{"type":"shutdown"},"typo":1}'),
    ('unknown_message_field', '{"version":1,"message":{"type":"shutdown","typo":1}}'),
    ('unknown_type', '{"version":1,"message":{"type":"pause"}}'),
    ('missing_type', '{"version":1,"message":{"job_id":"job-1"}}'),
    ('cancel_missing_job_id', '{"version":1,"message":{"type":"cancel"}}'),
    ('cancel_job_id_not_string', '{"version":1,"message":{"type":"cancel","job_id":7}}'),
    ('duplicate_job_id', '{"version":1,"message":{"type":"cancel","job_id":"a","job_id":"b"}}'),
    ('message_null', '{"version":1,"message":null}'),
    ('message_array', '{"version":1,"message":[]}'),
    ('not_json', 'not json'),
    ('trailing_garbage', SHUTDOWN + 'x'),
    ('byte_order_mark', '﻿' + SHUTDOWN),
    ('lone_surrogate', '{"version":1,"message":{"type":"cancel","job_id":"\\ud800"}}'),
    ('job_unknown_field', small_run().replace('"job_id":"j"', '"job_id":"j","repo":"x"')),
    ('job_missing_params', small_run().replace('"params":{},', '')),
    ('identity_unknown_field', small_run(job=SMALL_JOB.replace('"inputs":[]', '"inputs":[{"name":"a","path":"a","identity":{"state":"absent","digest":"x"}}]'))),
    ('identity_unknown_state', small_run(job=SMALL_JOB.replace('"inputs":[]', '"inputs":[{"name":"a","path":"a","identity":{"state":"stale"}}]'))),
    ('output_required_as_integer', small_run('{"path":"o.json","required":1}')),
    ('output_required_null', small_run('{"path":"o.json","required":null}')),
    ('output_unknown_field', small_run('{"path":"o.json","source":"x"}')),
    ('nan_parameter', small_run(job=SMALL_JOB.replace('"params":{}', '"params":{"x":NaN}'))),
    ('infinite_parameter', small_run(job=SMALL_JOB.replace('"params":{}', '"params":{"x":1e400}'))),
    ('nesting_depth_128', small_run(job=deep_job(deep_bad))),
]:
    add(name, 'request', frame(text), error='invalid')
# Positional (array) forms of the envelope, the message and every typed record, and duplicate keys
# anywhere, fail in both languages; serde alone would accept them.
INPUT = '{"name":"a","path":"a","identity":{"state":"absent"}}'
for name, kind, text in [
    ('positional_envelope', 'request', '[1,{"type":"shutdown"}]'),
    ('positional_message', 'request', '{"version":1,"message":["cancel","job-1"]}'),
    ('positional_job', 'request', '{"version":1,"message":{"type":"run","job":["j","u",{"kind":"k","version":"1"},'
                                  '"/jobs/j","s.py",["s.py"],[],{},[]]}}'),
    ('positional_op', 'request', small_run(job=SMALL_JOB.replace('{"kind":"k","version":"1"}', '["k","1"]'))),
    ('positional_input', 'request', small_run(job=SMALL_JOB.replace('"inputs":[]', '"inputs":[["a","a",{"state":"absent"}]]'))),
    ('positional_identity', 'request', small_run(job=SMALL_JOB.replace('"inputs":[]', '"inputs":[' + INPUT.replace('{"state":"absent"}', '["absent"]') + ']'))),
    ('positional_output', 'request', small_run('["o.json",null,true]')),
    ('duplicate_param_key', 'request', small_run(job=SMALL_JOB.replace('"params":{}', '"params":{"a":1,"a":2}'))),
    ('duplicate_identity_state', 'request', small_run(job=SMALL_JOB.replace('"inputs":[]', '"inputs":[' + INPUT.replace('{"state":"absent"}', '{"state":"absent","state":"absent"}') + ']'))),
    ('positional_failure', 'response', '{"version":1,"message":{"type":"failed","job_id":"j","failure":["job","m"]}}'),
    ('positional_completed_outputs', 'response', '{"version":1,"message":{"type":"completed","job_id":"j","outputs":[["a"]]}}'),
    ('positional_hello', 'response', '[1,{"type":"hello","worker_version":"fake-worker-1"}]'),
    ('duplicate_started_job_id', 'response', '{"version":1,"message":{"type":"started","job_id":"other","job_id":"j"}}'),
]:
    add(name, kind, frame(text), error='invalid')
# Arrays stay legitimate inside params, at any depth and of any element type.
add('arrays_inside_params_are_data', 'request',
    frame(small_run(job=SMALL_JOB.replace('"params":{}', '"params":{"m":[["k","1"],[{"a":[]}],[]]}'))),
    [{'type': 'run', 'job': {**small_expected([{'path': 'o.json', 'required': True}])['job'],
                             'params': {'m': [['k', '1'], [{'a': []}], []]}}}], canonical=True)
add('invalid_utf8', 'request', raw(b'{"version":1,"message":{"type":"cancel","job_id":"\xff"}}'), error='invalid')
add('zero_length', 'request', [{'hex': '00000000'}], error='invalid')
add('length_one_over_maximum', 'request', [head(MAX + 1)], error='invalid')
add('length_u32_max', 'request', [{'hex': 'ffffffff'}], error='invalid')

# Truncation fails as end of stream inside a frame.
shutdown = SHUTDOWN.encode()
add('truncated_header', 'request', [{'hex': '0000'}], error='truncated')
add('header_without_body', 'request', [head(len(shutdown))], error='truncated')
add('truncated_body', 'request', [head(len(shutdown)), {'hex': shutdown[:-1].hex()}], error='truncated')
add('frame_then_partial_header', 'request', frame(SHUTDOWN) + [{'hex': '00'}], [{'type': 'shutdown'}], error='truncated')

# Responses.
responses = [
    ('{"version":1,"message":{"type":"hello","worker_version":"fixture-1"}}', {'type': 'hello', 'worker_version': 'fixture-1'}),
    ('{"version":1,"message":{"type":"started","job_id":"job-1"}}', {'type': 'started', 'job_id': 'job-1'}),
    ('{"version":1,"message":{"type":"completed","job_id":"job-1","outputs":{"files":["arch.glb","ünï/côde.json"]}}}',
     {'type': 'completed', 'job_id': 'job-1', 'outputs': {'files': ['arch.glb', 'ünï/côde.json']}}),
]
for kind in ('job', 'dependency', 'protocol', 'crash', 'cancelled', 'timeout', 'guard_stop'):
    responses.append(('{"version":1,"message":{"type":"failed","job_id":"job-1","failure":{"kind":"%s","message":"m"}}}' % kind,
                      {'type': 'failed', 'job_id': 'job-1', 'failure': {'kind': kind, 'message': 'm'}}))
responses.append(('{"version":1,"message":{"type":"stopped"}}', {'type': 'stopped'}))
add('every_response_and_failure_kind', 'response', [c for text, _ in responses for c in frame(text)],
    [m for _, m in responses], canonical=True)
for name, text in [
    ('unknown_failure_kind', '{"version":1,"message":{"type":"failed","job_id":"j","failure":{"kind":"oops","message":"m"}}}'),
    ('stopped_unknown_field', '{"version":1,"message":{"type":"stopped","typo":1}}'),
    ('completed_missing_outputs', '{"version":1,"message":{"type":"completed","job_id":"j"}}'),
    ('completed_outputs_unknown_field', '{"version":1,"message":{"type":"completed","job_id":"j","outputs":{"files":[],"bytes":"AA=="}}}'),
    ('hello_null_version', '{"version":1,"message":{"type":"hello","worker_version":null}}'),
    ('request_is_not_a_response', SHUTDOWN),
]:
    add(name, 'response', frame(text), error='invalid')

document = {
    'about': 'Protocol v1 frames shared by tests/worker_session.rs and platform/studio/tests/test_build_v2_protocol.py. '
             'A vector concatenates its chunks (hex bytes or UTF-8 text). Reading frames of the given kind yields '
             'messages in order (opaque_messages more are only checked canonically, being too deep to embed); then the next read is a clean end (error null) or fails with the named error '
             '(invalid: Rust InvalidData, truncated: UnexpectedEof). Canonical vectors are also the exact bytes '
             'that both encoders write for those messages. reencoded, when present, is the exact text both encoders write for a non-canonical input. Regenerate with generate_protocol_v1.py.',
    'vectors': vectors,
}
json.dump(document, sys.stdout, ensure_ascii=False, indent=1)
sys.stdout.write('\n')
