#!/usr/bin/env python3
"""Exact original seven-recognizer manager/listener/action publication checks.

Run through atelier.safety. The frozen original host owns all expected outcomes;
corpus construction uses authored PAT points and supplies physical/AG inputs.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import random
import struct
import subprocess
from check_gesture_parity import converter, PLUGIN
from check_input_parity import Record, from_bits
from reference_build import build_probe


def corpus(sets):
    rng = random.Random(0x8259B878)
    names = sorted({pattern['name'] for group in sets for pattern in group['patterns']})
    queries = names+['Trick', 'GestureSpeed', 'HoldPattern', 'RightAirGrab', 'LeftAirGrab', 'RightPush', 'LeftPush', 'Unrelated', 'shared', 'Shared\0tail', 'a'*36, 'a'*36+'tail']
    records, cases = [], []
    def add(operation, label, build):
        writer = Record()
        writer.word(operation)
        build(writer)
        records.append(bytes(writer.data))
        cases.append(dict(command=len(cases), operation=operation, kind=label, input_bytes=len(writer.data)))
    def reset(label):
        add(0, label, lambda w: None)
    def sample(axes, difficulty, flags, state, action, label):
        def build(w):
            w.scalars([component for stick in axes for component in stick])
            w.words((difficulty, flags, state, len(action)))
            for name, bits in action:
                w.raw(name)
                w.word(bits)
        add(1, label, build)
    authored_cases = 0
    for group in sets:
        for pattern in group['patterns']:
            for variant in range(10):
                authored_cases += 1
                if authored_cases % 32 == 1:
                    reset('fresh authored recognizers and retained hold name')
                flags = (0, 1 << 3, 1 << 4, 1 << 5, 1 << 8, 1 << 12, 0, 0, 0, 1 << 4)[variant]
                state = (100, 100, 200, 201, 503, 500, 100, 200, 201, 100)[variant]
                difficulty = variant % 3
                action = [('RightAirGrab', 0), ('Unrelated', 0x80000000)]
                if variant == 4:
                    action = [('LeftAirGrab', 0x7fc12345)]
                if variant == 6:
                    action = [('Unrelated', 0x80000000)]
                if variant == 7:
                    action += [('LeftPush', 0)]
                if variant == 8:
                    action = [('LeftAirGrab', 0), ('RightPush', 0x7fc12345)]
                # Match the manager's mapped-Y negation, including authored
                # pauses before progression and post-recognition held samples.
                def mapped(point):
                    axes = [[0., 0.], [0., 0.]]
                    axes[group['stick']] = [point[0], -point[1]]
                    return axes
                label = f'{group["name"]}/{pattern["name"]}/permission={variant}/difficulty={difficulty}'
                sample([[0., 0.], [0., 0.]], difficulty, flags, state, action, label)
                for _ in range(30):
                    sample(mapped(pattern['points'][0]), difficulty, flags, state, action, label)
                for point in pattern['points'][1:]:
                    for _ in range(1+variant % 2):
                        sample(mapped(point), difficulty, flags, state, action, label)
                for _ in range(10):
                    sample(mapped(pattern['points'][-1]), difficulty, flags, state, action, label)
                for _ in range(3):
                    sample([[0., 0.], [0., 0.]], difficulty, flags, state, action, label)
    reset('generated and held publication replay')
    all_points = [point for group in sets for pattern in group['patterns'] for point in pattern['points']]
    boundary = (0., -0., from_bits(0x3dcccccc), from_bits(0x3dcccccd), from_bits(0x3dccccce), -.1, 1., -1., from_bits(0x7fc12345))
    for tick in range(8192):
        axes = [list(rng.choice(all_points)), list(rng.choice(all_points))]
        if tick % 5 == 0:
            axes = [[rng.choice(boundary), rng.choice(boundary)] for _ in range(2)]
        if tick % 17 == 0:
            axes[1] = axes[0][:]
        flags = sum(1 << bit for index, bit in enumerate((3, 4, 5, 8, 12)) if (tick//29) & (1 << index))
        action = [('Unrelated', rng.getrandbits(32)), ('shared', 0), ('Shared\0tail', 0x7fc12345)]
        for index, name in enumerate(('RightAirGrab', 'LeftAirGrab', 'RightPush', 'LeftPush')):
            if tick & (1 << index):
                action.append((name, (0, 0x7fc12345, 0x80000000, 0xbf800000)[index]))
        sample(axes, (tick//97) % 3, flags, (100, 200, 201, 503, 500, 0)[tick % 6], action, 'generated simultaneous sticks, permission masks and deadzone boundaries')
    writer = Record()
    writer.word(len(queries))
    for name in queries:
        writer.raw(name)
    writer.word(len(records))
    offset = len(writer.data)
    for case in cases:
        case['input_offset'] = offset
        offset += case['input_bytes']
    return bytes(writer.data)+b''.join(records), cases, queries, authored_cases


def original_coverage(data, cases, queries):
    at = 0
    counts = Counter()
    named = set()
    strengths = set()
    nonempty = 0
    for case in cases:
        operation, = struct.unpack_from('<I', data, at)
        at += 4
        assert operation == case['operation']
        if operation == 0:
            continue
        size, = struct.unpack_from('<I', data, at)
        at += 4
        nonempty += size != 0
        for name in queries:
            present, = struct.unpack_from('<I', data, at)
            at += 4
            if present:
                value, = struct.unpack_from('<I', data, at)
                at += 4
                counts[name] += 1
                if name == 'GestureSpeed':
                    strengths.add(value)
                if name not in ('Trick', 'GestureSpeed', 'HoldPattern', 'RightAirGrab', 'LeftAirGrab', 'RightPush', 'LeftPush', 'Unrelated', 'shared', 'Shared\0tail', 'a'*36, 'a'*36+'tail'):
                    named.add(name)
    assert at == len(data)
    assert counts['Trick'] > 0 and counts['GestureSpeed'] > 0, 'Oracle never recognized or published a permitted trick'
    assert counts['HoldPattern'] > 0, 'Oracle never reached retained hold publication'
    assert len(named) >= 7, f'Authored recognizers did not publish diverse named events: {named}'
    return dict(trick_frames=counts['Trick'], strength_frames=counts['GestureSpeed'], hold_frames=counts['HoldPattern'],
                named_events=sorted(named), distinct_strength_bits=len(strengths), nonempty_maps=nonempty)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--assets', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--target-dir', type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    sets = converter.gesture_sets(args.assets/'private/stock/data/joystick')
    settings = output/'settings.native'
    gestures = output/'gestures.native'
    settings.write_bytes(converter.encode_settings(args.assets/'private/stock/skater-collections.json'))
    gestures.write_bytes(converter.encode_gestures(sets))
    reference = build_probe(output, 'gesture-input-reference', PLUGIN/'Tests/Reference/gesture_input_publication_probe.rs', args.target_dir)
    native = PLUGIN/'Source/AtelierSkate/Private/Native'
    candidate = output/'gesture-input-cpp'
    subprocess.run(['clang++', '-std=c++17', '-O2', '-ffp-contract=off', '-fno-fast-math', '-Wall', '-Wextra', '-Werror', '-I', str(native),
                    *(str(native/f'{name}.cpp') for name in ('NameId', 'Settings', 'AnimationName', 'Intents', 'Gestures', 'GestureInputPublication')),
                    str(PLUGIN/'Tests/Native/gesture_input_publication_probe.cpp'), '-o', str(candidate)], check=True)
    inputs, cases, queries, authored_cases = corpus(sets)
    (output/'input.bin').write_bytes(inputs)
    (output/'cases.json').write_text(json.dumps(cases, indent=2)+'\n')
    expected = subprocess.check_output([str(reference), str(args.assets)], input=inputs)
    actual = subprocess.check_output([str(candidate), str(settings), str(gestures)], input=inputs)
    if expected != actual:
        (output/'reference.bin').write_bytes(expected)
        (output/'candidate.bin').write_bytes(actual)
        first = next((i for i, (a, b) in enumerate(zip(actual, expected)) if a != b), min(len(actual), len(expected)))
        report = dict(passed=False, first_byte=first, reference_length=len(expected), candidate_length=len(actual),
                      reference_hex=expected[max(0, first-16):first+32].hex(), candidate_hex=actual[max(0, first-16):first+32].hex())
        (output/'first-divergence.json').write_text(json.dumps(report, indent=2)+'\n')
        raise AssertionError(report)
    coverage = original_coverage(expected, cases, queries)
    report = dict(passed=True, commands=len(cases), publication_frames=sum(case['operation'] == 1 for case in cases), authored_cases=authored_cases,
                  input_bytes=len(inputs), output_bytes=len(actual), output_sha256=hashlib.sha256(actual).hexdigest(), coverage=coverage,
                  comparison='exact original PAT/JSON manager ordering, recognition/held state effects, permission gates and every named AG map word; no tolerance',
                  limitations='Hidden original manager fields are exercised through subsequent publications rather than exposed. Whole session sampling/scheduling remains separate.',
                  reference_provenance='gesture-input-reference-provenance.json')
    (output/'result.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(report, indent=2), flush=True)


if __name__ == '__main__':
    main()
