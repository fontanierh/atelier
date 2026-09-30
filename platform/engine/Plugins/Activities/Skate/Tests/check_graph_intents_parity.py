#!/usr/bin/env python3
"""Exact typed graph conditions, intent operations and production sliding checks.

Compile only through atelier.safety. The oracle executes unchanged pinned core
and host modules; the sliding animation input is an explicit IntentMap provider.
"""
import argparse
from collections import Counter
import hashlib
import io
import json
from pathlib import Path
import random
import re
import shutil
import struct
import subprocess
import tarfile
from check_gesture_parity import converter, PLUGIN
from check_graph_parity import attribute, element, original_graph
from check_input_parity import Record, fbits, from_bits
from session_parity import REFERENCE_REVISION, digest


def attrs(writer, values):
    writer.word(len(values))
    for value in values:
        writer.raw(value['name'])
        writer.raw(value['text'])
        writer.words((value['float_bits'], value['boolean_byte']))


def numeric_attributes(rng, case, name='HasAGIntent'):
    values = [attribute('name', name), attribute('intent', 'shared'), attribute('abs', boolean=case % 4)]
    if case % 3 == 0:
        values.append(attribute('comparison', ('Equals', 'NotEqual', 'GreaterThan', 'LessThan', 'GreaterEqual', 'LessEqual', 'greater', '')[case % 8]))
        values.append(attribute('value', bits=fbits(rng.choice((-1., -.0, 0., .5, 1.)))))
    fields = ('equal', 'notEqual', 'greater', 'greaterThanAbs', 'less', 'greaterEqual', 'lessEqual')
    for index, field in enumerate(fields):
        if (case >> index) & 1:
            values.append(attribute(field, bits=fbits(rng.choice((-1., -.0, 0., .5, 1.)))))
    # Duplicate raw representations must preserve the first hashed key.
    if case % 5 == 0:
        values.append(attribute('value', bits=0x7fc12345))
    return values


def parameter_attributes(rng, case):
    values = [attribute('name', 'CreateMGIntentFromAGIntent')]
    names = ('MGIntent', 'MGIntentMag', 'MGIntentAngle', 'AGIntent', 'intent', 'filteredIntent')
    for index, name in enumerate(names):
        if (case+index) % 3:
            values.append(attribute(name, ('Shared', 'shared', 'Shared\0suffix', 'a'*36+'tail', '')[(case+index) % 5]))
    scalar_fields = ('value', 'defaultValue', 'scale', 'startingValue', 'blend', 'blendRising', 'blendFalling', 'blendOut', 'rampTime', 'clampVel', 'clampAcc')
    for index, name in enumerate(scalar_fields):
        if (case+index) % 4:
            values.append(attribute(name, 'raw-encoded-text', bits=fbits(rng.choice((-.0, 0., .01, .15, .5, 1., -1.))), boolean=(case+index) % 256))
    filters = ('none', 'negate', 'abs', 'oneMinus', 'clamp', 'angleFlip', 'angleRot90', 'angleRotN90', 'ANGLEFLIP', 'negate\0tail', '')
    for index, name in enumerate(('filter', 'filter1', 'filter2', 'fakieFilter', 'mirrorFilter', 'angleFilter')):
        if (case+index) % 3:
            values.append(attribute(name, filters[(case+index) % len(filters)]))
    for index, name in enumerate(('onUpdate', 'negateOnMirror')):
        if case % 3:
            values.append(attribute(name, 'ignored', boolean=(0, 1, 2, 255)[(case+index) % 4]))
    return values


