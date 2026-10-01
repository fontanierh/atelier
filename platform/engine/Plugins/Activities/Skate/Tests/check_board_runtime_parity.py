#!/usr/bin/env python3
"""Exact persistent board lifecycle and shared board/attached simulation comparison.

Inputs exercise the real original BoardRuntime. Attached bodies and rows are
explicit fixtures, not a substitute for the pending gameplay skeleton producer.
Run through the render lock and memory guard.
"""
import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import random
import shutil
import struct
import subprocess
from reference_build import build_probe
from session_parity import PLUGIN


def bits(value):
    return struct.unpack('<I', struct.pack('<f', value))[0]


def corpus():
    rng = random.Random(0x82C0B2C8)
    cases, labels, words = [], [], []

    def floats(values):
        return list(map(bits, values))

    def transform(yaw, position):
        c, s = math.cos(yaw), math.sin(yaw)
        return floats([c, 0, -s, 0, 1, 0, s, 0, c, *position])

    def simulation(case, tick):
        # A stale frequency must be replaced inside BoardStep before reports.
        return [bits((1/60, 1/120, 1/30)[(case+tick) % 3]), bits(17), 30, bits(.001), *floats([0, -9.81, 0])]

    for case in range(96):
        mode, attached = case % 3, (0, 1, 3)[(case//3) % 3]
        header = [mode, *transform(case*.17, [case*.03, .2, -.1]), *simulation(case, 0)]
        custom_mass = case % 2
        header.append(custom_mass)
        if custom_mass:
            for n in range(7):
                header.extend(transform((n+1)*.04, [.02*n, -.004, .003]))
        header.append(attached)
        for n in range(attached):
            header.extend([4 if mode == 0 else 2, *floats([.03*n, .6+.2*n, .02])])
        commands = []
        meta = dict(case=case, mode=mode, attached=attached, custom_mass=bool(custom_mass))
        labels.append(dict(**meta, command=-1, operation='construct'))

        def add(op, payload=(), purpose=''):
            labels.append(dict(**meta, command=len(commands), operation=op, purpose=purpose))
            commands.append([op, *payload])

        def mutate(id, state, phase):
            add(5, [id, state, *floats([rng.uniform(-2, 2) for _ in range(12)]), bits(.3), 17], phase)

        def advance(tick, contact_count):
            ids = list(range(7))+list(range(8, 8+attached))
            payload = [*simulation(case, tick), (0, 1, 8, 25)[(case+tick) % 4],
                       *floats([.3*math.sin(tick), -.2*math.cos(tick), .025]), contact_count]
            for n in range(contact_count):
                # Both original A/B orders, all board parts and attached bodies;
                # a penetrating manifold can generate >16 report candidates.
                payload.extend([ids[n % len(ids)], (n+tick) % 2,
                                *floats([(-.01, 0, .002)[(n+tick) % 3], 0, 1, 0, .05, .8, .5]),
                                ((n+1) << 16) | ((n+tick+7) & 0xffff)])
            payload.append(tick % 2)
            add(7, payload, 'shared solve and post-integration contact reports')

        add(9, [1], 'enable diagnostic cadence')
        for n in range(25):
            add(0, [n % 3, *floats([.1*n, 0, 3, -.1, -0.0, .05])], 'capacity, repeated tags, append order')
        for n in range(8):
            mutate(n, (4, 2, 1)[mode] if n < 7 else 1, 'publish rates and forces before solver')
        for tick in range(7):
            advance(tick, 20 if tick == 3 else 7)
        add(9, [1], 'take completed snapshot without disabling capture')
        add(2, transform(.9, [1, .4, -2]), 'move assembly retaining rates, force queue and contacts')
        for hook in range(6):
            add(6, [153, hook], 'hook drive lifecycle')
            add(3, transform(.1*hook, [1, .5+.01*hook, -2]), 'separate animated target')
            advance(hook+8, 3)
        add(1, purpose='explicit force queue clear')
        add(8, [7], 'wipeout assembly collision group')
        add(4, [0x00100000 if case % 2 else 0, *floats([0, -9.81, 0]), *transform(-.6, [-1, .3, 2])],
            'physical reset, stance, retained flags/inertias and separate hook rates')
        add(9, [1], 'physical reset cleared diagnostics owner')
        for tick in range(8):
            advance(tick+20, 7)
        for n in list(range(8))+list(range(8, 8+attached)):
            mutate(n, 2 if n != 7 else 1, 'all assemblies inactive')
        add(0, [7, *floats([1, 2, 3, .1, -.0, -.1])], 'force queue still applies before inactive return')
        advance(30, 4)
        add(9, [0], 'consume retained diagnostic snapshot')
        add(8, [4], 'restore normal collision group')
        record = header+[len(commands)]
        for command in commands:
            record.extend(command)
        cases.append(record)
    words.append(len(cases))
    for case in cases:
        words.extend(case)
    return struct.pack(f'<{len(words)}I', *words), labels


def inspect(data, labels):
    assert len(data) % 4 == 0
    words = struct.unpack(f'<{len(data)//4}I', data)
    at = 0
    counts = Counter()
    for label in labels:
        size = words[at]
        end = at+size+1
        label.update(output_word=at, output_words=size+1)
        result = words[at+1]
        if label['operation'] == 0 and result == 0:
            counts['rejected_forces'] += 1
        if label['operation'] == 9 and result:
            counts['diagnostic_snapshots'] += 1
        # Result, eight full body snapshots, hook drive, then 15 transforms.
        p = at+1+1+8*49+24+15*12
        forces = words[p]
        assert forces <= 21
        p += 1+forces*7+2  # entries, total mass, group
        contacts = words[p]
        p += 1+contacts*66
        reports = words[p]
        assert reports <= 16
        counts['observed_solved_rows'] += contacts
        counts['observed_reports'] += reports
        p += 1+reports*25
        attached = words[p]
        assert attached == label['attached']
        p += 1+attached*49
        for width in (66, 98, 98):
            rows = words[p]
            p += 1+rows*width
        assert p == end, (label, p, end)
        at = end
    assert at == len(words)
    assert counts['rejected_forces'] == 96*4
    assert counts['observed_reports'] > 0
    assert counts['diagnostic_snapshots'] > 0
    return counts


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--target-dir', type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    for name in ('result.json', 'first-divergence.json'):
        (output/name).unlink(missing_ok=True)
    reference = build_probe(output, 'board-runtime-reference', PLUGIN/'Tests/Reference/board_runtime_probe.rs', args.target_dir)
    source = output/'native-source'
    if source.exists():
        shutil.rmtree(source)
    source.mkdir()
    units = ('NativeMath', 'RigidBody', 'BodyMass', 'AggregateMass', 'DeckGeometry', 'DriveFrames',
             'ConstraintFrames', 'ConstraintSolver', 'JointBuild', 'DriveBuild', 'JointRecords',
             'TruckDriveFrames', 'DrivePreparation', 'HookDrive', 'BoardAssembly', 'ContactBuild',
             'ContactGeneration', 'BoardPose', 'ForceQueue', 'CollisionBody', 'BoardContactFeedback',
             'BoardStep', 'BoardRuntime')
    names = [f'{unit}.{ext}' for unit in units for ext in ('h', 'cpp')] + ['GeometryTypes.h', 'BoardTypes.h', 'ContactRetention.h']
    for name in names:
        shutil.copy2(PLUGIN/'Source/AtelierSkate/Private/Native'/name, source/name)
    shutil.copy2(PLUGIN/'Tests/Native/board_runtime_probe.cpp', source/'board_runtime_probe.cpp')
    candidate = output/'board-runtime-cpp'
    subprocess.run(['clang++', '-std=c++17', '-O2', '-ffp-contract=off', '-fno-fast-math', '-fno-exceptions',
                    '-Wall', '-Wextra', '-Werror', '-I', str(source), *[str(source/f'{unit}.cpp') for unit in units],
                    str(source/'board_runtime_probe.cpp'), '-o', str(candidate)], check=True)
    provenance = dict(native_source_sha256={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(source.iterdir())},
                      binary_sha256=hashlib.sha256(candidate.read_bytes()).hexdigest(),
                      compiler=subprocess.check_output(['clang++', '--version'], text=True).strip())
    (output/'native-provenance.json').write_text(json.dumps(provenance, indent=2)+'\n')
    inputs, labels = corpus()
    (output/'inputs.bin').write_bytes(inputs)
    expected = subprocess.check_output([str(reference)], input=inputs)
    actual = subprocess.check_output([str(candidate)], input=inputs)
    (output/'reference.bin').write_bytes(expected)
    (output/'candidate.bin').write_bytes(actual)
    counts = inspect(expected, labels)
    (output/'cases.json').write_text(json.dumps(labels, indent=2)+'\n')
    if expected != actual:
        first = next((n for n, (a, b) in enumerate(zip(expected, actual)) if a != b), min(len(expected), len(actual)))//4
        label = next((item for item in labels if item['output_word'] <= first < item['output_word']+item['output_words']), None)
        report = dict(passed=False, first_word=first, case=label,
                      case_word=first-label['output_word'] if label else None,
                      reference=expected[first*4:first*4+4].hex(), cpp=actual[first*4:first*4+4].hex())
        (output/'first-divergence.json').write_text(json.dumps(report, indent=2)+'\n')
        raise AssertionError(report)
    result = dict(passed=True, streams=96, snapshots=len(labels), output_words=len(actual)//4, output_bytes=len(actual),
                  observed=dict(counts), sha256=hashlib.sha256(actual).hexdigest(),
                  comparison='exact persistent board, attached shared constraints and integrated bodies, force queue, contacts, reports, pose/reset lifecycle; diagnostic cadence/presence only, native diagnostic representation differs; not gameplay skeleton producers')
    (output/'result.json').write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps(result, indent=2), flush=True)


if __name__ == '__main__':
    main()
