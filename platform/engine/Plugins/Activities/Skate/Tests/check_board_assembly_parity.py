#!/usr/bin/env python3
"""Compare assembled board constraints, shared solve and body integration exactly.

The independent oracle calls the frozen original public assembly and solver.
Run through the render lock/memory guard; this is not a complete gameplay test.
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
    rng = random.Random(0x82C0B9C1)
    records, labels = [], []

    def floats(values):
        return list(map(bits, values))

    def quaternion():
        values = [rng.uniform(-1, 1) for _ in range(4)]
        norm = math.sqrt(sum(v*v for v in values))
        return [v/norm for v in values]

    def basis(q):
        x, y, z, w = q
        return [1-2*(y*y+z*z), 2*(x*y+w*z), 2*(x*z-w*y),
                2*(x*y-w*z), 1-2*(x*x+z*z), 2*(y*z+w*x),
                2*(x*z+w*y), 2*(y*z-w*x), 1-2*(x*x+y*y)]

    def body(state):
        q = quaternion()
        inverse = [rng.uniform(.1, 3) for _ in range(3)]
        # Independent current tensor/basis fields exercise the snapshot adapter.
        world = [inverse[0], .013, -.031, .013, inverse[1], .051, -.031, .051, inverse[2]]
        velocities = [rng.uniform(-10, 10) for _ in range(15)]
        values = [state, *floats(q+basis(quaternion())+world+velocities), bits(rng.uniform(0, 10)), rng.randrange(30),
                  *floats(inverse+[rng.uniform(.1, 2), 0, 20, 30, .01, .03])]
        assert len(values) == 49
        return values

    for index in range(2048):
        stock = index < 512
        mask = index % 256
        flags = [(4 if mask & (1 << n) else 0) | (index//256 << 4) for n in range(8)]
        record = [int(stock)]
        record.extend(flags if stock else [word for state in flags for word in body(state)])
        hook_frames = []
        for side in range(2):
            q = [0, 0, 0, 1] if index < 256 else [v*rng.uniform(.5, 2) for v in quaternion()]
            translation = [0, 0, 0] if index < 256 else [rng.uniform(-.5, .5) for _ in range(3)]
            hook_frames.extend(floats(q+translation)+[rng.getrandbits(32)])
        record.extend(hook_frames)
        hook_types = [index % 4, (index//4) % 4]
        for kind in hook_types:
            record.extend(floats([rng.uniform(0, 2000), rng.uniform(0, 20), rng.uniform(0, 100)])+[kind])
        for side in range(2):
            q = [0, 0, 0, 1] if index < 256 else quaternion()
            record.extend(floats(basis(q)+[rng.uniform(-.3, .3) for _ in range(3)]))
        targets = [0, 0] if index % 8 == 0 else [rng.uniform(-.7, .7) for _ in range(2)]
        record.extend(floats(targets))
        linear, hard = index % 2, (index//2) % 2
        record.extend([linear, hard, *floats([10, 0, 11] if stock else [rng.uniform(0, 20), rng.uniform(0, 5), rng.uniform(0, 20)])])
        dt = (1/60, 1/120, 1/30)[index % 3]
        calls, iterations = 1+index % 4, (0, 1, 2, 8, 25)[index % 5]
        record.extend([bits(dt), calls, iterations])
        records.append(record)
        labels.append(dict(case=index, stock=stock, active_mask=mask, flags=flags, preparation_calls=calls,
                           iterations=iterations, hook_types=hook_types, linear=linear, hard=hard))
    words = [len(records)]
    for record in records:
        words.extend(record)
    return struct.pack(f'<{len(words)}I', *words), labels


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--target-dir', type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    for name in ('result.json', 'first-divergence.json'):
        (output/name).unlink(missing_ok=True)
    reference = build_probe(output, 'board-assembly-reference', PLUGIN/'Tests/Reference/board_assembly_probe.rs', args.target_dir)
    source = output/'native-source'
    if source.exists():
        shutil.rmtree(source)
    source.mkdir()
    units = ('NativeMath', 'RigidBody', 'BodyMass', 'AggregateMass', 'DeckGeometry', 'DriveFrames',
             'ConstraintFrames', 'ConstraintSolver', 'JointBuild', 'DriveBuild', 'JointRecords',
             'TruckDriveFrames', 'DrivePreparation', 'HookDrive', 'BoardAssembly')
    names = [f'{unit}.{ext}' for unit in units for ext in ('h', 'cpp')] + ['GeometryTypes.h', 'BoardTypes.h']
    for name in names:
        shutil.copy2(PLUGIN/'Source/AtelierSkate/Private/Native'/name, source/name)
    shutil.copy2(PLUGIN/'Tests/Native/board_assembly_probe.cpp', source/'board_assembly_probe.cpp')
    candidate = output/'board-assembly-cpp'
    subprocess.run(['clang++', '-std=c++17', '-O2', '-ffp-contract=off', '-fno-fast-math', '-fno-exceptions',
                    '-Wall', '-Wextra', '-Werror', '-I', str(source),
                    *[str(source/f'{unit}.cpp') for unit in units], str(source/'board_assembly_probe.cpp'),
                    '-o', str(candidate)], check=True)
    provenance = dict(native_source_sha256={p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(source.iterdir())},
                      candidate_sha256=hashlib.sha256(candidate.read_bytes()).hexdigest(),
                      compiler=subprocess.check_output(['clang++', '--version'], text=True).strip())
    (output/'native-provenance.json').write_text(json.dumps(provenance, indent=2)+'\n')
    inputs, labels = corpus()
    (output/'inputs.bin').write_bytes(inputs)
    expected = subprocess.check_output([str(reference)], input=inputs)
    actual = subprocess.check_output([str(candidate)], input=inputs)
    (output/'reference.bin').write_bytes(expected)
    (output/'candidate.bin').write_bytes(actual)
    at = 0
    counts = Counter()
    for label in labels:
        length = struct.unpack_from('<I', expected, at)[0]
        label.update(output_byte=at, output_bytes=4*(length+1))
        # The oracle emits frames/live hook state for each preparation, then
        # the ordered joint/drive lists. Check all eight-bit activation masks.
        offset = at+4+label['preparation_calls']*66*4
        joint_count = struct.unpack_from('<I', expected, offset)[0]
        offset += 4+joint_count*98*4
        drive_count = struct.unpack_from('<I', expected, offset)[0]
        mask = label['active_mask']
        pairs = ((4, 6), (5, 6), (0, 4), (1, 4), (2, 5), (3, 5))
        assert joint_count == sum(bool(mask & ((1 << a) | (1 << b))) for a, b in pairs)
        assert drive_count == sum(bool(mask & ((1 << a) | (1 << 6))) for a in (4, 5, 7))
        counts['joints'] += joint_count
        counts['drives'] += drive_count
        at += label['output_bytes']
    assert at == len(expected), (at, len(expected))
    (output/'cases.json').write_text(json.dumps(labels, indent=2)+'\n')
    if expected != actual:
        first = next((n for n, (a, b) in enumerate(zip(expected, actual)) if a != b), min(len(expected), len(actual)))
        case = next((label for label in labels if label['output_byte'] <= first < label['output_byte']+label['output_bytes']), None)
        word = first//4
        report = dict(passed=False, first_word=word, case=case,
                      case_word=(first-case['output_byte'])//4 if case else None,
                      reference=expected[word*4:word*4+4].hex(), cpp=actual[word*4:word*4+4].hex())
        (output/'first-divergence.json').write_text(json.dumps(report, indent=2)+'\n')
        raise AssertionError(report)
    result = dict(passed=True, cases=len(labels), output_words=len(actual)//4, output_bytes=len(actual),
                  counts=dict(counts), activation_masks=len({x['active_mask'] for x in labels}),
                  sha256=hashlib.sha256(actual).hexdigest(),
                  comparison='exact full typed and packed assembly rows, live hook normalization, shared joint/drive solve and resulting body rate updates; not complete gameplay')
    (output/'result.json').write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps(result, indent=2), flush=True)


if __name__ == '__main__':
    main()