def corpus():
    rng = random.Random(0x4752494e)
    parts, cases = [], []
    def add(op, kind, build):
        w = Record()
        w.word(op)
        build(w)
        cases.append(dict(command=len(cases), operation=op, kind=kind, input_bytes=len(w.data)))
        parts.append(bytes(w.data))
    levels = (-1., -.9, -.5, -0., 0., .25, .5, .9, 1., from_bits(0x7fc12345))
    for case in range(1024):
        def build(w, case=case):
            attrs(w, numeric_attributes(rng, case))
            w.word(len(levels))
            w.scalars(levels)
        add(0, 'numeric constructor precedence and unordered branches', build)
    for case in range(1024):
        add(1, 'typed action/filter constructor fields and aliases', lambda w, case=case: attrs(w, parameter_attributes(rng, case)))
    for case in range(128):
        def build(w, case=case):
            w.scalar(rng.choice(levels))
            w.word(case % 2)
            w.scalar(rng.choice(levels))
            w.word(128)
            angles = (0., -0., -3.14, 3.14, -2.4, 2.4, -.2, .2, from_bits(0x7fc12345))
            for tick in range(128):
                w.word((0, 1, 1, 1, 2)[tick % 5])
                w.optional(None if tick % 5 == 0 else rng.choice(levels))
                w.scalar((0., 1/60, 1/120, .1)[tick % 4])
                w.optional(None if tick % 19 == 0 else rng.choice(levels))
                w.optional(None if tick % 23 == 0 else angles[tick % len(angles)])
                w.words((tick % 11, case % 2, tick % 2))
        add(2, 'constant/time lifecycle and raw-angle seam owner', build)
    for case in range(128):
        def build(w, case=case):
            values = parameter_attributes(rng, case)
            attrs(w, values)
            names = ('Shared', 'shared', 'Shared\0suffix', 'a'*36+'tail', '')
            w.word(len(names))
            for name in names:
                w.raw(name)
            w.word(128)
            for tick in range(128):
                w.word((0, 1, 1, 1, 2)[tick % 5])
                w.optional(None if tick % 7 == 0 else rng.choice(levels))
                w.scalar((0., -0., 1/60, .1)[tick % 4])
                w.word(tick % 13 != 0)
                if tick % 13 != 0:
                    w.word((tick % 4) << 29)
        add(3, 'motion filter live map/stance and removal aliases', build)
    condition_names = ('HasAGIntent', 'TimeSinceLastInput', 'PhysicsSpeedCompare', 'PhysicsSpeedAndSlopeCompare',
                       'PhysFilteredState', 'IsGrinding', 'IsMirrored', 'IsRidingFakie', 'DisablePushBrake', 'CurrentState')
    for case in range(4096):
        def build(w, case=case):
            name = condition_names[case % len(condition_names)]
            values = numeric_attributes(rng, case, name)
            values.extend((attribute('state', ('invalid', 'ground', 'air', 'grind', 'wipeout', 'teleport', 'offboard', 'offboardair')[case % 8]),
                           attribute('grindName', ('FiftyFifty', 'fiftyfifty', 'a'*31, 'a'*36)[case % 4]),
                           attribute('alongSkateZ', boolean=case % 3)))
            attrs(w, values)
            w.words((case % 9, case % 2))
            w.raw(('FiftyFifty', 'fiftyfifty', 'a'*31, 'a'*36)[case % 4])
            w.scalars([rng.choice(levels) for _ in range(4)])
            w.words((case % 2, (case//2) % 2))
            w.scalar(rng.choice(levels))
            w.word(case % 7 == 0)
            w.scalar(rng.choice((0., 45., 89., 90., 100.)))
            w.word(case % 64)
            w.word(case % 3)
            for i in range(case % 3):
                w.raw(('shared', 'SHARED')[i])
                w.scalar(rng.choice(levels))
            w.word(6)
            w.words((0xffffffff, 0, 1, 1, 2, 3))
            w.words((0xffffffff if case % 9 == 0 else case % 6,
                     0xffffffff if case % 7 == 0 else (case//5) % 6))
        add(4, 'typed physical conditions and explicit missing producers', build)
    for case in range(64):
        def build(w, case=case):
            w.words([rng.getrandbits(32) for _ in range(5)])
            w.scalar(rng.choice(levels))
            w.word(192)
            for tick in range(192):
                w.word(1 if tick % 19 < 15 else tick % 7)
                w.scalars((rng.choice(levels)*10, rng.choice(levels), (0., 1/60, .1)[tick % 3]))
                for i in range(4):
                    w.optional(None if (tick+i) % 9 == 0 else rng.choice(levels))
                w.scalars([rng.choice(levels) for _ in range(8)])
                w.word(tick % 2)
                for row in range(4):
                    w.scalars([float(row == column) for column in range(4)])
        add(5, 'actual host sliding state/CreateSlide/direction/decel/spin', build)
    attribute_names = ('Shared', 'shared', 'Shared\0tail', 'a'*30, 'a'*30+'tail', 'équipement', '')
    for case in range(2048):
        def build(w, case=case):
            name = ('HasAnimAttribute', 'PhysicsRequestsDismount', 'IsLandingOnBoard')[case % 3]
            values = numeric_attributes(rng, case, name)
            values.append(attribute('attribute', attribute_names[case % len(attribute_names)]))
            if case % 5:
                values.append(attribute('sequenceid', bits=(fbits(-1.), fbits(0.), fbits(1.), fbits(2.), 0x7fc12345, 0x7f800000, 0xff800000, 0x4f000000)[case % 8]))
            attrs(w, values)
            w.word(case % 5)
            for index in range(case % 5):
                w.raw(attribute_names[(case+index//2) % len(attribute_names)])
                w.words(((case+index) % 5-1 & 0xffffffff, (case+index) % 6))
                for lane in range(6):
                    initialized = (case+index+lane) % 4 != 0
                    w.word(initialized)
                    if initialized:
                        w.word(fbits(rng.choice(levels)))
            present = case % 7 != 0
            w.word(present)
            if present:
                w.words((case % 2, (0, 1, 503, 500, 504)[case % 5]))
        add(7, 'actual ActionHost first attribute/sequence/kind and physical producer diagnostics', build)
    offset = 4
    for case in cases:
        case['input_offset'] = offset
        offset += case['input_bytes']
    return struct.pack('<I', len(parts))+b''.join(parts), cases


def host_fixture(case):
    def behavior(name, extra):
        return element('behaviour', name, extra)
    def condition(name, extra=()):
        return element('condition', name, [attribute('mask', 'always'), *extra])
    shared = 'Shared' if case % 2 else 'shared'
    base = [behavior('CreateConstMGIntent', [attribute('MGIntent', 'Const'), attribute('value', bits=fbits((case+1)*.125)), attribute('onUpdate', boolean=case % 2)]),
            behavior('CreateMGIntentFromAGIntent', [attribute('MGIntent', shared), attribute('AGIntent', 'push'), attribute('filter', 'negate'), attribute('onUpdate', boolean=case % 2)]),
            behavior('CreateMGIntentFromAGIntent', [attribute('MGIntent', shared.upper()), attribute('AGIntent', 'other'), attribute('scale', bits=0x3f000000)]),
            behavior('CreateMGTimeIntentFromAGIntent', [attribute('MGIntent', 'Clock'), attribute('AGIntent', 'push')]),
            behavior('BoardAdjust', [attribute('MGIntentMag', 'BoardMag'), attribute('MGIntentAngle', 'BoardAngle'), attribute('angleFilter', ('none', 'angleFlip')[case % 2])]),
            behavior('BodyFlippingSignal', []), behavior('JuiceHook', [])]
    gated = element('state', 'active', children=[
        element('expression', attributes=[attribute('op', 'and')], children=[condition('HasAGIntent', [attribute('intent', 'enable')]), condition('CurrentState', [attribute('state', 'root')])]),
        behavior('CreateMGTimeIntentFromAGIntent', [attribute('MGIntent', 'ChildClock'), attribute('AGIntent', 'push')]),
        element('transition', attributes=[attribute('target', 'idle'), attribute('priority', 'urgent')], children=[element('expression', attributes=[attribute('op', 'and')], children=[condition('HasAGIntent', [attribute('intent', 'exit')]), condition('InParentStateForTime', [attribute('greaterEqual', bits=0)])])])])
    # Native selection returns None if every child fails activation. This leaf
    # lets the first frame select a state before CurrentState(root) can pass.
    return element('state', 'root', children=base+[gated, element('state', 'idle')])


def host_other_value(case, tick):
    # The second writer wins the encoded Shared alias collision. Vary its
    # actual source value rather than the earlier writer it overwrites.
    return ((tick+case) % 11-5)*.125


def host_corpus(case):
    rng = random.Random(0x484f5354+case)
    w = Record()
    w.words((1, 6))
    names = ('shared', 'SHARED', 'Const', 'Clock', 'ChildClock', 'BoardMag', 'BoardAngle', 'FrontFlip', 'BackFlip', '')
    w.word(len(names))
    for name in names:
        w.raw(name)
    w.word(256)
    for tick in range(256):
        w.word(tick in (127, 255))
        w.scalar((0., -0., 1/60, .1)[tick % 4])
        values = []
        if tick % 19 < 15:
            values.append(('push', rng.choice((0., 1., -.5))))
        if tick % 7:
            values.append(('other', host_other_value(case, tick)))
        if tick % 23 < 16:
            values.append(('enable', 0.))
        if tick % 31 == 0:
            values.append(('exit', 1.))
        if tick % 11:
            values.extend((('BoardAdjustMag', .9), ('BoardAdjustAngle', (-3.14, 3.14, .2, -.2)[tick % 4])))
        if tick % 17 == 0:
            values.extend((('FrontFlip', 0.), ('BackFlip', 1.)) if (tick//17) % 3 == 0 else [(('FrontFlip', 'BackFlip')[(tick//17) % 2], 0.)])
        # Publish both-key precedence and BackFlip-only on alternating first
        # air frames with positive dt. A ground gesture may expire before air.
        if tick % 20 == 10:
            values.extend((('FrontFlip', 0.), ('BackFlip', 1.)) if (tick//20) % 2 == 0 else [('BackFlip', 0.)])
        w.word(len(values))
        for name, value in values:
            w.raw(name)
            w.scalar(value)
        w.word(tick % 5)
        w.word((tick//5) % 4)
        w.optional(None if tick % 7 == 0 else tick/60)
    return bytes(w.data)


def state_time_corpus():
    w = Record()
    w.words((1, 8, 256))
    times = (None, -.1, -0., 0., .1, from_bits(0x7fc12345), float('inf'), -float('inf'))
    for case in range(256):
        w.word((0xffffffff, 0, 1, 2)[case % 4])
        w.word(case % 5)
        for index in range(case % 5):
            w.optional(times[(case+index) % len(times)])
    return bytes(w.data)


def build_probes(output, target_dir):
    native = PLUGIN/'Source/AtelierSkate/Private/Native'
    cpp = output/'graph-intents-cpp'
    sources = ('NativeMath', 'AnimationName', 'Intents', 'Input', 'InputIntentions', 'NameId', 'Settings',
               'Graph', 'CompiledGraph', 'GraphController', 'GraphConditions', 'GraphGestureOperations', 'GraphIntentOperations', 'GraphMotionSliding')
    subprocess.run(['clang++', '-std=c++17', '-O2', '-ffp-contract=off', '-fno-fast-math', '-Wall', '-Wextra', '-Werror',
                    '-I', str(native), *(str(native/f'{name}.cpp') for name in sources), str(PLUGIN/'Tests/Native/graph_intents_probe.cpp'), '-o', str(cpp)], check=True)
    root = Path(subprocess.check_output(['git', 'rev-parse', '--show-toplevel'], cwd=PLUGIN, text=True).strip())
    relative = (PLUGIN/'ThirdParty/skate-runtime').relative_to(root).as_posix()
    revision = subprocess.check_output(['git', 'rev-parse', REFERENCE_REVISION], cwd=root, text=True).strip()
    archive = subprocess.check_output(['git', 'archive', f'{revision}:{relative}'], cwd=root)
    source = output/'reference-source'
    source.mkdir(parents=True, exist_ok=True)
    with tarfile.open(fileobj=io.BytesIO(archive)) as stream:
        stream.extractall(source, filter='data')
    originals = {p.relative_to(source).as_posix(): digest(p) for p in sorted(source.rglob('*.rs')) if p.name != 'migration_probe.rs'}
    crate = source/'atelier-host'
    # Plain `mod physics` must resolve physics.rs and its physics/ children in
    # the same Rust module layout. Stage verbatim modules, not rewritten paths.
    host_source = source/'crates/skate-host/src'
    staged = {}
    for original in sorted(host_source.rglob('*.rs')):
        if original.relative_to(host_source).as_posix() in ('lib.rs', 'main.rs'):
            continue
        relative = original.relative_to(host_source)
        destination = crate/'src'/relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(original, destination)
        expected = digest(original)
        if digest(destination) != expected:
            raise AssertionError(f'Staged module changed: {relative}')
        staged[relative.as_posix()] = expected
    cargo = crate/'Cargo.toml'
    cargo.write_text(cargo.read_text()+'\nskate-core={path="../crates/skate-core"}\nskate-data={path="../crates/skate-data"}\nskate-net={path="../crates/skate-net"}\nhalf="2.7.1"\nbevy={version="0.19",default-features=false,features=["std","multi_threaded","bevy_log"]}\n\n[[bin]]\nname="graph-intents-reference"\npath="src/migration_probe.rs"\n')
    probe = PLUGIN/'Tests/Reference/graph_intents_probe.rs'
    shutil.copyfile(probe, crate/'src/migration_probe.rs')
    subprocess.run(['cargo', '+1.97.1', 'build', '--release', '--offline', '--jobs', '2', '--manifest-path', str(cargo),
                    '--target-dir', str(target_dir.resolve()), '--bin', 'graph-intents-reference'], check=True)
    for relative, expected in originals.items():
        if digest(source/relative) != expected:
            raise AssertionError(f'Reference implementation changed: {relative}')
    for relative, expected in staged.items():
        if digest(crate/'src'/relative) != expected:
            raise AssertionError(f'Staged reference implementation changed: {relative}')
    rust = output/'graph-intents-reference'
    shutil.copy2(target_dir.resolve()/'release/graph-intents-reference', rust)
    provenance = dict(reference_revision=revision, source_archive_sha256=hashlib.sha256(archive).hexdigest(), original_source_sha256=originals, staged_host_modules_sha256=staged,
                      probe_sha256=digest(probe), binary_sha256=digest(rust), cargo_lock_sha256=digest(crate/'Cargo.lock'),
                      compiler=subprocess.check_output(['rustc', '+1.97.1', '-vV'], text=True).strip())
    (output/'reference-provenance.json').write_text(json.dumps(provenance, indent=2)+'\n')
    return cpp, rust


class TraceReader:
    def __init__(self, data):
        self.data, self.at = data, 0

    def word(self):
        value, = struct.unpack_from('<I', self.data, self.at)
        self.at += 4
        return value

    def optional(self):
        return self.word() if self.word() else None

    def text(self):
        size = self.word()
        value = self.data[self.at:self.at+size].decode()
        self.at += size
        return value

    def finished(self):
        assert self.at == len(self.data), (self.at, len(self.data))


def host_coverage(data, case):
    reader = TraceReader(data)
    assert reader.word() == 6
    names = ('shared', 'SHARED', 'Const', 'Clock', 'ChildClock', 'BoardMag', 'BoardAngle', 'FrontFlip', 'BackFlip', '')
    frames = []
    for tick in range(256):
        frame = dict(tick=tick, dt_bits=reader.word(), current=reader.word(), last=reader.word())
        frame['state_times_bits'] = [reader.optional() for _ in range(reader.word())]
        frame['active'] = [(reader.word(), reader.word()) for _ in range(reader.word())]
        frame['map_size'] = reader.word()
        frame['intents_bits'] = {name: reader.optional() for name in names}
        frame['error'] = reader.text()
        frames.append(frame)
    reader.finished()
    states = {frame['current'] for frame in frames}
    assert {1, 2} <= states, f'No active/idle state selection: {states}'
    assert all(not frame['error'] for frame in frames), 'Unexpected host diagnostics'
    assert max(len(frame['active']) for frame in frames) == 8, 'Child behavior never became active'
    assert len({instance for frame in frames for _, instance in frame['active']}) > 8, 'No behavior reallocation'
    emissions = {name: sum(frame['intents_bits'][name] is not None for frame in frames) for name in names}
    assert all(emissions[name] > 0 for name in names if name), f'Fixture has unexercised emissions: {emissions}'
    transitions = sum(a['current'] != b['current'] for a, b in zip(frames, frames[1:]))
    assert transitions >= 8, f'Insufficient active/idle transitions: {transitions}'
    for tick in (127, 255):
        frame = frames[tick]
        assert not frame['active'], 'EndAllBehaviors left active instances'
        assert all(frame['intents_bits'][name] is None for name in ('Const', 'Clock', 'ChildClock', 'BoardMag', 'BoardAngle')), 'EndAllBehaviors failed owned intent removal'
    assert any(frame['intents_bits']['Clock'] not in (None, 0) for frame in frames), 'Clock never accumulated'
    shared_values = {frame['intents_bits']['shared'] for frame in frames if frame['intents_bits']['shared'] is not None}
    assert len(shared_values) >= 8, 'Authored numeric input never propagated through the winning alias writer'
    for frame in frames:
        shared = frame['intents_bits']['shared']
        if shared is not None:
            assert frame['tick'] % 7 and shared == fbits(host_other_value(case, frame['tick'])*.5), 'Shared alias winner did not publish the scaled current input'
        constant = frame['intents_bits']['Const']
        if constant is not None:
            assert constant == fbits((case+1)*.125), 'Case-specific authored constant did not propagate'
    return dict(states=sorted(states), transitions=transitions, emissions=emissions,
                distinct_shared_values=len(shared_values), authored_constant_bits=fbits((case+1)*.125),
                distinct_instances=len({instance for frame in frames for _, instance in frame['active']}),
                nonempty_maps=sum(frame['map_size'] != 0 for frame in frames), end_all_frames=[127, 255]), frames


def bound_condition_coverage(data):
    reader = TraceReader(data)
    assert reader.word() == 8
    observed = [set() for _ in range(4)]
    for _ in range(256):
        assert reader.word() == 4
        for values in observed:
            values.add(reader.word())
        assert reader.text() == ''
    reader.finished()
    assert observed[1] == {0, 1}, 'Bound CurrentState did not evaluate true and false'
    assert observed[3] == {0, 1}, 'Bound parent time did not evaluate true and false'
    return dict(condition_truth_values=[sorted(values) for values in observed])


def compare(output, name, cpp, rust, actual_args, expected_args, inputs=b'', coverage=None, host_case=None):
    expected = subprocess.check_output([str(rust), *map(str, expected_args)], input=inputs)
    actual = subprocess.check_output([str(cpp), *map(str, actual_args)], input=inputs)
    if actual != expected:
        (output/f'{name}-reference.bin').write_bytes(expected)
        (output/f'{name}-cpp.bin').write_bytes(actual)
        first = next((i for i, (a, b) in enumerate(zip(actual, expected)) if a != b), min(len(actual), len(expected)))
        report = dict(passed=False, name=name, first_byte=first, reference_length=len(expected), cpp_length=len(actual),
                      reference_hex=expected[max(0, first-16):first+32].hex(), cpp_hex=actual[max(0, first-16):first+32].hex())
        (output/'first-divergence.json').write_text(json.dumps(report, indent=2)+'\n')
        raise AssertionError(report)
    result = dict(name=name, output_bytes=len(expected), output_sha256=hashlib.sha256(expected).hexdigest())
    if coverage is host_coverage:
        result['coverage'], frames = coverage(expected, host_case)
        (output/f'{name}-original-trace.json').write_text(json.dumps(frames, indent=2)+'\n')
    elif coverage:
        result['coverage'] = coverage(expected)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--assets', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--target-dir', type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    cpp, rust = build_probes(output, args.target_dir)
    settings = output/'settings.native'
    settings.write_bytes(converter.encode_settings(args.assets/'private/stock/skater-collections.json'))
    inputs, cases = corpus()
    (output/'input.bin').write_bytes(inputs)
    (output/'cases.json').write_text(json.dumps(cases, indent=2)+'\n')
    results = [compare(output, 'subsystems', cpp, rust, ['stream', settings, args.assets], ['stream', settings, args.assets], inputs)]
    for case in range(12):
        reference = output/f'host-{case}.reference-graph'
        reference.write_bytes(original_graph(host_fixture(case)))
        native = output/f'host-{case}.graph'
        native.write_bytes(converter.encode_graph(converter.read_graph(reference)))
        results.append(compare(output, f'host-{case}-config', cpp, rust, ['config', native, args.assets], ['config', reference, args.assets]))
        inputs = host_corpus(case)
        (output/f'host-{case}-input.bin').write_bytes(inputs)
        results.append(compare(output, f'host-{case}', cpp, rust, ['stream', settings, args.assets, native], ['stream', settings, args.assets, reference], inputs, coverage=host_coverage, host_case=case))
        inputs = state_time_corpus()
        (output/f'host-{case}-state-time-input.bin').write_bytes(inputs)
        results.append(compare(output, f'host-{case}-state-time', cpp, rust, ['stream', settings, args.assets, native], ['stream', settings, args.assets, reference], inputs, coverage=bound_condition_coverage))
    host_hashes = {result['output_sha256'] for result in results if re.fullmatch(r'host-\d+', result['name'])}
    assert len(host_hashes) >= 4, 'Case-specific input/constructor variants did not produce distinct host traces'
    authored = args.assets/'private/stock/data/state/ActionGraph_OnBoard.stategraph'
    native = output/'authored-action.graph'
    native.write_bytes(converter.encode_graph(converter.read_graph(authored)))
    results.append(compare(output, 'authored-action-parameters', cpp, rust, ['config', native, args.assets], ['config', authored, args.assets]))
    report = dict(passed=True, commands=len(cases), operations=dict(Counter(case['operation'] for case in cases)),
                  host_fixtures=12, host_ticks=12*256, bound_condition_frames=12*256, results=results,
                  comparison='exact typed constructors, conditions, intent mutation/map lifecycle, controller host state, production sliding outputs; no tolerance',
                  limitations='Unported action/motion/gesture leaves retain explicit diagnostics. Whole session scheduling and offboard camera remap remain unported.',
                  reference_provenance='reference-provenance.json')
    (output/'result.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(report, indent=2), flush=True)


if __name__ == '__main__':
    main()
