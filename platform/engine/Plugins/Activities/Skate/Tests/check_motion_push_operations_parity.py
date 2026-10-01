#!/usr/bin/env python3
"""Bounded full original MotionHost push phase, lifecycle and attribute parity.

Only the parent runs builds/probes under atelier.safety. This exercises original
host factories and phase callbacks; complete controller registration is separate.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import struct
import subprocess
from check_gesture_parity import converter
from check_graph_parity import attribute, element, original_graph
from check_input_parity import Record, fbits, from_bits
from check_animation_trees_parity import converter as metadata_converter, name
from check_motion_animation_parity import validate_fixture_attributes
from motion_reference_build import build_probes

PROOFS = ('PUSH_PROOF_0', 'PUSH_PROOF_1', 'PUSH_PROOF_2', 'PUSH_PROOF_3', 'PUSH_PROOF_4')


def fixture():
    configs, groups = [], {}
    def add(n, attrs=()):
        groups.setdefault(n, []).append(len(configs))
        configs.append(element('behaviour', n, attrs))
    add('InitPush')
    add('ComputeFirstPushStrength')
    for regular in (0, 1):
        add('ComputeTargetCoefsFromSpeedAndStrength', [attribute('regularAttributes', boolean=regular)])
        add('ComputeRepushDeadline', [attribute('regularAttributes', boolean=regular)])
    for first in (0, 1):
        add('SetPushCoefs', [attribute('onFirstUpdateOnly', boolean=first)])
    for foot in ('LeftPush', 'RightPush'):
        add('PushCycle', [attribute('newPushName', foot)])
    for right in (0, 1):
        add('PushOut', [attribute('isRightFoot', boolean=right)])
    return element('state', 'root', children=configs), configs, groups


def fixture_metadata():
    data = dict(version=1, source_bank='PushFixture.abin', source_sha256='c'*64, source_bytes=1000000,
        clips=[], phase_blends=[], blend_spaces=[], selectors=[], selection_spaces=[], unsupported_trees=[])
    for i, param in enumerate(('HSTR_VEL_B', 'LSTR_VEL_B', 'VEL_E', 'OUTDISTANCEX', 'OUTDISTANCEY')):
        tree = f'PUSH_OBSERVER_{i}'
        children = []
        for j, v in enumerate((0., 1.) if i < 3 else (-100., 100.)):
            child = f'{tree}_{j}'
            children.append(child)
            offset = 48 + len(data['clips'])*4096
            pairs = sorted(((param, v), (PROOFS[i], v)), key=lambda item: tuple(name(item[0])))
            attrs = [dict(name=n, type_id=0, begin_bits=fbits(-1), end_bits=fbits(-1), payload_words=[fbits(value)], source_offset=offset+128+k*128) for k, (n, value) in enumerate(pairs)]
            data['clips'].append(dict(name=child, source_offset=offset, fps_bits=fbits(30), frames_bits=fbits(61), base_speed_bits=fbits(1), flags_word=0x10000000, attributes=attrs))
        data['phase_blends'].append(dict(name=tree, source_offset=100000+i*4096, parameter=param, children=children))
    validate_fixture_attributes(data)
    return data


def corpus(configs, groups):
    rows = []
    def add(index, phase, *, allocate=None, mode=0, physical=1, switch=0, speed=3., teleport=100., dt=1/60, intents=None, seed=None, flip=0, feet=None):
        if allocate is None:
            allocate = phase == 0
        rows.append(dict(index=index, phase=phase, allocate=int(allocate), mode=mode, physical=physical, switch=switch, speed=speed, teleport=teleport, dt=dt,
            intents=intents or {}, seed=seed, flip=flip, feet=feet or [[1., .2, 2., 1.], [-2., .3, -3., 1.], [.5, .1, -.5, 1.], [0., 1., 0., 0.], [0., 0., 1., 0.]]))
    # All phases, both missing-owner diagnostics and valid no-op phases.
    for i in range(len(configs)):
        for physical, mode in ((0, 1), (1, 2), (1, 1)):
            for phase in range(3):
                add(i, phase, physical=physical, mode=mode, intents={'Pushing': .2, 'LeftPush': 0.})
    # Init must preserve the actual prior out factor while replacing other data.
    add(groups['InitPush'][0], 0, mode=3, seed=[.75, 2., .2, .3, .4, .8, .7, .6, 1])
    init, strength = groups['InitPush'][0], groups['ComputeFirstPushStrength'][0]
    speeds = (-1., 0., 1., 3., 6., 12., from_bits(0x7fc12345), float('inf'))
    # Held/released/repressed first push, and old-time teleport simulation.
    for teleport in (0., 100.):
        add(init, 0, mode=1)
        add(strength, 0, teleport=teleport, intents={'Pushing': 0.})
        for frame, held in enumerate((0., .01, .05, .2, .5, None, .8, None)):
            add(strength, 1, teleport=100.-frame, speed=speeds[frame], dt=(0., .01, .05)[frame%3], intents={} if held is None else {'Pushing': held})
    # Shared current/target numeric values include sentinel and finite remaps.
    for regular in (0, 1):
        target = groups['ComputeTargetCoefsFromSpeedAndStrength'][regular]
        deadline = groups['ComputeRepushDeadline'][regular]
        for switch in (0, 1):
            for i, speed in enumerate(speeds):
                add(target, 1, mode=3, seed=[.5, (i%4)*.4, -.1, -.2, -1., 0., 0., 0., 0], switch=switch, speed=speed)
                add(deadline, 2, switch=switch, speed=speed)
                add(groups['SetPushCoefs'][0], 0, switch=switch, speed=speed)
                add(groups['SetPushCoefs'][0], 1, switch=switch, speed=speed)
    for index in groups['SetPushCoefs']:
        for dt in (0., .01, .05, .25):
            add(index, 0, mode=3, dt=dt, seed=[0., 0., .1, .9, .2, .8, .3, .7, 0])
            for _ in range(3):
                add(index, 1, dt=dt)
            add(index, 2, dt=dt)
        # Fresh allocation without Begin tests onFirstUpdateOnly=false state.
        add(index, 1, allocate=True, mode=3, seed=[0., 0., .1, .9, .2, .8, .3, .7, 0])
    # Separate checks allow release+new press in the same source update.
    for index, foot in zip(groups['PushCycle'], ('LeftPush', 'RightPush')):
        for held_at_begin in (False, True):
            add(init, 0, mode=1)
            add(index, 0, intents={'Pushing': .1, foot: 0.} if held_at_begin else {})
            maps = ({'Pushing': .2, foot: 0.}, {'Pushing': 2., foot: 0.}, {'NewPush': 0., foot: 0.},
                {'Pushing': .1, 'NewPush': 0., foot: 0.}, {'Pushing': .3, foot: 0.}, {'Pushing': .5}, {}, {'NewPush': 0., foot: 0.})
            for i, intents in enumerate(maps):
                add(index, 1, speed=speeds[i], intents=intents)
            add(index, 2)
        add(index, 1, allocate=True, mode=1)
    add(strength, 1, allocate=True, mode=1)
    for index in groups['PushOut']:
        add(index, 0, physical=1, mode=1)
        for flip in (0, 1):
            for scale in (.25, 1., 3.):
                feet = [[scale, .2*scale, 2.*scale, 1.], [-2.*scale, .3*scale, -3.*scale, 1.], [.5, .1, -.5, 1.], [.1, .9, .2, 0.], [-.2, .1, .95, 0.]]
                add(index, 0, physical=2, flip=flip, feet=feet)
    w = Record()
    w.word(len(rows))
    for row in rows:
        w.words(row[k] for k in ('index', 'phase', 'allocate', 'mode', 'physical', 'switch'))
        for k in ('speed', 'teleport', 'dt'):
            w.scalar(row[k])
        if row['mode'] == 3:
            for v in row['seed'][:8]:
                w.scalar(v)
            w.word(row['seed'][8])
        if row['physical'] == 2:
            for vector in row['feet']:
                for v in vector:
                    w.scalar(v)
            w.word(row['flip'])
        w.word(len(row['intents']))
        for n, v in row['intents'].items():
            w.raw(n)
            w.scalar(v)
    return bytes(w.data), rows


def coverage(data, rows, groups, trace_path):
    at = 0
    def word():
        nonlocal at
        v, = struct.unpack_from('<I', data, at)
        at += 4
        return v
    def string():
        nonlocal at
        n = word()
        s = data[at:at+n].decode()
        at += n
        return s
    assert word() == len(rows)
    traces, effects, phases = [], Counter(), {}
    for row in rows:
        error = string()
        statuses = [(word(), string()) for _ in range(3)]
        assert statuses == [(1, ''), (1, ''), (1, '')], (row, statuses)
        state = [word() for _ in range(8)] + [word()] if word() else None
        attrs = []
        for _ in range(word()):
            n = tuple(word() for _ in range(5))
            kind, status, sequence, begin, end = [word() for _ in range(5)]
            payload = [word() if word() else None for _ in range(6)]
            attrs.append(dict(name=n, kind=kind, status=status, sequence=sequence, begin=begin, end=end, payload=payload))
        operation = next(n for n, ids in groups.items() if row['index'] in ids)
        phases.setdefault(operation, set()).add(row['phase'])
        if error:
            effects['diagnostics'] += 1
        if state is not None:
            effects['shared'] += 1
            effects['continue_true' if state[-1] else 'continue_false'] += 1
        traces.append(dict(row=row, operation=operation, error=error, state=state, attrs=attrs))
    assert at == len(data)
    trace_path.write_text(json.dumps(traces, indent=2)+'\n')
    assert all(v == {0, 1, 2} for v in phases.values())
    assert all(effects[k] > 0 for k in ('diagnostics', 'shared', 'continue_true', 'continue_false')), effects
    for n in ('Push behavior requires actual skater physical outputs', 'Native push state initialization has not been published', 'ComputeFirstPushStrength updated before Begin', 'PushCycle updated before Begin'):
        assert any(n in t['error'] for t in traces), n
    for proof in PROOFS:
        values = {a['payload'][0] for t in traces for a in t['attrs'] if a['name'] == tuple(name(proof))}
        assert len(values) >= 3, (proof, values)
        effects[proof] = len(values)
    initialized = [t for t in traces if t['operation'] == 'InitPush' and t['row']['mode'] == 3]
    assert len(initialized) == 1
    assert initialized[0]['state'] == [fbits(.75), fbits(0), *[fbits(-1)]*6, 0], initialized
    for first in groups['SetPushCoefs']:
        selected = [t for t in traces if t['row']['index'] == first and t['row']['phase'] == 1 and t['row']['mode'] == 0 and t['row']['dt'] == .01]
        assert len(selected) == 3
        assert (selected[0]['state'] == selected[1]['state']) == (first == groups['SetPushCoefs'][1]), selected
    for n in ('ComputeFirstPushStrength', 'ComputeTargetCoefsFromSpeedAndStrength', 'ComputeRepushDeadline', 'PushCycle'):
        states = {tuple(t['state']) for t in traces if t['operation'] == n and not t['error'] and t['state']}
        assert len(states) >= 3, (n, states)
    return dict(commands=len(rows), operation_names=len(phases), phases={k:sorted(v) for k,v in phases.items()}, observable_effects=dict(effects))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for n in ('assets', 'metadata', 'output', 'target-dir'):
        p.add_argument('--'+n, type=Path, required=True)
    args = p.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    for marker in ('result.json', 'first-divergence.json'):
        (output/marker).unlink(missing_ok=True)
    sources = ('NativeMath', 'AnimationName', 'Intents', 'Input', 'InputIntentions', 'NameId', 'Settings', 'Graph', 'GraphController', 'GraphConditions', 'GraphGestureOperations',
        'AnimationSamples', 'AnimationMetadata', 'AnimationPlayback', 'AnimationPlaybackParameters', 'AnimationTrees', 'AnimationChannels', 'MotionAnimation', 'MotionFrame', 'GraphMotionPushOperations')
    cpp, rust = build_probes(output, args.target_dir, 'motion_push_operations', sources)
    graph, configs, groups = fixture()
    reference, native = output/'operations.reference-graph', output/'operations.graph'
    reference.write_bytes(original_graph(graph))
    native.write_bytes(converter.encode_graph(converter.read_graph(reference)))
    metadata = fixture_metadata()
    metadata_json, metadata_native = output/'fixture.json', output/'fixture.skate'
    metadata_json.write_text(json.dumps(metadata))
    metadata_native.write_bytes(metadata_converter.pack_metadata(metadata))
    settings = output/'settings.native'
    settings.write_bytes(converter.encode_settings(args.assets/'private/stock/skater-collections.json'))
    inputs, rows = corpus(configs, groups)
    (output/'input.bin').write_bytes(inputs)
    (output/'authored-commands.json').write_text(json.dumps(rows, indent=2)+'\n')
    expected = subprocess.check_output([str(rust), str(args.assets), str(reference), str(metadata_json)], input=inputs)
    actual = subprocess.check_output([str(cpp), str(args.metadata/'bank-0.skate'), str(args.metadata/'bank-1.skate'), str(metadata_native), str(native), str(settings)], input=inputs)
    (output/'reference.bin').write_bytes(expected)
    (output/'cpp.bin').write_bytes(actual)
    if actual != expected:
        first = next((i for i,(a,b) in enumerate(zip(actual, expected)) if a != b), min(len(actual),len(expected)))
        report = dict(passed=False, first_byte=first, reference_length=len(expected), cpp_length=len(actual), reference_hex=expected[max(0,first-16):first+32].hex(), cpp_hex=actual[max(0,first-16):first+32].hex())
        (output/'first-divergence.json').write_text(json.dumps(report, indent=2)+'\n')
        raise AssertionError(report)
    result = coverage(expected, rows, groups, output/'original-trace.json')
    report = dict(passed=True, authored_configs=len(configs), output_bytes=len(expected), output_sha256=hashlib.sha256(expected).hexdigest(), coverage=result,
        comparison='exact full pinned MotionHost push factories/phases, real stock settings/clip metrics, allocation/lifecycle/shared state, teleport timing, both footnames/switch branches, normalized coefficients and actual applied foot-distance observer channels',
        limitations='Full controller registration and physical producers are separate. Exhaustive malformed settings/metadata parser diagnostics are not covered.', reference_provenance='reference-provenance.json')
    (output/'result.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(report, indent=2), flush=True)


if __name__ == '__main__':
    main()
